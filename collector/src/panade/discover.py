"""`panade discover` : la phase de découverte, sans appeler de modèle.

Trouve la page qui liste les expositions d'un lieu, en garde une copie réduite
dans les fixtures (pour que tout le reste se teste hors ligne) et vérifie ce que
l'extracteur du lieu en tire. Écrire ou régénérer un extracteur reste le travail
de Claude Code, une fois par mutualisation, à partir de cette fixture.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from panade import extractors, html as h
from panade.http import AccesRefuse, ClientPoli, ErreurReseau, origine

# Le chemin de la page expos varie d'un site Paris Musées à l'autre : on les essaie, puis
# on lit le menu de la première page 404 rencontrée.
CHEMINS_PARIS_MUSEES = (
    "/expositions/expositions-en-cours",
    "/expositions/exposition-en-cours",
    "/visiter/expositions/expositions-en-cours",
)
MENU = re.compile(r"^/[^?#]*(expositions?-en-cours|/expositions?|programmation[^?#]*/expositions?)$", re.I)


@dataclass
class Decouverte:
    lieu: str
    statut: str                       # ok | echec
    detail: str
    url_demandee: str | None = None
    url_finale: str | None = None
    fixture: str | None = None
    extracteur: str | None = None
    expositions: int | None = None
    octets_bruts: int = 0
    octets_reduits: int = 0
    essais: list[str] = field(default_factory=list)

    def en_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], 0)} | {"statut": self.statut}


def _page_d_accueil(url: str) -> bool:
    return urlsplit(url).path in ("", "/")


def decouvrir(lieu, client: ClientPoli, dossier_fixtures: Path, aujourdhui: date) -> Decouverte:
    d = Decouverte(lieu["id"], "echec", "")
    if lieu["tier"] == "T4":
        d.detail = "lieu T4 : collecte manuelle, rien n'est téléchargé"
        return d
    depart = lieu["expos_url"]
    if not depart:
        d.detail = "aucune expos_url : à renseigner d'abord"
        return d

    candidats = [depart]
    if lieu["famille_id"] == "paris_musees" and _page_d_accueil(depart):
        candidats = [origine(depart) + c for c in CHEMINS_PARIS_MUSEES]
    page, retenue, menu_lu = None, None, False
    while candidats and page is None:
        url = candidats.pop(0)
        d.essais.append(url)
        try:
            reponse = client.get(url)
        except AccesRefuse as exc:
            d.detail = exc.raison
            return d
        except ErreurReseau as exc:
            d.detail = f"réseau : {exc}"
            return d
        if reponse.ok:
            page, retenue = reponse, url
        elif reponse.statut == 404 and not menu_lu and lieu["famille_id"] == "paris_musees":
            menu_lu = True
            liens = {a.attributes["href"] for a in h.lire(reponse.texte).css("a[href]") if MENU.match(a.attributes["href"])}
            candidats += [origine(url) + lien for lien in sorted(liens) if origine(url) + lien not in d.essais][:3]
    if page is None:
        d.detail = f"aucune page d'expositions trouvée ({len(d.essais)} essais)"
        return d

    d.url_demandee, d.url_finale = retenue, page.url
    reduit = h.reduire(page.texte)
    d.octets_bruts, d.octets_reduits = len(page.texte), len(reduit)
    dossier_fixtures.mkdir(parents=True, exist_ok=True)
    chemin = dossier_fixtures / f"{lieu['id']}.html"
    chemin.write_text(reduit, encoding="utf-8")
    d.fixture = str(chemin)

    choix = extractors.choisir({**dict(lieu), "expos_url": retenue})
    if choix is None:
        d.statut, d.detail = "ok", "page enregistrée ; pas d'extracteur pour ce lieu : à écrire à partir de la fixture"
        return d
    d.extracteur = choix[0]
    d.expositions = len(choix[1].extraire(page.texte, page.url, aujourdhui))
    d.statut = "ok" if d.expositions else "echec"
    d.detail = f"{d.expositions} exposition(s) extraite(s)" if d.expositions else \
        "l'extracteur ne trouve rien sur cette page : à régénérer, ou aucune exposition en cours"
    return d
