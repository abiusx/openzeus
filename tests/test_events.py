"""Scenario events and disasters.
Run: python3 tests/test_sim.py events (or a test by name: python3 tests/test_sim.py test_NAME)."""
import os
import pickle

from helpers import Game, _campaign, _ep


def test_scenario_events():
    """sim/scenario (docs/logic/events.md "Ours"): value groups, the pass's dates, chains, gifts, re-arm, old saves."""
    import tempfile
    from sim import scenario
    from sim.scenario.model import Scenario
    sc = Scenario("t", {}, {}, [], 1)
    assert scenario.value_resolve(sc, [0, 5, -1, -1]) == 5
    assert scenario.value_resolve(sc, [0, -1, 3, 3]) == -1                # quirk: a < 0, b == c -> a
    assert {scenario.value_resolve(sc, [0, -1, 5, 8]) for _ in range(300)} == {5, 6, 7, 8}
    assert {scenario.value_resolve(sc, [0, 1, 7, 3]) for _ in range(300)} == {1, 7, 3}
    scenario._plugins()                              # the tracks' handlers first, so the stubs replace them
    saved, fired = dict(scenario.HANDLERS), []

    def stub(g, ev):                                 # fires on its date, done, chains (stands in for 1H/1I)
        if scenario.due(g, ev):
            fired.append((ev["id"], g.month_index))
            scenario.done(g, ev)
            if ev["chain"] >= 0:
                scenario.chain(g, ev)
    try:
        for t in (4, 26, 27):
            scenario.register(t, stub, "test", replace=True)
        g = Game("sandbox2", 1)
        g.command("gods off")                        # the event timeline only (jealous gods: sim/gods' own tests)
        q = scenario.get(g, 0)                       # Hephaestus quest, Jan year +5 -> reward #1: 32 marble
        assert (q["year"], q["month"], q["chain"]) == (5, 0, 1)
        for _ in range(12 * 18 + 3):                 # the player accepts every offer it can (sim/empire/offers.py;
            g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"])    # goods with no storage room: decline)
            for o in [e for e in g.empire.events if e["type"] == "offer" and e.get("buttons", 0)]:
                g.command(f"offer {o['id']} {'accept' if o['buttons'] & 4 else 'decline'}")
        assert (0, 61) in fired                      # dated Jan +5: the pass at the change to Feb (month index 61)
        assert g.empire.totals["gifts_received"] == 5000                    # the Minotaur's reward (#6 -> #7)
        gifts = [e for e in g.scenario.events if e["type"] == 23 and e["flags"] & scenario.DYNAMIC]
        assert gifts and all(e["state"] == 10 for e in gifts)
        fired.clear()
        g = Game("sandbox_open", 1)                       # god invasion: Dec, year +5..8, recurring every 5..8 years
        g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"] * 12 * 21)
        at = [m for i, m in fired if i == 3]
        assert len(at) >= 2 and all(5 * 12 <= b - a <= 8 * 12 and b % 12 == 0 for a, b in zip(at, at[1:])), at
    finally:
        scenario.HANDLERS.clear()
        scenario.HANDLERS.update(saved)
    g = Game("sandbox_open", 1)                           # saves from before the engine: none
    del g.scenario, g.scenario_v
    with tempfile.TemporaryDirectory() as d:
        g.save(d + "/s.pkl")
        g2 = Game.load(d + "/s.pkl")
    assert g2.scenario is None and "on:" in g2.command("scenario on") and g2.scenario.events


def test_quota_status_events():
    """1L-5: scenario types 13/14/21/22 (demand / supply changes, event_demand_increase 0x00472540 ..: quota levels
    0/12/24/36, the oracle's warning, history + message), type 19's messages / subtypes 13 (a god's disaster: trade
    stops, the recovery 0x16 after the lead months) and 24 (conquered by a rival, FUN_0046EAC0), and the parent city
    destroyed while in a colony (FUN_00477AB0 -> 0xB94, the episode lost at once)."""
    from sim import scenario
    from sim.empire import status_events, quota_events
    from sim.empire.model import GOOD_IDS
    from sim.campaign import flow
    g = flow.start("zeus_and_europa", seed=1, difficulty="Easy")
    flow.briefed(g)
    e = g.empire
    c = next(c for c in e.cities.values() if c.trading() and c.buys)
    good = next(iter(c.buys))
    y, m = scenario.today(g)

    def ev(t, **kw):
        r = scenario.alloc(g, dict(dict(type=t, year=y, month=m, city=c.id, item=GOOD_IDS[good], flags=0, chain=-1), **kw))
        scenario.dispatch(g, r)
        return r
    c.buys[good] = 5
    r = ev(13)
    assert c.buys[good] == 12 and r["flags"] & scenario.DONE and "buy more" in g.city.messages[-1][1].lower()
    ev(13), ev(13), ev(13)
    assert c.buys[good] == 36
    ev(14)
    assert c.buys[good] == 24
    assert [quota_events.step(q, False) for q in (0, 12, 13, 24, 25, 36)] == [0, 0, 12, 12, 24, 24]
    n = len(g.city.messages)
    r = ev(14, year=y + 1, flags=scenario.WARN)               # not due: the oracle's prediction, once
    assert r["flags"] & scenario.WARNED and not r["flags"] & scenario.DONE and len(g.city.messages) == n + 1
    assert c.buys[good] == 24 and "oracle" in g.city.messages[-1][1].lower()
    other = next(x for x in e.cities.values() if x.sells and x is not c)
    sg = next(iter(other.sells))
    other.sells[sg] = 0
    r = scenario.alloc(g, dict(type=22, year=y, month=m, city=other.id, item=GOOD_IDS[sg], flags=0, chain=-1))
    scenario.dispatch(g, r)
    assert other.sells[sg] == 0 and r["flags"] & scenario.DONE
    # 19 / 13: a god's disaster closes trade; the recovery comes after the lead months
    k = len(g.scenario.events)
    ev(19, kind=13, lead=3, b36=0)
    assert not c.trade_open and "Zeus" in g.city.messages[-1][1]
    fol = g.scenario.events[k:]
    assert fol and fol[-1]["kind"] == 0x16 and (fol[-1]["year"] * 12 + fol[-1]["month"]) == y * 12 + m + 3
    # 19 / 24: conquered by a rival (+0x6F)
    riv = next(x for x in e.cities.values() if x.cls() == "rival" and x.exists())
    c.relation, c.trade_open = "ally", True
    raw = bytearray(124)
    raw[0x6F] = riv.id
    ev(19, kind=24, raw=raw.hex())
    assert c.relation == "rival" and riv.name in g.city.messages[-1][1]
    # the parent city destroyed while the player is in a colony: lost (0xB94) at once
    par = next(x for x in e.cities.values() if x is not c and x.kind == "foreign")
    par.kind = "parent"
    assert status_events.destroyed(g, par, by=riv) and par.kind == "destroyed"
    g.step(g.rules["ticks_per_day"])
    assert g.campaign["result"] == -1 and g.campaign["lost"] == 0xB94


def test_city_events():
    """1L-5: scenario types 8/9 wages (event_wage_increase 0x00472F00: the expectation 30 +/- amount within 5..45),
    12 clay pit flood, 15/16 prices (event_price_increase 0x00472B20: goods_price, 2 at the floor), 17/18 favour
    (0x0046E840: attitude +/- amount), 20 rival army away (0x00474160: 3/5 of the army away for 12 months, back by
    relations.monthly); their messages and chains."""
    from sim import scenario
    from sim.empire.model import GOOD_IDS
    from sim.systems import trade
    from sim.campaign import flow
    g = flow.start("zeus_and_europa", seed=1, difficulty="Easy")
    flow.briefed(g)
    e = g.empire
    y, m = scenario.today(g)

    def ev(t, **kw):
        r = scenario.alloc(g, dict(dict(type=t, year=y, month=m, flags=0, chain=-1), **kw))
        scenario.dispatch(g, r)
        return r
    r = ev(8, amount=10)
    assert g.wage_expectation == 40 and r["flags"] & scenario.DONE and "paid more" in g.city.messages[-1][1]
    ev(8, amount=10)
    assert g.wage_expectation == 40                         # 50 >= 46: no change
    ev(9, amount=30)
    assert g.wage_expectation == 10
    n = len(g.city.messages)
    r = ev(12)
    assert r["flags"] & scenario.DONE and len(g.city.messages) == n
    p0 = trade.price(g, "wine")
    ev(15, item=GOOD_IDS["wine"], amount=20)
    assert trade.price(g, "wine") == p0 + 20 and "Wine" in g.city.messages[-1][1]
    ev(16, item=GOOD_IDS["wine"], amount=10000)
    assert trade.price(g, "wine") == 2 and g.cat.trade["prices"]["wine"] == p0       # the game's table only
    r = ev(16, item=GOOD_IDS["wine"], amount=1, year=y + 1, flags=scenario.WARN)
    assert r["flags"] & scenario.WARNED and "seers predict" in g.city.messages[-1][1].lower()   # sic: 0x333
    c = next(c for c in e.cities.values() if c.exists() and c.cls() == "ally")
    c.attitude = 50
    ev(17, city=c.id, amount=30)
    assert c.attitude == 80 and "more highly" in g.city.messages[-1][1]
    ev(18, city=c.id, amount=100)
    assert c.attitude == 0
    riv = next(x for x in e.cities.values() if x.cls() == "rival" and x.exists())
    riv.army, riv.away = 100, [0, 0, 0]
    ev(20, city=riv.id)
    assert riv.army == 40 and riv.away[1] == 60 and riv.troops_return == [12, 60]
    assert "vulnerable" in g.city.messages[-1][1]
    ev(20, city=riv.id)                                     # again: the first 60 come home, then 3/5 of 100 go
    assert riv.army == 40 and riv.away[1] == 60


def test_invasion_events():
    """1L-5: scenario type 2 (invasion_event_month 0x00476E20): the announcement on its date (bit 1), the reminders
    once each, the army on the map when the months until due reach 0 (sim/military, quiet; message 0x2D9 with the
    bribe), done + active until the army is gone; a city that is not an active rival: done, nothing comes; the
    soonest pending one feeds the alarm (empire.next_invasion)."""
    from sim import scenario, empire
    from sim.military import invaders
    from sim.campaign import flow
    g = flow.start("zeus_and_europa", seed=1, difficulty="Easy")
    flow.briefed(g)
    e = g.empire
    riv = next(x for x in e.cities.values() if x.kind == "foreign" and x.relation == "rival" and x.exists())
    riv.tribute["mode"] = 0
    y, m = scenario.today(g)
    r = scenario.alloc(g, dict(type=2, year=y, month=m, lead=2, city=8, city2=riv.id, amount=20, flags=0, chain=-1))
    n = len(g.city.messages)
    scenario.dispatch(g, r)
    assert r["warned_bits"] == 1 and "launches invasion" in g.city.messages[-1][1] and "in 2 months" in g.city.messages[-1][1]
    scenario.dispatch(g, r)
    assert len(g.city.messages) == n + 1                    # once
    assert empire.next_invasion(g)[0] == 2
    r["month"], r["year"] = (m - 2) % 12, y - (1 if m < 2 else 0)
    scenario.dispatch(g, r)
    invs = [i for i in invaders.invasions(g).values() if i.get("sev") == r["id"]]
    assert invs and r["flags"] & scenario.DONE and r["active"] == 1 and "upon us" in g.city.messages[-1][1]
    invaders.close(g, invs[0]["id"], invs[0])
    scenario.dispatch(g, r)
    assert r["active"] == 0
    other = next(x for x in e.cities.values() if x.kind == "foreign" and x.relation == "ally" and x.exists())
    r2 = scenario.alloc(g, dict(type=2, year=y, month=m, lead=0, city=8, city2=other.id, amount=20, flags=0, chain=-1))
    scenario.dispatch(g, r2)
    assert r2["flags"] & scenario.DONE and not any(i.get("sev") == r2["id"] for i in invaders.invasions(g).values())


def test_request_events():
    """1L-5: scenario type 1 (event_request 0x00470800): activated a year ahead, the announcement when the countdown
    reaches the lead, paid on time (event_pay_tribute_or_gift: state 3) -> the attitude result 1..4 months later
    (request_resolve_attitude 0x0046FFA0: ally +18, history, "regards you more highly"); unpaid -> overdue (state 1,
    the grace months) -> refused (-20, state 5); the Overview and fulfil list it. Troops (event_troops_request_update
    0x0046ED70): never sent -> refused and the +0x56 consequence (the city destroyed); sent and in time -> the
    distant battle with the city's army against the rival's 3/5 (won: state 7, home after the travel months)."""
    from sim import scenario
    from sim.empire import requests, diplomacy
    from sim.campaign import flow
    g = flow.start("zeus_and_europa", seed=1, difficulty="Easy")
    flow.briefed(g)
    e = g.empire
    c = next(x for x in e.cities.values() if x.kind == "foreign" and x.relation == "ally" and x.exists())
    y, m = scenario.today(g)
    g.city.treasury = 5000

    def req(**kw):
        return scenario.alloc(g, dict(dict(type=1, year=y + 1, month=m, lead=3, city=c.id, item=23, amount=100,
                                           kind=0, flags=0, chain=-1), **kw))
    r = req()
    scenario.dispatch(g, r)
    assert r["active"] == 1 and r["countdown"] == 15 and r["b33"] == 1
    n = len(g.city.messages)
    for _ in range(12):
        scenario.dispatch(g, r)
    assert r["countdown"] == 3 and len(g.city.messages) == n + 1 and "100 drachmas in 3 months" in g.city.messages[-1][1]
    assert requests.is_open(r) and any(row.get("request") for row in scenario.request_list_rebuild(g))
    rows = [x for x in scenario.request_rows(g) if x["kind"] == "request" and x["city"] == c.name]
    assert rows and rows[0]["amount"] == 100 and rows[0]["months"] == 3 and rows[0]["can"]
    from sim import empire
    assert any(q["amount"] == 100 for cc in empire.export(g)["cities"] if cc["name"] == c.name for q in cc["requests"])
    c.attitude = 50
    diplomacy.fulfil(g, c, 0)
    assert r["state"] == 3 and g.city.treasury == 4900 and 1 <= r["countdown"] <= 4
    for _ in range(4):
        scenario.dispatch(g, r)
    assert r["state"] == 10 and r["flags"] & scenario.DONE and c.attitude == 68
    assert "regards you more highly" in g.city.messages[-1][1] and "agreeably sent" in g.city.messages[-1][1]
    r2 = req(year=0, month=0, lead=1)                       # year 0: active at once, countdown = month + lead
    scenario.dispatch(g, r2)
    assert r2["countdown"] == 1
    scenario.dispatch(g, r2)                                # countdown 0 < 1: overdue
    assert r2["state"] == 1 and r2["countdown"] >= 3 and "lost on the way" in g.city.messages[-1][1]
    while r2["state"] == 1:
        scenario.dispatch(g, r2)
    assert r2["state"] == 5 and c.attitude == 48 and "less highly" in g.city.messages[-1][1].replace("not regard you as highly", "less highly")
    # troops: never sent -> refused, the city destroyed by the rival (+0x56 = 1)
    riv = next(x for x in e.cities.values() if x.cls() == "rival" and x.exists())
    raw = bytearray(124)
    raw[0x6F], raw[0x56] = riv.id, 1
    c.attitude = 50
    t = req(item=24, kind=1, year=y, month=m, lead=0, amount=40, raw=raw.hex(), active=1)
    scenario.dispatch(g, t)
    assert t["state"] == 10 and c.attitude == 30 and c.kind == "destroyed"
    # troops sent and waiting at the city: the battle in the due month
    c2 = next(x for x in e.cities.values() if x.kind == "foreign" and x.relation == "ally" and x.exists())
    raw[0x56] = 0
    c2.army, riv.army = 100, 50
    t2 = req(item=24, kind=1, year=y, month=m, lead=0, amount=40, raw=raw.hex(), active=1, city=c2.id, state=6,
             countdown=1)
    scenario.dispatch(g, t2)
    assert t2["state"] == 7 and c2.army == 90 and riv.army == 35
    t2["year"] -= 1                                         # the following months: past the due date
    while t2["state"] == 7:
        scenario.dispatch(g, t2)
    assert t2["state"] == 10 and "Victorious warriors return" in g.city.messages[-1][1]


def test_request_answers():
    """1L-5 play mode: a request message carries the Dispatch now / Postpone / Refuse flags 0x1C0 when the stock
    covers it (event_request's bVar2) and its type-2 fields; `answer ID dispatch|refuse` (wm_sub_475AB0 / 475B50);
    the world map's 'requests by' rows follow the request list; a troops request's forces on their way are on the
    world map (event_world_map_position 0x004694E0); the tribute claim (event_tribute_out 0x004715C0) posts the exe's
    tribute_due phrases: announcement at the lead, overdue (one more year), the six-months warning, refused (-70)."""
    from sim import scenario, empire
    from sim.empire import diplomacy, war
    from sim.campaign import flow
    g = flow.start("zeus_and_europa", seed=1, difficulty="Easy")
    flow.briefed(g)
    e = g.empire
    c = next(x for x in e.cities.values() if x.kind == "foreign" and x.relation == "ally" and x.exists())
    y, m = scenario.today(g)
    g.city.treasury = 5000
    r = scenario.alloc(g, dict(type=1, year=0, month=0, lead=1, city=c.id, item=23, amount=100, kind=0, flags=0,
                               chain=-1))
    scenario.dispatch(g, r)
    scenario.dispatch(g, r)                              # countdown 1 -> 0: overdue, posted with the buttons
    meta = g.city.messages[-1][1].meta
    assert meta["buttons"] == 0x1C0 and meta["type"] == 2 and meta["event"] == r["id"] and meta["good"] == "drachmas"
    scenario.request_list_rebuild(g)
    row = next(q for cc in empire.export(g)["cities"] if cc["id"] == c.id for q in cc["requests"])
    assert row["event"] == r["id"] and row["overdue"]
    ex = next(q for q in scenario.export(g) if q["id"] == r["id"])
    assert ex["open"] and ex["can"] and ex["city"] == c.name
    out = g.command(f"answer {r['id']} dispatch")
    assert "100" in out and g.city.treasury == 4900 and r["state"] == 4
    r2 = scenario.alloc(g, dict(type=1, year=0, month=0, lead=3, city=c.id, item=23, amount=100, kind=0, flags=0,
                                chain=-1))
    scenario.dispatch(g, r2)
    g.command(f"answer {r2['id']} refuse")
    assert r2["flags"] & 0x40000 and r2["state"] == 1 and r2["countdown"] == 1
    # troops on their way: the player's army on the route to the city
    t = scenario.alloc(g, dict(type=1, year=0, month=0, lead=12, city=c.id, item=24, amount=10, kind=1, flags=0,
                               chain=-1, state=6, active=1, countdown=max(1, e.travel_months(e.player().id, c.id)),
                               strength=40))
    pos = [a for a in war.positions(g) if a["event"] == f"s{t['id']}"]
    assert pos and pos[0]["who"] == "player" and not pos[0]["home"] and pos[0]["size"] == 1
    # tribute claimed by a rival that conquered the player (+0xE0 = 2)
    riv = next(x for x in e.cities.values() if x.cls() == "rival" and x.exists())
    riv.tribute.update(mode=2, claim=400)
    g.city.treasury = 0
    from sim.empire import events
    ev = events.add(g, type="tribute_out", city=riv.id, item="drachmas", amount=400, deadline=2, countdown=14)
    texts = []
    for _ in range(27):
        n = len(g.city.messages)
        diplomacy.tribute_out_month(g, ev)
        texts += [str(x[1]) for x in g.city.messages[n:]]
    assert texts[0].startswith(f"{riv.name} demands Tribute. Attention") and "within 2 months" in texts[0], texts
    assert "one more year" in texts[1] and texts[2].startswith(f"{riv.name} demands Tribute. Six months"), texts
    assert texts[3].startswith(f"{riv.name} thinks less of you. Because you failed"), texts
    assert ev["state"] == 10      # refused (5), then done (events.done)


def test_earthquake():
    """1L-5 terrain disasters (sim/disasters, docs/logic/events.md "Terrain disasters"): Athens' disaster point 1 is an
    earthquake fault of 145 tiles in 21 rings (oracle 1L5-quake: the same rings, tile by tile every 10 ticks); started
    by its record (event_terrain_disaster 0x0046D6D0): the message 0x52E / 0x530 and the alert; one ring every 20 ticks
    (0x0056DD40), each tile cracked rock (terrain & 0xFACFA710 | 0x300002): the building on it collapses, the road
    goes, a walker on it dies; then state 7 and the record's state 2."""
    from sim import scenario, disasters, alerts
    from sim.campaign import flow
    g = flow.start("athens_through_the_ages", seed=1, difficulty="Easy")
    flow.briefed(g)
    st = disasters.setup(g)
    o = st["objects"][0]
    assert (o["cls"], o["x"], o["y"], len(o["nodes"]), o["rings"]) == (3, 109, 190, 145, 21)
    ring = {(n["x"], n["y"]): n["ring"] for n in o["nodes"]}
    far = max(ring, key=ring.get)                     # a tile of the last ring, a road on it
    g.road(*far, *far)
    assert g.world.road[far[1], far[0]]
    import copy                                       # episode 1's record 24 (point 1), dated now
    ev = copy.deepcopy(g.scenario.events[0])
    y, m = scenario.today(g)
    ev.update(type=3, year=y, month=m, flags=0, active=0, state=0, parent=-1,
              groups=dict(ev["groups"], city=[1, 1, -1, -1]))
    disasters.event(g, ev)
    assert ev["active"] == 1 and ev["state"] == 1 and ev["flags"] & scenario.DONE and o["started"]
    assert "Earthquake!" in str(g.city.messages[-1][1])
    meta = getattr(g.city.messages[-1][1], "meta", None) or {}      # type 0xDE: the window's go-to button
    assert meta.get("at") == [109, 190] and meta.get("kind") == 0xDE
    assert meta.get("stinger") == "dis"                             # disaster_start: FUN_005A1210(3 / 6), S_dis
    assert alerts.state(g)["slots"][0]["type"] == alerts.EARTHQUAKE
    t0 = g.tick
    g.step(19)
    assert not o["cracked"]                           # the 20th call cracks ring 1
    g.step(1)
    assert o["cracked"] == [(109, 190)] and int(g.world.flags[190, 109]) & 0x300002 == 0x300002
    while o["state"] != 7:
        g.step(1)
    assert g.tick - t0 == 21 * 20 and len(o["cracked"]) == 145 and not g.world.road[far[1], far[0]]
    disasters.event(g, ev)                            # the next pass: the object is done
    assert ev["state"] == 2 and ev["active"] == 0


def test_disaster_effects():
    """bugs.md 362: the post step (disaster_post_step 0x00447790) makes pictures only: with the live recorder on
    (g.fx) the earthquake reports its crack dust and nothing else (quake_segment_dust's node call is a getter), the
    sim's state and RNG stay the same as without it; a lava object's step reports splashes on the current ring's
    nodes (FUN_00506F40: at least 15 a call, wrapping) at fine spots -1..15 and drops from a lower ring
    (FUN_00507170); a tidal wave's 4..7 sprays (FUN_004E4480). Oracle: tools/oracle_disaster.py effects."""
    import copy
    import pickle
    from sim import scenario, disasters
    from sim.campaign import flow

    def game():
        g = flow.start("athens_through_the_ages", seed=1, difficulty="Easy")
        flow.briefed(g)
        st = disasters.setup(g)
        ev = copy.deepcopy(g.scenario.events[0])
        y, m = scenario.today(g)
        ev.update(type=3, year=y, month=m, flags=0, active=0, state=0, parent=-1,
                  groups=dict(ev["groups"], city=[1, 1, -1, -1]))
        disasters.event(g, ev)
        return g, st["objects"][0]
    a, oa = game()
    b, ob = game()
    a.fx = []
    kinds = set()
    for _ in range(60):
        a.step(1)
        kinds |= {e[1] for e in a.fx}
        a.fx = []
    b.step(60)
    a.__dict__.pop("fx")
    assert kinds == {"debris"} and pickle.dumps(a.world.flags) == pickle.dumps(b.world.flags)
    assert a.rng.getstate() == b.rng.getstate() and oa["seg"] == ob["seg"]
    cr = oa["crack"]                                  # the fault's nodes as a lava flow's inner rings of 10
    o = dict(oa, cls=disasters.LAVA, state=2, seg=3, count=10, crack=[], rings=5,
             nodes=[dict(n, edge=False) for n in oa["nodes"]], segs=[cr[k:k + 10] for k in range(0, 50, 10)])
    a.fx = []
    disasters.post_step(a, o)
    lava = [e for e in a.fx if e[1] == "lava"]
    ring = {(o["nodes"][j]["x"], o["nodes"][j]["y"]) for j in o["segs"][3]}
    assert len(lava) >= 15 and all((e[2], e[3]) in ring and -1 <= e[4] <= 15 and -1 <= e[5] <= 15 for e in lava)
    assert len([e for e in a.fx if e[1] == "drops"]) == 1
    a.fx = []
    disasters.post_step(a, dict(o, cls=disasters.TIDAL))
    assert 4 <= len([e for e in a.fx if e[1] == "spray"]) <= 7 and all(e[1] == "spray" for e in a.fx)


def test_lava_pictures_after_load():
    """bug 450: a loaded game's cooled lava (terrain 0x1000000, its lava nodes in state 7: still drawn, unmasked,
    FUN_00520820 / FUN_00507980) gets its lava pictures on load as in the session that burnt it: TerrainView repaints
    every tile whose terrain differs from the map's (before: only the session's own repaints; on reload the field
    kept the map's grass until a build next to it re-matched the area)."""
    import numpy as np
    from sim import disasters
    from sim.terrain_view import TerrainView
    import terrain_images as ti
    g = Game("sandbox_open", 1)
    tv = TerrainView(g)
    tiles = [(x, y) for y in range(60, 68) for x in range(100, 108)]
    for x, y in tiles:
        g.world.flags[y, x] = (int(g.world.flags[y, x]) & 0xFBCFA710) | 0x1000000
    g.__dict__["disasters"] = {"objects": [dict(idx=4, cls=disasters.LAVA, started=True, state=7, c3=100,
                                                nodes=[dict(x=x, y=y) for x, y in tiles])], "owner": {}}
    g.map_version = getattr(g, "map_version", 0) + 1
    tv.update(g)                                      # the session: repainted as the lava burns
    tv2 = TerrainView(g)                              # a load: the same pictures
    lo = ti.COL + ti.first(ti.G_LAVA)
    xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
    a, b = tv.ids[ys, xs], tv2.ids[ys, xs]
    assert (a == b).all() and tv.lava_edge == tv2.lava_edge
    centre = (b >= lo) & (b < lo + 6)
    assert centre.sum() == 36 and centre.sum() + len(tv2.lava_edge) == len(tiles)


def test_landslide():
    """1L-5 landslide (sim/disasters/landslide.py, docs/logic/events.md "Terrain disasters"): Open Play Economic 2's
    Taenarum colony (reached by forced wins) has one slide site at the map start (landslide_candidates 0x00505D90:
    (119, 134) north, size 4, score 243; 42 plateau tiles marked, as the exe's 0x80000000 bits in oracle
    1L5-dis-econ2-taenarum-lava); its first record (point 1) slides it: 46 tiles raised, 35 lowered (oracle: the
    same elevation and terrain grids, whole map), the message 0xC79 / 0xC7A; the second record (point 2) finds no
    valid site any more."""
    import os
    import tempfile
    import numpy as np
    from sim.campaign import flow
    g = flow.start("open_play_economic_2", seed=1, difficulty="Easy")
    save = os.path.join(tempfile.mkdtemp(), "c.pkl")
    mon = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    for col in ("Marathon", None, "Taenarum"):
        g.campaign["forced"] = True
        g.step(mon)
        g = flow.proceed(g, save, colony=col)
    flow.briefed(g)
    st = g.landslide
    assert [(s["x"], s["y"], s["dir"], s["size"], s["score"]) for s in st["sites"]] == [(119, 134, 0, 4, 243)]
    assert len(st["marks"]) == 42
    e0 = g.world.elev.astype(int)
    while not st["slides"]:
        g.step(mon)
    d = g.world.elev.astype(int) - e0
    assert ((d == 1).sum(), (d == -1).sum(), (abs(d) > 1).sum()) == (46, 35, 0)
    assert "Landslide!" in str(g.city.messages[-1][1])
    for _ in range(3):
        g.step(mon)
    assert len(st["slides"]) == 1


def test_tidal_push_boats():
    """1L-5 tidal wave retreat (0x004E3EC0 apply 0): a boat on a tile that turns to land moves 2 tiles towards the
    middle of the longest water arc around it (FUN_004A1FF0(4), N NE E SE S SW W NW); the exe's scan keeps a run
    broken by land unless it was the longest so far: water N NE E and SE only -> W."""
    from sim.game import Game
    from sim import disasters
    from sim.systems import walkers
    g = Game("sandbox", seed=1)
    w = g.world
    for wet, want in (((2, 3, 4), (102, 102)), ((0, 1, 6, 7), (100, 98)), ((0, 1, 2, 4), (98, 100))):
        for k, (dx, dy) in enumerate(disasters.NB):
            v = int(w.flags[100 + dy, 100 + dx]) & ~4
            w.flags[100 + dy, 100 + dx] = v | (4 if k in wet else 0)
        b = walkers.add(g, walkers.new_walker(g, role="ship", home=0, x=100, y=100))
        disasters._push_boats(g, 100, 100)
        assert (b.x, b.y) == want, (wet, b.x, b.y)
        walkers.remove(g, b)


def test_demand_refused_message():
    """A rival's refused demand (event_demand_refused 0x004756B0): message 0x3F2 / 0x3F3 on its date, not an English
    log line (bugs.md 384); play mode names the city by id (Mt. Pelion / Mt. Cithaeron share "Mt.")."""
    from sim import episode
    a = _campaign("zeus_and_europa")
    g = episode.new_city(a["source"] + "#0", _ep(a, 0), difficulty="Normal")
    c = g.empire.find("Eleusis")
    g.command(f"request {c.id} wine")
    mon = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    g.step(mon * 3)
    t = [m for _, m in g.city.messages if "refuses your demand" in str(m)]
    assert t and "Eleusis refuses your demand" in t[0] and "insolent oaf" in t[0], g.city.messages[-5:]


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])
