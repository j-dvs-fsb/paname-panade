"use strict";

// Une vraie photo par musée, pour la fiche du musée et pour ses collections
// permanentes. Avant, ces visuels étaient des icônes de site (favicon,
// apple-touch-icon de 180 px, favicons Google de 128 px) étirées à la taille
// d'une carte : d'où des images floues.
//
// Chaque adresse a été relevée le 2026-10-29 sur le site officiel du musée
// (image de partage, ou plus grande image de la page d'accueil) ou sur le
// portail Paris Musées pour les musées de la Ville, puis vérifiée une à une à
// l'œil (pas de portrait, d'affiche d'événement, de logo ni de texture) :
// au moins 800 px de large et moins de 5 Mo (limite de services/imageCache).
// Un musée absent de cette liste garde le visuel neutre du site, net, plutôt
// qu'une icône floue (cf. lib/values.js : isIconUrl).
//
// Clé : slug du musée ; `museofile` sert de repli si le slug a changé en base.

module.exports = {
  "musee-cernuschi-musee-des-arts-de-l-asie-de-la-ville-de-paris": {
    museofile: "M1106",
    url: "https://www.parismusees.paris.fr/sites/default/files/2020-05/cernuschi_dsc9161.jpg",
  },  // 1440x900
  "musee-de-la-liberation-de-paris-musee-du-general-leclerc-musee-jean-moulin": {
    museofile: "M1109",
    url: "https://www.parismusees.paris.fr/sites/default/files/2019-09/1L3A6807.jpg",
  },  // 2500x1667
  "musee-bourdelle": {
    museofile: "M1103",
    url: "https://www.bourdelle.paris.fr/sites/default/files/styles/metatag/public/2025-02/pa23_musee_bourdelle_2047_hd_banniere_web.jpg?h=7442ea1f&itok=iPArdiZ7",
  },  // 1200x630
  "musee-carnavalet-histoire-de-paris": {
    museofile: "M1104",
    url: "https://www.parismusees.paris.fr/sites/default/files/2019-01/Mus%C3%A9e%20Carnavalet%20%C2%A9%20Fran%C3%A7ois%20Grinberg.jpg",
  },  // 1920x1278
  "musee-de-la-chasse-et-de-la-nature": {
    museofile: "M0363",
    url: "https://www.chassenature.org/storage/407/L1970035_email.jpg",
  },  // 1500x1003
  "musee-de-la-vie-romantique": {
    museofile: "M1113",
    url: "https://www.parismusees.paris.fr/sites/default/files/2026-02/C69A5739.JPG",
  },  // 2000x1333
  "musee-des-arts-et-metiers": {
    museofile: "M5065",
    url: "https://www.arts-et-metiers.net/sites/arts-et-metiers/files/styles/homepage/public/2026-07/Caroussel%20Vacances%20scolaires_0.png.jpeg?h=d1cb525d&itok=jvZBBXkL",
  },  // 1920x1080
  "musee-du-louvre": {
    museofile: "M5031",
    url: "https://api-www.louvre.fr/sites/default/files/2021-01/cour-napoleon-et-pyramide_1.jpg",
  },  // 3000x1998, cour Napoléon
  "musee-gustave-moreau": {
    museofile: "M5041",
    url: "https://musee-moreau.fr/sites/moreau/files/styles/w1920_extra_wide/public/2026-08/Template%20bandeau%20site%20internet.png?itok=qOK8DITc",
  },  // 1920x588
  "musee-yves-saint-laurent-paris": {
    museofile: "M1204",
    url: "https://s3-eu-west-1.amazonaws.com/musee-ysl-paris/images/_1200x630_crop_center-center_82/D4A8302_A2_Def_170913_123352.jpg",
  },  // 1200x630
  "palais-galliera-musee-de-la-mode-et-de-la-ville-de-paris": {
    museofile: "M1108",
    url: "https://www.parismusees.paris.fr/sites/default/files/2020-10/PalaisGalliera.jpg",
  },  // 3024x2868
  "petit-palais-musee-des-beaux-arts-de-la-ville-de-paris": {
    museofile: "M1111",
    url: "https://www.parismusees.paris.fr/sites/default/files/2019-01/PetitPalaisNocturne_BenjaminSoligny.jpg",
  },  // 2000x1538
};
