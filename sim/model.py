"""State records: buildings, walkers, city. Plain dataclasses so saves are a pickle away."""
from dataclasses import MISSING, dataclass, field, fields


def _fill_new_fields(obj, state):
    """Unpickling an old save: fields added since get their defaults (bugs.md 256: buildings without `misc`)."""
    obj.__dict__.update(state)
    for f in fields(obj):
        if f.name not in obj.__dict__:
            if f.default_factory is not MISSING:
                setattr(obj, f.name, f.default_factory())
            elif f.default is not MISSING:
                setattr(obj, f.name, f.default)


@dataclass
class Building:
    id: int
    key: str                    # catalog key
    x: int
    y: int
    size: int
    kind: str
    access: tuple = None        # road tile used as entrance (None = no road access)
    network: int = 0            # road network id of the access tile
    employees: int = 0
    # houses
    level: int = 0              # 0 = Hut .. 6 = Townhouse
    occupants: int = 0
    pending: int = 0            # immigrants on their way
    goods: dict = field(default_factory=dict)       # good -> units held (houses, vendors, storage, producers)
    coverage: dict = field(default_factory=dict)    # service -> days left
    devolve_count: int = 0
    hunger: int = 0             # months without food (0..3)
    fed: bool = True            # ate last month
    crime: int = 0
    tax_days: int = 0
    desirability: int = 0
    reason: str = ""            # why a house can't evolve / a building isn't working
    # risks
    fire_risk: int = 0
    damage_risk: int = 0
    burning: int = 0            # fire counter: 0 = not burning, 1..32 burning, ruins after 16
    # production / services
    progress: int = 0
    spawn_timer: int = 0
    walkers: list = field(default_factory=list)     # ids of own walkers out
    # orchard trees
    tend: int = 0               # days of tending left
    ripe: bool = False          # harvest flag set in the harvest month
    claimed: int = 0            # walker id heading here
    misc: dict = field(default_factory=dict)   # per-kind counters (corral: penned, slaughter, calf)

    __setstate__ = _fill_new_fields


@dataclass
class Walker:
    id: int
    role: str                   # service name | cart | buyer | peddler | immigrant
    home: int                   # building id
    x: int
    y: int
    path: list = field(default_factory=list)        # remaining tiles (destination walkers)
    prev: tuple = None
    roam_left: int = 0
    returning: bool = False
    target: int = 0             # destination building id
    good: str = ""
    amount: int = 0
    wait: int = 0               # immigrants: ticks until arrival
    load: dict = field(default_factory=dict)        # buyers: goods carried
    next_move: int = 0          # tick this walker acts next (scheduler)
    rem: int = 0                # sub-step remainder (pace)
    arrived: int = 0            # tick it reached its current tile (for smooth display)
    step_end: int = 0           # the next move scheduled on that tick: the step is drawn from arrived to here
    state: str = ""             # go | work | back (gatherers); held (animals)
    target_tile: tuple = None
    origin: tuple = None        # animals: home area
    ready: int = 0              # animals: wool/milk readiness 0..100
    task: str = ""              # growers: pick | tend
    out_loads: int = 0          # traders: loads exported / imported this visit
    in_loads: int = 0
    # melee (crime.melee, services.md §6.1): anim "fight" | "die" | "" (also drawn by the client),
    # anim_t0 = tick it began, busy_until = tick the fight ends (the walker stands still until then),
    # foe = opponent id, face = (dx, dy) facing, hits_t0 = tick the defender starts hitting this criminal
    anim: str = ""
    anim_t0: int = 0
    busy_until: int = 0
    foe: int = 0
    face: tuple = None
    hits_t0: int = 0
    mover: bool = False
    link: int = 0               # stonecutter <-> its marble cart (each holds the other's id)
    piece: int = -1             # artisans, monument carts: index of the monument piece (Figure+0x5E; systems/monuments.py)
    fslot: int = 0              # the exe's figure slot (1..1999; Walkers below): the order walkers act in within a tick


@dataclass
class City:
    treasury: int = 0
    tax_rate: int = 9
    wage_rate: int = 30
    sentiment: int = 60
    population: int = 0
    workforce: int = 0
    employed: int = 0
    unemployed: int = 0
    migration: int = 0
    immigrants_month: int = 0
    emigrants_month: int = 0
    months_in_debt: int = 0
    reached_350: bool = False
    ledger: dict = field(default_factory=dict)      # this month's income/expenses by line
    last_ledger: dict = field(default_factory=dict)
    messages: list = field(default_factory=list)    # (tick, text)
    foods_listed: set = field(default_factory=set)   # sticky city food list flags 0x00FEB0D2[res] (agora.city_foods)


Walker.__setstate__ = City.__setstate__ = _fill_new_fields


SLOTS = 2000            # figures 0x00DBD788: 2000 records, slot 0 is scratch


class Walkers(dict):
    """g.walkers (id -> Walker) with the exe's figure slots (docs/logic/walkers.md 2.1, 2.2): figure_create 0x004D9FD0
    takes the id at the head of a ring of free ids, figure_delete 0x004DA250 puts it back at the tail (FIFO reuse); a new
    city pushes 1, 2, .., 1999. walkers_update 0x004CC8C0 runs the figures in slot order 1..1999 every tick, so the slot
    decides who acts first within a tick (ours: systems/walkers.move_all). A walker gets its slot when it enters the
    table and gives it back when it leaves (any pop / del). Ours where the exe fails (all 1999 slots taken: figure_create
    returns 0, no figure): slots from 2000 on, in creation order. The ring is part of the save (the exe rebuilds it at
    every load, 1999 down to 1, sav_load 0x004D9F40; ours keeps it so a loaded game plays on as the running one did,
    bugs.md 315), except for games from before the slots (adopt)."""

    def __init__(self, *a, **kw):
        super().__init__()
        from collections import deque
        self.free = deque(range(1, SLOTS))
        self.over = SLOTS
        for k, v in dict(*a, **kw).items():
            self[k] = v

    def roles(self):
        """{role: count} of the walkers in the table (kept on every add and removal; rebuilt after a load)."""
        r = self.__dict__.get("_roles")
        if r is None:
            r = {}
            for w in dict.values(self):
                k = getattr(w, "role", None)
                r[k] = r.get(k, 0) + 1
            self.__dict__["_roles"] = r
        return {k: v for k, v in r.items() if v > 0}

    def _count(self, w, d):
        r = self.__dict__.get("_roles")
        if r is not None:
            k = getattr(w, "role", None)
            r[k] = r.get(k, 0) + d

    def _take(self):
        if self.free:
            return self.free.popleft()
        self.over += 1
        return self.over - 1

    def _give(self, w):
        s = getattr(w, "fslot", 0)
        if s and s < SLOTS:
            self.free.append(s)
        if s:
            w.fslot = 0

    def __setitem__(self, k, w):
        old = dict.get(self, k)
        if old is not None and old is not w:
            self._give(old)
            self._count(old, -1)
        if not getattr(w, "fslot", 0):
            w.fslot = self._take()
        if old is not w:
            self._count(w, 1)
        dict.__setitem__(self, k, w)

    def __delitem__(self, k):
        w = dict.__getitem__(self, k)
        dict.__delitem__(self, k)
        self._give(w)
        self._count(w, -1)

    def pop(self, k, *d):
        if k in self:
            w = dict.pop(self, k)
            self._give(w)
            self._count(w, -1)
            return w
        return dict.pop(self, k, *d)

    def popitem(self):
        k, w = dict.popitem(self)
        self._give(w)
        self._count(w, -1)
        return k, w

    def clear(self):
        for w in self.values():
            w.fslot = 0
        dict.clear(self)
        self.__dict__.pop("_roles", None)
        from collections import deque
        self.free = deque(range(1, SLOTS))
        self.over = SLOTS

    def setdefault(self, k, d=None):
        if k not in self:
            self[k] = d
        return dict.__getitem__(self, k)

    def update(self, *a, **kw):
        for k, v in dict(*a, **kw).items():
            self[k] = v

    def __reduce_ex__(self, proto):
        return (_walkers_new, (), {"free": self.free, "over": self.over}, None, iter(dict.items(self)))

    def __setstate__(self, st):
        self.__dict__.update(st)
        self.__dict__.pop("_roles", None)

    @staticmethod
    def adopt(d):
        """A plain dict from a save made before the slots: slots in id order (1, 2, ..), the rest free as after an exe
        load (1999 down to 1, sav_load 0x004D9F40)."""
        t = _walkers_new()
        for i, k in enumerate(sorted(d)):
            w = d[k]
            w.fslot = i + 1 if i + 1 < SLOTS else SLOTS + i
            dict.__setitem__(t, k, w)
        used = {w.fslot for w in d.values()}
        from collections import deque
        t.free = deque(s for s in range(SLOTS - 1, 0, -1) if s not in used)
        t.over = max([SLOTS] + [s + 1 for s in used if s >= SLOTS])
        return t


def _walkers_new():
    t = dict.__new__(Walkers)
    from collections import deque
    t.free, t.over = deque(range(1, SLOTS)), SLOTS
    return t   # old saves: new fields get their defaults
