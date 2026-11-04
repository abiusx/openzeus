"""Scenario event type 2 (Invasion): `invasion_event_month` 0x00476E20, run by `invasions_month_update` 0x00504A30
before the monthly pass (scenario.invasions; not in editor mode). Registered with sim/scenario (PLUGINS). Track 1L-5.

Record: +0x58 (city2) the invading city, +0x1C (city) the entry point (1..8 land, 8 random; 9..16 sea, landing
+0x78), +0x0C the strength (invasion_spawn: soldiers = the nation's frequency x strength / 100), +0x2C the lead months
(2 by default), +0x38 the target class, +0x57 the warnings sent, +0x24 the chained record.

    already arrived (DONE): active (+0x32) and the city's forces gone from the map -> active 0; nothing else
    invasion_event_pending 0x00471F90: not 0x20001, not DONE, dated today or earlier and no more than lead months ago
    the city is not an active, shown rival (kind 2, +0xD4 == 1)            -> DONE (no invasion)
    m = event_months_until_due:
      0   -> invasion_spawn (the city's nation, strength, point, +0x38): the army on the map, alert 9 at its tile,
             message 0xDD 0x2D9 "city attacked" (the bribe 0x00476CF0 in it; the bribe button when it is less than
             the treasury); DONE; the chained record (always)
      24 / 12 / 6 -> the 2-year / 1-year / 6-month reminders 0x2D5 / 0x2D6 / 0x2D7 (bits 2 / 4 / 8 of +0x57)
      1   -> the 1-month warning 0x2D8 (0x2DD with auto-defend; bit 0x10)
      2+ and dated today -> the announcement 0x2D4 ([time_until_attack] = m; bit 1)
    each message once (+0x57), type 0xE0, title 0x2D2. A city that conquered the player (tribute mode +0xE0 == 2)
    uses the "last chance" family (+0xA73: 0xD45..); reason 0x2DB "no reason", or 4 "weakness" with flag 0x10.
Ours: the army is sim/military's (invaders.invade, quiet; the invasion keeps `sev` = the record's index). With the
military module off nothing spawns (logged; the record is done).
"""
from .. import scenario
from . import eventmsg

LAST_CHANCE = 0xA73
WARN = {24: (2, 0x2D5), 12: (4, 0x2D6), 6: (8, 0x2D7)}


def pending(g, ev):
    """invasion_event_pending 0x00471F90."""
    if ev["flags"] & (scenario.DISABLED | scenario.TEMPLATE | scenario.DONE):
        return False
    y, m = scenario.today(g)
    el = (y - ev["year"]) * 12 - ev["month"] + m
    return 0 <= el <= ev.get("lead", 0)


def _on_map(g, ev, c):
    from ..military import invaders
    return any(inv.get("sev") == ev["id"] or (c is not None and inv.get("city") == c.id)
               for inv in invaders.invasions(g).values())


def handler(g, ev):
    c = eventmsg.city(g, ev.get("city2"))
    if ev["flags"] & scenario.DONE:
        if ev.get("active") and (c is None or not _on_map(g, ev, c)):
            ev["active"] = 0
        return
    if c is None or not pending(g, ev):
        return
    if not (c.exists() and c.kind == "foreign" and c.relation == "rival"):     # kind 2, +0xD4 == 1, shown, active
        ev["flags"] |= scenario.DONE
        return
    last = LAST_CHANCE if c.tribute.get("mode") == 2 else 0
    reason = 4 if ev["flags"] & 0x10 else 0x2DB
    title = 0x2D2 + last
    m = scenario.months_until_due(g, ev)
    if m == 0:
        inv = spawn(g, ev, c)
        ev["flags"] |= scenario.DONE
        if inv is not None:
            from ..military import invaders
            eventmsg.post(g, title, 0x2D9 + last, ev, reason_id=reason, c=c,
                          bribe_amount=invaders.bribe_cost(g, inv))
        scenario.chain(g, ev)
        return
    if m == 1:
        from ..military import navy
        bit, body = 0x10, (0xD4B if last else 0x2D8) + (5 if navy.auto_defend(g) else 0)
    elif m in WARN:
        bit, body = WARN[m][0], WARN[m][1] + last
    else:
        if m < 2 or not scenario.due(g, ev, any_flags=True):        # events_date_check(1): dated today
            return
        bit, body = 1, 0x2D4 + last
    if not ev.get("warned_bits", 0) & bit:                            # +0x57
        ev["warned_bits"] = ev.get("warned_bits", 0) | bit
        eventmsg.post(g, title, body, ev, reason_id=reason, c=c, time_until_attack=m)


def spawn(g, ev, c):
    """invasion_spawn 0x00504600 (city +0xCC nation, +0x0C strength, +0x1C point, +0x38): sim/military; sets the
    record active (+0x32) and returns the invasion id, or None."""
    from .. import military
    if not military.on(g):
        scenario.log(g, f"event #{ev['id']}: invasion from {c.name} (military module off: none)")
        return None
    pt = ev.get("city", 8)
    adapter = dict(id=None, city=c.id, amount=ev.get("amount", 0), landing=ev.get("landing", 0))
    inv_id = military.invade(g, adapter, pt if 1 <= pt <= 16 else 8, target_class=ev.get("b38", 10), quiet=True)
    if inv_id is None:
        return None
    from ..military import invaders
    inv = invaders.invasions(g).get(inv_id)
    if inv is not None:
        inv["sev"] = ev["id"]
    ev["active"] = 1
    scenario.log(g, f"event #{ev['id']}: invasion from {c.name}, strength {ev.get('amount', 0)}, point {pt}")
    return inv_id


def disembarked(g, i):
    """FUN_00461AB0 (the first transport of record i unloads, FUN_004D3740): once per record (+0x57 bit 0x40), for
    subtype (+0x04, our "item") 1 or 2 only: message 0xDD title 0x2D2, body 0x2DC "has landed on our shores", reason
    4 "weakness" (flag 0x10) or 0x2DB (subtype 1 with flag 0x20: FUN_0047EC90's reason, not ported: 0x2DB)."""
    ev = scenario.get(g, i)
    if ev is None or ev["type"] != 2 or ev.get("warned_bits", 0) & 0x40 or ev.get("item") not in (1, 2):
        return
    reason = 4 if ev.get("item") == 1 and ev["flags"] & 0x10 else 0x2DB
    ev["warned_bits"] = ev.get("warned_bits", 0) | 0x40
    eventmsg.post(g, 0x2D2, 0x2DC, ev, reason_id=reason)


def next_pending(g):
    """(months, point, landing) of the soonest pending scenario invasion (g_months_to_next_invasion's share of type-2
    records, for sim/military's alarm month); None when none."""
    best = None
    for ev in scenario.events(g, 2):
        c = eventmsg.city(g, ev.get("city2"))
        if c is None or not pending(g, ev):
            continue
        m = scenario.months_until_due(g, ev)
        if best is None or m <= best[0]:
            best = (m, ev.get("city", 8), ev.get("landing", 0))
    return best


scenario.register(2, handler, owner="1L-5 invasions (sim/empire/invasion_events.py)")
