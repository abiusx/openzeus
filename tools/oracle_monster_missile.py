"""A monster's missile attack (action 28, monster_missile_attack 0x00530ED0), ours against the oracle run 1I-missile.

    python3 tools/oracle_monster_missile.py [RUN]        (default re/oracle/runs/1I-missile)

RUN = re/oracle/scenarios/monster-missile.txt (the Maenads rampaging toward one house plot, dumps every tick). Exe side,
from the dumps: the ticks the Maenad (figure 56) enters 28 (the dump after the call shows action 28 and anim frame 1),
the anim frame per tick, each 0x34 missile's first dump (created in the call before) and its tiles, the tick the plot
is destroyed and the actions after. Ours: the same on map "sandbox" (raw = logical + 1): the plot (house) at the
exe's origin, the Maenads at their lair with aggressiveness 1 and categories 6, the rest countdown ended as the poke
does. Ours' rampage route differs (its first step), so the comparison is relative to the first 28: shot starts,
missile launches, the flights' tile sequences, the destroying missile and the leave (10 -> 6).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from oracle import Dump, dump_files  # noqa: E402

FIG, FSZ, MON = 0x00DBD788, 0x184, 56


def exe(run):
    shots, frames, missiles, acts, gone = [], {}, {}, [], None
    prev_act = None
    for f in dump_files(os.path.join(run, "dump")):
        d = Dump(f)
        t = int(os.path.basename(f)[5:11])
        a = FIG + MON * FSZ
        act, fr = d.at(a + 0x38, "<B"), d.at(a + 1, "<B")
        if act == 28 and fr == 1 and prev_act != 28:      # entered in the call before (its tail: frame 0 -> 1)
            shots.append(t - 1)
        frames[t] = fr
        if act != prev_act:
            acts.append((t - 1, act))
        prev_act = act
        for i in range(1, 2000):
            b = FIG + i * FSZ
            if d.at(b + 0x0E, "<B") == 1 and d.at(b + 0x0A, "<B") == 0x34 and d.at(b + 0x5A, "<h") == MON:
                missiles.setdefault((i, d.at(b + 0x92, "<B")), []).append(
                    (t - 1, d.at(b + 0x14, "<h"), d.at(b + 0x16, "<h")))
        if gone is None and not d.at(0x0092E658 + 0x118, "<B") in (1,):
            gone = t - 1
    return shots, missiles, acts, gone


def ours(n_ticks):
    from sim.game import Game
    g = Game("sandbox", 1)
    g.command("monster maenads")
    m = next(w for w in g.walkers.values() if w.role == "monster")
    g.command("build house 121 197")                # exe origin (120, 196) logical
    g.step(2)                                       # spawned in (6, 7): resting from its first act (the exe's poke
    m.aggr, m.cats, m.timer = 1, (6, 6, 6), -1      # at 1640 is 8 ticks after the spawn, in 7)
    shots, missiles, acts, gone, prev = [], {}, [], None, m.act
    for _ in range(n_ticks):
        g.step(1)
        t = g.tick                                  # the pass just run (Game.step: the pass at the counted tick)
        if m.act == 28 and getattr(m, "shot_t0", None) == t:
            shots.append(t)
        if m.act != prev:
            acts.append((t, m.act))
            prev = m.act
        for w in g.walkers.values():
            if w.role == "enemy_arrow" and getattr(w, "pic", None) == "monster":
                missiles.setdefault(w.id, []).append((t, w.x - 1, w.y - 1))
        if gone is None and not any(b.key == "house" for b in g.buildings.values()):
            gone = t
    return shots, missiles, acts, gone


def rel(shots, missiles, acts, gone):
    t0 = shots[0]
    ms = sorted(missiles.values(), key=lambda v: v[0][0])
    return dict(shots=[s - t0 for s in shots], launches=[v[0][0] - t0 for v in ms],
                flights=[[(x - v[0][1], y - v[0][2]) for _, x, y in v] for v in ms],
                destroyed=None if gone is None else gone - t0, acts=[(t - t0, a) for t, a in acts if t >= t0])


def main(argv):
    run = argv[0] if argv else os.path.join(ROOT, "re", "oracle", "runs", "1I-missile")
    e = rel(*exe(run))
    o = rel(*ours(200))
    ok = True
    for k in ("shots", "launches", "flights", "destroyed", "acts"):
        same = e[k] == o[k]
        ok &= same
        print(f"{k}: {'same' if same else 'DIFFER'}\n  exe  {e[k]}\n  ours {o[k]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
