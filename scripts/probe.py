"""Sonde un site pour savoir quelle stratégie de scraping utiliser.

En 2 secondes : présence de __NEXT_DATA__, JSON-LD, API WordPress/Drupal,
plateforme Paris Musées, et liens vers des fiches d'exposition.

Usage :  python scripts/probe.py <url> [<url> ...]
"""
import sys
import os
import re

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.scrapers import base


def probe(url):
    try:
        html = base.fetch(url)
    except Exception as e:
        print(f"✗ {url} : {e}")
        return

    has_next = "__NEXT_DATA__" in html
    ld = base.json_ld(html)
    ld_types = sorted({str(o.get("@type")) for o in ld if isinstance(o, dict)})
    has_wp = "wp-json" in html or "wp-content" in html
    has_drupal = bool(re.search(r"drupal", html, re.I))
    is_pm = "parismusees" in html
    expo_links = sorted(set(re.findall(r'href="([^"]*/expositions?/[^"#?]+)"', html)))

    # Stratégie recommandée
    if has_next:
        strat = "Next.js → base.next_data() + parcours JSON"
    elif ld_types and any("Event" in t or "Exhibition" in t for t in ld_types):
        strat = "JSON-LD → base.json_ld()"
    elif is_pm:
        strat = "Paris Musées (Drupal) → scraper paris_musees"
    elif has_wp:
        strat = "WordPress → API /wp-json/wp/v2/…"
    elif has_drupal:
        strat = "Drupal → CSS sélecteurs (BeautifulSoup)"
    else:
        strat = "HTML brut → CSS sélecteurs (BeautifulSoup)"

    print(f"\n● {url}  ({len(html)//1024} Ko)")
    print(f"  __NEXT_DATA__ : {'oui' if has_next else 'non'}")
    print(f"  JSON-LD       : {('oui ' + str(ld_types)) if ld else 'non'}")
    print(f"  WordPress     : {'oui' if has_wp else 'non'}   Drupal : {'oui' if has_drupal else 'non'}"
          f"   Paris Musées : {'oui' if is_pm else 'non'}")
    print(f"  liens fiches  : {len(expo_links)}" + (f"  ex: {expo_links[0]}" if expo_links else ""))
    print(f"  → STRATÉGIE   : {strat}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python scripts/probe.py <url> [<url> ...]")
        sys.exit(1)
    for u in sys.argv[1:]:
        probe(u)
