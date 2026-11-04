"""Storehouse deliverymen (figure 0x24) and monument carts vs the exe, on a working-city run
(docs/logic/storage-distribution.md §7 "Oracle").

    python3 tools/oracle_storemen.py RUN [--ticks N]      # RUN = re/oracle/runs/sanctuary-build (10-tick dumps)

Exe side, from the dumps: every deliveryman's and storehouseman's (figure 9: the dock's and trading post's men here) trip (first seen, home storehouse, good, amount, destination, and each
change of action / amount / destination), the most deliverymen any storehouse had out at once, the deliverymen and
monument carts (figure 4, actions 0x12..0x17) in flight per 200 ticks, and the most monument carts from one storage
at once.

Ours: Adventures/tutorial15.sav (the same city) loaded by sim/savimport.py, seeded from dump 0: each storehouse's
stock (its bays +0x12 / +0x3C), granaries' food (+0x56 + 2g), workshops' input (+0x3C), the storage orders and limits
(storage record +0xD1: +0x0A + g, +0x34 + 2g; posts' and docks' trade states +0xC4 + g; savimport converts none), every staffed building's employees pinned to
the dumps (+0x40). Then the same lists from our walkers (task deliver). Producers, consumption and their timing are
ours, so trips start on other days; what must match: one deliveryman per storehouse, the trip shape (400 or the stock
out, unload up to the workshop's cap, the rest home, a refused rest kept while the man stands at home).
"""
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import oracle  # noqa: E402
from oracle import Dump  # noqa: E402

FIG, FSZ = 0x00DBD788, 0x184
BLD, BSZ = 0x0092E658, 0x118
STORAGES, SSZ = 0x009214F8, 0x10C
ORDERS = {0: "accept", 1: "refuse", 2: "get", 3: "empty"}


def exe_side(files):
    seen, maxper, flight, monmax = {}, Counter(), [], (0, 0, {})
    events = []
    for f in files:
        t = int(os.path.basename(f)[5:11])
        d = Dump(f)
        cur, mon = [], []
        for k in range(1, 2000):
            a = FIG + k * FSZ
            if not d.at(a + 0x0E, '<B'):
                continue
            ty, act = d.at(a + 0x0A, '<B'), d.at(a + 0x38, '<B')
            if ty in (0x24, 9):
                key = (k, d.at(a + 0x5A, '<h'))
                st = (act, d.at(a + 0x0B, '<B') or d.at(a + 0x7A, '<B'), d.at(a + 0x74, '<h'), d.at(a + 0x5E, '<h'))
                if ty == 0x24:
                    cur.append(key[1])
                if seen.get(key) != st:
                    events.append((t, "new" if key not in seen else "", ty, key[0], key[1], st))
                    seen[key] = st
            elif ty == 4 and 0x12 <= act <= 0x17:
                mon.append(d.at(a + 0x5A, '<h'))
        for h, n in Counter(cur).items():
            maxper[h] = max(maxper[h], n)
        per = Counter(mon)
        if per and max(per.values()) > monmax[0]:
            monmax = (max(per.values()), t, dict(per))
        flight.append((t, len(cur), len(mon)))
    return events, maxper, flight, monmax


def ours_side(run, files, ticks):
    from sim import savimport
    from sim.systems import labor, storemen, walkers
    g = savimport.load(os.path.join(ROOT, "zeus-original/app/Adventures/tutorial15.sav"))
    ox, oy = g.world.origin
    keys = list(g.cat.resources)
    by_xy = {(b.x - ox, b.y - oy): b for b in g.buildings.values()}
    d0 = Dump(files[0])
    emap = {}
    for e in range(1, 2000):
        a = BLD + e * BSZ
        if d0.at(a, '<B') != 1:
            continue
        b = by_xy.get((d0.at(a + 6, '<h'), d0.at(a + 8, '<h')))
        t = d0.at(a + 0x10, '<h')
        if b is not None and (t == b.misc.get("zeus_type", g.cat.spec(b.key).get("zeus_id"))
                              or (t == 0x3D and b.key == "dock")):     # ours: the dock is one building (0x3C + 0x3D)
            emap[e] = b
    for e, b in emap.items():
        a, t = BLD + e * BSZ, d0.at(BLD + e * BSZ + 0x10, '<h')
        if t in (0x39, 0x3A):
            r = STORAGES + d0.at(a + 0xD1, '<B') * SSZ
            orders = {keys[i - 1]: ORDERS.get(d0.at(r + 0x0A + i, '<B'), "accept") for i in range(1, 23)}
            b.misc["orders"] = {k: v for k, v in orders.items() if v != storemen.economy.order(g, b, k)}
            cap = g.cat.spec(b.key)["capacity"]
            b.misc["limits"] = {keys[i - 1]: d0.at(r + 0x34 + 2 * i, '<h') for i in range(1, 23)
                                if d0.at(r + 0x34 + 2 * i, '<h') != cap}
            b.goods = {}
            if t == 0x39:
                for i in range(1, 9):
                    n = d0.at(a + 0x56 + 2 * i, '<h')
                    if n:
                        b.goods[keys[i - 1]] = n
            else:
                j = e
                for _ in range(8):
                    j = d0.at(BLD + j * BSZ + 0x3A, '<h')
                    if j <= 0:
                        break
                    gd, n = d0.at(BLD + j * BSZ + 0x12, '<h'), d0.at(BLD + j * BSZ + 0x3C, '<h')
                    if gd and n:
                        b.goods[keys[gd - 1]] = b.goods.get(keys[gd - 1], 0) + n
        elif t in (0x3D, 0x3E):                        # trade_state 5 import, 7 export (storage +0xC4)
            r = STORAGES + d0.at(a + 0xD1, '<B') * SSZ
            b.misc["orders"] = {keys[i - 1]: {5: "import", 7: "export"}[d0.at(r + 0xC4 + i, '<B')]
                                for i in range(1, 23) if d0.at(r + 0xC4 + i, '<B') in (5, 7)}
        elif b.kind in storemen.WORKSHOPS:
            for k in storemen.economy.inputs(g, b)[:1]:
                b.goods[k] = d0.at(a + 0x3C, '<h')
    emp = {}
    for f in files:
        d = Dump(f)
        emp[int(os.path.basename(f)[5:11])] = {e: d.at(BLD + (d.at(BLD + e * BSZ + 0x38, '<h') if emap[e].key == "dock"
                                                               else e) * BSZ + 0x40, '<h') for e in emap}   # the dock's staff: its 0x3C part
    t0 = g.tick
    orig = labor.allocate

    def alloc(g_):
        orig(g_)
        for e, n in emp[min(max(emp), (g_.tick - t0) // 10 * 10)].items():
            emap[e].employees = n
    labor.allocate = alloc
    alloc(g)
    exe_id = {b.id: e for e, b in emap.items()}
    seen, events, maxper, flight = {}, [], Counter(), []
    try:
        while g.tick - t0 < ticks:
            g.step(10)
            t = g.tick - t0
            cur, mon = [], []
            for w in g.walkers.values():
                if w.role == "cart" and w.task in storemen.TASKS:
                    h = exe_id.get(w.home, -w.home)
                    if w.task == "deliver":
                        cur.append(h)
                    st = (w.state, w.good, w.amount, exe_id.get(w.target, w.target))
                    if seen.get(w.id) != st:
                        events.append((t, "new" if w.id not in seen else "", w.task, w.id, h, st))
                        seen[w.id] = st
                elif w.role == "cart" and getattr(w, "piece", -1) >= 0:
                    mon.append(exe_id.get(w.home, -w.home))
            for h, n in Counter(cur).items():
                maxper[h] = max(maxper[h], n)
            flight.append((t, len(cur), len(mon)))
    finally:
        labor.allocate = orig
    return events, maxper, flight


def main():
    run = sys.argv[1]
    ticks = int(sys.argv[sys.argv.index("--ticks") + 1]) if "--ticks" in sys.argv else 3800
    files = [f for f in oracle.dump_files(os.path.join(run, "dump")) if int(os.path.basename(f)[5:11]) <= ticks]
    ev, maxper, flight, monmax = exe_side(files)
    print("EXE deliveryman (0x24) / storehouseman (9) events (tick, new, type, figure, home, (action, res, amount, dest)):")
    for e in ev:
        print("  ", e)
    print("EXE most deliverymen out per storehouse:", dict(maxper))
    print("EXE in flight every 200 ticks (tick, deliverymen, monument carts):", flight[::20])
    print("EXE most monument carts from one storage at once:", monmax)
    ev, maxper, flight = ours_side(run, files, ticks)
    print("OURS events (tick, new, task, walker, home as exe index, (state, good, amount, dest)):")
    for e in ev:
        if e[5][0] != "search" or e[1]:
            print("  ", e)
    print("OURS most deliverymen out per storehouse:", dict(maxper))
    print("OURS in flight every 200 ticks:", flight[19::20])


if __name__ == "__main__":
    main()
