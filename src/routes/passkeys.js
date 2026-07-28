"use strict";

const express = require("express");
const {
  generateRegistrationOptions,
  verifyRegistrationResponse,
  generateAuthenticationOptions,
  verifyAuthenticationResponse,
} = require("@simplewebauthn/server");

const { Credential } = require("../models");
const { requireLogin } = require("../middleware/auth");
const { authLimiter, optionsLimiter } = require("../middleware/rateLimit");
const { urlFor } = require("../lib/urls");
const { rpConfig } = require("../services/webauthn");

const router = express.Router();

// --- Gestion des passkeys (utilisateur connecté) ---
router.get("/compte/passkeys", requireLogin, async (req, res) => {
  const creds = await Credential.findAll({
    where: { user_id: req.user.id },
    order: [["id", "ASC"]],
  });
  res.render("auth/passkeys.njk", { creds });
});

// Enregistrement — génère les options (challenge stocké en session).
router.post("/compte/passkeys/options", requireLogin, optionsLimiter, async (req, res) => {
  const { rpID, rpName } = rpConfig(req);
  const existing = await Credential.findAll({ where: { user_id: req.user.id } });
  const options = await generateRegistrationOptions({
    rpName,
    rpID,
    userName: req.user.email,
    userID: new TextEncoder().encode(String(req.user.id)),
    attestationType: "none",
    excludeCredentials: existing.map((c) => ({
      id: c.credential_id,
      transports: c.transports ? c.transports.split(",") : undefined,
    })),
    authenticatorSelection: { residentKey: "preferred", userVerification: "preferred" },
  });
  req.session.webauthnChallenge = options.challenge;
  res.json(options);
});

// Enregistrement — vérifie la réponse et sauvegarde la passkey.
router.post("/compte/passkeys/verify", requireLogin, async (req, res) => {
  const { rpID, origin } = rpConfig(req);
  const expectedChallenge = req.session.webauthnChallenge;
  delete req.session.webauthnChallenge; // usage unique, même en cas d'échec
  if (!expectedChallenge || !req.body.credential) {
    return res.status(400).json({ error: "Vérification échouée. Recharge la page et réessaie." });
  }
  try {
    const verification = await verifyRegistrationResponse({
      response: req.body.credential,
      expectedChallenge,
      expectedOrigin: origin,
      expectedRPID: rpID,
    });
    if (!verification.verified || !verification.registrationInfo) {
      return res.status(400).json({ error: "Vérification échouée." });
    }
    const cred = verification.registrationInfo.credential;
    await Credential.create({
      user_id: req.user.id,
      credential_id: cred.id,
      public_key: Buffer.from(cred.publicKey).toString("base64url"),
      counter: cred.counter || 0,
      transports: (cred.transports || []).join(","),
      label: (req.body.label || "").trim().slice(0, 120) || null,
    });
    res.json({ ok: true });
  } catch (e) {
    console.error("Passkey registration failed:", e.message);
    res.status(400).json({ error: "Vérification échouée." });
  }
});

router.post("/compte/passkeys/:id/delete", requireLogin, async (req, res) => {
  const cred = await Credential.findOne({
    where: { id: req.params.id, user_id: req.user.id },
  });
  if (cred) {
    await cred.destroy();
    req.flash("info", "Passkey supprimée.");
  }
  res.redirect(urlFor("auth.passkeys"));
});

// --- Connexion par passkey (sans mot de passe) ---
router.post("/connexion/passkey/options", optionsLimiter, async (req, res) => {
  const { rpID } = rpConfig(req);
  const options = await generateAuthenticationOptions({ rpID, userVerification: "preferred" });
  req.session.webauthnChallenge = options.challenge;
  res.json(options);
});

router.post("/connexion/passkey/verify", authLimiter, async (req, res) => {
  const { rpID, origin } = rpConfig(req);
  const expectedChallenge = req.session.webauthnChallenge;
  delete req.session.webauthnChallenge; // usage unique, même en cas d'échec
  if (!expectedChallenge) {
    return res.status(400).json({ error: "Session expirée. Recharge la page et réessaie." });
  }
  try {
    const cred = await Credential.findOne({ where: { credential_id: req.body.id } });
    if (!cred) return res.status(400).json({ error: "Passkey inconnue." });
    const verification = await verifyAuthenticationResponse({
      response: req.body,
      expectedChallenge,
      expectedOrigin: origin,
      expectedRPID: rpID,
      credential: {
        id: cred.credential_id,
        publicKey: new Uint8Array(Buffer.from(cred.public_key, "base64url")),
        counter: Number(cred.counter),
        transports: cred.transports ? cred.transports.split(",") : undefined,
      },
    });
    if (!verification.verified) return res.status(400).json({ error: "Vérification échouée." });
    cred.counter = verification.authenticationInfo.newCounter;
    await cred.save();
    // Régénère l'ID de session à la connexion (anti-fixation de session).
    req.session.regenerate((err) => {
      if (err) return res.status(500).json({ error: "Erreur de session." });
      req.session.userId = cred.user_id;
      res.json({ ok: true, redirect: urlFor("main.profile") });
    });
  } catch (e) {
    console.error("Passkey authentication failed:", e.message);
    res.status(400).json({ error: "Vérification échouée." });
  }
});

module.exports = router;
