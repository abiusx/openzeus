"""Runner of every test module (tests/test_*.py; shared helpers in tests/helpers.py), each test in its own process,
all in parallel: wall time = the longest test.

    python3 tests/test_sim.py                      every test
    python3 tests/test_sim.py military gods        the tests of tests/test_military.py and tests/test_gods.py
    python3 tests/test_sim.py test_bridge ...      single tests by name (any module)
    python3 tests/test_sim.py --list [WHAT ...]    print module.test, run nothing
    python3 tests/test_military.py                 one module (same runner)

pytest also works: python3 -m pytest tests -q."""
import glob
import importlib
import os
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FIRST = "test_full_city_villas"             # the longest: started first


def modules():
    return sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(HERE, "test_*.py"))
                  if os.path.basename(p) != "test_sim.py")


def collect(mod):
    m = importlib.import_module(mod)
    return [n for n in vars(m) if n.startswith("test_") and callable(getattr(m, n))]


def select(args):
    """(module, test) pairs for the arguments: module names (with or without test_, or a path) or test names."""
    mods = modules()
    every = [(m, n) for m in mods for n in collect(m)]
    if not args:
        return every
    out = []
    for a in args:
        a = os.path.basename(a)[:-3] if a.endswith(".py") else a
        m = a if a in mods else "test_" + a if "test_" + a in mods else None
        hit = [p for p in every if p[0] == m] if m else [p for p in every if p[1] == a]
        if not hit:
            raise SystemExit("no test module or test named %r (modules: %s)" % (a, " ".join(mods)))
        out += [p for p in hit if p not in out]
    return out


def _run(pair):
    mod, name = pair
    getattr(importlib.import_module(mod), name)()
    return pair


def main(args):
    if args[:1] == ["--list"]:
        for m, n in select(args[1:]):
            print("%s.%s" % (m, n))
        return
    pairs = sorted(select(args), key=lambda p: p[1] != FIRST)
    with ProcessPoolExecutor(len(pairs)) as ex:
        for f in [ex.submit(_run, p) for p in pairs]:
            f.result()
    print("ok (%d tests)" % len(pairs))


if __name__ == "__main__":
    main(sys.argv[1:])
