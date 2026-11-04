"""An original Zeus saved game (.sav) as our Game (track 1L-5): the tutorials start from Adventures/tutorialNN.sav
(tutorial_load_save 0x005BEBD0 -> game_file_load 0x0050E610), so their start is a converted save.

A .sav is the map container format (tools/mapfile.py) holding the 138/139 save blocks (refs/zeus-poseidon-arm64
formats/sav.md; the ranks below). game_file_load reads every block into its variable (truncating / zero-padding
blocks of an older shape element by element, 0x0050CB80), then rebuilds what is not saved (FUN_00510ED0,
FUN_00494BE0, FUN_00512590) and loads the adventure the save names (FUN_00426700(0x00F2A992), the name from the
live episode record 0x00902FC9) for the later episodes.

Ours, in two layers:
  map_container(path)   the save's grids, scenario block, empire, ... renumbered as a map container (map ranks), so
                        World, TerrainView and the empire builder read a .sav as they read a .map. The terrain image
                        grid (map rank 4) is not in a save (the exe recomputes it): the adventure map's own, and
                        TerrainView recomputes the tiles the city changed.
  load(path)            the Game: the map container + the save's date, treasury, rates, difficulty, scenario (events
                        as they stand, god block, allowed table, tutorial switches, games year), the empire as saved,
                        every building (placed through our own builders, footprint checked against the save's
                        building grid) with its state, the herd animals; companies recomputed from the houses.
What is not converted (docs/campaign-format.md "Tutorials"): walkers on their way (service walkers, carts, traders,
immigrants: our buildings send their own), the message list, the yearly finance history, storage orders.
"""
import copy
import json
import os
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mapfile  # noqa: E402

N = 228
# map rank -> sav rank of the same variable (map table 0x0063CDC0 vs save table 0x0063C2D0; addresses matched)
SAV_OF_MAP = {5: 15, 6: 17, 7: 20, 8: 22, 9: 24, 10: 42, 11: 43, 12: 44, 13: 45, 14: 9, 15: 99, 17: 10, 18: 101,
              19: 102, 20: 104, 21: 8, 22: 109, 23: 111, 24: 112, 25: 7, 26: 114, 27: 120, 28: 122, 29: 128, 30: 129,
              31: 135, 32: 136}
# the save blocks read here (GOG addresses, formats/sav.md)
CITY, YEAR, MONTH, CITIES, SCENARIO, EVENTS, EVENT_COUNT = 4, 5, 6, 7, 9, 13, 14
BUILDING_GRID, TERRAIN, FIGURES, BUILDINGS, DIFFICULTY = 16, 17, 28, 35, 12
CYCLE_STEP, MONTH_DAY, STORAGES, GODS, COMMEM_AVAIL, POP_FLAGS = 37, 38, 81, 122, 116, 58
FORMATIONS, FORM = 31, 0x9C                      # figure_groups 0x00DB7B40, 100 x 0x9C
BREC, FREC, SREC = 0x118, 0x184, 0x10C
DIFFICULTIES = ("VeryEasy", "Easy", "Normal", "Hard", "Impossible")     # g_difficulty 0x00F2A988 (rank 12)

_CACHE = {}


def _i16(b, o):
    return struct.unpack_from("<h", b, o)[0]


def _i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def read(path):
    """(header, {rank: bytes}) of a .sav (cached per path)."""
    key = os.path.abspath(path)
    if key not in _CACHE:
        try:
            hdr, blocks = mapfile.read_file(path)[0]
            assert any(b["rank"] == BUILDINGS for b in blocks)
        except Exception as e:                      # noqa: BLE001
            raise ValueError(f"{path}: not a readable original Zeus save ({type(e).__name__}: {e})") from None
        _CACHE[key] = (hdr, {b["rank"]: b["data"] for b in blocks})
    return _CACHE[key]


def info(path):
    """What the save says about itself: the adventure (live record name 0x00902FC9 = scenario +0x6A1), the episode
    slot (0x00902F78 - 1 -> 0x00F2A7B0, game_file_load), the date (year, month, day of the month 0..15, cycle step
    0..50), the scenario start year (scenario +0, i16), the difficulty."""
    hdr, b = read(path)
    s = b[SCENARIO]
    return dict(version=hdr["version"], adventure=s[0x6A1:0x6A1 + 64].split(b"\0")[0].decode("latin-1"),
                slot=_i32(s, 0x650) - 1, year=_i32(b[YEAR], 0), month=_i32(b[MONTH], 0),
                day=_i32(b[MONTH_DAY], 0), step=_i32(b[CYCLE_STEP], 0), start_year=_i16(s, 0),
                difficulty=DIFFICULTIES[max(0, min(4, _i32(b[DIFFICULTY], 0)))])


def adventure_file(path):
    """The adventure .pak next to the save (Adventures/<name>.pak, FUN_00426700)."""
    return os.path.join(os.path.dirname(path), info(path)["adventure"] + ".pak")


def map_container(path):
    """(hdr, blocks) of the save as a map container (map ranks). The header and the terrain image grid (rank 4)
    come from the adventure's map (container 0, or the colony's for a colony slot): the save does not keep them."""
    hdr, b = read(path)
    pak = adventure_file(path)
    slot = info(path)["slot"]
    idx = 0
    if slot >= 10:                                    # a colony episode: its own map container (0x00F2A7B0)
        a = _campaign(info(path)["adventure"])
        col = next((c for c in a["colonies"] if c["slot"] == slot), None) if a else None
        idx = col["map"] if col else 0
    mhdr, mblocks = mapfile.pak_map(pak, idx)
    mb = {x["rank"]: x for x in mblocks}
    out = [dict(mb[4])]
    for r in sorted(SAV_OF_MAP):
        out.append(dict(rank=r, data=b[SAV_OF_MAP[r]]))
    out.append(dict(rank=16, data=b[EVENT_COUNT] + b[EVENTS]))
    return dict(mhdr), sorted(out, key=lambda x: x["rank"])


def _campaign(aid):
    p = os.path.join(ROOT, "data", "campaign", f"{aid}.json")
    return json.load(open(p)) if os.path.exists(p) else None


# --- the game ---------------------------------------------------------------------------------------------------------

def episode_of(path):
    """The episode record the save plays (data/campaign/<adventure>.json, the save's slot), with what the save
    holds instead of the file's start values: start year, allowed table (scenario +0x408), games year (+0x328), god
    block (rank 122 = g_scenario_gods), tutorial switches (city +0x43AE = 0x00FEAE06, +2 = 0x00FE6A5A); events and
    player city are the save's own (set by load)."""
    inf = info(path)
    hdr, b = read(path)
    a = _campaign(inf["adventure"])
    s = b[SCENARIO]
    ep = None
    if a is not None:
        ep = next((e for e in a["episodes"] if e["slot"] == inf["slot"]), None)
    ep = copy.deepcopy(ep) if ep else dict(slot=inf["slot"], start="new_city", goals=[], goal_count=0)
    ep.setdefault("source", a["source"] if a else os.path.relpath(path, ROOT))
    import build_scenario                               # tools/
    ep.update(start_year=inf["start_year"], funds=_i32(s, 0x20), allowed_raw=list(struct.unpack_from("<100h", s, 0x408)),
              games_year=_i16(s, 0x328), gods=build_scenario.gods(b[GODS]), events=[], player_city=None)
    c = b[CITY]
    if ep.get("tutorial") is not None or (a or {}).get("tutorial"):
        ep["tutorial"] = dict(build_categories=list(c[0x43AE:0x43AE + 11]), world_map_button=c[2])
    return ep


def old_goods(path):
    """Saves before version 0x12F keep the Zeus goods numbering: FUN_00510ED0 renumbers them at load
    (goods_remap_all 0x0050F7E0: events, cities, storages, bays, prices ...), as tools/build_empire.py OLD."""
    return info(path)["version"] < 0x12F


def good_id(path, v):
    import build_empire
    return build_empire.OLD.get(v, 0) if old_goods(path) else v


def events_of(path):
    """The live event records (rank 13, count rank 14) in our scenario format (sim/scenario "The record"): as the
    file record (tools/build_scenario.py record, no fix-ups: the save holds the game's numbering) with the resolved
    values (group +0) and the run-time fields."""
    import build_scenario
    hdr, b = read(path)
    n = _i32(b[EVENT_COUNT], 0)
    E = b[EVENTS]
    out = []
    for i in range(min(n, 150)):
        r = E[i * 124:(i + 1) * 124]
        d = build_scenario.record(r, 99, remap=old_goods(path))
        d["index"] = _i16(r, 0)
        for k in ("item", "amount", "year", "city", "city2"):
            d[k] = d["groups"][k][0]
        d.update(countdown=_i16(r, 0x2E), state=_i16(r, 0x30), active=r[0x32], b33=r[0x33], parent=_i16(r, 0x34),
                 b61=r[0x61], b62=r[0x62], b63=r[0x63], src=_i16(r, 0x64), pitem=_i16(r, 0x66),
                 pamount=_i16(r, 0x68), b74=r[0x74])
        if d["type"] == 2:
            d["landing"] = _i16(r, 0x78)
        out.append(d)
    return out


def load(path, seed=1, difficulty=None):
    """The Game of an original .sav (map name = the save's path, relative to the project when inside it)."""
    from .game import Game
    from . import scenario, systems
    rel = os.path.relpath(os.path.abspath(path), ROOT)
    name = rel if not rel.startswith("..") else os.path.abspath(path)
    inf = info(path)
    ep = episode_of(path)
    g = Game(name, seed, difficulty=difficulty or inf["difficulty"], start=dict(kind="new_city", episode=ep))
    # the scenario as it stands: the save's live events (no resolving at start), the god block of the save
    sc = g.scenario
    evs = []
    for r in events_of(path):
        ev = scenario.blank(r["index"])
        ev.update({k: copy.deepcopy(v) for k, v in r.items() if k not in ("index", "name")})
        evs.append(ev)
    sc.events = evs
    scenario.request_list_rebuild(g)
    _calendar(g, inf)
    hdr, b = read(path)
    c = b[CITY]
    g.city.treasury = _i32(c, 0x0C)
    g.city.tax_rate = _i32(c, 0x08)
    g.city.wage_rate = _i32(c, 0x2C08)
    g.city.sentiment = _i32(c, 0x10)
    g.city.months_in_debt = _i32(c, 0x4824)
    g.sav = dict(source=name, path=path, adventure=inf["adventure"], slot=inf["slot"], ids={}, skipped=[])
    keep_allowed = g.__dict__.pop("allowed", None)
    keep_tut = g.__dict__.pop("tutorial", None)
    try:
        buildings(g, b)
        saved = animals(g, b)
    finally:
        if keep_allowed is not None:
            g.allowed = keep_allowed
        if keep_tut is not None:
            g.tutorial = keep_tut
    # the save's terrain stands (our builders mark sanctuary ground over the whole layout box, clear scrub on extras
    # tiles ...): the grid as saved, without the exe's building bit 0x8 (ours: World.occ) and 0x80000000 (not
    # modeled; the exe's load leaves a few of them, oracle 1L5-tut*)
    g.world.flags = np.frombuffer(b[TERRAIN], "<u4").reshape(N, N) & np.uint32(~(0x8 | 0x80000000) & 0xFFFFFFFF)
    _regrowth(g, b)
    g.city.treasury = _i32(c, 0x0C)                    # the builders spent; the save's treasury stands
    g.year_treasury = _i32(c, 0x2CC4)                  # _DAT_00fe971c: the treasury at the year's start
    g.city.ledger = {}
    _commemorative(g, b)
    systems.roads.rebuild(g)
    for bd in g.buildings.values():
        systems.roads.update_access(g, bd)
    _companies(g, b)                                  # the save's companies (slots, types, members) ...
    systems.military.update(g)                        # ... then as recomputed daily from the houses
    _figure_slots(g, b, saved)                        # the exe's free-id ring after a load
    g.city.population = sum(bd.occupants for bd in g.buildings.values() if bd.kind == "house")
    return g


def _regrowth(g, b):
    """The save's regrowth grid (g_grid_regrowth 0x00C1C648, rank 102) on trees and marble. A tree (terrain 0x1)
    below 255 is a stump (cut by a woodcutter; not a tree for his search 0x004A86E0): ours queues its regrowth
    (g.regrow, walkers.regrow_days from the saved byte; the tree bit stays, walkers.stumps). Marble (0x20000) below 255 is a
    quarry pit (g.quarry, the depth)."""
    from .systems import walkers
    rg = np.frombuffer(b[102], np.uint8).reshape(N, N)
    fl = g.world.flags
    tpd = g.rules["ticks_per_day"]
    ys, xs = np.nonzero(((fl & 0x80001) == 1) & (rg != 255))
    for y, x in zip(ys.tolist(), xs.tolist()):
        g.sd("regrow", []).append((g.tick + walkers.regrow_days(g, int(rg[y, x])) * tpd, x, y))
    ys, xs = np.nonzero(((fl & 0x20000) != 0) & (rg != 255))
    for y, x in zip(ys.tolist(), xs.tolist()):
        g.sd("quarry", {})[(x, y)] = int(rg[y, x])
    g.map_version = getattr(g, "map_version", 0) + 1


def _companies(g, b):
    """The companies as saved (rank 31, figure_groups 0x00DB7B40: +0 in use, +2 banner, +4 figure type 0xB rabble /
    0xC hoplite / 0xD horseman, +0x28 members, +0x2C morale, +0x66 / +0x73 the waver's counters, +0x93 ready): the palace's 1..20 keep their slots and banners (the army dialog's
    rows, oracle 1L5-troopsgo army.bmp); the sanctuary companies 31..34 (cycle_formations_pass_14 0x00567C70) go to
    the god's sanctuary (systems.military.SANCT). Members stand at home (their figures are not converted); the
    daily recount (systems.military.update) then matches the palace companies to the houses."""
    from .systems import military
    from . import gods
    F = b.get(FORMATIONS, b"")
    comps = military.companies(g)
    kinds = {0xB: "rabble", 0xC: "hoplite", 0xD: "horseman"}
    for slot in list(range(1, 21)) + list(military.SANCT):
        o = slot * FORM
        if o + FORM > len(F) or F[o] != 1 or _i16(F, o + 4) not in kinds:
            continue
        n = min(military.PER_COMPANY, F[o + 0x28])
        if slot <= 20:
            comps[slot] = {"type": kinds[_i16(F, o + 4)], "members": n, "banner": F[o + 2],
                           "morale": _i16(F, o + 0x2C), "ready": bool(F[o + 0x93]),     # +0x2C, +0x93
                           "rout": F[o + 0x73], "waver": F[o + 0x66]}                   # the waver's counters
            continue
        god, kind = military.SANCT[slot]
        sb = gods.sanctuary(g, gods.god_id(god))
        if sb is not None:
            comps[slot] = {"type": kind, "members": n, "sanct": god, "home": sb.id, "morale": 100, "ready": True,
                           "banner": F[o + 2]}


def _calendar(g, inf):
    """The save's date: scenario_start_year (year0, the events' years count from it), months since then, the day in
    the month (0x0091EC0C, 0..15) and the cycle step (0x0091EC14, 0..50) as our tick within the month."""
    g.year0 = inf["start_year"]
    g.scenario_year = inf["start_year"]
    g.months0 = (inf["year"] - inf["start_year"]) * 12 + inf["month"]
    g.tick = inf["day"] * g.rules["ticks_per_day"] + inf["step"]


# --- buildings ------------------------------------------------------------------------------------------------------

def records(b):
    """{exe id: dict} of the save's buildings in use (rank 35; buildings.md 'Building record')."""
    B = b[BUILDINGS]
    out = {}
    for k in range(1, len(B) // BREC):
        o = k * BREC
        if not B[o]:
            continue
        r = B[o:o + BREC]
        tile = _i32(r, 0x0C)
        out[k] = dict(id=k, state=r[0], type=_i16(r, 0x10), x=tile % N, y=tile // N, size=r[3],
                      parent=_i16(r, 0x38), next=_i16(r, 0x3A), link=_i16(r, 0xD8), level=_i16(r, 0x12),
                      orient=r[0xAC], raw=r)
    return out


def parts(recs, k):
    """The part chain of root k (+0x3A next)."""
    out, p = [], recs[k]["next"]
    while p and p in recs and len(out) < 400:
        out.append(p)
        p = recs[p]["next"]
    return out


def _footprint(grid, ids):
    ys, xs = np.nonzero(np.isin(grid, list(ids)))
    return set(zip(xs.tolist(), ys.tolist()))


def _keys():
    d = json.load(open(os.path.join(ROOT, "data", "buildings.json")))
    by = {}
    for k, v in d.items():
        by.setdefault(v.get("zeus_id"), k)
    return by


HOUSE_TYPES = range(2, 15)                # 2..8 common (level 0..6), 9..14 elite (level 7..12)
SKIP_TYPES = {59, 61, 66, 67, 68, 69, 70, 71, 72, 73, 134}      # parts: bays, dock house, stalls, corral
AVENUES = {118: 1, 126: 2}


def _real_pieces(key):
    """Layout indices of a monument's building parts (classes < 1000; the extras 1000.. are no buildings): the exe's
    part +0x12 counts these."""
    from .systems import monuments
    return [i for i, p in enumerate(monuments.layouts()[key]["pieces"]) if p[2] < 1000]


def _monument_place(key, r, recs):
    """(x, y, orientation) of a monument from its parts: part +0x12 = layout piece index, at the layout offset
    turned by the orientation (monuments.piece_xy); the anchor every part agrees on."""
    from .systems import monuments
    lay = monuments.layouts().get(key)
    if lay is None:
        return []
    ps = [recs[p] for p in [r["id"]] + parts(recs, r["id"])]
    real = _real_pieces(key)
    out = []
    for o in range(4):
        fake = type("B", (), {})()
        fake.key, fake.x, fake.y, fake.misc = key, 0, 0, {"orient": o}
        anchors = set()
        for q in ps:
            j = _i16(q["raw"], 0x12)
            if not 0 <= j < len(real):
                anchors = None
                break
            dx, dy = monuments.piece_xy(fake, real[j])
            anchors.add((q["x"] - dx, q["y"] - dy))
        if anchors and len(anchors) == 1:
            x, y = anchors.pop()
            out.append((x, y, str(o)))
    return out


def _candidates(key, r, fp, recs=None):
    """(x, y, extra) placements to try for a root, in order."""
    if (key == "palace" or key.startswith("sanctuary_")) and recs is not None:
        return _monument_place(key, r, recs)
    xs = [p[0] for p in fp] or [r["x"]]
    ys = [p[1] for p in fp] or [r["y"]]
    anchors = [(r["x"], r["y"]), (min(xs), min(ys))]
    anchors = list(dict.fromkeys(anchors))
    extras = {"agora": ("left", "down", "right", "up"), "grand_agora": ("v", "h"), "stadium": ("v", "h"),
              "horse_ranch": ("0", "1", "2", "3")}.get(key)
    if key in ("fishing_wharf", "urchin_quay", "trireme_wharf", "dock"):
        extras = ("n", "e", "s", "w")
        anchors = list(dict.fromkeys(anchors + [(x, y) for x, y in fp]))
    if key == "commemorative_monument":
        extras = (f"{r['level']} {r['orient']}",)
    return [(x, y, e) for x, y in anchors for e in (extras or (None,))]


def buildings(g, b):
    """Every root building of the save (state 1/3, no parent) through our builders, ordered by exe id; composite
    roots tried at each candidate placement until our footprint equals the save's (building grid rank 16)."""
    from .game import CommandError
    from . import systems
    recs = records(b)
    grid = np.frombuffer(b[BUILDING_GRID], "<u2").reshape(N, N)
    keys = _keys()
    ids = g.sav["ids"]
    w = g.world
    sanct = {k for k, r in recs.items() if 87 <= r["type"] <= 100 and r["parent"] == 0}
    w.flags &= np.uint32(~0x8 & 0xFFFFFFFF)          # the exe's "building here" terrain bit: ours is World.occ
    g.city.treasury = 10 ** 9
    keep_pos = g.__dict__.get("poseidon")
    g.poseidon = True                                 # the saves hold Ionic / Corinthian columns (Poseidon in ours)
    try:
        _buildings(g, recs, grid, keys, ids, sanct)
        _gardens(g, b)
    finally:
        if keep_pos is None:
            g.__dict__.pop("poseidon", None)
        else:
            g.poseidon = keep_pos
    g.map_version = getattr(g, "map_version", 0) + 1


def _gardens(g, b):
    """Gardens (type 128) are no building records in the exe: the gardens tool paints terrain 0x20 (map-terrain.md 3;
    desirability row 128 from the tile scan, step 37b). Ours keeps them as 1x1 "gardens" buildings (the desirability
    source and play mode's SPR_GARDENS stamps, scene.js gardenStamps), so every free 0x20 tile of the save becomes
    one (before: none, so a converted city lost its gardens' desirability and play mode drew the tiles black: the
    terrain pass leaves 0x20 tiles to the stored image, a General picture; bugs.md 399)."""
    from .game import CommandError
    terr = np.frombuffer(b[TERRAIN], "<u4").reshape(N, N)
    ys, xs = np.nonzero((terr & 0x20) != 0)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if g.world.occ[y, x] or g.world.road[y, x]:
            continue
        try:
            g.build("gardens", x, y)
        except CommandError as err:
            g.sav["skipped"].append((-1, 128, "gardens", f"({x},{y}): {err}"))


def _buildings(g, recs, grid, keys, ids, sanct):
    for k in sorted(recs):
        r = recs[k]
        t = r["type"]
        if r["parent"] or t in SKIP_TYPES or r["state"] not in (1, 3):
            continue
        if r["link"] in sanct:                        # a sanctuary's extras (trees): planted on its completion
            continue
        if t in AVENUES:
            _avenues(g, grid, k, AVENUES[t])
            continue
        if t == 123:                                  # roadblock: one tile, ours a set of road tiles
            rb = g.sd("roadblocks", set())
            rb.add((r["x"], r["y"]))
            continue
        key = keys.get(t)
        if t in HOUSE_TYPES:
            key = "house" if t <= 8 else "elite_house"
        if key is None or key not in g.cat.buildings:
            g.sav["skipped"].append((k, t, "no catalog key"))
            continue
        fp = _footprint(grid, [k] + parts(recs, k))
        nb = _place(g, key, r, fp, recs)
        if nb is None:
            continue
        ids[k] = nb.id
        _state(g, nb, r, recs)


def _ours(g, before):
    return {i for i in g.buildings if i not in before}


def _place(g, key, r, fp, recs):
    from .game import CommandError
    best = None
    cands = _candidates(key, r, fp, recs)
    for x, y, e in cands:
        trial = copy.deepcopy(g) if len(cands) > 1 else g
        before = set(trial.buildings)
        try:
            _build(trial, key, x, y, e)
        except CommandError as err:
            if best is None:
                best = (0, None, str(err))
            continue
        new = _ours(trial, before)
        mine = _footprint(trial.world.occ, new)
        if key == "palace" or key.startswith("sanctuary_"):
            ok = fp <= mine                           # ours occupies the whole layout box
        elif key in ("agora", "grand_agora"):         # the exe's agora also holds its road strip
            ok = mine == {(x_, y_) for x_, y_ in fp if not trial.world.road[y_, x_]}
        else:
            ok = mine == fp
        score = len(mine & fp) / max(1, len(mine | fp))
        if ok:
            if trial is not g:
                _build(g, key, x, y, e)
            return g.buildings[max(_ours(g, before))] if key not in ("agora", "grand_agora") else \
                next(g.buildings[i] for i in _ours(g, before) if g.buildings[i].key == key)
        if best is None or score > best[0]:
            best = (score, (x, y, e), f"footprint {len(mine)} tiles vs {len(fp)}")
    g.sav["skipped"].append((r["id"], r["type"], key, best[2] if best else "no placement"))
    return None


def _bbox(s):
    if not s:
        return None
    xs, ys = [p[0] for p in s], [p[1] for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def _build(g, key, x, y, e):
    spec = g.cat.spec(key)
    if spec["kind"] == "monument":
        return g._monument(key, spec, x, y, e)
    if key == "commemorative_monument":
        v = int(str(e).split()[0])
        from .systems import commemorative
        commemorative.state(g)["available"][v] += 1
    return g.build(key, x, y, e)


def _avenues(g, grid, k, kind):
    """Avenue / boulevard tiles: every tile whose building grid points at the map's one record of the type (avenues.md
    'Model'); our grid = kind << 8 | the exe's draw byte (the tile's draw flags, rank 15)."""
    hdr, blocks = read(g.sav["source"] if os.path.isabs(g.sav["source"]) else os.path.join(ROOT, g.sav["source"]))
    draw = np.frombuffer(blocks[15], np.uint8).reshape(N, N)
    ys, xs = np.nonzero(grid == k)
    for x, y in zip(xs.tolist(), ys.tolist()):
        g.world.avenue[y, x] = kind << 8 | int(draw[y, x])


# per-building state ---------------------------------------------------------------------------------------------------
FOOD_SLOTS = {"wheat": 0x54, "onions": 0x56, "carrots": 0x58, "cheese": 0x5A, "meat": 0x5C, "urchin": 0x5E,
              "fish": 0x60, "oranges": 0x62}
HOUSE_GOODS = dict(FOOD_SLOTS, wine=0x64, olive_oil=0x66, fleece=0x68, armor=0x6A, horses=0x72)
COVERAGE = {"water": 0x77, "healer": 0x78, "philosophy": 0x6D, "athletics": 0x6F, "drama": 0x71,
            "competition": 0x6C}             # service counters (services.md: set to 96, -1 a day)
GOOD_KEYS = ("", "urchin", "fish", "meat", "cheese", "carrots", "onions", "wheat", "oranges", "wood", "bronze",
             "marble", "grapes", "olives", "fleece", "horses", "black_marble", "orichalc", "armor", "sculpture",
             "olive_oil", "wine", "chariot", "silver")


def _state(g, nb, r, recs):
    """The record's state on our building: houses (level = type - 2, occupants +0x1C, goods +0x54..), workers
    (+0x40), risks (+0x46 damage, +0x48 fire), granary food (+0x56 + 2 good), storehouse / post / dock bays (+0x12
    good, +0x3C amount), a sanctuary's pieces (+0x12 piece, +0x58 stage), stall vendors."""
    raw = r["raw"]
    t = r["type"]
    if t in HOUSE_TYPES:
        nb.level = t - 2
        nb.occupants = _i16(raw, 0x1C)
        nb.goods = {k: _i16(raw, o) for k, o in HOUSE_GOODS.items() if _i16(raw, o) > 0}
        nb.coverage = {k: raw[o] for k, o in COVERAGE.items() if raw[o] > 0}
        nb.tax_days = raw[0x4E]                       # tax collector's 50 days (0x004A67C0)
        nb.crime = max(0, _i32(raw, 0xF4))            # unrest (services.md "Crime")
        nb.devolve_count = raw[0x82]                  # devolve counter (housing-evolution.md)
        nb.hunger = min(3, raw[0xCC])                 # months without food (housing.md)
        nb.fed = raw[0x7F] != 0                       # food types eaten last month
        if raw[0x85]:                                 # plague: infected days left (+0x85 flag, +0x100 countdown)
            nb.misc["infected"] = max(1, _i32(raw, 0x100))
    else:
        nb.employees = max(0, _i16(raw, 0x40))
        spec = g.cat.spec(nb.key)
        k = nb.kind
        if k in ("producer", "orchard"):
            nb.progress = _i16(raw, 0x54)             # crop / tree growth 0..1920 (production.md)
        elif k == "workshop":
            nb.progress = _i16(raw, 0x54)
            if _i16(raw, 0x3C) > 0:
                nb.goods[spec["input"]] = _i16(raw, 0x3C)
        elif k == "ranch":
            if _i16(raw, 0x3C) > 0:
                nb.goods[spec["input"]] = _i16(raw, 0x3C)
        elif k in ("gather", "hunt", "fishery", "urchin", "herd", "corral") and _i16(raw, 0x3C) > 0:
            nb.goods[spec["output"]] = _i16(raw, 0x3C)    # stock gathered (+0x3C)
        elif k == "lodge":                            # olives / oranges +0x3C, grapes +0xDC (lodge_receive_fruit)
            for good, o in (("olives" if nb.key == "growers_lodge" else "oranges", 0x3C), ("grapes", 0xDC)):
                if _i16(raw, o) > 0:
                    nb.goods[good] = _i16(raw, o)
    nb.fire_risk = max(0, _i16(raw, 0x48))
    nb.damage_risk = max(0, _i16(raw, 0x46))
    if t == 57:
        nb.goods = {GOOD_KEYS[i]: _i16(raw, 0x56 + 2 * i) for i in range(1, 9) if _i16(raw, 0x56 + 2 * i) > 0}
    elif t in (58, 62, 60):
        goods = {}
        for p in parts(recs, r["id"]):
            q = recs[p]
            if q["type"] == 59 and _i16(q["raw"], 0x12) > 0:
                k = GOOD_KEYS[good_id(g.sav["path"], _i16(q["raw"], 0x12))]
                goods[k] = goods.get(k, 0) + _i16(q["raw"], 0x3C)
        nb.goods = {k: v for k, v in goods.items() if v > 0}
    if nb.kind == "monument" and "pieces" in nb.misc:
        _monument_state(g, nb, r, recs)
    if t in (63, 64):
        from .systems import agora
        for p in parts(recs, r["id"]):
            q = recs[p]
            key = _keys().get(q["type"])
            s = agora.stall_at(g, q["x"], q["y"])
            if s is None or key in (None, "empty_stall"):
                continue
            if s.key == "empty_stall":
                agora.open_stall(g, key, q["x"], q["y"])
            s.employees = max(0, _i16(q["raw"], 0x40))
            g.sav["ids"][p] = s.id


def _monument_state(g, nb, r, recs):
    from .systems import monuments
    stage = {}
    real = _real_pieces(nb.key)
    for p in [r["id"]] + parts(recs, r["id"]):
        q = recs[p]
        j = _i16(q["raw"], 0x12)
        if 0 <= j < len(real):
            stage[real[j]] = _i16(q["raw"], 0x58)
    for p in nb.misc["pieces"]:
        if p["i"] in stage:
            p["s"] = min(p["n"], max(0, stage[p["i"]]))
    # the save's elevation grid holds the terraces: refresh_piece_image 0x0053D300 writes each piece's (and extra's)
    # layout elevation + the root's base +0x6C into it at placement. Ours keeps the ground (the base) there and raises
    # the pieces by their layout elevation when drawing (monuments.js), as for a monument built in ours (bugs.md 400)
    base = r["raw"][0x6C]
    lay = monuments.layouts()[nb.key]
    for i, pc in enumerate(lay["pieces"]):
        px, py = monuments.piece_xy(nb, i)
        n = monuments.size(pc[2])
        g.world.elev[py:py + n, px:px + n] = base
    nb.misc["built"] = monuments.progress(nb)
    if not r["raw"][0xDA] or nb.key == "palace":       # +0xDA monument unfinished (cleared on completion)
        for p in nb.misc["pieces"]:
            p["s"] = p["n"]
        nb.misc.update(complete=True, built=100, completed=[g.year, g.month])
        if nb.key.startswith("sanctuary_"):
            nb.misc["activity"] = 22
            monuments.extras_complete(g, nb)


def animals(g, b):
    """The herd animals (sheep 49, goats 50, boars 51; figure +0x0A type, +0x20 tile); a boar keeps its herd (figure
    +0x60, the herd formation's point: _herds)."""
    from .systems import walkers
    herd = _herds(g, b)
    F = b[FIGURES]
    out = {}
    for k in range(1, len(F) // FREC):
        o = k * FREC
        t = F[o + 0x0A]
        if t not in (49, 50, 51) or not F[o + 0x0E]:
            continue
        tile = _i32(F, o + 0x20)
        before = set(g.walkers)
        a = walkers.spawn_animal(g, {49: "sheep", 50: "goat", 51: "boar"}[t], tile % N, tile // N)
        if t == 51:
            a.origin = herd.get(_i16(F, o + 0x60), a.origin)
        out.update({wid: k for wid in set(g.walkers) - before})
    return out


def _herds(g, b):
    """The boar herds as saved (formations_pass 0x004DF570 refills only herd formations: in use, +0x42 == 0, +0x94 ==
    0, +0x69 == 1; the herd point +0x36 / +0x38 (logical), the refill count +0x75). FUN_004E0160 makes them at map
    start only, so a prey point with no herd formation in the save never gets boars again (oracle 1B-inv-city:
    tutorial15.sav has none, no boar in 2288 ticks; ours made 4 herds of 7 from forest-edge points, one of them where
    the invaders met the rabble). Returns {formation: raw point}; sets systems.wild's herd_timers (None: no herd)."""
    from .systems import wild
    F = b.get(FORMATIONS, b"")
    ox, oy = g.world.origin
    timers = g.sd("herd_timers", {})
    herd = {}
    for i in range(1, len(F) // FORM):
        o = i * FORM
        if F[o] != 1 or F[o + 0x42] or _i32(F, o + 0x94) or F[o + 0x69] != 1:
            continue
        p = (_i16(F, o + 0x36) + ox, _i16(F, o + 0x38) + oy)
        herd[i] = p
        timers[p] = F[o + 0x75]
    for p in wild.prey_points(g):
        timers.setdefault(tuple(p), None)
    return herd


def _figure_slots(g, b, saved):
    """sav_load's figures_rebuild_free_list 0x004D9F40: the free ring is rebuilt at every load, 1999 down to 1, the
    ids whose figure has state 0; the save's figures keep their ids. Ours: the herd animals keep their save ids, ours'
    other walkers made at the import (none of them the save's) take the ring's head in their order. So the figures
    made after a load get descending ids (oracle 1B-inv-city: the invaders 1883, 1881, .., 1828), which
    formations_refresh turns into reversed slots (sim/military/morale.refresh)."""
    from collections import deque
    from .model import SLOTS
    F = b[FIGURES]
    used = {k for k in range(1, min(SLOTS, len(F) // FREC)) if F[k * FREC + 0x0E]}
    W = g.walkers
    ring = deque(s for s in range(SLOTS - 1, 0, -1) if s not in used)
    for wid, w in W.items():
        if wid in saved:
            w.fslot = saved[wid]
    for w in sorted((w for wid, w in W.items() if wid not in saved), key=lambda w: w.fslot):
        w.fslot = ring.popleft()
    W.free, W.over = ring, SLOTS


def _commemorative(g, b):
    """Monuments waiting to be placed (0x00665CC8, rank 116) and the population milestones met (0x00FD37C4..CD,
    rank 58); the happy months (city +0x29BC)."""
    from .systems import commemorative
    s = commemorative.state(g)
    av = b[COMMEM_AVAIL]
    s["available"] = [av[v] if v < len(av) else 0 for v in range(commemorative.VARIANTS)]
    fl = b[POP_FLAGS]
    s["pop_done"] = [n for k, n in enumerate(commemorative.POP_MESSAGES) if k < len(fl) and fl[k]]
    s["happy_months"] = _i32(b[CITY], 0x29BC)
