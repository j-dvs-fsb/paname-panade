"use strict";

const path = require("path");

const BASE_DIR = path.resolve(__dirname, "..");

// Chemin explicite : dotenv cherche sinon dans le dossier courant du process,
// qui n'est pas forcément la racine du projet selon la façon dont l'hébergeur
// lance l'application.
require("dotenv").config({ path: path.join(BASE_DIR, ".env") });

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

const isProduction = process.env.NODE_ENV === "production";

// En production, un vrai secret de session est obligatoire (signe les cookies).
if (isProduction && (!process.env.SECRET_KEY || process.env.SECRET_KEY.length < 32)) {
  throw new Error(
    "SECRET_KEY manquante ou trop courte (32 caractères minimum) — " +
      'génère-la avec : node -e "console.log(require(\'crypto\').randomBytes(48).toString(\'base64url\'))"'
  );
}

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
  // Origine publique (https://paname-panade.fr) : fige le domaine des URL
  // canoniques, du sitemap et des balises Open Graph. À défaut, dérivée de la
  // requête — correct tant qu'on n'est servi que par un seul domaine.
  siteUrl: (process.env.SITE_URL || "").trim().replace(/\/+$/, "") || null,
};

module.exports = config;
