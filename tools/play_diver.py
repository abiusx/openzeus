"""Urchin collector's dive cycle for play mode: data/play/walkers.json roles.diver.work.dive (docs/play/walkers.md
"Urchin collector").

figure_urchin_collector 0x004BAAB0 (figure 44) at its mooring cycles three actions until its timer reaches 408
(urchin_collector_dive 0x004302D0), one animation frame per tick, sprite by action (packed 0x66NN = SprMain atlas
group NN-1, docs/play/walkers.md):
  action 7 (urchin_collector_step_a 0x00430200): 0x66C9 = group_200, 12 frames, then action 8
  action 8 (FUN_00430270; FUN_00430250 sets ready_level = 5): 0x66CA = group_201, 12 frames x 5, then action 9
  action 9 (0x004302D0): 0x66CB = group_202 (16 frames); before tick 408 back to action 7 at frame 8, after it
           the dive plays to its end and the collector swims home (action 10, 0x66CC = group_203, the carry set)
Play mode loops 7 -> 8 x5 -> first 8 frames of 9 ("chain", 80 ticks), then in the cycle whose action-9 check sees the
timer at 408 or more (the timer counts every tick of 7/8/9; checked at cycle offset 72: cycle 5) 7 -> 8 x5 -> all
16 frames of 9 ("last"): 5 x 80 + 12 + 60 + 16 = 488 ticks at the mooring, the sim's work_ticks (tools/build_data.py,
bugs.md 220). The frame counts per action are our reading of the frame advance (FUN_005AF8C0 after the handler;
whether figure_set_action resets the frame is not read): +-1 a segment is possible.

    python3 tools/play_diver.py      # rewrites the diver's "dive" line in data/play/walkers.json
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "data", "play", "walkers.json")
ATLAS = os.path.join(ROOT, "extracted", "sprites", "SprMain", "atlas.json")


def main():
    groups = {gr["id"]: gr for gr in json.load(open(ATLAS))["groups"]}
    first = lambda n: groups[n]["first"]
    dive = {"file": "SprMain", "dirs": 8, "frames": 12, "order": "frame-major",
            "dir_order": ["NE", "E", "SE", "S", "SW", "W", "NW", "N"],
            "chain": [{"start": first(200), "frames": 12},                 # action 7
                      {"start": first(201), "frames": 12, "repeat": 5},    # action 8, ready_level 5
                      {"start": first(202), "frames": 8}],                 # action 9 until frame 8
            "last": [{"start": first(200), "frames": 12},
                     {"start": first(201), "frames": 12, "repeat": 5},
                     {"start": first(202), "frames": 16}],                 # timer >= 408: the dive to its end
            "src": "figure_urchin_collector 0x004BAAB0 actions 7/8/9 (tools/play_diver.py)"}
    cyc = sum(c["frames"] * c.get("repeat", 1) for c in dive["chain"])
    check = cyc - dive["chain"][-1]["frames"]                  # the action-9 check's offset in a cycle
    dive["cycles"] = next(k for k in range(100) if k * cyc + check >= 408)
    work = dive["cycles"] * cyc + sum(c["frames"] * c.get("repeat", 1) for c in dive["last"])
    assert work == 488, work                                    # = urchin_quay work_ticks (tools/build_data.py)
    lines = open(P).read().rstrip("\n").split("\n")
    i = lines.index('  "diver": {')
    j = next(k for k in range(i, len(lines)) if lines[k] == '   "work": {')
    lines = [l for k, l in enumerate(lines) if not (k > j and k < j + 400 and l.startswith('    "dive": '))]
    lines.insert(j + 1, '    "dive": ' + json.dumps(dive) + ",")
    open(P, "w").write("\n".join(lines) + "\n")
    json.load(open(P))                                                     # still valid


if __name__ == "__main__":
    main()
