"""Incoming goods, money and troops: the exe's offer dialog (incoming_goods_dialog 0x004745E0; world-map.md 6.8).

Every gift from a city (type 0x17, event_gift 0x00474A80; debt rescue item 23 flags 0x110), tribute paid to the
player (0x1D, 0x00474F60), granted request (0x20, 0x004752A0) and raid plunder (0x20 flags 0x4100, FUN_0047F930)
is an offer the player answers in the message window: Accept (bit 4, 44:209), Postpone (2, 44:211), Decline
(1, 44:210). Room = the amount for money, else what storage could take (0x00488A60 = city_goods_add 0x00489230 dry
run) in loads; half = (amount + 1) / 2 (tribute: 1). b5 = the offer was postponed twice (state 4/5) or is tribute
(its state 0..3 is forced to 4: tribute never gets Postpone):

    room >= amount             granted (cash granted)    Accept + Decline
    half <= room < amount      partial space             Accept + Postpone + Decline   (b5: last chance, A + D)
    room < half                insufficient space        Postpone + Decline             (b5: forfeited, no buttons)
    state 0/1 -> 1, 2/3 -> 3, 4/5 -> 5 (no buttons: 8 = forfeited, the event ends)

Accept (0x004757F0): money to the treasury ("gifts received" 0x00FEAEB0; tribute: "tribute received" 0x00FEB500),
goods into storage (what does not fit is lost; the "accepted" message only when it did not all fit); a debt
rescue costs 10 attitude and marks the city (+0x175). Decline (0x00475850): the "refused" message, no attitude
effect. Postpone (0x004758A0): state 1 -> 2, 3 -> 4, re-offered next month; any other state -> forfeited.
Unanswered offers are offered again every month. Troops (item 24): Accept + Decline only (title 0x462); the
event waits in state 0 until answered; accepting brings the city's soldiers onto the map (war.aid_accept).

Message categories (Options > Messages; FUN_00521970): when the offer's category is not Full (2), tribute with
Accept is accepted and every other offer postponed (troops forfeited), as the exe does. The levels live in
`g.sd("msg_levels")` ({category: 0 Off, 1 Condensed, 2 Full}; `msglevel CAT LEVEL`). Categories: gift, granted,
rescue 5 (Gifts and Tribute); plunder, troops 0 (City News); tribute 16 (Tribute payments).

The play-mode hook (viewer/play/offers.js): `export(g)` lists the open offers (state.json "offers": id, title,
body, buttons); the window's buttons send `offer ID accept|postpone|decline`.
"""
from . import events, relations
from .model import MONEY, TROOPS, units

ACCEPT, POSTPONE, DECLINE = 4, 2, 1
TITLE = {"gift": 0x25A, "rescue": 0x2B4, "granted": 0x278, "plunder": 0xBA8, "tribute": 0x296}
CATEGORY = {"gift": 5, "rescue": 5, "granted": 5, "plunder": 0, "tribute": 16, "troops": 0}
# body = TITLE + 1 + k: 0 granted, 1 cash granted, 2 partial space, 3 insufficient, 4 last chance, 5 forfeited,
# 6 accepted, 7 cash accepted, 9 refused
GRANTED, CASH, PARTIAL, INSUFFICIENT, LAST, FORFEITED, ACCEPTED, CASH_ACCEPTED, REFUSED = 0, 1, 2, 3, 4, 5, 6, 7, 9
TROOPS_TITLE, TROOPS_BODY = 0x462, 0x463
NAMES = {"olive_oil": "olive oil", "black_marble": "black marble", "drachmas": "drachmas", "meat": "meat"}


def item_name(item):
    return NAMES.get(item, item.replace("_", " "))


def room(g, item, amount):
    """Loads that fit now (0x00488A60): money always fits; goods: storage room in units / 100 (sculpture / 400)."""
    if item == MONEY:
        return amount
    from ..systems import economy
    n = sum(economy.storage_room(g, s, item) for s in economy._stores(g) if s.kind == "storage")
    return n // units(item, 1)


def create(g, kind, c, item, amount, **kw):
    """A new offer, dispatched at once (the exe's event dated today)."""
    ev = events.add(g, type="offer", kind=kind, city=c.id, item=item, amount=amount, countdown=0, **kw)
    offer(g, ev)
    return ev


def _post(g, ev, body, buttons):
    from .. import messages
    c = g.empire.cities[ev["city"]]
    long, short = messages.item_words(ev["item"])
    kw = dict(city=c, amount=ev["amount"], item=long, itemshort=short)
    title = TROOPS_TITLE if ev["kind"] == "troops" else TITLE[ev["kind"]]
    same = ev.get("phrase") == body and ev.get("buttons") == buttons
    ev["title"], ev["body"], ev["phrase"] = messages.text(title, **kw), messages.text(body, **kw), body
    ev["buttons"] = buttons
    if not same:                        # ours: a monthly re-offer with the same text and buttons is not logged again
        ev["posted"] = g.tick           # (the exe re-opens the dialog; whether it adds a list entry: not certain)
        g.message(messages.line(title, body, **kw))


def _say(g, ev, k):
    """A plain message of the offer's family (accepted, refused, forfeited)."""
    from .. import messages
    c = g.empire.cities[ev["city"]]
    long, short = messages.item_words(ev["item"])
    kw = dict(city=c, amount=ev["amount"], item=long, itemshort=short)
    t = TITLE[ev["kind"]]
    g.message(messages.line(t, t + 1 + k, **kw))


def offer(g, ev):
    """incoming_goods_dialog 0x004745E0: pick the text and the buttons, advance the state."""
    if ev["kind"] == "troops":
        _post(g, ev, TROOPS_BODY, ACCEPT | DECLINE)
        return _auto(g, ev)
    st = ev["state"]
    tribute = ev["kind"] == "tribute"
    if tribute and st <= 3:
        st = 4
    b5 = st in (4, 5)
    amount = ev["amount"]
    r = room(g, ev["item"], amount)
    half = 1 if tribute else (amount + 1) // 2
    if r >= amount:
        k, btn = (CASH if ev["item"] == MONEY else GRANTED), ACCEPT | DECLINE
    elif r >= half:
        k, btn = (LAST, ACCEPT | DECLINE) if b5 else (PARTIAL, ACCEPT | POSTPONE | DECLINE)
    else:
        k, btn = (FORFEITED, 0) if b5 else (INSUFFICIENT, POSTPONE | DECLINE)
    ev["state"] = (1 if st <= 1 else 3 if st <= 3 else 5) if btn else (2 if st <= 1 else 4 if st <= 3 else 8)
    _post(g, ev, TITLE[ev["kind"]] + 1 + k, btn)
    if ev["state"] == 8:
        ev["buttons"] = 0
        return events.done(ev)
    _auto(g, ev)


def level(g, cat):
    return int(g.sd("msg_levels", {}).get(str(cat), 2))


def _auto(g, ev):
    """FUN_00521970: a category not set to Full answers the dialog itself."""
    if level(g, CATEGORY[ev["kind"]]) == 2:
        return
    if ev["kind"] == "tribute" and ev["buttons"] & ACCEPT:
        return answer(g, ev, "accept")
    return answer(g, ev, "postpone")


def month(g, ev):
    """Monthly (scenario_events_monthly): a postponed or unanswered offer is offered again."""
    if ev["state"] in (0, 1, 2, 3, 4, 5):
        offer(g, ev)


def find(g, ev_id=None):
    live = [ev for ev in events.live(g, "offer") if ev.get("buttons")]
    if ev_id is None:                    # the newest open one
        return live[-1] if live else None
    return next((ev for ev in live if ev["id"] == ev_id), None)


def answer(g, ev, choice):
    """The dialog's buttons: accept 0x004757F0, decline 0x00475850, postpone 0x004758A0."""
    bit = {"accept": ACCEPT, "postpone": POSTPONE, "decline": DECLINE}[choice]
    if not ev.get("buttons", 0) & bit:
        raise ValueError(f"this offer can't be {dict(accept='accepted', postpone='postponed', decline='declined')[choice]} now")
    c = g.empire.cities[ev["city"]]
    ev["buttons"] = 0
    if ev["kind"] == "troops":
        if choice == "accept":
            from . import war
            return war.aid_accept(g, ev, c)
        from .. import messages
        long, short = messages.item_words(TROOPS)
        g.message(messages.line(0x278, 0x282, city=c, amount=ev["amount"], item=long, itemshort=short))
        ev["state"] = 7
        events.done(ev)
        return f"declined the troops from {c.name}"
    if choice == "postpone":
        if ev["state"] in (1, 3):
            ev["state"] += 1
            ev["countdown"] = 1
            return f"postponed: {c.name} offers again next month"
        ev["state"] = 8
        _say(g, ev, FORFEITED)
        events.done(ev)
        return "forfeited"
    if choice == "decline":
        ev["state"] = 7
        _say(g, ev, REFUSED)
        events.done(ev)
        return f"declined the {item_name(ev['item'])} from {c.name}"
    ev["state"] = 6
    item, amount = ev["item"], ev["amount"]
    t = g.empire.totals
    if item == MONEY:
        g.city.treasury += amount
        t["tribute_received" if ev["kind"] == "tribute" else "gifts_received"] += amount
        got = amount
    else:
        from . import diplomacy
        got = diplomacy.deliver(g, item, units(item, amount)) // units(item, 1)
        if got < amount:
            _say(g, ev, ACCEPTED)
    if ev["kind"] == "rescue":
        relations.attitude_add(g, c, -10, 0xBF5, 0, MONEY)        # event_gift: rescue_cash_history
        c.extorted = True
    events.done(ev)
    return f"accepted {got} {item_name(item) if item == MONEY else 'loads of ' + item_name(item)} from {c.name}"


def export(g):
    """state.json "offers": the open dialogs (viewer/play/offers.js)."""
    e = getattr(g, "empire", None)
    if e is None:
        return []
    out = []
    for ev in events.live(g, "offer"):
        if ev.get("buttons"):
            out.append(dict(id=ev["id"], kind=ev["kind"], title=ev.get("title", ""), body=ev.get("body", ""),
                            tick=ev.get("posted", g.tick), category=CATEGORY[ev["kind"]],
                            accept=bool(ev["buttons"] & ACCEPT), postpone=bool(ev["buttons"] & POSTPONE),
                            decline=bool(ev["buttons"] & DECLINE)))
    return out


def text(g):
    live = events.live(g, "offer")
    if not live:
        return "no offers waiting"
    out = []
    for ev in live:
        b = ev.get("buttons", 0)
        opts = "/".join(k for k, v in (("accept", ACCEPT), ("postpone", POSTPONE), ("decline", DECLINE)) if b & v)
        out.append(f"{ev['id']}: {ev.get('title', '')}: {ev['amount']} {item_name(ev['item'])} [{opts or 'waiting'}]")
    return "\n".join(out)
