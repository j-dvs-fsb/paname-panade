"""Scrape les expositions des sites de musées (sources hors « Que Faire à Paris »).

Chaque musée ayant un `expos_url` et un scraper enregistré est traité. Les
expositions trouvées sont insérées en `status="draft"` (file de validation admin),
rattachées au musée, avec source="scraping".

Usage :
  python scripts/scrape.py                 # dry-run : affiche, n'écrit rien
  python scripts/scrape.py --commit        # écrit en base (brouillons)
  python scripts/scrape.py --museum musee-du-louvre --commit
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from slugify import slugify

from paname import create_app
from paname.extensions import db
from paname.models import Museum, Exposition
from paname.utils import find_duplicate_expo
from scripts.scrapers import SCRAPERS


def _unique_slug(base, ext_id):
    base = slugify(base)[:200] or "expo"
    slug, n = base, 2
    while True:
        clash = Exposition.query.filter(
            Exposition.slug == slug, Exposition.external_id != ext_id
        ).first()
        if not clash:
            return slug
        slug, n = f"{base}-{n}", n + 1


def upsert(museum, item):
    """Crée/maj une Exposition à partir d'un dict normalisé. Renvoie 'created'|'updated'."""
    ext_id = f"scrap:{museum.slug}:{item['ext_key']}"
    expo = Exposition.query.filter_by(external_id=ext_id).first()
    if not expo:   # déjà présente via une autre source (ex. Que Faire à Paris) ?
        expo = find_duplicate_expo(item["title"], museum.id, museum.name,
                                   item.get("date_start"))
    state = "updated"
    if not expo:
        expo = Exposition(
            external_id=ext_id,
            slug=_unique_slug(item["title"], ext_id),
            source="scraping",
            status="draft",          # passe par la validation admin
        )
        db.session.add(expo)
        state = "created"

    expo.title = item["title"]
    expo.description = item.get("description")
    expo.url = item.get("url")
    expo.image_url = item.get("image_url")
    expo.date_start = item.get("date_start")
    expo.date_end = item.get("date_end")
    expo.museum_id = museum.id
    expo.venue_name = museum.name
    expo.address = museum.address
    # Tarif de l'expo déduit des conditions de gratuité du musée.
    fa = museum.free_access_list
    if "gratuit_tous" in fa or "permanent" in fa:
        expo.price_category = "gratuit_tous"
    elif "gratuit_26" in fa:
        expo.price_category = "gratuit_26"
    else:
        expo.price_category = "gratuit_tous"
    return state


def run(only=None, commit=False):
    app = create_app()
    with app.app_context():
        targets = []
        for slug, fn in SCRAPERS.items():
            if only and slug != only:
                continue
            museum = Museum.query.filter_by(slug=slug).first()
            if not museum:
                print(f"⚠ Musée introuvable en base : {slug}")
                continue
            if not museum.expos_url:
                print(f"⚠ Pas d'expos_url renseignée pour {museum.name} — ignoré.")
                continue
            targets.append((museum, fn))

        if not targets:
            print("Aucun musée à scraper.")
            return

        for museum, fn in targets:
            print(f"\n→ {museum.name}  ({museum.expos_url})")
            try:
                items = fn(museum)
            except Exception as e:
                print(f"  ✗ Erreur scraping : {e}")
                continue
            print(f"  {len(items)} exposition(s) trouvée(s).")

            created = updated = 0
            for it in items:
                period = " → ".join(filter(None, [
                    it["date_start"].strftime("%d/%m/%Y") if it.get("date_start") else None,
                    it["date_end"].strftime("%d/%m/%Y") if it.get("date_end") else None,
                ])) or "dates ?"
                tags = ", ".join(it.get("tags", []))
                print(f"   • {it['title']}  [{period}]  {('— ' + tags) if tags else ''}")
                if commit:
                    state = upsert(museum, it)
                    created += state == "created"
                    updated += state == "updated"

            if commit:
                db.session.commit()
                print(f"  ✓ {created} créées (draft), {updated} mises à jour.")

        if not commit:
            print("\n(dry-run — rien n'a été écrit. Relance avec --commit pour enregistrer.)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--museum", help="slug d'un seul musée à scraper")
    parser.add_argument("--commit", action="store_true", help="écrire en base")
    args = parser.parse_args()
    run(only=args.museum, commit=args.commit)
