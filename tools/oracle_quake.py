"""Terrain disasters (scenario types 3 / 24 / 25) in the exe against ours (track 1L-5, docs/logic/events.md "Terrain
disasters").

@Athens through the Ages: episode 0 is won at its first month change (forced, as tools/campaign_chain.py), episode 1
(the same map, an empty city) runs on: its record 24 is an earthquake at disaster point 1 (raw (109, 190)) in January
of year +2. The camera is poked onto the point (0x00DA2F64 / 0x00DA2F68, tools/oracle_invasion.py) once episode 1 is
on; a shot and a right click (closes a message) every 15 virtual seconds.

    python3 tools/oracle_quake.py run [FROM TO EVERY]  # -> re/oracle/runs/1L5-quake (FROM..TO dumps every EVERY ticks;
                                                       # used: 19400 21600 10)
    python3 tools/oracle_quake.py exe                  # the exe's disaster state per dump: state table 0x0078C578,
                                                       # the tiles cracked so far (terrain 0x2000000 -> 0x300002)
    python3 tools/oracle_quake.py check                # ours (the same episode, stepped to each dump's date and tick
                                                       # offset from the quake's start) vs the exe: cracked tiles
    python3 tools/oracle_quake.py save OUT [TICKS]     # our game TICKS ticks after the quake's start (play-mode shots)
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
RUNS = os.path.join(ROOT, "re/oracle/runs")
NAME = "1L5-quake"
AID = "athens_through_the_ages"
POINT = (109, 190)                  # disaster point 1, raw
SECS = 1500
DENSE = (1230, 1420)        # virtual seconds of a shot every 1.5 s (the quake: ticks ~20450..20900)
TABLE = 0x0078C578
TERRAIN, PIECE = 0x00CCE128, 0x00D00D68
YEAR, MONTH, DAY = 0x0091EC04, 0x0091EC08, 0x0091EC0C
N = 228


def script():
    from campaign_chain import LIST, MENU
    i = LIST.index(AID)
    t = [MENU, "26:move 590,260", "26.5:click 590,260", f"30:move 120,{162 + 16 * i}", f"30.5:click 120,{162 + 16 * i}",
         "33:move 315,442", "33.5:click 315,442", "75:move 656,491", "75.5:click 656,491", "79:rclick 300,300",
         "81:shot DIR/v0.bmp", "82:move 296,555", "82.5:click 296,555", "88:move 656,491", "88.5:click 656,491",
         "92:rclick 300,300", "97:rclick 300,300"]
    k = 0
    s = 105.0
    while s < SECS:                                   # a shot, close the message; an invasion: Bribe; a gift: Decline
        t += [f"{s - 0.5:g}:shot DIR/m{k:03d}.bmp", f"{s:g}:rclick 300,300"]
        if DENSE[0] <= s < DENSE[1]:                  # a request's Refuse (its buttons ignore the right click)
            t += [f"{s + 0.3:g}:move 495,575", f"{s + 0.4:g}:click 495,575"]
        else:
            t += [f"{s + 7:g}:move 300,573", f"{s + 7.2:g}:click 300,573", f"{s + 7.4:g}:move 495,575",
                  f"{s + 7.6:g}:click 495,575"]
        k += 1
        s += 1.5 if DENSE[0] <= s < DENSE[1] else 15
    head = f"# 1L-5 (tools/oracle_quake.py): {AID} episode 0 won by force, episode 1 left alone; --seconds {SECS}\n"
    return head + "; ".join(t) + "\n"


def pokes():
    x, y = POINT
    col, row = max(0, ((x - y) * 30 + 6580) // 60), max(0, x + y - 18) & ~1   # an even row (bugs.md 363)
    out = []
    for tick in range(20, 56, 5):                     # episode 0 won at its first month change (campaign_chain)
        out.append(f"{tick} 0x00F2A6DB 1 1")
        if tick in (20, 50):
            out.append(f"{tick} 0x0091EC0C 4 15")
    for tick in range(70, 400, 10):                   # the flag outlives the episode change: cleared in episode 1
        out.append(f"{tick} 0x00F2A6DB 1 0")
    for tick in range(150, 30000, 400):               # the camera on the point (episode 1 from tick ~60)
        out += [f"{tick} da2f64 4 {col}", f"{tick} da2f68 4 {row}"]
    return "# tick address size value (tools/oracle_quake.py)\n" + "\n".join(out) + "\n"


def run(frm=None, to=None, every="204"):
    out = os.path.join(RUNS, NAME)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "dump"), exist_ok=True)
    os.makedirs(os.path.join(out, "write"), exist_ok=True)
    open(os.path.join(SC, NAME + ".txt"), "w").write(script())
    open(os.path.join(SC, NAME + ".poke"), "w").write(pokes())
    line = script().split("\n")[1]
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(out, "dump"), ZEUS_STATE_DUMP_EVERY=str(every),
               ZEUS_POKE=os.path.join(SC, NAME + ".poke"))
    if frm is not None:
        env.update(ZEUS_STATE_DUMP_FROM=str(frm), ZEUS_STATE_DUMP_TO=str(to))
    cmd = [os.path.join(ROOT, "refs/zeus-poseidon-arm64/build/zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original/app/Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(out, "write"), "--seconds", str(SECS), "--state-log",
           os.path.join(out, "state.txt"), "--screenshot", os.path.join(out, "end.bmp"), "--script",
           line.replace("DIR", out)]
    with open(os.path.join(out, "run.log"), "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), out], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), "--shots", out], cwd=ROOT)


def terrain(d):
    """(terrain u32 [y][x], piece u8 [y][x]) of a dump."""
    for b, a, s, o in d.zones:
        if a <= TERRAIN < a + s:
            ter = np.frombuffer(d.data[o + TERRAIN - a:o + TERRAIN - a + N * N * 4], "<u4").reshape(N, N)
        if a <= PIECE < a + s:
            pc = np.frombuffer(d.data[o + PIECE - a:o + PIECE - a + N * N], "u1").reshape(N, N)
    return ter, pc


def state(d, i=0):
    a = TABLE + i * 0x1C
    return dict(seg=d.at(a, "<i"), count=d.at(a + 4, "<i"), event=d.at(a + 0x10, "<i"), state=d.at(a + 0x14, "<i"),
                started=d.at(a + 0x18, "<B"))


def cracked(ter, pc):
    """Tiles turned to cracked rock: 0x300002 with piece 0x80."""
    return {(int(x), int(y)) for y, x in zip(*np.nonzero(((ter & 0x300002) == 0x300002) & ((pc & 0x80) > 0)))}


def exe_rows(run_dir=None):
    from oracle import Dump, dump_files
    run_dir = run_dir or os.path.join(RUNS, NAME)
    rows = []
    for f in dump_files(os.path.join(run_dir, "dump")):
        d = Dump(f)
        ter, pc = terrain(d)
        rows.append((int(os.path.basename(f)[5:11]), d.at(YEAR, "<i"), d.at(MONTH, "<i"), d.at(DAY, "<i"),
                     state(d, 0), cracked(ter, pc), int(((ter & 0x2000000) > 0).sum())))
    return rows


def exe():
    for tick, y, m, day, st, cr, fault in exe_rows():
        print(f"tick {tick:6d} {y} {m + 1:2d}/{day:2d} point 0: {st}  cracked {len(cr)} fault {fault}")


def ours_game():
    import tempfile
    from sim.campaign import flow
    g = flow.start(AID, seed=1, difficulty="Easy")
    flow.briefed(g)
    g.campaign["forced"] = True
    g.step(g.rules["ticks_per_day"] * g.rules["days_per_month"])
    g = flow.proceed(g, os.path.join(tempfile.mkdtemp(), "c.pkl"))
    flow.briefed(g)
    return g


def _quake(g):
    q = (getattr(g, "disasters", None) or {}).get("objects") or []
    return next((o for o in q if o and o["started"]), None)


def check():
    """The cracked tiles per dump while the exe's point 0 runs, against ours at the same tick offset from the start
    (state 0 -> 2: the first call of the update after the month pass)."""
    rows = exe_rows()
    start = next((r for r in rows if r[4]["started"]), None)
    if start is None:
        print("the exe's quake did not start in this run")
        return 1
    g = ours_game()
    while _quake(g) is None:
        g.step(1)
        if g.year > start[1] + 1:
            print("ours: no quake")
            return 1
    o = _quake(g)
    t0 = g.tick
    print(f"ours: started at {g.date()} tick {t0}; exe's first started dump {start[0]} ({start[1]} {start[2] + 1})")
    # the exe's counter at its first started dump tells the offset since the start (20 calls per ring)
    bad = 0
    e0 = None
    for tick, y, m, day, st, cr, fault in rows:
        if not st["started"] and st["state"] != 7:
            continue
        if e0 is None:                          # ticks since the exe's start: ring index * 20 + counter
            e0 = tick - (st["seg"] * 20 + st["count"])
        want = tick - e0
        while g.tick - t0 < want:
            g.step(1)
        ours = set(map(tuple, o["cracked"]))
        diff = (cr - ours, ours - cr)
        ok = not diff[0] and not diff[1]
        bad += not ok
        print(f"exe tick {tick} (+{want}) state {st['state']} ring {st['seg']}: exe {len(cr)} ours {len(ours)} "
              f"(ring {o['seg']}, state {o['state']})" + ("" if ok else f"  DIFF exe-only {sorted(diff[0])[:8]} "
                                                          f"ours-only {sorted(diff[1])[:8]}"))
    from oracle import Dump
    ter, _ = terrain(Dump(rows[-1][0] and os.path.join(RUNS, NAME, "dump", f"tick_{rows[-1][0]:06d}.bin")))
    vals = [(x, y, hex(int(ter[y, x])), hex(int(g.world.flags[y, x]))) for x, y in o["cracked"]
            if int(ter[y, x]) != int(g.world.flags[y, x])]
    print(f"{bad} differing dumps; terrain values of the cracked tiles at the last dump: {len(vals)} differ {vals[:5]}")
    return bad + len(vals)


def save(out, after=200):
    """Our game `after` ticks after the quake's start (negative: before it)."""
    from sim import savefile
    g = ours_game()
    while _quake(g) is None:
        g.step(1)
    if after < 0:
        t = g.tick + after
        g = ours_game()
        g.step(t - g.tick)
    else:
        g.step(after)
    with open(out, "wb") as f:
        savefile.write(g, f)
    print(out, g.date(), g.tick)


if __name__ == "__main__":
    op = sys.argv[1]
    if op == "run":
        run(*sys.argv[2:5]) if len(sys.argv) > 2 else run()
    elif op == "exe":
        exe()
    elif op == "check":
        sys.exit(1 if check() else 0)
    elif op == "save":
        save(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 200)
