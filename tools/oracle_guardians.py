"""Guardians (docs/logic/heroes-monsters.md "Guardians"): Ares' Dragon following his figure (action 0x12, 0x00533670),
ours (sim/heroes/guardians.py) against the oracle run 1I-dragon.

    python3 tools/oracle_guardians.py [RUN]        (default re/oracle/runs/1I-dragon)

RUN = re/oracle/scenarios/dragon.txt ("See a working city", dumps every tick 410..1010): Ares visits from tick 419 and
monster_spawn puts his Dragon (figure 1847, monster 7) at the sanctuary's altar access (logical (57, 52)) in action 0x12
with +0x68 = Ares (figure 1848). Ours: Adventures/tutorial15.sav imported (sim/savimport, raw = logical + (44, 44)),
the Dragon spawned at the same tile and tick by guardians.spawn, its leader a god figure that is put, every tick, on
the tile Ares has in the dump of that tick (Ares' slot comes after the Dragon's, so the Dragon's handler sees his
position from before his own move). Compared: the Dragon's tiles in order, the ticks it enters each (ours takes a step
whole at its start, the exe changes the tile at sub-step 8 of 15: a constant lead is expected, its spread is the
check), +0x44 (the 800-tick follow count) against ours' ticks since the spawn.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

FIG, FSZ = 0x00DBD788, 0x184
DRAGON, ARES = 1847, 1848
ORIGIN = (44, 44)


def exe(run):
    from oracle import Dump, dump_files
    rows = {}
    for f in dump_files(os.path.join(run, "dump")):
        t = int(os.path.basename(f)[5:11])
        d = Dump(f)
        b, a = FIG + DRAGON * FSZ, FIG + ARES * FSZ
        r = rows[t] = dict(lx=d.at(a + 0x14, "<h"), ly=d.at(a + 0x16, "<h"))
        if d.at(b + 0x0E, "<B") == 1 and d.at(b + 0x0A, "<B") == 0x44:
            r.update(x=d.at(b + 0x14, "<h"), y=d.at(b + 0x16, "<h"), act=d.at(b + 0x38, "<B"),
                     el=d.at(b + 0x44, "<h"), prog=d.at(b + 0x39, "<b"))
    return rows


def ours(rows):
    from sim import savimport
    from sim.heroes import guardians
    from sim.systems import walkers
    g = savimport.load(os.path.join(ROOT, "zeus-original/app/Adventures/tutorial15.sav"))
    t0 = min(t for t, r in rows.items() if "x" in r)
    ox, oy = ORIGIN
    sanct = next(b for b in g.buildings.values() if b.key == "sanctuary_ares")
    sanct.access = (rows[t0]["x"] + ox, rows[t0]["y"] + oy)
    L = walkers.new_walker(g, role="god", home=sanct.id, x=rows[t0]["lx"] + ox, y=rows[t0]["ly"] + oy)
    L.god, L.task = 5, "visit"
    g.walkers[L.id] = L
    g.tick = t0 - 1                              # the spawn's tick (dump t0 = after it): sanctuary_update makes it
    w = guardians.spawn(g, 7, 5, sanct, L)       # before the walker pass, which runs its first call in that tick
    out = {}
    for t in range(t0 - 1, max(rows)):
        r = rows.get(t)
        if r is None:
            break
        if (r["lx"], r["ly"]) == (0, 0):             # Ares made in this tick too (dump t is before): where he
            r = rows[t + 1]                          # stands at the next dump (action 0x0A: he does not move)
        g.tick = t
        L.x, L.y = r["lx"] + ox, r["ly"] + oy
        guardians.act(g, w)
        out[t + 1] = (w.x - ox, w.y - oy, w.act, t + 1 - w.follow_t0, w.prog)
    return out


def main(argv):
    run = argv[0] if argv else os.path.join(ROOT, "re", "oracle", "runs", "1I-dragon")
    rows = exe(run)
    o = ours(rows)
    rows = {t: r for t, r in rows.items() if "x" in r}
    ex = [(t, (r["x"], r["y"])) for t, r in sorted(rows.items())]
    ou = [(t, v[:2]) for t, v in sorted(o.items())]
    seq = lambda s: [p for i, (t, p) in enumerate(s) if i == 0 or s[i - 1][1] != p]
    when = lambda s: [t for i, (t, p) in enumerate(s) if i and s[i - 1][1] != p]
    se, so = seq(ex), seq(ou)
    n = min(len(se), len(so))
    same = se[:n] == so[:n]
    print(f"tiles: exe {len(se)}, ours {len(so)}, first {n} {'same' if same else 'DIFFER'}")
    if not same:
        k = next(i for i in range(n) if se[i] != so[i])
        print(f"  first difference at step {k}: exe {se[k - 1:k + 3]} ours {so[k - 1:k + 3]}")
    we, wo = when(ex), when(ou)
    lead = [a - b for a, b in zip(we, wo)]
    print(f"tile changes: exe {we[:6]}..., ours {wo[:6]}...; exe - ours: min {min(lead)} max {max(lead)}")
    els = [(t, rows[t]["el"], o[t][3], rows[t]["prog"], o[t][4]) for t in sorted(o) if t in rows]
    bad = [e for e in els if e[1] != e[2]]
    print(f"+0x44 (follow ticks): {len(els)} dumps, {len(bad)} differ" + (f", first {bad[0]}" if bad else ""))
    pb = [e for e in els if e[3] != e[4]]
    print(f"+0x39 (tile progress): {len(els)} dumps, {len(pb)} differ" + (f", first {pb[:3]}" if pb else ""))
    return 0 if same and not bad and not pb and max(lead) == min(lead) == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
