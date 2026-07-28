"use strict";

// Détermine le "Relying Party" WebAuthn. En prod, dérivé du domaine de la requête
// (ex. paname-panade.fr) ; surchargeable via WEBAUTHN_RP_ID / WEBAUTHN_ORIGIN.
// En local : rpID=localhost, origin=http://localhost:PORT (autorisé par WebAuthn).
function rpConfig(req) {
  const rpID = process.env.WEBAUTHN_RP_ID || req.hostname;
  const origin = process.env.WEBAUTHN_ORIGIN || `${req.protocol}://${req.get("host")}`;
  return { rpID, rpName: "Paname Panade", origin };
}

module.exports = { rpConfig };
