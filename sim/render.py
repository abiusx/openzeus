"""Text views: ASCII map, status report, tile info, catalog."""
from .systems import housing, finance, labor
from . import testcmds

TERRAIN_CH = {"land": ".", "meadow": ",", "water": "~", "tree": "T", "rock": "^", "marble": "M",
              "copper": "c", "silver": "s", "rubble": "r", "wall": "w",
              "cliff": "#", "offmap": " "}
KIND_CH = {"service": "S", "producer": "P", "workshop": "W", "storage": "G", "vendor": "V",
           "admin": "A", "decor": "*", "herd": "P", "lodge": "P", "gather": "P", "orchard": "o", "ranch": "P",
           "hunt": "P", "fishery": "P", "urchin": "P", "corral": "P",
           "school": "S", "hippodrome": "S", "trade": "X", "ruin": "!", "stall": "V", "gatehouse": "D", "tower": "Y", "monument": "&", "guild": "W", "shipyard": "P"}


def building_char(g, b):
    if b.kind == "house":
        if b.level >= 7:                      # elite: e lot/devolved, R Residence, N Mansion, O Manor, S Estate
            return "eeRNOS"[b.level - 7]
        return str(b.level + 1) if b.occupants or b.level else "h"
    spec = g.cat.spec(b.key)
    custom = {"fountain": "F", "granary": "G", "storehouse": "H", "maintenance": "m", "guardpost": "g",
              "tax_office": "$", "infirmary": "+", "palace": "A",
              "endless_warehouse": "X"}
    return custom.get(b.key, KIND_CH.get(b.kind, "?"))


def look(g, x0, y0, w=60, h=30):
    world = g.world
    walk = {(wk.x, wk.y) for wk in g.walkers.values() if wk.role != "immigrant"}
    blocks = getattr(g, "roadblocks", ())
    lines = ["     " + "".join(str((x0 + i) // 10 % 10) if (x0 + i) % 10 == 0 else " " for i in range(w)),
             "     " + "".join(str((x0 + i) % 10) for i in range(w))]
    legend = {}
    for y in range(y0, y0 + h):
        row = []
        for x in range(x0, x0 + w):
            if not (0 <= x < 228 and 0 <= y < 228):
                row.append(" ")
                continue
            bid = int(world.occ[y, x])
            if bid:
                b = g.buildings[bid]
                ch = building_char(g, b)
                legend[ch] = "house (digit = level, h = empty lot)" if b.kind == "house" else legend.get(ch, b.key)
                if ch in legend and legend[ch] != b.key and b.kind != "house" and b.key not in legend[ch]:
                    legend[ch] += "/" + b.key
            elif world.road[y, x]:
                ch = "o" if (x, y) in walk else "%" if (x, y) in blocks else "@" if world.avenue[y, x] else "="
            elif world.avenue[y, x]:
                ch = "\""
            else:
                ch = TERRAIN_CH[world.kind(x, y)]
            if (x, y) == world.entry:
                ch = "E"
            elif (x, y) == world.exit:
                ch = ">"
            row.append(ch)
        lines.append(f"{y:4d} " + "".join(row))
    lines.append("terrain: . land  , meadow  ~ water  T trees  ^ rock  M marble  c copper  s silver  # cliff  r rubble  w wall | = road  @ avenue/boulevard road  \" its side strip  % roadblock  o walker  E entry  > exit")
    if legend:
        lines.append("buildings: " + "  ".join(f"{k} {v}" for k, v in sorted(legend.items())))
    return "\n".join(lines)


def _on_the_way(g):
    """Ours (playtest haiku-1 #13, bugs.md 282): people walking from the map entry to houses with room are in no
    count until they arrive (0x004AC810 adds them to the house and the population)."""
    ws = [w for w in g.walkers.values() if w.role == "immigrant"]
    if not ws:
        return ""
    return f"  on the way: {sum(w.amount for w in ws)} immigrants ({len(ws)} walkers from the map entry)"


def city_problems(g, hs, stocks):
    """Ours (playtest haiku-3 #1, #3, #4): city-wide problems the exe leaves to its info panels and advisors."""
    out = []
    keys = {b.key for b in g.buildings.values()}
    if "tax_office" in keys and "palace" not in keys:          # 0x0048CFB0 case 0x7A; info text 106:11
        out.append("no palace: tax offices send no clerks, no taxes are collected")
    common = [b for b in hs if b.occupants and not g.cat.houses[b.level].get("elite")]
    if common:
        from .reports import CULTURE
        for svc, _, venues in CULTURE:
            have = [b for b in g.buildings.values() if b.key in venues and b.employees]
            if have and not any(b.coverage.get(svc) for b in common):
                out.append(f"{svc}: {len(have)} venue(s) reach no house (walkers roam from the venue's road;"
                           f" `coverage {svc}`)")
    short = {}
    goods = {g.cat.spec(k).get("goods") for k, s in g.cat.buildings.items() if s["kind"] == "vendor"} - {"food"}
    for b in hs:
        need = b.reason.rsplit("needs ", 1)[-1] if "needs " in b.reason else ""
        if need in goods:
            n = short.setdefault(need, [0, 0])
            n[0] += 1
            n[1] += b.reason.startswith("devolving")
    for good, (n, dev) in sorted(short.items()):
        dry = [a for a in g.buildings.values() if a.kind == "agora" and not a.goods.get(good)
               and any(st.key != "empty_stall" and g.cat.spec(st.key).get("goods") == good for st in _stalls(g, a))]
        out.append(f"{good} short: {n} houses" + (f" ({dev} devolving)" if dev else "") + f", in storage {stocks.get(good, 0)}"
                   + (f", agoras selling it but empty: {', '.join(f'#{a.id} ({a.x},{a.y})' for a in dry[:4])}" if dry else ""))
    return out


def _stalls(g, a):
    from .systems import agora
    return agora.stalls(g, a)


def status(g):
    c = g.city
    hs = [b for b in g.buildings.values() if b.kind == "house"]
    levels = {}
    for b in hs:
        if b.occupants:
            n = g.cat.houses[b.level]["name"]
            levels[n] = levels.get(n, 0) + 1
    vac = sum(max(0, housing.capacity(g, b) - b.occupants - b.pending) for b in hs if b.access)
    stocks = {}
    for b in g.buildings.values():
        if b.kind == "storage" and b.key != "endless_warehouse":
            for k, v in b.goods.items():
                if v: stocks[k] = stocks.get(k, 0) + v
    out = [f"{g.date()}  tick {g.tick}  day {g.day}  difficulty {getattr(g, 'difficulty', 'Normal')}",
           testcmds.summary(g) + "  (sim/testcmds.py)",
           f"treasury {c.treasury} dr   tax {c.tax_rate}%  wage {c.wage_rate}   last month: {c.last_ledger or '-'}",
           f"population {c.population}  vacancies {vac}  sentiment {c.sentiment}/100 (migration {c.migration:+d}%)"
           + _on_the_way(g),
           f"sentiment change per half-month: {finance.sentiment_parts(g)} (damped toward 41..60)",
           f"workforce {c.workforce} ({labor.workforce_pct(g)}% of common residents)  employed {c.employed}  unemployed {c.unemployed}  "
           f"jobs {sum(v[0] for v in g.__dict__.get('labor_jobs', {}).values())} "
           f"(open: {', '.join(f'{k} {n - f}' for k, (n, f) in g.__dict__.get('labor_jobs', {}).items() if n > f) or 'none'})   labor priority: "
           + (", ".join(f"{n} {v}" for n, v in zip(labor.CATEGORIES, labor.priorities(g)) if v) or "none set"),
           f"houses {len(hs)}: {levels or '-'}",
           f"buildings {len(g.buildings)}  walkers {len(g.walkers)}   health {g.__dict__.get('health_state', {}).get('health', 80)}"
           f" (target {g.__dict__.get('health_state', {}).get('target', 80)}), plague deaths {g.__dict__.get('health_state', {}).get('deaths', 0)}, fires {getattr(c, 'fires', 0)}",
           f"storage: {stocks or '-'}",
           f"surplus (endless warehouse, total ever): {g.__dict__.get('surplus') or '-'}"]
    tt = getattr(g, "trade_totals", None)
    posts = [b for b in g.buildings.values() if b.kind == "trade"]
    if posts or tt:
        held = {}
        for b in posts:
            for k, v in b.goods.items():
                if v: held[k] = held.get(k, 0) + v
        out.append(f"trade: {len(posts)} posts/docks, holding {held or '-'}; exported {(tt or {}).get('exported') or '-'}, "
                   f"imported {(tt or {}).get('imported') or '-'} (units, total; `trade` for partners)")
    problems = {}
    for b in g.buildings.values():
        if b.reason and b.kind != "house":
            problems.setdefault(b.reason, []).append(f"{b.key}#{b.id}")
    hreasons = {}
    for b in hs:
        if b.reason and b.reason != "top level":
            hreasons[b.reason] = hreasons.get(b.reason, 0) + 1
    city = city_problems(g, hs, stocks)
    if problems or city:
        out.append("problems: " + "; ".join(city + [f"{r}: {', '.join(v[:4])}{'...' if len(v) > 4 else ''}"
                                                    for r, v in problems.items()]))
    if hreasons:
        out.append("houses: " + "; ".join(f"{n} x {r}" for r, n in sorted(hreasons.items(), key=lambda x: -x[1])))
    recent = [m for t, m in c.messages if t > g.tick - 16 * 51]
    if recent:
        out.append("recent: " + " | ".join(recent[-6:]))
    return "\n".join(out)


def info(g, x, y):
    w = g.world
    out = [f"tile ({x},{y}): {w.kind(x, y)}, elevation {w.elev[y, x]}, desirability {w.des[y, x]}"
           + (", road" if w.road[y, x] else "")
           + (f", {('avenue', 'boulevard')[(int(w.avenue[y, x]) >> 8) - 1]}" + ("" if w.road[y, x] else " side strip")
              if w.avenue[y, x] else "")]
    bid = int(w.occ[y, x])
    if not bid and w.road[y, x]:        # an agora's road strip: the agora (not on the occupancy grid)
        bid = next((a.id for a in g.buildings.values() if a.key in ("agora", "grand_agora")
                    and (x, y) in a.misc.get("strip", ())), 0)
    if bid:
        b = g.buildings[bid]
        spec = g.cat.spec(b.key)
        size = f"{b.misc['w']}x{b.misc['h']}" if "w" in b.misc and "h" in b.misc else b.size
        out.append(f"{spec['name']} #{b.id} at ({b.x},{b.y}) size {size}, access {b.access}, "
                   f"employees {b.employees}/{spec['employees']} ({labor.staffing(g, b)}%)")
        if b.kind == "house":
            out.append(f"  {g.cat.houses[b.level]['name']} (level {b.level + 1}/{len(g.cat.houses)}), occupants {b.occupants}/"
                       f"{housing.capacity(g, b)} (+{b.pending} arriving), desirability {b.desirability}, "
                       f"culture {housing.culture(g, b)}, crime {b.crime}, hunger {b.hunger}")
            out.append(f"  coverage {b.coverage}  tax_days {b.tax_days}")
        out.append(f"  goods {dict((k, v) for k, v in b.goods.items() if v)}  progress {b.progress}  "
                   f"fire {b.fire_risk} damage {b.damage_risk}")
        if spec.get("needs_shows"):     # ours (playtest haiku-3 #1): a venue performs while it has shows
            out.append(f"  shows {b.misc.get('shows', 0)} (a performer from its school sets 32; -1 a day; its walker"
                       f" roams {g.rules.get('walker_roam', {}).get(spec.get('service'), g.rules['walker_roam_max'])}"
                       f" road tiles: `coverage {spec.get('service')}` shows the houses reached)")
        out.extend(_walkers_out(g, b))
        ag = g.buildings.get(b.misc.get("agora")) if b.kind == "stall" else None
        if ag:                          # the stock lives in the agora, not in the stall (storage-distribution.md B)
            out.append(f"  agora #{ag.id} stock {dict((k, v) for k, v in ag.goods.items() if v)} (stalls keep none;"
                       f" the agora's peddler hands it out)")
        if b.reason:
            out.append(f"  status: {b.reason}")
    return "\n".join(out)


def _walkers_out(g, b):
    """Ours (playtest haiku-3 #2): the building's walkers, carts with their load and destination."""
    ws = [g.walkers[w] for w in b.walkers if w in g.walkers]
    if not ws:
        return []
    parts, plain = [], {}
    for w in ws:
        if w.role in ("cart", "buyer") and (w.amount or w.target):
            dest = g.buildings.get(w.target)
            to = f" -> {g.cat.spec(dest.key)['name']} #{dest.id} ({dest.x},{dest.y})" if dest else \
                (" waiting: no place to take it" if w.amount else "")
            parts.append(f"{w.role} {w.good or ''} {w.amount or 0}{to} at ({w.x},{w.y})")
        else:
            plain[w.role] = plain.get(w.role, 0) + 1
    parts += [f"{r} x{n}" if n > 1 else r for r, n in plain.items()]
    return ["  walkers out: " + "; ".join(parts)]


def catalog(g):
    out = ["key                  size cost  workers kind      notes"]
    for k, s in sorted(g.cat.buildings.items(), key=lambda kv: (kv[1]["kind"], kv[0])):
        note = []
        for f in ("service", "output", "input", "needs", "accepts", "goods", "animal", "trees"):
            if f in s: note.append(f"{f}={s[f]}")
        d = s["desirability"]
        if d["value"]: note.append(f"des={d['value']}/{d['range']}")
        if s.get("poseidon") and not getattr(g, "poseidon", False):     # playtest haiku-2 #9
            note.insert(0, "POSEIDON ONLY (off: `poseidon on`)")
        if s.get("test"):                                                # not in the original (sim/testcmds.py)
            note.insert(0, "TEST ONLY (counted)")
        out.append(f"{k:20s} {s['size']:4d} {s['cost']:5d} {s['employees']:6d}  {s['kind']:9s} {' '.join(note)}")
    return "\n".join(out)


def overview(g, step=3):
    """Whole map, one char per step x step block (most common terrain; buildings/roads win)."""
    world = g.world
    lines = []
    for y in range(0, 228, step):
        row = []
        for x in range(0, 228, step):
            ks = {}
            occupied = False
            for yy in range(y, min(228, y + step)):
                for xx in range(x, min(228, x + step)):
                    if world.occ[yy, xx] or world.road[yy, xx]:
                        occupied = True
                    k = world.kind(xx, yy)
                    ks[k] = ks.get(k, 0) + 1
            if any(abs(world.entry[0] - xx) < step and abs(world.entry[1] - yy) < step
                   for xx, yy in [(x, y)]):
                row.append("E")
            elif occupied:
                row.append("@")
            else:
                row.append(TERRAIN_CH[max(ks, key=ks.get)])
        lines.append(f"{y:4d} " + "".join(row))
    lines.append(f"one char = {step}x{step} tiles; x = column*{step}. @ = built. terrain as in look.")
    return "\n".join(lines)


def houses_report(g):
    """Every house with coordinates, level, people, and what it needs."""
    out = ["   x   y  level        people  des  missing / status"]
    for b in sorted((b for b in g.buildings.values() if b.kind == "house"), key=lambda b: (b.y, b.x)):
        out.append(f"{b.x:4d} {b.y:3d}  {b.level + 1} {g.cat.houses[b.level]['name']:10s} {b.occupants:3d}/{housing.capacity(g, b):<3d} "
                   f"{b.desirability:4d}  {b.reason or '-'}")
    return "\n".join(out)


def coverage_map(g, service, x0=None, y0=None, w=60, h=30):
    """ASCII map: houses with the service (+), without (-), the service's buildings (S), roads (=)."""
    if x0 is None:
        hs = [b for b in g.buildings.values() if b.kind == "house"] or list(g.buildings.values())
        x0 = min((b.x for b in hs), default=g.world.entry[0]) - 4
        y0 = min((b.y for b in hs), default=g.world.entry[1]) - 4
    world = g.world
    rows = [f"coverage of '{service}'  (+ served house, - unserved house, S {service} building, = road)"]
    for y in range(y0, y0 + h):
        row = []
        for x in range(x0, x0 + w):
            if not (0 <= x < 228 and 0 <= y < 228):
                row.append(" "); continue
            bid = int(world.occ[y, x])
            if bid:
                b = g.buildings[bid]
                spec = g.cat.spec(b.key)
                if b.kind == "house":
                    ok = (b.tax_days > 0) if service == "tax" else (b.crime < 50) if service == "watchman" else \
                         (b.damage_risk < 500 and b.fire_risk < 500) if service == "maintenance" else bool(b.coverage.get(service))
                    row.append("+" if ok else "-")
                elif spec.get("service") == service or (service == "peddler" and b.kind == "vendor"):
                    row.append("S")
                else:
                    row.append("#")
            else:
                row.append("=" if world.road[y, x] else " ")
        rows.append(f"{y:4d} " + "".join(row))
    return "\n".join(rows)


def risk_report(g, top=15):
    t = g.rules["risk_threshold"]
    bs = sorted(g.buildings.values(), key=lambda b: -max(b.fire_risk, b.damage_risk))
    out = [f"highest fire/collapse risk (destroyed at {t}; maintenance walkers lower it)"]
    for b in bs[:top]:
        if max(b.fire_risk, b.damage_risk) <= 0: break
        out.append(f"  {b.key}#{b.id} at ({b.x},{b.y}): fire {b.fire_risk}, collapse {b.damage_risk}")
    return "\n".join(out)


def stability(g, settle_months=24):
    """Devolutions after the setpoint = the last non-time command + settle_months (trees grow, harvest and get pressed:
    up to two years). An ideal layout has none: every need is met all the time, so
    houses converge to their top level and stay. Returns (text, count after the setpoint)."""
    last = max((t for t, _ in g.log), default=0)
    sp = last + settle_months * g.rules["ticks_per_day"] * g.rules["days_per_month"]
    log = getattr(g, "devolve_log", [])
    settling = [d for d in log if last < d[0] <= sp]
    after = [d for d in log if d[0] > sp]
    reasons = {}
    for _, x, y, lvl, why in after:
        k = why.split(":")[-1].strip()
        reasons[k] = reasons.get(k, 0) + 1
    houses = sorted({(x, y) for _, x, y, _, _ in after})
    txt = (f"stability: {len(after)} devolutions after the setpoint (last build tick {last} + {settle_months} months; "
           f"{len(settling)} while settling)" + (f"; houses {houses[:8]}{'...' if len(houses) > 8 else ''}; reasons {reasons}"
                                                 if after else ""))
    if g.tick <= sp:
        txt += "  [run ended before the setpoint]"
    return txt, len(after)
