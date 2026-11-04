"""Profile a running live server: every tab request (cProfile per request, merged) and the save loop's saves.

  python3 tools/profile_live.py SAVE_COPY --port 8797 --secs 60 [--top 40] [live options...]

Runs `python3 -m sim live SAVE_COPY ...` in this process for --secs, then prints: the process CPU time, requests
and CPU per path, gzip totals, the 5 s autosave's time, and the top functions of every thread (one cProfile: since
Python 3.12 it watches all threads and only one may run; own time and cumulative). A synced tab's frames.json poll advances the sim (Runner.advance), so the sim and the frame recording
are inside the requests too. Drive it meanwhile with a tab, e.g.
  node tools/speed_check.mjs http://127.0.0.1:8797/play.html --rates 15 --secs 40
Never on the user's game: use a copy of the save and your own port. (A stack sampler was tried first: the GIL
biases it to calls that release it, gzip and socket writes, and hides Python work.)
"""
import collections
import cProfile
import os
import pstats
import resource
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    a = sys.argv[1:]
    def opt(k, d):
        if k in a:
            i = a.index(k)
            v = a[i + 1]
            del a[i:i + 2]
            return v
        return d
    secs, top = float(opt("--secs", 60)), int(opt("--top", 40))
    lock = threading.Lock()
    stats = [None]
    per = collections.defaultdict(lambda: [0, 0.0])          # path -> [requests, thread CPU s]
    gz, saves = [0, 0, 0, 0.0], [0, 0.0]

    import gzip
    import http.server
    _one = http.server.BaseHTTPRequestHandler.handle_one_request
    def handle_one_request(self):
        c0 = time.thread_time()
        try:
            return _one(self)
        finally:
            dt = time.thread_time() - c0
            path = (getattr(self, "path", "") or "?").split("?")[0]
            if path.startswith("/play/") or path.startswith("/data/"):
                path = path.rsplit("/", 1)[0] + "/*"
            with lock:
                per[path][0] += 1
                per[path][1] += dt
    http.server.BaseHTTPRequestHandler.handle_one_request = handle_one_request
    _gz = gzip.compress
    def compress(data, *aa, **kw):
        t = time.thread_time()
        z = _gz(data, *aa, **kw)
        with lock:
            gz[0] += 1; gz[1] += len(data); gz[2] += len(z); gz[3] += time.thread_time() - t
        return z
    gzip.compress = compress
    from sim.game import Game
    _save = Game.save
    def save(self, *aa, **kw):
        t = time.thread_time()
        try:
            return _save(self, *aa, **kw)
        finally:
            saves[0] += 1; saves[1] += time.thread_time() - t
    Game.save = save

    pr = cProfile.Profile()

    def report():
        pr.enable()
        r0 = resource.getrusage(resource.RUSAGE_SELF)
        c0, t0 = r0.ru_utime + r0.ru_stime, time.time()
        time.sleep(secs)
        r1 = resource.getrusage(resource.RUSAGE_SELF)
        cpu, wall = r1.ru_utime + r1.ru_stime - c0, time.time() - t0
        pr.disable()
        stats[0] = pstats.Stats(pr)
        with lock:
            print(f"\nprocess CPU {cpu:.2f} s over {wall:.0f} s = {100 * cpu / wall:.1f}% of a core (profiler included)")
            print(f"autosaves: {saves[0]}, {saves[1]:.2f} s CPU")
            print(f"gzip: {gz[0]} calls, {gz[1] / 1e6:.1f} MB -> {gz[2] / 1e6:.1f} MB, {gz[3]:.2f} s CPU")
            print("requests (count, CPU s):")
            for p, (n, t) in sorted(per.items(), key=lambda kv: -kv[1][1])[:15]:
                print(f"  {p:28s} {n:6d} {t:7.2f}  ({1000 * t / n:.2f} ms each)")
            if stats[0] is not None:
                s = stats[0]
                s.sort_stats("tottime").print_stats(top)
                s.sort_stats("cumulative").print_stats(top)
        sys.stdout.flush()
        os._exit(0)

    threading.Thread(target=report, daemon=True).start()
    from sim.__main__ import main as sim_main
    sim_main(["live", *a])


if __name__ == "__main__":
    main()
