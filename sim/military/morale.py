"""Company morale (formation +0x2C), both sides (docs/logic/military.md "Morale").

- formation_morale_add 0x004DE080: + delta, clamped 0..100; companies with +0x94 (event aid troops, sanctuary troops)
  never change.
- formation_member_lost 0x004DDFF0 (figure_hit and the other killers, right after the hit): formations_refresh first
  (+0x28 = the company's figures with state 1: the dying ones and the one just hit count, the ones at home too), then
  LOSS[+0x28 - 1] (clamped to 0..7).
- formations_morale_waver 0x004DDF20 (formations_update(0), cycle step 5), formations 1..99 by index, not herds
  (+0x69), not +0x94: a palace company (+0x42 = 1) on the map (+0x03 all_home 0) and not away (+0x82 < 0), or any
  other company (+0x42 = 0: the invaders), with morale < 21: the first time (+0x66 and +0x73 both 0) the other side's
  companies + 3 (FUN_004DE0E0: +0x42 != 0; FUN_004DE120: +0x42 == 0, +0x94 == 0) and its own side's - 3; then +0x73 + 1
  (morale < 11) or +0x66 + 1 (11..20).
- The counters' readers: the invaders' AI (enemy_company_ai_update 0x004FFF10: either nonzero -> every member action 3,
  leave the map; morale_check / go_attack give orders only while +0x73 == 0 and +0x66 < 2). A palace company's
  counters are read by nobody: fig_handler_standard 0x004B3E00 resets them with its peace +80. A palace company never
  routs (+0x93 is only ever written 1; oracle 1B-inv-city: company 1 at morale 0 fights to its last member).
"""
LOSS = [-30, -30, -30, -25, -18, -12, -8, -5]           # 0x004DDFF0's table, by +0x28 - 1
PLAYER_ROLES = ("rabble", "hoplite", "horseman")


def add(c, d):
    """formation_morale_add 0x004DE080."""
    if c.get("event") or c.get("sanct"):
        return
    c["morale"] = max(0, min(100, c.get("morale", 100) + d))


def member_lost(c, count):
    """formation_member_lost 0x004DDFF0: count = the company's figures with state 1 (+0x28 after the refresh)."""
    add(c, LOSS[max(0, min(7, count - 1))])


def player_count(g, slot, c):
    """+0x28 of a palace company after a death: the soldiers it still has (c["members"], the dead one taken off) plus
    its dying figures (state 1 until removed, the one just hit too)."""
    dying = sum(1 for w in g.walkers.values()
                if w.role in PLAYER_ROLES and w.anim == "die" and getattr(w, "comp", 0) == slot)
    return c["members"] + dying


def enemy_count(g, cid):
    """+0x28 of an invader company: its figures on the map, dying ones included."""
    from .invaders import TYPES
    return sum(1 for w in g.walkers.values() if w.role in TYPES and getattr(w, "company", 0) == cid)


def waver(g):
    """formations_morale_waver 0x004DDF20 (cycle step 5)."""
    from . import forces, invaders
    pal = forces.companies(g)
    ene = invaders.ecomps(g)
    order = sorted([(s, True, c) for s, c in pal.items()] + [(i, False, c) for i, c in ene.items()],
                   key=lambda t: t[0])

    def side(palace, d):                   # FUN_004DE0E0 (palace) / FUN_004DE120 (the rest)
        for _, p, c in order:
            if p == palace:
                add(c, d)
    for s, palace, c in order:
        if c.get("event") or c.get("sanct"):
            continue
        if palace:
            if c.get("away") or not _on_map(g, s):
                continue                   # +0x82 >= 0 (away) or +0x03 = 1 (every member at home)
        m = c.get("morale", 100)
        if m < 21 and not c.get("rout", 0) and not c.get("waver", 0):
            side(not palace, 3)
            side(palace, -3)
        m = c.get("morale", 100)
        if m < 11:
            c["rout"] = (c.get("rout", 0) + 1) & 0xFF        # u8
        elif m < 21:
            c["waver"] = (c.get("waver", 0) + 1) & 0xFF
        if not palace and (c.get("rout") or c.get("waver")):
            c["leave"] = True              # the AI's next update sends every member off (action 3)


def _on_map(g, slot):
    return any(w.role in PLAYER_ROLES and getattr(w, "comp", 0) == slot for w in g.walkers.values())


def refresh(g):
    """formations_refresh 0x004DE210's member lists (cycle step 5 and every formation_member_lost): a company above
    20 has its list (+0x08, 8 ids) rebuilt every time, the figures with state 1 (dying and hidden ones too) in figure
    id order (walkers_update's slot, Walker.fslot), each figure's +0x62 = its index. So the slot is the id rank, not
    the creation order: after a load the ids run downwards (figures_rebuild_free_list), the company's slots reverse at
    its first refresh (oracle 1B-inv-city: 1875 (made last) slot 0). Ours: the invader companies and the aid companies
    (21..30, all members on the map); the palace companies 1..20 (rebuilt only with no enemy units or warships) and
    the sanctuary companies keep their members at home as a count (not figures), so their slots stay as given."""
    from . import invaders, forces
    from .invaders import TYPES
    by = {}
    for w in g.walkers.values():
        if w.role in TYPES:
            by.setdefault(("e", getattr(w, "company", 0)), []).append(w)
        elif w.role in PLAYER_ROLES and 21 <= getattr(w, "comp", 0) <= 30:
            by.setdefault(("p", w.comp), []).append(w)
    for (side, cid), ws in by.items():
        c = (invaders.ecomps(g) if side == "e" else forces.companies(g)).get(cid)
        if c is None:
            continue
        ws.sort(key=lambda w: w.fslot)
        for i, w in enumerate(ws[:8]):
            w.slot = i
        c["ids"] = [w.id for w in ws[:8]]
