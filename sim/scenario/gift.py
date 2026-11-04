"""Type 23, Gift (event_gift 0x00474A80): goods or drachmas from a city, scheduled or chained (the open-play
rewards of Open Play Sandbox 2). docs/logic/events.md "Gift".

The exe: on its date (state 0, not active, flags & 0x20001 == 0) the record turns active and the offer dialog
(incoming_goods_dialog 0x004745E0) is posted; it is offered again every month until answered: accepted (state 6:
money to the treasury and "gifts received", goods into storage), refused (7) or forfeited (8); then state 10,
done. Item 25 (food) picks one food once (byte +0x74: city_pick_food 0x0042D140, wheat when none). A gift whose
city does not exist does nothing (city_exists).

Ours: the offer itself is sim/empire/offers.py's (the same dialog for every incoming gift; track 1B); this record
stays active until that offer is answered, then it is done. Without the empire module there are no cities, so
nothing happens (as city_exists fails).
"""
from sim import scenario
from sim.empire.model import FOODS, GOOD_IDS

FOOD_ID, WHEAT = 25, 7


def _city(g, ev):
    e = getattr(g, "empire", None)
    return e.cities.get(ev["city"]) if e is not None else None


def gift(g, ev):
    c = _city(g, ev)
    if c is None:
        return
    if ev["item"] == FOOD_ID and ev["b74"] == 0:
        foods = [f for f in FOODS if c.sells.get(f, 0) > 0][:4]       # the city's food list (+0xC4, goods 1..8)
        f = foods[(scenario.rng15(g) & 0x7F) % len(foods)] if foods else None
        ev["b74"] = GOOD_IDS[f] if f else WHEAT
    if ev["state"] == 10:
        return
    if not ev["active"]:
        if ev["flags"] & (scenario.TEMPLATE | scenario.DISABLED) or not scenario.due(g, ev, any_flags=True):
            return
        ev["active"] = 1
        _offer(g, ev, c)
        return
    off = ev.get("gift_offer")
    if off is None or _answered(g, off):
        ev.update(state=10, active=0)
        scenario.done(g, ev)


def _good(ev):
    item = ev["b74"] if ev["item"] == FOOD_ID else ev["item"]
    return {v: k for k, v in GOOD_IDS.items()}.get(item)


def _offer(g, ev, c):
    good = _good(ev)
    scenario.log(g, f"event #{ev['id']}: gift of {ev['amount']} {good} from {c.name}")
    try:
        from sim.empire import offers
    except ImportError:                                # before sim/empire/offers.py: auto-accepted
        offers = None
    if offers is not None and hasattr(offers, "create"):
        o = offers.create(g, "gift", c, good, ev["amount"])
        ev["gift_offer"] = o["id"]
    else:
        from sim.empire import diplomacy
        diplomacy.city_gift(g, c, good, ev["amount"])
        ev["gift_offer"] = None


def _answered(g, oid):
    e = getattr(g, "empire", None)
    if e is None:
        return True
    o = next((x for x in e.events if x["id"] == oid), None)
    return o is None or o["state"] == 10


scenario.register(23, gift, owner="1G gifts")
