"""Copy one sprite per building key from extracted/sprites into viewer/sprites (for the web viewer).

The images are the original game's art: viewer/sprites is git-ignored, rebuild it with
    python3 tools/viewer_sprites.py
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITES = os.path.join(ROOT, "extracted", "sprites")
OUT = os.path.join(ROOT, "viewer", "sprites")

# our building key -> Zeus_General sprite group (first image = the whole building)
GROUPS = {
    "wheat_farm": "SPR_B_FARM", "onion_farm": "SPR_B_FARM", "carrot_farm": "SPR_B_FARM",
    "sheep_farm": "SPR_B_SHEARER", "goat_farm": "SPR_B_DAIRY",
    "olive_tree": "SPR_OLIVE_TREE", "grapevine": "SPR_GRAPEVINE", "growers_lodge": "SPR_B_GROWERS_LODGE",
    "timber_mill": "SPR_B_TIMBER_MILL", "marble_quarry": "SPR_B_STONECUTTER_LODGE",
    "winery": "SPR_B_WINERY", "oil_press": "SPR_B_OILER",
    "granary": "SPR_B_GRANARY", "storehouse": "SPR_B_SBAY_GOODS", "endless_warehouse": "SPR_B_SBAY_GOODS",
    "food_vendor": "SPR_B_STALL_FOOD", "fleece_vendor": "SPR_B_STALL_FLEECE",
    "oil_vendor": "SPR_B_STALL_OIL", "wine_vendor": "SPR_B_STALL_WINE",
    "fountain": "SPR_B_FOUNTAIN1", "infirmary": "SPR_B_INFIRMARY", "maintenance": "SPR_B_MAINTENANCE_OFFICE",
    "guardpost": "SPR_B_WATCHPOST", "tax_office": "SPR_B_TAX_OFFICE", "palace": "SPR_B_PALACE1_FRONT",
    "podium": "SPR_B_PODIUM", "gymnasium": "SPR_B_GYMNASIUM", "theatre": "SPR_B_THEATER",
    "stadium": "SPR_B_STADIUM_N", "gardens": "SPR_GARDENS1", "doric_column": "SPR_DORIC_COLUMN",
    "ionic_column": "SPR_IONIC_COLUMN", "corinthian_column": "SPR_CORIN_COLUMN",
    "house_0": "SPR_B_FORSALE",
}
GROUPS.update({f"house_{i}": f"SPR_B_HOUSE{i}" for i in range(1, 8)})
GROUPS["roadblock"] = "SPR_B_ROADBLOCK"
GROUPS.update({"elite_0": "SPR_B_ELITE_HOUSE0A", "elite_1": "SPR_B_ELITE_HOUSE1", "elite_2": "SPR_B_ELITE_HOUSE2",
               "elite_3": "SPR_B_ELITE_HOUSE3", "elite_4": "SPR_B_ELITE_HOUSE4",
               "foundry": "SPR_B_FOUNDRY", "mint": "SPR_B_MINT", "armory": "SPR_B_ARMORY",
               "horse_ranch": "SPR_B_RANCH_HOUSE", "arms_vendor": "SPR_B_STALL_ARMOR",
               "horse_trainer": "SPR_B_STALL_HORSE", "hunting_lodge": "SPR_B_HUNTING_LODGE",
               "fishing_wharf": "SPR_B_FISHERY", "urchin_quay": "SPR_B_URCHIN_COLLECTOR",
               "sculpture_studio": "SPR_B_SCULPT_STUDIO", "college": "SPR_B_COLLEGE",
               "drama_school": "SPR_B_DRAMA_SCHOOL", "fruit_tree": None, "fruit_lodge": None})
GROUPS = {k: v for k, v in GROUPS.items() if v}
GROUPS["bench"] = "SPR_B_REC_AREA1"
GROUPS.update({"trading_post": "SPR_B_TPOST", "dock": "SPR_B_DOCK", "empty_stall": "SPR_STALL_UNASSIGNED",
               "artisans_guild": "SPR_B_CONS_GUILD", "trireme_wharf": "SPR_B_WARSHIP_WHARF",
               "gatehouse": "SPR_B_GATE_FRONT"})
EXACT_LATE = {"chariot_workshop": ("Poseidon_Loaded", "SPR_B_CHARIOT_FACTORY", 0),
              "chariot_vendor": ("Poseidon_Loaded", "SPR_B_CHARIOT_VENDOR", 0)}
# key -> (sprite file, group, n-th image in the group); identified by eye from contact sheets
EXACT = {
    "flower_garden": ("Zeus_General", "SPR_B_REC_AREA2", 0), "gazebo": ("Zeus_General", "SPR_B_REC_AREA2", 1),
    "topiary": ("Zeus_General", "SPR_B_REC_AREA2", 2), "fish_pond": ("Zeus_General", "SPR_B_REC_AREA2", 3),
    # Poseidon's redrawn beautification (Poseidon_Loaded, SPR_REC_*)
    "tall_obelisk": ("Poseidon_Loaded", "SPR_REC6", 0), "sundial": ("Poseidon_Loaded", "SPR_REC_SUNDIAL", 0),
    "hedge_maze": ("Poseidon_Loaded", "SPR_REC8", 0), "spring": ("Poseidon_Loaded", "SPR_REC_FOUNTAIN", 0),
    "stone_circle": ("Poseidon_Loaded", "SPR_REC_POND", 0), "dolphin_sculpture": ("Poseidon_Loaded", "SPR_REC_12", 0),
    "orrery": ("Poseidon_Loaded", "SPR_REC_13", 0), "shell_garden": ("Poseidon_Loaded", "SPR_REC_14", 0),
    "baths": ("Poseidon_Loaded", "SPR_REC_15", 0), "bird_bath": ("Poseidon_Loaded", "SPR_REC_16", 0),
    "short_obelisk": ("Poseidon_Loaded", "SPR_REC_11", 0), "water_park": ("Poseidon_Loaded", "SPR_WATERPARK", 0),
}


EXACT.update(EXACT_LATE)
EXACT.update({"fruit_tree": ("Poseidon_Loaded", "SPR_FRUIT_TREE", 0),
              "fruit_lodge": ("Poseidon_Loaded", "SPR_B_FRUIT_LODGE", 0),
              "corral": ("Poseidon_Loaded", "SPR_B_CORRAL_SLAUGHTER", 0),
              "black_marble_shop": ("Poseidon_Loaded", "SPR_B_BLACK_MARBLE_SHOP", 0),
              "orichalc_refinery": ("Poseidon_Loaded", "SPR_B_ORICHALC_REFINERY", 0),
              "bibliotheke": ("Poseidon_Loaded", "SPR_B_BIBLIOTHECA", 0),
              "observatory": ("Poseidon_Loaded", "SPR_B_OBSERVATORY", 0),
              "university": ("Poseidon_Loaded", "SPR_B_UNIVERSITY", 0),
              "laboratory": ("Poseidon_Loaded", "SPR_B_LABORATORY", 0),
              "inventors_workshop": ("Poseidon_Loaded", "SPR_B_INVENTORS_WORKSHOP", 0),
              "museum": ("Poseidon_Loaded", "SPR_B_MUSEUM", 0),
              "race_track": ("Poseidon_Loaded", "SPR_B_RACETRACK", 0)})


# crop growth stages (6 images per crop, small to ripe): crop_<output>_<0..5>
for crop, grp in (("wheat", "SPR_CROPS_WHEAT"), ("onions", "SPR_CROPS_ONION"), ("carrots", "SPR_CROPS_CARROT")):
    for k in range(6):
        EXACT[f"crop_{crop}_{k}"] = ("Zeus_General", grp, k)
for tree, file, grp in (("olives", "Zeus_General", "SPR_OLIVE_TREE"), ("grapes", "Zeus_General", "SPR_GRAPEVINE"),
                        ("oranges", "Poseidon_Loaded", "SPR_FRUIT_TREE")):
    for k in range(6):
        EXACT[f"tree_{tree}_{k}"] = (file, grp, k)


def main():
    groups = {}

    def image(file, group, n):
        if file not in groups:
            by = {}
            for im in json.load(open(os.path.join(SPRITES, file, "atlas.json")))["images"]:
                by.setdefault(im["group"], []).append(im)
            groups[file] = by
        ims = groups[file].get(group, [])
        return ims[n] if n < len(ims) else None

    os.makedirs(OUT, exist_ok=True)
    index = {}
    wanted = {k: ("Zeus_General", g, 0) for k, g in GROUPS.items()}
    wanted.update(EXACT)
    for key, (file, group, n) in sorted(wanted.items()):
        im = image(file, group, n)
        if im is None:
            print("missing", file, group, n)
            continue
        shutil.copyfile(os.path.join(SPRITES, file, im["png"]), os.path.join(OUT, key + ".png"))
        index[key] = dict(w=im["width"], h=im["height"], iso=im["iso_size"])
    json.dump(index, open(os.path.join(OUT, "index.json"), "w"), indent=1)
    print(f"{len(index)} sprites -> viewer/sprites")


if __name__ == "__main__":
    main()
