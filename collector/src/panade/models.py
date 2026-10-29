"""Modèles pydantic stricts : le vocabulaire canonique de la base et de l'export.

Le classeur a son propre vocabulaire (« vérifié », « oui »...). Il est traduit
dans seed.py, jamais ici : un modèle ne rattrape rien, il rejette.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Annotated, ClassVar, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

Portee = Literal["permanent", "temporaire", "tout"]
PorteeExpo = Literal["permanent", "temporaire"]
Regime = Literal["gratuit", "reduit", "abonnement"]
Audience = Literal[
    "tous", "moins_18", "moins_26", "moins_26_ue", "moins_30", "etudiant",
    "etudiant_art", "demandeur_emploi", "minima_sociaux", "enseignant",
    "handicap", "journaliste", "demandeur_asile",
    # trouvées dans le classeur, absentes du brief
    "enseignant_arts_visuels", "18_29_ans", "partenariats",
]
Tier = Literal["T0", "T1", "T2", "T3", "T4"]
StatutLieu = Literal["a_verifier", "verifie"]
ConfianceFamille = Literal["sur", "a_confirmer"]
EtatExpo = Literal["publie", "en_revue", "rejete"]
Jour = Literal["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
JOURS: tuple[str, ...] = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

# toujours | 1er_dimanche | 1er_samedi[_<saison>] | nocturne_<jour> | apres_16h
# | avant_16h | annuel | <période datée> (jusqu_au_..., du_...)
RECURRENCE_RE = re.compile(
    r"^(toujours|annuel|apres_16h|avant_16h"
    r"|1er_(dimanche|samedi)(_[a-z0-9_]+)?"
    r"|nocturne_(" + "|".join(JOURS) + r")"
    r"|(jusqu_au|du)_[a-z0-9_]+)$"
)


def _iso_date(v: str) -> str:
    try:
        parsed = date.fromisoformat(v)
    except ValueError as exc:
        raise ValueError("date ISO AAAA-MM-JJ attendue") from exc
    if parsed.isoformat() != v:
        raise ValueError("date ISO AAAA-MM-JJ attendue")
    return v


def _recurrence(v: str) -> str:
    if not RECURRENCE_RE.match(v):
        raise ValueError("récurrence inconnue (voir RECURRENCE_RE)")
    return v


IsoDate = Annotated[str, AfterValidator(_iso_date)]
Heure = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
Url = Annotated[str, Field(pattern=r"^https?://\S+$")]
Ident = Annotated[str, Field(pattern=r"^[a-z0-9]+([_-][a-z0-9]+)*$")]
Recurrence = Annotated[str, AfterValidator(_recurrence)]


class Row(BaseModel):
    """Une ligne de table. Strict : aucune conversion implicite, aucun champ en trop."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    table: ClassVar[str]

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        # Invariant 2 : une valeur absente est None, jamais une chaîne vide.
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def values(self) -> dict:
        return self.model_dump()


class Famille(Row):
    table: ClassVar[str] = "familles"

    id: Ident
    libelle: str
    gratuite_permanent: str | None = None
    gratuite_temporaire: str | None = None
    age_max: int | None = Field(default=None, gt=0)
    conditions: str | None = None
    source: str | None = None


class Lieu(Row):
    table: ClassVar[str] = "lieux"

    id: Ident
    nom: str
    famille_id: Ident
    confiance_famille: ConfianceFamille
    tier: Tier | None = None
    statut: StatutLieu = "a_verifier"
    expos_url: Url | None = None
    tarifs_url: Url | None = None
    horaires_url: Url | None = None
    logo_url: Url | None = None
    plateforme_billetterie: str | None = None
    gratuite_override: str | None = None
    notes: str | None = None
    notes_crawler: str | None = None
    verifie_le: IsoDate | None = None
    verifie_par: str | None = None

    @model_validator(mode="after")
    def _verifie_a_une_date(self):
        if self.statut == "verifie" and self.verifie_le is None:
            raise ValueError("un lieu vérifié doit avoir une date de vérification")
        return self


class Tarif(Row):
    table: ClassVar[str] = "tarifs"

    lieu_id: Ident
    portee: Portee
    regime: Regime
    audience: Audience
    prix: float | None = Field(default=None, ge=0)
    plein_tarif: float | None = Field(default=None, ge=0)
    recurrence: Recurrence
    justificatif: str | None = None
    source_url: Url | None = None
    verifie_le: IsoDate | None = None
    verifie_par: str | None = None

    @model_validator(mode="after")
    def _gratuit_est_un_zero_explicite(self):
        if self.regime == "gratuit" and self.prix != 0:
            raise ValueError("un tarif gratuit doit avoir un prix de 0 explicite")
        if self.regime != "gratuit" and self.prix == 0:
            raise ValueError("un prix de 0 n'est pas un tarif réduit ou un abonnement")
        return self


class Horaire(Row):
    table: ClassVar[str] = "horaires"

    lieu_id: Ident
    jour_num: int = Field(ge=1, le=7)
    jour: Jour
    ferme: bool
    ouverture: Heure | None = None
    fermeture: Heure | None = None
    nocturne: bool = False
    portee: Portee = "tout"
    derniere_entree_min: int | None = Field(default=None, ge=0)
    valide_du: IsoDate | None = None
    valide_au: IsoDate | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _coherence(self):
        if JOURS[self.jour_num - 1] != self.jour:
            raise ValueError(f"jour_num {self.jour_num} ne correspond pas à « {self.jour} »")
        if self.ferme and (self.ouverture or self.fermeture):
            raise ValueError("un jour fermé ne peut pas avoir d'heures")
        if not self.ferme and not (self.ouverture and self.fermeture):
            raise ValueError("un jour ouvert doit avoir une ouverture et une fermeture")
        if self.valide_du and self.valide_au and self.valide_au < self.valide_du:
            raise ValueError("valide_au précède valide_du")
        return self


class Fermeture(Row):
    table: ClassVar[str] = "fermetures"

    lieu_id: Ident
    date: str
    libelle: str
    recurrent_annuel: bool
    note: str | None = None

    @model_validator(mode="after")
    def _format_de_la_date(self):
        if self.recurrent_annuel:
            # 2000 est bissextile : 02-29 reste une date valide.
            if not re.fullmatch(r"\d\d-\d\d", self.date):
                raise ValueError("MM-JJ attendu pour une fermeture annuelle")
            _iso_date(f"2000-{self.date}")
        else:
            _iso_date(self.date)
        return self


class Exposition(Row):
    table: ClassVar[str] = "expositions"

    lieu_id: Ident
    titre: str
    portee: PorteeExpo
    date_debut: IsoDate | None = None
    date_fin: IsoDate | None = None
    description: str | None = None
    url: Url | None = None
    image_url: Url | None = None
    gratuite_calculee: str | None = None
    confiance: float | None = Field(default=None, ge=0, le=1)
    etat: EtatExpo = "en_revue"
    hash_source: str | None = None
    vu_le: IsoDate | None = None
    source: str

    @model_validator(mode="after")
    def _coherence(self):
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValueError("date_fin précède date_debut")
        if self.etat == "publie" and self.confiance is None:
            raise ValueError("pas de publication sans score de confiance")
        return self


MODELES: tuple[type[Row], ...] = (Famille, Lieu, Tarif, Horaire, Fermeture, Exposition)
