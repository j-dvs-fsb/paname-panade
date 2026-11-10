"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { isCurrent, isVisible, isoDaysAgo } = require("../src/lib/visibility");

const TODAY = "2026-11-09";

test("une expo finie hier n'est plus visible, celle qui finit aujourd'hui l'est encore", () => {
  assert.equal(isCurrent({ date_end: "2026-11-08" }, TODAY), false);
  assert.equal(isCurrent({ date_end: "2026-11-09" }, TODAY), true);
  assert.equal(isCurrent({ date_end: "2027-01-31", date_start: "2026-10-01" }, TODAY), true);
});

test("une collection permanente reste visible sans dates", () => {
  assert.equal(isCurrent({ source: "permanent" }, TODAY), true);
});

test("une expo sans aucune date n'est jamais montrée", () => {
  assert.equal(isCurrent({ source: "que-faire-a-paris" }, TODAY), false);
});

test("« à partir du… » sans date de fin : visible 120 jours après le début", () => {
  assert.equal(isCurrent({ date_start: isoDaysAgo(119, TODAY) }, TODAY), true);
  assert.equal(isCurrent({ date_start: isoDaysAgo(121, TODAY) }, TODAY), false);
  assert.equal(isCurrent({ date_start: "2027-02-01" }, TODAY), true);
});

test("seules les expos publiées sont visibles", () => {
  assert.equal(isVisible({ status: "archived", date_end: "2027-01-01" }, TODAY), false);
  assert.equal(isVisible({ status: "draft", date_end: "2027-01-01" }, TODAY), false);
  assert.equal(isVisible({ status: "published", date_end: "2027-01-01" }, TODAY), true);
});

test("isoDaysAgo traverse les mois et les années", () => {
  assert.equal(isoDaysAgo(10, "2026-01-05"), "2025-12-26");
});
