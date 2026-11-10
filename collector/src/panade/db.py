"""Connexion SQLite et création du schéma."""
from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

SCHEMA_VERSION = 2

# Migrations successives : MIGRATIONS[n] fait passer de la version n à n+1.
# `runs` était vide en v1 (rien n'y écrivait) : on la recrée plutôt que de la modifier.
MIGRATIONS = {
    1: """
        ALTER TABLE expositions ADD COLUMN provenance TEXT;
        ALTER TABLE expositions ADD COLUMN motif_revue TEXT;
        ALTER TABLE expositions ADD COLUMN gratuite_validee TEXT;
        DROP INDEX idx_runs_lieu;
        DROP TABLE runs;
        CREATE TABLE runs (
            id             INTEGER PRIMARY KEY,
            lieu_id        TEXT NOT NULL REFERENCES lieux(id),
            demarre_le     TEXT NOT NULL CHECK (datetime(demarre_le) IS NOT NULL),
            duree_ms       INTEGER CHECK (duree_ms IS NULL OR duree_ms >= 0),
            statut         TEXT NOT NULL CHECK (statut IN ('ok', 'inchange', 'vide', 'erreur', 'interdit')),
            items_trouves  INTEGER CHECK (items_trouves IS NULL OR items_trouves >= 0),
            erreur         TEXT,
            url            TEXT,
            etag           TEXT,
            derniere_modif TEXT,
            hash_page      TEXT
        );
        CREATE INDEX idx_runs_lieu ON runs (lieu_id, demarre_le);
        PRAGMA user_version = 2;
    """,
}


class SchemaTropRecent(RuntimeError):
    """La base a été créée par une version plus récente du collecteur."""


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    # Désactivées par défaut dans SQLite : sans ça, les clés étrangères ne servent à rien.
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_schema(con: sqlite3.Connection) -> bool:
    """Crée les tables d'une base vierge ou la met à jour. Renvoie False si rien n'a changé."""
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise SchemaTropRecent(
            f"base en version {version}, ce collecteur ne connaît que la version {SCHEMA_VERSION}"
        )
    if version == SCHEMA_VERSION:
        return False
    if version == 0:
        # executescript valide la transaction en cours, puis exécute le fichier tel quel.
        con.executescript(resources.files("panade").joinpath("schema.sql").read_text(encoding="utf-8"))
        return True
    while version < SCHEMA_VERSION:
        con.executescript("BEGIN;" + MIGRATIONS[version] + "COMMIT;")
        version = con.execute("PRAGMA user_version").fetchone()[0]
    return True


def est_vide(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM lieux LIMIT 1").fetchone() is None
