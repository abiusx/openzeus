"""The player's companies on the city map (docs/logic/military.md "Soldiers on the map", "Formations").

A company is the record systems/military.py keeps (slot 1..20 -> {"type", "members"}); this module adds its field
state: mob (mobilized, +0x90), dest (+0x32/+0x34, where its standard stands), layout (+0x2A), rot (+0x77), mode
(+0x91: 0 hold, 1 attack, 2 special), morale (+0x2C), ready (+0x93), ids (the soldiers on the map), target company.
At home the soldiers are a count (the exe keeps them as hidden figures at the palace: same thing). Mobilized, every
member is a walker:
- call to arms / move (formation_move 0x004DD250): soldiers at home appear on the road tiles of houses of their
  class (round robin, soldier_home_house 0x004CDC50) and march (route mode 0, type speed) to dest + OFF[layout][slot];
- on the slot, every tick: the mode action. Hold (FUN_004B10A0): stand; off the slot back to it only while the
  company's melee / under-fire timers are 0 (rabble throw at targets in range); melee only by tile contact.
  Attack / special: engage (0x004B0B60) the nearest invader or wolf within 6 tiles of the slot (rabble 14);
  horsemen charge an enemy 4..6 tiles away (formation_charge 0x004DD6D0: one charge hit, layout 1), hit and run
  regroups (0x12) after 5 ticks with one within 3;
- send home (formation_return_home 0x004DD8D0): each walks to a house of its class and vanishes into the palace;
- morale (sim/military/morale.py): member deaths (0x004DDFF0), the waver at step 5; a palace company never routs.
Expeditions (sim/empire/war.py): march_out walks the companies to the map exit (0x004DEB30), march_home brings them
back from it (0x004DEE60).
Every soldier acts every tick, as the exe's handlers (rabble 0x004B31F0, hoplite 0x004B26B0, horseman 0x004B1840).
The standard's morale rules run every tick (standards).
"""
from ..systems import walkers, index
from ..systems import military as recruit
from . import units, contact, mrng, morale

OFF = {0: [(0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (-1, 1), (0, -1), (1, -1)],
       1: [(0, 0), (-1, 0), (-2, 0), (-3, 0), (0, 1), (-1, 1), (-2, 1), (-3, 1)],
       2: [(0, 0), (0, -1), (0, -2), (0, -3), (1, 0), (1, -1), (1, -2), (1, -3)],
       3: [(0, 0), (0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (1, 1), (-1, 1)],
       4: [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (2, 1), (1, 2), (0, 2)],
       5: [(0, 0)] * 8,
       9: [(0, 0), (2, 0), (0, 2), (2, 2), (-2, 0), (-2, 2), (0, -2), (2, -2)],
       12: [(0, 0), (0, 1), (1, 1), (-1, 1), (-1, 2), (1, 2), (-2, 2), (2, 2)],
       13: [(0, 0), (-1, 0), (-1, -1), (-1, 1), (-2, -1), (-2, 1), (-2, -2), (-2, 2)],
       14: [(0, 0), (0, -1), (1, -1), (-1, -1), (-1, -2), (1, -2), (-2, -2), (2, -2)],
       15: [(0, 0), (1, 0), (1, -1), (1, 1), (2, -1), (2, 1), (2, -2), (2, 2)],
       16: [(0, 0), (0, -1), (0, -2), (0, -3), (-1, 0), (-1, -1), (-1, -2), (-1, -3)],
       17: [(0, 0), (-1, 0), (-2, 0), (-3, 0), (0, -1), (-1, -1), (-2, -1), (-3, -1)]}     # 0x005F2358
SPREAD = [(0, 0), (0, -3), (3, -3), (3, 0), (3, 3), (0, 3), (-3, 3), (-3, 0), (-3, -3), (6, -3), (6, 0), (6, 3),
          (-6, 3), (-6, 0), (-6, -3), (-3, -6), (0, -6), (3, -6), (3, 6), (-3, 6)]               # 0x006395D0
ROTATE = {2: 1, 1: 16, 16: 17, 17: 2, 12: 13, 13: 14, 14: 15, 15: 12}
MORALE_LOSS = morale.LOSS
ENEMIES = ("enemy_infantry", "enemy_archer", "enemy_cavalry", "wolf")
MODE_TASK = {0: "hold", 1: "attack", 2: "special"}
N = 228


# the sanctuary companies' pictures (bug 393; data/play/military.json "rabble:amazon" / "hoplite:ares"): formations
# 0x1F / 0x20 (Artemis) are Amazons, 0x21 / 0x22 (Ares) his warriors (fig_handler_rabble 0x004B31F0 / hoplite 0x004B26B0)
SANCT_LOOK = {31: "amazon", 32: "amazon", 33: "ares", 34: "ares"}

def companies(g):
    return recruit.companies(g)


def field(c):
    """Defaults for a company's field state (older records)."""
    c.setdefault("mob", False)
    c.setdefault("dest", None)
    c.setdefault("layout", 1)
    c.setdefault("rot", 0)
    c.setdefault("mode", 0)
    c.setdefault("morale", 50)
    c.setdefault("ready", True)
    c.setdefault("ids", [])
    c.setdefault("target", 0)
    return c


def palace(g):
    return next(iter(index.keyed(g, "palace")), None)


def home_tile(g):
    p = palace(g)
    return p.access if p is not None else None


def members(g, c):
    return [g.walkers[i] for i in c.get("ids", []) if i in g.walkers and g.walkers[i].anim != "die"]


def layout_for(c):
    """0x004E2100 / 0x004E2210 / 0x004E2320: by the axis flag (+0x77) and facing; hoplites in mode 2 wedge."""
    if c["type"] == "hoplite" and c["mode"] == 2:
        return 15 if not c["rot"] else 12
    return 1 if not c["rot"] else 2


def slot_tile(c, k, spread=(0, 0)):
    dx, dy = OFF.get(c["layout"], OFF[1])[k % 8]
    x, y = c["dest"]
    return (max(1, min(N - 2, x + spread[0] + dx)), max(1, min(N - 2, y + spread[1] + dy)))


# --- houses of a class (soldier_home_house 0x004CDC50) -------------------------------------------

def _house_ok(g, b, kind):
    if b.kind != "house" or not b.occupants or b.access is None:
        return False
    lv = b.level
    if kind == "rabble":
        return g.cat.houses[lv].get("soldier_pct", 0) > 0 and lv <= 6
    arms, horses = b.goods.get("armor", 0), b.goods.get("horses", 0)
    if kind == "horseman":
        return lv == 12 and horses > 0 and arms > 0
    if lv not in (10, 11, 12) or arms <= 0:
        return False
    if lv == 12 and ((horses >= 2 and arms >= 2) or (horses == 1 and arms == 1) or (horses >= 2 and arms >= 1)):
        return False
    return True


def pick_house(g, kind):
    """FUN_004CDC50: round robin over the houses from a shared cursor (0x00FEB0E8): the next house of this class
    (_house_ok), else None (the exe falls back to the palace)."""
    st = recruit_state(g)
    hs = index.of(g, "house")
    if hs:
        cur = st.get("house_cursor", 0)
        ids = [b.id for b in hs]
        start = next((i for i, bid in enumerate(ids) if bid > cur), 0)
        for k in range(len(ids)):
            b = hs[(start + k) % len(ids)]
            if (b.level <= 6) != (kind == "rabble") or not b.occupants or b.access is None:
                continue
            st["house_cursor"] = b.id              # every house of the class moves the cursor, eligible or not
            if _house_ok(g, b, kind):
                return b
    return None


def house_tile(g, kind):
    """The picked house's road tile, else the palace's road tile."""
    b = pick_house(g, kind)
    return b.access if b is not None else home_tile(g)


def charge_death(g, w):
    """figure_delete 0x004DA250, a palace company's soldier (Formation+0x94 == 0; event and sanctuary troops have
    1): the city pays for it. Rabble: house_deaths(6) from common houses; hoplite / horseman: the house
    FUN_004CDC50 picks (not the soldier's own) loses 1 armor (+ 1 horse) and 1 resident. Returns a short text."""
    from ..systems import health, housing
    if w.role == "rabble":
        return f"{health.house_deaths(g, 6)} people"
    b = pick_house(g, w.role)
    if b is None:                                 # exe: the palace's fields, population_sub(1)
        g.city.population = max(0, g.city.population - 1)
        return "1 person"
    housing.lose_soldier(g, b, horse=w.role == "horseman")
    return f"1 person, 1 armor{', 1 horse' if w.role == 'horseman' else ''} (house at {b.x},{b.y})"


def recruit_state(g):
    from . import state
    return state(g)


# --- orders ----------------------------------------------------------------------------------------

def reachable_tile(g, start, goal, k=0):
    """formation_move's candidate: (x, y) + SPREAD[k..19], the first reachable tile with no building."""
    ok = walkers.walkable(g)
    for i in range(k, len(SPREAD)):
        x, y = goal[0] + SPREAD[i][0], goal[1] + SPREAD[i][1]
        if not (2 <= x < N - 2 and 2 <= y < N - 2) or not ok[y * N + x] or g.world.occ[y, x]:
            continue
        if start is None or (x, y) == start or walkers.land_path(g, start, {(x, y)}, walkers.ROUTE_MAX, ok) is not None:
            return (x, y)
    return None


def move(g, slot, x, y, k=0, quiet=False):
    """formation_move 0x004DD250. Returns an error string or None."""
    c = field(companies(g)[slot])
    if c.get("away"):
        return "that company is away on an expedition"
    if not c["ready"]:
        return "that company is routed and regrouping at the palace"
    start = home_tile(g)
    ms = members(g, c)
    if ms:
        start = (ms[0].x, ms[0].y)
    t = reachable_tile(g, start, (x, y), k)
    if t is None:
        return f"({x},{y}) can't be reached"
    c["dest"] = t
    if c["mob"]:
        if not quiet and c["morale"] < 21:
            g.message(f"Company {slot} is close to breaking (morale {c['morale']}).")
        sync(g, slot, c)
        for w in members(g, c):
            if w.anim:
                continue
            w.task, w.after = "march", MODE_TASK[c["mode"]]
            _route(g, w, c)
    return None


def mobilize(g, slot, x=None, y=None, k=0):
    """Call to arms: mobilized, then a move to the target (the company's last dest, or the palace front)."""
    c = field(companies(g)[slot])
    if c.get("away"):
        return "that company is away on an expedition"
    c["mob"] = True
    if x is None:
        x, y = c["dest"] or (home_tile(g) or (0, 0))
    c["layout"] = layout_for(c)
    err = move(g, slot, x, y, k)
    if err:
        c["mob"] = False
    return err


def send_home(g, slot):
    """formation_return_home 0x004DD8D0: not mobilized; each soldier walks to a house of its class and vanishes."""
    c = field(companies(g)[slot])
    c["mob"] = False
    for w in members(g, c):
        if w.anim == "fight":
            w.after_fight = "home"
            continue
        _go_home(g, w)


def set_mode(g, slot, mode):
    c = field(companies(g)[slot])
    c["mode"], c["target"] = mode, 0
    c["layout"] = layout_for(c)
    for w in members(g, c):
        if w.task in ("hold", "attack", "special"):
            w.task = "march"
        w.after = MODE_TASK[mode]
        if not w.anim:
            _route(g, w, c)


def rotate(g, slot):
    c = field(companies(g)[slot])
    c["layout"] = ROTATE.get(c["layout"], 1)
    c["rot"] = 1 - c["rot"]
    for w in members(g, c):
        if not w.anim:
            w.task, w.after = "march", MODE_TASK[c["mode"]]
            _route(g, w, c)


def attack(g, slot, x, y, k=0):
    """A click on an enemy: mode 1 (attack), target company = the clicked enemy's company, then a move."""
    c = field(companies(g)[slot])
    tgt = next((f for f in contact.at(g, (x, y)) if f.role in ENEMIES and f.anim != "die"), None)
    if tgt is not None:
        c["mode"], c["target"] = 1, getattr(tgt, "company", 0) or 0
        c["layout"] = layout_for(c)
    if not c["mob"]:
        return mobilize(g, slot, x, y, k)
    return move(g, slot, x, y, k)


# --- the soldiers -----------------------------------------------------------------------------------

def sync(g, slot, c):
    """A mobilized company has all its members on the map: recruits appear at a house, extras go home."""
    ms = [i for i in c["ids"] if i in g.walkers]
    c["ids"] = ms
    alive = [g.walkers[i] for i in ms if g.walkers[i].anim != "die" and g.walkers[i].task != "gohome"]
    want = c["members"]
    used = {getattr(w, "slot", 0) for w in alive}
    while len(alive) < want:
        k = next(s for s in range(8) if s not in used)
        used.add(k)
        x, y = home_of(g, c) or (c["dest"] or (0, 0))
        w = units.spawn(g, c["type"], x, y, comp=slot, slot=k, good=SANCT_LOOK.get(slot, ""), task="march", after=MODE_TASK[c["mode"]],
                        target_id=0, next_shot=0, face=(0, 1), mode=c["mode"], spiral=0)
        c["ids"].append(w.id)
        alive.append(w)
        _route(g, w, c)
    for w in sorted(alive, key=lambda w: -getattr(w, "slot", 0))[:max(0, len(alive) - want)]:
        _go_home(g, w)


def _route(g, w, c, dest=None, keep=False):
    """A new march route (figure_find_route, route mode 0) from the soldier's tile: progress 15 (the step under way
    abandoned), except after a fight (keep: figure_fight_end keeps the progress and the walk goes on from it)."""
    dest = dest or slot_tile(c, w.slot, (0, 0))
    fp = w.__dict__.get("fprog", 15) if keep else 15
    ok = walkers.walkable(g)
    for k in range(0, 8):
        t = dest if k == 0 else (dest[0] + forces_spiral(k)[0], dest[1] + forces_spiral(k)[1])
        if not (0 <= t[0] < N and 0 <= t[1] < N) or not ok[t[1] * N + t[0]]:
            continue
        p = walkers.route0(g, (w.x, w.y), t, ok) if t != (w.x, w.y) else []     # route mode 0: bfs4 + trace(8)
        if p is not None:
            w.path, w.fprog, w.cpath = p, fp, None
            walkers.schedule(g, w, 1)
            return True
    w.path, w.fprog, w.cpath = [], fp, None
    walkers.schedule(g, w, 51)
    return False


def forces_spiral(k):
    return [(0, 0), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)][k % 9]


def _go_home(g, w):
    w.task, w.after = "gohome", ""
    c = companies(g).get(getattr(w, "comp", 0))
    t = home_of(g, c) if c is not None else (house_tile(g, w.role) or home_tile(g))
    if t is None:
        return units.remove(g, w)
    p = walkers.route0(g, (w.x, w.y), t) if t != (w.x, w.y) else []             # route mode 0
    w.path, w.fprog, w.cpath = p or [], 15, None
    walkers.schedule(g, w, 1)


def home_of(g, c):
    """Where a company's soldiers come from and go back to: event troops the map entry; sanctuary troops (31..34) the
    road entry of their sanctuary (cycle_formations_pass_14 0x00567C70: building_road_entry of the formation's
    building +0x06); the palace's a house of their class (soldier_home_house 0x004CDC50), else the palace."""
    if c.get("event"):
        return entry_tile(g)
    if c.get("sanct"):
        b = g.buildings.get(c.get("home"))
        return b.access if b is not None and b.access else home_tile(g)
    return house_tile(g, c["type"]) or home_tile(g)


def speed(g, w):
    return units.col(g, w, "speed")


def enemies_near(g, w, r):
    out = []
    for tile, ids in contact.tiles(g).items():
        if max(abs(tile[0] - w.x), abs(tile[1] - w.y)) > r:
            continue
        for i in ids:
            f = g.walkers.get(i)
            if f is not None and f.role in ENEMIES and f.anim != "die" and not getattr(f, "hidden", False):
                out.append(f)
    return out


def nearest_enemy(g, w, c, r):
    """0x005017A0: the strictly nearest invader or wolf within r (doubled distance when already attacked); hoplites and
    horsemen in attack / special skip the ones any figure_set_target ever marked (Figure+0x10C & 2)."""
    best, bd = None, None
    cand = enemies_near(g, w, r)
    if not cand:
        return None
    # attacked_by (+0x84): set by a soldier's figure_set_target (engage, the rabble's stone) on its target
    attacked = {getattr(o, "target_id", 0) for cc in companies(g).values() for o in members(g, cc) if o is not w}
    skip = w.role in ("hoplite", "horseman") and w.task in ("attack", "special")
    for f in sorted(cand, key=lambda f: f.id):
        if skip and getattr(f, "tagged", False):  # hoplites / horsemen in 0x11 / 0xB: not one already targeted
            continue                               # by anyone (flags & 2, figure_set_target)
        if c.get("target") and getattr(f, "company", 0) != c["target"]:
            continue
        d = max(abs(f.x - w.x), abs(f.y - w.y))
        if d > r:                                  # the range test on the plain distance, then doubled when it
            continue                               # already has an attacker (+0x84)
        if f.id in attacked or any(o.foe == f.id for o in units.attackers(g, f)):
            d *= 2
        if w.role == "rabble":
            from .defences import line_of_fire
            if not line_of_fire(g, (w.x, w.y), (f.x, f.y)):
                continue
        if bd is None or d < bd:
            best, bd = f, d
    return best


def act(g, w):
    if w.anim == "die":
        return units.act_dying(g, w)
    if w.anim == "fight":
        return units.fight_tick(g, w)
    c = companies(g).get(getattr(w, "comp", 0))
    if c is None:
        return units.remove(g, w)
    field(c)
    if w.task == "gohome":
        return _walk(g, w, c, on_arrive=lambda: _vanish(g, w, c))
    if w.task == "out":
        return _walk(g, w, c, on_arrive=lambda: _abroad(g, w, c))
    if w.task == "charge":
        return _walk(g, w, c, code=min(18, 2 * speed(g, w)), on_arrive=lambda: _after_charge(g, w, c))
    if w.task == "march":
        return _walk(g, w, c, on_arrive=lambda: _on_slot(g, w, c))
    return _stand(g, w, c)


def advance(g, w, code, decide, at_change=None):
    """figure_move 0x004D1170 -> figure_route_walk 0x004D7BD0 for a soldier, one call a tick (bugs.md 432): the
    sub-steps of this tick by speed code (invaders._substeps, speed_phase per figure); per sub-step the tile progress
    (+0x39, w.fprog) + 1; past 14 (the tile centre) progress 15 and the route decision: decide() gives the next tile
    (direction set, progress 0) or a result (8 arrived, 9 blocked, ...) that ends the walk this tick at the centre;
    at progress 8 the tile changes (figure_change_tile 0x004D9330: the tile contact; a fight started there ends the
    walk). A new route (figure_find_route) starts from progress 15: callers that give a new path set w.fprog = 15.
    at_change(): called after a tile change without a fight. Returns None (on its way), "fight" or decide's result."""
    from .invaders import _substeps, tile_ticks
    prog = w.__dict__.get("fprog", 15)
    for _ in range(_substeps(w, code)):
        prog += 1
        if prog > 14:
            prog = 15
            nxt = decide()
            if not isinstance(nxt, tuple):
                w.fprog = 15
                if isinstance(nxt, int):
                    w.xdir = nxt                   # the direction field holds the result (8, 9, 10)
                return nxt
            w.heading = nxt
            w.face = ((nxt[0] > w.x) - (nxt[0] < w.x), (nxt[1] > w.y) - (nxt[1] < w.y))
            w.xdir = DIRS.index(w.face) if w.face in DIRS else 8
            prog = 0
        if prog == 8:
            w.fprog = 8
            units.step(g, w, w.heading)
            num, den = units.SPEED[max(0, min(18, code))]
            w.step_draw = (g.tick, g.tick + (max(1, -(-15 * den // num)) if num else 15))   # play mode: the step
            if contact.on_enter(g, w):
                return "fight"
            if at_change is not None:
                at_change()
    w.fprog = prog
    return None


def _walk(g, w, c, on_arrive, code=None):
    """A soldier walking its route (march 9, home 7, expedition 0xD, charge 0x10) by figure_move's sub-steps, every
    tick. The next tile not walkable at the decision: 9 (blocked): a march finds a new route, others stop there."""
    ok = walkers.walkable(g)

    def decide():
        while w.path and w.path[0] == (w.x, w.y):  # a route found mid-step (after a fight) from the tile it entered
            w.path.pop(0)
        if not w.path:
            return 8
        nxt = w.path[0]
        if not ok[nxt[1] * N + nxt[0]]:
            return 9
        w.path.pop(0)
        return nxt

    r = advance(g, w, code or speed(g, w), decide)
    if r not in (8, 9, 10):                        # anim_frame: the prologue's +1 kept while it walks (wrap 12)
        w.acount = (getattr(w, "acount", 0) + 1) % 12
    if r == 8:
        return on_arrive()
    if r == 9:
        if w.task in ("march", "charge"):          # route freed: a new one (charge: to its slot) next tick
            return _route(g, w, c)
        w.path = []
        return on_arrive()
    if r == "fight":
        if w.task == "charge":
            _charge_hit(g, w)
        return None
    walkers.schedule(g, w, 1)


def _on_slot(g, w, c):
    """March arrived (FUN_004B08F0 direction 8): the saved mode action (+0x164); it acts in it from the next tick."""
    w.task = getattr(w, "after", "") or MODE_TASK[c["mode"]]
    walkers.schedule(g, w, 1)


def _stand(g, w, c):
    """Modes on the slot, every tick: hold (10), attack (0x11), special (0xB); the horsemen's regroup (0x12)."""
    if not c["mob"]:
        return _go_home(g, w)
    if w.role == "rabble":
        return _rabble(g, w, c)
    if w.task == "hold":                           # FUN_004B10A0: stand; back to the slot only by the timers
        if _back_to_slot(g, w, c, slot_tile(c, w.slot)):
            return None
        return walkers.schedule(g, w, 1)
    if w.task == "regroup":
        return _regroup(g, w, c)
    if w.role == "horseman":
        return _horseman(g, w, c)
    _engage(g, w, c, 6)                            # hoplite 0x11 / 0xB (fig_handler_hoplite 0x004B26B0)


def set_target(w, t):
    """figure_set_target 0x004E3280: +0x82 = t; t's flags |= 2 (sticky: cleared only when t is deleted,
    figure_clear_target_links 0x004E32C0), the mark nearest_enemy skips for hoplites / horsemen in 0x11 / 0xB."""
    w.target_id = t.id if t is not None else 0
    if t is not None:
        t.tagged = True


def _engage(g, w, c, leash):
    """FUN_004B0B60 for a hoplite / horseman: the slot (F.dest + OFF); its target (+0x82) kept while alive (state 1,
    not dying, visible); within leash of the slot and none: nearest_enemy(its tile, leash) and figure_set_target;
    dest = the target's tile, else the slot (also beyond the leash: the target is kept); then figure_move (_chase)."""
    slot = slot_tile(c, w.slot)
    t = g.walkers.get(getattr(w, "target_id", 0))
    if t is None or t.anim == "die" or getattr(t, "hidden", False):
        t, w.target_id = None, 0
    dest = slot
    if max(abs(w.x - slot[0]), abs(w.y - slot[1])) < leash:
        if t is None:
            t = nearest_enemy(g, w, c, leash)
            if t is not None:
                set_target(w, t)
        if t is not None:
            dest = (t.x, t.y)
    return _chase(g, w, dest)


def _horseman(g, w, c):
    """fig_handler_horseman 0x004B1840, attack 0x11 and hit-and-run 0xB: nearest_enemy within 6 of the horseman (none:
    engage; 0x11 also attack_timer 0); one within 6 but none within 3: formation_charge at it; within 3: 0x11
    engages, 0xB counts (+0x13C, named god_attack_kind) and engages below 5, at 5 the company regroups (FUN_004E2500)."""
    t6 = nearest_enemy(g, w, c, 6)
    if t6 is None:
        w.atk = 0 if w.task == "attack" else getattr(w, "atk", 0)
        return _engage(g, w, c, 6)
    if nearest_enemy(g, w, c, 3) is None:
        w.timer = 0
        charge(g, w.comp, c, t6)
        if w.task != "charge":                     # formation_charge refused: nothing else this tick
            walkers.schedule(g, w, 1)
        return None
    if w.task == "attack":
        return _engage(g, w, c, 6)
    w.hits = getattr(w, "hits", 0) + 1
    if w.hits < 5:
        return _engage(g, w, c, 6)
    w.timer, w.hits = 0, 0
    _regroup_start(g, c)
    walkers.schedule(g, w, 1)


def _ready(c, m):
    """FUN_004DD0F0: not walking home to the slot after a rout (action 3; ours has none) and the company ready."""
    return bool(c.get("ready", True))


def _regroup_start(g, c):
    """FUN_004E2500: every member not dying / fighting of a ready company: spiral 0, rabble / horsemen action 0x12."""
    for m in members(g, c):
        if m.anim or not _ready(c, m):
            continue
        m.spiral = 0
        if m.role in ("rabble", "horseman"):
            m.task = "regroup"
            m.cpath = None


def _leader(g, w, c):
    """FUN_004E24A0: in a company of the player (+0x69 == 0) the first member (F+0x08 order: ours by slot) not dying;
    else the figure itself."""
    for m in sorted(members(g, c), key=lambda m: m.slot):
        if m.anim != "die":
            return m
    return w


def _regroup(g, w, c):
    """Action 0x12 (fig_handler_horseman 0x004B1840): the leader's timer + 1; past 8 the company's mode-2 layout again
    (FUN_004E2320: members 0xB, marching ones keep 0xB saved); else its dest one tile against its direction field
    (+0x11; 8..10 after a walk's end give 4..6) and action 9 with 0x12 saved, spiral 0. The others take the leader's
    action; off their spot (OFF[layout][slot] + the leader's tile) they march with that action saved (9 is not saved)
    to OFF + the leader's dest (FUN_004B08F0 with +0x164 == 0x12); on it they stand in it."""
    lead = _leader(g, w, c)
    if lead is w:
        w.timer = getattr(w, "timer", 0) + 1
        if w.timer > 8:
            w.timer = 0
            _regroup_end(g, c)
            return walkers.schedule(g, w, 1)
        d = getattr(w, "xdir", 4)
        o = d - 4 if d - 4 >= 0 else d + 4
        dx, dy = {0: (0, -1), 1: (1, -1), 2: (1, 0), 3: (1, 1), 4: (0, 1), 5: (-1, 1), 6: (-1, 0)}.get(o, (-1, -1))
        w.rdest = (w.x + dx, w.y + dy)
        w.task, w.after, w.spiral = "march", "regroup", 0
        o = OFF.get(c["layout"], OFF[1])[w.slot % 8]   # FUN_004B08F0: OFF[layout][slot] + the leader's (own) dest
        _route(g, w, c, dest=(w.rdest[0] + o[0], w.rdest[1] + o[1]))
        return None
    # the leader fighting (5): off the spot the saved 5 resolves on arrival to the mode's action (FUN_004B08F0); on
    # the spot the exe sets 5 without an opponent and figure_fight_end restores the follower's own last saved action
    # (from its last fight; ours keeps no such record: it stays in 0x12, not settled)
    fight = lead.anim == "fight"
    a = MODE_TASK[c["mode"]] if fight else lead.task
    o = OFF.get(c["layout"], OFF[1])[w.slot % 8]
    if (w.x, w.y) != (lead.x + o[0], lead.y + o[1]):
        if a != "march":
            w.after = a
        w.task, w.spiral = "march", 0
    elif not fight:
        w.task = a
    if w.task != "march":
        return walkers.schedule(g, w, 1)
    if getattr(w, "after", "") == "regroup":      # FUN_004B08F0, +0x164 == 0x12: OFF + the leader's dest
        rd = getattr(lead, "rdest", None) or (lead.x, lead.y)
        return _route(g, w, c, dest=(rd[0] + o[0], rd[1] + o[1]))
    return _route(g, w, c)


def _regroup_end(g, c):
    """FUN_004E2320: the mode-2 layout (layout_for) and every ready member not dying / fighting: spiral 0; rabble,
    hoplites, horsemen marching keep 0xB saved, the others take 0xB (special)."""
    if c.get("morale", 50) < 21:                  # FUN_005231E0(0x22): close to breaking
        g.message(f"Company {next((s for s, x in companies(g).items() if x is c), 0)} is close to breaking "
                  f"(morale {c['morale']}).")
    c["layout"] = layout_for(c)
    for m in members(g, c):
        if m.anim or not _ready(c, m):
            continue
        m.spiral = 0
        if m.task == "march":
            m.after = "special"
        else:
            m.task = "special"
            m.cpath = None


DIRS = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def dir_angle(x, y, tx, ty):
    """FUN_0058D1F0: the 8-way direction from (x, y) toward (tx, ty) by the slope (x 100, the diagonal within
    1:4); 0 on its own tile."""
    ax, ay = abs(tx - x), abs(ty - y)
    if ay < ax:
        r = ax * 100 // ay if ay else 0
    elif ax < ay:
        r = -(ay * 100 // ax) if ax else 0
    else:
        r = 100
    if x == tx:
        if ty < y:
            return 0
        if y < ty:
            return 4
        return 0
    if tx < x:
        if y == ty:
            return 6
        if ty < y:
            return (0 if r < -399 else 7) if r < 400 else 6
        return (5 if r > -400 else 4) if r < 400 else 6
    if y == ty:
        return 2
    if ty < y:
        return (1 if r > -400 else 0) if r < 400 else 2
    return (4 if r < -399 else 3) if r < 400 else 2


def _face_to(w, x, y):
    w.xdir = dir_angle(w.x, w.y, x, y)
    w.face = DIRS[w.xdir]


def _fire(g, w, c, rng, shot_at, engage=False):
    """The rabble's stone (bugs.md 433): archer_fire_update 0x004B2F70 (hold 10 / skirmish 0xB: the stone at
    attack_timer 7) and the rabble part of engage 0x004B0B60 (attack 0x11: at 8), every tick. The reload counter
    (+0x6B, w.reload) + 1; past col7 (rabble 70..80 by difficulty): 0 and missile_target_search(range col6): none ->
    attack_timer 0, target 0, done; else attack_timer 1, facing it. With a target (+0x82, w.target_id; a monster only
    of class 8): it is marked attacked (+0x84); within col6 (Chebyshev) the rabble stands (route freed), faces it,
    at attack_timer 1 the sound, at shot_at the stone (0x2D from its tile to the target's tile, figure 0x004D9D70)
    and the company's firing timer +0x5C = 6 (0x004B31AD); attack_timer + 1 (past 100: 0). Hold / skirmish do not
    check the target is alive (the stale record's tile: ours its last seen tile, w.tpos); engage cleared it before.
    Returns True when it stands to throw."""
    from .defences import target_search, shoot
    t = g.walkers.get(w.target_id) if getattr(w, "target_id", 0) else None
    w.reload = getattr(w, "reload", 0) + 1
    if w.reload > units.col(g, w, "missile_rate"):
        w.reload = 0
        t = target_search(g, w, rng)
        if t is None:
            w.atk, w.target_id = 0, 0
            return False
        w.atk, w.target_id = 1, t.id
        _face_to(w, t.x, t.y)
    if not getattr(w, "target_id", 0):
        return False
    if t is not None and t.role == "monster" and units.unit_class(t) != 8:
        w.target_id = 0
        return False
    if t is not None:
        w.tpos = (t.x, t.y)
        t.tagged = True                        # figure_set_target: flags |= 2
    pos = getattr(w, "tpos", None)
    if pos is None:
        return False
    if max(abs(pos[0] - w.x), abs(pos[1] - w.y)) > rng:
        return False
    _face_to(w, *pos)
    atk = getattr(w, "atk", 0)
    if atk == 1:
        walkers.sfx(g, w, "shot")              # FUN_004D9D20 (rabble_rock; play mode only)
    elif atk == shot_at:
        shoot(g, w, t, aim=None if t is not None else pos)
        c["firing"] = 6
        if not engage:                         # archer_fire_update's stone sets cStack_9 = 1: anim_frame keeps the 0
            w.throw_t0, w.throw_ref = g.tick, 0    # it set (no restore), the throw starts again at frame 1
    w.atk = 0 if atk + 1 > 100 else atk + 1
    w.rfree = True                             # figure_route_free: its next walk finds a route from progress 15
    return True


def _rabble(g, w, c):
    """A mobilized rabble on its slot, every tick (fig_handler_rabble 0x004B31F0): hold 10, skirmish 0xB, attack 0x11;
    then its picture (the tail): in 10 / 0xB / 0x11 with a target (+0x82) the fight group 6945 (pick up a stone and
    throw) by sprite_anim_step(.., rate 100) on its anim_frame, in 0xB / 0x11 only while it does not walk this tick
    (cStack_9 == 0: hold, a throw within col6, at its dest); else the walk group. Play mode: look()."""
    w.rmoving = False
    r = _rabble_act(g, w, c)
    stand = w.task == "hold" or (w.task in ("special", "attack") and not w.rmoving)
    if stand and getattr(w, "target_id", 0):
        if getattr(w, "throw_t0", None) is None:
            w.throw_t0 = g.tick                  # the counter runs on from the frame it stood on (look [12])
            w.throw_ref = getattr(w, "acount", 0)
    else:
        w.throw_t0 = None
    return r


def _rabble_act(g, w, c):
    rng = units.col(g, w, "missile_range")
    slot = slot_tile(c, w.slot)
    if w.task == "special":
        from .defences import target_search
        if target_search(g, w, 5) is not None:   # an enemy within 5: dest one tile against its direction field
            d = getattr(w, "xdir", 4)              # (+0x11: 8..10 after a walk's end give 4..6, as the exe)
            o = d - 4 if d - 4 >= 0 else d + 4
            dx, dy = {0: (0, -1), 1: (1, -1), 2: (1, 0), 3: (1, 1), 4: (0, 1), 5: (-1, 1), 6: (-1, 0)}.get(o, (-1, -1))
            return _chase(g, w, (w.x + dx, w.y + dy))
        hold = target_search(g, w, rng) is None
        if hold and _back_to_slot(g, w, c, slot):
            _fire(g, w, c, rng, 7)
            return None
        _fire(g, w, c, rng, 7)
        return walkers.schedule(g, w, 1)
    if w.task == "hold":
        back = _back_to_slot(g, w, c, slot)
        _fire(g, w, c, rng, 7)
        return None if back else walkers.schedule(g, w, 1)
    # attack (0x11): engage 0x004B0B60 with leash col6 + 4
    leash = rng + 4
    t = g.walkers.get(getattr(w, "target_id", 0))
    if t is None or t.anim == "die" or getattr(t, "hidden", False):
        t, w.target_id = None, 0
    dest = slot
    if max(abs(w.x - slot[0]), abs(w.y - slot[1])) < leash:
        if t is None:
            t = nearest_enemy(g, w, c, leash)
            if t is not None:
                set_target(w, t)
                w.tpos = (t.x, t.y)
        if t is not None:
            dest = (t.x, t.y)
    if _fire(g, w, c, rng, 8, engage=True):
        return walkers.schedule(g, w, 1)
    return _chase(g, w, dest)


def _back_to_slot(g, w, c, slot):
    """FUN_004B10A0 (hold's first part): off its slot while the company's melee (+0x50) and under-fire (+0x5E)
    timers are 0 -> march back (action 9, the mode saved). True when it turned to march."""
    if (w.x, w.y) != slot and c.get("melee", 0) < 1 and c.get("under", 0) < 1:
        w.task, w.after = "march", w.task
        _route(g, w, c)
        return True
    return False


def _chase(g, w, dest):
    """figure_move toward dest (engage's chase 0x004B0B60, the skirmisher's step back), every tick: on dest's tile
    nothing (checked before figure_move, also mid-step); without a route (route_id < 1: none yet, used up, freed by a
    throw) figure_find_route, route mode 0 (walkers.route0) to dest as it is now, progress 15; then the route is
    walked to its end (8) even when dest moves on; no route: 10 (lost); a blocked next tile: 9, the route freed."""
    if w.__dict__.pop("rfree", False):
        w.cpath = None
    if (w.x, w.y) == dest:
        return walkers.schedule(g, w, 1)
    if w.__dict__.get("cpath") is None:
        if not (0 <= dest[0] < N and 0 <= dest[1] < N):
            return walkers.schedule(g, w, 1)
        p = walkers.route0(g, (w.x, w.y), dest)
        if not p:
            w.xdir = 10
            return walkers.schedule(g, w, 1)
        w.cpath, w.fprog = list(p), 15
    ok = walkers.walkable(g)

    def decide():
        if not w.cpath:
            w.cpath = None
            return 8
        nxt = w.cpath[0]
        if not ok[nxt[1] * N + nxt[0]]:
            w.cpath = None
            return 9
        w.cpath.pop(0)
        return nxt

    r = advance(g, w, speed(g, w), decide)
    w.rmoving = r not in (8, 9, 10)                # figure_move went on (the rabble's cStack_9 stays 1)
    if w.rmoving:
        w.acount = (getattr(w, "acount", 0) + 1) % 12
    walkers.schedule(g, w, 1)


def timers(g):
    """FUN_004DF410 (cycle step 29) for the player's companies: melee (+0x50), firing (+0x5C) and under-fire (+0x5E)
    count down; no enemy unit alive: all 0; a member fighting (action 5): melee 6."""
    alive = any(r in ENEMY_UNITS for r in g.walkers.roles())
    for c in companies(g).values():
        for k in ("melee", "firing", "under"):
            if c.get(k, 0) > 0:
                c[k] = 0 if not alive else c[k] - 1
        if any(g.walkers[i].anim == "fight" for i in c.get("ids", ()) if i in g.walkers):
            c["melee"] = 6


def charge(g, slot, c, t):
    """formation_charge 0x004DD6D0(t's tile): refused (nothing happens) unless mobilized, the tile is reached from the
    standard (ours: the company's dest, where it stands; route_distance) and is not the company's position
    (+0x2E/+0x30, slot 0's tile). Then F.dest = the tile, layout 1 (the direction from the tile to itself is 0), and
    every member not dying / fighting of a ready company: spiral 0, the hit-and-run count 0, the action saved (not
    0x10), action 0x10 (charge at 2 x col8), route freed. True when it charged."""
    from .invaders import company_pos
    dest = (t.x, t.y)
    if not c.get("mob") or dest == company_pos(g, c):
        return False
    if c.get("dest") and c["dest"] != dest and walkers.route0(g, c["dest"], dest) is None:
        return False
    c["dest"], c["layout"] = dest, 1
    for m in members(g, c):
        if m.anim or not _ready(c, m):
            continue
        m.spiral, m.hits = 0, 0
        if m.task != "charge":
            m.saved = m.task
        m.task = "charge"
        m.path, m.fprog, m.cpath = walkers.route0(g, (m.x, m.y), slot_tile(c, m.slot)) or [], 15, None
        walkers.schedule(g, m, 1)
    return True


def _charge_hit(g, w):
    """horseman_charge_hit 0x004E1080: A = attack (x4 never for player horsemen), dmg = ((30 - own armor) / 20) * A."""
    o = g.walkers.get(w.foe)
    if o is None:
        return
    A, Arm = units.col(g, w, "attack"), units.col(g, w, "armor")
    dmg = ((30 - Arm) // 20) * A if A else 0
    o.dmg = getattr(o, "dmg", 0) + dmg
    if o.dmg > units.col(g, o, "hp"):
        units.kill(g, o, w)
    w.task = getattr(w, "saved", "attack")


def _after_charge(g, w, c):
    """0x10 arrived (direction 8): the saved action, anim_frame 0; it acts in it from the next tick."""
    w.task = getattr(w, "saved", "attack")
    walkers.schedule(g, w, 1)


def _vanish(g, w, c):
    if w.id in c["ids"]:
        c["ids"].remove(w.id)
    units.remove(g, w)
    if c.get("event"):                  # event troops (0x004B1330 action 7): off the map at the entry, deleted
        c["members"] = max(0, c["members"] - 1)
        if c["members"] == 0:
            _event_company_gone(g, w.comp, c)


def _abroad(g, w, c):
    """0xF: hidden on the exit tile while the expedition is away (ours: off the map, counted in the company)."""
    if w.id in c["ids"]:
        c["ids"].remove(w.id)
    units.remove(g, w)


def died(g, w, by):
    """A soldier fell: the city pays (charge_death), the company loses a member and morale (0x004DDFF0)."""
    c = companies(g).get(getattr(w, "comp", 0))
    if by is not None:
        from .hooks import an
        g.message(f"{an(by.role)} killed {an(w.role)} of company {getattr(w, 'comp', '?')} at ({w.x},{w.y})")
    if c is None:
        return
    if not c.get("event") and not c.get("sanct"):  # +0x94 == 0: the palace's own companies
        w.charged = charge_death(g, w)
    field(c)
    c["members"] = max(0, c["members"] - 1)
    if c.get("event"):                  # formation_morale_add skips +0x94 companies: no morale loss, no rout
        if c["members"] == 0:
            _event_company_gone(g, w.comp, c)
        return
    if c.get("sanct"):                  # sanctuary troops (+0x94 = 1): the same; refilled monthly at the sanctuary
        if c["members"] == 0:
            companies(g).pop(w.comp, None)
        return
    morale.member_lost(c, morale.player_count(g, w.comp, c))
    if c["members"] == 0:
        companies(g).pop(w.comp, None)
        g.message(f"Company {w.comp} has been wiped out.")


def fight_over(g, w):
    if getattr(w, "after_fight", "") == "home":
        w.after_fight = ""
        return _go_home(g, w)
    c = companies(g).get(getattr(w, "comp", 0))
    if c is None:
        return units.remove(g, w)
    w.task = w.task if w.task in ("hold", "attack", "special", "march") else MODE_TASK[field(c)["mode"]]
    if w.task == "march":
        return _route(g, w, c, keep=True)
    walkers.schedule(g, w, 1)


ENEMY_UNITS = ("enemy_infantry", "enemy_archer", "enemy_cavalry", "enemy_transport", "enemy_warship")


def peace(g):
    """The standard's peace test (fig_handler_standard 0x004B3E00, also 0x0050EB90): g_months_since_enemy > 1,
    g_months_to_next_invasion > 1, g_enemy_units_alive == 0 (military_counts_on_figure 0x004E3420: types 0x28..0x2A,
    0x3F, 0x40 from figure_create to figure_delete, dying and hidden ones too) and g_enemy_warships == 0 (ours: the
    walker table's role counts, Walkers.roles)."""
    from . import alarm
    if alarm.months_since_enemy(g) < 2 or alarm.months_to_next(g) < 2:
        return False
    return not any(r in ENEMY_UNITS for r in g.walkers.roles())


def standards(g):
    """fig_handler_standard 0x004B3E00, every tick (each company's standard figure, type 0xE), its morale part, for
    the palace companies (+0x94 == 0; formation_morale_add skips the others):
    - not ready (+0x93 == 0; nothing in the exe writes 0 there: a company never routs, ours' older saves only):
      mobilized off (+0x90 = 0); in peace ready again, morale + 80, the waver counters +0x73 / +0x66 cleared;
    - ready, in peace: not mobilized -> morale + 80 every tick; mobilized -> the standard's timer (+0x36) + 1, at 26
      it is 0 again and morale + 1. Outside peace nothing changes (the counters are not cleared)."""
    comps = companies(g)
    if not comps:
        return
    p = None
    for s, c in comps.items():
        if s > 20 or c.get("event") or c.get("sanct"):
            continue
        ready = c.get("ready", True)
        if not ready:
            c["mob"] = False
        if p is None:
            p = peace(g)
        if not p:
            continue
        if not ready:
            c["ready"], c["rout"], c["waver"] = True, 0, 0
            morale.add(c, 80)
        elif not c.get("mob"):
            morale.add(c, 80)
        else:
            c["mtimer"] = c.get("mtimer", 0) + 1
            if c["mtimer"] >= 26:
                c["mtimer"] = 0
                morale.add(c, 1)


def day(g):
    """Daily (ours' step-50 point): mobilized companies keep their members on the map (the recruits appear, extras go
    home); soldiers of disbanded companies go home; the last tick an enemy was seen. The standard's morale rules run
    every tick (standards)."""
    from . import state
    st = state(g)
    comps = companies(g)
    enemy = any(f.role in ("enemy_infantry", "enemy_archer", "enemy_cavalry") and f.anim != "die"
                for ids in contact.tiles(g).values() for f in (g.walkers.get(i) for i in ids) if f is not None)
    if enemy:
        st["last_enemy"] = g.tick
    for s, c in list(comps.items()):
        field(c)
        if c.get("event") or c.get("sanct"):
            if c["mob"] and c["ready"] and not c.get("recalled"):
                sync(g, s, c)
            continue
        if c["mob"] and c["ready"]:
            sync(g, s, c)
    live = {i for c in comps.values() for i in c.get("ids", [])}
    for w in list(g.walkers.values()):
        if w.role in ("rabble", "hoplite", "horseman") and w.id not in live and w.anim != "die" \
                and w.task not in ("gohome",):
            _go_home(g, w)


# --- defensive aid: event troops 21..30 (aid_army_spawn 0x004E2C10, formation_create_event 0x004E2AC0) ---------

def entry_tile(g):
    """The map entry moved to the nearest walkable tile without a building (route_tile_check 0x004D2C60)."""
    ex, ey = g.world.entry
    ok = walkers.walkable(g)
    for r in range(0, 30):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                x, y = ex + dx, ey + dy
                if 0 <= x < N and 0 <= y < N and ok[y * N + x] and not g.world.occ[y, x]:
                    return (x, y)
    return (ex, ey)


def aid_split(c):
    """Company sizes for c soldiers of one type: < 9 one; 9..16 (c - c/2, c/2); >= 17 (c - 2*(c/3), c/3, c/3)."""
    if c <= 0:
        return []
    if c < 9:
        return [c]
    if c <= 16:
        return [c - c // 2, c // 2]
    return [c - 2 * (c // 3), c // 3, c // 3]


def aid_arrive(g, ev_id, city_id, n, nation):
    """aid_army_spawn 0x004E2C10: n (<= 150) soldiers of the player's own types, split by the sending nation's army
    shares (col 9 of rows 0..2): rabble = missile%, horsemen = cavalry%, hoplites the rest; companies in slots 21..30
    (none free: not created), mobilized, mode 0 (hold), morale 100, ready; they appear on the map entry and take
    their slots near it. Ours: a company keeps at most 8 soldiers (the exe's member list has 8 entries; larger
    shares overflow it, military.md / world-map.md 6.8: not certain). Returns the number of companies made."""
    d = units.data()["difficulty"][g.rules.get("difficulty", "Normal")]["armies"][max(0, min(10, nation))]
    n = min(n, 150)
    rab = d["missile"]["frequency"] * n // 100
    hor = d["cavalry"]["frequency"] * n // 100
    hop = n - rab - hor
    comps = companies(g)
    e = entry_tile(g)
    made = 0
    for t, cnt in (("hoplite", hop), ("rabble", rab), ("horseman", hor)):
        for size in aid_split(cnt):
            slot = next((i for i in range(21, 31) if i not in comps), None)
            if slot is None:
                continue
            c = comps[slot] = field({"type": t, "members": min(8, size), "event": ev_id, "city": city_id})
            c.update(mob=True, mode=0, morale=100, ready=True, layout=1, banner=slot - 1)
            c["dest"] = reachable_tile(g, None, e, made) or e
            sync(g, slot, c)
            made += 1
    return made


def aid_recall(g, city_id):
    """0x004E3060: every event company of that city is recalled (+0x98): its soldiers walk to the map entry."""
    for s, c in list(companies(g).items()):
        if c.get("event") and c.get("city") == city_id:
            c["recalled"], c["mob"] = True, False
            for w in members(g, c):
                if w.anim == "fight":
                    w.after_fight = "home"
                else:
                    _go_home(g, w)
            if not members(g, c):
                companies(g).pop(s, None)


def _event_company_gone(g, slot, c):
    """An event company has no soldiers left: freed; the city's last one, not recalled -> 0x00481D40 (defeated)."""
    companies(g).pop(slot, None)
    if c.get("recalled"):
        return
    if any(o.get("event") and o.get("city") == c.get("city") for o in companies(g).values()):
        return
    from .. import empire
    f = getattr(empire, "aid_lost", None)
    if f is not None and empire.get(g) is not None:
        f(g, c["event"])


# --- expeditions (sim/empire/war.py) ------------------------------------------------------------------

def march_out(g, ev, slots):
    """expedition_send_forces 0x004DEB30: every member of each company (alive, not dying) is teleported, when the
    company is all at home (+0x03), to the road tile of the house soldier_home_house 0x004CDC50 picks for it (the
    shared round-robin cursor, so the members land 4 a house, several on one tile where houses share their road
    access), and gets action 0xD: march at its type's speed (col8) on a route-mode-0 route (walkers.route0: 4-way
    flood, 8-way trace, so they cut corners) to g_land_exit; there 0xF, hidden on the exit tile until the
    expedition comes back (ours: off the map, counted in the company). F.dest = the exit. Oracle 1L5-troopsmarch
    (tools/oracle_troops.py march): the same tiles, groups and pace."""
    exit_tile = tuple(g.world.exit)
    for s in slots:
        c = companies(g).get(s)
        if c is None:
            continue
        field(c)
        c["mob"], c["dest"] = False, exit_tile
        have = members(g, c)
        for w in have:
            w.task, w.path, w.fprog, w.cpath = "out", walkers.route0(g, (w.x, w.y), exit_tile) or [], 15, None
            walkers.schedule(g, w, 1)
        for k in range(len(have), c["members"]):
            x, y = house_tile(g, c["type"]) or exit_tile
            w = units.spawn(g, c["type"], x, y, comp=s, slot=k, good=SANCT_LOOK.get(s, ""), task="out", after="", target_id=0, next_shot=0,
                            face=(0, 1), mode=0, spiral=0)
            w.path = walkers.route0(g, (x, y), exit_tile) or []
            c["ids"].append(w.id)


def march_home(g, ev):
    """expedition_forces_home 0x004DEE60: the survivors walk in from the map exit to their houses (action 7, route
    mode 0), then home."""
    ex = tuple(g.world.exit)
    for s, c in companies(g).items():
        if c.get("away") != ev["id"]:
            continue
        field(c)
        c["dest"] = home_tile(g)
        for k in range(c["members"]):
            w = units.spawn(g, c["type"], ex[0], ex[1], comp=s, slot=k, good=SANCT_LOOK.get(s, ""), task="gohome", after="", target_id=0,
                            next_shot=0, face=(0, 1), mode=0, spiral=0)
            t = house_tile(g, c["type"]) or home_tile(g) or ex
            w.path = walkers.route0(g, ex, t) or []
            c["ids"].append(w.id)


def look(g, w):
    """Play mode: the rabble's throw (group 6945 at rate 100, data/play/military.json rabble work "throw"), from the
    tick it stood with a target (throw_t0, _rabble) to the next target search at least (reload +0x6B past col7: the
    target may go then; the next record carries it on); the frame is (c0 + 1 + gated ticks) % 12 with c0 the counter
    it had: [12] = acount (anim_frame: +1 a tick it walked, wrap 12; _walk, _chase) for a new target, 0 from a hold /
    skirmish stone (archer_fire_update leaves anim_frame 0 that tick: oracle 1B-inv-city company 1,
    frames 5 -> 6 at the search (dump 395), 11 -> 1 at the stone (401), 11 -> 0 at 412). Else the core's walk / fight /
    die drawing."""
    if w.anim or w.role != "rabble":
        return None
    t0 = getattr(w, "throw_t0", None)
    if t0 is None or w.task not in ("hold", "special", "attack"):
        return None
    f = w.face or (0, 1)
    end = g.tick + max(1, units.col(g, w, "missile_rate") + 1 - getattr(w, "reload", 0))
    return ["work", t0, end, f[0], f[1], 0, 0, 0, "throw", False, None, None, getattr(w, "throw_ref", None)]


def status(g, c):
    """Advisor / panel status text 51:N (FUN_00591610 over FUN_00525120): 24 abroad, 22 fleeing (not ready),
    21 going home, 23 fighting, 20 marching, 19 still (mobilized), 18 at home. Returns (N, clickable)."""
    c = field(c)
    if c.get("away"):
        return 24, False
    if not c["ready"]:
        return 22, False
    ms = members(g, c)
    if any(w.task == "gohome" for w in ms):
        return 21, True
    if any(w.anim == "fight" for w in ms):
        return 23, True
    if any(w.task in ("march", "charge", "out") for w in ms):
        return 20, True
    return (19 if c["mob"] else 18), True
