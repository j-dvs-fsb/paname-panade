"use strict";

const { toSlug } = require("./slug");

// Clé de comparaison insensible casse/accents/ponctuation.
function normKey(value) {
  return toSlug(value);
}

// Cherche une exposition équivalente (même nom normalisé + même musée - ou même
// lieu si pas de musée - + même date de début). Port de utils.py:find_duplicate_expo.
async function findDuplicateExpo(Exposition, { title, museumId, venueName, dateStart, excludeId } = {}) {
  const key = normKey(title);
  if (!key) return null;

  const where = {};
  where.museum_id = museumId != null ? museumId : null;
  where.date_start = dateStart != null ? dateStart : null;

  const candidates = await Exposition.findAll({ where });
  for (const e of candidates) {
    if (excludeId && e.id === excludeId) continue;
    if (normKey(e.title) !== key) continue;
    if (museumId == null && normKey(e.venue_name) !== normKey(venueName)) continue;
    return e;
  }
  return null;
}

// Identifiant local pour un musée hors dataset IDF : « LOC-0001 »…
function nextLocalMuseumId(existingIds) {
  const nums = [];
  for (const x of existingIds) {
    if (!x) continue;
    const m = /^LOC-(\d+)$/.exec(x);
    if (m) nums.push(parseInt(m[1], 10));
  }
  const n = nums.length ? Math.max(...nums) + 1 : 1;
  return "LOC-" + String(n).padStart(4, "0");
}

module.exports = { normKey, findDuplicateExpo, nextLocalMuseumId };
