"""The gods module (docs/logic/religion.md): the 14 god records, the scenario's god roles, sanctuaries' priests
and sacrifices, god visits and blessings, help and prayers, jealousy and attacking gods, curses. Self-contained
and switchable (`gods off`); the core calls only:

  day(g)                    systems.run_day, once per day (= the exe's month_advance call, 16 a month): the monthly
                            god update on day 5, help + curse decay every day, sanctuary_update per sanctuary
  act(g, w)                 systems/walkers.act for the walkers this module drives (ROLES)
  look(g, w)                sim/export.walker_anim: the picture block of a god / priest (None = the core's)
  command(g, op, args)      Game.command: VERBS below; None when op is not ours
  export(g)                 play mode: god records, attacking gods, curses, buildable sanctuaries
  active(g, god)            god_sanctuary_active 0x004E9440: the permanent effects (systems use it; active_now: cached
                            per tick)
  built(g, god)             god_sanctuary_built 0x004E65F0
  cursed(g, b)              g_type_curse[type] != 0 (or g_production_stop): the building makes / sends nothing
  curse_free(g)             cursed() is False for every building now
  can_build(g, key)         build menu (FUN_00402B80) + placement limit (sanctuaries_at_limit 0x004E5F60)
  menu(g)                   the sanctuary keys the Mythology menu offers
  summon_artemis(g, wolf)   sim/military wolves: a wolf at its prey calls Artemis (the wolf chase 0x0056AF80)
  send_against_monster(g, god, monster)   sim/heroes: Apollo sent at a new monster (monster_event_update)
  expedition_sent(g, ev)    sim/empire war.attack (army_dialog_dispatch): Ares may join it (aid.py)
  expedition_battle(g, ev)  sim/empire war.battle: Ares comes back after it
  ares_helps(g, ev)         the event has Ares' flag 0x1000 (the enemy army counts 50 %)
  hermes_pays(g, ev) / hermes_paid(g)   sim/empire diplomacy.fulfil: Hermes pays the request (hermes_request_auto)

and for the scenario module (sim/scenario, track 1G): the god-invasion handler, event type 27 (invasion.py).

Days: our day = one month_advance call (51 ticks); month_tick 0..15 = g.day % 16.
Randomness: its own generator (state "rng"), so the core city's random stream is not disturbed.
Old saves: the state is created on first use (gods on, roles from the map's scenario).
"""
import json
import os
import random

ROLES = frozenset(("god", "priest", "god_bolt", "entranced", "god_helper"))
VERBS = ("gods", "pray", "oracle", "jealous", "godattack", "godvisit", "curse")
GODS = ["zeus", "poseidon", "demeter", "apollo", "artemis", "ares", "aphrodite", "hermes", "athena", "hephaistos",
        "dionysus", "hades", "hera", "atlas"]
NAMES = ["Zeus", "Poseidon", "Demeter", "Apollo", "Artemis", "Ares", "Aphrodite", "Hermes", "Athena", "Hephaestus",
         "Dionysus", "Hades", "Hera", "Atlas"]
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_T = None


def T():
    """data/gods.json (tools/build_gods.py): the exe's god tables."""
    global _T
    if _T is None:
        with open(os.path.join(ROOT, "data", "gods.json")) as f:
            _T = json.load(f)
    return _T


def god_id(name):
    name = name.lower().replace("hephaestus", "hephaistos")
    if name.isdigit():
        return int(name)
    return GODS.index(name) if name in GODS else -1


def state(g):
    st = g.sd("gods", {})
    if "rec" not in st:
        from . import roles
        roles.init(g, st)
    return st


def on(g):
    return state(g).get("on", True)


def reapply(g):
    """A new episode's god block on a running city (sim/episode.py resume; roles.apply)."""
    from . import roles
    roles.apply(g, state(g))


def rng(g):
    st = state(g)
    r = st.get("rng")
    if r is None:
        r = st["rng"] = random.Random(g.seed * 104729 + 7)
    return r


def rec(g, i):
    return state(g)["rec"][i]


def dom(g):
    """month_tick 0x0091EC0C: 0..15."""
    return g.day % g.rules["days_per_month"]


# --- sanctuaries ----------------------------------------------------------------------------------------------

def sanctuary(g, i):
    """god_sanctuary_building 0x004E8BF0: the god's sanctuary (the first placed: god+0x08 is written when a
    sanctuary is placed, 0x004E8C40), or None. Poseidon's grand sanctuary (type 98) in a Poseidon game."""
    keys = ("sanctuary_" + GODS[i],) + (("sanctuary_poseidon_grand",) if i == 1 else ())
    from ..systems import index
    bs = [b for b in index.of(g, "monument") if b.key in keys]
    return min(bs, key=lambda b: b.id) if bs else None


def god_of(b):
    """sanctuary_type_to_god 0x00546DB0."""
    k = b.key[len("sanctuary_"):] if b.key.startswith("sanctuary_") else ""
    if k == "poseidon_grand":
        return 1
    return GODS.index(k) if k in GODS else -1


def built(g, i):
    """god_sanctuary_built 0x004E65F0: construction > 99 %."""
    from ..systems import monuments
    b = sanctuary(g, i)
    return b is not None and monuments.complete(b)


def active(g, i):
    """god_sanctuary_active 0x004E9440: the sanctuary's activity byte +0x32 != 0 (22 on completion, 24 after a
    sacrifice, -1 a month while staffed: sanct.py). With the module off: complete (as before 10-29)."""
    if isinstance(i, str):
        i = god_id(i)
    b = sanctuary(g, i)
    if b is None:
        return False
    if not on(g):
        from ..systems import monuments
        return monuments.complete(b)
    return b.misc.get("activity", 0) != 0


def active_now(g, i):
    """active(g, i) cached for the current tick (hot paths: a walker's speed, a soldier's armour)."""
    c = g.__dict__.get("_godfx")
    if c is None or c[0] != g.tick:
        c = g._godfx = (g.tick, {})
    v = c[1].get(i)
    if v is None:
        v = c[1][i] = active(g, i)
    return v


def count_sanctuaries(g):
    """Gods with a sanctuary placed (god_sanctuary_building > 0), built or not."""
    return sum(1 for i in range(14) if sanctuary(g, i) is not None)


def at_limit(g):
    """sanctuaries_at_limit 0x004E5F60: min(scenario +0xDC, 4) sanctuaries placed."""
    st = state(g)
    if st.get("free"):
        return False
    return count_sanctuaries(g) >= min(st["max_sanct"], 4)


def can_be_jealous(g, i):
    """god_can_be_jealous 0x004E6010: listed, friendly, no sanctuary, may be jealous."""
    r = rec(g, i)
    return r["listed"] == 1 and r["unfriendly"] == 0 and sanctuary(g, i) is None and r["jealous"]


def menu(g):
    """FUN_00402B80, menus 0x14/0x26: a sanctuary is offered when scenario +0xDC != 0 and god_can_be_jealous(god)
    (so: one per god, only gods in slots 12..17 flagged 'may be jealous'). Without a scenario god block (custom
    maps, gods off): every sanctuary (ours)."""
    st = state(g)
    if st.get("free") or not on(g):
        return None
    if not st["max_sanct"]:
        return []
    return ["sanctuary_" + GODS[i] for i in range(14) if can_be_jealous(g, i)]


def can_build(g, key):
    """None when key may be placed, else the reason (build_commit 0x00498910: the menu, then
    sanctuaries_at_limit -> message 0xE5 + max)."""
    if not key.startswith("sanctuary_"):
        return None
    m = menu(g)
    if m is None:
        return None
    if at_limit(g):
        return f"no more sanctuaries: the limit is {min(state(g)['max_sanct'], 4)} (message {0xE5 + state(g)['max_sanct']})"
    if key not in m:
        return "this god's sanctuary cannot be built here (not a friendly god of this scenario, or already built)"
    return None


# --- curses -----------------------------------------------------------------------------------------------------

def cursed(g, b):
    """g_type_curse[type] != 0 (in month_advance calls), or g_production_stop (Hades): the building makes and sends
    nothing (buildings_spawn_walkers)."""
    st = getattr(g, "gods", None)          # hot path: no lazy init (no state yet = no curse)
    if not st or not st.get("on", True):
        return False
    if st.get("stop", 0) > 0:
        return True
    c = st.get("curse")
    if not c:
        return False
    zid = g.cat.spec(b.key).get("zeus_id")
    return c.get(zid, 0) > 0


def curse_free(g):
    """No curse and no production stop is in force: cursed() is False for every building (a daily pass over all
    buildings checks this once; performance round 3)."""
    st = getattr(g, "gods", None)
    return not st or not st.get("on", True) or (st.get("stop", 0) <= 0 and not st.get("curse"))


# --- interface ----------------------------------------------------------------------------------------------------

def day(g):
    st = state(g)
    if not st.get("on", True):
        return
    from . import month, sanct, help as god_help
    if dom(g) == 5:
        month.update(g)                     # gods_month_update 0x004E69A0
    god_help.update(g)                      # gods_help_update 0x004E6B10
    month.curse_decay(g)                    # curse_timers_decay 0x004E5EB0
    sanct.update(g)                         # sanctuary_update 0x004E94C0 per sanctuary (cycle step 31)


def act(g, w):
    from . import figures, priests
    from ..systems import walkers
    if not on(g):
        return walkers.remove(g, w)
    if w.role == "priest":
        return priests.act(g, w)
    if w.role == "god_bolt":
        from . import bolts
        return bolts.act(g, w)
    if w.role == "entranced":
        from . import attack
        return attack.follower_act(g, w)
    if w.role == "god_helper":                  # Hades' miners, Athena's growers (gifts.py)
        from . import gifts
        return gifts.helper_act(g, w)
    return figures.act(g, w)


SOUND = {"appear": "mat", "vanish": "demat", "vanish_gated": "demat"}   # FUN_004DC180 slots 9 / 10 (figure_set_action, the god handler)


def look(g, w):
    if w.role == "god":
        from . import figures
        h = figures.look(g, w)
        if h and h[0] == "work":                 # + the god's sound at the look's start (play mode, gods.js)
            s = SOUND.get(h[8])
            if h[8] == "cast":                   # 0xC bless / help (FUN_004C4910.., 0x19 arrival): sanctify 11;
                s = ("curse" if w.task == "attack" else    # the curse's enter (god_curse_target_enter): 12
                     "sanctify" if w.task in ("bless", "precinct", "hades", "athena", "help_food") else None)
            if w.task == "ares":                 # 0x22 is written directly, not by figure_set_action: no sound
                s = None
            # [10] the sound kind, [11] the tile progress at the look's start (play mode adds the walk table's term,
            # bugs.md 262): 0 after the visit's roam step (the exe's Apollo blessing, oracle 1H-bless1), else 15 (the
            # arrival of figure_walk_then: bolts, curse; oracle 1H-bolt)
            h = h + [s, 0 if w.task == "bless" else 15]
        return h
    if w.role == "priest":
        from . import priests
        return priests.look(g, w)
    if w.role == "god_bolt":
        from . import bolts
        return bolts.look(g, w)
    if w.role == "god_helper":
        from . import gifts
        return gifts.helper_look(g, w)
    return None


def walker_window(g, w):
    """The walker window's god lines (0x005740A0 case 0x43; docs/play/info.md "Gods, monsters and heroes"): the god
    id (+0x60: name 157:id, title 158:id, portrait SPR_GOD_PORTRAITS + id), its record's unfriendly byte (83:0/1)
    and the phrase picked at open (FUN_005ABB90 -> FUN_005A9C20 case 0x43: Figure+0x7D in the god's thought group,
    FUN_004E3750; -1 = none). The exe reads the god's action number; ours maps the sim's task (an approximation
    where the exe's action is finer): visit / bless (actions 8, 0x0C) -> 0; Zeus hostile 2, in a fight (0x3C,
    0x50) 1; Poseidon, Hades hostile 1; the others hostile 1, then their help actions: Demeter's food 2, Apollo's
    and Aphrodite's precinct walk 2, Apollo's / Aphrodite's shot at a target (0x50 / 0x4A) 3, Artemis' meat 2 and
    hunt 3, Ares' battle 2, Hermes' jealous roam (0x57) 2, Athena's growers 2, Hephaestus 2 while a monster is on
    the map, Dionysus' wine 2."""
    from . import attack
    i, t = getattr(w, "god", 0), getattr(w, "task", "")
    if t in ("visit", "bless"):
        ph = 0
    elif i == 0:
        ph = 2 if attack.hostile(g, w) else 1 if t in ("duel", "defend") else -1
    elif i in (1, 11):
        ph = 1 if attack.hostile(g, w) else -1
    else:
        ph = 1 if attack.hostile(g, w) else -1
        help_ = {2: {"help_food": 2}, 3: {"precinct": 2, "defend": 3}, 4: {"help_food": 2, "hunt": 3},
                 5: {"ares": 2}, 6: {"precinct": 2, "defend": 3}, 7: {"jealous": 2}, 8: {"athena": 2},
                 10: {"wine": 2}}.get(i, {})
        if t in help_:
            ph = help_[t]
        if i == 9 and any(m.role == "monster" and m.anim != "die" for m in g.walkers.values()):
            ph = 2
    return dict(god=i, unfriendly=int(rec(g, i).get("unfriendly", 0)), phrase=ph)


def voice(g, i, kind):
    """FUN_005A1050(god, kind): the god's spoken line, Audio/Voice/Walker/<data/gods.json voices[god][kind]> (kinds:
    0/1/2 jealous attack by sanctuaries placed 3+ / 1..2 / none, 3 invasion, 4 its monster, 5/6 quest given / done,
    7 help); Apollo's kind 1 in a Poseidon game is entry 8. None when the module is off or the god unknown."""
    if not 0 <= i < 14 or not on(g):
        return None
    if i == 3 and kind == 1 and getattr(g, "poseidon", False):
        kind = 8
    v = T().get("voices", [[None] * 9] * 14)[i][kind]
    return f"Voice/Walker/{v}" if v else None


def summon_artemis(g, wolf):
    from . import fight
    return fight.summon_artemis(g, wolf)


def send_against_monster(g, i, m):
    from . import fight
    if not on(g):
        return None
    return fight.send_against_monster(g, i, m)


def expedition_sent(g, ev):
    if on(g):
        from . import aid
        aid.expedition_sent(g, ev)


def expedition_battle(g, ev):
    if on(g):
        from . import aid
        aid.expedition_battle(g, ev)


def ares_helps(g, ev):
    return bool(ev.get("god_help")) and on(g)


def hermes_pays(g, ev):
    if not on(g):
        return False
    from . import aid
    return aid.hermes_pays(g, ev)


def hermes_paid(g):
    from . import aid
    aid.hermes_paid(g)


def command(g, op, a):
    if op not in VERBS:
        return None
    from . import commands
    return commands.run(g, op, a)


def export(g):
    from . import commands
    return commands.export(g)
