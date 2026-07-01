"use strict";

// Initialisation automatique au démarrage (utile sur hébergement sans accès shell).
// - Seed des musées curés si la base est vide.
// - Création d'un compte admin depuis les variables d'env si aucun utilisateur n'existe.
// Tout est idempotent : ne s'exécute que sur une base vide.

const { Museum, User } = require("./models");
const { seedMuseums } = require("./services/seed");

async function bootstrap() {
  try {
    if ((await Museum.count()) === 0) {
      const { created } = await seedMuseums();
      console.log(`[bootstrap] Seed automatique : ${created} musées créés.`);
    }
  } catch (e) {
    console.error("[bootstrap] Seed automatique échoué :", e.message);
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
