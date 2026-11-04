"""Replay a save's command log (Game.log: (tick, command) of every command that took effect) from a new game with
the save's map, seed and difficulty, to inspect any tick of a played game (playtest triage 10-30, bugs.md 270..279).

  python3 tools/replay_log.py SAVE [--save-at TICK ... --out DIR] [--every N --show agora,granary,house]

--save-at writes DIR/tTICK.pkl at those ticks (and DIR/end.pkl at the save's tick). --every N prints, every N ticks,
the buildings whose key contains one of the --show words (id, key, x, y, goods, employees, level, reason).
At the end it compares the replay (after a save/load round trip) with the save part by part (tools/state_hash.py's
hashes); "identical" means the log reproduces the game (with the code that played it: message texts count too). Work on a COPY of a save; the save itself is only read.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import state_hash  # noqa: E402  (first: it re-runs this script with PYTHONHASHSEED=0, so string sets order alike)
from sim.game import Game  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("save")
    ap.add_argument("--save-at", type=int, nargs="*", default=[])
    ap.add_argument("--out", default=None)
    ap.add_argument("--every", type=int, default=0)
    ap.add_argument("--show", default="")
    a = ap.parse_args()
    src = Game.load(a.save)
    g = Game(src.map_name, src.seed, difficulty=src.difficulty)
    log, i = list(src.log), 0
    stops = set(a.save_at)
    show = [w for w in a.show.split(",") if w]
    if stops or a.out:
        os.makedirs(a.out or ".", exist_ok=True)
    while g.tick < src.tick:
        while i < len(log) and log[i][0] == g.tick:
            g.command(log[i][1])
            i += 1
        g.step(1)
        if g.tick in stops:
            g.save(os.path.join(a.out or ".", f"t{g.tick}.pkl"))
        if a.every and g.tick % a.every == 0 and show:
            print(g.tick, g.date())
            for b in g.buildings.values():
                if any(w in b.key for w in show):
                    print(f"  #{b.id} {b.key} ({b.x},{b.y}) goods {dict(b.goods)} emp {b.employees} level {b.level}"
                          f" {b.reason}")
    import tempfile
    end = os.path.join(a.out, "end.pkl") if a.out else os.path.join(tempfile.mkdtemp(), "end.pkl")
    g.save(end)                     # compared after a save/load round trip, as the save itself (load migrations)
    pa, pb = state_hash.hashes(src)[1], state_hash.hashes(Game.load(end))[1]
    diff = [k for k in pa if pa[k] != pb.get(k)]
    print(f"replayed {len(log)} commands to tick {g.tick}: " + ("identical" if not diff else f"differs in {diff}"))


if __name__ == "__main__":
    main()
