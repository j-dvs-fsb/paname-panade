"use strict";

const crypto = require("crypto");
const path = require("path");
const express = require("express");
const session = require("express-session");
const flash = require("connect-flash");
const helmet = require("helmet");
const SequelizeStore = require("connect-session-sequelize")(session.Store);

const config = require("./config");
const { sequelize } = require("./models");
const nunjucksSetup = require("./nunjucks");
const { loadUser } = require("./middleware/auth");
const { csrfProtection } = require("./middleware/csrf");
const { pageMeta } = require("./lib/seo");

// Pages sans intérêt pour un moteur (ou strictement personnelles) : elles sont
// déjà exclues par robots.txt, la balise meta est la ceinture et les bretelles.
const PRIVATE_PATHS = /^\/(admin|compte|profil|connexion|inscription|deconnexion|au-hasard)/;

function createApp() {
  const app = express();
  app.set("trust proxy", 1); // derrière le reverse-proxy Infomaniak (HTTPS)

  // Nonce CSP par requête : seuls nos <script nonce=…> inline sont exécutés.
  app.use((req, res, next) => {
    res.locals.csp_nonce = crypto.randomBytes(16).toString("base64");
    next();
  });

  // En-têtes de sécurité (CSP, no-sniff, frame-ancestors, HSTS en prod…).
  app.use(
    helmet({
      contentSecurityPolicy: {
        directives: {
          defaultSrc: ["'self'"],
          scriptSrc: [
            "'self'",
            (req, res) => `'nonce-${res.locals.csp_nonce}'`,
            "https://cdn.jsdelivr.net",
            "https://unpkg.com",
          ],
          scriptSrcAttr: ["'none'"],
          styleSrc: ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net", "https://unpkg.com"],
          // Les visuels d'expos et de musées passent désormais par /img, donc
          // par notre origine. Ne restent en externe que les tuiles de carte
          // et les icônes de marqueur livrées avec Leaflet (chargées par sa
          // feuille de style, en chemin relatif au CDN).
          imgSrc: [
            "'self'",
            "data:",
            "blob:",
            "https://*.basemaps.cartocdn.com",
            "https://unpkg.com",
          ],
          connectSrc: ["'self'"],
          fontSrc: ["'self'", "data:", "https://cdn.jsdelivr.net"],
          objectSrc: ["'none'"],
          baseUri: ["'self'"],
          formAction: ["'self'"],
          frameAncestors: ["'self'"],
          upgradeInsecureRequests: config.isProduction ? [] : null,
        },
      },
      hsts: config.isProduction,
      crossOriginEmbedderPolicy: false, // ressources externes (CDN, images) sans en-têtes CORP
    })
  );

  // Templates + statiques
  nunjucksSetup.configure(app);
  app.use("/static", express.static(path.join(config.baseDir, "public")));

  // Corps de formulaire (POST classiques) + JSON (endpoints passkeys)
  app.use(express.urlencoded({ extended: true }));
  app.use(express.json({ limit: "1mb" }));

  // Sessions persistées en base (table `sessions`)
  const store = new SequelizeStore({ db: sequelize, tableName: "sessions" });
  app.use(
    session({
      secret: config.secretKey,
      store,
      resave: false,
      saveUninitialized: false,
      rolling: true,
      cookie: {
        httpOnly: true,
        sameSite: "lax",
        secure: config.isProduction,
        maxAge: 30 * 24 * 3600 * 1000,
      },
    })
  );
  store.sync();

  app.use(csrfProtection);
  app.use(flash());
  app.use(loadUser);

  // Messages flash disponibles dans tous les templates : [{category, message}]
  app.use((req, res, next) => {
    const cats = ["success", "info", "danger", "warning"];
    const flashes = [];
    for (const c of cats) for (const m of req.flash(c)) flashes.push({ category: c, message: m });
    res.locals.flashes = flashes;
    res.locals.request = { args: req.query, path: req.path };
    // Métadonnées SEO par défaut : chaque route les affine, mais aucune page
    // ne doit arriver dans base.njk sans description ni URL canonique.
    res.locals.meta = pageMeta(req, { robots: PRIVATE_PATHS.test(req.path) ? "noindex, nofollow" : null });
    next();
  });

  // Routeurs
  app.use("/", require("./routes/img"));
  app.use("/", require("./routes/main"));
  app.use("/", require("./routes/auth"));
  app.use("/", require("./routes/passkeys"));
  app.use("/admin", require("./routes/admin"));

  // 404
  app.use((req, res) => res.status(404).render("404.njk"));

  return app;
}

module.exports = { createApp };
