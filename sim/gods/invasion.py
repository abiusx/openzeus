"""God invasion, scenario event type 27 (`event_god_attack` 0x00482B10), registered with the scenario module's
dispatch (sim/scenario, track 1G: `scenario.register(27, handler)`). docs/logic/religion.md "Scenario god attack".

    on the event's date: flags |= 4 (done; a recurring one re-arms), the god arrives (god_attack_arrival
    0x004EBBD0: Zeus, Aphrodite, Athena, Hades, Hera at the palace's road tile, else the first building with road
    access, else the land entry; Poseidon at the sea entry; the others at the land entry; Hermes appears at the land
    entry and walks to it), action 10 -> 0x36 (attack), budget A = 3; message 0xDE (title PHRASE_<god>_invades_title,
    announcement ..._city_attacked_alert); then one defender god (each only with a built sanctuary): Zeus against
    anyone, else Aphrodite against Ares / Hephaestus / Hermes / Dionysus, else Hera against Zeus; then the chained
    event (+0x24).
    before the date, with flag 0x40 (warn) and not 0x80: once, the oracle's warning (..._oracle_prediction).
"""
from . import state, GODS, NAMES
from .month import log

# PHRASE_<god>_invades_title per god (event_god_attack's switch); announcement +1 warning / +2 attack, reason +4
INVADES = {0: 0x5C4, 1: 0x5D0, 2: 0x5E8, 3: 0x600, 4: 0x60C, 5: 0x618, 6: 0x630, 7: 0x63C, 8: 0x5F4, 9: 0x624,
           10: 0x648, 11: 0x5DC, 12: 0xDAD, 13: 0xDB9}


def arrival(g, i):
    """god_attack_arrival 0x004EBBD0 -> tile or None (the event is then marked done, nothing comes)."""
    w = g.world
    if i in (0, 6, 8, 11, 12):
        pal = [b for b in g.buildings.values() if b.key == "palace"]
        if pal and pal[0].access:
            return tuple(pal[0].access)
        roots = sorted((b for b in g.buildings.values() if b.access), key=lambda b: b.id)
        if roots:
            return tuple(roots[0].access)
        return tuple(w.entry)
    if i == 1:
        se = getattr(w, "sea_entry", None)
        return tuple(se) if se else None
    if i in (2, 3, 4, 5, 7, 9, 10, 13):
        return tuple(w.entry)
    return None


def handler(g, ev):
    from .. import scenario
    from .. import gods
    if not gods.on(g):
        return
    warn = False
    if not scenario.due(g, ev):
        if not ev["flags"] & 0x40 or ev["flags"] & 0x80:
            return
        warn = True
        ev["flags"] |= 0x80
    else:
        ev["flags"] |= 4
    i = ev.get("item", -1)
    if not 0 <= i < 14:
        scenario.log(g, f"event #{ev['id']}: no god")
        return
    base = INVADES[i]
    if warn:
        _post(g, base, base + 1)
        return
    from . import figures
    if figures.figure(g, i) is not None:
        scenario.log(g, f"event #{ev['id']}: {GODS[i]} is already on the map")
        return
    at = arrival(g, i)
    if at is None:
        ev["flags"] |= 4
        return
    from .. import alerts                        # alert 11 at the arrival tile (before the spawn)
    alerts.raise_alert(g, alerts.GOD_ATTACK, at)
    w = figures.attack_arrive(g, i, at, scenario_event=True)
    ev["active"] = 0
    _post(g, base, base + 2, i, at)
    log(g, f"{NAMES[i]} invades (scenario event #{ev['id']}) at {at}")
    if w is not None:
        figures.send_defender(g, i, w, at)
    if ev.get("chain", -1) >= 0:
        scenario.chain(g, ev)


def _post(g, title, body, god=-1, at=None):
    """The message; with god: the arrival's voice (event_god_attack: FUN_005A1050(god, 3) after the spawn). at: the
    arrival tile, FUN_00521A70(0xDE, 0, tile) (the go-to button); without one the exe posts 0xE0."""
    from .. import messages
    from . import voice
    meta = dict(at=[at[0], at[1]], kind=0xDE) if at is not None else None
    try:
        messages.post(g, title, body, voice=voice(g, god, 3) if god >= 0 else None, meta=meta)
    except KeyError:                             # phrases not in data/messages.json
        g.message(f"god invasion (phrases {title:#x}/{body:#x})")


def register():
    """Called by sim/scenario's PLUGINS import (track 1G)."""
    from .. import scenario
    scenario.register(27, handler, owner="1H gods")


def debug_invade(g, i):
    """`godattack GOD scenario`: the type-27 arrival now (tests; no event record)."""
    from . import figures
    at = arrival(g, i)
    if at is None:
        return "no arrival tile"
    from .. import alerts
    alerts.raise_alert(g, alerts.GOD_ATTACK, at)
    w = figures.attack_arrive(g, i, at, scenario_event=True)
    _post(g, INVADES[i], INVADES[i] + 2, i, at)
    if w is not None:
        figures.send_defender(g, i, w, at)
    log(g, f"{NAMES[i]} invades (command) at {at}")
    return f"{NAMES[i]} invades at {at}"


__all__ = ["handler", "register", "state"]

register()                                   # imported by sim/scenario's PLUGINS
