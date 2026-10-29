"""`panade probe` : classe un lieu en T0..T4 sans rien scraper.

Teste dans l'ordre du brief et s'arrête au premier succès : API ouverte (T0),
JSON-LD Event, flux RSS, .ics (T1), billetterie mutualisée connue (T2), sitemap.xml (T1).
Sans aucun signal, un site lisible vaut T3 (HTML lu par un extracteur dédié).
Un robots.txt qui interdit vaut T4 : on ne va pas plus loin.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from panade import html as h
from panade.http import AccesRefuse, ClientPoli, ErreurReseau, Verdict, origine

# Billetteries partagées par plusieurs musées : une intégration en couvre N.
BILLETTERIES = (
    (re.compile(r"(^|\.)tickeasy\.com$|vivaticket", re.I), "Tickeasy / Vivaticket"),
    (re.compile(r"(^|\.)billetterie-parismusees\.paris\.fr$", re.I), "billetterie Paris Musées"),
)


@dataclass
class Sonde:
    lieu: str
    tier: str | None
    statut: str                 # ok | indetermine | verrouille
    preuve: str
    url_utile: str | None = None
    tier_enregistre: str | None = None
    notes: list[str] = field(default_factory=list)

    def en_json(self) -> dict:
        concorde = None if self.tier is None or self.tier_enregistre is None \
            else self.tier == self.tier_enregistre
        sortie = {"lieu": self.lieu, "tier": self.tier, "preuve": self.preuve,
                  "url_utile": self.url_utile, "statut": self.statut,
                  "tier_enregistre": self.tier_enregistre, "concorde": concorde}
        if self.notes:
            sortie["notes"] = self.notes
        return sortie


# --- T0 : API ouvertes ---------------------------------------------------------

class QueFaireAParis:
    """Agenda de la Ville de Paris (Opendatasoft, sans clé)."""

    nom = "Que Faire à Paris"
    url = "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/que-faire-a-paris-/records"
    champs = ("contact_url", "access_link", "address_url")

    def presence(self, client: ClientPoli, domaine: str) -> int:
        """Nombre d'événements dont un lien officiel pointe vers ce domaine.

        La recherche plein texte d'Opendatasoft découpe les URL en mots : on revérifie
        donc l'hôte de chaque lien renvoyé, pour ne pas confondre `carnavalet.paris.fr`
        avec une page de paris.fr qui parle de Carnavalet.
        """
        recherche = " or ".join(f'search({c}, "{domaine}")' for c in self.champs)
        r = client.get(self.url, params={"where": recherche, "select": ",".join(self.champs), "limit": 50})
        if not r.ok:
            raise ErreurReseau(f"HTTP {r.statut}")
        try:
            lignes = json.loads(r.texte).get("results", [])
        except ValueError as exc:
            raise ErreurReseau("réponse JSON illisible") from exc
        n = 0
        for ligne in lignes:
            hotes = {urlsplit(ligne.get(c) or "").netloc.lower().removeprefix("www.") for c in self.champs}
            if any(hote == domaine or hote.endswith("." + domaine) for hote in hotes):
                n += 1
        return n


SOURCES_OUVERTES = (QueFaireAParis(),)


# --- signaux dans une page --------------------------------------------------------

def signaux(page_html: str, base: str) -> dict:
    arbre = h.lire(page_html)
    sortie: dict = {"jsonld": None, "rss": None, "ics": None, "billetteries": []}
    for objet in h.jsonld(arbre):
        if any(t.endswith("Event") for t in h.types_jsonld(objet)):
            sortie["jsonld"] = objet.get("name") or "Event"
            break
    for lien in arbre.css("link[rel~=alternate][type]"):
        type_ = (lien.attributes.get("type") or "").lower()
        href = h.absolu(base, lien.attributes.get("href"))
        if href and sortie["rss"] is None and ("rss" in type_ or "atom" in type_):
            sortie["rss"] = href
        if href and sortie["ics"] is None and "calendar" in type_:
            sortie["ics"] = href
    for a in arbre.css("a[href]"):
        href = (a.attributes.get("href") or "").strip()
        if sortie["ics"] is None and re.search(r"\.ics(\?|$)|^webcal://", href, re.I):
            sortie["ics"] = h.absolu(base, href.replace("webcal://", "https://", 1))
        lien = h.absolu(base, href)
        if lien:
            hote = urlsplit(lien).netloc
            for motif, nom in BILLETTERIES:
                if motif.search(hote) and (nom, hote) not in sortie["billetteries"]:
                    sortie["billetteries"].append((nom, hote))
    return sortie


def _billetterie_declaree(plateforme: str | None) -> str | None:
    for motif, nom in BILLETTERIES:
        if plateforme and motif.search(plateforme):
            return nom
    return None


# --- la sonde -------------------------------------------------------------------------

def sonder(lieu, client: ClientPoli, sources=SOURCES_OUVERTES) -> Sonde:
    """`lieu` : ligne de la table lieux. N'écrit rien."""
    s = Sonde(lieu["id"], None, "indetermine", "", tier_enregistre=lieu["tier"])
    depart = lieu["expos_url"] or lieu["tarifs_url"] or lieu["horaires_url"]

    if lieu["tier"] == "T4":
        # Décision manuelle : jamais de collecte automatique. On relit seulement robots.txt.
        s.statut, s.tier = "verrouille", "T4"
        s.preuve = "lieu verrouillé en T4 (collecte manuelle)"
        if depart:
            v = client.verdict(depart)
            if v.verdict is Verdict.AUTORISE:
                s.notes.append("robots.txt actuel n'interdit pas ce site, mais le T4 est maintenu "
                               "(décision du brief) : à réexaminer par une personne")
            else:
                s.notes.append(f"robots.txt : {v.raison}")
        return s

    if not depart:
        s.preuve = "aucune URL renseignée pour ce lieu"
        return s

    v = client.verdict(depart)
    if v.verdict is Verdict.INTERDIT:
        s.tier, s.statut, s.preuve = "T4", "ok", v.raison
        return s
    if v.verdict is Verdict.INJOIGNABLE:
        s.preuve = v.raison + ", on s'abstient"
        return s

    base = origine(depart)
    domaine = urlsplit(depart).netloc.lower().removeprefix("www.")

    # T0
    for source in sources:
        try:
            n = source.presence(client, domaine)
        except (ErreurReseau, AccesRefuse) as exc:
            s.notes.append(f"{source.nom} injoignable ({exc})")
            continue
        if n:
            s.tier, s.statut = "T0", "ok"
            s.preuve = f"{n} événement(s) de {domaine} dans {source.nom}"
            s.url_utile = source.url
            return s

    # La page de départ, une seule fois, pour JSON-LD, RSS, .ics et billetterie.
    try:
        page = client.get(depart)
        if page.statut in (404, 410) and depart != base + "/":
            s.notes.append(f"{depart} : HTTP {page.statut}, repli sur la page d'accueil")
            depart = base + "/"
            page = client.get(depart)
    except AccesRefuse as exc:
        s.tier, s.statut, s.preuve = ("T4", "ok", exc.raison) if exc.verdict is Verdict.INTERDIT \
            else (None, "indetermine", exc.raison)
        return s
    except ErreurReseau as exc:
        s.preuve = f"page injoignable ({exc})"
        return s
    if not page.ok:
        s.preuve = f"page en HTTP {page.statut}, pas de contournement"
        return s

    sig = signaux(page.texte, page.url)
    if sig["jsonld"]:
        return _trouve(s, "T1", f"JSON-LD Event « {sig['jsonld']} » dans la page", page.url)
    if sig["rss"]:
        return _trouve(s, "T1", "flux RSS ou Atom annoncé par la page", sig["rss"])
    if sig["ics"]:
        return _trouve(s, "T1", "calendrier .ics annoncé par la page", sig["ics"])
    if sig["billetteries"]:
        nom, hote = sig["billetteries"][0]
        return _trouve(s, "T2", f"lien vers la billetterie mutualisée {nom} ({hote})", page.url)
    declaree = _billetterie_declaree(lieu["plateforme_billetterie"])
    if declaree:
        return _trouve(s, "T2", f"billetterie mutualisée {declaree} déclarée dans la base", page.url)

    # sitemap.xml
    robots = client.robots(depart).robots
    for candidat in (robots.sitemaps if robots and robots.sitemaps else [base + "/sitemap.xml"]):
        try:
            r = client.get(candidat)
        except (AccesRefuse, ErreurReseau):
            continue
        if r.ok and re.search(r"<(urlset|sitemapindex)\b", r.texte[:4000]):
            return _trouve(s, "T1", "sitemap.xml présent", r.url)

    return _trouve(s, "T3", "page HTML lisible, aucun format structuré trouvé", page.url)


def _trouve(s: Sonde, tier: str, preuve: str, url: str) -> Sonde:
    s.tier, s.statut, s.preuve, s.url_utile = tier, "ok", preuve, url
    return s
