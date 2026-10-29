import json

import pytest

from panade import completer, db, seed
from panade.extractors import choisir

from conftest import CLASSEUR

WEB = CLASSEUR.parent / "lieux_web.json"


@pytest.fixture
def base(tmp_path):
    con = db.connect(tmp_path / "w.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    yield con
    con.close()


def lieu(con, lid):
    return con.execute("SELECT * FROM lieux WHERE id = ?", (lid,)).fetchone()


def test_comble_les_trous_et_ne_touche_pas_au_statut(base):
    avant = {r["id"]: r["statut"] for r in base.execute("SELECT id, statut FROM lieux")}
    completer.appliquer(base, WEB)
    assert lieu(base, "musee-du-louvre")["expos_url"] == "https://www.louvre.fr/expositions-et-evenements/expositions"
    assert lieu(base, "musee-du-louvre")["tarifs_url"] == "https://www.louvre.fr/visiter/horaires-tarifs"
    assert {r["id"]: r["statut"] for r in base.execute("SELECT id, statut FROM lieux")} == avant


def test_ne_reecrit_pas_une_saisie_sauf_correction_declaree(base, tmp_path):
    fichier = tmp_path / "web.json"
    fichier.write_text(json.dumps({"genere_le": "2026-10-29", "lieux": {
        "musee-de-la-vie-romantique": {"expos_url": "https://autre.test/"},
        "musee-de-la-musique": {"expos_url": "https://philharmoniedeparis.fr/fr/musee-de-la-musique", "corriger": ["expos_url"]}}}))
    completer.appliquer(base, fichier)
    assert lieu(base, "musee-de-la-vie-romantique")["expos_url"] == "https://museevieromantique.paris.fr/expositions/exposition-en-cours"
    assert lieu(base, "musee-de-la-musique")["expos_url"] == "https://philharmoniedeparis.fr/fr/musee-de-la-musique"


def test_idempotent(base):
    completer.appliquer(base, WEB)
    assert completer.appliquer(base, WEB) == []


def test_les_sites_qui_refusent_les_robots_passent_en_manuel(base):
    completer.appliquer(base, WEB)
    for lid in ("musee-d-orsay", "musee-des-monnaies-et-medailles", "musee-du-moyen-age-thermes-et-hotel-de-cluny"):
        assert lieu(base, lid)["tier"] == "T4"
        assert choisir(lieu(base, lid)) is None
    assert "musee-legiondhonneur.fr n'est plus le site officiel" in lieu(base, "musee-national-de-la-legion-d-honneur-et-des-ordres-de-cheva")["notes_crawler"]


def test_couverture_apres_completion(base):
    completer.appliquer(base, WEB)
    couverts = [r["id"] for r in base.execute("SELECT * FROM lieux") if choisir(r)]
    assert len(couverts) >= 30
