"""data/play/options.json: the top-bar Options and Help menus and the option dialogs (Display 0x0A, Sound 0x0B,
Speed 0x0C, Difficulty 0x45, Messages 0x1D) for viewer/play/options.js (docs/play/options.md), and the texts of the
Messages list (0x11) and Goals (0x3B) screens for viewer/play/lists.js.

    re/venv/bin/python tools/play_options.py      (needs pefile; reads Zeus.exe and extracted/text/zeus_text.json)

texts  = the text groups the menus and dialogs draw (1..3 menus, 12/13/44/63 Messages list and Goals (lists.js), 6/8/23/98 the message window (msgwin.js), 30/31/62/287/293/333 the front end and new-game screens (newgame.js),
         20 BC/AD and 25 months (autosave, message dates), 68 balloon help (ui.js), 43 file dialogs, 42 display, 45 speed, 46 sound, 153 difficulty,
         174 message categories, 183 Off/Condensed/Full, 5 the set-aside confirm and 333 tutorial names (campaign.js,
         newgame.js))
menus  = dropdown tables 0x005EFCC0 / 0x005EFD20 / 0x005EFD90 (16 bytes: u16 y, u16 text, handler)
hits   = dialog hit tables (28 bytes: x0, y0, x1, y1 relative to the 640x480 origin)
arrows = arrow-button lists (28 bytes: x, y, packed image group, size, handler, flags, arg1), relative to the list origin"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from play_ui import rd  # noqa: E402  (Zeus.exe reader)


def menu(va, n):
    out = []
    for i in range(n):
        y, text, fn = struct.unpack("<HHI", rd(va + 16 * i, 8))
        out.append(dict(y=y, text=text, fn=hex(fn)))
    return out


def hits(va, n):
    return [list(struct.unpack("<4h", rd(va + 28 * i, 8))) for i in range(n)]


def arrows(va, n):
    out = []
    for i in range(n):
        x, y, grp, size, fn, flags, a1 = struct.unpack("<hhiiIIi", rd(va + 28 * i, 24))
        out.append(dict(x=x, y=y, group=grp - 512, size=size, fn=hex(fn), a1=a1))
    return out


def main():
    T = json.load(open(os.path.join(ROOT, "extracted/text/zeus_text.json")))
    out = dict(
        note="tools/play_options.py: menus and option dialogs of Zeus.exe (docs/play/options.md)",
        texts={g: T[g] for g in ("1", "2", "3", "5", "6", "8", "12", "13", "20", "23", "25", "30", "31", "42", "43", "44", "45", "46", "62", "63", "68", "98", "153", "174", "183", "287", "293", "333")},
        menus=dict(file=menu(0x005EFCC0, 6), options=menu(0x005EFD20, 7), help=menu(0x005EFD90, 4)),
        hits=dict(display=hits(0x005ED528, 4), sound=hits(0x005ED5D0, 8), speed=hits(0x005ED598, 2),
                  messages=hits(0x005EE628, 20)),
        arrows=dict(sound=arrows(0x005EFB50, 8), speed=arrows(0x005EFAE0, 4), difficulty=arrows(0x005EFC68, 2)),
        # speed_delay_ms 0x0063DA1C (game speed -> ms between ticks, docs/logic/time-core.md 9.5)
        # the arrow groups' first images (extracted/sprites/Zeus_Interface: SPR_BUTTON_DOWN 582.., SPR_BUTTON_UP 580..)
        arrow_images={"31": 582, "32": 580},
        speed_delay_ms=list(struct.unpack("<11i", rd(0x0063DA1C, 44))),
    )
    path = os.path.join(ROOT, "data/play/options.json")
    json.dump(out, open(path, "w"), indent=1, ensure_ascii=False)
    print(path, {k: len(v) for k, v in out["menus"].items()})


if __name__ == "__main__":
    main()
