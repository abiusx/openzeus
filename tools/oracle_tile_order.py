"""The order of figures on a tile in the exe (TODO 11-03, bugs.md 438; docs/logic/walkers.md "Tile lists"):
grid_figure 0x00D0D878 (u16 head per tile, not in the save zones: dumped through ZEUS_STATE_DUMP_EXTRA) and each
figure's next_on_tile (+0x08).

Rule (disassembly): figure_tile_list 0x004DC860 appends (figure_create 0x004D9FD0 when placed, figure_change_tile
0x004D9330 after figure_tile_unlink 0x004DCA70, every teleport: unlink + list); the readers walk head first. But
city_draw 0x00458170 / tile_walkers_draw 0x0045A5A0 call tile_walkers_sort 0x00449B30 for every tile they draw: the
list is rewritten in draw order, qsort by (rank, id) (comparator 0x00449B10), rank -100 for state != 1 or action 4,
-50 for type 6 kind 13, else the figure's vertical offset in its tile (0x005F06D8[dir * 16 + tile_progress], or
the line-move tables 0x005F0358 / 0x005F0558 by fine position), at most 49 figures. So a tile on screen is in draw
order after each frame, a tile off screen in arrival order.

    python3 tools/oracle_tile_order.py run NAME [away]   # "See a working city" (tutorial15.sav, 1024 x 768) dumps
                                                  # every tick 20..320 of the figures (zone 28), grid_figure and the
                                                  # camera; away: the camera poked to the map's far side (logical
                                                  # (110, 10)) at ticks 1, 30, 60, so no tile with figures is drawn
    python3 tools/oracle_tile_order.py check RUN [FROM TO] [--near X0,X1,Y0,Y1]
                                                  # per dump, every tile list with 2+ figures on it against the two
                                                  # models: arrival (previous order + newcomers last) and draw (sorted)

Runs: re/oracle/runs/1B-tile-order (camera as the game sets it), 1B-tile-order-away (camera away).
"""
import os
import shutil
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from oracle import Dump, dump_files  # noqa: E402

RUNS = os.path.join(ROOT, "re/oracle/runs")
SC = os.path.join(ROOT, "re/oracle/scenarios")
FIG, FSZ, GRID, N = 0x00DBD788, 0x184, 0x00D0D878, 228
CAMERA = 0x00DA2F64                       # col, row (u32 each)
LAUNCH = ["5:key 27", "12:click 220,101", "17:char 78", "20:click 556,320", "27:click 644,523", "33:click 588,476",
          "45:rclick 300,300", "50:click 90,10", "52:click 120,41", "55:click 320,253"]   # oracle_invcity's launch
SECS = 330
AWAY = (110, 10)        # the away run's camera target (logical): no figures near it


def run(name, away=False):
    out = os.path.join(RUNS, name)
    shutil.rmtree(out, ignore_errors=True)
    for d in ("dump", "write"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    ev = LAUNCH + [f"{60 + 30 * k}:shot DIR/s{k:03d}.bmp" for k in range(9)]
    sc = f"# tile order (tools/oracle_tile_order.py{' away' if away else ''}); 1024 x 768\n" + "; ".join(ev) + "\n"
    open(os.path.join(SC, name + ".txt"), "w").write(sc)
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(out, "dump"), ZEUS_STATE_DUMP_EVERY="1",
               ZEUS_STATE_DUMP_FROM="20", ZEUS_STATE_DUMP_TO="320", ZEUS_STATE_DUMP_ZONES="28",
               ZEUS_STATE_DUMP_EXTRA=f"{GRID:x}:{N * N * 2},{CAMERA:x}:8")
    if away:
        from oracle_invcity import cam_pokes
        pk = os.path.join(SC, name + ".poke")
        open(pk, "w").write("# tick address size value (tools/oracle_tile_order.py away)\n"
                            + "\n".join(x for t in (1, 30, 60) for x in cam_pokes(t, AWAY))
                            + "\n")
        env["ZEUS_POKE"] = pk
    cmd = [os.path.join(ROOT, "refs/zeus-poseidon-arm64/build/zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original/app/Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(out, "write"), "--seconds", str(SECS), "--state-log", "/dev/null",
           "--screenshot", os.path.join(out, "end.bmp"), "--script", sc.split("\n")[1].replace("DIR", out)]
    with open(os.path.join(out, "run.log"), "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), out], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), "--shots", out], cwd=ROOT)


def _s8(b):
    return b - 256 if b > 127 else b


_TABLES = None


def tables():
    global _TABLES
    if _TABLES is None:
        import pefile
        pe = pefile.PE(os.path.join(ROOT, "zeus-original/app/Zeus.exe"), fast_load=True)
        _TABLES = tuple(bytes(pe.get_data(va - pe.OPTIONAL_HEADER.ImageBase, n))
                        for va, n in ((0x005F06D8, 128), (0x005F0358, 256), (0x005F0558, 256)))
    return _TABLES


def figures(d):
    """{id: fields} of the figures in use (state +0x0E != 0)."""
    raw = d.block(28)
    out = {}
    for i in range(1, 2000):
        r = raw[i * FSZ:(i + 1) * FSZ]
        if r[0x0E] == 0:
            continue
        h = lambda o: struct.unpack_from("<h", r, o)[0]
        out[i] = dict(next=struct.unpack_from("<H", r, 0x08)[0], type=r[0x0A], line=r[0x0C], state=r[0x0E],
                      dir=r[0x11], pdir=_s8(r[0x12]), x=h(0x14), y=h(0x16), tile=struct.unpack_from("<i", r, 0x20)[0],
                      action=r[0x38], prog=_s8(r[0x39]), fx=h(0x4A), fy=h(0x4C), kind=r[0x16C])
    return out


def rank(v, view=0):
    """tile_walkers_sort 0x00449B30's key for one figure (view = orientation 0x00DA2F88)."""
    if v["state"] != 1 or v["action"] == 4:
        return -100
    if v["type"] == 6 and v["kind"] == 13:
        return -50
    a, b, c = tables()
    if v["line"] == 0:
        dr = v["dir"]
        if dr > 7:
            dr = v["pdir"] if v["pdir"] <= 7 else 0
        return _s8(a[((dr - view) % 8) * 16 + v["prog"]])
    i = v["fx"] % 15 + (v["fy"] % 15) * 16
    return {0: _s8(b[i]), 2: -_s8(c[i]), 4: -_s8(b[i]), 6: _s8(c[i])}.get(view, 0)


def chains(d, f):
    """{tile: [ids on that tile in list order]} from grid_figure when dumped, else from the next links (the head =
    the on-tile figure no other one points to)."""
    heads = next((d.data[o:o + s] for b, a, s, o in d.zones if a == GRID and s >= N * N * 2), None)
    by = {}
    for i, v in f.items():
        by.setdefault(v["tile"], []).append(i)
    out = {}
    for t, ids in by.items():
        if heads is not None:
            h = struct.unpack_from("<h", heads, t * 2)[0] if 0 <= t < N * N else 0
        else:
            pointed = {f[i]["next"] for i in ids}
            hs = [i for i in ids if i not in pointed]
            if len(hs) != 1:
                continue
            h = hs[0]
        seq, seen = [], set()
        while h and h not in seen and len(seen) < 200:
            seen.add(h)
            if h in f and f[h]["tile"] == t:
                seq.append(h)
            h = f[h]["next"] if h in f else 0
        out[t] = seq
    return out


def check(name, lo=0, hi=10 ** 9, near=None):
    files = [p for p in dump_files(os.path.join(RUNS, name, "dump")) if lo <= int(p[-10:-4]) <= hi]
    prev = prevf = None
    stat = {}
    cams = set()
    examples = []
    for p in files:
        k = int(p[-10:-4])
        d = Dump(p)
        f = figures(d)
        ch = chains(d, f)
        try:
            cams.add((d.at(CAMERA, "<I"), d.at(CAMERA + 4, "<I")))
        except KeyError:
            pass
        if prev is not None and prev[0] == k - 1:
            pch, pf = prev[1], prevf
            for t, seq in ch.items():
                if len(seq) < 2:
                    continue
                v0 = f[seq[0]]
                where = "near" if near and near[0] <= v0["x"] <= near[1] and near[2] <= v0["y"] <= near[3] else "all"
                old = [i for i in pch.get(t, []) if i in f and f[i]["tile"] == t]
                new = [i for i in seq if i not in old]
                born = [i for i in new if i not in pf]
                arrival = seq[:len(old)] == old and set(seq[len(old):]) == set(new)
                drawn = seq == sorted(seq, key=lambda i: (rank(f[i]), i)) or len(seq) > 49
                kind = "born" if born else ("entered" if new else "stayed")
                s = stat.setdefault((where, kind), [0, 0, 0, 0])
                s[(0 if arrival else 2) + (0 if drawn else 1)] += 1
                if new and not arrival and len(examples) < 12:
                    examples.append((k, (v0["x"], v0["y"]), old, seq, [rank(f[i]) for i in seq]))
        prev, prevf = (k, ch), f
    print(f"{name}: dumps {len(files)}; cameras (col, row) {sorted(cams)[:6]}")
    print("  lists with 2+ figures, by (area, newest member): arrival&draw, arrival only, draw only, neither")
    for key in sorted(stat):
        print("  ", key, stat[key])
    for e in examples:
        print("   not arrival: dump", e[0], "tile", e[1], "before", e[2], "now", e[3], "ranks", e[4])


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "run":
        run(a[1], away="away" in a[2:])
    elif a and a[0] == "check":
        near = None
        if "--near" in a:
            i = a.index("--near")
            near = tuple(int(v) for v in a[i + 1].split(","))
            a = a[:i] + a[i + 2:]
        check(a[1], *(int(v) for v in a[2:4]), near=near)
    else:
        print(__doc__)
