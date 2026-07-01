"use strict";

const { DataTypes } = require("sequelize");
const { PRICE_LABELS, RESERVATION_LABELS } = require("./labels");
const { formatFrDate, todayIso } = require("../lib/dates");

module.exports = (sequelize) => {
  const Exposition = sequelize.define(
    "Exposition",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      slug: { type: DataTypes.STRING(220), unique: true, allowNull: false },
      title: { type: DataTypes.STRING(300), allowNull: false },
      description: { type: DataTypes.TEXT },
      museum_id: { type: DataTypes.INTEGER },
      date_start: { type: DataTypes.DATEONLY },
      date_end: { type: DataTypes.DATEONLY },
      schedule: { type: DataTypes.STRING(500) }, // horaires en texte libre
      url: { type: DataTypes.STRING(500) },
      image_url: { type: DataTypes.STRING(500) },
      image_local: { type: DataTypes.STRING(300) }, // chemin relatif dans public/ si téléchargée
      // Lieu
      venue_name: { type: DataTypes.STRING(200) },
      address: { type: DataTypes.STRING(300) },
      postal_code: { type: DataTypes.STRING(10) },
      lat: { type: DataTypes.FLOAT },
      lon: { type: DataTypes.FLOAT },
      // Tarif & réservation
      price_type: { type: DataTypes.STRING(50), defaultValue: "gratuit" },
      price_category: { type: DataTypes.STRING(30), defaultValue: "gratuit_tous" },
      reservation: { type: DataTypes.STRING(20), defaultValue: "non_necessaire" },
      reservation_url: { type: DataTypes.STRING(500) },
      source: { type: DataTypes.STRING(80) }, // seed / que-faire-a-paris / scraping / manuel
      external_id: { type: DataTypes.STRING(120) },
      status: { type: DataTypes.STRING(20), allowNull: false, defaultValue: "published" },
    },
    {
      tableName: "exposition",
      indexes: [{ fields: ["slug"] }, { fields: ["external_id"] }],
    }
  );

  const def = (name, get) => Object.defineProperty(Exposition.prototype, name, { get });

  def("price_label", function () {
    return PRICE_LABELS[this.price_category] || "Gratuit pour tous";
  });
  def("reservation_label", function () {
    return RESERVATION_LABELS[this.reservation] || "Sans réservation";
  });

  // URL à afficher : copie locale si présente, sinon l'image distante.
  def("image", function () {
    if (this.image_local) return "/static/" + this.image_local;
    return this.image_url;
  });

  // Coordonnées carte : celles de l'expo, sinon celles du musée (si chargé).
  def("map_lat", function () {
    if (this.lat !== null && this.lat !== undefined) return this.lat;
    return this.museum ? this.museum.lat : null;
  });
  def("map_lon", function () {
    if (this.lon !== null && this.lon !== undefined) return this.lon;
    return this.museum ? this.museum.lon : null;
  });

  def("is_permanent", function () {
    return this.source === "permanent";
  });

  def("date_label", function () {
    if (this.is_permanent && !this.date_start && !this.date_end) return "En permanence";
    if (this.date_start && this.date_end) {
      return `Du ${formatFrDate(this.date_start)} au ${formatFrDate(this.date_end)}`;
    }
    if (this.date_end) return `Jusqu'au ${formatFrDate(this.date_end)}`;
    if (this.date_start) return `À partir du ${formatFrDate(this.date_start)}`;
    return "Dates non communiquées";
  });

  def("is_current", function () {
    if (this.date_end && String(this.date_end).slice(0, 10) < todayIso()) return false;
    return true;
  });

  def("avg_rating", function () {
    const rated = (this.visits || []).map((v) => v.rating).filter(Boolean);
    if (!rated.length) return null;
    return Math.round((rated.reduce((a, b) => a + b, 0) / rated.length) * 10) / 10;
  });
  def("rating_count", function () {
    return (this.visits || []).filter((v) => v.rating).length;
  });

  return Exposition;
};
