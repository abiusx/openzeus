"""Every parent episode of an adventure: the exe started through its menus and pushed episode by episode with forced
wins, against ours started the same way (track 1L-5; docs/campaign-format.md "Adventure x episode").

    python3 tools/campaign_chain.py scenario ID     # write re/oracle/scenarios/1L5-chain-ID.txt + .poke
    python3 tools/campaign_chain.py run ID          # the oracle run (docs/re/oracle.md "Run") -> re/oracle/runs/1L5-chain-ID
    python3 tools/campaign_chain.py check ID        # ours vs the exe at each parent slot's start
    python3 tools/campaign_chain.py ours ID         # ours only: every episode started (colonies too), a year each

The exe chain: the family menu's Adventures (590,260) or Custom Adventures (590,288, sandbox2-food), the list row (y = 162 + 16 i, oracle 1L-europa1 s32), Begin
Adventure (315,442), To the city
(656,491); then per episode a forced win (0x00F2A6DB = 1, day 0x0091EC0C = 15),
Proceed (296,555), To the city; the forced win poked every 10 ticks and day 15 every 30 (each episode is won at its
first month change; ours steps to the exe's month at each start, then wins); at a colony choice the colony (order(): the first not founded, its flag at the
world object - (110, 43)) and the confirm button (777,380). (Poking the live record's next 0x00902FC0 does not skip
the choice: Proceed reads the adventure's record.) Ours plays the same order. Difficulty: Mortal = our Easy.
Compared at each slot's first dump (0x00F2A7B0 changed): tools/campaign_flow_check.py compare_start (date,
treasury, scenario start year, start kind, allowed table, every in-use city's kind / relationship / active / tribute
mode, the events' type / month / flags), and the data file against the dump (tools/campaign_oracle_check.py).
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
SC = os.path.join(ROOT, "re/oracle/scenarios")
RUNS = os.path.join(ROOT, "re/oracle/runs")
LIST = ["zeus_and_europa", "perseus_and_medusa", "athens_through_the_ages", "the_voyages_of_jason", "hercules_labors",
        "the_peloponnesian_war", "the_trojan_war", "open_play_economic", "open_play_military", "open_play_sandbox"]
CUSTOM = ["open_play_economic_2", "open_play_military_2", "open_play_sandbox_2", "the_odyssey"]   # Custom Adventures
MENU = "5:key 27; 12:click 220,101; 17:char 78; 20:click 556,320"


def adventure(aid):
    return json.load(open(os.path.join(ROOT, "data", "campaign", f"{aid}.json")))


def order(a):
    """The episodes in play order: [(slot, colony name or None)]: parent slots by their next (record +0x54); after a
    parent whose next is the colony choice, the first colony (n order) not founded yet that has a map (ours and the
    exe's chain pick the same), then the parent slot after it."""
    eps = {e["slot"]: e for e in a["episodes"]}
    cols = [c for c in sorted(a["colonies"], key=lambda c: c["n"]) if c.get("map") is not None]
    out, slot = [], 0
    while slot in eps:
        out.append((slot, None))
        nxt = eps[slot]["next"]
        if nxt == "end":
            break
        if nxt == "colony" and cols:
            c = cols.pop(0)
            out.append((c["slot"], c["name"]))
        slot += 1
    return out


def colony_xy(a, name):
    """The colony's flag on the colony choice screen (0x34): its world object at (x - 110, y - 43) (oracle shots:
    Zeus and Europa's Cydonia 297,541; Perseus' Calydon and Miletos)."""
    from sim.empire import scenario as S
    d = S.map_data(a["source"] + "#0")
    m = next(c["map"] for c in d["cities"] if c["name"] == name)
    return m["x"] - 110, m["y"] - 43


def script(aid):
    a = adventure(aid)
    i, by = (LIST.index(aid), 260) if aid in LIST else (CUSTOM.index(aid), 288)    # Adventures / Custom Adventures
    eps = order(a)
    t = [MENU, f"26:move 590,{by}", f"26.5:click 590,{by}", f"30:move 120,{162 + 16 * i}", f"30.5:click 120,{162 + 16 * i}",
         "32:shot DIR/l32.bmp", "33:move 315,442",
         "33.5:click 315,442", "40:shot DIR/b40.bmp", "75:move 656,491", "75.5:click 656,491", "79:rclick 300,300"]
    pokes = []
    b = 82
    for tick in range(20, 400 * len(eps), 10):    # every episode is won at its first month change
        pokes.append(f"{tick} 0x00F2A6DB 1 1")
        if tick % 30 == 20:
            pokes.append(f"{tick} 0x0091EC0C 4 15")
    for k in range(len(eps) - 1):
        t += [f"{b - 1}:shot DIR/v{k}.bmp", f"{b}:move 296,555", f"{b + 0.5}:click 296,555"]
        col = eps[k + 1][1]
        if col:                                   # the colony choice: the colony, then the confirm button
            x, y = colony_xy(a, col)
            t += [f"{b + 6}:shot DIR/c{k}.bmp", f"{b + 8}:move {x},{y}", f"{b + 8.5}:click {x},{y}",
                  f"{b + 12}:move 777,380", f"{b + 12.5}:click 777,380"]
            b += 14
        t += [f"{b + 6}:move 656,491", f"{b + 6.5}:click 656,491", f"{b + 10}:rclick 300,300",
              f"{b + 15}:rclick 300,300"]
        b += 30
    secs = b + 10
    head = (f"# 1L-5 (tools/campaign_chain.py): {a['name']}, Mortal, episodes {[s for s, _ in eps]} by forced wins; "
            f"--seconds {secs}, ZEUS_STATE_DUMP_EVERY=10\n")
    return head + "; ".join(t) + "\n", "# tick address size value (tools/campaign_chain.py)\n" + "\n".join(pokes) + "\n", secs


def write(aid):
    s, p, _ = script(aid)
    open(os.path.join(SC, f"1L5-chain-{aid}.txt"), "w").write(s)
    open(os.path.join(SC, f"1L5-chain-{aid}.poke"), "w").write(p)


def run(aid):
    write(aid)
    _, _, secs = script(aid)
    name = f"1L5-chain-{aid}"
    out = os.path.join(RUNS, name)
    import shutil
    shutil.rmtree(out, ignore_errors=True)            # a fresh write dir (the roster), no old dumps
    os.makedirs(os.path.join(out, "dump"), exist_ok=True)
    os.makedirs(os.path.join(out, "write"), exist_ok=True)
    line = [l for l in open(os.path.join(SC, name + ".txt")) if not l.startswith("#")][0].strip()
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(out, "dump"), ZEUS_STATE_DUMP_EVERY="10",
               ZEUS_POKE=os.path.join(SC, name + ".poke"))
    cmd = [os.path.join(ROOT, "refs/zeus-poseidon-arm64/build/zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original/app/Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(out, "write"), "--seconds", str(secs), "--state-log",
           os.path.join(out, "state.txt"), "--screenshot", os.path.join(out, "end.bmp"), "--script",
           line.replace("DIR", out)]
    with open(os.path.join(out, "run.log"), "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), out], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), "--shots", out], cwd=ROOT)


def slot_starts(run_dir):
    """[(slot, first dump tick)] where the live record's slot (scenario +0x650 = 0x00902F78, slot + 1; game_file_load
    sets 0x00F2A7B0 from it) changes, the first dump included."""
    from oracle import Dump, dump_files
    out, last = [], None
    for f in dump_files(os.path.join(run_dir, "dump")):
        d = Dump(f)
        s = d.at(0x00902F78, "<i") - 1
        if s != last:
            out.append((s, int(os.path.basename(f)[5:11])))
            last = s
    return out


def _skip_colonies():
    """Ours as the poked exe: an episode whose next is the colony choice goes on to the next parent slot."""
    from sim.campaign import flow
    orig = flow.episode_rec

    def rec(a, slot):
        ep = orig(a, slot)
        if ep.get("next") == "colony":
            ep["next"] = "parent"
        return ep
    flow.episode_rec = rec


def check(aid):
    import tempfile
    import campaign_flow_check as F
    from oracle import Dump
    from sim.campaign import flow
    run_dir = os.path.join(RUNS, f"1L5-chain-{aid}")
    starts = slot_starts(run_dir)
    print(f"{aid}: exe slots at dumps {starts}")
    save = os.path.join(tempfile.mkdtemp(), "c.pkl")
    g = flow.start(aid, difficulty="Easy")
    bad0 = len(F.bad)
    rows = []
    for k, (slot, tick) in enumerate(starts):
        if k:                                         # the exe's date at this start: the month change that won
            d0 = Dump(os.path.join(run_dir, "dump", f"tick_{tick:06d}.bin"))
            want = d0.at(0x0091EC04, "<i") * 12 + d0.at(0x0091EC08, "<i")
            while g.year * 12 + g.month < want - 1:
                g.step(F.month(g))
            g.campaign["forced"] = True
            g.step(F.month(g))
            col = next((c["name"] for c in adventure(aid)["colonies"] if c["slot"] == slot), None)
            g = flow.proceed(g, save, colony=col)
        n = len(F.bad)
        F.compare_start(g, Dump(os.path.join(run_dir, "dump", f"tick_{tick:06d}.bin")), f"slot {slot} (exe dump {tick})")
        if g.campaign["slot"] != slot:
            F.eq("slot", g.campaign["slot"], slot)
        rows.append((slot, len(F.bad) - n))
    print(f"{aid}: {len(F.bad) - bad0} differences; per slot {rows}")
    return rows


def ours(aid, months=12):
    """Every episode of the adventure started our way (parent slots in order by forced wins, each colony from the
    episode that leads to it) and played `months` months headless: [(slot, start kind, date, ok or the error)]."""
    import tempfile
    import traceback
    from sim.campaign import flow
    a = adventure(aid)
    save = os.path.join(tempfile.mkdtemp(), "c.pkl")
    rows = []

    def play(g):
        flow.briefed(g)
        try:
            g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"] * months)
            return "ok"
        except Exception as e:                     # noqa: BLE001
            traceback.print_exc()
            return f"{type(e).__name__}: {e}"
    g = flow.start(aid, difficulty="Easy")
    colonies = [c for c in a["colonies"] if c.get("map") is not None]
    while True:
        st = g.campaign
        slot, kind, date = st["slot"], g.episode["start"], g.date()
        import copy
        probe = copy.deepcopy(g)
        rows.append((slot, kind, date, play(probe), probe.date(), probe.city.population))
        nxt = flow.next_step(g)
        if nxt["kind"] in ("end", "done"):
            break
        g.campaign["forced"] = True
        g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"])
        if flow.next_step(g)["kind"] == "colony":
            opts = flow.colony_options(g)
            # the colony not played yet (each is founded once)
            pick = next((n for n, cid, name in opts if any(c["n"] == n for c in colonies)), None)
            g = flow.proceed(g, save, colony=pick)
        else:
            g = flow.proceed(g, save)
        if g.campaign.get("done") or g.campaign["slot"] == slot:
            break
    return rows


if __name__ == "__main__":
    op, aid = sys.argv[1], sys.argv[2]
    if op == "scenario":
        write(aid)
    elif op == "run":
        run(aid)
    elif op == "check":
        check(aid)
    elif op == "ours":
        for r in ours(aid):
            print(r)
