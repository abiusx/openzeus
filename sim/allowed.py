"""Allowed buildings: an episode's allowed table (scenario +0x408, 100 flags -> 0x00902D30) and the exe's derivation
buildings_availability 0x00402B80 (-> DAT_00787178, the build menus' slots), rules in data/allowed.json.

A game without a table (g.allowed absent: our unrestricted open play sandbox_open, saves from before 10-31) allows
everything. The original's open plays (sandbox, sandbox2) start with their episode's table and player city, which
hide the carrot and onion farms and the urchin quay (docs/campaign-format.md "Open play"). The core calls:
  check(g, key)     Game.build / wall / bridge / avenues: None, or the refusal text
  unavailable(g)    export: the keys the build menus hide (None = no table)
  goods_list(g) / food_list(g)   the city's goods and food lists as rebuild_goods_lists 0x005BAAF0 builds them
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA = {}


def data():
    if not _DATA:
        _DATA.update(json.load(open(os.path.join(ROOT, "data", "allowed.json"))))
    return _DATA


def table(g):
    return g.__dict__.get("allowed")


def flag(g, i):
    t = table(g)
    return t is None or (0 <= i < len(t) and t[i] != 0)


# --- the city's goods (rebuild_goods_lists 0x005BAAF0) -----------------------------------------------------------

GOD_GOODS = {"oranges": "hera", "bronze": "hephaistos", "grapes": "dionysus", "wine": "dionysus",
             "olives": "athena", "olive_oil": "athena"}     # god_resource_available 0x005BA890 (ecx per case)


def resources(g):
    """FUN_00460B40(player city's world object, good): the raw goods the player's world city lists (+0xA8)."""
    from . import empire
    e = empire.get(g)
    try:
        return set(e.player().resources) if e is not None else set()
    except StopIteration:
        return set()


# FUN_00460F90 / FUN_005BA980: a finished good counts through its raw material (wine 0x15 -> grapes 0xC, olive oil
# 0x14 -> olives 0xD, armour 0x12 and sculpture 0x13 -> bronze 0xA)
RAW_OF = {"wine": "grapes", "olive_oil": "olives", "armor": "bronze", "sculpture": "bronze"}


def _stock_all(g):
    """FUN_0040F810 for every good in one pass: {good: stock in trade buildings + storehouses + granaries}."""
    t = {}
    for b in g.buildings.values():
        if b.kind in ("storage", "trade") and not g.cat.spec(b.key).get("endless"):
            for k, v in b.goods.items():
                t[k] = t.get(k, 0) + v
    return t


def _stock(g, k):
    """FUN_0040F810: the city's stock of a good (trade buildings + storehouses + granaries). Inside _memo: the
    totals taken once for the whole read (frames list the menus every tick: 12 scans of every building each)."""
    t = g.__dict__.get("_astock")
    return (t if t is not None else _stock_all(g)).get(k, 0)


class _memo:
    """One read of the lists / menus (goods_list, food_list, mark, unavailable): the stocks are taken once. Reads
    only, so nothing changes the stocks inside; nests (the outermost one sets and drops it)."""
    def __init__(self, g):
        self.g, self.mine = g, False

    def __enter__(self):
        if "_astock" not in self.g.__dict__:
            self.g.__dict__["_astock"], self.mine = _stock_all(self.g), True

    def __exit__(self, *a):
        if self.mine:
            self.g.__dict__.pop("_astock", None)


def _sold(g, k):
    """city_any_sells_listed 0x005BAA40: a city that exists or trades with us lists the good among its 4 sells
    (+0xC4) with a quota (+0x60)."""
    from . import empire
    e = empire.get(g)
    return e is not None and any(c.kind != "player" and (c.exists() or c.trading()) and (c.sells or {}).get(k)
                                 for c in e.cities.values())


def produces(g, k):
    """FUN_00460F90: the player's world city lists the good (FUN_00460B40, +0xA8); a finished good: a city sells it
    or its raw material, or the raw material is in stock (FUN_0040F810), else the city lists the raw material."""
    raw = RAW_OF.get(k)
    if raw is not None:
        if _sold(g, k) or _sold(g, raw) or _stock(g, raw):
            return True
        k = raw
    return k in resources(g)


def _event_names(g, k):
    """FUN_005BA980: a gift event (type 0x17) names the good: its item choices +6 / +8 / +0xA (the value group's
    a, b, c, whatever the group's form), or with flag 0x100 (dynamic) its resolved item +4; a finished good also
    through its raw material."""
    from . import scenario
    from .empire.model import GOOD_IDS
    gid = GOOD_IDS.get(k)
    for ev in scenario.events(g, 23):
        if ev["flags"] & scenario.DYNAMIC:
            if ev["item"] == gid:
                return True
        elif gid in ev["groups"]["item"][1:4]:
            return True
    raw = RAW_OF.get(k)
    return raw is not None and _event_names(g, raw)


def god_provides(g, k):
    """god_resource_available 0x005BA890: the god's sanctuary exists and is finished (+0xDA == 0)."""
    from . import gods
    god = GOD_GOODS.get(k)
    return god is not None and gods.built(g, gods.god_id(god))


def _tribute(g, k):
    """city_pays_tribute_good 0x005BAA90: a vassal or colony that exists pays tribute (mode 1) in the good."""
    from . import empire
    e = empire.get(g)
    return e is not None and any(c.kind != "player" and c.exists() and c.tribute.get("mode") == 1
                                 and c.relation in ("vassal", "colony") and c.tribute.get("good") == k
                                 for c in e.cities.values())


def _listed(g, k, food=False):
    """One good's test in rebuild_goods_lists: the city may produce it, a city sells it, a gift event carries it,
    a finished sanctuary provides it (goods list only, not the food list), a vassal or colony pays it as tribute,
    or the city holds some."""
    return (produces(g, k) or _sold(g, k) or _event_names(g, k) or (not food and god_provides(g, k))
            or _tribute(g, k) or _stock(g, k) > 0)


def _order():
    from .empire.model import GOOD_IDS
    return [k for k, v in sorted(GOOD_IDS.items(), key=lambda kv: kv[1]) if 1 <= v <= 22]


def goods_list(g):
    """g_goods_list: goods 1..22 (our keys, exe order) the city can have now, plus the goods once listed (flags
    0x00FE93EC: g.goods_listed, set by mark()). Read only (frames call it); the exe also rebuilds the list when a
    building's window opens (FUN_005717D0), which marks nothing more than what a read shows here.
    Ours: a Poseidon good is not listed while Poseidon is off (economy.good_on)."""
    from .systems.economy import good_on
    once = g.__dict__.get("goods_listed", ())
    with _memo(g):
        return [k for k in _order() if (k in once or _listed(g, k)) and good_on(g, k)]


def food_list(g):
    """g_city_food_list: the foods 1..8 by the same tests (no god), plus the foods once listed (0x00FEB0D2 =
    City.foods_listed, kept by sim/systems/agora.py city_foods). Read only."""
    from .empire.model import FOODS
    with _memo(g):
        return [k for k in FOODS if k in g.city.foods_listed or _listed(g, k, food=True)]


def mark(g):
    """rebuild_goods_lists's marks 0x00FE93EC[good] = 1: a good once on the list stays on it (the exe rebuilds at
    the month change after month_events_dispatch, at episode start / load (0x00420390) and when a storage building
    is created (storage_create 0x00494960)). Only in a game with an allowed table: our open play sandbox_open
    lists every good some building makes (export.goods_list), and keeps no marks."""
    if table(g) is None:
        return
    once = g.sd("goods_listed", set())
    with _memo(g):
        once.update(k for k in _order() if k not in once and _listed(g, k))


# --- the derivation --------------------------------------------------------------------------------------------

def _guild(g):
    """Case 0x38 (artisans' guild): with max sanctuaries != 0, a god that may still get one (god_can_be_jealous)
    or has a sanctuary; else (Poseidon monuments) a monument slot in use: not ported (Poseidon)."""
    from . import gods
    st = gods.state(g)
    if st.get("free"):
        return True
    if not st.get("max_sanct"):
        return False
    return any(gods.can_be_jealous(g, i) or gods.sanctuary(g, i) is not None for i in range(14))


def _lists(g, ctx):
    if "goods" not in ctx:
        ctx["goods"], ctx["food"] = set(goods_list(g)), set(food_list(g))
    return ctx["goods"], ctx["food"]


def _holds(g, c, ctx):
    from . import gods
    if "palace" not in ctx:                     # one read (unavailable: ~90 rules): the building scans once
        ks = {b.key for b in g.buildings.values()}
        ctx["palace"], ctx["venue"] = "palace" in ks, bool(ks & {"stadium", "museum"})
    for k, v in c.items():
        if k in ("flag", "flag2"):
            if not flag(g, v):
                return False
        elif k == "resource":
            if v not in resources(g):
                return False
        elif k == "goods":
            gl = _lists(g, ctx)[0]
            if not all(x in gl for x in v):
                return False
        elif k == "food_or_goods":
            gl, fl = _lists(g, ctx)
            if not any(x in gl or x in fl for x in v):
                return False
        elif k == "sanctuary":
            if not gods.built(g, gods.god_id(v)):
                return False
        elif k == "poseidon":
            if bool(getattr(g, "poseidon", False)) != v:
                return False
        elif k == "no_palace":
            if ctx["palace"]:
                return False
        elif k == "no_venue":
            if ctx["venue"]:
                return False
        elif k == "guild":
            if not _guild(g):
                return False
        else:
            raise ValueError(f"data/allowed.json: unknown condition {k}")
    return True


def available(g, key, ctx=None):
    """DAT_00787178 for the slot of building `key` (True without a table or a rule)."""
    if table(g) is None:
        return True
    r = data()["rules"].get(key)
    if r is None:
        return True
    ctx = {} if ctx is None else ctx
    return any(_holds(g, c, ctx) for c in r.get("any", [r]))


def unavailable(g):
    """The building keys the build menus leave out (None: no table, everything as open play)."""
    if table(g) is None:
        return None
    ctx = {}
    with _memo(g):
        return sorted(k for k in data()["rules"] if not available(g, k, ctx))


def check(g, key):
    """None when key may be built, else why not (the exe's menus never offer it; ours refuses the command)."""
    if available(g, key):
        return None
    spec = g.cat.buildings.get(key, {})
    return f"{spec.get('name', key)} is not available in this episode (its allowed buildings, data/allowed.json)"
