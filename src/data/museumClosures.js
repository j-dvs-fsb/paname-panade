"use strict";

// Musées fermés au public (travaux, rénovation), relevés sur leur site officiel.
// Appliqué au démarrage (services/migrate.js) : la note n'est posée que si le
// musée n'en a pas déjà une, une note saisie dans l'admin n'est jamais écrasée.
// Tant qu'un musée a une note de fermeture, ses collections permanentes
// disparaissent du site ; elles reviennent dès que la note est effacée.
//
// Clé : slug du musée sur le site. `museofile` sert de repli si le slug diffère.
module.exports = {
  "centre-pompidou": {
    museofile: "M5050",
    note: "Fermé pour travaux de 2025 à 2030. Le Centre Pompidou expose hors les murs pendant ce temps.",
    source: "https://www.centrepompidou.fr/fr/",
    lu_le: "2026-11-10",
  },
};
