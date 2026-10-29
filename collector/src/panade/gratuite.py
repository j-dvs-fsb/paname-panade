"""Le moteur de gratuité : une fonction pure, sans base ni réseau.

    calculer(lieu, portee, aujourdhui) -> Gratuite

La gratuité d'une exposition n'est jamais lue sur sa page. Elle se calcule :
  1. les lignes de tarifs vérifiées du lieu (portée de l'expo ou « tout ») ;
  2. à défaut, la règle de la famille, sauf si le lieu a un `gratuite_override`
     (qui prime : on ne tombe jamais sur la règle de la famille) ou si son
     rattachement à la famille est incertain.
Tout ce que le moteur ne sait pas interpréter donne `a_confirmer`, jamais un gratuit.

Visiteur de référence : 18 à 25 ans, résident de l'UE. C'est la cible du site, et
c'est elle que visent les catégories `gratuit_26` et `reduit_26`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

PEREMPTION_JOURS = 120           # invariant 5 : une donnée vérifiée il y a plus longtemps est périmée

# Audiences dont fait partie un visiteur de 18 à 25 ans résident UE.
AUDIENCES_REFERENCE = frozenset({"tous", "moins_26", "moins_26_ue", "moins_30", "18_29_ans"})

# Une ligne « tout » qui précise « seul(s) » ou « uniquement » ne couvre qu'une partie
# de l'offre (« Jardins seuls ») : elle ne dit rien sur l'exposition.
RESTRICTIF = re.compile(r"\b(seuls?|seules?|uniquement)\b", re.I)
A_VERIFIER = re.compile(r"\ba v[ée]rifier\b", re.I)

STATUTS = ("gratuit_tous", "gratuit_26", "reduit_26", "payant", "a_confirmer")


@dataclass(frozen=True)
class Famille:
    id: str
    gratuite_permanent: str | None = None
    gratuite_temporaire: str | None = None
    age_max: int | None = None
    conditions: str | None = None


@dataclass(frozen=True)
class Tarif:
    portee: str
    regime: str
    audience: str
    prix: float | None
    plein_tarif: float | None
    recurrence: str
    justificatif: str | None = None
    verifie_le: str | None = None


@dataclass(frozen=True)
class Lieu:
    id: str
    famille: Famille
    confiance_famille: str = "sur"
    gratuite_override: str | None = None
    tarifs: tuple[Tarif, ...] = ()


@dataclass(frozen=True)
class Gratuite:
    statut: str
    source: str                       # tarifs | famille | override | aucune
    raison: str
    prix: float | None = None         # prix pour le visiteur de référence (0 si gratuit)
    plein_tarif: float | None = None
    audience: str | None = None
    justificatif: str | None = None
    creneaux: tuple[tuple[str, str, float | None, str], ...] = field(default=())   # (audience, régime, prix, récurrence)

    def en_json(self) -> str:
        """Forme stockée et exportée. Déterministe : égalité de chaînes = même gratuité."""
        objet = {"statut": self.statut, "source": self.source, "raison": self.raison}
        for cle in ("prix", "plein_tarif", "audience", "justificatif"):
            if getattr(self, cle) is not None:
                objet[cle] = getattr(self, cle)
        if self.creneaux:
            objet["creneaux"] = [{"audience": a, "regime": r, **({"prix": p} if p is not None else {}), "recurrence": rec}
                                 for a, r, p, rec in self.creneaux]
        return json.dumps(objet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def a_confirmer(raison: str, source: str = "aucune") -> Gratuite:
    return Gratuite("a_confirmer", source, raison)


# --------------------------------------------------------------------------------------

def calculer(lieu: Lieu, portee: str, aujourdhui: date) -> Gratuite:
    if portee not in ("permanent", "temporaire"):
        raise ValueError(f"portée d'exposition inconnue : {portee}")

    lignes, ecartees = _lignes_utilisables(lieu, portee, aujourdhui)
    resultat = _depuis_les_tarifs(lignes, ecartees)
    if resultat is not None:
        return resultat
    note = f" ({ecartees})" if ecartees else ""

    if lieu.gratuite_override:
        # L'exception du lieu prime sur la famille ; son texte libre, lui, n'est jamais interprété.
        return a_confirmer(f"exception propre au lieu à confirmer : « {lieu.gratuite_override} »{note}", "override")
    if lieu.confiance_famille != "sur":
        return a_confirmer(f"rattachement à la famille {lieu.famille.id} incertain{note}")
    return _depuis_la_famille(lieu.famille, portee, note)


def _lignes_utilisables(lieu: Lieu, portee: str, aujourdhui: date) -> tuple[list[Tarif], str]:
    limite = (aujourdhui - timedelta(days=PEREMPTION_JOURS)).isoformat()
    gardees, ecartees = [], []
    for t in lieu.tarifs:
        if t.portee not in (portee, "tout"):
            continue
        if t.verifie_le is None:
            ecartees.append(f"{t.audience} non vérifié")
        elif t.verifie_le < limite:
            ecartees.append(f"{t.audience} périmé ({t.verifie_le})")
        elif t.justificatif and A_VERIFIER.search(t.justificatif):
            ecartees.append(f"{t.audience} marqué à vérifier")
        elif t.portee == "tout" and t.justificatif and RESTRICTIF.search(t.justificatif):
            ecartees.append(f"{t.audience} limité à une partie de l'offre")
        else:
            gardees.append(t)
    return gardees, "; ".join(ecartees)


def _depuis_les_tarifs(lignes: list[Tarif], ecartees: str) -> Gratuite | None:
    pour_la_reference = [t for t in lignes if t.audience in AUDIENCES_REFERENCE and t.regime != "abonnement"]
    toujours = [t for t in pour_la_reference if t.recurrence == "toujours"]
    creneaux = tuple(sorted({(t.audience, t.regime, t.prix, t.recurrence) for t in pour_la_reference
                             if t.recurrence != "toujours"}, key=lambda c: (c[3], c[0], c[1])))
    if not toujours:
        if creneaux:
            return Gratuite("a_confirmer", "tarifs", "seuls des créneaux particuliers sont connus pour les moins de 26 ans",
                            creneaux=creneaux)
        return None

    gratuits_tous = [t for t in toujours if t.regime == "gratuit" and t.audience == "tous"]
    payants_cibles = [t for t in toujours if t.regime != "gratuit" and t.audience != "tous"]
    if gratuits_tous and payants_cibles:
        # « Gratuit pour tous » et « 5 € pour les moins de 26 ans » ne peuvent pas être vrais ensemble
        # pour la même exposition : la ligne gratuite concerne sans doute un espace particulier.
        return Gratuite("a_confirmer", "tarifs", "tarifs contradictoires : gratuit pour tous et payant pour les moins de 26 ans",
                        creneaux=creneaux)

    gratuits = [t for t in toujours if t.regime == "gratuit"]
    if gratuits:
        meilleur = sorted(gratuits, key=lambda t: t.audience != "tous")[0]
        statut = "gratuit_tous" if meilleur.audience == "tous" else "gratuit_26"
        return Gratuite(statut, "tarifs", f"ligne de tarif vérifiée ({meilleur.audience}, {meilleur.recurrence})",
                        prix=0, plein_tarif=meilleur.plein_tarif or None, audience=meilleur.audience,
                        justificatif=meilleur.justificatif, creneaux=creneaux)

    reduits = sorted(toujours, key=lambda t: (t.prix is None, t.prix if t.prix is not None else 0))
    meilleur = reduits[0]
    plein = meilleur.plein_tarif
    if meilleur.audience == "tous" and (meilleur.prix is None or plein is None or meilleur.prix >= plein):
        # le tarif « réduit » de tout le monde est le tarif normal
        return Gratuite("payant", "tarifs", "tarif unique, aucune réduction pour les moins de 26 ans",
                        prix=meilleur.prix, plein_tarif=plein, audience="tous", justificatif=meilleur.justificatif,
                        creneaux=creneaux)
    if meilleur.prix is None:
        return Gratuite("a_confirmer", "tarifs", "tarif réduit sans montant connu", plein_tarif=plein, creneaux=creneaux)
    return Gratuite("reduit_26", "tarifs", f"ligne de tarif vérifiée ({meilleur.audience}, {meilleur.recurrence})",
                    prix=meilleur.prix, plein_tarif=plein, audience=meilleur.audience,
                    justificatif=meilleur.justificatif, creneaux=creneaux)


def _depuis_la_famille(famille: Famille, portee: str, note: str) -> Gratuite:
    regle = famille.gratuite_permanent if portee == "permanent" else famille.gratuite_temporaire
    if regle == "Gratuit pour tous":
        return Gratuite("gratuit_tous", "famille", f"règle de la famille {famille.id} ({portee})", prix=0)
    if regle == "Gratuit" and famille.age_max and famille.age_max >= 26:
        return Gratuite("gratuit_26", "famille", f"règle de la famille {famille.id} ({portee}), moins de {famille.age_max} ans",
                        prix=0, audience="moins_26_ue", justificatif=famille.conditions)
    if regle == "Payant pour tous (gratuit -18 ans)":
        return Gratuite("payant", "famille", f"règle de la famille {famille.id} ({portee}) : payant à partir de 18 ans")
    return a_confirmer(f"règle de la famille {famille.id} ({portee}) non exploitable : « {regle} »{note}", "famille")


def en_json(g: Gratuite) -> str:
    return g.en_json()


# --- chargement depuis la base (la seule partie qui touche SQLite) -----------------------

def charger(con, lieu_id: str) -> Lieu:
    ligne = con.execute("SELECT * FROM lieux WHERE id = ?", (lieu_id,)).fetchone()
    fam = con.execute("SELECT * FROM familles WHERE id = ?", (ligne["famille_id"],)).fetchone()
    tarifs = tuple(Tarif(t["portee"], t["regime"], t["audience"], t["prix"], t["plein_tarif"], t["recurrence"],
                         t["justificatif"], t["verifie_le"])
                   for t in con.execute("SELECT * FROM tarifs WHERE lieu_id = ? ORDER BY id", (lieu_id,)))
    return Lieu(ligne["id"],
                Famille(fam["id"], fam["gratuite_permanent"], fam["gratuite_temporaire"], fam["age_max"], fam["conditions"]),
                ligne["confiance_famille"], ligne["gratuite_override"], tarifs)
