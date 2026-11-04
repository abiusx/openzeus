"""Oracle run of bug 268 (the palace burns): "See a working city" (VeryEasy: the palace's model fire risk is 0 there)
with the palace's model fire risk (g_building_model 0x00782F70, row 0x75, col 6) poked to 15 (Impossible) and the
palace root's fire risk (+0x48) held at 990, so step 44 (buildings_fire_collapse_risk 0x00492260) ignites it on its
first 1-in-8 day; the camera on the palace. Then dumps every 51 ticks show the burn: the root's counter, the parts,
the ruins (type 0xA9) with their counters, superintendents; shots every 15 s show the pictures.
docs/logic/buildings.md §8.1, docs/play/bugs.md 268; scenario text re/oracle/scenarios/palace-fire.txt (= --script DIR).

    python3 tools/oracle_palace_fire.py --poke > DIR/poke.txt
    python3 tools/oracle_palace_fire.py --script DIR > DIR/script.txt
    ZEUS_POKE=DIR/poke.txt ZEUS_STATE_DUMP=DIR/dump ZEUS_STATE_DUMP_EVERY=51 ZEUS_STATE_DUMP_FROM=561 \
      ZEUS_STATE_DUMP_TO=4500 refs/zeus-poseidon-arm64/build/zeus-run --run zeus-original/app/Zeus.exe --headless \
      --deterministic --write-dir DIR/write --seconds 2700 --state-log DIR/state.txt --script "$(cat DIR/script.txt)" \
      2> DIR/run.log
    re/venv/bin/python tools/oracle_palace_fire.py --report DIR     # per dump: the palace records, ruins, fires

The working city's palace: buildings 351 (root, 4x4 at logical (48, 82)), 352 (4x4 at (48, 86)), 353..374 (1x1 parts),
all type 0x75 (building_create in the composite placement gives every part the root's type).
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402

B, BSZ = 0x0092E658, 0x118            # g_buildings
FIG, FSZ = 0x00DBD788, 0x184          # g_figures
ROOT, PARTS = 351, range(351, 375)
MODEL = 0x00782F70                    # g_building_model, i32[type * 10 + col]
PREFIX = "5:key 27; 12:click 220,101; 17:char 78; 20:click 556,320; 27:click 644,523; 33:click 588,476; 45:rclick 300,300"


def poke():
    out = ["500 da2f64 4 93", "500 da2f68 4 204",                   # camera by the palace (oracle_gods --curse-poke)
           f"600 {MODEL + (0x75 * 10 + 6) * 4:x} 4 15"]              # palace fire risk col 6 = 15 (Impossible)
    out += [f"{t} {B + ROOT * BSZ + 0x48:x} 2 990" for t in range(600, 1400, 5)]   # root fire risk held at 990
    return "\n".join(out)


def script(d):
    acts = [PREFIX]
    for s in range(48, 2700, 3):
        acts.append(f"{s}:rclick 700,300")
        if s >= 390 and s % 15 == 0:
            acts.append(f"{s}:shot {d}/s_{s:04d}.bmp")
    return "; ".join(acts)


def report(d):
    from oracle import Dump
    for p in oracle.dump_files(os.path.join(d, "dump")):
        D = Dump(p)
        r = []
        for i in PARTS:
            a = B + i * BSZ
            st, ty, c = D.at(a, '<B'), D.at(a + 0x10, '<h'), D.at(a + 0x4A, '<h')
            r.append(f"{i}:{st}/{ty:#x}/c{c}" + (f"/f{D.at(a + 0x48, '<h')}" if i == ROOT else ""))
        ruins = []
        for i in range(1, 2000):
            a = B + i * BSZ
            try:
                st, ty = D.at(a, '<B'), D.at(a + 0x10, '<h')
            except KeyError:
                break
            if st and ty == 0xA9:
                ruins.append((D.at(a + 6, '<h'), D.at(a + 8, '<h'), D.at(a + 0x4A, '<h'), i, D.at(a + 0x20, '<h')))
        fires = sum(1 for i in range(1, 2000) if D.at(FIG + i * FSZ + 0x0E, '<B') and D.at(FIG + i * FSZ + 0x0A, '<B') == 10)
        sup = [(D.at(FIG + i * FSZ + 0x14, '<h'), D.at(FIG + i * FSZ + 0x16, '<h'), D.at(FIG + i * FSZ + 0x38, '<B'))
               for i in range(1, 2000) if D.at(FIG + i * FSZ + 0x0E, '<B') and D.at(FIG + i * FSZ + 0x0A, '<B') == 8
               and D.at(FIG + i * FSZ + 0x38, '<B') in (10, 11)]
        print(os.path.basename(p), " ".join(r))
        print("   ruins", len(ruins), sorted(ruins)[:60], "flames", fires, "fighters", sup)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--poke"]:
        print(poke())
    elif a[:1] == ["--script"]:
        print(script(a[1]))
    elif a[:1] == ["--report"]:
        report(a[1])
    else:
        print(__doc__)
