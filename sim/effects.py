"""Effect figures (the exe's figure type 6: dust, splashes, spray) as presentation (docs/play/walkers.md "Effect
figures"). The exe makes them only on screen (FUN_004104D0) and deletes them off screen, so they are not game
state here: a spawner call is reported to the live recorder (frame `fx`, like walkers.sfx) and play mode makes and
animates the figures (viewer/play/effects.js, data/play/walkers.json `effects`). No RNG is drawn in the sim.
"""


def _out(g):
    return g.__dict__.get("fx")


def debris(g, x, y, size=1):
    """collapse_debris_spawn(x, y, size, ...) 0x004CCD40: dust clouds over a size x size area (the tile's 4 corners x
    3 directions for size 1; for a bigger area each tile with rng & 3 == 0, else one random tile)."""
    out = _out(g)
    if out is not None:
        out.append([g.tick, "debris", int(x), int(y), int(size)])


def splash(g, kind, x, y, fx, fy, variant):
    """A standing picture on tile (x, y) at fine (fx, fy) (of 15 a tile; may be just outside it), height 10
    (FUN_004104D0(type, x, y, fx, fy, 10, 0, 0, 0, variant)): "lava" = subtype 1 (FUN_00411920: 0x220B + variant,
    rng % 6), "spray" = subtype 4 (FUN_00412080: 0x2236 frames 1..9, then 0x2238 0..9; variant 0)."""
    out = _out(g)
    if out is not None:
        out.append([g.tick, kind, int(x), int(y), int(fx), int(fy), int(variant)])


def drops(g, x, y, angle, speed, variant):
    """Subtype 2 (FUN_00411BE0, the lava's random ring): FUN_004104D0(2, x, y, 8, 8, 4, angle, speed, 0, variant):
    from the tile's middle, height 4, drifting along angle (0..255) at speed 0 / 1 (flags 1: the sin / cos tables of
    FUN_00410430 x speed / 32 a tick, in 1/120 tile); 0x2211 + variant, 12 / 13 / 15 / 15 frames, 1 tick each."""
    out = _out(g)
    if out is not None:
        out.append([g.tick, "drops", int(x), int(y), int(angle), int(speed), int(variant)])
