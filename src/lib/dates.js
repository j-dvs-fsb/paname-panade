"use strict";

const FR_MONTHS = [
  "janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre",
];

// Les colonnes DATEONLY de Sequelize renvoient une chaîne "YYYY-MM-DD".
// Ces helpers manipulent donc des chaînes ISO (ou des Date), jamais d'heure.

function toDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  const s = String(value).slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

// date -> "15 avril 2026". Renvoie "" si vide.
function formatFrDate(value) {
  const d = toDate(value);
  if (!d) return "";
  return `${d.getDate()} ${FR_MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

// "YYYY-MM-DD" du jour, pour comparer des DATEONLY sans souci de fuseau.
function todayIso() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

module.exports = { FR_MONTHS, formatFrDate, toDate, todayIso };
