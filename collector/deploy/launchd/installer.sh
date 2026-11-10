#!/bin/sh
# Installe (ou réinstalle) les tâches planifiées du collecteur sur macOS.
# Usage, depuis le dossier collector :  sh deploy/launchd/installer.sh
# Pour les retirer :                    sh deploy/launchd/installer.sh --retirer
set -eu
racine=$(cd "$(dirname "$0")/../.." && pwd)
agents="$HOME/Library/LaunchAgents"
domaine="gui/$(id -u)"
mkdir -p "$agents" "$racine/logs"
for modele in "$racine"/deploy/launchd/*.plist; do
  nom=$(basename "$modele")
  label=${nom%.plist}
  launchctl bootout "$domaine/$label" 2>/dev/null || true
  rm -f "$agents/$nom"
  if [ "${1:-}" = "--retirer" ]; then echo "retiré : $label"; continue; fi
  sed "s#__RACINE__#$racine#g" "$modele" > "$agents/$nom"
  plutil -lint "$agents/$nom" > /dev/null
  launchctl bootstrap "$domaine" "$agents/$nom"
  echo "installé : $label"
done
[ "${1:-}" = "--retirer" ] || echo "Vérifier : launchctl list | grep paname"
