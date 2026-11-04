"""Terrain images for play mode (docs/play/terrain.md): presentation only, used by the live server.

The sim keeps terrain as flags; this module turns the current flags into the original's ground images
with tools/terrain_images.py, recomputing only the regions whose flags changed (as the original does
after a woodcutter, a demolition, a fire, a road). Nothing in sim/systems imports it.

The sim's semantics differ from the original's in one place: a cut tree clears flag 0x1 and waits in
g.regrow, where the original keeps 0x1 and sets regrowth 0 (a stump). We rebuild the original's view:
tiles waiting in g.regrow get 0x1 back with regrowth 0. Quarried marble keeps its flag; its depth
(g.quarry {(x, y): 100 shallow | 0 deep}, docs/logic/map-terrain.md 5b) is the original's regrowth byte. Meadow
eaten by grazers (g.grass_bare) gets its regrowth byte from walkers.picture_regrowth (the meadow picture follows it a
day late, as figure_graze leaves the picture to the next daily regrow).
"""
import os
import sys

import numpy as np

from .world import MAPS, N, read_map

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import mapfile  # noqa: E402
import terrain_images as ti  # noqa: E402
import terrain_cliffs as tcl  # noqa: E402

ROAD = 0x40


def _denorm(ids):
    """Our ids (collection 5 = Zeus_Terrain) -> v247 numbering, which terrain_images expects as orig_ids."""
    ids = np.asarray(ids, np.int64)
    return np.where((ids >> 14) >= 4, ids - (2 << 14), ids).astype(np.uint32)


class TerrainView:
    def __init__(self, g):
        hdr, blocks = read_map(g.map_name)
        d = {b["rank"]: b["data"] for b in blocks}
        grid = lambda r, dt: np.frombuffer(d[r], dt)[:N * N].reshape(N, N).copy()
        self.rand, self.scrub, self.meadow = grid(8, "u1"), grid(22, "u1"), grid(15, "u1")
        self.piece = grid(7, "u1")
        self.map_flags = grid(6, "<u4")                     # the map's terrain: tiles the game changed are repainted
        self.v247 = hdr["version"] < 300
        orig = grid(4, "<u4")
        self.ids = ti.norm_ids(orig) if self.v247 else orig
        self.draw = grid(5, "u1")
        self.draw0 = self.draw.copy()                       # cliffs are not computed: keep the map's draw bytes
        self.flags, self.regrowth = self.view(g)
        self.alt = {}                                       # (x, y) -> id deltas of views 2, 4, 6 (rotation.md)
        self.update(g, force=True)
        # tiles never recomputed keep the map's ids: their other-view deltas from one full pass, kept where
        # that pass gives the same view-0 id
        alt = {}
        ids = ti.images_full(self.flags, None, self.rand, _denorm(self.ids), scrub=self.scrub, meadow=self.meadow,
                             regrowth=self.regrowth, piece=self.piece,
                             desirability=g.world.des.clip(-128, 127).astype(np.int8), alt=alt)[0]
        for (x, y), d in alt.items():
            if (x, y) not in self.alt and ids[y, x] == self.ids[y, x]:
                self.alt[(x, y)] = d
        # cliffs of the turned views (tools/terrain_cliffs.py; the exe recomputes them on every turn): {view:
        # [[tile index, id, draw byte]]} for the cliff tiles; static during play but after a landslide (slid)
        self.cliff_views = {}
        w = g.world
        for v in (2, 4, 6):
            ids_v, drw_v, fl_v = tcl.cliffs(self.flags, w.elev, self.rand, v)
            ys, xs = np.nonzero((fl_v & 0x200) > 0)
            self.cliff_views[v] = [[int(y) * N + int(x), int(ids_v[y, x]), int(drw_v[y, x])] for y, x in zip(ys, xs)]
        self._ramp_roads = None                             # the turned views' road ramps too
        self.ramp_roads(g, self.flags, g.world.des.clip(-128, 127).astype(np.int8))

    def view(self, g):
        """The sim's state as the original's flag + regrowth grids."""
        w = g.world
        f = w.flags & np.uint32(~ROAD & 0xFFFFFFFF)          # roads come from the sim (map flags can be stale)
        f[w.road] |= ROAD
        reg = np.full((N, N), 255, np.uint8)
        for _, x, y in getattr(g, "regrow", []):
            if not w.occ[y, x] and not w.road[y, x]:
                f[y, x] |= 0x1
                reg[y, x] = 0
        for (x, y), d in getattr(g, "quarry", {}).items():
            reg[y, x] = d
        from .systems import walkers                      # meadow eaten by grazers: its regrowth byte (meadow_day)
        for (x, y) in list(g.__dict__.get("grass_bare", {})):
            if f[y, x] & 0x800:
                reg[y, x] = walkers.picture_regrowth(g, x, y)
        return f, reg

    def update(self, g, force=False):
        """Recompute the regions whose flags changed since the last call. Returns True if anything did."""
        f, reg = self.view(g)
        st = g.__dict__.get("disasters")            # earthquake cracks: rock 0x300002 with piece 0x80 (0x0056D300)
        lava = set()
        if st is not None:
            from . import disasters
            for x, y in disasters.cracked_tiles(g):
                self.piece[y, x] |= 0x80
            lava = set(disasters.lava_tiles(g))     # lava nodes' tiles (FUN_00520820 / FUN_00507980)
        if not hasattr(self, "lava_edge"):
            self.lava_edge = {}                     # (x, y) -> T_LAVA ks: ground + tinted SPR_LAVA overlay
        if force:                                   # fault tiles: the map stores the editor's cracks (terrain_images.EDITOR)
            changed = (f != g.world.flags) | (reg != 255) | ((f & ROAD) > 0) | ((f & 0x2000000) > 0)
            # every tile whose terrain differs from the map's: a loaded save's lava, quake rock, rubble, cleared
            # trees (the map's ids are the terrain before them). Before 11-04 only the tiles above were repainted on
            # load: a cooled lava field showed the map's grass until a build next to it re-matched the area (bug 450)
            changed |= f != self.map_flags
        else:
            changed = (f != self.flags) | (reg != self.regrowth)
        self.flags, self.regrowth = f, reg
        ys, xs = np.nonzero(changed)
        if not len(xs):
            return False
        rects = []
        for x, y in zip(xs.tolist(), ys.tolist()):          # footprint +1 right/bottom, merged
            r = [max(0, x - 1), max(0, y - 1), min(N - 1, x + 1), min(N - 1, y + 1)]
            for q in rects:
                if r[0] <= q[2] + 1 and q[0] <= r[2] + 1 and r[1] <= q[3] + 1 and q[1] <= r[3] + 1:
                    q[:] = [min(q[0], r[0]), min(q[1], r[1]), max(q[2], r[2]), max(q[3], r[3])]
                    break
            else:
                rects.append(r)
        des = g.world.des.clip(-128, 127).astype(np.int8)
        for r in rects:
            rect = ti.expand_rect(f, tuple(r), self.draw)
            alt = {}
            le = {}
            ids, drw, pc = ti.images_full(f, None, self.rand, _denorm(self.ids), scrub=self.scrub,
                                          meadow=self.meadow, regrowth=reg, piece=self.piece,
                                          desirability=des, rect=rect, alt=alt, lava=lava, lava_edge=le)
            x0, y0, x1, y1 = rect
            for k in [k for k in self.lava_edge if x0 <= k[0] <= x1 and y0 <= k[1] <= y1]:
                del self.lava_edge[k]
            self.lava_edge.update(le)
            for k in [k for k in self.alt if x0 <= k[0] <= x1 and y0 <= k[1] <= y1]:
                del self.alt[k]
            self.alt.update(alt)
            self.ids[y0:y1 + 1, x0:x1 + 1] = ids[y0:y1 + 1, x0:x1 + 1]
            self.draw[y0:y1 + 1, x0:x1 + 1] = drw[y0:y1 + 1, x0:x1 + 1]
            self.piece[y0:y1 + 1, x0:x1 + 1] = pc[y0:y1 + 1, x0:x1 + 1]
        self.slid(g, f, des)
        cliff = (f & 0x200) > 0
        self.draw[cliff] = self.draw0[cliff]
        self.ramp_roads(g, f, des, changed)
        return True

    def slid(self, g, f, des):
        """After a landslide (sim/disasters/landslide.py: elevation changed, the exe's cliff passes re-ran): the cliff
        pictures of every view around the changed tiles (+-4) from tools/terrain_cliffs.py."""
        ls = g.__dict__.get("landslide")
        n = len(ls["slides"]) if ls else 0
        if n == getattr(self, "_slides", 0):
            return
        self._slides = n
        area = np.zeros((N, N), bool)
        for s in ls["slides"]:
            for x, y in s["tiles"]:
                area[max(0, y - 4):y + 5, max(0, x - 4):x + 5] = True
        ys, xs = np.nonzero(area)                   # map_tiles_update_images on the box: every tile repainted (a
        rect = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))    # lowered plateau tile keeps its flags)
        boxes = [s["box"] for s in ls["slides"] if s.get("box")]
        if boxes:                                   # the exe's call: (box +- 3, mode 3), mode bit 2 grows the rect by
            r = [max(0, min(b[0] for b in boxes)), max(0, min(b[1] for b in boxes)),     # FUN_0051F210 (rock, cliff
                 min(N - 1, max(b[2] for b in boxes)), min(N - 1, max(b[3] for b in boxes))]   # blocks never cut):
            rect = ti.expand_rect(f, tuple(r), self.draw)   # the plain ground around is re-stamped too (bugs.md 366)
        alt = {}
        ids, drw, pc = ti.images_full(f, None, self.rand, _denorm(self.ids), scrub=self.scrub, meadow=self.meadow,
                                      regrowth=self.regrowth, piece=self.piece, desirability=des, rect=rect, alt=alt)
        x0, y0, x1, y1 = rect
        for k in [k for k in self.alt if x0 <= k[0] <= x1 and y0 <= k[1] <= y1]:
            del self.alt[k]
        self.alt.update(alt)
        self.ids[y0:y1 + 1, x0:x1 + 1] = ids[y0:y1 + 1, x0:x1 + 1]
        self.draw[y0:y1 + 1, x0:x1 + 1] = drw[y0:y1 + 1, x0:x1 + 1]
        self.piece[y0:y1 + 1, x0:x1 + 1] = pc[y0:y1 + 1, x0:x1 + 1]
        w = g.world
        cv = getattr(self, "cliff_views", None)     # None in __init__'s first update: made from the new grids after
        for v in ((0, 2, 4, 6) if cv is not None else (0,)):
            ids_v, drw_v, fl_v = tcl.cliffs(f, w.elev, self.rand, v, desirability=des)
            cl = area & ((fl_v & 0x200) > 0)
            if v == 0:
                self.ids[cl] = ids_v[cl]
                self.draw0[cl] = drw_v[cl]
                continue
            ys, xs = np.nonzero(cl)
            keep = [r for r in self.cliff_views.get(v, []) if not area[r[0] // N, r[0] % N]]
            self.cliff_views[v] = keep + [[int(y) * N + int(x), int(ids_v[y, x]), int(drw_v[y, x])]
                                          for y, x in zip(ys, xs)]

    def ramp_preview(self, g, tiles, view):
        """The road drag's preview over ramps (bugs.md 464): roads_drag_place(1) 0x0049ACB0 sets the route's road bits
        in the terrain and map_tiles_update_images redraws the rectangle, so the cliff matcher FUN_0045E110 gives each
        ramp tile of the route its road picture (oracle slope-road d1..d3 = the built road). [[tile index, id, draw]]
        in `view` for the cliff tiles next to a route tile on a ramp without a road (the tile, its long-ramp partner),
        from tools/terrain_cliffs.py on our flags with those roads (one whole-map matcher run per new set, cached)."""
        f = self.flags
        add = sorted({int(y) * N + int(x) for x, y in tiles if f[y, x] & 0x400 and not f[y, x] & ROAD})
        if not add:
            return []
        key = (view, tuple(add), getattr(g, "map_version", 0))
        cache = self.__dict__.setdefault("_rp_cache", {})
        if key in cache:
            return cache[key]
        f2 = f.copy()
        near = np.zeros((N, N), bool)
        for i in add:
            y, x = divmod(i, N)
            f2[y, x] |= ROAD
            near[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = True
        des = g.world.des.clip(-128, 127).astype(np.int8)
        ids_v, drw_v, fl_v = tcl.cliffs(f2, g.world.elev, self.rand, view, desirability=des)
        ids_0, drw_0, _ = tcl.cliffs(f, g.world.elev, self.rand, view, desirability=des)   # without: only what changes
        ys, xs = np.nonzero(near & ((fl_v & 0x200) > 0) & ((ids_v != ids_0) | (drw_v != drw_0)))
        out = [[int(y) * N + int(x), int(ids_v[y, x]), int(drw_v[y, x])] for y, x in zip(ys, xs)]
        if len(cache) > 16:
            cache.clear()
        cache[key] = out
        return out

    def ramp_roads(self, g, f, des, changed=None):
        """Roads on ramps (docs/play/terrain.md 3): the exe's cliff matcher FUN_0045E110 gives a ramp tile with road 0x40
        its road picture, code + 8 when FUN_004A0480 (not beach, desirability > 4) else + 4 (E1_xROAD2 / _xROAD1, EH_*
        for long ramps), and the long ramp's partner tile image + 1; road placement re-runs it on the rect (0x00460290
        re-stamps). Here: the tiles around a ramp road (or one that had a road) take tools/terrain_cliffs.py's answer,
        in every view."""
        rr = ((f & 0x400) > 0) & ((f & ROAD) > 0)
        prev = getattr(self, "_ramp_roads", None)
        near = rr | (prev if prev is not None else False)
        self._ramp_roads = rr
        if not near.any():
            return
        # The matcher runs on the whole map in 4 views (~0.15 s each): only when its answer around the ramp roads can
        # differ, i.e. the ramp-road set changed, a ramp road's desirability crossed FUN_004A0480's > 4, or a changed
        # tile lies within 4 of one (the matcher's reach, as slid's box). Before 11-03 every terrain update ran it: the
        # daily meadow regrowth redraw held the server lock ~0.3-0.7 s, and every live tab's walkers stopped (bug 442)
        hi = (des > 4) & rr
        same = prev is not None and changed is not None and np.array_equal(prev, rr) and \
            np.array_equal(getattr(self, "_ramp_des", None), hi)
        self._ramp_des = hi
        if same:
            reach = np.zeros((N + 8, N + 8), bool)
            for dy in range(9):
                for dx in range(9):
                    reach[dy:dy + N, dx:dx + N] |= near
            if not (reach[4:N + 4, 4:N + 4] & changed).any():
                return
        k = np.zeros((N + 2, N + 2), bool)
        for dy in (0, 1, 2):
            for dx in (0, 1, 2):
                k[dy:dy + N, dx:dx + N] |= near
        near = k[1:N + 1, 1:N + 1] & ((f & 0x200) > 0)
        w = g.world
        cv = getattr(self, "cliff_views", None)     # None in __init__'s first update: made from the new grids after
        for v in ((0, 2, 4, 6) if cv is not None else (0,)):
            ids_v, drw_v, fl_v = tcl.cliffs(f, w.elev, self.rand, v, desirability=des)
            if v == 0:
                self.ids[near] = ids_v[near]
                continue
            ys, xs = np.nonzero(near & ((fl_v & 0x200) > 0))
            new = {int(y) * N + int(x): [int(y) * N + int(x), int(ids_v[y, x]), int(drw_v[y, x])] for y, x in zip(ys, xs)}
            old = getattr(self, "cliff_views", {}).get(v)
            if old is not None:
                self.cliff_views[v] = [new.pop(r[0], r) if r[0] in new else r for r in old] + list(new.values())
