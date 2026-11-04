"""Difficulty tables vs the exe (docs/logic/difficulty.md "Check"), and the difficulty each oracle run plays at.

1. For every level, the sim's Catalog(difficulty=L) against Model/Zeus_Model_<L>.txt as load_zeus_model 0x005B0C20
   reads it (extracted/model/model_<L>.json from tools/model.py; file table 0x0065AF78 by g_difficulty): building
   cost / fire risk / damage risk by zeus_id, the house table; and the exe's own tables: start funds 0x005F7F08,
   workforce base 0x006335C4, army factor 0x005EC670, tax sentiment (Tax_Sentiment_Model.txt column).
2. g_difficulty (0x00F2A988, dump zone 12) in the last dump of every oracle run under re/oracle/runs.
Usage: re/venv/bin/python tools/difficulty_check.py      (needs pefile; reads Zeus.exe)
"""
import glob
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import oracle  # noqa: E402
from disasm import read  # noqa: E402
from oracle import Dump  # noqa: E402
from sim.data import Catalog  # noqa: E402

LEVELS = ["VeryEasy", "Easy", "Normal", "Hard", "Impossible"]
HOUSE = {"devolve_des": "devolve_des", "evolve_des": "evolve_des", "culture": "culture_needed",
         "water": "water_needed", "food_types": "food_types_needed", "fleece": "fleece_needed",
         "oil": "oil_needed", "wine": "wine_needed", "arms": "arms_needed", "max_armor": "max_armor",
         "max_horses": "max_horses", "horses": "horses_needed", "capacity": "capacity",
         "tax_multiplier": "tax_multiplier", "crime_inc": "crime_inc", "crime_base": "crime_base",
         "soldier_pct": "soldier_pct"}


def tables():
    bad = 0
    names = [read(struct.unpack("<I", read(0x65AF78 + 4 * i, 4))[0], 40).split(b"\0")[0].decode() for i in range(5)]
    print("model files by g_difficulty:", names)
    model = {lv: json.load(open(os.path.join(ROOT, "extracted", "model", f"model_{lv}.json"))) for lv in LEVELS}
    for lv in LEVELS:
        cat = Catalog(difficulty=lv)
        diffs = []
        for key, b in cat.buildings.items():
            i = b.get("zeus_id")
            if i is None:
                continue
            for f in ("cost", "fire_risk", "damage_risk"):
                exe = model[lv]["buildings"][i][f]
                if b.get(f) != exe:
                    diffs.append(f"{key}.{f} ours {b.get(f)} exe {exe}")
        hd = [f"house {i}.{k} ours {h[k]} exe {model[lv]['houses'][i][m]}" for i, h in enumerate(cat.houses)
              for k, m in HOUSE.items() if k in h and h[k] != model[lv]["houses"][i][m]]
        print(f"{lv:10s} buildings/houses differing from the exe: {len(diffs) + len(hd)}"
              + (": " + "; ".join(diffs + hd) if diffs or hd else ""))
        bad += len(hd) + len(diffs)
    d = json.load(open(os.path.join(ROOT, "data", "difficulty.json")))
    rules = json.load(open(os.path.join(ROOT, "data", "rules.json")))
    for name, va, ours in (("start funds % 0x005F7F08", 0x5F7F08, [d[lv]["start_funds_pct"] for lv in LEVELS]),
                           ("workforce % 0x006335C4", 0x6335C4, rules["workforce"]["by_difficulty"])):
        exe = list(struct.unpack("<5i", read(va, 20)))
        print(f"{name}: exe {exe} ours {ours}")
        bad += exe != ours
    from sim.empire import relations
    exe = list(struct.unpack("<5d", read(0x5EC670, 40)))
    print(f"army factor 0x005EC670: exe {exe} ours {list(relations.ARMY_K)}")
    bad += exe != list(relations.ARMY_K)
    ts = json.load(open(os.path.join(ROOT, "extracted", "model", "tax_sentiment.json")))
    cols = ["Veryeasy", "Easy", "Normal", "Hard", "VeryHard"]
    exe = [[r["sentiment"][c] for r in ts] for c in cols]
    ours = [d[lv]["tax_sentiment"] for lv in LEVELS]
    print(f"tax sentiment columns equal: {exe == ours}")
    bad += exe != ours
    return bad


def runs():
    seen = {}
    for dd in sorted(glob.glob(os.path.join(ROOT, "re", "oracle", "runs", "*", "dump"))):
        fs = oracle.dump_files(dd)
        if not fs:
            continue
        try:
            v = Dump(fs[-1]).at(0x00F2A988)
        except (KeyError, OSError, ValueError):
            continue
        seen.setdefault(LEVELS[v] if 0 <= v < 5 else str(v), []).append(os.path.basename(os.path.dirname(dd)))
    for k, v in seen.items():
        print(f"oracle runs at {k} ({len(v)}): {' '.join(v)}")


if __name__ == "__main__":
    n = tables()
    runs()
    print("OK" if not n else f"FAIL {n}")
    sys.exit(1 if n else 0)
