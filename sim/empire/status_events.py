"""Scenario event type 19, City status change (event_city_status_change 0x00473680), registered with sim/scenario
(PLUGINS). 1L-3 added the change itself (the campaigns' end-of-episode records, flag 0x20000, dispatched by
scenario.episode_end); 1L-5 the whole handler: messages, the oracle's warning, subtypes 8, 13, 22 and 24, the
follow-up records, the chain.

  not due: WARN and not WARNED -> WARNED, and the oracle's prediction (the announcement phrase - 1) when the
           change would happen; nothing else
  due:     DONE; city +0x1C (0..21). Subtype 24 (0x18): the city is conquered by city +0x6F when that city exists and
           is a rival (FUN_0046EAC0). Else the subtype's new state (trade open +5, rebellion +0x174&1, tribute mode
           +0xE0, relationship +0xD4, strength +0xDC, wealth +0xD8, active +0x170, hidden +0x174&4); it is applied
           when the city is not destroyed nor an inactive colony, is shown (visible and active) or the change is
           its visibility / activity, and something changes. Then (not for end-of-episode records, 0x20000) the
           message 0xE0 (title, announcement by subtype) unless trade reopens with a city that is no trading
           partner; the history record; the follow-up record (subtype 0 -> 1 a year later; 6 -> 0x17 and 13 -> 0x16
           after the lead months, FUN_00473600); the chained record (FUN_004694A0 / event_chain_trigger).
"""
from .. import scenario
from . import relations

# subtype -> (title, announcement, history phrase); 13 / 22 by the god (+0x36): FUN_004734B0 (title family),
# FUN_00473410 (history)
MSG = {0: (0x2EA, 0x2EB, 0xBD9), 1: (0x2F0, 0x2F1, 0xBD7), 2: (0x2F6, 0x2F8, 0xBD8), 3: (0x2FE, 0x300, 0xBD6),
       4: (0x346, 0x347, 0xBDE), 5: (0x34C, 0x34D, 0xBDD), 6: (0x352, 0x353, 0xBDA), 7: (0x358, 0x359, 0xBDC),
       8: (0x410, 0x411, 0xBDA), 9: (0x39E, 0x39F, 0xBE5), 10: (0x3A4, 0x3A5, 0xBE6), 12: (0x3A4, 0x3A5, 0xBE6),
       11: (0x3AA, 0x3AB, 0xBE7), 14: (0x366, 0x368, 0xBD4), 15: (0x36E, 0x370, 0xBD5), 16: (0x376, 0x378, 0xBD3),
       17: (0x37E, 0x380, 0xBD2), 18: (0xC7F, 0xC80, 0xC97), 19: (0xC85, 0xC86, 0xC98), 20: (0xC8B, 0xC8C, 0xC99),
       21: (0xC91, 0xC92, 0xC9A), 0x17: (0x35E, 0x360, 0xBDB)}
GOD_FAMILY = [0x7BC, 0x7CC, 0x7EC, 0x80C, 0x81C, 0x82C, 0x84C, 0x85C, 0x7FC, 0x83C, 0x86C, 0x7DC, 0xDD5, 0xDE5]
GOD_HISTORY = [0xBD1, 0xBD0, 0xBCB, 0xBC7, 0xBC9, 0xBC8, 0xBC6, 0xBCF, 0xBCA, 0xBCE, 0xBCC, 0xBCD, 0xE15, 0xE16]
REL_CODE = {"ally": 0, "rival": 1, "vassal": 2, "colony": 3}
CODE_REL = {v: k for k, v in REL_CODE.items()}


def plan(c, ev):
    """(new state, title, announcement, history) of subtype ev["kind"] on city c, as the handler's switch: the
    fields as the exe keeps them (relationship code, tribute mode, trade open, strength, wealth, rebellion, active,
    hidden); title None = this subtype does nothing for this city."""
    rel = REL_CODE.get(c.relation, 1)
    s = dict(rel=rel, mode=c.tribute["mode"], trade=bool(c.trade_open), strength=c.strength, wealth=c.wealth,
             rebel=bool(c.rebellion), active=bool(c.active), hidden=not c.visible)
    sub, amount, god = ev.get("kind", 0), ev.get("amount", 0) or 0, ev.get("b36", 0) & 0xFF
    t = MSG.get(sub)
    if sub == 0 or sub == 2:
        s["trade"] = False
    elif sub in (1, 3):
        s["trade"] = True
    elif sub in (4, 5):
        if rel not in (2, 3):
            return s, None, None, -1
        s["mode"] = 0 if sub == 4 else 1
    elif sub == 6:
        if rel not in (2, 3):
            return s, None, None, -1
        s.update(trade=False, rebel=True, mode=0)
    elif sub == 7 or sub == 0x17:
        if rel not in (2, 3):
            return s, None, None, -1
        s.update(trade=True, rebel=False, mode=1)
    elif sub == 8:
        if rel != 3:
            return s, None, None, -1
        s["mode"] = 0
    elif sub == 9:
        if rel != 1:
            return s, None, None, -1
        s.update(rel=0, trade=True, rebel=False)
    elif sub in (10, 12):
        if rel not in (0, 2):
            return s, None, None, -1
        s.update(rel=1, trade=False, rebel=False, mode=0)
    elif sub == 11:
        if rel not in (1, 0):
            return s, None, None, -1
        s.update(rel=2, trade=True, rebel=False, mode=1)
    elif sub == 13:                                   # a god's disaster on the city: trade stops
        s["trade"] = False
        f = GOD_FAMILY[god] if god < len(GOD_FAMILY) else 0x7BC
        t = (f, f + 2, GOD_HISTORY[god] if god < len(GOD_HISTORY) else 0xBD1)
    elif sub == 22:                                   # ... and ends: trade again, no history record
        s["trade"] = True
        f = GOD_FAMILY[god] if god < len(GOD_FAMILY) else 0x7BC
        t = (f + 8, f + 10, -1)
    elif sub == 14:
        s["strength"] = min(amount + c.strength, 5)
    elif sub == 15:
        s["strength"] = max(c.strength - amount, 1)
    elif sub == 16:
        s["wealth"] = min(amount + c.wealth, 5)
    elif sub == 17:
        s["wealth"] = max(c.wealth - amount, 1)
    elif sub in (18, 19):
        s["active"] = sub == 18
    elif sub in (20, 21):
        s["hidden"] = sub == 21
    if t is None:
        return s, None, None, -1
    return s, t[0], t[1], t[2]


def _now(c):
    return dict(rel=REL_CODE.get(c.relation, 1), mode=c.tribute["mode"], trade=bool(c.trade_open),
                strength=c.strength, wealth=c.wealth, rebel=bool(c.rebellion), active=bool(c.active),
                hidden=not c.visible)


def _apply(g, c, s):
    c.relation = CODE_REL.get(s["rel"], "rival") if c.relation in REL_CODE else c.relation
    c.strength, c.wealth, c.trade_open = s["strength"], s["wealth"], s["trade"]
    c.tribute["mode"], c.rebellion, c.active, c.visible = s["mode"], s["rebel"], s["active"], not s["hidden"]
    c.goods_flags = c.trading()                       # buys / sells flags rebuilt for trading partners (6.8)
    g.map_version = getattr(g, "map_version", 0) + 1  # buildings_availability follows the allowed goods


def handler(g, ev):
    warn = False
    if not scenario.due(g, ev):
        f = ev["flags"]
        if not f & scenario.WARN or f & scenario.WARNED:
            return
        warn = True
        ev["flags"] |= scenario.WARNED
    else:
        ev["flags"] |= scenario.DONE
    e = getattr(g, "empire", None)
    cid = ev.get("city", -1)
    c = e.cities.get(cid) if e is not None and 0 <= cid < 22 else None
    silent = bool(ev["flags"] & scenario.DISABLED)    # 0x20000: an end-of-episode record (no messages, no chain)
    if c is not None and ev.get("kind", 0) == 24:
        raw = bytes.fromhex(ev.get("raw") or "")
        other = e.cities.get(raw[0x6F]) if len(raw) > 0x6F else None     # +0x6F: the conqueror
        if not warn and other is not None and other.exists() and other.cls() == "rival":
            conquered(g, c, other)
    elif c is not None:
        before = _now(c)
        s, title, ann, hist = plan(c, ev)
        shown = c.visible and c.active
        ok = (title is not None and not (c.kind == "colony" and not c.active) and c.kind != "destroyed"
              and (shown or s["hidden"] != before["hidden"] or s["active"] != before["active"]) and s != before)
        if ok:
            if warn:
                ann -= 1                              # the oracle's prediction phrase
            else:
                if ev.get("kind") == 9 and before["rel"] == 1:
                    from ..systems import commemorative
                    commemorative.grant(g, 8)         # FUN_00402B00(8): a Diplomacy Monument
                _apply(g, c, s)
            if not silent and (before["trade"] or not s["trade"] or c.trading() or warn):
                if not s["hidden"] or s["hidden"] != before["hidden"]:
                    from .. import messages
                    messages.post(g, title, ann, city=c)
            if warn:
                return
            if hist >= 0:
                relations.note(g, c, hist)
            _follow_up(g, ev)
    if warn:
        return
    if not silent:
        t = scenario.get(g, ev.get("chain", -1))
        if t is not None and t["flags"] & scenario.TEMPLATE and t["id"] != ev["id"]:
            scenario.chain(g, ev)


def _follow_up(g, ev):
    """FUN_00473600: a new type-19 record (a copy, DYNAMIC, state 0) with the next subtype: after a trade suspension
    (0) trade resumes (1) a year later; after a rebellion (6) it ends (0x17), after a god's disaster (13) the city
    recovers (0x16) when the lead months (+0x2C) have passed."""
    sub = ev.get("kind", 0)
    if sub == 0:
        year, month, nxt = ev["year"] + 1, ev["month"], 1
    elif sub in (6, 13):
        m = ev.get("lead", 0) + ev["month"]
        year, month, nxt = m // 12 + ev["year"], m % 12, 0x17 if sub == 6 else 0x16
    else:
        return
    import copy
    rec = {k: copy.deepcopy(v) for k, v in ev.items() if k != "id"}
    rec.update(type=19, year=year, month=month, state=0, kind=nxt, flags=scenario.DYNAMIC)
    new = scenario.alloc(g, rec)
    if new is not None:
        scenario.log(g, f"event #{ev['id']}: follow-up #{new['id']} (status {nxt}) {month + 1}/{year}")


def conquered(g, c, by):
    """FUN_0046EAC0: city c is taken by the rival `by` (subtype 24, or an unanswered request for help): the message by
    c's class (vassal 0x3D4 / colony 0x3DA / else ally 0x3CE; none for a rival), c becomes a rival (+0xD4 = 1), its
    rebellion ends, no tribute; history 0xBEA / 0xBE9 / 0xBE3 with the conqueror. The buys/sells flags are left as
    they are (subtype 24 skips event_city_status_change's rebuild; world-map.md 6.8, bug 472)."""
    cls = c.cls()
    title, hist = {"vassal": (0x3D4, 0xBEA), "colony": (0x3DA, 0xBE9)}.get(cls, (0x3CE, 0xBE3))
    if cls != "rival":
        from .. import messages
        nat = messages._data()["nationality"]
        messages.post(g, title, title + 1, city=c, rival_city_name=by.name,
                      rival_nationality=nat[by.nation] if 0 <= by.nation < len(nat) else "")
    c.relation, c.rebellion, c.tribute["mode"] = "rival", False, 0
    relations.note(g, c, hist)


# FUN_00477AB0 by city_class: (title by a rival, by a monster); history 0xBE4 / 0xBEE / 0xBEB, monster 0xBEF / 0xBF0
DESTROYED = {"ally": (0xB02, 0x8DA, 0xBE4, 0xBEF), "vassal": (0xB08, 0x8E0, 0xBEE, 0xBEF),
             "parent": (0xB14, 0x8EC, 0xBE4, 0xBEF), "colony": (0xB0E, 0x8E6, 0xBEB, 0xBF0)}
LOSE_PARENT_DESTROYED, LOSE_PARENT_FALLS = 0xB93, 0xB94


def destroyed(g, c, by=None, monster=None):
    """FUN_00477AB0 (called by event_troops_request_update 0x0046ED70 when an ally's call for help went unanswered,
    request +0x56 == 1): city c is destroyed by the rival `by` (+0x6F) or, for a quest request (+0x60 == 7), by a
    monster: the message by c's class (ally / vassal / parent / colony; any other class: nothing happens), the
    history record, c becomes kind 6 (destroyed). The parent city (class 3, while the player is in a colony): the
    episode is lost, 0xB93 by a monster / 0xB94 by a rival (0x00FEB160, then goals_month_check at once): the core
    sets g.episode_lost, the campaign's day hook takes it (sim/campaign/goals.py). Returns False when nothing
    happened."""
    cls = c.cls() if c.kind != "parent" else "parent"
    row = DESTROYED.get(cls)
    if row is None:
        return False
    title = row[1] if monster is not None else row[0]
    from .. import messages
    nat = messages._data()["nationality"]
    kw = dict(rival_city_name=by.name if by else "",
              rival_nationality=nat[by.nation] if by is not None and 0 <= by.nation < len(nat) else "")
    if monster is not None:
        kw["monster"] = monster
    # by a monster (+0x60 == 7): FUN_005A1210(4) first, S_mon1 (play mode: viewer/play/audio.js specials)
    messages.post(g, title, title + 1, city=c, meta=dict(stinger="mon1") if monster is not None else None, **kw)
    relations.note(g, c, row[3] if monster is not None else row[2])
    c.kind = "destroyed"
    g.map_version = getattr(g, "map_version", 0) + 1
    if cls == "parent":
        g.episode_lost = LOSE_PARENT_DESTROYED if monster is not None else LOSE_PARENT_FALLS
    return True


scenario.register(19, handler, owner="1L-3/1L-5 city status change (sim/empire/status_events.py)")
