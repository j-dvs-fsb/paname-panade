"""Registre des scrapers : slug de musée -> fonction scrape(museum) -> list[dict]."""
from . import louvre
from . import paris_musees

# Musées sur la plateforme Paris Musées (même scraper générique).
_PARIS_MUSEES = [
    "musee-carnavalet-histoire-de-paris",
    "petit-palais-musee-des-beaux-arts-de-la-ville-de-paris",
    "musee-d-art-moderne-de-paris-mam",
    "maison-de-victor-hugo",
]

SCRAPERS = {
    "musee-du-louvre": louvre.scrape,
    **{slug: paris_musees.scrape for slug in _PARIS_MUSEES},
}
