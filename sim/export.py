"""JSON snapshots of the game state for the viewer (viewer/index.html)."""
import json

import numpy as np

from .render import TERRAIN_CH
from .systems import economy, finance, housing, monuments, commemorative, risk
from .systems.walkers import GATHERERS, MIL_ROLES
from . import reports, scenario, alerts, allowed

_TERRAIN_CODE = {k: v for k, v in TERRAIN_CH.items()}


def terrain_string(g):
    """One character per tile, rows joined: "=" road, else _TERRAIN_CODE[world.kind] (the same rules, in numpy: the
    live server takes it with every building snapshot, and the per-tile loop cost ~15 ms there, ~45 ms on a small
    cloud machine, under the lock; bugs.md 482)."""
    from .world import OFFMAP, WATER, CLIFF, WALL, ROCK, MARBLE, TREE, RUBBLE, MEADOW, BEACH
    w = g.world
    f = w.flags.astype(np.int64)
    c = _TERRAIN_CODE
    ore = f & 0x300000
    rock = np.where(f & MARBLE, ord(c["marble"]), np.where(ore == 0x100000, ord(c["copper"]),
                                                          np.where(ore == 0x200000, ord(c["silver"]), ord(c["rock"]))))
    out = np.select([f & OFFMAP != 0, f & WATER != 0, f & CLIFF != 0, f & WALL != 0, f & ROCK != 0, f & TREE != 0,
                     f & RUBBLE != 0, f & (MEADOW | BEACH) != 0],
                    [ord(c["offmap"]), ord(c["water"]), ord(c["cliff"]), ord(c["wall"]), rock, ord(c["tree"]),
                     ord(c["rubble"]), ord(c["meadow"])], ord(c["land"]))
    out = np.where(w.road != 0, ord("="), out).astype(np.uint8)
    return out.tobytes().decode("ascii")


def _halls(g):
    from . import heroes
    return heroes.hall_menu(g)


def _messages(g):
    """The last 30 messages, plus older pop-up ones among the last 300: play mode no longer pauses while a window is
    open (ours, bugs.md 317/320), so a burst of lines must not push a waiting pop-up out before it opens."""
    ms = g.city.messages
    keep = [(t, m) for i, (t, m) in enumerate(ms[-300:]) if i >= len(ms[-300:]) - 30 or getattr(m, "meta", {}).get("popup")]
    return [dict(tick=t, text=str(m), **getattr(m, "meta", {})) for t, m in keep]


def snapshot(g, with_terrain=True):
    c = g.city
    hs = [b for b in g.buildings.values() if b.kind == "house"]
    levels = [0] * len(g.cat.houses)
    for b in hs:
        if b.occupants:
            levels[b.level] += 1
    stocks = {}
    for b in g.buildings.values():
        if b.kind == "storage" and b.key != "endless_warehouse":
            for k, v in b.goods.items():
                if v:
                    stocks[k] = stocks.get(k, 0) + v
    problems = {}
    for b in g.buildings.values():
        if b.reason and b.reason != "top level":
            problems.setdefault(b.reason, 0)
            problems[b.reason] += 1
    snap = dict(
        tick=g.tick, date=g.date(), map=g.map_name, size=int(g.world.flags.shape[0]),
        climate=risk.climate(g),                    # scenario byte 0x3D8 (minimap enemy colour, 0x00454980)
        entry=list(g.world.entry), exit=list(g.world.exit),
        city=dict(treasury=c.treasury, population=c.population, sentiment=c.sentiment,
                  tax=c.tax_rate, wage=c.wage_rate, workforce=c.workforce, employed=c.employed,
                  unemployed=c.unemployed, migration=c.migration, labor_jobs=getattr(g, "labor_jobs", {}), last_month=c.last_ledger,
                  vacancies=sum(max(0, housing.capacity(g, b) - b.occupants - b.pending) for b in hs if b.access),
                  sentiment_parts=finance.sentiment_parts(g)),
        house_levels=dict(zip([h["name"] for h in g.cat.houses], levels)),
        houses_total=len(hs), stocks=stocks, goods_list=goods_list(g), surplus=getattr(g, "surplus", {}), problems=problems,
        buildings=[_building(g, b) for b in g.buildings.values()] + avenue_entries(g),
        walkers=walker_list(g),
        roadblocks=sorted(getattr(g, "roadblocks", ())),
        # Aesthetics > Monuments (submenu 22): the granted variants waiting [v, count, name 198:v], menu order 0x005F41A0
        monuments_available=commemorative.menu(g),
        # Hero's Hall (submenu 23): [hero, name] of the halls the menu lists (sim/heroes hall_menu, 0x004FA620)
        halls_available=_halls(g),
        history=g.history,
        messages=_messages(g),
        offers=_offers(g),                         # the open accept/postpone/decline dialogs (sim/empire/offers.py)
        events=scenario.export(g),                 # the episode's records (sim/scenario); the exe shows them only
                                                   # through the Overview's request list (live /advisor 0) and
                                                   # their messages: play mode reads both from there
        reports=reports.all_reports(g),
        requests=scenario.request_rows(g),         # the Overview page's request rows (0x005B6F00: the first 3)
    )
    ep = episode_export(g)
    if ep is not None:
        snap["episode"] = ep
    if with_terrain:
        snap["terrain"] = terrain_string(g)
    return snap


def episode_export(g):
    """An episode game's switches for play mode (None in open play): the buildings its build menus leave out
    (sim/allowed.py, buildings_availability 0x00402B80), the tutorial's build categories (0x00FEAE06[11], the
    control panel's 11 page buttons) and world map button (0x00FE6A5A), the episode's slot and start kind."""
    from . import allowed
    if allowed.table(g) is None:
        return None
    return dict(unavailable=allowed.unavailable(g), tutorial=g.__dict__.get("tutorial"),
                **(g.__dict__.get("episode") or {}))


def _offers(g):
    from . import empire
    return empire.offers_export(g)


def avenue_entries(g):
    """Avenue/boulevard tiles as 1x1 pseudo buildings (id -(tile+1)) so viewers can show and click them
    (they are not buildings in the sim: systems/avenues.py). Presentation only."""
    from .systems import avenues
    n = g.world.flags.shape[1]
    return [dict(id=-(y * n + x + 1), key=k, kind="avenue", x=x, y=y, size=1, w=1, h=1, road=bool(r), level=0,
                 occupants=0, employees=0, burning=0, goods={}, coverage={}, reason="",
                 desirability=int(g.world.des[y, x]))
            for x, y, k, r in avenues.tiles(g)]


def _building(g, b):
    d = dict(id=b.id, key=b.key, kind=b.kind, x=b.x, y=b.y, size=b.size,
             w=b.misc.get("w", b.size), h=b.misc.get("h", b.size),
             built=b.misc.get("built"),
             level=b.level, occupants=b.occupants, employees=b.employees, burning=risk.on_fire(g, b),
             capacity=housing.capacity(g, b) if b.kind == "house" else 0,
             goods={k: v for k, v in b.goods.items() if v}, reason=b.reason,
             desirability=b.desirability, coverage=dict(b.coverage),
             growth=(b.progress * 100 // g.rules["farm_growth_max"]) if b.kind in ("producer", "orchard") else None,
             crop=g.cat.spec(b.key).get("output") if b.kind in ("producer", "orchard") else None,
             anim=None if b.kind == "house" else economy.anim_state(g, b))
    if "variant" in b.misc:                       # water park picture variant (R key, bugs.md 136)
        d["variant"] = b.misc["variant"]
        if b.key == "commemorative_monument":      # god statue facing: Building+0xAC (docs/play/monuments.md 9)
            d["orient"] = b.misc.get("orient", 0)
    if b.key == "heroes_hall":                     # sim/heroes: the hall's hero (statue) and whether he is about
        from .heroes import heroes as hh
        d["hero"] = b.misc.get("hero", 0)
        d["anim"] = "work" if hh.figure(g, d["hero"]) is not None else None
    if b.kind == "monument" and "pieces" in b.misc:
        d["pieces"] = monument_pieces(b, g)
        d["orient"] = b.misc.get("orient", 0)      # placement orientation (saves before it: 0)
    if b.kind != "monument" and "orient" in b.misc and b.key in ("fishing_wharf", "urchin_quay", "dock", "trireme_wharf"):
        d["orient"] = b.misc["orient"]             # shore building water side (systems/shore.py, bugs.md 131)
        if "pier" in b.misc:
            d["pier"] = list(b.misc["pier"])       # the dock's 2x2 pier anchor
    act = shore_act(g, b)
    if act:
        d["act"] = act                             # play mode: which per-type loop (docs/play/buildings.md 7c)
    if b.key == "horse_ranch" and "corral" in b.misc:
        d["corral"], d["orient"] = list(b.misc["corral"]), b.misc.get("orient", 0)   # 4x4 corral (bugs.md 134)
    if b.kind == "stall" and b.key != "empty_stall":
        d["stocked"] = stall_stocked(g, b)
    info = info_extra(g, b)
    if info:
        d["info"] = info
    ov = overlay_extra(g, b)
    if ov:
        d["ov"] = ov
    return d


def shore_act(g, b):
    """Presentation (city_draw's per-type handlers): "trade" while a ship trades at this dock (dock_trade_anim
    Building+0xE0, set by figure_trade_ship_update), "unload" while a fishing wharf's boat is moored unloading
    (action 10) or an urchin quay's collector unloads (goods_0, 200 ticks), else None."""
    if b.key == "dock":
        return "trade" if any(w.role == "ship" and w.target == b.id and w.state == "trade" for w in g.walkers.values()) else None
    if b.key == "fishing_wharf":
        return "unload" if any(g.walkers[i].role == "boat" and g.walkers[i].state == "unload" for i in b.walkers if i in g.walkers) else None
    if b.key == "urchin_quay":
        return "unload" if any(g.walkers[i].role == "diver" and g.walkers[i].state == "rest" for i in b.walkers if i in g.walkers) else None
    return None


def stall_stocked(g, s):
    """Presentation (bugs.md 130): the original draws a stall's goods picture while its agora holds the stall's
    good (city_draw 0x00459553 -> 0x0040ABF0, vendor_agora_stock != 0; food = any food), and its vendor person
    when the stall also has workers. True / False."""
    from .systems import agora
    a = agora.agora_of(g, s)
    if a is None:
        return False
    good = g.cat.spec(s.key).get("goods")
    return (agora.food_total(g, a) if good == "food" else a.goods.get(good, 0)) > 0


def overlay_extra(g, b):
    """Map overlays (play mode, viewer/play/overlays.js; docs/play/pages.md): risks, and the house values the
    original's overlay columns read (unrest, tax coverage, culture points, ate, infected). Read only."""
    d = {}
    if b.fire_risk or b.damage_risk:
        d["risk"] = [b.fire_risk, b.damage_risk]
    if b.kind == "house" and b.occupants:
        d.update(unrest=b.crime, tax=b.tax_days, culture=housing.culture(g, b), fed=bool(b.fed),
                 infected=b.misc.get("infected", 0))
    return d


# --- info window extras (play mode, viewer/play/info.js; docs/play/info.md) --------------------------
# Presentation only: plain values the original's building info window shows that the fields above lack.

def _house_code(g, b):
    """The house's state as the original's evolve_reason (0x00484660 family; the panel 0x0057F4E0 shows
    text 127:(36+code)): 0 devolving (appeal), 1..9 devolving for lack of water/culture/food/(stadium)/
    wine/fleece/oil/horses/armor, 10 top level, 12 can't evolve (appeal), 13..21 can't evolve for lack of
    water..armor, 22 evolving. Our sim's rules (housing.update), read without changing anything."""
    elite = housing.is_elite(b)
    top = housing.ELITE_TOP if elite else housing.COMMON_TOP
    h = g.cat.houses[b.level]

    def code(need, base):
        if not need: return None
        for i, k in enumerate(("water", "culture", "food", "", "wine", "fleece", "olive_oil", "horses", "armor")):
            if k and need.startswith(k):
                return base + 1 + i
        return base
    if b.level in (housing.ELITE_LOT, housing.ELITE_DEVOLVED):
        c = code(housing.missing(g, b, housing.ELITE_FIRST), 12)
        return 22 if c is None else c
    need_now = housing.missing(g, b, b.level)
    dv, ev = housing.des_gate(g, h)                # Aphrodite active: both - 10 (house_param 0x00433D80)
    if need_now or b.desirability <= dv:
        return code(need_now, 0) or 0
    if b.level >= top:
        return 10
    if b.desirability < ev:
        return 12
    c = code(housing.missing(g, b, b.level + 1), 12)
    return 22 if c is None else c


def goods_list(g):
    """Resources the city can have: the original lists these in storage windows (g_goods_list from
    rebuild_goods_lists 0x005BAAF0: goods the scenario's city can produce (0x00460B40), partners sell,
    gods/tribute give, or held): sim/allowed.py goods_list in a game with an allowed table (episodes, the original's
    open plays). Ours, sandbox_open (no table, every building allowed): every good some building produces, plus
    anything held."""
    if allowed.table(g) is not None:
        return allowed.goods_list(g)
    have = {s["output"] for s in g.cat.buildings.values() if isinstance(s, dict) and s.get("output")}
    for b in g.buildings.values():
        have.update(k for k, v in b.goods.items() if v)
        out = g.cat.spec(b.key).get("output")
        if out:
            have.add(out)
    from .empire.model import GOOD_IDS
    return sorted((k for k in have if k in g.cat.resources), key=lambda k: (GOOD_IDS.get(k, 99), k))   # goods order


def info_extra(g, b):
    k = b.kind
    if k == "house":
        return dict(code=_house_code(g, b), road=b.access is not None, taxed=b.tax_days > 0, unrest=b.crime,
                    room=housing.capacity(g, b) - b.occupants, food=sum(b.goods.get(f, 0) for f in g.cat.foods),
                    food_types=g.cat.houses[b.level]["food_types"],
                    tax_month=int(g.city.tax_rate * b.occupants * g.cat.houses[b.level]["tax_multiplier"] * 2 / 100 * 50 / 100)
                    if b.tax_days > 0 else 0)          # finance.month_end's per-house share
    d = {}
    if b.access is None and g.cat.spec(b.key).get("employees"):
        d["road"] = False
    if b.reason.startswith("no workers can reach"):
        d["labor"] = False
    if b.misc.get("off"):
        d["off"] = True
    if k == "storage":
        d.update(orders=dict(b.misc.get("orders", {})), limits=dict(b.misc.get("limits", {})))
    elif k == "workshop":
        d["progress"] = b.progress * 100 // g.rules["workshop_progress"]
    elif k == "orchard":
        d["ripe"] = bool(b.ripe)
    elif k == "agora":
        from .systems import agora
        st = []
        for s in agora.stalls(g, b):
            ws = [g.walkers[w] for w in s.walkers if w in g.walkers]
            st.append(dict(key=s.key, employees=s.employees, need=g.cat.spec(s.key)["employees"],
                           buying=any(w.role == "buyer" for w in ws), reason=s.reason))
        ped = [g.walkers[w] for w in b.walkers if w in g.walkers and g.walkers[w].role == "peddler"]
        d.update(stalls=st, peddler=bool(ped), returning=bool(ped and ped[0].returning))
    elif k == "monument" and "pieces" in b.misc and not b.misc.get("complete") and b.key != "palace":
        d["build"] = monuments.window(g, b)
    elif k == "monument" and b.key.startswith("sanctuary_"):
        d["activity"] = b.misc.get("activity", 0)  # +0x32 (set to 22 on completion; sacrifices: gods module)
        from . import gods
        i = gods.god_of(b)
        if i in (0, 3):                            # Consult Oracle / Oracle Unavailable (oracle_consult(1, 1))
            from .gods import oracle
            d["oracle"] = oracle.available(g, i)
    elif k == "tower":                         # tower window (sim/military, FUN_0057A3E0)
        from .military import defences
        d["tower"] = defences.tower_window(g, b)
    elif k == "shipyard":                      # trireme wharf window (sim/military, FUN_00583C60)
        from .military import navy
        d["wharf"] = navy.wharf_window(g, b)
    elif k == "hall":                          # Hero's Hall info window (sim/heroes, FUN_0057C720)
        from . import heroes
        d["hall"] = heroes.hall_info(g, b)
    if b.walkers and k not in ("agora",):
        d["out"] = sum(1 for w in b.walkers if w in g.walkers and g.walkers[w].role != "cart")
    return d


def monument_pieces(b, g=None):
    """Every layout piece of a monument as [dx, dy, class, elevation, stage, stages]: plain state for the
    play-mode renderer (docs/play/monuments.md). (dx, dy) from the layout box's min corner; stage = work
    stages done (the original's piece stage), complete when stage >= stages; pieces the sim does not
    build (palace parts, access pads, extras >= 1000) are [.., 0, 0]."""
    lay = monuments.layouts()[b.key]
    built = iter(enumerate(b.misc["pieces"]))    # monuments.create keeps the pieces with stages, in layout order
    out = []
    for dx, dy, c, e in lay["pieces"]:
        if monuments.stages(c, e) or c in monuments.BACKS:
            i, p = next(built)
            out.append([dx, dy, c, e, p["s"], p["n"]])
            t0 = g is not None and c in monuments.CONAN and p["s"] == 1 and monuments.carving(g, b, i)
            if t0 is not None and t0 is not False:
                out[-1].append(t0)                # [6]: a large statue being carved since tick t0 (monuments.CONAN)
        else:
            out.append([dx, dy, c, e, 0, 0])
    return out


def followers(g, w):
    """Presentation: how many vendor assistants (figure 47) the original would show trailing an agora
    stall's buyer: one per load carried home (storage-distribution.md part B, buyer_take_food 0x004CF570).
    Our sim folds them into the buyer, so this is only drawn (play client), never simulated."""
    if w.role != "buyer" or w.amount < 100:
        return 0
    home = g.buildings.get(w.home)
    return min(8, w.amount // 100) if home is not None and home.kind == "stall" else 0


def walker_anim(g, w):
    """Melee state for the play client (crime.melee, services.md §6.1), 0 when walking:
    [kind "fight"|"die", t0, end, face_dx, face_dy, back_dx, back_dy, hits_t0, foe_role, mover].
    back = towards the tile it came from (fighters stand short of the tile centre, on their own side);
    a vandal at work also plays the fight animation (fig_handler_vandal 0x004B6A00, action 10).
    Herders and their animals: herder_look ("work" with a block name, "hidden", "shorn")."""
    h = monuments.look(g, w)                  # artisan at a monument piece: "build" / "wait" (systems/monuments.py)
    if h is None and w.role in MIL_ROLES:     # soldiers, invaders, wolves, sentries, arrows (sim/military)
        from . import military
        h = military.look(g, w)
    if h is None and w.role in ("monster", "hero"):   # sim/heroes
        from . import heroes
        h = heroes.look(g, w)
    if h is None and w.role in ("god", "priest", "god_bolt", "entranced", "god_helper"):   # sim/gods
        from . import gods
        h = gods.look(g, w)
    if h is None and w.role == "contestant":  # games contestant waiting its timer: hidden (systems/games.py)
        from .systems import games
        h = games.look(g, w)
    if h is None:
        h = herder_look(g, w)
    if h is None:
        h = grower_look(g, w)
    if h is None:
        h = gatherer_look(g, w)
    if h is None:
        h = hunt_look(g, w)
    if h is not None:
        return h
    if w.anim or w.state == "vandalizing":
        p = w.prev or (w.x, w.y)
        bx, by = (p[0] > w.x) - (p[0] < w.x), (p[1] > w.y) - (p[1] < w.y)
        if not w.anim:
            return ["work", w.next_move - 51, w.next_move, 0, 0, 0, 0, 0, "", False]
        f = w.face or (0, 0)
        foe = g.walkers.get(w.foe)
        end = w.busy_until if w.anim == "fight" else w.anim_t0 + 128
        out = [w.anim, w.anim_t0, end, f[0], f[1], bx, by, w.hits_t0, foe.role if foe else "", w.mover]
        cp = w.__dict__.get("close_p")
        if w.anim == "fight" and cp is not None:      # sim/military/units.start_fight: [10] none, [11] its tile progress
            out += [None, list(cp), w.__dict__.get("ctr_ref")]   # [p, heading] (the closing-in), [12] the anim counter
        return out                                    # it fights on from (a walk tick; None = 0)
    return 0


HERD_WORK = {"shepherd": "shear", "goatherd": "milk"}   # work blocks in data/play/walkers.json


def herder_look(g, w):
    """Herding (production.md "Herding"), as the original draws it, in walker_anim's record:
    - shearer / milker at the animal (figure_shepherd 0x004B6CF0 action 0xD, 20 ticks): kind "work",
      slot 8 = the work block ("shear": SprMain group 70, 12 frames, 1 per tick, the sheep is in the
      shepherd's sprite; "milk": group 39, 8 frames); a tending herder on guard (action 8, 120 ticks):
      "guard" (group 72 / goatherd 41, 10 frames);
    - "hidden": the original hides (Figure+0x65) an animal while it is shorn / milked (action 9) and a
      herder still waiting inside the farm before it sets out (action 0xB / 6);
    - "shorn": a sheep with ready_level < 100 is drawn with the shorn set (figure_sheep 0x004BC380).
    None when not a herding case."""
    r = w.role
    if w.anim:                                # melee / dying: walker_anim's own record
        return None
    if r in HERD_WORK:
        if w.state == "work":
            blk = "guard" if w.task == "tend" else HERD_WORK[r]
            return ["work", w.anim_t0, w.next_move, 0, 0, 0, 0, 0, blk, False]
        if w.state == "go" and not w.arrived:
            return ["hidden", 0, 0, 0, 0, 0, 0, 0, "", False]
        return 0
    if r in ("sheep", "goat") and w.state == "held":
        return ["hidden", 0, 0, 0, 0, 0, 0, 0, "", False]
    if r == "sheep" and w.ready < 100:
        return ["shorn", 0, 0, 0, 0, 0, 0, 0, "", False]
    return None


GATHER_WORK = {"stonecutter": "cut", "miner": "mine", "woodcutter": "chop",   # work blocks in data/play/walkers.json
               "diver": "dive"}         # urchin collector at its mooring: actions 7/8/9 (tools/play_diver.py)


def marble_facing(g, x, y):
    """Which way a stonecutter on marble tile (x, y) swings (bugs.md 112). The exe faces him toward the tile in
    the shared search-result globals 0x00F13944/40 at his arrival (figure_miner 0x004C1310 action 7 ->
    0x0058D1F0), which any road/route search in the city overwrites: in practice an arbitrary direction (oracle:
    direction 2 for both stonecutters of the working city). We face him into the deposit instead: the sum of the
    offsets to the marble tiles of the 5x5 around him (untouched marble weighs more than pits), rounded to one
    of the 8 directions; direction 2 (tile x+1) when it cancels out."""
    fl, q = g.world.flags, getattr(g, "quarry", {})
    n = fl.shape[0]
    vx = vy = 0.0
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            xx, yy = x + dx, y + dy
            if (dx or dy) and 0 <= xx < n and 0 <= yy < n and fl[yy, xx] & 0x20000:
                wgt = (1.0 + q.get((xx, yy), 255) / 255.0) / (dx * dx + dy * dy)
                vx, vy = vx + dx * wgt, vy + dy * wgt
    if abs(vx) < 1e-6 and abs(vy) < 1e-6:
        return 1, 0
    import math
    a = round(math.atan2(vy, vx) / (math.pi / 4)) % 8          # 0 = +x, 2 = +y
    return ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))[a]


def hunt_look(g, w):
    """Hunting (figure_hunter 0x004BE260, figure_boar 0x004BD030; production.md "Hunter handler states"), in
    walker_anim's record:
    - hunter shooting (action 0xD, 12 ticks): "work" block "hunt" (SprMain group 237, 12 frames x 8 dirs, 1 per
      tick), facing the boar; butchering on the carcass (action 8, 13 ticks): block "butcher" (group 238, frame =
      ticks since it began, no direction);
    - the boar while shot at: "work" block "stand" (group 209, the passive set, facing the hunter); its carcass
      (action 10): kind "carcass" = the die group 207, frame min(ticks since the shot, 7), then frame 7 held."""
    if w.anim:
        return None
    if w.role == "hunter" and w.state == "work":
        if w.task == "strike":
            f = w.face or (0, 0)
            return ["work", w.anim_t0, w.next_move, f[0], f[1], 0, 0, 0, "hunt", False]
        if w.task == "butcher":
            return ["work", w.anim_t0, w.next_move, 0, 0, 0, 0, 0, "butcher", False]
    if w.role in ("boar", "deer"):
        if w.state == "struck":
            f = w.face or (0, 0)
            return ["work", w.anim_t0, w.anim_t0 + 12, f[0], f[1], 0, 0, 0, "stand", False]
        if w.state == "carcass":
            return ["carcass", w.anim_t0, w.anim_t0 + 500, 0, 0, 0, 0, 0, "", False]
    return None


def gatherer_look(g, w):
    """Stonecutter / miner / woodcutter at work (state "work"), in walker_anim's record: kind "work", slot 8 =
    the work block, 1 frame per tick (figure_miner 0x004C1310 action 8: SprMain group 224 marble, 10 frames;
    46 copper, 79 silver; figure_wood_cutter 0x004BF060: 12 frames; production.md "Quarrying and mining").
    Facing: a miner looks at the rock; a stonecutter stands on the marble and faces the deposit (marble_facing);
    a woodcutter keeps the heading of his last step (prev_direction) or looks at his tree."""
    blk = GATHER_WORK.get(w.role)
    if blk is None or w.anim:
        return None
    home = g.buildings.get(w.home)
    silver = w.role == "miner" and home is not None and g.cat.spec(home.key).get("output") == "silver"
    if w.role == "miner" and w.state == "pause":
        # figure_miner action 0xD: 25 ticks (finish_work schedules them), group 44 / 77 + timer / 2, no direction
        # (tools/play_miner_pause.py)
        return ["work", w.next_move - 25, w.next_move, 0, 0, 0, 0, 0, "pause_silver" if silver else "pause", False]
    if w.state != "work":
        return None
    if silver:
        blk = "mine_silver"                    # silver set (group 79); bronze is the role's default
    if w.role == "stonecutter":
        fx, fy = marble_facing(g, w.x, w.y)
    else:
        tx, ty = w.target_tile or (w.x, w.y)
        fx, fy = (tx > w.x) - (tx < w.x), (ty > w.y) - (ty < w.y)
        if not (fx or fy) and w.prev:
            fx, fy = (w.x > w.prev[0]) - (w.x < w.prev[0]), (w.y > w.prev[1]) - (w.y < w.prev[1])
    return ["work", w.anim_t0, w.next_move, fx, fy, 0, 0, 0, blk, False]


def grower_look(g, w):
    """Grower (figure 5, figure_grower 0x004AECF0; docs/play/walkers.md "Growers"), in walker_anim's record.
    The original picks the sprite set by the kind of the grower's tree (orange tree -> PoseidonImps), so:
    - at the tree (state "work"): kind "work", slot 8 = "tend_<fruit>" (action 8, SprMain group 105 grapes /
      106 olives) or "pick_<fruit>" (action 0xC, group 107 / 108), 10 frames x 8 dirs, 1 frame per tick;
      face = towards the tree (the original stands on the tree tile and keeps its last step's heading);
    - otherwise "tree" with slot 8 = the fruit, for the walk set (no carry sprite: action 0xD, walking home
      with the fruit, uses the plain walk group 103).
    None for other roles and for melee / dying."""
    if w.role != "grower" or w.anim:
        return None
    t = g.buildings.get(w.target)
    if t is None:
        home = g.buildings.get(w.home)
        trees = g.cat.spec(home.key).get("trees") if home is not None else None
        key = trees[0] if trees else None
    else:
        key = t.key
    fruit = (g.cat.spec(key).get("output") if key else None) or w.good or "olives"
    if w.state == "work":
        tx, ty = w.target_tile or (w.x, w.y)
        fx, fy = (tx > w.x) - (tx < w.x), (ty > w.y) - (ty < w.y)
        blk = ("pick_" if w.task == "pick" else "tend_") + fruit
        return ["work", w.anim_t0, w.next_move, fx, fy, 0, 0, 0, blk, False]
    return ["tree", 0, 0, 0, 0, 0, 0, 0, fruit, False]


def carried(g, w):
    """Presentation: the good a walker is carrying now, which picks its sprite (carry art vs plain walk).
    Gatherers leave empty and come back loaded (hunter, diver, woodcutter, herders, miners: bugs.md 104);
    an unloaded cart is the empty cart; a buyer walks out empty. Melee/herding looks are separate (walker_anim)."""
    load = next((k for k in w.load if k != "round"), "")
    if w.role == "contestant":                # the discipline's building key (Figure +0x0B picks the picture)
        return w.task or ""
    if w.role not in GATHERERS and w.role not in ("cart", "buyer"):
        return w.good or load                 # e.g. a trainee's good names its art (drama, philosophy...)
    if not w.amount and not load:
        return "empty" if w.role == "cart" else ""
    if w.good:
        return w.good
    if load:
        return load
    home = g.buildings.get(w.home)
    return (g.cat.spec(home.key).get("output") or "") if home is not None else ""


def walker_list(g):
    return [dict(id=w.id, x=w.x, y=w.y, role=w.role, good=carried(g, w), amount=w.amount,
                 anim=walker_anim(g, w)) for w in g.walkers.values()]


def frame(g):
    """Lightweight per-frame state for animation."""
    c = g.city
    return dict(tick=g.tick, date=g.date(), treasury=c.treasury, population=c.population,
                sentiment=c.sentiment, walkers=walker_list(g),
                version=getattr(g, "map_version", 0), alerts=alerts.export(g), houses=[[b.id, b.level, b.occupants, housing.capacity(g, b)] for b in g.buildings.values() if b.kind == "house"])


def write(g, path, with_terrain=True):
    with open(path, "w") as f:
        json.dump(snapshot(g, with_terrain), f, default=lambda o: int(o) if isinstance(o, np.integer) else str(o))
