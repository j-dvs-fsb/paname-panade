"use strict";

const express = require("express");
const { Op } = require("sequelize");
const { User } = require("../models");
const { requireLogin } = require("../middleware/auth");
const { urlFor } = require("../lib/urls");

const router = express.Router();

function parseDate(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((value || "").trim());
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return isNaN(d.getTime()) ? null : value.trim();
}

router.get("/inscription", (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));
  res.render("auth/register.njk", { form: {} });
});

router.post("/inscription", async (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));

  const email = (req.body.email || "").trim().toLowerCase();
  const password = req.body.password || "";
  const prenom = (req.body.prenom || "").trim();
  const dateNaissance = req.body.date_naissance || "";

  const errors = [];
  if (!email || !email.includes("@")) errors.push("Email invalide.");
  if (password.length < 6) errors.push("Le mot de passe doit faire au moins 6 caractères.");
  if (!prenom) errors.push("Le prénom est requis.");
  if (!dateNaissance) errors.push("La date de naissance est requise.");
  if (await User.findOne({ where: { email } })) errors.push("Cet email est déjà utilisé.");
  const dn = parseDate(dateNaissance);
  if (!dn) errors.push("Date de naissance invalide.");

  if (errors.length) {
    for (const e of errors) req.flash("danger", e);
    return res.render("auth/register.njk", { form: req.body });
  }

  const user = User.build({ email, prenom, date_naissance: dn });
  user.setPassword(password);
  await user.save();
  req.session.userId = user.id;
  req.flash("success", `Bienvenue ${prenom} ! Ton compte est créé.`);
  res.redirect(urlFor("main.profile"));
});

router.get("/connexion", (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));
  res.render("auth/login.njk");
});

router.post("/connexion", async (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));

  const email = (req.body.email || "").trim().toLowerCase();
  const password = req.body.password || "";
  const user = await User.findOne({ where: { email } });
  if (user && user.checkPassword(password)) {
    req.session.userId = user.id;
    const next = req.query.next;
    return res.redirect(next || urlFor("main.profile"));
  }
  req.flash("danger", "Email ou mot de passe incorrect.");
  res.render("auth/login.njk");
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
  if (password && password.length < 6)
    errors.push("Le nouveau mot de passe doit faire au moins 6 caractères.");
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

router.get("/deconnexion", requireLogin, (req, res) => {
  req.session.destroy(() => {
    res.redirect(urlFor("main.index"));
  });
});

module.exports = router;
