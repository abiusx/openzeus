"""The objectives screens' goal lines as the exe writes them (track 1L-4; docs/play/campaign.md).

objectives_screen_draw 0x0052C070 (screens 0x3B goals, 0x42 victory, 0x43 adventure complete) and the briefing
0x0052E520 (screen 0x35) fill each goal row with two texts of group 194 through the goal variables (FUN_00525E90:
token fill FUN_00505690 with the goal globals 0x00FE42A4..0x00FE42D4 set):
  goal text (FUN_0052A6A0 .. 0052B4E0 by type): 17 Population of [amount], 18 Treasury of [amount], 19..23
  sanctuaries, 24 Support [amount] [military_or_better], 25..29 quest / slay, 30 Produce [amount] [item] in one
  year, 31 Rule [city], 32 Yearly profit, 33 [amount] people in [house_level] or better, 34 trading partners,
  35 / 36 [amount] [item] for parent city / colony (35 when the current episode is a colony start, 0x00902FC4 = 1),
  37 / 38 Survive until / Complete episode before [finish_date], 41 / 42 hippodrome;
  status text (FUN_0052A6C0 .. 0052B500): 43 Population [amount], 44 Treasury [amount], 45..49 sanctuaries,
  50 [amount] supported, 51 / 52 quest, 53 / 54 slay, 55 / 57 Best is [amount], 56 [diplomatic_status],
  58 [amount] qualify, 59 [amount] trading partners, 60 [amount] in stock / 61 Set aside / 62 Done, 63
  [months_remaining] months remain, 69 No Hippodrome.
Tokens (variable table 0x005FBA5C): [amount] "%d"; [item] group 98 by the good id (wm_sub_465DA0); [god] 157;
[house_level] 28 (wm_sub_466490); [finish_date] "%d %s" with 20:0 BC / 20:1 AD (wm_sub_466500); [military_or_better]
138:0x47..0x4A (wm_sub_4665A0: 12 -> 72 "Hoplites or better", 13 -> 71 "Horsemen", 57 -> 73 "Triremes" (69
"Trireme" for one), else 74 "Rabble or better"); [diplomatic_status] 253 by the relationship; [monster] 87;
[god_quest] 52 by god + 14 * quest; [percent] "%d%%".
The tick box (sprite group SPR_CHECKBOX: 607 ticked, 608 empty) is the exe's per-type test of the screen (the
same as goals_status_update 0x0052B7D0: note type 12 is ticked when its year IS reached); the briefing draws every
box empty (0x0052E520: image + 1). A row is a button (window_highlight_draw over the status) for type 14 when the
city has the rest in stock (FUN_00529D10) and for type 4 when its quest can be dispatched (FUN_0052D240).
"""
import json
import os

from .. import measure

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_T = {}
REL = {"ally": 0, "rival": 1, "vassal": 2, "colony": 3}


def text(group, i):
    if not _T:
        _T.update(json.load(open(os.path.join(ROOT, "data", "campaign", "texts.json")))["groups"])
    g = _T.get(str(group), [])
    return g[i] if 0 <= i < len(g) else ""


def _fill(s, **kw):
    for k, v in kw.items():
        s = s.replace(f"[{k}]", str(v))
    return s


def _military(kind, amount):
    if kind == 12:
        return text(138, 72)
    if kind == 13:
        return text(138, 71)
    if kind == 57:
        return text(138, 69 if amount == 1 else 73)
    return text(138, 74)


def finish_date(year):
    return f"{abs(year)} {text(20, 0 if year < 0 else 1)}"


def _event(g, i):
    if g is None:
        return None
    from .. import scenario
    return scenario.get(g, i)


def _outstanding(ev):
    """request_outstanding 0x0047F630 for the goal's event: a god quest (4) when done (state 10) or active (+0x32);
    a monster (0x1A) when its state is not 0; requests (1 / 0x1E) are not goal events."""
    if ev is None:
        return False
    if ev["type"] == 4:
        return ev.get("state") == 10 or bool(ev.get("active"))
    if ev["type"] == 0x1A:
        return ev.get("state", 0) != 0
    return False


def _monster(g, ev):
    try:
        from ..heroes import monster_of_slot
        m = monster_of_slot(g, ev.get("item", 0))
    except Exception:                       # noqa: BLE001  (no heroes module / no god block)
        m = -1
    return text(87, m) if 0 <= m <= 0x11 else ""


def goal_text(g, r, colony=False, events=True):
    """The row's goal (left) text. g may be None (an episode not started); events=False: as with no event."""
    t, v = r["type"], r["v"]
    if t == 0:
        return _fill(text(194, 17), amount=v[0])
    if t == 1:
        return _fill(text(194, 18), amount=v[0])
    if t == 2:
        if v[0] != -1:
            return _fill(text(194, 19), god=text(157, v[0] if 0 <= v[0] <= 13 else 0))
        other = bool(r.get("other"))
        k = (21 if other else 20) if v[2] < 2 else (23 if other else 22)
        return _fill(text(194, k), amount=v[2])
    if t == 3:
        return _fill(text(194, 24), amount=v[1], military_or_better=_military(v[0], v[1]))
    if t == 4:
        ev = _event(g, v[0]) if events else None
        if ev is None:
            return text(194, 26)                # FUN_0052A9F0 LAB_0052AA22: no event
        if not _outstanding(ev):
            return text(194, 26)
        god, q = ev.get("kind", 0), ev.get("quest", 0)
        return _fill(text(194, 25), god_quest=text(52, (god if 0 <= god <= 13 else 0) + 14 * q))
    if t == 5:
        ev = _event(g, v[0]) if events else None
        if ev is None:
            return text(194, 27)
        return _fill(text(194, 28 if _outstanding(ev) else 29), monster=_monster(g, ev))
    if t == 6:
        return _fill(text(194, 30), amount=v[1], item=text(98, v[0]))
    if t == 7:
        e = getattr(g, "empire", None) if g is not None else None
        c = e.cities.get(v[0]) if e is not None and 0 <= v[0] <= 21 else None
        return _fill(text(194, 31), city=c.name if c else "")
    if t == 8:
        return _fill(text(194, 32), amount=v[0])
    if t == 9:
        return _fill(text(194, 33), amount=v[1], house_level=text(28, v[0]))
    if t == 10:
        return _fill(text(194, 34), amount=v[0])
    if t in (12, 13):
        y0 = g.__dict__.get("scenario_year", g.start_year) if g is not None else r.get("start_year", 0)
        return _fill(text(194, 38 if t == 12 else 37), finish_date=finish_date(y0 + v[0]))
    if t == 14:
        return _fill(text(194, 35 if colony else 36), amount=v[1], item=text(98, v[0] & 0xFF))
    if t == 16:
        return _fill(text(194, 42 if v[0] == 1 else 41), amount=v[0])
    return ""


def stock_loads(g, gid):
    from .goals import stock_loads as sl
    return sl(g, gid)


def status_text(g, r):
    """The row's status (right) text (FUN_0052A6C0 .. 0052B500)."""
    t, v = r["type"], r["v"]
    if t == 0:
        return _fill(text(194, 43), amount=g.city.population)
    if t == 1:
        return _fill(text(194, 44), amount=g.city.treasury)
    if t == 2:
        from .. import gods
        b = gods.sanctuary(g, v[1]) if 0 <= v[1] <= 13 else None
        if b is not None:
            if v[2] < 2:
                from ..systems import monuments
                return _fill(text(194, 45), percent=f"{monuments.progress(b)}%")
            return _fill(text(194, 48 if v[3] == 1 else 49), amount=v[3])
        return text(194, 46 if v[2] < 2 else 47)
    if t == 3:
        return _fill(text(194, 50), amount=measure.units(g).get(v[0], 0))
    if t == 4:
        ev = _event(g, v[0])
        if ev is None:
            return ""
        if ev.get("state") == 10:
            return text(194, 51)
        return text(185, 121) if quest_button(g, r) else text(194, 52)
    if t == 5:
        ev = _event(g, v[0])
        if ev is None:
            return ""
        return text(194, 53 if ev.get("state") == 5 else 54)
    if t == 6:
        return _fill(text(194, 55), amount=v[2])
    if t == 7:
        e = getattr(g, "empire", None)
        c = e.cities.get(v[0]) if e is not None and 0 <= v[0] <= 21 else None
        return _fill(text(194, 56), diplomatic_status=text(253, REL.get(c.relation, 0))) if c else ""
    if t == 8:
        return _fill(text(194, 57), amount=v[1])
    if t == 9:
        return _fill(text(194, 58), amount=v[2])
    if t == 10:
        return _fill(text(194, 59), amount=measure.values(g)["trading_partners"])
    if t in (12, 13):                       # FUN_0052B250: (years left - 1) * 12 + 12 - month, 0 once in the year
        end = g.__dict__.get("scenario_year", g.start_year) + v[0]
        left = end - g.year - 1 if g.year + 1 < end else 0
        return _fill(text(194, 63), months_remaining=(left * 3 + 3) * 4 - g.month)
    if t == 14:
        if v[2] < v[1]:
            have = stock_loads(g, v[0] & 0xFF) if v[0] & 0xFF else 0
            return _fill(text(194, 60), amount=have) if have < v[1] else text(194, 61)
        return text(194, 62)
    if t == 16:
        return text(194, 69)
    return ""


def box(g, r):
    """The tick box (objectives_screen_draw's per-type test; goals_status_update 0x0052B7D0)."""
    t, v = r["type"], r["v"]
    if t == 12:
        from .goals import year_reached
        return year_reached(g, r)
    if t == 2:                               # the screen's copy of the test (v[2] forced to 1 for a named god)
        v = list(v)
        if v[0] != -1:
            v[2] = 1
        if v[2] < 2:
            from .goals import _finished
            return v[1] != -1 and _finished(g, v[1])
        return v[2] <= v[3]
    from .goals import met
    return bool(met(g, dict(r, v=list(v))))


def set_aside_button(g, r):
    """FUN_00529D10: a type-14 row is a button when 0 < need = v2 - v3 <= the stock in loads."""
    v = r["v"]
    gid = v[0] & 0xFF
    return r["type"] == 14 and gid != 0 and v[2] < v[1] and v[1] - v[2] <= stock_loads(g, gid)


def quest_button(g, r):
    """FUN_0052D240 (1L-5): a type-4 row is a button while its quest event v1 is outstanding (FUN_00471560: type 4,
    active +0x32, state 0 announced or 0xB): the row lights. Its window (the exe's 0x00FE2588 / 0x00FE2590 by
    FUN_005BDDD0: the quest's hero present and idle): quest_window."""
    if r["type"] != 4:
        return False
    from .. import scenario
    ev = scenario.get(g, r["v"][0]) if getattr(g, "scenario", None) is not None else None
    return bool(ev is not None and ev["type"] == 4 and ev.get("active") and ev.get("state") in (0, 0xB))


def rows(g, goals, colony=False, briefing=False):
    """[{goal, status, box, button}] for the screens; the briefing (0x35) has no status and empty boxes."""
    out = []
    for r in goals:
        if briefing:
            # the briefing shows quest / slay goals as with no event (26 "Fulfill a forthcoming quest", 27 "Slay a
            # monster"): oracle 1L3-europa-return r170 (slot 3's "Slay a monster" while its event 0, a monster
            # invasion, exists once the episode runs). Hypothesis: 0x35 comes before the episode's events are loaded.
            out.append(dict(type=r["type"], goal=goal_text(g, r, colony, events=False), status="", box=False,
                            button=False))
            continue
        row = dict(type=r["type"], goal=goal_text(g, r, colony), status=status_text(g, r), box=box(g, r),
                   button=set_aside_button(g, r) or quest_button(g, r))
        if row["button"] and r["type"] == 4:
            row["quest"] = quest_window(g, r)
        out.append(row)
    return out


def quest_window(g, r):
    """What a lit quest row's click does (0x0052BC20 -> FUN_0052D240's object, vtable +8): the quest's hero in the
    city and idle (FUN_005BDDD0: when an item choice +6 / +8 / +0xA is 0x1A, a hero) and the quest outstanding (FUN_00471560) ->
    0x00FE2590: army_dialog_open 0x005BD950 for the quest event (ours: MilPanel.openArmy kind "quest"); else
    0x00FE2588: the screen's child window (0x0052D010): a titled frame 28 x 12 at (ox + 0x32, oy + 0x32), the quest
    title (FUN_004836B0: quest_title_text) 22C centred in 0x1C0 at (ox + 0x32, oy + 0x40), its text (the next
    phrase, FUN_00483720) 11C paragraph at (ox + 0x4C, oy + 0x60) 0x1A0 wide, 13:3 "Right-click to continue" at
    (ox + 0x32, oy + 0xDA) centred; a right click closes it (0x0052D200)."""
    from .. import scenario, messages
    ev = scenario.get(g, r["v"][0])
    row = scenario._quest_row(g, ev)
    need_hero = 0x1A in ev["groups"]["item"][1:4]                 # FUN_004691E0(0x1A): an item choice is "hero"
    out = dict(event=ev["id"], army=bool(row["ready"] or not need_hero), title=row["title"], body="")
    try:
        from ..heroes import events as hev, heroes
        h = heroes.hero_of_slot(g, ev.get("b36", -1))
        out["body"] = messages.text(hev.quest_title(ev.get("kind", 0), ev.get("quest", 0)) + 1).replace(
            "[hero_needed]", heroes.name(h) if h >= 0 else "")
    except (ImportError, KeyError):
        pass
    return out
