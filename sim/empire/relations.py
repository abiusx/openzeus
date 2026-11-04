"""Attitude, streaks, army regrowth and city status changes (empire.md, world-map.md 6.1-6.2, 6.6)."""
import math

from . import model

# attitude table 0x005EC528: (lo, hi, mode, change per difficulty VeryEasy..Impossible)
ATT_TABLE = [(91, 100, 0, (6, 4, 2, 1, 1)), (81, 90, 0, (3, 2, 1, 1, 0)), (71, 80, 0, (2, 1, 0, 0, 0)),
             (61, 70, 0, (0, 0, 0, 0, 0)), (41, 60, 2, (0, 0, 0, 0, 0)), (31, 40, 1, (0, 0, 0, 0, 0)),
             (21, 30, 1, (0, 0, 0, 1, 2)), (11, 20, 1, (0, 1, 1, 2, 3)), (0, 10, 1, (1, 1, 2, 4, 5))]
ARMY_K = (3.0, 4.0, 4.5, 5.0, 6.0)                 # 0x005EC670
# relationship letters (type 0x1F, 0x004742A0) when a streak crosses 40
LETTER_DISPLEASED = {"ally": "is resentful of you", "vassal": "is angry with you", "rival": "is hostile toward you",
                     "parent": "is resentful of you", "colony": "is angry with you"}
LETTER_PLEASED = {"ally": "loves you", "vassal": "loves you", "rival": "respects you", "parent": "loves you",
                  "colony": "loves you"}


def diff(g):
    from ..systems.labor import DIFFICULTIES
    d = g.rules.get("difficulty", "Normal")
    return DIFFICULTIES.index(d) if d in DIFFICULTIES else 2


# a history record's relation byte (+7) by city_class of a city other than the record's subject: group 91
REL = {"ally": 1, "rival": 2, "vassal": 3, "colony": 4, "parent": 5}


def goods_flags_rebuild(e):
    """FUN_00461360: every city's buys[] (+0x18) and sells[] (+0x3C) flags rebuilt from its buy and sell lists
    (city_in_buy_list / city_in_sell_list; the player city's sells from its resources, no buys), with no trading-
    partner gate, so flags zeroed by a status change (6.8) come back. Called by every saved-game load
    (game_file_load 0x0050E610 -> FUN_00510ED0), every episode start (episode_start_load 0x00420390: new city via
    FUN_0051D5F0 -> FUN_004612E0, colony at 0x004210E6, continue through game_file_load) and episode_end_save_parent
    0x0052D2B0 (world-map.md 6.8). Ours: City.goods_flags True."""
    if e is None:
        return
    for c in e.cities.values():
        c.goods_flags = True


def note(g, c, phrase, delta=0, rel=0, item=None):
    """A history record (FUN_0042EEC0 into the list at 0x007796D0, 2000 records, sav ranks 133/134): FUN_0042EE10
    dates it; +5 the city whose history it is (c), +6 the attitude change (the row's thumbs), +7 the relation byte
    ([city_affected]: 0 this city, else REL of the subject's class), +8 the phrase id, +10 the item ([itemshort]).
    Stored as (month index, text, change): the text is the exe's row text (messages.history)."""
    from .. import messages
    c.history.append((g.month_index, messages.history(phrase, rel, item), max(-128, min(127, int(delta)))))
    del c.history[:-60]


def attitude_add(g, c, d, phrase=None, rel=0, item=None, always=False):
    """city_attitude_add 0x0042CED0: clamp 0..100. With a phrase, the writers' history record (the computed change,
    not the clamped one), written when the change is not 0 (or always: city_receive_gift's own record)."""
    c.attitude = max(0, min(100, c.attitude + d))
    if phrase is not None and (d or always):
        note(g, c, phrase, d, rel, item)


def army_target(g, c):
    """city_army_target 0x0042D980: ftol(sqrt(min(years, 30)) * k[difficulty] * military_strength)."""
    e = g.empire
    return int(math.sqrt(min(e.months / 12.0, 30.0)) * ARMY_K[diff(g)] * c.strength)


def drift(g):
    """city_attitude_drift 0x0042D850, January and July: one step toward 50."""
    for c in g.empire.cities.values():
        if c.attitude > 50:
            c.attitude -= 1
        elif c.attitude < 50:
            c.attitude += 1


def monthly(g):
    """city_monthly_update 0x0042D540 (day 2): fatigue decay, returning troops, army regrowth."""
    for c in g.empire.cities.values():
        if c.exists():
            for f in (c.request_fatigue, c.gift_fatigue):
                for k in list(f):
                    f[k] = max(0, f[k] - 1)
            if c.troops_return[0]:
                c.troops_return[0] -= 1
                if not c.troops_return[0]:
                    c.away[1] -= c.troops_return[1]
                    c.army += c.troops_return[1]
                    c.troops_return[1] = 0
        if c.army < army_target(g, c) - sum(c.away):
            c.army += 1


def update(g):
    """city_attitude_update 0x0042D5E0 (days 0, 4, 8, 12): streaks from the attitude table; a streak
    crossing 40 sends a relationship letter (type 0x1F, message only)."""
    d = diff(g)
    for c in g.empire.cities.values():
        if c.kind == "distant":
            c.relation = "ally"
        if not c.exists():
            continue
        c.wealth = max(1, min(5, c.wealth))
        c.strength = max(1, min(6, c.strength))
        row = next((r for r in ATT_TABLE if r[0] <= c.attitude <= r[1]), None)
        if row is None:
            continue
        old_p, old_d = c.pleased, c.displeased
        if row[2] == 0:
            c.pleased, c.displeased = min(c.pleased + row[3][d], 50), 0
        elif row[2] == 1:
            c.pleased, c.displeased = 0, min(c.displeased + row[3][d], 50)
        else:
            c.pleased = c.displeased = 0
        k = c.cls()
        if old_d <= 40 < c.displeased and k in LETTER_DISPLEASED:
            g.message(f"{c.name} {LETTER_DISPLEASED[k]}.")
        elif old_p <= 40 < c.pleased and not c.rebellion and k in LETTER_PLEASED:
            g.message(f"{c.name} {LETTER_PLEASED[k]}.")


def attitude_code(c):
    """city_attitude_code 0x0042D8A0 -> text group 65 index."""
    k = c.cls()
    if c.pleased > 20:
        return 17 if k == "rival" else 15
    if c.displeased > 20:
        return {"ally": 16, "parent": 16, "vassal": 19, "colony": 19}.get(k, 18)
    a = c.attitude
    lvl = 0 if a > 80 else 1 if a > 60 else 2 if a >= 40 else 3 if a > 20 else 4
    return lvl + (0 if k == "ally" else 5 if k == "rival" else 10)


ATTITUDE_WORDS = ["Helpful", "Congenial", "Sympathetic", "Apathetic", "Annoyed", "Admiring", "Respectful", "Apathetic",
                  "Displeased", "Furious", "Devoted", "Dedicated", "Loyal", "Bitter", "Angry", "Philanthropic",
                  "Resentful", "Docile", "Hostile", "Insubordinate"]       # text group 65


def status_change(g, c, sub, amount=0):
    """events_cities_month 0x00473680 (type 0x13): the subtypes that change a city (empire.md)."""
    if c.kind == "destroyed" or (c.kind == "colony" and not c.active):
        return False
    rel = c.relation
    before = (c.trade_open, c.rebellion, c.tribute["mode"], c.relation, c.strength, c.wealth, c.active, c.visible)
    if sub == 0 or sub == 2:
        c.trade_open = False
    elif sub in (1, 3):
        c.trade_open = True
    elif sub == 4 and rel in ("vassal", "colony"):
        c.tribute["mode"] = 0
    elif sub == 5 and rel in ("vassal", "colony"):
        c.tribute["mode"] = 1
    elif sub == 6 and rel in ("vassal", "colony"):
        c.trade_open, c.rebellion, c.tribute["mode"] = False, True, 0
    elif sub == 7 and rel in ("vassal", "colony"):
        c.trade_open, c.tribute["mode"] = True, 1
    elif sub == 0x17 and rel in ("vassal", "colony"):
        c.trade_open, c.rebellion, c.tribute["mode"] = True, False, 1
    elif sub == 9 and rel == "rival":
        c.relation, c.trade_open, c.rebellion = "ally", True, False
    elif sub in (10, 12) and rel in ("ally", "vassal"):
        c.relation, c.trade_open, c.rebellion, c.tribute["mode"] = "rival", False, False, 0
    elif sub == 11 and rel in ("ally", "rival"):
        c.relation, c.trade_open, c.rebellion, c.tribute["mode"] = "vassal", True, False, 1
    elif sub == 14:
        c.strength = min(c.strength + amount, 5)
    elif sub == 15:
        c.strength = max(1, c.strength - amount) if c.strength - amount >= 2 else 1
    elif sub == 16:
        c.wealth = min(c.wealth + amount, 5)
    elif sub == 17:
        c.wealth = max(1, c.wealth - amount) if c.wealth - amount >= 2 else 1
    elif sub in (18, 19):
        c.active = sub == 18
    elif sub in (20, 21):
        c.visible = sub == 20
    after = (c.trade_open, c.rebellion, c.tribute["mode"], c.relation, c.strength, c.wealth, c.active, c.visible)
    if before != after:                            # 0x00473680: the buys/sells flags (+0x18/+0x3C) are rebuilt for
        c.goods_flags = c.trading()                # trading partners and zeroed for the others (world-map.md 6.8)
        if sub in STATUS_HISTORY:                  # event_city_status_change: its history record (change 0)
            note(g, c, STATUS_HISTORY[sub])
    if before != after and sub == 9:               # a rival became an ally: 0x00402B00(8), a Diplomacy Monument
        from ..systems import commemorative
        from .. import messages
        commemorative.grant(g, 8)
        messages.post(g, 0x39E, 0x39F, city=c)    # message 0xE0 "[city_name] becomes ally" (names the monument)
    return before != after


# event_city_status_change 0x00473680: the history phrase by subtype (written after a change; none for 22)
STATUS_HISTORY = {0: 0xBD9, 1: 0xBD7, 2: 0xBD8, 3: 0xBD6, 4: 0xBDE, 5: 0xBDD, 6: 0xBDA, 7: 0xBDC, 8: 0xBDA, 9: 0xBE5,
                  10: 0xBE6, 11: 0xBE7, 12: 0xBE6, 14: 0xBD4, 15: 0xBD5, 16: 0xBD3, 17: 0xBD2, 18: 0xC97, 19: 0xC98,
                  20: 0xC99, 21: 0xC9A, 0x17: 0xBDB}
STATUS_TEXT = {0: "has suspended trade with you", 1: "has resumed trade with you", 2: "has shut down trade",
               3: "has opened trade", 4: "has suspended its tribute", 5: "has resumed its tribute",
               6: "is in rebellion!", 7: "is no longer rebelling", 0x17: "has ended its rebellion",
               9: "is now your ally", 10: "is now your rival", 11: "is now your vassal", 12: "is now your rival",
               14: "builds up its army", 15: "has a weaker army", 16: "prospers", 17: "declines",
               18: "becomes active", 19: "becomes inactive", 20: "appears", 21: "disappears"}       # group 35


def player_strength(g):
    """player_military_strength 0x00568540 from the companies at home: P1 = rabble/2 + 2*horsemen +
    hoplites (+ 3 per trireme: our sim has no trireme figures yet). Returns (P1, P3 = P1 - rabble/2)."""
    from ..systems import military
    n = {t: 0 for t in military.TYPES}
    for comp in military.companies(g).values():
        if not comp.get("away") and not comp.get("event"):
            n[comp["type"]] += comp["members"]
    p1 = n["rabble"] // 2 + 2 * n["horseman"] + n["hoplite"]
    return p1, p1 - n["rabble"] // 2
