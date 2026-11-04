"""Fishing and urchin spots for play mode: data/play/walkers.json `water_life` (docs/play/walkers.md "Water life").

The exe spawns, at map start (FUN_004E0D80, editor_mode == 0), one effect figure (type 6) at each fishing point
(FUN_00412B60, subtype 0x0D) and urchin point (FUN_00412C60, subtype 0x13) of the scenario block
(docs/logic/map-terrain.md). Its handler (0x004AF530 -> 0x00410670 -> 0x00410E50, every tick) draws SprAmbient
0x2010 (fish) / 0x205C (urchins): counter +1 a tick, wraps at 3 * frames, frame = counter / 3; start counter
rng & 0x1F. Never mirrored. Screen position from the oracle (re/oracle/scenarios/water.txt, 4 views): the
walker spot of the raw point (x + 8/15, y + 8/15) plus (2, -20) px. The map's points are logical (raw = logical +
World.origin, sim/world.py; fitted before that as logical + 23/15). 8/15 may be the (8, 8) that FUN_00412B60 passes
to FUN_00410600 (not read).

    python3 tools/play_water_life.py      # rewrites the `water_life` key of data/play/walkers.json
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from play_buildings import amb_first  # noqa: E402


def entry(packed, src):
    f = amb_first(packed)
    return {"file": "SprAmbient", "first": f, "frames": amb_first(packed + 1) - f, "ticks_per_frame": 3,
            "phase": 32, "at": [8 / 15, 8 / 15], "px": [2, -20], "src": src}


def main():
    p = os.path.join(ROOT, "data", "play", "walkers.json")
    wl = {"fish": entry(0x2010, "0x2010 at fishing points (FUN_00412B60, subtype 0x0D)"),
          "urchin": entry(0x205C, "0x205C at urchin points (FUN_00412C60, subtype 0x13)")}
    # the file is partly hand-formatted: replace or append one line, leave the rest as it is
    lines = [l for l in open(p).read().rstrip().split("\n") if not l.startswith(' "water_life":')]
    assert lines[-1] == "}", "walkers.json: expected a closing brace on its own line"
    if not lines[-2].endswith(","):
        lines[-2] += ","
    lines.insert(-1, ' "water_life": ' + json.dumps(wl))
    open(p, "w").write("\n".join(lines) + "\n")
    json.load(open(p))                             # still valid
    print("water_life:", wl)


if __name__ == "__main__":
    main()
