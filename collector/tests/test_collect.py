import json
from datetime import datetime, timezone

import httpx
import pytest

from panade import collect, db, seed

from conftest import CLASSEUR, fixture


@pytest.fixture(autouse=True)
def sans_portail(monkeypatch):
    """Ces tests portent sur le lecteur du site propre d'un musée : le portail du réseau est mis de côté."""
    from panade.extractors import parismusees
    monkeypatch.setattr(parismusees, "MUSEES", {})


BASE = "https://www.carnavalet.paris.fr"
URL = f"{BASE}/expositions/expositions-en-cours"
LIEU = "musee-carnavalet-histoire-de-paris"
ROBOTS = "User-agent: *\nDisallow:\n"
PAGE = fixture("pages/carnavalet_expositions_en_cours.html")
NUIT_1 = lambda: datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)   # noqa: E731
NUIT_2 = lambda: datetime(2026, 10, 31, 3, 0, tzinfo=timezone.utc)   # noqa: E731


@pytest.fixture
def base(tmp_path):
    con = db.connect(tmp_path / "c.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    con.execute("UPDATE lieux SET expos_url = ? WHERE id = ?", (URL, LIEU))
    con.commit()
    yield con
    con.close()


def retirer_la_carte(page: str, href: str) -> str:
    from panade import html as h
    arbre = h.lire(page)
    lien = arbre.css_first(f'a[href="{href}"]')
    carte = lien
    while carte is not None and "card" not in (carte.attributes.get("class") or "").split():
        carte = carte.parent
    carte.decompose()
    return arbre.html


def runs(con):
    return [dict(r) for r in con.execute("SELECT * FROM runs ORDER BY id")]


def expos(con):
    return {r["titre"]: dict(r) for r in con.execute("SELECT * FROM expositions WHERE lieu_id = ?", (LIEU,))}


def passage(base, faux_client, page, quand=NUIT_1, statut=200, entetes=None, lieux=(LIEU,)):
    client, reseau = faux_client({f"{BASE}/robots.txt": ROBOTS, URL: (statut, entetes or {"etag": '"v1"'}, page)})
    return collect.collecter(base, client, maintenant=quand, lieux_ids=lieux)[0], reseau


def test_premiere_nuit(base, faux_client):
    r, _ = passage(base, faux_client, PAGE)
    assert (r.statut, r.items, r.nouveaux) == ("ok", 4, 4)
    e = expos(base)["Paris à l’arraché"]
    assert (e["etat"], e["confiance"], e["source"], e["vu_le"]) == ("en_revue", None, "paris_musees", "2026-10-30")
    assert json.loads(e["provenance"])["date_debut"] == "time" and len(e["hash_source"]) == 16
    run = runs(base)[0]
    assert (run["statut"], run["items_trouves"], run["etag"], run["demarre_le"], run["url"]) == ("ok", 4, '"v1"', "2026-10-30T03:00:00Z", URL)
    assert len(run["hash_page"]) == 64 and run["duree_ms"] >= 0


def test_deuxieme_nuit_304_ne_relit_rien(base, faux_client):
    passage(base, faux_client, PAGE)
    base.execute("UPDATE expositions SET etat = 'publie', confiance = 0.9 WHERE lieu_id = ?", (LIEU,))
    base.commit()
    recu = {}
    client, _ = faux_client({f"{BASE}/robots.txt": ROBOTS,
                             URL: lambda r: (recu.update(r.headers), httpx.Response(304))[1]})
    r = collect.collecter(base, client, maintenant=NUIT_2, lieux_ids=[LIEU])[0]
    assert r.statut == "inchange" and r.nouveaux == 0
    assert recu["if-none-match"] == '"v1"'
    dernier = runs(base)[-1]
    assert (dernier["statut"], dernier["etag"]) == ("inchange", '"v1"') and dernier["hash_page"] == runs(base)[0]["hash_page"]
    assert {e["vu_le"] for e in expos(base).values()} == {"2026-10-31"}   # toujours là cette nuit


def test_meme_contenu_avec_jetons_differents_est_inchange(base, faux_client):
    passage(base, faux_client, PAGE)
    page_bis = PAGE.replace("<main", '<main data-jeton="abc123"', 1).replace("itok=", "itok=ZZ")   # bruit sans effet sur le texte
    r, _ = passage(base, faux_client, page_bis, quand=NUIT_2, entetes={"etag": '"v2"'})
    assert r.statut == "inchange" and runs(base)[-1]["etag"] == '"v2"'


def test_page_modifiee_les_dates_d_une_expo_publiee_la_renvoient_en_relecture(base, faux_client):
    passage(base, faux_client, PAGE)
    base.execute("UPDATE expositions SET etat = 'publie', confiance = 0.9 WHERE lieu_id = ?", (LIEU,))
    base.commit()
    prolongee = PAGE.replace("2027-02-14T12:00:00Z", "2027-03-14T12:00:00Z").replace("14 février 2027", "14 mars 2027")
    r, _ = passage(base, faux_client, prolongee, quand=NUIT_2)
    assert (r.statut, r.modifies, r.renvoyes_en_revue) == ("ok", 1, 1)
    e = expos(base)["Paris à l’arraché"]
    assert (e["date_fin"], e["etat"], e["motif_revue"]) == ("2027-03-14", "en_revue", "titre ou dates modifiés sur le site")
    assert expos(base)["PARIS · ROME"]["etat"] == "publie"            # les autres n'ont pas bougé


def test_correction_humaine_jamais_ecrasee_et_vide_jamais_ecrit(base, faux_client):
    passage(base, faux_client, PAGE)
    prov = json.loads(expos(base)["PARIS · ROME"]["provenance"])
    prov["date_fin"] = "humain"
    base.execute("UPDATE expositions SET date_fin = '2027-02-01', provenance = ? WHERE titre = 'PARIS · ROME'",
                 (json.dumps(prov),))
    base.execute("UPDATE expositions SET description = NULL WHERE titre = 'PARIS · ROME'")
    base.commit()
    nouvelle = PAGE.replace("2027-01-05T12:00:00Z", "2027-01-09T12:00:00Z").replace("05 janvier 2027", "09 janvier 2027")
    passage(base, faux_client, nouvelle, quand=NUIT_2)
    e = expos(base)["PARIS · ROME"]
    assert e["date_fin"] == "2027-02-01"                      # l'humain gagne
    assert e["description"] == "Une amitié historique"        # un champ vide est comblé par la page


def test_expo_rejetee_ne_revient_pas(base, faux_client):
    passage(base, faux_client, PAGE)
    base.execute("UPDATE expositions SET etat = 'rejete' WHERE titre = 'PARIS · ROME'")
    base.commit()
    r, _ = passage(base, faux_client, PAGE.replace("Une amitié", "Une grande amitié"), quand=NUIT_2)
    assert expos(base)["PARIS · ROME"]["etat"] == "rejete" and r.nouveaux == 0


def test_page_vide_ne_depublie_rien_et_sera_relue(base, faux_client):
    passage(base, faux_client, PAGE)
    base.execute("UPDATE expositions SET etat = 'publie', confiance = 0.9 WHERE lieu_id = ?", (LIEU,))
    base.commit()
    r, _ = passage(base, faux_client, "<html><body><main><p>Site refait</p></main></body></html>", quand=NUIT_2)
    assert (r.statut, r.items) == ("vide", 0)
    assert {e["etat"] for e in expos(base).values()} == {"publie"}
    assert runs(base)[-1]["hash_page"] is None                 # la prochaine nuit relira, même si la page ne bouge pas


def test_expo_disparue_de_la_page_sort_de_l_export(base, faux_client):
    passage(base, faux_client, PAGE)
    base.execute("UPDATE expositions SET etat = 'publie', confiance = 0.9 WHERE lieu_id = ?", (LIEU,))
    base.commit()
    sans_rome = retirer_la_carte(PAGE, "/expositions/paris-rome")
    r, _ = passage(base, faux_client, sans_rome, quand=NUIT_2)
    e = expos(base)["PARIS · ROME"]
    assert (e["etat"], e["motif_revue"]) == ("en_revue", "absente de la page le 2026-10-31")
    assert r.renvoyes_en_revue == 1 and expos(base)["Paris à l’arraché"]["etat"] == "publie"


def test_robots_interdit_passe_le_lieu_en_t4_pour_toujours(base, faux_client):
    client, reseau = faux_client({f"{BASE}/robots.txt": "User-agent: *\nDisallow: /\n"})
    r = collect.collecter(base, client, maintenant=NUIT_1, lieux_ids=[LIEU])[0]
    assert r.statut == "interdit"
    lieu = base.execute("SELECT tier, notes_crawler FROM lieux WHERE id = ?", (LIEU,)).fetchone()
    assert lieu["tier"] == "T4" and "lieu passé en T4" in lieu["notes_crawler"]
    assert reseau.chemins == ["www.carnavalet.paris.fr/robots.txt"]
    suite = collect.collecter(base, client, maintenant=NUIT_2, lieux_ids=[LIEU])[0]
    assert suite.statut == "sans_extracteur" and len(runs(base)) == 1


@pytest.mark.parametrize("statut, attendu", [(503, "HTTP 503"), (404, "HTTP 404")])
def test_page_en_erreur_est_une_erreur_pas_un_t4(base, faux_client, statut, attendu):
    r, _ = passage(base, faux_client, "Maintenance", statut=statut)
    assert (r.statut, r.detail) == ("erreur", attendu)
    assert base.execute("SELECT tier FROM lieux WHERE id = ?", (LIEU,)).fetchone()[0] != "T4"
    assert runs(base)[0]["statut"] == "erreur" and runs(base)[0]["hash_page"] is None


def test_robots_en_maintenance_est_une_erreur_pas_un_t4(base, faux_client):
    client, _ = faux_client({f"{BASE}/robots.txt": (503, {}, "Maintenance")})
    r = collect.collecter(base, client, maintenant=NUIT_1, lieux_ids=[LIEU])[0]
    assert r.statut == "erreur" and "robots.txt injoignable" in r.detail
    assert base.execute("SELECT tier FROM lieux WHERE id = ?", (LIEU,)).fetchone()[0] != "T4"


def test_une_expo_de_la_graine_est_retrouvee_par_son_url_pas_dupliquee(base, faux_client):
    base.execute("INSERT INTO expositions (lieu_id, titre, portee, url, source) VALUES (?, 'Paris à l''arraché (graine)', "
                 "'temporaire', ?, 'site officiel')", (LIEU, f"{BASE}/expositions/paris-larrache"))
    base.commit()
    passage(base, faux_client, PAGE)
    lignes = base.execute("SELECT titre, source FROM expositions WHERE url = ?", (f"{BASE}/expositions/paris-larrache",)).fetchall()
    assert len(lignes) == 1 and lignes[0]["source"] == "paris_musees"
    assert lignes[0]["titre"] == "Paris à l’arraché"


def test_lieux_sans_extracteur_ne_laissent_aucune_ligne_dans_runs(base, faux_client):
    client, reseau = faux_client({})
    resultats = collect.collecter(base, client, maintenant=NUIT_1, lieux_ids=["musee-de-la-poste"])
    assert resultats == [] or resultats[0].statut == "sans_extracteur"
    assert runs(base) == [] and reseau.vues == []


def test_la_relecture_ne_vaut_que_tant_que_la_page_ne_change_pas(base, faux_client):
    passage(base, faux_client, PAGE)
    prov = json.loads(expos(base)["PARIS · ROME"]["provenance"])
    prov["relu"] = "humain"
    base.execute("UPDATE expositions SET etat = 'publie', confiance = 1.0, provenance = ? WHERE titre = 'PARIS · ROME'",
                 (json.dumps(prov),))
    base.commit()
    # un changement de description n'annule pas la relecture
    passage(base, faux_client, PAGE.replace("Une amitié historique", "Une grande amitié historique"), quand=NUIT_2)
    e = expos(base)["PARIS · ROME"]
    assert e["etat"] == "publie" and json.loads(e["provenance"]).get("relu") == "humain"
    # un changement de dates, si
    prolongee = PAGE.replace("2027-01-05T12:00:00Z", "2027-02-05T12:00:00Z").replace("05 janvier 2027", "05 février 2027")
    passage(base, faux_client, prolongee, quand=lambda: datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc))
    e = expos(base)["PARIS · ROME"]
    assert e["etat"] == "en_revue" and "relu" not in json.loads(e["provenance"])
