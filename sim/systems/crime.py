"""Criminals (docs/logic/services.md §6). Daily, every inhabited common house checks, in order,
unrest >= 100 vandal, >= 90 thief, >= 80 mugger, >= 70 disgruntled: with chance 1/200 it sends
that criminal out (one per house at a time).
- thief: walks to an elite house holding goods, steals a quarter of each good and is gone; with
  no target it just disappears;
- vandal: walks to an elite house, stays 51 ticks, destroys it; with no target it turns mugger;
- mugger: roams; a walker it meets dies with chance 1/4 (watchmen are immune);
- disgruntled: roams, no effect.
Melee (services.md §6.1): a criminal sharing a tile with a watchman, hunter or woodcutter fights it:
both stand still, the criminal dies after 2 hits by a watchman (48 ticks; disgruntled 3, 72), lies
dying for 128 ticks and is removed; the defender takes no damage and walks on. No arrests. Muggers and
disgruntled roam 0x900/0xF00 of a superintendent's budget, then walk home and vanish.
"""
from . import walkers, roads, index

CRIMINALS = [(100, "vandal"), (90, "thief"), (80, "mugger"), (70, "disgruntled")]
DEFENDERS = ("watchman", "hunter", "woodcutter")
ROLES = {r for _, r in CRIMINALS}
STEAL = ("horses", "armor", "wine", "olive_oil", "fleece")


def spawn(g):
    for b in list(index.of(g, "house")):
        if b.kind != "house" or not b.occupants or b.level >= 7 or b.access is None:
            continue
        for th, role in CRIMINALS:
            if b.crime >= th and g.rng.randrange(200) == 127:
                if any(w in g.walkers and g.walkers[w].role in ROLES for w in b.walkers):
                    break
                w = walkers.spawn_roamer(g, b, role)   # (thief/vandal: no roam, they route to their target)
                g.sd("criminals", set()).add(w.id)
                if role in ("thief", "vandal"):
                    _target(g, w, b)
                    if w.id not in g.walkers:
                        break
                g.message(f"a {role} came out of the house at ({b.x},{b.y})")
                break


def _elite_targets(g, role):
    for h in index.of(g, "house"):
        if h.kind == "house" and h.level >= 7 and h.access is not None:
            if role == "vandal" or any(h.goods.get(k, 0) > 0 for k in STEAL + tuple(g.cat.foods)):
                yield h


def _target(g, w, home):
    t, p = roads.nearest(g, home.access, list(_elite_targets(g, w.role)))
    if t is None:
        # no target: removed (0x005C0030 / 0x005C02C0); only the vandal path frees the house's walker slot
        # (+0x2A) first, so the house's mugger comes out in its place (a fresh mugger, full roam)
        role = w.role
        walkers.remove(g, w)
        if role == "vandal":
            m = walkers.spawn_roamer(g, home, "mugger")
            g.sd("criminals", set()).add(m.id)
        return
    w.target, w.path = t.id, p


def arrive(g, w):
    """Thief/vandal at the elite house."""
    h = g.buildings.get(w.target)
    if h is not None and w.role == "thief":
        stolen = {}
        for k in STEAL:
            n = h.goods.get(k, 0) // 4
            if n:
                h.goods[k] -= n
                stolen[k] = n
        food = [k for k in g.cat.foods if h.goods.get(k, 0)]
        for k in food:
            n = h.goods[k] // 4
            h.goods[k] -= n
            stolen[k] = stolen.get(k, 0) + n
        g.message(f"a thief robbed the villa at ({h.x},{h.y}): {stolen}")
        g.city.thefts = getattr(g.city, "thefts", 0) + 1
    elif h is not None and w.role == "vandal":
        if w.state != "vandalizing":
            w.state = "vandalizing"
            return walkers.schedule(g, w, 51)
        g.message(f"a vandal destroyed the villa at ({h.x},{h.y})")
        g.city.vandalisms = getattr(g.city, "vandalisms", 0) + 1
        from . import risk
        risk.collapse(g, h)
    walkers.remove(g, w)


def mug(g, w):
    """Mugger on a tile: another walker there dies with chance 1/4 (not watchmen, criminals,
    animals); otherwise a defender (hunter, woodcutter) fights it."""
    for o in list(g.walkers.values()):
        if o is w or (o.x, o.y) != (w.x, w.y) or o.role in ROLES or o.role in walkers.ANIMALS or o.anim:
            continue
        if o.role != "watchman" and g.rng.randrange(4) == 0:
            if o.role == "immigrant":
                h = g.buildings.get(o.home)
                if h:
                    h.pending -= o.amount
            g.message(f"a mugger killed a {o.role} at ({w.x},{w.y})")
            walkers.remove(g, o)
            g.city.muggings = getattr(g.city, "muggings", 0) + 1
            return True
    return False


HP = {"disgruntled": 12, "thief": 10, "mugger": 10, "vandal": 10}     # model figures col 1 (Normal)
ATTACK = {"watchman": 6, "hunter": 3, "woodcutter": 4}                  # col 2; criminals attack 0
HIT_EVERY = 24          # figure_fight_tick 0x004D5F10: a hit when attack_timer > 23
DYING = 128             # figure_dying_tick 0x004D60B0: timer +1 per tick, removed past 127


def _face(a, b):
    """Facing of a toward b as the exe's fight_direction (figure_fight_start 0x004D4BA0): from a's
    previous tile to b's previous tile (both stand on the same tile), else a's own heading."""
    pa, pb = a.prev or (a.x, a.y), b.prev or (b.x, b.y)
    dx, dy = (pb[0] > pa[0]) - (pb[0] < pa[0]), (pb[1] > pa[1]) - (pb[1] < pa[1])
    if not (dx or dy):
        dx, dy = (a.x > pa[0]) - (a.x < pa[0]), (a.y > pa[1]) - (a.y < pa[1])
    return (dx, dy)


def fighting(w):
    return w.anim in ("fight", "die")


def melee(g, w):
    """A criminal and a defender on the same tile fight (services.md §6.1): both stop and face each
    other; the defender hits every 24 ticks for its attack (criminals have armor 0) and the criminal
    dies at the first hit taking its damage past its hp (watchman: 2 hits = 48 ticks, disgruntled 3);
    the criminal's own hits do 0. The dead criminal lies dying for 128 ticks, then is removed; the
    defender walks on the tick after the kill. A defender fights at most 2 criminals at once, the
    second after the first. w is the walker that just stepped onto the tile (the mover)."""
    crim = getattr(g, "criminals", None)
    if not crim or fighting(w):
        return False
    crim &= set(g.walkers)
    here = (w.x, w.y)
    if w.role in ROLES:
        foes = [o for o in g.walkers.values() if o.role in DEFENDERS and (o.x, o.y) == here
                and _foes_of(g, o) < 2 and o.anim != "die"]
        pairs = [(w, foes[0])] if foes else []
    else:
        pairs = [(g.walkers[c], w) for c in sorted(crim) if (g.walkers[c].x, g.walkers[c].y) == here
                 and not fighting(g.walkers[c])][:1]
        if pairs and _foes_of(g, w) >= 2:
            pairs = []
    for c, d in pairs:
        now = g.tick
        hits = HP.get(c.role, 10) // ATTACK.get(d.role, 6) + 1          # dmg > hp kills
        start = max(now, d.busy_until - 1) if d.anim == "fight" else now  # queued behind the first foe
        death = start + hits * HIT_EVERY
        c.anim, c.anim_t0, c.busy_until, c.foe, c.hits_t0 = "fight", now, death, d.id, start
        c.face, c.mover = _face(c, d), c is w
        from ..military import units
        c.close_p = units.progress(g, c, now, c is w)          # the tile progress (units.resume_ticks after it)
        if d.anim != "fight":
            d.close_p = units.progress(g, d, now, d is w)
            d.anim, d.anim_t0, d.face = "fight", now, _face(d, c)
        d.foe, d.busy_until, d.mover = c.id, death + 1, d is w
        walkers.schedule(g, c, death - now)
        walkers.schedule(g, d, death + 1 - now)
        return True
    return False


def _foes_of(g, d):
    if d.anim != "fight":
        return 0
    return sum(1 for o in g.walkers.values() if o.foe == d.id and o.anim == "fight" and o.role in ROLES)


def fight_over(g, w):
    """w's fight time is up (walkers.act): a criminal dies, a defender walks on. True = w's turn is
    used (dying)."""
    from ..military import units
    r = units.resume_ticks(g, w) if w.anim == "fight" else None   # fight_end keeps the tile progress: the next tile
    if w.role in ROLES and w.anim == "fight":                     # change comes after the sub-steps left to count 8
        d = g.walkers.get(w.foe)
        if d is None:                       # the defender vanished: the criminal goes on (fight_end)
            w.anim, w.foe = "", 0
            return _resume(g, w, r)
        w.anim, w.anim_t0 = "die", g.tick
        g.message(f"a {d.role} killed a {w.role} at ({w.x},{w.y})")
        walkers.schedule(g, w, DYING)
        return True
    w.anim, w.foe, w.face = "", 0, None
    return _resume(g, w, r)


def _resume(g, w, r):
    """After fight_end a walking figure's first step waits for its tile progress (units.resume_ticks); True = its turn
    is used (scheduled for that step)."""
    if r is not None and (w.path or getattr(w, "roam_left", 0) > 0):
        walkers.schedule(g, w, r)            # this act is the fight's end tick e: figure_move from e + 1, the step at e + r
        return True
    return False
