"""Sanctuary and monument construction, commemorative monuments.
Run: python3 tests/test_sim.py monuments (or a test by name: python3 tests/test_sim.py test_NAME)."""

from helpers import Game


def test_sanctuary_construction():
    """Sanctuary built piece by piece as the exe (docs/logic/monuments.md): artisans walk onto the pieces' work tiles,
    carts bring materials per piece (one per day; a 100/400 marble cart shared between 50-unit tiles), tiles before
    the temple, completion message + staff; old saves' pooled materials go to the pieces."""
    from sim.systems import labor, monuments
    g = Game("sandbox_open", 1)
    g.city.treasury = 50000
    for c in ("gods off", "road 86 33 115 33", "build storehouse 87 30", "build artisans_guild 91 31",
              "build sanctuary_dionysus 100 34"):    # gods off: not a friendly god of the sandbox (sim/gods menu)
        g.command(c)
    st = next(b for b in g.buildings.values() if b.key == "storehouse")
    st.goods.update(marble=3200, wood=1600, sculpture=800)
    m = next(b for b in g.buildings.values() if b.key == "sanctuary_dionysus")
    box = {(m.x + i, m.y + j) for i in range(m.misc["w"]) for j in range(m.misc["h"])}
    orig = labor.allocate

    def staffed(g):                          # no population in this test: the guild and storehouse are staffed
        orig(g)
        for b in g.buildings.values():
            if b.key in ("storehouse", "artisans_guild"):
                b.employees = g.cat.spec(b.key)["employees"]
    labor.allocate = staffed
    try:
        seen_tiles, cart_days, shared, order = set(), set(), False, []
        for _ in range(200):
            g.step(g.rules["ticks_per_day"])
            for w in g.walkers.values():
                if w.role == "artisan" and w.state == "work":
                    seen_tiles.add((w.x, w.y))
                if w.role == "cart" and w.target == m.id:
                    assert w.piece >= 0
                    cart_days.add((w.id, g.day))
            if sum(1 for p in m.misc["pieces"] if p["held"].get("marble") == 50) >= 2:
                shared = True
            order.append([p["s"] for p in m.misc["pieces"]])
            if m.misc.get("complete"):
                break
    finally:
        labor.allocate = orig
    assert m.misc.get("complete") and m.misc["built"] == 100 and m.misc["activity"] == 22
    assert any("Sanctuary of Dionysus" in t and "complete" in t for _, t in g.city.messages)
    assert monuments.staffed_ok(g, m)
    assert seen_tiles and seen_tiles <= box | {(x, 33) for x in range(86, 116)}, seen_tiles   # on the monument
    assert shared                                                                             # one cart, two tiles
    tiles = [i for i, p in enumerate(m.misc["pieces"]) if p["c"] in monuments.TILES]
    first_temple = next(k for k, st_ in enumerate(order) if st_[0] > 0)
    assert all(order[first_temple][i] >= 1 for i in tiles)                                    # tiles before the temple
    # an old save: pooled materials, pieces without per-piece fields
    for p in m.misc["pieces"]:
        p.update(s=0)
        for k in ("i", "held", "carts", "resv"):
            p.pop(k)
    m.misc.update(pool={"marble": 450}, built=0, complete=False)
    monuments.adopt(g)
    assert m.misc["pieces"][0]["held"] == {"marble": 400} and "pool" not in m.misc
    assert sum(p["held"].get("marble", 0) for p in m.misc["pieces"]) == 450


def test_monument_window():
    """The window of a monument under construction (0x005813F0 / monument_progress 0x0053ECA0): loads still to
    bring (Ares at 0 % with 400 marble held = 36 slabs, 12 wood, 2 sculptures: oracle sanctuary-window b.bmp), the
    supply message when no storage has the good, and Halt Construction (no new jobs, no carts)."""
    from sim.systems import monuments
    g = Game("sandbox_open", 1)
    g.city.treasury = 50000
    for c in ("gods off", "road 86 33 115 33", "build storehouse 87 30", "build artisans_guild 91 31",
              "build sanctuary_ares 100 34"):    # gods off: not a friendly god of the sandbox (sim/gods menu)
        g.command(c)
    m = next(b for b in g.buildings.values() if b.key == "sanctuary_ares")
    w = monuments.window(g, m)
    assert w["loads"] == dict(wood=12, marble=40, black_marble=0, sculpture=2, orichalc=0) and w["pct"] == 0
    tiles = [p for p in m.misc["pieces"] if p["c"] in monuments.TILES][:8]
    for p in tiles:
        p["held"]["marble"] = 50
    assert monuments.window(g, m)["loads"]["marble"] == 36
    p = monuments.pick_piece(g, m)
    assert monuments.dispatch(g, m, p, "marble", 400) is None and "marble" in m.misc["short"]   # none in storage
    g.command(f"halt {m.x + 1} {m.y + 1}")
    assert monuments.halted(m) and monuments.pick_piece(g, m) is None and monuments.window(g, m)["halted"]
    g.command(f"halt {m.x + 1} {m.y + 1}")
    assert not monuments.halted(m)


def test_commemorative_monuments():
    """Commemorative monuments are granted, then placed at once (docs/logic/monuments.md "Commemorative monuments")."""
    from sim.game import CommandError
    from sim.systems import commemorative
    g = Game("sandbox_open", 1)
    try:
        g.command("build commemorative_monument 140 140")
        raise AssertionError("placed without a grant")
    except CommandError:
        pass
    g.command("grant_monument 6")
    g.command("build commemorative_monument 140 140")
    b = next(x for x in g.buildings.values() if x.key == "commemorative_monument")
    assert b.misc["variant"] == 6 and b.size == 3 and commemorative.state(g)["available"][6] == 0
    assert commemorative.placed(g)[6] == 1
    for _ in range(12):
        commemorative.grant(g, 1)
    assert commemorative.state(g)["available"][1] == 10                      # FUN_00402B00: at most 10 waiting
    s = commemorative.state(g)
    g.city.sentiment = 90
    for _ in range(60):
        commemorative.month(g)
    assert s["available"][6] == 1 and s["happy_months"] == 0


def test_commemorative_grants():
    """Grant rules (docs/logic/monuments.md "Commemorative monuments"): population 100/500/3000 message only,
    1000.. grant a Population Monument once each; 59 happy months do nothing, a sad month restarts the count;
    names 198:v; god statues: size, variant + orientation from the command, the menu order 0x005F41A0."""
    from sim.game import CommandError
    from sim.systems import commemorative as cm
    g = Game("sandbox_open", 1)
    s = cm.state(g)
    for pop, granted in ((99, 0), (100, 0), (999, 0), (1000, 1), (2999, 2), (3000, 2), (5000, 3), (25000, 7), (30000, 7)):
        g.city.population = pop
        cm.day(g)
        assert s["available"][1] == granted, (pop, s["available"][1])
    texts = [m for _, m in g.city.messages]
    # one message per milestone, the exe's own (0x4DA + 6 k title, + 1 announcement); the grant adds none
    assert len(texts) == 10 and not any("granted" in m for m in texts)
    assert texts[0] == "Population milestone: 100 people. Our fledgling village now boasts a population of 100 people."
    assert texts[4].startswith("Population milestone: 3,000 people. For the first time")
    assert sum("Commemorative Monument" in m for m in texts) == 7         # the granting ones name the monument
    g.city.sentiment = 81
    for _ in range(59):
        cm.month(g)
    g.city.sentiment = 80
    cm.month(g)
    assert s["happy_months"] == 0 and s["available"][6] == 0          # sentiment < 81 restarts the count
    g.city.sentiment, n = 81, len(g.city.messages)
    for _ in range(60):
        cm.month(g)
    assert s["available"][6] == 1 and len(g.city.messages) == n + 1     # 0x516 / 0x517 only
    assert g.city.messages[-1][1].startswith("Happiness monument available. It is truly a golden time")
    assert cm.name(22) == "Large Zeus Statue" and cm.name(63) == "Small Atlas Statue" and cm.size(36) == 4
    g.command("grant_monument 22")
    g.command("grant_monument 11")
    assert [r[0] for r in cm.menu(g)] == [1, 6, 11, 22]              # small statues before the large ones
    g.city.treasury = 50000
    g.command("build commemorative_monument 140 140 22 3")
    b = next(x for x in g.buildings.values() if x.key == "commemorative_monument")
    assert b.size == 4 and b.misc["variant"] == 22 and b.misc["orient"] == 3 and int(g.world.occ[143, 143]) == b.id
    try:
        g.command("build commemorative_monument 150 140 22")
        raise AssertionError("placed a second Large Zeus Statue with none waiting")
    except CommandError:
        pass
    from sim.export import _building
    assert _building(g, b)["orient"] == 3 and _building(g, b)["variant"] == 22


def test_commemorative_empire_grants():
    """Conquest (0x00480240: an ally or rival conquered -> 5) and Diplomacy (events_cities_month 0x00473680 subtype 9,
    a rival becomes an ally -> 8) monuments, through the empire module."""
    from sim.systems import commemorative as cm
    from sim.empire import relations, war
    g = Game("sandbox_open", 1)
    g.command("empire on")
    e = g.empire
    rivals = [c for c in e.cities.values() if c.cls() == "rival"]
    assert rivals, "sandbox empire has no rival"
    r = rivals[0]
    n = len(g.city.messages)
    assert relations.status_change(g, r, 9) and r.relation == "ally" and cm.state(g)["available"][8] == 1
    assert len(g.city.messages) == n + 1 and g.city.messages[-1][1].startswith(f"{r.name} becomes ally. Greetings")
    assert "[" not in g.city.messages[-1][1] and r.leader in g.city.messages[-1][1]
    assert not relations.status_change(g, r, 9) and cm.state(g)["available"][8] == 1   # not a rival any more
    n = len(g.city.messages)
    war.conquer(g, r, r.cls())
    assert r.relation in ("vassal", "colony") and cm.state(g)["available"][5] == 1
    assert len(g.city.messages) == n + 1 and g.city.messages[-1][1].startswith(f"You conquered {r.name}! Most martial")
    war.conquer(g, r, r.cls())                                       # a vassal: no monument
    assert cm.state(g)["available"][5] == 1
    from sim.military import invaders                                # army_withdraws 0x00481E80: Victory Monument
    for bribed, head in ((False, "Invasion force defeated! It's time to celebrate, Ruler!"),
                         (True, "Invaders paid off! It's time to celebrate, Ruler!")):
        i = invaders.invade(g, None)
        n = len(g.city.messages)
        invaders.withdraw(g, i, invaders.invasions(g)[i], bribed=bribed)
        assert len(g.city.messages) == n + 1 and g.city.messages[-1][1].startswith(head), g.city.messages[-1]
        assert "Commemorative Monument" in g.city.messages[-1][1] and "[" not in g.city.messages[-1][1]
    assert cm.state(g)["available"][2] == 2


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])
