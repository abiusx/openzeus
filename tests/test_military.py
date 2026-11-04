"""Military: wolves, invasions, fights, formations, defences, navy, missiles.
Run: python3 tests/test_sim.py military (or a test by name: python3 tests/test_sim.py test_NAME)."""
import os
import sys

from helpers import ROOT, Game, play, pre_pass, _hoplite_horseman_per_tick, _invader_routes_per_figure


def test_military_wolves():
    """Wolves (military.md "Wolves"): 3 packs of 7 at the sandbox's wolf points, hidden at first, then idle;
    a pack refills one wolf per 27 passes; a wolf on a sheep's tile kills it at its first hit (24 ticks);
    soldiers' and invaders' code stays off the core random stream."""
    from sim.military import units
    g, off = Game("sandbox_open", 1), Game("sandbox_open", 1)
    off.command("military off")
    g.step(g.rules["ticks_per_day"])
    off.step(g.rules["ticks_per_day"])
    ws = [w for w in g.walkers.values() if w.role == "wolf"]
    assert len(ws) == 21 and {w.origin for w in ws} == {(116, 15), (17, 122), (49, 157)}     # raw = logical + (1, 1)
    assert all(max(abs(w.x - w.origin[0]), abs(w.y - w.origin[1])) <= 1 for w in ws)
    assert g.rng.getstate() == off.rng.getstate()          # the module draws from its own generator
    assert not any(w.role == "wolf" for w in off.walkers.values())
    g.step(10 * g.rules["ticks_per_day"])
    assert all(w.task in ("x10", "x11", "x7", "xD", "xB", "xF") and not w.hidden for w in ws)
    victim = ws[0]
    units.kill(g, victim)
    g.step(14 * g.rules["ticks_per_day"])                  # 27 passes at 2 a day
    assert victim.id not in g.walkers
    assert len([w for w in g.walkers.values() if w.role == "wolf" and w.origin == victim.origin]) == 7
    from sim.systems import walkers
    wolf = next(w for w in g.walkers.values() if w.role == "wolf" and not w.anim)
    sheep = walkers.spawn_animal(g, "sheep", wolf.x, wolf.y)
    units.start_fight(g, wolf, sheep)
    g.step(units.HIT_EVERY + 1)
    assert sheep.anim == "die"
    g.step(units.DYING + 1)
    assert sheep.id not in g.walkers and wolf.anim != "fight"


def test_military_invasion():
    """An invasion on the boom city (military.md "Invaders on the map"): spawned hidden at a land invasion point,
    32-day muster, then the palace; recruitment frozen; the city's rabble mobilized at houses march to their slots
    and fight; the invasion ends. Point (149, 191) (land point 1): south of the city, away from the palace. Since the
    invaders' slots follow figure ids (formations_refresh 0x004DE210, bugs.md 426) the army passes the rabble's line
    and sacks the city: defeat (was: victory, slots in creation order). The outcome follows the city's figure slots
    and ids: since the storehouses' one deliveryman each (storemen.py, 11-04) the rabble hold: victory. Either way
    exactly one ending message."""
    from sim.military import invaders, forces
    g = play(1, "boom.txt")
    comps = forces.companies(g)
    n0 = sum(c["members"] for c in comps.values())
    assert n0 > 50
    g.command("invade 149 191")
    inv = next(iter(invaders.invasions(g).values()))
    assert inv["point"] in invaders.land_points(g)
    ens = [w for w in g.walkers.values() if w.role in invaders.TYPES]
    assert ens and all(w.hidden for w in ens)
    g.command("days 20")
    assert all(not w.hidden for w in ens if w.id in g.walkers)
    assert all(max(abs(w.x - inv["point"][0]), abs(w.y - inv["point"][1])) <= 20 for w in ens)   # mustering
    out = g.command("mobilize all 158 160")
    assert "mobilized" in out
    sol = [w for w in g.walkers.values() if w.role == "rabble"]
    assert len(sol) == n0 and all(w.task == "march" for w in sol)
    from sim.military import defences
    stones, shoot = [], defences.shoot
    defences.shoot = lambda g_, s, t, *a, **k: (stones.append((g_.tick, s.id)) if s.role == "rabble" else None) or shoot(g_, s, t, *a, **k)
    try:
        for _ in range(300):
            g.step(g.rules["ticks_per_day"])
            if not invaders.invasions(g):
                break
    finally:
        defences.shoot = shoot
    assert not invaders.invasions(g)
    msgs = [m for _, m in g.city.messages]
    assert any("Defeat!" in m for m in msgs) != any("Invasion force defeated" in m for m in msgs)
    # the rabble throw at the army, a stone per search that finds a target (archer_fire_update 0x004B2F70: a search
    # every col7 + 1 ticks in hold; bug 433); ours threw per tile walked and every 12 ticks before. (Was: fewer than 40
    # stones while the army passed the line; the battle now lasts: at most one stone per thrower per search.)
    by = {}
    for t in stones:
        by.setdefault(t[1], []).append(t[0])
    assert stones and min(b - a for v in by.values() for a, b in zip(v, v[1:])) > 12
    g.command("return all")
    g.command("days 20")
    assert not any(w.role == "rabble" for w in g.walkers.values())


def test_hoplite_horseman_per_tick():
    """fig_handler_hoplite 0x004B26B0 / fig_handler_horseman 0x004B1840 every tick (bugs.md 434): hold (FUN_004B10A0)
    walks back to the slot only while the company's melee / under-fire timers are 0 (not by an enemy within 20);
    attack 0x11: an enemy within 6 but none within 3 -> formation_charge 0x004DD6D0 (dest its tile, layout 1, the
    action saved), within 3 -> engage (figure_set_target marks it, flags & 2); hit and run 0xB: 5 ticks with one
    within 3 -> regroup 0x12; nearest_enemy skips marked enemies for hoplites / horsemen in 0x11 / 0xB."""
    from sim.campaign import flow
    from sim.military import forces, units
    g = flow.start("bigcity", seed=1, difficulty="VeryEasy")
    flow.briefed(g)
    ox, oy = g.world.origin
    from sim.systems import military as recruit
    upd, recruit.update = recruit.update, lambda g_: None   # no daily recount (the estates' horses drop it to 4)
    try:
        _hoplite_horseman_per_tick(g, ox, oy)
    finally:
        recruit.update = upd


def test_military_invasion_at_palace():
    """The boom city's land point (167, 173) is 7 tiles from the palace: the muster spot (FUN_00502840: route_search
    reach 600 from the lead, squares of radius 0..13; a building tile qualifies: only water, rubble / cliff, unreached
    and other figures fail it) is the palace's tile at radius 7. The members walk to it in route mode 2 (buildings
    +10, enemy_figure_update 0x00500BBF), stand in front of the palace and hit it (figure_check_next_tile 0x004D8BB0,
    grid 1: wall_damage_add(tile, 10, 1, city), every hit marks 0x00FE6A5B / 0x00FEB4F8); it collapses after its
    11th hit on one tile, and step 13's cities_relations_update finds no palace with the city's last hit: defeat
    (city_conquers_player), the army leaves (11-02: the exe's ending; before, the test accepted either)."""
    from sim.military import invaders
    g = play(1, "boom.txt")
    t0 = g.tick
    g.command("invade 167 173")
    for _ in range(10):
        g.step(g.rules["ticks_per_day"])
        if not invaders.invasions(g):
            break
    assert not invaders.invasions(g)
    msgs = [m for t, m in g.city.messages if t > t0]
    assert any("destroyed the palace" in m for m in msgs)
    assert any("Defeat!" in m for m in msgs) and not any("Invasion force defeated" in m for m in msgs)
    assert not any(w.role in invaders.TYPES and w.task != "leave" for w in g.walkers.values())


def test_invasion_hit_marks():
    """wall_damage_add 0x00492830 from figure_check_next_tile 0x004D8BB0 (route mode 2): a building hit passes the
    invader's city, a wall / tower hit 0xFF; 0x00FE6A5B = the last hit's, 0x00FEB4F8 = it on a palace tile (every
    hit); simulation_cycle_step 0xD resets both when no enemy is alive (cities_relations_update reads them)."""
    from sim.military import invaders, state
    g = play(1, "boom.txt")
    g.command("invade")
    inv = next(iter(invaders.invasions(g).values()))
    w = next(x for x in g.walkers.values() if x.role in invaders.TYPES)
    pal = next(b for b in g.buildings.values() if b.key == "palace")
    while (g.tick % 51) & 3:
        g.step(1)
    invaders._siege(g, w, (pal.x, pal.y), 1)
    st = state(g)
    assert st["palace_hit"] == st["last_hit"] == invaders.hitter(inv)
    invaders._siege(g, w, (pal.x + 30, pal.y), 3)                 # a wall hit: 0xFF, the palace's mark stays
    assert st["last_hit"] is None and st["palace_hit"] == invaders.hitter(inv)
    invaders.marks_reset(g)                                       # enemies alive: kept
    assert st["palace_hit"] == invaders.hitter(inv)


def test_military_hidden_archers_shoot():
    """A hidden archer in action 7 tries to shoot every tick (0x00500DAB -> archer_try_shoot 0x005009E0); a hit puts
    it in action 6 (0x005011C0), still hidden; fig_handler_enemy_archer 0x004B99B0's picture tail ends the shot at the
    frame wrap (action 7, attack_timer 0) with no hidden check, and action 6 does not count the action-7 timer: it
    appears the shot's length later than its spawn delay (bug 393; before: held in action 6 until the regroup)."""
    from sim.military import invaders
    from sim.systems import walkers
    g = play(1, "boom.txt")
    # land point 1, away from the palace: at a random point next to it (167, 173) the army razes the palace and
    # leaves (defeat) before the archer appears (11-02: the random pick followed ours' RNG order)
    g.command("invade 149 191")
    inv = next(iter(invaders.invasions(g).values()))
    px, py = inv["point"]
    arch = [w for w in g.walkers.values() if w.role == "enemy_archer"]
    assert arch and all(w.hidden for w in arch)
    appear0 = {w.id: w.appear for w in arch}
    from sim.military.defences import line_of_fire     # a target in range with a line of fire (the point is drawn)
    tx, ty = next((px + dx, py + dy) for dx, dy in ((0, 3), (3, 0), (0, -3), (-3, 0), (2, 2), (-2, 2), (2, -2), (-2, -2))
                  if g.world.inside(px + dx, py + dy) and line_of_fire(g, (px, py), (px + dx, py + dy)))
    t = walkers.new_walker(g, role="watchman", home=0, x=tx, y=ty)      # standing still
    walkers.add(g, t, 100000)
    # the reload (+0x6B) counts from each archer's first update, its first search col7 updates later (bug 435): on
    # this map the company's first regroup (FUN_005027e0, day 1) shows it before that, so the reload is taken as run
    for w in arch:
        w.next_shot = g.tick + 1
    g.step(3)
    shot = [w for w in arch if invaders.in_shot(w)]
    assert shot and all(w.hidden for w in shot)                     # shot at its first search, still hidden
    w = shot[0]
    L = invaders.shot_len(w)
    assert w.appear == appear0[w.id] + L                            # its action-7 timer stopped for the shot
    end = w.shot_end
    g.step(end - g.tick + 1)
    assert not invaders.in_shot(w) and w.hidden                     # the wrap: action 7 again, still hidden
    assert w.next_shot == end + invaders.units.col(g, w, "missile_rate") + 1
    while w.hidden and g.tick <= w.appear + 1:
        g.step(1)
    assert not w.hidden and g.tick - 1 >= appear0[w.id] + L


def test_military_closing_in():
    """figure_fight_tick 0x004D5F10 first steps a fighter whose tile progress is below 6 one fine unit a tick toward 6
    (the closing-in): the mover is at 8 (contact at the tile change), the other where its step is (an invader's +0x39,
    invaders.imove). figure_fight_end frees the route: the invader's next figure_move finds a new one (progress 15)
    and takes its route decision at once; the +0x36 timer does not run in action 5."""
    from sim.military import invaders, units
    from sim.systems import walkers
    g = Game("sandbox_open", 1)
    g.command("invade 150 60 16 0")
    g.step(20)
    inf = next(w for w in g.walkers.values() if w.role == "enemy_infantry")
    inf.hidden, inf.appear = False, 0
    m = walkers.new_walker(g, role="watchman", home=0, x=inf.x, y=inf.y)
    walkers.add(g, m, 10 ** 6)
    m.dmg = -10 ** 6
    with pre_pass(g) as T:
        m.prev, m.arrived = (m.x - 1, m.y), T
        assert units.progress(g, m, T, True)[0] == 8            # the mover: count 8, heading back = its step
        # the invader walks east, 3 sub-steps out of its tile centre toward (x + 1, y)
        inf.prev, inf.arrived, inf.task = (inf.x - 1, inf.y), T - 10, "march"
        inf.fprog, inf.heading, inf.iroute, inf.aim_due = 3, (inf.x + 1, inf.y), [(inf.x + 2, inf.y)], T + 20
        inf.dest = (inf.x + 2, inf.y)
        p = units.progress(g, inf, T, False)
        assert p == [3, 1, 0]
        units.start_fight(g, m, inf)
    assert inf.close_p == [3, 1, 0]
    g.step(10)
    assert units.closed_in(g, inf) == 3                         # 3 -> 6, then it stands
    with pre_pass(g):
        units.end_fight(g, m)                                   # (before the pass: inf sees it on the next tick)
    E = T + 11
    g.step(2)                                                   # inf's fight_end (its next tick): route freed
    assert inf.anim == "" and inf.iroute is None and inf.fprog == 6
    assert inf.aim_due == T + 20 + (E - T)                      # the re-aim timer moved by the fight's length
    x0 = inf.x
    g.step(1)                                                   # the saved action 9: a new route, decided at once
    assert inf.task == "march" and inf.fprog == 0 and inf.iroute is not None and inf.x == x0


def test_military_resume_after_fight():
    """figure_fight_end keeps the tile progress: a soldier's, wolf's or core walker's first tile change after a fight
    comes after the sub-steps left to count 8 from where the fight (and its closing-in) left it (units.resume_ticks):
    the mover (contact at count 8) a whole tile (15 sub-steps), the other 8 - p after closing in to 6 (bug 393)."""
    from sim.military import units
    from sim.systems import walkers
    g = Game("sandbox_open", 1)
    g.command("road 86 33 115 33")
    g.step(40)
    m = walkers.new_walker(g, role="mugger", home=0, x=100, y=33, roam_left=20)
    b = walkers.new_walker(g, role="watchman", home=0, x=100, y=33, roam_left=20)
    for w in (m, b):
        walkers.add(g, w, 10 ** 6)
        w.dmg = -10 ** 6
    with pre_pass(g) as T:
        m.prev, m.arrived = (99, 33), T                   # the mover steps in now: count 8
        b.prev, b.arrived = (101, 33), T - 12             # 12 ticks ago at speed 6: 8 + 12 = 20 -> 5 past the centre
        b.path = [(99, 33)]
        units.start_fight(g, m, b)
    assert m.close_p[0] == 8 and b.close_p[:1] == [5]
    g.step(10)
    with pre_pass(g) as E:
        units.end_fight(g, m)
        units.end_fight(g, b)
    assert m.next_move == E + 15                          # 15 sub-steps at 1 a tick
    assert b.next_move == E + 2                           # closed in 5 -> 6, then 2 to the tile change


def test_military_reaim_timer():
    """Invader actions 7 / 9 (0x00500C9E / 0x00500EC0): the +0x36 timer runs down every tick; at <= 0 it is 30 again
    and dest = the slot's spot; 7 -> 9 when not there, figure_move from the next tick (a figure at its tile centre
    decides on its first sub-step, the tile changes 8 sub-steps later); in 9 the dest changes only at the timer, an
    arrival is noticed at the tile centre (7 sub-steps after the step) and then it waits in 7 for the rest of the timer;
    a shot in a march ends in 7 (the wrap) with the step kept for the next march (bug 393)."""
    from sim.military import invaders
    g = Game("sandbox_open", 1)
    g.command("invade 150 60 16 0")
    g.step(2)
    inf = next(w for w in g.walkers.values() if w.role == "enemy_infantry")
    comp = invaders.ecomps(g)[inf.company]
    comp["countdown"] = 10 ** 6                                 # (no AI pass changes it here)
    inf.hidden, inf.appear = False, g.tick + 1
    goal = (inf.x - 6, inf.y)
    off = invaders.slot_dest(comp, inf.slot)
    comp["target"] = (comp["target"][0] + goal[0] - off[0], comp["target"][1] + goal[1] - off[1])
    assert invaders.slot_dest(comp, inf.slot) == goal
    T = g.tick + 1                                              # the next pass
    inf.next_move = T
    g.sd("queue", {}).setdefault(T, []).append(inf.id)
    x0 = (inf.x, inf.y)
    g.step(1)
    assert inf.task == "march" and inf.aim_due == T + 30 and (inf.x, inf.y) == x0
    steps = []
    while g.tick < T + 40:
        p = (inf.x, inf.y)
        g.step(1)
        if (inf.x, inf.y) != p:
            steps.append(g.tick)                                # the pass just run
    assert steps[:2] == [T + 9, T + 24], steps                # first sub-step T+1 (the decision), tile at +8, then 15
    # a target change mid-march is taken at the timer only
    comp["target"] = (comp["target"][0], comp["target"][1] + 3)
    d0 = tuple(inf.dest)
    while g.tick < inf.aim_due - 1:                             # every pass before the timer's
        g.step(1)
        assert tuple(inf.dest) == d0
    g.step(1)                                                   # the pass at aim_due
    assert tuple(inf.dest) == invaders.slot_dest(comp, inf.slot)


def test_sanctuary_troops_and_combat_sounds():
    """Sanctuary troops are drawn with their own art (bug 393): Artemis' Amazons (companies 31 / 32, rabble) with army
    4's archer sprites, Ares' warriors (33 / 34, hoplites) with Zeus_AresWarriors (fig_handler_rabble 0x004B31F0 /
    fig_handler_hoplite 0x004B26B0); the combat sounds: the sample table 0x010E0518 from the exe's loader (FUN_005A5D00),
    kinds by type and army (FUN_004DB3D0 / FUN_004DB7A0 / FUN_004DAB30 / FUN_004DC560), and the sim's hit sfx."""
    import json
    from sim.military import forces, units
    from sim.systems import walkers
    assert forces.SANCT_LOOK == {31: "amazon", 32: "amazon", 33: "ares", 34: "ares"}
    M = json.load(open(os.path.join(ROOT, "data", "play", "military.json")))["roles"]
    assert M["rabble:amazon"]["fight_rule"] == "amazon" and M["rabble:amazon"]["walk"]["frames"] == 12
    assert M["hoplite:ares"]["file"] == "Zeus_AresWarriors" and M["hoplite:ares"]["die"]["dir0"]
    C = json.load(open(os.path.join(ROOT, "data", "play", "audio.json")))["combat"]
    S = C["samples"]
    assert S["1"]["1"].endswith("greek_hand1.wav") and S["1"]["3"].endswith("rabble_rock1.wav")
    assert S["2"]["7"].endswith("hop_spear_hit.wav") and S["20"]["8"].endswith("Ares_warr_die.wav")
    assert C["army_kind"]["enemy_infantry"][1] == 0xA and C["type_kind"][str(0x3B)] == 0x69
    g = Game("sandbox_open", 1)
    g.sfx = []
    a = walkers.new_walker(g, role="wolf", home=0, x=50, y=50)
    b = walkers.new_walker(g, role="watchman", home=0, x=50, y=50)
    for w in (a, b):
        walkers.add(g, w, 10 ** 6)
    units.hit(g, a, b)
    assert any(e[1] == b.id and e[6] == "hit" for e in g.sfx)


def test_military_melee_timing():
    """Bug 393, melee as the exe (military.md "Fight", "Invader melee"): figure_fight_tick 0x004D5F10 runs every tick of
    action 5: an opponent that leaves action 5 (dies) ends the fight or switches to the other one the next tick, and
    the attack timer counts on across the switch (a hit every 24 ticks of the fighter's own cycle); mode-2 cavalry
    disengage at attack_timer 12 (0x004B9E20 -> 0x00501480: action 11 to a spot col 12 away, y from f.x); an archer
    whose fight ends with attack_timer != 0, or that a regroup (FUN_005027E0) takes out of its shot, never reloads
    (archer_try_shoot 0x005009E0 needs attack_timer 0) until a fight start resets it."""
    from sim.military import invaders, units
    from sim.systems import walkers
    g = Game("sandbox_open", 1)
    g.command("invade 150 60 16 0")
    g.step(2)
    ens = [w for w in g.walkers.values() if w.role in invaders.TYPES]
    inf = next(w for w in ens if w.role == "enemy_infantry")
    cav = next(w for w in ens if w.role == "enemy_cavalry")
    arc = next(w for w in ens if w.role == "enemy_archer")
    for w in (inf, cav, arc):
        w.hidden, w.appear = False, 0

    def man(x, y):
        m = walkers.new_walker(g, role="watchman", home=0, x=x, y=y)
        walkers.add(g, m, 10 ** 6)
        m.dmg = -10 ** 6                                     # never falls to a hit here
        return m
    w1, w2 = man(inf.x, inf.y), man(inf.x, inf.y)
    with pre_pass(g) as T:
        units.start_fight(g, w1, inf)                        # inf (b) answers w1; its timer from T
    g.step(5)
    with pre_pass(g):
        units.start_fight(g, w2, inf)                        # inf records w2 as its second opponent
    g.step(5)
    with pre_pass(g):
        units.kill(g, w1)                                    # w1 falls before tick T + 10 (not by inf)
    g.step(1)
    assert inf.foe == w1.id                                  # (g.step(1) runs the pass of tick g.tick)
    g.step(1)
    assert inf.anim == "fight" and inf.foe == w2.id          # switched in the next tick ...
    d0 = w2.dmg
    while g.tick < T + 23:
        g.step(1)
    assert w2.dmg == d0
    g.step(1)
    assert w2.dmg > d0                                       # ... and hits at T + 24, its own cycle (not T + 11 + 24)
    with pre_pass(g):
        units.kill(g, w2)
    g.step(1)
    assert inf.anim == "fight"
    g.step(1)
    assert inf.anim == ""                                    # its last foe fell: the fight ends the next tick
    # mode-2 cavalry: out of the fight at attack_timer 12
    comp = invaders.ecomps(g)[cav.company]
    comp["mode"], comp["countdown"] = 2, 99                 # (the daily AI keeps it)
    w3 = man(cav.x, cav.y)
    with pre_pass(g) as T:
        units.start_fight(g, w3, cav)
    while cav.anim == "fight" and g.tick < T + 30:
        g.step(1)
    assert cav.task == "disengage" and g.tick == T + 12
    d = units.col(g, cav, "special_range")
    assert (cav.dest[0] - cav.x) in (-d, 0, d) and (cav.dest[1] - cav.x) in (-d, 0, d)    # y = f.x + dy (exe)
    g.step(1)
    assert w3.anim == ""                                     # it saw its foe leave action 5 (the next tick)
    # an archer's fight ending with attack_timer != 0 jams its reload
    arc.next_shot, arc.shot_end, arc.arrow_due = g.tick + 10 ** 6, None, None   # (no shot at the watchmen here)
    w4 = man(arc.x, arc.y)
    with pre_pass(g):
        units.start_fight(g, w4, arc)
    g.step(5)
    with pre_pass(g):
        units.kill(g, w4)
    g.step(2)
    assert arc.anim == "" and arc.frozen and not invaders._try_shoot(g, arc, invaders.ecomps(g)[arc.company])
    w5 = man(arc.x, arc.y)                                   # a new fight resets it; ended by its own killing hit: 0
    w5.dmg = units.col(g, w5, "hp")
    with pre_pass(g):
        units.start_fight(g, arc, w5)
    while w5.anim == "fight":
        g.step(1)
    assert w5.anim == "die"
    g.step(1)
    assert arc.anim == "" and not arc.frozen
    man(arc.x, arc.y)                                        # a regroup mid-shot: action 7, attack_timer 1 kept
    arc.next_shot = 0
    with pre_pass(g):
        assert invaders._try_shoot(g, arc, invaders.ecomps(g)[arc.company])
        invaders._regroup(g, [arc])
    assert not invaders.in_shot(arc) and arc.arrow_due is None and arc.frozen


def test_military_orders_and_defences():
    """Companies: mobilize/move/mode/return walk soldiers out and home; a raid marches hoplites to the map exit;
    the full city's tower (2-thick wall) keeps a tower sentry and a wall sentry patrolling the wall-walk grid."""
    from sim.military import forces, defences
    g = play(1, "full.txt")
    old = next(b for b in g.buildings.values() if b.key == "tower")
    assert old.employees == 0 and "palace" in old.reason          # full.txt's west tower: off the palace's roads
    g.city.treasury += 5000                                         # a 2-thick wall with a tower by a palace road
    g.command("wall 125 111 128 111")
    g.command("wall 125 112 128 112")
    g.command("build tower 125 111")
    g.step(3 * g.rules["ticks_per_day"])
    t = next(b for b in g.buildings.values() if b.key == "tower" and (b.x, b.y) == (125, 111))
    assert t.employees == g.cat.spec("tower")["employees"]
    roles = {w.role for w in g.walkers.values()}
    assert "tower_sentry" in roles and "wall_sentry" in roles
    ok, _ = defences.wall_grid(g)
    seen = set()
    for _ in range(40):
        g.step(30)
        seen |= {(w.x, w.y) for w in g.walkers.values() if w.role == "wall_sentry"}
    assert len(seen) > 2 and seen <= ok
    s = min(forces.companies(g))
    g.command(f"mobilize {s}")
    c = forces.companies(g)[s]
    assert c["mob"] and len(forces.members(g, c)) == c["members"]
    g.command(f"mode {s} attack")
    g.command(f"return {s}")
    g.command("days 30")
    assert not forces.members(g, c) and not c["mob"]


def test_military_deaths_cost_the_city():
    """figure_delete 0x004DA250 (military.md "Soldier deaths"): a fallen palace soldier is paid for: rabble =
    house_deaths(6) from common houses; hoplite / horseman = the house FUN_004CDC50 picks loses 1 armor (+1 horse)
    and 1 resident."""
    from sim.military import forces, units
    g = play(1, "full.txt")
    comps = forces.companies(g)
    have = lambda good: sum(b.goods.get(good, 0) for b in g.buildings.values() if b.kind == "house")
    done = set()
    for kind in ("rabble", "hoplite", "horseman"):
        s = next((s for s, c in sorted(comps.items()) if c["type"] == kind), None)
        if s is None:
            continue
        g.command(f"mobilize {s}")
        w = forces.members(g, comps[s])[0]
        pop, armor, horses = g.city.population, have("armor"), have("horses")
        units.kill(g, w)
        if kind == "rabble":
            assert g.city.population == pop - 6, (pop, g.city.population)
        else:
            assert g.city.population == pop - 1 and have("armor") == armor - 1
            assert have("horses") == horses - (kind == "horseman")
        done.add(kind)
    assert "rabble" in done and done & {"hoplite", "horseman"}       # full.txt: rabble and horsemen


def test_military_morale_never_routs():
    """military.md "Morale" (sim/military/morale.py): formation_member_lost 0x004DDFF0 indexes its table by +0x28 - 1
    with the dying (the one just hit too) counted; formations_morale_waver 0x004DDF20 at cycle step 5: a mobilized
    palace company below 21 gives its side -3 and the invaders +3 once, then counts +0x73 (< 11) / +0x66 (11..20);
    it never routs (oracle 1B-inv-city: company 1 fights at morale 0). An invader company that wavers leaves."""
    from sim.military import forces, units, morale, invaders
    g = play(1, "full.txt")
    comps = forces.companies(g)
    s = next(s for s, c in sorted(comps.items()) if c["members"] >= 8)
    other = next(t for t in sorted(comps) if t != s)
    g.command(f"mobilize {s}")
    c = comps[s]
    c["morale"] = 100
    ms = forces.members(g, c)
    units.kill(g, ms[0])
    assert c["morale"] == 95                         # 8 figures (the dying one counted): LOSS[7]
    units.kill(g, ms[1])
    assert c["morale"] == 90                         # 6 + 2 dying = 8 again
    c["morale"], comps[other]["morale"] = 15, 100
    morale.waver(g)
    assert (c["morale"], c["waver"], c.get("rout", 0), comps[other]["morale"]) == (12, 1, 0, 97)
    morale.waver(g)                                  # counters set: no second -3
    assert (c["morale"], c["waver"], comps[other]["morale"]) == (12, 2, 97)
    c["morale"] = 0
    for m in forces.members(g, c)[:-1]:
        units.kill(g, m)
    assert c["mob"] and c["ready"] and len(forces.members(g, c)) == 1      # still mobilized, never routed
    e = {"id": 99, "morale": 5, "leave": False}
    invaders.ecomps(g)[99] = e
    morale.waver(g)
    assert e["rout"] == 1 and e["leave"]


def test_military_slots_routes_standards():
    """formations_refresh 0x004DE210: an invader company's slots are its figures' id ranks (Walker.fslot), dying ones
    included; route mode 0 (bfs4 + trace(8)) marches diagonally; fig_handler_standard 0x004B3E00 every tick in
    peace: + 80 a tick at home, + 1 per 26 ticks mobilized (bugs.md 426)."""
    from sim.military import forces, invaders, morale, alarm, state
    g = play(1, "full.txt")
    g.command("invade 149 191")
    c = next(iter(invaders.ecomps(g).values()))
    ws = [g.walkers[i] for i in c["ids"]]
    for w, s in zip(ws, sorted((w.fslot for w in ws), reverse=True)):
        w.fslot = s                                   # ids downwards, as after an exe load
    morale.refresh(g)
    assert [w.slot for w in sorted(ws, key=lambda w: w.fslot)] == list(range(len(ws)))
    assert ws[-1].slot == 0 and c["ids"][0] == ws[-1].id
    comps = forces.companies(g)
    s = next(s for s, k in sorted(comps.items()) if k["members"] >= 8)
    g.command(f"mobilize {s}")
    w = forces.members(g, comps[s])[0]
    p = w.path
    assert p and any(abs(a[0] - b[0]) == 1 and abs(a[1] - b[1]) == 1 for a, b in zip(p, p[1:])) or len(p) < 3
    for v in list(g.walkers.values()):                # no invasion: peace once the counters allow it
        if v.role in forces.ENEMY_UNITS:
            from sim.military import units
            units.remove(g, v)
    invaders.ecomps(g).clear()
    invaders.invasions(g).clear()
    st = state(g)
    st["months_since_enemy"], st["months_to_next"] = 2, 99
    assert forces.peace(g)
    other = next(t for t in sorted(comps) if t != s and not comps[t].get("mob"))
    comps[other]["morale"], comps[s]["morale"], comps[s]["mtimer"] = 10, 50, 0
    g.step(1)
    assert comps[other]["morale"] == 90
    g.step(25)
    assert comps[s]["morale"] == 51 and comps[s]["mtimer"] == 0


def test_military_auto_defend():
    """Auto-defend (0x00568D20 / 0x00569010, military.md "Counters"): one month before a rival's army arrives the
    companies muster at the rally point with military labour at priority 5; one month after the last invader they
    go home and the priorities come back. sentiment_from_military 0x00566E70: 0 in wartime, -1 for 1..2 mobilized
    companies in peace."""
    from sim.military import alarm, forces, invaders
    from sim.systems import labor
    from sim.empire import war
    g = play(1, "boom.txt")
    g.command("autodefend on")
    war.invasion_create(g, g.empire.find("Sparta"), 16)
    comps = forces.companies(g)
    mob = lambda: [c for c in comps.values() if c.get("mob")]
    while alarm.months_to_next(g) != 1:
        g.step(51)
    assert mob() and labor.priorities(g)[7] == 5 and max(labor.priorities(g)[:7]) <= 4
    # the rally mobilize used (alarm.state rally holds the last one): point 8 = a random valid point
    # (pick_point 0x00503E20), so asking rally_point again can draw another point
    rally = tuple(next(iter(alarm.state(g)["rally"].values())))
    assert rally in [tuple(c["dest"]) for c in mob()] and alarm.sentiment(g) == 0
    # offensive (11-03): an invader's action 10 hunts only while its company is engaged (else one step, then action 7:
    # oracle 1B-inv-city), so Sparta's archers stand off and shoot at companies holding the rally point for years
    g.command("mode all attack")
    for _ in range(600):
        g.step(51)
        if not mob() and not invaders.invasions(g):
            break
    assert not mob() and not invaders.invasions(g) and labor.priorities(g) == [3] * 8
    assert alarm.months_since_enemy(g) == 1
    s = min(comps)
    g.command("autodefend off")
    g.command(f"mobilize {s}")
    g.command("months 1")
    assert alarm.months_since_enemy(g) >= 2 and alarm.sentiment(g) == -1


def test_military_aid():
    """Defensive aid (world-map.md 6.8): the troops are offered (Accept/Decline), accepted they appear at the map
    entry as event companies 21..30 split by the sender's army shares (0x004E2C10), stay 4 months while no enemy is
    on the map, then walk out; the sender loses them (army += 0, 0x00481D10)."""
    from sim.military import forces
    g = play(1, "boom.txt")
    g.command("empire army Tiryns 40")
    g.command("empire attitude Tiryns 90")
    g.command("request Tiryns troops")
    while "Forces arrive" not in g.command("offers"):
        g.step(51)
    ev = next(e for e in g.empire.events if e["type"] == "offer" and e["kind"] == "troops")
    assert "postpone" not in g.command("offers").split("Forces arrive")[1].split("\n")[0]
    t = g.empire.find("Tiryns")
    army = t.army
    g.command(f"offer {ev['id']} accept")
    comps = forces.companies(g)
    aid = {s: c for s, c in comps.items() if c.get("event")}
    assert sorted(aid) == [21, 22, 23, 24] and sum(c["members"] for c in aid.values()) == 16
    assert t.army == army - 16 and t.away[2] == 16
    g.command("days 5")
    on_map = [w for w in g.walkers.values() if getattr(w, "comp", 0) in aid]
    assert len(on_map) == 16 and all(max(abs(w.x - g.world.entry[0]), abs(w.y - g.world.entry[1])) <= 8 for w in on_map)
    g.command("months 5")
    assert any("Forces return to Tiryns" in m for _, m in g.city.messages)
    g.command("days 20")
    assert not any(c.get("event") for c in comps.values()) and t.away[2] == 0
    assert not any(getattr(w, "comp", 0) in aid for w in g.walkers.values())


def test_enemy_ship_route_free():
    """bugs.md 243: the enemy ships' route is freed every 100 updates (0x004D4790); find_route sets progress 15,
    so the rest of the tile is skipped: a transport sails ~14.3 ticks a tile, not 15."""
    from sim.military import navy, units
    from sim.systems import walkers
    g = Game("sandbox_open", 1)
    sea = [p for p in navy.sea_points(g)[0] if p]
    start = navy.snap_ship(g, sea[0])
    land = next(x for x in navy.sea_points(g)[1] if x)
    w = units.spawn(g, "enemy_transport", start[0], start[1], delay=1, act=0xB, hidden=False, army=0, nation=0,
                    inv=0, loaded=True, payload=("missile", 0), landing=land, hp=100, hpmax=100, target=0,
                    face=(0, 1), timer=0, rr0=g.tick)
    dest = navy._landing_water(g, land)
    route = walkers.water_path(g, start, {dest})
    assert route and len(route) > 30, route
    t0 = g.tick
    while w.act == 0xB and g.tick < t0 + 3000:
        g.step(1)
    n = len(route)
    ticks = g.tick - t0
    assert 14 * n <= ticks < 15 * n - 3 * (ticks // 100), (ticks, n)  # ~5 sub-steps gained every 100 ticks


def test_military_navy():
    """Navy (navy.md): a staffed warship wharf launches a trireme that anchors at its mooring (6 -> 0x19 -> 0x14,
    advisor "Anchored" 51:34); sent home it sails back and its crew leaves (0x17 -> 0x18 "Unmanned", the wharf's
    workers go home). A sea invasion (invasion_spawn_sea 0x503FD0): warships patrol and hunt, transports land the
    soldiers at the map's landing point (0xDD), then sail away."""
    from sim.military import navy, invaders
    from sim.systems import labor
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("road 50 81 50 83")
    g.command("build trireme_wharf 50 84")
    b = next(x for x in g.buildings.values() if x.key == "trireme_wharf")
    b.goods.update(wood=200, armor=200)
    orig = labor.allocate
    g.command("road 86 33 115 33")                         # launch and repair need a palace (0x0048CFB0 case 0x88)
    g.command("build palace 92 24")

    def staffed(g):                              # no population in this test
        orig(g)
        if not b.misc.get("off"):
            b.employees = g.cat.spec(b.key)["employees"]
    labor.allocate = staffed
    try:
        for _ in range(60):
            g.step(51)
            if navy.triremes(g) and getattr(navy.triremes(g)[0], "act", None) == 0x14:
                break
        t = navy.triremes(g)[0]
        assert t.act == 0x14 and (t.x, t.y) == navy.dock(g, t) and navy.label(g, b) == (34, True)
        assert navy.crew(g, t) == 100 and navy.col(g, t, "attack") == 80
        g.command(f"trireme {t.id} patrol")                 # the trireme panel (0x00406400): patrol, then hold
        g.step(51 * 3)
        assert t.act in (0x15, 0x16) and (t.x, t.y) != navy.dock(g, t)
        g.command(f"trireme {t.id} hold")
        assert t.act == 0x14
        g.command(f"trireme {t.id} repair")                 # back to the wharf: anchored there again
        g.step(51 * 6)
        assert t.act == 0x14 and (t.x, t.y) == navy.dock(g, t)
        assert navy.look(g, t)[8] == "idle"           # standing: the crew picture unless the wharf's crew-home bit
        b.misc["off"] = True                           # (the trireme handler's tail; bug 236: 0x1D with the bit)
        assert navy.look(g, t)[8] == "idle_empty"
        b.misc.pop("off")
        inv = invaders.invade(g, None, army=1, strength=24, sea_pt=9)
        ships = [w for w in g.walkers.values() if w.role in ("enemy_warship", "enemy_transport")]
        assert sum(w.role == "enemy_warship" for w in ships) == 6              # warships hidden until their timer,
        assert all(w.hidden == (w.role == "enemy_warship") for w in ships)      # transports wait visible (0x004D29D0)
        assert len({(w.x, w.y) for w in ships}) == len(ships)                   # each on its own tile (0x00461C20)
        for _ in range(60):
            g.step(51)
            if invaders.invasions(g)[inv]["companies"]:
                break
        assert any("disembarked" in m for _, m in g.city.messages)
        land = [w for w in g.walkers.values() if w.role in invaders.TYPES]
        assert land and all(max(abs(w.x - 104), abs(w.y - 101)) <= 3 for w in land)
        navy.crew_home(g, t)
        g.step(51 * 6)
        if t.id in g.walkers and t.anim != "die":
            assert t.act == 0x18 and b.misc.get("off") and navy.label(g, b) == (33, True)
    finally:
        labor.allocate = orig


def test_arrow_pictures():
    """Arrow pictures (walker_player_missile 0x004BACE0, fig_handler_enemy_missile 0x004BD970; oracle 1D-arrows,
    tools/oracle_arrows.py: 1024 of 1024 equal): ((dir32 - 4 view) mod 32 - 13) & 31 into SprAmbient 79 / 71 (shadows
    78 / 70) by the shooter, group 51 / 50 one picture; exe image numbers + 1 = ours (dump: dir 0, view 0 -> 2625)."""
    from types import SimpleNamespace as NS
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import oracle_arrows as oa
    from sim.military import defences
    assert [oa.arrow_index(d, 0) for d in (0, 1, 13, 19)] == [19, 20, 0, 6]
    assert oa.arrow_index(0, 2) == 11 and oa.arrow_index(30, 6) == 25
    G = oa.groups()
    assert G[0][0] + oa.arrow_index(0, 0) == 2625 + 1 and G[3][2] == 1
    g = NS(poseidon=False)
    A, E = NS(role="arrow"), NS(role="enemy_arrow")
    pick = lambda w, sh: defences.arrow_group(g, w, sh)
    assert pick(A, NS(role="tower_sentry")) == pick(A, NS(role="wall_sentry")) == "a79"
    assert pick(A, NS(role="rabble", comp=3)) == "a51" and pick(A, NS(role="rabble", comp=31)) == "a79"
    assert pick(A, NS(role="trireme")) == "a51"
    assert [pick(E, NS(role="enemy_archer", army=n)) for n in (0, 1, 2, 5)] == ["a51", "a71", "a79", "a79"]
    assert pick(E, NS(role="enemy_warship")) == pick(E, None) == "a71"


def test_line_of_fire_piece():
    """Line of fire 0x004D9B80 blocks on a building tile whose piece nibble (g_grid_piece 0x00D00D68 & 0xF, written
    by building_footprint_place 0x004A04B0 as width - 1) is set: storehouse and trading post parts are 1x1 (clear),
    a dock's land parts clear and its water square blocks, a composite piece by its own width (stage-0 rough base:
    one picture per tile, clear). Checked against the exe's grids of all 16 tutorial saves (tools/los_piece_check.py)."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import los_piece_check
    for n in ("tutorial08.sav", "tutorial15.sav"):
        r = los_piece_check.check(os.path.join(ROOT, "zeus-original/app/Adventures", n))
        assert r[0] > 0 and not r[1], (n, r)


def test_sanctuary_companies():
    """bugs.md 368: the sanctuary companies 31..34 (cycle_formations_pass_14 0x00567C70 at day_of_month 2): "See a
    working city" converts with Ares' Sparti / Ares' Guard (33 / 34, 8 each) and its palace companies in their
    saved slots (horsemen 9, 10, 16: oracle 1L5-troopsgo army.bmp); a company gone is created again at the next day 2
    with one member when the sanctuary stands complete, +1 a month up to 8; with the sanctuary gone it is removed."""
    from sim.campaign import flow
    from sim.systems import military
    g = flow.start("bigcity", seed=1, difficulty="VeryEasy")
    comps = military.companies(g)
    assert {s: (c["type"], c["members"]) for s, c in comps.items() if s in (9, 10, 16, 33, 34)} == {
        9: ("horseman", 8), 10: ("horseman", 8), 16: ("horseman", 8), 33: ("hoplite", 8), 34: ("hoplite", 8)}
    del comps[34]
    comps[33]["members"] = 5
    dpm, tpd = g.rules["days_per_month"], g.rules["ticks_per_day"]
    while g.day % dpm != 3:
        g.step(tpd)
    assert comps[34]["members"] == 1 and comps[33]["members"] == 6 and comps[34]["sanct"] == "ares"
    comps[33]["home"] = comps[34]["home"] = -1                  # the sanctuary gone
    g.step(tpd * dpm)
    assert 33 not in comps and 34 not in comps


def test_invader_routes_per_figure():
    """Invaders walk route mode 2 per figure (enemy_figure_update 0x00500B70, figure_route_walk 0x004D7BD0): a route
    from route_search when they have none, progress 15 when one is found, the tile at progress 8; action 7 frees it
    every tick. A company's first target is logical (0, 0): its spots are off the map, so a released soldier stays
    put (route lost) until the company AI's muster spot (FUN_00502840: lead + layout, play edge 10, reach within 600
    pops, tiles free of other companies). Oracle 1B-inv-land / 1B-inv-walk (tools/oracle_invasion.py --compare):
    ours after tick K = the exe's dump K (Game.step: the cycle step, then the figure pass)."""
    from sim.military import invaders
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import oracle_invasion
    g = Game("sandbox", 1)
    ox, oy = g.world.origin
    oracle_invasion.arm(g, "land")                          # spawned in run_day of the change to February (816)
    # the special-mode roll draws the exe's RNG (enemy_company_special_roll 0x004FFE00): its outcomes in the run's
    # dumps up to 986 (exe companies 44 and 49 = ours 37 and 42 in mode 2), as tools/oracle_invasion._replay_special
    orig = invaders._special

    class Fixed:
        def __init__(self, rng, hit):
            self.rng, self.hit = rng, hit

        def randrange(self, n):
            self.rng.randrange(n)
            return -1 if self.hit else n
    invaders._special = lambda g_, comp, row1, rng: orig(g_, comp, row1, Fixed(rng, comp["id"] in (37, 42)))
    try:
        _invader_routes_per_figure(g, ox, oy)
    finally:
        invaders._special = orig


def test_build_refused_near_enemies():
    """build_commit 0x00498910 refuses every tool but clear land with an enemy soldier, transport or warship within
    12 tiles of either corner of the action (enemies_near_rect 0x004DCF60, message 0x21), after the debt test
    (message 0x13, every tool)."""
    from sim.game import CommandError
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("invade 150 60 16 0")                         # hidden ones count too
    for c in ("build house 155 62", "road 140 70 160 70", "wall 150 66 155 66", "avenue 150 50 160 50"):
        try:
            g.command(c)
            assert False, c
        except CommandError as e:
            assert e.warn == (0x21,), (c, e)
    assert "built" in g.command("build house 120 62")       # 30 tiles away
    g.command("clear 151 61")                               # clear land: no enemy test
    g.city.treasury = -2000
    for c in ("clear 120 62", "build house 100 62"):
        try:
            g.command(c)
            assert False, c
        except CommandError as e:
            assert e.warn == (19,), (c, e)


def test_invader_target_choice():
    """FUN_00501F20 / FUN_005020F0: the presence grid of mobilized companies (rings 7..1 by member count, +2 more
    under a soldier); FUN_00502250: the reached maximum within r; FUN_00502370: the palace when reached, else the
    class list's earliest type by 4-way hops, storehouse x + 1; the under-fire marks of a missile hit."""
    from sim.military import invaders, forces
    g = play(1, "boom.txt")
    slot, c = next((k, c) for k, c in sorted(forces.companies(g).items()) if c.get("members"))
    assert "mobilized" in g.command(f"mobilize {slot} 158 160")
    g.step(400)
    ms = forces.members(g, c)
    lead = min(ms, key=lambda f: f.slot)
    invaders.presence_build(g)
    p = invaders.presence(g)
    n = len([i for i in c["ids"] if i in g.walkers])
    rings = (7, 6, 5, 4, 3, 2, 1, 1)[:n]
    edge = (lead.y - 7) * 228 + lead.x                   # in the radius-7 ring only
    assert p[edge] in (1, 3)
    dist = invaders.reach(g, (lead.x, lead.y))
    spot = invaders.troops_spot(g, (lead.x + 10, lead.y), 16, dist)
    assert spot is not None and p[spot[1] * 228 + spot[0]] >= len(rings)
    g.command("invade")
    comp = next(iter(invaders.ecomps(g).values()))
    comp["pos"] = (lead.x, lead.y)
    t, pal = invaders.target_buildings(g, comp)
    palace = next(b for b in g.buildings.values() if b.key == "palace")
    from sim.systems import monuments
    assert pal and t == monuments.piece_xy(palace, 0)    # g_palace_building: the main part (oracle 1B-inv-city)
    inv = invaders.invasions(g)[comp["inv"]]
    w = next(g.walkers[i] for i in comp["ids"] if i in g.walkers)
    invaders.under_fire(g, 0x34, w, lead)                # its archer's missile hit a soldier: marked from his company
    assert comp["under"] == 6 and comp["under_from"] == slot
    invaders.under_fire(g, 0x2D, None, w)                # a sentry's arrow (formation 0)
    assert comp["under_from"] == 0 and inv["companies"]


def test_military_grid():
    """grid_military (0x00502BA0, sim/military/routes.grid): orchard trees and roads 0, bridges 5 (cost 2), water -2,
    burning ruins -1 (the sandbox's grid equals the exe's at tick 0: tools/oracle_route2.grid_from_dump)."""
    from sim.game import Game
    from sim.military import routes
    g = Game("sandbox", 1)
    gm = routes.grid(g)
    wx, wy = next((x, y) for y in range(228) for x in range(228) if g.world.flags[y, x] & 4
                  and not g.world.flags[y, x] & 0x90000)
    assert gm[wy * 228 + wx] == -2
    g.command("build house 121 197")
    b = next(b for b in g.buildings.values() if b.key == "house")
    assert routes.grid(g)[b.y * 228 + b.x] == 1
    assert routes.route2(g, (122, 201), (121, 197)) == [(122, 200), (121, 199), (120, 198), (121, 197)]   # 1I-missile


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])


def test_expedition_casualties_cost_the_city():
    """expedition_casualties 0x004DF120 (bug 471): the dead of a world-map battle get state 2 -> figure_delete, so a
    palace company's losses are paid like a death at home (rabble 6 people; hoplite / horseman 1 resident + 1 armor
    (+ 1 horse) from a house); sanctuary companies are free; a company with no member left is freed."""
    from sim.military import forces
    from sim.empire import war
    g = play(1, "full.txt")
    comps = forces.companies(g)
    have = lambda good: sum(b.goods.get(good, 0) for b in g.buildings.values() if b.kind == "house")
    s = next(s for s, c in sorted(comps.items()) if c["type"] == "horseman" and c["members"] >= 5)
    n = comps[s]["members"]
    pop, armor, horses = g.city.population, have("armor"), have("horses")
    lost = n * 20 // 100
    assert not war.casualties(g, {"id": -5, "companies": [s]}, 20)
    assert comps[s]["members"] == n - lost
    assert g.city.population == pop - lost and have("armor") == armor - lost and have("horses") == horses - lost
    comps[99] = {"type": "hoplite", "members": 8, "sanct": "ares"}
    pop = g.city.population
    assert not war.casualties(g, {"id": -5, "companies": [99]}, 50)
    assert comps[99]["members"] == 4 and g.city.population == pop            # sanctuary troops: free
    assert war.casualties(g, {"id": -5, "companies": [s, 99]}, 100)        # all dead: wiped, slots freed
    assert s not in comps and 99 not in comps
