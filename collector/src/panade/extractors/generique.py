"""Extracteur générique, paramétré par site : une config, pas un module par musée.

Principe, entièrement déterministe :
  1. on part de chaque lien interne de la zone principale (filtré par `inclure` / `exclure`) ;
  2. on remonte ses ancêtres jusqu'au premier bloc qui porte une date lisible
     (<time datetime> ou date écrite en français), sans dépasser `profondeur` niveaux
     ni avaler plusieurs expositions à la fois ;
  3. ce bloc est la « carte » : titre (titre HTML, sinon texte du lien), dates, image.

Les règles du projet valent ici comme ailleurs : aucune gratuité lue, aucune date devinée,
les activités (visites, ateliers, concerts) écartées.
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlsplit

from panade import html as h
from panade.dates_fr import analyser
from panade.extractors import ExpoBrute
from panade.extractors.paris_musees import ACTIVITES, MENTION_TARIF, _image

TITRES = ("h1", "h2", "h3", "h4", "h5", "[class*=title]:not([class*=sur]):not([class*=upper]):not([class*=sub])",
          "[class*=titre]:not([class*=sur])")
# Un titre qui *commence* par une activité (« Visite guidée de l'exposition... », « Atelier... »).
# Pas n'importe où dans le titre : « Une histoire du cinéma français » est une exposition.
MOTS_ACTIVITE = re.compile(
    r"^\W*(visites?\b|atelier|concert|conf[ée]rence|spectacle|projection|stage\b|rencontre|lecture\b|"
    r"colloque|nocturne|soir[ée]e|festival|cours\b|masterclass|journ[ée]e d'[ée]tude|week-end|concours|nuits? de)", re.I)


def extraire_avec(cfg: dict, page_html: str, url_page: str, aujourdhui: date) -> list[ExpoBrute]:
    if cfg.get("json_html"):
        # Réponse JSON qui transporte un fragment HTML (Bourse de Commerce : {"data": "<div>..."}).
        import json
        try:
            page_html = "<html><body><main>" + json.loads(page_html)[cfg["json_html"]] + "</main></body></html>"
        except (ValueError, KeyError, TypeError):
            return []
    arbre = h.lire(page_html)
    if cfg.get("fiche"):
        return _fiche(cfg, arbre, url_page, aujourdhui)
    if cfg.get("zone"):
        return _extraire_zone(cfg, arbre.css_first(cfg["zone"]), url_page, aujourdhui)
    trouvees = _extraire_zone(cfg, arbre.css_first("main"), url_page, aujourdhui)
    # Certaines pages rangent leurs cartes hors de <main> : on regarde alors toute la page.
    if trouvees or arbre.body is None:
        return trouvees
    # Repli sur toute la page, sans l'en-tête, le menu ni le pied de page.
    for bruit in arbre.body.css("header, footer, nav, [role=navigation], [role=contentinfo], [class*=footer], [id*=footer]"):
        bruit.decompose()
    return _extraire_zone(cfg, arbre.body, url_page, aujourdhui)


def _extraire_zone(cfg: dict, zone, url_page: str, aujourdhui: date) -> list[ExpoBrute]:
    if zone is None:
        return []
    hote = urlsplit(url_page).netloc.removeprefix("www.")
    inclure = re.compile(cfg["inclure"]) if cfg.get("inclure") else None
    exclure = re.compile(cfg["exclure"]) if cfg.get("exclure") else None
    profondeur = cfg.get("profondeur", 6)
    expos: dict[str, ExpoBrute] = {}
    for lien in zone.css(cfg.get("liens", "a[href]")):
        url = h.absolu(url_page, lien.attributes.get("href"))
        if not url or urlsplit(url).netloc.removeprefix("www.") != hote:
            continue
        url = url.split("#")[0]
        chemin = urlsplit(url).path + ("?" + urlsplit(url).query if urlsplit(url).query else "")
        if url.rstrip("/") == url_page.split("#")[0].rstrip("/") or url in expos:
            continue
        if (inclure and not inclure.search(chemin)) or (exclure and exclure.search(chemin)):
            continue
        if TAXONOMIE.search(urlsplit(url).path) or re.search(r"\.(pdf|jpe?g|png|docx?)$", urlsplit(url).path, re.I):
            continue
        carte = _carte_du_lien(lien, url, profondeur, aujourdhui, cfg.get("dates"), hote)
        if carte is None:
            continue
        noeud, debut, fin, provenance = carte
        titre = _titre(noeud, lien, cfg.get("titre"))
        if not titre or len(titre) < 3:
            continue
        texte_carte = h.texte(noeud)
        if not cfg.get("sans_filtre_activites") and (MOTS_ACTIVITE.search(titre) or any(
                c in ACTIVITES for c in _categories(noeud))):
            continue
        if fin and fin < aujourdhui.isoformat():
            continue
        e = ExpoBrute(titre=titre, url=url, date_debut=debut, date_fin=fin, image_url=_image(noeud, url_page),
                      description=_description(noeud, titre, texte_carte))
        e.provenance = {"titre": "carte", "url": "carte", "date_debut": provenance, "date_fin": provenance}
        if e.image_url:
            e.provenance["image_url"] = "carte"
        if e.description:
            e.provenance["description"] = "carte"
        expos[url] = e
    return list(expos.values())


TAXONOMIE = re.compile(r"/(types?|tags?|categor[a-z]*|th[eè]mes?|publics?|audiences?|type-evenement|event_type)(/|$)", re.I)


def _liens_internes(noeud, hote: str) -> set[str]:
    sortie = set()
    for a in noeud.css("a[href]"):
        href = a.attributes.get("href", "").split("#")[0].rstrip("/")
        if not href or re.search(r"billet|ticket|reserv|tickeasy", href, re.I):
            continue
        if TAXONOMIE.search(urlsplit(href).path):
            continue      # lien de rubrique (type, public, thème) : ne délimite pas une carte
        cible = urlsplit(href).netloc.removeprefix("www.")
        if cible and cible != hote:
            continue
        sortie.add(urlsplit(href).path.rstrip("/") or "/")
    return sortie


def _texte_dates(zone) -> str:
    """« <span>19 sep</span><span class=fleche/><span>1 nov 2026</span> » se lit « 19 sep au 1 nov 2026 »."""
    morceaux = [h.texte(enfant) for enfant in zone.iter() if h.texte(enfant)]
    return " au ".join(morceaux) if len(morceaux) == 2 else h.texte(zone)


def _carte_du_lien(lien, url: str, profondeur: int, aujourdhui: date, selecteur_dates: str | None, hote: str):
    noeud = lien
    for _ in range(profondeur):
        if noeud is None:
            return None
        if len(_liens_internes(noeud, hote)) > 2:     # on a remonté jusqu'à une liste : trop haut
            return None
        if selecteur_dates:
            for z in noeud.css(selecteur_dates):
                periode = analyser(_texte_dates(z), aujourdhui)
                if periode:
                    prov = "texte_fr_annee_deduite" if periode.annee_deduite else "texte_fr"
                    return noeud, periode.debut, periode.fin, prov
            noeud = noeud.parent
            continue
        temps = [t.attributes.get("datetime", "")[:10] for t in noeud.css("time[datetime]")]
        temps = [t for t in temps if re.fullmatch(r"\d{4}-\d\d-\d\d", t)]
        if temps:
            return noeud, temps[0], (temps[-1] if len(temps) > 1 else None), "time"
        texte = h.texte(noeud)
        if len(texte) < 700:
            periode = analyser(texte, aujourdhui)
            if periode:
                prov = "texte_fr_annee_deduite" if periode.annee_deduite else "texte_fr"
                return noeud, periode.debut, periode.fin, prov
        noeud = noeud.parent
    return None


def _fiche(cfg: dict, arbre, url_page: str, aujourdhui: date) -> list[ExpoBrute]:
    """La page est une seule exposition. Dates lues uniquement dans `dates` : jamais dans le texte libre,
    qui cite aussi des nocturnes et des ateliers."""
    noeud_titre = arbre.css_first(cfg.get("titre", "h1"))
    titre = h.texte(noeud_titre)
    if cfg.get("titre_motif") and titre:
        m = re.search(cfg["titre_motif"], titre)
        titre = m.group(1).strip() if m else titre
    periode = None
    for z in arbre.css(cfg["dates"]):
        periode = analyser(h.texte(z), aujourdhui)
        if periode:
            break
    if not titre or periode is None or (periode.fin and periode.fin < aujourdhui.isoformat()):
        return []
    og = {m.attributes.get("property"): m.attributes.get("content") for m in arbre.css("meta[property^='og:']")}
    prov = "texte_fr_annee_deduite" if periode.annee_deduite else "texte_fr"
    e = ExpoBrute(titre=titre, url=url_page, date_debut=periode.debut, date_fin=periode.fin,
                  image_url=h.absolu(url_page, og.get("og:image")))
    e.provenance = {"titre": "fiche", "url": "fiche", "date_debut": prov, "date_fin": prov}
    if e.image_url:
        e.provenance["image_url"] = "og:image"
    return [e]


GENERIQUES = re.compile(r"^(en savoir plus|d[ée]couvrir|lire la suite|voir|r[ée]server|billetterie|plus d'infos?)$", re.I)


def _titre(noeud, lien, selecteur: str | None = None) -> str:
    for sel in ((selecteur,) if selecteur else TITRES):
        for t in noeud.css(sel):
            texte = h.texte(t)
            if texte and not GENERIQUES.match(texte) and not analyser(texte, date(2000, 1, 1)) and len(texte) < 200:
                return texte
    texte = h.texte(lien)
    return texte if len(texte) < 200 and not GENERIQUES.match(texte) else ""


def _categories(noeud) -> list[str]:
    return [h.texte(n).strip().lower() for n in noeud.css("[class*=categor], [class*=type], [class*=tag], [class*=label]")]


def _description(noeud, titre: str, texte_carte: str) -> str | None:
    for p in noeud.css("p, [class*=subtitle], [class*=chapo], [class*=desc]"):
        t = h.texte(p)
        if t and t != titre and not analyser(t, date(2000, 1, 1)) and not MENTION_TARIF.search(t) and 10 < len(t) < 400:
            return t
    return None


# --- interface d'extracteur (voir extractors/__init__.py) ------------------------------------

def convient(lieu) -> bool:
    from panade.extractors.sites import SITES
    return lieu["id"] in SITES


def source(lieu) -> str:
    """L'adresse que collect interroge : la page de liste ou la source JSON configurée."""
    from panade.extractors.sites import SITES
    return SITES[lieu["id"]]["liste"]


def extraire_pour(lieu_id: str, page_html: str, url_page: str, aujourdhui: date) -> list[ExpoBrute]:
    from panade.extractors.sites import SITES
    cfg = {k: v for k, v in SITES[lieu_id].items() if k != "liste"}
    return extraire_avec(cfg, page_html, url_page, aujourdhui)
