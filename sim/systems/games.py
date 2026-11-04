"""Panhellenic games (docs/logic/games.md): the yearly games of Zeus, the only sandbox source of the Athlete (4) and
Scholar (9) commemorative monuments.

Games record 0x00FE6908: +0 host (won the last Olympian Games: this Olympian year is played at home), +4 result
(0 lost, 1 second, 2 won), +8 season (UI only). Year type t = year & 3 (year + 1 from month 8 on):
0 Olympian (all disciplines), 1 Isthmian (philosophy), 2 Nemean (athletics), 3 Pythian (drama).

- FUN_00565950, at the month change into June (month 5), Zeus only, when the scenario's games offset 0x00902C50 is
  not -1 and year >= start + offset (open-play sandbox: 0): FUN_00565A80 qualifies -> events 35 (begin, now) and
  37 (conclude, at the end of August, month 7); else event 36 (cannot participate, now).
- 35 begin 0x0046E1A0: message, contestants leave (FUN_00565B30; home games FUN_00566290), result drawn (FUN_00565E90).
- 36 cannot 0x0046E400: message; host = result = 0.
- 37 conclude 0x0046E5A0: message (won/second/lost), "won a game" flag 0x00FEB418 (Hercules), then FUN_00565FC0:
  won -> Olympian: host = 1 (home games won: games_victory_rewards); monument 4 (t 0, 2) or 9 (t 1, 3);
  attitude to the world cities (FUN_00566760); not won in an Olympian year -> host = 0; contestants come home.
Contestants are figures 0x38 (fig_handler_contestant 0x004C30D0, speed code 6): they wait their timer hidden, then
walk over land (route mode 0) and are removed on arrival. Role "contestant" here (w.task = the discipline's
building key, Figure +0x0B, picks its sprite); w.state "wait<action>" while hidden, then "go":
6 to the map entry or the land exit (random), 8 from where they are back to their building, 10 to the stadium.
"""
from . import walkers, commemorative
from .. import messages

TABLE = {0: (77, 79, 80, 78), 1: (77,), 2: (79, 80), 3: (78,)}   # 0x00641E80: building types per year type
TYPE_KEY = {77: "college", 78: "drama_school", 79: "gymnasium", 80: "stadium", 81: "podium", 82: "theatre"}
NAMES = ("Olympian", "Isthmian", "Nemean", "Pythian")
OFFSET = 0          # 0x00902C50 of the open-play sandbox (oracle dumps rotation-walls / -cliffs); -1 = no games
APOLLO_BONUS = 20   # FUN_00565D40: Apollo's sanctuary active (god record 3, 0x00EF5E74)
# message 0xE0 phrase ids (title; announcement = title + 1, conclude: + 1 won, + 2 second, + 3 lost), per year type
BEGIN = (0x4B0, 0x488, 0x474, 0x49C)           # home games: 0x4C4
CANNOT = (0x4B6, 0x48E, 0x47A, 0x4A2)          # home games cancelled: 0x4CA
CONCLUDE = (0x4BC, 0x494, 0x480, 0x4A8)        # home games: 0x4D0
# FUN_00566760: the history phrase by the games (olympian, isthmian, nemean, pythian *_won_history)
WIN_HISTORY = (0xD80, 0xD7E, 0xD7D, 0xD7F)


def state(g):
    s = g.sd("games", None)
    if not s:                                  # (an empty dict: saves where sim/heroes' games_won ran first, < 10-29)
        s = g.games = dict(host=0, result=0, season=0, won_ever=0, conclude=None, last=None)
    return s


def year_type(g, year=None, month=None):
    """(year + 1 if month > 7) & 3 (two's complement, as the exe's signed year)."""
    y = g.year if year is None else year
    m = g.month if month is None else month
    return (y + 1 if m > 7 else y) & 3


def staffed(g):
    """0x00782888[type]: alive buildings with workers > 0 (buildings_count_by_type 0x00491820)."""
    n = dict.fromkeys(TYPE_KEY, 0)
    rev = {k: t for t, k in TYPE_KEY.items()}
    for b in g.buildings.values():
        t = rev.get(b.key)
        if t is not None and b.employees > 0:
            n[t] += 1
    return n


def coverage(g):
    """FUN_00566A90 (cycle step 33): % of the house population whose house has philosophy / athletics / drama
    coverage (Building +0x6D / +0x6F / +0x71)."""
    from . import housing
    tot = ph = at = dr = 0
    for h in housing.houses(g):
        p = h.occupants
        if not p:
            continue
        tot += p
        c = h.coverage
        ph += p if c.get("philosophy") else 0
        at += p if c.get("athletics") else 0
        dr += p if c.get("drama") else 0
    if not tot:
        return 0, 0, 0
    return ph * 100 // tot, at * 100 // tot, dr * 100 // tot


def apollo_active(g):
    """god_sanctuary_active 0x004E9440 on god record 3 (Apollo): the sanctuary stands and its activity
    counter (+0x32) is not 0."""
    return any(b.key == "sanctuary_apollo" and b.misc.get("activity", 0) for b in g.buildings.values())


def chance(g, t):
    """FUN_00565D40(t): S1 philosophy = cov/4 + colleges + podiums; S2 athletics = cov/4 + 5 stadiums + gymnasiums;
    S3 drama = cov/4 + drama schools + theatres; Olympian (S1 + S2 + S3)/3 + 4 stadiums; + 20 with Apollo.
    begin() then applies FUN_00565E30 (sim/heroes games_chance: Hercules' hall, his games requirement unmet:
    chance^2 * 0.16)."""
    n = staffed(g)
    cph, cat, cdr = coverage(g)
    s1 = cph // 4 + n[77] + n[81]
    s2 = cat // 4 + 5 * n[80] + n[79]
    s3 = cdr // 4 + n[78] + n[82]
    a = APOLLO_BONUS if apollo_active(g) else 0
    return (a + (s3 + s2 + s1) // 3 + 4 * n[80], s1 + a, s2 + a, s3 + a)[t]


def qualifies(g, t):
    """FUN_00565A80: home games need a staffed stadium; else per year type: Olympian any of the four venues,
    Isthmian a college, Nemean a gymnasium or a stadium, Pythian a drama school (all staffed)."""
    n = staffed(g)
    if t == 0 and state(g)["host"]:
        return n[80] != 0
    return {0: n[78] + n[79] + n[80] + n[77], 1: n[77], 2: n[79] + n[80], 3: n[78]}[t] > 0


def stadium(g):
    """FUN_00568700(1, &b, 0x50, flags 0xB): the first alive, staffed stadium (lowest id)."""
    for bid in sorted(g.buildings):
        b = g.buildings[bid]
        if b.key == "stadium" and b.employees > 0 and b.access is not None:
            return b
    return None


def sources(g, t):
    """Alive, staffed buildings of the year type's table row, in building order (FUN_00565B30 loop)."""
    keys = {TYPE_KEY[x] for x in TABLE[t]}
    return [g.buildings[i] for i in sorted(g.buildings)
            if g.buildings[i].key in keys and g.buildings[i].employees > 0 and g.buildings[i].access is not None]


# --- the month hook --------------------------------------------------------------------------------------

def month(g):
    """At the month change (our month_start: g.month = the new month). The exe runs scenario_events_monthly with
    the old month, then month += 1, then FUN_00565950 when the new month is 5."""
    s = state(g)
    if s["conclude"] is not None and g.month == 8 and s["conclude"] == g.year:   # event 37 (month 7) fires
        s["conclude"] = None
        conclude(g)
    off = g.__dict__.get("games_year", OFFSET)            # an episode's +0x328 (sim/episode.py), from its
    y0 = g.__dict__.get("scenario_year", g.start_year)     # scenario_start_year (FUN_00565950)
    if g.month == 5 and off != -1 and g.year >= y0 + off:
        t = year_type(g)
        if qualifies(g, t):
            s["conclude"] = g.year
            begin(g, t)
        else:
            cannot(g, t)


def begin(g, t):
    """Event 35, 0x0046E1A0 (stinger S_games); then FUN_00565B30 and FUN_00565E90."""
    s = state(g)
    home = t == 0 and s["host"]
    title = 0x4C4 if home else BEGIN[t]
    messages.post(g, title, title + 1, meta=dict(stinger="games"))   # FUN_005A1210(7): S_games
    s["season"] = 1                                       # FUN_00565B30 +8
    if home:
        home_begin(g)
    else:
        for b in sources(g, t):                           # one contestant per building, action 6
            _spawn(g, b.id, b.access, 6, 2 * (g.rng.randrange(1 << 15) & 0x1F), b.key)
    c = chance(g, t)                                      # FUN_00565E90
    try:                                                  # FUN_00565E30: Hercules' hall (sim/heroes)
        from .. import heroes
        c = heroes.games_chance(g, c)
    except ImportError:
        pass
    r = g.rng.randrange(1 << 15) % 100
    s["result"] = 2 if r < c else 0 if c < 30 else 1
    s["last"] = dict(year=g.year, type=t, home=bool(home), chance=c, roll=r, result=s["result"])


def cannot(g, t):
    """Event 36, 0x0046E400: home games cancelled (no staffed stadium) or can't participate; host = result = 0."""
    s = state(g)
    title = 0x4CA if t == 0 and s["host"] else CANNOT[t]
    messages.post(g, title, title + 1)
    s["host"] = s["result"] = 0


def conclude(g):
    """Event 37, 0x0046E5A0, then FUN_00565FC0 (at month 7: year type of this year)."""
    s = state(g)
    t = year_type(g, g.year, 7)
    home = t == 0 and bool(s["host"])
    res = s["result"]
    title = 0x4D0 if home else CONCLUDE[t]
    messages.post(g, title, title + 3 - res)              # won / second / lost (the won text names the monument)
    if res == 2:
        s["won_ever"] = 1                                 # 0x00FEB418 (Hercules' requirement 6)
    # FUN_00565FC0
    s["season"] = 0
    hosting = home                                       # cVar5: the host flag as it was
    if res == 2:
        if t == 0:
            if s["host"]:
                victory_rewards(g)                        # games_victory_rewards 0x005666D0
            s["host"] = 1
        v = 4 if t in (0, 2) else 9
        commemorative.grant(g, v)
        attitude(g, t == 0, t)                            # FUN_00566760
    elif t == 0:
        s["host"] = 0
    if hosting:
        home_conclude(g)                                  # FUN_005664F0
        return
    ex, ey = g.world.exit                                 # contestants of the staffed buildings come home
    for b in sources(g, t):
        _spawn(g, b.id, (ex, ey), 8, 2 * (g.rng.randrange(1 << 15) & 0x1F), b.key)


def attitude(g, olympian, t):
    """FUN_00566760: every in-use, active, visible city: ally / rival +5, vassal / parent / colony +10 (+10 more in
    an Olympian year), with a history line (0xD7D..0xD80)."""
    e = getattr(g, "empire", None)
    if e is None:
        return
    from ..empire import relations
    for c in e.cities.values():
        if not (c.active and c.visible):
            continue
        k = c.cls()
        if k in ("ally", "rival"):
            d = 5
        elif k in ("vassal", "parent", "colony"):
            d = 10
        else:
            continue
        relations.attitude_add(g, c, d + (10 if olympian else 0), WIN_HISTORY[t])


def victory_rewards(g):
    """games_victory_rewards 0x005666D0 (home games won): every in-use, active city of class 0..4 +20 attitude
    (history 0xD81), city sentiment +15 (not clamped)."""
    e = getattr(g, "empire", None)
    if e is not None:
        from ..empire import relations
        for c in e.cities.values():
            if c.active and c.cls() in ("ally", "vassal", "rival", "parent", "colony"):
                relations.attitude_add(g, c, 20, 0xD81)          # home_games_conclude_..._history
    g.city.sentiment += 15


def home_begin(g):
    """FUN_00566290: local contestants walk to the stadium (action 10, timer 0); 10 visitors per discipline of the
    Olympian row come from the map entry or the land exit (random) to the stadium (timer 49 i + 11 k)."""
    for b in sources(g, 0):
        _spawn(g, b.id, b.access, 10, 0, b.key)
    for k, typ in enumerate(TABLE[0]):
        for i in range(10):
            at = g.world.exit if g.rng.randrange(1 << 15) & 1 else g.world.entry
            _spawn(g, 0, tuple(at), 10, i * 0x31 + k * 0xB, TYPE_KEY[typ])


def home_conclude(g):
    """FUN_005664F0 (only with a staffed stadium): local contestants walk home from the stadium (action 8, timer
    79 per table index), the visitors leave (action 6, timer 29 k + 50 i)."""
    st = stadium(g)
    if st is None:
        return
    for b in sources(g, 0):
        idx = [TYPE_KEY[x] for x in TABLE[0]].index(b.key)
        _spawn(g, b.id, st.access, 8, idx * 0x4F, b.key)
    for k, typ in enumerate(TABLE[0]):
        for i in range(10):
            _spawn(g, 0, st.access, 6, k * 0x1D + i * 0x32, TYPE_KEY[typ])


# --- contestants (figure 0x38) ---------------------------------------------------------------------------

def _spawn(g, home, at, action, timer, kind):
    w = walkers.new_walker(g, role="contestant", home=home, x=at[0], y=at[1], state=f"wait{action}", task=kind)
    walkers.add(g, w, timer + 1)


def _route(g, w, goal):
    """Route mode 0 (people over land; land_path over walkers.walkable)."""
    return walkers.land_path(g, (w.x, w.y), {tuple(goal)}, max_dist=walkers.ROUTE_MAX)


def contestant(g, w):
    """fig_handler_contestant 0x004C30D0."""
    if w.state.startswith("wait"):                       # timer over: pick the destination
        a = int(w.state[4:])
        if a == 6:
            goal = g.world.entry if g.rng.randrange(1 << 15) & 1 == 0 else g.world.exit
        elif a == 8:
            b = g.buildings.get(w.home)
            goal = b.access if b is not None else None
        else:                                            # 10: to the first staffed stadium, or gone
            st = stadium(g)
            goal = st.access if st is not None else None
        if goal is None:
            return walkers.remove(g, w)
        w.target_tile, w.state = tuple(goal), "go"
        w.path = _route(g, w, goal) or []
        if not w.path and (w.x, w.y) != w.target_tile:
            return walkers.schedule(g, w, 51)            # no route (direction 9): try again
    if w.path:
        walkers.step_to(g, w, w.path.pop(0))
        return walkers.schedule(g, w, walkers.tile_delay(g, w))
    if (w.x, w.y) == w.target_tile:                      # arrived (direction 8): removed
        return walkers.remove(g, w)
    w.path = _route(g, w, w.target_tile) or []           # a building or wall appeared on the way: route again
    return walkers.schedule(g, w, 51 if not w.path else 1)


def look(g, w):
    """Waiting contestants are hidden (Figure +0x65 while the timer runs)."""
    if w.role == "contestant" and w.state.startswith("wait"):
        return ["hidden", 0, 0, 0, 0, 0, 0, 0, "", False]
    return None
