"""The military module: soldiers, invaders, wolves, tower and wall sentries on the city map
(docs/logic/military.md). Self-contained and switchable (`military off`); the core calls only:

  day(g)                    systems.run_day, after recruitment (systems/military.py): packs, sentries, soldiers
  step29(g)                 Game.step at cycle step 29 of each day (FUN_00500910): the invaders' company AI and the
                            end-of-invasion check
  act(g, w)                 systems/walkers.act for the walkers this module drives (ROLES, or w.mil set while a
                            core walker fights or dies)
  entered(g, w)             systems/walkers.step_to when a walker steps onto a tile holding a combat unit
                            (figure_tile_contact 0x004D4DA0)
  look(g, w)                sim/export.walker_anim: the picture block of a combat unit (None = the core's)
  command(g, op, args)      Game.command: VERBS below; None when op is not ours
  export(g)                 /military.json for play mode (companies, invasion, arrows)
  enemies_alive(g)          systems/military.py: recruitment is frozen while invaders live (steps 13/14)
  sentiment(g)              systems/finance.py: the military-service component (0x00566E70; alarm.py)
  view_changed(g)           Game.command `view N`: the wall-walk grid follows the view; sentries moved off
                            tiles it no longer allows (0x004A1B70 -> 0x00587E50, 0x004CFEE0)

and for the empire module (sim/empire/war.py):
  invade(g, ev, pt)         a rival's army arrives on the city map (instead of the strength-only stub)
  march_out(g, ev, slots) / march_home(g, ev)    expedition companies walk to the map exit and back
  aid_arrive(g, ev_id, city, n, nation) / aid_recall(g, city)   defensive aid: event companies 21..30 at the map
                            entry (0x004E2C10) and their leaving (0x004E3060)
  enemy_present(g)          invaders or enemy warships alive (the aid stays while they are)
  navy_home / navy_send / navy_away / navy_casualties / navy_return    triremes on expeditions (navy.py)
and calls back empire.next_invasion (auto-defend) and empire.aid_lost (the last aid company is gone, 0x00481D40).

Randomness: its own generator (state "rng"), so the core city's random stream is not disturbed.
"""
import random
import weakref

ROLES = frozenset(("wolf", "tower_sentry", "wall_sentry", "arrow", "rabble", "hoplite", "horseman",
                   "enemy_infantry", "enemy_archer", "enemy_cavalry", "enemy_arrow",
                   "trireme", "enemy_warship", "enemy_transport"))          # ships: navy.py
VERBS = ("military", "mobilize", "move", "attack", "return", "mode", "rotate", "companies", "wolves", "invade",
         "bribe", "invasion", "autodefend", "navy", "trireme")
_CACHE = weakref.WeakKeyDictionary()
_LAST = (None, None)            # (weakref to the game asked last, its cache): skips the weak-dict lookup per step


def cache(g):
    global _LAST
    r, c = _LAST
    if r is not None and r() is g:
        return c
    c = _CACHE.get(g)
    if c is None:
        c = _CACHE[g] = {}
    _LAST = (weakref.ref(g), c)
    return c


def state(g):
    return g.sd("mil", {})


def on(g):
    return state(g).get("on", True)


def mrng(g):
    st = state(g)
    r = st.get("rng")
    if r is None:
        r = st["rng"] = random.Random(g.seed * 7919 + 13)
    return r


def _register():
    from ..systems import walkers
    from . import contact
    if walkers.CONTACT is None:
        walkers.CONTACT = contact.core_entered


def day(g):
    """The step-50 point (month_advance)."""
    _register()
    if not on(g):
        return
    from . import forces, alarm
    if g.day and g.day % g.rules["days_per_month"] == 0:
        alarm.month(g)                    # month_advance day 0: peace/war counters, auto-defend
    forces.day(g)


def step(g, s):
    """simulation_cycle_step 0x00483840's military cases: 5 / 29 formations_update (5: the morale waver; formations_pass: wolf packs;
    29: the invaders' company AI FUN_00500910), 13 cities_relations_update (an invasion's end), 31
    buildings_spawn_walkers (tower sentries case 0x84, trireme repair case 0x88)."""
    _register()
    if not on(g):
        return
    from . import wolves, defences, invaders, navy
    if s == 5:
        from . import morale
        morale.refresh(g)                 # formations_update(0): formations_count, formations_refresh, ..
        invaders.facings(g)               # FUN_004DE830: the companies' facing (+0x6B)
        morale.waver(g)                   # formations_morale_waver 0x004DDF20 (formations_update(0) only)
        wolves.day(g, recount=True)
    elif s == 13:
        invaders.relations(g)
    elif s == 29:
        invaders.facings(g)               # formations_update(1): FUN_004DE830 before the company AI
        invaders.day(g)
        from . import forces
        forces.timers(g)                  # FUN_004DF410 for the player's companies
        wolves.day(g, recount=False)
    elif s == 31:
        navy.day(g)
        defences.day(g)


def standards(g):
    """Every tick, after the cycle step (the standards are figures in walkers_update): their morale part."""
    if not getattr(g, "companies", None) or not on(g):
        return
    from . import forces
    forces.standards(g)


def step29(g):
    step(g, 29)


def view_changed(g):
    from . import defences
    if on(g):
        defences.view_changed(g)


def act(g, w):
    from . import units, wolves, defences, forces, invaders, navy
    if not on(g) and w.role in ROLES:
        if w.role == "trireme":                  # the module off: a launched trireme just waits at its wharf
            return units.walkers.schedule(g, w, 10 ** 6)
        return units.walkers.remove(g, w)
    r = w.role
    if r in navy.SHIPS:
        return navy.act(g, w)
    if r == "wolf":
        return wolves.act(g, w)
    if r in ("tower_sentry", "wall_sentry", "arrow", "enemy_arrow"):
        return defences.act(g, w)
    if r in ("rabble", "hoplite", "horseman"):
        return forces.act(g, w)
    if r in invaders.TYPES:
        return invaders.act(g, w)
    return units.act_core(g, w)          # a core walker in a fight or dying


def entered(g, w):
    from . import contact
    return contact.on_enter(g, w)


def look(g, w):
    from . import wolves, defences, forces, invaders, navy
    r = w.role
    if r in navy.SHIPS:
        return navy.look(g, w)
    if r == "wolf":
        return wolves.look(g, w)
    if r in ("tower_sentry", "wall_sentry", "arrow", "enemy_arrow"):
        return defences.look(g, w)
    if r in ("rabble", "hoplite", "horseman"):
        return forces.look(g, w)
    if r in invaders.TYPES:
        return invaders.look(g, w)
    return None


def enemies_alive(g):
    return any(w.role in ("enemy_infantry", "enemy_archer", "enemy_cavalry", "enemy_transport") and w.anim != "die"
               for w in g.walkers.values()) if state(g).get("invasions") else False    # g_enemy_units_alive


def sentiment(g):
    from . import alarm
    return alarm.sentiment(g)


def invade(g, ev, pt=8, **kw):
    """pt 1..8 a land invasion point (8 random), 9..16 by sea (navy.py; land when the map has no sea points).
    kw: invaders.invade's (target_class, quiet)."""
    from . import invaders, navy
    if pt >= 9 and navy.has_sea_invasions(g):
        return invaders.invade(g, ev, sea_pt=pt, **kw)
    return invaders.invade(g, ev, point=invaders.pick_point(g, pt if pt <= 8 else 8), **kw)


def aid_arrive(g, ev_id, city, n, nation):
    from . import forces
    return forces.aid_arrive(g, ev_id, city, n, nation)


def aid_recall(g, city):
    from . import forces
    return forces.aid_recall(g, city)


def episode_reset(g, armies=False, figures=False):
    """The continue start (episode_start_load kind 2). armies: every world city's army_months = 0 (0x008FBAC1, the
    'army in progress' that cities_relations_update ends with a defeat or a withdrawal): every invasion on the map
    is over, without an outcome (ours: the invasion and enemy company records). figures: FUN_0042C4E0, every enemy
    figure in use (types 0x28..0x2A soldiers, 0x3F transports, 0x40 warships) is deleted."""
    from . import invaders, units
    if armies:
        st = state(g)
        st.get("invasions", {}).clear()
        st.get("ecomps", {}).clear()
    if figures:
        for w in [w for w in g.walkers.values() if w.role in invaders.TYPES + ("enemy_transport", "enemy_warship")]:
            units.remove(g, w)


def enemy_present(g):
    from . import alarm
    return alarm.enemy_present(g)


def navy_home(g):
    """Trireme ids at home that may join an expedition (+0x132 < 0, not sinking)."""
    from . import navy
    return [w.id for w in navy.triremes(g) if getattr(w, "away", -1) < 0 and w.anim != "die"]


def navy_send(g, ev_id, ids):
    from . import navy
    navy.send(g, ev_id, ids)


def navy_away(g, ev_id):
    from . import navy
    return navy.away_ids(g, ev_id)


def navy_casualties(g, ev_id, pct):
    from . import navy
    navy.casualties(g, ev_id, pct)


def navy_return(g, ev_id):
    from . import navy
    navy.come_home(g, ev_id)


def march_out(g, ev, slots):
    from . import forces
    return forces.march_out(g, ev, slots)


def march_home(g, ev):
    from . import forces
    return forces.march_home(g, ev)


def command(g, op, a):
    if op not in VERBS:
        return None
    from . import commands
    return commands.run(g, op, a)


def export(g):
    from . import commands
    return commands.export(g)
