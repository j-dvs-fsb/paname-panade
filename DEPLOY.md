# Déploiement — Paname Panade (Node.js sur Infomaniak)

L'application web est en **Node.js** (Express + Nunjucks + Sequelize). Elle tourne sur
l'**Hébergement Web Infomaniak** via un site de type **Node.js**, et se connecte à la
**MariaDB** de l'hébergement.

## 1. Base de données
- Local (dev) : SQLite par défaut (`instance/paname.sqlite`), rien à configurer.
- Prod : MariaDB Infomaniak. Renseigne `DATABASE_URL` (voir `.env.example`) :
  ```
  DATABASE_URL=mysql://<user>:<motdepasse>@<hote>:3306/<base>
  ```
  Le schéma est créé automatiquement au démarrage (`sequelize.sync()`).

## 2. Variables d'environnement (Manager Infomaniak → site Node.js)
| Variable | Valeur |
|---|---|
| `SECRET_KEY` | chaîne aléatoire longue (`openssl rand -hex 32`) |
| `DATABASE_URL` | `mysql://user:pass@hote:3306/base` |
| `NODE_ENV` | `production` |
| `ADMIN_EMAIL` | ton email (compte admin créé au 1er démarrage) |
| `ADMIN_PASSWORD` | un mot de passe fort |
| `ADMIN_PRENOM` | ton prénom (optionnel) |
| `PORT` | **fournie automatiquement par Infomaniak** — ne pas fixer |

⚠️ Ne mets jamais ces secrets dans le code ni sur GitHub. Le mot de passe DB partagé
en clair doit être **changé** (il a été exposé).

## 3. Réglages du site Node.js (Manager)
- **Version de Node** : LTS récente (≥ 20).
- **Dossier d'exécution** : racine du dépôt (où se trouve `package.json`).
- **Commande de build** : `npm install`
- **Commande de lancement** : `npm start`
- **Point d'entrée** : `server.js` (écoute sur `process.env.PORT`).

## 4. Première mise en ligne (sans commande SSH)
Au **premier démarrage** l'app s'initialise seule (cf. `src/bootstrap.js`) :
- elle crée les **musées curés** si la base est vide ;
- elle crée le **compte admin** à partir de `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

Il reste juste à peupler les **expositions** : connecte-toi avec ton compte admin,
va sur `/admin` et clique **« ↻ Sync Que Faire à Paris »**. C'est rejouable à volonté.

> Si tu as un accès shell : `npm run sync` fait la même chose, et peut se mettre en cron
> pour rafraîchir régulièrement. Sans shell, le bouton du dashboard suffit.

### Envoyer le code sur le serveur (depuis ton Mac)
```bash
rsync -avz --delete \
  --exclude node_modules --exclude .git --exclude .venv \
  --exclude instance --exclude .env --exclude __pycache__ --exclude '.DS_Store' \
  ~/paname-panade/ \
  <user>@<hote-ssh>:sites/paname-panade.fr/
```

## 5. Scripts utiles
| Commande | Rôle |
|---|---|
| `npm start` | lance le serveur |
| `npm run seed` | musées gratuits permanents (liste curée) |
| `npm run sync [-- --limit N]` | sync expos QFAP |
| `npm run scrape [-- --commit]` | scrape sites musées (Louvre, Paris Musées) → brouillons |
| `npm run make-admin -- <email> [--off]` | (dé)promotion admin |

## 6. GitHub
Le dépôt sert de source de vérité. `.env`, `instance/`, `node_modules/` sont déjà
gitignorés. Push sur GitHub, puis branche le déploiement Infomaniak sur le dépôt.
