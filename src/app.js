"use strict";

const path = require("path");
const express = require("express");
const session = require("express-session");
const flash = require("connect-flash");
const SequelizeStore = require("connect-session-sequelize")(session.Store);

const config = require("./config");
const { sequelize } = require("./models");
const nunjucksSetup = require("./nunjucks");
const { loadUser } = require("./middleware/auth");

function createApp() {
  const app = express();
  app.set("trust proxy", 1); // derrière le reverse-proxy Infomaniak (HTTPS)

  // Templates + statiques
  nunjucksSetup.configure(app);
  app.use("/static", express.static(path.join(config.baseDir, "public")));

  // Corps de formulaire (POST classiques)
  app.use(express.urlencoded({ extended: true }));

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

  app.use(flash());
  app.use(loadUser);

  // Messages flash disponibles dans tous les templates : [{category, message}]
  app.use((req, res, next) => {
    const cats = ["success", "info", "danger", "warning"];
    const flashes = [];
    for (const c of cats) for (const m of req.flash(c)) flashes.push({ category: c, message: m });
    res.locals.flashes = flashes;
    res.locals.request = { args: req.query, path: req.path };
    next();
  });

  // Routeurs
  app.use("/", require("./routes/main"));
  app.use("/", require("./routes/auth"));
  app.use("/admin", require("./routes/admin"));

  // 404
  app.use((req, res) => res.status(404).render("404.njk"));

  return app;
}

module.exports = { createApp };
