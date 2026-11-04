"""Towers and their sentries, wall patrols, arrows (docs/logic/military.md "Towers, walls and their sentries").

- Daily (buildings_spawn_walkers 0x0048CFB0 case 0x84): a tower on the palace's road network (labor.py staffs
  it only then) keeps a tower sentry above 50 % staff and a wall sentry at 100 %. The tower sentry deletes itself
  whenever the tower has no wall sentry (0x004BB7B0), so in practice both exist only at full staff (bug 92).
- Tower sentry (0x2E): an archer on the tower's back tile, drawn 98 px up; looks for a target every 21 ticks
  within 13 tiles (missile_target_search 0x00501940: invaders 50, wolves 10); fires every col7 + 24 ticks, the
  arrow leaving at the 10th tick of its 24-tick draw.
- Wall sentry (0x27): hidden in the tower; every 41 ticks picks a patrol post 8 tiles out in a round-robin
  heading (0x004CFD80) on the wall-walk grid (grid_walls 0x00587E50: tower/gatehouse tiles and the back corner of
  2x2 wall blocks), walks there (speed 5), stands 41 ticks, walks home. Invisible on tower/gatehouse tiles.
  Shoots (range col6, every col7 ticks) only while an invading company is on the map: wolves never.
- Arrows (0x2D player, 0x34 enemy): fly 4 fine units a tick (figure_line_move 0x004D9750, Flight) toward the target's
  tile and hit the first hittable figure on their tile after every move (0x004DCE00 / 0x004DCE20); 106 calls at most.
"""
from collections import deque

from ..systems import walkers, index
from . import units, contact, mrng

N = 228
TOWER_SEARCH = 21
WALL_WAIT = 41
POST = [(0, -8), (8, 0), (0, 8), (-8, 0)]


def palace(g):
    return next(iter(index.keyed(g, "palace")), None)


def staff_pct(g, b):
    need = g.cat.spec(b.key)["employees"]
    return b.employees * 100 // need if need else 100


def day(g):
    pal = palace(g)
    for b in index.keyed(g, "tower"):
        ok = (pal is not None and b.access is not None and pal.access is not None and b.network == pal.network
              and not b.burning)
        pct = staff_pct(g, b) if ok else 0
        ws = g.walkers.get(b.misc.get("wall_sentry", 0))
        if pct >= 100 and ws is None:
            ws = units.spawn(g, "wall_sentry", b.x, b.y, home=b.id, task="home", timer_end=g.tick + WALL_WAIT,
                             hidden=True, heading=b.misc.get("heading", 0), face=(0, 1))
            b.misc["wall_sentry"] = ws.id
        ts = g.walkers.get(b.misc.get("sentry", 0))
        if pct > 50 and ts is None and ws is not None:
            ts = units.spawn(g, "tower_sentry", b.x, b.y, home=b.id, task="watch", reload=0, face=(0, 1),
                             t0=g.tick)
            b.misc["sentry"] = ts.id


def tower_window(g, b):
    """The tower's info window (FUN_0057A3E0; docs/play/info.md), presentation only: unmanned (the Military advisor's
    towers order, 0x00FEAF24 == 0: 170:10), palace (170:8), network (on the palace's road network, else 170:9),
    sentry (the wall sentry slot +0x2A: 170:3 with one, else 170:4)."""
    pal = palace(g)
    return dict(unmanned=bool(getattr(g, "towers_off", False)), palace=pal is not None,
                network=pal is not None and b.access is not None and pal.access is not None and b.network == pal.network,
                sentry=b.misc.get("wall_sentry", 0) in g.walkers)


def _tower_ok(g, w):
    b = g.buildings.get(w.home)
    if b is None or b.employees < 1:
        return None
    pal = palace(g)
    if pal is None or b.network != pal.network:
        return None
    return b


# --- targets and line of fire ------------------------------------------------------------------

PRIORITY = {"enemy_infantry": 50, "enemy_archer": 50, "enemy_cavalry": 50, "enemy_warship": 30, "enemy_transport": 20,
            "wolf": 10}                                   # a loaded transport 40 (missile_target_search 0x00501940)


def line(a, b):
    """Tiles from a to b (Bresenham, a excluded)."""
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x1 > x0 else -1), (1 if y1 > y0 else -1)
    err = dx - dy
    out = []
    x, y = x0, y0
    while (x, y) != (x1, y1):
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
        out.append((x, y))
    return out


def blocks(g, x, y):
    """Line of fire 0x004D9B80: terrain & 0xC001 (wall, tower / gatehouse tile, tree), or a building tile (terrain & 8)
    whose piece byte has a low nibble != 0 (piece_blocks). Ours keeps 0x8000 (tower / gatehouse tiles) as the building
    key (on_defence)."""
    w = g.world
    if w.flags[y, x] & 0x4001:
        return True
    b = g.buildings.get(int(w.occ[y, x]))
    if b is not None and b.key in ("tower", "gatehouse"):
        return True
    return piece_blocks(g, x, y)


def piece_blocks(g, x, y):
    """g_grid_piece 0x00D00D68 & 0xF != 0 on a building tile: building_footprint_place 0x004A04B0 writes width - 1 into
    the low nibble of every tile of a footprint, so a tile blocks when the footprint that covers it was placed more
    than one tile wide: a plain building by its width (misc "w", else its size; storehouses, trading posts and docks are
    placed as 1x1 parts: data/military.json "los_part_width"), a composite (sanctuary, palace, pyramid) by the piece on
    the tile (monuments.footprint_width). Checked against the original's grids: tools/los_piece_check.py."""
    bid = int(g.world.occ[y, x])
    b = g.buildings.get(bid) if bid else None
    if b is None:
        return False
    return _piece_width(g, b, x, y) > 1


def _piece_width(g, b, x, y):
    if b.kind != "monument":
        pw = units.data().get("los_part_width", {}).get(b.key)
        if pw is not None:                       # [inside the size x size box, outside it (the dock's water square)]
            return pw[0] if b.x <= x < b.x + b.size and b.y <= y < b.y + b.size else pw[1]
        return b.misc.get("w", b.size) or 1
    from ..systems import monuments as mon
    return mon.footprint_width(b, x, y)


def on_defence(g, x, y):
    b = g.buildings.get(int(g.world.occ[y, x]))
    return bool(g.world.flags[y, x] & 0x4000) or (b is not None and b.key in ("tower", "gatehouse"))


def line_of_fire(g, a, b):
    """0x004D9B80: the line a -> b walked in fine units (figure_line_move_init on figure 0, from tile * 15 to tile * 15),
    a tile check after every 8 sub-steps at fine // 15 (the start tile too, when 8 sub-steps stay on it); from a wall /
    tower tile (terrain 0xC000) the first 6 checks are skipped (shooting over its own wall). Reaching b ends it (clear),
    also in the middle of 8 sub-steps, before that chunk's check; past 999 checks: blocked."""
    f = Flight(a, b)
    skip = 6 if on_defence(g, *a) else 0
    for _ in range(1000):
        for _ in range(8):
            if f.done():
                return True
            f.sub_step()
        if skip:
            skip -= 1
        elif blocks(g, f.fx // 15, f.fy // 15):
            return False
    return False


def target_search(g, w, rng):
    """missile_target_search 0x00501940: a strictly higher priority that is also strictly nearer replaces the pick."""
    best, best_d, best_p = None, rng, 0
    for tile, ids in list(contact.tiles(g).items()):
        for i in sorted(ids):
            f = g.walkers.get(i)
            if f is None or f.anim == "die" or getattr(f, "hidden", False):
                continue
            p = PRIORITY.get(f.role, 0)
            if f.role == "enemy_transport" and getattr(f, "loaded", False):
                p = 40
            if not p:
                continue
            d = max(abs(f.x - w.x), abs(f.y - w.y))
            if p > best_p and d < best_d and line_of_fire(g, (w.x, w.y), (f.x, f.y)):
                best, best_d, best_p = f, d, p
    return best


def enemy_companies(g):
    return any(f.role in ("enemy_infantry", "enemy_archer", "enemy_cavalry") and f.anim != "die"
               for ids in contact.tiles(g).values() for f in (g.walkers.get(i) for i in ids) if f is not None)


# --- arrows -----------------------------------------------------------------------------------------

class Flight:
    """The exe's line move in fine units (15 a tile; a tile's fine origin is tile * 15): figure_line_move_init
    0x004D9980 (deltas, Bresenham error, major axis), and one sub-step of figure_line_move 0x004D9750 (FUN_004D98E0
    error update + major delta - 1, the major axis +-1 (FUN_004D9B40 x / FUN_004D9B00 y), the minor axis +-1 and its
    delta - 1 when the error is >= 0). Ported literally: the tile is fine // 15, so a tile toward -x / -y is entered
    after 1 sub-step, one toward +x / +y after 15."""
    __slots__ = ("fx", "fy", "tx", "ty", "dx", "dy", "err", "major")

    def __init__(self, a, b):
        self.fx, self.fy = a[0] * 15, a[1] * 15
        self.tx, self.ty = b[0] * 15, b[1] * 15
        self.dx, self.dy = abs(self.tx - self.fx), abs(self.ty - self.fy)
        if self.dx < self.dy:
            self.err = self.dx * 2 - self.dy
        elif self.dy < self.dx:
            self.err = self.dy * 2 - self.dx
        else:
            self.err = 0
        self.major = 2 if self.dx < self.dy else 1

    def __getstate__(self):
        return [getattr(self, k) for k in self.__slots__]

    def __setstate__(self, st):
        for k, v in zip(self.__slots__, st):
            setattr(self, k, v)

    def done(self):
        return self.dx + self.dy < 1

    def _x(self):
        self.fx += (self.fx < self.tx) - (self.fx > self.tx)

    def _y(self):
        self.fy += (self.fy < self.ty) - (self.fy > self.ty)

    def sub_step(self):
        if self.major == 1:
            if self.err < 0:
                self.err += self.dy * 2
            else:
                self.err += (self.dy - self.dx) * 2
            self.dx -= 1
            self._x()
            if self.err >= 0:
                self.dy -= 1
                self._y()
        else:
            if self.err < 0:
                self.err += self.dx * 2
            else:
                self.err += (self.dx - self.dy) * 2
            self.dy -= 1
            self._y()
            if self.err >= 0:
                self.dx -= 1
                self._x()

    def move(self, n):
        """figure_line_move(f, n): n sub-steps; 1 when the line was already done at one of them (the call that finds
        it done returns 1, so a line ending on the n-th sub-step reports it on the next call)."""
        for _ in range(n):
            if self.done():
                return True
            self.sub_step()
        return False

    def tile(self):
        return self.fx // 15, self.fy // 15


HIT_2D_ROLES = ("enemy_infantry", "enemy_archer", "enemy_cavalry", "wolf", "enemy_warship")
MISSILE_ROLES = ("arrow", "enemy_arrow", "god_bolt")
SKIP_34 = frozenset(("enemy_infantry", "enemy_archer", "enemy_cavalry", "enemy_warship", "enemy_transport")
                    + MISSILE_ROLES)
LIFE_START, LIFE_END = 15, 120      # figure_create sets +0x39 = 15; the handlers +1 a call: gone past 120 (0x2D) /
                                    # at 121 (0x34): 106 calls (docs/logic/military.md "Missile flight")


def tile_list(g, tile):
    """The figures on a tile in the exe's tile-list order (grid_figure 0x00D0D878 + next_on_tile): figure_tile_list
    0x004DC860 appends a figure when it enters (figure_create, change_tile, jumps), so the earliest arrival is first;
    ours: contact.order (walkers.listed's stamp: the tick, then the order of entries in it)."""
    out = [w for w in g.walkers.values() if w.x == tile[0] and w.y == tile[1]]
    out.sort(key=contact.order)
    return out


def victim(g, a, kind):
    """The missile's hit test on its tile after the move: 0x004DCE00 -> 0x004DCD30 (0x2D, friendly): the first figure
    not dying, not hidden, of type 0x28..0x2A (invaders), 0x3B (wolf), 0x40 (warship), 0x3F (transport) unless its
    nation (+0x6E) is 8, a god of unit class 10 (hostile) or a monster of class 8; 0x004DCE20 -> 0x004DCE40 (0x34,
    hostile): the first not dying (hidden too) that is not of type 0, 6, 0xA, 0xE, 0x22, 0x23 (effects, fire, flags,
    flotsam: not walkers in ours), 0x28..0x2A, 0x2D, 0x34, 0x3F, 0x40, a god of class 9 only, a monster of class 7
    only (the missile itself is on the tile too: type 0x2D / 0x34, skipped)."""
    for f in tile_list(g, (a.x, a.y)):
        if f is a or f.anim == "die":
            continue
        r = f.role
        if kind == 0x2D:
            if f.__dict__.get("hidden"):
                continue
            if r in HIT_2D_ROLES or (r == "enemy_transport" and f.__dict__.get("nation") != 8):
                return f
            if r in ("god", "monster") and units.unit_class(f) == (10 if r == "god" else 8):
                return f
        else:
            if r in SKIP_34:
                continue
            if r in ("god", "monster"):
                if units.unit_class(f) == (9 if r == "god" else 7):
                    return f
                continue
            return f
    return None


def dir16(x0, y0, x1, y1):
    """FUN_0058D050: the 16-way direction from (x0, y0) to (x1, y1), 0 = map -y, clockwise toward +x (8 = +y). The
    ratio r = 100 * long / short side (negative when y is the long side); 0x004D9D70 stores it << 1 in +0x11."""
    adx, ady = abs(x1 - x0), abs(y1 - y0)
    if ady < adx:
        r = adx * 100 // ady if ady else 0
    elif adx < ady:
        r = -(ady * 100 // adx) if adx else 0
    else:
        r = 100
    if x0 == x1:
        return 0 if y1 < y0 else 8 if y1 > y0 else 0
    if x1 < x0:
        if y0 == y1:
            return 12
        if y0 <= y1:
            return 12 if r > 499 else 11 if r > 199 else (8 + (r > -500)) if r < -199 else 10
        return 12 if r > 499 else 13 if r > 199 else (0 if r < -499 else 15) if r < -199 else 14
    if y0 == y1:
        return 4
    if y0 <= y1:
        return 4 if r > 499 else 5 if r > 199 else (7 + (r < -499)) if r < -199 else 6
    return 4 if r > 499 else 3 if r > 199 else int(r > -500) if r < -199 else 2


def launch(g, shooter, aim, w):
    """0x004D9D70 on a new missile figure w (created at the shooter's tile, owner 1): line_counter 10, building_id =
    the shooter, a line move from its fine position to aim * 15, slope_offset = the shooter's + 18; +0x39 = 15."""
    w.shooter, w.aim, w.src = shooter.id, tuple(aim), (shooter.x, shooter.y)
    w.flight = Flight((shooter.x, shooter.y), tuple(aim))
    w.dir32 = dir16(shooter.x, shooter.y, aim[0], aim[1]) * 2
    w.life = LIFE_START
    w.t0 = g.tick + 1                # the look's origin: dt = moves made in the frame after tick t0's pass (play mode
    w.moved = False                  # draws the state after a pass at P.t = tick + 1); set again at the first call


def fly(g, w, kind):
    """One call of walker_player_missile 0x004BACE0 (kind 0x2D) / fig_handler_enemy_missile 0x004BD970 (0x34), up to
    the hit test. Returns (victim or None, arrived, expired). 0x2D: +0x39 + 1, past 120 it is marked gone (state 2)
    but still moves and tests this call; 0x34: at 121 it does not move and counts as arrived. figure_line_move(f, 4),
    then the hit test on its tile (every call, the start tile too)."""
    if not w.moved:
        w.moved, w.t0 = True, g.tick
    w.life += 1
    if kind == 0x2D:
        expired = w.life > LIFE_END
        arrived = w.flight.move(4)
    elif w.life < LIFE_END + 1:
        expired, arrived = False, w.flight.move(4)
    else:
        expired, arrived = True, True
    t = w.flight.tile()
    if t != (w.x, w.y):
        old = (w.x, w.y)
        w.prev, (w.x, w.y) = old, t
        w.arrived = g.tick
        walkers.listed(g, w)
        if w.role in units.CLASS:
            contact.track(g, w, old)
    return victim(g, w, kind), arrived, expired


def shoot(g, shooter, target, role="arrow", aim=None):
    """0x004D9D70: an arrow (0x2D) / enemy missile (0x34) from the shooter's tile toward the target's tile (or `aim`: a
    monster's dest, monster_missile_attack 0x00530ED0). It is a new figure: its first call is in this tick when its
    slot comes after the shooter's (walkers.add)."""
    h = 116 if shooter.role == "tower_sentry" else 36 if shooter.role == "wall_sentry" else 18
    a = walkers.new_walker(g, role=role, home=0, x=shooter.x, y=shooter.y)
    a.dmg, a.foe, a.height = 0, 0, h
    if shooter.role == "monster":               # drawn as the monster missile (fig_handler_enemy_missile / walker_player_
        a.pic = "monster"                       # missile, type 0x44 branch: group 0x222F, see play_heroes.py "missile")
    launch(g, shooter, tuple(aim) if aim is not None else (target.x, target.y), a)
    walkers.add(g, a, 1)
    contact.track(g, a, (a.x, a.y))
    return a


def arrow_act(g, a):
    """walker_player_missile 0x004BACE0 (role arrow, 0x2D) / fig_handler_enemy_missile 0x004BD970 (enemy_arrow,
    0x34). 0x2D: its shooter gone -> deleted at once; a hit: figure_hit(shooter, victim, 1), the victim's company is
    under fire from the shooter's (+0x5E = 6, +0x60), gone; none: gone when its line has ended (or past its life).
    0x34: it flies on without its shooter (figure_delete zeroes the record: the hit then has a type-0 attacker, attack
    0, no damage, and the shooter's group is 0); its hit marks the shooter's company (+0x5E = 6, +0x60 = the victim's
    company)."""
    kind = 0x2D if a.role == "arrow" else 0x34
    shooter = g.walkers.get(a.shooter)
    if kind == 0x2D and shooter is None:
        return units.remove(g, a)
    f, arrived, expired = fly(g, a, kind)
    if f is not None:
        from . import navy, hooks
        if shooter is None:
            pass                                 # a zeroed record hits for 0 (attack 0: figure_hit adds no damage)
        elif shooter.role in navy.SHIPS or f.role in navy.SHIPS:
            navy.hit(g, shooter, f)              # hull damage / the trireme's crew-scaled attack
        else:
            units.hit(g, shooter, f, missile=True)
        from . import invaders
        invaders.under_fire(g, kind, shooter, f)
        _missile_end(g, a, shooter, kind, False)
        return units.remove(g, a)
    if arrived or expired:
        _missile_end(g, a, shooter, kind, True)
        return units.remove(g, a)
    walkers.schedule(g, a, 1)


def _missile_end(g, a, shooter, kind, landed):
    """The end of a monster's missile (a hit or the line's end): collapse_debris_spawn(x, y, 1, 1, 4, 0) on its tile
    (the 0x44 branch of both handlers' picture tail, play mode only). A 0x34 (bad monster) that lands without a hit
    on a tile of an active building (0x004DCF20: g_grid_building of the missile's tile, state 1): the monster's hit
    sound (FUN_004DB7A0, slot 7) and wall_damage_add(building tile, 4, 2) (0x00492830): +2 on the building's own tile
    (a composite piece's), destroyed by building_destroyed_by_attack 0x004928C0 past 4 (the third missile); the
    monster's target building (+0x5E) is dropped when no longer active. A deleted shooter's record is zeroed (type 0):
    nothing. The 0x2D of a good monster lands harmlessly."""
    if getattr(a, "pic", None) != "monster":
        return
    from .. import effects
    effects.debris(g, a.x, a.y, 1)
    if not landed or kind != 0x34 or shooter is None or shooter.role != "monster":
        return
    b = g.buildings.get(int(g.world.occ[a.y, a.x]))
    if b is None or b.kind in ("ruin", "road"):
        return
    from . import state as mstate
    from ..heroes import monsters
    walkers.sfx(g, shooter, "hit")
    ox, oy = monsters.building_tile(b, a.x, a.y)
    dmg = mstate(g).setdefault("wall_damage", {})
    k = f"{ox},{oy}"
    dmg[k] = dmg.get(k, 0) + 2
    if dmg[k] > 4:
        dmg.pop(k, None)
        monsters.destroy_tile(g, shooter, ox, oy)
    tb = g.buildings.get(getattr(shooter, "tb", 0))
    if getattr(shooter, "tb", 0) and (tb is None or tb.kind == "ruin" or not monsters.target_alive(g, tb)):
        shooter.tb = 0


# --- sentries ---------------------------------------------------------------------------------------

def act(g, w):
    if w.role in ("arrow", "enemy_arrow"):
        return arrow_act(g, w)
    if w.anim == "die":
        return units.act_dying(g, w)
    if w.anim == "fight":
        return units.fight_tick(g, w)
    if w.role == "tower_sentry":
        return tower_act(g, w)
    return wall_act(g, w)


def tower_act(g, w):
    b = _tower_ok(g, w)
    if b is None or g.walkers.get(b.misc.get("wall_sentry", 0)) is None or b.misc.get("sentry") != w.id:
        if b is not None and b.misc.get("sentry") == w.id:
            b.misc.pop("sentry", None)
        return units.remove(g, w)
    rate = units.col(g, w, "missile_rate")
    rng = units.col(g, w, "missile_range")
    if w.task == "watch":
        t = target_search(g, w, rng)
        if t is None:
            return walkers.schedule(g, w, TOWER_SEARCH)
        w.task, w.reload, w.target_id = "fire", rate, t.id
        w.reload_end = g.tick + 1
    if w.task == "fire":
        t = target_search(g, w, rng)
        if t is None:
            w.task = "watch"
            return walkers.schedule(g, w, TOWER_SEARCH)
        w.face = _dir(w, t)
        if getattr(w, "shot_t0", None) is None or g.tick >= w.shot_t0 + 24:
            w.shot_t0 = g.tick                    # timer 1..24: the draw; the arrow at 10
            walkers.sfx(g, w, "shot")             # timer 1: FUN_004D9D20 (the volley sound; play mode only)
            w.next_arrow = (g.tick + 9, t.id)
            return walkers.schedule(g, w, 9)
        when, tid = w.next_arrow
        if g.tick >= when and tid:
            shoot(g, w, g.walkers.get(tid) or t)
            w.next_arrow = (0, 0)
            return walkers.schedule(g, w, (w.shot_t0 + 24 - g.tick) + rate)   # reload col7 after the draw
        return walkers.schedule(g, w, 1)


def _dir(w, t):
    return ((t.x > w.x) - (t.x < w.x), (t.y > w.y) - (t.y < w.y))


# grid_walls (0x00587E50): the three neighbours a wall tile needs (wall or tower, flags 0xC000) to be walkable, in
# the current view (the back corner of a 2x2 block as seen on screen); rebuilt on every turn (0x004A1B70)
WALL_NB = {0: ((1, 0), (0, 1), (1, 1)), 2: ((-1, 0), (0, 1), (-1, 1)),
           4: ((-1, 0), (0, -1), (-1, -1)), 6: ((1, 0), (0, -1), (1, -1))}


def wall_grid(g):
    """grid_walls (0x00587E50): walkable = tower/gatehouse tiles and wall tiles whose three neighbours toward the
    view's back corner (WALL_NB[g.view]; view 0: (x+1,y), (x,y+1), (x+1,y+1)) are wall or tower too. The view
    is the only presentation state the sim keeps (`view N`, docs/play/rotation.md "The view in the sim")."""
    from ..systems.services import occ_version
    c = contact.cache(g)
    view = getattr(g, "view", 0)
    v = (occ_version(g), view)
    gw = c.get("wallgrid")
    if gw is not None and gw[0] == v:
        return gw[1]
    w = g.world
    defn = set()
    for b in index.of(g, "tower", "gatehouse"):
        ys, xs = (w.occ == b.id).nonzero()
        defn.update(zip(xs.tolist(), ys.tolist()))
    ys, xs = (w.flags & 0x4000).nonzero()
    walls = set(zip(xs.tolist(), ys.tolist()))
    solid = walls | defn
    ok = set(defn)
    nb = WALL_NB[view]
    for x, y in walls:
        if all((x + dx, y + dy) in solid for dx, dy in nb):
            ok.add((x, y))
    c["wallgrid"] = (v, (ok, defn))
    return ok, defn


def view_changed(g):
    """0x004CFEE0, after the grid is rebuilt for the new view: a wall sentry on a tile that is no longer walkable
    goes to the first walkable tile in the squares 1 and 2 tiles around it (0x004A3A20 / 0x004A3A70: rows top
    to bottom, columns left to right) and walks home from there; with none, it is put back on its tower. (The
    exe sets the walk-home action and frees the route on g_current_figure, not on the sentry: an exe slip; ours
    sends the sentry itself home.)"""
    ok, _ = wall_grid(g)
    for w in list(g.walkers.values()):
        if w.role != "wall_sentry" or not units.alive(w):
            continue
        if (w.x, w.y) in ok:
            if w.path and any(t not in ok for t in w.path):    # ours: a walk through a tile the turn closed is
                w.path = wall_path(g, (w.x, w.y), w.path[-1]) or []   # re-routed (the exe's route not read)
            continue
        spot = None
        for r in (1, 2):
            spot = next(((x, y) for y in range(max(0, w.y - r), min(N - 1, w.y + r) + 1)
                         for x in range(max(0, w.x - r), min(N - 1, w.x + r) + 1) if (x, y) in ok), None)
            if spot:
                break
        b = g.buildings.get(w.home)
        old = (w.x, w.y)
        if spot is None:
            if b is None:
                units.remove(g, w)
                continue
            spot = (b.x, b.y)
            w.task, w.path, w.timer_end = "home", [], g.tick
        else:
            w.task = "back"
            w.path = (wall_path(g, spot, (b.x, b.y)) or []) if b is not None else []
        w.prev = (w.x, w.y) = spot          # a jump, not a step: the exe sets the new tile and fine position
        w.arrived = g.tick
        walkers.listed(g, w)
        contact.track(g, w, old)


def wall_path(g, a, b):
    ok, _ = wall_grid(g)
    if a == b:
        return []
    prev = {a: None}
    q = deque([a])
    while q:
        t = q.popleft()
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            n = (t[0] + dx, t[1] + dy)
            if n in ok and n not in prev:
                prev[n] = t
                if n == b:
                    out = [n]
                    while prev[out[-1]] != a:
                        out.append(prev[out[-1]])
                    return out[::-1]
                q.append(n)
    return None


def patrol_target(g, w, b):
    """0x004CFD80: 8 tiles out along the tower's round-robin heading, the first walkable wall tile in growing
    squares; else up to 4 tries 3 tiles out."""
    ok, _ = wall_grid(g)
    ax, ay = b.x, b.y

    def ring(px, py, size):
        for r in range(1, 7):
            for y in range(py - r, py + size + r):
                for x in range(px - r, px + size + r):
                    if (x, y) in ok and 0 <= x < N and 0 <= y < N:
                        return (x, y)
        return None

    d = b.misc.get("heading", 0)
    ox, oy = POST[d]
    t = ring(max(0, min(N - 1, ax + ox)), max(0, min(N - 1, ay + oy)), 1)
    if t is not None:
        b.misc["heading"] = (d + 1) % 4
        return t
    for _ in range(4):
        old = d
        d = (d + 1) % 4
        ox, oy = POST[old]
        t = ring(max(0, min(N - 1, ax + 3 * ox // 8)), max(0, min(N - 1, ay + 3 * oy // 8)), 2)
        if t is not None:
            b.misc["heading"] = d
            return t
    b.misc["heading"] = d
    return None


def wall_act(g, w):
    b = _tower_ok(g, w)
    ok, defn = wall_grid(g)
    if b is None or b.misc.get("wall_sentry") != w.id or (w.x, w.y) not in ok:
        if b is not None and b.misc.get("wall_sentry") == w.id:
            b.misc.pop("wall_sentry", None)
        return units.remove(g, w)
    w.hidden = (w.x, w.y) in defn
    if w.task in ("post", "walk", "back") and enemy_companies(g) and not w.hidden:
        t = target_search(g, w, units.col(g, w, "missile_range"))
        if t is not None and max(abs(t.x - w.x), abs(t.y - w.y)) <= 10:
            w.task, w.path = "shoot", []
    if w.task == "shoot":
        t = target_search(g, w, units.col(g, w, "missile_range"))
        if t is None:
            w.task, w.path = "back", wall_path(g, (w.x, w.y), (b.x, b.y)) or []
        else:
            w.face = _dir(w, t)
            w.shot_t0 = g.tick
            walkers.sfx(g, w, "shot")             # 0x004B9230: FUN_004D9D20 with the arrow (play mode only)
            shoot(g, w, t)
            return walkers.schedule(g, w, units.col(g, w, "missile_rate") + 1)
    if w.task == "home":
        if g.tick < w.timer_end:
            return walkers.schedule(g, w, w.timer_end - g.tick)
        t = patrol_target(g, w, b)
        p = wall_path(g, (w.x, w.y), t) if t else None
        if not p:
            w.timer_end = g.tick + WALL_WAIT
            return walkers.schedule(g, w, WALL_WAIT)
        w.task, w.path = "walk", p
    if w.task in ("walk", "back"):
        if w.path:
            nxt = w.path.pop(0)
            if nxt not in ok:
                return units.remove(g, w)
            units.step(g, w, nxt)
            w.hidden = nxt in defn
            return walkers.schedule(g, w, units.tile_ticks(g, w, units.col(g, w, "speed")))
        if w.task == "walk":
            w.task, w.timer_end = "post", g.tick + WALL_WAIT
            return walkers.schedule(g, w, WALL_WAIT)
        w.task, w.timer_end = "home", g.tick + WALL_WAIT
        return walkers.schedule(g, w, WALL_WAIT)
    if w.task == "post":
        if g.tick < w.timer_end:
            return walkers.schedule(g, w, min(40, w.timer_end - g.tick))
        w.task, w.path = "back", wall_path(g, (w.x, w.y), (b.x, b.y)) or []
        return walkers.schedule(g, w, 1)
    return walkers.schedule(g, w, WALL_WAIT)


def died(g, w, by):
    if by is not None:
        from .hooks import an
        g.message(f"{an(by.role)} killed {an(w.role)} at ({w.x},{w.y})")


def fight_over(g, w):
    walkers.schedule(g, w, 1)


def arrow_group(g, w, sh):
    """The picture of an arrow by its shooter as it is now (the handlers' tails, every tick; oracle 1D-arrows):
    0x2D (walker_player_missile 0x004BACE0): a wall / tower sentry (0x27 / 0x2E), or rabble (0xB) of the sanctuary
    companies 0x1F / 0x20 (Amazons) or in a Poseidon game -> SprAmbient group 79 (shadow 78), 32 directions; anyone
    else (rabble, triremes) -> group 51 (shadow 50), one picture. 0x34 (fig_handler_enemy_missile 0x004BD970): an
    enemy archer (0x28) of its company's nation (+0x6A) 0 -> 51, 1 -> 71 (shadow 70), else 79; any other shooter,
    or none (its record zeroed) -> 71. The 32-direction picture: ((dir32 - 4 view) mod 32 - 13) & 31 (scene.js)."""
    r = getattr(sh, "role", "")
    if w.role == "arrow":
        if r in ("tower_sentry", "wall_sentry"):
            return "a79"
        if r == "rabble" and (getattr(sh, "comp", 0) in (31, 32) or getattr(g, "poseidon", False)):
            return "a79"
        return "a51"
    if r == "enemy_archer":
        n = getattr(sh, "army", 0) or 0
        return "a51" if n == 0 else "a71" if n == 1 else "a79"
    return "a71"


def look(g, w):
    """Play mode: [kind, t0, end, face dx, dy, 0, 0, 0, block, False, extra]. Sentries: "work" with block
    "idle" / "shoot" / "post"; arrows: "arrow" with [src x, src y, aim x, aim y, height, shooter's army, dir32 (0x004D9D70: dir16 << 1),
    picture group (arrow_group)]."""
    if w.role in ("arrow", "enemy_arrow"):
        role = "monster_missile" if getattr(w, "pic", None) == "monster" else w.role
        sh = g.walkers.get(w.shooter)
        return ["arrow", w.t0, w.t0 + LIFE_END - LIFE_START + 1, 0, 0, 0, 0, 0, role, False,
                [w.src[0], w.src[1], w.aim[0], w.aim[1], w.height,
                 getattr(sh, "army", 0) or 0, getattr(w, "dir32", 0), arrow_group(g, w, sh)]]
    if getattr(w, "hidden", False):
        return ["hidden", 0, 0, 0, 0, 0, 0, 0, "", False]
    f = w.face or (0, 1)
    if w.anim:
        return None
    if w.role == "tower_sentry":
        st = getattr(w, "shot_t0", None)
        if st is not None and g.tick < st + 24:
            return ["work", st, st + 24, f[0], f[1], 0, 0, 0, "shoot", False, [98]]
        return ["work", getattr(w, "t0", 0), g.tick + 10 ** 6, f[0], f[1], 0, 0, 0, "idle", False, [98]]
    if w.task == "shoot":
        return ["work", getattr(w, "shot_t0", g.tick), getattr(w, "shot_t0", g.tick) + 32, f[0], f[1], 0, 0, 0,
                "shoot", False, [18]]
    if w.task == "post":
        return ["work", w.timer_end - WALL_WAIT, w.timer_end, f[0], f[1], 0, 0, 0, "post", False, [18]]
    return ["walk", 0, 0, 0, 0, 0, 0, 0, "", False, [18]]
