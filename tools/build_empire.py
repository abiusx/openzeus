"""Build data/empire/<map>.json: the empire of a Zeus scenario map (docs/logic/world-map.md section 2).

    python3 tools/build_empire.py            (all maps in sim/world.py MAPS)

Reads the map's blocks with tools/mapfile.py: 25 cities (WorldCity, 476 B in version-247 maps), 17 world
objects (map markers), 18 trade routes, 26 map picture number; city and leader names from
extracted/text/zeus_text.json (groups 21 and 139). Pre-Poseidon maps (version < 303) use the old goods
numbering; it is converted like the exe's 0x0050F7E0 (empire.md "Goods renumbering").
Route dots are expanded like the exe's map load (FUN_005118C0 / FUN_004622F0): one dot every `spacing` px
along each segment between control points.
The output is our own format (good keys as in data/resources.json); sim/empire/scenario.py loads it.
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
import mapfile  # noqa: E402
from sim.empire.model import expand  # noqa: E402  (route dots, shared with sim/empire/world.py)

TEXT = os.path.join(ROOT, "extracted", "text", "zeus_text.json")
OUT = os.path.join(ROOT, "data", "empire")

# new (Poseidon) goods numbering -> our keys (tools/build_data.py RESOURCES; 23 = drachmas)
GOODS = {1: "urchin", 2: "fish", 3: "meat", 4: "cheese", 5: "carrots", 6: "onions", 7: "wheat",
         8: "oranges", 9: "wood", 10: "bronze", 11: "marble", 12: "grapes", 13: "olives", 14: "fleece",
         15: "horses", 16: "black_marble", 17: "orichalc", 18: "armor", 19: "sculpture", 20: "olive_oil",
         21: "wine", 22: "chariot", 23: "drachmas"}
# old (Zeus, map version < 303) -> new: 1..7 same, 8..14 -> 9..15, 15..18 -> 18..21, 19 -> 23
OLD = {**{i: i for i in range(1, 8)}, **{i: i + 1 for i in range(8, 15)}, **{i: i + 3 for i in range(15, 19)}, 19: 23}

KINDS = {0: "player", 1: "colony", 2: "foreign", 3: "parent", 4: "distant", 5: "enchanted", 6: "destroyed"}
RELATIONS = {0: "ally", 1: "rival", 2: "vassal", 3: "colony"}
LABEL = {0: "left", 1: "top", 2: "right"}          # world object +0x13; other values: below
ICON_OFFSET = 201                                  # exe Zeus_Interface image index -> extracted atlas index


def i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def i16(b, o):
    return struct.unpack_from("<h", b, o)[0]


def build(path, container=None):
    """container: (hdr, blocks) of one MAPS container (e.g. tools/mapfile.py pak_map); default: the file's first."""
    hdr, blocks = container or mapfile.read_file(path)[0]
    b = {x["rank"]: x["data"] for x in blocks}
    text = json.load(open(TEXT))
    old = hdr["version"] < 303
    conv = (lambda g: OLD.get(g, 0)) if old else (lambda g: g)
    size = len(b[25]) // 22
    objects = b[17]
    osize = len(objects) // 200
    obj_of = {}
    for i in range(200):
        o = objects[osize * i:osize * (i + 1)]
        if not o[1]:
            break
        if o[0] == 1:
            obj_of[i16(o, 0x18)] = dict(object=i, x=i16(o, 4), y=i16(o, 6), w=i16(o, 8), h=i16(o, 10),
                                        icon=(struct.unpack_from("<I", o, 0x0C)[0] & 0x3FFF) + ICON_OFFSET,
                                        label=LABEL.get(o[0x13], "bottom"))
    cities = []
    for i in range(22):
        c = b[25][size * i:size * (i + 1)]
        if not c[0]:
            continue
        quota = {conv(g): c[0x60 + g] for g in range(1, 23) if c[0x60 + g]}

        def goods(lst):
            return {GOODS[conv(g)]: quota.get(conv(g), 0) for g in lst if g and conv(g) in GOODS}
        # fields past 0xF0 moved in version 302 (0x0050C7E0): old +0x154.. -> +0x164..
        att, ps, ds, act = (i32(c, 0x154), i32(c, 0x158), i32(c, 0x15C), i32(c, 0x160)) if size < 0x23C else \
            (i32(c, 0x164), i32(c, 0x168), i32(c, 0x16C), i32(c, 0x170))
        flags = c[0x164] if size < 0x23C else c[0x174]
        tg = i16(c, 0xEC)
        nm = text["21"][c[3]] if c[3] < len(text["21"]) else f"city name {c[3]}"   # past group 21: not in our text
        rec = dict(id=i, name=nm, short=text["331"][c[3]] if c[3] < len(text["331"]) else nm,
                   leader=text["139"][i32(c, 0xD0)] if c[2] and i32(c, 0xD0) < len(text["139"]) else "",
                   kind=KINDS.get(c[2], "foreign"), relation=RELATIONS.get(i32(c, 0xD4), "rival"),
                   route="sea" if c[0x10] else "land", nation=i32(c, 0xCC),
                   buys=goods(c[0xBC:0xC0]), sells=goods(c[0xC4:0xC8]),
                   attitude=att, pleased=ps, displeased=ds, active=bool(act),
                   rebellion=bool(flags & 1), visible=not flags & 4,
                   wealth=i32(c, 0xD8), strength=i32(c, 0xDC),
                   tribute=dict(mode=i32(c, 0xE0), claim=i32(c, 0xE4), amount=i32(c, 0xE8),
                                good=GOODS.get(conv(tg), "drachmas") if tg > 0 else None),
                   resources=[GOODS[conv(g)] for g in c[0xA8:0xBC] if g and conv(g) in GOODS] if c[2] == 0 else [])
        rec["map"] = obj_of.get(i)
        cities.append(rec)
    routes = []
    for i in range(232):
        r = b[18][324 * i:324 * (i + 1)]
        n = r[0x141]
        a, bb = i16(r, 0x13C), i16(r, 0x13E)
        if not r[0x142] or n < 2 or a < 0 or bb < 0:
            continue
        ctrl = [[i16(r, 8 + 6 * k), i16(r, 10 + 6 * k)] for k in range(n)]
        routes.append(dict(a=a, b=bb, kind="sea" if r[0x140] == 2 else "land", spacing=r[0], percent=r[0x143],
                           points=ctrl, dots=expand(ctrl, r[0])))
    picture = struct.unpack("<i", b[26])[0] if 26 in b and len(b[26]) == 4 else 1
    # goods_price 0x0065B9B0 (block 21 = save rank 8, i32[36]): the map's own prices, read with the map; old maps
    # renumbered (goods_remap_all: the goods new in 303 get 0). Our keys, the goods the map's numbering has.
    tbl = struct.unpack_from("<36i", b[21]) if 21 in b and len(b[21]) >= 144 else None
    prices = {GOODS[conv(i)]: tbl[i] for i in range(1, 23) if conv(i) in GOODS and conv(i) != 23} if tbl else {}
    return dict(source=os.path.relpath(path, ROOT), version=hdr["version"],
                map_picture=min(14, max(1, picture)), cities=cities, routes=routes, prices=prices)


def main():
    from sim.world import MAPS
    os.makedirs(OUT, exist_ok=True)
    for name, path in MAPS.items():
        e = build(path)
        with open(os.path.join(OUT, f"{name}.json"), "w") as f:
            json.dump(e, f, indent=1)
        print(f"{name}: {len(e['cities'])} cities, {len(e['routes'])} routes, picture {e['map_picture']} -> data/empire/{name}.json")


if __name__ == "__main__":
    main()
