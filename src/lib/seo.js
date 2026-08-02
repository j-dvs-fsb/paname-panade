"use strict";

// Référencement : métadonnées de page, Open Graph et données structurées.
//
// Chaque route construit son objet `meta` avec `pageMeta()` ; base.njk le rend
// dans le <head>. Les valeurs absentes retombent sur les valeurs par défaut du
// site, pour qu'aucune page ne se retrouve sans description ni URL canonique.

const config = require("../config");
const { cleanValue, safeUrl } = require("./values");
const { proxyUrl } = require("../services/imageCache");

const SITE_NAME = "Paname Panade";
const DEFAULT_DESCRIPTION =
  "Toutes les expositions et les musées gratuits pour les moins de 26 ans à Paris : " +
  "dates, horaires, billetterie et conditions de gratuité.";

// Origine publique du site. SITE_URL fige le domaine (utile pour le sitemap et
// les balises canoniques) ; sinon on la dérive de la requête - `trust proxy`
// est actif, donc req.protocol vaut bien https derrière le proxy Infomaniak.
function origin(req) {
  if (config.siteUrl) return config.siteUrl;
  return `${req.protocol}://${req.get("host")}`;
}

function absoluteUrl(req, path) {
  const p = String(path || "/");
  return origin(req) + (p.startsWith("/") ? p : "/" + p);
}

// Description de ~155 caractères, coupée sur un mot entier et jamais sur une
// ponctuation orpheline.
function metaDescription(text, max = 155) {
  const value = cleanValue(text);
  if (!value) return null;
  const flat = value.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  const cut = flat.slice(0, max);
  const space = cut.lastIndexOf(" ");
  const kept = space > max * 0.5 ? cut.slice(0, space) : cut;
  return kept.replace(/[\s,;:.!?-]+$/, "") + "…";
}

// Image de partage : passée par notre proxy et rendue absolue, comme les
// visuels de page - plus aucun lien direct vers un CDN externe dans le HTML.
function shareImage(req, src) {
  const proxied = proxyUrl(src);
  return proxied ? absoluteUrl(req, proxied) : null;
}

// Objet consommé par base.njk. `jsonld` est déjà sérialisé et échappé.
function pageMeta(req, options = {}) {
  const url = options.url ? absoluteUrl(req, options.url) : absoluteUrl(req, req.originalUrl.split("?")[0]);
  return {
    site_name: SITE_NAME,
    title: cleanValue(options.title) || SITE_NAME,
    description: cleanValue(options.description) || DEFAULT_DESCRIPTION,
    url,
    canonical: options.canonical ? absoluteUrl(req, options.canonical) : url,
    image: shareImage(req, options.image),
    og_type: options.og_type || "website",
    robots: options.robots || null,
    jsonld: options.jsonld ? serializeJsonLd(options.jsonld) : null,
  };
}

// `</script>` dans une description fermerait la balise : on neutralise `<`.
function serializeJsonLd(data) {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

function isoDate(value) {
  const s = value ? String(value).slice(0, 10) : "";
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : null;
}

// schema.org/ExhibitionEvent - repris par les résultats enrichis de Google.
// N'émet que des champs vérifiables : pas d'offre inventée pour une expo dont
// on ne connaît pas le tarif.
function expoJsonLd(expo, { url, image } = {}) {
  const museum = expo.museum || null;
  const data = {
    "@context": "https://schema.org",
    "@type": "ExhibitionEvent",
    name: expo.title,
    url,
    eventStatus: "https://schema.org/EventScheduled",
    eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
  };

  const description = metaDescription(expo.description_text, 300);
  if (description) data.description = description;

  const start = isoDate(expo.date_start);
  const end = isoDate(expo.date_end);
  if (start) data.startDate = start;
  if (end) data.endDate = end;
  if (image) data.image = [image];

  const placeName = expo.venue_label || (museum ? museum.name : null);
  if (placeName) {
    const place = { "@type": "Place", name: placeName };
    const address = { "@type": "PostalAddress", addressLocality: "Paris", addressCountry: "FR" };
    const street = cleanValue(expo.address) || (museum ? cleanValue(museum.address) : null);
    const zip = cleanValue(expo.postal_code);
    if (street) address.streetAddress = street;
    if (zip) address.postalCode = zip;
    place.address = address;
    if (expo.map_lat != null && expo.map_lon != null) {
      place.geo = { "@type": "GeoCoordinates", latitude: expo.map_lat, longitude: expo.map_lon };
    }
    data.location = place;
  }

  if (museum) {
    data.organizer = { "@type": "Organization", name: museum.name };
    const site = safeUrl(museum.website);
    if (site) data.organizer.url = site;
  }

  const freeForAll = expo.price_category === "gratuit_tous";
  data.isAccessibleForFree = freeForAll;
  if (freeForAll) {
    const ticket = expo.ticket;
    const offer = {
      "@type": "Offer",
      price: 0,
      priceCurrency: "EUR",
      availability: "https://schema.org/InStock",
      url: (ticket && ticket.url) || url,
    };
    if (start) offer.validFrom = start;
    data.offers = offer;
  }

  return data;
}

function museumJsonLd(museum, { url, image } = {}) {
  const data = {
    "@context": "https://schema.org",
    "@type": "Museum",
    name: museum.name,
    url,
  };
  const description = metaDescription(museum.description, 300);
  if (description) data.description = description;
  if (image) data.image = [image];
  const site = safeUrl(museum.website);
  if (site) data.sameAs = [site];
  const street = cleanValue(museum.address);
  if (street) {
    data.address = {
      "@type": "PostalAddress",
      streetAddress: street,
      addressLocality: "Paris",
      addressCountry: "FR",
    };
  }
  if (museum.lat != null && museum.lon != null) {
    data.geo = { "@type": "GeoCoordinates", latitude: museum.lat, longitude: museum.lon };
  }
  const horaires = cleanValue(museum.horaires);
  if (horaires) data.openingHours = horaires;
  return data;
}

module.exports = {
  SITE_NAME,
  DEFAULT_DESCRIPTION,
  origin,
  absoluteUrl,
  shareImage,
  metaDescription,
  pageMeta,
  expoJsonLd,
  museumJsonLd,
};
