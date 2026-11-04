"""CLI verbs of the heroes-and-monsters module and its play-mode export.

  heroes [on|off]                 status (halls, requirements, heroes, monsters, quests), or switch the module
  heroes cheat [off]              the exe's cheat flag 0x00665DF0: any scenario hero's hall, Send For without paying
  monsters                        the monsters on the map
  monster SLOT|NAME [X Y] [aggr N] [lead N]   test: a monster event now (type 26, as the scenario's: slot 0..8 or a
                                  monster name/id; at X Y instead of the lair; aggressiveness 0..3 (open play: 0);
                                  lead N = warning months first (state 4))
  quest GOD [HERO_SLOT] [statue 1|2]  test: a god's quest now (type 4, as the sandbox's Golden Fleece: zeus 0 2)
  hero NAME                       one hero's record and requirements
  sendfor NAME                    the hall's Send For button (hero_send_for 0x004FC2B0)
  dispatch NAME                   send the hero in the city on the open quest (the quest window's Dispatch Hero)
"""
from . import state, on, data, monster_of_slot, slot_of_monster
from . import events, heroes, monsters


def _hero(a):
    names = [h["name"].lower() for h in data()["heroes"]]
    if not a:
        raise ValueError("which hero? (" + ", ".join(names) + ")")
    t = " ".join(a).lower()                       # the whole rest of the line: names with spaces too
    if t.isdigit() and int(t) < 8:
        return int(t)
    if t not in names:
        raise ValueError(f"no hero '{' '.join(a)}' ({', '.join(names)})")
    return names.index(t)


def _monster(g, t):
    names = [m["name"].lower().replace(" ", "") for m in data()["monsters"]]
    t = t.lower().replace(" ", "")
    if t.isdigit():
        return int(t)
    for i, n in enumerate(names):
        if n.startswith(t) or t.startswith(n):
            return i
    raise ValueError(f"no monster '{t}'")


def run(g, op, a):
    if op == "heroes":
        if a and a[0] in ("on", "off"):
            st = state(g)
            st["on"] = a[0] == "on"
            if not st["on"]:
                from ..systems import walkers
                for w in [w for w in g.walkers.values() if w.role in ("monster", "hero")]:
                    walkers.remove(g, w)
            return f"heroes and monsters {'on' if st['on'] else 'off'}"
        if a and a[0] == "cheat":                 # the exe's cheat flag 0x00665DF0 ('A' key in cheat mode): halls of
            st = state(g)                         # any scenario hero, Send For without requirements or payment
            st["cheat"] = len(a) < 2 or a[1] != "off"
            return f"hero cheat {'on' if st['cheat'] else 'off'}"
        return status(g)
    if not on(g):
        raise ValueError("the heroes module is off (`heroes on`)")
    if op == "monsters":
        return monsters_text(g)
    if op == "monster":
        if not a:
            raise ValueError("usage: monster SLOT|NAME [X Y] [aggr N] [lead N]")
        opts, rest = {}, []
        i = 1
        while i < len(a) and not a[0].isdigit() and not a[i].lstrip("-").isdigit() and a[i] not in ("aggr", "lead"):
            i += 1                                # a name with spaces (Calydonian Boar, Black Warrior): one argument
        a = [" ".join(a[:i])] + list(a[i:])
        i = 1
        while i < len(a):
            if a[i] in ("aggr", "lead") and i + 1 < len(a):
                opts[a[i]] = int(a[i + 1])
                i += 2
            else:
                rest.append(a[i])
                i += 1
        if a[0].isdigit() and int(a[0]) <= 8:
            k = int(a[0])
            if monster_of_slot(g, k) < 0:
                raise ValueError(f"slot {k} has no monster on this map")
        else:
            m = _monster(g, a[0])
            k = slot_of_monster(g, m)
            if k < 0:
                k = -1 - m                        # ours: a monster the scenario does not list (spawned at the entry)
        xy = [int(x) for x in rest if x.lstrip("-").isdigit()]
        ev = events.alloc(g, dict(type=26, item=k, b3e=opts.get("aggr", 0), lead=opts.get("lead", 0),
                                  kind=2 if opts.get("lead") else 0, flags=events.DYNAMIC | events.WARN))
        if opts.get("lead"):
            ev["year"], ev["month"] = events.year_offset(g), g.month
            ev["state"] = 4
        if len(xy) >= 2:
            ev["at"] = (xy[0], xy[1])
        events.monster_event(g, ev)
        return monsters_text(g)
    if op == "quest":
        if not a:
            raise ValueError("usage: quest GOD [HERO_SLOT] [statue 1|2]")
        from ..systems.commemorative import GODS
        names = [x.lower() for x in GODS]
        god = int(a[0]) if a[0].isdigit() else names.index(a[0].lower()) if a[0].lower() in names else None
        if god is None:
            raise ValueError(f"no god '{a[0]}'")
        nums = [int(x) for x in a[1:] if x.isdigit()]
        slot = nums[0] if nums else 0
        sel = nums[1] if len(nums) > 1 else 2
        ev = events.alloc(g, dict(type=4, kind=god, b36=slot, b38=sel))
        events.quest(g, ev)
        return quests_text(g)
    if op == "hero":
        return hero_text(g, _hero(a))
    if op == "sendfor":
        return heroes.send_for(g, _hero(a))
    if op == "dispatch":
        return heroes.dispatch(g, _hero(a))
    return None


def status(g):
    if not on(g):
        return "heroes and monsters off (`heroes on`)"
    out = [monsters_text(g), quests_text(g)]
    for h in range(8):
        if heroes.record(g, h).get("hall") or heroes.record(g, h).get("needed"):
            out.append(hero_text(g, h))
    return "\n".join(x for x in out if x)


def monsters_text(g):
    ms = [w for w in g.walkers.values() if w.role == "monster"]
    if not ms:
        return "no monsters on the map"
    return "\n".join(monsters.describe(g, w) for w in ms)


def quests_text(g):
    qs = [ev for ev in events.records(g) if ev["type"] == 4 and ev["state"] not in (10, 5) and ev["active"]]
    if not qs:
        return ""
    from ..systems.commemorative import GODS
    return "\n".join(f"quest of {GODS[ev['kind']]}: state {ev['state']} ({'waiting for the hero' if ev['state'] == 0 else 'hero away' if ev['state'] == 6 else 'returning'})"
                     for ev in qs)


def hero_text(g, h):
    return heroes.describe(g, h)


def _god_name(god):
    """Text 157:god (the god names; the army dialog's [god] token)."""
    from ..systems.commemorative import GODS
    return GODS[god] if 0 <= god < len(GODS) else ""


def export(g):
    return dict(on=on(g), heroes=[heroes.export(g, h) for h in range(8)],
                monsters=[monsters.export(g, w) for w in g.walkers.values() if w.role == "monster"],
                statues=monsters.statues(g),
                quests=[dict(id=ev["id"], god=ev["kind"], god_name=_god_name(ev["kind"]), quest=ev.get("quest", 0), state=ev["state"],
                             city=ev.get("city", -1), hero=heroes.hero_of_slot(g, ev["b36"]))
                        for ev in events.records(g) if ev["type"] == 4 and ev["active"]])
