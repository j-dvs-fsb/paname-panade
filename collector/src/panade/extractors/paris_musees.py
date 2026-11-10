"""Extracteur du réseau Paris Musées (Drupal) : un seul pour les 12 lieux.

Les sites partagent un gabarit mais pas une page : on a observé trois formes le
2026-10-29, toutes gérées ici.
  1. Carnavalet : cartes `.card` avec des <time datetime> (début, fin).
  2. Petit Palais : cartes `.card` avec les dates écrites en français, sans <time>.
  3. Bourdelle : la liste « en cours » redirige vers l'unique exposition, une fiche.

Règles qui ne se discutent pas :
  - la gratuité n'est jamais lue : badges « Gratuit » et mentions « Entrée gratuite »
    sont ignorés, et retirés de la description (invariant 1) ;
  - une date absente reste absente. Les dateStart / dateEnd du JSON embarqué sur les
    fiches sont des horaires de nocturne, pas les dates de l'exposition.
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit

from panade import html as h
from panade.dates_fr import analyser
from panade.extractors import ExpoBrute

ACTIVITES = {
    "visite", "visites", "atelier", "ateliers", "evenement", "evenements", "événement",
    "événements", "promenade", "spectacle", "conference", "conférence", "concert",
    "rencontre", "projection", "stage", "jeune public", "famille",
}
PAGES_DE_LISTE = {
    "expositions", "exposition", "expositions-en-cours", "exposition-en-cours", "expositions-passees",
    "expositions-venir", "prochaines-expositions", "expositions-hors-les-murs",
}
TITRES = ".card-title, .card-title-o, p.title"
LIENS = "a.card-link, .card-title a, .card-title-o a, p.title a, a.stretched-link"
CATEGORIES = ".meta-category, .card-category, p.category"
DATES = ".card-metas, .card-date, .date, .time, time"
SOUS_TITRES = ".card-subtitle, .card-text, p.author"
MENTION_TARIF = re.compile(r"gratuit|payant|tarif|prix|entr[ée]e|billet|€|r[ée]duit", re.I)


def convient(lieu) -> bool:
    """Une page d'accueil n'est pas une page d'expositions : `discover` doit d'abord trouver la bonne."""
    return (lieu["famille_id"] == "paris_musees" and bool(lieu["expos_url"])
            and urlsplit(lieu["expos_url"]).path not in ("", "/"))


def extraire(page_html: str, url_page: str, aujourdhui: date) -> list[ExpoBrute]:
    arbre = h.lire(page_html)
    zone = arbre.css_first("main") or arbre.body
    if zone is None:
        return []
    if _est_une_fiche(url_page):
        # Les cartes d'une fiche sont l'agenda de l'expo (ateliers, visites), pas des expositions.
        fiche = _fiche(arbre, url_page, aujourdhui)
        return [fiche] if fiche and not _passee(fiche, aujourdhui) else []
    expos, vus = [], set()
    for carte in zone.css(".card, .showcase"):
        expo = _carte(carte, url_page, aujourdhui)
        if expo and expo.url not in vus and not _passee(expo, aujourdhui):
            vus.add(expo.url)
            expos.append(expo)
    return expos


def _est_une_fiche(url_page: str) -> bool:
    chemin = url_page.split("?")[0].rstrip("/")
    return "exposition" in chemin.lower() and chemin.rsplit("/", 1)[-1] not in PAGES_DE_LISTE


def _passee(expo: ExpoBrute, aujourdhui: date) -> bool:
    return bool(expo.date_fin and expo.date_fin < aujourdhui.isoformat())


def _carte(carte, url_page: str, aujourdhui: date) -> ExpoBrute | None:
    titre_noeud = carte.css_first(TITRES)
    lien_noeud = carte.css_first(LIENS) or carte.css_first("a[href]")
    if titre_noeud is None or lien_noeud is None:
        return None
    titre = h.texte(titre_noeud)
    url = h.absolu(url_page, lien_noeud.attributes.get("href"))
    if not titre or not url:
        return None
    if re.search(r"/(agenda|evenements?[-a-z]*|activites?|visites?)(/|$)", url.split("?")[0], re.I):
        return None     # lien d'agenda : une activité, pas une exposition

    categories = [t.strip().lower() for n in carte.css(CATEGORIES) for t in h.texte(n).split("•")]
    if any(c in ACTIVITES for c in categories):
        return None

    debut, fin, provenance_dates = _dates(carte, aujourdhui)
    if debut is None and fin is None:
        return None     # une carte sans date n'est pas une exposition datée (menu, rubrique, appel à action)

    expo = ExpoBrute(titre=titre, url=url, date_debut=debut, date_fin=fin,
                     image_url=_image(carte, url_page), description=_description(carte))
    expo.provenance = {"titre": "carte", "url": "carte", "date_debut": provenance_dates, "date_fin": provenance_dates}
    if any("accrochage" in c for c in categories):
        # Un accrochage se tient souvent dans les collections permanentes (gratuites), parfois non :
        # la portée détermine la gratuité, on ne la devine pas.
        expo.provenance["portee"] = "incertaine"
    if expo.image_url:
        expo.provenance["image_url"] = "carte"
    if expo.description:
        expo.provenance["description"] = "carte"
    return expo


def _dates(noeud, aujourdhui: date) -> tuple[str | None, str | None, str]:
    temps = [t.attributes.get("datetime", "")[:10] for t in noeud.css("time[datetime]")]
    temps = [t for t in temps if re.fullmatch(r"\d{4}-\d\d-\d\d", t)]
    if temps:
        return temps[0], (temps[-1] if len(temps) > 1 else None), "time"
    for zone in [*noeud.css(DATES), noeud]:
        periode = analyser(h.texte(zone), aujourdhui)
        if periode:
            return periode.debut, periode.fin, "texte_fr_annee_deduite" if periode.annee_deduite else "texte_fr"
    return None, None, "absente"


def _image(noeud, base: str) -> str | None:
    """Image de la carte. Une image « différée » n'a souvent qu'un faux src : on lit aussi data-src."""
    for img in noeud.css("img"):
        for attribut in ("src", "data-src", "data-lazy-src"):
            valeur = img.attributes.get(attribut) or ""
            if valeur and not valeur.startswith("data:") and not re.search(r"(rien|blank|pixel|placeholder)\.", valeur):
                return h.absolu(base, valeur)
    source = noeud.css_first("source[srcset]")
    if source:
        return h.absolu(base, source.attributes["srcset"].split()[0])
    return None


def _description(noeud) -> str | None:
    morceaux = []
    for n in noeud.css(SOUS_TITRES):
        for segment in h.texte(n).split("•"):
            segment = segment.strip()
            if segment and not MENTION_TARIF.search(segment):   # invariant 1 : jamais de tarif repris de la page
                morceaux.append(segment)
    return " - ".join(dict.fromkeys(morceaux)) or None


def _fiche(arbre, url_page: str, aujourdhui: date) -> ExpoBrute | None:
    """La page est elle-même l'exposition (liste « en cours » redirigée vers l'unique expo)."""
    titre_noeud = arbre.css_first("h1")
    og = {m.attributes.get("property"): m.attributes.get("content") for m in arbre.css("meta[property^='og:']")}
    titre = h.texte(titre_noeud) or (og.get("og:title") or "").strip()
    if not titre:
        return None
    debut, fin, provenance_dates = _dates_fiche(arbre)
    expo = ExpoBrute(titre=titre, url=h.absolu(url_page, og.get("og:url")) or url_page,
                     image_url=h.absolu(url_page, og.get("og:image")),
                     date_debut=debut, date_fin=fin, description=_sans_tarif(og.get("og:description")))
    expo.provenance = {"titre": "fiche", "url": "fiche", "date_debut": provenance_dates, "date_fin": provenance_dates}
    if expo.image_url:
        expo.provenance["image_url"] = "og:image"
    if expo.description:
        expo.provenance["description"] = "og:description"
    return expo


def _dates_fiche(arbre) -> tuple[str | None, str | None, str]:
    """Sur une fiche, seules comptent les balises <time> hors des cartes d'agenda.

    Le texte libre d'une fiche cite des nocturnes, des ateliers, des dates de colloque :
    y lire « la » date de l'exposition reviendrait à la deviner.
    """
    def dans_une_carte(noeud) -> bool:
        parent = noeud.parent
        while parent is not None:
            if "card" in (parent.attributes.get("class") or "").split():
                return True
            parent = parent.parent
        return False

    temps = [t.attributes.get("datetime", "")[:10] for t in arbre.css("time[datetime]") if not dans_une_carte(t)]
    temps = [t for t in temps if re.fullmatch(r"\d{4}-\d\d-\d\d", t)]
    if temps:
        return temps[0], (temps[-1] if len(temps) > 1 else None), "time"
    return None, None, "absente"


def _sans_tarif(texte: str | None) -> str | None:
    if not texte:
        return None
    segments = [s.strip() for s in re.split(r"[•\n]", texte) if s.strip() and not MENTION_TARIF.search(s)]
    return " ".join(segments) or None
