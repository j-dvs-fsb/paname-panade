"use strict";

const { DataTypes } = require("sequelize");

// Signalements d'erreur sur une fiche et suggestions d'expositions envoyés par
// les visiteurs. File d'attente traitée depuis le back-office.
//
// Minimisation RGPD : on n'enregistre que le contenu du signalement et son
// horodatage. L'email est facultatif, uniquement si la personne veut une
// réponse ; aucune adresse IP, aucun identifiant de visiteur.
module.exports = (sequelize) => {
  return sequelize.define(
    "Report",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      kind: { type: DataTypes.STRING(20), allowNull: false, defaultValue: "erreur" }, // erreur | suggestion
      exposition_id: { type: DataTypes.INTEGER }, // null pour une suggestion libre
      problem: { type: DataTypes.STRING(30) }, // date | horaire | lien | gratuite | autre
      message: { type: DataTypes.TEXT, allowNull: false },
      email: { type: DataTypes.STRING(255) }, // facultatif
      status: { type: DataTypes.STRING(15), allowNull: false, defaultValue: "nouveau" }, // nouveau | traite
      created_at: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
    },
    { tableName: "report", indexes: [{ fields: ["status"] }, { fields: ["exposition_id"] }] }
  );
};
