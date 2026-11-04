"""The working-city invasion oracle (track 1B, TODO 11-02 "Oracle run for the company AI's troop and building
branches"; docs/logic/military.md "Company AI target choice", docs/re/oracle.md).

"See a working city" (Adventures/tutorial15.sav, VeryEasy: a palace, 13 rabble, 3 horseman, 2 sanctuary hoplite
companies) gets an injected invasion: event record 3 (g_events 0x009173F4, 0x7C each; count 0x009173F0 -> 4), type 2,
dated May of year 0 (the save's month, warning 0: invasion_event_month 0x00476E20 spawns it at the change to June,
dump tick 286 = ours' tick 816), strength STRENGTH %, land point 1 (slot 0, logical (8, 63)), invader Nemea (city 2,
a rival). The run is at 1024 x 768. Stage 2 mobilizes the first company (rabble 1) at 58 s as military-mobilize.txt:
the military page (862, 368), its icon (905, 103: the view jumps to its standard), the camera poked to MOB_CAM, Mobilize
(885, 307), a map click (470, 430): F+0x90 = 1 from dump 39, its spot (19, 69) from dump 42 (ours: `mobilize 1` after
dump 41). The invasion message (Surrender / Bribe / Fight) is answered "Fight" (693, 738) once: later map clicks
would move the selected company.
The dump patch's ZEUS_STATE_DUMP_EXTRA adds the presence grid 0x00C5BD98 (u8 a tile, not saved).

    OIC_EVERY=1 OIC_FROM=280 OIC_SECS=2600 python3 tools/oracle_invcity.py run 2
                                                  # -> re/oracle/runs/1B-inv-city (dumps 280..2288, ~25 min; the
                                                  # scenario and poke files in re/oracle/scenarios; stage 1: no
                                                  # mobilization)
    python3 tools/oracle_invcity.py compare [FROM TO]   # ours from the same save, event and mobilization: per AI day
                                                  # the presence grid, the event's target, each company's mode,
                                                  # layout and target (+0x3A / +0x3C); every company's morale,
                                                  # members (+0x28) and waver counters (+0x73 / +0x66)

Other companies: OIC_COMP (slot) and OIC_ICON (its icon on the military page, x,y at 1024 x 768): horseman company 9
is the icon 951,121 (re/oracle/runs/1B-inv-city-horse, made by `OIC_NAME=1B-inv-city-horse OIC_COMP=9
OIC_ICON=951,121 OIC_EVERY=1 OIC_FROM=36 OIC_SECS=1800 python3 tools/oracle_invcity.py run 2`; compared by
`OSW_COMP=9 OSW_RUN=1B-inv-city-horse python3 tools/oracle_soldier_walk.py`).

Exe dump k = ours' tick T0 + k (T0 = 530: the save's day 10 of May, cycle step 20).
"""
import os
import shutil
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, ROOT)
SC = os.path.join(ROOT, "re/oracle/scenarios")
RUNS = os.path.join(ROOT, "re/oracle/runs")
NAME = os.environ.get("OIC_NAME", "1B-inv-city")
EV, ESZ, NEV = 0x009173F4, 0x7C, 0x009173F0
PRESENCE, N = 0x00C5BD98, 228
FORM, FMS = 0x00DB7B40, 0x9C
INDEX, CITY, POINT, STRENGTH = 3, 2, 1, 50
T0 = 530
SECS = int(os.environ.get("OIC_SECS", 400))
LAUNCH = ["5:key 27", "12:click 220,101", "17:char 78", "20:click 556,320", "27:click 644,523", "33:click 588,476",
          "45:rclick 300,300", "50:click 90,10", "52:click 120,41", "55:click 320,253"]       # 1024 x 768 (mil-a)
CAM = (8, 63)          # the camera's target (logical): the point
MOB_AT = float(os.environ.get("OIC_MOB_AT", 58))       # virtual second of the mobilization (stage 2; ~ dump 16)
MOB_XY = (470, 430)    # the destination click (screen): where the camera's tile shows (shot s060 of stage 1)
MOB_CAM, MOB_CAM_T = (18, 67), 30                      # the camera before the map click (logical), its poke tick
FIGHT = (234.0,)   # the message is up from dump 286 (~ 226 s); one click: later map clicks move the selected company
COMP = int(os.environ.get("OIC_COMP", 1))             # the company mobilized in stage 2 (1: rabble; 9: horsemen)
ICON = tuple(int(v) for v in os.environ.get("OIC_ICON", "905,103").split(","))   # its icon on the military page


def pokes():
    a = EV + INDEX * ESZ
    f = [(0x00, 2, INDEX), (0x02, 1, 2), (0x03, 1, 4), (0x06, 2, 1), (0x08, 2, -1), (0x0A, 2, -1),
         (0x0C, 2, STRENGTH), (0x0E, 2, -1), (0x10, 2, 5), (0x12, 2, 10), (0x14, 2, 0), (0x16, 2, -1), (0x18, 2, 1),
         (0x1A, 2, 2), (0x1C, 2, POINT), (0x1E, 2, -1), (0x20, 2, 1), (0x22, 2, 8), (0x24, 2, -1), (0x26, 2, -1),
         (0x28, 4, 2), (0x2C, 2, 0), (0x34, 2, -1), (0x36, 1, 0), (0x38, 1, 0), (0x52, 2, -1), (0x54, 2, -1),
         (0x58, 2, CITY), (0x5A, 2, -1), (0x5C, 2, 1), (0x5E, 2, 8), (0x78, 1, 0)]
    out = [f"5 {a + o:x} {n} {v & ((1 << 8 * n) - 1)}" for o, n, v in f]
    out.append(f"5 {NEV:x} 4 {INDEX + 1}")
    return "# tick address size value (tools/oracle_invcity.py)\n" + "\n".join(out) + "\n"


def cam_pokes(tick, xy=CAM, origin=(44, 44)):
    """The camera (0x00DA2F64 col / 0x00DA2F68 row, even rows) so that the raw tile xy is near the view's centre at
    1024 x 768 (oracle_invasion's 800 x 600 rule shifted by the wider view: hypothesis, checked on the shots)."""
    x, y = xy[0] + origin[0], xy[1] + origin[1]
    col = max(0, ((x - y) * 30 + 6580) // 60 - 3)
    row = max(0, x + y - 24) & ~1
    return [f"{tick} da2f64 4 {col}", f"{tick} da2f68 4 {row}"]


def press(t, x, y):
    return [(t, f"move {x},{y}"), (t + 0.3, f"down {x},{y}"), (t + 0.6, f"up {x},{y}")]


def script(stage):
    ev = [(float(a.split(":")[0]), a.split(":", 1)[1]) for a in LAUNCH]
    for k in range(int((SECS - 58) // 4)):
        ev.append((58 + 4 * k, f"shot DIR/s{k:03d}.bmp"))
    for f in FIGHT:                                    # Fight to defend city (the invasion message pauses the game)
        ev += press(f, 693, 738)
    if stage >= 2:
        m = MOB_AT
        # as military-mobilize.txt (mil-a); the company's icon centres the view on its standard: the camera is poked
        # to MOB_CAM at tick MOB_CAM_T (between the icon and the map click), the map click is where CAM showed
        ev += [(m, "click 862,368"), (m + 2.5, "shot DIR/mil.bmp"), (m + 3, "click %d,%d" % ICON),
               (m + 4.5, "shot DIR/comp.bmp")] + press(m + 12, 885, 307) + [(m + 13, "shot DIR/mob0.bmp")] \
            + press(m + 14, *MOB_XY) + [(m + 15, "shot DIR/mob1.bmp")]
    ev.sort(key=lambda e: e[0])
    return (f"# 1B working-city invasion (tools/oracle_invcity.py, stage {stage}); --seconds {SECS}; 1024 x 768\n"
            + "; ".join(f"{t:g}:{a}" for t, a in ev) + "\n")


def run(stage=1):
    out = os.path.join(RUNS, NAME)
    shutil.rmtree(out, ignore_errors=True)
    for d in ("dump", "write"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    sc = script(stage)
    pk = pokes() + "\n".join(cam_pokes(300) + (cam_pokes(MOB_CAM_T, MOB_CAM) if stage >= 2 else [])) + "\n"
    open(os.path.join(SC, NAME + ".txt"), "w").write(sc)
    open(os.path.join(SC, NAME + ".poke"), "w").write(pk)
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(out, "dump"),
               ZEUS_STATE_DUMP_EVERY=os.environ.get("OIC_EVERY", "1"),
               ZEUS_STATE_DUMP_FROM=os.environ.get("OIC_FROM", "280"),
               ZEUS_STATE_DUMP_TO=os.environ.get("OIC_TO", "100000"),
               ZEUS_STATE_DUMP_ZONES="13,28,31,37,38,39,5,6",
               ZEUS_STATE_DUMP_EXTRA=f"{PRESENCE:x}:{N * N}",
               ZEUS_POKE=os.path.join(SC, NAME + ".poke"))
    cmd = [os.path.join(ROOT, "refs/zeus-poseidon-arm64/build/zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original/app/Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(out, "write"), "--seconds", str(SECS), "--state-log", "/dev/null",
           "--screenshot", os.path.join(out, "end.bmp"), "--script", sc.split("\n")[1].replace("DIR", out)]
    with open(os.path.join(out, "run.log"), "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), out], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), "--shots", out], cwd=ROOT)


MOB_TICK, MOB_DEST = 41, (19, 69)   # the map click lands between dumps 41 and 42 (F+0x32/+0x34 = (19, 69) from 42)


def spawn_day(g):
    """The day hook (sim/hooks.py, end of run_day) that spawns the event at the change to June (ours' tick T0 + 286):
    as the exe's month_advance block, before the walkers of that tick."""
    from sim.military import invaders
    if g.tick != T0 + 286:
        return
    ev = dict(id=INDEX, amount=STRENGTH, city=CITY, landing=0, ships=0)
    invaders.invade(g, ev, point=invaders.pick_point(g, POINT), strength=STRENGTH, target_class=0)


def ours_game():
    """Ours: the working city (sim/campaign bigcity, VeryEasy, tick T0), the event armed, company 1 mobilized to the
    exe's spot at the exe's tick (dump MOB_TICK: the click comes between it and the next)."""
    from sim.campaign import flow
    from sim import hooks
    from sim.systems import walkers
    walkers.RATE100_TPF = 1                       # the harness's virtual clock fires the rate-100 gate every tick
    g = flow.start("bigcity", seed=1, difficulty="VeryEasy")
    flow.briefed(g)
    assert g.tick == T0, g.tick
    hooks.attach(g, "day", "oracle_invcity:spawn_day")
    g.step(MOB_TICK)
    ox, oy = g.world.origin
    g.command(f"mobilize {COMP} {MOB_DEST[0] + ox} {MOB_DEST[1] + oy}")
    return g


def exe_state(d):
    """A dump's AI state: enemy companies {id: (mode, layout, +0x3A/+0x3C, +0x7A/+0x7C, position)}, the event's
    +0x42 / +0x44, the presence grid's nonzero cells {(x, y): v} (grid index: ours' raw tile)."""
    comps = {}
    for i in range(35, 100):
        a = FORM + i * FMS
        if not d.at(a, '<B'):
            continue
        ty = d.at(a + 4, '<h')
        if ty not in (0x28, 0x29, 0x2A):
            continue
        comps[i] = dict(mode=d.at(a + 0x91, '<B'), layout=d.at(a + 0x2A, '<h'),
                        t3a=(d.at(a + 0x3A, '<h'), d.at(a + 0x3C, '<h')), t7a=(d.at(a + 0x7A, '<h'), d.at(a + 0x7C, '<h')),
                        pos=(d.at(a + 0x2E, '<h'), d.at(a + 0x30, '<h')), n=d.at(a + 0x28, '<B'))
    e = EV + INDEX * ESZ
    ev = dict(target=(d.at(e + 0x42, '<h'), d.at(e + 0x44, '<h')), lead=(d.at(e + 0x3C, '<h'), d.at(e + 0x3E, '<h')))
    raw = d.block(-2) if any(b == -2 for b, *_ in d.zones) else b""
    pres = {(i % N, i // N): v for i, v in enumerate(raw) if v}
    return comps, ev, pres


def exe_palace(d):
    """The palace companies in use: {slot: (morale +0x2C, members +0x28, +0x73, +0x66)}; the invaders' morale too."""
    out = {}
    for i in list(range(1, 21)) + list(range(35, 100)):
        a = FORM + i * FMS
        if d.at(a, '<B') and d.at(a + 0x69, '<B') == 0:
            out[i] = (d.at(a + 0x2C, '<h'), d.at(a + 0x28, '<B'), d.at(a + 0x73, '<B'), d.at(a + 0x66, '<B'))
    return out


def ours_palace(g):
    from sim.military import forces, invaders, morale
    out = {s: (c.get("morale", 50), morale.player_count(g, s, c), c.get("rout", 0), c.get("waver", 0))
           for s, c in forces.companies(g).items() if s <= 20}
    for cid, c in invaders.ecomps(g).items():
        n = morale.enemy_count(g, cid)
        if n:
            out[cid] = (c["morale"], n, c.get("rout", 0), c.get("waver", 0))
    return out


def ours_state(g):
    from sim.military import invaders
    comps = {}
    for cid in sorted(invaders.ecomps(g)):
        c = invaders.ecomps(g)[cid]
        comps[cid] = dict(mode=c["mode"], layout=c["layout"], target=c.get("target"), pos=c.get("pos"),
                          n=len(invaders.alive_members(g, c)))
    inv = next(iter(invaders.invasions(g).values()), None)
    pres = invaders.presence(g)
    return comps, (inv or {}).get("target"), {(i % N, i // N): v for i, v in enumerate(pres) if v}


def compare(lo=0, hi=10 ** 9, every=51):
    """Per AI day (ours' tick % 51 == 30, after step 29; exe dump = ours' tick - T0): the presence grid, the event's
    target and per company (paired by order) mode, layout and target; the special-mode roll replays the exe's outcome
    (oracle_invasion._replay_special)."""
    from oracle import Dump, dump_files
    from sim.military import invaders
    import oracle_invasion
    files = [(int(os.path.basename(p).split("_")[1].split(".")[0]), p)
             for p in dump_files(os.path.join(RUNS, NAME, "dump"))]
    have = dict(files)
    g = ours_game()
    ox, oy = g.world.origin
    oracle_invasion._replay_special(g, [(t + T0, p) for t, p in files], invaders)
    days = bad = 0
    t = g.tick
    while True:
        t += 1
        while (t % 51) != 30:
            t += 1
        k = t - T0
        if k > max(have) or k > hi:
            break
        if k < lo or k not in have:
            continue
        g.step(t - g.tick)
        ec, eev, ep = exe_state(Dump(have[k]))
        oc, otg, op = ours_state(g)
        otg = None if otg is None else (otg[0] - ox, otg[1] - oy)
        lines = []
        if ep != op:
            dk = sorted(set(ep) ^ set(op) | {c for c in ep if c in op and ep[c] != op[c]})
            lines.append(f"  presence: exe {len(ep)} cells, ours {len(op)}; differ at {len(dk)}: "
                         + " ".join(f"{c}:{ep.get(c, 0)}/{op.get(c, 0)}" for c in dk[:8]))
        if ec and otg is not None and eev["target"] != otg:
            lines.append(f"  event target: exe {eev['target']} ours {otg}")
        for (ei, e), (oi, o) in zip(sorted(ec.items()), sorted(oc.items())):
            otgt = None if o["target"] is None else (o["target"][0] - ox, o["target"][1] - oy)
            if (e["mode"], e["layout"], e["t3a"]) != (o["mode"], o["layout"], otgt):
                lines.append(f"  c{ei}/{oi}: exe mode {e['mode']} layout {e['layout']} target {e['t3a']} (+0x7A "
                             f"{e['t7a']}) n {e['n']}; ours {o['mode']} {o['layout']} {otgt} n {o['n']}")
        ex, ou = exe_palace(Dump(have[k])), ours_palace(g)
        mo = [f"{s}: exe {ex.get(s)} ours {ou.get(s)}" for s in sorted(set(ex) | set(ou)) if ex.get(s) != ou.get(s)]
        if mo:
            lines.append("  morale, members, +0x73, +0x66: " + "; ".join(mo[:6]))
        days += 1
        bad += bool(lines)
        print(f"day at dump {k} (ours {t}): {len(ec)} companies, presence {len(ep)} cells"
              + ("" if not lines else "\n" + "\n".join(lines[:10])))
    print(f"total: {days} AI days compared, {bad} differ")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["run"]:
        run(int(a[1]) if len(a) > 1 else 1)
    elif a[:1] == ["compare"]:
        compare(*[int(x) for x in a[1:3]])
    else:
        print(__doc__)
