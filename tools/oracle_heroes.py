"""Print the heroes/monsters state of oracle dumps (docs/re/oracle.md; docs/logic/heroes-monsters.md "Oracle check"):
monster (0x44), hero (0x45) and statue (0x46) figures, the active buildings (type, origin, state), hero records and
the monster events.

    python3 tools/oracle_heroes.py re/oracle/runs/RUN/dump/tick_*.bin*
    python3 tools/oracle_heroes.py --brief DUMP...        one line per dump: figures + building count
    python3 tools/oracle_heroes.py --bash-poke > POKE.txt  the ZEUS_POKE file of re/oracle/scenarios/monster-bash.txt
    python3 tools/oracle_heroes.py --hero-poke > POKE.txt  the ZEUS_POKE file of re/oracle/scenarios/monster-hero.txt
    python3 tools/oracle_heroes.py --quest-poke > POKE.txt the ZEUS_POKE file of re/oracle/scenarios/quest-trip.txt
    python3 tools/oracle_heroes.py --quest DUMP...         one line per dump: quest event #0 and the hero
    python3 tools/oracle_heroes.py --overview-poke > POKE.txt  the ZEUS_POKE file of re/oracle/scenarios/overview-quest.txt

Figures g_figures 0x00DBD788 (0x184 each): +0x0A type, +0x0E state, +0x14/16 x y, +0x24/26 dest, +0x2C/2E home
(spawn), +0x30/32 roam centre, +0x36 timer, +0x38 action, +0x82 target figure, +0x5E target building, +0x98 damage.
Buildings 0x0092E658 (0x118 each): +0 state, +6/8 x y, +0x10 type. Hero records 0x00F0E4E8 (8 x 28): +0 present?,
+0x0C needed, +0x19 paid (docs/logic/heroes-monsters.md "Heroes").
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402
from oracle import Dump  # noqa: E402

FIG, FSZ = 0x00DBD788, 0x184
BLD, BSZ = 0x0092E658, 0x118
HERO, HSZ = 0x00F0E4E8, 28
EVT, ESZ = 0x009173F4, 124
MYTH = {0x44: "monster", 0x45: "hero", 0x46: "statue"}


def fig(d, i):
    a = FIG + i * FSZ
    r = lambda off, f: d.at(a + off, f)
    return dict(id=i, state=r(0x0E, '<B'), type=r(0x0A, '<B'), m=r(0x0B, '<B'), x=r(0x14, '<h'), y=r(0x16, '<h'),
                act=r(0x38, '<B'), dest=(r(0x24, '<h'), r(0x26, '<h')), home=(r(0x2C, '<h'), r(0x2E, '<h')),
                centre=(r(0x30, '<h'), r(0x32, '<h')), timer=r(0x36, '<h'), tf=r(0x82, '<h'), tb=r(0x5E, '<h'),
                dmg=r(0x98, '<h'), flags=r(0x10C, '<I'), dir=r(0x11, '<b'))


def buildings(d):
    out = []
    for i in range(1, 2000):
        try:
            st = d.at(BLD + i * BSZ, '<B')
        except KeyError:
            break
        if st:
            a = BLD + i * BSZ
            out.append(dict(id=i, state=st, type=d.at(a + 0x10, '<h'), x=d.at(a + 6, '<h'), y=d.at(a + 8, '<h')))
    return out


def figures(d):
    out = []
    for i in range(1, 2000):
        f = fig(d, i)
        if f['state'] and f['type'] in MYTH:
            out.append(f)
    return out


def bash_poke(last=8000):
    """Camera to cell (70, 290), the Maenads event (#1) to year 0 / January (as monster-lair.txt), and the no-road
    counter (Building +0x24) of buildings 1 and 2 (the two house plots) zeroed every 51 ticks, so the exe keeps them
    (house_road_check: removed on the 5th check without a road)."""
    out = ["5 da2f64 4 70", "5 da2f68 4 290", "5 917484 2 0", "5 917473 1 0"]
    for t in range(60, last, 51):
        for b in (1, 2):
            out.append(f"{t} {BLD + b * BSZ + 0x24:x} 2 0")
    return "\n".join(out)


def hero_poke():
    """Camera to cell (86, 318) (the open land at raw (142, 189)), the cheat flag 0x00665DF0 = 1 (every hero's hall
    in the menu, Send For without requirements or payment: hero_hall_buildable 0x004FA620, hero_can_send_for
    0x004FA670, hero_send_for 0x004FC2B0) and the Maenads event (#1) to year 0 / January."""
    return "\n".join(["5 da2f64 4 86", "5 da2f68 4 318", "5 665df0 1 1", "5 917484 2 0", "5 917473 1 0"])


def missile_poke(last=8000):
    """re/oracle/scenarios/monster-missile.txt: as bash_poke (the house plot kept: building 1), plus the Maenads event's
    (#1) target categories +0x38/+0x3A/+0x3C = 6 (residential) and aggressiveness +0x3E = 1 (copied to the figure by
    monster_spawn), and at tick 1640 (the Maenad, figure 56, spawned at 1632, back in rest 7) her rest countdown +0x36 = -1: her next
    rest update ends it (monster_rest_update 0x005304B0 -> rampage 10), so she goes for the plot in action 11 and
    shoots at it from Chebyshev 2..3 (action 28, monster_missile_attack 0x00530ED0)."""
    ev = EVT + ESZ
    out = [bash_poke(last)] + [f"5 {ev + o:x} 2 {v}" for o, v in ((0x38, 6), (0x3A, 6), (0x3C, 6), (0x3E, 1))]
    out.append(f"1640 {FIG + 56 * FSZ + 0x36:x} 2 65535")
    return "\n".join(out)


QUEST_FIG, QUEST_TICK = 57, 4284


def quest_poke():
    """As hero_poke (Achilles' hall, the Maenads), plus the open-play quest (event #0, Zeus, city 7 Thasus, lead 2):
    year 0 / February (+0x14, +0x03) and its hero slot +0x36 = 2 (Achilles, so the hall of monster-hero.txt serves it).
    At QUEST_TICK (Achilles, figure 57 in the 1I-hero run, patrolling) the army dialog's dispatch is emulated, as
    army_dialog_dispatch 0x005BE0E0 -> FUN_0046DA70 + expedition_send_forces 0x004DEB30 leave it: event state +0x30 = 6,
    countdown +0x2E = 3 (not read again: state 6 ends on event_months_until_due), the hero's +0x02 = 1 (enlisted:
    expedition_forces_home 0x004DEE60 brings back only enlisted heroes), +0x132 = 0 (the event) and action 14 (to the
    land exit; written directly as expedition_send_forces does, which also frees his route)."""
    ev = EVT
    fig = FIG + QUEST_FIG * FSZ
    out = [hero_poke(), f"5 {ev + 0x14:x} 2 0", f"5 {ev + 3:x} 1 1", f"5 {ev + 0x36:x} 2 2",
           f"{QUEST_TICK} {ev + 0x30:x} 2 6", f"{QUEST_TICK} {ev + 0x2E:x} 2 3",
           f"{QUEST_TICK} {fig + 2:x} 1 1", f"{QUEST_TICK} {fig + 0x132:x} 2 0", f"{QUEST_TICK} {fig + 0x38:x} 1 14"]
    return "\n".join(out)


def overview_poke():
    """re/oracle/scenarios/overview-quest.txt: only the open-play quest's date (event #0: year 0, February), so the
    monthly pass of tick 1632 opens it (state 0, active) and request_list_rebuild lists it (bugs.md 255)."""
    return "\n".join([f"5 {EVT + 0x14:x} 2 0", f"5 {EVT + 3:x} 1 1"])


def quest_line(d, tick):
    r = lambda off, f: d.at(EVT + off, f)
    f = fig(d, QUEST_FIG)
    return (f"{tick} quest state {r(0x30, '<h')} active {r(0x32, '<B')} countdown {r(0x2E, '<h')} "
            f"| fig {QUEST_FIG} type {f['type']:#x} state {f['state']} act {f['act']} at ({f['x']},{f['y']}) "
            f"+0x132 {d.at(FIG + QUEST_FIG * FSZ + 0x132, '<h')}")


def main(argv):
    if argv[:1] == ['--bash-poke']:
        print(bash_poke())
        return
    if argv[:1] == ['--missile-poke']:
        print(missile_poke())
        return
    if argv[:1] == ['--hero-poke']:
        print(hero_poke())
        return
    if argv[:1] == ['--quest-poke']:
        print(quest_poke())
        return
    if argv[:1] == ['--overview-poke']:
        print(overview_poke())
        return
    if argv[:1] == ['--quest']:
        for p in argv[1:]:
            print(quest_line(Dump(p), os.path.basename(p)[5:11]))
        return
    brief = argv[:1] == ['--brief']
    for p in argv[1:] if brief else argv:
        d = Dump(p)
        tick = os.path.basename(p)[5:11]
        fs = figures(d)
        bs = buildings(d)
        if brief:
            print(tick, ' '.join(f"{MYTH[f['type']]}{f['m']}@{f['x']},{f['y']}a{f['act']}" for f in fs),
                  'buildings', len(bs), sorted((b['type'], b['x'], b['y'], b['state']) for b in bs))
            continue
        print('==', tick)
        for f in fs:
            print(' ', MYTH[f['type']], f)
        for b in bs:
            print('  building', b)
        for h in range(8):
            raw = bytes(d.at(HERO + h * HSZ + k, '<B') for k in range(HSZ))
            print('  hero', h, raw.hex())


if __name__ == '__main__':
    main(sys.argv[1:])
