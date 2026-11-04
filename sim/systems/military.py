"""Armies (docs/logic/military.md "Recruitment"). There are no barracks in Zeus: soldiers live at home and
the palace keeps up to 20 companies of up to 8, filled from the houses:
- rabble from common houses (Hovel..Townhouse): ceil(residents * soldier % / 100) each, summed, / 6;
- hoplites from Mansions and Manors, as many as they hold armor (up to the house's max armor);
- horsemen from Estates with horses and armor; the rest of an Estate's share are hoplites.
Targets (military_recruit_targets 0x00567910) and companies (cycle_formations_pass_14 0x00567C70) are
recomputed daily; no palace = no companies. Soldiers stay in their houses until mobilized (the original
draws no idle soldiers), so a company is a count, not walkers.
On the map (mobilizing, marching, fighting, invasions): sim/military. Sanctuary companies 31..34 (Artemis, Ares):
sanctuary_companies below.
"""
import math

from . import index, walkers

TYPES = ("horseman", "hoplite", "rabble")      # the order the original spends the 20-company budget
MAX_COMPANIES = 20
PER_COMPANY = 8


def targets(g):
    """{type: soldiers} the houses support (military_recruit_targets)."""
    rabble = hop = horse = 0
    for b in index.of(g, "house"):
        h = g.cat.houses[b.level]
        s = math.ceil(b.occupants * h.get("soldier_pct", 0) / 100)
        if not s:
            continue
        if 2 <= b.level <= 6:
            rabble += s
        elif b.level in (10, 11):
            hop += min(s, b.goods.get("armor", 0), h["max_armor"])
        elif b.level == 12:
            a = min(b.goods.get("armor", 0), h["max_armor"])
            hs = min(b.goods.get("horses", 0), h["max_horses"])      # held as items (economy._peddle)
            n = min(s, hs, a)
            hop += min(s - n, a - n)
            horse += n
    return {"rabble": math.ceil(rabble / 6), "hoplite": hop, "horseman": horse}


def companies(g):
    return g.sd("companies", {})               # slot 1..20 -> {"type": t, "members": soldier count}; 21..30:
                                               # defensive aid on loan ("event": its empire event; sim/military)


def update(g):
    """Daily: recruit or disband so the palace companies match the targets. Frozen while invaders are on the map
    (steps 13/14 run only when g_enemy_units_alive == 0; sim/military.enemies_alive). Mobilized companies are never
    disbanded (only companies with all members home are, +0x03); their new recruits march out (sim/military)."""
    from .. import military as field_army
    if field_army.on(g) and field_army.enemies_alive(g):
        return
    comps = companies(g)
    if g.day % g.rules["days_per_month"] == 2:     # cycle_formations_pass_14 0x00567C70, day_of_month == 2
        sanctuary_companies(g)
    for c in comps.values():                      # saves from before soldiers stayed home (walker ids)
        if isinstance(c["members"], list):
            for i in c["members"]:
                if i in g.walkers:
                    walkers.remove(g, g.walkers[i])
            c["members"] = len(c["members"])
    if next(iter(index.keyed(g, "palace")), None) is None:     # no palace: every company at home disbands
        for s in [s for s, c in comps.items() if not c.get("away") and not c.get("mob") and not c.get("ids")
                  and not c.get("sanct") and not c.get("event")]:
            del comps[s]
        return
    want = targets(g)
    away = {s: c for s, c in comps.items() if c.get("away")}     # on a world-map expedition (sim/empire/war.py):
    keep = {s for s, c in comps.items() if c.get("mob") or c.get("ids")}    # in the field (sim/military)
    for c in away.values():                       # kept out of recruiting; their soldiers count as present
        want[c["type"]] = max(0, want[c["type"]] - c["members"])
    n_want = {t: math.ceil(want[t] / PER_COMPANY) for t in TYPES}
    if sum(n_want.values()) > MAX_COMPANIES - len(away):      # 20-company budget, horsemen first
        left = MAX_COMPANIES - len(away)
        for t in TYPES:
            n_want[t] = min(n_want[t], left)
            want[t] = min(want[t], n_want[t] * PER_COMPANY)
            left -= n_want[t]
    for t in TYPES:
        mine = [s for s, c in comps.items() if c["type"] == t and s not in away and not c.get("event")
                and not c.get("sanct")]
        while len([s for s in mine if s not in keep]) and len(mine) > n_want[t]:   # too many: free the smallest home one
            s = min((s for s in mine if s not in keep), key=lambda s: (comps[s]["members"], -s))
            del comps[s]
            mine.remove(s)
        have = sum(comps[s]["members"] for s in mine)
        while have < want[t]:                     # too few soldiers: fill companies, then new ones
            s = next((s for s in sorted(mine) if comps[s]["members"] < PER_COMPANY), None)
            if s is None:
                if len(mine) >= n_want[t]:
                    break
                s = next((i for i in range(1, MAX_COMPANIES + 1) if i not in comps), None)
                if s is None:
                    break
                comps[s] = {"type": t, "members": 0}
                mine.append(s)
            comps[s]["members"] += 1
            have += 1
        for s in sorted(mine, reverse=True):      # too many soldiers: they go home
            take = min(have - want[t], comps[s]["members"]) if have > want[t] else 0
            comps[s]["members"] -= take
            have -= take
            if not comps[s]["members"] and s not in keep:
                del comps[s]


def summary(g):
    comps = companies(g)
    out = {t: [0, 0] for t in TYPES}
    for c in comps.values():
        if c.get("event") or c.get("sanct"):      # defensive aid on loan (21..30), mythical warriors (31..34)
            continue
        out[c["type"]][0] += 1
        out[c["type"]][1] += c["members"]
    return out


# Sanctuary companies (cycle_formations_pass_14 0x00567C70 at day_of_month 2, formation_create_sanctuary 0x004E30F0):
# 31 / 32 Artemis (god 4, figure type 0xB: ours "rabble", +0x48 = 4), 33 / 34 Ares (god 5, type 0xC: "hoplite",
# +0x48 = 0). +0x94 = 1 (free deaths, no morale change), morale 100, ready.
SANCT = {31: ("artemis", "rabble"), 32: ("artemis", "rabble"), 33: ("ares", "hoplite"), 34: ("ares", "hoplite")}


def sanctuary_companies(g):
    """For each slot 31..34: not in use -> when the god's sanctuary is 100 % built, the company is created on the
    sanctuary (its first / second soldier-slot part for 31, 33 / 32, 34; ours: the sanctuary) and gets its first
    member at once; in use with fewer than 8 -> one more member a month while its sanctuary stands 100 % built,
    else every member is removed (state 2; the company goes with its last member). A full company is not checked
    (exe: an 8-member company outlives its sanctuary). New members appear at the sanctuary's road entry: ours keeps
    them as the count, like the palace companies at home."""
    from .. import gods
    from . import monuments
    comps = companies(g)
    for slot, (god, kind) in SANCT.items():
        c = comps.get(slot)
        if c is None:
            b = gods.sanctuary(g, gods.god_id(god))
            if b is None or not monuments.complete(b):
                continue
            c = comps[slot] = {"type": kind, "members": 0, "sanct": god, "home": b.id, "morale": 100,
                               "ready": True, "banner": slot - 1}
        if c["members"] >= PER_COMPANY:
            continue
        b = g.buildings.get(c.get("home"))
        if b is None or b.kind != "monument" or not monuments.complete(b):
            from ..military import forces
            for w in forces.members(g, c):
                forces.units.remove(g, w)
            del comps[slot]
            continue
        c["members"] += 1
