"""`panade health` : ce qui ne tourne plus, ce qui est périmé.

Sans ce contrôle, un extracteur cassé passe inaperçu des semaines : le site continue de
tourner avec de vieilles données et personne ne le voit.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from panade import extractors, gratuite, validate

ECHECS = ("erreur", "vide", "interdit")
NUITS_MUET = 2                 # « un lieu silencieux deux nuits de suite déclenche une alerte »
PUBLICATION_MAX_JOURS = 2


@dataclass
class Muet:
    lieu: str
    nuits: int                    # nuits d'échec consécutives (ou jours sans passage)
    genre: str                    # indisponible | casse | interdit | silencieux
    derniere_reussite: str | None
    detail: str

    @property
    def message(self) -> str:
        depuis = f", dernière lecture réussie le {self.derniere_reussite}" if self.derniere_reussite else ", jamais lu avec succès"
        return f"{self.lieu} muet depuis {self.nuits} nuit(s) ({self.genre}{depuis}) : {self.detail}"


def _lieux_collectes(con):
    return [l for l in con.execute("SELECT * FROM lieux ORDER BY id") if extractors.choisir(l)]


def lieux_muets(con: sqlite3.Connection, aujourdhui: date) -> list[Muet]:
    muets = []
    for lieu in _lieux_collectes(con):
        runs = con.execute("SELECT * FROM runs WHERE lieu_id = ? ORDER BY id DESC LIMIT 60", (lieu["id"],)).fetchall()
        if not runs:
            continue       # jamais collecté : relève de l'inventaire, pas du silence
        reussite = next((r for r in runs if r["statut"] in ("ok", "inchange")), None)
        jours_echec: set[str] = set()
        for r in runs:
            if r["statut"] not in ECHECS:
                break
            jours_echec.add(r["demarre_le"][:10])
        dernier = runs[0]
        sans_passage = (aujourdhui - date.fromisoformat(dernier["demarre_le"][:10])).days
        deja_trouve = con.execute("SELECT 1 FROM runs WHERE lieu_id = ? AND statut = 'ok' AND items_trouves > 0",
                                  (lieu["id"],)).fetchone() is not None
        if all(r["statut"] == "vide" for r in runs[:len(jours_echec) or 1]) and not deja_trouve:
            continue      # page lue, aucune exposition, et il n'y en a jamais eu : rien d'anormal
        if len(jours_echec) >= NUITS_MUET:
            genre = {"vide": "casse", "interdit": "interdit"}.get(dernier["statut"], "indisponible")
            muets.append(Muet(lieu["id"], len(jours_echec), genre, reussite["demarre_le"][:10] if reussite else None,
                              dernier["erreur"] or dernier["statut"]))
        elif sans_passage >= NUITS_MUET:
            muets.append(Muet(lieu["id"], sans_passage, "silencieux", reussite["demarre_le"][:10] if reussite else None,
                              f"aucun passage de collect depuis le {dernier['demarre_le'][:10]}"))
    return muets


def extracteurs_casses(con: sqlite3.Connection) -> list[dict]:
    """Page lue mais plus rien d'extrait, alors qu'elle donnait des expositions avant : site refait ?"""
    casses = []
    for lieu in _lieux_collectes(con):
        dernier = con.execute("SELECT statut, demarre_le FROM runs WHERE lieu_id = ? ORDER BY id DESC LIMIT 1", (lieu["id"],)).fetchone()
        if not dernier or dernier["statut"] != "vide":
            continue
        avant = con.execute("SELECT demarre_le, items_trouves FROM runs WHERE lieu_id = ? AND statut = 'ok' AND items_trouves > 0 "
                            "ORDER BY id DESC LIMIT 1", (lieu["id"],)).fetchone()
        if avant is None:
            continue      # jamais rien trouvé : un musée sans exposition en cours, pas un extracteur cassé
        casses.append({"lieu": lieu["id"], "depuis": dernier["demarre_le"][:10],
                       "dernier_succes": avant["demarre_le"][:10] if avant else None,
                       "reparation": f"panade discover {lieu['id']}"})
    return casses


def sans_extracteur(con: sqlite3.Connection) -> list[dict]:
    """Les lieux vérifiés qu'aucun extracteur ne couvre : à faire à la main ou à écrire."""
    sortie = []
    for lieu in con.execute("SELECT * FROM lieux WHERE statut = 'verifie' ORDER BY id"):
        if extractors.choisir(lieu) is None:
            raison = "T4, collecte manuelle" if lieu["tier"] == "T4" else \
                "page des expositions à découvrir" if lieu["famille_id"] == "paris_musees" else "aucun extracteur"
            sortie.append({"lieu": lieu["id"], "raison": raison})
    return sortie


def donnees_perimees(con: sqlite3.Connection, aujourdhui: date) -> dict:
    rapport = validate.Rapport()
    validate._perimes(con, aujourdhui, rapport)
    horaires = [dict(r) for r in con.execute(
        "SELECT lieu_id, MIN(valide_au) AS jusqu_au FROM horaires WHERE valide_au < ? GROUP BY lieu_id", (aujourdhui.isoformat(),))]
    return {"verifications": rapport.perimes, "horaires_expires": horaires}


def publication(dossier: str | Path, aujourdhui: date) -> dict:
    chemin = Path(dossier) / "publie" / "derniere.json"
    if not chemin.exists():
        return {"derniere": None, "jours": None}
    try:
        genere = json.loads(chemin.read_text(encoding="utf-8"))["genere_le"][:10]
    except (ValueError, KeyError):
        return {"derniere": "illisible", "jours": None}
    return {"derniere": genere, "jours": (aujourdhui - date.fromisoformat(genere)).days}


def rapport(con: sqlite3.Connection, aujourdhui: date, dossier: str | Path = "data") -> dict:
    muets = lieux_muets(con, aujourdhui)
    casses = extracteurs_casses(con)
    pub = publication(dossier, aujourdhui)
    en_revue = con.execute("SELECT COUNT(*) AS n, MIN(vu_le) AS plus_ancienne FROM expositions WHERE etat = 'en_revue'").fetchone()
    alertes = [m.message for m in muets] + [f"extracteur cassé : {c['lieu']} (réparer : {c['reparation']})" for c in casses]
    if pub["jours"] is not None and pub["jours"] > PUBLICATION_MAX_JOURS:
        alertes.append(f"aucune publication depuis {pub['jours']} jours (dernière : {pub['derniere']})")
    if pub["derniere"] is None:
        alertes.append("le site n'a encore reçu aucune publication")
    return {
        "date": aujourdhui.isoformat(), "alertes": alertes,
        "muets": [asdict(m) for m in muets], "extracteurs_casses": casses,
        "perimees": donnees_perimees(con, aujourdhui), "sans_extracteur": sans_extracteur(con),
        "relecture": {"en_attente": en_revue["n"], "plus_ancienne_vue": en_revue["plus_ancienne"]},
        "publication": pub,
        "lieux": dict(con.execute("SELECT statut, COUNT(*) FROM lieux GROUP BY statut").fetchall()),
    }


def alerte_du_soir(muet: Muet) -> bool:
    """On alerte au passage à deux nuits, puis chaque semaine : pas de rappel quotidien qui lasse."""
    return muet.nuits == NUITS_MUET or (muet.nuits > NUITS_MUET and (muet.nuits - NUITS_MUET) % 7 == 0)
