"""Heroes and monsters: lairs, halls, duels, rampages, guardians, sounds.
Run: python3 tests/test_sim.py heroes (or a test by name: python3 tests/test_sim.py test_NAME)."""
import os
import sys

from helpers import ROOT, Game, _campaign, _ep


def test_heroes_monsters():
    """sim/heroes (docs/logic/heroes-monsters.md): a monster at its lair smashes what is built near it; the hall,
    Send For, the hero's arrival, the 300-tick duel, the event's end; a quest with its statue."""
    from sim import heroes
    from sim.heroes import events as hev
    g = Game("sandbox_open", 1)
    g.command("monster maenads")
    m = [w for w in g.walkers.values() if w.role == "monster"]
    g.step(2)                                    # monster_spawn_and_act(6, 7): home at once, then the rest timer
    assert len(m) == 1 and (m[0].x, m[0].y) == (122, 201) and m[0].timer >= 10000      # lair slot 2 (logical 121, 200), aggr 0
    g.command("build bench 122 198")
    g.step(g.rules["ticks_per_day"] * 40)
    assert not [b for b in g.buildings.values() if b.key == "bench"]                      # smashed
    assert heroes.heroes.record(g, 0)["needed"]                                            # Achilles (Maenads)
    g.command("heroes cheat")
    g.command("build heroes_hall 144 183 achilles")      # out of the Maenads' roam (at 136 183 they smash it first)
    g.command("road 143 187 150 187")
    g.command("sendfor achilles")
    g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"] * 6)
    assert heroes.heroes.present(g, 0)
    assert not [w for w in g.walkers.values() if w.role == "monster"]                      # the duel
    ev = [e for e in hev.records(g) if e["type"] == 26 and e["item"] == 2 and e["flags"] & 0x100]
    assert ev and ev[0]["state"] == 5
    from sim.empire import war                       # expedition_send_forces 0x004DEB30: the enlisted hero walks out
    ach = heroes.heroes.figure(g, 0)
    war.attack(g, g.empire.find("Sparta"), True, slots=[], ships=[], heroes=[0])
    assert ach.act == 14 and not ach.hidden and war.heroes_present(g) == []
    g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"] * 2)
    assert ach.act == 16 and ach.hidden and (ach.x, ach.y) == tuple(g.world.exit)      # hidden on the exit tile
    g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"] * 8)                    # the army is home: back
    assert ach.quest is None and ach.act in (7, 8, 9, 12, 13) and max(abs(ach.x - 139), abs(ach.y - 187)) < 40
    g.command("quest zeus 0 2")                                                            # slot 0: Theseus
    assert heroes.heroes.record(g, 5)["needed"]
    g.command("build heroes_hall 136 177 theseus")
    g.command("road 135 181 142 181")
    g.command("sendfor theseus")
    g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"] * 5)
    assert heroes.heroes.present(g, 5)
    g.command("dispatch theseus")
    g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"] * 4)
    from sim.systems import commemorative
    assert commemorative.state(g)["available"][22] == 1                                    # large Zeus statue
    assert [e for e in hev.records(g) if e["type"] == 4 and e["state"] == 10]
    # any hall (11-02): the war on Sparta above brings Sparta's invasion, whose timing and point follow ours' RNG
    # order; when it lands near Achilles' hall the invaders raze it (as the exe would)
    hall = next(b for b in g.buildings.values() if b.key == "heroes_hall")
    hall.coverage.update(drama=5, competition=5, athletics=5, philosophy=5)              # the hall takes coverage
    assert heroes.heroes.hall_culture(g, hall) >= 80                                     # 25 + 20 + 20 + 15
    from sim.model import Walker
    from sim.systems import walkers as W
    g.command("build horse_ranch 150 150")
    rb = next(b for b in g.buildings.values() if b.key == "horse_ranch")
    for i in range(3):                                                                   # Send For takes horses
        h = W.new_walker(g, role="horse", home=rb.id, x=rb.x, y=rb.y)
        W.add(g, h)
        rb.walkers.append(h.id)
    heroes.heroes.take_horses(g, 2)
    assert len([w for w in g.walkers.values() if w.role == "horse"]) == 1
    from sim.military import units                                                       # monster_hit_victim
    from sim.heroes import monsters as M
    med = M.spawn(g, 5, dict(id=-1, at=(150, 140)))
    v = units.spawn(g, "hoplite", 151, 140)
    units.kill(g, v, med)                                                                # petrified: a statue
    g.step(3)
    assert v.id not in g.walkers and [(s["x"], s["y"]) for s in M.statues(g)] == [(151, 140)]
    hyd = M.spawn(g, 0, dict(id=-1, at=(150, 130)))
    v = units.spawn(g, "hoplite", 151, 130)
    units.kill(g, v, hyd)
    assert v.tint == 0x7C00                                                              # devoured: drawn red
    g = Game("sandbox_open", 1)                                       # monument_piece_damage: a finished sanctuary's piece
    g.city.treasury = 100000
    g.command("build sanctuary_aphrodite 161 112")
    b = next(x for x in g.buildings.values() if x.key == "sanctuary_aphrodite")
    for p in b.misc["pieces"]:
        p["s"] = p["n"]
    g.step(51)
    (x, y), _ = M.pieces(g, b)[0]
    M.spawn(g, 11, dict(id=-1, at=(x - 2, y - 1)))
    g.step(51 * 10)
    dm = [p for p in b.misc["pieces"] if p.get("damaged")]
    assert dm and all(p["s"] == 0 for p in dm) and b.misc["built"] < 100 and b.misc["complete"]


def test_hero_bridge_no_teleport():
    """Bug 386: a hero walks to a monster across a bridge (road over water is route-grid road 0x04 in mask 0x11D,
    0x005876F0), one tile at a time; after the duel he walks to the nearest road within his distance to the hall
    (road_tile_near_building 0x004A39D0) and patrols. Before: the bridge was blocked, the lost route put him on the
    monster's tile at once, and after the kill he stood still. Since bug 392 the chase (action 10) is route mode 6
    (land and water), so he may wade the river instead of taking the bridge."""
    from sim.heroes import monsters as M, hero_ai
    from sim.heroes import heroes as H
    g = Game("sandbox_open", 1)
    w = g.world
    w.flags[145, :] |= 0x4                                   # a river from west to east
    w.road[145, 150] = True                                  # its only crossing
    g.command("heroes cheat")
    g.command("build heroes_hall 145 160 hercules")
    g.command("road 150 146 150 166")
    g.command("road 144 164 149 164")
    g.command("road 150 138 150 144")
    hyd = M.spawn(g, 0, dict(id=-1, at=(152, 124)))
    assert M.passable(g)[145 * 228 + 150] and not M.passable(g)[145 * 228 + 151]
    g.command("sendfor hercules")
    last, crossed, jumps = None, False, []
    for _ in range(51 * 16 * 8):
        g.step(1)
        h = H.figure(g, 1)
        if h is None or getattr(h, "hidden", False):
            last = None
            continue
        if last and max(abs(h.x - last[0]), abs(h.y - last[1])) > 1:
            jumps.append((g.tick, last, (h.x, h.y), h.act))
        crossed |= h.y == 145                               # the bridge, or wading (chasing: mode 6, bug 392)
        last = (h.x, h.y)
        if hyd.id not in g.walkers and h.act == 8:
            break
    assert not jumps, jumps
    assert crossed and hyd.id not in g.walkers
    assert h.act == 8                                        # on the road again, patrolling
    assert hero_ai.road_near(g, 152, 124, 40) == (150, 138)  # nearest non-bridge road, by radius


def test_hero_duel_either_side():
    """TODO 11-04 (user: Achilles fought the Maenad for minutes): hero vs his quarry is the fight engine's action 5
    whoever starts the contact (figure_fight_start 0x004D4BA0), with hero_duel_hit 0x004D5BC0 in place of figure_hit:
    no damage either way, the hero's +0x68 = 300 (figure_hero_update head with +0x82 a monster) counts down from his
    first fight tick and the monster falls at anim_t0 + 299. Ours before: only the hero's own arrival started the
    duel; a melee the monster began did damage both ways until she died. A monster not his quarry: a plain melee."""
    from sim.heroes import heroes as H, monsters as M
    from sim.military import units, contact
    from sim.systems import walkers as W
    for starter in ("monster", "hero", "none"):
        g = Game("sandbox_open", 1)
        g.command("heroes cheat")
        g.command("build heroes_hall 144 183 achilles")
        h = H.create(g, 0)
        old = (h.x, h.y)
        h.x, h.y = 150, 150
        contact.track(g, h, old)
        m = M.spawn(g, 11, dict(id=-1, at=(151, 150)))                  # a Maenad: his quarry
        h.act, h.target = 10, (0 if starter == "none" else m.id)
        if starter == "hero":                                          # his chase: adjacent -> FUN_004D5330
            g.step(1)
            assert h.anim == "fight" and h.mover and m.foe == h.id
            t0 = h.anim_t0                                              # his contact tick: +0x68 = 300 there
            while m.anim != "die" and g.tick < t0 + 400:
                g.step(1)
            assert g.tick == t0 + 299, g.tick - t0
        else:                                                           # the monster's contact in its own tick
            orig = M.act

            def once(g, w):
                if w is m and not h.anim:
                    units.start_fight(g, m, h)
                    return None
                return orig(g, w)
            M.act = once
            W.schedule(g, h, 10 ** 6)                                   # he does not act first
            try:
                W.schedule(g, m, 1)
                g.step(2)
            finally:
                M.act = orig
            assert h.anim == "fight" and m.mover
            t0 = h.anim_t0                                              # his slot is before hers: t0 = her tick
            while m.anim != "die" and g.tick < t0 + 400:
                g.step(1)
            assert g.tick == (t0 + 1 if starter == "none" else t0 + 299), (starter, g.tick - t0)  # no +0x82: 0
        assert getattr(m, "dmg", 0) == 0 and getattr(h, "dmg", 0) == 0, (starter, m.dmg, h.dmg)
        g.step(3)
        assert h.anim == "" and h.act in (8, 12, 13)
    g = Game("sandbox_open", 1)                                        # not his quarry: blows, no countdown
    g.command("heroes cheat")
    g.command("build heroes_hall 144 183 achilles")
    h = H.create(g, 0)
    old = (h.x, h.y)
    h.x, h.y = 150, 150
    contact.track(g, h, old)
    m = M.spawn(g, 3, dict(id=-1, at=(151, 150)))                       # a Cyclops
    h.act, h.target = 10, m.id
    g.step(1)
    units.start_fight(g, m, h)
    g.step(60)
    assert getattr(m, "dmg", 0) > 0 and h.duel_end is None


def test_hero_monster_message_sounds():
    """TODO 11-04 (user: no sound when the Maenads / Achilles arrived): hero_arrival_event_update 0x00481A80 plays
    FUN_005A0F70(hero): Audio/Voice/Walker/<name at 0x006469D8 + hero * 0x28> (data/heroes.json voice, built by
    tools/build_heroes.py); monster_event_update 0x00481430 the stinger FUN_005A1210(1/0) (S_mon1), a god-sent one the
    god's line first (FUN_005A1050(god, 4)); monster_slain_message 0x00481350 its texts (+6 / +7, type 0xE0) and
    FUN_005A1210(2) (S_mon2). Ours had the god's line only."""
    from sim.heroes import heroes as H, monsters as M
    from sim.military import units
    g = Game("sandbox_open", 1)
    g.command("monster maenads")
    meta = lambda: [getattr(m, "meta", {}) for _, m in g.city.messages]                    # noqa: E731
    assert meta()[0]["stinger"] == "mon1" and not meta()[0].get("voice")                    # not god-sent
    g.command("heroes cheat")
    g.command("build heroes_hall 144 183 achilles")
    g.command("road 143 187 150 187")
    g.command("sendfor achilles")
    n = len(g.city.messages)
    while H.figure(g, 0) is None and g.tick < 51 * 16 * 4:
        g.step(51)
    arr = [m for m in meta()[n:] if m.get("voice")]
    assert arr and arr[0]["voice"] == "Voice/Walker/ach_ev_1.mp3" and arr[0]["at"] == list(g.world.entry)
    assert [h["voice"] for h in H.data()["heroes"]] == ["ach_ev_1.mp3", "hec_ev_1.mp3", "jas_ev_1.mp3",
                                                        "ody_ev_1.mp3", "per_ev_1.mp3", "the_ev_1.mp3",
                                                        "ata_ev_1.mp3", "bel_ev_1.mp3"]
    for f in [h["voice"] for h in H.data()["heroes"]] + ["../../Music/S_mon1.mp3", "../../Music/S_mon2.mp3"]:
        assert os.path.isfile(os.path.join(ROOT, "zeus-original", "app", "Audio", "Voice", "Walker", f)), f
    m = M.spawn(g, 3, dict(id=-1, at=(150, 150)))                     # a Cyclops without an event: the generic slain
    n = len(g.city.messages)
    units.kill(g, m)
    g.step(200)
    sl = [x for x in meta()[n:] if x.get("stinger") == "mon2"]
    assert sl and sl[0]["title"] and sl[0]["kind"] == 0xE0
    from sim.systems import games                                    # the other FUN_005A1210 callers: games 7,
    n = len(g.city.messages)                                         # request 0x8D4 5, destroyed by a monster 4,
    games.begin(g, 1)                                                # disasters 3 / 6 (test_earthquake)
    assert meta()[n]["stinger"] == "games"


def test_monster_cache_not_saved():
    """Bug 386: the land grid cache (_monster_ok) came back with a loaded save and was reused (a bridge built since
    the cache was made stayed blocked); Game.load drops it."""
    import tempfile
    from sim.heroes import monsters as M
    g = Game("sandbox_open", 1)
    M.passable(g)
    with tempfile.TemporaryDirectory() as d:
        g.save(d + "/s.pkl")
        h = Game.load(d + "/s.pkl")
    assert not hasattr(h, "_monster_ok") and not hasattr(h, "_net_rank")


def test_monster_sounds():
    """Monster sounds the frames' looks cannot tell (sim walkers.sfx, heroes.js): the Kraken's "appear" at its spawn
    (monster_spawn_and_act 0x0052F726, slot 9); a bad monster blocked by a building plays atk1/atk2 every tick while
    it bashes (direction 11, 0x004C8C72): "bash" entries with an end tick."""
    import collections
    from sim.heroes import monsters
    g = Game("sandbox_open", 1)
    g.city.treasury = 10 ** 6
    g.sfx = []
    monsters.spawn(g, 1, None)
    assert [e[6] for e in g.sfx] == ["appear"] and g.sfx[0][4] == "monster"
    g.command("monster maenads")
    for dx in range(-4, 5):                      # benches around the lair (raw 122, 201): her rest routes bash them
        for dy in (-4, 4):
            for x, y in ((122 + dx, 201 + dy), (122 + dy, 201 + dx)):
                try:
                    g.command(f"build bench {x} {y}")
                except Exception:
                    pass
    g.sfx = []
    g.step(51 * 200)
    bash = [e for e in g.sfx if e[6] == "bash"]
    assert bash and all(e[7] > e[0] for e in bash), collections.Counter(e[6] for e in g.sfx)


def test_hercules_games():
    """Hercules' 'win a pan-Hellenic game' requirement (type 6) in the sandbox (his hall only with the cheat: he is not
    a hero of the sandbox's monster slots): FUN_00565E30 squares the year's chance x 0.16 while his hall stands, he is
    not sent for and the requirement is unmet; a won game (games conclude: 0x00FEB418) meets it, and the boost stops."""
    from sim.heroes import heroes as H
    from sim.systems import games
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    assert H.games_chance(g, 25) == 25                           # no hall
    g.command("heroes cheat")
    g.command("build heroes_hall 136 183 hercules")
    g.command("road 135 187 142 187")
    i = [q[0] for q in H.data()["heroes"][1]["requirements"]].index(6)
    assert not H.met(g, 1, i)
    assert (H.games_chance(g, 25), H.games_chance(g, 10), H.games_chance(g, 5), H.games_chance(g, 0)) == (100, 16, 4, 0)
    orig = games.chance
    games.chance = lambda g, t: 25                               # -> 100 with the hall: a sure win
    try:
        games.begin(g, 2)
    finally:
        games.chance = orig
    assert games.state(g)["result"] == 2 and games.state(g)["last"]["chance"] == 100
    games.conclude(g)
    assert games.state(g)["won_ever"] and H.met(g, 1, i) and H.games_chance(g, 25) == 25


def test_monster_missile():
    """Action 28 (monster_missile_attack 0x00530ED0): a ranged monster rampaging toward a building at Chebyshev 2..3
    shoots: a shot every 13 ticks, the missile (0x34 for a bad monster) at anim frame 0x006409F0[monster] (Maenads 7),
    the third landing destroys the building (wall_damage_add +2, past 4); the same as the exe's oracle run 1I-missile
    (tools/oracle_monster_missile.py). The missile's picture direction is FUN_0058D050 << 1 (defences.dir16)."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import oracle_monster_missile as om
    from sim.military import defences
    r = om.rel(*om.ours(200))
    assert r["shots"][:4] == [0, 13, 26, 39] and r["launches"][:4] == [7, 20, 33, 46] and r["destroyed"] == 44
    assert r["flights"][0][:8] == [(0, 0), (0, 0), (0, 0), (0, -1), (0, -1), (0, -1), (0, -1), (0, -2)]
    assert [defences.dir16(0, 0, dx, dy) for dx, dy in ((0, -5), (5, 0), (0, 5), (-5, 0), (5, -5), (-1, -3), (3, -1))] \
        == [0, 4, 8, 12, 2, 15, 3]                # (-1, -3): +0x11 = 30 in the oracle dump (tick 1694)
    from sim.heroes import monsters               # monster_has_ranged 0x0052FA00: all but monsters 5 and 16
    assert monsters.ranged(type("W", (), {"mid": 11})()) and not monsters.ranged(type("W", (), {"mid": 5})())


def test_rampage_figure_targets():
    """sim/heroes/rampage.py (monster_pick_targets 0x00531320, 0x005318B0): a rampaging monster also picks the nearest
    figure of its categories (nearest_figure_in_category 0x004AC020, data/heroes.json target_figures) when no building
    of the category is nearer-or-picked, walks to it in route mode 3 and fights it on contact; without a target it goes
    home (6) and rests (7). A building target is preferred; the monster smashes / bashes it."""
    from sim.systems import walkers
    from sim.heroes import monsters as M, rampage
    g = Game("sandbox", 1)
    g.command("monster maenads")
    m = next(w for w in g.walkers.values() if w.role == "monster")
    g.step(2)                                    # spawned in (6, 7): resting (its timer drawn) from its first act
    m.aggr, m.cats, m.timer = 1, (6, 6, 6), -1
    t = M.snap(g, m.x + 4, m.y)
    v = walkers.new_walker(g, role="immigrant", home=0, x=t[0], y=t[1])
    walkers.add(g, v, 10 ** 6)
    acts, fought = [], False
    for _ in range(200):
        g.step(1)
        if not acts or acts[-1] != m.act:
            acts.append(m.act)
        fought |= m.anim == "fight" and m.foe == v.id
    assert acts[:2] == [10, 11] and m.tf in (0, v.id) and fought, acts
    assert v.anim == "die" or v.id not in g.walkers
    assert 6 in acts and acts[-1] == 7, acts
    # categories: the nearest building and the nearest figure of each, the first category with either wins
    m2 = type("W", (), {})()
    m2.x, m2.y, m2.mid, m2.cats = m.x, m.y, 11, (6, 6, 6)
    assert rampage.nearest_figure(g, m2, 6) is None          # the immigrant is gone
    assert rampage.nearest_building(g, m2, 7) is None        # category 7: no figures, no beauty buildings here


def test_hero_hall_needs_allowed_flag():
    """hero_needed_message 0x004FA710 posts the hall message only with the episode's allowed flag 26 (0x00902D64):
    Zeus and Europa episode 1 has the Hydra but no heroes' halls (bugs.md 379)."""
    from sim import episode, heroes
    a = _campaign("zeus_and_europa")
    g = episode.new_city(a["source"] + "#0", _ep(a, 0), difficulty="Normal")
    assert g.allowed[26] == 0
    g.step(816 * 2)
    assert [w for w in g.walkers.values() if w.role == "monster"]                 # the Hydra came
    assert not heroes.heroes.record(g, 1)["needed"]                                # Hercules: no hall offered
    assert not [t for _, t in g.city.messages if "Hall" in str(t)], g.city.messages
    g.allowed[26] = 1
    heroes.heroes.needed(g, 1, 0)
    assert heroes.heroes.record(g, 1)["needed"]


def test_heroes_reset_at_continue_start():
    """episode_start_load 0x00420390 (continue): halls (0x7D) freed, hero records cleared (FUN_00511DE0: needed,
    text, sent, paid, announced), hero figures (0x45) removed; a monster on the map announces its hero again, so only
    that hero's hall is offered (bugs.md 397)."""
    from sim import heroes, episode
    g = Game("sandbox_open", 1)
    g.command("heroes cheat")
    g.command("quest zeus 0 2")                                                            # Theseus needed
    g.command("build heroes_hall 136 177 theseus")
    g.command("road 135 181 142 181")
    g.command("sendfor theseus")
    g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"] * 5)
    assert heroes.heroes.present(g, 5) and heroes.heroes.record(g, 5)["needed"]
    g.command("heroes cheat off")
    g.command("monster maenads")                                                           # Achilles needed
    for b in [b for b in g.buildings.values() if b.key == "heroes_hall"]:
        g.demolish(b.id, reason="episode")
    episode.heroes_reset(g)
    episode.monsters_announce(g)
    r = heroes.heroes.record(g, 5)
    assert (r["needed"], r["sent"], r["paid"], r["announced"], r["text"]) == (0, 0, 0, 0, -1)
    assert not [w for w in g.walkers.values() if w.role == "hero"]
    assert heroes.heroes.record(g, 0)["needed"]
    assert [h for h, _ in heroes.hall_menu(g)] == [0]


def test_hero_swims_when_chasing():
    """figure_hero_update 0x004C8F50: route mode 6 (0x0058B560: land and water) while chasing (action 10) or on water;
    on deep water outside a bridge he swims (bugs.md 392). sandbox_open: across the central lake."""
    from sim.heroes import hero_ai as A
    from sim.systems import walkers as W
    g = Game("sandbox_open", 1)
    h = W.new_walker(g, role="hero", home=0, x=70, y=114)
    h.act = 9                                                  # to the hall: mode 0, round the lake
    land = A._route(g, h, (125, 114))
    h.act = 10                                                 # chasing: mode 6, straight over the water
    wet = A._route(g, h, (125, 114))
    assert len(wet) < len(land) and not any(A.on_water(g, x, y) for x, y in land)
    assert sum(1 for x, y in wet if A.on_water(g, x, y)) > 20


def test_hall_menu():
    """Build menu 0x17 lists the halls of hero_hall_buildable 0x004FA620: a needed hero of the monster slots without a
    hall (bugs.md 383); the state carries them for play mode."""
    from sim import heroes, export
    g = Game("sandbox_open", 1)
    assert heroes.hall_menu(g) == []
    g.command("monster maenads")                           # Achilles needed
    assert heroes.hall_menu(g) == [[0, "Hero's Hall for Achilles"]]
    assert export.snapshot(g, False)["halls_available"] == [[0, "Hero's Hall for Achilles"]]


def test_hero_goods_requirement_units():
    """A hall's goods requirement (FUN_0040F810, hundredths: 3200 = 32 loads) against our stores, which already count
    hundredths: 31.68 loads of wine do not meet Hercules' 32; the status says 31 (bugs.md 385)."""
    from sim.heroes import heroes as hh
    g = Game("sandbox_open", 1)
    vals = {"wine": 3168}
    import sim.systems.economy as E
    real = E.city_stock
    E.city_stock = lambda g_, k: vals.get(k, 0)
    try:
        assert hh.stock(g, 21) == 3168
        assert not 3200 <= hh.stock(g, 21)
        vals["wine"] = 3200
        assert 3200 <= hh.stock(g, 21)
    finally:
        E.city_stock = real


def test_guardians():
    """sim/heroes/guardians.py (figure_monster_update 0x004C8760, heroes-monsters.md "Guardians"): Cerberus (Hades,
    set_action(0xE, 0xF)) patrols buildings' road access (14: 0x00532F10 / 0x00533070) and leaves when the next
    building search runs past buildings_last (flag 1 clear); with enemy soldiers on the map it chases the nearest
    (15: 0x00533220 / 0x00533340) and shoots from Chebyshev 2..3 (28, back to 15); the Kraken (Poseidon, 0x15 -> 14)
    sails to the sea exit and fights an enemy warship it targets (figure_tile_contact's ship rule) until it sinks;
    Ares' Dragon (0x12) follows his figure and vanishes with him; Talos (0x14: flag 1, 64 days); a killed guardian
    sets the sanctuary's flag for 192 days (+0xC8 = 0xC0, sanctuary_update)."""
    from sim import heroes, gods
    from sim.heroes import guardians
    from sim.gods import figures, sanct

    def city(seed=3):
        g = Game("sandbox_open", seed)
        g.city.treasury = 500000
        for c in ("road 86 33 115 33", "build sanctuary_hades 86 34"):
            g.command(c)
        for x in range(98, 116, 2):
            g.command(f"build house {x} 31")
        m = next(b for b in g.buildings.values() if b.key == "sanctuary_hades")
        for p in m.misc["pieces"]:
            p["s"] = p["n"]
        return g, m

    g, m = city()
    w = heroes.guardian(g, 11, m)
    assert w.mid == 2 and w.uclass == 7 and w.act == 0x0E and w.timer >= 1 and not w.gflag
    seen = []
    for _ in range(2000):
        g.step(1)
        if w.id not in g.walkers:
            break
        if not seen or seen[-1] != w.act:
            seen.append(w.act)
    assert w.id not in g.walkers and seen[:2] == [0x0E, 0x11] and seen[-1] == 0, seen
    assert heroes.guardian(g, 11, m) is not None            # gone (not killed): a new one may come
    g, m = city()
    w = heroes.guardian(g, 11, m)
    g.command("invade 110 50 8 0")                          # (at 100 45 the muster spot falls on the sanctuary,
    acts = set()                                            # which the invaders then hit: it falls, Cerberus leaves)
    for _ in range(1500):
        g.step(1)
        acts.add(w.act)
        if 28 in acts:
            break
    t = g.walkers.get(w.tf)
    assert {0x0F, 28} <= acts and t is not None and t.role.startswith("enemy_"), acts
    assert w.ret == 0x0F                                    # 28 goes back to 15 (+0x34)
    # killed: the flag, 192 days, then cleared by sanctuary_update
    from sim.military import units
    units.kill(g, w, t)
    assert m.misc["guardian_killed"] and m.misc["guardian_days"] == 0xC0
    assert heroes.guardian(g, 11, m) is None
    m.employees = 0
    for _ in range(0xC0):
        sanct.update(g)
    assert not m.misc.get("guardian_killed")
    # the Kraken against a sea invasion
    g, m = city()
    orig = guardians.sanctuary                              # Poseidon is not a sandbox god: his sanctuary = m
    guardians.sanctuary = lambda g_, w_: m
    try:
        k = heroes.guardian(g, 1, m)
        assert k.mid == 1 and tuple(k.spawn) == tuple(g.world.sea_entry) and k.act == 0x0E
        assert tuple(k.dest) == tuple(g.world.sea_exit) and k.tb == 1          # 0x00532EB0: the exit first
        g.command("invade sea")
        sunk = False
        for _ in range(600):
            g.step(1)
            ships = [o for o in g.walkers.values() if o.role in guardians.SHIPS]
            if any(o.anim == "die" for o in ships):
                sunk = True
                break
        assert sunk and k.act in (0x0F, 0x10, 28), k.act
    finally:
        guardians.sanctuary = orig
    # Ares' Dragon follows Ares (0x12) and vanishes with him
    g = Game("sandbox_open", 1)
    g.city.treasury = 500000
    st = gods.state(g)
    st["free"] = True
    st["rec"][5].update(unfriendly=0, listed=1)
    g.command("road 86 33 115 33")
    g.command("build sanctuary_ares 86 34")
    a5 = next(b for b in g.buildings.values() if b.key == "sanctuary_ares")
    for p in a5.misc["pieces"]:
        p["s"] = p["n"]
    g.step(51)
    ares = figures.visit_start(g, 5, a5)
    d = next(o for o in g.walkers.values() if o.role == "monster")
    assert d.mid == 7 and d.act == 0x12 and d.leader == ares.id and d.mflags & 0x80
    near = 0
    for _ in range(1500):
        g.step(1)
        if d.id not in g.walkers:
            break
        near = max(near, max(abs(d.x - ares.x), abs(d.y - ares.y)))
    assert d.id not in g.walkers and near <= 2 and ares.task == "leave", (near, ares.task)
    # Talos: 0x14 -> flag 1, 64 days, 14
    g, m = city()
    tl = guardians.spawn(g, 8, 9, m)
    assert tl.act == 0x0E and tl.gflag == 1 and tl.gdays == 64


def test_monster_rest_moves_as_exe():
    """TODO 11-02 items 2 and 4 (heroes-monsters.md "Monster actions as the exe"): every monster action runs each tick
    (figure_monster_update 0x004C8760) and moves by figure_move's sub-steps: tile progress 0..15, the tile change at 8;
    resting (7) a bad monster routes in mode 2 and, in front of a building, stands (direction 11) and adds wall damage
    only on ticks whose cycle_step & 3 == 0; 6 / 9 / 26 / 0x17 route in mode 3, roads first (guardians.route3)."""
    from sim.heroes import monsters as M
    from sim.heroes.guardians import route3
    from sim.military import state as mstate
    g = Game("sandbox", 1)
    g.command("monster maenads")
    m = next(w for w in g.walkers.values() if w.role == "monster")
    g.command("build house 121 197")
    progs, bash = set(), []
    for _ in range(60):
        before = sum(mstate(g).get("wall_damage", {}).values())
        g.step(1)
        progs.add(getattr(m, "prog", 15))
        if m.act == 7 and getattr(m, "mdir", None) == 11:
            bash.append((g.tick % 51 & 3, sum(mstate(g).get("wall_damage", {}).values()) - before))   # the pass ran at g.tick
    assert progs - {15} and max(progs) <= 15 and bash
    assert all((d == 1) == (c == 0) for c, d in bash), bash       # one hit on each cycle_step & 3 == 0 tick
    m.mflags &= ~0x100
    M.set_action(g, m, 6, 7)
    M.fmove(g, m)
    assert M.route_mode(m) == 3 and m.route is not None
    assert [m.heading] + list(m.route) == route3(g, (m.x, m.y), tuple(m.spawn)) or (m.x, m.y) == tuple(m.spawn)


def test_monster_shoots_out_of_contact():
    """TODO 11-02 item 3: a tile contact on the walk starts a melee (action 5) and the handler goes on (0x00531050, as
    15 0x00533340 and 11 0x005318B0): a ranged monster with its target at Chebyshev 2..3 goes to 28 with +0x34 = 5,
    its opponent lets go; after the shot one tick in 5, figure_fight_end puts back 28 (no sound, no missile) and at
    its last frame +0x34 = 0: (6, 7)."""
    from sim.systems import walkers
    from sim.heroes import monsters as M
    from sim.military import units
    g = Game("sandbox", 1)
    g.command("monster maenads")
    m = next(w for w in g.walkers.values() if w.role == "monster")
    g.step(2)
    t = walkers.new_walker(g, role="immigrant", home=0, x=122, y=205)
    walkers.add(g, t, 10 ** 6)
    x = units.spawn(g, "hoplite", 122, 202, delay=10 ** 6)
    m.tf = t.id
    M.enter(g, m, 9)
    seen = []
    for _ in range(40):
        g.step(1)
        seen.append((m.act, getattr(m, "ret", None), m.anim, x.anim))
    i = seen.index((28, 5, "", ""))
    n = M.frames(m.mid, 3)
    assert seen[i - 1][0] == 9 and all(s[:2] == (28, 5) for s in seen[i:i + n - 1])
    assert all(s[:2] == (28, 0) for s in seen[i + n - 1:i + 2 * n])
    assert seen[i + 2 * n][:2] == (6, 7)
    assert sum(1 for w in g.walkers.values() if w.role == "enemy_arrow") <= 1


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])
