"use strict";

const { DataTypes } = require("sequelize");
const { FREE_ACCESS_LABELS } = require("./labels");

module.exports = (sequelize) => {
  const Museum = sequelize.define(
    "Museum",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      slug: { type: DataTypes.STRING(160), unique: true, allowNull: false },
      museofile_id: { type: DataTypes.STRING(20), unique: true }, // ID officiel (dataset IDF)
      name: { type: DataTypes.STRING(200), allowNull: false },
      description: { type: DataTypes.TEXT },
      address: { type: DataTypes.STRING(300) },
      arrondissement: { type: DataTypes.STRING(20) },
      website: { type: DataTypes.STRING(500) },
      expos_url: { type: DataTypes.STRING(500) }, // page « expositions en cours » (cible scraping)
      free_access: { type: DataTypes.STRING(120) }, // clés CSV, cf. FREE_ACCESS_LABELS
      image_url: { type: DataTypes.STRING(500) },
      logo_url: { type: DataTypes.STRING(500) },
      lat: { type: DataTypes.FLOAT },
      lon: { type: DataTypes.FLOAT },
    },
    { tableName: "museum", indexes: [{ fields: ["slug"] }] }
  );

  Object.defineProperty(Museum.prototype, "free_access_list", {
    get() {
      return (this.free_access || "").split(",").filter(Boolean);
    },
  });

  Object.defineProperty(Museum.prototype, "free_labels", {
    get() {
      return this.free_access_list
        .filter((k) => k in FREE_ACCESS_LABELS)
        .map((k) => FREE_ACCESS_LABELS[k]);
    },
  });

  // Compat : collections accessibles gratuitement à tous.
  Object.defineProperty(Museum.prototype, "is_permanent_free", {
    get() {
      const keys = this.free_access_list;
      return keys.includes("permanent") || keys.includes("gratuit_tous");
    },
  });

  return Museum;
};
