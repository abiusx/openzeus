"""Print the military state of oracle dumps (docs/re/oracle.md): companies (figure_groups 0x00DB7B40, 0x9C each)
and the figures of military / wolf types (g_figures 0x00DBD788, 0x184 each, 2000).

    python3 tools/oracle_military.py re/oracle/runs/RUN/dump/tick_000100.bin [...]
    python3 tools/oracle_military.py --track TYPE[,TYPE] DUMP...     one line per figure per dump (x y action)

Types: 0xB rabble, 0xC hoplite, 0xD horseman, 0x27 wall sentry, 0x28..0x2A enemies, 0x2D/0x34 missiles,
0x2E tower sentry, 0x3B wolf, 0x1E shepherd, 0x1F goatherd, 0x31 sheep, 0x32 goat, 0x35 hunter.
Positions are the exe's logical coordinates: ours (raw) = + World.origin ((1, 1) on the sandbox; map-terrain.md
"Logical and raw coordinates").
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle import Dump  # noqa: E402

FORM, FSZ = 0x00DB7B40, 0x9C
FIG, GSZ = 0x00DBD788, 0x184
MIL = {0xB, 0xC, 0xD, 0x27, 0x28, 0x29, 0x2A, 0x2D, 0x2E, 0x34, 0x3B}


def fig(d, i):
    a = FIG + i * GSZ
    r = lambda off, f: d.at(a + off, f)
    return dict(id=i, state=r(0x0E, '<B'), type=r(0x0A, '<B'), x=r(0x14, '<h'), y=r(0x16, '<h'),
                action=r(0x38, '<B'), dir=r(0x11, '<b'), prog=r(0x39, '<b'), timer=r(0x36, '<h'),
                form=r(0x60, '<h'), slot=r(0x62, '<B'), damage=r(0x98, '<h'), hidden=r(0x65, '<B'),
                dest=(r(0x24, '<h'), r(0x26, '<h')), sprite=r(0x04, '<I'), frame=r(0x01, '<B'),
                opp=r(0x90, '<h'), target=r(0x82, '<h'), bld=r(0x5A, '<h'), link=r(0x5C, '<H'))


def form(d, i):
    a = FORM + i * FSZ
    r = lambda off, f: d.at(a + off, f)
    return dict(id=i, in_use=r(0, '<B'), type=r(4, '<h'), n=r(0x28, '<B'), layout=r(0x2A, '<h'),
                morale=r(0x2C, '<h'), x=r(0x2E, '<h'), y=r(0x30, '<h'), dest=(r(0x32, '<h'), r(0x34, '<h')),
                home=(r(0x36, '<h'), r(0x38, '<h')), standard=r(0x40, '<h'), all_home=r(3, '<B'),
                facing=r(0x6B, '<B'), away=r(0x82, '<h'), mob=r(0x90, '<B'), mode=r(0x91, '<B'),
                sel=r(0x92, '<B'), ready=r(0x93, '<B'), herd=r(0x69, '<B'), members=[r(8 + 2 * k, '<h') for k in range(8)])


def main(argv):
    track = None
    if argv and argv[0] == '--track':
        track = {int(t, 16) for t in argv[1].split(',')}
        argv = argv[2:]
    for p in argv:
        d = Dump(p)
        tick = os.path.basename(p)
        if track:
            for i in range(1, 2000):
                f = fig(d, i)
                if f['state'] == 1 and f['type'] in track:
                    print(tick, f['id'], hex(f['type']), f['x'], f['y'], 'act', hex(f['action']), 'dir', f['dir'],
                          'prog', f['prog'], 'form', f['form'], f['slot'], 'dmg', f['damage'], 'dest', f['dest'],
                          'hid', f['hidden'], 'spr', hex(f['sprite']), 'fr', f['frame'], 'opp', f['opp'], 'tmr', f['timer'])
            continue
        print('==', tick)
        for i in range(1, 100):
            g = form(d, i)
            if g['in_use']:
                print(' company', g)
        for i in range(1, 2000):
            f = fig(d, i)
            if f['state'] == 1 and f['type'] in MIL:
                print(' fig', f)


if __name__ == '__main__':
    main(sys.argv[1:])
