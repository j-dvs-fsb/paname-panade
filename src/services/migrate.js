"use strict";

// Mini-migrations jouées au démarrage, avant les seeds.
//
// `server.js` appelle `sequelize.sync()` SANS `{ alter: true }` : les tables
// absentes sont créées, mais une colonne ajoutée à une table existante ne l'est
// jamais. Toute nouvelle colonne doit donc être déclarée ici en plus du modèle.
//
// Tout est idempotent : rien à faire = aucun log, aucune écriture.

const { DataTypes, Op } = require("sequelize");

const { sequelize, Exposition, Museum, User, AuthAccount, Credential, Passkey } = require("../models");
const { SENTINEL_VALUES } = require("../lib/values");

// Colonnes ajoutées après coup, par table. Y laisser les anciennes entrées :
// elles ne coûtent qu'un describeTable au démarrage et servent aux bases qui
// n'ont pas encore été migrées.
const ADDED_COLUMNS = {
  museum: {
    horaires: { type: DataTypes.STRING(500) },
    horaires_url: { type: DataTypes.STRING(500) },
  },
  // Champs attendus par Better Auth sur la table `user` historique.
  user: {
    emailVerified: { type: DataTypes.BOOLEAN, allowNull: false, defaultValue: false },
    image: { type: DataTypes.STRING(500) },
    updated_at: { type: DataTypes.DATE },
  },
};

// Contraintes NOT NULL à relâcher : Better Auth insère un utilisateur sans
// mot de passe (connexion Google) et sans date de naissance (demandée juste
// après). Sans ça, la création de compte échouerait en base.
const RELAXED_COLUMNS = [
  ["user", "password_hash", { type: DataTypes.STRING(255), allowNull: true }],
  ["user", "date_naissance", { type: DataTypes.DATEONLY, allowNull: true }],
];

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
// corrigé - et la prod ne se réimporte pas.
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

// Relâche les NOT NULL devenus incompatibles avec Better Auth. `describeTable`
// dit si le travail est déjà fait : sur SQLite, changeColumn reconstruit la
// table, autant ne pas le refaire à chaque démarrage.
async function relaxColumns() {
  const qi = sequelize.getQueryInterface();
  const relaxed = [];
  for (const [table, column, spec] of RELAXED_COLUMNS) {
    let existing;
    try {
      existing = await qi.describeTable(table);
    } catch (e) {
      continue;
    }
    const current = existing[column];
    if (!current || current.allowNull) continue;
    await qi.changeColumn(table, column, spec);
    relaxed.push(`${table}.${column}`);
  }
  return relaxed;
}

// Les mots de passe vivaient dans `user.password_hash` ; Better Auth les lit
// dans `account.password`, sur une ligne de fournisseur "credential". On
// recopie les hachages bcrypt tels quels - le même algorithme est branché côté
// Better Auth, donc les mots de passe existants continuent de fonctionner.
async function backfillCredentialAccounts() {
  const users = await User.findAll({
    where: { password_hash: { [Op.ne]: null } },
    attributes: ["id", "password_hash", "created_at"],
  });
  if (!users.length) return 0;

  const existing = await AuthAccount.findAll({
    where: { providerId: "credential", userId: users.map((u) => u.id) },
    attributes: ["userId"],
  });
  const done = new Set(existing.map((a) => a.userId));

  const rows = users
    .filter((u) => !done.has(u.id))
    .map((u) => ({
      accountId: String(u.id),
      providerId: "credential",
      userId: u.id,
      password: u.password_hash,
      createdAt: u.created_at || new Date(),
      updatedAt: new Date(),
    }));
  if (!rows.length) return 0;
  await AuthAccount.bulkCreate(rows);
  return rows.length;
}

// Les passkeys vivaient dans `credential` (implémentation maison) ; le greffon
// de Better Auth les lit dans `passkey`. Le contenu est repris tel quel, à un
// détail près : la clé publique était encodée en base64url, le greffon la lit
// en base64 standard.
//
// `deviceType` et `backedUp` n'existaient pas : on prend les valeurs les plus
// prudentes. Elles ne servent qu'à l'affichage et à la journalisation, pas à
// la vérification cryptographique : les passkeys déjà enregistrées continuent
// donc de fonctionner.
async function migratePasskeys() {
  const credentials = await Credential.findAll();
  if (!credentials.length) return 0;

  const existing = await Passkey.findAll({ attributes: ["credentialID"] });
  const done = new Set(existing.map((p) => p.credentialID));

  const rows = credentials
    .filter((c) => !done.has(c.credential_id))
    .map((c) => ({
      name: c.label || null,
      userId: c.user_id,
      credentialID: c.credential_id,
      publicKey: Buffer.from(c.public_key, "base64url").toString("base64"),
      counter: Number(c.counter) || 0,
      deviceType: "singleDevice",
      backedUp: false,
      transports: c.transports || null,
      createdAt: c.created_at || new Date(),
    }));
  if (!rows.length) return 0;
  await Passkey.bulkCreate(rows);
  return rows.length;
}

async function runMigrations() {
  try {
    const added = await addMissingColumns();
    if (added.length) console.log(`[migration] Colonnes ajoutées : ${added.join(", ")}.`);
  } catch (e) {
    console.error("[migration] Ajout de colonnes échoué :", e.message);
  }

  try {
    const relaxed = await relaxColumns();
    if (relaxed.length) console.log(`[migration] Colonnes rendues facultatives : ${relaxed.join(", ")}.`);
  } catch (e) {
    console.error("[migration] Assouplissement de colonnes échoué :", e.message);
  }

  try {
    const moved = await backfillCredentialAccounts();
    if (moved) console.log(`[migration] Mots de passe repris par Better Auth : ${moved} comptes.`);
  } catch (e) {
    console.error("[migration] Reprise des mots de passe échouée :", e.message);
  }

  try {
    const moved = await migratePasskeys();
    if (moved) console.log(`[migration] Passkeys reprises par Better Auth : ${moved}.`);
  } catch (e) {
    console.error("[migration] Reprise des passkeys échouée :", e.message);
  }

  try {
    const scrubbed = await scrubSentinels();
    if (scrubbed) console.log(`[migration] Valeurs « None » nettoyées : ${scrubbed}.`);
  } catch (e) {
    console.error("[migration] Nettoyage des valeurs vides échoué :", e.message);
  }
}

module.exports = {
  runMigrations,
  addMissingColumns,
  relaxColumns,
  backfillCredentialAccounts,
  migratePasskeys,
  scrubSentinels,
  ADDED_COLUMNS,
};
