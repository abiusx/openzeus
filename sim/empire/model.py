"""The empire's data model (docs/logic/world-map.md "Interface"): one generic record per world city, the
routes between cities, and the empire as a whole. Filled by one loader (scenario.py) from a Zeus map; a
later loader may fill the same records from a simulated or saved city.

Field names follow the exe's WorldCity record (empire.md) in plain words. Goods are our resource keys;
'drachmas' is the money item. Quantities: buys/sells are yearly quotas in loads (1 load = 100 units,
a sculpture = 400 units).
"""
import math

# items that can be asked for / given (world-map.md 4.1, 4.2); exe item ids in brackets
MONEY, TROOPS, FOOD, STRIKE = "drachmas", "troops", "food", "strike"       # 23, 24, 25, 27
GOOD_IDS = {"urchin": 1, "fish": 2, "meat": 3, "cheese": 4, "carrots": 5, "onions": 6, "wheat": 7, "oranges": 8,
            "wood": 9, "bronze": 10, "marble": 11, "grapes": 12, "olives": 13, "fleece": 14, "horses": 15,
            "black_marble": 16, "orichalc": 17, "armor": 18, "sculpture": 19, "olive_oil": 20, "wine": 21,
            "chariot": 22, MONEY: 23, TROOPS: 24, FOOD: 25, STRIKE: 27}
FOODS = ("urchin", "fish", "meat", "cheese", "carrots", "onions", "wheat", "oranges")


def expand(ctrl, spacing):
    """Route dots (FUN_004622F0 per segment, map load FUN_005118C0): t = 0, s, 2s, ... <= length;
    point = p0 + (p1 - p0) * t / length (truncated; the exe's x87 rounding is not checked: hypothesis).
    Used by tools/build_empire.py (Zeus maps) and world.py (world files)."""
    dots = []
    if spacing <= 0:
        return dots
    for i in range(1, len(ctrl)):
        (x0, y0), (x1, y1) = ctrl[i - 1], ctrl[i]
        length = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
        if length == 0:
            continue
        t = 0
        while t <= length:
            dots.append([int(x0 + (x1 - x0) * t / length), int(y0 + (y1 - y0) * t / length)])
            t += spacing
    return dots


def units(good, loads):
    """event_amount_units 0x00466E30: loads -> units (sculpture 400 per load)."""
    return loads * (400 if good == "sculpture" else 100)


def loads(good, n_units):
    return n_units // (400 if good == "sculpture" else 100)


class City:
    """One world city. kind: player | colony | foreign | parent | distant | enchanted | destroyed;
    relation: ally | rival | vassal | colony (WorldCity +0xD4)."""

    def __init__(self, **kw):
        self.id = 0
        self.name = self.short = self.leader = ""
        self.kind = "foreign"
        self.relation = "ally"
        self.route = "land"            # +0x10: land caravans or sea ships
        self.nation = 0                # +0xCC: army / icon nationality (text group 37)
        self.buys = {}                 # good -> yearly quota (loads); the player exports these
        self.sells = {}                # good -> yearly quota; the player imports these
        self.resources = []            # player city only: goods it may produce
        self.attitude = 50             # 0..100
        self.pleased = 0               # streaks 0..50 (+0x168 / +0x16C)
        self.displeased = 0
        self.wealth = 3                # 1..5
        self.strength = 3              # military strength 1..6 (6 = invincible)
        self.army = 0                  # soldiers at home (+0x1E8)
        self.away = [0, 0, 0]          # +0x1EC/+0x1F0/+0x1F4: away (strike / ally help / defensive aid)
        self.troops_return = [0, 0]    # +0xCA months, +0xCB troops coming back
        self.tribute = dict(mode=0, claim=0, amount=0, good=None)   # mode 0 none, 1 pays you, 2 you pay it
        self.trade_open = True         # +0x05
        self.active = True             # +0x170
        self.visible = True            # !(+0x174 & 4)
        self.rebellion = False         # +0x174 & 1
        self.extorted = False          # +0x175: gave the debt rescue gift
        self.request_fatigue = {}      # item -> +15 per request, -1 per month; asks allowed while < 21
        self.gift_fatigue = {}         # good -> +12 per player gift (cap 48), -1 per month
        self.history = []              # (month index, text, attitude change)
        self.map = None                # {x, y, w, h, icon (atlas index), label}
        self.__dict__.update(kw)

    # --- predicates (empire.md "Predicates") ---
    def cls(self):
        """city_class 0x0042CF10."""
        if self.kind == "player":
            return "self"
        if self.kind == "colony":
            return "rival" if self.relation == "rival" else "colony"
        if self.kind == "parent":
            return "parent"
        if self.kind == "distant":
            return "distant"
        if self.kind != "foreign":
            return "other"
        return {"ally": "ally", "vassal": "vassal"}.get(self.relation, "rival")

    def exists(self):
        """city_exists 0x0042CAE0."""
        return self.kind not in ("distant", "enchanted", "destroyed") and self.active and self.visible

    def tradeable(self):
        """city_tradeable 0x0042C9C0."""
        return (self.kind not in ("player", "enchanted", "destroyed") and self.active and self.visible
                and self.relation != "rival")

    def trading(self):
        """is_trading_partner 0x0042C9F0."""
        return self.tradeable() and self.trade_open

    def shown(self):
        """FUN_00599D30: drawn on the map (not invisible, not an inactive colony)."""
        return self.visible and not (self.kind == "colony" and not self.active)

    def trades_something(self):
        """!city_trades_nothing 0x005B93A0."""
        return any(self.buys.values()) or any(self.sells.values())


class Empire:
    def __init__(self, cities, routes, picture=1, source=""):
        self.cities = {c.id: c for c in cities}
        self.routes = routes           # [{a, b, kind, spacing, points, dots}]
        self.picture = picture         # Zeus_MapOfGreece<NN>
        self.source = source
        self.events = []               # sim/empire/events.py
        self.next_event = 1
        self.months = 0                # months since the start (0x00903114, army target)
        self.peak_strength = 0         # g_military_strength_peak 0x00FE6A78
        self.totals = dict(gifts_given=0, gifts_received=0, tribute_paid=0, tribute_received=0)

    def player(self):
        return next(c for c in self.cities.values() if c.kind == "player")

    def find(self, name):
        n = name.lower()
        for c in self.cities.values():
            if c.name.lower() == n or str(c.id) == n:
                return c
        hits = [c for c in self.cities.values() if c.name.lower().startswith(n)]
        if len(hits) == 1:
            return hits[0]
        raise ValueError(f"unknown city '{name}' ({', '.join(c.name for c in self.cities.values())})")

    def route(self, a, b):
        """route_between 0x00462910."""
        for r in self.routes:
            if {r["a"], r["b"]} == {a, b}:
                return r
        return None

    def travel_months(self, a, b):
        """route_travel_months 0x004625A0: max(2, dots * spacing / 200)."""
        r = self.route(a, b)
        if not r:
            return 2
        return max(2, len(r["dots"]) * r["spacing"] // 200)
