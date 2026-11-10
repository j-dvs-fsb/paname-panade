"use strict";

// Réception de l'export du Panade Collector (contrat : collector/docs/export.md).
//
// Chaque matin, le collecteur (sur le Mac) envoie son export par POST
// /api/import. Le site ne scrape rien : il vérifie le fichier, puis l'applique
// en entier ou pas du tout (une seule transaction). S'il ne reçoit rien un
// matin, il garde simplement ce qu'il a.
//
// Ce que fait l'import :
//   - chaque lieu est rattaché à un musée du site (alias, même slug, ou slug
//     qui commence par l'identifiant du lieu) ; à défaut, le musée est créé ;
//   - les horaires du collecteur complètent un musée qui n'en a pas (jamais
//     d'écrasement d'une saisie faite dans l'admin) ;
//   - chaque exposition est créée ou mise à jour, repérée par son
//     external_id « collecteur:<id> » ;
//   - une exposition du collecteur qui n'est plus dans l'export est masquée
//     (statut « collector_removed ») et revient si elle réapparaît ;
//   - les expositions « payant » et « à confirmer » ne sont pas montrées : le
//     site ne liste que des expos gratuites ou à tarif réduit pour les -26 ans ;
//   - une exposition déjà présente sur le site par une autre source (même
//     lien ou même titre dans le même musée) n'est pas dupliquée.

const crypto = require("crypto");
const { Op } = require("sequelize");

const { sequelize, Museum, Exposition, CollectorImport } = require("../models");
const ALIASES = require("../data/collectorAliases");
const { toSlug } = require("../lib/slug");
const { safeUrl } = require("../lib/values");

const VERSION = 1;
const PREFIXE = "collecteur:";
const RETIREE = "collector_removed";
const CATEGORIES = new Set(["gratuit_tous", "gratuit_26", "reduit_26", "payant", "a_confirmer"]);
const AFFICHEES = new Set(["gratuit_tous", "gratuit_26", "reduit_26"]);
const PORTEES = new Set(["permanent", "temporaire"]);
const IMPORTS_GARDES = 7;
const ISO = /^\d{4}-\d{2}-\d{2}$/;

class ImportRefuse extends Error {
  constructor(statut, message, details = []) {
    super(message);
    this.statut = statut;
    this.details = details;
  }
}

// JSON canonique, identique à celui du collecteur : clés triées, séparateurs
// sans espace, caractères non ASCII tels quels (json.dumps(..., sort_keys=True,
// separators=(",", ":"), ensure_ascii=False)).
function canonique(valeur) {
  if (Array.isArray(valeur)) return "[" + valeur.map(canonique).join(",") + "]";
  if (valeur && typeof valeur === "object") {
    return "{" + Object.keys(valeur).sort().map((k) => JSON.stringify(k) + ":" + canonique(valeur[k])).join(",") + "}";
  }
  return JSON.stringify(valeur);
}

function empreinte(contenu) {
  const sans = { ...contenu };
  delete sans.empreinte;
  return crypto.createHash("sha256").update(canonique(sans), "utf8").digest("hex");
}

const estTexte = (v) => typeof v === "string" && v.trim() !== "";

// Valide le fichier entier avant toute écriture. Renvoie la liste des erreurs.
function verifier(contenu) {
  const erreurs = [];
  if (!contenu || typeof contenu !== "object" || Array.isArray(contenu)) return ["le corps n'est pas un objet JSON"];
  if (contenu.version !== VERSION) erreurs.push(`version inconnue : ${JSON.stringify(contenu.version)}`);
  if (!estTexte(contenu.genere_le)) erreurs.push("genere_le manquant");
  if (!Array.isArray(contenu.lieux)) return [...erreurs, "lieux manquant"];
  let total = 0;
  const vus = new Set();
  contenu.lieux.forEach((lieu, i) => {
    const ou = `lieux[${i}]`;
    if (!lieu || !/^[a-z0-9]+([_-][a-z0-9]+)*$/.test(lieu.id || "")) erreurs.push(`${ou}.id invalide`);
    if (!estTexte(lieu && lieu.nom)) erreurs.push(`${ou}.nom manquant`);
    const expos = (lieu && lieu.expositions) || [];
    if (!Array.isArray(expos)) return erreurs.push(`${ou}.expositions n'est pas une liste`);
    expos.forEach((e, j) => {
      const ici = `${ou}.expositions[${j}]`;
      total += 1;
      if (!Number.isInteger(e.id)) erreurs.push(`${ici}.id invalide`);
      else if (vus.has(e.id)) erreurs.push(`${ici}.id en double : ${e.id}`);
      vus.add(e.id);
      if (!estTexte(e.titre)) erreurs.push(`${ici}.titre manquant`);
      if (!PORTEES.has(e.portee)) erreurs.push(`${ici}.portee invalide`);
      for (const d of ["date_debut", "date_fin"]) {
        if (e[d] !== undefined && !ISO.test(e[d])) erreurs.push(`${ici}.${d} invalide`);
      }
      if (e.date_debut && e.date_fin && e.date_fin < e.date_debut) erreurs.push(`${ici} : date de fin avant le début`);
      for (const u of ["url", "image_url"]) {
        if (e[u] !== undefined && !safeUrl(e[u])) erreurs.push(`${ici}.${u} invalide`);
      }
      if (!e.gratuite || !CATEGORIES.has(e.gratuite.categorie)) erreurs.push(`${ici}.gratuite.categorie invalide`);
    });
  });
  if (!contenu.compte || contenu.compte.lieux !== contenu.lieux.length || contenu.compte.expositions !== total) {
    erreurs.push("compte ne correspond pas au contenu : fichier incomplet");
  }
  return erreurs;
}

// Précision affichée sous le tarif (getter `price_note`, lib/pricing.js).
function noteTarif(g) {
  if (g.categorie === "reduit_26" && typeof g.prix === "number") {
    return typeof g.plein_tarif === "number" ? `${g.prix} € au lieu de ${g.plein_tarif} €` : `${g.prix} €`;
  }
  if (g.categorie === "gratuit_26" && g.audience === "moins_26_ue") {
    return "Résidents de l'Union européenne, sur justificatif.";
  }
  return null;
}

function trouverMusee(id, musees) {
  if (ALIASES[id]) {
    const alias = musees.find((m) => m.slug === ALIASES[id]);
    if (alias) return alias;
  }
  const meme = musees.find((m) => m.slug === id);
  if (meme) return meme;
  const prefixe = musees.filter((m) => m.slug.startsWith(id + "-"));
  return prefixe.length === 1 ? prefixe[0] : null;
}

async function slugLibre(base, pris, transaction) {
  base = toSlug(base).slice(0, 200) || "exposition";
  let slug = base;
  for (let n = 2; ; n += 1) {
    if (!pris.has(slug) && !(await Exposition.findOne({ where: { slug }, attributes: ["id"], transaction }))) {
      pris.add(slug);
      return slug;
    }
    slug = `${base}-${n}`;
  }
}

// Une expo d'une autre source (QFAP, admin, scraping) qui est la même : même
// lien ou même titre dans le même musée ; pour une collection permanente, le
// musée en a déjà une.
function doublon(e, musee, existantes) {
  const autres = existantes.filter((x) => x.museum_id === musee.id && !(x.external_id || "").startsWith(PREFIXE));
  if (e.portee === "permanent") return autres.some((x) => x.source === "permanent");
  const lien = safeUrl(e.url);
  const titre = toSlug(e.titre);
  return autres.some((x) => (lien && safeUrl(x.url) === lien) || toSlug(x.title) === titre);
}

async function appliquer(contenu) {
  const bilan = {
    lieux: contenu.lieux.length, musees_rattaches: 0, musees_crees: [], horaires_completes: 0,
    expos_creees: 0, expos_mises_a_jour: 0, expos_retirees: 0, doublons_ignores: [], non_affichees: {},
  };
  const transaction = await sequelize.transaction();
  try {
    const musees = await Museum.findAll({ transaction });
    const existantes = await Exposition.findAll({
      where: { status: { [Op.ne]: "archived" } },
      attributes: ["id", "museum_id", "title", "url", "source", "external_id"],
      transaction,
    });
    const duCollecteur = new Map(
      (await Exposition.findAll({ where: { external_id: { [Op.like]: `${PREFIXE}%` } }, transaction }))
        .map((x) => [x.external_id, x])
    );
    const vues = new Set();
    const slugsPris = new Set();

    for (const lieu of contenu.lieux) {
      let musee = trouverMusee(lieu.id, musees);
      if (musee) {
        bilan.musees_rattaches += 1;
      } else {
        musee = await Museum.create({
          slug: lieu.id, name: lieu.nom, horaires_url: safeUrl(lieu.horaires_url), expos_url: safeUrl(lieu.expos_url),
        }, { transaction });
        musees.push(musee);
        bilan.musees_crees.push(lieu.id);
      }
      const complements = {};
      if (!musee.horaires && estTexte(lieu.horaires_resume)) complements.horaires = lieu.horaires_resume.slice(0, 500);
      if (!musee.horaires_url && safeUrl(lieu.horaires_url)) complements.horaires_url = safeUrl(lieu.horaires_url);
      if (complements.horaires) bilan.horaires_completes += 1;
      if (Object.keys(complements).length) await musee.update(complements, { transaction, hooks: false });

      for (const e of lieu.expositions || []) {
        const cle = PREFIXE + e.id;
        const categorie = e.gratuite.categorie;
        if (!AFFICHEES.has(categorie)) {
          bilan.non_affichees[categorie] = (bilan.non_affichees[categorie] || 0) + 1;
          continue; // pas vue : si elle était affichée, elle sera retirée plus bas
        }
        const donnees = {
          title: e.titre.slice(0, 300),
          description: e.description || null,
          museum_id: musee.id,
          venue_name: musee.name,
          date_start: e.date_debut || null,
          date_end: e.date_fin || null,
          url: safeUrl(e.url),
          image_url: safeUrl(e.image_url),
          price_category: categorie,
          price_note: noteTarif(e.gratuite),
          reservation: "inconnue",
          source: e.portee === "permanent" ? "permanent" : "collecteur",
          external_id: cle,
        };
        const deja = duCollecteur.get(cle);
        if (deja) {
          // « draft » : masquée à la main dans l'admin, on ne la republie pas.
          if (deja.status === RETIREE) donnees.status = "published";
          await deja.update(donnees, { transaction });
          bilan.expos_mises_a_jour += 1;
        } else if (doublon(e, musee, existantes)) {
          bilan.doublons_ignores.push(`${lieu.id} : ${e.titre}`);
          continue;
        } else {
          await Exposition.create(
            { ...donnees, slug: await slugLibre(e.titre, slugsPris, transaction), status: "published" },
            { transaction }
          );
          bilan.expos_creees += 1;
        }
        vues.add(cle);
      }
    }

    for (const [cle, expo] of duCollecteur) {
      if (!vues.has(cle) && expo.status === "published") {
        await expo.update({ status: RETIREE }, { transaction });
        bilan.expos_retirees += 1;
      }
    }

    await CollectorImport.create({
      empreinte: contenu.empreinte, genere_le: contenu.genere_le, recu_le: new Date(),
      nb_lieux: contenu.compte.lieux, nb_expositions: contenu.compte.expositions,
      bilan: JSON.stringify(bilan), contenu: JSON.stringify(contenu),
    }, { transaction });
    const anciens = await CollectorImport.findAll({
      attributes: ["id"], order: [["id", "DESC"]], offset: IMPORTS_GARDES, transaction,
    });
    if (anciens.length) await CollectorImport.destroy({ where: { id: anciens.map((a) => a.id) }, transaction });

    await transaction.commit();
    return bilan;
  } catch (err) {
    await transaction.rollback();
    throw err;
  }
}

// Point d'entrée : corps brut (Buffer), en-têtes déjà authentifiés par la route.
async function recevoir(corps, idempotencyKey) {
  let contenu;
  try {
    contenu = JSON.parse(Buffer.isBuffer(corps) ? corps.toString("utf8") : String(corps));
  } catch {
    throw new ImportRefuse(400, "le corps n'est pas du JSON valide");
  }
  if (!contenu || typeof contenu.empreinte !== "string" || empreinte(contenu) !== contenu.empreinte) {
    throw new ImportRefuse(422, "empreinte invalide : fichier incomplet ou modifié");
  }
  if (idempotencyKey && idempotencyKey !== contenu.empreinte) {
    throw new ImportRefuse(422, "Idempotency-Key ne correspond pas à l'empreinte");
  }
  const erreurs = verifier(contenu);
  if (erreurs.length) throw new ImportRefuse(422, "export non conforme, rien n'a été appliqué", erreurs.slice(0, 50));
  if (await CollectorImport.findOne({ where: { empreinte: contenu.empreinte }, attributes: ["id"] })) {
    return { deja_applique: true };
  }
  return { applique: true, bilan: await appliquer(contenu) };
}

module.exports = { recevoir, appliquer, verifier, empreinte, canonique, ImportRefuse, PREFIXE, RETIREE };
