"use strict";

// Gestion des passkeys.
//
// Les cérémonies WebAuthn elles-mêmes (émission du défi, vérification de la
// signature) sont assurées par le greffon officiel de Better Auth, monté sur
// /api/auth/passkey/* et appelé directement par le navigateur. Ce routeur ne
// garde que ce qui relève du site : la page de gestion et la suppression, avec
// notre jeton CSRF et nos messages flash.

const express = require("express");

const { Passkey } = require("../models");
const { requireLogin } = require("../middleware/auth");
const { urlFor } = require("../lib/urls");

const router = express.Router();

router.get("/compte/passkeys", requireLogin, async (req, res) => {
  const passkeys = await Passkey.findAll({
    where: { userId: req.user.id },
    order: [["id", "ASC"]],
  });
  res.render("auth/passkeys.njk", {
    passkeys,
    // Affiché juste après une inscription : on propose la passkey plutôt que
    // de la laisser enfouie dans les réglages du compte.
    bienvenue: req.query.bienvenue === "1",
  });
});

router.post("/compte/passkeys/:id/delete", requireLogin, async (req, res) => {
  const passkey = await Passkey.findOne({
    where: { id: req.params.id, userId: req.user.id },
  });
  if (passkey) {
    await passkey.destroy();
    req.flash("info", "Passkey supprimée.");
  }
  res.redirect(urlFor("auth.passkeys"));
});

module.exports = router;
