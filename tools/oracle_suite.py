"""Run every oracle compare tool that replays ours against stored oracle runs (re/oracle/runs), one output file per
check, and print each check's summary lines (docs/re/oracle.md "Suite"). For a change that moves the simulation's
timing (the tick order, 11-02): run it before and after, then diff the two directories.

    python3 tools/oracle_suite.py OUTDIR [NAME ...]     # default: every check below; NAME = a key of CHECKS
    python3 tools/oracle_suite.py --list

Checks whose run directory is missing are skipped (the runs are git-ignored; docs/re/oracle.md says how to make them).
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = "re/oracle/runs/"
# name: (env, argv after python3, the run it needs, how to find the summary in the output)
CHECKS = {
    "inv-land": ({}, ["tools/oracle_invasion.py", "--compare", "land", R + "1B-inv-land"], "1B-inv-land", "total:"),
    "inv-walk": ({}, ["tools/oracle_invasion.py", "--compare", "land", R + "1B-inv-walk"], "1B-inv-walk", "total:"),
    "inv-sea": ({}, ["tools/oracle_invasion.py", "--compare", "sea", R + "1B-inv-sea"], "1B-inv-sea", "total:"),
    "inv-city": ({}, ["tools/oracle_invcity.py", "compare"], "1B-inv-city", "total:"),
    "soldier-walk": ({}, ["tools/oracle_soldier_walk.py"], "1B-inv-city-march", "dumps compared"),
    "horse-walk": ({"OSW_RUN": "1B-inv-city-horse", "OSW_COMP": "9"}, ["tools/oracle_soldier_walk.py"],
                   "1B-inv-city-horse", "dumps compared"),
    "horse-city": ({"OIC_NAME": "1B-inv-city-horse", "OIC_COMP": "9"}, ["tools/oracle_invcity.py", "compare"],
                   "1B-inv-city-horse", "total:"),
    "warships": ({}, ["tools/oracle_warships.py", R + "1B-inv-sea"], "1B-inv-sea", ""),
    "route2": ({}, ["tools/oracle_route2.py"], "1I-missile", ""),
    "roads": ({}, ["tools/oracle_roads.py", R + "1R-roads"], "1R-roads", ""),
    "monster-missile": ({}, ["tools/oracle_monster_missile.py"], "1I-missile", ""),
    "guardians": ({}, ["tools/oracle_guardians.py"], "1I-dragon", ""),
    "arrows": ({}, ["tools/oracle_arrows.py"], "1D-arrows", ""),
    "troops-march": ({"OTR_NAME": "1L5-troopsmarch", "OTR_FAST": "0"}, ["tools/oracle_troops.py", "march"],
                     "1L5-troopsmarch", ""),
    "requests": ({}, ["tools/oracle_requests.py", "check"], "1L5-requests", ""),
    "requests-troops": ({"ORQ_AID": "hercules_labors", "ORQ_NAME": "1L5-troops"}, ["tools/oracle_requests.py", "check"],
                        "1L5-troops", ""),
    "quake": ({}, ["tools/oracle_quake.py", "check"], "1L5-quake", ""),
    "lava-europa4": ({}, ["tools/oracle_disaster.py", "check", "europa4", "24"], "1L5-dis-europa4", ""),
    "tidal-odyssey3": ({}, ["tools/oracle_disaster.py", "check", "odyssey3", "25"], "1L5-dis-odyssey3", ""),
    "tidal-marathon": ({}, ["tools/oracle_disaster.py", "check", "econ2-marathon", "25"], "1L5-dis-econ2-marathon", ""),
    "effects-odyssey3": ({}, ["tools/oracle_disaster.py", "effects", "odyssey3", "25"], "1L5-dis-odyssey3", ""),
    "schools": ({}, ["tools/oracle_schools.py", "--sim", R + "schools-A"], "schools-A", ""),
    "woodcutters": ({}, ["tools/oracle_gatherers.py", R + "schools-A", "woodcutter"], "schools-A", ""),
    "stonecutters": ({}, ["tools/oracle_gatherers.py", R + "schools-A", "stonecutter"], "schools-A", ""),
    "miners": ({}, ["tools/oracle_miners.py", R + "1M-miners"], "1M-miners", ""),
    "flow-goal-met": ({}, ["tools/campaign_flow_check.py", "goal-met", R + "1L3-goal-met"], "1L3-goal-met", ""),
    "flow-time-limit": ({}, ["tools/campaign_flow_check.py", "time-limit", R + "1L3-time-limit"], "1L3-time-limit", ""),
    "flow-debt": ({}, ["tools/campaign_flow_check.py", "debt", R + "1L3-debt"], "1L3-debt", ""),
    "flow-return": ({}, ["tools/campaign_flow_check.py", "return", R + "1L3-europa-return"], "1L3-europa-return", ""),
    "tutorials": ({}, ["tools/tutorial_check.py"], "1L5-tut00", ""),
}


def main(argv):
    if argv[:1] == ["--list"]:
        for k, (env, a, run, _) in CHECKS.items():
            print(f"{k:18s} {' '.join(f'{e}={v}' for e, v in env.items())} python3 {' '.join(a)}")
        return 0
    if not argv:
        print(__doc__)
        return 2
    out = argv[0]
    os.makedirs(out, exist_ok=True)
    names = argv[1:] or list(CHECKS)
    for k in names:
        env, a, run, key = CHECKS[k]
        if not os.path.isdir(os.path.join(ROOT, R + run)):
            print(f"== {k}: skipped (no run {run})", flush=True)
            continue
        t0 = time.time()
        p = subprocess.run([sys.executable] + a, cwd=ROOT, env=dict(os.environ, **env), capture_output=True,
                           text=True)
        txt = p.stdout + ("\n--- stderr\n" + p.stderr if p.stderr.strip() else "")
        with open(os.path.join(out, k + ".txt"), "w") as f:
            f.write(txt)
        lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
        tail = [ln for ln in lines if key and ln.startswith(key)] or lines[-3:]
        print(f"== {k}: exit {p.returncode}, {time.time() - t0:.0f} s", flush=True)
        for ln in tail:
            print("   " + ln[:200], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
