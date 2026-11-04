"""Gifts, requests, tribute and the cities' own gifts (world-map.md 4.1-4.3, 6.2-6.5). Incoming goods are
auto-accepted (the exe's accept/refuse/postpone dialog has an auto-accept option); what does not fit in
storage is lost, as in the exe."""
import math

from . import events, model, relations
from .model import MONEY, TROOPS, FOOD, STRIKE, FOODS, units

GIFT_UNITS = {"small": 400, "medium": 800, "large": 1600}          # gift_size_units 0x00462540
GIFT_MONEY = {"small": 500, "medium": 1000, "large": 2500}
GIFTABLE = [k for k, i in model.GOOD_IDS.items() if 1 <= i <= 21 and i != 15] + [MONEY]   # 0x004624C0
REQUESTABLE = [k for k, i in model.GOOD_IDS.items() if 9 <= i <= 21] + [MONEY, TROOPS, FOOD, STRIKE]   # 0x00462500
MONEY_GIFT_R = ((0.5, 0.66, 1.0), (0.33, 0.5, 0.8), (0.2, 0.33, 0.6), (0.15, 0.25, 0.4))   # 0x00632F00
OTHERS_SHARE = {"ally": 0.15, "vassal": 0.2, "colony": 0.25}
AID_PCT = (100, 75, 67, 50, 33)                    # 0x005EC4E8 city_pick_aid_good
MONEY_GIFT_Q = (5, 4, 3, 2.5, 2)                   # 0x005EC648 city_money_gift_amount
TRIBUTE_MULT = (1.0, 1.5, 2.0, 2.5, 3.0)           # 0x005EC4C0
REQ_MONEY = (1000, 800, 600, 500, 400)             # 0x00633340 (x wealth)
REQ_GOODS = (1.0, 0.75, 0.66667, 0.5, 0.33333)     # 0x00633318 (x quota)
# attitude cost of asking (0x0047FD90; tables 0x006332AC/D0/F4): class -> (self, same-class others)
ASK_COST = {"goods": {"ally": (-10, -2), "rival": (-20, -5), "vassal": (-15, -5), "colony": (-10, -5), "parent": (-10, 0)},
            TROOPS: {"ally": (-40, -5), "rival": (-100, -100), "vassal": (-30, -5), "colony": (-25, -5), "parent": (-25, 0)},
            STRIKE: {"ally": (-50, -5), "rival": (-100, -100), "vassal": (-35, -10), "colony": (-30, -5), "parent": (-30, 0)}}
# city requests: attitude by outcome (0x0046FFA0, tables 0x00632F60..0x006331A0); columns
# ally-self, ally-others, rival-self, rival-others, vassal/colony-self, -others, parent-self
REQ_ATT = {0: {2: (25, 3, 20, 0, 27, 4, 25), 3: (18, 2, 10, 0, 22, 3, 20), 4: (-10, -1, -10, 0, -15, -2, -15), 5: (-20, -2, -25, 0, -25, -5, -25)},
           5: {2: (30, 8, 20, 5, 30, 8, 35), 3: (25, 5, 15, 0, 25, 4, 30), 4: (-15, -2, -15, 0, -20, -5, -20), 5: (-25, -10, -25, -5, -25, -10, -30)},
           4: {2: (25, 3, 5, 0, 20, 4, 20), 3: (15, 2, 2, 0, 15, 3, 15), 4: (-5, -1, -10, 0, -5, -2, -10), 5: (-10, -2, -15, 0, -10, -5, -20)},
           3: {2: (20, 3, 15, 0, 15, 4, 15), 3: (15, 2, 10, 0, 10, 3, 10), 4: (-5, -1, -10, 0, -5, -2, -5), 5: (-10, -2, -15, 0, -10, -5, -10)},
           6: {2: (22, 3, 15, 0, 23, 6, 28), 3: (16, 2, 10, 0, 17, 5, 20), 4: (-12, -1, -20, 0, -12, -4, -12), 5: (-18, -2, -25, 0, -23, -7, -25)}}
TRIBUTE_OUT_ATT = {2: 10, 3: 5, 4: -35, 5: -70}
REQ_HISTORY = {0: 0xC36, 3: 0xC46, 4: 0xC06, 5: 0xC16, 6: 0xC26}    # *_early_history_D by request kind (0x0046FFA0)
TONE = {"ally": 0, "rival": 1, "vassal": 2, "colony": 2, "parent": 3}
KIND_NAMES = {0: "a request", 3: "a festival", 4: "a building project", 5: "famine relief", 6: "financial help"}


def price(g, good):
    from ..systems import trade
    return max(trade.price(g, good), 1)


def stock(g, item):
    from ..systems import economy
    if item == MONEY:
        return g.city.treasury
    if item == FOOD:
        return sum(economy.city_stock(g, f) for f in FOODS)
    return economy.city_stock(g, item)


def _others(g, c, share):
    for o in g.empire.cities.values():
        if o is not c and o.visible and o.active and o.cls() == c.cls() and share:
            yield o


# --- the player's gift (4.2) ---

def gift_sizes(g, good):
    """Sizes the gift dialog offers: as far as the stock covers (none below small)."""
    have = stock(g, good)
    tab = GIFT_MONEY if good == MONEY else GIFT_UNITS
    return [s for s, n in tab.items() if have >= n]


def gift(g, c, good, size):
    """player_gift_send 0x0047FBB0: pay now, arrive in 1..4 months."""
    from ..systems import economy
    if not c.exists():
        raise ValueError(f"{c.name}: no gifts possible")
    if good not in GIFTABLE:
        raise ValueError(f"'{good}' cannot be given ({', '.join(GIFTABLE)})")
    if size not in gift_sizes(g, good):
        raise ValueError(f"not enough {good} for a {size} gift (have {stock(g, good)})")
    if c.gift_fatigue.get(good, 0) > 39:
        g.message(f"{c.name} refuses your gift: it simply doesn't need more {good}.")
        return f"{c.name} refuses the gift (too many gifts of {good} lately)"
    if good == MONEY:
        amount = GIFT_MONEY[size]
        g.city.treasury -= amount
        g.empire.totals["gifts_given"] += amount
    else:
        amount = model.loads(good, GIFT_UNITS[size])
        economy.goods_remove(g, good, GIFT_UNITS[size])
    ev = events.add(g, type="gift_out", city=c.id, item=good, amount=amount, state=3,
                    countdown=g.rng.randrange(4) + 1, deadline=48, size=size)
    return f"{size} gift of {amount} {good if good == MONEY else 'loads of ' + good} on its way to {c.name} ({ev['countdown']} months)"


def gift_month(g, ev):
    ev["countdown"] -= 1
    if ev["countdown"] < 1:
        receive_gift(g, g.empire.cities[ev["city"]], ev["item"], ev["amount"], ev.get("size"))
        events.done(ev)


def receive_gift(g, c, good, amt, size=None):
    """city_receive_gift 0x0046FC00 (empire.md): attitude gain, gift fatigue, same-class cities share; then the
    city's thanks (zeus.c ~78596, the gift_out event's arrival: message 0xDF, pops up, by the case 0 money, 1 needed,
    2 not needed, 3 produced there: PHRASE_gift_received_* 0xB1A / 0xB22 / 0xB2A / 0xB32, announcement + 1;
    bugs.md 328)."""
    if good == MONEY:
        v = math.sqrt(amt)
        b = 1.0 if c.wealth == 0 else 1.0 / c.wealth
        t = g.city.treasury
        ti = 0 if t < 5000 else 1 if t <= 10000 else 2 if t <= 20000 else 3
        ai = 0 if amt <= 500 else 1 if amt <= 1000 else 2
        a = MONEY_GIFT_R[ti][ai]
        word = "gratefully accepts your gift of money"
        phrase, case = 0xBF1, 0                        # city_receive_gift: the history phrase by the case
    else:
        v = math.sqrt(price(g, good)) * (amt * 400 * 0.01 if good == "sculpture" else amt * 100 * 0.01)
        a = 0.3
        if good in c.sells:
            b, word, phrase, case = 0.075, f"produces {good} itself", 0xBF4, 3
        elif good in c.buys:
            b, word, phrase, case = 0.4, f"needed the {good}", 0xBF2, 1
        else:
            b, word, phrase, case = 0.15, f"doesn't need {good}", 0xBF3, 2
    k = c.gift_fatigue.get(good, 0)
    dv = 1 if k < 16 else 2 if k < 24 else 4 if k < 32 else 8 if k < 40 else 10
    gain = min(int(a * b * v / dv), 100)
    c.gift_fatigue[good] = min(k + 12, 48)
    relations.attitude_add(g, c, gain, phrase, 0, good, always=True)
    for o in _others(g, c, OTHERS_SHARE.get(c.cls())):
        relations.attitude_add(g, o, int(gain * OTHERS_SHARE[c.cls()]), phrase, relations.REL.get(o.cls(), 0), good)
    from .. import messages
    long, short = messages.item_words(good)
    sizes = messages._data()["history"].get("gift_size", [])
    k = list(GIFT_UNITS).index(size) if size in GIFT_UNITS else -1
    messages.post(g, 0xB1A + 8 * case, 0xB1B + 8 * case, city=c, item=long, itemshort=short,
                  gift_size=sizes[k] if 0 <= k < len(sizes) else "")
    return gain


# --- the player's request (4.1) ---

def threshold(c, item):
    """city_request_threshold 0x0042DD50: class code 0 request, 1 demand, 2 order, 3 requisition;
    -1 never, -2 not regarded highly enough."""
    k, a = c.cls(), c.attitude
    food = item == FOOD or item in FOODS
    if k == "rival":
        if a > 89 or (a >= 81 and food):
            return 0
        return 1 if (food or item == MONEY or item not in (TROOPS, STRIKE)) else -1
    need = {"ally": {"goods": 50, TROOPS: 81, FOOD: 41, STRIKE: 90},
            "vassal": {"goods": 31, TROOPS: 41, FOOD: 21, STRIKE: 50}}
    row = need["ally"] if k == "ally" else need["vassal"] if k in ("vassal", "colony", "parent") else None
    if row is None:
        return -1
    key = FOOD if food else item if item in (TROOPS, STRIKE) else "goods"
    if a < row[key]:
        return -2
    return {"ally": 0, "vassal": 2, "colony": 2, "parent": 3}[k]


def best_food(c):
    ok = [f for f in FOODS if c.sells.get(f, 0) > 0 and c.request_fatigue.get(f, 0) < 21]
    return max(ok, key=lambda f: c.sells[f]) if ok else None


def can_request(g, c, item):
    """city_can_request 0x0042DF90 -> (threshold class, code): code 3 = can ask, 2 = not regarded highly
    enough, 1 = can't spare troops, 0 = no surplus, -1 = not offered (the exe returns false: no row in the
    request dialog)."""
    if not c.exists() or c.rebellion:
        return -1, -1
    thr = threshold(c, item)
    if item in (TROOPS, STRIKE):
        # 0x0042DC80 / 0x0042DB70(0): ally, vassal, parent or colony; at home >= a fifth of the whole army and
        # 2/5 of it >= 1, else 1 ("can't spare"); 0x0042DF40: 1 too while the city's own troops request is open
        if c.cls() not in ("ally", "vassal", "parent", "colony"):
            return thr, -1
        if c.army < (c.army + sum(c.away)) // 5 or c.army * 2 // 5 < 1:
            return thr, 1
        if any(ev["type"] in ("request", "tribute_out") and ev.get("item") == TROOPS for ev in events.live(g, None, c.id)):
            return thr, 1
    elif item == FOOD:
        if not best_food(c):
            return thr, 0 if any(c.sells.get(f, 0) for f in FOODS) else -1
    elif item != MONEY:
        if not c.sells.get(item):
            return thr, -1
    if thr == -1:
        return thr, -1
    if thr == -2:
        return thr, 2
    if item != FOOD and c.request_fatigue.get(item, 0) > 20:
        return thr, 0
    return thr, 3


def refusal(g, c, item, thr, code):
    """Why can_request said no, in words (ours: the exe's request dialog just has no row for an item it cannot ask
    for, and greys a row with "no surplus" / "not regarded highly enough"; playtest haiku-3 #5)."""
    k = c.cls()
    if not c.exists() or c.rebellion:
        return "the city is gone or in rebellion"
    if code == 2 or thr == -2:
        need = {"ally": {"goods": 50, TROOPS: 81, FOOD: 41, STRIKE: 90},
                "vassal": {"goods": 31, TROOPS: 41, FOOD: 21, STRIKE: 50}}.get("ally" if k == "ally" else "vassal", {})
        key = FOOD if item == FOOD or item in FOODS else item if item in (TROOPS, STRIKE) else "goods"
        return f"you're not regarded highly enough (attitude {c.attitude}, needs {need.get(key, '?')})"
    if code == 1:
        return "it can't spare troops now (too few at home, or your last troops request is still open)"
    if code == 0:
        return "no surplus this year (asked too often; it recovers over the months)"
    if item == FOOD:
        sells = [f for f in FOODS if c.sells.get(f)]
        if not sells:
            others = [o.name + " (" + ", ".join(f for f in FOODS if o.sells.get(f)) + ")"
                      for o in g.empire.cities.values() if o is not c and o.visible and o.exists()
                      and o.cls() not in ("self", "distant") and any(o.sells.get(f) for f in FOODS)]
            return f"{c.name} sells no food" + (f"; cities that sell food: {', '.join(others)}" if others else "")
    if item in (TROOPS, STRIKE) and k not in ("ally", "vassal", "parent", "colony"):
        return f"only allies, vassals, colonies and the parent city send troops ({c.name} is {k})"
    if item not in (MONEY, FOOD, TROOPS, STRIKE) and not c.sells.get(item):
        return f"{c.name} doesn't sell {item}" + (f" (sells: {', '.join(c.sells)})" if c.sells else "")
    return f"a {k} city takes no request for {item}"


def request_amount(g, c, item):
    d = relations.diff(g)
    if item in (TROOPS, STRIKE):
        return c.army * 2 // 5
    if item == MONEY:
        return REQ_MONEY[d] * c.wealth
    return int(c.sells.get(item, 0) * REQ_GOODS[d])


def request(g, c, item, target=None):
    """city_player_request_create 0x0047FF80."""
    from . import war
    thr, code = can_request(g, c, item)
    if thr < 0 or code != 3:
        raise ValueError(f"{c.name}: can't request {item}: {refusal(g, c, item, thr, code)}")
    good = best_food(c) if item == FOOD else item
    if c.request_fatigue.get(good, 0) >= 21:
        raise ValueError(f"{c.name}: no surplus {good}")
    amount = request_amount(g, c, good)
    if amount <= 0:
        raise ValueError(f"{c.name}: nothing to spare")
    if item == STRIKE:
        t = target or (war.strike_targets(g, c) or [None])[0]
        if t is None or t not in war.strike_targets(g, c):
            raise ValueError(f"{c.name} will not strike that city ({', '.join(x.name for x in war.strike_targets(g, c))})")
        ev = events.add(g, type="strike", city=c.id, target=t.id, item=STRIKE, amount=amount)
        out = f"{c.name} sends {amount} soldiers against {t.name}"
    else:
        delay = g.rng.randrange(2) + 1
        typ = "delivery"
        if thr == 1:                                   # a rival's demand: backed by your strength?
            p1, _ = relations.player_strength(g)
            if p1 < max(1, c.army):
                typ = "refused"
        ev = events.add(g, type=typ, city=c.id, item=good, amount=amount, due=g.month_index + delay)
        if typ != "refused":
            c.request_fatigue[good] = c.request_fatigue.get(good, 0) + 15
        out = f"asked {c.name} for {amount} {good if good in (MONEY, TROOPS) else 'loads of ' + good} (in {delay} months)"
    ask_effects(g, c, item, good)
    return out


def ask_effects(g, c, item, good=None):
    """city_request_attitude_effects 0x0047FD90 (a request, or an ally joining an attack: item strike): the asked
    city and the others of its class lose attitude; history 0xC75 goods / 0xC76 troops / 0xC77 strike, item the good
    asked for (troops 0x18, strike 0x1B)."""
    key = item if item in (TROOPS, STRIKE) else "goods"
    phrase = {TROOPS: 0xC76, STRIKE: 0xC77}.get(item, 0xC75)
    good = good or item
    self_d, other_d = ASK_COST[key].get(c.cls(), (0, 0))
    relations.attitude_add(g, c, self_d, phrase, 0, good)
    for o in _others(g, c, other_d):
        relations.attitude_add(g, o, other_d, phrase, relations.REL.get(o.cls(), 0), good)


def delivery_month(g, ev):
    """0x004752A0 (type 0x20): on its date the goods, money or troops are offered (offers.py; plunder: raid)."""
    if g.month_index < ev["due"]:
        return
    from . import offers
    c = g.empire.cities[ev["city"]]
    events.done(ev)
    offers.create(g, "troops" if ev["item"] == TROOPS else "plunder" if ev.get("raid") else "granted",
                  c, ev["item"], ev["amount"])


def refused_month(g, ev):
    if g.month_index >= ev["due"]:
        c = g.empire.cities[ev["city"]]
        # event_demand_refused 0x004756B0: message 0xE0, title 0x3F2 "[city_name] refuses your demand", announcement
        # 0x3F3 ("So, [player_name], you want [amount] [item]? ...") (bugs.md 384)
        from .. import messages
        long, short = messages.item_words(ev["item"])
        messages.post(g, 0x3F2, 0x3F3, city=c, amount=ev.get("amount", 0), item=long, itemshort=short)
        events.done(ev)


def deliver(g, good, n):
    from ..systems import economy
    return economy.goods_add(g, good, n)


# --- requests by cities (6.5) and tribute out (6.4) ---

def city_request(g, c, item, amount, kind=0, deadline=12):
    """A city asks the player (scenario event type 1; the sandbox has none). Announced now."""
    ev = events.add(g, type="request", city=c.id, item=item, amount=amount, kind=kind, deadline=deadline,
                    countdown=deadline, announced=False)
    request_month(g, ev, start=True)
    from .. import scenario
    scenario.request_list_rebuild(g)                   # ours (a test command): listed at once
    return ev


def have_enough(g, ev):
    item = ev["item"]
    need = ev["amount"] if item == MONEY else sum(units(f, ev["amount"]) for f in [FOODS[0]]) if item == FOOD else units(item, ev["amount"])
    return stock(g, item) >= need


def _tmsg(g, ev, c, title, body, reason=-1, months=None):
    """A tribute-out message (FUN_00521A70 record 0xDF, no buttons): the block of FUN_00474500 for the record (+8
    amount, +0xA item, +0xC the months the handler means)."""
    from . import eventmsg
    rec = dict(id=ev["id"], type=0x1E, item=model.GOOD_IDS.get(ev["item"], 23), amount=ev["amount"], lead=ev["deadline"],
               year=0, month=0, city=c.id, state=ev["state"])
    over = {} if months is None else dict(time_allotted=months)
    eventmsg.post(g, title, body, rec, reason_id=reason, c=c, record=0xDF, time_until_attack=0, **over)


def tribute_out_month(g, ev):
    """event_tribute_out 0x004715C0 (record type 0x1E, created every January by city_schedule_tribute_out
    0x00477370 for a city whose claim +0xE0 is 2: drachmas, lead 2, active at once with countdown lead + 12, +0x33
    when the treasury covers it). Each month pass: the city must still claim it (+0xE0 == 2, +0xD4 == 1), else done.
    State 0: countdown - 1; == lead: 0x1C0 / 0x1C2 "[city] demands tribute" ([time_allotted] lead); == 6 with lead
    > 6: 0x1C3; < 1: overdue, countdown 12, state 1, 0x1C4. State 1: countdown - 1; == 6: 0x1C5; < 1: refused:
    attitude -70 (history 0xC59), 0x38C / 0x38D with reason 0x1C9, state 5. Not messaged this month, +0x33 clear,
    outstanding and the treasury covers it: 0xB6A / 0xB6B (reason 0xB6C; goods 0xB70 / 0xB71), +0x33. Paid (2 early,
    3 on time, 4 late; countdown 1..4): at 0 attitude +10 / +5 / -35 (0xC56..0xC58), 0x386 / 0x387 when it rose,
    0x38C / 0x38D when it fell, reasons 0x1C6..0x1C8, done."""
    c = g.empire.cities[ev["city"]]
    if not (c.exists() and c.tribute["mode"] == 2 and c.relation == "rival"):
        ev["state"] = 10
        events.done(ev)
        return
    st = ev["state"]
    if st in (2, 3, 4):
        ev["countdown"] -= 1
        if ev["countdown"] > 0:
            return
        d = TRIBUTE_OUT_ATT[st]
        relations.attitude_add(g, c, d, 0xC56 + st - 2, 0, ev.get("item"))
        reason = 0x1C6 + st - 2
        if d > 0:
            _tmsg(g, ev, c, 0x386, 0x387, reason)
        elif d < 0:
            _tmsg(g, ev, c, 0x38C, 0x38D, reason)
        else:
            _tmsg(g, ev, c, 0xD0D, 0xD0E, 0xD10)
        events.done(ev)
        return
    ev["countdown"] -= 1
    cd, lead = ev["countdown"], ev["deadline"]
    posted = False
    if st == 0:
        if cd == lead and not ev.get("announced"):
            ev["announced"] = True
            _tmsg(g, ev, c, 0x1C0, 0x1C2)
            posted = True
        elif cd == 6 and lead > 6:
            _tmsg(g, ev, c, 0x1C0, 0x1C3, months=6)
            posted = True
        elif cd < 1:
            ev["countdown"], ev["state"] = 12, 1
            _tmsg(g, ev, c, 0x1C0, 0x1C4, months=12)
            posted = True
    elif st == 1:
        if cd == 6:
            _tmsg(g, ev, c, 0x1C0, 0x1C5, months=6)
            posted = True
        elif cd < 1:
            relations.attitude_add(g, c, TRIBUTE_OUT_ATT[5], 0xC59, 0, ev.get("item"))
            _tmsg(g, ev, c, 0x38C, 0x38D, 0x1C9)
            ev["state"] = 5
            events.done(ev)
            return
    if not ev.get("notice") and not posted and (ev["state"] == 1 or ev["countdown"] <= lead) and have_enough(g, ev):
        ev["notice"] = True
        if ev["item"] == MONEY:
            _tmsg(g, ev, c, 0xB6A, 0xB6B, 0xB6C, months=ev["countdown"])
        else:
            _tmsg(g, ev, c, 0xB70, 0xB71, months=ev["countdown"])


def request_month(g, ev, start=False):
    """event_request 0x00470800 (states 0/1) and the fulfilled states 2/3/4."""
    if ev["type"] == "tribute_out":
        return tribute_out_month(g, ev)
    c = g.empire.cities[ev["city"]]
    st = ev["state"]
    if st in (2, 3, 4):
        ev["countdown"] -= 1
        if ev["countdown"] < 1:
            request_attitude(g, ev, st)
            events.done(ev)
        return
    if not start:
        ev["countdown"] -= 1
    what = f"{ev['amount']} {ev['item'] if ev['item'] == MONEY else 'loads of ' + ev['item']}"
    if st == 0:
        if ev["countdown"] == ev["deadline"] and not ev.get("announced"):
            ev["announced"] = True
            verb = ("demands" if c.cls() == "rival" else "needs" if c.cls() == "ally" else "begs for"
                    if c.cls() in ("vassal", "colony") else "requisitions")
            if ev["type"] == "tribute_out":
                g.message(f"{c.name} claims its tribute of {what}: pay within {ev['deadline']} months.")
            else:
                g.message(f"{c.name} {verb} {what} ({KIND_NAMES.get(ev.get('kind', 0), 'a request')}) within {ev['deadline']} months.")
        elif ev["countdown"] == 6 and ev["deadline"] > 6:
            g.message(f"Reminder: {c.name} still waits for {what}.")
        elif ev["countdown"] < 1:
            g.message(f"The request of {c.name} for {what} is overdue.")
            ev["state"] = 1
            a, b, cc = (g.rng.randrange(128) for _ in range(3))
            k = ev.get("kind", 0)
            ev["countdown"] = (12 if ev["type"] == "tribute_out" else
                               {0: a % 12 + b % 12 + cc % 12 + 3, 3: b % 3 + cc % 3 + 2, 4: b % 13 + cc % 13 + 12,
                                5: cc % 3 + 1, 6: a % 10 + b % 10 + cc % 10 + 7}.get(k, 24))
        if not ev.get("notice") and ev["state"] == 0 and have_enough(g, ev):
            ev["notice"] = True
            g.message(f"You now have enough to fulfil {c.name}'s request ({what}).")
    elif st == 1 and ev["countdown"] < 1:
        request_attitude(g, ev, 5)
        g.message(f"{c.name} gave up on its request for {what}.")
        ev["state"] = 5
        events.done(ev)


def fulfil(g, c, n=0, slots=None):
    """event_pay_tribute_or_gift 0x0046DAA0 from the 'requests by [city]' list."""
    from ..systems import economy
    from . import requests, _city_requests
    from .. import scenario
    rows = _city_requests(g, c)                        # the rows in the list's order (FUN_00464320)
    if not rows:
        raise ValueError(f"{c.name} has no outstanding requests")
    r = rows[min(n, len(rows) - 1)]
    if r.get("event") is not None:                     # a scenario type-1 record (sim/empire/requests.py)
        sev = scenario.get(g, r["event"])
        if sev["item"] == requests.TROOPS_ID:
            return requests.dispatch(g, sev, slots=slots)
        return requests.pay(g, sev)
    ev = next(x for x in g.empire.events if x["id"] == r["eid"])
    item, amount = ev["item"], ev["amount"]
    from .. import gods
    hermes = gods.hermes_pays(g, ev)                   # hermes_request_auto 0x004E7C00: no stock needed, nothing taken
    if not hermes and not have_enough(g, ev):
        raise ValueError(f"You do not have enough to fulfill the request ({amount} {item})")
    ev["state"] = (2 if ev["countdown"] > ev["deadline"] else 3) if ev["state"] == 0 else 4
    ev["countdown"] = g.rng.randrange(4) + 1
    from .. import scenario
    scenario.request_list_rebuild(g)                   # wm_sub_475ab0 / 0x00475B50 after paying
    if hermes:
        gods.hermes_paid(g)
        return f"Hermes pays {amount} {item} to {c.name} ({'early' if ev['state'] == 2 else 'on time' if ev['state'] == 3 else 'late'})"
    if item == MONEY:
        g.city.treasury -= amount
        g.empire.totals["tribute_paid" if ev["type"] == "tribute_out" else "gifts_given"] += amount
    elif item == FOOD:
        left = units(FOODS[0], amount)
        for f in sorted(FOODS, key=lambda f: -stock(g, f)):
            left -= economy.goods_remove(g, f, left)
            if left <= 0:
                break
    else:
        economy.goods_remove(g, item, units(item, amount))
    return f"sent {amount} {item} to {c.name} ({'early' if ev['state'] == 2 else 'on time' if ev['state'] == 3 else 'late'})"


def request_attitude(g, ev, outcome):
    """request_resolve_attitude 0x0046FFA0: 2 early, 3 on time, 4 late, 5 refused/failed."""
    c = g.empire.cities[ev["city"]]
    if ev["type"] == "tribute_out":                    # event_tribute_out: tribute_due_*_history_D 0xC56..0xC59
        relations.attitude_add(g, c, TRIBUTE_OUT_ATT[outcome], 0xC56 + outcome - 2, 0, ev.get("item"))
        return
    tab = REQ_ATT.get(ev.get("kind", 0), REQ_ATT[0])[outcome]
    t = TONE.get(c.cls())
    if t is None:
        return
    self_d = tab[(0, 2, 4, 6)[t]]
    other_d = (tab[1], tab[3], tab[5], 0)[t]
    # history phrase (0x0046FFA0): the kind's early_history_D + the outcome (early 0, on time 1, late 2, refused 3)
    # + 4 x the tone's block (D demand: rival, P plea: vassal / colony, R requisition: parent, S request: ally)
    phrase = REQ_HISTORY.get(ev.get("kind", 0), REQ_HISTORY[0]) + (outcome - 2) + 4 * (3, 0, 1, 2)[t]
    relations.attitude_add(g, c, self_d, phrase, 0, ev.get("item"))
    for o in _others(g, c, other_d):
        if TONE.get(o.cls()) == t:
            relations.attitude_add(g, o, other_d, phrase, relations.REL.get(o.cls(), 0), ev.get("item"))
    if self_d:
        g.message(f"{c.name} {'regards you more highly' if self_d > 0 else 'thinks less of you'} ({self_d:+d}).")


# --- monthly city code ---

def tribute(g):
    """cities_tribute_yearly 0x004771E0 (January, day 2)."""
    d = relations.diff(g)
    for c in g.empire.cities.values():
        if c.kind == "player":
            continue
        t = c.tribute
        if c.exists() and t["mode"] == 1:
            if c.relation not in ("vassal", "colony"):
                t["mode"] = 0
            elif t["good"] and t["amount"] > 0:
                tribute_in(g, c, t["good"], t["amount"])
        if c.kind != "parent" and c.exists() and t["mode"] == 2 and t["claim"] > 0:
            amount = int(t["claim"] * TRIBUTE_MULT[d])
            ev = events.add(g, type="tribute_out", city=c.id, item=MONEY, amount=amount, deadline=2, countdown=2 + 12)
            ev["notice"] = g.city.treasury >= amount           # +0x33 at the activation (event_tribute_out)


def tribute_in(g, c, good, amount):
    """0x00474F60 (type 0x1D): offered (offers.py; tribute gets the last-chance rules, never Postpone)."""
    from . import offers
    offers.create(g, "tribute", c, good, amount)


def city_gift(g, c, good, amount, rescue=False):
    """event_gift 0x00474A80 (type 0x17; a debt rescue: item 23 flags 0x110): offered (offers.py)."""
    from . import offers
    offers.create(g, "rescue" if rescue else "gift", c, good, amount)


def aid_gift(g, c):
    """city_schedule_aid 0x00477610 with city_pick_aid_good 0x0042CFA0."""
    d = relations.diff(g)
    ok = [k for k, q in c.sells.items() if q and c.request_fatigue.get(k, 0) < 21]
    if not ok:
        return False
    good = ok[g.rng.randrange(len(ok))]
    amount = c.sells[good] * AID_PCT[d] // 100
    last = [k for k in c.sells][-1]                     # sic: the last scanned list entry gets the fatigue
    c.request_fatigue[last] = c.request_fatigue.get(last, 0) + 15
    if amount <= 0:
        return False
    city_gift(g, c, good, amount)
    return True


# streak consequences 0x00477430: row -> {class: action}, attitude change when the action happens
STREAK = {0: ({"ally": "aid", "vassal": "aid", "colony": "aid", "parent": "aid"}, -30),
          4: ({"ally": "suspend", "rival": "invade", "vassal": "rebel", "colony": "rebel", "parent": "suspend"}, 30)}


def streaks(g):
    """cities_streak_pick 0x0047ECD0 (day 7): one random colony/foreign/parent city."""
    cand = [c for c in g.empire.cities.values() if c.active and c.visible and c.kind in ("colony", "foreign", "parent")]
    if not cand:
        return
    c = cand[g.rng.randrange(len(cand))]
    if c.pleased >= 50:
        row = 0
    elif 21 <= c.pleased <= 49:
        row = 1
    elif c.pleased == 0 and c.displeased == 0:
        row = 2
    elif 21 <= c.displeased <= 49:
        row = 3
    elif c.displeased >= 50:
        row = 4
    else:
        return
    if row not in STREAK:
        return
    act = STREAK[row][0].get(c.cls())
    did = False
    if act == "aid":
        did = aid_gift(g, c)
    elif act == "suspend":
        did = relations.status_change(g, c, 0)
        if did:
            g.message(f"{c.name} has suspended trade with you.")
    elif act == "rebel":
        did = relations.status_change(g, c, 6)
        if did:
            g.message(f"{c.name} is in rebellion!")
    elif act == "invade":
        from . import war
        did = war.invasion_create(g, c, c.army * 3 // 5)        # 0x00477830, strength 0x0042D9D0
    if did:
        c.pleased = c.displeased = 0
        c.attitude += STREAK[row][1]                   # not clamped here (0x00477430, sic)


def spontaneous(g):
    """cities_spontaneous_events 0x0047EE20 (day 12): debt rescue gift or a rival invasion."""
    from . import war
    p1, _ = relations.player_strength(g)
    cand = []
    for c in g.empire.cities.values():
        k = c.cls()
        if k in ("ally", "parent") and c.exists() and g.city.treasury < 0 and c.attitude > 49 and not c.extorted:
            cand.append(("gift", c))
        r = c.army * 3 // 5
        if (k == "rival" and c.exists() and p1 < 0.4 * r and r <= 0.75 * g.empire.peak_strength
                and c.pleased == 0 and not war.invasion_pending(g, c)):
            cand.append(("invade", c))
    if not cand:
        return
    what, c = cand[g.rng.randrange(len(cand))]
    if what == "gift":
        city_gift(g, c, MONEY, int((c.wealth + 1) * MONEY_GIFT_Q[relations.diff(g)] * 200), rescue=True)
    else:
        war.invasion_create(g, c, c.army * 3 // 5, spontaneous=True)
