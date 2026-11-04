"""data/play/walker_info.json: what the play mode's walker info window needs (docs/play/info.md "Walker
window"): our walker role -> the exe figure type, that type's name group / thought group / flags (figure
type table 0x00639698: +0x18 name group, +0x10 thought group, +0x14 flag bytes), the text groups used
(names, 64 figure types, 70 locality, thoughts), and the portrait group (Zeus_Unloaded SPR_FIG_PORTRAIT,
image = first + type: FUN_00573880 default). Run: python3 tools/play_walker_info.py"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = lambda p: json.load(open(os.path.join(ROOT, p)))

# our sim roles -> exe figure types (enums in extracted/model/figure_handlers.json); ours where the sim's
# role has no exact counterpart: trainee = worker 33, deer = boar 51, bull = cattle 76. The buyer of an agora stall
# is the agora vendor 37 ('Collecting' / 'Returning with'); a cart from a storage is the deliveryman 36 (sim/live.py
# fig_type)
ROLE_TYPE = dict(immigrant=1, emigrant=2, homeless=3, cart=4, buyer=37, peddler=26, water=60, healer=32,
                 philosophy=16, athletics=17, drama=18, competition=15, maintenance=8, watchman=61, tax=7,
                 trainee=33, scholar=72, astronomer=73, inventor=74, artisan=58, woodcutter=55, stonecutter=62,
                 miner=62, shepherd=30, goatherd=31, grower=5, hunter=53, rancher=77, diver=44, trader=19,
                 donkey=21, ship=20, boat=25, trireme=57, sheep=49, goat=50, cattle=76, bull=76, horse=43,
                 boar=51, deer=51, wolf=59, thief=23, vandal=29, mugger=27, disgruntled=22, plagued=66,
                 rabble=11, hoplite=12, horseman=13, nobleman=38, vendor_assistant=47,
                 god=67, monster=68, hero=69, priest=65)
# gods 67, monsters 68, heroes 69 (0x005740A0 cases 0x43..0x45): per id (Figure+0x60) the thought group
# (figure_thought_group 0x004E3750's switch), the name / title groups the window draws (157 + 158 + 83 friendly /
# unfriendly; 190; 185), and the portrait (FUN_00573880): image id font_group_entry(k) + 0x8000 = Zeus_Unloaded
# group rank k + 1, + 0xC000 = Poseidon_Unloaded rank k + 1; packed group 0x4NN = Zeus_Unloaded rank NN, 0x6NN =
# Poseidon_Unloaded rank NN.
GOD_THOUGHT = {0: 300, 1: 0x12d, 2: 0x12f, 3: 0x132, 4: 0x131, 5: 0x133, 6: 0x135, 7: 0x136, 8: 0x130, 9: 0x134,
               10: 0x137, 11: 0x12e, 12: 0x161, 13: 0x162}
MONSTER_THOUGHT = {0: 0x144, 1: 0x145, 2: 0x140, 3: 0x141, 4: 0x148, 5: 0x147, 6: 0x13f, 7: 0x142, 8: 0x14a,
                   9: 0x143, 10: 0x149, 11: 0x146, 12: 0x166, 13: 0x163, 14: 0x165, 15: 0x164, 17: 0x13e}
HERO_THOUGHT = {0: 0x138, 1: 0x139, 2: 0x13a, 3: 0x13b, 4: 0x13c, 5: 0x13d, 6: 0x168, 7: 0x167}
FIGURE_GROUPS = {157, 158, 83, 190, 185}


def portraits():
    """Per kind and id: [file, image index] (FUN_00573880 cases 0x43 / 0x44 / 0x45)."""
    def ranks(f):
        a = J(f"extracted/sprites/{f}/atlas.json")
        return [g for g in sorted(a["groups"], key=lambda g: g["id"]) if g["first"] > 0]
    zu, pu = ranks("Zeus_Unloaded"), ranks("Poseidon_Unloaded")
    z = lambda r, k=0: ["Zeus_Unloaded", zu[r - 1]["first"] + k]
    p = lambda r: ["Poseidon_Unloaded", pu[r - 1]["first"]]
    god = {i: z(11, i) for i in range(12)}                    # font_group_entry(10) + 0x8000 + id
    god.update({12: p(0x11), 13: p(0x12)})                    # entries 0x10 / 0x11 + 0xC000
    mon = {i: z(13, i) for i in range(18)}                    # font_group_entry(0xC) + 0x8000 + id (0x11: + 0xC)
    mon.update({12: p(0x18), 13: p(0x15), 14: p(0x17), 15: p(0x16)})   # entries 0x17 / 0x14 / 0x16 / 0x15 + 0xC000
    hero = {i: z(12, i) for i in range(6)}                    # packed 0x40C + id
    hero.update({6: p(0x1a), 7: p(0x19)})                     # packed 0x61A / 0x619
    return {"67": {str(k): v for k, v in god.items()}, "68": {str(k): v for k, v in mon.items()},
            "69": {str(k): v for k, v in hero.items()}}

EXTRA_TYPES = (36,)
# thought group by the figure's home (figure_thought_group 0x004E3750): miners 62 by building, growers at the fruit
# lodge, hunters of deer (341, not by home: not used)
THOUGHT_BY_HOME = {"foundry": {"62": 218}, "mint": {"62": 219}, "marble_quarry": {"62": 220},
                   "orichalc_refinery": {"62": 343}, "fruit_lodge": {"5": 340},
                   # agora vendors 37 by stall (FUN_005A9C20: groups 222..227)
                   "food_vendor": {"37": 222}, "fleece_vendor": {"37": 223}, "oil_vendor": {"37": 224},
                   "wine_vendor": {"37": 225}, "arms_vendor": {"37": 226}, "horse_trainer": {"37": 227}}
# name group by home (figure_name_group 0x004E34F0): agora vendors by stall type 0x44 -> 258, 0x45 -> 266, 0x47 ->
# 267, 0x49 -> 268, else 254
NAME_BY_HOME = {"food_vendor": {"37": 258}, "fleece_vendor": {"37": 266}, "oil_vendor": {"37": 254},
                "wine_vendor": {"37": 267}, "arms_vendor": {"37": 254}, "horse_trainer": {"37": 268}}
# the window's own lines (0x005740A0): 8 count nouns, 21 city names, 23 goods, 28 buildings, 129 walker lines,
# 274 miner kinds
LINE_GROUPS = {8, 21, 23, 28, 129, 274}


def main():
    figs = {f["type"]: f for f in J("extracted/model/figure_handlers.json")["figures"]}
    text = J("extracted/text/zeus_text.json")
    atlas = J("extracted/sprites/Zeus_Unloaded/atlas.json")
    portrait = next(g["first"] for g in atlas["groups"] if g["name"] == "SPR_FIG_PORTRAIT")
    iface = J("extracted/sprites/Zeus_Interface/atlas.json")
    tell = next(g["first"] for g in iface["groups"] if g["name"] == "SPR_TELL_ME_MORE_BTN")
    types, groups = {}, {64, 70}
    for t in sorted(set(ROLE_TYPE.values()) | set(EXTRA_TYPES)):
        f = figs[t]
        flags = int(f["flags"], 16)
        types[str(t)] = dict(enum=f["enum"], name_group=f["name_group"], thought_group=f["text_id"],
                             danger=bool(flags & 0xFF), mood=bool(flags >> 8 & 0xFF))
        groups |= {g for g in (f["name_group"], f["text_id"]) if g > 0}
    groups |= LINE_GROUPS | {g for D in (THOUGHT_BY_HOME, NAME_BY_HOME) for d in D.values() for g in d.values()}
    by_res = {"67": GOD_THOUGHT, "68": MONSTER_THOUGHT, "69": HERO_THOUGHT}
    groups |= FIGURE_GROUPS | {g for d in by_res.values() for g in d.values()}
    out = dict(note="generated by tools/play_walker_info.py; see docs/play/info.md 'Walker window'",
               roles=ROLE_TYPE, types=types, thought_by_home=THOUGHT_BY_HOME, name_by_home=NAME_BY_HOME, portrait=dict(file="Zeus_Unloaded", first=portrait), tell_more=tell,
               thought_by_res={t: {str(k): v for k, v in d.items()} for t, d in by_res.items()}, portraits=portraits(),
               texts={str(g): text.get(str(g), []) for g in sorted(groups)})
    with open(os.path.join(ROOT, "data/play/walker_info.json"), "w") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    print(len(types), "types,", len(groups), "text groups")


if __name__ == "__main__":
    main()
