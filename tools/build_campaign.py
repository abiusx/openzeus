"""Zeus adventure .pak files -> data/campaign/<id>.json (+ index.json): everything an episode needs, as the exe's
loaders read it (docs/campaign-format.md; RE notes docs/logic/campaigns.md).

    python3 tools/build_campaign.py              writes data/campaign/*.json (every .pak in Adventures/, sub-folders too)
    python3 tools/build_campaign.py --check      rebuilds in memory and compares with the files
    python3 tools/build_campaign.py --show ID    one adventure, human-readable (episode chain, goals, gods, events)

Inputs (zeus-original, GOG 2.1.0.10): zeus-original/app/Adventures/**/*.pak, Zeus_MM.eng (episode texts: title,
subtitle), extracted/text/zeus_text.json (tools/engtext.py: goal names, gods, city names). Pure Python, no packages.

How the exe reads a .pak (GOG Zeus.exe addresses):
- adventure_read 0x00425D00 fills the adventure object 0x006AA750 field by field (file layout differs by .set
  version: 5 = every Zeus file, 26 = Poseidon; refs/zeus-poseidon-arm64/formats/set.md), then fix-ups by version:
  v < 22 FUN_00425260 renumbers goods (old Zeus -> new) in each episode's scenario block (player-city resources
  +0x7A8, buy list +0x7BC, sell list +0x7C2, the 23-byte table +0x7C8 by goods_remap_u8 0x0050EF70) and in every
  event (event_goods_remap 0x0050F3C0); v < 24: scenario +0x288 (Poseidon flag) = value_O; v < 25: requests of kind
  7 -> item 24; v < 26: quest byte +0x7A = 0. FUN_0052DF50 then reads the goal tables (4 globals) and, v < 22,
  FUN_005268D0 -> FUN_00526500 renumbers the good of goals of type 6 and 14.
- episode_start_load 0x00420390 for map slot s = 0x00F2A7B0 (0..9 parent-city episodes, 10..13 colonies) applies
  the episode record's kind (scenario +0x644 +0x58): 0 new city (load the parent map), 1 colony (load parent.dat,
  keep its empire/treasury/date, load the colony map), 2 continue (load parent.dat). See docs/campaign-format.md.
Output is our own format; raw bytes are kept where the core may still need them (scenario block, events).
"""
import hashlib
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_empire  # noqa: E402
import build_scenario  # noqa: E402
import mapfile  # noqa: E402

ADV = os.path.join(ROOT, "zeus-original", "app", "Adventures")
MM = os.path.join(ROOT, "zeus-original", "app", "Zeus_MM.eng")
OUT = os.path.join(ROOT, "data", "campaign")
TEXT = json.load(open(os.path.join(ROOT, "extracted", "text", "zeus_text.json")))

# --- the adventure object (adventure_read 0x00425D00): (object offset, size) in file order, by .set version --------
def _fields(ver):
    f = [(0x4, 4), (0x8, 4), (0xC, 4), (0x10, 4), (0x14, 0xDE8), (0xDFC, 0xDE8), (0x1BE4, 0x4F60), (0x6B44, 0x1FC0)]
    f += [(0x8B04 + 4 * i, 4) for i in range(2)] + [(0x8B0C, 16)] + [(0x8B1C + 4 * i, 4) for i in range(11)]
    f += [(0x8B48, 40), (0x8B70, 40)]
    if ver < 23:   # 224-byte god blocks read into 300-byte slots, +0xE0 (monument count) = 0
        f += [(0x8B98 + 300 * i, 0xE0) for i in range(10)] + [(0x9750 + 300 * i, 0xE0) for i in range(4)]
    else:
        f += [(0x8B98, 3000), (0x9750, 1200)]
    f += [(0x9C00, 0x2D690), (0x37290, 0x122A0), (0x49530, 1), (0x49534, 4), (0x49538, 0x14), (0x4954C, 500000),
          (0xC366C, 0x28), (0xC3694, 0x10), (0xC36A4, 0x280), (0xC3924, 0x2800), (0xC6124, 0x2800), (0xC8924, 0x100),
          (0xC8A24, 0x1000), (0xC9A24, 0x1000), (0xCAA24, 0x40), (0xCAA64, 0x400), (0xCAE64, 0x400),
          (0xCB264, 0x28), (0xCB28C, 0x10), (0xCB29C, 0x1000)]
    if ver > 2:
        f += [(0xCC29C, 4)]
    if ver > 3:
        f += [(0xCC2A0, 0x6E), (0xCC30E, 0x6E)]
    if ver > 4:
        f += [(0xCC37C, 10), (0xCC386, 4)]
    if ver > 20:
        f += [(0xCC7D8, 4)]
    return f


OBJ_SIZE = 0xCC7DC
# FUN_0052DF50: the goal tables, 4 globals after the object: colony counts, colony goals, parent counts, parent goals
GOAL_GLOBALS = [(0xFE3B5C, 0x10), (0xFE3B6C, 0x720), (0xFE2964, 0x28), (0xFE298C, 0x11D0)]

# goods: old Zeus numbering (.set < 22) -> new (Poseidon) numbering (the switch in FUN_00425260 / FUN_00526500 /
# goods_remap_all 0x0050F7E0); 0 = no such good
OLD2NEW = {**{i: i for i in range(1, 8)}, **{i: i + 1 for i in range(8, 15)}, **{i: i + 3 for i in range(15, 20)},
           19: 23, 20: 24, 21: 25, 22: 26, 23: 27}
NEW2OLD = {v: k for k, v in OLD2NEW.items() if v <= 22}
GOODS = build_empire.GOODS                       # new numbering -> our keys (23 drachmas)
GOODS_X = {**GOODS, 24: "troops", 25: "food"}   # event/goal items past the goods (world-map.md 9)

KIND = {0: "zeus_campaign", 1: "folder", 2: "tutorial", 3: "poseidon_campaign", 4: "folder"}
EPISODE_KIND = {0: "new_city", 1: "colony", 2: "continue"}       # record +0x58, episode_start_load switch
NEXT = {0: "parent", 1: "colony", 2: "parent", 3: "end"}         # record +0x54, FUN_00422FC0 / FUN_00421920

# scenario +0x408: 100 i16 "allowed" flags, index -> what FUN_00402B80 gates with it (exe building type in the switch
# at 0x00402D15; our keys from data/buildings.json zeus_id). Names checked case by case; 0 and 5 are not read.
ALLOWED = {1: "mint", 2: "hunting_lodge", 3: "olive_press", 4: "grand_agora", 6: "corral (poseidon)", 7: "granary",
           8: "agora", 9: "storehouse", 10: "trade (posts / docks)", 11: "stadium / museum", 12: "theatre / laboratory",
           13: "gymnasium / bibliotheke", 14: "winery", 15: "sculpture_studio", 16: "podium / observatory",
           17: "college / university", 18: "fountain", 19: "horse_ranch", 20: "drama_school / inventors_workshop",
           21: "maintenance", 22: "infirmary", 23: "tax_office", 24: "guardpost", 25: "palace", 26: "heroes_hall",
           27: "roadblock", 28: "bridge", 29: "columns", 30: "gardens", 31: "avenue", 32: "boulevard", 33: "wall",
           34: "tower", 35: "gatehouse", 36: "bench", 37: "flower_garden", 38: "gazebo", 39: "hedge_maze",
           40: "fish_pond", 41: "armory", 42: "trireme_wharf", 43: "elite_house", 44: "hippodrome (poseidon)",
           45: "chariot_factory (poseidon)", 46: "tall_obelisk", 47: "sundial", 48: "topiary", 49: "spring",
           50: "stone_circle", 51: "short_obelisk", 52: "water_park", 53: "dolphin_sculpture", 54: "orrery",
           55: "shell_garden", 56: "baths", 57: "bird_bath"}

# the tutorial menu (FUN_005BE2F0 checks): .pak names at 0x0065C508 and start saves at 0x0065D548 (stride 0x104);
# 0..7 "Beginning tutorials", 8..15 "Advanced tutorials". A tutorial STARTS from its save (tutorial_load_save
# 0x005BEBD0 -> game_file_load 0x0050E610 "Adventures\\tutorialNN.sav"), not from the .pak's episode 0; the .pak
# gives the later episodes and colonies (the save holds the adventure name, scenario record +0x5D).
TUTORIALS = ["housing", "food", "agora", "culture", "hygiene", "goods", "oliveoil", "firstcity",
             "interface", "trade", "palace", "warrior", "sanctuary", "colony", "peacewar", "bigcity"]
GOAL_TYPES = TEXT["194"][:17]   # 0 Population .. 16 Hippodrome (text group 194 = goals, FUN_0052B020 uses 0xC2)
GOD = TEXT["157"][:14]
MONSTER = TEXT["190"][:18]


def i16(b, o):
    return struct.unpack_from("<h", b, o)[0]


def i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", re.sub(r"^[^A-Za-z0-9]+", "", name).lower()).strip("_")


def mm_records():
    """Zeus_MM.eng: 80-byte records; title +0x44, subtitle +0x48, body +0x4C (the exe's table 0x00F13CB0 that
    FUN_0042B950 / FUN_0042B560 / FUN_0042B980 read for ids 0..999)."""
    d = open(MM, "rb").read()
    n, = struct.unpack_from("<I", d, 0x14)
    area = 0x13898

    def s(o):
        return d[area + o:d.index(b"\0", area + o)].decode("cp1252") if o else ""
    return [tuple(s(x) for x in struct.unpack_from("<3I", d, 0x18 + 80 * i + 0x44)) for i in range(n)]


MMR = mm_records()


def text_ref(i):
    if i is None or i < 0 or i >= 1000 or i >= len(MMR):
        return None
    t, c, _ = MMR[i]
    return dict(id=i, title=t, subtitle=c)


# --- reading -----------------------------------------------------------------------------------------------------
def read_object(d):
    """The adventure object as the exe holds it after adventure_read + fix-ups, and the goal globals."""
    ver = struct.unpack_from("<I", d, 4)[0]
    obj = bytearray(OBJ_SIZE)
    p = 4
    for off, n in _fields(ver):
        obj[off:off + n] = d[p:p + n]
        p += n
    goals = {}
    for addr, n in GOAL_GLOBALS:
        goals[addr] = bytearray(d[p:p + n])
        p += n
    return ver, obj, goals, p


def fix_scenarios(obj, ver):
    """FUN_00425260 (v < 22, goods part; the events are renumbered by build_scenario.record) and the v < 24 copy of
    value_O into scenario +0x288."""
    for s in range(14):
        b = 0x1BE4 + s * 0x7F0
        if ver < 22:
            for o, n in ((0x7A8, 20), (0x7BC, 4), (0x7C2, 4)):
                for k in range(n):
                    obj[b + o + k] = OLD2NEW.get(obj[b + o + k], 0) if obj[b + o + k] <= 23 else 0
            t = obj[b + 0x7C8:b + 0x7C8 + 23]                       # goods_remap_u8: new[n] = old[NEW2OLD[n]]
            obj[b + 0x7C8:b + 0x7C8 + 23] = bytes([t[0]] + [t[NEW2OLD[n]] if n in NEW2OLD else 0
                                                             for n in range(1, 23)])
        if ver < 24:
            # value_O is not in v < 21 files: the object keeps its previous value (assumed 0: a fresh object)
            obj[b + 0x288:b + 0x28A] = obj[0xCC7D8:0xCC7DA]


def goal_tables(goals, ver):
    """[slot] -> list of 76-byte goal records (slots 0..9 parent table 0x00FE2964/0x00FE298C, 10..13 colony table
    0x00FE3B5C/0x00FE3B6C), after FUN_005268D0 (v < 22)."""
    out = {}
    for s in range(14):
        cnt_b, tab_b, k = (goals[0xFE2964], goals[0xFE298C], s) if s < 10 else (goals[0xFE3B5C], goals[0xFE3B6C], s - 10)
        n = i32(cnt_b, 4 * k)
        recs = []
        for j in range(max(0, min(n, 6))):
            r = bytearray(tab_b[k * 456 + 76 * j:k * 456 + 76 * (j + 1)])
            if ver < 22:                                                   # FUN_00526500
                if i32(r, 0) == 14:
                    r[4] = OLD2NEW.get(r[4], 0) if r[4] <= 23 else 0
                elif i32(r, 0) == 6:
                    v = i32(r, 4)
                    struct.pack_into("<i", r, 4, OLD2NEW.get(v, 0) if 0 <= v <= 23 else 0)
            recs.append(bytes(r))
        out[s] = (n, recs)
    return out


def expand_goals(recs):
    """FUN_00526430 (after the copy in FUN_0052DE20): every type-11 goal is removed and replaced by up to 8 type-14
    goals (good byte +4+i, amount int +0xC+4i, start value int +0x2C+4i; amount > 0 and good != 0; at most 6 goals).
    The type-11 goods are not renumbered by FUN_00526500 (only 6 and 14): in a v5 file they stay old numbers."""
    recs = [bytearray(r) for r in recs]
    while True:
        k = next((i for i, r in enumerate(recs) if i32(r, 0) == 11), None)
        if k is None:
            return [bytes(r) for r in recs]
        r = recs.pop(k)
        for i in range(8):
            good, amount, have = r[4 + i], i32(r, 0xC + 4 * i), i32(r, 0x2C + 4 * i)
            if amount > 0 and good and len(recs) < 6:
                g = bytearray(76)
                struct.pack_into("<i", g, 0, 14)
                g[4] = good
                struct.pack_into("<ii", g, 8, amount, have)
                recs.append(g)


def goal(r):
    """One goal record (76 B) decoded by what the checks read (FUN_00526FC0 / FUN_0052B7D0, docs/campaign-format.md)."""
    t = i32(r, 0)
    v = [i32(r, 4 * k) for k in range(1, 6)]
    g = dict(type=t, name=GOAL_TYPES[t] if 0 <= t < len(GOAL_TYPES) else str(t), v=v[:4])
    if t == 0:
        g.update(population=v[0])
    elif t == 1:
        g.update(treasury=v[0])
    elif t == 2:
        g.update(god=GOD[v[1]] if 0 <= v[1] < 14 else None, count=v[2],
                 rule="v0 != -1 -> count 1; count > 1: sanctuaries v3 >= count; else the god v1's sanctuary built")
    elif t == 3:
        g.update(unit=v[0], count=v[1])
    elif t in (4, 5):
        g.update(event=v[0], state=10 if t == 4 else 5)
    elif t == 6:
        g.update(good=GOODS_X.get(v[0]), amount=v[1])
    elif t == 7:
        g.update(city=v[0])
    elif t == 8:
        g.update(profit=v[0])
    elif t == 9:
        g.update(house_level=v[0], count=v[1])
    elif t == 10:
        g.update(partners=v[0])
    elif t in (12, 13):
        g.update(years=v[0])
    elif t == 14:
        g.update(good=GOODS_X.get(r[4]), amount=v[1])
    elif t == 15:
        g.update(pyramid=v[1], slot=v[2])
    elif t == 16:
        g.update(length=v[0])
    g["raw"] = r.hex()
    return g


def god_block(blk):
    """g_scenario_gods 0x00FFA450 (300 B) as episode_start_load copies it: +0 24 god slots, +0x60 independent
    monster, +0x64 24 ints (copied, not decoded), +0xC4 24 bytes may-be-jealous / sanctuary allowed, +0xDC max
    sanctuaries, +0xE0 monument count, +0xE4 6 x 12 B monument slots (Poseidon pyramids, monuments.md)."""
    g = build_scenario.gods(blk)
    g.pop("raw")
    g["b64"] = list(struct.unpack_from("<24i", blk, 0x64))
    g["monument_count"] = i32(blk, 0xE0)
    g["monuments"] = [dict(type=i32(blk, 0xE4 + 12 * k), b4=i32(blk, 0xE8 + 12 * k), flags=i32(blk, 0xEC + 12 * k))
                      for k in range(6)]
    g["raw"] = bytes(blk).hex()
    return g


def episode(obj, ver, slot, goals_tab, maps):
    sc = bytes(obj[0x1BE4 + slot * 0x7F0:][:0x7F0])
    rec = sc[0x644:0x644 + 356]                  # FUN_0042B480(slot, 1): the copy episode_start_load uses
    kind, nxt = i32(rec, 0x58), i32(rec, 0x54)
    gods = bytes(obj[0x8B98 + slot * 300:][:300])
    n_ev = i32(obj, 0xC366C + 4 * slot)          # adventure_episode_event_count 0x0042B760 (slot 10.. = colony counts)
    evs = []
    for i in range(n_ev):
        r = obj[0x9C00 + slot * 18600 + 124 * i:][:124]
        e = build_scenario.record(bytes(r), ver, remap=ver < 22)
        e["index"] = i
        evs.append(e)
    n_goals, grecs = goals_tab[slot]
    city = dict(                                  # episode_start_load -> g_cities[player] (kinds 0 and 2)
        resources=[GOODS.get(x) for x in sc[0x7A8:0x7BC] if x],                       # +0xA8, 20 B
        buys=[GOODS.get(x) for x in sc[0x7BC:0x7C0] if x],                             # buy_list +0xBC
        sells=[GOODS.get(x) for x in sc[0x7C2:0x7C6] if x],                            # sell_list +0xC4
        table_60={GOODS[k]: sc[0x7C8 + k] for k in range(1, 23) if sc[0x7C8 + k]},    # +0x60, 23 B
        wealth=i32(obj, 0x8B70 + 4 * slot) if slot < 10 else None,                    # FUN_0042B790
        military=i32(obj, 0x8B48 + 4 * slot) if slot < 10 else None,                  # FUN_0042B780
        attitude=i32(obj, 0xCB264 + 4 * slot) if slot < 10 else None)                 # FUN_0042B7A0
    if slot >= 10:      # kind 1 writes only the resources; the rest is the colony city's own record (carried empire)
        city = dict(resources=city["resources"])
    ep = dict(
        slot=slot, role="parent" if slot < 10 else "colony", number=slot + 1 if slot < 10 else slot - 9,
        start=EPISODE_KIND.get(kind, kind), next=NEXT.get(nxt, nxt) if slot < 10 else "parent",
        intro=text_ref(i32(rec, 8)), victory=text_ref(i32(rec, 0x14)),
        start_year=i16(sc, 0), funds=i32(sc, 0x20),
        # +0x288 = 0x00902BB0 (poseidon_game 0x004200F0 also needs 0x006AA4E0, the Poseidon mode). v < 21 files have
        # no value_O: the exe copies a stale object value (0 after the tutorial, 1 in the Europa run): None here
        poseidon=i16(sc, 0x288) if ver >= 21 else None, games_year=i16(sc, 0x328),
        allowed={ALLOWED[k]: i16(sc, 0x408 + 2 * k) for k in sorted(ALLOWED)},
        allowed_raw=list(struct.unpack_from("<100h", sc, 0x408)),
        player_city=city,
        gods=god_block(gods),
        goals_stored=[goal(r) for r in grecs], goal_count=n_goals,
        goals=[goal(r) for r in expand_goals(grecs)],
        events=evs,
        tutorial=None,
        record=dict(b00=i32(rec, 0), map=i32(rec, 0xC), b10=i32(rec, 0x10), b18=list(struct.unpack_from("<14i", rec, 0x18)),
                    name=rec[0x5D:].split(b"\0")[0].decode("cp1252")))
    if obj[0x49530] == 2:                        # tutorials: FUN_0042B920; else every category 1 and the map button 1
        ep["tutorial"] = dict(build_categories=list(obj[0xCC2A0 + 11 * slot:][:11]),   # FUN_0042B9D0 -> 0x00FEAE06[11]
                              world_map_button=obj[0xCC37C + slot])                    # FUN_0042BAB0 -> 0x00FE6A5A
    return ep


def build(path):
    d = open(path, "rb").read()
    ver, obj, goals, end = read_object(d)
    fix_scenarios(obj, ver)
    gt = goal_tables(goals, ver)
    offs = mapfile.pak_map_offsets(d)
    maps = []
    for k, o in enumerate(offs):
        if o is None:
            continue
        hdr, blocks = mapfile.read_blocks(d, o)
        emp = build_empire.build(path, (hdr, blocks))
        # the empire is summarized here (what the campaign logic reads: colony choice, Rule goals, city names); the
        # full empire of a map container comes from build_empire.build(path, mapfile.pak_map(path, k)) (1L-2)
        cities = [dict(id=c["id"], name=c["name"], kind=c["kind"], relation=c["relation"], active=c["active"],
                       visible=c["visible"]) for c in emp["cities"]]
        maps.append(dict(index=k, slot=0 if k == 0 else 9 + k, offset=o, version=hdr["version"],
                         sha256=hashlib.sha256(d[o:hdr["end"]]).hexdigest(),
                         origin=list(mapfile.scenario_origin(blocks)), map_picture=emp["map_picture"],
                         cities=cities))
    parent = next(m for m in maps if m["index"] == 0)
    # colony_index_nth 0x00462280: the n-th in-use city of kind 1 (colony) in the empire; the colony choice screen
    # (0x34, FUN_00421AF0) offers those not yet active; choice n -> map slot 9 + n
    col_cities = [c for c in parent["cities"] if c["kind"] == "colony"]
    colonies = []
    for n, c in enumerate(col_cities[:4], 1):
        colonies.append(dict(n=n, slot=9 + n, city=c["id"], name=c["name"], active=c["active"],
                             map=n if offs[n] is not None else None))
    used = [s for s in range(14) if (s == 0 or (s < 10 and _reachable(obj, s)) or
                                     (s >= 10 and offs[s - 9] is not None))]
    name = os.path.basename(path)[:-4]
    out = dict(
        _doc="Built by tools/build_campaign.py (docs/campaign-format.md); do not edit by hand.",
        id=slug(name), name=name, source=os.path.relpath(path, ROOT), sha256=hashlib.sha256(d).hexdigest(),
        set_version=ver, kind=KIND.get(obj[0x49530], obj[0x49530]), kind_raw=obj[0x49530],
        game="poseidon" if ver >= 23 else "zeus",
        header=dict(episodes=i32(obj, 8), b0c=i32(obj, 0xC), colonies=i32(obj, 0x10), picture=i32(obj, 0xCC29C)),
        brief=text_ref(i32(obj, 0x8B40)), complete=text_ref(i32(obj, 0x8B44)),
        order=_order(obj),
        colonies=colonies,
        tutorial=_tutorial(name),
        maps=maps,
        episodes=[episode(obj, ver, s, gt, maps) for s in used])
    return out


def _tutorial(name):
    if name not in TUTORIALS:
        return None
    i = TUTORIALS.index(name)
    sav = os.path.join(ADV, f"tutorial{i:02d}.sav")
    return dict(index=i, menu="basic" if i < 8 else "advanced", start_save=os.path.relpath(sav, ROOT),
                start_save_sha256=hashlib.sha256(open(sav, "rb").read()).hexdigest())


def _reachable(obj, s):
    """Parent slot s is played when every slot before it continues (next != 3 'end')."""
    for k in range(s):
        if i32(obj, 0x1BE4 + k * 0x7F0 + 0x644 + 0x54) == 3:
            return False
    return True


def _order(obj):
    """The play order by FUN_00422FC0 / FUN_00421920: start at slot 0; a parent episode with next 3 ends the
    adventure, next 1 opens the colony choice (then the colony slot, then back to the parent slot + 1), else slot+1."""
    out, s = [], 0
    while s < 10:
        nxt = i32(obj, 0x1BE4 + s * 0x7F0 + 0x644 + 0x54)
        out.append(s)
        if nxt == 3:
            break
        if nxt == 1:
            out.append("colony")
        s += 1
    return out


def paks():
    out = []
    for dp, _, fs in os.walk(ADV):
        out += [os.path.join(dp, f) for f in fs if f.lower().endswith(".pak")]
    return sorted(out)


def dump(obj, depth=0, inline=4):
    """JSON, one item per line down to `inline` levels, compact below (events and goals one line each)."""
    if depth >= inline or not isinstance(obj, (dict, list)) or not obj:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")) if depth else json.dumps(obj) + "\n"
    pad, pad1 = " " * depth, " " * (depth + 1)
    if isinstance(obj, dict):
        body = ",\n".join(f"{pad1}{json.dumps(k)}: {dump(v, depth + 1, inline)}" for k, v in obj.items())
        s = "{\n" + body + "\n" + pad + "}"
    else:
        s = "[\n" + ",\n".join(pad1 + dump(v, depth + 1, inline) for v in obj) + "\n" + pad + "]"
    return s + ("\n" if depth == 0 else "")


def index(advs):
    return dict(_doc="Built by tools/build_campaign.py (docs/campaign-format.md).",
                adventures=[dict(id=a["id"], name=a["name"], file=a["source"], kind=a["kind"], game=a["game"],
                                 set_version=a["set_version"], picture=a["header"]["picture"],
                                 title=(a["brief"] or {}).get("title"), order=a["order"],
                                 tutorial=(a["tutorial"] or {}).get("index"),
                                 colonies=len(a["colonies"]), maps=len(a["maps"])) for a in advs])


TEXT_GROUPS = (5, 20, 28, 52, 62, 87, 98, 138, 157, 185, 194, 253, 287, 293, 333)


def texts():
    """The text groups the campaign module and its screens write (sim/campaign/texts.py, docs/play/campaign.md):
    5 set-aside dialog, 20 BC/AD, 28 house levels, 52 god quests, 62 victory / defeat / colony choice, 87 monsters,
    98 goods units, 138 military, 157 gods, 185 Dispatch Hero, 194 goals, 253 relationships, 287 / 293 / 333 the
    new-game screens (adventure list, family menu, tutorial names)."""
    return dict(_doc="Built by tools/build_campaign.py from extracted/text/zeus_text.json (Zeus_Text.eng groups).",
                groups={str(g): TEXT[str(g)] for g in TEXT_GROUPS})


def show(a):
    print(f"{a['name']}  [{a['kind']}, {a['game']}, .set v{a['set_version']}]  brief: {(a['brief'] or {}).get('title')}")
    print("order:", a["order"], " colonies:", [(c["n"], c["name"], c["map"]) for c in a["colonies"]])
    for e in a["episodes"]:
        print(f"- slot {e['slot']:2d} {e['role']} {e['number']}: start={e['start']} next={e['next']} "
              f"year={e['start_year']} funds={e['funds']} intro={(e['intro'] or {}).get('title')!r}")
        print("    goals:", [(g["name"], g["v"]) for g in e["goals"]])
        print("    gods:", e["gods"]["names"][:4], "friendly", [n for n in e["gods"]["names"][12:18] if n],
              "max sanct", e["gods"]["max_sanctuaries"], " events:", len(e["events"]),
              " disallowed:", [k for k, v in e["allowed"].items() if not v])
        if e["tutorial"]:
            print("    tutorial:", e["tutorial"])


def main():
    args = sys.argv[1:]
    advs = [build(p) for p in paks()]
    if args[:1] == ["--show"]:
        for a in advs:
            if a["id"] == args[1]:
                show(a)
        return
    files = {f"{a['id']}.json": dump(a) for a in advs}
    files["index.json"] = dump(index(advs))
    files["texts.json"] = dump(texts())
    if "--check" in args:
        bad = 0
        for n, s in sorted(files.items()):
            p = os.path.join(OUT, n)
            same = os.path.exists(p) and open(p).read() == s
            bad += not same
            if not same:
                print(f"data/campaign/{n}: DIFFERS")
        print(f"{len(files)} files, {bad} differ")
        sys.exit(1 if bad else 0)
    os.makedirs(OUT, exist_ok=True)
    for n, s in files.items():
        open(os.path.join(OUT, n), "w").write(s)
    print(f"data/campaign: {len(advs)} adventures, {sum(len(s) for s in files.values()) // 1024} KB")


if __name__ == "__main__":
    main()
