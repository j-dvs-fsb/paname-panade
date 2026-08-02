# Déploiement - Paname Panade (Node.js sur Infomaniak)

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
| `SITE_URL` | `https://paname-panade.fr` - fige les URL canoniques, le sitemap et le retour OAuth |
| `GOOGLE_CLIENT_ID` | (optionnel) identifiant OAuth Google |
| `GOOGLE_CLIENT_SECRET` | (optionnel) secret OAuth Google |
| `PORT` | **fournie automatiquement par Infomaniak** - ne pas fixer |

### Authentification (Better Auth)
Les comptes, sessions et connexions sociales passent par **Better Auth**. Les tables
`session`, `account` et `verification` sont créées automatiquement au démarrage
(`sequelize.sync()`), et une mini-migration reprend les mots de passe existants depuis
`user.password_hash` vers `account.password` - **les comptes déjà créés continuent de se
connecter avec leur mot de passe actuel, sans réinitialisation.**

> `better-sqlite3` n'est qu'une dépendance de **développement** (base SQLite locale).
> En production, Better Auth utilise le pool **mysql2** déjà présent : `npm ci --omit=dev`
> reste la bonne commande de build, rien de natif à compiler.

Pour activer la connexion Google, crée un « ID client OAuth » de type *Application Web*
sur <https://console.cloud.google.com/apis/credentials> et déclare l'URI de redirection
`https://<ton-domaine>/api/auth/callback/google`. Sans ces variables, le bouton
n'apparaît pas et le reste de l'authentification fonctionne normalement.

⚠️ Ne mets jamais ces secrets dans le code ni sur GitHub. Le mot de passe DB partagé
en clair doit être **changé** (il a été exposé).

## 3. Réglages du site Node.js (Manager)
- **Version de Node** : LTS récente (≥ 20).
- **Dossier d'exécution** : racine du dépôt (où se trouve `package.json`).
- **Commande de build** : `npm ci --omit=dev`
- **Commande de lancement** : `npm start`
- **Point d'entrée** : `server.js` (écoute sur `process.env.PORT`).

> ⚠️ **`npm ci`, jamais `npm install`.** Cette commande est rejouée à chaque
> construction. `npm install` peut réécrire `package.json` et `package-lock.json`
> sur le serveur : le dépôt et la machine divergent, `git pull` se met à refuser
> de s'appliquer, et `node_modules` finit reconstruit depuis un lock qui n'est
> plus celui du dépôt. `npm ci` lit le lock sans jamais le modifier et reconstruit
> `node_modules` à l'identique.
>
> `--omit=dev` écarte `sqlite3`, réservé au développement : sa compilation native
> échoue souvent en mutualisé, et la production utilise MariaDB.
>
> Si `npm ci` échoue en signalant un décalage entre `package.json` et le lock,
> c'est que le lock n'a pas été régénéré après une modification des dépendances.
> Corriger dans le dépôt (`npm install` en local, puis committer le lock), jamais
> sur le serveur.

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
