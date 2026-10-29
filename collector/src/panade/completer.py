"""`panade completer` : applique à la base ce que la découverte a trouvé sur le web.

`data/lieux_web.json` décrit, lieu par lieu, les pages officielles (expositions, tarifs,
horaires), l'état du site (maintenance, anti-robots, fermé pour travaux...) et un tier quand
la collecte doit rester manuelle. Le fichier est versionné : c'est la mémoire de la découverte.

Règle : on comble les trous, on ne réécrit pas ce qu'une personne a saisi. Un champ n'est
remplacé que s'il est vide, ou s'il figure dans `corriger` (valeur du classeur reconnue fausse).
Le statut d'un lieu (vérifié ou non) n'est jamais touché : vérifier reste un geste humain.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

CHAMPS = ("expos_url", "tarifs_url", "horaires_url", "tier")


def appliquer(con: sqlite3.Connection, chemin: str | Path) -> list[str]:
    donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    marque = f"[web {donnees.get('genere_le', '?')}]"
    changements = []
    with con:
        for lid, info in donnees["lieux"].items():
            lieu = con.execute("SELECT * FROM lieux WHERE id = ?", (lid,)).fetchone()
            if lieu is None:
                changements.append(f"{lid} : lieu inconnu de la base, ignoré")
                continue
            corriger = set(info.get("corriger", []))
            for champ in CHAMPS:
                valeur = info.get(champ)
                if not valeur or valeur == lieu[champ]:
                    continue
                if lieu[champ] is None or champ in corriger:
                    con.execute(f"UPDATE lieux SET {champ} = ? WHERE id = ?", (valeur, lid))
                    changements.append(f"{lid} : {champ} = {valeur}" + (f" (au lieu de {lieu[champ]})" if lieu[champ] else ""))
            etat, note = info.get("etat_web"), info.get("note")
            texte = " ; ".join(x for x in (f"état du site : {etat}" if etat and etat != "ok" else None, note) if x)
            if texte and marque not in (lieu["notes_crawler"] or ""):
                ajout = f"{marque} {texte}"
                con.execute("UPDATE lieux SET notes_crawler = CASE WHEN notes_crawler IS NULL THEN ? "
                            "ELSE notes_crawler || ' | ' || ? END WHERE id = ?", (ajout, ajout, lid))
                changements.append(f"{lid} : note ajoutée")
    return changements
