"""The control panel's alert slots, the exe against ours (docs/play/alerts.md "Checks", docs/re/oracle.md).

    python3 tools/oracle_alerts.py --exe re/oracle/runs/RUN          # the slots per dump, printed when they change
    python3 tools/oracle_alerts.py --ours land|monster|god [TICKS]   # ours, the setup of that run, same format
    python3 tools/oracle_alerts.py --poke > DIR/poke.txt              # ZEUS_POKE of re/oracle/scenarios/alerts.txt
    python3 tools/oracle_alerts.py --script 800|1024                  # its script (DIR = the run dir)
    python3 tools/oracle_alerts.py --bal-poke > DIR/poke.txt          # re/oracle/scenarios/alerts-balloon.txt

The exe's slots: 4 records of 0x70 at 0x00665E48 (save block 132 of the dumps): +4 type (-1 none), +8 year, +0xC
month, +0x10 day of month, +0x14 tiles (DAT_00DA2F80 + y * 0xE4 + x), +0x64 count, +0x68 next, +0x6C all visited.
Printed: tick, the date (year month day), per slot "-" or (type, raised (month, day), count, next, visited, tiles
logical x y). Ours prints the same from sim/alerts.py (tiles raw - World.origin = logical).
Setups of --ours (the oracle runs they copy): land = 1B-inv-land (tools/oracle_invasion.py: the invasion spawned
at tick 815, the month change); monster = 1I-bash / 1I-hero (the Maenads event, #1, moved to year 0 / January:
spawn at the change to March); god = 1H-god (the jealousy countdown at 1: a jealous god at day 5, tick 255).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SLOTS, SZ = 0x00665E48, 0x70


def exe_rows(d):
    off = d.at(0x00DA2F80)
    rows = []
    for k in range(4):
        a = SLOTS + k * SZ
        t = d.at(a + 4)
        if t == -1:
            rows.append("-")
            continue
        n, nxt, vis = d.at(a + 0x64), d.at(a + 0x68), d.at(a + 0x6C, "<B")
        tiles = [d.at(a + 0x14 + 4 * i) - off for i in range(min(max(n, 0), 20))]
        rows.append((t, (d.at(a + 0xC), d.at(a + 0x10)), n, nxt, vis, [(v % 0xE4, v // 0xE4) for v in tiles]))
    return (d.at(0x0091EC04), d.at(0x0091EC08), d.at(0x0091EC0C)), rows


def exe(run):
    import glob
    from oracle import Dump
    prev = None
    for p in oracle.dump_files(os.path.join(run, "dump")):
        date, rows = exe_rows(Dump(p))
        if rows != prev:
            print(int(os.path.basename(p)[5:11]), *date, rows)
            prev = rows


def ours_rows(g):
    from sim import alerts
    ox, oy = g.world.origin
    st = g.__dict__.get("alerts")
    rows = []
    for s in (st["slots"] if st else [dict(type=-1)] * 4):
        if s["type"] < 0:
            rows.append("-")
            continue
        d = s["day"]
        tiles = [(t[0] - ox, t[1] - oy) if t else None for t in s["tiles"]]
        rows.append((s["type"], ((d // 16) % 12, d % 16), len(s["tiles"]), s["next"], int(s["visited"]), tiles))
    return rows


def ours(kind, until):
    sys.path.insert(0, ROOT)
    from sim.game import Game
    g = Game("sandbox", 1)
    tpd = g.rules["ticks_per_day"]
    if kind == "god":
        g.command("jealous 1")
    if kind == "monster":
        from sim.heroes import events as hev
        ev = hev.records(g)[1]                    # the Maenads (oracle_heroes.py hero_poke: +0x14 year 0, +3 month 0)
        ev["year"], ev["month"] = 0, 0
    if kind == "land":                            # spawned in run_day of the change to February (oracle_invasion)
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import oracle_invasion
        oracle_invasion.arm(g, "land")
    prev = None
    while g.tick <= until:
        rows = ours_rows(g)
        if rows != prev:
            print(g.tick, g.year, g.month, g.day % 16, rows)
            prev = rows
        g.step(1)


ROUND0, ROUND_STEP, ROUNDS, FINAL = 300, 150, 7, 1350
RATE, T60 = 8.54, 125                       # ticks per virtual second after the start, the tick at 60 s (run 1D-alerts)


def sec(tick):
    return round(60 + (tick - T60) / RATE, 1)


def poke():
    """re/oracle/scenarios/alerts.txt: the slots set directly. Rounds r = 0..6 at ticks 300 + 150 r: slot 0 type r,
    slot 1 7 + r % 2, slot 2 9 + r % 3, slot 3 12 + r % 3, dated year 30000 (never more than 8 days old), one tile
    each (logical (100 + 10 k, 120)). At tick 1350 (day 26 = February 10): slots 0 (fire) and 1 (disease) dated today
    (more than 8 days old from day 35, tick 1785: slot 1 clears, slot 0 stays while the mouse rests on it), slot 2 an
    invasion with 2 tiles (148, 190) and (121, 200) dated year 30000 (clicked twice), slot 3 empty."""
    out = []

    def put(t, k, typ, ymd, tiles):
        a = SLOTS + k * SZ
        out.append(f"{t} {a + 4:x} 4 {typ}")
        if typ < 0:
            out.append(f"{t} {a + 0x64:x} 4 0")
            return
        y, m, d = ymd
        out.extend([f"{t} {a + 8:x} 4 {y}", f"{t} {a + 0xC:x} 4 {m}", f"{t} {a + 0x10:x} 4 {d}",
                    f"{t} {a + 0x64:x} 4 {len(tiles)}", f"{t} {a + 0x68:x} 4 0", f"{t} {a + 0x6C:x} 1 0"])
        for i, (x, yy) in enumerate(tiles):     # DAT_00DA2F80 = 229 in the sandbox (logical (1, 1) offset)
            out.append(f"{t} {a + 0x14 + 4 * i:x} 4 {229 + yy * 0xE4 + x}")

    for r in range(ROUNDS):
        t = ROUND0 + ROUND_STEP * r
        for k, typ in enumerate((r, 7 + r % 2, 9 + r % 3, 12 + r % 3)):
            put(t, k, typ, (30000, 0, 0), [(100 + 10 * k, 120)])
    t, d = FINAL, FINAL // 51
    put(t, 0, 0, (-1000, d // 16, d % 16), [(100, 120)])
    put(t, 1, 7, (-1000, d // 16, d % 16), [(110, 120)])
    put(t, 2, 9, (30000, 0, 0), [(148, 190), (121, 200)])
    put(t, 3, -1, None, [])
    return "\n".join(out)


def script(width):
    """The run's script: Open Play Sandbox (sandbox-start.txt), at 1024 wide Options > Display > 1024x768
    (balloons-worldmap.txt); the first messages closed with their OK button; per round the mouse on each slot (shot
    DIR/r<r>_<k>.bmp) and on the map (DIR/r<r>_n.bmp); the final round: a shot, slot 2 held (r7_held), let go
    (r7_up, r7_up2) and once more (r7_b, r7_b2); the mouse on slot 0 from tick ~1620 (r7_hold before, r7_late after
    tick 1785), away (r7_gone). Every shot's tick is in the run's stderr (pick by tick, not by name)."""
    px, ok = (598, (568, 574)) if width == 800 else (838, (808, 740))
    sx = [px + 26 + 34 * k for k in range(4)]
    a = ["5:key 27", "12:click 220,101", "17:char 78", "20:click 556,320", "27:click 590,256", "31:click 120,306",
         "33:click 315,442", "38:click 656,491", "46:rclick 300,300"]
    if width == 1024:
        a += ["48:move 568,574", "48.3:down 568,574", "48.6:up 568,574", "50:click 90,10", "52:click 120,41",
              "55:click 320,253"]
    a += [f"{t}:click {ok[0]},{ok[1]}" for t in (57, 59, 61, 63)]
    for r in range(ROUNDS):
        b = sec(ROUND0 + ROUND_STEP * r) + 3
        for k in range(4):
            a += [f"{b + 2 * k:.1f}:move {sx[k]},494", f"{b + 2 * k + 1.5:.1f}:shot DIR/r{r}_{k}.bmp"]
        a += [f"{b + 8:.1f}:move 300,300", f"{b + 9.5:.1f}:shot DIR/r{r}_n.bmp"]
    b = sec(FINAL) + 3
    a += [f"{b:.1f}:shot DIR/r7_n.bmp", f"{b + 1:.1f}:move {sx[2]},494", f"{b + 2:.1f}:down {sx[2]},494",
          f"{b + 2.3:.1f}:shot DIR/r7_held.bmp", f"{b + 2.6:.1f}:up {sx[2]},494", f"{b + 2.65:.1f}:shot DIR/r7_up.bmp",
          f"{b + 4:.1f}:shot DIR/r7_up2.bmp", f"{b + 6:.1f}:down {sx[2]},494", f"{b + 6.3:.1f}:up {sx[2]},494",
          f"{b + 6.35:.1f}:shot DIR/r7_b.bmp", f"{b + 8:.1f}:shot DIR/r7_b2.bmp", f"{b + 9:.1f}:move 300,300",
          f"{b + 10:.1f}:shot DIR/r7_b3.bmp"]
    h0, h1 = sec(1620), sec(1785)
    a += [f"{h0:.1f}:move {sx[0]},494", f"{h1 - 2:.1f}:shot DIR/r7_hold.bmp", f"{h1 + 6:.1f}:shot DIR/r7_late.bmp",
          f"{h1 + 8:.1f}:move 300,300", f"{h1 + 10:.1f}:shot DIR/r7_gone.bmp"]
    a.sort(key=lambda s: float(s.split(":")[0]))
    return "; ".join(a)


def bal_poke():
    """re/oracle/scenarios/alerts-balloon.txt ("See a working city", where the panel's balloons show): at tick 5
    slot 0 = type 6 (blocked road), slot 1 = type 8 (plague), dated year 30000, one tile each."""
    out = []
    for k, typ in ((0, 6), (1, 8)):
        a = SLOTS + k * SZ
        out += [f"5 {a + 4:x} 4 {typ}", f"5 {a + 8:x} 4 30000", f"5 {a + 0xC:x} 4 0", f"5 {a + 0x10:x} 4 0",
                f"5 {a + 0x14:x} 4 27589", f"5 {a + 0x64:x} 4 1", f"5 {a + 0x68:x} 4 0"]
    return "\n".join(out)


def main(a):
    if a[:1] == ["--exe"]:
        return exe(a[1])
    if a[:1] == ["--ours"]:
        return ours(a[1], int(a[2]) if len(a) > 2 else 3000)
    if a[:1] == ["--poke"]:
        return print(poke())
    if a[:1] == ["--bal-poke"]:
        return print(bal_poke())
    if a[:1] == ["--script"]:
        return print(script(int(a[1])))
    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
