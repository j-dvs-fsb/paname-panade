"""Lecture des périodes écrites en français : « 15 septembre 2026 - 24 janvier 2027 »,
« du 3 mars au 12 juillet 2026 », « jusqu'au 13 décembre », « à partir du 10 novembre ».

Une année absente est déduite de la date du jour, et signalée : ce n'est jamais
aussi sûr qu'une année écrite.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

MOIS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12, "décembre": 12,
}
_MOIS_RE = "|".join(sorted(MOIS, key=len, reverse=True))
_DATE = rf"(?P<j{{n}}>\d{{{{1,2}}}})(?:er)?\s+(?P<m{{n}}>{_MOIS_RE})(?:\s+(?P<a{{n}}>\d{{{{4}}}}))?"
_D1 = _DATE.format(n=1)
_D2 = _DATE.format(n=2)

# Du plus précis au plus général : le premier motif qui correspond gagne.
_MOTIFS = (
    ("intervalle", re.compile(rf"(?:du\s+)?{_D1}\s*(?:-|–|—|au|à)\s*{_D2}", re.I)),
    ("jusqua", re.compile(rf"(?:jusqu['’]au|jusqu['’]à|jusqu['’]en)\s+{_D1}", re.I)),
    ("depuis", re.compile(rf"(?:à\s+partir\s+du|dès\s+le|depuis\s+le|ouvre\s+le|à\s+partir\s+de)\s+{_D1}", re.I)),
    ("seule", re.compile(_D1, re.I)),
)


@dataclass(frozen=True)
class Periode:
    debut: str | None
    fin: str | None
    annee_deduite: bool = False


def _construire(j: str, m: str, a: str | None, defaut: int) -> date | None:
    try:
        return date(int(a) if a else defaut, MOIS[m.lower()], int(j))
    except ValueError:
        return None


def analyser(texte: str, aujourdhui: date) -> Periode | None:
    """Première période trouvée dans `texte`, ou None. Ne devine jamais une date absente."""
    texte = re.sub(r"\s+", " ", texte)
    for nom, motif in _MOTIFS:
        trouve = motif.search(texte)
        if not trouve:
            continue
        g = trouve.groupdict()
        if nom == "intervalle":
            fin = _construire(g["j2"], g["m2"], g["a2"], aujourdhui.year)
            if fin is None:
                return None
            if g["a1"]:
                debut = _construire(g["j1"], g["m1"], g["a1"], fin.year)
            else:  # « du 3 mars au 12 juillet 2026 » : le début hérite de l'année de la fin
                debut = _construire(g["j1"], g["m1"], None, fin.year)
                if debut and debut > fin:
                    debut = debut.replace(year=fin.year - 1)
            if debut is None or debut > fin:
                return None
            return Periode(debut.isoformat(), fin.isoformat(), annee_deduite=not (g["a1"] and g["a2"]))
        d = _construire(g["j1"], g["m1"], g["a1"], aujourdhui.year)
        if d is None:
            return None
        deduite = not g["a1"]
        if deduite and nom == "jusqua" and d < aujourdhui - timedelta(days=60):
            d = d.replace(year=d.year + 1)   # « jusqu'au 13 décembre » dit en janvier : l'année suivante
        if nom == "jusqua":
            return Periode(None, d.isoformat(), deduite)
        if nom == "depuis":
            return Periode(d.isoformat(), None, deduite)
        return Periode(d.isoformat(), None, deduite)
    return None
