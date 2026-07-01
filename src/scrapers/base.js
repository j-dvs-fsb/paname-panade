"use strict";

// Briques communes aux scrapers de sites de musées. Port de scripts/scrapers/base.py.
// Chaque scraper reçoit un Museum (avec son expos_url) et renvoie des dicts normalisés :
//   title, subtitle, description, url, image_url, date_start, date_end (ISO|null),
//   ext_key, tags[]

const cheerio = require("cheerio");

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) " +
  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36";

const MONTHS = {
  janvier: 1, février: 2, fevrier: 2, mars: 3, avril: 4, mai: 5, juin: 6,
  juillet: 7, août: 8, aout: 8, septembre: 9, octobre: 10, novembre: 11,
  décembre: 12, decembre: 12,
};
const MONTHS_RE = Object.keys(MONTHS).join("|");
const DATE_RE = new RegExp(`(\\d{1,2})\\s+(${MONTHS_RE})\\.?\\s*(\\d{4})?`, "gi");

async function fetchText(url, timeout = 30000) {
  const resp = await fetch(url, {
    headers: { "User-Agent": UA },
    signal: AbortSignal.timeout(timeout),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status} pour ${url}`);
  return resp.text();
}

// Extrait le JSON __NEXT_DATA__ d'une page Next.js (null si absent).
function nextData(html) {
  const m = /<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/.exec(html);
  return m ? JSON.parse(m[1]) : null;
}

function soup(html) {
  return cheerio.load(html);
}

// Objets JSON-LD (<script type="application/ld+json">).
function jsonLd(html) {
  const out = [];
  const re = /<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/gi;
  let m;
  while ((m = re.exec(html))) {
    try {
      const data = JSON.parse(m[1]);
      if (Array.isArray(data)) out.push(...data);
      else out.push(data);
    } catch (e) {
      /* ignore JSON invalide */
    }
  }
  return out;
}

// Texte du plus long <p> (heuristique de description, best-effort).
function longestParagraph(html) {
  const $ = soup(html);
  let best = null;
  $("p").each((_, el) => {
    const t = $(el).text().replace(/\s+/g, " ").trim();
    if (!best || t.length > best.length) best = t;
  });
  return best || null;
}

function absolute(base, path) {
  if (!path) return null;
  if (path.startsWith("http")) return path;
  return base.replace(/\/+$/, "") + "/" + path.replace(/^\/+/, "");
}

function siteBase(url) {
  const u = new URL(url);
  return `${u.protocol}//${u.host}`;
}

function iso(y, m, d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${y}-${p(m)}-${p(d)}`;
}

// « 15 avril – 20 juillet 2026 » -> [ '2026-04-15', '2026-07-20' ].
// Gère « jusqu'au … » (fin seule) et « à partir du … » (début seul).
function parseFrenchDate(text) {
  if (!text) return [null, null];
  const low = text.toLowerCase();
  const matches = [...text.matchAll(DATE_RE)];
  if (!matches.length) return [null, null];

  const year = matches.map((m) => m[3]).find(Boolean);
  if (!year) return [null, null];
  const parsed = matches.map((m) => iso(m[3] || year, MONTHS[m[2].toLowerCase()], m[1]));

  if (low.includes("jusqu") || low.includes("avant")) return [null, parsed[parsed.length - 1]];
  if (low.includes("partir") || low.includes("depuis") || low.includes("dès")) return [parsed[0], null];
  if (parsed.length === 1) return [parsed[0], null];
  return [parsed[0], parsed[parsed.length - 1]];
}

module.exports = {
  UA, fetchText, nextData, soup, jsonLd, longestParagraph, absolute, siteBase, parseFrenchDate,
};
