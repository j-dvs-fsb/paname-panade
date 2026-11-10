from datetime import datetime, time

import pytest

from panade import cli, db, seed

from conftest import CLASSEUR, FAMILLE, LIEU, ligne


@pytest.fixture(scope="module")
def base_reelle(tmp_path_factory):
    """La vraie base issue du vrai classeur, construite une seule fois."""
    con = db.connect(tmp_path_factory.mktemp("seed") / "reel.db")
    db.init_schema(con)
    rapport = seed.importer(con, CLASSEUR)
    yield con, rapport
    con.close()


def un(con, sql, *params):
    return con.execute(sql, params).fetchall()


# --- le vrai classeur -------------------------------------------------------

def test_comptes(base_reelle):
    con, rapport = base_reelle
    for table, attendu in {"familles": 6, "lieux": 57, "tarifs": 68, "horaires": 61,
                           "fermetures": 19, "expositions": 21, "runs": 0}.items():
        assert un(con, f"SELECT COUNT(*) FROM {table}")[0][0] == attendu, table
    assert rapport.lieux_verifies == 9
    assert un(con, "SELECT COUNT(*) FROM lieux WHERE statut = 'a_verifier'")[0][0] == 48


def test_aucune_valeur_vide_ni_litterale(base_reelle):
    """Invariant 2 : ni chaîne vide, ni 'None' / 'null' écrits en toutes lettres."""
    con, _ = base_reelle
    for (table,) in un(con, "SELECT name FROM sqlite_master WHERE type = 'table'"):
        for colonne in un(con, f"PRAGMA table_info({table})"):
            nom = colonne["name"]
            n = un(con, f'SELECT COUNT(*) FROM {table} WHERE trim(CAST("{nom}" AS TEXT)) = "" '
                        f'OR lower(trim(CAST("{nom}" AS TEXT))) IN ("none", "null", "nan")')[0][0]
            assert n == 0, f"{table}.{nom}"


def test_aucune_url_ne_contient_d_espace(base_reelle):
    con, _ = base_reelle
    for table, colonne in [("lieux", "expos_url"), ("lieux", "tarifs_url"), ("lieux", "horaires_url"),
                           ("lieux", "logo_url"), ("tarifs", "source_url"),
                           ("expositions", "url"), ("expositions", "image_url")]:
        assert un(con, f"SELECT COUNT(*) FROM {table} WHERE {colonne} LIKE '% %'")[0][0] == 0


def test_liens_invalides_du_classeur(base_reelle):
    con, rapport = base_reelle
    zadkine = un(con, "SELECT expos_url, notes_crawler FROM lieux WHERE id = 'musee-zadkine'")[0]
    assert zadkine["expos_url"] is None
    assert "probablement zadkine.paris.fr" in zadkine["notes_crawler"]  # l'indice est conservé
    assert un(con, "SELECT COUNT(*) FROM lieux WHERE logo_url IS NULL AND statut = 'verifie'")[0][0] == 2
    assert rapport.logo_du_lieu == 3
    assert un(con, "SELECT COUNT(*) FROM expositions WHERE image_url = 'LOGO_MUSEE'")[0][0] == 0
    cartier = un(con, "SELECT DISTINCT source_url FROM tarifs WHERE lieu_id LIKE 'fondation-cartier%'")
    assert [r[0] for r in cartier] == ["https://www.fondationcartier.com/informations-pratiques"]


def test_rien_n_est_publie_sans_relecture(base_reelle):
    con, _ = base_reelle
    lignes = un(con, "SELECT DISTINCT etat, confiance FROM expositions")
    assert [tuple(r) for r in lignes] == [("en_revue", None)]


def test_vocabulaire_du_classeur_traduit(base_reelle):
    con, _ = base_reelle
    assert {r[0] for r in un(con, "SELECT DISTINCT statut FROM lieux")} == {"a_verifier", "verifie"}
    assert {r[0] for r in un(con, "SELECT DISTINCT confiance_famille FROM lieux")} == {"sur", "a_confirmer"}
    assert un(con, "SELECT COUNT(*) FROM lieux WHERE confiance_famille = 'a_confirmer'")[0][0] == 12


def test_montmartre_reste_en_t4(base_reelle):
    con, _ = base_reelle
    montmartre = un(con, "SELECT tier, statut, notes_crawler FROM lieux WHERE id = 'musee-de-montmartre'")[0]
    assert montmartre["tier"] == "T4"
    assert "INTERDIT les robots" in montmartre["notes_crawler"]


def test_exceptions_de_famille_conservees_telles_quelles(base_reelle):
    con, _ = base_reelle
    for lieu_id in ("palais-galliera-musee-de-la-mode-et-de-la-ville-de-paris",
                    "crypte-archeologique-de-l-ile-de-la-cite"):
        override = un(con, "SELECT gratuite_override FROM lieux WHERE id = ?", lieu_id)[0][0]
        assert override.startswith("EXCEPTION a la regle Paris Musees")
    assert un(con, "SELECT COUNT(*) FROM lieux WHERE gratuite_override IS NOT NULL")[0][0] == 2


def test_familles_gardent_le_texte_du_classeur(base_reelle):
    con, _ = base_reelle
    f = {r["id"]: r for r in un(con, "SELECT * FROM familles")}
    assert f["paris_musees"]["gratuite_permanent"] == "Gratuit pour tous"
    assert f["paris_musees"]["gratuite_temporaire"] == "Payant pour tous (gratuit -18 ans)"
    assert f["musee_national"]["age_max"] == 26
    assert f["prive_assoc"]["gratuite_permanent"] == "À VÉRIFIER"


@pytest.mark.parametrize("lieu_id, audience, temporaire_prix", [
    ("musee-d-art-et-d-histoire-du-judaisme", "moins_26_ue", 5),    # mahJ
    ("musee-de-la-musique", "moins_26_ue", 5),                       # Musée de la musique
])
def test_piege_central_permanent_gratuit_temporaire_payant(base_reelle, lieu_id, audience, temporaire_prix):
    """Le même musée est gratuit en permanent et payant en temporaire : deux lignes, deux portées."""
    con, _ = base_reelle
    permanent = un(con, "SELECT regime, prix FROM tarifs WHERE lieu_id = ? AND portee = 'permanent' "
                        "AND audience = ?", lieu_id, audience)
    assert [tuple(r) for r in permanent] == [("gratuit", 0)]
    temporaire = un(con, "SELECT regime, prix FROM tarifs WHERE lieu_id = ? AND portee = 'temporaire' "
                         "AND regime = 'reduit' AND audience IN ('moins_26', 'moins_26_ue')", lieu_id)
    assert [tuple(r) for r in temporaire] == [("reduit", temporaire_prix)]


def test_prix_inconnu_reste_inconnu(base_reelle):
    """La Vie romantique n'affiche pas de prix pour les expos temporaires : NULL, pas 0."""
    con, _ = base_reelle
    t = un(con, "SELECT regime, prix, plein_tarif FROM tarifs "
                "WHERE lieu_id = 'musee-de-la-vie-romantique' AND portee = 'temporaire'")
    assert [tuple(r) for r in t] == [("reduit", None, None)]


def test_horaires_et_fermetures(base_reelle):
    con, _ = base_reelle
    assert un(con, "SELECT COUNT(*) FROM horaires WHERE nocturne = 1")[0][0] == 5
    assert un(con, "SELECT COUNT(*) FROM horaires WHERE ferme = 1 AND ouverture IS NOT NULL")[0][0] == 0
    unique = un(con, "SELECT \"date\", recurrent_annuel FROM fermetures WHERE \"date\" = '2026-08-26'")
    assert [tuple(r) for r in unique] == [("2026-08-26", 0)]


def test_le_seed_refuse_une_base_deja_remplie(base_reelle):
    con, _ = base_reelle
    with pytest.raises(seed.DejaInitialisee):
        seed.importer(con, CLASSEUR)


def test_cli_init_est_idempotent(tmp_path, capsys):
    chemin = str(tmp_path / "cli.db")
    assert cli.main(["init", "--db", chemin, "--xlsx", str(CLASSEUR)]) == 0
    assert "lieux 57 (9 vérifiés)" in capsys.readouterr().out
    assert cli.main(["init", "--db", chemin, "--xlsx", str(CLASSEUR)]) == 0
    assert "Déjà initialisée" in capsys.readouterr().out
    con = db.connect(chemin)
    assert un(con, "SELECT COUNT(*) FROM lieux")[0][0] == 57
    con.close()


# --- cas limites du classeur --------------------------------------------------

def test_lignes_de_legende_ignorees(classeur_minimal, con):
    chemin = classeur_minimal(
        Familles=[FAMILLE, ligne("Familles", famille_id="Vérifie ces lignes une seule fois.")],
        Lieux=[LIEU],
        Tarifs=[ligne("Tarifs", lieu_id="Une ligne = un droit d'accès."), [None] * 11],
    )
    rapport = seed.importer(con, chemin)
    assert rapport.comptes["Familles"] == 1 and rapport.comptes["Tarifs"] == 0
    assert rapport.legendes_ignorees == 2


def test_types_excel_convertis(classeur_minimal, con):
    chemin = classeur_minimal(
        Familles=[FAMILLE],
        Lieux=[LIEU],
        Horaires=[ligne("Horaires", lieu_id="musee-test", jour_num=2.0, jour="mardi", ferme="non",
                        ouverture=time(10, 0), fermeture=time(18, 0), nocturne="non", portee="tout",
                        derniere_entree_min=45.0, valide_au=datetime(2026, 10, 14))],
        Tarifs=[ligne("Tarifs", lieu_id="musee-test", portee="temporaire", regime="reduit",
                      audience="tous", prix=7.5, plein_tarif=15.0, recurrence="toujours")],
    )
    seed.importer(con, chemin)
    h = con.execute("SELECT * FROM horaires").fetchone()
    assert (h["jour_num"], h["ouverture"], h["fermeture"], h["valide_au"], h["derniere_entree_min"]) \
        == (2, "10:00", "18:00", "2026-10-14", 45)
    t = con.execute("SELECT prix, plein_tarif FROM tarifs").fetchone()
    assert (t["prix"], t["plein_tarif"]) == (7.5, 15)


def test_toutes_les_erreurs_sont_rapportees_et_rien_n_est_ecrit(classeur_minimal, con):
    chemin = classeur_minimal(
        Familles=[FAMILLE],
        Lieux=[LIEU,
               ligne("Lieux", id="autre", nom="Autre", famille="inconnue", confiance_famille="sûr"),
               ligne("Lieux", id="sans-date", nom="Sans date", famille="paris_musees",
                     confiance_famille="sûr", statut="vérifié")],
        Tarifs=[
            ligne("Tarifs", lieu_id="musee-test", portee="tout", regime="gratuit", audience="martiens",
                  prix=0, recurrence="toujours"),
            ligne("Tarifs", lieu_id="musee-test", portee="tout", regime="gratuit", audience="tous",
                  recurrence="toujours"),                                   # gratuit sans prix explicite
            ligne("Tarifs", lieu_id="fantome", portee="tout", regime="reduit", audience="tous",
                  prix=5, recurrence="toujours"),                           # lieu inconnu
        ],
        Fermetures=[ligne("Fermetures", lieu_id="musee-test", date="2026-05-01", libelle="x",
                          recurrent_annuel="oui")],
    )
    with pytest.raises(seed.SeedError) as exc:
        seed.importer(con, chemin)
    texte = "\n".join(exc.value.erreurs)
    assert "Tarifs ligne 2 (musee-test) : audience" in texte
    assert "Tarifs ligne 3 (musee-test)" in texte and "prix de 0 explicite" in texte
    assert "Tarifs : lieu inconnu : fantome" in texte
    assert "Lieux ligne 4 (sans-date)" in texte and "date de vérification" in texte
    assert "Lieux (autre) : famille inconnue : inconnue" in texte
    assert "Fermetures ligne 2 (musee-test)" in texte and "MM-JJ" in texte
    assert db.est_vide(con)


def test_en_tete_renomme_ou_inconnu_refuse(classeur_minimal, con, tmp_path):
    from openpyxl import load_workbook
    chemin = classeur_minimal(Familles=[FAMILLE], Lieux=[LIEU])
    wb = load_workbook(chemin)
    wb["Lieux"]["B1"] = "nom_du_musee"
    wb["Tarifs"]["L1"] = "colonne_surprise"
    wb.save(chemin)
    with pytest.raises(seed.SeedError) as exc:
        seed.importer(con, chemin)
    texte = "\n".join(exc.value.erreurs)
    assert "Lieux : colonnes absentes : ['nom']" in texte
    assert "Lieux : colonnes inconnues : ['nom_du_musee']" in texte
    assert "Tarifs : colonnes inconnues : ['colonne_surprise']" in texte


def test_identifiant_de_lieu_en_double(classeur_minimal, con):
    chemin = classeur_minimal(Familles=[FAMILLE], Lieux=[LIEU, LIEU])
    with pytest.raises(seed.SeedError) as exc:
        seed.importer(con, chemin)
    assert any("identifiant en double : musee-test" in e for e in exc.value.erreurs)
