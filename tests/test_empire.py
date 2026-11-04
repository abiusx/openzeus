"""World map and empire: cities, diplomacy, war, world files, troops abroad.
Run: python3 tests/test_sim.py empire (or a test by name: python3 tests/test_sim.py test_NAME)."""
import os
import sys

from helpers import ROOT, Game


def test_empire_scenario():
    """sim/empire: the sandbox's own empire (docs/logic/world-map.md): 8 cities from the .map, trade only
    with trading partners, no post for a rival, `empire off` = data/trade.json partners."""
    from sim.systems import trade
    from sim import live
    g = Game("sandbox_open", 1)
    e = g.empire
    names = {c.name: c for c in e.cities.values()}
    assert sorted(names) == ["Aulis", "Delos", "Elis", "Miletos", "Olympia", "Sparta", "Thasus", "Tiryns"]
    assert names["Elis"].kind == "colony" and names["Elis"].tribute["mode"] == 1          # colony pays (0x0042E130)
    assert names["Miletos"].relation == "vassal" and names["Miletos"].tribute["mode"] == 0  # "Suspended" (seen)
    assert names["Elis"].buys == {"wood": 12, "fleece": 36, "armor": 12} and names["Elis"].sells == {"wine": 24}
    assert names["Sparta"].attitude == 25 and not names["Sparta"].trading()
    assert names["Thasus"].trading() and not names["Thasus"].exists()                    # distant: trades, no diplomacy
    menu = {m["city"] for m in live.trade_menu(g)}
    assert "Sparta" not in menu and "Delos" not in menu and "Elis" in menu and "Miletos" in menu
    try:
        g.command("build trading_post 143 107 Sparta")
        raise AssertionError("a post for a rival")
    except Exception as ex:
        assert "does not trade" in str(ex), ex
    assert e.route(0, 3) and len(e.route(0, 1)["dots"]) == 11                             # = the map's +0x134
    from sim import empire
    w = empire.export(g)
    assert {r["b"] if r["a"] == 0 else r["a"] for r in w["routes"]} == {1, 2, 4, 6, 7}     # partners only
    g2 = Game("sandbox_open", 1)
    g2.command("empire off")
    assert trade.partners(g2)[0]["name"] == "Sardis"
    from sim import empire
    off = empire.export(g2)                      # play mode's off screen (bugs.md 125): picture + partners, no markers
    assert off["off"] and off["picture"] == g.empire.picture and off["partners"][0]["name"] == "Sardis"
    assert "cities" not in off


def test_empire_diplomacy():
    """Gift formula (0x0046FC00), request cost/fatigue (0x0047FF80), tribute into storage (0x00474F60)."""
    from sim.empire import diplomacy
    g = Game("sandbox_open", 1)
    t = g.empire.find("Tiryns")
    g.city.treasury = 15000
    assert diplomacy.receive_gift(g, t, "drachmas", 500) == 1          # 0.2 * (1/3) * sqrt(500) = 1.49
    m = g.city.messages[-1][1]                                           # the city's thanks (bugs.md 328)
    assert m.meta["title"] == "Tiryns thanks you for money" and m.meta["popup"], m.meta
    assert diplomacy.receive_gift(g, t, "olive_oil", 8, "medium") == int(0.3 * 0.4 * (145 ** 0.5) * 8)   # it buys oil: 11
    m = g.city.messages[-1][1]
    assert m.meta["title"].startswith("Tiryns grateful for") and "generous gift of" in m.meta["body"], m.meta
    assert t.gift_fatigue["olive_oil"] == 12
    a0 = t.attitude
    out = g.command("request Tiryns fleece")
    assert "16 loads" in out and t.request_fatigue["fleece"] == 15 and t.attitude == a0 - 10
    s = g.empire.find("Sparta")
    assert diplomacy.can_request(g, s, "armor") == (1, 3)                # a rival's "demand"
    assert diplomacy.can_request(g, s, "troops")[0] == -1
    g.command("months 13")                                              # January: Elis' tribute, no room -> lost
    assert any("Tribute paid by Elis" in m and "unable to accept" in m for _, m in g.city.messages)
    offers = g.command("offers")                                        # tribute never waits (last-chance rules);
    assert "Tribute" not in offers and "Tiryns grants" in offers        # the granted fleece waits for an answer


def test_empire_history_rows():
    """World-map history rows as the exe writes them (FUN_0042EEC0 records, text FUN_004669E0): the eventmsg
    *_history phrase, [city_affected] = 91:relation ("this city" for the city's own record), [itemshort] = 23:item;
    oracle 1F-wmdlg2 history2 / 1F-strike history3."""
    from sim.empire import diplomacy, relations
    g = Game("sandbox_open", 1)
    t, a = g.empire.find("Tiryns"), g.empire.find("Aulis")
    g.city.treasury = 15000
    g.command("request Tiryns drachmas")
    assert t.history[-1][1:] == ("You requested drachmas from this city", -10)
    assert a.history[-1][1:] == ("You requested drachmas from an ally", -2)          # same class: 0xC75, relation 1
    diplomacy.receive_gift(g, t, "olive_oil", 8)
    assert t.history[-1][1] == "You gave much needed Olive oil to this city"         # 0xBF2 (it buys oil)
    diplomacy.receive_gift(g, t, "drachmas", 10)                                      # a 0 gain still writes the row
    assert t.history[-1][1:] == ("You made a gift of cash to this city", 0)
    g.command("empire army Tiryns 20")
    g.command("empire attitude Tiryns 100")
    g.command("request Tiryns strike Sparta")
    assert t.history[-1][1:] == ("You relied on this city for a military strike", -50)
    assert relations.status_change(g, t, 0) and t.history[-1][1:] == ("Suspended trade", 0)


def test_empire_war():
    """Raid and conquest (0x00461540 tiers), ally strike (0x00480A00), companies away and back."""
    g = Game("sandbox_open", 1)
    g.companies = {1: {"type": "hoplite", "members": 8}, 2: {"type": "horseman", "members": 8}}
    g.command("empire army Sparta 10")
    t0 = g.city.treasury
    g.command("raid Sparta")
    assert all(c.get("away") for c in g.companies.values())
    g.command("months 6")
    s = g.empire.find("Sparta")
    assert any("Battle at Sparta: your 24 against 10: victory" in m for _, m in g.city.messages)
    assert "Accept" not in g.command("offers") and "accept" in g.command("offers")   # the plunder waits for an answer
    g.command("offer accept")
    assert g.city.treasury == t0 + 1800                                 # (wealth 2 + 1) * 3 * 200 drachmas
    assert not any(c.get("away") for c in g.companies.values())
    g.companies = {1: {"type": "hoplite", "members": 8}}               # no palace: companies disband at home
    g.command("conquer Delos")                                          # army 0: easy win, by sea
    g.command("months 8")
    d = g.empire.find("Delos")
    assert d.relation == "vassal" and d.tribute["mode"] == 1 and d.trading() and d.attitude >= 0
    assert g.empire.find("Aulis").attitude == 50                        # other allies unaffected by a rival's fall


def test_world_file():
    """World files (docs/world-format.md, sim/empire/world.py): data/world/partners.json loads, bad files give
    field-named errors, and `empire on partners --migrate` re-binds a post (built with empire off) by name."""
    import json
    import tempfile
    from sim.empire import world
    from sim.systems import trade
    e = world.load_world("partners")
    assert e.picture == 8 and len(e.cities) == 9 and e.player().name == "Ephesus"
    assert all(c.trading() for c in e.cities.values() if c.kind != "player")
    assert len(e.routes) == 8 and all(r["b"] == 0 and r["dots"][-1] != r["dots"][0] for r in e.routes)
    bad = dict(format="world", version=1, picture=12, cities=[
        dict(name="Home", kind="player", map=dict(x=10, y=10)),
        dict(name="A", kind="foe", buys={"gold": 3}, map=dict(x=900, y=10, label="up")),
        dict(name="Home", map=dict(x=20, y=20), path=[[1]])])
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(bad, f)
    try:
        world.load_world(f.name)
        raise AssertionError("bad world loaded")
    except world.WorldError as ex:
        msg = str(ex)
        for part in ("picture: 12 not in 1..10", "cities[1] (A).kind: 'foe'", "unknown good 'gold'",
                     "cities[1] (A).map x: 900", "map.label: 'up'", "'Home' appears twice", "path[0]: must be [x, y]"):
            assert part in msg, (part, msg)
    finally:
        os.unlink(f.name)
    g = Game("sandbox_open", 1)
    g.command("empire off")
    g.city.treasury = 10 ** 6
    g.command("build trading_post 143 107 Babylon")
    b = next(b for b in g.buildings.values() if b.kind == "trade")
    assert trade.partners(g)[b.misc["partner"]]["name"] == "Babylon"
    try:
        g.command("empire on partners")
        raise AssertionError("switched with a post and no --migrate")
    except Exception as ex:
        assert "--migrate" in str(ex), ex
    out = g.command("empire on partners --migrate")
    assert "1 trade buildings re-bound" in out, out
    assert trade.partners(g)[b.misc["partner"]]["name"] == "Babylon" and b.misc["partner"] == 2
    assert g.empire.source == "data/world/partners.json"


def test_troops_abroad():
    """1L-5 a call for troops answered with companies (tools/oracle_troops.py; oracle 1L5-troopsgo, "See a working
    city" with an injected call by Mantineia attacked by Nemea, due June, lead 1): the 3 horseman companies go (state
    6, countdown 2 = the travel months, flag 0x200: they arrive after the deadline), the June pass fights and wins
    (state 7, "Mantineia regards you more highly"), countdown 2 -> 1, then home in August (state 10, active 0,
    "Victorious warriors return!", the companies home with 8 each); the exe's record and companies the same month
    by month."""
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import oracle_troops as O
    from sim.empire import requests
    from sim.systems import military
    g, ev = O.ours_game()
    mon = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    g.step(mon - g.tick % mon)
    assert "Mantineia under attack" in str(g.city.messages[-1][1]) and ev["state"] == 0
    requests.dispatch(g, ev)
    comps = {k: c for k, c in military.companies(g).items() if c["type"] == "horseman"}
    assert (ev["state"], ev["countdown"], ev["flags"]) == (6, 2, 0x200) and all(c.get("away") for c in comps.values())
    seen = len(g.city.messages)
    want = [(7, 2, 1, "Mantineia regards you more highly"), (7, 1, 1, None), (10, 0, 0, "Victorious warriors return")]
    for st, cd, act, msg in want:
        g.step(mon)
        new = " | ".join(str(m) for _, m in g.city.messages[seen:])
        seen = len(g.city.messages)
        assert (ev["state"], ev["countdown"], ev["active"]) == (st, cd, act), (g.date(), ev["state"], ev["countdown"])
        assert msg is None or msg in new, new
    assert all(c["members"] == 8 and not c.get("away") for c in military.companies(g).values() if c["type"] == "horseman")


def test_troops_march():
    """bugs.md 369 (oracle 1L5-troopsmarch, tools/oracle_troops.py march: 39 of 39 samples equal): the 24 horsemen
    appear on the road tiles of the houses soldier_home_house picks (round robin; the houses right of the avenue
    take their bottom row's segment road, g_adjacent_ring), 8 + 8 + 4 + 4, and reach the land exit on route-mode-0
    routes (8-way trace, over the ramps) by the exe's tick."""
    import sys
    from collections import Counter
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import oracle_troops as O
    from sim.empire import requests
    g, ev = O.ours_game()
    mon = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    g.step(mon - g.tick % mon)
    requests.dispatch(g, ev)
    o = g.world.origin
    at = lambda: Counter((w.x - o[0], w.y - o[1]) for w in g.walkers.values() if w.role == "horseman")
    assert at() == {(57, 39): 8, (57, 45): 8, (57, 51): 4, (57, 33): 4}, at()
    g.step(666)                                   # exe tick 700 (dispatch at 34): the last 8 at (127, 61)
    assert at() == {(127, 61): 8}, at()
    g.step(20)
    assert not at()


def test_empire_city_names_with_spaces():
    """bugs.md 449 (user 11-04: an army sent to Mt. Cithaeron did nothing): raid / conquer / gift and the "with ALLY"
    of a city whose name has a space; the army dialog sends `conquer Mt. Cithaeron with Knossos companies ...`."""
    from sim.empire import _join_city

    class C:
        def __init__(self, n):
            self.name = n

    class E:
        cities = {0: C("Mt. Cithaeron"), 1: C("Knossos"), 2: C("Mt. Pelion")}
    assert _join_city(E, ["Mt.", "Cithaeron", "with", "Knossos"]) == ["Mt. Cithaeron", "with", "Knossos"]
    assert _join_city(E, ["Knossos", "wine"]) == ["Knossos", "wine"]
    assert _join_city(E, ["Mt.", "Pelion"]) == ["Mt. Pelion"]


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])


def test_goods_flags_load_rebuild():
    """Bug 472: a status change that closes trade zeroes the city's buys/sells flags (event_city_status_change
    0x00473680); conquest (0x00480240) reopens trade without them, so no traders come (oracle: flags poked to 0 with
    trade open -> no traders); every saved-game load (FUN_00510ED0 -> FUN_00461360) and episode start rebuilds them
    from the lists for every city (oracle: back after Load)."""
    import tempfile
    from sim.empire import relations, war
    from sim.systems import trade
    g = Game("sandbox_open", 1)
    t = g.empire.find("Tiryns")
    lists = (dict(t.buys), dict(t.sells))
    assert relations.status_change(g, t, 10)                 # becomes a rival: trade closed, flags zeroed
    assert t.relation == "rival" and not t.goods_flags and trade.partners(g)[t.id]["buys"] == {}
    war.conquer(g, t, "rival")                               # a vassal, trading, flags still zero
    assert t.relation == "vassal" and t.trading() and not t.goods_flags
    assert (trade.partners(g)[t.id]["buys"], trade.partners(g)[t.id]["sells"]) == ({}, {})
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.pkl")
        g.save(p)
        h = type(g).load(p)
    u = h.empire.find("Tiryns")
    assert u.goods_flags and (trade.partners(h)[u.id]["buys"], trade.partners(h)[u.id]["sells"]) == lists
    assert all(c.goods_flags for c in h.empire.cities.values())        # rivals too: city_buys gates on partner
    from sim.empire import status_events
    a = h.empire.find("Aulis")
    status_events.conquered(h, a, h.empire.find("Sparta"))   # FUN_0046EAC0: a rival now, its flags untouched
    assert a.relation == "rival" and a.goods_flags
