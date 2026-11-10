"""Écran de relecture. FastAPI et du HTML simple, pas de framework front.

Objectif : 30 secondes par exposition. Chaque fiche montre pourquoi elle attend, d'où vient
chaque champ, ce que le moteur calcule comme gratuité, et propose trois gestes : publier
(en corrigeant au besoin titre, portée et dates), rejeter, passer.

Sécurité : l'écran n'écoute que sur 127.0.0.1, refuse tout autre nom d'hôte (DNS rebinding),
exige un jeton par processus sur chaque POST, et n'accepte aucun script hors nonce.
"""
from __future__ import annotations

import json
import secrets
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from panade import apercu, db, gratuite, models, validate

DOSSIER = Path(__file__).parent
MOTIFS_URGENTS = ("gratuité modifiée", "absente de la page", "titre ou dates modifiés")


def libelle_gratuite(brut: str | None) -> str:
    """La gratuité calculée, en une phrase pour la personne qui relit."""
    if not brut:
        return "pas encore calculée"
    g = json.loads(brut)
    prix = lambda v: f"{v:g} €"  # noqa: E731
    statut = g["statut"]
    if statut == "gratuit_tous":
        base = "Gratuit pour tous"
    elif statut == "gratuit_26":
        base = "Gratuit pour les moins de 26 ans" + (" (résidents UE)" if g.get("audience") == "moins_26_ue" else "")
    elif statut == "reduit_26":
        base = f"Tarif réduit moins de 26 ans : {prix(g['prix'])}" + (f" (plein tarif {prix(g['plein_tarif'])})" if g.get("plein_tarif") else "")
    elif statut == "payant":
        base = "Payant" + (f" : {prix(g['prix'])}" if g.get("prix") else ", montant inconnu")
    else:
        base = "À confirmer sur place"
    return f"{base}. {g['raison']}"


# Libellés du site (src/models/labels.js et src/lib/pricing.js) : l'aperçu dit la même chose que la fiche publique.
LIBELLES_SITE = {
    "gratuit_tous": ("GRATUIT", "Gratuit pour tous"),
    "gratuit_26": ("GRATUIT", "Gratuit pour les -26 ans"),
    "reduit_26": ("TARIF RÉDUIT", "Tarif réduit pour les -26 ans"),
    "payant": ("PAYANT", "Payant"),
    "a_confirmer": ("À CONFIRMER", "À confirmer sur place"),
}


NOMS_CHAMPS = {"lieu": "Lieu", "titre": "Titre", "image": "Image", "description": "Description", "dates": "Dates",
               "portee": "Portée", "lien": "Page de l'exposition", "horaires": "Horaires", "tarif": "Tarif",
               "reservation": "Réservation"}


def tarif_site(brut: str | None) -> dict:
    """Badge, libellé et précision tels que la fiche publique les afficherait."""
    if not brut:
        return {"badge": "?", "libelle": "Gratuité non calculée", "note": None, "gratuit": False}
    g = json.loads(brut)
    badge, libelle = LIBELLES_SITE[g["statut"]]
    note = None
    if g["statut"] == "reduit_26" and g.get("prix") is not None:
        note = f"{g['prix']:g} € au lieu de {g['plein_tarif']:g} €" if g.get("plein_tarif") else f"{g['prix']:g} €"
    elif g["statut"] == "gratuit_26" and g.get("audience") == "moins_26_ue":
        note = "Résidents de l'Union européenne, sur justificatif."
    return {"badge": badge, "libelle": libelle, "note": note, "gratuit": g["statut"] in ("gratuit_tous", "gratuit_26")}


def accroche(statut: str | None, lieu_nom: str) -> str:
    """La phrase éditoriale du site (getter `editorial_note` du modèle Exposition)."""
    lieu = f" à {lieu_nom}" if lieu_nom else " à Paris"
    if statut == "gratuit_26":
        return (f"Exposition gratuite pour les moins de 26 ans{lieu} : entrée libre sur présentation d'une pièce "
                "d'identité, plein tarif au-delà.")
    if statut == "reduit_26":
        return f"Exposition à tarif réduit pour les moins de 26 ans{lieu}."
    if statut == "gratuit_tous":
        return f"Exposition gratuite pour tout le monde{lieu}, sans condition d'âge ni de résidence."
    return f"Exposition{lieu}."


def creer_app(chemin_db: str, *, aujourdhui: Callable[[], date] = date.today) -> FastAPI:
    app = FastAPI(title="Panade : relecture", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    jeton = secrets.token_urlsafe(24)
    modeles = Jinja2Templates(directory=str(DOSSIER / "templates"))
    modeles.env.filters["gratuite"] = libelle_gratuite
    modeles.env.globals["NOMS_CHAMPS"] = NOMS_CHAMPS

    @app.middleware("http")
    async def en_tetes(requete: Request, suite):
        requete.state.nonce = secrets.token_urlsafe(12)
        reponse = await suite(requete)
        reponse.headers["Content-Security-Policy"] = (
            f"default-src 'none'; img-src https: http:; style-src 'unsafe-inline'; "
            f"script-src 'nonce-{requete.state.nonce}'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        reponse.headers["X-Content-Type-Options"] = "nosniff"
        reponse.headers["Referrer-Policy"] = "no-referrer"
        return reponse

    def connexion():
        con = db.connect(chemin_db)
        try:
            yield con
        finally:
            con.close()

    def verifier_jeton(csrf: str = Form("")) -> None:
        if not secrets.compare_digest(csrf, jeton):
            raise HTTPException(403, "jeton de formulaire invalide")

    def file_d_attente(con) -> list[int]:
        """Les urgences d'abord (gratuité modifiée, disparue, modifiée), puis les lieux vérifiés, puis le reste."""
        lignes = con.execute(
            "SELECT e.id, e.motif_revue, l.statut FROM expositions e JOIN lieux l ON l.id = e.lieu_id "
            "WHERE e.etat = 'en_revue' ORDER BY e.id").fetchall()
        def rang(r):
            urgent = any((r["motif_revue"] or "").startswith(m) for m in MOTIFS_URGENTS)
            return (0 if urgent else 1, 0 if r["statut"] == "verifie" else 1, r["id"])
        return [r["id"] for r in sorted(lignes, key=rang)]

    def suivant(con, apres: int | None) -> int | None:
        file = file_d_attente(con)
        restantes = [i for i in file if apres is None or i != apres]
        return restantes[0] if restantes else None

    def contexte(requete, **plus):
        return {"request": requete, "jeton": jeton, "nonce": requete.state.nonce, **plus}

    @app.get("/", response_class=HTMLResponse)
    def accueil(requete: Request, con=Depends(connexion)):
        prochain = suivant(con, None)
        if prochain is not None:
            return RedirectResponse(f"/item/{prochain}", status_code=303)
        comptes = {r["etat"]: r["n"] for r in con.execute("SELECT etat, COUNT(*) n FROM expositions GROUP BY etat")}
        return modeles.TemplateResponse(requete, "vide.html", contexte(requete, comptes=comptes))

    @app.get("/liste", response_class=HTMLResponse)
    def liste(requete: Request, con=Depends(connexion)):
        ids = file_d_attente(con)
        lignes = []
        for i in ids:
            expo = con.execute("SELECT e.*, l.nom AS lieu_nom FROM expositions e JOIN lieux l ON l.id = e.lieu_id WHERE e.id = ?",
                               (i,)).fetchone()
            etats = analyser(con, expo)[3].values()
            lignes.append({"e": expo, "manques": sum(x.etat == "manque" for x in etats),
                           "doutes": sum(x.etat == "doute" for x in etats)})
        return modeles.TemplateResponse(requete, "liste.html", contexte(requete, lignes=lignes))

    def charger(con, expo_id: int):
        expo = con.execute("SELECT e.*, l.nom AS lieu_nom, l.statut AS lieu_statut FROM expositions e "
                           "JOIN lieux l ON l.id = e.lieu_id WHERE e.id = ?", (expo_id,)).fetchone()
        if expo is None:
            raise HTTPException(404, "exposition inconnue")
        return expo

    def analyser(con, expo):
        """Lieu, horaires résumés, gratuité recalculée et état de chaque champ de la fiche publique.
        La gratuité est recalculée à l'affichage : c'est celle que le site montrerait si on publiait maintenant."""
        lieu = con.execute("SELECT * FROM lieux WHERE id = ?", (expo["lieu_id"],)).fetchone()
        jour = aujourdhui()
        lignes_horaires = [dict(h) for h in con.execute("SELECT * FROM horaires WHERE lieu_id = ?", (expo["lieu_id"],))]
        horaires = apercu.resume_horaires(lignes_horaires, jour, expo["portee"])
        calculee = gratuite.calculer(gratuite.charger(con, expo["lieu_id"]), expo["portee"], jour).en_json()
        return lieu, horaires, calculee, apercu.diagnostiquer(dict(expo), dict(lieu), calculee, horaires, jour)

    @app.get("/item/{expo_id}", response_class=HTMLResponse)
    def fiche(expo_id: int, requete: Request, con=Depends(connexion), erreur: str | None = None):
        expo = charger(con, expo_id)
        file = file_d_attente(con)
        provenance = json.loads(expo["provenance"] or "{}")
        score, _ = validate.confiance(expo)
        lieu, horaires, calculee, etats = analyser(con, expo)
        problemes = [(nom, etat) for nom, etat in etats.items() if etat.etat != "ok"]
        problemes.sort(key=lambda x: (x[1].etat != "manque", x[0]))
        return modeles.TemplateResponse(requete, "item.html", contexte(
            requete, e=expo, lieu=lieu, provenance=provenance, score=score, restantes=len(file),
            position=(file.index(expo_id) + 1) if expo_id in file else None, erreur=erreur,
            etats=etats, problemes=problemes, horaires=horaires, tarif=tarif_site(calculee),
            dates=apercu.libelle_dates(expo["date_debut"], expo["date_fin"], expo["portee"]),
            accroche=accroche(json.loads(calculee)["statut"], lieu["nom"]), calculee=calculee,
            gratuite_avant=expo["gratuite_validee"] if expo["gratuite_validee"] not in (None, calculee) else None))

    def retour(con, apres: int) -> RedirectResponse:
        prochain = suivant(con, apres)
        return RedirectResponse(f"/item/{prochain}" if prochain is not None else "/", status_code=303)

    @app.post("/item/{expo_id}/publier", dependencies=[Depends(verifier_jeton)])
    def publier(expo_id: int, titre: str = Form(...), portee: str = Form(...), date_debut: str = Form(""),
                date_fin: str = Form(""), con=Depends(connexion)):
        expo = charger(con, expo_id)
        saisi = {"titre": titre.strip(), "portee": portee, "date_debut": date_debut.strip() or None,
                 "date_fin": date_fin.strip() or None}
        champs = list(models.Exposition.model_fields)
        candidat = {c: expo[c] for c in champs} | saisi | {"etat": "publie", "confiance": 1.0}
        try:
            models.Exposition(**candidat)
        except ValidationError as exc:
            message = "; ".join(f"{'.'.join(map(str, e['loc']))} : {e['msg']}" for e in exc.errors())
            return RedirectResponse(f"/item/{expo_id}?erreur={quote(message)}", status_code=303)

        provenance = json.loads(expo["provenance"] or "{}")
        for champ, valeur in saisi.items():
            if valeur != expo[champ]:
                provenance[champ] = "humain"          # une correction à la main n'est plus jamais écrasée
        provenance["relu"] = "humain"
        lieu = gratuite.charger(con, expo["lieu_id"])
        calculee = gratuite.calculer(lieu, saisi["portee"], aujourdhui()).en_json()
        with con:
            con.execute(
                "UPDATE expositions SET titre = ?, portee = ?, date_debut = ?, date_fin = ?, etat = 'publie', confiance = 1.0,"
                " motif_revue = NULL, provenance = ?, gratuite_calculee = ?, gratuite_validee = ? WHERE id = ?",
                (saisi["titre"], saisi["portee"], saisi["date_debut"], saisi["date_fin"],
                 json.dumps(provenance, ensure_ascii=False), calculee, calculee, expo_id))
        return retour(con, expo_id)

    @app.post("/item/{expo_id}/rejeter", dependencies=[Depends(verifier_jeton)])
    def rejeter(expo_id: int, con=Depends(connexion)):
        charger(con, expo_id)
        with con:
            con.execute("UPDATE expositions SET etat = 'rejete', motif_revue = 'rejetée par une personne' WHERE id = ?", (expo_id,))
        return retour(con, expo_id)

    return app
