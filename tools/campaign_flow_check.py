"""The campaign module's flow and goal judging (sim/campaign, track 1L-3) against oracle runs of the original game.

    python3 tools/campaign_flow_check.py goal-met   re/oracle/runs/1L3-goal-met
    python3 tools/campaign_flow_check.py time-limit re/oracle/runs/1L3-time-limit
    python3 tools/campaign_flow_check.py debt       re/oracle/runs/1L3-debt
    python3 tools/campaign_flow_check.py return     re/oracle/runs/1L3-europa-return

The runs (re/oracle/scenarios/1L3-*.txt + .poke, run as docs/re/oracle.md "Run" with ZEUS_POKE) play Zeus and Europa
at Mortal (= our Easy). Ours plays the same through sim/campaign/flow.py and is compared:
  goal-met    goal 1 poked to Treasury 5001 (not met at the first month change) then 5000 (met at the second, by the
              exe's own check): 0x00FEB168 (victory shown) and 0x00FEB160 (loss phrase) after each month change
  time-limit  goal 1 poked to Time limit 0 years: lost at the month change, 0x00FEB160 = 0xB95
  debt        treasury -100 and 35 months in debt: lost at the month change, months 36, 0x00FEB160 = 0xB91
  return      forced wins (0x00F2A6DB) through slots 0, 1, 2, the colony Cydonia (slot 10) and back to the parent
              (slot 3): the state after each start (dumps 310, 620, 920+): date, treasury, scenario_start_year,
              the start kind, the allowed table, every in-use world city's kind / relationship / active / tribute
              mode, the events' type / month / flags (rebased by the month; years are rolled at the start)
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from oracle import Dump  # noqa: E402

KINDS = {0: "player", 1: "colony", 2: "foreign", 3: "parent", 4: "distant", 5: "enchanted", 6: "destroyed"}
RELATIONS = {0: "ally", 1: "rival", 2: "vassal", 3: "colony"}
bad = []


def eq(name, ours, exe):
    ok = ours == exe
    print(f"{'ok ' if ok else 'BAD'} {name}: ours {ours} exe {exe}")
    if not ok:
        bad.append(name)


def dump(run, tick):
    for t in range(tick, tick + 40):
        p = os.path.join(run, "dump", f"tick_{t:06d}.bin")
        if os.path.exists(p) or os.path.exists(p + ".zst"):
            return Dump(p), t
    raise SystemExit(f"no dump at or after tick {tick} in {run}")


def result(d):
    return dict(won=d.at(0x00FEB168, "<i"), lost=d.at(0x00FEB160, "<i"), debt=d.at(0x00FEB27C, "<i"),
                date=(d.at(0x0091EC04, "<i"), d.at(0x0091EC08, "<i")))


def new_game():
    from sim.campaign import flow
    return flow.start("zeus_and_europa", difficulty="Easy")


def month(g):
    return g.rules["ticks_per_day"] * g.rules["days_per_month"]


def ours_state(g):
    st = g.campaign
    return dict(won=1 if st["result"] == 1 else 0, lost=st["lost"] if st["lost"] is not None else -1,
                debt=g.city.months_in_debt, date=(g.year, g.month))


def paused_at(run):
    """The tick every later shot shows (run.log 'shot PATH ticks K'): the game stopped there (a modal screen)."""
    ticks = [int(l.split()[-1]) for l in open(os.path.join(run, "run.log")) if l.startswith("shot ")]
    return ticks[-1] if ticks else None


def check_goal_met(run):
    g = new_game()
    g.campaign["goals"][0].update(type=1, v=[5001, 0, 0, 0, 0, 0])
    g.step(month(g))
    a = ours_state(g)
    g.campaign["goals"][0]["v"][0] = 5000
    g.step(month(g))
    b = ours_state(g)
    d1, t1 = dump(run, 51)
    r1 = result(d1)
    print(f"exe dump {t1}")
    eq("first month change (5001 > treasury 5000): won, lost", (a["won"], a["lost"]), (r1["won"], r1["lost"]))
    # the victory screen stops the clock at the second month change: no dump after it; the shots after tick 102
    # show the Victory screen with "Treasury of 5000" ticked (m104.bmp, by eye)
    eq("second month change (5000): ours won / the exe stopped at the month change (tick 102)",
       (b["won"], b["lost"], b["date"]), (1, -1, (-1150, 2)) if paused_at(run) == 102 else ("exe ran on", paused_at(run)))


def check_loss(run, setup, phrase):
    g = new_game()
    setup(g)
    g.step(month(g))
    a = ours_state(g)
    d, t = dump(run, 51)
    r = result(d)
    print(f"exe dump {t}")
    eq("after the month change: won, lost phrase, months in debt", (a["won"], a["lost"], a["debt"]),
       (r["won"], r["lost"], r["debt"]))
    eq("the phrase", a["lost"], phrase)


def moved(g):
    """The goods a price event (type 15 / 16) has changed in this game or one it came from: ours' scenario log, and
    every good whose price is off the catalogue's (a colony starts with a new log and the carried prices)."""
    import re
    log = getattr(getattr(g, "scenario", None), "log", None) or []
    out = {m.group(1) for x in log for m in [re.search(r"price of (\w+)", str(x))] if m}
    cat = g.cat.trade["prices"]
    return out | {k for k, v in (g.__dict__.get("prices") or {}).items() if v != cat.get(k, 0)}


def compare_start(g, d, label):
    from sim import scenario
    sc = d.block(9)
    i16 = lambda b, o: struct.unpack_from("<h", b, o)[0]   # noqa: E731
    i32 = lambda b, o: struct.unpack_from("<i", b, o)[0]   # noqa: E731
    print(f"--- {label}: slot {g.campaign['slot']} ({g.episode['start']})")
    eq("date (year, month)", (g.year, g.month), (d.at(0x0091EC04, "<i"), d.at(0x0091EC08, "<i")))
    eq("treasury", g.city.treasury, d.at(0x00FE6A64, "<i"))
    eq("scenario_start_year", g.scenario_year, i16(sc, 0))
    eq("start kind (record +0x58)", ["new_city", "colony", "continue"].index(g.episode["start"]), i32(sc, 0x644 + 0x58))
    eq("allowed table", g.allowed, list(struct.unpack_from("<100h", sc, 0x408)))
    # episode-transition.md: what the map brings and what flows through parent.dat
    eq("world map picture (0x0090311C)", g.empire.picture, d.at(0x0090311C, "<i"))
    eq("months count (0x00903114)", g.empire.months, d.at(0x00903114, "<i"))
    eq("treasury at the year's start (0x00FE971C)", g.year_treasury, d.at(0x00FE971C, "<i"))
    from sim.systems import trade
    from build_empire import GOODS
    skip = ("horses", "chariot", "oranges", "black_marble", "orichalc")      # not traded in a Zeus game
    ex = {GOODS[i]: d.at(0x0065B9B0 + 4 * i, "<i") for i in range(1, 23) if i in GOODS and GOODS[i] not in skip}
    base = (g.empire and __import__("sim.empire.scenario", fromlist=["x"]).map_data(g.map_name).get("prices")) or {}
    base = {k: base.get(k, g.cat.trade["prices"].get(k, 0)) for k in ex} if g.episode["start"] == "new_city" else None
    ours = {k: trade.price(g, k) for k in ex}
    both = [k for k in ex if ours[k] != ex[k] and base is None and k in moved(g)]
    if both:      # a price event of an earlier episode with a random amount: drawn by ours' own RNG (events.md)
        print(f"    prices moved by an event in both, amounts drawn by different RNGs: "
              + ", ".join(f"{k} ours {ours[k]} exe {ex[k]}" for k in both))
    eq("goods prices (goods_price 0x0065B9B0, traded goods)", {k: v for k, v in ours.items() if k not in both},
       {k: v for k, v in ex.items() if k not in both})
    cb = d.block(7)
    exe, ours = {}, {}
    for i in range(22):
        c = cb[0x23C * i:0x23C * (i + 1)]
        if not c[0]:
            continue
        exe[i] = (KINDS.get(c[2]), RELATIONS.get(i32(c, 0xD4)), bool(i32(c, 0x170)), i32(c, 0xE0))
    for i, c in g.empire.cities.items():
        ours[i] = (c.kind, c.relation, bool(c.active), c.tribute["mode"])
    for i in sorted(set(exe) | set(ours)):
        if ours.get(i) != exe.get(i):
            eq(f"city {i} (kind, relationship, active, tribute mode)", ours.get(i), exe.get(i))
    print(f"    {len(exe)} in-use cities compared")
    n = d.at(0x009173F0, "<i")
    eb = d.block(13)
    evs = scenario.events(g)
    eq("event count", len(evs), n)
    diff = years = 0
    for i, ev in enumerate(evs[:n]):
        x = eb[124 * i:124 * (i + 1)]
        o, e = (ev["type"], ev["month"], ev["flags"]), (x[2], x[3], struct.unpack_from("<I", x, 0x28)[0])
        if o != e:
            diff += 1
            eq(f"event {i} (type, month, flags)", o, e)
        if ev["year"] != i16(x, 0x14):
            years += 1
    print(f"    events: {n} compared, {diff} differ in type/month/flags; {years} years differ (rolled at the start)")


def check_return(run, before=os.path.join(ROOT, "re", "oracle", "runs", "1L-europa-colony")):
    """Slots 1, 2 and the colony from 1L-europa-colony's dumps (the same script and pokes up to there; 1L-1), the
    return to the parent from 1L3-europa-return's (dumped from tick 600 on)."""
    from sim.campaign import flow
    import tempfile
    save = os.path.join(tempfile.mkdtemp(), "eu.pkl")
    g = new_game()

    def win(g):
        g.campaign["forced"] = True
        g.step(month(g))
        return g
    g = flow.proceed(win(g), save)                       # slot 1 (continue), exe dump 60
    compare_start(g, dump(before, 60)[0], "slot 1 (exe dump 60)")
    g = flow.proceed(win(g), save)                       # slot 2, exe dump 310
    compare_start(g, dump(before, 310)[0], "slot 2 (exe dump 310)")
    g = flow.proceed(win(g), save, colony="Cydonia")     # colony slot 10, exe dump 620
    compare_start(g, dump(run, 620)[0], "colony Cydonia (exe dump 620)")
    g = flow.proceed(win(g), save)                       # back to the parent, slot 3, exe dump 920+
    d, t = dump(run, 920)
    compare_start(g, d, f"parent after the colony, slot 3 (exe dump {t})")
    from sim.systems import commemorative
    eq("colony monument granted (commemorative kind 3)", commemorative.state(g)["available"][3] > 0, True)


def main(mode, run):
    if mode == "goal-met":
        check_goal_met(run)
    elif mode == "time-limit":
        check_loss(run, lambda g: g.campaign["goals"][0].update(type=12, v=[0, 0, 0, 0, 0, 0]), 0xB95)
    elif mode == "debt":
        def setup(g):
            g.city.treasury, g.city.months_in_debt = -100, 35
        check_loss(run, setup, 0xB91)
    elif mode == "return":
        check_return(run)
    else:
        print(__doc__)
        return 2
    print(f"{len(bad)} differences" + (f": {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:]))
