"use strict";

// Proxy et cache d'images servi depuis notre domaine.
//
// Les visuels d'expositions viennent de cdn.paris.fr, api-www.louvre.fr…
// Les afficher en lien direct nous rend dépendants de la latence et de la
// disponibilité de ces hôtes, et fait fuiter la navigation de nos visiteurs
// chez eux. Le premier appel télécharge et met en cache sur disque, les
// suivants sont servis localement.
//
// Pas de redimensionnement ni de conversion WebP : cela demanderait `sharp`,
// une dépendance native de plusieurs dizaines de mégaoctets à compiler, ce que
// l'hébergement mutualisé supporte mal. Le gain visé ici est la suppression du
// hotlink et la mise en cache, pas la recompression.

const crypto = require("crypto");
const fsp = require("fs/promises");
const path = require("path");

const config = require("../config");
const { safeUrl } = require("../lib/values");

const CACHE_DIR = path.join(config.baseDir, ".cache", "img");
const MAX_BYTES = 5 * 1024 * 1024;
const FETCH_TIMEOUT = 10000;
const MAX_AGE_MS = 60 * 24 * 3600 * 1000; // purge des entrées jamais redemandées

const UA = "PanamePanade/1.0 (+https://paname-panade.fr)";

// --- Signature ---
// Sans elle, /img serait un proxy ouvert : n'importe qui pourrait faire
// télécharger n'importe quelle URL par le serveur (SSRF) et faire relayer du
// contenu arbitraire par notre domaine. Seules les URL que nos propres
// templates ont fabriquées portent une signature valide.
function sign(url) {
  return crypto.createHmac("sha256", config.secretKey).update(url).digest("base64url").slice(0, 24);
}

function verify(url, provided) {
  const expected = Buffer.from(sign(url));
  const given = Buffer.from(String(provided || ""));
  return expected.length === given.length && crypto.timingSafeEqual(expected, given);
}

// URL à mettre dans un <img>. Renvoie null si la source est inexploitable :
// au template de basculer sur le placeholder.
function proxyUrl(src) {
  if (!src) return null;
  const value = String(src);
  if (value.startsWith("/")) return value; // déjà servie par nous (image locale)
  const url = safeUrl(value);
  if (!url) return null;
  return `/img?s=${sign(url)}&src=${encodeURIComponent(url)}`;
}

// --- Reconnaissance du type réel ---
// On ne fait pas confiance au Content-Type annoncé : le type est déduit des
// octets. Le SVG est refusé volontairement — servi depuis notre origine, il
// pourrait embarquer du script et contourner la CSP.
function sniffType(buf) {
  if (buf.length < 12) return null;
  if (buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return "image/jpeg";
  if (buf.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) {
    return "image/png";
  }
  const head = buf.subarray(0, 6).toString("latin1");
  if (head === "GIF87a" || head === "GIF89a") return "image/gif";
  if (buf.subarray(0, 4).toString("latin1") === "RIFF" && buf.subarray(8, 12).toString("latin1") === "WEBP") {
    return "image/webp";
  }
  if (buf.subarray(4, 8).toString("latin1") === "ftyp") {
    const brand = buf.subarray(8, 12).toString("latin1");
    if (brand === "avif" || brand === "avis") return "image/avif";
  }
  return null;
}

function cachePath(url) {
  return path.join(CACHE_DIR, crypto.createHash("sha256").update(url).digest("hex"));
}

async function readCache(file) {
  try {
    const buf = await fsp.readFile(file);
    const type = sniffType(buf);
    return type ? { buf, type } : null;
  } catch (e) {
    return null;
  }
}

// Écriture atomique : un fichier temporaire puis un rename, pour qu'une
// requête concurrente ne lise jamais un fichier à moitié écrit. Un échec
// d'écriture (disque plein, dossier non inscriptible) n'est pas bloquant :
// l'image est quand même servie, simplement sans être mise en cache.
async function writeCache(file, buf) {
  const tmp = `${file}.${crypto.randomBytes(6).toString("hex")}.tmp`;
  try {
    await fsp.mkdir(CACHE_DIR, { recursive: true });
    await fsp.writeFile(tmp, buf);
    await fsp.rename(tmp, file);
  } catch (e) {
    fsp.unlink(tmp).catch(() => {});
  }
}

async function download(url) {
  const resp = await fetch(url, {
    headers: { "User-Agent": UA, Accept: "image/*" },
    signal: AbortSignal.timeout(FETCH_TIMEOUT),
    redirect: "follow",
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

  const announced = Number(resp.headers.get("content-length") || 0);
  if (announced > MAX_BYTES) throw new Error("image trop lourde");

  const buf = Buffer.from(await resp.arrayBuffer());
  if (buf.length > MAX_BYTES) throw new Error("image trop lourde");

  const type = sniffType(buf);
  if (!type) throw new Error("format non reconnu");
  return { buf, type };
}

// Les requêtes simultanées sur une image pas encore en cache partagent le même
// téléchargement (un visiteur qui ouvre la liste demande 20 images d'un coup).
const inflight = new Map();

async function load(url) {
  const file = cachePath(url);
  const hit = await readCache(file);
  if (hit) return hit;

  if (inflight.has(file)) return inflight.get(file);
  const pending = download(url)
    .then(async (result) => {
      await writeCache(file, result.buf);
      return result;
    })
    .finally(() => inflight.delete(file));
  inflight.set(file, pending);
  return pending;
}

// Purge au démarrage des images plus demandées depuis MAX_AGE_MS : le cache ne
// grossit pas indéfiniment quand les expositions tournent.
async function sweep() {
  let removed = 0;
  try {
    const names = await fsp.readdir(CACHE_DIR);
    const now = Date.now();
    for (const name of names) {
      const file = path.join(CACHE_DIR, name);
      try {
        const stat = await fsp.stat(file);
        if (now - stat.mtimeMs > MAX_AGE_MS) {
          await fsp.unlink(file);
          removed += 1;
        }
      } catch (e) {
        /* fichier disparu entre-temps */
      }
    }
  } catch (e) {
    return 0; // dossier absent : rien à purger
  }
  return removed;
}

module.exports = { proxyUrl, sign, verify, load, sweep, sniffType, CACHE_DIR, MAX_BYTES };
