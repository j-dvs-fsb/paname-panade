"use strict";

const bcrypt = require("bcryptjs");
const express = require("express");
const { Op } = require("sequelize");
const {
  sequelize,
  User,
  Favorite,
  Visit,
  Credential,
  Exposition,
  AuthSession,
  AuthAccount,
} = require("../models");
const { requireLogin, requireProfile } = require("../middleware/auth");
const { authLimiter } = require("../middleware/rateLimit");
const { urlFor } = require("../lib/urls");
const { getAuth, isGoogleEnabled, baseUrl } = require("../auth");
const { toHeaders, forwardCookies, closeSession } = require("../auth/session");

const router = express.Router();

const MIN_PASSWORD = 8;

function parseDate(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((value || "").trim());
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return isNaN(d.getTime()) ? null : value.trim();
}

// N'accepte que des chemins relatifs internes (anti open-redirect).
function safeNext(value) {
  const next = String(value || "");
  if (next.startsWith("/") && !next.startsWith("//") && !next.includes("\\")) return next;
  return null;
}

// Better Auth renvoie une Response Web quand on demande `asResponse` : on en
// recopie les cookies (session) sur la réponse Express.
async function callAuth(req, res, method, body) {
  const auth = await getAuth();
  const response = await auth.api[method]({
    body,
    headers: toHeaders(req),
    asResponse: true,
  });
  forwardCookies(res, response.headers);
  if (response.ok) return { ok: true };

  let message = null;
  try {
    message = (await response.json()).message;
  } catch (e) {
    /* réponse sans corps JSON */
  }
  return { ok: false, status: response.status, message };
}

// Une inscription ou une connexion Google peut arriver sans date de naissance :
// elle est indispensable au compte à rebours, on la demande juste après.
function needsProfile(user) {
  return !!user && !user.date_naissance;
}

router.get("/inscription", (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));
  res.render("auth/register.njk", { form: {}, google_enabled: isGoogleEnabled() });
});

router.post("/inscription", authLimiter, async (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));

  const email = (req.body.email || "").trim().toLowerCase();
  const password = req.body.password || "";
  const prenom = (req.body.prenom || "").trim();
  const dateNaissance = req.body.date_naissance || "";

  const errors = [];
  if (!email || !email.includes("@")) errors.push("Email invalide.");
  if (password.length < MIN_PASSWORD)
    errors.push(`Le mot de passe doit faire au moins ${MIN_PASSWORD} caractères.`);
  if (!prenom) errors.push("Le prénom est requis.");
  if (!dateNaissance) errors.push("La date de naissance est requise.");
  if (await User.findOne({ where: { email } })) errors.push("Cet email est déjà utilisé.");
  const dn = parseDate(dateNaissance);
  if (!dn) errors.push("Date de naissance invalide.");

  if (errors.length) {
    for (const e of errors) req.flash("danger", e);
    return res.status(400).render("auth/register.njk", {
      form: req.body,
      google_enabled: isGoogleEnabled(),
    });
  }

  // Better Auth crée l'utilisateur, hache le mot de passe (bcrypt, cf.
  // src/auth) et ouvre la session — `autoSignIn` est actif.
  const result = await callAuth(req, res, "signUpEmail", {
    email,
    password,
    name: prenom,
    date_naissance: dn,
  });
  if (!result.ok) {
    req.flash("danger", result.message || "Impossible de créer le compte.");
    return res.status(400).render("auth/register.njk", {
      form: req.body,
      google_enabled: isGoogleEnabled(),
    });
  }

  req.flash("success", `Bienvenue ${prenom} ! Ton compte est créé.`);
  res.redirect(urlFor("main.profile"));
});

router.get("/connexion", (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));
  res.render("auth/login.njk", { google_enabled: isGoogleEnabled() });
});

router.post("/connexion", authLimiter, async (req, res) => {
  if (req.user) return res.redirect(urlFor("main.index"));

  const email = (req.body.email || "").trim().toLowerCase();
  const password = req.body.password || "";

  const result = await callAuth(req, res, "signInEmail", { email, password });
  if (result.ok) {
    return res.redirect(safeNext(req.query.next) || urlFor("main.profile"));
  }

  // Message volontairement identique quel que soit le motif : pas d'indice
  // permettant de savoir si l'email existe.
  req.flash("danger", "Email ou mot de passe incorrect.");
  res.status(401).render("auth/login.njk", { google_enabled: isGoogleEnabled() });
});

// --- Connexion Google ---
// On demande l'URL d'autorisation à Better Auth puis on redirige. Le retour
// arrive sur /api/auth/callback/google, servi par son propre gestionnaire.
router.get("/connexion/google", authLimiter, async (req, res) => {
  if (!isGoogleEnabled()) {
    req.flash("danger", "La connexion Google n'est pas configurée sur ce site.");
    return res.redirect(urlFor("auth.login"));
  }
  try {
    const auth = await getAuth();
    const { url } = await auth.api.signInSocial({
      body: {
        provider: "google",
        callbackURL: baseUrl() + urlFor("auth.after_google"),
        errorCallbackURL: baseUrl() + urlFor("auth.login"),
      },
      headers: toHeaders(req),
    });
    if (!url) throw new Error("URL d'autorisation absente");
    return res.redirect(url);
  } catch (e) {
    console.error("Connexion Google impossible :", e.message);
    req.flash("danger", "Connexion Google indisponible pour le moment.");
    return res.redirect(urlFor("auth.login"));
  }
});

// Atterrissage après le retour de Google : la session existe déjà, il ne
// manque que la date de naissance à un tout premier passage.
router.get("/connexion/google/retour", async (req, res) => {
  if (!req.user) {
    req.flash("danger", "Connexion Google interrompue.");
    return res.redirect(urlFor("auth.login"));
  }
  if (needsProfile(req.user)) return res.redirect(urlFor("auth.complete_profile"));
  req.flash("success", `Content de te revoir, ${req.user.prenom} !`);
  res.redirect(urlFor("main.profile"));
});

// --- Complément de profil (date de naissance) ---
router.get("/compte/complete", requireLogin, (req, res) => {
  if (!needsProfile(req.user)) return res.redirect(urlFor("main.profile"));
  res.render("auth/complete.njk", { u: req.user });
});

router.post("/compte/complete", requireLogin, async (req, res) => {
  const prenom = (req.body.prenom || "").trim() || req.user.prenom;
  const dn = parseDate(req.body.date_naissance);
  if (!dn) {
    req.flash("danger", "Date de naissance invalide.");
    return res.status(400).render("auth/complete.njk", { u: req.user });
  }
  req.user.prenom = prenom;
  req.user.date_naissance = dn;
  req.user.updated_at = new Date();
  await req.user.save();
  req.flash("success", "Merci ! Ton compte est complet.");
  res.redirect(urlFor("main.profile"));
});

router.get("/compte", requireLogin, requireProfile, (req, res) => {
  res.render("auth/account.njk", { u: req.user });
});

router.post("/compte", requireLogin, async (req, res) => {
  const user = req.user;
  const email = (req.body.email || "").trim().toLowerCase();
  const prenom = (req.body.prenom || "").trim();
  const dateNaissance = req.body.date_naissance || "";
  const password = req.body.password || "";
  const password2 = req.body.password2 || "";

  const errors = [];
  if (!email || !email.includes("@")) errors.push("Email invalide.");
  if (!prenom) errors.push("Le prénom est requis.");
  if (!dateNaissance) errors.push("La date de naissance est requise.");
  const dn = parseDate(dateNaissance);
  if (dateNaissance && !dn) errors.push("Date de naissance invalide.");
  // Email déjà pris par un AUTRE utilisateur ?
  const clash = await User.findOne({ where: { email, id: { [Op.ne]: user.id } } });
  if (clash) errors.push("Cet email est déjà utilisé.");
  if (password && password.length < MIN_PASSWORD)
    errors.push(`Le nouveau mot de passe doit faire au moins ${MIN_PASSWORD} caractères.`);
  if (password && password !== password2)
    errors.push("Les deux mots de passe ne correspondent pas.");

  if (errors.length) {
    for (const e of errors) req.flash("danger", e);
    return res.render("auth/account.njk", { u: Object.assign({}, user.get(), req.body) });
  }

  user.email = email;
  user.prenom = prenom;
  if (dn) user.date_naissance = dn;
  user.updated_at = new Date();
  await user.save();

  if (password) {
    // Le mot de passe vit dans `account.password` (fournisseur "credential").
    // On écrit le hachage bcrypt directement : c'est exactement l'algorithme
    // branché sur Better Auth (cf. src/auth/index.js). Passer par son API
    // demanderait le mot de passe actuel, que ce formulaire ne collecte pas.
    const hash = bcrypt.hashSync(password, 12);
    const [account, created] = await AuthAccount.findOrCreate({
      where: { userId: user.id, providerId: "credential" },
      defaults: {
        accountId: String(user.id),
        providerId: "credential",
        userId: user.id,
        password: hash,
        createdAt: new Date(),
        updatedAt: new Date(),
      },
    });
    if (!created) {
      account.password = hash;
      account.updatedAt = new Date();
      await account.save();
    }
    // La colonne historique ne doit plus servir de source de vérité.
    if (user.password_hash) {
      user.password_hash = null;
      await user.save();
    }
  }

  req.flash("success", "Compte mis à jour.");
  res.redirect(urlFor("main.profile"));
});

// --- RGPD : portabilité — export JSON de toutes les données du compte ---
router.get("/compte/donnees", requireLogin, async (req, res) => {
  const [favorites, visits, credentials] = await Promise.all([
    Favorite.findAll({
      where: { user_id: req.user.id },
      include: [{ model: Exposition, as: "exposition", attributes: ["title", "slug"] }],
    }),
    Visit.findAll({
      where: { user_id: req.user.id },
      include: [{ model: Exposition, as: "exposition", attributes: ["title", "slug"] }],
    }),
    Credential.findAll({ where: { user_id: req.user.id } }),
  ]);

  const data = {
    exporte_le: new Date().toISOString(),
    compte: {
      email: req.user.email,
      prenom: req.user.prenom,
      date_naissance: req.user.date_naissance,
      cree_le: req.user.created_at,
    },
    favoris: favorites.map((f) => ({
      exposition: f.exposition ? f.exposition.title : null,
      ajoute_le: f.created_at,
    })),
    visites: visits.map((v) => ({
      exposition: v.exposition ? v.exposition.title : null,
      note: v.rating,
      commentaire: v.comment,
      visite_le: v.visited_at,
    })),
    passkeys: credentials.map((c) => ({ nom: c.label, ajoutee_le: c.created_at })),
  };

  res.setHeader("Content-Disposition", 'attachment; filename="paname-panade-mes-donnees.json"');
  res.json(data);
});

// --- RGPD : droit à l'effacement — suppression du compte par l'utilisateur ---
router.post("/compte/supprimer", requireLogin, async (req, res) => {
  const confirm = (req.body.confirm_email || "").trim().toLowerCase();
  if (confirm !== req.user.email.toLowerCase()) {
    req.flash("danger", "Confirmation incorrecte : saisis l'email exact de ton compte.");
    return res.redirect(urlFor("auth.account"));
  }

  const userId = req.user.id;
  // Effacement réel, pas un drapeau « désactivé » : compte, favoris, avis,
  // passkeys, sessions Better Auth et comptes liés (dont Google) partent
  // ensemble, dans une transaction.
  await sequelize.transaction(async (t) => {
    await Favorite.destroy({ where: { user_id: userId }, transaction: t });
    await Visit.destroy({ where: { user_id: userId }, transaction: t });
    await Credential.destroy({ where: { user_id: userId }, transaction: t });
    await AuthSession.destroy({ where: { userId }, transaction: t });
    await AuthAccount.destroy({ where: { userId }, transaction: t });
    await User.destroy({ where: { id: userId }, transaction: t });
  });

  await closeSession(req, res);
  req.session.destroy(() => res.redirect(urlFor("main.index")));
});

router.post("/deconnexion", requireLogin, async (req, res) => {
  await closeSession(req, res);
  // La session Express ne porte plus que le flash et le jeton CSRF, mais
  // autant repartir de zéro.
  req.session.destroy(() => {
    res.redirect(urlFor("main.index"));
  });
});

module.exports = router;
