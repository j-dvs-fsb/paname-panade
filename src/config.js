"use strict";

require("dotenv").config();

const path = require("path");

const BASE_DIR = path.resolve(__dirname, "..");

// Variables DB séparées (préférées) : le mot de passe est pris tel quel, sans
// encodage d'URL — pratique quand il contient un caractère spécial (@ : / …).
const dbDiscrete =
  process.env.DB_HOST && process.env.DB_NAME
    ? {
        host: process.env.DB_HOST,
        port: parseInt(process.env.DB_PORT, 10) || 3306,
        database: process.env.DB_NAME,
        username: process.env.DB_USER || "",
        password: process.env.DB_PASSWORD || "",
      }
    : null;

const config = {
  baseDir: BASE_DIR,
  secretKey: process.env.SECRET_KEY || "dev-change-me-in-production",
  port: parseInt(process.env.PORT, 10) || 3000,
  // Priorité : variables DB séparées > DATABASE_URL > SQLite (dev).
  db: dbDiscrete,
  databaseUrl:
    process.env.DATABASE_URL ||
    "sqlite:" + path.join(BASE_DIR, "instance", "paname.sqlite"),
  sqlLog: (process.env.SQL_LOG || "false").toLowerCase() === "true",
  isProduction: process.env.NODE_ENV === "production",
};

module.exports = config;
