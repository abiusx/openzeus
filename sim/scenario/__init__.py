"""The scenario event engine (docs/logic/events.md "Ours"): the adventure episode's scheduled events, run monthly as
`scenario_events_monthly` 0x0046D380 does, with one registered handler per event type.

The core calls only:
  new_game(g)       Game.__init__: g.scenario from data/scenario/<map>.json (None when the map has no episode)
  month(g)          systems.run_day at our month change (after empire.day): the invasions pass (type 2), the
                    monthly pass, the recurring re-arm
  command(g, op, a) Game.command: `scenario [log|on|off]`; None when op is not ours
  export(g)         what the viewer may show (live records)
Other tracks: register(type_, fn, owner) + the helpers below; add the module to PLUGINS.
"""
import copy
import importlib
import json
import os

from .model import Scenario

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data", "scenario")
VERBS = ("scenario",)
# modules that register handlers (imported before the first pass): one line per track
PLUGINS = ["sim.scenario.gift", "sim.heroes.events", "sim.gods.invasion", "sim.empire.status_events",
           "sim.empire.quota_events", "sim.empire.city_events", "sim.empire.invasion_events",
           "sim.empire.requests", "sim.disasters"]

# flags (ScenarioEvent +0x28)
TEMPLATE, RECURRING, DONE, CHAINED, WARN, WARNED, DYNAMIC, DISABLED = 1, 2, 4, 8, 0x40, 0x80, 0x100, 0x20000
MAX_EVENTS = 0x8C                                  # events_alloc 0x00467A40: 140 records
# event type table 0x00632700 + type*20 (Zeus.exe): has a city = byte +0x10 and not +0x11 (FUN_004681C0);
# carries a good = +0x13 (event_has_goods_item 0x00468DA0); item range [int +0x18, int +0x1C) (FUN_00468DB0/DC0)
_CITY = {1, 4, 6, 7, 8, 9, 13, 14, 17, 18, 19, 20, 21, 22, 23, 29, 30, 31, 32, 33, 34}
_GOODS = {1, 4, 13, 14, 15, 16, 21, 22, 23, 29, 30, 32, 33}
_ITEM_RANGE = {1: (1, 27), 4: (0, 27), 13: (1, 23), 14: (1, 23), 15: (1, 23), 16: (1, 23), 21: (1, 23), 22: (1, 23),
               23: (1, 27), 29: (1, 27), 30: (1, 27), 32: (1, 27), 33: (1, 27)}
TYPE_NAMES = {0: "Free Event", 1: "Request", 2: "Invasion", 3: "Earthquake", 4: "Quest", 5: "Landslide",
              6: "Sea trade problem", 7: "Land trade problem", 8: "Wage increase", 9: "Wage decrease",
              10: "Contaminated water", 11: "Copper mine collapse", 12: "Clay pit flood", 13: "Demand increase",
              14: "Demand decrease", 15: "Price increase", 16: "Price decrease", 17: "Favor increase",
              18: "Favor decrease", 19: "City status change", 20: "Rival army away", 21: "Supply increase",
              22: "Supply decrease", 23: "Gift", 24: "Lava flow", 25: "Tidal wave", 26: "Monster invasion",
              27: "God invasion", 28: "Sink land"}

HANDLERS = {}        # type -> (fn, owner)
_ctx = {"loop": -1, "now": None, "plugins": False, "episode_end": False}


# --- registration ------------------------------------------------------------------------------------------

def register(type_, fn, owner="", replace=False):
    """fn(g, ev) runs once per monthly pass for every live (non-template) record of this type."""
    if type_ in HANDLERS and not replace and HANDLERS[type_][0] is not fn:
        raise ValueError(f"event type {type_} already has a handler ({HANDLERS[type_][1]})")
    HANDLERS[type_] = (fn, owner)


def _plugins():
    if not _ctx["plugins"]:
        _ctx["plugins"] = True
        for m in PLUGINS:
            importlib.import_module(m)


# --- loading and resolving ---------------------------------------------------------------------------------

def available(map_name):
    return os.path.exists(os.path.join(DATA, f"{map_name}.json"))


def new_game(g, episode=None):
    """episode: an episode record (docs/campaign-format.md "episodes"; sim/episode.py) instead of the map's
    data/scenario/<map>.json."""
    g.scenario_v = 1
    if episode is not None:
        g.scenario = from_episode(g, episode)
    else:
        g.scenario = load(g) if available(g.map_name) else None
    request_list_rebuild(g)                         # episode_start_load / city_init_from_map
    if g.scenario is not None and any(ev["type"] == 5 for ev in g.scenario.events):
        from ..disasters import landslide           # city_init_from_map's FUN_00506BC0: the landslide sites
        landslide.new_game(g)


def load(g):
    d = json.load(open(os.path.join(DATA, f"{g.map_name}.json")))
    return build(g, d["source"], d["scenario"], d["gods"], d["events"])


def from_episode(g, ep):
    """g.scenario from an episode record: its scenario values, god block and events."""
    return build(g, ep.get("source", ""), dict(start_year=ep["start_year"], funds=ep["funds"]), ep["gods"],
                 ep["events"])


def build(g, source, info, gods_, records):
    evs = []
    for r in records:
        ev = blank(r["index"])
        ev.update({k: copy.deepcopy(v) for k, v in r.items() if k not in ("index", "name")})
        evs.append(ev)
    sc = Scenario(source, info, copy.deepcopy(gods_), evs, getattr(g, "seed", 1))
    for ev in evs:                                # episode_start_load 0x00420390: each record resolved in order
        resolve_at_start(sc, ev, g)
    return sc


def rebase(g):
    """event_rebase_month 0x00467930, episode_start_load's colony and continue starts: every record that is not a
    template or disabled (flags & 0x20001) moves by the current month: month += month; above 11: year + 1 and
    month - 11 (sic: the exe's quirk, 12 -> 1, not 0). The exe's event years count from scenario_start_year, which
    those starts set to the current year; ours count from the game's first year (Game.start_year), so the years
    move by the current year's offset as well (the same due dates)."""
    y, m = g.month_index // 12, g.month
    for ev in g.scenario.events:
        if ev["flags"] & (TEMPLATE | DISABLED):
            continue
        ev["year"] += y
        ev["month"] += m
        if ev["month"] > 11:
            ev["year"] += 1
            ev["month"] -= 11


def blank(i):
    """event_init_defaults 0x00467590 (as far as we keep fields): recurring, no chain."""
    return dict(id=i, type=0, month=0, flags=RECURRING, chain=-1, lead=0,
                groups={k: [0, -1, -1, -1] for k in ("item", "amount", "year", "city", "city2")},
                item=0, amount=0, year=0, city=0, city2=0, countdown=0, state=0, active=0, b33=0, parent=-1,
                b36=0, b37=0, b38=0, b3a=0, b3c=0, b3e=0, kind=0, b61=0, b62=0, b63=0, src=-1, pitem=0, pamount=0,
                b74=0, quest=0, raw="")


def rng15(g):
    return _rng15(g.scenario)


def _rng15(sc):
    return sc.rng.randrange(32768)


def value_resolve(sc, grp):
    """event_value_resolve 0x004673C0 on [value, a, b, c]: a >= 0, b < 0 -> a; a, b >= 0 -> one of a, b (, c);
    a < 0 -> random in [b, c] (quirk: b == c >= 0 -> value = a)."""
    v, a, b, c = grp
    if a < 0:
        if b >= 0 and c >= 0 and b == c:
            grp[0] = a
            return a
        n = c - b + 1
        r = _rng15(sc)
        grp[0] = (r % abs(n) if n else 0) + b          # n <= 0: not in the shipped files (the exe divides by it)
    elif b < 0:
        grp[0] = a
    else:
        k = _rng15(sc) % (3 if c >= 0 else 2)
        grp[0] = (a, b, c)[k]
    return grp[0]


def resolve_at_start(sc, ev, g=None):
    """event_resolve_at_start 0x00467660: resolve the value groups, reset the run-time fields, 2 more draws.
    Type 2 with a sea point (+0x1C > 8): the landing point +0x78 = FUN_00503EC0 (rng_15 % the existing landing
    points; ours: the scenario's RNG). Not ported: the earthquake points (type 3)."""
    ev["flags"] &= ~0x40EC4
    gr = ev["groups"]
    for k in ("item", "amount", "year", "city", "city2"):
        ev[k] = value_resolve(sc, gr[k])
    ev.update(b74=0, countdown=ev["month"] + ev["year"], state=0, active=0, b33=0, parent=-1, src=-1, b63=0)
    if ev.get("warned_bits"):                         # +0x57 = 0 (an invasion's warnings, sim/empire/invasion_events)
        ev["warned_bits"] = 0
    if ev["type"] == 2:
        ev["landing"] = 0
        if ev["city"] > 8 and g is not None:
            from ..military import navy
            n = sum(1 for x in navy.sea_points(g)[1] if x)
            if n:
                ev["landing"] = _rng15(sc) % n
    ev["b61"] = _rng15(sc) % 5 + 4
    ev["b62"] = _rng15(sc) & 1


# --- dates -------------------------------------------------------------------------------------------------

def today(g):
    """(year offset from the start, month 0..11) as the exe's globals read: inside the monthly pass the month that
    just ended (scenario_events_monthly runs before month += 1), otherwise the current month."""
    if _ctx["now"] is not None:
        return _ctx["now"]
    return g.month_index // 12, g.month


def due(g, ev, any_flags=False):
    """events_date_check 0x00471F00."""
    f = ev["flags"]
    if f & DISABLED:
        return _ctx["episode_end"]                     # DAT_0091BCBB: 1 only during episode_end (wm_sub_471E90)
    if not any_flags and f & (DISABLED | DONE | TEMPLATE):
        return False
    y, m = today(g)
    return ev["year"] == y and ev["month"] == m


def months_until_due(g, ev):
    """event_months_until_due 0x00472000."""
    y, m = today(g)
    return ev["lead"] + (ev["year"] - y) * 12 + ev["month"] - m


def done(g, ev):
    ev["flags"] |= DONE


def events(g, type_=None):
    sc = getattr(g, "scenario", None)
    if sc is None:
        return []
    return [ev for ev in sc.events if type_ is None or ev["type"] == type_]


def get(g, i):
    """FUN_0046D900: the record by index, None when out of range."""
    sc = getattr(g, "scenario", None)
    if sc is None or i is None or i < 0 or i >= len(sc.events):
        return None
    return sc.events[i]


def gods(g):
    sc = getattr(g, "scenario", None)
    return sc.gods if sc else None


def good(ev):
    """Our good key for the record's item (new goods numbering, sim/empire/model.py GOOD_IDS)."""
    from sim.empire.model import GOOD_IDS
    return {v: k for k, v in GOOD_IDS.items()}.get(ev["item"])


def log(g, text):
    sc = g.scenario
    sc.log.append((g.month_index, text))
    del sc.log[:-300]


def post(g, title, body, ev=None, city=None, **vars):
    """A message by the exe's phrase ids (sim/messages.py): [amount], [item], [itemshort] ... from vars."""
    from sim import messages
    vars = {k: str(v) for k, v in vars.items()}
    try:
        messages.post(g, title, body, city=city, **vars)
    except TypeError:                                  # sim/messages.py before it took extra variables
        s = messages.line(title, body, city=city)
        for k, v in vars.items():
            s = s.replace(f"[{k}]", v)
        g.message(s)


# --- the monthly pass --------------------------------------------------------------------------------------

def dispatch(g, ev):
    """month_events_dispatch 0x0046DFD0 (and invasion_event_month for type 2)."""
    _plugins()
    h = HANDLERS.get(ev["type"])
    if h is None:
        sc = g.scenario
        if ev["id"] not in sc.noted:
            sc.noted.add(ev["id"])
            log(g, f"event #{ev['id']} type {ev['type']} ({TYPE_NAMES.get(ev['type'], '?')}): no handler")
        return
    h[0](g, ev)


def invasions(g):
    """The scenario part of invasions_month_update 0x00504A30: type-2 records (handler registered by 1B)."""
    for ev in list(g.scenario.events):
        if ev["type"] == 2 and not ev["flags"] & (TEMPLATE | DISABLED):
            dispatch(g, ev)


def month(g):
    """At our month change: invasions (type 2), scenario_events_monthly 0x0046D380, request_list_rebuild,
    events_rearm_recurring."""
    sc = getattr(g, "scenario", None)
    if g.day == 0 or g.day % g.rules["days_per_month"]:
        return
    from .. import empire
    if sc is None:                                 # the empire's requests (sim/empire/events) are on the list too
        empire.month_events(g)
        request_list_rebuild(g)
        return
    _plugins()
    mi = g.month_index - 1
    _ctx["now"] = (mi // 12, mi % 12)
    try:
        invasions(g)
        i = 0
        while i < len(sc.events):                      # records chained during the pass are reached too
            ev = sc.events[i]
            if not ev["flags"] & TEMPLATE and ev["type"] != 2:
                _ctx["loop"] = i
                if due(g, ev):                         # ours: the timeline (tools/scenario_events.py ours)
                    log(g, f"event #{i} ({TYPE_NAMES.get(ev['type'], '?')}) due")
                dispatch(g, ev)
            i += 1
        _ctx["loop"] = -1
        empire.month_events(g)                         # the empire's run-time records: after the episode's (bugs.md 360)
        request_list_rebuild(g)                        # FUN_00483040, after the dispatch, before the re-arm
        rearm(g)
    finally:
        _ctx["loop"], _ctx["now"] = -1, None


def episode_end(g):
    """wm_sub_471E90 (on Proceed after a victory, before episode_end_save_parent): a type-19 record (City status
    change) flagged DYNAMIC (0x100) and not DONE gets flags = 0x20000; then every record flagged 0x20000 ("at the end
    of the episode": the editor's disabled events, e.g. Zeus and Europa's cities that appear or become vassals for the
    next episode) is dispatched with DAT_0091BCBB = 1, which makes events_date_check 0x00471F00 call it due."""
    sc = getattr(g, "scenario", None)
    if sc is None:
        return 0
    _plugins()
    n = 0
    _ctx["episode_end"] = True
    try:
        for ev in list(sc.events):
            if ev["flags"] & DYNAMIC and ev["type"] == 19 and not ev["flags"] & DONE:
                ev["flags"] = DISABLED
            if ev["flags"] & DISABLED:
                dispatch(g, ev)
                n += 1
    finally:
        _ctx["episode_end"] = False
    return n


def rearm(g):
    """events_rearm_recurring 0x0046D660: done + recurring + not active -> re-resolved, `year = max(1, resolved)
    + today's year offset` (it comes again that many years later, same month)."""
    y = today(g)[0]
    for ev in g.scenario.events:
        if ev["flags"] & DONE and not ev["active"] and ev["flags"] & RECURRING:
            ev["flags"] &= ~DONE
            resolve_at_start(g.scenario, ev, g)
            ev["year"] = max(1, ev["year"]) + y
            log(g, f"event #{ev['id']} ({TYPE_NAMES.get(ev['type'], '?')}) re-armed: year +{ev['year']}, "
                   f"month {ev['month'] + 1}")


# --- chains ------------------------------------------------------------------------------------------------

def alloc(g, rec=None):
    """events_alloc 0x00467A40(0) + event_init_defaults: reuse a finished dynamic record (not dated today; type 2
    only when no army of it is out: not checked, we keep type 2 records), else append (at most 140); None when
    full. `rec` (optional): fields to set on it (a record created at run time, e.g. 0x27 hero arrival; give it
    flags yourself, e.g. DYNAMIC; the defaults are the editor's: RECURRING)."""
    sc = g.scenario
    ev = None
    for old in sc.events:
        if (old["flags"] & DYNAMIC and old["flags"] & DONE and not old["active"] and not due(g, old, True)
                and old["type"] != 2):
            ev = sc.events[old["id"]] = blank(old["id"])
            break
    if ev is None:
        if len(sc.events) >= MAX_EVENTS:
            log(g, "ERR Could not add event")
            return None
        ev = blank(len(sc.events))
        sc.events.append(ev)
    if rec:
        ev.update({k: v for k, v in rec.items() if k != "id"})
    return ev


def _span(grp):
    """The range a value must fall in to be kept (FUN_00472CC0 on the group): range b..c, or the single value."""
    v, a, b, c = grp
    if a < 0:
        return b, c
    return (a, a) if b < 0 else (-1, -1)


def _item_ok(child, item):
    """FUN_00469090: the parent's item fits the child's type (only the cases the open-play types reach)."""
    lo, hi = _ITEM_RANGE.get(child["type"], (0, 0))
    if not lo <= item < hi:
        return False
    if child["type"] in (13, 14, 15, 16, 21, 22):
        return item not in (15, 22)
    if child["type"] == 23:
        return item not in (15, 22, 24, 25, 26)       # FUN_00469050
    return child["type"] not in (1, 3, 4, 24, 25, 26, 27)     # those have their own checks (not ported)


def chain(g, parent, src=-1):
    """event_chain_trigger 0x0046DE00: parent["chain"] (a template) -> a new dynamic record; its resolved `year`
    is a delay in months from today; delay 0 -> dispatched at once (or later in this pass)."""
    tpl = get(g, parent["chain"])
    if tpl is None:
        return None
    ev = alloc(g)
    if ev is None:
        return None
    i = ev["id"]
    ev.update(copy.deepcopy(tpl))
    ev["id"] = i
    resolve_at_start(g.scenario, ev, g)
    ev["flags"] = DYNAMIC | CHAINED
    hc = ev["type"] in _CITY
    if hc == (parent["type"] in _CITY):
        lo, hi = _span(ev["groups"]["city"])
        if lo <= parent["city"] <= hi:
            ev["city"] = parent["city"]
    if ev["type"] in _GOODS and parent["type"] in _GOODS and _item_ok(ev, parent["item"]):
        lo, hi = _span(ev["groups"]["item"])
        if lo <= parent["item"] <= hi:
            ev["item"] = parent["item"]
    ev.update(src=src, parent=parent["id"], b63=parent["city"] if hc else 0, pamount=parent["amount"],
              pitem=parent["item"], b37=parent["b36"] & 0xFF)
    y, m = today(g)
    d = ev["year"]
    ev["month"] = (m + d) % 12
    ev["year"] = y + d // 12 + (1 if ev["month"] < m else 0)
    log(g, f"event #{parent['id']} chains #{tpl['id']} -> #{i} ({TYPE_NAMES.get(ev['type'], '?')}) in {d} months")
    if d == 0:
        loop = _ctx["loop"]
        if ev["type"] == 2 or not (loop >= 0 and i >= loop):     # FUN_0046DD90: later in this pass otherwise
            dispatch(g, ev)
    return ev


def mark_done_and_chain(g, ev):
    """event_mark_done_and_chain 0x00472EC0 (types 6, 7, 10, 11)."""
    if due(g, ev):
        done(g, ev)
        t = get(g, ev["chain"])
        if t is not None and t["flags"] & TEMPLATE and t["id"] != ev["id"]:     # FUN_004694A0
            chain(g, ev)


register(6, mark_done_and_chain, "1G")
register(7, mark_done_and_chain, "1G")
register(10, mark_done_and_chain, "1G")
register(11, mark_done_and_chain, "1G")


# --- the request list (Overview advisor) -------------------------------------------------------------------

def _request_open(ev):
    """request_is_open 0x004714F0 for ours' empire requests (event types 1 request / 0x1E tribute: "request",
    "tribute_out"): state 0 while request_outstanding 0x0047F630 (announced: countdown <= the lead months), or
    state 1 (overdue). States 2..4 (fulfilled, waiting for the city's answer) and 10 (done) are not listed."""
    if ev["type"] not in ("request", "tribute_out"):
        return False
    if ev["state"] == 1:
        return True
    return ev["state"] == 0 and (ev.get("announced") or ev.get("countdown", 0) <= ev.get("deadline", 0))


def qsort(items, key):
    """The CRT qsort 0x005CC22F as it orders ties: up to 8 items (its cutoff, `cmp eax, 8`) it runs shortsort, a
    selection sort that moves the first of the largest keys to the end, then repeats on the rest. Longer lists:
    a stable sort (ours; the partition steps are not ported)."""
    a = list(items)
    if len(a) > 8:
        return sorted(a, key=key)
    hi = len(a) - 1
    while hi > 0:
        m = 0
        for p in range(1, hi + 1):
            if key(a[p]) > key(a[m]):
                m = p
        a[m], a[hi] = a[hi], a[m]
        hi -= 1
    return a


def request_list_rebuild(g):
    """request_list_rebuild 0x00483040 (= FUN_00483040): the list 0x00916E08 the Overview advisor shows
    (FUN_005B7760, at most 8 rows). Built after the monthly pass (scenario_events_monthly 0x0046D380), at the game
    start (episode_start_load, city_init_from_map) and when a request is paid (0x00475AB0 / 0x00475B50) or a quest
    dispatched (army_dialog_dispatch): first the open requests (request_is_open) with their months (+0x2E, the
    countdown at the rebuild: the row shows this cached number), sorted by it (qsort 0x005CC22F, compare 0x00483020;
    ties as its shortsort orders them), then the quests (type 4, FUN_0046D3E0) with FUN_00471560: active
    (+0x32) and state 0 (request_outstanding: active) or 0xB, in record order. Stored in g.request_list as
    [{"src": "empire"|"scenario", "id", "months"}]."""
    out = []
    e = getattr(g, "empire", None)
    sc = getattr(g, "scenario", None)
    if e is not None:
        reqs = [("empire", ev) for ev in e.events if _request_open(ev)]
        if sc is not None:                         # the scenario's own type-1 records (sim/empire/requests.py)
            from ..empire import requests
            reqs += [("scenario", ev) for ev in sc.events if ev["type"] == 1 and requests.is_open(ev)]
        reqs = qsort(reqs, lambda r: r[1].get("countdown", 0))
        out += [dict(src=src, id=ev["id"], months=ev.get("countdown", 0), request=src == "scenario")
                for src, ev in reqs]
    if sc is not None:
        out += [dict(src="scenario", id=ev["id"], months=None) for ev in sc.events
                if ev["type"] == 4 and ev.get("active") and ev.get("state") in (0, 0xB)]
    g.request_list = out
    return out


def request_rows(g):
    """The Overview's request rows from g.request_list (rebuilt when missing: saves from before 10-30): for a
    request its good, amount, city and months (state 1: overdue); for a quest the god (+0x60, icon group 0x807 +
    god, name 157:god), the hero of its slot (185:hero), the quest title (quest_title_text, FUN_004836B0) and the
    font: 3 with the request-done bullet when the hero is in the city and free (FUN_005BDDD0), else 5."""
    lst = g.__dict__.get("request_list")
    if lst is None:
        lst = request_list_rebuild(g)
    rows = []
    e = getattr(g, "empire", None)
    for r in lst:
        if r["src"] == "empire":
            ev = next((x for x in e.events if x["id"] == r["id"]), None) if e is not None else None
            if ev is None:
                continue
            cc = e.cities.get(ev.get("city"))
            rows.append(dict(kind="request", item=ev.get("item"), amount=ev.get("amount", 0),
                             city=cc.name if cc else "", short=(cc.short or cc.name[:4]) if cc else "",
                             stock=_stock_column(g, ev.get("item")), relation=cc.relation if cc else "",
                             months=r["months"], overdue=ev.get("state") == 1, tribute=ev["type"] == "tribute_out",
                             can=_can_fulfil(g, ev)))
        elif r.get("request"):                     # a scenario request (type 1)
            ev = get(g, r["id"])
            cc = e.cities.get(ev.get("city")) if ev is not None and e is not None else None
            if cc is None:
                continue
            from ..empire import requests
            key = requests.good_key(ev["item"]) or ev["item"]
            rows.append(dict(kind="request", item=key, amount=ev.get("amount", 0), city=cc.name,
                             short=cc.short or cc.name[:4], stock=_stock_column(g, key), relation=cc.relation,
                             months=r["months"], overdue=ev.get("state") == 1, tribute=False,
                             can=requests.enough(g, ev) or ev["item"] == requests.TROOPS_ID))
        else:
            ev = get(g, r["id"])
            if ev is None:
                continue
            rows.append(dict(kind="quest", **_quest_row(g, ev)))
    return rows


def _stock_column(g, item):
    """FUN_005B7760's stock column: the treasury for drachmas (count_noun 8:0), nothing for troops; else granaries
    (foods) + storehouses + trading posts in loads (/100, sculpture /400), food = every food good."""
    try:
        from ..empire import diplomacy, model
    except Exception:                             # noqa: BLE001  (no empire module)
        return None
    if item == model.TROOPS:
        return None
    n = diplomacy.stock(g, item)
    return n if item == model.MONEY else n // (400 if item == "sculpture" else 100)


def _can_fulfil(g, ev):
    """FUN_004713E0: the stock (or treasury) covers the amount, or Hermes pays it (hermes_request_auto 0x004E7C00);
    the rows' bullet (request complete 12 / incomplete 18) and font (13 / 8) follow it."""
    try:
        from ..empire import diplomacy
        from .. import gods
        return bool(diplomacy.have_enough(g, ev) or gods.hermes_pays(g, ev))
    except Exception:                             # noqa: BLE001  (no empire / gods module)
        return False


def _quest_row(g, ev):
    try:
        from ..heroes import heroes, events as hev
    except Exception:                             # noqa: BLE001  (no heroes module)
        return dict(god=ev.get("kind", 0), hero="", title="", ready=False)
    h = heroes.hero_of_slot(g, ev.get("b36", -1))
    god, q = ev.get("kind", 0), ev.get("quest", 0)
    title = ""
    if god < 14:                                   # FUN_004836B0: the title phrase with [hero_needed] = the hero
        from .. import messages
        try:
            title = messages.text(hev.quest_title(god, q)).replace("[hero_needed]", heroes.name(h) if h >= 0 else "")
        except KeyError:
            title = ""
    w = heroes.figure(g, h) if h >= 0 else None
    ready = w is not None and getattr(w, "quest", None) is None
    return dict(god=god, hero=heroes.name(h) if h >= 0 else "", title=title, ready=ready)


# --- CLI and export ----------------------------------------------------------------------------------------

def describe(g, ev):
    sc = g.scenario
    y0 = g.start_year
    yr = y0 + ev["year"]
    when = f"{['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][ev['month']]} " \
           f"{abs(yr)} {'BC' if yr < 0 else 'AD'}"
    fl = ",".join(n for b, n in ((TEMPLATE, "template"), (RECURRING, "recurring"), (DONE, "done"),
                                 (DYNAMIC, "dynamic"), (DISABLED, "disabled")) if ev["flags"] & b)
    h = HANDLERS.get(ev["type"])
    return (f"#{ev['id']:<3d} {TYPE_NAMES.get(ev['type'], ev['type']):<17s} {when:<12s} state {ev['state']} "
            f"active {ev['active']} item {ev['item']} amount {ev['amount']} city {ev['city']}"
            + (f" chain #{ev['chain']}" if ev["chain"] >= 0 else "") + (f" [{fl}]" if fl else "")
            + ("" if h or ev["flags"] & TEMPLATE else " (no handler)"))


def command(g, op, a):
    if op not in VERBS:
        return None
    _plugins()
    if a and a[0] == "on":
        if not available(g.map_name):
            raise ValueError(f"no episode data for map {g.map_name} (data/scenario/)")
        g.scenario = load(g)
        g.scenario_v = 1
        late = [ev for ev in g.scenario.events if not ev["flags"] & TEMPLATE
                and ev["year"] * 12 + ev["month"] < g.month_index]
        return (f"scenario events on: {len(g.scenario.events)} records from {g.scenario.source}"
                + (f"; {len(late)} dated before today will not fire" if late else ""))
    if a and a[0] == "off":
        g.scenario = None
        return "scenario events off"
    sc = getattr(g, "scenario", None)
    if sc is None:
        return "scenario events: none (`scenario on` loads the map's episode)"
    if a and a[0] == "log":
        return "\n".join(f"{m // 12:+d}/{m % 12 + 1}: {t}" for m, t in sc.log) or "(empty)"
    return "\n".join([f"scenario events from {sc.source}: {len(sc.events)} records"]
                     + [describe(g, ev) for ev in sc.events])


def export(g):
    sc = getattr(g, "scenario", None)
    if sc is None:
        return None
    out = [dict(id=ev["id"], type=ev["type"], name=TYPE_NAMES.get(ev["type"], ""), year=ev["year"],
                month=ev["month"], state=ev["state"], active=ev["active"], flags=ev["flags"])
           for ev in sc.events if not ev["flags"] & TEMPLATE]
    if getattr(g, "empire", None) is not None:      # type 1: what the request's message window and dialogs need
        from ..empire import requests
        for d in out:
            if d["type"] == 1:
                ev = get(g, d["id"])
                c = g.empire.cities.get(ev.get("city"))
                r = g.empire.cities.get(_byte(ev, 0x6F)) if ev.get("kind") == 2 else None
                d.update(item=ev.get("item"), kind=ev.get("kind", 0), open=requests.is_open(ev),
                         can=requests.is_open(ev) and requests.can_fulfil(g, ev), city=c.name if c else "",
                         route=c.route if c else "", rival=r.name if r else "",
                         hero=requests.monster_hero(g, ev) if ev.get("kind") == 7 else None)
    return out


def _byte(ev, off):
    raw = bytes.fromhex(ev.get("raw") or "")
    return raw[off] if len(raw) > off else 0
