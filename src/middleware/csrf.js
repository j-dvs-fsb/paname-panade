"use strict";

const crypto = require("crypto");

// Protection CSRF par jeton de session (motif « synchronizer token »).
// - `csrf_token()` (exposé aux templates) crée le jeton à la demande, pour ne
//   pas créer une session en base pour chaque visiteur anonyme.
// - Toute requête non sûre (POST/PUT/PATCH/DELETE) doit fournir le jeton via
//   le champ `_csrf` (formulaires) ou l'en-tête `X-CSRF-Token` (fetch JSON).
// Défense en profondeur : le cookie SameSite=Lax bloque déjà l'essentiel.

function ensureToken(session) {
  if (!session.csrfToken) session.csrfToken = crypto.randomBytes(32).toString("base64url");
  return session.csrfToken;
}

function tokensMatch(expected, provided) {
  if (typeof expected !== "string" || typeof provided !== "string") return false;
  const a = Buffer.from(expected);
  const b = Buffer.from(provided);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function csrfProtection(req, res, next) {
  res.locals.csrf_token = () => ensureToken(req.session);

  if (SAFE_METHODS.has(req.method)) return next();

  const provided = (req.body && req.body._csrf) || req.get("x-csrf-token");
  if (tokensMatch(req.session.csrfToken, provided)) return next();

  const wantsJson = req.is("json") || (req.get("accept") || "").includes("application/json");
  if (wantsJson) return res.status(403).json({ error: "Session expirée, recharge la page." });
  return res.status(403).send("403 - jeton de sécurité invalide ou expiré. Recharge la page et réessaie.");
}

module.exports = { csrfProtection, ensureToken };
