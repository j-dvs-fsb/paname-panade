"use strict";

const slugify = require("slugify");

// Slug identique à python-slugify : l'apostrophe agit comme séparateur
// (« d'Art » -> « d-art »), contrairement au mode strict brut qui la supprime.
function toSlug(value) {
  return slugify(String(value || "").replace(/['’]/g, " "), { lower: true, strict: true });
}

module.exports = { toSlug };
