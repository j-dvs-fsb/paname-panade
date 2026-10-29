"""Client HTTP poli : c'est le seul endroit du projet qui parle au réseau.

- User-Agent identifiable ;
- robots.txt lu avant toute page, respecté, jamais contourné ;
- une requête par seconde et par domaine au maximum ;
- requêtes conditionnelles (ETag, If-Modified-Since) : un 304 coûte presque rien ;
- corps lu au plus `max_octets`, redirections suivies à la main (chaque
  nouvelle destination repasse par robots.txt et par la limite de débit).

Les tests injectent un `httpx.MockTransport` : aucune requête réelle hors
des commandes `probe`, `discover` et `collect`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urljoin, urlsplit

import httpx

from panade.robots import Robots

USER_AGENT = "PanadeCollector/1.0 (+https://paname-panade.fr/bot)"
PRODUIT = "PanadeCollector"
MAX_REDIRECTIONS = 5


class Verdict(Enum):
    AUTORISE = "autorise"
    INTERDIT = "interdit"          # robots.txt interdit : le lieu relève du tier T4
    INJOIGNABLE = "injoignable"    # robots.txt en 5xx ou illisible : on s'abstient, sans conclure


class AccesRefuse(Exception):
    def __init__(self, verdict: Verdict, raison: str):
        super().__init__(raison)
        self.verdict = verdict
        self.raison = raison


class ErreurReseau(Exception):
    pass


@dataclass
class Reponse:
    url: str
    statut: int
    texte: str = ""
    etag: str | None = None
    derniere_modif: str | None = None
    type_contenu: str = ""
    entetes: dict[str, str] = field(default_factory=dict)
    tronque: bool = False

    @property
    def non_modifie(self) -> bool:
        return self.statut == 304

    @property
    def ok(self) -> bool:
        return 200 <= self.statut < 300


@dataclass
class ResultatRobots:
    verdict: Verdict
    raison: str
    robots: Robots | None = None


def origine(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


class ClientPoli:
    def __init__(self, *, transport: httpx.BaseTransport | None = None, intervalle: float = 1.0,
                 horloge=time.monotonic, dormir=time.sleep, delai: float = 20.0,
                 max_octets: int = 2_000_000, pause_reprise: float = 2.0):
        self._http = httpx.Client(
            transport=transport, timeout=delai, follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "fr",
                     "Accept": "text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.5"},
        )
        self.intervalle = intervalle
        self._horloge = horloge
        self._dormir = dormir
        self.max_octets = max_octets
        self.pause_reprise = pause_reprise
        self._dernier: dict[str, float] = {}
        self._robots: dict[str, ResultatRobots] = {}
        self.requetes = 0

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- robots.txt -----------------------------------------------------

    def robots(self, url: str) -> ResultatRobots:
        """Verdict de robots.txt pour l'origine de `url` (mis en cache pour la durée du client)."""
        base = origine(url)
        if base not in self._robots:
            self._robots[base] = self._lire_robots(base)
        return self._robots[base]

    def _lire_robots(self, base: str) -> ResultatRobots:
        try:
            url = f"{base}/robots.txt"
            for _ in range(MAX_REDIRECTIONS + 1):  # museedemontmartre.fr redirige vers www.
                r = self._requete(url, {})
                if r.statut in (301, 302, 303, 307, 308) and r.entetes.get("location"):
                    url = urljoin(url, r.entetes["location"])
                    continue
                break
        except ErreurReseau as exc:
            return ResultatRobots(Verdict.INJOIGNABLE, f"robots.txt injoignable ({exc})")
        if r.statut >= 500 or r.statut in (408, 429):
            return ResultatRobots(Verdict.INJOIGNABLE, f"robots.txt injoignable (HTTP {r.statut})")
        if 400 <= r.statut < 500:  # RFC 9309 : pas de robots.txt = tout est permis
            return ResultatRobots(Verdict.AUTORISE, f"pas de robots.txt (HTTP {r.statut})", Robots())
        return ResultatRobots(Verdict.AUTORISE, "robots.txt lu", Robots.lire(r.texte))

    def verdict(self, url: str) -> ResultatRobots:
        """Verdict pour une URL précise : AUTORISE, INTERDIT ou INJOIGNABLE."""
        res = self.robots(url)
        if res.verdict is not Verdict.AUTORISE or res.robots is None:
            return res
        p = urlsplit(url)
        chemin = (p.path or "/") + (f"?{p.query}" if p.query else "")
        if res.robots.autorise(PRODUIT, chemin):
            return ResultatRobots(Verdict.AUTORISE, res.raison, res.robots)
        return ResultatRobots(Verdict.INTERDIT, f"robots.txt interdit {p.path or '/'}", res.robots)

    # --- pages ----------------------------------------------------------

    def get(self, url: str, *, etag: str | None = None, derniere_modif: str | None = None,
            params: dict | None = None) -> Reponse:
        """GET poli. Lève AccesRefuse si robots.txt interdit ou est injoignable."""
        conditionnel = {}
        if etag:
            conditionnel["If-None-Match"] = etag
        if derniere_modif:
            conditionnel["If-Modified-Since"] = derniere_modif
        courante = url
        for _ in range(MAX_REDIRECTIONS + 1):
            v = self.verdict(courante)
            if v.verdict is not Verdict.AUTORISE:
                raise AccesRefuse(v.verdict, v.raison)
            r = self._requete(courante, conditionnel, params if courante == url else None)
            suite = r.entetes.get("location")
            if r.statut in (301, 302, 303, 307, 308) and suite:
                courante = urljoin(courante, suite)
                continue
            return r
        raise ErreurReseau(f"plus de {MAX_REDIRECTIONS} redirections depuis {url}")

    def _requete(self, url: str, entetes: dict, params: dict | None = None) -> Reponse:
        """Une requête, avec limite de débit et une seule reprise sur coupure de connexion."""
        derniere_erreur: Exception | None = None
        for tentative in range(2):
            self._attendre(urlsplit(url).netloc)
            try:
                return self._envoyer(url, entetes, params)
            except httpx.TransportError as exc:
                derniere_erreur = exc
                if tentative == 0:
                    self._dormir(self.pause_reprise)
        raise ErreurReseau(f"{type(derniere_erreur).__name__}: {derniere_erreur}")

    def _attendre(self, hote: str) -> None:
        attente = self._dernier.get(hote, -1e9) + self.intervalle - self._horloge()
        if attente > 0:
            self._dormir(attente)
        self._dernier[hote] = self._horloge()

    def _envoyer(self, url: str, entetes: dict, params: dict | None) -> Reponse:
        self.requetes += 1
        requete = self._http.build_request("GET", url, headers=entetes, params=params)
        reponse = self._http.send(requete, stream=True)
        try:
            morceaux, total, tronque = [], 0, False
            for bloc in reponse.iter_bytes():
                morceaux.append(bloc)
                total += len(bloc)
                if total > self.max_octets:
                    tronque = True
                    break
            corps = b"".join(morceaux)[: self.max_octets]
            h = {k.lower(): v for k, v in reponse.headers.items()}
            encodage = reponse.charset_encoding or "utf-8"
            return Reponse(
                url=str(reponse.url), statut=reponse.status_code,
                texte=corps.decode(encodage, errors="replace"),
                etag=h.get("etag"), derniere_modif=h.get("last-modified"),
                type_contenu=h.get("content-type", ""), entetes=h, tronque=tronque,
            )
        finally:
            reponse.close()
