"""The ore miner's pause after work for play mode: data/play/walkers.json roles.miner.work.pause / pause_silver
(docs/play/walkers.md "Ore miner's pause").

figure_miner 0x004C1310: when the mining (action 8) ends, an ore miner gets action 0xD with timer 0; each tick
case 0xD adds 1 to the timer and past 0x18 (timer 25) turns to action 9 (home). The picture tail, case 0xD, draws
sprite = group_first + timer / 2, no direction: copper SprMain group 44 (DAT_0153ad78 + 0x160), silver group 77
(+ 0x268), orichalc PoseidonImps group 35 (DAT_01554600 + 0x118; group 0 before file version 0x23). Timer 0..24 ->
frames 0..12; the group has 12 pictures, so frame 12 (timer 24) is the next group's first picture (the carry set):
kept as the exe draws it. Ours: the sim's state "pause" (25 ticks, sim/systems/walkers.finish_work) gives the look
["work", start, end, 0, 0, ..., "pause"] (sim/export.gatherer_look); the "clamp" rule of viewer/play/scene.js plays
min(12, ticks since the start / 2). Orichalc has no miner art in ours yet (Poseidon): not written.

    python3 tools/play_miner_pause.py      # rewrites the miner's "pause" lines in data/play/walkers.json
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "data", "play", "walkers.json")
ATLAS = os.path.join(ROOT, "extracted", "sprites", "SprMain", "atlas.json")


def block(first):
    return {"file": "SprMain", "start": first, "dirs": 1, "frames": 13, "order": "frame", "ticks_per_frame": 2,
            "clamp": 12, "src": "figure_miner 0x004C1310 action 0xD: group first + timer / 2 (tools/play_miner_pause.py)"}


def main():
    groups = {gr["id"]: gr for gr in json.load(open(ATLAS))["groups"]}
    lines = open(P).read().rstrip("\n").split("\n")
    i = lines.index('  "miner": {')
    j = next(k for k in range(i, len(lines)) if lines[k] == '   "work": {')
    lines = [ln for k, ln in enumerate(lines)
             if not (j < k < j + 60 and (ln.startswith('    "pause": ') or ln.startswith('    "pause_silver": ')))]
    lines.insert(j + 1, '    "pause_silver": ' + json.dumps(block(groups[77]["first"])) + ",")
    lines.insert(j + 1, '    "pause": ' + json.dumps(block(groups[44]["first"])) + ",")
    open(P, "w").write("\n".join(lines) + "\n")
    d = json.load(open(P))                                                 # still valid
    assert d["roles"]["miner"]["work"]["pause"]["start"] == 2699, d["roles"]["miner"]["work"]["pause"]


if __name__ == "__main__":
    main()
