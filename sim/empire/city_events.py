"""Scenario event types 8 / 9 (wage increase / decrease), 12 (clay pit flood), 15 / 16 (price increase / decrease),
17 / 18 (favour increase / decrease) and 20 (rival army away), registered with sim/scenario (PLUGINS). Track 1L-5.

All run on their date (events_date_check 0x00471F00, scenario.due): done (flag 4), the change, the message (0xE0;
prices 0xE3 with the amount and the good), the chained record (FUN_004694A0 + event_chain_trigger). Before the date,
a record flagged WARN (0x40) and not WARNED gets the oracle's prediction once (wages, prices).

- 8 / 9 `event_wage_increase` 0x00472F00 / `event_wage_decrease` 0x004730A0: the wage level 0x00FE9664 (30 at
  city_record_reset 0x00566950; nothing else reads it: a Pharaoh leftover, so only the messages show) += / -= amount
  while it stays < 46 / > 4; prediction 0x337 / 0x33F, announcement 0x338 / 0x340 (title 0x336 / 0x33E); the chain
  runs even when the change does not. Ours: g.wage_expectation (absent until an event).
- 12 `event_clay_pit_flood` 0x004733F0: done, nothing else (Pharaoh).
- 15 / 16 `event_price_increase` 0x00472B20 / `_decrease` 0x00472D00: goods_price[item] += amount; decrease: when the
  price is > 0, price - amount, or 2 when amount >= price. Message 0x328 / 0x330 (title 0x326 / 0x32E) and the chain
  only when the record is not an end-of-episode one (0x20000); prediction 0x32B / 0x333. Ours: sim/systems/trade.py
  set_price (g.prices).
- 17 / 18 `event_favor_increase` 0x0046E840 / `_decrease` 0x0046E970: message 0x386/0x387 (0x38C/0x38D), then the city
  (when it exists, FUN_0046E140) attitude +/- amount (city_attitude_add, clamped 0..100, no history row).
- 20 `event_rival_army_away` 0x00474160: done; the city exists, is a rival (+0xD4 == 1) and +0x60 == 0: message
  0x43A/0x43C, city_army_away_12 0x0042E230 (troops still away from an earlier one come home first; then 3/5 of the
  army, as a byte, goes away for 12 months: +0xCA = 12, +0xCB = n, away_b += n, army -= n; relations.monthly brings
  them back), the chain.
"""
from .. import scenario
from . import eventmsg

WAGE0 = 30


def _chain(g, ev):
    t = scenario.get(g, ev.get("chain", -1))
    if t is not None and t["flags"] & scenario.TEMPLATE and t["id"] != ev["id"]:      # FUN_004694A0
        scenario.chain(g, ev)


def _warn(ev):
    f = ev["flags"]
    return bool(f & scenario.WARN) and not f & scenario.WARNED


def wage(g, ev):
    up = ev["type"] == 8
    w = g.__dict__.get("wage_expectation", WAGE0)
    title = 0x336 if up else 0x33E
    n = w + ev["amount"] if up else w - ev["amount"]
    ok = n < 0x2E if up else n > 4
    if not scenario.due(g, ev):
        if _warn(ev) and ok:
            eventmsg.post(g, title, title + 1, ev, reason_id=0x339 if up else 0x341)
            ev["flags"] |= scenario.WARNED
        return
    ev["flags"] |= scenario.DONE
    if ok:
        g.wage_expectation = n
        eventmsg.post(g, title, title + 2, ev, reason_id=0x339 if up else 0x341)
        scenario.log(g, f"event #{ev['id']}: wage expectation {w} -> {n}")
    _chain(g, ev)


def clay_pit_flood(g, ev):
    if scenario.due(g, ev):
        ev["flags"] |= scenario.DONE


def price(g, ev):
    from ..systems import trade
    up = ev["type"] == 15
    title = 0x326 if up else 0x32E
    good = scenario.good(ev)
    if not scenario.due(g, ev):
        if _warn(ev):
            eventmsg.post(g, title, title + 5, ev, reason_id=title + 3)
            ev["flags"] |= scenario.WARNED
        return
    ev["flags"] |= scenario.DONE
    if good is None:
        return
    p = trade.price(g, good)
    if up:
        new = p + ev["amount"]
    else:
        if p <= 0:
            return
        new = p - ev["amount"] if ev["amount"] < p else 2
    trade.set_price(g, good, new)
    scenario.log(g, f"event #{ev['id']}: price of {good} {p} -> {new}")
    if not ev["flags"] & scenario.DISABLED:
        eventmsg.post(g, title, title + 2, ev, reason_id=title + 3)
        _chain(g, ev)


def favor(g, ev):
    if not scenario.due(g, ev):
        return
    up = ev["type"] == 17
    title = 0x386 if up else 0x38C
    eventmsg.post(g, title, title + 1, ev, reason_id=title + 2)
    c = eventmsg.city(g, ev.get("city"))
    if c is not None and c.exists():                       # FUN_0046E140
        c.attitude = max(0, min(100, c.attitude + (ev["amount"] if up else -ev["amount"])))
    ev["flags"] |= scenario.DONE
    _chain(g, ev)


def army_away(c):
    """city_army_away_12 0x0042E230."""
    if c.troops_return[0]:
        c.away[1] -= c.troops_return[1]
        c.army += c.troops_return[1]
    n = (c.army * 3 // 5) & 0xFF                              # a byte (+0xCB)
    c.troops_return = [12, n]
    c.away[1] += n
    c.army -= n


def rival_army_away(g, ev):
    if not scenario.due(g, ev):
        return
    ev["flags"] |= scenario.DONE
    c = eventmsg.city(g, ev.get("city"))
    if c is None or not c.exists() or c.relation != "rival" or ev.get("kind", 0) != 0:
        return
    army_away(c)
    eventmsg.post(g, 0x43A, 0x43C, ev, reason_id=0x43D, c=c)
    scenario.log(g, f"event #{ev['id']}: {c.name} sends {c.troops_return[1]} soldiers away for 12 months")
    _chain(g, ev)


OWNER = "1L-5 city events (sim/empire/city_events.py)"
for _t in (8, 9):
    scenario.register(_t, wage, owner=OWNER)
scenario.register(12, clay_pit_flood, owner=OWNER)
for _t in (15, 16):
    scenario.register(_t, price, owner=OWNER)
for _t in (17, 18):
    scenario.register(_t, favor, owner=OWNER)
scenario.register(20, rival_army_away, owner=OWNER)
