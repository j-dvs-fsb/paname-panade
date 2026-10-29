"""Connexion SQLite et création du schéma."""
from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

SCHEMA_VERSION = 1


class SchemaTropRecent(RuntimeError):
    """La base a été créée par une version plus récente du collecteur."""


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    # Désactivées par défaut dans SQLite : sans ça, les clés étrangères ne servent à rien.
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_schema(con: sqlite3.Connection) -> bool:
    """Crée les tables d'une base vierge. Renvoie False si elles existaient déjà."""
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise SchemaTropRecent(
            f"base en version {version}, ce collecteur ne connaît que la version {SCHEMA_VERSION}"
        )
    if version == SCHEMA_VERSION:
        return False
    # executescript valide la transaction en cours, puis exécute le fichier tel quel.
    con.executescript(resources.files("panade").joinpath("schema.sql").read_text(encoding="utf-8"))
    return True


def est_vide(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM lieux LIMIT 1").fetchone() is None
