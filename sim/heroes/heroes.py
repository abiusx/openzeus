"""Heroes (docs/logic/heroes-monsters.md "Heroes"): the 8 hero records (g_hero_records 0x00F0E4E8), their Hero's Halls
(building 125, `heroes_hall`, misc["hero"] = hall +0x12), the 5 requirements (g_hero_requirements 0x0063B3D0,
hero_requirement_met 0x004FBC20), the monthly check (heroes_month_check 0x00524860), Send For (hero_send_for
0x004FC2B0) and the hero figure (figure type 0x45, figure_hero_update 0x004C8F50).

Record (state(g)["heroes"][h]): hall (building id), fig (walker id), needed (+0x0C), met [5] (+0x0D), all_met (+0x12),
text (+0x14, the 'needed' text), sent (+0x18), paid (+0x19), announced (+0x1A).
"""
from . import state, data, hrng, cache
from ..systems import walkers

HERO = "hero"


def records(g):
    r = state(g).get("records")
    if r is None:
        r = state(g)["records"] = [dict(hall=0, fig=0, needed=0, met=[0] * 5, all_met=0, text=0, sent=0, paid=0,
                                        announced=0) for _ in range(8)]
    return r


def record(g, h):
    return records(g)[h]


def episode_reset(g):
    """The continue start (episode_start_load 0x00420390, kind 2), after the halls (0x7D) are freed: FUN_00511DE0
    clears every record's needed (+0x0C), 'needed' text (+0x14 = -1), sent (+0x18), paid (+0x19) and announced
    (+0x1A) (requirements +0x0D..+0x12 kept); then every hero figure (0x45) in use is set to state 2 (removed at
    once, away on a quest or not). Only a monster still on the map announces its hero again (sim/episode.py
    monsters_announce), so a hall is offered again only then (bugs.md 397)."""
    for r in records(g):
        r.update(needed=0, text=-1, sent=0, paid=0, announced=0, fig=0)
    from ..military import units
    for w in [w for w in g.walkers.values() if w.role == HERO]:
        units.remove(g, w)


def name(h):
    return data()["heroes"][h]["name"]


def hall(g, h):
    """hero_record_hall 0x004FA5D0: the hero's hall (type 125 with +0x12 = h), or None."""
    r = record(g, h)
    b = g.buildings.get(r["hall"])
    if b is not None and b.key == "heroes_hall" and b.misc.get("hero") == h:
        return b
    for b in g.buildings.values():
        if b.key == "heroes_hall" and b.misc.get("hero") == h:
            r["hall"] = b.id
            return b
    r["hall"] = 0
    return None


def figure(g, h):
    """hero_record_figure 0x004FAA00: the hero's figure when it is on the map and alive."""
    w = g.walkers.get(record(g, h)["fig"])
    if w is not None and w.role == HERO and getattr(w, "hero", -1) == h and w.anim != "die":
        return w
    return None


def present(g, h):
    """hero_present 0x004FA4A0."""
    return figure(g, h) is not None


def hero_of_slot(g, k):
    """scenario_hero_of_monster_slot 0x00586C40."""
    from . import monster_of_slot
    m = monster_of_slot(g, k)
    return data()["monsters"][m]["hero"] if 0 <= m < 16 else -1


def needed(g, h, text185, reason=None):
    """hero_needed_message 0x004FA710(text, extra): once (+0x0C), only when the episode's allowed flag 26 (heroes'
    halls, 0x00902D64 = 0x00902D30 + 2 * 26) is set (open play: set; Zeus and Europa episode 1: not, bugs.md 379):
    +0x14 = the 185 text (the hall window's bottom line), message 0xE0 PHRASE_<hero>_hall_available title /
    announcement / reason (extra, else base + 2); the hall becomes buildable."""
    from .. import allowed
    r = record(g, h)
    if not allowed.flag(g, 26) or r["needed"]:
        return
    r["needed"] = 1
    r["text"] = text185
    from .events import post
    base = HALL_AVAILABLE[h]
    post(g, base, base + 1, reason if reason is not None else base + 2)


# --- requirements -------------------------------------------------------------------------------------------

def _res_key(g, rid):
    for r in g.cat.resources.values() if isinstance(g.cat.resources, dict) else g.cat.resources:
        if (r.get("zeus_id") if isinstance(r, dict) else getattr(r, "zeus_id", None)) == rid:
            return r["key"] if isinstance(r, dict) else r.key
    return None


HALL_AVAILABLE = [0x9FA, 0xA00, 0xA06, 0xA0C, 0xA12, 0xA18, 0xFAA, 0xFB0]   # PHRASE_<hero>_hall_available_title
FOODS = (1, 2, 3, 4, 5, 6, 7, 8)          # urchin .. oranges (g_city_food_list: the scenario's foods)


def _goods_res(req):
    """The good a type-0 requirement names: v2 when it is a food or a good the city knows, else v3 (Zeus goods vs
    Poseidon ones; hypothesis: g_city_food_list / g_goods_list are the scenario's lists)."""
    t, v1, v2, v3 = req[0], req[1], req[2], req[3]
    if v3 != 0 and v2 in (17, 22, 23):        # orichalc, chariots, silver: Poseidon goods
        return v3
    return v2


def stock(g, rid):
    """FUN_0040F810: the city's stored units of the good, in hundredths of a load (requirements say 3200 = 32). Our
    stores already count hundredths (storage-distribution.md: 100 = one load); bugs.md 385: was * 100 again."""
    from ..systems import economy
    if rid == 0x19:
        return sum(stock(g, f) for f in FOODS)
    k = _res_key(g, rid)
    return economy.city_stock(g, k) if k else 0


def met(g, h, i):
    """hero_requirement_met 0x004FBC20."""
    r = record(g, h)
    b = hall(g, h)
    if b is None:
        return False
    if present(g, h) or r["sent"] or r["paid"]:
        return True
    req = data()["heroes"][h]["requirements"][i]
    t, v1, v2, v3, v4, v5 = req
    c = g.city
    if t == 0:
        return v1 <= stock(g, _goods_res(req))
    if t == 1:
        if v2 == 0x2B:
            return v1 <= horses(g)
        if v2 == 0x39:
            return v1 <= sum(1 for w in g.walkers.values() if w.role == "trireme")
        return False
    if t == 2:
        cnt = companies_by_type(g)
        if h == 2:
            return v1 <= cnt[v2]
        if h == 6:
            return v1 <= cnt[0] + cnt[1] + cnt[2]
        return v1 <= cnt[v4] + cnt[v2]
    if t == 3:
        return sanctuary_req(g, v1, [v2, v3, v4, v5])
    if t == 4:
        return no_unrest(g)
    if t == 5:
        return athletics(g) > 89 if v2 == 0 else hall_culture(g, b) > 89
    if t == 6:
        return games_won(g)
    if t == 7:
        return v1 <= c.population
    if t == 8:
        return c.sentiment > 89
    if t == 9:
        return health(g) > 79
    if t == 10:
        return v1 <= elite_houses(g)
    if t == 11:
        return v1 <= c.treasury
    if t == 12:
        return palace_near(g, b, 5)
    if t == 13:
        return hall_desirability(g, b) > 60
    if t == 14:
        return walled(g, b)
    if t == 17:
        return tax_coverage(g) > 88
    if t == 18:
        return venue_shows(g, v3 if v3 else v2)
    return False


def evaluate(g, h):
    """hero_requirements_eval 0x004FBAD0: +0x0D..+0x11, all met (+0x12) also needs the hall's +0x18."""
    r = record(g, h)
    r["met"] = [1 if met(g, h, i) else 0 for i in range(5)]
    b = hall(g, h)
    r["all_met"] = 1 if all(r["met"]) and b is not None and hall_active(g, b) else 0
    return r["all_met"]


def hall_active(g, b):
    """The hall's +0x18: 100 when its road-access tile is a road (cycle_buildings_pass_12 0x00484FE0)."""
    return bool(getattr(b, "access", None))


def horses(g):
    """FUN_0040F780(0): horses in the city's ranches."""
    from ..systems import ranch
    return sum(len(ranch.horses(g, b)) for b in g.buildings.values() if b.key == "horse_ranch")


def venue_shows(g, t):
    """Type 18: buildings_count_by_type[t] != 0 (Zeus: v3 = 80 stadium; Poseidon: v2 = 207 museum) and
    g_unique_venue_shows (0x00FEAED2) > 0: the unique venue is giving shows."""
    from ..systems import services
    ven = [b for b in g.buildings.values() if g.cat.spec(b.key).get("zeus_id") == t]
    return bool(ven) and any(services.shows(b) > 0 for b in g.buildings.values()
                             if g.cat.spec(b.key).get("unique_venue"))


def companies_by_type(g):
    """g_companies_by_type 0x00FEB538: companies per type (0 rabble? 1 hoplite, 2 horseman; hypothesis)."""
    from ..systems import military
    cnt = [0] * 16
    try:
        comps = military.companies(g) if hasattr(military, "companies") else {}
    except Exception:
        comps = {}
    kinds = {"rabble": 0, "hoplite": 1, "horseman": 2}
    for c in comps.values():
        k = kinds.get(c.get("type"))
        if k is not None and c.get("members", 0) > 0:
            cnt[k] += 1
    return cnt


def sanctuary_req(g, n, gods):
    """Type 3: n (1 or 2) of the listed gods that the scenario lists as friendly-jealous have a finished
    sanctuary (monument_progress 100)."""
    from . import gods_block
    from ..systems import monuments
    from ..systems.commemorative import GODS
    gb = gods_block(g)
    ok = []
    for god in gods:
        if god < 0:
            continue
        if gb is not None:
            slot = gb["slots"].index(god) if god in gb["slots"] else -1
            if slot < 0 or not gb["jealous"][slot]:
                continue
        ok.append(god)
    picks = ok[:n]
    if len(picks) < n:
        return False
    for god in picks:
        key = "sanctuary_" + GODS[god].lower().replace("hephaestus", "hephaistos")
        if not any(b.key == key and monuments.complete(b) for b in g.buildings.values()):
            return False
    return True


def sanctuary_gods(g, gods):
    """The listed gods the scenario has as friendly and jealous (scenario_slot_jealous_flag 0x005871A0), in order."""
    from . import gods_block
    gb = gods_block(g)
    out = []
    for god in gods:
        if god < 0:
            continue
        if gb is not None:
            slot = gb["slots"].index(god) if god in gb["slots"] else -1
            if slot < 0 or not gb["jealous"][slot]:
                continue
        out.append(god)
    return out


def sanctuary_progress(g, god):
    """monument_progress of the god's sanctuary (0 without one)."""
    from ..systems import monuments
    from ..systems.commemorative import GODS
    key = "sanctuary_" + GODS[god].lower().replace("hephaestus", "hephaistos")
    return max((monuments.progress(b) for b in g.buildings.values() if b.key == key and "pieces" in b.misc), default=0)


def crime_level(g):
    """city_crime_level 0x00519910 (0x00FEB544): 0x8F no house with unrest >= 51 (or no houses); 0x8A more than half
    at 71..80; else by the share at >= 81: < 11 % 0x8E, 11..25 % 0x8C, more 0x8B."""
    hs = [b for b in g.buildings.values() if b.kind == "house" and b.occupants]
    if not hs or not any(b.crime >= 51 for b in hs):
        return 0x8F
    n = len(hs)
    if sum(1 for b in hs if 71 <= b.crime <= 80) * 2 > n:
        return 0x8A
    hi = sum(1 for b in hs if b.crime >= 81) * 100 // n
    return 0x8E if hi < 11 else 0x8C if hi <= 25 else 0x8B


def no_unrest(g):
    """Type 4: crime level 0x8E or 0x8F."""
    return crime_level(g) in (0x8E, 0x8F)


def athletics(g):
    """0x0091EA78: the city's athletics (gymnasium) coverage % (games.coverage, FUN_00566A90)."""
    from ..systems import games
    return games.coverage(g)[1]


def tax_coverage(g):
    """g_tax_coverage_pct 0x00FE9690: % of houses registered by a clerk (ours: by house count)."""
    hs = [b for b in g.buildings.values() if b.kind == "house" and b.occupants]
    return sum(1 for b in hs if b.tax_days > 0) * 100 // len(hs) if hs else 0


def hall_culture(g, b):
    """Hall +0x80: houses_culture_compute 0x00484DE0 counts type 0x7D like a house (competitor 20, philosopher 15,
    athlete 20, actor 25, + the unique venue's 10); the hall keeps service coverage like a house (services.apply)."""
    from ..systems import housing
    return housing.culture(g, b)


def games_won(g):
    """Type 6: 0x00FEB418, set when the city won a pan-Hellenic game (sim/systems/games.py won_ever)."""
    from ..systems import games
    return bool(games.state(g).get("won_ever"))


def games_chance(g, c):
    """FUN_00565E30 (games_chance_hercules, from FUN_00565E90 on the year's chance FUN_00565D40): Hercules' hall
    built (hero_record_hall 0x004FA5D0), he is not sent for (+0x18) and his 'win a pan-Hellenic game' requirement
    (type 6) is not met (FUN_004FBA70: hero_requirements_eval, then the met byte of the first requirement of that
    type; 0 when he has none) and c != 0: c = ftol(c * c * 0.16) (constant 0x005E4800): 25 -> 100, 10 -> 16, 5 -> 4."""
    if not c or hall(g, 1) is None or record(g, 1)["sent"]:
        return c
    reqs = data()["heroes"][1]["requirements"]
    i = next((k for k, q in enumerate(reqs) if q[0] == 6), None)
    if i is not None and met(g, 1, i):
        return c
    return int(c * c * 0.16)


def health(g):
    return getattr(g, "health_state", {}).get("health", 80)


def elite_houses(g):
    """0x00782888[11..14]: occupied elite houses (residence .. estate; buildings_count_by_type 0x00491820)."""
    from ..systems import housing
    return sum(1 for b in g.buildings.values() if b.kind == "house" and b.occupants and housing.is_elite(b))


def palace_near(g, b, d):
    """FUN_004FBB20(hall, 0x75, 5): a palace within 5 tiles of the hall."""
    for p in g.buildings.values():
        if p.key != "palace":
            continue
        pw, ph = p.misc.get("w", p.size) or 6, p.misc.get("h", p.size) or 9
        dx = max(p.x - (b.x + b.size - 1), b.x - (p.x + pw - 1), 0)
        dy = max(p.y - (b.y + b.size - 1), b.y - (p.y + ph - 1), 0)
        if max(dx, dy) <= d:
            return True
    return False


def hall_desirability(g, b):
    return int(g.world.des[b.y, b.x])


def walled(g, b):
    """Type 14: no route from the map entry, the land exit or any invasion point to the hall (FUN_0058DF40)."""
    from ..military import invaders
    ok = walkers.walkable(g)
    starts = [tuple(g.world.entry), tuple(g.world.exit)]
    goal = set(walkers.edge_tiles(g, b, ok) or [])
    if not goal:
        return True
    for s in starts:
        if walkers.land_path(g, s, goal, max_dist=600, ok=ok) is not None:
            return False
    return True


# --- month, send for, arrival -----------------------------------------------------------------------------

def month(g):
    """heroes_month_check 0x00524860 (month_tick 6): needed heroes not yet sent for re-evaluate; all met and not
    announced -> 'You may now call for X' (0xEA + hero, 0xF2), +0x1A = 1."""
    from . import events
    events.month(g)
    for h in range(8):
        r = record(g, h)
        if r["needed"] and not r["sent"]:
            if evaluate(g, h):
                if not r["announced"]:
                    r["announced"] = 1
                    g.message(f"{text19(234 + h)}. {text19(242)}.")          # ticker 0x005231E0
            else:
                r["announced"] = 0


def text19(i):
    """Ticker texts 19:234..242 (data/heroes.json "ticker")."""
    return data()["ticker"][i - 234]


def send_for(g, h):
    """hero_send_for 0x004FC2B0 (the hall's Send For button): queue the arrival (1..3 months), pay the
    requirements once."""
    from . import events
    r = record(g, h)
    if hall(g, h) is None:
        raise ValueError(f"no {data()['heroes'][h]['hall']}")
    if r["sent"] or present(g, h):
        raise ValueError(f"{name(h)} is already on the way or here")
    cheat = state(g).get("cheat")              # 0x00665DF0: Send For without the requirements, nothing paid
    if not evaluate(g, h) and not cheat:
        raise ValueError(f"{name(h)}: the city is not yet worthy (requirements not met)")
    events.queue_arrival(g, h)
    r["sent"] = 1
    if not r["paid"] and not cheat:
        r["paid"] = 1
        pay(g, h)
    return f"{name(h)} sent for: travelling to the city"


def pay(g, h):
    from ..systems import economy
    for req in data()["heroes"][h]["requirements"]:
        t, v1 = req[0], req[1]
        if t == 0:
            rid = _goods_res(req)
            if rid == 0x19:
                left = v1
                for f in FOODS:
                    if not left:
                        break
                    have = stock(g, f)
                    n = min(left, have)
                    _remove(g, f, n)
                    left -= n
            else:
                _remove(g, rid, v1)
        elif t == 1 and req[2] == 0x2B and req[3] == 1:
            take_horses(g, v1)
        elif t == 11 and req[2] == 1:
            g.city.treasury -= v1


def take_horses(g, n):
    """hero_send_for: v1 horses leave the horse ranches (type 0x85) in building order, each ranch's figure slots
    in order (state 2, slot cleared, count byte +0xA8 - 1)."""
    from ..systems import ranch
    for b in sorted((b for b in g.buildings.values() if b.key == "horse_ranch"), key=lambda b: b.id):
        for h in ranch.horses(g, b):
            if n <= 0:
                return
            walkers.remove(g, h)
            n -= 1


def _remove(g, rid, hundredths):
    """city_goods_remove(res, n, 3): from storage."""
    from ..systems import economy
    k = _res_key(g, rid)
    left = (hundredths + 99) // 100
    for s in economy._stores(g):
        if not left:
            break
        n = min(left, s.goods.get(k, 0))
        if n:
            s.goods[k] -= n
            if not s.goods[k]:
                del s.goods[k]
            left -= n


def create(g, h):
    """hero_create 0x004FA4F0: the hero at the map entry, action 6 (walk to his hall), linked to the hall."""
    from ..military import units
    b = hall(g, h)
    x, y = g.world.entry                         # raw (oracle 1I-hero: logical (166, 169) = raw (167, 170))
    w = units.spawn(g, HERO, x, y, home=b.id if b else 0, hero=h, act=6, timer=0, target=0, duel=0, good=f"h{h}")
    record(g, h)["fig"] = w.id
    if b is not None:
        b.misc["hero_fig"] = w.id
    from .. import alerts                         # alert 13 "go to hero" at the spawn tile
    alerts.raise_alert(g, alerts.HERO, (x, y))
    return w


# --- the hero figure (figure_hero_update 0x004C8F50) ----------------------------------------------------------

def act(g, w):
    from . import hero_ai
    return hero_ai.act(g, w)


def look(g, w):
    from . import hero_ai
    return hero_ai.look(g, w)


def died(g, w, by):
    h = getattr(w, "hero", -1)
    if 0 <= h < 8:
        r = record(g, h)
        r["fig"] = 0


def fight_over(g, w):
    from . import hero_ai
    return hero_ai.fight_over(g, w)


def dispatch(g, h):
    from . import hero_ai
    return hero_ai.dispatch(g, h)


def quest_home(g, ev):
    from . import hero_ai
    return hero_ai.quest_home(g, ev)


# --- reports -----------------------------------------------------------------------------------------------

REQ_TEXT = {0: "in storage", 1: "", 2: "companies", 3: "A Sanctuary to", 4: "No unrest in the city",
            5: "excellent culture access", 6: "win any pan-Hellenic game", 7: "people in the city",
            8: "Great Popularity", 9: "excellent city wide health", 10: "elite houses", 11: "in treasury",
            12: "Build the hall near the palace", 13: "Good appeal around the hall", 14: "Hall is protected by Walls",
            17: "Excellent city wide observatory access", 18: "A working Stadium"}


def req_line(g, h, i):
    """The left text of a hall window row (FUN_004FAA70)."""
    D = data()
    req = D["heroes"][h]["requirements"][i]
    t, v1 = req[0], req[1]
    if t == 0:
        rid = _goods_res(req)
        return f"{v1 // (400 if rid == 0x13 else 100)} {D['goods'][rid]}"
    if t == 1:
        return f"{v1} {D['goods'][15]}" if req[2] == 0x2B else f"{v1} {D['units'][7 if v1 != 1 else 6]}"
    if t == 2:                                   # "%d %s %s %s": v1, 64:v3 (unit), 8:0x31, 185:0x73 (Jason: no 0x73)
        if h == 6:
            return f"{v1} {D['units'][5 if v1 != 1 else 4]}"
        if h == 2:
            return f"{v1} {D['figure_names'][req[3]]} {D['units'][5]}"
        return f"{v1} {D['figure_names'][req[3]]} {D['units'][5]} {T(0x73)}"
    if t == 3:                                   # one god: the first listed one the scenario has as friendly-jealous
        gods = sanctuary_gods(g, req[2:])
        if v1 == 1 and gods:
            return f"{T(47)} {D['gods'][gods[0]]}"
        gods = [D["gods"][x] for x in req[2:] if 0 <= x < 14]
        return f"{T(47)} {' / '.join(gods)}"
    if t == 5:
        return T(51) if req[2] == 0 else T(49)
    if t in (7, 10):
        return f"{v1} {T(52 if t == 7 else 35)}"
    if t == 11:
        return f"{T(125)}{v1} {D['goods'][23]}"
    if t == 18:
        return T(126)
    return T({4: 48, 6: 50, 8: 54, 9: 55, 12: 56, 13: 57, 14: 58, 17: 124}.get(t, 59))


def describe(g, h):
    r = record(g, h)
    b = hall(g, h)
    s = f"{name(h)}: hall {'(%d,%d)' % (b.x, b.y) if b else 'none'}, needed {bool(r['needed'])}, " \
        f"{'in the city' if present(g, h) else 'travelling' if r['sent'] else 'all met' if r['all_met'] else 'not yet worthy'}"
    lines = [s]
    for i in range(5):
        lines.append(f"  [{'x' if r['met'][i] else ' '}] {req_line(g, h, i)}")
    return "\n".join(lines)


def T(i):
    return data()["texts"][str(i)]


def bucket(v):
    """The window's 5-step ladders (FUN_0057C720): v < 1 -> 0, < 26 -> 1, < 61 -> 2, <= 89 -> 3, else 4."""
    return 0 if v < 1 else 1 if v < 26 else 2 if v < 61 else 3 if v <= 89 else 4


def req_status(g, h, i):
    """The right column of a requirement row (current value + text 185:16..46)."""
    req = data()["heroes"][h]["requirements"][i]
    t, v1 = req[0], req[1]
    b = hall(g, h)
    if t == 0:
        rid = _goods_res(req)
        return f"{stock(g, rid) // 100} {T(33) if rid == 0x19 else T(16)}"
    if t == 1:
        return f"{horses(g)} {T(34)}" if req[2] == 0x2B else \
            f"{sum(1 for w in g.walkers.values() if w.role == 'trireme')} {T(32)}"
    if t == 2:                                   # companies of the row's types, 8:0x30 / 0x31
        cnt = companies_by_type(g)
        n = cnt[req[2]] if h == 2 else sum(cnt[:3]) if h == 6 else cnt[req[2]] + cnt[req[4]]
        return f"{n} {data()['units'][4 if n == 1 else 5]}"
    if t == 3:
        gods = sanctuary_gods(g, req[2:])
        if v1 == 1 and gods:
            return f"{sanctuary_progress(g, gods[0])}% {T(18)}"
        return T(18) if sanctuary_req(g, v1, req[2:]) else f"0% {T(18)}"
    if t == 4:                                   # 61:(city_crime_level + 6) (0x005B6690): 0x8F -> "none"
        r = data().get("ratings")
        k = crime_level(g) + 6 - 140
        return r[k] if r and 0 <= k < len(r) else ""
    if t == 5:
        return T(26 + bucket(athletics(g))) if req[2] == 0 else T(19 + bucket(hall_culture(g, b) if b else 0))
    if t == 6:
        return T(25 if games_won(g) else 24)
    if t == 7:
        return f"{g.city.population} {T(31)}"
    if t == 10:
        return f"{elite_houses(g)} {T(35)}"
    if t == 11:
        return f"{g.city.treasury} {T(36)}"
    if t == 12:
        has = any(p.key == "palace" for p in g.buildings.values())
        return T(37) if not has else T(39) if b is not None and palace_near(g, b, 5) else T(38)
    if t == 13:
        return T(40 + bucket(hall_desirability(g, b) if b else 0))
    if t == 14:
        return T(46) if b is not None and walled(g, b) else T(45)
    return ""


def status_text(g, h):
    """0x0057C630: 63 not worthy / 64 may now call / 65 travelling / 66 away on a quest / 67 doing battle /
    68 in the city / 69 resting (actions 6, 7)."""
    r = record(g, h)
    w = figure(g, h)
    if w is None:
        return 65 if r["sent"] else 64 if r["all_met"] else 63
    if getattr(w, "quest", None) is not None:
        return 66
    if w.act == 5:
        return 67
    if w.act in (6, 7):
        return 69
    return 68


def export(g, h):
    if hall(g, h) is not None:
        evaluate(g, h)                             # building_info_panel_prepare re-runs it
    r = record(g, h)
    b = hall(g, h)
    w = figure(g, h)
    return dict(id=h, name=name(h), hall=b.id if b else 0, needed=r["needed"], met=r["met"], all_met=r["all_met"],
                sent=r["sent"], present=w is not None, fig=w.id if w else 0,
                away=w is not None and getattr(w, "quest", None) is not None,     # +0x132 >= 0 (army dialog: Abroad)
                reqs=[req_line(g, h, i) for i in range(5)], values=[req_status(g, h, i) for i in range(5)],
                status=T(status_text(g, h)).replace("[hero_name]", name(h)),     # trailing space kept: it centres
                road=bool(b is not None and hall_active(g, b)),
                can_send=w is None and not r["sent"] and bool(r["all_met"] or state(g).get("cheat")),
                needed_text=T(r["text"]).replace("[hero_name]", name(h)) if 0 < r["text"] < 134 else "",
                hall_title=T(8 + h), texts=dict(requires=T(59), status=T(60), send_for=T(62),
                                                no_road=data().get("no_road", "")))


def hall_info(g, b):
    h = b.misc.get("hero", 0)
    evaluate(g, h)
    return export(g, h)
