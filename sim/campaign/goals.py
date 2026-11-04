"""Episode goals as the exe judges them (track 1L-3; docs/campaign-format.md "The campaign module").

The goal table (0x00FE2768: +4 count, up to 6 records of 76 bytes from +8: +0 type, +4 v1, +8 v2, +0xC v3, +0x10 v4,
+0x14 the 'other' byte) is g.campaign["goals"]: [{type, v: [v1..v6], other, ...}]. The values come from the episode
(data/campaign/<id>.json "goals", type-11 goals already expanded) and the counters live in the same fields as in
the exe, so they are saved with the game.

Every day (sim/hooks.py "day"; the core calls day(g)) the losses the core signals at once are taken; at the month
change goals_month_check 0x0052B610 runs (month_advance 0x00483C10 calls it last, after the year rollover):

  result = -1 if a loss is already recorded (0x00FEB160 >= 0) else scenario_goals_check 0x00526990
  the forced win flag 0x00F2A6DB (`campaign win`, a test command) -> 1
  continue building after the last victory (0x00FEAF28) -> 0, nothing judged
  1: victory (shown once, 0x00FEB168), -1: defeat (the defeat screen; the exe opens it one day later the first
  time in a session, 0x00FEB164; ours: a day later every time, campaign["defeat_at"])

scenario_goals_check 0x00526990: the counters (FUN_00525FB0 sanctuaries, FUN_005260F0 pyramids (Poseidon, not
ported), FUN_005262A0 housing, FUN_00526330 yearly profit, FUN_00526370 yearly production), then the goals in
order: types 0..10, 14..16 AND their goal_met into the result (it starts as count > 0); type 12 (time limit)
SETS the result to "its year not reached" and remembers that it was reached; type 13 (survival time) SETS the
result and the survival flag to "its year reached"; type 11 is skipped. Then: result or survival -> won (1); the
time limit reached -> lost (PHRASE_lose_out_of_time 0xB95); 36 months in debt (0x00FEB27C >= 0x24) -> lost
(PHRASE_lose_economical 0xB91); else 0. (Order quirk: a time limit after other goals overwrites their result.)
Losses outside the check: an enemy army sacks the city a second time (city_conquers_player 0x00482200 ->
PHRASE_lose_military 0xB92; sim/military sets mil["game_lost"]); the parent city falls while in a colony
(FUN_00477AB0 -> 0xB93 / 0xB94: sim/empire/status_events.destroyed sets g.episode_lost, taken here at once).
"""
from .. import measure

NAMES = ["Population", "Treasury", "Sanctuary", "Support", "Quest", "Slay", "Yearly production", "Rule",
         "Yearly profit", "Housing", "Trading partners", "Unused (old dispatch goods goal)", "Time limit",
         "Survival time", "Set aside goods", "Pyramid", "Hippodrome"]          # text group 194:0..16
NORMAL = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14, 15, 16}     # the jump table's group 0 (byte table 0x00526D68)
LOSE_TITLE, LOSE_DEBT, LOSE_MILITARY, LOSE_PARENT_DESTROYED, LOSE_PARENT_FALLS, LOSE_TIME = range(0xB90, 0xB96)
UNITS = {11: "soldiers", 12: "hoplites or horsemen", 13: "horsemen", 57: "triremes"}
SCULPTURE = 19                                               # 400 units per load (event_amount_units 0x00466E30)
FOOD = 25                                                    # 0x19: every food 1..8 together


def records(ep):
    """The episode's goal table as goals_load_episode 0x0052DE20 copies it (goals_expand_set_aside done by
    tools/build_campaign.py)."""
    out = []
    for gl in ep.get("goals", [])[:6]:
        v = (list(gl["v"]) + [0] * 6)[:6]
        out.append(dict(type=gl["type"], v=v, other=0, good=gl.get("good")))
    return out


def _good_key(r):
    if r.get("good"):
        return r["good"]
    from ..empire.model import GOOD_IDS
    gid = r["v"][0] & 0xFF if r["type"] == 14 else r["v"][0]
    return {i: k for k, i in GOOD_IDS.items()}.get(gid)


def _finished(g, god):
    """FUN_004F0B30 on the god record: its sanctuary is finished (monument_progress > 99)."""
    from .. import gods
    return 0 <= god < 14 and gods.built(g, god)


# --- the counters (scenario_goals_check's first five calls) ------------------------------------------------------

def counters(g, goals):
    # FUN_00525FB0, type 2: a goal for one god takes that god (v2 = v1, v4 = 1; a second goal for the same god logs
    # "ERR GOAL: two goals requiring the same god"); then each 'any god' goal takes finished sanctuaries of gods
    # not taken yet, counting them in v4 until v3; the 'other' byte marks every type-2 goal after the first when
    # there are two or more ("any other god" / "other sanctuaries" in the texts).
    taken = [False] * 16
    n = 0
    for r in goals:
        if r["type"] == 2:
            v = r["v"]
            v[1], v[3] = -1, 0
            n += 1
            if v[0] != -1 and 0 <= v[0] < 16 and not taken[v[0]]:
                v[1], taken[v[0]], v[3] = v[0], True, 1
    first = True
    for r in goals:
        if r["type"] != 2:
            continue
        r["other"] = 0 if n < 2 or first else 1
        first = False
        v = r["v"]
        if v[0] == -1:
            for god in range(14):
                if not taken[god] and _finished(g, god):
                    v[1], taken[god] = god, True
                    v[3] += 1
                    if v[2] <= v[3]:
                        break
    m = None
    for r in goals:                              # FUN_005262A0, type 9: v3 = people in houses of type >= v1
        if r["type"] == 9:
            r["v"][2] = measure.people_at_least(g, r["v"][0])
    for r in goals:                              # FUN_00526330, the FIRST type-8 goal: v2 = max(v2, last year's profit)
        if r["type"] == 8:
            r["v"][1] = max(r["v"][1], measure.profit_last_year(g))
            break
    for r in goals:                              # FUN_00526370, type 6: v3 = max(v3, last year's production / 100)
        if r["type"] == 6:
            if m is None:
                m = measure.values(g)
            r["v"][2] = max(r["v"][2], m["produced_last_year"].get(_good_key(r), 0))


# --- goal_met 0x00526FC0 (and the check's own copies of it) -------------------------------------------------------

def year_reached(g, r):
    """0x00526F20 (types 12, 13): scenario_start_year + v1 <= year."""
    return g.__dict__.get("scenario_year", g.start_year) + r["v"][0] <= g.year


def met(g, r):
    t, v = r["type"], r["v"]
    if t == 0:
        return g.city.population >= v[0]
    if t == 1:
        return g.city.treasury >= v[0]
    if t == 2:
        if v[0] != -1:
            v[2] = 1
        if v[2] > 1:
            return v[3] >= v[2]
        return v[1] != -1 and _finished(g, v[1])
    if t == 3:
        return measure.units(g).get(v[0], 0) >= v[1]
    if t in (4, 5):                              # FUN_00526E50 / 00526E90: the event's state +0x30
        from .. import scenario
        ev = scenario.get(g, v[0])
        return ev is not None and ev.get("state") == (10 if t == 4 else 5)
    if t in (6, 9):
        return v[2] >= v[1]
    if t == 7:                                   # FUN_00526ED0: out of 0..21 -> met; else relationship 2 (vassal)
        if not 0 <= v[0] <= 21:
            return True
        e = getattr(g, "empire", None)
        c = e.cities.get(v[0]) if e is not None else None
        return c is not None and c.relation == "vassal"
    if t == 8:
        return v[1] >= v[0]
    if t == 10:
        return measure.values(g)["trading_partners"] >= v[0]
    if t in (12, 13):
        return year_reached(g, r)
    if t == 14:                                  # FUN_00526F00: no good, or the amount set aside
        return (v[0] & 0xFF) == 0 or v[1] <= v[2]
    if t == 15:                                  # pyramids (Poseidon, FUN_00526F40): not ported
        return False
    if t == 16:                                  # FUN_00526F90: a hippodrome (Poseidon) at least v1 stades long
        L = measure.values(g)["hippodrome_length"]
        return L is not None and L >= v[0]
    return False


def check(g, goals):
    """scenario_goals_check 0x00526990: 1 won, -1 lost (with the phrase), 0 neither. Returns (result, phrase)."""
    counters(g, goals)
    res = len(goals) > 0
    survived = timed_out = False
    for r in goals:
        t = r["type"]
        if t in NORMAL:
            ok = met(g, r)
            r["met"] = ok
            res = res and ok
        elif t == 12:
            timed_out = year_reached(g, r)
            r["met"] = not timed_out
            res = not timed_out
        elif t == 13:
            survived = res = year_reached(g, r)
            r["met"] = survived
    if res or survived:
        return 1, None
    if timed_out:
        return -1, LOSE_TIME
    if g.city.months_in_debt >= 36:
        return -1, LOSE_DEBT
    return 0, None


# --- the month check and the core's immediate losses --------------------------------------------------------------

def day(g):
    """The day hook (sim/hooks.py). A loss the core signals (mil["game_lost"]: the second sack, city_conquers_player
    0x00482200, which calls goals_month_check at once); at the month change goals_month_check."""
    st = g.__dict__.get("campaign")
    if st is None or st.get("result"):
        return
    if (g.__dict__.get("mil") or {}).get("game_lost") and st.get("lost") is None:
        st["lost"] = LOSE_MILITARY
        month_check(g)
        return
    if g.__dict__.get("episode_lost") and st.get("lost") is None:   # the parent city fell (FUN_00477AB0: 0xB93 /
        st["lost"] = g.__dict__.pop("episode_lost")                     # 0xB94, sim/empire/status_events.destroyed)
        month_check(g)
        return
    if g.day and g.day % g.rules["days_per_month"] == 0:
        month_check(g)


def month_check(g):
    """goals_month_check 0x0052B610."""
    st = g.campaign
    if st.get("stay"):                           # 0x00FEAF28: continue building this city (after the last episode)
        st["forced"] = False
        return 0
    if st.get("lost") is None:
        r, why = check(g, st["goals"])
        if r < 0:
            st["lost"] = why
    else:
        r = -1
    if st.get("forced"):
        r = 1
    st["forced"] = False
    if r > 0:
        st["result"] = 1
        st["won_at"] = g.date()
        from .flow import episode_of
        v = (episode_of(g).get("victory") or {}).get("title") or "Victory"
        g.message(f"Victory! {v}. (campaign: `campaign status` / `campaign next`)")
    elif r < 0:
        st["result"] = -1
        st["lost_at"] = g.date()
        # the defeat screen opens at the next day's check (0x00FEB164: the first defeat of a session waits a day;
        # oracle 1L3-time-limit: lost at tick 51, the screen at tick 102); ours: every defeat (sim/campaign/flow
        # screen())
        st["defeat_at"] = g.tick + g.rules["ticks_per_day"]
        from .. import messages
        messages.post(g, LOSE_TITLE, st["lost"], city=_parent_city(g))
    return r


def _parent_city(g):
    e = getattr(g, "empire", None)
    if e is None:
        return None
    return next((c for c in e.cities.values() if c.kind == "parent"), None)


# --- Set aside (the objectives screen: click a type-14 goal, confirm) ---------------------------------------------

def stock_loads(g, gid):
    """0x00529D10 / 0x0052ECF0: (granary [goods 1..8] + trading post + storehouse units) / 100 (sculpture 400);
    0x19 = every food together."""
    from ..empire import diplomacy
    from ..empire.model import GOOD_IDS
    per = 400 if gid == SCULPTURE else 100
    if gid == FOOD:
        return diplomacy.stock(g, diplomacy.FOOD) // per
    key = {i: k for k, i in GOOD_IDS.items()}.get(gid)
    return diplomacy.stock(g, key) // per if key else 0


def set_aside(g, i):
    """The 'Set aside' confirm 0x0052ECF0 on goal i (type 14): the dialog opens only when the city has the rest
    (need = amount - counter > 0, stock in loads >= need, 0x00529D10); then need loads leave storage
    (city_goods_remove 0x00489B90 mode 3) and the counter v3 += need. Returns a text; raises ValueError."""
    goals = g.campaign["goals"]
    if not 0 <= i < len(goals) or goals[i]["type"] != 14:
        raise ValueError(f"goal {i + 1} is not a 'Set aside goods' goal")
    r = goals[i]
    gid = r["v"][0] & 0xFF
    if gid == 0:
        raise ValueError("this goal names no good: it is met")
    need = r["v"][1] - r["v"][2]
    have = stock_loads(g, gid)
    if need <= 0:
        raise ValueError("already set aside (Done)")
    if have < need:
        raise ValueError(f"not enough in stock: {have} of the {need} still to set aside (the goal's window stays shut)")
    per = 400 if gid == SCULPTURE else 100
    from ..systems import economy
    from ..empire import diplomacy
    key = _good_key(r)
    if gid == FOOD:
        left = need * per
        for f in sorted(diplomacy.FOODS, key=lambda f: -diplomacy.stock(g, f)):
            left -= economy.goods_remove(g, f, left)
            if left <= 0:
                break
    else:
        economy.goods_remove(g, key, need * per)
    r["v"][2] += need
    return f"set aside {need} {key or 'food'} ({r['v'][2]} of {r['v'][1]})"


# --- texts ---------------------------------------------------------------------------------------------------------

def _god_name(i):
    from .. import gods
    return gods.NAMES[i] if 0 <= i < 14 else "?"


def describe(g, r, in_colony=False):
    """(goal text, current value text) in the words of text group 194 (17..42, 45..72)."""
    t, v = r["type"], r["v"]
    key = _good_key(r) if t in (6, 14) else None
    if t == 0:
        return f"Population of {v[0]}", f"population {g.city.population}"
    if t == 1:
        return f"Treasury of {v[0]}", f"treasury {g.city.treasury}"
    if t == 2:
        if v[0] != -1:
            what = f"Sanctuary to {_god_name(v[0])}"
        elif v[2] > 1:
            what = f"{v[2]} {'other ' if r.get('other') else ''}sanctuaries"
        else:
            what = "Sanctuary to any other god" if r.get("other") else "Sanctuary to any god"
        return what, (f"{v[3]} complete" if v[2] > 1 else "complete" if met(g, dict(r, v=list(v))) else
                      "Sanctuary needed")
    if t == 3:
        return f"Support {v[1]} {UNITS.get(v[0], f'units of type {v[0]}')}", f"{measure.units(g).get(v[0], 0)} supported"
    if t == 4:
        return f"Quest (event #{v[0]})", "completed" if met(g, r) else "not completed"
    if t == 5:
        return f"Slay a monster (event #{v[0]})", "slain" if met(g, r) else "not slain"
    if t == 6:
        return f"Produce {v[1]} {key} in one year", f"best is {v[2]}"
    if t == 7:
        e = getattr(g, "empire", None)
        c = e.cities.get(v[0]) if e is not None else None
        return f"Rule {c.name if c else f'city {v[0]}'}", (c.relation if c else "-")
    if t == 8:
        return f"Yearly profit of {v[0]}", f"best is {v[1]}"
    if t == 9:
        import json
        import os
        names = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..", "data", "houses.json")))
        lvl = v[0] - 2
        name = names[lvl] if 0 <= lvl < len(names) else f"house type {v[0]}"
        return f"{v[1]} people in {name} or better", f"{v[2]} qualify (at the last month change; now {measure.people_at_least(g, v[0])})"
    if t == 10:
        return f"{v[0]} trading partners", f"{measure.values(g)['trading_partners']} trading partners"
    if t in (12, 13):
        y = g.__dict__.get("scenario_year", g.start_year) + v[0]
        d = f"{abs(y)} {'BC' if y < 0 else 'AD'}"
        left = (y - g.year) * 12 - g.month
        return (("Complete episode before " if t == 12 else "Survive until ") + d,
                f"{max(0, left)} months remain")
    if t == 14:
        gid = v[0] & 0xFF
        return (f"{v[1]} {key} for {'parent city' if in_colony else 'colony'}",
                "Done" if v[2] >= v[1] else f"{v[2]} set aside, {stock_loads(g, gid)} in stock")
    if t == 16:
        return f"Hippodrome {v[0]} stades long", "No Hippodrome"
    return NAMES[t] if 0 <= t < len(NAMES) else f"goal type {t}", ""
