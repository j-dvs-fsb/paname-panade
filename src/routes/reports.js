"use strict";

// Signalements d'erreur sur une fiche et suggestions d'expositions.
//
// Anti-spam volontairement léger : un pot de miel (champ masqué qu'un humain
// ne remplit jamais) et une limite par IP. Pas de captcha : il coûterait plus
// de signalements perdus qu'il n'éviterait de spam, sur un volume pareil.

const express = require("express");

const { Exposition, Report, REPORT_PROBLEM_LABELS } = require("../models");
const { reportLimiter } = require("../middleware/rateLimit");
const { urlFor } = require("../lib/urls");
const { cleanValue } = require("../lib/values");
const seo = require("../lib/seo");

const router = express.Router();

const MIN_MESSAGE = 10;
const MAX_MESSAGE = 2000;

// Un robot remplit tous les champs du formulaire, y compris celui qu'aucun
// humain ne voit. S'il est rempli, on répond comme si tout allait bien : pas
// de retour exploitable pour ajuster le script.
function isBot(body) {
  return !!cleanValue(body.website);
}

function readSubmission(body) {
  const message = String(body.message || "").trim().slice(0, MAX_MESSAGE);
  const email = cleanValue(body.email);
  return {
    message,
    email: email && email.includes("@") ? email.slice(0, 255) : null,
    problem: Object.prototype.hasOwnProperty.call(REPORT_PROBLEM_LABELS, body.problem)
      ? body.problem
      : "autre",
  };
}

// --- Signaler une erreur sur une fiche ---
router.post("/exposition/:id/signaler", reportLimiter, async (req, res) => {
  const expo = await Exposition.findByPk(req.params.id);
  if (!expo) return res.status(404).render("404.njk");
  const back = urlFor("main.expo_detail", { slug: expo.slug });

  if (isBot(req.body)) return res.redirect(back);

  const { message, email, problem } = readSubmission(req.body);
  if (message.length < MIN_MESSAGE) {
    req.flash("danger", "Décris le problème en quelques mots (10 caractères minimum).");
    return res.redirect(back);
  }

  await Report.create({ kind: "erreur", exposition_id: expo.id, problem, message, email });
  req.flash("success", "Merci ! Le signalement est enregistré, on vérifie ça.");
  res.redirect(back);
});

// --- Suggérer une expo / une reco ---
router.get("/suggerer", (req, res) => {
  res.locals.meta = seo.pageMeta(req, {
    title: "Suggérer une expo",
    description:
      "Une expo gratuite manque au site ? Une bonne adresse à partager ? " +
      "Envoie ta suggestion, elle sera lue et ajoutée si elle colle.",
    url: urlFor("main.suggest"),
  });
  res.render("suggest.njk", { form: {} });
});

router.post("/suggerer", reportLimiter, async (req, res) => {
  if (isBot(req.body)) return res.redirect(urlFor("main.suggest"));

  const { message, email } = readSubmission(req.body);
  if (message.length < MIN_MESSAGE) {
    req.flash("danger", "Décris ta suggestion en quelques mots (10 caractères minimum).");
    return res.status(400).render("suggest.njk", { form: req.body });
  }

  await Report.create({ kind: "suggestion", message, email });
  req.flash("success", "Merci ! Ta suggestion est bien arrivée.");
  res.redirect(urlFor("main.suggest"));
});

module.exports = router;
