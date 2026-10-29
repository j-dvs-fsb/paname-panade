from datetime import date

import pytest

from panade import db, discover, seed

from conftest import CLASSEUR, fixture

ROBOTS = "User-agent: *\nDisallow:\n"


@pytest.fixture(scope="module")
def lieux(tmp_path_factory):
    con = db.connect(tmp_path_factory.mktemp("disc") / "d.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    yield {r["id"]: r for r in con.execute("SELECT * FROM lieux")}
    con.close()


def test_trouve_le_bon_chemin_et_garde_une_fixture(lieux, faux_client, tmp_path):
    base = "https://www.carnavalet.paris.fr"
    client, reseau = faux_client({
        f"{base}/robots.txt": ROBOTS,
        f"{base}/expositions/expositions-en-cours": fixture("pages/carnavalet_expositions_en_cours.html"),
    })
    d = discover.decouvrir(lieux["musee-carnavalet-histoire-de-paris"], client, tmp_path, date(2026, 10, 29))
    assert (d.statut, d.extracteur, d.expositions) == ("ok", "paris_musees", 4)
    assert d.url_demandee == f"{base}/expositions/expositions-en-cours"
    assert (tmp_path / "musee-carnavalet-histoire-de-paris.html").read_text().startswith("<")
    assert reseau.chemins == ["www.carnavalet.paris.fr/robots.txt", "www.carnavalet.paris.fr/expositions/expositions-en-cours"]


def test_chemin_variable_lu_dans_le_menu_de_la_page_404(lieux, faux_client, tmp_path):
    """Petit Palais : aucun des trois chemins connus, le bon est dans le menu de la page 404."""
    base = "https://www.petitpalais.paris.fr"
    menu = '<html><body><nav><a href="/decouvrir-la-programmation/expositions">Expositions</a><a href="/visiter">Visiter</a></nav></body></html>'
    client, reseau = faux_client({
        f"{base}/robots.txt": ROBOTS,
        f"{base}/expositions/expositions-en-cours": (404, {}, menu),
        f"{base}/expositions/exposition-en-cours": (404, {}, menu),
        f"{base}/visiter/expositions/expositions-en-cours": (404, {}, menu),
        f"{base}/decouvrir-la-programmation/expositions": fixture("pages/petitpalais_expositions.html"),
    })
    d = discover.decouvrir(lieux["petit-palais-musee-des-beaux-arts-de-la-ville-de-paris"], client, tmp_path, date(2026, 10, 29))
    assert (d.statut, d.expositions) == ("ok", 3)
    assert d.url_demandee == f"{base}/decouvrir-la-programmation/expositions"


def test_site_en_maintenance_n_ecrit_rien(lieux, faux_client, tmp_path):
    client, _ = faux_client({"https://museevieromantique.paris.fr/robots.txt": (503, {}, "Maintenance")})
    d = discover.decouvrir(lieux["musee-de-la-vie-romantique"], client, tmp_path, date(2026, 10, 29))
    assert d.statut == "echec" and "503" in d.detail and list(tmp_path.iterdir()) == []


def test_lieu_t4_rien_n_est_telecharge(lieux, faux_client, tmp_path):
    client, reseau = faux_client({})
    d = discover.decouvrir(lieux["musee-de-montmartre"], client, tmp_path, date(2026, 10, 29))
    assert d.statut == "echec" and "T4" in d.detail and reseau.vues == []


def test_lieu_sans_extracteur_garde_quand_meme_la_fixture(lieux, faux_client, tmp_path):
    lieu = {**dict(lieux["musee-de-la-poste"]), "expos_url": "https://www.imarabe.org/fr/agenda/expositions-musee"}
    client, _ = faux_client({"https://www.imarabe.org/robots.txt": ROBOTS,
                             "https://www.imarabe.org/fr/agenda/expositions-musee": fixture("pages/ima_expositions.html")})
    d = discover.decouvrir(lieu, client, tmp_path, date(2026, 10, 29))
    assert d.statut == "ok" and d.extracteur is None and "pas d'extracteur" in d.detail
    assert d.octets_reduits <= d.octets_bruts   # la fixture de test est déjà réduite : idempotent
