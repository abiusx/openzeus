"""Scenario event types 13 / 14 (demand increase / decrease: event_demand_increase 0x00472540, _decrease
0x004727C0) and 21 / 22 (supply increase / decrease: event_supply_increase 0x00472030, _decrease 0x004722B0),
registered with sim/scenario (PLUGINS). Track 1L-5.

A city's yearly quota of a good (WorldCity +0x60 + good, shared by its buy and sell lists: ours `buys` / `sells`)
moves one step on the levels 0 / 12 / 24 / 36:
  - the city must buy (demand, FUN_00460B80 city_in_buy_list) or sell (supply, FUN_00460BB0) the good (+4), else the
    record is done at once;
  - not due, WARN and not WARNED: when the city is a trading partner and the step is possible, the oracle's
    prediction (title, prediction phrase) and WARNED;
  - due: DONE; increase: < 12 -> 12, < 24 -> 24, < 36 -> 36; decrease: 0 stays, <= 12 -> 0, < 25 -> 12, else 24 (and
    trade_status_recheck); then the history record (0xBE1 / 0xBDF / 0xBE2 / 0xBE0, the good) and, when the city is a
    trading partner and the record is not an end-of-episode one (0x20000), the message 0xE2 (title, announcement);
    then the chained record (not for 0x20000).
"""
from .. import scenario
from . import relations

# type -> (title, oracle prediction, announcement, history phrase)
PHRASES = {13: (0x306, 0x307, 0x308, 0xBE1), 14: (0x30E, 0x30F, 0x310, 0xBDF),
           21: (0x316, 0x317, 0x318, 0xBE2), 22: (0x31E, 0x31F, 0x320, 0xBE0)}


def step(q, up):
    if up:
        return 12 if q < 12 else 24 if q < 24 else 36
    return 0 if q <= 12 else 12 if q < 25 else 24


def handler(g, ev):
    t = ev["type"]
    up = t in (13, 21)
    e = getattr(g, "empire", None)
    c = e.cities.get(ev.get("city", -1)) if e is not None else None
    good = scenario.good(ev)
    lst = None if c is None else (c.buys if t in (13, 14) else c.sells)
    if lst is None or good not in lst:
        ev["flags"] |= scenario.DONE
        return
    title, pred, ann, hist = PHRASES[t]
    q = lst[good]
    possible = q < 36 if up else q != 0
    from .. import messages
    item, short = messages.item_words(good)
    if not scenario.due(g, ev):
        f = ev["flags"]
        if f & scenario.WARN and not f & scenario.WARNED and c.trading() and possible:
            messages.post(g, title, pred, city=c, item=item, itemshort=short)
            ev["flags"] |= scenario.WARNED
        return
    ev["flags"] |= scenario.DONE
    silent = bool(ev["flags"] & scenario.DISABLED)
    if possible:
        lst[good] = step(q, up)
        relations.note(g, c, hist, item=good)
        if c.trading() and not silent:
            messages.post(g, title, ann, city=c, item=item, itemshort=short)
        scenario.log(g, f"event #{ev['id']}: {c.name} {'buys' if t in (13, 14) else 'sells'} {good} {q} -> {lst[good]}")
    if not silent:
        tpl = scenario.get(g, ev.get("chain", -1))
        if tpl is not None and tpl["flags"] & scenario.TEMPLATE and tpl["id"] != ev["id"]:
            scenario.chain(g, ev)


for _t in PHRASES:
    scenario.register(_t, handler, owner="1L-5 demand / supply changes (sim/empire/quota_events.py)")
