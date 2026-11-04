"""Profile the simulation on a save: where the time per tick goes.

  python3 tools/profile_sim.py SAVE [--ticks 3060] [--warm 510] [--live] [--rate 15] [--top 40] [--out FILE.prof]

Loads SAVE (never writes it back; use a copy of a running game's save), runs --warm ticks unprofiled (caches,
first-day work), then --ticks ticks under cProfile and prints ticks/s plus the top functions by own time and by
cumulative time. 3060 ticks = 60 game days = ~3.75 months, so every monthly pass is in.
--live: drive a sim.live Runner (no HTTP) the way a synced tab does, so the live server's per-tick recording
(record_frame every frame_every() ticks, record_state snapshots) is profiled too; --rate sets its speed
(15 = 1x, which decides how often frames are recorded). A campaign city on its "complete" screen is set to keep
building (as {"op": "stay"}) so it runs.
"""
import argparse
import cProfile
import os
import pstats
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.game import Game  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("--ticks", type=int, default=3060)
    ap.add_argument("--warm", type=int, default=510)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--rate", type=int, default=15)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    g = Game.load(a.save)
    st = g.__dict__.get("campaign")
    if st and st.get("done"):
        from sim.campaign import flow
        flow.continue_building(g)
    if a.live:
        from sim import live
        r = live.Runner(g, speed=a.rate)
        r.set_speed(rate=a.rate, paused=False)
        step = lambda n: r.advance(g.tick + n)  # noqa: E731
    else:
        step = g.step
    step(a.warm)
    print(f"{g.date()}, tick {g.tick}, walkers {len(getattr(g, 'walkers', []) or [])}, "
          f"buildings {len(getattr(g, 'buildings', []) or [])}")
    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    done = 0
    while done < a.ticks:                       # in chunks: Runner.advance stops at its CHUNK budget
        t = g.tick
        step(min(255, a.ticks - done))
        done += max(1, g.tick - t)
    pr.disable()
    dt = time.perf_counter() - t0
    # unprofiled rate on the same city: profiling inflates call-heavy code, so the shares are only a guide
    t1 = time.perf_counter()
    step(510)
    raw = 510 / (time.perf_counter() - t1)
    print(f"{done} ticks profiled in {dt:.1f}s ({done / dt:.0f} ticks/s under the profiler); unprofiled {raw:.0f} ticks/s")
    if a.out:
        pr.dump_stats(a.out)
    s = pstats.Stats(pr)
    s.sort_stats("tottime").print_stats(a.top)
    s.sort_stats("cumulative").print_stats(a.top)


if __name__ == "__main__":
    main()
