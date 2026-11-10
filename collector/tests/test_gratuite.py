import json
from datetime import date

import pytest

from panade import db, gratuite, seed
from panade.gratuite import Famille, Lieu, Tarif, calculer

from conftest import CLASSEUR

AUJ = date(2026, 10, 29)
RECENT = "2026-09-19"

FAMILLES = {
    "paris_musees": Famille("paris_musees", "Gratuit pour tous", "Payant pour tous (gratuit -18 ans)", None,
                            "Collections permanentes en accès libre, sans réservation"),
    "musee_national": Famille("musee_national", "Gratuit", "Variable selon l'établissement", 26,
                              "Résident de longue durée UE/EEE, pièce d'identité exigée"),
    "cmn": Famille("cmn", "Gratuit", "Généralement inclus dans le billet", 26, "Résident de longue durée UE/EEE"),
    "militaire": Famille("militaire", "À VÉRIFIER", "À VÉRIFIER"),
    "prive_assoc": Famille("prive_assoc", "À VÉRIFIER", "À VÉRIFIER"),
    "autre_public": Famille("autre_public", "À VÉRIFIER", "À VÉRIFIER"),
}


def lieu(famille="paris_musees", tarifs=(), **kw):
    return Lieu("test", FAMILLES[famille], tarifs=tuple(tarifs), **kw)


def tarif(portee="tout", regime="gratuit", audience="moins_26", prix=0, plein=15, rec="toujours", just=None, verifie=RECENT):
    return Tarif(portee, regime, audience, prix, plein, rec, just, verifie)


# --- une famille, un cas ---------------------------------------------------------------

@pytest.mark.parametrize("famille, portee, statut", [
    ("paris_musees", "permanent", "gratuit_tous"),
    ("paris_musees", "temporaire", "payant"),             # le piège central : permanent gratuit, temporaire payant
    ("musee_national", "permanent", "gratuit_26"),
    ("musee_national", "temporaire", "a_confirmer"),      # « variable selon l'établissement »
    ("cmn", "permanent", "gratuit_26"),
    ("cmn", "temporaire", "a_confirmer"),                 # « généralement inclus dans le billet »
    ("militaire", "permanent", "a_confirmer"),
    ("militaire", "temporaire", "a_confirmer"),
    ("prive_assoc", "permanent", "a_confirmer"),
    ("prive_assoc", "temporaire", "a_confirmer"),
    ("autre_public", "permanent", "a_confirmer"),
    ("autre_public", "temporaire", "a_confirmer"),
])
def test_une_famille_un_cas(famille, portee, statut):
    g = calculer(lieu(famille), portee, AUJ)
    assert g.statut == statut and g.source in ("famille", "tarifs")
    assert (g.prix == 0) == statut.startswith("gratuit")      # un gratuit est toujours un 0 explicite


def test_famille_nationale_sans_age_max_n_est_pas_devinee():
    g = calculer(Lieu("x", Famille("musee_national", "Gratuit", "Variable", None)), "permanent", AUJ)
    assert g.statut == "a_confirmer"


def test_rattachement_incertain_bloque_la_regle_de_la_famille():
    g = calculer(lieu("paris_musees", confiance_famille="a_confirmer"), "permanent", AUJ)
    assert g.statut == "a_confirmer" and "incertain" in g.raison


# --- l'override prime toujours ----------------------------------------------------------

@pytest.mark.parametrize("portee", ["permanent", "temporaire"])
def test_override_prime_sur_la_famille(portee):
    """Palais Galliera : la famille dit « gratuit pour tous » en permanent, le lieu dit le contraire."""
    g = calculer(lieu("paris_musees", gratuite_override="EXCEPTION : tout est payant. A verifier."), portee, AUJ)
    assert g.statut == "a_confirmer" and g.source == "override" and "EXCEPTION" in g.raison


def test_override_ne_masque_pas_des_tarifs_verifies():
    g = calculer(lieu("paris_musees", gratuite_override="exception", tarifs=[tarif(portee="permanent", audience="tous")]),
                 "permanent", AUJ)
    assert (g.statut, g.source) == ("gratuit_tous", "tarifs")


# --- les cas limites du brief -------------------------------------------------------------

def test_mahj_et_musee_de_la_musique_permanent_gratuit_temporaire_reduit():
    rows = [tarif(portee="permanent", audience="moins_26_ue", just="Collections permanentes uniquement"),
            tarif(portee="temporaire", regime="reduit", audience="moins_26", prix=5, plein=12)]
    permanent = calculer(lieu("prive_assoc", rows), "permanent", AUJ)
    temporaire = calculer(lieu("prive_assoc", rows), "temporaire", AUJ)
    assert (permanent.statut, permanent.prix) == ("gratuit_26", 0)
    assert (temporaire.statut, temporaire.prix, temporaire.plein_tarif) == ("reduit_26", 5, 12)


def test_gratuit_pour_tous_contredit_par_un_tarif_moins_26_payant():
    rows = [tarif(portee="temporaire", audience="tous"), tarif(portee="temporaire", regime="reduit", audience="moins_26_ue", prix=5)]
    g = calculer(lieu("prive_assoc", rows), "temporaire", AUJ)
    assert g.statut == "a_confirmer" and "contradictoires" in g.raison


def test_creneaux_particuliers_ne_font_pas_le_prix_de_base():
    rows = [tarif(portee="temporaire", audience="moins_26", rec="apres_16h"),
            tarif(portee="temporaire", regime="reduit", audience="moins_26", prix=10),
            tarif(portee="temporaire", regime="reduit", audience="moins_26", prix=7.5, rec="avant_16h")]
    g = calculer(lieu("prive_assoc", rows), "temporaire", AUJ)
    assert (g.statut, g.prix) == ("reduit_26", 10)
    assert ("moins_26", "gratuit", 0, "apres_16h") in g.creneaux      # affiché, mais pas la règle de base


def test_seuls_des_creneaux_connus_donne_a_confirmer():
    g = calculer(lieu("prive_assoc", [tarif(portee="temporaire", audience="moins_26", rec="apres_16h")]), "temporaire", AUJ)
    assert g.statut == "a_confirmer" and g.creneaux


def test_ligne_limitee_a_une_partie_de_l_offre_est_ecartee():
    """« Jardins Renoir seuls : 5 € » n'est pas le prix du musée."""
    rows = [tarif(portee="tout", regime="reduit", audience="tous", prix=5, plein=15, just="Jardins Renoir seuls : 5 EUR")]
    g = calculer(lieu("prive_assoc", rows), "temporaire", AUJ)
    assert g.statut == "a_confirmer" and "limité à une partie" in g.raison


def test_uniquement_est_inoffensif_sur_une_ligne_de_portee_permanent():
    g = calculer(lieu("prive_assoc", [tarif(portee="permanent", audience="moins_26_ue", just="Collections permanentes uniquement")]),
                 "permanent", AUJ)
    assert g.statut == "gratuit_26"


def test_ligne_marquee_a_verifier_est_ecartee():
    g = calculer(lieu("prive_assoc", [tarif(portee="temporaire", regime="reduit", audience="tous", prix=16, plein=16,
                                           just="A VERIFIER : billet combiné musée + expo")]), "temporaire", AUJ)
    assert g.statut == "a_confirmer" and "marqué à vérifier" in g.raison


def test_tarif_reduit_pour_tous_egal_au_plein_tarif_est_payant():
    g = calculer(lieu("prive_assoc", [tarif(portee="temporaire", regime="reduit", audience="tous", prix=16, plein=16)]),
                 "temporaire", AUJ)
    assert (g.statut, g.prix) == ("payant", 16)


def test_prix_inconnu_reste_inconnu():
    g = calculer(lieu("paris_musees", [tarif(portee="temporaire", regime="reduit", audience="tous", prix=None, plein=None)]),
                 "temporaire", AUJ)
    assert g.statut == "payant" and g.prix is None


# --- jamais de gratuité sans donnée vérifiée --------------------------------------------------

def test_tarif_non_verifie_ne_donne_jamais_gratuit():
    g = calculer(lieu("prive_assoc", [tarif(portee="permanent", audience="tous", verifie=None)]), "permanent", AUJ)
    assert g.statut == "a_confirmer" and "non vérifié" in g.raison


def test_tarif_perime_ne_donne_jamais_gratuit():
    vieux = "2026-06-01"        # 150 jours avant le 2026-10-29
    g = calculer(lieu("prive_assoc", [tarif(portee="permanent", audience="tous", verifie=vieux)]), "permanent", AUJ)
    assert g.statut == "a_confirmer" and "périmé" in g.raison
    limite = tarif(portee="permanent", audience="tous", verifie="2026-07-01")   # exactement 120 jours : encore valable
    assert calculer(lieu("prive_assoc", [limite]), "permanent", AUJ).statut == "gratuit_tous"


def test_audience_hors_reference_ne_compte_pas():
    rows = [tarif(portee="permanent", audience=a) for a in ("moins_18", "demandeur_emploi", "minima_sociaux", "etudiant")]
    assert calculer(lieu("prive_assoc", rows), "permanent", AUJ).statut == "a_confirmer"


def test_abonnement_n_est_pas_un_prix_de_visite():
    g = calculer(lieu("prive_assoc", [tarif(portee="tout", regime="abonnement", audience="18_29_ans", prix=20)]), "temporaire", AUJ)
    assert g.statut == "a_confirmer"


def test_portee_inconnue_refusee():
    with pytest.raises(ValueError):
        calculer(lieu(), "tout", AUJ)


def test_serialisation_deterministe_et_sans_valeur_vide():
    rows = [tarif(portee="temporaire", regime="reduit", audience="moins_30", prix=10, plein=15, just="Pièce d'identité")]
    a = calculer(lieu("prive_assoc", rows), "temporaire", AUJ).en_json()
    b = calculer(lieu("prive_assoc", list(reversed(rows))), "temporaire", AUJ).en_json()
    assert a == b and None not in json.loads(a).values()
    assert json.loads(a) == {"audience": "moins_30", "justificatif": "Pièce d'identité", "plein_tarif": 15, "prix": 10,
                             "raison": "ligne de tarif vérifiée (moins_30, toujours)", "source": "tarifs", "statut": "reduit_26"}


# --- balayage structurel sur la vraie graine ------------------------------------------------------

@pytest.fixture(scope="module")
def graine(tmp_path_factory):
    con = db.connect(tmp_path_factory.mktemp("g") / "g.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    yield con
    con.close()


def test_aucun_gratuit_sans_ligne_verifiee_ni_regle_reconnue(graine):
    """Sur les 57 lieux et les deux portées : tout « gratuit » s'explique par une ligne vérifiée ou une règle de famille nommée."""
    gratuits = 0
    for (lid,) in graine.execute("SELECT id FROM lieux"):
        l = gratuite.charger(graine, lid)
        for portee in ("permanent", "temporaire"):
            g = calculer(l, portee, AUJ)
            assert g.statut in gratuite.STATUTS
            if g.statut.startswith("gratuit"):
                gratuits += 1
                assert g.prix == 0 and g.source in ("tarifs", "famille")
                if g.source == "famille":
                    assert l.gratuite_override is None and l.confiance_famille == "sur"
                    assert getattr(l.famille, f"gratuite_{portee}") in ("Gratuit pour tous", "Gratuit")
                else:
                    assert any(t.regime == "gratuit" and t.verifie_le for t in l.tarifs)
    assert gratuits > 20          # le balayage a bien rencontré des gratuits


def test_verdicts_sur_les_cas_reels_de_la_graine(graine):
    def v(lid, portee):
        return calculer(gratuite.charger(graine, lid), portee, AUJ).statut
    assert v("musee-d-art-et-d-histoire-du-judaisme", "permanent") == "gratuit_26"
    assert v("musee-d-art-et-d-histoire-du-judaisme", "temporaire") == "a_confirmer"
    assert v("musee-de-la-musique", "permanent") == "gratuit_26"
    assert v("musee-de-la-musique", "temporaire") == "reduit_26"
    assert v("palais-galliera-musee-de-la-mode-et-de-la-ville-de-paris", "permanent") == "a_confirmer"
    assert v("crypte-archeologique-de-l-ile-de-la-cite", "permanent") == "a_confirmer"
    assert v("musee-carnavalet-histoire-de-paris", "permanent") == "gratuit_tous"
    assert v("musee-carnavalet-histoire-de-paris", "temporaire") == "payant"
    assert v("fondation-cartier-pour-l-art-contemporain", "temporaire") == "reduit_26"
    assert v("musee-des-arts-decoratifs-union-centrale-des-arts-decoratifs", "temporaire") == "gratuit_26"
    assert v("musee-de-montmartre", "temporaire") == "a_confirmer"
