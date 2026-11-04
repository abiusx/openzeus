"""The empire module: world cities, diplomacy, tribute, expeditions and the world map's state
(docs/logic/world-map.md, "Interface"). Self-contained; the core calls only:

  new_game(g)                 Game.__init__: load the scenario's empire (off when the map has none)
  loaded(g)                   Game.load: the post-load fix-ups (FUN_00510ED0's FUN_00461360)
  day(g)                      systems.run_day, once per day (the exe's month_advance hooks)
  command(g, op, args)        Game.command: the CLI verbs below; None when op is not ours
  export(g)                   sim/live.py /world.json: what the world map screen needs
  partners / trading / tradeable    sim/systems/trade.py: who trades (None / True when the module is off)
  next_invasion(g)            sim/military: months to the soonest invasion and its entry point (auto-defend)
  aid_lost(g, ev_id)          sim/military: the last company of an accepted aid army is gone (0x00481D40)
  offers_export(g)            sim/export.py state.json "offers": the open accept/postpone/decline dialogs

Switch: `empire off` turns the module off (no diplomacy; trade partners from data/trade.json, the state of
saves and games from before the module); `empire on [WORLD]` loads the scenario's empire or a world file
(data/world/WORLD.json, docs/world-format.md; sim/empire/world.py), only before any trading post or dock
exists unless `--migrate` (re-binds the posts by partner name). Uses from the core: economy.goods_add/goods_remove/city_stock, military.companies
(a company's "away" mark), g.message, g.rng, g.city.treasury.
"""
from . import diplomacy, events, relations, scenario, war, world
from .model import MONEY, TROOPS, FOOD, STRIKE

VERBS = ("empire", "cities", "city", "gift", "request", "fulfill", "fulfil", "refuse", "raid", "conquer", "cityrequest",
         "citystatus", "cityinvade", "offer", "offers", "msglevel", "answer")


def get(g):
    return getattr(g, "empire", None)


def new_game(g, start=None):
    """start (sim/episode.py): {"empire": an Empire to keep (a colony start carries the parent's) or None = the
    map's own (any map name, built at run time when data/empire has none), "player_city": the episode's values}."""
    if start is None:
        g.empire = scenario.load_scenario(g.map_name) if scenario.available(g.map_name) else None
        relations.goods_flags_rebuild(g.empire)   # FUN_0051D5F0 -> FUN_004612E0 -> FUN_00461360 (6.8)
        if g.empire is not None:
            map_prices(g, scenario.map_data(g.map_name))
        return
    e = start.get("empire")
    if e is None:
        d = scenario.map_data(g.map_name)
        g.empire = scenario.from_data(d)
        map_prices(g, d)                          # a colony keeps the parent's prices (sim/episode.py carry)
    else:
        g.empire = e
    if start.get("player_city"):
        set_player_city(g, start["player_city"], start.get("resources_only", False))
    relations.goods_flags_rebuild(g.empire)       # episode_start_load: FUN_00461360 (new city, colony; 6.8)


def map_prices(g, d):
    """goods_price 0x0065B9B0 as the map brings it (block 21, read by the map load FUN_005B0990): ours keep
    g.prices only when the map's differ from the catalogue's (data/trade.json: the table of 34 of the 44 Zeus .pak
    maps); Hercules Labors (bronze 105, marble 72, armor 195), The Peloponnesian War (wheat 40) and a few
    colony maps have their own (docs/logic/episode-transition.md). Goods the map's numbering lacks keep the
    catalogue's (Poseidon goods in a Zeus map)."""
    cat = g.cat.trade["prices"]
    mp = d.get("prices") or {}
    if any(v != cat.get(k, 0) for k, v in mp.items()):
        g.prices = dict(cat, **mp)


def loaded(g):
    """game_file_load 0x0050E610 -> FUN_00510ED0, after every saved-game load: FUN_00461360 rebuilds every city's
    buys/sells flags from its lists (a city whose flags a status change zeroed trades again; world-map.md 6.8); the
    player's city is set active (+0x170 = 1) and visible (+0x174 &= ~4)."""
    e = get(g)
    relations.goods_flags_rebuild(e)
    if e is not None:
        try:
            p = e.player()
        except StopIteration:
            return
        p.active, p.visible = True, True


def episode_reset(g):
    """episode_start_load (colony and continue starts) copies the episode's events over g_events 0x009173F4: every
    run-time record of the episode before (a city's request, a gift or delivery on its way, tribute, an ally strike,
    an expedition, an invasion on the world map, an offer waiting for an answer) is gone. The world cities keep
    their counters (troops away, fatigue, attitude)."""
    e = get(g)
    if e is not None:
        e.events = []


def set_player_city(g, pc, resources_only=False):
    """An episode's player-city values into the player's WorldCity (episode_start_load 0x00420390): resources
    (scenario +0x7A8 -> city +0xA8, the raw goods it may produce); new city / continue starts also the buy and sell
    lists (+0x7BC / +0x7C2), their quotas (+0x7C8 -> +0x60 per good), wealth, military strength and attitude
    (adventure +0x8B70 / +0x8B48 / +0xCB264); a colony start writes the resources only. (The exe then zeroes every
    city's army_months byte: ours ends the invasions, sim/military episode_reset.)"""
    e = get(g)
    if e is None:
        return
    c = e.player()
    c.resources = list(pc.get("resources", []))
    if resources_only:
        return
    q = pc.get("table_60", {})
    c.buys = {k: q.get(k, 0) for k in pc.get("buys", [])}
    c.sells = {k: q.get(k, 0) for k in pc.get("sells", [])}
    for k, f in (("wealth", "wealth"), ("military", "strength"), ("attitude", "attitude")):
        if k in pc:
            setattr(c, f, pc[k])


def set_kind(g, city_id, kind, **fields):
    """A world city's kind (and other fields, e.g. tribute mode): the colony starts and returns
    (episode_start_load kind 1: parent -> parent kind 3, colony -> player 0, active; episode_end_save_parent
    0x0052D2B0: colony -> kind 1 with tribute mode 1, parent -> player)."""
    c = get(g).cities[city_id]
    c.kind = kind
    for k, v in fields.items():
        if k == "tribute_mode":
            c.tribute["mode"] = v
        else:
            setattr(c, k, v)
    return c


# --- core hooks -------------------------------------------------------------------------------

def day(g):
    """month_advance hooks (world-map.md 6.1) by day of the month (our day = the exe's 51-tick cycle)."""
    e = get(g)
    if e is None:
        return
    dom = g.day % g.rules["days_per_month"]
    if dom == 0 and g.day:
        e.months += 1
        if g.month in (0, 6):
            relations.drift(g)
    if dom in (0, 4, 8, 12):
        relations.update(g)
    if dom == 2:
        relations.monthly(g)
        if g.month == 0:
            diplomacy.tribute(g)
    if dom == 4:
        e.peak_strength = max(e.peak_strength, relations.player_strength(g)[1])
    if dom == 7:
        diplomacy.streaks(g)
    if dom == 12:
        diplomacy.spontaneous(g)


def month_events(g):
    """The empire's run-time records (the exe keeps them in g_events after the episode's: run-time slots come after
    the scenario's records, so month_events_dispatch reaches them after the scenario's in scenario_events_monthly
    0x0046D380): called by sim/scenario.month after its own records, before request_list_rebuild. Their messages
    (a tribute claim's) arrive after the scenario's of the same month (bugs.md 360)."""
    e = get(g)
    if e is None or g.day == 0 or g.day % g.rules["days_per_month"]:
        return
    events.month(g)


def partners(g):
    """Trade partners for sim/systems/trade.py, indexed by city id (None: module off)."""
    e = get(g)
    if e is None:
        return None
    n = max(e.cities) + 1
    out = [dict(name="", route="land", buys={}, sells={}) for _ in range(n)]
    for c in e.cities.values():
        flags = c.kind != "player" and getattr(c, "goods_flags", True)    # zeroed by a status change that
        out[c.id] = dict(name=c.name, route=c.route, buys=c.buys if flags else {},   # closed trade (6.8); conquest
                         sells=c.sells if flags else {})                             # reopens trade, not the flags (a load does)
    return out


def trading(g, c):
    """is_trading_partner: traders come from this city."""
    e = get(g)
    return True if e is None else (c in e.cities and e.cities[c].trading())


def tradeable(g, c):
    """city_tradeable: the Trade build menu may list it (not a rival)."""
    e = get(g)
    return True if e is None else (c in e.cities and e.cities[c].tradeable())


def next_invasion(g):
    """For sim/military (month_advance day 0): (months until the soonest pending invasion arrives, its entry
    point 1..8 land / 9..16 sea, its landing point index +0x78); (1000000, 8, 0) when none
    (event_months_until_due 0x00472000)."""
    e = get(g)
    best = (1000000, 8, 0)
    if e is None:
        return best
    for ev in events.live(g, "invasion"):
        if ev.get("arrived"):
            continue
        m = ev["due"] - g.month_index
        if m <= best[0]:
            best = (m, ev.get("point", 8), ev.get("landing", 0))
    if getattr(g, "scenario", None) is not None:          # the scenario's type-2 records (invasion_events.py)
        from . import invasion_events
        s = invasion_events.next_pending(g)
        if s is not None and s[0] <= best[0]:
            best = s
    return best


def aid_lost(g, ev_id):
    if get(g) is not None:
        war.aid_lost(g, ev_id)


def offers_export(g):
    from . import offers
    return offers.export(g) if get(g) is not None else []


# --- CLI ----------------------------------------------------------------------------------------

def command(g, op, a):
    if op not in VERBS:
        return None
    e = get(g)
    if e is not None and a:                          # city names may have spaces ("Mt. Cithaeron"): one argument
        a = _join_city(e, a)
    if op == "empire":
        if a and a[0] in ("on", "off"):              # empire on [WORLD] [--migrate] | empire off
            rest = [x for x in a[1:] if x != "--migrate"]
            return switch(g, a[0] == "on", rest[0] if rest else None, "--migrate" in a)
        if a and a[0] == "worlds":
            return "worlds (data/world/): " + (", ".join(world.names()) or "none")
        if a and a[0] == "attitude":                 # empire attitude CITY N: sandbox cheat (tests)
            c = e.find(a[1])
            c.attitude = max(0, min(100, int(a[2])))
            return f"{c.name}: attitude {c.attitude}"
        if a and a[0] == "army":                     # empire army CITY N: sandbox cheat (tests)
            c = e.find(a[1])
            c.army = int(a[2])
            return f"{c.name}: army {c.army}"
        return status(g)
    if e is None:
        raise ValueError("the empire module is off (`empire on`)")
    if op in ("offer", "offers", "msglevel"):
        return _offer_cmd(g, op, a)
    if op == "cities":
        return "\n".join(line(g, c) for c in e.cities.values())
    if op == "answer":                               # answer ID dispatch|refuse [companies 1,2|none] [ships ..] [heroes ..]
        return _answer(g, a)
    c = e.find(a[0]) if a else None
    if c is None:
        raise ValueError(f"usage: {op} CITY ...")
    if op == "city":
        return describe(g, c)
    if op == "gift":
        return diplomacy.gift(g, c, a[1], a[2] if len(a) > 2 else "small")
    if op == "request":
        target = e.find(a[2]) if len(a) > 2 else None
        return diplomacy.request(g, c, a[1], target)
    if op == "refuse":                               # a scenario request's refuse button (wm_sub_475B50)
        from . import requests as R
        sevs = R.open_for(g, c.id)
        if not sevs:
            raise ValueError(f"{c.name} has no outstanding scenario request")
        return R.refuse(g, sevs[min(int(a[1]) if len(a) > 1 else 0, len(sevs) - 1)])
    if op in ("fulfill", "fulfil"):
        return diplomacy.fulfil(g, c, int(a[1]) if len(a) > 1 else 0,
                                [int(x) for x in a[2:]] if len(a) > 2 else None)
    if op in ("raid", "conquer"):    # raid CITY [GOOD] [with ALLY] [companies 1,2|none] [ships ID,ID|none] [heroes H,H]
        rest = a[1:]
        pick = {}
        keys = ("with", "companies", "ships", "heroes")
        for k in keys:
            if k in rest:
                i = rest.index(k)
                j = i + 2
                if k == "with":                      # the ally's name runs to the next keyword (spaces allowed)
                    while j < len(rest) and rest[j] not in keys:
                        j += 1
                pick[k] = " ".join(rest[i + 1:j]) if i + 1 < len(rest) else ""
                del rest[i:j]
        ids = lambda v: None if v is None else [] if v in ("", "none") else [int(x) for x in v.split(",") if x]
        good = rest[0] if rest else None
        return war.attack(g, c, op == "raid", good, pick.get("with"), ids(pick.get("companies")), ids(pick.get("ships")),
                          ids(pick.get("heroes")))
    if op == "cityrequest":                          # cityrequest CITY ITEM AMOUNT [KIND] [DEADLINE]
        ev = diplomacy.city_request(g, c, a[1], int(a[2]), int(a[3]) if len(a) > 3 else 0,
                                    int(a[4]) if len(a) > 4 else 12)
        return f"{c.name} asks for {ev['amount']} {ev['item']} (event {ev['id']})"
    if op == "cityinvade":                           # cityinvade CITY [STRENGTH]: a scenario invasion event
        n = int(a[1]) if len(a) > 1 else c.army * 3 // 5     # (type 2) dated today; default: the spontaneous size
        if c.cls() != "rival":
            raise ValueError(f"{c.name} is not a rival (only rivals invade)")
        if not war.invasion_create(g, c, n):
            raise ValueError(f"{c.name} already has an army on the way (or strength {n} < 1)")
        return f"{c.name} sends an army of {n}: it arrives in 2 months"
    if op == "citystatus":                           # citystatus CITY SUBTYPE [AMOUNT] (text group 35)
        sub = int(a[1])
        if relations.status_change(g, c, sub, int(a[2]) if len(a) > 2 else 0):
            if sub != 9:                             # 9 (rival -> ally): status_change posted the exe's message
                g.message(f"{c.name} {relations.STATUS_TEXT.get(sub, 'changes')}.")
            return f"{c.name} {relations.STATUS_TEXT.get(sub, 'changed')}"
        return f"{c.name}: nothing changes"


def _join_city(e, a):
    """a with every run of words that names a city joined into one argument ("Mt.", "Cithaeron" -> "Mt. Cithaeron"),
    wherever it stands (the city, a request's target, a raid's ally, `empire attitude CITY N`); the longest run wins,
    single words are left as they are (bugs 382, 449, 451)."""
    names = {c.name.lower() for c in e.cities.values() if " " in c.name}
    if not names:
        return list(a)
    out, i = [], 0
    while i < len(a):
        for n in range(len(a) - i, 1, -1):
            if " ".join(a[i:i + n]).lower() in names:
                out.append(" ".join(a[i:i + n]))
                i += n
                break
        else:
            out.append(a[i])
            i += 1
    return out


def _offer_cmd(g, op, a):
    """offers | offer [ID] accept|postpone|decline | msglevel CAT 0|1|2 (offers.py)."""
    from . import offers
    if op == "offers":
        return offers.text(g)
    if op == "msglevel":                             # Options > Messages per category: 0 Off, 1 Condensed, 2 Full
        if len(a) < 2:
            raise ValueError("usage: msglevel CATEGORY 0|1|2")
        g.sd("msg_levels", {})[str(int(a[0]))] = max(0, min(2, int(a[1])))
        return f"message category {int(a[0])}: {['off', 'condensed', 'full'][max(0, min(2, int(a[1])))]}"
    if not a or a[-1] not in ("accept", "postpone", "decline"):
        raise ValueError("usage: offer [ID] accept|postpone|decline (`offers` lists them)")
    ev = offers.find(g, int(a[0]) if len(a) > 1 else None)
    if ev is None or not ev.get("buttons"):
        raise ValueError("no such offer waiting (`offers`)")
    return offers.answer(g, ev, a[-1])


def switch(g, on, name=None, migrate=False):
    """empire on [WORLD] [--migrate] / empire off. WORLD: data/world/WORLD.json (docs/world-format.md); without
    it, the map's own scenario. With trading posts already built, `--migrate` re-binds them by partner name
    (world.migrate); otherwise switching is refused (their partner indexes would point at other cities)."""
    has_posts = any(b.kind == "trade" for b in g.buildings.values())
    if on:
        if name:
            emp = world.load_world(name)
        elif scenario.available(g.map_name):
            emp = scenario.load_scenario(g.map_name)
        else:
            raise ValueError(f"no empire data for map '{g.map_name}' (tools/build_empire.py); worlds: "
                             f"{', '.join(world.names()) or 'none'}")
        if has_posts:
            if not migrate:
                raise ValueError("this city has trading posts: `empire on [WORLD] --migrate` re-binds them by "
                                 "partner name (docs/world-format.md \"Migration\")")
            note = world.migrate(g, emp)
            return status(g) + "\n" + note
        g.empire = emp
    else:
        if has_posts:
            raise ValueError("switch the empire off before building any trading post or dock")
        g.empire = None
    g.__dict__.pop("trade_state", None)
    return status(g)


def status(g):
    e = get(g)
    if e is None:
        return "empire off (trade partners from data/trade.json)"
    t = e.totals
    return (f"empire on ({e.source}, map picture {e.picture}): {len(e.cities)} cities, "
            f"{len(events.live(g))} events under way; gifts given {t['gifts_given']} dr, received "
            f"{t['gifts_received']} dr, tribute received {t['tribute_received']}")


def line(g, c):
    from ..systems import trade
    k = c.cls()
    word = relations.ATTITUDE_WORDS[relations.attitude_code(c)] if c.exists() else "-"
    used = trade.state(g)["used"][c.id] if c.id < len(trade.state(g)["used"]) else {}
    goods = lambda d: " ".join(f"{gd} {used.get(gd, 0)}/{q}" for gd, q in d.items() if q) or "-"
    flags = [f for f, on in (("trading", c.trading()), ("REBELLING", c.rebellion), ("trade suspended",
             c.tradeable() and not c.trade_open), ("inactive", not c.active), ("invisible", not c.visible)) if on]
    if c.kind == "player":
        return f"{c.id} {c.name}: our city"
    return (f"{c.id} {c.name} ({c.kind}, {k}, {c.route}): attitude {c.attitude} {word}, army {c.army}"
            f"{', ' + ', '.join(flags) if flags else ''}\n   buys {goods(c.buys)} | sells {goods(c.sells)}")


def describe(g, c):
    out = [line(g, c)]
    if c.kind != "player":
        out.append(f"   leader {c.leader}; wealth {c.wealth}, military {c.strength}, streaks +{c.pleased}/-{c.displeased}, "
                   f"tribute {c.tribute}")
        asks = []
        for it in diplomacy.REQUESTABLE:
            thr, code = diplomacy.can_request(g, c, it)
            if thr >= 0 and code == 3:
                asks.append(it)
        out.append(f"   can request: {', '.join(asks) or 'nothing'}; can be attacked: {war.can_be_attacked(c)}")
        reqs = [ev for ev in events.live(g, None, c.id) if ev["type"] in ("request", "tribute_out") and ev["state"] in (0, 1)]
        for i, ev in enumerate(reqs):
            out.append(f"   request {i}: {ev['amount']} {ev['item']} ({'overdue' if ev['state'] == 1 else str(ev['countdown']) + ' months'})")
        for m, text, d in c.history[-8:]:
            out.append(f"   history: month {m}: {text}" + (f" ({d:+d})" if d else ""))
    return "\n".join(out)


# --- play mode export -------------------------------------------------------------------------------

def _marker(c):
    """city_marker_image 0x0042CB30 (Zeus branch) + standards/strength icons (world_map_draw)."""
    n = min(max(c.nation, 0), 4)
    base = {"player": ("SPR_EMP_CITY", 0), "parent": ("SPR_EMP_CITY", 0),
            "colony": ("SPR_EMP_ACTIVE_COLONY", 0) if c.active else ("SPR_EMP_INACTIVE_COLONY", 0),
            "foreign": ("SPR_EMP_NONPLAYER_CITY", n) if c.active else ("SPR_EMP_INACTIVE_CITY", 0),
            "distant": ("SPR_EMP_DISTANT_CITY", n) if c.active else ("SPR_EMP_INACTIVE_CITY", n),
            "enchanted": ("SPR_EMP_MONSTER_LAIR", 0 if c.active else 1),
            "destroyed": ("SPR_EMP_MONSTER_LAIR", 1)}[c.kind]
    m = dict(base=base)
    if c.active:
        std = {"player": "SPR_EMP_PLAYER_STANDARD", "colony": "SPR_EMP_COLONY_STANDARD",
               "parent": "SPR_EMP_COLONY_STANDARD"}.get(c.kind)
        if c.kind == "foreign":
            std = {"ally": "SPR_EMP_ALLY_BANNER", "vassal": "SPR_EMP_COLONY_STANDARD"}.get(c.relation)
        if std:
            m["standard"] = std
        if c.kind == "foreign":
            m["army"] = min(5, max(1, c.army // 20)) - 1
            m["wealth"] = min(5, max(1, c.wealth)) - 1
        if c.rebellion:
            m["rebelling"] = True
    return m


def _answer(g, a):
    """A scenario request (type-1 record ID) answered from its message's buttons, the world map's 'requests by' row or
    the army dialog: dispatch = event_pay_tribute_or_gift (goods / money / food leave now; troops: the companies,
    triremes and heroes picked, `companies` absent = every one at home), refuse = wm_sub_475B50."""
    from . import requests as R
    from .. import scenario as S
    if len(a) < 2 or a[1] not in ("dispatch", "refuse"):
        raise ValueError("usage: answer ID dispatch|refuse [companies 1,2|none] [ships ID,ID|none] [heroes H,H]")
    ev = S.get(g, int(a[0]))
    if ev is None or ev["type"] != 1 or not R.is_open(ev):
        raise ValueError(f"request #{a[0]} is not open")
    if a[1] == "refuse":
        return R.refuse(g, ev)
    if ev["item"] != R.TROOPS_ID:
        return R.pay(g, ev)
    rest = a[2:]
    pick = {k: rest[rest.index(k) + 1] if rest.index(k) + 1 < len(rest) else "" for k in ("companies", "ships", "heroes")
            if k in rest}
    ids = lambda v: None if v is None else [] if v in ("", "none") else [int(x) for x in v.split(",") if x]
    return R.dispatch(g, ev, ids(pick.get("companies")), ids(pick.get("ships")), ids(pick.get("heroes")))


def _city_requests(g, c):
    """The 'requests by [city]' rows (world_map_btn4 0x00406B00 / FUN_00464320): the request list 0x00916E08
    (scenario.request_list_rebuild: open requests and tribute claims sorted by their months) filtered by the city, in
    that order; months = the list's cached countdown."""
    from .. import scenario as S
    from . import requests as R
    lst = g.__dict__.get("request_list")
    if lst is None:
        lst = S.request_list_rebuild(g)
    out = []
    for r in lst:
        if r["src"] == "empire":
            ev = next((x for x in g.empire.events if x["id"] == r["id"]), None)
            if ev is None or ev.get("city") != c.id:
                continue
            out.append(dict(item=ev["item"], amount=ev["amount"], overdue=ev["state"] == 1, months=r["months"],
                            tribute=ev["type"] == "tribute_out", can=_can_fulfil(g, ev), have=_have(g, ev["item"]),
                            eid=ev["id"]))
        elif r.get("request"):
            ev = S.get(g, r["id"])
            if ev is None or ev.get("city") != c.id:
                continue
            key = R.good_key(ev["item"]) or TROOPS
            out.append(dict(item=key, amount=ev["amount"], overdue=ev["state"] == 1, months=r["months"],
                            tribute=False, can=ev["item"] == R.TROOPS_ID or R.enough(g, ev), have=_have(g, key),
                            event=ev["id"]))
    return out


def _can_fulfil(g, ev):
    """FUN_004713E0 (the 'requests by' row's status icon and font): enough in stock or Hermes pays."""
    from .. import gods
    try:
        return bool(gods.hermes_pays(g, ev) or diplomacy.have_enough(g, ev))
    except (KeyError, TypeError, ValueError):
        return False


def _have(g, item):
    """The stock count under a 'requests by' row (FUN_00464C00 mode 5): food = all foods / 100, sculpture / 400,
    other goods / 100; drachmas: the exe reads goods slot 23 of the stock arrays (nothing there): 0."""
    if item == MONEY:
        return 0
    try:
        return diplomacy.stock(g, item) // (400 if item == "sculpture" else 100)
    except (KeyError, TypeError, ValueError):
        return 0


def export(g):
    from ..systems import trade
    e = get(g)
    if e is None:                 # module off: the picture and data/trade.json's partners (they have no map position)
        return {"off": True, "picture": scenario.picture(getattr(g, "map_name", "sandbox")),
                "partners": [dict(name=p.get("name", ""), route=p.get("route", ""), buys=sorted(p.get("buys", {})),
                                  sells=sorted(p.get("sells", {})), post=trade.post_of(g, i) is not None)
                             for i, p in enumerate(trade.partners(g))]}
    st = trade.state(g)
    pid = e.player().id
    d = relations.diff(g)
    cities = []
    for c in e.cities.values():
        used = st["used"][c.id] if c.id < len(st["used"]) else {}
        post = trade.post_of(g, c.id) if c.kind != "player" else None
        reqs = _city_requests(g, c)
        asks = []
        if c.kind != "player":
            for it in diplomacy.REQUESTABLE:
                thr, code = diplomacy.can_request(g, c, it)
                if code >= 0:                          # city_can_request true (0x00465070: and thr >= 0 or code >= 0)
                    asks.append(dict(item=it, thr=thr, code=code, ok=thr >= 0 and code == 3,
                                     amount=diplomacy.request_amount(g, c, diplomacy.best_food(c) if it == FOOD else it)
                                     if thr >= 0 and code == 3 else 0))
        gifts = {it: diplomacy.gift_sizes(g, it) for it in diplomacy.GIFTABLE} if c.exists() and c.kind != "player" else {}
        t = dict(c.tribute)
        if t["mode"] == 2:
            t["claim_now"] = int(t["claim"] * diplomacy.TRIBUTE_MULT[d])
        cities.append(dict(
            id=c.id, name=c.name, short=c.short, leader=c.leader, kind=c.kind, relation=c.relation, cls=c.cls(),
            attitude=c.attitude, word=relations.attitude_code(c) if c.exists() else None,
            pleased=c.pleased, displeased=c.displeased, wealth=c.wealth, strength=c.strength, army=c.army,
            rebellion=c.rebellion, exists=c.exists(), trading=c.trading(), tradeable=c.tradeable(),
            trade_open=c.trade_open, shown=c.shown(), active=c.active, route=c.route,
            buys=[[gd, used.get(gd, 0), q] for gd, q in c.buys.items() if q],
            sells=[[gd, used.get(gd, 0), q] for gd, q in c.sells.items() if q],
            tribute=t, map=c.map, marker=_marker(c),
            post=dict(id=post.id, x=post.x, y=post.y) if post else None,
            buttons=dict(request=c.exists() and not c.rebellion and c.kind != "player",
                         requests=c.exists() and c.kind != "player", gift=c.exists() and c.kind != "player",
                         raid=war.can_be_attacked(c), conquer=war.can_be_attacked(c),
                         orders=c.kind != "player" and c.trading() and c.trades_something()),
            requests=reqs, asks=asks, gifts=gifts,
            history=[dict(month=m, text=tx, delta=dl) for m, tx, dl in c.history[-30:]]))
    routes = [dict(a=r["a"], b=r["b"], kind=r["kind"], dots=r["dots"]) for r in e.routes
              if pid in (r["a"], r["b"]) and e.cities.get(r["b"] if r["a"] == pid else r["a"]) is not None
              and e.cities[r["b"] if r["a"] == pid else r["a"]].trading()]
    return dict(picture=e.picture, player=pid, cities=cities, routes=routes, armies=war.positions(g),
                totals=e.totals, treasury=g.city.treasury, companies=len(war.home_companies(g)),
                start_year=g.start_year)
