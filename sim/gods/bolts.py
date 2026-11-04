"""God bolts as figures (docs/logic/religion.md "Bolts"): created by 0x004D9D70 (a line move from the god to the target
tile, building_id = the god):

  0x2D  a friendly god's bolt (walker_player_missile 0x004BACE0): 4 fine units a call (military defences.Flight), deleted
        past its life (+0x39 from 15, gone past 120: 106 calls) or at once when its god is gone; on each tile (0x004DCE00 -> 0x004DCD30) it hits the first
        non-dying, visible figure of type 0x28..0x2A (invaders), 0x3B (wolf), 0x40, 0x3F (enemy ships; 0x3F unless
        +0x6E == 8), a god of unit class 10 (hostile) or a monster of class 8, and is gone; at the end of its line,
        with no hit, it is deleted.
        A bolt that reaches its end without a hit plays G_miss (FUN_004DC180(god, 13); walkers.sfx "miss").
  0x34  a hostile god's bolt (fig_handler_enemy_missile 0x004BD970, owner type 0x43): life: +0x39 from 15 to 0x79 (105 moves, then counts as arrived); on each
        tile (0x004DCE20 -> 0x004DCE40) it hits the first non-dying figure that is not of type 0, 6, 0x0A, 0x0E, 0x22,
        0x23, 0x28..0x2A, 0x2D, 0x34, 0x3F, 0x40, a god of class 9 (friendly) or a monster of class 7 (good) only;
        at the end of its line: a building on the tile (0x004DCF20) takes wall_damage_add(tile, 10, 100) = destroyed;
        none: the god's building target (+0x5E) is cleared while it is in 0x3B, and G_miss.
The hit is figure_hit(god, victim, 1): a god (type 0x43) against anything but a god, monster or hero has attack 9999
and the victim armour 0 (a sure kill); against those three the model values (sim/military units.hit).
"""
from . import rec



def _W():
    from ..systems import walkers
    return walkers


def shoot(g, god, to, kind=None):
    """0x004D9D70: a bolt from the god's tile to `to`; kind 0x2D (friendly) / 0x34 (hostile, by the god's record). The
    flight is the missiles' (military defences.Flight: 4 fine units a call, the hit test on its tile after each)."""
    from ..military.defences import launch
    W = _W()
    if kind is None:
        kind = 0x34 if god.__dict__.get("uclass", 9) == 10 or god.task == "attack" else 0x2D
    b = W.new_walker(g, role="god_bolt", home=0, x=god.x, y=god.y, good=f"bolt{god.god}")
    launch(g, god, tuple(to), b)
    b.kind, b.god = kind, god.god
    W.add(g, b, 1)
    god.bolt = b.id
    return b


def alive(g, god):
    """god_missile_alive 0x004ED790: the god's last bolt is still flying."""
    b = g.walkers.get(god.__dict__.get("bolt", 0) or 0)
    return b is not None and b.role == "god_bolt" and b.shooter == god.id


def hit(g, god, f):
    """figure_hit(god, victim, 1)."""
    from ..military import units
    if f.role in ("god", "hero", "monster"):
        return units.hit(g, god, f, missile=True)      # a god that survives it: G_<god>_hit (units.hit)
    if f.role in ("trireme", "boat", "ship", "enemy_warship", "enemy_transport"):
        from ..military import navy
        try:
            return navy.hit(g, god, f)
        except Exception:                        # noqa: BLE001  (navy's own model; a sure kill otherwise)
            pass
    units.kill(g, f, god)
    return True


def act(g, b):
    """walker_player_missile 0x004BACE0 (0x2D: its god gone -> deleted at once) / fig_handler_enemy_missile 0x004BD970
    (0x34: flies on without its god; figure_delete zeroes the record, so a hit then does nothing to the victim and the
    line's end has no owner type 0x43: no building hit, no G_miss). A victim on its tile after the move: hit, gone.
    None: at the line's end (or 0x34 past its life) _end; 0x2D past its life: gone without a sound."""
    from ..military.defences import fly
    W = _W()
    god = g.walkers.get(b.shooter)
    if god is not None and god.role != "god":
        god = None
    if b.kind == 0x2D and god is None:
        return W.remove(g, b)
    f, arrived, expired = fly(g, b, b.kind)
    if f is not None:
        if god is not None:
            hit(g, god, f)
        return W.remove(g, b)
    if arrived:
        return _end(g, b, god)
    if expired:
        return W.remove(g, b)
    W.schedule(g, b, 1)


def _end(g, b, god):
    """The end of the line: a hostile bolt destroys the building there (wall_damage_add(tile, 10, 100))."""
    W = _W()
    if b.kind == 0x34 and god is not None:
        bid = int(g.world.occ[b.y, b.x])
        bb = g.buildings.get(bid)
        if bb is not None:
            from .attack import destroyed_by_attack
            destroyed_by_attack(g, bb, god)
        else:
            if getattr(god, "phase", "") == "A":
                god.target = 0
            W.sfx(g, b, "miss")                  # FUN_004DC180(god, 13): G_miss
    elif god is not None:
        W.sfx(g, b, "miss")                      # walker_player_missile: no figure hit -> G_miss
    return W.remove(g, b)


def look(g, b):
    """Play mode: ["arrow", t0, end, .., "god_bolt", false, [src x, y, aim x, y, height 0, god, dir32]] (scene.js
    drawArrow: the god's bolt picture, gods.js Gods.bolt; dir32 = +0x11, defences.launch)."""
    return ["arrow", b.t0, b.t0 + 106, 0, 0, 0, 0, 0, "god_bolt", False,
            [b.src[0], b.src[1], b.aim[0], b.aim[1], 0, b.god, getattr(b, "dir32", 0)]]


__all__ = ["shoot", "act", "alive", "rec"]
