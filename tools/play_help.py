"""data/play/help.json: the in-game help ("Mythology Manual", Zeus_MM.eng) for the play mode's help window
(screen 5, help_page_draw 0x004F2D80; docs/play/help.md), and which record each help button opens.

    re/venv/bin/python tools/play_help.py      (needs pefile; reads Zeus_MM.eng and Zeus.exe)

records[i] = [layout, kind, x, y, cols, rows, pic, pic_x, pic_y, title_x, title_y, caption_x, caption_y,
              title, caption, body]  (record fields +0x00..+0x20, +0x44/+0x48/+0x4C; formats/eng.md "MM file")
by_type    = exe building type -> record (g_building_type_info 0x005F6368 + 32*type + 0x14; 0 = Table of Contents)
page_help  = control-panel page 0..10 -> record (0x0063E4B4, used by page_help 0x005169B0)
lower      = lower panel buttons 0..6 (alerts, messages, goals, world map) -> record (table 0x0063DF80, +0x20 arg2)
tools      = road / roadblock / clear / undo, category tabs (table 0x0063DC40 [11..16], +0x20 arg2; undo has none)
land, figures, heroes: the rules of FUN_005731D0 and building_info_panel_prepare (constants in the code)."""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from play_ui import rd  # noqa: E402  (Zeus.exe reader)

MM = os.path.join(ROOT, "zeus-original/app/Zeus_MM.eng")


def records():
    d = open(MM, "rb").read()
    assert d[:13] == b"Zeus MM file.", "not a Zeus MM file"
    n, = struct.unpack_from("<I", d, 0x14)
    area = 0x13898

    def s(o):
        return d[area + o:d.index(b"\0", area + o)].decode("cp1252") if o else ""
    out = []
    for i in range(n):
        r = d[0x18 + 80 * i:0x18 + 80 * (i + 1)]
        layout, kind = struct.unpack_from("<2H", r, 0)
        x, y, cols, rows, pic, px, py = struct.unpack_from("<7h", r, 6)
        tx, ty, cx, cy = struct.unpack_from("<4h", r, 0x1A)
        t, c, b = struct.unpack_from("<3I", r, 0x44)
        out.append([layout, kind, x, y, cols, rows, pic, px, py, tx, ty, cx, cy, s(t), s(c), s(b)])
    return out


def main():
    by_type = {t: struct.unpack("<i", rd(0x005F6368 + 32 * t + 0x14, 4))[0] for t in range(0xE0)}
    page_help = list(struct.unpack("<11i", rd(0x0063E4B4, 44)))
    lower = [struct.unpack("<i", rd(0x0063DF80 + 40 * i + 0x20, 4))[0] for i in range(7)]
    tools = [struct.unpack("<i", rd(0x0063DC40 + 40 * i + 0x20, 4))[0] for i in range(11, 17)]
    out = dict(
        note="tools/play_help.py: Zeus_MM.eng records + help record tables of Zeus.exe (docs/play/help.md)",
        records=records(),
        by_type={str(t): r for t, r in by_type.items() if r},
        # hero halls (type 0x7D) by hero = house_level: Achilles .. Bellerophon (building_info_panel_prepare)
        hero_hall=[63, 64, 65, 66, 67, 68, 74, 107],
        page_help=page_help, lower=lower, tools=tools,
        # land window (FUN_005731D0) by land kind 0xFFA138: road, water crossing, park, wall; else Terrain Types
        land={"6": 5, "11": 28, "12": 20, "24": 31}, land_default=113,
        # ... and by the shown figure's exe type: sheep/goat, wolf, boar (151 Deer when figure.resource != 0),
        # cattle, trireme, god, monster, hero, soldiers; anything else 91 Walkers
        figures={"49": 95, "50": 95, "59": 101, "51": 102, "76": 152, "57": 103, "67": 93, "68": 92, "69": 94,
                 "11": 96, "12": 96, "13": 96}, deer=151, figure_default=91,
        back=json.load(open(os.path.join(ROOT, "extracted/text/zeus_text.json")))["12"][0],   # 12:0 "Back"
        world_map=88, messages=87, goals=90, control_panel=86, about=0, contents=1,
    )
    path = os.path.join(ROOT, "data/play/help.json")
    json.dump(out, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
    print(path, len(out["records"]), "records; page_help", page_help, "lower", lower, "tools", tools)


if __name__ == "__main__":
    main()
