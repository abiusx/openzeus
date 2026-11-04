"""Callbacks from the fight engine (units.py) to the module that owns a walker."""


def _owner(w):
    from . import wolves, forces, invaders, defences
    if w.role in ("monster", "hero"):          # sim/heroes (monsters, heroes) use this fight engine
        from .. import heroes
        return heroes
    if w.role == "wolf":
        return wolves
    if w.role in ("rabble", "hoplite", "horseman"):
        return forces
    if w.role in invaders.TYPES:
        return invaders
    if w.role in ("tower_sentry", "wall_sentry"):
        return defences
    return None


def died(g, w, by):
    """w just fell (action 4)."""
    m = _owner(w)
    if m is not None and m.__name__.rsplit(".", 1)[-1] in ("forces", "invaders", "wolves"):
        from . import morale                 # formation_member_lost 0x004DDFF0 runs formations_refresh first
        morale.refresh(g)
    if m is not None and hasattr(m, "died"):
        m.died(g, w, by)
    elif by is not None and w.role not in ("boar", "sheep", "goat", "cattle", "deer"):
        g.message(f"{an(by.role)} killed {an(w.role)} at ({w.x},{w.y})")       # ours: the exe logs no message
    if by is not None and by.role == "monster":     # monster_hit_victim 0x00532CF0: devoured / petrified (sim/heroes)
        from .. import heroes
        heroes.victim(g, w, by)


def gone(g, w):
    """w's body is removed (127 ticks after its death)."""
    from . import contact
    contact.untrack(g, w)


def fight_over(g, w):
    m = _owner(w)
    if m is not None:
        return m.fight_over(g, w)
    from ..systems import walkers
    w.mil = False                       # a core walker walks on (its own handler again)
    walkers.schedule(g, w, 1)


def an(role):
    r = role.replace("_", " ")
    return ("an " if r[:1] in "aeiou" else "a ") + r


def fight_started(g, w):
    """w just entered action 5 (figure_fight_start): its module's own reset (an archer's shot loses its arrow)."""
    m = _owner(w)
    if m is not None and hasattr(m, "fight_started"):
        m.fight_started(g, w)


def melee_wake(g, w):
    """An earlier tick than the next hit at which w's module needs its fight tick (None: the hit only)."""
    m = _owner(w)
    if m is not None and hasattr(m, "melee_wake"):
        return m.melee_wake(g, w)
    return None


def melee_tail(g, w):
    """The handler's own action-5 rule after figure_fight_tick; True when it took w out of the fight."""
    m = _owner(w)
    if m is not None and hasattr(m, "melee_tail"):
        return m.melee_tail(g, w)
    return False
