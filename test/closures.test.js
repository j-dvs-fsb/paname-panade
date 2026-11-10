"use strict";

// Musée fermé (Centre Pompidou) : ses collections permanentes disparaissent du
// site tant que la note de fermeture est posée, et reviennent quand elle est
// effacée. Base SQLite jetable, propre à ce fichier de test.

const fs = require("fs");
const os = require("os");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const dossier = fs.mkdtempSync(path.join(os.tmpdir(), "panade-fermetures-"));
process.env.DATABASE_URL = "sqlite:" + path.join(dossier, "test.sqlite");
delete process.env.DB_HOST;

const { sequelize, Museum, Exposition } = require("../src/models");
const { applyMuseumClosures, syncClosedCollections } = require("../src/services/migrate");
const { isVisible } = require("../src/lib/visibility");

test.before(async () => {
  await sequelize.sync();
});

test.after(async () => {
  await sequelize.close();
  fs.rmSync(dossier, { recursive: true, force: true });
});

test("Pompidou fermé : note posée, collections masquées, gratuité retirée", async () => {
  const pompidou = await Museum.create({ slug: "centre-pompidou", name: "Centre Pompidou", free_access: "gratuit_26" });
  const louvre = await Museum.create({ slug: "musee-du-louvre", name: "Musée du Louvre", free_access: "gratuit_26" });
  const coll = await Exposition.create({ slug: "collections-pompidou", title: "Collections permanentes - Centre Pompidou",
    museum_id: pompidou.id, source: "permanent", status: "published" });
  const collLouvre = await Exposition.create({ slug: "collections-louvre", title: "Collections permanentes - Louvre",
    museum_id: louvre.id, source: "permanent", status: "published" });

  const r = await applyMuseumClosures();
  assert.equal(r.notes, 1);
  await pompidou.reload();
  await coll.reload();
  await collLouvre.reload();
  assert.match(pompidou.closed_note, /2030/);
  assert.equal(pompidou.is_closed, true);
  assert.deepEqual(pompidou.free_labels, []);
  assert.equal(coll.status, "museum_closed");
  assert.equal(isVisible(coll), false);
  assert.equal(collLouvre.status, "published");

  // Relancé au démarrage suivant : rien ne bouge.
  assert.deepEqual(await applyMuseumClosures(), { notes: 0, hidden: 0, restored: 0 });
});

test("note effacée dans l'admin : la collection revient, un brouillon manuel reste brouillon", async () => {
  const musee = await Museum.create({ slug: "musee-rouvert", name: "Musée rouvert", closed_note: "Fermé pour travaux." });
  const coll = await Exposition.create({ slug: "collections-rouvert", title: "Collections", museum_id: musee.id,
    source: "permanent", status: "published" });
  const brouillon = await Exposition.create({ slug: "collections-brouillon", title: "Collections bis", museum_id: musee.id,
    source: "permanent", status: "draft" });
  await syncClosedCollections();
  await coll.reload();
  assert.equal(coll.status, "museum_closed");

  await musee.update({ closed_note: null });
  await syncClosedCollections();
  await coll.reload();
  await brouillon.reload();
  assert.equal(coll.status, "published");
  assert.equal(brouillon.status, "draft");
});
