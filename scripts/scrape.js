"use strict";

// Scrape les expositions des sites de musées (hors « Que Faire à Paris »).
// Insère en status="draft" (file de validation admin). Port de scripts/scrape.py.
//
// Usage :
//   npm run scrape                          # dry-run : affiche, n'écrit rien
//   npm run scrape -- --commit              # écrit en base (brouillons)
//   npm run scrape -- --museum musee-du-louvre --commit

const { Op } = require("sequelize");
const { sequelize, Museum, Exposition } = require("../src/models");
const { findDuplicateExpo } = require("../src/lib/dedup");
const { cleanValue, coerceUrl } = require("../src/lib/values");
const { toSlug } = require("../src/lib/slug");
const { SCRAPERS } = require("../src/scrapers");

function fmtDate(iso) {
  if (!iso) return null;
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

async function uniqueSlug(title, extId) {
  const b = toSlug(title).slice(0, 200) || "expo";
  let slug = b;
  let n = 2;
  for (;;) {
    const clash = await Exposition.findOne({ where: { slug, external_id: { [Op.ne]: extId } } });
    if (!clash) return slug;
    slug = `${b}-${n}`;
    n += 1;
  }
}

async function upsert(museum, item) {
  const extId = `scrap:${museum.slug}:${item.ext_key}`;
  let expo = await Exposition.findOne({ where: { external_id: extId } });
  if (!expo) {
    expo = await findDuplicateExpo(Exposition, {
      title: item.title,
      museumId: museum.id,
      venueName: museum.name,
      dateStart: item.date_start,
    });
  }
  let state = "updated";
  if (!expo) {
    expo = Exposition.build({
      external_id: extId,
      slug: await uniqueSlug(item.title, extId),
      source: "scraping",
      status: "draft",
    });
    state = "created";
  }

  expo.title = item.title;
  expo.description = cleanValue(item.description);
  expo.url = coerceUrl(item.url);
  expo.image_url = coerceUrl(item.image_url);
  expo.date_start = item.date_start || null;
  expo.date_end = item.date_end || null;
  expo.museum_id = museum.id;
  expo.venue_name = cleanValue(museum.name);
  expo.address = cleanValue(museum.address);
  const fa = museum.free_access_list;
  if (fa.includes("gratuit_tous") || fa.includes("permanent")) expo.price_category = "gratuit_tous";
  else if (fa.includes("gratuit_26")) expo.price_category = "gratuit_26";
  else expo.price_category = "gratuit_tous";
  await expo.save();
  return state;
}

function parseArgs() {
  const args = process.argv.slice(2);
  const only = args.includes("--museum") ? args[args.indexOf("--museum") + 1] : null;
  const commit = args.includes("--commit");
  return { only, commit };
}

async function run() {
  await sequelize.authenticate();
  await sequelize.sync();
  const { only, commit } = parseArgs();

  const targets = [];
  for (const [slug, fn] of Object.entries(SCRAPERS)) {
    if (only && slug !== only) continue;
    const museum = await Museum.findOne({ where: { slug } });
    if (!museum) {
      console.log(`⚠ Musée introuvable en base : ${slug}`);
      continue;
    }
    if (!museum.expos_url) {
      console.log(`⚠ Pas d'expos_url pour ${museum.name} - ignoré.`);
      continue;
    }
    targets.push([museum, fn]);
  }

  if (!targets.length) {
    console.log("Aucun musée à scraper.");
    await sequelize.close();
    return;
  }

  for (const [museum, fn] of targets) {
    console.log(`\n→ ${museum.name}  (${museum.expos_url})`);
    let items;
    try {
      items = await fn(museum);
    } catch (e) {
      console.log(`  ✗ Erreur scraping : ${e.message}`);
      continue;
    }
    console.log(`  ${items.length} exposition(s) trouvée(s).`);

    let created = 0;
    let updated = 0;
    for (const it of items) {
      const period =
        [fmtDate(it.date_start), fmtDate(it.date_end)].filter(Boolean).join(" → ") || "dates ?";
      const tags = (it.tags || []).join(", ");
      console.log(`   • ${it.title}  [${period}]  ${tags ? "- " + tags : ""}`);
      if (commit) {
        const state = await upsert(museum, it);
        if (state === "created") created += 1;
        else updated += 1;
      }
    }
    if (commit) console.log(`  ✓ ${created} créées (draft), ${updated} mises à jour.`);
  }

  if (!commit) console.log("\n(dry-run - rien n'a été écrit. Relance avec --commit pour enregistrer.)");
  await sequelize.close();
}

run().catch((e) => {
  console.error("✗ Scrape échoué :", e);
  process.exit(1);
});
