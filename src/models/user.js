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
      password_hash: { type: DataTypes.STRING(255), allowNull: false },
      prenom: { type: DataTypes.STRING(80), allowNull: false },
      date_naissance: { type: DataTypes.DATEONLY, allowNull: false },
      is_admin: { type: DataTypes.BOOLEAN, allowNull: false, defaultValue: false },
      created_at: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
    },
    { tableName: "user", indexes: [{ fields: ["email"] }] }
  );

  User.prototype.setPassword = function (password) {
    this.password_hash = bcrypt.hashSync(password, 10);
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
