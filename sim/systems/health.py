"""City health and plague (docs/logic/services.md §5).

Month start: health target = population-weighted (50 if the house has healer coverage + 50 if it
ate last month), plus a bonus for small cities. Daily: health moves 1 toward the target. Daily
plague check (month_advance is per cycle = our day): chance per 10000 from the health table,
at most ceil(chance*384/10000) outbreaks in two years, half of that per year, one per month.
An outbreak infects half of the 2/5 least-covered inhabited houses: each loses a share of its
residents (difficulty table) and is infected for 32 days; 3 plagued walkers roam from it. They have no
service effect; one is removed when it shares a tile with a healer or watchman (figure_tile_contact ->
plagued_walker_meet 0x00448450), and they walk through roadblocks (0x004A31E0).
An infected house takes no one (room 0, house_room_update 0x004860A0; immigrants/homeless arriving are lost).
Year start: births or deaths by health (population_births_deaths 0x00566D40).
"""
import weakref

from . import walkers, index

SMALL_CITY_BONUS = [(100, 80), (200, 80), (300, 70), (400, 60), (500, 50), (600, 40), (700, 30), (800, 20),
                    (900, 10), (1000, 0)]
PLAGUE_CHANCE = [(10, 300), (20, 250), (30, 200), (45, 100), (60, 50), (75, 25), (100, 0)]
DEATHS = {"VeryEasy": 0.25, "Easy": 1 / 3, "Normal": 0.5, "Hard": 2 / 3, "Impossible": 1.0}
INFECTED_DAYS = 32


def _st(g):
    st = getattr(g, "health_state", None)
    if st is None:
        st = g.health_state = dict(health=80, target=80, this_year=0, last_year=0, this_month=0)
    return st


def month_start(g):
    st = _st(g)
    st["this_month"] = 0
    P = W = 0
    for b in index.of(g, "house"):
        if b.kind != "house" or not b.occupants:
            continue
        w = (50 if b.coverage.get("healer", 0) > 0 else 0) + (50 if b.fed else 0)
        P += b.occupants
        W += b.occupants * w
    h = W // P if P else 0
    bonus = next((v for p, v in SMALL_CITY_BONUS if g.city.population < p), 0)
    st["target"] = max(0, min(100, h + bonus))
    if g.month == 0:
        st["last_year"], st["this_year"] = st["this_year"], 0


_T19 = None


def _text19(i):
    """Text group 19 line i (extracted/text/zeus_text.json, tools/engtext.py); "" without the file."""
    global _T19
    if _T19 is None:
        import json
        import os
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        try:
            _T19 = json.load(open(os.path.join(root, "extracted", "text", "zeus_text.json"))).get("19", [])
        except (OSError, ValueError):
            _T19 = []
    return _T19[i].strip() if i < len(_T19) else ""


def health_message(g, old, up):
    """FUN_005246B0, after each step of city_health_step 0x00566B90 (old = the health before it): the short message
    (FUN_005231E0, text group 19) when the health crosses a tens boundary in a city of 301+ people:
    down: 19:147 + (health - 1) / 10 ("Hygiene appalling, plague imminent" .. "Hygiene is deteriorating"; 147
    at 0), and below 20 on every step down whatever the size; up: 19:157 + (health - 1) / 10 ("Hygiene is
    better, plague still likely" .. "Hygiene is perfect!"), none below 10."""
    from ..messages import Msg
    h, pop = _st(g)["health"], g.city.population
    if not up:
        if (old // 10 == h // 10 or pop < 301) and h > 19:
            return
        k = 147 if h == 0 else (h - 1) // 10 + 147
    else:
        if old // 10 == h // 10 or pop < 301 or h < 10:
            return
        k = (h - 1) // 10 + 157
    g.message(Msg(_text19(k) or f"health {h}", dict(text19=k)))


def plague_countdown(g):
    """Cycle step 6, houses_plague_countdown 0x004483F0: an infected house's countdown - 1."""
    for b in index.of(g, "house"):
        inf = b.misc.get("infected") if b.kind == "house" else 0
        if inf:
            b.misc["infected"] = inf - 1


def update(g):
    """month_advance 0x00483C10 (after step 50): health step, plague roll (the countdown: plague_countdown)."""
    st = _st(g)
    h, t = st["health"], st["target"]
    st["health"] = max(0, min(100, h + (t > h) - (t < h)))
    if t != h:
        health_message(g, h, t > h)
    chance = next((c for th, c in PLAGUE_CHANCE if th > st["health"]), 0)
    if not chance:
        return
    cap = -(-chance * 384 // 10000)
    if cap <= st["this_year"] + st["last_year"] or st["this_month"] or -(-cap // 2) <= st["this_year"]:
        return
    if g.rng.randrange(10000) < chance:
        outbreak(g)


def outbreak(g, cause=None):
    from .. import alerts
    st = _st(g)
    st["this_month"] += 1
    st["this_year"] += 1
    hs = [b for b in index.of(g, "house") if b.occupants]
    n = len(hs) * 2 // 5
    key = lambda b: (20 if b.fed else 0) + min(255, b.coverage.get("healer", 0))
    cand = sorted(hs, key=lambda b: (key(b), b.id))[:n]
    need = n // 2
    frac = DEATHS.get(g.rules.get("difficulty", "Normal"), 0.5)
    dead, src = 0, None
    for i, b in enumerate(cand):
        if need <= 0:
            break
        if len(cand) - i <= need or g.rng.randrange(2) == 0:
            need -= 1
            # plague_infect_houses: alert 8 ("go to source of plague"), raised by the first house, the others add
            (alerts.raise_alert if need == n // 2 - 1 else alerts.add)(g, alerts.PLAGUE, (b.x, b.y))
            src = src or b
            d = int(b.occupants * frac)
            b.occupants -= d
            g.city.population -= d
            dead += d
            b.misc["infected"] = INFECTED_DAYS
            if b.access:
                for _ in range(3):
                    walkers.spawn_roamer(g, b, "plagued")
    # cause: ours, CLI text (playtest haiku-2 #10: Apollo's plague at health 82 looked causeless; at 75+ the random
    # check never fires, plague_check 0x00447FF0)
    # plague_messages: FUN_00521A70(0xDC, the source building's type, its tile): the window's go-to button
    text = f"plague! {dead} people died (health {st['health']}" + (f"; {cause})" if cause else ")")
    from ..messages import Msg
    g.message(Msg(text, dict(at=[src.x, src.y], kind=0xDC)) if src is not None else text)
    st["deaths"] = st.get("deaths", 0) + dead


MEETS = ("healer", "watchman")          # figure types 0x20, 0x3D (0x26 too: no counterpart in ours)


_BY_ROLE = weakref.WeakKeyDictionary()     # game -> (key, plagued walkers, healers/watchmen): not game state


def _contact_lists(g):
    """The plagued walkers and the healers/watchmen, in g.walkers order, kept until a walker is created (roles
    never change; removed ones are skipped on use)."""
    key = (g.next_wid, id(g.walkers))
    c = _BY_ROLE.get(g)
    if c is None or c[0] != key:
        ws = g.walkers.values()
        c = _BY_ROLE[g] = (key, [o for o in ws if o.role == "plagued"], [o for o in ws if o.role in MEETS])
    return c


def contact(g, w):
    """w just stepped onto its tile: a plagued walker and a healer/watchman sharing it -> the plagued one is
    removed (0x00448450, checked in both directions by figure_tile_contact 0x004D4DA0)."""
    here = (w.x, w.y)
    _, plagued, meets = _contact_lists(g)
    ws = g.walkers
    if w.role == "plagued":
        if any((o.x, o.y) == here and ws.get(o.id) is o for o in meets):
            walkers.remove(g, w)
        return
    for o in [o for o in plagued if (o.x, o.y) == here and ws.get(o.id) is o]:
        walkers.remove(g, o)


def sanctuary_done(g, god):
    """god_sanctuary_active 0x004E9440: the god's sanctuary is active (a sacrifice in the last months; sim/gods)
    (Hera: +3 births, Aphrodite: no emigration, Dionysus: crime)."""
    from .. import gods
    return gods.active(g, god)


BIRTHS = [(90, 6), (80, 4), (70, 3), (60, 2), (50, 1), (40, 0)]   # health > threshold -> % (0x00566D40)


def year_start(g):
    """population_births_deaths 0x00566D40 (population.md (d)), once at the year rollover:
    p = 6/4/3/2/1/0 % for health > 90/80/70/60/50/40; below that -1 if the health TARGET > 30 (exe quirk),
    else -2/-3/-5 for health > 20/10/0. Hera's finished sanctuary +3. Births (house_births 0x00486EF0) fill
    inhabited common houses with road access up to capacity, deaths (house_deaths 0x00487020) empty common
    houses, each from its own rotating cursor over building ids."""
    st = _st(g)
    h, t = st["health"], st["target"]
    p = next((v for th, v in BIRTHS if h > th), None)
    if p is None:
        p = -1 if t > 30 else -2 if h > 20 else -3 if h > 10 else -5 if h > 0 else 0
    if sanctuary_done(g, "hera"):
        p += 3
    pop = g.city.population
    if p > 0:
        n = _spread(g, pop * p // 100, "births_cursor", lambda b: b.access is not None and b.occupants > 0, +1)
        st["births"] = st.get("births", 0) + n
        if n:
            g.message(f"{n} births this year (health {h})")
    elif p < 0:
        n = _spread(g, pop * -p // 100, "deaths_cursor", lambda b: True, -1)
        st["deaths"] = st.get("deaths", 0) + n
        if n:
            g.message(f"{n} deaths this year (health {h})")


def house_deaths(g, n):
    """house_deaths 0x00487020(n, 0): n people die from common houses, from the rotating deaths cursor; returns
    how many (population_sub included). Callers: the yearly deaths above, a fallen rabble soldier (sim/military)."""
    return _spread(g, n, "deaths_cursor", lambda b: True, -1)


def _spread(g, n, cursor, ok, sign):
    from . import housing
    hs = sorted((b for b in index.of(g, "house") if b.kind == "house" and b.level < 7 and ok(b)), key=lambda b: b.id)
    if not hs or n <= 0:
        return 0
    cur = g.sd(cursor, 0)
    start = next((i for i, b in enumerate(hs) if b.id > cur), 0)
    done = 0
    for b in hs[start:] + hs[:start]:
        if n <= 0:
            break
        k = min(n, housing.capacity(g, b) - b.occupants) if sign > 0 else min(n, b.occupants)
        k = max(0, k)
        b.occupants += sign * k
        n -= k
        done += k
        setattr(g, cursor, b.id)
    g.city.population += sign * done
    return done
