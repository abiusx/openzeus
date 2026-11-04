"""Migration and overcrowding (docs/logic/population.md, simplified)."""
import math

from . import housing, health


def migration_rate(g):
    s = g.city.sentiment
    for threshold, rate in g.rules["migration"]:
        if s >= threshold:
            return rate
    return g.rules["migration"][-1][1]


def update(g):
    migrate(g)
    evict(g)


def evict(g):
    """Cycle step 24, house_evict_overcrowded 0x004871B0 (after a devolve): the surplus walks out homeless."""
    hs = housing.houses(g)
    for b in hs:
        cap = housing.capacity(g, b)
        if b.occupants > cap and not b.misc.get("infected"):     # infected: room = 0 (house_room_update 0x004860A0)
            out = b.occupants - cap
            b.occupants = cap
            from . import walkers
            walkers.spawn_homeless(g, b, out)
            g.message(f"{out} people evicted from an overcrowded house at ({b.x},{b.y})")
    _recount(g, hs)


def migrate(g):
    """Cycle step 23, city_population_update 0x00486190: immigration / emigration waves."""
    c = g.city
    hs = housing.houses(g)
    rate = migration_rate(g)
    c.migration = rate
    # migration_rate_update 0x00567450: a switch of direction waits 2 passes (cooldowns); dues under 4 accumulate
    st = g.sd("migration_state", dict(imm_cd=0, emig_cd=0, pend_in=0, pend_out=0))
    from . import walkers
    if rate > 0:
        if st["imm_cd"]:
            st["imm_cd"] -= 1
            return _recount(g, hs)
        st["emig_cd"] = 2
        n = math.ceil(rate * 12 / 100)
        if n < 4:
            st["pend_in"] += n
            n, st["pend_in"] = (st["pend_in"], 0) if st["pend_in"] >= 4 else (0, st["pend_in"])
        # send_immigrants 0x00486860: pass A empty houses (4 each), B room > 7 (4 each), C any room (up to the
        # room); one walker on the way per house
        left = n
        for cond, per in ((lambda b, r: b.occupants == 0, 4), (lambda b, r: r > 7, 4), (lambda b, r: True, None)):
            for b in hs:
                if left <= 0:
                    break
                if b.access is None or b.pending or b.misc.get("infected"):
                    continue
                room = housing.capacity(g, b) - b.occupants
                if room > 0 and cond(b, room):
                    k = min(left, per or room)
                    walkers.spawn_immigrant(g, b, k)
                    left -= k
        c.immigrants_month += n - left          # 0x00FE9194 += settled: counted when they set out (bugs.md 282)
    elif rate < 0:
        if st["emig_cd"]:
            st["emig_cd"] -= 1
            return _recount(g, hs)
        if c.population <= 100:
            return _recount(g, hs)
        st["imm_cd"] = 2
        n = math.ceil(-rate * 12 / 100)
        if n < 4:
            st["pend_out"] += n
            n, st["pend_out"] = (st["pend_out"], 0) if st["pend_out"] >= 4 else (0, st["pend_out"])
        if n and not health.sanctuary_done(g, "aphrodite"):       # 0x00486AB0: Aphrodite stops emigration
            # send_emigrants: lowest house level first, then list order, at most 4 per house
            for b in sorted(hs, key=lambda b: (b.level, b.id)):
                if n <= 0:
                    break
                k = min(b.occupants, 4, n)
                b.occupants -= k
                n -= k
                c.emigrants_month += k
                if k:
                    walkers.spawn_emigrant(g, b, k)
    _recount(g, hs)


def _recount(g, hs):
    g.city.population = sum(b.occupants for b in hs)
