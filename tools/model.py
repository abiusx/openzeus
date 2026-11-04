"""Zeus Model/*.txt -> JSON (building, house, figure, enemy, tax and monster tables).

Reads integers the way Zeus.exe does: find the section marker, then for each record skip past
'{' and read N signed integers (anything after them is ignored). See docs/formats.md.

Usage: python3 tools/model.py MODEL_DIR OUT_DIR
"""
import json
import os
import re
import sys

LEVELS = ["VeryEasy", "Easy", "Normal", "Hard", "Impossible"]
MONSTER_LEVELS = ["Veryeasy", "Easy", "Normal", "Hard", "VeryHard"]

BUILDING_FIELDS = ["cost", "desirability", "des_step", "des_step_size", "des_range",
                   "employees", "fire_risk", "damage_risk", "resource_used", "risk_reducer"]
HOUSE_FIELDS = ["devolve_des", "evolve_des", "culture_needed", "water_needed", "edu_needed",
                "soldier_pct", "max_horses", "horses_needed", "food_types_needed",
                "fleece_needed", "oil_needed", "wine_needed", "arms_needed", "max_armor",
                "crime_inc", "crime_base", "unused_17", "capacity", "tax_multiplier",
                "unused_20", "disease_inc"]
FIGURE_FIELDS = ["unit_type", "hp", "attack", "armor", "missile_armor", "missile_attack",
                 "missile_range", "missile_rate", "speed", "frequency", "defensive_morale",
                 "special_pct", "special_range", "unused"]
FIGHTING_TYPES = ["non_fighter", "helpless", "good_guy", "bad_guy", "criminal", "predator",
                  "prey", "good_monster", "bad_monster", "good_god", "bad_god"]

_INT = re.compile(r"-?\d+")


def records(text, marker, count, nfields, stop_marker=None):
    """[(label text before '{', [ints])] for `count` records after `marker`."""
    pos = text.index(marker) + len(marker) if marker else 0
    end = text.index(stop_marker, pos) if stop_marker else len(text)
    out = []
    for line in text[pos:end].splitlines():
        if "{" not in line:
            continue
        label, rest = line.split("{", 1)
        # Game: per field, skip to the next digit/minus, read an int, skip past the next comma.
        vals = [int(m) for m in _INT.findall(rest.split("}")[0])][:nfields]
        if len(vals) < nfields:
            vals = [int(m) for m in _INT.findall(rest)][:nfields]
        out.append((label, vals))
        if len(out) == count:
            break
    if len(out) != count:
        raise ValueError(f"{marker}: {len(out)} records, expected {count}")
    return out


def label_parts(label):
    return [p.strip() for p in label.split(",") if p.strip()]


def parse_zeus_model(path):
    text = open(path, encoding="latin-1").read()
    buildings = []
    for i, (label, v) in enumerate(records(text, "ALL BUILDINGS", 221, 10, "ALL HOUSES")):
        parts = label_parts(label.replace('"', ""))
        name = parts[1] if len(parts) > 1 else parts[0]
        buildings.append(dict(id=i, name=name.split("//")[0].strip().rstrip(","),
                              **dict(zip(BUILDING_FIELDS, v))))
    houses = []
    for i, (label, v) in enumerate(records(text, "ALL HOUSES", 13, 21)):
        houses.append(dict(id=i, name=label.split(",")[0].strip(), **dict(zip(HOUSE_FIELDS, v))))
    return dict(buildings=buildings, houses=houses)


def parse_figure_model(path):
    text = open(path, encoding="latin-1").read()
    figures = []
    for i, (label, v) in enumerate(records(text, "ALL FIGURES", 78, 14, "ALL ENEMIES")):
        parts = label_parts(label)
        f = dict(id=i, name=parts[-1] if parts else "Nobody", **dict(zip(FIGURE_FIELDS, v)))
        f["unit_type_name"] = FIGHTING_TYPES[v[0]] if 0 <= v[0] < len(FIGHTING_TYPES) else None
        figures.append(f)
    enemies = []
    for i, (label, v) in enumerate(records(text, "ALL ENEMIES", 66, 14)):
        parts = label_parts(label)
        enemies.append(dict(id=i, army=i // 6, name=parts[1] if len(parts) > 1 else parts[0],
                            unit_class=parts[2] if len(parts) > 2 else None,
                            **dict(zip(FIGURE_FIELDS, v))))
    return dict(figures=figures, enemies=enemies)


def parse_tax(path):
    text = open(path, encoding="latin-1").read()
    rows = []
    for label, v in records(text, None, 7, 6):
        rows.append(dict(name=label.split(",")[0].strip(), rate_pct=v[0],
                         sentiment=dict(zip(MONSTER_LEVELS, v[1:]))))
    return rows


def parse_monsters(path):
    text = open(path, encoding="latin-1").read()
    rows = []
    for i, (label, v) in enumerate(records(text, None, 16, 9)):
        name = label.split(",")[0].split(":")[-1].strip()
        rows.append(dict(id=i, name=name, values=v))  # all 9 read by 0x0052F460 (bytes at 0x00FE42F0, 12-byte slots)
    return rows


def find(model_dir, name):
    """The file in model_dir called `name`, whatever its case (the shipped names mix cases)."""
    matches = [entry for entry in os.listdir(model_dir) if entry.casefold() == name.casefold()]
    if not matches:
        raise FileNotFoundError(name)
    return os.path.join(model_dir, matches[-1])


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return
    src, out = argv
    os.makedirs(out, exist_ok=True)
    result = {}
    for lv in LEVELS:
        result[lv] = dict(**parse_zeus_model(find(src, f"Zeus_Model_{lv}.txt")),
                          **parse_figure_model(find(src, f"Figure_model_{lv}.txt")))
    for lv, mlv in zip(LEVELS, MONSTER_LEVELS):
        result[lv]["monsters"] = parse_monsters(find(src, f"monster_behavior_{mlv}.txt"))
    for lv in LEVELS:
        with open(os.path.join(out, f"model_{lv}.json"), "w") as f:
            json.dump(result[lv], f, indent=1)
    with open(os.path.join(out, "tax_sentiment.json"), "w") as f:
        json.dump(parse_tax(find(src, "Tax_Sentiment_Model.txt")), f, indent=1)
    n = result["Normal"]
    print(f"{len(n['buildings'])} buildings, {len(n['houses'])} houses, {len(n['figures'])} "
          f"figures, {len(n['enemies'])} enemies, {len(n['monsters'])} monsters x {len(LEVELS)}")


if __name__ == "__main__":
    main(sys.argv[1:])
