# Panade Collector — brief projet

Logiciel auto-hébergé, **indépendant de paname-panade.fr**. Il collecte,
range et valide les données des musées parisiens, puis pousse chaque matin
un export vers le site.

Le site ne scrape rien. Il ne connaît que l'export.

---

## Pourquoi deux systèmes séparés

Si le collecteur casse, le site continue de tourner avec le dernier export valide.
C'est la seule garantie qui compte. Tout le reste du document découle de là.

```
   ┌─────────────────┐                      ┌──────────────────┐
   │ Panade Collector│   export.json        │ paname-panade.fr │
   │  (chez toi)     │ ───────────────────► │   (en ligne)     │
   │  SQLite         │   tous les matins 7h │                  │
   └─────────────────┘                      └──────────────────┘
```

---

## Stack

- **Python 3.11+** — meilleur écosystème pour la collecte.
- **SQLite**, un seul fichier. 57 lieux et quelques milliers d'expos : largement suffisant.
  Pas de serveur de base à administrer, sauvegarde = copier le fichier.
- **httpx** pour les requêtes, **selectolax** pour lire le HTML (plus léger que BeautifulSoup),
  **pydantic** pour valider.
- **FastAPI + HTML simple** pour l'écran de relecture. Pas de framework front.
- Le navigateur intégré de Claude Code **uniquement en phase de découverte**, jamais en production.

Le site peut être dans n'importe quel langage, ça n'a aucune importance : les deux
systèmes ne se parlent que par un fichier JSON.

---

## Règle numéro un : l'IA ne tourne pas la nuit

C'est la règle structurante du projet. Trois phases distinctes.

**1. Découverte — une fois par musée, avec l'IA.**
Claude Code ouvre la page, comprend sa structure, et **écrit un extracteur** :
un petit module Python déterministe, 30 lignes, qui sait lire cette page.
Il enregistre aussi une copie de la page dans `fixtures/`.

**2. Exploitation — toutes les nuits, sans IA.**
Les extracteurs tournent seuls. **Zéro token.** C'est du code ordinaire.

**3. Réparation — rarement, avec l'IA.**
Quand un extracteur ne renvoie plus rien (le musée a refait son site),
il part dans une file, et on régénère l'extracteur.

L'IA sert à comprendre une structure. Le code sert à récupérer des données.
Un système qui appelle un modèle 57 fois par nuit et un système qui l'appelle
57 fois au total ont un rapport de coût de l'ordre de 1 à 300 sur un an.

**Si une tâche demandée implique d'appeler un modèle en production, dis-le et
propose la version déterministe à la place.**

---

## Politesse réseau et éthique — non négociable

1. **Lire `robots.txt` avant tout.** S'il interdit, le lieu passe en tier T4 et on
   n'y va pas. Le navigateur ne change pas cette réponse, il permet seulement de
   passer outre. On ne passe pas outre.
2. Cas déjà connu : **museedemontmartre.fr interdit les robots**. Tier T4 définitif,
   passer par la newsletter ou `presse@museedemontmartre.fr`.
3. User-Agent identifiable : `PanadeCollector/1.0 (+https://paname-panade.fr/bot)`.
4. Une requête par seconde maximum et par domaine. Collecte de nuit.
5. Jamais de contournement de protection technique (captcha, Cloudflare).
6. Jamais de scraping d'un concurrent ou d'un agrégateur. Source officielle uniquement :
   on a constaté jusqu'à trois tarifs contradictoires pour un même musée selon les agrégateurs,
   dont un périmé depuis des années.

---

## Les tiers de collecte

Avant d'écrire un extracteur, déterminer le tier. On ne descend jamais
sans avoir essayé le niveau au-dessus.

| Tier | Source | Coût |
|---|---|---|
| T0 | API ouverte : Que Faire à Paris, OpenAgenda Île-de-France | nul |
| T1 | Le site expose du structuré : JSON-LD `Event`, RSS, `.ics`, `sitemap.xml` | faible |
| T2 | Billetterie mutualisée — une intégration couvre plusieurs musées | moyen, très rentable |
| T3 | HTML lu par un extracteur dédié | moyen |
| T4 | Manuel : newsletter presse, formulaire de soumission | humain |

**Mutualisations déjà identifiées, à exploiter en priorité :**

- **Réseau Paris Musées** (12 lieux) : les sites partagent le même gabarit Drupal.
  Même structure de menu, mêmes chemins d'images, un `/sitemap` sur chacun.
  **Un seul extracteur couvre les 12.** Attention, le chemin de la page expos varie
  légèrement (`/expositions/exposition-en-cours`, `/expositions/expositions-en-cours`,
  `/visiter/expositions/expositions-en-cours`) : paramétrer, pas dupliquer.
- **Billetteries Tickeasy / Vivaticket** : au moins deux musées déjà repérés,
  même format d'URL `(domaine).tickeasy.com/fr-FR/tarifs`. Un connecteur, N musées.
- **Drupal avec agenda filtrable** : mahJ et IMA exposent un filtre par type
  dans l'URL, ce qui évite d'avoir à trier après coup.

---

## Modèle de données

Sept tables. Le fichier `PP_lieux_v2.xlsx` sert de **seed** : écrire un import
qui le lit et remplit la base au premier lancement.

```sql
familles(id, libelle, gratuite_permanent, gratuite_temporaire, age_max, conditions)

lieux(id, nom, famille_id, tier, statut, expos_url, tarifs_url, horaires_url,
      logo_url, plateforme_billetterie, gratuite_override, notes_crawler,
      verifie_le, verifie_par)

tarifs(id, lieu_id, portee, regime, audience, prix, plein_tarif, recurrence,
       justificatif, source_url, verifie_le, verifie_par)
  portee   : permanent | temporaire | tout
  regime   : gratuit | reduit | abonnement
  audience : tous | moins_18 | moins_26 | moins_26_ue | moins_30 | etudiant
           | etudiant_art | demandeur_emploi | minima_sociaux | enseignant
           | handicap | journaliste | demandeur_asile
  recurrence : toujours | 1er_dimanche | 1er_samedi | nocturne_<jour>
             | apres_16h | <periode datee>

horaires(id, lieu_id, jour_num, jour, ferme, ouverture, fermeture, nocturne,
         portee, derniere_entree_min, valide_du, valide_au, note)

fermetures(id, lieu_id, date, libelle, recurrent_annuel, note)
  date : MM-JJ si recurrent_annuel, sinon AAAA-MM-JJ

expositions(id, lieu_id, titre, portee, date_debut, date_fin, description,
            url, image_url, gratuite_calculee, confiance, etat,
            hash_source, vu_le, source)
  etat : publie | en_revue | rejete

runs(id, lieu_id, demarre_le, duree_ms, statut, items_trouves, erreur)
```

### Invariants, à faire respecter par le code et par les tests

1. **La gratuité n'est jamais lue sur la page d'une expo.** Elle est *calculée* :
   règle du lieu + portée + override éventuel. Aucun modèle ne produit jamais une
   règle de gratuité.
2. Un champ vide ne sort **jamais** dans l'export. Pas de `null`, pas de `/exposition/None`.
3. Une expo sous le seuil de confiance reste en `en_revue` et n'est pas exportée.
4. Un lieu au statut `a_verifier` n'exporte aucune expo.
5. Une donnée vérifiée il y a plus de 120 jours est signalée comme périmée.

### Le piège central

« Collections permanentes gratuites » ne veut pas dire « exposition temporaire gratuite ».
Dans les musées de la Ville de Paris c'est même systématiquement l'inverse.
Deux cas réels à mettre en test :

- **mahJ** : collection gratuite pour les -26 ans UE, mais expo temporaire à 5 €.
- **Musée de la musique** : idem, permanent gratuit, temporaire à 5 €.

Le même musée doit donc apparaître dans le filtre « gratuit -26 » *et* dans
« réduit -26 », selon la portée. C'est la raison d'être de la colonne `portee`.

### Les exceptions existent

Le Palais Galliera et la Crypte archéologique ne suivent pas la règle de leur famille.
Le système de familles reste bon, mais `gratuite_override` doit toujours primer.

---

## Les commandes

```
panade probe <lieu_id>        # classe le lieu en T0..T4, n'écrit rien d'autre
panade discover <lieu_id>     # phase IA : génère l'extracteur + la fixture
panade collect [--lieu X]     # fait tourner les extracteurs. AUCUN appel modèle
panade validate               # schéma, cohérence, dédoublonnage, confiance
panade review                 # ouvre l'écran de relecture local
panade export                 # produit export.json, ne publie pas
panade publish                # vérifie les garde-fous puis pousse vers le site
panade health                 # lieux muets, extracteurs cassés, données périmées
```

### `probe`

Teste dans l'ordre et s'arrête au premier succès : présence dans l'OpenAgenda
Île-de-France → JSON-LD `Event` dans le HTML → `<link rel=alternate>` RSS →
`.ics` → domaine de billetterie connu → `sitemap.xml`.
Sortie JSON `{tier, preuve, url_utile}`. Ne scrape rien, diagnostique.

### `collect`

- Lit `robots.txt` et le respecte.
- Requête conditionnelle (`If-Modified-Since` / `ETag`). Un `304` coûte presque rien :
  c'est l'essentiel du trafic économisé sur 57 musées × 365 nuits.
- Compare un hash du contenu. Identique → on passe, on ne ré-extrait pas.
- Écrit une ligne dans `runs` à chaque passage, succès comme échec.

### `validate`

- Schéma pydantic strict. Une sortie non conforme est **rejetée**, pas rattrapée.
- `date_fin >= date_debut`, dates à moins de 3 ans.
- Dédoublonnage par similarité titre + lieu + dates. C'est ce qui a produit les
  trois `chaillot-experience` sur le site actuel.
- Score de confiance par champ. Sous le seuil → `en_revue`.

---

## La publication, et ses garde-fous

C'est la partie où une erreur se voit en ligne. Elle doit être la plus prudente.

**Format.** Un seul fichier `export.json`, versionné et horodaté, contenant
uniquement les expos en état `publie` et les lieux en statut `verifie`.

**Transport.** POST authentifié par token vers un endpoint du site, ou dépôt git.
Jamais d'écriture directe dans la base du site.

**Atomique.** Le site reçoit l'export entier ou rien. Il garde toujours la version
précédente et bascule seulement quand le nouveau fichier est complet et valide.

**Trois garde-fous avant d'envoyer, qui bloquent la publication :**

1. L'export contient moins de 70 % des expos de la veille → refus + alerte.
   C'est ce qui empêche un bug de scraper de vider le site.
2. Un lieu passe de « a des expos » à « n'en a plus » → refus pour ce lieu seul,
   on garde ses données de la veille.
3. Une gratuité a changé depuis hier sans relecture humaine → l'expo sort de
   l'export et part en `en_revue`.

**Un tarif non vérifié ne s'affiche jamais « gratuit ».** Il s'affiche
« à confirmer sur place », ou il n'apparaît pas.

---

## Planification

```
03:00  collect     requêtes conditionnelles, 1 req/s par domaine
04:00  validate
07:00  publish     uniquement si validate est passé et les garde-fous sont verts
lundi  health      rapport des lieux muets et des données de plus de 120 jours
```

Un lieu silencieux deux nuits de suite déclenche une alerte. Sans ça, un extracteur
cassé peut passer inaperçu des semaines.

---

## Tests

**Fixtures obligatoires** dans `tests/fixtures/`. Toute l'extraction doit être
testable hors ligne. **Interdiction de taper sur un site réel pendant un cycle de
debug** : c'est comme ça qu'on se fait bloquer en développant, et c'est du trafic pur perdu.

Cas limites à couvrir dès le départ, tous rencontrés en vrai :

- Tarifs dans un **PDF** lié en bas de page (Fondation Cartier).
- Tarifs sur un **autre domaine**, celui de la billetterie.
- Images en **chargement différé** : un crawler naïf récupère un fichier vide.
  Lire la balise `<meta og:image>` en premier, elle donne presque toujours une image exploitable.
- Flux RSS **mélangeant** expositions et ateliers pour enfants : filtrer.
- Agenda mélangeant **concerts et expos** (Philharmonie).
- Expo sans **date de fin**, ou avec seulement « jusqu'au 13 décembre ».
- Une **page d'accueil accessible mais une page expos bloquée** sur le même site (MAD).
- Un musée **fermé pour travaux** ou en période de montage.
- Une famille avec une **exception** (Palais Galliera).

---

## Sobriété

Au-delà du principe « pas d'IA la nuit » :

- Ne jamais envoyer une page entière à un modèle, même en phase de découverte.
  Couper le menu, le pied de page et les scripts : une page de musée fait souvent
  300 000 caractères pour 2 000 utiles.
- Préférer Haiku quand un modèle est vraiment nécessaire. Le gros modèle sert
  à la découverte, pas à la lecture d'une grille de tarifs.
- Un musée à la fois, contexte vidé entre chaque. Pas de sous-agents parallèles :
  chacun repart à froid et relit tout.
- Ne pas stocker les images des musées, seulement leur adresse.
- JSON et SQLite, pas de format lourd. L'export doit rester lisible et compressible.

---

## Ordre de construction

1. Le schéma SQLite + l'import du fichier `PP_lieux_v2.xlsx`.
2. `probe`, et le faire tourner sur les 9 lieux déjà vérifiés pour contrôler le résultat.
3. L'extracteur **Paris Musées** en premier : 12 lieux d'un coup, c'est le meilleur rendement.
4. `collect` + `validate` + les fixtures.
5. L'écran de relecture. Objectif : 30 secondes par item.
6. `export` et `publish` avec leurs garde-fous.
7. Le moteur de gratuité, fonction pure testée unitairement, un cas par famille
   plus les cas limites ci-dessus.
8. Les alertes et `health`.

**Après chaque étape, montrer le résultat sur 3 lieux avant de passer aux 57.**

---

## Ce qu'on ne fait pas

- Pas d'extracteur écrit à la main musée par musée quand une mutualisation existe.
- Pas d'appel de modèle en production.
- Pas d'agent qui navigue seul la nuit.
- Pas de gratuité devinée.
- Pas de publication sans score de confiance ni garde-fou.
- Pas de contournement d'un `robots.txt`.
- Pas d'écriture directe dans la base du site.
