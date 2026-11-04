"""Fire and collapse (docs/logic/buildings.md §7-8, services.md §4), crime (services.md §6).

Daily = one cycle. Risk: damage += col7 every day; about 1 building in 8 per day gets
fire += col6 * (1..5). Damage 1000 -> the building collapses (rubble). Fire 1000 -> it ignites:
the fire counter starts at 1 (size 1) or 1..8 and rises by 1 a day. Past 16 the building is
gone: every footprint tile becomes a 1x1 burning ruin (residents die) whose counter starts again at the
building's (seed & 7) + 1 (building_to_burning_ruins 0x00492BE0; oracle 1F-palacefire). At 33 a ruin burns
out and leaves rubble; a ruin put out by a superintendent stays a ruin.
Every 8 days a burning building/ruin spreads the fire with chance 1/4 to the neighbour in the wind direction
(then wind-1, wind+1). Wind: one draw a year.
The palace (bug 268, buildings.md §8.1) is the one composite with risks (model row 0x75): its root burns as one
building, past 16 all 24 pieces turn to burning ruins (each piece its own restart counter), a collapse turns the
whole box to rubble; superintendents never come to it (its +0x20 stays 0: road access 0x004A3D40 sets no distance).
Buildings with parts (buildings.md §8.2, bugs 290 / 292): the horse ranch (house 3x3 + corral 4x4: fireproof in the
type table, so no fire spreads to it, but its own risk ignites it) and the agora (its stalls) burn as the palace:
the root counts, every part burns with its own counter, past 16 every part turns to ruins.
Fire risk (model col 6, model_building_value 0x00433D50) is 0 while Hephaestus' sanctuary is active (bug 291);
a non-house whose col 6 is 0 has its fire risk reset to 0 on its day. A building once lit never catches fire
from a neighbour again (+0x4C stays 1), even when put out.
Fire fighting (services.md §4.1): superintendents already out on the streets find fires within 25
tiles; the nearest one runs there cross-country and puts it out if the counter is <= 16.
"""
from . import index
from .. import fastrand
from .. import alerts

DIR8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
RUBBLE = 0x1000


def climate(g):
    """The map's climate (g_scenario_climate 0x00902D00 = scenario block byte 0x3D8): 0 humid, 1 normal,
    2 arid (texts 44:76..78). Every shipped map has 0 (read 10-29: 111 maps)."""
    c = g.__dict__.get("climate")
    if c is None:
        c = 0
        try:
            from .. import world as wmod
            hdr, blocks = wmod.read_map(g.map_name)
            c = [b for b in blocks if b["rank"] == 14][0]["data"][0x3D8]
        except Exception:
            pass
        g.climate = c
    return c


def fire_inc(g, b, spec, heph=None):
    """model_building_value(type, 6) 0x00433D50: the fire risk increment of b's type (houses: the row of the house's
    current type 2 + level; manors and estates have their own); 0 while Hephaestus' sanctuary is active
    (god_sanctuary_active 0x004E9440 on god record 9, ecx 0x00EF5FAC)."""
    if heph is None:
        heph = hephaestus(g)
    if heph:
        return 0
    if b.kind == "house":
        return g.cat.houses[b.level].get("fire_risk", spec["fire_risk"])
    return spec["fire_risk"]


def hephaestus(g):
    from .. import gods
    return gods.active(g, 9)


def update(g):
    """Cycle step 44, buildings_fire_collapse_risk 0x00492260 (the burning pass is step 43's: burn)."""
    t = g.rules["risk_threshold"]
    k = g.rng.randrange(8)
    arid = climate(g) == 2
    heph = hephaestus(g)
    from .housing import ELITE_LOT
    for b in list(g.buildings.values()):
        if b.id not in g.buildings or b.burning:
            continue
        spec = g.cat.spec(b.key)
        if b.kind in ("road", "decor", "ruin") or (b.kind == "monument" and b.key != "palace"):
            continue                              # the palace's root takes its model risks (step 44 skips 0xA9, 0x3B)
        b.damage_risk += spec["damage_risk"]
        if b.kind == "house" and (b.level < 2 or b.level == ELITE_LOT):    # house level < 2, type 9
            b.damage_risk = 0
        if g.world.flags[b.y, b.x] & 0x10000:     # beach under the building's tile: it never collapses
            b.damage_risk = 0
        if b.damage_risk >= t:
            alerts.raise_alert(g, alerts.COLLAPSE, (b.x, b.y))    # message 0xDC 0xB41 with alert 5 (0x004924DF)
            _tile_msg(g, f"collapse! {b.key} at ({b.x},{b.y})", b)   # FUN_00521A70(0xDC, type, tile, 0xB41..)
            collapse(g, b)
            continue
        s = fastrand.below(g.rng, 5) + 1
        if (b.id + b.x * 3 + b.y) % 8 == k:
            inc = fire_inc(g, b, spec, heph)
            if b.kind != "house":
                if arid and inc:
                    b.fire_risk += 3
                b.fire_risk += inc * s
                if not inc:                       # col 6 == 0 (or Hephaestus): reset
                    b.fire_risk = 0
            elif b.occupants < 1:
                b.fire_risk = 0
            else:
                b.fire_risk += inc * s
            if b.fire_risk > t - 1:               # no fireproof test here (the type table's flag stops spread only)
                alerts.raise_alert(g, alerts.FIRE, (b.x, b.y))    # message 0xDC 0xB3B with alert 0 (spread: none)
                ignite(g, b)


def _rubble(g, x, y, size, h=None, key=None):
    w = g.world
    for yy in range(y, y + (h or size)):
        for xx in range(x, x + size):
            if w.inside(xx, yy) and not w.flags[yy, xx] & 0x4:
                w.flags[yy, xx] |= RUBBLE
                if key is not None:
                    mark_ruin(g, xx, yy, key)


def mark_ruin(g, x, y, key):
    """g_grid_ruin_type (0x004A07C0 / building_to_burning_ruins): the type of the building a rubble or ruin tile
    came from, named by the rubble window (0x0057DA10, 28:type); a burning ruin (0xA9) keeps the one before."""
    if key != "ruin":
        g.sd("ruin_type", {})[(x, y)] = key


def _tile_msg(g, text, b):
    """A building message with its tile: the exe's type 0xDC (building type, tile), whose window has the go-to
    button (msgwin.js: meta at). The phrases 0xB3A.. / 0xB40.. are not in data/messages.json: our line."""
    from ..messages import Msg
    g.message(Msg(text, dict(at=[b.x, b.y], kind=0xDC)))


def collapse(g, b):
    g.city.collapses = getattr(g.city, "collapses", 0) + 1
    to_rubble(g, b, "collapsed")


def boxes(g, b):
    """[(x, y, w, h)] of b and its parts: the ranch's house and corral, the agora's stalls, else b's footprint
    (stadium / palace: w x h)."""
    if b.key == "horse_ranch" and "corral" in b.misc:
        return [(b.x, b.y, 3, 3), (b.misc["corral"][0], b.misc["corral"][1], 4, 4)]
    if b.kind == "agora":
        from . import agora
        return [(s.x, s.y, 2, 2) for s in agora.stalls(g, b)]
    w = b.misc.get("w", b.size)
    return [(b.x, b.y, w, b.misc.get("h") or w)]


def remove(g, b, reason):
    """building_on_remove + clear: an agora takes its stalls with it (its road strip stays)."""
    if b.kind == "agora":
        from . import agora
        agora.remove(g, b, reason)
    else:
        g.demolish(b.id, reason)


def to_rubble(g, b, reason):
    """The building and all its parts to rubble (building_footprint_to_rubble 0x004A07C0 on the root,
    building_parts_destroy_or_ignite(root, 0) on the rest): stadium w x h, the palace its whole box, the ranch's
    corral, an agora's stalls."""
    bx = boxes(g, b)
    remove(g, b, reason)
    for x, y, w, h in bx:
        _rubble(g, x, y, w, h, b.key)
    g.map_version = getattr(g, "map_version", 0) + 1


def ignite(g, b):
    """building_ignite 0x004950B0 (+ building_parts_destroy_or_ignite(id, 1)): size 1 starts at 1, larger ones at
    (seed & 7) + 1 (ours: one draw, kept in misc fire_c0: the ruins restart there). The palace: its root (4x4) as
    a larger building; its other pieces' counters are never read (step 43 counts roots only)."""
    if b.burning and b.key == "palace":           # re-lit through a 1x1 piece (can_catch_fire): the root again
        b.burning = b.misc.get("fire_c0") or 1    # at (seed & 7) + 1, no message (spread posts none)
        return
    b.burning = 1 if b.size == 1 else g.rng.randrange(8) + 1
    if b.size != 1:
        b.misc["fire_c0"] = b.burning
    b.misc["no_spread"] = 1                       # +0x4C = 1: never set back, not even when put out
    if b.key == "horse_ranch" and "corral" in b.misc:
        b.misc["fire_parts"] = [g.rng.randrange(8) + 1]   # the corral (4x4) its own (seed & 7) + 1
    elif b.kind == "agora":                       # the agora root has no tiles (no flames); each stall part (2x2)
        from . import agora                       # its own counter, flames and no workers
        for s in agora.stalls(g, b):
            s.misc["fire_c0"] = g.rng.randrange(8) + 1
            s.misc["no_spread"] = 1
            s.employees = 0
    b.fire_risk = b.damage_risk = 0
    b.employees = 0
    _tile_msg(g, f"fire! {b.key} at ({b.x},{b.y})", b)     # FUN_00521A70(0xDC, type, tile, 0xB3B..)
    g.city.fires = getattr(g.city, "fires", 0) + 1


def can_catch_fire(g, b, x=None, y=None):
    """Spread target at tile (x, y) (buildings_fire_burn_spread: the part there not fireproof (+0x4C: the type
    table's flag, set to 1 by building_ignite and never cleared) and building_type_flammable). The palace's 1x1
    pieces never get +0x4C (building_ignite lights no tile of a size-1 part), so fire reaching one lights the palace
    again even while it burns (its root restarts at (seed & 7) + 1). A stall or the road strip of an agora is
    the agora's part: target() gives the agora."""
    if b.key == "palace" and (b.burning or b.misc.get("no_spread")):
        from . import monuments as mon
        lay = mon.layouts()[b.key]["pieces"]
        return any(mon.size(c) == 1 and mon.piece_xy(b, i) == (x, y) for i, (_, _, c, _) in enumerate(lay))
    if b.burning or b.misc.get("no_spread") or b.kind in ("decor", "ruin", "hippodrome", "road") or \
            (b.kind == "monument" and b.key != "palace"):
        return False                              # the palace: type table fireproof 0, building_type_flammable
    return not g.cat.spec(b.key)["fireproof"]


def on_fire(g, b):
    """b burns: its own counter, or (a stall) its agora's (building_ignite lit the stall part: no workers, flames)."""
    if b.burning:
        return b.burning
    if b.kind == "stall":
        a = g.buildings.get(b.misc.get("agora"))
        return a.burning if a is not None else 0
    return 0


def target(g, x, y):
    """The building record at tile (x, y) for the spread (g_grid_building, then building_ignite +
    building_parts_destroy_or_ignite from the root): a stall -> its agora, an agora's road strip tile -> the agora."""
    n = g.buildings.get(int(g.world.occ[y, x]))
    if n is not None and n.kind == "stall":
        return g.buildings.get(n.misc.get("agora")) or n
    if n is None and g.world.road[y, x]:
        from . import index
        for a in index.of(g, "agora"):
            if [x, y] in a.misc.get("strip", []) or (x, y) in a.misc.get("strip", []):
                return a
    return n


def ruin_tiles(g, b):
    """[(tiles, counter, bump)] for building_parts_to_burning_ruins 0x00492F30 -> building_to_burning_ruins
    0x00492BE0: each part's tiles start again at its (seed & 7) + 1 (ours: the ignition draw fire_c0, else one draw
    per part); bump: the part's own record (an id after the root's) becomes the ruin on its first tile and is
    counted again in the same step-43 pass (+1 there).
    The palace: piece 0 (the root, 4x4) fire_c0, every other piece (4x4 front, 22 1x1) its own draw. The ranch: the
    house fire_c0, the corral its own (oracle 1F-ranchburn: 9 ruins at 5, the corral's 16 at 8, its first tile 9).
    The agora: the root becomes nothing (state 5), each stall its own (oracle 1F-agoraburn: 8 / 3 / 4, +1)."""
    c0 = b.misc.get("fire_c0") or g.rng.randrange(8) + 1
    sq = lambda x, y, w, h: [(x + k, y + j) for j in range(h) for k in range(w)]
    if b.key == "palace":
        from . import monuments as mon
        out = []
        for i, (_, _, c, _) in enumerate(mon.layouts()[b.key]["pieces"]):
            x, y = mon.piece_xy(b, i)
            n = mon.size(c)
            out.append((sq(x, y, n, n), c0 if i == 0 else g.rng.randrange(8) + 1, i > 0))
        return out
    if b.key == "horse_ranch" and "corral" in b.misc:
        c1 = (b.misc.get("fire_parts") or [0])[0] or g.rng.randrange(8) + 1
        return [(sq(b.x, b.y, 3, 3), c0, False), (sq(*b.misc["corral"], 4, 4), c1, True)]
    if b.kind == "agora":
        from . import agora
        return [(sq(s.x, s.y, 2, 2), s.misc.get("fire_c0") or g.rng.randrange(8) + 1, True)
                for s in agora.stalls(g, b)]
    return [(sq(b.x, b.y, b.misc.get("w", b.size), b.misc.get("h") or b.misc.get("w", b.size)), c0, False)]


def to_ruins(g, b):
    """Past day 16: the building is gone, each footprint tile a burning 1x1 ruin (counters: ruin_tiles)."""
    from ..model import Building
    w = g.world
    if b.kind == "house" and b.occupants:
        g.message(f"{b.occupants} people died in the fire at ({b.x},{b.y})")
    parts = ruin_tiles(g, b)
    remove(g, b, "burned down")
    first = None
    for tiles, counter, bump in parts:
        for j, (xx, yy) in enumerate(tiles):
            if not w.inside(xx, yy) or w.flags[yy, xx] & 0x4 or w.occ[yy, xx]:
                continue
            # a palace piece's own record (ids after the root's) becomes the ruin on its first tile and is counted
            # again in the same step-43 pass (oracle 1F-palacefire: parts 352..374 one ahead of the new ruins)
            mark_ruin(g, xx, yy, b.key)
            r = Building(id=g.next_bid, key="ruin", x=xx, y=yy, size=1, kind="ruin",
                         burning=counter + (1 if bump and j == 0 else 0))
            g.next_bid += 1
            g.buildings[r.id] = r
            w.occ[yy, xx] = r.id
            roads.update_access(g, r)             # step 21 gives a ruin by a road its access: superintendents come
            first = first or r
    g.map_version = getattr(g, "map_version", 0) + 1
    return first


def burn(g):
    """Cycle step 43, buildings_fire_burn_spread 0x00493140."""
    wind = getattr(g, "wind", 0)
    arid = climate(g) == 2
    for b in list(g.buildings.values()):
        if not b.burning or b.id not in g.buildings:
            continue
        b.burning += 1
        if b.burning >= 33:                               # burnt out
            g.demolish(b.id, "burned down")
            _rubble(g, b.x, b.y, b.misc.get("w", b.size), b.misc.get("h"))
            g.map_version = getattr(g, "map_version", 0) + 1
            continue
        if b.burning > 16 and b.kind != "ruin":
            b = to_ruins(g, b)
            if b is None:
                continue
        if b.burning & (3 if arid else 7) == 0 and g.rng.randrange(4) == 0:   # spread downwind (arid: 4 days)
            sx, sy = (b.x, b.y)
            if b.key == "palace":                 # from the root's tile (piece 0): its neighbours are palace tiles
                from . import monuments as mon
                sx, sy = mon.piece_xy(b, 0)
            for d in (wind, (wind - 1) % 8, (wind + 1) % 8):
                x, y = sx + DIR8[d][0], sy + DIR8[d][1]
                if not g.world.inside(x, y):
                    continue
                n = target(g, x, y)
                if n is not None and can_catch_fire(g, n, x, y):
                    ignite(g, n)
                    break


def year_start(g):
    g.wind = g.rng.randrange(8)


def fire_dispatch(g, w):
    """Superintendent search (services.md §4.1, 0x004CD450): a roaming or returning superintendent
    counts ticks only while a building burns and from 20 on looks (every step) for an unclaimed,
    road-connected burning building within Chebyshev 25; the
    nearest idle superintendent in the city (maybe itself) runs there cross-country.
    Returns True when w itself was sent."""
    cache = getattr(g, "_burning", None)
    if cache is None or cache[0] != g.tick:
        on = [b for b in g.buildings.values() if b.burning]
        # candidates (fire_find_target 0x00493510): road-connected (+0x20 != 0); the palace's +0x20 is never set
        cache = g._burning = (g.tick, [b for b in on if b.access is not None and b.key != "palace"], bool(on))
    burning = cache[1]
    if not cache[2]:                 # 0x004CD450: the timer counts only while something burns (any listed fire)
        return False
    w.wait += max(1, g.tick - w.arrived)       # +1 per tick in the exe; ours acts once per tile step
    if w.wait < 20:
        return False
    free = []
    for b in burning:
        f = g.walkers.get(b.misc.get("fighter", 0))
        if f is None or f.role != "maintenance" or f.state not in ("fire", "ext"):
            b.misc["fighter"] = 0
            free.append(b)
    if not free:
        return False
    d, b = min(((max(abs(w.x - b.x), abs(w.y - b.y)), b) for b in free), key=lambda t: t[0])
    if d > 25:
        return False
    w.wait = 0
    idle = [s for s in g.walkers.values() if s.role == "maintenance" and s.state not in ("fire", "ext")]
    s = min(idle, key=lambda s: (max(abs(s.x - b.access[0]), abs(s.y - b.access[1])), s.id))
    p = walkers.land_path(g, (s.x, s.y), {b.access}, max_dist=walkers.ROUTE_MAX)   # route mode 0, no radius
    if p is None:
        return False
    s.wait, s.state, s.target, s.path, s.returning = 0, "fire", b.id, p, False
    b.misc["fighter"] = s.id
    if s is not w:
        walkers.schedule(g, s, walkers.tile_delay(g, s))
    return s is w


def fire_fight(g, w):
    """Superintendent on its fire run (cross-country) / extinguishing at the building."""
    from . import walkers
    if w.state == "fire":
        if w.path:
            walkers.step_to(g, w, w.path.pop(0))
            return walkers.schedule(g, w, walkers.tile_delay(g, w))
        w.state = "ext"
        b = g.buildings.get(w.target)
        if b is not None and b.burning and max(abs(w.x - b.x), abs(w.y - b.y)) < 10:
            if b.burning <= 16:
                b.burning = 0
                g.message(f"fire at ({b.x},{b.y}) put out")
            else:
                b.burning = 32
        return walkers.schedule(g, w, 50)
    w.state, w.wait = "", 20                 # done: home by road (may be sent again at once)
    walkers.go_home(g, w)


def crime(g):
    """Twice a month per house (houses_unrest_update): unrest += crime_inc + (40 - sentiment)/2
    once the city has 350 people, clamped to [crime_base, 100]. Criminals: systems/crime.py."""
    c = g.city
    if c.population >= 350:
        g.crime_latch = True
    from .health import sanctuary_done
    dionysus = sanctuary_done(g, "dionysus")
    for b in list(index.of(g, "house")):
        if b.kind != "house":
            continue
        if not b.occupants or b.level >= 7:     # elite houses: no unrest counter (housing.md §5)
            b.crime = 0
            continue
        h = g.cat.houses[b.level]
        if getattr(g, "crime_latch", None):
            if dionysus:                        # god record 10's finished sanctuary: -20 instead
                b.crime -= 20
            else:
                b.crime += h["crime_inc"] + int((40 - c.sentiment) / 2)
        b.crime = min(100, max(b.crime, h["crime_base"]))


from . import roads, walkers  # noqa: E402  (circular: imported last)
