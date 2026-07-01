"""Scraper générique de la plateforme « Paris Musées » (Drupal).

Couvre les musées de la Ville de Paris : Carnavalet, Petit Palais, Musée d'Art
Moderne, Cognacq-Jay, Zadkine, Bourdelle, Cernuschi, Galliera, Maison de Victor
Hugo, Maison de Balzac, Vie romantique…

La plateforme existe en DEUX générations de thème ; on gère les deux :
  - ancien : cartes `.showcase` + `span.date-display-start[content]`
  - récent : cartes `.card` (a.card-link) + `<time datetime="…">`

Le `expos_url` de chaque musée (en base, éditable dans l'admin) pointe vers SA
page d'expositions. Les expositions passées (date de fin dépassée) sont ignorées.
"""
from datetime import date
from urllib.parse import urlsplit

from . import base


# Catégories qui ne sont PAS des expositions (agenda d'activités).
_ACTIVITY_CATS = {
    "visite", "visites", "atelier", "ateliers", "evenement", "evenements",
    "événement", "événements", "promenade", "spectacle", "conference", "conférence",
}


def _site_base(url):
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def _is_activity(tags):
    return any(t.strip().lower() in _ACTIVITY_CATS for t in tags)


def _iso(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _description(url):
    try:
        return base.longest_paragraph(base.fetch(url))
    except Exception:
        return None


def _parse_showcase(card):
    """Ancien thème : .showcase."""
    a = card.select_one("p.title a") or card.select_one("a[href]")
    if not a:
        return None
    img = card.select_one("figure img")
    sub = card.select_one("p.author")
    return {
        "href": a.get("href", ""),
        "title": a.get_text(" ", strip=True),
        "subtitle": sub.get_text(" ", strip=True) if sub else None,
        "image": img.get("src") if img else None,
        "date_start": _iso((card.select_one("span.date-display-start") or {}).get("content")),
        "date_end": _iso((card.select_one("span.date-display-end") or {}).get("content")),
        "tags": [c.get_text(" ", strip=True) for c in card.select("p.category")],
    }


def _parse_card(card):
    """Thème récent : .card / a.card-link."""
    a = card.select_one("a.card-link") or card.select_one("a[href]")
    title = card.select_one(".card-title")
    if not a or not title:
        return None
    img = card.select_one(".card-figure img")
    sub = card.select_one(".card-subtitle")
    cat = card.select_one(".meta-category")
    times = card.select("time[datetime]")
    return {
        "href": a.get("href", ""),
        "title": title.get_text(" ", strip=True),
        "subtitle": sub.get_text(" ", strip=True) if sub else None,
        "image": img.get("src") if img else None,
        "date_start": _iso(times[0]["datetime"]) if times else None,
        "date_end": _iso(times[-1]["datetime"]) if len(times) > 1 else None,
        "tags": [cat.get_text(" ", strip=True)] if cat else [],
    }


def scrape(museum):
    site = _site_base(museum.expos_url)
    page = base.soup(base.fetch(museum.expos_url))
    today = date.today()

    cards = page.select(".showcase")
    parse = _parse_showcase
    if not cards:
        cards = page.select(".card")
        parse = _parse_card

    items, seen = [], set()
    for card in cards:
        raw = parse(card)
        if not raw or not raw["href"] or not raw["title"]:
            continue
        # Une exposition a une date de début ; on écarte nav et activités d'agenda.
        if not raw["date_start"] or _is_activity(raw["tags"]):
            continue
        if raw["date_end"] and raw["date_end"] < today:   # passée -> on ignore
            continue
        if raw["href"] in seen:                            # cartes dupliquées
            continue
        seen.add(raw["href"])

        url = base.absolute(site, raw["href"])
        items.append({
            "title": raw["title"],
            "subtitle": raw["subtitle"],
            "description": _description(url) or raw["subtitle"],
            "url": url,
            "image_url": base.absolute(site, raw["image"]),
            "date_start": raw["date_start"],
            "date_end": raw["date_end"],
            "tags": [t for t in raw["tags"] if t],
            "ext_key": raw["href"].rstrip("/").rsplit("/", 1)[-1],
        })
    return items
