"use strict";

// Une seule règle, partagée par les requêtes (SQL) et par les templates (JS),
// pour décider si une expo se montre au public :
//   - publiée ;
//   - collection permanente : toujours ;
//   - sinon, date de fin aujourd'hui ou plus tard ;
//   - sans date de fin : seulement si elle a commencé il y a moins de
//     OPEN_ENDED_DAYS jours (« à partir du… ») ;
//   - sans aucune date : jamais, on ne peut pas savoir si elle est finie.
// Les expos terminées passent en statut « archived » (services/archive.js) :
// elles restent en base pour l'historique des visiteurs (expos faites, avis).

const { Op } = require("sequelize");
const { todayIso } = require("./dates");

const OPEN_ENDED_DAYS = 120;

function isoDaysAgo(days, today = todayIso()) {
  const [y, m, d] = today.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d - days));
  return t.toISOString().slice(0, 10);
}

function day(value) {
  return value ? String(value).slice(0, 10) : null;
}

// Vrai si les dates de l'expo la rendent visible aujourd'hui (le statut à part).
function isCurrent(expo, today = todayIso()) {
  if (expo.source === "permanent") return true;
  const end = day(expo.date_end);
  if (end) return end >= today;
  const start = day(expo.date_start);
  return !!start && start >= isoDaysAgo(OPEN_ENDED_DAYS, today);
}

function isVisible(expo, today = todayIso()) {
  return expo.status === "published" && isCurrent(expo, today);
}

// Équivalent SQL de isVisible, à fusionner dans un `where` Sequelize.
function visibleWhere(extra = {}, today = todayIso()) {
  return {
    status: "published",
    [Op.and]: [
      {
        [Op.or]: [
          { source: "permanent" },
          { date_end: { [Op.gte]: today } },
          { date_end: null, date_start: { [Op.gte]: isoDaysAgo(OPEN_ENDED_DAYS, today) } },
        ],
      },
    ],
    ...extra,
  };
}

module.exports = { OPEN_ENDED_DAYS, isCurrent, isVisible, visibleWhere, isoDaysAgo };
