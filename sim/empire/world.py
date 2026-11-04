"""World files: custom worlds as data (docs/world-format.md). data/world/<name>.json -> model.Empire, the same
records scenario.py fills from a Zeus map. A game picks one with `empire on NAME` (new games keep the map's own
scenario world). `empire on NAME --migrate` switches a save that already has trading posts (migrate()).

Every error names the file and the field (WorldError)."""
import json
import os

from .model import City, Empire, GOOD_IDS, expand

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIR = os.path.join(ROOT, "data", "world")

KINDS = ("player", "colony", "foreign", "parent", "distant", "enchanted", "destroyed")
RELATIONS = ("ally", "rival", "vassal", "colony")
LABELS = ("left", "right", "top", "bottom")
GOODS = tuple(k for k in GOOD_IDS if k not in ("drachmas", "troops", "food", "strike"))
# marker size by kind (the world objects of the Zeus maps: data/empire/sandbox*.json) and icon (atlas index)
SIZE = {"player": (33, 38, 1038), "parent": (33, 38, 1038), "colony": (23, 25, 1039), "foreign": (32, 33, 1041),
        "distant": (27, 22, 1056), "enchanted": (32, 33, 1041), "destroyed": (32, 33, 1041)}
PICTURE_SIZE = (838, 738)            # Zeus_MapOfGreece01..10
MAX_GOODS = 10                       # buys + sells rows that fit the side panel's goods frame (world.js, compact)
SPACING = 5                          # route dot spacing of every Zeus map route (+0x00)


class WorldError(ValueError):
    pass


def names():
    return sorted(f[:-5] for f in os.listdir(DIR) if f.endswith(".json")) if os.path.isdir(DIR) else []


def path_of(name):
    return name if name.endswith(".json") else os.path.join(DIR, f"{name}.json")


def available(name):
    return os.path.exists(path_of(name))


def load_world(name):
    """data/world/NAME.json (or a path) -> Empire. Raises WorldError with every problem found."""
    p = path_of(name)
    if not os.path.exists(p):
        raise WorldError(f"no world '{name}' (data/world/: {', '.join(names()) or 'none'})")
    try:
        d = json.load(open(p))
    except json.JSONDecodeError as ex:
        raise WorldError(f"{os.path.relpath(p, ROOT)}: not valid JSON: {ex}")
    errs = []
    emp = build(d, errs)
    if errs:
        raise WorldError(f"{os.path.relpath(p, ROOT)}:\n  " + "\n  ".join(errs))
    emp.source = os.path.relpath(p, ROOT)
    return emp


def _num(errs, where, v, lo, hi, integer=True):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or (integer and not isinstance(v, int)):
        errs.append(f"{where}: must be {'an integer' if integer else 'a number'}, got {v!r}")
        return False
    if not lo <= v <= hi:
        errs.append(f"{where}: {v} not in {lo}..{hi}")
        return False
    return True


def _point(errs, where, p):
    if not (isinstance(p, list) and len(p) == 2):
        errs.append(f"{where}: must be [x, y], got {p!r}")
        return False
    return _num(errs, f"{where} x", p[0], 0, PICTURE_SIZE[0] - 1) & _num(errs, f"{where} y", p[1], 0, PICTURE_SIZE[1] - 1)


def _goods(errs, where, v):
    if not isinstance(v, dict):
        errs.append(f"{where}: must be {{good: yearly loads}}, got {v!r}")
        return {}
    out = {}
    for g, q in v.items():
        if g not in GOODS:
            errs.append(f"{where}: unknown good '{g}' (one of {', '.join(GOODS)})")
        elif _num(errs, f"{where}.{g}", q, 0, 999):
            out[g] = q
    return out


CITY_KEYS = {"name", "short", "leader", "kind", "relation", "route", "nation", "buys", "sells", "attitude",
             "wealth", "strength", "tribute", "active", "visible", "resources", "map", "path", "note"}


def _city(errs, i, r, player_xy):
    w = f"cities[{i}]" + (f" ({r.get('name')})" if isinstance(r, dict) and r.get("name") else "")
    if not isinstance(r, dict):
        errs.append(f"{w}: must be an object")
        return None, None
    for k in r:
        if k not in CITY_KEYS:
            errs.append(f"{w}: unknown field '{k}' (fields: {', '.join(sorted(CITY_KEYS))})")
    name = r.get("name")
    if not isinstance(name, str) or not name.strip():
        errs.append(f"{w}.name: required, a non-empty string")
        name = f"city{i}"
    kind = r.get("kind", "foreign")
    if kind not in KINDS:
        errs.append(f"{w}.kind: '{kind}' not one of {', '.join(KINDS)}")
        kind = "foreign"
    rel = r.get("relation", "colony" if kind == "colony" else "ally")
    if rel not in RELATIONS:
        errs.append(f"{w}.relation: '{rel}' not one of {', '.join(RELATIONS)}")
        rel = "ally"
    route = r.get("route", "land")
    if route not in ("land", "sea"):
        errs.append(f"{w}.route: '{route}' not land or sea")
        route = "land"
    c = City(id=i, name=name, short=r.get("short", name), leader=r.get("leader", ""), kind=kind, relation=rel,
             route=route, buys=_goods(errs, f"{w}.buys", r.get("buys", {})),
             sells=_goods(errs, f"{w}.sells", r.get("sells", {})))
    if len(c.buys) + len(c.sells) > MAX_GOODS:
        errs.append(f"{w}: {len(c.buys)} buys + {len(c.sells)} sells; the world map panel shows at most {MAX_GOODS} goods")
    for k, lo, hi, dflt in (("nation", 0, 4, 0), ("attitude", 0, 100, 50), ("wealth", 1, 5, 3), ("strength", 1, 6, 3)):
        v = r.get(k, dflt)
        if _num(errs, f"{w}.{k}", v, lo, hi):
            setattr(c, k, v)
    for k in ("active", "visible"):
        v = r.get(k, True)
        if not isinstance(v, bool):
            errs.append(f"{w}.{k}: must be true or false")
        else:
            setattr(c, k, v)
    t = r.get("tribute")
    if t is not None:
        if not isinstance(t, dict) or set(t) - {"mode", "amount", "good", "claim"}:
            errs.append(f"{w}.tribute: must be {{mode, amount, good, claim}}")
        else:
            mode = {"none": 0, "pays": 1, "receives": 2}.get(t.get("mode", "none"))
            if mode is None:
                errs.append(f"{w}.tribute.mode: '{t.get('mode')}' not none, pays (to you) or receives (from you)")
                mode = 0
            good = t.get("good")
            if good is not None and good not in GOODS + ("drachmas",):
                errs.append(f"{w}.tribute.good: unknown good '{good}'")
            c.tribute = dict(mode=mode, amount=t.get("amount", 0), good=good, claim=t.get("claim", 0))
            _num(errs, f"{w}.tribute.amount", c.tribute["amount"], 0, 100000)
            _num(errs, f"{w}.tribute.claim", c.tribute["claim"], 0, 100)
    res = r.get("resources", [])
    if kind == "player":
        c.resources = [g for g in res if g in GOODS]
        for g in res:
            if g not in GOODS:
                errs.append(f"{w}.resources: unknown good '{g}'")
    m = r.get("map")
    wd, ht, icon = SIZE[kind]
    if not isinstance(m, dict) or "x" not in m or "y" not in m:
        errs.append(f"{w}.map: required, {{x, y, label}} on the {PICTURE_SIZE[0]}x{PICTURE_SIZE[1]} picture")
        return c, None
    _point(errs, f"{w}.map", [m["x"], m["y"]])
    label = m.get("label", "bottom")
    if label not in LABELS:
        errs.append(f"{w}.map.label: '{label}' not one of {', '.join(LABELS)}")
    c.map = dict(x=m["x"], y=m["y"], w=m.get("w", wd), h=m.get("h", ht), icon=m.get("icon", icon), label=label)
    path = r.get("path")
    if kind == "player":
        if path is not None:
            errs.append(f"{w}.path: the player city has no route of its own (routes end at it)")
        return c, None
    if path is None:
        path = []
    if not isinstance(path, list) or not all(_point(errs, f"{w}.path[{k}]", p) for k, p in enumerate(path)):
        if not isinstance(path, list):
            errs.append(f"{w}.path: must be a list of [x, y]")
        return c, None
    return c, [[m["x"], m["y"]]] + [list(p) for p in path] + ([list(player_xy)] if player_xy else [])


def build(d, errs):
    if not isinstance(d, dict):
        errs.append("top level: must be an object")
        return None
    for k in d:
        if k not in ("format", "version", "name", "note", "picture", "cities", "routes"):
            errs.append(f"unknown top-level field '{k}'")
    if d.get("format") != "world" or d.get("version") != 1:
        errs.append('"format": "world" and "version": 1 are required')
    pic = d.get("picture", 1)
    _num(errs, "picture", pic, 1, 10)
    rows = d.get("cities")
    if not isinstance(rows, list) or not rows:
        errs.append("cities: required, a non-empty list")
        return None
    players = [r for r in rows if isinstance(r, dict) and r.get("kind") == "player"]
    if len(players) != 1:
        errs.append(f"cities: exactly one city must have \"kind\": \"player\" (found {len(players)})")
    pm = players[0].get("map") if players and isinstance(players[0].get("map"), dict) else {}
    pxy = (pm["x"], pm["y"]) if "x" in pm and "y" in pm else None
    cities, routes, seen = [], [], set()
    for i, r in enumerate(rows):
        c, pts = _city(errs, i, r, pxy)
        if c is None:
            continue
        if c.name.lower() in seen:
            errs.append(f"cities[{i}].name: '{c.name}' appears twice")
        seen.add(c.name.lower())
        if c.kind == "colony" and c.relation == "colony" and c.tribute["mode"] != 1:   # as scenario.py
            c.tribute["mode"] = 1
        cities.append(c)
        if pts and pxy and c.kind not in ("enchanted", "destroyed"):
            routes.append(dict(a=c.id, b=0, kind=c.route, spacing=SPACING, percent=0, points=pts,
                               dots=expand(pts, SPACING)))
    if not cities:
        return None
    pid = next((c.id for c in cities if c.kind == "player"), 0)
    for r in routes:
        r["b"] = pid
    byname = {c.name.lower(): c for c in cities}
    for k, r in enumerate(d.get("routes", [])):              # extra routes between any two cities
        w = f"routes[{k}]"
        if not isinstance(r, dict) or not {"from", "to", "points"} <= set(r):
            errs.append(f"{w}: must be {{from, to, kind, points}}")
            continue
        a, b = byname.get(str(r["from"]).lower()), byname.get(str(r["to"]).lower())
        if a is None or b is None:
            errs.append(f"{w}: unknown city '{r['from'] if a is None else r['to']}'")
            continue
        if r.get("kind", "land") not in ("land", "sea"):
            errs.append(f"{w}.kind: not land or sea")
        if not all(_point(errs, f"{w}.points[{j}]", p) for j, p in enumerate(r["points"])):
            continue
        pts = [[a.map["x"], a.map["y"]]] + [list(p) for p in r["points"]] + [[b.map["x"], b.map["y"]]]
        routes.append(dict(a=a.id, b=b.id, kind=r.get("kind", "land"), spacing=SPACING, percent=0, points=pts,
                           dots=expand(pts, SPACING)))
    return Empire(cities, routes, pic, "")


# --- switching a save onto a world ---------------------------------------------------------------

def migrate(g, emp):
    """Put `emp` on game g, which may already have trading posts bound to the old partner list (data/trade.json
    or another world): each post/dock is re-bound to the city of the same name, caravans and ships under way
    keep going to the same post, and this year's used quotas move with them. Refuses when a bound partner has
    no city of that name in the new world, or its route kind differs. Returns a report line."""
    from ..systems import trade, walkers
    old = trade.partners(g)
    by_name = {c.name.lower(): c for c in emp.cities.values()}
    remap, errs = {}, []
    for b in g.buildings.values():
        if b.kind != "trade" or b.misc.get("partner") is None:
            continue
        i = b.misc["partner"]
        nm = old[i]["name"] if 0 <= i < len(old) else f"#{i}"
        c = by_name.get(nm.lower())
        if c is None:
            errs.append(f"{b.key} at ({b.x},{b.y}) trades with {nm}, which this world lacks")
        elif c.route != old[i]["route"]:
            errs.append(f"{b.key} at ({b.x},{b.y}): {nm} trades by {old[i]['route']} here, by {c.route} in the world")
        elif not c.tradeable():
            errs.append(f"{b.key} at ({b.x},{b.y}): {nm} is not a trading partner in the world ({c.cls()})")
        else:
            remap[i] = c.id
    if errs:
        raise WorldError("cannot migrate:\n  " + "\n  ".join(errs))
    st = trade.state(g)
    for i, ci in enumerate(old):                # partners without a post: map by name when they exist
        c = by_name.get(ci["name"].lower())
        if i not in remap and c is not None:
            remap[i] = c.id
    g.empire = emp
    n = len(trade.partners(g))
    new = dict(used=[{} for _ in range(n)], countdown=[0] * n, traders=[[] for _ in range(n)], cursor={})
    for i, j in remap.items():
        if i < len(st["used"]):
            new["used"][j] = dict(st["used"][i])
            new["countdown"][j] = st["countdown"][i]
            new["traders"][j] = list(st["traders"][i])
    moved = 0
    for b in g.buildings.values():
        if b.kind == "trade" and b.misc.get("partner") in remap:
            b.misc["partner"] = remap[b.misc["partner"]]
            moved += 1
    gone = 0
    for w in list(g.walkers.values()):           # traders/ships carry their partner in w.good (trade.trader)
        if w.id in g.walkers and w.role in ("trader", "ship") and str(w.good).isdigit():
            i = int(w.good)
            if i in remap:
                w.good = str(remap[i])
            else:                                # a partner the world lacks (no post): its caravan is removed
                drop, gone = {w.id}, gone + 1
                while True:                      # with its donkeys (each follows the one before: target)
                    more = {d.id for d in g.walkers.values() if d.role == "donkey" and d.target in drop} - drop
                    if not more:
                        break
                    drop |= more
                for k in drop:
                    if k in g.walkers:
                        walkers.remove(g, g.walkers[k])
    g.trade_state = new
    return f"{moved} trade buildings re-bound by name; {len(remap)} partners mapped" + (f"; {gone} caravans dropped" if gone else "")
