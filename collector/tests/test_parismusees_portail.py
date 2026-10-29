"""Le portail Paris Musées, page réelle du 2026-10-29 (9 sites sur 12 en maintenance ce jour-là)."""
from datetime import date

import httpx
import pytest

from panade import collect, completer, db, seed
from panade.extractors import choisir, parismusees as pm

from conftest import CLASSEUR, fixture

AUJ = date(2026, 10, 29)
PAGE = fixture("sites/parismusees_portail.html")


def test_repartition_par_musee():
    compte = {lid: len(pm.extraire_pour(lid, PAGE, pm.SOURCE, AUJ)) for lid in pm.MUSEES}
    assert compte["musee-d-art-moderne-de-la-ville-de-paris"] == 3
    assert compte["petit-palais-musee-des-beaux-arts-de-la-ville-de-paris"] == 2
    assert compte["palais-galliera-musee-de-la-mode-et-de-la-ville-de-paris"] == 1      # site propre en maintenance
    assert compte["musee-de-la-liberation-de-paris-musee-du-general-leclerc-mus"] == 1   # idem
    assert sum(compte.values()) == 9          # Victor Hugo et les Catacombes ne sont pas dans la base


def test_dates_lues_sur_le_portail_meme_quand_la_fiche_du_musee_n_en_donne_pas():
    (e,) = pm.extraire_pour("musee-bourdelle", PAGE, pm.SOURCE, AUJ)
    assert (e.titre, e.date_debut, e.date_fin) == ("L’étoffe de l’artiste", "2026-09-23", "2027-01-24")
    assert e.url.startswith("https://www.parismusees.paris.fr/fr/exposition/") and e.image_url


def test_carnavalet_titre_et_sous_titre():
    (e,) = pm.extraire_pour("musee-carnavalet-histoire-de-paris", PAGE, pm.SOURCE, AUJ)
    assert (e.titre, e.description) == ("Paris à l'arraché", "Jacques Villeglé et l'art urbain")


def test_le_portail_passe_avant_le_site_du_musee():
    assert choisir({"id": "musee-carnavalet-histoire-de-paris", "famille_id": "paris_musees", "tier": "T1",
                    "expos_url": "https://www.carnavalet.paris.fr/expositions/expositions-en-cours"})[0] == "parismusees"


def test_une_seule_requete_pour_tous_les_lieux_du_reseau(tmp_path, faux_client):
    con = db.connect(tmp_path / "pm.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    completer.appliquer(con, CLASSEUR.parent / "lieux_web.json")
    client, reseau = faux_client({"https://www.parismusees.paris.fr/robots.txt": "User-agent: *\nDisallow:\n", pm.SOURCE: PAGE})
    resultats = collect.collecter(con, client, lieux_ids=list(pm.MUSEES))
    assert reseau.chemins.count("www.parismusees.paris.fr/fr/expositions") == 1
    statuts = {r.lieu: r.statut for r in resultats}
    assert statuts["musee-d-art-moderne-de-la-ville-de-paris"] == "ok"
    assert statuts["musee-zadkine"] == "vide"          # aucune expo en cours ce jour-là
    assert con.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 12
    con.close()


def test_une_erreur_de_la_source_partagee_vaut_pour_tous_sans_redemander(tmp_path, faux_client):
    con = db.connect(tmp_path / "pm2.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    def coupe(r):
        raise httpx.ConnectError("reset")
    client, reseau = faux_client({"https://www.parismusees.paris.fr/robots.txt": "User-agent: *\nDisallow:\n", pm.SOURCE: coupe})
    resultats = collect.collecter(con, client, lieux_ids=list(pm.MUSEES))
    assert {r.statut for r in resultats} == {"erreur"}
    assert reseau.chemins.count("www.parismusees.paris.fr/fr/expositions") == 2     # une reprise, puis plus rien
    con.close()
