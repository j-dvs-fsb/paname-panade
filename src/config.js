"use strict";

require("dotenv").config();

const path = require("path");

const BASE_DIR = path.resolve(__dirname, "..");

const config = {
  baseDir: BASE_DIR,
  secretKey: process.env.SECRET_KEY || "dev-change-me-in-production",
  port: parseInt(process.env.PORT, 10) || 3000,
  // Défaut local : SQLite. En prod : DATABASE_URL=mysql://user:pass@host:3306/db
  databaseUrl:
    process.env.DATABASE_URL ||
    "sqlite:" + path.join(BASE_DIR, "instance", "paname.sqlite"),
  sqlLog: (process.env.SQL_LOG || "false").toLowerCase() === "true",
  isProduction: process.env.NODE_ENV === "production",
};

module.exports = config;
