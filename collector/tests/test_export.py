import json
from datetime import date, datetime, timezone

import pytest

from panade import db, export, gratuite, seed, validate

from conftest import CLASSEUR

AUJ = date(2026, 10, 29)
MAINTENANT = datetime(2026, 10, 30, 7, 0, tzinfo=timezone.utc)
MUSIQUE = "musee-de-la-musique"          # vérifié : permanent gratuit_26, temporaire reduit_26 (5 €)
MAD = "musee-des-arts-decoratifs-union-centrale-des-arts-decoratifs"      # vérifié : gratuit_26
PROV = {"titre": "carte", "url": "carte", "date_debut": "time", "date_fin": "time"}


@pytest.fixture
def base(tmp_path):
    con = db.connect(tmp_path / "e.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    con.execute("DELETE FROM expositions")
    con.commit()
    yield con
    con.close()


def ajouter(con, titre, lieu=MUSIQUE, portee="temporaire", debut="2026-10-01", fin="2027-02-01", etat="publie", **extra):
    """Insère l'expo directement dans l'état voulu (sans passer par validate, qui promeut tout ce qui est sûr)."""
    url = f"https://x.test/{titre.lower().replace(' ', '-')}"
    cur = con.execute(
        "INSERT INTO expositions (lieu_id, titre, portee, date_debut, date_fin, url, source, provenance, etat, confiance, motif_revue)"
        " VALUES (?, ?, ?, ?, ?, ?, 'paris_musees', ?, ?, ?, ?)",
        (lieu, titre, portee, debut, fin, url, json.dumps(PROV), etat, 1.0 if etat == "publie" else None,
         "x" if etat != "publie" else None))
    i = cur.lastrowid
    calculee = gratuite.calculer(gratuite.charger(con, lieu), portee, AUJ).en_json()
    con.execute("UPDATE expositions SET gratuite_calculee = ?, gratuite_validee = ? WHERE id = ?",
                (calculee, calculee if etat == "publie" else None, i))
    for colonne, valeur in extra.items():
        con.execute(f"UPDATE expositions SET {colonne} = ? WHERE id = ?", (valeur, i))
    con.commit()
    return i


def contenu(con):
    return export.construire(con, AUJ, MAINTENANT).contenu


def expos(c):
    return {e["titre"]: e for l in c["lieux"] for e in l.get("expositions", [])}


def test_seuls_les_lieux_verifies_et_les_expos_publiees_sortent(base):
    ajouter(base, "Publiée")
    ajouter(base, "En revue", etat="en_revue")
    ajouter(base, "Rejetée", etat="rejete")
    ajouter(base, "Lieu à vérifier", lieu="musee-carnavalet-histoire-de-paris")
    c = contenu(base)
    assert set(expos(c)) == {"Publiée"}
    assert len(c["lieux"]) == 9 and all(l["id"] != "musee-carnavalet-histoire-de-paris" for l in c["lieux"])
    assert c["compte"] == {"lieux": 9, "expositions": 1}


def test_expositions_terminees_ne_sortent_pas_celles_sans_fin_si(base):
    ajouter(base, "Terminée", debut="2026-01-01", fin="2026-10-28")
    ajouter(base, "Dernier jour", debut="2026-01-01", fin="2026-10-29")
    ajouter(base, "Sans fin", fin=None, portee="permanent")
    assert set(expos(contenu(base))) == {"Dernier jour", "Sans fin"}


def test_jamais_de_champ_vide(base):
    """Invariant 2 : ni null, ni chaîne vide, ni /exposition/None."""
    ajouter(base, "Minimale", fin=None, debut=None)
    c = contenu(base)
    assert not export.a_des_champs_vides(c)
    texte = json.dumps(c, ensure_ascii=False)
    assert "null" not in texte and '""' not in texte and "/None" not in texte
    e = expos(c)["Minimale"]
    assert "date_debut" not in e and "date_fin" not in e and "description" not in e


def test_epurer():
    assert export.epurer({"a": None, "b": "", "c": [], "d": {}, "e": {"f": None}, "g": [None, {"h": ""}, 1], "i": 0, "j": False}) \
        == {"g": [1], "i": 0, "j": False}


def test_la_gratuite_exportee_est_calculee_pas_lue(base):
    ajouter(base, "Temporaire", portee="temporaire")
    ajouter(base, "Collection", portee="permanent", fin=None)
    e = expos(contenu(base))
    assert e["Temporaire"]["gratuite"] == {"categorie": "reduit_26", "libelle": "Tarif réduit pour les moins de 26 ans", "prix": 5,
                                           "plein_tarif": 12, "audience": "moins_26", "justificatif": e["Temporaire"]["gratuite"]["justificatif"]}
    assert e["Collection"]["gratuite"]["categorie"] == "gratuit_26" and e["Collection"]["gratuite"]["prix"] == 0


def test_donnee_non_verifiee_ne_sort_jamais_gratuite(base):
    ajouter(base, "Collection", portee="permanent", fin=None)
    base.execute("UPDATE tarifs SET verifie_le = NULL WHERE lieu_id = ?", (MUSIQUE,))
    base.commit()
    validate.valider(base, AUJ)              # la gratuité change : l'expo repart en relecture
    c = contenu(base)
    assert "Collection" not in expos(c)
    assert base.execute("SELECT etat FROM expositions").fetchone()[0] == "en_revue"
    assert all(t["verifie_le"] for l in c["lieux"] for t in l.get("tarifs", []))      # aucun tarif non vérifié exporté


def test_garde_fou_3_a_l_export_meme_sans_validate(base):
    a = ajouter(base, "Change", portee="permanent", fin=None)
    b = ajouter(base, "Stable", lieu=MAD, portee="temporaire")
    base.execute("UPDATE tarifs SET audience = 'moins_18' WHERE lieu_id = ? AND portee = 'permanent'", (MUSIQUE,))    # la règle change après validate
    base.commit()
    resultat = export.construire(base, AUJ, MAINTENANT)
    assert [i for i, _ in resultat.exclues] == [a]
    assert "gratuité modifiée sans relecture : gratuit_26 → a_confirmer" in resultat.exclues[0][1]
    assert set(expos(resultat.contenu)) == {"Stable"}
    ligne = base.execute("SELECT etat, motif_revue FROM expositions WHERE id = ?", (a,)).fetchone()
    assert (ligne["etat"], ligne["motif_revue"]) == ("en_revue", resultat.exclues[0][1])
    assert b and base.execute("SELECT etat FROM expositions WHERE id = ?", (b,)).fetchone()[0] == "publie"


def test_gratuite_jamais_relue_sort_de_l_export(base):
    i = ajouter(base, "Orpheline")
    base.execute("UPDATE expositions SET gratuite_validee = NULL WHERE id = ?", (i,))
    base.commit()
    assert export.construire(base, AUJ, MAINTENANT).exclues[0][1] == "gratuité jamais relue"


def test_collection_permanente_sans_affiche_prend_le_logo_du_lieu(base):
    ajouter(base, "Collection", portee="permanent", fin=None)
    ajouter(base, "Temporaire", portee="temporaire")
    e = expos(contenu(base))
    assert e["Collection"].get("image_url") is None            # le logo du Musée de la musique n'a pas été récupéré
    logo = base.execute("SELECT logo_url FROM lieux WHERE id = ?", (MAD,)).fetchone()[0]
    ajouter(base, "Collection MAD", lieu=MAD, portee="permanent", fin=None)
    assert expos(contenu(base))["Collection MAD"]["image_url"] == logo
    assert "image_url" not in expos(contenu(base))["Temporaire"]


def test_donnees_perimees_signalees_dans_l_export(base):
    ajouter(base, "Une expo")
    c = export.construire(base, date(2027, 2, 1), MAINTENANT).contenu       # 135 jours après les vérifications
    musique = next(l for l in c["lieux"] if l["id"] == MUSIQUE)
    assert musique["perime"] is True and all(t["perime"] is True for t in musique["tarifs"])
    assert "perime" not in next(l for l in contenu(base)["lieux"] if l["id"] == MUSIQUE)


def test_horaires_et_fermetures(base):
    musique = next(l for l in contenu(base)["lieux"] if l["id"] == MUSIQUE)
    lundi = next(h for h in musique["horaires"] if h["jour_num"] == 1)
    assert lundi["ferme"] is True and "ouverture" not in lundi
    assert any(h["nocturne"] is True for h in musique["horaires"])
    assert {"date": "12-25", "libelle": "25 decembre", "recurrent_annuel": True} in musique["fermetures"]
    assert "gratuite_override" not in musique and "notes" not in musique and "notes_crawler" not in musique


def test_empreinte_et_ecriture_atomique(base, tmp_path):
    ajouter(base, "Une expo")
    resultat = export.construire(base, AUJ, MAINTENANT)
    chemin = export.ecrire(resultat, tmp_path / "out", MAINTENANT)
    assert chemin.name == "export-2026-10-30T07-00-00Z.json" and list((tmp_path / "out").glob("*.tmp")) == []
    assert export.lire(chemin)["compte"] == {"lieux": 9, "expositions": 1}
    texte = chemin.read_text(encoding="utf-8").replace("Une expo", "Une autre")
    chemin.write_text(texte, encoding="utf-8")
    with pytest.raises(ValueError, match="empreinte invalide"):
        export.lire(chemin)


def test_export_deterministe(base):
    ajouter(base, "Une expo")
    a, b = contenu(base), contenu(base)
    assert a == b and a["empreinte"] == b["empreinte"]
