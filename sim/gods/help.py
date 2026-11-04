"""Help and prayers (docs/logic/religion.md "Help and prayers").

gods_help_update 0x004E6B10, every month_advance call (our day):
    the month's help candidate (gods_month_update) helps if its sanctuary is built: god_help(cand, prayed 0, force 0)
    for every god: god_gifts_deliver (deliver_gifts: the gift's leftover into storage); a pending prayer -> god_help(g, 1, 1)
god_help 0x004E6630: if force or god_can_help -> the god's own function: its need (automatic help only), its
precondition, the god figure out of its sanctuary (god_figure_spawn), the figure's help action, cost
(god_help_cost 0x004E60B0) added to the prayer counter, the help message (0x00480590, PHRASE_<god>_help_*).
A prayer that cannot be answered now is queued: cost added once, prayer_pending, pending_months 1 (Zeus 2).

Ported effects (figures.py): Demeter (wheat / carrots / onions), Poseidon (urchin / fish), Artemis (meat): the god
walks from the sanctuary to the storage with the most room (FUN_004C44E0), the carriers behind (presentation), and
puts min(room, 3200) there; gifts.py: Zeus, Aphrodite, Apollo, Athena, Hephaestus, Dionysus, Hades; aid.py: Ares
(joins an expedition), Hermes (fulfils a request), Hera (gifts.py: restocks the agoras' vendors). Atlas (Poseidon) is
not ported: prayers to him are queued and lapse; see religion.md "What each god's help does".
"""
from . import T, state, rec, built, sanctuary, GODS, NAMES
from .month import log

FOODS = {1: ("urchin", "fish"), 2: ("wheat", "carrots", "onions"), 4: ("meat",)}
MIN_ROOM = {1: 3200, 2: 3200, 4: 2400}          # 0xC7F < room (Poseidon, Demeter); 0x95F < room (Artemis)
HELP_TITLE = {0: 0x6E4, 1: 0x6EC, 2: 0x6FC, 3: 0x70C, 4: 0x714, 5: 0x71C, 6: 0x72C, 7: 0x734, 8: 0x704, 9: 0x724,
              10: 0x73C, 11: 0x6F4, 12: 0xDC5, 13: 0xDCD}


def threshold(i):
    return T()["help_threshold"][i]


def cost(i, prayed):
    return T()["help_cost"][i][1 if prayed else 0]


def busy(g, i):
    """god_figure_busy 0x004E75E0: the god figure is on the map with an action in 0x0F..0x35 (helping)."""
    from . import figures
    w = figures.figure(g, i)
    return w is not None and w.task in figures.BUSY


def can_help(g, i):
    """god_can_help 0x004E6610."""
    return rec(g, i)["prayer"] <= threshold(i) and not busy(g, i)


def update(g):
    st = state(g)
    c = st["help_cand"]
    if c != -1 and built(g, c):
        god_help(g, c, False, False)
    for i in range(14):
        deliver_gifts(g, i)
        if rec(g, i)["pending"]:
            god_help(g, i, True, True)


def gift_leftover(g, i, a1, a2):
    """The god record's gift_amount_1 / _2 (+0x28 / +0x2C) and gift_active (+0x30): what the god's storage did not
    take (written when the gift is split: 0x004C4910 / 0x004C4F20 / 0x004C5420 / dionysus_satyrs_spawn at the
    start, Athena at her storehouse (0x29), Artemis with no prey (0x1B: 2400)); the help actions set gift_active
    every tick (ours: at once)."""
    r = rec(g, i)
    r["gift"] = [max(0, a1), max(0, a2)]
    r["gift_active"] = 1


def deliver_gifts(g, i):
    """god_gifts_deliver 0x004E6780 (gods_help_update, every day): with gift_active, the leftover goes into the
    city's storage (city_goods_add 0x00489230; what does not fit is lost): Poseidon urchins, then fish (each only
    when on the city's goods list); Demeter wheat / carrots / onions in goods-list order; Artemis meat; Athena oil
    (amount 1) and olives (amount 2); Dionysus wine. Then the record is cleared."""
    r = rec(g, i)
    if not r.get("gift_active"):
        return
    a1, a2 = (r.get("gift") or [0, 0])
    r["gift"], r["gift_active"] = [0, 0], 0
    if a1 < 1 and a2 < 1:
        return
    from ..systems import economy
    from .. import export
    if i == 1:
        gl = export.goods_list(g)
        for good in ("urchin", "fish"):
            if good in gl and a1 > 0 and good in g.cat.resources:
                a1 -= economy.goods_add(g, good, a1)
    elif i == 2:
        for good in export.goods_list(g):
            if good in ("wheat", "carrots", "onions") and a1 > 0:
                a1 -= economy.goods_add(g, good, a1)
    elif i == 4:
        economy.goods_add(g, "meat", a1)
    elif i == 8:
        economy.goods_add(g, "olive_oil", a1)
        economy.goods_add(g, "olives", a2)
    elif i == 10:
        economy.goods_add(g, "wine", a1)
    log(g, f"{NAMES[i]}'s gift: the rest into storage")


def god_help(g, i, prayed, force):
    if not (force or can_help(g, i)):
        return
    f = HELPERS.get(i)
    if f is None:
        if prayed:
            _queue(g, i, prayed)
        return
    f(g, i, prayed)


def _queue(g, i, prayed):
    r = rec(g, i)
    if not r["pending"]:
        r["prayer"] += cost(i, prayed)
        r["pending"] = 1
        r["pending_months"] = 2 if i == 0 else 1


def _granted(g, i, prayed, tile=None):
    st = state(g)
    r = rec(g, i)
    r["prayer"] += cost(i, prayed)
    r["pending"] = 0
    if st["help_cand"] == i:
        st["help_cand"] = -1
    from .. import alerts                        # god_message 0x00480590: alert 12 at the given tile, else (-1) at
    f = g.walkers.get(r["figure"]) if tile is None and r.get("figure") else None   # the god's figure, else none
    at = tile if tile is not None else (f.x, f.y) if f is not None else None
    alerts.raise_alert(g, alerts.GOD, at)
    from .. import messages
    # the message: FUN_00521A70(0xDE, 0, tile) with the same tile (the go-to button); Hermes' is 0xE0 (no button)
    meta = dict(at=[at[0], at[1]], kind=0xDE) if at is not None and i != 7 else None
    try:
        from . import voice                      # god_message 0x00480590: FUN_005A1050(god, 7)
        messages.post(g, HELP_TITLE[i], HELP_TITLE[i] + 1, voice=voice(g, i, 7), meta=meta)
    except KeyError:
        g.message(f"{NAMES[i]} helps the city")
    log(g, f"{NAMES[i]} helps ({'prayer' if prayed else 'automatic'})")


def food_need(g):
    """FUN_00569310 (hypothesis for the city fields): no food in the granaries (city+0x2B18 < 1), or less than half
    the population fed (city+0x296C * 100 / city+0x45A4 < 50)."""
    from ..systems import index
    food = sum(sum(v for k, v in s.goods.items() if g.cat.is_food(k)) for s in index.of(g, "storage")
               if g.cat.spec(s.key).get("accepts") == "food")
    if food < 1:
        return True
    pop = g.city.population
    if not pop:
        return False
    fed = sum(h.occupants for h in index.of(g, "house") if h.fed)
    return fed * 100 // pop < 50


def room_for(g, good):
    """FUN_00488A60 = city_goods_add(r, 1000000, dry run): room for the good in the city's storage."""
    from ..systems import economy
    return sum(economy.storage_room(g, s, good) for s in economy._stores(g) if s.kind == "storage")


def best_store(g, good):
    """FUN_004C44E0(good, &room, 1): the granary (food 1..8, order accept/get) with the most room for it."""
    from ..systems import economy, index
    best, room = None, 0
    for s in index.of(g, "storage"):
        if s.access is None or not s.employees:
            continue
        if g.cat.spec(s.key).get("accepts") != "food":
            continue
        if economy.order(g, s, good) not in ("accept", "get"):
            continue
        n = economy.storage_room(g, s, good)
        if n > room:
            best, room = s, n
    return best, room


def _food_god(g, i, prayed):
    """Poseidon 0x004E6DE0, Demeter 0x004E6FF0, Artemis 0x004E73F0."""
    if not prayed and not food_need(g):
        return
    if busy(g, i):
        return _queue(g, i, prayed) if prayed else None
    room = sum(room_for(g, k) for k in FOODS[i] if k in g.cat.resources)
    if room < MIN_ROOM[i]:
        return _queue(g, i, prayed) if prayed else None
    from . import figures
    w = figures.out_of_sanctuary(g, i)
    if w is None:
        return _queue(g, i, prayed) if prayed else None
    figures.start_food_help(g, w, i)
    _granted(g, i, prayed)


HELPERS = {1: _food_god, 2: _food_god, 4: _food_god}
from .gifts import HELPERS as _OTHERS                    # noqa: E402  (Zeus' strike, Aphrodite's houses: gifts.py)
HELPERS.update(_OTHERS)
from .aid import HELPERS as _AID                         # noqa: E402  (Ares' expedition, Hermes' requests: aid.py)
HELPERS.update(_AID)


def pray(g, i):
    """Pray button of the sanctuary window (0x00408DA0): 3 refused when the sanctuary needs a sacrifice
    (activity 0) or the god cannot help, 2 granted, 1 heard (queued)."""
    b = sanctuary(g, i)
    if b is None or not built(g, i):
        return 3, "no sanctuary"
    if not b.misc.get("activity", 0):
        return 3, "the sanctuary needs a sacrifice"
    ok = can_help(g, i)
    god_help(g, i, True, False)
    if ok and rec(g, i)["pending"]:
        return 1, f"{NAMES[i]} heard the prayer and will help later"
    if ok:
        return 2, f"{NAMES[i]} grants the prayer"
    return 3, f"{NAMES[i]} refuses (prayer counter {rec(g, i)['prayer']} > {threshold(i)})"


__all__ = ["update", "pray", "can_help", "GODS"]
