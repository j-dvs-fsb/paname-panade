"use strict";

// Sync des expositions « Que Faire à Paris ».
// Usage : npm run sync            (limite 200 par défaut)
//         node scripts/sync.js --limit 500

const { sequelize, Exposition } = require("../src/models");
const { runSync } = require("../src/services/sync");

function parseArgs() {
  const args = process.argv.slice(2);
  const i = args.indexOf("--limit");
  const limit = i >= 0 ? parseInt(args[i + 1], 10) : 200;
  return { limit: Number.isFinite(limit) ? limit : 200 };
}

async function run() {
  await sequelize.authenticate();
  await sequelize.sync();
  const { limit } = parseArgs();
  console.log(`→ Requête API Que Faire à Paris (limit=${limit})…`);
  const { created, updated } = await runSync({ limit });
  const total = await Exposition.count();
  console.log(`✓ Sync terminée : ${created} créées, ${updated} mises à jour.`);
  console.log(`  Total expositions en base : ${total}`);
  await sequelize.close();
}

run().catch((e) => {
  console.error("✗ Sync échouée :", e);
  process.exit(1);
});
