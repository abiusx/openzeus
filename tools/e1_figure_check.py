"""Figure picture positions in oracle shots against walker_draw 0x0044FEF0 (bugs.md 251, docs/play/walkers.md "Position").

    python3 tools/e1_figure_check.py RUN SHOT.bmp COL ROW [--ticks A,B,..|A-B] [--types 4,9] [--all] [--bank 18=Zeus_Greek]

RUN = an oracle run with dumps (re/oracle/runs/NAME), SHOT one of its 800x600 view-0 shots, COL ROW = the exe's top-left
view cell of that shot (0x00DA2F64 / 0x00DA2F68 as poked). For every figure of the dump(s) (block 28, Figure 0x184
bytes: +0x04 sprite, +0x0A type, +0x0C in_line_move, +0x11 direction, +0x12 prev_direction, +0x20 tile, +0x39
tile_progress, +0x41 on-road flag, +0x6C/+0x6D extra offset, +0x78 slope_offset, +0x11C prev_tile, +0x180 sprite_extra;
sprite ids = bank * 0x4000 + n, bank 51 SprMain, 16 SprAmbient, 53 PoseidonImps, n = atlas index - 1) the picture's
top-left by walker_draw:
    tile point (view 0: ((x - y) 30, (x + y) 15 - 30 elevation) - camera (60 COL - 6870, 15 ROW - 30))
    + (29, 15) (map_view_set_size: half the 58 x 30 tile) + walk table 0x005F0658 / 0x005F06D8 [dir][progress]
    + (2, 10 + type / marble terms - slope_offset) - the picture's anchor;
the extra picture (cart cargo, sprite_extra) of types 4/9/0x1C/0x24 at the same point without (2, 10), + (+0x6C,
+0x6D) - its anchor. Scores the share of the picture's opaque pixels equal in the shot (within 10 a channel, the
exe draws RGB565) there and, if under 0.9, the best spot within 16 px (its offset from the rule). Figures hidden
behind buildings score low at both: only figures with a clear best spot tell the rule apart. With several --ticks
(the shot's tick is known only roughly) the dump whose figures match best in sum is taken as the shot's. Prints one line per figure on
screen and a summary per type."""
import argparse, glob, json, os, struct, sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import oracle  # noqa: E402
from oracle import Dump  # noqa: E402
from oracle_match import screen, tmpl as _tmpl, meta, score_at  # noqa: E402

N = 228
BANK = {4: "Zeus_General", 16: "SprAmbient", 51: "SprMain", 52: "Poseidon_Loaded", 53: "PoseidonImps"}
ROAD_TYPES = {1, 0xB, 0xC, 0xD, 0x28, 0x29, 0x2A, 0x37, 0x3B}
ROAD_T = [1, 2, 3, 3, 4, 5, 6, 7, -5, -5, -4, -3, -2, -1, -1, 0]
CART_TYPES = {4, 9, 0x1C, 0x24}


def tmpl(f, i):
    """the picture without its shadow (pure red pixels: the exe darkens the ground there). An alpha-masked picture
    (gods, monsters, satyrs: any alpha strictly between 0 and 255) as the exe blends it (draw_runs_blended 0x00413E30:
    (a * image + (31 - a) * ground) >> 5 per 5-bit channel): its fully opaque pixels (a = 31) one 5-bit step darker;
    the partly transparent ones are left out (the ground under them is not known)."""
    T = _tmpl(f, i).copy()
    T[(T[..., 0] == 255) & (T[..., 1] == 0) & (T[..., 2] == 0), 3] = 0
    if ((T[..., 3] > 0) & (T[..., 3] < 255)).any():
        v = T[..., :3] >> 3
        T[..., :3] = ((v * 31) >> 5) << 3
    return T


def blend_shift(f, i):
    """1 for a mirrored alpha-masked picture: FUN_00414190 draws it 1 px right of the exact mirror (play_atlas.py)"""
    m = meta(f, i)
    if not m.get("mirror_of"):
        return 0
    T = _tmpl(f, i)
    return int(((T[..., 3] > 0) & (T[..., 3] < 255)).any())


def tables():
    import pefile
    pe = pefile.PE(os.path.join(ROOT, "zeus-original/app/Zeus.exe"), fast_load=True)
    b = pe.OPTIONAL_HEADER.ImageBase
    return (struct.unpack("128b", pe.get_data(0x5F0658 - b, 128)), struct.unpack("128b", pe.get_data(0x5F06D8 - b, 128)))


def pic(sid):
    bank, n = divmod(sid, 0x4000)
    f = BANK.get(bank)
    if not f or not n:
        return None
    try:
        meta(f, n + 1)
    except KeyError:
        return None
    return f, n + 1


def figures(dump, ter, el, reg, TX, TY):
    F = dump.block(28)
    out = []
    for k in range(2000):
        o = k * 0x184
        t = F[o + 0xA]
        if not t:
            continue
        sid, ex = struct.unpack_from("<I", F, o + 4)[0], struct.unpack_from("<I", F, o + 0x180)[0]
        tile = struct.unpack_from("<i", F, o + 0x20)[0]
        if not 0 <= tile < N * N:
            continue
        d = F[o + 0x11]
        if d > 7:
            d = F[o + 0x12] if F[o + 0x12] <= 7 else 0
        p = F[o + 0x39] & 0xF
        y = 10
        if t in ROAD_TYPES:
            pt = struct.unpack_from("<i", F, o + 0x11C)[0]
            road = (ter[pt] >> 6) & 1 if 0 <= pt < N * N else 0
            if road == (F[o + 0x41] != 0):
                y = (12 if road else 0) - 5
            else:
                y = ROAD_T[15 - p if road else p]
            y += 10
        if ter[tile] & 0x20000:
            y += 8 if reg[tile] == 0 else 4 if reg[tile] == 100 else 0
        if F[o + 0xC]:
            continue                                   # line moves (ships, missiles): other tables, not checked here
        x, yy = 2 + TX[d * 16 + p], y + TY[d * 16 + p] - F[o + 0x78]
        out.append(dict(fig=k, type=t, tile=(tile % N, tile // N), p=p, d=d, sid=sid, ex=ex,
                        off=(x, yy), ext=struct.unpack_from("<bb", F, o + 0x6C), elev=int(el[tile])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run"); ap.add_argument("shot"); ap.add_argument("col", type=int); ap.add_argument("row", type=int)
    ap.add_argument("--ticks", help="A,B,.. or A-B")
    ap.add_argument("--bank", action="append", default=[], help="N=FILE: a sprite bank loaded per map (enemies: 18=Zeus_Greek ..)"); ap.add_argument("--types"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--dx", type=int, default=0, help="shift every prediction (a camera the poke did not hit exactly)")
    ap.add_argument("--dy", type=int, default=0)
    a = ap.parse_args()
    dumps = oracle.dump_files(os.path.join(a.run, "dump"))
    if a.ticks:
        want = set(range(int(a.ticks.split("-")[0]), int(a.ticks.split("-")[1]) + 1)) if "-" in a.ticks else {int(t) for t in a.ticks.split(",")}
        dumps = [f for f in dumps if int(f[-10:-4]) in want]
    else:
        dumps = dumps[-1:]
    types = {int(t, 0) for t in a.types.split(",")} if a.types else None
    for b in a.bank:
        n, f = b.split("=")
        BANK[int(n)] = f
    TX, TY = tables()
    S = screen(a.shot)
    per_tick = {}
    for f in dumps:
        D = Dump(f)
        ter = np.frombuffer(D.block(17), "<u4")
        el = np.frombuffer(D.block(111), "i1")
        reg = np.frombuffer(D.block(102), "u1")
        for g in figures(D, ter, el, reg, TX, TY):
            if types and g["type"] not in types:
                continue
            P = pic(g["sid"])
            if not P:
                continue
            x, y = g["tile"]
            tx = (x - y) * 30 - (60 * a.col - 6870) + 29
            ty = (x + y) * 15 - (15 * a.row - 30) - 30 * g["elev"] + 15
            m = meta(*P)
            L, T = tx + g["off"][0] - m["anchor_x"] + blend_shift(*P) + a.dx, ty + g["off"][1] - m["anchor_y"] + a.dy
            if L > 800 or T > 600 or L + m["width"] < 0 or T + m["height"] < 0:
                continue
            Tm = tmpl(*P)
            s, n = score_at(S, Tm, L, T)
            r = dict(g, file=P[0], idx=P[1], at=(L, T), score=round(float(s), 3), n=int(n), tick=int(f[-10:-4]))
            if s < 0.9:
                bs, bx, by = 0, 0, 0
                for dy in range(-16, 17):
                    for dx in range(-16, 17):
                        q, _ = score_at(S, Tm, L + dx, T + dy)
                        if q > bs:
                            bs, bx, by = q, dx, dy
                r["best"] = (round(float(bs), 3), bx, by)
            E = pic(g["ex"]) if g["type"] in CART_TYPES and g["ex"] else None
            if E:
                me = meta(*E)
                el_ = tx + g["off"][0] - 2 + g["ext"][0] - me["anchor_x"]
                et = ty + g["off"][1] - 10 + g["ext"][1] - me["anchor_y"]
                r["extra"] = (E, round(float(score_at(S, tmpl(*E), el_, et)[0]), 3))
            per_tick.setdefault(r["tick"], {})[r["fig"]] = r
    # the shot's tick: the dump whose figures match best in sum (a tick later every moving figure is 2-4 px off)
    if not per_tick:
        sys.exit("no figure with a known picture on screen")
    tick = max(per_tick, key=lambda t: sum(r["score"] for r in per_tick[t].values()))
    print("shot tick", tick, " sums:", {t: round(sum(r["score"] for r in v.values()), 1) for t, v in sorted(per_tick.items())})
    best = per_tick[tick]
    per = {}
    for r in sorted(best.values(), key=lambda r: (r["type"], r["fig"])):
        ok = r["score"] >= 0.9
        per.setdefault(r["type"], [0, 0, 0])
        per[r["type"]][0] += ok
        per[r["type"]][1] += 1
        if not ok and r.get("best", (0,))[0] >= 0.9:
            per[r["type"]][2] += 1
        if a.all or not ok or "extra" in r:
            print(f"fig {r['fig']:4d} type {r['type']:#04x} tick {r['tick']} tile {r['tile']} p {r['p']:2d} d {r['d']} "
                  f"{r['file']}:{r['idx']} at {r['at']} score {r['score']} n {r['n']}"
                  + (f" best {r['best']}" if "best" in r else "") + (f" extra {r['extra']}" if "extra" in r else ""))
    print("type: at the rule (>= 0.9) / on screen / elsewhere within 16 px (>= 0.9)")
    for t, (o, n, e) in sorted(per.items()):
        print(f"  {t:#04x}: {o} / {n} / {e}")


if __name__ == "__main__":
    main()
