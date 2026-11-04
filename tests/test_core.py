"""Engine core: determinism, saves, the benchmark cities, CLI texts and commands, difficulty, tick
order, figure slots, messages.
Run: python3 tests/test_sim.py core (or a test by name: python3 tests/test_sim.py test_NAME)."""
import os
import pickle

from helpers import ROOT, Game, play, fingerprint, assert_stable, _campaign, _ep, _raises


def test_deterministic():
    assert fingerprint(play(1)) == fingerprint(play(1))


def test_save_file_formats():
    """sim/savefile.py (user 10-31): our saves are a versioned header + zstd pickle; bare-pickle saves still load;
    an original .map / .pak opens as a new game on that map; an original .sav is refused."""
    import glob, tempfile, pickle as pk
    from sim import savefile
    g = Game("sandbox_open", 1)
    g.command("road 50 81 50 83")
    d = tempfile.mkdtemp()
    p = os.path.join(d, "a.pkl")
    g.save(p)
    assert savefile.kind(p) == "ours" and savefile.header(p) == (savefile.FORMAT, b"Z")
    g2 = Game.load(p)
    assert g2.tick == g.tick and (g2.world.road == g.world.road).all()
    old = os.path.join(d, "old.pkl")
    with open(old, "wb") as f:                              # a save from before the header
        pk.dump(g, f)
    assert savefile.kind(old) == "pickle" and Game.load(old).tick == g.tick
    adv = os.path.join(ROOT, "zeus-original", "app", "Adventures")
    files = sorted(glob.glob(os.path.join(adv, "*", "*.map")))[:1] + [os.path.join(adv, "}Open Play Sandbox.pak")]
    assert [savefile.kind(f) for f in files] == ["map", "pak"], files
    for f in files:
        assert Game.load(f).tick == 0                       # a new game on that map
    sav = os.path.join(d, "x.sav")
    open(sav, "wb").write(b"A\x01\x00\x00" + bytes(64))
    assert savefile.kind(sav) == "sav" and "original Zeus save" in str(_raises(lambda: Game.load(sav)))   # broken
    real = os.path.join(adv, "tutorial00.sav")              # 1L-5: converted (sim/savimport.py)
    assert savefile.kind(real) == "sav" and Game.load(real).city.treasury == 14759


def test_save_load_transparent():
    """A game saved and loaded mid-day (each CLI call) plays on exactly as one run in a single process (bugs.md 315:
    the contact hook was set by the first military day of a process, and the fighters list missed walkers spawned
    since it was made)."""
    import tempfile
    from sim.systems import walkers
    g = play(1)
    g.command("wolves 150 140")              # a pack in the town: tile contacts (wolf on a walker, a hunter on a wolf)
    d = tempfile.mkdtemp()
    p, q = os.path.join(d, "a.pkl"), os.path.join(d, "b.pkl")
    g.save(p)
    a = Game.load(p)
    a.step(1500)
    b = Game.load(p)
    for n in (37, 250, 13, 400, 51, 333, 416):
        b.step(n)
        b.save(q)
        b = Game.load(q)
        walkers.CONTACT = None               # as a new process (a CLI call) starts
    def canon(o):                            # sets in a fixed order (a loaded set may iterate differently)
        if isinstance(o, (set, frozenset)):
            return sorted((canon(v) for v in o), key=repr)
        if isinstance(o, dict):
            return [(canon(k), canon(v)) for k, v in o.items()]
        if isinstance(o, (list, tuple)):
            return [canon(v) for v in o]
        return o if isinstance(o, (int, float, str, bool, type(None))) else canon(vars(o))

    key = lambda x: repr(canon([x.tick, x.city, x.rng.getstate(), [(b.id, b.key, b.level, b.occupants, b.goods)
                                for b in x.buildings.values()], [vars(w) for w in x.walkers.values()]]))
    assert key(a) == key(b)
    # the two causes, directly: (1) a hunter stepping onto a wolf fights at once in a new process (no day passed yet)
    from sim.military import contact
    wolves = [w for w in a.walkers.values() if w.role == "wolf" and not w.anim]
    wo, wo2 = wolves[0], wolves[1]
    walkers.CONTACT = None
    h = walkers.add(a, walkers.new_walker(a, role="hunter", home=0, x=wo.x + 1, y=wo.y), 10 ** 6)
    walkers.step_to(a, h, (wo.x, wo.y))
    assert h.anim == "fight" and wo.anim == "fight"
    # (2) a hunter created after today's fighters list was made is found by a wolf stepping onto its tile
    contact.fighters(a)
    h2 = walkers.add(a, walkers.new_walker(a, role="hunter", home=0, x=wo2.x + 1, y=wo2.y), 10 ** 6)
    old, wo2.x = (wo2.x, wo2.y), wo2.x + 1
    contact.track(a, wo2, old)
    assert contact.on_enter(a, wo2) and h2.anim == "fight"


def test_city_grows():
    g = play(1)
    assert g.city.population > 100


def test_boom_reaches_townhouses():
    g = play(1, "boom.txt")
    from sim.systems.housing import COMMON_TOP
    assert sum(1 for b in g.buildings.values() if b.kind == "house" and b.level == COMMON_TOP) >= 30
    assert_stable(g)


def test_full_city_villas():
    """scripts/full.txt: every common house a Townhouse and the villas Estates (wave 3: 90 + 10)."""
    from sim.systems.housing import COMMON_TOP, ELITE_TOP
    g = play(1, "full.txt")
    hs = [b for b in g.buildings.values() if b.kind == "house"]
    assert sum(1 for b in hs if b.level == COMMON_TOP) >= 85
    assert sum(1 for b in hs if b.level == ELITE_TOP) >= 8
    tt = g.trade_totals                     # wave 6: caravans and ships both traded
    assert tt["exported"].get("wine", 0) >= 1000 and tt["imported"].get("bronze", 0) >= 1000
    assert_stable(g)


def test_cli_hints_haiku3():
    """CLI texts (ours, playtest haiku-3 triage): `status` problems name a missing palace; a refused build names
    its footprint and what is in the way; `clear` names each whole building it removed."""
    from sim import render
    from sim.game import CommandError
    g = Game("sandbox_open", 1)
    from sim.systems import risk
    g.command("road 140 110 140 116")
    g.command("build palace 150 110")
    g.command("build tax_office 141 110")
    assert "no palace" not in render.status(g)
    risk.collapse(g, next(b for b in g.buildings.values() if b.key == "palace"))
    assert "no palace: tax offices send no clerks" in render.status(g)
    e = _raises(lambda: g.command("build granary 139 112"))
    assert isinstance(e, CommandError) and "(4x4: (139,112)-(142,115))" in str(e) and "(140,112) is a road" in str(e), e
    g.command("build granary 141 113")
    out = g.command("clear 143 115")
    assert "Granary #" in out and "(141,113)-(144,116)" in out, out


def test_difficulty_mid_game():
    """Options > Difficulty in play (0x00401EE0, docs/logic/difficulty.md "Difficulty during play"): Hard -> Easy
    swaps the per-level tables, read at their next use; treasury, built-up risk and the save keep theirs."""
    import tempfile
    from sim.systems import labor
    g = Game("sandbox_open", 1, difficulty="Hard")
    g.command("road 140 100 150 100")
    g.command("build house 141 101")
    g.step(300)
    hb = next(b for b in g.buildings.values() if b.key == "house")
    risk, t = (hb.fire_risk, hb.damage_risk), g.city.treasury
    assert g.cat.spec("house")["cost"] == 25
    wf = labor.workforce_pct(g)
    g.command("difficulty Easy")
    assert g.difficulty == "Easy" and g.rules["difficulty"] == "Easy"
    assert g.city.treasury == t                                     # mid-game: never re-scaled (0x00401EE0 on 0x45)
    assert (hb.fire_risk, hb.damage_risk) == risk                   # built-up risk stays
    assert labor.workforce_pct(g) == wf + 8                         # by_difficulty 37 -> 45, next labour pass
    g.command("build house 143 101")                                   # next placement: the Easy price
    assert g.city.treasury == t - 15
    with tempfile.TemporaryDirectory() as d:                        # the save keeps the level (sav rank 12)
        g.save(d + "/s.pkl")
        g2 = Game.load(d + "/s.pkl")
    assert g2.difficulty == "Easy" and g2.cat.spec("house")["cost"] == 15 and labor.workforce_pct(g2) == wf + 8
    g2.command("difficulty Hard")
    assert labor.workforce_pct(g2) == wf and g2.city.treasury == t - 15


def test_difficulty():
    """data/difficulty.json overlay (docs/logic/difficulty.md): costs, houses, tax sentiment, start funds %."""
    from sim.game import CommandError
    g = Game("sandbox_open", 1)
    assert g.difficulty == "Normal" and g.city.treasury == 15000 and g.cat.spec("house")["cost"] == 20
    g.command("difficulty veryeasy")
    assert g.city.treasury == 22500 and g.cat.spec("house")["cost"] == 10 and g.rules["tax_levels"][3]["sentiment"] == 2
    g.command("difficulty Impossible")
    assert g.city.treasury == 12000 and g.rules["difficulty"] == "Impossible"
    g.command("road 140 100 145 100")
    t = g.city.treasury
    g.command("difficulty Hard")                                    # after building: catalog only, no re-scale
    assert g.difficulty == "Hard" and g.city.treasury == t and g.cat.spec("house")["cost"] == 25
    try:
        g.command("difficulty Medium")
        raise AssertionError("unknown difficulty accepted")
    except CommandError:
        pass
    assert Game("sandbox_open", 1).cat.spec("house")["cost"] == 20      # catalogs are per game
    import sim.world as W                                           # per-map default (data/maps.json)
    W.MAP_INFO["sandbox"]["difficulty"], was = "Hard", W.MAP_INFO["sandbox"]["difficulty"]
    try:
        assert Game("sandbox", 1).difficulty == "Hard" and Game("sandbox", 1, difficulty="Easy").difficulty == "Easy"
    finally:
        W.MAP_INFO["sandbox"]["difficulty"] = was


def test_figure_slots_order():
    """Figure slots (model.Walkers; walkers.md 2.1 / 2.2): figure_create 0x004D9FD0 takes the head of a FIFO ring of free
    ids (1..1999 in a new city), figure_delete gives the id back at the tail; walkers_update 0x004CC8C0 runs slots
    1..1999 in order, so in a fight started by a (figure_fight_start 0x004D4BA0) the other one, b, takes its first
    fight tick in the same tick when its slot comes after a's (timer one ahead: it hits a tick earlier); a fighter
    whose foe fell sees it in the same tick when its slot comes after the killer's (bug 393)."""
    import pickle
    from sim.model import Walkers
    from sim.military import units
    from sim.systems import walkers
    g = Game("sandbox_open", 1)
    t = Walkers()
    ws = [walkers.new_walker(g, role="watchman", home=0, x=10, y=10) for _ in range(3)]
    for w in ws:
        t[w.id] = w
    assert [w.fslot for w in ws] == [1, 2, 3]
    t.pop(ws[1].id)
    assert ws[1].fslot == 0 and t.free[-1] == 2 and t.free[0] == 4     # back at the tail (FIFO reuse)
    t2 = pickle.loads(pickle.dumps(t))
    assert isinstance(t2, Walkers) and list(t2.free)[:2] == [4, 5] and t2[ws[2].id].fslot == 3
    old = Walkers.adopt({5: ws[0], 2: ws[2]})                          # a save from before the slots
    assert old[2].fslot == 1 and old[5].fslot == 2 and old.free[0] == 1999

    def man(x, y, delay=10 ** 6):
        m = walkers.new_walker(g, role="watchman", home=0, x=x, y=y)
        walkers.add(g, m, delay)
        m.dmg = -10 ** 6
        return m
    a, b = man(50, 50), man(50, 50)
    assert a.fslot < b.fslot
    T = g.tick
    g.__dict__["_pass"] = [[], a.fslot]                  # inside the walker pass, a acting
    units.start_fight(g, a, b)
    del g.__dict__["_pass"]
    assert a.anim_t0 == T and a.busy_until == T + 24
    assert b.anim_t0 == T - 1 and b.busy_until == T + 23  # b runs later in this tick: its first fight tick now
    c, d = man(60, 60), man(60, 60)
    g.__dict__["_pass"] = [[], d.fslot]                  # d moves onto c: c's slot came first, it waits a tick
    units.start_fight(g, d, c)
    del g.__dict__["_pass"]
    assert c.anim_t0 == T and c.busy_until == T + 24
    # a, b fight; e also fights b; b falls to a's hit inside the pass: e (a later slot) sees it this tick
    e = man(50, 50)
    units.start_fight(g, e, b)
    heap = []
    g.__dict__["_pass"] = [heap, a.fslot]
    units.kill(g, b, a)
    del g.__dict__["_pass"]
    assert (e.fslot, e.id) in heap and e.next_move == g.tick
    # the pass itself runs in slot order
    order = []
    import sim.systems.walkers as W
    real = W.act
    W.act = lambda g_, w: order.append(w.id)
    try:
        x1, x2 = man(70, 70, 1), man(70, 70, 1)
        g.walkers.pop(x1.id)
        g.walkers[x1.id] = x1                            # x1 takes a later slot than x2 now
        walkers.schedule(g, x1, 1)
        g.step(2)
    finally:
        W.act = real
    assert order.index(x2.id) < order.index(x1.id)


def test_scenario_start_year():
    """A new game starts in its episode's year (scenario block +0, episode_start_load); old saves keep 1000 BC."""
    g = Game("sandbox2", 1)
    assert g.start_year == -1750 and g.date().endswith("1750 BC"), g.date()
    g.__dict__.pop("year0")                                      # a save from before 10-30
    assert g.start_year == g.rules["start_year"] == -1000


def test_track1c_rules():
    """Track 1C (the stage plan): slider levels (0x00641F50 / 0x00641F38), health messages (0x005246B0)."""
    from sim.systems import health
    g = Game("sandbox_open", 1)
    assert g.command("tax 10") == "tax rate 9%" and g.command("tax 8") == "tax rate 7%"   # nearest, ties lower
    assert g.command("wage 33") == "wage rate 34" and g.command("wage 60") == "wage rate 40"
    g.city.population = 400
    st = health._st(g)
    st["health"] = 69
    health.health_message(g, 70, False)                     # tens digit 7 -> 6: 19:(147 + 68 / 10)
    assert g.city.messages[-1][1] == "Hygiene is good but worsening"
    n = len(g.city.messages)
    st["health"] = 68
    health.health_message(g, 69, False)                     # same tens digit: nothing
    st["health"] = 70
    health.health_message(g, 69, True)                      # up: 19:(157 + 69 / 10)
    assert len(g.city.messages) == n + 1 and g.city.messages[-1][1] == "Hygiene is very good and improving!"


def test_messages_with_tile():
    """The exe's messages with a tile (FUN_00521A70 types 0xDC / 0xDE with a tile) carry meta at (raw) and kind, so the
    message window shows its go-to button (msgwin.js): fire and collapse (0xDC, the building), plague (0xDC, the first
    infected house), a jealous god (0xDE, its tile), a god's help (0xDE, its figure's tile)."""
    from sim.systems import risk, health
    from sim.gods import figures, help as ghelp, rec
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("road 80 40 100 40")
    for x in range(80, 100, 2):
        g.command(f"build house {x} 41")
    hs = [b for b in g.buildings.values() if b.kind == "house"]
    for b in hs:
        b.occupants = 10
    def last():
        m = g.city.messages[-1][1]
        return getattr(m, "meta", {}) or {}
    risk.ignite(g, hs[0])
    assert last().get("at") == [hs[0].x, hs[0].y] and last().get("kind") == 0xDC
    health.outbreak(g)
    m = last()
    assert m.get("kind") == 0xDC and tuple(m["at"]) in {(b.x, b.y) for b in hs}
    figures.attack_start(g, 5)
    w = figures.figure(g, 5)
    assert w is not None and last().get("at") == [w.x, w.y] and last().get("kind") == 0xDE
    ghelp._granted(g, 5, True)
    assert last().get("at") == [w.x, w.y] and last().get("kind") == 0xDE
    ghelp._granted(g, 7, True)                   # Hermes: 0xE0, no button
    assert "at" not in last()


def test_test_commands():
    """sim/testcmds.py (decision 2026-10-31): test-only commands work but are warned and counted in the save;
    `testcmds off` refuses them (on again is counted); the live server's --no-test-commands (LOCKED) refuses them
    and `testcmds on`; player actions, settings and `heroes cheat off` are not test commands; old saves start at 0."""
    from sim import testcmds, render
    from sim.game import CommandError
    g = Game("sandbox_open", 1)
    assert "used: none" in render.status(g)
    out = g.command("funds 100")
    assert out.startswith("TEST COMMAND (funds, use 1;") and out.endswith("treasury 15100 dr")
    g.command("funds 1")
    g.command("empire attitude Sparta 50")
    assert g.command("heroes cheat off") == "hero cheat off"           # switching the cheat off: not counted
    assert g.command("tax 9") == "tax rate 9%" and g.command("gods") and g.command("military off")
    assert g.command("build endless_warehouse 137 125").startswith("TEST COMMAND (build endless_warehouse, use 1")
    assert g.test_uses == {"funds": 2, "empire attitude": 1, "build endless_warehouse": 1}
    assert "test commands off" in g.command("testcmds off")
    e = _raises(lambda: g.command("wolves 100 100"))
    assert isinstance(e, CommandError) and "testcmds on" in str(e)
    assert g.command("testcmds on").startswith("TEST COMMAND (testcmds on, use 1")
    g2 = pickle.loads(pickle.dumps(g))                                  # stored in the save
    assert g2.test_uses["testcmds on"] == 1 and g2.testcmds
    assert "used: build endless_warehouse 1, empire attitude 1, funds 2, testcmds on 1" in render.status(g2)
    testcmds.LOCKED = True                                              # live --no-test-commands
    try:
        assert "--no-test-commands" in str(_raises(lambda: g.command("invade")))
        assert "--no-test-commands" in str(_raises(lambda: g.command("testcmds on")))
        assert "off (this server)" in g.command("testcmds")
        assert g.command("tax 9") == "tax rate 9%"
    finally:
        testcmds.LOCKED = False
    old = Game("sandbox_open", 1)                                            # a save from before 10-31
    old.__dict__.pop("test_uses", None); old.__dict__.pop("testcmds", None)
    assert "test commands on; used: none" in render.status(pickle.loads(pickle.dumps(old)))


def test_month_message_order():
    """bugs.md 360: at a month change the episode's records post before the empire's run-time ones (a tribute claim:
    the exe keeps both in g_events, the run-time slots after the episode's, scenario_events_monthly 0x0046D380)."""
    from sim.campaign import flow
    g = flow.start("athens_through_the_ages", seed=1, difficulty="Easy")
    flow.briefed(g)
    D = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    seen = 0
    while g.date() != "Sep 799 BC":                   # Thermopylai, Knossos' request, Knossos' tribute claim
        g.step(D)
        new = [str(t) for _, t in g.city.messages[seen:]]
        seen = len(g.city.messages)
    new = [t for t in new if "out to destroy us" not in t and "launches invasion" not in t]   # invasions: their
    # pass runs first, their dates move with the random stream
    assert [t.split(".")[0] for t in new] == ["Thermopylai needs Food", "Knossos demands drachmas",
                                              "Knossos demands Tribute"], new


def test_names_with_spaces_every_command():
    """bugs.md 451 (the user, after 382 and 449: "check it doesn't exist anywhere else"): every command that takes a
    name keeps a multi-word one as one argument, on Zeus and Europa's world (ally Mt. Pelion 4, rival Mt. Cithaeron 8):
    city, gift, request (and its strike target), refuse, fulfil, raid / conquer with an ally, cityrequest, cityinvade,
    citystatus, empire attitude / army, build trading_post; monsters with spaces (Calydonian Boar, Black Warrior)."""
    from sim import episode, empire
    from sim.empire import diplomacy, war, requests as R
    from sim.heroes import commands as hc
    a = _campaign("zeus_and_europa")
    g = episode.new_city(a["source"] + "#0", _ep(a, 0), difficulty="Normal")
    P, C = "Mt. Pelion", "Mt. Cithaeron"
    seen = []
    keep = {}

    def stub(mod, name, f):
        keep[(mod, name)] = getattr(mod, name)
        setattr(mod, name, f)
    stub(empire, "describe", lambda g, c: seen.append(("city", c.name)) or "")
    stub(diplomacy, "gift", lambda g, c, item, size: seen.append(("gift", c.name, item, size)) or "")
    stub(diplomacy, "request", lambda g, c, item, t: seen.append(("request", c.name, item, t and t.name)) or "")
    stub(diplomacy, "fulfil", lambda g, c, i, ids: seen.append(("fulfil", c.name, i)) or "")
    stub(diplomacy, "city_request", lambda g, c, item, n, k, d: seen.append(("cityrequest", c.name, item, n))
         or dict(amount=n, item=item, id=0))
    stub(war, "attack", lambda g, c, raid, good, ally, *r: seen.append(("raid" if raid else "conquer", c.name, good, ally)) or "")
    stub(war, "invasion_create", lambda g, c, n: seen.append(("cityinvade", c.name, n)) or True)
    stub(R, "open_for", lambda g, cid: seen.append(("refuse", g.empire.cities[cid].name)) or [])
    try:
        for line in (f"city {P}", f"gift {P} wine small", f"request {P} strike {C}", f"fulfill {P} 0",
                     f"raid {C} wine with {P} companies none", f"conquer {C} with {P} companies 1 ships none",
                     f"cityrequest {P} wine 5", f"cityinvade {C} 4"):
            g.command(line)
        try:
            g.command(f"refuse {P}")
        except Exception as e:
            assert "Mt. Pelion has no outstanding" in str(e), e
    finally:
        for (mod, name), f in keep.items():
            setattr(mod, name, f)
    assert seen == [("city", P), ("gift", P, "wine", "small"), ("request", P, "strike", C), ("fulfil", P, 0),
                    ("raid", C, "wine", P), ("conquer", C, None, P), ("cityrequest", P, "wine", 5),
                    ("cityinvade", C, 4), ("refuse", P)], seen
    assert g.command(f"empire attitude {P} 55").endswith("Mt. Pelion: attitude 55")
    assert g.command(f"empire army {C} 7").endswith("Mt. Cithaeron: army 7")
    assert "Mt. Cithaeron" in g.command(f"citystatus {C} 0")
    names = []
    g.build = lambda key, x, y, extra=None: names.append(extra) or ""
    g.command(f"build trading_post 1 1 {P}")
    assert names == [P]
    mon = []
    g.command("heroes on")
    keep_m = hc._monster
    hc._monster = lambda g, t: mon.append(t) or keep_m(g, t)
    try:
        for line in ("monster Calydonian Boar 5 5", "monster Black Warrior aggr 1"):
            try:
                g.command(line)
            except Exception:
                pass                                # the module may refuse the event; the name is what counts
    finally:
        hc._monster = keep_m
    assert mon == ["Calydonian Boar", "Black Warrior"], mon


def test_strip_condensed_reason():
    """Bug 461: the panel strip's [reason_phrase] is the reason's CONDENSED phrase (FUN_00466AD0 sets 0x00916DF1,
    wm_sub_465EF0), not the full one the message window shows; the strip text is cut at 200 chars."""
    from types import SimpleNamespace
    from sim import messages
    from sim.empire import eventmsg
    g = Game("sandbox_open", 1)
    got = []
    g.message = lambda m: got.append(m)
    c = SimpleNamespace(name="Knossos", leader="Minos", nation=0)
    ev = dict(id=1, type=0, amount=10, item=None, lead=0, year=0, month=0)
    eventmsg.post(g, 908, 909, ev, reason_id=302, c=c, item="skeins of fleece", itemshort="Fleece", god="Zeus")
    m = got[-1].meta
    assert "took too long to respond" in m["body"], m["body"]
    assert m["condensed"] == "Knossos thinks less of you since you sent 10 skeins of fleece late.", m["condensed"]
    assert len(messages.strip_text("x" * 300)) == 200


def test_leader_name_in_save():
    """bugs.md 380: the leader name posted by play mode is kept in the save; a restart on it restores the name, and
    a game without one (new game, next episode) takes the running one's."""
    import tempfile
    from sim import live, messages
    from sim.game import Game
    old = messages.PLAYER
    try:
        messages.PLAYER = "Ruler"
        g = Game("sandbox_open")
        r = live.Runner(g, speed=30)
        assert getattr(g, "live_player", None) is None
        messages.PLAYER = "Darius"; r.g.live_player = messages.PLAYER   # what /control {player} does
        with tempfile.TemporaryDirectory() as d:
            g.save(d + "/a.pkl")
            messages.PLAYER = "Ruler"                                    # a new server process
            live.Runner(Game.load(d + "/a.pkl"), speed=30)
            assert messages.PLAYER == "Darius"
            g2 = Game("sandbox_open")
            live.Runner(g2, speed=30)
            assert g2.live_player == "Darius"
    finally:
        messages.PLAYER = old


def test_tick_order_cycle_step_before_pass():
    """simulation_tick 0x00513A30 runs the cycle step (month_advance after step 50), then walkers_update: Game.step
    counts the tick, runs run_day / run_step29, then move_all; a figure made in the day's work acts in that tick's
    pass. Between steps walkers.now is the next tick; a save from before (no tick_v) runs its pending pass on load."""
    import tempfile
    from sim import systems
    from sim.systems import walkers
    g = Game("sandbox_open", 1)
    seen = []
    orig = systems.run_day

    def day(g_):
        orig(g_)
        seen.append(("day", g_.tick, walkers.now(g_)))
    systems.run_day = day
    try:
        g.step(51)
    finally:
        systems.run_day = orig
    assert seen == [("day", 51, 51)] and walkers.now(g) == 52
    w = walkers.new_walker(g, role="watchman", home=0, x=100, y=100)
    walkers.add(g, w)                                    # a command: its first call is in the next tick's pass
    assert w.next_move == g.tick + 1
    walkers.schedule(g, w, 3)
    assert w.next_move == g.tick + 1 + 3
    g.walkers.pop(w.id)
    p = os.path.join(tempfile.mkdtemp(), "old.pkl")
    g.tick_v = 0                                          # an old save: the pass of its tick is still to run
    g.save(p)
    g2 = Game.load(p)
    assert g2.tick_v == 1 and g2.tick == g.tick and g.tick not in g2.queue


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])


def test_no_duplicate_functions():
    """bugs.md 484: navy.py defined _hunt twice, the enemy warship's replaced the player trireme's (it crashed the
    shared server's walker pass). No module of sim/ may define a top-level name twice."""
    import ast
    import collections
    import pathlib
    bad = []
    for p in sorted(pathlib.Path(ROOT, "sim").rglob("*.py")):
        c = collections.Counter(n.name for n in ast.parse(p.read_text()).body
                                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
        bad += [f"{p.relative_to(ROOT)}: {k}" for k, v in c.items() if v > 1]
    assert not bad, bad


def test_failed_walker_pass_requeues():
    """bugs.md 484: a walker's code raising in move_all left the rest of the tick's bucket unscheduled (they froze
    for good); now they act on the next tick, and Game.load repairs saves where walkers were lost."""
    from sim.systems import walkers
    g = play(1)
    due = sorted(((w.fslot, w.id) for w in g.walkers.values() if w.next_move == g.tick + 1))
    assert len(due) >= 3, len(due)
    first = g.walkers[due[0][1]]
    real = walkers.act
    def boom(gg, w):
        if w is first:
            raise RuntimeError("test")
        return real(gg, w)
    walkers.act = boom
    try:
        assert isinstance(_raises(lambda: g.step(1)), RuntimeError)
    finally:
        walkers.act = real
    g.__dict__.pop("_in_tick", None)
    rest = [g.walkers[i] for _, i in due[1:]]
    assert all(w.next_move == g.tick + 1 and w.id in g.queue[g.tick + 1] for w in rest)
    assert walkers.reschedule_lost(g) == 1          # the walker that raised: due in the past, now rescheduled
    assert walkers.reschedule_lost(g) == 0
    # a lost walker (as in the shared server's save): Game.load puts it back
    w = rest[0]
    g.queue[g.tick + 1].remove(w.id)
    w.next_move = g.tick - 100
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        g.save(os.path.join(d, "s.pkl"))
        h = Game.load(os.path.join(d, "s.pkl"))
    assert h.walkers[w.id].next_move == h.tick + 1 and w.id in h.queue[h.tick + 1]
    h.step(30)
