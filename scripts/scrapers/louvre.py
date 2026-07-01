"""Scraper du musée du Louvre.

La page « expositions » est un site Next.js : les expositions sont des objets
`{"type": "Exposition", ...}` dans le JSON __NEXT_DATA__. Pas de HTML à parser.

On ne garde que les expositions EN COURS et physiquement au Louvre (on exclut
les expositions passées, à venir, et « Le Louvre ailleurs » = hors les murs).
Pour chaque expo retenue, on suit sa fiche pour récupérer la description longue
(≈ 1 requête de plus par expo, soit une poignée).
"""
import re

from . import base

SITE = "https://www.louvre.fr"
IMG_HOST = "https://api-www.louvre.fr"   # les médias sont servis par l'hôte d'API


def _image(img):
    """URL d'image : variante paysage 3:2 optimisée (webp), sinon l'original.

    Les images du Louvre sont servies par api-www.louvre.fr (pas www), et le
    JSON fournit des dérivés prêts à l'emploi dans `hashes`.
    """
    if not isinstance(img, dict):
        return None
    hashes = img.get("hashes") or {}
    for w in (1200, 1080, 828, 750, 640):
        url = hashes.get(f"w{w}_3_2")
        if url:
            return url
    path = img.get("fallback") or img.get("path")
    return base.absolute(IMG_HOST, path) if path else None


def _walk(node, wanted_type=None, key=None):
    """Parcourt récursivement et rend les dicts ayant type==wanted_type,
    ou les valeurs str trouvées à la clé `key`."""
    if isinstance(node, dict):
        if wanted_type and node.get("type") == wanted_type:
            yield node
        for k, v in node.items():
            if key and k == key and isinstance(v, str):
                yield v
            yield from _walk(v, wanted_type, key)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, wanted_type, key)


def _is_current_onsite(tags):
    low = [t.lower() for t in tags]
    if not any(t.startswith("en cours") for t in low):
        return False
    if any("ailleurs" in t for t in low):   # « Le Louvre ailleurs » = hors les murs
        return False
    return True


def _fetch_description(url):
    """Récupère la description longue depuis la fiche détaillée."""
    from paname.utils import html_to_text
    try:
        data = base.next_data(base.fetch(url))
    except Exception:
        return None
    if not data:
        return None
    page = data.get("props", {}).get("initialState", {}).get("Page", {})
    # Tous les blocs riches sont des `...html`. On prend le plus long « vrai »
    # paragraphe (sans gabarits {{ ... }} de crédits / infos pratiques).
    candidates = []
    for raw in _walk(page, key="html"):
        if "{{" in raw:
            continue
        clean = re.sub(r"<\?xml[^>]*\?>", "", raw)
        txt = html_to_text(clean)
        if txt:
            candidates.append(txt)
    return max(candidates, key=len) if candidates else None


def scrape(museum):
    data = base.next_data(base.fetch(museum.expos_url))
    if not data:
        return []

    items = []
    for e in _walk(data, wanted_type="Exposition"):
        title = (e.get("title") or "").strip()
        link = e.get("link") or {}
        url_path = link.get("url") if isinstance(link, dict) else link
        if not title or not url_path:
            continue

        tags = [t.get("label", "").strip() for t in e.get("tags", []) if isinstance(t, dict)]
        if not _is_current_onsite(tags):
            continue

        img = e.get("image") or {}
        date_start, date_end = base.parse_french_date(e.get("date"))
        url = base.absolute(SITE, url_path)
        subtitle = (e.get("subtitle") or "").strip() or None

        items.append({
            "title": title,
            "subtitle": subtitle,
            "description": _fetch_description(url) or subtitle,
            "url": url,
            "image_url": _image(img),
            "date_start": date_start,
            "date_end": date_end,
            "tags": tags,
            "ext_key": url_path.rstrip("/").rsplit("/", 1)[-1],
        })
    return items
