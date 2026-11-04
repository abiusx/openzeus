"""Build data/play/ui.json: the original in-game city screen UI (play mode, docs/play/ui.md).

    re/venv/bin/python tools/play_ui.py        (needs pefile; reads zeus-original/app/Zeus.exe)

Every table that the exe holds (control-panel draw tables, page build buttons, overlay lists, build
submenus, info-window buttons, minimap groups) is read from Zeus.exe at the addresses given in the
output; packed group ids (collection*512 + group rank) are resolved to atlas indices with
extracted/sprites/<file>/atlas.json (rank == atlas group id, checked for Zeus_Fonts/Interface/General).
Geometry that is code (immediates) is written here by hand with the function address it comes from.
Measurements from oracle screenshots are tagged evidence "seen".
"""
import json
import os
import struct

import pefile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(ROOT, "extracted", "sprites")
EXE = os.path.join(ROOT, "zeus-original", "app", "Zeus.exe")
TEXT = os.path.join(ROOT, "extracted", "text", "zeus_text.json")
OUT = os.path.join(ROOT, "data", "play", "ui.json")
COLL = {0: "Zeus_Fonts", 1: "Zeus_Interface", 2: "Zeus_Unloaded", 3: "Poseidon_Unloaded", 4: "Zeus_General",
        5: "Zeus_Terrain", 51: "SprMain", 52: "Poseidon_Loaded", 53: "PoseidonImps"}

PE = pefile.PE(EXE, fast_load=True)
BASE = PE.OPTIONAL_HEADER.ImageBase


def rd(va, n):
    rva = va - BASE
    for s in PE.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            b = s.get_data()[rva - s.VirtualAddress:rva - s.VirtualAddress + n]
            return b + b"\0" * (n - len(b))
    raise KeyError(hex(va))


def i32(va):
    return struct.unpack("<i", rd(va, 4))[0]


_atl = {}


def atlas(f):
    if f not in _atl:
        a = json.load(open(os.path.join(SPR, f, "atlas.json")))
        _atl[f] = ({g["id"]: g for g in a["groups"]}, {i["index"]: i for i in a["images"]},
                   {g["name"]: g for g in a["groups"]})
    return _atl[f]


def group(packed, off=0):
    """packed group id -> sprite ref of its first image (+off)."""
    coll, rank = divmod(packed, 512)
    f = COLL[coll]
    g = atlas(f)[0][rank]
    return {"file": f, "index": g["first"] + off, "group": g["name"]}


def gref(f, name, off=0):
    g = atlas(f)[2][name]
    return {"file": f, "index": g["first"] + off, "group": name}


def size(ref):
    im = atlas(ref["file"])[1][ref["index"]]
    return [im["width"], im["height"]]


def drawtab(va, n):
    """40-byte widget draw entries (0x004316F0): x,y,w,h, packed group, image offset, state bytes."""
    out = []
    for i in range(n):
        e = rd(va + 40 * i, 40)
        x, y, w, h = struct.unpack("<hhhh", e[:8])
        g = struct.unpack("<H", e[10:12])[0]
        img = struct.unpack("<h", e[12:14])[0]
        out.append(dict(x=x, y=y, w=w, h=h, packed=g, img=img, state=e[0x18], arg1=struct.unpack("<i", e[0x14:0x18])[0]))
    return out


def hittab(va, n):
    out = []
    for i in range(n):
        e = rd(va + 28 * i, 28)
        l, t, r, b = struct.unpack("<hhhh", e[:8])
        out.append([l, t, r, b])
    return out


TXT = json.load(open(TEXT))


def text(g, i):
    s = TXT.get(str(g), [])
    return s[i] if 0 <= i < len(s) else None


STATES = {"normal": 0, "hover": 1, "selected": 2, "disabled": 3}


def widget(e, name, ox, oy, tooltip=None, extra=None):
    """One draw-table entry as a UI element; position relative to the panel's left edge (x) / screen top (y)."""
    base = group(e["packed"], e["img"])
    d = {"name": name, "rect": [e["x"] + ox, e["y"] + oy, e["w"], e["h"]],
         "sprite": base, "sprite_size": size(base),
         "states": {k: {"file": base["file"], "index": base["index"] + v} for k, v in STATES.items()}}
    if tooltip:
        d["tooltip"] = tooltip
    if extra:
        d.update(extra)
    return d


def main():
    # ---------------- control panel (0x00517BF0 panel_draw, origin (panelX, 0x16)) ----------------
    main_tab = drawtab(0x0063DC40, 17)
    page_names = [text(88, i) for i in range(25)]
    pages = []
    for i in range(11):
        pages.append(widget(main_tab[i], f"page_{i}", 0, 0x16, {"group": 88, "index": i, "text": page_names[i]},
                            {"page": i}))
    tools = []
    for i, key in zip(range(11, 15), ["build_road", "build_roadblock", "clear", "undo"]):
        tools.append(widget(main_tab[i], key, 0, 0x16, {"group": 88, "index": i, "text": page_names[i]}))
    tabs = [widget(main_tab[15], "tab_overview", 0, 0x16, {"group": 88, "index": 15, "text": page_names[15]},
                   {"category": 0}),
            widget(main_tab[16], "tab_radar", 0, 0x16, {"group": 88, "index": 16, "text": page_names[16]},
                   {"category": 1})]
    low_tab = drawtab(0x0063DF80, 7)
    alert_kinds = ["FIRE", "EARTHQUAKE", "FLOOD", "LANDSLIDE", "LAVA", "COLLAPSED_BUILDING", "BLOCKED_ROAD",
                   "DISEASE", "PLAGUE", "ENEMY_INVASION", "MONSTER_INVASION", "GOD_INVASION", "GOD_ARRIVES",
                   "HERO_ARRIVES", "SOLDIERS_RETURN"]
    alerts = []
    for i in range(4):
        w = widget(low_tab[i], f"goto_{i + 1}", 0, 0x16, {"group": 88, "index": 17 + i, "text": page_names[17 + i]})
        w["note"] = ("event 'go to' button; drawn only while an alert of that slot is active; the image group "
                     "is chosen at run time from SPR_BTN_ALERTS_<KIND> (3 images: normal, hover, selected)")
        alerts.append(w)
    # the slots' pictures at run time (FUN_00410230): an alert of type t -> packed group 0x005D83CC[t] (+0 normal,
    # +1 hovered, +2 pressed); an empty slot -> group 0x279 with offset -3, drawn with state 0 (+3): the first image
    # of SPR_BTN_ALERTS_DISABLED, which matches the panel art under it. Balloons 68:(178 + t) (FUN_004F5F00)
    alert_types = []
    for t in range(15):
        g = group(i32(0x005D83CC + 4 * t))
        alert_types.append({"type": t, "name": alert_kinds[t].lower(), "sprite": g,
                            "balloon": {"group": 68, "index": 178 + t, "text": text(68, 178 + t)}})
    alert_empty = group(0x279)
    lower = [widget(low_tab[4], "messages", 0, 0x16, {"group": 88, "index": 21, "text": page_names[21]}),
             widget(low_tab[5], "goals", 0, 0x16, {"group": 88, "index": 22, "text": page_names[22]}),
             widget(low_tab[6], "world_map", 0, 0x16, {"group": 88, "index": 23, "text": page_names[23]})]
    rot = drawtab(0x0063E098, 1)[0]
    rbase = group(rot["packed"])
    rotate = {"name": "rotate", "rect": [rot["x"], rot["y"] + 0x16, rot["w"], rot["h"]], "sprite": rbase,
              "sprite_size": size(rbase),
              "image_rule": "first + (view_rotation/2)*8 + (4 if pressed else 1 if hovered else 0)",
              "evidence": "exe 0x00517A20 (entry 0x0063E098)"}

    # per-page content (origin (panelX, 0x1e))
    ovl_lists = []
    for p in range(11):
        ids = [i32(0x0063E2E0 + p * 20 + 4 * k) for k in range(5)]
        ovl_lists.append([x for x in ids if x])
    ovl_tab = drawtab(0x0063E3C0, 5)
    ob = group(ovl_tab[0]["packed"], ovl_tab[0]["img"])
    overlay_buttons = {"rects": [[e["x"], e["y"] + 0x1e, e["w"], e["h"]] for e in ovl_tab],
                       "sprite": ob, "sprite_size": size(ob),
                       "states": {k: {"file": ob["file"], "index": ob["index"] + v} for k, v in STATES.items()},
                       "label": "text group 14 [overlay id], centred in the button width, y = button y + 8 (0x26-0x1e), font SPR_FONTS_9LTBK (font table entry 10)",
                       "selected_rule": "selected when the current overlay (0x00FA05F0) equals the button's overlay id",
                       "evidence": "exe 0x005170A0 (table 0x0063E3C0, lists 0x0063E2E0)"}
    extra_btn = drawtab(0x0063DEE8, 1)[0]
    eb = group(extra_btn["packed"])
    advisor_btn = {"name": "advisor_magnifier", "rect": [extra_btn["x"], extra_btn["y"] + 0x1e, extra_btn["w"], extra_btn["h"]],
                   "sprite": eb, "sprite_size": size(eb),
                   "states": {k: {"file": eb["file"], "index": eb["index"] + v} for k, v in STATES.items()},
                   "advisor_per_page": [i32(0x0063E488 + 4 * p) for p in range(11)],
                   "evidence": "exe 0x00516FA0 (entry 0x0063DEE8, advisor ids 0x0063E488)"}
    btab = drawtab(0x0063E240, 4)
    build_slots = [[e["x"], e["y"] + 0x1e, e["w"], e["h"]] for e in btab]
    sub_of = {0x1a: 0xb, 0x1b: 4, 0x1e: 0xd, 0x22: 0xe, 0x26: 0xf, 0x2b: 0x10, 0x2f: 0x11, 0x34: 0x12, 0x43: 0x13,
              0x53: 0x14, 99: 0x15, 0x89: 5, 0x8a: 6, 0x8b: 10, 0x8c: 8, 0x8d: 3, 0x8e: 7, 0x8f: 0x17, 0x9d: 0x16,
              200: 0x23, 0xd0: 0x24, 0xd1: 0x25}  # FUN_00403F00 (Zeus game; 0x53 -> 0x26 in Poseidon)
    page_content = []
    for p in range(11):
        slots = []
        for s in range(4):
            tool, icon = struct.unpack("<ii", rd(0x0063E0C0 + (s + p * 4) * 8, 8))
            if not tool:
                slots.append(None)
                continue
            if icon < 0x21:
                ref = group(0x239, icon * 3)
            else:
                ref = group(0x6806, icon * 3 - 99)
            slots.append({"slot": s, "rect": build_slots[s], "tool": tool, "text": text(28, tool),
                          "tooltip": {"group": 28, "index": tool},
                          "sprite": ref, "states": {"normal": ref["index"], "hover": ref["index"] + 1,
                                                    "selected": ref["index"] + 2},
                          "submenu": sub_of.get(tool)})
        page_content.append({"page": p, "title": {"group": 88, "index": p, "text": page_names[p]},
                             "overlays": [{"id": o, "text": text(14, o)} for o in ovl_lists[p]],
                             "build_buttons": slots, "advisor": i32(0x0063E488 + 4 * p)})

    # ---------------- build submenus (0x005F27D4 rows of 75 ints; draw 0x0058F650; hit 0x00402790) -------------
    menus = {}
    for m in range(0x27):
        row = [i32(0x005F27D4 + (m * 75 + k) * 4) for k in range(75)]
        items = []
        for k in range(1, 75):
            if row[k] < 1:
                break
            items.append(row[k])
        menus[m] = items
    sub_names = {3: "Recreational Areas", 4: "Drama", 5: "Philosophy", 6: "Athletics", 7: "Beautification",
                 8: "Military Workshops", 10: "Fortifications", 11: "Trade", 13: "Farms", 14: "Orchards",
                 15: "Herding", 16: "Land and Sea", 17: "Raw Materials", 18: "Workshops", 19: "Agoras",
                 20: "Sanctuaries", 21: "Poseidon Pyramid (god statues)", 22: "Monuments", 23: "Hero's Hall",
                 35: "Hippodrome", 36: "Astronomy", 37: "Technology", 38: "Sanctuaries (Poseidon game)"}
    submenus = {}
    for m, nm in sub_names.items():
        items = menus[m]
        entry = {"name": nm, "items": [{"tool": t, "text": text(28, t)} for t in items]}
        if m == 0x16:
            entry = {"name": nm, "items": "commemorative monuments: index table 0x005F41A0, text group 0xC6 (198), "
                                          "listed only when g_commemorative_available[i]"}
        if m == 0x17:
            entry = {"name": nm, "items": "hero halls: table 0x005F42CC, text group 0xB9 (185) index+7, listed when FUN_004FA620"}
        if m == 0x0b:
            entry["items"] = "trade buildings: table 0x005F34BC, label by trade_building_label (city name), listed when FUN_005B9410"
        if m == 0x15:
            entry["items"] = "god statues of the Poseidon pyramid: table 0x005F4074 -> scenario gods"
        submenus[str(m)] = entry
    y0 = [struct.unpack("<i", rd(0x005F5664 + 8 * n, 4))[0] for n in range(24)]
    submenu_geom = {
        "evidence": "exe 0x0058F650 (draw), 0x00402790 (hit), 0x004029D0 (count), 0x005127F0 (width); seen at 1024x768",
        "anchor": "right edge of the bars is panelX-5; menu is left of the control panel",
        "cells_C": "ceil(max width of text group 28 strings in font SPR_FONTS_11C / 16) (0x005127F0); English GOG = 15",
        "bar_x": "panelX - 117 - 16*C  (1024x768: 481)",
        "bar_cells": "C + 7 (16-px tiles; 1024x768: 22 = 352 px)",
        "row_y": "Y0[n] + 0x6E + 24*i, n = number of listed (available) items, i = 0..n-1",
        "Y0_by_count": y0,
        "row_height": 20, "row_pitch": 24,
        "bar_tiles": {"style_hovered": 1, "style_normal": 2,
                      "left": "SPR_PANELING first + 26 + 3*style", "middle": "first + 27 + 3*style",
                      "right": "first + 28 + 3*style",
                      "sprites": {"normal": [gref("Zeus_Interface", "SPR_PANELING", 26 + 6 + k) for k in range(3)],
                                  "hovered": [gref("Zeus_Interface", "SPR_PANELING", 26 + 3 + k) for k in range(3)]},
                      "draw": "middle tile at x, x+16, ... (cells tiles), then left tile at x and right tile at x+16*(cells-1) (0x0059FBA0)"},
        "label": {"text": "group 28 [tool]", "x": "panelX - (16*C+20) - 0x59", "width": 0xB0, "dy": 3,
                  "font_normal": "SPR_FONTS_11C (font table entry 1)", "font_hovered": "SPR_FONTS_11CB (entry 5)",
                  "colour_normal": "0x3EFA (565)", "colour_hovered": "0xFAC1 (565)"},
        "cost": {"icon": gref("Zeus_General", "SPR_REQUEST_CASH_ICON"), "icon_x": "panelX - 0x52", "icon_dy": -2,
                 "number_x": "panelX - 0x42", "number_dy": 4,
                 "value": "model building cost (model_building_value(tool,0)); not drawn when 0"},
        "sanctuary_extra_costs": {"marble_icon": "Zeus_General SPR_GOODS_ICONS (packed 0x87B) + goods index, x=panelX-0x82, dy=+2",
                                  "black_marble_icon": "Poseidon_Loaded SPR_BLACK_MARBLE_ICON (0x682A)",
                                  "drachma_x": "panelX - 0xB2 + 16*k (k = 3, 6 or 9 after the extra icons)"},
        "hit": "rows [bar_x, row_y, bar_x+16*(C+7), row_y+20) (table 0x005ED1E0); left press selects (build_tool_select 0x00404330)",
        "close": "screen 6 is left by choosing an item, clicking a page button, or right click (returns to screen 1)",
    }

    # ---------------- info window (0x005715A0) ----------------
    help_close = drawtab(0x005EF708, 2)
    info = {
        "evidence": "exe 0x005715A0 (placement), 0x0056E960 (typical body), table 0x005EF708; seen in oracle shots",
        "frame": "titled frame (SPR_MARBLE1, 0x0059EE90), width 29 cells (464 px)",
        "x": {"640x480": 8, "800x600": 68, "1024x768": 188, "rule": "0x44/0x80/0xF8 minus 60 (folded-panel flag 0)"},
        "y": {"1024x768": "mouse y < 397 ? 760 - 16*rows : 32", "800x600": "mouse y < 313 ? (37-rows)*16 : 32",
              "640x480": 32, "wide (arm64 rule)": "mouse y < H/2+12 ? H-8-16*rows : 32"},
        "rows_by_class": {"0 (default, also walkers)": 22, "1": 16, "2": 18, "3": 19, "4": 14, "5 (agora, crops)": 24,
                          "6 (composite: sanctuary, monuments, palace)": 31},
        "overrides": {"storehouse/granary/vendors 0x39 0x3A 0x3D 0x3E": "x=0, y=32, 30x(4*goods/3+13) or 32x25",
                      "type 0x7D": "x=0, y=45, 40x29", "type 0x75": "rows 12"},
        "title": "text centred in 16*cols at y+10, font SPR_FONTS_22C (entry 6) in 0x0056E960",
        "body_text": "x+15, y+40, width 16*cols, font SPR_FONTS_11C (entry 1)",
        "workers_box": "plain frame (SPR_MARBLE2) at (x+15, y+16*rows-128), cols-2 wide, 5 rows (0x0056E960); "
                       "the sanctuary window draws it at (x+16, y+388) seen",
        "help_button": {"rect": [help_close[0]["x"], "16*rows-40", 27, 27],
                        "sprite": group(help_close[0]["packed"], help_close[0]["img"]),
                        "states": "+0 normal, +1 hover, +2 pressed"},
        "close_button": {"rect": [help_close[1]["x"], "16*rows-37", 24, 24],
                         "sprite": group(help_close[1]["packed"], help_close[1]["img"]),
                         "states": "+0 normal, +1 hover, +2 pressed"},
        "button_highlight": "window_highlight_draw (SPR_RIMS): e.g. Oracle 'Consult Oracle' 301x32 at (x+75, y+240) seen",
        "walker": {"rows": 22, "seen_1024": {"frame": [188, 32, 464, 352], "inner_frame_marble2": [216, 72, 420, 152],
                                              "speech_highlight_rims": [212, 134, 416, 122]},
                   "figure_slots": {"rects": hittab(0x005EE858, 7), "note": "up to 7 figure thumbnails 50x50 at (x+26+60i, y+46) (hit table 0x005EE858)"}},
    }

    # ---------------- minimap ----------------
    mm_types = {}
    for ty in range(221):
        v = i32(0x005F6368 + ty * 32 + 28)
        if v > 0:
            mm_types[str(ty)] = {"text": text(28, ty), "sprite": group(v)}
    minimap = {
        "evidence": "exe 0x00454980 (draw), 0x004547C0 (scroll), call sites 0x0051C7E0 / 0x00517480",
        "rects": {"radar_tab": [50, 165, 128, 110], "overview_page": [50, 318, 128, 110]},
        "projection": "one map tile = 2 pixels wide x 1 pixel tall (iso rows alternate by 1 px: x = left - (row&1)); "
                      "the 2 pixels are the first 2 pixels of the chosen sprite image (0x00456BA0)",
        "scroll": "centred on the main view, clamped to the map (0x004547C0)",
        "view_rect": "1-px outline colour 0xF800 (red, 565) = the main view (0x00509870)",
        "terrain": [
            {"test": "off-map / void", "group": "SPR_R_SPACE"},
            {"test": "flags & 0x15374AE7 == 0 (plain land)", "group": "SPR_R_GRASS", "variant": "rand & 6"},
            {"test": "flags & 0x15374AE7 == 0x80 (scrub only)", "group": "SPR_R_SCRUB", "variant": "scrub level + (rand & 1)"},
            {"test": "water 0x4: road 0x40 with bridge byte", "group": "SPR_R_ROAD"},
            {"test": "water 0x4 and 0x4000000", "group": "SPR_R_RIVER", "variant": "rand & 3"},
            {"test": "water 0x4", "group": "SPR_R_DEEPWATER", "variant": "rand & 3"},
            {"test": "tree 0x1", "group": "SPR_R_WOODS", "variant": "rand & 3"},
            {"test": "marble 0x20000 (by regrowth 255 / <100 / else)", "group": "SPR_R_QUARRY", "variant": "+0/+4/+3 (+ rand&1)"},
            {"test": "rock 0x100002", "group": "SPR_R_COPPER_ROCK", "variant": "rand & 3"},
            {"test": "rock 0x200002", "group": "SPR_R_SILVER_ROCK", "variant": "rand & 3"},
            {"test": "0x300000 (orichalc)", "group": "Poseidon_Loaded (bank 52)", "variant": "rand & 3"},
            {"test": "rock (other)", "group": "SPR_R_ROCK", "variant": "rand & 3"},
            {"test": "beach 0x10000", "group": "SPR_R_DUNES", "variant": "rand & 7"},
            {"test": "marsh 0x40000", "group": "SPR_R_WOODS", "variant": "rand & 4"},
            {"test": "0x1000000 (fertility layer)", "group": "SPR_R_LAVA", "variant": "(rand&1) + value*6/100"},
            {"test": "wall 0x4000", "group": "SPR_R_FIRST_BUILD + 0x3C"},
            {"test": "cliff 0x200", "group": "SPR_R_ELEVATION", "variant": "rand & 3"},
            {"test": "road 0x40", "group": "SPR_R_ROAD"},
            {"test": "garden 0x20", "group": "SPR_R_FIRST_BUILD + 0x32"},
            {"test": "0x10000000", "group": "SPR_R_FIRST_BUILD + 0x37"},
            {"test": "meadow 0x800", "group": "SPR_R_MEADOW", "variant": "meadow >> 5"},
        ],
        "terrain_status": "order and groups read from 0x00454980 (game-mode branch); a few flag names hypothesis",
        "buildings": {"rule": "on the building's draw tile (draw byte bit 0x40): image of the per-type minimap group; "
                              "piece size (grid_piece & 0xF): 0 -> 2 px of image+0; 1 -> image+1 at y-1; 2..4 -> image+n at y-n; "
                              "5 -> image+2 three times; burning buildings tinted 0xF863",
                      "per_type": mm_types},
        "figures": "tiles with soldiers/enemies: a 2-px dot (colour by climate, 0x7800/0x3C00/...); gods/monsters/heroes: "
                   "SPR_R_GOD / SPR_R_MONSTER / SPR_R_HERO (figure types 0x43/0x44/0x45)",
        "overlays": "with an overlay active, buildings use the overlay object's colour function (vtable +0x24 of 0x00641C10[overlay])",
    }

    # ---------------- assemble ----------------
    panel = {
        "anchor": "right: panelX = W - 186 (0x0058E280: 478/598/838 for 640/800/1024)",
        "width": 186,
        "background": {"sprite": gref("Zeus_Interface", "SPR_SIDE_MAIN_PANEL"), "rect": [0, 0, 186, 768],
                       "note": "one 186x768 image with transparent holes for the buttons; the god art at the bottom is part of it; "
                               "800x600 clips it at y=600; below 768 rows (wide modes) the arm64 host repeats rows 762..767 "
                               "(texture only) with a random horizontal shift, keeping the 7-px left border (not original)"},
        "table_origin_y": {"main_and_lower": 0x16, "page_content": 0x1E},
        "state_rule": "image = group first + offset + (3 if disabled else 2 if selected else 1 if hovered else 0); "
                      "state byte 2 = not drawn (draw table 0x004316F0)",
        "tabs": tabs, "pages": pages, "tools": tools, "alerts": alerts, "lower": lower, "rotate": rotate,
        "alert_types": alert_types, "alert_empty": alert_empty,
        "page_title": {"rect": [50, 30, 130, 0], "text": "group 88 [page] centred in 130 px, font SPR_FONTS_11C",
                       "evidence": "exe 0x00517480"},
        "overlay_buttons": overlay_buttons,
        "info_box": {"frame": "plain frame (SPR_MARBLE2) at (50, 300 - hh), 8 cells wide, hh/16 rows; "
                              "hh = u + 32 - (u & 15), u = (11 - n_overlay_buttons) * 20; drawn when category 0 or page 10",
                     "evidence": "exe 0x00517480; seen (888,76) for 1 overlay at 1024x768"},
        "advisor_button": advisor_btn,
        "name_bar": {"frame": "plain frame (50, 302) 8x1 + bottom row (50, 304)", "text_y": "0x134 (building) / 0x136 (button names), centred in 130 px from x=50, font SPR_FONTS_9DKBU (entry 13)",
                     "shows": "name of the hovered page button (group 88) or build button (group 28) + its cost with SPR_REQUEST_CASH_ICON",
                     "evidence": "exe 0x00517210"},
        "build_buttons": {"rects": build_slots, "evidence": "exe 0x00516D50 (table 0x0063E0C0 per page, draw table 0x0063E240)",
                          "image_rule": "icon < 33: Zeus_Interface SPR_BUILD_BTNS + 3*icon; else Poseidon_Loaded packed 0x6806 + 3*icon - 99; "
                                        "+1 hover, +2 selected; hidden when the slot has no tool or the tool is not available (0x00787178)"},
        "minimap": minimap["rects"],
        "message_strip": {"rect_seen": [8, 512, 172, 48], "note": "last message text area (part of the background art); text by another agent"},
    }
    top_bar = {
        "background": {"sprite": gref("Zeus_Interface", "SPR_TOP_BAR"), "rect": [0, 0, 838, 30],
                       "rule": "1024: at (0,0); 800: at (0,0) clipped at x = panelX; 640: at (-360,0) (0x0059EBE0)",
                       "wide": "not original: arm64 host extends x>=838 up to panelX by mirroring the last 500 px"},
        "menus": {"titles": [{"group": 1, "text": text(1, 0), "items": 6}, {"group": 2, "text": text(2, 0), "items": 7},
                             {"group": 3, "text": text(3, 0), "items": 4}],
                  "layout": "first title at x=10, y=6; each next title starts 10 px after the previous ends (0x004310E0, table 0x005EFF00); "
                            "font SPR_FONTS_11C; open/hovered title drawn with colour 0xFAC1 and shadow style",
                  "dropdown": {"frame": "titled-frame middle tiles (0x0059F0F0) at (title_x, 24), cells = text-group width cells "
                                        "(FUN_00512870), rows = (items+1)*20/16",
                               "items": "text (title_x+8, 30 + 20*i), font SPR_FONTS_11C; hovered: SPR_FONTS_11LTYEL (entry 9), colour 0xFAC1, shadow style",
                               "item_tables": {"File": "0x005EFCC0", "Options": "0x005EFD20", "Help": "0x005EFD90"},
                               "evidence": "exe 0x00431210 (screen 3 draw), seen"}},
        "funds": {"icon": gref("Zeus_General", "SPR_CASH_ICON"), "x": {"800": 219, "1024": 381}, "y": 0,
                  "number": "at icon x + 16, y 5; font SPR_FONTS_11C (negative: rank 4)", "evidence": "exe 0x0058EB20, seen"},
        "population": {"icon": gref("Zeus_General", "SPR_POPULATION_ICON"), "x": {"800": 350, "1024": 525}, "y": 0,
                       "number": "at icon x + 16, y 5", "evidence": "exe 0x0058EB20, seen"},
        "date": {"x": "panelX - 110", "y": 5, "text": "month name (text group 25 [month]) then year (0x00508E50)",
                 "evidence": "exe 0x0058EB20"},
        "wide_rule": "the arm64 wide mode keeps the 1024 values (funds 381, population 525) and date at panelX-110",
    }
    frames = {
        "titled": {"function": "0x0059EE90", "sprite_group": gref("Zeus_Interface", "SPR_MARBLE1"), "tile": 16,
                   "top_row": {"first": 0, "last": 0xB, "middle": "1 + s"}, "bottom_row": {"first": 0x84, "last": 0x8F, "middle": "0x85 + s"},
                   "middle_rows": {"first": "0xC + p", "last": "0x17 + p", "middle": "0xD + s + p"},
                   "s": "counter of middle tiles in a row, 0..9 then wraps (ceiling 10)", "p": "+0xC after each middle row, wraps at 0x78"},
        "plain": {"function": "0x0059F2A0", "sprite_group": gref("Zeus_Interface", "SPR_MARBLE2"), "tile": 16,
                  "top_row": {"first": 0, "last": 6, "middle": "1 + s"}, "bottom_row": {"first": 0x2A, "last": 0x30, "middle": "0x2B + s"},
                  "middle_rows": {"first": "7 + p", "last": "0xD + p", "middle": "8 + s + p"},
                  "s": "wraps at 5", "p": "+7 per middle row, wraps at 0x23"},
        "highlight": {"function": "0x0059F6E0", "sprite_group": gref("Zeus_Interface", "SPR_RIMS"),
                      "tiles": "top +0 first, +1 middle, +2 last; bottom +6 first, +5 middle, +4 last; sides +7 left, +3 right; "
                               "inside not drawn; second variant = +8; last column/row pulled back so the rect is exact"},
        "button_bar": {"function": "0x0059ED50 / 0x0059FBA0", "sprite_group": gref("Zeus_Interface", "SPR_PANELING"),
                       "tiles": "3 per style (first, middle, last)"},
        "rule": "tile (r,c) at (x+16c, y+16r); a WxH panel = cols x rows of 16-px tiles (interface.md 5.3, verified natively by arm64)",
    }
    tooltip = {"evidence": "arm64 interface.md 6.6 (0x004F6E40)",
               "width": "190 px; 270 px if the text needs more than 2 lines", "height": "lines*16 + 10",
               "position": "20 px right of the mouse (left of it when mouse x >= screen - width - 20), 50 px below (72 above when y >= 200)",
               "box": "two nested rectangles, colours 0x84 / 0x9B2 (555) or 0x104 / 0x1372 (565)"}
    cursors = {"note": "Win32 cursor resources of Zeus.exe (monochrome 32x32), chosen by 0x0050B6F0",
               "default": {"resource": 0x66, "hotspot": [0, 0]}, "clear_land": {"resource": 0x82, "hotspot": [5, 26]},
               "military": {"resource": 0x88, "hotspot": [0, 0]}, "special": {"resource": 0xA6, "hotspot": [13, 10]},
               "build": "no special cursor: the building preview is drawn on the map"}
    layout = {
        "map_view": "x in [0, panelX), y in [0, H); the top bar (30 px) is drawn over it",
        "resolutions": {
            "1024x768": {"panelX": 838, "verified": "oracle screenshot"},
            "800x600": {"panelX": 598, "edge": {"sprite": gref("Zeus_Interface", "SPR_EDGE_800x600"), "x": 784, "y": 0},
                        "note": "panel image 186 wide drawn at 598, plus a 16x600 edge at 784; panel clipped at 600 rows",
                        "verified": "oracle screenshot"},
            "640x480": {"panelX": 478, "note": "exe values only; not a target"},
        },
        "larger": "the original has no mode above 1024x768. Use the 1024 rules with panelX = W-186: top bar left-anchored "
                  "(funds/population fixed x), date right-anchored to the panel, panel right-anchored and top-anchored, "
                  "info windows by the arm64 formulas, menus/submenus relative to panelX; fill top bar and panel bottom as the arm64 host does",
    }
    data = {
        "_doc": "Original Zeus in-game city UI. Sprite refs {file, index} = atlas index of extracted/sprites/<file>/atlas.json. "
                "Panel rects are [x, y, w, h] with x relative to panelX (the panel's left edge) and y from the screen top. "
                "See docs/play/ui.md. Generated by tools/play_ui.py from Zeus.exe.",
        "layout": layout, "top_bar": top_bar, "control_panel": panel, "pages": page_content,
        "overlays": {"names": {str(i): text(14, i) for i in range(len(TXT["14"]))},
                     "per_page": {str(p): ovl_lists[p] for p in range(11)},
                     "where": "buttons at the top of each control-panel page (category tab 0); space toggles the page overlay"},
        "submenu": submenu_geom, "submenus": submenus, "info_window": info, "frames": frames, "minimap": minimap,
        "tooltip": tooltip, "cursors": cursors,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w"), indent=1)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
