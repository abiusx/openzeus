"""Walker motion as play mode draws it, from the frames' step records (sim/live.py _walker_step; viewer/play/scene.js:
the newest record whose step has begun, its [from x, from y, start, end] interpolated), without a browser: the largest
move of any walker between two draws a quarter tick apart, and the moves above a limit (bugs.md 46: a stutter shows
as whole-tile jumps). For a change to the tick order or the step records (11-02).

    python3 tools/walker_smooth_check.py [--script boom.txt] [--ticks 600] [--every 1] [--limit 0.2] [--roles R,..]

--script invcity: the working city with rabble company 1 marching (tools/oracle_invcity.py ours_game; soldiers'
sub-step walk, bugs.md 432).

--every N: a frame every N ticks (play mode records on a divisor of its REC grid). Walkers that appear, vanish or
are moved by the sim without a step (a hidden invader shown, a cart led by its stonecutter) are counted apart.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def frames(script, ticks, every, roles=None):
    from sim.game import Game
    from sim import script as scripts
    from sim.live import _walker_step
    if script == "invcity":                       # the working city, rabble company 1 marching (tools/oracle_invcity.py)
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import oracle_invcity
        g = oracle_invcity.ours_game()
    else:
        g = Game("sandbox_open", 1)
        for _, line in scripts.load(os.path.join(ROOT, "scripts", script)):
            if line.split()[0] not in ("status", "look", "info", "history", "map", "catalog", "houses"):
                scripts.apply(g, line)
    out = {}
    t_end = g.tick + ticks
    while g.tick < t_end:
        g.step(every - g.tick % every if g.tick % every else every)
        out[g.tick] = {w.id: (w.x, w.y, _walker_step(g, w)) for w in g.walkers.values() if not roles or w.role in roles}
        ROLES[g.tick] = {w.id: w.role for w in g.walkers.values()}
    return out


ROLES = {}


def pos(f0, f1, i, t, k):
    w, n = f0.get(i), f1.get(i) if f1 else None
    if w is None:
        return None
    src = n if n is not None and n[2] and n[2][2] <= t else w
    st = src[2] if src[2] and src[2][2] <= t else None
    if st:
        kk = min(1.0, max(0.0, (t - st[2]) / (st[3] - st[2])))
        return (st[0] + (src[0] - st[0]) * kk, st[1] + (src[1] - st[1]) * kk)
    x1, y1 = (n[0], n[1]) if n is not None else (w[0], w[1])
    if n is not None and n[2] and n[2][2] > t and (n[2][0], n[2][1]) == (w[0], w[1]):
        x1, y1 = w[0], w[1]                      # its next step starts later from here: it stands (scene.js)
    return (w[0] + (x1 - w[0]) * k, w[1] + (y1 - w[1]) * k)


def main(argv):
    a = argparse.ArgumentParser()
    a.add_argument("--script", default="boom.txt")
    a.add_argument("--ticks", type=int, default=600)
    a.add_argument("--every", type=int, default=1)
    a.add_argument("--limit", type=float, default=0.2)
    a.add_argument("--roles", help="only these roles, e.g. rabble,hoplite,horseman")
    a.add_argument("--stand", type=float, default=2, help="report stands inside a walk of at least this many ticks")
    a.add_argument("--stand-roles", help="fail on stands of these roles (route walkers), e.g. immigrant,cart,water")
    o = a.parse_args(argv)
    fr = frames(o.script, o.ticks, o.every, set(o.roles.split(",")) if o.roles else None)
    rl = ROLES
    ts = sorted(fr)
    last, worst, over, samples = {}, 0.0, 0, 0
    still, stands, moved = {}, [], {}                       # still[i] = (t0, moved before): drawn standing since t0 inside a walk
    for a0, a1 in zip(ts, ts[1:]):
        f0, f1 = fr[a0], fr[a1]
        for q in range(4 * (a1 - a0)):
            t = a0 + q / 4
            k = (t - a0) / (a1 - a0)
            for i in f0:
                p = pos(f0, f1, i, t, k)
                if p is None:
                    continue
                prev = last.get(i)
                last[i] = (t, p)
                if prev is None or prev[0] != t - 0.25:
                    continue
                d = max(abs(p[0] - prev[1][0]), abs(p[1] - prev[1][1]))
                samples += 1
                if d == 0:
                    if i not in still:
                        still[i] = (t - 0.25, moved.get(i, False))
                else:
                    s0 = still.pop(i, None)
                    if s0 and s0[1] and t - 0.25 - s0[0] >= 1:
                        stands.append((i, s0[0], t - 0.25 - s0[0]))
                    moved[i] = True
                if d > 1.5:                         # teleported by the sim (no step): not a draw stutter
                    continue
                worst = max(worst, d)
                over += d > o.limit
    print(f"{samples} walker-draws, largest move in a quarter tick {worst:.3f} tile, {over} above {o.limit}")
    # stands inside a walk (bug 442): drawn still for >= STAND ticks between two moves. A walker on a route should
    # never stop between steps; work stops (a grower at a tree, a shepherd's sheep...) are counted too, so the list
    # is by role, and --stand-roles limits the failing count to the walkers that walk routes
    from collections import Counter
    roles = {}
    for t in ts:
        for i, r in rl.get(t, {}).items():
            roles[i] = r
    long_ = [x for x in stands if x[2] >= o.stand]
    by = Counter(roles.get(i, "?") for i, _, _ in long_)
    bad = [x for x in long_ if not o.stand_roles or roles.get(x[0]) in o.stand_roles.split(",")]
    print(f"stands inside a walk (>= {o.stand} ticks): {len(long_)}; by role {dict(by.most_common(12))}")
    for i, t0, d in bad[:8]:
        print(f"  walker {i} ({roles.get(i)}) still {d:.2f} ticks from {t0:.2f}")
    return 1 if over or (o.stand_roles and bad) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
