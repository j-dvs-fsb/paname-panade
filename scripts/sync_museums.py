"""Synchronise / nettoie les musées depuis le dataset officiel Île-de-France.

Source : https://data.iledefrance.fr — dataset `liste_des_musees_franciliens`
API Opendatasoft Explore v2.1, gratuite et sans clé. On ne prend que Paris.

Ce que fait le script :
  - récupère les ~50 musées parisiens (musées de France) officiels ;
  - enrichit les musées déjà en base (les 8 curés du seed) avec les données
    officielles : coordonnées GPS, identifiant_museofile, adresse/CP si absents —
    sans écraser la curation éditoriale (nom, description, free_access, etc.) ;
  - crée les musées manquants à partir des fiches officielles.

Le rapprochement avec les musées curés se fait via MANUAL_MATCH (museofile_id →
slug), puis pour la suite via la colonne museofile_id (matching stable).

Usage :  python scripts/sync_museums.py
"""
import sys
import os

import requests
from slugify import slugify

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from paname import create_app
from paname.extensions import db
from paname.models import Museum

API = ("https://data.iledefrance.fr/api/explore/v2.1/catalog/datasets/"
       "liste_des_musees_franciliens/records")
PAGE = 100

# Rapprochement des 8 musées curés (seed) avec leur fiche officielle.
# Permet de leur attribuer un museofile_id la première fois, sans matching flou.
MANUAL_MATCH = {
    "M5050": "centre-pompidou",
    "M1114": "maison-de-victor-hugo",
    "M1104": "musee-carnavalet-histoire-de-paris",
    "M1101": "musee-d-art-moderne-de-paris-mam",
    "M5060": "musee-d-orsay",
    "M5031": "musee-du-louvre",
    "M5055": "musee-du-quai-branly-jacques-chirac",
    "M1111": "petit-palais-musee-des-beaux-arts-de-la-ville-de-paris",
}


def fetch():
    """Récupère tous les musées parisiens, paginé."""
    records = []
    offset = 0
    while True:
        params = {
            "where": 'departement="Paris"',
            "limit": PAGE,
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


def arrondissement_from_cp(cp):
    """'75003' -> 'Paris 3e'. None si le CP ne correspond pas à un arr. 1-20."""
    if cp and len(cp) == 5 and cp.startswith("75"):
        try:
            n = int(cp[3:5])
        except ValueError:
            return None
        if 1 <= n <= 20:
            return f"Paris {n}er" if n == 1 else f"Paris {n}e"
    return None


def clean_name(name):
    """Capitalise la première lettre du nom officiel (souvent en minuscule)."""
    name = (name or "").strip()
    return name[:1].upper() + name[1:] if name else name


def clean_url(url):
    if not url:
        return None
    url = url.strip().rstrip("/")
    if not url.startswith("http"):
        url = "https://" + url
    return url


def unique_slug(base, museum_id=None):
    base = slugify(base)[:150] or "musee"
    slug = base
    n = 2
    while True:
        clash = Museum.query.filter(Museum.slug == slug)
        if museum_id is not None:
            clash = clash.filter(Museum.id != museum_id)
        if not clash.first():
            return slug
        slug = f"{base}-{n}"
        n += 1


def run():
    app = create_app()
    with app.app_context():
        print("→ Requête API Liste des musées franciliens (Paris)…")
        try:
            records = fetch()
        except requests.RequestException as e:
            print(f"✗ Erreur réseau : {e}")
            return
        print(f"  {len(records)} fiche(s) reçue(s).")

        created = enriched = 0
        for rec in records:
            mid = rec.get("identifiant_museofile")
            official_name = clean_name(rec.get("nom_officiel_du_musee"))
            if not mid or not official_name:
                continue

            lat = rec.get("latitude")
            lon = rec.get("longitude")
            cp = rec.get("code_postal")
            addr = " ".join(filter(None, [rec.get("adresse"), cp, "Paris"])) or None
            website = clean_url(rec.get("url"))
            arr = arrondissement_from_cp(cp)

            # 1) déjà rattaché via museofile_id ? 2) musée curé connu ? 3) nouveau.
            museum = Museum.query.filter_by(museofile_id=mid).first()
            if not museum and mid in MANUAL_MATCH:
                museum = Museum.query.filter_by(slug=MANUAL_MATCH[mid]).first()

            if museum:
                # Enrichissement : on ne touche pas à la curation éditoriale.
                museum.museofile_id = mid
                if lat is not None and museum.lat is None:
                    museum.lat = lat
                if lon is not None and museum.lon is None:
                    museum.lon = lon
                if addr and not museum.address:
                    museum.address = addr
                if arr and not museum.arrondissement:
                    museum.arrondissement = arr
                if website and not museum.website:
                    museum.website = website
                enriched += 1
            else:
                # Création depuis la fiche officielle (pas de donnée éditoriale).
                museum = Museum(
                    slug=unique_slug(official_name),
                    museofile_id=mid,
                    name=official_name,
                    address=addr,
                    arrondissement=arr,
                    website=website,
                    lat=lat,
                    lon=lon,
                )
                created += 1

            db.session.add(museum)

        db.session.commit()
        print(f"✓ Sync terminée : {created} créés, {enriched} enrichis.")
        print(f"  Total musées en base : {Museum.query.count()}")


if __name__ == "__main__":
    run()
