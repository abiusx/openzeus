"""Commemorative monuments (type 119 = 0x77; docs/logic/monuments.md "Commemorative monuments").

The original never builds these over time: the city is *granted* a monument of a variant by an event, the player
places it from the Aesthetics > Monuments menu (submenu 22), and it appears at once (cost 0, no artisans, no staff).
Its only effect is desirability (model row 119: +30, step 2, step size -5, range 6).

- Grant `FUN_00402B00(v)`: `g_commemorative_available[v]` (0x00665CC8) += 1 while it is <= 9 (at most 10 waiting).
- Place (FUN_00496CA0 case 0x77): the variant goes to `+0x12`; placed[v] (0x00665C7C) += 1, available[v] -= 1.
- Remove (building_on_remove 0x00494690): placed[v] -= 1; the grant is not given back.
Grants reachable in an open-play sandbox:
- 1 Population Monument: population >= 1000, 2000, 5000, 10000, 15000, 20000, 25000, once each
  (city_population_update 0x00486190, flags 0x00FD37C6..CD);
- 6 Happiness Monument: at the start of each month `g_high_sentiment_months` (0x00FE9414) += 1 while sentiment
  >= 81, else 0; at 60 the monument is granted and the count restarts (city_sentiment_update 0x005671A0).
The others (2 victory, 3 colony, 4/9 games, 5 conquest, 7 hero, 8 diplomacy, 10..65 god statues from hero quests) come
from military / world-map / hero events: `grant(g, v)` is their hook.
The grant posts no message (as FUN_00402B00): each event posts its own, which says a Commemorative Monument can now
be built (sim/messages.py, the exe's phrase ids).
"""
from .. import messages

NAMES = ["None", "Population Monument", "Victory Monument", "Colony Monument", "Athlete Monument",
         "Conquest Monument", "Happiness Monument", "Heroic Figure Monument", "Diplomacy Monument", "Scholar Monument"]
GODS = ["Zeus", "Poseidon", "Demeter", "Apollo", "Artemis", "Ares", "Aphrodite", "Hermes", "Athena", "Hephaestus",
        "Dionysus", "Hades", "Hera", "Atlas"]
VARIANTS = 66                       # 1..65 used (0x00665CC8 is u8[75])
POP_STEPS = (1000, 2000, 5000, 10000, 15000, 20000, 25000)
POP_MESSAGES = (100, 500, 1000, 2000, 3000, 5000, 10000, 15000, 20000, 25000)   # flags 0x00FD37C4..CD
POP_TITLE, POP_STRIDE = 0x4DA, 6    # message 0xE0: title 0x4DA + 6 k, announcement + 1 (k = index in POP_MESSAGES)
HAPPY_TITLE = 0x516                 # message 0xE0: 0x516 title, 0x517 announcement
HAPPY_SENTIMENT, HAPPY_MONTHS = 81, 60
KEY = "commemorative_monument"


def state(g):
    s = g.sd("commemorative", None)
    if s is None:
        s = g.commemorative = dict(available=[0] * VARIANTS, pop_done=[], happy_months=0, v=2)
    return s


def god(v):
    """Variant 10..65 -> god 0..13 (FUN_0051B9D0): 10..21 / 38..49 small, 22..33 / 50..61 large Zeus..Hades,
    34/35 + 62/63 small and 36/37 + 64/65 large Hera/Atlas (the two sets: a god's first / second quest)."""
    if v < 10:
        return None
    return (v - 10) % 12 if v < 34 else 12 + v % 2 if v < 38 else (v - 38) % 12 if v < 62 else 12 + v % 2


def name(v):
    """Text group 198 (198:v)."""
    if 0 < v < len(NAMES):
        return NAMES[v]
    if 10 <= v < VARIANTS:
        return f"{'Large' if size(v) == 4 else 'Small'} {GODS[god(v)]} Statue"
    return f"Monument {v}"


def size(v):
    """1..9: 3x3; god statues: small 3x3, large (22..33, 36, 37, 50..61, 64, 65) 4x4 (building_create 0x00493E70)."""
    return 4 if (22 <= v <= 33 or v in (36, 37, 64, 65) or 50 <= v <= 61) else 3


# Monuments submenu order (0x005F41A0 = 0x005F27D8[22 * 75 ..]): small statues of a set before its large ones
MENU_ORDER = (list(range(1, 22)) + [34, 35] + list(range(22, 34)) + [36, 37] + list(range(38, 50)) + [62, 63]
              + list(range(50, 62)) + [64, 65])


def menu(g):
    """The Monuments submenu: [variant, waiting, name] for every variant with g_commemorative_available[v] != 0
    (build_menu_draw 0x0058F650), in menu order."""
    av = state(g)["available"]
    return [[v, av[v], name(v)] for v in MENU_ORDER if av[v] > 0]


def placed(g):
    """placed[v], recounted from the buildings (FUN_0050E9F0 recounts the same table)."""
    out = [0] * VARIANTS
    for b in g.buildings.values():
        if b.key == KEY:
            out[b.misc.get("variant", 1)] += 1
    return out


def grant(g, v):
    """FUN_00402B00: one more waiting (at most 10); no message (the caller's event posts its own)."""
    s = state(g)
    if s["available"][v] > 9:
        return False
    s["available"][v] += 1
    return True


def take(g, extra):
    """The variant and orientation a placement uses: `build commemorative_monument X Y [V|auto] [O]` (default: the
    first variant available, orientation 0; O 0..3 = the R key's DAT_00DA23C4 -> Building+0xAC, the god statues'
    facing). Raises ValueError when none of that variant is waiting (the menu lists only available ones)."""
    av = state(g)["available"]
    toks = str(extra).split() if extra not in (None, "") else []
    v_tok = toks[0] if toks else "auto"
    orient = 0
    if len(toks) > 1:
        if not toks[1].isdigit() or int(toks[1]) > 3:
            raise ValueError("commemorative monument orientation is 0..3")
        orient = int(toks[1])
    if v_tok == "auto":
        v = next((i for i in range(1, VARIANTS) if av[i] > 0), 0)
        if not v:
            raise ValueError("no commemorative monument granted yet (the Monuments menu is empty): "
                             "population milestones and 60 happy months grant them")
        return v, orient
    if not v_tok.isdigit() or not 1 <= int(v_tok) < VARIANTS:
        raise ValueError("commemorative monument variant is 1..65")
    v = int(v_tok)
    if av[v] <= 0:
        raise ValueError(f"no {name(v)} is waiting to be placed")
    return v, orient


def placed_one(g, v):
    state(g)["available"][v] -= 1


def day(g):
    """Population milestones (city_population_update)."""
    s = state(g)
    p = g.city.population
    for k, n in enumerate(POP_MESSAGES):            # 100, 500 and 3000: the message only
        if p >= n and n not in s["pop_done"]:
            s["pop_done"].append(n)
            if n in POP_STEPS:
                grant(g, 1)
            t = POP_TITLE + POP_STRIDE * k
            messages.post(g, t, t + 1)


def month(g):
    """Happiness monument (city_sentiment_update, at day_of_month 0)."""
    s = state(g)
    s["happy_months"] = s["happy_months"] + 1 if g.city.sentiment >= HAPPY_SENTIMENT else 0
    if s["happy_months"] >= HAPPY_MONTHS:
        s["happy_months"] = 0
        grant(g, 6)
        messages.post(g, HAPPY_TITLE, HAPPY_TITLE + 1)


def adopt(g):
    """Old saves: monuments placed when they were freely buildable become variant 1 (a Population Monument); the
    milestones the city has already passed are granted at the next day, as the original would have."""
    for b in g.buildings.values():
        if b.key == KEY:
            b.misc.setdefault("variant", 1)
    s = g.sd("commemorative", None)
    if s is not None and s.get("v", 1) < 2:        # saves before the message-only milestones: no late messages
        s["pop_done"] += [n for n in POP_MESSAGES if n not in POP_STEPS and n <= g.city.population]
        s["v"] = 2
