"""Attacking gods (figure 0x43, actions 0x36..0x49; docs/logic/religion.md "God and priest figure handlers",
"Attacking god (A)"). A hostile god does all its A (destroy), then all B (curse), then all C (kill), then leaves;
each failed target search costs one unit; it also leaves when its 6 months (+0x108 = 0x60 month_advance calls) end.

w.phase: "wander" (0x37), "A" (0x3A walk / 0x3B bolts), "B" (0x38 walk / 0x39 curse), "C" (0x43 walk / 0x44 bolts),
"charm" (Aphrodite / Dionysus 0x3F..0x42), "hermes" (0x45..0x48), "leave" (0x49 walk, then the vanish).
Animation timing: one frame a tick (the exe advances non-walking frames on a wall-clock gate; ours: per tick).
"""
from . import T, state, rec, rng, GODS, NAMES
from .month import log, curse

PALACE = 117
HOUSES = set(range(2, 15))
ORDINARY_SKIP = frozenset(("god", "priest", "monster", "hero", "boat", "ship", "trireme", "arrow", "enemy_arrow",
                           "sheep", "goat", "cattle", "horse", "boar", "deer", "wolf", "rabble", "hoplite",
                           "horseman", "enemy_infantry", "enemy_archer", "enemy_cavalry", "tower_sentry",
                           "wall_sentry"))


def _W():
    from ..systems import walkers
    return walkers


def frames(i, k):
    """FUN_004EA4E0: frames of the god's action group k (0 walk, 1 vanish, 2 attack, 3 appear, 4 cast)."""
    return max(1, T()["frames"][i][k])


def tpf(i, k):
    """Ticks per frame of god i's group k where the handler's tail steps it at rate 100 (sprite_anim_step 0x005AF8C0:
    only when the gate 0x006668EC[image speed] fires; data/gods.json frame_ticks, at the exe's default game speed;
    bug 393). Ours counts from the look's start (the exe's gate phase is wall-clock)."""
    from ..systems.walkers import RATE100_TPF          # the oracle harness's clock: 1 (walkers.RATE100_TPF)
    return RATE100_TPF or max(1, T()["frame_ticks"][i][k])


def dur(i, k):
    """A rate-100 look that ends on its group's last frame: frames x ticks per frame."""
    return frames(i, k) * tpf(i, k)


def zid(g, b):
    """The exe's building type; our common / elite houses are one key with levels (types 2..8 / 9..14)."""
    if b.kind == "house":
        return (9 if b.key == "elite_house" else 2) + b.level
    return g.cat.spec(b.key).get("zeus_id")


def init(g, w):
    """god_attack_init 0x004ECA10: budgets, the 6-month clock, trade blocks, the god's first action."""
    from .figures import BUDGETS
    i = w.god
    a, b, c, _ = BUDGETS[i]
    w.budget = [a, b, c]
    w.days_left, w.day_seen = 0x60, g.day
    w.task = "attack"
    st = state(g)
    if i == 0:
        st["trade_block"] = [0xC0, 0xC0]
    elif i == 1:
        st["trade_block"][0] = 0xC0
    elif i == 7:
        st["trade_block"][1] = 0xC0
    if i in (4, 5):                              # Artemis / Ares: an army at the map entry (FUN_00504650)
        army(g, w)
    if i == 2:                                   # Demeter kills every second sheep / goat
        _cull(g, ("sheep", "goat"))
    if i == 12:                                  # Hera every second cattle (0x004EC7C0)
        _cull(g, ("cattle",))
    pal = _palace(g)
    if i == 0 and pal is not None:
        return _go(g, w, "A", pal)
    if i in (3, 11, 12, 13):
        t = pal or _highest_house(g)
        if t is not None:
            return _go(g, w, "B", t)
    if i in (2, 8, 9):
        return _enter(g, w, "B")
    if i in (4, 5):
        return _enter(g, w, "C")
    if i in (6, 10):
        if i == 10:                              # Dionysus: 3 followers beside him (god_follower_create(f, 0x44): satyrs)
            for _ in range(3):
                follower(g, w, "satyr")
        return _enter(g, w, "charm")
    if i == 7:
        return _enter(g, w, "hermes")
    return _enter(g, w, "wander")


def _cull(g, roles):
    n = 0
    for a in sorted((a for a in g.walkers.values() if a.role in roles and a.anim != "die"), key=lambda a: a.id):
        n += 1
        if n % 2 == 0:
            _W().remove(g, a)


def _palace(g):
    return next((b for b in g.buildings.values() if b.key == "palace"), None)


def _highest_house(g):
    hs = [b for b in g.buildings.values() if b.kind == "house"]
    return max(hs, key=lambda b: (b.level + (100 if b.key == "elite_house" else 0), -b.id)) if hs else None


def _cursed(g, b):
    from . import cursed
    return cursed(g, b)


# --- the state machine ---------------------------------------------------------------------------------------

def act(g, w):
    W = _W()
    if g.day != w.day_seen and hostile(g, w):    # +0x108 -1 whenever month_tick changed (hostile gods only)
        w.days_left -= g.day - w.day_seen
    w.day_seen = g.day
    _aura(g, w)
    ph = w.phase
    if ph in ("B", "C", "hermes") and hostile(g, w) and should_leave(w):   # 0x38/0x39, 0x43..0x46 (not A, charm)
        return _enter(g, w, "leave")
    if w.path:                                   # walking to the action's destination
        W.step_to(g, w, w.path.pop(0))
        return W.schedule(g, w, _tick(g, w))
    if ph == "wander":
        return _wander(g, w)
    if ph == "A":
        return _destroy(g, w)
    if ph == "B":
        return _curse(g, w)
    if ph == "C":
        return _kill(g, w)
    if ph == "charm":
        return _charm(g, w)
    if ph == "hermes":
        return _hermes(g, w)
    if ph == "leave":
        from .figures import vanish
        return vanish(g, w)
    if ph == "gone":
        return None
    return _enter(g, w, "wander")


def _tick(g, w):
    from .figures import tile_ticks
    return tile_ticks(g, w) // 3 if (w.god == 7 and w.phase == "leave") else tile_ticks(g, w)


def hostile(g, w):
    """god_figure_hostile 0x004EDE40: unfriendly and listed (scenario slots 0..3). A jealous friendly god is not:
    it has no 6-month clock and leaves only when its budgets are spent (the wander test)."""
    r = rec(g, w.god)
    return r["unfriendly"] == 1 and r["listed"] == 1


def should_leave(w):
    """god_attack_should_leave 0x004ECB00."""
    a, b, c = w.budget
    return w.days_left < 1 or (a < 1 and b < 1 and c < 1)


def _wander(g, w):
    if should_leave(w):
        return _enter(g, w, "leave")
    a, b, c = (x if 0 <= x <= 100 else 0 for x in w.budget)
    w.budget = [a, b, c]
    if a > 0:
        return _enter(g, w, "A")
    if b > 0:
        return _enter(g, w, "B")
    if c > 0:
        return _enter(g, w, "C")
    return _enter(g, w, "leave")


def _enter(g, w, ph):
    """The enter-action callbacks (0x004EBD50): pick the target, set the walk."""
    W = _W()
    w.phase, w.step, w.target, w.path = ph, 0, 0, []
    if ph == "A":
        cat = T()["destroy_category"][w.god]
        if cat < 0:
            cat = rng(g).randrange(32768) % 11
        b = _nearest(g, w, set(T()["destroy_types"][cat]), roots=False)
        if b is None:
            w.budget[0] -= 1
            return _enter(g, w, "wander")
        return _go(g, w, "A", b)
    if ph == "B":
        row = w.god if w.god else rng(g).randrange(32768) % 14 + 1          # Zeus: a random row 1..14 (quirk)
        b = _nearest(g, w, set(T()["curse_types"][row]), roots=True, limit=1000)
        if b is None:
            w.budget[1] -= 1
            return _enter(g, w, "wander")
        return _go(g, w, "B", b)
    if ph == "C":
        t = _victim(g, w)
        if t is None:
            w.budget[2] -= 1
            return _enter(g, w, "wander")
        w.target = t.id
        w.path = _land_path(g, w, {(t.x + dx, t.y + dy) for dx in range(-4, 5) for dy in range(-4, 5)}) or []
        return W.schedule(g, w, 1)
    if ph == "charm":
        b = _palace(g) or next((b for b in sorted(g.buildings.values(), key=lambda b: b.id) if b.access), None)
        if b is None:
            return _enter(g, w, "leave")
        w.charm_t0 = 0
        w.path = _land_path(g, w, {tuple(b.access)}) or []
        return W.schedule(g, w, 1)
    if ph == "hermes":
        w.step = 0
        return W.schedule(g, w, 1)
    if ph == "leave":
        release(g, w)                            # enter 0x49 (0x004EC000): god_leave_release
        from .invasion import arrival
        at = arrival(g, w.god) or tuple(g.world.entry)
        w.path = _land_path(g, w, {tuple(at)}) or []
        log(g, f"{NAMES[w.god]} leaves the city")
        return W.schedule(g, w, 1)
    return W.schedule(g, w, 1)


def _go(g, w, ph, b):
    W = _W()
    w.phase, w.step, w.target = ph, 0, b.id
    goal = tuple(b.access) if b.access else None
    if goal is None:
        goals = W.edge_tiles(g, b)
    else:
        goals = {(goal[0] + dx, goal[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
    w.path = _land_path(g, w, goals) or []
    return W.schedule(g, w, 1)


def _land_path(g, w, goals):
    W = _W()
    if (w.x, w.y) in goals:
        return []
    return W.land_path(g, (w.x, w.y), goals, max_dist=W.ROUTE_MAX)


def _nearest(g, w, types, roots=True, limit=None):
    """nearest_building_in_category 0x004ABBF0 / god_curse_target_find 0x004ECE60: alive buildings of the types,
    not cursed, smallest |dx| + |dy| (first id wins ties)."""
    best, bd = None, None
    for b in sorted(g.buildings.values(), key=lambda b: b.id):
        z = zid(g, b)
        if z not in types or _cursed(g, b) or (roots and b.kind == "stall"):
            continue
        d = abs(b.x - w.x) + abs(b.y - w.y)
        if limit is not None and d >= limit:
            continue
        if bd is None or d < bd:
            best, bd = b, d
    return best


def _victim(g, w):
    """next_figure_in_radius 0x004AC270: the first figure in id order within Chebyshev 15 whose unit class is 1
    (helpless), 2 (good guy) or 7 (good monster), off water (Poseidon: on water)."""
    from ..military import units
    water = g.world.flags
    for t in sorted(g.walkers.values(), key=lambda t: t.id):
        if t.role in ("god", "carrier") or t.anim == "die" or getattr(t, "hidden", False):
            continue
        if max(abs(t.x - w.x), abs(t.y - w.y)) >= 15:
            continue
        if units.unit_class(t) not in (1, 2, 7):
            continue
        wet = bool(water[t.y, t.x] & 4)
        if wet != (w.god == 1):
            continue
        return t
    return None


def _destroy(g, w):
    """0x3B (0x004ED510 / 0x004ED800): 5 shots; each attack cycle (frames(Athena 4, else 2)) a new random tile of the
    building as the aim (frame 0) and a bolt 0x34 there (shot_frame; bolts.py: the first that lands destroys the
    building); when the shots are done and no bolt of the god flies: building_destroyed_by_attack, A -1. The building
    gone (or invalid) -> A -1 at once."""
    from . import bolts
    W = _W()
    b = g.buildings.get(w.target)
    if b is None:
        w.budget[0] -= 1
        w.anim_kind = ""
        return _enter(g, w, "wander")
    k = 4 if w.god == 8 else 2
    n, p = frames(w.god, k), tpf(w.god, k)       # rate 100: frame f at f * p ticks into the cycle (bug 393)
    sf = min(T()["shot_frame"][w.god], n - 1)
    if w.step == 0:                              # enter 0x3B: +0x92 = 5
        w.step, w.shots, w.anim_kind = 1, 5, "attack"
        w.face = (b.x - w.x, b.y - w.y)
    if w.step == 1:                              # frame 0: a random tile of b, face it
        r = rng(g)
        sz = max(1, b.size or 1)
        w.aim = (b.x + r.randrange(32768) % sz, b.y + r.randrange(32768) % sz)
        w.face = (w.aim[0] - w.x, w.aim[1] - w.y)
        w.anim_t0, w.step = g.tick, 2
        return W.schedule(g, w, max(1, sf * p))
    if w.step == 2:                              # shot_frame: the bolt
        bolts.shoot(g, w, w.aim, 0x34)
        w.step = 3
        return W.schedule(g, w, max(1, (n - 2 - sf) * p))
    if w.step == 3:                              # frame n-2: +0x92 -1
        w.shots -= 1
        if w.shots > 0:
            w.step = 1
            return W.schedule(g, w, 2 * p)
        w.step = 4
    if bolts.alive(g, w):
        return W.schedule(g, w, 2)
    destroyed_by_attack(g, b, w)
    w.budget[0] -= 1
    w.anim_kind = ""
    return _enter(g, w, "wander")


def destroyed_by_attack(g, b, god):
    """building_destroyed_by_attack 0x004928C0 (a hostile bolt landing, wall_damage_add(tile, 10, 100))."""
    if b.id not in g.buildings:
        return
    from ..systems import risk
    from .. import effects
    log(g, f"{NAMES[god.god]} destroys the {g.cat.spec(b.key)['name']} at ({b.x},{b.y})")
    effects.debris(g, b.x, b.y, b.size)          # collapse_debris_spawn(x, y, size, 1, 4, 0) (play mode only)
    if b.key == "palace":                        # type 0x75: building_footprint_to_rubble + every part (state 4)
        risk.to_rubble(g, b, f"destroyed by {NAMES[god.god]}")
    elif b.kind == "monument":
        g.demolish(b.id, f"destroyed by {NAMES[god.god]}")
    else:
        risk.collapse(g, b)


def _curse(g, w):
    """0x39 god_curse_building 0x004ED2A0: at the attack frame g_type_curse[type] = months << 4, B -1; the effect
    reaching the building: god_special_hit 0x004EDFC0 (houses, the palace)."""
    W = _W()
    b = g.buildings.get(w.target)
    if b is None:
        w.budget[1] -= 1
        return _enter(g, w, "wander")
    if w.step == 0:
        w.step, w.anim_t0, w.anim_kind = 1, g.tick, "cast"
        w.face = (b.x - w.x, b.y - w.y)
        return W.schedule(g, w, max(1, T()["attack_frame"][w.god] * tpf(w.god, 4)))   # the cast group at rate 100
    z = zid(g, b)
    n = curse(g, w.god, z)
    w.budget[1] -= 1
    log(g, f"{NAMES[w.god]} curses the {g.cat.spec(b.key)['name']}s (type {z}) for {n // 16} months")
    special_hit(g, w.god, z)
    w.anim_kind = ""
    return _enter(g, w, "wander")


def special_hit(g, i, z):
    """god_special_hit 0x004EDFC0: only for houses (2..14) and the palace."""
    if z not in HOUSES and z != PALACE:
        return
    st = state(g)
    if z == PALACE and i == 0:
        p = _palace(g)
        if p is not None:                        # building_destroyed_by_attack(palace tile): the palace to rubble
            log(g, "Zeus destroys the palace")
            from ..systems import risk
            from .. import effects
            effects.debris(g, p.x, p.y, p.size)
            risk.to_rubble(g, p, "destroyed by Zeus")
    if i == 12:                                  # Hera: every ordinary walker goes home (0x004EDE80)
        from ..systems import walkers
        for o in list(g.walkers.values()):
            if o.role not in ORDINARY_SKIP and o.role in _roamers():
                walkers.go_home(g, o)
    elif i == 11:                                # Hades: every ordinary walker dies, production stops
        from ..military import units
        for o in list(g.walkers.values()):
            if o.role not in ORDINARY_SKIP and o.anim != "die":
                units.kill(g, o)
        st["stop"] = max(st["stop"], 4)
    elif i == 8:                                 # Athena: towers and walls cursed
        curse(g, 8, 132)
        curse(g, 8, 130)
    elif i == 3:                                 # Apollo: plague_outbreak(0)
        from ..systems import health
        try:
            health.outbreak(g, "Apollo's attack")
        except Exception:                        # noqa: BLE001  (no house to infect)
            pass


def _roamers():
    from ..systems import services
    return set(services.SERVICES) | {"peddler", "trainee", "tax"}


def _kill(g, w):
    """0x44 god_kill_tick 0x004EFA50: per attack cycle (frames(Athena 4, else 2)) face the target and a bolt 0x34 at it
    (shot_frame); 3 cycles, one more, then (no bolt of the god flying) the target falls (action 4), C -1; a hero with a
    hall is sent home instead (no cost); a god or a figure in 0x50 is never killed (the god keeps shooting)."""
    from . import bolts
    W = _W()
    from ..military import units
    t = g.walkers.get(w.target)
    if t is None or t.anim == "die" or t.id not in g.walkers:
        w.budget[2] -= 1
        w.anim_kind = ""
        return _enter(g, w, "wander")
    if w.budget[2] < 1 and t.role != "god":
        w.target, w.anim_kind = 0, ""
        return _enter(g, w, "wander")
    k = 4 if w.god == 8 else 2
    n, p = frames(w.god, k), tpf(w.god, k)       # rate 100 (bug 393)
    sf = min(T()["shot_frame"][w.god], n - 1)
    if w.step == 0:
        if max(abs(t.x - w.x), abs(t.y - w.y)) > 4 and t.role != "god":   # not there yet: walk on to it
            w.path = _land_path(g, w, {(t.x + dx, t.y + dy) for dx in range(-4, 5) for dy in range(-4, 5)}) or []
            if not w.path:
                w.budget[2] -= 1
                return _enter(g, w, "wander")
            return W.schedule(g, w, 1)
        w.step, w.shots, w.anim_kind = 1, 3, "attack"
    if w.step == 1:
        w.face, w.anim_t0, w.step = (t.x - w.x, t.y - w.y), g.tick, 2
        return W.schedule(g, w, max(1, sf * p))
    if w.step == 2:
        bolts.shoot(g, w, (t.x, t.y), 0x34)
        w.step = 3
        return W.schedule(g, w, max(1, (n - 1 - sf) * p))
    if w.step == 3:
        w.shots -= 1
        if w.shots >= 0 or t.role == "god":    # 3 cycles and one more; at a god: on and on
            w.step = 1
            return W.schedule(g, w, p)
        w.step = 4
    if bolts.alive(g, w):
        return W.schedule(g, w, 2)
    if t.role == "hero":
        w.target = 0
        w.anim_kind = ""
        return _enter(g, w, "wander")
    log(g, f"{NAMES[w.god]} kills a {t.role} at ({t.x},{t.y})")
    units.kill(g, t, w)
    w.budget[2] -= 1
    w.anim_kind = ""
    return _enter(g, w, "wander")


def turn_on(g, w, defender):
    """A defender's 0x4B (0x004EAA60): the attacking god targets it with 0x44 (bolts; it cannot kill a god)."""
    if getattr(w, "phase", "") == "leave":
        return
    w.phase, w.target, w.step, w.path = "C", defender.id, 1, []
    w.shots, w.anim_kind = 3, "attack"
    _W().schedule(g, w, 1)


def driven_off(g, w):
    """A defender's 0x50 end: the attacking god's action 4 (as 0x0B: vanish where it stands, god_leave_release)."""
    from .figures import vanish
    release(g, w)
    w.phase = "gone"
    vanish(g, w, gated=True)                     # action 4: the vanish group at rate 100 (bug 393)


def army(g, w):
    """FUN_00504650 = enemy_army_spawn_land(type, 0 archers, 8 infantry, 0 horsemen, the map entry, 10, 0x8C) from
    god_attack_init: Artemis army type 4, Ares 10 (sim/military invaders: one company of 8, hidden and staggered)."""
    try:
        from ..military import invaders, state as mstate
    except ImportError:
        return
    n = 4 if w.god == 4 else 10
    st = mstate(g)
    st["serial"] = st.get("serial", 0) % 32000 + 1
    inv_id = st["serial"]
    e = tuple(g.world.entry)
    inv = dict(id=inv_id, ev=None, city=None, nation=n, point=e, companies=[], day=0, target=None, lead=None,
               start=g.tick, name=f"{NAMES[w.god]}'s army", god=w.god, target_class=10)
    invaders.invasions(g)[inv_id] = inv
    invaders.land_companies(g, inv_id, inv, {"infantry": 8}, e)
    w.army_inv = inv_id
    log(g, f"{NAMES[w.god]} brings an army of 8 (army type {n}) at {e}")


def release(g, w):
    """god_leave_release 0x004EF770: Ares -- every enemy infantry of army 10 retreats (action 3); Artemis -- army 4;
    Aphrodite / Dionysus -- their followers (0x004EF0F0) go back to walking."""
    i = w.god
    if i in (4, 5):
        try:
            from ..military import invaders
        except ImportError:
            return
        n = 4 if i == 4 else 10
        for inv_id, inv in list(invaders.invasions(g).items()):
            if inv.get("nation") == n and inv.get("god") == i:
                invaders._send_away(g, inv)
    if i in (6, 10):
        for fid in list(w.__dict__.get("chain", [])):
            f = g.walkers.get(fid)
            if f is not None and f.role == "entranced":
                _unfollow(g, f)


# --- entranced followers (0x47) -----------------------------------------------------------------------------------

def follower(g, w, kind):
    """god_follower_create 0x004EF150: a follower figure 0x47 'Entranced' (resource = the walker's type; Dionysus' own
    three: 0x44) at the god, appended to the god's chain (+0x5C next / +0x68 leader): its leader is the chain's last
    member, or the god; random start frame."""
    W = _W()
    chain = w.__dict__.setdefault("chain", [])
    chain[:] = [i for i in chain if i in g.walkers]
    f = W.new_walker(g, role="entranced", home=0, x=w.x, y=w.y, good=kind)
    f.leader = chain[-1] if chain else w.id
    f.fdest, f.ftimer = None, g.tick
    chain.append(f.id)
    W.add(g, f, 1)
    return f


def _mode10(g, start, goal):
    """Route mode 10 (figure_find_route 0x004D8220 -> route_bfs_military 0x0058B170 with both flags 0): BFS over
    grid_military, every tile but -1 / 1 (buildings) / -2; route_trace(4) first, so a 4-way path. The path (excluding
    start) or None."""
    from collections import deque
    from ..military import invaders
    gm, N = invaders.grid(g), 228
    if start == goal:
        return []
    prev = {start: None}
    q = deque([start])
    while q:
        t = q.popleft()
        for n in ((t[0], t[1] - 1), (t[0] + 1, t[1]), (t[0], t[1] + 1), (t[0] - 1, t[1])):
            if n in prev or not (0 <= n[0] < N and 0 <= n[1] < N) or gm[n[1] * N + n[0]] in (-1, 1, -2):
                continue
            prev[n] = t
            if n == goal:
                out = [n]
                while prev[out[-1]] != start:
                    out.append(prev[out[-1]])
                return list(reversed(out))
            q.append(n)
    return None


def follower_act(g, f):
    """fig_handler_piper_follower 0x004C9F30, once a tile (ours: tile steps): the follower walks (route mode 10) to its
    leader's tile, re-routed when the leader has moved and every 21 ticks; speed 8 while the leader is a tile or more
    away (Chebyshev), else 7. A leader that is gone, dying or not a god / follower: unchained (leader 0), the follower
    walks to the land entry and is removed there (the exe's state 2 on arrival, direction 8)."""
    W = _W()
    from ..military.units import tile_ticks as tt
    lead = g.walkers.get(getattr(f, "leader", 0) or -1)
    if lead is not None and (lead.role not in ("god", "entranced") or lead.anim == "die"):
        lead = None
    if lead is None:
        f.leader = 0
        e = tuple(g.world.entry)
        if (f.x, f.y) == e:
            return W.remove(g, f)
        goal = e
    else:
        goal = (lead.x, lead.y)
    path = f.__dict__.get("fpath")
    if goal != getattr(f, "fdest", None) or not path or g.tick - getattr(f, "ftimer", 0) >= 21:
        f.fdest, f.ftimer = goal, g.tick
        path = f.fpath = _mode10(g, (f.x, f.y), goal) or []
    if path:
        W.step_to(g, f, path.pop(0))
    elif lead is None:                           # no route to the entry: the exe's direction 10 (lost) removes it
        return W.remove(g, f)
    far = lead is not None and max(abs(lead.x - f.x), abs(lead.y - f.y)) > 0
    if not path and (f.x, f.y) == goal and lead is not None:
        return W.schedule(g, f, 1)               # on the leader's tile: checks again next tick
    W.schedule(g, f, tt(g, f, 8 if far or lead is None else 7))


def _unfollow(g, f):
    """0x004EF0F0 (god flag 0x10): the chain's followers die (state 2), except Dionysus' own satyrs (resource 0x44),
    which are only unchained (leader 0) and walk out by the land entry (follower_act)."""
    if f.good == "satyr":
        f.leader = 0
    else:
        _W().remove(g, f)


def _charm(g, w):
    """Aphrodite / Dionysus 0x40/0x41: roam 2400 units (+6 a tick: 400 ticks) with g_production_stop >= 1;
    walkers within 8 are entranced (deleted; their followers: presentation not ported), then out by the entry."""
    W = _W()
    from .figures import _roam, tile_ticks
    st = state(g)
    if not w.charm_t0:
        w.charm_t0 = g.tick
        W.sfx(g, w, "charm", g.tick + 400)       # god_entrance_roam_tick: FUN_004DB3D0(god, 0) every tick (atk1/2)
    if g.tick - w.charm_t0 >= 400:
        return _enter(g, w, "leave")
    st["stop"] = max(st["stop"], 1)
    if (g.tick - w.charm_t0) % 2 == 0:           # 0x004EF2F0 at even tile progress: walkers within 8 entranced
        for o in sorted(g.walkers.values(), key=lambda o: o.id):
            if o.role in _roamers() and o.anim != "die" and max(abs(o.x - w.x), abs(o.y - w.y)) <= 8:
                W.remove(g, o)                   # god_entrance_charm 0x004EF2F0: the walker is deleted
                follower(g, w, o.role)
                w.entranced = getattr(w, "entranced", 0) + 1
    if not _roam(g, w):
        return W.schedule(g, w, 15)
    return W.schedule(g, w, tile_ticks(g, w))


def _hermes(g, w):
    """0x45/0x46: the first caravan (figure 0x13) dies; none -> 0x47/0x48: at the palace (or the first building
    with road access) the treasury loses max(1000, treasury / 10) (0 when <= 1000). C never decreases."""
    W = _W()
    if w.step == 0:
        cv = next((t for t in sorted(g.walkers.values(), key=lambda t: t.id)
                   if t.role in ("trader", "donkey") and t.anim != "die"), None)
        if cv is not None:
            w.step, w.target, w.anim_t0, w.anim_kind = 1, cv.id, g.tick, "attack"
            # 0x46: timer = frames(2) ticks (hermes_caravan_anim_enter 0x004EFE80), not the frames: the attack group
            # plays at rate 100 meanwhile, so only frames / tpf of it show (bug 393)
            return W.schedule(g, w, frames(7, 2))
        b = _palace(g) or next((b for b in sorted(g.buildings.values(), key=lambda b: b.id) if b.access), None)
        if b is None:
            return _enter(g, w, "leave")
        w.step, w.target = 2, b.id
        w.path = _land_path(g, w, {tuple(b.access)}) or []
        return W.schedule(g, w, 1)
    if w.step == 1:
        cv = g.walkers.get(w.target)
        if cv is not None:
            from ..military import units
            log(g, f"Hermes kills a {cv.role}")
            units.kill(g, cv, None)
        w.step, w.anim_kind = 0, ""
        return W.schedule(g, w, 1)
    if w.step == 2:
        w.step, w.anim_t0, w.anim_kind = 3, g.tick, "cast"
        return W.schedule(g, w, frames(7, 4))  # 0x48: timer = frames(4) ticks (god_treasury_anim_enter 0x004EFFD0)
    c = g.city
    take = max(1000, c.treasury // 10) if c.treasury > 1000 else max(0, c.treasury)
    c.treasury -= take
    log(g, f"Hermes takes {take} dr from the treasury")
    w.anim_kind = ""
    return _enter(g, w, "wander")


def _aura(g, w):
    """god_hostile_aura 0x004EE0C0, once per animation cycle: Poseidon sinks boats, ships, triremes and kills urchin
    divers within 6; Hephaestus: houses within 4 get a 6 % chance of fire risk 1000 (at most 10)."""
    k = frames(w.god, 0)
    if (g.tick // k) == getattr(w, "aura_cycle", -1):
        return
    w.aura_cycle = g.tick // k
    if w.god == 1:
        from ..military import units
        for o in list(g.walkers.values()):
            if o.role in ("boat", "ship", "trireme", "diver") and max(abs(o.x - w.x), abs(o.y - w.y)) < 6:
                if o.anim != "die":
                    units.kill(g, o, None)
    elif w.god == 9:
        n = 0
        for b in g.buildings.values():
            if b.kind == "house" and abs(b.x - w.x) <= 4 and abs(b.y - w.y) <= 4:
                n += 1
                if rng(g).randrange(32768) % 100 <= 5:
                    b.fire_risk = 1000
                if n >= 10:
                    break


__all__ = ["init", "act", "GODS", "rec"]
