"""The empire's event queue (the exe's scenario-event records, world-map.md section 9), monthly dispatch.

An event is a dict: id, type, city (id), item, amount (loads for goods, drachmas, soldiers), state,
countdown (months), deadline (months), created (month index) and type-specific fields. Types (exe type
byte in brackets): gift_out (1, kind 9), request (1: a city asks the player), tribute_out (0x1E),
delivery (0x20: goods/money/troops the player asked for), refused (0x21), strike (0x22),
expedition (1, kind 9, item troops), invasion (2), offer (0x17 / 0x1D / 0x20 when it reaches the player: the
accept/postpone/decline dialog, offers.py), aid_troops (accepted defensive aid on the city map).
"""


def add(g, **ev):
    e = g.empire
    ev.setdefault("state", 0)
    ev.setdefault("created", g.month_index)
    ev["id"] = e.next_event
    e.next_event += 1
    e.events.append(ev)
    return ev


def live(g, type_=None, city=None):
    return [ev for ev in g.empire.events if ev["state"] != 10 and (type_ is None or ev["type"] == type_)
            and (city is None or ev.get("city") == city)]


def done(ev):
    ev["state"] = 10


def month(g):
    """month_events_dispatch 0x0046DFD0, once per month (our month start)."""
    from . import diplomacy, war, offers
    for ev in list(g.empire.events):
        if ev["state"] == 10:
            continue
        h = {"gift_out": diplomacy.gift_month, "delivery": diplomacy.delivery_month,
             "refused": diplomacy.refused_month, "request": diplomacy.request_month,
             "tribute_out": diplomacy.request_month, "strike": war.strike_month,
             "expedition": war.expedition_month, "invasion": war.invasion_month,
             "aid_troops": war.aid_month, "offer": offers.month}.get(ev["type"])
        if h:
            h(g, ev)
    g.empire.events = [ev for ev in g.empire.events if ev["state"] != 10 or g.month_index - ev["created"] < 24]
