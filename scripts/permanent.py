"""Génère une « exposition » pour les collections permanentes gratuites.

Les collections permanentes ne sont pas listées sur les pages « expositions »
des sites de musées : ce sont des attributs du musée (cf. Museum.free_access).
Pour qu'elles apparaissent quand même dans la liste des expos et soient prises
par les filtres de prix, on crée une entrée Exposition « pérenne » (sans date de
fin -> toujours en cours) par musée dont l'accès est gratuit.

Usage :
  python scripts/permanent.py            # dry-run
  python scripts/permanent.py --commit   # écrit en base
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from slugify import slugify

from paname import create_app
from paname.extensions import db
from paname.models import Museum, Exposition


def _price_for(free_access):
    """Tarif de la collection permanente selon les conditions de gratuité."""
    if "gratuit_tous" in free_access or "permanent" in free_access:
        return "gratuit_tous"
    if "gratuit_26" in free_access:
        return "gratuit_26"
    return None   # pas de gratuité connue -> on ne génère pas


def run(commit=False):
    app = create_app()
    with app.app_context():
        created = updated = skipped = 0
        for museum in Museum.query.order_by(Museum.name).all():
            price = _price_for(museum.free_access_list)
            if not price:
                skipped += 1
                continue

            ext_id = f"permanent:{museum.slug}"
            expo = Exposition.query.filter_by(external_id=ext_id).first()
            state = "maj"
            if not expo:
                expo = Exposition(
                    external_id=ext_id,
                    slug=slugify(f"collections-permanentes-{museum.slug}")[:200],
                    source="permanent",
                    status="published",
                )
                db.session.add(expo)
                state = "créée"
                created += 1
            else:
                updated += 1

            expo.title = f"Collections permanentes — {museum.name}"
            expo.description = museum.description
            expo.museum_id = museum.id
            expo.venue_name = museum.name
            expo.address = museum.address
            expo.lat = museum.lat
            expo.lon = museum.lon
            expo.image_url = museum.logo_url or museum.image_url
            expo.price_category = price
            expo.reservation = "non_necessaire"
            expo.date_start = None      # pérenne : toujours « en cours »
            expo.date_end = None
            print(f"   • [{state}] {expo.title}  ({price})")

        if commit:
            db.session.commit()
            print(f"\n✓ {created} créées, {updated} mises à jour, {skipped} musées sans gratuité connue.")
        else:
            db.session.rollback()
            print(f"\n(dry-run — {created} à créer, {updated} à mettre à jour, "
                  f"{skipped} ignorés. Relance avec --commit.)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    run(commit=args.commit)
