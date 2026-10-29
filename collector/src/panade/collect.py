"""`panade collect` : fait tourner les extracteurs. Aucun appel de modèle.

Pour chaque lieu qui a un extracteur : une requête conditionnelle, une empreinte du
contenu de la page, l'extraction si la page a changé, une ligne dans `runs`
quoi qu'il arrive. Les règles de rangement protègent le travail humain :

  - une correction faite à la main (provenance « humain ») n'est jamais écrasée ;
  - une valeur absente de la page n'efface jamais une valeur connue ;
  - une exposition rejetée à la main ne revient jamais ;
  - une extraction vide ne dépublie rien : c'est l'extracteur qui est suspect, pas le musée.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from panade import extractors, html as h
from panade.extractors import ExpoBrute
from panade.http import AccesRefuse, ClientPoli, ErreurReseau, Verdict

CHAMPS_PAGE = ("titre", "date_debut", "date_fin", "description", "image_url", "url")
CHAMPS_CLES = ("titre", "date_debut", "date_fin")   # leur changement sur une expo publiée la renvoie en relecture


@dataclass
class Resultat:
    lieu: str
    statut: str            # ok | inchange | vide | erreur | interdit | sans_extracteur
    detail: str = ""
    items: int | None = None
    nouveaux: int = 0
    modifies: int = 0
    renvoyes_en_revue: int = 0


def empreinte(page_html: str) -> str:
    """Empreinte du contenu visible. Les jetons de formulaire et d'image changent à chaque
    chargement : on ne hache que le texte de la zone principale."""
    arbre = h.lire(page_html)
    zone = arbre.css_first("main") or arbre.body
    texte = re.sub(r"\s+", " ", zone.text(separator=" ")).strip() if zone else ""
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


def _hash_source(expo: ExpoBrute) -> str:
    contenu = json.dumps([getattr(expo, c) for c in CHAMPS_PAGE], ensure_ascii=False)
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()[:16]


def collecter(con: sqlite3.Connection, client: ClientPoli, *, maintenant=None, lieux_ids=None) -> list[Resultat]:
    maintenant = maintenant or (lambda: datetime.now(timezone.utc))
    requete = "SELECT * FROM lieux WHERE expos_url IS NOT NULL"
    params: list = []
    if lieux_ids:
        requete += f" AND id IN ({','.join('?' * len(lieux_ids))})"
        params = list(lieux_ids)
    resultats = []
    for lieu in con.execute(requete + " ORDER BY id", params).fetchall():
        choix = extractors.choisir(lieu)
        if choix is None:
            resultats.append(Resultat(lieu["id"], "sans_extracteur"))
            continue
        resultats.append(_passage(con, client, lieu, *choix, maintenant))
    return resultats


def _passage(con, client, lieu, nom, extracteur, maintenant) -> Resultat:
    debut = maintenant()
    chrono = time.monotonic()
    url = lieu["expos_url"]
    precedent = con.execute(
        "SELECT * FROM runs WHERE lieu_id = ? AND url = ? AND statut IN ('ok', 'inchange') ORDER BY id DESC LIMIT 1",
        (lieu["id"], url)).fetchone()

    run = {"statut": "erreur", "erreur": None, "items": None, "etag": None, "derniere_modif": None, "hash": None}
    resultat = Resultat(lieu["id"], "erreur")
    try:
        reponse = client.get(url, etag=precedent["etag"] if precedent else None,
                             derniere_modif=precedent["derniere_modif"] if precedent else None)
    except AccesRefuse as exc:
        run["erreur"] = exc.raison
        if exc.verdict is Verdict.INTERDIT:
            run["statut"] = "interdit"
            _passer_en_t4(con, lieu, exc.raison, debut)
    except ErreurReseau as exc:
        run["erreur"] = str(exc)
    else:
        if reponse.non_modifie and precedent:
            run.update(statut="inchange", etag=precedent["etag"], derniere_modif=precedent["derniere_modif"],
                       hash=precedent["hash_page"])
        elif not reponse.ok:
            run["erreur"] = f"HTTP {reponse.statut}"
        else:
            run.update(etag=reponse.etag, derniere_modif=reponse.derniere_modif, hash=empreinte(reponse.texte))
            if precedent and precedent["hash_page"] == run["hash"]:
                run["statut"] = "inchange"
            else:
                expos = extracteur.extraire(reponse.texte, reponse.url, debut.date())
                run["items"] = len(expos)
                if expos:
                    run["statut"] = "ok"
                    _ranger(con, lieu, nom, expos, debut.date().isoformat(), resultat)
                else:
                    run["statut"], run["erreur"], run["hash"] = "vide", "l'extracteur ne trouve rien sur la page", None
        if run["statut"] == "inchange":
            with con:   # la page n'a pas bougé : tout ce qu'elle montre est « vu » aujourd'hui
                con.execute("UPDATE expositions SET vu_le = ? WHERE lieu_id = ? AND source = ? AND etat <> 'rejete'",
                            (debut.date().isoformat(), lieu["id"], nom))

    resultat.statut, resultat.detail, resultat.items = run["statut"], run["erreur"] or "", run["items"]
    with con:
        con.execute(
            "INSERT INTO runs (lieu_id, demarre_le, duree_ms, statut, items_trouves, erreur, url, etag, derniere_modif, hash_page)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (lieu["id"], debut.strftime("%Y-%m-%dT%H:%M:%SZ"), int((time.monotonic() - chrono) * 1000), run["statut"],
             run["items"], run["erreur"], url, run["etag"], run["derniere_modif"], run["hash"]))
    return resultat


def _passer_en_t4(con, lieu, raison: str, quand: datetime) -> None:
    """Le brief : un robots.txt qui interdit fait passer le lieu en T4, et on n'y retourne plus."""
    note = f"[collect {quand.date().isoformat()}] {raison} : lieu passé en T4"
    with con:
        con.execute("UPDATE lieux SET tier = 'T4', notes_crawler = CASE WHEN notes_crawler IS NULL THEN ? "
                    "ELSE notes_crawler || ' | ' || ? END WHERE id = ?", (note, note, lieu["id"]))


def _ranger(con, lieu, nom: str, expos: list[ExpoBrute], aujourdhui: str, resultat: Resultat) -> None:
    vues: set[str] = set()
    with con:
        for expo in expos:
            existante = _retrouver(con, lieu["id"], expo)
            if existante is None:
                _inserer(con, lieu["id"], nom, expo, aujourdhui)
                resultat.nouveaux += 1
            else:
                changement, renvoyee = _mettre_a_jour(con, existante, nom, expo, aujourdhui)
                resultat.modifies += changement
                resultat.renvoyes_en_revue += renvoyee
            if expo.url:
                vues.add(expo.url)
        # Une exposition de cet extracteur qui n'est plus sur la page : on ne la supprime pas,
        # on la sort de l'export en attendant qu'une personne tranche.
        for ligne in con.execute("SELECT id, url, date_fin FROM expositions WHERE lieu_id = ? AND source = ? "
                                 "AND etat = 'publie'", (lieu["id"], nom)).fetchall():
            if ligne["url"] not in vues and (ligne["date_fin"] is None or ligne["date_fin"] >= aujourdhui):
                con.execute("UPDATE expositions SET etat = 'en_revue', motif_revue = ? WHERE id = ?",
                            (f"absente de la page le {aujourdhui}", ligne["id"]))
                resultat.renvoyes_en_revue += 1


def _retrouver(con, lieu_id: str, expo: ExpoBrute):
    if expo.url:
        ligne = con.execute("SELECT * FROM expositions WHERE lieu_id = ? AND url = ?", (lieu_id, expo.url)).fetchone()
        if ligne:
            return ligne
    return con.execute("SELECT * FROM expositions WHERE lieu_id = ? AND url IS NULL AND lower(titre) = lower(?)",
                       (lieu_id, expo.titre)).fetchone() if not expo.url else None


def _inserer(con, lieu_id: str, nom: str, expo: ExpoBrute, aujourdhui: str) -> None:
    con.execute(
        "INSERT INTO expositions (lieu_id, titre, portee, date_debut, date_fin, description, url, image_url, etat,"
        " hash_source, vu_le, source, provenance) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'en_revue', ?, ?, ?, ?)",
        (lieu_id, expo.titre, expo.portee, expo.date_debut, expo.date_fin, expo.description, expo.url, expo.image_url,
         _hash_source(expo), aujourdhui, nom, json.dumps(expo.provenance, ensure_ascii=False)))


def _mettre_a_jour(con, existante, nom: str, expo: ExpoBrute, aujourdhui: str) -> tuple[int, int]:
    """Renvoie (1 si quelque chose a changé, 1 si l'expo repart en relecture)."""
    if existante["etat"] == "rejete":
        con.execute("UPDATE expositions SET vu_le = ? WHERE id = ?", (aujourdhui, existante["id"]))
        return 0, 0
    provenance = json.loads(existante["provenance"] or "{}")
    nouveau, cle_modifiee = {}, False
    for champ in CHAMPS_PAGE:
        valeur = getattr(expo, champ)
        if provenance.get(champ) == "humain" or valeur is None or valeur == existante[champ]:
            continue
        nouveau[champ] = valeur
        provenance[champ] = expo.provenance.get(champ, "carte")
        cle_modifiee |= champ in CHAMPS_CLES and existante[champ] is not None
    if cle_modifiee:
        provenance.pop("relu", None)    # la page a changé depuis la relecture : elle ne vaut plus
    renvoyee = cle_modifiee and existante["etat"] == "publie"
    con.execute("UPDATE expositions SET vu_le = ?, source = ?, hash_source = ?, provenance = ? WHERE id = ?",
                (aujourdhui, nom, _hash_source(expo), json.dumps(provenance, ensure_ascii=False), existante["id"]))
    if nouveau:
        sets = ", ".join(f"{c} = ?" for c in nouveau)
        con.execute(f"UPDATE expositions SET {sets} WHERE id = ?", [*nouveau.values(), existante["id"]])
    if renvoyee:
        con.execute("UPDATE expositions SET etat = 'en_revue', motif_revue = 'titre ou dates modifiés sur le site' WHERE id = ?",
                    (existante["id"],))
    return int(bool(nouveau)), int(renvoyee)
