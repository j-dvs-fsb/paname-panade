from datetime import date

from panade.apercu import diagnostiquer, libelle_dates, resume_horaires

AUJ = date(2026, 11, 10)
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def semaine(ouverture="10:00", fermeture="18:00", fermes=(1,), speciaux=None, portee="tout"):
    lignes = []
    for n, j in enumerate(JOURS, 1):
        if n in fermes:
            lignes.append({"jour_num": n, "jour": j, "ferme": True, "ouverture": None, "fermeture": None, "portee": portee})
        else:
            o, f = (speciaux or {}).get(n, (ouverture, fermeture))
            lignes.append({"jour_num": n, "jour": j, "ferme": False, "ouverture": o, "fermeture": f, "portee": portee})
    return lignes


def test_horaires_simples():
    assert resume_horaires(semaine(), AUJ) == "Du mardi au dimanche, 10h-18h ; fermé le lundi."


def test_nocturne_et_plage_a_cheval_sur_la_semaine():
    lignes = semaine("09:00", "18:00", fermes=(2,), speciaux={3: ("09:00", "21:00"), 5: ("09:00", "21:00")})
    assert resume_horaires(lignes, AUJ) == "Du mercredi au lundi, 9h-18h ; jusqu'à 21h les mercredi et vendredi ; fermé le mardi."


def test_creneaux_qui_se_touchent_fusionnes():
    lignes = semaine("12:00", "18:00") + [{"jour_num": 5, "jour": "vendredi", "ferme": False, "ouverture": "18:00",
                                          "fermeture": "20:00", "portee": "tout", "nocturne": True}]
    assert resume_horaires(lignes, AUJ) == "Du mardi au dimanche, 12h-18h ; jusqu'à 20h le vendredi ; fermé le lundi."


def test_lignes_hors_saison_et_autre_portee_ignorees():
    hiver = [dict(l, valide_du="2026-10-01", valide_au="2027-03-31") for l in semaine("11:00", "18:00", fermes=())]
    ete = [dict(l, valide_du="2027-04-01", valide_au="2027-09-30") for l in semaine("10:00", "18:00", fermes=())]
    assert resume_horaires(hiver + ete, AUJ) == "Tous les jours, 11h-18h."
    assert resume_horaires(semaine(portee="permanent"), AUJ, "temporaire") is None


def test_libelle_des_dates_comme_le_site():
    assert libelle_dates("2026-09-01", "2027-01-24") == "Du 1er septembre 2026 au 24 janvier 2027"
    assert libelle_dates(None, "2027-01-24") == "Jusqu'au 24 janvier 2027"
    assert libelle_dates("2026-12-05", None) == "À partir du 5 décembre 2026"
    assert libelle_dates(None, None, "permanent") == "En permanence"


LIEU = {"statut": "verifie", "nom": "Musée", "logo_url": None}
GRATUIT = '{"statut": "gratuit_26", "source": "tarifs", "raison": "ligne de tarif vérifiée"}'


def test_fiche_complete_tout_est_ok_sauf_la_reservation():
    expo = {"titre": "T", "url": "https://x", "image_url": "https://i", "description": "D", "portee": "temporaire",
            "date_debut": "2026-10-01", "date_fin": "2027-01-01",
            "provenance": '{"titre": "carte", "date_debut": "time", "date_fin": "time"}'}
    etats = diagnostiquer(expo, LIEU, GRATUIT, "Du mardi au dimanche, 10h-18h.", AUJ)
    assert {k for k, e in etats.items() if e.etat != "ok"} == {"reservation"}


def test_classeur_sans_confirmation_et_tarif_de_famille_en_orange():
    expo = {"titre": "T", "url": None, "image_url": None, "description": None, "portee": "temporaire",
            "date_debut": "2026-10-01", "date_fin": "2027-01-01", "provenance": None}
    famille = '{"statut": "reduit_26", "source": "famille", "raison": "règle de la famille"}'
    etats = diagnostiquer(expo, dict(LIEU, statut="a_verifier"), famille, None, AUJ)
    assert {k for k, e in etats.items() if e.etat == "manque"} == {"image", "description", "lien", "horaires"}
    assert {k for k, e in etats.items() if e.etat == "doute"} == {"lieu", "titre", "dates", "tarif", "reservation"}
    assert "venue du classeur" in etats["dates"].raison
