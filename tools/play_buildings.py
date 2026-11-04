"""Build data/play/buildings.json: building key -> original sprites (play mode, docs/play/buildings.md).

    python3 tools/play_buildings.py

Sources: the exe's type table (extracted/model/building_sizes.json: image_group = collection*512 + group id,
image_offset), the sprite atlases (extracted/sprites/*/atlas.json) and the raw SG3 records
(zeus-original/app/DATA/*.sg3: animation speed byte at record offset 58). Everything not derived from
those is listed in OVERRIDES / the notes of the output.
"""
import json
import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(ROOT, "extracted", "sprites")
COLL = {4: "Zeus_General", 5: "Zeus_Terrain", 16: "SprAmbient", 17: "destruction", 51: "SprMain",
        52: "Poseidon_Loaded", 53: "PoseidonImps"}
_atl, _raw = {}, {}


def atlas(f):
    if f not in _atl:
        a = json.load(open(os.path.join(SPR, f, "atlas.json")))
        _atl[f] = ({g["id"]: g for g in a["groups"]}, {i["index"]: i for i in a["images"]},
                   {g["name"]: g for g in a["groups"]})
    return _atl[f]


def raw_speed(f, index):
    if f not in _raw:
        d = open(os.path.join(ROOT, "zeus-original", "app", "DATA", f + ".sg3"), "rb").read()
        rec = 72 if struct.unpack_from("<I", d, 4)[0] == 0xD6 else 64
        _raw[f] = (d, rec)
    d, rec = _raw[f]
    return d[680 + 40000 + rec * index + 58]


# sprite_anim_step 0x005AF8C0 with rate 100: the frame steps on a tick only when the gate 0x006668EC[speed] is set
# (speed = the group's first image +0x3A, raw_speed). game_turn rebuilds the gate every turn (0x00413330): entry i
# fires once 20 * i ms of timeGetTime passed since it last fired. At the default game speed 90 simulation_due
# 0x005168A0 runs a tick every speed_delay_ms[1] + 2 = 22 ms (docs/logic/time-core.md 1). Ours: one game turn per
# tick (a gate firing in a turn without a tick, lost in the exe, is not modelled), so a rate-100 frame lasts
# ceil(20 * speed / 22) ticks (= speed for speed 1..10). Bug 393.
RATE100 = {"ms_per_tick": 22, "gate_ms": 20}


def rate100_ticks(speed):
    """Ticks per frame of a rate-100 animation of image speed `speed` at the exe's default game speed."""
    return max(1, -(-RATE100["gate_ms"] * speed // RATE100["ms_per_tick"]))


# burning buildings: city_draw 0x00458170 -> FUN_0045A8E0 (docs/play/buildings.md "Fire"): per tile of the burning part
# (pixel offsets from its draw point, tables 0x005F5D08 / 5D28 / 5D70 / 5DF0 / 5EB8 by size 2..6; size 1: (0, 0)) a
# flame loop by grid_random % 10: 0x2205 0x6A01 0x2206 0x6A02 0x2207 0x6A03 0x2208 none 0x2209 none (packed
# collection * 512 + group + 1: destruction groups 4..8, PoseidonImps groups 0..2), frame from FUN_005AF8C0 (the
# first image's +0x1E frames, +0x3A speed), drawn at + (dx + 20 - anchor_x, dy + 20 - anchor_y)
FLAME_PACKED = [0x2205, 0x6A01, 0x2206, 0x6A02, 0x2207, 0x6A03, 0x2208, None, 0x2209, None]
FLAME_OFFSETS = {
    1: [[0, 0]],
    2: [[30, -15], [0, 0], [60, 0], [30, 15]],
    3: [[60, -30], [30, -15], [90, -15], [0, 0], [60, 0], [120, 0], [30, 15], [90, 15], [60, 30]],
}


def _diamond(n):
    """The exe's tables for sizes 4..6 follow the same rows as 2 and 3 (read from 0x005F5D70 / 5DF0 / 5EB8):
    row r (0..2n-2) holds min(r, 2n-2-r) + 1 tiles, y = (r - n + 1) * 15, x from 30 * |r - n + 1| in steps of 60."""
    out = []
    for r in range(2 * n - 1):
        k = min(r, 2 * n - 2 - r) + 1
        x0 = 30 * (n - 1 - min(r, 2 * n - 2 - r))
        out += [[x0 + 60 * i, (r - n + 1) * 15] for i in range(k)]
    return out


def flames():
    out = []
    for p in FLAME_PACKED:
        if p is None:
            out.append(None)
            continue
        f = COLL[p >> 9]
        first = atlas(f)[0][(p & 0x1FF) - 1]["first"]
        frames = atlas(f)[1][first]["anim_frames"]
        sp = raw_speed(f, first)
        out.append({"file": f, "first": first, "frames": frames, "ms_per_frame": 20 * sp if sp else 100})
    offs = {str(n): FLAME_OFFSETS.get(n) or _diamond(n) for n in range(1, 7)}
    assert offs["2"] == _diamond(2) and offs["3"] == _diamond(3)
    return {"choices": out, "offsets": offs, "src": "exe FUN_0045A8E0 (city_draw: a burning building's tiles)"}


def amb_first(packed):
    """First image of a SprAmbient packed group id (0x20NN: atlas group NN - 1)."""
    return atlas("SprAmbient")[0][(packed & 0x1FF) - 1]["first"]


def group_first(f, name):
    return atlas(f)[2][name]["first"]


def group_images(f, name):
    first = group_first(f, name)
    n = 0
    im = atlas(f)[1]
    while first + n in im and im[first + n]["group"] == name:
        n += 1
    return first, n


def anim_of(f, base):
    im = atlas(f)[1][base]
    n = im["anim_frames"]
    if not n:
        return None
    sp = raw_speed(f, base)
    a = {"file": f, "start": base + 1, "count": n, "dx": im["anchor_x"], "dy": im["anchor_y"], "speed": sp}
    a["ms_per_frame"] = 20 * sp if sp else None
    return a


def entry(f, base, size, **kw):
    im = atlas(f)[1][base]
    e = {"file": f, "base": base, "size": size, "img_w": im["width"], "img_h": im["height"], "img_tiles": im["iso_size"]}
    a = anim_of(f, base)
    if a:
        e["anim"] = a
    e.update(kw)
    return e


def main():
    bsim = json.load(open(os.path.join(ROOT, "data", "buildings.json")))
    types = {t["id"]: t for t in json.load(open(os.path.join(ROOT, "extracted", "model", "building_sizes.json")))["types"]}
    out = {}
    for key, spec in bsim.items():
        zid, size = spec["zeus_id"], spec["size"]
        t = types.get(zid)
        if t and t["image_group"] >= 512 and t["image_group"] // 512 in COLL:
            f = COLL[t["image_group"] // 512]
            g = atlas(f)[0].get(t["image_group"] % 512)
            if g and f in ("Zeus_General", "Poseidon_Loaded"):
                out[key] = entry(f, g["first"] + t["image_offset"], size, group=g["name"], src="exe type table")
    O = out
    gen = "Zeus_General"
    pos = "Poseidon_Loaded"

    # ---- houses -------------------------------------------------------------------------------
    O["house"] = {"file": gen, "size": 2, "kind": "house", "src": "exe house_set_type 0x00494EA0 / table 0x005F6078",
                  "levels": [{"level": i, "file": gen, "group": f"SPR_B_HOUSE{i + 1}",
                              "variants": [group_first(gen, f"SPR_B_HOUSE{i + 1}") + v for v in (0, 1)]} for i in range(7)],
                  "vacant": {"file": gen, "base": group_first(gen, "SPR_B_FORSALE")},
                  "poseidon_levels": {str(i): {"file": pos, "variants": [group_first(pos, f"SPR_B_POS_HOUSE{i + 1}") + v for v in (0, 1)]}
                                      for i in range(2, 7)},
                  "variant_rule": "variants[grid_random[tile] & 1] (a fixed per-tile bit, never changes)",
                  "notes": "level = sim house level 0..6 (Hut..Townhouse). A house with 0 people (and no plague) shows 'vacant'. "
                           "Poseidon game uses poseidon_levels for levels 2..6 (redrawn art); levels 0,1 are the same."}
    names = ["SPR_B_ELITE_HOUSE0A", "SPR_B_ELITE_HOUSE0B", "SPR_B_ELITE_HOUSE1", "SPR_B_ELITE_HOUSE2",
             "SPR_B_ELITE_HOUSE3", "SPR_B_ELITE_HOUSE4"]
    O["elite_house"] = {"file": gen, "size": 4, "kind": "elite_house", "src": "exe elite_house_place_sprites 0x004FECF0",
                        "levels": [{"level": 7 + i, "label": lab, "file": gen, "group": n, "first": group_first(gen, n)}
                                   for i, (n, lab) in enumerate(zip(names, ["vacant lot", "devolved", "Residence", "Mansion", "Manor", "Estate"]))],
                        "poseidon_levels": [{"level": 7 + i, "file": pos, "group": n.replace("B_ELITE", "B_POS_ELITE"),
                                             "first": group_first(pos, n.replace("B_ELITE", "B_POS_ELITE"))} for i, n in enumerate(names)],
                        "quadrants": [{"dx": 0, "dy": 0, "image": 3}, {"dx": 0, "dy": 2, "image": "0|1 by grid_random[tile]&1"},
                                      {"dx": 2, "dy": 0, "image": 4}, {"dx": 2, "dy": 2, "image": 2}],
                        "notes": "4x4 = four 2x2 images (118 wide each), image index = first + n within the level's 5-image group. "
                                 "Each quadrant is drawn as a 2x2 object at (x+dx, y+dy). Default view only. "
                                 "The house itself is the (0,2) quadrant; the other three show walls/gardens."}
    # ---- farms and orchards ----------------------------------------------------------------------
    farm = group_first(gen, "SPR_B_FARM")
    crops = {"wheat_farm": "SPR_CROPS_WHEAT", "onion_farm": "SPR_CROPS_ONION", "carrot_farm": "SPR_CROPS_CARROT"}
    for k, grp in crops.items():
        O[k] = entry(gen, farm, 3, group="SPR_B_FARM", src="exe table + farm_place_images 0x004A9F50",
                     crop={"file": gen, "first": group_first(gen, grp), "stages": 6,
                           "patch_offsets": [[-2, 0], [-1, 1], [0, 2], [1, 1], [2, 0]], "draw_order": [0, 4, 1, 3, 2],
                           "stage_rule": "p = min(growth_percent, 100)//4 (0..25); patch order 0..4 each takes min(5, p) then p -= 5; image = first + that",
                           "patch_xy": "patch top-left = base_top_left + (60 + dx*30, 55 + dy*15 - (h - 30)); visually verified"})
    for k, (f, grp) in {"olive_tree": (gen, "SPR_OLIVE_TREE"), "grapevine": (gen, "SPR_GRAPEVINE"), "fruit_tree": (pos, "SPR_FRUIT_TREE")}.items():
        first = group_first(f, grp)
        O[k] = entry(f, first, 1, group=grp, src="exe FUN_004A9C90",
                     stages={"file": f, "first": first, "count": 6, "rule": "min(5, growth_percent // 20); growth = goods_0*100/0x780 (ripe = last)"})
    # ---- storage ----------------------------------------------------------------------------------
    # blocks of 4 from SPR_B_SBAY_GOODS; checked on the images (bugs.md 57): 869 armor (18), 873 sculpture (19, one
    # image), 877 olive oil (20), 881 wine (21). It was one block too far from 18 on (oil drew as wine).
    goods_order = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 9: 7, 10: 8, 11: 9, 12: 10, 13: 11, 14: 12, 15: 13, 18: 14, 19: 15, 20: 16, 21: 17}
    bay_first = group_first(gen, "SPR_B_SBAY_GOODS")
    bays = {"file": gen, "empty": group_first(gen, "SPR_B_SBAY_EMPTY"),
            "goods_first": {str(r): bay_first + 4 * i for r, i in goods_order.items()},
            "poseidon_goods_first": {"8": [pos, group_first(pos, "SPR_SH_FRUIT")], "16": [pos, group_first(pos, "SPR_SH_BLACK_MARBLE")],
                                     "17": [pos, group_first(pos, "SPR_SH_ORICHALC")]},
            "band_rule": "band = 0 if amount<200, 1 if <300, 2 if <400, 3 at 400; image = goods_first[resource] + band (sculpture 19: no band, 1 image); amount 0 -> empty",
            "note": "keys are resource zeus ids (data/resources.json). Horses (15) images are blank in the file: draw nothing/empty. src exe FUN_004898C0/00489B50"}
    O["storehouse"] = {"file": gen, "size": 3, "kind": "storage", "src": "exe FUN_00496CA0 case 0x3A",
                       "root": {"dx": 0, "dy": 0, "file": gen, "base": group_first(gen, "SPR_B_SHOUSE"), "img_tiles": 1},
                       "bays": "the other 8 tiles of the 3x3, each a 1x1 image from 'bay_images'", "bay_images": bays}
    O["endless_warehouse"] = dict(O["storehouse"], notes="test sink; draw like a storehouse")
    O["trading_post"] = {"file": gen, "size": 4, "kind": "storage", "src": "exe FUN_00496CA0 case 0x3E",
                         "root": {"dx": 0, "dy": 0, "file": gen, "base": group_first(gen, "SPR_B_TPOST"), "img_tiles": 1},
                         "bays": "the other 15 tiles of the 4x4, 1x1 bay images", "bay_images": bays}
    cap = {b["key"]: b.get("capacity") for b in json.load(open(os.path.join(ROOT, "data", "buildings.json"))).values()
           if isinstance(b, dict) and "key" in b}
    O["granary"] = entry(gen, group_first(gen, "SPR_B_GRANARY"), 4, group="SPR_B_GRANARY", src="exe table",
                         goods={"file": gen, "first": group_first(gen, "SPR_GRANARY_GOODS"), "order": ["urchin", "fish", "meat", "cheese", "carrots", "onions", "wheat"],
                                "poseidon": {"8": [pos, group_first(pos, "SPR_SMALL_FRUIT_ICON")]}, "capacity": cap.get("granary", 3200),
                                "slots": [[57, -49], [77, -56], [97, -63], [51, -32], [71, -39], [91, -46], [111, -53], [131, -60]],
                                "adjust": {"1": [3, 0], "2": [0, 0], "3": [3, 1], "4": [4, -2], "5": [0, 2], "6": [4, 2], "7": [2, 0], "8": [5, 3]},
                                "rule": "exe FUN_004574C0: foods by ascending zeus id; piles n = 1 if stock<=400 else stock//400; when the granary is full "
                                        "(free 0) and fewer than 8 piles, +1 pile for the food with the largest stock%400 (first on ties); "
                                        "piles take slots in order; image = first + id - 1 (fruit 8: Poseidon SPR_SMALL_FRUIT_ICON); "
                                        "pile top-left = cell point + slot + adjust[id], cell point = (base_left, base_top + h - 75) (left tile of the 4x4)"},
                         notes="the 16 anim frames (37x38) are the idle wheel/flag animation at (125,130). Goods piles: 8 roof openings (goods.rule), drawn even unstaffed.")
    # ---- vendors / agora -----------------------------------------------------------------------------
    # Exe (bugs.md 130; docs/play/buildings.md 8): city_draw 0x00459553 -> 0x0040ABF0 draws the stall's stock picture
    # (vendor table 0x005E8578 [5] image, [9],[10] offset from the tile draw point) while the agora holds the stall's
    # good (vendor_agora_stock != 0), and the per-type vendor person (0x0045B690.. 0x0045BE60: SprAmbient packed group,
    # frame k = first + k, animated by the image's speed byte, 20*speed ms) when it also has workers. Draw point of a
    # 2x2 = (base_left, base_top + h - 45) (building_top_draw for a 118-wide image). Vendor person top-left =
    # draw point + (x - frame.anchor_x, y - frame.anchor_y).
    ov = {"food_vendor": ("SPR_STALL_FOOD_OVERLAY", (2, -28), (0x2052, 67, 20)),
          "fleece_vendor": ("SPR_STALL_FLEECE_OVERLAY", (9, -23), (0x2051, 62, 5)),
          "oil_vendor": ("SPR_STALL_OIL_OVERLAY", (16, -37), (0x2054, 56, -4)),
          "wine_vendor": ("SPR_STALL_WINE_OVERLAY", (5, -20), (0x200F, 77, 11)),
          "arms_vendor": ("SPR_STALL_ARMOR_OVERLAY", (15, -18), (0x2055, 74, 11)),
          "horse_trainer": ("SPR_STALL_HORSES_OVERLAY", (68, -21), (0x2053, 59, 0))}
    amb = atlas("SprAmbient")
    for k, (grp, (ox, oy), (packed, vx, vy)) in ov.items():
        o = O[k]
        h = atlas(gen)[1][o["base"]]["height"]
        o["stock_overlay"] = {"file": gen, "index": group_first(gen, grp), "dx": ox, "dy": oy + h - 45,
                              "note": "exe 0x0040ABF0: drawn while the agora holds the stall's good; offset = vendor table [9], [10] from the draw point (base_left, base_top + h - 45)"}
        first = amb_first(packed)
        sp = raw_speed("SprAmbient", first)
        o.pop("ambient", None)
        o["vendor"] = {"file": "SprAmbient", "first": first, "frames": amb[1][first]["anim_frames"], "x": vx, "y": vy,
                       "ms_per_frame": 20 * sp if sp else 100,
                       "note": "exe city_draw case 0x44..0x49: vendor person while stocked and staffed; top-left = (base_left, base_top + h - 45) + (x - anchor_x, y - anchor_y) of the frame"}
    O["chariot_vendor"]["stock_overlay"] = {"file": pos, "index": group_first(pos, "SPR_CHARIOT_VENDOR_OVERLAY"), "dx": None, "dy": None}
    O["empty_stall"] = {"file": gen, "size": 2, "kind": "stall", "variants": [group_first(gen, "SPR_STALL_UNASSIGNED") + v for v in range(3)],
                        "img_tiles": 2, "notes": "variant by tile random; base=variants[0]"}
    O["empty_stall"]["base"] = O["empty_stall"]["variants"][0]
    O["agora"] = {"file": gen, "size": 0, "kind": "agora", "src": "exe type 65 (agora road), 66 (empty vendor)",
                  "road_tiles": [group_first(gen, "SPR_AGORA_ROAD") + v for v in range(3)],
                  "stall": "empty_stall", "notes": "6x3: a 6-tile strip drawn with road_tiles[random%3] per tile (1x1 images) + 3 stalls of 2x2 on the stall side. "
                  "A vendor built on a stall replaces that stall's image by the vendor base."}
    O["grand_agora"] = dict(O["agora"], notes="6x5: strip in the middle, stalls (2x2) on both sides; same images as agora")
    # ---- decor ---------------------------------------------------------------------------------------
    O["gardens"] = {"file": gen, "size": 1, "kind": "ground", "variants": [group_first(gen, "SPR_GARDENS1") + v for v in range(8)],
                    "base": group_first(gen, "SPR_GARDENS1"), "notes": "8 variants (58x30); original picks by neighbours (8 images) - rule unknown, use random per tile"}
    O["bench"] = entry(gen, group_first(gen, "SPR_B_REC_AREA1"), 1, group="SPR_B_REC_AREA1", src="exe table")
    for k, n in (("doric_column", "SPR_DORIC_COLUMN"), ("ionic_column", "SPR_IONIC_COLUMN"), ("corinthian_column", "SPR_CORIN_COLUMN")):
        O[k]["connectors"] = {"ns": group_first(gen, "SPR_COLUMN_OVER_NS"), "ew": group_first(gen, "SPR_COLUMN_OVER_EW"),
                              "note": "31x19 / 30x22 beams drawn between adjacent columns; offsets unknown"}
    O["avenue"] = {"file": gen, "size": 2, "kind": "avenue", "road_images": [group_first(gen, "SPR_BOUL_ROAD"), 49],
                   "status": "UNVERIFIED: eZeus selection tree (49 ids over SPR_BOUL_ROAD) + side pieces SPR_BOUL_SIDE_*; the exe uses its own pattern table (not decoded)"}
    O["boulevard"] = dict(O["avenue"], size=3)
    # exe city_draw case 0x12 -> 0x0045B500 (bugs.md 135): SprAmbient packed group 0x2056 every redraw (no state),
    # frame = first + k on the image speed timer, at the draw point + (0x78 - anchor_x, 0x2A - anchor_y)
    first = amb_first(0x2056)
    O["fish_pond"]["overlay"] = {"file": "SprAmbient", "first": first, "frames": atlas("SprAmbient")[1][first]["anim_frames"],
                                 "ms_per_frame": 20 * raw_speed("SprAmbient", first), "x": 0x78, "y": 0x2A,
                                 "note": "fish jumping (exe 0x0045B500), always; top-left = draw point (base_left, base_top + h - 15*(n+1)) + (x - anchor_x, y - anchor_y)"}
    O["bird_bath"]["note"] = "SPR_REC_16: base + 9 frames, animated like other bases"
    # stalled workshop/gatherer (staffed, stock below the threshold): idle worker figure instead of the work
    # animation. exe animation_draw 0x0045D140 -> 0x0044EAB0: (dx, dy, dir) per type; figure = SprAmbient packed
    # group 0x204A (atlas group 73, 12 frames) or 0x2049 (group 72, 20 frames) when grid_random[tile] & 1;
    # sprite = first + frame*8 + dir; top-left = (base_left + (base_w+1)//2 + dx - ax, base_bottom - 30 + dy - ay)
    figs = [{"file": "SprAmbient", "first": f, "frames": n, "dirs": 8, "ms_per_frame": 20 * raw_speed("SprAmbient", f)}
            for f, n in ((2437, 12), (2277, 20))]
    for k, (dx, dy, d) in {"mint": (0x23, 0xB, 0), "foundry": (10, 0x22, 2), "timber_mill": (4, 0x24, 3),
                           "winery": (0x1E, 2, 2), "oil_press": (0, 0x1C, 2), "sculpture_studio": (-5, 0x1F, 3),
                           "horse_ranch": (0, 0x30, 3), "armory": (3, 0x24, 1)}.items():
        O[k]["idle"] = {"dx": dx, "dy": dy, "dir": d, "figures": figs, "src": "exe 0x0044EAB0; figures[grid_random & 1]"}
    # marble quarry 0x31 / black marble shop 0xD5: city_draw's per-type extra FUN_0045C170 while staffed and not
    # burning (the base has no frames, so no generic animation): stock (+0x3C) 0 -> the idle figure (as above, dir 3)
    # at (0x3B, 0x1B); else n = stock // 100 - 1 (0..7) -> a stonecutter chiselling the block, packed group 0x2043
    # (0x2042 for n 7), sprite_anim_step(group, dir, rate 100) = first + frame*8 + dir, at (dx, dy) from the table on
    # its stack; top-left = draw point (base_left, base_bottom - 15*(n+1)) + (dx - ax, dy - ay)
    cut = [(0x3B, 0x29, 7, 0x2043), (0x3F, 0x32, 0, 0x2043), (0x37, 0x2D, 6, 0x2043), (0x3B, 0x33, 7, 0x2043),
           (0x3B, 0x25, 7, 0x2043), (0x3E, 0x29, 0, 0x2043), (0x3D, 0x25, 6, 0x2043), (0x3F, 0x33, 7, 0x2042)]
    amb = atlas("SprAmbient")[1]
    for k, good in (("marble_quarry", "marble"), ("black_marble_shop", "black_marble")):
        O[k]["yard"] = {"good": good, "idle": {"dx": 0x3B, "dy": 0x1B, "dir": 3, "figures": figs},
                        "cutters": [{"file": "SprAmbient", "first": amb_first(pk), "frames": amb[amb_first(pk)]["anim_frames"],
                                     "dirs": 8, "dir": d, "dx": dx, "dy": dy,
                                     "ms_per_frame": 20 * raw_speed("SprAmbient", amb_first(pk))} for dx, dy, d, pk in cut],
                        "src": "city_draw case 0x31/0xD5 (staffed, not burning) -> FUN_0045C170; cutters[stock // 100 - 1]"}
    O["guardpost"].pop("anim", None)      # its "frames" are 'LI 1'..'LI 9' placeholder labels, not an animation
    O["guardpost"]["note"] = "the 9 images after the base are green 'LI n' label boxes (unused placeholders): not drawn"
    # ---- fortifications, bridge, roadblock, ruin -----------------------------------------------------
    sw, nw = group_images(gen, "SPR_STONE_WALLS")
    O["wall"] = {"file": gen, "size": 1, "kind": "wall", "base": sw + 15, "first": sw, "count": nw,
                 "status": "isolated post = first+15 (exe table offset 15); the neighbour->image rule for the other 35 is not decoded (36 = 4 views x 9?)"}
    O["gatehouse"] = {"file": gen, "size": 2, "kind": "gate", "base": group_first(gen, "SPR_STONE_GATEHOUSE"), "orientations": 2,
                      "front": group_first(gen, "SPR_B_GATE_FRONT"), "back": group_first(gen, "SPR_B_GATE_BACK"),
                      "overlay": group_first(gen, "SPR_GATE_OVERLAY"), "status": "base only; front/back are the 1x1 road tiles under the gate"}
    O["tower"] = entry(gen, group_first(gen, "SPR_STONE_TOWERS"), 2, group="SPR_STONE_TOWERS", src="exe table")
    O["roadblock"] = entry(gen, group_first(gen, "SPR_B_ROADBLOCK"), 1, group="SPR_B_ROADBLOCK", src="exe type 123")
    O["bridge"] = {"file": gen, "size": 1, "kind": "bridge", "flat": [group_first(gen, "SPR_QUAKE_BRIDGE"), group_first(gen, "SPR_QUAKE_BRIDGE") + 1],
                   "ramps": [group_first(gen, "SPR_BRIDGE"), 10],
                   "status": "UNVERIFIED mapping: flat deck images (58x31, two orientations) = SPR_QUAKE_BRIDGE; SPR_BRIDGE 10x(119x100) are the ramps/high spans (exe: bridge piece 1..14 in grid 0x00CB4B08)"}
    O["ruin"] = {"file": "Zeus_Terrain", "size": 1, "kind": "ruin", "base": 615, "variants": list(range(615, 623)),
                 "flames": flames(),
                 "dust": {"file": "destruction", "groups": [[1, 9], [10, 9], [19, 9], [28, 9]], "note": "collapse dust 60x60 pivot (32,40)"},
                 "status": "rubble variants = SPR_RUBBLE (terrain); flames: see 'flames' (every burning building, not only ruins)"}
    for k in ("sheep", "goat", "cattle"):
        O[k] = {"kind": "animal", "size": 1, "status": "NOT a building sprite: draw as a walker (docs/play/walkers.md); exe group id "
                + str(types[bsim[k]["zeus_id"]]["image_group"])}
    # ---- monuments -----------------------------------------------------------------------------------
    for k, spec in bsim.items():
        if spec["kind"] == "monument":
            O[k] = {"kind": "monument", "size": 0, "status": "mapped per piece in data/play/monuments.json "
                    "(tools/play_monuments.py, viewer/play/monuments.js Monuments.draw, docs/play/monuments.md)"}
    O["palace"] = {"kind": "monument", "size": 0, "file": gen, "front": group_first(gen, "SPR_B_PALACE1_FRONT"), "back": group_first(gen, "SPR_B_PALACE1_BACK"),
                   "front2": group_first(gen, "SPR_B_PALACE2_FRONT"), "back2": group_first(gen, "SPR_B_PALACE2_BACK"),
                   "corner": group_first(gen, "SPR_B_PALACE_CORNER"), "flag_pole": group_first(gen, "SPR_B_PALACE_FLAG_POLE"),
                   "anim": anim_of(gen, group_first(gen, "SPR_B_PALACE1_FRONT")),
                   "status": "superseded by data/play/monuments.json (Monuments.draw places all 24 pieces + the guard animation); "
                             "the 10 'anim' frames of SPR_B_PALACE1_FRONT are placeholder boxes ('LI 1'..'LI 10'), the exe draws "
                             "SprAmbient guard frames instead (docs/play/monuments.md)"}
    # ---- specific fixes / notes ------------------------------------------------------------------------
    O["hedge_maze"]["note"] = "exe: hedge_maze = SPR_B_REC_AREA2[2], topiary = Poseidon SPR_REC8 (tools/viewer_sprites.py has them swapped)"
    O["fountain"]["note"] = "fountain overlay frames are 48x28 water drawn at anchor (36,41)"
    # water park: 8 picture variants of 8 images (base + 7 animation frames), variant = Building+0x12, chosen by
    # R / a 1.5 s cycle while placing (exe FUN_0041BC90; placed by FUN_0041BE40 at image + 8*variant; bugs.md 136)
    O["water_park"]["variant_stride"] = 8
    # commemorative monument: variant v = Building+0x12 (1..9) shows SPR_B_COMMEM_MONU + (v - 1) (building_create
    # 0x00493E70, cycle_buildings_pass_40; docs/logic/monuments.md "Commemorative monuments")
    O["commemorative_monument"]["base"] -= 1
    O["commemorative_monument"]["variant_stride"] = 1
    # god statue variants 10..65 (FUN_00496CA0 case 0x77, preview FUN_00456E30; docs/play/monuments.md 9): every
    # tile but the centre shows SPR_SANCTUARY_TILE + 0; small (3x3) centre 1x1 = FUN_00535A10(s, f): Zeus_General
    # SPR_SMALL_GOD_STATUE + 4s + f, s = 1 Poseidon_Loaded SPR_POS_SMALL_POSEIDON_STATUE + f, 12 / 13
    # SPR_POS_SMALL_GOD_STATUES + 0 / 4 + f; large (4x4) centre 2x2 at (1, 1) = the god's statue file (name table
    # 0x00640DB8[god]) SPR_GOD_STATUE + f. god = FUN_0051B9D0(v), s = FUN_00496C00(god).
    # Facing f (o = Building+0xAC, view 0x00DA2F88, ^6 in views 2/6 = 0x0045DC50): small ((view + 2o) & 7) / 2,
    # large ((2o - view) & 7) / 2 (oracle runs commem-*: seen)
    pl = "Poseidon_Loaded"
    O["commemorative_monument"]["statues"] = {
        "tile": [gen, group_first(gen, "SPR_SANCTUARY_TILE")],
        "small": [gen, group_first(gen, "SPR_SMALL_GOD_STATUE")],
        "small_special": {"1": [pl, group_first(pl, "SPR_POS_SMALL_POSEIDON_STATUE")],
                          "12": [pl, group_first(pl, "SPR_POS_SMALL_GOD_STATUES")],
                          "13": [pl, group_first(pl, "SPR_POS_SMALL_GOD_STATUES") + 4]},
        "large": [[f, group_first(f, "SPR_GOD_STATUE")] for f in
                  ["Zeus_God01", "Zeus_God02", "Zeus_God04", "Zeus_God07", "Zeus_God06", "Zeus_God08", "Zeus_God10",
                   "Zeus_God11", "Zeus_God05", "Zeus_God09", "Zeus_God12", "Zeus_God03", "Poseidon_HeraStat",
                   "Poseidon_AtlasStat"]],
        "sculpture": [0, 1, 3, 6, 5, 7, 9, 10, 4, 8, 11, 2, 12, 13],
        "god": {str(v): ((v - 10) % 12 if v < 34 else 12 + v % 2 if v < 38 else (v - 38) % 12 if v < 62 else 12 + v % 2)
                for v in range(10, 66)},
        "large_variants": [v for v in range(10, 66) if 22 <= v <= 33 or v in (36, 37) or 50 <= v <= 61 or v in (64, 65)],
        "note": "variant -> god (0 Zeus .. 11 Hades, 12 Hera, 13 Atlas): FUN_0051B9D0; s = sculpture[god]; images "
                "[file, atlas index]; see the comment in tools/play_buildings.py and docs/play/monuments.md 9"}
    # stadium: two 5x5 halves; exe table 0x005E4958 (view 0): orientation 0 (v, 5x10) root SPR_B_STADIUM_S +
    # second half (0,5) SPR_B_STADIUM_N; orientation 1 (h, 10x5) root SPR_B_STADIUM_E + (5,0) SPR_B_STADIUM_W
    sg = {n: group_first(gen, "SPR_B_STADIUM_" + n) for n in "NESW"}
    O["stadium"]["parts"] = {"file": gen, "v": [[0, 0, sg["S"]], [0, 5, sg["N"]]], "h": [[0, 0, sg["E"]], [5, 0, sg["W"]]],
                             "note": "[dx, dy, image] per 5x5 half, each drawn on its own half (exe FUN_005AFB40, ghost FUN_005AFD80)"}
    # stadium shows (city_draw 0x0045FB40 case 0x50 -> FUN_0044CD10, only when the root is staffed and its
    # venue_shows != 0; docs/play/buildings.md 7d): SprAmbient loops at draw point + (dx - ax, dy - ay) of the half
    # picture; "S" = the half showing the root's own picture (S / E), "N" = the other (N / W); `set` = which of the
    # three day sets (day_of_month + 1) % 6 / 2 shows it (null = always); `phase`: frame = (counter - phase) of
    # the one counter stepped at 0x203C's rate (0x0044DDE0). The games (year % 4, months 5..7) are not drawn.
    def show(packed, dx, dy, st=None, phase=None):
        f = amb_first(packed)
        return {"first": f, "frames": amb_first(packed + 1) - f,
                "ms_per_frame": 20 * raw_speed("SprAmbient", f), "dx": dx, "dy": dy, "set": st, "phase": phase,
                "src": hex(packed)}
    O["stadium"]["show"] = {"file": "SprAmbient",
                            "S": [show(0x2035, 0x43, 0x1C, 0), show(0x203D, 0xA9, 0x36, None, 6)],
                            "N": [show(0x2036, 0xDE, -0x0E, 1), show(0x2037, 0xAB, -0x0B, 2),
                                  show(0x203C, 0x7E, -0x21, None, 12)]}
    # shore buildings half over water (production.md "Shore buildings", trade.md "Dock placement"): image = group
    # first + orientation (Building+0xAC: 0 water N/-y, 1 E/+x, 2 S/+y, 3 W/-x), FUN_00496CA0 cases 0x2C/0x2D/0x88/0x3C
    for k in ("fishing_wharf", "urchin_quay", "trireme_wharf"):
        O[k]["orient_stride"] = 1
        O[k]["src"] = "exe FUN_00496CA0: group first + orientation (b.orient; saves before 10-28: none = 0)"
        O[k].pop("anim", None)      # urchin quay: the SG3 header's 20 frames are the other orientations' images, no animation
    O["dock"] = {"file": gen, "size": 4, "kind": "storage", "src": "exe FUN_00496CA0 case 0x3C (pier) / 0x3D (dock house)",
                 "root": {"dx": 0, "dy": 0, "file": gen, "base": group_first(gen, "SPR_B_DHOUSE"), "img_tiles": 1},
                 "bays": "the other 15 tiles of the 4x4 dock house, 1x1 bay images", "bay_images": bays,
                 "pier": {"file": gen, "first": group_first(gen, "SPR_B_DOCK"), "img_tiles": 2,
                          "rule": "2x2 at b.pier, image first + b.orient: 463 SPR_B_DOCK (o0), 464 _E, 465 _S, 466 _W "
                                  "(seen: oracle re/oracle/runs/shore/dock.bmp, o2 = SPR_B_DOCK_S)"},
                 "note": "the sim's dock is the 4x4 dock house at (x, y) plus its pier (b.pier, b.orient); docks of saves "
                         "before 10-28 have no pier and draw as the house only"}
    # ---- per-type extras of city_draw (docs/play/buildings.md 7c) ------------------------------------------
    # `loops`: SprAmbient loops drawn by the per-type handlers while the building is staffed, picture top-left =
    # draw point (base_left, base_top + h - 15*(n+1)) + (dx - anchor_x, dy - anchor_y) of the frame drawn;
    # `when`: staffed | act (b.act == the value, else the next entry) ; per orientation (view-relative, b.orient)
    # rows [first, dx, dy]; dirs/dir: image = first + frame*dirs + dir (dir "2o" = 2*orientation).
    def loop(packed, frames, ms, rows, when="staffed", **kw):
        first = lambda pk: amb_first(pk) if pk > 0x2000 else pk
        d = {"file": "SprAmbient", "frames": frames, "ms_per_frame": ms, "when": when, **kw}
        if isinstance(rows[0], list):
            d["by_orient"] = [[first(pk), dx, dy] for pk, dx, dy in rows]
        else:
            d["first"], d["dx"], d["dy"] = first(packed), rows[0], rows[1]
        return d
    O["trading_post"]["loops"] = [loop(0x2003, 39, 100, (31, -35), src="0x0044C2F0 table 0x5F8AA4; the exe steps it every 2nd redraw "
                                       "(tile byte 0x00CB4B08), rate unknown: ours 100 ms (the file's speed 5); the trading variant (0x5F8B04, "
                                       "group_3) needs Building+0xE0, never set for a trading post (hypothesis)")]
    O["storehouse"]["loops"] = [loop(0x200A, 24, 100, (31, 5), src="0x0044BE90 table 0x5F8924, at the 1x1 root")]
    O["dock"]["loops"] = [loop(0x2009, 39, 100, (31, 5), at="root", src="dock house 0x3D: 0x0044BFA0, at the 1x1 root of the house")]
    O["dock"]["pier_loops"] = [
        loop(0, 34, 40, [[0x200E, 70, 18], [0x200C, 81, 12], [0x200B, 45, 12], [0x200D, 53, 0]], when="act", act="trade",
             src="0x0044C0B0 table 0x5F89E4 while a ship trades (dock_trade_anim, figure_trade_ship_update); speed 4 + 1 per redraw: ours 40 ms"),
        loop(0, 32, 100, [[0x2008, 70, 9], [0x2006, 60, 18], [0x2005, 47, 19], [0x2007, 50, 4]], src="0x0044C0B0 table 0x5F8A44")]
    O["fishing_wharf"]["loops"] = [
        loop(0, 20, 80, [[0x201D, 78, -3], [0x201F, 72, 13], [0x201E, 41, 14], [0x201C, 45, 0]], when="act", act="unload",
             src="0x0045AB70 table 0x5F8DA8: its boat moored (action 10); boat building (goods_0, 0x5F8E08) not in ours"),
        loop(0, 12, 120, [[0x2046, 62, 7], [0x2046, 65, 31], [0x2046, 45, 33], [0x2046, 54, 4]], dirs=8, dir="2o", src="0x0045AB70 table 0x5F8D48")]
    O["urchin_quay"]["loops"] = [
        loop(0, 50, 80, [[0x2018, 61, 20], [0x201A, 61, 32], [0x2019, 44, 25], [0x2017, 64, 14]], when="act", act="unload",
             src="0x0045ADE0 table 0x5F8EC8 while the collector unloads (200 ticks; urchin_collector_unload 0x00430400 steps it)"),
        loop(0, 12, 120, [[0x2046, 65, -1], [0x2046, 72, 23], [0x2046, 48, 20], [0x2046, 48, 4]], dirs=8, dir="2o", src="0x0045ADE0 table 0x5F8E68")]
    gp = atlas(gen)[1][O["guardpost"]["base"]]["width"]
    O["theatre"]["loops"] = [loop(0x2016, amb_first(0x2017) - amb_first(0x2016), 20 * raw_speed("SprAmbient", amb_first(0x2016)),
                                  (0x96, -0x1A), when="show", src="city_draw case 0x52 -> FUN_0044CB80 (timer Building+0x98), "
                                  "only when staffed and venue_shows != 0: actors on the stage")]
    O["guardpost"]["loops"] = [loop(0x205A, 53, 80, (((gp + 1) >> 1) - 5, 8), src="animation_draw case 0x7C (0x0045D140): a pacing sentry "
                                    "instead of the base's 10 frames (LI placeholder boxes), via 0x0044DDE0 (dx -5, dy 8 from the base centre)")]
    # `stock_pics` (building_extra_draw 0x0044F320, any state): picture top-left = draw point + (dx, dy), no anchors.
    # rule std: n = (s - 100) // 100 (none below 100), min(n, max); any: s > 0 -> first; ge100: s >= 100 -> first;
    # mint: s != 0 -> min(max((s - 50) // 50, 0), 2) (C truncation); reverse: image = first + max - n
    def pic(good, group, rule, mx, dx, dy, **kw):
        return {"good": good, "file": kw.pop("file", gen), "first": group_first(kw.pop("file2", gen), group), "rule": rule, "max": mx,
                "dx": dx, "dy": dy, **kw}
    S = {"growers_lodge": [pic("olives", "SPR_WSHOP_OLIVES", "ge100", 0, 41, 10), pic("grapes", "SPR_WSHOP_GRAPES", "ge100", 0, 45, 22)],
         "sheep_farm": [pic("fleece", "SPR_WSHOP_FLEECE", "std", 4, 12, -13)],
         "goat_farm": [pic("cheese", "SPR_WSHOP_CHEESE", "std", 4, 43, 16)],
         "hunting_lodge": [pic("meat", "SPR_WSHOP_PORK", "std", 4, 63, 7)],
         "mint": [pic("silver", "SPR_MINT_ORE", "mint", 2, 85, 3)],
         "marble_quarry": [pic("marble", "SPR_MARBLE_OVERLAY", "std", 7, 33, 0, reverse=True, before_anim=True,
                               offsets={"0": [43, 9], "1": [43, 9], "2": [33, 9], "3": [33, 9]})],
         # building_extra_draw case 0xD5: the quarry's table and rule, images group 28 first + 8 - n (701..708)
         "black_marble_shop": [dict(pic("black_marble", "SPR_B_BLACK_MARBLE_SHOP", "std", 7, 33, 0, reverse=True,
                                        before_anim=True, file=pos, file2=pos, offsets={"0": [43, 9], "1": [43, 9],
                                                                                        "2": [33, 9], "3": [33, 9]}),
                                    first=group_first(pos, "SPR_B_BLACK_MARBLE_SHOP") + 1)],
         "foundry": [pic("bronze", "SPR_WSHOP_BRONZE", "any", 0, 25, -10)],
         "timber_mill": [pic("wood", "SPR_WSHOP_WOOD", "any", 0, 65, 3)],
         "winery": [pic("grapes", "SPR_WSHOP_GRAPES", "std", 2, 73, -15)],
         "oil_press": [pic("olives", "SPR_WSHOP_OLIVES", "std", 2, 47, 8)],
         "sculpture_studio": [pic("bronze", "SPR_WSHOP_BRONZE", "std", 4, 39, 7)],
         "horse_ranch": [pic("wheat", "SPR_WSHOP_WHEAT", "std", 7, 75, 16)],
         "armory": [pic("bronze", "SPR_WSHOP_BRONZE", "std", 2, 44, 9)],
         "trireme_wharf": [pic("wood", "SPR_WSHOP_WOOD", "std", 4, 0, 0, by_orient=[[84, 30], [7, -6], [24, 0], [112, -12]]),
                           pic("armor", "SPR_WSHOP_ARMOR", "std", 4, 0, 0, by_orient=[[104, 25], [27, 9], [44, 15], [132, 3]])]}
    for k, v in S.items():
        if k in O:
            O[k].pop("stock_overlay", None)
            O[k]["stock_pics"] = v
    O["horse_ranch"]["corral"] = {"file": gen, "base": group_first(gen, "SPR_B_RANCH_CORRAL"), "img_tiles": 4,
                                  "rule": "4x4 at b.corral (exe building 0x86, FUN_00496CA0 case 0x85), one picture for every orientation"}
    O["horse_ranch"]["note"] = ("ranch 3x3 house + its 4x4 corral (b.corral; production.md 'Horse ranch parts', bugs.md 134); "
                                "ranches of old saves without room for a corral draw the house only")
    # ---- roads ------------------------------------------------------------------------------------------
    # rows [pattern, view-0 offset, [offset per view 0, 2, 4, 6]] from the exe tables (terrain_images.py T_ROAD_B /
    # T_ROAD_A): the pattern engine FUN_004A6920 picks column view/2 (docs/play/rotation.md)
    import terrain_images as ti
    pat = lambda p: "".join("." if v == 2 else str(v) for v in p)
    tab17 = [(pat(p), ks[0], list(ks)) for p, ks, _, _ in ti.T_ROAD_B]
    tab48 = [(pat(p), ks[0], list(ks)) for p, ks, _, _ in ti.T_ROAD_A]
    O["road"] = {"file": "Zeus_Terrain", "size": 1, "kind": "road",
                 "kinds": [{"name": "rutted", "desirability": "< 0", "first": group_first("Zeus_Terrain", "SPR_RUTTED_ROAD"), "count": 49, "table": "tab48"},
                           {"name": "dirt", "desirability": "0..15", "first": group_first("Zeus_Terrain", "SPR_ROADS"), "count": 18, "table": "tab17"},
                           {"name": "paved", "desirability": "16..29", "first": group_first("Zeus_Terrain", "SPR_PAVED_ROADS"), "count": 49, "table": "tab48"},
                           {"name": "plaza", "desirability": ">= 30", "first": group_first(gen, "SPR_PLAZA_1X1"), "file": gen, "count": 7, "table": None,
                            "variant": "grid_random[tile] % 7"}],
                 "neighbours": "bits in order N,NE,E,SE,S,SW,W,NW = tiles (x,y-1),(x+1,y-1),(x+1,y),(x+1,y+1),(x,y+1),(x-1,y+1),(x-1,y),(x-1,y-1); "
                               "pattern char per neighbour: '1' must be a road, '0' must not, '.' any; first matching row of the table wins; image = kind.first + offset",
                 "neighbour_is_road": "terrain flag 0x40 (road) or 0x08000000 (exe mask 0x8000040)",
                 "tab17": tab17, "tab48": tab48,
                 "src": "exe FUN_004A0190 (choice by desirability FUN_004A0450), pattern engine FUN_004A6920, tables 0x00637098 (17 rows) and 0x006371F0 (48 rows)",
                 "confidence": "table rows and offsets verified from the exe; which 49-image group is 'rutted' vs 'paved' and the desirability thresholds inferred (medium)"}
    json.dump(O, open(os.path.join(ROOT, "data", "play", "buildings.json"), "w"), indent=1)
    miss = [k for k in bsim if k not in O]
    print(len(O), "entries; no entry:", miss)


if __name__ == "__main__":
    main()
