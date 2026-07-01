"use strict";

// Donne (ou retire) les droits admin à un utilisateur.
// Usage : npm run make-admin -- <email> [--off]

const { sequelize, User } = require("../src/models");

async function run() {
  const args = process.argv.slice(2);
  const email = (args.find((a) => !a.startsWith("--")) || "").trim().toLowerCase();
  const on = !args.includes("--off");
  if (!email) {
    console.error("Usage : npm run make-admin -- <email> [--off]");
    process.exit(1);
  }

  await sequelize.authenticate();
  await sequelize.sync();
  const user = await User.findOne({ where: { email } });
  if (!user) {
    console.log(`✗ Aucun utilisateur avec l'email « ${email} ».`);
    await sequelize.close();
    return;
  }
  user.is_admin = on;
  await user.save();
  console.log(`✓ ${email} : is_admin = ${on}`);
  await sequelize.close();
}

run().catch((e) => {
  console.error("✗ Échec :", e);
  process.exit(1);
});
