#!/bin/sh
# La nuit du collecteur en une seule tâche, dans l'ordre : collect, validate, publish.
# Pensé pour un portable (launchd sur macOS) : si la machine dormait à l'heure prévue,
# la tâche part au réveil, et les trois étapes restent dans le bon ordre.
# Une validation en échec bloque la publication : le site garde l'export de la veille.
# Journaux : logs/collect.log, logs/validate.log, logs/publish.log, logs/nuit.log.
set -u
ici=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$ici/../logs"
journal="$ici/../logs/nuit.log"
echo "--- $(date -u +%Y-%m-%dT%H:%M:%SZ) début de la nuit" >> "$journal"
"$ici/run.sh" collect;  echo "collect : code $?" >> "$journal"
if "$ici/run.sh" validate; then
  echo "validate : ok" >> "$journal"
  "$ici/run.sh" publish; echo "publish : code $?" >> "$journal"
else
  echo "validate : en échec, publication annulée (le site garde l'export précédent)" >> "$journal"
fi
