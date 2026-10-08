# Paname Panade

Site qui regroupe **les expositions et musées gratuits ou à tarif réduit pour les -26 ans à Paris**.
Coche les expos faites, note-les, garde ton compte à rebours avant tes 26 ans.

Node.js (Express, Nunjucks, Sequelize) + SQLite en local, MariaDB en production + Bootstrap 5.
Style noir & blanc, sobre.

## Fonctionnalités

- 🏛️ Fiche par **musée** avec ses **expositions** (chacune sa fiche : dates, horaires, lien billetterie)
- 📡 **Radar** des musées gratuits autour de toi, par distance et direction
- 👤 **Compte perso** (email + mot de passe, Google ou passkey, prénom + date de naissance)
- ⭐ Ajouter une expo en **favori**, la marquer **« faite »** avec une **note sur 5 étoiles** (affichée sur la fiche)
- 🎲 Mode **expo gratuite au hasard**
- 📊 **Barre de progression** (expos faites / total)
- 😄 **Stats fun** : jours avant tes 26 ans, nombre d'expos/semaine pour tout faire à temps
- 🛠️ **Back-office** (`/admin`) : validation des expos, musées, utilisateurs, pages éditables

## Installation

Node 20 ou plus.

```bash
cd ~/paname-panade
npm install
```

En local, rien d'autre à configurer : la base SQLite (`instance/paname.sqlite`) est créée
au premier démarrage. Les variables d'environnement (voir `.env.example`) ne servent
qu'à surcharger les valeurs par défaut.

## Données

Approche **hybride** :

1. **Musées gratuits en permanence** → liste éditoriale curée, semée automatiquement
   au premier démarrage sur une base vide, ou à la main :
   ```bash
   npm run seed
   ```
2. **Expositions temporaires gratuites** → API officielle « Que Faire à Paris ? »
   (`opendata.paris.fr`, Opendatasoft, gratuite, sans clé) :
   ```bash
   npm run sync -- --limit 200
   ```
   Rejouable à volonté (idempotent via `external_id`). À mettre en cron pour rafraîchir.
3. **Musées officiels d'Île-de-France** (coordonnées GPS, identifiants) :
   ```bash
   npm run sync-museums
   ```
4. **Sites de musées** (Louvre, Paris Musées) → les expos arrivent en brouillon,
   à valider dans l'admin :
   ```bash
   npm run scrape            # simulation
   npm run scrape -- --commit
   ```

Donner les droits admin à un compte existant :

```bash
npm run make-admin -- <email>
```

## Lancer

```bash
npm run dev
# → http://localhost:3000
```

`npm start` lance le serveur sans rechargement automatique.

## Structure

```
paname-panade/
├── server.js             # point d'entrée (base, amorçage, écoute)
├── src/
│   ├── app.js            # Express : en-têtes de sécurité (CSP), sessions, routes
│   ├── config.js         # configuration (variables d'environnement)
│   ├── auth/             # Better Auth : mot de passe, Google, passkeys
│   ├── models/           # Sequelize : User, Museum, Exposition, Favorite, Visit…
│   ├── routes/           # main (fiches, favoris, fait, hasard, profil), auth, admin…
│   ├── services/         # synchronisations, seed, stats, cache d'images, migrations
│   ├── scrapers/         # scrapers de sites de musées
│   ├── lib/              # tarifs, dates, SEO, texte, doublons…
│   └── middleware/       # session utilisateur, CSRF, limitation de débit
├── views/                # gabarits Nunjucks
├── public/css/style.css  # feuille de style
└── scripts/              # commandes `npm run …` (seed, sync, scrape, make-admin)
```

## Production

Voir [DEPLOY.md](DEPLOY.md) : hébergement Node.js Infomaniak, MariaDB, variables
d'environnement (`SECRET_KEY`, `DATABASE_URL`, `SITE_URL`…) et première mise en ligne.
