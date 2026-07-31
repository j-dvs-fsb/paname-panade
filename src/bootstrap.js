"use strict";

// Initialisation automatique au démarrage (utile sur hébergement sans accès shell).
// - Mini-migrations de schéma et de données (sync() ne fait pas d'ALTER).
// - Seed des musées curés si la base est vide.
// - Création d'un compte admin depuis les variables d'env si aucun utilisateur n'existe.
// Tout est idempotent : ne s'exécute que sur une base vide.

const { Museum, User, Page } = require("./models");
const { runMigrations } = require("./services/migrate");
const { seedMuseums } = require("./services/seed");
const { seedPages } = require("./services/defaultPages");

async function bootstrap() {
  await runMigrations();

  try {
    if ((await Museum.count()) === 0) {
      const { created } = await seedMuseums();
      console.log(`[bootstrap] Seed automatique : ${created} musées créés.`);
    }
  } catch (e) {
    console.error("[bootstrap] Seed automatique échoué :", e.message);
  }

  try {
    const { created } = await seedPages(Page);
    if (created) console.log(`[bootstrap] Pages statiques créées : ${created}.`);
  } catch (e) {
    console.error("[bootstrap] Seed des pages échoué :", e.message);
  }

  const email = (process.env.ADMIN_EMAIL || "").trim().toLowerCase();
  const password = process.env.ADMIN_PASSWORD || "";
  if (email && password) {
    try {
      if ((await User.count()) === 0) {
        const user = User.build({
          email,
          prenom: process.env.ADMIN_PRENOM || "Admin",
          date_naissance: "2000-01-01",
          is_admin: true,
        });
        user.setPassword(password);
        await user.save();
        console.log(`[bootstrap] Compte admin créé : ${email}`);
      }
    } catch (e) {
      console.error("[bootstrap] Création admin échouée :", e.message);
    }
  }
}

module.exports = { bootstrap };
