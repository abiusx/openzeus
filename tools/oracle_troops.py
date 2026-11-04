"""A call for troops answered with real companies, exe against ours (track 1L-5, docs/play/world.md "Requests",
docs/logic/events.md "Requests and invasions").

"See a working city" (Adventures/tutorial15.sav, VeryEasy: 3 horseman companies at the palace) gets an injected
record: Hercules' Labors' call for troops by Cyme (1L5-troops record 2, as the exe holds it before it runs) turned into
a call by Mantineia (city 3, ally) attacked by Nemea (+0x6F = 2, rival), due this May (year 0, month 4, lead 1),
already active with countdown 2: the May month-end pass posts the call (cd == lead), the June pass is its due month.
Poked into g_events (0x009173F4, 124 bytes; count 0x009173F0) at tick POKE_T; the day 0x0091EC0C is poked to 15 to
reach the month ends quickly (not while the dialog clicks run).

    python3 tools/oracle_troops.py run [STAGE]   # -> re/oracle/runs/1L5-troopsgo (stage 1: shots only; 2: the
                                                 # message's Dispatch, the army dialog, companies, Dispatch)
    python3 tools/oracle_troops.py exe           # the record, the companies (+0x82 away) and soldiers per dump
    python3 tools/oracle_troops.py ours          # ours: the same record injected, dispatched, month by month
    python3 tools/oracle_troops.py march         # the march to the land exit (OTR_NAME=1L5-troopsmarch, OTR_FAST=0):
                                                 # the horsemen's tiles every 20 ticks, exe against ours (bugs.md 369)
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
NAME = os.environ.get("OTR_NAME", "1L5-troopsgo")
EVENTS, YEAR, MONTH, DAY = 0x009173F4, 0x0091EC04, 0x0091EC08, 0x0091EC0C
# re/oracle/runs/1L5-troops tick 102, record 2 (Cyme's call for troops, Hercules' Labors episode 0)
CYME = bytes.fromhex(
    "0200010118001800ffffffff14001400ffffffff00000000ffffffff05000500ffffffffffffffff000000000300010000000000ffff"
    "00000000000000000000000000000000000000000000000000000000ffffffff00000200ffff0000310001070000ffff0000000000"
    "0000000008000000000000000000000000")
CITY, RIVAL, INDEX = 3, 2, 3          # Mantineia, attacked by Nemea; the working city holds records 0..2
POKE_T = 20
LAUNCH = ["5:key 27", "12:click 220,101", "17:char 78", "20:click 556,320", "27:click 644,523", "33:click 588,476",
          "45:rclick 300,300"]


def record():
    r = bytearray(CYME)
    struct.pack_into("<h", r, 0, INDEX)
    r[3] = 4                                            # month: May
    struct.pack_into("<hh", r, 0x14, 0, 0)              # year 0 (start year 1340 BC)
    struct.pack_into("<hh", r, 0x1C, CITY, CITY)        # city group
    struct.pack_into("<h", r, 0x2C, 1)                  # lead
    struct.pack_into("<h", r, 0x2E, 2)                  # countdown
    r[0x32] = 1                                         # active
    struct.pack_into("<h", r, 0x58, RIVAL)
    r[0x6F] = RIVAL
    return bytes(r)


def pokes(stage):
    r = record()
    out = [f"{POKE_T} 0x{EVENTS + INDEX * 124 + i:08X} 4 {struct.unpack_from('<I', r, i)[0]}" for i in range(0, 124, 4)]
    out.append(f"{POKE_T} 0x{EVENTS - 4:08X} 4 {INDEX + 1}")
    out.append(f"{POKE_T + 5} 0x{DAY:08X} 4 15")              # May ends: the call
    if os.environ.get("OTR_FAST", "1") == "1":               # later months fast (the dialog pauses the game at ~31)
        for t in range(40, 40000, 20):                       # OTR_FAST=0: real months (the march out to the exit)
            out.append(f"{t} 0x{DAY:08X} 4 15")
    return "# tick address size value (tools/oracle_troops.py)\n" + "\n".join(out) + "\n"


def script(stage):
    t = list(LAUNCH)
    s, k = 46.0, 0
    while s < (68 if stage >= 2 else 120):               # dense shots around the call
        t.append(f"{s:g}:shot DIR/a{k:03d}.bmp")
        s += 2
        k += 1
    if stage >= 2:
        t += CLICKS
    s = 160.0
    while s < SECS:
        t += [f"{s - 0.5:g}:shot DIR/m{k:03d}.bmp", f"{s:g}:rclick 300,300"]
        s += 10
        k += 1
    return f"# 1L-5 troops abroad (tools/oracle_troops.py, stage {stage}); --seconds {SECS}\n" + "; ".join(t) + "\n"


SECS = int(os.environ.get("OTR_SECS", 900))
# stage 2 (the call shows at ~64 s, a009, and pauses the game): its Dispatch now (98, 573) -> the army dialog (screen
# 0x21; at 800 x 600 the horsemen rows are at y 140 + 18 i: "The Frogs", "The Combatants", "The Tigers"; no hoplite
# phalanx; Ares' Sparti / Ares' Guard under Mythical Warriors, not enlisted here: ours has no sanctuary companies,
# bugs.md 368), each horseman row, its Dispatch (553, 548)
CLICKS = ["70:move 98,573", "70.3:down 98,573", "70.6:up 98,573", "72:shot DIR/army.bmp"]
for _i, _y in enumerate((140, 158, 176)):
    _t = 74 + 3 * _i
    CLICKS += [f"{_t}:move 200,{_y}", f"{_t + 0.3}:down 200,{_y}", f"{_t + 0.6}:up 200,{_y}", f"{_t + 2}:shot DIR/army_sel{_i}.bmp"]
CLICKS += ["84:move 553,548", "84.3:down 553,548", "84.6:up 553,548", "86:shot DIR/army_go.bmp",   # 'Dispatch forces?'
           "88:move 433,251", "88.3:down 433,251", "88.6:up 433,251", "90:shot DIR/after.bmp"]


def run(stage=1):
    out = os.path.join(RUNS, NAME)
    shutil.rmtree(out, ignore_errors=True)
    for d in ("dump", "write"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    open(os.path.join(SC, NAME + ".txt"), "w").write(script(stage))
    open(os.path.join(SC, NAME + ".poke"), "w").write(pokes(stage))
    line = script(stage).split("\n")[1]
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(out, "dump"), ZEUS_STATE_DUMP_EVERY="20",
               ZEUS_POKE=os.path.join(SC, NAME + ".poke"))
    cmd = [os.path.join(ROOT, "refs/zeus-poseidon-arm64/build/zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original/app/Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(out, "write"), "--seconds", str(SECS), "--state-log",
           os.path.join(out, "state.txt"), "--screenshot", os.path.join(out, "end.bmp"), "--script",
           line.replace("DIR", out)]
    with open(os.path.join(out, "run.log"), "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), out], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), "--shots", out], cwd=ROOT)


def exe():
    from oracle import Dump, dump_files
    import oracle_requests as R
    import oracle_military as M
    last = None
    for f in dump_files(os.path.join(RUNS, NAME, "dump")):
        d = Dump(f)
        rec = R.records(d).get(INDEX)
        comps = [M.form(d, i) for i in range(1, 40)]
        comps = [(c["id"], c["type"], c["n"], c["away"]) for c in comps if c["in_use"] and c["type"] in (0xC, 0xD)]
        line = (f"{d.at(YEAR, '<i')} {d.at(MONTH, '<i')} {d.at(DAY, '<i')} rec "
                f"{None if rec is None else {k: rec[k] for k in ('state', 'countdown', 'active', 'flags')}} comps {comps}")
        if line != last:
            print(os.path.basename(f), line)
        last = line


def ours_game():
    """Ours: the working city (sim/campaign bigcity, VeryEasy) with the record injected as savimport reads one."""
    import build_scenario
    from sim.campaign import flow
    g = flow.start("bigcity", seed=1, difficulty="VeryEasy")
    flow.briefed(g)
    r = record()
    d = build_scenario.record(r, 99, remap=False)
    for k in ("item", "amount", "year", "city", "city2"):
        d[k] = d["groups"][k][0]
    d.update(countdown=2, state=0, active=1, b33=0, parent=-1, b61=r[0x61], b62=r[0x62], b63=r[0x63], src=-1,
             pitem=0, pamount=0, b74=0)
    from sim import scenario
    ev = scenario.blank(INDEX)
    ev.update(d)
    ev["id"] = INDEX
    evs = g.scenario.events
    while len(evs) < INDEX:
        evs.append(scenario.blank(len(evs)))
    evs[INDEX:INDEX + 1] = [ev]
    return g, ev


def ours(dispatch=True):
    from sim.empire import requests, war
    from sim.systems import military
    g, ev = ours_game()
    mon = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    seen = len(g.city.messages)
    for _ in range(8):
        g.step(mon - g.tick % mon if g.tick % mon else mon)
        for _, m in g.city.messages[seen:]:
            print("   msg:", str(m)[:110])
        seen = len(g.city.messages)
        comps = military.companies(g)
        print(g.date(), {k: ev.get(k) for k in ("state", "countdown", "active", "flags")},
              [(k, c["type"], c["members"], c.get("away")) for k, c in comps.items() if c["type"] != "rabble"])
        if dispatch and ev["state"] == 0 and ev.get("active") and requests.can_fulfil(g, ev) and \
                any("Mantineia" in str(m) for _, m in g.city.messages):
            print("   dispatch:", requests.dispatch(g, ev))
            print("   strength", ev.get("strength"))
    return g, ev


def march_exe():
    """The exe's horsemen per dump: tick -> sorted [(x, y, hidden), count] (logical tiles)."""
    from collections import Counter
    from oracle import Dump, dump_files
    import oracle_military as M
    out = {}
    for f in dump_files(os.path.join(RUNS, "1L5-troopsmarch", "dump")):
        d = Dump(f)
        hs = [x for x in (M.fig(d, i) for i in range(1, 2000)) if x["state"] == 1 and x["type"] == 0xD]
        out[int(os.path.basename(f)[5:11])] = sorted(Counter((x["x"], x["y"], x["hidden"]) for x in hs).items())
    return out


def march_ours(ticks, t0):
    """Ours dispatched at exe tick t0 (the army dialog's confirm): the same samples; the companies abroad count as
    hidden on the exit tile (the exe keeps them there, action 0xF)."""
    from collections import Counter
    from sim.empire import requests
    from sim.systems import military
    g, ev = ours_game()
    mon = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    g.step(mon - g.tick % mon)
    requests.dispatch(g, ev)
    o, ex = g.world.origin, g.world.exit
    out, now = {}, t0
    for t in ticks:
        if t < t0:
            continue
        g.step(t - now)
        now = t
        c = Counter((w.x - o[0], w.y - o[1], 0) for w in g.walkers.values() if w.role == "horseman")
        gone = sum(k["members"] for k in military.companies(g).values() if k["type"] == "horseman") - sum(c.values())
        if gone:
            c[(ex[0] - o[0], ex[1] - o[1], 1)] += gone
        out[t] = sorted(c.items())
    return out


def march(t0=None):
    exe_ = march_exe()
    ticks = sorted(exe_)
    if t0 is None:                       # the confirm click lands between the shots at ticks 31 and 33
        t0 = min(range(30, 40), key=lambda k: sum(a != b for t, a in march_ours(ticks, k).items()
                                                  for b in [exe_[t]]))
    ours_ = march_ours(ticks, t0)
    same = 0
    for t in ticks:
        if t in ours_:
            same += exe_[t] == ours_[t]
            print(t, "=" if exe_[t] == ours_[t] else "x", "exe", exe_[t])
            if exe_[t] != ours_[t]:
                print("        ours", ours_[t])
    print(f"dispatch at exe tick {t0}: {same} of {len(ours_)} samples equal")
    return same, len(ours_)


if __name__ == "__main__":
    op = sys.argv[1]
    if op == "run":
        run(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    elif op == "exe":
        exe()
    elif op == "ours":
        ours()
    elif op == "march":
        march(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif op == "pokes":
        print(pokes(1))
