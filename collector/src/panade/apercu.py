"""Aperçu d'une exposition telle que paname-panade.fr l'afficherait, champ par champ.

Pour chaque élément de la fiche publique, `diagnostiquer` dit s'il est :
  - `ok`     : présent et lu sur une source fiable ;
  - `doute`  : présent mais incertain (année déduite, valeur venue du classeur sans
               confirmation de la page, gratuité à confirmer...) -> orange ;
  - `manque` : absent, la fiche publique aurait un trou -> rouge.

Fonctions pures : pas de base, pas de réseau. L'écran de relecture s'en sert pour colorer
l'aperçu, et `resume_horaires` sert aussi à l'export (texte d'horaires d'un lieu).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from panade.models import JOURS

MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre")
PROVENANCES_DOUTEUSES = {
    "texte_fr_annee_deduite": "année absente de la page, déduite de la date du jour",
    "incertaine": "la page ne tranche pas",
}


@dataclass(frozen=True)
class Etat:
    etat: str          # ok | doute | manque
    raison: str | None = None

    @property
    def classe(self) -> str:
        return "" if self.etat == "ok" else self.etat


OK = Etat("ok")


# --- textes affichés -------------------------------------------------------------------------

def date_fr(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{'1er' if d.day == 1 else d.day} {MOIS[d.month - 1]} {d.year}"


def libelle_dates(debut: str | None, fin: str | None, portee: str = "temporaire") -> str:
    """Même phrase que le site (getter `date_label` du modèle Exposition)."""
    if portee == "permanent" and not debut and not fin:
        return "En permanence"
    if debut and fin:
        return f"Le {date_fr(debut)}" if debut == fin else f"Du {date_fr(debut)} au {date_fr(fin)}"
    if fin:
        return f"Jusqu'au {date_fr(fin)}"
    if debut:
        return f"À partir du {date_fr(debut)}"
    return "Dates non communiquées"


def _heure(hhmm: str) -> str:
    h, m = hhmm.split(":")
    return f"{int(h)}h" + ("" if m == "00" else m)


def _liste(noms: list[str]) -> str:
    return noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + " et " + noms[-1]


def _plage(jours: list[int]) -> str:
    """« du mardi au dimanche », « tous les jours », « du mercredi au lundi », « les lundi et mardi »."""
    jours = sorted(set(jours))
    if len(jours) == 7:
        return "tous les jours"
    if len(jours) == 1:
        return f"le {JOURS[jours[0] - 1]}"
    # Plage continue, éventuellement à cheval sur la fin de semaine (du mercredi au lundi).
    for depart in jours:
        suite = [((depart - 1 + k) % 7) + 1 for k in range(len(jours))]
        if sorted(suite) == jours and len(jours) > 2:
            return f"du {JOURS[suite[0] - 1]} au {JOURS[suite[-1] - 1]}"
    return "les " + _liste([JOURS[j - 1] for j in jours])


def _fusionner(plages: list[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    """Fusionne les créneaux qui se touchent ou se chevauchent (12h-18h + 18h-20h = 12h-20h)."""
    sortie: list[list[str]] = []
    for o, f in sorted(plages):
        if sortie and o <= sortie[-1][1]:
            sortie[-1][1] = max(sortie[-1][1], f)
        else:
            sortie.append([o, f])
    return tuple((o, f) for o, f in sortie)


def resume_horaires(lignes: list[dict], aujourdhui: date, portee: str = "temporaire") -> str | None:
    """Les horaires d'un lieu en une phrase, pour une exposition de cette portée.

    « Du mardi au dimanche, 10h-18h ; jusqu'à 21h30 le jeudi ; fermé le lundi. »
    Ne garde que les lignes valables aujourd'hui et de portée « tout » ou `portee`.
    """
    jour_iso = aujourdhui.isoformat()
    utiles = [l for l in lignes
              if l["portee"] in ("tout", portee)
              and (not l.get("valide_du") or l["valide_du"] <= jour_iso)
              and (not l.get("valide_au") or l["valide_au"] >= jour_iso)]
    if not utiles:
        return None
    par_jour: dict[int, tuple] = {}
    fermes: list[int] = []
    for j in range(1, 8):
        du_jour = [l for l in utiles if l["jour_num"] == j]
        if not du_jour:
            continue
        ouverts = [(l["ouverture"], l["fermeture"]) for l in du_jour if not l["ferme"]]
        if ouverts:
            par_jour[j] = _fusionner(ouverts)
        else:
            fermes.append(j)
    if not par_jour:
        return "Fermé" if fermes else None
    texte = lambda sig: " et ".join(f"{_heure(o)}-{_heure(f)}" for o, f in sig)  # noqa: E731
    # Horaire de base : le plus fréquent ; les autres jours sont dits à part.
    frequences: dict[tuple, int] = {}
    for sig in par_jour.values():
        frequences[sig] = frequences.get(sig, 0) + 1
    base = max(frequences, key=lambda s: (frequences[s], -min(j for j, v in par_jour.items() if v == s)))
    simple = len(base) == 1
    tard: dict[str, list[int]] = {}       # fermeture plus tardive, même ouverture
    tot: dict[str, list[int]] = {}        # ouverture différente, même fermeture
    autres: dict[tuple, list[int]] = {}  # jours à part, regroupés par créneaux identiques
    for j, sig in par_jour.items():
        if sig == base:
            continue
        if simple and len(sig) == 1 and sig[0][0] == base[0][0] and sig[0][1] > base[0][1]:
            tard.setdefault(sig[0][1], []).append(j)
        elif simple and len(sig) == 1 and sig[0][1] == base[0][1]:
            tot.setdefault(sig[0][0], []).append(j)
        else:
            autres.setdefault(sig, []).append(j)
    # La plage principale couvre aussi les jours qui ne diffèrent que par l'heure d'ouverture ou de fermeture.
    principaux = [j for j, sig in par_jour.items() if sig == base] + [j for js in (*tard.values(), *tot.values()) for j in js]
    phrase = _plage(principaux)
    morceaux = [f"{phrase[0].upper()}{phrase[1:]}, {texte(base)}"]
    morceaux += [f"jusqu'à {_heure(h)} {_plage(js)}" for h, js in sorted(tard.items())]
    morceaux += [f"à partir de {_heure(h)} {_plage(js)}" for h, js in sorted(tot.items())]
    morceaux += [f"{texte(sig)} {_plage(js)}" for sig, js in autres.items()]
    if fermes:
        morceaux.append(f"fermé {_plage(fermes)}")
    return " ; ".join(morceaux) + "."


# --- diagnostic --------------------------------------------------------------------------------

def _etat_date(nom: str, valeur: str | None, provenance: dict) -> Etat:
    source = provenance.get(nom)
    if valeur is None:
        return Etat("doute", f"pas de date de {'début' if nom == 'date_debut' else 'fin'}")
    if source == "humain":
        return OK
    if source is None:
        return Etat("doute", f"date de {'début' if nom == 'date_debut' else 'fin'} venue du classeur, "
                             "non confirmée par la page du musée")
    if source in PROVENANCES_DOUTEUSES:
        return Etat("doute", f"date de {'début' if nom == 'date_debut' else 'fin'} : {PROVENANCES_DOUTEUSES[source]}")
    if source == "absente":
        return Etat("doute", f"date de {'début' if nom == 'date_debut' else 'fin'} introuvable sur la page")
    return OK


def diagnostiquer(expo: dict, lieu: dict, gratuite_json: str | None, horaires_texte: str | None,
                  aujourdhui: date | None = None) -> dict[str, Etat]:
    """État de chaque élément de la fiche publique. `expo` et `lieu` : lignes de la base (ou dicts)."""
    provenance = json.loads(expo.get("provenance") or "{}")
    etats: dict[str, Etat] = {}

    etats["lieu"] = OK if lieu["statut"] == "verifie" else Etat(
        "doute", "lieu pas encore vérifié : l'exposition ne partira pas sur le site tant qu'il ne l'est pas")

    titre_source = provenance.get("titre")
    etats["titre"] = OK if titre_source in ("carte", "fiche", "humain") else Etat(
        "doute", "titre venu du classeur, non confirmé par la page du musée")

    if expo.get("image_url"):
        etats["image"] = OK
    elif expo.get("portee") == "permanent" and lieu.get("logo_url"):
        etats["image"] = Etat("doute", "pas d'image propre : le site prendra le logo du lieu")
    else:
        etats["image"] = Etat("manque", "pas d'image : le site affichera un visuel neutre")

    etats["description"] = OK if expo.get("description") else Etat(
        "manque", "pas de description : la fiche n'aura que l'accroche du site")

    if not expo.get("date_debut") and not expo.get("date_fin"):
        etats["dates"] = (OK if expo.get("portee") == "permanent" else
                          Etat("manque", "aucune date : une exposition sans date n'est jamais montrée sur le site"))
    else:
        debut = _etat_date("date_debut", expo.get("date_debut"), provenance)
        fin = _etat_date("date_fin", expo.get("date_fin"), provenance)
        doutes = [e.raison for e in (debut, fin) if e.etat != "ok"]
        etats["dates"] = Etat("doute", " ; ".join(doutes)) if doutes else OK
        if aujourdhui and expo.get("date_fin") and expo["date_fin"] < aujourdhui.isoformat():
            etats["dates"] = Etat("manque", f"exposition terminée le {date_fr(expo['date_fin'])} : elle ne sera jamais "
                                            "montrée, à rejeter (ou corriger la date de fin si elle est prolongée)")

    if provenance.get("portee") == "incertaine":
        etats["portee"] = Etat("doute", "collections permanentes ou exposition temporaire ? La page ne le dit pas, "
                                        "et la gratuité en dépend")
    else:
        etats["portee"] = OK

    etats["lien"] = OK if expo.get("url") else Etat("manque", "pas de lien vers la page de l'exposition")

    etats["horaires"] = OK if horaires_texte else Etat(
        "manque", "le lieu n'a pas d'horaires : le site dira « non communiqués »")

    if not gratuite_json:
        etats["tarif"] = Etat("manque", "gratuité pas encore calculée")
    else:
        g = json.loads(gratuite_json)
        if g["statut"] == "a_confirmer":
            etats["tarif"] = Etat("doute", f"à confirmer : {g['raison']}")
        elif g.get("source") == "famille":
            etats["tarif"] = Etat("doute", f"déduite de la règle de la famille de musées, pas d'un tarif lu sur le site "
                                           f"du lieu ({g['raison']})")
        elif g["statut"] == "reduit_26" and g.get("prix") is None:
            etats["tarif"] = Etat("doute", "tarif réduit, montant inconnu")
        else:
            etats["tarif"] = OK

    etats["reservation"] = Etat("doute", "le collecteur ne sait pas si la réservation est nécessaire : "
                                         "le site renverra vers la billetterie du musée")
    return etats
