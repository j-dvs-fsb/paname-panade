"use strict";

const { User } = require("../models");
const { urlFor } = require("../lib/urls");
const { currentSession } = require("../auth/session");

// current_user anonyme : objet nu exposant les attributs lus par les templates.
const ANON = { is_authenticated: false, is_admin: false, is_over_26: false };

// Charge l'utilisateur de la session Better Auth et l'expose en req.user +
// res.locals.current_user. L'instance Sequelize est rechargée : les templates
// et les routes s'appuient sur ses getters (days_until_26, is_over_26…), que
// l'objet renvoyé par Better Auth n'a pas.
async function loadUser(req, res, next) {
  let user = null;
  try {
    const session = await currentSession(req);
    if (session && session.user) user = await User.findByPk(Number(session.user.id));
  } catch (e) {
    user = null;
  }
  req.user = user;
  res.locals.current_user = user || ANON;
  next();
}

function requireLogin(req, res, next) {
  if (req.user) return next();
  req.flash("info", "Connecte-toi pour accéder à cette page.");
  const next_ = encodeURIComponent(req.originalUrl);
  return res.redirect(urlFor("auth.login") + "?next=" + next_);
}

// Une première connexion Google ne fournit pas de date de naissance : sans
// elle, le compte à rebours et les statistiques n'ont aucun sens. On la demande
// à l'entrée des pages qui s'en servent — ailleurs, la navigation reste libre.
function requireProfile(req, res, next) {
  if (req.user && !req.user.date_naissance) {
    return res.redirect(urlFor("auth.complete_profile"));
  }
  return next();
}

function requireAdmin(req, res, next) {
  if (!req.user) {
    req.flash("info", "Connecte-toi pour accéder à cette page.");
    return res.redirect(urlFor("auth.login"));
  }
  if (!req.user.is_admin) return res.status(403).send("403 — accès réservé.");
  return next();
}

module.exports = { loadUser, requireLogin, requireProfile, requireAdmin, ANON };
