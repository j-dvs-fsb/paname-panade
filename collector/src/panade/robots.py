"""Lecture de robots.txt selon la RFC 9309.

Le module `urllib.robotparser` de la bibliothèque standard ne gère pas les
jokers (`*`, `$`) que presque tous les robots.txt Drupal utilisent : on écrit
donc le nôtre. Règle de décision : la règle la plus longue gagne, et à
longueur égale Allow l'emporte.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Robots:
    groupes: dict[str, list[tuple[bool, re.Pattern, int]]] = field(default_factory=dict)
    sitemaps: list[str] = field(default_factory=list)

    @classmethod
    def lire(cls, texte: str) -> "Robots":
        robots = cls()
        agents: list[str] = []
        dans_les_regles = False
        for brut in texte.splitlines():
            ligne = brut.split("#", 1)[0].strip()
            if ":" not in ligne:
                continue
            cle, valeur = (s.strip() for s in ligne.split(":", 1))
            cle = cle.lower()
            if cle == "user-agent":
                if dans_les_regles:  # un nouveau groupe commence
                    agents, dans_les_regles = [], False
                agents.append(valeur.lower())
                robots.groupes.setdefault(valeur.lower(), [])
            elif cle in ("allow", "disallow") and agents:
                dans_les_regles = True
                if not valeur:  # « Disallow: » vide = tout permis, pas de règle
                    continue
                motif = _compiler(valeur)
                for agent in agents:
                    robots.groupes[agent].append((cle == "allow", motif, len(valeur)))
            elif cle == "sitemap" and valeur:
                robots.sitemaps.append(valeur)
        return robots

    def autorise(self, produit: str, chemin: str) -> bool:
        """`produit` : le jeton de notre User-Agent (« PanadeCollector »)."""
        regles = self.groupes.get(produit.lower())
        if regles is None:
            regles = self.groupes.get("*", [])
        meilleur: tuple[int, bool] | None = None
        for autorise, motif, longueur in regles:
            if motif.match(chemin) and (meilleur is None or (longueur, autorise) > meilleur):
                meilleur = (longueur, autorise)
        return True if meilleur is None else meilleur[1]


def _compiler(motif: str) -> re.Pattern:
    fin = motif.endswith("$")
    corps = motif[:-1] if fin else motif
    expr = ".*".join(re.escape(morceau) for morceau in corps.split("*"))
    return re.compile(expr + ("$" if fin else ""))
