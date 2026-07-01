"use strict";

// Registre des scrapers : slug de musée -> fonction scrape(museum) -> Promise<dict[]>.
// Port de scripts/scrapers/__init__.py.

const louvre = require("./louvre");
const parisMusees = require("./parisMusees");

// Musées sur la plateforme Paris Musées (même scraper générique).
const PARIS_MUSEES = [
  "musee-carnavalet-histoire-de-paris",
  "petit-palais-musee-des-beaux-arts-de-la-ville-de-paris",
  "musee-d-art-moderne-de-paris-mam",
  "maison-de-victor-hugo",
];

const SCRAPERS = { "musee-du-louvre": louvre.scrape };
for (const slug of PARIS_MUSEES) SCRAPERS[slug] = parisMusees.scrape;

module.exports = { SCRAPERS };
