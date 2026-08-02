# Brief d'implémentation - Refonte musées : gratuité structurée, liste définitive, tableau de scraping

> Document autonome : donne tout le contexte nécessaire à une session Claude Code
> qui n'a jamais vu ce projet. À exécuter tel quel, sauf indication contraire du propriétaire.

---

## 1. Le projet en deux mots

**Paname Panade** (`~/paname-panade`) : site des expos et musées gratuits pour les -26 ans à Paris.
Node.js ≥ 20, Express + Nunjucks + Sequelize. Dev local : SQLite (`instance/paname.sqlite`).
Prod : MariaDB sur hébergement mutualisé Infomaniak, déploiement par `git pull` + redémarrage Manager.

### Conventions NON NÉGOCIABLES du projet
- **Commits en français, sans aucune mention de Claude/IA** (pas de Co-Authored-By, pas de "Generated with").
- **Tout formulaire POST** doit contenir `<input type="hidden" name="_csrf" value="{{ csrf_token() }}">` (middleware CSRF maison, sinon 403).
- **Tout `<script>` inline** doit porter `nonce="{{ csp_nonce }}"` ; gestionnaires inline (onclick…) interdits par la CSP - utiliser `data-confirm` / `data-busy` (gérés par le script global de `base.njk`).
- Pas de nouvelle dépendance npm sauf nécessité absolue (déploiements mutualisés fragiles ; historique douloureux).
- Style de code : suivre l'existant (commentaires en français, mêmes idiomes).
- Les URL passent par `url_for()` (réplique Flask) : chaque route a une entrée dans `src/lib/urls.js`.

### ⚠️ Piège critique : pas d'ALTER automatique
`server.js` fait `sequelize.sync()` **sans** `{ alter: true }` : les tables nouvelles sont créées,
mais **les colonnes ajoutées à une table existante ne le sont PAS**. Toute nouvelle colonne sur
`museum` exige une mini-migration idempotente dans `src/bootstrap.js` (voir §5.2).

---

## 2. Objectif

Trois changements liés :

1. **Gratuité structurée** : remplacer le champ multi-cases imprécis `free_access`
   (`gratuit_26,permanent,premier_dimanche,gratuit_tous`) par un modèle filtrable qui distingue
   le périmètre (collections permanentes seules vs musée entier) et la condition d'âge.
2. **Liste de musées définitive** : le bouton admin « Sync musées (Île-de-France) » **crée**
   aujourd'hui des musées ([src/services/syncMuseums.js](src/services/syncMuseums.js), branche `else` → `Museum.build`).
   Il a déjà tourné en prod (donc la base prod contient des dizaines de musées auto-créés en plus
   des 8 curés). Désormais : **plus jamais de création automatique** - les inconnus deviennent des
   « suggestions » visibles dans l'admin, à traiter manuellement.
3. **Tableau éditorial** : le propriétaire remplira un tableau (CSV) par musée - gratuité exacte,
   liens de scraping (expos / horaires / nocturnes), climatisation. Ce tableau, converti en fichier
   de données versionné dans le repo, devient la source de vérité de la liste des musées.

Décisions déjà validées par le propriétaire :
- Modèle de gratuité : à ma main, critères « vraie catégorisation + tous les cas couverts + filtres qui fonctionnent ».
- Le sync IDF a déjà été utilisé en prod → prévoir le tri des musées auto-créés.
- Source de vérité = fichier repo + bouton admin de réimport (pas d'édition base seule).

---

## 3. Modèle de gratuité retenu (et pourquoi)

| Colonne | Type | Valeurs |
|---|---|---|
| `free_scope` | STRING(30) | `expo_permanente` \| `musee_entier` \| NULL (rien de gratuit) |
| `free_max_age` | INTEGER null | ex. `26` = gratuit pour les moins de 26 ans ; **NULL = gratuit pour tous** |
| `free_notes` | STRING(300) | cas particuliers en texte libre : « résidents UE », « 1er dimanche du mois », « nocturne gratuite le vendredi »… |

**Pourquoi 2 colonnes plutôt que les 6 catégories proposées** : les 6 catégories sont le produit
cartésien de 2 dimensions indépendantes (périmètre × condition). Les stocker séparément donne :
des filtres SQL directs (`WHERE free_scope='musee_entier' AND (free_max_age IS NULL OR free_max_age>=26)`),
l'extensibilité (un musée gratuit -18 ne demande aucune nouvelle catégorie), et zéro ambiguïté.
Les cas non filtrables (1er dimanche, nocturnes gratuites) vont en `free_notes` : on les affiche,
on ne filtre pas dessus - si un filtre devient nécessaire plus tard, on ajoutera une colonne dédiée.

**Migration des valeurs actuelles** (à faire dans la mini-migration, quand `free_scope` est NULL) :
`permanent` → (`expo_permanente`, NULL) · `gratuit_tous` → (`musee_entier`, NULL) ·
`gratuit_26` → (`musee_entier`, 26) · `premier_dimanche` → concaténé dans `free_notes`.
La colonne legacy `free_access` **reste en base** (ignorée par le code) pour vérifier la migration ;
suppression dans un chantier ultérieur.

### Autres colonnes ajoutées à `museum`
`horaires_url` STRING(500) · `nocturnes_url` STRING(500) · `climatise` BOOLEAN null (NULL = inconnu).

---

## 4. État actuel du code (repères pour l'implémentation)

- `src/models/museum.js` - colonnes actuelles : id, slug, museofile_id, name, description, address,
  arrondissement, website, expos_url, free_access, image_url, logo_url, lat, lon.
  Getters : `free_access_list`, `free_labels` (depuis `FREE_ACCESS_LABELS` de `src/models/labels.js`),
  `is_permanent_free` (utilisé par templates + scrape).
- `src/services/syncMuseums.js` - `runSyncMuseums()` : fetch dataset IDF (~50 musées parisiens),
  enrichit les existants (rapprochés par `museofile_id` ou `MANUAL_MATCH`), **crée** les inconnus.
- `src/services/seed.js` - const `MUSEUMS` (8 musées curés) + `seedMuseums()` (upsert par slug,
  appelé par bootstrap seulement si base vide, et par `npm run seed`).
- `src/services/sync.js` - sync expos QFAP : ne crée PAS de musées (rattachement par nom, sinon
  expo « lieu seul »). Ne pas y toucher.
- `scripts/scrape.js` - scraping expos → brouillons ; mappe `price_category` depuis
  `museum.free_access_list` (à adapter). Registre des scrapers : `src/scrapers/index.js`
  (Louvre + 4 musées Paris Musées).
- `src/routes/admin.js` - protégé par `requireAdmin` au niveau routeur ; helpers `clean()`,
  `uniqueSlug()` ; flash + redirect après POST ; formulaires dans `views/admin/*.njk`.
- `src/bootstrap.js` - s'exécute au boot : seed musées si base vide, seed pages statiques
  (idempotent par page), création admin. C'est ici que vivra la mini-migration.
- Base locale : 8 musées (4 → `permanent` : Carnavalet, Petit Palais, MAM, Maison V. Hugo ;
  4 → `gratuit_26` : Louvre, Orsay, Quai Branly, Pompidou).

---

## 5. Implémentation

### 5.1 Modèle & nouvelles tables
- `src/models/museum.js` : ajouter les 6 colonnes (§3). Remplacer `free_labels` par un getter
  `free_label` construit depuis scope/âge (ex. « Collections permanentes gratuites », « Musée
  gratuit pour les -26 ans », suffixe notes séparé). Réécrire `is_permanent_free` :
  `free_scope != null && free_max_age == null` pour le périmètre concerné (garder la sémantique
  actuelle : « accessible gratuitement à tous » - vérifier ses usages avant de changer).
- **Nouveau** `src/models/museumSuggestion.js` : `museofile_id` STRING(20) unique, `name` STRING(200),
  `address` STRING(300), `arrondissement` STRING(20), `website` STRING(500), `lat`/`lon` FLOAT,
  `status` STRING(15) défaut `nouvelle` (`nouvelle` | `ignoree`), tableName `museum_suggestion`.
  Enregistrer + exporter dans `src/models/index.js`. (Table neuve → `sequelize.sync()` suffit.)

### 5.2 Mini-migration (bootstrap)
Dans `src/bootstrap.js`, avant les seeds :
```
const qi = sequelize.getQueryInterface();
const cols = await qi.describeTable("museum");
pour chaque nouvelle colonne absente de cols → qi.addColumn("museum", …)
puis si des musées ont free_scope NULL et free_access non vide → appliquer le mapping §3
```
Idempotent, silencieux si rien à faire, log en une ligne sinon. Compatible SQLite + MariaDB.

### 5.3 Liste définitive
- `src/services/syncMuseums.js` : remplacer la branche création par un upsert de
  `MuseumSuggestion` par `museofile_id` (met à jour les infos d'une suggestion `nouvelle` ;
  **ne réveille pas** une `ignoree`). Retour `{ enriched, suggested }`.
- Routes admin + `src/lib/urls.js` :
  - GET `/admin/suggestions` → `admin.suggestions` - liste des `nouvelle` + section repliée des `ignoree`
  - POST `/admin/suggestions/:id/ignorer` → `admin.suggestion_ignore`
  - POST `/admin/suggestions/:id/creer` → `admin.suggestion_create` - crée le musée depuis la
    suggestion (action manuelle explicite : autorisée), slug via `uniqueSlug`, puis supprime la suggestion
- `views/admin/suggestions.njk` (tableau : nom, adresse, site, actions) ;
  `views/admin/dashboard.njk` : tuile compteur suggestions `nouvelle` + bouton « Suggestions de musées ».
- Adapter le flash du bouton sync : « X musées enrichis, Y nouveaux signalés ».

### 5.4 Tableau éditorial
- **Nouveau** `src/data/museums.js` : la liste éditoriale complète (déplacer `MUSEUMS` depuis
  `services/seed.js`, qui l'importe). Y ajouter les nouveaux champs pour les 8 musées curés
  (valeurs §4 mappées). Ce fichier sera régénéré quand le propriétaire rendra son tableau rempli.
- `src/services/seed.js` : `seedMuseums()` upsert tous les champs par slug (comportement bootstrap
  inchangé : base vide seulement). Nouvelle fonction `reimportMuseums()` : upsert tout + retourne
  `{ updated, created, orphans }` où `orphans` = slugs présents en base mais absents du fichier
  (candidats à suppression **manuelle** via le bouton delete existant de la liste admin - ne
  JAMAIS supprimer automatiquement : suppression musée = cascade sur ses expos).
- Admin : POST `/admin/reimport-musees` → `admin.reimport_museums` - bouton
  « ↻ Réimporter la liste éditoriale » sur le dashboard, rapport en flash (lister les orphelins).
- **Export CSV** : GET `/admin/musees/export.csv` → `admin.museums_csv` - toutes les lignes de la
  table `museum` (donc la prod réelle), colonnes :
  `slug;name;garder;free_scope;free_max_age;free_notes;expos_url;horaires_url;nocturnes_url;climatise;website;address;arrondissement;remarques`
  (`garder` et `remarques` vides, à remplir - non stockées en base).
  `Content-Type: text/csv; charset=utf-8`, BOM UTF-8 pour Excel, séparateur `;` (Excel FR).

### 5.5 Affichage & formulaires
- `views/admin/museum_form.njk` + `handleMuseumForm` (admin.js) : remplacer les cases
  `free_access` par select `free_scope` (3 options), input numérique `free_max_age`
  (vide = pour tous), input `free_notes`, inputs `horaires_url` / `nocturnes_url`,
  select `climatise` (Inconnu/Oui/Non). Ne plus écrire `free_access`.
- `views/museums.njk` + `views/museum_detail.njk` : afficher `free_label` (+ notes en petit) ;
  badge « ❄ Climatisé » si `climatise === true`. Vérifier les usages de `free_labels`/
  `is_permanent_free` dans TOUTES les vues (grep) avant de supprimer l'ancien getter.
- `scripts/scrape.js` : `price_category` = `gratuit_tous` si `free_max_age` NULL,
  sinon `gratuit_26` si `free_max_age >= 26` - depuis les nouveaux champs.

### 5.6 Guide utilisateur
**Nouveau** `docs/SCRAPING.md` - mode d'emploi du tableau, écrit pour un non-développeur :
- sens de chaque colonne + valeurs permises (exactement `expo_permanente` / `musee_entier`, etc.) ;
- où trouver l'info sur le site d'un musée : page « billetterie / tarifs » (gratuité et conditions),
  « infos pratiques / horaires » (horaires_url, souvent la même page pour les nocturnes),
  page « expositions / agenda » (expos_url - l'URL de la LISTE, pas d'une expo) ;
- **des URLs suffisent - inutile de fournir le HTML des pages** : elles seront inspectées au
  moment d'écrire les scrapers ; les sites entièrement en JavaScript seront traités au cas par cas ;
- `remarques` : tout ce qui aide (« les expos sont dans l'onglet Agenda », « le site est lent »…) ;
- workflow complet (§6).

---

## 6. Boucle de travail cible (à documenter dans SCRAPING.md)

1. Déployer → le propriétaire télécharge le CSV depuis l'admin (données prod réelles)
2. Il le remplit dans Excel/Numbers/Google Sheets et le renvoie
3. Conversion en `src/data/museums.js` (+ vérification de chaque URL), commit
4. Bouton admin « Réimporter » → base à jour ; musées `garder=non` supprimés à la main
   depuis la liste admin (jamais automatique)
5. Écriture des scrapers supplémentaires (chantier séparé, hors de ce brief)

---

## 7. Vérification (avant tout commit)

Reproduire la méthode e2e du projet : booter sur une base SQLite jetable
(`SECRET_KEY=... DATABASE_URL=sqlite:/tmp/test.sqlite ADMIN_EMAIL=... ADMIN_PASSWORD=... PORT=39xx node server.js`),
puis tester via curl (session + jeton CSRF extrait du HTML - attention : en
`NODE_ENV=production` sans HTTPS le cookie de session n'est pas posé, tester en mode dev).

1. **Migration** : copier `instance/paname.sqlite`, booter dessus → colonnes ajoutées,
   `permanent` → `expo_permanente`, `gratuit_26` → (`musee_entier`, 26) (vérifier via sqlite3) ;
   rebooter → aucune action (idempotence).
2. **Sync IDF** (API réelle) : `npm run sync-museums` → **0 musée créé**, suggestions créées ;
   relance → pas de doublons ; suggestion passée `ignoree` puis relance → reste `ignoree`.
3. **Admin e2e** : liste suggestions ; ignorer ; créer (→ musée présent, suggestion disparue) ;
   export CSV (ouvrir, vérifier BOM/colonnes/valeurs) ; réimport (rapport orphelins correct).
4. **Public** : /musees et fiche musée affichent les bons libellés ; badge climatisé ;
   aucune régression sur les pages expos.
5. **Scrape** : `npm run scrape` (dry-run) → price_category correcte.
6. `node --check` sur tous les fichiers modifiés ; formulaire musée : POST avec CSRF passe,
   sans CSRF → 403.

Commits : en français, découpés logiquement (modèle+migration / liste définitive+suggestions /
tableau+export+réimport / affichage), sans mention d'IA.

## 8. Déploiement (rappels spécifiques à ce projet)

- Sur le serveur : `git pull origin main` puis **redémarrer via le Manager Infomaniak** (pas de
  commande SSH pour ça). La commande de build est `npm ci --omit=dev` - ne jamais lancer
  `npm install` sur le serveur.
- La migration et la table `museum_suggestion` se créent seules au redémarrage (bootstrap).
- Aucune variable d'environnement nouvelle.
