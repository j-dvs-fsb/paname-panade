"use strict";

const { User } = require("../models");
const { urlFor } = require("../lib/urls");

// current_user anonyme : objet nu exposant les attributs lus par les templates.
const ANON = { is_authenticated: false, is_admin: false };

// Charge l'utilisateur de session et l'expose en req.user + res.locals.current_user.
async function loadUser(req, res, next) {
  let user = null;
  if (req.session && req.session.userId) {
    try {
      user = await User.findByPk(req.session.userId);
    } catch (e) {
      user = null;
    }
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

function requireAdmin(req, res, next) {
  if (!req.user) {
    req.flash("info", "Connecte-toi pour accéder à cette page.");
    return res.redirect(urlFor("auth.login"));
  }
  if (!req.user.is_admin) return res.status(403).send("403 — accès réservé.");
  return next();
}

module.exports = { loadUser, requireLogin, requireAdmin, ANON };
