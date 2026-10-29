"""`panade validate` : conformité, cohérence, dédoublonnage, confiance, gratuité.

Rien n'est « rattrapé » : une exposition non conforme est bloquée en `en_revue` avec son
motif, pas corrigée. Seule une personne publie ce que la machine n'est pas sûre de lire.

Ordre : 1. conformité  2. doublons  3. confiance  4. gratuité (garde-fou 3)  5. promotion.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher

from pydantic import ValidationError

from panade import gratuite, models

SEUIL_PAR_DEFAUT = 0.8
FENETRE_ANNEES = 3

# D'où vient une valeur -> à quel point on s'y fie. Les extracteurs déclarent la provenance,
# la confiance se décide ici, à un seul endroit.
CONFIANCE_PROVENANCE = {
    "time": 1.0,                      # <time datetime> : lisible par une machine
    "carte": 1.0, "fiche": 0.9,
    "og:image": 1.0, "og:description": 1.0,
    "texte_fr": 0.9,                  # « 15 septembre 2026 - 24 janvier 2027 » : année écrite
    "texte_fr_annee_deduite": 0.6,    # année absente, déduite de la date du jour
    "absente": 0.0,
    "incertaine": 0.5,                # portée (permanent ou temporaire) que la page ne tranche pas
    "humain": 1.0,
}


@dataclass
class Rapport:
    verifiees: int = 0
    promues: int = 0
    bloquees: int = 0
    doublons: int = 0
    gratuite_changee: int = 0
    perimes: list[str] = field(default_factory=list)
    problemes_graves: list[str] = field(default_factory=list)   # ce qui empêcherait publish
    motifs: dict[int, str] = field(default_factory=dict)


def seuil() -> float:
    return float(os.environ.get("PANADE_SEUIL_CONFIANCE", SEUIL_PAR_DEFAUT))


def confiance(expo: sqlite3.Row | dict) -> tuple[float | None, str | None]:
    """(score, champ le plus faible). None si l'exposition n'a pas de provenance (importée du classeur)."""
    provenance = json.loads(expo["provenance"] or "{}")
    if not provenance:
        return None, None
    if provenance.get("relu") == "humain":
        return 1.0, None      # une personne a relu et publié : la machine ne revient pas dessus
    scores = {"titre": CONFIANCE_PROVENANCE.get(provenance.get("titre"), 0.0)}
    if expo["url"]:
        scores["url"] = CONFIANCE_PROVENANCE.get(provenance.get("url"), 0.0)
    dates = [CONFIANCE_PROVENANCE.get(provenance.get(c), 0.0) for c in ("date_debut", "date_fin") if expo[c]]
    # Une seule borne connue : exposition « ouverte » ou date de fin manquante, on ne tranche pas seul.
    scores["dates"] = 0.0 if not dates else min(dates) if len(dates) == 2 else min(dates[0], 0.6)
    if "portee" in provenance:
        scores["portée"] = CONFIANCE_PROVENANCE.get(provenance["portee"], 0.0)
    faible = min(scores, key=scores.get)
    return scores[faible], faible


def _normaliser(titre: str) -> str:
    sans_accent = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sans_accent.lower()).strip()


def _memes_dates(a, b) -> bool:
    return all(x is None or y is None or x == y for x, y in ((a["date_debut"], b["date_debut"]), (a["date_fin"], b["date_fin"])))


def _doublons(a, b) -> bool:
    if a["lieu_id"] != b["lieu_id"] or a["portee"] != b["portee"] or not _memes_dates(a, b):
        return False
    if a["url"] and a["url"] == b["url"]:
        return True
    ta, tb = _normaliser(a["titre"]), _normaliser(b["titre"])
    if re.findall(r"\d+", ta) != re.findall(r"\d+", tb):
        return False       # « Nocturne 1 » et « Nocturne 2 » ne sont pas la même exposition
    return ta == tb or SequenceMatcher(None, ta, tb).ratio() >= 0.88


def valider(con: sqlite3.Connection, aujourdhui: date, *, seuil_confiance: float | None = None) -> Rapport:
    seuil_confiance = seuil() if seuil_confiance is None else seuil_confiance
    rapport = Rapport()
    with con:
        _integrite(con, rapport)
        _perimes(con, aujourdhui, rapport)
        _conformite(con, aujourdhui, rapport)
        _dedoublonner(con, rapport)
        _confiance_gratuite_et_promotion(con, aujourdhui, seuil_confiance, rapport)
    return rapport


def _bloquer(con, expo_id: int, motif: str, rapport: Rapport) -> None:
    avant = con.execute("SELECT etat, motif_revue FROM expositions WHERE id = ?", (expo_id,)).fetchone()
    con.execute("UPDATE expositions SET etat = 'en_revue', motif_revue = ? WHERE id = ?", (motif, expo_id))
    rapport.motifs[expo_id] = motif
    if (avant["etat"], avant["motif_revue"]) != ("en_revue", motif):    # un re-passage identique ne compte pas
        rapport.bloquees += 1


def _integrite(con, rapport: Rapport) -> None:
    if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        rapport.problemes_graves.append("la base SQLite est corrompue (integrity_check)")
    for violation in con.execute("PRAGMA foreign_key_check").fetchall():
        rapport.problemes_graves.append(f"clé étrangère violée : {tuple(violation)}")


def _perimes(con, aujourdhui: date, rapport: Rapport) -> None:
    """Invariant 5 : une donnée vérifiée il y a plus de 120 jours est signalée périmée."""
    limite = (aujourdhui - timedelta(days=gratuite.PEREMPTION_JOURS)).isoformat()
    for r in con.execute("SELECT id, verifie_le FROM lieux WHERE statut = 'verifie' AND verifie_le < ?", (limite,)):
        rapport.perimes.append(f"lieu {r['id']} : vérifié le {r['verifie_le']}")
    for r in con.execute("SELECT lieu_id, MIN(verifie_le) AS le, COUNT(*) AS n FROM tarifs WHERE verifie_le < ? GROUP BY lieu_id", (limite,)):
        rapport.perimes.append(f"tarifs de {r['lieu_id']} : {r['n']} ligne(s), la plus ancienne vérifiée le {r['le']}")


def _conformite(con, aujourdhui: date, rapport: Rapport) -> None:
    """Schéma pydantic strict, puis dates plausibles (à moins de 3 ans)."""
    bas = aujourdhui.replace(year=aujourdhui.year - FENETRE_ANNEES).isoformat()
    haut = aujourdhui.replace(year=aujourdhui.year + FENETRE_ANNEES).isoformat()
    champs = list(models.Exposition.model_fields)
    for expo in con.execute("SELECT * FROM expositions WHERE etat <> 'rejete'").fetchall():
        rapport.verifiees += 1
        probleme = None
        try:
            models.Exposition(**{c: expo[c] for c in champs})
        except ValidationError as exc:
            probleme = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'ligne'} : {e['msg']}" for e in exc.errors())
        else:
            for c in ("date_debut", "date_fin"):
                if expo[c] and not bas <= expo[c] <= haut:
                    probleme = f"{c} {expo[c]} hors de la fenêtre de {FENETRE_ANNEES} ans"
        if probleme:
            _bloquer(con, expo["id"], f"non conforme : {probleme}", rapport)


def _dedoublonner(con, rapport: Rapport) -> None:
    """Les trois `chaillot-experience` du site actuel : même lieu, titre voisin, dates compatibles."""
    lignes = con.execute("SELECT * FROM expositions WHERE etat <> 'rejete' ORDER BY lieu_id, id").fetchall()
    traitees: set[int] = set()
    for i, a in enumerate(lignes):
        if a["id"] in traitees:
            continue
        groupe = [a] + [b for b in lignes[i + 1:] if b["id"] not in traitees and _doublons(a, b)]
        if len(groupe) == 1:
            continue
        # on garde la plus avancée : déjà publiée, puis la plus sûre, puis la plus complète, puis la plus ancienne
        groupe.sort(key=lambda e: (e["etat"] != "publie", -(e["confiance"] or 0),
                                   -sum(e[c] is not None for c in ("description", "image_url", "url", "date_debut", "date_fin")), e["id"]))
        garde, autres = groupe[0], groupe[1:]
        for autre in autres:
            for c in ("description", "image_url", "url", "date_debut", "date_fin"):
                if garde[c] is None and autre[c] is not None:
                    con.execute(f"UPDATE expositions SET {c} = ? WHERE id = ?", (autre[c], garde["id"]))
            con.execute("UPDATE expositions SET etat = 'rejete', motif_revue = ? WHERE id = ?",
                        (f"doublon de l'exposition {garde['id']}", autre["id"]))
            traitees.add(autre["id"])
            rapport.doublons += 1


def _confiance_gratuite_et_promotion(con, aujourdhui: date, seuil_confiance: float, rapport: Rapport) -> None:
    caches: dict[str, gratuite.Lieu] = {}
    for expo in con.execute("SELECT * FROM expositions WHERE etat <> 'rejete' ORDER BY id").fetchall():
        score, faible = confiance(expo)
        lieu = caches.setdefault(expo["lieu_id"], gratuite.charger(con, expo["lieu_id"]))
        calculee = gratuite.calculer(lieu, expo["portee"], aujourdhui).en_json()
        con.execute("UPDATE expositions SET confiance = ?, gratuite_calculee = ? WHERE id = ?", (score, calculee, expo["id"]))
        etat, motif, validee = expo["etat"], expo["motif_revue"], expo["gratuite_validee"]

        # Garde-fou 3 : la gratuité a changé depuis la dernière relecture ou publication.
        if etat == "publie" and validee is not None and validee != calculee:
            avant, apres = json.loads(validee)["statut"], json.loads(calculee)["statut"]
            _bloquer(con, expo["id"], f"gratuité modifiée sans relecture : {avant} → {apres}", rapport)
            rapport.gratuite_changee += 1
            continue
        if etat == "publie" and validee is None:
            con.execute("UPDATE expositions SET gratuite_validee = ? WHERE id = ?", (calculee, expo["id"]))

        if score is None:
            if etat == "en_revue" and motif is None:
                con.execute("UPDATE expositions SET motif_revue = 'importée du classeur, jamais relue' WHERE id = ?", (expo["id"],))
            continue
        if score < seuil_confiance:
            if etat == "publie" or motif is None or motif.startswith("confiance"):
                _bloquer(con, expo["id"], f"confiance {score:.2f} sous le seuil {seuil_confiance:.2f} ({faible})", rapport)
            continue
        if etat == "en_revue" and motif is None:
            # Nouvelle exposition lue de façon sûre : elle peut partir. Sa gratuité calculée devient la référence.
            con.execute("UPDATE expositions SET etat = 'publie', gratuite_validee = ? WHERE id = ?", (calculee, expo["id"]))
            rapport.promues += 1
        elif etat == "en_revue" and motif.startswith("confiance"):
            con.execute("UPDATE expositions SET motif_revue = NULL WHERE id = ?", (expo["id"],))   # remontée au-dessus du seuil
