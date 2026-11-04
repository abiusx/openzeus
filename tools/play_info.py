"""Building info windows of the original (right click on a building) -> data/play/info_panels.json.

Usage: python3 tools/play_info.py
Inputs: data/play/strings_ui.json (per key: zeus_id, panel_fn, text_group), data/buildings.json,
data/resources.json, extracted/text/zeus_text.json, extracted/sprites/*/atlas.json.
The layouts below were read in the decompile (re/decomp/zeus.c; `python3 tools/fn.py ADDR`); every
number carries the address it comes from. Positions are relative to the window's top-left (L, T);
"H" = window height in 16-px cells, "C" = width in cells. Doc: docs/play/info.md.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p)))

# --- window height by type: info_window_class 0x00571EE0 + info_window_open 0x005715A0 ---------------
CLASS_ROWS = {1: 16, 2: 18, 3: 19, 4: 14, 5: 24, 6: 31}
CLASS1 = {0x2c, 0x2d, 0x38, 0x3c, 0x4b, 0x4c, 0x4d, 0x73, 0x7a, 0x7c, 0x7f, 0x83, 0x84, 0xa9, 0xcc}
CLASS2 = {0x50, 0x51, 0x79, 0xcb, 0xcf}
CLASS3 = {0x52, 0xcd}
CROPS = {0x1f, 0x20, 0x21, 0x23, 0x24, 0xd9}          # type_is_crop 0x004A9590


def rows_of(t):
    if t in (0x3f, 0x40):                             # agoras (building_type_agora): class 5
        return 24
    if t == 0x75:                                     # palace: info_window_open override
        return 12
    if 0x54 <= t <= 0x62 or 100 <= t < 0x73:          # composite (sanctuaries) / pyramids: class 6
        return 31
    if t in CROPS:
        return 24
    if t in CLASS1: return 16
    if t == 0x4a: return 14
    if t in CLASS2: return 18
    if t in CLASS3: return 19
    return 22


# --- staffing ladders: which string of the panel's group for each state -------------------------------
# keys: fire, none (no workers), s100, s75, s50, s25, s0 (>=100 / 75-99 / 50-74 / 25-49 / <25 %),
# curse, bless, halted, out (own walker out), idle (walker at home). A value [g, i] uses group g.
STD = dict(fire=8, none=7, s100=2, s75=3, s50=4, s25=5, s0=6, curse=9, bless=10)   # 0x00577D20 (Infirmary), 0x00578150
IND = dict(fire=[69, 6], none=5, s100=6, s75=7, s50=8, s25=9, s0=10, curse=[69, 10], bless=[69, 12], halted=4)  # 0x00582920, 0x00584520
GEN = dict(fire=[69, 6], none=[69, 9], s100=[69, 15], s75=[69, 14], s50=[69, 13], s25=[69, 13], s0=[69, 13],
           curse=[69, 10], bless=[69, 12])                                       # 0x005B2420 (storage), fallback
WALK = dict(fire=10, none=9, s100=4, s75=5, s50=6, s25=7, s0=8, curse=11, bless=12, out=2, idle=3)   # 104 / 164 string order (hyp)

# --- panels: sim key -> panel kind + group + layout -----------------------------------------------------
# Layout fields (all exe unless marked): status_y (paragraph at L+32, width (C-4)*16, font 11C),
# inset [y, rows] (plain frame at L+16, C-2 cells), workers_y (0x00577290 at that y0), desc_y
# (description g:1 at T + H*16 + desc_y; null = not drawn).
SERVICE = dict(panel="service", status_y=0x38, inset=[0x88, 4], workers_y=0x8e, desc_y=None, ladder=STD)
PANELS = {
    "wall": dict(panel="wall", fn="0x005776A0", evidence="exe: a wall tile opens the land window kind 0x18 -> title 166:0, text 166:1 at H*16-0x9E"),
    "house": dict(panel="house", fn="0x0057F4E0"),
    "elite_house": dict(panel="house", fn="0x0057F4E0"),
    "granary": dict(panel="storage", fn="0x005B2880 + 0x005B38C0"),
    "storehouse": dict(panel="storage", fn="0x005B2880 + 0x005B38C0"),
    "endless_warehouse": dict(panel="storage", fn="(ours: storehouse layout)", title="Endless warehouse"),
    "agora": dict(panel="agora", fn="0x0057AA10 + 0x0040B5F0"),
    "grand_agora": dict(panel="agora", fn="0x0057AA10 + 0x0040B5F0"),
    # farms and orchard trees 0x00584520: crop icon, "Production is n% complete.", status, workers, description
    **{k: dict(panel="farm", fn="0x00584520", status_y=0x46, inset=[0x88, 4], workers_y=0x8e, desc_y=-0x71,
               ladder=IND) for k in ("wheat_farm", "onion_farm", "carrot_farm", "grapevine", "olive_tree", "fruit_tree")},
    # industry 0x00582920: output icon, "Holds n raw" / "Production is n% complete.", input stock, status
    **{k: dict(panel="industry", fn="0x00582920", status_y=0x4b, status_y_input=0x56, inset=[0x88, 4],
               workers_y=0x8e, desc_y=-0x71, ladder=IND)
       for k in ("sheep_farm", "goat_farm", "mint", "marble_quarry", "foundry", "timber_mill", "winery", "oil_press",
                 "sculpture_studio", "armory", "horse_ranch", "orichalc_refinery", "chariot_workshop", "black_marble_shop")},
    "infirmary": dict(SERVICE, fn="0x00577D20"),
    "college": dict(SERVICE, fn="0x00578150"),
    "drama_school": dict(SERVICE, fn="0x00578580"),
    "gymnasium": dict(SERVICE, fn="0x005789B0"),
    "bibliotheke": dict(SERVICE, fn="0x00585400", evidence="positions exe; ladder hyp"),
    "university": dict(SERVICE, fn="0x00585400", evidence="positions exe; ladder hyp"),
    "inventors_workshop": dict(SERVICE, fn="0x00585400", evidence="positions exe; ladder hyp"),
    # venues 0x005792A0 / 0x00579800 / 0x00578DE0: status, 6-row inset, workers at +0x8a, show line at +0xb6
    **{k: dict(panel="venue", fn=f, status_y=0x38, inset=[0x88, 6], workers_y=0x8a, show_y=0xb6, desc_y=None,
               ladder=dict(fire=12, none=4, s100=3, curse=13, bless=14, idle=2))
       for k, f in (("stadium", "0x005792A0"), ("podium", "0x00579800"), ("theatre", "0x00578DE0"))},
    **{k: dict(panel="venue", fn="0x00584EF0", status_y=0x38, inset=[0x88, 6], workers_y=0x8a, show_y=None,
               desc_y=None, ladder=dict(none=7, s100=2), evidence="hyp")
       for k in ("observatory", "laboratory", "museum")},
    "fountain": dict(panel="fountain", fn="0x0057D750", status_y=-0xb7, inset=[0x68, 4], workers_y=0x6e),
    "maintenance": dict(panel="walker", fn="0x0057BE20", status_y=0x38, status2_y=0x68, inset=[0xa8, 4], workers_y=0xae,
                        desc_y=None, ladder=WALK),
    "guardpost": dict(panel="walker", fn="0x00579CC0", status_y=0x38, status2_y=0x48, inset=[0x88, 4], workers_y=0x8e,
                      desc_y=-0x71, ladder=WALK),
    "tax_office": dict(panel="service", fn="0x0057D1E0", status_y=0x48, inset=[0x88, 4], workers_y=0x8e, desc_y=None,
                       ladder=dict(fire=13, none=10, s100=5, s75=6, s50=7, s25=8, s0=9, curse=14, bless=15),
                       evidence="positions exe, full staff seen; the tax-rate line at +0x2b (60:1 + rate) not drawn; ladder from the string order (hyp)"),
    "growers_lodge": dict(panel="lodge", fn="0x0057DB80", stored=[[0x24, 13, 11], [0x38, 12, 12]], status_y=0x4c, out_y=0x8f,
                          inset=[0xb8, 4], workers_y=0xba, desc_y=-0x4b,
                          ladder=dict(fire=13, none=3, s100=4, s75=5, s50=6, s25=7, s0=8, curse=14, bless=15, halted=2, out=9)),
    "fruit_lodge": dict(panel="lodge", fn="0x0057E2B0", title_index=17, desc_index=18, stored=[[0x24, 8, 28]],
                        status_y=0x4c, out_y=0x8f, inset=[0xb8, 4], workers_y=0xba, desc_y=-0x4b,
                        ladder=dict(fire=29, none=20, s100=21, s75=22, s50=23, s25=24, s0=25, curse=30, bless=31, halted=19, out=26)),
    "hunting_lodge": dict(panel="gatherer", fn="0x0057EEA0", stored=[0x3c, 13, 0x3c], status_y=0x56, inset=[0x88, 4],
                          workers_y=0x8e, desc_y=None,
                          ladder=dict(fire=14, none=5, s100=6, s75=7, s50=8, s25=9, s0=10, curse=15, bless=16, halted=4, out=11)),
    "corral": dict(panel="gatherer", fn="0x00585880", stored=[0x3c, 11, 0x20], progress=[0x2c, 12, 13], status_y=0x4c,
                   inset=[0x88, 4], workers_y=0x8e, desc_y=-0x71,
                   ladder=dict(fire=8, none=7, s100=2, s75=3, s50=4, s25=5, s0=6, curse=9, bless=10, halted=14)),
    "fishing_wharf": dict(panel="gatherer", fn="0x0057B220", status_y=0x38, inset=[0x88, 4], workers_y=0x8e, desc_y=None,
                          ladder=dict(fire=10, none=[69, 9], s100=6, curse=11, bless=12, halted=9, out=5, idle=6),
                          evidence="positions exe; state strings hyp"),
    "urchin_quay": dict(panel="gatherer", fn="0x0057B760", status_y=0x38, inset=[0x88, 4], workers_y=0x8e, desc_y=None,
                        ladder=dict(fire=6, none=[69, 9], s100=2, curse=7, bless=8, halted=5, out=4, idle=2),
                        evidence="positions exe; state strings hyp"),
    "artisans_guild": dict(SERVICE, fn="0x0057EA60", status_y=0x3c,
                           ladder=dict(fire=7, none=1, s100=2, s75=3, s50=4, s25=5, s0=6, curse=8, bless=9),
                           evidence="positions exe; ladder from the string order (hyp)"),
    # trireme wharf 0x00583C60 (+ button 0x00642B38 drawn by info_window_draw 0x005724E0, click 0x00572490)
    "trireme_wharf": dict(panel="wharf", fn="0x00583C60", inset=[0xdf, 4], workers_y=0xdf, desc_y=-0x3f,
                          ladder=dict(fire=[69, 6], halted=4, none=5, s100=6, s75=7, s50=8, s25=9, s0=10,
                                      curse=[69, 10], bless=[69, 12]), evidence="exe"),
    # tower 0x0057A3E0: one status paragraph at +0x2d (no % ladder: 170:3 with a sentry out, else 170:4)
    "tower": dict(panel="tower", fn="0x0057A3E0", status_y=0x2d, inset=[0x97, 4], workers_y=0x9d, desc_y=None,
                  ladder=dict(fire=5, unmanned=10, no_palace=8, no_network=9, none=2, curse=6, bless=7, out=3, idle=4),
                  evidence="exe"),
    "palace": dict(panel="simple", fn="0x0057BB50", title_ref=[28, 117], desc_y_top=0x32, no_workers=True),
    # title + description only
    **{k: dict(panel="simple", fn=f, desc_y=d)
       for k, f, d in (("doric_column", "0x00577950", None), ("ionic_column", "0x00577950", None),
                       ("corinthian_column", "0x00577950", None), ("roadblock", "0x0057A2F0", -0x9e),
                       ("gatehouse", "0x0057A200", -0x9e), ("ruin", "0x0057DA10", -0x8f))},
    # walker list of the locality (0x00573540: inset at +0x28, 12 rows, 70:0 when nobody) + text
    **{k: dict(panel="locality", fn=f, desc_y=-0x71, desc_x=0x20) for k, f in (("avenue", "0x00577870"), ("boulevard", "0x00577790"))},
    "gardens": dict(panel="locality", fn="0x005731D0 (terrain window)", title_ref=[70, 22], desc_ref=[75, 1], desc_y=-0x71,
                    desc_x=0x20, evidence="seen (Park window); text 75:1 seen, the exe's lookup not read"),
    # title 90:0, text 90:variant (Building+0x12: text_ref_paragraph_override(0x5A, house_level))
    "commemorative_monument": dict(panel="simple", fn="0x00577C50", desc_index=1, desc_variant=True),
    # decorations 0x00577A10: title 137:2k, text 137:2k+1 at T+0x38
    **{k: dict(panel="decor", fn="0x00577A10") for k in (
        "bench", "flower_garden", "gazebo", "hedge_maze", "fish_pond", "tall_obelisk", "sundial", "topiary", "spring",
        "stone_circle", "short_obelisk", "water_park", "dolphin_sculpture", "orrery", "shell_garden", "baths", "bird_bath")},
}
DECOR_K = {0x7f: 0, 0xf: 1, 0x10: 2, 0x11: 3, 0x12: 4, 0x13: 5, 0x14: 6, 0x15: 7, 0x16: 8, 0x17: 9, 0x18: 10,
           0x19: 11, 0x94: 12, 0x95: 13, 0x96: 14, 0x97: 15, 0x98: 16}            # 0x00577A10 switch

# --- fixed layouts of the big panels ------------------------------------------------------------------
LAYOUTS = {
    "common": dict(
        evidence="exe: 0x0056E960/0x00577D20 (title), 0x00512EB0 (inset), 0x00577290 (workers line); seen: Infirmary",
        title_y=10, title_font="22C", status_x=0x20, status_font="11C", inset_x=0x10,
        workers=dict(icon_dx=0x28, icon_dy=6, text_dx=0x3c, need_dx=0x46, dy_short=10, dy_full=0x10,
                     reason_dx=0x46, reason_dy=0x1a, reason_w=400, font="11CB"),
        desc_x=0x20, desc_font="11C"),
    "house": dict(
        evidence="exe 0x0057F4E0, 0x00576DA0, 0x00576F60, 0x00577060",
        title_group=29, inset=[0x94, 10],
        occupants=dict(icon=[0x22, 0x9e], text=[0x32, 0xa8], font="11CB"),
        tax=dict(x=0x24, y=0xc2, font="11CB"), unrest=dict(x=0x24, y=0xd6, font="11CB",
                                                            steps=[[2, 21], [11, 22], [31, 23], [51, 24], [71, 25], [91, 26], [9999, 27]]),
        forage=dict(x=0x24, y=0xea, font="11CB", ref=[127, 28]),
        food=dict(icon=[0x20, 0x6e], num=[0x40, 0x6e], font="11C"),
        goods=dict(common=["fleece", "olive_oil"], elite=["fleece", "olive_oil", "wine", "armor", "horses"],
                   slots=[[0x20 + 110, 0x6e], [0x20 + 220, 0x6e], [0x20 + 330, 0x6e], [0x20, 0x82], [0x20 + 110, 0x82]],
                   num_dx=0x20),
        status=dict(x=0x20, y=0x24, w_cells=-4, font="11C", fire=[111, 1], no_road=[69, 4], base=[127, 36]),
        empty=dict(evidence="exe 0x0057FF00, 0x00573540", title=[128, 0], title_y=8, footer=[13, 1], footer_dy=-0x16,
                   list_inset=[0x28, 12], nobody=[70, 0], nobody_y=0x78, text_dy=-0x71, ok=[128, 1], no_road=[128, 2])),
    "storage": dict(
        evidence="exe 0x005B2880 (window), 0x005B38C0 (rows), 0x005B3660 (row), 0x005B2420 (status), 0x005B1DE0 (workers), "
                 "0x005715A0 (size)",
        x=0, y=32, cols=30, close_x=444, rows_rule="ceil(4*n/3)+13 (n = goods listed)",
        title_y=10, status_y=0x24, status_h=0x14,
        storing=dict(base=0x26, rule_dy=-5, label=[130, 5], space=[130, 6], space_x=0x118, x=0x22, font="11C", noun=[8, 16]),
        full=dict(ref=[130, 38]),
        header=dict(rule_dy=10, dy=0x10, rule2_dy=0x1b, font="9LTBK", cols=[[0x19, 8], [300, 9], [0x177, 10]], base=0x28),
        rows=dict(first=0x49, step=20, icon_x=0xf, icon_dy=-4, num_x=0x21, name_x=0x41, order_x=0x125, limit_x=0x18e,
                  fonts=dict(full="11LTYEL", empty="11C", stock="11LTBLUE"),
                  orders={"accept": [0, "11LTBLUE"], "refuse": [1, "11C"], "get": [2, "11LTBLUE"], "empty": [3, "11C"]}),
        workers=dict(inset_x=0x2d, inset_rows_from_bottom=6, cols_less=5, icon_dx=5, text_dx=0x19, dy=5,
                     reason_dy=0x14, font="11CB"),
        deliverymen=dict(x=0x32, dy=-0x38, font="11CB", group=130)),
    "agora": dict(
        evidence="exe 0x0057AA10 (window), 0x0040B5F0 (vendor boxes), rect table 0x005E86E8",
        title_group=97, inset=[0xf2, 5], workers_y=0xf2,
        boxes=[[20, 40, 120, 80], [170, 40, 120, 80], [320, 40, 120, 80], [20, 150, 120, 80], [170, 150, 120, 80], [320, 150, 120, 80]],
        vendors=[["food_vendor", "food"], ["fleece_vendor", "fleece"], ["oil_vendor", "olive_oil"], ["wine_vendor", "wine"],
                 ["arms_vendor", "armor"], ["horse_trainer", "horses"]],
        box=dict(name=[10, 10], icon=[10, 0x23], num=[0x1e, 0x23], state=[10, 0x3c], name_font="11C", num_font="11LTBLUE"),
        states=dict(no_vendor=[10, "11LTBLUE"], not_buying=[11, "11C"], no_labor=[19, "11LTBLUE"], buying=[18, "11LTYEL"],
                    no_goods=[12, "11C"], distributing=[17, "11LTYEL"], no_demand=[13, "11C"]),
        status=dict(fire=[0x11a, 23], no_stalls=[0x106, 4], no_road=[0x146], none=[0x11a, 3], waiting=[0x11a, 20],
                    out=[0x11a, 21], back=[0x11a, 22], icon=[0x20, 0x11a], text_x=0x40, font="11CB")),
    "sanctuary": dict(evidence="exe 0x005813F0 (texts 132:g+66/80/94 joined by ' ', prayer 132:10+g); positions seen (Oracle of Apollo, 800x600)",
                      title_y=10, x=0x14, w_less=0x1e, status_y=0x32, text1=66, text2=80, text3=94, pray=[75, 340, 301, 31], pray_text=10, pray_label=[10, 8], oracle=[75, 240, 301, 31],
                      # under construction (monument_progress < 100, 0x005813F0 first branch; seen: re/oracle/runs/sanctuary-window/b.bmp)
                      build=dict(title=[178, 2], body_y=0x42, halt=[75, 440, 301, 31], halt_text=[132, 112], halt_label_y=8,
                                 no_guild=[178, 0], no_artisans=[178, 1], halted=[132, 130], halted_working=[132, 129],
                                 none=dict(wood=3, sculpture=4, marble=5, black_marble=6, orichalc=7),
                                 stockpiled=dict(wood=8, sculpture=9, marble=10, black_marble=11, orichalc=12),
                                 undeliverable=dict(wood=13, sculpture=14, marble=15, black_marble=16, orichalc=17),
                                 check_order=["marble", "black_marble", "wood", "sculpture", "orichalc"],
                                 activity={"1": 18, "2": 19, "3": 20, "4": 21, "5": 22}, percent=23, remainder=25,
                                 loads=dict(marble=26, black_marble=28, wood=30, sculpture=32, orichalc=34),
                                 loads_order=["marble", "black_marble", "wood", "sculpture", "orichalc"], arrived=36)),
    "industry": dict(evidence="exe 0x00582920", icon=[10, 10], line_y=0x2c, input_y=0x3c, mint_y=0x39),
    "farm": dict(evidence="exe 0x00584520", icon=[10, 10], line_y=0x2c),
    # 0x00583C60: paragraphs at L+0x20 advance the pen y (DAT_00F13A6C) by 16 a line (paragraph_draw 0x005090A0);
    # top line at +0x2d (width C*16): 175:18 no palace / 175:2 n% 175:3 (status 0x1000 and the crew-all flag; the
    # number at +0x2c) / 175:16 repairing; then at +0x37+pen: 175:12 wood (count noun 8:54) and 175:13 armor at
    # L+0xe1 (pen += 26 + 10); status at +0x37+pen, (C-4)*16; trireme line (175:17 none, 175:14 at the wharf)
    # at +0x37+pen+10. Button: RIMS 384x20 at (L+0x28, T+(H-2)*16), label 175:(20 - C4&1) centred at T+H*16-0x1a.
    "wharf": dict(evidence="exe 0x00583C60, 0x005724E0, 0x00572490, table 0x00642B38", x=0x20, top_y=0x2d, num_y=0x2c,
                  base_y=0x37, armor_x=0xe1, noun=[8, 54], gap=10, button=[0x28, -0x20, 384, 20], label_dy=-0x1a,
                  no_palace=18, production=[2, 3], repairing=16, wood=12, armor=13, needs=17, at_wharf=14,
                  staff=19, send_home=20),
    "venue": dict(evidence="exe 0x005792A0, 0x00579800, 0x00578DE0"),
}

FOODS = ["urchin", "fish", "meat", "cheese", "carrots", "onions", "wheat", "oranges"]


def goods_icons(res):
    """Resource icon: SPR_GOODS_ICONS (Zeus_General group 123) + FUN_0040FD80(res); oranges, orichalc,
    black marble, chariots from Poseidon_Loaded groups 40..43 (packed 0x6828..0x682B); 'food' = +1 after
    wine's icon (0x0057F4E0)."""
    gen = {g["id"]: g["first"] for g in J("extracted/sprites/Zeus_General/atlas.json")["groups"]}
    pos = {g["id"]: g["first"] for g in J("extracted/sprites/Poseidon_Loaded/atlas.json")["groups"]}
    idx = {**{i: i for i in range(1, 8)}, 9: 8, 10: 9, 11: 10, 12: 11, 13: 12, 14: 13, 15: 14, 18: 15, 19: 16,
           20: 17, 21: 18, 23: 19, 24: 20, 25: 21, 26: 22, 27: 23}       # FUN_0040FD80
    special = {8: 40, 17: 41, 16: 42, 22: 43}
    out = {}
    for r in res:
        z = r["zeus_id"]
        if z in special:
            out[r["key"]] = dict(file="Poseidon_Loaded", index=pos[special[z]])
        elif z in idx:
            out[r["key"]] = dict(file="Zeus_General", index=gen[123] + idx[z])
    out["food"] = dict(file="Zeus_General", index=gen[123] + idx[21] + 1)
    return out


def main():
    texts = J("extracted/text/zeus_text.json")
    su = J("data/play/strings_ui.json")["buildings"]
    cat = J("data/buildings.json")
    res = J("data/resources.json")
    iface = {g["id"]: g for g in J("extracted/sprites/Zeus_Interface/atlas.json")["groups"]}
    used = {8, 13, 23, 28, 29, 44, 69, 70, 75, 97, 103, 111, 127, 128, 130, 132, 137, 157, 166, 178}   # 44:148 "of" (trade window)
    panels = {}
    for key, spec in cat.items():
        z = spec.get("zeus_id")
        s = su.get(key, {})
        p = dict(PANELS.get(key) or dict(panel="generic", fn=s.get("panel_fn") or "-", status_y=0x38, inset=[0x88, 4],
                                         workers_y=0x8e, desc_y=None, ladder=GEN, evidence="ours: fallback"))
        if spec.get("kind") == "monument" and key not in PANELS:
            p = dict(panel="monument", fn=s.get("panel_fn"), status_y=0x32, inset=[-0x6c, 4], workers_y=-0x66,
                     ladder=dict(none=[132, 0], s100=[132, 5], s75=[132, 1], s50=[132, 2], s25=[132, 3], s0=[132, 4],
                                 fire=[69, 6]), evidence="simplified: title, staffing (132:0..5), workers box (seen at y+388)")
        if spec.get("kind") in ("stall", "vendor"):
            p = dict(panel="agora_part", fn="-", evidence="ours: a stall opens its agora's window")
        p["zeus_id"] = z
        p["group"] = s.get("text_group")
        if p["group"] is not None:
            used.add(p["group"])
        if z is not None:
            p["rows"] = rows_of(z)
        if p["panel"] == "monument" and z is not None and 0x54 <= z <= 0x61:
            p["god"] = z - 0x54
        if p["panel"] == "decor":
            p["k"] = DECOR_K.get(z, 0)
        panels[key] = p
    out = dict(
        version=1,
        note="Building info windows (docs/play/info.md); generated by tools/play_info.py from the decompile "
             "readings listed per panel ('fn'). Positions: px from the window's top-left; negative y = from the bottom "
             "(T + H*16 + y). Text refs [group, index] into 'texts'.",
        cols=29,
        icons=dict(occupants=dict(file="Zeus_Interface", index=iface[93]["first"]),
                   workers=dict(file="Zeus_Interface", index=iface[93]["first"] + 1),
                   note="SPR_POP_MAN (group table entry 92 of Zeus_Interface, +0x4000 / +0x4001 in 0x00576DA0 / 0x00577290)"),
        goods_icons=goods_icons(res), foods=FOODS,
        resource_ids={r["key"]: r["zeus_id"] for r in res},
        layouts=LAYOUTS, panels=panels,
        texts={str(g): texts[str(g)] for g in sorted(used)},
    )
    p = os.path.join(ROOT, "data/play/info_panels.json")
    json.dump(out, open(p, "w"), indent=1, ensure_ascii=False)
    kinds = {}
    for k, v in panels.items():
        kinds[v["panel"]] = kinds.get(v["panel"], 0) + 1
    print(p, kinds, os.path.getsize(p), "bytes")


if __name__ == "__main__":
    main()
