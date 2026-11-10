import pytest

from panade.robots import Robots

from conftest import fixture


def test_drupal_interdit_core_mais_autorise_les_pages():
    r = Robots.lire(fixture("robots/drupal.txt"))
    assert r.autorise("PanadeCollector", "/expositions/expositions-en-cours")
    assert not r.autorise("PanadeCollector", "/core/install.php")
    assert not r.autorise("PanadeCollector", "/README.md")


def test_jokers_et_fin_de_motif_du_drupal():
    r = Robots.lire(fixture("robots/drupal.txt"))
    # Allow: /core/*.css$ est plus long que Disallow: /core/ ? Non : la règle la plus longue gagne.
    assert r.autorise("PanadeCollector", "/core/misc/style.css")
    assert not r.autorise("PanadeCollector", "/core/misc/style.css.map")


def test_montmartre_autorise_les_pages_publiques_et_interdit_les_chemins_listes():
    """Le brief dit « interdit les robots » : le fichier actuel dit autre chose (voir README)."""
    r = Robots.lire(fixture("robots/museedemontmartre.txt"))
    assert r.autorise("PanadeCollector", "/expositions-evenements/")
    assert not r.autorise("PanadeCollector", "/recherche")
    assert not r.autorise("PanadeCollector", "/qqch/index.php")
    assert r.sitemaps == ["https://www.museedemontmartre.fr/sitemap.xml"]


def test_disallow_vide_autorise_tout():
    assert Robots.lire(fixture("robots/fondationcartier.txt")).autorise("PanadeCollector", "/n-importe-quoi")


def test_interdiction_totale_et_groupe_specifique():
    r = Robots.lire("User-agent: *\nDisallow: /\n\nUser-agent: PanadeCollector\nAllow: /\nDisallow: /prive\n")
    assert r.autorise("PanadeCollector", "/expositions")
    assert not r.autorise("PanadeCollector", "/prive/x")
    assert not r.autorise("AutreRobot", "/expositions")


def test_a_longueur_egale_allow_l_emporte():
    r = Robots.lire("User-agent: *\nDisallow: /a\nAllow: /a\n")
    assert r.autorise("PanadeCollector", "/a")


def test_groupes_a_plusieurs_agents_et_commentaires():
    r = Robots.lire("# bonjour\nUser-agent: botA\nUser-agent: botB\nDisallow: /x # fin\n\nUser-agent: *\nDisallow:\n")
    assert not r.autorise("botA", "/x") and not r.autorise("botB", "/x")
    assert r.autorise("PanadeCollector", "/x")


@pytest.mark.parametrize("texte", ["", "n'importe quoi", "Disallow: /\n"])
def test_fichier_sans_groupe_utilisable_autorise(texte):
    assert Robots.lire(texte).autorise("PanadeCollector", "/x")
