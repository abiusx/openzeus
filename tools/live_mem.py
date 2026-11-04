"""Memory of the live server's recording (sim/live.py Runner) over a long run, without HTTP or a browser
(docs/sim-design.md "Performance", "Live recording memory").

Runs a Runner on a save (use a COPY: nothing is saved) as the live loop does (advance + compact), with a game clock
standing in for the wall clock (tick / speed seconds), so snapshots taken by wall time (STATE_WALL) come as often as in
a real session at that speed. Prints, every --every months: the recorded frames, building snapshots and terrains
(count, bytes held) and the process RSS.

  python3 tools/live_mem.py COPY.pkl --months 48 --speed 30 [--every 6]
"""
import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def rss_mb():
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout
    return int(out.strip() or 0) / 1024


def held(entries, cols):
    """(count, bytes) of the byte strings in the given tuple columns (compressed ("z", bytes) counted as stored)."""
    n = 0
    for e in entries:
        for c in cols:
            d = e[c]
            if isinstance(d, tuple):
                d = d[1]
            if d is not None:
                n += len(d)
    return len(entries), n


def report(r, t0):
    f = held(r.frames, (1, 4))
    s = held(r.states, (1, 4))
    tn = len(r.terrains)
    tb = sum(len(t[1]) if not isinstance(t[1], tuple) else len(t[1][1]) for t in r.terrains)
    print(f"{r.g.date():>12}  tick {r.g.tick:>8}  frames {f[0]:>6} {f[1] / 1e6:7.1f} MB  states {s[0]:>5} "
          f"{s[1] / 1e6:7.1f} MB  terrains {tn:>4} {tb / 1e6:6.1f} MB  total {(f[1] + s[1] + tb) / 1e6:7.1f} MB  "
          f"rss {rss_mb():7.0f} MB  ({time.perf_counter() - t0:.0f} s)", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("save")
    ap.add_argument("--months", type=int, default=48)
    ap.add_argument("--speed", type=int, default=30, help="the live rate (ticks/s): sets the frame interval")
    ap.add_argument("--every", type=int, default=6, help="report every N months")
    a = ap.parse_args()
    from sim import live
    from sim.game import Game
    g = Game.load(a.save)
    clock = {"t": 0.0}

    class GameClock:                           # live.py reads time.time() for STATE_WALL and the save timer
        sleep = staticmethod(time.sleep)

        @staticmethod
        def time():
            return clock["t"]
    live.time = GameClock
    r = live.Runner(g, save=None, script=None, speed=a.speed)
    r.rate, r.paused = a.speed, False
    month = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    end = g.tick + a.months * month
    t0 = time.perf_counter()
    report(r, t0)
    nxt = g.tick + a.every * month
    while g.tick < end:
        step = max(1, a.speed // 2)            # the live loop runs ~every 10 ms; half a second of game a call is plenty
        r.advance(min(end, g.tick + step))
        clock["t"] = g.tick / a.speed
        r.compact()
        if g.tick >= nxt:
            report(r, t0)
            nxt += a.every * month
    check(r)


def check(r):
    """The recording still answers every query: frames (both protocols) and snapshots across the whole timeline
    parse as JSON, ticks ascending."""
    import json
    t0, t1 = r.frame_ticks[0], r.g.tick
    assert r.frame_ticks == sorted(r.frame_ticks) and r.state_ticks == sorted(r.state_ticks)
    assert [f[0] for f in r.frames] == r.frame_ticks and [s[0] for s in r.states] == r.state_ticks
    n = 0
    for k in range(41):
        t = t0 + (t1 - t0) * k // 40
        fr = json.loads(r.frames_range(t, t + 120))
        json.loads(r.frames_range(t, t + 120, v2=True, base=None))
        assert fr and fr[0]["tick"] <= max(t, t0)
        f0, f1 = r.frames_at(t)
        json.loads(f0), json.loads(f1)
        st = json.loads(r.state_at(t))
        json.loads(r.state_lite(t))
        assert st["state_tick"] <= max(t, r.state_ticks[0]) and len(st["terrain"]) == 228 * 228
        n += 1
    print(f"check: {n} ticks queried over {t0}..{t1}: frames, frames v2, frame pairs, snapshots, terrains parse")


if __name__ == "__main__":
    main()
