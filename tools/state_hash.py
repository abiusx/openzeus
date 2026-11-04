"""Whole-game state hash, to prove an optimization changes no result (docs/sim-design.md "Performance").

Runs a benchmark and prints one sha256 over the whole pickled game state (Game.__getstate__: everything but
the caches) plus one hash per top-level attribute, so a mismatch names the part that differs. Floats, numpy
grids, the rng state, every building and walker attribute are included; sets are sorted, dicts keep their
order (iteration order can steer later ticks, so it counts).

  python3 tools/state_hash.py full                      # scripts/full.txt from a new sandbox_open (seed 1)
  python3 tools/state_hash.py script boom.txt           # any script in scripts/
  python3 tools/state_hash.py save COPY.pkl --months 12  # load a save (a COPY), run N game months
  ... --json OUT.json        per-attribute hashes (diff two runs with --diff A.json B.json)
  ... --profile OUT.prof     cProfile the run (pstats file; the top 30 by tottime are printed)
  ... --pos                  also hash only building+walker positions (x, y, key/kind per id)

Re-execs itself with PYTHONHASHSEED=0 so string sets order the same in every run.
"""
import argparse
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)
sys.path.insert(0, ROOT)

import numpy as np          # noqa: E402

SKIP = {"record_dir", "cat", "rules"}       # the recorder's path; the catalog is re-read from data/ on load


def feed(h, o, seen):
    """Canonical bytes of o into hash h."""
    t = type(o)
    if o is None or t in (bool, int, float, str, complex):
        h.update(f"{t.__name__}:{o!r};".encode())
    elif t is bytes or t is bytearray:
        h.update(b"b:" + bytes(o) + b";")
    elif isinstance(o, np.ndarray):
        h.update(f"nd:{o.dtype}:{o.shape};".encode())
        h.update(np.ascontiguousarray(o).tobytes())
    elif isinstance(o, np.generic):
        h.update(f"np:{o.dtype}:{o!r};".encode())
    elif t in (list, tuple):
        h.update(f"{t.__name__}[{len(o)}".encode())
        for v in o:
            feed(h, v, seen)
        h.update(b"]")
    elif isinstance(o, dict):
        h.update(f"{t.__name__}{{{len(o)}".encode())
        for k, v in o.items():
            feed(h, k, seen)
            feed(h, v, seen)
        h.update(b"}")
    elif t in (set, frozenset):
        h.update(f"set{{{len(o)}".encode())
        for v in sorted(o, key=repr):
            feed(h, v, seen)
        h.update(b"}")
    elif hasattr(o, "getstate") and t.__name__ == "Random":
        feed(h, o.getstate(), seen)
    else:
        if id(o) in seen:                    # shared or cyclic reference: its first-visit number
            h.update(f"ref:{seen[id(o)]};".encode())
            return
        seen[id(o)] = len(seen)
        st = o.__getstate__() if hasattr(type(o), "__getstate__") and t.__getstate__ is not object.__getstate__ \
            else getattr(o, "__dict__", None)
        h.update(f"obj:{t.__module__}.{t.__qualname__}".encode())
        if st is None:
            h.update(repr(o).encode())
        else:
            feed(h, st, seen)


def hashes(g):
    st = g.__getstate__()
    parts, whole, seen = {}, hashlib.sha256(), {}
    for k, v in st.items():
        if k in SKIP:
            continue
        h = hashlib.sha256()
        feed(h, v, seen)
        parts[k] = h.hexdigest()[:16]
        whole.update(k.encode() + parts[k].encode())
    return whole.hexdigest(), parts


def positions(g):
    h = hashlib.sha256()
    for b in sorted(g.buildings.values(), key=lambda b: b.id):
        h.update(f"B{b.id}:{b.key}:{b.x},{b.y};".encode())
    for w in sorted(g.walkers.values(), key=lambda w: w.id):
        h.update(f"W{w.id}:{w.role}:{w.x},{w.y};".encode())
    return h.hexdigest()


def run(args):
    from sim.game import Game
    from sim import script as scripts
    if args.mode in ("full", "script"):
        name = "full.txt" if args.mode == "full" else args.arg
        g = Game("sandbox_open", args.seed)        # the benchmarks' map: everything buildable (data/maps.json)
        lines = [ln for _, ln in scripts.load(os.path.join(ROOT, "scripts", name))
                 if ln.split()[0] not in ("status", "look", "info", "history", "map", "catalog", "houses")]
        go = lambda: [scripts.apply(g, ln) for ln in lines]             # noqa: E731  (as tests/helpers.play)
    else:
        g = Game.load(args.arg)
        for c in args.cmd or ():
            g.command(c)
        go = lambda: g.step(args.months * g.rules["days_per_month"] * g.rules["ticks_per_day"])    # noqa: E731
    t0 = time.perf_counter()
    if args.profile:
        import cProfile
        import pstats
        pr = cProfile.Profile()
        pr.runcall(go)
        pr.dump_stats(args.profile)
        dt = time.perf_counter() - t0
        pstats.Stats(args.profile).sort_stats("tottime").print_stats(30)
    else:
        go()
        dt = time.perf_counter() - t0
    whole, parts = hashes(g)
    print(f"ticks {g.tick}  buildings {len(g.buildings)}  walkers {len(g.walkers)}  "
          f"pop {g.city.population}  time {dt:.2f} s")
    print(f"state {whole}")
    if args.pos:
        print(f"positions {positions(g)}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"state": whole, "positions": positions(g), "time": dt, "tick": g.tick, "parts": parts}, f,
                      indent=1)


def diff(a, b):
    A, B = (json.load(open(p)) for p in (a, b))
    print("state", "equal" if A["state"] == B["state"] else "DIFFERS", f"({A['time']:.2f} s vs {B['time']:.2f} s)")
    for k in sorted(set(A["parts"]) | set(B["parts"])):
        if A["parts"].get(k) != B["parts"].get(k):
            print("  differs:", k)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("full", "script", "save", "diff"))
    ap.add_argument("arg", nargs="?")
    ap.add_argument("arg2", nargs="?")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--cmd", action="append", help="command to apply after loading a save (repeatable)")
    ap.add_argument("--json")
    ap.add_argument("--profile")
    ap.add_argument("--pos", action="store_true")
    args = ap.parse_args()
    if args.mode == "diff":
        diff(args.arg, args.arg2)
    else:
        run(args)


if __name__ == "__main__":
    main()
