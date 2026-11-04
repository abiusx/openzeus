"""Walker lift on ramps (bugs.md 211, docs/play/walkers.md "Lift on ramps"): play mode's scene.js rampLift against
the exe's figure slope offset (+0x78) in oracle dumps.

    python3 tools/e1_ramp_check.py [RUN]      (default re/oracle/runs/e1-ramps: the working city, every tick)

For every figure on a ramp tile (terrain 0x400 or 0x10000000) that moved since the previous dump, takes its tile
(+0x20), step progress (+0x39, 1..15; the tile changes at 8), direction (+0x11), route (+0x3A: 0 = roaming) and slope
offset (+0x78), and evaluates the function rampLift from viewer/play/scene.js (with a route walker's next direction: the one it has when its
next step begins, or its own at the route's end) (its source, in node) on the dump's
terrain (block 17) and elevation (block 111) grids, at the position ours draws: tile point to tile point (the exe's
fine +0x4A/+0x4C can be a few counts off the tile points), mode 0 for a route walker, 1 roaming, 2 a follower
(type 28; vendor assistants follow by FUN_004D7110 but
with cargo 0x13 by FUN_004D7340: mode 1 here).
Compares the drawn lift: the exe's tile elevation * 30 + offset against ours, walkerSpot's rounded tile's elevation *
30 + rampLift, given the figure's own last tiles (scene.js rampPath / rampReplay: the exe's state machine replayed;
NO_HISTORY=1: the old straight-walk formula). Prints the number of samples, how many equal (per figure type), apart
for figures that kept their heading for the last 30 ticks and those that turned, and the differing straight ones
(ALL=1: every differing one). Ox pairs (type 28 with a SprMain picture; followers keep +0x4A/+0x4C, so a move is a
new tile or step): their slope picture group (group_5 up / group_6 down / group_4) against scene.js oxSlope (oracle
1F-ox: re/oracle/scenarios/ox-ramp.txt)."""
import glob, json, os, re, struct, subprocess, sys, tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import oracle  # noqa: E402
from oracle import Dump  # noqa: E402

N = 228
DIRS = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def _ox_pic(sid):
    """an ox pair's picture group (figure_oxcart 0x004C3680): SprMain group_5 (305..400) going up 1, group_6 (401..496)
    going down -1, else 0 (the plain group_4); None for another picture (the trailer)"""
    if sid >> 14 != 51:
        return None
    n = (sid & 0x3FFF) + 1
    return 1 if 305 <= n <= 400 else -1 if 401 <= n <= 496 else 0 if 209 <= n <= 304 else None


def samples(run):
    fs = oracle.dump_files(os.path.join(run, "dump"))
    d0 = Dump(fs[0])
    ter = np.frombuffer(d0.block(17), "<u4").copy()
    el = np.frombuffer(d0.block(111), "i1").copy()
    out, prev, dirs, waits, seqs = [], {}, {}, {}, {}
    for f in fs:
        F = Dump(f).block(28)
        cur = {}
        for k in range(2000):
            o = k * 0x184
            if not F[o + 0xA]:
                continue
            tile = struct.unpack_from("<i", F, o + 0x20)[0]
            fx, fy = struct.unpack_from("<hh", F, o + 0x4A)
            # followers (type 28 ox pairs, trailers) keep +0x4A/+0x4C (oracle 1F-ox): their tile and step tell the move
            cur[k] = (fx, fy) if F[o + 0xA] != 28 else (tile, F[o + 0x39])
            sq = seqs.setdefault(k, [])
            if 0 <= tile < N * N and (not sq or sq[-1] != tile):
                sq.append(tile)
                del sq[:-8]
            h = dirs.setdefault(k, [])
            h.append(F[o + 0x11])
            del h[:-31]
            if 1 <= F[o + 0x39] < 8 and F[o + 0x11] < 8:   # its next step began: the route's next direction
                for q in waits.pop(k, ()):
                    q["nd"] = F[o + 0x11]
            if not (0 <= tile < N * N) or not (ter[tile] & 0x10000400):
                continue
            if prev.get(k) in (None, (fx, fy)):
                continue                                   # standing (rampLift applies to moving figures)
            p, d = F[o + 0x39], F[o + 0x11]
            if d > 7 or not 1 <= p <= 15:
                continue
            ddx, ddy = DIRS[d]
            sx, sy = (tile % N - ddx, tile // N - ddy) if p >= 8 else (tile % N, tile // N)
            ex, ey = sx + ddx * p / 15, sy + ddy * p / 15     # ours: tile point to tile point
            rid = struct.unpack_from("<h", F, o + 0x3A)[0]
            mode = 2 if F[o + 0xA] == 28 else 0 if rid > 0 else 1
            rnd = int(round(ey)) * N + int(round(ex))     # walkerSpot's tile (its elevation is drawn)
            # the tiles before the step's origin, newest first (scene.js rampPath): the figure's own tile history
            sq = seqs[k][:-1] if p >= 8 else seqs[k]
            back = [[t % N, t // N] for t in reversed(sq[:-1])][:6]
            out.append(dict(tick=int(f[-10:-4]), fig=k, type=F[o + 0xA], x=ex, y=ey, dir=d, mode=mode,
                            exe=int(el[tile]) * 30 + F[o + 0x78], base=int(el[rnd]) * 30, target=F[o + 0x79],
                            straight=len(h) == 31 and len(set(h)) == 1, nd=d, back=back,
                            pic=_ox_pic(struct.unpack_from("<I", F, o + 4)[0]) if F[o + 0xA] == 28 else None))
            rs, rl = struct.unpack_from("<hh", F, o + 0x3C)
            if p >= 8 and mode == 0 and rs < rl:          # route ended: the exe takes the current direction
                waits.setdefault(k, []).append(out[-1])
        prev = cur
    return ter, el, out


JS = r"""
import { readFileSync } from "node:fs";
const [src, data] = process.argv.slice(2);
const s = readFileSync(src, "utf8"), D = JSON.parse(readFileSync(data, "utf8"));
const grab = name => { const i = s.indexOf(name); if (i < 0) throw new Error(name); let j = s.indexOf("\n}", i); return s.slice(i, j + 2); };
const N = 228, T = { flags: D.ter, elev: D.el };
const DIR_STEP = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]];
const DIR_DELTA = { "0,-1": 0, "1,-1": 1, "1,0": 2, "1,1": 3, "0,1": 4, "-1,1": 5, "-1,0": 6, "-1,-1": 7 };
const fns = new Function("T", "N", "DIR_STEP", "DIR_DELTA", grab("function rampReplay(") + "\n" + grab("function rampLift(") + "\n" + grab("function oxSlope(") + "\n" + grab("function followerRun(") + "\nreturn [rampLift, rampReplay, oxSlope];")(T, N, DIR_STEP, DIR_DELTA);
const lift = fns[0], hist = process.env.NO_HISTORY ? null : 1;
process.stdout.write(JSON.stringify(D.samples.map(p => [p.base + lift(p.x, p.y, p.dir, p.mode, p.nd, hist && p.back),
                                                       p.pic == null ? null : fns[2](p.x, p.y, p.dir, hist && p.back)])));
"""


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "re/oracle/runs/e1-ramps")
    ter, el, ss = samples(run)
    with tempfile.TemporaryDirectory() as d:
        js, dj = os.path.join(d, "r.mjs"), os.path.join(d, "d.json")
        open(js, "w").write(JS)
        json.dump(dict(ter=ter.astype(np.int64).tolist(), el=el.tolist(), samples=ss), open(dj, "w"))
        ours = json.loads(subprocess.run(["node", js, os.path.join(ROOT, "viewer/play/scene.js"), dj],
                                         check=True, capture_output=True, text=True).stdout)
    pics = [o[1] for o in ours]
    ours = [o[0] for o in ours]
    from collections import Counter
    ox = [(p, q) for p, q in zip(ss, pics) if p["pic"] is not None]
    if ox:
        print(f"{len(ox)} ox-pair samples: slope picture (group_5 up / group_6 down / group_4) equal "
              f"{sum(p['pic'] == q for p, q in ox)}")
        for p, q in ox:
            if p["pic"] != q:
                print(f"  tick {p['tick']} fig {p['fig']} at ({p['x']:.2f},{p['y']:.2f}) dir {p['dir']}: exe {p['pic']}, ours {q}")
    for straight in (True, False):
        n, eq = Counter(), Counter()
        for p, o in zip(ss, ours):
            if p["straight"] == straight:
                n[p["type"]] += 1
                eq[p["type"]] += round(o) == p["exe"]
        print(f"{sum(n.values())} samples {'heading unchanged for 30 ticks' if straight else 'turned within 30 ticks'}: "
              f"drawn lift (elevation * 30 + slope offset) equal {sum(eq.values())}")
        print("  by figure type (equal/samples): " + ", ".join(f"{t}: {eq[t]}/{n[t]}" for t in sorted(n)))
    for p, o in zip(ss, ours):
        if (p["straight"] or os.environ.get("ALL")) and round(o) != p["exe"]:
            print(f"  tick {p['tick']} fig {p['fig']} type {p['type']} mode {p['mode']} at ({p['x']:.2f},{p['y']:.2f}) dir {p['dir']}: "
                  f"exe {p['exe']} (target {p['target']}), ours {o:.1f}")


if __name__ == "__main__":
    main()
