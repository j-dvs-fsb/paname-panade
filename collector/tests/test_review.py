import json
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from panade import db, seed, validate
from panade.review.app import creer_app, libelle_gratuite

from conftest import CLASSEUR

AUJ = date(2026, 10, 29)
PROV = {"titre": "carte", "url": "carte", "date_debut": "texte_fr_annee_deduite", "date_fin": "texte_fr_annee_deduite"}


@pytest.fixture
def ctx(tmp_path):
    chemin = tmp_path / "r.db"
    con = db.connect(chemin)
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    con.execute("DELETE FROM expositions")      # on part d'une file que le test contrôle
    con.commit()
    client = TestClient(creer_app(str(chemin), aujourdhui=lambda: AUJ), follow_redirects=False)
    yield client, con
    con.close()


def ajouter(con, titre="Expo", lieu="musee-carnavalet-histoire-de-paris", portee="temporaire", debut="2026-10-01",
            fin="2027-02-01", prov=PROV, motif=None, **extra):
    cur = con.execute(
        "INSERT INTO expositions (lieu_id, titre, portee, date_debut, date_fin, url, image_url, description, source, provenance, motif_revue)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'paris_musees', ?, ?)",
        (lieu, titre, portee, debut, fin, f"https://x.test/{abs(hash(titre))}", "https://x.test/i.jpg", "Une description",
         json.dumps(prov) if prov is not None else None, motif))
    con.commit()
    return cur.lastrowid


def jeton(client, expo_id):
    page = client.get(f"/item/{expo_id}")
    assert page.status_code == 200
    return re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)


def ligne(con, i):
    return dict(con.execute("SELECT * FROM expositions WHERE id = ?", (i,)).fetchone())


def publier(client, con, i, **champs):
    donnees = {"csrf": jeton(client, i), "titre": ligne(con, i)["titre"], "portee": ligne(con, i)["portee"],
               "date_debut": ligne(con, i)["date_debut"] or "", "date_fin": ligne(con, i)["date_fin"] or ""} | champs
    return client.post(f"/item/{i}/publier", data=donnees)


def test_l_accueil_mene_a_la_premiere_a_relire_les_urgences_d_abord(ctx):
    client, con = ctx
    ordinaire = ajouter(con, "Ordinaire")
    urgente = ajouter(con, "Urgente", motif="gratuité modifiée sans relecture : gratuit_tous → a_confirmer")
    r = client.get("/")
    assert (r.status_code, r.headers["location"]) == (303, f"/item/{urgente}")
    assert ordinaire < urgente        # la plus récente passe devant parce qu'elle est urgente


def test_file_vide(ctx):
    client, _ = ctx
    r = client.get("/")
    assert r.status_code == 200 and "Rien à relire" in r.text


def test_la_fiche_montre_le_motif_la_provenance_et_la_gratuite_calculee(ctx):
    client, con = ctx
    i = ajouter(con, "Nouvel accrochage", portee="permanent", motif="confiance 0.60 sous le seuil 0.80 (dates)")
    validate.valider(con, AUJ)
    page = client.get(f"/item/{i}").text
    assert "Pourquoi elle attend" in page and "sous le seuil" in page
    assert "date_debut : texte_fr_annee_deduite" in page
    assert "Gratuit pour tous" in page                    # Carnavalet, permanent : règle de famille
    assert "jamais lue sur la page" in page


def test_le_contenu_vient_d_un_site_tiers_il_est_echappe(ctx):
    client, con = ctx
    i = ajouter(con, "<script>alert(1)</script>")
    con.execute("UPDATE expositions SET description = '<img src=x onerror=alert(2)>' WHERE id = ?", (i,))
    con.commit()
    r = client.get(f"/item/{i}")
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;alert(1)" in r.text
    assert "<img src=x" not in r.text
    nonce = re.search(r"script-src 'nonce-([^']+)'", r.headers["content-security-policy"]).group(1)
    assert f'nonce="{nonce}"' in r.text and "default-src 'none'" in r.headers["content-security-policy"]


def test_publier_avec_corrections(ctx):
    client, con = ctx
    i = ajouter(con, "Expo", portee="temporaire")
    suivante = ajouter(con, "Suivante")
    r = publier(client, con, i, titre="Expo corrigée", date_fin="2027-03-01", portee="permanent")
    assert (r.status_code, r.headers["location"]) == (303, f"/item/{suivante}")
    e = ligne(con, i)
    assert (e["etat"], e["confiance"], e["motif_revue"], e["titre"], e["date_fin"], e["portee"]) == \
        ("publie", 1.0, None, "Expo corrigée", "2027-03-01", "permanent")
    prov = json.loads(e["provenance"])
    assert prov["relu"] == "humain" and prov["titre"] == prov["date_fin"] == prov["portee"] == "humain"
    assert prov["date_debut"] == "texte_fr_annee_deduite"              # non corrigée : sa provenance reste honnête
    assert json.loads(e["gratuite_calculee"])["statut"] == "gratuit_tous" and e["gratuite_validee"] == e["gratuite_calculee"]


def test_la_machine_ne_rebloque_pas_ce_qu_une_personne_a_publie(ctx):
    client, con = ctx
    i = ajouter(con, "Expo")
    publier(client, con, i)
    validate.valider(con, AUJ)
    validate.valider(con, AUJ)
    assert ligne(con, i)["etat"] == "publie"


def test_publier_une_expo_de_la_graine_sans_provenance(ctx):
    client, con = ctx
    i = ajouter(con, "Graine", prov=None, lieu="musee-de-la-musique")
    publier(client, con, i)
    e = ligne(con, i)
    assert (e["etat"], e["confiance"]) == ("publie", 1.0) and json.loads(e["provenance"]) == {"relu": "humain"}
    validate.valider(con, AUJ)
    assert ligne(con, i)["etat"] == "publie"


def test_dates_incoherentes_rien_n_est_enregistre(ctx):
    client, con = ctx
    i = ajouter(con, "Expo")
    r = publier(client, con, i, date_debut="2027-05-01", date_fin="2027-01-01")
    assert r.headers["location"].startswith(f"/item/{i}?erreur=")
    assert ligne(con, i)["etat"] == "en_revue" and ligne(con, i)["date_debut"] == "2026-10-01"
    page = client.get(r.headers["location"]).text
    assert "Rien n'a été enregistré" in page and "date_fin précède date_debut" in page


def test_rejeter(ctx):
    client, con = ctx
    i = ajouter(con, "Atelier mal classé")
    r = client.post(f"/item/{i}/rejeter", data={"csrf": jeton(client, i)})
    assert r.status_code == 303 and ligne(con, i)["etat"] == "rejete"
    assert ligne(con, i)["motif_revue"] == "rejetée par une personne"


@pytest.mark.parametrize("csrf", ["", "faux"])
def test_sans_jeton_valide_rien_ne_bouge(ctx, csrf):
    client, con = ctx
    i = ajouter(con, "Expo")
    for action in ("publier", "rejeter"):
        r = client.post(f"/item/{i}/{action}", data={"csrf": csrf, "titre": "x", "portee": "temporaire"})
        assert r.status_code == 403
    assert ligne(con, i)["etat"] == "en_revue"


def test_nom_d_hote_etranger_refuse(ctx):
    client, con = ctx
    ajouter(con, "Expo")
    assert client.get("/", headers={"host": "evil.example"}).status_code == 400


def test_exposition_inconnue(ctx):
    client, _ = ctx
    assert client.get("/item/9999").status_code == 404


def test_liste(ctx):
    client, con = ctx
    ajouter(con, "Première", motif="doublon possible")
    page = client.get("/liste").text
    assert "1 à relire" in page and "Première" in page and "doublon possible" in page


@pytest.mark.parametrize("statut, attendu", [
    ({"statut": "gratuit_26", "audience": "moins_26_ue", "raison": "r"}, "Gratuit pour les moins de 26 ans (résidents UE). r"),
    ({"statut": "reduit_26", "prix": 5, "plein_tarif": 12, "raison": "r"}, "Tarif réduit moins de 26 ans : 5 € (plein tarif 12 €). r"),
    ({"statut": "payant", "raison": "r"}, "Payant, montant inconnu. r"),
    ({"statut": "a_confirmer", "raison": "pourquoi"}, "À confirmer sur place. pourquoi"),
])
def test_libelles_de_gratuite(statut, attendu):
    assert libelle_gratuite(json.dumps(statut)) == attendu
