from datetime import date

import pytest

from panade.dates_fr import Periode, analyser

AUJOURDHUI = date(2026, 10, 29)


@pytest.mark.parametrize("texte, attendu", [
    ("15 septembre 2026 - 24 janvier 2027", Periode("2026-09-15", "2027-01-24")),
    (" 20 octobre 2026 - 24 janvier 2027", Periode("2026-10-20", "2027-01-24")),
    ("du 3 mars au 12 juillet 2026", Periode("2026-03-03", "2026-07-12")),
    ("Du 1er octobre 2026 au 3 février 2027", Periode("2026-10-01", "2027-02-03")),
    ("du 12 novembre au 3 février 2027", Periode("2026-11-12", "2027-02-03")),
    ("jusqu'au 13 décembre 2026", Periode(None, "2026-12-13")),
    ("Jusqu’au 13 décembre", Periode(None, "2026-12-13", annee_deduite=True)),
    ("à partir du 10 novembre 2026", Periode("2026-11-10", None)),
    ("14 octobre 2026", Periode("2026-10-14", None)),
    ("5 août 2026 \u2013 4 oct 2026", Periode("2026-08-05", "2026-10-04")),
    ("01 janv. 2026 31 déc. 2026", Periode("2026-01-01", "2026-12-31")),   # séparées par une icône, années écrites
    ("du 12 mars 3 avril", Periode("2026-03-12", None, annee_deduite=True)),    # sans années ni séparateur : pas d'intervalle
    ("01 janv. 2026 - 31 déc. 2026", Periode("2026-01-01", "2026-12-31")),
    ("Du 14/10/2026 au 04/04/2027", Periode("2026-10-14", "2027-04-04")),
    ("19 Sep au 1 nov 2026", Periode("2026-09-19", "2026-11-01")),
    ("du 3 mars au 12 juillet", Periode("2026-03-03", "2026-07-12", annee_deduite=True)),
    ("24 jan 2026 au 2 jan 2027", Periode("2026-01-24", "2027-01-02")),
    ("17.06 au 28.09.2026", Periode("2026-06-17", "2026-09-28")),
    ("DU 03.09 AU 20.12.26", Periode("2026-09-03", "2026-12-20")),
    ("jusqu'au 12/01/2027", Periode(None, "2027-01-12")),
    ("le 12.03.2027 à 18h", Periode("2027-03-12", None)),
])
def test_periodes(texte, attendu):
    assert analyser(texte, AUJOURDHUI) == attendu


def test_jusqu_au_sans_annee_vu_en_janvier_vise_l_annee_suivante():
    # le 2 janvier, « jusqu'au 13 décembre » parle de la fin d'année qui vient
    assert analyser("jusqu'au 13 décembre", date(2027, 1, 2)) == Periode(None, "2027-12-13", annee_deduite=True)


def test_jusqu_au_sans_annee_recent_reste_dans_l_annee():
    assert analyser("jusqu'au 3 octobre", date(2026, 10, 29)) == Periode(None, "2026-10-03", annee_deduite=True)


@pytest.mark.parametrize("texte", ["", "Entrée gratuite", "31 février 2026", "ouvert toute l'année",
                                   "ouvert de 10.30 à 18.00", "version 1.2.3", "le 12/03 à 18h", "13/45/2026", "octobre"])
def test_rien_de_devine(texte):
    assert analyser(texte, AUJOURDHUI) is None


@pytest.mark.parametrize("tiret", ["-", "\u2013", "\u2014"])
def test_les_trois_tirets_separent_deux_dates(tiret):
    assert analyser(f"15 septembre 2026 {tiret} 24 janvier 2027", AUJOURDHUI) == Periode("2026-09-15", "2027-01-24")


def test_intervalle_inverse_est_refuse():
    assert analyser("du 12 juillet 2026 au 3 mars 2026", AUJOURDHUI) is None
