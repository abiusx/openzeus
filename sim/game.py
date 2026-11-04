"""Game: state + tick loop + commands. Deterministic for a given seed and command sequence."""
import pickle

import numpy as np
import random

from .data import Catalog
from .model import Building, City, Walkers
from .world import World, map_difficulty, migrate_points, play
from . import systems
from .systems import shore, ranch
from . import empire, military, heroes
from . import scenario
from . import gods
from . import alerts
from . import savefile
from . import testcmds
from . import allowed

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# Game.road_drag's floods by start tile, for the passability mask they were made on (roaddrag.Grids.passable, keyed
# by content: any change, trees cut or regrown too, starts afresh; a drag asks again on every move, bugs.md 95).
# Not part of the game: never pickled.
_ROUTE_CACHE = {}
_ROAD_GRIDS = {}            # road_grids' constant parts: the play edge by map size, (piece 0x80, random grid) by map


WAGE_LEVELS = (0, 20, 26, 30, 34, 40)       # wage slider values 0x00641F38 (text group 285 None..Very high)


def year_treasury_of(g):
    """The treasury at the current year's start for a save from before g.year_treasury (11-04): the last monthly
    snapshot of the year before (taken at our month change, where ledger_year_rollover 0x00488840 sets
    _DAT_00fe971c), else the game's starting funds (an episode's scenario funds x the difficulty's share; a colony or
    continued city's carried treasury is not in such a save: the rules' funds as before)."""
    y = g.month_index // 12
    end = [h["treasury"] for h in g.history if "mi" in h and h["mi"] // 12 == y - 1]
    if end:
        return end[-1]
    funds = g.start_funds if (g.__dict__.get("episode") or {}).get("start") == "new_city" else g.rules["start_funds"]
    return funds * g.rules.get("start_funds_pct", 100) // 100


def tax_levels(g):
    """Tax slider values 0x00641F50: 0, 3, 7, 9, 11, 15, 20 (rules tax_levels)."""
    return [lv["rate"] for lv in g.rules["tax_levels"]]


def snap_level(levels, v):
    """The slider value nearest to v, ties to the lower (tax_level_index 0x005697F0 / wage_level_index
    0x00569610 scan upward with a strict <)."""
    return min(levels, key=lambda x: (abs(v - x), x))


class CommandError(Exception):
    """A refused command. warn: the original's warning for it, text ids in group 19 (title[, hint]),
    which the play mode shows instead of our technical message (build_commit 0x00498910 messages)."""
    def __init__(self, msg, warn=None):
        super().__init__(msg)
        self.warn = warn


def bridge_piece(i, n, d):
    """Bridge piece number of tile i (0 = the clicked tile A) of an n-tile span going in exe direction d
    (FUN_0041D720, non race-track branch; docs/logic/bridges.md "Pieces"). d: 0 = step -228 (north), 2 = +1 (east),
    4 = +228 (south), 6 = -1 (west). 13/14: short (< 4 tiles); 1..12: long (ends 1/6/7/12 draw nothing)."""
    ns = d in (0, 4)
    if n < 4:
        return 14 if ns else 13
    if i == n - 1:
        return {0: 12, 2: 6, 4: 7, 6: 1}[d]
    if i == 0:
        return {0: 7, 2: 1, 4: 12, 6: 6}[d]
    if i == n - 2:
        return {0: 11, 2: 5, 4: 8, 6: 2}[d]
    if i == 1:
        return {0: 8, 2: 2, 4: 11, 6: 5}[d]
    return (9 + (i & 1)) if ns else (4 - (i & 1))


BRIDGE_DIR = {(0, -1): 0, (1, 0): 2, (0, 1): 4, (-1, 0): 6}      # step (dx, dy) -> exe direction


class Game:
    def __init__(self, map_name="sandbox", seed=1, catalog=None, difficulty=None, start=None):
        """start: an episode start (sim/episode.py new_city / colony), None = open play on the map: its episode
        when data/maps.json names one (sandbox, sandbox2: as the exe), else unrestricted (sandbox_open, "ours")."""
        if difficulty is None:                      # the map's default (data/maps.json; docs/logic/difficulty.md)
            difficulty = catalog.rules.get("difficulty", "Normal") if catalog else map_difficulty(map_name)
        if start is None:                           # sandbox_open plays map "sandbox" (data/maps.json "map")
            map_name, ep_ref = play(map_name)
            if ep_ref:
                from . import episode
                start = episode.open_play(ep_ref)
        self.difficulty = difficulty
        self.cat = catalog or Catalog(difficulty=difficulty)
        self.rules = self.cat.rules
        self.world = World(map_name)
        self.map_name = map_name
        self.rng = random.Random(seed)
        self.seed = seed
        self.tick = 0
        self.labor_prio_v = 1                       # labor priorities start at 3 (Game.load migrates older saves)
        self.fire_v = 1                             # ranches may burn (bug 290; Game.load resets older ranches' risk)
        self.goods_v = 1                            # Poseidon goods off while Poseidon is off (Game.load purges older saves)
        self.tick_v = 1                             # the cycle step before the figure pass (11-02; Game.load migrates)
        self.stump_v = 1                            # stumps keep the tree bit 0x1 (11-02; Game.load migrates)
        self.buildings = {}
        self.walkers = Walkers()                # id -> Walker, with the exe's figure slots (model.Walkers)
        self.next_bid = 1
        self.next_wid = 1
        # treasury = scenario funds x start_funds_pct[difficulty] / 100 (0x0051D5F0, table 0x005F7F08)
        self.city = City(treasury=self.rules["start_funds"] * self.rules.get("start_funds_pct", 100) // 100,
                         tax_rate=self.rules["tax_rate"],
                         wage_rate=self.rules["wage_rate"])
        self.year_treasury = self.city.treasury     # _DAT_00fe971c: the treasury at the year's start (0x0051D5F0)
        self.log = []           # executed commands: (tick, text)
        self.history = []       # monthly snapshots for graphs
        self.visits = {}        # role -> {road tile: last tick walked} (roaming memory)
        systems.roads.rebuild(self)     # the map's own roads (World.road from terrain 0x40; bugs.md 233)
        if start is not None:
            from . import episode
            episode.init(self, start)   # the carried date, before the modules start (colony starts)
        empire.new_game(self, start)    # the scenario's world cities (sim/empire; `empire off` for data/trade.json partners)
        scenario.new_game(self, start and start.get("episode"))   # the episode's scheduled events and god block
        if start is not None:
            episode.apply(self, start)  # start year, funds, switches (sim/episode.py)
        elif self.scenario is not None:  # the calendar starts in the episode's year (scenario block +0 ->
            self.year0 = self.scenario.info["start_year"]   # scenario_start_year 0x00902928, episode_start_load)

    # --- calendar -----------------------------------------------------------------------
    @property
    def day(self):
        return self.tick // self.rules["ticks_per_day"]

    @property
    def month_index(self):
        """Months since the game's first month. months0 (episodes only, sim/episode.py): months the calendar moved
        while this city was not played (a colony episode in between, or a colony's start after its parent's)."""
        return self.day // self.rules["days_per_month"] + self.__dict__.get("months0", 0)

    @property
    def month(self):
        return self.month_index % 12

    @property
    def start_year(self):
        """The game's first year: the episode's (sandbox 1000 BC, sandbox2 1750 BC); games without an episode and
        saves from before 10-30: data/rules.json (1000 BC)."""
        return self.__dict__.get("year0", self.rules["start_year"])

    @property
    def year(self):
        return self.start_year + self.month_index // 12

    def date(self):
        y = self.year
        return f"{MONTHS[self.month]} {abs(y)} {'BC' if y < 0 else 'AD'}"

    def message(self, text):
        self.city.messages.append((self.tick, text))
        del self.city.messages[:-200]

    # --- simulation ---------------------------------------------------------------------
    def step(self, ticks=1):
        tpd = self.rules["ticks_per_day"]
        d = self.__dict__
        for _ in range(ticks):
            # simulation_tick 0x00513A30: simulation_cycle_step (step s = tick % 51, then month_advance after step
            # 50), terrain_events_update, then walkers_update. Ours counts the tick first: inside it, tick % 51 is
            # the exe's cycle_step after the step counted on (0 in month_advance, 30 after step 29, and during the
            # figure pass), and the state after N ticks is the oracle's dump N (entry of tick N; docs/logic/
            # time-core.md "Ours"). Before 11-02 the figure pass ran first: one pass ahead of the exe.
            if d.get("hover"):                  # a build tool over the map: the frames before this tick shoo
                systems.walkers.shoo(self)      # animals off its footprint (FUN_004059C0, walkers.shoo)
            self.tick += 1
            d["_in_tick"] = True
            try:
                if self.tick % tpd == 0:
                    systems.run_day(self)
                else:                           # cycle step s = tick % 51 - 1 (systems.STEPS)
                    systems.run_step(self, self.tick % tpd - 1)
                if self.tick % tpd == 30:       # cycle step 29
                    rec = getattr(self, "record_dir", None)
                    if rec and self.day % self.rules["days_per_month"] == 0:
                        from . import export
                        export.write(self, f"{rec}/{self.tick:08d}.json")
                military.standards(self)        # the companies' standards (fig_handler_standard): their morale part
                if "disasters" in d:            # terrain_events_update 0x00446A70: after the cycle step (sim/disasters)
                    from . import disasters
                    disasters.tick(self)
                    disasters.after_tick(self)
                systems.walkers.move_all(self)
            finally:
                d.pop("_in_tick", None)

    # --- building ------------------------------------------------------------------------
    def spend(self, amount, line):
        if self.city.treasury < -1999:          # build_commit 0x00498910 step 2: the treasury before, not after
            raise CommandError(f"not enough money ({self.city.treasury} dr, need {amount})", (19,))
        self.city.treasury -= amount
        self.city.ledger[line] = self.city.ledger.get(line, 0) - amount

    def build(self, key, x, y, extra=None):
        if key not in self.cat.buildings or key == "ruin":
            raise CommandError(f"unknown building '{key}' (see catalog)")
        spec = self.cat.spec(key)
        if spec.get("poseidon") and not getattr(self, "poseidon", False):
            raise CommandError(f"{spec['name']} is a Poseidon building (Zeus only by default; `poseidon on` allows it)")
        why = allowed.check(self, key)              # the episode's allowed buildings (sim/allowed.py; open play: all)
        if why:
            raise CommandError(why)
        if spec["kind"] in ("storage", "trade"):  # storage_create 0x00494960 starts with rebuild_goods_lists
            allowed.mark(self)
        if spec["kind"] == "road":
            return self.road(x, y, x, y)
        if spec["kind"] in ("gatehouse", "tower"):    # build gatehouse X Y [h|v]
            return self._wall_building(key, spec, x, y, extra)
        if spec["kind"] in ("bridge", "wall"):
            raise CommandError(f"use `{spec['kind']} X1 Y1 X2 Y2`")
        if spec["kind"] == "avenue":
            raise CommandError(f"use `{key} X1 Y1 X2 Y2`: drag along a road")
        if key == "palace" and any(b.key == "palace" for b in self.buildings.values()):
            # build_commit 0x00498910: type 0x75 while g_palace_exists -> message 0x14 (19:20)
            raise CommandError("Only one of this building allowed (one palace per city)", (20,))
        if spec["kind"] == "monument":
            why = gods.can_build(self, key)           # the Mythology menu / sanctuary limit (sim/gods)
            if why:
                raise CommandError(why)
            return self._monument(key, spec, x, y, extra)
        if key == "tax_office" and not any(b.key == "palace" for b in self.buildings.values()):
            raise CommandError("a tax office needs a palace (buildings.md: placement check 0xDD)", (221,))
        if spec["kind"] == "agora":            # build agora X Y [down|up|left|right] / grand_agora X Y [h|v]
            return systems.agora.build(self, key, x, y, extra)
        if key == "museum" and systems.stadium.exists(self):
            # g_unique_venue_exists 0x00FEAED0 (buildings.md): one stadium OR museum per city; the museum's
            # placement check refuses with 19:20 (the stadium's, 0x005B03A0, with 19:44: stadium.check)
            raise CommandError("only one stadium or museum per city", (20,))
        if key == "stadium":                  # build stadium X Y [v|h]: two 5x5 halves (systems/stadium.py)
            return systems.stadium.build(self, x, y, extra)
        if spec["kind"] == "vendor" and systems.agora.stall_at(self, x, y):
            return systems.agora.open_stall(self, key, x, y)
        if spec["kind"] == "vendor" and key != "chariot_vendor":      # the original has no standalone stalls
            raise CommandError(f"{key} goes on an empty stall of an agora (build agora X Y [side] first)", (41,))
        if spec["kind"] == "roadblock":
            if not self.roadblock_ok(x, y):
                raise CommandError("a roadblock must be placed on a plain road tile (not on an agora, a bridge "
                                   "or a ramp)", (42,))
            rb = self.sd("roadblocks", set())
            if (x, y) in rb:
                raise CommandError(f"there is already a roadblock at ({x},{y})")
            self.spend(spec["cost"], "construction")
            rb.add((x, y))
            self.map_version = getattr(self, "map_version", 0) + 1
            systems.roads.rebuild(self)             # entrances never sit on a roadblock
            return f"roadblock at ({x},{y}), cost {spec['cost']}: roaming walkers turn back here"
        if spec["kind"] == "animal":            # sheep/goats are walkers, not buildings
            w = self.world
            if not (w.inside(x, y) and w.flags[y, x] & (0x800 | 0x10000) and not w.occ[y, x] and not w.road[y, x]
                    and not w.avenue[y, x]):
                b = self.buildings.get(int(w.occ[y, x])) if w.inside(x, y) else None
                why = ("off the map" if not w.inside(x, y) else f"a {b.key}" if b else "road" if w.road[y, x] or
                       w.avenue[y, x] else w.kind(x, y))
                raise CommandError(f"{key} must be placed on free meadow (',' in look); ({x},{y}) is {why}", (208,))
            why = self.walker_on(x, y, 1, 1)    # build_commit 0x00498910 step 6: no walker but type 24 on the tile
            if why:
                raise CommandError(f"can't place {key} at ({x},{y}): {why}", (208,))
            have, cap = systems.walkers.animal_count(self, spec["animal"])
            if have >= cap:                      # FUN_004F92A0: fewer than 8 per farm (production.md)
                first = {"sheep": 209, "goat": 213, "cattle": 251}.get(spec["animal"], 209)   # 19:209.. per kind
                raise CommandError(f"{key}: {have} already, at most 8 per farm ({cap // 8} farms)",
                                   (first, first + 1) if cap == 0 else (first + 2, first + 3))
            self.spend(spec["cost"], "construction")
            a = systems.walkers.spawn_animal(self, spec["animal"], x, y)
            return f"placed {key} #{a.id} at ({x},{y}), cost {spec['cost']}"
        if key == "water_park" and extra not in (None, "") and not (str(extra).isdigit() and int(extra) <= 7):
            raise CommandError("water park variant is 0..7")
        if key in shore.KEYS:                  # half over water (systems/shore.py, bugs.md 131)
            return self._shore(key, spec, x, y, extra)
        if key == "horse_ranch":               # 3x3 house + 4x4 corral (systems/ranch.py, bugs.md 134)
            return self._ranch(key, spec, x, y, extra)
        variant = orient = None
        if key == systems.commemorative.KEY:    # granted by events, placed from Aesthetics > Monuments (variant V)
            try:                                # build commemorative_monument X Y [V|auto] [O 0..3]
                variant, orient = systems.commemorative.take(self, extra)
            except ValueError as e:
                raise CommandError(str(e))
        hero = None
        if key == "heroes_hall":               # build heroes_hall X Y HERO: a needed hero without a hall (0x004FA620)
            try:
                hero = heroes.hall_allowed(self, extra)
            except ValueError as e:
                raise CommandError(str(e))
        size = spec["size"] if variant is None else systems.commemorative.size(variant)
        ok, why = self.world.area_ok(x, y, size)
        if ok:
            why = self.walker_on(x, y, size, size)
            ok = not why
        if not ok:
            if why.endswith("is rubble"):     # as the exe (map_area_buildable mask 0x3DFFD66F has rubble 0x1000)
                why += " (clear it first: `clear X1 Y1 X2 Y2`, 2 dr a tile)"
            why = self.occupied_text(why)
            span = f" ({size}x{size}: ({x},{y})-({x + size - 1},{y + size - 1}))" if size > 1 else ""
            raise CommandError(f"can't build {key} at ({x},{y}){span}: {why}", (18,))
        why = self.site_error(key, x, y)
        if why:
            raise CommandError(why, (208,) if spec.get("needs") == "meadow" else (23,) if spec.get("needs") == "coast" else None)
        w = self.world
        if spec["kind"] == "trade":
            try:
                c = systems.trade.pick(self, key, extra)
            except ValueError as e:
                raise CommandError(str(e))
        self.spend(spec["cost"], "construction")
        b = Building(id=self.next_bid, key=key, x=x, y=y, size=size, kind=spec["kind"],
                     level=7 if spec.get("elite") else 0)
        if spec["kind"] == "trade":
            b.misc.update(partner=c, orders={}, limits={})
        if key == "water_park" and extra not in (None, ""):   # build water_park X Y [0..7]: the R key's picture
            b.misc["variant"] = int(extra)                     # variant (exe FUN_0041BC90 -> +0x12; bugs.md 136)
        if variant is not None:                                # +0x12 = variant (building_create 0x00493E70)
            b.misc["variant"] = variant
            if orient:                                         # +0xAC = the R key's DAT_00DA23C4 (god statues face it)
                b.misc["orient"] = orient
            systems.commemorative.placed_one(self, variant)
        if hero is not None:                                   # +0x12 = hero id, record +0x04 = hall (0x004FA6B0)
            b.misc["hero"] = hero
        self.next_bid += 1
        self.buildings[b.id] = b
        w.occ[y:y + size, x:x + size] = b.id
        w.flags[y:y + size, x:x + size] &= np.uint32(~0x1000 & 0xFFFFFFFF)     # building clears rubble
        self.map_version = getattr(self, "map_version", 0) + 1
        systems.roads.update_access(self, b)
        warn = "" if b.access or spec["kind"] in ("decor", "orchard") else "  WARNING: no road access (needs a road touching one side)"
        if spec["kind"] == "trade":
            warn += f"  trades with {systems.trade.partners(self)[c]['name']}"
        return f"built {key} #{b.id} at ({x},{y}) size {size}, cost {spec['cost']}{warn}"

    def _ranch(self, key, spec, x, y, extra=None):
        """build horse_ranch X Y [0..3|e|n|w|s]: the 3x3 ranch house at (X, Y) and its 4x4 corral at the orientation
        offset (0 east = the exe's default, 1 north, 2 west, 3 south; FUN_00496CA0 case 0x85, table 0x00637E60)."""
        try:
            o = ranch.orient_arg(extra)
        except ValueError as e:
            raise CommandError(str(e))
        why, _ = ranch.check(self, x, y, o)
        if why:
            raise CommandError(f"can't build {key} at ({x},{y}) {ranch.LETTER[o]}: {why}", (18,))
        self.spend(spec["cost"], "construction")
        b = Building(id=self.next_bid, key=key, x=x, y=y, size=3, kind=spec["kind"])
        self.next_bid += 1
        self.buildings[b.id] = b
        self.world.occ[y:y + 3, x:x + 3] = b.id
        ranch.attach(self, b, o)
        systems.roads.update_access(self, b)
        warn = "" if b.access else "  WARNING: no road access (needs a road touching one side)"
        cx, cy = b.misc["corral"]
        return f"built {key} #{b.id} at ({x},{y}) size 3, corral ({cx},{cy}) 4x4 {ranch.LETTER[o]}, cost {spec['cost']}{warn}"

    def _shore(self, key, spec, x, y, extra=None):
        """build fishing_wharf|urchin_quay|trireme_wharf X Y [n|e|s|w], build dock X Y [PARTNER][,n|e|s|w]: (X, Y) is
        the anchor of the half-water square (the dock's pier); without a side the first orientation that fits
        (FUN_004A10C0 / FUN_004A14B0, production.md "Shore buildings"); the dock house goes behind the pier."""
        toks = [t for t in str(extra or "").replace(",", " ").split() if t]
        side = [t for t in toks if t.lower() in shore.NAMES or t.lower() in ("auto", "a")]
        rest = [t for t in toks if t not in side]
        try:
            o = shore.orient_arg(side[-1] if side else None)
        except ValueError as e:
            raise CommandError(str(e))
        why = shore.site_error(self, key, x, y, o)
        if why:
            raise CommandError(why[0], why[1])
        o = shore.fit(self, key, x, y, o)
        if spec["kind"] == "trade":
            try:
                c = systems.trade.pick(self, key, rest[0] if rest else None)
            except ValueError as e:
                raise CommandError(str(e))
        self.spend(spec["cost"], "construction")
        bx, by, size, tiles, misc = shore.layout(key, x, y, o)
        b = Building(id=self.next_bid, key=key, x=bx, y=by, size=size, kind=spec["kind"])
        b.misc.update(misc)
        if spec["kind"] == "trade":
            b.misc.update(partner=c, orders={}, limits={})
        self.next_bid += 1
        self.buildings[b.id] = b
        w = self.world
        for tx, ty in tiles:
            w.occ[ty, tx] = b.id
        self.map_version = getattr(self, "map_version", 0) + 1
        systems.roads.update_access(self, b)
        warn = "" if b.access else "  WARNING: no road access (needs a road touching one side)"
        if spec["kind"] == "trade":
            warn += f"  trades with {systems.trade.partners(self)[c]['name']}"
        where = f"pier ({x},{y}) facing {shore.LETTER[o]}, dock house ({bx},{by}) 4x4" if key == "dock" \
            else f"({x},{y}) size {size} facing {shore.LETTER[o]}"
        return f"built {key} #{b.id} at {where}, cost {spec['cost']}{warn}"

    # gatehouse pieces (FUN_004E5480 check / FUN_004E4FA0 place, table 0x0063A848: road_ok, size, a, b; the
    # piece is at (x+b, y+a) in orientation 0, (x+a, y+b) in orientation 1): two 2x2 towers and two passage
    # tiles between them that get the road bit (0x8048), so a road runs through.
    GATE_PIECES = ((False, 2, 0, 0), (True, 1, 2, 0), (True, 1, 2, 1), (False, 2, 3, 0))

    @staticmethod
    def gate_orient(d):
        """Command token -> exe orientation (Building+0xAC): h (default; build_tool_select 0x00404330 sets
        1) = 1, 5x2 along x, road through north-south; v = 0, 2x5 along y, road through east-west."""
        if d in (None, "", "h", "1", "x"):
            return 1
        if d in ("v", "0", "y"):
            return 0
        raise CommandError(f"gatehouse orientation is h (5x2, default) or v (2x5), not '{d}'")

    def gate_tiles(self, x, y, d=None):
        """[(x, y, passage)] of a gatehouse at (x, y) [h|v]."""
        o = self.gate_orient(d)
        out = []
        for road_ok, n, a, b in self.GATE_PIECES:
            px, py = (x + b, y + a) if o == 0 else (x + a, y + b)
            out += [(px + i, py + j, road_ok) for j in range(n) for i in range(n)]
        return out

    def _wall_building(self, key, spec, x, y, d=None):
        """Tower: 2x2, every tile a wall (terrain_area_all(x, y, 2, 0, 0x4000), else message 0x25), nothing
        else on it (map_area_buildable mask 0xFFFFBFFF). Gatehouse: 5x2 or 2x5 (gate_tiles); the towers on
        free land (mask -1: no road, no wall), each passage tile a road or free land; the passage becomes
        road. buildings.md §5. Both idle until invasions exist."""
        w = self.world
        if key == "tower":
            tiles = [(xx, yy) for yy in range(y, y + 2) for xx in range(x, x + 2)]
            for xx, yy in tiles:
                if not w.inside(xx, yy) or w.occ[yy, xx] or w.road[yy, xx] or w.avenue[yy, xx]:
                    raise CommandError(f"can't build {key} at ({x},{y}): ({xx},{yy}) is taken")
                if not w.flags[yy, xx] & 0x4000:
                    raise CommandError("a tower must stand on 2x2 wall tiles", (37,))
            passage = []
        else:
            o = self.gate_orient(d)
            land = getattr(w, "build_land", w.free_land)    # mask -1: rubble and beach refused too
            tiles, passage = [], []
            for xx, yy, road_ok in self.gate_tiles(x, y, d):
                tiles.append((xx, yy))
                if road_ok and w.inside(xx, yy) and w.road[yy, xx] and not w.occ[yy, xx]:
                    passage.append((xx, yy))
                    continue
                if not land(xx, yy):
                    raise CommandError(f"can't build a gatehouse at ({x},{y}): ({xx},{yy}) is "
                                       + ("off the map" if not w.inside(xx, yy) else "taken" if w.occ[yy, xx]
                                          else w.blocked_kind(xx, yy))
                                       + (" (road)" if w.inside(xx, yy) and w.road[yy, xx] else ""), (18,))
                if road_ok:
                    passage.append((xx, yy))
        self.spend(spec["cost"], "construction")
        b = Building(id=self.next_bid, key=key, x=x, y=y, size=2, kind=spec["kind"])
        if key == "gatehouse":
            b.misc.update(w=5 if o == 1 else 2, h=2 if o == 1 else 5, orient=o)
        self.next_bid += 1
        self.buildings[b.id] = b
        for xx, yy in tiles:
            w.occ[yy, xx] = b.id
        for xx, yy in passage:
            w.road[yy, xx] = True
        self.map_version = getattr(self, "map_version", 0) + 1
        systems.roads.rebuild(self)
        return f"built {key} #{b.id} at ({x},{y})" + (f" {b.misc['w']}x{b.misc['h']}" if passage else "")

    @staticmethod
    def monument_orient(d):
        """build KEY X Y [0..3]: the placement orientation (R key; exe DAT_00DA23C4 -> b+0x9C, composite_offset_rotate
        0x0053D9A0 / FUN_0053C390: 0 as the layout file, 1..3 turned by 90 degrees each; bugs.md 133)."""
        if d in (None, ""):
            return 0
        if str(d) in ("0", "1", "2", "3"):
            return int(d)
        raise CommandError(f"monument orientation is 0..3, not '{d}'")

    def _monument(self, key, spec, x, y, d=None):
        """Sanctuary / pyramid / palace: the whole layout box (w x h, turned with the orientation) must be free
        land (no level test: World.area_ok)."""
        w = self.world
        o = self.monument_orient(d)
        bw, bh = (spec["h"], spec["w"]) if o % 2 else (spec["w"], spec["h"])
        for yy in range(y, y + bh):
            for xx in range(x, x + bw):
                if not w.inside(xx, yy) or w.occ[yy, xx] or w.road[yy, xx] or w.avenue[yy, xx] or w.flags[yy, xx] & 0x4207:
                    raise CommandError(f"can't build {key} ({bw}x{bh}) at ({x},{y}): ({xx},{yy}) is not free land")
        self.spend(spec["cost"], "construction")
        b = Building(id=self.next_bid, key=key, x=x, y=y, size=0, kind="monument")
        self.next_bid += 1
        systems.monuments.create(self, b, o)
        self.buildings[b.id] = b
        w.occ[y:y + bh, x:x + bw] = b.id
        w.flags[y:y + bh, x:x + bw] &= np.uint32(~0x1000 & 0xFFFFFFFF)
        if key.startswith("sanctuary_"):
            systems.monuments.mark_ground(self, b)   # FUN_0053C390: terrain 0x10000000 on the layout box at placement
        self.map_version = getattr(self, "map_version", 0) + 1
        systems.roads.update_access(self, b)
        warn = "" if b.access else "  WARNING: no road access"
        return f"built {key} #{b.id} at ({x},{y}) {bw}x{bh}, {len(b.misc['pieces'])} pieces, cost {spec['cost']}{warn}"

    @staticmethod
    def wall_tiles(x1, y1, x2, y2, n=228):
        """The tiles a wall drag (x1, y1) -> (x2, y2) covers (walls_drag 0x0049AF50, military.md "Wall drag"):
        a straight rectangle along the longer axis, 1 or 2 tiles thick: the other coordinate of the end is
        held within 1 of the start's (|dx| > |dy|: along x; else, ties included, along y). Coordinates
        are clamped to the map first."""
        c = lambda v: max(0, min(n - 1, v))
        x1, y1, x2, y2 = c(x1), c(y1), c(x2), c(y2)
        if abs(x2 - x1) > abs(y2 - y1):
            y2 = max(y1 - 1, min(y1 + 1, y2))
        else:
            x2 = max(x1 - 1, min(x1 + 1, x2))
        return [(x, y) for y in range(min(y1, y2), max(y1, y2) + 1) for x in range(min(x1, x2), max(x1, x2) + 1)]

    def wall(self, x1, y1, x2, y2):
        """A wall drag (wall_tiles: straight, 1-2 thick); walls block walkers (gatehouses let roads through)."""
        w = self.world
        tiles = self.wall_tiles(x1, y1, x2, y2, w.flags.shape[0])
        # walls_drag 0x0049AF50 puts a wall on each tile with terrain & 0x1537166F == 0 (no road 0x40, no building
        # 0x8, ...) and silently skips the others: a road tile is never walled (military.md "Walls")
        land = getattr(w, "build_land", w.free_land)    # walls refuse rubble and beach too (mask 0x1537166F)
        new = [(x, y) for x, y in tiles if w.inside(x, y) and not w.flags[y, x] & 0x4000 and land(x, y)]
        bad = [(x, y) for x, y in tiles if not (w.inside(x, y) and w.flags[y, x] & 0x4000) and (x, y) not in new]
        if not new and bad:
            x, y = bad[0]
            raise CommandError(f"wall blocked at ({x},{y}): " + ("off the map" if not w.inside(x, y) else w.blocked_kind(x, y))
                               + (" (road: use a gatehouse)" if w.inside(x, y) and w.road[y, x] else ""))
        cost = len(new) * self.cat.spec("wall")["cost"]
        self.spend(cost, "construction")
        for x, y in new:
            w.flags[y, x] |= np.uint32(0x4000)
        self.map_version = getattr(self, "map_version", 0) + 1
        return f"wall {len(new)} tiles, cost {cost}" + (f" ({len(bad)} blocked tiles skipped)" if bad else "")

    def walker_tiles(self):
        """{(x, y): role} of the tiles walkers stand on (map_area_buildable 0x004A0DC0 walks grid_figure 0x00D0D878:
        any figure but FIG_AMBIENT 6 / FIG_ZGUY 0x18 refuses the tile; ours has neither kind)."""
        return {(wk.x, wk.y): wk.role for wk in self.walkers.values()}

    def walker_on(self, x, y, w, h, tiles=None):
        """'' or why a w x h footprint at (x, y) is refused for a walker standing on it (19:18 as other tiles).
        Not for script lines (script.apply)."""
        if getattr(self, "script_mode", False):
            # deviation (user-approved 10-28): scripts skip the walker rule, or sheep wandering onto build sites
            # make the benchmarks fail at random; in play the rule applies as in the exe
            return ""
        tiles = self.walker_tiles() if tiles is None else tiles
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if (xx, yy) in tiles:
                    return f"({xx},{yy}) has a walker on it ({tiles[(xx, yy)]})"
        return ""

    def bridge_site(self, x, y):
        tiles, step, why = self.bridge_scan(x, y)
        return (tiles, step) if why is None else (None, why)

    def bridge_scan(self, x, y):
        """The exe's bridge tool (FUN_0041C450, non race-track branch; docs/logic/bridges.md): the player
        points at a water tile A beside a shore. Returns (tiles, step, None), or (tiles scanned so far, step or None, reason) when refused (the play-mode ghost).
        - A: water, no road/building (0x48), no beach (0x10000) among its 4 neighbours;
        - the bridge runs away from A's first land neighbour in the order N, E, S, W (none: refused);
        - it steps on while the next tile is water, at most 15 steps (16 tiles): the next tile must not hold a
          tree, a road/building (0x48), and every stepped-on tile needs water on all 4 diagonals
          (FUN_004A36F0); a deep tile that is already road (another bridge) refuses;
        - the last water tile E: no bridge piece beside it (no parallel bridge; side neighbours); with 2+
          tiles E has exactly 3 water neighbours (land ahead), with 1 tile no beach beside it.
        Only the water tiles become road (FUN_0041D8B0 sets 0x40 and the piece number)."""
        w = self.world
        n = w.flags.shape[0]
        f = w.flags
        water = lambda x, y: 0 <= x < n and 0 <= y < n and bool(f[y, x] & 0x4)
        roadb = lambda x, y: bool(w.road[y, x] or w.occ[y, x])
        beach4 = lambda x, y: any(0 <= x + dx < n and 0 <= y + dy < n and f[y + dy, x + dx] & 0x10000
                                  for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)))
        if not water(x, y) or roadb(x, y):
            return [(x, y)], None, "a bridge starts on a water tile without a road"
        if beach4(x, y):
            return [(x, y)], None, "beach beside the bridge start"
        for (ax, ay), d in (((0, -1), 4), ((1, 0), 6), ((0, 1), 0), ((-1, 0), 2)):
            if not water(x + ax, y + ay):
                sx, sy = -ax, -ay
                break
        else:
            return [(x, y)], None, "a bridge starts on water beside a shore"
        tiles = [(x, y)]
        cx, cy = x, y
        bridges = self.sd("bridges", set())
        if water(cx + sx, cy + sy):
            for _ in range(15):
                cx, cy = cx + sx, cy + sy
                tiles.append((cx, cy))
                nx, ny = cx + sx, cy + sy
                if not (0 <= nx < n and 0 <= ny < n) or f[ny, nx] & 0x1:
                    return tiles, (sx, sy), "trees at the far end"
                if f[cy, cx] & 0x4000000 and w.road[cy, cx]:
                    return tiles, (sx, sy), "crosses another bridge"
                if not water(nx, ny):
                    break
                if roadb(nx, ny):
                    return tiles, (sx, sy), "road or building in the way"
                if not all(water(cx + dx, cy + dy) for dx, dy in ((1, -1), (1, 1), (-1, 1), (-1, -1))):
                    return tiles, (sx, sy), "the channel is too narrow (land diagonally beside the bridge)"
        ex, ey = tiles[-1]
        side = ((1, 0), (-1, 0)) if sx == 0 else ((0, 1), (0, -1))
        if any((ex + dx, ey + dy) in bridges for dx, dy in side):
            return tiles, (sx, sy), "another bridge alongside"
        if len(tiles) < 2:
            if beach4(ex, ey):
                return tiles, (sx, sy), "beach beside the bridge"
        elif sum(water(ex + dx, ey + dy) for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0))) != 3 or beach4(ex, ey):
            return tiles, (sx, sy), "no shore to land on within 16 tiles"
        return tiles, (sx, sy), None

    def bridge(self, x, y, *rest):
        """bridge X Y: the exe's bridge tool at water tile (X, Y) beside a shore (bridge_site). Cost: tiles x the
        bridge's model cost (build_commit 0x00498910, tool 0x78: g_build_cost x length); refused with
        19:23 "Find a good site along the water". (bridge X1 Y1 X2 Y2, the old form: X1 Y1 is a land end; the
        start is the next tile toward X2 Y2.)"""
        if len(rest) >= 2:
            x2, y2 = rest[:2]
            if x != x2 and y != y2:
                raise CommandError("a bridge must be straight", (23,))
            x, y = x + (x2 > x) - (x2 < x), y + (y2 > y) - (y2 < y)
        tiles, why = self.bridge_site(x, y)
        if tiles is None:
            raise CommandError(f"can't build a bridge at ({x},{y}): {why}", (23,))
        d = BRIDGE_DIR[why]                      # bridge_site's second value: the step
        pieces = self.sd("bridge_pieces", {})
        for i, t in enumerate(tiles):            # FUN_0041D8B0: piece FUN_0041D720(i, len, dir) per tile (drawing)
            pieces[t] = bridge_piece(i, len(tiles), d)
        w = self.world
        cost = len(tiles) * self.cat.spec("bridge")["cost"]
        self.spend(cost, "construction")
        for tx, ty in tiles:
            w.road[ty, tx] = True
        self.sd("bridges", set()).update(tiles)
        if len(tiles) < 4:                       # pieces 13/14: ships can't pass (ship grid 0x00587B90 -> 0xFF)
            self.sd("bridge_short", set()).update(tiles)
        self.map_version = getattr(self, "map_version", 0) + 1
        systems.roads.rebuild(self)
        return f"bridge {len(tiles)} tiles over water from ({tiles[0][0]},{tiles[0][1]}) to ({tiles[-1][0]},{tiles[-1][1]}), cost {cost}"

    def bridge_spans(self):
        """{tile: piece} of every bridge tile. Bridges built before the pieces were stored get theirs from their
        straight runs, the start (i = 0) being the end whose first land neighbour (N, E, S, W) points along it."""
        br = getattr(self, "bridges", None) or set()
        pieces = self.sd("bridge_pieces", {})
        todo = br - set(pieces)
        while todo:
            x, y = min(todo)
            run = None
            for sx, sy in ((1, 0), (0, 1)):
                r = [(x, y)]
                while (r[-1][0] + sx, r[-1][1] + sy) in todo:
                    r.append((r[-1][0] + sx, r[-1][1] + sy))
                if run is None or len(r) > len(run[0]):
                    run = (r, (sx, sy))
            r, (sx, sy) = run
            f = self.world.flags
            land = lambda t: not (0 <= t[0] < f.shape[1] and 0 <= t[1] < f.shape[0]) or not f[t[1], t[0]] & 0x4
            first = next((d for d in ((0, -1), (1, 0), (0, 1), (-1, 0)) if land((r[0][0] + d[0], r[0][1] + d[1]))), None)
            if first != (-sx, -sy):              # the run starts at its other end
                r, sx, sy = r[::-1], -sx, -sy
            for i, t in enumerate(r):
                pieces[t] = bridge_piece(i, len(r), BRIDGE_DIR[(sx, sy)])
            todo -= set(r)
        return pieces

    def remove_bridge(self, x, y):
        """Clearing any tile of a bridge removes the whole span (FUN_0041DA20 walks to one end, then clears
        road bit and piece along it). Returns the tiles removed."""
        pieces = self.bridge_spans()
        ns = pieces[(x, y)] in (7, 8, 9, 10, 11, 12, 14)          # N-S pieces; E-W: 1..6, 13
        span = {(x, y)}
        for k in (1, -1):
            t = (x, y + k) if ns else (x + k, y)
            while t in pieces and (pieces[t] in (7, 8, 9, 10, 11, 12, 14)) == ns:
                span.add(t)
                t = (t[0], t[1] + k) if ns else (t[0] + k, t[1])
        w = self.world
        for tx, ty in span:
            w.road[ty, tx] = False
            pieces.pop((tx, ty), None)
            self.bridges.discard((tx, ty))
            self.sd("bridge_short", set()).discard((tx, ty))
        return len(span)

    def road(self, x1, y1, x2, y2):
        """L-shaped road: along x first, then along y. Skips tiles that already have road."""
        tiles = []
        sx = 1 if x2 >= x1 else -1
        for x in range(x1, x2 + sx, sx):
            tiles.append((x, y1))
        sy = 1 if y2 >= y1 else -1
        for y in range(y1 + sy, y2 + sy, sy) if y2 != y1 else []:
            tiles.append((x2, y))
        w = self.world
        new = [(x, y) for x, y in tiles if not (w.inside(x, y) and w.road[y, x])]
        for x, y in new:
            if not w.free_land(x, y):
                raise CommandError(f"road blocked at ({x},{y}): {w.blocked_kind(x, y) if w.inside(x, y) else 'off map'}"
                                   + (" (occupied)" if w.inside(x, y) and w.occ[y, x] else ""))
        cost = len(new) * self.cat.spec("road")["cost"]
        self.spend(cost, "construction")
        for x, y in new:
            w.road[y, x] = True
        self.map_version = getattr(self, "map_version", 0) + 1
        systems.roads.rebuild(self)
        return f"road {len(new)} tiles, cost {cost}"

    # dragging a road: roads_drag_place 0x0049ACB0 as sim/roaddrag.py ports it, on our state seen as the exe's grids
    def road_grids(self):
        """roaddrag.Grids of our state: terrain with the exe's building bit 8 (our buildings, avenue/boulevard tiles,
        roadblocks) and road bit 0x40 (World.road; stale map bits dropped), our 1x1 gardens as the exe's painted
        garden terrain 0x20 (no building), building types (zeus ids; avenue 0x76, boulevard 0x7E, roadblock 0x7B),
        the play edge, and the cracked rock tiles (rock with piece 0x80: the map's and the earthquakes')."""
        from . import roaddrag
        w = self.world
        T = (w.flags.astype(np.uint32) & np.uint32(~0x68 & 0xFFFFFFFF)) | np.where(w.road, 0x40, 0).astype(np.uint32)
        occ = w.occ
        bt = np.zeros(occ.shape, np.int32)
        if occ.any():
            lut = np.zeros(int(occ.max()) + 1, np.int32)
            for b in self.buildings.values():
                if b.id < len(lut):
                    lut[b.id] = -1 if b.key == "gardens" else self.cat.spec(b.key).get("zeus_id", 1) or 1
            bt = lut[occ]
        T |= np.where(bt == -1, 0x20, np.where(bt > 0, 8, 0)).astype(np.uint32)
        T |= (w.flags.astype(np.uint32) & np.uint32(0x20))
        bt = np.where(bt < 0, 0, bt)
        av = getattr(w, "avenue", None)
        if av is not None and av.any():
            kind = av.astype(np.int32) >> 8
            bt = np.where(av != 0, np.where(kind == 2, 0x7E, 0x76), bt)
            T |= np.where(av != 0, 8, 0).astype(np.uint32)
        for x, y in getattr(self, "roadblocks", None) or ():
            T[y, x] |= 8
            bt[y, x] = 0x7B
        size = tuple(getattr(w, "size", (226, 226)))
        edge = _ROAD_GRIDS.get(size)
        if edge is None:
            edge = _ROAD_GRIDS[size] = roaddrag.near_edge(size)
        cracked, crack = self._road_cracks(T)
        return roaddrag.Grids(T, bt, edge, cracked, crack)

    def _road_cracks(self, T):
        """Cracked rock tiles (flat indices) and FUN_0058CAD0 for them: the tile's crack picture (T_CRACKS 0x00636BE0
        over its cracked neighbours, column view/2, + the map's random byte % variants; tools/terrain_images.py) must
        be a straight piece or an end: 0..3 / 16..19 need no road N and S of it, 4..7 / 20..23 none W and E (swapped
        in views 2 and 6)."""
        from . import disasters
        from .world import read_map, N as NN
        w = self.world
        m = _ROAD_GRIDS.get(self.map_name)
        if m is None:                               # the map's piece (0x80) and random grids, read once per map
            hdr, blocks = read_map(self.map_name)
            d = {b["rank"]: b["data"] for b in blocks}
            m = _ROAD_GRIDS[self.map_name] = (np.frombuffer(d[7], np.uint8)[:NN * NN].reshape(NN, NN) & 0x80,
                                              np.frombuffer(d[8], np.uint8)[:NN * NN].reshape(NN, NN).copy())
        pc, rand = m
        tiles = set(map(tuple, np.argwhere(pc != 0)[:, ::-1].tolist())) | set(disasters.cracked_tiles(self))
        tiles = {(x, y) for x, y in tiles if int(T[y, x]) & 2}
        if not tiles:
            return (), None
        import terrain_images as ti
        view = getattr(self, "view", 0)
        cr = {y * NN + x for x, y in tiles}

        def crack(i, TT):
            x, y = i % NN, i // NN
            arr = [(y + dy) * NN + x + dx in cr and bool(int(TT[(y + dy) * NN + x + dx]) & 2) for dx, dy in ti.N8]
            rec = next((r for r in ti.T_CRACKS if all(p == 2 or (p == 1) == a for p, a in zip(r[0], arr))), None)
            if rec is None:
                return False
            v = rec[1][view >> 1] + (int(rand[y, x]) % rec[3] if rec[3] else 0)
            if v in (0, 1, 2, 3, 16, 17, 18, 19):
                ew = False
            elif v in (4, 5, 6, 7, 20, 21, 22, 23):
                ew = True
            else:
                return False
            if view in (2, 6):
                ew = not ew
            if ew:
                return not int(TT[i + 1]) & 0x40 and not int(TT[i - 1]) & 0x40
            return not int(TT[i - NN]) & 0x40 and not int(TT[i + NN]) & 0x40
        return cr, crack

    def road_drag(self, x1, y1, x2, y2):
        """roads_drag_place 0x0049ACB0 on our state, without changing it: roaddrag.drag's dict (ok, refused, tiles
        set in trace order from the end, new, ramps). A failed trace keeps the tiles it set (the exe's too)."""
        from . import roaddrag
        n = self.world.flags.shape[0]
        if not all(0 <= v < n for v in (x1, y1, x2, y2)):
            return dict(ok=False, refused=True, tiles=[], new=0, ramps=[])
        G = self.road_grids()
        if not roaddrag.ends_ok(G, x1, y1, x2, y2)[0]:
            return roaddrag.drag(G, x1, y1, x2, y2)
        mask = G.passable()
        if _ROUTE_CACHE.get("mask") != mask:
            _ROUTE_CACHE.clear()
            _ROUTE_CACHE.update(mask=mask, flood={})
        a = y1 * n + x1
        flood = _ROUTE_CACHE["flood"]
        dist = flood.get(a)
        if dist is None:
            dist = roaddrag.flood(mask, a) if mask[a] else [0] * len(mask)
            if len(flood) > 8:
                flood.clear()
            flood[a] = dist
        return roaddrag.drag(G, x1, y1, x2, y2, dist=dist)

    def herd_point_in(self, x1, y1, x2, y2):
        """map_area_has_marker 0x00496B50: a wolf, boar or deer point (scenario tables 0x00902BB4 / D10 / C54, logical
        x and y compared as stored, so a (0, 0) slot counts) in the rectangle of the two corners."""
        w = self.world
        o = getattr(w, "origin", (1, 1))
        lx, ly = sorted((x1 - o[0], x2 - o[0])), sorted((y1 - o[1], y2 - o[1]))
        pts = getattr(w, "points", {})
        for k in ("wolf", "boar", "deer"):
            for p in pts.get(k, ()):
                if p is not None and lx[0] <= p[0] - o[0] <= lx[1] and ly[0] <= p[1] - o[1] <= ly[1]:
                    return True
        return False

    # the commands that are build_commit 0x00498910 tools: buildings, roads (0x1C), walls (0x82), avenues /
    # boulevards (0x80), bridges (0x78 / 0xC9), clear land (0x1D); the road drag `path` checks on its own
    TOOL_OPS = ("build", "road", "wall", "bridge", "avenue", "boulevard", "clear")

    def tool_refusal(self, op, x1, y1, x2=None, y2=None):
        """build_commit 0x00498910's first refusals, in its order: the treasury below -1999 (message 0x13; every
        tool), then (every tool but clear land) an enemy near either corner of the action's rectangle (enemies_near_rect
        0x004DCF60, message 0x21: nothing is built; a drag's preview is undone). A building's rectangle is its
        tile. Raises CommandError; returns None when neither applies."""
        if x2 is None or y2 is None or op == "build":
            x2, y2 = x1, y1
        if self.city.treasury < -1999:
            raise CommandError(f"not enough money ({self.city.treasury} dr)", (19,))
        if op != "clear" and self.enemies_near_rect(x1, y1, x2, y2):    # clear land (0x1D) skips this test
            raise CommandError(f"{op}: enemies are too close to build", (0x21,))
        return None

    def enemies_near_rect(self, x1, y1, x2, y2):
        """enemies_near_rect 0x004DCF60: an enemy soldier, transport or warship within 12 tiles in both axes of either
        corner (figure types 0x28..0x2A, 0x3F, 0x40)."""
        for f in self.walkers.values():
            if f.role in ("enemy_infantry", "enemy_archer", "enemy_cavalry", "enemy_transport", "enemy_warship"):
                if (abs(f.x - x1) < 13 and abs(f.y - y1) < 13) or (abs(f.x - x2) < 13 and abs(f.y - y2) < 13):
                    return True
        return False

    def road_path(self, x1, y1, x2, y2, clear_trees=False):
        """Road along the cheapest route over free land (existing roads reused), like dragging a
        road in the game. With clear_trees, trees on the way are cut (2 dr each; a tree tile
        counts as 5 road tiles when choosing the route)."""
        import heapq
        w = self.world
        start, goal = (x1, y1), (x2, y2)
        if not clear_trees:                    # the game's drag: build_commit 0x00498910 tool 28
            # build_commit's refusals. Enemies: the terrain is restored from the drag's backup. Debt and herd points:
            # it is not, so the preview's road (roads_drag_place(1) of the last mouse position, a failed trace's part
            # too) stays, uncharged (oracle 1R-roads d137/d138: 8 tiles kept, 0 dr)
            if self.enemies_near_rect(x1, y1, x2, y2):
                raise CommandError("path: enemies are too close to build", (0x21,))
            refuse = ((f"not enough money ({self.city.treasury} dr)", (19,)) if self.city.treasury < -1999 else
                      ("path: an animal herd's spawn point is in the way", (0x16,)) if self.herd_point_in(x1, y1, x2, y2)
                      else None)
            r = self.road_drag(x1, y1, x2, y2)
            if refuse:
                if r["tiles"]:
                    for x, y in r["tiles"]:
                        w.road[y, x] = True
                    self.map_version = getattr(self, "map_version", 0) + 1
                    systems.roads.rebuild(self)
                raise CommandError(*refuse)
            if not r["tiles"]:
                raise CommandError(f"path: no route from {start} to {goal} (try: path ... clear)")
            for x, y in r["tiles"]:                # a failed trace keeps (and charges) the tiles it set
                w.road[y, x] = True
            price = r["new"] * self.cat.spec("road")["cost"]
            self.spend(price, "construction")
            self.map_version = getattr(self, "map_version", 0) + 1
            systems.avenues.refresh(self)          # build_commit: 0x00418BD0 + 0x004193A0 twice (the 2nd in rebuild)
            systems.roads.rebuild(self)
            return (f"road {r['new']} tiles, cost {price}" if r["ok"] else
                    f"road {r['new']} tiles, cost {price} (no route to the start: the exe keeps the part it laid)")

        def cost(x, y):
            if not w.inside(x, y):
                return None
            if w.road[y, x]:
                return 1
            if w.free_land(x, y):
                return 1
            if clear_trees and w.occ[y, x] == 0 and int(w.flags[y, x]) & 0x1 and not int(w.flags[y, x]) & 0x206:
                return 5
            return None
        if cost(*start) is None or cost(*goal) is None:
            raise CommandError("path: start and end must be free land or road")
        dist, prev = {start: 0}, {start: None}
        heap = [(0, start)]
        while heap:
            d, t = heapq.heappop(heap)
            if t == goal:
                break
            if d > dist[t]:
                continue
            x, y = t
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                c = cost(*nb)
                if c is not None and d + c < dist.get(nb, 1 << 30):
                    dist[nb], prev[nb] = d + c, t
                    heapq.heappush(heap, (d + c, nb))
        if goal not in prev:
            raise CommandError(f"path: no route from {start} to {goal}" + ("" if clear_trees else " (try: path ... clear)"))
        tiles, t = [], goal
        while t:
            tiles.append(t)
            t = prev[t]
        new = [(x, y) for x, y in tiles if not w.road[y, x]]
        trees = [(x, y) for x, y in new if int(w.flags[y, x]) & 0x1]
        price = len(new) * self.cat.spec("road")["cost"] + 2 * len(trees)
        self.spend(price, "construction")
        for x, y in trees:
            w.flags[y, x] &= np.uint32(0xFFFFFFFE)
        for x, y in new:
            w.road[y, x] = True
        self.map_version = getattr(self, "map_version", 0) + 1
        systems.roads.rebuild(self)
        return f"road path {len(tiles)} tiles ({len(new)} new, {len(trees)} trees cut), cost {price}"

    def clear(self, x1, y1, x2=None, y2=None):
        x2 = x1 if x2 is None else x2
        y2 = y1 if y2 is None else y2
        w = self.world
        removed, trees, rubble, roads, segs = set(), 0, 0, 0, 0
        for y in range(min(y1, y2), max(y1, y2) + 1):
            for x in range(min(x1, x2), max(x1, x2) + 1):
                if not w.inside(x, y): continue
                if w.avenue[y, x]: systems.avenues.remove_segment(self, x, y); segs += 1   # the road stays
                elif w.occ[y, x]: removed.add(int(w.occ[y, x]))
                elif (x, y) in getattr(self, "roadblocks", ()): self.roadblocks.discard((x, y)); roads += 1
                elif (x, y) in (getattr(self, "bridges", None) or ()): roads += self.remove_bridge(x, y)
                elif w.road[y, x]: w.road[y, x] = False; roads += 1
                elif w.flags[y, x] & 0x4000: w.flags[y, x] &= np.uint32(~0x4000 & 0xFFFFFFFF); roads += 1
                elif w.flags[y, x] & 0x1001:      # trees and rubble (clear_land_commit 0x0049A460: & 0x93B72F92;
                    if w.flags[y, x] & 0x1: trees += 1          # each counts in g_build_count, i.e. the cost)
                    else: rubble += 1
                    w.flags[y, x] &= np.uint32(~0x1001 & 0xFFFFFFFF)
        # a vendor cleared alone leaves its empty stall in the agora (vendor_demolish 0x0040AF80: stall -> type 66);
        # the text says so (playtest haiku-2 #4: twice cleared by mistake)
        stalls = [self.buildings[bid] for bid in removed if self.buildings[bid].kind == "stall"
                  and self.buildings[bid].misc.get("agora") not in removed]
        closed = [b.key for b in stalls if b.key != "empty_stall"]
        whole = [self.footprint_text(self.buildings[bid]) for bid in sorted(removed)
                 if self.buildings[bid].kind != "stall" or self.buildings[bid].misc.get("agora") in removed]
        for bid in removed:
            self.demolish(bid)
        self.map_version = getattr(self, "map_version", 0) + 1
        cost = 2 * (trees + rubble + roads + segs)
        if cost: self.spend(cost, "construction")
        systems.roads.rebuild(self)
        # ours (playtest haiku-3 #7): the whole building goes whatever tile of it is cleared (clear_land_commit
        # 0x0049A460 takes each building in the rectangle by its root), so name each one and its footprint
        return (f"cleared {len(removed) - len(stalls)} buildings" + (f" ({'; '.join(whole)})" if whole else "") + ", "
                + (f"{segs} avenue segments, " if segs else "")
                + f"{roads} road tiles, {trees} trees" + (f", {rubble} rubble tiles" if rubble else "") + f" (cost {cost})"
                + (f"; closed {', '.join(closed)}: the stall stays in its agora, empty (`build VENDOR X Y` reopens it;"
                   " clear the agora to remove it)" if closed else ""))

    def occupied_text(self, why):
        """World.area_ok's '(x,y) is occupied' with what is there (ours, playtest haiku-3 #7)."""
        import re
        m = re.fullmatch(r"\((\d+),(\d+)\) is occupied", why)
        if not m:
            return why
        x, y = int(m.group(1)), int(m.group(2))
        w = self.world
        bid = int(w.occ[y, x])
        if bid and bid in self.buildings:
            return f"({x},{y}) is taken by {self.footprint_text(self.buildings[bid])}"
        if w.avenue[y, x]:
            return f"({x},{y}) is an avenue"
        if w.road[y, x]:
            return f"({x},{y}) is a road"
        return why

    def footprint_text(self, b):
        """'Granary #187 (161,150)-(164,153)': a building and the tiles it covers (CLI texts)."""
        w, h = b.misc.get("w", b.size), b.misc.get("h") or b.misc.get("w", b.size)
        name = self.cat.spec(b.key)["name"]
        if b.kind in ("road", "agora") or not w:
            return f"{name} #{b.id} at ({b.x},{b.y})"
        return f"{name} #{b.id} ({b.x},{b.y})" + (f"-({b.x + w - 1},{b.y + h - 1})" if w > 1 or h > 1 else "")

    def demolish(self, bid, reason=None):
        b = self.buildings.get(bid)
        if b and b.kind == "stall" and b.misc.get("agora") in self.buildings:
            if b.key != "empty_stall":           # a vendor goes, its stall stays with the agora
                for wid in list(b.walkers):
                    self.walkers.pop(wid, None)
                b.walkers = []
                name = self.cat.spec(b.key)["name"]
                systems.agora.empty_stall(self, b)
                self.map_version = getattr(self, "map_version", 0) + 1
                if reason:
                    self.message(f"{name} at ({b.x},{b.y}) {reason}")
            return
        b = self.buildings.pop(bid, None)
        if not b: return
        if b.kind == "monument":                 # a sanctuary's extras: ores, trees, Demeter's meadow (FUN_00546A60)
            systems.monuments.extras_removed(self, b)
        self.world.occ[self.world.occ == bid] = 0
        self.map_version = getattr(self, "map_version", 0) + 1
        for wid in list(b.walkers):
            self.walkers.pop(wid, None)
        if b.kind == "house" and b.occupants:
            self.city.population -= b.occupants
            if reason is None:                   # cleared by the player: they walk out (clear_land_commit)
                systems.walkers.spawn_homeless(self, b, b.occupants)
        if reason and b.kind != "ruin":
            self.message(f"{self.cat.spec(b.key)['name']} at ({b.x},{b.y}) {reason}")

    # --- undo (exe: undo_begin 0x004A6CC0 at each build-tool click, undo_record_building 0x004A6E90, undo_arm
    # 0x004A6FD0, undo_expire 0x004A7A50, undo 0x004A7000 from the panel button 0x00405B80; docs/play/undo.md) ---
    UNDO_OPS = ("build", "road", "wall", "bridge", "avenue", "boulevard", "clear", "path")
    UNDO_GRIDS = ("flags", "road", "occ", "avenue")
    UNDO_TICKS = 500                    # undo_arm: g_undo_ticks_left = 500

    def action_begin(self):
        """Start one player action (a click or a drag): the previous action can no longer be undone."""
        w = self.world
        self.undo = None
        self._undo_pre = dict(grids={k: getattr(w, k).copy() for k in self.UNDO_GRIDS}, buildings=dict(self.buildings),
                              walkers=set(self.walkers), treasury=self.city.treasury,
                              roadblocks=set(getattr(self, "roadblocks", None) or ()), bridges=self._bridge_state())

    def action_end(self):
        """Record what the action changed (tiles, buildings, cost) as the undo of the last action."""
        pre = self.__dict__.pop("_undo_pre", None)
        if pre is None:
            return
        w = self.world
        tiles = {}
        for k, before in pre["grids"].items():
            now = getattr(w, k)
            idx = np.flatnonzero(before != now)
            if len(idx):
                tiles[k] = (idx, before.flat[idx].copy(), now.flat[idx].copy())
        created = [bid for bid in self.buildings if bid not in pre["buildings"]]
        removed = {bid: b for bid, b in pre["buildings"].items() if bid not in self.buildings}
        animals = [wid for wid in self.walkers if wid not in pre["walkers"] and self.walkers[wid].role in ("sheep", "goat", "cattle")]
        rb = set(getattr(self, "roadblocks", None) or ())
        cost = pre["treasury"] - self.city.treasury
        br = self._bridge_state()
        if not (tiles or created or removed or animals or rb != pre["roadblocks"] or br != pre["bridges"]):
            return
        self.undo = dict(tick=self.tick, year=self.year, tiles=tiles, cost=cost, animals=animals,
                         created={bid: (self.buildings[bid].key, self.buildings[bid].x, self.buildings[bid].y) for bid in created},
                         removed=removed, roadblocks=(pre["roadblocks"], rb), bridges=pre["bridges"],
                         ruins=sum(1 for b in self.buildings.values() if b.kind == "ruin" or b.burning))

    def roadblock_ok(self, x, y):
        """The roadblock tool 0x7B (build check 0x00452xxx): the tile is road (0x40), not occupied (0x8: an agora's
        road strip is part of the agora), no bridge piece (0x00CB4B08) and no ramp (0x400) (bugs.md 381)."""
        from .world import RAMP
        from .systems import agora
        w = self.world
        if not (w.inside(x, y) and w.road[y, x]) or w.occ[y, x] or w.flags[y, x] & RAMP:
            return False
        if (x, y) in (getattr(self, "bridges", None) or ()) or (x, y) in (getattr(self, "bridge_pieces", None) or {}):
            return False
        return not agora.strip_near(self, x, y, 0)

    def _bridge_state(self):
        return (set(getattr(self, "bridges", None) or ()), set(getattr(self, "bridge_short", None) or ()),
                dict(getattr(self, "bridge_pieces", None) or {}))

    def undo_state(self):
        """'' when the last action can be undone, else why not (undo_expire 0x004A7A50 rules)."""
        u = getattr(self, "undo", None)
        if not u:
            return "nothing to undo"
        if self.tick - u["tick"] >= self.UNDO_TICKS:
            return f"too late: undo lasts {self.UNDO_TICKS} ticks after the action"
        if self.year != u["year"]:                      # month_advance 0x00483C10 clears it at the new year
            return "a new year began"
        if sum(1 for b in self.buildings.values() if b.kind == "ruin" or b.burning) != u["ruins"]:
            return "a fire or collapse happened"         # building_ignite / collapse clear 0x00DA2374
        for bid, (key, x, y) in u["created"].items():
            b = self.buildings.get(bid)
            if b is None or (b.key, b.x, b.y) != (key, x, y):
                return "a building of the action is gone or changed"
            if b.kind == "house" and b.occupants:        # houses: undo ends once someone moves in
                return "people moved into the new houses"
        return ""

    def undo_last(self):
        why = self.undo_state()
        if why:
            raise CommandError(f"can't undo: {why}")
        u, w = self.undo, self.world
        self.undo = None
        for bid in u["created"]:
            b = self.buildings.pop(bid)
            for wid in list(b.walkers):
                self.walkers.pop(wid, None)
        for wid in u["animals"]:
            self.walkers.pop(wid, None)
        for k, (idx, before, now) in u["tiles"].items():
            getattr(w, k).flat[idx] = before
        for bid, b in u["removed"].items():             # cleared buildings come back empty (snapshot after
            if b.kind == "house" and b.occupants:       # spawn_homeless, clear_land_commit 0x0049A460)
                b.occupants = 0
            b.walkers = [w_ for w_ in b.walkers if w_ in self.walkers]    # its walkers were dismissed
            self.buildings[bid] = b
        if u["roadblocks"][0] != u["roadblocks"][1]:
            self.roadblocks = set(u["roadblocks"][0])
        if "bridges" in u:                               # bridge tiles, pieces, short spans as before the action
            self.bridges, self.bridge_short, self.bridge_pieces = (type(v)(v) for v in u["bridges"])
        self.city.treasury += u["cost"]                  # 0x004A7000: treasury += g_build_cost, construction -= it
        self.city.ledger["construction"] = self.city.ledger.get("construction", 0) + u["cost"]
        self.map_version = getattr(self, "map_version", 0) + 1
        systems.roads.rebuild(self)
        for bid in u["removed"]:
            systems.roads.update_access(self, self.buildings[bid])
        return (f"undone: {self._undo_names(u['created'].values())} removed, "
                f"{self._undo_names((b.key, b.x, b.y) for b in u['removed'].values())} restored, "
                f"{sum(len(t[0]) for t in u['tiles'].values())} tile changes reverted, {u['cost']} dr refunded")

    @staticmethod
    def _undo_names(items):
        """'agora, 3 x stall (4 buildings)' / 'nothing' for the undo text (playtest haiku-1 #10: an agora's
        stalls are buildings of their own, so the bare count read as one too many; bugs.md 280)."""
        n = {}
        for key, _x, _y in items:
            n[key] = n.get(key, 0) + 1
        if not n:
            return "no buildings"
        total = sum(n.values())
        names = ", ".join(k if c == 1 else f"{c} x {k}" for k, c in n.items())
        return names if total == 1 else f"{names} ({total} buildings)"

    # --- commands --------------------------------------------------------------------------
    def site_error(self, key, x, y):
        """The terrain need of a building at (x, y) (meadow, coast), or "" when met.
        Shared by the build command and the play-mode preview (sim/live.py footprint)."""
        spec = self.cat.spec(key)
        size = spec.get("size") or 1
        need = spec.get("needs")
        w = self.world
        if need == "meadow":
            tiles = [(xx, yy) for yy in range(y, y + size) for xx in range(x, x + size)]
            if not any(w.inside(xx, yy) and w.flags[yy, xx] & (0x800 | 0x10000) for xx, yy in tiles):   # buildings.md §7
                return f"{key} needs at least one meadow tile (',' in look)"
        # timber mill, quarry, foundry, mint...: no resource test at placement (build_commit 0x00498910,
        # buildings.md §5); their workers walk to the nearest resource tile on the map (production.md)
        elif key in shore.KEYS:                    # half over water, first fitting orientation (systems/shore.py)
            why = shore.site_error(self, key, x, y)
            return why[0] if why else ""
        elif need == "coast" and systems.walkers.water_exit(self, x, y, size, connected=True) is None:
            return f"{key} must be next to open water (8+ connected water tiles)"
        return ""

    def set_difficulty(self, d):
        """g_difficulty 0x00F2A988 changed in play (Options > Difficulty, handler 0x00401EE0: each click at once).
        The exe reloads the per-level model files and nothing else; every reader looks the level up when it runs
        (docs/logic/difficulty.md "Difficulty during play"), so swapping the catalog is the whole change: built-up
        risk, curse lengths, ship hp and requests already made keep their values. The treasury is re-scaled only on
        a city still at tick 0 with nothing built (ours: the exe's open-play level is chosen before the city exists;
        an episode's new city as episode.set_difficulty; a colony's carried treasury never)."""
        pristine = not self.tick and not self.buildings and \
            not (self.world.road != (self.world.flags & 0x40 > 0)).any()          # only the map's own roads
        self.difficulty, self.cat = d, Catalog(difficulty=d)
        self.rules = self.cat.rules
        if not pristine:
            return
        st = getattr(self, "episode", None) or {}
        if not st:
            self.city.treasury = self.rules["start_funds"] * self.rules.get("start_funds_pct", 100) // 100
        elif st.get("start") == "new_city" and getattr(self, "start_funds", None) is not None:
            self.city.treasury = self.start_funds * self.rules.get("start_funds_pct", 100) // 100

    def command(self, text):
        """Execute one text command; returns a result string. Raises CommandError."""
        p = text.split()
        if not p: return ""
        op, a = p[0].lower(), p[1:]
        own = op in self.UNDO_OPS and not hasattr(self, "_undo_pre")     # not inside a batch (action_begin)
        if own:
            self.action_begin()
        try:
            test = testcmds.name_of(self, op, a)      # test-only commands (sim/testcmds.py): warned, counted, switchable
            if test and (why := testcmds.refuse(self, test)):
                raise CommandError(why)
            ints = [int(v) for v in a if v.lstrip("-").isdigit()]
            if op == "testcmds": out = testcmds.switch(self, a)
            elif op == "goals":          # the goal checker's measurements (sim/measure.py; read only)
                from . import measure
                out = measure.text(self)
            elif op == "allowed":        # an episode's unavailable buildings (sim/allowed.py; read only)
                off = allowed.unavailable(self)
                out = ("every building (no allowed table: open play)" if off is None else
                       "not available: " + (", ".join(off) or "none"))
            elif op in self.TOOL_OPS and len(ints) >= 2 and self.tool_refusal(op, *ints[:4]): pass
            elif op == "build": out = self.build(a[0], ints[0], ints[1], (" ".join(a[3:]) if a[0] in shore.KEYS
                                                                        or a[0] == systems.commemorative.KEY
                                                                        or a[0] in ("trading_post", "heroes_hall") else a[3])
                                               if len(a) > 3 else None)
            elif op == "undo": out = self.undo_last()
            elif op == "staff":          # staff X Y on|off: military buildings (towers, wharves) only
                b = self.buildings.get(int(self.world.occ[ints[1], ints[0]]))
                if b is None or self.cat.spec(b.key)["labor_category"] < len(systems.labor.CATEGORIES):
                    raise CommandError(f"no tower or trireme wharf at ({ints[0]},{ints[1]})")
                if b.key == "trireme_wharf":     # the wharf window's button (0x00572490) acts only without a trireme
                    from .military import navy
                    t = navy.wharf_trireme(self, b)
                    if t is not None:
                        raise CommandError(f"this wharf has a trireme: `trireme {t.id} crew` sends its crew home")
                b.misc["off"] = a[2] == "off"
                out = f"{b.key} at ({b.x},{b.y}): workers {'sent home' if b.misc['off'] else 'called back'}"
            elif op == "shore":          # shore KEY [N]: anchors where a shore building fits now (systems/shore.py)
                if not a or a[0] not in shore.KEYS:
                    raise CommandError(f"usage: shore {'|'.join(shore.KEYS)} [N]")
                found = shore.sites(self, a[0], int(a[1]) if len(a) > 1 and a[1].isdigit() else 40)
                out = (f"{a[0]}: {len(found)} sites (X Y facing): " + ", ".join(f"{x} {y} {o}" for x, y, o in found)
                       if found else f"{a[0]}: no site on this map fits now")
            elif op == "view":           # view 0|2|4|6: play mode's map orientation (docs/play/rotation.md
                if not ints or ints[0] not in (0, 2, 4, 6):  # "The view in the sim"); only the wall-walk grid uses it
                    if not a:
                        out = f"view {getattr(self, 'view', 0)}"
                    else:
                        raise CommandError("usage: view 0|2|4|6")
                else:
                    self.view = ints[0]
                    military.view_changed(self)
                    out = f"view {self.view}"
            elif op == "towers":         # towers on|off: the Military tab's "man all towers" switch
                if a[:1] not in (["on"], ["off"]):
                    raise CommandError("usage: towers on|off")
                self.towers_off = a[0] == "off"
                out = f"towers {'sent home' if self.towers_off else 'manned'}"
            elif op == "storage":        # storage X Y GOOD accept|refuse|get|empty [LIMIT]
                b = self.buildings.get(int(self.world.occ[ints[1], ints[0]]))
                if b is None or b.kind != "storage" or self.cat.spec(b.key).get("endless"):
                    raise CommandError(f"no granary or storehouse at ({ints[0]},{ints[1]})")
                good, mode = a[2], a[3]
                if good not in self.cat.resources or mode not in ("accept", "refuse", "get", "empty"):
                    raise CommandError("usage: storage X Y GOOD accept|refuse|get|empty [LIMIT]")
                b.misc.setdefault("orders", {})[good] = mode
                if len(ints) > 2:
                    b.misc.setdefault("limits", {})[good] = ints[2]
                out = f"{b.key} at ({b.x},{b.y}): {good} {mode}" + (f" up to {ints[2]}" if len(ints) > 2 else "")
            elif op == "halt":           # halt X Y: a monument's Halt / Resume Construction button (0x00408E40)
                b = next((m for m in self.buildings.values() if m.kind == "monument" and "pieces" in m.misc and len(ints) >= 2
                          and m.x <= ints[0] < m.x + m.misc.get("w", m.size) and m.y <= ints[1] < m.y + m.misc.get("h", m.size)),
                         None)
                if b is None or b.misc.get("complete"):
                    raise CommandError("usage: halt X Y (a monument under construction)")
                b.misc["halted"] = not b.misc.get("halted")
                if not b.misc["halted"]:
                    del b.misc["halted"]
                out = f"{b.key} at ({b.x},{b.y}): construction {'halted' if b.misc.get('halted') else 'resumed'}"
            elif op == "stockpile":      # stockpile GOOD on|off (city-wide, 0x00FE94E0)
                if a[0] not in self.cat.resources:
                    raise CommandError(f"unknown good '{a[0]}'")
                st = self.sd("stockpile", set())
                (st.add if a[1] == "on" else st.discard)(a[0])
                out = f"{a[0]} {'stockpiled: not distributed, not exported' if a[1] == 'on' else 'released'}"
            elif op == "trade":          # trade | trade X Y GOOD export|import|off [LIMIT]
                if not a:
                    out = systems.trade.describe(self)
                else:
                    bid = int(self.world.occ[ints[1], ints[0]])
                    b = self.buildings.get(bid)
                    if b is None or b.kind != "trade":
                        raise CommandError(f"no trading post or dock at ({ints[0]},{ints[1]})")
                    out = systems.trade.set_order(self, b, a[2], a[3], ints[2] if len(ints) > 2 else None)
            elif op == "road": out = self.road(*ints[:4])
            elif op in ("wall", "bridge", "avenue", "boulevard") and (why := allowed.check(self, op)):
                raise CommandError(why)                              # the episode's allowed buildings (sim/allowed.py)
            elif op == "wall": out = self.wall(*ints[:4])
            elif op == "bridge": out = self.bridge(*ints[:4])          # bridge X Y (exe tool) | X1 Y1 X2 Y2
            elif op in ("avenue", "boulevard"): out = systems.avenues.build(self, op, *ints[:4])
            elif op == "clear": out = self.clear(*ints[:4])
            elif op == "path": out = self.road_path(*ints[:4], clear_trees="clear" in a)
            elif op == "hover":          # hover KEY X Y | hover off: a build tool held over the map (play mode's ghost):
                if not a or a[0] in ("off", "none"):      # sheep / goats / cattle walk off its footprint
                    self.hover = None; out = "hover off"
                else:
                    if a[0] not in self.cat.buildings and a[0] not in ("road", "wall", "clear"):
                        raise CommandError(f"unknown building '{a[0]}' (see catalog)")
                    if len(ints) < 2:
                        raise CommandError("usage: hover KEY X Y | hover off")
                    self.hover = systems.walkers.hover_rect(self, a[0], ints[0], ints[1])
                    out = f"hover {a[0]} ({ints[0]},{ints[1]})-({self.hover[2] - 1},{self.hover[3] - 1})"
            elif op == "poseidon":       # poseidon on|off: allow the expansion's buildings (data: "poseidon")
                if a: self.poseidon = a[0] in ("on", "1", "yes")
                out = f"poseidon {'on' if getattr(self, 'poseidon', False) else 'off'}"
            elif op == "difficulty":     # difficulty [NAME]: at any time, as each Options arrow click (0x00401EE0)
                if a:
                    from .data import DIFFICULTIES
                    d = next((x for x in DIFFICULTIES if x.lower() == a[0].lower()), None)
                    if d is None:
                        raise CommandError(f"difficulty is one of {', '.join(DIFFICULTIES)}")
                    self.set_difficulty(d)
                out = f"difficulty {getattr(self, 'difficulty', 'Normal')}"
            elif op == "grant_monument":   # grant_monument V: sandbox cheat / event hook, a commemorative monument
                if not ints or not 1 <= ints[0] < systems.commemorative.VARIANTS:
                    raise CommandError("usage: grant_monument V (1..65; 1 population, 6 happiness, ...)")
                systems.commemorative.grant(self, ints[0])
                out = f"granted: {systems.commemorative.name(ints[0])} (available {systems.commemorative.state(self)['available'][ints[0]]})"
            elif op == "funds":          # funds N: sandbox cheat, adds N dr to the treasury
                self.city.treasury += ints[0]; out = f"treasury {self.city.treasury} dr"
            elif op == "tax":          # the exe's slider: 7 fixed levels (0x00641F50), the nearest one
                self.city.tax_rate = snap_level(tax_levels(self), ints[0]); out = f"tax rate {self.city.tax_rate}%"
            elif op == "wage":         # 6 fixed levels (0x00641F38)
                self.city.wage_rate = snap_level(WAGE_LEVELS, ints[0]); out = f"wage rate {self.city.wage_rate}"
            elif op == "priority":
                cat = systems.labor.category(a[0]); n = max(0, min(5, ints[-1]))
                systems.labor.priorities(self)[cat] = n
                systems.labor.allocate(self)     # the advisor's arrows re-run the allocation at once (0x00590580)
                out = f"labor priority {systems.labor.CATEGORIES[cat]} = {n}"
            elif op == "industry":       # industry GOOD on|off: the labor advisor's shut-down (g_industry_halted)
                if len(a) != 2 or a[1] not in ("on", "off") or (a[0] not in self.cat.resources and a[0] != "meat_beef"):
                    raise CommandError("usage: industry GOOD on|off")
                off = self.sd("industry_off", set())
                (off.add if a[1] == "off" else off.discard)(a[0])
                systems.labor.allocate(self)     # FUN_00590660 only flips the flag; ours shows it at once
                out = f"{a[0]} industry {'shut down' if a[1] == 'off' else 'reactivated'}"
            elif op == "until":          # until STAT N [MAX_MONTHS]: let days pass until city.STAT >= N
                stat, n = a[0], ints[0]
                limit = (ints[1] if len(ints) > 1 else 24) * self.rules["days_per_month"]
                if not hasattr(self.city, stat) or not isinstance(getattr(self.city, stat), int):
                    raise CommandError(f"unknown stat '{stat}' (population, unemployed, workforce, treasury, ...)")
                d = 0
                while getattr(self.city, stat) < n and d < limit:
                    self.step(self.rules["ticks_per_day"]); d += 1
                out = f"now {self.date()}: {stat} {getattr(self.city, stat)}" + ("" if getattr(self.city, stat) >= n else " (gave up)")
            elif op in ("step", "wait"): self.step(ints[0] if ints else 1); out = f"now tick {self.tick} ({self.date()})"
            elif op == "days": self.step((ints[0] if ints else 1) * self.rules["ticks_per_day"]); out = f"now {self.date()}"
            elif op == "months": self.step((ints[0] if ints else 1) * self.rules["ticks_per_day"] * self.rules["days_per_month"]); out = f"now {self.date()}"
            elif op in scenario.VERBS: out = scenario.command(self, op, a)    # scheduled events (sim/scenario)
            elif (out := empire.command(self, op, a)) is None and \
                    (out := military.command(self, op, a)) is None and \
                    (out := heroes.command(self, op, a)) is None and \
                    (out := gods.command(self, op, a)) is None and \
                    (out := alerts.command(self, op, a)) is None:          # world map (sim/empire), armies (sim/military), heroes/monsters (sim/heroes), gods (sim/gods)
                raise CommandError(f"unknown command '{op}'")
        except ValueError as e:
            raise CommandError(str(e))
        except (IndexError, TypeError):
            raise CommandError(f"bad arguments for '{op}'")
        finally:
            if own:
                self.action_end()
        if test:
            out = testcmds.count(self, test, out)
        if op not in ("step", "wait", "days", "months", "until"):
            self.log.append((self.tick, text))
        return out

    # --- persistence ------------------------------------------------------------------------
    CACHES = ("_undo_pre", "_kinds", "_win", "_trees", "_rtrees", "_roadl", "_flagl", "_desl", "_walk", "_wild", "_fields", "_burning", "_des_sig", "_entry_reach", "_shipgrid", "_godfx", "_hero_water_ok", "_moves", "_monster_ok", "_listed", "_astock", "_stumps", "_tlseq")    # rebuilt on demand

    def sd(self, name, default):
        """setdefault for game attributes (not via __dict__: that slows every attribute under PyPy)."""
        v = getattr(self, name, None)
        if v is None:
            v = default
            setattr(self, name, v)
        return v

    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k not in self.CACHES}

    def save(self, path):
        rec, self.record_dir = getattr(self, "record_dir", None), None   # never pickled
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            savefile.write(self, f)               # versioned header + zstd pickle (sim/savefile.py)
        import os
        os.replace(tmp, path)        # atomic: the viewer never sees a half-written save
        self.record_dir = rec

    @staticmethod
    def load(path):
        """Load a save. The catalog is re-read from data/ so edits to data/*.json apply to old saves. Any file
        sim/savefile.py knows: ours (any format version), a bare pickle (older saves), or an original Zeus .map /
        .pak (a new game on that map), an original .sav (converted, sim/savimport.py)."""
        k = savefile.kind(path)
        if k in ("map", "pak"):
            return Game(path)
        if k == "sav":                            # an original saved game: converted (sim/savimport.py)
            from . import savimport
            g = savimport.load(path)
            empire.loaded(g)                      # game_file_load's fix-ups (FUN_00510ED0), as below
            return g
        g, _version = savefile.read(path)         # _version: migrations by format go here (FORMAT 1 = the first)
        g.__dict__.pop("gone", None)              # the live recorder's per-frame lists (sim/live.py)
        g.__dict__.pop("sfx", None)
        for k in Game.CACHES + ("_monster_ok", "_wolf_ok", "_net_rank"):   # rebuilt on demand; the last three are
            g.__dict__.pop(k, None)               # pickled, keyed by counters that restart (bug 386: stale land grid)
        if not isinstance(g.walkers, Walkers):    # saves from before the figure slots (11-02): slots in id order
            g.walkers = Walkers.adopt(g.walkers)
        from .military.forces import SANCT_LOOK   # sanctuary troops' pictures (11-02): soldiers already out
        for wk in g.walkers.values():
            if wk.role in ("rabble", "hoplite") and not wk.good and getattr(wk, "comp", 0) in SANCT_LOOK:
                wk.good = SANCT_LOOK[wk.comp]
        systems.agora.repair(g)                   # stalls lost to "clear" before 2026-10-28
        systems.walkers.reschedule_lost(g)        # walkers lost from the queue by a failed pass (bugs.md 484)
        g.cat = Catalog(difficulty=getattr(g, "difficulty", "Normal"))      # saves from before difficulty: Normal
        g.rules = g.cat.rules
        w = g.world
        migrate_points(g)                         # scenario points logical before 2026-10-29 (world.POINTS_V)
        if not hasattr(w, "sea_entry"):           # saves from before trade
            fresh = World(g.map_name)
            w.sea_entry, w.sea_exit = fresh.sea_entry, fresh.sea_exit
        if getattr(w, "avenue", None) is None:    # saves from before avenues followed roads: the old
            systems.avenues.grid(w)               # 2x2/3x3 avenue blocks are removed and refunded
            old = [b for b in g.buildings.values() if b.key in ("avenue", "boulevard")]
            for b in old:
                g.demolish(b.id)
                g.city.treasury += g.cat.spec(b.key)["cost"]
            if old:
                g.message(f"{len(old)} old avenue/boulevard blocks removed and refunded: build them along a road")
        systems.stadium.upgrade(g)                # 5x5 stadiums from before 2026-10-28 -> both halves
        systems.commemorative.adopt(g)            # monuments placed when they were freely buildable: variant 1
        systems.monuments.adopt(g)                # pooled materials (before 2026-10-28) -> per piece
        shore.remoor(g)                           # wharf boats/triremes moored by the pre-10-29 rule (bugs.md 173)
        if not getattr(g, "labor_prio_v", 0):     # saves from before 2026-10-29 started at 0 (no priority), not 3
            p = getattr(g, "labor_priority", None)
            if p:
                g.labor_priority = [3 if v == 0 else v for v in p]
            g.labor_prio_v = 1
        # rates set before 2026-10-29 could be any integer; the exe's sliders have fixed levels
        g.city.tax_rate = snap_level(tax_levels(g), g.city.tax_rate)
        g.city.wage_rate = snap_level(WAGE_LEVELS, g.city.wage_rate)
        if not hasattr(g, "empire"):              # saves from before the empire module: module off
            g.empire = None
        empire.loaded(g)                          # FUN_00510ED0 -> FUN_00461360: buys/sells flags (bug 472)
        from . import allowed
        allowed.mark(g)                           # FUN_00510ED0 -> rebuild_goods_lists: the sticky goods marks
        if "year_treasury" not in g.__dict__:     # saves from before 11-04: the treasury at the last year change
            g.year_treasury = year_treasury_of(g)  # (the year's last monthly snapshot), else the starting funds
        if getattr(g, "fire_v", 0) < 1:           # before 10-30 a ranch gathered fire risk but never lit (bug 290):
            for b in g.buildings.values():        # it starts at 0, no backlog (agoras never gathered any)
                if b.key == "horse_ranch":
                    b.fire_risk = 0
            g.fire_v = 1
        if getattr(g, "scenario_v", 0) < 1:       # saves from before the scenario events (2026-10-29): none;
            g.scenario, g.scenario_v = None, 1    # `scenario on` loads the map's episode (sim/scenario)
        if getattr(g, "store_v", 0) < 1:          # before 2026-10-29 storehouses/posts took horses and chariots
            # (imports from a partner selling chariots, chariot workshop carts); the exe never stores them
            # (storage_goods_list 0x005B12C0). They go back to the nearest chariot workshop up to its 400 cap,
            # as if never shipped; the rest is dropped (no refund: the exe has nowhere to keep them, and
            # a refund would invent money). bugs.md, economy.evict_unstorable.
            gone = systems.economy.evict_unstorable(g)
            if gone:
                g.message("storehouses and trading posts can't hold horses or chariots: "
                          + ", ".join(f"{n} {k}" for k, n in gone.items()) + " removed")
            g.store_v = 1
        if getattr(g, "goods_v", 0) < 1:          # before 2026-10-30 oranges (a Poseidon good) came in through our
            # trade partners; now off while Poseidon is off (the decision log 10-30): removed once, everywhere
            if not getattr(g, "poseidon", False) and g.cat.poseidon_goods:
                gone, orders = systems.economy.purge_goods(g, g.cat.poseidon_goods)
                if gone or orders:
                    names = ", ".join(sorted(g.cat.poseidon_goods))
                    g.message(f"{names.capitalize()} removed (a Poseidon good; `poseidon on` allows it): "
                              + ", ".join(f"{n} from {k}" for k, n in gone.items())
                              + (f"; {orders} trade/storage orders dropped" if orders else "")
                              + "; no partner trades it any more")
            g.goods_v = 1
        if getattr(g, "tick_v", 0) < 1:           # before 11-02 Game.step ran the figure pass before the cycle step:
            g.__dict__["_in_tick"] = True         # a save at tick N still waits for the pass at N, which Game.step
            try:                                  # now runs inside tick N (after its cycle step): run it here once
                systems.walkers.move_all(g)
            finally:
                g.__dict__.pop("_in_tick", None)
            g.tick_v = 1
        if getattr(g, "stump_v", 0) < 1:          # before 11-02 a cut tree lost its bit 0x1 until it grew back; the
            w = g.world                           # exe keeps it on the stump (regrowth < 255): give it back
            for _, x, y in getattr(g, "regrow", None) or ():
                if w.occ[y, x] == 0 and not w.road[y, x] and not w.avenue[y, x]:
                    w.flags[y, x] |= np.uint32(0x1)
            g.map_version = getattr(g, "map_version", 0) + 1
            g.stump_v = 1
        return g
