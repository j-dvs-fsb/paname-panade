"use strict";

const bcrypt = require("bcryptjs");
const express = require("express");
const { Op } = require("sequelize");
const { sequelize, User, Favorite, Visit, Credential, Exposition } = require("../models");
const { requireLogin } = require("../middleware/auth");
const { authLimiter } = require("../middleware/rateLimit");
const { urlFor } = require("../lib/urls");

const router = express.Router();

const MIN_PASSWORD = 8;

// Hachage factice comparé quand l'email est inconnu : temps de réponse
// identique compte connu / inconnu (pas d'énumération par chronométrage).
const DUMMY_HASH = bcrypt.hashSync("dummy-timing-equalizer", 12);

function parseDate(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((value || "").trim());
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return isNaN(d.getTime()) ? null : value.trim();
}

// Régénère l'ID de session à la connexion (anti-fixation de session).
function loginSession(req, userId) {
  return new Promise((resolve, reject) => {
    req.session.regenerate((err) => {
      if (err) return reject(err);
      req.session.userId = userId;
      resolve();
    });
  });
}

// N'accepte que des chemins relatifs internes (anti open-redirect).
function safeNext(value) {
  const next = String(value || "");
  if (next.startsWith("/") && !next.startsWith("//") && !next.includes("\\")) return next;
  return null;
}

router.get("/inscription", (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));
  res.render("auth/register.njk", { form: {} });
});

router.post("/inscription", authLimiter, async (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));

  const email = (req.body.email || "").trim().toLowerCase();
  const password = req.body.password || "";
  const prenom = (req.body.prenom || "").trim();
  const dateNaissance = req.body.date_naissance || "";

  const errors = [];
  if (!email || !email.includes("@")) errors.push("Email invalide.");
  if (password.length < MIN_PASSWORD)
    errors.push(`Le mot de passe doit faire au moins ${MIN_PASSWORD} caractères.`);
  if (!prenom) errors.push("Le prénom est requis.");
  if (!dateNaissance) errors.push("La date de naissance est requise.");
  if (await User.findOne({ where: { email } })) errors.push("Cet email est déjà utilisé.");
  const dn = parseDate(dateNaissance);
  if (!dn) errors.push("Date de naissance invalide.");

  if (errors.length) {
    for (const e of errors) req.flash("danger", e);
    return res.status(400).render("auth/register.njk", { form: req.body });
  }

  const user = User.build({ email, prenom, date_naissance: dn });
  user.setPassword(password);
  await user.save();
  await loginSession(req, user.id);
  req.flash("success", `Bienvenue ${prenom} ! Ton compte est créé.`);
  res.redirect(urlFor("main.profile"));
});

router.get("/connexion", (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));
  res.render("auth/login.njk");
});

router.post("/connexion", authLimiter, async (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));

  const email = (req.body.email || "").trim().toLowerCase();
  const password = req.body.password || "";
  const user = await User.findOne({ where: { email } });
  const ok = user ? user.checkPassword(password) : bcrypt.compareSync(password, DUMMY_HASH) && false;
  if (ok) {
    await loginSession(req, user.id);
    return res.redirect(safeNext(req.query.next) || urlFor("main.profile"));
  }
  req.flash("danger", "Email ou mot de passe incorrect.");
  res.status(401).render("auth/login.njk");
});

router.get("/compte", requireLogin, (req, res) => {
  res.render("auth/account.njk", { u: req.user });
});

router.post("/compte", requireLogin, async (req, res) => {
  const user = req.user;
  const email = (req.body.email || "").trim().toLowerCase();
  const prenom = (req.body.prenom || "").trim();
  const dateNaissance = req.body.date_naissance || "";
  const password = req.body.password || "";
  const password2 = req.body.password2 || "";

  const errors = [];
  if (!email || !email.includes("@")) errors.push("Email invalide.");
  if (!prenom) errors.push("Le prénom est requis.");
  if (!dateNaissance) errors.push("La date de naissance est requise.");
  const dn = parseDate(dateNaissance);
  if (dateNaissance && !dn) errors.push("Date de naissance invalide.");
  // Email déjà pris par un AUTRE utilisateur ?
  const clash = await User.findOne({ where: { email, id: { [Op.ne]: user.id } } });
  if (clash) errors.push("Cet email est déjà utilisé.");
  if (password && password.length < MIN_PASSWORD)
    errors.push(`Le nouveau mot de passe doit faire au moins ${MIN_PASSWORD} caractères.`);
  if (password && password !== password2)
    errors.push("Les deux mots de passe ne correspondent pas.");

  if (errors.length) {
    for (const e of errors) req.flash("danger", e);
    return res.render("auth/account.njk", { u: Object.assign({}, user.get(), req.body) });
  }

  user.email = email;
  user.prenom = prenom;
  if (dn) user.date_naissance = dn;
  if (password) user.setPassword(password);
  await user.save();
  req.flash("success", "Compte mis à jour.");
  res.redirect(urlFor("main.profile"));
});

// --- RGPD : portabilité — export JSON de toutes les données du compte ---
router.get("/compte/donnees", requireLogin, async (req, res) => {
  const [favorites, visits, credentials] = await Promise.all([
    Favorite.findAll({
      where: { user_id: req.user.id },
      include: [{ model: Exposition, as: "exposition", attributes: ["title", "slug"] }],
    }),
    Visit.findAll({
      where: { user_id: req.user.id },
      include: [{ model: Exposition, as: "exposition", attributes: ["title", "slug"] }],
    }),
    Credential.findAll({ where: { user_id: req.user.id } }),
  ]);

  const data = {
    exporte_le: new Date().toISOString(),
    compte: {
      email: req.user.email,
      prenom: req.user.prenom,
      date_naissance: req.user.date_naissance,
      cree_le: req.user.created_at,
    },
    favoris: favorites.map((f) => ({
      exposition: f.exposition ? f.exposition.title : null,
      ajoute_le: f.created_at,
    })),
    visites: visits.map((v) => ({
      exposition: v.exposition ? v.exposition.title : null,
      note: v.rating,
      commentaire: v.comment,
      visite_le: v.visited_at,
    })),
    passkeys: credentials.map((c) => ({ nom: c.label, ajoutee_le: c.created_at })),
  };

  res.setHeader("Content-Disposition", 'attachment; filename="paname-panade-mes-donnees.json"');
  res.json(data);
});

// --- RGPD : droit à l'effacement — suppression du compte par l'utilisateur ---
router.post("/compte/supprimer", requireLogin, async (req, res) => {
  const confirm = (req.body.confirm_email || "").trim().toLowerCase();
  if (confirm !== req.user.email.toLowerCase()) {
    req.flash("danger", "Confirmation incorrecte : saisis l'email exact de ton compte.");
    return res.redirect(urlFor("auth.account"));
  }

  const userId = req.user.id;
  await sequelize.transaction(async (t) => {
    await Favorite.destroy({ where: { user_id: userId }, transaction: t });
    await Visit.destroy({ where: { user_id: userId }, transaction: t });
    await Credential.destroy({ where: { user_id: userId }, transaction: t });
    await User.destroy({ where: { id: userId }, transaction: t });
  });

  req.session.destroy(() => res.redirect(urlFor("main.index")));
});

router.post("/deconnexion", requireLogin, (req, res) => {
  req.session.destroy(() => {
    res.redirect(urlFor("main.index"));
  });
});

module.exports = router;
