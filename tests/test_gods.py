"""Gods: sanctuaries' priests, jealousy, fights, help, sounds, permanent effects.
Run: python3 tests/test_sim.py gods (or a test by name: python3 tests/test_sim.py test_NAME)."""
import os

from helpers import ROOT, Game, play, pre_pass


def test_gods_sanctuary_priests_visits():
    """sim/gods (docs/logic/religion.md): the sandbox's Mythology menu offers only its friendly gods; a complete,
    fully staffed sanctuary sends a priest when its activity drops below 20, he fetches 400 food (no animal on the
    map) from the granary and the sacrifice
    sets the activity to 24; the god visits (road roam), may bless, and vanishes by its sanctuary."""
    from sim.systems import labor, monuments
    from sim import gods
    g = Game("sandbox_open", 1)
    g.city.treasury = 50000
    assert gods.menu(g) == ["sanctuary_zeus", "sanctuary_demeter", "sanctuary_artemis", "sanctuary_aphrodite",
                            "sanctuary_athena", "sanctuary_hades"]
    try:
        g.command("build sanctuary_hermes 100 34")
        assert False, "Hermes is unfriendly in the sandbox"
    except Exception as e:
        assert "cannot be built" in str(e)
    for c in ("road 86 33 115 33", "build granary 88 29", "build sanctuary_artemis 100 34", "jealous 99"):
        g.command(c)
    gr = next(b for b in g.buildings.values() if b.key == "granary")
    gr.goods["wheat"] = 800
    m = next(b for b in g.buildings.values() if b.key == "sanctuary_artemis")
    for p in m.misc["pieces"]:
        p["s"] = p["n"]
    orig = labor.allocate

    def staffed(g):
        orig(g)
        m.employees = g.cat.spec(m.key)["employees"]
    labor.allocate = staffed
    try:
        g.step(g.rules["ticks_per_day"])
        assert monuments.complete(m) and m.misc["activity"] == 22 and gods.active(g, "artemis")
        assert "sanctuary_artemis" not in gods.menu(g)
        m.misc["activity"] = 19
        seen = set()
        for _ in range(60):
            g.step(g.rules["ticks_per_day"])
            seen |= {w.role for w in g.walkers.values()}
            if m.misc["activity"] == 24:
                break
        assert "priest" in seen and m.misc["activity"] == 24 and gr.goods.get("wheat", 0) in (0, 400)
        g.gods["jealousy"] = 99
        m.misc["visit_timer"] = 0
        for _ in range(40):
            g.step(g.rules["ticks_per_day"])
            if any(w.role == "god" for w in g.walkers.values()):
                break
        god = next(w for w in g.walkers.values() if w.role == "god")
        assert god.god == 4 and god.home == m.id
        for _ in range(40):
            g.step(g.rules["ticks_per_day"])
            if god.id not in g.walkers:
                break
        assert god.id not in g.walkers and any("visits" in t for _, t in g.gods["log"])
    finally:
        labor.allocate = orig


def test_gods_jealousy_attack():
    """jealousy_update 0x004F0B50: an empty sandbox gets a jealous friendly god every 6..12 months (oracle
    open-play-events: 25 in 19.5 years); a jealous god only roams the roads 548 ticks (0x56 / 0x57, oracle 1H-god)
    and vanishes; an attacking god of a scenario invasion curses / destroys / kills and leaves (budgets)."""
    g = Game("sandbox_open", 1)
    g.step(g.rules["ticks_per_day"] * 16 * 60)
    months = [t // (g.rules["ticks_per_day"] * 16) for t, s in g.gods["log"] if "(jealous)" in s]
    assert 4 <= len(months) <= 10 and all(6 <= b - a <= 12 for a, b in zip(months, months[1:]))
    for c in ("road 86 33 115 33", "build granary 88 29", "build granary 96 29"):
        g.command(c)
    out = g.command("godattack demeter")
    assert "attacks" in out
    t0 = g.tick
    for _ in range(40):
        g.step(g.rules["ticks_per_day"])
        if not any(w.role == "god" for w in g.walkers.values()):
            break
    assert sum(b.key == "granary" for b in g.buildings.values()) == 2          # the jealous god harms nothing
    from sim.gods.attack import dur
    lo = 548 + 10 + dur(2, 3)                          # + 0x0A: 10 hidden, then the appear group at rate 100 (bug 393)
    assert lo <= g.tick - t0 <= lo + 2 * g.rules["ticks_per_day"]
    g = Game("sandbox_open", 1)                       # a scenario invasion (type 27): the attack proper
    for c in ("road 86 33 115 33", "build granary 88 29", "build granary 96 29"):
        g.command(c)
    out = g.command("godattack demeter scenario")
    for _ in range(200):
        g.step(g.rules["ticks_per_day"])
        if not any(w.role == "god" for w in g.walkers.values()):
            break
    log = [t for _, t in g.gods["log"]]
    assert sum("Demeter destroys the Granary" in t for t in log) == 2
    assert not any(b.key == "granary" for b in g.buildings.values())
    assert not any(w.role == "god" for w in g.walkers.values())


def test_gods_fights():
    """sim/gods fight.py / bolts.py (religion.md "Gods fighting"): Athena hunts an invasion with bolts (0x51..0x53),
    Artemis shoots a wolf that reached its prey (0x0056AF80), Apollo is sent at a new monster (0x4A/0x4B/0x50),
    Ares attacks with his army of 8 (FUN_00504650) and Zeus, the defender, drives him off; Dionysus' 3 followers;
    the god's voice line with the invasion message (FUN_005A1050 kind 3)."""
    import collections
    from sim.systems import labor
    from sim import gods
    from sim.gods import fight, rec, bolts
    shots, shoot = [0], bolts.shoot

    def counted(*a, **kw):
        shots[0] += 1
        return shoot(*a, **kw)

    def city(keys, friends=()):
        g = Game("sandbox_open", 1)
        g.city.treasury = 500000
        for i in friends:
            r = rec(g, i)
            r["unfriendly"], r["listed"], r["jealous"] = 0, 1, 1
        g.command("road 86 33 115 33")
        ms = []
        for k, x in zip(keys, (100, 86)):
            g.command(f"build sanctuary_{k} {x} 34")
            m = next(b for b in g.buildings.values() if b.key == f"sanctuary_{k}")
            for p in m.misc["pieces"]:
                p["s"] = p["n"]
            m.misc["visit_timer"] = 10 ** 6
            ms.append(m)
        orig = labor.allocate

        def staffed(g):
            orig(g)
            for m in ms:
                m.employees = g.cat.spec(m.key)["employees"]
        labor.allocate = staffed
        g.step(g.rules["ticks_per_day"])
        shots[0] = 0
        return g, orig

    def days(g, n, stop=None):
        seen = collections.Counter()
        for _ in range(n):
            g.step(g.rules["ticks_per_day"])
            seen |= collections.Counter(w.role for w in g.walkers.values())
            if stop and stop(g):
                break
        return seen

    def log(g):
        return [t for _, t in g.gods["log"]]

    bolts.shoot = counted
    g, orig = city(["athena"])
    try:
        g.command("invade 150 60 16 0")
        g.step(g.rules["ticks_per_day"] * 2)
        assert fight.athena_month(g) is not None
        seen = days(g, 120, lambda g: not any(w.role.startswith("enemy_") for w in g.walkers.values()))
        assert shots[0] and not any(w.role.startswith("enemy_") for w in g.walkers.values())
        assert "Athena goes to fight the invaders" in log(g)
    finally:
        labor.allocate = orig

    g, orig = city(["artemis"])
    try:
        g.command("wolves 120 50")
        wolf = next(w for w in g.walkers.values() if w.role == "wolf")
        assert gods.summon_artemis(g, wolf) is not None
        # the bolts fly the exe's fine line (defences.Flight): the first one hits another wolf of the pack on a tile the
        # old whole-tile line skipped, the next one this wolf
        days(g, 8, lambda g: wolf.id not in g.walkers or wolf.anim == "die")
        assert (wolf.id not in g.walkers or wolf.anim == "die") and "Artemis comes to fight the wolf" in log(g)
    finally:
        labor.allocate = orig

    g, orig = city(["apollo"], friends=(3,))
    try:
        g.command("heroes on")
        g.command("monster maenads")
        m = next(w for w in g.walkers.values() if w.role == "monster")
        days(g, 10)
        assert m.id not in g.walkers and "Apollo defeats the Maenad" in log(g)
    finally:
        labor.allocate = orig

    g, orig = city(["zeus"])
    try:
        g.command("godattack ares scenario")
        assert g.city.messages[-1][1].meta["voice"] == "Voice/Walker/are_ev_4.mp3"        # FUN_005A1050(5, 3)
        seen = days(g, 120, lambda g: not any(w.role == "god" for w in g.walkers.values()))
        assert seen["enemy_infantry"] == 8 and shots[0]
        assert "Zeus defeats Ares" in log(g)
        g.command("godattack dionysus scenario")
        # followers walk (fig_handler_piper_follower 0x004C9F30, route mode 10): one tile a step, never a jump; at the
        # god's leave Dionysus' own satyrs are unchained and walk out by the land entry (0x004EF0F0)
        pos, jumps, entranced, left = {}, 0, 0, set()
        for _ in range(120 * g.rules["ticks_per_day"]):
            g.step(1)
            fs = [w for w in g.walkers.values() if w.role == "entranced"]
            entranced = max(entranced, len(fs))
            for w in fs:
                p0 = pos.get(w.id)
                jumps += p0 is not None and max(abs(p0[0] - w.x), abs(p0[1] - w.y)) > 1
                pos[w.id] = (w.x, w.y)
            left |= {i for i in pos if i not in g.walkers}
            if not any(w.role in ("god", "entranced") for w in g.walkers.values()):
                break
        assert entranced >= 3 and jumps == 0 and len(left) >= 3
    finally:
        labor.allocate = orig
        bolts.shoot = shoot


def test_gods_rate100_looks():
    """Bug 393: figure_god_handler's tail steps appear / cast / attack (and the fights' vanish) with sprite_anim_step
    rate 100: a frame per gate 0x006668EC[image speed] = ceil(20 * speed / 22) ticks at the default game speed. The
    appear (0x0A) ends on its last frame: 10 hidden + frames x ticks per frame; the 0x0B vanish stays one a tick;
    the visible archer's shot (action 6): the arrow at frame 1, the reload from the wrap (n x p)."""
    import json
    from sim.gods import figures, attack
    from sim.military import invaders, units
    from sim.systems import walkers
    T = json.load(open(os.path.join(ROOT, "data", "gods.json")))
    assert T["frame_ticks"][0] == [3, 3, 2, 3, 4] and T["image_speed"][7][1] == 1 and T["frame_ticks"][7][1] == 1
    assert all(t == max(1, -(-20 * s // 22)) for r, q in zip(T["image_speed"], T["frame_ticks"]) for s, t in zip(r, q))
    g = Game("sandbox_open", 1)
    g.command("road 86 33 115 33")
    with pre_pass(g) as t0:
        w = figures._spawn(g, 2, 100, 33, "visit")               # Demeter: appear 18 frames x 4 ticks
        assert attack.dur(2, 3) == 18 * 4 and w.next_move == t0 + 10 + 72
        h = figures.look(g, w)
    assert h[8] == "appear" and h[2] - h[1] == 72
    while w.task == "appear":
        g.step(1)
    assert g.tick - t0 == 10 + 72                                # acted in tick 82 (the pass runs at g.tick)
    with pre_pass(g) as t:
        figures._leave(g, w)                                     # 0x0B: rate 0
        assert figures.look(g, w)[8] == "vanish" and w.next_move == t + attack.frames(2, 1)
        figures._leave(g, w, gated=True)                         # action 4: rate 100
        assert figures.look(g, w)[8] == "vanish_gated" and w.next_move == t + attack.dur(2, 1)
    # the archer's shot
    g = play(1, "boom.txt")
    g.command("invade")
    a = next(x for x in g.walkers.values() if x.role == "enemy_archer")
    a.hidden, a.appear = False, 0
    from sim.military.defences import line_of_fire
    tx, ty = next((a.x + dx, a.y + dy) for dx, dy in ((0, 3), (3, 0), (0, -3), (-3, 0), (2, 2), (-2, 2), (2, -2), (-2, -2))
                  if g.world.inside(a.x + dx, a.y + dy) and line_of_fire(g, (a.x, a.y), (a.x + dx, a.y + dy)))
    t = walkers.new_walker(g, role="watchman", home=0, x=tx, y=ty)
    walkers.add(g, t, 100000)
    from sim.military import contact
    contact.cache(g).pop("tidx", None)                           # the per-tick figure index
    comp = invaders.ecomps(g)[a.company]
    a.next_shot = 0
    with pre_pass(g) as T0:
        assert invaders._try_shoot(g, a, comp)
        look2 = invaders.look(g, a)[2]
    n, p = invaders.shot_frames(a)
    sf = invaders.shot_frame(a)                                  # SHOT[0] = 8 (0x005011C0)
    arrows = lambda: sum(x.role == "enemy_arrow" for x in g.walkers.values())   # noqa: E731
    # frame 1 on the shot's tick (archer_try_shoot sets 0, the tail steps it), frame k at T0 + (k - 1) p; the wrap at
    # T0 + (n - 1) p (oracle 1B-inv-city under p = 1: shot 376, arrow 384, wrap 387, next shot 478; bug 435)
    assert (n, p, sf) == (12, 4, 8) and a.shot_end == T0 + (n - 1) * p and look2 == T0 + 44
    while arrows() == 0 and g.tick < T0 + 60:
        g.step(1)
    assert g.tick == T0 + (sf - 1) * p + 1                       # the logic sees frame 8 the tick after it is drawn
    while invaders.in_shot(a):
        g.step(1)
    assert g.tick == T0 + (n - 1) * p and a.next_shot == T0 + (n - 1) * p + units.col(g, a, "missile_rate") + 1


def test_gods_jealous_reuses_attacker():
    """Bug 234 (as exe): a jealous draw of a god that is attacking (here a forced scenario Demeter invasion; in the
    sandbox only unfriendly gods invade by event, and those are never jealous) reuses its figure: god_attack_start ->
    god_figure_spawn 0x004E8A30 (figure_place_on_tile on the god's existing figure) -> action 10 -> 0x56 / 0x57: the
    attack's budgets go unused; a bolt already flying still lands (fig_handler_enemy_missile does not check its
    owner's action)."""
    from sim import gods
    g = Game("sandbox_open", 1)
    for c in ("road 86 33 115 33", "build granary 88 29", "build granary 96 29", "days 1"):
        g.command(c)
    st = gods.state(g)
    st["jealousy"] = 99
    g.command("godattack demeter scenario")
    fid = st["rec"][2]["figure"]
    while not any("destroys" in s for _, s in st["log"]):
        g.step(1)
    for i in range(14):
        st["rec"][i]["jealous"] = int(i == 2)
    st["jealousy"] = 1
    while not any("(jealous)" in s for _, s in st["log"]):
        g.step(1)
    w = g.walkers[st["rec"][2]["figure"]]
    assert w.id == fid and (w.x, w.y) == (167, 167) and w.task == "appear" and w.next_task == "jealous"


def test_gods_sounds():
    """Figure sounds the frames' looks cannot tell (sim walkers.sfx -> frame "sfx", gods.js): Zeus' bolts at an
    attacking Athena: G_zeus_hit on a hit she survives (figure_hit -> FUN_004DB7A0), G_miss on a bolt that hits
    nothing (FUN_004DC180(god, 13)); Dionysus' entrancing walk: the atk1/atk2 loop for 400 ticks
    (god_entrance_roam_tick -> FUN_004DB3D0(god, 0))."""
    import collections
    from sim.systems import labor

    def run(g, god, n):
        g.sfx = []
        g.command(f"godattack {god} scenario")
        for _ in range(n):
            g.step(g.rules["ticks_per_day"])
            if not any(w.role == "god" for w in g.walkers.values()):
                break
        return collections.Counter((e[6], e[5]) for e in g.sfx), g.sfx

    g = Game("sandbox_open", 1)
    g.city.treasury = 500000
    g.command("road 86 33 115 33")
    g.command("build palace 92 24")
    g.step(g.rules["ticks_per_day"])
    seen, ev = run(g, "dionysus", 120)
    charm = [e for e in ev if e[6] == "charm"]
    assert seen[("charm", 10)] == 1 and charm[0][7] == charm[0][0] + 400, seen
    g.command("build sanctuary_zeus 100 34")
    m = next(b for b in g.buildings.values() if b.key == "sanctuary_zeus")
    for p in m.misc["pieces"]:
        p["s"] = p["n"]
    m.misc["visit_timer"] = 10 ** 6
    orig = labor.allocate

    def staffed(g):
        orig(g)
        m.employees = g.cat.spec(m.key)["employees"]
    labor.allocate = staffed
    try:
        g.step(g.rules["ticks_per_day"])
        from sim.gods import rec, GODS
        rec(g, GODS.index("athena"))["unfriendly"] = 1   # an attacking god (class 10): Zeus' 0x2D bolts hit only those,
        seen, _ = run(g, "athena", 60)                    # her 0x34 bolts skip class-10 gods (herself on her tile)
        assert seen[("hit", 0)], seen
        from sim.gods import bolts, figures              # a bolt to an empty tile: G_miss at the line's end
        z = figures.figure(g, 0) or figures._spawn(g, 0, 100, 33, "defend")
        z.task = "defend"
        g.sfx = []
        b = bolts.shoot(g, z, (z.x - 5, z.y - 5), 0x2D)
        for _ in range(40):
            g.step(1)
            if b.id not in g.walkers:
                break
        assert b.id not in g.walkers and [e for e in g.sfx if e[6] == "miss" and e[5] == 0], g.sfx
    finally:
        labor.allocate = orig


def test_gods_help_zeus_aphrodite():
    """gifts.py: a prayer to Zeus with an army on the map (zeus_help 0x004E6B80): he vanishes at his sanctuary,
    appears by the largest formation, 5 bolts, then every invader falls (0x13); Aphrodite's help (0x004E77E0 /
    FUN_004C56F0): she walks 9 tiles out, waits 100 ticks, and each house with room takes up to 4 people. The prayer's
    result code and Consult Oracle's counter (oracle_consult 0x004EA630)."""
    from sim.systems import labor
    from sim import gods
    from sim.gods import rec
    g = Game("sandbox_open", 1)
    g.city.treasury = 500000
    g.command("road 86 33 115 33")
    for k, x in (("zeus", 100), ("aphrodite", 86)):
        g.command(f"build sanctuary_{k} {x} 34")
    ms = [b for b in g.buildings.values() if b.key.startswith("sanctuary_")]
    for m in ms:
        for p in m.misc["pieces"]:
            p["s"] = p["n"]
    orig = labor.allocate

    def staffed(g):
        orig(g)
        for m in ms:
            m.employees = g.cat.spec(m.key)["employees"]
    labor.allocate = staffed
    try:
        g.step(g.rules["ticks_per_day"])
        for m in ms:
            m.misc["activity"] = 22
        g.command("invade 150 60 16 0")
        g.step(g.rules["ticks_per_day"] * 2)
        out = g.command("pray zeus")
        assert "grants" in out, out
        for _ in range(30):
            g.step(g.rules["ticks_per_day"])
            if not any(w.role.startswith("enemy_") for w in g.walkers.values()):
                break
        assert not any(w.role.startswith("enemy_") for w in g.walkers.values())
        assert "Zeus strikes down the invaders" in [t for _, t in g.gods["log"]]
        assert out.startswith("result 2")                           # sanctuary_pray_click: granted
        g.command("oracle zeus")                                    # oracle_consult: +18 >= threshold 14
        assert rec(g, 0)["oracle"] == 18 and "unavailable" in g.command("oracle zeus")
        for i in range(6):
            g.command(f"build house {88 + 2 * i} 31")
        hs = [b for b in g.buildings.values() if b.kind == "house"]
        out = g.command("pray aphrodite")
        assert "grants" in out, out
        fills = sum(t == "Aphrodite fills the houses" for _, t in g.gods["log"])
        for _ in range(20):
            g.step(g.rules["ticks_per_day"])
            if sum(t == "Aphrodite fills the houses" for _, t in g.gods["log"]) > fills:
                break
        assert hs and all(h.occupants >= 4 for h in hs), [h.occupants for h in hs]
    finally:
        labor.allocate = orig


def test_gods_help_hades_athena():
    """gifts.py: Hades' prayer (hades_help 0x004E81A0, FUN_004C4BC0): 8 miners dig at his precinct (408 ticks), then
    he walks to the palace and the treasury gets 3200; Athena's (athena_help 0x004E7C50, FUN_004C4D50): 8 growers tend
    her grove, then she brings 1600 olives and 1600 oil to the storehouse with the most room (FUN_004C46D0)."""
    import collections
    from sim.systems import labor
    g = Game("sandbox_open", 1)
    g.city.treasury = 500000
    for c in ("road 86 33 115 33", "build storehouse 88 30", "build palace 92 24", "build sanctuary_hades 86 34",
              "build sanctuary_athena 100 34"):
        g.command(c)
    ms = [b for b in g.buildings.values() if b.key.startswith("sanctuary_")]
    st = next(b for b in g.buildings.values() if b.key == "storehouse")
    assert len(ms) == 2
    for m in ms:
        for p in m.misc["pieces"]:
            p["s"] = p["n"]
    orig = labor.allocate

    def staffed(g):
        orig(g)
        for b in ms + [st]:
            b.employees = g.cat.spec(b.key)["employees"]
    labor.allocate = staffed
    try:
        g.step(g.rules["ticks_per_day"])
        for m in ms:
            m.misc["activity"] = 22
        t0 = g.city.treasury
        assert g.command("pray hades").startswith("result 2")
        assert g.command("pray athena").startswith("result 2")
        seen = collections.Counter()
        for _ in range(40):
            g.step(g.rules["ticks_per_day"])
            seen |= collections.Counter(w.good for w in g.walkers.values() if w.role == "god_helper")
            log = [t for _, t in g.gods["log"]]
            if any("drachmas of silver" in t for t in log) and any("olives" in t for t in log):
                break
        assert seen["miner"] == 8 and seen["grower"] == 8, seen
        assert any("brings 3200 drachmas" in t for t in log), log
        assert st.goods.get("olives", 0) == 1600 and st.goods.get("olive_oil", 0) == 1600, st.goods
    finally:
        labor.allocate = orig


def test_gods_help_ares_hermes():
    """aid.py: Ares (ares_help 0x004E7610) joins a prayed-for expedition: the vanish group, hidden until the battle,
    the enemy counts 50 % (flag 0x1000), then he walks home; Hermes (hermes_help 0x004E7980): one open request is
    fulfilled for free, several -> message 0x734/0xB8E + pending, then the player's next request costs nothing
    (hermes_request_auto 0x004E7C00)."""
    from sim import gods
    from sim.gods import help as gh
    g = Game("sandbox_open", 1)
    g.city.treasury = 500000
    st = gods.state(g)
    st["free"] = True
    for i in (5, 7):
        st["rec"][i].update(unfriendly=0, listed=1)
    g.command("road 86 33 115 33")
    g.command("build sanctuary_ares 86 34")
    m = next(b for b in g.buildings.values() if b.key == "sanctuary_ares")
    for p in m.misc["pieces"]:
        p["s"] = p["n"]
    g.step(g.rules["ticks_per_day"])
    m.misc["activity"] = 22
    assert gods.built(g, 5)
    assert g.command("pray ares").startswith("result 1")          # no expedition yet: queued
    g.companies = {1: {"type": "hoplite", "members": 8}, 2: {"type": "horseman", "members": 8}}
    g.command("empire army Sparta 40")
    g.command("raid Sparta")
    ev = next(e for e in g.empire.events if e["type"] == "expedition")
    assert ev.get("god_help") and not st["rec"][5]["pending"]
    w = g.walkers[st["rec"][5]["figure"]]
    assert w.task == "ares" and gods.look(g, w)[8] == "vanish" and gods.look(g, w)[10] is None
    g.step(60)
    assert w.hidden and gods.look(g, w)[0] == "hidden"
    g.command("months 6")
    assert any("Battle at Sparta: your 24 against 20: victory" in t for _, t in g.city.messages), \
        [t for _, t in g.city.messages if "Battle" in t]
    assert st["rec"][5]["figure"] == 0 or g.walkers.get(st["rec"][5]["figure"]) is None
    # Hermes
    st["rec"][7]["prayer"] = 0
    g.command("cityrequest Tiryns fleece 5")
    g.command("cityrequest Tiryns wine 5")
    gh.god_help(g, 7, True, False)
    assert st["rec"][7]["pending"] and any("Hermes will fulfill" in t_ for _, t_ in g.city.messages)
    out = g.command("fulfil Tiryns")
    assert out.startswith("Hermes pays") and not st["rec"][7]["pending"], out
    st["rec"][7]["prayer"] = 0
    gh.god_help(g, 7, True, False)                                 # one open request left: fulfilled at once
    reqs = [e for e in g.empire.events if e["type"] == "request"]
    # the 'requests by' rows follow the request list (qsort by months: equal months keep its tie order)
    assert all(e["state"] == 3 for e in reqs) and sum(bool(e.get("hermes")) for e in reqs) == 1, reqs


def test_gods_help_apollo_dionysus():
    """gifts.py: Apollo's prayer heals the plague (apollo_help 0x004E71F0 -> city_heal_plague 0x004C5690: the houses'
    infection cleared, health + 50); Dionysus' brings 1600 wine to the storehouse with the most room (0x004E8010)."""
    from sim.systems import labor, health
    from sim.gods import rec
    g = Game("sandbox_open", 1)
    g.city.treasury = 500000
    for i in (3, 10):
        r = rec(g, i)
        r["unfriendly"], r["listed"], r["jealous"] = 0, 1, 1
    for c in ("road 86 33 115 33", "build storehouse 88 30", "build house 92 31", "build sanctuary_apollo 86 34",
              "build sanctuary_dionysus 100 34"):
        g.command(c)
    ms = [b for b in g.buildings.values() if b.key.startswith("sanctuary_")]
    st = next(b for b in g.buildings.values() if b.key == "storehouse")
    hs = next(b for b in g.buildings.values() if b.kind == "house")
    for m in ms:
        for p in m.misc["pieces"]:
            p["s"] = p["n"]
    orig = labor.allocate

    def staffed(g):
        orig(g)
        for b in ms + [st]:
            b.employees = g.cat.spec(b.key)["employees"]
    labor.allocate = staffed
    try:
        g.step(g.rules["ticks_per_day"])
        for m in ms:
            m.misc["activity"] = 22
        hs.misc["infected"] = 30
        health._st(g)["health"] = 20
        assert g.command("pray apollo").startswith("result 2")
        assert g.command("pray dionysus").startswith("result 2")
        for _ in range(20):
            g.step(g.rules["ticks_per_day"])
            log = [t for _, t in g.gods["log"]]
            if any("heals the city" in t for t in log) and any("wine" in t for t in log):
                break
        assert not hs.misc.get("infected") and health._st(g)["health"] >= 69, health._st(g)
        assert st.goods.get("wine", 0) == 1600, st.goods
    finally:
        labor.allocate = orig


def test_monster_turns_on_god():
    """Apollo sent at a new monster (0x4A/0x4B): the target turns on the god (0x004EAA60: a monster -> action 9 at it)
    and falls to his bolts (0x50: action 4); the event counts it killed (sim/gods fight.py + sim/heroes)."""
    from sim.systems import labor
    from sim.gods import rec
    g = Game("sandbox_open", 1)
    g.city.treasury = 500000
    r = rec(g, 3)
    r["unfriendly"], r["listed"], r["jealous"] = 0, 1, 1
    g.command("road 86 33 115 33")
    g.command("build sanctuary_apollo 100 34")
    m = next(b for b in g.buildings.values() if b.key == "sanctuary_apollo")
    for p in m.misc["pieces"]:
        p["s"] = p["n"]
    m.misc["visit_timer"] = 10 ** 6
    orig = labor.allocate

    def staffed(g):
        orig(g)
        m.employees = g.cat.spec(m.key)["employees"]
    labor.allocate = staffed
    try:
        g.step(51)
        g.command("monster maenads")
        mon = next(w for w in g.walkers.values() if w.role == "monster")
        turned = False
        for _ in range(10 * 51):
            g.step(1)
            apollo = next((w for w in g.walkers.values() if w.role == "god"), None)
            turned |= bool(apollo and mon.act == 9 and mon.tf == apollo.id)
            if mon.id not in g.walkers:
                break
        assert turned and mon.id not in g.walkers
    finally:
        labor.allocate = orig


def test_god_meets_monster_only_apollo():
    """figure_tile_contact 0x004D4DA0: a god (0x43) and a monster (0x44) on one tile fight only when the god passes
    FUN_004D4910 (Apollo, class 9, sanctuary placed and active); any other god ends the contact, either side moving
    (bug 439: visiting Ares and Artemis beat Talos to death). A guardian and a bad monster do fight (g_hostility
    7 <-> 8)."""
    from types import SimpleNamespace
    from sim.gods import figures
    import sim.gods as gods
    from sim.military import contact
    from sim.heroes import guardians, data as hdata
    orig = gods.active
    gods.active = lambda g, j: j == 3                               # Apollo's sanctuary active, no other
    try:
        for i, ok in ((5, False), (4, False), (3, True)):
            for mover in ("god", "monster"):
                g = Game("sandbox_open", 1)
                g.command("monster talos")
                talos = next(w for w in g.walkers.values() if w.role == "monster")
                gods.rec(g, i)["unfriendly"] = 0                    # a friendly god: class 9
                god = figures._spawn(g, i, talos.x, talos.y, "visit")
                god.state = ""
                got = contact.on_enter(g, god) if mover == "god" else contact.figure_contact(g, talos, god)
                assert got is ok and (god.anim == "fight") is ok and (talos.anim == "fight") is ok, (i, mover)
    finally:
        gods.active = orig
    g = Game("sandbox_open", 1)
    g.command("monster talos")
    talos = next(w for w in g.walkers.values() if w.role == "monster")
    mid = next(m["id"] for m in hdata()["monsters"] if m["name"] == "Dragon")
    dragon = guardians.spawn(g, mid, 5, SimpleNamespace(x=talos.x, y=talos.y, id=0, access=None))
    dragon.x, dragon.y = talos.x, talos.y
    assert contact.figure_contact(g, dragon, talos) and dragon.anim == "fight" and talos.anim == "fight"


def test_sanctuary_effects():
    """Bug 296 (religion.md "Permanent effects"): with a god's sanctuary active, Aphrodite: house desirability gates
    - 10; Athena: + 4 missile armour for soldiers and heroes; Hermes: carts x 133 / 100, traders x 150 / 100, trader
    countdown x 66 / 100; Atlas: stonecutters 0x435 ticks; Poseidon: fishing x 66 / 100 (C division)."""
    from sim import gods
    from sim.systems import housing, walkers
    from sim.military import units
    g = Game("sandbox_open", 1)
    on = set()
    old = gods.active, gods.active_now
    gods.active = gods.active_now = lambda g_, i: i in on
    try:
        h = g.cat.houses[3]
        W = lambda role: type("W", (), dict(role=role, rem=0))()
        base = (housing.des_gate(g, h), units.col(g, W("hoplite"), "missile_armor"),
                walkers.speed(g, W("cart")), walkers.speed(g, W("trader")), walkers.speed(g, W("ship")))
        on.update((6, 7, 8))
        assert housing.des_gate(g, h) == (base[0][0] - 10, base[0][1] - 10)
        assert units.col(g, W("hoplite"), "missile_armor") == min(base[1] + 4, 19)
        assert units.col(g, W("watchman"), "missile_armor") == units.stats(g, W("watchman"))["missile_armor"]
        assert (walkers.speed(g, W("cart")), walkers.speed(g, W("trader")), walkers.speed(g, W("ship"))) == (
            base[2] * 133 // 100, base[3] * 150 // 100, base[4] * 150 // 100) == (7, 9, 16)
        assert walkers.speed(g, W("sheep")) == 6
    finally:
        gods.active, gods.active_now = old


def test_gods_help_hera_gifts():
    """Gods' help audit (docs/logic/religion.md "What each god's help does"): Hera's need (hera_help 0x004E8430: half
    the vendors' agoras want more and their buyers found no supply) and her blessing (FUN_004C59A0: every staffed
    vendor's good + 800 with 1..3 vendors, food as wheat, capped 1100 / 800); god_gifts_deliver 0x004E6780 puts a
    gift's leftover into storage the next day (Demeter: wheat / carrots / onions in goods-list order)."""
    from sim.game import Game
    from sim.systems import agora, index
    from sim.gods import gifts, help as H, rec
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    e = g.world.entry
    for c in (f"road {e[0]} {e[1] - 40} {e[0]} {e[1]}", f"build agora {e[0]} {e[1] - 18} right"):
        g.command(c)
    a = next(x for x in g.buildings.values() if x.kind == "agora")
    st = agora.stalls(g, a)
    g.command(f"build food_vendor {st[0].x} {st[0].y}")
    g.command(f"build fleece_vendor {st[1].x} {st[1].y}")
    vs = [s for s in index.of(g, "stall") if s.key != "empty_stall"]
    assert len(vs) == 2 and not gifts.hera_need(g)
    vs[0].reason = "no storage with food within 40 tiles"
    assert gifts.hera_need(g)                                   # 1 of 2 = 50 %
    for s in vs:
        s.employees = 5
    a.goods = {"wheat": 900, "fleece": 100}
    assert gifts.hera_bless(g) == 2 and a.goods == {"wheat": 1100, "fleece": 800}
    g.command(f"build granary {e[0] + 3} {e[1] - 30}")         # some room for wheat
    H.gift_leftover(g, 2, 500, 0)
    H.deliver_gifts(g, 2)
    # the first of wheat / carrots / onions on the goods list (goods order: carrots 5 first)
    assert [b.goods for b in index.of(g, "storage")] == [{"carrots": 500}] and not rec(g, 2)["gift_active"]


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])
