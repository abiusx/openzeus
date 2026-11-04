"""Service walkers and their effect on buildings within a 5x5 square (docs/logic/services.md).
Coverage services set a house counter to `coverage_days`; it decays by 1 per day."""
from . import labor, index

COVERAGE = ("water", "healer", "philosophy", "athletics", "drama", "competition")
SERVICES = COVERAGE + ("maintenance", "watchman", "tax")


def decay(g):
    coverage_decay(g)
    tax_decay(g)


def coverage_decay(g):
    """Cycle step 35, houses_coverage_decay 0x00484D20: every house's coverage counters - 1."""
    for b in list(index.of(g, "house")) + list(index.keyed(g, "heroes_hall")):
        if b.kind != "house" and b.key != "heroes_hall":
            continue
        for s in list(b.coverage):
            b.coverage[s] -= 1
            if b.coverage[s] <= 0:
                del b.coverage[s]


def tax_decay(g):
    """Cycle step 48, buildings_tax_coverage_decay 0x00488220: the tax collector's timer (b+0x4E) - 1."""
    for b in list(index.of(g, "house")) + list(index.keyed(g, "heroes_hall")):
        if b.kind != "house" and b.key != "heroes_hall":
            continue
        if b.tax_days > 0:
            b.tax_days -= 1


def shows(b):
    return b.misc.get("shows", 0)


def spawn(g):
    """Service buildings, schools and vendors send walkers (services.md §3): once the previous
    walker is back, a spawn timer counts days up to a delay that depends on staffing. Venues that
    need shows (podium, theatre, stadium, observatory, museum) only perform while they have shows,
    which trainees from schools bring; the shows counter drops by 1 a day, after every building has spawned
    (exe: buildings_spawn_walkers is cycle step 31, the venue_shows decrement step 33 in buildings_count_by_type, for
    every venue, cursed or not; the trainee calls the venue finder at step 32), so the venue's own roamer check and
    the schools' venue finder see the day's value before the decrement, whatever the building order."""
    from . import walkers, economy
    from ..gods import cursed, curse_free
    days = g.rules["walker_spawn_days"]
    free = curse_free(g)                          # nothing in the loop changes the gods' state
    for b in list(g.buildings.values()):
        spec = g.cat.spec(b.key)
        if not free and cursed(g, b):                          # a god's curse on the type: no walkers (sim/gods)
            continue
        if b.kind == "service":
            role = spec["service"]
        elif b.kind == "school":
            role = "trainee"
        elif b.kind in ("vendor", "agora") and any(v > 0 for v in b.goods.values()) and spec.get("goods") != "chariot":
            role = "peddler"
        else:
            continue
        if b.access is None or not b.employees:
            continue
        # one roamer out at a time; schools (and the gymnasium's trainee) don't wait for walkers
        # to come back: the college spawner 0x0048CFB0 case 0x4D has no walkers-out check
        out = any(g.walkers[w].role == role for w in b.walkers if w in g.walkers)
        if out and not spec.get("trains"):
            continue
        pct = labor.staffing(g, b)
        if b.key == "fountain" and g.world.des[b.y, b.x] < 30:
            pct //= 2                         # 0x0048CFB0: half pace while the desirability at its tile < 30
        if "spawn_days" in spec:
            if pct < 1:
                continue
            b.spawn_timer += 1
            if b.spawn_timer <= economy.ladder(pct, spec["spawn_days"]):
                continue
        else:
            b.spawn_timer += pct
            if b.spawn_timer < days * 100:
                continue
        b.spawn_timer = 0
        if role == "tax" and next(iter(index.keyed(g, "palace")), None) is None:
            continue                          # 0x0048CFB0 case 0x7A: a clerk only while g_palace_building > 0
        for trainee, venue in spec.get("trains", []):
            send_trainee(g, b, trainee, venue)
        if out or role == "trainee" or (spec.get("needs_shows") and shows(b) <= 0):
            continue
        walkers.spawn_roamer(g, b, role)
    for b in g.buildings.values():
        if shows(b) > 0 and g.cat.spec(b.key).get("needs_shows"):
            b.misc["shows"] -= 1


def send_trainee(g, b, trainee, venue_key):
    """A trainee walks from a school (or the gymnasium) to a venue and gives it shows (services.md §3.1).
    Venue finder 0x00491630: staffed venues of the type with shows <= 24; the pick is the lowest
    road distance + 2 * shows (0x0058AAD0), over the whole road network, no distance limit.
    No venue: the trainee is not sent (the original creates it and deletes it at the school's road tile a tick
    later: the same, except the school's +0xA8 walkers-out count blinks).
    Arrival 0x00491EF0 SETS shows to 32 (rules.trainee_shows). A trainee still walking after
    3,200 ticks (rules.trainee_travel_ticks, ~213 tiles) vanishes without giving shows."""
    from . import walkers, roads
    if b.access is None:
        return
    best = None
    for v in index.keyed(g, venue_key):
        if v.key != venue_key or v.access is None or not v.employees or shows(v) > 24 or v.network != b.network:
            continue
        p = roads.path(g, b.access, {v.access})
        if p is None:
            continue
        cost = len(p) + 2 * shows(v)
        if best is None or cost < best[0]:
            best = (cost, v, p)
    if best is None:
        return
    _, dest, p = best
    w = walkers.spawn(g, b, "trainee", target=dest.id, good=g.cat.spec(venue_key)["service"], task=trainee)
    limit = g.rules.get("trainee_travel_ticks", 3200) // g.rules.get("walker_pace", 15)
    if len(p) > limit:
        p, w.target = p[:limit], 0      # gives up on the way: arrives nowhere
    w.path = p
    # Timing (oracle schools-A-tick1/2): created at step 31 (tick T), hidden at the school's road tile through
    # actions 6 and 7 (finder at T+1), walks from T+2 starting at the tile's centre (serves it there), enters each
    # tile at sub-step 8 and arrives at the last tile's centre: T + 2 + 15 * len, after that tick's cycle step, i.e.
    # 15 * len after the day's shows decrement (step 33 = T+2). Ours runs the day at one tick, decrement after the
    # spawns: its first pass is the creation tick's (Game.step: the day's work, then the pass), the first tile at
    # T+10 (dump T+11: (45, 79) at progress 8; 9 before 11-02, calibrated with the old pass order), 7 more on the last
    # tile (walkers.follow): arrival at T + 2 + 15 len.
    apply(g, w)
    walkers.schedule(g, w, 10 if p else 1)


def unique_venue_bonus(g):
    """+10 culture for every house while a stadium or museum is giving shows (services.md §2).
    Cached per tick."""
    c = getattr(g, "_uvb", None)
    if c and c[0] == g.tick:
        return c[1]
    v = g.rules.get("unique_venue_culture", 10) if any(
        g.cat.spec(b.key).get("unique_venue") and shows(b) > 0 for b in g.buildings.values()) else 0
    g._uvb = (g.tick, v)
    return v


def occ_version(g):
    """Changes when buildings or roads change, not when a tree is cut or regrows (trees only
    matter to walking paths): the key for caches of who stands where."""
    return getattr(g, "map_version", 0) - getattr(g, "tree_changes", 0)


def window(g, x, y):
    """{building id: tiles} in the 5x5 square around (x, y), ids ascending (cached per occ_version)."""
    ver = occ_version(g)
    cache = getattr(g, "_win", None)
    if cache is None or cache[0] != ver:
        cache = g._win = (ver, {})
    out = cache[1].get((x, y))
    if out is None:
        world = g.world
        r = g.rules["coverage_radius"]
        n = world.occ.shape[0]
        cnt = {}
        for row in world.occ[max(0, y - r):min(n, y + r + 1), max(0, x - r):min(n, x + r + 1)].tolist():
            for v in row:
                if v:
                    cnt[v] = cnt.get(v, 0) + 1
        out = cache[1][(x, y)] = {k: cnt[k] for k in sorted(cnt)}
    return out


def repair_walls(g, x, y, red):
    """maintenance_walker_reduce_risk 0x004A5D90: wall tiles (terrain 0x4000, no building) in the 5x5 square
    lose 50 (col 9 of type 121) of their attack damage (g_grid_wall_damage 0x00C753B8; ours in the military
    state, sim/military/invaders.py)."""
    dmg = g.__dict__.get("mil", {}).get("wall_damage")
    if not dmg:
        return
    r, world = g.rules["coverage_radius"], g.world
    for k in list(dmg):
        tx, ty = map(int, k.split(","))
        if abs(tx - x) <= r and abs(ty - y) <= r and world.flags[ty, tx] & 0x4000 and not world.occ[ty, tx]:
            dmg[k] -= red
            if dmg[k] <= 0:
                del dmg[k]


def apply(g, w):
    """Effect of walker w on every building with a tile in the 5x5 square around it."""
    tiles = window(g, w.x, w.y)
    ids = tiles
    role = w.good if w.role == "trainee" else w.role      # trainees serve on their way (services.md §3.1)
    if role == "watchman":
        crime.melee(g, w)
    if w.role in ("plagued", "healer", "watchman"):
        health.contact(g, w)
        if w.id not in g.walkers:
            return
    days = g.rules["coverage_days"]
    red = g.rules["risk_reduce"]
    home_blessed = role == "tax" and bool(getattr(g.buildings.get(w.home), "misc", {}).get("blessed"))
    if role == "maintenance":
        repair_walls(g, w.x, w.y, red)
        for aid, n in agora.strip_near(g, w.x, w.y, g.rules["coverage_radius"]).items():   # the agora's road strip
            a = g.buildings[aid]
            a.fire_risk = max(0, a.fire_risk - red * n)
            a.damage_risk = max(0, a.damage_risk - red * n)
    for bid in ids:
        b = g.buildings.get(bid)
        if b is None:
            continue
        if role in COVERAGE:
            if b.kind == "house" or b.key == "heroes_hall":     # the hall too (houses_culture_compute 0x00484DE0)
                b.coverage[role] = days
        elif role == "maintenance":          # once per building tile in range (services.md), on the root
            if b.kind == "stall":            # building_root: a stall part's tiles lower its agora's risks
                b = g.buildings.get(b.misc.get("agora")) or b
            b.fire_risk = max(0, b.fire_risk - red * tiles[bid])
            b.damage_risk = max(0, b.damage_risk - red * tiles[bid])
        elif role == "watchman":         # 0x004A5F70: -50 per tile of an inhabited house, clamp [col15, 100]
            if b.kind == "house" and b.occupants:
                b.crime = min(100, max(g.cat.houses[b.level]["crime_base"], b.crime - red * tiles[bid]))
        elif role == "tax":              # 0x004A67C0: inhabited houses only
            if b.kind == "house" and b.occupants:
                b.tax_days = 50
                # +0x84 = the collector's office is blessed (b+0xDB; set by gods, stage 2): x4, once
                if home_blessed:
                    b.misc["tax_blessed"] = 1
                else:
                    b.misc.pop("tax_blessed", None)
        elif role == "peddler":          # 0x0040D160: inhabited houses, and elite houses even when empty
            if b.kind == "house" and (b.occupants or is_elite(b)):
                economy.peddle(g, g.buildings.get(w.home), b)


from . import agora, crime, economy, health  # noqa: E402  (circular: imported last)
from .housing import is_elite  # noqa: E402
