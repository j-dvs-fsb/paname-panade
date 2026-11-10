"""Configuration de l'extracteur générique, site par site (découverte du 2026-10-29).

Chaque entrée : `liste` = la page (ou la source JSON) qui liste les expositions, puis les
réglages facultatifs de `generique.extraire_avec` :
    inclure / exclure   regex sur le chemin des liens retenus
    liens               sélecteur CSS des liens à suivre (cartes d'expositions seulement)
    dates               sélecteur CSS où lire les dates dans une carte
    titre               sélecteur CSS du titre
    fiche               la page est une seule exposition (titre et dates lus aux sélecteurs donnés)
    json_html           la source est un JSON qui transporte un fragment HTML sous cette clé
    profondeur          niveaux d'ancêtres remontés pour trouver la carte (défaut 6)

Une page tirée d'un site qui a changé de gabarit rendra `vide` : `panade health` le signale et
`panade discover` en garde une nouvelle fixture.
"""

SITES: dict[str, dict] = {
    # --- musées nationaux ----------------------------------------------------------------
    "musee-du-louvre": {
        "liste": "https://www.louvre.fr/expositions-et-evenements/expositions",
        "inclure": r"^/agenda/expositions/"},
    "musee-de-l-orangerie-des-tuileries": {
        "liste": "https://www.musee-orangerie.fr/fr/programme/agenda/expositions",
        "inclure": r"/agenda/expositions/"},
    "musee-des-arts-asiatiques-guimet": {
        "liste": "https://www.guimet.fr/fr/expositions",
        "inclure": r"^/fr/expositions/"},
    "musee-du-quai-branly-jacques-chirac": {
        "liste": "https://www.quaibranly.fr/fr/expositions-evenements/au-musee/expositions",
        "inclure": r"/expositions/details-de-levenement/"},
    "musee-eugene-delacroix": {
        "liste": "https://www.musee-delacroix.fr/expositions",
        "fiche": True, "titre": "h1", "dates": "span.date"},
    "musee-gustave-moreau": {
        "liste": "https://musee-moreau.fr/fr/exposition-en-cours",
        "inclure": r"^/fr/agenda/event/", "exclure": r"/type-evenement/"},
    "musee-jean-jacques-henner": {
        "liste": "https://musee-henner.fr/",
        "inclure": r"^/agenda/evenement/"},
    "musee-national-de-l-histoire-et-des-cultures-de-l-immigratio": {
        "liste": "https://www.histoire-immigration.fr/expositions",
        "inclure": r"^/programmation/expositions/"},
    "musee-national-de-la-marine": {
        "liste": "https://www.musee-marine.fr/nos-musees/paris/expositions-et-evenements/les-expositions.html",
        "inclure": r"^/nos-musees/paris/expositions-et-evenements/les-expositions/"},
    "musee-picasso": {
        "liste": "https://www.museepicassoparis.fr/fr/agenda/types/exposition/"},
    "musee-rodin": {
        "liste": "https://www.musee-rodin.fr/musee/expositions",
        "inclure": r"^/musee/expositions/[a-z]"},
    "musee-des-monuments-francais": {
        "liste": "https://www.citedelarchitecture.fr/fr/agenda/type_evenement/exposition-98?date=tout",
        "inclure": r"^/fr/agenda/exposition/"},
    "musee-national-de-la-legion-d-honneur-et-des-ordres-de-cheva": {
        "liste": "https://www.legiondhonneur.fr/fr/le-musee/visiter-le-musee/la-programmation-et-les-visites"},
    # --- monuments nationaux (CMN) : même gabarit, les expositions ont leurs propres cartes --
    **{lid: {"liste": f"https://www.{dom}/agenda", "liens": ".exposition-title a"}
       for lid, dom in (("arc-de-triomphe", "paris-arc-de-triomphe.fr"), ("conciergerie", "paris-conciergerie.fr"),
                        ("pantheon", "paris-pantheon.fr"), ("sainte-chapelle", "sainte-chapelle.fr"))},
    # --- militaire -------------------------------------------------------------------------
    "musee-de-l-armee": {
        "liste": "https://www.musee-armee.fr/au-programme/expositions.html",
        "dates": ".meta-content"},
    # --- autres établissements publics ---------------------------------------------------
    "cite-des-sciences-et-de-l-industrie": {
        "liste": "https://www.cite-sciences.fr/fr/au-programme/expos-temporaires",
        "inclure": r"^/fr/au-programme/expos-temporaires/"},
    "museum-national-d-histoire-naturelle": {
        # mnhn.fr refuse les robots (403) ; le programme parisien est publié sur le site du Jardin des Plantes
        "liste": "https://www.jardindesplantesdeparis.fr/fr/expositions-evenements"},
    "musee-de-l-ecole-nationale-superieure-des-beaux-arts": {
        "liste": "https://beauxartsparis.fr/fr/exposition/a-voir",
        "inclure": r"^/fr/exposition"},
    # --- privés, associatifs, fondations -------------------------------------------------
    "musee-de-l-institut-du-monde-arabe": {
        "liste": "https://www.imarabe.org/fr/agenda/expositions-musee",
        "inclure": r"^/fr/agenda/expositions-musee/", "dates": ".dates"},
    "musee-d-art-et-d-histoire-du-judaisme": {
        "liste": "https://www.mahj.org/fr/programme/l-agenda-du-mahj?f%5B0%5D=field_ag_type_manifestation%3A422",
        "inclure": r"^/fr/programme/"},
    "fondation-cartier-pour-l-art-contemporain": {
        "liste": "https://www.fondationcartier.com/en-ce-moment",
        "inclure": r"^/programme/exposition/"},
    "bourse-de-commerce-pinault-collection": {
        "liste": "https://www.pinaultcollection.com/fr/programme/content/json?date=all&type=expo&audience=all",
        "json_html": "data", "inclure": r"^/fr/boursedecommerce/"},
    "musee-de-la-musique": {
        "liste": "https://philharmoniedeparis.fr/fr/musee-de-la-musique",
        "inclure": r"^/fr/activite/exposition/", "exclure": r"collection-permanente"},
    "musee-de-la-franc-maconnerie": {
        "liste": "https://www.museefm.org/expositions-du-musee/"},
    "musee-d-art-et-d-histoire-de-l-hopital-sainte-anne": {
        "liste": "https://mahhsa.fr/expo-du-moment/",
        "fiche": True, "titre": "h5 ~ h5", "dates": "h5"},
}
