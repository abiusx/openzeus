"""Build the engine's data/*.json from extracted/model (Zeus numbers) + a role overlay.

The output is our own format and is meant to be hand-edited afterwards (balance).
Usage: python3 tools/build_data.py [--difficulty Normal]
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "extracted", "model")

# Role overlay: Zeus type id -> engine role. Keys are short ids used in commands.
# kind: house | road | decor | service | producer | workshop | storage | vendor | admin
ROLES = {
    2: dict(key="house", kind="house", name="House"),
    # elite housing: 4x4 lot, levels 7 (vacant) .. 12 (Estate); residents don't work (labor.md)
    9: dict(key="elite_house", kind="house", name="Elite House", elite=True),
    28: dict(key="road", kind="road"),
    # on a road tile: roaming walkers turn back, walkers with a destination pass (pathfinding.md §6)
    123: dict(key="roadblock", kind="roadblock", name="Roadblock", size=1),
    # services: walker roams, sets a coverage counter on houses (value 96 days) or reduces a risk
    # services (services.md §3): spawn delay in days by staffing (>=100, >=75, >=50, >=25, >=1)
    74: dict(key="fountain", kind="service", service="water", spawn_days=[1, 3, 7, 15, 29]),
    76: dict(key="infirmary", kind="service", service="healer", spawn_days=[3, 7, 15, 29, 44]),
    121: dict(key="maintenance", kind="service", service="maintenance", name="Maintenance Office",
              spawn_days=[0, 1, 3, 7, 15]),
    124: dict(key="guardpost", kind="service", service="watchman", spawn_days=[0, 1, 3, 7, 15]),
    122: dict(key="tax_office", kind="service", service="tax", spawn_days=[0, 1, 3, 7, 15]),
    # culture venues need "shows" brought by trainees from schools; their performers roam.
    # Poseidon science buildings fill the same house culture slots (curator=competition,
    # astronomer=philosophy, scholar=athletics, inventor=drama; services.md §2).
    81: dict(key="podium", kind="service", service="philosophy", needs_shows=True, spawn_days=[8, 15, 30, 50, 100]),
    79: dict(key="gymnasium", kind="service", service="athletics", spawn_days=[4, 5, 10, 17, 30],
             trains=[["competitor", "stadium"]]),
    82: dict(key="theatre", kind="service", service="drama", needs_shows=True, spawn_days=[3, 7, 15, 29, 44]),
    80: dict(key="stadium", kind="service", service="competition", needs_shows=True, spawn_days=[3, 7, 15, 29, 44],
             unique_venue=True,     # two 5x5 halves (sim/systems/stadium.py, exe table 0x005E4958): w x h per side
             orientations={"v": [5, 10], "h": [10, 5]}),
    77: dict(key="college", kind="school", trains=[["philosopher", "podium"]], spawn_days=[8, 15, 30, 50, 100]),
    78: dict(key="drama_school", kind="school", trains=[["actor", "theatre"]], spawn_days=[8, 15, 30, 50, 100]),
    202: dict(key="bibliotheke", kind="service", service="athletics", walker="scholar", spawn_days=[4, 5, 10, 17, 30]),
    203: dict(key="observatory", kind="service", service="philosophy", walker="astronomer", needs_shows=True,
              spawn_days=[8, 15, 30, 50, 100]),
    204: dict(key="university", kind="school", trains=[["curator", "museum"], ["astronomer", "observatory"]],
              spawn_days=[8, 15, 30, 50, 100]),
    205: dict(key="laboratory", kind="service", service="drama", walker="inventor", spawn_days=[3, 7, 15, 29, 44]),
    206: dict(key="inventors_workshop", kind="school", trains=[["inventor", "laboratory"]], spawn_days=[8, 15, 30, 50, 100]),
    207: dict(key="museum", kind="service", service="competition", walker="curator", needs_shows=True,
              spawn_days=[3, 7, 15, 29, 44], unique_venue=True),
    # Poseidon hippodrome (finance.md 5.2): buys horses; monthly income by the number of horses
    199: dict(key="race_track", kind="hippodrome", horses_cap=24, income=[[4, 10], [12, 20], [24, 40], [36, 60],
              [60, 100], [100, 200], [200, 500]]),
    # food
    31: dict(key="wheat_farm", kind="producer", output="wheat", needs="meadow", mode="harvest", harvest_month=6),
    32: dict(key="onion_farm", kind="producer", output="onions", needs="meadow", mode="harvest", harvest_month=3),
    33: dict(key="carrot_farm", kind="producer", output="carrots", needs="meadow", mode="harvest", harvest_month=3),
    # herding (production.md "Herding"): herders walk to ready animals; 1 animal = 1 load. The sheds need
    # no meadow (exe build_commit 0x00498910: only farms, orchards and the animals do; buildings.md §5)
    41: dict(key="sheep_farm", kind="herd", output="fleece", animal="sheep", herder="shepherd",
            yield_=100, cap=500, work_ticks=20),  # shear/milk: herder_take_from_animal 0x004F7F60 timer 0x14
    42: dict(key="goat_farm", kind="herd", output="cheese", animal="goat", herder="goatherd",
            yield_=100, cap=500, work_ticks=20),  # shear/milk: herder_take_from_animal 0x004F7F60 timer 0x14
    40: dict(key="sheep", kind="animal", needs="meadow", animal="sheep"),
    39: dict(key="goat", kind="animal", needs="meadow", animal="goat"),
    # orchards: trees (1x1, meadow) tended and picked by growers from a lodge
    36: dict(key="olive_tree", kind="orchard", output="olives", needs="meadow", harvest_month=0, rot_month=2),
    35: dict(key="grapevine", kind="orchard", output="grapes", needs="meadow", harvest_month=9, rot_month=11),
    37: dict(key="growers_lodge", kind="lodge", trees=["olive_tree", "grapevine"], cap=500,
            work_ticks=204),                 # 204 ticks at the tree (grower_tend_done 0x004AB6F0 / pick 0x004AB830)
    # Poseidon orange trees + fruit lodge (oranges never rot: production.md)
    217: dict(key="fruit_tree", kind="orchard", output="oranges", needs="meadow", harvest_month=10, rot_month=None),
    214: dict(key="fruit_lodge", kind="lodge", trees=["fruit_tree"], cap=500, work_ticks=204),
    # hunting (production.md "Hunting lodge"): hunters chase prey (deer/boar) and carry back 100 meat
    46: dict(key="hunting_lodge", kind="hunt", output="meat", cap=500, work_ticks=60,
            hunters=[3, 2, 1, 1, 0], intervals=[1, 4, 16, 32, 64]),
    # fishing wharf: a boat sails to a fishing point, fishes 408..2040 ticks by staffing, sails back to its
    # mooring and unloads 204..1020 ticks, then the stock is 100 fish (figure_fishing_boat 0x004B5F10)
    44: dict(key="fishing_wharf", kind="fishery", output="fish", needs="coast", cap=500,
            boat_rate=[10, 8, 6, 4, 2], catch_ticks=[408, 816, 1224, 1632, 2040],
            unload_ticks=[204, 408, 612, 816, 1020]),
    # urchin quay: a diver works at its mooring until its timer (every tick of actions 7/8/9) is 408 or more at an
    # action-9 check, then dives to the end (urchin_collector_dive 0x004302D0): 5 cycles of 80 + 12 + 60 + 16 = 488
    # ticks (tools/play_diver.py, bugs.md 220); 200 ticks after coming back, +100 urchins
    45: dict(key="urchin_quay", kind="urchin", output="urchin", needs="coast", cap=500,
            intervals=[1, 4, 8, 16, 32], divers=[1, 1, 1, 1, 0], work_ticks=488, after_ticks=200),
    # Poseidon cattle: corral sends ranchers to bring cows in; each cow -> 200 meat, a calf is released
    220: dict(key="cattle", kind="animal", needs="meadow", animal="cattle"),
    216: dict(key="corral", kind="corral", output="meat", cap=600, herder="rancher", animal="cattle",
             work_ticks=60),
    # gatherers: workers walk to a resource tile, work there, carry back. No resource test at placement
    # (build_commit 0x00498910) and no radius: the nearest tile by walking distance over the whole map
    # (resource_tile_search 0x004A86E0; production.md "Resource search")
    51: dict(key="timber_mill", kind="gather", output="wood", resource="trees", worker="woodcutter",
            work_ticks=408, yield_=25, cap=500,
            mask=0x1, match=0x1, workers=[3, 2, 2, 1, 1]),
    49: dict(key="marble_quarry", kind="gather", output="marble", resource="marble", worker="stonecutter",
            work_ticks=1632, yield_=800, cap=800,
            mask=0x120000, match=0x20000, workers=[1, 1, 1, 1, 0]),
    # miners (production.md "Mines"): walk to copper/silver rock, work 408 ticks, bring back 25
    50: dict(key="foundry", kind="gather", output="bronze", resource="copper", worker="miner",
            work_ticks=408, yield_=25, cap=500,
            mask=0x300002, match=0x100002, workers=[3, 2, 1, 1, 0]),
    48: dict(key="mint", kind="gather", output="silver", resource="silver", worker="miner",
            work_ticks=408, yield_=25, cap=300,
            mask=0x300002, match=0x200002, workers=[3, 2, 1, 1, 0], keeps_output=True,
            mint_rate=[6, 4, 3, 1, 0]),
    135: dict(key="armory", kind="workshop", input="bronze", output="armor"),
    55: dict(key="sculpture_studio", kind="workshop", input="bronze", output="sculpture", batch=400,
            input_cap=400),                 # stock_cap 0x0048A880: 400 for 0x37 / 0xD4, 300 for 0x88
    213: dict(key="black_marble_shop", kind="gather", output="black_marble", resource="black marble",
             worker="stonecutter", work_ticks=1632, yield_=800, cap=800,
             mask=0x120000, match=0x120000, workers=[1, 1, 1, 1, 0]),
    211: dict(key="orichalc_refinery", kind="gather", output="orichalc", resource="orichalc", worker="miner",
             work_ticks=408, yield_=25, cap=500,
             mask=0x300002, match=0x300000, workers=[3, 2, 1, 1, 0]),
    # horse ranch (production.md): eats wheat, breeds a horse every 2 months; horses graze nearby
    133: dict(key="horse_ranch", kind="ranch", input="wheat", output="horses", input_cap=800,
             food_per_horse=10, max_horses=6),
    72: dict(key="arms_vendor", kind="vendor", goods="armor"),
    73: dict(key="horse_trainer", kind="vendor", goods="horses"),
    # workshops: input -> output, 320 progress (pct/10 per day) per 100 units
    53: dict(key="winery", kind="workshop", input="grapes", output="wine"),
    54: dict(key="oil_press", kind="workshop", input="olives", output="olive_oil"),
    # storage
    57: dict(key="granary", kind="storage", accepts="food", capacity=3200),
    58: dict(key="storehouse", kind="storage", accepts="nonfood", capacity=3200, size=3),
    # trade (trade.md): a post/dock bound to one partner city; holds goods like a storehouse
    # (15 bays x 400); per-good orders export/import/off with a stock limit. The original dock is a
    # 2x2 pier on water + a 4x4 dock house; ours is one 4x4 building that touches open water.
    169: dict(key="ruin", kind="ruin", name="Burning Ruins"),
    # monuments (monuments.md): artisans from the guild build sanctuaries/pyramids piece by piece
    56: dict(key="artisans_guild", kind="guild"),
    # military (wave 7: built and staffed, idle). Chariot workshop: wood -> chariots kept in the workshop up
    # to 400 (no cart; production.md "Chariot workshop"); it buys horses from ranches, and a (Poseidon) horse
    # trainer fetches chariot + horse together (economy.chariot_workshop); chariot vendor: no exe counterpart;
    # trireme wharf builds one trireme from 200 wood + 200 armor (text 175:11), it then waits.
    212: dict(key="chariot_workshop", kind="workshop", input="wood", output="chariot", input_cap=400,
              keeps_output=True, output_cap=400),
    215: dict(key="chariot_vendor", kind="vendor", goods="chariot"),
    136: dict(key="trireme_wharf", kind="shipyard", needs="coast", inputs=["wood", "armor"], input_cap=300),
    119: dict(key="commemorative_monument", kind="decor", size=3),
    # Hero's Hall (heroes-monsters.md "Hero's Hall"): one per needed hero (misc["hero"] = +0x12), cost 0, no staff;
    # sim/heroes runs the hero; offered only once the hero is needed (0x004FA620)
    125: dict(key="heroes_hall", kind="hall", name="Hero's Hall", size=4),
    # avenue/boulevard: segments across a road, built by dragging along it (sim/systems/avenues.py)
    118: dict(key="avenue", kind="avenue", size=1, width=2),
    126: dict(key="boulevard", kind="avenue", size=1, width=3),
    # infrastructure: bridge = road over water (per tile), wall = terrain flag 0x4000 (per tile);
    # gatehouse lets a road through a wall, tower stands on walls (military: built, idle)
    120: dict(key="bridge", kind="bridge", size=1),
    130: dict(key="wall", kind="wall", size=1),
    131: dict(key="gatehouse", kind="gatehouse", size=2),
    132: dict(key="tower", kind="tower", size=2),
    # agoras (storage-distribution.md part B): road strip + 2x2 stalls; size 0 = not a footprint
    63: dict(key="agora", kind="agora", name="Common Agora", stalls=3, size=0),
    64: dict(key="grand_agora", kind="agora", name="Grand Agora", stalls=6, size=0),
    66: dict(key="empty_stall", kind="stall", name="Empty Stall", size=2),
    62: dict(key="trading_post", kind="trade", route="land", capacity=6000, size=4),
    60: dict(key="dock", kind="trade", route="sea", capacity=6000, size=4, needs="coast"),
    # distribution: vendor buys from storage (cart), peddler roams and hands goods to houses
    68: dict(key="food_vendor", kind="vendor", goods="food"),
    69: dict(key="fleece_vendor", kind="vendor", goods="fleece"),
    70: dict(key="oil_vendor", kind="vendor", goods="olive_oil"),
    71: dict(key="wine_vendor", kind="vendor", goods="wine"),
}
# Trade partners (ours, 2026-10-27; trade.md for the mechanics). The original sandbox map has its own
# empire; we hard-code up to 10 partners (the original's limit is 10 docks) so that every tradeable
# good has at least one buyer and one seller. Quota = loads (100 units; sculpture 400) per year,
# editor levels 12/24/36; ours mostly 12 so exports stay near a city's real surplus. Prices: Open Play Sandbox map, per load; oranges, black marble, orichalc,
# chariot are not priced there (ours).
# No partner trades oranges (user 2026-10-30, the decision log): a Poseidon good, off while Poseidon is off; before,
# Babylon bought them and Tyre and Memphis sold them (12 each).
TRADE = dict(
    prices=dict(urchin=36, fish=36, meat=45, cheese=45, carrots=40, onions=40, wheat=30, oranges=40,
                wood=75, bronze=110, marble=84, grapes=42, olives=38, fleece=60, black_marble=150,
                orichalc=200, armor=200, sculpture=640, olive_oil=145, wine=160, chariot=250),
    units=dict(sculpture=400),
    land_every_days=4, sea_every_days=30,      # trader countdown in cycles (= our days)
    max_loads=dict(land=8, sea=12), trade_ticks=11, wait_ticks=20,
    partners=[
        dict(name="Sardis", route="land", buys=dict(wine=12, olive_oil=12, armor=12, sculpture=12),
             sells=dict(bronze=12, marble=12, wood=12)),
        dict(name="Babylon", route="land", buys=dict(fleece=12, olive_oil=12, wine=12),
             sells=dict(wheat=24, onions=12, carrots=12, black_marble=12)),
        dict(name="Susa", route="land", buys=dict(sculpture=12, armor=12, chariot=12, olives=12),
             sells=dict(fleece=12, cheese=12, meat=12, orichalc=12)),
        dict(name="Ecbatana", route="land", buys=dict(wheat=12, marble=12, wood=12, bronze=12, grapes=12),
             sells=dict(chariot=12, armor=12, olive_oil=12)),
        dict(name="Tyre", route="sea", buys=dict(fish=12, urchin=12, meat=12, cheese=12, black_marble=12),
             sells=dict(wine=12, sculpture=12, grapes=12)),
        dict(name="Miletus", route="sea", buys=dict(onions=12, carrots=12, fleece=24, orichalc=12, wine=12),
             sells=dict(fish=12, urchin=12, olives=12)),
        dict(name="Memphis", route="sea", buys=dict(wood=12, bronze=12, chariot=12, grapes=12, olives=12),
             sells=dict(wheat=24, marble=12)),
        dict(name="Corinth", route="sea", buys=dict(armor=12, sculpture=12, olive_oil=12, black_marble=12),
             sells=dict(wood=12, bronze=12, fleece=12)),
    ],
)

DECOR = [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 127, 128, 129, 145, 146, 148, 149,
         150, 151, 152]

# Zeus resource ids (text group 23) -> our keys
RESOURCES = {1: "urchin", 2: "fish", 3: "meat", 4: "cheese", 5: "carrots", 6: "onions", 7: "wheat",
             8: "oranges", 9: "wood", 10: "bronze", 11: "marble", 12: "grapes", 13: "olives",
             14: "fleece", 15: "horses", 16: "black_marble", 17: "orichalc", 18: "armor",
             19: "sculpture", 20: "olive_oil", 21: "wine", 22: "chariot", 23: "silver"}
FOOD = {"urchin", "fish", "meat", "cheese", "carrots", "onions", "wheat", "oranges"}
# Poseidon goods off while `poseidon` is off (economy.good_on; user 2026-10-30: oranges only for now)
POSEIDON_GOODS = {"oranges"}


# max_roam per figure handler (docs/logic/walkers.md §5.5): healer 0x004B78A0, water bearer 0x004C0BC0,
# mugger 0x004B68B0, disgruntled 0x004B5A20: 0x900; clerk 0x004AF550, culture 0x004B4370: 0xC00;
# superintendent 0x004AF930, watchman 0x004C0CF0, peddler 0x004B6720: 0xF00
ROAM_BUDGET = dict(water=0x900, healer=0x900, mugger=0x900, disgruntled=0x900,
                   tax=0xC00, philosophy=0xC00, athletics=0xC00, drama=0xC00, competition=0xC00,
                   maintenance=0xF00, watchman=0xF00, peddler=0xF00)


# Poseidon-only buildings (the expansion's manual; aesthetics 145-152 after its "many new aesthetic
# structures", hypothesis: their type ids follow Zeus's last ones). Off unless `poseidon on` (Game.poseidon):
# the goal is a complete Zeus (the decision log, 2026-10-28).
POSEIDON = {"sanctuary_hera", "sanctuary_atlas", "sanctuary_poseidon_grand", *(f"pyramid_{i:02d}" for i in range(1, 16)),
            "race_track", "bibliotheke", "observatory", "university", "laboratory", "inventors_workshop", "museum",
            "orichalc_refinery", "black_marble_shop", "chariot_workshop", "chariot_vendor", "fruit_lodge", "fruit_tree",
            "corral", "cattle", "ionic_column", "corinthian_column", "dolphin_sculpture", "orrery", "shell_garden",
            "baths", "bird_bath"}


DIFFICULTIES = ["VeryEasy", "Easy", "Normal", "Hard", "Impossible"]      # g_difficulty 0x00F2A988 order
TAX_COLS = ["Veryeasy", "Easy", "Normal", "Hard", "VeryHard"]             # Tax_Sentiment_Model.txt columns


def house_table(model):
    houses = []
    for i, h in enumerate(model["houses"][:13]):
        name = h["name"].split(":")[-1].strip()
        if name == "Vacant": name = "Elite lot"
        if name == "Devolved": name = "Elite devolved"
        houses.append(dict(name=name, elite=i >= 7, max_horses=h["max_horses"],
                           horses=h["horses_needed"], arms=h["arms_needed"], max_armor=h["max_armor"],
                           devolve_des=h["devolve_des"],
                           evolve_des=h["evolve_des"], culture=h["culture_needed"],
                           water=h["water_needed"], food_types=h["food_types_needed"],
                           fleece=h["fleece_needed"], oil=h["oil_needed"], wine=h["wine_needed"],
                           capacity=h["capacity"], tax_multiplier=h["tax_multiplier"],
                           crime_inc=h["crime_inc"], crime_base=h["crime_base"], soldier_pct=h["soldier_pct"],
                           # the building model row of the house's type 2 + level (manor and estate have their own
                           # fire risk; buildings_fire_collapse_risk 0x00492260 reads col 6/7 of the current type)
                           fire_risk=model["buildings"][2 + i]["fire_risk"],
                           damage_risk=model["buildings"][2 + i]["damage_risk"]))
    return houses


def difficulty_overlays(base, buildings, tax):
    """data/difficulty.json: per difficulty, what differs from the base data (docs/logic/difficulty.md).
    load_zeus_model 0x005B0C20 reads Model/Zeus_Model_<difficulty>.txt: building cost, fire and damage risk and
    the whole house table change; Tax_Sentiment_Model.txt has one column per difficulty (0x00567120); start
    funds % 0x005F7F08. Fields our role overlay overrides are left alone."""
    out = {}
    for di, d in enumerate(DIFFICULTIES):
        m = json.load(open(os.path.join(EX, f"model_{d}.json")))
        bov = {}
        for key, b in buildings.items():
            i = b.get("zeus_id")
            if i is None:
                continue
            for f in ("cost", "fire_risk", "damage_risk"):
                if b.get(f) == base["buildings"][i][f] and m["buildings"][i][f] != base["buildings"][i][f]:
                    bov.setdefault(key, {})[f] = m["buildings"][i][f]
        out[d] = dict(buildings=bov, houses=house_table(m),
                      tax_sentiment=[r["sentiment"][TAX_COLS[di]] for r in tax],
                      start_funds_pct=[150, 100, 100, 100, 80][di])
    return out


def main(argv):
    diff = argv[argv.index("--difficulty") + 1] if "--difficulty" in argv else "Normal"
    model = json.load(open(os.path.join(EX, f"model_{diff}.json")))
    sizes = {t["id"]: t for t in json.load(open(os.path.join(EX, "building_sizes.json")))["types"]}
    out = os.path.join(ROOT, "data")
    os.makedirs(out, exist_ok=True)

    buildings = {}
    roles = dict(ROLES)
    for i in DECOR:
        roles[i] = dict(kind="decor")
    for i, role in sorted(roles.items()):
        m = model["buildings"][i]
        name = m["name"].replace("BUILD_", "").strip().lower()
        key = role.get("key", name)
        b = dict(zeus_id=i, key=key, name=role.get("name", key.replace("_", " ").title()),
                 size=role.get("size", sizes[i]["size"]), cost=m["cost"],
                 employees=m["employees"], labor_category=sizes[i]["labor_category"],
                 desirability=dict(value=m["desirability"], step=m["des_step"],
                                   step_size=m["des_step_size"], range=m["des_range"]),
                 fire_risk=m["fire_risk"], damage_risk=m["damage_risk"],
                 fireproof=bool(sizes[i]["fireproof"]))
        b.update({k.rstrip("_"): v for k, v in role.items() if k not in ("key", "size", "name")})
        buildings[key] = b

    # test sink: unlimited storage, lowest priority, no staff; nothing is ever taken out of it.
    # Measures surplus production (carts still drive the goods there).
    buildings["endless_warehouse"] = dict(buildings["storehouse"], key="endless_warehouse",
                                          name="Endless Warehouse", zeus_id=None, cost=0, employees=0,
                                          accepts="all", capacity=10 ** 9, endless=True, test=True,
                                          fire_risk=0, damage_risk=0)

    # sanctuaries and Poseidon pyramids: one building per layout box (tools/monuments.py)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import monuments as monlib
    mons = monlib.build()
    gods = {"zeus": "Zeus", "poseidon": "Poseidon", "demeter": "Demeter", "apollo": "Apollo", "artemis": "Artemis",
            "ares": "Ares", "aphrodite": "Aphrodite", "hermes": "Hermes", "athena": "Athena",
            "hephaistos": "Hephaistos", "dionysus": "Dionysus", "hades": "Hades", "hera": "Hera", "atlas": "Atlas",
            "poseidon_grand": "Poseidon (grand)"}
    for key, lay in mons.items():
        i = lay["zeus_id"]
        m = model["buildings"][i]
        name = f"Sanctuary of {gods[key[10:]]}" if key.startswith("sanctuary_") else \
            "Palace" if key == "palace" else f"Pyramid {key[-2:]}"
        buildings[key] = dict(zeus_id=i, key=key, name=name, size=0, w=lay["w"], h=lay["h"], cost=m["cost"],
                              employees=m["employees"], labor_category=sizes[i]["labor_category"],
                              desirability=dict(value=m["desirability"], step=m["des_step"],
                                                step_size=m["des_step_size"], range=m["des_range"]),
                              # risks and fireproof as the exe (model row, type table +4): 0 / fireproof for
                              # sanctuaries and pyramids; the palace 5 / 5 at Normal, not fireproof (bug 268)
                              fire_risk=m["fire_risk"], damage_risk=m["damage_risk"],
                              fireproof=bool(sizes[i]["fireproof"]), kind="monument")
    with open(os.path.join(out, "monuments.json"), "w") as f:
        json.dump(mons, f)

    houses = house_table(model)

    resources = [dict(key=k, zeus_id=i, food=k in FOOD, **(dict(poseidon=True) if k in POSEIDON_GOODS else {}))
                 for i, k in RESOURCES.items()]
    tax = json.load(open(os.path.join(EX, "tax_sentiment.json")))
    rules = dict(
        difficulty=diff,
        ticks_per_day=51, days_per_month=16, start_year=-1000, start_funds=15000,
        coverage_days=96, coverage_radius=2, walker_roam_max=26, walker_spawn_days=3,
        trainee_shows=32, trainee_travel_ticks=3200, unique_venue_culture=10,
        risk_threshold=1000, risk_reduce=50,
        tax_rate=9, wage_rate=30,
        # share of common residents who work (labor_pool_compute 0x004865A0, labor.md §2): by_difficulty
        # 0x006335C4 [VeryEasy..Impossible] + by_wage 0x006335D8 [wage level index: the wage_levels entry
        # 0x00641F38 nearest to the wage, first on ties, 0x00569610] + by_health 0x006335F0 [health >= 80/65/35/20]
        workforce=dict(by_difficulty=[50, 45, 40, 37, 35], wage_levels=[0, 20, 26, 30, 34, 40],
                       by_wage=[-10, -6, -3, 0, 3, 5], health_steps=[20, 35, 65, 80], by_health=[-2, -1, 0, 1, 2]),
        culture_points=dict(philosophy=15, athletics=20, drama=25, competition=20),
        tax_levels=[dict(rate=r["rate_pct"], sentiment=r["sentiment"]["Normal"]) for r in tax],
        migration=[[71, 100], [61, 75], [50, 50], [36, 0], [26, -8], [16, -17], [0, -25]],
        storage_capacity=3200, storage_good_share=50,
        # roam length in tiles per role, from each handler's roam budget max_roam (+0x42; walkers.md
        # §5.5): roam_len += speed code (6 for all of these) per tick, 1 sub-step per tick, 15 per
        # tile; the walker turns home mid-tile, after entering tile (max_roam/6 + 6) // 15
        walker_roam={r: (b // 6 + 6) // 15 for r, b in ROAM_BUDGET.items()},
        walker_pace=15, animal_ready_per_month=9, cart_load=100, workshop_progress=320, farm_growth_max=1920,
    )
    for k in POSEIDON:
        buildings[k]["poseidon"] = True
    with open(os.path.join(out, "difficulty.json"), "w") as f:
        json.dump(difficulty_overlays(model, buildings, tax), f, indent=1)
    for name, obj in [("buildings", buildings), ("houses", houses), ("resources", resources),
                      ("rules", rules), ("trade", TRADE)]:
        with open(os.path.join(out, f"{name}.json"), "w") as f:
            json.dump(obj, f, indent=1)
    print(f"{len(buildings)} buildings, {len(houses)} houses, {len(resources)} resources -> data/")


if __name__ == "__main__":
    main(sys.argv[1:])
