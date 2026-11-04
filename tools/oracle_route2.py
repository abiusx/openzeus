"""Route mode 2 (route_search 0x00502EE0 + route_trace(8)), ours (sim/military/routes.py) against the routes the exe
stored in oracle dumps.

    python3 tools/oracle_route2.py [RUN ...]     (default: the 1I and 1B-inv-land runs)

For each dump and each figure with route mode 2 (+0x72) and a route (+0x3A route_id > 0, +0x3E length, directions in
routes 0x00E7AEC8 + id * 500): the start = the figure's tile walked back over the steps it has taken (+0x3C, one
less while tile progress +0x39 < 8: the tile changes at progress 8), the goal = its dest (+0x24 / +0x26). The
military grid is built from the same dump (terrain 0x00CCE128, building ids 0x00D26E98, building types +0x10 of
g_buildings 0x0092E658 (0x118 bytes), bridge pieces 0x00CB4B08) by military_grid_build_rect 0x00502BA0's rules;
composites are not in these runs (a dump with one is skipped). Then ours' Search + trace8 from the start to the
goal must give the exe's directions. A route found before the grid changed (a building destroyed since) can differ;
such routes are reported with the tiles whose value changed along it.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from oracle import Dump, dump_files  # noqa: E402

FIG, FSZ, NFIG = 0x00DBD788, 0x184, 2000
BLD, BSZ = 0x0092E658, 0x118
TERRAIN, BGRID, PIECE, ROUTES = 0x00CCE128, 0x00D26E98, 0x00CB4B08, 0x00E7AEC8
N = 228
D8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))
COMPOSITE = None


def _arr(d, addr, n, fmt):
    import struct
    for b, a, s, o in d.zones:
        if a <= addr and addr + n * struct.calcsize(fmt) <= a + s:
            return struct.unpack_from(f"<{n}{fmt}", d.data, o + addr - a)
    raise KeyError(hex(addr))


def grid_from_dump(d):
    """military_grid_build_rect 0x00502BA0 over the whole map from the dump's grids. None if a composite stands."""
    T = _arr(d, TERRAIN, N * N, "I")
    B = _arr(d, BGRID, N * N, "h")
    P = _arr(d, PIECE, N * N, "B")
    types = {}
    out = [0] * (N * N)
    for i in range(N * N):
        f = T[i]
        if f & 0x80000 or f & 0x10004 == 0x10004:
            v = -1
        elif f & 0x8000:
            v = 4
        elif f & 0x44 == 0x44 and P[i]:
            v = 5
        elif f & 4:
            v = -2
        elif f & 0x40:
            v = 0
        elif f & 0x400:
            v = 2
        elif f & 0x200:
            v = -1
        elif f & 8:
            b = B[i]
            t = types.get(b)
            if t is None:
                t = types[b] = d.at(BLD + b * BSZ + 0x10, "<h")
            if t in (0x3A, 0x3D, 0x3E, 0x75):
                v = 1
            elif t == 0x83:
                v = 4
            elif t == 0xA9:
                v = -1
            elif t in (0x24, 0x23, 0xD9, 0x76, 0x7E):
                v = 0
            elif 100 <= t <= 114:
                v = 1
            elif t in COMPOSITES:
                return None
            elif t == 0xA4:
                v = -1
            else:
                v = 1
        elif f & 0x4000:
            v = 3
        elif f & 0x60001 or f & 0x1000 or f & 0x20:
            v = 0
        elif f & 0x2DFED66F:
            v = -1
        else:
            v = 0
        out[i] = v
    return out


def _composites():
    """building_type_composite: the composite types (data/buildings.json kind monument, but the palace 0x75 and the
    pyramids 100..114 are tested before it)."""
    import json
    d = json.load(open(os.path.join(ROOT, "data", "buildings.json")))
    return {v["zeus_id"] for v in d.values() if isinstance(v, dict) and v.get("kind") == "monument"
            and v.get("zeus_id") is not None} - {0x75} - set(range(100, 115))


COMPOSITES = _composites()


def routes_in(d):
    """[(figure, type, start, goal, dirs)] of the mode-2 routes in dump d (logical coordinates)."""
    out = []
    for i in range(1, NFIG):
        a = FIG + i * FSZ
        if d.at(a + 0x0E, "<B") != 1 or d.at(a + 0x72, "<B") != 2 or d.at(a + 0x76, "<B"):
            continue
        rid, step, ln = d.at(a + 0x3A, "<h"), d.at(a + 0x3C, "<h"), d.at(a + 0x3E, "<h")
        if rid <= 0 or ln <= 0:
            continue
        dirs = list(_arr(d, ROUTES + rid * 500, ln, "B"))
        x, y, prog = d.at(a + 0x14, "<h"), d.at(a + 0x16, "<h"), d.at(a + 0x39, "<b")
        moved = step if 8 <= prog <= 14 else step - 1 if prog < 8 else step
        for k in dirs[:max(0, moved)][::-1]:
            x, y = x - D8[k][0], y - D8[k][1]
        out.append((i, d.at(a + 0x0A, "<B"), (x, y), (d.at(a + 0x24, "<h"), d.at(a + 0x26, "<h")), dirs))
    return out


def ours(gm, start, goal, off):
    """off = DAT_00DA2F80, the raw index of logical (0, 0)."""
    from sim.military import routes
    s = (start[0] + off % N, start[1] + off // N)
    e = (goal[0] + off % N, goal[1] + off // N)
    st = routes.Search(gm, s[1] * N + s[0])
    if not st.run(e[1] * N + e[0]):
        return None
    p = routes.trace8(st.dist, s, e)
    if p is None:
        return None
    out, (x, y) = [], s
    for nx, ny in p:
        out.append(D8.index((nx - x, ny - y)))
        x, y = nx, ny
    return out


def check(run):
    seen, same, diff = set(), 0, 0
    for f in dump_files(os.path.join(run, "dump")):
        d = Dump(f)
        rs = [r for r in routes_in(d) if (r[0], r[2], r[3], tuple(r[4])) not in seen]
        if not rs:
            continue
        gm = grid_from_dump(d)
        if gm is None:
            print(f"{os.path.basename(f)}: a composite stands, skipped")
            continue
        for fid, ty, s, e, dirs in rs:
            seen.add((fid, s, e, tuple(dirs)))
            o = ours(gm, s, e, d.at(0x00DA2F80))
            if o == dirs:
                same += 1
            else:
                diff += 1
                print(f"{os.path.basename(f)} figure {fid} type {ty:#x} {s}->{e}\n  exe  {''.join(map(str, dirs))}\n"
                      f"  ours {None if o is None else ''.join(map(str, o))}")
    print(f"{run}: {same} same, {diff} different")
    return diff == 0


def main(argv):
    runs = argv or [os.path.join(ROOT, "re", "oracle", "runs", r)
                    for r in ("1I-missile", "1I-missile-a", "1I-roam", "1I-bash", "1B-inv-land")]
    ok = True
    for r in runs:
        ok &= check(r)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
