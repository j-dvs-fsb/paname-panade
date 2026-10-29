import json
from datetime import date

import pytest

from panade import cli, db, health, seed

from conftest import CLASSEUR

AUJ = date(2026, 11, 3)
CARNAVALET = "musee-carnavalet-histoire-de-paris"
URL = "https://www.carnavalet.paris.fr/expositions/expositions-en-cours"


@pytest.fixture
def base(tmp_path):
    con = db.connect(tmp_path / "h.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    con.execute("UPDATE lieux SET expos_url = ? WHERE id = ?", (URL, CARNAVALET))
    con.commit()
    yield con
    con.close()


def run(con, jour, statut, items=None, erreur=None, lieu=CARNAVALET):
    con.execute("INSERT INTO runs (lieu_id, demarre_le, statut, items_trouves, erreur, url) VALUES (?, ?, ?, ?, ?, ?)",
                (lieu, f"2026-11-{jour:02d}T03:00:00Z", statut, items, erreur, URL))
    con.commit()


def test_un_echec_isole_n_est_pas_un_silence(base):
    run(base, 1, "ok", 4)
    run(base, 2, "ok", 4)
    run(base, 3, "erreur", erreur="HTTP 503")
    assert health.lieux_muets(base, AUJ) == []


def test_deux_nuits_de_suite_c_est_un_silence(base):
    run(base, 1, "ok", 4)
    run(base, 2, "erreur", erreur="HTTP 503")
    run(base, 3, "erreur", erreur="HTTP 503")
    (m,) = health.lieux_muets(base, AUJ)
    assert (m.lieu, m.nuits, m.genre, m.derniere_reussite) == (CARNAVALET, 2, "indisponible", "2026-11-01")
    assert "muet depuis 2 nuit(s)" in m.message and "HTTP 503" in m.message


def test_une_reussite_interrompt_la_serie(base):
    run(base, 1, "erreur")
    run(base, 2, "erreur")
    run(base, 3, "inchange")
    assert health.lieux_muets(base, AUJ) == []


def test_plusieurs_passages_le_meme_jour_comptent_pour_une_nuit(base):
    run(base, 3, "erreur")
    run(base, 3, "erreur")
    assert health.lieux_muets(base, AUJ) == []


def test_extracteur_qui_ne_trouve_plus_rien_apres_avoir_trouve(base):
    run(base, 1, "ok", 4)
    run(base, 2, "vide", 0, erreur="l'extracteur ne trouve rien sur la page")
    run(base, 3, "vide", 0, erreur="l'extracteur ne trouve rien sur la page")
    (m,) = health.lieux_muets(base, AUJ)
    assert m.genre == "casse"
    (c,) = health.extracteurs_casses(base)
    assert c == {"lieu": CARNAVALET, "depuis": "2026-11-03", "dernier_succes": "2026-11-01",
                 "reparation": f"panade discover {CARNAVALET}"}


def test_robots_qui_interdit_est_signale_comme_tel(base):
    run(base, 2, "interdit", erreur="robots.txt interdit /expositions/expositions-en-cours")
    run(base, 3, "interdit", erreur="robots.txt interdit /expositions/expositions-en-cours")
    assert health.lieux_muets(base, AUJ)[0].genre == "interdit"


def test_collect_qui_ne_passe_plus_du_tout_est_un_silence(base):
    run(base, 1, "ok", 4)
    (m,) = health.lieux_muets(base, date(2026, 11, 4))
    assert (m.genre, m.nuits) == ("silencieux", 3) and "aucun passage" in m.detail


def test_lieu_jamais_collecte_n_est_pas_muet(base):
    assert health.lieux_muets(base, AUJ) == []


def test_lieu_sans_extracteur_n_est_jamais_muet(base):
    run(base, 1, "erreur", lieu="musee-de-la-poste")
    run(base, 2, "erreur", lieu="musee-de-la-poste")
    assert health.lieux_muets(base, AUJ) == []


@pytest.mark.parametrize("nuits, alerte", [(1, False), (2, True), (3, False), (8, False), (9, True), (16, True)])
def test_alerte_a_deux_nuits_puis_chaque_semaine(nuits, alerte):
    assert health.alerte_du_soir(health.Muet("x", nuits, "indisponible", None, "")) is alerte


def test_donnees_perimees_et_horaires_expires(base):
    p = health.donnees_perimees(base, date(2027, 2, 1))
    assert any("musee-de-montmartre" in x for x in p["verifications"])
    assert {"lieu_id": "musee-d-art-et-d-histoire-du-judaisme", "jusqu_au": "2026-10-14"} in p["horaires_expires"]
    assert health.donnees_perimees(base, date(2026, 10, 1))["horaires_expires"] == []


def test_publication_ancienne(base, tmp_path):
    (tmp_path / "publie").mkdir()
    (tmp_path / "publie" / "derniere.json").write_text(json.dumps({"genere_le": "2026-10-29T07:00:00Z"}), encoding="utf-8")
    r = health.rapport(base, AUJ, tmp_path)
    assert r["publication"] == {"derniere": "2026-10-29", "jours": 5}
    assert any("aucune publication depuis 5 jours" in a for a in r["alertes"])


def test_jamais_publie(base, tmp_path):
    assert "le site n'a encore reçu aucune publication" in health.rapport(base, AUJ, tmp_path)["alertes"]


def test_rapport_complet(base, tmp_path):
    run(base, 2, "erreur", erreur="HTTP 503")
    run(base, 3, "erreur", erreur="HTTP 503")
    r = health.rapport(base, AUJ, tmp_path)
    assert r["muets"][0]["lieu"] == CARNAVALET and r["lieux"] == {"a_verifier": 48, "verifie": 9}
    assert {"lieu": "musee-de-montmartre", "raison": "T4, collecte manuelle"} in r["sans_extracteur"]
    assert json.dumps(r)        # sérialisable


def test_cli_health_code_de_sortie_et_alerte(base, tmp_path, capsys):
    chemin = str(tmp_path / "h.db")
    assert cli.main(["health", "--db", chemin, "--dossier", str(tmp_path), "--alerter"]) == 1      # jamais publié
    sortie = capsys.readouterr()
    assert "ALERTE" in sortie.out and "aucune publication" in (tmp_path / "alertes.log").read_text(encoding="utf-8")


def test_un_musee_sans_exposition_en_cours_n_est_ni_muet_ni_casse(base):
    run(base, 1, "vide", 0, erreur="l'extracteur ne trouve rien sur la page")
    run(base, 2, "vide", 0, erreur="l'extracteur ne trouve rien sur la page")
    run(base, 3, "vide", 0, erreur="l'extracteur ne trouve rien sur la page")
    assert health.lieux_muets(base, AUJ) == [] and health.extracteurs_casses(base) == []
