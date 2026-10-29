import json
from datetime import date, datetime, timezone

import httpx
import pytest

from panade import db, export, gratuite, publish, seed

from conftest import CLASSEUR
from test_export import AUJ, MAD, MUSIQUE, ajouter

HIER = date(2026, 10, 28)
MAINTENANT = datetime(2026, 10, 29, 7, 0, tzinfo=timezone.utc)
URL = "https://paname-panade.test/api/import"


@pytest.fixture
def base(tmp_path):
    con = db.connect(tmp_path / "p.db")
    db.init_schema(con)
    seed.importer(con, CLASSEUR)
    con.execute("DELETE FROM expositions")
    con.commit()
    yield con
    con.close()


class Site:
    """Faux site : enregistre ce qu'il reçoit, répond ce qu'on lui dit de répondre."""

    def __init__(self, statut=200):
        self.statut, self.recus = statut, []

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        if self.statut == "coupure":
            raise httpx.ConnectError("reset")
        self.recus.append(requete)
        return httpx.Response(self.statut, text="ok" if self.statut < 300 else "refusé")

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self))


def lancer(base, tmp_path, site, **kw):
    return publish.publier(base, kw.pop("jour", AUJ), tmp_path / "data", url=kw.pop("url", URL),
                           jeton=kw.pop("jeton", "secret"), client=site.client(), maintenant=MAINTENANT, webhook="", **kw)


def peupler(base, n_musique=3, n_mad=3):
    for k in range(n_musique):
        ajouter(base, f"Musique {k}", lieu=MUSIQUE)
    for k in range(n_mad):
        ajouter(base, f"MAD {k}", lieu=MAD)


def reference(tmp_path, base, jour=HIER):
    """Pose une publication de la veille comme référence."""
    c = export.construire(base, jour, MAINTENANT).contenu
    dossier = tmp_path / "data" / "publie"
    dossier.mkdir(parents=True)
    (dossier / "derniere.json").write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    return c


# --- garde-fous, purs ------------------------------------------------------------------------

def faux_export(**par_lieu):
    lieux = [{"id": l, "expositions": [{"id": i * 100 + k, "titre": f"{l}{k}", "date_fin": "2027-01-01"} for k in range(n)]}
             for i, (l, n) in enumerate(par_lieu.items(), 1)]
    c = {"version": 1, "compte": {"lieux": len(lieux), "expositions": sum(n for n in par_lieu.values())}, "lieux": lieux}
    c["empreinte"] = export.empreinte(c)
    return c


@pytest.mark.parametrize("nouveau, refuse", [(7, False), (6, True), (10, False), (0, True)])
def test_garde_fou_1_seuil_de_70_pour_cent(nouveau, refuse):
    veille = faux_export(a=5, b=5)
    maintenant = faux_export(a=nouveau - nouveau // 2, b=nouveau // 2 or 1) if nouveau else faux_export(a=0, b=0)
    maintenant["compte"]["expositions"] = nouveau
    v = publish.garde_fous(maintenant, veille, AUJ)
    assert bool(v.refus) is refuse
    if refuse and nouveau:
        assert "garde-fou 1" in v.refus


def test_garde_fou_1_ignore_les_expos_terminees_de_la_veille():
    veille = faux_export(a=3)
    veille["lieux"][0]["expositions"][0]["date_fin"] = "2026-10-28"     # terminée hier
    veille["lieux"][0]["expositions"][1]["date_fin"] = "2026-10-28"
    # 1 attendue sur 3 : 1 exposition aujourd'hui suffit, sans quoi la fin normale d'une expo bloquerait tout
    assert publish.garde_fous(faux_export(a=1), veille, AUJ).refus is None


def test_garde_fou_2_un_lieu_qui_n_a_plus_rien_garde_les_donnees_de_la_veille():
    veille = faux_export(a=8, b=2)
    nouveau = faux_export(a=8, b=0)
    nouveau["compte"]["expositions"] = 8
    v = publish.garde_fous(nouveau, veille, AUJ)
    assert v.refus is None and v.reportes == {"b": 2}
    assert len(v.contenu["lieux"][1]["expositions"]) == 2 and v.contenu["compte"]["expositions"] == 10
    assert v.contenu["empreinte"] == export.empreinte(v.contenu) and any("garde-fou 2" in a for a in v.alertes)


def test_garde_fou_2_ne_ressuscite_pas_une_expo_sortie_par_le_garde_fou_3():
    veille = faux_export(a=8, b=1)
    nouveau = faux_export(a=8, b=0)
    nouveau["compte"]["expositions"] = 8
    exclue = veille["lieux"][1]["expositions"][0]["id"]
    v = publish.garde_fous(nouveau, veille, AUJ, {exclue})
    assert v.reportes == {} and v.contenu["lieux"][1]["expositions"] == []


def test_garde_fou_2_ne_touche_pas_un_lieu_qui_n_etait_plus_exporte():
    veille = faux_export(a=8, b=2)
    nouveau = faux_export(a=8)
    assert publish.garde_fous(nouveau, veille, AUJ).reportes == {}


def test_export_vide_toujours_refuse():
    assert "aucune exposition" in publish.garde_fous(faux_export(a=0), None, AUJ).refus
    assert "aucun lieu" in publish.garde_fous(faux_export(), None, AUJ).refus


# --- publier -------------------------------------------------------------------------------------

def test_premiere_publication_envoie_l_export_complet_et_pose_la_reference(base, tmp_path):
    peupler(base)
    site = Site()
    r = lancer(base, tmp_path, site)
    assert (r["envoye"], r["lieux"], r["expositions"]) == (True, 9, 6)
    (requete,) = site.recus
    assert requete.headers["authorization"] == "Bearer secret" and requete.headers["content-type"] == "application/json"
    recu = json.loads(requete.content)
    assert requete.headers["idempotency-key"] == recu["empreinte"] == export.empreinte(recu)
    derniere = export.lire(tmp_path / "data" / "publie" / "derniere.json")
    assert derniere == recu
    assert not export.a_des_champs_vides(recu)
    assert "publié : 9 lieux, 6 expositions" in (tmp_path / "data" / "alertes.log").read_text(encoding="utf-8")


def test_le_site_refuse_la_reference_ne_bouge_pas(base, tmp_path):
    peupler(base)
    ancienne = reference(tmp_path, base)
    with pytest.raises(publish.PublicationRefusee) as exc:
        lancer(base, tmp_path, Site(statut=500))
    assert exc.value.code == 3 and "HTTP 500" in exc.value.raison
    assert export.lire(tmp_path / "data" / "publie" / "derniere.json") == ancienne     # la veille reste la référence


def test_site_injoignable_apres_une_reprise(base, tmp_path):
    peupler(base)
    with pytest.raises(publish.PublicationRefusee) as exc:
        lancer(base, tmp_path, Site(statut="coupure"))
    assert exc.value.code == 3 and "injoignable" in exc.value.raison
    assert not (tmp_path / "data" / "publie" / "derniere.json").exists()


def test_garde_fou_1_bloque_et_garde_le_fichier_pour_examen(base, tmp_path):
    peupler(base, 5, 5)
    reference(tmp_path, base)
    for r in base.execute("SELECT id FROM expositions ORDER BY id LIMIT 4").fetchall():
        base.execute("UPDATE expositions SET etat = 'en_revue', motif_revue = 'x' WHERE id = ?", (r["id"],))   # un bug en retire 4 sur 10
    base.commit()
    site = Site()
    with pytest.raises(publish.PublicationRefusee) as exc:
        lancer(base, tmp_path, site)
    assert "garde-fou 1" in exc.value.raison and site.recus == []
    assert list((tmp_path / "data" / "exports").glob("export-*.json"))
    assert "publication refusée" in (tmp_path / "data" / "alertes.log").read_text(encoding="utf-8")


def test_garde_fou_2_de_bout_en_bout(base, tmp_path):
    peupler(base, 5, 1)
    reference(tmp_path, base)
    base.execute("UPDATE expositions SET etat = 'en_revue', motif_revue = 'absente de la page le 2026-10-29' WHERE lieu_id = ?", (MAD,))
    base.commit()
    site = Site()
    r = lancer(base, tmp_path, site)
    assert r["envoye"] and r["reportes"] == {MAD: 1}
    recu = json.loads(site.recus[0].content)
    assert recu["compte"]["expositions"] == 6 and len(next(l for l in recu["lieux"] if l["id"] == MAD)["expositions"]) == 1


def test_un_effondrement_massif_est_refuse_meme_si_le_garde_fou_2_pourrait_le_reparer(base, tmp_path):
    """Un lieu qui pèse la moitié du site disparaît : c'est un incident, pas un à-coup, une personne regarde."""
    peupler(base, 3, 3)
    reference(tmp_path, base)
    base.execute("UPDATE expositions SET etat = 'en_revue', motif_revue = 'absente de la page le 2026-10-29' WHERE lieu_id = ?", (MAD,))
    base.commit()
    with pytest.raises(publish.PublicationRefusee, match="garde-fou 1"):
        lancer(base, tmp_path, Site())


def test_garde_fou_3_de_bout_en_bout(base, tmp_path):
    peupler(base, 1, 5)
    reference(tmp_path, base)
    base.execute("UPDATE tarifs SET audience = 'moins_18' WHERE lieu_id = ? AND portee = 'temporaire'", (MUSIQUE,))
    base.commit()          # la gratuité de l'unique expo de la musique change sans relecture
    site = Site()
    r = lancer(base, tmp_path, site)
    assert r["reportes"] == {}        # retirée par le garde-fou 3 (dans validate), et pas ressuscitée par le garde-fou 2
    recu = json.loads(site.recus[0].content)
    assert {l["id"] for l in recu["lieux"] if l.get("expositions")} == {MAD} and recu["compte"]["expositions"] == 5
    assert base.execute("SELECT COUNT(*) FROM expositions WHERE etat = 'en_revue'").fetchone()[0] == 1
    assert "gratuité modifiée sans relecture" in base.execute("SELECT motif_revue FROM expositions WHERE etat = 'en_revue'").fetchone()[0]


def test_a_blanc_ne_contacte_personne(base, tmp_path):
    peupler(base)
    site = Site()
    r = publish.publier(base, AUJ, tmp_path / "data", a_blanc=True, maintenant=MAINTENANT, webhook="")
    assert r["envoye"] is False and site.recus == []
    assert not (tmp_path / "data" / "publie" / "derniere.json").exists()


def test_http_en_clair_refuse_sauf_en_local(base, tmp_path):
    peupler(base)
    with pytest.raises(publish.PublicationRefusee, match="https"):
        lancer(base, tmp_path, Site(), url="http://paname-panade.test/api/import")
    assert lancer(base, tmp_path, Site(), url="http://127.0.0.1:3000/api/import")["envoye"]


@pytest.mark.parametrize("url, jeton", [(None, "secret"), (URL, None), (None, None)])
def test_sans_url_ou_sans_jeton(base, tmp_path, monkeypatch, url, jeton):
    monkeypatch.delenv("PANADE_PUBLISH_URL", raising=False)
    monkeypatch.delenv("PANADE_PUBLISH_TOKEN", raising=False)
    peupler(base)
    with pytest.raises(publish.PublicationRefusee) as exc:
        publish.publier(base, AUJ, tmp_path / "data", url=url, jeton=jeton, maintenant=MAINTENANT, webhook="")
    assert exc.value.code == 4


def test_reference_alteree_refuse_la_publication(base, tmp_path):
    peupler(base)
    reference(tmp_path, base)
    chemin = tmp_path / "data" / "publie" / "derniere.json"
    chemin.write_text(chemin.read_text(encoding="utf-8").replace("Musique 0", "Musique X"), encoding="utf-8")
    with pytest.raises(publish.PublicationRefusee) as exc:
        lancer(base, tmp_path, Site())
    assert exc.value.code == 5 and "illisible" in exc.value.raison


def test_base_corrompue_refuse(base, tmp_path, monkeypatch):
    peupler(base)
    from panade import validate
    monkeypatch.setattr(validate, "_integrite", lambda con, rapport: rapport.problemes_graves.append("la base SQLite est corrompue"))
    with pytest.raises(publish.PublicationRefusee, match="corrompue"):
        lancer(base, tmp_path, Site())


def test_le_jeton_n_apparait_dans_aucune_alerte(base, tmp_path):
    peupler(base)
    with pytest.raises(publish.PublicationRefusee):
        lancer(base, tmp_path, Site(statut=500), jeton="tres-secret-1234")
    assert "tres-secret-1234" not in (tmp_path / "data" / "alertes.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("etat, motif, reprise", [
    ("en_revue", "absente de la page le 2026-10-29", True),       # page lue de travers : on garde la veille
    ("en_revue", "gratuité modifiée sans relecture : gratuit_26 → a_confirmer", False),
    ("en_revue", "titre ou dates modifiés sur le site", False),
    ("en_revue", "non conforme : url : String should match pattern", False),
    ("rejete", "rejetée par une personne", False),
    ("rejete", "doublon de l'exposition 3", False),
])
def test_le_garde_fou_2_ne_reprend_que_ce_qui_a_disparu_par_accident(base, tmp_path, etat, motif, reprise):
    peupler(base, 5, 1)
    reference(tmp_path, base)
    base.execute("UPDATE expositions SET etat = ?, motif_revue = ?, confiance = 1.0 WHERE lieu_id = ?", (etat, motif, MAD))
    base.commit()
    r = lancer(base, tmp_path, Site())
    assert (r["reportes"] == {MAD: 1}) is reprise
