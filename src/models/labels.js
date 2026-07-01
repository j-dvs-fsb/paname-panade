"use strict";

// Conditions de gratuité d'un musée (clé stockée -> libellé). Multi-sélection.
const FREE_ACCESS_LABELS = {
  gratuit_26: "Gratuit pour les -26 ans (UE)",
  permanent: "Collections permanentes gratuites",
  premier_dimanche: "Gratuit le 1er dimanche du mois",
  gratuit_tous: "Gratuit pour tous",
};

// Catégories de prix (clé stockée -> libellé affiché).
const PRICE_LABELS = {
  gratuit_tous: "Gratuit pour tous",
  gratuit_26: "Gratuit pour les -26 ans",
  reduit_26: "Tarif réduit pour les -26 ans",
};

// Type de réservation (clé stockée -> libellé affiché).
const RESERVATION_LABELS = {
  obligatoire: "Réservation obligatoire",
  conseillee: "Réservation conseillée",
  non_necessaire: "Sans réservation",
};

module.exports = { FREE_ACCESS_LABELS, PRICE_LABELS, RESERVATION_LABELS };
