"""The player's soldiers' walk tick by tick, exe against ours (TODO 11-03, bugs.md 432; docs/logic/military.md
"Soldiers on the map"): "See a working city" with company 1 (rabble) mobilized as tools/oracle_invcity.py stage 2,
dumps every tick 36..290 (re/oracle/runs/1B-inv-city-march, made by
`OIC_NAME=1B-inv-city-march OIC_EVERY=1 OIC_FROM=36 OIC_TO=290 OIC_SECS=430 python3 tools/oracle_invcity.py run 2`).
Per dump: company 1's members (logical tile, tile progress +0x39, action) in the exe and ours (oracle_invcity's
ours_game, exe dump k = ours' tick T0 + k), paired by slot; prints the dumps where the tiles differ and a summary
(tile changes: the tick each soldier enters each tile).

    python3 tools/oracle_soldier_walk.py [FROM TO] [--all] [--acts]
    OSW_RUN=1B-inv-city-horse OSW_COMP=9 python3 tools/oracle_soldier_walk.py ...   # horseman company 9 (hold),
                                                  # dumps every tick 36..2404 (oracle_invcity.py's docstring)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
os.environ.setdefault("OIC_NAME", os.environ.get("OSW_RUN", "1B-inv-city-march"))
os.environ.setdefault("OIC_COMP", os.environ.get("OSW_COMP", "1"))

import oracle_invcity as OIC  # noqa: E402
import oracle_military as M  # noqa: E402
from oracle import Dump, dump_files  # noqa: E402

ACTS = False

RUN = os.path.join(OIC.RUNS, os.environ["OIC_NAME"])
COMPANY = OIC.COMP


def exe_members(d):
    f = M.form(d, COMPANY)
    out = {}
    for k, i in enumerate(f["members"]):
        if i <= 0:
            continue
        x = M.fig(d, i)
        if x["state"] == 1 and not x["hidden"]:
            out[x["slot"]] = (x["x"], x["y"], x["prog"], x["action"])
    return out


ACTION = {"march": 9, "hold": 10, "special": 0xB, "attack": 0x11, "gohome": 7, "out": 0xD, "charge": 0x10,
          "regroup": 0x12}


def ours_members(g):
    """Ours' members: (tile, progress, the exe's action number: dying 4, fighting 5, else by task)."""
    from sim.military import forces
    c = forces.companies(g).get(COMPANY)
    ox, oy = g.world.origin
    out = {}
    for w in forces.members(g, c) if c else []:
        a = 4 if w.anim == "die" else 5 if w.anim == "fight" else ACTION.get(w.task, w.task)
        out[w.slot] = (w.x - ox, w.y - oy, w.__dict__.get("fprog", 15), a)
    return out


def main(argv):
    global ACTS
    show_all = "--all" in argv
    ACTS = "--acts" in argv                        # also print the dumps where only an action differs
    argv = [a for a in argv if a not in ("--all", "--acts")]
    lo, hi = (int(argv[0]), int(argv[1])) if len(argv) > 1 else (0, 10 ** 9)
    files = {int(os.path.basename(p)[5:11]): p for p in dump_files(os.path.join(RUN, "dump"))}
    g = OIC.ours_game()
    import oracle_invasion                         # the invaders' special-mode roll takes the exe's outcome (compare)
    from sim.military import invaders
    oracle_invasion._replay_special(g, [(OIC.T0 + k, p) for k, p in sorted(files.items())], invaders)
    bad = n = pbad = abad = 0
    enter_e, enter_o = {}, {}
    for k in sorted(files):
        if k < max(lo, OIC.MOB_TICK) or k > hi:
            continue
        g.step(OIC.T0 + k - g.tick)
        e, o = exe_members(Dump(files[k])), ours_members(g)
        for s, v in e.items():
            if enter_e.setdefault(s, [])[-1:] != [v[:2]]:
                enter_e[s].append(v[:2])
                enter_e.setdefault((s, "t"), []).append(k)
        for s, v in o.items():
            if enter_o.setdefault(s, [])[-1:] != [v[:2]]:
                enter_o[s].append(v[:2])
                enter_o.setdefault((s, "t"), []).append(k)
        n += 1
        same = {s: e[s][:2] for s in e} == {s: o[s][:2] for s in o}
        bad += not same
        pbad += {s: e[s][:3] for s in e} != {s: o[s][:3] for s in o}
        acts = e == o
        abad += not acts
        if show_all or not same or (ACTS and not acts):
            print(f"{k:4d} {'=' if same else 'x'} exe  " + " ".join(f"{s}:{v[0]},{v[1]}p{v[2]}a{v[3]}" for s, v in sorted(e.items())))
            if not same or show_all or not acts:
                print("       ours " + " ".join(f"{s}:{v[0]},{v[1]}p{v[2]}a{v[3]}" for s, v in sorted(o.items())))
    for s in sorted(k for k in enter_e if isinstance(k, int)):
        te, to = enter_e.get((s, "t"), []), enter_o.get((s, "t"), [])
        pe, po = enter_e[s], enter_o.get(s, [])
        print(f"slot {s}: exe {len(pe)} tiles, ours {len(po)}; same path {pe == po}; "
              f"entry ticks exe - ours: {[a - b for a, b in zip(te, to)][:24]}")
    print(f"{n} dumps compared, {bad} with tiles differing, {pbad} with tile or tile progress differing, {abad} with "
          f"tile, progress or action differing")


if __name__ == "__main__":
    main(sys.argv[1:])
