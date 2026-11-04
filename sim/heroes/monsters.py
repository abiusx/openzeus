"""Monsters (docs/logic/heroes-monsters.md "Monster actions as the exe"): figure type 0x44, role "monster", one per
monster id (monster records 0x00FE43F0). Handler figure_monster_update 0x004C8760, every tick, every action moving
by figure_move's sub-steps (rampage.move) in the header's route mode (route_mode):

  6   home (walk_then, lost 24), then 7                24  home = here, then 7
  7   rest / roam at the lair (monster_rest_update 0x005304B0): the day countdown, the scan byte (30..59 ticks): a god
      or an enemy -> 9, a building -> 26; else roam: a building / wall tile within 4 rings, else around home
  9   go for the target figure (0x00531050), 28 at Chebyshev 2..3; fights through sim/military/units.py
  26  to the building (lost at once in mode 3), 27 smash it (2 x the attack frames, building_destroyed_by_attack)
  28  the missile attack (monster_missile_attack 0x00530ED0)
  10/11/25 rampage (sim/heroes/rampage.py); 14..0x1D the guardians' actions (sim/heroes/guardians.py)
  0x17 held by a hero (0x00534150; the duel: combat.py)         4  dying (the fight engine)

Walker fields: mid (monster id, +0x0B), slot (scenario slot), ev (event id), uclass (7 good / 8 bad), aggr (+0x7B),
cats (+0x115..0x117), spawn (+0x2C/+0x2E), homexy (+0x30/+0x32), act (+0x38), timer (+0x36), tday (+0x92),
scan_t (the scan countdown byte +0x114; 27's smash count too), tb (+0x5E target building), tf (+0x82 target figure), rampage (+0x108),
dest, path.
"""
from . import state, data, hrng, msrand, monster_of_slot, slot_of_monster, lair
from ..systems import walkers
from ..military import units

N = 228
SPEED = 7                      # Figure_model row 68 col 8 (all difficulties): 12 ticks a tile
DIRS8 = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]
BLOCK = 0x2 | 0x4 | 0x200 | 0x80000 | 0x4000 | 0x8000         # rock, water, cliff, off-map, wall, tower/gate tile


def records(g):
    """Monster records (0x00FE43F0): {mid: {"fig": walker id, "ev": event id}}."""
    return state(g).setdefault("monsters", {})


def behaviour(g, m):
    d = data()["monsters"][m]["behaviour"]
    return d.get(g.rules.get("difficulty", "Normal")) or d["Normal"] if d else [0] * 9


def params(g, w):
    """monster_params_load 0x00532290: (rest_base, rest_span, rings, rampage months)."""
    b = behaviour(g, w.mid) if w.mid < 16 else [0] * 9
    lv = getattr(w, "aggr", 0)
    if lv == 0:
        base, span = 10000, 10000
    else:
        base, span = b[2 * (lv - 1)], b[2 * (lv - 1) + 1] - b[2 * (lv - 1)]
    return base, max(1, span), b[8], b[6]


# --- spawn -------------------------------------------------------------------------------------------------

def spawn(g, m, ev, how="spawn"):
    """monster_spawn 0x0052EEF0 + monster_spawn_and_act(m, ev, 6, 7): at the lair of its slot (0..2), else the land
    entry (sea monsters: the sea entry); the event's target categories and aggressiveness unless a guardian."""
    from . import is_guardian
    k = slot_of_monster(g, m)
    at = ev.get("at") if ev else None
    if at is None:
        if 0 <= k <= 2 and lair(g, k) is not None:
            at = lair(g, k)
        elif data()["monsters"][m]["sea"]:
            at = tuple(g.world.sea_entry or g.world.entry)
        else:
            at = tuple(g.world.entry)
    x, y = at
    guard = is_guardian(g, m)
    kw = dict(mid=m, slot=k, ev=ev["id"] if ev else -1, uclass=7 if guard else 8, spawn=(x, y), homexy=(x, y),
              act=7, timer=0, tday=g.day, scan_t=0, tb=0, tf=0, rampage=0, dest=None, aggr=0, cats=(0, 0, 0),
              mflags=0, good=f"m{m}", route=None, prog=15, ret=0)                 # good: the play client's sprite set (data/play/heroes.json)
    if not guard:                                # monster_spawn: alert 10 at the spawn tile (not for guardians)
        from .. import alerts
        alerts.raise_alert(g, alerts.MONSTER, (x, y))
    if not guard and ev is not None:
        kw["cats"] = (ev.get("b38", 0) & 0xFF, ev.get("b3a", 0) & 0xFF, ev.get("b3c", 0) & 0xFF)
        kw["aggr"] = ev.get("b3e", 0)
    w = units.spawn(g, "monster", x, y, delay=1, **kw)
    w.face = (0, 1)
    records(g)[m] = dict(fig=w.id, ev=kw["ev"])
    if m == 1:                                   # monster_spawn_and_act 0x0052F726: the Kraken's "appear" (slot 9)
        walkers.sfx(g, w, "appear")
    set_action(g, w, 6, 7)                       # monster_spawn_and_act(m, ev, 6, 7): home, then rest
    return w


def spawn_guardian(g, god, b, leader=None):
    """A friendly god's guardian (Poseidon 0x004E6260 Kraken, Hades 0x004E62D0 Cerberus, Hephaestus' help Talos,
    Ares' visit the Dragon): monster_spawn with the sanctuary, a good monster (unit type 7, no event bytes), then the
    god's entry action (sim/heroes/guardians.py). Not when its figure lives or the sanctuary's flag +0xC4 & 8 (set
    when its guardian was killed, cleared 192 days later) is set."""
    from . import guardians
    m = data()["guardian"].get(str(god), -1)
    if m < 0 or b is None or figure(g, m) is not None or b.misc.get("guardian_killed"):
        return None
    return guardians.spawn(g, m, god, b, leader)


def near(g, x, y, r, bad=True):
    """Monsters within Chebyshev r of (x, y) (for the gods: Apollo's fight, FUN_004F1B50)."""
    return [w for w in g.walkers.values() if w.role == "monster" and units.alive(w)
            and (not bad or w.uclass == 8) and max(abs(w.x - x), abs(w.y - y)) <= r]


def figure(g, m):
    """monster_record_figure 0x0052F1D0: the live figure of monster m."""
    r = records(g).get(m)
    w = g.walkers.get(r["fig"]) if r else None
    if w is not None and w.role == "monster" and w.mid == m and w.anim != "die":
        return w
    return None


def apollo_sent(g, m):
    """monster_event_update's tail: Apollo's sanctuary complete -> Apollo (god record 3) is sent against the monster
    (god_figure_spawn, action 0x4A). Gods are track 1H (sim/gods); a hook when that module is there."""
    try:
        from .. import gods
    except ImportError:
        return
    f = getattr(gods, "send_against_monster", None)
    w = figure(g, m)
    if f is not None and w is not None:
        f(g, 3, w)


# --- actions -----------------------------------------------------------------------------------------------
# figure_monster_update 0x004C8760 runs a monster's handler every tick (ours: scheduled every tick, _next); the
# header picks the route mode (route_mode), the handlers move with figure_move (rampage.move, sub-steps) and the
# tail plays the bash sound while the direction is 11 and steps the picture.

def route_mode(w):
    """figure_monster_update's header: the Kraken / Scylla (not walking land) water_mode 2 ("sea"); the Black Warrior
    (16, a land walker of monster_is_1_10_16) route mode 6; else 3, and a bad monster (unit class 8) with flag 0x100
    or in action 7: 2 (route_search over grid_military, bashing through)."""
    if w.mid in (1, 10):
        return "sea"
    if w.mid == 16:
        return 6
    if w.uclass == 8 and (w.mflags & 0x100 or w.act == 7):
        return 2
    return 3


def cur_act(w):
    """The exe's action: 5 while a melee runs (ours keeps the action under w.anim == "fight")."""
    return 5 if w.anim == "fight" else w.act


def _out_of_melee(g, w):
    """figure_set_action from action 5 (a handler going on after its walk started a fight): no figure_fight_end, the
    opponents see it gone at their next fight tick. The foe and the attack timer are kept for a return to 5 (28's
    +0x34 = 5)."""
    if w.anim == "fight":
        w.melee = (w.foe, (g.tick - w.anim_t0) % units.HIT_EVERY)
        units.leave_fight(g, w)


def set_action(g, w, a, ret=0):
    """figure_set_action 0x004ABAF0 (saved = action, +0x34 = ret, action = a) + monster_on_action_enter 0x0052F750."""
    from . import guardians
    _out_of_melee(g, w)
    if w.uclass == 7 and a in guardians.ACTS:
        return guardians.set_action(g, w, a, ret)
    if a in (0x0E, 0x0F, 0x10, 0x12, 0x13, 0x14, 0x15, 0x1D):
        return guardians.set_action(g, w, a, ret)
    if a in (10, 11, 25):
        from . import rampage
        return rampage.set_action(g, w, a, ret)
    w.saved, w.ret, w.act = cur_act(w), ret, a
    if a == 0:                                   # not a good monster: flag 0x200, (6, 7)
        w.mflags |= 0x200
        return set_action(g, w, 6, 7)
    if a == 6:                                   # 0x0052FA30
        free_route(w)
        w.tf = w.tb = 0
        w.txy = None
        w.dest = tuple(w.spawn)
    elif a == 7:                                 # monster_rest_timer_start 0x0052FA80; roam centre = dest
        if w.mflags & 0x200:
            w.mflags &= ~0x200
        else:
            base, span, _, _ = params(g, w)
            w.timer = base + hrng(g).randrange(1 << 15) % span
            w.tday = g.day
        if w.dest:
            w.homexy = tuple(w.dest)
    elif a == 8:                                 # monster_wander_dest(-1, -1)
        wander_dest(g, w, None)
    elif a == 9:                                 # 0x00531000
        free_route(w)
        o = g.walkers.get(w.tf)
        if o is not None:
            w.dest = (o.x, o.y)
    elif a == 0x18:                              # monster_action24_enter 0x00534430: home = here
        w.spawn = (w.x, w.y)
    elif a == 26:
        return _enter26(g, w)
    elif a == 27:                                # 0x00532620: +0x114 = 2 x the attack group's frames
        w.scan_t = (2 * frames(w.mid, 2)) & 0xFF
        w.anim_t0 = g.tick
    return None


def enter(g, w, a, ret=None):
    """For other modules (a hit 0x00533FB0, a god's attack, a hero's hold): figure_set_action(a, a)."""
    set_action(g, w, a, a if ret is None else ret)
    if w.id in g.walkers and not w.anim and w.act != 28:
        walkers.schedule(g, w, 1)


def free_route(w):
    """figure_route_free."""
    w.route, w.path = None, []


def fmove(g, w):
    """figure_move 0x004D1170 with the header's route mode (rampage.move); the direction (+0x11) kept: None moving,
    8 arrived, 9 blocked, 10 lost, 11 bashing."""
    from . import rampage
    if w.dest is None:                           # (older saves: a monster that never routed)
        w.dest = (w.x, w.y)
    d = rampage.move(g, w)
    w.mdir = d
    return d


def walk_then(g, w, lost):
    """figure_walk_then 0x004ABB60: blocked -> route freed; lost -> `lost` (0: state 2, removed); arrived -> +0x34."""
    d = fmove(g, w)
    if d == 9:
        free_route(w)
    elif d == 10:
        if lost == 0:
            return _gone(g, w)
        set_action(g, w, lost, 0)
    elif d == 8:
        set_action(g, w, getattr(w, "ret", 0) or 0, 0)
    return d


def _gone(g, w):
    from . import guardians
    guardians._remove(g, w)


def act(g, w):
    if w.anim == "die":
        return units.act_dying(g, w)
    a = w.act
    if w.uclass == 7 and a != 6:
        from . import guardians
        if a in guardians.ACTS:
            return guardians.act(g, w)
    if a in (10, 11, 25):
        from . import rampage
        return rampage.act(g, w)
    if getattr(w, "back5", None) is not None:    # +0x34 = 5: one tick in action 5 after the shot
        return _back_to_melee(g, w)
    if a == 28:
        return shoot(g, w)
    if a == 0:                                   # case 0: state 2
        return _gone(g, w)
    if a == 6:
        _tick6(g, w)
    elif a == 7:
        rest(g, w)
    elif a == 8:
        walk_then(g, w, 7)
    elif a == 9:
        _tick9(g, w)
    elif a in (0x0D, 0x11):
        walk_then(g, w, 0)
    elif a == 0x17:
        _tick23(g, w)
    elif a == 0x18:
        _days(g, w)
        set_action(g, w, 7, 0)
        if getattr(w, "mdir", None) in (9, 10, 11):
            free_route(w)
    elif a == 26:
        _tick26(g, w)
    elif a == 27:
        _tick27(g, w)
    else:                                        # default: (6, 7)
        set_action(g, w, 6, 7)
    return _next(g, w)


def _next(g, w):
    """Every tick (figure_monster_update); a shot (28) schedules itself; play mode: the step drawn over its sub-steps."""
    if w.id not in g.walkers or getattr(w, "gone", False) or w.anim:
        return None
    if w.act == 28:
        return None
    if w.act in (10, 11, 25):
        from . import rampage
        return rampage._next(g, w)
    walkers.schedule(g, w, 1)
    sd = w.__dict__.get("step_draw")
    if sd and sd[0] == w.arrived:
        w.step_end = sd[1]
    return None


def _days(g, w):
    """+0x36 counts down once per day the monster acts (`+0x92 != day`)."""
    if g.day != w.tday:
        w.timer -= 1
        w.tday = g.day


def _cheb(w, x, y):
    return max(abs(x - w.x), abs(y - w.y))


def _toward(w, t):
    return ((t[0] > w.x) - (t[0] < w.x), (t[1] > w.y) - (t[1] < w.y))


def rest(g, w):
    """monster_rest_update 0x005304B0 (route mode 2 for a bad monster: it bashes through what is in its way):
    a good monster without its sanctuary leaves (0x11); +0x36 < 0, or counted to 0 on a new day: the rest is over;
    the scan countdown +0x114 (a byte, kept across actions) - 1: at 0 or past 60 a scan (one main-RNG draw: the next
    in 30..59 ticks): a god engaging it or an enemy figure -> 9, a building -> 26 (flag 0x200 keeps the timer);
    else figure_move: arrived (8): a building / wall within 4 rings of here other than dest -> dest, else at the roam
    centre a wander tile around home, else the roam centre (route freed, flag 0x100 cleared); blocked / lost (9, 10):
    the building search, else a wander tile around here snapped to open land (route_tile_check; on water
    FUN_00461C20), else the roam centre."""
    from . import guardians
    if w.uclass == 7 and guardians.sanctuary(g, w) is None:
        return set_action(g, w, 0x11, 0)
    if w.timer < 0:
        return rest_over(g, w)
    if w.tday != g.day:
        w.timer -= 1
        w.tday = g.day
        if w.timer < 1:
            return rest_over(g, w)
    st = getattr(w, "scan_t", 0)
    st = 0 if st == 0 else st - 1
    w.scan_t = st
    if st == 0 or st > 60:
        w.scan_t = hrng(g).randrange(1 << 15) % 30 + 30
        if god_engages(g, w) or seek_enemy(g, w):
            w.mflags |= 0x200
            return set_action(g, w, 9, 9)
        b = seek_building(g, w)
        if b is not None:
            w.tb = b.id
            w.mflags |= 0x200
            return set_action(g, w, 26, 26)
        return None
    d = fmove(g, w)
    if d == 8:
        if _rest_building(g, w):
            return None
        if (w.x, w.y) == tuple(w.homexy):
            return wander_dest(g, w, None)
        w.dest = tuple(w.homexy)
        free_route(w)
        w.mflags &= ~0x100
        return None
    if d in (9, 10):
        if _rest_building(g, w):
            return None
        wander_dest(g, w, (w.x, w.y))
        fl = g.world.flags
        if not fl[w.y, w.x] & 4 or (g.world.road[w.y, w.x] and (w.x, w.y) in (getattr(g, "bridges", None) or ())):
            t = snap(g, *w.dest)
        else:
            from . import rampage
            sg = walkers.ship_grid(g)
            t = rampage._ring_tile(g, w.dest[0], w.dest[1],
                                   lambda a, c: sg[c, a] < 0x80 and not rampage._anyone(g, a, c))
        w.dest = t if t is not None else tuple(w.homexy)
    return None


def _rest_building(g, w):
    """LAB_005307CA: a land walker's building / wall tile within 4 rings (0x005301E0), not dest: dest = it, route
    freed, flag 0x100 cleared, facing it."""
    from . import guardians
    if not guardians.walks_land(w):
        return False
    t = near_building_tile(g, w, 4)
    if t is None or t == tuple(w.dest or ()):
        return False
    w.dest = t
    free_route(w)
    w.mflags &= ~0x100
    w.mdir = None
    w.face = _toward(w, t) or w.face
    return True


def wander_dest(g, w, around):
    """monster_wander_dest 0x00530AE0: flag 0x100 cleared, route freed, dest = around (None: home +0x2C) + two main-RNG
    draws (rng % 15 - 8 each) when that is in the play area."""
    w.mflags &= ~0x100
    free_route(w)
    w.dest = wander_tile(g, w, tuple(w.spawn) if around is None else around)


def rest_over(g, w):
    """LAB_00530560: a bad monster rampages for rampage_months x 16 days (10, 11); a good one fights the enemies of
    its kind (15, 16), else leaves (0x11)."""
    if w.uclass == 8:
        _, _, _, months = params(g, w)
        w.rampage = months << 4
        w.rday = g.day
        return set_action(g, w, 10, 11)
    from . import guardians
    if (guardians.sea_fighter(w) and guardians.sea_enemies(g)) or \
            (guardians.walks_land(w) and guardians.land_enemies(g)):
        return set_action(g, w, 0x0F, 0x10)
    return set_action(g, w, 0x11, 0)


def _tick6(g, w):
    """Case 6: the rest day count, walk_then(spd, lost 24) home; action 0 -> (7, 0); a good monster then: enemies of
    its kind -> (15, 16)."""
    _days(g, w)
    walk_then(g, w, 0x18)
    if w.act == 0:
        return set_action(g, w, 7, 0)
    if w.uclass == 7:
        from . import guardians
        if guardians.wants_fight(g, w):
            set_action(g, w, 0x0F, 0x10)


def _tick9(g, w):
    """FUN_00531050: the rest day count; +0x100 + 1; walk_then(spd, lost 6) to the target figure; target gone /
    dying / hidden -> (6, 7); action 0 -> route freed, (6, 6); ranged at Chebyshev 2..3 -> 28 (dest = its tile,
    +0x34 = the action now: 5 when this walk started a melee); arrived (8): Chebyshev < 2 -> tile contact, else
    within the aggro rings of home (Chebyshev) -> (9, 6) again, else (6, 7); blocked / lost -> target dropped, route
    freed; +0x100 past 50 at tile progress 0 or past 14 -> +0x100 = 0, route freed, dest = the target's tile;
    action 0 -> (6, 7)."""
    from ..military import contact
    _days(g, w)
    w.cnt = getattr(w, "cnt", 0) + 1
    walk_then(g, w, 6)
    o = g.walkers.get(w.tf) if w.tf else None
    if o is None or not units.alive(o) or getattr(o, "hidden", False):
        return set_action(g, w, 6, 7)
    if cur_act(w) == 0:
        free_route(w)
        return set_action(g, w, 6, 6)
    dist = _cheb(w, o.x, o.y)
    if in_range(w, o.x, o.y):
        w.dest = (o.x, o.y)
        return go_shoot(g, w, (o.x, o.y), cur_act(w))
    d = getattr(w, "mdir", None)
    if d == 8:
        if dist < 2:
            contact.figure_contact(g, w, o)
        else:
            _, _, rings_, _ = params(g, w)
            if _cheb(w, *w.spawn) < rings_:
                set_action(g, w, 9, 6)
            else:
                set_action(g, w, 6, 7)
    elif d in (9, 10):
        w.tf = 0
        free_route(w)
    elif w.cnt > 50 and getattr(w, "prog", 15) in (0, 15):
        w.cnt = 0
        free_route(w)
        w.dest = (o.x, o.y)
    if cur_act(w) == 0:
        set_action(g, w, 6, 7)


def _enter26(g, w):
    """FUN_00532520: route freed; no building / not state 1 -> (7, 7); dest = its origin (a composite's piece: its own
    origin) when plain or the piece attackable (0x005463B0) and not damaged, else (7, 7)."""
    free_route(w)
    b = g.buildings.get(w.tb) if w.tb else None
    if b is None or not target_alive(g, b):
        return set_action(g, w, 7, 7)
    if b.kind == "monument" and not _piece_ok(g, w, b):
        return set_action(g, w, 7, 7)
    w.dest = tuple(getattr(w, "txy", None) or (b.x, b.y))
    return None


def _piece_ok(g, w, b):
    from . import rampage
    t = getattr(w, "txy", None)
    for x, y, i, ok in rampage.records(g, b):
        if t is None or (x, y) == tuple(t):
            return ok
    return False


def _tick26(g, w):
    """monster_walk_to_building 0x005327A0: the rest day count; the building gone (or not on dest) -> route freed,
    (7, 7); walk_then(spd, lost 7) (mode 3 to a building tile: lost at once, set_action(7, 0)); lost: within
    Chebyshev 2 of the origin -> the attack below, else route freed, (7, 7) (a new rest timer: the first entry used
    flag 0x200); blocked -> building dropped, (7, 7); arrived -> the attack: a damaged / unattackable piece or a
    building gone -> (7, 7); dest on the origin's row or column -> 27 (smash), else ranged and Chebyshev <= 3 -> 28
    (+0x34 = the action now), Chebyshev < 3 -> 27, else building dropped, (7, 7)."""
    _days(g, w)
    b = g.buildings.get(w.tb) if w.tb else None
    if b is None or not target_alive(g, b) or int(g.world.occ[w.dest[1], w.dest[0]]) != b.id:
        free_route(w)
        return set_action(g, w, 7, 7)
    walk_then(g, w, 7)
    d = getattr(w, "mdir", None)
    bx, by = getattr(w, "txy", None) or (b.x, b.y)
    if d == 10:
        if not (w.tb and _cheb(w, bx, by) < 3):
            free_route(w)
            return set_action(g, w, 7, 7)
    elif cur_act(w) == 0:
        if not (w.tb and _cheb(w, bx, by) < 3):
            set_action(g, w, 7, 7)
            if d != 8 or tuple(w.dest) != (w.x, w.y):
                return None
    elif d != 8:
        if d == 9:
            w.tb = 0
            free_route(w)
            set_action(g, w, 7, 7)
        return _tail0(g, w)
    if w.tb:                                     # LAB_005329E3
        b = g.buildings.get(w.tb)
        if b is None or not target_alive(g, b) or (b.kind == "monument" and not _piece_ok(g, w, b)):
            return set_action(g, w, 7, 7)
        if w.dest[0] == bx or w.dest[1] == by:
            set_action(g, w, 27, 27)
            w.face = _toward(w, (bx, by)) or w.face
        else:
            dist = _cheb(w, bx, by)
            if ranged(w) and dist <= 3:
                w.dest = (bx, by)
                w.face = _toward(w, (bx, by)) or w.face
                return go_shoot(g, w, (bx, by), cur_act(w))
            if dist < 3:
                set_action(g, w, 27, 27)
                w.face = _toward(w, (bx, by)) or w.face
            else:
                w.tb = 0
                w.txy = None
                set_action(g, w, 7, 7)
    return _tail0(g, w)


def _tail0(g, w):
    if cur_act(w) == 0:
        set_action(g, w, 7, 7)


def _tick27(g, w):
    """monster_smash_building2 0x00532C70: +0x114 - 1 (not below 0); at 0 (or 0xFF) building_destroyed_by_attack on
    the building record's origin (no state re-check), then (7, 7)."""
    st = getattr(w, "scan_t", 0)
    if st:
        st -= 1
    w.scan_t = st
    if st == 0 or st == 0xFF:
        b = g.buildings.get(w.tb) if w.tb else None
        xy = getattr(w, "txy", None) or ((b.x, b.y) if b is not None else None)
        if xy is not None:
            destroy_tile(g, w, *xy)
        w.tb = 0
        w.txy = None
        set_action(g, w, 7, 7)


def _tick23(g, w):
    """FUN_00534150 (held by a hero; the duel itself is the fight engine's, hero_duel_hit: combat.py): no target -> (6, 7); the hero dying /
    gone / hidden -> route freed and figure_set_action(HERO, 6, 7) (exe bug kept: the hero gets the action, the
    monster stays); the hero in 0xE / 0x10 or beaten (flag 0x10) -> (6, 7); +0x36 + 1; FUN_004D5330 (contact with
    the neighbours' first figures; a fight: done); figure_move to him: arrived -> facing him, contact again, on his
    tile the tile contact, 4+ away -> dest = his tile, route freed, +0x36 = 0; blocked / lost -> dest = his tile,
    route freed, +0x36 = 0; moving with +0x36 >= 16 at a tile centre -> the same re-aim."""
    from . import rampage
    from ..military import contact
    h = g.walkers.get(w.tf) if w.tf else None
    if h is None and not w.tf:
        return set_action(g, w, 6, 7)
    if h is None or not units.alive(h) or getattr(h, "hidden", False):
        free_route(w)
        if h is not None and h.role == "hero":
            h.act = 6
            walkers.schedule(g, h, 1)
        return None
    if h.act in (14, 16) or getattr(h, "beaten", False):
        return set_action(g, w, 6, 7)
    w.timer += 1
    rampage.neighbours(g, w)
    if w.anim:
        return None
    d = fmove(g, w)
    if d != 8:
        if d in (9, 10) or (w.timer >= 0x10 and getattr(w, "prog", 15) in (0, 15)):
            w.dest = (h.x, h.y)
            free_route(w)
            w.timer = 0
        return None
    w.face = _toward(w, (h.x, h.y)) or w.face
    rampage.neighbours(g, w)
    if w.anim:
        return None
    if (w.x, w.y) == (h.x, h.y):
        return contact.figure_contact(g, w, h)
    if _cheb(w, h.x, h.y) >= 4:
        w.dest = (h.x, h.y)
        free_route(w)
        w.timer = 0
    return None


def destroy_tile(g, w, x, y):
    """building_destroyed_by_attack 0x004928C0 (no message in the exe; ours logs one): a building collapses into
    rubble (no fire); a wall tile becomes rubble."""
    bid = int(g.world.occ[y, x])
    b = g.buildings.get(bid)
    if b is not None:
        if b.kind == "monument":
            return piece_damage(g, w, b, x, y)
        destroy(g, w, b)
    elif g.world.flags[y, x] & 0x4000:
        from .. import effects
        effects.debris(g, x, y, 1)                # building_destroyed_by_attack, no building: dust (x, y, 1)
        g.world.flags[y, x] = int(g.world.flags[y, x]) & ~0x4000 & 0xFFFFFFFF
        g.map_version = getattr(g, "map_version", 0) + 1
        g.message(f"The {data()['monsters'][w.mid]['name']} broke through the wall at ({x},{y}).")


def piece_damage(g, w, b, x, y):
    """monument_piece_damage 0x005463D0 on the piece covering (x, y), if it is one a monster attacks (the exe's
    grid_military makes the others impassable or open, so the bash never reaches them): the class's damage method
    (vt+0x90) -- 0x00536D00 (palace pieces): the whole building to rubble; 0x00556020: damaged (+0x69, +0x9D) and
    back to stage 0 (set_stage(0, 0): materials held dropped), with the temple front / back partner (0x005351D0) the
    same; the root's +0x64 |= 0x200 (rebuilt -> the extras again at completion). Artisans rebuild it."""
    from ..systems import monuments as mon
    if b.key == "palace":                        # palace pieces (0x00536D00): the whole palace to rubble
        return destroy(g, w, b)
    if "pieces" not in b.misc:
        return
    att, col = set(data().get("piece_attack", ())), set(data().get("piece_collapse", ()))
    for p in b.misc["pieces"]:
        if p["c"] in att and (x, y) in mon.piece_tiles(b, p):
            break
    else:
        return
    if p["c"] in col:
        return destroy(g, w, b)
    hit = [p]
    if p["c"] in mon.TEMPLES or p["c"] in mon.BACKS:
        other = mon.BACKS if p["c"] in mon.TEMPLES else mon.TEMPLES
        mate = [q for q in b.misc["pieces"] if q["c"] in other]
        if mate:                                  # 0x005351D0: the partner of this front / back (ours: the nearest)
            px, py = mon.piece_xy(b, p)
            hit.append(min(mate, key=lambda q: abs(mon.piece_xy(b, q)[0] - px) + abs(mon.piece_xy(b, q)[1] - py)))
    from .. import effects
    px, py = mon.piece_xy(b, p)                   # the piece's dust, then monument_piece_damage
    effects.debris(g, px, py, mon.size(p["c"]))
    for q in hit:
        q["damaged"] = True
        mon.set_stage(b, q, 0)
    b.misc["damaged"] = True
    g.map_version = getattr(g, "map_version", 0) + 1


def destroy(g, w, b):
    """building_destroy 0x004928C0: the building collapses into rubble (no fire)."""
    from ..systems import risk
    from .. import effects
    effects.debris(g, b.x, b.y, b.size)          # collapse_debris_spawn(x, y, size, 1, 4, 0) (play mode only)
    risk.collapse(g, b)                          # (its "collapsed" line is ours; the exe posts nothing)


# --- missile attack (action 28) -----------------------------------------------------------------------------

def ranged(w):
    """monster_has_ranged 0x0052FA00: every monster but Medusa (5) and 16."""
    return bool(data()["monsters"][w.mid].get("ranged"))


def in_range(w, x, y):
    """The entry test of 9 (0x00531050), 11 (0x005318B0) and 15 (0x00533340): ranged and Chebyshev 2..3."""
    return ranged(w) and 1 < max(abs(x - w.x), abs(y - w.y)) < 4


def go_shoot(g, w, aim, ret):
    """figure_set_action(f, 28, ret) with dest = aim and the heading toward it (FUN_0058D1F0); on-enter 0x00530EA0:
    anim_frame 0, flag 0x4000 cleared (0x8000 is not). The picture tail of the same call steps the frame (+1 a tick,
    wrapping at the special group's count, 0x004C8D4B), so the handler sees frame 1 at the next tick. From a melee
    its walk started this tick (ret 5: the handler goes on after the contact, TODO 11-02 item 3) it leaves the fight
    without figure_fight_end (its foes see it at their next fight tick)."""
    _out_of_melee(g, w)
    w.face = ((aim[0] > w.x) - (aim[0] < w.x), (aim[1] > w.y) - (aim[1] < w.y))
    w.saved = cur_act(w)
    w.dest, w.ret, w.act, w.path = tuple(aim), ret, 28, []
    w.f4000 = False
    w.af, w.af_t = 1, g.tick + 1
    w.shot_t0 = g.tick
    w.shot_p = units.progress(g, w, g.tick, False)   # drawn where its step stands (ours' step = the exe's count 8)
    w.step_due = w.step_end = g.tick            # tile_progress = 15 at the end: the step under way is abandoned
    return walkers.schedule(g, w, _shoot_wait(g, w))


def _shot_frame(g, w, t):
    n = max(1, frames(w.mid, 3))
    return (w.af + t - w.af_t) % n


def _shoot_wait(g, w):
    """Ticks to the next call that does something: frame 1 (sound), the missile frame, the last frame."""
    n, F = max(1, frames(w.mid, 3)), data()["monsters"][w.mid].get("missile_frame", 0)
    for k in range(1, 2 * n + 2):
        fr = _shot_frame(g, w, g.tick + k)
        if (fr == 1 and not w.f4000) or (fr == F and not getattr(w, "f8000", False)) or fr == n - 1:
            return k
    return 1


def shoot(g, w):
    """monster_missile_attack 0x00530ED0 (action 28), every tick: at anim frame 1 (flag 0x4000 clear) the attack sound
    FUN_004D9D20 -> FUN_004DB3D0(f, 1): atk3 / atk4 by CRT rand (the MSVC stream of the seek radius), and the heading
    toward dest, flags 0x4000 set / 0x8000 cleared; else at frame 0x006409F0[monster] (flag 0x8000 clear) the missile
    FUN_004D9D70 from its tile to dest: 0x34 (unit class 8) or 0x2D (class 7), flag 0x8000; at the special group's last
    frame (monster_anim_info(m, 0x1C): 0x?A04 / 0x?C04 ...; FUN_005AF5F0) tile_progress = 15 and back to the action it
    came from (+0x34: 9, 11 or 15, its on-enter run). So a shot lasts n - 1 ticks and the next starts n ticks after.
    +0x34 = 5 (the shot began right after a contact): action 5 for one tick (_back_to_melee), then figure_fight_end
    puts back the saved action 28 and the shot's frames run on (no sound, no missile: flags kept) to the last one,
    where +0x34 = 0: on-enter 0 (6, 7) for a bad monster, state 2 for a good one."""
    n, F = max(1, frames(w.mid, 3)), data()["monsters"][w.mid].get("missile_frame", 0)
    fr = _shot_frame(g, w, g.tick)
    if fr == 1 and not w.f4000:
        v = msrand(g) * 2 >> 15                  # FUN_004DB3D0(f, 1): slot 3 + (rand * 2 >> 15)
        walkers.sfx(g, w, "atk4" if v else "atk3")
        aim = w.dest
        w.face = ((aim[0] > w.x) - (aim[0] < w.x), (aim[1] > w.y) - (aim[1] < w.y))
        w.f4000, w.f8000 = True, False
    elif fr == F and not getattr(w, "f8000", False):
        from ..military import defences
        defences.shoot(g, w, None, "enemy_arrow" if w.uclass == 8 else "arrow", aim=w.dest)
        w.f8000 = True
    if fr == n - 1:
        w.step_due = w.step_end = g.tick
        w.prog = 15                              # tile progress 15 (guardians' sub-step move, guardians.move)
        ret = getattr(w, "ret", 0) or 0
        if ret == 5:                             # set_action(5, 0): saved 28, +0x34 0; the tail steps the fight group
            w.ret, w.saved = 0, 28
            nf = max(1, frames(w.mid, 2))
            w.back5 = n if n < nf else 0         # the frame after this tick's tail (fight group count nf)
            return walkers.schedule(g, w, 1)
        set_action(g, w, ret, 0)                 # 11's on-enter 0x005315C0, 9's 0x00531000, 15's ...
        return _next(g, w)
    return walkers.schedule(g, w, _shoot_wait(g, w))


def _back_to_melee(g, w):
    """The tick after a shot that returned to action 5: figure_fight_tick 0x004D5F10 with the old opponent: still in
    a fight (state 1, action 5) -> the fight goes on (its attack timer from before the shot, + 1 now), else
    figure_fight_end: action = saved (28), route freed; the tail steps the special group: the shot's frames run on."""
    f5, w.back5 = w.back5, None
    foe, att = getattr(w, "melee", None) or (0, 0)
    w.melee = None
    o = g.walkers.get(foe)
    n = max(1, frames(w.mid, 3))
    if o is not None and units.in_fight(o):
        w.act = 28                               # its saved action when this fight ends
        w.f28 = (f5, g.tick)
        w.anim, w.foe, w.face, w.mil = "fight", o.id, _toward(w, (o.x, o.y)) or w.face, True
        w.anim_t0 = g.tick - att - 1
        w.busy_until = w.anim_t0 + units.HIT_EVERY
        w.mover = False
        units.fighting(g).add(w.id)
        return walkers.schedule(g, w, units.wake(g, w) - g.tick)
    free_route(w)
    f = f5 + 1 if f5 + 1 < n else 0              # this tick's tail, in 28 again: the frame the handler sees next
    w.af, w.af_t = f, g.tick + 1
    w.shot_t0 = g.tick - f
    return walkers.schedule(g, w, _shoot_wait(g, w))


def building_tile(b, x, y):
    """The tile of the Building record covering (x, y): a plain building's origin, a composite's piece origin."""
    if b.kind == "monument":
        from ..systems import monuments as mon
        i = mon.piece_at(b, x, y)
        if i is not None:
            return mon.piece_xy(b, i)
    return b.x, b.y


def target_alive(g, b):
    """The monster's target building still standing (state 1)."""
    return b.id in g.buildings and b.kind not in ("ruin", "road")


def fight_started(g, w):
    """Pulled into a melee (action 5) while shooting (28): the picture tail steps the fight group from here, from 0 if
    the monster moved into the fight (figure_fight_start resets the mover's anim_frame), else from its 28 frame."""
    if w.act == 28:
        w.f28 = (0 if getattr(w, "mover", False) else _shot_frame(g, w, g.tick), g.tick)


def fight_over(g, w):
    """figure_fight_end 0x004D61B0: the saved action (ours: w.act, kept under the fight) again, route freed; its
    handler runs from the next tick (9: the target fallen -> (6, 7)). Out of a fight that interrupted a shot
    (28), figure_fight_end 0x004D61B0 restores action 28 and its handler goes on from the frame the fight group's
    counter reached (+1 a tick, wrapping at the fight group's count; then the special group's count)."""
    w.mil = False
    if w.act == 28 and getattr(w, "f28", None):
        f0, t0 = w.f28
        w.f28 = None
        nf, n = max(1, frames(w.mid, 2)), max(1, frames(w.mid, 3))
        fe = (f0 + g.tick - t0) % nf             # the frame the fight tail left at this tick
        w.af, w.af_t = (fe + 1 if fe + 1 < n else 0), g.tick + 1      # this tick's tail, now in 28: wraps at n
        return walkers.schedule(g, w, _shoot_wait(g, w))
    if w.uclass == 7:
        from . import guardians
        if w.act in guardians.ACTS:              # figure_fight_end: the saved action, route freed
            return guardians.fight_over(g, w)
    free_route(w)
    return walkers.schedule(g, w, 1)


def died(g, w, by):
    """walkers_update 0x004CC8C0: a type-0x44 figure removed, not a guardian -> its event (0x004812F0)."""
    from . import events
    rec = records(g).get(w.mid)
    if rec is not None and rec["fig"] == w.id:
        rec["fig"] = 0
    if w.uclass == 7:                            # a guardian killed (figure_hit): its god's sanctuary (FUN_0052F3D0)
        from . import guardians                  # +0xC4 |= 8, +0xC8 = 0xC0 (192 days, sim/gods/sanct.py)
        b = guardians.sanctuary(g, w) or g.buildings.get(getattr(w, "sanctuary", 0))
        if b is not None and w.mid in guardians.GOD_OF:
            b.misc["guardian_killed"] = True
            b.misc["guardian_days"] = 0xC0
        return
    if w.uclass == 8 and not events.monster_killed(g, w.mid):
        n = events.monster_texts(w.mid, -1)[0]  # monster_slain_message 0x00481350: FUN_00480F20's base +6 / +7, type
        events.post(g, n + 6, n + 7, stinger="mon2")             # 0xE0, then FUN_005A1210(2) (S_mon2)


def victim(g, w, by):
    """monster_hit_victim 0x00532CF0, after figure_hit killed w (action 4): Hydra / Kraken (id < 2) devour it
    (monster_devour 0x00532340: draw colour +0x168 = 0x7C00, red, while it dies); Medusa (5) petrifies it
    (monster_petrify 0x005323A0: w removed at once, state 2; a figure 0x46 "turned to stone" at its tile with its
    sprite, fig_handler_turned_to_stone 0x004C9EF0: drawn grey 0x6318, removed after 10 000 ticks; a soldier's
    company loses the member as on any death). Others: the plain kill. Ours keeps the statues as records
    (state(g)["statues"]: x, y, role, good, face, until, and the victim's look and tick: the 0x46 figure copies the
    victim's picture +0x04), exported with /heroes.json and the frames (heroes.frame: play mode draws the statue
    grey and the devoured red, heroes.js)."""
    m = getattr(by, "mid", -1)
    if m in (0, 1):
        w.tint = 0x7C00
    elif m == 5:
        from ..export import walker_anim
        lk = walker_anim(g, w)
        st = state(g).setdefault("statues", [])
        st.append(dict(x=w.x, y=w.y, role=w.role, good=getattr(w, "good", None), face=list(w.face or (0, 1)),
                       until=g.tick + 10000, tick=g.tick, look=lk if lk and lk[0] == "fight" else None))
        w.anim_t0 = g.tick - units.DYING + 1     # gone at its next act, no dying picture
        w.hidden = True
        walkers.schedule(g, w, 1)


def statues(g):
    """The live petrified figures (0x46); expired ones dropped."""
    st = state(g).get("statues")
    if st:
        st[:] = [s for s in st if s["until"] > g.tick]
    return st or []


# --- searches ------------------------------------------------------------------------------------------------

def god_engages(g, w):
    """monster_god_engages 0x0052FBA0: an Apollo or Zeus god figure targeting it within Chebyshev 12 (gods: 1H)."""
    for o in g.walkers.values():
        if o.role == "god" and getattr(o, "god", -1) in (0, 3) and getattr(o, "target_fig", 0) == w.id \
                and max(abs(o.x - w.x), abs(o.y - w.y)) < 12:
            w.tf = o.id
            return True
    return False


_RINGS = {}


def rings(n):
    """Tiles of rings 0..n around (0, 0) in ring order (the exe's offset lists 0x005F07EA; ours: square rings,
    clockwise from north)."""
    r = _RINGS.get(n)
    if r is None:
        r = [(0, 0)]
        for k in range(1, n + 1):
            for dx in range(-k, k + 1):
                r.append((dx, -k))
            for dy in range(-k + 1, k + 1):
                r.append((k, dy))
            for dx in range(k - 1, -k - 1, -1):
                r.append((dx, k))
            for dy in range(k - 1, -k, -1):
                r.append((-k, dy))
        _RINGS[n] = r
    return r


def seek_enemy(g, w):
    """monster_seek_enemy 0x005300D0 / ring search 0x0052FD30: the first figure within aggro rings that is alive,
    not a god / monster / hero-held / stoned, and hostile to the monster's class."""
    _, _, nr, _ = params(g, w)
    from ..military import contact
    idx = contact.everyone_at(g)
    for dx, dy in rings(nr):
        for o in idx.get((w.x + dx, w.y + dy), ()):
            if o is w or not units.alive(o) or o.role in ("monster", "god", "stoned") or getattr(o, "hidden", False):
                continue
            if units.hostile(w, o):
                w.tf = o.id
                return True
    return False


def attackable(g, b):
    """nearest_attackable_building's filter for a plain building: active, the type's cooldown 0x00EF60B0 clear (ours:
    none yet), not composite (sanctuaries, palace, pyramids: their pieces, `pieces`) nor a great monument 100..114,
    not a road."""
    if b.kind in ("ruin", "road", "monument") or b.key in ("palace",):
        return False
    t = g.cat.spec(b.key).get("zeus_id")
    if t is not None and 100 <= t <= 114:
        return False
    return True


def pieces(g, b):
    """The attackable pieces of a composite (the exe's one Building record per piece, 0x004ABE80): class with
    vt+0x8C true (data/heroes.json piece_attack), started (vt+0x9C: stage > 0; the palace's classes always), not
    damaged (vt+0x98, +0x69). [(x, y) of the piece's min tile, piece index]."""
    if b.kind != "monument" or "pieces" not in b.misc:
        return []
    from ..systems import monuments as mon
    att, col = set(data().get("piece_attack", ())), set(data().get("piece_collapse", ()))
    out = []
    if b.key == "palace":                        # ours keeps no piece records for the palace (classes 3..6)
        lay = mon.layouts().get(b.key)
        return [(mon.piece_xy(b, i), i) for i, pc in enumerate(lay["pieces"]) if pc[2] in col] if lay else []
    for i, p in enumerate(b.misc["pieces"]):
        if p["c"] in att and (p["s"] > 0 or p["c"] in col) and not p.get("damaged"):
            out.append((mon.piece_xy(b, p), i))
    return out


def piece_grid(g, b):
    """grid_military over composite b's pieces (military_grid_build_rect 0x00502BA0, composite branch): a piece not
    started (vt+0x9C; the palace's never) 0, else attackable (vt+0x8C) and not damaged (vt+0x98) 1, else -1."""
    from ..systems import monuments as mon
    att, col = set(data().get("piece_attack", ())), set(data().get("piece_collapse", ()))
    out = []
    for p in b.misc.get("pieces", ()):
        if p["s"] == 0 and p["c"] not in col:
            v = 0
        elif p["c"] in att and not p.get("damaged"):
            v = 1
        else:
            v = -1
        out.append((mon.piece_tiles(b, p), v))
    return out


def candidates(g):
    """(x, y, building) of every attack target in building order: plain buildings at their origin, composites per
    attackable piece at the piece's origin."""
    for b in g.buildings.values():
        if attackable(g, b):
            yield b.x, b.y, b
        elif b.kind == "monument":
            for (x, y), _ in pieces(g, b):
                yield x, y, b


def seek_building(g, w):
    """monster_seek_building 0x00530180: bad monsters only; radius 2 + (rand()*4 >> 15) (MSVC rand);
    nearest_attackable_building 0x004ABE80: the smallest Manhattan distance to an origin (a piece's for composites).
    Returns the building; w.dest_xy = the origin attacked."""
    if w.uclass != 8:
        return None
    d = (msrand(g) * 4 >> 15) + 2
    best, bd, bxy = None, 1000, None
    for x, y, b in candidates(g):
        dd = abs(x - w.x) + abs(y - w.y)
        if dd <= d and dd < bd:
            best, bd, bxy = b, dd, (x, y)
    w.txy = bxy
    return best


def near_building_tile(g, w, n):
    """0x005301E0: the first tile within n-1 rings that holds a building or a wall (0xC000), bad monsters only."""
    if w.uclass != 8:
        return None
    occ, fl = g.world.occ, g.world.flags
    for k in range(0, n):
        for dx, dy in (rings(k)[len(rings(k - 1)):] if k else [(0, 0)]):
            x, y = w.x + dx, w.y + dy
            if 0 <= x < N and 0 <= y < N and (occ[y, x] > 0 or fl[y, x] & 0xC000):
                return (x, y)
    return None


def wander_tile(g, w, around):
    """FUN_00530AE0: around (home = the spawn tile, or where it stands after a failed route) + (rng % 15 - 8,
    rng % 15 - 8) when that is in the play area, else around."""
    r = hrng(g)
    dx = r.randrange(1 << 15) % 15 - 8
    dy = r.randrange(1 << 15) % 15 - 8
    x, y = around[0] + dx, around[1] + dy
    if g.world.inside(x, y):
        return (x, y)
    return tuple(around)


def snap(g, x, y):
    """route_tile_check 0x004D2C60: (x, y) if it is open land (land route bits, no building, terrain & 0x300203 ==
    0: no tree, rock, cliff), else the first such tile of rings 1, 2, ... (each ring: top row, bottom row, left
    column, right column, clipped to the map); None if there is none."""
    fl, occ = g.world.flags, g.world.occ

    def ok(a, b):
        f = int(fl[b, a])
        return not f & (0x300203 | 0x4 | 0x80000) and (occ[b, a] == 0 or g.world.road[b, a])
    if 0 <= x < N and 0 <= y < N and ok(x, y):
        return (x, y)
    for r in range(1, N):
        x0, x1, y0, y1 = max(x - r, 0), min(x + r, N - 1), max(y - r, 0), min(y + r, N - 1)
        if x0 > x1 or y0 > y1:
            break
        for yy in (y - r, y + r):
            if 0 <= yy < N:
                for xx in range(x0, x1 + 1):
                    if ok(xx, yy):
                        return (xx, yy)
        for xx in (x - r, x + r):
            if 0 <= xx < N:
                for yy in range(y0, y1 + 1):
                    if ok(xx, yy):
                        return (xx, yy)
    return None


def passable(g):
    """Route mode 3 / 0 land: route grid bits (0x005876F0, pathfinding.md section 2) in mask 0x11D, by its first
    matching case: off-map or water + beach (0x10004) blocked; a road (ramp road 0x100, road 0x04; a bridge is road
    over water) open, but a race-track tile (0x200 / 0x02) blocked; ramp 0x400 or garden 0x20 open (0x10); cliff
    blocked; sanctuary ground 0x10000000 blocked (0x20); a building: orchard trees (0x23 / 0x24 / 0xD9) and roadblocks
    open, any other blocked; beach, tree, rubble, marble, reeds (0x10000, 0x61001) open; terrain & 0x2DFFD66F (rock,
    water, walls, ore kinds, ...) blocked; else open (bug 386: the Thebes Hydra's lair is across bridges). A quarry
    pit (marble 0x20000 with regrowth != 0xFF: bit 0x80, outside the mask) is blocked. The decor tile objects
    (0x00666930) are a task of their own."""
    from ..systems.services import occ_version
    v = (occ_version(g), len(g.__dict__.get("quarry") or ()))
    c = getattr(g, "_monster_ok", None)
    if c is None or c[0] != v:
        import numpy as np
        from ..systems import index
        wd = g.world
        f = wd.flags.astype(np.int64) & ~0x40     # ours' road is World.road (stale 0x40 bits of cleared map roads)
        ok = np.zeros((N, N), bool)
        done = np.zeros((N, N), bool)

        def put(mask, val):
            m = mask & ~done
            ok[m] = val if isinstance(val, bool) else val[m]
            done[m] = True
        put(((f & 0x80000) != 0) | ((f & 0x10004) == 0x10004), False)
        track = np.zeros((N, N), bool)
        for b in index.of(g, "hippodrome"):
            track |= wd.occ == b.id
        put(wd.road & track, False)
        put(wd.road, True)
        put((f & 0x420) != 0, True)
        put((f & 0x200) != 0, False)
        pit = np.zeros((N, N), bool)              # marble (0x20000) with regrowth != 0xFF (a quarry pit): bit 0x80
        for (x, y), dep in (g.__dict__.get("quarry") or {}).items():
            pit[y, x] = dep != 255
        put(pit & ((f & 0x20000) != 0), False)
        put((f & 0x10000000) != 0, False)
        bld = wd.occ != 0
        if bld.any():
            lut = np.zeros(int(wd.occ.max()) + 1, bool)
            for b in g.buildings.values():
                if b.id < len(lut) and (b.kind in ("orchard", "roadblock") or b.key == "gardens"):
                    lut[b.id] = True
            put(bld, lut[wd.occ])
        dry = (f & 0x4) == 0
        put(dry & ((f & 0x71001) != 0), True)
        put((f & 0x2DFFD66F) != 0, False)
        put(np.ones((N, N), bool), True)
        c = g._monster_ok = (v, ok.ravel().tolist())
    return c[1]


def route2(g, start, goal):
    """Route mode 2 (figure_find_route 0x004D8220 case 2): route_search 0x00502EE0 over grid_military, then
    route_trace(8) (sim/military/routes.py). Oracle 1I-roam: the sandbox Maenads walk 66-tile detours out of their
    gully and back."""
    from ..military import routes
    return routes.route2(g, start, goal)


def frames(m, grp):
    """Frames of animation group grp (0 walk, 1 die, 2 attack, 3 special) of monster m (data/heroes.json)."""
    f = data()["monsters"][m].get("frames") if 0 <= m < 16 else None
    return f[grp] if f else 16


def _tiles(b):
    w = b.misc.get("w", b.size) or 1
    h = b.misc.get("h", b.size) or 1
    return [(b.x + dx, b.y + dy) for dy in range(h) for dx in range(w)]


def day(g):
    pass


# --- reports -------------------------------------------------------------------------------------------------

ACT = {7: "resting at its lair", 26: "going for a building", 27: "smashing a building", 9: "attacking",
       6: "going home", 10: "rampaging", 11: "rampaging", 0x17: "fighting a hero", 0x11: "leaving",
       0x0E: "patrolling", 0x0F: "chasing an enemy", 0x10: "attacking", 0x12: "following its god",
       0x13: "hunting a wolf", 0x1D: "wandering", 28: "shooting", 0: "leaving"}


def describe(g, w):
    nm = data()["monsters"][w.mid]["name"]
    s = f"{nm} at ({w.x},{w.y}) lair {tuple(w.spawn)}: {ACT.get(w.act, w.act)}"
    if w.anim == "die":
        s += " (dying)"
    elif w.anim == "fight":
        s += " (fighting)"
    return s + f", rest {w.timer} days, damage {getattr(w, 'dmg', 0)}"


def export(g, w):
    return dict(id=w.id, mid=w.mid, name=data()["monsters"][w.mid]["name"], x=w.x, y=w.y, act=w.act,
                lair=list(w.spawn), timer=w.timer)


def look(g, w):
    """Play mode: [kind, t0, end, face...] for a smashing / dueling / idle monster; walking = None."""
    f = w.face or (0, 1)
    if w.anim:
        return None
    if w.act == 28:                              # the special group (0x?A04..), +1 a tick from 1 at the entry's tick
        n = max(1, frames(w.mid, 3))
        return ["work", w.shot_t0, w.shot_t0 + n, f[0], f[1], 0, 0, w.shot_t0, "special", False, None,
                list(getattr(w, "shot_p", None) or [15, 0, 0])]
    # mover False: no fight-start sound (the smash of 27 is silent; 25 and the bash play via walkers.sfx "bash")
    if w.act == 27:                              # 2 x the attack group's frames from the entry (+0x114)
        t0 = getattr(w, "anim_t0", g.tick)
        return ["fight", t0, t0 + 2 * frames(w.mid, 2), f[0], f[1], 0, 0, t0, "", False]
    if w.act == 25:                              # monster_smash_building: the attack group, 2 x its frames
        t0 = getattr(w, "anim_t0", g.tick)
        return ["fight", t0, t0 + 2 * frames(w.mid, 2), f[0], f[1], 0, 0, t0, "", False]
    if w.act == 0x10:                            # monster_anim_info(m, 0x10): the attack group, one tick (16 -> 15)
        t0 = getattr(w, "a16", g.tick)
        return ["fight", t0, t0 + 1, f[0], f[1], 0, 0, t0, "", False]
    if getattr(w, "bashing", 0) and w.bashing >= g.tick - 1:                         # direction 11: the
        t0 = getattr(w, "bash_t0", None) or w.bashing                               # fight group (tail: action 5)
        return ["fight", t0, g.tick + 2, f[0], f[1], 0, 0, t0, "", False]
    return None
