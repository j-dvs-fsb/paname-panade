import re
import sqlite3
from typing import get_args

import pytest

from panade import db, models

TABLES = {"familles", "lieux", "tarifs", "horaires", "fermetures", "expositions", "runs"}


def ddl(con, table):
    return con.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[0]


def test_sept_tables_et_version(con):
    noms = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}
    assert noms == TABLES
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION


def test_init_schema_est_idempotent(con):
    assert db.init_schema(con) is False


def test_base_plus_recente_refusee(con):
    con.execute(f"PRAGMA user_version = {db.SCHEMA_VERSION + 1}")
    with pytest.raises(db.SchemaTropRecent):
        db.init_schema(con)


@pytest.mark.parametrize("table, colonne, litteral", [
    ("lieux", "tier", models.Tier),
    ("lieux", "statut", models.StatutLieu),
    ("lieux", "confiance_famille", models.ConfianceFamille),
    ("tarifs", "portee", models.Portee),
    ("tarifs", "regime", models.Regime),
    ("tarifs", "audience", models.Audience),
    ("horaires", "jour", models.Jour),
    ("horaires", "portee", models.Portee),
    ("expositions", "portee", models.PorteeExpo),
    ("expositions", "etat", models.EtatExpo),
])
def test_listes_fermees_identiques_au_modele(con, table, colonne, litteral):
    """Les CHECK de schema.sql et les Literal de models.py ne doivent pas diverger."""
    sql = ddl(con, table)
    ligne = re.search(rf"\b{colonne}\s+TEXT[^,]*?CHECK\s*\(\s*{colonne}\s+IN\s*\((.*?)\)\s*\)",
                      sql, re.S)
    dans_la_base = set(re.findall(r"'([^']+)'", ligne.group(1)))
    assert dans_la_base == set(get_args(litteral))


def lieu(con, **extra):
    con.execute("INSERT OR IGNORE INTO familles (id, libelle) VALUES ('f', 'F')")
    champs = {"id": "l", "nom": "L", "famille_id": "f", "confiance_famille": "sur", **extra}
    con.execute(f"INSERT INTO lieux ({', '.join(champs)}) VALUES ({', '.join('?' * len(champs))})",
                list(champs.values()))


def test_cle_etrangere_active(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO tarifs (lieu_id, portee, regime, audience, prix, recurrence) "
                    "VALUES ('fantome', 'tout', 'gratuit', 'tous', 0, 'toujours')")


@pytest.mark.parametrize("extra", [
    {"statut": "verifie"},                    # vérifié sans date
    {"tier": "T9"},
    {"expos_url": "A TROUVER"},               # pas une URL
    {"verifie_le": "19/09/2026"},
])
def test_lieu_invalide_refuse(con, extra):
    with pytest.raises(sqlite3.IntegrityError):
        lieu(con, **extra)


@pytest.mark.parametrize("regime, prix", [
    ("gratuit", None),   # un gratuit est un 0 explicite, jamais un prix absent
    ("gratuit", 5),
    ("reduit", 0),
])
def test_gratuite_jamais_devinee(con, regime, prix):
    lieu(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO tarifs (lieu_id, portee, regime, audience, prix, recurrence) "
                    "VALUES ('l', 'tout', ?, 'tous', ?, 'toujours')", (regime, prix))


def test_prix_inconnu_est_permis_pour_un_tarif_non_gratuit(con):
    lieu(con)
    con.execute("INSERT INTO tarifs (lieu_id, portee, regime, audience, prix, recurrence) "
                "VALUES ('l', 'temporaire', 'reduit', 'tous', NULL, 'toujours')")


@pytest.mark.parametrize("valeurs", [
    "1, 'lundi', 1, '10:00', NULL",     # fermé mais avec des heures
    "1, 'lundi', 0, NULL, NULL",        # ouvert sans heures
    "8, 'lundi', 1, NULL, NULL",        # jour_num hors 1..7
])
def test_horaire_incoherent_refuse(con, valeurs):
    lieu(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO horaires (lieu_id, jour_num, jour, ferme, ouverture, fermeture) "
                    f"VALUES ('l', {valeurs})")


@pytest.mark.parametrize("date, recurrent", [
    ("2026-05-01", 1), ("05-01", 0), ("13-45", 0), ("5-1", 1),
])
def test_fermeture_format_de_date(con, date, recurrent):
    lieu(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO fermetures (lieu_id, \"date\", libelle, recurrent_annuel) "
                    "VALUES ('l', ?, 'x', ?)", (date, recurrent))


def test_pas_de_publication_sans_confiance(con):
    lieu(con)
    base = "INSERT INTO expositions (lieu_id, titre, portee, source, etat, confiance) VALUES ('l', 't', 'temporaire', 's', ?, ?)"
    con.execute(base, ("en_revue", None))
    con.execute(base, ("publie", 0.9))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(base, ("publie", None))


def test_expo_dates_inversees_refusees(con):
    lieu(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO expositions (lieu_id, titre, portee, source, date_debut, date_fin) "
                    "VALUES ('l', 't', 'temporaire', 's', '2026-10-02', '2026-10-01')")


@pytest.mark.parametrize("table, colonne", [
    ("lieux", "verifie_le"), ("tarifs", "verifie_le"), ("horaires", "valide_du"),
    ("horaires", "valide_au"), ("expositions", "date_debut"), ("expositions", "date_fin"),
    ("expositions", "vu_le"),
])
def test_date_illisible_refusee_dans_chaque_colonne(con, table, colonne):
    """date(x) = x vaut NULL pour une date illisible, et un CHECK NULL laisse passer."""
    lieu(con)
    base = {
        "lieux": ("id, nom, famille_id, confiance_famille", "'l2', 'L2', 'f', 'sur'"),
        "tarifs": ("lieu_id, portee, regime, audience, prix, recurrence", "'l', 'tout', 'gratuit', 'tous', 0, 'toujours'"),
        "horaires": ("lieu_id, jour_num, jour, ferme", "'l', 1, 'lundi', 1"),
        "expositions": ("lieu_id, titre, portee, source", "'l', 't', 'temporaire', 's'"),
    }[table]
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(f"INSERT INTO {table} ({base[0]}, {colonne}) VALUES ({base[1]}, '19/09/2026')")


@pytest.mark.parametrize("ouverture", ["29:00", "10:75", "9:00", "10h00"])
def test_heure_impossible_refusee(con, ouverture):
    lieu(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO horaires (lieu_id, jour_num, jour, ferme, ouverture, fermeture) "
                    "VALUES ('l', 1, 'lundi', 0, ?, '18:00')", (ouverture,))


def test_fermeture_annuelle_29_fevrier_permise_30_fevrier_refuse(con):
    lieu(con)
    insert = ("INSERT INTO fermetures (lieu_id, \"date\", libelle, recurrent_annuel) "
              "VALUES ('l', ?, 'x', 1)")
    con.execute(insert, ("02-29",))
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(insert, ("02-30",))


# --- migration v1 -> v2 ------------------------------------------------------------

def colonnes(con, table):
    return {(c["name"], c["type"], c["notnull"]) for c in con.execute(f"PRAGMA table_info({table})")}


def test_migration_v1_vers_v2_donne_le_meme_schema_et_garde_les_donnees(tmp_path):
    from conftest import FIXTURES
    ancienne = db.connect(tmp_path / "v1.db")
    ancienne.executescript((FIXTURES / "schema_v1.sql").read_text(encoding="utf-8"))
    assert ancienne.execute("PRAGMA user_version").fetchone()[0] == 1
    ancienne.execute("INSERT INTO familles (id, libelle) VALUES ('f', 'F')")
    ancienne.execute("INSERT INTO lieux (id, nom, famille_id, confiance_famille) VALUES ('l', 'L', 'f', 'sur')")
    ancienne.execute("INSERT INTO expositions (lieu_id, titre, portee, source) VALUES ('l', 'T', 'temporaire', 's')")
    ancienne.commit()

    assert db.init_schema(ancienne) is True
    neuve = db.connect(tmp_path / "v2.db")
    db.init_schema(neuve)
    assert ancienne.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    for table in TABLES:
        assert colonnes(ancienne, table) == colonnes(neuve, table), table
    assert ancienne.execute("SELECT titre, provenance, motif_revue FROM expositions").fetchone()[:] == ("T", None, None)
    assert db.init_schema(ancienne) is False      # rejouée : rien à faire
    with pytest.raises(sqlite3.IntegrityError):    # la nouvelle table runs a bien son CHECK
        ancienne.execute("INSERT INTO runs (lieu_id, demarre_le, statut) VALUES ('l', '2026-10-30T03:00:00Z', 'bizarre')")
    ancienne.close()
    neuve.close()


def test_runs_refuse_une_date_illisible(con):
    lieu(con)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO runs (lieu_id, demarre_le, statut) VALUES ('l', 'hier soir', 'ok')")
    con.execute("INSERT INTO runs (lieu_id, demarre_le, statut) VALUES ('l', '2026-10-30T03:00:05Z', 'ok')")
