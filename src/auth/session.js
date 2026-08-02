"use strict";

// Ponts entre Express et Better Auth : lire la session courante, en ouvrir une
// depuis une route maison, en fermer une.
//
// Les formulaires du site restent des POST classiques rendus par le serveur
// (jeton CSRF, limitation de débit, messages flash). On appelle donc l'API
// serveur de Better Auth plutôt que d'exposer ses points d'entrée REST au
// navigateur — sauf pour le retour OAuth de Google, qui doit atterrir sur son
// gestionnaire.

const { getAuth } = require("./index");

// Convertit les en-têtes Node en objet Headers du Web (attendu par l'API).
function toHeaders(req) {
  const headers = new Headers();
  for (const [key, value] of Object.entries(req.headers)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) value.forEach((v) => headers.append(key, v));
    else headers.set(key, value);
  }
  return headers;
}

// Recopie les cookies posés par Better Auth sur la réponse Express.
function forwardCookies(res, headers) {
  if (!headers) return;
  const cookies = typeof headers.getSetCookie === "function" ? headers.getSetCookie() : [];
  for (const cookie of cookies) res.append("Set-Cookie", cookie);
}

async function currentSession(req) {
  const auth = await getAuth();
  try {
    return await auth.api.getSession({ headers: toHeaders(req) });
  } catch (e) {
    return null;
  }
}

// Ouvre une session pour un utilisateur déjà authentifié par un autre moyen
// (ici : une passkey vérifiée par nos soins). On passe par l'adaptateur interne
// puis par le sérialiseur de cookie signé de Better Auth, pour produire
// exactement le même cookie que ses propres points d'entrée — plutôt que de
// réimplémenter sa signature.
async function openSession(res, userId) {
  const auth = await getAuth();
  const ctx = await auth.$context;
  const { serializeSignedCookie } = await import("better-call");

  const session = await ctx.internalAdapter.createSession(String(userId));
  const definition = ctx.authCookies.sessionToken;
  const cookie = await serializeSignedCookie(definition.name, session.token, ctx.secret, {
    ...definition.attributes,
    maxAge: ctx.sessionConfig.expiresIn,
  });
  res.append("Set-Cookie", cookie);
  return session;
}

async function closeSession(req, res) {
  const auth = await getAuth();
  try {
    const response = await auth.api.signOut({ headers: toHeaders(req), asResponse: true });
    forwardCookies(res, response.headers);
  } catch (e) {
    /* pas de session à fermer */
  }
}

module.exports = { toHeaders, forwardCookies, currentSession, openSession, closeSession };
