"""Compare a converted tutorial start (sim/savimport.py on Adventures/tutorialNN.sav) with the exe's first dump after
loading the same save (tools/tutorial_oracle.py run NN: re/oracle/runs/1L5-tutNN/dump/tick_000000.bin).

    python3 tools/tutorial_check.py [NN ...]        # default: all 16; prints differences, a summary line per tutorial

What is compared (what we model; docs/campaign-format.md "Tutorials"): the date (year 0x0091EC04, month 0x0091EC08,
day 0x0091EC0C), treasury / tax / wage (city +0x0C / +0x08 / +0x2C08), difficulty 0x00F2A988; the terrain grid (rank
17, without the exe's building bit 0x8, the display bit 0x40000000 and 0x80000000, not modeled); every building root (rank 35, buildings.md):
our building at the same anchor with the catalog key of its type, house level (type - 2) and occupants (+0x1C),
workers (+0x40), granary food (+0x56 + 2 good), storehouse / post / dock bays (+0x3C by good +0x12), monument pieces'
stages (+0x58), stall vendors; avenue tiles, roadblocks; the scenario block's allowed table (+0x408), games year
(+0x328), the tutorial switches (city +0x43AE, +2), the god block (0x00FFA450 slots), every event (rank 13: type,
month, flags, resolved values, countdown, state); the empire's cities (rank 7 via tools/build_empire.py: kind,
relation, active, visible); the sheep and goats (figures 49 / 50 at their tiles); the palace companies (figure groups
rank 31, slots 1..20: type, members) against ours recomputed from the houses.
"""
import os
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
from oracle import Dump  # noqa: E402

N = 228


def i16(b, o):
    return struct.unpack_from("<h", b, o)[0]


def i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def check(n, verbose=True):
    from sim import savimport as S
    import build_empire
    sav = os.path.join(ROOT, f"zeus-original/app/Adventures/tutorial{n:02d}.sav")
    d = Dump(os.path.join(ROOT, f"re/oracle/runs/1L5-tut{n:02d}/dump/tick_000000.bin"))
    g = S.load(sav)
    bad, ok = [], []

    def eq(name, ours, exe):
        (ok if ours == exe else bad).append(name)
        if ours != exe and verbose:
            print(f"  BAD {name}: ours {ours} exe {exe}")

    tpd = g.rules["ticks_per_day"]
    eq("year", g.year, d.at(0x0091EC04, "<i"))
    eq("month", g.month, d.at(0x0091EC08, "<i"))
    eq("day of month", (g.tick // tpd) % 16, d.at(0x0091EC0C, "<i"))
    c = d.block(4)
    eq("treasury", g.city.treasury, i32(c, 0x0C))
    eq("tax rate", g.city.tax_rate, i32(c, 0x08))
    eq("wage rate", g.city.wage_rate, i32(c, 0x2C08))
    eq("difficulty", g.difficulty, S.DIFFICULTIES[d.at(0x00F2A988, "<i")])
    # terrain
    T = np.frombuffer(d.block(17), "<u4").reshape(N, N)
    mask = np.uint32(~(0x8 | 0x40000000 | 0x80000000) & 0xFFFFFFFF)
    diff = int(((T & mask) != (g.world.flags & mask)).sum())
    eq("terrain tiles differing", diff, 0)
    # buildings
    B = d.block(35)
    grid = np.frombuffer(d.block(16), "<u2").reshape(N, N)
    keys = S._keys()
    ids = g.sav["ids"]
    nb = 0
    recs = {}
    for k in range(1, len(B) // S.BREC):
        o = k * S.BREC
        if B[o]:
            r = B[o:o + S.BREC]
            tile = i32(r, 0x0C)
            recs[k] = dict(id=k, state=r[0], type=i16(r, 0x10), x=tile % N, y=tile // N, parent=i16(r, 0x38),
                           next=i16(r, 0x3A), link=i16(r, 0xD8), level=i16(r, 0x12), orient=r[0xAC], raw=r)
    sanct = {k for k, r in recs.items() if 87 <= r["type"] <= 100 and r["parent"] == 0}
    for k, r in sorted(recs.items()):
        t = r["type"]
        if r["parent"] or t in S.SKIP_TYPES or t in S.AVENUES or t == 123 or r["link"] in sanct:
            continue
        nb += 1
        b = g.buildings.get(ids.get(k))
        if b is None:
            eq(f"building {k} type {t} at ({r['x']},{r['y']})", None, "present")
            continue
        key = "house" if 2 <= t <= 8 else "elite_house" if 9 <= t <= 14 else keys.get(t)
        eq(f"building {k} key", b.key, key)
        if 2 <= t <= 14:
            eq(f"house {k} level", b.level, t - 2)
            eq(f"house {k} occupants", b.occupants, i16(r["raw"], 0x1C))
            goods = {kk: i16(r["raw"], o) for kk, o in S.HOUSE_GOODS.items() if i16(r["raw"], o) > 0}
            eq(f"house {k} goods", b.goods, goods)
        else:
            eq(f"building {k} {key} workers", b.employees, max(0, i16(r["raw"], 0x40)))
        if t == 57:
            eq(f"granary {k}", b.goods, {S.GOOD_KEYS[i]: i16(r["raw"], 0x56 + 2 * i) for i in range(1, 9)
                                         if i16(r["raw"], 0x56 + 2 * i) > 0})
        if t in (58, 60, 62):
            have = {}
            p = r["next"]
            while p:
                q = recs[p]
                if q["type"] == 59 and i16(q["raw"], 0x12) > 0:
                    gk = S.GOOD_KEYS[i16(q["raw"], 0x12)]
                    have[gk] = have.get(gk, 0) + i16(q["raw"], 0x3C)
                p = q["next"]
            eq(f"storage {k} {key}", b.goods, {kk: v for kk, v in have.items() if v > 0})
        if b.kind == "monument" and t != 117:
            eq(f"monument {k} complete", bool(b.misc.get("complete")), not r["raw"][0xDA])
    av = {(x, y) for y, x in zip(*np.nonzero(g.world.avenue))}
    ex = set()
    for k, r in recs.items():
        if r["type"] in S.AVENUES:
            ys, xs = np.nonzero(grid == k)
            ex |= set(zip(xs.tolist(), ys.tolist()))
    eq("avenue tiles", av, ex)
    eq("roadblocks", set(getattr(g, "roadblocks", set())), {(r["x"], r["y"]) for r in recs.values() if r["type"] == 123})
    # scenario
    sc = d.block(9)
    eq("allowed", g.allowed, list(struct.unpack_from("<100h", sc, 0x408)))
    eq("games year", g.games_year, i16(sc, 0x328))
    tut = getattr(g, "tutorial", None)
    eq("tutorial switches", tut and (tut["build_categories"], tut["world_map_button"]),
       (list(c[0x43AE:0x43AE + 11]), c[2]))
    eq("god slots", g.scenario.gods["slots"], list(struct.unpack_from("<24i", d.block(122), 0)))
    E = d.block(13)
    ne = d.at(0x009173F0, "<i")
    eq("event count", len(g.scenario.events), ne)
    for i, ev in enumerate(g.scenario.events[:ne]):
        r = E[i * 124:(i + 1) * 124]
        eq(f"event {i}", (ev["type"], ev["month"], ev["flags"], ev["item"], ev["amount"], ev["year"], ev["city"],
                          ev["countdown"], ev["state"]),
           (r[2], r[3], i32(r, 0x28), i16(r, 4), i16(r, 0xC), i16(r, 0x14), i16(r, 0x1C), i16(r, 0x2E), i16(r, 0x30)))
    # empire
    from sim.world import read_map  # noqa: F401
    cont = S.map_container(sav)
    blocks = [dict(x) for x in cont[1]]
    for x in blocks:
        if x["rank"] == 25:
            x["data"] = d.block(7)
        if x["rank"] == 17:
            x["data"] = d.block(10)
    emp = build_empire.build(sav, (cont[0], blocks))
    exe_c = {r["id"]: (r["kind"], r["active"], r["visible"]) for r in emp["cities"]}
    ours_c = {c.id: (c.kind, c.active, c.visible) for c in g.empire.cities.values()} if g.empire else {}
    eq("empire cities (kind, active, visible)", ours_c, exe_c)
    # animals
    F = d.block(28)
    exe_a = sorted(("sheep" if F[k * S.FREC + 0x0A] == 49 else "goat", i32(F, k * S.FREC + 0x20) % N,
                    i32(F, k * S.FREC + 0x20) // N) for k in range(1, 2000) if F[k * S.FREC + 0x0A] in (49, 50))
    ours_a = sorted((w.role, w.x, w.y) for w in g.walkers.values() if w.role in ("sheep", "goat"))
    eq("herd animals", ours_a, exe_a)
    # companies
    G = d.block(31)
    TYPES = {11: "rabble", 12: "hoplite", 13: "horseman"}
    exe_co = []
    for s in range(1, 21):
        o = s * 156
        figs = [i16(G, o + 8 + 2 * j) for j in range(8)]
        figs = [f for f in figs if f > 0]
        if figs:
            exe_co.append((TYPES.get(F[figs[0] * S.FREC + 0x0A], F[figs[0] * S.FREC + 0x0A]), len(figs)))
    from sim.systems import military
    ours_co = [(c_["type"], c_["members"]) for s_, c_ in sorted(military.companies(g).items()) if s_ <= 20]
    eq("companies (type, members)", sorted(ours_co), sorted(exe_co))
    print(f"tutorial{n:02d} ({g.sav['adventure']}, slot {g.sav['slot']}): {len(ok)} ok, {len(bad)} differences; "
          f"{nb} building roots, skipped at import {len(g.sav['skipped'])}")
    return bad


if __name__ == "__main__":
    ns = [int(a) for a in sys.argv[1:]] or range(16)
    for n in ns:
        check(n)
