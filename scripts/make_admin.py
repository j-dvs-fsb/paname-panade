"""Donne (ou retire) les droits admin à un utilisateur.

Usage :  python scripts/make_admin.py <email> [--off]
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from paname import create_app
from paname.extensions import db
from paname.models import User


def run(email, on=True):
    app = create_app()
    with app.app_context():
        user = User.query.filter_by(email=email.strip().lower()).first()
        if not user:
            print(f"✗ Aucun utilisateur avec l'email {email!r}.")
            return
        user.is_admin = on
        db.session.commit()
        print(f"✓ {email} : is_admin = {on}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("--off", action="store_true", help="retirer les droits admin")
    args = parser.parse_args()
    run(args.email, on=not args.off)
