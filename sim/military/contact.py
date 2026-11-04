"""Tile contact (figure_tile_contact 0x004D4DA0): when a figure enters a tile it fights the first figure there
that its class is hostile to (g_hostility 0x00639430, units.HOSTILE), which is alive, visible, not dying and has
fewer than 2 opponents. Either side may be the mover: a wolf walking onto a sheep, or a hunter onto a wolf.

Finding figures on a tile without scanning every walker:
- combat units (ROLES) are tracked by tile here (track / tiles), updated as they step;
- other fighters (hunters, watchmen, woodcutters, criminals, animals) come from a list in id order, rebuilt once a
  day and extended by the walkers created since (fighters());
- helpless walkers (immigrants, carts, service walkers) only matter to invaders: a per-tick tile index is built
  while invaders are on the map.
"""
from . import cache, ROLES, units
from ..systems import walkers


def tiles(g):
    """{tile: set(walker ids)} of the combat units (rebuilt from the walkers after a load)."""
    c = cache(g)
    t = c.get("mtiles")
    if t is None:
        t = c["mtiles"] = {}
        for w in g.walkers.values():
            if w.role in ROLES:
                t.setdefault((w.x, w.y), set()).add(w.id)
    return t


def track(g, w, old):
    t = tiles(g)
    s = t.get(old)
    if s is not None:
        s.discard(w.id)
        if not s:
            del t[old]
    t.setdefault((w.x, w.y), set()).add(w.id)


def untrack(g, w):
    s = tiles(g).get((w.x, w.y))
    if s is not None:
        s.discard(w.id)


def fighters(g):
    """Ids of non-helpless core walkers (classes 2, 4, 5, 6 outside ROLES): rebuilt daily, and walkers created since
    (ids from the last seen next_wid on) are added when asked. It used to miss a walker spawned since the list was
    made until the next day, so a game loaded mid-day (a new list) played differently from one run on (bugs.md 315)."""
    c = cache(g)
    day = g.tick // 51
    f = c.get("fighters")
    ok = lambda w: w.role not in ROLES and units.CLASS.get(w.role, 1) != 1
    if f is None or f[0] != day:
        f = c["fighters"] = [day, g.next_wid, sorted(w.id for w in g.walkers.values() if ok(w))]
    elif f[1] != g.next_wid:
        ws = g.walkers
        f[2].extend(i for i in range(f[1], g.next_wid) if i in ws and ok(ws[i]))
        f[1] = g.next_wid
    return f[2]


def everyone_at(g):
    """{tile: [walkers]} as they stand now: rebuilt when a figure has stepped or been created since (g._moves, walkers.step_to / add: the
    exe's searches read the current tile lists, so a figure that moved earlier in this tick's pass is seen there)."""
    c = cache(g)
    f = c.get("tidx")
    key = (g.tick, g.__dict__.get("_moves", 0))
    if f is None or f[0] != key:
        idx = {}
        for w in g.walkers.values():
            idx.setdefault((w.x, w.y), []).append(w)
        f = c["tidx"] = (key, idx)
    return f[1]


order = walkers.tile_order      # the exe's tile-list order (walkers.listed)


def at(g, tile, with_helpless=False):
    if with_helpless:                    # every figure there now (a per-tick snapshot missed those that moved since)
        return sorted((w for w in g.walkers.values() if w.x == tile[0] and w.y == tile[1]), key=order)
    out = [g.walkers[i] for i in tiles(g).get(tile, ())
           if i in g.walkers and (g.walkers[i].x, g.walkers[i].y) == tile]
    for i in fighters(g):
        w = g.walkers.get(i)
        if w is not None and (w.x, w.y) == tile:
            out.append(w)
    out.sort(key=order)
    return out


def on_enter(g, w):
    """w just stepped onto its tile. True when a fight started (w now stands)."""
    if w.anim:
        return False
    here = (w.x, w.y)
    row = units.HOSTILE[units.unit_class(w)]
    if not any(row):
        return False
    others = at(g, here, with_helpless=bool(row[1]))
    if others and god_monster_off(g, w, others[0]):
        return False
    for o in others:
        if o is not w and not getattr(o, "hidden", False):
            if god_monster_off(g, w, o):
                return False
            if w.role == "god" and o.role == "god":     # 0x43 with 0x43: never a tile fight (gods duel: 0x3C)
                continue
        if o.role in SHIP_ROLES and o is not w:     # the generic loop skips 0x19, 0x39, 0x3F, 0x40: only a monster
            if ship_target(w, o) and units.alive(o):   # meets the ship it targets
                units.start_fight(g, w, o)
                return True
            continue
        if o is w or o.anim:
            if o is not w and o.anim == "fight" and row[units.unit_class(o)] and units.can_engage(g, o):
                units.start_fight(g, w, o)
                return True
            continue
        if row[units.unit_class(o)] and units.can_engage(g, o):
            units.start_fight(g, w, o)
            return True
    return False


SHIP_ROLES = ("boat", "trireme", "enemy_warship", "enemy_transport")      # figure types 0x19, 0x39, 0x3F, 0x40


def apollo_fights(g, god):
    """FUN_004D4910: the god is Apollo (record byte 0x00DBD793 = resource 3) of class 9 (friendly) with his sanctuary placed
    (god_sanctuary_building 0x004E8BF0 > 0) and active (god_sanctuary_active 0x004E9440)."""
    if units.unit_class(god) != 9 or getattr(god, "god", -1) != 3:
        return False
    from .. import gods
    return gods.active(g, 3)


def god_monster_off(g, w, o):
    """figure_tile_contact 0x004D4DA0: a god (0x43) and a monster (0x44) meeting -- either the mover -- end the whole
    contact unless the god passes FUN_004D4910 (active Apollo). So Ares, Artemis or any other visiting god never
    fights a monster on a tile (bug 439: Ares and Artemis beat Talos to death in ours)."""
    if w.role == "god" and o.role == "monster":
        return not apollo_fights(g, w)
    if w.role == "monster" and o.role == "god":
        return not apollo_fights(g, o)
    return False


def ship_target(w, o):
    """figure_tile_contact's monster rule: a bad monster (class 8) fights a fishing boat (0x19) / trireme (0x39), a good
    one (class 7) an enemy transport (0x3F) / warship (0x40), only when it is the monster's target (+0x82)."""
    if w.role != "monster" or getattr(w, "tf", 0) != o.id:
        return False
    c = units.unit_class(w)
    return (c == 8 and o.role in ("boat", "trireme")) or (c == 7 and o.role in ("enemy_transport", "enemy_warship"))


def figure_contact(g, w, first):
    """figure_tile_contact 0x004D4DA0 (w, first): w meets the figures on first's tile, from first on in tile order --
    a hidden / fighting / dying w or a dying first: nothing; ships only as ship_target; the first hostile one alive
    with fewer than 2 opponents is fought. True when a fight started."""
    if w.anim or getattr(w, "hidden", False) or first is None or not units.alive(first):
        return False
    row = units.HOSTILE[units.unit_class(w)]
    if not any(row) and w.role != "monster":
        return False
    if god_monster_off(g, w, first):
        return False
    others = at(g, (first.x, first.y), with_helpless=True)
    if first in others:
        others = others[others.index(first):]
    for o in others:
        if o is w or getattr(o, "hidden", False):
            continue
        if god_monster_off(g, w, o):
            return False
        if w.role == "god" and o.role == "god":
            continue
        if o.role in SHIP_ROLES:
            if ship_target(w, o) and units.alive(o):
                units.start_fight(g, w, o)
                return True
            continue
        if row[units.unit_class(o)] and units.can_engage(g, o):
            units.start_fight(g, w, o)
            return True
    return False


def core_entered(g, w):
    """walkers.step_to hook for core walkers: only tiles with a combat unit matter."""
    t = tiles(g)
    if (w.x, w.y) not in t or w.role in ROLES or w.anim:
        return False
    return on_enter(g, w)
