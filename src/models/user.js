"use strict";

const bcrypt = require("bcryptjs");
const { DataTypes } = require("sequelize");
const { toDate } = require("../lib/dates");

module.exports = (sequelize) => {
  const User = sequelize.define(
    "User",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      email: { type: DataTypes.STRING(255), unique: true, allowNull: false },
      // Legacy : les mots de passe vivent désormais dans `account.password`
      // (Better Auth). La colonne reste le temps de vérifier la migration ;
      // elle est nullable, un compte Google n'en a pas.
      password_hash: { type: DataTypes.STRING(255) },
      prenom: { type: DataTypes.STRING(80), allowNull: false }, // `name` côté Better Auth
      // Nullable : une première connexion Google ne la fournit pas, elle est
      // demandée juste après (cf. /compte/complete).
      date_naissance: { type: DataTypes.DATEONLY },
      is_admin: { type: DataTypes.BOOLEAN, allowNull: false, defaultValue: false },
      // Champs attendus par Better Auth.
      emailVerified: { type: DataTypes.BOOLEAN, allowNull: false, defaultValue: false },
      image: { type: DataTypes.STRING(500) },
      created_at: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
      updated_at: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
    },
    { tableName: "user", indexes: [{ fields: ["email"] }] }
  );

  // Conservés pour le bootstrap (création du compte admin au 1er démarrage,
  // avant que Better Auth ne soit sollicité). Le reste de l'application passe
  // par Better Auth : cf. src/auth/index.js, qui réutilise le même bcrypt pour
  // que les hachages déjà en base restent valables.
  User.prototype.setPassword = function (password) {
    this.password_hash = bcrypt.hashSync(password, 12);
  };
  User.prototype.checkPassword = function (password) {
    return bcrypt.compareSync(password, this.password_hash || "");
  };

  // Toujours vrai pour une vraie instance User (cf. current_user anonyme = objet nu).
  Object.defineProperty(User.prototype, "is_authenticated", { get() { return true; } });

  Object.defineProperty(User.prototype, "birthday_26", {
    get() {
      const d = toDate(this.date_naissance);
      if (!d) return null;
      return new Date(d.getFullYear() + 26, d.getMonth(), d.getDate());
    },
  });

  // Anniversaire fatidique passé. `null` (date de naissance inconnue) vaut
  // « non » : on garde l'affichage par défaut du site plutôt que d'annoncer à
  // tort un plein tarif.
  Object.defineProperty(User.prototype, "is_over_26", {
    get() {
      const days = this.days_until_26;
      return days !== null && days < 0;
    },
  });

  Object.defineProperty(User.prototype, "days_until_26", {
    get() {
      const b = this.birthday_26;
      if (!b) return null;
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      return Math.round((b - today) / 86400000);
    },
  });

  return User;
};
