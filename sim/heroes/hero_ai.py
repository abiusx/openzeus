"""The hero figure (figure type 0x45, figure_hero_update 0x004C8F50; docs/logic/heroes-monsters.md "Hero handler").

  6   just created at the map entry: +0x36 = 0 -> 9 at once
  9   walk to the hall's road access -> 7
  7   in the hall (hidden, healed): out at once when the hall has road access, after 800 ticks when he came home
      beaten (hall +0xC4 bit 4) -> 8
  8   patrol the roads (roam budget 0xF00 units = 256 tiles at 15 a tile) -> 9; hero_find_target every tick
  10  hero_combat_update: chase (re-path every 16 ticks); within Chebyshev < 4 the monster is held (action 23 follows
      him); in contact (either side starting it): the fight engine's action 5, which with his quarry is the duel
      (hero_duel_hit 0x004D5BC0: no damage either way, +0x68 300 -> the monster dies; sim/heroes/combat.py);
      afterwards hero_return_to_hall: on a road -> 8, else back to a road / the hall (12/13)
  14  to the land exit for a quest -> 16 (hidden at the exit); 15 back to the hall when the quest is done
  17  the hall is gone: removed, sent_for = 0

Walker fields: hero (id, +0x0B), act, target (+0x82), duel_n / duel_end (+0x68: the count, and in a duel the tick
it runs out), chase_t0 (the tick +0x36 was 0), quest (+0x132 event id), roam
(+0x44 tiles walked), rest_until.
"""
from . import data
from ..systems import walkers
from ..military import units

N = 228
SPEED = 7                     # Figure_model row 69 col 8: 12 ticks a tile
ENGAGE = 4                    # Chebyshev distance at which the monster is held (0x00534060)
ROAM_TILES = 0xF00 // 15      # +0x42 = 0xF00 roam units, 15 a tile
BEATEN_REST = 800             # action 7 with hall +0xC4 bit 4


def hall(g, w):
    from . import heroes
    return heroes.hall(g, w.hero)


def on_water(g, x, y):
    """figure_hero_update 0x004C8F50 head: deep water (terrain 0x4000000) that is not a bridge piece (road + water
    0x44 with a bridge byte 0x00CB4B08): the hero swims there (action 0x13 look: his special group on a raft)."""
    wd = g.world
    if not wd.flags[y, x] & 0x4000000:
        return False
    return not (wd.road[y, x] and wd.flags[y, x] & 0x4)


def water_ok(g):
    """Route mode 6 (0x0058B560): route & 0x3C (road, open land, walkable building parts) or a blocked tile (route
    bit 2) on water or beach (terrain & 0x10004) without a building. Ours: the mode-0 land (monsters.passable, which
    also lets ramp roads and decor through) plus every water / beach tile without a building."""
    from .monsters import passable
    from ..systems.services import occ_version
    v = occ_version(g)
    c = getattr(g, "_hero_water_ok", None)
    if c is None or c[0] != v:
        wd = g.world
        wet = (((wd.flags & 0x10004) != 0) & (wd.occ == 0)).ravel().tolist()
        c = g._hero_water_ok = (v, [a or b for a, b in zip(passable(g), wet)])
    return c[1]


def _route(g, w, goal, near=0):
    """figure_find_route by the hero's +0x72 (figure_hero_update 0x004C8F50 sets it every tick): mode 6 while chasing
    (action 10), going back to a road or the hall (12, 13) or standing on water (on_water): 0x0058B560 over land and
    water (water_ok), else route_distance; otherwise mode 0: route_distance over the land mask 0x11D
    (monsters.passable: open land, roads, bridges, ramps). Both + trace8, at most 499 steps (walkers.route0). The goal
    is the target's own tile; `near` only shortens the walk (the caller stops within it). Bug 392: heroes swim."""
    from .monsters import passable
    p = None
    if w.act in (10, 12, 13) or on_water(g, w.x, w.y):
        p = walkers.route0(g, (w.x, w.y), tuple(goal), water_ok(g))
    if p is None:
        p = walkers.route0(g, (w.x, w.y), tuple(goal), passable(g))
    if p and near:
        while len(p) > 1 and max(abs(p[-2][0] - goal[0]), abs(p[-2][1] - goal[1])) <= near:
            p.pop()
    return p


def walk(g, w, goal, arrive, near=0, lost=None):
    goal = tuple(goal)
    if max(abs(goal[0] - w.x), abs(goal[1] - w.y)) <= near:
        return arrive()
    if not w.path or getattr(w, "dest", None) != goal:
        w.dest = goal
        w.path = _route(g, w, goal, near) or []
        if not w.path:
            return (lost or arrive)()              # lost (result 10)
    nxt = w.path.pop(0)
    w.face = (nxt[0] - w.x, nxt[1] - w.y)
    units.step(g, w, nxt)
    return walkers.schedule(g, w, units.tile_ticks(g, w, SPEED))


def access(b):
    return tuple(b.access) if getattr(b, "access", None) else (b.x, b.y)


def act(g, w):
    if w.anim == "die":
        return units.act_dying(g, w)
    b = hall(g, w)
    if b is None or b.misc.get("hero_fig") != w.id:
        return gone(g, w)                          # 17
    a = w.act
    if a == 16:
        return walkers.schedule(g, w, 1 << 20)     # away on the quest
    if a == 6:
        w.act = 9
        a = 9
    if a == 9:
        w.hidden = False
        return walk(g, w, access(b), lambda: enter_hall(g, w, b))
    if a == 7:
        return in_hall(g, w, b)
    if a == 10:
        return chase(g, w)
    if a == 5:
        return duel(g, w)
    if a in (12, 13):
        return back_to_road(g, w, b)
    if a == 14:
        return walk(g, w, tuple(g.world.exit), lambda: away(g, w))
    if a == 15:
        w.hidden = False
        return walk(g, w, access(b), lambda: enter_hall(g, w, b))
    return patrol(g, w, b)


def gone(g, w):
    from . import heroes
    r = heroes.record(g, w.hero)
    r["sent"] = 0
    if r["fig"] == w.id:
        r["fig"] = 0
    return units.remove(g, w)


def enter_hall(g, w, b):
    """0x004C8EB0: into the hall (action 7), healed, flag 0x10 cleared."""
    w.act = 7
    w.hidden = True
    w.dmg = 0
    w.path = []
    if getattr(w, "beaten", False):
        w.beaten = False
        w.rest_until = g.tick + BEATEN_REST
    else:                                          # action 7: +0x68 - 1 a tick, out when < 1 (a duel count left
        w.rest_until = g.tick + max(0, (getattr(w, "duel_n", 0) or 0) - 1)    # over from a broken-off duel)
    w.duel_n = 0
    return walkers.schedule(g, w, 1)


def in_hall(g, w, b):
    if g.tick < w.rest_until or not b.access:
        return walkers.schedule(g, w, max(1, w.rest_until - g.tick) if g.tick < w.rest_until else 51)
    w.hidden = False
    units.step(g, w, access(b))                    # 0x004E3220: out at the road access
    w.act = 8
    w.roam = 0
    return walkers.schedule(g, w, 1)


def patrol(g, w, b):
    """Action 8: roam the roads (ours: a step to a road neighbour, the least recently walked first as a roamer),
    hero_find_target every step; the budget spent -> home (9)."""
    w.act = 8
    w.hidden = False
    if find_target(g, w):
        return None
    if w.roam >= ROAM_TILES:
        w.act = 9
        w.path = []
        return walkers.schedule(g, w, 1)
    road = walkers.road_list(g)
    x, y = w.x, w.y
    if not road[y * N + x]:
        return back_to_road(g, w, b)
    near = [t for t in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))
            if 0 <= t[0] < N and 0 <= t[1] < N and road[t[1] * N + t[0]]]
    if not near:
        return walkers.schedule(g, w, 51)
    opts = [t for t in near if t != w.prev] or near
    mem = g.sd("visits", {}).setdefault(("hero", w.hero), {})
    if len(opts) > 1:
        oldest = min(mem.get(t, -1) for t in opts)
        opts = [t for t in opts if mem.get(t, -1) == oldest]
    nxt = opts[g.rng.randrange(len(opts))] if len(opts) > 1 else opts[0]
    mem[nxt] = g.tick
    w.face = (nxt[0] - x, nxt[1] - y)
    units.step(g, w, nxt)
    w.roam += 1
    return walkers.schedule(g, w, units.tile_ticks(g, w, SPEED))


def road_near(g, x, y, rmax):
    """road_tile_near_building 0x004A39D0(x, y, 1, rmax): radius 0, 1, .. rmax, each the filled square
    [x-r, x+r] x [y-r, y+r] row by row (road_tile_near_rect 0x004A37D0): a road tile not on water (terrain & 0x44 ==
    0x40: no bridge), the best-ranked network among the 10 largest (11 for others) first, the first found on a tie.
    (Ours skips its avenue/boulevard step to the anchor tile.)"""
    from ..systems import monuments
    w = g.world
    road = walkers.road_list(g)
    rank = monuments.network_ranks(g)
    for r in range(0, rmax + 1):
        best = None
        for ty in range(max(0, y - r), min(N - 1, y + r) + 1):       # the smaller squares had none: only the ring
            xs = range(max(0, x - r), min(N - 1, x + r) + 1) if abs(ty - y) == r else \
                [t for t in (x - r, x + r) if 0 <= t < N] if r else [x]
            for tx in xs:
                if road[ty * N + tx] and not w.flags[ty, tx] & 0x4:
                    k = rank.get(int(w.road_net[ty, tx]), 11)
                    if best is None or k < best[0]:
                        best = (k, (tx, ty))
        if best:
            return best[1]
    return None


def back_to_road(g, w, b):
    """hero_return_to_hall 0x004FD060 (and action 12's retry, 0x004C948E): on a road -> patrol (8); else the nearest
    road within the Chebyshev distance to the hall (road_near) -> 13 there, else 12 to the hall's road access.
    Route lost: retried (the exe frees the route on direction 9/10 and searches again the next tick; ours after 51
    ticks). Not ported: action 12's straight line move (route mode 6, hall +service_acc != 0)."""
    road = walkers.road_list(g)
    if road[w.y * N + w.x]:
        w.act, w.roam = 8, 0
        return walkers.schedule(g, w, 1)
    best = road_near(g, w.x, w.y, max(abs(w.x - b.x), abs(w.y - b.y)))
    w.act = 13 if best else 12
    return walk(g, w, best or access(b), lambda: walkers.schedule(g, w, 1), lost=lambda: walkers.schedule(g, w, 51))


def find_target(g, w):
    """hero_find_target 0x004FCF90: the nearest live bad monster of his two ids (any distance), not claimed by another
    hero; else (0x004FCA00) another aggressive monster within 16; else an invader anywhere -> action 10."""
    mons = data()["heroes"][w.hero]["monsters"]
    best, bd = None, 1 << 30
    for o in g.walkers.values():
        if o.role == "monster" and o.mid in mons and units.alive(o) and getattr(o, "uclass", 8) == 8 \
                and not getattr(o, "hidden", False) and getattr(o, "hero_fig", 0) in (0, w.id):
            d = max(abs(o.x - w.x), abs(o.y - w.y))
            if d < bd:
                best, bd = o, d
    if best is None:
        for o in g.walkers.values():
            if o.role == "monster" and units.alive(o) and getattr(o, "uclass", 8) == 8 \
                    and max(abs(o.x - w.x), abs(o.y - w.y)) < 16 and getattr(o, "hero_fig", 0) in (0, w.id):
                best = o
                break
    if best is None:
        for o in g.walkers.values():
            if o.role in ("enemy_infantry", "enemy_archer", "enemy_cavalry") and units.alive(o):
                best = o
                break
    if best is None:
        return False
    if best.role == "monster":
        from .monsters import free_route
        best.hero_fig = w.id
        free_route(best)                           # figure_route_free(target): the exe frees the TARGET's route
    w.act = 10
    w.chase_t0 = g.tick                            # +0x36 = 0, dest = its tile
    if w.target != best.id:
        w.path = []
    w.target = best.id
    walkers.schedule(g, w, 1)
    return True


def chase(g, w):
    """hero_combat_update 0x004FD2B0 (+0x36 counts ticks; ours keeps the tick of the last route in chase_t0).
    Arrived (ours: next to the target): facing it, FUN_004D5330 (figure_tile_contact with the first figure of each
    neighbour tile): a fight with his quarry is the duel (figure_fight_start -> action 5, +0x68 = 300; the fight
    engine's hero_duel_hit: sim/heroes/combat.py), with anyone else a plain melee; no fight -> on toward its tile.
    Walking: +0x36 > 16 at a tile centre with the target not in action 5 -> re-routed to its tile; within Chebyshev
    < 4 a monster not yet holding him (+0x82 = him, action 0x17) is held (monster_engage_hero 0x00534060), else
    +0x36 > 16 -> hero_find_target again (a nearer quarry). Before 11-04 ours started a separate duel only from the
    hero's side, so a melee the monster began (its 0x17 contact) did damage both ways and lasted until it died."""
    from .rampage import neighbours
    o = g.walkers.get(getattr(w, "target", 0))
    if o is None or not units.alive(o) or getattr(o, "hidden", False):
        w.target = 0
        return back_to_road(g, w, hall(g, w))
    d = max(abs(o.x - w.x), abs(o.y - w.y))
    if d <= 1:
        w.face = ((o.x > w.x) - (o.x < w.x), (o.y > w.y) - (o.y < w.y)) if d else w.face
        neighbours(g, w)
        if w.anim:
            return None
        if (w.x, w.y) == (o.x, o.y):
            from ..military import contact
            if contact.figure_contact(g, w, o):    # on its tile: figure_tile_contact(hero, target)
                return None
        return walkers.schedule(g, w, 4)
    late = g.tick - getattr(w, "chase_t0", g.tick) > 16
    if d < ENGAGE and o.role == "monster":
        if o.act != 23 or getattr(o, "tf", 0) != w.id:
            hold(g, o, w)
    elif late:
        find_target(g, w)
        if w.target != o.id:
            return None                            # a nearer quarry: chased from the next tick
    if not w.path or (late and o.anim != "fight"):
        w.chase_t0 = g.tick
        w.path = _route(g, w, (o.x, o.y), 1) or []
        if not w.path:                             # route result 10 (lost): FUN_004E3220 puts him on its tile
            units.step(g, w, (o.x, o.y))
            return walkers.schedule(g, w, 1)
    nxt = w.path.pop(0)
    w.face = (nxt[0] - w.x, nxt[1] - w.y)
    units.step(g, w, nxt)
    return walkers.schedule(g, w, units.tile_ticks(g, w, SPEED))


def hold(g, m, w):
    """monster_engage_hero 0x00534060: the monster's other opponents of unit type 0/1 let go; it turns to the hero
    (action 23, 0x00534150: follows him)."""
    from ..military import units as u
    for a in u.attackers(g, m):
        if u.unit_class(a) in (0, 1):
            u.end_fight(g, a)
    m.act = 23
    m.path, m.route = [], None
    m.tf = w.id
    walkers.schedule(g, m, 1)


def duel(g, w):
    """A save from before 11-04 mid-duel (ours' old separate action 5): ends as it would have."""
    o = g.walkers.get(getattr(w, "foe", 0))
    if g.tick < w.duel_end and o is not None and units.alive(o):
        return walkers.schedule(g, w, w.duel_end - g.tick)
    w.anim, w.foe = "", 0
    if o is not None and units.alive(o):
        o.anim = ""
        units.kill(g, o, w)
    w.target = 0
    return back_to_road(g, w, hall(g, w))


def fight_over(g, w):
    from . import combat
    w.duel_n, w.duel_end = combat.duel_left(g, w), None      # +0x68 as it stands (a broken-off duel's count)
    w.mil = False
    if getattr(w, "beaten", False):
        w.act = 9
    elif w.act != 16:
        w.act = 12
    return walkers.schedule(g, w, 1)


def dispatch(g, h):
    """The army dispatch dialog answering a quest (0x005BE0E0 -> 0x0046DA70): state 6, countdown = travel months
    (< 1 -> 12), the hero of the quest's slot leaves (+0x132 = event, action 14 to the land exit)."""
    from . import heroes, events
    w = heroes.figure(g, h)
    if w is None:
        raise ValueError(f"{heroes.name(h)} is not in the city")
    if getattr(w, "quest", None) is not None:
        raise ValueError(f"{heroes.name(h)} is already away")
    qs = [ev for ev in events.open_quests(g) if heroes.hero_of_slot(g, ev["b36"]) == h]
    if not qs:
        raise ValueError(f"no quest needs {heroes.name(h)}")
    ev = qs[0]
    ev["state"] = 6
    t = events.travel_months(g, ev)
    ev["countdown"] = t if t >= 1 else 12
    w.quest = ev["id"]
    if w.anim == "fight":
        units.end_fight(g, w)
    w.act = 14
    w.path = []
    w.hidden = False
    walkers.schedule(g, w, 1)
    from .. import scenario
    scenario.request_list_rebuild(g)             # army_dialog_dispatch 0x005BDAD0 -> request_list_rebuild
    return f"{heroes.name(h)} sets out on the quest"


def away(g, w):
    w.act = 16
    w.hidden = True
    return walkers.schedule(g, w, 1 << 20)


def quest_home(g, ev):
    """expedition_forces_home 0x004DEE60: the hero who went (+0x132 = the event) comes back (action 15)."""
    for w in list(g.walkers.values()):
        if w.role == "hero" and getattr(w, "quest", None) == ev["id"]:
            w.quest = None
            w.act = 15
            w.hidden = False
            w.path = []
            walkers.schedule(g, w, 1)


def look(g, w):
    if getattr(w, "hidden", False):
        return ["hidden", 0, 0, 0, 0, 0, 0, 0, "", False]
    if w.act == 5 and w.anim == "fight" and getattr(w, "duel_end", None) is not None:   # an old save's duel
        f = w.face or (0, 1)
        return ["fight", w.anim_t0, w.duel_end, f[0], f[1], 0, 0, w.anim_t0, "monster", True]
    return None
