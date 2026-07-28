"use strict";

const { DataTypes } = require("sequelize");

// Pages statiques éditables depuis le back-office (à propos, mentions
// légales, politique de confidentialité). Le contenu est du HTML saisi par
// un admin et rendu tel quel — la CSP (scripts à nonce uniquement) neutralise
// tout <script> qui y serait injecté.
module.exports = (sequelize) => {
  return sequelize.define(
    "Page",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      slug: { type: DataTypes.STRING(40), unique: true, allowNull: false },
      title: { type: DataTypes.STRING(200), allowNull: false },
      content: { type: DataTypes.TEXT, allowNull: false, defaultValue: "" },
    },
    {
      tableName: "page",
      indexes: [{ fields: ["slug"] }],
    }
  );
};
