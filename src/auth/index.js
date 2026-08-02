"use strict";

// Better Auth : email/mot de passe, connexion Google, sessions.
//
// Le paquet est distribué uniquement en ESM ; le projet est en CommonJS. On
// l'importe donc dynamiquement, dans une initialisation asynchrone appelée au
// démarrage. `require()` d'un module ESM ne fonctionne qu'à partir de Node
// 20.19 / 22.12 et la version exacte de l'hébergeur n'est pas garantie -
// `import()` fonctionne partout.
//
// Choix de schéma (cf. src/models/authTables.js) :
// - identifiants entiers auto-incrémentés, pour rester compatibles avec la
//   table `user` historique et les clés étrangères de favorite/visit/credential ;
// - la table `user` est réutilisée telle quelle, avec un mapping de champs
//   (`name` -> `prenom`, dates en snake_case) et deux champs supplémentaires
//   (`date_naissance`, `is_admin`) ;
// - les mots de passe restent hachés en bcrypt : la fonction de hachage et de
//   vérification est branchée sur bcryptjs, donc les comptes créés avant la
//   migration continuent de se connecter sans réinitialisation.

const bcrypt = require("bcryptjs");

const config = require("./../config");

let authPromise = null;

function googleCredentials() {
  const clientId = (process.env.GOOGLE_CLIENT_ID || "").trim();
  const clientSecret = (process.env.GOOGLE_CLIENT_SECRET || "").trim();
  return clientId && clientSecret ? { clientId, clientSecret } : null;
}

function isGoogleEnabled() {
  return !!googleCredentials();
}

// Origine publique utilisée pour les redirections OAuth et la vérification
// d'origine des requêtes.
function baseUrl() {
  return config.siteUrl || `http://localhost:${config.port}`;
}

// Better Auth parle à la base par Kysely, pas par Sequelize : il lui faut un
// pilote à lui.
//
// En production, le pool mysql2 déjà présent dans les dépendances. En
// développement, `node:sqlite`, intégré à Node - surtout pas better-sqlite3 :
// Better Auth le déclare en dépendance de pair *optionnelle*, ce qui suffit à
// npm pour l'installer même avec `npm ci --omit=dev` (vérifié), et il faudrait
// alors compiler un module natif sur le mutualisé.
function buildDatabase() {
  if (config.db || !config.databaseUrl.startsWith("sqlite:")) {
    const mysql = require("mysql2/promise");
    if (config.db) {
      return mysql.createPool({
        host: config.db.host,
        port: config.db.port,
        user: config.db.username,
        password: config.db.password,
        database: config.db.database,
        timezone: "Z",
      });
    }
    return mysql.createPool(config.databaseUrl);
  }

  const { DatabaseSync } = require("node:sqlite");
  return new DatabaseSync(config.databaseUrl.slice("sqlite:".length));
}

// Relying Party WebAuthn. Le greffon est configuré une fois au démarrage (et
// non par requête comme l'ancienne implémentation) : en production, le domaine
// doit donc être figé par SITE_URL ou WEBAUTHN_RP_ID.
function webauthnConfig() {
  const origin = process.env.WEBAUTHN_ORIGIN || baseUrl();
  let host = "localhost";
  try {
    host = new URL(origin).hostname;
  } catch (e) {
    /* origine illisible : on garde localhost */
  }
  const rpID = process.env.WEBAUTHN_RP_ID || host;

  // Une passkey est liée au domaine qui l'a créée. Si la production démarrait
  // sur « localhost » faute de SITE_URL, aucune passkey ne fonctionnerait, et
  // rien ne le signalerait avant qu'un visiteur n'essaie.
  if (config.isProduction && rpID === "localhost") {
    console.warn(
      "[auth] SITE_URL et WEBAUTHN_RP_ID sont absents : les passkeys seront " +
        "rattachées à « localhost » et ne fonctionneront pas en production."
    );
  }

  return { rpID, rpName: "Paname Panade", origin };
}

async function build() {
  const { betterAuth } = await import("better-auth");
  const { passkey } = await import("@better-auth/passkey");

  const google = googleCredentials();
  const webauthn = webauthnConfig();

  return betterAuth({
    appName: "Paname Panade",
    secret: config.secretKey,
    baseURL: baseUrl(),
    basePath: "/api/auth",
    database: buildDatabase(),
    trustedOrigins: [baseUrl()],

    advanced: {
      // Identifiants entiers laissés à la base (AUTO_INCREMENT).
      database: { generateId: "serial" },
      useSecureCookies: config.isProduction,
      cookiePrefix: "paname",
      defaultCookieAttributes: { sameSite: "lax", httpOnly: true },
    },

    emailAndPassword: {
      enabled: true,
      minPasswordLength: 8,
      autoSignIn: true,
      // Même algorithme qu'avant la migration : les hachages déjà en base
      // restent valides, personne n'a à réinitialiser son mot de passe.
      password: {
        hash: async (password) => bcrypt.hashSync(password, 12),
        verify: async ({ hash, password }) => bcrypt.compareSync(password, hash || ""),
      },
    },

    socialProviders: google ? { google } : {},

    user: {
      modelName: "user",
      fields: { name: "prenom", createdAt: "created_at", updatedAt: "updated_at" },
      additionalFields: {
        // Renseignée à l'inscription classique ; demandée après coup lors
        // d'une première connexion Google (cf. /compte/complete).
        date_naissance: { type: "string", required: false, input: true },
        // Jamais modifiable depuis une requête : la promotion admin passe par
        // le back-office ou `npm run make-admin`.
        is_admin: { type: "boolean", required: false, defaultValue: false, input: false },
      },
    },

    session: {
      modelName: "session",
      expiresIn: 30 * 24 * 3600,
      updateAge: 24 * 3600,
      // Évite une lecture en base à chaque page : la session est relue depuis
      // un cookie signé de courte durée.
      cookieCache: { enabled: true, maxAge: 5 * 60 },
    },

    account: { modelName: "account" },
    verification: { modelName: "verification" },

    plugins: [
      passkey({
        rpID: webauthn.rpID,
        rpName: webauthn.rpName,
        origin: webauthn.origin,
        // `residentKey: preferred` laisse l'appareil proposer une passkey
        // découvrable, ce qui permet de se connecter sans saisir son email.
        authenticatorSelection: { residentKey: "preferred", userVerification: "preferred" },
      }),
    ],
  });
}

// Instance unique, construite au premier appel.
function getAuth() {
  if (!authPromise) authPromise = build();
  return authPromise;
}

module.exports = { getAuth, isGoogleEnabled, baseUrl };
