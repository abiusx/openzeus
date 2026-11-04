#!/bin/bash
# Reset a shared OpenZeus server (tools/server/setup.sh) to its default city: saves/default*.pkl -> saves/shared*.pkl,
# then restart the service. Run as root on the server:  sudo /home/openzeus/openzeus/tools/server/reset.sh
# Make the current city the new default first with:    sudo /home/openzeus/openzeus/tools/server/reset.sh --keep
set -e
D=${OPENZEUS_DIR:-/home/openzeus/openzeus}
cd "$D/saves"
if [ "$1" = "--keep" ]; then
  curl -s -X POST -H 'Content-Type: application/json' -d '{"save":true}' http://127.0.0.1:8080/control >/dev/null || true
  for f in "" .parent .replay; do [ -f "shared$f.pkl" ] && cp "shared$f.pkl" "default$f.pkl"; done
  chown openzeus:openzeus default*.pkl
  echo "default = the current city"
  exit 0
fi
[ -f default.pkl ] || { echo "no saves/default.pkl"; exit 1; }
systemctl stop openzeus
rm -f shared.pkl shared.parent.pkl shared.replay.pkl
for f in "" .parent .replay; do [ -f "default$f.pkl" ] && cp "default$f.pkl" "shared$f.pkl"; done
chown openzeus:openzeus shared*.pkl
systemctl start openzeus
echo "reset to the default city"
