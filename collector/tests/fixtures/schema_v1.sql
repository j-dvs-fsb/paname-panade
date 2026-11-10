-- Schéma v1 du collecteur : un seul fichier SQLite, sauvegarde = copie du fichier.
--
-- Les listes fermées (CHECK ... IN) sont aussi déclarées dans models.py ;
-- tests/test_schema.py vérifie qu'elles concordent.
-- Les dates sont du texte ISO (AAAA-MM-JJ), les heures du texte HH:MM,
-- les booléens des entiers 0/1. Aucune colonne ne contient de chaîne vide :
-- une valeur absente est NULL (invariant 2 du brief).

CREATE TABLE familles (
    id                  TEXT PRIMARY KEY,
    libelle             TEXT NOT NULL,
    -- Texte brut du classeur. Le vocabulaire exploitable par le moteur de
    -- gratuité est fixé à l'étape 7 ; d'ici là, rien ne doit l'interpréter.
    gratuite_permanent  TEXT,
    gratuite_temporaire TEXT,
    age_max             INTEGER CHECK (age_max IS NULL OR age_max > 0),
    conditions          TEXT,
    source              TEXT
);

CREATE TABLE lieux (
    id                     TEXT PRIMARY KEY,
    nom                    TEXT NOT NULL,
    famille_id             TEXT NOT NULL REFERENCES familles(id),
    -- 'a_confirmer' : le rattachement à la famille est lui-même incertain,
    -- la règle héritée ne doit pas être appliquée telle quelle.
    confiance_famille      TEXT NOT NULL CHECK (confiance_famille IN ('sur', 'a_confirmer')),
    tier                   TEXT CHECK (tier IN ('T0', 'T1', 'T2', 'T3', 'T4')),
    statut                 TEXT NOT NULL DEFAULT 'a_verifier'
                           CHECK (statut IN ('a_verifier', 'verifie')),
    expos_url              TEXT CHECK (expos_url    IS NULL OR expos_url    LIKE 'http%://%'),
    tarifs_url             TEXT CHECK (tarifs_url   IS NULL OR tarifs_url   LIKE 'http%://%'),
    horaires_url           TEXT CHECK (horaires_url IS NULL OR horaires_url LIKE 'http%://%'),
    logo_url               TEXT CHECK (logo_url     IS NULL OR logo_url     LIKE 'http%://%'),
    plateforme_billetterie TEXT,
    -- Texte libre du classeur, jamais interprété (« pas de gratuité devinée »).
    -- Prime sur la règle de la famille quand le moteur existera.
    gratuite_override      TEXT,
    notes                  TEXT,
    notes_crawler          TEXT,
    verifie_le             TEXT CHECK (verifie_le IS NULL OR date(verifie_le) IS verifie_le),
    verifie_par            TEXT,
    CHECK (statut <> 'verifie' OR verifie_le IS NOT NULL)
);

CREATE TABLE tarifs (
    id           INTEGER PRIMARY KEY,
    lieu_id      TEXT NOT NULL REFERENCES lieux(id),
    portee       TEXT NOT NULL CHECK (portee IN ('permanent', 'temporaire', 'tout')),
    regime       TEXT NOT NULL CHECK (regime IN ('gratuit', 'reduit', 'abonnement')),
    audience     TEXT NOT NULL CHECK (audience IN (
                     'tous', 'moins_18', 'moins_26', 'moins_26_ue', 'moins_30',
                     'etudiant', 'etudiant_art', 'demandeur_emploi', 'minima_sociaux',
                     'enseignant', 'handicap', 'journaliste', 'demandeur_asile',
                     -- trouvées dans le classeur, absentes du brief
                     'enseignant_arts_visuels', '18_29_ans', 'partenariats')),
    -- NULL = prix inconnu, jamais « gratuit » : un gratuit est un 0 explicite.
    prix         REAL,
    plein_tarif  REAL CHECK (plein_tarif IS NULL OR plein_tarif >= 0),
    recurrence   TEXT NOT NULL CHECK (recurrence <> ''),
    justificatif TEXT,
    source_url   TEXT CHECK (source_url IS NULL OR source_url LIKE 'http%://%'),
    verifie_le   TEXT CHECK (verifie_le IS NULL OR date(verifie_le) IS verifie_le),
    verifie_par  TEXT,
    CHECK ((regime = 'gratuit'  AND COALESCE(prix, -1) = 0)
        OR (regime <> 'gratuit' AND COALESCE(prix, 1) > 0))
);

CREATE TABLE horaires (
    id                  INTEGER PRIMARY KEY,
    lieu_id             TEXT NOT NULL REFERENCES lieux(id),
    jour_num            INTEGER NOT NULL CHECK (jour_num BETWEEN 1 AND 7),
    jour                TEXT NOT NULL CHECK (jour IN (
                            'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')),
    ferme               INTEGER NOT NULL CHECK (ferme IN (0, 1)),
    ouverture           TEXT CHECK (ouverture IS NULL OR time(ouverture) IS ouverture || ':00'),
    fermeture           TEXT CHECK (fermeture IS NULL OR time(fermeture) IS fermeture || ':00'),
    nocturne            INTEGER NOT NULL DEFAULT 0 CHECK (nocturne IN (0, 1)),
    portee              TEXT NOT NULL DEFAULT 'tout'
                        CHECK (portee IN ('permanent', 'temporaire', 'tout')),
    derniere_entree_min INTEGER CHECK (derniere_entree_min IS NULL OR derniere_entree_min >= 0),
    valide_du           TEXT CHECK (valide_du IS NULL OR date(valide_du) IS valide_du),
    valide_au           TEXT CHECK (valide_au IS NULL OR date(valide_au) IS valide_au),
    note                TEXT,
    CHECK ((ferme = 1 AND ouverture IS NULL     AND fermeture IS NULL)
        OR (ferme = 0 AND ouverture IS NOT NULL AND fermeture IS NOT NULL)),
    CHECK (valide_du IS NULL OR valide_au IS NULL OR valide_au >= valide_du)
);

CREATE TABLE fermetures (
    id               INTEGER PRIMARY KEY,
    lieu_id          TEXT NOT NULL REFERENCES lieux(id),
    -- MM-JJ si recurrent_annuel, sinon AAAA-MM-JJ
    "date"           TEXT NOT NULL,
    libelle          TEXT NOT NULL,
    recurrent_annuel INTEGER NOT NULL CHECK (recurrent_annuel IN (0, 1)),
    note             TEXT,
    CHECK ((recurrent_annuel = 1 AND date('2000-' || "date") IS '2000-' || "date")
        OR (recurrent_annuel = 0 AND date("date") IS "date"))
);

CREATE TABLE expositions (
    id                INTEGER PRIMARY KEY,
    lieu_id           TEXT NOT NULL REFERENCES lieux(id),
    titre             TEXT NOT NULL CHECK (titre <> ''),
    portee            TEXT NOT NULL CHECK (portee IN ('permanent', 'temporaire')),
    date_debut        TEXT CHECK (date_debut IS NULL OR date(date_debut) IS date_debut),
    date_fin          TEXT CHECK (date_fin   IS NULL OR date(date_fin)   IS date_fin),
    description       TEXT,
    url               TEXT CHECK (url       IS NULL OR url       LIKE 'http%://%'),
    image_url         TEXT CHECK (image_url IS NULL OR image_url LIKE 'http%://%'),
    -- Calculée, jamais lue sur la page. Format fixé à l'étape 7.
    gratuite_calculee TEXT,
    confiance         REAL CHECK (confiance IS NULL OR confiance BETWEEN 0 AND 1),
    etat              TEXT NOT NULL DEFAULT 'en_revue'
                      CHECK (etat IN ('publie', 'en_revue', 'rejete')),
    hash_source       TEXT,
    vu_le             TEXT CHECK (vu_le IS NULL OR date(vu_le) IS vu_le),
    source            TEXT NOT NULL CHECK (source <> ''),
    CHECK (date_debut IS NULL OR date_fin IS NULL OR date_fin >= date_debut),
    -- Pas de publication sans score de confiance.
    CHECK (etat <> 'publie' OR confiance IS NOT NULL)
);

-- Les valeurs de statut sont fixées à l'étape 4, avec `collect`.
CREATE TABLE runs (
    id            INTEGER PRIMARY KEY,
    lieu_id       TEXT NOT NULL REFERENCES lieux(id),
    demarre_le    TEXT NOT NULL,
    duree_ms      INTEGER CHECK (duree_ms IS NULL OR duree_ms >= 0),
    statut        TEXT NOT NULL,
    items_trouves INTEGER CHECK (items_trouves IS NULL OR items_trouves >= 0),
    erreur        TEXT
);

CREATE INDEX idx_tarifs_lieu      ON tarifs (lieu_id);
CREATE INDEX idx_horaires_lieu    ON horaires (lieu_id);
CREATE INDEX idx_fermetures_lieu  ON fermetures (lieu_id);
CREATE INDEX idx_expositions_lieu ON expositions (lieu_id, etat);
CREATE INDEX idx_runs_lieu        ON runs (lieu_id, demarre_le);

PRAGMA user_version = 1;
