"""Oracle runs of bugs 290 / 292 (a building with parts burns): "See a working city" (VeryEasy) with one building's
fire risk (+0x48) held at 990, so step 44 (buildings_fire_collapse_risk 0x00492260) ignites it on its first 1-in-8
day (the model's fire risk at VeryEasy is non-zero for both: ranch 5, agora 6); the camera on that building. Dumps
every 51 ticks show the burn (the records of the chain, the ruins (type 0xA9) with their counters, flames, horses);
shots every 15 s show the pictures. docs/logic/buildings.md §8.2, docs/play/bugs.md 290 / 292.

    TARGET = ranch (the horse ranch 572 (3x3, logical (76, 60)) + its corral 573 (4x4, (79, 59)), 6 horses)
           | agora (the common agora 494 at (50, 97) + stall parts 495..497, vendors 498..500)
    DIR=$PWD/re/oracle/runs/NAME; mkdir -p $DIR/dump          # absolute paths (the dumps need the folder)
    python3 tools/oracle_fire_parts.py --poke TARGET [--burn TICK] > DIR/poke.txt
    python3 tools/oracle_fire_parts.py --script DIR > DIR/script.txt
    ZEUS_POKE=DIR/poke.txt ZEUS_STATE_DUMP=DIR/dump ZEUS_STATE_DUMP_EVERY=51 ZEUS_STATE_DUMP_FROM=561 \
      ZEUS_STATE_DUMP_TO=4500 refs/zeus-poseidon-arm64/build/zeus-run --run zeus-original/app/Zeus.exe --headless \
      --deterministic --write-dir DIR/write --seconds 2700 --state-log DIR/state.txt --script "$(cat DIR/script.txt)" \
      2> DIR/run.log
    re/venv/bin/python tools/oracle_fire_parts.py --report TARGET DIR

Runs: re/oracle/runs/1F-ranchfire, 1F-agorafire (no --burn: put out by a superintendent), 1F-ranchburn
(--burn 770), 1F-agoraburn (--burn 1280): the counter poked to 15 after the ignition, so the building turns to ruins. Camera cells: COL = ((x - y) * 30 + 6580) / 60,
ROW = x + y - 18 (even) in raw tiles (logical + (44, 44)), as tools/oracle_gods.py.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402

B, BSZ = 0x0092E658, 0x118            # g_buildings
FIG, FSZ = 0x00DBD788, 0x184          # g_figures
TARGETS = {"ranch": dict(root=572, chain=(572, 573), cam=(117, 206)),
           "agora": dict(root=494, chain=(494, 495, 496, 497, 498, 499, 500), cam=(86, 218))}
PREFIX = "5:key 27; 12:click 220,101; 17:char 78; 20:click 556,320; 27:click 644,523; 33:click 588,476; 45:rclick 300,300"


def poke(t, burn=None):
    T = TARGETS[t]
    out = [f"500 da2f64 4 {T['cam'][0]}", f"500 da2f68 4 {T['cam'][1]}"]
    out += [f"{k} {B + T['root'] * BSZ + 0x48:x} 2 990" for k in range(600, 1400, 5)]
    if burn:                          # the root's fire counter (+0x4A) to 15 at tick BURN (after the ignition):
        out.append(f"{burn} {B + T['root'] * BSZ + 0x4A:x} 2 15")   # 17 two days later, before a superintendent
    return "\n".join(sorted(out, key=lambda l: int(l.split()[0])))


def script(d):
    acts = [PREFIX]
    for s in range(48, 2700, 3):
        acts.append(f"{s}:rclick 700,300")
        if s >= 390 and s % 15 == 0:
            acts.append(f"{s}:shot {d}/s_{s:04d}.bmp")
    return "; ".join(acts)


def report(t, d):
    from oracle import Dump
    T = TARGETS[t]
    for p in oracle.dump_files(os.path.join(d, "dump")):
        D = Dump(p)
        r = []
        for i in T["chain"]:
            a = B + i * BSZ
            r.append(f"{i}:{D.at(a, '<B')}/{D.at(a + 0x10, '<h')}/c{D.at(a + 0x4A, '<h')}/fp{D.at(a + 0x4C, '<B')}"
                     f"/f{D.at(a + 0x48, '<h')}/p{D.at(a + 0x38, '<h')}/n{D.at(a + 0x3A, '<h')}")
        ruins = []
        for i in range(1, 2000):
            a = B + i * BSZ
            try:
                st, ty = D.at(a, '<B'), D.at(a + 0x10, '<h')
            except KeyError:
                break
            if st and ty == 0xA9:
                ruins.append((D.at(a + 6, '<h'), D.at(a + 8, '<h'), D.at(a + 0x4A, '<h'), i))
        live = lambda i: D.at(FIG + i * FSZ + 0x0E, '<B')
        ftype = lambda i: D.at(FIG + i * FSZ + 0x0A, '<B')
        fires = sum(1 for i in range(1, 2000) if live(i) and ftype(i) == 10)
        horses = [(i, live(i), D.at(FIG + i * FSZ + 0x14, '<h'), D.at(FIG + i * FSZ + 0x16, '<h'))
                  for i in range(1, 2000) if live(i) and ftype(i) == 43]
        print(os.path.basename(p), " ".join(r))
        print("   ruins", len(ruins), sorted(ruins)[:60], "flames", fires, "horses", horses)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--poke"]:
        print(poke(a[1], int(a[a.index("--burn") + 1]) if "--burn" in a else None))
    elif a[:1] == ["--script"]:
        print(script(a[1]))
    elif a[:1] == ["--report"]:
        report(a[1], a[2])
    else:
        print(__doc__)
