"""Peace and war counters, the military-service sentiment, auto-defend (docs/logic/military.md "Counters",
"Auto-defend"; sentiment.md 6).

month_advance 0x00483C10 at day_of_month 0 (before the sentiment update of that day):
- g_months_since_enemy 0x00FE9578: +1 when no invader and no enemy warship is alive, else 0 (each spawned enemy
  company also resets it, enemy_army_spawn_land 0x00504650);
- g_months_to_next_invasion 0x00FE957C: the least event_months_until_due 0x00472000 over pending invasions
  (1000000 if none). The exe tests auto-defend with last month's value and then stores the new one; ours computes
  the new value first and tests it, which fires in the same month (one month before the army arrives, when the
  "next month" warning is posted) because our invasion arrives when the months left reach 0;
- auto-defend (option 0x00F2A990): next invasion 1 month away -> auto_defend_mobilize 0x00568D20; else, one month
  after the last enemy (months_since_enemy == 1) and when it had mobilized (0x00FEB4F9) -> auto_defend_dismiss
  0x00569010.
sentiment_from_military 0x00566E70: mobilized palace companies, only in peace (2 months since the last enemy, the
next invasion 2+ months away, no enemy alive): 0 -> 0, 1..2 -> -1, 3..5 -> -2, 6..8 -> -3, 9..12 -> -4, else -5.
"""
from ..systems import labor, walkers
from . import state, on

NONE = 1000000


def months_since_enemy(g):
    return state(g).get("months_since_enemy", 0)


def months_to_next(g):
    return state(g).get("months_to_next", NONE)


def warships(g):
    return sum(1 for w in g.walkers.values() if w.role == "enemy_warship" and w.anim != "die")


def enemy_present(g):
    from . import enemies_alive
    return enemies_alive(g) or warships(g) > 0


def next_invasion(g):
    """(months, land point index 1..8 or sea 9..16, landing point index) of the soonest pending invasion, from the
    empire module."""
    from .. import empire
    f = getattr(empire, "next_invasion", None)
    r = tuple(f(g)) if f is not None and empire.get(g) is not None else (NONE, 8, 0)
    return r + (0,) * (3 - len(r))


def month(g):
    """Day 0 of a month: the counters, then auto-defend."""
    st = state(g)
    st["months_since_enemy"] = 0 if enemy_present(g) else st.get("months_since_enemy", 0) + 1
    m, pt, landing = next_invasion(g)
    st["months_to_next"], st["next_point"] = m, pt
    if not st.get("auto_defend"):
        return
    if m == 1:
        mobilize(g, pt, landing)
    elif st["months_since_enemy"] == 1 and st.get("auto_active"):
        dismiss(g)


def sentiment(g):
    """sentiment_from_military 0x00566E70 (0 when the module is off)."""
    if not on(g):
        return 0
    from .forces import companies, field
    s = sum(1 for k, c in companies(g).items() if 1 <= k <= 20 and field(c)["mob"])
    if months_since_enemy(g) < 2 or months_to_next(g) < 2 or enemy_present(g):
        return 0
    return 0 if s <= 0 else -1 if s < 3 else -2 if s < 6 else -3 if s < 9 else -4 if s <= 12 else -5


# --- auto-defend -------------------------------------------------------------------------------------------

def rally_point(g, pt, landing=0):
    """The rally point of an invasion point (0x004E29B0 -> 0x004E28D0): the middle tile of the route from the
    point to the palace (FUN_004E2580 walks the route and returns path[len/2]); no route: the palace's road tile.
    A sea invasion (points 9..16) uses the rally point of its landing point (0x00DB6940[landing], the landing tile
    moved to the nearest route tile). Ours: our land path (8-way over walkable land) to the palace's road tile;
    the landing point is the event's +0x78 (city_event_invasion 0x00477830 via FUN_00503EC0)."""
    from .forces import palace
    from .invaders import pick_point
    p = palace(g)
    if p is None:
        return None
    src = None
    if pt > 8:                                    # sea (0x00DB6940): from the landing point, moved by
        from . import navy                        # route_tile_check 0x004D2C60 to the nearest land route tile
        lands = navy.sea_points(g)[1]
        land = lands[landing] if 0 <= landing < len(lands) and lands[landing] else next((x for x in lands if x), None)
        if land:
            src = navy._land_tile(g, land)
    if src is None:
        src = pick_point(g, pt if 1 <= pt <= 8 else 8)
    c = state(g).setdefault("rally", {})
    key = f"{src[0]},{src[1]},{p.id}"
    if key not in c:
        path = walkers.land_path(g, tuple(src), {tuple(p.access)}, walkers.ROUTE_MAX, walkers.walkable(g)) \
            if p.access else None
        c.clear()
        c[key] = list(path[len(path) // 2]) if path else list(p.access or (p.x, p.y))
    return tuple(c[key])


def mobilize(g, pt, landing=0):
    """auto_defend_mobilize 0x00568D20: military labour to priority 5 (the others capped at 4, saved), then up to
    20 companies in the city, ready and not yet selected (sanctuary troops 31..34 first, then horsemen, hoplites,
    rabble), each mobilized in mode 0 and moved (formation_move with spread k) to the rally point."""
    from .forces import companies, field, mobilize as mob
    st = state(g)
    st["auto_active"] = True
    pr = labor.priorities(g)
    if pr[7] != 5:
        st["saved_priorities"] = list(pr)
        for i in range(len(pr)):
            pr[i] = 5 if i == 7 else min(pr[i], 4)
        labor.allocate(g)
    comps = companies(g)
    pick = [s for s in sorted(comps) if 31 <= s <= 34]
    for t in ("horseman", "hoplite", "rabble"):
        pick += [s for s in sorted(comps) if s <= 30 and comps[s]["type"] == t]
    sel = [s for s in pick if not field(comps[s]).get("away") and comps[s]["ready"] and comps[s]["members"] > 0][:20]
    dest = rally_point(g, pt, landing)
    if dest is None:
        return
    for k, s in enumerate(sel):
        c = comps[s]
        c["mode"], c["target"] = 0, 0
        c["mob"] = False                             # formation_move from home with the new mode
        mob(g, s, dest[0], dest[1], k=k)
    if sel:
        g.message(f"Auto-defend: {len(sel)} companies called to arms against the coming invasion.")
    if sel and pt > 8:                            # by sea: every wharf's crew back aboard, its trireme hunts
        from . import navy
        for w in navy.triremes(g):
            navy.init(g, w)
            b = navy.wharf(g, w)
            if b is not None:
                b.misc.pop("off", None)
            if w.away < 0 and w.anim != "die":
                navy.go_hunt(g, w)
                walkers.schedule(g, w, 1)


def dismiss(g):
    """auto_defend_dismiss 0x00569010: the saved labour priorities back (clamped 0..5), every company in the city
    and ready sent home."""
    from .forces import companies, field, send_home
    st = state(g)
    st["auto_active"] = False
    pr = labor.priorities(g)
    saved = st.pop("saved_priorities", None)
    if pr[7] == 5 and saved:
        for i in range(len(pr)):
            pr[i] = max(0, min(5, saved[i]))
        labor.allocate(g)
    for s, c in companies(g).items():
        if field(c)["mob"] and not c.get("away") and c["ready"]:
            send_home(g, s)
    from . import navy                            # triremes at home back to their wharf (0x4D0800)
    for w in navy.triremes(g):
        navy.init(g, w)
        if w.away < 0 and w.anim != "die" and navy.wharf(g, w) is not None:
            navy.return_to_wharf(g, w)
            walkers.schedule(g, w, 1)
