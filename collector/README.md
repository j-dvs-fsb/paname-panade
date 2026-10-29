# Panade Collector

Collecte, range et valide les données des musées parisiens, puis produira chaque
matin un `export.json` pour le site. Le brief complet est dans [CLAUDE.md](CLAUDE.md).

Ce dossier est autonome (son propre `pyproject.toml`, aucun import du site Node) :
il peut être déplacé tel quel dans son propre dépôt.

**Avancement : étape 1 sur 8** (schéma SQLite et import du classeur).

## Installation

Python 3.11 ou plus.

```bash
cd collector
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
```

## Premier lancement

```bash
panade init
```

Crée `data/panade.db` (ignoré par git) et la remplit depuis `data/PP_lieux_v2.xlsx`.
Relancée, la commande ne touche à rien : une fois la base remplie, c'est elle qui fait
foi, le classeur n'est plus relu. Pour repartir de zéro, supprimer le fichier `.db`.
La sauvegarde est une copie du fichier.

Le fichier se règle avec `--db` ou la variable `PANADE_DB`.

## Tests

```bash
pytest
```

Hors ligne, aucune requête réseau.

## Ce que l'import fait du classeur

| Onglet | Table | Remarques |
|---|---|---|
| Familles | `familles` | Textes de gratuité conservés tels quels, sans interprétation (étape 7). |
| Lieux | `lieux` | `statut` et `confiance_famille` traduits (`vérifié` en `verifie`...). Les colonnes de formules « héritées » sont ignorées. |
| Tarifs | `tarifs` | Un prix absent reste `NULL`, jamais 0. Un `gratuit` exige un 0 explicite. |
| Horaires, Fermetures | `horaires`, `fermetures` | Dates et heures vérifiées par le schéma. |
| Expositions | `expositions` | Toutes importées en `en_revue`, sans score : rien n'est publiable avant relecture. |
| Suivi, Lisez-moi | | Ignorés. |

L'import est tout ou rien : toutes les lignes sont validées avant la première
insertion, et chaque erreur est listée avec son onglet et sa ligne.

Liens invalides du classeur (`A TROUVER...`, `PAS DE LOGO RECUPERE`) : mis à `NULL`
et signalés. Pour `expos_url`, `tarifs_url` et `horaires_url`, le texte d'origine est
gardé dans `notes_crawler`. `LOGO_MUSEE` devient `NULL` : le logo du lieu sera repris
à l'export (étape 6).

Colonnes ajoutées au schéma du brief, pour ne pas perdre d'information du classeur :
`lieux.notes`, `lieux.confiance_famille`, `familles.source`. Trois valeurs d'`audience`
du classeur absentes du brief : `enseignant_arts_visuels`, `18_29_ans`, `partenariats`.

## Structure

```
collector/
├── CLAUDE.md             # brief du projet
├── data/PP_lieux_v2.xlsx # graine de la base
├── src/panade/
│   ├── schema.sql        # les 7 tables et leurs contraintes
│   ├── models.py         # modèles pydantic stricts
│   ├── seed.py           # import du classeur
│   ├── db.py             # connexion, création du schéma
│   └── cli.py            # commande `panade`
└── tests/
```
