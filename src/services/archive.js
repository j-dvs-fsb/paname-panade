"use strict";

// Range les expos terminées : statut « archived ». Elles disparaissent du
// site (listes, pages musée, carte, sitemap, fiche en 410) mais restent en
// base, parce que les visites et favoris des utilisateurs pointent dessus
// (une suppression les effacerait en cascade).
//
// Le statut suit les dates dans les deux sens : une expo prolongée (date de
// fin repoussée par la synchro ou dans l'admin) redevient publiée.
// « archived » n'est jamais posé à la main : c'est ce qui rend le retour sûr.

const { Op } = require("sequelize");
const { Exposition } = require("../models");
const { todayIso } = require("../lib/dates");

async function archivePastExpos(today = todayIso()) {
  const [archived] = await Exposition.update(
    { status: "archived" },
    {
      where: {
        status: "published",
        date_end: { [Op.lt]: today },
        [Op.or]: [{ source: null }, { source: { [Op.ne]: "permanent" } }],
      },
    }
  );
  const [restored] = await Exposition.update(
    { status: "published" },
    { where: { status: "archived", date_end: { [Op.gte]: today } } }
  );
  return { archived, restored };
}

const SIX_HOURS = 6 * 60 * 60 * 1000;

// Au démarrage puis toutes les 6 heures : une expo finie hier soir quitte le
// site dans la matinée même sans redémarrage. Les requêtes publiques filtrent
// de toute façon sur les dates : ce rangement n'est pas la seule barrière.
function scheduleArchiving(log = console.log) {
  const run = () =>
    archivePastExpos()
      .then(({ archived, restored }) => {
        if (archived || restored) log(`[archives] ${archived} expo(s) terminée(s) archivée(s), ${restored} prolongée(s) republiée(s).`);
      })
      .catch((err) => console.error("[archives] échec :", err.message));
  run();
  const timer = setInterval(run, SIX_HOURS);
  timer.unref();
  return timer;
}

module.exports = { archivePastExpos, scheduleArchiving };
