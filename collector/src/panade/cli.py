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

    collecte = sub.add_parser("collect", parents=[commun], help="fait tourner les extracteurs (aucun appel de modèle)")
    collecte.add_argument("--lieu", action="append", metavar="lieu_id", help="un lieu seulement (répétable)")
    collecte.set_defaults(fonction=cmd_collect)

    relecture = sub.add_parser("review", parents=[commun], help="ouvre l'écran de relecture local")
    relecture.add_argument("--port", type=int, default=8765)
    relecture.add_argument("--sans-navigateur", action="store_true")
    relecture.set_defaults(fonction=cmd_review)

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
    init.set_defaults(fonction=cmd_init)

    args = parser.parse_args(argv)
    return args.fonction(args)


if __name__ == "__main__":
    raise SystemExit(main())
