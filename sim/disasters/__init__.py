"""Terrain disasters: the map's 8 disaster points and the scenario events that set them off (types 3 earthquake,
24 lava flow, 25 tidal wave; type 5 landslide: sim/disasters/landslide.py). Track 1L-5, docs/logic/events.md
"Terrain disasters".

The exe (Zeus.exe GOG 2.1):
- At the map start (FUN_004467A0) each disaster point (0x00902CBC / 0x00902CCC, logical) whose tile carries a
  class's terrain bit gets an object of that class: 0x2000000 (fault) -> earthquake (vtable 0x005E4898), 0x10 ->
  lava (0x005D94D0), 0x100 -> tidal wave (0x005D93A0). The object's region (FUN_00447470): every tile with the
  bit 8-connected to the point (FUN_00447A50, neighbour table 0x005D90B8: N NE E SE S SW W NW), one node per tile;
  the rings (FUN_00447B70): ring 1 = the point (or, when any region tile lies within 1 of the play edge, those
  tiles: map_near_play_edge 0x00496080 d = 1), ring r + 1 = the nodes with an 8-neighbour of ring r; a node with
  fewer than 4 N/E/S/W neighbours in the region is an edge node. Ring r's inner nodes go to segment r - 1, the
  edge nodes to one more list (the "crack" list); each list is ordered by the tile's g_grid_random (FUN_00447E50).
- Its run state lives in the table 0x0078C578 (8 x 0x1C, saved): +0 segment, +4 counter, +0x10 the event,
  +0x14 state (0 idle, 2..5 running, 7 done), +0x18 started.
- event_terrain_disaster 0x0046D6D0 (the monthly pass): on its date picks a point of the record's range
  (+0x1E alone, or +0x20..+0x22; FUN_00446AE0: random untried slots, the object enabled and of the event's type)
  and starts it (FUN_004474E0): started, the event; the message 0xDE at the point (title = the class's phrase
  base, announcement base + 2, or + 1 with [god] when the parent record is a god's: FUN_004693D0); the alert
  of the class (vtable +0xC: quake 1, tidal 2, lava 4); music / sound. The record: active, state 1, done; once
  the object is idle or done again, state 2.
- terrain_events_update 0x00446A70 (every tick, after the cycle step): each started object's update (vtable +0x38)
  then its post step (+0x3C 0x00447790: random visual calls, nothing for the earthquake).

Ours: g.disasters = {"objects": [8 x dict or None], "owner": {tile: slot + 1}}; the objects are built when the first
disaster event of a game runs (the exe at the map start: the terrain they read is the map's until then, nothing the
player does clears the class bits; the lava's random seeds are drawn then, from our RNG). Nothing exists in open play.
Two points in one region share the object (disasters_create_objects: the point's tile already owned by an object of
that kind; its use count +0x34).
"""
import os

import numpy as np

from .. import scenario

QUAKE, LAVA, TIDAL = 3, 24, 25
# class: terrain bit of the region, the bits the node sets (vtable +0x18 node / +0x20 object), phrase base, alert
CLASSES = {
    QUAKE: dict(name="earthquake", mask=0x2000000, sets=0x300002, phrase=0x52E, alert=1, kind=3),
    LAVA: dict(name="lava flow", mask=0x10, sets=0x1000000, phrase=0x522, alert=4, kind=1),
    TIDAL: dict(name="tidal wave", mask=0x100, sets=0x100, phrase=0x528, alert=2, kind=2),
}
NB = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))     # 0x005D90B8
CLEAR = 0xFACFA710                    # the earthquake node's terrain mask (0x0056D300)
N = 228


def state(g):
    return g.__dict__.get("disasters")


def _rand(g):
    from ..world import read_map
    hdr, blocks = read_map(g.map_name)
    d = {b["rank"]: b["data"] for b in blocks}
    return np.frombuffer(d[8], "u1")[:N * N].reshape(N, N).copy()


def _near_edge(w, x, y, d=1):
    """map_near_play_edge(x, y, d): a tile within d (along x or y) of an off-map tile or of the grid border."""
    if x < d or y < d or x >= N - d or y >= N - d:
        return True
    for k in range(1, d + 1):
        for dx, dy in ((k, 0), (-k, 0), (0, k), (0, -k)):
            if not w.inside(x + dx, y + dy):
                return True
    return False


def setup(g):
    """FUN_004467A0: the objects of the 8 disaster points."""
    st = state(g)
    if st is not None:
        return st
    st = g.__dict__["disasters"] = {"objects": [None] * 8, "owner": {}}
    w = g.world
    pts = (getattr(w, "points", None) or {}).get("disaster") or []
    rand = _rand(g)
    for i in range(8):
        p = pts[i] if i < len(pts) else None
        if p is None:
            continue
        x, y = p
        f = int(w.flags[y, x])
        cls = QUAKE if f & 0x2000000 else LAVA if f & 0x10 else TIDAL if f & 0x100 else None
        if cls is None:
            continue
        k = st["owner"].get((x, y))                # the point's tile already in an object of this kind: shared
        prev = st["objects"][k - 1] if k else None
        if prev is not None and CLASSES[prev["cls"]]["kind"] == CLASSES[cls]["kind"]:
            st["objects"][i] = prev
            prev["uses"] += 1
            continue
        st["objects"][i] = _build(g, w.flags.copy(), rand, st["owner"], i, cls, (x, y))
    return st


def _build(g, flags, rand, owner, i, cls, p):
    """disaster_region_build 0x00447470 / disaster_region_add 0x00447A50 / disaster_rings 0x00447B70: region,
    the class's ring pre-pass (vtable +0x1C), rings, segments. `flags` is a copy: the exe clears the region bit
    while it walks and sets it back at the end."""
    w = g.world
    c = CLASSES[cls]
    mask = c["mask"]
    nodes, at = [], {}
    near_any = fault = False

    def add(x, y):                            # FUN_00447A50 (pre-order: the node, then its 8 neighbours in turn)
        nonlocal near_any, fault
        if not w.inside(x, y) or not int(flags[y, x]) & mask:
            return None
        near = _near_edge(w, x, y)            # the class's make_node (vtable +0x2C): +0x2D |= near, ring = near
        near_any |= near
        n = dict(x=x, y=y, ring=1 if near else 0, dir=0, edge=False, skip=False)
        if cls == LAVA and int(w.flags[y, x]) & 0x2000000:   # lava_make_node 0x005073A0: a fault tile, +0x2E
            fault = True
            n["ring"] = 1
        at[(x, y)] = len(nodes)
        nodes.append(n)
        if not owner.get((x, y)) or cls == LAVA:   # the owner byte 0x0078C658: a lava node takes it (vtable +0x20)
            owner[(x, y)] = i + 1
        flags[y, x] = int(flags[y, x]) & ~mask & 0xFFFFFFFF
        return n

    start = add(*p)
    stack = [(p[0], p[1], 0)] if start is not None else []
    while stack:                              # the recursion as an explicit stack (deep fault lines)
        x, y, k = stack.pop()
        if k >= 8:
            continue
        stack.append((x, y, k + 1))
        dx, dy = NB[k]
        if add(x + dx, y + dy) is not None:
            stack.append((x + dx, y + dy, 0))
    obj = dict(cls=cls, idx=i, x=p[0], y=p[1], enabled=start is not None, near=near_any, fault=fault, nodes=nodes,
               segs=[], crack=[], seg=0, count=0, c2=0, c3=0, state=0, started=False, event=-1, uses=1,
               cracked=[], changed=[], alert=False)
    if start is None:
        return obj
    if not near_any:
        start["ring"] = 1
    _prepass(g, obj, at)
    live = [n for n in nodes if not n.get("removed")]
    cur = 1
    for _ in range(4 * len(nodes) + 4):       # FUN_00447B70 (a region without ring 1 would never end: capped)
        pending = False
        for n in live:
            if n["ring"]:
                continue
            pending = True
            card = run = best = 0
            first, second, hit = -1, -1, False
            for k in range(16):
                dx, dy = NB[k & 7]
                xx, yy = n["x"] + dx, n["y"] + dy
                nxt = run
                if w.inside(xx, yy):
                    m = at.get((xx, yy))
                    if m is not None:
                        if not k & 1:
                            card += 1
                        if nodes[m]["ring"] == cur:
                            hit = True
                            if best < run:
                                second, first, nxt, best = first, -1, 0, run
                            run = nxt
                            continue
                    if first < 0:
                        first = k
                    nxt = run + 1
                run = nxt
            if hit:
                if card < 8:
                    n["edge"] = True
                n["ring"] = cur + 1
                n["dir"] = (best // 2 + second) & 7
        if not pending:
            break
        cur += 1
    obj["rings"] = cur
    segs = [[] for _ in range(cur)]
    for j, n in enumerate(nodes):             # FUN_00447E50: by g_grid_random, ties as the exe inserts them
        if n.get("removed"):
            continue
        lst = obj["crack"] if n["edge"] else segs[n["ring"] - 1] if 0 < n["ring"] <= cur else None
        if lst is not None:
            _insert(lst, j, int(rand[n["y"], n["x"]]), nodes)
    obj["segs"] = segs
    return obj


def _prepass(g, o, at):
    """The class's ring pre-pass (vtable +0x1C, first thing in disaster_rings)."""
    if o["cls"] == QUAKE:                     # quake_clear_edge_flags 0x0056DE40: +0x20 = 0 (none set yet here)
        for n in o["nodes"]:
            n["edge"] = False
    elif o["cls"] == LAVA:
        _lava_seed(g, o, at)
    elif o["cls"] == TIDAL:
        _tidal_pass(g, o, at)


def _lava_seed(g, o, at):
    """lava_seed_rings 0x005076D0. Not near the play edge and no fault: 100 passes over the nodes, each node with
    rng & 7 == 0 becomes ring 1 when all 8 neighbours are region nodes and exactly one of its N/E/S/W neighbours is
    ring 1 (a branch grows from the point); stop after the pass that brought the count of such picks to 10.
    With a fault tile in the region (+0x2E): ring 1 = the fault nodes only (the near-edge nodes' ring 1 cleared)."""
    nodes, w = o["nodes"], g.world
    if not o["near"] and not o["fault"]:
        left = 10
        for _ in range(100):
            for n in nodes:
                if g.rng.randrange(8):                 # (rng_a & 7) == 0, one draw per node
                    continue
                every = ones = 0
                for k, (dx, dy) in enumerate(NB):      # the table 0x005D9450 (= NB)
                    xx, yy = n["x"] + dx, n["y"] + dy
                    if not w.inside(xx, yy):
                        continue
                    m = at.get((xx, yy))
                    if m is not None:
                        every += 1
                        if not k & 1 and nodes[m]["ring"] == 1:
                            ones += 1
                if ones == 1 and every == 8:
                    n["ring"] = 1
                    left -= 1
            if left < 1:
                break
    if not o["fault"]:
        return
    o["near"] = False                                  # +0x2D = 0
    for n in nodes:
        if n["ring"] and not int(w.flags[n["y"], n["x"]]) & 0x2000000:
            n["ring"] = 0


def _tidal_pass(g, o, at):
    """tidal_terrain_pass 0x004E4B40 (before the first start, +0x18 = 0): a water tile of the region next to a
    region land tile gets terrain 0x2000 (the shore); then a deep-water node (0x4000000) leaves the region (its
    owner byte 0; the exe keeps its freed node in the tile grid, so it still counts as a neighbour), a shallow one on
    the shore or next to deep water is a seed: ring 1, skipped (+0x21: never flooded)."""
    w = g.world
    f = w.flags
    owner = state(g)["owner"] if state(g) else {}

    def nb(n):
        for dx, dy in NB:
            xx, yy = n["x"] + dx, n["y"] + dy
            if 0 <= xx < N and 0 <= yy < N:
                yield int(f[yy, xx])
    for n in o["nodes"]:
        t = int(f[n["y"], n["x"]])
        if t & 4 and any(v & 0x100 and not v & 4 for v in nb(n)):
            f[n["y"], n["x"]] = t | 0x2000
    for n in o["nodes"]:
        t = int(f[n["y"], n["x"]])
        if not t & 4:
            continue
        if t & 0x4000000:
            n["removed"] = True
            owner.pop((n["x"], n["y"]), None)
        elif t & 0x2000 or any(v & 0x4000000 for v in nb(n)):
            n["ring"] = 1
            n["skip"] = True


def _insert(lst, j, key, nodes):
    """FUN_00447E50: key <= head -> front; key < tail -> before the first with key >= it; else at the back."""
    keys = [nodes[k]["key"] for k in lst]
    nodes[j]["key"] = key
    if not lst or key <= keys[0]:
        lst.insert(0, j)
    elif key < keys[-1]:
        lst.insert(next(i for i, v in enumerate(keys) if v >= key), j)
    else:
        lst.append(j)


# --- the scenario event ---------------------------------------------------------------------------------------------

def event(g, ev):
    """event_terrain_disaster 0x0046D6D0 (types 3, 24, 25)."""
    st = setup(g)
    grp = ev["groups"]["city"]
    if not ev["active"] and scenario.due(g, ev):
        a, b, c = grp[1], grp[2], grp[3]
        if a < 0:
            lo, hi = b, c
        elif b < 0:
            lo = hi = a
        else:
            lo = hi = -1
        k = _pick(g, st, ev, lo, hi)
        if k >= 0:
            ev.update(point=k, active=1, state=1)
            ev["flags"] |= scenario.DONE
            return
    else:
        if ev["state"] != 1:
            return
        o = st["objects"][ev.get("point", 0)] if 0 <= ev.get("point", 0) < 8 else None
        if o is not None and o["state"] not in (0, 7):
            return
        ev["active"] = 0
    ev["state"] = 2


def _pick(g, st, ev, lo, hi):
    """FUN_00446AE0: untried slots of lo..hi at random (rng_15 % n), the first enabled object of the event's type
    that starts."""
    n = hi - lo + 1
    if lo <= 0 or hi >= 9 or n <= 0:
        return -1
    tried = [False] * n
    left, retries = n, 10000
    while left and retries:
        k = scenario.rng15(g) % n
        if tried[k]:
            retries -= 1
            continue
        tried[k] = True
        left -= 1
        i = k + lo - 1
        o = st["objects"][i]
        if o is not None and o["enabled"] and o["cls"] == ev["type"] and start(g, o, ev):
            return i
    return -1


def start(g, o, ev):
    """FUN_004474E0: started, the event; the message and the alert."""
    if o["started"]:
        return False
    o.update(started=True, event=ev["id"])
    c = CLASSES[o["cls"]]
    base = c["phrase"]
    if o["cls"] == TIDAL:                      # 0x004E4DE0: Poseidon's flood (record +0x79) has its own phrases
        base = 0x1022 if scenario._byte(ev, 0x79) else 0x528
    par = scenario.get(g, ev.get("parent", -1))
    god = None
    if par is not None and (_by_god(par) or par["type"] == 27):
        body, god = base + 1, scenario._byte(par, 6)
    else:
        body = base + 2
    from .. import alerts, messages
    kw = {}
    if god is not None:
        from ..gods import NAMES
        kw["god"] = NAMES[god] if 0 <= god < len(NAMES) else ""
    try:
        # FUN_00521A70(0xDE, ..., the object's tile): a type-0xDE message, its window has the go-to button
        # FUN_005A1210(3 / 6) before it: S_dis (play mode: viewer/play/audio.js specials)
        messages.post(g, base, body, meta=dict(at=[o["x"], o["y"]], kind=0xDE, stinger="dis"), **kw)
    except KeyError:                             # Poseidon's flood phrases (0x1022..) are not in data/messages.json
        g.message(f"{c['name']} (phrases {base:#x}/{body:#x})")
    alerts.raise_alert(g, c["alert"], (o["x"], o["y"]))
    return True


def _by_god(par):
    """FUN_004693D0: a request of kind 3, or a city status change of kind 13 / 22."""
    t, k = par["type"], par.get("kind", 0)
    return (t == 1 and k == 3) or (t == 19 and k in (13, 22))


# --- every tick -----------------------------------------------------------------------------------------------------

def tick(g):
    """terrain_events_update 0x00446A70: each started object's update (vtable +0x38). The post step (+0x3C,
    disaster_post_step 0x00447790) only makes effect figures (dust, lava splashes, spray): play mode's (export)."""
    st = state(g)
    if st is None:
        return
    seen = set()
    for o in st["objects"]:
        if o is None or not o["started"] or id(o) in seen:
            continue
        seen.add(id(o))
        UPDATE[o["cls"]](g, o)
        if g.__dict__.get("fx") is not None:      # live only: the post step makes pictures, no game state
            post_step(g, o)


# --- the post step (disaster_post_step 0x00447790): effect figures, play mode only (bugs.md 362) ------------------
# Every tick in states 2..5: p = count * 100 / vtable+0x40 (20; the tidal wave 5), in state 5 max(0, 99 - p); the
# current segment (vtable +0x18: seg clamped to 0..rings-1, the tidal wave's seg - 1 in state 5) gets segment
# vtable +0xC(p); when seg > 1 one random segment below seg - 1 gets +0x10; segment 0 +0x14; the crack list +0xC(110).
# Segment vtables (0x005D94B4 lava, 0x005E487C quake, 0x005D9384 tidal) and node vtables (0x005D9490, 0x005E4858,
# 0x005D9360), read from the exe:
#   lava  +0xC FUN_00506F40: k nodes from a random one (k = n when n > (rng & 7) + 15, else (rng & 7) + 15; wraps)
#              -> node FUN_00506D00: not an edge node, or its tile is lava (0x1000000): FUN_00411920 = subtype 1;
#         +0x10 FUN_00507170: one random node -> FUN_00411BE0 = subtype 2 (drifting drops);
#         +0x14 FUN_00507270: one random node -> FUN_00411DD0 = subtype 3, a ballistic blob that FUN_00410E50 deletes
#              on its first update (case 3: 0 frames, flags 9 without 0x20): never seen, not reported.
#   quake +0xC quake_segment_dust 0x0056D5A0: k nodes (n, or (rng & 3) + 5) -> node FUN_0056D2F0, which only calls the
#              getter +0x18 (0x0056DE80: 0x300002): no figure; +0x10 / +0x14 (0x0056D7D0 / 0x0056D990) call the
#              node's no-ops 0x00401000. The earthquake shows only collapse_debris_spawn's dust (quake_crack).
#   tidal +0xC FUN_004E4480: k nodes (k = (rng & 3) + 4 when n >= (rng & 3) + 4, else n; all n when the first is a
#              skipped node, the state 2 and the count 1) -> node FUN_004E3E40: not an edge node, or its tile is
#              water (0x40FEB0: 4): FUN_00412080 = subtype 4 (spray); +0x10 / +0x14 no-ops.
# The exe draws its own RNG for every pick (the game's state, made only on screen by FUN_004104D0); ours uses a local
# generator seeded by the tick and the object, so the sim's RNG and state are untouched (hashes unchanged).
DIRS8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))     # 0x005D8408


def _fine(p, d, r):
    """FUN_00411920 / FUN_00412080: the spot in the tile, 0..14 fine units a side (of 15) from the progress p along
    the node's direction: a side moving that way gets base (p // 100) * 100 or 100 - p and a range of p % 100 (>= 1),
    else range 100; v = trunc((r % range + base) * 0.01 * 14), stored as the byte v << 3 (signed), read back >> 3."""
    out = []
    for k in (0, 1):
        s = DIRS8[d & 7][k]
        base, rng = (p // 100) * 100, 100
        if s == -1:
            base = 100 - p
        if s in (-1, 1):
            rng = max(1, p % 100)
        v = int((r.randrange(32768) % rng + base) * 0.01 * 14.0)
        b = (v << 3) & 0xFF
        b = b - 256 if b > 127 else b
        out.append(int(b / 8))
    return out


def _walk(lst, start, k):
    n = len(lst)
    return [lst[(start + i) % n] for i in range(k)]


def post_step(g, o):
    from .. import effects
    st = o["state"]
    if st not in (2, 3, 4, 5) or o["cls"] == QUAKE:
        return
    import random
    r = random.Random(g.tick * 16 + o["idx"])
    nodes, R = o["nodes"], o.get("rings", 0)
    tidal = o["cls"] == TIDAL
    p = int(o["count"] * 100 / (5 if tidal else 20))
    if st == 5:
        p = max(0, 99 - p)
    cur = max(0, min(o["seg"] - (1 if tidal and st == 5 else 0), R - 1))
    flags = g.world.flags

    def spawn(lst, p):
        n = len(lst)
        if not n:
            return
        start = max(0, r.randrange(32768) % n - 1)
        if tidal:
            k = (r.randrange(32768) & 3) + 4
            if k > n:
                k = n
            if nodes[lst[start]]["skip"] and st == 2 and o["count"] == 1:
                k = n
        else:
            k = (r.randrange(32768) & 7) + 15
            if n > k:
                k = n
        for j in _walk(lst, start, k):
            nd = nodes[j]
            x, y = nd["x"], nd["y"]
            if nd["edge"] and not int(flags[y, x]) & (4 if tidal else 0x1000000):
                continue
            fx, fy = _fine(p, nd["dir"], r)
            effects.splash(g, "spray" if tidal else "lava", x, y, fx, fy, 0 if tidal else r.randrange(32768) % 6)

    if R:
        spawn(o["segs"][cur], p)
        if not tidal and o["seg"] > 1:          # FUN_00507170 on a random segment below seg - 1
            lst = o["segs"][r.randrange(32768) % (o["seg"] - 1)]
            if lst:
                nd = nodes[lst[max(0, r.randrange(32768) % len(lst) - 1)]]
                a = (r.randrange(32768) & 7) + nd["dir"] * 31 - 4          # FUN_00411BE0: angle, speed 0 / 1
                effects.drops(g, nd["x"], nd["y"], a & 0xFF, ((r.randrange(32768) % 3) * 8 + 8) >> 4,
                              r.randrange(32768) & 3)
    spawn(o["crack"], 110)


def quake_update(g, o):
    """0x0056DD40: one ring every 20 calls; then state 7."""
    if o["state"] == 0:
        o["state"] = 2
    elif o["state"] != 2:
        return
    _rings_out(g, o, 19, 1)
    if o["rings"] <= o["seg"]:
        o["state"] = 7


def lava_update(g, o):
    """lava_update 0x00507560: state 2 as the quake (a ring every 20 calls, lava_node_burn), then 3: the lava cools,
    +0xC (c3) + 1 every 3 calls; at 100 (300 calls) state 7. c3 is the cooling percent (vtable +0x14 0x00507920):
    the edge pictures' colour (vtable +0x10 0x00507950, play mode)."""
    if o["state"] == 0:
        o["state"] = 2
    elif o["state"] != 2:
        if o["state"] != 3:
            return
        o["c2"] += 1
        if o["c2"] > 2:
            o["c3"] += 1
            o["c2"] = 0
        if o["c3"] >= 100:
            o["state"] = 7
        return
    _rings_out(g, o, 19, 1)
    if o["rings"] <= o["seg"]:
        o["state"] = 3


def tidal_update(g, o):
    """tidal_update 0x004E4890: 2: a ring every 5 calls (flooded: node apply 1) -> 4: 10 calls (c2, c3) -> ring
    index - 1, then 5 (or 7 for Poseidon's flood, record +0x79: the water stays) -> 5: back ring by ring every 5
    calls (apply 0; the edge nodes all at once on each step) -> 7: the table entry reset (FUN_00447DD0: not started,
    state 0), so the record can start it again."""
    st = o["state"]
    if st in (0, 2):
        if st == 0:
            o["state"] = 2
        _rings_out(g, o, 4, 1)
        if o["rings"] <= o["seg"]:
            o["state"] = 4
    elif st == 4:
        o["c2"] += 1
        if o["c2"] > 9:
            o["c3"] += 1
            o["c2"] = 0
        if o["c3"] < 1:
            return
        o["seg"] -= 1
        ev = scenario.get(g, o["event"])
        _tidal_state(g, o, 7 if ev is not None and scenario._byte(ev, 0x79) else 5)
    elif st == 5:
        o["count"] += 1
        if o["count"] > 4:
            if _advance(g, o, o["segs"][o["seg"]], 0):
                o["seg"] -= 1
            _advance(g, o, o["crack"], 0)
            if o["seg"] >= 0:
                o["count"] = 0
        if o["seg"] < 0:
            _tidal_state(g, o, 7)


def _tidal_state(g, o, s):
    """tidal_set_state 0x004E4E40: 7 without the flood resets the table entry (FUN_00447DD0)."""
    o["state"] = s
    if s == 7:
        ev = scenario.get(g, o["event"])
        if ev is None or not scenario._byte(ev, 0x79):
            o.update(seg=0, count=0, c2=0, c3=0, event=0, state=0, started=False)


def _rings_out(g, o, every, apply):
    """The outward step of the three updates: count + 1; past `every`, segment [seg] (disaster_list_advance
    0x00447230 with (apply, 0, 1)), seg + 1 when it is done, then the crack list; the count restarts while rings
    remain."""
    R = o["rings"]
    o["count"] += 1
    if o["count"] > every:
        if o["seg"] < R and _advance(g, o, o["segs"][o["seg"]], apply):
            o["seg"] += 1
        _advance(g, o, o["crack"], apply)
        if o["seg"] < R:
            o["count"] = 0


def _advance(g, o, lst, apply=1):
    """0x00447230 (apply, 0, 1): every node of the list in order but the skipped ones (+0x21), then done."""
    fn = NODE[o["cls"]]
    for j in lst:
        n = o["nodes"][j]
        if not n["skip"]:
            fn(g, o, n, apply)
    return True


def _edge_wait(o, n):
    """An edge node applies only on the ring the object is at (node +0x20, +0x18 against the table's segment)."""
    return n["edge"] and n["ring"] != o["seg"]


def _destroy(g, x, y):
    """building_destroyed_by_attack(x, y, tile, 1) on the building of the tile, not a ruin (0xA9)."""
    b = g.buildings.get(int(g.world.occ[y, x]))
    if b is not None and b.key != "ruin":
        from ..systems import risk
        from .. import effects
        effects.debris(g, b.x, b.y, b.size)   # building_destroyed_by_attack: collapse_debris_spawn(x, y, size, 1, 4, 0)
        risk.collapse(g, b)


def _set(g, o, x, y, f, road=None):
    w = g.world
    if road is not None and bool(w.road[y, x]) != road:
        w.road[y, x] = road
        g.__dict__["_quake_roads"] = True
    w.flags[y, x] = f & 0xFFFFFFFF
    o["changed"].append((x, y))
    g.map_version = getattr(g, "map_version", 0) + 1


def quake_crack(g, o, n, apply=1):
    """0x0056D300: an inner node, or an edge node of the current ring: the building on it falls
    (building_destroyed_by_attack, not a ruin), the tile becomes cracked rock (terrain & 0xFACFA710 | 0x300002,
    piece | 0x80), dust (collapse_debris_spawn: play mode), the figures on it die."""
    if _edge_wait(o, n):
        return
    w = g.world
    x, y = n["x"], n["y"]
    _destroy(g, x, y)
    f = int(w.flags[y, x])
    _regrow_clear(g, x, y, f)
    _set(g, o, x, y, (f & CLEAR) | 0x300002, road=False if w.road[y, x] else None)
    o["cracked"].append((x, y))
    from .. import effects
    effects.debris(g, x, y, 1)                # collapse_debris_spawn(x, y, 1, 0, (rng & 1) + 1, 0)
    _kill_on(g, x, y, (0x06, 0x0E, 0x22))


def lava_burn(g, o, n, apply=1):
    """lava_node_burn 0x00506D80: as the quake's node without the dust: the building falls (terrain 8, not a ruin,
    not state 6), terrain & 0xFBCFA710 | 0x1000000 (lava: trees, rocks, water, roads, rubble, meadow gone; the
    region bits stay), draw |= 0x40, piece &= 0x70, the 0xCB4B08 byte 0; figures die but types 6, 0xE, 0x22."""
    if _edge_wait(o, n) or not apply:
        return
    w = g.world
    x, y = n["x"], n["y"]
    _destroy(g, x, y)
    f = int(w.flags[y, x])
    _regrow_clear(g, x, y, f)
    _set(g, o, x, y, (f & 0xFBCFA710) | 0x1000000, road=False if w.road[y, x] else None)
    _kill_on(g, x, y, (0x06, 0x0E, 0x22))


def tidal_apply(g, o, n, apply):
    """0x004E3EC0 (decompiled with re/ghidra DecompAt). Skipped nodes never; an edge node only on its ring while
    flooding (any time while the water goes back, state 5).
    apply 1: terrain & 0xFFCFEFDD | 4 (water; rock 2, 0x20, rubble 0x1000, 0x300000 cleared; trees stay); a road
    (0x40) is kept as 0x8000000; the building of the tile (terrain 8, not a ruin, not state 6) or a 0x4000 tile:
    building_destroyed_by_attack; figures on it die but types 6 and 0xE (FUN_004E1AE0).
    apply 0: a water tile: & 0xFBFFFFFB (water and deep gone), 0x8000000 -> the road again; boats (figure types 0x14,
    0x19, 0x39) on it pushed 2 tiles towards the water (_push_boats). Not ported: FUN_0041DA20 on the 8 neighbours
    (water edge bytes 0xCB4B08, pictures)."""
    if n["skip"]:
        return
    if n["edge"] and o["state"] != 5 and n["ring"] != o["seg"]:
        return
    w = g.world
    x, y = n["x"], n["y"]
    f = int(w.flags[y, x])
    if apply:
        _regrow_clear(g, x, y, f)
        f2 = (f & 0xFFCFEFDD) | 4
        road = None
        if f & 0x40 or w.road[y, x]:
            f2 = (f2 & ~0x40) | 0x8000000
            road = False
        _set(g, o, x, y, f2, road)
        b = g.buildings.get(int(w.occ[y, x]))
        if (b is not None or f & 0x4000) and (b is None or b.key != "ruin"):
            _destroy(g, x, y)
        _kill_on(g, x, y, (0x06, 0x0E))
    elif f & 4:
        if f & 0x8000000:
            _set(g, o, x, y, (f & 0xF3FFFFFB) | 0x40, road=True)
        else:
            _set(g, o, x, y, f & 0xFBFFFFFB)
        _push_boats(g, x, y)
    # the farm of the tile (building_is_crop, its 3x3 without water, FUN_004AA600) gets its crop pieces back (piece 2,
    # terrain 8, crop_redraw): pictures only; ours draws a farm's crops from its state every frame


BOATS = ("ship", "boat", "trireme")        # figure types 0x14 trade ship, 0x19 fishing boat, 0x39 trireme


def _push_boats(g, x, y):
    """0x004E3EC0, apply 0 on a water tile: each boat on the tile moves 2 tiles towards the middle of the longest arc
    of water around it (FUN_004A1FF0(4): the 8 neighbours N NE E SE S SW W NW with terrain 4; the exe's run scan over
    16 steps keeps a run broken by land unless it was the longest so far)."""
    boats = [w for w in g.walkers.values() if w.x == x and w.y == y and w.role in BOATS]
    if not boats:
        return
    f = g.world.flags
    wet = [bool(int(f[y + dy, x + dx]) & 4) if 0 <= x + dx < N and 0 <= y + dy < N else False for dx, dy in NB]
    best, start, cs, cl = 0, -1, -1, 0
    for i in range(16):
        if not wet[i & 7] or i == 15:
            if wet[i & 7]:
                if cs < 0:
                    cs = i
                cl += 1
            if best < cl:
                best, start, cs, cl = cl, cs, -1, 0
        else:
            if cs < 0:
                cs = i
            cl += 1
    dx, dy = NB[(best // 2 + start) & 7]
    for w in boats:
        w.x += 2 * dx
        w.y += 2 * dy
        w.path = []
        w.prev = None


def _regrow_clear(g, x, y, f):
    if f & 0x1:
        rg = getattr(g, "regrow", None)
        if rg:
            g.regrow = [r for r in rg if (r[1], r[2]) != (x, y)]


def _kill_on(g, x, y, spared=()):
    """FUN_004E1AE0 on every figure of the tile but the class's spared types (effects 6 and the exe's 0xE / 0x22:
    none of ours) and the hero (0x45: its own handler FUN_004C8EB0, not ported)."""
    from ..systems import walkers
    from ..military import hooks as mh
    for w in [w for w in g.walkers.values() if w.x == x and w.y == y]:
        if w.role == "hero":
            continue
        mh.died(g, w, None)
        mh.gone(g, w)
        walkers.remove(g, w)


UPDATE = {QUAKE: quake_update, LAVA: lava_update, TIDAL: tidal_update}
NODE = {QUAKE: quake_crack, LAVA: lava_burn, TIDAL: tidal_apply}


def after_tick(g):
    """Grid upkeep once per tick when a node changed roads (route_grid_build_rect)."""
    if g.__dict__.pop("_quake_roads", False):
        from ..systems import roads
        roads.rebuild(g)


def cracked_tiles(g):
    """Every tile cracked by an earthquake so far (play mode: piece 0x80)."""
    st = state(g)
    if st is None:
        return []
    return [t for o in _objects(st) if o["cls"] == QUAKE for t in o["cracked"]]


def _objects(st):
    out, seen = [], set()
    for o in st["objects"]:
        if o is not None and id(o) not in seen:
            seen.add(id(o))
            out.append(o)
    return out


def lava_tiles(g):
    """Play mode (FUN_00520820 / FUN_00507980): {(x, y): (object state, cooling c3)} of the tiles whose node is a
    lava node (the tile grid 0x00799168: a lava node takes the tile)."""
    st = state(g)
    if st is None:
        return {}
    out = {}
    for o in _objects(st):
        if o["cls"] == LAVA and o["started"]:
            for n in o["nodes"]:
                out[(n["x"], n["y"])] = (o["state"], o["c3"])
    return out


def export(g):
    st = state(g)
    if st is None:
        return None
    return [dict(i=o["idx"], cls=o["cls"], x=o["x"], y=o["y"], state=o["state"], seg=o["seg"], rings=o.get("rings", 0),
                 count=o["count"], c2=o["c2"], c3=o["c3"], started=o["started"]) for o in _objects(st)]


for _t in (QUAKE, LAVA, TIDAL):
    scenario.register(_t, event, "sim.disasters")

from . import landslide  # noqa: E402,F401  (type 5)
