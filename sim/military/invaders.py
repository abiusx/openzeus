"""Invading armies on the city map (docs/logic/military.md "Invaders on the map", "End of an invasion", "Bribe").

invade(g, ev) (sim/empire/war.py when a rival's invasion arrives, or the `invade` test command) spawns the army at a
land invasion point of the map (`invasion_point_select` 0x00503E20; the scenario's 8 points 0x00902C10/30):
companies of 8 per class (`enemy_army_spawn_land` 0x00504650: infantry/missile/cavalry counts = the army's
frequency column x strength / 100), each soldier hidden at the point until its delay (j+1 + company*20)*10 ticks
or, sooner, 51 ticks after its company's first go-attack (action 10 -> 7 with timer 50; oracle 1B-inv-land).

Each soldier (enemy_figure_update 0x00500B70): "wait" (7: re-aims every 30 ticks at its slot = company target +
layout offset), "march" (9), "hunt" (13: the nearest soldier, when its company is engaged), "shoot" (archers, 6),
"leave" (3: to the map exit, gone there). Route mode 2: a weighted route that cuts through buildings (+10), walls
(+40), towers and gatehouses (+60); in front of one it stands and hits the tile (13 hits in 51 ticks): a building
falls past 10 damage, a wall tile past 200, a tower/gatehouse tile past 400 (wall_damage_add 0x00492830). Tile
contact: invaders fight soldiers, citizens (helpless walkers), criminals and wolves on the tiles they enter.

The company AI (daily at cycle step 29, FUN_00500910 -> 0x004FFFD0; military.step29): the lead company picks the target (player troops within 16 tiles, else the
palace if reachable, else the nearest building of the earliest type in its class list TARGETS 0x006383E0); a 32-day
muster near the lead; then cycles of march (m days), gather (g) and halt (h). Mode machine on +0x75 (special roll,
attack, morale check: regroup at low morale, never a rout).
End (cities_relations_update 0x00568C20, daily): E = invaders weighted 1 archer / 2 infantry / 3 cavalry, P = the
player's ready companies in the city weighted rabble 1 / hoplite 2 / horseman 3: E > 3P after hitting the palace
(or no palace) -> defeat (the city pays tribute; a second defeat by the same city loses the game); 8E < P and
E == 0 -> the army withdraws (victory). Bribe: `bribe` pays invasion_bribe_cost 0x00476CF0 and they leave.
Each soldier walks its own route mode 2 route (imove: route_search + route_trace(8), figure_route_walk sub-steps;
docs/logic/military.md "Invaders' walking per figure"). Sea invasions: navy.py.
"""

from ..systems import walkers, index
from . import units, contact, mrng, state

TYPES = ("enemy_infantry", "enemy_archer", "enemy_cavalry")
CLASS_ROLE = {"infantry": "enemy_infantry", "missile": "enemy_archer", "cavalry": "enemy_cavalry"}
WEIGHT = {"enemy_archer": 1, "enemy_infantry": 2, "enemy_cavalry": 3}
PWEIGHT = {"rabble": 1, "hoplite": 2, "horseman": 3}
BRIBE_MUL = [1, 3, 4, 5, 7]                  # f64 table 0x00633280 by difficulty
N = 228
BLOCK = 0x4 | 0x2 | 0x200 | 0x80000 | 0x4000000     # water, rock, cliff, off-map, deep water: never entered
DIRS8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
LAYOUT_BY_FACING = {0: 1, 2: 2, 4: 17, 6: 16}


def invasions(g):
    return state(g).setdefault("invasions", {})


def ecomps(g):
    return state(g).setdefault("ecomps", {})


def land_points(g):
    """The map's 8 land invasion points (g_invasion_points 0x00902C10 / 0x00902C30 slots 0..7), raw (World.points)."""
    return g.world.points["land_invasion"]


def pick_point(g, pt=8):
    """invasion_point_select 0x00503E20 (land): 8 = random among the valid ones; else pt-1, then the next valid."""
    pts = land_points(g)
    valid = [p for p in pts if p is not None]
    if not valid:
        return tuple(g.world.entry)
    if pt == 8:
        n = len(valid)
        r = mrng(g).randrange(128)
        i = r & (1 if n <= 2 else 3 if n <= 4 else 7)
    else:
        i = max(0, pt - 1)
    for k in range(8):
        p = pts[(i + k) % 8]
        if p is not None:
            return p
    return valid[0]


def facing_of(g, p):
    """enemy_army_spawn_land 0x00504650: the facing from the point's logical position: y == 0 -> 4, y >= H-1 -> 0,
    x == 0 -> 2, x >= W-1 -> 6, else 4 (W, H = scenario block +0x2C / +0x30, World.size)."""
    w = g.world
    x, y = p[0] - w.origin[0], p[1] - w.origin[1]
    W, H = w.size
    if y == 0:
        return 4
    if y >= H - 1:
        return 0
    if x == 0:
        return 2
    if x >= W - 1:
        return 6
    return 4


def split8(n):
    """Companies of 8; the last two share the remainder (r+8) - (r+8)//2 and (r+8)//2."""
    n = min(n, 256)
    if n <= 0:
        return []
    full, r = divmod(n, 8)
    if r == 0:
        return [8] * full
    if full == 0:
        return [r]
    return [8] * (full - 1) + [(r + 8) - (r + 8) // 2, (r + 8) // 2]


def invade(g, ev, point=None, army=None, strength=None, target_class=10, sea_pt=None, quiet=False):
    """Spawn an invasion. ev: the empire event dict (or None for a test army). sea_pt (9..16): by sea
    (invasion_spawn_sea 0x503FD0, sim/military/navy.py: warships and transports that land at the landing point).
    quiet: no message (the caller posts the exe's, e.g. a scenario invasion: sim/empire/invasion_events.py).
    Returns the invasion id."""
    d = units.data()["difficulty"][g.rules.get("difficulty", "Normal")]
    nation = army if army is not None else _nation(g, ev)
    nation = max(0, min(10, nation))
    rows = d["armies"][nation]
    s = min(strength if strength is not None else (ev.get("amount", 0) if ev else 16), 256)
    counts = {k: rows[k]["frequency"] * s // 100 for k in ("infantry", "missile", "cavalry")}
    st = state(g)
    st["serial"] = st.get("serial", 0) % 32000 + 1
    inv_id = st["serial"]
    if sea_pt is not None:
        from . import navy
        if navy.has_sea_invasions(g):
            p = navy.sea_points(g)[0][max(0, sea_pt - 9) % 8] or next(x for x in navy.sea_points(g)[0] if x)
            inv = dict(id=inv_id, ev=ev["id"] if ev else None, city=ev.get("city") if ev else None, nation=nation,
                       point=p, companies=[], day=0, target=None, lead=None, start=g.tick,
                       name=_city_name(g, ev), target_class=target_class)
            invasions(g)[inv_id] = inv
            navy.invade_sea(g, inv_id, nation, s, sea_pt, (ev or {}).get("landing", 0), (ev or {}).get("ships"))
            st["last_enemy"] = g.tick
            from .. import alerts                       # invasion_event_month: alert 9 at the tile the spawn returns
            alerts.raise_alert(g, alerts.INVASION, p)
            if not quiet:
                g.message(f"Ships carrying an army of {sum(counts.values())} from {inv['name']} have been sighted at "
                          f"({p[0]},{p[1]})!")
            return inv_id
    p = point or pick_point(g, 8)
    inv = dict(id=inv_id, ev=ev["id"] if ev else None, city=ev.get("city") if ev else None, nation=nation,
               point=p, companies=[], day=0, target=None, lead=None, start=g.tick,
               name=_city_name(g, ev))
    invasions(g)[inv_id] = inv
    land_companies(g, inv_id, inv, counts, p)
    from .. import alerts                               # invasion_event_month: alert 9 at the invasion point
    alerts.raise_alert(g, alerts.INVASION, p)
    total = sum(counts.values())
    if not quiet:
        g.message(f"An army of {total} from {inv['name']} has arrived at ({p[0]},{p[1]})! Bribe: {bribe_cost(g, inv_id)} dr "
                  f"(`bribe`).")
    return inv_id


def land_companies(g, inv_id, inv, counts, p):
    """enemy_army_spawn_land 0x00504650: companies of 8 per class (infantry, missile, cavalry), each soldier hidden
    at p until its delay (j+1 + company*20)*10. Also the transports' unloading (navy.unload)."""
    st = state(g)
    nation = inv["nation"]
    facing = facing_of(g, p)
    seq = 0
    for cls in ("infantry", "missile", "cavalry"):
        for size in split8(counts.get(cls, 0)):
            cid = st.get("next_ecomp", 35)
            st["next_ecomp"] = cid + 1
            comp = dict(id=cid, inv=inv_id, cls=cls, ids=[], layout=LAYOUT_BY_FACING[facing], facing=0,
                        mode=0, countdown=0, morale=100, A=0, B=0, C=0, days=0, engaged=0, firing=0, under=0,
                        under_from=0, target=tuple(g.world.origin), pos=p, leave=False, noreach=0, rot=0)
            ecomps(g)[cid] = comp
            inv["companies"].append(cid)
            for j in range(size):
                delay = (j + 1 + seq * 20) * 10
                # a hidden archer in action 7 tries to shoot every tick (0x00500DAB): it acts from the next tick on
                w = units.spawn(g, CLASS_ROLE[cls], p[0], p[1], delay=1 if cls == "missile" else delay, company=cid,
                                slot=j, task="wait",
                                army=nation, good=f"army{nation}", hidden=True, timer=0, face=_dir(facing),
                                next_shot=0, inv=inv_id)
                # the timer (+0x36) runs from its first update: in this tick's pass when the pass is still to reach
                # its slot (walkers.add), so it runs out in update number `delay` (oracle 1B-inv-land: a delay of 10
                # from a spawn before tick 815's pass shows timer 22 at tick 833)
                ps = g.__dict__.get("_pass")
                first = g.tick + 1 if ps is not None and w.fslot <= ps[1] else g.tick
                w.appear = first + delay - 1
                if cls == "missile":                 # the reload (+0x6B) counts from its first update: 1 then,
                    w.next_shot = first + units.col(g, w, "missile_rate")   # past col 7 col7 updates later
                comp["ids"].append(w.id)
            seq += 1
    st["last_enemy"] = g.tick
    st["months_since_enemy"] = 0                 # each spawned company resets g_months_since_enemy


def _nation(g, ev):
    e = getattr(g, "empire", None)
    if ev and e is not None and ev.get("city") in e.cities:
        return getattr(e.cities[ev["city"]], "nation", 0) or 0
    return 0


def _city_name(g, ev):
    e = getattr(g, "empire", None)
    if ev and e is not None and ev.get("city") in e.cities:
        return e.cities[ev["city"]].name
    return "a rival city"


def _dir(f):
    return DIRS8[f & 7]


# --- grid_military -------------------------------------------------------------------------------------------

def obstacle(g, x, y):
    """grid_military: 0 open, 1 building, 3 wall, 4 tower/gatehouse tile; None = impassable."""
    v = grid(g)[y * N + x]
    return None if v < 0 else v


def grid(g):
    """grid_military (sim/military/routes.grid)."""
    from . import routes
    return routes.grid(g)


# --- route mode 2, per figure (enemy_figure_update 0x00500B70 writes +0x72 = 2 every tick, 0x00500BBF) ---------

def free_route(w):
    """figure_route_free 0x004D8990: route_id 0. The next figure_route_walk 0x004D7BD0 finds a new route
    (figure_find_route 0x004D8220 case 2: route_search + route_trace(8)), which sets the tile progress to 15: the
    figure takes its next route decision from the tile it is on at once (a step under way is abandoned)."""
    w.iroute = None


def _substeps(w, code):
    """figure_move 0x004D1170: the sub-steps of figure_route_walk this tick by speed code, speed_phase (+0x2B) kept
    per figure (navy.PATTERN; infantry / archers 6: 1 a tick, cavalry 11: 2, 2, 2, 1)."""
    from .navy import PATTERN
    if code <= 0:
        return 0
    if code in (6, 12) or code >= 18:
        return {6: 1, 12: 2}.get(code, 3)
    lim, a, b = PATTERN[code]
    ph = w.__dict__.get("sph", 0)
    if ph < lim:
        w.sph = ph + 1
        return a
    w.sph = 0
    return b


def _fight_ahead(g, tile):
    """figure_check_next_tile 0x004D8BB0 for types 0x28..0x2A (0x3F / 0x40 too): the first figure on the next tile by
    FUN_004DCE40 (tile-list order; not dying, not of types 0, 6, 0xA, 0xE, 0x22, 0x23, 0x28..0x2A, 0x2D, 0x34, 0x3F,
    0x40; a god only of class 9, a monster only of class 7) in action 5 -> direction 9 (blocked)."""
    fs = units.fighting(g)
    ws = g.walkers
    if not any(i in ws and ws[i].x == tile[0] and ws[i].y == tile[1] for i in fs):
        return False
    from types import SimpleNamespace
    from .defences import victim
    f = victim(g, SimpleNamespace(x=tile[0], y=tile[1]), 0x34)
    return f is not None and f.anim == "fight"


def _check_next(g, w, nxt):
    """figure_check_next_tile 0x004D8BB0, route mode 2: a fight on the tile -> 9; grid_military < 0 -> 9; 0, 5, a
    ramp 2 -> on; 1 (building), 3 (wall), 4 (tower / gatehouse), 2 off a ramp -> 11 (it stands and hits: _siege).
    Returns None (go on), 9 or 11."""
    if _fight_ahead(g, nxt):
        return 9
    o = obstacle(g, *nxt)
    if o is None:
        return 9
    if o in (1, 3, 4):
        _siege(g, w, nxt, o)
        return 11
    return None


def tile_ticks(g, w):
    """Ticks of a tile's 15 sub-steps at the figure's speed (play mode: the step drawn over them)."""
    num, den = units.SPEED[max(0, min(18, units.col(g, w, "speed")))]
    return max(1, -(-15 * den // num)) if num else 15


def imove(g, w, dest):
    """figure_move 0x004D1170 -> figure_route_walk 0x004D7BD0 for an invader, one call a tick: with no route
    (route_id < 1) figure_find_route (routes.route2 from its tile to dest; found: tile progress +0x39 = 15); then per
    sub-step progress + 1; past 14 (the tile centre): figure_route_next_dir (route used up: route freed, 8 arrived)
    and figure_check_next_tile (9 blocked / 11 siege: it stands at the centre, the route kept), else the next
    direction, progress 0; at progress 8 the tile changes (figure_change_tile: the tile contact). No route found:
    direction_to(here, dest): 8 on its own tile, else 10 (lost). Returns None (on its way), 8, 9, 10, 11 or
    "fight" (a contact at the tile change started one)."""
    from . import routes
    dest = tuple(dest)
    route = w.__dict__.get("iroute")
    prog = w.__dict__.get("fprog", 15)
    n = _substeps(w, units.col(g, w, "speed"))
    if n <= 0:
        return None
    if route is None:
        here = (w.x, w.y)
        p = None
        if here != dest and 0 <= dest[0] < N and 0 <= dest[1] < N:
            p = routes.route2(g, here, dest)
        if not p:                                  # route_trace of length 0 / no route: route_id stays 0
            w.iroute = None
            return 8 if here == dest else 10
        route, prog = list(p), 15
    for _ in range(n):
        prog += 1
        if prog > 14:
            prog = 15
            if not route:
                w.iroute, w.fprog = None, 15
                return 8
            nxt = route[0]
            r = _check_next(g, w, nxt)
            if r is not None:
                w.iroute, w.fprog = route, 15
                return r
            route = route[1:]
            w.heading = nxt
            w.face = ((nxt[0] > w.x) - (nxt[0] < w.x), (nxt[1] > w.y) - (nxt[1] < w.y))
            prog = 0
        if prog == 8:
            units.step(g, w, w.heading)
            w.step_draw = (g.tick, g.tick + tile_ticks(g, w))   # play mode: the step drawn over 15 sub-steps
            if contact.on_enter(g, w):
                w.iroute, w.fprog = route, prog
                return "fight"
    w.iroute, w.fprog = route, prog
    return None


# --- soldiers -------------------------------------------------------------------------------------

def act(g, w):
    if w.anim == "die":
        return units.act_dying(g, w)
    if w.anim == "fight":
        return units.fight_tick(g, w)
    comp = ecomps(g).get(getattr(w, "company", 0))
    if comp is None:
        return units.remove(g, w)
    if w.task == "leave":
        return _leave(g, w)
    if w.task == "attack":                         # action 10 (0x00500FE5), every tick: company not engaged -> 7
        w.task = "attack10" if comp["engaged"] else "attack7"     # (it stays there), then the hunt step (0x00500FF2)
        _pause(g, w, 1)                            # this tick runs action 10, not 7: its +0x36 timer (a hidden one's
                                                   # appearance) does not count (oracle 1B-inv-city: company 35's
                                                   # timers 50 at dumps 315 and 316, the go-attack's tick)
    archer = w.role == "enemy_archer"
    if archer and in_shot(w):                      # action 6 (0x005011C0 + the picture tail): the shot to its wrap
        return _shot_tick(g, w)
    if w.hidden and g.tick < getattr(w, "appear", 0) and w.task == "wait":     # action 7, its timer running
        if archer:
            return _hidden_archer(g, w, comp)
        if _charge(g, w, comp):                    # mode-2 cavalry: the hold's charge (0x00500DD5), hidden too
            return walkers.schedule(g, w, 1)
        return walkers.schedule(g, w, _hold_wake(g, w, comp, w.appear) - g.tick)
    if w.hidden and g.tick >= getattr(w, "appear", 0):     # action 7's timer (+0x36) ran out: it appears
        w.hidden = False
        w.aim_due = w.appear
        if comp.get("first_seen") is None:
            comp["first_seen"] = g.tick
    if w.task in ("attack7", "attack10"):          # the hunt step of action 10 (0x00500FF2: try_shoot first); only
        keep = "wait" if w.task == "attack7" else "attack"        # the cavalry charge sets action 13 (0x00500E55)
        w.task = keep
        if archer and _try_shoot(g, w, comp):
            return None
        return _hunt(g, w, comp, keep)
    if w.task == "hunt":                           # action 13 (0x00500FF2): try_shoot, then the hunt, every tick
        if archer and _try_shoot(g, w, comp):
            return None
        return _hunt(g, w, comp)
    if w.task == "disengage":                      # action 11 (cavalry): to the free spot, then 7
        return _disengage_walk(g, w, comp)
    if w.task == "march":                          # action 9 (0x00500EC0)
        return _march(g, w, comp)
    return _hold(g, w, comp)                       # action 7 (0x00500C9E)


def _due(g, w):
    """The next tick the +0x36 timer (re-aim) runs out: action 7 and 9 count it down every tick (not 5 / 6)."""
    return getattr(w, "aim_due", 0) or 0


MOVING = ("march", "hunt", "disengage", "leave")


def _hold(g, w, comp):
    """Action 7 (0x00500C9E): figure_route_free every tick; timer (+0x36) - 1; at <= 0: 30 again, then company engaged
    -> action 10 (the hunt from the next tick); else dest = the slot's spot (company target + layout offset); not there
    (direction_to < 8) -> action 9 (figure_move from the next tick). Every tick then: archers try to shoot
    (0x005009E0), mode-2 cavalry charge a soldier within col 12 (0x00500DD5)."""
    free_route(w)
    if g.tick >= _due(g, w):
        w.aim_due = g.tick + 30
        if comp["engaged"]:
            w.task = "attack"
        else:
            goal = slot_dest(comp, w.slot)
            w.dest = goal
            if (w.x, w.y) != goal:
                _start_march(g, w)
    if w.role == "enemy_archer" and _try_shoot(g, w, comp):
        return None
    if w.task == "wait" and _charge(g, w, comp):
        return walkers.schedule(g, w, 1)
    if w.task != "wait":
        return walkers.schedule(g, w, 1)
    return walkers.schedule(g, w, _hold_wake(g, w, comp, w.aim_due) - g.tick)


def _start_march(g, w, task="march"):
    """7 -> 9 (or 13 / 11): figure_move runs from the next tick; action 7 freed the route, so its first figure_move
    finds a new one from the tile it stands on (progress 15: a step it stopped in is not finished)."""
    w.task = task
    free_route(w)


def _stop(g, w, task="wait"):
    """Back to action 7 where it stands (its tile progress stays; action 7 frees the route every tick)."""
    if w.task in MOVING:
        w.walk_t = g.tick                          # its walk frame counter stops here (action 7 draws frame 0)
    w.task = task
    free_route(w)


def _march(g, w, comp):
    """Action 9 (0x00500EC0): +0x36 - 1; at <= 0: 30 again; the slot's spot != dest -> dest = it: on the figure's own
    tile (direction_to == 8) -> action 7 (it stops where it is), else +0x5E = the company's +0x3E and the route is
    freed (figure_route_free: figure_move finds the new one in this tick). Then figure_move; arrived (8), blocked (9)
    or lost (10) -> 7. archer_try_shoot after, whatever the move did (0x00500FD8)."""
    if g.tick >= _due(g, w):
        w.aim_due = g.tick + 30
        goal = slot_dest(comp, w.slot)
        if goal != tuple(w.dest or ()):
            w.dest = goal
            if (w.x, w.y) == goal:
                _stop(g, w)
                return _hold_after(g, w, comp)
            free_route(w)
    r = imove(g, w, tuple(w.dest))
    if r in (8, 9, 10):
        _stop(g, w)
    elif r == "fight":
        return _shoot_out_of_fight(g, w, comp)
    return _hold_after(g, w, comp)


def _shoot_out_of_fight(g, w, comp):
    """Action 9 calls archer_try_shoot after figure_move (0x00500FD8) whatever the move did: an archer whose step just
    started a fight (figure_fight_start: action 5, attack_timer 0) still reloads and may shoot, which turns the fresh
    action 5 into 6 (no fight_end: its foe sees it leave action 5 on its next fight tick)."""
    if w.role != "enemy_archer" or w.anim != "fight" or not w.mover:
        return None
    left = getattr(w, "reload_left", 0)
    w.frozen, w.next_shot = False, g.tick + left
    if _try_shoot(g, w, comp):
        units.leave_fight(g, w)
        return None
    w.frozen = True                                # still fighting: no reload in action 5
    return None


def _hold_after(g, w, comp):
    if w.role == "enemy_archer" and _try_shoot(g, w, comp):
        return None
    if w.task != "wait":
        return walkers.schedule(g, w, 1)
    return walkers.schedule(g, w, _hold_wake(g, w, comp, _due(g, w)) - g.tick)


def _hold_wake(g, w, comp, due):
    """The tick this invader must act next before `due`: every tick while an archer may shoot (reload due, not
    jammed) or mode-2 cavalry holds (charge check); else `due`."""
    if w.role == "enemy_archer" and not getattr(w, "frozen", False):
        return max(g.tick + 1, min(due, getattr(w, "next_shot", 0)))
    if w.role == "enemy_cavalry" and comp.get("mode") == 2 and w.task == "wait":
        return g.tick + 1
    return max(g.tick + 1, due)


def _hidden_archer(g, w, comp):
    """A hidden archer before its action-7 timer runs out (invader handler 0x00500B70, action 7 at 0x00500C9E): every
    tick, hidden or not, archers call archer_try_shoot 0x005009E0 (reload per call, then archer_target). A hit sets
    action 6 (0x005011C0); fig_handler_enemy_archer 0x004B99B0's picture tail has no hidden check, so the shot ends at
    its frame wrap as a visible one's (action 7, attack_timer 0). Action 6 does not count the action-7 timer (+0x36):
    the archer appears the shot's length later (bug 393; before: "a6", held in action 6 until the regroup)."""
    if _try_shoot(g, w, comp):
        return None
    return walkers.schedule(g, w, _hold_wake(g, w, comp, w.appear) - g.tick)


def slot_dest(comp, k):
    """The slot's spot: company target (+0x3A / +0x3C) + the figure's layout offset (+0x30 / +0x32); not clamped (a
    company's first target is logical (0, 0): its spots are off the map until the company AI sets one, lost)."""
    from .forces import OFF
    dx, dy = OFF.get(comp["layout"], OFF[1])[k % 8]
    tx, ty = comp["target"]
    return (tx + dx, ty + dy)


def _siege(g, w, tile, o):
    """figure_check_next_tile 0x004D8BB0, route mode 2: in front of a building / wall / tower tile it stands (direction
    11) and tries again every tick; it hits only on ticks whose cycle_step & 3 == 0 (13 in 51 ticks). cycle_step
    during walkers_update (after simulation_cycle_step, which runs step s then counts on) is ours' tick % 51."""
    x, y = tile
    w.face = ((x > w.x) - (x < w.x), (y > w.y) - (y < w.y))
    if getattr(w, "sieging", None) is None or g.tick - w.sieging > 1:
        w.siege_t0 = g.tick                        # the attack group's look starts (play mode)
    w.sieging = g.tick
    if (g.tick % 51) & 3:
        return
    inv = invasions(g).get(getattr(w, "inv", 0))
    # wall_damage_add 0x00492830 (tile, limit, 1, city): a building tile (grid 1) passes the hitter's city
    # (FUN_004E2A60: its event's city), a wall / tower / gatehouse 0xFF. 0x00FE6A5B = that value on every hit (the
    # last hitter); 0x00FEB4F8 = it when the tile's building root is the palace (any hit, not only the last one)
    who = hitter(inv) if o == 1 else None
    st = state(g)
    st["last_hit"] = who
    b = g.buildings.get(int(g.world.occ[y, x]))
    if b is not None and b.key == "palace":
        st["palace_hit"] = who
    dmg = st.setdefault("wall_damage", {})
    k = f"{x},{y}"
    dmg[k] = dmg.get(k, 0) + 1
    limit = {1: 10, 3: 200, 4: 400}[o]
    if dmg[k] > limit:
        dmg.pop(k, None)
        destroy(g, x, y, w)


def destroy(g, x, y, by):
    """building_destroyed_by_attack 0x004928C0: a wall tile becomes rubble; any building collapses (no fire)."""
    from ..systems import risk
    from .. import effects
    world = g.world
    bid = int(world.occ[y, x])
    b = g.buildings.get(bid)
    inv = invasions(g).get(getattr(by, "inv", 0))
    if b is not None:
        g.message(f"Invaders destroyed the {b.key.replace('_', ' ')} at ({b.x},{b.y})!")
        effects.debris(g, b.x, b.y, b.size)        # collapse_debris_spawn(x, y, size, 1, 4, 0) (play mode only)
        risk.collapse(g, b)
    elif world.flags[y, x] & 0x4000:
        effects.debris(g, x, y, 1)                 # no building on the tile: (x, y, 1)
        world.flags[y, x] = int(world.flags[y, x]) & ~0x4000 & 0xFFFFFFFF
        state(g)["breaches"] = state(g).get("breaches", 0) + 1
        g.map_version = getattr(g, "map_version", 0) + 1
        g.message(f"Invaders broke through the wall at ({x},{y}).")
    if inv is not None and b is not None and b.key in ("tower", "gatehouse"):
        inv["hit_wall"] = True


def _hunt(g, w, comp, keep="hunt"):
    """The hunt step (0x00500FF2, after archer_try_shoot) of actions 13 and 10: the target (+0x82) is dropped when it
    is not state 1 or dying; with none, nearest_soldier 0x00501640 (range 0): dest = its tile, it +0x84 = this hunter
    (0x004E3280), the route freed. None at all -> action 7 with timer 50 (0x00501122). Then figure_move toward dest
    (set at the search, not following the target); arrived (8) -> dest = the target's tile now, route freed; lost
    (9 / 10) -> 7, target 0. The action stays what it was (keep): 13 "hunt" (the mode-2 cavalry charge), 10 "attack"
    (company engaged) or 7 "wait" (action 10 of a company not engaged sets 7 first: one step, then action 7's hold;
    oracle 1B-inv-city: the hidden members keep their timers and stand, target set, tile progress 0)."""
    t = g.walkers.get(getattr(w, "target_id", 0))
    if t is None or t.anim == "die":
        t = nearest_soldier(g, w)
        if t is not None:
            w.target_id, w.hunted, w.dest = t.id, True, (t.x, t.y)
            free_route(w)
        else:
            w.target_id, w.hunted = 0, False
    if t is None:
        _stop(g, w)
        if w.hidden:
            w.appear = g.tick + 50
            return walkers.schedule(g, w, _hold_wake(g, w, comp, w.appear) - g.tick)
        w.aim_due = g.tick + 50
        return walkers.schedule(g, w, _hold_wake(g, w, comp, w.aim_due) - g.tick)
    w.task = "hunt"
    if not getattr(w, "dest", None):
        w.dest = (t.x, t.y)
    r = imove(g, w, tuple(w.dest))
    if r == "fight":
        return None
    if r == 8:
        w.dest = (t.x, t.y)
        free_route(w)
    elif r in (9, 10):
        _stop(g, w)
        w.target_id, w.hunted = 0, False
        return walkers.schedule(g, w, _hold_wake(g, w, comp, _due(g, w)) - g.tick)
    if keep == "wait":                             # action 7 from the next tick (it frees the route, the frame stops)
        _stop(g, w)
        due = w.appear if w.hidden else _due(g, w)
        return walkers.schedule(g, w, max(1, _hold_wake(g, w, comp, due) - g.tick))
    w.task = keep
    return walkers.schedule(g, w, 1)


def target_gone(g, w):
    """A soldier fell or left: the invaders hunting it see that on their next tick (action 13 checks its target every
    tick): in this tick's pass if their slot comes later (walkers.wake_now)."""
    for o in _figures(g)[1]:
        if getattr(o, "target_id", 0) == w.id and o.task in ("hunt", "attack") and not o.anim:
            walkers.wake_now(g, o)


def nearest_soldier(g, w, rng=0, at=None):
    """0x00501640(x, y, range): soldiers 0xB..0xD and heroes 0x45, state 1, not dying, visible, attacked_by (+0x84)
    == 0; Chebyshev nearest (first in index order on a tie). With a range: none past it. With range 0 and none
    found: the first live soldier 0xB..0xD in index order (hidden or attacked too). attacked_by is the hunter that took
    it (+0x82 / +0x84, 0x005010CF), cleared by walkers_update once that one is gone or targets another (an archer's
    shot retargets +0x82): ours, a live invader whose target_id it is from its hunt (`hunted`)."""
    x0, y0 = at or (w.x, w.y)
    sold, invs = _figures(g)
    taken = {o.target_id for o in invs if o.anim != "die" and getattr(o, "hunted", False)}
    best, bd = None, None
    for f in sold:
        if f.anim != "die" and not getattr(f, "hidden", False) and f.id not in taken:
            d = max(abs(f.x - x0), abs(f.y - y0))
            if bd is None or d < bd:
                best, bd = f, d
    if rng:
        return best if best is not None and bd <= rng else None
    if best is None:
        best = next((f for f in sold if f.role != "hero" and f.anim != "die"), None)
    return best


def _figures(g):
    """(soldiers and heroes in id order, invaders) on the map this tick (cached per tick)."""
    c = contact.cache(g)
    f = c.get("inv_figs")
    if f is None or f[0] != g.tick:
        sold, invs = [], []
        for o in g.walkers.values():
            if o.role in ("rabble", "hoplite", "horseman", "hero"):
                sold.append(o)
            elif o.role in TYPES:
                invs.append(o)
        sold.sort(key=lambda o: o.id)
        f = c["inv_figs"] = (g.tick, sold, invs)
    return f[1], f[2]


# --- cavalry in the special mode (company +0x91 == 2) ----------------------------------------------

def _charge(g, w, comp):
    """Action 7, cavalry (0x2A) of a company in mode 2 (0x00500DD5): a soldier within col 12 (special_range) of it ->
    action 13 toward it (dest = its tile; the hunt then takes the nearest free soldier)."""
    if w.role != "enemy_cavalry" or comp.get("mode") != 2 or w.task != "wait":
        return False
    t = nearest_soldier(g, w, units.col(g, w, "special_range"))
    if t is None:
        return False
    w.task, w.dest = "hunt", (t.x, t.y)            # the hunt itself from the next tick
    return True


# 0x00501480: the 8 offsets (x, y) x special_range, tried from a random start
SPOT = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]


def _free_spot(g, w):
    """0x00501480(fig, col 12): from a random direction (RNG & 7), the first of the 8 points d away around it with no
    soldier within d (0x00501640); the point's y is f.x + dy (the exe adds the figure's x twice: kept)."""
    d = units.col(g, w, "special_range")
    r = mrng(g).randrange(8)
    for i in range(8):
        dx, dy = SPOT[(r + i) % 8]
        p = (w.x + dx * d, w.x + dy * d)
        if nearest_soldier(g, w, d, at=p) is None:
            return p
    return None


def melee_wake(g, w):
    """fig_handler_enemy_horseman 0x004B9E20, action 5: in mode 2 it tries to disengage every tick its attack timer is
    past 11 (12..23): the first such tick from now."""
    if w.role != "enemy_cavalry":
        return None
    comp = ecomps(g).get(getattr(w, "company", 0))
    if comp is None or comp.get("mode") != 2:
        return None
    k = (g.tick + 1 - w.anim_t0) % units.HIT_EVERY
    return g.tick + 1 if k >= 12 else g.tick + 1 + (12 - k)


def melee_tail(g, w):
    """The horseman handler's action-5 tail after figure_fight_tick: mode 2 and attack_timer > 11 -> 0x00501480; a free
    spot -> action 11 (0xB) there, straight out of the fight (no fight_end: its foes see it leave action 5)."""
    if w.role != "enemy_cavalry":
        return False
    comp = ecomps(g).get(getattr(w, "company", 0))
    if comp is None or comp.get("mode") != 2 or (g.tick - w.anim_t0) % units.HIT_EVERY <= 11:
        return False
    p = _free_spot(g, w)
    if p is None:
        return False
    route = w.__dict__.get("iroute")
    units.end_fight(g, w)
    w.iroute = route                               # no fight_end: a route it walked before the fight is kept (it
    w.task, w.dest = "disengage", p                # walks it out, then 7); figure_move from the next tick
    walkers.schedule(g, w, 1)
    return True


def _disengage_walk(g, w, comp):
    """Action 11 (0x00500C4C): figure_move to the spot; arrived (8) or lost (10) -> 7 (the hold, its charge check from
    the next tick); blocked (9) -> the route is freed and found again in the next call (it stays in 11 until it gets
    there or the company AI re-tasks it)."""
    r = imove(g, w, tuple(w.dest))
    if r == "fight":
        return None
    if r in (8, 10):
        _stop(g, w)
        return walkers.schedule(g, w, 1)
    if r == 9:
        free_route(w)
    return walkers.schedule(g, w, 1)


ARCHER_PRI = {"rabble": 50, "hoplite": 50, "horseman": 50, "wall_sentry": 50, "tower_sentry": 50, "watchman": 50,
              "hero": 50, "trireme": 30}
# archer_target 0x00501C50 skips figure types 0, 6 ambient, 0xA fire, 0xE standard, 0x22 map flag, 0x23 flotsam,
# 0x28..0x2A invaders, 0x2D / 0x34 missiles, 0x30 shipwreck, 0x31 sheep, 0x33 boar (ours' deer too), 0x3B wolf,
# 0x3F / 0x40 enemy ships, 0x4C cattle (ours' bull too); anyone else (goats, trade ships, boats) only while few
ARCHER_SKIP = {"arrow", "enemy_arrow", "sheep", "boar", "deer", "wolf", "enemy_transport", "enemy_warship", "cattle",
               "bull"}


def _try_shoot(g, w, comp):
    """archer_try_shoot 0x005009E0, called every tick of actions 7 / 9 / 10 / 13: only while attack_timer == 0 (ours:
    not `frozen`), the reload +0x6B +1 a call; past col 7 (ours: next_shot) archer_target 0x00501C50: soldiers,
    sentries, watchmen, heroes first; anyone else only while fewer than 4 player soldiers live. A hit: reload 0,
    attack_timer 1, anim_frame 0, action 6, facing and line_tx / line_ty (+0x4E / +0x50) = the target's tile then,
    missile_target = it (figure_set_target 0x004E3280)."""
    if getattr(w, "frozen", False) or g.tick < getattr(w, "next_shot", 0):
        return False
    best = archer_target(g, w)
    if best is None:
        return False
    w.face = ((best.x > w.x) - (best.x < w.x), (best.y > w.y) - (best.y < w.y))
    from .forces import dir_angle
    w.xdir = dir_angle(w.x, w.y, best.x, best.y)  # +0x11: FUN_0058D1F0 toward the target (read by FUN_004DE830)
    w.target_id, w.hunted = best.id, False        # +0x82 only (figure_set_target): its attacked_by is not set
    w.walk_t = None                                # anim_frame 0 (the wrap leaves it 0 too)
    n, p = shot_frames(w)
    T = g.tick
    # anim_frame 0, the tail steps it in this tick (the rate-100 gate taken to fire on the shot's tick: frame k at
    # T + (k - 1) p): the wrap to 0 at T + (n - 1) p; the logic sees the frame drawn the tick before, so the arrow
    # (frame SHOT) at T + (SHOT - 1) p + 1. Oracle 1B-inv-city (p = 1 under the harness's clock): figure 1845 shoots
    # at 376, its arrow at 384 (SHOT 8), the wrap at 387, the next shot at 478 (reload 91 calls from 388)
    w.shot_t0, w.shot_end = T, T + (n - 1) * p
    w.arrow_due = (T + (shot_frame(w) - 1) * p + 1, best.id, (best.x, best.y))
    w.next_shot = w.shot_end + units.col(g, w, "missile_rate") + 1
    _pause(g, w, (n - 1) * p)                    # action 6 (T + 1 .. the wrap) runs neither figure_move nor the +0x36
                                                 # timer
    walkers.schedule(g, w, w.arrow_due[0] - T)
    return True


def _pause(g, w, d, since=None):
    """Actions 5 / 6 do not count the +0x36 timer (re-aim, a hidden one's appearance): each one pending at `since`
    (default now) moves on by d. figure_move is not called in them either (the tile progress stays)."""
    T = g.tick if since is None else since
    if w.hidden and getattr(w, "appear", 0) > T:
        w.appear += d
    if _due(g, w) > T:
        w.aim_due += d


def archer_target(g, w):
    """archer_target 0x00501C50 within col 6 (missile_range): priority 50 soldiers, sentries, watchmen, heroes; 30
    triremes; 10 anyone else (distance + 5) only while fewer than 4 player soldiers live; a candidate replaces the best
    only if strictly higher priority and strictly nearer (the best distance starts at the range), with a line of fire.
    The exe scans figures 1..1999 in index order: ours the figures within range in id order."""
    rng = units.col(g, w, "missile_range")
    few = sum(1 for f in g.walkers.values() if f.role in ("rabble", "hoplite", "horseman") and f.anim != "die") < 4
    from .defences import line_of_fire
    idx = contact.everyone_at(g)
    cand = []
    for y in range(w.y - rng, w.y + rng + 1):
        for x in range(w.x - rng, w.x + rng + 1):
            cand.extend(idx.get((x, y), ()))
    best, bd, bp = None, rng, 0
    for o in sorted(cand, key=lambda o: o.id):
        if o.anim == "die" or getattr(o, "hidden", False) or o.role in TYPES or o.role in ARCHER_SKIP:
            continue
        p = ARCHER_PRI.get(o.role, 10 if few else 0)
        if not p:
            continue
        d = max(abs(o.x - w.x), abs(o.y - w.y)) + (5 if p == 10 else 0)
        if p > bp and d < bd and line_of_fire(g, (w.x, w.y), (o.x, o.y)):
            best, bd, bp = o, d, p
    return best


def in_shot(w):
    return getattr(w, "shot_end", None) is not None


def shot_len(w):
    """The ticks a shot keeps the archer in action 6 at its logic: T + 1 .. the wrap at T + (n - 1) p."""
    n, p = shot_frames(w)
    return (n - 1) * p


def shot_frames(w):
    """(frames, ticks per frame) of the archer's shot (data/military.json armies[army].archer_shot)."""
    a = units.data()["armies"][getattr(w, "army", 0) or 0].get("archer_shot") or {}
    return a.get("frames", 12), walkers.RATE100_TPF or a.get("frame_ticks", 1)


def shot_frame(w):
    """SHOT[army]: the frame of action 6 at which the missile leaves (0x005011C0; frame 1 plays the shot sound)."""
    a = units.data()["armies"][getattr(w, "army", 0) or 0].get("archer_shot") or {}
    return a.get("shot_frame", 1)


def _frame_at(w, t):
    """The shot's fight-group frame drawn in tick t (rate 100: frame 1 at the shot's start, +1 every p ticks; ours'
    gate phase: it fires on the shot's tick)."""
    n, p = shot_frames(w)
    return ((t - w.shot_t0) // p + 1) % n


FIRING_ALWAYS = ("rabble", "hoplite", "horseman", "wall_sentry", "tower_sentry", "trireme", "watchman", "hero")


def _arrow(g, w):
    """Action 6 with attack_timer 1 at frame SHOT[army] (the logic sees the frame the picture tail drew last tick): the
    missile 0x34 (0x004D9D70) toward line_tx / line_ty, the target's tile when the shot began (not where it is now),
    attack_timer 2. The company is "firing" (+0x5C = 6) when the target (missile_target) is gone or a soldier, sentry,
    trireme, watchman or hero (types 0xB..0xD, 0x27, 0x2E, 0x39, 0x3D, 0x45: table 0x00501438), else on 1 in 8 (RNG)."""
    from types import SimpleNamespace
    from .defences import shoot
    _, tid, tile = w.arrow_due
    w.arrow_due = None
    shoot(g, w, SimpleNamespace(x=tile[0], y=tile[1]), role="enemy_arrow")
    t = g.walkers.get(getattr(w, "target_id", 0))
    comp = ecomps(g).get(getattr(w, "company", 0))
    if comp is not None and (t is None or t.role in FIRING_ALWAYS or mrng(g).randrange(8) == 0):
        comp["firing"] = 6


def _shot_tick(g, w):
    """Action 6: the arrow at frame SHOT[army], then it stands (hidden or not) to the wrap, where the picture tail sets
    action 7 and attack_timer 0 (the reload counts again from the next tick)."""
    if w.arrow_due is not None and g.tick >= w.arrow_due[0]:
        _arrow(g, w)
    if g.tick < w.shot_end:
        nxt = w.shot_end if w.arrow_due is None else min(w.shot_end, w.arrow_due[0])
        return walkers.schedule(g, w, nxt - g.tick)
    w.shot_end, w.arrow_due, w.frozen = None, None, False
    w.next_shot = g.tick + units.col(g, w, "missile_rate") + 1      # reload 0 at the shot; +1 a call from the next tick
    if w.task != "leave" and not w.hidden:         # the wrap sets action 7 (from 9 / 13 / 11 too: it stops there and
        _stop(g, w)                                # waits for its +0x36 timer to re-aim)
    return walkers.schedule(g, w, 1)


def fight_started(g, w):
    """figure_fight_start sets attack_timer 0: an archer's pending missile is lost (action 6 resumes after the fight
    with attack_timer != 1); its reload stops (no archer_try_shoot in action 5); its fight frames run on its shot's
    counter (the same group at rate 100; b's anim_frame is not reset). fight_from = its last tick outside action 5
    (anim_t0: the start tick, or the tick before for a b whose slot comes after the mover's)."""
    w.fight_from = w.anim_t0
    if w.role != "enemy_archer":
        return
    if not getattr(w, "frozen", False):
        w.frozen, w.reload_left = True, max(0, getattr(w, "next_shot", 0) - g.tick)
    w.arrow_due = None
    # the fight frames' counter origin (look [7]): the shot's counter was 1 at its start (frame 1 drawn then)
    w.hits_t0 = w.shot_t0 - shot_frames(w)[1] if in_shot(w) and not w.mover else g.tick


def _leave(g, w):
    """Action 3 (0x00500E61): dest = the land exit (g_land_exit 0x00902CB8), figure_move; arrived (8), blocked (9) or
    lost (10) -> state 2 (deleted)."""
    r = imove(g, w, tuple(g.world.exit))
    if r in (8, 9, 10):
        return units.remove(g, w)
    if r == "fight":
        return None
    return walkers.schedule(g, w, 1)


def died(g, w, by):
    comp = ecomps(g).get(getattr(w, "company", 0))
    if by is not None:
        from .hooks import an
        g.message(f"{an(by.role)} killed an invader ({w.role.split('_')[1]}) at ({w.x},{w.y})")
    if comp is not None:
        from . import morale                       # formation_member_lost: +0x28 counts the dying, this one too
        morale.member_lost(comp, morale.enemy_count(g, comp["id"]))


def fight_over(g, w):
    """figure_fight_end 0x004D61B0: the saved action again, attack_timer as the fight left it ((end - 1 - start) % 24:
    0 only right after its own hit). An archer whose timer is not 0 cannot reload (archer_try_shoot needs 0) until a
    fight start resets it: ours `frozen` (exe rule kept, bug 393). A shot it was in resumes (action 6) to its next wrap;
    with attack_timer 1 its missile leaves at the next SHOT frame."""
    if w.role == "enemy_archer":
        timer = (g.tick - 1 - w.anim_t0) % units.HIT_EVERY
        if in_shot(w):
            n, p = shot_frames(w)
            e = w.shot_t0 + (n - 1) * p            # the next wrap (frame n - 1 -> 0) at or after this tick
            while e < g.tick:
                e += n * p
            w.shot_end = e
            if timer == 1:
                sf = shot_frame(w)
                due = next((x for x in range(g.tick + 1, w.shot_end + 1) if _frame_at(w, x - 1) == sf), None)
                if due is not None:
                    t = g.walkers.get(getattr(w, "target_id", 0))
                    w.arrow_due = (due, w.target_id, (t.x, t.y) if t is not None else (w.x, w.y))
        elif timer == 0:
            w.next_shot = g.tick + getattr(w, "reload_left", 0)
            w.frozen = False
    # the +0x36 timer stops in action 5 (fight_end at this tick: the saved action runs from the next); the
    # closing-in (figure_fight_tick: +1 sub-step a tick while the tile progress is below 6) moved it on; fight_end
    # frees the route: the saved action's next figure_move finds a new one (progress 15) from the tile it is on
    k = units.closed_in(g, w)
    if k and w.__dict__.get("fprog") is not None:
        w.fprog = min(15, w.fprog + k)
    t0 = getattr(w, "fight_from", g.tick)
    _pause(g, w, g.tick - t0, since=t0)
    free_route(w)
    walkers.schedule(g, w, 1)


def look(g, w):
    if getattr(w, "hidden", False):
        return ["hidden", 0, 0, 0, 0, 0, 0, 0, "", False]
    if w.anim:
        return None
    if getattr(w, "sieging", None) is not None and g.tick - w.sieging < 2:
        f = w.face or (0, 1)
        t0 = getattr(w, "siege_t0", w.sieging)
        return ["work", t0, w.sieging + 51, f[0], f[1], 0, 0, 0, "siege", False]
    if in_shot(w):                                   # action 6 to its wrap (data/play/military.json shoot: p a frame)
        f = w.face or (0, 1)
        return ["work", w.shot_t0, w.shot_end, f[0], f[1], 0, 0, 0, "shoot", False]
    return None


# --- company AI (daily) -----------------------------------------------------------------------------

def formation_of(w):
    """A figure's formation index (+0x60): an invader's company, a player soldier's company slot, else 0."""
    if w is None:
        return 0
    if w.role in TYPES:
        return getattr(w, "company", 0) or 0
    if w.role in PLAYER_SOLDIERS:
        return getattr(w, "comp", 0) or 0
    return 0


def under_fire(g, kind, shooter, victim):
    """A missile's hit marks a company under fire (+0x5E = 6, +0x60 = the other side's formation): the player's
    0x2D (walker_player_missile 0x004BACE0) the victim's company, when it has one, from the shooter's; the enemy
    0x34 (fig_handler_enemy_missile 0x004BD970) the shooter's company from the victim's (0 for a figure in no
    company). Read by the company AI (enemy_company_ai_update: target the marking company where it stands)."""
    if kind == 0x2D:
        comp, src = ecomps(g).get(formation_of(victim)), formation_of(shooter)
    else:
        comp, src = ecomps(g).get(formation_of(shooter)), formation_of(victim)
    if comp is not None:
        comp["under"], comp["under_from"] = 6, src


def company_pos(g, c):
    """A company's position (+0x2E / +0x30): the slot-0 member where it stands (military.md "+0x2E/+0x30 follows the
    slot-0 member"); an enemy company's as its AI last set it."""
    if "pos" in c and c.get("inv") is not None:
        return c["pos"]
    for i in c.get("ids", ()):
        f = g.walkers.get(i)
        if f is not None and getattr(f, "slot", 0) == 0:
            return (f.x, f.y)
    return None


def alive_members(g, comp):
    return [g.walkers[i] for i in comp["ids"] if i in g.walkers and g.walkers[i].anim != "die"]


def day(g):
    invs = invasions(g)
    if not invs:
        return
    rng = mrng(g)
    d = units.data()["difficulty"][g.rules.get("difficulty", "Normal")]
    st = state(g)                                  # FUN_00500910: 0x00EF57C4 + 1, past 4: 0 and the presence grid
    st["presence_ctr"] = st.get("presence_ctr", 0) + 1
    if st["presence_ctr"] > 4:
        st["presence_ctr"] = 0
        presence_build(g)
    for inv_id, inv in list(invs.items()):
        inv["lead_today"], inv["seq"] = None, 0    # event +0x3A, +0x48
        comps = [ecomps(g)[c] for c in inv["companies"] if c in ecomps(g)]
        for comp in comps:
            ms = alive_members(g, comp)
            comp["ids"] = [m.id for m in ms]
            if not ms:
                continue
            _ai(g, inv, comp, ms, d["armies"][inv["nation"]], rng)


def relations(g):
    """Cycle step 13 (simulation_cycle_step case 0xD): marks_reset, then cities_relations_update 0x00568C20 over
    the attacking cities (ours: each invasion, end_check)."""
    marks_reset(g)
    for inv_id, inv in list(invasions(g).items()):
        end_check(g, inv_id, inv)


def _ai(g, inv, comp, ms, rows, rng):
    row1 = rows["missile"]
    comp["countdown"] -= 1
    if comp["countdown"] <= 0:
        if comp["mode"] == 0:
            if not _special(g, comp, row1, rng):
                _go_attack(g, comp, ms, row1)
        elif comp["mode"] == 1:
            if not _morale(g, comp, ms, row1):
                _special(g, comp, row1, rng)
        elif comp["mode"] == 2:
            if not _morale(g, comp, ms, row1):
                _go_attack(g, comp, ms, row1)
        else:
            comp["mode"] = 1
    for k in ("firing", "under", "engaged"):
        if comp[k]:
            comp[k] -= 1
    if not any(f.role in ("rabble", "hoplite", "horseman") for f in g.walkers.values()):
        comp["firing"] = comp["under"] = comp["engaged"] = 0
    if comp["leave"]:
        for m in ms:
            if m.task != "leave" and not m.anim:
                m.task = "leave"
                walkers.schedule(g, m, 1)
        return
    if comp["mode"] != 0 and any(m.anim == "fight" and g.walkers.get(m.foe) is not None and
                                 g.walkers[m.foe].role in ("rabble", "hoplite", "horseman") for m in ms):
        comp["engaged"] = 6
    s0 = next((m for m in ms if m.slot == 0), None)     # slot 0's figure (+0x08), alive: the company's position
    if s0 is not None:
        comp["pos"] = (s0.x, s0.y)
    elif comp.get("pos") is None:
        comp["pos"] = (ms[0].x, ms[0].y)
    near = 0                                       # local_c: troops near the lead (1: 16 tiles, 2: 32)
    if inv["lead_today"] is None:
        inv["lead_today"] = comp["id"]
        inv["lead_pos"], inv["lead_layout"] = comp["pos"], comp["layout"]   # event +0x3C / +0x3E, +0x40
        dist = reach(g, comp["pos"])               # route_search(pos, -2, -2, 0, 100000): the reach test
        troops = troops_spot(g, comp["pos"], 16, dist)
        near = 1 if troops is not None else 2 if troops_spot(g, comp["pos"], 32, dist) is not None else 0
        if inv.get("x4a"):                         # event +0x4A (writers unknown, military.md): troops ignored
            near = 0
        if near == 1:
            inv["target"] = troops                 # +0x42 / +0x44 = the presence maximum
        else:
            t, palace_ok = target_buildings(g, comp)
            if not palace_ok:
                comp["noreach"] += 1
                if comp["noreach"] > 48:
                    comp["waver"], comp["leave"] = 1, True      # +0x66 = 1
            else:
                comp["noreach"] = 0
            if t is not None:
                comp["target"] = t                 # +0x7A / +0x7C (FUN_00502370 keeps them when nothing is found)
            inv["target"] = comp["target"]
    comp["seq"] = inv["seq"]                       # +0x98 = event +0x48, then + 1
    inv["seq"] += 1
    comp["days"] += 1
    tgt = inv["target"] if inv.get("target") is not None else comp["target"]
    comp["target"] = tgt                           # +0x7A.. = the event's target
    from .forces import OFF
    lo = OFF.get(inv.get("lead_layout"), OFF[1])[0]  # LAYOUT[lead layout][g_current_figure's slot]: the figure pass
    lp = inv.get("lead_pos") or comp["pos"]          # leaves g_current_figure at 2000, whose slot byte is route 0's
    around = (lp[0] + lo[0], lp[1] + lo[1])          # step 0x62: 0 (oracle 1B dumps)
    if comp["firing"]:
        comp["target"] = comp["pos"]
        return
    if comp["under"]:                              # +0x5E: target the shooting company (+0x60) where it stands
        src = comp.get("under_from") or 0
        if src < 1:
            comp["target"] = tgt
            return
        from .forces import companies
        sc = companies(g).get(src) or ecomps(g).get(src)
        if sc is None or not [i for i in sc.get("ids", ()) if i in g.walkers]:
            return                                 # its member count 0: the target stays
        sp = company_pos(g, sc)
        if sp is not None:
            comp["target"] = sp
        return
    if comp["days"] < 32:                          # muster in formation by the lead (0x00500806)
        comp["A"] = 4
        comp["target"] = formation_spot(g, comp, around, True) or tgt
        return
    if inv.get("lead_layout") in (6, 10):          # fixed lengths by the company's order today (+0x98), no draws
        q = comp["seq"]
        m, h = (4, 2) if q < 2 else (5, 3) if q < 4 else (6, 4)
        gg = 2
        if not near:
            m, h, gg = m + 6, h - 1, 1
    elif near:
        gg, m, h = rng.randrange(3) + 3, rng.randrange(4) + 6, rng.randrange(3) + 1
    else:
        gg, m, h = rng.randrange(2) + 1, rng.randrange(4) + 10, rng.randrange(2) + 1
    if comp["C"] == 0:
        if comp["B"] != 0:
            comp["B"] -= 1
            comp["A"] = comp["C"] = 0
            if comp["B"] < 1:
                comp["A"] = m
                comp["target"] = tgt
                _regroup(g, ms)
                return
            comp["target"] = formation_spot(g, comp, around, comp["days"] < 32) or tgt
            return
        comp["A"] -= 1
        comp["B"] = comp["C"] = 0
        comp["target"] = tgt
        if comp["A"] > 0:
            return
        comp["C"] = h
    else:
        comp["C"] -= 1
        comp["A"] = comp["B"] = 0
        if comp["C"] > 0:
            comp["target"] = comp["pos"]
            return
        comp["B"] = gg
    _regroup(g, ms)
    comp["target"] = comp["pos"]


def _regroup(g, ms):
    """FUN_005027e0: every member not fighting / dying -> action 7, timer 0 (a hidden one appears in this tick's
    figure pass: timer - 1 < 1)."""
    for m in ms:
        if not m.anim and m.task != "leave":
            if in_shot(m):                         # action 6 -> 7 mid-shot: attack_timer stays 1 / 2.. (not 0), so
                                                   # archer_try_shoot never reloads until a melee resets it (exe rule)
                m.shot_end = m.arrow_due = None
                m.frozen, m.reload_left = True, units.col(g, m, "missile_rate") + 1
            _stop(g, m)
            m.aim_due = g.tick                     # timer 0: it runs out in this tick's pass (0 - 1 <= 0)
            if m.hidden:
                m.appear = g.tick
            m.next_move = g.tick                   # it acts in this tick's figure pass (step 29 runs before it)
            g.sd("queue", {}).setdefault(g.tick, []).append(m.id)


def _layout(comp, special=False):
    """The layout by the axis flag (+0x77, never set for invaders: 0) and the facing (+0x6B, facings below):
    enemy_company_go_attack 0x004FFD00 / morale_check 0x004FFC10 / special_roll 0x004FFE00 (non-infantry): +0x77 0 ->
    facing 0: 1, else 0x11; +0x77 set -> facing 2: 2, else 0x10; the special roll's infantry wedges: 0xF / 0xD, or
    0xC / 0xE. (Ours before 11-03: by the landing facing, {0: 1, 2: 2, 4: 0x11, 6: 0x10}, the wedges likewise.)"""
    f, r = comp.get("facing", 0), comp.get("rot", 0)
    if special:
        return (0xF if f == 0 else 0xD) if not r else (0xC if f == 2 else 0xE)
    return (1 if f == 0 else 0x11) if not r else (2 if f == 2 else 0x10)


FACING_BY_LAYOUT = {1: 0, 0xD: 0, 2: 2, 0xC: 2, 0xE: 6, 0x10: 6, 0xF: 4, 0x11: 4}


def facings(g):
    """FUN_004DE830 (formations_update, cycle steps 5 and 29, before the company AI): every company in use and not a
    herd: with +0x70 0 (no writer found: ours 0), not firing (+0x5C == 0) the facing (+0x6B) from the layout (1, 0xD
    -> 0; 2, 0xC -> 2; 0xE, 0x10 -> 6; 0xF, 0x11 -> 4; 3: by the move since the last pass), firing: the first
    member's direction (+0x11 of F+0x08); the position then kept (+0x6C / +0x6E). Invaders spawn with facing 0
    (oracle 1B-inv-city-horse: 0 at dump 286, 4 from the step-5 pass at 292 under layout 0x11; companies 39 / 40
    shooting: 3, their archers' direction; 38 in wedge 0xD: 0, so its go-attack took layout 1)."""
    from .forces import DIRS
    for comp in ecomps(g).values():
        pos = company_pos(g, comp)
        if not comp.get("firing"):
            lay = comp.get("layout")
            if lay in FACING_BY_LAYOUT:
                comp["facing"] = FACING_BY_LAYOUT[lay]
            elif lay == 3 and pos is not None and comp.get("prev_pos") is not None:
                (x, y), (px, py) = pos, comp["prev_pos"]
                if abs(y - py) < abs(x - px):
                    comp["facing"] = 6 if x < px else 2 if px < x else comp["facing"]
                else:
                    comp["facing"] = 0 if y < py else 4 if py < y else comp["facing"]
        else:
            ms = [g.walkers[i] for i in comp.get("ids", ()) if i in g.walkers]
            m = next((x for x in ms if getattr(x, "slot", 0) == 0), ms[0] if ms else None)
            if m is not None:
                f = getattr(m, "face", None)
                comp["facing"] = getattr(m, "xdir", None) if getattr(m, "xdir", None) is not None else \
                    DIRS.index(f) if f in DIRS else comp.get("facing", 0)
        comp["prev_pos"] = pos




def _special(g, comp, row1, rng):
    if rng.randrange(100) < row1["special_pct"]:
        comp["mode"], comp["countdown"] = 2, 6
        if comp["cls"] == "cavalry":               # holding / fighting cavalry check every tick from now on
            for i in comp["ids"]:
                m = g.walkers.get(i)
                if m is not None and m.anim != "die" and (m.task == "wait" or m.anim == "fight"):
                    m.next_move = g.tick
                    g.sd("queue", {}).setdefault(g.tick, []).append(m.id)
        comp["layout"] = _layout(comp, special=comp["cls"] == "infantry")
        return True
    return False


def _go_attack(g, comp, ms, row1):
    """enemy_company_go_attack 0x004FFD00: mode 1, layout by facing, and every member that is not dying, fighting
    or shooting (actions 4/5/6) gets action 10, hidden ones too. Its next update (0x00500FE5) finds the company not
    engaged: action 7, then as action 13; no soldier to hunt -> action 7 with timer 50 (0x00501122). So a hidden
    member appears 51 ticks after the company's first go-attack, not at its spawn delay (oracle 1B-inv-land)."""
    if comp["morale"] >= row1["defensive_morale"] - 20:
        comp["mode"], comp["countdown"] = 1, 4
        comp["layout"] = _layout(comp)
        if not comp["leave"]:
            for m in ms:
                if m.anim or m.task == "leave" or in_shot(m):
                    continue
                m.next_move = g.tick                     # action 10: it acts in this tick's figure pass (step 29
                g.sd("queue", {}).setdefault(g.tick, []).append(m.id)   # runs before walkers_update)
                m.task = "attack"
        return True
    return False


def _morale(g, comp, ms, row1):
    if comp["morale"] < row1["defensive_morale"]:
        comp["mode"], comp["countdown"] = 0, 6
        comp["layout"] = _layout(comp)
        if not comp["leave"]:                      # members only while +0x73 == 0 and +0x66 < 2 (+0x66 == 1: they
            _regroup(g, ms)                        # get action 7, then 3 in the same update: the same end)
        return True
    return False


PLAYER_SOLDIERS = ("rabble", "hoplite", "horseman")    # figure types 0xB..0xD (sanctuary troops too)


def presence(g):
    """The presence grid 0x00C5BD98 (u8 per tile, raw y * N + x): not in the save (zeros after a load, as the exe)."""
    p = g.__dict__.get("_presence")
    if p is None:
        p = g.__dict__["_presence"] = bytearray(N * N)
    return p


def presence_build(g):
    """FUN_00501F20 (every 5th company-AI day, FUN_00500910): cleared, then for every player company 1..34 in use,
    mobilized (+0x90) and not away (+0x82 < 0), around its lead (FUN_004DD130: the first member slot whose figure is
    not dying) squares of radius 7, 6, 5, 4, 3, 2, 1, 1 for member counts > 0..7 (FUN_005020F0(x, y, r, 1): +1 a
    tile, +2 more when the tile list's head is a player soldier; the exe tests the head even when it skips ambient
    figures 6 / 0x18 to a later one: kept; u8, wraps)."""
    from . import forces
    p = presence(g)
    p[:] = bytes(N * N)
    w = g.world
    ox, oy = w.origin
    W, H = tuple(getattr(w, "size", (226, 226)))
    figs = contact.everyone_at(g)
    for slot in sorted(forces.companies(g)):
        c = forces.companies(g)[slot]
        if not c.get("mob") or c.get("away"):
            continue
        ids = [i for i in c.get("ids", ()) if i in g.walkers]
        lead = min((g.walkers[i] for i in ids if g.walkers[i].anim != "die"),
                   key=lambda f: getattr(f, "slot", 0), default=None)
        if lead is None:
            continue
        n = len(ids)
        for r in (7, 6, 5, 4, 3, 2, 1, 1)[:n]:
            for ty in range(max(oy, lead.y - r), min(oy + H - 1, lead.y + r) + 1):
                for tx in range(max(ox, lead.x - r), min(ox + W - 1, lead.x + r) + 1):
                    i = ty * N + tx
                    v = (p[i] + 1) & 0xFF
                    fs = figs.get((tx, ty))
                    if fs and min(fs, key=contact.order).role in PLAYER_SOLDIERS:
                        v = (v + 2) & 0xFF
                    p[i] = v


def reach(g, pos):
    """route_search_ship 0x00503A60 from pos (dest -2, -2: none): a 4-way breadth-first search (N, E, S, W) over
    grid_military >= 0, the start 1, each hop + 1 (flat list, 0 = not reached). The weighted route_search the lead
    runs first (mode 0, limit 100000, 0x010DF2C4 = 1) reaches the same tiles (values 0..5 are all >= 0, its limit is
    past the map's tile count), so FUN_00502250's reach test reads this one too."""
    gm = grid(g)
    dist = [0] * (N * N)
    s = pos[1] * N + pos[0]
    dist[s] = 1
    q = [s]
    i = 0
    while i < len(q):
        t = q[i]
        i += 1
        d = dist[t] + 1
        for m in (t - N, t + 1, t + N, t - 1):
            if 0 <= m < N * N and dist[m] == 0 and gm[m] >= 0:
                dist[m] = d
                q.append(m)
    return dist


def troops_spot(g, pos, r, dist):
    """FUN_00502250(x, y, r): the square of radius r around pos (clamped to the map), row by row: the reached tile
    with the highest presence (strictly higher replaces: the first maximum), or None when all are 0."""
    w = g.world
    ox, oy = w.origin
    W, H = tuple(getattr(w, "size", (226, 226)))
    p = presence(g)
    best, at = 0, None
    for ty in range(max(oy, pos[1] - r), min(oy + H - 1, pos[1] + r) + 1):
        for tx in range(max(ox, pos[0] - r), min(ox + W - 1, pos[0] + r) + 1):
            i = ty * N + tx
            if dist[i] > 0 and p[i] > best:
                best, at = p[i], (tx, ty)
    return at


def _exe_type(g, b):
    t = g.cat.spec(b.key).get("zeus_id")
    if b.kind == "house":
        return 2 + b.level
    return t


STORE_TYPES = (0x3A, 0x3D, 0x3E)                    # storehouse, 0x3D, trading post: target x + 1


def _records(g):
    """The exe's building records in id order as (type, (x, y) of the record's tile, building): one per building, one
    per eligible piece of a composite (0x004ABE80: a record per piece; FUN_00502370 takes a sanctuary's or pyramid's
    piece when started (vt+0x9C false), attackable (vt+0x8C) and not damaged (vt+0x98): heroes.monsters.pieces).
    Ours' piece ids are in the composite's id slot (the exe gives them ids of their own at building time)."""
    from ..heroes import monsters
    for b in g.buildings.values():
        if b.kind == "ruin":
            continue
        ty = _exe_type(g, b)
        if b.kind == "monument" and "pieces" in b.misc:
            for xy, _ in monsters.pieces(g, b):
                yield ty, xy, b
        else:
            yield ty, (b.x, b.y), b


def target_buildings(g, comp):
    """FUN_00502370(company): the target class (+0x44; 10 = rng_15 % 11), route_search_ship from the company's
    position (reach), then the palace (type 0x75, state 1) when its main tile is reached: the target is its tile,
    True. Else over the building records, class then class 9 (the exe's best index and distance carry over, only
    used when the first finds nothing): state 1, presence 0 on its tile, reached, not the palace, its type in the
    class list: the earliest list index wins, then a strictly smaller hop count (ties: the first record); types 100..114
    and composites only through their piece (vt tests, _records). Storehouse types 0x3A / 0x3D / 0x3E: x + 1 (and
    +0x7E = id + 1: kept as an exe quirk, ours keeps no building id there). Returns (target or None, palace
    reached)."""
    inv = invasions(g)[comp["inv"]]
    cls = inv.get("target_class", 10)
    if cls == 10:
        cls = mrng(g).randrange(11)
    dist = reach(g, comp["pos"])
    pal = next(iter(index.keyed(g, "palace")), None)
    if pal is not None:
        # g_palace_building 0x00FE91E8: the palace's first 0x75 record, its main part (layout piece 0, 4x4; the
        # tutorial15 oracle: record 351 at (48, 82), the composite's anchor at (47, 81))
        from ..systems import monuments as mon
        px, py = mon.piece_xy(pal, 0) if "palace" in mon.layouts() else (pal.x, pal.y)
        if dist[py * N + px] > 0:
            return (px, py), True
    p = presence(g)
    tl = units.data()["targets"]
    best_i, best_d, best = 100, 10000, None
    for c in (cls, 9):
        order = tl[c] if c < len(tl) else []
        for ty, (x, y), b in _records(g):
            i = y * N + x
            if ty is None or p[i] or dist[i] <= 0 or b.key == "palace" or ty not in order:
                continue
            k = order.index(ty)
            if k > best_i or k >= 50:
                continue
            if k < best_i:
                best_i = k
            elif best_d <= dist[i]:
                continue
            best_d, best = dist[i], (ty, x, y)
        if best is not None:
            break
    if best is None:
        return None, False
    ty, x, y = best
    return ((x + 1, y) if ty in STORE_TYPES else (x, y)), False


def _tiles_of(g, b):
    w = b.misc.get("w", b.size) or 1
    h = b.misc.get("h", b.size) or 1
    return [(b.x + dx, b.y + dy) for dy in range(h) for dx in range(w)]


def _play_edge(g, d):
    from .. import roaddrag
    c = contact.cache(g)
    k = ("play_edge", d)
    e = c.get(k)
    if e is None:
        e = c[k] = roaddrag.near_edge(tuple(getattr(g.world, "size", (226, 226))), d)
    return e


def formation_spot(g, comp, around, edge):
    """FUN_00502840(company, x, y, 1, edge): route_search from (x, y) with no goal and limit 600 (the reach test: a
    tile is reached when its distance is > 0), then squares of radius 0..13 around (x, y) (clamped to the map), row by
    row; with `edge` a spot within 10 of the play area's edge is skipped (map_near_play_edge 0x00496080). A spot fits
    when each of the company's member count of layout tiles (its offsets less slot 0's: the spot is slot 0's tile)
    is not water (4), rubble or cliff (0x1200), is reached, and the first figure on it (tile list; ambient 6 / 0x18
    skipped) is of this company or there is none (the exe tests the list head's company: kept). Returns the spot, or
    None (the target stays)."""
    from .forces import OFF
    from . import routes
    w = g.world
    ox, oy = w.origin
    W, H = tuple(getattr(w, "size", (226, 226)))
    offs = OFF.get(comp["layout"], OFF[1])
    n = len(alive_members(g, comp))
    rel = [(dx - offs[0][0], dy - offs[0][1]) for dx, dy in offs[:max(1, n)]] if n else []
    x, y = around
    st = routes.Search(routes.grid(g), y * N + x) if 0 <= x < N and 0 <= y < N else None
    if st is not None:
        st.run_pops(600)
    dist = st.dist if st is not None else None
    flags = w.flags
    near = _play_edge(g, 10) if edge else None
    figs = contact.everyone_at(g)
    cid = comp["id"]

    def ok(tx, ty):
        if not (0 <= tx < N and 0 <= ty < N):
            return False
        if int(flags[ty, tx]) & 0x1204 or dist is None or dist[ty * N + tx] < 1:
            return False
        fs = figs.get((tx, ty))
        if fs:
            head = min(fs, key=contact.order)
            if getattr(head, "company", None) != cid or head.role not in TYPES:
                return False
        return True
    for r in range(14):
        for ty in range(max(oy, y - r), min(oy + H - 1, y + r) + 1):
            for tx in range(max(ox, x - r), min(ox + W - 1, x + r) + 1):
                if near is not None and near[ty, tx]:
                    continue
                if all(ok(tx + dx, ty + dy) for dx, dy in rel):
                    return (tx, ty)
    return None


# --- the end of an invasion (cities_relations_update 0x00568C20) -------------------------------------

def player_weight(g):
    from ..systems import military as recruit
    from .forces import field as ffield
    p = 0
    for c in recruit.companies(g).values():
        ffield(c)
        if not c.get("away") and c["ready"]:
            p += c["members"] * PWEIGHT[c["type"]]
    return p


def enemy_weight(g, inv):
    e = 0
    for cid in inv["companies"]:
        comp = ecomps(g).get(cid)
        if comp is None:
            continue
        for m in alive_members(g, comp):
            e += WEIGHT[m.role]                     # leaving ones count until they are off the map
    rows = units.data()["difficulty"][g.rules.get("difficulty", "Normal")]["armies"][inv["nation"]]
    for w in g.walkers.values():                    # 0x5687A0: a loaded transport adds P = class*1000 + n split by
        if w.role == "enemy_transport" and w.anim != "die" and getattr(w, "loaded", False) \
                and getattr(w, "inv", None) == inv["id"]:          # the army's shares (exe bug: P whole, kept)
            cls, n = w.payload
            P = ("missile", "infantry", "cavalry").index(cls) * 1000 + n
            mis = P * rows["missile"]["frequency"] // 100
            cav = P * rows["cavalry"]["frequency"] // 100
            e += 2 * (P - mis - cav) + mis + 3 * cav
    return e


def hitter(inv):
    """FUN_004E2A60: the city of an invader's event (ours: the invasion's city; an invasion with none, e.g. the `invade`
    test command or a god's army, by its own id)."""
    if inv is None:
        return None
    c = inv.get("city")
    return c if c is not None else ("inv", inv["id"])


def marks_reset(g):
    """simulation_cycle_step case 0xD (0x00483840): with no enemy unit alive and no enemy warship, 0x00FEB4F8 (the
    palace's last hitter) and 0x00FE6A5B (the last hitter) = 0xFF, before cities_relations_update."""
    if any(w.anim != "die" and (w.role in TYPES or w.role == "enemy_warship") for w in g.walkers.values()):
        return
    st = state(g)
    st.pop("palace_hit", None)
    st.pop("last_hit", None)


def end_check(g, inv_id, inv):
    """cities_relations_update 0x00568C20: (no palace and the last hit, 0x00FE6A5B, was this city's on a building) or
    (E > 3P and this city's was the palace's last hit, 0x00FEB4F8) -> city_conquers_player; 8E < P and E == 0 ->
    city_army_sent_home."""
    E, P = enemy_weight(g, inv), player_weight(g)
    pal = next(iter(index.keyed(g, "palace")), None)
    st, me = state(g), hitter(inv)
    if (pal is None and st.get("last_hit") == me) or (E > 3 * P and st.get("palace_hit") == me):
        return defeat(g, inv_id, inv)
    if 8 * E < P and E == 0:
        return withdraw(g, inv_id, inv)
    if E == 0 and P == 0:
        g.message(f"The army from {inv['name']} is gone.")
        return close(g, inv_id, inv)


def defeat(g, inv_id, inv):
    """enemy_victorious 0x00482200 (city_conquers_player): a city whose tribute mode is not 2 yet makes the player pay
    it tribute (mode 2, message 0xB9C/0xB9D); a city the player already pays (mode 2: carried into a colony and back
    with the world cities, ended by a withdrawal 0x00481E80) sacks it again: the game is lost (0xB92). An invasion
    with no world city (the `invade` test command, a god's army) keeps its own mark."""
    st = state(g)
    e = getattr(g, "empire", None)
    c = e.cities.get(inv.get("city")) if e is not None and inv.get("city") is not None else None
    if c is not None:
        again = c.tribute.get("mode") == 2
    else:
        lost = st.setdefault("defeats", {})
        again = bool(lost.get(str(inv.get("city"))))
        lost[str(inv.get("city"))] = True
    if again:
        g.message(f"The army from {inv['name']} has sacked your city again. Your city is lost!")
        st["game_lost"] = True
    else:
        g.message(f"Defeat! The army from {inv['name']} has sacked your city: you are forced to pay this brigand tribute.")
        if c is not None:
            c.tribute["mode"] = 2
    _send_away(g, inv)
    close(g, inv_id, inv)


def withdraw(g, inv_id, inv, bribed=False):
    """army_withdraws 0x00481E80."""
    _send_away(g, inv, bribed)
    try:                                             # 0x00402B00(2): a Victory Monument to place
        from ..systems import commemorative
        commemorative.grant(g, 2)
    except (ImportError, AttributeError):
        pass
    # message 0xE0 0xD75 / 0xD78 (bribed) or 0xDE 0x442 / 0x445 (the announcement that names the monument)
    from .. import messages
    e = getattr(g, "empire", None)
    c = e.cities.get(inv.get("city")) if e is not None and inv.get("city") is not None else None
    if c is None:
        from types import SimpleNamespace
        c = SimpleNamespace(name=inv["name"], leader="", nation=inv.get("nation", 0))
    # city_army_sent_home: not bribed, FUN_00521A70(0xDE, 0, a company's formation tile (+0x16/+0x18 of the last
    # company of the army met in the figure loop; ours: the army's last company)): the window's go-to button
    at = None
    if not bribed:
        pos = [ecomps(g)[k]["pos"] for k in inv.get("companies", ()) if k in ecomps(g) and ecomps(g)[k].get("pos")]
        at = pos[-1] if pos else None
    messages.post(g, *((0xD75, 0xD78) if bribed else (0x442, 0x445)), city=c, nation=inv.get("nation"),
                  meta=dict(at=[at[0], at[1]], kind=0xDE) if at else None)
    if getattr(c, "tribute", {}).get("mode") == 2:   # 0x00481E80: a city the player paid stops being paid
        c.tribute["mode"] = 0
    close(g, inv_id, inv)


def _send_away(g, inv, bribed=False):
    for w in list(g.walkers.values()):              # army_withdraws 0x00481E80: transports and warships sail out
        if w.role in ("enemy_transport", "enemy_warship") and getattr(w, "inv", None) == inv["id"] and w.anim != "die":
            if w.role == "enemy_transport":
                w.act, w.loaded, w.path = 0xE, False, []
            else:
                w.act, w.path = 0xF, []
            walkers.schedule(g, w, 1)
    for cid in inv["companies"]:
        comp = ecomps(g).get(cid)
        if comp is None:
            continue
        comp["rout"], comp["leave"] = 3, True          # +0x73 = 3
        for m in alive_members(g, comp):
            if bribed and m.hidden:
                units.remove(g, m)
                continue
            m.task = "leave"
            if not m.anim:
                walkers.schedule(g, m, 1)


def close(g, inv_id, inv):
    inv["over"] = g.tick
    invasions(g).pop(inv_id, None)
    st = state(g)
    st.setdefault("past", []).append(dict(id=inv_id, name=inv["name"], start=inv["start"], end=g.tick))
    del st["past"][:-20]
    e = getattr(g, "empire", None)
    if e is not None and inv.get("ev") is not None:
        from ..empire import events
        for ev in events.live(g, "invasion"):
            if ev["id"] == inv["ev"]:
                events.done(ev)


def bribe_cost(g, inv_id):
    """invasion_bribe_cost 0x00476CF0: 25 per archer/infantry, 50 per horseman, x [1,3,4,5,7][difficulty]."""
    inv = invasions(g).get(inv_id)
    if inv is None:
        return 0
    v = 0
    for cid in inv["companies"]:
        comp = ecomps(g).get(cid)
        if comp is not None:
            v += sum(50 if m.role == "enemy_cavalry" else 25 for m in alive_members(g, comp))
    for w in g.walkers.values():                     # + 200 per live warship, 25*(p0 + p1 + 2*p2) per transport payload
        if getattr(w, "inv", None) == inv_id and w.anim != "die":
            if w.role == "enemy_warship":
                v += 200
            elif w.role == "enemy_transport" and getattr(w, "loaded", False):
                v += 25 * w.payload[1] * (2 if w.payload[0] == "cavalry" else 1)
    from ..data import DIFFICULTIES
    k = BRIBE_MUL[DIFFICULTIES.index(g.rules.get("difficulty", "Normal"))]
    return max(1, min(60000, int(v * k)))


def bribe(g):
    invs = invasions(g)
    if not invs:
        return "no army is attacking"
    inv_id = next(iter(invs))
    cost = bribe_cost(g, inv_id)
    if cost >= g.city.treasury:
        return f"the bribe is {cost} dr: not enough in the treasury ({g.city.treasury})"
    g.city.treasury -= cost
    g.city.ledger["bribes"] = g.city.ledger.get("bribes", 0) - cost
    withdraw(g, inv_id, invs[inv_id], bribed=True)
    return f"paid {cost} dr: the invaders leave"
