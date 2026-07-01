"""Briques communes aux scrapers de sites de musées.

Chaque scraper reçoit un objet Museum (avec son `expos_url`) et renvoie une
liste de dicts normalisés, prêts à devenir des Exposition. Les champs reconnus :

    title, subtitle, description, url, image_url,
    date_start (date|None), date_end (date|None),
    ext_key (identifiant stable côté source -> external_id), tags (list[str])

On privilégie les données structurées (JSON-LD, __NEXT_DATA__) avant de parser
le HTML brut. Ici, pas besoin de BeautifulSoup : tout passe par requests + stdlib.
"""
import json
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}
_DATE_RE = re.compile(
    r"(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\.?\s*(\d{4})?",
    re.IGNORECASE,
)


def fetch(url, timeout=30):
    """GET avec un User-Agent de navigateur. Lève en cas d'erreur HTTP."""
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def next_data(html):
    """Extrait le JSON __NEXT_DATA__ d'une page Next.js (None si absent)."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def soup(html):
    """Parse le HTML avec BeautifulSoup (parser stdlib, pas de dépendance C)."""
    return BeautifulSoup(html, "html.parser")


def json_ld(html):
    """Renvoie la liste des objets JSON-LD (<script type=application/ld+json>)."""
    out = []
    for m in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                        html, re.S):
        try:
            data = json.loads(m)
        except json.JSONDecodeError:
            continue
        out.extend(data if isinstance(data, list) else [data])
    return out


def longest_paragraph(html):
    """Texte du plus long <p> d'une page (heuristique de description, best-effort)."""
    texts = [p.get_text(" ", strip=True) for p in soup(html).find_all("p")]
    return max(texts, key=len) if texts else None


def _is_image_url(url):
    """Vérifie qu'une URL renvoie bien une image (200 + content-type image/*)."""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10, stream=True)
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image")
        r.close()
        return ok
    except requests.RequestException:
        return False


def find_logo(website):
    """Logo d'un site : apple-touch-icon / plus grande icône / og:image, en
    vérifiant que le fichier existe vraiment ; sinon service favicon (fiable).
    Renvoie une URL absolue (toujours une image) ou None."""
    if not website:
        return None
    from urllib.parse import urlsplit
    site = _site_base(website)

    candidates = []  # (priorité, href)
    try:
        page = soup(fetch(website))
    except Exception:
        page = None
    if page is not None:
        for link in page.select("link[rel]"):
            rel = " ".join(link.get("rel", [])).lower()
            href = link.get("href")
            if not href:
                continue
            if "apple-touch-icon" in rel:
                candidates.append((10000, href))
            elif "icon" in rel:
                m = re.search(r"(\d+)x\d+", link.get("sizes", ""))
                candidates.append((int(m.group(1)) if m else 1, href))
        og = page.select_one('meta[property="og:image"]')
        if og and og.get("content"):
            candidates.append((5, og["content"]))

    candidates.sort(reverse=True)
    for _, href in candidates:
        url = absolute(site, href)
        if _is_image_url(url):
            return url

    # Repli : service favicon Google (renvoie toujours une icône PNG).
    netloc = urlsplit(website).netloc
    return f"https://www.google.com/s2/favicons?domain={netloc}&sz=128" if netloc else None


def _site_base(url):
    from urllib.parse import urlsplit
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def absolute(base, path):
    """Transforme un chemin relatif en URL absolue."""
    if not path:
        return None
    if path.startswith("http"):
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")


def parse_french_date(text):
    """« 15 avril – 20 juillet 2026 » -> (date(2026,4,15), date(2026,7,20)).

    Gère « jusqu'au … » (fin seule) et « à partir du … » (début seul).
    Renvoie (date_start, date_end), l'un ou l'autre pouvant être None.
    """
    if not text:
        return None, None
    low = text.lower()
    matches = _DATE_RE.findall(text)
    if not matches:
        return None, None

    def to_date(day, month, year):
        return date(int(year), _MONTHS[month.lower()], int(day))

    # Propage l'année : si une date n'a pas d'année, on prend la suivante connue.
    year = next((y for _, _, y in matches if y), None)
    if not year:
        return None, None
    parsed = [to_date(d, m, (y or year)) for d, m, y in matches]

    if "jusqu" in low or "avant" in low:
        return None, parsed[-1]
    if "partir" in low or "depuis" in low or "dès" in low:
        return parsed[0], None
    if len(parsed) == 1:
        return parsed[0], None
    return parsed[0], parsed[-1]
