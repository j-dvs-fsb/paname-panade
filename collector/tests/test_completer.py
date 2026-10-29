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


def test_comble_les_trous_et_ne_retrograde_aucun_statut(base):
    avant = {r["id"]: r["statut"] for r in base.execute("SELECT id, statut FROM lieux")}
    completer.appliquer(base, WEB)
    assert lieu(base, "musee-du-louvre")["expos_url"] == "https://www.louvre.fr/expositions-et-evenements/expositions"
    assert lieu(base, "musee-du-louvre")["tarifs_url"] == "https://www.louvre.fr/visiter/horaires-tarifs"
    apres = {r["id"]: r["statut"] for r in base.execute("SELECT id, statut FROM lieux")}
    assert all(apres[i] == "verifie" for i, s in avant.items() if s == "verifie")        # rien n'est rétrogradé
    nouveaux = {i for i in apres if apres[i] != avant[i]}
    assert "musee-du-louvre" in nouveaux and lieu(base, "musee-du-louvre")["verifie_par"] == "claude"


def test_tarifs_officiels_ajoutes_une_seule_fois_et_conformes(base):
    completer.appliquer(base, WEB)
    n = base.execute("SELECT COUNT(*) FROM tarifs").fetchone()[0]
    completer.appliquer(base, WEB)
    assert base.execute("SELECT COUNT(*) FROM tarifs").fetchone()[0] == n
    louvre = base.execute("SELECT * FROM tarifs WHERE lieu_id = 'musee-du-louvre' AND audience = 'moins_26_ue'").fetchone()
    assert (louvre["portee"], louvre["regime"], louvre["prix"], louvre["source_url"]) == \
        ("tout", "gratuit", 0, "https://www.louvre.fr/visiter/horaires-tarifs")


def test_arts_et_metiers_le_piege_central(base):
    """Gratuit 18-25 ans UE « uniquement pour l'exposition permanente » : pas pour les temporaires."""
    from datetime import date
    from panade import gratuite
    completer.appliquer(base, WEB)
    l = gratuite.charger(base, "musee-des-arts-et-metiers")
    assert gratuite.calculer(l, "permanent", date(2026, 10, 29)).statut == "gratuit_26"
    assert gratuite.calculer(l, "temporaire", date(2026, 10, 29)).statut == "a_confirmer"


def test_paris_musees_temporaire_reduit_et_non_payant(base):
    from datetime import date
    from panade import gratuite
    completer.appliquer(base, WEB)
    carnavalet = gratuite.calculer(gratuite.charger(base, "musee-carnavalet-histoire-de-paris"), "temporaire", date(2026, 10, 29))
    assert carnavalet.statut == "reduit_26" and carnavalet.source == "famille"
    bourdelle = gratuite.calculer(gratuite.charger(base, "musee-bourdelle"), "temporaire", date(2026, 10, 29))
    assert (bourdelle.statut, bourdelle.prix, bourdelle.plein_tarif) == ("reduit_26", 10, 12)


def test_une_verification_existante_n_est_pas_reecrite(base):
    avant = lieu(base, "musee-de-montmartre")
    completer.appliquer(base, WEB)
    assert (lieu(base, "musee-de-montmartre")["verifie_le"], lieu(base, "musee-de-montmartre")["verifie_par"]) == \
        (avant["verifie_le"], avant["verifie_par"])


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


def test_musee_de_l_armee_gratuit_en_permanent_seulement(base):
    from datetime import date
    from panade import gratuite
    completer.appliquer(base, WEB)
    l = gratuite.charger(base, "musee-de-l-armee")
    assert gratuite.calculer(l, "permanent", date(2026, 10, 29)).statut == "gratuit_26"
    assert gratuite.calculer(l, "temporaire", date(2026, 10, 29)).statut == "a_confirmer"


def test_horaires_poses_une_fois_et_jamais_sur_ceux_du_classeur(base):
    avant = base.execute("SELECT COUNT(*) FROM horaires WHERE lieu_id = 'musee-de-la-vie-romantique'").fetchone()[0]
    completer.appliquer(base, WEB)
    louvre = {r["jour"]: r for r in base.execute("SELECT * FROM horaires WHERE lieu_id = 'musee-du-louvre' AND nocturne = 0")}
    assert louvre["mardi"]["ferme"] == 1 and (louvre["vendredi"]["ouverture"], louvre["vendredi"]["fermeture"]) == ("09:00", "21:00")
    assert base.execute("SELECT COUNT(*) FROM horaires WHERE lieu_id = 'musee-de-la-vie-romantique'").fetchone()[0] == avant
    n = base.execute("SELECT COUNT(*) FROM horaires").fetchone()[0]
    completer.appliquer(base, WEB)
    assert base.execute("SELECT COUNT(*) FROM horaires").fetchone()[0] == n
    assert base.execute("SELECT COUNT(*) FROM fermetures WHERE lieu_id = 'musee-picasso'").fetchone()[0] == 3
