"""A scenario event's message (FUN_00521A70 with the parameter block FUN_00474500 fills from the record), for the
handlers in sim/empire (requests, invasions, city events). Track 1L-5.

The block (short[]): +0 announcement, +2 title, +6 / +0x12 the city, +8 / +0x18 amount, +0xA / +0x1A item, +0xC the
lead months (+0x2C; the handlers overwrite it with the months they mean), +0xE event_months_until_due, +0x10 the
reason phrase, +0x1E the second city (+0x6F). The variables (table 0x005FBA2C, one reader each) read it:
[amount] +8, [item] / [itemshort] +0xA, [time_allotted] / [travel_time] +0xC (wm_sub_465E60 / 465E90),
[time_until_attack] +0xE (wm_sub_465EC0), [reason_phrase] the phrase at +0x10 rendered with the second set
(wm_sub_465EF0 sets 0x00916DF0: +0x12 city, +0x18 amount, +0x1A item: a chained record's parent values, FUN_00474500),
[a_foreign_army] text group 37 entry 22 + the city's nationality (wm_sub_465FB0), [rival_city_name] /
[rival_nationality] the city at +0x6F, [monster] the monster of the record's slot (+0x36).
"""
from .. import messages, scenario


def byte(ev, off):
    """A byte of the record that the sim does not keep as a field (the file's 124 bytes)."""
    raw = bytes.fromhex(ev.get("raw") or "")
    return raw[off] if len(raw) > off else 0


def city(g, i):
    e = getattr(g, "empire", None)
    return e.cities.get(i) if e is not None and i is not None and 0 <= i < 22 else None


def foreign_army(nation):
    t = messages._data()["history"].get("foreign_army", [])
    return t[nation] if 0 <= nation < len(t) else ""


def variables(g, ev, c=None, **over):
    """The message variables of record ev (FUN_00474500's block), `over` replacing any of them."""
    if c is None:
        c = city(g, ev.get("city2") if ev["type"] == 2 else ev.get("city"))
    item = ev.get("item")
    long, short = messages.item_words(item) if item is not None else ("", "")
    v = dict(amount=ev.get("amount", 0), item=long, itemshort=short, time_allotted=ev.get("lead", 0),
             travel_time=ev.get("lead", 0), time_until_attack=scenario.months_until_due(g, ev))
    if c is not None:
        v["a_foreign_army"] = foreign_army(getattr(c, "nation", 0))
    r = city(g, byte(ev, 0x6F))
    if r is not None:
        nat = messages._data()["nationality"]
        v["rival_city_name"] = r.name
        v["rival_nationality"] = nat[r.nation] if 0 <= r.nation < len(nat) else ""
    v.update(over)
    return c, v


def reason(g, ev, pid, c, v, condensed=False):
    """[reason_phrase]: the reason phrase's text with the second variable set (a chained record: its parent's city,
    amount and item, FUN_00474500 +0x12/+0x18/+0x1A). condensed: the panel strip's (wm_sub_465EF0 with 0x00916DF1:
    the reason's condensed phrase, messages.condensed_reason)."""
    if pid is None or pid < 0:
        return ""
    ph = messages._data()["phrases"].get(str(pid))
    if ph is None:
        return ""
    if condensed:
        ph = (None, messages.condensed(pid))
        if ph[1] is None:
            return ""
    v2 = dict(v)
    c2 = c
    if scenario.get(g, ev.get("parent", -1)) is not None:
        v2["amount"] = ev.get("pamount", v2["amount"])
        long, short = messages.item_words(ev.get("pitem"))
        v2.update(item=long, itemshort=short)
        if ev.get("b63"):
            c2 = city(g, ev["b63"]) or c
    v2.pop("reason_phrase", None)
    return messages.fill(ph[1], city=c2, **v2)


def post(g, title, body, ev, reason_id=None, c=None, popup=True, record=None, buttons=0, stinger=None, **over):
    """Post title + announcement for record ev (FUN_00521A70 0xDF / 0xE0 / 0xDE ...: ours one message). record: the
    message record when it matters to the window (0xDF = Zeus_MM 223, type 2: the item icon, amount and "n months to
    comply" from the block's +8 / +0xA / +0xC, help_page_draw 0x004F2D80); buttons: the block's flags +0x16 (0x1C0 =
    Dispatch now / Postpone / Refuse, wm_sub_475AB0 / 475B20 / 475B50)."""
    c, v = variables(g, ev, c, **over)
    cv = None
    if "reason_phrase" not in over:
        v["reason_phrase"] = reason(g, ev, reason_id, c, v)
        cv = dict(reason_phrase=reason(g, ev, reason_id, c, v, condensed=True))
    if c is None:
        from types import SimpleNamespace
        c = SimpleNamespace(name="", leader="", nation=0)
    meta = None
    if record is not None or buttons:
        from . import requests
        it = ev.get("item")
        meta = dict(type=2 if record == 0xDF else 0, event=ev["id"] if ev["type"] == 1 else None, item=it, good=requests.good_key(it) or (
            {requests.MONEY_ID: "drachmas", requests.TROOPS_ID: "troops", requests.FOOD_ID: "food"}.get(it, "")),
            goodName=v.get("item", "") if ev.get("amount", 0) > 1 or it in (0xB, 0x10) else v.get("itemshort", ""), amount=ev.get("amount", 0), months=v.get("time_allotted", 0), buttons=buttons)
        if ev["type"] != 1:            # the window shows the months while the record is in state 0 (the poster knows)
            meta["months"] = v.get("time_allotted", 0) if ev.get("state", 0) == 0 else None
    if stinger:                        # FUN_005A1210 (play mode: viewer/play/audio.js specials)
        meta = dict(meta or {}, stinger=stinger)
    messages.post(g, title, body, popup=popup, city=c, meta=meta, condensed_vars=cv, **v)
