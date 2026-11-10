"""`panade publish` : vérifie les garde-fous, puis pousse l'export vers le site.

C'est la partie où une erreur se voit en ligne : elle est la plus prudente.

Trois garde-fous bloquent ou corrigent la publication :
  1. moins de 70 % des expositions attendues (celles de la veille qui ne sont pas terminées) :
     refus et alerte. C'est ce qui empêche un bug de scraper de vider le site ;
  2. un lieu qui passait pour avoir des expositions n'en a plus : on garde ses données de la
     veille, pour ce lieu seul ;
  3. une gratuité qui a changé sans relecture : l'exposition sort de l'export (export.construire).

Transport : POST authentifié vers le site, jamais d'écriture directe dans sa base. Le site
reçoit l'export entier ou rien : il garde la version précédente et ne bascule qu'une fois le
nouveau fichier complet et valide (voir docs/export.md). Chez nous, « dernière publication »
n'est mise à jour qu'après une réponse 2xx.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from panade import alerts, export, validate
from panade.http import USER_AGENT

SEUIL_VOLUME = 0.70


class PublicationRefusee(Exception):
    def __init__(self, raison: str, code: int = 2):
        super().__init__(raison)
        self.raison, self.code = raison, code


@dataclass
class Verdict:
    contenu: dict
    alertes: list[str] = field(default_factory=list)
    refus: str | None = None
    reportes: dict[str, int] = field(default_factory=dict)


def garde_fous(nouveau: dict, precedent: dict | None, aujourdhui: date, exclues_ids: set[int] = frozenset(),
               seuil: float = SEUIL_VOLUME) -> Verdict:
    verdict = Verdict(nouveau)
    if not nouveau.get("lieux"):
        verdict.refus = "l'export ne contient aucun lieu vérifié"
        return verdict
    if nouveau["compte"]["expositions"] == 0:
        verdict.refus = "l'export ne contient aucune exposition : il viderait le site"
        return verdict
    if precedent is None:
        verdict.alertes.append("première publication : aucun export précédent à comparer")
        return verdict

    attendues = export.expos_attendues(precedent, aujourdhui)
    attendu = sum(len(v) for v in attendues.values())
    obtenu = nouveau["compte"]["expositions"]

    # Garde-fou 1
    if attendu and obtenu < seuil * attendu:
        verdict.refus = (f"garde-fou 1 : {obtenu} exposition(s) pour {attendu} attendue(s) "
                         f"(moins de {seuil:.0%}), publication refusée")
        return verdict

    # Garde-fou 2 : un lieu qui avait des expositions n'en a plus, on garde celles de la veille
    for lieu in nouveau["lieux"]:
        if lieu.get("expositions") or lieu["id"] not in attendues:
            continue
        reprises = [e for e in attendues[lieu["id"]] if e["id"] not in exclues_ids]
        if reprises:
            lieu["expositions"] = reprises
            verdict.reportes[lieu["id"]] = len(reprises)
            verdict.alertes.append(f"garde-fou 2 : {lieu['id']} n'a plus d'exposition, "
                                   f"{len(reprises)} reprise(s) de la veille")
    if verdict.reportes:
        nouveau["compte"]["expositions"] = sum(len(l.get("expositions", [])) for l in nouveau["lieux"])
        nouveau["empreinte"] = export.empreinte(nouveau)
    return verdict


def retirees_volontairement(con: sqlite3.Connection, precedent: dict | None) -> set[int]:
    """Expositions de la veille qui ne sont plus publiées pour une raison qui doit être respectée.

    Le garde-fou 2 ne reprend que ce qui a disparu par accident : une page lue de travers (« absente
    de la page ») ou encore publiée. Une gratuité modifiée, un rejet, un doublon, une exposition non
    conforme ou modifiée sur le site ne reviennent jamais par ce chemin.
    """
    if not precedent:
        return set()
    ids = [e["id"] for l in precedent.get("lieux", []) for e in l.get("expositions", [])]
    retirees = set(ids)
    for i in range(0, len(ids), 500):
        morceau = ids[i:i + 500]
        for r in con.execute(f"SELECT id, etat, motif_revue FROM expositions WHERE id IN ({','.join('?' * len(morceau))})", morceau):
            if r["etat"] == "publie" or (r["etat"] == "en_revue" and (r["motif_revue"] or "").startswith("absente de la page")):
                retirees.discard(r["id"])
    return retirees


def _verifier_url(url: str) -> None:
    p = urlsplit(url)
    local = p.hostname in ("localhost", "127.0.0.1", "::1")
    if p.scheme != "https" and not (p.scheme == "http" and local):
        raise PublicationRefusee(f"l'URL de publication doit être en https (jeton d'authentification) : {url}", 4)


def envoyer(contenu: dict, url: str, jeton: str, client: httpx.Client | None = None) -> httpx.Response:
    _verifier_url(url)
    corps = json.dumps(contenu, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    entetes = {"Authorization": f"Bearer {jeton}", "Content-Type": "application/json", "User-Agent": USER_AGENT,
               "Idempotency-Key": contenu["empreinte"]}
    propre = client is None
    client = client or httpx.Client(timeout=60)
    try:
        for tentative in range(2):
            try:
                return client.post(url, content=corps, headers=entetes)
            except httpx.TransportError as exc:
                if tentative == 1:
                    raise PublicationRefusee(f"le site est injoignable : {exc}", 3) from exc
        raise AssertionError("inatteignable")
    finally:
        if propre:
            client.close()


def publier(con: sqlite3.Connection, aujourdhui: date, dossier: str | Path, *, url: str | None = None,
            jeton: str | None = None, a_blanc: bool = False, client: httpx.Client | None = None,
            maintenant: datetime | None = None, webhook: str | None = None) -> dict:
    """Renvoie un compte rendu. Lève PublicationRefusee (avec code de sortie) si rien n'est publié."""
    maintenant = maintenant or datetime.now(timezone.utc)
    dossier = Path(dossier)
    url = url or os.environ.get("PANADE_PUBLISH_URL")
    jeton = jeton or os.environ.get("PANADE_PUBLISH_TOKEN")

    def refuser(raison: str, niveau: str = "alerte", code: int = 2):
        alerts.notifier(niveau, f"publication refusée : {raison}", dossier=dossier, maintenant=maintenant, webhook=webhook)
        raise PublicationRefusee(raison, code)

    if not a_blanc:
        if not url or not jeton:
            refuser("PANADE_PUBLISH_URL et PANADE_PUBLISH_TOKEN doivent être définis", "grave", 4)
        try:
            _verifier_url(url)
        except PublicationRefusee as exc:
            refuser(exc.raison, "grave", exc.code)

    rapport = validate.valider(con, aujourdhui)
    if rapport.problemes_graves:
        refuser("validate signale : " + "; ".join(rapport.problemes_graves), "grave")

    construit = export.construire(con, aujourdhui, maintenant)
    for expo_id, motif in construit.exclues:
        alerts.notifier("alerte", f"garde-fou 3 : exposition {expo_id} sortie de l'export ({motif})",
                        dossier=dossier, maintenant=maintenant, webhook=webhook)

    derniere = dossier / "publie" / "derniere.json"
    precedent = None
    if derniere.exists():
        try:
            precedent = export.lire(derniere)
        except ValueError as exc:
            refuser(f"l'export de référence est illisible ({exc}) : à examiner avant de publier", "grave", 5)

    interdites = {i for i, _ in construit.exclues} | retirees_volontairement(con, precedent)
    verdict = garde_fous(construit.contenu, precedent, aujourdhui, interdites)
    chemin = export.ecrire(export.Export(verdict.contenu), dossier / "exports", maintenant)
    for message in verdict.alertes:
        alerts.notifier("alerte", message, dossier=dossier, maintenant=maintenant, webhook=webhook)
    if verdict.refus:
        refuser(f"{verdict.refus} (fichier gardé pour examen : {chemin})")

    compte = verdict.contenu["compte"]
    resume = {"fichier": str(chemin), "lieux": compte["lieux"], "expositions": compte["expositions"],
              "reportes": verdict.reportes, "exclues": len(construit.exclues), "envoye": False}
    if a_blanc:
        return resume

    reponse = envoyer(verdict.contenu, url, jeton, client)
    if not 200 <= reponse.status_code < 300:
        refuser(f"le site a répondu HTTP {reponse.status_code} : {reponse.text[:200]}", "grave", 3)
    (dossier / "publie").mkdir(parents=True, exist_ok=True)
    temporaire = derniere.with_suffix(".tmp")
    temporaire.write_text(chemin.read_text(encoding="utf-8"), encoding="utf-8")
    temporaire.replace(derniere)     # la référence de demain n'est posée qu'après un 2xx
    resume["envoye"] = True
    alerts.notifier("info", f"publié : {compte['lieux']} lieux, {compte['expositions']} expositions ({chemin.name})",
                    dossier=dossier, maintenant=maintenant, webhook=webhook)
    return resume
