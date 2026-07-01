"use strict";

const { DataTypes } = require("sequelize");

module.exports = (sequelize) => {
  return sequelize.define(
    "Favorite",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      user_id: { type: DataTypes.INTEGER, allowNull: false },
      exposition_id: { type: DataTypes.INTEGER, allowNull: false },
      created_at: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
    },
    {
      tableName: "favorite",
      indexes: [{ unique: true, fields: ["user_id", "exposition_id"], name: "uq_fav" }],
    }
  );
};
