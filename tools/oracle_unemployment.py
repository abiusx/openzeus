"""Does unemployment move sentiment in the exe? (playtest haiku-2 triage, bugs.md 299; docs/logic/sentiment.md 3)

sentiment_update 0x005671A0 adds sentiment_from_unemployment 0x005670D0 (+1 below 5 %, 0 below 11 %, -1 / -2 / -3
below 18 / 26 / above) to the other parts (disasm 0x00567222 `add ecx, ebp`). This checks it on the running exe:
"See a working city" (re/oracle/scenarios/working-city.txt, VeryEasy, pop 2220, sentiment 100), tax poked to 20 %
(VeryEasy -2) so a negative total is not damped away, and g_unemployment_pct 0x00FE9654 poked every tick to U
(0 in one run, 30 in the other). 0x00FEAF84 is the copy sentiment_update takes of the percent it used.

    python3 tools/oracle_unemployment.py --poke U > DIR/poke.txt
    O=re/oracle/runs/1F-unemp30; mkdir -p $O/dump
    ZEUS_POKE=$O/poke.txt ZEUS_STATE_DUMP=$PWD/$O/dump ZEUS_STATE_DUMP_EVERY=102 \
      refs/zeus-poseidon-arm64/build/zeus-run --run zeus-original/app/Zeus.exe --headless --deterministic \
      --write-dir $O/write --seconds 2400 --state-log /dev/null \
      --script "$(grep -v '^#' re/oracle/scenarios/working-city.txt)" > $O/run.log 2>&1
    python3 tools/oracle_unemployment.py --check re/oracle/runs/1F-unemp0 re/oracle/runs/1F-unemp30
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402

START, END = 300, 4000          # poke window (ticks from the first simulation_tick)
TAX, UNEMP = 0x00FE6A60, 0x00FE9654


def poke(u):
    print(f"# tools/oracle_unemployment.py --poke {u}: tax 20 % once, unemployment {u} % every tick {START}..{END}")
    print(f"{START} {TAX:08X} 4 20")
    for t in range(START, END + 1):
        print(f"{t} {UNEMP:08X} 4 {u}")


def rows(run):
    from oracle import Dump
    out = []
    for f in oracle.dump_files(os.path.join(run, "dump")):
        d = Dump(f)
        out.append((int(f[-10:-4]), d.at(0x00FE6A68), d.at(0x00FEAF84), d.at(TAX), d.at(0x00FE6A7C),
                    d.at(0x00FE9184)))
    return out


def check(runs):
    for run in runs:
        print(run)
        print("  tick  sentiment  unemployment% used  tax%  population  migration%")
        last = None
        for r in rows(run):
            if r[1:] != last:
                print("  %5d  %9d  %18d  %4d  %10d  %10d" % r)
                last = r[1:]


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--poke"]:
        poke(int(a[1]))
    elif a[:1] == ["--check"]:
        check(a[1:])
    else:
        print(__doc__)
