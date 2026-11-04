"""Shared helpers of the tests (tests/test_*.py; runner: python3 tests/test_sim.py)."""
import hashlib
import os
import pickle
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sim.game import Game  # noqa: E402,F401


def play(seed=1, script="smoke.txt", pre=()):
    from sim import script as scripts
    g = Game("sandbox_open", seed)
    for line in pre:                         # e.g. "gods off": isolate a subsystem from jealous gods' curses
        g.command(line)
    for _, line in scripts.load(os.path.join(ROOT, "scripts", script)):
        if line.split()[0] not in ("status", "look", "info", "history", "map", "catalog", "houses"):
            scripts.apply(g, line)
    return g


class pre_pass:
    """Set-up code run as inside the next tick, before its figure pass (Game.step counts the tick, runs the cycle
    step, then the pass): g.tick is that tick (yielded), walkers.add / schedule count from it. No g.step inside."""
    def __init__(self, g):
        self.g = g

    def __enter__(self):
        self.g.tick += 1
        self.g.__dict__["_in_tick"] = True
        return self.g.tick

    def __exit__(self, *a):
        self.g.tick -= 1
        self.g.__dict__.pop("_in_tick", None)


def fingerprint(g):
    state = (g.tick, g.city, sorted((b.id, b.key, b.level, b.occupants, sorted(b.goods.items()))
                                    for b in g.buildings.values()))
    return hashlib.sha256(pickle.dumps(state)).hexdigest()


def assert_stable(g):
    """Ideal layout: no house devolves after the setpoint (last build/order + 24 months)."""
    from sim import render
    txt, n = render.stability(g)
    assert "before the setpoint" not in txt, txt
    assert n == 0, txt


def ti_first(gid):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import terrain_images
    return terrain_images.first(gid)


def _hoplite_horseman_per_tick(g, ox, oy):
    from sim.military import forces, units
    assert g.command(f"mobilize 9 {19 + ox} {69 + oy}") is not None
    c = forces.companies(g)[9]
    g.step(700)
    ms = forces.members(g, c)
    assert len(ms) == 8 and all(w.task == "hold" and (w.x, w.y) == forces.slot_tile(c, w.slot) for w in ms)
    c["layout"], c["under"] = 2, 3                 # the slots move; under fire: they stand
    g.step(1)
    assert all(w.task == "hold" for w in ms)
    c["under"] = 0                                 # timers 0: back to the slot (action 9, hold saved) at once
    g.step(1)
    assert all(w.task == "march" and w.after == "hold" for w in ms if (w.x, w.y) != forces.slot_tile(c, w.slot))
    c["layout"] = 1
    g.step(200)
    assert all(w.task == "hold" and (w.x, w.y) == forces.slot_tile(c, w.slot) for w in ms)
    lead = min(ms, key=lambda w: w.slot)
    e = units.spawn(g, "enemy_infantry", lead.x + 5, lead.y, delay=10 ** 6, company=0)   # 5..8 from them
    c["mode"] = 1
    for w in ms:
        w.task = "attack"
    g.step(1)
    assert c["dest"] == (e.x, e.y) and c["layout"] == 1
    assert all(w.task == "charge" and w.saved == "attack" for w in ms)
    units.remove(g, e)
    g.step(300)
    assert all(w.task == "attack" for w in ms if not w.anim)
    # within 3: engage; the target is marked; a hoplite in attack then skips it for an unmarked one
    lead = min(ms, key=lambda w: w.slot)
    e = units.spawn(g, "enemy_infantry", lead.x - 2, lead.y, delay=10 ** 6, company=0)
    g.step(1)
    assert e.tagged and sum(w.target_id == e.id for w in ms) == 1     # one engages it; the others skip it after
    e2 = units.spawn(g, "enemy_infantry", lead.x - 4, lead.y, delay=10 ** 6, company=0)
    lead.task, lead.role = "attack", "hoplite"
    assert forces.nearest_enemy(g, lead, c, 6) is e2
    lead.role = "horseman"
    # hit and run: 5 ticks with an unmarked enemy within 3 -> the company regroups (0x12); each horseman marks one
    # (its target, kept), so a crowd is needed
    from sim.systems import walkers as W
    ok = W.walkable(g)
    for dx in range(-3, 4):
        for dy in (-3, 3):
            if ok[(lead.y + dy) * 228 + lead.x + dx]:
                units.spawn(g, "enemy_infantry", lead.x + dx, lead.y + dy, delay=10 ** 6, company=0)
    c["mode"] = 2
    for w in ms:
        w.task, w.hits, w.target_id = "special", 0, 0
    seen = set()
    for _ in range(8):
        g.step(1)
        seen |= {w.task for w in ms}
    assert "regroup" in seen or any(w.after == "regroup" for w in ms), seen


def _comms_apply(base, d, keyed):
    """Python twin of viewer/play/comms.js apply (test only)."""
    assert "_b" in d
    o = {k: v for k, v in base.items() if k not in d.get("del", ())}
    o.update(d.get("set", {}))
    for k, kd in d.get("keyed", {}).items():
        key = keyed[k]
        idx = {e[key]: e for e in base[k] if e[key] not in kd.get("rm", ())}
        added = []
        for u in kd.get("up", ()):
            p = idx.get(u[key])
            if p is None:
                added.append(u[key])
                idx[u[key]] = u
            elif isinstance(u, dict):
                n = dict(p, **u)
                for f in u.get("_x", ()):
                    n.pop(f, None)
                n.pop("_x", None)
                idx[u[key]] = n
            else:
                idx[u[key]] = u
        order = kd.get("order") or [e[key] for e in base[k] if e[key] in idx] + added
        o[k] = [idx[i] for i in order]
    for k, sd in d.get("sub", {}).items():
        o[k] = {x: y for x, y in dict(base[k], **sd.get("set", {})).items() if x not in sd.get("del", ())}
    for k, x in d.get("ix", {}).items():
        o[k] = list(base[k])
        for i in range(0, len(x), 2):
            o[k][x[i]] = x[i + 1]
    return o


def _campaign(cid):
    import json
    return json.load(open(os.path.join(ROOT, "data", "campaign", f"{cid}.json")))


def _ep(a, slot):
    return next(e for e in a["episodes"] if e["slot"] == slot)


def _raises(f):
    try:
        f()
    except Exception as e:                    # noqa: BLE001
        return e
    return None


def _route_search_literal(gm, s, e, limit=100000):
    """route_search 0x00502EE0 (mode 0) as the decompile reads: the ring queue scanned linearly (no wrap: a tile
    is queued once), the distance set when first reached."""
    N = 228
    dist = [0] * (N * N)
    dist[s] = 1
    q, head, local, n = [s], 0, 0, 0
    while True:
        v, i = dist[q[head]], head
        if local < v:
            best = v
            for j in range(head + 1, len(q)):
                w = dist[q[j]]
                if w < best:
                    best, i = w, j
                    if w <= local:
                        break
            local = best
        t = q[i]
        if i != head:
            q[i] = q[head]
        if t == e:
            break
        n += 1
        if n > limit:
            break
        d = dist[t] + 1
        for m in (t - N, t + 1, t + N, t - 1):
            o = gm[m]
            if dist[m] == 0 and 0 <= o < 6:
                dist[m] = d + (40 if o == 3 else 60 if o == 4 else 10 if o == 1 else 2 if o == 5 else 0)
                q.append(m)
        head += 1
        if head == len(q):
            break
    return dist[e] != 0, dist


def _invader_routes_per_figure(g, ox, oy):
    from sim.military import invaders
    g.step(833)                                             # exe dump 833: one infantry out, timer 22, lost
    first = g.walkers[invaders.ecomps(g)[35]["ids"][0]]
    assert not first.hidden and first.task == "wait" and first.aim_due - g.tick == 22
    assert (first.x - ox, first.y - oy) == (148, 190)
    g.step(901 - 833)                                       # exe dump 901: routes to the muster spot (143, 185)
    comp = invaders.ecomps(g)[35]
    assert (comp["target"][0] - ox, comp["target"][1] - oy) == (143, 185)
    assert first.task == "march" and first.fprog == 4 and len(first.iroute) == 4
    cav = g.walkers[invaders.ecomps(g)[41]["ids"][0]]       # cavalry (speed 11: 2, 2, 2, 1 sub-steps a tick)
    assert (cav.x - ox, cav.y - oy) == (147, 189) and cav.fprog == 8
    g.step(986 - 901)                                       # exe dump 986: slot 1 decides its last step
    s1 = g.walkers[comp["ids"][1]]
    assert (s1.x - ox, s1.y - oy) == (142, 185) and s1.fprog == 0 and s1.iroute == []
