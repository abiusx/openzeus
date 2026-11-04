"""Oracle check of the agora food buyer's 5-food cap (bugs.md 297): "See a working city" (VeryEasy) holds three
foods (fish, cheese, wheat: sticky food flags 0x00FEB0D2[2, 4, 7] in the dumps). Both runs hold the fish and cheese
of granary 32 (60, 94; stock of res r at +0x56 + 2r, granary_remove_food 0x0048B830) at 0 every 10 ticks, so the
food stall of the common agora 494 (50, 97), whose nearest food storage that granary is, finds only wheat there.
With --poke (not --control) the flags of urchin,
meat, carrots and onions (res 1, 3, 5, 6) are set as well, so rebuild_goods_lists 0x005BAAF0 lists 7 foods in id
order (urchin, fish, meat, cheese, carrots, onions, wheat) and buyer_food_list 0x0040D840 hands the stall buyer only
the first 5: wheat (res 7, agora slot 0) is then never bought, though granaries hold it and the buyer still goes to
the nearest storage with any food (vendor_find_source 0x0040EAD0). The control run (3 foods listed) buys wheat.
(First try without the granary pokes: both runs equal, agora 494 never needed more than its fish and cheese.)
docs/logic/storage-distribution.md "Source search", docs/play/bugs.md 297.

    DIR=$PWD/re/oracle/runs/NAME; mkdir -p $DIR/dump          # absolute paths (the dumps need the folder)
    python3 tools/oracle_agora_foods.py --poke [--control] > DIR/poke.txt
    python3 tools/oracle_agora_foods.py --script > DIR/script.txt
    ZEUS_POKE=DIR/poke.txt ZEUS_STATE_DUMP=DIR/dump ZEUS_STATE_DUMP_EVERY=51 ZEUS_STATE_DUMP_TO=4500 \
      refs/zeus-poseidon-arm64/build/zeus-run --run zeus-original/app/Zeus.exe --headless --deterministic \
      --write-dir DIR/write --seconds 2700 --state-log DIR/state.txt --script "$(cat DIR/script.txt)" 2> DIR/run.log
    python3 tools/oracle_agora_foods.py --report DIR

Runs: re/oracle/runs/1F-agorafood5 (poked), 1F-agorafood (control: --poke --control, camera only).
"""
import glob
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402

B, BSZ = 0x0092E658, 0x118            # g_buildings
STICKY = 0x00FEB0D2                   # u8[res]: food once listed (city record, rank 4)
SLOTS = ["wheat", "onions", "carrots", "cheese", "meat", "urchin", "fish", "oranges"]   # agora +0x56 + 2*slot
FOODS = ["", "urchin", "fish", "meat", "cheese", "carrots", "onions", "wheat", "oranges"]
AGORAS = (33, 382, 494)               # common (54,79), grand (58,55), common (50,97)
PREFIX = "5:key 27; 12:click 220,101; 17:char 78; 20:click 556,320; 27:click 644,523; 33:click 588,476; 45:rclick 300,300"


def poke(control=False):
    out = ["500 da2f64 4 86", "500 da2f68 4 218"]            # camera on the common agora 494 and granary 32
    out += [f"{t} {B + 32 * BSZ + 0x56 + 2 * r:x} 2 0" for t in range(5, 4500, 10) for r in (2, 4)]
    if not control:
        for t in (5, 300, 1000):
            out += [f"{t} {STICKY + r:x} 1 1" for r in (1, 3, 5, 6)]
    return "\n".join(sorted(out, key=lambda l: int(l.split()[0])))


def script():
    return "; ".join([PREFIX] + [f"{s}:rclick 700,300" for s in range(48, 2700, 3)])


def report(d):
    from oracle import Dump
    prev, rises = {}, {}
    for p in oracle.dump_files(os.path.join(d, "dump")):
        D = Dump(p)
        flags = "".join(str(D.at(STICKY + r, '<B')) for r in range(1, 9))
        row = [f"granary32:" + ",".join(f"{FOODS[r]}{D.at(B + 32 * BSZ + 0x56 + 2 * r, '<h')}" for r in range(1, 9)
                                         if D.at(B + 32 * BSZ + 0x56 + 2 * r, '<h'))]
        for a in AGORAS:
            s = [D.at(B + a * BSZ + 0x56 + 2 * k, '<h') for k in range(8)]
            for k, v in enumerate(s):
                if (a, k) in prev and v > prev[(a, k)]:
                    rises[(a, SLOTS[k])] = rises.get((a, SLOTS[k]), 0) + (v - prev[(a, k)])
                prev[(a, k)] = v
            row.append(f"{a}:" + ",".join(f"{SLOTS[k]}{v}" for k, v in enumerate(s) if v))
        print(os.path.basename(p), "listed", flags, " ".join(row))
    print("bought (sum of rises between dumps):", {f"{a} {k}": v for (a, k), v in sorted(rises.items())})


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--poke"]:
        print(poke("--control" in a))
    elif a[:1] == ["--script"]:
        print(script())
    elif a[:1] == ["--report"]:
        report(a[1])
    else:
        print(__doc__)
