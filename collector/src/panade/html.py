"""Petits outils HTML partagés par `probe`, `discover` et les extracteurs."""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser

_INUTILE = "script, style, svg, noscript, iframe, template, link[rel=stylesheet], link[rel=preload], " \
           "link[rel=modulepreload], link[rel=prefetch], link[rel=dns-prefetch], link[rel=preconnect]"


def lire(html: str) -> LexborHTMLParser:
    return LexborHTMLParser(html)


def reduire(html: str) -> str:
    """Version compacte d'une page, pour les fixtures et pour la découverte.

    Une page de musée pèse souvent 300 000 caractères pour 2 000 utiles : on retire
    scripts, styles, SVG, commentaires et URI de données, en gardant le JSON-LD.
    """
    arbre = LexborHTMLParser(html)
    for noeud in arbre.css(_INUTILE):
        if noeud.tag == "script" and (noeud.attributes.get("type") or "").lower() == "application/ld+json":
            continue
        noeud.decompose()
    sortie = arbre.html or ""
    sortie = re.sub(r"<!--.*?-->", "", sortie, flags=re.S)
    sortie = re.sub(r"data:[^\"')\s]{40,}", "data:", sortie)
    sortie = re.sub(r">\s+<", "><", sortie)
    return re.sub(r"\s*\n\s*", "\n", sortie).strip() + "\n"


def absolu(base: str, lien: str | None) -> str | None:
    """Lien absolu http(s), ou None. Évite les `javascript:`, `mailto:` et les liens vides."""
    if not lien or not lien.strip():
        return None
    complet = urljoin(base, lien.strip())
    return complet if re.match(r"https?://\S+$", complet) else None


def texte(noeud) -> str:
    return re.sub(r"\s+", " ", noeud.text(separator=" ")).strip() if noeud is not None else ""


def _parcourir(objet):
    if isinstance(objet, dict):
        yield objet
        for valeur in objet.values():
            yield from _parcourir(valeur)
    elif isinstance(objet, list):
        for valeur in objet:
            yield from _parcourir(valeur)


def jsonld(arbre: LexborHTMLParser) -> list[dict]:
    """Tous les objets JSON-LD de la page, à plat. Un bloc illisible est ignoré."""
    objets: list[dict] = []
    for bloc in arbre.css('script[type="application/ld+json"]'):
        try:
            objets.extend(_parcourir(json.loads(bloc.text())))
        except ValueError:
            continue
    return objets


def types_jsonld(objet: dict) -> list[str]:
    t = objet.get("@type")
    return [str(x) for x in t] if isinstance(t, list) else [str(t)] if t else []
