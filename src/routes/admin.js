"use strict";

const express = require("express");
const { Op } = require("sequelize");

const {
  sequelize,
  Museum,
  Exposition,
  PRICE_LABELS,
  RESERVATION_LABELS,
  FREE_ACCESS_LABELS,
} = require("../models");
const { requireAdmin } = require("../middleware/auth");
const { urlFor } = require("../lib/urls");
const { htmlToText } = require("../lib/text");
const { nextLocalMuseumId } = require("../lib/dedup");
const { toSlug } = require("../lib/slug");

const router = express.Router();
router.use(requireAdmin);

// --- Helpers ---
async function uniqueSlug(model, base, currentId = null) {
  base = toSlug(base).slice(0, 200) || model.name.toLowerCase();
  let slug = base;
  let n = 2;
  for (;;) {
    const where = { slug };
    if (currentId != null) where.id = { [Op.ne]: currentId };
    const clash = await model.findOne({ where });
    if (!clash) return slug;
    slug = `${base}-${n}`;
    n += 1;
  }
}

function parseDate(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((value || "").trim());
  return m ? value.trim() : null;
}

function toFloat(value) {
  const f = parseFloat(value);
  return Number.isNaN(f) ? null : f;
}

function clean(value) {
  const s = (value || "").trim();
  return s || null;
}

function asList(v) {
  if (v === undefined || v === null) return [];
  return (Array.isArray(v) ? v : [v]).filter(Boolean);
}

// --- Dashboard ---
router.get("/", async (req, res) => {
  const stats = {
    expos: await Exposition.count(),
    expos_draft: await Exposition.count({ where: { status: "draft" } }),
    museums: await Museum.count(),
  };
  const drafts = await Exposition.findAll({
    where: { status: "draft" },
    order: [["id", "DESC"]],
    limit: 10,
  });
  res.render("admin/dashboard.njk", { stats, drafts });
});

// --- Expositions ---
router.get("/expositions", async (req, res) => {
  const q = (req.query.q || "").trim();
  const status = (req.query.status || "").trim();
  const where = {};
  if (q) where.title = { [Op.like]: `%${q}%` };
  if (status === "draft" || status === "published") where.status = status;
  const expos = await Exposition.findAll({ where, order: [["id", "DESC"]] });
  res.render("admin/expos.njk", { expos, q, status });
});

async function renderExpoForm(res, expo) {
  const museums = await Museum.findAll({ order: [["name", "ASC"]] });
  res.render("admin/expo_form.njk", {
    expo,
    museums,
    price_labels: PRICE_LABELS,
    reservation_labels: RESERVATION_LABELS,
  });
}

async function handleExpoForm(req, res) {
  const expoId = req.params.id ? parseInt(req.params.id, 10) : null;
  let expo = expoId ? await Exposition.findByPk(expoId) : null;
  if (expoId && !expo) return res.status(404).render("404.njk");

  if (req.method === "POST") {
    const f = req.body;
    const title = (f.title || "").trim();
    if (!title) {
      req.flash("danger", "Le titre est obligatoire.");
      return renderExpoForm(res, expo);
    }
    if (!expo) {
      expo = Exposition.build({ source: "manuel", slug: await uniqueSlug(Exposition, title) });
    }
    expo.title = title;
    expo.description = htmlToText(f.description);
    expo.date_start = parseDate(f.date_start);
    expo.date_end = parseDate(f.date_end);
    expo.schedule = clean(f.schedule);
    expo.url = clean(f.url);
    expo.image_url = clean(f.image_url);
    expo.venue_name = clean(f.venue_name);
    expo.address = clean(f.address);
    expo.postal_code = clean(f.postal_code);
    expo.lat = toFloat(f.lat);
    expo.lon = toFloat(f.lon);
    expo.price_category = f.price_category || "gratuit_tous";
    expo.reservation = f.reservation || "non_necessaire";
    expo.reservation_url = clean(f.reservation_url);
    expo.museum_id = f.museum_id ? parseInt(f.museum_id, 10) : null;
    expo.status = f.status === "published" ? "published" : "draft";
    await expo.save();
    req.flash("success", "Exposition enregistrée.");
    return res.redirect(urlFor("admin.expos"));
  }
  return renderExpoForm(res, expo);
}

router.get("/expositions/nouvelle", handleExpoForm);
router.post("/expositions/nouvelle", handleExpoForm);
router.get("/expositions/:id/edit", handleExpoForm);
router.post("/expositions/:id/edit", handleExpoForm);

router.post("/expositions/:id/statut", async (req, res) => {
  const expo = await Exposition.findByPk(req.params.id);
  if (!expo) return res.status(404).render("404.njk");
  expo.status = expo.status === "published" ? "draft" : "published";
  await expo.save();
  req.flash("info", `Statut : ${expo.status}.`);
  res.redirect(req.get("referer") || urlFor("admin.expos"));
});

router.post("/expositions/:id/supprimer", async (req, res) => {
  const expo = await Exposition.findByPk(req.params.id);
  if (!expo) return res.status(404).render("404.njk");
  await expo.destroy();
  req.flash("info", "Exposition supprimée.");
  res.redirect(urlFor("admin.expos"));
});

// --- Musées ---
router.get("/musees", async (req, res) => {
  const museums = await Museum.findAll({ order: [["name", "ASC"]] });
  res.render("admin/museums.njk", { museums });
});

async function handleMuseumForm(req, res) {
  const museumId = req.params.id ? parseInt(req.params.id, 10) : null;
  let museum = museumId ? await Museum.findByPk(museumId) : null;
  if (museumId && !museum) return res.status(404).render("404.njk");

  if (req.method === "POST") {
    const f = req.body;
    const name = (f.name || "").trim();
    if (!name) {
      req.flash("danger", "Le nom est obligatoire.");
      return res.render("admin/museum_form.njk", { museum, free_access_labels: FREE_ACCESS_LABELS });
    }
    if (!museum) {
      const slug = await uniqueSlug(Museum, name);
      const existing = (await Museum.findAll({ attributes: ["museofile_id"] })).map((m) => m.museofile_id);
      museum = Museum.build({ slug, name, museofile_id: nextLocalMuseumId(existing) });
    }
    museum.name = name;
    museum.description = clean(f.description);
    museum.address = clean(f.address);
    museum.arrondissement = clean(f.arrondissement);
    museum.website = clean(f.website);
    museum.expos_url = clean(f.expos_url);
    museum.logo_url = clean(f.logo_url);
    const valid = new Set(Object.keys(FREE_ACCESS_LABELS));
    museum.free_access = asList(f.free_access).filter((k) => valid.has(k)).join(",");
    museum.lat = toFloat(f.lat);
    museum.lon = toFloat(f.lon);
    await museum.save();
    req.flash("success", "Musée enregistré.");
    return res.redirect(urlFor("admin.museums"));
  }
  return res.render("admin/museum_form.njk", { museum, free_access_labels: FREE_ACCESS_LABELS });
}

router.get("/musees/nouveau", handleMuseumForm);
router.post("/musees/nouveau", handleMuseumForm);
router.get("/musees/:id/edit", handleMuseumForm);
router.post("/musees/:id/edit", handleMuseumForm);

router.post("/musees/:id/supprimer", async (req, res) => {
  const museum = await Museum.findByPk(req.params.id);
  if (!museum) return res.status(404).render("404.njk");
  await museum.destroy();
  req.flash("info", "Musée supprimé (et ses expositions rattachées).");
  res.redirect(urlFor("admin.museums"));
});

// --- Sync « Que Faire à Paris » ---
router.post("/sync-qfap", async (req, res) => {
  const { runSync } = require("../services/sync");
  try {
    const { created, updated } = await runSync({ limit: 200 });
    req.flash("success", `Sync QFAP : ${created} créées, ${updated} mises à jour.`);
  } catch (e) {
    req.flash("danger", `Erreur sync : ${e.message}`);
  }
  res.redirect(urlFor("admin.dashboard"));
});

module.exports = router;
