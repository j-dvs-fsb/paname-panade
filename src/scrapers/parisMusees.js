"use strict";

// Scraper générique de la plateforme « Paris Musées » (Drupal), deux générations
// de thème : ancien (.showcase) et récent (.card). Port de scripts/scrapers/paris_musees.py.

const base = require("./base");
const { todayIso } = require("../lib/dates");

const ACTIVITY_CATS = new Set([
  "visite", "visites", "atelier", "ateliers", "evenement", "evenements",
  "événement", "événements", "promenade", "spectacle", "conference", "conférence",
]);

function isActivity(tags) {
  return tags.some((t) => ACTIVITY_CATS.has(t.trim().toLowerCase()));
}

function iso(value) {
  if (!value) return null;
  const s = String(value).slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : null;
}

async function description(url) {
  try {
    return base.longestParagraph(await base.fetchText(url));
  } catch (e) {
    return null;
  }
}

// Ancien thème : .showcase
function parseShowcase($, card) {
  const c = $(card);
  let a = c.find("p.title a").first();
  if (!a.length) a = c.find("a[href]").first();
  if (!a.length) return null;
  const img = c.find("figure img").first();
  const sub = c.find("p.author").first();
  return {
    href: a.attr("href") || "",
    title: a.text().replace(/\s+/g, " ").trim(),
    subtitle: sub.length ? sub.text().replace(/\s+/g, " ").trim() : null,
    image: img.length ? img.attr("src") : null,
    date_start: iso(c.find("span.date-display-start").attr("content")),
    date_end: iso(c.find("span.date-display-end").attr("content")),
    tags: c.find("p.category").map((i, el) => $(el).text().replace(/\s+/g, " ").trim()).get(),
  };
}

// Thème récent : .card / a.card-link
function parseCard($, card) {
  const c = $(card);
  let a = c.find("a.card-link").first();
  if (!a.length) a = c.find("a[href]").first();
  const title = c.find(".card-title").first();
  if (!a.length || !title.length) return null;
  const img = c.find(".card-figure img").first();
  const sub = c.find(".card-subtitle").first();
  const cat = c.find(".meta-category").first();
  const times = c.find("time[datetime]");
  return {
    href: a.attr("href") || "",
    title: title.text().replace(/\s+/g, " ").trim(),
    subtitle: sub.length ? sub.text().replace(/\s+/g, " ").trim() : null,
    image: img.length ? img.attr("src") : null,
    date_start: times.length ? iso($(times[0]).attr("datetime")) : null,
    date_end: times.length > 1 ? iso($(times[times.length - 1]).attr("datetime")) : null,
    tags: cat.length ? [cat.text().replace(/\s+/g, " ").trim()] : [],
  };
}

async function scrape(museum) {
  const site = base.siteBase(museum.expos_url);
  const $ = base.soup(await base.fetchText(museum.expos_url));
  const today = todayIso();

  let cards = $(".showcase").toArray();
  let parse = parseShowcase;
  if (!cards.length) {
    cards = $(".card").toArray();
    parse = parseCard;
  }

  const items = [];
  const seen = new Set();
  for (const card of cards) {
    const raw = parse($, card);
    if (!raw || !raw.href || !raw.title) continue;
    if (!raw.date_start || isActivity(raw.tags)) continue;
    if (raw.date_end && raw.date_end < today) continue; // passée
    if (seen.has(raw.href)) continue;
    seen.add(raw.href);

    const url = base.absolute(site, raw.href);
    items.push({
      title: raw.title,
      subtitle: raw.subtitle,
      description: (await description(url)) || raw.subtitle,
      url,
      image_url: base.absolute(site, raw.image),
      date_start: raw.date_start,
      date_end: raw.date_end,
      tags: raw.tags.filter(Boolean),
      ext_key: raw.href.replace(/\/+$/, "").split("/").pop(),
    });
  }
  return items;
}

module.exports = { scrape };
