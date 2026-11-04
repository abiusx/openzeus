"""Oracle check for bug 472 (docs/logic/world-map.md 6.8): a city whose buys/sells flags (WorldCity +0x18 / +0x3C)
are zero sends no traders although its trade is open, and a saved-game load rebuilds the flags (FUN_00510ED0 ->
FUN_00461360).

Open Play Sandbox, a trading post for Tiryns (city 2) as re/oracle/scenarios/trade-window.txt. Three runs:
  ctl   as is: Tiryns' traders come (WorldCity +0x12 trader slots fill)
  zero  the flags poked to 0 at tick 5 (re/oracle/scenarios/1F-tradeflags.poke): no trader, flags stay 0
  zl    zero + File > Save, File > Load (re/oracle/scenarios/1F-tradeflags-load.txt): the flags are back after
        the load (the run then stops at a tribute letter the script does not close)

Usage: python3 tools/oracle_trade_flags.py [--run] [ctl zero zl]   (--run: run zeus-run first, ~4 min in parallel;
       without it: read the dumps of re/oracle/runs/1F-tradeflags-*). Needs the oracle build (docs/re/oracle.md)."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle import Dump, dump_files

Z = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(Z, "re/oracle/scenarios")
CITY = 0x8FBAC0 + 2 * 0x23C                           # g_cities[2] (Tiryns)


def script(run, o):
    base = open(os.path.join(SC, "trade-window.txt")).read().split("\n")[3].split("; 69:shot")[0]
    extra = open(os.path.join(SC, "1F-tradeflags-load.txt")).read().split("\n")[-2] if run == "zl" else ""
    return (base + extra + "; 69:shot DIR/a.bmp; 150:shot DIR/s150.bmp").replace("DIR", o)


def start(run):
    o = os.path.join(Z, "re/oracle/runs/1F-tradeflags-" + run)
    os.makedirs(o + "/dump", exist_ok=True)
    os.makedirs(o + "/write", exist_ok=True)
    env = dict(os.environ, ZEUS_STATE_DUMP=o + "/dump", ZEUS_STATE_DUMP_EVERY="50", ZEUS_STATE_DUMP_ZONES="999",
               ZEUS_STATE_DUMP_EXTRA="8fbac0:12584")   # only the city table
    if run in ("zero", "zl"):
        env["ZEUS_POKE"] = os.path.join(SC, "1F-tradeflags.poke")
    cmd = [f"{Z}/refs/zeus-poseidon-arm64/build/zeus-run", "--run", f"{Z}/zeus-original/app/Zeus.exe", "--headless",
           "--deterministic", "--write-dir", o + "/write", "--seconds", "200", "--state-log", "/dev/null",
           "--screenshot", o + "/end.bmp", "--script", script(run, o)]
    return subprocess.Popen(cmd, cwd=Z, env=env, stdout=open(o + "/run.log", "w"), stderr=subprocess.STDOUT)


def report(run):
    fs = dump_files(os.path.join(Z, "re/oracle/runs/1F-tradeflags-" + run, "dump"))
    print(run)
    for f in fs[::4] + fs[-1:]:
        d = Dump(f)
        buys = [i for i in range(23) if d.at(CITY + 0x18 + i, "<B")]
        sells = [i for i in range(23) if d.at(CITY + 0x3C + i, "<B")]
        tr = [d.at(CITY + 0x12 + 2 * i, "<h") for i in range(3)]
        print(f"  tick {f[-10:-4]}  trade_open {d.at(CITY + 5, '<B')}  traders {tr}  buys {buys}  sells {sells}")


if __name__ == "__main__":
    a = sys.argv[1:]
    runs = [r for r in a if r != "--run"] or ["ctl", "zero", "zl"]
    if "--run" in a:
        for p in [start(r) for r in runs]:
            p.wait()
    for r in runs:
        report(r)
