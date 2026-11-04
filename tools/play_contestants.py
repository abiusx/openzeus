"""Panhellenic games contestants for play mode: the `contestant*` roles of data/play/walkers.json
(docs/logic/games.md "Contestant figure 0x38", docs/play/walkers.md).

fig_handler_contestant 0x004C30D0 (figure 0x38) picks its picture by Figure +0x0B (resource = the building type that
sent it): 77 college / 81 podium -> packed 0x66F1 (die 0x66F2), 79 gymnasium -> 0x66D7 (0x66D8), 80 stadium ->
0x66D9 (0x66DA), anything else (78 drama school) -> 0x6603 (0x6604). Packed = collection * 512 + group number,
collection 51 = SprMain, group number n = atlas group n - 1. Walking: sprite = first + 8 * anim_frame + d (anim_frame
+1 a tick, wraps at 12; d = direction, prev_direction when >= 8, minus the view rotation); dying (action 4):
die first + min(timer, 7). While its timer runs (actions 6, 8, 10) the figure is hidden (+0x65).
The sim's contestant carries the discipline's building key in w.task (export: `good`), so the role resolves "by good".

    re/venv/bin/python tools/play_contestants.py     # rewrites the contestant lines of data/play/walkers.json
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from play_military import atlas_groups, block  # noqa: E402

HANDLER, HANDLER_LEN = 0x004C30D0, 0x600
# resource (building type) -> (walk, die) packed ids in fig_handler_contestant
PICTURES = {"philosopher": ((77, 81), 0x66F1, 0x66F2), "athlete": ((79,), 0x66D7, 0x66D8),
            "competitor": ((80,), 0x66D9, 0x66DA), "actor": ((78,), 0x6603, 0x6604)}
KEYS = {77: "college", 78: "drama_school", 79: "gymnasium", 80: "stadium", 81: "podium"}   # sim/systems/games.py


def main():
    from disasm import read
    code = read(HANDLER, HANDLER_LEN)
    groups = atlas_groups("SprMain")
    lines = {}
    by = {}
    for name, (types, walk, die) in PICTURES.items():
        for v in (walk, die):                     # the ids are immediates of the handler: check them in the exe
            assert struct.pack("<I", v) in code, f"{v:#x} not in fig_handler_contestant"
            assert v >> 9 == 51, f"{v:#x}: not SprMain"
        assert die == walk + 1
        role = f"contestant_{name}"
        lines[role] = dict(file="SprMain", walk=block("SprMain", groups, walk & 511),
                           die=block("SprMain", groups, die & 511, dirs=1),
                           orig=f"FIG_CONTESTANT (type 56), resource {'/'.join(map(str, types))}: packed {walk:#x}/{die:#x} "
                                f"(fig_handler_contestant {HANDLER:#010x})")
        for t in types:
            by[KEYS[t]] = role
    lines["contestant"] = {"by": "good", "map": by, "fallback_role": "contestant_actor",
                           "orig": "FIG_CONTESTANT (type 56): picture by resource (the sending building's type); "
                                   "hidden while waiting its timer (tools/play_contestants.py)"}
    p = os.path.join(ROOT, "data", "play", "walkers.json")
    src = open(p).read().rstrip().split("\n")
    keep = [l for l in src if not any(l.startswith(f'  "{k}": ') for k in lines)]
    at = keep.index(' "roles": {') + 1
    keep[at:at] = [f'  "{k}": {json.dumps(v)},' for k, v in lines.items()]
    open(p, "w").write("\n".join(keep) + "\n")
    d = json.load(open(p))                         # still valid
    for k in lines:
        print(k, json.dumps(d["roles"][k])[:160])


if __name__ == "__main__":
    main()
