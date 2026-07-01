"""Seed : musées gratuits en permanence à Paris (liste éditoriale curée).

Usage :  python scripts/seed.py
"""
import sys
import os
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from slugify import slugify

from paname import create_app
from paname.extensions import db
from paname.models import Museum, Exposition

# Musées dont les collections permanentes sont gratuites, ou gratuits pour les -26 ans UE.
MUSEUMS = [
    {
        "name": "Musée Carnavalet — Histoire de Paris",
        "arrondissement": "Paris 3e",
        "address": "23 Rue de Sévigné, 75003 Paris",
        "website": "https://www.carnavalet.paris.fr",
        "free_access": "permanent",
        "description": "L'histoire de Paris de la préhistoire à nos jours, dans un hôtel particulier du Marais. Collections permanentes en accès libre.",
    },
    {
        "name": "Petit Palais — Musée des Beaux-Arts de la Ville de Paris",
        "arrondissement": "Paris 8e",
        "address": "Av. Winston Churchill, 75008 Paris",
        "website": "https://www.petitpalais.paris.fr",
        "free_access": "permanent",
        "description": "Beaux-arts de l'Antiquité à 1900 dans un palais de l'Exposition universelle de 1900.",
    },
    {
        "name": "Musée d'Art Moderne de Paris (MAM)",
        "arrondissement": "Paris 16e",
        "address": "11 Av. du Président Wilson, 75116 Paris",
        "website": "https://www.mam.paris.fr",
        "free_access": "permanent",
        "description": "Art moderne et contemporain du XXe siècle à aujourd'hui. Collection permanente gratuite.",
    },
    {
        "name": "Maison de Victor Hugo",
        "arrondissement": "Paris 4e",
        "address": "6 Place des Vosges, 75004 Paris",
        "website": "https://www.maisonsvictorhugo.paris.fr",
        "free_access": "permanent",
        "description": "L'appartement de Victor Hugo place des Vosges, où il vécut de 1832 à 1848.",
    },
    {
        "name": "Musée du Louvre",
        "arrondissement": "Paris 1er",
        "address": "Rue de Rivoli, 75001 Paris",
        "website": "https://www.louvre.fr",
        "free_access": "gratuit_26",
        "description": "Le plus grand musée d'art au monde. Gratuit pour les moins de 26 ans résidents de l'UE (et pour tous certains soirs).",
    },
    {
        "name": "Musée d'Orsay",
        "arrondissement": "Paris 7e",
        "address": "Esplanade Valéry Giscard d'Estaing, 75007 Paris",
        "website": "https://www.musee-orsay.fr",
        "free_access": "gratuit_26",
        "description": "Chef-d'œuvre de l'art du XIXe siècle (impressionnisme...) dans une ancienne gare. Gratuit pour les -26 ans UE.",
    },
    {
        "name": "Musée du Quai Branly — Jacques Chirac",
        "arrondissement": "Paris 7e",
        "address": "37 Quai Branly, 75007 Paris",
        "website": "https://www.quaibranly.fr",
        "free_access": "gratuit_26",
        "description": "Arts et civilisations d'Afrique, d'Asie, d'Océanie et des Amériques.",
    },
    {
        "name": "Centre Pompidou",
        "arrondissement": "Paris 4e",
        "address": "Place Georges-Pompidou, 75004 Paris",
        "website": "https://www.centrepompidou.fr",
        "free_access": "gratuit_26",
        "description": "Le plus grand musée d'art moderne et contemporain d'Europe. Gratuit pour les -26 ans UE.",
    },
]


def run():
    app = create_app()
    with app.app_context():
        created = 0
        for data in MUSEUMS:
            slug = slugify(data["name"])
            museum = Museum.query.filter_by(slug=slug).first()
            if not museum:
                museum = Museum(slug=slug)
                created += 1
            for k, v in data.items():
                setattr(museum, k, v)
            db.session.add(museum)
        db.session.commit()
        print(f"✓ {len(MUSEUMS)} musées traités ({created} créés).")
        print(f"  Total musées en base : {Museum.query.count()}")


if __name__ == "__main__":
    run()
