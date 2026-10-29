"""Lecture des périodes écrites en français : « 15 septembre 2026 - 24 janvier 2027 »,
« du 3 mars au 12 juillet 2026 », « jusqu'au 13 décembre », « à partir du 10 novembre »,
« 01 janv. 2026 - 31 déc. 2026 », « du 14/10/2026 au 04/04/2027 », « 17.06 au 28.09.2026 ».

Une année absente est déduite de la date du jour, et signalée : ce n'est jamais
aussi sûr qu'une année écrite. Une date en chiffres sans année n'est jamais lue seule.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

MOIS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    # abréviations courantes (avec ou sans point)
    "janv": 1, "jan": 1, "fevr": 2, "fev": 2, "avr": 4, "juil": 7, "sept": 9, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MOIS_RE = (r"(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre"
            r"|janv?\.?|f[ée]vr?\.?|avr\.?|juil\.?|sept?\.?|oct\.?|nov\.?|d[ée]c\.?)(?![a-zà-ÿ])")
_TIRET = r"(?:-|\u2013|\u2014|au|à)"   # trait d'union, tirets demi-cadratin et cadratin


def _lettres(n: int) -> str:
    return rf"(?P<j{n}>\d{{1,2}})(?:er)?\s+(?P<m{n}>{_MOIS_RE})(?:\s+(?P<a{n}>\d{{4}}))?"


def _chiffres(n: int, annee_obligatoire: bool = False) -> str:
    annee = rf"[./](?P<a{n}>\d{{4}}|\d{{2}})" + ("" if annee_obligatoire else "?")
    if not annee_obligatoire:
        annee = rf"(?:[./](?P<a{n}>\d{{4}}|\d{{2}}))?"
    return rf"(?<![\d./])(?P<j{n}>\d{{1,2}})[./](?P<m{n}>\d{{1,2}}){annee}(?![\d./]*\d)"


# Du plus précis au plus général : le premier motif qui correspond gagne.
_MOTIFS = []
for _D1, _D2, _nature in ((_lettres(1), _lettres(2), "lettres"), (_chiffres(1), _chiffres(2), "chiffres")):
    _MOTIFS += [
        ("intervalle", _nature, re.compile(rf"(?:du\s+)?{_D1}\s*{_TIRET}\s*(?:le\s+)?{_D2}", re.I)),
        ("jusqua", _nature, re.compile(rf"(?:jusqu['’]\s?au|jusqu['’]\s?à|jusqu['’]\s?en)\s+{_D1}", re.I)),
        ("depuis", _nature, re.compile(rf"(?:à\s+partir\s+du|dès\s+le|depuis\s+le|ouvre\s+le|à\s+partir\s+de)\s+{_D1}", re.I)),
    ]
# Deux dates complètes côte à côte, séparées par une icône (quai Branly) : années écrites obligatoires.
_MOTIFS += [("intervalle", "lettres", re.compile(
    rf"(?P<j1>\d{{1,2}})(?:er)?\s+(?P<m1>{_MOIS_RE})\s+(?P<a1>\d{{4}})\s+(?P<j2>\d{{1,2}})(?:er)?\s+(?P<m2>{_MOIS_RE})\s+(?P<a2>\d{{4}})", re.I))]
_MOTIFS += [("seule", "lettres", re.compile(_lettres(1), re.I)),
            ("seule", "chiffres", re.compile(_chiffres(1, annee_obligatoire=True), re.I))]


@dataclass(frozen=True)
class Periode:
    debut: str | None
    fin: str | None
    annee_deduite: bool = False


def _mois(texte: str) -> int | None:
    if texte.isdigit():
        n = int(texte)
        return n if 1 <= n <= 12 else None
    sans = unicodedata.normalize("NFKD", texte.lower().rstrip(".")).encode("ascii", "ignore").decode()
    return MOIS.get(sans)


def _annee(a: str | None, defaut: int) -> int:
    if not a:
        return defaut
    return 2000 + int(a) if len(a) == 2 else int(a)


def _construire(j: str, m: str, a: str | None, defaut: int) -> date | None:
    mois = _mois(m)
    if mois is None:
        return None
    try:
        return date(_annee(a, defaut), mois, int(j))
    except ValueError:
        return None


def analyser(texte: str, aujourdhui: date) -> Periode | None:
    """Première période trouvée dans `texte`, ou None. Ne devine jamais une date absente."""
    texte = re.sub(r"\s+", " ", texte.replace("\xa0", " "))
    for nom, _nature, motif in _MOTIFS:
        trouve = motif.search(texte)
        if not trouve:
            continue
        g = trouve.groupdict()
        if nom == "intervalle":
            fin = _construire(g["j2"], g["m2"], g["a2"], aujourdhui.year)
            if fin is None:
                continue
            debut = _construire(g["j1"], g["m1"], g["a1"] or (g["a2"] if not g["a1"] else None), fin.year)
            if debut and not g["a1"] and debut > fin:
                debut = debut.replace(year=fin.year - 1)   # « du 12 novembre au 3 février 2027 »
            if debut is None or debut > fin:
                return None       # intervalle incohérent : on ne se rabat pas sur une date isolée
            # L'année du début se lit sur la fin (« du 3 mars au 12 juillet 2026 ») : ce n'est pas deviner.
            # Seule une fin sans année oblige à prendre l'année du jour.
            return Periode(debut.isoformat(), fin.isoformat(), annee_deduite=not g["a2"])
        d = _construire(g["j1"], g["m1"], g["a1"], aujourdhui.year)
        if d is None:
            continue
        deduite = not g["a1"]
        if deduite and nom == "jusqua" and d < aujourdhui - timedelta(days=60):
            d = d.replace(year=d.year + 1)   # « jusqu'au 13 décembre » dit en janvier : l'année suivante
        if nom == "jusqua":
            return Periode(None, d.isoformat(), deduite)
        return Periode(d.isoformat(), None, deduite)
    return None
