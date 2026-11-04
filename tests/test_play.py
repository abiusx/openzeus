"""Play mode's server side: comms deltas, alerts, info / walker windows, the stall watcher.
Run: python3 tests/test_sim.py play (or a test by name: python3 tests/test_sim.py test_NAME)."""

from helpers import Game, play, _comms_apply, _raises


def test_walker_window_gone_figure():
    """TODO 11-04 (user: Demeter's window drew only its list box; bugs.md 457): the tab draws behind the sim, so a god
    it shows can be gone on the server when its window asks; the exe's window reads the figure slot, whose data
    stays. sim/live keeps the walkers removed in the last GONE_KEEP ticks (Runner.gone_walkers) for walker_info."""
    from sim import live
    from sim.systems import walkers
    g = Game("sandbox_open", 1)
    g.command("godattack zeus")
    z = next(w for w in g.walkers.values() if w.role == "god")
    r = live.Runner(g, speed=30)
    walkers.remove(g, z)
    assert live.walker_info(g, [z.id]) == []
    r.record_frame()
    d = live.walker_info(g, [z.id], r.gone_walkers)
    assert len(d) == 1 and d[0]["type"] == 67 and d[0]["res"] == 0 and d[0]["gone"]
    g.step(live.GONE_KEEP + 1)
    r.record_frame()
    assert live.walker_info(g, [z.id], r.gone_walkers) == []


def test_trireme_wharf_window():
    """The wharf's info window (FUN_00583C60, export info.wharf) and its button (0x00572490 = `staff X Y on|off`,
    only without a trireme); no trireme is launched without a palace (buildings_spawn_walkers case 0x88)."""
    from sim.military import navy
    from sim.systems import labor
    from sim import export
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("road 50 81 50 83")
    g.command("build trireme_wharf 50 84")
    b = next(x for x in g.buildings.values() if x.key == "trireme_wharf")
    b.goods.update(wood=200, armor=200)
    orig = labor.allocate

    def staffed(g):
        orig(g)
        if not b.misc.get("off"):
            b.employees = g.cat.spec(b.key)["employees"]
    labor.allocate = staffed
    try:
        w = export.info_extra(g, b)["wharf"]
        assert w == dict(palace=False, trireme=False, at_wharf=False, status="", progress=0, crew_all=False)
        g.step(51 * 40)
        assert not navy.triremes(g) and b.progress == 0           # no palace: nothing is built
        g.command("staff 50 84 off")                              # the button: "Send Wharf workers home"
        assert b.misc.get("off") and export.info_extra(g, b).get("off")
        g.step(51)
        assert b.employees == 0
        g.command("staff 50 84 on")                               # "Staff this Trireme Wharf"
        assert not b.misc.get("off")
        g.command("road 86 33 115 33")
        g.command("build palace 92 24")
        g.step(51 * 3)
        w = export.info_extra(g, b)["wharf"]
        assert w["palace"] and w["status"] == "build" and 0 < w["progress"] < 100, w
        for _ in range(60):
            g.step(51)
            if navy.triremes(g) and getattr(navy.triremes(g)[0], "act", None) == 0x14:
                break
        t = navy.triremes(g)[0]
        w = export.info_extra(g, b)["wharf"]
        assert w["trireme"] and w["at_wharf"] and w["status"] == "" and b.goods.get("wood", 0) == 0
        assert "trireme" in str(_raises(lambda: g.command("staff 50 84 off"))) and not b.misc.get("off")
        assert navy.wharf_trireme(g, b) is t
        # the Military page's "crew all" / "stand down" (wm_sub_40A380, label FUN_0051AE00; bugs.md 329)
        assert navy.crew_all_label(g) == 5                         # 'crew all'
        g.command("navy crew")
        assert navy.crew_all_label(g) == 4 and export.info_extra(g, b)["wharf"]["crew_all"]   # 'all crewed'
        g.command("navy crew")                                    # stand down: back to the wharf, crew home
        assert t.act == 0x17 and navy.crew_all_label(g) == 5, hex(t.act)
        for _ in range(30):
            g.step(51)
            if b.misc.get("off"):
                break
        assert b.misc.get("off"), (hex(t.act), b.misc)
        g.command("navy crew")                                    # crew all: the wharf takes workers again
        assert not b.misc.get("off")
    finally:
        labor.allocate = orig


def test_walker_window_figures():
    """Walker window records of gods, monsters, heroes (sim/live walker_info; 0x005740A0 cases 0x43..0x45, bugs.md
    325): figure type, id, thought group by id (FUN_004E3750) and phrase (FUN_005A9C20)."""
    from sim import live, gods
    g = Game("sandbox_open", 1)
    g.command("monster maenads")
    m = next(w for w in g.walkers.values() if w.role == "monster")
    d = live.walker_info(g, [m.id])[0]
    assert (d["type"], d["res"], d["thought"]) == (68, 11, [326, 0])            # 190:11 Maenad, 326:0
    g.command("godattack zeus")
    z = next(w for w in g.walkers.values() if w.role == "god")
    d = live.walker_info(g, [z.id])[0]
    assert (d["type"], d["res"], d["unfriendly"]) == (67, 0, 0)
    assert d["thought"] is None                       # jealous (0x57): no phrase for Zeus
    z.task = "visit"
    assert live.walker_info(g, [z.id])[0]["thought"] == [300, 0]                # visit / bless: phrase 0
    gods.rec(g, 0)["unfriendly"] = 1
    z.task = "attack"
    assert live.walker_info(g, [z.id])[0]["thought"] == [300, 2]                # Zeus hostile: 2
    from sim.systems import walkers
    h = walkers.new_walker(g, role="peddler", home=0, x=z.x + 2, y=z.y)
    assert live._danger(g, h, False) == 0            # an unfriendly god within 5: danger (FUN_005A97A0)
    gods.rec(g, 0)["unfriendly"] = 0
    h.x, h.y = m.x + 3, m.y
    assert live._danger(g, h, True) == 0             # a bad monster (class 8): soldiers fear it too
    p = walkers.new_walker(g, role="priest", home=0, x=20, y=20)    # priest 0x41: to a sheep 1 + 1, a goat home 2 + 1
    s = walkers.new_walker(g, role="sheep", home=0, x=22, y=20)
    g.walkers[p.id], g.walkers[s.id] = p, s
    p.state, p.target = "animal", s.id
    assert live.walker_info(g, [p.id])[0]["thought"] == [237, 2]
    p.state, p.good = "altar", "goat"
    assert live.walker_info(g, [p.id])[0]["thought"] == [237, 3]


def test_comms_deltas():
    """Protocol 2 (docs/play/comms.md): frames, snapshots and terrain rebuilt from the deltas equal the full ones."""
    import json as _json
    from sim import comms, live
    g = play(1)                                                  # smoke.txt: a small city with walkers
    g.live_rate = None
    r = live.Runner(g, speed=30)
    for _ in range(4):
        r.advance(g.tick + 40)
        r.record_state()
        r.commands(["tax 10" if g.tick % 2 else "tax 8"])      # re-recorded frame / snapshot at the same tick
    full = _json.loads(r.frames_range(0, g.tick))
    dl = _json.loads(r.frames_range(0, g.tick, v2=True))
    assert len(full) == len(dl) > 100
    prev = None
    for f, d in zip(full, dl):
        if "_b" in d:
            assert prev["fs"] == d["_b"]
            d = _comms_apply(prev, d, comms.FRAME_KEYED)
        assert d == f and _json.dumps(d, sort_keys=True) == _json.dumps(f, sort_keys=True)
        prev = d
    assert sum("_b" in d for d in dl) > len(dl) - 10
    first = r.states[0]
    s0 = _json.loads(r.state_lite(first[0]))
    chain = _json.loads(r.state_lite(g.tick, v2=True, base=s0["seq"]))
    s = s0
    for d in chain["deltas"]:
        s = _comms_apply(s, d, comms.STATE_KEYED)
    assert _json.dumps(s, sort_keys=True) == _json.dumps(_json.loads(r.state_lite(g.tick)), sort_keys=True)
    a = {"n": 3, "ids": [1, 2, 3], "x": {"a": 1}}
    b = {"n": 3, "ids": [1, 5, 3], "y": True}
    ea, eb = comms.encode(a, grids=("ids",)), comms.encode(b, grids=("ids",))
    assert comms.join(ea) == comms.dumps(a) and comms.join(eb) == comms.dumps(b)
    d = _json.loads(comms.delta(ea, eb, 7))
    assert d["ix"] == {"ids": [1, 5]} and _comms_apply(a, d, {}) == b


def test_alerts():
    """sim/alerts.py (docs/play/alerts.md): the panel's 4 alert slots: slot by type range, replace, 8-day age (the
    exe's date: g.day, or g.day - 1 in run_day's month-end block, oracle 1B-inv-land / 1I-hero / 1H-god), the hover
    hold, go through the tiles, plague's extra tiles, the 20-tile quirk, reset on load, the frame export."""
    from sim import alerts
    g = Game("sandbox_open", 1)
    tpd = g.rules["ticks_per_day"]
    assert alerts.export(g) == [0, 0, 0, 0]
    assert g.command("alert raise 9 120 130").endswith(": slot 2: invasion")      # a test command (sim/testcmds.py)
    alerts.raise_alert(g, alerts.MONSTER, (100, 100))                 # same range: replaces
    assert alerts.export(g)[2][0] == 10 and alerts.export(g)[2][2] == [[100, 100]]
    g.step(8 * tpd)
    assert alerts.export(g)[2]                                          # 8 days old: still there
    g.step(tpd)
    assert alerts.export(g)[2] == 0                                     # 9: gone
    alerts.raise_alert(g, alerts.GOD, (100, 100))
    g.command("alert hover 3")
    g.step(12 * tpd)
    assert alerts.export(g)[3]                                          # hovered: kept
    g.command("alert hover -1")
    g.step(tpd)
    assert alerts.export(g)[3] == 0
    alerts.raise_alert(g, alerts.PLAGUE, (110, 120))
    alerts.add(g, alerts.PLAGUE, (111, 121))
    assert g.command("alert go 1") == "go to (110,120)" and alerts.export(g)[1][1] == 1
    assert g.command("alert go 1") == "go to (111,121)" and alerts.export(g)[1] == 0      # all visited: cleared
    alerts.raise_alert(g, alerts.PLAGUE, (110, 120))
    for _ in range(25):
        alerts.add(g, alerts.PLAGUE, (111, 121))
    assert len(alerts.export(g)[1][2]) == 20
    assert g.command("alert go 1") == "nothing to go to" and alerts.export(g)[1] == 0     # count 20: as none (sic)
    with alerts.dated(g, g.day - 1):                                    # run_day's month-end block
        alerts.raise_alert(g, alerts.HERO, (100, 100))
    assert alerts.state(g)["slots"][3]["day"] == g.day - 1
    g2 = Game("sandbox_open", 1)                                             # oracle 1B-inv-land: raised at 815, gone at 1224
    g2.step(16 * tpd - 1)
    from sim.military import invaders
    invaders.invade(g2, dict(id=4, amount=50, city=3, landing=0, ships=0), point=invaders.pick_point(g2, 1), army=0,
                    strength=50, target_class=0)
    assert alerts.export(g2)[2][0] == alerts.INVASION
    g2.step(1224 - g2.tick - 1)
    assert alerts.export(g2)[2]
    g2.step(1)
    assert alerts.export(g2)[2] == 0
    g3 = Game("sandbox_open", 1)                                             # oracle 1H-god: the jealous god at day 5, gone at 714
    g3.command("jealous 1")
    g3.step(256)
    assert alerts.export(g3)[3][0] == alerts.GOD and alerts.state(g3)["slots"][3]["day"] == 5
    alerts.reset(g3)                                                    # the live server's loads (FUN_0040FFD0)
    assert alerts.export(g3) == [0, 0, 0, 0]


def test_live_stall_watcher():
    """The server's stall watcher (user 11-03, after bugs.md 442): a lock hold over STALL_MS is logged with where it
    was taken; short holds are not."""
    import time
    from sim import live
    from sim.game import Game
    r = live.Runner(Game("sandbox_open"), speed=30)
    with r.lock:
        pass
    assert not r.stalls
    with r.lock:
        time.sleep(live.STALL_MS / 1000 + 0.03)
    assert len(r.stalls) == 1 and r.stalls[0]["kind"] == "lock" and r.stalls[0]["where"].startswith("test_live_stall_watcher:")


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])
