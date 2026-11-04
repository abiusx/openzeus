"""Arrow pictures (docs/logic/military.md "Arrow 0x2D"): the exe's sprite of a sentry / tower arrow (0x2D,
walker_player_missile 0x004BACE0) and of an enemy archer's arrow (0x34, fig_handler_enemy_missile 0x004BD970) for
every direction +0x11 and view, against ours (viewer/play/scene.js drawArrow, `arrow_index` here).

    python3 tools/oracle_arrows.py --poke > DIR/poke.txt      # the ZEUS_POKE file (re/oracle/scenarios/arrows.txt)
    python3 tools/oracle_arrows.py [RUN]                      # check (default re/oracle/runs/1D-arrows)

The poke ("See a working city", tick 59): 4 x 32 arrows in free figure slots 1500..1627 at logical (10, 10) (an
empty tile; tile index 12366 = x + 228 y + 10076), each flying toward (30, 30) (line fields as figure_line_move_init:
the first tile change after 15 sub-steps, the fourth call), +0x11 = 0..31: slots 1500.. shot by a tower sentry
(figure 1700: type 0x2E, state 0 so its own handler never runs; the arrow handler only drops an arrow whose shooter is
in state 2), 1532.. 0x34 by an enemy archer (1701, type 0x28) of company 90 (army_nation +0x6A = 1), 1564.. by 1702
of company 91 (nation 2), 1596.. by 1703 of company 92 (nation 0). The view 0x00DA2F88 is poked to 0 / 2 / 4 / 6 at
ticks 60 / 62 / 64 / 66 (written at the tick's entry); dump t (every tick 59..68) holds each arrow's sprite (+0x04)
and shadow (+0x180) computed in tick t - 1, with the view of dump t - 1.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

FIG, FSZ, FORM, FOSZ = 0x00DBD788, 0x184, 0x00DB7B40, 0x9C
VIEW = 0x00DA2F88
T0 = 59
X, Y, TILE = 10, 10, 12366
SHOOTERS = [(1700, 0x2E, 0, 0x2D), (1701, 0x28, 90, 0x34), (1702, 0x28, 91, 0x34), (1703, 0x28, 92, 0x34)]
NATION = {90: 1, 91: 2, 92: 0}
VIEWS = [(60, 0), (62, 2), (64, 4), (66, 6)]


def poke():
    out = ["# arrows of every direction for 4 shooters (tools/oracle_arrows.py --poke)"]
    p = lambda a, n, v: out.append(f"{T0} {a:x} {n} {v & ((1 << (8 * n)) - 1)}")
    for f, n in NATION.items():
        p(FORM + f * FOSZ + 0x6A, 1, n)
    for k, (s, typ, form, missile) in enumerate(SHOOTERS):
        b = FIG + s * FSZ
        p(b + 0x0A, 1, typ)
        p(b + 0x0E, 1, 0)
        p(b + 0x60, 2, form)
        p(b + 0x14, 2, X)
        p(b + 0x16, 2, Y)
        for d in range(32):
            a = FIG + (1500 + 32 * k + d) * FSZ
            for off, n, v in ((0x0A, 1, missile), (0x0E, 1, 1), (0x11, 1, d), (0x14, 2, X), (0x16, 2, Y),
                              (0x1C, 1, 10), (0x20, 4, TILE), (0x39, 1, 15), (0x4A, 2, X * 15), (0x4C, 2, Y * 15),
                              (0x4E, 2, (X + 20) * 15), (0x50, 2, (Y + 20) * 15), (0x52, 2, 300), (0x54, 2, 300),
                              (0x56, 2, 0), (0x58, 1, 1), (0x5A, 2, s), (0x78, 1, 18), (0x08, 2, 0)):
                p(a + off, n, v)
    for t, v in VIEWS:
        out.append(f"{t} {VIEW:x} 4 {v}")
    return "\n".join(out)


def arrow_index(d32, view):
    """Ours (scene.js drawArrow): the picture of a 32-direction arrow group, ((d32 - 4 view) mod 32 - 13) & 31."""
    return (((d32 - 4 * view) & 31) - 13) & 31


def groups():
    """(start, shadow, dirs) per poked shooter: ours' group (sim defences.arrow_group for that shooter) in
    data/play/military.json (tools/play_military.py), as scene.js drawArrow picks it."""
    import json
    from types import SimpleNamespace as NS
    sys.path.insert(0, ROOT)
    from sim.military import defences
    m = json.load(open(os.path.join(ROOT, "data", "play", "military.json")))
    blk = {"a79": m["arrow"], "a71": m["enemy_arrows"]["1"], "a51": m["enemy_arrows"]["0"]}
    g = NS(poseidon=False)
    kinds = [("arrow", NS(role="tower_sentry")), ("enemy_arrow", NS(role="enemy_archer", army=1)),
             ("enemy_arrow", NS(role="enemy_archer", army=2)), ("enemy_arrow", NS(role="enemy_archer", army=0))]
    out = {}
    for k, (role, sh) in enumerate(kinds):
        b = blk[defences.arrow_group(g, NS(role=role), sh)]
        out[k] = (b["start"], b["shadow"], b["dirs"])
    return out


def check(run):
    from oracle import Dump, dump_files
    G = groups()
    n = bad = 0
    view = None
    for f in dump_files(os.path.join(run, "dump")):
        t = int(os.path.basename(f)[5:11])
        d = Dump(f)
        pv, view = view, d.at(VIEW, "<i")        # the sprites in dump t come from tick t - 1: its view
        if t <= T0 + 1 or pv is None:
            continue
        for k in range(4):
            start, shadow, dirs = G[k]
            for dd in range(32):
                a = FIG + (1500 + 32 * k + dd) * FSZ
                if d.at(a + 0x0E, "<B") != 1:
                    continue
                d32 = d.at(a + 0x11, "<b")
                # the exe's image number (low 18 bits; file in the high bits) is ours - 1 (the atlas counts from 1)
                spr, ext = (d.at(a + 0x04, "<I") & 0x3FFFF) + 1, (d.at(a + 0x180, "<I") & 0x3FFFF) + 1
                i = arrow_index(d32, pv) if dirs > 1 else 0
                ok = spr == start + i and ext == shadow + i
                n += 1
                if not ok:
                    bad += 1
                    if bad <= 20:
                        print(f"tick {t} view {pv} shooter {k} dir {d32}: exe {spr} / {ext}, "
                              f"ours {start + i} / {shadow + i}")
    print(f"{n} arrow pictures compared, {bad} differ")
    return bad


def main(argv):
    if argv[:1] == ["--poke"]:
        print(poke())
        return 0
    return 1 if check(argv[0] if argv else os.path.join(ROOT, "re/oracle/runs/1D-arrows")) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
