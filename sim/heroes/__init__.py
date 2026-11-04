"""Heroes and monsters (docs/logic/heroes-monsters.md): monsters at their lair (figure type 0x44), heroes (0x45) called
from their Hero's Hall (building 125), the duel, god quests. Self-contained and switchable (`heroes off`); the core
calls only:

  day(g)                 systems.run_day after the military module: month start -> heroes_month_check (0x00524860)
  act(g, w)              systems/walkers.act for roles "monster" and "hero" (ROLES)
  look(g, w)             sim/export.walker_anim: the picture block of a monster / hero
  command(g, op, args)   Game.command: VERBS (commands.py); None when op is not ours
  export(g)              /heroes.json for play mode (halls, requirements, monsters, quests)
  died(g, w, by) / fight_over(g, w)   from sim/military/hooks.py (the shared fight engine, units.py)
  hall_info(g, b)        the Hero's Hall info window rows (requirements, status, Send For)
  frame(g)               sim/live.py record_frame: draw colours (+0x168) of walkers and the petrified statues (0x46)
  games_chance(g, c)     sim/systems/games.py: the pan-Hellenic win chance with Hercules' hall (FUN_00565E30)

and for the scenario-event engine (track 1G, sim/scenario, docs/logic/events.md "Ours"): events.py registers the
handlers of types 4 (quest), 26 (monster invasion) and 0x27 (hero arrival) with scenario.register.

The scenario's monster slots (monster_of_slot 0x00586B40) come from the episode's god block (sim.scenario.gods;
else track 1H's data/gods/<map>.json): slots 0/1 = the monster of the unfriendly god in god slot 0/1, slot 2 = the
independent monster, 3..8 = guardians of friendly god slots 12..17.

Randomness: its own generator (state "rng"), so the core city's random stream is not disturbed (ours; the exe uses
its main generator for rest days and scan timers and MSVC rand() for the building-search radius).
"""
import json
import os
import random
import weakref

from ..data import DATA_DIR

ROLES = frozenset(("monster", "hero"))
VERBS = ("heroes", "monster", "monsters", "hero", "sendfor", "quest", "dispatch")
_CACHE = weakref.WeakKeyDictionary()
_DATA = {}


def data():
    if not _DATA:
        _DATA.update(json.load(open(os.path.join(DATA_DIR, "heroes.json"))))
    return _DATA


def cache(g):
    c = _CACHE.get(g)
    if c is None:
        c = _CACHE[g] = {}
    return c


def state(g):
    return g.sd("heroes", {})


def on(g):
    return state(g).get("on", True)


def hrng(g):
    st = state(g)
    r = st.get("rng")
    if r is None:
        r = st["rng"] = random.Random(g.seed * 104729 + 7)
    return r


def msrand(g):
    """MSVC rand() 0x005CC7A2 (seed 0x00662E30): seed = seed*214013+2531011, (seed>>16) & 0x7fff. The exe's second
    generator; ours starts from the module seed."""
    st = state(g)
    s = st.get("msseed")
    if s is None:
        s = hrng(g).randrange(1 << 31)
    s = (s * 214013 + 2531011) & 0xFFFFFFFF
    st["msseed"] = s
    return (s >> 16) & 0x7FFF


def gods_block(g):
    """The episode's god block (track 1G's g.scenario, sim.scenario.gods), else the map's (track 1H's
    data/gods/<map>.json), or None."""
    from .. import scenario
    gb = scenario.gods(g)
    if gb is not None:
        return gb
    c = cache(g)
    if "gods" not in c:
        p = os.path.join(DATA_DIR, "gods", f"{g.map_name}.json")
        c["gods"] = json.load(open(p)) if os.path.exists(p) else None
    return c["gods"]


def monster_of_slot(g, k):
    """scenario_monster_of_slot 0x00586B40."""
    gb = gods_block(g)
    if gb is None:
        return -1
    d = data()
    slots = gb["slots"]
    if k in (0, 1):
        return d["god_monster"][slots[k]] if slots[k] >= 0 else -1
    if k == 2:
        return gb.get("independent_monster", -1)
    if 3 <= k <= 8:
        god = slots[9 + k]
        return d["guardian"].get(str(god), -1) if god >= 0 else -1
    return -1


def slot_of_monster(g, m):
    """scenario_monster_slot_of 0x00586E70: the first slot 0..8 holding m, else -1."""
    for k in range(9):
        if monster_of_slot(g, k) == m:
            return k
    return -1


def is_guardian(g, m):
    """monster_is_guardian 0x00587020."""
    return 3 <= slot_of_monster(g, m) <= 8


def lair(g, k):
    """The map's monster point k (scenario block 0x902E08 x[3] / 0x902E14 y[3], i32), raw: World converts the map's
    logical points (the sandbox Maenads' logical (121, 200) is raw (122, 201))."""
    pts = getattr(g.world, "monster_points", None)
    if pts is None:
        from .. import world as _w
        pts = _w.monster_points(g.map_name)
    if 0 <= k < len(pts) and pts[k][0] >= 0 and pts[k][1] >= 0:
        return tuple(pts[k])
    return None


def _register():
    from ..military import units
    if units.MYTH is None:
        from . import combat
        units.MYTH = combat


def day(g):
    _register()
    if not on(g):
        return
    from . import heroes, monsters
    dpm = g.rules["days_per_month"]
    if g.day % dpm == 0 and g.day:
        heroes.month(g)
    monsters.day(g)


def act(g, w):
    _register()
    from . import monsters, heroes
    if not on(g):
        from ..systems import walkers
        return walkers.remove(g, w)
    if w.role == "monster":
        return monsters.act(g, w)
    return heroes.act(g, w)


def look(g, w):
    from . import monsters, heroes
    if w.role == "monster":
        return monsters.look(g, w)
    if w.role == "hero":
        return heroes.look(g, w)
    return None


def frame(g):
    """Per frame for play mode: tint = [[walker id, 15-bit colour]] (+0x168: 0x7C00 a devoured victim, walker_draw
    0x0044FEF0 -> sprite_dispatch colour blit FUN_005B86A0), statues = [[x, y, role, good, fdx, fdy, look, tick]]
    (figure 0x46, drawn with 0x6318). Empty when the module is off or nothing is tinted."""
    from . import monsters
    out = {}
    tint = [[w.id, w.tint] for w in g.walkers.values() if getattr(w, "tint", 0)]
    if tint:
        out["tint"] = tint
    st = monsters.statues(g)
    if st:
        out["statues"] = [[s["x"], s["y"], s["role"], s["good"], *s["face"], s.get("look"), s.get("tick", 0)] for s in st]
    return out


def walker_window(g, w):
    """The walker window's monster / hero lines (0x005740A0 cases 0x44 / 0x45; docs/play/info.md "Gods, monsters
    and heroes"): monster: its id (+0x60: name 190:id, portrait SPR_MONSTER_PORTRAITS + id) and phrase 0 (FUN_005A9C20
    case 0x44); hero: its id (185:id, SPR_HERO_PORTRAITS + id) and `warned` = a type-26 monster event active (+0x32)
    in state 4 (FUN_005A9C20 case 0x45 -> action phrase 0, so 0 + 7 + 1 = 8 "a monster on the way"; else the danger /
    city-mood phrases as other figures with both flags)."""
    if w.role == "monster":
        return dict(monster=getattr(w, "mid", 0), phrase=0)
    from . import events
    warned = any(r.get("type") == 26 and r.get("active") and r.get("state") == 4 for r in events.records(g))
    return dict(hero=getattr(w, "hero", 0), warned=warned)


def died(g, w, by):
    from . import monsters, heroes
    (monsters if w.role == "monster" else heroes).died(g, w, by)


def piece_grid(g, b):
    """For sim/military's grid_military (0x00502BA0): [(tiles, value)] per piece of composite b -- not started 0
    (vt+0x9C), attackable 1 (vt+0x8C, not damaged), else -1."""
    from . import monsters
    return monsters.piece_grid(g, b)


def pieces_version(g, mons):
    """A key that changes when a piece of these composites starts, is damaged or rebuilt (the grid's cache)."""
    return tuple((m.id, sum(p["s"] for p in m.misc["pieces"]), sum(1 for p in m.misc["pieces"] if p.get("damaged")))
                 for m in mons)


def victim(g, w, by):
    """For sim/military (the fight engine's kill): monster_hit_victim 0x00532CF0 -- devoured / petrified."""
    from . import monsters
    monsters.victim(g, w, by)


def fight_started(g, w):
    from . import monsters, combat
    if w.role == "monster":
        monsters.fight_started(g, w)
    elif w.role == "hero":
        combat.fight_started(g, w)


def melee_wake(g, w):
    """The hero's duel end (hero_duel_hit counts every fight tick; ours wakes him on the tick it runs out)."""
    from . import combat
    return combat.melee_wake(g, w)


def fight_over(g, w):
    from . import monsters, heroes
    return (monsters if w.role == "monster" else heroes).fight_over(g, w)


def command(g, op, a):
    if op not in VERBS:
        return None
    from . import commands
    return commands.run(g, op, a)


def export(g):
    from . import commands
    return commands.export(g)


def hall_info(g, b):
    from . import heroes
    return heroes.hall_info(g, b)


def games_chance(g, c):
    """For sim/systems/games.py (FUN_00565E90): the year's win chance after Hercules' adjustment (FUN_00565E30)."""
    from . import heroes
    return heroes.games_chance(g, c) if on(g) else c


def guardian(g, god, sanctuary, leader=None):
    """For sim/gods (monthly passive effects, Hephaestus' help, Ares' visit with his figure as `leader`): the friendly
    god's guardian monster at its sanctuary (sim/heroes/guardians.py)."""
    from . import monsters
    if on(g):
        return monsters.spawn_guardian(g, god, sanctuary, leader)


def monsters_near(g, x, y, r, bad=True):
    """For sim/gods (Apollo / Zeus fighting monsters): live monsters within Chebyshev r."""
    from . import monsters
    return monsters.near(g, x, y, r, bad)


def hall_allowed(g, extra):
    """The build menu's Hero's Hall items (0x004FA620): the hero belongs to one of the scenario's 3 monster slots, is
    needed (+0x0C) and has no hall. The sandbox cheat flag 0x00665DF0 (ours: `heroes cheat on`) skips the test."""
    from . import heroes
    names = [h["name"].lower() for h in data()["heroes"]]
    t = str(extra or "").strip().lower()
    if not t:
        raise ValueError("which hero's hall? build heroes_hall X Y HERO (" + ", ".join(names) + ")")
    h = int(t) if t.isdigit() else names.index(t) if t in names else -1
    if not 0 <= h < 8:
        raise ValueError(f"no hero '{extra}'")
    if heroes.hall(g, h) is not None:
        raise ValueError(f"{data()['heroes'][h]['hall']} is already built")
    if not state(g).get("cheat"):
        if h not in [heroes.hero_of_slot(g, k) for k in range(3)]:
            raise ValueError(f"{data()['heroes'][h]['name']} has no part in this scenario")
        if not heroes.record(g, h)["needed"]:
            raise ValueError(f"{data()['heroes'][h]['name']} is not needed yet (his hall is offered once a monster "
                             f"or a quest calls for him)")
    return h



def hall_menu(g):
    """Build menu 0x17 (Hero's Hall): [hero, name] per hall the menu lists, table 0x005F42CC order (heroes 0..7),
    names 185:(8 + hero); listed when hero_hall_buildable 0x004FA620: the cheat flag 0x00665DF0, or the hero of one of
    the 3 monster slots, needed (+0x0C) and without a hall (bugs.md 383)."""
    from . import heroes
    cheat = bool(state(g).get("cheat"))
    slots = [heroes.hero_of_slot(g, k) for k in range(3)]
    return [[h, d["hall"]] for h, d in enumerate(data()["heroes"][:8])
            if cheat or (h in slots and heroes.record(g, h)["needed"] and heroes.hall(g, h) is None)]

from . import events as _events  # noqa: E402,F401  registers the handlers of types 4, 26, 0x27 (sim/scenario)
