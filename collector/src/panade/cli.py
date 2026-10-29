"""Point d'entrée `panade`. Les commandes du brief arrivent étape par étape."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from panade import db, seed

DB_PAR_DEFAUT = "data/panade.db"
CLASSEUR_PAR_DEFAUT = "data/PP_lieux_v2.xlsx"


def cmd_init(args: argparse.Namespace) -> int:
    """Crée la base et la remplit depuis le classeur, une seule fois."""
    chemin_db = Path(args.db)
    chemin_db.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect(chemin_db)
    try:
        cree = db.init_schema(con)
        print(f"{'Base créée' if cree else 'Base existante'} : {chemin_db} (schéma v{db.SCHEMA_VERSION})")
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

    con = db.connect(args.db)
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

    con = db.connect(args.db)
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
