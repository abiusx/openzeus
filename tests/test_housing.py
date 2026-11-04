"""Houses and services: stadium, avenues, health, immigrants, desirability, schools and games, crime, fire.
Run: python3 tests/test_sim.py housing (or a test by name: python3 tests/test_sim.py test_NAME)."""
import os

from helpers import Game, play, _raises


def test_stadium():
    """Two 5x5 halves (v 5x10 default, h 10x5), one per city (19:44); old 5x5 saves grow a second half."""
    from sim.game import CommandError
    from sim.model import Building
    from sim.systems import stadium
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("road 60 71 74 71")
    assert "5x10" in g.command("build stadium 60 61")
    b = next(b for b in g.buildings.values() if b.key == "stadium")
    assert (g.world.occ == b.id).sum() == 50 and b.access == (64, 71)    # g_adjacent_ring: bottom edge right to left
    try:
        g.command("build stadium 66 60 h")
        assert False, "second stadium built"
    except CommandError as e:
        assert e.warn == (44,)
    g.command("poseidon on")
    try:                                          # stadium OR museum (g_unique_venue_exists): museum 19:20
        g.command("build museum 80 61")
        assert False, "museum built beside a stadium"
    except CommandError as e:
        assert e.warn == (20,)
    g.demolish(b.id)
    assert "10x5" in g.command("build stadium 60 66 h")
    b = next(b for b in g.buildings.values() if b.key == "stadium")
    g.demolish(b.id)
    old = Building(id=g.next_bid, key="stadium", x=60, y=61, size=5, kind="service")   # a pre-2026-10-28 save
    g.next_bid += 1
    g.buildings[old.id] = old
    g.world.occ[61:66, 60:65] = old.id
    stadium.upgrade(g)
    assert old.misc == dict(w=5, h=10, orient=0) and (g.world.occ == old.id).sum() == 50


def test_avenues():
    """Avenues/boulevards go along a road (docs/logic/avenues.md): the road stays, side strips beside it,
    a side strip between two roads is road, houses reach the road through a strip, clear keeps the road."""
    from sim.game import CommandError
    g = Game("sandbox_open", 1)
    g.command("road 150 140 165 140")
    g.command("road 158 135 158 150")
    assert "13 segments" in g.command("avenue 151 140 163 140")      # side strip north (row 139)
    assert "12 segments" in g.command("boulevard 158 136 158 149")   # not across the avenue
    w = g.world
    assert w.road[140, 151:164].all() and w.avenue[139, 151:164].all() and w.avenue[140, 151:164].all()
    assert w.road[139, 158] and not w.road[139, 157]          # the crossing road continues through the strip
    assert w.avenue[136:150, 157].sum() and not w.road[137, 157] and w.road[137, 158]
    for bad in ("avenue 150 141 150 141", "avenue 150 150 160 150"):
        try:
            g.command(bad)
            assert False, bad
        except CommandError:
            pass
    g.command("build house 152 137")                            # touches only the strip
    h = next(b for b in g.buildings.values() if b.key == "house")
    assert h.access == (153, 140)                              # ring: bottom edge right to left
    g.step(g.rules["ticks_per_day"])
    assert w.des[137, 152] > 0
    assert "1 avenue segments" in g.command("clear 156 139")
    assert w.road[140, 156] and not w.avenue[140, 156] and not w.avenue[139, 156]


def test_old_avenue_blocks_load():
    import tempfile
    from sim.model import Building
    tmp = os.path.join(tempfile.mkdtemp(), "old.pkl")
    g = Game("sandbox_open", 1)
    g.buildings[99] = Building(id=99, key="avenue", x=150, y=150, size=2, kind="decor")
    g.world.occ[150:152, 150:152] = 99
    del g.world.avenue
    t = g.city.treasury
    g.save(tmp)
    g2 = Game.load(tmp)
    os.remove(tmp)
    assert 99 not in g2.buildings and not g2.world.occ[150:152, 150:152].any() and g2.city.treasury == t + 20
    assert g2.world.avenue.shape == (228, 228)


def test_melee_fight():
    """services.md §6.1: watchman vs mugger on one tile: both stand 48 ticks, the mugger dies (128 ticks
    of dying), the watchman walks on."""
    from sim.systems import walkers, crime
    g = play(1)
    h = next(b for b in g.buildings.values() if b.kind == "house" and b.access is not None)
    c = walkers.spawn_roamer(g, h, "mugger")
    d = walkers.spawn_roamer(g, h, "watchman")
    g.sd("criminals", set()).add(c.id)
    t0, here = g.tick, (c.x, c.y)
    assert crime.melee(g, c) and c.anim == d.anim == "fight" and c.busy_until == t0 + 48
    g.step(48)                              # (step runs the walkers due at g.tick, then tick += 1)
    assert (c.x, c.y) == (d.x, d.y) == here and c.anim == d.anim == "fight"
    g.step(1)
    assert c.anim == "die" and c.id in g.walkers and (c.x, c.y) == here
    g.step(30)
    assert d.anim == "" and (d.x, d.y) != here
    g.step(100)
    assert c.id not in g.walkers


def test_health_consequences():
    """Yearly births/deaths by health (0x00566D40), plagued walker meets a healer (0x00448450), infected house
    takes no immigrants (0x004AC810)."""
    from sim.systems import health, walkers
    from sim.model import Walker
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    g.command("road 130 100 150 100")
    for x in range(130, 150, 2):
        g.command(f"build house {x} 98")
    hs = [b for b in g.buildings.values() if b.kind == "house"]
    st = health._st(g)
    for h, t, want in ((95, 95, 53), (55, 55, 50), (35, 35, 50), (35, 25, 49), (5, 5, 48)):
        for b in hs:
            b.occupants = 5
        g.city.population = 50
        st["health"], st["target"] = h, t
        health.year_start(g)
        assert g.city.population == want == sum(b.occupants for b in hs), (h, t, g.city.population)
    b = hs[0]
    p = walkers.spawn(g, b, "plagued")
    health.contact(g, walkers.spawn(g, b, "healer"))
    assert p.id not in g.walkers
    b.misc["infected"], b.occupants, b.pending = 5, 1, 3
    w = Walker(id=10 ** 6, role="immigrant", home=b.id, x=0, y=0, amount=3)
    g.walkers[w.id] = w
    walkers.immigrant_arrive(g, w)
    assert b.occupants == 1


def test_immigrants_counted_when_sent():
    """send_immigrants 0x00486860 adds the people it sends to 0x00FE9194 (this month's newcomers) when they set out;
    the arrival (0x004AC810) only fills the house (bugs.md 282). The undo text names what it removed (bugs.md 280)."""
    from sim import render
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    e = g.world.entry
    g.command(f"road {e[0]} {e[1] - 40} {e[0]} {e[1]}")
    for y in range(e[1] - 38, e[1] - 20, 2):
        g.command(f"build house {e[0] + 1} {y}")
    out = g.command(f"build agora {e[0]} {e[1] - 18} right")
    assert "undone: agora, 3 x empty_stall (4 buildings) removed, no buildings restored" in g.command("undo"), out
    while not any(w.role == "immigrant" for w in g.walkers.values()):
        g.step(1)
    on_way = sum(w.amount for w in g.walkers.values() if w.role == "immigrant")
    assert g.city.immigrants_month == on_way > 0 and g.city.population == 0
    assert f"on the way: {on_way} immigrants" in render.status(g)


def test_trainee_venue_timing():
    """Schools -> venue (services.md 3.1, oracle runs schools-A/B): the day's spawns and the venue finder see the
    shows before the day's decrement (exe steps 31 / 33), whatever the building order; a trainee arrives 15 * len + 2
    ticks after its spawn (hidden 2 ticks, from the start tile's centre to the last one's), after the decrement."""
    from sim.systems import labor, risk, services
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("road 60 71 100 71")
    g.command("build theatre 62 66")                     # built first: its decrement used to come before the school
    g.command("build drama_school 90 68")
    th = next(b for b in g.buildings.values() if b.key == "theatre")
    ds = next(b for b in g.buildings.values() if b.key == "drama_school")
    orig_alloc, orig_risk = labor.allocate, risk.update

    def staffed(g):
        orig_alloc(g)
        th.employees, ds.employees = 18, 10
    labor.allocate, risk.update = staffed, (lambda g: None)
    try:
        tpd = g.rules["ticks_per_day"]
        g.step((31 - g.tick % tpd) % tpd)                # the tick before the day's step 31 (tick % 51 == 32)
        ds.spawn_timer, th.misc["shows"] = 8, 25         # fires today; 25 > 24 before the decrement: refused
        g.step(1)
        assert th.misc["shows"] == 24 and not [w for w in g.walkers.values() if w.role == "trainee"]
        ds.spawn_timer = 8                               # 24 now: accepted
        g.step(tpd)
        t = [w for w in g.walkers.values() if w.role == "trainee"]
        assert len(t) == 1 and t[0].target == th.id and th.misc["shows"] == 23, (t, th.misc)
        start, n, wid = g.tick, len(t[0].path), t[0].id
        while wid in g.walkers:
            g.step(1)
        assert g.tick - start == 15 * n + 2, (g.tick - start, n)
        assert th.misc["shows"] == 32
    finally:
        labor.allocate, risk.update = orig_alloc, orig_risk


def test_games():
    """Panhellenic games (docs/logic/games.md): June begin / can't participate, contestants walk out to the map edge
    and back, the end-of-August result grants Athlete (4) or Scholar (9) monuments; Olympian win -> home games."""
    from sim.systems import games, labor, risk, commemorative
    g = Game("sandbox_open", 1)                                  # no venue: 1000 BC is an Olympian year (-1000 & 3 == 0)
    while g.month_index < 5:
        g.step(51)
    assert any(m.startswith("Olympian Games. Most noble Ruler, you could have been a contender") for _, m in g.city.messages)
    assert games.year_type(g, -999, 5) == 1 and games.year_type(g, -999, 8) == 2 and games.year_type(g, -997, 3) == 3
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("road 60 71 80 71")
    g.command("build college 66 68")
    c = next(b for b in g.buildings.values() if b.key == "college")
    orig_alloc, orig_risk, orig_chance = labor.allocate, risk.update, games.chance

    def staffed(g):
        orig_alloc(g)
        c.employees = 12
    labor.allocate, risk.update = staffed, (lambda g: None)
    c.employees = 12
    try:
        assert games.qualifies(g, 0) and games.qualifies(g, 1) and not games.qualifies(g, 2)
        assert games.chance(g, 1) == 1 and games.chance(g, 0) == 0        # S1 = cov/4 + colleges; (S1+S2+S3)/3
        games.chance = lambda g, t: 100
        while g.month_index < 5:
            g.step(51)
        con = [w for w in g.walkers.values() if w.role == "contestant"]
        assert len(con) == 1 and con[0].state == "wait6" and (con[0].x, con[0].y) == c.access, con
        while g.month_index < 8:
            g.step(51)
        s = games.state(g)
        assert s["result"] == 2 and s["host"] == 1 and s["won_ever"] == 1
        assert commemorative.state(g)["available"][4] == 1                 # Olympian win: Athlete Monument
        assert g.city.messages[-1][1].startswith("Olympian Games conclude. Oh great Ruler, good news abounds!")
        back = [w for w in g.walkers.values() if w.role == "contestant" and w.state == "wait8"]
        assert len(back) == 1 and (back[0].x, back[0].y) == tuple(g.world.exit)
        bid = back[0].id
        for _ in range(16 * 6):                                               # walks home at 15 ticks a tile
            g.step(51)
            if bid not in g.walkers:
                break
        assert bid not in g.walkers
        before = commemorative.state(g)["available"][9]
        g.year0 = g.start_year + 1                                            # 999 BC, an Isthmian year: Scholar
        s["result"] = 2
        games.conclude(g)
        assert commemorative.state(g)["available"][9] == before + 1
        s["host"] = 1                                                         # home games need a staffed stadium
        assert not games.qualifies(g, 0)
        games.cannot(g, 0)
        assert s["host"] == 0 and s["result"] == 0
    finally:
        labor.allocate, risk.update, games.chance = orig_alloc, orig_risk, orig_chance


def test_desirability_as_exe():
    """docs/logic/desirability.md, bugs.md 266: square rings count from 0, rectangle rings from 1; the clamp on every
    add; rubble spreads -2 / -1 around its tile; an unfinished sanctuary spreads nothing; + 10 next to water."""
    import numpy as np
    from sim.model import Building
    from sim.systems import desirability as D
    a = np.zeros((228, 228), np.int16)
    D.spread_rect(a, 100, 100, 102, 105, 12, 2, -2, 6)              # an agora's values: 12 10 10 8 8 6
    assert [int(a[100, 102 + r]) for r in range(1, 8)] == [12, 10, 10, 8, 8, 6, 0]
    a[:] = 0
    D.spread(a, 100, 100, 3, 12, 2, -2, 6)                          # square: 12 12 10 10 8 8
    assert [int(a[100, 102 + r]) for r in range(1, 8)] == [12, 12, 10, 10, 8, 8, 0]
    a[:] = 95
    D.spread(a, 100, 100, 1, 20, 1, 0, 1)
    D.spread(a, 100, 100, 1, -20, 1, 0, 1)
    assert a[100, 101] == 80                                       # 95 + 20 -> 100, then - 20
    g = Game("sandbox_open", 1)
    w = g.world
    w.flags[150, 150] |= 0x1000                                     # rubble
    g._des_sig = None
    D.update(g)
    assert (w.des[150, 150], w.des[150, 151], w.des[150, 152], w.des[150, 153]) == (0, -2, -1, 0)
    b = Building(id=999999, key="sanctuary_athena", x=120, y=120, size=0, kind="monument")
    b.misc.update(w=12, h=16)
    g.buildings[b.id] = b
    g._des_sig = None
    D.update(g)
    assert w.des[118, 125] == 0                                    # under construction: nothing
    b.misc["complete"] = True
    g._des_sig = None
    D.update(g)
    assert w.des[119, 125] == 20 and w.des[118, 125] == 18
    del g.buildings[b.id]
    ys, xs = np.nonzero((w.flags & 0x4) != 0)
    y, x = int(ys[len(ys) // 2]), int(xs[len(xs) // 2])
    h = Building(id=999998, key="house", x=x + 1, y=y, size=1, kind="house")
    assert D.next_to_water(g, h)                                    # its west neighbour is water
    far = Building(id=999997, key="house", x=150, y=150, size=2, kind="house")
    assert not (w.flags[148:154, 148:154] & 0x4).any() and not D.next_to_water(g, far)


def test_palace_fire():
    """Bug 268 (docs/logic/buildings.md "Palace fire and collapse", oracle 1F-palacefire): the palace takes its
    model risks (VeryEasy 0, Normal 5, Impossible 15), burns as one building, past day 16 all 54 tiles turn to
    burning ruins restarting at (seed & 7) + 1, which burn out to rubble; a collapse turns the whole box to rubble;
    superintendents never come to a burning palace; one palace per city; tax clerks only while a palace stands."""
    from sim.systems import risk
    for d, r in (("VeryEasy", 0), ("Normal", 5), ("Impossible", 15)):
        spec = Game("sandbox_open", 1, difficulty=d).cat.spec("palace")
        assert (spec["fire_risk"], spec["damage_risk"], spec["fireproof"]) == (r, r, False), (d, spec)
    g = Game("sandbox_open", 1, difficulty="Impossible")
    for c in ("gods off", "road 150 140 158 140", "build palace 150 141"):
        g.command(c)
    assert "Only one" in str(_raises(lambda: g.command("build palace 160 141")))
    p = next(b for b in g.buildings.values() if b.key == "palace")
    p.fire_risk = 995
    day = g.rules["ticks_per_day"]
    for _ in range(16):
        g.step(day)
        if p.burning:
            break
    assert p.burning and p.misc["fire_c0"] == p.burning <= 8 and p.id in g.buildings
    assert not risk.can_catch_fire(g, p, p.x + 1, p.y + 1)        # a 4x4 piece: lit, fireproof
    assert risk.can_catch_fire(g, p, p.x, p.y)                     # a 1x1 piece: lights it again
    c0 = p.misc["fire_c0"]
    while p.id in g.buildings:
        g.step(day)
    ruins = [b for b in g.buildings.values() if b.kind == "ruin"]
    assert len(ruins) == 54 and all(1 <= r.burning <= 9 for r in ruins)
    assert sorted(r.burning for r in ruins if (r.x, r.y) in [(p.x + 1 + i, p.y + 1 + j) for i in range(4)
                                                             for j in range(4)]) == [c0] * 16
    assert not any(b.key == "palace" for b in g.buildings.values())
    for _ in range(40):
        g.step(day)
    assert not g.buildings and int(((g.world.flags[141:150, 150:156] & 0x1000) > 0).sum()) == 54
    g.command("build palace 150 141")                               # rebuilt on the rubble
    q = next(b for b in g.buildings.values() if b.key == "palace")
    q.damage_risk = 999
    g.step(day)
    assert q.id not in g.buildings and int(((g.world.flags[141:150, 150:156] & 0x1000) > 0).sum()) == 54
    # a burning palace is no superintendent's job (its +0x20 stays 0)
    g = Game("sandbox_open", 1)
    for c in ("gods off", "road 150 140 158 140", "build palace 150 141", "build maintenance 158 141"):
        g.command(c)
    p = next(b for b in g.buildings.values() if b.key == "palace")
    risk.ignite(g, p)
    w = type("W", (), dict(x=152, y=140, wait=100, arrived=g.tick))()
    assert not risk.fire_dispatch(g, w)


def test_parts_fire():
    """Bugs 290-292 (docs/logic/buildings.md §8.2, oracle 1F-ranchburn / 1F-agoraburn): the horse ranch (fireproof:
    no spread) ignites from its own risk, burns with its corral, past day 16 25 ruins (house c0, corral its own +1
    on its first tile), the horses gone; an agora burns with its stalls (no workers), past day 16 its stalls are
    ruins and the road strip stays; a stall reached by fire lights the agora; once lit, never relit by spread;
    an active Hephaestus sanctuary: no fire risk; a non-house with model fire risk 0 resets to 0; manors and
    estates take their own model rows."""
    from sim.systems import risk, agora, services
    day = 51
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    g.command("gods off")
    g.command("build horse_ranch 140 104 n")
    b = next(x for x in g.buildings.values() if x.key == "horse_ranch")
    assert not risk.can_catch_fire(g, b, b.x, b.y)                  # type table fireproof: no spread
    b.fire_risk = 995
    for _ in range(64):
        g.step(day)
        if b.burning:
            break
    assert b.burning and b.misc["no_spread"] and 1 <= b.misc["fire_parts"][0] <= 8 and b.employees == 0
    c0, c1 = b.misc["fire_c0"], b.misc["fire_parts"][0]
    while b.id in g.buildings:
        g.step(day)
    ruins = {(r.x, r.y): r.burning for r in g.buildings.values() if r.kind == "ruin"}
    assert len(ruins) == 25 and ruins[(139, 100)] == c1 + 1 and ruins[(140, 104)] == c0 and ruins[(142, 106)] == c0
    assert ruins[(142, 103)] == c1 and not any(w.role == "horse" for w in g.walkers.values())
    # agora: risk, ignition with its stalls, ruins on the stalls, the strip stays road
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    e = g.world.entry
    for c in ("gods off", f"road {e[0]} {e[1] - 40} {e[0]} {e[1]}", f"build agora {e[0]} {e[1] - 18} right"):
        g.command(c)
    a = next(x for x in g.buildings.values() if x.kind == "agora")
    st = agora.stalls(g, a)
    assert a.misc["strip"] and risk.target(g, *a.misc["strip"][2]) is a and risk.target(g, st[1].x, st[1].y) is a
    assert risk.can_catch_fire(g, a)
    a.fire_risk = 995
    for _ in range(64):
        g.step(day)
        if a.burning:
            break
    assert a.burning and all(risk.on_fire(g, s) and s.misc["fire_c0"] for s in st)
    cs = [s.misc["fire_c0"] for s in st]
    while a.id in g.buildings:
        g.step(day)
    ruins = {(r.x, r.y): r.burning for r in g.buildings.values() if r.kind == "ruin"}
    assert len(ruins) == 4 * len(st) and [ruins[(s.x, s.y)] for s in st] == [c + 1 for c in cs]
    assert not any(s.id in g.buildings for s in st) and all(g.world.road[y, x] for x, y in a.misc["strip"])
    # maintenance on the strip / a stall lowers the agora's risk (building_root)
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    for c in ("gods off", f"road {e[0]} {e[1] - 40} {e[0]} {e[1]}", f"build agora {e[0]} {e[1] - 18} right"):
        g.command(c)
    a = next(x for x in g.buildings.values() if x.kind == "agora")
    a.fire_risk = 900
    sx, sy = a.misc["strip"][2]
    w = type("W", (), dict(x=sx, y=sy, role="maintenance", good=None, id=0, home=None))()
    services.apply(g, w)
    assert a.fire_risk == 900 - 50 * (5 + 4 + 4 + 2)              # 5 strip tiles + the stalls' 10 tiles in the 5x5
    # Hephaestus active: fire risk 0 for non-houses, houses keep theirs; col 6 == 0 resets
    from sim import gods
    g = Game("sandbox_open", 1)
    g.command("build storehouse 140 104")
    s = next(x for x in g.buildings.values() if x.key == "storehouse")
    s.fire_risk = 500
    gods.active, old = (lambda g_, i: i == 9), gods.active
    try:
        for _ in range(64):
            g.step(day)
        assert s.fire_risk == 0 and risk.fire_inc(g, s, g.cat.spec("storehouse")) == 0
    finally:
        gods.active = old
    assert risk.fire_inc(g, s, g.cat.spec("storehouse")) == 10
    g.command("build fountain 150 104")                             # model fire risk 0: reset
    f = next(x for x in g.buildings.values() if x.key == "fountain")
    f.fire_risk = 400
    for _ in range(64):
        g.step(day)
    assert f.fire_risk == 0
    h = type("H", (), dict(kind="house", level=12))()
    assert risk.fire_inc(g, h, g.cat.spec("elite_house")) == 5     # estate (type 14) at Normal; manor 10
    h.level = 11
    assert risk.fire_inc(g, h, g.cat.spec("elite_house")) == 10


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])
