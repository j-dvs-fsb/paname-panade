"""Récupère le logo de chaque musée (depuis son site) et le stocke en base.

Sert d'image aux « collections permanentes » (qui n'ont pas de visuel propre).

Usage :
  python scripts/logos.py                 # dry-run
  python scripts/logos.py --commit        # écrit logo_url
  python scripts/logos.py --commit --force  # rafraîchit même si déjà renseigné
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from paname import create_app
from paname.extensions import db
from paname.models import Museum
from scripts.scrapers import base


def run(commit=False, force=False):
    app = create_app()
    with app.app_context():
        found = missing = 0
        for m in Museum.query.order_by(Museum.name).all():
            if not m.website:
                continue
            if m.logo_url and not force:
                continue
            logo = base.find_logo(m.website)
            if logo:
                found += 1
                print(f"  ✓ {m.name[:45]:45} {logo[:70]}")
                if commit:
                    m.logo_url = logo
            else:
                missing += 1
                print(f"  ✗ {m.name[:45]:45} (pas de logo trouvé)")
        if commit:
            db.session.commit()
            print(f"\n✓ {found} logo(s) enregistré(s), {missing} introuvable(s).")
        else:
            print(f"\n(dry-run - {found} trouvé(s), {missing} introuvable(s). --commit pour écrire.)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--force", action="store_true", help="rafraîchir les logos existants")
    args = parser.parse_args()
    run(commit=args.commit, force=args.force)
