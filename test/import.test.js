"use strict";

// Connecteur du Panade Collector : POST /api/import.
// L'export de test (fixtures/export-collecteur.json) a été produit par le
// collecteur Python lui-même : l'empreinte recalculée ici en JavaScript doit
// être identique à la sienne.

const fs = require("fs");
const os = require("os");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const dossier = fs.mkdtempSync(path.join(os.tmpdir(), "panade-import-"));
process.env.DATABASE_URL = "sqlite:" + path.join(dossier, "test.sqlite");
process.env.PANADE_IMPORT_TOKEN = "jeton-de-test-suffisamment-long-pour-etre-accepte";
delete process.env.DB_HOST;

const { sequelize, Museum, Exposition, CollectorImport } = require("../src/models");
const { recevoir, empreinte, RETIREE } = require("../src/services/collectorImport");
const { runMigrations } = require("../src/services/migrate");
const { priceForUser } = require("../src/lib/pricing");

const BRUT = fs.readFileSync(path.join(__dirname, "fixtures", "export-collecteur.json"), "utf8");
const exportDeTest = () => JSON.parse(BRUT);
const corps = (contenu) => Buffer.from(JSON.stringify(contenu), "utf8");

// Re-signe un export modifié, comme le ferait le collecteur.
function resigner(contenu) {
  contenu.compte = {
    lieux: contenu.lieux.length,
    expositions: contenu.lieux.reduce((n, l) => n + (l.expositions || []).length, 0),
  };
  contenu.empreinte = empreinte(contenu);
  return contenu;
}

test.before(async () => {
  await sequelize.sync();
  await runMigrations();
  // Musées déjà présents sur le site (slugs réels de scripts/import-data.json).
  await Museum.create({ slug: "musee-d-art-moderne-de-paris-mam", name: "Musée d'Art Moderne de Paris" });
  await Museum.create({ slug: "musee-d-art-et-d-histoire-du-judaisme", name: "mahJ", horaires: "Saisi à la main" });
  const vr = await Museum.create({ slug: "musee-de-la-vie-romantique", name: "Musée de la Vie romantique" });
  await Exposition.create({ slug: "collections-vie-romantique", title: "Collections permanentes - Vie romantique",
    museum_id: vr.id, source: "permanent", status: "published" });
});

test.after(async () => {
  await sequelize.close();
  fs.rmSync(dossier, { recursive: true, force: true });
});

test("l'empreinte calculée en JavaScript est celle du collecteur Python", () => {
  const contenu = exportDeTest();
  assert.equal(empreinte(contenu), contenu.empreinte);
});

test("un export modifié en route est refusé et rien n'est écrit", async () => {
  const contenu = exportDeTest();
  contenu.lieux[0].expositions[0].titre = "Titre altéré";
  await assert.rejects(recevoir(corps(contenu)), (e) => e.statut === 422 && /empreinte/.test(e.message));
  assert.equal(await CollectorImport.count(), 0);
  assert.equal(await Exposition.count({ where: { source: "collecteur" } }), 0);
});

test("un export non conforme est refusé en entier", async () => {
  const contenu = exportDeTest();
  contenu.lieux[0].expositions[0].date_fin = "2020-01-01"; // fin avant le début
  await assert.rejects(recevoir(corps(resigner(contenu))), (e) => e.statut === 422 && e.details.length === 1);
  const autre = exportDeTest();
  autre.version = 2;
  await assert.rejects(recevoir(corps(resigner(autre))), (e) => e.statut === 422);
  assert.equal(await CollectorImport.count(), 0);
});

test("l'export est appliqué : musées rattachés ou créés, expos créées, doublons et « à confirmer » écartés", async () => {
  const r = await recevoir(corps(exportDeTest()), exportDeTest().empreinte);
  assert.equal(r.applique, true);
  const b = r.bilan;
  assert.deepEqual(b.musees_crees.sort(), ["bourse-de-commerce-pinault-collection", "fondation-cartier-pour-l-art-contemporain"]);
  assert.equal(b.musees_rattaches, 3); // MAM par alias, mahJ et Vie romantique par slug
  assert.equal(b.expos_creees, 3); // Remember Me, Ibrahim Mahama, parcours permanent du mahJ
  assert.deepEqual(b.non_affichees, { a_confirmer: 4 });
  assert.equal(b.doublons_ignores.length, 1); // la Vie romantique a déjà sa collection permanente

  const mahama = await Exposition.findOne({ where: { title: { [require("sequelize").Op.like]: "Ibrahim Mahama%" } } });
  assert.equal(mahama.price_category, "reduit_26");
  assert.equal(mahama.price_note, "10 € au lieu de 15 €");
  assert.equal(mahama.reservation, "inconnue");
  assert.equal(mahama.reservation_label, "Voir la billetterie du musée");
  assert.equal(mahama.status, "published");

  const parcours = await Exposition.findOne({ where: { external_id: "collecteur:13" } });
  assert.equal(parcours.source, "permanent");
  assert.equal(parcours.price_category, "gratuit_26");
  assert.equal(parcours.price_note, "Résidents de l'Union européenne, sur justificatif.");

  // Horaires : complétés quand le musée n'en avait pas, jamais écrasés.
  const cartier = await Museum.findOne({ where: { slug: "fondation-cartier-pour-l-art-contemporain" } });
  assert.match(cartier.horaires, /^Du mardi au dimanche, 11h-19h/);
  const mahj = await Museum.findOne({ where: { slug: "musee-d-art-et-d-histoire-du-judaisme" } });
  assert.equal(mahj.horaires, "Saisi à la main");
});

test("le même export renvoyé une seconde fois ne change rien", async () => {
  const avant = await Exposition.count();
  assert.deepEqual(await recevoir(corps(exportDeTest())), { deja_applique: true });
  assert.equal(await Exposition.count(), avant);
});

test("une expo qui sort de l'export est masquée, puis revient si elle y réapparaît", async () => {
  const sans = exportDeTest();
  const bourse = sans.lieux.find((l) => l.id === "bourse-de-commerce-pinault-collection");
  bourse.expositions = [];
  sans.genere_le = "2026-11-11T06:00:00Z";
  const r = await recevoir(corps(resigner(sans)));
  assert.equal(r.bilan.expos_retirees, 1);
  const remember = await Exposition.findOne({ where: { title: "Remember Me" } });
  assert.equal(remember.status, RETIREE);

  const avec = exportDeTest();
  avec.genere_le = "2026-11-12T06:00:00Z";
  await recevoir(corps(resigner(avec)));
  await remember.reload();
  assert.equal(remember.status, "published");
});

test("un tarif réduit ne s'affiche jamais « gratuit »", () => {
  const p = priceForUser({ price_category: "reduit_26", price_note: "10 € au lieu de 15 €" }, null);
  assert.equal(p.free, false);
  assert.equal(p.badge, "TARIF RÉDUIT");
  assert.equal(p.note, "10 € au lieu de 15 €");
  assert.equal(priceForUser({ price_category: "gratuit_26" }, null).badge, "GRATUIT");
});

test("le point d'entrée HTTP exige le jeton, du JSON, et répond par le bilan", async () => {
  const { createApp } = require("../src/app");
  const serveur = createApp().listen(0);
  const url = `http://127.0.0.1:${serveur.address().port}/api/import`;
  try {
    const sansJeton = await fetch(url, { method: "POST", body: "{}", headers: { "Content-Type": "application/json" } });
    assert.equal(sansJeton.status, 401);

    const auth = { Authorization: `Bearer ${process.env.PANADE_IMPORT_TOKEN}` };
    const mauvaisType = await fetch(url, { method: "POST", body: "x", headers: { ...auth, "Content-Type": "text/plain" } });
    assert.equal(mauvaisType.status, 415);

    const autre = exportDeTest();
    autre.genere_le = "2026-11-13T06:00:00Z";
    const ok = await fetch(url, {
      method: "POST",
      body: JSON.stringify(resigner(autre)),
      headers: { ...auth, "Content-Type": "application/json" },
    });
    assert.equal(ok.status, 200);
    assert.equal((await ok.json()).applique, true);
  } finally {
    serveur.close();
  }
});
