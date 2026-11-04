"""Live runner: the server owns a Game, simulates it and records everything; the browser plays the
recording back like a video (viewer/index.html).

  python3 -m sim live [SAVE] [--script SCRIPT] [--port 8765] [--speed TICKS_PER_SEC] [--no-test-commands]

--no-test-commands: test-only commands (sim/testcmds.py) are refused for the server's whole run, whatever the
save's `testcmds` setting (default: the save decides, on unless `testcmds off`; docs/play.md "Test commands").

One live timeline (user decision 2026-10-27): the server advances the city with the wall clock at
its own speed (`rate` ticks/s, `paused`), records a walker frame every REC ticks and a building snapshot
whenever the map changes or every STATE_EVERY ticks. A browser tab is either live (follows the live
tick; may change speed/pause and send commands) or replaying (plays the recording at any tick and
speed, read-only). The server tracks no tabs: a command carries the sender's tick and is accepted only
if it is within live_window() of live (scripts and curl send no tick).

HTTP:
  GET  /frame.json?t=T&rate=R   frames around tick T (f0 <= T < f1) + meta (sim viewer; R sets the live
                                speed when T is live)
  GET  /frames.json?from=A&to=B&at=T   play mode: frames A..B + meta (live tick, rate, paused, window)
                                [&v=2&base=FS]: protocol 2, deltas on the tab's newest frame (docs/play/comms.md)
  GET  /state.json?t=T[&lite=1] building snapshot in effect at tick T (+ terrain, history to T)
                                [lite=1&v=2&base=SEQ]: the chain of deltas from snapshot SEQ
  GET  /state_ticks.json        tests: the recorded snapshots [[tick, seq]]
  GET  /stalls.json             the stall watcher: lock holds over STALL_MS and slow-clock windows (also on stderr)
  GET  /terrain.json, /footprint.json?key=K&x=X&y=Y[&d=D]   play mode: ground images, build preview
                                (terrain.json?v=2&base=TID: a delta on terrain TID)
  GET  /trade.json              play mode: the Trade build submenu (partners without a post/dock)
  GET  /military.json           play mode: companies (standards, status), invasions (sim/military export)
  GET  /world.json              play mode: the world map (cities, routes, armies; sim/empire export)
  GET  /walker_info.json?ids=A,B  play mode: the walker window (names, thoughts, homes)
  GET  /land.json?x=X&y=Y     play mode: the land window's kind of a tile (land_kind)
  GET  /goals.json            play mode: the Goals screen's adventure/episode help records, city name (goals_info)
  GET  /maps.json             play mode: the new-game screen's maps (maps_info)
  GET  /adventures.json       play mode: the new-game screens' adventure lists (sim/campaign flow.adventures)
  GET  /campaign.json         play mode: the campaign screens (flow.screens; {"campaign": false} in open play)
  POST /campaign              JSON {"op": "start", "adventure": A[, "difficulty": D]} | {"op": "briefed"[, "difficulty": D]} |
                              {"op": "proceed"[, "colony": N]} | {"op": "stay"} | {"op": "replay"} |
                              {"op": "setaside", "goal": I} | {"op": "win"} (test command) (docs/play/campaign.md)
  GET  /options.json          play mode: difficulty (index in g_difficulty order), invaders alive (options.js)
  GET  /trade_post.json?id=B    play mode: a trading post / dock window (partner goods, quotas, orders)
  POST /control                 JSON {"save": true} | {"rate": R} | {"paused": bool} | {"new": true[, "map": M][, "difficulty": D]}
                                | {"save_as": NAME} | {"load": NAME} | {"delete": NAME}  (play mode File menu)
  GET  /saves.json              named saves (saves/play/NAME.pkl): [{name, mtime, size}], newest first
  POST /cmd                     JSON {"cmd": "build house 140 150", "tick": T} -> {"ok", "out", "tick"}
                                or {"cmds": [...], "tick": T} -> {"results": [{"ok", "out", "tick"}]} (atomic)
Script lines run in order; days/months/step wait for game time, `until STAT N [MONTHS]` waits for a
city stat (e.g. `until unemployed 40`).
"""
import bisect
import collections
import copy
import gzip
import json
import traceback
import zlib
import os
import sys
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

from . import comms, export, alerts, messages
from .systems import housing
from .game import Game, CommandError
from .serve import VIEWER
from .script import apply as script_apply

REC = 15                 # ticks between recorded frames (one tile step at normal walking speed)
SAVES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "saves", "play")
STATE_EVERY = 408        # ticks between building snapshots (8 days) when nothing was built
STATE_WALL = 0.5         # ...and at most this many wall-clock seconds (>= 2 frames apart): a guard's effect on
                         # unrest shows within a moment at any speed, not 8 game days later
CHUNK = 2040             # ticks simulated per lock hold
SHARED_IDLE = 10.0       # --shared: the city stands still once no tab has polled for this many seconds (user 11-04)
DRIVE_TIMEOUT = 1.0      # synced live: a tab that polled within this many seconds drives the clock
TIME_OPS = ("step", "wait", "days", "months", "until")
VIEWS = ("status", "look", "info", "history", "map", "catalog", "houses", "coverage", "risk", "report")


def _dumps(obj):
    return json.dumps(obj, default=int, separators=(",", ":")).encode()


def terrain(g, view):
    """Play mode (viewer/play.html): the ground images of the current state (sim/terrain_view.py, ids in
    current numbering, collection 5 = Zeus_Terrain) + elevation, flags, roads, desirability; flattened
    (index y*228+x)."""
    w = g.world
    view.update(g)
    return dict(n=int(w.flags.shape[0]), version=321, ids=view.ids.ravel().tolist(),
                draw=view.draw.ravel().tolist(), elev=w.elev.ravel().tolist(),
                flags=view.flags.ravel().tolist(), road=w.road.ravel().astype(int).tolist(),
                des=w.des.ravel().astype(int).tolist(), map_version=getattr(g, "map_version", 0),
                avenues=avenue_images(g, view),
                **{f"avenues{v}": avenue_images(g, view, v) for v in (2, 4, 6)},   # turned views (rotation.md)
                # [[tile index, image id, draw byte]]: cliff pictures of the turned views (tools/terrain_cliffs.py)
                **{f"cliffs{v}": c for v, c in getattr(view, "cliff_views", {}).items()},
                # [[tile index, d2, d4, d6]]: id deltas of the turned views for pattern-table tiles (docs/play/rotation.md)
                alt=[[y * int(w.flags.shape[0]) + x, *d] for (x, y), d in sorted(getattr(view, "alt", {}).items())],
                # [[tile index, piece]]: bridge tiles (water + road) and their FUN_0041D720 pieces (docs/logic/bridges.md)
                bridges=[[ty * int(w.flags.shape[0]) + tx, p] for (tx, ty), p in sorted(g.bridge_spans().items())],
                # the map's fishing / urchin points: the exe's effect figures there (walkers.md "Water life")
                fishing=[list(p) for p in getattr(w, "fishing_spots", None) or []],
                urchins=[list(p) for p in getattr(w, "urchin_spots", None) or []],
                # [[tile index, px]]: figures on a quarried marble tile sink 8 px (regrowth 0, deep) or 4 (100,
                # shallow): walker_draw 0x0044FEF0 (terrain 0x20000; docs/play/walkers.md "Position")
                sink=_marble_sink(view),
                # [[tile index, disaster slot, k0, k2, k4, k6]]: lava tiles (sim/disasters; FUN_00507980): k = -1 a
                # centre tile (its own SPR_LAVA picture, animated while its flow runs), else the SPR_LAVA index drawn
                # over the tile's ground per view orientation; the tint comes with the frames (`lava`)
                lava=_lava_tiles(g, view))


def _walker_step(g, w):
    """A frame's walker [8]: its current step [from_x, from_y, start tick, end tick, roaming, next x, next y], or 0.
    A stonecutter's marble cart (state follow) is moved by him (sim/systems/walkers.py gatherer: to his last tile, on
    his step's tick) and never schedules its own steps: its step lasts his (bugs.md 387: it crossed a tile in one tick,
    then stood 14, drawn ~15x too fast), its next tile is his."""
    end, nxt = getattr(w, "step_end", 0), (w.path[0] if w.path else ())
    sd = w.__dict__.get("step_draw")                 # an invader's step (sim/military/invaders._move): 15 sub-steps,
    if sd and sd[0] == w.arrived:                    # though it acts at the tile centre between
        end = sd[1]
    if w.role == "cart" and w.state == "follow":
        L = g.walkers.get(w.link)
        if L is not None and getattr(L, "arrived", None) == w.arrived:
            end, nxt = getattr(L, "step_end", 0), (L.x, L.y)
    if not w.prev or end <= w.arrived:
        return 0
    # The pass of tick v runs inside Game.step's tick v (after the cycle step, as simulation_tick), so the frame
    # recorded at v already holds a step taken in it: drawn from v - 1, the step moves between the frames v - 1
    # and v (else the renderer would slide the walker frame to frame, then jump back to the step's start).
    return [w.prev[0], w.prev[1], w.arrived - 1, end - 1, int(not w.path and w.roam_left > 0), *nxt]


def _lava_frame(g):
    if "disasters" not in g.__dict__:
        return []
    from . import disasters
    return [[o["idx"], o["state"], o["c3"]] for o in disasters._objects(disasters.state(g))
            if o["cls"] == disasters.LAVA and o["started"]]


def _lava_tiles(g, view):
    from . import disasters
    lt = disasters.lava_tiles(g)
    if not lt:
        return []
    st = disasters.state(g)
    n = int(g.world.flags.shape[0])
    slot = {}
    for o in disasters._objects(st):
        if o["cls"] == disasters.LAVA:
            for nd in o["nodes"]:
                slot[(nd["x"], nd["y"])] = o["idx"]
    out = []
    for (x, y) in sorted(lt):
        if not int(view.flags[y, x]) & 0x1000000:
            continue
        ks = getattr(view, "lava_edge", {}).get((x, y))
        out.append([y * n + x, slot.get((x, y), 0), *(ks if ks else (-1, -1, -1, -1))])
    return out


def _marble_sink(view):
    f, r = view.flags.ravel(), view.regrowth.ravel()
    return [[int(i), 8 if r[i] == 0 else 4] for i in ((f & 0x20000) != 0).nonzero()[0] if r[i] in (0, 100)]


def avenue_images(g, view, orient=0):
    """[[tile index, Zeus_General picture]] of avenue/boulevard tiles (presentation: the exe's own picture
    rule 0x004193A0 with the map's random grid; SPR_BOUL_ROAD < 288 <= side strips), for view orientation
    `orient` (0, 2, 4, 6; docs/play/rotation.md)."""
    from .systems import avenues
    w = g.world
    av = avenues.grid(w)
    if not av.any():
        return []
    n = av.shape[0]
    imgs = avenues.recompute(av, w.road.copy(), view.rand, orient)
    return sorted([y * n + x, v] for (x, y), v in imgs.items())


class _Accepted(Exception):
    pass


def _would_build(g, cmd, *args):
    """(ok, why) of the sim's own command, without doing it: it runs on a shallow copy whose spend()
    stops it. Every build command checks the site, then spends, then changes the map, so nothing changes
    (the wall/tower/gatehouse previews follow game.py's rule as it is, bugs.md 86/89)."""
    from .game import CommandError
    p = copy.copy(g)

    def stop(*a):
        raise _Accepted
    p.spend = stop
    try:
        getattr(p, cmd)(*args)
    except _Accepted:
        return True, None
    except CommandError as e:
        return False, str(e)
    return False, "no spend"           # never reached by the build commands


_WALKER_INFO = None


def _walker_table():
    global _WALKER_INFO
    if _WALKER_INFO is None:
        with open(os.path.join(os.path.dirname(VIEWER), "data", "play", "walker_info.json")) as fh:
            _WALKER_INFO = json.load(fh)
    return _WALKER_INFO


_RAND_A = {}                    # Figure+0x7C per walker id: the phrase cycle counter (advanced by each pick)


def _mood_weights(g, rural):
    """FUN_005A9550 -> bytes 0x010E4244: [w0 health, w1 food months, w2 unemployment, w3 vassal, w4 rebel] and
    whether any came from a listed band (not the 1 / 0 fallback)."""
    from .systems import health
    from . import reports
    h = health._st(g)["health"]
    c = g.city
    eaten = c.population * FOOD_RATE // 100
    months = reports.food_stored(g) // eaten if eaten else 2         # 0x00FE9570
    u = c.unemployed * 100 // c.population if c.population else 0
    w0 = 8 if h < 20 else 6 if h < 30 else 4 if h < 40 else 1
    w1 = 6 if months < 1 else 4 if months == 1 else 1
    w2 = 0 if rural else 1 if not c.population else 8 if u >= 18 else 6 if u >= 11 else 4 if u >= 6 else 1
    w = [w0, w1, w2, 0, 0]                        # w3 vassal events, w4 rebel cities: none in the sandbox
    return w, any(v > 1 for v in w[:3])


def _rng(g, wid, salt):
    """The exe draws its game RNG (rng_7 / rng_15) here; ours a stable draw per walker, picking and month."""
    import random
    return random.Random(wid * 7919 + salt * 104729 + g.tick // 816)


def city_mood(g, wid, rural=False):
    """FUN_005A96F0: the mood phrase 0 hygiene, 1 food, 2 jobs, 3 vassal, 4 rebel, 5 'could be better', 6 best.
    No problem and sentiment > 39: 6. Else r = rng_7 & tot (bitwise AND, as the exe), tot = sum w*100//S, the first
    i with r <= cumulative (4 if none); a weight-1 pick among the first three gives 5."""
    w, problem = _mood_weights(g, rural)
    if not problem and g.city.sentiment > 39:
        return 6
    S = sum(w) or 1
    parts = [v * 100 // S for v in w]
    r = _rng(g, wid, 7).randrange(128) & sum(parts)
    acc, pick = 0, 4
    for i, v in enumerate(parts):
        acc += v
        if r <= acc:
            pick = i
            break
    return 5 if w[pick] == 1 and pick <= 2 else pick


def _danger(g, w, soldier):
    """FUN_005A97A0: 0 when an enemy (invader types 40-42, 63, 64) or a threat (an unfriendly god: god_is_unfriendly;
    a bad monster, class 8: ours for FUN_00587040 / FUN_00587060) is within Chebyshev distance < 5; soldiers (types
    11-13, 39, 57) only fear threats."""
    for f in g.walkers.values():
        if f is w or f.anim == "die" or max(abs(f.x - w.x), abs(f.y - w.y)) >= 5:
            continue
        if f.role == "god":
            from . import gods
            if gods.rec(g, getattr(f, "god", 0)).get("unfriendly") == 1:
                return 0
        elif f.role == "monster":
            if getattr(f, "uclass", 8) == 8:
                return 0
        elif not soldier and f.role.startswith("enemy_") and f.role != "enemy_arrow":
            return 0
    return -1


def _cyc3(wid):
    a = _RAND_A.get(wid, 0)
    _RAND_A[wid] = 0 if a >= 2 else a + 1
    return a


def _action(g, w, t, cause):
    """FUN_005A9C20 for the sim's walkers: the exe reads the figure's action number; ours maps the walker's state
    (docs/play/info.md 'Walker window'). R50 = a 50 % draw (the exe advances its RNG: ours a stable draw)."""
    r50 = _rng(g, w.id, 15).randrange(100) >= 50
    home = g.buildings.get(w.home)
    hk = home.key if home else ""
    dest = g.buildings.get(w.target)
    out = w.state in ("go", "") and not w.returning
    if t == 1:                                    # immigrant: cycles its three lines
        return _cyc3(w.id)
    if t in (2, 22, 23, 27, 29):                  # emigrant, criminals: the worst sentiment cause
        return {1: 1, 2: 0, 3: 2, 4: 3, 5: 6, 6: 5}.get(cause, 4)
    if t == 3:                                    # vagrant: alternates
        a = _RAND_A.get(w.id, 0)
        _RAND_A[w.id] = 1 - a if a in (0, 1) else 0
        return 1 if a == 0 else 0
    if t in (4, 36):                              # cart: waiting with nowhere to go (+0x66 == 1) / a long trip
        if t == 4 and w.state == "wait":
            return 1
        if dest is not None and home is not None and max(abs(dest.x - home.x), abs(dest.y - home.y)) > 24:
            return 2
        return -1
    if t == 26:                                   # peddler: going back for supplies cycles, else after 6 picks
        if w.returning:
            return _cyc3(w.id)
        a = _RAND_A.get(w.id, 0) + 1
        _RAND_A[w.id] = a
        return 3 if a > 5 else -1
    if t == 8:                                    # superintendent: at a fire cycles, else R50 -> 4
        if w.state == "ext":
            return _cyc3(w.id)
        return 4 if r50 else -1
    if t == 32:                                   # healer: city health < 40
        from .systems import health
        return 0 if health._st(g)["health"] < 40 else -1
    if t == 37:                                   # agora vendor (our buyer): collecting 0 / returning 1
        return 1 if w.returning else 0
    if t == 47:
        return _cyc3(w.id)
    if t == 61:                                   # watchman: fighting 3/4, else the unrest he sees (+0x66)
        if w.anim == "fight":
            return 4
        u = max((getattr(b, "crime", 0) for b in g.buildings.values() if b.kind == "house"
                 and abs(b.x - w.x) <= 2 and abs(b.y - w.y) <= 2), default=0)
        return 0 if u < 10 else 1 if u < 50 else 2
    if t == 58:                                   # artisan: walking 0, at the site 1 (pyramids 2 / 3)
        pyr = dest is not None and dest.key.startswith("pyramid")
        if w.state == "go":
            return (2 if pyr else 0) if r50 else -1
        return (3 if pyr else 1) if r50 else -1
    if t == 5:                                    # grower: tending 0 / 2, picking 1 / 3 (olive / vine)
        vine = "grape" in (w.good or "") or hk == "growers_lodge" and getattr(w, "task", "") and "vine" in w.task
        if w.task == "tend":
            return (2 if vine else 0) if r50 else -1
        if w.task == "pick":
            return (3 if vine else 1) if r50 else -1
        return -1
    if t in (30, 31):                             # shepherd / goatherd: out 0, working 1/2, back 3
        if not r50:
            return -1
        return 3 if w.state == "back" else 1 if w.state == "work" else 0
    if t == 53:                                   # hunter: back with meat 1, else 0
        return (1 if w.state == "back" else 0) if r50 else -1
    if t == 55:                                   # woodcutter: back 1, out / cutting 0
        return (1 if w.state == "back" else 0) if r50 or w.state == "work" else -1
    if t == 62:                                   # miner / stonecutter: out 0, back 1
        if w.state == "work":
            return 2 if hk in ("foundry", "mint") else -1
        return (1 if w.state == "back" else 0) if r50 else -1
    if t == 25:                                   # fishing boat
        return {"fish": 2, "go": 0, "unload": 3, "back": 1}.get(w.state, -1) if r50 else -1
    if t == 44:                                   # urchin gatherer
        return {"go": 0, "work": 3, "back": 1}.get(w.state, -1) if r50 else -1
    if t == 66:
        return 0
    if t == 65:                                   # priest (0x41): to the offering (action 7) by its kind: goat 0,
        kind = getattr(g.walkers.get(w.target), "role", "") if w.state == "animal" else w.good   # sheep 1, cattle 4;
        if w.state == "animal":                   # leading it to the altar (action 10): goat 2, sheep 3, cattle 5
            return 0 if kind == "goat" else 1 if kind == "sheep" else 4
        if w.state == "altar":                    # (ours: an offering from storage has no phrase)
            return {"goat": 2, "sheep": 3, "cattle": 5}.get(kind, -1)
        return -1
    if t == 77:                                   # rancher
        return {"go": 0, "work": 1, "back": 2}.get(w.state, -1)
    return -1


SOLDIERS = (11, 12, 13, 39, 57)
RURAL_HOMES = ("fruit_lodge", "orichalc_refinery")


def walker_phrase(g, w, t, ft, cause):
    """FUN_005ABB90: Figure+0x7D. flag_a (danger) and flag_b (mood) bytes of the figure type table 0x00639698:
    danger d -> d + 7*flag_b; else action a -> a + 7*flag_b + flag_a; else with flag_b the city's mood."""
    fa, fb = int(bool(ft.get("danger"))), int(bool(ft.get("mood")))
    if fa:
        d = _danger(g, w, t in SOLDIERS)
        if d != -1:
            return d + 7 * fb
    a = _action(g, w, t, cause)
    if a != -1:
        return a + 7 * fb + fa
    if fb:
        home = g.buildings.get(w.home)
        rural = (home is not None and home.key in RURAL_HOMES) or t in (72, 73, 74, 75, 77)
        return city_mood(g, w.id, rural)
    return -1


def fig_type(g, w, T):
    """The exe figure type of a walker: the role's (walker_info.json), a cart from a storage is a deliveryman (36)."""
    t = T["roles"].get(w.role)
    if w.role in ("cart", "buyer"):
        home = g.buildings.get(w.home)
        if home is not None and home.kind in ("storage", "trade"):
            return 36
    return t


GONE_KEEP = 3000                # ticks a removed walker still answers the walker window (Runner.gone_walkers)


def walker_info(g, ids, gone=None):
    """Play mode's walker window (docs/play/info.md "Walker window"): per walker id (alive, or removed lately:
    `gone` {id: (tick, walker)}, Runner.gone_walkers -- the exe's window reads the figure slot, whose data stays
    after the figure is gone; ours asks the server, which runs ahead of the tab's playhead), its exe figure
    type, name (group, index; ours: id % group size, the exe counts names per group at creation), thought
    [group, phrase] (FUN_005ABB90, picked when the window opens: the client asks once), and what the type's own
    lines need (0x005740A0): home and destination building keys, returning, carried good and amount, the goods a
    peddler / buyer carries or sells, a trader's city and stage, a miner's kind."""
    T = _walker_table()
    from .systems import finance
    parts = finance.sentiment_parts(g)
    cause = finance.worst_cause(parts)
    out = []
    for wid in ids:
        w = g.walkers.get(wid)
        was = w is None and bool(gone) and wid in gone
        if was:
            w = gone[wid][1]
        if w is None:
            continue
        t = fig_type(g, w, T)
        ft = T["types"].get(str(t), {}) if t is not None else {}
        if t in (67, 68, 69):                     # gods, monsters, heroes: their own lines (0x005740A0 0x43..0x45)
            out.append(_figure_info(g, w, t, ft, T))
            if was:
                out[-1]["gone"] = True
            continue
        home = g.buildings.get(w.home)
        ng = T.get("name_by_home", {}).get(home.key if home else "", {}).get(str(t), ft.get("name_group", -1))
        tg = T.get("thought_by_home", {}).get(home.key if home else "", {}).get(str(t), ft.get("thought_group", -1))
        names = T["texts"].get(str(ng), [])
        thought = None
        weights = None
        if tg > 0:
            ph = walker_phrase(g, w, t, ft, cause)
            if ph >= 0:
                thought = [tg, ph]
            if ft.get("mood"):                    # the 'Tell me more' button's weights (0x010E4244)
                home_ = g.buildings.get(w.home)
                weights = _mood_weights(g, (home_ is not None and home_.key in RURAL_HOMES) or t in (72, 73, 74, 75, 77))[0]
        dest = g.buildings.get(w.target)
        d = dict(id=wid, role=w.role, type=t, name=[ng, w.name % len(names) if w.role == "trireme" and isinstance(getattr(w, "name", None), int)
                                     else wid % len(names)] if names else None,
                 thought=thought, home=home.key if home else "", dest=dest.key if dest else "",
                 returning=bool(w.returning or w.state == "back"), good=w.good, amount=w.amount,
                 load={k: v for k, v in (w.load or {}).items() if isinstance(v, int) and v > 0}, state=w.state,
                 weights=weights)
        if w.role == "peddler" and home is not None:   # the goods its agora has in stock (icons)
            d["sells"] = [k for k in ("food", "fleece", "olive_oil", "wine", "armor", "horses")
                          if (sum(home.goods.get(f, 0) for f in g.cat.foods) if k == "food" else home.goods.get(k, 0)) > 0]
        if w.role in ("trader", "ship"):          # the city (Figure+0x6E), its goods with quota, this visit's ledger
            from .systems import trade
            c = int(w.good) if str(w.good).isdigit() else (home.misc.get("partner") if home is not None else None)
            parts = trade.partners(g)
            p = parts[c] if c is not None and 0 <= c < len(parts) else {}
            used = trade.state(g)["used"][c] if p else {}
            d["city"] = p.get("name", "")
            d["buys"] = [k for k, q in p.get("buys", {}).items() if used.get(k, 0) < q]      # city_has_quota
            d["sells"] = [k for k, q in p.get("sells", {}).items() if used.get(k, 0) < q]
            led = w.load or {}
            d["bought"] = dict(led.get("ledger_out", {}))                                  # 0x008F9868: our exports
            d["sold"] = dict(led.get("ledger_in", {}))                                     # 0x008F988C: our imports
            d["load"] = {}
        if was:
            d["gone"] = True
        out.append(d)
    return out


def _figure_info(g, w, t, ft, T):
    """A god's (sim/gods walker_window), monster's or hero's (sim/heroes walker_window) window record: res = its id
    (Figure+0x60), thought [group by id (FUN_004E3750), phrase] (FUN_005ABB90: a god's / monster's action phrase; a
    hero (both flags): danger 7, a monster on the way 8, else the city's mood), the god's unfriendly byte (83:k)."""
    if t == 67:
        from . import gods
        x = gods.walker_window(g, w)
        res, ph = x["god"], x["phrase"]
    else:
        from . import heroes
        x = heroes.walker_window(g, w)
        res = x.get("monster", x.get("hero", 0))
        ph = x.get("phrase", -1)
    weights = None
    if t == 69:
        d0 = _danger(g, w, False)
        ph = d0 + 7 if d0 != -1 else 8 if x.get("warned") else city_mood(g, w.id, False)
        weights = _mood_weights(g, False)[0]
    tg = T.get("thought_by_res", {}).get(str(t), {}).get(str(res), -1)
    return dict(id=w.id, role=w.role, type=t, res=res, unfriendly=x.get("unfriendly"),
                thought=[tg, ph] if tg > 0 and ph >= 0 else None, name=None, weights=weights,
                home="", dest="", returning=False, good=None, amount=0, load={}, state=getattr(w, "state", ""))


def pak_records(path):
    """A map's adventure and episode-0 Zeus_MM.eng records from its .pak header (see goals_info); -1 when none."""
    import struct
    adv = ep = -1
    if str(path).endswith(".pak") and os.path.exists(path):
        with open(path, "rb") as f:
            d = f.read(0x8B44)
        if len(d) >= 0x8B44:
            adv = struct.unpack_from("<i", d, 0x8B40)[0]
        ep = struct.unpack_from("<i", d, 0x1BE4 + 0x64C)[0]
    return adv, ep


def maps_info():
    """The new-game screen's map list (viewer/play/newgame.js): every map of data/maps.json with its default
    difficulty (index in DIFFICULTIES) and its adventure / episode records (names, description, briefing)."""
    from .data import DIFFICULTIES
    from .world import MAP_INFO, MAPS
    out = []
    for k, v in MAP_INFO.items():
        adv, ep = pak_records(MAPS[k])
        d = v.get("difficulty", "Normal")
        e = dict(key=k, file=os.path.basename(MAPS[k]), adventure=adv, episode=ep,
                 difficulty=DIFFICULTIES.index(d) if d in DIFFICULTIES else 2)
        if v.get("ours"):                   # ours (data/maps.json "map": the map without its episode): own name
            e.update(ours=True, name=v.get("title", k), note=v.get("note", ""))
        # a custom (Poseidon editor) adventure keeps its texts in DIR/NAME.txt: Adventure_Title, ..._Introduction,
        # Parent_Episode_1_Title / _Introduction (the editor's text file, "key=quoted text")
        txt = [os.path.join(os.path.dirname(MAPS[k]), f) for f in os.listdir(os.path.dirname(MAPS[k]))
               if f.endswith(".txt")] if adv < 0 else []
        if txt:
            import re
            kv = dict(re.findall(r'^(\w+)="(.*?)"', open(txt[0], encoding="latin-1").read(), re.M | re.S))
            e.update(title=kv.get("Adventure_Title", ""), intro=kv.get("Adventure_Introduction", ""),
                     episode_title=kv.get("Parent_Episode_1_Title", ""),
                     episode_text=kv.get("Parent_Episode_1_Introduction", ""))
        out.append(e)
    return out


def goals_info(g):
    """The Goals screen (objectives_screen_draw 0x0052C070) for play mode: the adventure's title record (+0x8B40 of
    the adventure object, FUN_0042B810), the episode's record (+0x64C of episode 0 at +0x1BE4, FUN_0042B640 title /
    FUN_0042B5E0 body; Zeus_MM.eng record numbers), read from the map's .pak header (formats/set.md: same offsets in
    the file), the player city's name, and the goals (none: open play). Maps without a .pak (a bare .map): no texts."""
    if g.__dict__.get("campaign"):             # a campaign: the episode's records and its goal rows (sim/campaign)
        from .campaign import flow
        d = flow.screens(g)
        return dict(adventure=d["brief"], episode=d["intro"], city=d["city"], goals=d["goals"], campaign=True,
                    strings=d.get("strings"), tutorial=d.get("tutorial"))
    from .world import MAPS, map_path
    adv, ep = pak_records(map_path(g.map_name)[0])
    emp = getattr(g, "empire", None)
    city = ""
    try:
        city = emp.player().name if emp else ""
    except StopIteration:
        pass
    return dict(adventure=adv, episode=ep, city=city, goals=[])


def campaign_screen(g):
    """The campaign screen up on a campaign game (sim/campaign flow.screen), else None. The live server calls the
    campaign module; the sim core never does (docs/campaign-format.md "The campaign module")."""
    from .campaign import flow
    return flow.screen(g)


def campaign_key(g):
    """meta.campaign of /frames.json: changes whenever the campaign screens must be fetched again (/campaign.json)."""
    st = g.__dict__.get("campaign")
    if not st:
        return None
    from .campaign import flow
    tl = flow.top_left(g)                      # the city's top-left lines change monthly
    return (f"{st['adventure']}|{st['slot']}|{st['result']}|{campaign_screen(g)}|{len(st['goals'])}"
            f"|{tl['won']}|{tl.get('kind')}|{tl.get('months')}")


def land_kind(g, x, y):
    """The land window's kind for a tile with no building (FUN_005717D0's terrain chain -> 0x00FFA138; title
    70:(k+10), text 70:(k+41), drawn by FUN_005731D0): 1 trees, 2 rock (0x10 copper, 0x11 silver, 0x1F orichalc),
    3 water (0x1B fishing spot, 0x1A urchin spot within one tile), 6 road, 7 marble quarry (0x1E black marble),
    8 rubble (the ruin panel), 0xA empty land, 0xB water crossing (a bridge tile), 0xE / 0xF the map entry / exit
    road, 0x13 beach, 0x14 submerged beach, 0x15 marsh, 0x18 wall (panel 166), 0x19 meadow, 0x1D lava.
    None: a building's own window. Ours: cracks (5, earthquake pieces) and park terrain (0xC: gardens are
    buildings here) never come up."""
    w = g.world
    if not w.inside(x, y):
        return None
    f = int(w.flags[y, x])
    b = g.buildings.get(int(w.occ[y, x]))
    if b is not None:
        if b.key == "bridge":                    # bridges are terrain in the exe (grid 0x00CB4B08): 0xB on water
            return 0xB if f & 0x4 else 0xA
        if b.key == "wall":
            return 0x18
        if not (b.kind == "agora" and w.road[y, x]):
            return None                          # a road through an agora is road land (0x40 and the agora)
    if f & 0x1 and b is None:
        return 0x1
    if f & 0x120000 == 0x120000:
        return 0x1E
    if f & 0x120000 == 0x20000:
        return 0x7
    r = f & 0x300002
    if r:
        if (x, y) == tuple(w.entry):
            return 0xE
        if (x, y) == tuple(w.exit):
            return 0xF
        return {0x100002: 0x10, 0x200002: 0x11, 0x300000: 0x1F}.get(r, 0x2)
    if f & 0x4 and not f & 0x10008:
        for sx, sy in getattr(w, "fishing_spots", []) or []:
            if abs(sx - x) <= 1 and abs(sy - y) <= 1:
                return 0x1B
        for sx, sy in getattr(w, "urchin_spots", []) or []:
            if abs(sx - x) <= 1 and abs(sy - y) <= 1:
                return 0x1A
        return 0x3
    if f & 0x1000000:
        return 0x1D
    if f & 0x40 or w.road[y, x]:
        return 0x6
    if f & 0x1000:
        return 0x8
    if f & 0x40000:
        return 0x15
    if f & 0x4000:
        return 0x18
    if f & 0x10004 == 0x10000:
        return 0x13
    if f & 0x10000:
        return 0x14
    if f & 0x800:
        return 0x19
    return 0xA


def trade_post(g, bid):
    """Play mode's trading post / dock window (docs/play/info.md "Trade window"): the bound partner, what it
    sells (we import) and buys (we export) with the yearly quota and this year's count, the post's orders,
    limits and stock, the prices. Read only; the clicks send `trade X Y GOOD import|export|off [LIMIT]`."""
    from .systems import trade
    b = g.buildings.get(bid)
    if b is None or b.kind != "trade":
        return {}
    c = b.misc.get("partner")
    p = trade.partners(g)[c] if c is not None else {}
    used = trade.state(g)["used"][c] if c is not None else {}
    goods = (set(p.get("buys", {})) | set(p.get("sells", {}))) - set(trade.NOT_TRADED)   # 0x005B12C0: no horses/chariots
    return dict(id=bid, partner=p.get("name", ""), route=p.get("route", ""),
                sells={k: v for k, v in p.get("sells", {}).items() if k in goods},
                buys={k: v for k, v in p.get("buys", {}).items() if k in goods}, used={k: used.get(k, 0) for k in goods},
                orders={k: trade.order(g, b, k) for k in goods}, limits={k: trade.limit(g, b, k) for k in goods},
                prices={k: trade.price(g, k) for k in goods}, goods=dict(b.goods),
                capacity=g.cat.spec(b.key).get("capacity", trade.DEFAULT_LIMIT),
                units={k: trade.unit(g, k) for k in goods})


def advisor(g, a):
    """Play mode: the data of advisor screen `a` (docs/play/advisors.md). 1 = labor: per category need / have /
    priority (g_labor_cat 0x00FE9584, rows of FUN_00590920; ours: labor.allocate's labor_jobs) and the
    industries the city has producers of, with their shut-down flag (FUN_00590C30, g_industry_halted)."""
    from .systems import labor
    if a in ADVISOR_DATA:
        return dict(advisor=a, **ADVISOR_DATA[a](g))
    if a != 1:
        return dict(advisor=a)
    jobs = getattr(g, "labor_jobs", None) or {}
    pr = labor.priorities(g)
    cats = [dict(need=jobs.get(c, [0, 0])[0], have=jobs.get(c, [0, 0])[1], priority=pr[i])
            for i, c in enumerate(labor.CATEGORIES)]
    have = set()                                  # 0x0091EB58[res] > 0: some building produces it
    for b in g.buildings.values():
        out = g.cat.spec(b.key).get("output")
        if out:
            have.add("meat_beef" if b.key == "corral" else out)
    off = getattr(g, "industry_off", None) or set()
    c = g.city
    return dict(advisor=1, cats=cats, industries={k: (k in off) for k in have}, workforce=c.workforce,
                employed=c.employed, unemployed=c.unemployed)


def _count(g, key):
    return sum(1 for b in g.buildings.values() if b.key == key)


def _people(g, test=lambda b: True):
    return sum(b.occupants for b in g.buildings.values() if b.kind == "house" and b.occupants and test(b))


def _adv_hygiene(g):
    """Advisor 8 (FUN_00594080): g_city_health 0x00FE6A70, people with a healer 0x00FE6A84 and fed 0x00FE6A80
    (house populations summed, sentiment.md), outbreaks this month 0x00FEB528, infected houses 0x00FEB524,
    maintenance offices / watchposts (building counts 0x00782A6C / 0x00782A78), crimes this month (vandalism
    0x00FEAEE6, thefts 0x00FEAEE4, muggings 0x00FE96D8). Ours: the month's crimes = the totals minus the totals
    at the last month end."""
    from .systems import health
    st = health._st(g)
    c = g.city
    last = g.history[-1] if g.history else {}
    month = lambda k: getattr(c, k, 0) - last[k] if k in last else 0      # 0 until a month closed with the totals
    return dict(health=st["health"], population=c.population,
                healer=_people(g, lambda b: b.coverage.get("healer")), fed=_people(g, lambda b: b.fed),
                plagues=st.get("this_month", 0),
                infected=sum(1 for b in g.buildings.values() if b.kind == "house" and b.misc.get("infected")),
                maintenance=_count(g, "maintenance"), watchposts=_count(g, "guardpost"),
                vandalisms=month("vandalisms"), thefts=month("thefts"), muggings=month("muggings"))


def _adv_culture(g):
    """Advisor 10 (FUN_00594B70): venue counts (building counts 0x007829CC podium, C4 gymnasium, D0 theatre, C8
    stadium) and coverage 0x0091EA74.. = people in houses the service reaches * 100 / people in houses
    (FUN_00566A90): philosophy, athletics, drama."""
    P = _people(g)
    cov = {s: _people(g, lambda b, s=s: b.coverage.get(s)) * 100 // P if P else 0
           for s in ("philosophy", "athletics", "drama")}
    return dict(counts={k: _count(g, k) for k in ("podium", "gymnasium", "theatre", "stadium")}, coverage=cov)


FIN_LINES = ("taxes", "exports", "gifts", "mint", "tribute_in", "races",
             "imports", "wages", "construction", "tribute_out", "aid")


def _adv_finance(g):
    """Advisor 12 (finance_advisor_draw 0x005951F0): last year / so far this year per line. Ours: the sim's
    monthly ledgers (finance.month_end keeps each closed month in g.history with its month index) summed per
    calendar year, plus the running month; expenses as positive amounts as the exe shows them. Gifts, tribute
    and aid are not simulated (0)."""
    c = g.city
    y = g.month_index // 12

    def year(rows):
        out = dict.fromkeys(FIN_LINES, 0)
        for led in rows:
            for k, v in led.items():
                if k in out:
                    out[k] += abs(v)
        return out
    hist = [h for h in g.history if "mi" in h]
    this = year([h["ledger"] for h in hist if h["mi"] // 12 == y] + [c.ledger])
    prev = year([h["ledger"] for h in hist if h["mi"] // 12 == y - 1])
    end = [h["treasury"] for h in hist if h["mi"] // 12 == y - 1]
    return dict(last=prev, this=this, balance=[end[-1] if end else 0, c.treasury], last_known=bool(end))


# --- advisors 9, 11, 7, 15, 6, 13, 2 (docs/play/advisors.md) -----------------------------------------------------

# husbandry rows: exe resource 1..8 -> our producer keys (the source table 0x00F9FA58 is indexed by resource);
# corrals (resource 24) follow resource 3 (FUN_00597720)
FOOD_SRC = [(1, ("urchin_quay",)), (2, ("fishing_wharf",)), (3, ("hunting_lodge",)), (4, ("goat_farm",)),
            (5, ("carrot_farm",)), (6, ("onion_farm",)), (7, ("wheat_farm",)), (8, ("fruit_tree",))]
FOOD_RATE = 25                                     # food_consumption_rate 0x004E5EF0: units per 100 people a month


def _working(g, keys):
    """0x0091EAC8[res]: buildings of the type with workers (buildings_count_by_type 0x00491820); ours: types
    that need no staff count when they stand."""
    n = 0
    for b in g.buildings.values():
        if b.key in keys:
            need = g.cat.spec(b.key).get("employees", 0)
            n += 1 if (b.employees > 0 or not need) else 0
    return n


def food_supply(g):
    """The husbandry advisor's table (exe FUN_00518FF0 fills 0x00F9FA58 with an estimate per source: count,
    loads x 100 a month, people = (100 / 25) x loads; imports from FUN_00518E40). Ours: the average of the
    closed months in g.history (up to 12; food_src / food_imp, recorded since 10-28): units a source's carts took
    away, units imported by traders."""
    hist = [h for h in g.history if "food_src" in h][-12:]
    per = 100 // FOOD_RATE
    src = {}
    for h in hist:
        for k, v in h["food_src"].items():
            src[k] = src.get(k, 0) + v
    if not hist:                                    # saves from before 10-28: output per good (produced_hist), each
        ph = getattr(g, "produced_hist", [])[-12:]  # good given to its first source with a working building
        for m in ph:
            for good, v in m.items():
                for k in [k for k, sp in g.cat.buildings.items() if sp.get("output") == good and _working(g, (k,))][:1]:
                    src[k] = src.get(k, 0) + v
        hist = ph
    n = len(hist) or 1
    imp = {}
    for h in hist:
        for k, v in h.get("food_imp", {}).items():
            imp[k] = imp.get(k, 0) + v
    rows = []
    for res, keys in FOOD_SRC:
        cnt = _working(g, keys)
        if cnt:
            u = sum(src.get(k, 0) for k in keys) // n
            rows.append(dict(res=res, count=cnt, text=[57, 31 + res], units=u, people=per * u))
        if res == 3:
            cnt = _working(g, ("corral",))
            if cnt:
                u = src.get("corral", 0) // n
                rows.append(dict(res=24, count=cnt, text=[57, 40], units=u, people=per * u))
    from .empire.model import GOOD_IDS
    imports = []
    for k, rid in sorted(((k, GOOD_IDS[k]) for k in imp if k in GOOD_IDS), key=lambda t: t[1]):
        u = imp[k] // n
        if u:
            imports.append(dict(res=rid, units=u, people=per * u))
    return dict(rows=rows, imports=imports, months=len(hist))


def _adv_husbandry(g):
    return food_supply(g)


GODS = ("zeus", "poseidon", "demeter", "apollo", "artemis", "ares", "aphrodite", "hermes", "athena", "hephaistos",
        "dionysus", "hades", "hera", "atlas")
MATERIAL_TEXT = {"sculpture": 0x22, "marble": 0x23, "black_marble": 0x24, "wood": 0x25, "orichalc": 0x26}


def _sanctuary_state(g, b):
    """FUN_004F0130 (param 0 = the advisor's long texts, group 59) -> (text id, font rank, percent).
    Complete: no staff -> 0x1C needs priests (rank 4); active (sim/gods) -> the god's mood FUN_004F00A0 by
    prayer counter - help threshold d: > 36 0x13 (rank 4), > 24 0x14, > 12 0x15, > 6 0x16, 4..6 0x17, 1..3 0x18,
    < 1 0x19 (rank 5); not active: no priest out 0x1D needs sacrifice (rank 5), else 0x1E preparing (rank 4).
    Building: the monument's reason (needs <material> / artisans), else 'Sanctuary is N % complete' (0x20, rank 5)."""
    from .systems import monuments
    from . import gods
    try:
        done = monuments.progress(b)
    except (KeyError, TypeError):
        done = b.misc.get("built", 0)
    if done >= 100:
        if b.employees <= 0:
            return 0x1C, 4, done                         # needs priests
        i = gods.god_of(b)
        if gods.on(g) and 0 <= i < 14:
            if not gods.active(g, i):
                out = any(w in g.walkers and g.walkers[w].role == "priest" for w in b.walkers)
                return (0x1E, 4, done) if out else (0x1D, 5, done)
            d = gods.rec(g, i)["prayer"] - gods.T()["help_threshold"][i]
            t = 0x13 if d > 36 else 0x14 if d > 24 else 0x15 if d > 12 else 0x16 if d > 6 else \
                0x17 if d >= 4 else 0x18 if d >= 1 else 0x19
            return t, (5 if d < 37 else 4), done
        return 0x19, 5, done
    r = b.reason or ""
    if "artisan" in r:
        return 0x27, 4, done
    for good, t in MATERIAL_TEXT.items():
        if f"needs {good}" in r:
            return t, 4, done
    return 0x20, 5, done


def _adv_mythology(g):
    """Advisor 11 (FUN_00596FB0, counts FUN_00595F20): sanctuaries of the gods that are not unfriendly (first per
    god, at most min(scenario +0xDC, 4)), 'others' = the other gods that are not unfriendly (absent ones count,
    hence the frame height), listed by name: no sanctuary and friendly (scenario slot 12..23); unfriendly gods
    (slots 0..11) with FUN_004F0AE0's text: 0x41 'has unleashed' when its monster is on the map, 0x33 + god
    'X is attacking the city' when the god is on the map, else none (ustate -1). Heroes: track 1I."""
    from . import gods
    from .gods import figures as gods_figures
    st = gods.state(g)
    cap = 4 if st.get("free") else min(st["max_sanct"], 4)
    sanct, others, friendly, unfriendly, ustate = [], 0, [], [], []
    for i, god in enumerate(GODS):
        r = gods.rec(g, i)
        if r["unfriendly"] == 1:
            unfriendly.append(i)
            w = gods_figures.figure(g, i)
            ustate.append(0x33 + i if w is not None else -1)
            continue
        b = gods.sanctuary(g, i)
        if b is not None and len(sanct) < cap:
            t, f, p = _sanctuary_state(g, b)
            sanct.append(dict(god=i, text=t, font=f, pct=p))
            continue
        others += 1
        if b is None and r["unfriendly"] == 0:
            friendly.append(i)
    return dict(sanctuaries=sanct, others=others, friendly=friendly, unfriendly=unfriendly, ustate=ustate, heroes=0)


def _adv_population(g):
    """Advisor 7 (FUN_00593740): history = the monthly population (g_population_history, 2400 months; ours:
    g.history), society = people per house level 0..12 (0x00FE90E4, FUN_00593D20)."""
    levels = [0] * 13
    for b in g.buildings.values():
        if b.kind == "house" and b.occupants and 0 <= b.level < 13:
            levels[b.level] += b.occupants
    return dict(history=[h.get("population", 0) for h in g.history][-2400:], levels=levels,
                start_year=g.start_year, year=g.year, month=g.month)


def _god_of_statue(v):
    """FUN_0051B9D0: god statue variant -> god (1..13; 157:god)."""
    for g, vs in enumerate(((), (0xB, 0x17, 0x27, 0x33), (0xC, 0x18, 0x28, 0x34), (0xD, 0x19, 0x29, 0x35),
                            (0xE, 0x1A, 0x2A, 0x36), (0xF, 0x1B, 0x2B, 0x37), (0x10, 0x1C, 0x2C, 0x38),
                            (0x11, 0x1D, 0x2D, 0x39), (0x12, 0x1E, 0x2E, 0x3A), (0x13, 0x1F, 0x2F, 0x3B),
                            (0x14, 0x20, 0x30, 0x3C), (0x15, 0x21, 0x31, 0x3D), (0x22, 0x24, 0x3E, 0x40),
                            (0x23, 0x25, 0x3F, 0x41))):
        if v in vs:
            return g
    return 0


COMM_TEXT = {1: 5, 2: 7, 3: 10, 5: 8, 6: 11, 7: 6, 8: 9, 9: 12, 4: 13}     # wm_sub_4663b0: variant -> 133:k


def _adv_aesthetics(g):
    """Advisor 15 (FUN_00596180): pyramids (Poseidon scenario goals: none here) and the commemorative monuments
    placed (g_commemorative_placed[variant]; ours misc 'variant', 1 when unset as sim/systems/commemorative.py),
    in the exe's order: variants 1..8 but 4, then god statues per god (10..65 -> 157:god), then 9, then 4.
    Lines: [group, index, count]."""
    placed = {}
    for b in g.buildings.values():
        if b.key == "commemorative_monument":
            v = int(b.misc.get("variant", 1))
            placed[v] = placed.get(v, 0) + 1
    lines = [[133, COMM_TEXT[v], placed[v]] for v in (1, 2, 3, 5, 6, 7, 8) if placed.get(v)]
    gods = {}
    for v, n in placed.items():
        if v >= 10 and _god_of_statue(v):
            gods[_god_of_statue(v)] = gods.get(_god_of_statue(v), 0) + n
    lines += [[157, k, gods[k]] for k in sorted(gods)]
    lines += [[133, COMM_TEXT[v], placed[v]] for v in (9, 4) if placed.get(v)]
    return dict(lines=lines, pyramids=[])


def _adv_trade(g):
    """Advisor 6 (FUN_005BAD80 / FUN_005BAEF0): goods list (rebuild_goods_lists 0x005BAAF0: a partner sells it,
    the city can make it or holds stock; at most 17), price, state per good (FUN_00460E30 a trading partner sells
    it with quota left, FUN_00460F10 buys it), and the cities a post imports from (5) / exports to (7)
    (0x01607E68 table, filled from the posts' orders; imports only from a trading partner)."""
    from .systems import trade
    from . import empire
    from .empire.model import GOOD_IDS
    parts = trade.partners(g)
    st = trade.state(g)
    prices = {k: trade.price(g, k) for k in g.cat.trade["prices"]}
    have = set()
    for b in g.buildings.values():
        if b.kind in ("storage", "trade") and not g.cat.spec(b.key).get("endless"):
            have |= {k for k, v in b.goods.items() if v > 0}
        out = g.cat.spec(b.key).get("output")
        if out:
            have.add(out)
    from . import allowed
    gl = set(allowed.goods_list(g)) if allowed.table(g) is not None else None   # ours, sandbox_open: as before
    rows = []
    for k, rid in sorted(GOOD_IDS.items(), key=lambda t: t[1]):
        if rid > 22:
            continue
        sells = any(p.get("sells", {}).get(k, 0) > st["used"][c].get(k, 0) and empire.trading(g, c)
                    for c, p in enumerate(parts))
        buys = any(p.get("buys", {}).get(k, 0) > st["used"][c].get(k, 0) and empire.trading(g, c)
                   for c, p in enumerate(parts))
        listed = (k in gl if gl is not None else
                  k in have or any(k in p.get("sells", {}) or k in p.get("buys", {}) for p in parts))
        if not listed:
            continue
        state, cities = 9, []
        for b in sorted((b for b in g.buildings.values() if b.kind == "trade"), key=lambda b: b.id):
            o = trade.order(g, b, k)
            c = b.misc.get("partner")
            if c is None:
                continue
            if o == "export" or (o == "import" and empire.trading(g, c)):
                state = 7 if o == "export" else 5
                cities.append(dict(name=parts[c]["name"], partner=bool(empire.trading(g, c)), post=[b.x, b.y]))
        rows.append(dict(res=rid, key=k, price=prices.get(k, 0), state=state, sells=sells, buys=buys, cities=cities))
    return dict(goods=rows[:17])


def _adv_overview(g):
    """Advisor 13 (FUN_005B7760): the per-topic status texts (group 61) by the exe's rules; numbers here."""
    from .systems import finance, labor
    from . import reports
    c = g.city
    parts = finance.sentiment_parts(g)
    cause = finance.worst_cause(parts)             # g_sentiment_worst_cause: 1 food .. 5 debt, 6 called to arms
    hs = [b for b in g.buildings.values() if b.kind == "house"]
    from .systems import housing
    room = sum(max(0, housing.capacity(g, b) - b.occupants) for b in hs if b.access is not None)
    eaten = c.population * FOOD_RATE // 100
    sup = food_supply(g)
    produced = sum(r["units"] for r in sup["rows"]) + sum(r["units"] for r in sup["imports"])
    stored = reports.food_stored(g)
    jobs = getattr(g, "labor_jobs", None) or {}
    unfilled = sum(max(0, n - f) for n, f in jobs.values())
    unemp = c.unemployed * 100 // c.workforce if c.workforce else 0
    from .systems import health
    common = [b for b in hs if b.occupants]
    hi = sum(1 for b in common if getattr(b, "crime", 0) >= 81)
    mid = sum(1 for b in common if 71 <= getattr(b, "crime", 0) <= 80)
    any51 = any(getattr(b, "crime", 0) >= 51 for b in common)
    start_t = g.year_treasury                     # _DAT_00fe971c (FUN_005B6730's finances line)
    P = _people(g)
    # FUN_00566A90's four coverages (0x0091EA74/78/7C philosophy, athletics, drama; 0x0091EA70 = house +0x6C, the
    # competitor / curator coverage: competition), averaged by the overview's culture line (0x005B6830)
    cov = [(_people(g, lambda b, s=s: b.coverage.get(s)) * 100 // P if P else 0)
           for s in ("philosophy", "athletics", "drama", "competition")]
    # the culture line rates the next Panhellenic games when the map has them (FUN_005B6830: 0x00902C50 != -1 and not
    # a Poseidon game): year type (year + 1 from August) & 3 -> FUN_00565D40 (games.chance, without Hercules' term)
    from .systems import games as _games
    gm = None
    if _games.OFFSET != -1:
        t = _games.year_type(g)
        gm = [t, _games.chance(g, t)]
    from . import scenario
    reqs = scenario.request_rows(g)        # request_list_rebuild 0x00483040's list: requests, then quests
    try:
        from .empire import events
        e = getattr(g, "empire", None)
        inv = bool(e is not None and events.live(g, "invasion"))
    except Exception:
        inv = False
    return dict(sentiment=c.sentiment, cause=cause, immigrants=getattr(c, "immigrants_month", 0), room=room,
                migration=getattr(c, "migration", 0), eaten=eaten, produced=produced, stored=stored,
                months=(stored // eaten if eaten else (1 if stored > 0 else 0)), unemployment=unemp,
                unfilled=unfilled, health=health._st(g)["health"], unrest=dict(houses=len(common), high=hi, mid=mid,
                any=any51), treasury=c.treasury, year_start=start_t, culture=cov, games=gm, invasion=inv,
                requests=reqs)


def _adv_military(g):
    """Advisor 2 (FUN_00591C30): the palace companies by type (records 0x00DB7BDC, slots 1..20; ours
    military.companies), their banner (text 138) and status (FUN_00591610: at home 51:18 for ours: no company
    is ever mobilized), the navy (trireme wharves, type 0x88), mercenaries (none), mythical warriors (sanctuary companies 31..34), and the
    three report lines (soldiers, companies, triremes; threats; requests)."""
    from .systems import military as mil
    from . import military as military_map
    from .military import forces as mforces
    comps = mil.companies(g)
    rows = []
    mythical = []
    for s, cpy in sorted(comps.items(), key=lambda kv: int(kv[0])):
        if cpy.get("sanct"):                     # sanctuary companies 31..34: "Mythical Warriors" (138:slot-1)
            mythical.append(dict(slot=int(s), type=cpy["type"], banner=int(s) - 1, soldiers=int(cpy["members"]),
                                 away=bool(cpy.get("away"))))
            continue
        if cpy.get("event"):                     # defensive aid on loan: the exe lists them under other forces
            continue
        rows.append(dict(slot=int(s), type=cpy["type"], banner=int(cpy.get("banner", int(s) - 1)) % 20,
                         soldiers=int(cpy["members"]) if not isinstance(cpy["members"], list) else len(cpy["members"]),
                         away=bool(cpy.get("away"))))
        if military_map.on(g):           # sim/military: the field state (FUN_00591610)
            rows[-1]["status"], rows[-1]["button"] = mforces.status(g, cpy)
    navy = []
    for b in sorted((b for b in g.buildings.values() if b.kind == "shipyard"), key=lambda b: b.id):
        tri = [w for w in g.walkers.values() if w.role == "trireme" and getattr(w, "home", None) == b.id]
        row = dict(workers=b.employees, trireme=bool(tri), hp=100, off=bool(b.misc.get("off")))
        if tri and military_map.on(g):          # the label 0x591680 and hull 0x591C30 (sim/military/navy.py)
            from .military import navy as mnavy
            mnavy.init(g, tri[0])
            row.update(label=mnavy.label(g, b)[0], clickable=mnavy.label(g, b)[1], hp=mnavy.hp_pct(tri[0]),
                       hull_text=mnavy.hull_text(tri[0]), id=tri[0].id)
        navy.append(row)
    tri_all = sum(1 for w in g.walkers.values() if w.role == "trireme")
    inv = False
    try:
        from .empire import events
        inv = getattr(g, "empire", None) is not None and bool(events.live(g, "invasion"))
    except Exception:
        pass
    inv = inv or bool(military_map.state(g).get("invasions"))      # an army on the map (sim/military)
    return dict(companies=rows, navy=navy, triremes=tri_all, soldiers=sum(r["soldiers"] for r in rows),
                invasion=inv, mythical=mythical)


ADVISOR_DATA = {8: _adv_hygiene, 10: _adv_culture, 12: _adv_finance, 9: _adv_husbandry, 11: _adv_mythology,
                7: _adv_population, 15: _adv_aesthetics, 6: _adv_trade, 13: _adv_overview, 2: _adv_military}


def trade_menu(g):
    """The Trade build submenu: one item per partner city that has no trading post or dock yet and trades
    something (FUN_005B9410, items by city_nth_other 0x005B9350), labelled "<building>: <city>"
    (trade_building_label 0x005B9480, format "%s: %s" at 0x0065B838; seen in the original); the building is the dock for a sea route, else the trading post
    (trade_building_type_for_city 0x005B9460: 0x3C / 0x3E). Choosing one binds the new building to that
    city (0x00665DB0): `build KEY X Y CITY`."""
    from .systems import trade
    from . import empire
    out = []
    for c, p in enumerate(trade.partners(g)):
        if trade.post_of(g, c) or not (p.get("buys") or p.get("sells")) or not empire.tradeable(g, c):
            continue
        key = "dock" if p["route"] == "sea" else "trading_post"
        out.append(dict(key=key, city=p["name"], text=f"{g.cat.spec(key)['name']}: {p['name']}"))
    return out


def footprint(g, key, x, y, d=None, x2=None, y2=None, tv=None, view=0):
    """Play mode build preview: the tiles a `build KEY X Y [d]` would cover and whether each is free land
    (a hint for the ghost; the build command itself decides). Avenue/boulevard: the drag (x, y) -> (x2, y2),
    each tile [x, y, ok, road tile]."""
    from .systems import agora, avenues, shore, ranch
    if key not in g.cat.buildings:
        return dict(ok=False, error=f"unknown building '{key}'")
    spec = g.cat.spec(key)
    w = g.world
    if key == "bridge":                       # one click on a water tile beside a shore (FUN_0041C450): the span
        from .game import bridge_piece, BRIDGE_DIR
        tiles, step, why = g.bridge_scan(x, y)  # the tiles scanned, red when refused
        cost = len(tiles) * spec.get("cost", 0)
        out = dict(ok=why is None, x=x, y=y, w=1, h=1, cost=cost if why is None else 0,
                   tiles=[[tx, ty, why is None] for tx, ty in tiles], **({"why": why} if why else {}))
        if step:                               # the exe's direction (the ghost turns it by the view, bridges.js)
            out["dir"] = BRIDGE_DIR[step]
        if why is None:                        # the pieces, drawn as the ghost
            out["pieces"] = [[tx, ty, bridge_piece(i, len(tiles), BRIDGE_DIR[step])] for i, (tx, ty) in enumerate(tiles)]
        return out
    if key == "road":                         # the road tool (bugs.md 464; oracle slope-road)
        from . import roaddrag
        G = g.road_grids()
        n = roaddrag.N
        piece = lambda cx, cy: int(tv.piece[cy, cx]) if tv is not None and 0 <= cx < n and 0 <= cy < n else 0
        poor = g.city.treasury < -1999
        if x2 is None:                        # no drag: the cursor tile alone (FUN_00452B80)
            ok, pic = roaddrag.cursor(G, x, y, piece(x, y))
            return dict(ok=ok and not poor, x=x, y=y, w=1, h=1, cost=0, tiles=[],
                        cursor=[x, y, ok and not poor, pic and list(pic)])
        # a drag: roads_drag_place(1) (Game.road_drag). The exe draws the route's road pictures when the trace reaches
        # the start (map_tiles_update_images on the rectangle: ramp tiles get their road-on-ramp pictures, as built);
        # a failed trace's part is in its terrain but not drawn, so no tiles then. The cursor tile is tested on the
        # terrain with the preview's road (FUN_00452B80: a road tile is red, so a placed end is red; oracle d1..d3)
        y2 = y if y2 is None else y2
        r = g.road_drag(x, y, x2, y2)
        for tx, ty in r["tiles"]:
            G.T[ty * n + tx] |= 0x40
        ok, pic = roaddrag.cursor(G, x2, y2, piece(x2, y2))
        out = dict(ok=r["ok"], x=x, y=y, w=1, h=1, cost=r["new"] * spec.get("cost", 0) if r["ok"] else 0,
                   tiles=[[tx, ty, True] for tx, ty in r["tiles"][::-1]] if r["ok"] else [],
                   cursor=[x2, y2, ok and not poor, pic and list(pic)])
        if r["ok"] and tv is not None:        # the route's ramp tiles in their road pictures, in the tab's view
            out["ramps"] = tv.ramp_preview(g, r["tiles"], view)
        return out
    if key == "wall" and x2 is not None:      # the wall drag's rectangle, each tile by the command's own rule
        line = g.wall_tiles(x, y, x2, y if y2 is None else y2, w.flags.shape[0])
        tiles = [[tx, ty, w.inside(tx, ty) and _would_build(g, "wall", tx, ty, tx, ty)[0]] for tx, ty in line]
        new = [t for t in tiles if t[2] and not w.flags[t[1], t[0]] & 0x4000]
        return dict(ok=all(t[2] for t in tiles), x=x, y=y, w=1, h=1, cost=len(new) * spec.get("cost", 0), tiles=tiles)
    if spec["kind"] == "gatehouse":            # 5x2 (h) / 2x5 (v): the build command's own check (bugs.md 88)
        try:
            o = g.gate_orient(d)
        except Exception as e:
            return dict(ok=False, error=str(e))
        ok, why = _would_build(g, "build", key, x, y, "h" if o == 1 else "v")
        # each tile red where it fails its own part of the rule (towers: free land; passage: road or free land)
        land = getattr(w, "build_land", w.free_land)
        tiles = [[tx, ty, ok or bool(w.inside(tx, ty) and ((p and w.road[ty, tx] and not w.occ[ty, tx]) or land(tx, ty)))]
                 for tx, ty, p in g.gate_tiles(x, y, "h" if o == 1 else "v")]
        if not ok and all(t[2] for t in tiles):
            for t in tiles:
                t[2] = False
        return dict(ok=ok, x=x, y=y, w=5 if o == 1 else 2, h=2 if o == 1 else 5, cost=spec.get("cost", 0), tiles=tiles,
                    **({"why": why} if why else {}))
    if spec["kind"] == "tower":                # on walls: the build command's own check
        ok, why = _would_build(g, "build", key, x, y, d)
        n = spec.get("size") or 2
        tiles = [[x + i, y + j, ok] for j in range(n) for i in range(n)]
        return dict(ok=ok, x=x, y=y, w=n, h=n, cost=spec.get("cost", 0), tiles=tiles, **({"why": why} if why else {}))
    if spec["kind"] == "avenue":
        tiles = [list(t) for t in avenues.preview(g, key, x, y, x if x2 is None else x2, y if y2 is None else y2)]
        return dict(ok=any(t[2] for t in tiles), x=x, y=y, w=1, h=1, cost=spec.get("cost", 0), tiles=tiles,
                    segments=sum(1 for t in tiles if t[2] and t[3]))
    if key in shore.KEYS:                      # half over water (systems/shore.py, bugs.md 131): the command's own test
        try:
            o = shore.orient_arg(d)
        except ValueError as e:
            return dict(ok=False, error=str(e))
        k = shore.fit(g, key, x, y, o)
        if k is None:                          # nothing fits: show the asked side, else the one closest to fitting
            k = o if o is not None else max(range(4), key=lambda j: sum(t[2] for t in shore.check(g, key, x, y, j)[1]))
        why = shore.site_error(g, key, x, y, o)
        tiles = shore.check(g, key, x, y, k)[1]
        if why and all(t[2] for t in tiles):   # the tiles pass but the front water, sea access or a limit fails
            for t in tiles:
                t[2] = False
        bx, by, size, _, misc = shore.layout(key, x, y, k)
        ghost = dict(id=0, key=key, kind=spec["kind"], x=bx, y=by, size=size, w=size, h=size, **misc)
        n = shore.KEYS[key]
        return dict(ok=not why, x=x, y=y, w=n, h=n, cost=spec.get("cost", 0), tiles=tiles, orient=k,
                    side=shore.LETTER[k], ghost=ghost, **({"why": why[0]} if why else {}))
    if key == "horse_ranch":                   # 3x3 house + 4x4 corral (systems/ranch.py, bugs.md 134)
        try:
            o = ranch.orient_arg(d)
        except ValueError as e:
            return dict(ok=False, error=str(e))
        why, tiles = ranch.check(g, x, y, o)
        cx, cy = ranch.corral_at(x, y, o)
        ghost = dict(id=0, key=key, kind=spec["kind"], x=x, y=y, size=3, w=3, h=3, corral=[cx, cy], orient=o)
        return dict(ok=not why, x=x, y=y, w=3, h=3, cost=spec.get("cost", 0), tiles=tiles, orient=o, ghost=ghost,
                    **({"why": why} if why else {}))
    wt = g.walker_tiles()                      # map_area_buildable 0x004A0DC0: no walker, not near the edge
    free = lambda tx, ty: bool(w.free_land(tx, ty)) and not w.near_play_edge(tx, ty) and (tx, ty) not in wt
    if key == "stadium":                       # two 5x5 halves, each level on its own; one per city
        from .systems import stadium
        try:
            bw, bh, halves = stadium.layout(x, y, d)
        except ValueError as e:
            return dict(ok=False, error=str(e))
        one = stadium.exists(g)
        tiles = []
        for hx, hy in halves:
            lvl = w.area_ok(hx, hy, 5)[0] or not all(free(hx + i, hy + j) for j in range(5) for i in range(5))
            tiles += [[hx + i, hy + j, free(hx + i, hy + j) and lvl and not one] for j in range(5) for i in range(5)]
        out = dict(ok=all(t[2] for t in tiles), x=x, y=y, w=bw, h=bh, cost=spec.get("cost", 0), tiles=tiles)
        if one:
            out["why"] = "You may only have one Stadium"           # 19:44
        return out
    if spec["kind"] == "agora":
        snapped = None
        if not d:                              # the cursor tile; the exe's search picks the spot and side (snap)
            snapped = agora.snap(g, key, x, y)
            if snapped:
                x, y, d = snapped
        strip, stalls, (bw, bh) = agora.layout(key, x, y, d)
        tiles = [[tx, ty, agora.strip_ok(w, tx, ty)] for tx, ty in strip]     # must be existing road
        for sx, sy in stalls:                  # each 2x2 stall: free land (world.area_ok, as `build`)
            lvl = w.area_ok(sx, sy, 2)[0] or not all(free(sx + i, sy + j) for j in (0, 1) for i in (0, 1))
            tiles += [[sx + i, sy + j, free(sx + i, sy + j) and lvl] for j in (0, 1) for i in (0, 1)]
        if not d or snapped:                   # play mode: the ghost moves to the snapped spot (fp.snap, fp.at)
            return dict(ok=bool(snapped) and all(t[2] for t in tiles), x=x, y=y, w=bw, h=bh, cost=spec.get("cost", 0),
                        tiles=tiles, snap=True, d=d or "down")
    else:
        if spec["kind"] == "monument":           # same rule as Game._monument: free, no road/wall/water
            try:
                o = g.monument_orient(d)          # R key: 0..3 (bugs.md 133)
            except Exception as e:
                return dict(ok=False, error=str(e))
            bw, bh = (spec["h"], spec["w"]) if o % 2 else (spec["w"], spec["h"])
            tiles = [[x + i, y + j, bool(w.inside(x + i, y + j) and not w.occ[y + j, x + i] and not w.road[y + j, x + i]
                                         and not w.avenue[y + j, x + i] and not w.flags[y + j, x + i] & 0x4207)]
                     for j in range(bh) for i in range(bw)]
            from .model import Building
            from .systems import monuments
            gb = Building(id=0, key=key, x=x, y=y, size=0, kind="monument")
            monuments.create(g, gb, o)             # pure: the piece layout only
            for p in gb.misc["pieces"]:
                p["s"] = p["n"]                    # drawn finished
            ghost = dict(id=0, key=key, kind="monument", x=x, y=y, w=bw, h=bh, orient=o, pieces=export.monument_pieces(gb))
            return dict(ok=all(t[2] for t in tiles), x=x, y=y, w=bw, h=bh, cost=spec.get("cost", 0), tiles=tiles,
                        ghost=ghost)
        else:
            bw = bh = spec.get("size") or 1
            if key == "commemorative_monument":    # d = "V [O]": large god statues are 4x4 (building_create 0x00493E70)
                from .systems import commemorative
                v = str(d or "").split()[:1]
                bw = bh = commemorative.size(int(v[0])) if v and v[0].isdigit() else bw
        if spec["kind"] == "vendor":           # snaps to the stall under (x, y), as `build` does
            st = agora.stall_at(g, x, y)
            if st is not None:
                a = g.buildings.get(st.misc.get("agora"))
                dup = a is not None and any(g.buildings[i].key == key for i in a.misc["stalls"] if i in g.buildings)
                ok, x, y = st.key == "empty_stall" and not dup, st.x, st.y
            else:
                ok = False
            tiles = [[x + i, y + j, ok] for j in range(bh) for i in range(bw)]
            return dict(ok=ok, x=x, y=y, w=bw, h=bh, cost=spec.get("cost", 0), tiles=tiles, snap=st is not None)
        elif spec["kind"] == "roadblock":
            tiles = [[x, y, g.roadblock_ok(x, y)]]
        else:
            tiles = [[x + i, y + j, free(x + i, y + j)] for j in range(bh) for i in range(bw)]
            if spec.get("needs") and all(t[2] for t in tiles):
                why = g.site_error(key, x, y)        # the same terrain rule the build command applies
                if why:
                    for t in tiles:
                        t[2] = False
                    return dict(ok=False, x=x, y=y, w=bw, h=bh, cost=spec.get("cost", 0), tiles=tiles, why=why)
    return dict(ok=all(t[2] for t in tiles), x=x, y=y, w=bw, h=bh, cost=spec.get("cost", 0), tiles=tiles)


KEEP_RAW = 4000          # ticks of frames kept uncompressed behind live (older ones are zlib'd)
STATE_DELTAS = 64        # building snapshots that keep their delta on the one before (protocol 2)
# Recording thinned by age (compact; docs/sim-design.md "Live recording memory"): (older than AGE ticks, keep the
# first frame / snapshot of every EVERY-tick bucket). Frames: every recorded one (1 tick apart at speed <= 30) for
# FINE_KEEP ticks, the 15-tick grid for a year, then one per 4 tiles' walk, past 4 years one per 240 ticks (~5 days).
# Snapshots: all for KEEP_RAW ticks (at speed 30 one per 30 ticks), then one per 8 days, past 4 years one per month.
MONTH = 816              # ticks per game month (51 x 16)
FINE_KEEP = 300
FRAME_TIERS = ((FINE_KEEP, REC), (12 * MONTH, 60), (48 * MONTH, 240))
STATE_TIERS = ((KEEP_RAW, STATE_EVERY), (48 * MONTH, 2 * MONTH))
THIN_BATCH = 600         # ticks of new candidates before a tier is thinned again (list splices are O(n))


def _raw(d):
    """A recorded frame/state: bytes, or ("z", compressed bytes) once compacted."""
    return zlib.decompress(d[1]) if isinstance(d, tuple) else d


def _terr(t):
    """A recorded terrain string, or ("z", compressed utf-8) once compacted."""
    return zlib.decompress(t[1]).decode() if isinstance(t, tuple) else t


_TEXTS = None


def warning(ids):
    """The original's warning (text group 19: title, then hint) for CommandError.warn, as one
    line, or "" (extracted/text/zeus_text.json; missing file: "")."""
    global _TEXTS
    if not ids:
        return ""
    if _TEXTS is None:
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            _TEXTS = json.load(open(os.path.join(root, "extracted", "text", "zeus_text.json"))).get("19", [])
        except (OSError, ValueError):
            _TEXTS = []
    return ". ".join(_TEXTS[i].strip() for i in ids if i < len(_TEXTS))


def save_file(name):
    """saves/play/NAME.pkl for a player-chosen name (letters, digits, space, - _ .), else None."""
    name = str(name or "").strip()
    if not name or len(name) > 40 or name.startswith(".") or any(not (c.isalnum() or c in " -_.") for c in name):
        return None
    return os.path.join(SAVES, name + ".pkl")


def list_saves():
    out = []
    if os.path.isdir(SAVES):
        for f in os.listdir(SAVES):
            if f.endswith(".pkl"):
                st = os.stat(os.path.join(SAVES, f))
                out.append(dict(name=f[:-4], mtime=st.st_mtime, size=st.st_size))
    return sorted(out, key=lambda s: -s["mtime"])


STALL_MS = 100                    # a lock held this long stalls every tab (the playhead keeps ~130 ms of frames)
SLOW_WINDOW = 2.0                 # the watcher's window (s): ticks done vs speed x time
SLOW_SHARE = 0.75                 # under this share of the expected ticks: logged as slow


class TimedLock:
    """The runner's lock, timed (bugs.md 442: a terrain update held it ~0.6 s once a game day and every walker
    stopped). A hold over STALL_MS is logged to stderr and kept in runner.stalls (GET /stalls.json), with where it
    was taken (function:line) and the tick."""
    def __init__(self, runner):
        self._l = threading.Lock()
        self._r = runner
        self._t0 = 0.0
        self._where = ""

    def __enter__(self):
        self._l.acquire()
        f = sys._getframe(1)
        self._where = f"{f.f_code.co_name}:{f.f_lineno}"
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        ms = (time.perf_counter() - self._t0) * 1000
        where = self._where
        self._l.release()
        if ms >= STALL_MS:
            self._r.note_stall("lock", ms, where)
        return False

    def acquire(self, *a, **k):
        return self._l.acquire(*a, **k)

    def release(self):
        self._l.release()

    def locked(self):
        return self._l.locked()


class Runner:
    def __init__(self, game, save=None, script=None, speed=120):
        self.setup(game, save, script, speed)

    def setup(self, game, save=None, script=None, speed=120):
        self.g = game
        self.save_path = save
        # live speed (ticks per wall-clock second) and pause: set by live tabs, kept in the save so a
        # load or a server restart keeps them
        self.rate = getattr(game, "live_rate", None) or speed
        self.paused = bool(getattr(game, "live_paused", False))
        # the leader name (play mode's /control {player}) is kept in the save too, so a server restart keeps it
        # (bugs.md 380; the exe: the save sits in its leader's folder Save/NAME/); a game without one (new, loaded,
        # the next episode) takes the running one's
        if getattr(game, "live_player", None):
            messages.PLAYER = game.live_player
        elif messages.PLAYER != "Ruler":
            game.live_player = messages.PLAYER
        game.hover = None             # the build tool over the map (walkers.shoo): a tab's, set again on its next move
        self.driven_at = 0.0          # synced live: when a tab last asked for ticks (docs/play-mode.md)
        self.seen_at = time.time()    # when any tab last polled frames (visible or not): --shared pauses without one
        self.shared = getattr(self, "shared", False)   # sim live --shared (a public server, set by live())
        self.held_at = 0.0            # when a driving tab last said a screen holds its playhead (hold=1: world map,
                                      # advisors, help ... play.js screenPauses): the stall watcher skips that time
        self.lock = TimedLock(self)
        self.stalls = getattr(self, "stalls", None) or collections.deque(maxlen=200)
        self.queue = []
        self.wait = None              # ("tick", T) | ("until", stat, n, deadline)
        if script:
            from . import script as scripts
            self.queue = [l for _, l in scripts.load(script) if l.split()[0] not in VIEWS]
        self.log = []
        # [(tick, json bytes | ("z", zlib bytes), fs, base fs, delta bytes | None)]: fs = frame serial (unique per
        # recorded frame, also across new games / loads), delta = protocol 2's delta on the frame before (base fs),
        # None when it would not be smaller or after compaction (docs/play/comms.md)
        self.frames = []
        self.error = ""               # last internal error (the sim pauses on one; shown by play mode)
        self._zf = self._zs = 0       # frames / states compacted up to this index
        self._zd = 0                  # states' deltas dropped up to this index
        self._zt = 0                  # terrains compressed up to this index
        self._thin_t = {}             # (frames|states, bucket) -> thinned below this tick (compact)
        self.frame_ticks = []
        self.states = []              # [(tick, json bytes, seq, base seq, delta | None)], snapshot without terrain/history
        self.state_ticks = []
        self.terrains = []            # [(tick, terrain string)]
        self.terrain_ticks = []
        self.last_version = None
        self._fenc = self._fenc2 = None   # (fs, comms.encode) of the newest frame / the one before (deltas)
        self._senc = self._senc2 = None   # (seq, comms.encode) of the newest snapshot / the one before
        self._terrains = []               # [(map_version, comms.encode)]: the last terrains served (terrain deltas)
        game.gone = []                # start collecting removed walkers (see record_frame)
        self.gone_walkers = {}        # {id: (tick, walker)} removed lately (walker_info)
        self.seen_walkers = {}
        game.sfx = []                 # and figure sounds (walkers.sfx)
        game.fx = []                  # and effect figures (sim/effects.py: dust, splashes)
        self.record_frame()
        self.record_state()

    def set_speed(self, rate=None, paused=None):
        if rate is not None:
            self.rate = self.g.live_rate = max(1, int(rate))
            # a fast rate records every REC ticks: the sim may stand between two frames. A synced tab plays only
            # up to its newest frame and asks for ticks past it; the sim, already past those, would wait for it
            # forever (128x then 1x froze the city, bugs.md 344). A frame at the current tick ends the buffer here.
            if self.frame_ticks and self.frame_ticks[-1] < self.g.tick:
                self.record_frame()
        if paused is not None:
            self.paused = self.g.live_paused = bool(paused)

    def frame_every(self):
        """Ticks between recorded frames: every tick at low speed (a synced tab draws what the sim just
        did), the 15-tick grid at high speed. Always a divisor of REC (frames on the REC grid stay)."""
        return 1 if self.rate <= 30 else 3 if self.rate <= 60 else 5 if self.rate <= 150 else REC

    def driven(self):
        return time.time() - self.driven_at < DRIVE_TIMEOUT

    # --- recording -----------------------------------------------------------------------------
    def went_into(self, wid, x, y):
        """[bx, by]: the tile of the building a removed walker went into (its target, else its home, as of
        the last frame), the footprint tile nearest to where it stood; [] if unknown. Play mode draws its
        last step onto that tile, where the building hides it (bugs.md 114)."""
        g = self.g
        for bid in getattr(self, "dest", {}).get(wid, ()):
            b = g.buildings.get(bid)
            if b is None:
                continue
            w, h = b.misc.get("w", b.size or 1), b.misc.get("h", b.size or 1)
            bx, by = min(max(x, b.x), b.x + w - 1), min(max(y, b.y), b.y + h - 1)
            if max(abs(bx - x), abs(by - y)) <= 1:
                return [bx, by]
        return []

    def sanct_menu(self):
        from . import gods
        try:
            return gods.menu(self.g)
        except Exception:                   # noqa: BLE001  (a frame never fails over the menu)
            return None

    def heroes_frame(self):
        from . import heroes
        try:
            return heroes.frame(self.g)
        except Exception:                   # noqa: BLE001  (a frame never fails over the heroes module)
            return {}

    def record_frame(self):
        g = self.g
        self.fserial = getattr(self, "fserial", 0) + 1
        f = dict(tick=g.tick, fs=self.fserial, date=g.date(), treasury=g.city.treasury, population=g.city.population,
                 sentiment=g.city.sentiment, version=getattr(g, "map_version", 0),
                 poseidon=bool(getattr(g, "poseidon", False)),     # build menus hide Poseidon buildings when off
                 sanct=self.sanct_menu(),           # the Mythology menu's sanctuaries (sim/gods; None = all)
                 episode=export.episode_export(g),  # an episode's unavailable buildings, tutorial switches (None:
                                                    # open play; sim/allowed.py, sim/episode.py)
                 undo=not g.undo_state(),           # the panel's undo button is enabled (panel_draw 0x00517BF0)
                 alerts=alerts.export(g),           # the panel's 4 alert slots (sim/alerts.py; ui.js drawAlerts)
                 lava=_lava_frame(g),               # [[slot, state, cooling %]] of started lava flows (play.js tint)
                 # [8] = the current step [from_x, from_y, start tick, end tick, roaming, next x, next y] (0 if
                 # none): play mode moves the walker over the step's own ticks, whatever the frame interval;
                 # roaming and the route's next tile set its lift on ramps (scene.js rampLift, bugs.md 211)
                 walkers=[[w.id, w.x, w.y, w.role, export.carried(g, w), w.amount, export.followers(g, w),
                           export.walker_anim(g, w), _walker_step(g, w)]
                          for w in g.walkers.values()],
                 # walkers removed since the last frame, at the tile they went in from (play mode draws
                 # their last step instead of leaving them standing a frame interval)
                 gone=[[i, x, y, *self.went_into(i, x, y)] for i, x, y in (g.__dict__.get("gone") or [])
                       if i not in g.walkers],
                 sfx=g.__dict__.get("sfx") or [],   # figure sounds since the last frame (walkers.sfx; gods.js)
                 fx=g.__dict__.get("fx") or [],     # effect figures to make (sim/effects.py; effects.js)
                 **self.heroes_frame(),             # tint / statues (sim/heroes frame: devoured red, petrified grey)
                 houses=[[b.id, b.level, b.occupants, housing.capacity(g, b)]
                         for b in g.buildings.values() if b.kind == "house"],
                 # carts waiting with nowhere to go (Figure+0x7B, set when cart_find_destination fails: figure_cart_pusher
                 # 0x004AE160; economy.cart_wait): the problems overlays' '?' icon and tooltip 66:16 (docs/play/pages.md)
                 waiting=[w.id for w in g.walkers.values() if w.role == "cart" and w.state == "wait" and not w.target])
        # bugs.md 455: a tab draws its frames behind the sim (the playhead lags the newest frame), so a figure it
        # shows may be gone on the server when its walker window asks; the removed walker objects of the last
        # GONE_KEEP ticks answer for it (the exe's window reads the figure slot, which keeps its data)
        seen = getattr(self, "seen_walkers", None) or {}
        for i, _x, _y in (g.__dict__.get("gone") or []):
            if i in seen and i not in g.walkers:
                self.gone_walkers[i] = (g.tick, seen[i])
        if self.gone_walkers and next(iter(self.gone_walkers.values()))[0] < g.tick - GONE_KEEP:
            self.gone_walkers = {i: v for i, v in self.gone_walkers.items() if v[0] >= g.tick - GONE_KEEP}
        self.seen_walkers = dict(g.walkers)
        g.gone = []
        g.sfx = []
        g.fx = []
        self.dest = {w.id: (w.target, w.home) for w in g.walkers.values()}
        enc = comms.encode(f, comms.FRAME_KEYED)
        data = comms.join(enc)
        again = bool(self.frame_ticks) and self.frame_ticks[-1] == g.tick    # re-recorded at the same tick (a command)
        base = self._fenc2 if again else self._fenc
        dl = comms.delta(base[1], enc, base[0], comms.FRAME_KEYED) if base else None
        entry = (g.tick, data, self.fserial, base[0] if base else None, dl if dl is not None and len(dl) < len(data) else None)
        if again:
            self.frames[-1] = entry
        else:
            self.frames.append(entry)
            self.frame_ticks.append(g.tick)
            self._fenc2 = self._fenc
        self._fenc = (self.fserial, enc)

    def record_state(self):
        g = self.g
        self._state_wall = time.time()
        snap = export.snapshot(g, with_terrain=False)
        snap.pop("history", None)
        # a snapshot can be re-recorded at the same tick (a command right after one): seq tells them apart
        self.seq = getattr(self, "seq", 0) + 1
        snap["seq"] = self.seq
        enc = comms.encode(snap, comms.STATE_KEYED, sub=True)
        data = comms.join(enc)
        again = bool(self.state_ticks) and self.state_ticks[-1] == g.tick
        base = self._senc2 if again else self._senc
        dl = comms.delta(base[1], enc, base[0], comms.STATE_KEYED) if base else None
        entry = (g.tick, data, self.seq, base[0] if base else None, dl if dl is not None and len(dl) < len(data) else None)
        if again:
            self.states[-1] = entry
        else:
            self.states.append(entry)
            self.state_ticks.append(g.tick)
            self._senc2 = self._senc
        self._senc = (self.seq, enc)
        terr = export.terrain_string(g)
        if not self.terrains or self.terrains[-1][1] != terr:
            self.terrains.append((g.tick, terr))
            self.terrain_ticks.append(g.tick)
        self.last_version = getattr(g, "map_version", 0)

    # --- script --------------------------------------------------------------------------------
    def start_wait(self, line):
        p = line.split()
        r = self.g.rules
        if p[0] == "until":
            months = int(p[3]) if len(p) > 3 else 24
            return ("until", p[1], int(p[2]), self.g.tick + months * r["ticks_per_day"] * r["days_per_month"])
        n = int(p[1]) if len(p) > 1 else 1
        return ("tick", self.g.tick + {"step": n, "wait": n, "days": n * r["ticks_per_day"],
                                       "months": n * r["ticks_per_day"] * r["days_per_month"]}[p[0]])

    def wait_done(self):
        w = self.wait
        if w[0] == "tick":
            return self.g.tick >= w[1]
        return getattr(self.g.city, w[1], 0) >= w[2] or self.g.tick >= w[3]

    def wait_left(self):
        """Known remaining script time in ticks (until-waits count as 0), for the timeline."""
        r = self.g.rules
        left = self.wait[1] - self.g.tick if self.wait and self.wait[0] == "tick" else 0
        for line in self.queue:
            p = line.split()
            if p[0] in ("step", "wait", "days", "months"):
                n = int(p[1]) if len(p) > 1 else 1
                left += {"step": n, "wait": n, "days": n * r["ticks_per_day"],
                         "months": n * r["ticks_per_day"] * r["days_per_month"]}[p[0]]
        return max(0, left)

    def command(self, line):
        return self.commands([line])[0]

    def commands(self, lines):
        """Run lines in one go under the lock and record one snapshot after all of them, so a drag that
        places 20 houses never shows half of them: [(ok, out, tick, warn)] per line (warn: the
        original's warning text for a refusal, "" if none)."""
        with self.lock:
            # one batch = one player action: undo takes all of it back (undo_begin at the tool click)
            undoable = any(line.split()[:1] and line.split()[0].lower() in Game.UNDO_OPS for line in lines)
            if undoable:
                self.g.action_begin()
            try:
                res = [self._command(line) for line in lines]
            finally:
                if undoable:
                    self.g.action_end()
            if self.g.tick % REC == 0:
                self.record_frame()
            self.record_state()
            return res

    def _command(self, line):
        warn = ""
        if True:
            try:
                out = self.g.command(line)
                self.log.append(f"> {line}: {out}")
                ok = True
            except CommandError as e:
                out = str(e)
                self.log.append(f"! {line}: {e}")
                ok = False
                warn = warning(e.warn)
            except Exception as e:      # a bug in a command must not take the server down
                traceback.print_exc()
                out = f"internal error: {type(e).__name__}: {e}"
                self.log.append(f"! {line}: {out}")
                ok = False
            return ok, out, self.g.tick, warn

    # --- loop ----------------------------------------------------------------------------------
    def live_window(self):
        """How far behind live a tab may be and still count as live (its commands are accepted):
        about a second of play plus the frame interval and polling."""
        return max(45, self.rate) + 2 * REC

    def note_stall(self, kind, ms, where, **extra):
        """One stall: kept for GET /stalls.json and printed (the server's own watcher, user 11-03)."""
        e = dict(at=time.strftime("%H:%M:%S"), kind=kind, ms=round(ms), where=where, tick=self.g.tick, **extra)
        self.stalls.append(e)
        print(f"[stall] {e['at']} {kind} {e['ms']} ms at {where} (tick {e['tick']})"
              + "".join(f" {k}={v}" for k, v in extra.items()), file=sys.stderr, flush=True)

    def watch(self):
        """Real time vs ticks: every SLOW_WINDOW seconds, while the city runs (not paused, no campaign screen) and
        a tab is driving it or the server runs alone, the ticks done against speed x time; under SLOW_SHARE of them
        is logged as "slow" (the sim, a long request or the lock falling behind the clock). A window in which the
        driving tab said a screen holds it (hold=1: world map with "Pause on the world map", advisors, help ...)
        is not counted: the city waits for that tab on purpose (bugs.md 467)."""
        last_t, last_tick = time.time(), self.g.tick
        while True:
            time.sleep(SLOW_WINDOW)
            now, tick = time.time(), self.g.tick
            g = self.g
            running = not self.paused and not ("campaign" in g.__dict__ and campaign_screen(g)) \
                and not (self.shared and now - self.seen_at > SHARED_IDLE) \
                and not (self.driven() and self.held_at >= last_t)
            if running and (self.driven() or not self.driven_at) and tick >= last_tick:
                want = self.rate * (now - last_t)
                if want >= 10 and tick - last_tick < SLOW_SHARE * want:
                    self.note_stall("slow", (now - last_t) * 1000, "clock", ticks=tick - last_tick, want=round(want))
            last_t, last_tick = now, tick

    def run(self):
        """The one live timeline: the sim advances with the wall clock at self.rate (tabs only watch,
        or replay recorded frames; they never pace the sim). An exception never ends the loop: it is
        logged, shown to the browser (meta.error) and pauses the city; play resumes on request."""
        last_save = time.time()
        last = time.time()
        target = float(self.g.tick)
        while True:
            try:
                now = time.time()
                idle = self.shared and now - self.seen_at > SHARED_IDLE   # --shared: no tab open -> the city waits
                if not self.paused and not self.driven() and not idle:
                    target += self.rate * (now - last)
                last = now
                target = min(max(target, self.g.tick), self.g.tick + 2 * self.rate)   # no debt if we fell behind
                worked = False if self.driven() else self.advance(int(target))   # synced: the tab's poll advances
                if self.save_path and time.time() - last_save > 5:
                    with self.lock:
                        self.g.save(self.save_path)
                    last_save = time.time()
                self.compact()
            except Exception as e:
                traceback.print_exc()
                self.error = f"{type(e).__name__}: {e} (tick {self.g.tick}); the city is paused"
                self.log.append("! internal error: " + self.error)
                self.set_speed(paused=True)
                target = float(self.g.tick)
                worked = False
            if not worked:
                time.sleep(0.01)

    def advance(self, limit):
        """Run script lines that are due, then simulate up to tick `limit` (in REC steps)."""
        worked = False
        with self.lock:
            g = self.g
            while self.wait is None and self.queue:
                line = self.queue.pop(0)
                if line.split()[0] in TIME_OPS:
                    self.wait = self.start_wait(line)
                else:
                    try:
                        self.log.append(f"> {line}: {script_apply(g, line)}")
                    except CommandError as e:
                        self.log.append(f"! {line}: {e}")
                    except Exception as e:      # a bug in a command: log it, keep the script going
                        traceback.print_exc()
                        self.log.append(f"! {line}: internal error: {type(e).__name__}: {e}")
                    self.record_state()
            budget = CHUNK
            fe = self.frame_every()
            camp = "campaign" in g.__dict__
            while g.tick < limit and budget > 0:
                if camp and campaign_screen(g):       # a campaign screen is up: the exe's city stands still
                    break
                n = min(fe - g.tick % fe, max(1, limit - g.tick))
                if camp:                          # the goals are judged at the day's end: stop right there
                    tpd = g.rules["ticks_per_day"]
                    n = min(n, tpd - g.tick % tpd)
                g.step(n)
                budget -= n
                worked = True
                if g.tick % fe == 0:    # frames on a divisor of the REC grid: walkers interpolate linearly
                    self.record_frame()
                since = g.tick - self.state_ticks[-1]
                if getattr(g, "map_version", 0) != self.last_version or since >= STATE_EVERY or \
                        (since >= REC * 2 and time.time() - self._state_wall >= STATE_WALL):
                    self.record_state()
                if self.wait is not None and self.wait_done():
                    self.wait = None
                    break
        return worked

    def compact(self):
        """Keep the recording small over long sessions (docs/sim-design.md "Live recording memory"): thin out old
        frames and building snapshots by age (FRAME_TIERS, STATE_TIERS), compress frames older than KEEP_RAW ticks,
        every snapshot but the last 4 and every terrain but the newest."""
        live = self.g.tick
        with self.lock:
            done = self.__dict__.setdefault("_thin_t", {})
            for name, tiers in (("frames", FRAME_TIERS), ("states", STATE_TIERS)):
                for age, every in tiers:
                    lim = live - age
                    t0 = done.get((name, every), -1)
                    if lim - t0 >= THIN_BATCH:
                        self._thin(name, t0, lim, every)
                        done[(name, every)] = lim
            while self._zf < len(self.frames) and self.frames[self._zf][0] < live - KEEP_RAW:
                t, d, fs, b, _ = self.frames[self._zf]          # (old frames: no delta; a tab asking them gets full ones)
                if not isinstance(d, tuple):
                    self.frames[self._zf] = (t, ("z", zlib.compress(d, 6)), fs, b, None)
                self._zf += 1
            while self._zs < len(self.states) - 4:
                t, d, seq, b, dl = self.states[self._zs]
                if not isinstance(d, tuple):
                    self.states[self._zs] = (t, ("z", zlib.compress(d, 6)), seq, b, dl)
                self._zs += 1
            k = len(self.states) - STATE_DELTAS                  # deltas kept for the last STATE_DELTAS snapshots
            while self._zd < k:
                t, d, seq, b, _ = self.states[self._zd]
                self.states[self._zd] = (t, d, seq, b, None)
                self._zd += 1
            while self._zt < len(self.terrains) - 1:           # old terrains: replay reads them rarely
                t, terr = self.terrains[self._zt]
                if not isinstance(terr, tuple):
                    self.terrains[self._zt] = (t, ("z", zlib.compress(terr.encode(), 6)))
                self._zt += 1

    def _thin(self, name, t0, t1, every):
        """Of the frames / snapshots with t0 <= tick < t1 keep the first in each `every`-tick bucket (the one in effect
        at the bucket's start, as replay shows it). A kept frame whose delta base is gone loses its delta (replay of
        that stretch gets whole frames); index cursors move with the removed entries."""
        items, ticks = (self.frames, self.frame_ticks) if name == "frames" else (self.states, self.state_ticks)
        a, k = bisect.bisect_left(ticks, t0), bisect.bisect_left(ticks, t1)
        if k - a < 2:
            return
        last = ticks[a - 1] // every if a > 0 else None
        keep = []
        for i in range(a, k):
            q = ticks[i] // every
            if q != last:
                keep.append(i)
                last = q
        if len(keep) == k - a:
            return
        kept = []
        prev_id = items[a - 1][2] if a > 0 else None
        for i in keep:
            e = items[i]
            if e[4] is not None and e[3] != prev_id:     # its base was dropped: the delta is useless now
                e = e[:4] + (None,)
            kept.append(e)
            prev_id = e[2]
        if k < len(items) and items[k][4] is not None and items[k][3] != prev_id:
            items[k] = items[k][:4] + (None,)            # the next one's base may have been dropped too
        removed = sorted(set(range(a, k)) - set(keep))
        items[a:k] = kept
        ticks[a:k] = [ticks[i] for i in keep]
        cur = ("_zf",) if name == "frames" else ("_zs", "_zd")
        for c in cur:                                     # an index cursor moves back by the removed entries before it
            setattr(self, c, getattr(self, c) - bisect.bisect_left(removed, getattr(self, c)))

    # --- queries -------------------------------------------------------------------------------
    def frames_range(self, a, b, v2=False, base=None):
        """Recorded frames with a <= tick <= b, starting with the one in effect at a (play mode buffers ahead
        instead of polling pairs). v2 (protocol 2, docs/play/comms.md): a frame whose predecessor in the answer
        (for the first: the tab's newest frame, fs = base) is the base of its delta goes as that delta; base's
        own frame is left out."""
        i = max(0, bisect.bisect_right(self.frame_ticks, a) - 1)
        j = bisect.bisect_right(self.frame_ticks, b)
        if not v2:
            return b"[" + b",".join(_raw(f[1]) for f in self.frames[i:j]) + b"]"
        out, prev = [], base
        for _, d, fs, bfs, dl in self.frames[i:j]:
            if prev is not None and fs == prev:
                continue
            out.append(dl if prev is not None and bfs == prev and dl is not None else _raw(d))
            prev = fs
        return b"[" + b",".join(out) + b"]"

    def frames_at(self, t):
        i = max(0, bisect.bisect_right(self.frame_ticks, t) - 1)
        f0 = _raw(self.frames[i][1])
        f1 = _raw(self.frames[i + 1][1]) if i + 1 < len(self.frames) else b"null"
        return f0, f1

    def state_lite(self, t, v2=False, base=None):
        """The building snapshot in effect at tick t (play mode). v2 with base (the seq the tab holds): the chain of
        deltas from base to it ({"deltas": [...]}, [] if it is base) when every link is kept and the chain is
        smaller than the snapshot; else the snapshot."""
        i = max(0, bisect.bisect_right(self.state_ticks, t) - 1)
        full = self.states[i][1]
        if v2 and base is not None:
            k = i
            while k >= 0 and k >= i - STATE_DELTAS and self.states[k][2] != base:
                k -= 1
            if k >= 0 and self.states[k][2] == base:
                chain = [self.states[m][4] for m in range(k + 1, i + 1)]
                if all(chain[n] is not None and self.states[k + 1 + n][3] == self.states[k + n][2] for n in range(len(chain))):
                    size = sum(len(c) for c in chain)
                    if isinstance(full, tuple) or size < len(full):
                        return b'{"deltas":[' + b",".join(chain) + b"]}"
        return _raw(full)

    def state_at(self, t):
        g = self.g
        i = max(0, bisect.bisect_right(self.state_ticks, t) - 1)
        j = max(0, bisect.bisect_right(self.terrain_ticks, t) - 1)
        month = g.rules["ticks_per_day"] * g.rules["days_per_month"]
        hist = g.history[:max(0, t // month)]
        return (_raw(self.states[i][1])[:-1] + b',"state_tick":' + str(self.state_ticks[i]).encode()
                + b',"terrain_tick":' + str(self.terrain_ticks[j]).encode()
                + b',"terrain":' + _dumps(_terr(self.terrains[j][1])) + b',"history":' + _dumps(hist) + b"}")


def campaign_base(r):
    """The save the campaign's parent.dat / replay files sit next to (sim/campaign flow.files): the server's save,
    else saves/play/campaign.pkl."""
    return r.save_path or os.path.join(SAVES, "campaign.pkl")


def campaign_op(r, body):
    """POST /campaign (play mode's campaign screens, docs/play/campaign.md "Server"): the CLI's campaign commands
    (sim/campaign/cli.py) on the live game. A new episode's game replaces the runner's (as File > New)."""
    from .campaign import flow, goals
    op = body.get("op")
    try:
        with r.lock:
            g = r.g
            new = None
            if op == "start":
                new = flow.start(str(body.get("adventure")), None, int(body.get("seed", 1)), body.get("difficulty"))
            elif not g.__dict__.get("campaign"):
                return dict(ok=False, out="not a campaign game")
            elif op == "briefed":                  # [, "difficulty": D]: the briefing's arrows
                flow.briefed(g, body.get("difficulty"))
            elif op == "proceed":
                try:
                    new = flow.proceed(g, campaign_base(r), body.get("colony"))
                except flow.Choice as c:
                    return dict(ok=False, choose=[dict(n=n, id=cid, name=nm) for n, cid, nm in c.options], out=str(c))
                if new is g:
                    new = None
            elif op == "stay":
                flow.continue_building(g)
            elif op == "replay":
                new = flow.replay(campaign_base(r))
                new.campaign["briefed"] = True       # the defeat screen's Replay episode goes to the city (0x00421730)
            elif op == "win":                      # TEST COMMAND (campaign win): won at the next month change
                from . import testcmds
                why = testcmds.refuse(g, "campaign win")
                if why:
                    return dict(ok=False, out=why)
                g.campaign["forced"] = True
                return dict(ok=True, out=testcmds.count(g, "campaign win", "won at the next month change"))
            elif op == "setaside":
                out = goals.set_aside(g, int(body.get("goal", -1)))
                r.record_state()
                return dict(ok=True, out=out)
            else:
                return dict(ok=False, out=f"unknown op {op!r}")
            if new is not None:
                if op != "replay":
                    os.makedirs(os.path.dirname(campaign_base(r)) or ".", exist_ok=True)
                    new.save(flow.files(campaign_base(r))["replay"])
                r.setup(new, r.save_path, None, r.rate)
                r._tview = None
                r._terrain = (None, b"")
            return dict(ok=True, tick=r.g.tick, screen=flow.screen(r.g))
    except ValueError as e:
        return dict(ok=False, out=str(e))
    except Exception as e:                      # noqa: BLE001  (a bug must not take the server down)
        traceback.print_exc()
        return dict(ok=False, out=f"{type(e).__name__}: {e}")


def live(save=None, script=None, port=8765, speed=120, map_name=None, seed=1, no_test=False, host="127.0.0.1",
         shared=False):
    from . import testcmds
    if map_name is None:                # the scripts/ benchmarks build everything: the unrestricted sandbox
        map_name = "sandbox_open" if script else "sandbox"
    testcmds.LOCKED = no_test           # one game per server process; survives File > New / Load
    if save and os.path.exists(save) and not script:
        g = Game.load(save)
        alerts.reset(g)                 # a loaded game starts without alerts (exe FUN_00510ED0 -> FUN_0040FFD0)
    else:
        g = Game(map_name, seed)
    r = Runner(g, save, script, speed)
    r.shared = shared
    threading.Thread(target=r.run, daemon=True).start()
    threading.Thread(target=r.watch, daemon=True).start()   # stalls: stderr + /stalls.json

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=VIEWER, **kw)

        def log_message(self, *a):
            pass

        def end_headers(self):                  # viewer files change while we work: never serve stale JS
            p = self.path.split("?")[0]
            if p.startswith("/play/atlas/") and p.endswith((".png", ".bin", ".jpg")):
                # sprite sheets (built or installed assets, hundreds of MB): cacheable, so a CDN in front of a remote
                # server (Cloudflare) serves them instead of the server; a day, as they change only with a new build
                self.send_header("Cache-Control", "public, max-age=86400")
            elif not p.endswith((".png", ".mp3", ".wav")):
                self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def send_bytes(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            # frames and building snapshots are repetitive JSON: gzip cuts them 10-40x for ~1 ms (user 10-29: 2 MB/s)
            if len(body) > 2048 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
                body = gzip.compress(body, compresslevel=6)
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def query(self):
            q = {}
            if "?" in self.path:
                for kv in self.path.split("?", 1)[1].split("&"):
                    k, _, v = kv.partition("=")
                    q[k] = v
            return q

        def do_GET(self):
            path = self.path.split("?")[0]
            q = self.query()
            if path == "/":                     # the game (play mode); the developer map viewer stays at /index.html
                self.send_response(302)
                q0 = self.path[2:] if self.path.startswith("/?") else ""
                if shared:                      # --shared: visitors go straight into the city (newgame.js boot)
                    q0 = "shared=1" + ("&" + q0 if q0 else "")
                self.send_header("Location", "/play.html" + ("?" + q0 if q0 else ""))
                self.end_headers()
                return
            if path == "/server.json":          # what kind of server this is (newgame.js boot: --shared skips the menu)
                return self.send_bytes(_dumps(dict(shared=r.shared)))
            if path == "/frame.json":
                with r.lock:
                    live_tick = r.g.tick
                    t = int(float(q.get("t", live_tick)))
                    if "rate" in q and float(q["rate"]) > 0 and live_tick - t <= r.live_window():
                        r.set_speed(int(float(q["rate"])))      # a paused viewer (rate 0) leaves the city alone
                    f0, f1 = r.frames_at(t)
                    i = max(0, bisect.bisect_right(r.state_ticks, t) - 1)
                    meta = dict(live_tick=live_tick, rec=REC, state_tick=r.state_ticks[i],
                                script_left=r.wait_left(), script_running=bool(r.queue or r.wait),
                                waiting=(r.wait[1] + " " + str(r.wait[2])) if r.wait and r.wait[0] == "until" else "",
                                log=r.log[-8:])
                return self.send_bytes(b'{"f0":' + f0 + b',"f1":' + f1 + b',"meta":' + _dumps(meta) + b"}")
            if path == "/footprint.json":         # play mode: build preview hint
                with r.lock:
                    return self.send_bytes(_dumps(footprint(r.g, q.get("key", ""), int(q.get("x", 0)),
                                                            int(q.get("y", 0)), q.get("d") or None,
                                                            int(q["x2"]) if q.get("x2") else None,
                                                            int(q["y2"]) if q.get("y2") else None,
                                                            getattr(r, "_tview", None), int(q.get("v", 0) or 0))))
            if path == "/walker_info.json":       # play mode: the walker window (walker_info)
                ids = [int(v) for v in q.get("ids", "").split(",") if v.lstrip("-").isdigit()]
                with r.lock:
                    return self.send_bytes(_dumps(walker_info(r.g, ids, r.gone_walkers)))
            if path == "/trade_post.json":        # play mode: a trading post / dock window (trade_post)
                with r.lock:
                    return self.send_bytes(_dumps(trade_post(r.g, int(q.get("id", 0) or 0))))
            if path == "/advisor.json":           # play mode: an advisor screen's data (advisor)
                with r.lock:
                    return self.send_bytes(_dumps(advisor(r.g, int(q.get("a", 0) or 0))))
            if path == "/land.json":              # play mode: the land window's kind of a tile (land_kind)
                with r.lock:
                    x, y = int(q.get("x", 0)), int(q.get("y", 0))
                    d = dict(kind=land_kind(r.g, x, y))
                    if d["kind"] == 8:                # rubble: the building it came from (g_grid_ruin_type)
                        d["ruin"] = (getattr(r.g, "ruin_type", None) or {}).get((x, y))
                    return self.send_bytes(_dumps(d))
            if path == "/maps.json":              # play mode: the new-game screen (maps_info)
                return self.send_bytes(_dumps(maps_info()))
            if path == "/adventures.json":        # play mode: the new-game screens (sim/campaign flow.adventures)
                from .campaign import flow
                return self.send_bytes(_dumps(dict(flow.adventures(), maps=maps_info())))
            if path == "/campaign.json":          # play mode: the campaign screens (flow.screens)
                from .campaign import flow
                with r.lock:
                    d = flow.screens(r.g) if r.g.__dict__.get("campaign") else dict(campaign=False)
                    from .data import DIFFICULTIES
                    dn = getattr(r.g, "difficulty", None)
                    d.update(tick=r.g.tick, difficulty=DIFFICULTIES.index(dn) if dn in DIFFICULTIES else 2)
                return self.send_bytes(_dumps(d))
            if path == "/goals.json":             # play mode: the Goals screen (goals_info)
                with r.lock:
                    return self.send_bytes(_dumps(goals_info(r.g)))
            if path == "/options.json":           # play mode: what the Options menu shows (options.js)
                from . import military
                from .data import DIFFICULTIES
                with r.lock:
                    d = getattr(r.g, "difficulty", None) or r.g.cat.rules.get("difficulty")   # (older saves: the catalog's)
                    return self.send_bytes(_dumps(dict(
                        difficulty=DIFFICULTIES.index(d) if d in DIFFICULTIES else 2, difficulty_name=d,
                        invaders=bool(military.enemies_alive(r.g)), tick=r.g.tick,
                        auto_defend=bool(military.state(r.g).get("auto_defend")))))
            if path == "/trade.json":             # play mode: the Trade build submenu (trade_menu)
                with r.lock:
                    return self.send_bytes(_dumps(trade_menu(r.g)))
            if path == "/military.json":          # play mode: standards, company panel (sim/military export)
                from . import military
                with r.lock:
                    return self.send_bytes(_dumps(military.export(r.g)))
            if path == "/heroes.json":            # play mode: halls, heroes, monsters (sim/heroes export)
                from . import heroes
                with r.lock:
                    return self.send_bytes(_dumps(heroes.export(r.g)))
            if path == "/world.json":             # play mode: the world map screen (sim/empire export)
                from . import empire
                with r.lock:
                    return self.send_bytes(_dumps(empire.export(r.g)))
            if path == "/frames.json":            # play mode: a window of frames + live meta
                r.seen_at = time.time()
                if "want" in q:                   # synced live: the tab's playhead + its margin drives the sim
                    r.driven_at = time.time()
                    if q.get("hold"):             # a screen pauses the tab (play.js screenPauses): not "slow"
                        r.held_at = r.driven_at
                    if not r.paused and not r.error:
                        r.advance(min(int(float(q["want"])), r.g.tick + max(2 * r.rate, REC)))
                    with r.lock:              # the tab wants only ticks the sim has passed, and its newest frame is
                        # behind the sim (the sim stood between two frames): one at the sim's tick, else both wait
                        # for each other (bugs.md 344). Not when want == tick: that is every poll at high speed.
                        if r.frame_ticks and r.frame_ticks[-1] < r.g.tick and int(float(q["want"])) < r.g.tick:
                            r.record_frame()
                with r.lock:
                    a, b = int(float(q.get("from", 0))), int(float(q.get("to", 0)))
                    i = max(0, bisect.bisect_right(r.state_ticks, int(float(q.get("at", a)))) - 1)
                    meta = dict(live_tick=r.g.tick, state_tick=r.state_ticks[i], version=getattr(r.g, "map_version", 0),
                                rate=r.rate, paused=r.paused, window=r.live_window(), first=r.frame_ticks[0],
                                error=r.error, head_seq=r.seq, every=r.frame_every(),
                                view=getattr(r.g, "view", 0))
                    ck = campaign_key(r.g)
                    if ck:
                        meta["campaign"] = ck
                    meta["proto"] = 2            # the newest protocol this server speaks (docs/play/comms.md)
                    v2 = q.get("v") == "2"
                    base = int(q["base"]) if v2 and q.get("base", "").isdigit() else None
                    return self.send_bytes(b'{"frames":' + r.frames_range(a, b, v2, base) + b',"meta":' + _dumps(meta) + b"}")
            if path == "/state.json":
                with r.lock:
                    t = int(float(q.get("t", r.g.tick)))
                    if q.get("lite"):           # play mode: buildings only (v=2&base=SEQ: deltas on SEQ)
                        return self.send_bytes(r.state_lite(t, q.get("v") == "2",
                                                            int(q["base"]) if q.get("base", "").lstrip("-").isdigit() else None))
                    return self.send_bytes(r.state_at(t))
            if path.startswith("/data/") and path.endswith(".json") and ".." not in path:
                f = os.path.join(os.path.dirname(VIEWER), path.lstrip("/"))     # play mode: data + mapping tables
                if os.path.exists(f):
                    with open(f, "rb") as fh:
                        return self.send_bytes(fh.read())
                return self.send_error(404)
            if path.startswith("/audio/") and ".." not in path:      # play mode: the original's sound files
                rel = urllib.parse.unquote(path[len("/audio/"):])
                # Adventures/...: a custom adventure's spoken texts next to its .pak (sim/campaign flow.voices)
                f = os.path.join(os.path.dirname(VIEWER), "zeus-original", "app", *(("",) if rel.startswith("Adventures/") else ("Audio",)), rel)
                if not os.path.isfile(f):
                    return self.send_error(404)
                with open(f, "rb") as fh:
                    body = fh.read()
                # byte ranges: play mode streams music through <audio> and seeks to resume a song
                rng = self.headers.get("Range", "")
                a, b = 0, len(body) - 1
                if rng.startswith("bytes="):
                    s0, _, s1 = rng[6:].split(",")[0].partition("-")
                    if s0:
                        a, b = int(s0), int(s1) if s1 else len(body) - 1
                    elif s1:
                        a = max(0, len(body) - int(s1))
                    b = min(b, len(body) - 1)
                self.send_response(206 if rng else 200)
                self.send_header("Content-Type", "audio/mpeg" if f.lower().endswith(".mp3") else "audio/wav")
                self.send_header("Accept-Ranges", "bytes")
                if rng:
                    self.send_header("Content-Range", f"bytes {a}-{b}/{len(body)}")
                self.send_header("Content-Length", str(b - a + 1))
                self.end_headers()
                return self.wfile.write(body[a:b + 1])
            if path == "/terrain.json":          # play mode (viewer/play.html): the map's terrain images
                with r.lock:
                    v = getattr(r.g, "map_version", 0)
                    if getattr(r, "_terrain", (None,))[0] != v:
                        if getattr(r, "_tview", None) is None:
                            from .terrain_view import TerrainView
                            r._tview = TerrainView(r.g)
                        # tid: a serial unique across new games / loads (protocol 2's base; map_version restarts)
                        r.tserial = getattr(r, "tserial", 0) + 1
                        enc = comms.encode(dict(terrain(r.g, r._tview), tid=r.tserial), grids=comms.TERRAIN_GRIDS)
                        r._terrain = (v, comms.join(enc))
                        r._terrains = (r._terrains + [(r.tserial, enc)])[-3:]
                    base = q.get("base", "")
                    if q.get("v") == "2" and base.isdigit():   # protocol 2: a delta on the terrain the tab holds
                        if r._terrains and r._terrains[-1][0] == int(base):
                            return self.send_bytes(b'{"_b":' + base.encode() + b"}")   # the tab has it
                        for tid, enc in r._terrains[:-1]:
                            if tid == int(base):
                                dl = comms.delta(enc, r._terrains[-1][1], tid)
                                if len(dl) < len(r._terrain[1]):
                                    return self.send_bytes(dl)
                    return self.send_bytes(r._terrain[1])
            if path == "/saves.json":
                return self.send_bytes(_dumps(list_saves()))
            if path == "/stalls.json":          # the server's stall watcher: lock holds >= STALL_MS, slow clock
                return self.send_bytes(_dumps(dict(stalls=list(r.stalls), lock_ms=STALL_MS)))
            if path == "/state_ticks.json":     # tests (tools/comms_check.mjs): the recorded snapshots [[tick, seq]]
                with r.lock:
                    return self.send_bytes(_dumps(dict(states=[[t, e[2]] for t, e in zip(r.state_ticks, r.states)])))
            if path == "/timeline.json":
                return self.send_bytes(_dumps(dict(live=True, server="live", snapshots=[])))
            return super().do_GET()

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/control" and body.get("new"):     # play mode: start an empty city
                with r.lock:
                    try:                                         # {"new": true[, "difficulty": "Hard"]}: else the map's default
                        g = Game(body.get("map", r.g.map_name), int(body.get("seed", 1)),
                                 difficulty=body.get("difficulty"))
                    except ValueError as ex:
                        return self.send_bytes(_dumps(dict(ok=False, out=str(ex))))
                    r.setup(g, r.save_path, None, r.rate)
                    r._tview = None
                    r._terrain = (None, b"")
                return self.send_bytes(_dumps(dict(ok=True, tick=r.g.tick)))
            if self.path == "/campaign":
                return self.send_bytes(_dumps(campaign_op(r, body)))
            if self.path == "/control" and ("save_as" in body or "load" in body or "delete" in body):
                f = save_file(body.get("save_as") or body.get("load") or body.get("delete"))
                if not f:
                    return self.send_bytes(_dumps(dict(ok=False, out="bad name: use letters, digits, spaces, - _ .")))
                try:
                    if "save_as" in body:
                        os.makedirs(SAVES, exist_ok=True)
                        with r.lock:
                            r.g.save(f)
                        return self.send_bytes(_dumps(dict(ok=True, out=f"saved {body['save_as']}", tick=r.g.tick)))
                    if not os.path.exists(f):
                        return self.send_bytes(_dumps(dict(ok=False, out="no such save")))
                    if "delete" in body:
                        os.remove(f)
                        return self.send_bytes(_dumps(dict(ok=True, out=f"deleted {body['delete']}")))
                    g = Game.load(f)                     # outside the lock: the city keeps running meanwhile
                    alerts.reset(g)                      # no alerts after a load (FUN_0040FFD0)
                    with r.lock:
                        r.setup(g, r.save_path, None, r.rate)
                        r._tview = None
                        r._terrain = (None, b"")
                    return self.send_bytes(_dumps(dict(ok=True, out=f"loaded {body['load']}", tick=r.g.tick)))
                except Exception as e:
                    traceback.print_exc()
                    return self.send_bytes(_dumps(dict(ok=False, out=f"{type(e).__name__}: {e}")))
            if self.path == "/control" and ("rate" in body or "paused" in body):   # live tabs: speed, pause
                with r.lock:
                    r.set_speed(body.get("rate"), body.get("paused"))
                    if "paused" in body:
                        if not r.paused:
                            r.error = ""        # resuming after an internal error: try again
                return self.send_bytes(_dumps(dict(ok=True, rate=r.rate, paused=r.paused)))
            if self.path == "/control" and "hover" in body:      # play mode: the build tool over the map, every
                h = body.get("hover")                               # change of tool / tile (walkers.shoo)
                with r.lock:
                    try:
                        from .systems import walkers as _w
                        r.g.hover = (_w.hover_rect(r.g, str(h[0]), int(h[1]), int(h[2]))
                                     if isinstance(h, list) and len(h) == 3 else None)
                    except Exception:
                        r.g.hover = None
                return self.send_bytes(_dumps(dict(ok=True)))
            if self.path == "/control":
                if isinstance(body.get("player"), str):    # play mode: the leader name of this browser (newgame.js)
                    messages.PLAYER = body["player"][:31] or "Ruler"
                    r.g.live_player = messages.PLAYER
                if body.get("save") and r.save_path:
                    with r.lock:
                        r.g.save(r.save_path)
                return self.send_bytes(_dumps(dict(ok=True)))
            if self.path == "/cmd":
                if body.get("tick") is not None and r.g.tick - int(body["tick"]) > r.live_window():
                    return self.send_bytes(_dumps(dict(ok=False, live=False, tick=r.g.tick,
                        out=f"not live: you are at tick {body['tick']}, the city is at {r.g.tick} (go live to build)")))
                if isinstance(body.get("cmds"), list):        # play mode: one drag = one batch
                    res = r.commands([str(c) for c in body["cmds"][:2000]])
                    return self.send_bytes(_dumps(dict(results=[dict(ok=a, out=b, tick=c, warn=d) for a, b, c, d in res],
                                                       seq=r.seq)))
                ok, out, tick, _ = r.command(body.get("cmd", ""))
                return self.send_bytes(_dumps(dict(ok=ok, out=out, tick=tick)))
            self.send_error(404)

    # host: 127.0.0.1 (this machine only) by default; --host 0.0.0.0 serves other machines too (a remote server)
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"live sim on http://{host}:{port}/  (save: {save}, script: {script}, {speed} ticks/s"
          f"{', test commands refused' if no_test else ''})")
    httpd.serve_forever()
