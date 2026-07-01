# Paname Panade

Site qui regroupe **toutes les expositions et musées gratuits pour les -26 ans à Paris**.
Coche les expos faites, note-les, garde ton compte à rebours avant tes 26 ans.

Flask + SQLite + Bootstrap 5. Style noir & blanc, sobre.

## Fonctionnalités

- 🏛️ Fiche par **musée** avec ses **expositions** (chacune sa fiche : dates, horaires, lien billetterie)
- 👤 **Compte perso** (email + mot de passe, prénom + date de naissance)
- ⭐ Ajouter une expo en **favori**, la marquer **« faite »** avec une **note sur 5 étoiles** (affichée sur la fiche)
- 🎲 Mode **expo gratuite au hasard**
- 📊 **Barre de progression** (expos faites / total)
- 😄 **Stats fun** : jours avant tes 26 ans, nombre d'expos/semaine pour tout faire à temps

## Installation

```bash
cd ~/paname-panade
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Données

Approche **hybride** :

1. **Musées gratuits en permanence** → liste éditoriale curée :
   ```bash
   python scripts/seed.py
   ```
2. **Expositions temporaires gratuites** → API officielle « Que Faire à Paris ? »
   (`opendata.paris.fr`, Opendatasoft, gratuite, sans clé) :
   ```bash
   python scripts/sync_data.py --limit 200
   ```
   Rejouable à volonté (idempotent via `external_id`). À mettre en cron pour rafraîchir.

## Lancer

```bash
python run.py
# → http://localhost:5000
```

## Structure

```
paname-panade/
├── run.py                # point d'entrée
├── config.py             # config (SECRET_KEY, DB)
├── paname/
│   ├── __init__.py       # app factory
│   ├── extensions.py     # db, login_manager
│   ├── models.py         # User, Museum, Exposition, Favorite, Visit
│   ├── auth.py           # inscription / connexion
│   ├── main.py           # routes (fiches, favoris, fait, hasard, profil)
│   ├── stats.py          # progression + stats fun
│   ├── templates/
│   └── static/css/style.css
└── scripts/
    ├── seed.py           # musées permanents
    └── sync_data.py      # API Que Faire à Paris
```

## Production

- Définis `SECRET_KEY` (variable d'environnement).
- Sers via `gunicorn "paname:create_app()"` derrière un reverse proxy.
