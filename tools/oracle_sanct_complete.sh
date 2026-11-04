#!/bin/bash
# A sanctuary placed on Open Play Sandbox (Easy, "Allow All" cheat 0x00665DF0) and completed by pokes, then checked
# against ours (bugs.md 214, docs/logic/monuments.md "Extras on completion"; scenario re/oracle/scenarios/e1-sanct.txt).
#   tools/oracle_sanct_complete.sh OUT KEY MENU_Y ORIENT
# KEY e.g. sanctuary_athena; MENU_Y the god's row in the Sanctuaries menu (Zeus 328, Demeter 352, Artemis 376,
# Aphrodite 400, Athena 424, Hades 448: the sandbox's gods only); ORIENT 0..3 = the R key count DAT_00DA23C4 (poked
# every tick 120..184: the emulator has no GetAsyncKeyState; the tool selection resets it). The pieces go to their last
# stage at tick 200 (tools/oracle_monument.py --complete), the completion pass applies the extras, the message is
# closed at 140 s; dumps every 5 ticks, shots OUT/ghost.bmp, placed.bmp, done.bmp. Then tools/e1_sanct_check.py.
set -e
cd "$(dirname "$0")/.."
O=$1; KEY=$2; Y=$3; NR=$4
rm -rf "$O"; mkdir -p "$O/dump"
python3 tools/oracle_monument.py --complete "$O/c.poke" "$KEY" 1 200
{ printf "5 665df0 4 1\n5 da2f64 4 109\n5 da2f68 4 118\n"; tail -n +2 "$O/c.poke"; for t in $(seq 120 184); do echo "$t da23c4 4 $NR"; done; } > "$O/poke.txt"
S=$(sed -n '/^[0-9]/p' re/oracle/scenarios/e1-sanct.txt | sed "s#DIR#$O#g; s#MENU_Y#$Y#g")
ZEUS_POKE="$O/poke.txt" ZEUS_STATE_DUMP="$O/dump" ZEUS_STATE_DUMP_EVERY=5 refs/zeus-poseidon-arm64/build/zeus-run \
  --run zeus-original/app/Zeus.exe --headless --deterministic --write-dir "$O/write" --seconds 162 \
  --state-log "$O/state.txt" --script "$S" > "$O/run.log" 2>&1
python3 tools/e1_sanct_check.py "$O" "$KEY"
