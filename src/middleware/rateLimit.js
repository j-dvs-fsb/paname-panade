"use strict";

const { rateLimit } = require("express-rate-limit");

// Limites anti-force-brute sur les points d'entrée d'authentification.
// (`trust proxy` est configuré : req.ip = IP réelle du visiteur.)

const message = "Trop de tentatives. Réessaie dans quelques minutes.";

function handler(req, res) {
  if (req.is("json") || (req.get("accept") || "").includes("application/json")) {
    return res.status(429).json({ error: message });
  }
  res.status(429).send(`429 — ${message}`);
}

// Connexion / inscription / vérification passkey : 10 échecs / 15 min / IP.
// Les requêtes réussies ne comptent pas (IP partagées : école, wifi public…).
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 10,
  skipSuccessfulRequests: true,
  standardHeaders: "draft-8",
  legacyHeaders: false,
  handler,
});

// Génération d'options WebAuthn (inoffensif mais évite l'abus) : 30 / 15 min.
const optionsLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 30,
  standardHeaders: "draft-8",
  legacyHeaders: false,
  handler,
});

module.exports = { authLimiter, optionsLimiter };
