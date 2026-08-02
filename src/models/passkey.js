"use strict";

const { DataTypes } = require("sequelize");

// Table du greffon passkey de Better Auth (@better-auth/passkey).
//
// Comme pour session/account/verification, on la déclare en modèle Sequelize
// pour que `sequelize.sync()` la crée : le CLI de migration de Better Auth
// n'est pas jouable sur l'hébergement mutualisé.
//
// ⚠ Les noms de colonnes sont ceux qu'attend le greffon (camelCase). Elle
// remplace l'ancienne table `credential`, dont le contenu est repris par la
// migration de démarrage (cf. services/migrate.js).
module.exports = (sequelize) => {
  return sequelize.define(
    "Passkey",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      name: { type: DataTypes.STRING(120) },
      userId: { type: DataTypes.INTEGER, allowNull: false },
      credentialID: { type: DataTypes.STRING(255), allowNull: false },
      publicKey: { type: DataTypes.TEXT, allowNull: false }, // base64 standard
      counter: { type: DataTypes.INTEGER, allowNull: false, defaultValue: 0 },
      deviceType: { type: DataTypes.STRING(32), allowNull: false, defaultValue: "singleDevice" },
      backedUp: { type: DataTypes.BOOLEAN, allowNull: false, defaultValue: false },
      transports: { type: DataTypes.STRING(120) }, // CSV : internal,usb,ble,nfc…
      aaguid: { type: DataTypes.STRING(64) },
      createdAt: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
    },
    { tableName: "passkey", indexes: [{ fields: ["userId"] }, { fields: ["credentialID"] }] }
  );
};
