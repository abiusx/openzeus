"""A sheep on a lone meadow tile in the original exe (bugs.md 486): does it stay or walk off the meadow?

    python3 tools/oracle_sheep_isolated.py poke > re/oracle/scenarios/sheep-isolated.poke
    python3 tools/oracle_sheep_isolated.py script > re/oracle/scenarios/sheep-isolated.txt
    (run: docs/re/oracle.md "Run", "See a working city"; ZEUS_POKE=re/oracle/scenarios/sheep-isolated.poke,
     ZEUS_STATE_DUMP_EVERY=10 FROM=25, ZEUS_STATE_DUMP_ZONES=28,17, --state-log /dev/null)
    python3 tools/oracle_sheep_isolated.py report RUN_DIR

Poke at tick 25 (sheep 288 grazes at logical (132,130) from tick 25; re/oracle/scenarios/sheep-build.txt): every
meadow tile (terrain bit 0x800) within 4 of it but its own loses the bit, values read from the sheep-build-r1 dump of
tick 25. report: per dump, sheep 288's tile, action (+0x38) and destination (+0x24/+0x26), and the terrain bit under it.
"""
import glob, os, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from oracle import Dump  # noqa: E402

N, TERRAIN, SX, SY, K, R = 228, 0x00CCE128, 132, 130, 288, 4
BASE = os.path.join(ROOT, "re/oracle/runs/sheep-build-r1/dump/tick_000025.bin.zst")
SCRIPT = ("5:key 27; 12:click 220,101; 17:char 78; 20:click 556,320; 27:click 644,523; 33:click 588,476; "
          "45:rclick 300,300; " + "; ".join(f"{t}:click 568,574" for t in range(60, 2400, 15)))


def poke():
    T = Dump(BASE).block(17)
    print(f"# tools/oracle_sheep_isolated.py poke: meadow bit cleared within {R} of ({SX},{SY}), its own tile kept")
    for y in range(SY - R, SY + R + 1):
        for x in range(SX - R, SX + R + 1):
            v = struct.unpack_from("<I", T, 4 * (y * N + x))[0]
            if (x, y) != (SX, SY) and v & 0x800:
                print(f"25 {TERRAIN + 4 * (y * N + x):x} 4 {v & ~0x800}")


def report(run):
    for p in sorted(glob.glob(os.path.join(run, "dump", "tick_*.bin*"))):
        d = Dump(p)
        F, T = d.block(28), d.block(17)
        o = K * 0x184
        t = struct.unpack_from("<i", F, o + 0x20)[0]
        dx, dy = struct.unpack_from("<hh", F, o + 0x24)
        tick = int(os.path.basename(p)[5:11])
        print(f"{tick:5d} ({t % N},{t // N}) act {F[o + 0x38]} dest ({dx},{dy}) "
              f"terrain {struct.unpack_from('<I', T, 4 * t)[0]:x}")


if __name__ == "__main__":
    {"poke": poke, "script": lambda: print(SCRIPT), "report": lambda: report(sys.argv[2])}[sys.argv[1]]()
