"use strict";

const fs = require("fs");
const path = require("path");
const { Sequelize } = require("sequelize");

const config = require("./config");

// Construit une instance Sequelize à partir de DATABASE_URL.
// Supporte deux dialectes : sqlite (local) et mysql/mariadb (prod Infomaniak).
function build() {
  const common = {
    logging: config.sqlLog ? console.log : false,
    define: { underscored: false, timestamps: false },
  };

  // Variables DB séparées (mot de passe brut, sans encodage d'URL).
  if (config.db) {
    return new Sequelize(config.db.database, config.db.username, config.db.password, {
      host: config.db.host,
      port: config.db.port,
      dialect: "mysql",
      dialectOptions: { charset: "utf8mb4" },
      pool: { max: 5, min: 0, idle: 10000 },
      ...common,
    });
  }

  const url = config.databaseUrl;

  if (url.startsWith("sqlite:")) {
    const storage = url.slice("sqlite:".length);
    fs.mkdirSync(path.dirname(storage), { recursive: true });
    return new Sequelize({ dialect: "sqlite", storage, ...common });
  }

  // mysql:// ou mariadb:// -> dialecte mysql (driver mysql2)
  return new Sequelize(url, {
    dialect: "mysql",
    dialectOptions: { charset: "utf8mb4" },
    pool: { max: 5, min: 0, idle: 10000 },
    ...common,
  });
}

const sequelize = build();

module.exports = { sequelize, Sequelize };
