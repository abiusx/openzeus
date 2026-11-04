"""Effect figures (type 6) for play mode: data/play/walkers.json `effects` (docs/play/walkers.md "Effect figures").

The exe makes them only on screen (FUN_004104D0 refuses a spot outside the view; FUN_004106A0 deletes an effect
that left it, every 16 ticks), so they are pictures: the sim reports where the exe calls a spawner (sim/effects.py,
frame `fx`), play mode makes and animates them (viewer/play/effects.js). Pictures and timing from the effect
handler FUN_00410E50 (jump table 0x004117E8, Ghidra DecompAt): picture = packed group + the variant byte (+1),
frame = counter / ticks-per-frame, the effect dies at counter >= ticks * frames. Packed 0x22NN = collection 17
"destruction", atlas group NN - 1.
  subtype 0 (collapse_debris_spawn 0x004CCD40): group by +0x15C = rng % 5: 0x220A, 0x2201..0x2204; 9 frames;
     ticks per frame = +0x59 = (rng & 3) + 1, also its line-move speed (FUN_004106A0 case 0: figure_line_move).
  subtype 1 (lava splash, FUN_00411920): 0x220B + variant (rng % 6), frames 0x12 0x12 0x11 0x13 0x11 0x13, 1 tick.
  subtype 2 (FUN_00411BE0, "drops"): 0x2211 + variant (rng & 3), frames 0x0C 0x0D 0x0F 0x0F, 1 tick.
  subtype 4 (FUN_00412080, the tidal wave's "spray"): 20 frames: counter 1..9 in 0x2236, 10..19 in 0x2238 (% 10).
  subtype 5: 0x2215 + variant, frames as 2.  subtype 7: 0x2205..0x2209 by variant, 8 frames.

    python3 tools/play_effects.py      # rewrites the `effects` key of data/play/walkers.json
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from play_buildings import atlas  # noqa: E402


def first(packed):
    assert packed >> 9 == 0x11
    return atlas("destruction")[0][(packed & 0x1FF) - 1]["first"]


def main():
    eff = {
        "debris": {"file": "destruction", "groups": [first(p) for p in (0x220A, 0x2201, 0x2202, 0x2203, 0x2204)],
                   "frames": 9, "src": "collapse_debris_spawn 0x004CCD40, subtype 0 of FUN_00410E50"},
        "lava": {"file": "destruction", "groups": [first(0x220B + v) for v in range(6)],
                 "frames": [0x12, 0x12, 0x11, 0x13, 0x11, 0x13], "src": "FUN_00411920, subtype 1"},
        "drops": {"file": "destruction", "groups": [first(0x2211 + v) for v in range(4)],
                  "frames": [0x0C, 0x0D, 0x0F, 0x0F], "src": "FUN_00411BE0, subtype 2"},
        "spray": {"file": "destruction", "groups": [first(0x2236), first(0x2238)], "frames": 20,
                  "src": "FUN_00412080, subtype 4: 0x2236 frames 1..9, then 0x2238 frames 0..9 (counter 10..19)"},
    }
    p = os.path.join(ROOT, "data", "play", "walkers.json")
    lines = [l for l in open(p).read().rstrip().split("\n") if not l.startswith(' "effects":')]
    assert lines[-1] == "}", "walkers.json: expected a closing brace on its own line"
    if not lines[-2].endswith(","):
        lines[-2] += ","
    lines.insert(-1, ' "effects": ' + json.dumps(eff))
    open(p, "w").write("\n".join(lines) + "\n")
    json.load(open(p))
    print("effects:", {k: v["groups"] for k, v in eff.items()})


if __name__ == "__main__":
    main()
