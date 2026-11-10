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


# --- réseau simulé ------------------------------------------------------------

import httpx  # noqa: E402

from panade.http import ClientPoli  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture(chemin: str) -> str:
    return (FIXTURES / chemin).read_text(encoding="utf-8")


class FauxReseau:
    """Sert des réponses préparées et note chaque requête. Toute requête non prévue est une erreur."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.vues: list[str] = []

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        url = str(requete.url)
        self.vues.append(url)
        for cle in (url, url.split("?")[0]):
            if cle in self.routes:
                valeur = self.routes[cle]
                if callable(valeur):
                    return valeur(requete)
                if isinstance(valeur, str):
                    return httpx.Response(200, text=valeur)
                statut, entetes, corps = (valeur + ({}, ""))[:3] if isinstance(valeur, tuple) else (valeur, {}, "")
                return httpx.Response(statut, headers=entetes, text=corps)
        raise AssertionError(f"requête inattendue : {url}")

    @property
    def chemins(self) -> list[str]:
        return [u.split("//", 1)[1] for u in self.vues]


class Horloge:
    def __init__(self):
        self.t = 1000.0
        self.pauses: list[float] = []

    def maintenant(self) -> float:
        return self.t

    def dormir(self, s: float) -> None:
        self.pauses.append(s)
        self.t += s


@pytest.fixture
def horloge():
    return Horloge()


@pytest.fixture
def faux_client(horloge):
    """faux_client(routes) -> (client, réseau). Le client ne dort jamais pour de vrai."""
    clients = []

    def fabrique(routes: dict, **options):
        reseau = FauxReseau(routes)
        client = ClientPoli(transport=httpx.MockTransport(reseau), horloge=horloge.maintenant,
                            dormir=horloge.dormir, **options)
        clients.append(client)
        return client, reseau

    yield fabrique
    for c in clients:
        c.close()
