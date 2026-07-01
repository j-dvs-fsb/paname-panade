"use strict";

const config = require("./src/config");
const { sequelize } = require("./src/models");
const { createApp } = require("./src/app");

async function main() {
  await sequelize.authenticate();
  await sequelize.sync(); // crée les tables si absentes (comme db.create_all())

  const app = createApp();
  app.listen(config.port, () => {
    console.log(`Paname Panade — http://localhost:${config.port}`);
  });
}

main().catch((err) => {
  console.error("Échec du démarrage :", err);
  process.exit(1);
});
