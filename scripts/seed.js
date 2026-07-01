"use strict";

// Seed : musées gratuits en permanence à Paris (liste éditoriale curée).
// Usage : npm run seed   (ou node scripts/seed.js)

const { sequelize } = require("../src/models");
const { MUSEUMS, seedMuseums } = require("../src/services/seed");

async function run() {
  await sequelize.authenticate();
  await sequelize.sync();
  const { created, total } = await seedMuseums();
  console.log(`✓ ${MUSEUMS.length} musées traités (${created} créés).`);
  console.log(`  Total musées en base : ${total}`);
  await sequelize.close();
}

run().catch((e) => {
  console.error("✗ Seed échoué :", e);
  process.exit(1);
});
