"""Production, storage and distribution, agoras, trade.
Run: python3 tests/test_sim.py economy (or a test by name: python3 tests/test_sim.py test_NAME)."""
import os

from helpers import ROOT, Game, ti_first, _campaign, _ep, _raises


def test_quarry_depth():
    """map-terrain.md 5b: a cut block deepens the marble tile 255 -> 100 -> 0 (0 only once all 8 neighbours
    are pits); the search prefers untouched interior tiles; play mode draws shallow / deep pit images."""
    import numpy as np
    from sim.systems import walkers, economy
    from sim.terrain_view import TerrainView
    g = Game("sandbox_open", 1)
    fl = g.world.flags
    N = fl.shape[0]
    hits = np.flatnonzero((fl & np.uint32(0x120000)).ravel() == 0x20000).tolist()
    inner = next(economy.marble_targets(g, hits, 0x20000, set()))
    x, y = next((i % N, i // N) for i in inner if all(j in inner for j in (i - N - 1, i - N, i - N + 1, i - 1,
                                                                          i + 1, i + N - 1, i + N, i + N + 1)))
    walkers.quarry_dig(g, x, y)
    assert g.quarry[(x, y)] == 100
    walkers.quarry_dig(g, x, y)
    assert g.quarry[(x, y)] == 100                  # neighbours untouched: stays shallow
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                walkers.quarry_dig(g, x + dx, y + dy)
    walkers.quarry_dig(g, x, y)
    assert g.quarry[(x, y)] == 0
    passes = list(economy.marble_targets(g, hits, 0x20000, set()))
    assert all(y * N + x not in p for p in passes)  # deep pit ringed by shallow ones: not a target
    assert y * N + x - 1 in passes[3] and y * N + x - 1 not in passes[1]   # shallow: only the loose pass
    ids = TerrainView(g).ids
    deep, shallow = ti_first(203), ti_first(204)
    assert deep <= (int(ids[y, x]) & 0x3fff) < deep + 60
    assert shallow <= (int(ids[y, x - 1]) & 0x3fff) < shallow + 60


def test_horse_ranch_corral():
    """3x3 ranch house + 4x4 corral at the orientation offset (0x00637E60); horses stay in it (0x004D0140); an old
    save's ranch gets a corral when there is room (bugs.md 134)."""
    from sim.model import Building
    from sim.systems import ranch, economy, walkers
    g = Game("sandbox_open", 1)
    out = g.command("build horse_ranch 140 104 n")
    b = next(x for x in g.buildings.values() if x.key == "horse_ranch")
    assert b.misc["corral"] == [139, 100] and b.misc["orient"] == 1 and g.world.occ[100, 139] == b.id, out
    for i in range(3):
        h = walkers.spawn_animal(g, "horse", *ranch.spawn_tile(g, b, i))
        h.home = b.id
        b.walkers.append(h.id)
    assert ranch.spawn_tile(g, b, 1) == (141, 100)
    for _ in range(40):
        g.command("days 1")
        assert all(ranch.in_corral(b, h.x, h.y) for h in ranch.horses(g, b))
    old = Building(id=g.next_bid, key="horse_ranch", x=150, y=104, size=3, kind="ranch")    # before 10-28: no corral
    g.next_bid += 1
    g.buildings[old.id] = old
    g.world.occ[104:107, 150:153] = old.id
    economy.ranch_month(g, old, g.cat.spec("horse_ranch"))
    assert old.misc["corral"] == [153, 103] and g.world.occ[103, 153] == old.id


def test_herd_stock_cap():
    """herd_send_herders 0x004F77A0 sends shearers while the farm's stock (b+0x3C) < 500, loads on the way not
    counted; building_stock_add 0x004F8050 clamps each arriving load at 500 (the rest is lost). Ours counted the
    loads on the way and never clamped: a farm could hold 600 (playtest haiku-3 triage)."""
    from sim.systems import walkers, economy
    g = Game("sandbox_open", 1)
    g.command("road 140 110 140 116")
    g.command("build sheep_farm 141 112")
    b = next(x for x in g.buildings.values() if x.key == "sheep_farm")
    b.employees = 8
    spec = g.cat.spec("sheep_farm")
    sheep = []
    for x, y in ((136, 112), (136, 113)):
        a = walkers.spawn_animal(g, "sheep", x, y)
        a.ready = 100
        sheep.append(a)
    b.goods["fleece"] = 400
    economy.send_herders(g, b, spec, 1, 2)                 # one slot: one shearer
    first = [w for w in g.walkers.values() if w.role == "shepherd"]
    assert len(first) == 1 and first[0].task != "tend"
    first[0].amount = 100                                   # carrying its load home: stock is still 400 < 500
    economy.send_herders(g, b, spec, 1, 2)
    sh = [w for w in g.walkers.values() if w.role == "shepherd" and w.task != "tend"]
    assert len(sh) == 2 and {w.target for w in sh} == {a.id for a in sheep}
    for w in sh:
        w.amount = 100
        walkers.deliver_gathered(g, w, b)
    assert b.goods["fleece"] == 500                         # 400 + 100 + 100, clamped
    b.goods["fleece"] = 500
    sheep[0].ready = 100
    economy.send_herders(g, b, spec, 2, 2)                  # full: no shearer
    assert not [w for w in g.walkers.values() if w.role == "shepherd" and w.task != "tend"]


def test_no_horses_or_chariots_in_storage():
    """Storehouses and posts never take horses or chariots (storage_goods_list 0x005B12C0; no cart carries them;
    posts can't import them); a chariot workshop keeps its chariots up to 400 (0x0048CFB0 case 0xD4); old saves
    hand stored chariots back to the nearest workshop and drop the rest (bugs.md: invisible chariots)."""
    import tempfile
    from sim.systems import trade, economy, labor, risk
    g = Game("sandbox_open", 1)
    g.command("gods off")                         # no jealous god destroying the storehouse in 200 days
    g.command("empire off")                       # data/trade.json: Ecbatana sells chariots, Susa buys them
    g.command("poseidon on")
    g.city.treasury = 10 ** 6
    g.command("road 60 71 80 71")
    g.command("build storehouse 61 68")
    g.command("build trading_post 70 67 Ecbatana")
    g.command("build chariot_workshop 75 67")
    s = next(b for b in g.buildings.values() if b.key == "storehouse")
    post = next(b for b in g.buildings.values() if b.kind == "trade")
    ws = next(b for b in g.buildings.values() if b.key == "chariot_workshop")
    for k in ("chariot", "horses"):
        try:
            trade.set_order(g, post, k, "import")
            raise AssertionError(f"{k} import order accepted")
        except ValueError:
            pass
        assert economy.storage_room(g, s, k) == 0 and economy.goods_add(g, k, 400) == 0
    s.goods["wood"], ws.goods["wood"] = 400, 400
    orig = labor.allocate

    def staffed(g):                               # no population in this test
        orig(g)
        for b in (s, ws):
            b.employees = g.cat.spec(b.key)["employees"]
    labor.allocate, upd = staffed, risk.update
    risk.update = lambda g: None                  # no fire/collapse in this test
    try:
        for _ in range(200):
            g.step(51)
            assert not any(w.good == "chariot" for w in g.walkers.values())
    finally:
        labor.allocate, risk.update = orig, upd
    assert ws.goods.get("chariot") == 400 and "chariot" not in s.goods, (ws.goods, s.goods)
    # an old save with chariots/horses in storage and an import order for them
    ws.goods["chariot"] = 300
    s.goods.update(chariot=3200, horses=200)
    post.misc["orders"]["chariot"] = "import"
    g.store_v = 0
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        path = f.name
    try:
        g.save(path)
        g2 = Game.load(path)
    finally:
        os.unlink(path)
    s2, post2, ws2 = g2.buildings[s.id], g2.buildings[post.id], g2.buildings[ws.id]
    assert "chariot" not in s2.goods and "horses" not in s2.goods and "chariot" not in post2.misc["orders"]
    assert ws2.goods["chariot"] == 400 and ws2.goods["horses"] == 200, ws2.goods
    assert "3100 chariot" in g2.city.messages[-1][1], g2.city.messages[-1]


def test_trade_limit_per_visit():
    """The post's per-good number caps what ONE trader brings or takes per visit (trade_ledger_full 0x005B8E00,
    ledger zeroed per trader by 0x005B9DF0), not the city total; the partner's yearly quota caps the total
    (city_sells/city_buys). Confirmed by the user's play of the original (docs/logic/trade.md)."""
    from sim.systems import trade, walkers
    g = Game("sandbox_open", 1)
    g.command("empire off")
    g.city.treasury = 10 ** 6
    g.command("road 60 71 80 71")
    g.command("build trading_post 70 67 Sardis")     # sells bronze, buys wine (12 loads a year each)
    post = next(b for b in g.buildings.values() if b.kind == "trade")
    c = post.misc["partner"]
    trade.set_order(g, post, "bronze", "import", 200)
    trade.set_order(g, post, "wine", "export", 100)

    def visit():
        w = walkers.new_walker(g, role="merchant", home=post.id, x=post.x, y=post.y, good=str(c))
        got = []
        while True:
            post.goods["wine"] = 1000                 # plenty to sell
            k = trade.import_one(g, w, post, c) if trade.can_import(g, w, post, c) else None
            post.goods.pop("bronze", None)            # pushed out to storage at once
            e = trade.export_one(g, w, post, c) if trade.can_export(g, w, post, c) else None
            if k is None and e is None:
                return got
            got += [x for x in (k, e) if x]
    assert sorted(visit()) == ["bronze", "bronze", "wine"]          # 200 in, 100 out per visit
    assert sorted(visit()) == ["bronze", "bronze", "wine"]          # the next trader again
    n = sum(len(visit()) for _ in range(10))
    used = trade.state(g)["used"][c]
    assert used["bronze"] == 12 and used["wine"] == 12, used       # yearly quota is the only total cap
    assert visit() == []


def test_trade_staffed_dock_inverted():
    """staffed (0x005B9610 / 0x005B9990 / 0x005B8F90): >= 50 % for a post; for a dock the exe computes
    need * 100 / workers, so any staff up to twice the need passes (bugs.md 342)."""
    from sim.systems import trade
    g = Game("sandbox_open", 1)
    need = g.cat.spec("dock")["employees"]

    class B:
        key = "dock"
    b = B()
    for n, ok in ((0, False), (1, True), (need // 3, True), (need, True)):
        b.employees = n
        assert trade.staffed(g, b) is ok, (n, ok)


def test_workshop_fills_to_its_cap():
    """A sculpture studio needs 400 bronze in stock to work and holds at most 400 (stock_cap 0x0048A880):
    deliveries go on while stock + incoming < cap, with no extra margin, or it stalls at 300 (bugs.md 168)."""
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("road 60 71 80 71")
    g.command("build storehouse 61 68")
    g.command("build sculpture_studio 66 69")
    s = next(b for b in g.buildings.values() if b.key == "storehouse")
    st = next(b for b in g.buildings.values() if b.key == "sculpture_studio")
    s.goods["bronze"] = 1200
    st.goods["bronze"] = 300
    from sim.systems import labor
    orig = labor.allocate

    def staffed(g):                              # no population in this test
        orig(g)
        for b in (s, st):
            b.employees = g.cat.spec(b.key)["employees"]
    labor.allocate = staffed
    try:
        for _ in range(40):
            g.step(51)
            if st.goods.get("bronze", 0) >= 400 or st.progress:
                break
    finally:
        labor.allocate = orig
    assert st.goods.get("bronze", 0) >= 400 or st.progress, (st.goods, st.progress)


def test_storehouse_one_deliveryman():
    """storage-distribution.md §7 (user 11-03, bugs.md 452): a storehouse has ONE deliveryman (slot +0xB6,
    storage_spawn_walkers 0x005B4B40); with the slot empty it picks the first workshop in building order that accepts a
    stored input (0x0048AAC0) and sends min(stock, 400) at once; the man unloads up to the workshop's cap, carries the
    rest on (find_workshop_for_input) or home. Three wineries, one storehouse with 2000 grapes: never two men out."""
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("road 60 71 90 71")
    g.command("build storehouse 61 68")
    for x in (66, 70, 74):
        g.command(f"build winery {x} 69")
    s = next(b for b in g.buildings.values() if b.key == "storehouse")
    ws = [b for b in g.buildings.values() if b.key == "winery"]
    s.goods["grapes"] = 2000
    from sim.systems import labor, storemen
    orig = labor.allocate

    def staffed(g):                              # no population in this test
        orig(g)
        for b in [s] + ws:
            b.employees = g.cat.spec(b.key)["employees"]
    labor.allocate = staffed
    trips, most = set(), 0
    try:
        for _ in range(51 * 40):
            g.step(1)
            out = [w for w in g.walkers.values() if w.role == "cart" and w.home == s.id and w.task == "deliver"]
            most = max(most, len(out))
            for w in out:
                if w.id not in trips:
                    trips.add(w.id)
                    assert w.amount == 400 and w.good == "grapes" and s.misc["dman"] == w.id
    finally:
        labor.allocate = orig
    assert most == 1 and len(trips) >= 2
    assert all(b.goods.get("grapes", 0) > 0 for b in ws)
    assert not any(w.role == "cart" and w.home == s.id and w.task == "" for w in g.walkers.values())   # no old pull


def test_storehouse_get_storehousemen():
    """storage_get_targets 0x00489E60 / storage_get_worker_plan 0x0048CA00: one Get good under 50 % of its limit ->
    two storehousemen (slots +0x2A, +0xB8), each walking out empty, taking up to 400 at the nearest source
    (storage_find_source 0x0048A140), bringing it home; never a third. Empty: one man, only without a Get target."""
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("road 60 71 100 71")
    g.command("build storehouse 61 68")
    g.command("build storehouse 90 68")
    a, b = sorted((x for x in g.buildings.values() if x.key == "storehouse"), key=lambda x: x.x)
    from sim.systems import labor, storemen
    assert storemen.worker_plan(10, 100, 1) == (1, 1, 2) and storemen.worker_plan(70, 100, 1) == (0, 1, 1)
    assert storemen.worker_plan(70, 80, 2) == (1, 0, 2)
    b.goods["wood"] = 2000
    a.misc.setdefault("orders", {})["wood"] = "get"
    orig = labor.allocate

    def staffed(g):
        orig(g)
        for x in (a, b):
            x.employees = g.cat.spec(x.key)["employees"]
    labor.allocate = staffed
    most, loads = 0, set()
    try:
        for _ in range(51 * 30):                # 29 tiles each way at 15 ticks a tile
            g.step(1)
            out = [w for w in g.walkers.values() if w.home == a.id and w.task == "get"]
            most = max(most, len(out))
            loads |= {w.amount for w in out}
    finally:
        labor.allocate = orig
    assert most == 2 and loads <= {0, 400} and a.goods.get("wood", 0) >= 800, (most, loads, a.goods)
    assert storemen.empty_target(g, a, "wood") == 0          # Get first: no Empty man while a Get target exists


def test_monument_cart_source_as_exe():
    """monument_dispatch_cart 0x00543DE0: the source is storage_find_source(monument, good, 0, need_min 1,
    min(amount, 400)): a storehouse holding less than the load is no source, staff is not tested, a storehouse on Get
    is one; no storage walker slot (the exe's sanctuary-build run: two marble carts from storehouse 60 at once)."""
    from sim.model import Building
    from sim.systems import storemen
    g = Game("sandbox_open", 1)
    g.city.treasury = 100000
    g.command("road 60 71 100 71")
    g.command("build storehouse 61 68")
    s = next(b for b in g.buildings.values() if b.key == "storehouse")
    m = Building(id=10 ** 6, key="sanctuary_zeus", x=95, y=60, size=1, kind="monument", access=(95, 71))
    m.network = s.network
    s.goods["marble"] = 300
    s.employees = 0
    assert storemen.find_source(g, m, "marble", need_min=True, minimum=400, start=(95, 71)) is None
    assert storemen.find_source(g, m, "marble", need_min=True, minimum=100, start=(95, 71)) is s
    s.misc["orders"] = {"marble": "get"}
    assert storemen.find_source(g, m, "marble", need_min=True, minimum=100, start=(95, 71)) is s
    assert storemen.find_source(g, m, "marble", need_min=False, minimum=100, start=(95, 71)) is None


def test_city_food_list_sticky():
    """Bug 297 (storage-distribution.md "Stall buyer"): the city food list (g_city_food_list, rebuild_goods_lists
    0x005BAAF0) is in goods order and sticky (0x00FEB0D2[res]): a food that ran out keeps its place, so the agora
    buyers' first 5 stay urchin .. carrots once all 8 were held, and wheat is never bought."""
    from sim.model import Building
    from sim.systems import agora
    g = Game("sandbox_open", 1)
    g.command("empire off")
    gr = Building(id=99999, key="granary", x=0, y=0, size=4, kind="storage")
    g.buildings[gr.id] = gr
    gr.goods = {"wheat": 400, "fish": 100}
    assert agora.city_foods(g) == ["fish", "wheat"]
    gr.goods = {f: 100 for f in g.cat.foods}
    assert agora.city_foods(g)[:5] == ["urchin", "fish", "meat", "cheese", "carrots"]
    gr.goods = {"wheat": 400}
    assert agora.city_foods(g) == [f for f in g.cat.foods if f != "oranges"]     # ours: oranges off (Poseidon off)
    g.command("poseidon on")
    gr.goods = {"oranges": 100}
    assert agora.city_foods(g) == list(g.cat.foods)


def test_agora_food_fix():
    """Bug 297, ours: exe bug fixed (data/fixes.json agora_all_foods, default fixed). Exe rule: the food buyer takes
    only the first 5 foods of the city's list and goes to the nearest storage holding any food; fixed: it takes
    every listed food and goes to the nearest storage holding a food it takes."""
    from sim.model import Building
    from sim.systems import agora
    g = Game("sandbox_open", 1)
    g.command("empire off")
    assert g.cat.fixed("agora_all_foods") and g.cat.fixes["agora_all_foods"]["fixed"] is True
    near = Building(id=99998, key="granary", x=10, y=10, size=4, kind="storage", access=(9, 9), employees=1)
    far = Building(id=99999, key="granary", x=20, y=10, size=4, kind="storage", access=(19, 9), employees=1)
    for b in (near, far):
        g.buildings[b.id] = b
    near.goods = {f: 100 for f in g.cat.foods}
    agora.city_foods(g)                           # all 7 foods (no oranges: Poseidon off) listed, sticky
    near.goods, far.goods = {"wheat": 400, "oranges": 300}, {"oranges": 300}
    a = type("A", (), {})()
    a.goods = {}
    stall = type("S", (), dict(x=12, y=12))()

    def buyer():
        w = type("W", (), {})()
        w.good, w.amount, w.load = "food", 0, {}
        return w
    for fixed in (True, False):
        g.cat.fixes["agora_all_foods"]["fixed"] = fixed
        foods = agora.food_list(g)
        assert foods == (["urchin", "fish", "meat", "cheese", "carrots", "onions", "wheat"] if fixed
                         else ["urchin", "fish", "meat", "cheese", "carrots"]), foods
        w = buyer()
        near.goods["wheat"] = 400
        agora.buy_at(g, a, w, near)
        assert w.load == ({"wheat": 400} if fixed else {}) and w.amount == (400 if fixed else 0), (fixed, w.load)
        # a storage holding only food the buyer won't take (oranges, off): the exe still picks it, ours not
        near.goods["wheat"] = 0
        src = {b.id for b in agora.sources(g, stall, "food")}
        assert src == (set() if fixed else {near.id, far.id}), (fixed, src)
    g.cat.fixes["agora_all_foods"]["fixed"] = True


def test_agora_food_storehouse_only_imported():
    """Bug 460 (exe vendor_find_source 0x0040EAD0 kind 0, buyer_research_sources 0x0040E2A0): a food buyer
    takes a storehouse or post as its source only for a food the city imports (trade status 0x01607EC4 == 5,
    trade.city_status), a post also not exporting it; a granary for any food. No staff test, stock > 0."""
    from sim.model import Building
    from sim.systems import agora, trade
    g = Game("sandbox_open", 1)
    g.command("empire off")
    sh = Building(id=99997, key="storehouse", x=10, y=10, size=3, kind="storage", access=(9, 9), employees=0)
    gr = Building(id=99998, key="granary", x=20, y=10, size=4, kind="storage", access=(19, 9), employees=0)
    post = Building(id=99999, key="trading_post", x=30, y=10, size=4, kind="trade", access=(29, 9),
                    misc=dict(partner=0, orders={}, limits={}))
    for b in (sh, gr, post):
        g.buildings[b.id] = b
    sh.goods, gr.goods, post.goods = {"wheat": 2400}, {"fish": 50}, {}
    agora.city_foods(g)
    stall = type("S", (), dict(x=12, y=12))()
    src = lambda: {b.id for b in agora.sources(g, stall, "food")}
    assert trade.city_status(g, "wheat") is None
    assert src() == {gr.id}, src()                            # wheat not imported: the storehouse is no source
    p = trade.partners(g)[0]
    p["sells"]["wheat"] = 12
    post.misc["orders"]["wheat"] = "import"
    assert trade.city_status(g, "wheat") == "import"
    assert src() == {sh.id, gr.id}, src()
    post.goods = {"wheat": 100}
    assert src() == {sh.id, gr.id, post.id}, src()
    post.misc["orders"]["wheat"] = "export"                   # the last post's state wins: exporting
    assert trade.city_status(g, "wheat") == "export" and src() == {gr.id}, src()


def test_oranges_off_without_poseidon():
    """Ours (user 10-30): oranges, a Poseidon good, are off while Poseidon is off: no partner of data/trade.json or
    the partners/wartest worlds trades them, posts refuse orders for them and never trade them; `poseidon on` allows
    them again. Old saves lose them once on load (Game.load goods_v, economy.purge_goods), with a message."""
    import json
    import tempfile
    from sim.model import Building
    from sim.systems import trade, walkers
    g = Game("sandbox_open", 1)
    g.command("empire off")
    assert g.cat.poseidon_goods == {"oranges"}
    assert not any("oranges" in p["buys"] or "oranges" in p["sells"] for p in g.cat.trade["partners"])
    for name in ("partners", "wartest"):
        cities = json.load(open(os.path.join(ROOT, "data", "world", name + ".json")))["cities"]
        assert not any("oranges" in c.get(k, {}) for c in cities for k in ("buys", "sells")), name
    p0 = g.cat.trade["partners"][0]
    p0["sells"]["oranges"], p0["buys"]["oranges"] = 12, 12          # a partner listing them (a Poseidon world)
    assert not trade.city_sells(g, 0, "oranges") and not trade.city_buys(g, 0, "oranges")
    post = Building(id=99990, key="trading_post", x=0, y=0, size=0, kind="trade", misc=dict(partner=0, orders={}, limits={}))
    assert "Poseidon" in str(_raises(lambda: trade.set_order(g, post, "oranges", "import")))
    g.command("poseidon on")
    assert trade.city_sells(g, 0, "oranges")
    assert trade.set_order(g, post, "oranges", "import")
    del p0["sells"]["oranges"], p0["buys"]["oranges"]
    g.command("poseidon off")
    # an old save holding oranges everywhere
    st = Building(id=99991, key="granary", x=4, y=4, size=4, kind="storage")
    house = Building(id=99992, key="house", x=8, y=8, size=1, kind="house", goods={"oranges": 90, "wheat": 10})
    ag = Building(id=99993, key="agora", x=12, y=12, size=0, kind="agora", goods={"oranges": 300})
    for b in (st, house, ag, post):
        g.buildings[b.id] = b
    st.goods["oranges"] = 700
    st.misc.setdefault("orders", {})["oranges"] = "get"
    cart = walkers.new_walker(g, role="cart", home=post.id, x=1, y=1, good="oranges", amount=200)
    g.walkers[cart.id] = cart
    g.city.foods_listed.update({"oranges", "wheat"})
    g.goods_v = 0
    with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
        path = f.name
    try:
        g.save(path)
        g2 = Game.load(path)
        g.poseidon = True
        g.save(path)
        g3 = Game.load(path)
    finally:
        os.unlink(path)
    assert all("oranges" not in b.goods for b in g2.buildings.values())
    assert "oranges" not in g2.buildings[st.id].misc["orders"] and "oranges" not in g2.buildings[post.id].misc["orders"]
    assert cart.id not in g2.walkers and g2.city.foods_listed == {"wheat"} and g2.goods_v == 1
    assert g2.buildings[house.id].goods == {"wheat": 10}
    msg = g2.city.messages[-1][1]
    assert msg.startswith("Oranges removed") and "90 from houses" in msg and "200 from carts" in msg, msg
    assert g3.buildings[house.id].goods["oranges"] == 90 and cart.id in g3.walkers      # Poseidon on: kept


def test_goods_list_sandbox():
    """1L goods lists (rebuild_goods_lists 0x005BAAF0, storage_goods_list 0x005B12C0): Open Play Sandbox's city as the
    oracle shows it (re/oracle/scenarios/1L-storage-lists.txt): the Distribution page's goods (no horses / chariots),
    the granary's foods (fish meat cheese wheat); no carrots, onions, urchins. A gift event choosing black marble
    lists it (FUN_005BA980), and it stays once marked (0x00FE93EC). With grapes and olives neither in the city's
    resources nor sold: the growers' lodge halts (0x004873F0) until a finished Athena sanctuary provides olives
    (god_resource_available 0x005BA890)."""
    from sim.game import Game
    from sim import allowed, export, scenario, gods
    from sim.systems import labor
    g = Game("sandbox", seed=1)
    gl = export.goods_list(g)
    assert [k for k in gl if k not in ("horses", "chariot")] == [
        "fish", "meat", "cheese", "wheat", "wood", "bronze", "marble", "grapes", "olives", "fleece", "armor",
        "sculpture", "olive_oil", "wine"], gl
    assert [k for k in gl if k in g.cat.foods] == ["fish", "meat", "cheese", "wheat"]
    ev = scenario.blank(0)
    ev.update(type=23, flags=0)
    ev["groups"]["item"] = [0, 16, -1, -1]
    g.scenario.events.append(ev)
    assert "black_marble" in export.goods_list(g)
    allowed.mark(g)
    g.scenario.events.remove(ev)
    assert "black_marble" in export.goods_list(g)
    g.empire.player().resources = [k for k in g.empire.player().resources if k not in ("grapes", "olives")]
    for c in g.empire.cities.values():
        for k in ("grapes", "olives", "wine", "olive_oil"):
            c.sells.pop(k, None)
    b = type("B", (), dict(key="growers_lodge"))()
    assert labor.halted(g, b)
    gods.built = lambda g_, i, _f=gods.built: i == gods.god_id("athena") or _f(g_, i)
    try:
        assert allowed.god_provides(g, "olives") and not labor.halted(g, b)
    finally:
        gods.built = gods.built.__defaults__[0]


def test_trading_post_partner_with_space():
    """build trading_post X Y NAME takes the whole name: Zeus and Europa's Mt. Pelion (bugs.md 382)."""
    from sim import episode
    a = _campaign("zeus_and_europa")
    g = episode.new_city(a["source"] + "#0", _ep(a, 0), difficulty="Normal")
    seen = []
    g.build = lambda key, x, y, extra=None: seen.append(extra) or ""
    g.command("build trading_post 1 1 Mt. Pelion")
    assert seen == ["Mt. Pelion"], seen


def test_stonecutter_route_mode_b():
    """Route mode 0xB (figure_find_route case 11): roads first (0x0058A6C0) traced 4-way, else the 0x19C search traced
    8-way. Oracle schools-A (the working city): stonecutter 1951 from its quarry's road access (88, 59) to the marble
    (95, 70) passes (88, 61) .. (88, 68), (89, 69), (91, 69) .. (94, 69); 1894 from (86, 56): (87, 56), (88, 57)."""
    from sim import savimport
    from sim.systems import walkers
    g = savimport.load(os.path.join(ROOT, "zeus-original/app/Adventures/tutorial15.sav"))
    ox, oy = g.world.origin
    lg = lambda p: [(x - ox, y - oy) for x, y in p]     # noqa: E731
    p = lg(walkers.route11(g, (88 + ox, 59 + oy), (95 + ox, 70 + oy)))
    assert p == [(88, y) for y in range(60, 69)] + [(x, 69) for x in range(89, 95)] + [(95, 70)], p
    p = lg(walkers.route11(g, (86 + ox, 56 + oy), (95 + ox, 70 + oy)))
    assert p[:2] == [(87, 56), (88, 57)] and p[-2:] == [(94, 69), (95, 70)]
    b = next(b for b in g.buildings.values() if b.key == "marble_quarry")
    home = walkers.route11(g, (95 + ox, 70 + oy), tuple(b.access))
    assert home[-1] == tuple(b.access)


def test_resource_search_port():
    """resource_tile_search 0x004A86E0 (economy.resource_search): woodcutters take grown trees only (regrowth 0xFF),
    the building's check counts stumps (0); an ore rock lists its free neighbours N, NE, E ... with the rock, the
    flood's first pop wins; a list ending exactly at a 3999-entry flush finds nothing (exe bug kept); bugs.md 420."""
    import numpy as np
    from sim.systems import economy, walkers
    g = Game("sandbox_open", 1)
    w = g.world
    x0, y0 = 150, 150
    w.flags[y0 - 6:y0 + 7, x0 - 6:x0 + 7] = 0
    w.flags[w.flags & 0x1 != 0] &= np.uint32(0xFFFFFFFE)            # no other tree on the map
    g.map_version = getattr(g, "map_version", 0) + 1
    w.flags[y0, x0 + 3] |= np.uint32(0x1)
    spec = g.cat.spec("timber_mill")
    g.regrow = [(10 ** 9, x0 + 3, y0)]                                # a stump
    assert economy.resource_search(g, spec, (x0, y0), 0xFF) is None and g.trees_exist is False
    assert economy.resource_search(g, spec, (x0, y0), 0) == ((x0 + 3, y0), None)
    g.regrow = []
    assert economy.resource_search(g, spec, (x0, y0), 0xFF) == ((x0 + 3, y0), None)
    spec = g.cat.spec("foundry")
    w.flags[y0 + 3, x0] = np.uint32(0x100002)
    g.map_version += 1
    dest, rock = economy.resource_search(g, spec, (x0, y0), 0)
    assert rock == (x0, y0 + 3) and dest == (x0, y0 + 2), (dest, rock)    # N of the rock: popped first
    ent = [(i, None) for i in range(economy.LIST_CHUNK)]
    assert economy._listed_pick(g, (x0, y0), ent) is None


def test_miner_pause_look():
    """figure_miner 0x004C1310 action 0xD (the ore miner's 25-tick pause after work): SprMain group 44 (copper) / 77
    (silver) + timer / 2, no direction; play mode's "work" look "pause" from the tick the pause began (the sim's
    25-tick wait) and the data block (tools/play_miner_pause.py)."""
    import json
    from sim import export
    from sim.systems import walkers
    g = Game("sandbox_open", 1)
    w = walkers.new_walker(g, role="miner", home=0, x=150, y=150)
    w.state = "pause"
    walkers.add(g, w, 1)
    t0 = walkers.now(g)
    walkers.schedule(g, w, 25)                    # finish_work: the pause's 25 ticks from the tick it begins
    assert export.gatherer_look(g, w) == ["work", t0, t0 + 25, 0, 0, 0, 0, 0, "pause", False]
    blk = json.load(open(os.path.join(ROOT, "data", "play", "walkers.json")))["roles"]["miner"]["work"]
    assert (blk["pause"]["start"], blk["pause_silver"]["start"]) == (2699, 3845)
    assert blk["pause"]["dirs"] == 1 and blk["pause"]["ticks_per_frame"] == 2 and blk["pause"]["clamp"] == 12


def test_quarry_yard_figure():
    """city_draw case 0x31 / 0xD5 -> FUN_0045C170 (bugs.md 454): a staffed, unburnt marble quarry / black marble shop
    draws a stonecutter chiselling its block, by stock n = s // 100 - 1 at the table's (dx, dy, dir), group 0x2043
    (SprAmbient 2017; 0x2042 = 1937 for n 7), or the idle figure (dir 3, (0x3B, 0x1B)) with stock 0; the black
    marble shop's stock pictures (building_extra_draw 0xD5: 701 + 7 - n, the quarry's offsets). Oracle
    overlays-check/quarry r1..r6 (stock 400 / 300): 0 px. Play side: tools/quarry_yard_check.mjs."""
    import json
    B = json.load(open(os.path.join(ROOT, "data", "play", "buildings.json")))
    want = [(0x3B, 0x29, 7, 2017), (0x3F, 0x32, 0, 2017), (0x37, 0x2D, 6, 2017), (0x3B, 0x33, 7, 2017),
            (0x3B, 0x25, 7, 2017), (0x3E, 0x29, 0, 2017), (0x3D, 0x25, 6, 2017), (0x3F, 0x33, 7, 1937)]
    for k, good in (("marble_quarry", "marble"), ("black_marble_shop", "black_marble")):
        Y = B[k]["yard"]
        assert Y["good"] == good
        assert [(c["dx"], c["dy"], c["dir"], c["first"]) for c in Y["cutters"]] == want
        assert all(c["frames"] == 10 and c["dirs"] == 8 for c in Y["cutters"])
        assert (Y["idle"]["dx"], Y["idle"]["dy"], Y["idle"]["dir"]) == (0x3B, 0x1B, 3)
        assert [f["first"] for f in Y["idle"]["figures"]] == [2437, 2277]
    sp = B["black_marble_shop"]["stock_pics"][0]
    assert (sp["good"], sp["file"], sp["first"], sp["max"], sp["reverse"]) == ("black_marble", "Poseidon_Loaded", 701, 7, True)
    js = open(os.path.join(ROOT, "viewer", "play", "scene.js")).read()
    assert "function drawYard(" in js and "if (m.yard) drawYard(" in js


if __name__ == "__main__":
    import test_sim
    test_sim.main([__file__])


def test_grazer_stays_on_lone_meadow():
    """animal_pick_dest 0x004F83E0 (oracle re/oracle/runs/sheep-isolated, bugs.md 486): a sheep on a lone meadow
    tile never leaves it, and one whose tile is not meadow never moves (the exe refuses off meadow at once)."""
    from sim.systems import walkers
    g = Game("sandbox_open", 1)
    fl = g.world.flags
    x, y = 136, 112
    assert fl[y, x] & 0x800
    for yy in range(y - 6, y + 7):
        for xx in range(x - 6, x + 7):
            if (xx, yy) != (x, y):
                fl[yy, xx] &= ~(0x800 | 0x10000) & 0xFFFFFFFF
    g.__dict__.pop("_flagl", None)
    lone = walkers.spawn_animal(g, "sheep", x, y)
    off = walkers.spawn_animal(g, "sheep", x + 1, y)    # beside the meadow tile, not on it
    for _ in range(40):
        assert walkers._hop(g, lone, x, y, -4, 4, True) is None
        assert walkers._hop(g, off, x + 1, y, -4, 4, True) is None
