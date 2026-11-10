"use strict";

// Lieux du collecteur dont l'identifiant ne correspond pas au slug du musée
// sur le site. Les autres se retrouvent seuls : même slug, ou slug du site qui
// commence par l'identifiant (le collecteur coupe ses identifiants à 60 signes).
//
// Clé : identifiant du lieu dans le collecteur. Valeur : slug du musée sur le site.
module.exports = {
  "musee-d-art-moderne-de-la-ville-de-paris": "musee-d-art-moderne-de-paris-mam",
  "musee-national-d-art-moderne-centre-national-d-art-et-de-cul": "centre-pompidou",
};
