"""Houses: needs, evolve/devolve, consumption (docs/logic/housing.md, housing-evolution.md)."""

LUXURIES = (("wine", "wine"), ("fleece", "fleece"), ("olive_oil", "oil"))   # (good, house spec column)
DURABLES = (("armor", "arms"), ("horses", "horses"))                         # held, never consumed
COMMON_TOP, ELITE_LOT, ELITE_DEVOLVED, ELITE_FIRST, ELITE_TOP = 6, 7, 8, 9, 12


def houses(g):
    from . import index
    return list(index.of(g, "house"))


def road_check(g):
    """Cycle step 21 for houses (buildings_road_access 0x004856A0, buildings.md §6), once a day: a house
    with no road beside it for 5 checks in a row is removed and its people walk out homeless; an empty
    Hut whose road the map entry can't reach is removed after 9 checks."""
    from . import walkers
    n = g.world.flags.shape[0]
    field = None
    for b in houses(g):
        c = b.misc.get("noroad", 0)
        if b.access is None:
            c += 1
            if c > 4:
                if b.occupants:
                    walkers.spawn_homeless(g, b, b.occupants)
                    g.city.population -= b.occupants
                    b.occupants = 0
                g.demolish(b.id, "has no road access")
                continue
        else:
            field = field or walkers.entry_field(g)
            x, y = b.access
            if field[y * n + x] >= 0:
                c = 0
            else:
                c += 1
                if c > 8:
                    c = 0
                    if b.level == 0 and b.occupants == 0:
                        g.demolish(b.id, "has no road to the city entry")
                        continue
        if c:
            b.misc["noroad"] = c
        else:
            b.misc.pop("noroad", None)


def is_elite(b):
    return b.level >= ELITE_LOT


def lose_soldier(g, b, horse=False):
    """A fallen hoplite / horseman is charged to elite house b (figure_delete 0x004DA250): 1 armor, a horseman
    also 1 horse, and 1 resident (population_sub(1))."""
    for good, n in (("armor", 1), ("horses", 1 if horse else 0)):
        if n and b.goods.get(good, 0) > 0:
            b.goods[good] -= n
    if b.occupants > 0:
        b.occupants -= 1
        g.city.population -= 1


def capacity(g, b):
    if b.level == ELITE_LOT:              # vacant elite lot takes its first settlers (housing.md §4)
        return g.cat.houses[ELITE_DEVOLVED]["capacity"]
    return g.cat.houses[b.level]["capacity"]


def food_types_held(g, b):
    return sum(1 for f in g.cat.foods if b.goods.get(f, 0) > 0)


def culture(g, b):
    pts = g.rules["culture_points"]
    c = sum(v for s, v in pts.items() if b.coverage.get(s, 0) > 0)
    return c + services.unique_venue_bonus(g)


def missing(g, b, level):
    """First unmet requirement of house level `level`, or '' if all are met."""
    h = g.cat.houses[level]
    if h["water"] and not b.coverage.get("water"): return "water"
    if h["culture"]:
        c = culture(g, b)
        if c < h["culture"]: return f"culture {c}/{h['culture']}"
    if h["food_types"]:
        f = food_types_held(g, b)
        if f < h["food_types"]: return f"food types {f}/{h['food_types']}"
    for good, col in LUXURIES + DURABLES:
        if b.goods.get(good, 0) < h.get(col, 0): return good
    return ""


def update(g):
    w = g.world
    des = getattr(g, "_desl", None)
    if des is None:
        des = g._desl = w.des.ravel().tolist()
    for b in houses(g):
        elite = is_elite(b)
        top = ELITE_TOP if elite else COMMON_TOP
        floor = ELITE_DEVOLVED if elite else 0
        limit = 10 if elite else 3
        b.desirability = max(des[y * 228 + x] for y in range(b.y, b.y + b.size) for x in range(b.x, b.x + b.size)) \
            + (10 if desirability.next_to_water(g, b) else 0)      # step 38: + 10 next to water (0x004842A0)
        if b.access is None:
            b.reason = "no road access"
            continue
        if (b.level <= 1 or b.level == ELITE_LOT) and b.occupants == 0:
            b.reason = "empty"
            continue
        h = g.cat.houses[b.level]
        d = b.desirability
        if b.level == ELITE_LOT:              # settlers moved in: a Residence (housing.md §2)
            b.level = ELITE_FIRST
            continue
        if b.level == ELITE_DEVOLVED:         # back to Residence as soon as its needs are met, no des gate
            need = missing(g, b, ELITE_FIRST)
            if not need:
                b.level, b.reason = ELITE_FIRST, ""
            else:
                b.reason = f"to evolve needs {need}"
            continue
        dv, ev = des_gate(g, h)
        r = -1 if d <= dv else (1 if d >= ev else 0)
        need_now = missing(g, b, b.level)
        if need_now:
            r = -1
        elif r == 1 and b.level < top:
            need_next = missing(g, b, b.level + 1)
            if need_next:
                r = 0
        if r == -1:
            if b.level == floor:
                b.reason = f"needs {need_now}" if need_now else "low desirability"
                continue
            b.devolve_count += 1
            b.reason = f"devolving: needs {need_now}" if need_now else f"devolving: desirability {d} <= {dv}"
            if b.devolve_count >= limit:
                b.devolve_count = 0
                b.level -= 1
                g.message(f"house at ({b.x},{b.y}) devolved to {g.cat.houses[b.level]['name']}")
                g.sd("devolve_log", []).append((g.tick, b.x, b.y, b.level, b.reason))
        else:
            b.devolve_count = 0
            if r == 1 and b.level < top:
                b.level += 1
                b.reason = ""
            elif b.level >= top:
                b.reason = "top level"
            elif d < ev:
                b.reason = f"needs desirability {ev} (has {d})"
            else:
                b.reason = f"to evolve needs {missing(g, b, b.level + 1)}"


def des_gate(g, h):
    """(devolve, evolve) desirability of house row h: house_param 0x00433D80 cols 0 / 1, both - 10 while Aphrodite's
    sanctuary is active (god record 6, ecx 0x00EF5F10); house_desirability_gate 0x00484360 compares them."""
    from .. import gods
    k = 10 if gods.active_now(g, 6) else 0
    return h["devolve_des"] - k, h["evolve_des"] - k


def consume_luxuries(g):
    for b in houses(g):
        if not b.occupants:
            continue
        h = g.cat.houses[b.level]
        for good, col in LUXURIES:
            if h[col]:
                b.goods[good] = max(0, b.goods.get(good, 0) - h[col])


def eat_food(g):
    """Monthly: occupants*25/100 of each needed food type (split across types); a house with
    horses also feeds them 1 food unit, else one horse starves (housing.md §3)."""
    for b in houses(g):
        if b.goods.get("horses"):
            f = next((f for f in g.cat.foods if b.goods.get(f, 0) >= 1), None)
            if f:
                b.goods[f] -= 1
            else:
                b.goods["horses"] -= 1
        nf = g.cat.houses[b.level]["food_types"]
        amt = b.occupants * 25 // 100
        if nf > 1:
            amt //= nf
        eaten = 0
        if b.occupants:
            for f in g.cat.foods:
                have = b.goods.get(f, 0)
                if have:
                    b.goods[f] = max(0, have - amt)
                    eaten += 1
                    if eaten >= max(nf, 1):
                        break
        b.fed = eaten > 0


from . import services, desirability  # noqa: E402  (circular: imported last)
