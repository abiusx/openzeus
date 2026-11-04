"""Monsters and heroes in the shared fight engine (sim/military/units.py calls these through units.MYTH).

figure_hit 0x004D54D0 with a monster (float constant 0x005D9358 = 1.5):
- the target is a bad monster (class 8): its armor x1.5 (ftol), its hp 500 x 1.5 = 750;
- the attacker is a bad monster: attack x1.5 (75), x2 again against a trireme;
- missile hitters (rabble 0xB, enemy archer 0x28, tower sentry 0x2E, wall sentry 0x27) do 0 to a bad monster
  (towers shoot at monsters, priority 50, without effect); a good monster (class 7) does 0 to a monster;
- every hit on a monster calls 0x00533FB0: unless it is busy (actions 0, 4, 5, 9, 12, 16, 22, 23, 25..28) a bad
  monster turns on the attacker (flag 0x200, action 9).
figure_can_kill 0x004D53D0 (the damage still adds up when it returns false):
- a god only by a god; a hero by a god, or by a monster that is not his quarry (hero_can_fight 0x004FCD60): he is
  not killed but beaten back to his hall (flag 0x10, action 9; ours: the same, his damage cleared);
- a monster by gods, heroes and monsters; a bad monster also by rabble, hoplites, horsemen, watchmen, wall sentries;
  a good monster by the enemy soldiers (0x28..0x2A).
The horseman charge (0x004E1080) skips both can_kill and the x1.5 (hp 500): sim/military's charge calls hit() like
any other blow, so ours does not have the bypass (noted in docs/logic/heroes-monsters.md "Ours").
"""
from . import data

ROLES = frozenset(("monster", "hero", "god"))
MISSILE = ("rabble", "enemy_archer", "tower_sentry", "wall_sentry")
KILL_BAD = ("rabble", "hoplite", "horseman", "watchman", "wall_sentry")
KILL_GOOD = ("enemy_infantry", "enemy_archer", "enemy_cavalry")
BUSY = (0, 4, 5, 9, 12, 16, 22, 23, 25, 26, 27, 28)


def _cls(w):
    from ..military import units
    return units.unit_class(w)


def adjust(g, att, tgt, A, D):
    if tgt.role == "monster" and _cls(tgt) == 8:
        D = int(D * 1.5)
        if att.role in MISSILE:
            A = 0
    if att.role == "monster":
        if _cls(att) == 7 and tgt.role == "monster":
            A = 0
        elif _cls(att) == 8:
            A = int(A * 1.5)
            if tgt.role == "trireme":
                A *= 2
    return A, D


def hp(g, w, v):
    if w.role == "monster" and _cls(w) == 8:
        return int(v * 1.5)
    return v


def quarry(hero, monster):
    return monster.mid in data()["heroes"][hero.hero]["monsters"]


def can_kill(g, att, tgt):
    if tgt.role == "god":
        return att.role == "god"
    if tgt.role == "hero":
        if att.role == "god":
            return True
        if att.role == "monster" and not quarry(tgt, att):
            beaten(g, tgt)
        return False
    if tgt.role == "monster":
        if att.role in ROLES:
            return True
        return att.role in (KILL_BAD if _cls(tgt) == 8 else KILL_GOOD)
    return True


def beaten(g, w):
    """A hero 'killed' by a monster he can't fight: flag 0x10, back to his hall (hall flags_c4 |= 4)."""
    from ..military import units
    from . import hero_ai
    w.dmg = 0
    if w.anim == "fight":
        units.end_fight(g, w)
    w.act = 12
    w.beaten = True
    hero_ai.walkers.schedule(g, w, 1)


def hit(g, att, tgt):
    """0x00533FB0: a monster turns on whoever hits it, unless busy (a good monster: re-targets, action 15)."""
    if tgt.role != "monster":
        return
    if _cls(tgt) == 7:                           # a good monster: (15, 16) unless busy (guardians.py)
        from . import guardians
        return guardians.hit(g, tgt)
    if tgt.anim == "fight" or getattr(tgt, "act", 7) in BUSY:
        return
    from . import monsters
    tgt.tf = att.id
    tgt.mflags |= 0x200
    monsters.enter(g, tgt, 9)


DUEL = 300               # +0x68 = 300 vs a monster (figure_hero_update 0x004C8F50 head, hero_combat_update 0x004FD2B0)


def duel_pair(w, o):
    """hero_duel_hit 0x004D5BC0's test: a hero fighting a monster he can fight (hero_can_fight 0x004FCD60: one of
    his two quarry ids), or that monster fighting him. (hero, monster) or None."""
    if o is None:
        return None
    if w.role == "hero" and o.role == "monster" and quarry(w, o):
        return w, o
    if w.role == "monster" and o.role == "hero" and quarry(o, w):
        return o, w
    return None


def fight_started(g, w):
    """The hero entered action 5 (figure_fight_start). figure_hero_update's head, every tick of action 5: +0x82 (his
    target) a monster and +0x68 == 0 -> +0x68 = 300 (also set by hero_combat_update right after his own contact);
    hero_duel_hit counts it down by 1 every fight tick vs his quarry, from his first fight tick (anim_t0 + 1), and
    the monster falls on the tick it is <= 1 after the decrement: n = 300 -> anim_t0 + 299. A fight with his quarry
    while +0x82 is 0 (no target): +0x68 stays 0 and the monster falls on his first fight tick. A partial count (a
    duel broken off) is kept in duel_n (+0x68) for the next one."""
    if w.role != "hero":
        return
    o = g.walkers.get(w.foe)
    t = g.walkers.get(getattr(w, "target", 0) or 0)
    n = getattr(w, "duel_n", 0) or 0
    if n == 0 and t is not None and t.role == "monster" and t.anim != "die" and not getattr(t, "hidden", False):
        n = DUEL
    w.duel_n = n
    w.duel_end = w.anim_t0 + 1 + max(0, n - 2) if duel_pair(w, o) else None


def duel_left(g, w):
    """+0x68 after the hero's fight ended at g.tick without the kill: the last decrement was the tick before."""
    end = getattr(w, "duel_end", None)
    if end is None:
        return getattr(w, "duel_n", 0) or 0
    return max(0, end - g.tick + 2)


def melee_wake(g, w):
    if w.role == "hero" and getattr(w, "duel_end", None) is not None:
        return w.duel_end
    return None


def duel_tick(g, w, o):
    """figure_fight_tick 0x004D5F10 -> hero_duel_hit 0x004D5BC0 for a hero and his quarry (either side): it replaces
    figure_hit, so no damage either way; when the attack timer passes 23 the opponent's hit sound (FUN_004DB7A0) and
    the timer 0; the hero's +0x68 counts down and at <= 1 the monster gets flag 0x10 and action 4, the hero's +0x82
    and +0x68 = 0 (his next fight tick sees it fallen: figure_fight_end). False when w and o are no such pair."""
    p = duel_pair(w, o)
    if p is None:
        return False
    from ..military import units
    from ..systems import walkers
    h, m = p
    if g.tick >= w.busy_until:
        walkers.sfx(g, o, "hit")
        w.busy_until = g.tick + units.HIT_EVERY
    if w is h and getattr(h, "duel_end", None) is None:      # a fight that became a duel (the opponent switched)
        h.duel_end = g.tick + max(0, (getattr(h, "duel_n", 0) or 0) - 2)
    if w is h and g.tick >= h.duel_end:
        m.mflags = getattr(m, "mflags", 0) | 0x10
        h.target, h.duel_n, h.duel_end = 0, 0, None
        units.kill(g, m, h)
        return walkers.schedule(g, h, 1)
    return walkers.schedule(g, w, units.wake(g, w) - g.tick)
