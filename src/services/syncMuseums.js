"use strict";

// Synchronise / enrichit les musées depuis le dataset officiel Île-de-France
// (data.iledefrance.fr, ~50 musées parisiens avec coordonnées GPS).
// Port de scripts/sync_museums.py.

const { Op } = require("sequelize");
const { Museum } = require("../models");
const { toSlug } = require("../lib/slug");

const API =
  "https://data.iledefrance.fr/api/explore/v2.1/catalog/datasets/liste_des_musees_franciliens/records";
const PAGE = 100;

// Rapprochement des 8 musées curés (seed) avec leur fiche officielle.
const MANUAL_MATCH = {
  M5050: "centre-pompidou",
  M1114: "maison-de-victor-hugo",
  M1104: "musee-carnavalet-histoire-de-paris",
  M1101: "musee-d-art-moderne-de-paris-mam",
  M5060: "musee-d-orsay",
  M5031: "musee-du-louvre",
  M5055: "musee-du-quai-branly-jacques-chirac",
  M1111: "petit-palais-musee-des-beaux-arts-de-la-ville-de-paris",
};

async function fetchRecords() {
  const records = [];
  let offset = 0;
  for (;;) {
    const params = new URLSearchParams({
      where: 'departement="Paris"',
      limit: String(PAGE),
      offset: String(offset),
    });
    const resp = await fetch(`${API}?${params}`, { signal: AbortSignal.timeout(30000) });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    const results = data.results || [];
    if (!results.length) break;
    records.push(...results);
    offset += results.length;
    if (offset >= (data.total_count || 0)) break;
  }
  return records;
}

function arrondissementFromCp(cp) {
  if (cp && cp.length === 5 && cp.startsWith("75")) {
    const n = parseInt(cp.slice(3, 5), 10);
    if (n >= 1 && n <= 20) return n === 1 ? "Paris 1er" : `Paris ${n}e`;
  }
  return null;
}

function cleanName(name) {
  name = (name || "").trim();
  return name ? name[0].toUpperCase() + name.slice(1) : name;
}

function cleanUrl(url) {
  if (!url) return null;
  url = url.trim().replace(/\/+$/, "");
  if (!url) return null;
  return url.startsWith("http") ? url : "https://" + url;
}

async function uniqueSlug(base, museumId = null) {
  base = toSlug(base).slice(0, 150) || "musee";
  let slug = base;
  let n = 2;
  for (;;) {
    const where = { slug };
    if (museumId != null) where.id = { [Op.ne]: museumId };
    if (!(await Museum.findOne({ where }))) return slug;
    slug = `${base}-${n}`;
    n += 1;
  }
}

async function runSyncMuseums() {
  const records = await fetchRecords();
  let created = 0;
  let enriched = 0;

  for (const rec of records) {
    const mid = rec.identifiant_museofile;
    const officialName = cleanName(rec.nom_officiel_du_musee);
    if (!mid || !officialName) continue;

    const lat = rec.latitude;
    const lon = rec.longitude;
    const cp = rec.code_postal;
    const addr = [rec.adresse, cp, "Paris"].filter(Boolean).join(" ") || null;
    const website = cleanUrl(rec.url);
    const arr = arrondissementFromCp(cp);

    let museum = await Museum.findOne({ where: { museofile_id: mid } });
    if (!museum && MANUAL_MATCH[mid]) {
      museum = await Museum.findOne({ where: { slug: MANUAL_MATCH[mid] } });
    }

    if (museum) {
      // Enrichissement : on ne touche pas à la curation éditoriale existante.
      museum.museofile_id = mid;
      if (lat != null && museum.lat == null) museum.lat = lat;
      if (lon != null && museum.lon == null) museum.lon = lon;
      if (addr && !museum.address) museum.address = addr;
      if (arr && !museum.arrondissement) museum.arrondissement = arr;
      if (website && !museum.website) museum.website = website;
      enriched += 1;
    } else {
      museum = Museum.build({
        slug: await uniqueSlug(officialName),
        museofile_id: mid,
        name: officialName,
        address: addr,
        arrondissement: arr,
        website,
        lat,
        lon,
      });
      created += 1;
    }
    await museum.save();
  }
  return { created, enriched, total: await Museum.count() };
}

module.exports = { runSyncMuseums };
