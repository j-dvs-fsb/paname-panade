"""Synchronise les expositions gratuites depuis l'API « Que Faire à Paris ? ».

Source : https://opendata.paris.fr — dataset `que-faire-a-paris-`
API Opendatasoft Explore v2.1, gratuite et sans clé.

Usage :  python scripts/sync_data.py [--limit N]

On filtre les événements gratuits dont la catégorie/tag évoque une exposition,
on les rattache à un musée existant si le lieu correspond, sinon on les garde
sans musée (l'adresse reste affichée sur la fiche).
"""
import sys
import os
import argparse
from datetime import datetime

import requests
from slugify import slugify

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from paname import create_app
from paname.extensions import db
from paname.models import Museum, Exposition
from paname.utils import html_to_text, find_duplicate_expo

API = "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/que-faire-a-paris-/records"
PAGE = 100


def parse_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S+00:00"):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
    return None


def fetch(limit):
    """Récupère les enregistrements gratuits, paginé."""
    records = []
    offset = 0
    # where : price_type gratuit ET tag "Expo" (vocabulaire qfap_tags de la Ville de Paris)
    where = 'price_type="gratuit" and qfap_tags like "Expo"'
    while len(records) < limit:
        params = {
            "where": where,
            "limit": min(PAGE, limit - len(records)),
            "offset": offset,
        }
        resp = requests.get(API, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break
        records.extend(results)
        offset += len(results)
        if offset >= data.get("total_count", 0):
            break
    return records


def map_reservation(access_type):
    """access_type QFAP -> clé réservation du modèle."""
    a = (access_type or "").strip().lower()
    if a.startswith("oblig"):
        return "obligatoire"
    if a.startswith("conseil"):
        return "conseillee"
    return "non_necessaire"


def clean_link(url):
    if not url:
        return None
    url = url.strip().rstrip("/")
    if not url:
        return None
    return url if url.startswith("http") else "https://" + url


def match_museum(rec):
    """Tente de rattacher l'expo à un musée connu via le nom du lieu."""
    place = (rec.get("address_name") or "").lower()
    if not place:
        return None
    for m in Museum.query.all():
        key = m.name.split("—")[0].split("(")[0].strip().lower()
        if key and (key in place or place in key):
            return m
    return None


def run(limit):
    app = create_app()
    with app.app_context():
        print(f"→ Requête API Que Faire à Paris (limit={limit})…")
        try:
            records = fetch(limit)
        except requests.RequestException as e:
            print(f"✗ Erreur réseau : {e}")
            return
        print(f"  {len(records)} enregistrement(s) reçu(s).")

        created = updated = 0
        for rec in records:
            ext_id = str(rec.get("id") or rec.get("recordid") or "")
            title = rec.get("title")
            if not title:
                continue

            # Données nécessaires au rapprochement (musée, lieu, date de début).
            museum = match_museum(rec)
            museum_id = museum.id if museum else None
            venue = rec.get("address_name")
            date_start = parse_date(rec.get("date_start"))

            expo = None
            if ext_id:
                expo = Exposition.query.filter_by(external_id=ext_id).first()
            if not expo:   # pas trouvée par id : doublon d'une autre source ?
                expo = find_duplicate_expo(title, museum_id, venue, date_start)
            if not expo:
                base = slugify(title)[:200] or "expo"
                slug = base
                n = 2
                while Exposition.query.filter(Exposition.slug == slug,
                                              Exposition.external_id != ext_id).first():
                    slug = f"{base}-{n}"
                    n += 1
                expo = Exposition(slug=slug, external_id=ext_id, source="que-faire-a-paris")
                created += 1
            else:
                updated += 1

            expo.title = title
            expo.description = (html_to_text(rec.get("description"))
                                or html_to_text(rec.get("lead_text")) or "")
            expo.date_start = date_start
            expo.date_end = parse_date(rec.get("date_end"))
            expo.schedule = html_to_text(rec.get("date_description"))
            expo.url = rec.get("url")
            expo.image_url = rec.get("cover_url")
            expo.price_type = "gratuit"
            expo.price_category = "gratuit_tous"  # flux QFAP = entrée libre

            # Lieu structuré
            expo.venue_name = rec.get("address_name")
            expo.address = rec.get("address_street")
            expo.postal_code = rec.get("address_zipcode")
            geo = rec.get("lat_lon") or {}
            expo.lat = geo.get("lat")
            expo.lon = geo.get("lon")

            # Réservation
            expo.reservation = map_reservation(rec.get("access_type"))
            expo.reservation_url = clean_link(rec.get("access_link"))

            if museum_id:
                expo.museum_id = museum_id

            db.session.add(expo)

        db.session.commit()
        print(f"✓ Sync terminée : {created} créées, {updated} mises à jour.")
        print(f"  Total expositions en base : {Exposition.query.count()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    run(args.limit)
