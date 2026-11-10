from datetime import date

import pytest

from panade import extractors
from panade.extractors import paris_musees as pm

from conftest import fixture


@pytest.fixture(autouse=True)
def sans_portail(monkeypatch):
    """Ces tests portent sur le lecteur du site propre d'un musée : le portail du réseau est mis de côté."""
    from panade.extractors import parismusees
    monkeypatch.setattr(parismusees, "MUSEES", {})


AUJOURDHUI = date(2026, 10, 29)
CARNAVALET = "https://www.carnavalet.paris.fr/expositions/expositions-en-cours"
PETIT_PALAIS = "https://www.petitpalais.paris.fr/decouvrir-la-programmation/expositions"
BOURDELLE = "https://www.bourdelle.paris.fr/visiter/expositions/letoffe-de-lartiste"


def lire(nom: str, url: str):
    return pm.extraire(fixture(f"pages/{nom}.html"), url, AUJOURDHUI)


def test_carnavalet_cartes_avec_time():
    expos = {e.titre: e for e in lire("carnavalet_expositions_en_cours", CARNAVALET)}
    assert len(expos) == 4
    e = expos["Paris à l’arraché"]
    assert (e.date_debut, e.date_fin) == ("2026-10-14", "2027-02-14")
    assert e.url == "https://www.carnavalet.paris.fr/expositions/paris-larrache"
    assert e.image_url.startswith("https://www.carnavalet.paris.fr/sites/default/files/")
    assert e.provenance["date_debut"] == "time"
    # les rubriques du menu (Prochaines expositions, Publications...) n'ont pas de date : ignorées
    assert not any("Publications" in t or "Prochaines" in t or "passées" in t for t in expos)


def test_petit_palais_dates_en_francais():
    expos = {e.titre: e for e in lire("petitpalais_expositions", PETIT_PALAIS)}
    assert set(expos) == {"Eva Gonzalès", "Visionnaires", "Bruxelles 1900"}
    assert (expos["Eva Gonzalès"].date_debut, expos["Eva Gonzalès"].date_fin) == ("2026-09-15", "2027-01-24")
    assert expos["Bruxelles 1900"].date_debut == "2026-11-10"     # à venir : conservée
    assert expos["Eva Gonzalès"].provenance["date_debut"] == "texte_fr"


def test_jamais_de_gratuite_lue_sur_la_page():
    """Invariant 1 : le badge « Gratuit » du Petit Palais et « Entrée gratuite » de Carnavalet disparaissent."""
    tout = lire("petitpalais_expositions", PETIT_PALAIS) + lire("carnavalet_expositions_en_cours", CARNAVALET)
    for e in tout:
        assert not any(m in (e.description or "").lower() for m in ("gratuit", "payant", "tarif", "entrée"))
        assert not hasattr(e, "gratuite")
    cain = next(e for e in tout if e.titre.startswith("En mémoire de Georges Cain"))
    assert cain.description == "Accrochage au sein des collections permanentes"


def test_fiche_unique_sans_date_lisible_reste_sans_date():
    """Bourdelle : la liste « en cours » redirige vers l'unique expo ; sa fiche ne donne aucune date."""
    expos = lire("bourdelle_fiche_etoffe", BOURDELLE)
    assert len(expos) == 1
    e = expos[0]
    assert e.titre == "L'étoffe de l'artiste"
    assert (e.date_debut, e.date_fin) == (None, None)       # ni nocturne (6 novembre) ni dateStart du JSON
    assert e.provenance["date_debut"] == "absente"
    assert e.image_url.startswith("https://www.bourdelle.paris.fr/") and "metatag" in e.image_url   # og:image
    assert "tarif" not in (e.description or "").lower()


def test_les_ateliers_d_une_fiche_ne_sont_pas_des_expositions():
    titres = [e.titre for e in lire("bourdelle_fiche_etoffe", BOURDELLE)]
    assert not any("atelier" in t.lower() or "visites guidées" in t.lower() for t in titres)


def carte(corps: str) -> str:
    return f'<html><body><main>{corps}</main></body></html>'


def test_exposition_passee_ignoree_et_a_venir_conservee():
    page = carte('''
      <div class="card"><a class="card-link" href="/expositions/vieille"><h5 class="card-title">Vieille</h5>
        <time datetime="2026-01-01T12:00:00Z">1</time><time datetime="2026-09-30T12:00:00Z">2</time></a></div>
      <div class="card"><a class="card-link" href="/expositions/future"><h5 class="card-title">Future</h5>
        <time datetime="2027-02-01T12:00:00Z">1</time><time datetime="2027-05-30T12:00:00Z">2</time></a></div>''')
    assert [e.titre for e in pm.extraire(page, CARNAVALET, AUJOURDHUI)] == ["Future"]


def test_activites_filtrees_par_categorie_et_par_lien():
    page = carte('''
      <div class="card"><a class="card-link" href="/expositions/a"><div class="meta-category">Atelier</div><h5 class="card-title">Atelier</h5>
        <time datetime="2027-02-01T12:00:00Z">1</time></a></div>
      <div class="card"><a class="card-link" href="/evenements-et-activites/agenda/visite-x"><h5 class="card-title">Visite</h5>
        <time datetime="2027-02-01T12:00:00Z">1</time></a></div>
      <div class="card"><a class="card-link" href="/expositions/vraie"><div class="meta-category">Exposition</div><h5 class="card-title">Vraie</h5>
        <time datetime="2027-02-01T12:00:00Z">1</time></a></div>''')
    assert [e.titre for e in pm.extraire(page, CARNAVALET, AUJOURDHUI)] == ["Vraie"]


def test_image_differee_lit_data_src_et_ignore_le_faux_src():
    page = carte('''<div class="card"><a class="card-link" href="/expositions/x"><h5 class="card-title">X</h5>
        <img src="/themes/rien.gif" data-src="/sites/default/files/vraie.jpg">
        <time datetime="2027-02-01T12:00:00Z">1</time></a></div>''')
    assert pm.extraire(page, CARNAVALET, AUJOURDHUI)[0].image_url == "https://www.carnavalet.paris.fr/sites/default/files/vraie.jpg"


def test_ancien_theme_showcase():
    page = carte('''<div class="showcase"><p class="title"><a href="/expositions/ancienne">Ancienne</a></p>
        <p class="author">Sous-titre</p><p class="category">Exposition</p>
        <figure><img src="/a.jpg"></figure>
        <span class="date-display-start" content="2027-01-01T00:00:00+01:00"><time datetime="2027-01-01T12:00:00Z">1 janvier</time></span></div>''')
    e = pm.extraire(page, CARNAVALET, AUJOURDHUI)[0]
    assert (e.titre, e.date_debut, e.description) == ("Ancienne", "2027-01-01", "Sous-titre")


def test_page_de_liste_vide_ne_renvoie_rien():
    assert pm.extraire(carte("<p>Aucune exposition en cours.</p>"), CARNAVALET, AUJOURDHUI) == []


def test_registre():
    lieu_pm = {"id": "musee-carnavalet-histoire-de-paris", "famille_id": "paris_musees", "expos_url": CARNAVALET, "tier": "T1"}
    assert extractors.choisir(lieu_pm)[0] == "paris_musees"
    assert extractors.choisir({**lieu_pm, "tier": "T4"}) is None         # T4 : jamais d'extracteur
    assert extractors.choisir({**lieu_pm, "expos_url": None}) is None
    assert extractors.choisir({**lieu_pm, "expos_url": "https://www.mam.paris.fr/"}) is None   # accueil : discover d'abord
    assert extractors.choisir({**lieu_pm, "famille_id": "cmn"}) is None
    assert extractors.choisir({**lieu_pm, "id": "musee-du-louvre", "famille_id": "musee_national"})[0] == "generique"


def test_un_accrochage_a_une_portee_incertaine_les_autres_non():
    """Gratuit si c'est dans les collections permanentes, payant sinon : on ne devine pas."""
    expos = {e.titre: e for e in lire("carnavalet_expositions_en_cours", CARNAVALET)}
    assert expos["Nouveau Paris, de 1977 à nos jours"].provenance["portee"] == "incertaine"
    assert expos["En mémoire de Georges Cain (1853-1919), refondateur du musée Carnavalet"].provenance["portee"] == "incertaine"
    assert "portee" not in expos["Paris à l’arraché"].provenance
    assert all(e.portee == "temporaire" for e in expos.values())     # la valeur par défaut reste la plus prudente
