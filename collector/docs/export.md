# Contrat de l'export

Le collecteur et le site ne se parlent que par ce fichier. Le site peut être écrit dans
n'importe quel langage : il lit du JSON et ne scrape rien.

## Réception (ce que le site doit faire)

`POST` de l'export sur un point d'entrée du site, par exemple `/api/import`.

| En-tête | Valeur |
|---|---|
| `Authorization` | `Bearer <jeton>`, jeton long et propre à cet usage |
| `Content-Type` | `application/json` |
| `Idempotency-Key` | l'`empreinte` de l'export : rejouer le même envoi ne change rien |

Le site doit :

1. **refuser sans jeton valide** (401) et ne rien lire d'autre que ce point d'entrée ;
2. **recalculer l'`empreinte`** (voir plus bas) et refuser (422) si elle ne correspond pas : le
   fichier est incomplet ou altéré ;
3. refuser un `version` qu'il ne connaît pas ;
4. **tout ou rien** : valider le fichier entier, le charger à côté (nouvelle table, nouveau
   fichier), puis basculer d'un seul geste. Jamais d'écriture directe dans la base du site
   depuis le collecteur, jamais de fichier à moitié appliqué ;
5. **garder la version précédente** et ne répondre `2xx` qu'une fois la bascule faite. Le
   collecteur ne retient une publication comme réussie que sur un `2xx`.

Si le collecteur ne publie pas un matin (garde-fou, panne), le site continue avec le dernier
export reçu. C'est la seule garantie qui compte.

## Format (`version` 1)

```json
{
  "version": 1,
  "genere_le": "2026-10-30T07:00:00Z",
  "compte": {"lieux": 9, "expositions": 14},
  "empreinte": "sha256 hexadécimal",
  "lieux": [
    {
      "id": "musee-d-art-et-d-histoire-du-judaisme",
      "nom": "Musée d'art et d'histoire du judaïsme",
      "famille": "prive_assoc",
      "logo_url": "https://…", "tarifs_url": "https://…", "horaires_url": "https://…", "expos_url": "https://…",
      "plateforme_billetterie": "mahj.tickeasy.com (Vivaticket)",
      "verifie_le": "2026-09-19",
      "perime": true,
      "tarifs":     [{"portee": "permanent", "regime": "gratuit", "audience": "moins_26_ue", "prix": 0,
                      "plein_tarif": 13, "recurrence": "toujours", "justificatif": "…", "source_url": "https://…",
                      "verifie_le": "2026-09-19", "perime": true}],
      "horaires":   [{"jour_num": 2, "jour": "mardi", "ferme": false, "ouverture": "11:00", "fermeture": "18:00",
                      "nocturne": false, "portee": "tout", "derniere_entree_min": 45}],
      "fermetures": [{"date": "05-01", "libelle": "1er mai", "recurrent_annuel": true}],
      "expositions": [
        {"id": 12, "titre": "…", "portee": "temporaire", "date_debut": "2026-10-14", "date_fin": "2027-02-14",
         "description": "…", "url": "https://…", "image_url": "https://…",
         "gratuite": {"categorie": "reduit_26", "libelle": "Tarif réduit pour les moins de 26 ans",
                      "prix": 5, "plein_tarif": 12, "audience": "moins_26", "justificatif": "…"}}
      ]
    }
  ]
}
```

### Règles qui valent pour tout le fichier

- **Aucun champ vide.** Pas de `null`, pas de chaîne vide, pas de liste vide : une valeur absente
  est une clé absente. Le site ne verra jamais `/exposition/None`.
- Seuls les lieux au statut `verifie` et les expositions `publie` y figurent. Les expositions
  terminées n'y figurent plus.
- `perime: true` signale une donnée vérifiée il y a plus de 120 jours. Elle reste affichable,
  mais le site peut la présenter avec prudence.
- Les dates sont `AAAA-MM-JJ` ; les fermetures annuelles `MM-JJ` ; les heures `HH:MM`.
- Les tarifs non vérifiés ne sont jamais exportés.

### `gratuite.categorie`

La gratuité est **calculée** par le collecteur, jamais lue sur la page d'une exposition. Elle
vise un visiteur de 18 à 25 ans résident de l'UE.

| Valeur | Sens |
|---|---|
| `gratuit_tous` | gratuit pour tout le monde |
| `gratuit_26` | gratuit pour les moins de 26 ans (`audience: moins_26_ue` = résidents UE) |
| `reduit_26` | tarif réduit moins de 26 ans, `prix` et `plein_tarif` quand ils sont connus |
| `payant` | pas de gratuité ni de réduction pour les moins de 26 ans |
| `a_confirmer` | donnée insuffisante ou contradictoire |

**Une gratuité `a_confirmer` ne s'affiche jamais « gratuit ».** Elle s'affiche « à confirmer sur
place » (`libelle`), ou l'exposition n'apparaît pas dans les filtres de gratuité.

`creneaux` (facultatif) liste des tarifs qui ne valent qu'à certains moments (par exemple
gratuit après 16 h avec une carte) : à afficher, pas à confondre avec le tarif de base.

Correspondance avec les catégories actuelles du site : `gratuit_tous`, `gratuit_26` et
`reduit_26` existent déjà telles quelles ; `payant` et `a_confirmer` n'ont pas de catégorie
aujourd'hui.

### `empreinte`

SHA-256 du JSON de l'export **sans la clé `empreinte`**, sérialisé de façon canonique : clés
triées, séparateurs `,` et `:` sans espace, caractères non ASCII non échappés, encodage UTF-8.
En Python : `hashlib.sha256(json.dumps(sans, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()`.

## Côté collecteur

`PANADE_PUBLISH_URL` doit être en `https` (le jeton circule), sauf vers `localhost`. Le jeton
se donne par `PANADE_PUBLISH_TOKEN`, jamais en argument de ligne de commande.
