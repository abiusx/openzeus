"""Composite the original in-game city UI from data/play/ui.json + extracted sprites (check of ui.json).

    python3 tools/play_ui_composite.py OUT_DIR [WxH ...]      (default sizes: 1024x768 1600x1000)

Draws: top bar (+ wide extension), control panel (background, tabs, page/tool/lower buttons, rotate,
page content of one page, overlay buttons, info box, name bar, build buttons, minimap frame), a build
submenu, a building info window and the Options dropdown. The map area is a flat placeholder. Text uses
the Zeus_Fonts glyphs with the glyph table of the exe for ASCII only (approximate; fonts are another task).
"""
import json
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(ROOT, "extracted", "sprites")
UI = json.load(open(os.path.join(ROOT, "data", "play", "ui.json")))
_atl, _img = {}, {}


def atlas(f):
    if f not in _atl:
        a = json.load(open(os.path.join(SPR, f, "atlas.json")))
        _atl[f] = ({i["index"]: i for i in a["images"]}, {g["name"]: g for g in a["groups"]})
    return _atl[f]


def img(f, index):
    key = (f, index)
    if key not in _img:
        im = atlas(f)[0][index]
        if im.get("mirror_of"):
            src = atlas(f)[0][im["mirror_of"]]
            _img[key] = Image.open(os.path.join(SPR, f, src["png"])).convert("RGBA").transpose(Image.FLIP_LEFT_RIGHT)
        else:
            _img[key] = Image.open(os.path.join(SPR, f, im["png"])).convert("RGBA")
    return _img[key]


def first(f, group):
    return atlas(f)[1][group]["first"]


def put(canvas, ref_or_f, index_or_xy, xy=None):
    if isinstance(ref_or_f, dict):
        f, index, (x, y) = ref_or_f["file"], ref_or_f["index"], index_or_xy
    else:
        f, index, (x, y) = ref_or_f, index_or_xy, xy
    im = img(f, index)
    canvas.alpha_composite(im, (x, y)) if 0 <= x and 0 <= y and x + im.width <= canvas.width and y + im.height <= canvas.height \
        else canvas.paste(im, (x, y), im)


# --- text (approximate) -------------------------------------------------------------------------------
FONT_GROUPS = ["SPR_FONTS", "SPR_FONTS_11C", "SPR_FONTS_11C4", "SPR_FONTS_11C2", "SPR_FONTS_11C3", "SPR_FONTS_11CB"]
PUNCT = "!\"%'()*+,-./:;=?_"   # 63.. (approximation of the exe table 0x0063BE0C for ASCII punctuation)


def glyph(ch):
    if "a" <= ch <= "z":
        return ord(ch) - 96
    if "A" <= ch <= "Z":
        return ord(ch) - 64 + 26
    if "1" <= ch <= "9":
        return ord(ch) - 48 + 52
    if ch == "0":
        return 62
    if ch in PUNCT:
        return 63 + PUNCT.index(ch)
    return 0


def text_w(s, font="SPR_FONTS_11C"):
    f0, w = first("Zeus_Fonts", font), 0
    for ch in s:
        g = glyph(ch)
        w += 4 if ch == " " else (atlas("Zeus_Fonts")[0][f0 + g - 1]["width"] + 1 if g else 0)
    return w


def draw_text(c, s, x, y, font="SPR_FONTS_11C", width=None):
    if width:
        x += (width - text_w(s, font)) // 2
    f0 = first("Zeus_Fonts", font)
    for ch in s:
        g = glyph(ch)
        if ch == " ":
            x += 4
            continue
        if not g:
            continue
        im = img("Zeus_Fonts", f0 + g - 1)
        c.paste(im, (x, y - 3), im)
        x += im.width + 1


# --- frames ---------------------------------------------------------------------------------------------
def frame(c, kind, x, y, cols, rows):
    """0x0059EE90 (titled, SPR_MARBLE1) / 0x0059F2A0 (plain, SPR_MARBLE2) tile rules."""
    if kind == "titled":
        f0, tl, tr, tm, bl, br, bm, ml, mr, mm, sc, ps, pc = first("Zeus_Interface", "SPR_MARBLE1"), 0, 0xB, 1, 0x84, 0x8F, 0x85, 0xC, 0x17, 0xD, 10, 0xC, 0x78
    else:
        f0, tl, tr, tm, bl, br, bm, ml, mr, mm, sc, ps, pc = first("Zeus_Interface", "SPR_MARBLE2"), 0, 6, 1, 0x2A, 0x30, 0x2B, 7, 0xD, 8, 5, 7, 0x23
    p = 0
    for r in range(rows):
        s = 0
        for col in range(cols):
            if r == 0:
                o = tl if col == 0 else tr if col == cols - 1 else tm + s
            elif r == rows - 1:
                o = bl if col == 0 else br if col == cols - 1 else bm + s
            else:
                o = (ml + p) if col == 0 else (mr + p) if col == cols - 1 else mm + s + p
            if 0 < col < cols - 1:
                s = 0 if s + 1 >= sc else s + 1
            put(c, "Zeus_Interface", f0 + o, (x + 16 * col, y + 16 * r))
        if 0 < r < rows - 1:
            p = 0 if p + ps >= pc else p + ps


def highlight(c, x, y, w, h):
    f0 = first("Zeus_Interface", "SPR_RIMS")
    cols, rows = -(-w // 16), -(-h // 16)
    for r in range(rows):
        yy = y + 16 * r if r < rows - 1 else y + h - 16
        for col in range(cols):
            xx = x + 16 * col if col < cols - 1 else x + w - 16
            if r == 0:
                o = 0 if col == 0 else 2 if col == cols - 1 else 1
            elif r == rows - 1:
                o = 6 if col == 0 else 4 if col == cols - 1 else 5
            else:
                o = 7 if col == 0 else 3 if col == cols - 1 else None
            if o is not None:
                put(c, "Zeus_Interface", f0 + o, (xx, yy))


# --- the screen -----------------------------------------------------------------------------------------
def compose(W, H, page, submenu_tool=None, hover_row=None, info=False, dropdown=False):
    c = Image.new("RGBA", (W, H), (58, 82, 60, 255))
    d = ImageDraw.Draw(c)
    for gx in range(0, W, 60):                       # placeholder map grid
        d.line([(gx, 0), (gx, H)], fill=(70, 96, 72, 255))
    px = W - 186
    cp, tb = UI["control_panel"], UI["top_bar"]

    # top bar (0x0059EBE0) + wide extension (arm64 host rule: mirror the last 500 px)
    bar = img(tb["background"]["sprite"]["file"], tb["background"]["sprite"]["index"])
    c.paste(bar.crop((0, 0, min(bar.width, px), 30)), (0, 0))
    for x in range(bar.width, px):
        m = (x - bar.width) % 1000
        sx = bar.width - 1 - m if m < 500 else bar.width - 1000 + m
        c.paste(bar.crop((sx, 0, sx + 1, 30)), (x, 0))
    x = 10
    for t in tb["menus"]["titles"]:
        draw_text(c, t["text"], x, 6)
        x += text_w(t["text"]) + 10
    fx = 381 if W >= 1024 else 219
    put(c, tb["funds"]["icon"], (fx, 0)); draw_text(c, "25930", fx + 16, 5)
    pxx = 525 if W >= 1024 else 350
    put(c, tb["population"]["icon"], (pxx, 0)); draw_text(c, "2220", pxx + 16, 5)
    draw_text(c, "May 1340 BC", px - 110, 5)

    # panel background, filled below 768 with its texture rows (arm64 host rule)
    bg = img(cp["background"]["sprite"]["file"], cp["background"]["sprite"]["index"])
    c.paste(bg, (px, 0), bg)
    for y in range(768, H):
        row = bg.crop((0, 762 + (y * 7919) % 6, 186, 763 + (y * 7919) % 6))
        shift = (y * 104729) % 179
        inner = row.crop((7, 0, 186, 1))
        inner = Image.merge("RGBA", [Image.fromarray(__import__("numpy").roll(__import__("numpy").asarray(ch), -shift, axis=1)) for ch in inner.split()])
        c.paste(row.crop((0, 0, 7, 1)), (px, y)); c.paste(inner, (px + 7, y))

    def widget(wd, state="normal"):
        x, y, w, h = wd["rect"]
        put(c, wd["states"][state], (px + x, y))

    widget(cp["tabs"][0], "selected"); widget(cp["tabs"][1])
    for i, wd in enumerate(cp["pages"]):
        widget(wd, "selected" if i == page else "normal")
    for wd in cp["tools"]:
        widget(wd, "disabled" if wd["name"] == "undo" else "normal")
    for wd in cp["lower"]:
        widget(wd)
    r = cp["rotate"]
    put(c, r["sprite"], (px + r["rect"][0], r["rect"][1]))

    pc = UI["pages"][page]
    draw_text(c, pc["title"]["text"], px + 50, 30, width=130)
    ob = cp["overlay_buttons"]
    for k, o in enumerate(pc["overlays"]):
        x, y, w, h = ob["rects"][k]
        put(c, ob["states"]["selected" if k == 0 else "normal"], (px + x, y))
        draw_text(c, o["text"], px + x, y + 8, "SPR_FONTS_9LTBK", width=w)
    n = len(pc["overlays"])
    u = (11 - n) * 20                                # category tab 0 (or page 10): info box (0x00517480)
    hh = u + 32 - (u & 15)
    frame(c, "plain", px + 50, 300 - hh, 8, hh // 16)
    ab = cp["advisor_button"]
    put(c, ab["sprite"], (px + ab["rect"][0], ab["rect"][1]))
    frame(c, "plain", px + 50, 302, 8, 1)
    hovered = UI["pages"][page]["build_buttons"][0]
    if hovered:
        draw_text(c, hovered["text"], px + 50, 0x136, "SPR_FONTS_9DKBU", width=130)
    for s in pc["build_buttons"]:
        if s:
            x, y, w, h = s["rect"]
            put(c, s["sprite"]["file"], s["states"]["selected" if s["tool"] == submenu_tool else "normal"], (px + x, y))
    if page == 10:
        x, y, w, h = cp["minimap"]["overview_page"]
        d.rectangle([px + x, y, px + x + w - 1, y + h - 1], fill=(196, 176, 110, 255))
        d.rectangle([px + x + 30, y + 30, px + x + 70, y + 60], outline=(255, 0, 0, 255))

    # build submenu (0x0058F650)
    if submenu_tool:
        sg = UI["submenu"]
        mid = next(s["submenu"] for s in pc["build_buttons"] if s and s["tool"] == submenu_tool)
        items = UI["submenus"][str(mid)]["items"]
        C = 15
        bx, cells = px - 117 - 16 * C, C + 7
        y0 = sg["Y0_by_count"][len(items)] + 0x6E
        p0 = first("Zeus_Interface", "SPR_PANELING")
        for i, it in enumerate(items):
            y = y0 + 24 * i
            style = 1 if i == hover_row else 2
            for k in range(cells):
                put(c, "Zeus_Interface", p0 + 27 + 3 * style, (bx + 16 * k, y))
            put(c, "Zeus_Interface", p0 + 26 + 3 * style, (bx, y))
            put(c, "Zeus_Interface", p0 + 28 + 3 * style, (bx + 16 * (cells - 1), y))
            draw_text(c, it["text"], px - (16 * C + 20) - 0x59, y + 3, "SPR_FONTS_11CB" if i == hover_row else "SPR_FONTS_11C", 0xB0)
            put(c, sg["cost"]["icon"], (px - 0x52, y - 2))
            draw_text(c, "10", px - 0x42, y + 4)

    # building info window (sanctuary class: 29 x 31) placed for a mouse in the upper half
    if info:
        iw = UI["info_window"]
        rows, cols = 31, 29
        ix = 188 + (W - 1024) // 2 if False else 188
        iy = H - 8 - 16 * rows
        frame(c, "titled", ix, iy, cols, rows)
        draw_text(c, "Oracle of Apollo", ix, iy + 10, "SPR_FONTS_22C", 16 * cols)
        frame(c, "plain", ix + 16, iy + 388, cols - 2, 5)
        highlight(c, ix + 75, iy + 240, 301, 32)
        highlight(c, ix + 75, iy + 340, 301, 32)
        hb, cb = iw["help_button"], iw["close_button"]
        put(c, hb["sprite"], (ix + hb["rect"][0], iy + 16 * rows - 40))
        put(c, cb["sprite"], (ix + cb["rect"][0], iy + 16 * rows - 37))

    # Options dropdown (0x00431210): titled-frame middle tiles under the title
    if dropdown:
        t0 = 10 + text_w("File") + 10
        items = ["Display options", "Sound options", "Speed options", "Difficulty", "Autosave - ON", "Auto Defend - OFF", "Messages"]
        cells = -(-max(text_w(s) for s in items) // 16) + 2
        rows = (len(items) + 1) * 20 // 16
        f0 = first("Zeus_Interface", "SPR_MARBLE1")
        for rr in range(rows):
            for cc in range(cells):
                put(c, "Zeus_Interface", f0 + 0xD + (cc % 10) + 0xC * (rr % 10), (t0 + 16 * cc, 24 + 16 * rr))
        for i, s in enumerate(items):
            draw_text(c, s, t0 + 8, 30 + 20 * i)
    return c


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    sizes = sys.argv[2:] or ["1024x768", "1600x1000"]
    os.makedirs(out, exist_ok=True)
    for sz in sizes:
        W, H = map(int, sz.split("x"))
        compose(W, H, page=3, submenu_tool=67, hover_row=2).convert("RGB").save(os.path.join(out, f"ui_{W}x{H}_submenu.png"))
        compose(W, H, page=10, info=True, dropdown=True).convert("RGB").save(os.path.join(out, f"ui_{W}x{H}_info.png"))
        print("wrote", sz)


if __name__ == "__main__":
    main()
