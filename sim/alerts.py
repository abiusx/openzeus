"""The control panel's alert slots: the four "go to" buttons left of the messages button (docs/play/alerts.md).

Exe: 4 records of 0x70 bytes at 0x00665E48 (saved, block 132, but cleared after a load: FUN_0040FFD0):
+0 slot, +4 alert type (-1 none), +8/+0xC/+0x10 year / month / day of the raise, +0x14 20 tiles, +0x64 their count,
+0x68 the next one to visit, +0x6C "all visited". Each slot takes a range of types (FUN_00410190):
slot 0 = 0..6, 1 = 7..8, 2 = 9..11, 3 = 12..14; a new alert of the slot's range replaces the old one.

- raise_alert  FUN_00410030 (also FUN_00410070 by x, y; FUN_00521A70's last argument when not -1): the slot of
               the type's range gets the type, today's date, the one tile, next 0, not visited; it becomes the
               last raised slot (0x005E8FD4).
- add          FUN_004100C0: one more tile in the type's slot (at most 20; the type is not checked).
- set_first    FUN_0040FF80(5, 0, tile): the last raised slot's first tile (only when that slot is > 0).
- go           FUN_00410290 (the button, 0x00405BA0): the next tile (the view is centred on it when it is on the map,
               FUN_0044A7D0), next + 1; after the last one the slot is "all visited".
- expire       FUN_004102F0 (every frame through FUN_00517CD0 -> FUN_00410000 -> FUN_00410230): a slot clears
               when all visited and its button not pressed, or when more than 8 days old and its button not hovered
               (the widget's hover byte, 0x0063DF9A + 0x28 slot). Ours: all visited clears at once (the client
               keeps the pressed look a moment), the age every day (run_day) unless the client said the mouse rests
               on that button (`alert hover K`).

Types (balloon 68:178 + type, picture SPR_BTN_ALERTS_* by the table 0x005D83CC): see NAMES. The raisers in the exe
and in ours: docs/play/alerts.md. The sim never reads the slots; play mode draws them (frame "alerts").
"""

RANGES = ((0, 6), (7, 8), (9, 11), (12, 14))
NAMES = ("fire", "earthquake", "tidal wave", "landslide", "lava flow", "collapsed building", "blocked road",
         "disease", "plague", "invasion", "monster attack", "god's appearance", "god", "hero", "soldiers")
MAX_TILES = 20
OLD_DAYS = 8

FIRE, EARTHQUAKE, TIDAL_WAVE, LANDSLIDE, LAVA, COLLAPSE, BLOCKED, DISEASE, PLAGUE, INVASION, MONSTER, GOD_ATTACK, \
    GOD, HERO, SOLDIERS = range(15)


def _empty():
    return dict(type=-1, day=0, tiles=[], next=0, visited=False)


def state(g):
    st = g.__dict__.get("alerts")
    if st is None:
        st = g.__dict__["alerts"] = dict(slots=[_empty() for _ in RANGES], last=0, hover=-1, serial=0)
    return st


def reset(g):
    """FUN_0040FFB0 / FUN_0040FFD0: a new game or a loaded save starts without alerts. Ours: the live server's loads
    (start from a save, File > Load); not Game.load itself, so `python3 -m sim do` calls and run checkpoints go on
    with the slots they had."""
    g.__dict__.pop("alerts", None)


def slot_of(t):
    return next((k for k, (lo, hi) in enumerate(RANGES) if lo <= t <= hi), None)


def _tile(at):
    return (int(at[0]), int(at[1])) if at is not None else None


class dated:
    """The exe's date while a part of run_day raises alerts, when it is not g.day: the month's events run in
    month_advance's month-end block with day_of_month held at 15 (invasions_month_update, scenario_events_monthly:
    the old month), and the building steps of the day cycle (buildings_fire_collapse_risk) run during the day that
    run_day closes; both = g.day - 1. Oracle 1B-inv-land / 1I-hero / 1I-quest: raised (m, 15), cleared on day 9
    after; 1H-god (gods_month_update, after day_of_month++): the new day."""
    def __init__(self, g, day):
        self.g, self.day = g, day

    def __enter__(self):
        self.g.__dict__["_alert_day"] = self.day

    def __exit__(self, *exc):
        self.g.__dict__.pop("_alert_day", None)


def raise_alert(g, t, at):
    """FUN_00410030: alert type t at tile at ((x, y) raw, or None: an alert without a place, e.g. a god's help
    message when the god has no figure)."""
    k = slot_of(t)
    if k is None:
        return None
    st = state(g)
    st["serial"] += 1
    day = g.__dict__.get("_alert_day", g.day)
    st["slots"][k] = dict(type=t, day=day, tiles=[_tile(at)], next=0, visited=False, serial=st["serial"])
    st["last"] = k
    return k


def add(g, t, at):
    """FUN_004100C0: another tile for the slot of t's range (plague: every infected house after the first)."""
    k = slot_of(t)
    if k is None:
        return
    s = state(g)["slots"][k]
    if len(s["tiles"]) < MAX_TILES:
        s["tiles"].append(_tile(at))


def set_first(g, at):
    """FUN_0040FF80(5, 0, tile): the last raised slot's first tile (Hephaestus' help: his Talos)."""
    st = state(g)
    k = st["last"]
    if k > 0 and st["slots"][k]["tiles"]:
        st["slots"][k]["tiles"][0] = _tile(at)


def go(g, k):
    """FUN_00410290: the button of slot k -> the tile to centre the view on (None: none, or not on the map)."""
    s = state(g)["slots"][k]
    if s["type"] < 0:
        return None
    at = None
    if len(s["tiles"]) > MAX_TILES - 1:    # sic: a count outside 0..19 counts as none (20 plague houses)
        s["visited"] = True
    elif s["next"] < len(s["tiles"]):
        at = s["tiles"][s["next"]]
        s["next"] += 1
        if s["next"] >= len(s["tiles"]):
            s["visited"] = True
    else:
        s["visited"] = True
    if s["visited"]:                       # FUN_004102F0: all visited and the button let go -> cleared
        state(g)["slots"][k] = _empty()
    if at is not None and not g.world.inside(*at):
        return None                        # 0 < tile < 0xCB10
    return at


def day(g):
    """FUN_004102F0's age rule, once a day: more than 8 days old and not hovered -> cleared."""
    st = g.__dict__.get("alerts")
    if not st:
        return
    for k, s in enumerate(st["slots"]):
        if s["type"] >= 0 and k != st["hover"] and g.day - s["day"] > OLD_DAYS:
            st["slots"][k] = _empty()


def export(g):
    """The frame's "alerts": per slot 0 (none) or [type, next, [[x, y] | None ...], serial]."""
    st = g.__dict__.get("alerts")
    if not st:
        return [0, 0, 0, 0]
    return [[s["type"], s["next"], [list(t) if t else None for t in s["tiles"]], s.get("serial", 0)]
            if s["type"] >= 0 else 0 for s in st["slots"]]


def command(g, op, a):
    """alert                       the slots
       alert go K                  the button of slot K (0..3): the tile it goes to
       alert hover K|-1            the mouse rests on slot K's button (keeps it past 8 days) / on none
       alert raise TYPE X Y        test: raise an alert"""
    if op != "alert":
        return None
    if not a:
        rows = [f"{k}: " + (f"{NAMES[s['type']]} ({s['type']}) day {s['day']}, tiles {s['tiles']}, next {s['next']}"
                            if s["type"] >= 0 else "-") for k, s in enumerate(state(g)["slots"])]
        return "; ".join(rows)
    if a[0] == "go":
        k = int(a[1])
        if not 0 <= k < 4:
            raise ValueError("usage: alert go 0..3")
        at = go(g, k)
        return f"go to ({at[0]},{at[1]})" if at else "nothing to go to"
    if a[0] == "hover":
        k = int(a[1])
        state(g)["hover"] = k if 0 <= k < 4 else -1
        return f"hover {state(g)['hover']}"
    if a[0] == "raise":
        t = int(a[1])
        if slot_of(t) is None:
            raise ValueError("usage: alert raise TYPE(0..14) X Y")
        k = raise_alert(g, t, (int(a[2]), int(a[3])) if len(a) > 3 else None)
        return f"slot {k}: {NAMES[t]}"
    raise ValueError("usage: alert [go K | hover K | raise TYPE X Y]")
