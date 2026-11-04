"""Friendly gods fighting (docs/logic/religion.md "Gods fighting"): the behaviour objects 0x00EF5DD0 (actions 0x4A/0x4B/
0x50: a god shoots at one target from where it stands and drives it off) and 0x00EF5DD4 (0x51..0x54: a god hunts
invaders or a monster across the map), the god-vs-god encounter (god_encounter_check 0x004EE2B0, duel 0x3C).

Who sends them:
  Athena   athena_month_defend 0x004E6340 (monthly, sanctuary built): an invasion on (FUN_004AC7C0(0): enemy units
           alive besides transports / warships) -> Athena out of her sanctuary (or, on the map, set_action(0x51)) at the
           nearest invader (FUN_004AC570(fig, 0): the enemy-company member nearest her, Chebyshev, not on a building)
  Apollo   apollo_month_fight_monster 0x004E6440 (monthly, sanctuary built): not on the map -> the nearest bad monster
           (FUN_004F1B50(sanctuary road access): class 8, any distance) -> 0x51 with flag 0x400 (keep this target);
           on the map (not in 10, 0x51..0x54, 0x0B, 4) -> the bad monster nearest him (FUN_004F1A60): a monster ->
           0x4A/0x4B, else 0x51
  visits   god_walk_interrupt 0x004EBA10 (actions 8 and 9 of a friendly god, class 9): Apollo (active sanctuary): the
           nearest bad monster -> 0x51 (flag 0x400); Athena or Hera (active): an invasion on -> 0x51
  Artemis  the wolf chase 0x0056AF80 (sim/military wolves): a wolf at its prey -> Artemis (sanctuary complete) out at
           her sanctuary (if absent) targets the wolf, 0x4A/0x4B (not again while in 0x4A/0x4B or with +0x34 == 0x4B)
  events   event_god_attack's defender (Zeus / Aphrodite / Hera): 0x4A/0x4B at the attacking god
  monsters monster_event_update's tail (sim/heroes apollo_sent): Apollo (sanctuary complete) at the new monster

0x4A (0x004EA8F0): set_action(10, 0x4B) (the appear animation), timer = frames(4), flags 0x2000 on both.
0x4B (0x004EAA60): timer -1 a tick; the target turns on the god (a god -> 0x44 at it, a monster -> 9); a bolt 0x2D at
     the attack frame shot_frame of each cycle; at timer < 1: target gone -> 0x0B, else 0x50 (timer = frames(2)).
0x50 (0x004EAD00): a bolt each cycle; after 5 cycles of frames(2) the target falls (action 4: a god vanishes, a
     monster / wolf dies), FUN_004E3310(god, target) (the fight message 0x3E9), the god vanishes (0x0B).
0x51 enter (0x004EAF90): flag 0x400 -> keep the target, else FUN_004AC570(fig, 0); none -> 0x0B. dest = 4 steps ahead
     on the target's route (FUN_004E2800) or its tile, snapped by free_tile_near(4) (FUN_004C43C0); farther than 5
     from the god: vanish (frames(1)) and reappear there (frames(3)) (flags 4/8); then walk.
0x51 tick (0x004EB180): walk; target gone -> 0x51 again; arrived: within 6 of the target -> 0x52, else 0x53; lost ->
     vanish and reappear at dest; every 50 ticks at a tile centre: target within 6 -> dest = its tile, else 0x51 again.
0x52 (0x004EB4A0 / 0x004EB5F0): target gone -> 0x51; farther than 5 -> 0x53; else stand, face it, and per cycle of
     frames(Athena 4, else 2) a bolt at shot_frame, then re-enter 0x52.
0x53 (0x004EB740 / 0x004EB7A0): chase the target (dest = its tile; re-aimed every 50 ticks); within 16 while walking
     or arrived -> 0x52; lost -> placed on the target's tile, appear, 0x53.
0x54 (0x004EB970 / 0x004EB9A0): walk to the creation tile, then 0x0B and the god record's +0x1C = 0xC0.
Animations: 0x0A, 0x4B, 0x50, 0x51 (vanish / appear) and 0x52 step at rate 100 (one frame per frame_ticks ticks,
attack.tpf; bug 393); the duel 0x3C at rate 0 (one a tick). The 0x0A / 0x4B / 0x50 timers count ticks.
"""
from . import T, rec, sanctuary, built, active, rng, NAMES
from .month import log

LEAVE_TASKS = ("leave", "home")


def _W():
    from ..systems import walkers
    return walkers


def frames(i, k):
    from .attack import frames as f
    return f(i, k)


def tpf(i, k):
    from .attack import tpf as f
    return f(i, k)


def dur(i, k):
    """A rate-100 look's length (attack.dur, bug 393)."""
    from .attack import dur as d
    return d(i, k)


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def valid(t):
    """Target alive (state 1, action != 4), visible; a god not leaving."""
    if t is None or t.anim == "die" or t.__dict__.get("hidden"):
        return False
    return not (t.role == "god" and t.task == "leave")


# --- targets -----------------------------------------------------------------------------------------------------

def invasion_on(g):
    """FUN_004AC7C0(0): enemy units alive besides transports and warships."""
    return any(w.role in ("enemy_infantry", "enemy_archer", "enemy_cavalry") and w.anim != "die"
               for w in g.walkers.values())


def nearest_invader(g, x, y):
    """FUN_004AC570(fig, 0): over the enemy companies (state 1, not the city's), their member figures alive, not on a
    building tile; the nearest by Chebyshev distance (the first wins ties)."""
    occ = g.world.occ
    best, bd = None, None
    for w in sorted(g.walkers.values(), key=lambda w: (getattr(w, "company", 0), getattr(w, "slot", 0), w.id)):
        if w.role not in ("enemy_infantry", "enemy_archer", "enemy_cavalry") or w.anim == "die":
            continue
        if int(occ[w.y, w.x]) > 0:               # (hidden members count: the exe does not test +0x65)
            continue
        d = cheb((w.x, w.y), (x, y))
        if bd is None or d < bd:
            best, bd = w, d
    return best


def nearest_monster(g, x, y):
    """FUN_004F1B50 / FUN_004F1A60: the bad monster (class 8) nearest (x, y), any distance."""
    best, bd = None, 9999
    for w in g.walkers.values():
        if w.role != "monster" or w.anim == "die" or w.__dict__.get("uclass", 8) != 8:
            continue
        d = cheb((w.x, w.y), (x, y))
        if d < bd:
            best, bd = w, d
    return best


# --- sending a god -------------------------------------------------------------------------------------------------

def _out(g, i):
    """god_figure_spawn at the sanctuary when the god is not on the map (FUN_0053FBE0: its road entry)."""
    from . import figures
    return figures.out_of_sanctuary(g, i)


def hunt(g, i, target, keep=False, w=None):
    """Action 0x51 for god i at target (keep = flag 0x400: hunt this target; else the nearest invader)."""
    from . import figures
    w = w or figures.figure(g, i)
    fresh = w is None
    if fresh:
        w = _out(g, i)
        if w is None:
            return None
    w.saved_task = None if fresh else w.task
    w.target_fig = target.id if target is not None else 0
    if target is not None:
        target.tagged = True                   # figure_set_target 0x004E3280: flags |= 2 (sim/military nearest_enemy)
    w.keep = keep
    w.ph = "pick"
    w.path = []
    if fresh:
        w.next_task = "hunt"
    else:
        w.task = "hunt"
        _W().schedule(g, w, 1)
    log(g, f"{NAMES[i]} goes to fight the {target.role if target else 'invaders'}")
    return w


def defend(g, i, target, w=None):
    """Actions 0x4A/0x4B for god i at target (a god, monster or wolf): appear, then shoot."""
    from . import figures
    w = w or figures.figure(g, i)
    fresh = w is None
    if fresh:
        w = _out(g, i)
        if w is None:
            return None
    w.target_fig = target.id
    target.tagged = True                       # figure_set_target: flags |= 2
    w.task = "appear"
    w.next_task = "defend"
    w.anim_t0 = g.tick
    w.path = []
    w.anim_t0 = g.tick - 10                    # 0x0A with timer >= 10: drawn at once
    w.cyc, w.dstage = 0, None
    w.timer = frames(i, 4) + dur(i, 3)         # 0x4A: timer = frames(4), +1 a tick in 0x0A, -1 a tick in 0x4B
    w.flag2000 = True
    target.flag2000 = True
    w.face = (target.x - w.x, target.y - w.y)
    W = _W()
    W.schedule(g, w, dur(i, 3))
    log(g, f"{NAMES[i]} comes to fight {_name(target)}")
    return w


def _name(t):
    if t.role == "god":
        return NAMES[t.god]
    if t.role == "monster":
        from ..heroes import data
        try:
            return "the " + data()["monsters"][t.mid]["name"]
        except Exception:                        # noqa: BLE001
            return "the monster"
    return "the " + t.role.replace("_", " ")


def can_fight(w):
    """god_can_fight 0x004EE270: no flag 0x2010, not in 0x3C..0x3E, 10, 0x0B, 0x49."""
    if w.__dict__.get("flag2000") or w.__dict__.get("no_bless") and w.task == "home":
        return False
    if w.task in ("appear", "leave", "duel", "home"):
        return False
    if w.task == "attack" and getattr(w, "phase", "") == "leave":
        return False
    return True


def athena_month(g):
    """athena_month_defend 0x004E6340: an invasion on -> Athena (not on the map) out at her sanctuary, action 10 -> 0x51
    (the target FUN_004AC570 is set, but without flag 0x400 the 0x51 entry picks the nearest invader again); on the
    map: set_action(0x51)."""
    from . import figures
    if not invasion_on(g):
        return None
    w = figures.figure(g, 8)
    if w is None and sanctuary(g, 8) is None:
        return None
    return hunt(g, 8, None, w=w)


def apollo_month(g):
    """apollo_month_fight_monster 0x004E6440."""
    from . import figures
    b = sanctuary(g, 3)
    if b is None:
        return
    w = figures.figure(g, 3)
    if w is None:
        from .figures import _sanct_tile
        t0 = _sanct_tile(g, b)
        m = nearest_monster(g, *(t0 or (b.x, b.y)))
        if m is None:
            return
        return hunt(g, 3, m, keep=True)
    m = nearest_monster(g, w.x, w.y)
    if m is None or w.task in ("appear", "hunt", "leave") or w.task == "defend":
        return
    if m.role == "monster":
        return defend(g, 3, m, w=w)
    return hunt(g, 3, m, keep=True, w=w)


def send_against_monster(g, i, m):
    """sim/heroes monster_event_update's tail: Apollo (sanctuary complete) is sent against the new monster
    (god_figure_spawn, action 0x4A)."""
    from ..systems import monuments
    b = sanctuary(g, i)
    if b is None or not monuments.complete(b):
        return None
    from . import figures
    w = figures.figure(g, i)
    if w is not None and w.task in ("defend",):
        return None
    return defend(g, i, m, w=w)


def summon_artemis(g, wolf):
    """The wolf chase 0x0056AF80: Artemis (sanctuary complete) at her sanctuary targets the wolf (0x4A/0x4B), unless
    she is already in 0x4A/0x4B (or about to be)."""
    from ..systems import monuments
    from . import figures, on
    if not on(g):
        return None
    b = sanctuary(g, 4)
    if b is None or not monuments.complete(b):
        return None
    w = figures.figure(g, 4)
    if w is not None and (w.task == "defend" or w.task == "appear" and getattr(w, "next_task", "") == "defend"):
        return None
    return defend(g, 4, wolf, w=w)


def walk_interrupt(g, w):
    """god_walk_interrupt 0x004EBA10 (a friendly god in actions 8 / 9): True when it left the walk to fight."""
    i = w.god
    if w.__dict__.get("uclass", 9) != 9 or i not in (3, 8, 12):
        return False
    if sanctuary(g, i) is None or not active(g, i):
        return False
    if i == 3:
        m = nearest_monster(g, w.x, w.y)
        if m is None:
            return False
        hunt(g, 3, m, keep=True, w=w)
        return True
    if not invasion_on(g):
        return False
    hunt(g, i, None, w=w)
    return True


# --- the handlers ---------------------------------------------------------------------------------------------------

def _tile_ticks(g, w):
    from .figures import tile_ticks
    return tile_ticks(g, w)


def _step(g, w, nxt):
    _W().step_to(g, w, nxt)


def _path(g, w, goal):
    W = _W()
    if (w.x, w.y) == tuple(goal):
        return []
    return W.land_path(g, (w.x, w.y), {tuple(goal)}, max_dist=W.ROUTE_MAX) or None


def _intercept(g, w, t):
    """FUN_004C43C0(fig, target, 4): 4 steps ahead on the target's route (FUN_004E2800) or its tile; a route tile
    farther than 1 from the target is the dest as it is, else free_tile_near(tile, 4)."""
    p = getattr(t, "path", None) or []
    if p:
        x, y = p[min(3, len(p) - 1)]
        if (x - t.x) ** 2 + (y - t.y) ** 2 > 1:
            return (x, y)
    else:
        x, y = t.x, t.y
    return free_tile_near(g, x, y, 4)


def free_tile_near(g, x, y, r0):
    """free_tile_near 0x004C41B0: the rings r0+1 .. 12 around (x, y) (ring table 0x005F07EA: ring k = radius k+1;
    ours: square rings in sim/heroes' order), the first tile in the play area with no building, no figure and clear
    or wooded land, scored by the map edge (map_near_play_edge within 3 -> 2, 7 -> 3, 12 -> 4, else 5; ours: the
    four tiles d away along the axes); the best (first 5 at once), else (x, y) itself."""
    from ..heroes.monsters import rings
    W = _W()
    world, n = g.world, 228
    ok = W.walkable(g)
    occ = world.occ
    figs = {(o.x, o.y) for o in g.walkers.values() if not o.__dict__.get("hidden")}

    def near_edge(xx, yy, d):
        return any(not world.inside(a, b) for a, b in ((xx + d, yy), (xx - d, yy), (xx, yy + d), (xx, yy - d)))
    best, bs = (x, y), -1
    for dx, dy in rings(12):
        if max(abs(dx), abs(dy)) <= r0:
            continue
        xx, yy = x + dx, y + dy
        if not (0 <= xx < n and 0 <= yy < n) or not world.inside(xx, yy) or int(occ[yy, xx]) or not ok[yy * n + xx]:
            continue
        if (xx, yy) in figs:
            continue
        sc = 2 if near_edge(xx, yy, 3) else 3 if near_edge(xx, yy, 7) else 4 if near_edge(xx, yy, 12) else 5
        if sc > bs:
            best, bs = (xx, yy), sc
            if sc == 5:
                break
    return best


def _teleport(g, w, dest, then):
    """Flags 4 / 8: the vanish animation (frames(1); Hermes none), placed on dest, the appear animation (frames(3))."""
    w.ph = "tele"
    w.tele = (tuple(dest), then)
    w.anim_t0, w.anim_kind = g.tick, "vanish"
    _W().schedule(g, w, dur(w.god, 1) if w.god != 7 else 1)


def act(g, w):
    if w.task == "hunt":
        return _hunt(g, w)
    if w.task == "defend":
        return _defend(g, w)
    return None


def _target(g, w):
    t = g.walkers.get(getattr(w, "target_fig", 0) or 0)
    return t if valid(t) else None


def _hunt(g, w):
    W = _W()
    ph = w.ph
    if ph == "tele":
        (dest, then) = w.tele
        if w.anim_kind == "vanish":
            w.prev, (w.x, w.y) = None, dest
            w.arrived = g.tick
            W.listed(g, w)
            w.anim_t0, w.anim_kind = g.tick, "appear"
            return W.schedule(g, w, dur(w.god, 3) if w.god != 7 else 1)
        w.anim_kind = ""
        w.ph = then
        if then == "walk":
            w.path = []
            return _arrived(g, w)
        return W.schedule(g, w, 1)
    if ph == "pick":                              # enter 0x51
        t = _target(g, w) if w.keep else None
        w.keep = False
        if t is None:
            t = nearest_invader(g, w.x, w.y)
        if t is not None and t.__dict__.get("hidden"):
            return W.schedule(g, w, 10)          # ours: wait while the nearest invader is still hidden at its entry
        if t is None:
            from .figures import _leave
            log(g, f"{NAMES[w.god]} has no one left to fight")
            return _leave(g, w)
        w.target_fig = t.id
        t.tagged = True                          # figure_set_target (0x004EAF90): flags |= 2
        dest = _intercept(g, w, t)
        w.dest = dest
        w.walk_t = 0
        if cheb((w.x, w.y), dest) > 5:
            return _teleport(g, w, dest, "walk")
        w.ph = "walk"
        w.path = _path(g, w, dest) or []
        return W.schedule(g, w, 1)
    t = _target(g, w)
    if ph == "walk":                              # tick 0x51
        if t is None:
            w.ph = "pick"
            return W.schedule(g, w, 1)
        if w.path:
            nxt = w.path.pop(0)
            _step(g, w, nxt)
            w.walk_t += _tile_ticks(g, w)
            if w.walk_t > 50:                     # every 50 ticks at a tile centre
                w.walk_t = 0
                if cheb((w.x, w.y), (t.x, t.y)) < 6:
                    w.dest = (t.x, t.y)
                    w.path = _path(g, w, w.dest) or []
                else:
                    w.ph = "pick"
                    w.keep = True
            return W.schedule(g, w, _tile_ticks(g, w))
        return _arrived(g, w)
    if ph == "shoot":                             # 0x52
        if t is None:
            w.ph = "pick"
            return W.schedule(g, w, 1)
        if cheb((w.x, w.y), (t.x, t.y)) > 5:
            w.ph = "chase"
            w.walk_t = 0
            w.path = _path(g, w, (t.x, t.y)) or []
            w.anim_kind = ""
            return W.schedule(g, w, 1)
        k = 4 if w.god == 8 else 2
        return _shoot_cycle(g, w, t, frames(w.god, k), tpf(w.god, k))
    if ph == "chase":                             # 0x53
        if t is None:
            w.ph = "pick"
            return W.schedule(g, w, 1)
        if cheb((w.x, w.y), (t.x, t.y)) < 16 and w.path or not w.path and (w.x, w.y) == (t.x, t.y):
            w.ph = "shoot"
            return W.schedule(g, w, 1)
        if not w.path:
            w.path = _path(g, w, (t.x, t.y))
            if w.path is None:                    # lost: placed on the target's tile, appear, 0x53
                w.prev, (w.x, w.y) = None, (t.x, t.y)
                W.listed(g, w)
                w.anim_t0, w.anim_kind = g.tick, "appear"
                w.ph = "tele"
                w.tele = ((t.x, t.y), "chase")
                w.path = []
                return W.schedule(g, w, dur(w.god, 3))
        nxt = w.path.pop(0)
        _step(g, w, nxt)
        w.walk_t += _tile_ticks(g, w)
        if w.walk_t >= 50:
            w.walk_t = 0
            w.path = []
        return W.schedule(g, w, _tile_ticks(g, w))
    if ph == "home":                              # 0x54
        if w.path:
            _step(g, w, w.path.pop(0))
            return W.schedule(g, w, _tile_ticks(g, w))
        rec(g, w.god)["timer_1c"] = 0xC0
        from .figures import _leave
        return _leave(g, w)
    w.ph = "pick"
    return W.schedule(g, w, 1)


def _arrived(g, w):
    W = _W()
    t = _target(g, w)
    if t is None:
        w.ph = "pick"
        return W.schedule(g, w, 1)
    if cheb((w.x, w.y), (t.x, t.y)) < 6:
        w.ph = "shoot"
    else:
        w.ph = "chase"
        w.walk_t = 0
        w.path = _path(g, w, (t.x, t.y)) or []
    return W.schedule(g, w, 1)


def _shoot_cycle(g, w, t, n, p):
    """One animation cycle of n frames, p ticks each (rate 100): face the target at frame 0, a bolt at shot_frame
    (0x0063A8C4[god])."""
    from . import bolts
    W = _W()
    sf = min(T()["shot_frame"][w.god], n - 1) * p
    end = n * p - 1
    if getattr(w, "cyc_t0", None) is None or w.anim_kind != "attack":
        w.cyc_t0, w.anim_t0, w.anim_kind, w.shot = g.tick, g.tick, "attack", False
        w.face = (t.x - w.x, t.y - w.y)
    k = g.tick - w.cyc_t0
    if not w.shot and k >= sf:
        w.shot = True
        bolts.shoot(g, w, (t.x, t.y), 0x2D)
        return W.schedule(g, w, max(1, end - k))
    if k >= end:
        w.cyc_t0 = None
        w.anim_kind = ""
        return W.schedule(g, w, 1)
    return W.schedule(g, w, max(1, sf - k))


def _defend(g, w):
    """0x4B then 0x50."""
    W = _W()
    from . import bolts
    t = g.walkers.get(getattr(w, "target_fig", 0) or 0)
    alive = t is not None and t.anim != "die" and not (t.role == "god" and t.task == "leave")
    if not getattr(w, "dstage", None):
        w.dstage, w.dt0, w.cyc = "4B", g.tick, 0
        w.anim_t0, w.anim_kind = g.tick, "attack"
        if alive:
            _turn_on(g, t, w)
    k = 4 if w.god == 8 else 2                    # Athena: the cast group (the tail's LAB_004c82d3)
    n, p = frames(w.god, k), tpf(w.god, k)         # rate 100: frame = el // p in a cycle of n * p ticks (bug 393)
    sf = min(T()["shot_frame"][w.god], n - 1)
    if w.dstage == "4B":
        el = g.tick - w.dt0
        if alive and el % (n * p) == sf * p:
            bolts.shoot(g, w, (t.x, t.y), 0x2D)
        if el < w.timer:
            return W.schedule(g, w, 1)
        if not alive:
            return _done(g, w, None)
        w.dstage, w.dt0, w.cyc = "50", g.tick, 0
        w.face = (t.x - w.x, t.y - w.y)
        _turn_on(g, t, w)
        return W.schedule(g, w, 1)
    if not alive:                                 # 0x50: the target gone -> 0x0B
        return _done(g, w, None)
    if t.role == "god" and t.god in (0, 1, 7):     # trade_block_set: Zeus both, Poseidon sea, Hermes land -> 0
        from . import state
        tb = state(g)["trade_block"]
        for k in {0: (0, 1), 1: (0,), 7: (1,)}[t.god]:
            tb[k] = 0
    el = g.tick - w.dt0
    if el % (n * p) == sf * p:
        bolts.shoot(g, w, (t.x, t.y), 0x2D)
    # 0x50: 5 rounds of timer = frames(2) ticks, then (FUN_004EAD00) on until anim_frame >= frames(2) - 1
    if el < 5 * frames(w.god, 2) or (el % (n * p)) // p < n - 1:
        return W.schedule(g, w, 1)
    return _done(g, w, t)


def _turn_on(g, t, w):
    """0x4B: the target turns to fight the god (a god -> 0x44 at it, a monster -> 9)."""
    if getattr(t, "foe_god", 0) == w.id:
        return
    t.foe_god = w.id
    if t.role == "monster":
        try:
            from ..heroes import monsters
            if t.anim != "fight":
                t.tf = w.id
                t.mflags |= 0x200
                monsters.enter(g, t, 9)
        except Exception:                         # noqa: BLE001  (sim/heroes absent)
            pass
    elif t.role == "god" and t.task == "attack":
        from . import attack
        attack.turn_on(g, t, w)


def _done(g, w, t):
    """0x50 end: FUN_004E3310(god, target) (the fight message), target action 4, the god 0x0B."""
    from .figures import _leave
    w.flag2000 = False
    w.anim_kind = ""
    w.dstage = None
    if t is not None:
        t.flag2000 = False
        log(g, f"{NAMES[w.god]} defeats {_name(t)}")
        if t.role == "god":
            from . import attack
            attack.driven_off(g, t)
        else:
            from ..military import units
            units.kill(g, t, w)
    return _leave(g, w)


def look(g, w):
    """Play mode blocks while hunting / defending."""
    f = getattr(w, "face", None) or (0, 1)
    f = ((f[0] > 0) - (f[0] < 0), (f[1] > 0) - (f[1] < 0))
    k = getattr(w, "anim_kind", "")
    i = w.god
    if k == "vanish":                             # 0x51 flag 4: rate 100
        return ["work", w.anim_t0, w.anim_t0 + dur(i, 1), f[0], f[1], 0, 0, 0, "vanish_gated", False]
    if k == "appear":
        return ["work", w.anim_t0, w.anim_t0 + dur(i, 3), f[0], f[1], 0, 0, 0, "appear", False]
    if k == "attack" and not w.path:
        if w.task == "duel":                      # 0x3C: the attack group at rate 0 (one frame a tick)
            return ["work", w.anim_t0, w.anim_t0 + frames(i, 2), f[0], f[1], 0, 0, 0, "duel", False]
        blk = "cast" if i == 8 else "attack"      # Athena's 0x4B / 0x50 / 0x52: her cast group
        return ["work", w.anim_t0, w.anim_t0 + dur(i, 4 if blk == "cast" else 2), f[0], f[1], 0, 0, 0, blk, False]
    return None


# --- god vs god -------------------------------------------------------------------------------------------------------

def encounter_check(g, w):
    """god_encounter_check 0x004EE2B0 (each animation cycle of a god that can fight): another visible god figure of the
    other side (one record unfriendly == 1, the other 0) within Chebyshev 15 -- no limit for Zeus with an active
    sanctuary, Aphrodite (active) against Ares / Hephaestus / Hermes / Dionysus, Hera (active) against Zeus -- that can
    fight too: both go into the duel (0x3C) at each other."""
    if not can_fight(w):
        return False
    i = w.god
    special = False
    if w.__dict__.get("uclass", 9) == 9 and i in (0, 6, 12) and sanctuary(g, i) is not None and active(g, i):
        special = True
    from . import figures
    for j in range(14):
        o = figures.figure(g, j)
        if o is None or o is w or o.__dict__.get("hidden") or o.anim == "die":
            continue
        unlimited = special and (i == 0 or i == 6 and j in (5, 9, 7, 10) or i == 12 and j == 0)
        if not unlimited and cheb((w.x, w.y), (o.x, o.y)) > 15:
            continue
        ri, rj = rec(g, i)["unfriendly"], rec(g, j)["unfriendly"]
        if not ((ri == 1 and rj == 0) or (ri == 0 and rj == 1)) or not can_fight(o):
            continue
        for a, b in ((w, o), (o, w)):
            a.duel_saved = (a.task, getattr(a, "phase", None))
            a.task, a.foe_id, a.shots, a.path, a.anim_kind = "duel", b.id, 0, [], ""
            _W().schedule(g, a, 1)
        log(g, f"{NAMES[i]} and {NAMES[j]} meet and fight")
        return True
    return False


def duel(g, w):
    """0x3C (0x004EE570 / 0x004EE850): walk to within 8 tiles of the other god, 5 bolts (0x34 if hostile, else 0x2D, one
    per attack cycle), then, when the last bolt is gone, god_fight_wins 0x004EE5B0: the loser 0x3D (a friendly god walks
    back to its sanctuary without blessing and vanishes; a hostile one leaves, 0x49), the winner 0x3E (resumes)."""
    from . import bolts, figures
    W = _W()
    foe = g.walkers.get(getattr(w, "foe_id", 0) or 0)
    if foe is None or foe.role != "god" or foe.task in LEAVE_TASKS or foe.task == "attack" and foe.phase == "leave":
        return _resume(g, w)
    if cheb((w.x, w.y), (foe.x, foe.y)) > 8:
        if not w.path:
            w.path = _path(g, w, (foe.x, foe.y)) or []
            if not w.path:
                return _resume(g, w)
        _step(g, w, w.path.pop(0))
        return W.schedule(g, w, _tile_ticks(g, w))
    w.path = []
    n = frames(w.god, 2)
    sf = min(T()["shot_frame"][w.god], n - 1)
    if w.shots < 5:
        if w.anim_kind != "attack":
            w.anim_kind, w.anim_t0, w.face = "attack", g.tick, (foe.x - w.x, foe.y - w.y)
            return W.schedule(g, w, sf)
        if g.tick - w.anim_t0 == sf:
            bolts.shoot(g, w, (foe.x, foe.y), 0x34 if w.__dict__.get("uclass", 9) == 10 else 0x2D)
            return W.schedule(g, w, n - 1 - sf)
        w.shots += 1
        w.anim_kind = ""
        return W.schedule(g, w, 1)
    if bolts.alive(g, w):
        return W.schedule(g, w, 2)
    if foe.task != "duel":
        return _resume(g, w)
    from .figures import fight_wins
    win = fight_wins(g, w.god, foe.god)
    loser, winner = (foe, w) if win else (w, foe)
    log(g, f"{NAMES[w.god]} and {NAMES[foe.god]} fight: {NAMES[loser.god]} loses")
    _lose(g, loser)
    _resume(g, winner)
    return None


def _lose(g, w):
    """0x3D (0x004EEF30)."""
    w.anim_kind = ""
    if w.__dict__.get("uclass", 9) == 10 or (w.duel_saved[0] == "attack"):
        from . import attack
        w.task, w.phase = "attack", w.duel_saved[1]
        return attack._enter(g, w, "leave")
    from .figures import _go_home
    return _go_home(g, w)


def _resume(g, w):
    """0x3E: back to the saved action (Zeus hostile: god_attack_init again)."""
    task, phase = getattr(w, "duel_saved", ("visit", None))
    w.anim_kind = ""
    w.task = task
    if task == "attack":
        from . import attack
        if w.god == 0 and w.__dict__.get("uclass", 9) == 10:
            return attack.init(g, w)
        return attack._enter(g, w, phase or "wander")
    _W().schedule(g, w, 1)


__all__ = ["hunt", "defend", "athena_month", "apollo_month", "summon_artemis", "send_against_monster",
           "walk_interrupt", "encounter_check", "act", "duel", "look", "rng", "built"]
