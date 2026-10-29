#!/bin/sh
# Lance une commande panade avec le bon environnement et son journal.
# Usage : deploy/run.sh collect | validate | publish | health --alerter
set -eu
racine=$(cd "$(dirname "$0")/.." && pwd)
cd "$racine"
if [ -f .env ]; then set -a; . ./.env; set +a; fi     # PANADE_PUBLISH_URL, PANADE_PUBLISH_TOKEN, PANADE_ALERT_WEBHOOK
mkdir -p logs
exec >> "logs/$1.log" 2>&1
echo "--- $(date -u +%Y-%m-%dT%H:%M:%SZ) panade $*"
exec "$racine/.venv/bin/panade" "$@"
