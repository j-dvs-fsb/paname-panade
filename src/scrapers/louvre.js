"use strict";

// Scraper du musée du Louvre (site Next.js : expositions dans __NEXT_DATA__).
// On ne garde que les expositions EN COURS et physiquement au Louvre.
// Port de scripts/scrapers/louvre.py.

const base = require("./base");
const { htmlToText } = require("../lib/text");

const SITE = "https://www.louvre.fr";
const IMG_HOST = "https://api-www.louvre.fr";

function image(img) {
  if (!img || typeof img !== "object") return null;
  const hashes = img.hashes || {};
  for (const w of [1200, 1080, 828, 750, 640]) {
    const url = hashes[`w${w}_3_2`];
    if (url) return url;
  }
  const path = img.fallback || img.path;
  return path ? base.absolute(IMG_HOST, path) : null;
}

// Parcourt récursivement, collecte les objets {type == wantedType}.
function walkType(node, type, out = []) {
  if (Array.isArray(node)) {
    for (const v of node) walkType(v, type, out);
  } else if (node && typeof node === "object") {
    if (node.type === type) out.push(node);
    for (const v of Object.values(node)) walkType(v, type, out);
  }
  return out;
}

// Collecte les valeurs string trouvées à la clé `key`.
function walkKey(node, key, out = []) {
  if (Array.isArray(node)) {
    for (const v of node) walkKey(v, key, out);
  } else if (node && typeof node === "object") {
    for (const [k, v] of Object.entries(node)) {
      if (k === key && typeof v === "string") out.push(v);
      walkKey(v, key, out);
    }
  }
  return out;
}

function isCurrentOnsite(tags) {
  const low = tags.map((t) => t.toLowerCase());
  if (!low.some((t) => t.startsWith("en cours"))) return false;
  if (low.some((t) => t.includes("ailleurs"))) return false; // hors les murs
  return true;
}

async function fetchDescription(url) {
  let data;
  try {
    data = base.nextData(await base.fetchText(url));
  } catch (e) {
    return null;
  }
  if (!data) return null;
  const page = (((data.props || {}).initialState || {}).Page) || {};
  const candidates = [];
  for (const raw of walkKey(page, "html")) {
    if (raw.includes("{{")) continue;
    const clean = raw.replace(/<\?xml[^>]*\?>/g, "");
    const txt = htmlToText(clean);
    if (txt) candidates.push(txt);
  }
  return candidates.length ? candidates.reduce((a, b) => (b.length > a.length ? b : a)) : null;
}

async function scrape(museum) {
  const data = base.nextData(await base.fetchText(museum.expos_url));
  if (!data) return [];

  const items = [];
  for (const e of walkType(data, "Exposition")) {
    const title = (e.title || "").trim();
    const link = e.link || {};
    const urlPath = typeof link === "object" ? link.url : link;
    if (!title || !urlPath) continue;

    const tags = (e.tags || [])
      .filter((t) => t && typeof t === "object")
      .map((t) => (t.label || "").trim());
    if (!isCurrentOnsite(tags)) continue;

    const [dateStart, dateEnd] = base.parseFrenchDate(e.date);
    const url = base.absolute(SITE, urlPath);
    const subtitle = (e.subtitle || "").trim() || null;

    items.push({
      title,
      subtitle,
      description: (await fetchDescription(url)) || subtitle,
      url,
      image_url: image(e.image || {}),
      date_start: dateStart,
      date_end: dateEnd,
      tags,
      ext_key: urlPath.replace(/\/+$/, "").split("/").pop(),
    });
  }
  return items;
}

module.exports = { scrape };
