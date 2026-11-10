"use strict";

// POST /api/import : reçoit l'export quotidien du Panade Collector.
//
// Monté avant les sessions et la protection CSRF (app.js) : ce n'est pas un
// formulaire de navigateur, c'est un envoi machine authentifié par un jeton
// Bearer (PANADE_IMPORT_TOKEN). Le corps est lu brut pour que l'empreinte soit
// vérifiée sur ce qui a été reçu, avant toute écriture.

const crypto = require("crypto");
const express = require("express");
const { rateLimit } = require("express-rate-limit");

const config = require("../config");
const { recevoir, ImportRefuse } = require("../services/collectorImport");

const router = express.Router();
const JETON_MIN = 32;

// Un envoi par matin suffit ; au-delà, c'est une erreur ou une tentative.
const limiteur = rateLimit({
  windowMs: 60 * 60 * 1000,
  limit: 20,
  standardHeaders: "draft-8",
  legacyHeaders: false,
  handler: (req, res) => res.status(429).json({ erreur: "trop d'envois, réessayer plus tard" }),
});

function jetonValide(entete, attendu) {
  const m = /^Bearer\s+(.+)$/i.exec(entete || "");
  if (!m) return false;
  // Comparaison à durée constante sur des empreintes de même longueur.
  const a = crypto.createHash("sha256").update(m[1].trim()).digest();
  const b = crypto.createHash("sha256").update(attendu).digest();
  return crypto.timingSafeEqual(a, b);
}

router.post(
  "/api/import",
  limiteur,
  express.raw({ type: () => true, limit: "20mb" }),
  async (req, res) => {
    const attendu = config.importToken;
    if (!attendu || attendu.length < JETON_MIN) {
      return res.status(503).json({ erreur: "import désactivé : PANADE_IMPORT_TOKEN absent ou trop court" });
    }
    if (!jetonValide(req.get("authorization"), attendu)) {
      return res.status(401).json({ erreur: "jeton invalide" });
    }
    if (!req.is("application/json")) {
      return res.status(415).json({ erreur: "Content-Type application/json attendu" });
    }
    try {
      const resultat = await recevoir(req.body, req.get("idempotency-key"));
      if (resultat.applique) console.log("[import] Export du collecteur appliqué :", JSON.stringify(resultat.bilan));
      return res.status(200).json(resultat);
    } catch (err) {
      if (err instanceof ImportRefuse) {
        return res.status(err.statut).json({ erreur: err.message, details: err.details });
      }
      console.error("[import] Échec, rien n'a été appliqué :", err);
      return res.status(500).json({ erreur: "erreur interne, rien n'a été appliqué" });
    }
  }
);

module.exports = router;
