"use strict";

const { DataTypes } = require("sequelize");

// Journal des exports reçus du collecteur (POST /api/import). Garde le fichier
// lui-même : c'est la version précédente que le contrat demande de conserver,
// et ce qui permet de rejouer ou d'examiner un import après coup.
module.exports = (sequelize) =>
  sequelize.define(
    "CollectorImport",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      empreinte: { type: DataTypes.STRING(64), unique: true, allowNull: false },
      genere_le: { type: DataTypes.STRING(25), allowNull: false },
      recu_le: { type: DataTypes.DATE, allowNull: false },
      nb_lieux: { type: DataTypes.INTEGER, allowNull: false },
      nb_expositions: { type: DataTypes.INTEGER, allowNull: false },
      bilan: { type: DataTypes.TEXT }, // JSON : ce que l'import a changé sur le site
      contenu: { type: DataTypes.TEXT("long"), allowNull: false }, // l'export tel que reçu
    },
    { tableName: "collector_import" }
  );
