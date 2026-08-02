"use strict";

// Tables de Better Auth (sessions, comptes liés, jetons de vérification).
//
// Better Auth parle à la base via Kysely, pas via Sequelize, et son CLI de
// migration n'est pas jouable sur l'hébergement mutualisé. On déclare donc ces
// tables ici : `sequelize.sync()` les crée au démarrage, sur SQLite comme sur
// MariaDB, et Better Auth n'a plus qu'à lire et écrire dedans.
//
// ⚠ Les noms de colonnes sont ceux qu'attend Better Auth (camelCase) : ne pas
// les renommer sans ajouter le mapping correspondant dans src/auth/index.js.
// Les identifiants sont des entiers auto-incrémentés (`generateId: "serial"`),
// pour rester cohérents avec la table `user` historique et ses clés étrangères.

const { DataTypes } = require("sequelize");

function defineAuthSession(sequelize) {
  return sequelize.define(
    "AuthSession",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      token: { type: DataTypes.STRING(255), allowNull: false, unique: true },
      userId: { type: DataTypes.INTEGER, allowNull: false },
      expiresAt: { type: DataTypes.DATE, allowNull: false },
      ipAddress: { type: DataTypes.STRING(64) },
      userAgent: { type: DataTypes.STRING(512) },
      createdAt: { type: DataTypes.DATE, allowNull: false, defaultValue: DataTypes.NOW },
      updatedAt: { type: DataTypes.DATE, allowNull: false, defaultValue: DataTypes.NOW },
    },
    { tableName: "session", indexes: [{ fields: ["userId"] }] }
  );
}

function defineAuthAccount(sequelize) {
  return sequelize.define(
    "AuthAccount",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      // Identifiant chez le fournisseur ; pour un compte mot de passe, l'id local.
      accountId: { type: DataTypes.STRING(255), allowNull: false },
      providerId: { type: DataTypes.STRING(64), allowNull: false }, // "credential" | "google"
      userId: { type: DataTypes.INTEGER, allowNull: false },
      accessToken: { type: DataTypes.TEXT },
      refreshToken: { type: DataTypes.TEXT },
      idToken: { type: DataTypes.TEXT },
      accessTokenExpiresAt: { type: DataTypes.DATE },
      refreshTokenExpiresAt: { type: DataTypes.DATE },
      scope: { type: DataTypes.STRING(255) },
      password: { type: DataTypes.STRING(255) }, // hachage bcrypt, comptes email/mot de passe
      createdAt: { type: DataTypes.DATE, allowNull: false, defaultValue: DataTypes.NOW },
      updatedAt: { type: DataTypes.DATE, allowNull: false, defaultValue: DataTypes.NOW },
    },
    { tableName: "account", indexes: [{ fields: ["userId"] }, { fields: ["providerId", "accountId"] }] }
  );
}

function defineAuthVerification(sequelize) {
  return sequelize.define(
    "AuthVerification",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      identifier: { type: DataTypes.STRING(255), allowNull: false },
      value: { type: DataTypes.TEXT, allowNull: false },
      expiresAt: { type: DataTypes.DATE, allowNull: false },
      createdAt: { type: DataTypes.DATE, allowNull: false, defaultValue: DataTypes.NOW },
      updatedAt: { type: DataTypes.DATE, allowNull: false, defaultValue: DataTypes.NOW },
    },
    { tableName: "verification", indexes: [{ fields: ["identifier"] }] }
  );
}

module.exports = { defineAuthSession, defineAuthAccount, defineAuthVerification };
