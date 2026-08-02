"""Détecte et fusionne les expositions en doublon (toutes sources confondues).

Doublon = même nom (normalisé) + même musée (ou même lieu si pas de musée) +
même date de début. On garde une entrée « pivot » (priorité : avis/favoris >
publiée > description la plus riche > plus petit id) et on lui rattache les
favoris/visites des autres avant de les supprimer.

Usage :
  python scripts/dedup.py            # dry-run : liste les doublons
  python scripts/dedup.py --commit   # fusionne
"""
import sys
import os
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from slugify import slugify

from paname import create_app
from paname.extensions import db
from paname.models import Exposition, Favorite, Visit


def _key(e):
    base = (slugify(e.title or ""), e.museum_id, e.date_start)
    return base + (slugify(e.venue_name or ""),) if e.museum_id is None else base


def _rank(e):
    """Plus c'est grand, plus l'entrée est prioritaire pour être conservée."""
    user_data = len(e.favorites) + len(e.visits)
    return (user_data, 1 if e.status == "published" else 0, len(e.description or ""), -e.id)


def _merge(keeper, loser):
    """Rattache favoris/visites du loser au keeper, puis supprime le loser."""
    for fav in list(loser.favorites):
        if Favorite.query.filter_by(user_id=fav.user_id, exposition_id=keeper.id).first():
            db.session.delete(fav)
        else:
            fav.exposition_id = keeper.id
    for visit in list(loser.visits):
        if Visit.query.filter_by(user_id=visit.user_id, exposition_id=keeper.id).first():
            db.session.delete(visit)
        else:
            visit.exposition_id = keeper.id
    db.session.delete(loser)


def run(commit=False):
    app = create_app()
    with app.app_context():
        groups = defaultdict(list)
        for e in Exposition.query.all():
            groups[_key(e)].append(e)
        dups = {k: v for k, v in groups.items() if len(v) > 1}

        if not dups:
            print("✓ Aucun doublon (nom + musée/lieu + date).")
            return

        merged = 0
        for group in dups.values():
            group.sort(key=_rank, reverse=True)
            keeper, losers = group[0], group[1:]
            print(f"\n• {keeper.title!r}  (musée={keeper.museum_id}, début={keeper.date_start})")
            print(f"    GARDE  id={keeper.id} [{keeper.source}/{keeper.status}]")
            for lo in losers:
                print(f"    fusion id={lo.id} [{lo.source}/{lo.status}]")
                if commit:
                    _merge(keeper, lo)
                merged += 1

        if commit:
            db.session.commit()
            print(f"\n✓ {merged} doublon(s) fusionné(s).")
        else:
            print(f"\n(dry-run - {merged} entrée(s) à fusionner. Relance avec --commit.)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    run(commit=args.commit)
