"""sanctuary_update 0x004E94C0 (cycle step 31, per sanctuary): timers, priests, the god's visits.

    complete (progress > 99):
        +0xC4 bit 8 (its guardian killed): +0xC8 (0xC0 at the kill) -1 a day, at 0 the bit clears
        (+0x64 set and activity > 24 -> 22: +0x64 has no known writer on sanctuaries; not ported)
        staffed (workers != 0):
            priests (sanctuary_priests_update 0x004E97D0): on day 0 activity -= 1 (u8: 0 wraps to 255), and below 20
                one more priest goes out for a sacrifice (priests.py)
            the god is on the map from here: visit timer 16; else activity 0: timer 1 (no visit); else timer =
            min(timer, 16) and -1 a day; at 0 the god appears (figures.visit_start)
"""
from . import sanctuary, god_of, dom, GODS


def update(g):
    from ..systems import index, monuments
    from . import priests, figures
    for b in index.of(g, "monument"):
        if not b.key.startswith("sanctuary_") or not monuments.complete(b):
            continue
        i = god_of(b)
        if i < 0 or sanctuary(g, i) is not b:
            continue
        m = b.misc
        if m.get("guardian_killed"):             # +0xC4 & 8: +0xC8 -1 a day, at 0 the flag clears (a new guardian)
            d = max(0, m.get("guardian_days", 0) - 1)
            m["guardian_days"] = d
            if d < 1:
                m.pop("guardian_killed", None)
                m.pop("guardian_days", None)
        if not b.employees:
            continue
        if dom(g) == 0:
            m["activity"] = (m.get("activity", 0) - 1) & 0xFF
        priests.update(g, b, i)
        w = figures.figure(g, i)
        if w is not None and w.home == b.id:
            m["visit_timer"] = 16
            continue
        if not m.get("activity", 0):
            m["visit_timer"] = 1
            continue
        t = min(m.get("visit_timer", 0), 16)
        if t:
            m["visit_timer"] = t - 1
            continue
        figures.visit_start(g, i, b)


__all__ = ["update", "GODS"]
