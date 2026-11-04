"""Consult Oracle (Zeus' and Apollo's sanctuary window, docs/logic/religion.md "Oracle").

oracle_consult 0x004EA630 (table {god, cost_auto, cost_consult, threshold} = {0, 10, 18, 14}, {3, 8, 16, 12}): available
while the god record's oracle counter (+0x10, -1 a month: month.py) < threshold. The button (wm_sub_408EB0) consults:
counter + cost_consult, then FUN_0047F6C0(1): among the scenario's events those FUN_0047F4C0 accepts, a random one
(rng % count) gets flag 0x40 (warn) and the monthly dispatch runs, so its handler posts its oracle warning; when no
message came, it picks again; none left -> the "nothing foreseen" message (title 0xB88, announcement 0xB89,
reason 0xB8A; PHRASE_oracle_nothing_*).
FUN_0047F4C0: not flags 0x40 / 0x01 / 0x20000; m = months since the event's date ((year - start - ev year) * 12 -
month + ev month); type 0x13 (invasion) with 0 < m < 13 and kind (+0x60) in 2, 3, 0xD, 0x16; type 0x1B (god
invasion) with 0 < m < 13; type 0x1A (monster) in state 4 with lead < months until due <= lead + 12; type 1 (fields
+0x2C..+0x32 not mapped in ours: not offered).
"""
from . import rec, rng, built, NAMES
from .month import log

TABLE = {0: (10, 18, 14), 3: (8, 16, 12)}       # god -> (cost_auto, cost_consult, threshold)


def has_oracle(i):
    """god_has_oracle 0x004EA600."""
    return i in TABLE


def available(g, i):
    return has_oracle(i) and rec(g, i)["oracle"] < TABLE[i][2]


def _months_since(g, ev):
    from .. import scenario
    y, m = scenario.today(g)
    return (y - ev["year"]) * 12 - m + ev["month"]


def _offered(g, ev):
    from .. import scenario
    f = ev["flags"]
    if f & (0x40 | 0x01 | 0x20000):
        return False
    t = ev["type"]
    if t == 0x13:
        return 0 < _months_since(g, ev) < 13 and ev.get("kind", 0) in (2, 3, 0xD, 0x16)
    if t == 0x1B:
        return 0 < _months_since(g, ev) < 13
    if t == 0x1A:
        if ev.get("state") != 4:
            return False
        lead = ev.get("lead", 0)
        return lead < scenario.months_until_due(g, ev) <= lead + 12
    return False


def consult(g, i):
    """The button: (ok, text)."""
    if not built(g, i):
        return False, f"{NAMES[i]} has no built sanctuary"
    if not available(g, i):
        return False, f"{NAMES[i]}'s oracle is unavailable"
    r = rec(g, i)
    r["oracle"] += TABLE[i][1]
    from .. import scenario, messages
    while True:
        cands = [ev for ev in scenario.events(g) if _offered(g, ev)]
        if not cands:
            try:
                messages.post(g, 0xB88, 0xB89)
            except KeyError:
                g.message("The oracle foresees nothing")
            log(g, f"{NAMES[i]}'s oracle foresees nothing")
            return True, "the oracle foresees nothing"
        ev = cands[rng(g).randrange(32768) % len(cands)]
        ev["flags"] |= 0x40
        n = len(g.city.messages)
        scenario.dispatch(g, ev)
        if len(g.city.messages) != n:
            log(g, f"{NAMES[i]}'s oracle foretells event #{ev['id']} (type {ev['type']})")
            return True, f"the oracle foretells event #{ev['id']}"
