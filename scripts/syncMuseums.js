"use strict";

// Sync des musées parisiens (dataset officiel Île-de-France).
// Usage : npm run sync-museums

const { sequelize } = require("../src/models");
const { runSyncMuseums } = require("../src/services/syncMuseums");

async function run() {
  await sequelize.authenticate();
  await sequelize.sync();
  console.log("→ Requête API Liste des musées franciliens (Paris)…");
  const { created, enriched, total } = await runSyncMuseums();
  console.log(`✓ Sync terminée : ${created} créés, ${enriched} enrichis.`);
  console.log(`  Total musées en base : ${total}`);
  await sequelize.close();
}

run().catch((e) => {
  console.error("✗ Sync musées échouée :", e);
  process.exit(1);
});
