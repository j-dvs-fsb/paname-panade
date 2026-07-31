"use strict";

// Assainissement des valeurs « vides ».
//
// Héritage des imports Python : un champ absent a été sérialisé en chaîne
// "None" au lieu d'un NULL. D'où, sur les fiches concernées, « Horaires :
// None », un code postal « None » collé à l'adresse, et surtout un bouton
// « Réserver » avec href="None" — que le navigateur résout relativement à la
// page courante, produisant le lien mort /exposition/None.
//
// Ces helpers servent des deux côtés : à l'écriture (sync, scraping,
// back-office) pour ne plus jamais stocker ça, et à la lecture (getters du
// modèle) pour que les données déjà en base ne s'affichent pas.

const SENTINELS = new Set(["none", "null", "nan", "undefined"]);

// Valeurs SQL à remettre à NULL par la migration (cf. services/migrate.js).
const SENTINEL_VALUES = ["None", "none", "NONE", "Null", "null", "NULL", "NaN", "nan", "undefined"];

// Chaîne exploitable, ou null. Toute valeur vide ou sentinelle devient null,
// ce qui suffit aux templates : `{% if expo.schedule_text %}` masque la ligne.
function cleanValue(value) {
  if (value === undefined || value === null) return null;
  const s = String(value).trim();
  if (!s) return null;
  return SENTINELS.has(s.toLowerCase()) ? null : s;
}

// URL utilisable dans un href : absolue, en http(s). Tout le reste — y compris
// une valeur relative qui deviendrait un lien mort — renvoie null, à charge de
// l'appelant de ne pas afficher le bouton.
function safeUrl(value) {
  const s = cleanValue(value);
  if (!s) return null;
  let url;
  try {
    url = new URL(s);
  } catch (e) {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  return url.href;
}

// Variante tolérante pour les données importées : accepte « exemple.fr/page »
// (sans schéma) en le préfixant en https. Réservée aux flux externes, jamais
// à une saisie qu'on peut corriger.
function coerceUrl(value) {
  const s = cleanValue(value);
  if (!s) return null;
  if (/^https?:\/\//i.test(s)) return safeUrl(s);
  if (/^[\w-]+(\.[\w-]+)+(\/|$)/.test(s)) return safeUrl("https://" + s);
  return null;
}

module.exports = { cleanValue, safeUrl, coerceUrl, SENTINELS, SENTINEL_VALUES };
