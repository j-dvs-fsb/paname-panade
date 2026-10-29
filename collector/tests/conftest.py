from pathlib import Path

import pytest
from openpyxl import Workbook

from panade import db

CLASSEUR = Path(__file__).resolve().parents[1] / "data" / "PP_lieux_v2.xlsx"

ENTETES = {
    "Familles": ["famille_id", "libellé", "gratuite_permanent", "gratuite_temporaire",
                 "age_max", "conditions", "source / à vérifier"],
    "Lieux": ["id", "nom", "famille", "confiance_famille", "règle permanent (héritée)",
              "règle temporaire (héritée)", "âge max (hérité)", "expos_url", "tarifs_url",
              "gratuite_override", "statut", "date_verif", "notes", "tier",
              "plateforme_billetterie", "notes_crawler", "logo_url", "horaires_url"],
    "Tarifs": ["lieu_id", "portee", "regime", "audience", "prix", "plein_tarif", "recurrence",
               "justificatif", "source_url", "verifie_le", "verifie_par"],
    "Horaires": ["lieu_id", "jour_num", "jour", "ferme", "ouverture", "fermeture", "nocturne",
                 "portee", "derniere_entree_min", "valide_du", "valide_au", "note"],
    "Fermetures": ["lieu_id", "date", "libelle", "recurrent_annuel", "note"],
    "Expositions": ["lieu_id", "titre", "portee", "date_debut", "date_fin", "description",
                    "url", "image_url", "statut", "source", "verifie_le", "verifie_par"],
}


def ligne(onglet: str, **valeurs) -> list:
    return [valeurs.get(h) for h in ENTETES[onglet]]


@pytest.fixture
def con(tmp_path):
    connexion = db.connect(tmp_path / "test.db")
    db.init_schema(connexion)
    yield connexion
    connexion.close()


@pytest.fixture
def classeur_minimal(tmp_path):
    """Fabrique un classeur de test : un onglet par clé de ENTETES, lignes ajoutables."""

    def fabrique(**lignes_par_onglet):
        wb = Workbook()
        wb.remove(wb.active)
        for nom, entetes in ENTETES.items():
            ws = wb.create_sheet(nom)
            ws.append(entetes)
            for contenu in lignes_par_onglet.get(nom, []):
                ws.append(contenu)
        chemin = tmp_path / "mini.xlsx"
        wb.save(chemin)
        return chemin

    return fabrique


FAMILLE = ligne("Familles", famille_id="paris_musees", **{"libellé": "Paris Musées"})
LIEU = ligne("Lieux", id="musee-test", nom="Musée test", famille="paris_musees",
             confiance_famille="sûr", statut="à vérifier")
