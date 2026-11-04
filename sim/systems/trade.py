"""Trade (docs/logic/trade.md): partner cities send caravans (a merchant + 2 donkeys, walking from
the land entry) or ships (sailing from the sea entry) to the trading post / dock built for them.
At the post the trader swaps one export load and one import load every trade_ticks until both
fail or it carries max_loads each way, then leaves by the map exit. Each load is 100 units
(sculpture 400) at one price per good, and uses one unit of the partner's yearly quota.

Partners, quotas and prices are ours (data/trade.json, tools/build_data.py TRADE), all active from
the start. A post holds goods like a storehouse; per good the player sets an order:
  export [LIMIT]  carts bring the good here and the post's storehousemen fetch it from storage
                  (up to LIMIT, default all 6000); traders take it away. `stockpile GOOD on`
                  stops all of that city-wide
  import [LIMIT]  traders bring the good (while stock < LIMIT); vendors/workshops take it from here
  off             nothing
"""
from . import walkers, labor

DEFAULT_LIMIT = 6000          # the post's capacity (storage-distribution.md §8)
# Goods a post/dock never trades: storage_goods_list 0x005B12C0 leaves horses (15) and chariots (22) out of the
# trade window (types 0x3D/0x3E), and the post's trade_state for them stays 9 (storage_create 0x00494960), so
# storage_cannot_accept 0x004894E0 refuses them and import_one/export_one 0x005B9BD0/0x005B9810 never pick them
# (they need state 5/7). A partner may still list them (city_sells/city_buys accept 0..22): dead entries.
NOT_TRADED = ("horses", "chariot")


def partners(g):
    """The partner list, indexed by city: the empire's cities (sim/empire) or, with the module off,
    data/trade.json's partners."""
    from .. import empire
    return empire.partners(g) or g.cat.trade["partners"]


def state(g):
    st = getattr(g, "trade_state", None)
    if st is None:
        n = len(partners(g))
        st = g.trade_state = dict(used=[{} for _ in range(n)], countdown=[0] * n,
                                  traders=[[] for _ in range(n)], cursor={})
    return st


def unit(g, good):
    return g.cat.trade["units"].get(good, 100)


def good_price(g, good):
    """goods_price[good] (one price per good, bought and sold at it): the catalogue's (data/trade.json), or the game's
    own table once a scenario price event changed it (event_price_increase 0x00472B20 / _decrease 0x00472D00,
    sim/empire/city_events.py; g.prices, absent until then)."""
    own = g.__dict__.get("prices")
    if own is not None and good in own:
        return own[good]
    return g.cat.trade["prices"].get(good, 0)


price = good_price          # the name the readers outside use


def set_price(g, good, value):
    if g.__dict__.get("prices") is None:
        g.prices = dict(g.cat.trade["prices"])
    g.prices[good] = value


def partner_index(g, name):
    for i, p in enumerate(partners(g)):
        if p["name"].lower() == name.lower():
            return i
    raise ValueError(f"unknown partner '{name}' ({', '.join(p['name'] for p in partners(g))})")


def post_of(g, c):
    """trade_building_of_city: the first post/dock bound to partner c."""
    from . import index
    for b in index.of(g, "trade"):
        if b.kind == "trade" and b.misc.get("partner") == c:
            return b
    return None


def pick(g, key, name=None):
    """The partner a new post/dock (catalog key) is bound to: the named one, else the first free
    partner of its route."""
    from .. import empire
    route = g.cat.spec(key)["route"]
    if name:
        c = partner_index(g, name)
        if not empire.tradeable(g, c):
            raise ValueError(f"{partners(g)[c]['name']} does not trade with you (rival, inactive or unknown)")
        if partners(g)[c]["route"] != route:
            raise ValueError(f"{partners(g)[c]['name']} trades by {partners(g)[c]['route']}, not {route}")
        if post_of(g, c):
            raise ValueError(f"{partners(g)[c]['name']} already has a trade building")
    else:
        free = [i for i, p in enumerate(partners(g)) if p["route"] == route and not post_of(g, i)
                and empire.tradeable(g, i) and (p["buys"] or p["sells"])]
        if not free:
            raise ValueError(f"every {route} partner already has a trade building")
        c = free[0]
    return c


def order(g, b, good):
    return b.misc.get("orders", {}).get(good, "off")


def city_status(g, good):
    """The city's trade status of a good (0x01607EC4[g*0x18], built by FUN_005BB490): 9 (None) by default;
    every post / dock in storage-record order (ours: building id order) with the good on export (7), or on
    import (5) with a trading partner, writes its state, so the last such post wins. Returns "import",
    "export" or None. The exe rebuilds it when an advisor screen opens (advisor_screen_open_refresh
    0x00408C00) and in the trade advisor (0x00517E30), and trade_status_recheck 0x005BAD20 resets it when a
    partner is lost; ours: computed when asked (the simulation does not depend on which screens were opened)."""
    from .. import empire
    st = None
    for b in sorted((b for b in g.buildings.values() if b.kind == "trade"), key=lambda b: b.id):
        if "partner" not in b.misc:
            continue
        o = order(g, b, good)
        if o == "export" or (o == "import" and empire.trading(g, b.misc.get("partner"))):
            st = o
    return st


def limit(g, b, good):
    return b.misc.get("limits", {}).get(good, DEFAULT_LIMIT)


def city_stock(g, good):
    """Units of good in regular storage (not trade posts, not the endless warehouse)."""
    return sum(s.goods.get(good, 0) for s in g.buildings.values()
               if s.kind == "storage" and not g.cat.spec(s.key).get("endless"))


def set_order(g, b, good, mode, lim=None):
    from .economy import good_on
    if good not in g.cat.trade["prices"] or good in NOT_TRADED:
        raise ValueError(f"'{good}' is not tradeable")
    if not good_on(g, good):                                 # ours: oranges while Poseidon is off (economy.good_on)
        raise ValueError(f"'{good}' is a Poseidon good (`poseidon on` allows it)")
    p = partners(g)[b.misc["partner"]]
    if mode == "export" and good not in p["buys"]:
        raise ValueError(f"{p['name']} does not buy {good} (buys: {', '.join(p['buys'])})")
    if mode == "import" and good not in p["sells"]:
        raise ValueError(f"{p['name']} does not sell {good} (sells: {', '.join(p['sells'])})")
    if mode == "off":
        b.misc["orders"].pop(good, None)
    else:
        b.misc["orders"][good] = mode
    if lim is not None:
        b.misc["limits"][good] = lim
    out = f"{b.key} ({p['name']}): {good} {mode}" + (f" up to {limit(g, b, good)}" if mode != "off" else "")
    if mode in ("import", "export"):          # ours (playtest haiku-3 #6): the yearly quota is the real cap
        q = p["sells" if mode == "import" else "buys"][good]
        used = state(g)["used"][b.misc["partner"]].get(good, 0)
        out += (f"; {p['name']} {'sells' if mode == 'import' else 'buys'} {q} loads of {good} a year ({used} used"
                + (": quota reached, nothing more until January)" if used >= q else ")")
                + f"; {limit(g, b, good)} is the most the post holds, a load is {unit(g, good)}")
    return out


def staffed(g, b):
    """staffed (inlined in 0x005B9610 / 0x005B9990 / 0x005B8F90, trade.md): >= 50 %. A dock's is inverted in the
    exe (employees needed * 100 / workers, of the dock house): any staff up to twice the need passes (bugs.md 342)."""
    if b.key == "dock":
        need = g.cat.spec(b.key)["employees"]
        return b.employees > 0 and need * 100 // b.employees >= 50
    return labor.staffing(g, b) >= 50


def city_buys(g, c, good):
    from .economy import stockpiled, good_on
    from .. import empire
    if stockpiled(g, good) or not empire.trading(g, c):      # city_buys 0x005B92E0: a trading partner
        return False
    if not good_on(g, good):                                 # ours: no oranges while Poseidon is off
        return False
    q = partners(g)[c]["buys"].get(good, 0)
    return q > state(g)["used"][c].get(good, 0)


def city_sells(g, c, good):
    from .economy import good_on
    if not good_on(g, good):                                 # ours: no oranges while Poseidon is off
        return False
    q = partners(g)[c]["sells"].get(good, 0)
    return q > state(g)["used"][c].get(good, 0) and g.city.treasury >= -1999


# --- spawning (cities_trade_update, once per cycle = our day) -----------------------------------

def update(g):
    st = state(g)
    w = g.world
    from .. import empire
    for c, p in enumerate(partners(g)):
        if not empire.trading(g, c):              # is_trading_partner 0x0042C9F0 (world-map.md 5)
            continue
        sea = p["route"] == "sea"
        if sea and getattr(w, "sea_entry", None) is None:
            continue
        levels = [3 if q >= 25 else 2 if q >= 13 else 1 for q in list(p["buys"].values()) + list(p["sells"].values()) if q]
        if not levels:
            continue
        slots = -(-sum(levels) // len(levels))
        st["traders"][c] = [i for i in st["traders"][c] if i in g.walkers]
        if len(st["traders"][c]) >= slots:
            continue
        if st["countdown"][c] > 0:
            st["countdown"][c] -= 1
            continue
        t = g.cat.trade
        st["countdown"][c] = t["sea_every_days"] if sea else t["land_every_days"]
        from .. import gods
        if gods.active_now(g, 7):                # cities_trade_update 0x005B9EE0: Hermes (0x00EF5F44) x 66 / 100
            st["countdown"][c] = st["countdown"][c] * 66 // 100
        b = post_of(g, c)
        if b is None or b.access is None:
            continue
        if sea:
            x, y = w.sea_entry
            a = walkers.add(g, walkers.new_walker(g, role="ship", home=0, x=x, y=y, target=b.id, good=str(c),
                                                  state="wait"), t["wait_ticks"])
            st["traders"][c].append(a.id)
        else:
            x, y = w.entry
            m = walkers.add(g, walkers.new_walker(g, role="trader", home=0, x=x, y=y, target=b.id, good=str(c),
                                                  state="wait"), t["wait_ticks"])
            lead = m
            for _ in range(2):
                lead = walkers.add(g, walkers.new_walker(g, role="donkey", home=0, x=x, y=y, target=lead.id))
            st["traders"][c].append(m.id)
        return                                   # at most one new trader per pass


def year_start(g):
    st = state(g)
    st["used"] = [{} for _ in partners(g)]


# --- the trader walkers -----------------------------------------------------------------------------

def _post_ok(g, b):
    return b is not None and b.access is not None and staffed(g, b)


def trader(g, w):
    """Merchant (land) or ship (sea): wait at the entry -> go to the post -> trade -> leave."""
    t = g.cat.trade
    c = int(w.good)
    sea = w.role == "ship"
    b = g.buildings.get(w.target)
    if w.path:
        if w.state == "go" and not _post_ok(g, b):       # post gone/unstaffed on the way: leave
            return _leave(g, w, b)
        walkers.step_to(g, w, w.path.pop(0))
        return walkers.schedule(g, w, walkers.tile_delay(g, w))
    if w.state == "wait":
        if not _post_ok(g, b) or not (can_export(g, w, b, c) or can_import(g, w, b, c)):
            return _leave(g, w, b)
        if sea:
            from . import shore
            berth = shore.berth(g, b)               # the pier's berth (0x005BA3A0, trade.md "Dock placement")
            p = walkers.water_path(g, (w.x, w.y), {berth}, max_dist=walkers.ROUTE_MAX) if berth else None
        else:
            p = walkers.path_from_entry(g, b)
            p = p[1:] if p else p
        if p is None:
            b.reason = f"{partners(g)[c]['name']} traders can't reach this {b.key}"
            return _leave(g, w, b)
        w.state, w.path = "go", p
        return walkers.schedule(g, w, walkers.tile_delay(g, w) if p else 1)
    if w.state == "go":
        w.state = "trade"
        return walkers.schedule(g, w, t["trade_ticks"])
    if w.state == "trade":
        fails = 0
        if not (_post_ok(g, b) and can_export(g, w, b, c) and export_one(g, w, b, c)):
            fails += 1
        if not (_post_ok(g, b) and can_import(g, w, b, c) and import_one(g, w, b, c)):
            fails += 1
        if fails == 2:
            return _leave(g, w, b)
        return walkers.schedule(g, w, t["trade_ticks"])
    # leaving: path done
    walkers.remove(g, w)


def _leave(g, w, b):
    w.state = "leave"
    if w.role == "ship":
        p = walkers.water_path(g, (w.x, w.y), {g.world.sea_exit}, max_dist=walkers.ROUTE_MAX)
    else:
        p = _land_path_to_exit(g, w)
    if not p:
        return walkers.remove(g, w)
    w.path = p
    walkers.schedule(g, w, walkers.tile_delay(g, w))


def _land_path_to_exit(g, w):
    dist = walkers.entry_field(g, "exit")
    n = g.world.flags.shape[0]
    i = w.y * n + w.x
    if dist[i] < 0:
        return None
    out = []
    while dist[i] > 0:
        x = i % n
        for j in (i - n, i + n, i - 1 if x > 0 else -1, i + 1 if x < n - 1 else -1):
            if 0 <= j < n * n and dist[j] == dist[i] - 1:
                out.append((j % n, j // n))
                i = j
                break
        else:
            return None
    return out


def donkey(g, w):
    """Donkeys follow the walker ahead of them one tile behind; they vanish with their merchant."""
    lead = g.walkers.get(w.target)
    if lead is None:
        return walkers.remove(g, w)
    if lead.prev and (w.x, w.y) != lead.prev and (lead.x, lead.y) != (w.x, w.y):
        walkers.step_to(g, w, lead.prev)
    walkers.schedule(g, w, walkers.tile_delay(g, w))


# --- loads --------------------------------------------------------------------------------------

def _goods(g):
    return [k for k in g.cat.trade["prices"] if k not in NOT_TRADED]


def _ledger(w, side):
    """The trader's own ledger (g_trade_ledgers, zeroed by trade_ledger_alloc 0x005B9DF0 when the figure is
    created): loads per good taken ("out") / brought ("in") this visit."""
    return w.load.setdefault("ledger_" + side, {})


def _ledger_ok(g, w, b, k, side):
    """trade_ledger_full 0x005B8E00: the post's limit[g] caps what ONE trader moves per visit
    (loads*unit < limit), not the city total; the yearly cap is the partner's quota (city_sells/city_buys)."""
    return _ledger(w, side).get(k, 0) * unit(g, k) < limit(g, b, k)


def can_export(g, w, b, c):
    if w.out_loads >= g.cat.trade["max_loads"]["sea" if w.role == "ship" else "land"]:
        return False
    return any(order(g, b, k) == "export" and city_buys(g, c, k) and b.goods.get(k, 0) >= unit(g, k)
               and _ledger_ok(g, w, b, k, "out") for k in _goods(g))


def can_import(g, w, b, c):
    if w.in_loads >= g.cat.trade["max_loads"]["sea" if w.role == "ship" else "land"]:
        return False
    return any(_import_ok(g, w, b, k, c) for k in _goods(g))


def _import_ok(g, w, b, k, c):
    """trade_import_ok 0x005B8EE0: import order, the post's stock + one load within limit (storage_cannot_accept),
    this trader's ledger below the limit (trade_ledger_full mode 7), the partner sells (quota left)."""
    room = g.cat.spec(b.key)["capacity"] - sum(b.goods.values())
    return (k not in NOT_TRADED and order(g, b, k) == "import" and city_sells(g, c, k) and room >= unit(g, k)
            and b.goods.get(k, 0) + unit(g, k) <= limit(g, b, k) and _ledger_ok(g, w, b, k, "in"))


def _next(g, b, key, ok):
    """Round-robin over the goods (the post's cursors +0x2E / +0x30)."""
    goods = _goods(g)
    cur = b.misc.get(key, -1)
    for i in range(1, len(goods) + 1):
        k = goods[(cur + i) % len(goods)]
        if ok(k):
            b.misc[key] = (cur + i) % len(goods)
            return k
    return None


def export_one(g, w, b, c):
    k = _next(g, b, "cur_exp", lambda k: order(g, b, k) == "export" and city_buys(g, c, k)
              and b.goods.get(k, 0) >= unit(g, k) and _ledger_ok(g, w, b, k, "out"))
    if k is None:
        return None
    b.goods[k] -= unit(g, k)
    price = good_price(g, k)
    g.city.treasury += price
    g.city.ledger["exports"] = g.city.ledger.get("exports", 0) + price
    state(g)["used"][c][k] = state(g)["used"][c].get(k, 0) + 1
    w.out_loads += 1
    _ledger(w, "out")[k] = _ledger(w, "out").get(k, 0) + 1
    _tally(g, "exported", k, unit(g, k))
    return k


def import_one(g, w, b, c):
    k = _next(g, b, "cur_imp", lambda k: _import_ok(g, w, b, k, c))
    if k is None:
        return None
    b.goods[k] = b.goods.get(k, 0) + unit(g, k)
    price = good_price(g, k)
    g.city.treasury -= price
    g.city.ledger["imports"] = g.city.ledger.get("imports", 0) - price
    state(g)["used"][c][k] = state(g)["used"][c].get(k, 0) + 1
    w.in_loads += 1
    _ledger(w, "in")[k] = _ledger(w, "in").get(k, 0) + 1
    _tally(g, "imported", k, unit(g, k))
    if k in g.cat.foods:                          # imported food this month (husbandry advisor)
        fi = g.sd("food_imp_month", {})
        fi[k] = fi.get(k, 0) + unit(g, k)
    return k


def _tally(g, side, k, n):
    t = g.sd("trade_totals", {"exported": {}, "imported": {}})
    t[side][k] = t[side].get(k, 0) + n


def describe(g):
    """Text: partners, their posts, quotas used this year, and trade totals."""
    st = state(g)
    lines = []
    for c, p in enumerate(partners(g)):
        b = post_of(g, c)
        where = f"{b.key} at ({b.x},{b.y})" if b else f"no {'dock' if p['route'] == 'sea' else 'trading post'}"
        used = st["used"][c]
        full = lambda k, q: " (quota reached until January)" if used.get(k, 0) >= q else ""
        buys = " ".join(f"{k} {used.get(k, 0)}/{q}{full(k, q)}" for k, q in p["buys"].items())
        sells = " ".join(f"{k} {used.get(k, 0)}/{q}{full(k, q)}" for k, q in p["sells"].items())
        lines.append(f"{p['name']} ({p['route']}): {where}\n  buys  {buys}\n  sells {sells}")
        if b:
            orders = ", ".join(f"{k} {m} {limit(g, b, k)}" for k, m in sorted(b.misc.get("orders", {}).items()))
            lines.append(f"  orders: {orders or 'none'}")
    lines.append("(quotas: loads a year, reset in January, trade_import_ok / city_sells 0x005B9930)")
    tot = getattr(g, "trade_totals", None)
    if tot:
        lines.append(f"exported (units, total): {tot['exported']}")
        lines.append(f"imported (units, total): {tot['imported']}")
    return "\n".join(lines)
