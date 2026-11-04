"""Oracle runs of the 16 tutorials' starts (track 1L-5; docs/campaign-format.md "Tutorials"): the exe loads
Adventures/tutorialNN.sav (tutorial_load_save 0x005BEBD0) and its first dumps are compared with our import
(sim/savimport.py) by tools/tutorial_check.py.

    python3 tools/tutorial_oracle.py scenarios        # write re/oracle/scenarios/1L5-tutNN.txt
    python3 tools/tutorial_oracle.py run [NN ...]     # run them (docs/re/oracle.md "Run"), re/oracle/runs/1L5-tutNN

The tutorial menu (oracle 1L-tutlist list.bmp): Beginning 0..7 at x 212, Advanced 8..15 at x 588, rows y = 118 + 51 i.
Clicked at 32 s; the first message is closed (right click) at 40 s; dumps every 51 ticks (a day)."""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, "re/oracle/scenarios")
RUNS = os.path.join(ROOT, "re/oracle/runs")
MENU = "5:key 27; 12:click 220,101; 17:char 78; 20:click 556,320; 27:click 644,523"


def script(n):
    x, y = (212 if n < 8 else 588), 118 + 51 * (n % 8)
    return (f"# 1L-5: tutorial {n:02d} (tutorial{n:02d}.sav) start. --seconds 72, ZEUS_STATE_DUMP_EVERY=51\n"
            f"{MENU}; 32:click {x},{y}; 38:shot DIR/start.bmp; 40:rclick 300,300; 41:shot DIR/s41.bmp; "
            f"70:shot DIR/s70.bmp\n")


def scenarios():
    for n in range(16):
        open(os.path.join(SC, f"1L5-tut{n:02d}.txt"), "w").write(script(n))


def run(n):
    name = f"1L5-tut{n:02d}"
    out = os.path.join(RUNS, name)
    import shutil
    shutil.rmtree(out, ignore_errors=True)            # a fresh write dir (the roster), no old dumps
    os.makedirs(os.path.join(out, "dump"), exist_ok=True)
    os.makedirs(os.path.join(out, "write"), exist_ok=True)
    line = [l for l in open(os.path.join(SC, name + ".txt")) if not l.startswith("#")][0].strip()
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(out, "dump"), ZEUS_STATE_DUMP_EVERY="51")
    cmd = [os.path.join(ROOT, "refs/zeus-poseidon-arm64/build/zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original/app/Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(out, "write"), "--seconds", "72", "--state-log", os.path.join(out, "state.txt"),
           "--screenshot", os.path.join(out, "end.bmp"), "--script", line.replace("DIR", out)]
    with open(os.path.join(out, "run.log"), "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), out], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), "--shots", out], cwd=ROOT)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "scenarios":
        scenarios()
    elif a and a[0] == "run":
        for n in ([int(x) for x in a[1:]] or range(16)):
            run(n)
    else:
        print(__doc__)
