import json
from datetime import date

import pytest

from panade import db, seed, validate

from conftest import CLASSEUR

AUJ = date(2026, 10, 29)


@pytest.fixture
def base(tmp_path):
    con = db.connect(tmp_path / "v.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    yield con
    con.close()


def ajouter(con, lieu="musee-carnavalet-histoire-de-paris", titre="Expo", portee="temporaire", debut="2026-10-01",
            fin="2027-02-01", url=None, prov=None, etat="en_revue", confiance=None, motif=None, **extra):
    prov = prov if prov is not None else {"titre": "carte", "url": "carte", "date_debut": "time", "date_fin": "time"}
    url = url if url is not None else f"https://x.test/{titre.lower().replace(' ', '-')}"
    cur = con.execute(
        "INSERT INTO expositions (lieu_id, titre, portee, date_debut, date_fin, url, source, provenance, etat, confiance, motif_revue)"
        " VALUES (?, ?, ?, ?, ?, ?, 'paris_musees', ?, ?, ?, ?)",
        (lieu, titre, portee, debut, fin, url, json.dumps(prov), etat, confiance, motif))
    con.commit()
    for colonne, valeur in extra.items():
        con.execute(f"UPDATE expositions SET {colonne} = ? WHERE id = ?", (valeur, cur.lastrowid))
    con.commit()
    return cur.lastrowid


def ligne(con, i):
    return dict(con.execute("SELECT * FROM expositions WHERE id = ?", (i,)).fetchone())


def test_nouvelle_expo_lue_de_facon_sure_est_publiee_avec_sa_gratuite_calculee(base):
    i = ajouter(base, portee="permanent", titre="Parcours")
    r = validate.valider(base, AUJ)
    e = ligne(base, i)
    assert (e["etat"], e["confiance"], r.promues) == ("publie", 1.0, 1)
    assert json.loads(e["gratuite_calculee"])["statut"] == "gratuit_tous"        # Carnavalet permanent : règle de famille
    assert e["gratuite_validee"] == e["gratuite_calculee"]


def test_dates_deduites_restent_en_revue_avec_leur_motif(base):
    i = ajouter(base, prov={"titre": "carte", "url": "carte", "date_debut": "texte_fr_annee_deduite", "date_fin": "texte_fr_annee_deduite"})
    validate.valider(base, AUJ)
    e = ligne(base, i)
    assert e["etat"] == "en_revue" and e["motif_revue"] == "confiance 0.60 sous le seuil 0.80 (dates)"


def test_une_seule_date_connue_ne_suffit_pas(base):
    i = ajouter(base, fin=None, prov={"titre": "carte", "url": "carte", "date_debut": "time", "date_fin": "absente"})
    validate.valider(base, AUJ)
    assert ligne(base, i)["etat"] == "en_revue"


def test_sans_aucune_date_confiance_nulle(base):
    i = ajouter(base, debut=None, fin=None, prov={"titre": "fiche", "url": "fiche", "date_debut": "absente", "date_fin": "absente"})
    validate.valider(base, AUJ)
    e = ligne(base, i)
    assert (e["etat"], e["confiance"]) == ("en_revue", 0.0) and "dates" in e["motif_revue"]


def test_la_graine_du_classeur_n_est_jamais_publiee_toute_seule(base):
    r = validate.valider(base, AUJ)
    assert base.execute("SELECT COUNT(*) FROM expositions WHERE etat = 'publie'").fetchone()[0] == 0
    assert r.promues == 0
    assert {m for (m,) in base.execute("SELECT DISTINCT motif_revue FROM expositions")} == {"importée du classeur, jamais relue"}


def test_seuil_reglable(base):
    i = ajouter(base, prov={"titre": "carte", "url": "carte", "date_debut": "texte_fr_annee_deduite", "date_fin": "texte_fr_annee_deduite"})
    validate.valider(base, AUJ, seuil_confiance=0.5)
    assert ligne(base, i)["etat"] == "publie"


def test_expo_au_motif_humain_n_est_jamais_promue_par_la_machine(base):
    i = ajouter(base, motif="absente de la page le 2026-10-30")
    validate.valider(base, AUJ)
    assert ligne(base, i)["etat"] == "en_revue"


def test_dates_hors_fenetre_de_trois_ans_bloquees(base):
    i = ajouter(base, debut="2026-10-01", fin="2031-01-01")
    validate.valider(base, AUJ)
    e = ligne(base, i)
    assert e["etat"] == "en_revue" and "fenêtre de 3 ans" in e["motif_revue"]


def test_les_trois_chaillot_experience(base):
    """Même lieu, mêmes dates, titre voisin : une seule exposition survit, avec les champs des autres."""
    a = ajouter(base, titre="Chaillot Expérience", url="https://x.test/chaillot-experience", debut="2026-09-01", fin="2027-06-30")
    b = ajouter(base, titre="Chaillot Experience", url="https://x.test/chaillot-experience-2", debut="2026-09-01", fin="2027-06-30",
                description="Une description", image_url="https://x.test/i.jpg")
    c = ajouter(base, titre="CHAILLOT expérience", url="https://x.test/chaillot-experience-3", debut="2026-09-01", fin=None)
    r = validate.valider(base, AUJ)
    assert r.doublons == 2
    etats = [ligne(base, i)["etat"] for i in (a, b, c)]
    assert etats.count("rejete") == 2
    survivant = next(ligne(base, i) for i in (a, b, c) if ligne(base, i)["etat"] != "rejete")
    assert survivant["description"] == "Une description" and survivant["image_url"] == "https://x.test/i.jpg"
    assert any("doublon" in ligne(base, i)["motif_revue"] for i in (a, b, c) if ligne(base, i)["etat"] == "rejete")


def test_la_publiee_gagne_contre_son_doublon(base):
    ancienne = ajouter(base, titre="Paris Rome", etat="publie", confiance=0.9, gratuite_validee=None)
    recente = ajouter(base, titre="Paris-Rome", url="https://x.test/autre")
    validate.valider(base, AUJ)
    assert ligne(base, ancienne)["etat"] == "publie" and ligne(base, recente)["etat"] == "rejete"


def test_memes_titres_dates_differentes_ne_sont_pas_des_doublons(base):
    a = ajouter(base, titre="Nocturne", debut="2026-10-01", fin="2026-12-01")
    b = ajouter(base, titre="Nocturne", debut="2027-01-01", fin="2027-03-01", url="https://x.test/n2")
    r = validate.valider(base, AUJ)
    assert r.doublons == 0 and ligne(base, a)["etat"] != "rejete" and ligne(base, b)["etat"] != "rejete"


def test_garde_fou_3_gratuite_modifiee_sans_relecture(base):
    i = ajouter(base, portee="permanent", titre="Parcours")
    validate.valider(base, AUJ)
    assert ligne(base, i)["etat"] == "publie"
    # le lieu reçoit une exception : la gratuité calculée change, personne n'a relu
    base.execute("UPDATE lieux SET gratuite_override = 'EXCEPTION : tout est payant' WHERE id = 'musee-carnavalet-histoire-de-paris'")
    base.commit()
    r = validate.valider(base, AUJ)
    e = ligne(base, i)
    assert (e["etat"], r.gratuite_changee) == ("en_revue", 1)
    assert e["motif_revue"] == "gratuité modifiée sans relecture : gratuit_tous → a_confirmer"
    # une personne relit : la nouvelle valeur devient la référence et l'expo repart
    base.execute("UPDATE expositions SET etat = 'publie', motif_revue = NULL, gratuite_validee = gratuite_calculee WHERE id = ?", (i,))
    base.commit()
    validate.valider(base, AUJ)
    assert ligne(base, i)["etat"] == "publie"


def test_idempotent(base):
    ajouter(base, portee="permanent", titre="Parcours")
    ajouter(base, titre="Autre", prov={"titre": "carte", "url": "carte", "date_debut": "texte_fr_annee_deduite", "date_fin": "texte_fr_annee_deduite"})
    validate.valider(base, AUJ)
    avant = [tuple(r) for r in base.execute("SELECT * FROM expositions ORDER BY id")]
    r = validate.valider(base, AUJ)
    assert [tuple(x) for x in base.execute("SELECT * FROM expositions ORDER BY id")] == avant
    assert (r.promues, r.bloquees, r.doublons, r.gratuite_changee) == (0, 0, 0, 0)


def test_donnees_perimees_signalees_sans_rien_changer(base):
    r = validate.valider(base, date(2027, 2, 1))     # 135 jours après le 2026-09-19
    assert any(p.startswith("lieu musee-de-montmartre") for p in r.perimes)
    assert any(p.startswith("tarifs de musee-de-la-musique") for p in r.perimes)
    assert base.execute("SELECT COUNT(*) FROM lieux WHERE statut = 'verifie'").fetchone()[0] == 9
    assert validate.valider(base, AUJ).perimes == []


def test_motifs_et_gravite(base):
    r = validate.valider(base, AUJ)
    assert r.problemes_graves == []


def test_expo_rejetee_a_la_main_est_laissee_tranquille(base):
    i = ajouter(base, titre="Rejetée", etat="rejete", motif="rejetée par une personne")
    validate.valider(base, AUJ)
    e = ligne(base, i)
    assert (e["etat"], e["motif_revue"]) == ("rejete", "rejetée par une personne") and e["gratuite_calculee"] is None


def test_portee_incertaine_reste_en_revue(base):
    i = ajouter(base, prov={"titre": "carte", "url": "carte", "date_debut": "time", "date_fin": "time", "portee": "incertaine"})
    validate.valider(base, AUJ)
    e = ligne(base, i)
    assert e["etat"] == "en_revue" and e["motif_revue"] == "confiance 0.50 sous le seuil 0.80 (portée)"


def test_titres_qui_ne_different_que_par_un_nombre_ne_sont_pas_des_doublons(base):
    a = ajouter(base, titre="Nocturne 1", url="https://x.test/n1")
    b = ajouter(base, titre="Nocturne 2", url="https://x.test/n2")
    r = validate.valider(base, AUJ)
    assert r.doublons == 0 and ligne(base, a)["etat"] != "rejete" and ligne(base, b)["etat"] != "rejete"


def test_jusqu_au_suffit_sans_date_de_debut(base):
    i = ajouter(base, debut=None, prov={"titre": "carte", "url": "carte", "date_debut": "texte_fr", "date_fin": "texte_fr"})
    validate.valider(base, AUJ)
    assert ligne(base, i)["etat"] == "publie"
