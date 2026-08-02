"use strict";

const config = require("./src/config");
const { sequelize } = require("./src/models");
const { createApp } = require("./src/app");
const { bootstrap } = require("./src/bootstrap");
const { sweep } = require("./src/services/imageCache");

async function main() {
  await sequelize.authenticate();
  await sequelize.sync(); // crée les tables si absentes (comme db.create_all())
  await bootstrap(); // migrations + seed musées + admin (si base vide)

  // Purge des images en cache jamais redemandées (sans bloquer le démarrage).
  sweep()
    .then((n) => n && console.log(`[cache images] ${n} fichiers périmés supprimés.`))
    .catch(() => {});

  const app = createApp();
  app.listen(config.port, () => {
    console.log(`Paname Panade - http://localhost:${config.port}`);
  });
}

main().catch((err) => {
  console.error("Échec du démarrage :", err);
  process.exit(1);
});
