"""Point d'entrée `panade`. Les commandes du brief arrivent étape par étape."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from panade import db, seed

DB_PAR_DEFAUT = "data/panade.db"
CLASSEUR_PAR_DEFAUT = "data/PP_lieux_v2.xlsx"


def _ouvrir(chemin: str):
    """Ouvre une base existante (et la migre si elle est ancienne), sans jamais en créer une."""
    if not Path(chemin).is_file():
        print(f"Base introuvable : {chemin}. Premier lancement : panade init", file=sys.stderr)
        return None
    con = db.connect(chemin)
    db.init_schema(con)
    return con


def cmd_init(args: argparse.Namespace) -> int:
    """Crée la base et la remplit depuis le classeur, une seule fois."""
    chemin_db = Path(args.db)
    chemin_db.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect(chemin_db)
    try:
        avant = con.execute("PRAGMA user_version").fetchone()[0]
        db.init_schema(con)
        action = "Base créée" if avant == 0 else "Base migrée" if avant < db.SCHEMA_VERSION else "Base existante"
        print(f"{action} : {chemin_db} (schéma v{db.SCHEMA_VERSION})")
        if not db.est_vide(con):
            print("Déjà initialisée, le classeur n'est pas réimporté.")
            return 0
        if not Path(args.xlsx).is_file():
            print(f"Classeur introuvable : {args.xlsx}", file=sys.stderr)
            return 1
        try:
            rapport = seed.importer(con, args.xlsx)
        except seed.SeedError as exc:
            print(f"Import refusé, rien n'a été écrit ({exc}) :", file=sys.stderr)
            for erreur in exc.erreurs:
                print(f"  - {erreur}", file=sys.stderr)
            return 1
    finally:
        con.close()

    if Path(args.web).is_file():
        from panade import completer
        con = db.connect(chemin_db)
        try:
            n = len(completer.appliquer(con, args.web))
        finally:
            con.close()
        print(f"Découverte web appliquée : {args.web} ({n} changement(s))")
    c = rapport.comptes
    print(f"Import : {args.xlsx}")
    print(f"  familles {c['Familles']} · lieux {c['Lieux']} ({rapport.lieux_verifies} vérifiés)"
          f" · tarifs {c['Tarifs']} · horaires {c['Horaires']} · fermetures {c['Fermetures']}"
          f" · expositions {c['Expositions']} (toutes en_revue)")
    if rapport.legendes_ignorees:
        print(f"  {rapport.legendes_ignorees} ligne(s) de légende ignorée(s)")
    if rapport.logo_du_lieu:
        print(f"  {rapport.logo_du_lieu} expo(s) permanente(s) sans image : logo du lieu à l'export")
    if rapport.avertissements:
        print(f"Avertissements ({len(rapport.avertissements)}) :")
        for message, n in rapport.avertissements.items():
            print(f"  - {message}" + (f" (x{n})" if n > 1 else ""))
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    """Classe un ou plusieurs lieux en T0..T4. N'écrit le tier qu'avec --ecrire."""
    import json

    from panade import probe
    from panade.http import ClientPoli

    con = _ouvrir(args.db)
    if con is None:
        return 1
    try:
        if args.verifies:
            lieux = con.execute("SELECT * FROM lieux WHERE statut = 'verifie' ORDER BY id").fetchall()
        else:
            lieux = [con.execute("SELECT * FROM lieux WHERE id = ?", (i,)).fetchone() for i in args.lieux]
            inconnus = [i for i, l in zip(args.lieux, lieux) if l is None]
            if inconnus:
                print(f"Lieu inconnu : {', '.join(inconnus)}", file=sys.stderr)
                return 1
        if not lieux:
            print("Aucun lieu à sonder.", file=sys.stderr)
            return 1
        resultats = []
        with ClientPoli() as client:
            for lieu in lieux:
                sonde = probe.sonder(lieu, client)
                resultats.append(sonde.en_json())
                if args.ecrire and sonde.statut == "ok" and sonde.tier and lieu["tier"] != "T4":
                    with con:
                        con.execute("UPDATE lieux SET tier = ? WHERE id = ?", (sonde.tier, lieu["id"]))
        print(json.dumps(resultats[0] if len(resultats) == 1 else resultats, ensure_ascii=False, indent=2))
    finally:
        con.close()
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    """Trouve la page des expositions d'un lieu et en garde une fixture. Aucun appel de modèle."""
    import json
    from datetime import date

    from panade import discover
    from panade.http import ClientPoli

    con = _ouvrir(args.db)
    if con is None:
        return 1
    try:
        lieu = con.execute("SELECT * FROM lieux WHERE id = ?", (args.lieu,)).fetchone()
        if lieu is None:
            print(f"Lieu inconnu : {args.lieu}", file=sys.stderr)
            return 1
        with ClientPoli() as client:
            resultat = discover.decouvrir(lieu, client, Path(args.fixtures), date.today())
        if args.ecrire and resultat.statut == "ok" and resultat.expositions and resultat.url_demandee != lieu["expos_url"]:
            with con:
                con.execute("UPDATE lieux SET expos_url = ? WHERE id = ?", (resultat.url_demandee, lieu["id"]))
            resultat.detail += f" ; expos_url mise à jour : {resultat.url_demandee}"
        print(json.dumps(resultat.en_json(), ensure_ascii=False, indent=2))
        return 0 if resultat.statut == "ok" else 2
    finally:
        con.close()


def _alerter_muets(chemin_db: str) -> None:
    """Un lieu silencieux deux nuits de suite déclenche une alerte, sans attendre le rapport du lundi."""
    from datetime import date

    from panade import alerts, health

    con = db.connect(chemin_db)
    try:
        for muet in health.lieux_muets(con, date.today()):
            if health.alerte_du_soir(muet):
                alerts.notifier("alerte", muet.message, dossier=Path(chemin_db).parent)
    finally:
        con.close()


def cmd_collect(args: argparse.Namespace) -> int:
    """Fait tourner les extracteurs. Aucun appel de modèle."""
    from panade import collect
    from panade.http import ClientPoli

    con = _ouvrir(args.db)
    if con is None:
        return 1
    try:
        with ClientPoli() as client:
            resultats = collect.collecter(con, client, lieux_ids=args.lieu)
    finally:
        con.close()
    _alerter_muets(args.db)
    comptes: dict[str, int] = {}
    for r in resultats:
        comptes[r.statut] = comptes.get(r.statut, 0) + 1
        if r.statut == "sans_extracteur" and not args.lieu:
            continue    # 40 lignes inutiles : l'inventaire est dans `panade health`
        suite = f" ({r.nouveaux} nouvelle(s), {r.modifies} modifiée(s), {r.renvoyes_en_revue} renvoyée(s) en relecture)" \
            if r.statut == "ok" else f" {r.detail}" if r.detail else ""
        print(f"{r.statut:16} {r.lieu}{suite}")
    print("Bilan : " + ", ".join(f"{n} {s}" for s, n in sorted(comptes.items())))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Schéma, cohérence, dédoublonnage, confiance, gratuité. Code de sortie 1 si la base est en cause."""
    from datetime import date

    from panade import validate

    con = _ouvrir(args.db)
    if con is None:
        return 1
    try:
        r = validate.valider(con, date.today())
        en_revue = con.execute("SELECT COUNT(*) FROM expositions WHERE etat = 'en_revue'").fetchone()[0]
        publiees = con.execute("SELECT COUNT(*) FROM expositions WHERE etat = 'publie'").fetchone()[0]
    finally:
        con.close()
    print(f"{r.verifiees} expositions vérifiées : {publiees} publiées, {en_revue} en relecture")
    print(f"  ce passage : {r.promues} promue(s), {r.bloquees} bloquée(s), {r.doublons} doublon(s) écarté(s), "
          f"{r.gratuite_changee} gratuité(s) modifiée(s) sans relecture")
    for p in r.perimes[:10]:
        print(f"  périmé (plus de {validate.gratuite.PEREMPTION_JOURS} jours) : {p}")
    if len(r.perimes) > 10:
        print(f"  ... et {len(r.perimes) - 10} autre(s)")
    for p in r.problemes_graves:
        print(f"  GRAVE : {p}", file=sys.stderr)
    return 1 if r.problemes_graves else 0


def cmd_review(args: argparse.Namespace) -> int:
    """Ouvre l'écran de relecture local (127.0.0.1 uniquement)."""
    try:
        import uvicorn

        from panade.review.app import creer_app
    except ImportError:
        print("L'écran de relecture demande : pip install -e '.[review]'", file=sys.stderr)
        return 1
    con = _ouvrir(args.db)
    if con is None:
        return 1
    con.close()
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Écran de relecture : {url}   (Ctrl+C pour quitter)")
    if not args.sans_navigateur:
        import webbrowser
        webbrowser.open(url)
    uvicorn.run(creer_app(args.db), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Produit l'export du jour. Ne publie pas."""
    import json
    from datetime import date

    from panade import export

    con = _ouvrir(args.db)
    if con is None:
        return 1
    try:
        resultat = export.construire(con, date.today())
        chemin = export.ecrire(resultat, Path(args.dossier) / "exports")
    finally:
        con.close()
    c = resultat.contenu["compte"]
    print(f"{chemin} : {c['lieux']} lieux, {c['expositions']} expositions")
    for expo_id, motif in resultat.exclues:
        print(f"  exposition {expo_id} sortie de l'export, repartie en relecture : {motif}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    """Vérifie les garde-fous puis pousse l'export vers le site."""
    import json
    from datetime import date

    from panade import publish

    con = _ouvrir(args.db)
    if con is None:
        return 1
    try:
        resume = publish.publier(con, date.today(), args.dossier, a_blanc=args.a_blanc)
    except publish.PublicationRefusee as exc:
        print(f"Publication refusée : {exc.raison}", file=sys.stderr)
        return exc.code
    finally:
        con.close()
    print(json.dumps(resume, ensure_ascii=False, indent=2))
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """Lieux muets, extracteurs cassés, données périmées. Code de sortie 1 s'il y a une alerte."""
    import json
    from datetime import date

    from panade import alerts, health

    con = _ouvrir(args.db)
    if con is None:
        return 1
    try:
        r = health.rapport(con, date.today(), args.dossier)
    finally:
        con.close()
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(f"Santé du {r['date']} : {r['lieux'].get('verifie', 0)} lieux vérifiés, {r['lieux'].get('a_verifier', 0)} à vérifier")
        print(f"  à relire : {r['relecture']['en_attente']} exposition(s)")
        pub = r["publication"]
        print(f"  dernière publication : {pub['derniere'] or 'aucune'}" + (f" (il y a {pub['jours']} jour(s))" if pub["jours"] is not None else ""))
        for titre, liste in (("alerte", r["alertes"]),):
            for a in liste:
                print(f"  ALERTE : {a}")
        if r["perimees"]["verifications"]:
            print(f"  données de plus de {health.gratuite.PEREMPTION_JOURS} jours : {len(r['perimees']['verifications'])}")
            for p in r["perimees"]["verifications"][:8]:
                print(f"    - {p}")
        for h in r["perimees"]["horaires_expires"]:
            print(f"  horaires expirés : {h['lieu_id']} (valides jusqu'au {h['jusqu_au']})")
        if r["sans_extracteur"]:
            print(f"  lieux vérifiés sans extracteur : {len(r['sans_extracteur'])}")
            for x in r["sans_extracteur"]:
                print(f"    - {x['lieu']} ({x['raison']})")
    if args.alerter:
        for a in r["alertes"]:
            alerts.notifier("alerte", a, dossier=args.dossier)
    return 1 if r["alertes"] else 0


def cmd_completer(args: argparse.Namespace) -> int:
    """Applique data/lieux_web.json : comble les trous, ne réécrit jamais une saisie humaine."""
    from panade import completer

    con = _ouvrir(args.db)
    if con is None:
        return 1
    try:
        changements = completer.appliquer(con, args.fichier)
    finally:
        con.close()
    for c in changements:
        print(f"  {c}")
    print(f"{len(changements)} changement(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="panade", description="Panade Collector")
    sub = parser.add_subparsers(dest="commande", required=True)
    commun = argparse.ArgumentParser(add_help=False)
    commun.add_argument("--db", default=os.environ.get("PANADE_DB", DB_PAR_DEFAUT),
                        help=f"fichier SQLite (défaut : $PANADE_DB ou {DB_PAR_DEFAUT})")

    sonde = sub.add_parser("probe", parents=[commun], help="classe des lieux en T0..T4 (ne scrape rien)")
    sonde.add_argument("lieux", nargs="*", metavar="lieu_id")
    sonde.add_argument("--verifies", action="store_true", help="tous les lieux au statut vérifié")
    sonde.add_argument("--ecrire", action="store_true", help="enregistre le tier trouvé (jamais sur un lieu T4)")
    sonde.set_defaults(fonction=cmd_probe)

    completion = sub.add_parser("completer", parents=[commun], help="applique les pages officielles trouvées (data/lieux_web.json)")
    completion.add_argument("--fichier", default="data/lieux_web.json")
    completion.set_defaults(fonction=cmd_completer)

    collecte = sub.add_parser("collect", parents=[commun], help="fait tourner les extracteurs (aucun appel de modèle)")
    collecte.add_argument("--lieu", action="append", metavar="lieu_id", help="un lieu seulement (répétable)")
    collecte.set_defaults(fonction=cmd_collect)

    relecture = sub.add_parser("review", parents=[commun], help="ouvre l'écran de relecture local")
    relecture.add_argument("--port", type=int, default=8765)
    relecture.add_argument("--sans-navigateur", action="store_true")
    relecture.set_defaults(fonction=cmd_review)

    exportation = sub.add_parser("export", parents=[commun], help="produit l'export du jour (ne publie pas)")
    exportation.add_argument("--dossier", default="data", help="dossier des exports (défaut : data)")
    exportation.set_defaults(fonction=cmd_export)

    publication = sub.add_parser("publish", parents=[commun], help="vérifie les garde-fous puis pousse vers le site")
    publication.add_argument("--dossier", default="data", help="dossier des exports (défaut : data)")
    publication.add_argument("--a-blanc", action="store_true", help="tout vérifier sans rien envoyer")
    publication.set_defaults(fonction=cmd_publish)

    sante = sub.add_parser("health", parents=[commun], help="lieux muets, extracteurs cassés, données périmées")
    sante.add_argument("--dossier", default="data", help="dossier des exports (défaut : data)")
    sante.add_argument("--json", action="store_true")
    sante.add_argument("--alerter", action="store_true", help="envoie aussi chaque alerte (journal, webhook)")
    sante.set_defaults(fonction=cmd_health)

    validation = sub.add_parser("validate", parents=[commun],
                                help="schéma, cohérence, dédoublonnage, confiance, gratuité")
    validation.set_defaults(fonction=cmd_validate)

    decouverte = sub.add_parser("discover", parents=[commun],
                                help="trouve la page des expositions d'un lieu et en garde une fixture (sans modèle)")
    decouverte.add_argument("lieu", metavar="lieu_id")
    decouverte.add_argument("--fixtures", default="tests/fixtures/pages", help="dossier des fixtures")
    decouverte.add_argument("--ecrire", action="store_true",
                            help="enregistre l'expos_url trouvée si l'extracteur y lit au moins une expo")
    decouverte.set_defaults(fonction=cmd_discover)

    init = sub.add_parser("init", parents=[commun],
                          help="crée la base et importe le classeur (premier lancement)")
    init.add_argument("--xlsx", default=CLASSEUR_PAR_DEFAUT,
                      help=f"classeur de départ (défaut : {CLASSEUR_PAR_DEFAUT})")
    init.add_argument("--web", default="data/lieux_web.json", help="pages officielles à appliquer après la graine")
    init.set_defaults(fonction=cmd_init)

    args = parser.parse_args(argv)
    return args.fonction(args)


if __name__ == "__main__":
    raise SystemExit(main())
