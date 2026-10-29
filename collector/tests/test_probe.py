import json

import httpx
import pytest

from panade import db, probe, seed
from panade.probe import QueFaireAParis, sonder, signaux

from conftest import CLASSEUR, fixture

ROBOTS_LIBRE = "User-agent: *\nDisallow:\n"
ROBOTS_DRUPAL = fixture("robots/drupal.txt")


@pytest.fixture(scope="module")
def lieux(tmp_path_factory):
    con = db.connect(tmp_path_factory.mktemp("probe") / "p.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    yield {r["id"]: r for r in con.execute("SELECT * FROM lieux")}
    con.close()


def api(domaines: dict[str, list[str]]):
    """Fausse API Que Faire à Paris : domaine cherché -> liens contact_url renvoyés."""
    def repondre(requete: httpx.Request) -> httpx.Response:
        where = requete.url.params["where"]
        for domaine, liens in domaines.items():
            if f'"{domaine}"' in where:
                return httpx.Response(200, json={"results": [{"contact_url": l, "access_link": None, "address_url": None} for l in liens]})
        return httpx.Response(200, json={"results": []})
    return repondre


API = QueFaireAParis.url
ROBOTS_API = {"https://opendata.paris.fr/robots.txt": ROBOTS_LIBRE}


def lieu_synthetique(lieux, **champs):
    base = dict(lieux["musee-de-la-vie-romantique"])
    base.update(champs)
    return base


def test_t0_quand_le_domaine_est_dans_l_agenda_de_la_ville(lieux, faux_client):
    client, reseau = faux_client({
        "https://www.mahj.org/robots.txt": ROBOTS_DRUPAL, **ROBOTS_API,
        API: api({"mahj.org": ["https://www.mahj.org/fr/programme/georges-kars-un-bohemien-paris-32135"]}),
    })
    s = sonder(lieux["musee-d-art-et-d-histoire-du-judaisme"], client)
    assert (s.tier, s.statut, s.url_utile) == ("T0", "ok", API)
    assert "1 événement(s) de mahj.org" in s.preuve
    assert not any("programme" in c for c in reseau.chemins)   # la page du musée n'est pas téléchargée


def test_t0_ne_confond_pas_un_article_de_paris_fr_avec_le_musee(lieux, faux_client):
    """La recherche plein texte découpe les URL en mots : on revérifie l'hôte."""
    lieu = lieu_synthetique(lieux, expos_url="https://www.carnavalet.paris.fr/expositions/expositions-en-cours",
                            tier=None, plateforme_billetterie=None)
    client, _ = faux_client({
        "https://www.carnavalet.paris.fr/robots.txt": ROBOTS_DRUPAL, **ROBOTS_API,
        API: api({"carnavalet.paris.fr": ["https://www.paris.fr/pages/carnavalet-rouvre"]}),
        "https://www.carnavalet.paris.fr/expositions/expositions-en-cours": "<html></html>",
        "https://www.carnavalet.paris.fr/sitemap.xml": (404, {}, ""),
    })
    assert sonder(lieu, client).tier == "T3"


def test_api_injoignable_ne_bloque_pas_la_sonde(lieux, faux_client):
    def coupe(r):
        raise httpx.ConnectError("reset")
    client, _ = faux_client({
        "https://www.imarabe.org/robots.txt": ROBOTS_DRUPAL, **ROBOTS_API, API: coupe,
        "https://www.imarabe.org/fr/agenda/expositions-musee": fixture("pages/ima_expositions.html"),
        "https://www.imarabe.org/sitemap.xml": "<urlset></urlset>",
    })
    s = sonder(lieux["musee-de-l-institut-du-monde-arabe"], client)
    assert s.tier == "T1" and "sitemap" in s.preuve   # la page IMA ne porte ni JSON-LD, ni RSS, ni .ics
    assert any("injoignable" in n for n in s.notes)


PAGE_VIDE = "<html><head><title>x</title></head><body></body></html>"


def sonde_sur_page(lieux, faux_client, page: str, **champs):
    lieu = lieu_synthetique(lieux, expos_url="https://m.test/expos", tier=None, plateforme_billetterie=None, **champs)
    client, _ = faux_client({"https://m.test/robots.txt": ROBOTS_LIBRE, **ROBOTS_API, API: api({}),
                             "https://m.test/expos": page, "https://m.test/sitemap.xml": (404, {}, "")})
    return sonder(lieu, client)


def test_jsonld_event(lieux, faux_client):
    page = ('<html><head><script type="application/ld+json">{"@graph":[{"@type":"WebSite"},'
            '{"@type":["ExhibitionEvent"],"name":"Expo test"}]}</script></head></html>')
    s = sonde_sur_page(lieux, faux_client, page)
    assert (s.tier, s.preuve) == ("T1", "JSON-LD Event « Expo test » dans la page")


def test_jsonld_sans_event_ne_compte_pas(lieux, faux_client):
    page = '<html><head><script type="application/ld+json">{"@type":"Organization"}</script></head></html>'
    assert sonde_sur_page(lieux, faux_client, page).tier == "T3"


def test_jsonld_illisible_est_ignore(lieux, faux_client):
    page = '<html><head><script type="application/ld+json">{pas du json</script></head></html>'
    assert sonde_sur_page(lieux, faux_client, page).tier == "T3"


def test_flux_rss(lieux, faux_client):
    page = '<html><head><link rel="alternate" type="application/rss+xml" href="/?page=backend"></head></html>'
    s = sonde_sur_page(lieux, faux_client, page)
    assert (s.tier, s.url_utile) == ("T1", "https://m.test/?page=backend")


def test_calendrier_ics_par_lien_et_par_webcal(lieux, faux_client):
    s = sonde_sur_page(lieux, faux_client, '<a href="/agenda/export.ics?x=1">agenda</a>')
    assert (s.tier, s.url_utile) == ("T1", "https://m.test/agenda/export.ics?x=1")
    s = sonde_sur_page(lieux, faux_client, '<a href="webcal://m.test/cal.ics">agenda</a>')
    assert s.url_utile == "https://m.test/cal.ics"


def test_billetterie_mutualisee_vue_sur_la_page_mahj(lieux, faux_client):
    client, _ = faux_client({
        "https://www.mahj.org/robots.txt": ROBOTS_DRUPAL, **ROBOTS_API, API: api({}),
        lieux["musee-d-art-et-d-histoire-du-judaisme"]["expos_url"]: fixture("pages/mahj_agenda.html"),
    })
    s = sonder(lieux["musee-d-art-et-d-histoire-du-judaisme"], client)
    assert s.tier == "T2" and "Tickeasy / Vivaticket (mahj.tickeasy.com)" in s.preuve


def test_billetterie_declaree_dans_la_base_si_la_page_n_en_parle_pas(lieux, faux_client):
    lieu = lieu_synthetique(lieux, expos_url="https://m.test/expos", tier=None,
                            plateforme_billetterie="mahj.tickeasy.com (Vivaticket)")
    client, _ = faux_client({"https://m.test/robots.txt": ROBOTS_LIBRE, **ROBOTS_API, API: api({}), "https://m.test/expos": PAGE_VIDE})
    s = sonder(lieu, client)
    assert s.tier == "T2" and "déclarée dans la base" in s.preuve


def test_sitemap_annonce_par_robots_txt(lieux, faux_client):
    lieu = lieu_synthetique(lieux, expos_url="https://www.museedemontmartre.fr/x", tier=None, plateforme_billetterie=None)
    client, _ = faux_client({
        "https://www.museedemontmartre.fr/robots.txt": fixture("robots/museedemontmartre.txt"), **ROBOTS_API, API: api({}),
        "https://www.museedemontmartre.fr/x": PAGE_VIDE,
        "https://www.museedemontmartre.fr/sitemap.xml": '<?xml version="1.0"?><urlset xmlns="x"><url/></urlset>',
    })
    s = sonder(lieu, client)
    assert (s.tier, s.url_utile) == ("T1", "https://www.museedemontmartre.fr/sitemap.xml")


def test_t3_quand_rien_n_est_structure(lieux, faux_client):
    s = sonde_sur_page(lieux, faux_client, PAGE_VIDE)
    assert (s.tier, s.statut) == ("T3", "ok")


def test_robots_qui_interdit_donne_t4_sans_telecharger_la_page(lieux, faux_client):
    lieu = lieu_synthetique(lieux, expos_url="https://m.test/expos", tier=None)
    client, reseau = faux_client({"https://m.test/robots.txt": "User-agent: *\nDisallow: /\n"})
    s = sonder(lieu, client)
    assert (s.tier, s.statut) == ("T4", "ok") and "interdit" in s.preuve
    assert reseau.chemins == ["m.test/robots.txt"]


def test_t4_enregistre_est_verrouille_meme_si_robots_autorise(lieux, faux_client):
    """Cas Montmartre : le brief dit T4 définitif, le robots.txt actuel n'interdit rien."""
    client, reseau = faux_client({"https://museedemontmartre.fr/robots.txt": (302, {"location": "https://www.museedemontmartre.fr/robots.txt"}, ""),
                                  "https://www.museedemontmartre.fr/robots.txt": fixture("robots/museedemontmartre.txt")})
    s = sonder(lieux["musee-de-montmartre"], client)
    assert (s.tier, s.statut, s.concorde if hasattr(s, "concorde") else True) == ("T4", "verrouille", True)
    assert any("T4 est maintenu" in n for n in s.notes)
    assert set(reseau.chemins) == {"museedemontmartre.fr/robots.txt", "www.museedemontmartre.fr/robots.txt"}  # rien d'autre


def test_site_en_maintenance_est_indetermine_pas_t4(lieux, faux_client):
    client, reseau = faux_client({"https://museevieromantique.paris.fr/robots.txt": (503, {"retry-after": "3600"}, "Maintenance")})
    s = sonder(lieux["musee-de-la-vie-romantique"], client)
    assert (s.tier, s.statut) == (None, "indetermine") and "503" in s.preuve
    assert reseau.chemins == ["museevieromantique.paris.fr/robots.txt"]


def test_refus_du_serveur_pas_de_contournement(lieux, faux_client):
    lieu = lieu_synthetique(lieux, expos_url="https://m.test/expos", tier=None)
    client, _ = faux_client({"https://m.test/robots.txt": ROBOTS_LIBRE, **ROBOTS_API, API: api({}), "https://m.test/expos": (403, {}, "bot")})
    s = sonder(lieu, client)
    assert (s.tier, s.statut) == (None, "indetermine") and "403" in s.preuve


def test_page_404_repli_sur_l_accueil(lieux, faux_client):
    lieu = lieu_synthetique(lieux, expos_url="https://m.test/vieille-url", tier=None, plateforme_billetterie=None)
    client, _ = faux_client({"https://m.test/robots.txt": ROBOTS_LIBRE, **ROBOTS_API, API: api({}),
                             "https://m.test/vieille-url": (404, {}, ""), "https://m.test/": PAGE_VIDE,
                             "https://m.test/sitemap.xml": (404, {}, "")})
    s = sonder(lieu, client)
    assert s.tier == "T3" and any("repli sur la page d'accueil" in n for n in s.notes)


def test_lieu_sans_url(lieux, faux_client):
    client, reseau = faux_client({})
    s = sonder(lieux["musee-d-orsay"], client)
    assert (s.tier, s.statut) == (None, "indetermine") and reseau.vues == []


def test_signaux_sur_des_pages_reelles():
    """Pages enregistrées le 2026-10-29 : aucune n'expose de JSON-LD Event, de RSS ni de .ics."""
    pages = {"cartier_en_ce_moment": "https://www.fondationcartier.com/", "bourse_programme": "https://www.pinaultcollection.com/",
             "ima_expositions": "https://www.imarabe.org/", "mahj_agenda": "https://www.mahj.org/",
             "carnavalet_expositions_en_cours": "https://www.carnavalet.paris.fr/"}
    for nom, base in pages.items():
        sig = signaux(fixture(f"pages/{nom}.html"), base)
        assert (sig["jsonld"], sig["rss"], sig["ics"]) == (None, None, None), nom
    # seules deux billetteries sont mutualisées : Tickeasy (mahJ) et Paris Musées (Carnavalet)
    assert signaux(fixture("pages/mahj_agenda.html"), "https://www.mahj.org/")["billetteries"][0][0] == "Tickeasy / Vivaticket"
    assert signaux(fixture("pages/carnavalet_expositions_en_cours.html"), "https://www.carnavalet.paris.fr/")["billetteries"][0][0] == "billetterie Paris Musées"
    assert signaux(fixture("pages/bourse_programme.html"), "https://www.pinaultcollection.com/")["billetteries"] == []


def test_sortie_json(lieux, faux_client):
    s = sonde_sur_page(lieux, faux_client, PAGE_VIDE)
    sortie = json.loads(json.dumps(s.en_json(), ensure_ascii=False))
    assert set(sortie) >= {"lieu", "tier", "preuve", "url_utile"} and sortie["concorde"] is None  # tier enregistré vide
