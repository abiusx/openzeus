"""Campaigns: episodes, allowed buildings, goals, the campaign module and its screens, .sav import.
Run: python3 tests/test_sim.py campaign (or a test by name: python3 tests/test_sim.py test_NAME)."""
import os
import pickle

from helpers import ROOT, Game, play, _campaign, _ep, _raises


def test_episode_new_city():
    """1L-2: a new game from an episode (sim/episode.py new_city, episode_start_load kind 0): the .pak's map
    container by index (mapfile.read_file(pak)[0] is the last map of a multi-map .pak), start year, funds x
    difficulty, the episode's events and god block, the map's empire with the episode's player city."""
    from sim import episode, world
    a = _campaign("zeus_and_europa")
    pak = os.path.join(ROOT, a["source"])
    terrain = lambda name: [b["data"] for b in world.read_map(name)[1] if b["rank"] == 6][0]   # noqa: E731
    assert terrain(pak + "#0") != terrain(pak)                         # the parent city, not the colony
    assert terrain(pak + "#1") == terrain(pak)                         # read_file's first = the last map, Cydonia
    ep = _ep(a, 0)
    g = episode.new_city(a["source"] + "#0", ep, difficulty="Normal")
    assert g.date() == "Jan 1150 BC" and g.start_year == g.scenario_year == -1150
    assert g.city.treasury == 5000 * g.rules.get("start_funds_pct", 100) // 100
    assert len(g.scenario.events) == len(ep["events"]) and g.scenario.gods["max_sanctuaries"] == 0
    p = g.empire.player()
    assert (p.name, p.resources, p.sells, p.wealth, p.attitude) == (
        "Thebes", ep["player_city"]["resources"], {"marble": 36, "olive_oil": 24}, 2, 50)
    assert g.allowed == ep["allowed_raw"] and g.games_year == 0 and "tutorial" not in g.__dict__
    g.step(816 * 13)                                                   # a year runs: the counters roll
    assert g.year == -1149 and g.year_stats["year"] == -1150
    g2 = pickle.loads(pickle.dumps(g))
    assert g2.allowed == g.allowed and g2.date() == g.date()


def test_allowed_buildings():
    """1L-2: the allowed table + buildings_availability 0x00402B80 (data/allowed.json): refused with a message;
    open play (no table) unchanged."""
    from sim import episode, allowed
    a = _campaign("zeus_and_europa")
    ep = _ep(a, 0)
    g = episode.new_city(a["source"] + "#0", ep, difficulty="Normal")
    off = allowed.unavailable(g)
    # flag 0 (mint, hunting lodge ...), raw goods the city lacks (carrots, wood), Poseidon, elite housing flag 43
    for k in ("mint", "carrot_farm", "onion_farm", "timber_mill", "elite_house", "race_track", "winery", "stadium"):
        assert k in off, k
    for k in ("house", "wheat_farm", "olive_tree", "sheep_farm", "goat_farm", "marble_quarry", "oil_press", "palace",
              "agora", "granary", "fountain", "wall", "theatre"):
        assert k not in off, k
    assert "not available in this episode" in str(_raises(lambda: g.command("build mint 100 100")))
    assert "not available in this episode" in str(_raises(lambda: g.command("build elite_house 100 100")))
    g.allowed[43] = 1
    assert "elite_house" not in allowed.unavailable(g)
    g.allowed[33] = 0                                                  # walls go through their own command
    assert "not available" in str(_raises(lambda: g.command("wall 100 100 104 100")))
    o = Game("sandbox_open", 1)
    assert allowed.unavailable(o) is None and allowed.check(o, "carrot_farm") is None
    assert "allowed" not in o.__dict__


def test_open_plays():
    """User 10-31 (the decision log "Two open plays"): sandbox / sandbox2 start as the exe starts them, with their
    episode (}Open Play Sandbox.pak: the player city's raw goods; oracle runs sandbox-food / sandbox2-food: Farms =
    Wheat Farm only, no urchin quay; sandbox2 no fishery either); sandbox_open / sandbox2_open (ours): the same map,
    no episode, everything buildable, the state of a sandbox game before 10-31 (map name included); saves made
    before (no allowed table) stay unrestricted."""
    from sim import allowed, export, world
    g = Game("sandbox", 1)
    off = allowed.unavailable(g)
    for k in ("carrot_farm", "onion_farm", "urchin_quay"):
        assert k in off and "not available" in str(_raises(lambda: g.command(f"build {k} 100 100"))), k
    for k in ("wheat_farm", "fishing_wharf", "hunting_lodge", "sheep_farm", "goat_farm", "olive_tree", "grapevine",
              "growers_lodge", "food_vendor", "timber_mill", "foundry", "marble_quarry", "horse_trainer", "mint"):
        assert k not in off, k
    assert g.empire.player().resources == ["fish", "meat", "cheese", "wheat", "wood", "bronze", "marble", "grapes",
                                            "olives", "fleece", "horses"]
    assert g.episode == {"slot": 0, "start": "new_city"} and "carrot_farm" in export.snapshot(g)["episode"]["unavailable"]
    assert (g.date(), g.city.treasury) == ("Jan 1000 BC", 15000)
    s2 = allowed.unavailable(Game("sandbox2", 1))
    assert {"carrot_farm", "onion_farm", "urchin_quay", "fishing_wharf"} <= set(s2) and "hunting_lodge" not in s2
    for m in ("sandbox_open", "sandbox2_open"):
        o = Game(m, 1)
        assert o.map_name == world.play(m)[0] and allowed.unavailable(o) is None and "allowed" not in o.__dict__
        assert "episode" not in export.snapshot(o) and allowed.check(o, "carrot_farm") is None
    old = pickle.loads(pickle.dumps(Game("sandbox_open", 1)))       # a pre-10-31 save: map "sandbox", no table
    assert old.map_name == "sandbox" and allowed.check(old, "urchin_quay") is None


def test_episode_sanctuaries_tutorial():
    """1L-2: max sanctuaries and the gods that may get one from the episode's god block (sim/gods menu), a
    continue start (resume: scenario_gods_apply), the tutorial build categories / world map button."""
    from sim import episode, gods, export
    a = _campaign("sanctuary")
    g = episode.new_city(a["source"] + "#0", _ep(a, 0), difficulty="Normal")
    assert gods.menu(g) == [] and "sanctuary" in str(_raises(lambda: g.command("build sanctuary_zeus 100 100")))
    episode.resume(g, _ep(a, 1))
    assert g.episode["start"] == "continue" and gods.menu(g) == ["sanctuary_dionysus"]
    assert gods.state(g)["max_sanct"] == 1
    h = _campaign("housing")
    t = episode.new_city(h["source"] + "#0", _ep(h, 0), difficulty="Normal")
    assert t.tutorial == dict(build_categories=[1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0], world_map_button=0)
    assert t.games_year == -1
    s = export.snapshot(t)
    assert s["episode"]["tutorial"]["world_map_button"] == 0 and "mint" in s["episode"]["unavailable"]
    assert "episode" not in export.snapshot(Game("sandbox_open", 1))


def test_episode_rebase_and_carry():
    """1L-2: event_rebase_month 0x00467930 (month + current month, above 11: year + 1 and month - 11), the colony
    start (parent.dat's partial merge: empire, treasury, date; parent kind 3, colony kind 0) and the return
    (episode_end_save_parent 0x0052D2B0: colony kind 1 paying tribute, the parent city as it was)."""
    from sim import episode, scenario
    a = _campaign("zeus_and_europa")
    g = episode.new_city(a["source"] + "#0", _ep(a, 0), difficulty="Normal")
    g.step(816 * 17 + 3)                                               # Jun 1149 BC
    assert g.date() == "Jun 1149 BC"
    g.city.treasury = 12345
    ep = _ep(a, 10)
    c = episode.colony(g, a["source"] + "#1", ep, 1)
    assert c.date() == "Jun 1149 BC" and c.city.treasury == 12345 and c.scenario_year == -1149
    assert c.empire.player().name == "Cydonia" and c.empire.cities[0].kind == "parent"
    assert g.empire.player().name == "Thebes"                         # the parent's own empire untouched
    assert c.empire.player().resources == ep["player_city"]["resources"]
    ref = scenario.from_episode(c, ep)                                # the same records, not rebased
    for r, ev in zip(ref.events, c.scenario.events):                  # rebased by June (5) and year offset 1
        if r["flags"] & 0x20001:
            assert (ev["month"], ev["year"]) == (r["month"], r["year"])
            continue
        m, y = r["month"] + 5, r["year"] + 1
        assert (ev["month"], ev["year"]) == ((m - 11, y + 1) if m > 11 else (m, y))
    ev = scenario.blank(0)
    ev.update(month=8, year=2, flags=0)
    c.scenario.events = [ev]
    scenario.rebase(c)                                                # 8 + 5 = 13 -> year + 1, month 2 (sic)
    assert (ev["month"], ev["year"]) == (2, 2 + 1 + 1)
    c.step(816 * 3)
    c.city.treasury = 777
    p = episode.back_from_colony(g, c, 1)
    assert p.date() == c.date() == "Sep 1149 BC" and p.city.treasury == 777
    assert p.empire.player().name == "Thebes" and p.empire.cities[1].kind == "colony"
    assert p.empire.cities[1].tribute["mode"] == 1
    p.step(816)
    assert p.date() == "Oct 1149 BC"


def test_episode_continue_resets():
    """The continue start (episode_start_load kind 2, docs/logic/episode-transition.md): g_events replaced (the
    run-time world-map records gone), the message list emptied (FUN_00522230), the sticky goods / food marks cleared
    and rebuilt (FUN_0050D6C0 + rebuild_goods_lists), army_months = 0 and the enemy figures deleted (FUN_0042C4E0),
    the year's starting treasury = the treasury; no message for the removed heroes' halls."""
    from sim import episode, empire
    from sim.empire import events
    from sim.military import invaders
    a = _campaign("zeus_and_europa")
    g = episode.new_city(a["source"] + "#0", _ep(a, 0), difficulty="Normal")
    g.step(816 * 2 + 5)
    g.message("an old message")
    events.add(g, type="request", city=1, item="wheat", amount=4, countdown=6, deadline=12)
    g.goods_listed = {"bronze", "armor"}                              # marks this city's lists would not set
    g.city.foods_listed.update({"carrots", "meat"})
    inv = invaders.invade(g, None, strength=16, quiet=True)
    g.step(400)
    assert invaders.invasions(g) and any(w.role in invaders.TYPES for w in g.walkers.values())
    g.city.treasury = 4321
    episode.resume(g, _ep(a, 1))
    assert g.empire.events == [] and not any("old message" in str(m) for _, m in g.city.messages)
    assert not any("Hall" in str(m) for _, m in g.city.messages)
    assert "bronze" not in g.goods_listed and "armor" not in g.goods_listed and "wine" in g.goods_listed
    assert not g.city.foods_listed
    assert not invaders.invasions(g) and not invaders.ecomps(g)
    assert not any(w.role in invaders.TYPES + ("enemy_transport", "enemy_warship") for w in g.walkers.values())
    assert g.year_treasury == g.start_funds == 4321
    g.step(816 * 2)                                                   # runs on without the old records
    p = g.empire.player()
    p.active, p.visible = False, False                                # FUN_00510ED0: the player's city active, visible
    empire.loaded(g)
    assert p.active and p.visible
    del inv


def test_episode_colony_carry():
    """The colony start carries the world cities, routes, prices, treasury and date and nothing else (picture,
    months count, peak strength, totals and g_events come with the colony map / are new); the return carries the
    cities, prices, traded loads back and keeps the parent's own (oracle 1L-europa-colony 620, 1L3-europa-return
    920: picture 6 -> 1 -> 6, months 2 -> 0 -> 3). A second sack by a city the player already pays loses (tribute
    mode 2 carried with the cities, 0x00482200); its army driven off ends the tribute (0x00481E80)."""
    from sim import episode
    from sim.empire import events
    from sim.systems import trade
    a = _campaign("zeus_and_europa")
    g = episode.new_city(a["source"] + "#0", _ep(a, 0), difficulty="Normal")
    g.step(816 * 3 + 2)
    e = g.empire
    e.months, e.peak_strength, e.totals["gifts_given"] = 40, 77, 500
    events.add(g, type="request", city=1, item="wheat", amount=4, countdown=6, deadline=12)
    trade.set_price(g, "wheat", 55)
    pic = e.picture
    c = episode.colony(g, a["source"] + "#1", _ep(a, 10), 1)
    ce = c.empire
    assert c.prices["wheat"] == 55 and ce.events == [] and ce.months == 0 and ce.peak_strength == 0
    assert ce.totals["gifts_given"] == 0 and ce.picture != pic and ce.routes == e.routes
    assert c.year_treasury == c.city.treasury == g.city.treasury
    trade.set_price(c, "wheat", 61)
    ce.months, ce.totals["gifts_given"] = 3, 9
    trade.state(c)["used"][2] = {"wine": 3}
    c.step(816)
    p = episode.back_from_colony(g, c, 1)
    pe = p.empire
    assert p.prices["wheat"] == 61 and pe.months == 40 and pe.totals["gifts_given"] == 500 and pe.picture == pic
    assert pe.peak_strength == 77 and pe.cities[1].kind == "colony" and trade.state(p)["used"][2] == {"wine": 3}
    # the sack rule (tribute mode, not a separate mark)
    from sim.military import invaders
    rival = next(x for x in pe.cities.values() if x.kind == "foreign")
    inv = dict(id=1, city=rival.id, name=rival.name, companies=[], nation=0, start=p.tick)
    invaders.invasions(p)[1] = inv
    invaders.defeat(p, 1, inv)                                        # first: the player pays it
    assert rival.tribute["mode"] == 2 and not p.mil.get("game_lost")
    invaders.invasions(p)[2] = inv2 = dict(inv, id=2)
    invaders.withdraw(p, 2, inv2)                                     # driven off: the tribute ends
    assert rival.tribute["mode"] == 0
    rival.tribute["mode"] = 2                                         # paying it (e.g. carried into a colony)
    invaders.invasions(p)[3] = inv3 = dict(inv, id=3)
    invaders.defeat(p, 3, inv3)
    assert p.mil.get("game_lost")


def test_goal_measurements():
    """1L-2: the goal checker's measurements (sim/measure.py, goal_met 0x00526FC0 and its counters)."""
    from sim import measure
    g = play(1)
    m = measure.values(g)
    assert m["population"] == g.city.population and m["treasury"] == g.city.treasury
    assert sum(m["housing"].values()) == sum(b.occupants for b in g.buildings.values() if b.kind == "house")
    assert measure.people_at_least(g, 2) == sum(m["housing"].values())
    assert set(m["units"]) == {11, 12, 13, 57} and m["units"][11] >= m["units"][12] >= m["units"][13]
    assert m["hippodrome_length"] is None and "year_stats" not in g.__dict__
    assert "population" in g.command("goals")


def test_campaign_isolated():
    """1L-3: the core never imports the campaign module (only the front ends dispatch to it: the CLI sim/__main__.py
    and, since 1L-4, the live server sim/live.py for the play-mode screens; the month check reaches the game through
    sim/hooks.py by name)."""
    import re
    bad = []
    for d, _, fs in os.walk(os.path.join(ROOT, "sim")):
        if os.sep + "campaign" in d:
            continue
        for f in fs:
            p = os.path.join(d, f)
            if f.endswith(".py") and not p.endswith((os.path.join("sim", "__main__.py"), os.path.join("sim", "live.py"))):
                if re.search(r"^\s*(from\s+(sim\.|\.+)campaign|import\s+sim\.campaign)", open(p).read(), re.M):
                    bad.append(p)
    assert not bad, bad


def test_campaign_goal_rules():
    """1L-3: scenario_goals_check 0x00526990 / goal_met 0x00526FC0 on hand-made goal tables: AND of the normal goals;
    type 12 overwrites the result (a time limit after other goals ignores them), its year reached loses (0xB95);
    type 13 wins when its year comes; 36 months in debt loses (0xB91); no goals never win; the type-2 counter
    (FUN_00525FB0) gives a god goal its god and an 'any god' goal the other finished gods; type 14 with no good is
    met; Rule of a city id out of 0..21 is met."""
    from sim.campaign import goals as G
    g = Game("sandbox_open", 1)
    g.year0, g.scenario_year = g.start_year, g.start_year
    rec = lambda t, *v: dict(type=t, v=(list(v) + [0] * 6)[:6], other=0, good=None)     # noqa: E731
    pop = g.city.population
    assert G.check(g, [rec(0, pop)]) == (1, None)
    assert G.check(g, [rec(0, pop + 1)]) == (0, None)
    assert G.check(g, []) == (0, None)                                   # count 0: never won
    assert G.check(g, [rec(0, pop + 1), rec(12, 5)]) == (1, None)        # sic: the time limit resets the AND
    assert G.check(g, [rec(12, 5), rec(0, pop + 1)]) == (0, None)        # the editor's order: time limit first
    assert G.check(g, [rec(12, 0), rec(0, pop + 1)]) == (-1, G.LOSE_TIME)
    assert G.check(g, [rec(13, 0)]) == (1, None) and G.check(g, [rec(13, 1)]) == (0, None)
    assert G.check(g, [rec(14, 0x200, 30, 0)]) == (1, None)              # good byte 0 (0x200 & 0xFF): met
    assert G.check(g, [rec(14, 9, 30, 29)]) == (0, None) and G.check(g, [rec(14, 9, 30, 30)]) == (1, None)
    assert G.check(g, [rec(7, 22)]) == (1, None)                         # city out of range: met
    g.city.months_in_debt = 36
    assert G.check(g, [rec(0, pop + 1)]) == (-1, G.LOSE_DEBT)
    g.city.months_in_debt = 0
    from sim import gods
    built = {3, 5}
    real = gods.built
    gods.built = lambda g_, i: i in built
    try:
        t = [rec(2, 5, -1, 1), rec(2, -1, -1, 1)]
        assert G.check(g, t) == (1, None)
        assert t[0]["v"][1] == 5 and t[1]["v"][1] == 3 and (t[0]["other"], t[1]["other"]) == (0, 1)
        t = [rec(2, -1, -1, 3)]                                          # 3 sanctuaries: 2 finished
        assert G.check(g, t) == (0, None) and t[0]["v"][3] == 2
    finally:
        gods.built = real


def test_campaign_flow():
    """1L-3: Zeus and Europa through the campaign module: new city, forced win (0x00F2A6DB) judged at the month change,
    Proceed -> slot 1 (continue: parent.dat loaded, date and treasury kept), slot 2 -> the colony choice (Cydonia),
    the colony (kind 1 start), its win -> back to the parent at slot 3 (episode_end_save_parent: the colony's date and
    treasury, Cydonia kind colony paying tribute; the colony monument message and grant); a loss by debt; replay."""
    import tempfile
    from sim.campaign import flow
    from sim.systems import commemorative
    d = tempfile.mkdtemp()
    save = os.path.join(d, "eu.pkl")
    g = flow.start("zeus_and_europa", seed=1, difficulty="Easy")
    assert g.campaign["slot"] == 0 and g.date() == "Jan 1150 BC" and len(g.campaign["goals"]) == 1
    month = g.rules["ticks_per_day"] * g.rules["days_per_month"]

    def win(g):
        g.campaign["forced"] = True
        g.step(month)
        assert g.campaign["result"] == 1, g.campaign
        return g
    win(g)
    assert flow.next_step(g)["kind"] == "episode"
    g.city.treasury = 4321
    g = flow.proceed(g, save)
    assert os.path.exists(flow.files(save)["parent"])
    assert g.campaign["slot"] == 1 and g.episode["start"] == "continue" and g.city.treasury == 4321
    assert g.date() == "Feb 1150 BC" and g.scenario_year == -1150 and g.campaign["result"] == 0
    g = flow.proceed(win(g), save)
    assert g.campaign["slot"] == 2
    win(g)
    try:
        flow.proceed(g, save)
        assert False, "the colony choice was not asked"
    except flow.Choice as c:
        assert [o[2] for o in c.options] == ["Cydonia"]
    c = flow.proceed(g, save, colony="1")
    assert c.campaign["slot"] == 10 and c.campaign["prev"] == 2 and c.empire.player().name == "Cydonia"
    assert c.date() == "Apr 1150 BC" and [r["type"] for r in c.campaign["goals"]] == [14, 14]
    c.step(month)
    c.city.treasury = 777
    p = flow.proceed(win(c), save)
    assert p.campaign["slot"] == 3 and p.empire.player().name == "Thebes" and p.city.treasury == 777
    assert p.date() == "Jun 1150 BC"
    cy = p.empire.cities[1]
    assert cy.kind == "colony" and cy.active and cy.tribute["mode"] == 1
    assert commemorative.state(p)["available"][3] == 1
    assert any("Cydonia" in str(m[1]) for m in p.city.messages[-3:])
    assert flow.colony_options(p) == []                                # each colony once
    p.save(flow.files(save)["replay"])
    p.city.treasury, p.city.months_in_debt = -100, 35
    p.step(month)
    assert p.campaign["result"] == -1 and p.campaign["lost"] == 0xB91
    r = flow.replay(save)
    assert r.campaign["slot"] == 3 and r.campaign["result"] == 0


def test_campaign_briefing_difficulty():
    """The briefing's difficulty arrows, taken at "To the city" (flow.briefed -> episode.set_difficulty): a new
    city's funds x start_funds_pct of the chosen level (episode_start_load runs after screen 0x35), the rules of
    that level; tick 0 only for the funds."""
    from sim.campaign import flow
    g = flow.start("zeus_and_europa", seed=1, difficulty="Normal")
    funds = flow.episode_of(g)["funds"]
    assert g.city.treasury == funds and g.difficulty == "Normal"
    flow.briefed(g, "VeryEasy")
    assert g.campaign["briefed"] and g.difficulty == "VeryEasy" and g.rules["difficulty"] == "VeryEasy"
    assert g.city.treasury == funds * 150 // 100, g.city.treasury
    flow.briefed(g, "Impossible")
    assert g.city.treasury == funds * 80 // 100 and g.cat.rules["difficulty"] == "Impossible"


def test_campaign_set_aside():
    """1L-3: the objectives screen's Set aside (0x0052ECF0): needs the rest in stock (0x00529D10), takes it out of
    storage (city_goods_remove) and adds it to the goal's counter v3."""
    from sim.campaign import goals as G
    from sim.systems import economy
    g = Game("sandbox_open", 1)
    g.campaign = dict(goals=[dict(type=14, v=[9, 3, 0, 0, 0, 0], other=0, good="wood")])
    assert _raises(lambda: G.set_aside(g, 0)) is not None              # nothing in stock
    g.command("road 86 33 115 33")
    g.command("build storehouse 88 30")
    s = next(b for b in g.buildings.values() if b.key == "storehouse")
    s.goods["wood"] = 500
    assert "set aside 3 wood" in G.set_aside(g, 0)
    assert g.campaign["goals"][0]["v"][2] == 3 and economy.city_stock(g, "wood") == 200
    assert G.met(g, g.campaign["goals"][0]) and _raises(lambda: G.set_aside(g, 0)) is not None


def test_campaign_screen_texts():
    """1L-4: the objectives screens' goal rows as the exe writes them (oracle 1L4-goals goals.bmp / hover.bmp /
    after.bmp: six poked goals): goal and status texts of group 194, the tick box (Treasury met; a time limit not yet
    reached is empty), the Set aside row lit only with the rest in stock (FUN_00529D10), Done after it."""
    from sim.campaign import flow, texts
    g = flow.start("zeus_and_europa", seed=1, difficulty="Easy")
    rec = lambda t, *v: dict(type=t, v=(list(v) + [0] * 6)[:6], other=0, good=None)     # noqa: E731
    g.campaign["goals"] = [rec(0, 1000), rec(1, 4000), rec(2, -1, -1, 2), rec(3, 13, 4), rec(14, 9, 3, 0), rec(12, 5)]
    rows = texts.rows(g, g.campaign["goals"])
    assert [(r["goal"], r["status"]) for r in rows] == [
        ("Population of 1000", "Population 0"), ("Treasury of 4000", "Treasury 5000"),
        ("2 sanctuaries", "Sanctuaries needed"), ("Support 4 Horsemen", "0 supported"),
        ("3 planks of wood for colony", "0 in stock"), ("Complete episode before 1145 BC", "60 months remain")], rows
    assert [r["box"] for r in rows] == [False, True, False, False, False, False]
    assert not any(r["button"] for r in rows)
    g.command("build storehouse 98 20")                # a free spot of the parent map
    s = next(b for b in g.buildings.values() if b.key == "storehouse")
    s.goods["wood"] = 500
    rows = texts.rows(g, g.campaign["goals"])
    assert rows[4]["status"] == "Set aside" and rows[4]["button"], rows[4]
    from sim.campaign import goals as G
    G.set_aside(g, 4)
    rows = texts.rows(g, g.campaign["goals"])
    assert rows[4]["status"] == "Done" and rows[4]["box"] and not rows[4]["button"]
    # the briefing (0x0052E520): goal texts only, every box empty; a colony start says "for parent city"
    a = flow.load("zeus_and_europa")
    b = flow.briefing_rows(None, a, flow.episode_rec(a, 10))
    assert [r["goal"] for r in b] == ["30 planks of wood for parent city", "30 amphorae of wine for parent city"]
    assert not any(r["box"] or r["status"] for r in b)


def test_campaign_screens():
    """1L-4: which campaign screen is up (flow.screen; the live server holds the city while one is): the briefing
    until "To the city", the victory from the winning month check, the adventure-complete screen after Proceed on the
    last episode until "Continue building this city", the defeat a day after the loss (0x00FEB164); the adventure
    list as the exe's (oracle 1L-europa1 s32: 7 campaigns + 3 open plays by .pak name, Poseidon off)."""
    import tempfile
    from sim.campaign import flow
    A = flow.adventures()
    assert [e["name"] for e in A["adventures"]] == [
        "Zeus and Europa", "Perseus and Medusa", "Athens through the Ages", "The Voyages of Jason", "Hercules Labors",
        "The Peloponnesian War", "The Trojan War", "Open Play Economic", "Open Play Military", "Open Play Sandbox"]
    assert len(A["tutorials"]) == 16 and not any(e["why"] for e in A["tutorials"])     # 1L-5: .sav starts
    assert "The Odyssey" in [e["name"] for e in A["custom"]]
    d = tempfile.mkdtemp()
    save = os.path.join(d, "eu.pkl")
    g = flow.start("zeus_and_europa", seed=1, difficulty="Easy")
    assert flow.screen(g) == "briefing"
    flow.briefed(g)
    assert flow.screen(g) is None
    month = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    g.campaign["forced"] = True
    g.step(month)
    assert flow.screen(g) == "victory"
    s = flow.screens(g)
    assert s["screen"] == "victory" and s["victory"] == 444 and s["intro"] == 430 and s["city"] == "Thebes"
    g = flow.proceed(g, save)
    assert flow.screen(g) == "briefing" and g.campaign["slot"] == 1
    flow.briefed(g)
    g.campaign["slot"] = 6                                 # the last episode (next 3): Proceed -> screen 0x43
    g.campaign["forced"] = True
    g.step(month)
    assert flow.screen(g) == "victory" and flow.next_step(g)["kind"] == "end"
    assert flow.proceed(g, save) is g and flow.screen(g) == "complete"
    flow.continue_building(g)
    assert flow.screen(g) is None and g.campaign["stay"]
    # a defeat: the screen opens at the next day's check
    g = flow.start("zeus_and_europa", seed=1, difficulty="Easy")
    flow.briefed(g)
    g.city.treasury, g.city.months_in_debt = -100, 35
    while g.campaign["result"] == 0:
        g.step(1)
    assert g.campaign["result"] == -1 and flow.screen(g) is None
    g.step(g.rules["ticks_per_day"])
    assert flow.screen(g) == "defeat" and "lost_text" in flow.screens(g)


def test_tutorial_sav_import():
    """1L-5: an original .sav as our Game (sim/savimport.py; oracle 1L5-tut*, tools/tutorial_check.py): the date,
    treasury, buildings placed by our builders with the save's footprints, houses with their level / people / goods /
    service counters, storage, monuments, avenues, roadblocks, herds; a tutorial starts from it through the campaign."""
    from sim import savimport, savefile
    from sim.campaign import flow
    p = os.path.join(ROOT, "zeus-original/app/Adventures/tutorial00.sav")
    assert savefile.kind(p) == "sav"
    g = Game.load(p)
    assert (g.date(), g.city.treasury, g.city.population, g.difficulty) == ("Mar 1989 BC", 14759, 88, "VeryEasy")
    assert sorted(b.key for b in g.buildings.values()).count("house") == 11 and not g.sav["skipped"]
    assert {b.level for b in g.buildings.values() if b.kind == "house"} == {0}
    g = flow.start("bigcity")
    assert g.campaign["slot"] == 1 and g.sav["slot"] == 1 and not g.sav["skipped"]
    gardens = [b for b in g.buildings.values() if b.key == "gardens"]  # bugs.md 399: the exe's gardens are terrain 0x20
    assert len(g.buildings) - len(gardens) == 334 and len(gardens) == int(((g.world.flags & 0x20) != 0).sum()) == 225
    # bugs.md 349: a tutorial starts on its goals screen with the tutorial buttons (oracle 1L5-tut00 start.bmp)
    assert flow.screen(g) == "tutorial" and flow.screens(g)["tutorial"] == dict(id="bigcity", index=15,
                                                                               prev="peacewar", next=None)
    flow.briefed(g)
    assert flow.screen(g) is None
    keys = {b.key for b in g.buildings.values()}
    assert {"palace", "sanctuary_apollo", "sanctuary_ares", "stadium", "dock", "horse_ranch", "grand_agora"} <= keys
    assert all(b.misc.get("complete") for b in g.buildings.values() if b.key.startswith("sanctuary_"))
    assert g.world.avenue.any() and len(g.roadblocks) == 19
    assert sum(1 for w in g.walkers.values() if w.role in ("sheep", "goat")) == 40
    hs = [b for b in g.buildings.values() if b.kind == "house"]
    assert {b.level for b in hs} == {6, 12} and all(b.coverage.get("water") for b in hs if b.level == 6)
    flow.briefed(g)
    g.step(816)                                 # a month: the houses keep their level (service counters imported)
    assert {b.level for b in g.buildings.values() if b.kind == "house"} == {6, 12}
    assert not (g.world.flags & 0x8).any()      # the exe's building bit is World.occ in ours


def test_sav_monument_terraces():
    """bugs.md 400: a .sav's elevation grid holds a monument's terraces (refresh_piece_image 0x0053D300 writes layout
    elevation + the root's base +0x6C); ours keeps the base under the pieces and raises them when drawing, so an
    imported sanctuary is not raised twice."""
    import numpy as np
    from sim import savimport
    from sim.systems import monuments
    p = os.path.join(ROOT, "zeus-original/app/Adventures/tutorial15.sav")
    sav = np.frombuffer(savimport.read(p)[1][savimport.SAV_OF_MAP[23]], np.uint8).reshape(228, 228)  # elevation
    g = Game.load(p)
    b = next(b for b in g.buildings.values() if b.key == "sanctuary_ares")
    lay = monuments.layouts()[b.key]
    el, ex = set(), set()
    for i, pc in enumerate(lay["pieces"]):
        px, py = monuments.piece_xy(b, i)
        n = monuments.size(pc[2])
        el |= set(int(v) for v in g.world.elev[py:py + n, px:px + n].ravel())
        ex |= set(int(v) for v in sav[py:py + n, px:px + n].ravel())
    assert len(el) == 1 and min(ex) == min(el) and len(ex) > 1


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])
