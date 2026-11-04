"""Scenario-event handlers of this module (docs/logic/events.md, heroes-monsters.md "Monster events"):

  4     quest            event_quest 0x00482820
  26    monster invasion monster_event_update 0x00481430
  0x27  hero arrival     hero_arrival_event_update 0x00481A80 (created by hero_send_for, hero_arrival_queue 0x004808D0)

`HANDLERS[type](g, ev)` runs once a month for every event of that type that is not a template (flag 1), as the exe's
month_events_dispatch 0x0046DFD0; `monster_killed(g, m)` is called directly on a kill (0x004812F0).

The record is track 1G's (sim/scenario, docs/logic/events.md "Ours"): id, type, month, year, item (+0x04: the monster
slot k for type 26), chain, flags, lead, countdown, state, active, b36 (+0x36), b38, b3a, b3c, b3e, kind (+0x60),
quest (+0x7A). The handlers are registered with `scenario.register` at import (sim/scenario PLUGINS lists this
module); dates, chains and new records come from its helpers (today/due/months_until_due/chain/alloc).
A game without a scenario (g.scenario None: old saves; `scenario on` loads one) keeps the records of the test verbs
(`monster`, `quest`) and hero arrivals in state(g)["events"], dispatched by month() here.
"""
from .. import messages, scenario
from . import state, data, monster_of_slot

TEMPLATE, RECURRING, DONE, WARN, WARNED, DYNAMIC = 1, 2, 4, 0x40, 0x80, 0x100
DISABLED = 0x20000


def fix(ev):
    """Records from saves before 727a1e6 call +0x60 `sub` (now `kind`); fields missing in older records get the
    editor defaults (scenario.blank)."""
    if "kind" not in ev:
        ev["kind"] = ev.pop("sub", 0)
    for k, v in scenario.blank(ev.get("id", 0)).items():
        ev.setdefault(k, v)
    return ev


def own(g):
    return state(g).setdefault("events", [])


def has_engine(g):
    return getattr(g, "scenario", None) is not None


def records(g):
    """Every record of our types (the scenario's, or our own without one)."""
    if has_engine(g):
        return [fix(r) for r in scenario.events(g) if r.get("type") in HANDLERS]
    return [fix(r) for r in own(g)]


def alloc(g, rec):
    """events_alloc 0x00467A40 + defaults: a new dynamic record (flags 0x100)."""
    rec = dict(rec)
    rec.setdefault("flags", DYNAMIC)
    if has_engine(g):
        y, m = scenario.today(g)
        rec.setdefault("year", y)
        rec.setdefault("month", m)
        return scenario.alloc(g, rec)
    ev = scenario.blank(1000 + len(own(g)))
    ev.update(year=year_offset(g), month=g.month)
    ev.update({k: v for k, v in rec.items() if k != "id"})
    own(g).append(ev)
    return ev


def chain(g, ev, text=None):
    """event_chain_trigger 0x0046DE00: the reward event +0x24."""
    if has_engine(g) and ev.get("chain", -1) >= 0:
        return scenario.chain(g, ev)
    return None


def year_offset(g):
    return scenario.today(g)[0]


def date_due(g, ev):
    """events_date_check 0x00471F00 (no force)."""
    return scenario.due(g, ev)


def months_until_due(g, ev):
    """event_months_until_due 0x00472000."""
    return scenario.months_until_due(g, ev)


def month(g):
    """Without a scenario: our own records, as month_events_dispatch 0x0046DFD0 (the scenario engine dispatches its
    own records)."""
    if has_engine(g):
        return
    for ev in list(own(g)):
        if not ev["flags"] & TEMPLATE:
            h = HANDLERS.get(ev["type"])
            if h is not None:
                h(g, ev)


# --- messages ----------------------------------------------------------------------------------------------

def post(g, title, ann, reason=None, at=None, voice=None, stinger=None, **vars):
    """FUN_00521A70 with a phrase record (title +2, announcement +0, reason +0x10); at = the tile the message's
    "go to" button shows (type 0xDE), else 0xE0. [reason_phrase] = the reason phrase's text, [greeting] from messages.fill
    ("O great", wm_sub_465B10), others from vars ([hero_needed], [time_until_attack]). voice: the spoken line played
    with it (a god's FUN_005A1050, a hero's arrival FUN_005A0F70: Audio/Voice/Walker/...); stinger: the music sting
    (FUN_005A1210: data/play/audio.json music.special key, "mon1" / "mon2"); play mode plays them when the message
    arrives, the voice first; a sound refused while another of these plays (viewer/play/audio.js special)."""
    def txt(pid):
        s = messages.text(pid)
        for k, v in vars.items():
            s = s.replace(f"[{k}]", str(v))
        return s
    try:
        vars.setdefault("reason_phrase", txt(reason) if reason else "")
    except KeyError:
        vars.setdefault("reason_phrase", "")
    try:
        t, b = txt(title), txt(ann)
        line = f"{t} {b}" if t[-1:] in "!?." else f"{t}. {b}"
    except KeyError:
        t, b = None, None
        line = f"[message {title:#x}/{ann:#x}]"
    if at is not None:
        line += f" ({at[0]},{at[1]})"
    # the message window's title and body are the texts (as messages.post; bugs.md 316: the ids showed as "2554")
    meta = dict(phrase=ann, reason=reason, popup=True, kind=0xDE if at else 0xE0, category=messages.category(ann))
    if t is not None:
        meta.update(title=t, body=b)
    c = messages.condensed(ann)
    if c is not None:            # the panel strip's line (FUN_00430D80; as messages.post), reason condensed too
        cv = dict(vars, reason_phrase=messages.condensed_reason(reason, **{k: str(v) for k, v in vars.items()
                                                                          if k != "reason_phrase"}))
        meta["condensed"] = messages.strip_text(c, **cv)
    if at is not None:
        meta["at"] = list(at)
    if voice:                                    # a god's / hero's line (FUN_005A1050 / FUN_005A0F70)
        meta["voice"] = voice
    if stinger:                                  # FUN_005A1210
        meta["stinger"] = stinger
    g.message(messages.Msg(line, meta) if hasattr(messages, "Msg") else line)


def _voice(g, god, kind):
    """The god's line with the message (FUN_005A1050: monster_event_update kind 4 for a god-sent monster, event_quest
    5 given / 6 fulfilled), from sim/gods when that module is there."""
    try:
        from .. import gods
    except ImportError:
        return None
    f = getattr(gods, "voice", None)
    return f(g, god, kind) if f is not None and isinstance(god, int) else None


# monster_event_texts 0x004810E0 / FUN_00480F20: (normal base, warning base) per monster; god-sent base per god
MONSTER_TEXT = [(0x744, 0x8F2), (0x74E, 0x908), (0x758, 0x91E), (0x762, 0x934), (0x76C, 0x94A), (0x776, 0x960),
                (0x780, 0x976), (0x78A, 0x98C), (0x794, 0x9A2), (0x79E, 0x9B8), (0x7A8, 0x9CE), (0x7B2, 0x9E4),
                (0xF36, 0xF76), (0xF2C, 0xF60), (0xF40, 0xF8C), (0xF22, 0xF4A)]
GOD_TEXT = [0x654, 0x660, 0x678, 0x690, 0x69C, 0x6A8, 0x6C0, 0x6CC, 0x684, 0x6B4, 0x6D8, 0x66C, 0xF0A, 0xF16]


def monster_texts(m, god):
    n, w = MONSTER_TEXT[m] if 0 <= m < len(MONSTER_TEXT) else MONSTER_TEXT[0]
    return n, w, GOD_TEXT[god] if 0 <= god < len(GOD_TEXT) else GOD_TEXT[0]


# --- type 26: monster invasion ------------------------------------------------------------------------------

def monster_event(g, ev):
    """monster_event_update 0x00481430."""
    fix(ev)
    from . import monsters, heroes
    st = ev["state"]
    if st in (1, 5):
        return
    k = ev["item"]
    m = monster_of_slot(g, k)
    if m < 0:
        return                                   # "ERR: No monster for event"
    from . import gods_block
    gods = gods_block(g)
    god = gods["slots"][k] if gods is not None and k in (0, 1) else -1
    ev["b36"] = god
    normal, warn, godsent = monster_texts(m, god)
    hero_text = normal + 2
    spawned, at, needs_hero = False, None, False
    if st == 0 and ev["kind"] == 2:              # +0x60 == 2: the warning path (oracle prediction first)
        ev["state"] = st = 4
    if st == 0:
        if not date_due(g, ev):
            return
        if ev["kind"] == 0:
            title, ann, reason = normal, normal + 1, normal + 2
        else:
            title, ann, reason = godsent, godsent + 2, godsent + 4
            hero_text = godsent + 3
        w = monsters.spawn(g, m, ev, "spawn")
        if w is not None:
            at = (w.x, w.y)
        ev["state"], ev["active"] = 1, 1
        needs_hero = spawned = True
        # sounds as the exe calls them: not god-sent FUN_005A1210(1) (S_mon1) before the spawn, god-sent the god's
        # line FUN_005A1050(god, 4); after a spawn FUN_005A1210(0) (S_mon1, refused while the first one plays)
        post(g, title, ann, reason, at, voice=_voice(g, god, 4) if ev["kind"] != 0 else None,
             stinger="mon1")
    elif st == 2:                                # the monster was killed
        ev["state"], ev["active"] = 5, 0
        if ev["b38"] & 0x100:                    # sic: +0x38 bit 8 (the exe tests param_1[0x1c] & 0x100)
            from ..systems import commemorative
            commemorative.grant(g, 7)
        if ev.get("chain", -1) >= 0:
            if m == 15:
                t = 0xFA2
            elif m == 12:
                t = 0xFA4
            elif m == 13:
                t = 0xFA3
            elif m == 14:
                t = 0xFA5
            else:
                t = m + 0xCAD
            chain(g, ev, t)
        post(g, normal + 6, normal + 7, stinger="mon2")       # FUN_005A1210(2): S_mon2
        return
    elif st == 4:                                # warning countdown
        lead = ev["lead"]
        left = months_until_due(g, ev)
        if left < 1:
            w = monsters.spawn(g, m, ev, "spawn")
            if w is not None:
                at = (w.x, w.y)
            ev["state"], ev["active"] = 1, 1
            hero_text = warn + 8
            needs_hero = spawned = True
            post(g, warn, warn + 7, warn + 9, at, stinger="mon1")    # FUN_005A1210(0) before the spawn
        else:
            ann = None
            if left == lead:
                if ev["flags"] & WARNED:
                    return
                ann = warn + 2
            elif left == 24 and lead >= 25:
                ann = warn + 3
            elif left == 12 and lead >= 13:
                ann = warn + 4
            elif left == 6 and lead >= 7:
                ann = warn + 5
            elif left == 1 and lead >= 2:
                ann = warn + 6
            if ann is None:                          # LAB_0048173d: the oracle prediction once (flag 0x40 set)
                if not ev["flags"] & WARN or ev["flags"] & WARNED:
                    return
                ev["flags"] |= WARNED
                ann = warn + 1
            post(g, warn, ann, warn + 9, time_until_attack=max(0, left))
            return
    else:
        return
    h = data()["monsters"][m]["hero"]
    if needs_hero and h >= 0:
        heroes.needed(g, h, hero_monster_text(h, m), hero_text)
    if spawned:
        from . import monsters as _m
        _m.apollo_sent(g, m)


def monster_killed(g, m):
    """monster_event_killed 0x004812F0: the active (state 1) type-26 event of monster m -> state 2, handled now.
    False when none (the caller posts the generic 'monster slain' message, 0x00481350)."""
    for ev in records(g):
        if ev["type"] == 26 and ev["state"] == 1 and monster_of_slot(g, ev["item"]) == m:
            ev["state"] = 2
            monster_event(g, ev)
            return True
    return False


# --- type 4: quest --------------------------------------------------------------------------------------

QUEST_TITLE = [0xA42, 0xA4A, 0xA5A, 0xA6A, 0xA72, 0xA7A, 0xA8A, 0xA92, 0xA62, 0xA82, 0xA9A, 0xA52, 0xDF5, 0xDFD,
               0xE2A, 0xE32, 0xE42, 0xE52, 0xE5A, 0xE62, 0xE72, 0xE7A, 0xE4A, 0xE6A, 0xE82, 0xE3A, 0xE8A, 0xE92]
QUEST_DONE = [0xAA2, 0xAAA, 0xABA, 0xACA, 0xAD2, 0xADA, 0xAEA, 0xAF2, 0xAC2, 0xAE2, 0xAFA, 0xAB2, 0xE05, 0xE0D,
              0xE9A, 0xEA2, 0xEB2, 0xEC2, 0xECA, 0xED2, 0xEE2, 0xEEA, 0xEBA, 0xEDA, 0xEF2, 0xEAA, 0xEFA, 0xF02]


def quest_title(god, q):
    """quest_title_text 0x00482360: PHRASE_<god>_quest[2]_title [god + 14 quest]."""
    return QUEST_TITLE[god + 14 * q] if 0 <= god < 14 and 0 <= q < 2 else 0xA42


def quest_fulfilled(god, q):
    """FUN_00482490: PHRASE_<god>_quest[2]_fulfilled_title."""
    return QUEST_DONE[god + 14 * q] if 0 <= god < 14 and 0 <= q < 2 else 0xAA2


def statue_variant(god, q, sel):
    """quest_statue_variant 0x004825C0: selector 1 small, 2 large; 0 none."""
    if not (0 <= god < 14 and 0 <= q < 2 and sel in (1, 2)):
        return 0
    base = 10 if q == 0 else 38
    if god < 12:
        return base + god + (12 if sel == 2 else 0)
    return base + 24 + (god - 12) + (2 if sel == 2 else 0)


def quest(g, ev):
    """event_quest 0x00482820. States: 0 waiting, 6 the hero is away, 7 returning, 10 done."""
    fix(ev)
    from . import heroes
    st = ev["state"]
    if st in (10, 5):
        return
    god, q = ev["kind"], ev.get("quest", 0)
    title = quest_title(god, q) if st == 0 else quest_fulfilled(god, q)
    if months_until_due(g, ev) < 1 and st == 6:
        ev["state"] = 7
        ev["countdown"] = max(1, travel_months(g, ev))
        return
    if st == 0:
        if ev["active"] or ev["flags"] & (DISABLED | TEMPLATE):
            return
        if (ev["year"], ev["month"]) != scenario.today(g):
            return
        ev["countdown"], ev["active"] = 0, 1
        h = heroes.hero_of_slot(g, ev["b36"])
        post(g, title, title + 1, title + 3, voice=_voice(g, god, 5), hero_needed=heroes.name(h) if h >= 0 else "a hero")
        if h >= 0:
            heroes.needed(g, h, quest_hero_text(god, q), title + 2)
        return
    if st == 7:
        ev["countdown"] -= 1
        if ev["countdown"] > 0:
            return
        h = heroes.hero_of_slot(g, ev["b36"])
        post(g, title, title + 1, title + 3, at=tuple(g.world.exit), voice=_voice(g, god, 6),
             hero_needed=heroes.name(h) if h >= 0 else "")
        from .. import alerts                    # event_quest: message 0xDE with alert 14 at the land exit
        alerts.raise_alert(g, alerts.SOLDIERS, tuple(g.world.exit))
        heroes.quest_home(g, ev)
        v = statue_variant(god, q, ev["b38"])
        if v:
            from ..systems import commemorative
            commemorative.grant(g, v)
        if ev.get("chain", -1) >= 0:
            chain(g, ev, title + 2)
        ev["state"], ev["active"] = 10, 0
        return
    if st == 6:
        ev["countdown"] -= 1
        if ev["countdown"] < 1:
            ev["countdown"] = 1


def travel_months(g, ev):
    """event_travel_months 0x0046D950 for a quest: the event-type table 0x00632710 row 4 has a city (+0 = 1, +1 = 0:
    FUN_004681C0), so city +0x1C (the open-play quest: 7, Thasus): route_between(city, player) 0x00462910 ->
    route_travel_months 0x004625A0; no route (or no empire module) -> 0 (the caller then takes 12)."""
    e = getattr(g, "empire", None)
    city = ev.get("city", -1)
    if e is None or city is None or city < 0:
        return 0
    try:
        player = e.player()
    except Exception:                            # noqa: BLE001  (empire off: no player city)
        return 0
    if city not in e.cities or e.route(city, player.id) is None:
        return 0
    return e.travel_months(city, player.id)


QUEST_HERO_TEXT = [0x57, 0x58, 0x5A, 0x5D, 0x5C, 0x5E, 0x60, 0x61, 0x5B, 0x5F, 0x62, 0x59, 99, 100,
                   0x65, 0x66, 0x68, 0x6B, 0x6A, 0x6C, 0x6E, 0x6F, 0x69, 0x6D, 0x70, 0x67, 0x71, 0x72]
HERO_MONSTER_TEXT = {(0, 9): 0x47, (0, 11): 0x48, (1, 2): 0x49, (1, 0): 0x4A, (2, 7): 0x4B, (2, 8): 0x4C,
                     (3, 3): 0x4D, (3, 10): 0x4E, (4, 1): 0x4F, (4, 5): 0x50, (5, 6): 0x51, (5, 4): 0x52,
                     (6, 12): 0x53, (6, 14): 0x54, (7, 13): 0x55, (7, 15): 0x56}


def quest_hero_text(god, q):
    """quest_hero_text 0x004FDA40: text 185:87..114 ('[hero_name] must return the Golden Fleece ...')."""
    return QUEST_HERO_TEXT[god + 14 * q] if 0 <= god < 14 and 0 <= q < 2 else -1


def hero_monster_text(h, m):
    """hero_monster_text 0x004FD900: text 185:71..86 ('Achilles is needed to do battle with Hector.')."""
    return HERO_MONSTER_TEXT.get((h, m), -1)


def open_quests(g):
    return [ev for ev in records(g) if ev["type"] == 4 and ev["active"] and ev["state"] == 0]


# --- 0x27: hero arrival -----------------------------------------------------------------------------------

ARRIVAL_TEXT = [0xA1E, 0xA24, 0xA2A, 0xA30, 0xA36, 0xA3C, 0xFB6, 0xFBC]


def queue_arrival(g, hero):
    """hero_arrival_queue 0x004808D0: a new event 0x27, +0x36 = hero, flags 0x100, state 1, countdown 1..3
    months (main generator rng15 % 3 + 1)."""
    from . import hrng
    r = scenario.rng15(g) if has_engine(g) else hrng(g).randrange(1 << 15)
    return alloc(g, dict(type=0x27, b36=hero, flags=DYNAMIC, state=1, countdown=r % 3 + 1))


def hero_arrival(g, ev):
    """hero_arrival_event_update 0x00481A80: countdown; at < 1 the hero appears at the map entry."""
    fix(ev)
    from . import heroes
    if ev["state"] != 1:
        return
    ev["countdown"] -= 1
    if ev["countdown"] >= 1:
        return
    h = ev["b36"]
    if not 0 <= h < 8:
        return
    w = heroes.create(g, h)
    t = ARRIVAL_TEXT[h]
    at = (w.x, w.y) if w is not None else tuple(g.world.entry)
    v = data()["heroes"][h].get("voice")         # FUN_005A0F70(hero): Audio/Voice/Walker/<0x006469D8 + hero * 0x28>
    post(g, t, t + 1, t + 2, at, voice=f"Voice/Walker/{v}" if v else None)
    ev["flags"] |= DONE
    ev["state"] = 0


HANDLERS = {4: quest, 26: monster_event, 0x27: hero_arrival}
for _t, _f in HANDLERS.items():
    scenario.register(_t, _f, owner="1I heroes and monsters (sim/heroes)")
