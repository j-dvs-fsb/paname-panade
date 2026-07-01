"use strict";

const { DataTypes } = require("sequelize");

module.exports = (sequelize) => {
  return sequelize.define(
    "Visit",
    {
      id: { type: DataTypes.INTEGER, primaryKey: true, autoIncrement: true },
      user_id: { type: DataTypes.INTEGER, allowNull: false },
      exposition_id: { type: DataTypes.INTEGER, allowNull: false },
      rating: { type: DataTypes.INTEGER }, // 1..5
      comment: { type: DataTypes.TEXT },
      visited_at: { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
    },
    {
      tableName: "visit",
      indexes: [{ unique: true, fields: ["user_id", "exposition_id"], name: "uq_visit" }],
    }
  );
};
