"""Exact fast paths for random.Random.randrange(k) (performance round 3, docs/sim-design.md "Performance").

CPython's randrange(k) for one positive int argument is _randbelow_with_getrandbits(k): getrandbits(k.bit_length())
until the draw is below k. below() and below_sum() make the same getrandbits calls without randrange's three
Python frames, so the generator's stream and every result stay identical. They are used only when this module
proves that on the running interpreter (EXACT); otherwise they fall back to randrange.
"""
import random


def _below_fast(rng, k):
    bits, gb = k.bit_length(), rng.getrandbits
    r = gb(bits)
    while r >= k:
        r = gb(bits)
    return r


def _below_sum_fast(rng, k, n):
    bits, gb, total = k.bit_length(), rng.getrandbits, 0
    for _ in range(n):
        r = gb(bits)
        while r >= k:
            r = gb(bits)
        total += r
    return total


def _below_ref(rng, k):
    return rng.randrange(k)


def _below_sum_ref(rng, k, n):
    rr = rng.randrange
    return sum(rr(k) for _ in range(n))


def _exact():
    if random.Random._randbelow is not random.Random._randbelow_with_getrandbits:
        return False
    for k in (1, 2, 3, 5, 7, 8, 9, 103, 1 << 15):
        a, b = random.Random(k), random.Random(k)
        if [_below_fast(a, k) for _ in range(40)] != [b.randrange(k) for _ in range(40)] \
                or _below_sum_fast(a, k, 40) != _below_sum_ref(b, k, 40) or a.getstate() != b.getstate():
            return False
    return True


EXACT = _exact()
below = _below_fast if EXACT else _below_ref                  # == rng.randrange(k), k > 0
below_sum = _below_sum_fast if EXACT else _below_sum_ref      # == sum(rng.randrange(k) for n draws)
