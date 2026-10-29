"""`panade completer` : applique à la base ce que la découverte a trouvé sur le web.

`data/lieux_web.json` décrit, lieu par lieu, les pages officielles (expositions, tarifs,
horaires), l'état du site (maintenance, anti-robots, fermé pour travaux...) et un tier quand
la collecte doit rester manuelle. Le fichier est versionné : c'est la mémoire de la découverte.

Règle : on comble les trous, on ne réécrit pas ce qu'une personne a saisi. Un champ n'est
remplacé que s'il est vide, ou s'il figure dans `corriger` (valeur du classeur reconnue fausse).

Le fichier porte aussi des lignes de tarifs lues sur les pages officielles (avec leur source et
leur date), ajoutées seulement si le lieu n'a pas déjà la même ligne, et une vérification
(`verification`) qui ne fait jamais que faire passer un lieu de « à vérifier » à « vérifié » :
elle ne rétrograde rien et ne réécrit pas une vérification existante. `verifie_par` dit qui a
lu les pages ; une personne peut toujours repasser derrière.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from panade import models

CHAMPS = ("expos_url", "tarifs_url", "horaires_url", "tier")


def appliquer(con: sqlite3.Connection, chemin: str | Path) -> list[str]:
    donnees = json.loads(Path(chemin).read_text(encoding="utf-8"))
    marque = f"[web {donnees.get('genere_le', '?')}]"
    changements = []
    with con:
        for fid, info in donnees.get("familles", {}).items():
            famille = con.execute("SELECT * FROM familles WHERE id = ?", (fid,)).fetchone()
            for champ in info.get("corriger", []):
                if famille is not None and info.get(champ) and famille[champ] != info[champ]:
                    con.execute(f"UPDATE familles SET {champ} = ?, source = ? WHERE id = ?",
                                (info[champ], info.get("source", famille["source"]), fid))
                    changements.append(f"famille {fid} : {champ} = {info[champ]}")
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
            for t in info.get("tarifs", []):
                ligne = models.Tarif(lieu_id=lid, **t)      # rejeté s'il n'est pas conforme
                deja = con.execute("SELECT 1 FROM tarifs WHERE lieu_id = ? AND portee = ? AND regime = ? AND audience = ? "
                                   "AND recurrence = ?", (lid, ligne.portee, ligne.regime, ligne.audience, ligne.recurrence)).fetchone()
                if not deja:
                    v = ligne.values()
                    con.execute(f"INSERT INTO tarifs ({', '.join(v)}) VALUES ({', '.join(':' + k for k in v)})", v)
                    changements.append(f"{lid} : tarif {ligne.portee}/{ligne.regime}/{ligne.audience}/{ligne.recurrence}")
            verif = info.get("verification")
            if verif and lieu["statut"] == "a_verifier":
                con.execute("UPDATE lieux SET statut = 'verifie', verifie_le = ?, verifie_par = ? WHERE id = ?",
                            (verif["verifie_le"], verif["verifie_par"], lid))
                changements.append(f"{lid} : vérifié ({verif['verifie_par']}, {verif['verifie_le']})")
            etat, note = info.get("etat_web"), info.get("note")
            texte = " ; ".join(x for x in (f"état du site : {etat}" if etat and etat != "ok" else None, note) if x)
            if texte and marque not in (lieu["notes_crawler"] or ""):
                ajout = f"{marque} {texte}"
                con.execute("UPDATE lieux SET notes_crawler = CASE WHEN notes_crawler IS NULL THEN ? "
                            "ELSE notes_crawler || ' | ' || ? END WHERE id = ?", (ajout, ajout, lid))
                changements.append(f"{lid} : note ajoutée")
    return changements
