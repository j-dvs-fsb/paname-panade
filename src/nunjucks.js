"use strict";

const path = require("path");
const nunjucks = require("nunjucks");

const { urlFor } = require("./lib/urls");
const { formatFrDate } = require("./lib/dates");
const { proxyUrl } = require("./services/imageCache");
const { priceForUser } = require("./lib/pricing");

// Configure Nunjucks sur le dossier views/ et branche le moteur à Express.
function configure(app) {
  const env = nunjucks.configure(path.join(__dirname, "..", "views"), {
    autoescape: true,
    express: app,
    watch: false,
  });

  // Équivalent de url_for(endpoint, **params) côté Jinja/Flask.
  // Nunjucks passe les arguments nommés en dernier objet -> on fusionne.
  env.addGlobal("url_for", function (endpoint, ...rest) {
    let params = {};
    for (const r of rest) {
      if (r && typeof r === "object") params = Object.assign(params, r);
    }
    delete params.__keywords;
    return urlFor(endpoint, params);
  });

  env.addFilter("fr_date", formatFrDate);

  // Passe une image externe par notre proxy (cf. services/imageCache).
  // Renvoie null si la source est inexploitable : au template d'afficher son
  // propre placeholder plutôt qu'un <img> vide.
  env.addGlobal("img_url", function (src) {
    return proxyUrl(src);
  });

  // Tarif réellement applicable au visiteur (cf. lib/pricing). `current_user`
  // est passé explicitement : les globals Nunjucks ne reçoivent pas le contexte.
  env.addGlobal("price_for", function (expo, user) {
    return priceForUser(expo, user);
  });

  // dd/mm/yyyy (remplace value.strftime('%d/%m/%Y') côté Jinja).
  env.addFilter("dmy", function (value) {
    if (!value) return "";
    const d = value instanceof Date ? value : new Date(value);
    if (isNaN(d.getTime())) return "";
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
  });

  // JSON sûr pour l'injection dans une balise <script> (équiv. Jinja tojson).
  env.addFilter("tojson", function (value) {
    return new nunjucks.runtime.SafeString(JSON.stringify(value));
  });

  // Équivalents Jinja absents de Nunjucks.
  const getattr = (item, attr) => (item == null ? undefined : item[attr]);

  env.addFilter("selectattr", function (arr, attr, test, value) {
    return (arr || []).filter((item) => {
      const v = getattr(item, attr);
      if (test === undefined) return !!v;
      if (test === "equalto") return v === value;
      return !!v;
    });
  });

  env.addFilter("rejectattr", function (arr, attr, test, value) {
    return (arr || []).filter((item) => {
      const v = getattr(item, attr);
      if (test === undefined) return !v;
      if (test === "equalto") return v !== value;
      return !v;
    });
  });

  env.addFilter("select", function (arr) {
    return (arr || []).filter(Boolean);
  });

  env.addFilter("list", function (arr) {
    if (Array.isArray(arr)) return arr;
    return Array.from(arr || []);
  });

  app.set("view engine", "njk");
  return env;
}

module.exports = { configure };
