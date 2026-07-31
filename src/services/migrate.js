"use strict";

// Mini-migrations jouées au démarrage, avant les seeds.
//
// `server.js` appelle `sequelize.sync()` SANS `{ alter: true }` : les tables
// absentes sont créées, mais une colonne ajoutée à une table existante ne l'est
// jamais. Toute nouvelle colonne doit donc être déclarée ici en plus du modèle.
//
// Tout est idempotent : rien à faire = aucun log, aucune écriture.

const { DataTypes, Op } = require("sequelize");

const { sequelize, Exposition, Museum } = require("../models");
const { SENTINEL_VALUES } = require("../lib/values");

// Colonnes ajoutées après coup, par table. Y laisser les anciennes entrées :
// elles ne coûtent qu'un describeTable au démarrage et servent aux bases qui
// n'ont pas encore été migrées.
const ADDED_COLUMNS = {
  museum: {
    horaires: { type: DataTypes.STRING(500) },
    horaires_url: { type: DataTypes.STRING(500) },
  },
};

// Colonnes texte susceptibles de contenir la chaîne "None" (cf. lib/values.js).
const SCRUBBED_COLUMNS = {
  exposition: [
    "description", "schedule", "url", "image_url",
    "venue_name", "address", "postal_code", "reservation_url",
  ],
  museum: [
    "description", "address", "arrondissement", "website",
    "expos_url", "image_url", "logo_url", "horaires", "horaires_url",
  ],
};

async function addMissingColumns() {
  const qi = sequelize.getQueryInterface();
  const added = [];
  for (const [table, columns] of Object.entries(ADDED_COLUMNS)) {
    let existing;
    try {
      existing = await qi.describeTable(table);
    } catch (e) {
      continue; // table pas encore créée : sync() s'en charge avec le bon schéma
    }
    for (const [name, spec] of Object.entries(columns)) {
      if (existing[name]) continue;
      await qi.addColumn(table, name, spec);
      added.push(`${table}.${name}`);
    }
  }
  return added;
}

// Remet à NULL les "None" hérités des imports Python. Sans ça, les fiches déjà
// en base continueraient d'afficher « Horaires : None » même une fois le code
// corrigé — et la prod ne se réimporte pas.
async function scrubSentinels() {
  const models = { exposition: Exposition, museum: Museum };
  let total = 0;
  for (const [table, columns] of Object.entries(SCRUBBED_COLUMNS)) {
    const model = models[table];
    for (const column of columns) {
      if (!model.rawAttributes[column]) continue;
      const [count] = await model.update(
        { [column]: null },
        { where: { [column]: { [Op.in]: SENTINEL_VALUES } }, validate: false, hooks: false }
      );
      total += count || 0;
    }
  }
  return total;
}

async function runMigrations() {
  try {
    const added = await addMissingColumns();
    if (added.length) console.log(`[migration] Colonnes ajoutées : ${added.join(", ")}.`);
  } catch (e) {
    console.error("[migration] Ajout de colonnes échoué :", e.message);
  }

  try {
    const scrubbed = await scrubSentinels();
    if (scrubbed) console.log(`[migration] Valeurs « None » nettoyées : ${scrubbed}.`);
  } catch (e) {
    console.error("[migration] Nettoyage des valeurs vides échoué :", e.message);
  }
}

module.exports = { runMigrations, addMissingColumns, scrubSentinels, ADDED_COLUMNS };
