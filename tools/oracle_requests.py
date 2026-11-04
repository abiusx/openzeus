"""Scenario requests (type 1) and invasions (type 2) in the exe against ours (track 1L-5, docs/logic/events.md
"Requests and invasions: oracle").

@Athens through the Ages, episode 0 (Mortal = our Easy) schedules an invasion by Knossos in Jun 800 BC (record 0, lead
1, point 8), a request by Knossos for 100 drachmas in Aug 799 BC (record 13, lead 1; Knossos makes Athens pay tribute,
so the invasion uses the "last chance" phrases), a request by Thermopylai for food (record 3, inactive city: nothing)
and a recurring invasion in Dec 798 BC (record 12, lead 0). The exe is started through its menus (as
tools/campaign_chain.py) and left alone (a right click every 15 s closes the message, a shot just before each; a
click on Bribe (300,573) 7 s later answers an invasion's dialog: an empty city cannot fight; then Decline (495,575)
for a tribute or gift offer: Accept's place opens the help in an ordinary message), dumps every 2 days.

    python3 tools/oracle_requests.py scenario    # write re/oracle/scenarios/1L5-requests.txt
    python3 tools/oracle_requests.py run         # the run -> re/oracle/runs/1L5-requests (docs/re/oracle.md "Run")
    python3 tools/oracle_requests.py check       # the type-1/2 records month by month: exe vs ours
    python3 tools/oracle_requests.py buttons     # run re/oracle/runs/1L5-reqbtn: the same run up to Knossos' request
                                                 # message (Aug 798 BC), then its buttons, the world map's request
                                                 # dialog and its confirm (play-mode pixel checks, docs/play/world.md "Requests")
    ORQ_AID=hercules_labors ORQ_NAME=1L5-troops python3 tools/oracle_requests.py run|check
                                                 # Hercules' Labors ep 0: the calls for troops (records 2, 5)
    python3 tools/oracle_requests.py troops      # run re/oracle/runs/1L5-troopsbtn: the world map, Cyme, its
                                                 # requests, the troops row -> the army dialog, Dispatch (5:0xC)
    ORQ_... python3 tools/oracle_requests.py save OUT [TICK]   # ours at that point (ORQ_TREASURY: drachmas)

check: for every type-1 and type-2 record, its state (+0x30), countdown (+0x2E), active (+0x32), flags (+0x28) and
warnings (+0x57) at the first dump of each month (after the month change), against ours at the same date (ours: a new
game of the same adventure, seed 1, stepped month by month; the RNG-resolved fields come from the exe's own records
where they differ: amount, year). The run's own clicks are mirrored: a request it refused in its message (flag
0x40000, wm_sub_475B50) is refused in ours at the start of that month (requests.refuse); ours never bribes (the run's
Bribe click lands only now and then: its city stays occupied).
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
NAME = os.environ.get("ORQ_NAME", "1L5-requests")            # another adventure's episode 0: ORQ_AID, ORQ_NAME,
AID = os.environ.get("ORQ_AID", "athens_through_the_ages")     # ORQ_SECS (1L5-troops: hercules_labors, bugs 364..)
SECS = int(os.environ.get("ORQ_SECS", 4000))
EVENTS = 0x009173F4          # g_events, 124-byte records (count at 0x009173F0)
YEAR, MONTH = 0x0091EC04, 0x0091EC08


def script():
    from campaign_chain import LIST, MENU
    i = LIST.index(AID)
    t = [MENU, "26:move 590,260", "26.5:click 590,260", f"30:move 120,{162 + 16 * i}", f"30.5:click 120,{162 + 16 * i}",
         "33:move 315,442", "33.5:click 315,442", "75:move 656,491", "75.5:click 656,491", "79:rclick 300,300"]
    k = 0
    for s in range(90, SECS, 15):                  # a shot, close the message; an invasion's dialog: Bribe
        t += [f"{s - 0.5}:shot DIR/m{k:03d}.bmp", f"{s}:rclick 300,300", f"{s + 7}:move 300,573",
              f"{s + 7.2}:click 300,573", f"{s + 7.4}:move 495,575", f"{s + 7.6}:click 495,575"]
        k += 1
    head = (f"# 1L-5 (tools/oracle_requests.py): {AID} episode 0, Mortal, left alone; --seconds {SECS}, "
            "ZEUS_STATE_DUMP_EVERY=102\n")
    return head + "; ".join(t) + "\n"


# 1L5-reqbtn: the 1L5-requests script up to its shot m089 (tick 26112, Thermopylai's message) and the right click
# after it; Knossos' request for 100 drachmas pops up next (in 1L5-requests the Bribe / Decline clicks at 1432 hit its
# Postpone? no: its Refuse, flag 0x40000 at tick 26214) (its announcement, buttons 0x1C0: the treasury covers it). Then: shots of the message,
# Dispatch hovered, Postpone, the world map (panel button (761, 578)), Knossos (KNOSSOS, found on wm.bmp), its
# 'requests by' dialog (side panel widget 4), the row hovered, the row's confirm 5:6/5:7, OK hovered, OK.
BTN = "1L5-reqbtn"
KNOSSOS = (372, 535)       # its marker on wm.bmp (800 x 600)


def script_buttons(stage=2):
    base = script().split("\n")[1].split("; ")
    keep = []
    for t in base:
        at = float(t.split(":")[0])
        if at > 1425:
            break
        keep.append(t)
    keep = [x for x in keep if "shot DIR/m" not in x]        # the base run's shots: not needed here
    t = keep + ["1426:shot DIR/rq_msg.bmp", "1427:move 98,577", "1427.5:shot DIR/rq_hover.bmp",
                "1428:move 276,577", "1428.2:click 276,577", "1429:shot DIR/after_pp.bmp", "1429.5:rclick 300,300",
                "1430:move 761,578", "1430.2:down 761,578", "1430.5:up 761,578", "1432:shot DIR/wm.bmp"]
    if stage >= 2 and KNOSSOS[0] is not None:
        kx, ky = KNOSSOS
        t += [f"1433:move {kx},{ky}", f"1433.3:down {kx},{ky}", f"1433.6:up {kx},{ky}", "1435:shot DIR/wm_knossos.bmp",
              "1436:move RQX,RQY", "1436.3:down RQX,RQY", "1436.6:up RQX,RQY", "1438:shot DIR/wm_requests.bmp",
              "1439:move ROWX,ROWY", "1440:shot DIR/wm_row_hover.bmp", "1440.3:down ROWX,ROWY", "1440.6:up ROWX,ROWY",
              "1442:shot DIR/wm_confirm.bmp", "1443:move OKX,OKY", "1444:shot DIR/wm_confirm_ok.bmp",
              "1444.3:down OKX,OKY", "1444.6:up OKX,OKY", "1446:shot DIR/wm_after.bmp"]
    return "# 1L-5 request buttons (tools/oracle_requests.py buttons)\n" + "; ".join(t) + "\n"


def run_buttons():
    out = os.path.join(RUNS, BTN)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "write"), exist_ok=True)
    line = script_buttons().split("\n")[1]
    for k, v in BTN_POS.items():
        line = line.replace(k, str(v))
    open(os.path.join(SC, BTN + ".txt"), "w").write(script_buttons())
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(out, "dump"), ZEUS_STATE_DUMP_EVERY="102",
               ZEUS_STATE_DUMP_FROM="26112", ZEUS_STATE_DUMP_TO="26500")
    os.makedirs(os.path.join(out, "dump"), exist_ok=True)
    cmd = [os.path.join(ROOT, "refs/zeus-poseidon-arm64/build/zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original/app/Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(out, "write"), "--seconds", "1450", "--state-log",
           os.path.join(out, "state.txt"), "--screenshot", os.path.join(out, "end.bmp"), "--script",
           line.replace("DIR", out)]
    with open(os.path.join(out, "run.log"), "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), out], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), "--shots", out], cwd=ROOT)


# 800 x 600: side panel widget 4 at (614 + 95, 485) (1F-wmdlg1's (933, 485) at 1024); mode 5 at ((630 - 496) / 2,
# (600 - 416) / 2) = (67, 92), row 0 (x + 38, y + 96) 400 x 40; the 0x3F popup at (160, 140), OK (+256, +100) 34 x 34
BTN_POS = {"RQX": 709, "RQY": 485, "ROWX": 305, "ROWY": 208, "OKX": 433, "OKY": 257}


# 1L5-troopsbtn (Hercules' Labors episode 0, ORQ_AID=hercules_labors ORQ_NAME=1L5-troops): the run up to Cyme's
# request for troops (record 2, its message at tick 1632, shot m007 at 194.5 s) and the right click after it, then the
# world map, Cyme (CYME, found on wm.bmp), its 'requests by' dialog, the row hovered, the row's army dialog (a request
# for troops: 283:3, no companies), its Dispatch (the 0xE popup: no companies) and OK.
TBTN = "1L5-troopsbtn"
CYME = (487, 215)       # its marker on wm.bmp (800 x 600)


def script_troops():
    base = script().split("\n")[1].split("; ")
    keep = [t for t in base if float(t.split(":")[0]) <= 195.5 and "shot DIR/m" not in t]
    t = keep + ["196:move 761,578", "196.2:down 761,578", "196.5:up 761,578", "198:shot DIR/wm.bmp"]
    if CYME[0] is not None:
        cx, cy = CYME
        t += [f"199:move {cx},{cy}", f"199.3:down {cx},{cy}", f"199.6:up {cx},{cy}", "201:shot DIR/wm_cyme.bmp",
              "202:move RQX,RQY", "202.3:down RQX,RQY", "202.6:up RQX,RQY", "204:shot DIR/wm_requests.bmp",
              "205:move ROWX,ROWY", "206:shot DIR/wm_row_hover.bmp", "206.3:down ROWX,ROWY", "206.6:up ROWX,ROWY",
              "208:shot DIR/army.bmp"]
        if TBTN_POS["DSX"]:
            t += ["209:move DSX,DSY", "210:shot DIR/army_hover.bmp", "210.3:down DSX,DSY", "210.6:up DSX,DSY",
                  "212:shot DIR/army_dispatch.bmp", "213:rclick 300,300", "215:shot DIR/after.bmp"]
    return "# 1L-5 troops request buttons (tools/oracle_requests.py troops)\n" + "; ".join(t) + "\n"


def run_troops():
    out = os.path.join(RUNS, TBTN)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "write"), exist_ok=True)
    line = script_troops().split("\n")[1]
    for k, v in list(BTN_POS.items()) + list(TBTN_POS.items()):
        line = line.replace(k, str(v))
    open(os.path.join(SC, TBTN + ".txt"), "w").write(script_troops())
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(out, "dump"), ZEUS_STATE_DUMP_EVERY="10",
               ZEUS_STATE_DUMP_FROM="1600", ZEUS_STATE_DUMP_TO="1700")
    os.makedirs(os.path.join(out, "dump"), exist_ok=True)
    cmd = [os.path.join(ROOT, "refs/zeus-poseidon-arm64/build/zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original/app/Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(out, "write"), "--seconds", "218", "--state-log",
           os.path.join(out, "state.txt"), "--screenshot", os.path.join(out, "end.bmp"), "--script",
           line.replace("DIR", out)]
    with open(os.path.join(out, "run.log"), "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), out], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), "--shots", out], cwd=ROOT)


# the army dialog (screen 0x21) at 800 x 600: its Dispatch button (on army.bmp)
TBTN_POS = {"DSX": 553, "DSY": 548}


def write():
    open(os.path.join(SC, NAME + ".txt"), "w").write(script())


def run():
    write()
    out = os.path.join(RUNS, NAME)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "dump"), exist_ok=True)
    os.makedirs(os.path.join(out, "write"), exist_ok=True)
    line = [x for x in open(os.path.join(SC, NAME + ".txt")) if not x.startswith("#")][0].strip()
    env = dict(os.environ, ZEUS_STATE_DUMP=os.path.join(out, "dump"), ZEUS_STATE_DUMP_EVERY="102")
    cmd = [os.path.join(ROOT, "refs/zeus-poseidon-arm64/build/zeus-run"), "--run",
           os.path.join(ROOT, "zeus-original/app/Zeus.exe"), "--headless", "--deterministic",
           "--write-dir", os.path.join(out, "write"), "--seconds", str(SECS), "--state-log",
           os.path.join(out, "state.txt"), "--screenshot", os.path.join(out, "end.bmp"), "--script",
           line.replace("DIR", out)]
    with open(os.path.join(out, "run.log"), "w") as log:
        subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), out], cwd=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tools/oracle_compress.py"), "--shots", out], cwd=ROOT)


def records(d):
    """{index: dict} of the dump's type-1 / type-2 records."""
    n = d.at(EVENTS - 4, "<i")
    out = {}
    for i in range(n):
        a = EVENTS + i * 124
        t = d.at(a + 2, "<B")
        if t not in (1, 2):
            continue
        out[i] = dict(type=t, month=d.at(a + 3, "<B"), item=d.at(a + 4, "<h"), amount=d.at(a + 0xC, "<h"),
                      year=d.at(a + 0x14, "<h"), city=d.at(a + 0x1C, "<h"), flags=d.at(a + 0x28, "<I"),
                      lead=d.at(a + 0x2C, "<h"), countdown=d.at(a + 0x2E, "<h"), state=d.at(a + 0x30, "<h"),
                      active=d.at(a + 0x32, "<B"), enough=d.at(a + 0x33, "<B"), bits=d.at(a + 0x57, "<B"),
                      kind=d.at(a + 0x60, "<B"), city2=d.at(a + 0x58, "<h"))
    return out


def months(run_dir):
    """[(year, month, first dump path of that month)]."""
    from oracle import Dump, dump_files
    out, last = [], None
    for f in dump_files(os.path.join(run_dir, "dump")):
        d = Dump(f)
        ym = (d.at(YEAR, "<i"), d.at(MONTH, "<i"))
        if ym != last and ym[0] != 0:
            out.append((ym[0], ym[1], f))
            last = ym
    return out


FIELDS = ("state", "countdown", "active", "flags", "enough", "bits")


def ours_record(ev):
    return dict(state=ev["state"], countdown=ev["countdown"], active=ev["active"], flags=ev["flags"],
                enough=ev.get("b33", 0), bits=ev.get("warned_bits", 0))


def check():
    from oracle import Dump
    from sim.campaign import flow
    run_dir = os.path.join(RUNS, NAME)
    ms = months(run_dir)
    g = flow.start(AID, seed=1, difficulty="Easy")
    flow.briefed(g)
    first = records(Dump(ms[0][2]))
    for i, r in first.items():                       # the exe's RNG-resolved values (ours draws its own)
        ev = g.scenario.events[i]
        ev.update(amount=r["amount"], year=r["year"], month=r["month"], city=r["city"])
        if r["type"] == 2:
            ev["landing"] = Dump(ms[0][2]).at(EVENTS + i * 124 + 0x78, "<B")
        if r["type"] == 1:
            ev["countdown"] = r["countdown"]
            _sync_rng(ev, Dump(ms[0][2]), i)
    D = g.rules["ticks_per_day"]
    bad = shifted = 0
    seen = 0
    from sim.empire import requests
    for k, (y, m, f) in enumerate(ms[1:]):
        ex = records(Dump(f))
        nxt = records(Dump(ms[k + 2][2])) if k + 2 < len(ms) else {}
        while g.year * 12 + g.month < y * 12 + m:
            g.step(D)
        for msg in g.city.messages[seen:]:
            print(f"   ours msg: {str(msg[1])[:200]}")
        seen = len(g.city.messages)
        for i, r in ex.items():
            if r["flags"] & 0x100:                   # a run-time record (a city's own invasion, flags 0x120 / 0x110):
                ours = [e for e in g.scenario.events if e["type"] == r["type"] and e["flags"] & 0x100
                        and e.get("city2") == r.get("city2") and (e["year"], e["month"]) == (r["year"], r["month"])]
                if not ours:                         # created in another month (the streak city pick, our RNG)
                    near = [e for e in g.scenario.events if e["type"] == r["type"] and e["flags"] & 0x100
                            and e.get("city2") == r.get("city2")]
                    if near:
                        print(f"   ours #{near[-1]['id']} (created {near[-1]['year']}/{near[-1]['month'] + 1}): "
                              + " ".join(f"{k} {v}" for k, v in ours_record(near[-1]).items()))
                o = ours_record(ours[0]) if ours else None    # ours has no type-0x1E records: its index differs
                diff = {k: (r[k], o[k]) for k in FIELDS if r[k] != o[k]} if o else "missing: " + str(
                    [(e["year"], e["month"], e.get("city2"), e["flags"]) for e in g.scenario.events
                     if e["type"] == 2 and e["flags"] & 0x100] + [(r["year"], r["month"], r["city2"])])
                row = " ".join(f"{k} {r[k]}" for k in FIELDS)
                print(f"{y} {m + 1:2d} #{i:<2d} t{r['type']} run-time {row}" + (f"   DIFF ours {diff}" if diff else ""))
                bad += bool(diff) and o is not None          # another month: the streak pick's RNG (counted apart)
                shifted += o is None
                continue
            if i >= len(g.scenario.events):
                continue
            ev = g.scenario.events[i]
            if not ev["active"] and not ev["flags"] & 4 and not r["active"] and not r["flags"] & 4:
                d = Dump(f)                                # re-armed (recurring): the exe's new draws
                new = dict(amount=r["amount"], year=r["year"], city=r["city"])
                if r["type"] == 2:
                    new["landing"] = d.at(EVENTS + i * 124 + 0x78, "<B")
                if any(ev.get(k) != v for k, v in new.items()):
                    print(f"   #{i}: the exe's resolved values {new} (RNG; ours {[ev.get(k) for k in new]})")
                    ev.update(new)
            if ev["state"] != 1:
                ev.pop("grace_synced", None)
            if (r["type"] == 1 and r["state"] == 1 and ev["state"] == 1 and not ev.get("grace_synced")
                    and r["countdown"] != ev["countdown"]):    # the grace months: three draws of the exe's RNG
                print(f"   grace #{i}: exe {r['countdown']}, ours {ev['countdown']} (RNG; ours takes the exe's)")
                ev["countdown"], ev["grace_synced"] = r["countdown"], True
            o = ours_record(ev)
            diff = {k: (r[k], o[k]) for k in FIELDS if r[k] != o[k]}
            row = " ".join(f"{k} {r[k]}" for k in FIELDS)
            print(f"{y} {m + 1:2d} #{i:<2d} t{r['type']} {row}" + (f"   DIFF ours {diff}" if diff else ""))
            bad += bool(diff)
        for i, r in nxt.items():                     # refused by the run's click during the coming month
            ev = g.scenario.events[i] if i < len(g.scenario.events) else None
            if (ev is not None and ev["type"] == 1 and r["flags"] & 0x40000 and not ev["flags"] & 0x40000
                    and requests.is_open(ev)):
                print(f"   ours: request #{i} refused (the run's click): {requests.refuse(g, ev)}")
    print(f"{bad} differences ({shifted} month rows of a city's own invasion created in another month: the city the "
          "streak pass 0x0047ECD0 picks is drawn by each game's own RNG)")
    return bad


def _sync_rng(ev, d, i):
    """The request's other start draws (event_resolve_at_start): +0x61 (rng % 5 + 4: the warning month, the travel
    time phrase) and +0x62 from the exe's record."""
    a = EVENTS + i * 124
    ev["b61"], ev["b62"] = d.at(a + 0x61, "<B"), d.at(a + 0x62, "<B")


def save(out, tick=26112):
    """Our game of the same adventure at `tick` (the records synced to the exe's values as in check, the run's refuse
    click left out): Knossos' request #13 announced with its buttons at the month change of tick 26112 (Aug 798 BC).
    For the play-mode checks against 1L5-reqbtn (docs/play/world.md "Requests")."""
    from oracle import Dump
    from sim.campaign import flow
    from sim import savefile, messages
    messages.PLAYER = "N"                            # the run's player name (campaign_chain: char 78)
    ms = months(os.path.join(RUNS, NAME))
    g = flow.start(AID, seed=1, difficulty="Easy")
    flow.briefed(g)
    first = records(Dump(ms[0][2]))
    for i, r in first.items():
        ev = g.scenario.events[i]
        ev.update(amount=r["amount"], year=r["year"], month=r["month"], city=r["city"])
        if r["type"] == 1:
            ev["countdown"] = r["countdown"]
            _sync_rng(ev, Dump(ms[0][2]), i)
    D = g.rules["ticks_per_day"]
    while g.tick < tick:
        g.step(min(D, tick - g.tick))
    g.city.treasury = int(os.environ.get("ORQ_TREASURY", 15000))   # the exe's (Mortal start, nothing built)
    with open(out, "wb") as f:
        savefile.write(g, f)
    print(out, g.date(), [(t, str(m)[:60]) for t, m in g.city.messages[-4:]])


if __name__ == "__main__":
    if sys.argv[1] == "save":
        save(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 26112)
    else:
        {"scenario": write, "run": run, "check": check, "buttons": run_buttons, "troops": run_troops}[sys.argv[1]]()
