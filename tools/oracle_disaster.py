"""Terrain disasters (lava flow 24, tidal wave 25, landslide 5, earthquake 3) in the exe, reached through an
adventure's episodes by forced wins (tools/campaign_chain.py), against ours (track 1L-5, docs/logic/events.md
"Terrain disasters"; the earthquake's own run is tools/oracle_quake.py).

Runs (RUNS below): the chain of forced wins up to the target slot, then the target episode is left alone: a shot and
a right click (closes a message) every 15 virtual seconds, an invasion's Bribe / a gift's Decline / a request's
Refuse clicked after it. A first pass (`run NAME`) dumps every 204 ticks to find the disaster's start tick and point;
`run NAME FROM TO EVERY [X,Y]` dumps FROM..TO every EVERY ticks, with the camera poked onto raw tile X,Y and dense
shots (every 1.5 s) over the virtual seconds that cover FROM..TO (from the first pass's `shot ... ticks K` lines).

    python3 tools/oracle_disaster.py run NAME [FROM TO EVERY [X,Y]]   # -> re/oracle/runs/1L5-dis-NAME
    python3 tools/oracle_disaster.py exe NAME          # the state table 0x0078C578 per dump: started objects, their
                                                       # state / ring / counters, tiles changed by class
    python3 tools/oracle_disaster.py check NAME CLASS  # ours (the same chain, the same episode) vs the exe from the
                                                       # start of the CLASS (24 lava, 25 tidal, 3 quake) object: the
                                                       # tiles with its terrain bit per dump, the terrain values of
                                                       # the region at the end
    python3 tools/oracle_disaster.py save NAME OUT CLASS [TICKS]  # our game TICKS ticks after the start (shots)
    python3 tools/oracle_disaster.py effects NAME CLASS  # effect figures (type 6) alive per dense dump, exe (minus the
                                                       # ambient ones before the start) vs ours (sim fx reports: the
                                                       # post step's, alive for their frames; no screen test)

Env: NODENSE=1 no dense shots (the emulator crawls with lava on screen: ~12 ticks per 15 s); RUNSUFFIX=-X a second run
of NAME (1L5-dis-NAME-X; also for exe/check); SECONDS_=N another length. The checked runs (10-31):
    python3 tools/oracle_disaster.py run europa4 && NODENSE=1 python3 tools/oracle_disaster.py run europa4 4280 5800 20
    RUNSUFFIX=-shots SECONDS_=2600 NODENSE=1 python3 tools/oracle_disaster.py run europa4 4280 4300 20 82,193
    python3 tools/oracle_disaster.py run odyssey3 && python3 tools/oracle_disaster.py run odyssey3 11620 11960 4 158,141
    RUNSUFFIX=-lava NODENSE=1 python3 tools/oracle_disaster.py run odyssey3 13240 13760 4
    python3 tools/oracle_disaster.py run econ2-marathon && ... run econ2-marathon 17940 18400 4 119,115
    python3 tools/oracle_disaster.py run econ2-taenarum && RUNSUFFIX=-lava NODENSE=1 ... run econ2-taenarum 22000 23200 4
    check europa4 24 / odyssey3 25 / econ2-marathon 25 / (RUNSUFFIX=-lava) odyssey3 24, econ2-taenarum 24: 0 differences.
The landslide (10-31; sim/disasters/landslide.py): dense runs need the first run's shot ticks, so copy its run.log and
scenario text to the suffixed names first (re/oracle/runs/1L5-dis-econ2-taenarum-X/run.log,
re/oracle/scenarios/1L5-dis-econ2-taenarum-X.txt), then
    RUNSUFFIX=-slide SECONDS_=3900 python3 tools/oracle_disaster.py run econ2-taenarum 22900 23100 4 119,134
    RUNSUFFIX=-slide2 SECONDS_=4000 python3 tools/oracle_disaster.py run econ2-taenarum 22990 23010 2 119,134
(-slide: the dust, m273..m281; -slide2 m276: the clean after-shot); tests/test_events.py test_landslide has the checks.
The effect figures (11-01, bugs.md 362): the lava's with the camera on it, dumps every 4 ticks (~705 live, the cap):
    RUNSUFFIX=-fx SECONDS_=2600 NODENSE=1 python3 tools/oracle_disaster.py run europa4 4560 4700 4 82,193
then `effects odyssey3 25` / `effects econ2-marathon 25` (the tidal waves' dense runs above).

State table 0x0078C578 (8 x 0x1C): +0 segment, +4 counter, +8 second counter, +0xC third (lava cooling / tidal
wait), +0x10 the event, +0x14 state, +0x18 started. Terrain 0x00CCE128 (u32), elevation 0x008E01FA (i8), piece 0x00D00D68.
"""
import os
import shutil
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
SC = os.path.join(ROOT, "re/oracle/scenarios")
RUNS_DIR = os.path.join(ROOT, "re/oracle/runs")
TABLE = 0x0078C578
TERRAIN, PIECE, ELEV = 0x00CCE128, 0x00D00D68, 0x008E01FA
YEAR, MONTH, DAY = 0x0091EC04, 0x0091EC08, 0x0091EC0C
N = 228
# name: (adventure, target slot, virtual seconds, what to look at)
RUNS = {
    "europa4": ("zeus_and_europa", 4, 1500, "lava flow (record 9, point 1, May year 0)"),
    "econ2-marathon": ("open_play_economic_2", 10, 1500, "tidal wave (record 1, points 1..8, Oct year 1)"),
    "econ2-taenarum": ("open_play_economic_2", 11, 4800, "lava flow (Mar year 2), landslides (Apr, May year 2)"),
    "odyssey3": ("the_odyssey", 3, 1300, "tidal wave (Feb y1), earthquake (Mar y1), lava flow (Apr y1)"),
}


def _name(n):
    return "1L5-dis-" + n + os.environ.get("RUNSUFFIX", "")    # RUNSUFFIX: a second run of NAME beside the first


def chain(aid, slot):
    """campaign_chain's script and pokes cut at the target slot: (clicks up to its start, the second it starts, the
    episodes before it)."""
    import campaign_chain as C
    a = C.adventure(aid)
    eps = C.order(a)
    k = [s for s, _ in eps].index(slot)
    s, _, _ = C.script(aid)
    line = s.split("\n")[1]
    acts = [x.strip() for x in line.split(";")]
    # the chain's per-episode blocks: proceed at b (+30 s, +14 more after a colony choice); keep the first k
    b, keep_to = 82, 79
    for j in range(k):
        col = eps[j + 1][1]
        b2 = b + (14 if col else 0)
        keep_to = b2 + 15                            # the last right click of that block
        b = b2 + 30
    acts = [x for x in acts if float(x.split(":")[0]) <= keep_to]
    return acts, keep_to, k


def script(name, dense=None):
    aid, slot, secs, _ = RUNS[name]
    secs = int(os.environ.get("SECONDS_", secs))                   # SECONDS_: another length
    acts, t0, k = chain(aid, slot)
    acts = [x for x in acts if ":shot " not in x or "/v" in x or "/c" in x]
    t = list(acts)
    s, i = t0 + 10.0, 0
    while s < secs:
        d = dense and dense[0] <= s < dense[1]
        t += [f"{s - 0.5:g}:shot DIR/m{i:03d}.bmp", f"{s:g}:rclick 300,300"]
        if not d:
            t += [f"{s + 7:g}:move 300,573", f"{s + 7.2:g}:click 300,573", f"{s + 7.4:g}:move 495,575",
                  f"{s + 7.6:g}:click 495,575"]
        i += 1
        s += 1.5 if d else 15
    head = f"# 1L-5 (tools/oracle_disaster.py {name}): {aid} to slot {slot} by forced wins, then left alone; --seconds {secs}\n"
    return head + "; ".join(t) + "\n"


def pokes(name, cam=None):
    aid, slot, secs, _ = RUNS[name]
    _, _, k = chain(aid, slot)
    start = 50 * k + 10                         # chain runs: a slot every ~50 ticks (campaign_chain slot_starts)
    out = []
    for tick in range(20, start - 5, 10):
        out.append(f"{tick} 0x00F2A6DB 1 1")
        if tick % 30 == 20:
            out.append(f"{tick} 0x0091EC0C 4 15")
    for tick in range(start, start + 600, 10):
        out.append(f"{tick} 0x00F2A6DB 1 0")
    if cam:
        x, y = cam
        col, row = max(0, ((x - y) * 30 + 6580) // 60), max(0, x + y - 18) & ~1   # an even row (bugs.md 363)
        for tick in range(start + 100, 60000, 400):
            out += [f"{tick} da2f64 4 {col}", f"{tick} da2f68 4 {row}"]
    return "# tick address size value (tools/oracle_disaster.py)\n" + "\n".join(out) + "\n"


def shot_ticks(name):
    """[(virtual second, tick)] from a run's log."""
    out = []
    log = os.path.join(RUNS_DIR, _name(name), "run.log")
    if not os.path.exists(log):
        return out
    sc = open(os.path.join(SC, _name(name) + ".txt")).read().split("\n")[1]
    when = {}
    for a in sc.split(";"):
        a = a.strip()
        if ":shot " in a:
            when[os.path.basename(a.split("shot ")[1])] = float(a.split(":")[0])
    for line in open(log, errors="replace"):
        if line.startswith("shot ") and " ticks " in line:
            p, tk = line.split()[1], int(line.split()[-1])
            if os.path.basename(p) in when:
                out.append((when[os.path.basename(p)], tk))
    return sorted(out)


def run(name, frm=None, to=None, every="204", cam=None):
    dense = None
    if frm is not None and not os.environ.get("NODENSE"):     # NODENSE=1: the dumps only, shots every 15 s
        st = shot_ticks(name)
        a = max([s for s, t in st if t <= int(frm)] or [0])
        b = min([s for s, t in st if t >= int(to)] or [RUNS[name][2]])
        dense = (a, b + 15)
    out = os.path.join(RUNS_DIR, _name(name))
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "dump"), exist_ok=True)
    os.makedirs(os.path.join(out, "write"), exist_ok=True)
    open(os.path.join(SC, _name(name) + ".txt"), "w").write(script(name, dense))
    open(os.path.join(SC, _name(name) + ".poke"), "w").write(pokes(name, cam))
    line = script(name, dense).split("\n")[1]
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(out, "dump"), ZEUS_STATE_DUMP_EVERY=str(every),
               ZEUS_POKE=os.path.join(SC, _name(name) + ".poke"))
    if frm is not None:
        env.update(ZEUS_STATE_DUMP_FROM=str(frm), ZEUS_STATE_DUMP_TO=str(to))
    cmd = [os.path.join(ROOT, "refs/zeus-poseidon-arm64/build/zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original/app/Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(out, "write"), "--seconds", str(os.environ.get("SECONDS_", RUNS[name][2])), "--state-log",
           os.path.join(out, "state.txt"), "--screenshot", os.path.join(out, "end.bmp"), "--script",
           line.replace("DIR", out)]
    with open(os.path.join(out, "run.log"), "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), out], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), "--shots", out], cwd=ROOT)


# --- reading the exe -----------------------------------------------------------------------------------------------

def grids(d):
    """(terrain u32, piece u8, elevation i8), [y][x]."""
    out = {}
    for b, a, s, o in d.zones:
        for nm, addr, dt, sz in (("ter", TERRAIN, "<u4", 4), ("pc", PIECE, "u1", 1), ("el", ELEV, "i1", 1)):
            if a <= addr < a + s and addr + N * N * sz <= a + s:
                out[nm] = np.frombuffer(d.data[o + addr - a:o + addr - a + N * N * sz], dt).reshape(N, N)
    return out.get("ter"), out.get("pc"), out.get("el")


def table(d, i):
    a = TABLE + i * 0x1C
    return dict(seg=d.at(a, "<i"), count=d.at(a + 4, "<i"), c2=d.at(a + 8, "<i"), c3=d.at(a + 0xC, "<i"),
                event=d.at(a + 0x10, "<i"), state=d.at(a + 0x14, "<i"), started=d.at(a + 0x18, "<B"))


def rows(name):
    from oracle import Dump, dump_files
    out = []
    for f in dump_files(os.path.join(RUNS_DIR, _name(name), "dump")):
        d = Dump(f)
        ter, pc, el = grids(d)
        out.append(dict(tick=int(os.path.basename(f)[5:11]), year=d.at(YEAR, "<i"), month=d.at(MONTH, "<i"),
                        day=d.at(DAY, "<i"), tab=[table(d, i) for i in range(8)], ter=ter, pc=pc, el=el,
                        slot=d.at(0x00902F78, "<i") - 1))
    return out


def exe(name):
    rs = rows(name)
    base = None
    for r in rs:
        live = [(i, t) for i, t in enumerate(r["tab"]) if t["started"] or t["state"]]
        lava = int(((r["ter"] & 0x1000000) > 0).sum()) if r["ter"] is not None else -1
        water = int(((r["ter"] & 4) > 0).sum()) if r["ter"] is not None else -1
        if base is None and r["el"] is not None:
            base = r["el"].copy()
        el = int((r["el"] != base).sum()) if r["el"] is not None and base is not None else -1
        print(f"tick {r['tick']:6d} slot {r['slot']} {r['year']} {r['month'] + 1:2d}/{r['day']:2d} lava {lava} "
              f"water {water} elev-changed {el} " + " ".join(f"#{i}:{t}" for i, t in live))


def _pass1_starts(name):
    """(run dir, [(slot, first dump tick)]): the slot starts of the adventure's chain run (re/oracle/runs/1L5-chain-ID,
    tools/campaign_chain.py run ID: the same clicks and pokes up to the target slot, dumps every 10 ticks)."""
    import campaign_chain as C
    d = os.path.join(RUNS_DIR, "1L5-chain-" + RUNS[name][0])
    return d, C.slot_starts(d)


def ours_game(name):
    """Ours through the same chain: at each slot start of the exe's run, step to the month before the exe's date,
    win (forced), proceed (campaign_chain.check's way)."""
    import tempfile
    import campaign_chain as C
    from oracle import Dump
    from sim.campaign import flow
    aid, slot, _, _ = RUNS[name]
    run_dir, starts = _pass1_starts(name)
    save = os.path.join(tempfile.mkdtemp(), "c.pkl")
    g = flow.start(aid, seed=1, difficulty="Easy")
    mon = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    for k, (s, tick) in enumerate(starts):
        if k:
            d0 = Dump(os.path.join(run_dir, "dump", f"tick_{tick:06d}.bin"))
            want = d0.at(YEAR, "<i") * 12 + d0.at(MONTH, "<i")
            while g.year * 12 + g.month < want - 1:
                g.step(mon)
            g.campaign["forced"] = True
            g.step(mon)
            col = next((c["name"] for c in C.adventure(aid)["colonies"] if c["slot"] == s), None)
            g = flow.proceed(g, save, colony=col)
        if s == slot:
            break
    flow.briefed(g)
    return g


def _started(g, cls=None):
    from sim import disasters
    st = disasters.state(g)
    if not st:
        return None
    return next((o for o in disasters._objects(st) if o["started"] and (cls is None or o["cls"] == cls)), None)


def _mask(cls):
    return {24: 0x1000000, 25: 0x4, 3: 0x300002}[cls]


def check(name, cls):
    """Ours against the exe from the start of the class's object: the start date and point, then per dense dump the
    tiles with the class's terrain bit inside the region (lava 0x1000000, tidal wave water 4), and at the end the
    terrain values of the region's tiles."""
    from sim import disasters
    rs = rows(name)
    st0 = None
    for r in rs:
        live = [(i, t) for i, t in enumerate(r["tab"]) if t["started"] and t["state"] in (0, 2)]
        if live:
            st0 = (r, live[0])
            break
    if st0 is None:
        print("the exe's object did not start in the dumps")
        return 1
    r0, (i0, t0) = st0
    calls = {24: 20, 25: 5, 3: 20}[cls]
    e0 = r0["tick"] - (t0["seg"] * calls + t0["count"])     # the exe's first update call (state 0 -> 2)
    g = ours_game(name)
    from sim import disasters as D
    orig = D._pick

    def pick(g_, st, ev, lo, hi):                 # the RNG's pick of a point (rng_15 % n) can't match: the exe's
        o = st["objects"][i0]
        if ev["type"] == cls and lo <= i0 + 1 <= hi and o is not None and D.start(g_, o, ev):
            return i0
        return orig(g_, st, ev, lo, hi)
    D._pick = pick
    while _started(g, cls) is None:
        g.step(1)
        if g.year > r0["year"] + 2:
            print("ours: did not start")
            return 1
    o = _started(g, cls)
    t_ours = g.tick
    print(f"exe: slot {i0} at dump {r0['tick']} ({r0['year']} {r0['month'] + 1}/{r0['day']}), first call ~{e0}; "
          f"ours: slot {o['idx']} at {g.date()} tick {t_ours}, rings {o['rings']}, nodes {len(o['nodes'])}")
    tiles = {(n["x"], n["y"]) for n in o["nodes"]}
    xs = np.array([t[0] for t in tiles]); ys = np.array([t[1] for t in tiles])
    m = _mask(cls)
    bad = 0
    ours_series, exe_series = [], []
    for r in rs:
        if r["tick"] < e0 or r["ter"] is None:
            continue
        want = r["tick"] - e0 - 1                 # ours has made its first call when we see it started
        while g.tick - t_ours < want:
            g.step(1)
        ex = {(int(x), int(y)) for x, y in zip(xs, ys) if r["ter"][y, x] & m}
        ou = {(int(x), int(y)) for x, y in zip(xs, ys) if int(g.world.flags[y, x]) & m}
        ok = ex == ou
        bad += not ok
        tab = r["tab"][i0]
        exe_series.append(len(ex)); ours_series.append(len(ou))
        print(f"exe tick {r['tick']} (+{want}) state {tab['state']} ring {tab['seg']} c3 {tab['c3']}: exe {len(ex)} "
              f"ours {len(ou)} (state {o['state']} ring {o['seg']} c3 {o['c3']})" +
              ("" if ok else f"  DIFF exe-only {sorted(ex - ou)[:6]} ours-only {sorted(ou - ex)[:6]}"))
    last = rs[-1]["ter"]
    vals = [(x, y, hex(int(last[y, x])), hex(int(g.world.flags[y, x]))) for x, y in sorted(tiles)
            if int(last[y, x]) != int(g.world.flags[y, x])]
    print(f"{bad} differing dumps; region terrain values at the last dump: {len(vals)} of {len(tiles)} differ "
          f"{vals[:6]}")
    return bad + len(vals)


def save(name, out, cls, after=200):
    """Our game `after` ticks after the class's object starts."""
    from sim import savefile
    g = ours_game(name)
    while _started(g, cls) is None:
        g.step(1)
    g.step(after)
    with open(out, "wb") as f:
        savefile.write(g, f)
    print(out, g.date(), g.tick)


def effects(name, cls):
    """The post step's effect figures (bugs.md 362): the exe's live type-6 figures per dense dump (the camera on the
    region; the count before the start is the ambient fish / urchins, taken off) against ours: the sim's fx reports
    from the object's start (sim/disasters.post_step), each alive for its frames (spray 20, lava 17..19 by variant,
    drops 12..15), counted on the same ticks after the start."""
    from oracle import Dump, dump_files
    FIG = 0x00DBD788
    ex, start, base, i0 = [], None, None, None
    for f in dump_files(os.path.join(RUNS_DIR, _name(name), "dump")):
        d = Dump(f)
        t = int(os.path.basename(f)[5:11])
        n = sum(1 for i in range(1, 2000) if d.at(FIG + i * 0x184 + 0x0E, "<B") == 1 and d.at(FIG + i * 0x184 + 0x0A, "<B") == 6)
        tab = [table(d, i) for i in range(8)]
        if start is None and any(x["started"] and x["state"] for x in tab):
            i0 = next(i for i, x in enumerate(tab) if x["started"] and x["state"])
            start = t - next(x["count"] for x in tab if x["started"] and x["state"]) - 4 * next(x["seg"] for x in tab if x["started"] and x["state"])
        if start is None:
            base = n
        else:
            ex.append((t - start, n - (base or 0)))
    life = {"spray": [20], "lava": [18, 18, 17, 19, 17, 19], "drops": [12, 13, 15, 15], "debris": [9]}
    g = ours_game(name)
    from sim import disasters as D
    orig = D._pick

    def pick(g_, st, ev, lo, hi):                 # the exe's point (check's way: the RNG's pick can't match)
        o = st["objects"][i0]
        if ev["type"] == cls and lo <= i0 + 1 <= hi and o is not None and D.start(g_, o, ev):
            return i0
        return orig(g_, st, ev, lo, hi)
    D._pick = pick
    alive = []
    life_of = lambda e: (e[0], e[0] + (life.get(e[1], [9])[e[6]] if len(life.get(e[1], [9])) > 1 else life.get(e[1], [9])[0]))
    while _started(g, cls) is None:
        g.fx = []                                 # the start tick's post step too
        g.step(1)
    alive += [life_of(e) for e in g.fx]
    t0 = g.tick - 1
    g.fx = []
    upto = max(a for a, _ in ex) if ex else 0
    for k in range(1, upto + 1):
        g.step(1)
        alive += [life_of(e) for e in g.fx]
        g.fx = []
        if any(a == k for a, _ in ex):
            ours = sum(1 for a, b in alive if a <= g.tick - 1 < b)
            exe_n = next(n for a, n in ex if a == k)
            print(f"+{k:4d} exe {exe_n:4d} ours {ours:4d}")
    print("start: exe estimate", start, "ours", t0)
    g.__dict__.pop("fx", None)
    D._pick = orig


if __name__ == "__main__":
    op = sys.argv[1]
    if op == "run":
        a = sys.argv[3:]
        cam = tuple(int(v) for v in a[3].split(",")) if len(a) > 3 else None
        run(sys.argv[2], *(a[:3]), cam=cam) if a else run(sys.argv[2])
    elif op == "exe":
        exe(sys.argv[2])
    elif op == "check":
        sys.exit(1 if check(sys.argv[2], int(sys.argv[3])) else 0)
    elif op == "save":
        save(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]) if len(sys.argv) > 5 else 200)
    elif op == "effects":
        effects(sys.argv[2], int(sys.argv[3]))
    elif op == "script":
        print(script(sys.argv[2]))
        print(pokes(sys.argv[2]))
