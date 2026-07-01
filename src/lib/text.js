"use strict";

const cheerio = require("cheerio");

// Balises qui introduisent un saut de ligne / paragraphe à l'affichage.
const BLOCK_TAGS = new Set(["p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"]);

function normalize(raw) {
  const text = raw.replace(/ /g, " ");
  const lines = text.split("\n").map((ln) => ln.replace(/[ \t]+/g, " ").trim());
  const out = [];
  let blank = false;
  for (const ln of lines) {
    if (ln) {
      out.push(ln);
      blank = false;
    } else if (!blank) {
      out.push("");
      blank = true;
    }
  }
  return out.join("\n").trim();
}

// Nettoie un champ pouvant contenir du HTML (descriptions QFAP). Renvoie un
// texte brut multi-lignes (paragraphes séparés par des sauts de ligne), sans
// balises ni entités. Renvoie null si vide. (Port de paname/utils.py:html_to_text)
function htmlToText(value) {
  if (!value) return null;
  if (!value.includes("<") && !value.includes("&")) {
    return value.trim() || null;
  }
  const $ = cheerio.load(value, { decodeEntities: true });
  const parts = [];
  (function walk(node) {
    for (const child of node.children || []) {
      if (child.type === "text") {
        parts.push(child.data || "");
      } else if (child.type === "tag") {
        if (BLOCK_TAGS.has(child.name)) parts.push("\n");
        walk(child);
        if (BLOCK_TAGS.has(child.name)) parts.push("\n");
      }
    }
  })($.root()[0]);
  return normalize(parts.join("")) || null;
}

module.exports = { htmlToText };
