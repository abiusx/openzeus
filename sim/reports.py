"""The original's 11 control-panel tabs as reports (manual: each tab's panel plus its
magnifying-glass screen): Population, Husbandry, Industry, Distribution, Hygiene/Safety,
Administration, Culture, Mythology, Military, Aesthetics, Overview. Read-only views of the state.

A report is a list of sections {title, rows: [[label, value, warn]], table: {cols, rows}};
warn = the original's yellow text (a problem). `report TAB` prints one; the viewer shows them all.
"""
import re

from .systems import housing, labor, health, trade, finance

TABS = ["population", "husbandry", "industry", "distribution", "hygiene", "administration", "culture",
        "mythology", "military", "aesthetics", "overview"]
CULTURE = [("philosophy", "philosophers", ("podium", "observatory")),
           ("athletics", "athletes", ("gymnasium", "bibliotheke")),
           ("drama", "actors", ("theatre", "laboratory")),
           ("competition", "competitors", ("stadium", "museum"))]
PRODUCERS = ("producer", "workshop", "herd", "lodge", "gather", "hunt", "fishery", "urchin", "corral",
             "ranch", "shipyard", "guild")


def sec(title, rows=(), table=None):
    s = dict(title=title, rows=[list(r) + [False] * (3 - len(r)) for r in rows])
    if table:
        s["table"] = table
    return s


def pct(a, b):
    return a * 100 // b if b else 0


def _houses(g):
    return [b for b in g.buildings.values() if b.kind == "house" and b.occupants]


def _name(g, key):
    return g.cat.spec(key).get("name", key)


def _problem(reason):
    """'needs workers (11/12)' -> 'needs workers' so like problems group together."""
    return re.sub(r" \(\d+/\d+\)", "", reason)


def _count(g, *keys):
    return sum(1 for b in g.buildings.values() if b.key in keys)


def produced_year(g):
    out = {}
    for m in getattr(g, "produced_hist", []):
        for k, v in m.items():
            out[k] = out.get(k, 0) + v
    return out


def food_stored(g):
    """0x00FE93C4 as the month's stock count (zeus.c 94008..94096) sums it: granaries (type 0x39) with road access
    (0x004A3FB0) only; agoras' and houses' stock is not counted (playtest haiku-2 #3: "food stored: 0" while the
    agoras held 2,053 is the exe's figure)."""
    return sum(s.goods.get(f, 0) for s in g.buildings.values() if s.kind == "storage" and s.access
               and g.cat.spec(s.key).get("accepts") == "food" and not g.cat.spec(s.key).get("endless")
               for f in g.cat.foods)


def food_per_month(g):
    """eat_food: occupants*25/100 a month per house (split across its food types)."""
    return sum(b.occupants * 25 // 100 for b in _houses(g))


def _walking(g):
    """Immigrants walking from the map entry (ours, playtest haiku-1 #13): they join the house on arrival."""
    ws = [w for w in g.walkers.values() if w.role == "immigrant"]
    return f"{sum(w.amount for w in ws)} immigrants in {len(ws)} groups" if ws else "nobody"


def population(g):
    c = g.city
    hs = [b for b in g.buildings.values() if b.kind == "house"]
    cap = sum(housing.capacity(g, b) for b in hs if b.access)
    room = sum(max(0, housing.capacity(g, b) - b.occupants - b.pending) for b in hs if b.access)
    last = g.history[-1] if g.history else {}
    imm, emi = last.get("immigrants", 0), last.get("emigrants", 0)
    trend = "growing" if imm > emi else "shrinking" if emi > imm else "stable"
    if c.migration <= 0:
        block = f"people are unhappy (sentiment {c.sentiment}): nobody wants to move here"
    elif room <= 0:
        block = "no room: build or improve housing"
    else:
        block = "none"
    common = sum(b.occupants for b in _houses(g) if b.level < 7)
    elite = sum(b.occupants for b in _houses(g) if b.level >= 7)
    levels = {}
    for b in _houses(g):
        n = g.cat.houses[b.level]["name"]
        r = levels.setdefault(b.level, [n, 0, 0, 0])
        r[1] += 1
        r[2] += b.occupants
        r[3] += housing.capacity(g, b)
    return [sec("Population", [["population", c.population], ["housing holds", cap],
                               ["room for", room, room == 0 and c.migration > 0],
                               ["trend", f"{trend} (last month +{imm} / -{emi})", emi > imm],
                               ["immigration limited by", block, block != "none"],
                               ["this month", f"+{c.immigrants_month} newcomers (counted when they set out from the map "
                                              f"entry, as the exe's 0x00FE9194)"],
                               ["on the way", _walking(g)]]),
            sec("Society", [["common residents", f"{common} ({c.workforce} of working age)"],
                            ["elite residents", elite],
                            ["rabble / hoplites / horsemen", "not simulated (no armies)"]]),
            sec("Housing", table=dict(cols=["level", "houses", "people", "holds"],
                                      rows=[v for _, v in sorted(levels.items())]))]


def husbandry(g):
    stored, month = food_stored(g), food_per_month(g)
    yr = produced_year(g)
    made = sum(yr.get(f, 0) for f in g.cat.foods)
    imported = sum((getattr(g, "trade_totals", None) or {}).get("imported", {}).get(f, 0) for f in g.cat.foods)
    months = len(getattr(g, "produced_hist", [])) or 1
    supports = made * 12 // months * 100 // (25 * 12)          # people one year's food feeds
    hungry = [b for b in _houses(g) if not b.fed]
    farms = {}
    for b in g.buildings.values():
        if b.kind in ("producer", "orchard", "herd", "hunt", "fishery", "urchin", "corral", "lodge"):
            farms[b.key] = farms.get(b.key, 0) + 1
    return [sec("Food", [["food stored", f"{stored} ({stored // month if month else 0} months)", month and stored < 3 * month],
                         ["eaten per month", month],
                         [f"produced, last {months} months", made],
                         ["production feeds", f"{supports} people (population {g.city.population})",
                          supports < g.city.population],
                         ["imported (total ever)", imported or "–"],
                         ["houses that went hungry last month", len(hungry), bool(hungry)]]),
            sec("Produced, last 12 months", table=dict(cols=["food", "units"],
                rows=[[f, yr[f]] for f in g.cat.foods if yr.get(f)])),
            sec("Husbandry buildings", table=dict(cols=["building", "count"],
                rows=[[_name(g, k), n] for k, n in sorted(farms.items())]))]


def industry(g):
    c = g.city
    jobs = getattr(g, "labor_jobs", {})
    prio = labor.priorities(g)
    wage_year = c.wage_rate * c.employed // 120 * 12
    rows = []
    for i, cat in enumerate(labor.CATEGORIES + ["towers/wharves"]):
        n, f = jobs.get(cat, [0, 0])
        rows.append([cat, prio[i] if i < len(prio) else "first", n, f, n - f])
    yr = produced_year(g)
    probs = {}
    for b in g.buildings.values():
        if b.kind in PRODUCERS and b.reason:
            probs.setdefault(_problem(b.reason), []).append(_name(g, b.key))
    return [sec("Workers", [["wage", f"{c.wage_rate} (≈{wage_year} dr a year)"],
                            ["employed", f"{c.employed} of {c.workforce}"],
                            ["unemployed", f"{c.unemployed} ({pct(c.unemployed, c.workforce)}%)", pct(c.unemployed, c.workforce) >= 10],
                            ["jobs open", sum(r[4] for r in rows), sum(r[4] for r in rows) > 0]]),
            sec("Labor allocation", table=dict(cols=["sector", "priority", "jobs", "filled", "open"], rows=rows)),
            sec("Produced, last 12 months", table=dict(cols=["good", "units"],
                rows=[[k, v] for k, v in sorted(yr.items()) if k not in g.cat.foods])),
            sec("Industry problems", [[k, f"{len(v)}× " + ", ".join(sorted(set(v))), True]
                                      for k, v in sorted(probs.items())] or [["none", ""]])]


def distribution(g):
    stored, posts = {}, {}
    for b in g.buildings.values():
        if b.kind == "storage" and not g.cat.spec(b.key).get("endless"):
            for k, v in b.goods.items():
                stored[k] = stored.get(k, 0) + v
        elif b.kind == "trade":
            for k, v in b.goods.items():
                posts[k] = posts.get(k, 0) + v
    flags = getattr(g, "stockpile", set())
    status = {}
    for b in g.buildings.values():
        if b.kind == "trade" and "partner" in b.misc:
            p = trade.partners(g)[b.misc["partner"]]["name"]
            for k, m in b.misc.get("orders", {}).items():
                status.setdefault(k, []).append(f"{m} {p}" + (f" ≤{trade.limit(g, b, k)}" if m == "export" else ""))
    tot = getattr(g, "trade_totals", None) or {}
    # the page's goods (FUN_00517E30): the city's goods list (rebuild_goods_lists 0x005BAAF0, in goods order; ours,
    # sandbox_open: every good a building makes, export.goods_list) and anything stored; the trade state per good
    # (0x01607EC4: 5 importing, 7 exporting, 9 neither) from the posts' orders, the last post in id order winning
    # (as live.py _adv_trade)
    from . import export, empire
    from .empire.model import GOOD_IDS
    gl = export.goods_list(g)
    goods = sorted(set(gl) | {k for k, v in stored.items() if v} | {k for k, v in posts.items() if v},
                   key=lambda k: GOOD_IDS.get(k, 99))
    state = {}
    for b in sorted((b for b in g.buildings.values() if b.kind == "trade"), key=lambda b: b.id):
        if "partner" not in b.misc:
            continue
        for k in goods:
            o = trade.order(g, b, k)
            if o == "export" or (o == "import" and empire.trading(g, b.misc["partner"])):
                state[k] = 7 if o == "export" else 5
    rows = [[k, stored.get(k, 0), posts.get(k, 0), "yes" if k in flags else "", "; ".join(status.get(k, [])) or "",
             tot.get("exported", {}).get(k, 0), tot.get("imported", {}).get(k, 0), state.get(k, 9)] for k in goods]
    ag = [b for b in g.buildings.values() if b.kind == "agora"]
    return [sec("Inventory", table=dict(cols=["good", "stored", "at posts", "stockpiled", "trade", "exported", "imported", "state"],
                                        rows=rows)),
            sec("Storage and markets", [["granaries", _count(g, "granary")], ["storehouses", _count(g, "storehouse")],
                                        ["agoras", f"{len(ag)} holding {sum(sum(a.goods.values()) for a in ag)} units"],
                                        ["trade posts / piers", sum(1 for b in g.buildings.values() if b.kind == "trade")]])]


def hygiene(g):
    st = getattr(g, "health_state", {})
    h = st.get("health", 80)
    chance = next((c for th, c in health.PLAGUE_CHANCE if th > h), 0)
    hs = _houses(g)
    P = sum(b.occupants for b in hs)
    healed = sum(1 for b in hs if b.coverage.get("healer"))
    fed = sum(b.occupants for b in hs if b.fed)
    infected = sum(1 for b in hs if b.misc.get("infected"))
    t = g.rules["risk_threshold"]
    others = [b for b in g.buildings.values() if b.kind not in ("road", "decor", "ruin", "agora", "monument")]
    fire = sum(1 for b in others if b.fire_risk >= t // 2)
    dmg = sum(1 for b in others if b.damage_risk >= t // 2)
    common = [b for b in hs if b.level < 7]
    crime = sum(b.crime for b in common) // len(common) if common else 0
    crims = len(getattr(g, "criminals", set()) & set(g.walkers))
    c = g.city
    return [sec("Hygiene", [["health", f"{h} (target {st.get('target', 80)})", h < 75],
                            ["plague chance", f"{chance / 100:.2f}% a day" if chance else "none", bool(chance)],
                            ["houses visited by a healer", f"{pct(healed, len(hs))}%", healed < len(hs)],
                            ["residents who ate last month", f"{pct(fed, P)}%", fed < P],
                            ["infected houses", infected, bool(infected)],
                            ["plague deaths (total)", st.get("deaths", 0)],
                            ["water: houses with a fountain", f"{pct(sum(1 for b in common if b.coverage.get('water')), len(common))}%"]]),
            sec("Safety", [["maintenance offices", _count(g, "maintenance")],
                           ["burning now", sum(1 for b in g.buildings.values() if b.burning), any(b.burning for b in g.buildings.values())],
                           ["buildings at high fire risk", fire, bool(fire)],
                           ["buildings at high collapse risk", dmg, bool(dmg)],
                           ["fires / collapses (total)", f"{getattr(c, 'fires', 0)} / {getattr(c, 'collapses', 0)}"]]),
            sec("Unrest", [["average unrest (common houses)", crime, crime >= 70],
                           ["guardposts", _count(g, "guardpost")],
                           ["criminals in the streets", crims, bool(crims)],
                           ["thefts / muggings (total)", f"{getattr(c, 'thefts', 0)} / {getattr(c, 'muggings', 0)}"]])]


def administration(g):
    c = g.city
    hs = _houses(g)
    reg = sum(1 for b in hs if b.tax_days > 0)
    yr = g.history[-12:]
    prev = g.history[-24:-12]
    net = lambda rows: sum(r.get("taxes", 0) - r.get("wages", 0) for r in rows)
    levels = g.rules["tax_levels"]
    word = ["(none)", "(very low)", "(low)", "(normal)", "(high)", "(very high)", "(outrageous)"][
        finance._nearest([lv["rate"] for lv in levels], c.tax_rate)]
    return [sec("Taxes", [["tax rate", f"{c.tax_rate}% {word}".strip()],
                          ["palace", "yes" if _count(g, "palace") else "none (no tax offices without one)", not _count(g, "palace")],
                          ["tax offices", _count(g, "tax_office")],
                          ["houses registered by a clerk", f"{reg} of {len(hs)} ({pct(reg, len(hs))}%)", reg < len(hs)],
                          ["taxes, last 12 months", sum(r.get("taxes", 0) for r in yr)]]),
            sec("Treasury", [["treasury", f"{c.treasury} dr", c.treasury < 0],
                             ["months in debt", c.months_in_debt, c.months_in_debt > 0],
                             ["taxes - wages, last 12 months", net(yr), net(yr) < 0],
                             ["taxes - wages, the 12 before", net(prev) if prev else "–"]]),
            sec("Last month", [[k, v] for k, v in (c.last_ledger or {}).items()] or [["–", ""]])]


def culture(g):
    common = [b for b in _houses(g)]
    rows = []
    for svc, who, keys in CULTURE:
        cov = sum(1 for b in common if b.coverage.get(svc))
        rows.append([svc, ", ".join(f"{_count(g, k)} {_name(g, k)}" for k in keys), f"{pct(cov, len(common))}%"])
    schools = [[_name(g, k), _count(g, k)] for k in ("college", "drama_school", "university", "inventors_workshop")]
    return [sec("Culture", table=dict(cols=["kind", "venues", "houses reached"], rows=rows)),
            sec("Schools", table=dict(cols=["school", "count"], rows=schools)),
            sec("Games", [["Pan-Hellenic games", "not simulated (scripted events are out of scope)"]])]


def mythology(g):
    rows = []
    for b in sorted(g.buildings.values(), key=lambda b: b.id):
        if b.kind == "monument" and b.key != "palace":
            done = b.misc.get("built", 0)
            rows.append([_name(g, b.key), f"({b.x},{b.y})", f"{done}%", "complete" if done >= 100 else (b.reason or "building")])
    return [sec("Sanctuaries and monuments", table=dict(cols=["name", "at", "built", "status"], rows=rows or [["none", "", "", ""]])),
            sec("Gods, monsters, heroes", [["", "not simulated (out of scope)"]])]


def military(g):
    towers = [b for b in g.buildings.values() if b.key == "tower"]
    wh = [b for b in g.buildings.values() if b.kind == "shipyard"]
    tri = [w for w in g.walkers.values() if w.role == "trireme"]
    off = getattr(g, "towers_off", None)
    from .systems import military as mil
    comps = mil.summary(g)
    want = mil.targets(g)
    return [sec("Companies", table=dict(cols=["type", "companies", "soldiers", "houses support"],
                                        rows=[[t, comps[t][0], comps[t][1], want[t]] for t in mil.TYPES])),
            sec("Forces", [["companies", f"{sum(v[0] for v in comps.values())} of {mil.MAX_COMPANIES} (palace needed)",
                            not index_palace(g)],
                           ["triremes", len(tri)],
                           ["warship wharves", ", ".join(f"({b.x},{b.y}) {b.employees} workers" + (" (sent home)" if b.misc.get("off") else "") for b in wh) or "none"],
                           ["towers", f"{len(towers)} " + ("(ordered unmanned: `towers on`)" if off else
                                                         f"manned, {sum(b.employees for b in towers)} sentries"), bool(off and towers)],
                           ["gatehouses", _count(g, "gatehouse")],
                           ["wall tiles", int((g.world.flags & 0x4000 != 0).sum())],
                           ["armories / chariot workshops", f"{_count(g, 'armory')} / {_count(g, 'chariot_workshop')}"]]),
            sec("Threats", [["invasions", "none (not simulated; companies are never called to arms)"]])]


def index_palace(g):
    return any(b.key == "palace" for b in g.buildings.values())


def aesthetics(g):
    deco = {}
    for b in g.buildings.values():
        if b.kind == "decor":
            deco[b.key] = deco.get(b.key, 0) + 1
    hs = _houses(g)
    des = [b.desirability for b in hs]
    held = [b for b in hs if "desirab" in (b.reason or "") or "appeal" in (b.reason or "")]
    mons = [f"({b.x},{b.y})" for b in g.buildings.values() if b.key == "commemorative_monument"]
    return [sec("Appeal", [["average appeal of houses", sum(des) // len(des) if des else 0],
                           ["lowest / highest", f"{min(des)} / {max(des)}" if des else "–"],
                           ["houses held back by appeal", len(held), bool(held)]]),
            sec("Commemorative monuments", [["", ", ".join(mons) or "none"]]),
            sec("Beautification", table=dict(cols=["building", "count"],
                                             rows=[[_name(g, k), n] for k, n in sorted(deco.items())]))]


def overview(g):
    c = g.city
    s = c.sentiment
    pop = "very popular" if s >= 80 else "popular" if s >= 60 else "tolerated" if s >= 40 else "unpopular" if s >= 20 else "hated"
    stored, month = food_stored(g), food_per_month(g)
    fm = stored // month if month else 99
    jobs = getattr(g, "labor_jobs", {})
    open_ = sum(n - f for n, f in jobs.values())
    u = pct(c.unemployed, c.workforce)
    h = getattr(g, "health_state", {}).get("health", 80)
    common = [b for b in _houses(g) if b.level < 7]
    crime = sum(b.crime for b in common) // len(common) if common else 0
    yr, prev = g.history[-12:], g.history[-24:-12]
    net = lambda rows: sum(r.get("treasury", 0) for r in rows[-1:]) - sum(r.get("treasury", 0) for r in rows[:1])
    fin = net(yr)
    probs = {}
    for b in g.buildings.values():
        if b.reason and b.reason != "top level":
            probs[_problem(b.reason)] = probs.get(_problem(b.reason), 0) + 1
    top = sorted(probs.items(), key=lambda kv: -kv[1])[:6]
    return [sec("City update", [["popularity", f"{pop} ({s})", s < 40],
                                ["food", f"{fm} months stored" if month else "nobody eats yet", month and fm < 3],
                                ["employment", f"{u}% unemployed" if c.unemployed else f"{open_} jobs open" if open_ else "everyone employed",
                                 u >= 10 or open_ > 0],
                                ["hygiene", h, h < 75],
                                ["unrest", "high" if crime >= 70 else "some" if crime >= 40 else "low", crime >= 70],
                                ["finances", f"treasury {'up' if fin >= 0 else 'down'} {abs(fin)} dr over the last 12 months", fin < 0],
                                ["threats", "none"]]),
            sec("Requests", [["", "none (other cities' requests are not simulated)"]]),
            sec("Problems", [[k, f"{n}×", True] for k, n in top] or [["none", ""]])]


def all_reports(g):
    return {t: globals()[t](g) for t in TABS}


def text(g, tab):
    out = []
    for s in globals()[tab](g):
        out.append(f"== {s['title']}")
        for label, value, warn in s["rows"]:
            out.append(f"  {'!' if warn else ' '} {label}{': ' if label else ''}{value}")
        t = s.get("table")
        if t:
            cols = t["cols"]
            w = [max(len(str(r[i])) for r in [cols] + t["rows"]) for i in range(len(cols))]
            for r in [cols] + t["rows"]:
                out.append("    " + "  ".join(str(v).ljust(w[i]) for i, v in enumerate(r)))
    return "\n".join(out)
