"""Our side of the 1I oracle runs (docs/logic/heroes-monsters.md "Oracle check (1I)"): a new Open Play Sandbox with the
Maenads event (#1) poked to year 0 / January as re/oracle/scenarios/monster-lair.txt / monster-bash.txt, optional
commands (e.g. the scenario's house plots and road), then the monsters and buildings every EVERY ticks in the format of
tools/oracle_heroes.py --brief.

    python3 tools/sim_monster_track.py [--ticks 6528] [--every 204] [--seed 1] [--cmd "build house 120 196"]...
    python3 tools/sim_monster_track.py --bash      the monster-bash.txt setup (the two house plots)
    python3 tools/sim_monster_track.py --hero --every 102 --ticks 4500   the monster-hero.txt setup: the cheat, Achilles'
        hall at raw (142, 189) with its road, Send For at tick 250 (the exe's click falls between ticks 204 and 306)

    python3 tools/sim_monster_track.py --quest --every 102 --ticks 9600   re/oracle/scenarios/quest-trip.txt: --hero, the
        open-play quest (event #0) at year 0 / February with hero slot 2 (Achilles), `dispatch achilles` at tick 4284 (the
        oracle's poke tick); prints the quest's state / countdown and the hero's action and tile
    python3 tools/sim_monster_track.py --quest --every 51 --ticks 5468 --save Q.pkl   the state of
        re/oracle/scenarios/1L-quest-worldmap.txt's world map (tick 5469): `python3 -m sim live Q.pkl`, open the map

Positions are ours (raw grid); the exe's dumps print logical ones: raw = logical + (1, 1) on the sandbox.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.game import Game  # noqa: E402

HERO = ["heroes cheat", "build heroes_hall 142 189 achilles", "road 146 189 146 191"]
BASH = ["build house 121 197", "build house 123 202"]     # the exe's logical (120, 196), (122, 201): raw = + origin (1, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=6528)
    ap.add_argument("--every", type=int, default=204)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--cmd", action="append", default=[])
    ap.add_argument("--bash", action="store_true")
    ap.add_argument("--hero", action="store_true")
    ap.add_argument("--quest", action="store_true")
    ap.add_argument("--save", help="save the game at the end (e.g. for the world map: 1L-quest-worldmap.txt)")
    a = ap.parse_args()
    a.hero |= a.quest
    g = Game("sandbox", a.seed)
    ev = g.scenario.events[1]
    ev["year"], ev["month"] = 0, 0
    q = g.scenario.events[0]
    if a.quest:
        q["year"], q["month"], q["b36"] = 0, 1, 2
    for c in (BASH if a.bash else []) + (HERO if a.hero else []) + a.cmd:
        print("#", c, "->", g.command(c))
    while g.tick <= a.ticks:
        ms = [w for w in g.walkers.values() if w.role in ("monster", "hero") and not getattr(w, "hidden", False)]
        bs = sorted((b.key, b.x, b.y) for b in g.buildings.values() if b.kind not in ("road",))
        if a.quest:
            h = next((w for w in g.walkers.values() if w.role == "hero"), None)
            print(f"{g.tick:06d} quest state {q['state']} active {q['active']} countdown {q.get('countdown')} | hero "
                  + (f"act {h.act} at ({h.x},{h.y}) hidden {int(bool(getattr(h, 'hidden', False)))}" if h else "-"))
        else:
            print(f"{g.tick:06d}", " ".join(f"{w.role}{getattr(w, 'mid', getattr(w, 'hero', ''))}@{w.x},{w.y}a{w.act}"
                                            for w in ms), "buildings", len(bs), bs)
        for _ in range(a.every):
            g.step(1)
            if a.hero and g.tick == 250:
                print("#", g.tick, "sendfor achilles ->", g.command("sendfor achilles"))
            if a.quest and g.tick == 4284:
                print("#", g.tick, "dispatch achilles ->", g.command("dispatch achilles"))
            if a.bash:                   # as the oracle's poke file: the plots' no-road counters stay 0
                for b in g.buildings.values():
                    b.misc.pop("noroad", None)
    if a.save:
        g.save(a.save)


if __name__ == "__main__":
    main()
