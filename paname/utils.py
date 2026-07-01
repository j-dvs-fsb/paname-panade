"""Petits utilitaires partagés (nettoyage de texte, identifiants)."""
import re
from html import unescape
from html.parser import HTMLParser

# Balises qui introduisent un saut de ligne / paragraphe à l'affichage.
_BLOCK_TAGS = {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}


class _TextExtractor(HTMLParser):
    """Convertit un fragment HTML en texte brut en préservant les paragraphes."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self):
        raw = "".join(self.parts)
        raw = unescape(raw).replace("\xa0", " ")
        # Normalise les espaces intra-ligne puis compacte les sauts multiples.
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw.split("\n")]
        out, blank = [], False
        for ln in lines:
            if ln:
                out.append(ln)
                blank = False
            elif not blank:
                out.append("")
                blank = True
        return "\n".join(out).strip()


def html_to_text(value):
    """Nettoie un champ qui peut contenir du HTML (descriptions QFAP).

    Renvoie un texte brut multi-lignes (paragraphes séparés par des sauts de
    ligne), sans balises ni entités HTML. Renvoie None si vide.
    """
    if not value:
        return None
    # Cas fréquent : pas de balise -> juste déséchapper les entités.
    if "<" not in value and "&" not in value:
        return value.strip() or None
    p = _TextExtractor()
    p.feed(value)
    return p.text() or None


def _norm(value):
    """Clé de comparaison insensible casse/accents/ponctuation."""
    from slugify import slugify
    return slugify(value or "")


def find_duplicate_expo(title, museum_id, venue_name=None, date_start=None, exclude_id=None):
    """Cherche une exposition équivalente, éventuellement d'une autre source.

    Règle de doublon : même nom (normalisé) + même musée (ou même lieu si pas de
    musée) + même date de début. La date évite de fusionner des sessions répétées
    d'un même événement (dates différentes = entrées distinctes).

    Renvoie l'Exposition existante ou None.
    """
    from .models import Exposition
    key = _norm(title)
    if not key:
        return None
    q = Exposition.query
    q = q.filter(Exposition.museum_id == museum_id) if museum_id is not None \
        else q.filter(Exposition.museum_id.is_(None))
    q = q.filter(Exposition.date_start.is_(None)) if date_start is None \
        else q.filter(Exposition.date_start == date_start)
    for e in q:
        if exclude_id and e.id == exclude_id:
            continue
        if _norm(e.title) != key:
            continue
        if museum_id is None and _norm(e.venue_name) != _norm(venue_name):
            continue
        return e
    return None


def next_local_museum_id(existing_ids):
    """Génère un identifiant local pour un musée absent de l'API IDF.

    Pattern volontairement distinct des identifiants museofile (« M#### ») :
    « LOC-0001 », « LOC-0002 »… `existing_ids` est un itérable de museofile_id
    déjà en base.
    """
    nums = [
        int(m.group(1))
        for x in existing_ids if x
        for m in [re.match(r"LOC-(\d+)$", x)] if m
    ]
    return f"LOC-{(max(nums) + 1) if nums else 1:04d}"
