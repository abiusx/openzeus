"""Enemy warships (figure 0x40, fig_handler_enemy_warship 0x004C2980) of the sea invasion run against ours
(docs/logic/navy.md "Warship 0x40").

    python3 tools/oracle_warships.py [RUN]        # default re/oracle/runs/1B-inv-sea (dumps every 17 ticks)

Ours: the run's game as tools/oracle_invasion.py builds it (sandbox, the same sea event at the change to February).
The patrol's hunt check draws the exe's RNG (0x4D4500: rng_15 % 30 + 75 <= timer); ours has its own numbers, so the
check is replayed: from two dumps with the warship patrolling (action 0xE) whose timer (+0x36) fell, the trigger
update is u = t2 - timer2 - 2 (timer 0 at u, the hunt's update u + 1 leaves it, + 1 a tick from u + 2), and
navy.hunt_due answers True in ours' pass u + 1 (dump N = the state after ours' N passes, numbered 1..N; the exe's
updates 0..N - 1). Warships are matched by creation order. Per dump: tile, action, hidden,
and the timer while patrolling; prints the differing dumps and the count.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
from oracle import Dump, dump_files  # noqa: E402

FIG, FSZ = 0x00DBD788, 0x184


def exe_ships(d):
    out = []
    for i in range(1, 2000):
        a = FIG + i * FSZ
        try:
            st, ty = d.at(a + 0x0E, '<B'), d.at(a + 0x0A, '<B')
        except KeyError:
            break
        if st == 1 and ty == 0x40:
            out.append(dict(id=i, x=d.at(a + 0x14, '<h'), y=d.at(a + 0x16, '<h'), act=d.at(a + 0x38, '<B'),
                            hid=d.at(a + 0x65, '<B'), timer=d.at(a + 0x36, '<h')))
    return out


def triggers(files):
    """{exe figure id: set of trigger ticks} from consecutive patrol dumps."""
    prev, out = {}, {}
    for f in files:
        t = int(os.path.basename(f)[5:11])
        cur = {s["id"]: (t, s) for s in exe_ships(Dump(f))}
        for i, (t2, s2) in cur.items():
            p = prev.get(i)
            if p is None:
                continue
            t1, s1 = p
            grow = s1["act"] == 0xE and s2["timer"] == s1["timer"] + (t2 - t1)
            if not grow and s2["act"] in (0xE, 8) and s1["act"] in (0xE, 8):
                u = t2 - s2["timer"] - 2 if s2["act"] == 0xE else t2 - 1
                out.setdefault(i, set()).add(u)
        prev = cur
    return out


def compare(run):
    import oracle_invasion as OI
    from sim.military import navy
    files = dump_files(os.path.join(run, "dump"))
    trig = triggers(files)
    g = OI._game("sea")
    ox, oy = g.world.origin
    order = {}                                             # exe id -> ours id, by creation order

    def ours_ships():
        return sorted((w for w in g.walkers.values() if w.role == "enemy_warship"), key=lambda w: w.id)
    orig = navy.hunt_due

    def due(g, w):
        e = next((i for i, o in order.items() if o == w.id), None)
        return e is not None and g.tick - 1 in trig.get(e, ())     # ours' pass at tick k = the exe's update k - 1
    navy.hunt_due = due
    same = n = 0
    try:
        for f in files:
            t = int(os.path.basename(f)[5:11])
            g.step(max(0, t - g.tick))
            ex = exe_ships(Dump(f))
            ou = ours_ships()
            for e in sorted(s["id"] for s in ex):
                if e not in order:
                    taken = set(order.values())
                    o = next((w.id for w in ou if w.id not in taken), None)
                    if o is not None:
                        order[e] = o
            if not ex and not ou:
                continue
            n += 1
            ea = sorted((s["x"], s["y"], s["act"], s["hid"], s["timer"] if s["act"] == 0xE else 0) for s in ex)
            oa = sorted((w.x - ox, w.y - oy, w.act, int(bool(w.hidden)), w.timer if w.act == 0xE else 0)
                        for w in ou)
            if ea == oa:
                same += 1
            else:
                print(t, "exe ", ea)
                print(" " * len(str(t)), "ours", oa)
    finally:
        navy.hunt_due = orig
    print(f"warships: {same} of {n} dumps equal (hunt triggers replayed: {sum(len(v) for v in trig.values())})")
    return same, n


if __name__ == "__main__":
    compare(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "re", "oracle", "runs", "1B-inv-sea"))
