"""Portail du réseau Paris Musées : une page, les expositions des 14 musées de la Ville.

C'est la mutualisation la plus rentable du projet. Une seule page couvre les 12 lieux Paris
Musées de la base, y compris quand le site propre d'un musée est en maintenance (ce qui était
le cas de 9 sur 12 le 2026-10-29). `collect` ne la télécharge qu'une fois par passage.

Carte observée : article.node--type-exposition > a[href=/fr/exposition/...] avec .nom-musee,
.description .title (+ sous-titre), dates en deux morceaux « 29 » « 09/26 » (jour, mois/année).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from panade import html as h
from panade.extractors import ExpoBrute
from panade.extractors.paris_musees import _image

SOURCE = "https://www.parismusees.paris.fr/fr/expositions"

# lieu de la base -> nom affiché par le portail (comparaison sans accents ni casse, par inclusion)
MUSEES = {
    "musee-carnavalet-histoire-de-paris": "musee carnavalet",
    "petit-palais-musee-des-beaux-arts-de-la-ville-de-paris": "petit palais",
    "musee-d-art-moderne-de-la-ville-de-paris": "musee d'art moderne",
    "palais-galliera-musee-de-la-mode-et-de-la-ville-de-paris": "palais galliera",
    "musee-bourdelle": "musee bourdelle",
    "musee-de-la-liberation-de-paris-musee-du-general-leclerc-mus": "musee de la liberation",
    "musee-cognacq-jay-musee-du-xviiie-siecle-de-la-ville-de-pari": "cognacq-jay",
    "musee-cernuschi-musee-des-arts-de-l-asie-de-la-ville-de-pari": "cernuschi",
    "musee-zadkine": "zadkine",
    "maison-de-balzac": "balzac",
    "musee-de-la-vie-romantique": "vie romantique",
    "crypte-archeologique-de-l-ile-de-la-cite": "crypte",
}


def _norm(texte: str) -> str:
    sans = unicodedata.normalize("NFKD", texte.replace("’", "'")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sans.lower()).strip()


def convient(lieu) -> bool:
    return lieu["id"] in MUSEES


def source(lieu) -> str:
    return SOURCE


def _date(zone) -> str | None:
    if zone is None:
        return None
    morceaux = " ".join(h.texte(s) for s in zone.css(".date"))
    m = re.fullmatch(r"(\d{1,2}) (\d{1,2})/(\d{2})", morceaux.strip())
    if not m:
        return None
    try:
        return date(2000 + int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def toutes(page_html: str, url_page: str, aujourdhui: date) -> list[tuple[str, ExpoBrute]]:
    """(nom du musée normalisé, exposition) pour chaque carte du portail."""
    sortie, vus = [], set()
    for carte in h.lire(page_html).css("article.node--type-exposition"):
        lien = carte.css_first("a[href*='/exposition/']")
        musee = carte.css_first(".nom-musee")
        titre = carte.css_first(".description .title")
        if lien is None or musee is None or titre is None:
            continue
        url = h.absolu(url_page, lien.attributes.get("href"))
        if not url or url in vus:
            continue
        vus.add(url)
        debut, fin = _date(carte.css_first(".date-debut-evenement")), _date(carte.css_first(".date-fin-evenement"))
        if not (debut or fin) or (fin and fin < aujourdhui.isoformat()):
            continue
        sous_titre = carte.css_first(".field--name-field-sous-titre")
        e = ExpoBrute(titre=h.texte(titre), url=url, date_debut=debut, date_fin=fin, image_url=_image(carte, url_page),
                      description=h.texte(sous_titre) or None)
        e.provenance = {"titre": "carte", "url": "carte", "date_debut": "texte_fr", "date_fin": "texte_fr"}
        if e.image_url:
            e.provenance["image_url"] = "carte"
        if e.description:
            e.provenance["description"] = "carte"
        sortie.append((_norm(h.texte(musee)), e))
    return sortie


def extraire_pour(lieu_id: str, page_html: str, url_page: str, aujourdhui: date) -> list[ExpoBrute]:
    cle = MUSEES[lieu_id]
    return [e for musee, e in toutes(page_html, url_page, aujourdhui) if cle in musee]
