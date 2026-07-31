"use strict";

const { DataTypes } = require("sequelize");
const { PRICE_LABELS, RESERVATION_LABELS } = require("./labels");
const { formatFrDate, todayIso } = require("../lib/dates");
const { cleanValue, safeUrl } = require("../lib/values");

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
    return safeUrl(this.image_url);
  });

  // --- Champs d'affichage : jamais de valeur vide ni de lien mort ---
  // Chaque getter renvoie null quand l'info manque ; les templates testent la
  // valeur et masquent la ligne ou le bouton (au lieu d'afficher « None »).

  // Adresse sur une ligne. Le code postal n'est ajouté que s'il est exploitable,
  // et « Paris » que s'il n'y figure pas déjà (les adresses scrapées sont
  // souvent complètes : « Rue de Rivoli, 75001 Paris »).
  def("address_line", function () {
    const parts = [cleanValue(this.address), cleanValue(this.postal_code)].filter(Boolean);
    if (!parts.length) return null;
    const line = parts.join(", ");
    return /paris/i.test(line) ? line : `${line} Paris`;
  });

  // Horaires de l'expo, à défaut ceux du musée rattaché (s'il est chargé).
  def("schedule_text", function () {
    const own = cleanValue(this.schedule);
    if (own) return own;
    return this.museum ? cleanValue(this.museum.horaires) : null;
  });

  // Vrai quand les horaires affichés proviennent du musée : la fiche le précise.
  def("schedule_from_museum", function () {
    return !cleanValue(this.schedule) && !!(this.museum && cleanValue(this.museum.horaires));
  });

  // Page « horaires / infos pratiques » du musée, quand elle est renseignée.
  def("schedule_url", function () {
    return this.museum ? safeUrl(this.museum.horaires_url) : null;
  });

  // Billetterie : réservation de l'expo, à défaut le site officiel du musée.
  // Renvoie null s'il n'y a rien de valide — mieux vaut aucun bouton qu'un mort.
  def("ticket", function () {
    const own = safeUrl(this.reservation_url);
    if (own) {
      return {
        url: own,
        label: this.reservation === "obligatoire" ? "Réserver" : "Billetterie",
        from_museum: false,
      };
    }
    const site = this.museum ? safeUrl(this.museum.website) : null;
    if (site) return { url: site, label: "Site officiel du musée", from_museum: true };
    return null;
  });

  // Page de l'exposition chez la source (musée, Que Faire à Paris…).
  def("official_url", function () {
    return safeUrl(this.url);
  });

  def("venue_label", function () {
    return cleanValue(this.venue_name);
  });

  def("description_text", function () {
    return cleanValue(this.description);
  });

  // Phrase éditoriale propre au site : les fiches reprennent toutes la même
  // description que le jeu de données de la Ville de Paris, ce qui les rend
  // dupliquées aux yeux des moteurs. Cette ligne dit ce qu'on apporte en plus
  // — la condition de gratuité — et varie selon l'expo.
  def("editorial_note", function () {
    const where = this.museum ? this.museum.name : this.venue_label;
    const lieu = where ? ` à ${where}` : " à Paris";
    if (this.price_category === "gratuit_26") {
      return `Exposition gratuite pour les moins de 26 ans${lieu} : entrée libre sur présentation d'une pièce d'identité, plein tarif au-delà.`;
    }
    if (this.price_category === "reduit_26") {
      return `Exposition à tarif réduit pour les moins de 26 ans${lieu}.`;
    }
    return `Exposition gratuite pour tout le monde${lieu}, sans condition d'âge ni de résidence.`;
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
      // Séance d'un seul jour : « Du X au X » n'apporte rien.
      if (String(this.date_start).slice(0, 10) === String(this.date_end).slice(0, 10)) {
        return `Le ${formatFrDate(this.date_start)}`;
      }
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
