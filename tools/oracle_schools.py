"""Which schools feed which venues in the exe? (TODO "Schools vs venues on the oracle"; docs/logic/services.md 3.1)

"See a working city" has 3 drama schools (buildings 54, 433, 567), 2 theatres (38, 568), 2 colleges (432, 569) and
1 podium (570) on one road network. Run A: as is. Run B: theatre 568's shows (Building +0xA9) poked to 32 every
25 ticks, so the venue finder 0x00491630 (accepts shows <= 24) never picks it: 3 schools, 1 theatre.

    python3 tools/oracle_schools.py --script > re/oracle/scenarios/schools-venues.txt
    python3 tools/oracle_schools.py --poke > re/oracle/scenarios/schools-venues.poke     (run B only)
    O=re/oracle/runs/schools-A; mkdir -p $O/dump            # B: also ZEUS_POKE=$PWD/re/oracle/scenarios/schools-venues.poke
    ZEUS_STATE_DUMP=$PWD/$O/dump ZEUS_STATE_DUMP_EVERY=25 \
      refs/zeus-poseidon-arm64/build/zeus-run --run zeus-original/app/Zeus.exe --headless --deterministic \
      --write-dir $O/write --seconds 3000 --state-log /dev/null \
      --script "$(grep -v '^#' re/oracle/scenarios/schools-venues.txt)" > $O/run.log 2>&1
    python3 tools/oracle_compress.py $O
    python3 tools/oracle_schools.py --check re/oracle/runs/schools-A
    python3 tools/oracle_schools.py --sim re/oracle/runs/schools-A     # the same in ours (B: blocks theatre 568 too)

Per-tick timing of one trainee (school 54 -> theatre 38, 21 road tiles): the same run with ZEUS_STATE_DUMP_EVERY=1
and ZEUS_STATE_DUMP_FROM=355 ZEUS_STATE_DUMP_TO=380 (runs/schools-A-tick1), 670..700 (schools-A-tick2), --seconds 500:
spawned in tick 368 (step 31), action 7 at 369 (finder), walks from 370 (the shows decrement, step 33, also in 370),
enters a tile at sub-step 8, arrives at the 21st tile's centre in tick 685 = 368 + 2 + 15 * 21, after the day's
decrement in 676, so the theatre keeps 32 that day.

--sim loads Adventures/tutorial15.sav (the same city) into ours (sim/savimport.py; ids + origin (44, 44)), sets the
venues' shows and the schools' spawn timers (+0x32) from the run's tick-0 dump, pins every school's and venue's
employees to the run's dumps (our labour allocation differs a little), runs 4,600 ticks and prints each school's
trainee departures (ticks after the load) and venues: compare with --check (the exe's are seen up to 25 ticks late).

--check prints, per dump interval, the trainees seen walking (figure +0x0A type 0x12 actor / 0x10 philosopher,
action +0x38 = 8, school = +0x5A building_id, venue = +0x5E, set by the handler 0x004B4370 from the finder), every school's walkers out (Building +0xA8: +1 at each
spawn by buildings_spawn_walkers 0x0048CFB0, -1 when the figure is deleted) and every venue's shows (+0xA9; a jump up = an arrival,
0x00491EF0 sets it to 32).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402
from oracle import Dump  # noqa: E402

FIG, FSZ = 0x00DBD788, 0x184
BLD, BSZ = 0x0092E658, 0x118
SCHOOLS = {54: "drama", 433: "drama", 567: "drama", 432: "college", 569: "college"}
VENUES = {38: "theatre", 568: "theatre", 570: "podium"}
BLOCKED = 568
PRE = "5:key 27; 12:click 220,101; 17:char 78; 20:click 556,320; 27:click 644,523; 33:click 588,476; 45:rclick 300,300"


def script():
    print("# tools/oracle_schools.py --script: \"See a working city\" (as working-city.txt), messages dismissed every 30 s;")
    print("# --seconds 3000 (~4,600 ticks); see the tool's docstring for the run lines.")
    print(PRE + "".join(f"; {t}:click 568,574" for t in range(60, 3000, 30)))


def poke():
    print(f"# tools/oracle_schools.py --poke: theatre {BLOCKED} shows (+0xA9) = 32 every 25 ticks (never accepts a trainee)")
    for t in range(1, 6000, 25):
        print(f"{t} {BLD + BLOCKED * BSZ + 0xA9:x} 1 32")


def check(run):
    files = oracle.dump_files(os.path.join(run, "dump"))
    prev = None
    walking = set()                # (figure, school) in action 8 at the previous dump
    trips = []                     # (school, venue, tick first seen walking)
    arrivals = {v: 0 for v in VENUES}
    first = last = None
    for f in files:
        d = Dump(f)
        t = int(os.path.basename(f)[5:11])
        a8 = {b: d.at(BLD + b * BSZ + 0xA8, '<B') for b in SCHOOLS}
        a9 = {v: d.at(BLD + v * BSZ + 0xA9, '<B') for v in VENUES}
        now = set()
        for i in range(1, 4000):
            a = FIG + i * FSZ
            try:
                st = d.at(a + 0x0E, '<B')
            except KeyError:
                break
            if st != 1 or d.at(a + 0x0A, '<B') not in (0x10, 0x12):
                continue
            act, home, ven = d.at(a + 0x38, '<B'), d.at(a + 0x5A, '<h'), d.at(a + 0x5E, '<h')
            if home in SCHOOLS and act == 8:
                now.add((i, home))
                if (i, home) not in walking:
                    trips.append((home, ven, t))
        walking = now
        if prev:
            for v in VENUES:
                if a9[v] > prev[1][v]:
                    arrivals[v] += 1
        if first is None:
            first = (t, a8)
        last = (t, a8)
        prev = (a8, a9)
        if t % 400 == 0:
            print(t, "out", a8, "shows", a9)
    print(f"ticks {first[0]}..{last[0]}")
    for b, k in SCHOOLS.items():
        walked = [(v, t) for h, v, t in trips if h == b]
        print(f"school {b} {k}: trainees seen walking {len(walked)}: "
              + " ".join(f"{t}->{v}" for v, t in walked))
    print("venue arrivals (shows jumped up):", arrivals)


def sim(run):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sim import savimport
    from sim.systems import labor, services
    g = savimport.load(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    "zeus-original/app/Adventures/tutorial15.sav"))
    ox, oy = g.world.origin
    ours = {}
    for b in g.buildings.values():
        ours[(b.key, b.x - ox, b.y - oy)] = b
    d0 = Dump(oracle.dump_files(os.path.join(run, "dump"))[0])
    emap = {}
    for e in list(SCHOOLS) + list(VENUES):
        a = BLD + e * BSZ
        x, y = d0.at(a + 6, '<h'), d0.at(a + 8, '<h')
        b = next(b for (k, bx, by), b in ours.items() if (bx, by) == (x, y))
        emap[e] = b
        if e in VENUES:
            b.misc["shows"] = d0.at(a + 0xA9, '<B')
        b.spawn_timer = d0.at(a + 0x32, '<B')
    emp = {}
    for f in oracle.dump_files(os.path.join(run, "dump")):
        d = Dump(f)
        emp[int(os.path.basename(f)[5:11])] = {e: d.at(BLD + e * BSZ + 0x40, '<B') for e in emap}
    blocked = os.path.basename(run.rstrip("/")).endswith("B")
    t0 = g.tick
    orig_alloc, orig_send = labor.allocate, services.send_trainee

    def alloc(g):
        orig_alloc(g)
        for e, n in emp[min(max(emp), (g.tick - t0) // 25 * 25)].items():
            emap[e].employees = n
    rev = {b.id: e for e, b in emap.items()}
    trips = []

    def send(g, b, trainee, venue):
        before = set(g.walkers)
        orig_send(g, b, trainee, venue)
        for w in set(g.walkers) - before:
            trips.append((rev.get(b.id), rev.get(g.walkers[w].target), g.tick - t0))
    labor.allocate, services.send_trainee = alloc, send
    alloc(g)
    while g.tick - t0 < 4600:
        if blocked:
            emap[BLOCKED].misc["shows"] = 32
        g.step(1)
    for b, k in SCHOOLS.items():
        walked = [(v, t) for h, v, t in trips if h == b]
        print(f"school {b} {k}: trainees {len(walked)}: " + " ".join(f"{t}->{v}" for v, t in walked))


if __name__ == "__main__":
    if sys.argv[1] == "--script":
        script()
    elif sys.argv[1] == "--poke":
        poke()
    elif sys.argv[1] == "--sim":
        for r in sys.argv[2:]:
            print("== ours", r)
            sim(r)
    else:
        for r in sys.argv[2:]:
            print("==", r)
            check(r)
