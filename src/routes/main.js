"use strict";

const express = require("express");
const { Op } = require("sequelize");

const { sequelize, User, Museum, Exposition, Favorite, Visit, Page } = require("../models");
const { requireLogin } = require("../middleware/auth");
const { urlFor } = require("../lib/urls");
const { todayIso } = require("../lib/dates");
const seo = require("../lib/seo");
const stats = require("../services/stats");

const router = express.Router();

// --- Helpers ---
function currentWhere(extra = {}) {
  // Publiées et non passées (date de fin absente ou ≥ aujourd'hui).
  return {
    status: "published",
    [Op.and]: [{ [Op.or]: [{ date_end: null }, { date_end: { [Op.gte]: todayIso() } }] }],
    ...extra,
  };
}

function asList(v) {
  if (v === undefined || v === null) return [];
  return (Array.isArray(v) ? v : [v]).filter((x) => x !== "");
}

async function userExpoState(req, expoId) {
  if (!req.user) return { isFavorite: false, visit: null };
  const fav = await Favorite.findOne({ where: { user_id: req.user.id, exposition_id: expoId } });
  const visit = await Visit.findOne({ where: { user_id: req.user.id, exposition_id: expoId } });
  return { isFavorite: !!fav, visit };
}

function randomOrder() {
  return [sequelize.getDialect() === "mysql" ? sequelize.literal("RAND()") : sequelize.literal("RANDOM()")];
}

// --- Quasi-doublons ---
// Le jeu de données publie une fiche par séance : « Visite + Chaillot
// Expérience » existe en quatre exemplaires, même titre et même visuel, seules
// les dates changent. Elles se cannibalisent dans les résultats de recherche.
// On les regroupe par (titre, lieu) : la plus ancienne fiche fait référence,
// les autres la déclarent en canonical et affichent les dates de la fratrie.
function sessionKey(expo) {
  const place = expo.museum_id != null ? `m${expo.museum_id}` : `v${expo.venue_name || ""}`;
  return `${(expo.title || "").trim().toLowerCase()}|${place}`;
}

async function sessionSiblings(expo) {
  const where = { title: expo.title, status: "published" };
  if (expo.museum_id != null) where.museum_id = expo.museum_id;
  else where.venue_name = expo.venue_name;
  return Exposition.findAll({
    where,
    attributes: ["id", "slug", "title", "date_start", "date_end", "source"],
    order: [["id", "ASC"]],
  });
}

// --- Accueil ---
router.get("/", async (req, res) => {
  const total_expos = await Exposition.count({ where: currentWhere() });
  const total_museums = await Museum.count();
  const latest = await Exposition.findAll({
    where: currentWhere(),
    include: [{ model: Museum, as: "museum" }],
    order: [["id", "DESC"]],
    limit: 6,
  });
  res.locals.meta = seo.pageMeta(req, {
    title: "Expos et musées gratuits à Paris pour les -26 ans",
    description:
      `${total_expos} expositions gratuites et ${total_museums} musées à Paris, ` +
      "avec les dates, les horaires et les conditions de gratuité pour les moins de 26 ans.",
    url: urlFor("main.index"),
  });
  res.render("index.njk", { total_expos, total_museums, latest });
});

// --- Musées ---
router.get("/musees", async (req, res) => {
  const museums = await Museum.findAll({ order: [["name", "ASC"]] });
  res.locals.meta = seo.pageMeta(req, {
    title: "Musées gratuits à Paris",
    description:
      "La liste des musées parisiens gratuits : collections permanentes en accès libre " +
      "et musées gratuits pour les moins de 26 ans, arrondissement par arrondissement.",
    url: urlFor("main.museums"),
  });
  res.render("museums.njk", { museums });
});

router.get("/musee/:slug", async (req, res) => {
  const museum = await Museum.findOne({
    where: { slug: req.params.slug },
    include: [{ model: Exposition, as: "expositions", include: [{ model: Visit, as: "visits" }] }],
  });
  if (!museum) return res.status(404).render("404.njk");
  const url = urlFor("main.museum_detail", { slug: museum.slug });
  res.locals.meta = seo.pageMeta(req, {
    title: `${museum.name} — gratuit pour les -26 ans`,
    description:
      seo.metaDescription(museum.description) ||
      `${museum.name} : expositions en cours, horaires et conditions de gratuité pour les moins de 26 ans.`,
    url,
    og_type: "article",
    image: museum.image_url,
    jsonld: seo.museumJsonLd(museum, {
      url: seo.absoluteUrl(req, url),
      image: seo.shareImage(req, museum.image_url),
    }),
  });
  res.render("museum_detail.njk", { museum });
});

// --- Radar ---
async function geoMuseums() {
  const museums = await Museum.findAll({
    where: { lat: { [Op.ne]: null }, lon: { [Op.ne]: null } },
    order: [["name", "ASC"]],
  });
  const currents = await Exposition.findAll({ where: currentWhere(), attributes: ["museum_id"] });
  const counts = {};
  for (const e of currents) {
    if (e.museum_id != null) counts[e.museum_id] = (counts[e.museum_id] || 0) + 1;
  }
  return { museums, counts };
}

function arrSortKey(arr) {
  const m = /(\d+)/.exec(arr || "");
  return m ? [0, parseInt(m[1], 10)] : [1, 0];
}

router.get("/radar", async (req, res) => {
  const { museums } = await geoMuseums();
  const groups = {};
  for (const m of museums) {
    if (m.arrondissement) (groups[m.arrondissement] || (groups[m.arrondissement] = [])).push(m);
  }
  const centroids = {};
  for (const [arr, ms] of Object.entries(groups)) {
    centroids[arr] = {
      lat: ms.reduce((a, x) => a + x.lat, 0) / ms.length,
      lon: ms.reduce((a, x) => a + x.lon, 0) / ms.length,
    };
  }
  const arrondissements = Object.keys(groups).sort((a, b) => {
    const ka = arrSortKey(a), kb = arrSortKey(b);
    return ka[0] - kb[0] || ka[1] - kb[1] || a.localeCompare(b);
  });
  res.locals.meta = seo.pageMeta(req, {
    title: "Radar — les musées gratuits sur la carte",
    description:
      "La carte des musées gratuits de Paris, arrondissement par arrondissement, " +
      "avec le nombre d'expositions en cours dans chacun.",
    url: urlFor("main.radar"),
  });
  res.render("radar.njk", { arrondissements, centroids });
});

router.get("/api/museums.json", async (req, res) => {
  const { museums, counts } = await geoMuseums();
  res.json(
    museums.map((m) => ({
      id: m.id,
      name: m.name,
      slug: m.slug,
      arrondissement: m.arrondissement,
      lat: m.lat,
      lon: m.lon,
      expo_count: counts[m.id] || 0,
      url: urlFor("main.museum_detail", { slug: m.slug }),
    }))
  );
});

// --- Expositions (liste + filtres) ---
const PRICE_TILES = [
  ["gratuit_tous", "Gratuit pour tous"],
  ["gratuit_26", "Gratuit -26 ans"],
  ["reduit_26", "Tarif réduit -26 ans"],
];
const FLAG_TILES = [
  ["nocturne", "Nocturne"],
  ["dimanche", "Ouvert le dimanche"],
  ["climatise", "Climatisé"],
];

function toggleArgs(query, key, value) {
  const d = {};
  for (const [k, v] of Object.entries(query)) d[k] = asList(v);
  const cur = d[key] || [];
  const idx = cur.indexOf(value);
  if (idx >= 0) cur.splice(idx, 1);
  else cur.push(value);
  if (cur.length) d[key] = cur;
  else delete d[key];
  return d;
}

function buildTiles(defs, key, active, query) {
  return defs.map(([val, label]) => ({
    label,
    active: active.includes(val),
    href: urlFor("main.expos", toggleArgs(query, key, val)),
  }));
}

router.get("/expositions", async (req, res) => {
  const q = (req.query.q || "").trim();
  const active_prix = asList(req.query.prix);
  const active_flags = asList(req.query.f);

  const where = currentWhere();
  if (q) where.title = { [Op.like]: `%${q}%` };
  const validPrix = active_prix.filter((p) => PRICE_TILES.some(([v]) => v === p));
  if (validPrix.length) where.price_category = { [Op.in]: validPrix };
  // nocturne / dimanche / climatisé : pas de données -> non filtré (parité Flask).

  const expos = await Exposition.findAll({
    where,
    include: [{ model: Museum, as: "museum" }],
    order: [["title", "ASC"]],
  });

  res.locals.meta = seo.pageMeta(req, {
    title: "Toutes les expositions gratuites de Paris",
    description:
      "Les expositions gratuites à Paris en ce moment : dates, horaires, musée et " +
      "conditions d'entrée, filtrables par type de gratuité.",
    url: urlFor("main.expos"),
    // Les combinaisons de filtres produisent autant d'URL que de croisements :
    // toutes se déclarent canoniques vers la liste nue.
    canonical: urlFor("main.expos"),
    robots: q || active_prix.length || active_flags.length ? "noindex, follow" : null,
  });
  res.render("expos.njk", {
    expos,
    q,
    price_tiles: buildTiles(PRICE_TILES, "prix", active_prix, req.query),
    flag_tiles: buildTiles(FLAG_TILES, "f", active_flags, req.query),
    active_prix,
    active_flags,
  });
});

router.get("/exposition/:slug", async (req, res) => {
  const expo = await Exposition.findOne({
    where: { slug: req.params.slug },
    include: [
      { model: Museum, as: "museum" },
      { model: Visit, as: "visits", include: [{ model: User, as: "user" }] },
    ],
  });
  if (!expo) return res.status(404).render("404.njk");
  if (expo.status !== "published" && !(req.user && req.user.is_admin)) {
    return res.status(404).render("404.njk");
  }
  const { isFavorite, visit } = await userExpoState(req, expo.id);
  const reviews = (expo.visits || [])
    .filter((v) => v.rating || v.comment)
    .sort((a, b) => new Date(b.visited_at || 0) - new Date(a.visited_at || 0));

  const siblings = expo.status === "published" ? await sessionSiblings(expo) : [expo];
  const reference = siblings.length ? siblings[0] : expo;
  const otherSessions = siblings.filter((s) => s.id !== expo.id);

  const url = urlFor("main.expo_detail", { slug: expo.slug });
  const absolute = seo.absoluteUrl(req, url);
  res.locals.meta = seo.pageMeta(req, {
    title: `${expo.title}${expo.museum ? " — " + expo.museum.name : ""}`,
    description: seo.metaDescription(expo.description_text) || expo.editorial_note,
    url,
    canonical: urlFor("main.expo_detail", { slug: reference.slug }),
    og_type: "article",
    image: expo.image,
    jsonld: seo.expoJsonLd(expo, { url: absolute, image: seo.shareImage(req, expo.image) }),
  });
  res.render("expo_detail.njk", {
    expo,
    is_fav: isFavorite,
    visit,
    reviews,
    other_sessions: otherSessions,
  });
});

// --- Favori / fait ---
router.post("/exposition/:id/favori", requireLogin, async (req, res) => {
  const expo = await Exposition.findByPk(req.params.id);
  if (!expo) return res.status(404).render("404.njk");
  const fav = await Favorite.findOne({ where: { user_id: req.user.id, exposition_id: expo.id } });
  if (fav) {
    await fav.destroy();
    req.flash("info", "Retiré des favoris.");
  } else {
    await Favorite.create({ user_id: req.user.id, exposition_id: expo.id });
    req.flash("success", "Ajouté aux favoris ⭐");
  }
  res.redirect(req.get("referer") || urlFor("main.expo_detail", { slug: expo.slug }));
});

router.post("/exposition/:id/fait", requireLogin, async (req, res) => {
  const expo = await Exposition.findByPk(req.params.id);
  if (!expo) return res.status(404).render("404.njk");
  const rating = parseInt(req.body.rating, 10);
  const comment = (req.body.comment || "").trim();

  let visit = await Visit.findOne({ where: { user_id: req.user.id, exposition_id: expo.id } });
  if (!visit) visit = Visit.build({ user_id: req.user.id, exposition_id: expo.id });
  if (rating && rating >= 1 && rating <= 5) visit.rating = rating;
  visit.comment = comment || visit.comment;
  await visit.save();
  req.flash("success", "Expo marquée comme faite ! 🎉");
  res.redirect(req.get("referer") || urlFor("main.expo_detail", { slug: expo.slug }));
});

router.post("/exposition/:id/annuler-fait", requireLogin, async (req, res) => {
  const visit = await Visit.findOne({ where: { user_id: req.user.id, exposition_id: req.params.id } });
  if (visit) {
    await visit.destroy();
    req.flash("info", "Visite annulée.");
  }
  res.redirect(req.get("referer") || urlFor("main.profile"));
});

// --- Au hasard ---
router.get("/au-hasard", async (req, res) => {
  const expo = await Exposition.findOne({ where: currentWhere(), order: randomOrder() });
  if (!expo) {
    req.flash("info", "Aucune exposition en base pour le moment.");
    return res.redirect(urlFor("main.index"));
  }
  res.redirect(urlFor("main.expo_detail", { slug: expo.slug }));
});

// --- Profil ---
router.get("/profil", requireLogin, async (req, res) => {
  const prog = await stats.progress(req.user);
  const fun = await stats.funStats(req.user);
  const visits = await Visit.findAll({
    where: { user_id: req.user.id },
    include: [{ model: Exposition, as: "exposition", include: [{ model: Museum, as: "museum" }] }],
    order: [["visited_at", "DESC"]],
  });
  const favorites = await Favorite.findAll({
    where: { user_id: req.user.id },
    include: [{ model: Exposition, as: "exposition", include: [{ model: Museum, as: "museum" }] }],
    order: [["created_at", "DESC"]],
  });
  res.render("profile.njk", { prog, fun, visits, favorites });
});

// --- Pages statiques (pied de page), éditables depuis le back-office ---
async function staticPage(req, res) {
  const page = await Page.findOne({ where: { slug: req.path.slice(1) } });
  if (!page) return res.status(404).render("404.njk");
  res.locals.meta = seo.pageMeta(req, {
    title: page.title,
    description: seo.metaDescription(page.content.replace(/<[^>]+>/g, " ")),
    url: req.path,
  });
  res.render("page.njk", { page });
}
router.get("/a-propos", staticPage);
router.get("/mentions-legales", staticPage);
router.get("/confidentialite", staticPage);

// --- Sitemap & robots ---
function xmlEscape(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

router.get("/sitemap.xml", async (req, res) => {
  const entries = [
    { path: urlFor("main.index"), priority: "1.0", changefreq: "daily" },
    { path: urlFor("main.expos"), priority: "0.9", changefreq: "daily" },
    { path: urlFor("main.museums"), priority: "0.8", changefreq: "weekly" },
    { path: urlFor("main.radar"), priority: "0.5", changefreq: "monthly" },
  ];

  const museums = await Museum.findAll({ attributes: ["slug"], order: [["name", "ASC"]] });
  for (const m of museums) {
    entries.push({ path: urlFor("main.museum_detail", { slug: m.slug }), priority: "0.7", changefreq: "weekly" });
  }

  // Une seule URL par groupe de quasi-doublons : celle déclarée canonique par
  // la fiche (cf. sessionSiblings), sinon on soumettrait des pages qu'on
  // demande par ailleurs de ne pas indexer.
  const expos = await Exposition.findAll({
    where: currentWhere(),
    attributes: ["id", "slug", "title", "museum_id", "venue_name", "date_end"],
    order: [["id", "ASC"]],
  });
  const seen = new Set();
  for (const expo of expos) {
    const key = sessionKey(expo);
    if (seen.has(key)) continue;
    seen.add(key);
    entries.push({
      path: urlFor("main.expo_detail", { slug: expo.slug }),
      priority: "0.6",
      changefreq: "weekly",
    });
  }

  for (const slug of ["main.about", "main.legal", "main.privacy"]) {
    entries.push({ path: urlFor(slug), priority: "0.2", changefreq: "yearly" });
  }

  const body = entries
    .map(
      (e) =>
        `  <url><loc>${xmlEscape(seo.absoluteUrl(req, e.path))}</loc>` +
        `<changefreq>${e.changefreq}</changefreq><priority>${e.priority}</priority></url>`
    )
    .join("\n");

  res.type("application/xml");
  res.send(`<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${body}\n</urlset>\n`);
});

router.get("/robots.txt", (req, res) => {
  const lines = [
    "User-agent: *",
    "Allow: /",
    "Disallow: /admin",
    "Disallow: /compte",
    "Disallow: /profil",
    "Disallow: /connexion",
    "Disallow: /inscription",
    "Disallow: /deconnexion",
    "Disallow: /au-hasard", // redirection aléatoire : rien à indexer
    "",
    `Sitemap: ${seo.absoluteUrl(req, "/sitemap.xml")}`,
    "",
  ];
  res.type("text/plain").send(lines.join("\n"));
});

module.exports = router;
