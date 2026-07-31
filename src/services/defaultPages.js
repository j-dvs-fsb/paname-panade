"use strict";

// Contenu initial des pages statiques éditables (voir models/page.js).
// Semé au démarrage si la page n'existe pas encore ; ensuite, la vérité
// est en base et se modifie depuis le back-office.

const DEFAULT_PAGES = [
  {
    slug: "a-propos",
    title: "À propos",
    content: `<p><strong>Paname Panade</strong> regroupe les expositions et musées
<strong>gratuits pour les moins de 26 ans</strong> à Paris. Fiches par musée,
dates et horaires des expositions temporaires, mode « au hasard » pour les
indécis — et un compte perso pour cocher les expos faites, les noter, et
suivre le compte à rebours avant l'anniversaire fatidique.</p>

<p>Le site est indépendant et sans publicité. Il n'est affilié ni à la
Ville de Paris ni aux musées référencés.</p>

<h2 class="h5 mt-5 mb-3">D'où viennent les données ?</h2>
<p>Les expositions temporaires sont issues du jeu de données ouvert
<a href="https://opendata.paris.fr/explore/dataset/que-faire-a-paris-/" rel="noopener">« Que Faire à Paris ? »</a>
de la Ville de Paris, complété par une sélection éditoriale pour les
musées gratuits en permanence. Les informations (dates, horaires, gratuité)
peuvent évoluer : vérifie toujours sur le site du musée avant de te déplacer.</p>

<h2 class="h5 mt-5 mb-3">Une erreur, une expo manquante ?</h2>
<p>Le site est maintenu bénévolement — les signalements sont bienvenus
et les corrections rapides.</p>`,
  },
  {
    slug: "mentions-legales",
    title: "Mentions légales",
    content: `<h2 class="h5 mt-4 mb-2">Éditeur du site</h2>
<p class="mb-1">[À compléter : nom ou raison sociale de l'éditeur]</p>
<p>Contact : [À compléter : adresse email de contact]</p>

<h2 class="h5 mt-4 mb-2">Directeur de la publication</h2>
<p>[À compléter]</p>

<h2 class="h5 mt-4 mb-2">Hébergement</h2>
<p>Infomaniak Network SA<br>
Rue Eugène-Marziano 25, 1227 Genève, Suisse<br>
<a href="https://www.infomaniak.com" rel="noopener">www.infomaniak.com</a></p>

<h2 class="h5 mt-4 mb-2">Contenus et propriété intellectuelle</h2>
<p>Les informations sur les expositions (titres, descriptions, visuels)
proviennent du jeu de données ouvert « Que Faire à Paris ? »
(<a href="https://opendata.paris.fr" rel="noopener">opendata.paris.fr</a>)
et des institutions culturelles concernées, qui restent titulaires des
droits sur leurs contenus. Le reste du site (textes, code, mise en page)
est la propriété de l'éditeur.</p>

<h2 class="h5 mt-4 mb-2">Responsabilité</h2>
<p>Les informations pratiques (dates, horaires, conditions de gratuité)
sont fournies à titre indicatif et peuvent changer sans préavis.
Vérifie sur le site officiel du musée avant de te déplacer.</p>

<p class="muted small mt-5">Voir aussi la
<a href="/confidentialite">politique de confidentialité</a>.</p>`,
  },
  {
    slug: "confidentialite",
    title: "Politique de confidentialité",
    content: `<p>Paname Panade collecte le strict minimum : pas de publicité, pas de
traceurs, pas de revente de données. Cette page décrit ce qui est
réellement enregistré et pourquoi.</p>

<h2 class="h5 mt-5 mb-2">Sans compte</h2>
<p>La consultation du site ne dépose aucun cookie de suivi et ne collecte
aucune donnée personnelle. Il n'y a ni mesure d'audience, ni publicité.</p>

<h2 class="h5 mt-5 mb-2">Avec un compte</h2>
<p>À l'inscription, sont enregistrés :</p>
<ul>
  <li><strong>Email</strong> — identifiant de connexion ;</li>
  <li><strong>Mot de passe</strong> — stocké uniquement sous forme hachée
    (bcrypt), jamais en clair ;</li>
  <li><strong>Prénom</strong> (facultatif) — personnalisation ;</li>
  <li><strong>Date de naissance</strong> — calcul du compte à rebours
    des 26 ans et des statistiques associées ;</li>
  <li><strong>Tes favoris, visites et notes</strong> — le cœur du service.</li>
</ul>
<p>Si tu ajoutes une <strong>passkey</strong>, seule une clé publique est
enregistrée. Aucune donnée biométrique ne quitte ton appareil.</p>

<h2 class="h5 mt-5 mb-2">Signalements et suggestions</h2>
<p>Quand tu signales une erreur sur une fiche ou proposes une expo, seuls
le contenu du message, la fiche concernée et la date d'envoi sont
enregistrés. L'email est <strong>facultatif</strong> : ne le renseigne que
si tu veux une réponse. Sans lui, l'envoi est totalement anonyme — ni
adresse IP, ni identifiant de visiteur. Les signalements traités sont
supprimés au fil de l'eau.</p>

<h2 class="h5 mt-5 mb-2">Cookies</h2>
<p>Un unique cookie de session, strictement nécessaire à la connexion,
valable 30 jours. C'est tout.</p>

<h2 class="h5 mt-5 mb-2">Qui peut voir tes données ?</h2>
<p>Personne d'autre que toi. Par conception, les administrateurs du site
ne peuvent ni consulter ta date de naissance, ni modifier tes informations
personnelles ou ton mot de passe. Aucune donnée n'est transmise à des
tiers.</p>

<h2 class="h5 mt-5 mb-2">Où sont hébergées les données ?</h2>
<p>Chez Infomaniak, à Genève (Suisse) — un pays reconnu par l'Union
européenne comme offrant une protection adéquate des données.</p>

<h2 class="h5 mt-5 mb-2">Tes droits</h2>
<p>Tout se fait depuis ton compte, sans rien demander à personne :</p>
<ul>
  <li><strong>Consulter et rectifier</strong> tes informations :
    page <a href="/compte">Mon compte</a> ;</li>
  <li><strong>Exporter</strong> l'intégralité de tes données (format JSON) :
    bouton dédié sur la page Mon compte ;</li>
  <li><strong>Supprimer</strong> ton compte et toutes les données associées,
    immédiatement et définitivement : également depuis Mon compte.</li>
</ul>
<p>Pour toute autre demande : [À compléter : adresse email de contact].</p>`,
  },
];

// Crée les pages manquantes (idempotent, page par page : une base existante
// reçoit les nouvelles pages au prochain démarrage sans toucher aux autres).
async function seedPages(Page) {
  let created = 0;
  for (const page of DEFAULT_PAGES) {
    const [, wasCreated] = await Page.findOrCreate({
      where: { slug: page.slug },
      defaults: page,
    });
    if (wasCreated) created += 1;
  }
  return { created };
}

module.exports = { DEFAULT_PAGES, seedPages };
