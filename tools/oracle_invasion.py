"""Oracle runs of track 1B: a land and a sea invasion in the Open Play Sandbox, the exe against ours (docs/logic/
military.md "Oracle check: invasions", docs/re/oracle.md).

    python3 tools/oracle_invasion.py --poke land|sea > DIR/poke.txt   # ZEUS_POKE: an invasion at the first month change
    python3 tools/oracle_invasion.py --brief DIR/dump/tick_*.bin*        # invaders / enemy ships per dump (logical x y)
    python3 tools/oracle_invasion.py --ours land|sea TICK...            # ours, the same event, the same ticks (logical)
    python3 tools/oracle_invasion.py --compare land|sea DIR [FROM TO]    # per-figure walk, ours against the dumps

--compare: ours' state after tick K is compared with the exe's dump K (entry of tick K: Game.step counts the tick,
runs the cycle step's work, then the figure pass, as simulation_tick). The event is spawned inside ours' run_day of
the change to February (the exe's month change block in month_advance, before the walkers of that tick). Figures are
paired by company order (the exe's slots 42.. and ours' 35.. in spawn order) and slot; a company is compared while
its mode (+0x91), layout (+0x2A) and target (+0x3A / +0x3C) equal ours' (the special-mode roll replays the exe's
outcome, _replay_special):
tile, action, tile progress (+0x39), route (+0x3A > 0), the +0x36 timer in actions 7 / 9.

The poke appends event 4 (g_events 0x009173F4, 0x7C each; count 0x009173F0) to the sandbox's 4: type 2, dated
January of the start year, warning months 0 (so invasion_event_month 0x00476E20 spawns it at the change to February:
months until due 0), event_init_defaults 0x00467590 for the rest; strength 50 %; land: point 1 (logical (148, 190)),
invader Sparta (city 3, an active rival: +0x02 = 2, +0xD4 = 1, +0x170 = 1); sea: point 9 (sea point 0, (34, 80)),
2 warships, landing point 0 ((104, 101)), invader Delos (city 5). Target class +0x38 = 0. The camera (0x00DA2F64 /
0x00DA2F68) is put near the point (land: 6 tiles up-screen of it; 800x600: COL = ((x - y) * 30 + 6580) / 60, ROW = x + y - 18 for raw x, y at the
view's centre; tools/oracle_gods.py).
Figures g_figures 0x00DBD788 (0x184 each): +0x0A type (0x28 archer, 0x29 infantry, 0x2A cavalry, 0x3F transport,
0x40 warship), +0x0E state, +0x11 direction, +0x14 / +0x16 x y, +0x38 action, +0x60 company, +0x65 hidden.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402

FIG, FSZ = 0x00DBD788, 0x184
EV, ESZ, NEV = 0x009173F4, 0x7C, 0x009173F0
TYPES = {0x28: "archer", 0x29: "infantry", 0x2A: "cavalry", 0x3F: "transport", 0x40: "warship"}
KIND = dict(land=dict(point=1, city=3, ships=0, landing=0, at=(143, 185)),
            sea=dict(point=9, city=5, ships=2, landing=0, at=(35, 81)))
STRENGTH = 50


def poke(kind):
    k = KIND[kind]
    a = EV + 4 * ESZ
    f = []                                      # (offset, size, value)
    f += [(0x00, 2, 4), (0x02, 1, 2), (0x03, 1, 0), (0x06, 2, 1), (0x08, 2, -1), (0x0A, 2, -1), (0x0C, 2, STRENGTH),
          (0x0E, 2, -1), (0x10, 2, 5), (0x12, 2, 10), (0x14, 2, 0), (0x16, 2, -1), (0x18, 2, 1), (0x1A, 2, 2),
          (0x1C, 2, k["point"]), (0x1E, 2, -1), (0x20, 2, 1), (0x22, 2, 8), (0x24, 2, -1), (0x26, 2, -1),
          (0x28, 4, 2), (0x2C, 2, 0), (0x34, 2, -1), (0x36, 1, k["ships"]), (0x38, 1, 0), (0x52, 2, -1),
          (0x54, 2, -1), (0x58, 2, k["city"]), (0x5A, 2, -1), (0x5C, 2, 1), (0x5E, 2, 8), (0x78, 1, k["landing"])]
    x, y = k["at"]
    col, row = max(0, ((x - y) * 30 + 6580) // 60), max(0, x + y - 18)
    out = [f"5 {a + o:x} {n} {v & ((1 << 8 * n) - 1)}" for o, n, v in f]
    out += [f"5 {NEV:x} 4 5", f"5 da2f64 4 {col}", f"5 da2f68 4 {row}"]
    return "\n".join(out)


def fig_rows(d):
    rows = []
    for i in range(1, 2000):
        a = FIG + i * FSZ
        try:
            st, ty = d.at(a + 0x0E, '<B'), d.at(a + 0x0A, '<B')
        except KeyError:
            break
        if st and ty in TYPES:
            rows.append((i, TYPES[ty], d.at(a + 0x14, '<h'), d.at(a + 0x16, '<h'), d.at(a + 0x11, '<b'),
                         d.at(a + 0x38, '<B'), d.at(a + 0x65, '<B'), d.at(a + 0x60, '<h')))
    return rows


def show(tick, rows):
    """One line per tick: per kind the count shown / hidden, and the shown figures' tiles, actions and directions."""
    by = {}
    for _, kind, x, y, dr, act, hid, comp in rows:
        by.setdefault(kind, []).append((x, y, dr, act, hid, comp))
    parts = []
    for kind in sorted(by):
        fs = by[kind]
        vis = sorted((x, y, dr, act, comp) for x, y, dr, act, hid, comp in fs if not hid)
        parts.append(f"{kind} {len(vis)}/{len(fs)} " + " ".join(f"({x},{y})d{dr}a{act:#x}c{comp}" for x, y, dr, act, comp in vis[:12]))
    print(f"tick {tick}: " + (" | ".join(parts) or "-"))


def brief(paths):
    from oracle import Dump
    for p in paths:
        t = int(os.path.basename(p).split("_")[1].split(".")[0])
        show(t, fig_rows(Dump(p)))


ROLE = {"enemy_archer": "archer", "enemy_infantry": "infantry", "enemy_cavalry": "cavalry"}


def spawn_day(g):
    """The day hook (sim/hooks.py, end of run_day) that spawns g._oracle_inv's event at the change to February: the
    exe's month change block in month_advance, before the walkers of that tick."""
    from sim.military import invaders
    kind = g.__dict__.get("_oracle_inv")
    if kind is None or g.tick != g.rules["ticks_per_day"] * g.rules["days_per_month"]:
        return
    k = KIND[kind]
    ev = dict(id=4, amount=STRENGTH, city=k["city"], landing=k["landing"], ships=k["ships"])
    if kind == "sea":
        invaders.invade(g, ev, army=0, strength=STRENGTH, target_class=0, sea_pt=k["point"])
    else:
        invaders.invade(g, ev, point=invaders.pick_point(g, k["point"]), army=0, strength=STRENGTH, target_class=0)


def arm(g, kind):
    """Make g spawn the run's event (spawn_day)."""
    from sim import hooks
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    g._oracle_inv = kind
    hooks.attach(g, "day", "oracle_invasion:spawn_day")


def _game(kind):
    """A new sandbox game that spawns the event at the change to February (arm)."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sim.game import Game
    g = Game("sandbox", 1)
    arm(g, kind)
    return g


def ours(kind, ticks):
    """A new sandbox game (ours), the same event: type 2, strength 50 %, the same point / ships / landing, spawned at
    the change to February (the exe's month change block, before the month increments)."""
    from sim.military import invaders
    g = _game(kind)
    ox, oy = g.world.origin
    for t in sorted(ticks):
        g.step(max(0, t - g.tick))
        rows = []
        for w in g.walkers.values():
            kd = ROLE.get(w.role) or ("transport" if w.role == "enemy_transport" else
                                       "warship" if w.role == "enemy_warship" else None)
            if kd:
                f = tuple(getattr(w, "face", None) or ())
                dr = invaders.DIRS8.index(f) if f in invaders.DIRS8 else -1
                a = getattr(w, "act", None)
                rows.append((w.id, kd, w.x - ox, w.y - oy, dr, a if isinstance(a, int) else 0,
                             1 if getattr(w, "hidden", False) else 0, getattr(w, "company", 0) or 0))
        show(t, rows)


ACT = {"wait": 7, "march": 9, "hunt": 13, "disengage": 11, "leave": 3, "attack": 10, "attack7": 7}
FORM, FMS = 0x00DB7B40, 0x9C


def exe_figs(d):
    out = {}
    for i in range(1, 2000):
        a = FIG + i * FSZ
        try:
            st, ty = d.at(a + 0x0E, '<B'), d.at(a + 0x0A, '<B')
        except KeyError:
            break
        if st and ty in (0x28, 0x29, 0x2A):
            c = d.at(a + 0x60, '<h')
            fa = FORM + c * FMS
            out[(c, d.at(a + 0x62, '<B'))] = dict(
                xy=(d.at(a + 0x14, '<h'), d.at(a + 0x16, '<h')), act=d.at(a + 0x38, '<B'), prog=d.at(a + 0x39, '<b'), tm=d.at(a + 0x36, '<h'),
                route=d.at(a + 0x3A, '<h') > 0, dest=(d.at(a + 0x24, '<h'), d.at(a + 0x26, '<h')),
                hid=d.at(a + 0x65, '<B'), comp=(d.at(fa + 0x91, '<B'), d.at(fa + 0x2A, '<h'),
                                                (d.at(fa + 0x3A, '<h'), d.at(fa + 0x3C, '<h'))))
    return out


def _replay_special(g, files, invaders):
    """The special-mode roll (enemy_company_special_roll 0x004FFE00) draws the exe's RNG; ours draws its own, so the
    companies' modes part after the first roll (11-02: any change to ours' draw order moved them). Replayed: ours'
    roll takes the exe's outcome, the company's mode (+0x91 == 2) in the first dump after the AI's tick (exe
    company c paired with ours by order, as compare). Ours' RNG is still drawn (the draw order stays ours')."""
    from oracle import Dump
    modes = {}

    def exe_modes(t):
        if t not in modes:
            d = Dump(dict(files)[t])
            modes[t] = {c: v["comp"][0] for (c, _), v in exe_figs(d).items()}
        return modes[t]
    orig = invaders._special

    class Fixed:
        def __init__(self, rng, hit):
            self.rng, self.hit = rng, hit

        def randrange(self, n):
            self.rng.randrange(n)
            return -1 if self.hit else n

    def special(g_, comp, row1, rng):
        nxt = next((t for t, _ in files if t > g_.tick), None)
        if nxt is None:
            return orig(g_, comp, row1, rng)
        em = exe_modes(nxt)
        ocs = sorted(invaders.ecomps(g_))
        c = dict(zip(ocs, sorted(em))).get(comp["id"])
        if c is None:
            return orig(g_, comp, row1, rng)
        return orig(g_, comp, row1, Fixed(rng, em[c] == 2))
    invaders._special = special


def compare(kind, run, lo=0, hi=10 ** 9):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from oracle import Dump, dump_files
    from sim.military import invaders
    g = _game(kind)
    ox, oy = g.world.origin
    month = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    files = [(int(os.path.basename(p).split("_")[1].split(".")[0]), p) for p in dump_files(os.path.join(run, "dump"))]
    _replay_special(g, files, invaders)
    tot = bad = 0
    gone = set()                                   # companies that differed once (mode, layout or target)
    for t, p in files:
        if t < lo or t > hi or t < month:
            continue
        g.step(max(0, t - g.tick))
        ex = exe_figs(Dump(p))
        ecs = sorted({c for c, _ in ex})
        ocs = sorted(invaders.ecomps(g))
        cmap = dict(zip(ecs, ocs))
        n = m = 0
        lines = []
        for (c, slot), e in sorted(ex.items()):
            oc = invaders.ecomps(g).get(cmap.get(c))
            if oc is None:
                continue
            tg = oc["target"]
            if c in gone or e["comp"] != (oc["mode"], oc["layout"], (tg[0] - ox, tg[1] - oy)):
                gone.add(c)
                continue
            w = next((g.walkers[i] for i in oc["ids"] if i in g.walkers and g.walkers[i].slot == slot), None)
            if w is None or w.anim:
                continue
            if e["hid"] and getattr(w, "hidden", False):
                continue
            o_act = ACT.get(w.task, -1)
            o = dict(xy=(w.x - ox, w.y - oy), act=o_act, prog=15 if w.__dict__.get("fprog") is None else w.fprog,
                     route=w.__dict__.get("iroute") is not None,
                     tm=(w.appear if w.hidden else w.aim_due) - g.tick if o_act in (7, 9) else e["tm"])
            n += 1
            diff = [f for f in ("xy", "act", "prog", "route", "tm") if o[f] != e[f]]
            if e["hid"] != int(bool(getattr(w, "hidden", False))):
                diff.append("hidden")
            if diff:
                m += 1
                lines.append(f"  c{c}/{slot}: " + ", ".join(f"{f} exe {e.get(f, e['hid'])} ours {o.get(f, w.hidden)}"
                                                             for f in diff))
        tot += n
        bad += m
        print(f"tick {t}: {n} figures compared, {m} differ" + ("" if not lines else "\n" + "\n".join(lines[:8])))
    print(f"total: {tot} figure-dumps compared, {bad} differ")


def main(argv):
    if argv[:1] == ["--poke"]:
        print(poke(argv[1]))
    elif argv[:1] == ["--brief"]:
        brief(argv[1:])
    elif argv[:1] == ["--ours"]:
        ours(argv[1], [int(t) for t in argv[2:]])
    elif argv[:1] == ["--compare"]:
        compare(argv[1], argv[2], *[int(a) for a in argv[3:5]])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
