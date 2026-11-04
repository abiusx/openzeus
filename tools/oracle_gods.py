"""Oracle runs of track 1H (gods): pokes and a reader (docs/logic/religion.md "Oracle shots", docs/re/oracle.md).

    python3 tools/oracle_gods.py --attack-poke > DIR/poke.txt     # a jealous god at once, camera on the map centre
    python3 tools/oracle_gods.py --brief DIR/dump/tick_*.bin*      # god figures (type 0x43) and bolts per dump
    python3 tools/oracle_gods.py --jealous-poke > DIR/poke.txt    # working city: six jealous visits, one god a month
    python3 tools/oracle_gods.py --jealous-report DIR            # what the jealous gods did (dumps + state.txt)
    python3 tools/oracle_gods.py --follower-poke > DIR/poke.txt   # working city: Ares' visit turned into Dionysus' attack
    python3 tools/oracle_gods.py --bless-poke > DIR/poke.txt      # working city: camera on Apollo's visit (blessing)
    python3 tools/oracle_gods.py --curse-poke [--bolt] [--cam TICK COL ROW] > DIR/poke.txt   # (ROW even!) Apollo's
                                      # visit turned into an attack (curse), or into Zeus' (bolts, then his curse)

Camera pokes: keep ROW even (the exe keeps 0x00DA2F68 & ~1; an odd row draws the whole map 30 px right, oracle 1F-curse).
--attack-poke: the view's top-left cell 0x00DA2F64 / 0x00DA2F68 = (113, 308) (raw tile (166, 160) near the view's
centre: god_attack_start 0x004F0EA0 puts a jealous god on the road tile nearest the map centre (FUN_004D31E0) when no
composite building stands, in the sandbox (166, 166) by the entry road; COL = ((x - y) * 30 + 6580) / 60, ROW = x + y
- 18 from play mode's camera, tools/oracle_view_compare.py), and the jealousy countdown 0x00FE6A59 = 1
(jealousy_update 0x004F0B50 draws a god at the next monthly update).
--jealous-poke (bug 232, re/oracle/scenarios/god-jealous.txt): "See a working city" (a built city, 2 sanctuaries)
with the sandbox's six jealous gods made eligible one per month (god record 0x00EF5DD8 + 0x34 * g: +0 unfriendly 0,
+1 listed 1, +0x21 may_be_jealous 1; the other five listed 2), that god in the scenario block's friendly slot 14
(0x00FFA450 + 4 * 14, its "may be jealous" byte +0xC4 + 14 = 1: god_attack_slot_assign 0x00587390 only takes a god
from slots 12..17; the working city has Ares and Apollo in 12 / 13) and the jealousy countdown 0x00FE6A59 = 1, poked at
day 2 of each month (the run's tick 0 is day 10 step 20, so day 0 falls on ticks 286 + 816 k): jealousy_update
(day 5) then always draws that god.
Figures g_figures 0x00DBD788 (0x184 each): +0x0A type, +0x0B resource (god id), +0x0E state, +0x14/16 x y, +0x38 action.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402

FIG, FSZ = 0x00DBD788, 0x184
GODS = ["zeus", "poseidon", "demeter", "apollo", "artemis", "ares", "aphrodite", "hermes", "athena", "hephaestus",
        "dionysus", "hades", "hera", "atlas"]


def attack_poke():
    return "\n".join(["5 da2f64 4 113", "5 da2f68 4 308", "5 fe6a59 1 1"])


def brief(paths):
    from oracle import Dump
    for p in paths:
        d = Dump(p)
        out = []
        for i in range(1, 2000):
            a = FIG + i * FSZ
            try:
                st, ty = d.at(a + 0x0E, '<B'), d.at(a + 0x0A, '<B')
            except KeyError:
                break
            if st and ty in (0x43, 0x2D, 0x34, 0x47):
                r = d.at(a + 0x0B, '<B')
                name = GODS[r] if ty == 0x43 and r < 14 else hex(ty)
                out.append(f"{name}#{i}@({d.at(a + 0x14, '<h')},{d.at(a + 0x16, '<h')}) a{d.at(a + 0x38, '<B'):#x}")
        print(os.path.basename(p), " ".join(out))


JEALOUS = [8, 2, 4, 6, 11, 0]          # Athena, Demeter, Artemis, Aphrodite, Hades, Zeus (the sandbox's jealous gods)
GOD_REC = 0x00EF5DD8


def jealous_poke():
    out = []
    for k, god in enumerate(JEALOUS):
        t = 286 + 816 * k + 102
        for g in JEALOUS:
            a = GOD_REC + 0x34 * g
            out += [f"{t} {a:x} 1 0", f"{t} {a + 1:x} 1 {1 if g == god else 2}", f"{t} {a + 0x21:x} 1 1"]
        out += [f"{t} ffa488 4 {god}", f"{t} ffa522 1 1", f"{t} fe6a59 1 1"]
    return "\n".join(out)


def jealous_report(run):
    """Per dump: god figures (type, god, tile, action), alive building count, non-zero curse timers, figures alive;
    from state.txt: every tick where the buildings (zone 35) or curse (126) hash changed."""
    import glob
    import collections
    from oracle import Dump
    B, BS = 0x0092E658, 0x118
    prev_b = None
    acts = collections.defaultdict(set)
    for p in oracle.dump_files(os.path.join(run, "dump")):
        d = Dump(p)
        gods, nfig = [], 0
        for i in range(1, 2000):
            a = FIG + i * FSZ
            if not d.at(a + 0x0E, '<B'):
                continue
            nfig += 1
            ty = d.at(a + 0x0A, '<B')
            if ty in (0x43, 0x2D, 0x34, 0x47):
                r = d.at(a + 0x0B, '<B')
                act = d.at(a + 0x38, '<B')
                name = GODS[r] if ty == 0x43 and r < 14 else hex(ty)
                acts[name].add(act)
                gods.append(f"{name}#{i}@({d.at(a + 0x14, '<h')},{d.at(a + 0x16, '<h')}) a{act:#x}")
        alive = {}
        for i in range(1, 4000):
            a = B + i * BS
            if d.at(a, '<B') == 1:
                alive[i] = d.at(a + 0x10, '<h')
        curse = [(t, d.at(0x00EF60B0 + t, '<B')) for t in range(221) if d.at(0x00EF60B0 + t, '<B')]
        gone = [] if prev_b is None else sorted(set(prev_b) - set(alive))
        print(os.path.basename(p), f"figs {nfig} bld {len(alive)}",
              f"gone {[(i, prev_b[i]) for i in gone]}" if gone else "", f"curse {curse}" if curse else "",
              " ".join(gods))
        prev_b = alive
    print("god actions seen:", {k: sorted(hex(a) for a in v) for k, v in acts.items()})


def follower_poke():
    """re/oracle/scenarios/god-follower.txt: in "See a working city" Ares visits from tick 425 (figure 1848, logical
    (57, 39) at tick 459); at tick 470 that figure becomes Dionysus (+0x0B = 10) in action 0x36 (god_attack_init:
    3 followers 0x47 beside him, then 0x3F / 0x40), Dionysus' record unfriendly + listed with the figure, Ares' record
    without it; the camera cell on raw (101, 84) = logical (57, 40) + the map origin (44, 44): COL = ((x - y) * 30 +
    6580) / 60, ROW = x + y - 18 in raw tiles."""
    f, a, g10, g5 = 1848, FIG + 1848 * FSZ, GOD_REC + 10 * 0x34, GOD_REC + 5 * 0x34
    return "\n".join([f"470 {a + 0x0B:x} 1 10", f"470 {a + 0x38:x} 1 54", f"470 {a + 0x01:x} 1 0",
                      f"470 {g10:x} 1 1", f"470 {g10 + 1:x} 1 1", f"470 {g10 + 0x18:x} 4 {f}", f"470 {g5 + 0x18:x} 4 0",
                      "470 da2f64 4 118", "470 da2f68 4 167"])


def bless_poke():
    """re/oracle/scenarios/god-bless.txt: Apollo's own visit to "See a working city" (from tick ~680 at logical
    (47, 68)); the camera cell (101, 196) on raw (98, 116) from tick 500."""
    return "\n".join(["500 da2f64 4 101", "500 da2f68 4 196"])


def curse_poke(bolt=False):
    """re/oracle/scenarios/god-curse.txt: as god-bless.txt, and at tick 730 Apollo's visiting figure 1802 (walking,
    action 8) gets action 0x36 (god_attack_init 0x004EC4A0: curse the palace 0x38 / 0x39, then the attack's A / B /
    C) with his record unfriendly 1 / listed 1 (+0x18 already the figure); the camera cell (93, 204) on raw (94, 128),
    by the palace (building 351, logical (48, 82), size 4; Apollo curses it from its road at logical (51, 90), action
    0x39 from tick ~1212 to ~2740, no bolt: run 1H-curse2).
    --bolt: the figure becomes Zeus (+0x0B = 0; his record unfriendly / listed / +0x18 = the figure, Apollo's +0x18 =
    0): Zeus' god_attack_init 0x004EC090 sends him straight to bolt the palace (0x3A walk -> 0x3B, bolts 0x34)."""
    f, a, g3, g0 = 1802, FIG + 1802 * FSZ, GOD_REC + 3 * 0x34, GOD_REC
    out = ["500 da2f64 4 101", "500 da2f68 4 196", f"730 {a + 0x38:x} 1 54", f"730 {a + 0x01:x} 1 0",
           "730 da2f64 4 93", "730 da2f68 4 204"]
    if bolt:
        out += [f"730 {a + 0x0B:x} 1 0", f"730 {g0:x} 1 1", f"730 {g0 + 1:x} 1 1", f"730 {g0 + 0x18:x} 4 {f}",
                f"730 {g3 + 0x18:x} 4 0"]
    else:
        out += [f"730 {g3:x} 1 1", f"730 {g3 + 1:x} 1 1"]
    return "\n".join(out)


def main(argv):
    if argv[:1] == ["--attack-poke"]:
        print(attack_poke())
    elif argv[:1] == ["--jealous-poke"]:
        print(jealous_poke())
    elif argv[:1] == ["--follower-poke"]:
        print(follower_poke())
    elif argv[:1] == ["--bless-poke"]:
        print(bless_poke())
    elif argv[:1] == ["--curse-poke"]:
        out = curse_poke("--bolt" in argv)
        if "--cam" in argv:                         # --cam TICK COL ROW: move the camera later (Zeus' curse: 1500 95 227)
            t, c, r = argv[argv.index("--cam") + 1:argv.index("--cam") + 4]
            out += f"\n{t} da2f64 4 {c}\n{t} da2f68 4 {r}"
        print(out)
    elif argv[:1] == ["--jealous-report"]:
        jealous_report(argv[1])
    elif argv[:1] == ["--brief"]:
        brief(argv[1:])
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
