"""Monthly god update (gods_month_update 0x004E69A0, month_tick 5), jealousy (jealousy_update 0x004F0B50) and
the curse timers (curse_timers_decay 0x004E5EB0, every month_advance call). docs/logic/religion.md."""
from . import T, state, rec, rng, sanctuary, built, can_be_jealous, GODS, NAMES


def update(g):
    st = state(g)
    for i in range(14):
        month_tick(g, i)
    jealousy(g)
    # help candidate: a random friendly god (scenario slots 12..23) with a built sanctuary
    cands = [gid for s, gid in _slots(g) if s >= 12 and gid >= 0 and built(g, gid)]
    st["help_cand"] = -1
    if cands:
        i = cands[rng(g).randrange(128) % len(cands)]                  # rng_7 % n
        from .help import can_help
        if can_help(g, i):
            st["help_cand"] = i


def _slots(g):
    st = state(g)
    return sorted((r["slot"], i) for i, r in enumerate(st["rec"]) if r["slot"] >= 0)


def month_tick(g, i):
    """god_month_tick 0x004E6160: counters -1, pending prayer months, the passive monthly effects."""
    r = rec(g, i)
    r["prayer"] = max(0, r["prayer"] - 1)
    r["oracle"] = max(0, r["oracle"] - 1)
    if not r["pending"]:
        r["pending_months"] = 0
    else:
        if r["pending_months"] > 2:
            r["pending_months"] = 1
        r["pending_months"] -= 1
        if r["pending_months"] < 1:
            r["pending"] = 0
    if not built(g, i):
        return
    if i == 0:                                   # Zeus: world cities' relation +1 (0x004E6230)
        _zeus_relations(g)
    elif i in (1, 11):                           # Poseidon's Kraken / Hades' Cerberus (track 1I: monsters)
        _guardian(g, i)
    elif i == 8:                                 # Athena fights an invasion (0x004E6340)
        from . import figures
        figures.athena_month(g)
    elif i == 3:                                 # Apollo fights a monster near his sanctuary (0x004E6440)
        from . import figures
        figures.apollo_month(g)


def _zeus_relations(g):
    """0x004E6230: each of the 22 world cities with byte +0 set and attitude (+0x164) < 100 gets +1. Ours: every
    city but the player's (byte +0 not identified)."""
    emp = getattr(g, "empire", None)
    if emp is None:
        return
    for c in emp.cities.values():
        if c.kind != "player" and c.attitude < 100:
            c.attitude += 1


def _guardian(g, i):
    """Poseidon (0x004E6260): monster 1 (Kraken), Hades (0x004E62D0): monster 2 (Cerberus), when the sanctuary's flag
    +0xC4&8 (guardian killed) is clear and the monster is not on the map: sim/heroes (track 1I) spawns it."""
    from .. import heroes
    heroes.guardian(g, i, sanctuary(g, i))


def jealousy(g):
    """jealousy_update 0x004F0B50: countdown (u8) -1 below 13, else re-rolled 6..12; at 0 with at most 3
    sanctuaries placed, a weighted draw among the gods that may be jealous; the god attacks if it gets an attack
    slot (god_attack_slot_assign 0x00587390), then the countdown is re-rolled."""
    st = state(g)
    if st.get("free"):
        return
    c = st["jealousy"]
    if c < 13:
        c = (c - 1) & 0xFF
    else:
        c = rng(g).randrange(32768) % 7 + 6
    st["jealousy"] = c
    if c != 0:
        return
    from . import count_sanctuaries
    if count_sanctuaries(g) > 3:                 # sanctuaries_more_than_3
        return
    wts = T()["jealousy_weight"]
    w = [wts[i] + 1 if can_be_jealous(g, i) else 0 for i in range(14)]
    tot = sum(w)
    if not tot:
        return
    r = rng(g).randrange(128) % tot + 1          # rng_7 % sum + 1
    pick = -1
    for i in range(14):
        if w[i]:
            r -= w[i]
            if r < 1:
                pick = i
                break
    if pick < 0 or not attack_slot(g, pick):
        return
    from . import figures
    figures.attack_start(g, pick)
    st["jealousy"] = rng(g).randrange(32768) % 7 + 6


def attack_slot(g, i):
    """god_attack_slot_assign 0x00587390: 4 on-screen 'god attacking' slots per side (friendly gods among scenario
    slots 12..17, unfriendly among 0..3); a god already holding a slot keeps it; False when all 4 are taken."""
    from . import figures
    st = state(g)
    r = st["rec"][i]
    if r["unfriendly"] == 0:
        side = [gid for s, gid in _slots(g) if 12 <= s < 18]
    else:
        side = [gid for s, gid in _slots(g) if 0 <= s < 4]
    if i not in side:
        return False
    used = {}
    for gid in side:
        figures.figure(g, gid)                   # god_figure_get: clears the slot of a god whose figure is gone
        a = st["rec"][gid]["attack_slot"]
        if 0 <= a < 4:
            if a not in used:
                used[a] = gid
            else:
                st["rec"][gid]["attack_slot"] = -1
    for k in range(4):
        if used.get(k, i) == i:
            r["attack_slot"] = k
            return True
    return False


def curse_decay(g):
    """curse_timers_decay 0x004E5EB0: every non-zero entry of g_type_curse -1 per month_advance call
    (g_production_stop is entry 179 of the same table)."""
    st = state(g)
    c = st["curse"]
    for k in list(c):
        c[k] -= 1
        if c[k] <= 0:
            del c[k]
    if st["stop"] > 0:
        st["stop"] -= 1


def curse(g, i, zid):
    """god_curse_building 0x004ED2A0's effect: g_type_curse[type] = curse months (0x0063AEAC[god*5 + difficulty])
    << 4, i.e. in month_advance calls."""
    from ..data import DIFFICULTIES
    d = DIFFICULTIES.index(g.rules.get("difficulty", "Normal")) if g.rules.get("difficulty", "Normal") in DIFFICULTIES else 2
    n = T()["curse_months"][i][d] << 4
    if n > 0:
        state(g)["curse"][zid] = n
    return n


def log(g, text):
    st = state(g)
    st["log"].append((g.tick, text))
    del st["log"][:-300]


__all__ = ["update", "jealousy", "curse_decay", "curse", "NAMES"]
