"""Build data/play/advisors.json: the advisor screens for play mode (viewer/play/advisors.js, docs/play/advisors.md).

    re/venv/bin/python tools/play_advisors.py      (needs pefile; reads zeus-original/app/Zeus.exe)

- page -> advisor table 0x0063E488 (the control panel's magnifier and, while an advisor is open, its page buttons:
  FUN_00516D50 -> advisor_screen_open_refresh 0x00408C00);
- per advisor: the frame (immediates of its draw function, dispatcher FUN_005904F0) and its title string;
- the screen's help / exit buttons: draw table 0x005EF758 (exit x = cols*16 - 36, screen_draw 0x00514020);
- the labor advisor (advisor 1): FUN_005906C0 (frame, headers), FUN_00590920 (category rows), FUN_00590C30
  (industry list), priority arrows: image table 0x006434D0 (handler 0x00590580), industry rows: hit table
  0x00643690 (handler FUN_00590660), industry resource list 0x00643470.
Fonts: the exe's font table 0x012AFBEC is indexed by rank (entry k = text.md rank k); packed font ids are 1-based.
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import play_ui as U  # noqa: E402  (exe reader, atlas groups, texts)

OUT = os.path.join(ROOT, "data", "play", "advisors.json")
FONTS = ["SMALL", "11C", "11C4", "11C2", "11C3", "11CB", "22C", "22C2", "9B", "11LTYEL", "9LTBK", "9LTBU", "9LTYEL",
         "9DKBU", "9DKYEL", "11LTBLUE", "DKMESSAGE"]          # rank order (docs/play/text.md 1)


def font(rank):
    return "SPR_FONTS_" + FONTS[rank] if rank else "SPR_FONTS"


# advisor -> (draw function, frame dx, dy from the 640x480 origin, cols, rows, title [group, index]); FUN_005904F0
ADVISORS = {
    1: ("0x005906C0", -0x3A, -10, 0x23, 0x21, [50, 0]),         # labor ("Workforce Allocation")
    2: ("0x00591C30", -0x4B, -0x1C, 0x25, 0x23, [51, 0]),       # military
    6: ("0x005BAD80", -0x50, 0, 0x25, 0x1D, [54, 0]),           # trade
    7: ("0x00593740", -0x37, 0x32, 0x23, 0x16, [55, 0]),        # population
    8: ("0x00594080", -0x50, 0x32, 0x24, 0x19, [56, 0]),        # hygiene
    9: ("0x00597720", -0x1E, 0, 0x20, 0x18, [57, 0]),           # husbandry
    10: ("0x00594B70", -0x28, 0x32, 0x20, 0x0D, [58, 0]),       # culture: 13 rows, 18 when games are scheduled (0x00902C50 != -1)
    11: ("0x00596FB0", -0x1E, 0, 0x21, 0x1B, [59, 0]),          # mythology (rows from its list; 27 used here)
    12: ("0x005951F0", -0x1E, 0, 0x21, 0x1B, [60, 0]),          # finance
    13: ("0x005B7760", -0x4B, -0x1C, 0x25, 0x23, [61, 0]),      # overview
    15: ("0x00596180", -0x1E, 0, 0x21, 0x1B, [133, 0]),         # aesthetics (Poseidon page)
}


# Positions below are from the frame's top-left (the exe draws from the 640x480 origin: frame + (-dx, -dy)).
# Text refs are [group, index]; fonts by rank (font()); "word" rows pick the index from a count or a percent.
# Hygiene (advisor 8, FUN_00594080; frame dx -80, dy 50)
HYGIENE = dict(
    evidence="exe FUN_00594080 (+ FUN_00594000 outbreak words, FUN_00594040 crime words); oracle runs/advisors/p4.bmp",
    title=dict(pos=[30, 12], font=font(6), text=[56, 0]),
    health=dict(pos=[35, 54], text_base=[56, 24], rule="24 + health/10", font=font(10), font_low=font(12), low_below=30),
    inset1=dict(pos=[35, 72], cols=32, rows=3),
    healer=dict(pos=[40, 84], font=font(13), text_base=[56, 35], rule="35 + (healer people*100/population)/10"),
    food=dict(pos=[40, 100], font=font(13), text_base=[56, 46],
              rule="fed == 0: 46; else 46 + clamp((fed*100/population)/10, 1, 10)"),
    crises=dict(pos=[45, 134], font=font(11), text=[56, 57]),
    plague=dict(pos=[45, 166], font=font(10), text_base=[56, 58], rule="0: 58, <3: 59, <6: 60, <9: 61, else 62"),
    infected=dict(pos=[45, 182], font=font(10), pre=[56, 68], post=[56, 69], post_one=[56, 70]),
    safety=dict(pos=[30, 202], font=font(6), text=[56, 71]),
    inset2=dict(pos=[40, 240], cols=32, rows=3),
    maintenance=dict(pos=[45, 252], font=font(13), text=[56, 72], text_one=[56, 73]),
    watchposts=dict(pos=[45, 268], font=font(13), text=[56, 74], text_one=[56, 75]),
    crimes=dict(pos=[50, 312], font=font(11), text=[56, 76]),
    crime_rows=[dict(key=k, pos=[50, y], text=[56, t]) for k, y, t in
                (("vandalisms", 328, 77), ("thefts", 344, 78), ("muggings", 360, 79))],
    crime_font=font(10), crime_word_base=[56, 80], crime_word_rule="0: 80 No, <3: 81, <6: 82, <9: 83, else 84",
)
# Culture (advisor 10, FUN_00594B70, non-Poseidon branch; frame dx -40, dy 50; games block not drawn: no games)
CULTURE = dict(
    evidence="exe FUN_00594B70; oracle runs/advisors/p6.bmp",
    title=dict(pos=[30, 12], font=font(6), text=[58, 0]),
    headers=[dict(pos=[35, 54], font=font(1), text=[58, 25]), dict(pos=[335, 54], font=font(1), text=[58, 26])],
    inset=dict(pos=[35, 70], cols=28, rows=6),
    rows=[dict(key="podium", cov="philosophy", text=[58, 27], text_one=[58, 28]),
          dict(key="gymnasium", cov="athletics", text=[58, 29], text_one=[58, 30]),
          dict(key="theatre", cov="drama", text=[58, 31], text_one=[58, 32]),
          dict(key="stadium", cov=None, text=[58, 33], text_one=[58, 33])],
    row_x=45, row_y=86, row_step=16, font=font(3), cov_x=335, cov_w=100,
    cov_words=[[0, 55], [1, 57], [20, 59], [40, 60], [60, 62], [80, 64], [100, 66]],
    cov_rule="coverage % (people reached / people in houses): <1 None 55, <20 57, <40 59, <60 60, <80 62, <100 64, else 66",
)
# Finance (advisor 12, finance_advisor_draw 0x005951F0; frame dx -30, dy 0); all rows font 1 (11C)
FINANCE = dict(
    evidence="exe 0x005951F0; oracle runs/advisors/p5.bmp",
    title=dict(pos=[20, 12], font=font(6), text=[60, 0]),
    font=font(1), cols=[250, 390], label_x=40, head_x=20,
    headers=[dict(pos=[230, 57], text=[60, 6]), dict(pos=[360, 57], text=[60, 7])],
    income=dict(y=72, text=[60, 10]),
    income_rows=[dict(key=k, y=y, text=[60, t]) for k, y, t in
                 (("taxes", 87, 8), ("exports", 102, 9), ("gifts", 117, 20), ("mint", 132, 24), ("tribute_in", 147, 16))],
    hippodrome=dict(key="races", y=162, text=[60, 27], rule="only when the hippodrome is allowed (0x00902D88)"),
    income_rule_y=175, income_total=dict(y=180, text=[60, 25]), shift_without_hippodrome=-15,
    expenses=dict(y=220, text=[60, 17]),
    expense_rows=[dict(key=k, y=y, text=[60, t]) for k, y, t in
                  (("imports", 235, 11), ("wages", 250, 12), ("construction", 265, 13), ("tribute_out", 280, 21),
                   ("aid", 295, 22))],
    expense_rule_y=308, expense_total=dict(y=313, text=[60, 26]),
    net=dict(y=335, text=[60, 18]), balance=dict(y=358, text=[60, 19]),
    rules=[[250, 320], [390, 460]], rule_note="FUN_00509700 colour 0: 1-px black line x0..x1",
)

# Husbandry (advisor 9, FUN_00597720; frame dx -30, dy 0); rows from 0x00F9FA58 (ours: live.food_supply)
HUSBANDRY = dict(
    evidence="exe FUN_00597720 (estimate FUN_00518FF0, imports FUN_00518E40); oracle runs/advisors/p1.bmp",
    title=dict(pos=[30, 12], font=font(6), text=[57, 0]),
    head=dict(pos=[50, 45], font=font(1), text=[57, 29]),
    head_loads=dict(pos=[200, 45], width=150, font=font(1), text=[57, 30], rule="paragraph_draw_centered 0x005086E0"),
    head_people=dict(pos=[350, 45], width=150, font=font(1), text=[57, 31]),
    font=font(1), row_y=100, row_step=16, count_x=15, name_x=60, loads_x=200, people_x=350, col_w=140,
    imported=[57, 41], total=[57, 42], none=dict(pos=[50, 100], width=140, text=[57, 44]),
    rule="rows: resources 1..8 with a working producer (count, loads/100, people), corrals (57:40) after 3; then "
         "imports '57:41 ' + 23:res; total at row_y + (rows+1)*16: loads = sum(loads*100)/100",
)
# Mythology (advisor 11, FUN_00596FB0; frame dx -30, dy 0, rows from the lists: FUN_00595F20 counts)
MYTHOLOGY = dict(
    evidence="exe FUN_00596FB0, FUN_00595F20, FUN_004F0130 (state texts), FUN_004F00A0 (god mood); oracle p7.bmp",
    title=dict(pos=[30, 12], font=font(6), text=[59, 0]),
    worship=dict(pos=[35, 0x2C], font=font(1), text=[59, 18]),
    inset=dict(pos=[35, 0x42], cols=29), row_y=0x47, row_step=0x14, god_x=40, god_font=font(3), state_x=0xBE,
    others=[59, 41], unfriendly=[59, 50], label_x=40, label_font=font(1), name_font=font(15),
    state_fonts={"4": font(4), "5": font(5)}, pct_format="%s %d %% %s (59:31, percent, 59:32)",
    height_rule="h = 0x52 or 20n+99; + (others+1)*16; + (unfriendly+1)*16; + 10 if unfriendly or heroes; rows = h/16 + 2",
)
# Population (advisor 7, FUN_00593740; frame dx -55, dy 50): history FUN_00593A80 / society FUN_00593D20
POPULATION = dict(
    evidence="exe FUN_00593740, FUN_00593A80, FUN_00593D20, FUN_00593EE0 (scale), FUN_00567710/FUN_00567750, "
             "button FUN_00593A30 (rims) + hit table 0x005EE5A8 (wm_sub_408d70 toggles 0x00665E30); oracle p0.bmp",
    inset=dict(pos=[0x31, 0x3B], cols=27, rows=13),
    title=dict(pos=[0x1E, 12], font=font(6), text=[[55, 0], [55, 1]]),
    caption=dict(pos=[0x3C, 0x118], width=400, font=font(1), text=[[55, 4], [55, 5]]),
    button=dict(pos=[0x31, 0x136], width=0x1B0, font=font(1), text=[[55, 3], [55, 2]], rims=[0x31, 0x130, 0x1B0, 0x14],
                hit=[0x31, 0x136, 0x1E1, 0x14A]),
    graph=[0x40, 0x40], scale_x=-0x42, scale_w=60, scale_y=[-3, 0x60, 0xC4], label_font=font(0),
    month_x=[-0x14, 0x17C], label_y=0xD2, bar_bottom=200, fill=[248, 0, 0], fill_note="0xF800 (RGB565 red) then a black outline",
    society_labels=[dict(x=-0x50, width=200, text=[55, 6]), dict(x=0x118, width=200, text=[55, 7])],
)
# Aesthetics (advisor 15, FUN_00596180; frame dx -30, dy 0)
AESTHETICS = dict(
    evidence="exe FUN_00596180, FUN_0051BD00/FUN_0051BDD0 (lines), wm_sub_4663b0 (type names); oracle p9.bmp",
    title=dict(pos=[32, 12], font=font(6), text=[133, 0]), sub=dict(pos=[32, 0x2A], font=font(15), text=[133, 0]),
    inset=dict(pos=[32, 0x3E], cols=29, rows=14),
    comm=dict(pos=[0x20, 27 * 16 - 0x88], font=font(1), text=[133, 1]), none=dict(font=font(14), text=[133, 2]),
    line_x=0x2A, line_dy=0xE, line_step=12, per_col=8, col_step=0x8C, line_font=font(11),
    one=[133, 3], many=[133, 4],
    type_text={"1": 5, "2": 7, "3": 10, "5": 8, "6": 11, "7": 6, "8": 9, "9": 12, "4": 13},
    order=[1, 2, 3, 5, 6, 7, 8, 9, 4], order_note="types 0..8 except 4, 9 (none for 0); god types (none here); 9; 4",
)
# Trade (advisor 6, FUN_005BAD80 frame + FUN_005BAEF0 rows; frame dx -80, dy 0)
TRADE = dict(
    evidence="exe FUN_005BAD80, FUN_005BAEF0, rebuild_goods_lists 0x005BAAF0, hit tables 0x0065BAD0 / 0x0065BCB0 "
             "(handlers 0x005BA720 go to the post, 0x005BA7D0 more); oracle p3.bmp",
    title=dict(pos=[10, 12], font=font(6), text=[54, 0]), prices=dict(pos=[0x73, 0x27], width=100, font=font(15), text=[54, 9]),
    inset=dict(pos=[16, 0x34], cols=35, rows=23), row_y=0x39, row_step=22, max_rows=17, icon_x=0x16, text_dy=4,
    name_x=0x2C, price_x=0x73, price_w=100, state_x=0xCC, city_x=0x154, more_x=0x1C2, more_text_x=0x1C6,
    font=font(3), city_font=font(5), city_hover=font(3), city_off=font(4), city_rect=[0, 0, 0x6E, 0x16],
    more=[54, 10], state_text={"5": 1, "7": 2}, avail={"both": 5, "sells": 3, "buys": 4},
)
# Overview (advisor 13, FUN_005B7760; frame dx -75, dy -28)
OVERVIEW = dict(
    evidence="exe FUN_005B7760 + status fns popularity_advisor_text 0x005B5AF0, 0x005B5FA0, 0x005B6260, 0x005B5E10, "
             "0x005B6350, 0x005B65C0, 0x005B6690 (unrest 0x00FEB544 from 0x00519880), 0x005B6730, 0x005B6830, "
             "0x005B69D0, 0x005B6AE0; oracle p10.bmp",
    title=dict(pos=[0x20, 12], font=font(6), text=[61, 0]), inset=dict(pos=[0x20, 0x28], cols=33, rows=16),
    bullet_x=0x28, label_x=0x37, status_x=0xBD, label_font=font(3), para_w=37 * 16 - 0xC6,
    rows=[dict(key=k, y=y, label=l) for k, y, l in (("popularity", 0x38, 1), ("migration", 0x5C, 2),
          ("food_production", 0x80, 3), ("food_level", 0x92, 4), ("employment", 0xA4, 5), ("hygiene", 0xB6, 6),
          ("unrest", 0xC8, 7), ("finances", 0xDA, 8), ("culture", 0xEC, 9), ("mythology", 0xFE, 11),
          ("security", 0x110, 12))],
    second_y=0x4A, requests=dict(pos=[0x23, 299], font=font(6), text=[61, 195]),
    hint=dict(y=0x136, font=font(1), text=[61, 207]), req_frame=dict(pos=[0x23, 0x14B], cols=33, rows=12),
    req=dict(icon_y=0x155, text_y=0x159, step=0x17, max=8, goods_dx=0x16, amount_dx=0x30, good_dx=0x4E, city_dx=0xA8,
             class_dx=0xFD, stock_dx=0x148, due_dx=0x1C0, more=dict(width=0x82, text=[61, 196]),
             # a quest row (FUN_005B7760, event type 4): bullet entry 12 + font 3 when its hero is in the city and
             # free (FUN_005BDDD0), else entry 18 + font 5; the god's icon (packed group 0x807 + god) at +0x1A, the
             # hero (185:hero) at +0x4C, the quest title (FUN_004836B0) at +0xA6, the god's name (157:god) at +0x1A7
             quest=dict(god_dx=0x1A, hero_dx=0x4C, title_dx=0xA6, godname_dx=0x1A7, fonts=["3", "5"])),
    fonts={"3": font(3), "4": font(4), "5": font(5), "8": font(8), "13": font(13), "14": font(14)},
)
# Military (advisor 2, FUN_00591C30; frame dx -75, dy -28): frame-relative = origin-relative + (75, 28)
MILITARY = dict(
    evidence="exe FUN_00591C30 (+ FUN_00591610 status, FUN_0051ABE0 type icon, FUN_005917A0 thin button, "
             "FUN_00591680 crew); oracle p8.bmp",
    army=dict(pos=[20, 12], width=280, font=font(1), text=[51, 13]),
    col_x=20, col_cols=17, first_y=28, head_dx=5, troops_x=194, head_font=font(13), row_dy=0x11, row_step=16,
    sections=[dict(type="horseman", text=[51, 14]), dict(type="hoplite", text=[51, 15]), dict(type="rabble", text=[51, 16])],
    troops=[51, 17], flag_dx=5, icon_x=53, name_dx=0x36, name_font=font(8), status_font=font(10), status_plain=font(8),
    gap=0x20, right_x=300, navy=dict(text=[51, 32], y=12, inset_y=0x1C, rows=7, row_y=0x21),
    other=dict(text=[51, 54], y=0x91, inset_y=0xA1, rows=12, head_y=0xA6, row_y=0xB2, text_merc=[51, 67]),
    myth=dict(inset_dy=0xC0, rows=6, head_dy=0xC5, row_dy=0xD1, text=[51, 68]), none=[58, 55], none_font=font(8),
    lines=dict(bullet_x=0x29, y=[0x1E6, 0x1FA, 0x20E], text_x=0x3D, count_x=0x35, in_dx=0x3D, comp_dx=0x33,
               tri_dx=0xBF, font=font(1)),
)


def table28(va, n):
    """28-byte image/hit table entries: x, y (or l, t, r, b) shorts, then ints."""
    out = []
    for i in range(n):
        e = U.rd(va + 28 * i, 28)
        out.append(struct.unpack("<hhhhiiiii", e))
    return out


def main():
    res = {r["zeus_id"]: r["key"] for r in json.load(open(os.path.join(ROOT, "data", "resources.json")))}
    page_adv = [U.i32(0x0063E488 + 4 * i) for i in range(11)]
    advisors = {}
    for a, (fn, dx, dy, cols, rows, title) in ADVISORS.items():
        advisors[str(a)] = dict(draw=fn, frame=[dx, dy, cols, rows], title=title, title_text=U.text(*title),
                                implemented=True)
    # help / exit buttons (draw table 0x005EF758: the exit's x is patched to cols*16-36 each frame)
    btn = []
    for name, e in zip(("help", "exit"), U.drawtab(0x005EF758, 2)):
        raw = U.rd(0x005EF758 + 40 * ("help", "exit").index(name), 40)
        w = U.widget(e, name, 0, 0)
        w["handler"] = f"0x{int.from_bytes(raw[16:20], 'little'):08X}"
        btn.append(w)
    btn[1]["x_rule"] = "cols*16 - 36"
    btn[0]["y_rule"] = btn[1]["y_rule"] = "(rows-2)*16 + rect.y"
    # labor: priority arrows (image table 0x006434D0, 16 = 8 rows x down/up), handler 0x00590580: arg 0 = up
    # (priority + 1, max 5), 1 = down (- 1, min 0), then labor_allocate 0x00487750 + labor_assign_buildings 0x00487BA0
    arrows = []
    for i in range(16):
        x, y, packed, _, handler, _, arg, row = struct.unpack("<hhiiiiii", U.rd(0x006434D0 + 28 * i, 28))
        ref = U.group(packed)
        arrows.append(dict(rect=[x, y] + U.size(ref), sprite=ref, pressed=dict(file=ref["file"], index=ref["index"] + 1),
                           dir="up" if arg == 0 else "down", row=row, handler=f"0x{handler:08X}"))
    ind_rects = [list(e[:4]) for e in table28(0x00643690, 20)]
    ind_list = [U.i32(0x00643470 + 4 * i) for i in range(24)]
    industries = []
    for i, r in enumerate(ind_list):
        industries.append(dict(res=r, key=res.get(r, {24: "meat_beef"}.get(r)), name=U.text(50, 33 + i)))
    icons = {}
    for r in sorted(set(ind_list) | set(range(1, 23))):   # FUN_00590C30 / FUN_005BAEF0 switch + FUN_0040FD80 offsets
        special = {8: 0x6828, 16: 0x682A, 17: 0x6829, 22: 0x682B, 23: 0x804, 27: 0x806}
        if r in special:
            ref = U.group(special[r])
        elif r == 24:
            ref = U.group(0x87B, 3)
        else:
            off = r if r <= 7 else r - 1 if r <= 15 else {18: 15, 19: 16, 20: 17, 21: 18}[r]
            ref = U.group(0x87B, off)
        icons[str(r)] = ref
    labor = dict(
        evidence="exe FUN_005906C0, FUN_00590920, FUN_00590C30; oracle re/oracle/runs/labor-advisor (a.bmp at 1024x768)",
        title=dict(pos=[0xF, 0xC], font=font(6), text=[50, 0]),
        headers=[dict(text=[50, i], pos=p, font=font(10)) for i, p in ((18, [0x46, 0x2E]), (19, [0xAC, 0x2E]),
                                                                        (10, [0x178, 0x2E]), (11, [0x1AA, 0x2E]))],
        rows_inset=dict(pos=[0x19, 0x3C], cols=0x1C, rows=0xB),
        arrows_origin=[0x28, 0x44], arrows=arrows,
        row_step=0x14,
        priority=dict(x=0x4E, y=0x4A, text_base=[50, 24],
                      font_rule="0 -> 9B, 1..3 -> 9DKBU, 4..5 -> 9DKYEL",
                      fonts={"0": font(8), "1": font(13), "2": font(13), "3": font(13), "4": font(14), "5": font(14)}),
        name=dict(x=0xA0, y=0x46, font=font(3), text_base=[50, 1],
                  poseidon_culture=dict(text=[50, 9], note="row 5 reads 'Science' in a Poseidon game (y = 0xAA, font 3)")),
        need=dict(x=0x174, y=0x46, font=font(3)),
        have=dict(x=0x1A6, y=0x46, font=font(3), font_short=font(4), rule="have != need -> 11C3 (orange)"),
        industry_title=dict(pos=[0xF, 0xF4], font=font(6), text=[50, 22]),
        industry_hint=dict(pos=[0xF, 0x10E], font=font(10), text=[50, 23]),
        industry_inset=dict(pos=[0x19, 0x11A], cols=0x20, rows=0xD),
        industry_origin=[0x1C, 0x11C], industry_rects=ind_rects, industry_max=20,
        industry_row=dict(icon_dy=5, text_dx=0x1A, text_dy=8, status_dx=0x73, name_font=font(13),
                          status=dict(on=[50, 30], off=[50, 31], on_font=font(13), off_font=font(14))),
        industry_none=dict(text=[50, 32], pos=[0x1C, 0x126], center=0x200, font=font(14)),
        industries=industries, icons=icons,
        industry_shown="a resource is listed while the city has a producer of it (0x0091EB58[res] > 0, "
                       "buildings_count_by_type 0x00491820); fish/urchin/grapes...: same rule (FUN_005905D0)",
    )
    texts = {"50": U.TXT["50"], "88": U.TXT["88"][:11], "56": U.TXT["56"], "58": U.TXT["58"], "60": U.TXT["60"]}
    for g in (8, 20, 23, 25, 51, 54, 55, 57, 59, 61, 133, 138, 157):
        texts[str(g)] = U.TXT[str(g)]
    # military row tables (28-byte hit entries in pairs: name rect, status button rect), FUN_00591C30
    mil_tabs = {k: [list(e[:4]) for e in table28(va - 0x1C, 2 * 20)] for k, va in
                (("horseman", 0x006438DC), ("hoplite", 0x00643D3C), ("rabble", 0x0064419C), ("merc", 0x0064474C), ("myth", 0x0064497C))}
    mil_tabs["navy"] = [list(e[:4]) for e in table28(0x006445E0, 2 * 10)]
    MILITARY["tables"] = mil_tabs
    MILITARY["tables_note"] = "pairs [name rect, status rect] per row (navy: [hull text rect, crew button rect])"
    sprites = dict(bullet=U.group(512 + 153), flags=U.group(512 + 27), types=U.group(512 + 23),
                   thin_button=U.group(512 + 25), request_open=U.group(512 + 19), request_done=U.group(512 + 13),
                   god_icons=U.group(0x807),
                   rims=U.group(512 + 124))
    sprites_note = ("bullet: interface entry 152 (0x4C0/8); flags 26 + banner; type icons 0x217 (+0 horse, 1 hoplite, 2 "
                    "rabble; mercenaries 0/5/4; +3 trireme); thin button 24 (+0 left, +4 middle, +8 right, +1 hover; 13 px "
                    "a piece); requests 18 / 12; rims 123 (window_highlight_draw)")
    for a in ADVISORS.values():
        g, i = a[5]
        texts.setdefault(str(g), {})
        if isinstance(texts[str(g)], dict):
            texts[str(g)][str(i)] = U.text(g, i)
    out = dict(version=1, note="advisor screens (docs/play/advisors.md); tools/play_advisors.py",
               hygiene=HYGIENE, culture=CULTURE, finance=FINANCE, husbandry=HUSBANDRY, mythology=MYTHOLOGY,
               population=POPULATION, aesthetics=AESTHETICS, trade=TRADE, overview=OVERVIEW, military=MILITARY,
               sprites=sprites, sprites_note=sprites_note,
               origin="frame position = ((W-640)/2 + dx, (H-480)/2 + dy) (0x00F2A6AC/A8, set in app_init 0x0050B980 and FUN_0050BD20)",
               page_advisor=page_adv, page_advisor_evidence="exe 0x0063E488 (index = control-panel page)",
               advisors=advisors, buttons=btn, labor=labor, texts=texts)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=1)
    print(f"{len(advisors)} advisors, page map {page_adv} -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
