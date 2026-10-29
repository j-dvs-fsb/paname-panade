"""Extracteurs : du déterministe, sans modèle. Un extracteur par mutualisation, pas par musée.

Un extracteur expose :
    convient(lieu) -> bool
    extraire(page_html, url_page, aujourdhui) -> list[ExpoBrute]     (ou extraire_pour(lieu_id, ...))
    source(lieu) -> str                                             (facultatif : sinon lieu["expos_url"])
et déclare pour chaque champ d'où il le tient (`provenance`) : c'est `validate` qui
traduit cette provenance en score de confiance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from types import ModuleType


@dataclass
class ExpoBrute:
    titre: str
    url: str | None = None
    image_url: str | None = None
    date_debut: str | None = None
    date_fin: str | None = None
    description: str | None = None
    portee: str = "temporaire"
    provenance: dict[str, str] = field(default_factory=dict)


def disponibles() -> dict[str, ModuleType]:
    from panade.extractors import generique, paris_musees
    # L'ordre compte : un extracteur de mutualisation passe avant la config générique.
    return {"paris_musees": paris_musees, "generique": generique}


def choisir(lieu) -> tuple[str, ModuleType] | None:
    """L'extracteur d'un lieu, ou None. Un lieu T4 n'a jamais d'extracteur : c'est du manuel."""
    if lieu["tier"] == "T4":
        return None
    for nom, module in disponibles().items():
        if module.convient(lieu):
            return nom, module
    return None


__all__ = ["ExpoBrute", "choisir", "disponibles", "date"]
