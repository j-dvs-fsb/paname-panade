# Panade Collector

Collecte, range et valide les données des musées parisiens, puis pousse chaque matin un
`export.json` vers le site. Le brief complet est dans [CLAUDE.md](CLAUDE.md), le contrat de
l'export dans [docs/export.md](docs/export.md).

Ce dossier est autonome (son propre `pyproject.toml`, aucun import du site Node) : il peut
être déplacé tel quel dans son propre dépôt.

**Avancement : les 8 étapes du brief sont construites.** Ce qui reste est de la donnée et du
branchement (voir « À faire »), pas du code de base.

## Installation

Python 3.11 ou plus.

```bash
cd collector
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[review]'
panade init
```

`panade init` crée `data/panade.db` (ignoré par git) depuis `data/PP_lieux_v2.xlsx`. Relancée,
elle ne réimporte rien (elle migre seulement le schéma si besoin). La base fait foi une fois
remplie : pour repartir de zéro, supprimer le fichier. La sauvegarde est une copie du fichier.

## Les commandes

| Commande | Ce qu'elle fait | Réseau |
|---|---|---|
| `panade probe <lieu_id>`, `--verifies` | classe en T0..T4, rien d'écrit sans `--ecrire` | oui, poli |
| `panade discover <lieu_id>` | trouve la page des expositions, garde une fixture réduite | oui, poli |
| `panade collect [--lieu X]` | fait tourner les extracteurs, **aucun appel de modèle** | oui, poli |
| `panade validate` | conformité, doublons, confiance, gratuité calculée | non |
| `panade review` | écran de relecture local (`http://127.0.0.1:8765`) | non |
| `panade export` | produit `data/exports/export-….json`, ne publie pas | non |
| `panade publish [--a-blanc]` | garde-fous, puis POST vers le site | le site seul |
| `panade health [--alerter]` | lieux muets, extracteurs cassés, données périmées | non |

Chaque lieu passe par le même chemin :

```
collect (03h)  ->  validate (04h)  ->  relecture si besoin  ->  publish (07h)
```

Une exposition lue de façon sûre (dates lisibles par une machine, titre et lien présents) est
publiée par `validate`. Les autres attendent une personne dans `panade review`, avec le motif
affiché : dates déduites, portée incertaine, gratuité modifiée, disparue de la page.

## Ce que le code garantit

- **La gratuité n'est jamais lue sur une page.** Elle est calculée par `gratuite.py` (fonction
  pure) : lignes de tarifs vérifiées du lieu, sinon règle de la famille, sauf `gratuite_override`
  qui prime. Tout ce qui n'est pas interprétable donne `a_confirmer`, jamais un gratuit.
  Deux tarifs contradictoires donnent `a_confirmer`.
- **Aucun champ vide dans l'export** : pas de `null`, pas de chaîne vide.
- **Un lieu `a_verifier` n'exporte aucune exposition.** Une donnée vérifiée il y a plus de 120
  jours est signalée périmée.
- **Les trois garde-fous de `publish`** : moins de 70 % des expos attendues (refus), un lieu qui
  n'en a plus (on garde la veille, pour lui seul), une gratuité modifiée sans relecture (l'expo
  sort de l'export). Le garde-fou 2 ne reprend jamais ce qu'une règle ou une personne a retiré.
- **Politesse réseau** (`http.py`, le seul code qui parle au réseau) : `robots.txt` lu et
  respecté avant toute page, un `robots.txt` en panne fait s'abstenir sans conclure à un T4,
  une requête par seconde et par domaine, User-Agent identifiable, requêtes conditionnelles,
  jamais de contournement d'une protection.
- **Le travail humain n'est jamais écrasé** : une correction faite dans l'écran de relecture
  reste, une valeur absente de la page n'efface pas une valeur connue, une exposition rejetée
  ne revient pas, une extraction vide ne dépublie rien.

## Planification

`deploy/panade.cron` (cron) ou `deploy/systemd/` (timers, avec rattrapage si la machine dormait).
Les secrets vont dans `.env` (chmod 600) :

```
PANADE_PUBLISH_URL=https://paname-panade.fr/api/import
PANADE_PUBLISH_TOKEN=...
PANADE_ALERT_WEBHOOK=...        # facultatif, format compatible Slack, Mattermost, Discord
```

Un lieu silencieux deux nuits de suite déclenche une alerte à la fin de `collect`, puis une
fois par semaine tant qu'il l'est. Les alertes vont dans `data/alertes.log`.

## Constats du 2026-10-29 (premier passage sur les vrais sites)

- **Musée de Montmartre.** Le brief et le classeur disent « le `robots.txt` interdit les robots ».
  Le fichier actuel ne l'interdit pas (`Allow: /`, quelques chemins exclus). Le lieu reste en T4,
  décision du brief, et rien n'est téléchargé : à réexaminer par une personne.
- **Paris Musées.** Ce jour-là, 6 des 12 sites répondaient par une page de maintenance (503), 3
  n'ont aucune URL dans la base (Cernuschi, Cognacq-Jay, Libération). Seuls Carnavalet, Bourdelle
  et Petit Palais ont pu être lus. Les chemins des pages d'expositions varient plus que le brief
  ne le dit : `discover` les trouve et `--ecrire` enregistre l'`expos_url`.
- **madparis.fr** coupe la connexion aux robots : MAD et Nissim de Camondo restent
  indéterminés, sans contournement.
- **Tiers du classeur.** Sur les 9 lieux vérifiés, la sonde confirme 3 tiers (Bourse de Commerce,
  IMA, Montmartre), en contredit 3 (Cartier : T3 au lieu de T1, mahJ : T2 au lieu de T1, Musée de
  la musique : T1 au lieu de T3) et n'a pas pu conclure pour 3 (Vie romantique en maintenance, MAD et
  Nissim de Camondo qui coupent la connexion). Les tiers du classeur étaient posés à la main :
  `panade probe --verifies` les contrôle.
- **T0 non validé en direct.** La requête vers « Que Faire à Paris » a répondu une fois avec
  les bons événements du mahJ, puis le réseau du bac à sable a coupé la connexion. La logique est
  testée hors ligne contre le schéma réel de l'API, pas confirmée de bout en bout.
- **Données du classeur.** Horaires du mahJ valides jusqu'au 14 octobre (expirés). Tarifs du mahJ
  contradictoires pour les expos temporaires (gratuit pour tous, et 5 € pour les moins de 26
  ans) : `a_confirmer` tant que la ligne « galerie contemporaine » n'est pas rattachée à son
  espace.

## À faire

- Brancher le site : un point d'entrée qui respecte [docs/export.md](docs/export.md). Rien n'a
  été modifié dans le site Node.
- Vérifier des lieux (`statut`) : tant qu'un lieu est `a_verifier`, aucune de ses expositions
  ne sort. Aujourd'hui seuls 9 lieux sur 57 sont vérifiés, et un seul (Vie romantique) a un
  extracteur.
- Extracteurs pour les autres mutualisations : Drupal avec agenda filtrable (mahJ, IMA), billetterie
  Tickeasy/Vivaticket, flux RSS de MAD. Une mutualisation à la fois, avec `discover`.
- Source OpenAgenda Île-de-France pour `probe` : non vérifiable depuis l'environnement de
  développement (connexion coupée).

## Tests

```bash
pip install -e '.[dev]'
pytest
```

Hors ligne : les pages et `robots.txt` réels du 2026-10-29 sont dans `tests/fixtures/`. Aucun
test ne touche un site réel.

## Ce que l'import fait du classeur

| Onglet | Table | Remarques |
|---|---|---|
| Familles | `familles` | Textes de gratuité gardés tels quels ; `gratuite.py` n'en reconnaît que trois, le reste donne `a_confirmer`. |
| Lieux | `lieux` | `statut` et `confiance_famille` traduits. Les colonnes de formules « héritées » sont ignorées. |
| Tarifs | `tarifs` | Un prix absent reste `NULL`, jamais 0. Un `gratuit` exige un 0 explicite. |
| Horaires, Fermetures | `horaires`, `fermetures` | Dates et heures vérifiées par le schéma. |
| Expositions | `expositions` | Toutes importées en `en_revue`, sans score : rien n'est publiable avant relecture. |
| Suivi, Lisez-moi | | Ignorés. |

L'import est tout ou rien : toutes les lignes sont validées avant la première insertion, et
chaque erreur est listée avec son onglet et sa ligne. Les liens invalides (`A TROUVER...`) sont mis
à `NULL` et signalés ; `LOGO_MUSEE` devient `NULL` et l'export reprend le logo du lieu.

Colonnes ajoutées au schéma du brief pour ne rien perdre : `lieux.notes`, `lieux.confiance_famille`,
`familles.source`, `expositions.provenance`, `motif_revue` et `gratuite_validee`, et dans `runs` les
validateurs HTTP et l'empreinte de la page. Trois valeurs d'`audience` du classeur absentes du
brief : `enseignant_arts_visuels`, `18_29_ans`, `partenariats`.

## Structure

```
collector/
├── CLAUDE.md                 brief du projet
├── docs/export.md            contrat de l'export, à lire côté site
├── data/PP_lieux_v2.xlsx     graine de la base
├── deploy/                   cron, systemd, run.sh
├── src/panade/
│   ├── schema.sql, db.py     schéma v2 et migrations
│   ├── models.py, seed.py    modèles stricts, import du classeur
│   ├── http.py, robots.py    client poli, robots.txt (RFC 9309)
│   ├── probe.py, discover.py classer un lieu, trouver sa page d'expositions
│   ├── extractors/           un extracteur par mutualisation
│   ├── collect.py            collecte conditionnelle
│   ├── validate.py           conformité, doublons, confiance
│   ├── gratuite.py           moteur de gratuité (fonction pure)
│   ├── review/               écran de relecture
│   ├── export.py, publish.py export et garde-fous
│   └── health.py, alerts.py  santé et alertes
└── tests/
```
