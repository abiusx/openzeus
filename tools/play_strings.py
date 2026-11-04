"""Strings the play-mode UI needs, as (group, index) references into the original's text file
(docs/play/text.md section "Strings").

    python3 tools/play_strings.py          -> data/play/strings_ui.json

Reads extracted/text/zeus_text.json (tools/engtext.py of Zeus_Text.eng; group numbers are the exe's)
and data/buildings.json (zeus_id = the exe's building type). Each reference is [group, index] and the
resolved English text is written next to it ("text") so the UI can use either. The per-type info
panel table below was read from the exe's dispatcher 0x005720E0 (building info window, kind 2) and the
panel functions it calls (title = string drawn in font 22C at the window top).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT = os.path.join(ROOT, "extracted", "text", "zeus_text.json")
BUILDINGS = os.path.join(ROOT, "data", "buildings.json")
OUT = os.path.join(ROOT, "data", "play", "strings_ui.json")

# exe building type -> (panel function, text group of the panel; None = composed elsewhere).
# Title: [group, 0] unless TITLE says otherwise. Read from 0x005720E0's switch + each panel function.
PANELS = {}
def _p(types, fn, group):
    for t in types:
        PANELS[t] = (fn, group)
_p(range(2, 15), "0x0057F4E0", 127)                                    # housing (title 29:type-2)
_p(list(range(15, 26)) + [0x7F, 0x94, 0x95, 0x96, 0x97, 0x98], "0x00577A10", 137)   # decorations, bench...
_p([0x1F], "0x00584520", 112); _p([0x20], "0x00584520", 113); _p([0x21], "0x00584520", 114)
_p([0x23], "0x00584520", 116); _p([0x24], "0x00584520", 115); _p([0xD9], "0x00584520", 107)
_p([0x25], "0x0057DB80", 179); _p([0xD6], "0x0057E2B0", 179)
for t, g in {0x29: 123, 0x2A: 121, 0x30: 119, 0x31: 118, 0x32: 117, 0x33: 120, 0x35: 122, 0x36: 125,
             0x37: 126, 0x85: 89, 0x87: 124, 0xD3: 109, 0xD4: 281, 0xD5: 169}.items():
    _p([t], "0x00582920", g)                                            # industry (switch in 0x00582920)
_p([0x2C], "0x0057B220", 102); _p([0x2D], "0x0057B760", 159); _p([0x2E], "0x0057EEA0", 154)
_p([0x38], "0x0057EA60", 171)
_p([0x39, 0x3A, 0x3D, 0x3E], "0x005B2880", None)                       # granary/storehouse/pier/trading post
_p([0x3F, 0x40], "0x0057AA10", 97)
_p([0x4A, 0x4B], "0x0057D750", 108)
for t, fn in {0x4C: "0x00577D20", 0x4D: "0x00578150", 0x4E: "0x00578580", 0x4F: "0x005789B0",
              0x50: "0x005792A0", 0x51: "0x00579800", 0x52: "0x00578DE0"}.items():
    _p([t], fn, t)                                                      # infirmary..theater: group = type
_p(range(0x54, 0x63), "0x005813F0", 132)                               # sanctuaries (+178 for construction)
_p(range(0x64, 0x73), "0x00580430", 132)                               # pyramids / monuments
_p([0x73], "0x0057D8D0", 110); _p([0x75], "0x0057BB50", 103); _p([0x76], "0x00577870", 135)
_p([0x77], "0x00577C50", 90); _p([0x79], "0x0057BE20", 104); _p([0x7A], "0x0057D1E0", 106)
_p([0x7B], "0x0057A2F0", 155); _p([0x7C], "0x00579CC0", 164); _p([0x7D], "0x0057C720", 99)
_p([0x7E], "0x00577790", 136); _p([0x81, 0x91, 0x92], "0x00577950", 134)
_p([0x83], "0x0057A200", 168); _p([0x84], "0x0057A3E0", 170); _p([0x88], "0x00583C60", 175)
_p([0xA9], "0x0057DA10", 140); _p([0xC7], "0x0056E960", 167)
_p([0xCA], "0x00585400", 336); _p([0xCC], "0x00585400", 334); _p([0xCE], "0x00585400", 335)
_p([0xCB], "0x00584EF0", 337); _p([0xCD], "0x00584EF0", 338); _p([0xCF], "0x00584EF0", 339)
_p([0xD8], "0x00585880", 141)
TITLE = {t: [29, t - 2] for t in range(2, 15)}                         # house level names, lowercase
TITLE.update({t: [28, t] for t in list(range(0x39, 0x3F)) + list(range(0x54, 0x73)) + [0x75]})
DECOR = {t: k + 1 for k, t in enumerate(list(range(15, 26)) + [0x94, 0x95, 0x96, 0x97, 0x98])}   # 0x00577A10
DECOR[0x7F] = 0                                                         # bench (default case)
TITLE.update({t: [137, 2 * k] for t, k in DECOR.items()})              # description = [137, 2k + 1]


def main():
    t = json.load(open(TEXT))
    txt = lambda g, i: t.get(str(g), [None] * (i + 1))[i] if i < len(t.get(str(g), [])) else None
    ref = lambda g, i: {"ref": [g, i], "text": txt(g, i)}
    grp = lambda g, a=0, b=None: [ref(g, i) for i in range(a, len(t[str(g)]) if b is None else b)]

    buildings = {}
    for key, b in json.load(open(BUILDINGS)).items():
        zid = b.get("zeus_id")
        if zid is None:
            continue
        fn, g = PANELS.get(zid, (None, None))
        e = {"zeus_id": zid, "name": ref(28, zid), "panel_fn": fn}
        e["title"] = {"ref": TITLE[zid], "text": txt(*TITLE[zid])} if zid in TITLE else (ref(g, 0) if g else ref(28, zid))
        if zid in DECOR:
            e["description"] = ref(137, 2 * DECOR[zid] + 1)
        elif g:
            e["text_group"] = g
            e["texts"] = [s for s in t[str(g)]]
        buildings[key] = e

    out = {
        "version": 1,
        "note": "UI strings of the original as [group, index] into extracted/text/zeus_text.json (exe group "
                "numbers; index 0-based); 'text' is the English string. Fonts and positions: docs/play/text.md.",
        "top_menu": {"file": grp(1), "options": grp(2), "help": grp(3), "reports": grp(4)},
        "top_bar": {"months": grp(25), "months_long": grp(160), "bc": ref(20, 0), "ad": ref(20, 1),
                    "drachmas": ref(8, 0), "drachma": ref(8, 1)},
        "control_panel": {"page_titles": grp(88), "page_buttons": grp(14),
                          "message_strip_examples": grp(12)},
        "tooltips": {"note": "mouse help (balloon help); index per widget is a hypothesis from the text order",
                     "strings": grp(68, 0, 60)},
        "build_menu": {"item_name": "28:<zeus_id> (data/buildings.json zeus_id); cost from the model",
                       "category_tooltips": grp(68, 20, 32)},
        "dialogs": {"quit": ref(5, 0), "exit_game": ref(5, 1), "no": ref(18, 0), "yes": ref(18, 1),
                    "cancel": ref(18, 2), "ok": ref(18, 3), "click_to_continue": ref(13, 0),
                    "right_click_to_continue": ref(13, 1), "paused": ref(13, 2)},
        "info_common": {"units": grp(8), "workers": grp(69),
                        "employee_line": "<n> 8:12|8:13 (<needed> 69:0 — see docs/play/text.md)"},
        "walkers": {"names": grp(64), "note": "walker info: names 64:<figure name index>, locality texts group 70"},
        "reports": {"workforce": ref(50, 0), "military": ref(51, 0), "trade": ref(54, 0),
                    "population": ref(55, 0), "hygiene": ref(56, 0), "husbandry": ref(57, 0),
                    "culture": ref(58, 0), "mythology": ref(59, 0), "finance": ref(60, 0),
                    "overview": ref(61, 0), "messages": ref(63, 0)},
        "buildings": buildings,
    }
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("wrote", OUT, len(buildings), "buildings")


if __name__ == "__main__":
    main()
