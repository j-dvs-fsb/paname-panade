"use strict";

const { DataTypes } = require("sequelize");

// Clé d'accès (passkey / WebAuthn) rattachée à un utilisateur.
module.exports = (sequelize) => {
  return sequelize.define(
    "Credential",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      user_id: { type: DataTypes.INTEGER, allowNull: false },
      credential_id: { type: DataTypes.STRING(255), allowNull: false, unique: true }, // base64url
      public_key: { type: DataTypes.TEXT, allowNull: false }, // base64url de la clé publique
      counter: { type: DataTypes.BIGINT, allowNull: false, defaultValue: 0 },
      transports: { type: DataTypes.STRING(120) }, // CSV : internal,usb,ble,nfc…
      label: { type: DataTypes.STRING(120) },
      created_at: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
    },
    { tableName: "credential", indexes: [{ fields: ["credential_id"] }] }
  );
};
