"use strict";

const { sequelize } = require("../db");

const User = require("./user")(sequelize);
const Museum = require("./museum")(sequelize);
const Exposition = require("./exposition")(sequelize);
const Favorite = require("./favorite")(sequelize);
const Visit = require("./visit")(sequelize);
const Credential = require("./credential")(sequelize);
const Page = require("./page")(sequelize);
const Report = require("./report")(sequelize);
const Passkey = require("./passkey")(sequelize);

const {
  defineAuthSession,
  defineAuthAccount,
  defineAuthVerification,
} = require("./authTables");

const AuthSession = defineAuthSession(sequelize);
const AuthAccount = defineAuthAccount(sequelize);
const AuthVerification = defineAuthVerification(sequelize);

// --- Associations (alias = noms des backref SQLAlchemy, pour parité des templates) ---
Museum.hasMany(Exposition, { as: "expositions", foreignKey: "museum_id", onDelete: "CASCADE" });
Exposition.belongsTo(Museum, { as: "museum", foreignKey: "museum_id" });

Exposition.hasMany(Favorite, { as: "favorites", foreignKey: "exposition_id", onDelete: "CASCADE" });
Favorite.belongsTo(Exposition, { as: "exposition", foreignKey: "exposition_id" });

Exposition.hasMany(Visit, { as: "visits", foreignKey: "exposition_id", onDelete: "CASCADE" });
Visit.belongsTo(Exposition, { as: "exposition", foreignKey: "exposition_id" });

User.hasMany(Favorite, { as: "favorites", foreignKey: "user_id", onDelete: "CASCADE" });
Favorite.belongsTo(User, { as: "user", foreignKey: "user_id" });

User.hasMany(Visit, { as: "visits", foreignKey: "user_id", onDelete: "CASCADE" });
Visit.belongsTo(User, { as: "user", foreignKey: "user_id" });

User.hasMany(Credential, { as: "credentials", foreignKey: "user_id", onDelete: "CASCADE" });
Credential.belongsTo(User, { as: "user", foreignKey: "user_id" });

User.hasMany(Passkey, { as: "passkeys", foreignKey: "userId", onDelete: "CASCADE" });
Passkey.belongsTo(User, { as: "user", foreignKey: "userId" });

// Un signalement pointe une expo (ou rien, pour une suggestion libre). La fiche
// peut disparaître avant le traitement : le signalement reste, sans rattachement.
Exposition.hasMany(Report, { as: "reports", foreignKey: "exposition_id", onDelete: "SET NULL" });
Report.belongsTo(Exposition, { as: "exposition", foreignKey: "exposition_id" });

const {
  FREE_ACCESS_LABELS,
  PRICE_LABELS,
  RESERVATION_LABELS,
  REPORT_PROBLEM_LABELS,
} = require("./labels");

module.exports = {
  sequelize,
  User,
  Museum,
  Exposition,
  Favorite,
  Visit,
  Credential,
  Page,
  Report,
  Passkey,
  AuthSession,
  AuthAccount,
  AuthVerification,
  FREE_ACCESS_LABELS,
  PRICE_LABELS,
  RESERVATION_LABELS,
  REPORT_PROBLEM_LABELS,
};
