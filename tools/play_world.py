"""Build data/play/world.json and viewer/play/atlas/world/*.jpg: the world map screen for play mode
(viewer/play/world.js, docs/logic/world-map.md section 3, docs/play/world.md).

    re/venv/bin/python tools/play_world.py      (needs pefile; reads zeus-original/app/Zeus.exe)

- widgets: the exe's world-map draw table 0x005EF488 (12 x 40 B: rect, packed group, image offset, handler);
- map pictures: zeus-original/app/DATA/Zeus_MapOfGreece01..10.JPG copied (re-encoded losslessly as the same
  JPEG bytes) to viewer/play/atlas/world/ (git-ignored: the original's art);
- strings: the text groups the screen uses (extracted/text/zeus_text.json);
- layout: positions read from the panel code FUN_005981B0 (immediates), with the address.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import play_ui as U  # noqa: E402  (exe reader, atlas groups)

OUT = os.path.join(ROOT, "data", "play", "world.json")
PICS = os.path.join(ROOT, "viewer", "play", "atlas", "world")
DATA = os.path.join(ROOT, "zeus-original", "app", "DATA")

NAMES = ["back", "help", "attitude", "request", "requests", "gift", "raid", "conquer", "prev", "next",
         "history", "orders"]
TOOLTIPS = {"help": [68, 1], "attitude": [68, 4], "request": [68, 5], "gift": [68, 6], "raid": [44, 312],
            "conquer": [44, 313], "requests": [68, 8]}
GROUPS = [20, 21, 23, 25, 37, 39, 41, 47, 65, 92, 98, 253]
G44 = [83] + list(range(284, 330))


def main():
    import play_backdrops
    play_backdrops.world_pictures()                 # the pictures (also written by tools/assets.py build)
    widgets = []
    for name, e in zip(NAMES, U.drawtab(0x005EF488, 12)):
        raw = U.rd(0x005EF488 + 40 * NAMES.index(name), 40)
        handler = int.from_bytes(raw[16:20], "little")
        w = U.widget(e, name, 0, 0, {"group": TOOLTIPS[name][0], "index": TOOLTIPS[name][1],
                                     "text": U.text(*TOOLTIPS[name])} if name in TOOLTIPS else None)
        w["handler"] = f"0x{handler:08X}"
        widgets.append(w)
    texts = {str(g): U.TXT[str(g)] for g in GROUPS}
    texts["44"] = {str(i): U.TXT["44"][i] for i in G44}
    texts["68"] = {str(i): U.TXT["68"][i] for i in (37, 42)}
    texts["19"] = {"31": U.TXT["19"][31]}
    texts["61"] = {"205": U.TXT["61"][205]}
    texts["5"] = {str(i): U.TXT["5"][i] for i in (0x48, 0x49, 0x4A, 0x4B)}   # strike popups (screen 0x3F: 0x48 / 0x4A)
    side = U.gref("Zeus_Interface", "SPR_WORLD_SIDE_INT")
    out = dict(
        version=1,
        note="world map screen (docs/logic/world-map.md 3, docs/play/world.md); tools/play_world.py",
        pictures=[f"play/atlas/world/Zeus_MapOfGreece{n:02d}.jpg" for n in range(1, 11)],
        picture_size=[838, 738],
        side_panel=dict(sprite=side, size=U.size(side), evidence="exe 0x00597E60, FUN_00597E20: x = panelX (W > 800)"),
        widgets=widgets,
        layout=dict(evidence="exe FUN_005981B0 (immediates), seen re/oracle/runs/worldmap; tribute_x and tribute_amount x measured on the oracle shot (+4, +10 vs the immediates)",
                    box_x=16, box_w=151, kind_y=34, name_y=50, leader_y=69, our_city_y=46, our_name_y=65,
                    goods_x=20, goods_y=184, list_title_y=247, box_dx=24, row_dy=20, icon_dx=29, name_dx=54,
                    quota_x=129, quota_w=37, tribute_x=10, tribute_y=412, tribute_w=170, tribute_icon=[12, 424],
                    tribute_amount=[38, 428], suspended_y=444, click_info_y=202,
                    list_bottom=394),   # goods frame inner bottom (y 396, read back from SPR_WORLD_SIDE_INT in play mode)
        fonts=dict(title="11C", leader="9LTBK", rows="9DKBU", tribute="9DKBU", suspended="9DKYEL", label="11C",
                   evidence="exe font table 0x012AFBEC entries 1/10, font_group_entry(13), packed 0xE/0xF"),
        icons=dict(drachmas=U.gref("Zeus_General", "SPR_REQUEST_CASH_ICON"),
                   troops=U.gref("Zeus_General", "SPR_REQUEST_TROOPS_ICON"),
                   strike=U.gref("Zeus_General", "SPR_REQUEST_TROOPS_ICON"),
                   evidence="exe FUN_005981B0: packed 0x804 drachmas, 0x806 troops/strike; goods: info_panels goods_icons"),
        markers=dict(standard_offset="icon top-right", evidence="exe world_map_draw 0x00599DA0"),
        # the dialogs of screen 0x1A (FUN_00464C00 by mode 0x00903440; docs/play/world.md "Dialogs"): row icons the
        # exe picks by item (food: General entry 0x7A + 0x13; Interface group table entries k = atlas group k + 1)
        dialog_icons=dict(food=U.gref("Zeus_General", "SPR_GOODS_ICONS", 0x13),
                          can=U.gref("Zeus_Interface", "SPR_REQUEST_COMPLETE"),
                          cannot=U.gref("Zeus_Interface", "SPR_REQUEST_INCOMPLETE"),
                          months=U.gref("Zeus_Interface", "SPR_MOON"),
                          thumbs=U.gref("Zeus_Interface", "SPR_THUMBS"),
                          evidence="exe FUN_00464C00: food font_group_entry(0x7A)+0x10013; mode 5 entries 12/18 "
                                   "(can / cannot fulfil, FUN_004713E0), 19 months; mode 6 entry 175 + mood 0..5"),
        texts=texts,
    )
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"{len(widgets)} widgets, 10 pictures -> {os.path.relpath(OUT, ROOT)}, {os.path.relpath(PICS, ROOT)}")


if __name__ == "__main__":
    main()
