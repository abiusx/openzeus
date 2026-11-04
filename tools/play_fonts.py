"""Font metrics of the original's text renderer for play mode (docs/play/text.md).

    python3 tools/play_fonts.py            -> data/play/fonts.json

Reads extracted/sprites/Zeus_Fonts/atlas.json (glyph sizes) and zeus-original/app/Zeus.exe (the
256-byte character -> glyph table at 0x0063BE0C). Everything else (space widths, line heights, lift
rules) is constant in the exe's code and written here with its address.
"""
import json
import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATLAS = os.path.join(ROOT, "extracted", "sprites", "Zeus_Fonts", "atlas.json")
EXE = os.path.join(ROOT, "zeus-original", "app", "Zeus.exe")
OUT = os.path.join(ROOT, "data", "play", "fonts.json")

GLYPH_TABLE_VA = 0x0063BE0C
GLYPHS = 134

# Font group order of bank 0 (the exe's group table, 0-based rank; = sg3 group id - 1).
GROUPS = ["SPR_FONTS", "SPR_FONTS_11C", "SPR_FONTS_11C4", "SPR_FONTS_11C2", "SPR_FONTS_11C3",
          "SPR_FONTS_11CB", "SPR_FONTS_22C", "SPR_FONTS_22C2", "SPR_FONTS_9B", "SPR_FONTS_11LTYEL",
          "SPR_FONTS_9LTBK", "SPR_FONTS_9LTBU", "SPR_FONTS_9LTYEL", "SPR_FONTS_9DKBU",
          "SPR_FONTS_9DKYEL", "SPR_FONTS_11LTBLUE", "SPR_FONTS_DKMESSAGE"]

# What each font looks like (seen in the glyph images; mask = sg3 type 20, one colour set by the caller).
LOOK = {
    "SPR_FONTS": "small mask font: 1-colour glyphs, colour given by the caller (555 RGB); debug overlays, bottom strip, top-left alerts",
    "SPR_FONTS_11C": "11 px dark navy, engraved look (top menu, top bar numbers, info panel bodies, build menu)",
    "SPR_FONTS_11C4": "11 px green with dark edge",
    "SPR_FONTS_11C2": "11 px pale blue/white with dark edge (help and message pages, control panel numbers)",
    "SPR_FONTS_11C3": "11 px orange",
    "SPR_FONTS_11CB": "11 px very dark navy (info panel employee lines, selected build menu row)",
    "SPR_FONTS_22C": "22 px dark navy (window titles)",
    "SPR_FONTS_22C2": "22 px pale blue",
    "SPR_FONTS_9B": "9 px very dark navy",
    "SPR_FONTS_11LTYEL": "11 px yellow",
    "SPR_FONTS_9LTBK": "9 px dark blue with light edge (control panel buttons, e.g. 'See Supplies')",
    "SPR_FONTS_9LTBU": "9 px white/pale blue",
    "SPR_FONTS_9LTYEL": "9 px yellow",
    "SPR_FONTS_9DKBU": "9 px pale with dark edge (control panel texts, tooltips)",
    "SPR_FONTS_9DKYEL": "9 px yellow-orange (control panel highlighted values)",
    "SPR_FONTS_11LTBLUE": "11 px pale blue",
    "SPR_FONTS_DKMESSAGE": "small dark font (control panel message strip)",
}

# string_draw 0x00508800: (space advance, extra px after each glyph, line height 0x00F13960)
DRAW = {0: (4, 1, 9), 6: (8, 0, 0x17), 7: (8, 0, 0x18), 16: (4, 0, 7)}
DRAW_OTHER = (6, 0, 0x0B)
# string_width 0x00507DA0 (used to centre / right-align): (space, extra)
MEASURE = {0: (4, 1), 6: (10, 1), 7: (10, 1)}
MEASURE_OTHER = (6, 0)

# text_draw_line 0x00508B50 / text_draw_panel 0x004F59B0: characters lifted by exactly 2 px (Polish
# letters of the GOG table; byte values) and the one never lifted (0xE7).
LIFT2 = [0xB9, 0xA5, 0xEA, 0xCA, 0xE6, 0xC6, 0xF1, 0xD1, 0xB3, 0xA3, 0xF3, 0xD3, 0x9F, 0x8F, 0xBF,
         0xAF, 0x9C, 0x8C]
LIFT0 = [0xE7]


def read_va(path, va, n):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    sec = pe + 24 + optsz
    rva = va - base
    for i in range(nsec):
        vsz, vaddr, rsz, rptr = struct.unpack_from("<IIII", d, sec + 40 * i + 8)
        if vaddr <= rva < vaddr + max(vsz, rsz):
            return d[rptr + rva - vaddr: rptr + rva - vaddr + n]
    raise ValueError("address not in any section")


def main():
    atlas = json.load(open(ATLAS))
    by_index = {im["index"]: im for im in atlas["images"]}
    first = {g["name"]: g["first"] for g in atlas["groups"]}
    table = list(read_va(EXE, GLYPH_TABLE_VA, 256))
    for c in range(0x20):                     # the first 32 bytes overlap a file name; every reader skips ch < 0x20
        table[c] = 0
    fonts = {}
    for rank, name in enumerate(GROUPS):
        f0 = first[name]
        ims = [by_index[f0 + k] for k in range(GLYPHS)]
        sp, extra, lh = DRAW.get(rank, DRAW_OTHER)
        msp, mextra = MEASURE.get(rank, MEASURE_OTHER)
        key = name.replace("SPR_FONTS_", "") if name != "SPR_FONTS" else "SMALL"
        fonts[key] = {
            "rank": rank, "group": name, "first": f0,
            "mask": ims[0]["type"] == 20,
            "look": LOOK[name],
            "draw": {"space": sp, "extra": extra, "line_height": lh, "paragraph_step": 5 + lh},
            "measure": {"space": msp, "extra": mextra},
            "width": [im["width"] for im in ims],
            "height": [im["height"] for im in ims],
        }
    out = {
        "version": 1,
        "note": "Text metrics of Zeus.exe (rules and addresses: docs/play/text.md). Glyph g (1..134) of a "
                "font is atlas image first+g-1 of file Zeus_Fonts. charmap[byte] = glyph (0 = none). "
                "Strings are cp1252 bytes.",
        "file": "Zeus_Fonts",
        "encoding": "cp1252",
        "charmap": table,
        "lift2": LIFT2,
        "lift0": LIFT0,
        "word_wrap": {"space": 4, "char_extra": 1, "word_break": [32, 36]},
        "panel": {"line_step": 16, "line_height": 11, "space_draw": 6, "space_measure": 4,
                  "small_extra": 2, "paragraph_indent": 50, "highlight_555": 0x7F9A},
        "fonts": fonts,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print("wrote", OUT, len(fonts), "fonts")


# --- reference renderer (same rules as viewer/play/text.js; used to check against the original) ------

class Ref:
    """Python twin of viewer/play/text.js. draw_* call put(atlas_index, x, y, colour) per glyph."""

    def __init__(self, fonts_json=OUT):
        self.d = json.load(open(fonts_json))
        self.map = self.d["charmap"]

    def _f(self, font):
        return self.d["fonts"][font]

    def glyph(self, f, b):
        return self.map[b] if b >= 0x20 else 0

    def lift(self, f, b, g, lh):
        if b in self.d["lift2"]:
            return 2
        if b < 0x80 or b in self.d["lift0"]:
            return 0
        return max(0, f["height"][g - 1] - lh)

    def measure(self, font, s):                       # string_width 0x00507DA0
        f = self._f(font)
        b = s.encode("cp1252", "replace") if isinstance(s, str) else s
        w = 0
        for c in b:
            if c == 0x20:
                w += f["measure"]["space"]
            else:
                g = self.map[c]
                if g:
                    w += f["width"][g - 1] + f["measure"]["extra"]
        return w

    def draw(self, put, font, s, x, y, colour=0):     # string_draw 0x00508800 (styles off)
        f = self._f(font)
        dr = f["draw"]
        b = s.encode("cp1252", "replace") if isinstance(s, str) else s
        x0 = x
        for c in b:
            if c < 0x20:
                continue
            g = self.glyph(f, c) if c not in (0x23, 0x5F) else 0
            if not g:
                x += dr["space"]
                continue
            put(f["first"] + g - 1, x, y - 3 - self.lift(f, c, g, dr["line_height"]), colour)
            x += f["width"][g - 1] + dr["extra"]
        return x - x0

    def draw_centered(self, put, font, s, x, y, width, colour=0):   # 0x00508670
        return self.draw(put, font, s, x + max(0, (width - self.measure(font, s)) // 2), y, colour)

    def word(self, b, i, f):                          # word_width_line 0x005091B0
        w, n, seen = 0, 0, False
        while i + n < len(b) and n < 1999:
            c = b[i + n]
            if c == 0x20:
                if seen:
                    break
                w += 4
            elif c == 0x24:
                if seen:
                    break
            elif c > 0x1F:
                g = self.map[c]
                w += (f["width"][g - 1] + 1) if g else 0
                seen = True
            n += 1
        return w, n

    def wrap(self, font, s, width):                   # paragraph_draw 0x005090A0 line breaking
        f = self._f(font)
        b = s.encode("cp1252", "replace") if isinstance(s, str) else s
        i, lines = 0, []
        while len(lines) < 99:
            w, start = 0, i
            while i < len(b):
                ww, n = self.word(b, i, f)
                if w + ww >= width:
                    break
                w += ww
                i += n
            if i == start and i < len(b):             # a word wider than the box: the exe loops on empty lines
                ww, n = self.word(b, i, f)
                i += n
            lines.append(b[start:i])
            if i >= len(b):
                break
        return lines

    def draw_paragraph(self, put, font, s, x, y, width, colour=0, centered=False):
        step = self._f(font)["draw"]["paragraph_step"]
        lines = self.wrap(font, s, width)
        for ln in lines:
            if centered:
                self.draw_centered(put, font, ln, x, y, width, colour)
            else:
                self.draw(put, font, ln, x, y, colour)
            y += step
        return len(lines) * step


if __name__ == "__main__":
    main()
