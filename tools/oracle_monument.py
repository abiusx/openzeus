"""Timeline of a monument being built in an oracle run (docs/logic/monuments.md "Oracle").

Usage: python3 tools/oracle_monument.py RUN_DIR FIRST_PIECE LAST_PIECE [--every N]
       python3 tools/oracle_monument.py --poke OUT FIRST_PIECE LAST_PIECE BAY...   the ZEUS_POKE file that resets the
       pieces to stage 0 (materials, counters and the root's complete flag cleared) and fills the given storehouse
       bays with 400 marble each, at simulation tick 3 (re/oracle/scenarios/sanctuary-build.txt: 395 423 63..68 76..85)
       python3 tools/oracle_monument.py --complete OUT KEY ROOT TICK   the ZEUS_POKE file that sets every piece of the
       composite KEY (data/monuments.json) placed at building index ROOT (the layout's pieces of class < 1000 in order:
       piece j at ROOT + j, +0x12 = j; the extras classes >= 1000 have no record) to its last
       stage at tick TICK, so the next completion pass (cycle step 32) completes it and applies its extras
       (re/oracle/scenarios/e1-sanct-*.txt)
Prints, for each dump: the stage of every piece (+0x58), the root's complete flag (+0x68), materials held per
piece (+0x70 wood, +0x74 marble, +0x78 sculpture), and the figures working for it: artisans (type 0x3A) and
cart pushers (type 4) whose destination (+0x5E) is one of the pieces: id, tile, action (+0x38), resource (+0x0B),
amount (+0x74).
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402
from oracle import Dump  # noqa: E402

BUILDINGS, BREC = 0x0092E658, 0x118
FIGURES, FREC = 0x00DBD788, 388


def snapshot(d, lo, hi):
    def b(i, o, f='<h'):
        return d.at(BUILDINGS + i * BREC + o, f)
    pieces = {i: dict(stage=b(i, 0x58, '<i'), wood=b(i, 0x70, '<i'), marble=b(i, 0x74, '<i'),
                      sculpture=b(i, 0x78, '<i'), x=b(i, 6), y=b(i, 8)) for i in range(lo, hi + 1)}
    figs = []
    for k in range(1, 2000):
        a = FIGURES + k * FREC
        if not d.at(a + 0x0E, '<B'):
            continue
        t = d.at(a + 0x0A, '<B')
        dest = d.at(a + 0x5E, '<h')
        if t == 0x3A or (t == 4 and lo <= dest <= hi) or t == 0x1C:
            figs.append(dict(id=k, type=t, x=d.at(a + 0x14, '<h'), y=d.at(a + 0x16, '<h'), action=d.at(a + 0x38, '<B'),
                             dest=dest, res=d.at(a + 0x0B, '<B'), amount=d.at(a + 0x74, '<h'),
                             home=d.at(a + 0x5A, '<h')))
    return dict(pieces=pieces, complete=b(lo, 0x68, '<B'), figures=figs)


def poke_file(out, lo, hi, bays, tick=3):
    lines = ["# reset the monument pieces %d..%d to stage 0 and stock marble (tools/oracle_monument.py --poke)" % (lo, hi)]
    for i in range(lo, hi + 1):
        a = BUILDINGS + i * BREC
        lines.append(f"{tick} {a + 0x58:x} 4 0")
        for off in (0x70, 0x74, 0x78, 0xAC, 0xC0, 0xA4, 0xB0, 0xA8, 0x60):     # held, reservations, work counters
            lines.append(f"{tick} {a + off:x} 4 0")
    lines.append(f"{tick} {BUILDINGS + lo * BREC + 0x68:x} 1 0")
    for i in bays:
        a = BUILDINGS + i * BREC
        lines += [f"{tick} {a + 0x12:x} 2 11", f"{tick} {a + 0x3C:x} 2 400"]
    open(out, "w").write("\n".join(lines) + "\n")


def complete_file(out, key, root, tick):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from sim.systems import monuments as M
    lay = M.layouts()[key]
    with open(out, "w") as f:
        f.write(f"# {key}: every piece to its last stage (stages(class, elev)) at tick {tick}\n")
        for i, (dx, dy, c, e) in enumerate(p for p in lay["pieces"] if p[2] < 1000):
            f.write(f"{tick} {BUILDINGS + (root + i) * BREC + 0x58:x} 4 {len(M.stages(c, e))}\n")


def main():
    if sys.argv[1] == "--complete":
        return complete_file(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]))
    if sys.argv[1] == "--poke":
        bays = []
        for a in sys.argv[5:]:
            x, _, y = a.partition("..")
            bays += list(range(int(x), int(y or x) + 1))
        return poke_file(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), bays)
    run, lo, hi = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    every = int(sys.argv[sys.argv.index('--every') + 1]) if '--every' in sys.argv else 1
    files = oracle.dump_files(os.path.join(run, "dump"))[::every]
    for f in files:
        s = snapshot(Dump(f), lo, hi)
        st = ''.join(str(min(9, p['stage'])) for p in s['pieces'].values())
        held = {i - lo: (p['wood'], p['marble'], p['sculpture']) for i, p in s['pieces'].items()
                if p['wood'] or p['marble'] or p['sculpture']}
        figs = ' '.join(f"{'A' if q['type'] == 0x3A else 'C' if q['type'] == 4 else 'h'}{q['id']}@{q['x']},{q['y']}"
                        f"a{q['action']}->{q['dest'] - lo if lo <= q['dest'] <= hi else q['dest']}"
                        + (f"r{q['res']}x{q['amount']}" if q['type'] == 4 else '') for q in s['figures'])
        print(os.path.basename(f)[5:11], st, 'C' if s['complete'] else '-', held or '', figs)


if __name__ == '__main__':
    main()
