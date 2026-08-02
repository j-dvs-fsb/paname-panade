"use strict";

// Musées gratuits en permanence à Paris (liste éditoriale curée) + fonction de seed.
// Utilisé par scripts/seed.js (CLI) et par le bootstrap au démarrage.

const { Museum } = require("../models");
const { toSlug } = require("../lib/slug");

const MUSEUMS = [
  {
    name: "Musée Carnavalet - Histoire de Paris",
    arrondissement: "Paris 3e",
    address: "23 Rue de Sévigné, 75003 Paris",
    website: "https://www.carnavalet.paris.fr",
    free_access: "permanent",
    description:
      "L'histoire de Paris de la préhistoire à nos jours, dans un hôtel particulier du Marais. Collections permanentes en accès libre.",
  },
  {
    name: "Petit Palais - Musée des Beaux-Arts de la Ville de Paris",
    arrondissement: "Paris 8e",
    address: "Av. Winston Churchill, 75008 Paris",
    website: "https://www.petitpalais.paris.fr",
    free_access: "permanent",
    description:
      "Beaux-arts de l'Antiquité à 1900 dans un palais de l'Exposition universelle de 1900.",
  },
  {
    name: "Musée d'Art Moderne de Paris (MAM)",
    arrondissement: "Paris 16e",
    address: "11 Av. du Président Wilson, 75116 Paris",
    website: "https://www.mam.paris.fr",
    free_access: "permanent",
    description:
      "Art moderne et contemporain du XXe siècle à aujourd'hui. Collection permanente gratuite.",
  },
  {
    name: "Maison de Victor Hugo",
    arrondissement: "Paris 4e",
    address: "6 Place des Vosges, 75004 Paris",
    website: "https://www.maisonsvictorhugo.paris.fr",
    free_access: "permanent",
    description:
      "L'appartement de Victor Hugo place des Vosges, où il vécut de 1832 à 1848.",
  },
  {
    name: "Musée du Louvre",
    arrondissement: "Paris 1er",
    address: "Rue de Rivoli, 75001 Paris",
    website: "https://www.louvre.fr",
    free_access: "gratuit_26",
    description:
      "Le plus grand musée d'art au monde. Gratuit pour les moins de 26 ans résidents de l'UE (et pour tous certains soirs).",
  },
  {
    name: "Musée d'Orsay",
    arrondissement: "Paris 7e",
    address: "Esplanade Valéry Giscard d'Estaing, 75007 Paris",
    website: "https://www.musee-orsay.fr",
    free_access: "gratuit_26",
    description:
      "Chef-d'œuvre de l'art du XIXe siècle (impressionnisme...) dans une ancienne gare. Gratuit pour les -26 ans UE.",
  },
  {
    name: "Musée du Quai Branly - Jacques Chirac",
    arrondissement: "Paris 7e",
    address: "37 Quai Branly, 75007 Paris",
    website: "https://www.quaibranly.fr",
    free_access: "gratuit_26",
    description:
      "Arts et civilisations d'Afrique, d'Asie, d'Océanie et des Amériques.",
  },
  {
    name: "Centre Pompidou",
    arrondissement: "Paris 4e",
    address: "Place Georges-Pompidou, 75004 Paris",
    website: "https://www.centrepompidou.fr",
    free_access: "gratuit_26",
    description:
      "Le plus grand musée d'art moderne et contemporain d'Europe. Gratuit pour les -26 ans UE.",
  },
];

// Insère/actualise les musées curés. Idempotent (clé = slug).
async function seedMuseums() {
  let created = 0;
  for (const data of MUSEUMS) {
    const slug = toSlug(data.name);
    let museum = await Museum.findOne({ where: { slug } });
    if (!museum) {
      museum = Museum.build({ slug });
      created += 1;
    }
    museum.set(data);
    await museum.save();
  }
  return { created, total: await Museum.count() };
}

module.exports = { MUSEUMS, seedMuseums };
