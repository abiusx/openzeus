"""Scenario event type 1 (Request): a city asks the player for goods, money, food (`event_request` 0x00470800) or
troops (`event_troops_request_update` 0x0046ED70, item 24), registered with sim/scenario (PLUGINS). Track 1L-5.
The empire's own requests (sim/empire/diplomacy.py city_request, the `cityrequest` test command) keep their queue;
the attitude result is this module's (resolve).

Record: +0x1C (city) the asking city, +0x04 item (23 drachmas, 24 troops, 25 food, else a good), +0x0C amount (loads;
drachmas; for troops the enemy's strength), +0x2C lead = the months allowed, +0x60 (kind) 0 general, 3 festival,
4 building project, 5 famine, 6 financial woes; with troops 1 defend the city against the rival +0x6F, 2 join its
attack on the rival +0x6F, 7 slay the monster of slot +0x36; +0x24 / +0x26 / +0x52 / +0x54 the chained records on
success / refusal / late / lost battle; +0x56 what happens to the city when the troops do not come (1 destroyed
FUN_00477AB0, 2 conquered by +0x6F FUN_0046EAC0); +0x61 / +0x62 the two reminders (months before the deadline,
counted beyond the travel time); +0x33 "you can now fulfil" sent.

Goods (event_request):
    activation (not active, not 0x20001): year offset > 0: in the month a year before the date (countdown = lead + 12);
      year 0: at the first pass (countdown = month + lead); +0x33 = 1 when the stock already covers it
    active: countdown - 1 each month; state 0: WARN and not WARNED: the oracle's prediction (title + 1; the countdown
      is put back); countdown == lead: the announcement (+2, [time_allotted] = lead); countdown == 6 (lead > 6): the
      reminder (+3); countdown < 1: overdue (+4): state 1, a grace period by kind (general 3 + 3 x rng%12, festival
      2 + 2 x rng%3, building 12 + 2 x rng%13, famine 1 + rng%3, financial 7 + 3 x rng%10); state 1 at 0: refused
      (attitude, the +0x26 chain), state 5. Not already messaged this month, +0x33 clear, outstanding
      (request_outstanding 0x0047F630) and the stock covers it: "you can now fulfil" (0xD15.. money / 0xD2D.. goods,
      by tone), +0x33 = 1.
    paid (event_pay_tribute_or_gift 0x0046DAA0: state 2 early when countdown > lead, 3 on time, 4 when overdue;
      countdown 1..4): at 0 the attitude result (request_resolve_attitude 0x0046FFA0), the chain +0x24 (early, on
      time) or +0x52 (late), state 10, done.
Troops (event_troops_request_update): the same activation (and a late start in the window); the family by the
city's class (kind 1 ally 0x1D6 / vassal 0x1EC / colony 0x202 / parent 0x218; kind 2 ally 0x22E / vassal 0x244;
kind 7 ally 0x87C / vassal 0x892 / colony 0x8A8 / parent 0x8BE); prediction (+1), announcement (+2, [travel_time]
= months until due - +0x61 - travel + 6), reminders (+3 / +4) when the months until due less the travel time reach
+0x61 / +0x62; kind 7 also announces the hero the monster needs. The player sends companies (dispatch: state 6,
countdown = travel months, flag 0x200 when they arrive after the deadline); they wait at the city until the due
month (flag 0x400: arrived early). On the due month: never sent -> refused (attitude, the +0x56 consequence, the
+0x26 chain); still more than 2 months away -> late (state 8); else distant_battle_resolve 0x00461540 (the
companies and heroes plus the city's army (kind 2: 3/5) against +0x0C or the rival's army (kind 1: 3/5); 0x400 and
more than half the enemy: won without a fight, 0x800 "attack averted"; 0x200: the enemy x 70 %): won -> state 7,
attitude early/comply, +0x24, kind 2 with +0x56 == 2: the rival falls to the city (0x3C2 / 0x3C8); lost -> state 9,
attitude "lost battle", the consequence, +0x54. The forces come home after the travel months (messages 0xB64 /
0xB5E / 0xD63 / 0xD5D at the land exit, alert 14).
"""
from .. import scenario
from . import eventmsg, relations

MONEY_ID, TROOPS_ID, FOOD_ID = 23, 24, 25
# city_class 0x0042CF10: 0 ally, 1 vassal, 2 rival, 3 parent, 4 colony, 5 self, 6 distant
CLASS = {"ally": 0, "vassal": 1, "rival": 2, "parent": 3, "colony": 4, "self": 5, "distant": 6}
# event_request: the title phrase by kind and tone (request_tone 0x0046FBC0: 0 S ally, 1 D rival, 2 P vassal /
# colony, 3 R parent / self); +1 prediction, +2 announcement, +3 reminder, +4 overdue, +6.. the outcome reasons
FAMILY = {0: (0x60, 0x6B, 0x76, 0x81), 3: (0x110, 0x11B, 0x126, 0x131), 4: (0xB8, 0xC3, 0xCE, 0xD9),
          5: (0x08, 0x13, 0x1E, 0x29), 6: (0x168, 0x173, 0x17E, 0x189)}
# the history phrase of the outcome (request_resolve_attitude: + outcome + 4 x the tone's block)
HISTORY = {0: 0xC36, 3: 0xC46, 4: 0xC06, 5: 0xC16, 6: 0xC26}
TONE_BLOCK = (3, 0, 1, 2)
# troops: the family by kind and city class (event_troops_request_update; FUN_00476130.. reasons = family + 5 + outcome)
TROOP_FAMILY = {1: {0: 0x1D6, 1: 0x1EC, 4: 0x202, 3: 0x218}, 2: {0: 0x22E, 1: 0x244},
                7: {0: 0x87C, 1: 0x892, 4: 0x8A8, 3: 0x8BE}}
# kinds 1 / 7 (tables 0x0063322C / 0x00633254): (self, same-class others) by outcome early, comply, late, refused, lost
TROOP_ATT = ((70, 40), (40, 15), (-30, -10), (-20, -10), (-80, -40))
TROOP_HIST = {1: (0xC5A, 0xD88), 7: (0xBF6, 0xD8E)}          # (base + 4 x block + outcome, the "lost" phrase + block)
TROOP_BLOCK = {0: 0, 1: 3, 3: 2, 4: 1}
TROOP_REL = {0: 1, 1: 3, 3: 5, 4: 4}
# the history row's relation byte of another city by its class
REL = {0: 1, 1: 3, 2: 2, 4: 4}


def cls(c):
    return CLASS.get(c.cls(), 6)


def tone(c):
    """request_tone 0x0046FBC0."""
    k = cls(c)
    return 2 if k in (1, 4) else 1 if k == 2 else 3 if k in (3, 5) else 0


def stock(g, item):
    """The stock the exe compares (granaries for foods 1..8 + storehouses + trading posts; food 25 every food;
    drachmas the treasury)."""
    from . import diplomacy, model
    if item == MONEY_ID:
        return g.city.treasury
    if item == FOOD_ID:
        return sum(diplomacy.stock(g, f) for f in model.FOODS)
    key = good_key(item)
    return diplomacy.stock(g, key) if key else 0


def good_key(item):
    from .model import GOOD_IDS
    return {v: k for k, v in GOOD_IDS.items()}.get(item)


def units(ev):
    """event_amount_units 0x00466E30: drachmas / troops as is, sculpture x 400, else loads x 100."""
    it = ev["item"]
    if it in (MONEY_ID, TROOPS_ID):
        return ev["amount"]
    return ev["amount"] * (400 if good_key(it) == "sculpture" else 100)


def enough(g, ev):
    return stock(g, ev["item"]) >= units(ev)


def outstanding(ev):
    """request_outstanding 0x0047F630 for type 1."""
    if not ev.get("active"):
        return False
    return bool(ev["flags"] & scenario.WARN) or ev["countdown"] <= ev["lead"] or ev["state"] == 1


def is_open(ev):
    """request_is_open 0x004714F0: listed on the Overview and payable."""
    return (ev["type"] == 1 and ev.get("active") and not ev["flags"] & 0x40000
            and ((ev["state"] == 0 and outstanding(ev)) or ev["state"] == 1))


def _chain(g, ev, key):
    t = scenario.get(g, ev.get(key, -1))
    if t is not None and t["flags"] & scenario.TEMPLATE and t["id"] != ev["id"]:      # FUN_004694A0
        src = ev.get("chain")
        ev["chain"] = t["id"]
        try:
            scenario.chain(g, ev)
        finally:
            ev["chain"] = src


def _links(ev):
    """+0x26 refused, +0x52 late, +0x54 lost battle: shorts in the file record."""
    raw = bytes.fromhex(ev.get("raw") or "")

    def s16(o):
        return int.from_bytes(raw[o:o + 2], "little", signed=True) if len(raw) >= o + 2 else -1
    for k, o in (("chain_refused", 0x26), ("chain_late", 0x52), ("chain_lost", 0x54)):
        ev.setdefault(k, s16(o))


def _rng7(g):
    return scenario.rng15(g) & 0x7F


def grace(g, kind):
    """The overdue months by kind (event_request; three rng_7 draws a, b, c)."""
    a, b, c = _rng7(g), _rng7(g), _rng7(g)
    return {0: c % 12 + b % 12 + 3 + a % 12, 3: b % 3 + 2 + a % 3, 4: b % 13 + 12 + a % 13, 5: a % 3 + 1,
            6: c % 10 + b % 10 + 7 + a % 10}.get(kind, 24)


# --- the handler ---------------------------------------------------------------------------------------------

def handler(g, ev):
    _links(ev)
    if ev["item"] == TROOPS_ID:
        return troops(g, ev)
    if ev["state"] in (10, 5):
        ev["active"] = 0
        ev["flags"] |= scenario.DONE
        return
    c = eventmsg.city(g, ev.get("city"))
    if c is None or not (c.exists() or c.trading()):                      # city_exists_or_partner 0x0042CB10
        return
    kind = ev.get("kind", 0)
    base = FAMILY.get(kind, FAMILY[0])[tone(c)] if kind != 9 else 0
    if ev["state"] in (2, 3, 4):
        ev["countdown"] -= 1
        if ev["countdown"] > 0:
            return
        resolve(g, ev, c)
        _chain(g, ev, "chain" if ev["state"] in (2, 3) else "chain_late")
        ev.update(state=10, active=0)
        ev["flags"] |= scenario.DONE
        return
    if ev.get("active"):
        ev["countdown"] -= 1
        have = enough(g, ev)
        posted = False
        if ev["state"] == 0:
            f = ev["flags"]
            if f & scenario.WARN and not f & scenario.WARNED:
                ev["countdown"] += 1
                post(g, ev, c, base, base + 1, have, time_allotted=ev["countdown"])
                ev["flags"] |= scenario.WARNED
                posted = True
            elif ev["countdown"] == ev["lead"]:
                post(g, ev, c, base, base + 2, have)
                posted = True
            elif ev["countdown"] == 6 and ev["lead"] > 6:
                post(g, ev, c, base, base + 3, have, time_allotted=6)
                posted = True
            elif ev["countdown"] < 1:
                ev["countdown"] = grace(g, kind)
                ev["state"] = 1
                post(g, ev, c, base, base + 4, have, time_allotted=ev["countdown"])
                posted = True
        elif ev["state"] == 1 and ev["countdown"] < 1:
            resolve(g, ev, c)
            _chain(g, ev, "chain_refused")
            ev.update(state=5, active=0)
        if not ev.get("b33") and not posted and outstanding(ev) and have:
            ev["b33"] = 1
            t = (0xD15 if ev["item"] == MONEY_ID else 0xD2D) + 6 * tone(c)
            eventmsg.post(g, t, t + 1, ev, reason_id=t + 2, c=c, time_allotted=ev["countdown"], record=0xDF,
                          buttons=BUTTONS)
        return
    if ev["flags"] & (scenario.DISABLED | scenario.TEMPLATE):
        return
    y, m = scenario.today(g)
    if ev["year"] > 0:
        if (y, m) != (ev["year"] - 1, ev["month"]):
            return
        ev["countdown"] = ev["lead"] + 12
    else:
        if y != 0:
            return
        ev["countdown"] = ev["month"] + ev["lead"]
    ev["active"] = 1
    if enough(g, ev):
        ev["b33"] = 1
    scenario.log(g, f"event #{ev['id']}: request by {c.name} active, {ev['countdown']} months")


BUTTONS = 0x1C0          # the message's Dispatch now / Postpone / Refuse (set C of the message window)


def post(g, ev, c, title, body, have=False, **over):
    """A request message (0xDF): reason FUN_00475BF0 (the family's "no reason"); with the buttons when the stock
    covers it (event_request's bVar2: the stock alone, not Hermes)."""
    eventmsg.post(g, title, body, ev, reason_id=no_reason(ev, c), c=c, record=0xDF, buttons=BUTTONS if have else 0,
                  **over)


def no_reason(ev, c):
    """FUN_00475BF0 for type 1."""
    kind = ev.get("kind", 0)
    if ev["item"] == TROOPS_ID:
        fam = TROOP_FAMILY.get(kind, {}).get(cls(c))
        return fam + 10 if fam is not None else -1
    if kind == 6:
        return FAMILY[6][tone(c)]                     # sic: the title
    return FAMILY.get(kind, FAMILY[0])[tone(c)] + 10


def outcome_of(state, kind):
    """request_resolve_attitude: the outcome index by the record's state (early 0, comply 1, late 2, refused 3,
    lost battle 4)."""
    if state == 5:
        return 4 if kind in (1, 7) else 0
    return {1: 3, 2: 0, 3: 1, 6: 1, 4: 2}.get(state)


def reason_of(ev, c, out):
    """FUN_00476130 / 00476400 / 00476940 / 004766D0 / 00476BB0: the outcome's reason phrase."""
    kind = ev.get("kind", 0)
    if ev["item"] == TROOPS_ID or kind in (1, 2, 7):
        fam = TROOP_FAMILY.get(kind, {}).get(cls(c))
        return fam + 5 + out if fam is not None else -1
    if kind == 6 or kind not in FAMILY:
        return -1
    return FAMILY[kind][tone(c)] + 6 + out if out < 4 else -1


def resolve(g, ev, c=None, state=None):
    """request_resolve_attitude 0x0046FFA0: the city's attitude (and its peers') by the outcome, the history rows,
    the message 0xE0 to the city's own change (0x386 / 0x38C "regards you more / less highly" with the outcome's
    reason; flag 0x800 "attack averted" 0x392, kind 7 0x8D4)."""
    c = c or eventmsg.city(g, ev.get("city"))
    if c is None:
        return
    kind = ev.get("kind", 0)
    out = outcome_of(ev["state"] if state is None else state, kind)
    if out is None:
        return
    reason = reason_of(ev, c, out)
    from . import diplomacy
    item = ev.get("item")
    me = cls(c)
    if kind in (1, 7):
        self_d, other_d = TROOP_ATT[out]
        base, lost = TROOP_HIST[kind]
        blk = TROOP_BLOCK.get(me, 0)
        phrase = lost + blk if out == 4 else blk * 4 + out + base
        rows = [(c, self_d, 0)] + [(o, other_d, TROOP_REL.get(me, 0)) for o in _cities(g)
                                   if o is not c and cls(o) == me]
    elif kind in diplomacy.REQ_ATT and out < 4:
        t = tone(c)
        col = diplomacy.REQ_ATT[kind][out + 2]
        self_d = col[(0, 2, 4, 6)[t]]
        other = {0: (col[1], (0,)), 1: (col[3], (2,)), 2: (col[5], (1, 4)), 3: (0, ())}[t]
        phrase = HISTORY[kind] + out + 4 * TONE_BLOCK[t]
        rows = [(c, self_d, 0)] + [(o, other[0], REL.get(cls(o), 0)) for o in _cities(g)
                                   if o is not c and cls(o) in other[1]]
    else:
        return
    for o, d, rel in rows:
        if d:
            relations.attitude_add(g, o, d, phrase, rel, item)
    if ev["flags"] & 0x800:
        title = 0x8D4 if kind == 7 else 0x392
        reason = reason_of(ev, c, 0)
    else:
        title = 0x386 if self_d >= 1 else 0x38C
    # 0x8D4 (a quest's monster slain in time): request_resolve_attitude 0x0046FFA0 FUN_005A1210(5), S_mon2
    eventmsg.post(g, title, title + 1, ev, reason_id=reason, c=c, stinger="mon2" if title == 0x8D4 else None)


def _cities(g):
    """In use, shown, active (the loop's test)."""
    return [o for o in g.empire.cities.values() if o.visible and o.active]


# --- paying (event_pay_tribute_or_gift 0x0046DAA0) ------------------------------------------------------------

def open_for(g, cid):
    return [ev for ev in scenario.events(g, 1) if ev.get("city") == cid and is_open(ev)]


def pay(g, ev):
    """The player answers record ev: goods / money leave now (Hermes may pay instead), the city's verdict comes 1..4
    months later; troops: dispatch."""
    if ev["item"] == TROOPS_ID:
        raise ValueError("a request for troops: send companies (`fulfil CITY N [SLOTS...]`)")
    from . import diplomacy, model
    from .. import gods
    if not enough(g, ev) and not gods.hermes_pays(g, dict(type="request", kind=ev.get("kind", 0))):
        raise ValueError(f"You do not have enough to fulfill the request ({ev['amount']} {_what(ev)})")
    ev["state"] = (2 + (ev["countdown"] <= ev["lead"])) if ev["state"] == 0 else 4
    ev["countdown"] = (scenario.rng15(g) & 3) + 1
    scenario.request_list_rebuild(g)
    if gods.hermes_pays(g, dict(type="request", kind=ev.get("kind", 0))):
        gods.hermes_paid(g)
        return f"Hermes pays {ev['amount']} {_what(ev)}"
    from ..systems import economy
    it = ev["item"]
    if it == MONEY_ID:
        g.city.treasury -= ev["amount"]
        g.empire.totals["gifts_given"] += ev["amount"]
    elif it == FOOD_ID:
        left = units(ev)
        for f in sorted(model.FOODS, key=lambda f: -diplomacy.stock(g, f)):
            left -= economy.goods_remove(g, f, left)
            if left <= 0:
                break
    else:
        economy.goods_remove(g, good_key(it), units(ev))
    return f"sent {ev['amount']} {_what(ev)} ({['', '', 'early', 'on time', 'late'][ev['state']]})"


def _what(ev):
    from .. import messages
    return messages.item_words(ev["item"])[0]


def refuse(g, ev):
    """The request message's refuse button (wm_sub_475B50, button bit 0x100): an open record (state 0 or 1) gets flag
    0x40000 (no longer listed); goods / money: state 1, countdown 1 (refused at the next pass)."""
    if ev["state"] not in (0, 1):
        return "not open"
    if ev["item"] != TROOPS_ID:
        ev["state"], ev["countdown"] = 1, 1
    ev["flags"] |= 0x40000
    scenario.request_list_rebuild(g)
    return f"request #{ev['id']} refused"


# --- troops (event_troops_request_update 0x0046ED70) ----------------------------------------------------------

def _rival(g, ev):
    return eventmsg.city(g, eventmsg.byte(ev, 0x6F))


def travel(g, ev):
    """event_travel_months 0x0046D950: the route from the city (kind 2: the rival +0x6F) to the player's; 0 when none."""
    e = g.empire
    cid = eventmsg.byte(ev, 0x6F) if ev.get("kind") == 2 else ev.get("city")
    if cid not in e.cities or e.route(cid, e.player().id) is None:
        return 0
    return e.travel_months(cid, e.player().id)


def _travel12(g, ev):
    t = travel(g, ev)
    return t if t >= 1 else 12


def family(g, ev, c):
    """The phrase family and whether the request is invalid (bVar2)."""
    kind = ev.get("kind", 0)
    if c is None or not c.exists():
        return -1, True
    r = _rival(g, ev)
    if kind == 1:
        bad = r is None or r.relation != "rival" or not r.exists()
    elif kind == 7:
        bad = False
    else:
        bad = r is None or r.relation != "rival" or not r.exists()
        if c.kind != "foreign":
            return 0x22E, True
    k = cls(c)
    fam = TROOP_FAMILY.get(kind if kind in (1, 7) else 2, {}).get(k)
    if fam is None:
        return 0x22E if kind not in (1, 7) else -1, True
    return fam, bad


def _hero_needed(g, ev):
    """Kind 7: the hero the monster of slot +0x36 needs (FUN_00480F20 + hero_needed_message)."""
    try:
        from ..heroes import monster_of_slot, data, heroes
        from ..heroes.events import MONSTER_TEXT, hero_monster_text
    except ImportError:
        return
    m = monster_of_slot(g, ev.get("b36", 0) & 0xFF)
    if m < 0:
        return
    h = data()["monsters"][m]["hero"]
    if h < 0:
        return
    heroes.needed(g, h, hero_monster_text(h, m), MONSTER_TEXT[m][0] + 2)


def _monster_name(g, ev):
    try:
        from ..heroes import monster_of_slot, data
        m = monster_of_slot(g, ev.get("b36", 0) & 0xFF)
        return data()["monsters"][m]["name"] if m >= 0 else ""
    except (ImportError, KeyError, IndexError):
        return ""


def can_troops(g):
    """FUN_0046EC40: companies that could go (0x00FE6A74 > 0), a trireme (0x00FEB0B9) or a hero in the city and free."""
    from . import war
    from .. import military
    return bool(war.home_companies(g) or (military.on(g) and military.navy_home(g)) or war.heroes_present(g))


def monster_hero(g, ev):
    """Kind 7: the hero the monster of slot +0x36 needs (scenario_hero_of_monster_slot), -1 when none."""
    try:
        from ..heroes import monster_of_slot, data
        m = monster_of_slot(g, ev.get("b36", 0) & 0xFF)
        return data()["monsters"][m]["hero"] if m >= 0 else -1
    except (ImportError, KeyError, IndexError):
        return -1


def can_fulfil(g, ev):
    """request_can_fulfil 0x004713E0 (the message window drops a request's buttons when false): troops (not kind 7)
    FUN_0046EC40; kind 7 the monster's hero in the city and free; goods / money / food the stock or Hermes."""
    from .. import gods
    from . import war
    if ev["item"] == TROOPS_ID:
        if ev.get("kind") != 7:
            return can_troops(g)
        h = monster_hero(g, ev)
        return h >= 0 and h in war.heroes_present(g)
    return enough(g, ev) or bool(gods.hermes_pays(g, dict(type="request", kind=ev.get("kind", 0))))


def tpost(g, ev, c, title, body, record=0xE0, **over):
    if ev.get("kind") == 7:
        over.setdefault("monster", _monster_name(g, ev))
    eventmsg.post(g, title, body, ev, reason_id=no_reason(ev, c) if c is not None else -1, c=c, record=record,
                  buttons=BUTTONS if can_troops(g) else 0, **over)


def troops(g, ev):
    if ev["state"] == 10:
        ev["flags"] |= scenario.DONE
        return
    c = eventmsg.city(g, ev.get("city"))
    fam, bad = family(g, ev, c)
    kind = ev.get("kind", 0)
    m = scenario.months_until_due(g, ev)
    st = ev["state"]
    if m != 0:
        if st == 0:
            if not ev.get("active"):
                _activate(g, ev, m)
                return
            if bad:
                ev["state"] = 10
                return
            if ev["flags"] & 0x40000:
                return
            tt = max(1, m - ev.get("b61", 0) - _travel12(g, ev) + 6)            # FUN_0046EA80
            ev["countdown"] -= 1
            cd, lead = ev["countdown"], ev["lead"]
            f = ev["flags"]
            if lead < cd and f & scenario.WARN and not f & scenario.WARNED:
                ev["countdown"] += 1
                tpost(g, ev, c, fam, fam + 1, travel_time=tt)
                ev["flags"] |= scenario.WARNED
                return
            if cd == lead:
                tpost(g, ev, c, fam, fam + 2, travel_time=tt)
            elif lead > cd:
                left = m - _travel12(g, ev)
                if left == ev.get("b61", 0):
                    tpost(g, ev, c, fam, fam + 3, record=0xDF, travel_time=tt)
                elif left == ev.get("b62", 0):
                    tpost(g, ev, c, fam, fam + 4, record=0xDF, travel_time=tt)
                else:
                    return
            else:
                return
            if kind == 7:
                _hero_needed(g, ev)
        elif st == 6:
            ev["countdown"] -= 1
            if ev["countdown"] > 0:
                return
            if ev["lead"] < m:
                ev["flags"] |= 0x400                                  # arrived before the deadline
            if m >= 0 or not bad:
                ev["countdown"] = 1
                ev["flags"] |= 0x10000                                # waiting at the city
                return
            _home(g, ev, alert=True)
            ev["state"] = 10
        elif st in (7, 8, 9):
            ev["countdown"] -= 1
            if ev["countdown"] >= 1:
                return
            if st == 7:
                t = 0xB64 if kind in (1, 7) else 0xD63
            elif st == 8:
                t = 0xB5E
            else:
                t = 0xB5E if kind in (1, 7) else 0xD5D
            eventmsg.post(g, t, t + 1, ev, reason_id=t + 2, c=c)
            _home(g, ev, alert=True)
            ev["state"], ev["active"] = 10, 0                         # the record's +0x32 cleared too (bugs.md 364)
        return
    # the due month
    if bad:
        if st == 6:
            _home(g, ev, alert=True)
        ev["state"] = 10
        return
    if st == 0:
        if kind in (1, 2, 7):                                          # FUN_00469440
            ev["state"] = 1
            resolve(g, ev, c)
            if kind != 2:
                _consequence(g, ev, c)
        _chain(g, ev, "chain_refused")
        ev["state"], ev["active"] = 10, 0                             # +0x32 = 0 (bugs.md 364; not on a bad city)
        return
    if st != 6:
        ev["state"], ev["active"] = 10, 0
        return
    if ev["countdown"] > 2:                                           # still on the way: too late
        resolve(g, ev, c, state=4)
        if kind != 2:
            _consequence(g, ev, c)
        _chain(g, ev, "chain_late")
        ev["state"] = 8
        ev["countdown"] = max(1, travel(g, ev) - ev["countdown"])
        return
    won, wiped = battle(g, ev, c)
    if not won:
        resolve(g, ev, c, state=5)
        if kind != 2:
            _consequence(g, ev, c)
        _chain(g, ev, "chain_lost")
        ev["state"] = 9
        ev["countdown"] = max(1, travel(g, ev))
        return
    if kind in (1, 7):
        resolve(g, ev, c, state=2 if ev["flags"] & 0x800 else 3)
    _chain(g, ev, "chain")
    ev["state"] = 7
    ev["countdown"] = max(1, travel(g, ev))
    r = _rival(g, ev)
    if kind == 2 and r is not None and r.exists() and eventmsg.byte(ev, 0x56) == 2 and r.relation == "rival":
        r.rebellion, r.trade_open = False, True
        t, hist = (0x3C2, 0xD92) if c.relation == "ally" else (0x3C8, 0xD93)
        eventmsg.post(g, t, t + 1, ev, reason_id=t + 2, c=c)
        relations.note(g, r, hist)


def _activate(g, ev, m):
    if ev["flags"] & (scenario.DISABLED | scenario.TEMPLATE):
        return
    y, mo = scenario.today(g)
    yr = ev["year"]
    if yr < 1:
        ev["active"], ev["countdown"] = 1, ev["month"] + ev["lead"]
        return
    ay = yr - 1
    if y == ay:
        if mo == ev["month"]:
            ev["active"], ev["countdown"] = 1, ev["lead"] + 12
    elif ay < y:                                                       # started late: inside the window
        y2 = ev["lead"] // 12 + yr
        if (y == y2 and mo <= ev["month"] + ev["lead"] % 12) or y < y2:
            ev["active"], ev["countdown"] = 1, m


def _consequence(g, ev, c):
    """+0x56: 1 the city is destroyed (by the rival +0x6F, or by the monster for kind 7), 2 conquered by the rival."""
    from . import status_events
    k = eventmsg.byte(ev, 0x56)
    r = _rival(g, ev)
    if k == 1:
        status_events.destroyed(g, c, by=r, monster=_monster_name(g, ev) if ev.get("kind") == 7 else None)
    elif k == 2 and r is not None:
        status_events.conquered(g, c, r)


def dispatch(g, ev, slots=None, ships=None, heroes=None):
    """event_pay_tribute_or_gift for item 24 (army_dialog_dispatch): the chosen companies (None = every horseman and
    hoplite company at home), triremes and heroes march; state 6, countdown = the travel months (0 -> 12); flag 0x200
    when they will arrive after the deadline; Ares may join."""
    from . import events, war
    from .model import TROOPS
    c = eventmsg.city(g, ev.get("city"))
    if c is None or ev["state"] not in (0, 1) or not ev.get("active"):
        raise ValueError("this request is not open")
    comps, navy = war.eligible(g, _rival(g, ev) if ev.get("kind") == 2 and _rival(g, ev) else c)
    if slots is not None:
        bad = [s for s in slots if s not in comps]
        if bad:
            raise ValueError(f"companies {bad} can't go (horsemen and hoplites at home: {sorted(comps)})")
        comps = {s: comps[s] for s in slots}
    navy = list(ships) if ships is not None else navy
    hs = list(heroes or [])
    if not comps and not navy and not hs:
        raise ValueError("Assign some companies first! (horsemen or hoplites at home)")
    t = travel(g, ev)
    carrier = events.add(g, type="request_forces", city=c.id, item=TROOPS, sev=ev["id"], state=6,
                         companies=sorted(comps), triremes=list(navy), heroes=hs)
    ev["forces"] = carrier["id"]
    ev["strength"] = max(1, min(100, war.sent_strength(g, carrier)))          # +0x77: the world map's army size
    for comp in comps.values():
        comp["away"] = carrier["id"]
    from .. import military
    if navy:
        military.navy_send(g, carrier["id"], navy)
    if hs:
        war._heroes_go(g, carrier, hs)
    if military.on(g):
        military.march_out(g, carrier, sorted(comps))
    ev["state"] = 6
    ev["countdown"] = t if t >= 1 else 12
    if ev["lead"] < ev["countdown"]:
        ev["flags"] |= 0x200
    from .. import gods
    gods.expedition_sent(g, carrier)
    scenario.request_list_rebuild(g)
    return f"{len(comps)} companies march to {c.name} ({ev['countdown']} months)"


def _carrier(g, ev):
    from . import events
    return next((x for x in g.empire.events if x["id"] == ev.get("forces") and x["state"] != 10), None) \
        if ev.get("forces") is not None else None


def _home(g, ev, alert=False):
    """expedition_forces_home 0x004DEE60 (+ alert 14 at the land exit)."""
    from . import war
    car = _carrier(g, ev)
    if car is not None:
        war.forces_home(g, car)
    if alert:
        war._soldiers_alert(g)


def battle(g, ev, c):
    """distant_battle_resolve 0x00461540 for a troops request: (won, wiped)."""
    from . import war
    car = _carrier(g, ev)
    kind = ev.get("kind", 0)
    r = _rival(g, ev) if kind in (1, 2) else None
    p = war.sent_strength(g, car) if car is not None else 0
    E = ev["amount"]
    if kind == 2:
        p += c.army * 3 // 5
        if r is not None:
            E = r.army
    else:
        p += c.army
        if r is not None:
            E = r.army * 3 // 5
    if ev["flags"] & 0x400 and E // 2 < p:
        ev["flags"] |= 0x800                                           # attack averted: no battle
        return True, False
    if ev["flags"] & 0x200:
        E = E * 70 // 100
    if p < E:
        d = (E - p) * 100 // E if E else 0
        pl, en, al = 80, war.tier(war.LOSS_T, d, 10, 0), 50
        win = False
    else:
        d = (p - E) * 100 // p if p else 0
        x = 10 if d <= 74 else 0
        pl, en, al = war.tier(war.CONQUER_WIN, d, (x, 50, x), (x, 50, x))
        win = True
    wiped = war.casualties(g, car, pl) if car is not None else True
    c.army -= c.army * al // 100
    if r is not None:
        r.army -= en * E // 100
    if c.strength == 6 and kind == 2:
        win = False
    scenario.log(g, f"event #{ev['id']}: battle for {c.name}: {p} against {E}: {'won' if win else 'lost'}")
    return win, wiped


scenario.register(1, handler, owner="1L-5 requests (sim/empire/requests.py)")
