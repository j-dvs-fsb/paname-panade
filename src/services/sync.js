"use strict";

// Synchronise les expositions gratuites depuis l'API « Que Faire à Paris ? ».
// Source : https://opendata.paris.fr — dataset que-faire-a-paris- (Opendatasoft v2.1).
// Port de scripts/sync_data.py.

const { Op } = require("sequelize");
const { Museum, Exposition } = require("../models");
const { htmlToText } = require("../lib/text");
const { cleanValue, coerceUrl } = require("../lib/values");
const { findDuplicateExpo } = require("../lib/dedup");
const { toSlug } = require("../lib/slug");

const API =
  "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/que-faire-a-paris-/records";
const PAGE = 100;

function parseDate(value) {
  if (!value) return null;
  const s = String(value).slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : null;
}

async function fetchRecords(limit) {
  const records = [];
  let offset = 0;
  const where = 'price_type="gratuit" and qfap_tags like "Expo"';
  while (records.length < limit) {
    const params = new URLSearchParams({
      where,
      limit: String(Math.min(PAGE, limit - records.length)),
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

function mapReservation(accessType) {
  const a = (accessType || "").trim().toLowerCase();
  if (a.startsWith("oblig")) return "obligatoire";
  if (a.startsWith("conseil")) return "conseillee";
  return "non_necessaire";
}

// Le flux fournit parfois « exemple.fr/billetterie » sans schéma : on préfixe.
// Tout ce qui n'est pas une URL http(s) exploitable devient null — pas de
// bouton plutôt qu'un lien mort.
function cleanLink(url) {
  return coerceUrl(url);
}

function matchMuseum(rec, museums) {
  const place = (rec.address_name || "").toLowerCase();
  if (!place) return null;
  for (const m of museums) {
    const key = m.name.split("—")[0].split("(")[0].trim().toLowerCase();
    if (key && (place.includes(key) || key.includes(place))) return m;
  }
  return null;
}

async function uniqueSlug(title, extId) {
  const base = toSlug(title).slice(0, 200) || "expo";
  let slug = base;
  let n = 2;
  for (;;) {
    const clash = await Exposition.findOne({
      where: { slug, external_id: { [Op.ne]: extId } },
    });
    if (!clash) return slug;
    slug = `${base}-${n}`;
    n += 1;
  }
}

async function runSync({ limit = 200 } = {}) {
  const records = await fetchRecords(limit);
  const museums = await Museum.findAll();

  let created = 0;
  let updated = 0;
  for (const rec of records) {
    const extId = String(rec.id || rec.recordid || "");
    const title = rec.title;
    if (!title) continue;

    const museum = matchMuseum(rec, museums);
    const museumId = museum ? museum.id : null;
    const venue = rec.address_name || null;
    const dateStart = parseDate(rec.date_start);

    let expo = null;
    if (extId) expo = await Exposition.findOne({ where: { external_id: extId } });
    if (!expo) {
      expo = await findDuplicateExpo(Exposition, {
        title,
        museumId,
        venueName: venue,
        dateStart,
      });
    }
    if (!expo) {
      const slug = await uniqueSlug(title, extId);
      expo = Exposition.build({ slug, external_id: extId, source: "que-faire-a-paris" });
      created += 1;
    } else {
      updated += 1;
    }

    expo.title = title;
    expo.description =
      htmlToText(rec.description) || htmlToText(rec.lead_text) || "";
    expo.date_start = dateStart;
    expo.date_end = parseDate(rec.date_end);
    expo.schedule = cleanValue(htmlToText(rec.date_description));
    expo.url = coerceUrl(rec.url);
    expo.image_url = coerceUrl(rec.cover_url);
    expo.price_type = "gratuit";
    expo.price_category = "gratuit_tous";
    expo.venue_name = cleanValue(rec.address_name);
    expo.address = cleanValue(rec.address_street);
    expo.postal_code = cleanValue(rec.address_zipcode);
    const geo = rec.lat_lon || {};
    expo.lat = geo.lat != null ? geo.lat : null;
    expo.lon = geo.lon != null ? geo.lon : null;
    expo.reservation = mapReservation(rec.access_type);
    expo.reservation_url = cleanLink(rec.access_link);
    if (museumId) expo.museum_id = museumId;

    await expo.save();
  }
  return { created, updated };
}

module.exports = { runSync, fetchRecords, parseDate, mapReservation, cleanLink, matchMuseum };
