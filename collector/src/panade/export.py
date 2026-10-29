"""`panade export` : produit l'export du jour. Ne publie rien.

Le site ne connaît que ce fichier. Il contient uniquement des expositions `publie` et des
lieux `verifie`, et aucun champ vide : pas de `null`, pas de chaîne vide, pas de
`/exposition/None`. Les clés absentes sont omises (invariant 2).

La gratuité est recalculée ici, pas relue dans la base : si elle diffère de celle qu'une
personne a relue (ou que la machine a publiée), l'exposition sort de l'export et repart
en relecture (garde-fou 3).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from panade import gratuite

VERSION_FORMAT = 1
LIBELLES = {
    "gratuit_tous": "Gratuit", "gratuit_26": "Gratuit pour les moins de 26 ans",
    "reduit_26": "Tarif réduit pour les moins de 26 ans", "payant": "Payant", "a_confirmer": "À confirmer sur place",
}


@dataclass
class Export:
    contenu: dict
    exclues: list[tuple[int, str]] = field(default_factory=list)    # (id d'expo, motif) sorties par garde-fou 3
    lieux_sans_expo: list[str] = field(default_factory=list)


def typo(texte: str | None) -> str | None:
    """Typographie du site : pas de tiret long ni moyen, un trait d'union à la place."""
    if not texte:
        return texte
    for long_, court in ((" \u2014 ", " - "), (" \u2013 ", " - "), ("\u2014", "-"), ("\u2013", "-")):
        texte = texte.replace(long_, court)
    return texte


def epurer(valeur):
    """Retire récursivement None, chaînes vides et conteneurs vides."""
    if isinstance(valeur, dict):
        propre = {k: epurer(v) for k, v in valeur.items()}
        return {k: v for k, v in propre.items() if v is not None and v != "" and v != [] and v != {}}
    if isinstance(valeur, list):
        return [v for v in (epurer(x) for x in valeur) if v is not None and v != "" and v != {}]
    return valeur


def a_des_champs_vides(valeur) -> bool:
    if isinstance(valeur, dict):
        return any(v is None or v == "" or a_des_champs_vides(v) for v in valeur.values())
    if isinstance(valeur, list):
        return any(v is None or v == "" or a_des_champs_vides(v) for v in valeur)
    return False


def empreinte(contenu: dict) -> str:
    sans = {k: v for k, v in contenu.items() if k != "empreinte"}
    return hashlib.sha256(json.dumps(sans, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _gratuite_publique(brut: str) -> dict:
    g = json.loads(brut)
    return {"categorie": g["statut"], "libelle": LIBELLES[g["statut"]], "prix": g.get("prix"),
            "plein_tarif": g.get("plein_tarif"), "audience": g.get("audience"),
            "justificatif": g.get("justificatif"),
            "creneaux": [{"audience": c["audience"], "regime": c["regime"], "prix": c.get("prix"), "recurrence": c["recurrence"]}
                         for c in g.get("creneaux", [])]}


def construire(con: sqlite3.Connection, aujourdhui: date, maintenant: datetime | None = None) -> Export:
    maintenant = maintenant or datetime.now(timezone.utc)
    limite_peremption = (aujourdhui - timedelta(days=gratuite.PEREMPTION_JOURS)).isoformat()
    lieux, exclues = [], []
    total_expos = 0
    sans_expo = []
    for lieu in con.execute("SELECT * FROM lieux WHERE statut = 'verifie' ORDER BY id").fetchall():
        regles = gratuite.charger(con, lieu["id"])
        expos = []
        candidates = con.execute(
            "SELECT * FROM expositions WHERE lieu_id = ? AND etat = 'publie' AND (date_fin IS NULL OR date_fin >= ?) "
            "ORDER BY COALESCE(date_debut, '0000'), id", (lieu["id"], aujourdhui.isoformat())).fetchall()
        for e in candidates:
            fraiche = gratuite.calculer(regles, e["portee"], aujourdhui).en_json()
            if e["gratuite_validee"] != fraiche:
                motif = ("gratuité jamais relue" if e["gratuite_validee"] is None else
                         f"gratuité modifiée sans relecture : {json.loads(e['gratuite_validee'])['statut']} → {json.loads(fraiche)['statut']}")
                with con:
                    con.execute("UPDATE expositions SET etat = 'en_revue', motif_revue = ?, gratuite_calculee = ? WHERE id = ?",
                                (motif, fraiche, e["id"]))
                exclues.append((e["id"], motif))
                continue
            expos.append({
                "id": e["id"], "titre": typo(e["titre"]), "portee": e["portee"], "date_debut": e["date_debut"],
                "date_fin": e["date_fin"], "description": typo(e["description"]), "url": e["url"],
                # une collection permanente n'a pas d'affiche : on prend le logo du lieu
                "image_url": e["image_url"] or (lieu["logo_url"] if e["portee"] == "permanent" else None),
                "gratuite": _gratuite_publique(fraiche)})
        if not expos:
            sans_expo.append(lieu["id"])
        total_expos += len(expos)
        tarifs = [dict(t) for t in con.execute(
            "SELECT portee, regime, audience, prix, plein_tarif, recurrence, justificatif, source_url, verifie_le "
            "FROM tarifs WHERE lieu_id = ? AND verifie_le IS NOT NULL ORDER BY id", (lieu["id"],))]
        for t in tarifs:
            t["perime"] = True if t["verifie_le"] < limite_peremption else None
        horaires = [{**dict(h), "ferme": bool(h["ferme"]), "nocturne": bool(h["nocturne"])} for h in con.execute(
            "SELECT jour_num, jour, ferme, ouverture, fermeture, nocturne, portee, derniere_entree_min, valide_du, valide_au, note "
            "FROM horaires WHERE lieu_id = ? ORDER BY jour_num, nocturne, id", (lieu["id"],))]
        fermetures = [{**dict(f), "recurrent_annuel": bool(f["recurrent_annuel"])} for f in con.execute(
            'SELECT "date", libelle, recurrent_annuel, note FROM fermetures WHERE lieu_id = ? ORDER BY recurrent_annuel DESC, "date"',
            (lieu["id"],))]
        lieux.append({
            "id": lieu["id"], "nom": typo(lieu["nom"]), "famille": lieu["famille_id"], "logo_url": lieu["logo_url"],
            "tarifs_url": lieu["tarifs_url"], "horaires_url": lieu["horaires_url"], "expos_url": lieu["expos_url"],
            "plateforme_billetterie": lieu["plateforme_billetterie"], "verifie_le": lieu["verifie_le"],
            "perime": True if lieu["verifie_le"] < limite_peremption else None,
            "tarifs": tarifs, "horaires": horaires, "fermetures": fermetures, "expositions": expos})

    contenu = epurer({
        "version": VERSION_FORMAT, "genere_le": maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "compte": {"lieux": len(lieux), "expositions": total_expos}, "lieux": lieux})
    contenu["empreinte"] = empreinte(contenu)
    return Export(contenu, exclues, sans_expo)


def ecrire(export: Export, dossier: str | Path, maintenant: datetime | None = None) -> Path:
    """Écrit le fichier de façon atomique (écriture dans un fichier voisin puis renommage)."""
    maintenant = maintenant or datetime.now(timezone.utc)
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"export-{maintenant.strftime('%Y-%m-%dT%H-%M-%SZ')}.json"
    temporaire = chemin.with_suffix(".tmp")
    temporaire.write_text(json.dumps(export.contenu, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    temporaire.replace(chemin)
    return chemin


def lire(chemin: str | Path) -> dict:
    contenu = json.loads(Path(chemin).read_text(encoding="utf-8"))
    if contenu.get("empreinte") != empreinte(contenu):
        raise ValueError(f"{chemin} : empreinte invalide, le fichier est incomplet ou modifié")
    return contenu


def expos_attendues(precedent: dict, aujourdhui: date) -> dict[str, list[dict]]:
    """Expositions de l'export précédent qui devraient encore figurer aujourd'hui (non terminées)."""
    sortie: dict[str, list[dict]] = {}
    for lieu in precedent.get("lieux", []):
        vivantes = [e for e in lieu.get("expositions", []) if e.get("date_fin", "9999") >= aujourdhui.isoformat()]
        if vivantes:
            sortie[lieu["id"]] = vivantes
    return sortie
