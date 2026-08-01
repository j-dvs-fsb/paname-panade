"use strict";

// Ce que coûte réellement une exposition à la personne qui regarde la page.
//
// Le site s'adresse aux moins de 26 ans : par défaut, une expo « gratuit -26 »
// s'affiche « gratuit ». Pour un visiteur connecté qui a dépassé 26 ans, ce
// serait un mensonge — on bascule sur le tarif qui s'applique vraiment.
//
// La base ne contient aucun montant (le jeu de données « Que Faire à Paris »
// n'expose qu'une catégorie de gratuité, pas de prix) : on annonce donc « plein
// tarif » et on renvoie vers la billetterie, sans inventer de chiffre.

const { PRICE_LABELS } = require("../models/labels");

// Catégories dont la gratuité (ou la réduction) dépend de l'âge.
const AGE_LIMITED = new Set(["gratuit_26", "reduit_26"]);

function isOver26(user) {
  return !!(user && user.is_authenticated && user.is_over_26);
}

// { free, badge, label, note } — `free` sert aussi au filtre « encore gratuit ».
function priceForUser(expo, user) {
  const category = expo.price_category || "gratuit_tous";
  const label = PRICE_LABELS[category] || PRICE_LABELS.gratuit_tous;

  if (category === "gratuit_tous") {
    return { free: true, badge: "GRATUIT", label, note: null };
  }

  if (!isOver26(user) || !AGE_LIMITED.has(category)) {
    return { free: true, badge: "GRATUIT", label, note: null };
  }

  if (category === "reduit_26") {
    return {
      free: false,
      badge: "PLEIN TARIF",
      label: "Plein tarif",
      note: "Le tarif réduit -26 ans ne s'applique plus à toi — voir la billetterie du musée.",
    };
  }

  return {
    free: false,
    badge: "PLEIN TARIF",
    label: "Plein tarif",
    note: "La gratuité -26 ans ne s'applique plus à toi — voir la billetterie du musée.",
  };
}

module.exports = { priceForUser, isOver26, AGE_LIMITED };
