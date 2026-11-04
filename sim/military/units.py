"""Fighting figures: model values, hostility, the hit, melee fights and deaths (docs/logic/military.md
"Combat"). Shared by wolves, soldiers, invaders and sentries; works on any walker (a hunter or a sheep a wolf
attacks is one too: while it fights, this module drives it, then hands it back to sim/systems/walkers.py).

Per-walker combat state, kept as plain attributes on the Walker (pickled with it):
  dmg       damage taken (Figure+0x98); death when dmg > hp (figure_hit 0x004D54D0)
  foe       the walker it hits (opponent +0x90); anim "fight" while fighting, "die" while dying
  busy_until  its next hit tick (fight) -- the play client draws the fight until then
  mil       True while this module drives a core walker (fight, dying)
"""
import json
import os

from ..systems import walkers

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data",
                    "military.json")
HIT_EVERY = 24          # figure_fight_tick 0x004D5F10: a hit when the attack timer passes 23
DYING = 128             # figure_dying_tick 0x004D60B0: removed at 127

# unit class (Figure_model col 0): 0 non fighter, 1 helpless, 2 good guy, 3 bad guy, 4 criminal, 5 predator,
# 6 prey, 8 monster, 9 god, 10 hero
CLASS = {"rabble": 2, "hoplite": 2, "horseman": 2, "wall_sentry": 2, "tower_sentry": 2, "watchman": 2,
         "hunter": 2, "woodcutter": 2, "trireme": 2,
         "enemy_infantry": 3, "enemy_archer": 3, "enemy_cavalry": 3, "enemy_warship": 3, "enemy_transport": 3,
         "mugger": 4, "thief": 4, "vandal": 4, "disgruntled": 4,
         "wolf": 5, "sheep": 6, "goat": 6, "cattle": 6, "boar": 6,
         "arrow": 0, "enemy_arrow": 0}        # missiles are not fighters (no tile-contact fights with them)
# g_hostility 0x00639430, 11 x 11 u8: row = the mover's class, column = the other's
HOSTILE = [[0] * 11,
           [0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0],
           [0, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1],
           [0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 0],
           [0, 0, 1, 1, 0, 1, 0, 0, 1, 1, 0],
           [0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0],
           [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
           [0, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1],
           [0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 0],
           [0, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1],
           [0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 0]]
ROLES_OWNED = ("enemy_infantry", "enemy_archer", "enemy_cavalry", "enemy_warship", "enemy_transport", "tower_sentry",
               "wall_sentry", "arrow", "enemy_arrow")
MISSILE_HITTERS = ("rabble", "wall_sentry", "tower_sentry", "enemy_archer")   # figure_hit: 0xB, 0x27, 0x2E, 0x28
ENEMY_CLASS = {"enemy_infantry": "infantry", "enemy_archer": "missile", "enemy_cavalry": "cavalry",
               "enemy_warship": "warship", "enemy_transport": "transport"}      # ships: army 0 (navy.md)

_data = None


def data():
    global _data
    if _data is None:
        with open(DATA) as f:
            _data = json.load(f)
    return _data


def unit_class(w):
    if w.role == "monster":                      # figure_type_value 0x004E1B20: 8 bad monster, 7 good (guardian)
        return getattr(w, "uclass", 8)
    if w.role == "hero":                         # model row 69: good guy
        return 2
    if w.role == "god":                          # 0x004E1B20: 10 for a god whose record is unfriendly, else 9 (sim/gods)
        return getattr(w, "uclass", 9)
    c = CLASS.get(w.role, 1)
    if w.role == "cattle" and getattr(w, "bull", False):
        return 6
    return c


def stats(g, w):
    """The figure's model row (figure_type_value 0x004E1B20) for this difficulty; enemies by their army."""
    d = data()["difficulty"][g.rules.get("difficulty", "Normal")]
    if w.role in ENEMY_CLASS:
        return d["armies"][min(getattr(w, "army", 0), 10)][ENEMY_CLASS[w.role]]
    return d["figures"].get(w.role) or d["figures"]["immigrant"]


ATHENA = ("rabble", "hoplite", "horseman", "hero")           # figure types 0xB, 0xC, 0xD, 0x45


def col(g, w, name):
    v = stats(g, w)[name]
    if name == "missile_armor" and w.role in ATHENA:          # 0x004E1B20: Athena's active sanctuary (god record 8,
        from .. import gods                                    # ecx 0x00EF5F78): cols 4 and 0x12 + 4 (0x12 is never
        if gods.active_now(g, 8):                              # read: missile armour only)
            v += 4
    if name in ("armor", "missile_armor") and v > 18:          # armor cap
        v = 19
    return v


def hostile(a, b):
    return bool(HOSTILE[unit_class(a)][unit_class(b)])


def alive(w):
    return w is not None and w.anim != "die"


def group_mode(g, w):
    """figure_hit's group test: the figure's formation (+0x60) as it is now, its combat mode (+0x91); none for figures
    in no formation or in a herd (+0x69: wolves, boars). The player's soldiers: their company's; invaders (land
    companies, ships): their company's (ours read a soldier's mode as spawned and none for invaders before 11-03:
    oracle 1B-inv-city-horse, Nemea's archers in mode 1 hit the holding horsemen for 4, in mode 2 for 5)."""
    if w.role in ("rabble", "hoplite", "horseman"):
        from .forces import companies
        c = companies(g).get(getattr(w, "comp", 0))
    elif getattr(w, "company", 0):
        from .invaders import ecomps
        c = ecomps(g).get(w.company)
    else:
        return None
    return None if c is None else c.get("mode", 0)


def damage(g, att, tgt, missile=False):
    """figure_hit 0x004D54D0: missile attack vs missile armor for 0xB/0x27/0x28/0x2E (melee too), else attack
    vs armor; group modes x1.5 (combat mode +0x91); dmg = A - D*A/20 (C truncation), never below 0."""
    if att.role == "god" and tgt.role not in ("god", "hero", "monster"):
        return 9999                              # figure_hit case 0x43: attack 9999, armour 0 (a sure kill)
    if att.role in MISSILE_HITTERS:
        A, D = col(g, att, "missile_attack"), col(g, tgt, "missile_armor")
    else:
        A, D = col(g, att, "attack"), col(g, tgt, "armor")
    if att.role == "wolf" and unit_class(tgt) == 6 and tgt.role == "cattle" and getattr(tgt, "bull", False):
        A = D = 0
    ma, mt = group_mode(g, att), group_mode(g, tgt)
    if ma is not None and mt is not None:
        if ma == 1 and mt == 2:
            A = A * 150 // 100
        if ma == 0 and mt == 2:
            D = D * 150 // 100
        if ma == 1 and mt == 0:
            D = D * 150 // 100
    if MYTH is not None and (att.role in MYTH.ROLES or tgt.role in MYTH.ROLES):
        A, D = MYTH.adjust(g, att, tgt, A, D)      # monsters / heroes (sim/heroes: x1.5, missiles 0, duels)
    if A == 0:
        return 0
    return max(0, A - int(D * A / 20))


MYTH = None             # set by sim/heroes: adjust(g, att, tgt, A, D), hp(g, w, hp), can_kill(g, att, tgt), ROLES


def hit(g, att, tgt, missile=False):
    """One hit; True when it kills (damage over the model hp). figure_can_kill 0x004D53D0 (sim/heroes for monsters,
    heroes): the damage still adds up when the attacker may not kill."""
    if not alive(tgt):
        return False
    if tgt.role in ("trireme", "enemy_warship", "enemy_transport"):   # figure_hit: a ship loses hull (+0x128)
        from . import navy
        navy.hit(g, att, tgt)
        return not alive(tgt)
    tgt.dmg = getattr(tgt, "dmg", 0) + damage(g, att, tgt, missile)
    hp = col(g, tgt, "hp")
    myth = MYTH is not None and (att.role in MYTH.ROLES or tgt.role in MYTH.ROLES)
    if myth:
        hp = MYTH.hp(g, tgt, hp)
        MYTH.hit(g, att, tgt)
    if tgt.dmg > hp and (not myth or MYTH.can_kill(g, att, tgt)):
        kill(g, tgt, att)
        return True
    walkers.sfx(g, tgt, "hit")                   # figure_hit -> FUN_004DB7A0(target): its hit sound (a god: G_<god>_hit)
    return False


def kill(g, w, by=None):
    """Action 4: the figure falls (die picture, 128 ticks), then is removed. Its company loses a member."""
    from . import hooks
    fighting(g).discard(w.id)
    w.anim, w.anim_t0, w.busy_until, w.foe, w.mil = "die", g.tick, g.tick + DYING, 0, True
    w.path = []
    walkers.schedule(g, w, DYING)
    wake_attackers(g, w)
    hooks.died(g, w, by)
    _hunted_gone(g, w)


def _face(a, b):
    dx, dy = (b.x > a.x) - (b.x < a.x), (b.y > a.y) - (b.y < a.y)
    if not (dx or dy):
        p = a.prev or (a.x, a.y)
        dx, dy = (a.x > p[0]) - (a.x < p[0]), (a.y > p[1]) - (a.y < p[1])
    return (dx, dy)


def _speed_frac(g, w):
    """Sub-steps per tick (num, den) at the figure's speed code (Figure_model col 8; walkers.SPEED)."""
    code = col(g, w, "speed") if w.role in ENEMY_CLASS or w.role in ("rabble", "hoplite", "horseman", "wolf") \
        else walkers.speed(g, w)
    return walkers.SPEED[max(0, min(18, code))]


def _moving(w):
    if w.role in ENEMY_CLASS:
        return getattr(w, "task", "") in ("march", "hunt", "disengage", "leave", "attack")
    return bool(w.path) or getattr(w, "roam_left", 0) > 0


def progress(g, w, now, mover):
    """The figure's tile progress (+0x39, 0..15) as a fight starts: the mover is at 8 (figure_change_tile calls the
    contact at the tile change, count 8); the other one where its step is: ours' step to (x, y) at `arrived` is that
    figure's count 8, then num/den counts a tick (its speed); a walking one wraps past its tile centre (15 -> 0) toward
    the next tile, a standing one stops at the centre (15). Returns (p, heading dx, dy): the heading is the tile it
    walks to for p < 8, the step it came by for p >= 8."""
    p0 = w.prev or (w.x, w.y)
    back = ((w.x > p0[0]) - (w.x < p0[0]), (w.y > p0[1]) - (w.y < p0[1]))
    a = getattr(w, "arrived", 0) or 0
    if mover and a == now:                         # a contact from a hero / monster standing (FUN_004D5330, the
        return [8, back[0], back[1]]               # neighbour tiles) is not at the tile change
    fp = w.__dict__.get("fprog")                   # invaders and soldiers keep the exe's progress (invaders.imove,
    if fp is not None and (w.role in ENEMY_CLASS or w.role in SOLDIERS) and not w.anim:     # forces.advance)
        if fp >= 15:
            return [15, 0, 0]
        if fp >= 8 or not w.__dict__.get("heading"):
            return [fp, back[0], back[1]]
        h = w.heading
        return [fp, (h[0] > w.x) - (h[0] < w.x), (h[1] > w.y) - (h[1] < w.y)]
    if not w.prev or a <= 0 or a > now or w.anim:
        return [15, 0, 0]
    num, den = _speed_frac(g, w)
    c = (now - a) * num // max(1, den) if num else 0
    if not _moving(w):
        return [min(15, 8 + c), back[0], back[1]]
    p = 8 + c
    if p < 15:
        return [p, back[0], back[1]]
    p = min(14, p - 15)
    if p >= 8:
        return [p, back[0], back[1]]
    nx = w.path[0] if w.path else (w.x + back[0], w.y + back[1])
    return [p, (nx[0] > w.x) - (nx[0] < w.x), (nx[1] > w.y) - (nx[1] < w.y)]


def counter_ref(g, w, now):
    """The anim_frame (+0x01) a figure keeps into a fight it did not start (figure_fight_start resets the mover's only),
    as the tick whose walk frame it equals in play mode (walk frames by the game tick): `now` for a figure whose counter
    runs every tick (walking; rabble: the prologue's +1 a tick; wolves); an invader standing in action 7 keeps the frame
    it stopped on (walk_t; None = 0: never walked, or after a shot's wrap)."""
    if getattr(w, "shot_end", None) is not None:   # an archer in its shot: the shot's counter (look [7] = its start)
        return None
    if w.role in ENEMY_CLASS and getattr(w, "task", "") in ("wait", "attack", "attack7"):
        return getattr(w, "walk_t", None)
    return now


def closed_in(g, w, end=None):
    """figure_fight_tick's closing-in: while its tile progress is below 6 the fighter takes one fine step a tick (+1,
    figure_fine_step) toward 6, from its first fight tick (anim_t0 + 1) on. Returns the counts it moved by `end`."""
    p = (getattr(w, "close_p", None) or [15])[0]
    if p >= 6:
        return 0
    end = g.tick if end is None else end
    return max(0, min(6 - p, end - w.anim_t0))


def fighting(g):
    """Ids of the walkers in a fight (rebuilt from the walkers after a load)."""
    from . import cache
    c = cache(g)
    f = c.get("fighting")
    if f is None:
        f = c["fighting"] = {w.id for w in g.walkers.values() if w.anim == "fight" and w.__dict__.get("mil")}
    return f


def attackers(g, w):
    out = []
    for i in list(fighting(g)):
        o = g.walkers.get(i)
        if o is None or o.anim != "fight":
            fighting(g).discard(i)
        elif o.foe == w.id:
            out.append(o)
    return out


def can_engage(g, b):
    """figure_tile_contact 0x004D4DA0's test on the other figure: alive, visible, not dying, < 2 opponents."""
    if not alive(b) or getattr(b, "hidden", False) or b.state == "held":
        return False
    return len(attackers(g, b)) < 2


def start_fight(g, a, b):
    """figure_fight_start 0x004D4BA0: a fights b; b turns to fight a (if free: else it keeps its own fight and timer
    and only records a). Both stand; attack_timer = 0 (each hits when its timer passes 23: every 24 ticks)."""
    from . import hooks
    now = g.tick
    if a.role == "god":                          # FUN_004DB3D0(a, 0): the mover's attack sound (god: G_<god>_atk1/2)
        walkers.sfx(g, a, "atk")
    for x, y in ((a, b), (b, a)):
        if x.anim == "fight" and x is b:
            continue                       # b is busy with someone else: a still hits it
        x.saved_task = getattr(x, "task", "")
        # attack_timer 0 now. walkers_update runs the figures in slot order: b, if its slot comes after a's, runs its
        # first fight tick (+1) in this same tick, so its timer is one ahead of a's and it hits a tick earlier
        t0 = now - 1 if x is b and not walkers.acted_this_tick(g, b) else now
        x.close_p = progress(g, x, now, x is a)    # tile progress at the start (the closing-in, fight_tick)
        x.ctr_ref = None if x is a else counter_ref(g, x, now)   # fight_start resets anim_frame of the mover only
        x.anim, x.anim_t0, x.foe, x.face = "fight", t0, y.id, _face(x, y)
        x.busy_until = t0 + HIT_EVERY
        x.mover = x is a                   # the look's mover: a's attack sound at the start (FUN_004DB3D0(a, 0))
        x.mil = True
        x.path_saved = list(x.path)
        fighting(g).add(x.id)
        hooks.fight_started(g, x)
        walkers.schedule(g, x, wake(g, x) - now)


def act_core(g, w):
    """A core walker (hunter, sheep, watchman...) while this module drives it: fighting or dying."""
    if w.anim == "die":
        return act_dying(g, w)
    if w.anim == "fight":
        return fight_tick(g, w)
    w.mil = False
    walkers.schedule(g, w, 1)


def in_fight(o):
    """figure_fight_tick's test on the opponent: state 1 and action 5 (fighting anyone)."""
    return o is not None and o.anim == "fight"


def fight_tick(g, w):
    """figure_fight_tick 0x004D5F10, every tick of action 5 in the exe (ours: at the hit ticks and when woken): the
    opponent must still be fighting (state 1, action 5), else the other recorded opponent (count 2 -> 1) if it is,
    else the fight ends (0x004D61B0 restores the saved action). The attack timer (+0x6A) counts on across a switch:
    a hit when it passes 23, then 0. Ours: timer = (tick - anim_t0) % 24, the hit at busy_until."""
    o = g.walkers.get(w.foe)
    if not in_fight(o) or o.id not in g.walkers:
        nxt = [a for a in attackers(g, w) if a is not w and in_fight(a)]
        if not nxt:
            return end_fight(g, w)
        o = nxt[0]
        w.foe, w.face = o.id, _face(w, o)
    if MYTH is not None and w.role in MYTH.ROLES:  # hero_duel_hit 0x004D5BC0 replaces figure_hit for a hero and his
        r = MYTH.duel_tick(g, w, o)                # quarry (sim/heroes/combat.py)
        if r is not False:
            return r
    if g.tick >= w.busy_until:
        hit(g, w, o)
        if w.anim != "fight":
            return None
        w.busy_until = g.tick + HIT_EVERY
        if not in_fight(o):                      # it fell: the next tick switches or ends (count 1 -> fight_end)
            return walkers.schedule(g, w, 1)
    from . import hooks
    if hooks.melee_tail(g, w):                   # the handler's picture tail (cavalry disengage 0x004B9E20)
        return None
    walkers.schedule(g, w, wake(g, w) - g.tick)


def wake(g, w):
    """The next tick this fighter must act: its hit, or earlier for the module's own per-tick rule (hooks.melee_wake)."""
    from . import hooks
    t = w.busy_until
    e = hooks.melee_wake(g, w)
    if e is not None and g.tick < e < t:
        t = e
    return max(g.tick + 1, t)


def wake_attackers(g, w):
    """w left action 5 (died, or its fight ended): whoever fights it sees that on its next fight tick, which is in this
    tick when its slot comes after the one acting now (walkers_update runs every fighter's fight tick every tick, in slot
    order), else the next tick."""
    for i in sorted(fighting(g), key=lambda i: g.walkers[i].fslot if i in g.walkers else 0):
        a = g.walkers.get(i)
        if a is not None and a is not w and a.anim == "fight" and a.foe == w.id:
            walkers.wake_now(g, a)


def end_fight(g, w):
    from . import hooks
    fighting(g).discard(w.id)
    d = resume_ticks(g, w)
    w.anim, w.foe, w.face, w.busy_until = "", 0, None, 0
    w.path = getattr(w, "path_saved", w.path) or w.path
    wake_attackers(g, w)
    hooks.fight_over(g, w)
    if d is not None and w.id in g.walkers and not w.anim and (w.path or getattr(w, "roam_left", 0) > 0) \
            and w.next_move < g.tick + d:
        walkers.schedule(g, w, d)                # its next act is a step: not before the tile change


RESUMERS = ("rabble", "hoplite", "horseman", "wolf")     # + core walkers (no owner module); invaders: invaders._pause
SOLDIERS = ("rabble", "hoplite", "horseman")             # walk by sub-steps (forces.advance): progress kept in fprog


def resume_ticks(g, w):
    """figure_fight_end 0x004D61B0 keeps the tile progress (+0x39): the restored action's figure_move goes on from it
    the next tick, so the first tile change comes after the sub-steps left to count 8 (the tile change, 0x004D9330):
    8 - p below 8, else 7 to the centre (15 -> 0, the route decision) + 8. p = the progress at the fight start
    (progress: the mover 8, the other where its step was) + the closing-in (+1 a fight tick while below 6). Ticks at the
    figure's speed (num / den sub-steps a tick) from the next tick. Soldiers, wolves and core walkers (invaders keep
    their own pending step: invaders._pause); None for the others."""
    if w.role not in RESUMERS and (w.role in ROLES_OWNED or w.role in walkers.GOD_ROLES or w.role in ("monster", "hero")):
        return None
    cp = getattr(w, "close_p", None)
    if not cp:
        return None
    p = min(15, cp[0] + closed_in(g, w))
    if w.role in SOLDIERS:                         # forces.advance goes on from it, every tick
        w.fprog = p
        return 1
    r = 8 - p if p < 8 else 23 - p
    num, den = _speed_frac(g, w)
    if not num:
        return None
    return max(1, -(-r * den // num))


def leave_fight(g, w):
    """w leaves action 5 for another action without figure_fight_end (an archer's shot right after its contact, a
    cavalry disengage): its foes see it on their next fight tick."""
    fighting(g).discard(w.id)
    w.anim, w.foe, w.busy_until = "", 0, 0
    w.path = getattr(w, "path_saved", w.path) or w.path
    wake_attackers(g, w)


def act_dying(g, w):
    if g.tick >= w.anim_t0 + DYING - 1:
        from . import hooks
        hooks.gone(g, w)
        return walkers.remove(g, w)
    walkers.schedule(g, w, w.anim_t0 + DYING - g.tick)


def step(g, w, nxt):
    """Move a combat unit one tile (keeps contact.tiles in step)."""
    from . import contact
    old = (w.x, w.y)
    walkers.step_to(g, w, nxt)
    contact.track(g, w, old)


def spawn(g, role, x, y, delay=1, **kw):
    """A combat unit (ROLES) on the map."""
    from . import contact
    w = walkers.new_walker(g, role=role, home=kw.pop("home", 0), x=x, y=y)
    w.dmg, w.foe = 0, 0
    for k, v in kw.items():
        setattr(w, k, v)
    walkers.add(g, w, delay)
    contact.track(g, w, (x, y))
    return w


def remove(g, w):
    from . import contact
    contact.untrack(g, w)
    walkers.remove(g, w)
    _hunted_gone(g, w)


def _hunted_gone(g, w):
    """Invaders hunting w (action 13 checks its target every tick) see it gone on their next tick."""
    if w.role in ("rabble", "hoplite", "horseman", "hero"):
        from . import invaders
        invaders.target_gone(g, w)


SPEED = walkers.SPEED


def tile_ticks(g, w, code):
    """Ticks to the next tile at speed code `code` (15 sub-steps a tile, remainder carried as walkers.tile_delay)."""
    pace = g.rules.get("walker_pace", 15)
    num, den = SPEED[max(0, min(18, code))]
    if num == 0:
        return 10 ** 9
    total = pace * den + w.rem
    w.rem = total % num
    return max(1, total // num)
