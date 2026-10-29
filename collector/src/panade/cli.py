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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="panade", description="Panade Collector")
    sub = parser.add_subparsers(dest="commande", required=True)

    init = sub.add_parser("init", help="crée la base et importe le classeur (premier lancement)")
    init.add_argument("--db", default=os.environ.get("PANADE_DB", DB_PAR_DEFAUT),
                      help=f"fichier SQLite (défaut : $PANADE_DB ou {DB_PAR_DEFAUT})")
    init.add_argument("--xlsx", default=CLASSEUR_PAR_DEFAUT,
                      help=f"classeur de départ (défaut : {CLASSEUR_PAR_DEFAUT})")
    init.set_defaults(fonction=cmd_init)

    args = parser.parse_args(argv)
    return args.fonction(args)


if __name__ == "__main__":
    raise SystemExit(main())
