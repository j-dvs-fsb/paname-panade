import httpx
import pytest

from panade.http import AccesRefuse, ErreurReseau, Verdict, USER_AGENT

ROBOTS_OK = "User-agent: *\nDisallow: /prive\n"


def test_user_agent_identifiable_et_robots_lu_en_premier(faux_client):
    vus = []
    client, reseau = faux_client({
        "https://a.test/robots.txt": ROBOTS_OK,
        "https://a.test/page": lambda r: (vus.append(r.headers["user-agent"]), httpx.Response(200, text="ok"))[1],
    })
    assert client.get("https://a.test/page").texte == "ok"
    assert reseau.chemins == ["a.test/robots.txt", "a.test/page"]
    assert vus == [USER_AGENT] and "paname-panade.fr/bot" in USER_AGENT


def test_robots_lu_une_seule_fois_par_origine(faux_client):
    client, reseau = faux_client({"https://a.test/robots.txt": ROBOTS_OK, "https://a.test/1": "x", "https://a.test/2": "y"})
    client.get("https://a.test/1")
    client.get("https://a.test/2")
    assert reseau.chemins.count("a.test/robots.txt") == 1


def test_une_requete_par_seconde_et_par_domaine(faux_client, horloge):
    client, _ = faux_client({"https://a.test/robots.txt": ROBOTS_OK, "https://a.test/1": "x", "https://a.test/2": "y",
                             "https://b.test/robots.txt": ROBOTS_OK, "https://b.test/1": "z"})
    client.get("https://a.test/1")      # a: robots puis page
    client.get("https://a.test/2")
    avant = len(horloge.pauses)
    client.get("https://b.test/1")      # autre domaine : robots.txt part sans attendre a, la page attend 1 s
    assert all(p == pytest.approx(1.0) for p in horloge.pauses)
    assert len(horloge.pauses) == avant + 1


def test_interdit_par_robots_leve_et_ne_telecharge_pas(faux_client):
    client, reseau = faux_client({"https://a.test/robots.txt": ROBOTS_OK})
    with pytest.raises(AccesRefuse) as exc:
        client.get("https://a.test/prive/secret")
    assert exc.value.verdict is Verdict.INTERDIT
    assert reseau.chemins == ["a.test/robots.txt"]


@pytest.mark.parametrize("statut", [500, 503, 429])
def test_robots_en_erreur_serveur_on_s_abstient(faux_client, statut):
    client, reseau = faux_client({"https://a.test/robots.txt": (statut, {"retry-after": "3600"}, "maintenance")})
    with pytest.raises(AccesRefuse) as exc:
        client.get("https://a.test/page")
    assert exc.value.verdict is Verdict.INJOIGNABLE
    assert reseau.chemins == ["a.test/robots.txt"]


def test_robots_absent_tout_est_permis(faux_client):
    client, _ = faux_client({"https://a.test/robots.txt": (404, {}, "non"), "https://a.test/p": "ok"})
    assert client.get("https://a.test/p").ok


def test_robots_qui_redirige_est_suivi(faux_client):
    client, _ = faux_client({
        "https://m.test/robots.txt": (302, {"location": "https://www.m.test/robots.txt"}, ""),
        "https://www.m.test/robots.txt": "User-agent: *\nDisallow: /prive\n",
    })
    assert client.verdict("https://m.test/page").verdict is Verdict.AUTORISE
    assert client.verdict("https://m.test/prive").verdict is Verdict.INTERDIT


def test_redirection_vers_un_autre_domaine_repasse_par_robots(faux_client):
    client, reseau = faux_client({
        "https://a.test/robots.txt": ROBOTS_OK,
        "https://a.test/p": (301, {"location": "https://b.test/arrivee"}, ""),
        "https://b.test/robots.txt": "User-agent: *\nDisallow: /\n",
    })
    with pytest.raises(AccesRefuse) as exc:
        client.get("https://a.test/p")
    assert exc.value.verdict is Verdict.INTERDIT
    assert "b.test/arrivee" not in reseau.chemins


def test_requete_conditionnelle_et_304(faux_client):
    recu = {}
    def page(r):
        recu.update(r.headers)
        return httpx.Response(304)
    client, _ = faux_client({"https://a.test/robots.txt": ROBOTS_OK, "https://a.test/p": page})
    r = client.get("https://a.test/p", etag='"abc"', derniere_modif="Wed, 21 Oct 2026 07:28:00 GMT")
    assert r.non_modifie and r.texte == ""
    assert recu["if-none-match"] == '"abc"' and recu["if-modified-since"].startswith("Wed, 21 Oct 2026")


def test_etag_et_last_modified_remontes(faux_client):
    client, _ = faux_client({"https://a.test/robots.txt": ROBOTS_OK,
                             "https://a.test/p": (200, {"etag": '"v1"', "last-modified": "Mon, 01 Jun 2026 00:00:00 GMT"}, "ok")})
    r = client.get("https://a.test/p")
    assert (r.etag, r.derniere_modif) == ('"v1"', "Mon, 01 Jun 2026 00:00:00 GMT")


def test_une_reprise_sur_coupure_de_connexion_puis_abandon(faux_client, horloge):
    essais = []
    def coupe(r):
        essais.append(1)
        raise httpx.ConnectError("reset")
    client, _ = faux_client({"https://a.test/robots.txt": ROBOTS_OK, "https://a.test/p": coupe})
    with pytest.raises(ErreurReseau):
        client.get("https://a.test/p")
    assert len(essais) == 2 and 2.0 in horloge.pauses


def test_corps_plafonne(faux_client):
    client, _ = faux_client({"https://a.test/robots.txt": ROBOTS_OK, "https://a.test/gros": "x" * 5000}, max_octets=1000)
    r = client.get("https://a.test/gros")
    assert r.tronque and len(r.texte) == 1000


def test_trop_de_redirections(faux_client):
    client, _ = faux_client({"https://a.test/robots.txt": ROBOTS_OK, "https://a.test/boucle": (302, {"location": "/boucle"}, "")})
    with pytest.raises(ErreurReseau):
        client.get("https://a.test/boucle")
