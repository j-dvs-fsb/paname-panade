"""Alertes : un fichier de journal, la sortie d'erreur, et un webhook si on en configure un.

Une alerte qui ne part pas ne doit jamais empêcher le reste de tourner : l'envoi au
webhook est « au mieux ». Le journal, lui, est toujours écrit.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

NIVEAUX = ("info", "alerte", "grave")


def notifier(niveau: str, message: str, *, dossier: str | Path = "data", maintenant: datetime | None = None,
             webhook: str | None = None, sortie=None) -> None:
    assert niveau in NIVEAUX, niveau
    quand = (maintenant or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ligne = f"{quand} {niveau.upper():6} {message}"
    (sortie or sys.stderr).write(ligne + "\n")
    try:
        chemin = Path(dossier) / "alertes.log"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with chemin.open("a", encoding="utf-8") as f:
            f.write(ligne + "\n")
    except OSError as exc:
        (sortie or sys.stderr).write(f"(journal d'alertes illisible : {exc})\n")
    webhook = webhook if webhook is not None else os.environ.get("PANADE_ALERT_WEBHOOK")
    if webhook and niveau != "info":
        try:   # format compatible Slack, Mattermost et Discord (« text » / « content »)
            httpx.post(webhook, json={"text": f"[panade] {message}", "content": f"[panade] {message}"}, timeout=10)
        except httpx.HTTPError:
            pass
