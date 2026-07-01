"use strict";

// Importe musées + expositions depuis scripts/import-data.json vers la base
// configurée (MariaDB en prod). REMPLACE le contenu actuel de ces deux tables.
// Migration one-shot de l'ancienne base SQLite Flask -> nouvelle base Node.
// Usage (sur le serveur) : node scripts/importData.js

const fs = require("fs");
const path = require("path");
const { sequelize, Museum, Exposition, Favorite, Visit } = require("../src/models");

async function run() {
  const file = path.join(__dirname, "import-data.json");
  if (!fs.existsSync(file)) {
    console.error("✗ Fichier introuvable :", file);
    process.exit(1);
  }
  const data = JSON.parse(fs.readFileSync(file, "utf-8"));
  const museums = data.museums || [];
  const expositions = data.expositions || [];

  await sequelize.authenticate();
  await sequelize.sync();

  // Vide les tables dans l'ordre des dépendances (FK), puis réinsère avec les IDs.
  await Visit.destroy({ where: {} });
  await Favorite.destroy({ where: {} });
  await Exposition.destroy({ where: {} });
  await Museum.destroy({ where: {} });

  await Museum.bulkCreate(museums, { validate: false });
  await Exposition.bulkCreate(expositions, { validate: false });

  console.log(`✓ Import terminé : ${await Museum.count()} musées, ${await Exposition.count()} expositions.`);
  await sequelize.close();
}

run().catch((e) => {
  console.error("✗ Import échoué :", e);
  process.exit(1);
});
