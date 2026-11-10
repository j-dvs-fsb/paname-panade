"""Chaque site configuré, sur sa page réelle enregistrée le 2026-10-29."""
import json
from datetime import date

import pytest

from panade.extractors import generique
from panade.extractors.generique import extraire_avec
from panade.extractors.sites import SITES

from conftest import FIXTURES

AUJ = date(2026, 10, 29)
ATTENDUS = json.loads((FIXTURES / "sites" / "attendus.json").read_text(encoding="utf-8"))


def page(lid):
    ext = "json" if SITES[lid].get("json_html") else "html"
    return (FIXTURES / "sites" / f"{lid}.{ext}").read_text(encoding="utf-8")


@pytest.mark.parametrize("lid", sorted(SITES))
def test_chaque_site_sur_sa_page_reelle(lid):
    expos = generique.extraire_pour(lid, page(lid), SITES[lid]["liste"], AUJ)
    assert len(expos) == ATTENDUS[lid]
    for e in expos:
        assert e.titre and e.url and e.url.startswith("http")
        assert e.date_debut or e.date_fin                     # jamais une carte sans date
        assert not e.date_fin or e.date_fin >= AUJ.isoformat()  # jamais une exposition terminée
        assert not any(m in (e.description or "").lower() for m in ("gratuit", "tarif", "€"))


def test_couverture_minimale():
    assert sum(1 for n in ATTENDUS.values() if n) >= 25


@pytest.mark.parametrize("lid, titres", [
    ("musee-du-louvre", {"Zurbarán", "Sculpter la couleur", "Louvre Photo"}),
    ("musee-de-l-institut-du-monde-arabe", {"Vive la mariée !", "Les secrets de l'Alhambra"}),
    ("pantheon", {"Marc Bloch, l’esprit de l’Histoire", "Vies minuscules"}),
    ("bourse-de-commerce-pinault-collection", {"Remember Me", "Nan Goldin. Stendhal Syndrome"}),
    ("musee-des-arts-asiatiques-guimet", {"Le savoir en trompe-l’œil. Corée, 18e-20e s."}),     # pas le surtitre
    ("musee-national-de-l-histoire-et-des-cultures-de-l-immigratio", {"Une histoire du cinéma français"}),
])
def test_titres_connus(lid, titres):
    assert titres <= {e.titre for e in generique.extraire_pour(lid, page(lid), SITES[lid]["liste"], AUJ)}


def test_dates_ima_en_deux_morceaux():
    e = {x.titre: x for x in generique.extraire_pour("musee-de-l-institut-du-monde-arabe", page("musee-de-l-institut-du-monde-arabe"),
                                                    SITES["musee-de-l-institut-du-monde-arabe"]["liste"], AUJ)}
    assert (e["Vive la mariée !"].date_debut, e["Vive la mariée !"].date_fin) == ("2026-09-29", "2027-02-28")


def test_monuments_cmn_les_visites_ne_sont_pas_des_expositions():
    titres = {e.titre for e in generique.extraire_pour("pantheon", page("pantheon"), SITES["pantheon"]["liste"], AUJ)}
    assert not any("visite" in t.lower() or t.startswith("Les femmes") for t in titres)


def test_un_mot_d_activite_au_milieu_d_un_titre_ne_l_ecarte_pas():
    html = '<main><div><a href="/expositions/x"><h3>Une histoire du cinéma</h3></a><p>Du 1 mars 2027 au 2 mai 2027</p></div></main>'
    assert len(extraire_avec({}, html, "https://m.test/expositions", AUJ)) == 1
    html = html.replace("Une histoire du cinéma", "Visite guidée de l'exposition")
    assert extraire_avec({}, html, "https://m.test/expositions", AUJ) == []


def test_pied_de_page_ignore_dans_le_repli():
    html = '<body><div><a href="/x"><h3>Vraie</h3></a><p>Du 1 mars 2027 au 2 mai 2027</p></div>' \
           '<footer><a href="/contact">Contact</a><p>Fermé le 1er mai 2027</p></footer></body>'
    assert [e.titre for e in extraire_avec({}, html, "https://m.test/", AUJ)] == ["Vraie"]


def test_liens_de_rubrique_et_fichiers_ignores():
    html = ('<main><article><a href="/agenda/expo-a"><h3>Expo A</h3></a><a href="/agenda/types/exposition">Exposition</a>'
            '<a href="/agenda/publics/tous">Tous</a><p>Jusqu\'au 3 janvier 2027</p></article>'
            '<div><a href="/doc.pdf">Communiqué</a><p>Du 1 mars 2027 au 2 mai 2027</p></div></main>')
    assert [e.titre for e in extraire_avec({}, html, "https://m.test/agenda", AUJ)] == ["Expo A"]


def test_source_json_illisible():
    assert extraire_avec({"json_html": "data"}, "pas du json", "https://m.test/", AUJ) == []
