"use strict";

// Sert les visuels d'expositions depuis notre domaine (cf. services/imageCache).
// Une source cassée ne produit jamais d'image brisée : on renvoie le
// placeholder, avec un cache court pour retenter plus tard.

const crypto = require("crypto");
const express = require("express");

const { safeUrl } = require("../lib/values");
const { verify, load } = require("../services/imageCache");

const router = express.Router();

const IMMUTABLE = "public, max-age=31536000, immutable";
const RETRY_SOON = "public, max-age=300";

// Placeholder aux couleurs du site (même motif que .card-img-placeholder).
const PLACEHOLDER = Buffer.from(
  `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="270" viewBox="0 0 400 270" role="img" aria-label="Visuel indisponible">
  <defs>
    <pattern id="h" width="20" height="20" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="20" height="20" fill="#f4f4f4"/><rect width="10" height="20" fill="#ececec"/>
    </pattern>
  </defs>
  <rect width="400" height="270" fill="url(#h)"/>
  <text x="200" y="145" text-anchor="middle" font-family="Helvetica,Arial,sans-serif"
        font-size="48" font-weight="800" fill="#9a9a9a">PP</text>
</svg>`,
  "utf-8"
);

function sendPlaceholder(res) {
  res.setHeader("Cache-Control", RETRY_SOON);
  res.type("image/svg+xml").send(PLACEHOLDER);
}

router.get("/img", async (req, res) => {
  const url = safeUrl(req.query.src);
  if (!url || !verify(url, req.query.s)) return sendPlaceholder(res);

  let image;
  try {
    image = await load(url);
  } catch (e) {
    return sendPlaceholder(res);
  }

  // L'URL source est signée et le contenu figé : le cache navigateur peut être
  // agressif. L'ETag évite de retransmettre l'image quand elle est déjà là.
  const etag = `"${crypto.createHash("sha1").update(image.buf).digest("base64url").slice(0, 22)}"`;
  res.setHeader("ETag", etag);
  res.setHeader("Cache-Control", IMMUTABLE);
  if (req.get("if-none-match") === etag) return res.status(304).end();

  res.type(image.type).send(image.buf);
});

module.exports = router;
