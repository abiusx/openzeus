"""God figures (figure type 0x43, handler 0x004C5D40): visits and blessings, help walks, attacks, fights.
docs/logic/religion.md ("God visits", "Attacking god behaviour", "God and priest figure handlers").

A god is a walker with role "god", w.god = god id, w.task = its action family:
  appear     action 10: the appearing animation, then w.next_task
  visit      actions 8/9: roams the roads (budget 0xF00 at speed 7), blessing buildings beside it
             (god_visit_bless_try 0x004C3CD0); bless = action 0x0C, the blessing animation
  leave      action 0x0B: the disappearing animation, then gone
  help_food  actions 0x15/0x17/0x1B: walks to the storage with the most room, carriers behind (presentation)
  attack     actions 0x36/0x37 (scenario) and 0x56 (jealous): the budgets A/B/C and the 6-month time budget,
             curses (0x38/0x39), A (0x3A/0x3B), C (0x43/0x44); leave 0x49
  fight      actions 0x4A/0x4B: a defender god walks at the attacker; god_fight_wins 0x004EE5B0
"""
from . import T, state, rec, rng, sanctuary, active, built, GODS, NAMES
from .month import log, curse

SPEED = 7                     # Figure_model col 8 of type 0x43
VISIT_TICKS = 0xF00 // SPEED  # +0x44 += speed a tick up to +0x42 = 0xF00 (forced every tick): 548 ticks of roaming
BUSY = frozenset(("help_food", "help", "strike", "precinct", "hades", "athena", "wine", "ares", "hera"))   # actions 0x0F..0x35 (god_figure_busy 0x004E75E0)
# init budgets per god (god_attack_init 0x004ECA10): A +0x120, B +0x132 (curses), C +0x12C, kind +0x13C
BUDGETS = {0: (3, 10, 10, 10), 1: (3, 10, 0, 1), 2: (3, 10, 10, 0), 3: (2, 10, 7, 6), 4: (2, 10, 10, 0),
           5: (4, 0, 10, 5), 6: (0, 0, 0, -1), 7: (0, 0, 10, 19), 8: (3, 10, 7, 3), 9: (2, 10, 5, 2),
           10: (0, 0, 0, -1), 11: (3, 10, 10, 4), 12: (3, 10, 10, 9), 13: (2, 10, 10, 2)}


def _walkers():
    from ..systems import walkers
    return walkers


def figure(g, i):
    """god_figure_get 0x004EA490: the god's figure if it is on the map, else clear the link and the attack slot."""
    r = rec(g, i)
    w = g.walkers.get(r["figure"]) if r["figure"] else None
    if w is None or w.role != "god" or getattr(w, "god", -1) != i:
        if r["figure"]:
            r["figure"] = 0
            r["attack_slot"] = -1
        return None
    return w


def tile_ticks(g, w):
    from ..military.units import tile_ticks as tt
    return tt(g, w, SPEED)


def nearest_road(g, x, y, r=228):
    """FUN_004D31E0 / road_tile_near_building: rings around (x, y) out to r, the first road tile (rows above and
    below, then the columns)."""
    road, n = _walkers().road_list(g), 228
    if 0 <= x < n and 0 <= y < n and road[y * n + x]:
        return (x, y)
    for k in range(1, r):
        x0, x1, y0, y1 = max(0, x - k), min(n - 1, x + k), max(0, y - k), min(n - 1, y + k)
        for yy in (y - k, y + k):
            if 0 <= yy < n:
                for xx in range(x0, x1 + 1):
                    if road[yy * n + xx]:
                        return (xx, yy)
        for xx in (x - k, x + k):
            if 0 <= xx < n:
                for yy in range(y0, y1 + 1):
                    if road[yy * n + xx]:
                        return (xx, yy)
    return None


def _spawn(g, i, x, y, task, home=0, **kw):
    """god_figure_spawn 0x004E8A30: create the god's figure (or move it) at (x, y); g_god_on_map = 1."""
    W = _walkers()
    w = figure(g, i)
    if w is not None:
        w.x, w.y, w.path, w.prev = x, y, [], None
    else:
        w = W.new_walker(g, role="god", home=home, x=x, y=y, good=GODS[i])   # good: the picture file (play mode)
        w.god = i
        w.uclass = 10 if rec(g, i)["unfriendly"] == 1 else 9      # figure_type_value(f, 0) of a god (0x004E1B20)
        W.add(g, w, 1)
        rec(g, i)["figure"] = w.id
    w.home = home
    w.task, w.next_task, w.anim_t0 = "appear", task, W.now(g)     # the tick of its first pass
    w.state = "held"                             # 0x0A / 0x0B: figure_tile_contact skips it (units.can_engage)
    for k, v in kw.items():
        setattr(w, k, v)
    state(g)["on_map"] = 1
    w.next_move = 0
    W.schedule(g, w, 10 + dur(i, 3))              # 0x0A: hidden 10 ticks (no tail), then the appear group at rate 100
    return w


def frames(i, k):
    from .attack import frames as f
    return f(i, k)


def dur(i, k):
    """A rate-100 look's length (attack.dur, bug 393)."""
    from .attack import dur as d
    return d(i, k)


def remove_all(g):
    W = _walkers()
    from . import ROLES
    for w in [w for w in g.walkers.values() if w.role in ROLES]:
        W.remove(g, w)


def _sanct_tile(g, b):
    from ..systems import monuments
    return monuments.road_entry(g, b) or b.access


# --- visits ---------------------------------------------------------------------------------------------------

def visit_start(g, i, b):
    """sanctuary_update's spawn: at the road tile near the sanctuary (road_tile_near_building(x, y, 20, 20); Hermes
    at the map entry, walking there), visit length 0xF00, action 10 -> 8."""
    t = nearest_road(g, b.x, b.y, 20)
    if t is None:
        return None
    if i == 7:
        e = g.world.entry
        w = _spawn(g, i, e[0], e[1], "visit", home=b.id)
        from ..systems import roads
        p = roads.path(g, tuple(e), {t})
        w.path = p or []
    else:
        w = _spawn(g, i, t[0], t[1], "visit", home=b.id)
    log(g, f"{NAMES[i]} visits the city at ({w.x},{w.y})")
    if i == 5:                                   # Ares: his Dragon (monster 7) at the sanctuary (sim/heroes, 1I)
        from .. import heroes
        heroes.guardian(g, 5, b, w)              # set_action(0x12): follows him (+0x68), flags |= 0x80
    return w


def _roam(g, w):
    """One road step, preferring a road not just walked (the generic roam: ours, the god's own memory)."""
    W = _walkers()
    road = W.road_list(g)
    x, y = w.x, w.y
    near = [t for t in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))
            if 0 <= t[0] < 228 and 0 <= t[1] < 228 and road[t[1] * 228 + t[0]]]
    opts = [t for t in near if t != w.prev] or near
    if not opts:
        return False
    mem = w.__dict__.setdefault("mem", {})
    old = min(mem.get(t, -1) for t in opts)
    opts = [t for t in opts if mem.get(t, -1) == old]
    nxt = opts[rng(g).randrange(len(opts))]
    mem[nxt] = g.tick
    W.step_to(g, w, nxt)
    return True


def affected(g, i, b):
    """god_building_affected 0x004E9310: the god's type list (Zeus: all of them; Aphrodite: inhabited houses without
    plague), not cursed, not burning (b+0x4A)."""
    from . import cursed
    if b.burning or cursed(g, b):
        return False
    if i == 6 or i == 0 and b.kind == "house":
        if b.kind == "house" and b.occupants > 0 and not b.misc.get("plague"):
            return True
        if i == 6:
            return False
    zid = g.cat.spec(b.key).get("zeus_id")
    types = T()["types"]
    if i == 0:
        return any(zid in v for v in types.values())
    return zid in types.get(GODS[i], [])


def bless_try(g, w):
    """god_visit_bless_try 0x004C3CD0: the 8 neighbour tiles from a random direction; the first not yet blessed
    building the god cares about, with chance bless_chance / size."""
    i = w.god
    chance0 = T()["bless_chance"][i]
    if not chance0:
        return False
    occ = g.world.occ
    d0 = rng(g).randrange(8)
    DIRS = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
    for k in range(8):
        dx, dy = DIRS[(d0 + k) % 8]
        x, y = w.x + dx, w.y + dy
        if not (0 <= x < 228 and 0 <= y < 228):
            continue
        bid = int(occ[y, x])
        b = g.buildings.get(bid)
        if b is None or b.misc.get("blessed"):
            continue
        if not affected(g, i, b):
            continue
        size = max(1, b.size or 1)
        if rng(g).randrange(32768) % 100 < chance0 // size:
            b.misc["blessed"] = 1
            w.task, w.anim_t0, w.face = "bless", g.tick, (dx, dy)
            w.visit_t0 = 0                       # 0x0C: a blessing restarts the visit clock (+0x44 = 0)
            log(g, f"{NAMES[i]} blesses the {g.cat.spec(b.key)['name']} at ({b.x},{b.y})")
            return True
    return False


# --- attacks ---------------------------------------------------------------------------------------------------

def attack_start(g, i):
    """god_attack_start 0x004F0EA0 (jealousy): at the road tile nearest the last composite building (sanctuaries,
    the palace; else the map centre), action 10 -> 0x56, the jealousy message (wooing0 / jealousy1 / jealousy2 by
    sanctuaries placed: 0, 1-2, 3+). The jealous god does not attack: 0x56 (FUN_004F1070) -> 0x57, whose enter
    (0x004F10D0) sets +0x44 = 0, +0x42 = 0xF00, next 0x0B; 0x57 (FUN_004F1300) is figure_roam_tick on the roads until
    +0x44 >= 0xF00, then 0x0B where it stands (Poseidon: dest home +-8 by the rng, on water). It woos: the message,
    no blessing, no curse, no destruction (a friendly record: no hostile aura). Oracle 1H-god: Athena appears at
    (166, 166) on the sandbox's entry road at tick 255 and walks it north until ~tick 816."""
    from . import count_sanctuaries
    comp = [b for b in g.buildings.values() if b.key.startswith("sanctuary_") or b.key == "palace"
            or b.key.startswith("pyramid_")]
    x, y = (max(comp, key=lambda b: b.id).x, max(comp, key=lambda b: b.id).y) if comp else (114, 114)
    t = nearest_road(g, x, y) if i != 1 else (x, y)
    if t is not None:
        x, y = t
    w = _spawn(g, i, x, y, "jealous")             # 10 -> 0x56 -> 0x57 (behaviour 0x00EF5DC0), not the 0x36 attack
    n = count_sanctuaries(g)
    base = JEALOUS[i] + (0 if n == 0 else 2 if n < 3 else 4)
    from .. import messages
    try:
        from . import voice                      # god_attack_message 0x004F1110: kind 2 / 1 / 0 by sanctuaries
        messages.post(g, base, base + 1, voice=voice(g, i, 2 if n == 0 else 1 if n < 3 else 0),
                      meta=dict(at=[x, y], kind=0xDE) if w is not None else None)   # FUN_00521A70(0xDE, 0, the god's tile)
    except KeyError:
        g.message(f"{NAMES[i]} is jealous and attacks the city")
    if w is not None:                            # god_attack_start: alert 12 "go to god" at the spawn tile
        from .. import alerts
        alerts.raise_alert(g, alerts.GOD, (x, y))
    log(g, f"{NAMES[i]} (jealous) appears at ({x},{y}): roams the roads {VISIT_TICKS} ticks, no harm")
    return w


JEALOUS = {0: 0x534, 1: 0x540, 2: 0x558, 3: 0x570, 4: 0x57C, 5: 0x588, 6: 0x5A0, 7: 0x5AC, 8: 0x564, 9: 0x594,
           10: 0x5B8, 11: 0x54C, 12: 0xD95, 13: 0xDA1}


def attack_arrive(g, i, at, scenario_event=False):
    """event_god_attack's arrival: action 10 -> 0x36, budget A = 3 (god_attack_init then sets the god's budgets);
    Hermes appears at the land entry and walks to the arrival tile."""
    if i == 7:
        e = g.world.entry
        w = _spawn(g, i, e[0], e[1], "attack")
        from ..systems import roads
        w.path = roads.path(g, tuple(e), {tuple(at)}) or []
    else:
        w = _spawn(g, i, at[0], at[1], "attack")
    return w


def send_defender(g, i, attacker, at):
    """event_god_attack's defenders (each only with a built sanctuary): Zeus against any god; else Aphrodite against
    Ares, Hephaestus, Hermes, Dionysus; else Hera against Zeus. The defender comes out at its sanctuary (or, on the
    map, only when god_can_fight) and shoots at the attacker (0x4A/0x4B, then 0x50: it drives the attacker off;
    sim/gods/fight.py)."""
    from . import fight
    d = -1
    if built(g, 0) and i != 0:
        d = 0
    elif built(g, 6) and i in (5, 9, 7, 10):
        d = 6
    elif built(g, 12) and i == 0:
        d = 12
    if d < 0:
        return None
    w = figure(g, d)
    if w is not None and not fight.can_fight(w):
        return None
    return fight.defend(g, d, attacker, w=w)


def power(i):
    return T()["power"][i]


def fight_wins(g, a, b):
    """god_fight_wins 0x004EE5B0: Aphrodite (active) beats Ares, Hephaestus, Hermes, Dionysus; Hera (active) beats
    Zeus; else the higher god_power."""
    if a == 6 and active(g, 6) and b in (5, 9, 7, 10):
        return True
    if b == 6 and active(g, 6) and a in (5, 9, 7, 10):
        return False
    if a == 12 and active(g, 12) and b == 0:
        return True
    if b == 12 and active(g, 12) and a == 0:
        return False
    return power(a) > power(b)


def _go_home(g, w):
    """0x14 / 0x3D: back to a road tile by the sanctuary (no blessing on the way), then vanish."""
    W = _walkers()
    b = g.buildings.get(w.home)
    t = nearest_road(g, b.x, b.y, 20) if b is not None else None
    from ..systems import roads
    p = roads.path(g, (w.x, w.y), {t}) if t else None
    if not p:
        return _leave(g, w)
    w.task, w.path = "home", p
    w.no_bless = True
    return W.schedule(g, w, 1)


# --- help -----------------------------------------------------------------------------------------------------

def out_of_sanctuary(g, i):
    """god_figure_spawn at the sanctuary (FUN_0053FBE0: ours its road entry) when the god is not on the map."""
    w = figure(g, i)
    if w is not None:
        return w
    b = sanctuary(g, i)
    if b is None:
        return None
    t = _sanct_tile(g, b)
    if t is None:
        return None
    return _spawn(g, i, t[0], t[1], "help", home=b.id)


def start_food_help(g, w, i):
    """0x004C4910 (Poseidon) / 0x004C4F20 (Demeter) / 0x004C5420 (Artemis): the food (of the god's) the best
    storage has the most room for; gift = min(room, 3200; Artemis 2400); ceil(gift / 400) carriers behind the god; the
    rest of the 3200 (2400) goes in through god_gifts_deliver (help.deliver_gifts); the god walks
    to the storage's road tile (action 0x18) and the goods go in there."""
    from .help import FOODS, best_store
    best = (None, None, 0)
    for good in FOODS[i]:
        if good not in g.cat.resources:
            continue
        s, room = best_store(g, good)
        if s is not None and room > best[2]:
            best = (good, s, room)
    good, s, room = best
    if s is None:
        w.next_task = "leave" if w.task == "appear" else w.next_task
        w.task = "leave" if w.task != "appear" else w.task
        return
    cap = 2400 if i == 4 else 3200                    # 0x960 Artemis, 0xC80 Poseidon / Demeter
    w.help_good, w.help_store, w.amount = good, s.id, min(room, cap)
    w.carriers = (w.amount + 399) // 400
    from .help import gift_leftover                   # gift_amount_1 = cap - gift: god_gifts_deliver puts it in
    gift_leftover(g, i, cap - w.amount, 0)
    if w.task == "appear":
        w.next_task = "help_food"
    else:
        w.task = "help_food"
    from ..systems import roads
    w.path = roads.path(g, (w.x, w.y), {tuple(s.access)}) or []


def _help_food_act(g, w):
    W = _walkers()
    if w.path:
        W.step_to(g, w, w.path.pop(0))
        return W.schedule(g, w, tile_ticks(g, w))
    s = g.buildings.get(getattr(w, "help_store", 0))
    if s is not None:
        from ..systems import economy
        n = min(w.amount, economy.storage_room(g, s, w.help_good))
        if n > 0:
            s.goods[w.help_good] = s.goods.get(w.help_good, 0) + n
        log(g, f"{NAMES[w.god]} brings {n} {w.help_good} to the {g.cat.spec(s.key)['name']} at ({s.x},{s.y})")
    w.amount = 0
    w.carriers = 0
    return _go_home(g, w)


def athena_month(g):
    """0x004E6340: an invasion on -> Athena out to fight it (fight.py)."""
    from . import fight
    return fight.athena_month(g)


def apollo_month(g):
    """0x004E6440: a bad monster on the map -> Apollo fights it (fight.py)."""
    from . import fight
    return fight.apollo_month(g)


# --- the handler ------------------------------------------------------------------------------------------------

def _leave(g, w, gated=False):
    """0x0B: the vanish group (rate 0: one frame a tick), then deleted. gated: action 4 (driven off, Zeus' strike
    done), the same end but the tail steps the vanish group at rate 100 (bug 393)."""
    W = _walkers()
    w.task, w.anim_t0, w.path = "leave", g.tick, []
    w.state = "held"
    w.gated = gated
    W.schedule(g, w, dur(w.god, 1) if gated else frames(w.god, 1))


vanish = _leave


def act(g, w):
    W = _walkers()
    t = w.task
    if t == "appear":
        w.state = ""
        w.task = getattr(w, "next_task", "visit") or "visit"
        if w.task == "attack":
            from . import attack
            return attack.init(g, w)
        if w.path:
            return W.schedule(g, w, 1)
        return W.schedule(g, w, 1)
    if t == "leave":
        if w.__dict__.get("phase") is not None:   # an attacking god: god_leave_release at the end of 0x0B
            from . import attack
            attack.release(g, w)
        if w.id == rec(g, w.god)["figure"]:
            rec(g, w.god)["figure"] = 0
            rec(g, w.god)["attack_slot"] = -1
        return W.remove(g, w)
    if t == "bless":
        w.task = "visit"
        return W.schedule(g, w, 1)
    if t == "ares":                              # 0x22 / 0x23: Ares away with an expedition (aid.py)
        from . import aid
        return aid.ares_act(g, w)
    if t == "ares_home":                         # 0x14 after the battle: hidden cleared, home, then 0x0B
        w.hidden = False
        return _go_home(g, w)
    if t == "visit":
        return _visit_act(g, w)
    if t == "jealous":
        return _jealous_act(g, w)
    if t == "home":                              # 0x09: walk to the road tile near the sanctuary, then vanish
        from . import fight
        if fight.walk_interrupt(g, w):
            return None
        if w.path:
            W.step_to(g, w, w.path.pop(0))
            if not getattr(w, "no_bless", False) and bless_try(g, w):
                return W.schedule(g, w, dur(w.god, 4))
            return W.schedule(g, w, tile_ticks(g, w))
        return _leave(g, w)
    if t in ("visit", "jealous", "attack", "hunt", "help_food") and _encounter(g, w):
        return None
    if t == "attack":
        from . import attack
        return attack.act(g, w)
    if t == "help_food":
        return _help_food_act(g, w)
    if t in ("hunt", "defend"):
        from . import fight
        return fight.act(g, w)
    if t == "duel":
        from . import fight
        return fight.duel(g, w)
    if t in ("strike", "precinct", "hades", "athena", "wine", "hera"):   # help actions 0x0F..0x13, 0x19/0x1A, 0x25..0x32 (gifts.py)
        from . import gifts
        return gifts.act(g, w)
    return _leave(g, w)


def _encounter(g, w):
    """god_encounter_check 0x004EE2B0 at animation frame 1, i.e. once per walk cycle (frames(0) ticks)."""
    c = g.tick // frames(w.god, 0)
    if c == w.__dict__.get("enc_cycle"):
        return False
    w.enc_cycle = c
    from . import fight
    return fight.encounter_check(g, w)


def _jealous_act(g, w):
    """0x57 (FUN_004F1300): road roam, +0x44 += speed a tick, at 0xF00 the vanish (0x0B) where it stands."""
    W = _walkers()
    if not getattr(w, "visit_t0", 0):
        w.visit_t0 = g.tick
    if g.tick - w.visit_t0 >= VISIT_TICKS:
        return _leave(g, w)
    if w.god == 1 or not _roam(g, w):            # ours: Poseidon's water wander (home +-8) is not ported: he stays
        return W.schedule(g, w, 15)
    return W.schedule(g, w, tile_ticks(g, w))


def _visit_act(g, w):
    """0x08: road roam with +0x44 += speed a tick and god_visit_bless_try; at 0xF00: action 9 to a road tile within
    20 of the sanctuary (none: vanish here)."""
    W = _walkers()
    if w.path:                                   # Hermes from the land entry
        W.step_to(g, w, w.path.pop(0))
        return W.schedule(g, w, tile_ticks(g, w) // 3 or 1)
    from . import fight
    if fight.walk_interrupt(g, w):               # god_walk_interrupt 0x004EBA10 (Apollo, Athena, Hera)
        return None
    if not getattr(w, "visit_t0", 0):
        w.visit_t0 = g.tick
    if g.tick - w.visit_t0 >= VISIT_TICKS:
        b = g.buildings.get(w.home)
        t = nearest_road(g, b.x, b.y, 20) if b is not None else None
        if t is None:
            return _leave(g, w)
        from ..systems import roads
        w.task, w.path = "home", roads.path(g, (w.x, w.y), {t}) or []
        return W.schedule(g, w, 1)
    if not _roam(g, w):
        return W.schedule(g, w, 15)
    if bless_try(g, w):
        return W.schedule(g, w, dur(w.god, 4))   # 0x0C: the cast group at rate 100 to its last frame
    return W.schedule(g, w, tile_ticks(g, w))


def look(g, w):
    """Play mode: [kind, t0, end, fx, fy, 0, 0, 0, block, False]; blocks: appear / leave (vanish) / bless (cast) /
    attack / cast (curse, Hermes' drain)."""
    i = w.god
    f = getattr(w, "face", None) or (0, 1)
    f = ((f[0] > 0) - (f[0] < 0), (f[1] > 0) - (f[1] < 0))
    if getattr(w, "hidden", False):              # Figure+0x65 (Ares away; his appear after the battle)
        return ["hidden", 0, 0, 0, 0, 0, 0, 0, "", False]
    if w.task == "ares":                         # 0x22: the vanish group, written directly (no sound)
        return ["work", w.anim_t0, w.anim_t0 + frames(i, 1), f[0], f[1], 0, 0, 0, "vanish", False]
    if w.task == "appear":
        return ["work", w.anim_t0 + 10, w.anim_t0 + 10 + dur(i, 3), f[0], f[1], 0, 0, 0, "appear", False]
    if w.task == "leave":
        if getattr(w, "gated", False):           # action 4: rate 100
            return ["work", w.anim_t0, w.anim_t0 + dur(i, 1), f[0], f[1], 0, 0, 0, "vanish_gated", False]
        return ["work", w.anim_t0, w.anim_t0 + frames(i, 1), f[0], f[1], 0, 0, 0, "vanish", False]
    if w.task == "bless":
        return ["work", w.anim_t0, w.anim_t0 + dur(i, 4), f[0], f[1], 0, 0, 0, "cast", False]
    if w.task in ("hunt", "defend", "duel"):
        from . import fight
        return fight.look(g, w)
    if w.task in ("strike", "precinct", "hades", "athena", "wine", "hera"):
        from . import gifts
        return gifts.look(g, w)
    k = getattr(w, "anim_kind", "")
    if w.task == "attack" and k and not w.path:
        if k == "attack" and i == 8:             # Athena's 0x3B / 0x44: her cast group (the tail's LAB_004c82d3)
            k = "cast"
        return ["work", w.anim_t0, w.next_move, f[0], f[1], 0, 0, 0, k, False]
    return None
