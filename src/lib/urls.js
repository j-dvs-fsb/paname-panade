"use strict";

// Réplique de `url_for` de Flask : nom d'endpoint -> chemin.
// Chaque entrée consomme d'éventuels paramètres de chemin ; les paramètres
// restants sont ajoutés en query-string (avec support des valeurs multiples,
// comme les filtres ?prix=a&prix=b de la page expositions).

const ROUTES = {
  "main.index": () => "/",
  "main.expos": () => "/expositions",
  "main.museums": () => "/musees",
  "main.random_expo": () => "/au-hasard",
  "main.radar": () => "/radar",
  "main.api_museums": () => "/api/museums.json",
  "main.profile": () => "/profil",
  "main.expo_detail": (p) => `/exposition/${enc(take(p, "slug"))}`,
  "main.museum_detail": (p) => `/musee/${enc(take(p, "slug"))}`,
  "main.toggle_favorite": (p) => `/exposition/${take(p, "expo_id")}/favori`,
  "main.mark_done": (p) => `/exposition/${take(p, "expo_id")}/fait`,
  "main.unmark_done": (p) => `/exposition/${take(p, "expo_id")}/annuler-fait`,

  "auth.login": () => "/connexion",
  "auth.register": () => "/inscription",
  "auth.logout": () => "/deconnexion",
  "auth.account": () => "/compte",

  "admin.dashboard": () => "/admin",
  "admin.expos": () => "/admin/expositions",
  "admin.museums": () => "/admin/musees",
  "admin.expo_form": (p) =>
    has(p, "expo_id")
      ? `/admin/expositions/${take(p, "expo_id")}/edit`
      : "/admin/expositions/nouvelle",
  "admin.museum_form": (p) =>
    has(p, "museum_id")
      ? `/admin/musees/${take(p, "museum_id")}/edit`
      : "/admin/musees/nouveau",
  "admin.expo_toggle_status": (p) => `/admin/expositions/${take(p, "expo_id")}/statut`,
  "admin.expo_delete": (p) => `/admin/expositions/${take(p, "expo_id")}/supprimer`,
  "admin.museum_delete": (p) => `/admin/musees/${take(p, "museum_id")}/supprimer`,
  "admin.sync_qfap": () => "/admin/sync-qfap",
  "admin.sync_musees": () => "/admin/sync-musees",

  static: (p) => "/static/" + String(take(p, "filename") || "").replace(/^\/+/, ""),
};

function has(p, k) {
  return p && p[k] !== undefined && p[k] !== null && p[k] !== "";
}
function take(p, k) {
  const v = p && p[k];
  if (p && k in p) delete p[k]; // consommé : n'ira pas en query-string
  return v;
}
function enc(v) {
  return encodeURIComponent(String(v));
}

function queryString(params) {
  const parts = [];
  for (const [k, val] of Object.entries(params || {})) {
    if (val === undefined || val === null || val === "") continue;
    const list = Array.isArray(val) ? val : [val];
    for (const v of list) parts.push(`${enc(k)}=${enc(v)}`);
  }
  return parts.length ? "?" + parts.join("&") : "";
}

function urlFor(endpoint, params) {
  const builder = ROUTES[endpoint];
  if (!builder) throw new Error(`url_for: endpoint inconnu « ${endpoint} »`);
  const rest = Object.assign({}, params); // copie : take() y puise les params de chemin
  const path = builder(rest);
  return path + queryString(rest);
}

module.exports = { urlFor, ROUTES };
