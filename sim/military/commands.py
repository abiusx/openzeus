"""CLI verbs of the military module and its play-mode export.

  military [on|off]                  status, or switch the module (off: its walkers vanish, invasions stay abstract)
  companies                          the palace companies: type, soldiers, state, position, mode, morale
  mobilize SLOT|all [X Y]            call to arms (to X Y, else the company's last spot / the palace front)
  move SLOT X Y                      move a mobilized company (formation_move 0x004DD250)
  attack SLOT X Y                    move onto an enemy there (mode attack, that company its target)
  return SLOT|all                    send home (formation_return_home 0x004DD8D0)
  mode SLOT hold|attack|special      the company's stance (+0x91)
  rotate SLOT                        turn the formation (layout cycle 2 -> 1 -> 16 -> 17)
  wolves X Y                         test: a new wolf pack of 7 at X Y
  invade [X Y] [N] [ARMY]            test: an invading army of strength N (default 16) of army 0..10 at X Y
                                     (default: one of the map's land invasion points)
  invasion                           the armies on the map, their target, the bribe
  bribe                              pay the bribe (the army leaves)
  navy                               the triremes: action, label, hull, crew
  navy crew                          the Military page's "crew all" / "stand down" toggle (wm_sub_40A380)
  trireme ID X Y | ID crew           order a trireme to sail / attack (0x4093E0), or send its crew home / call
                                     it back (the advisor's navy row, 0x591400)
  trireme ID repair|crewpanel|hold|hunt|patrol   the trireme panel's buttons (0x00406400)
  invade ... sea                     test: by sea (the map's sea invasion point; warships and transports)
  autodefend [on|off]                the Options toggle (0x005692D0; can't be switched on while enemies are on the
                                     map): one month before an invasion the companies muster at its rally point
"""
from . import state, on, contact, units
from . import forces, invaders, wolves

MODES = {"hold": 0, "attack": 1, "special": 2}


def _slots(g, a):
    comps = forces.companies(g)
    if not a:
        raise ValueError("which company? (`companies` lists them)")
    if a[0] == "all":
        return sorted(comps)
    s = int(a[0])
    if s not in comps:
        raise ValueError(f"no company {s} (`companies` lists them)")
    return [s]


def _ints(a):
    return [int(x) for x in a if x.lstrip("-").isdigit()]


def run(g, op, a):
    if op == "military":
        if a and a[0] in ("on", "off"):
            st = state(g)
            st["on"] = a[0] == "on"
            if not st["on"]:
                from . import ROLES
                for w in [w for w in g.walkers.values() if w.role in ROLES and w.role != "trireme"]:
                    units.remove(g, w)
                st.pop("invasions", None)
                st.pop("ecomps", None)
            return f"military {'on' if st['on'] else 'off'}"
        return status(g)
    if not on(g):
        raise ValueError("the military module is off (`military on`)")
    if op == "navy":
        if a and a[0] == "crew":
            from . import navy
            on_ = navy.crew_all_toggle(g)
            return "crew all: wharves staffed, triremes back to their wharves" if on_ else \
                "stand down: the triremes return and their crews go home"
        return navy_text(g)
    if op == "trireme":
        from . import navy
        if not a:
            raise ValueError("usage: trireme ID X Y | trireme ID crew")
        w = g.walkers.get(int(a[0]))
        if w is None or w.role != "trireme":
            raise ValueError(f"no trireme {a[0]} (`navy` lists them)")
        if len(a) > 1 and a[1] == "crew":
            navy.crew_home(g, w)
            return f"trireme {w.id}: {'crew going home' if w.act == 0x17 else 'crew back aboard'}"
        PANEL = {"repair": 1, "crewpanel": 2, "hold": 3, "hunt": 4, "patrol": 5}
        if len(a) > 1 and a[1] in PANEL:            # the trireme panel's buttons (0x00406400)
            err = navy.panel_order(g, w, PANEL[a[1]])
            if err:
                raise ValueError(err)
            return f"trireme {w.id}: action 0x{w.act:X}"
        xy = _ints(a[1:])
        if len(xy) < 2:
            raise ValueError("usage: trireme ID X Y")
        err = navy.order(g, w, xy[0], xy[1])
        if err:
            raise ValueError(err)
        return f"trireme {w.id}: " + ("attacking" if w.act == 0x1B else f"sailing to {w.dest}")
    if op == "autodefend":
        from . import alarm
        st = state(g)
        if a and a[0] in ("on", "off"):
            want = a[0] == "on"
            if want and not st.get("auto_defend") and alarm.enemy_present(g):
                raise ValueError("auto-defend can't be switched on while enemies are on the map")
            st["auto_defend"] = want
        return f"auto-defend {'on' if st.get('auto_defend') else 'off'}"
    if op == "companies":
        return companies_text(g)
    if op in ("mobilize", "move", "attack"):
        slots = _slots(g, a)
        xy = _ints(a[1:])
        out = []
        for k, s in enumerate(slots):
            c = forces.field(forces.companies(g)[s])
            if op == "mobilize":
                err = forces.mobilize(g, s, *(xy[:2] if len(xy) >= 2 else (None, None)), k=k)
            elif len(xy) < 2:
                raise ValueError(f"usage: {op} SLOT X Y")
            elif op == "move":
                if not c["mob"]:
                    err = forces.mobilize(g, s, xy[0], xy[1], k=k)
                else:
                    err = forces.move(g, s, xy[0], xy[1], k=k)
            else:
                err = forces.attack(g, s, xy[0], xy[1], k=k)
            out.append(f"company {s}: " + (err or f"{'mobilized, ' if op == 'mobilize' else ''}to {c['dest']}"))
        return "\n".join(out)
    if op == "return":
        slots = _slots(g, a)
        for s in slots:
            forces.send_home(g, s)
        return f"companies {', '.join(map(str, slots))} sent home"
    if op == "mode":
        if len(a) < 2 or a[1] not in MODES:
            raise ValueError("usage: mode SLOT hold|attack|special")
        for s in _slots(g, a):
            forces.set_mode(g, s, MODES[a[1]])
        return f"mode {a[1]}"
    if op == "rotate":
        for s in _slots(g, a):
            forces.rotate(g, s)
        return "rotated"
    if op == "wolves":
        xy = _ints(a)
        if len(xy) < 2:
            raise ValueError("usage: wolves X Y")
        p = (xy[0], xy[1])
        if not g.world.inside(*p):
            raise ValueError(f"({p[0]},{p[1]}) is off the map")
        extra = state(g).setdefault("extra_packs", [])
        if p not in extra:
            extra.append(p)
        wolves.packs(g).pop(p, None)
        wolves.day_point(g, p)
        return f"a wolf pack of {wolves.PACK} at {p}"
    if op == "invade":
        xy = _ints(a)
        pt = (xy[0], xy[1]) if len(xy) >= 2 else None
        if pt is not None and not g.world.inside(*pt):
            raise ValueError(f"({pt[0]},{pt[1]}) is off the map")
        n = xy[2] if len(xy) >= 3 else 16
        army = xy[3] if len(xy) >= 4 else 0
        inv = invaders.invade(g, None, point=pt, army=army, strength=n, sea_pt=9 if "sea" in a else None)
        return f"invasion {inv}: strength {n}, army {army} ({units.data()['armies'][army]['name']})"
    if op == "invasion":
        return invasion_text(g)
    if op == "bribe":
        return invaders.bribe(g)
    return None


def navy_text(g):
    from . import navy
    ts = navy.triremes(g)
    if not ts:
        return "no triremes (a staffed trireme wharf builds one from 200 wood and 200 armor)"
    words = {33: "unmanned", 34: "anchored", 35: "sailing", 36: "disembarking", 37: "returning", 38: "repairing",
             39: "fighting", 40: "abroad"}
    out = []
    for w in ts:
        navy.init(g, w)
        b = navy.wharf(g, w)
        lab = navy.label(g, b)[0] if b is not None else None
        out.append(f"trireme {w.id} at ({w.x},{w.y}): {words.get(lab, 'action 0x%X' % w.act)}, hull {navy.hp_pct(w)}%, "
                   f"crew {navy.crew(g, w)}%")
    return "\n".join(out)


def status(g):
    if not on(g):
        return "military off"
    n = {}
    for w in g.walkers.values():
        if w.role in ("wolf", "tower_sentry", "wall_sentry", "rabble", "hoplite", "horseman") + invaders.TYPES \
                and w.anim != "die":
            n[w.role] = n.get(w.role, 0) + 1
    inv = invaders.invasions(g)
    return ("military on: " + (", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(n.items())) or "nothing on the map")
            + (f"; {len(inv)} invasion(s) under way" if inv else ""))


def companies_text(g):
    comps = forces.companies(g)
    if not comps:
        return "no companies (soldiers come from houses: common houses rabble, elite houses with armor hoplites, Estates with horses horsemen; needs a palace)"
    out = []
    for s in sorted(comps):
        c = forces.field(comps[s])
        where = "away" if c.get("away") else ("in the field" if c["mob"] else "at home")
        on_map = len(forces.members(g, c))
        out.append(f"{s:2d} {c['type']:<8} {c['members']} soldiers, {where}" + (f" ({on_map} on the map)" if on_map else "")
                   + f", mode {[k for k, v in MODES.items() if v == c['mode']][0]}, morale {c['morale']}"
                   + (f", at {c['dest']}" if c["dest"] else "") + ("" if c["ready"] else ", routed"))
    return "\n".join(out)


def invasion_text(g):
    invs = invaders.invasions(g)
    if not invs:
        return "no invasion"
    out = []
    for i, inv in invs.items():
        n = sum(len(invaders.alive_members(g, invaders.ecomps(g)[c])) for c in inv["companies"] if c in invaders.ecomps(g))
        out.append(f"invasion {i} from {inv['name']}: {n} soldiers, target {inv['target']}, "
                   f"weights enemy {invaders.enemy_weight(g, inv)} vs yours {invaders.player_weight(g)}; "
                   f"bribe {invaders.bribe_cost(g, i)} dr")
    return "\n".join(out)


def _standard_homes(g):
    """The palace's class-5 pieces in layout order: company slot k's standard stands on the k-th while not
    mobilized (`palace_part_is_soldier_slot` 0x00542610, `formation_create_company` 0x004DDA00; docs/play/monuments.md)."""
    from ..systems import monuments
    p = forces.palace(g)
    if p is None or p.key not in monuments.layouts():
        return []
    lay = monuments.layouts()[p.key]
    return [list(monuments.piece_xy(p, i)) for i, q in enumerate(lay["pieces"]) if q[2] == 5]


def export(g):
    """/military.json: companies (standards and icons), invasions, wall damage (play mode, advisor 2)."""
    comps = forces.companies(g)
    from . import alarm
    out = dict(on=on(g), companies=[], invasions=[], enemies=0, auto_defend=bool(state(g).get("auto_defend")),
               months_to_next=alarm.months_to_next(g), months_since_enemy=alarm.months_since_enemy(g))
    homes = _standard_homes(g)
    for s in sorted(comps):
        c = forces.field(comps[s])
        out["companies"].append(dict(slot=s, type=c["type"], members=c["members"], mob=c["mob"],
                                     away=bool(c.get("away")), dest=c["dest"], mode=c["mode"], morale=c["morale"],
                                     ready=c["ready"], layout=c["layout"], on_map=len(forces.members(g, c)),
                                     status=forces.status(g, c)[0], banner=int(c.get("banner", s - 1)) % 20,
                                     loan=bool(c.get("event")),           # defensive aid: SPR_FLAG_LOAN
                                     recalled=bool(c.get("recalled")),
                                     ids=[i for i in c.get("ids", []) if i in g.walkers],
                                     home=homes[s - 1] if 0 < s <= len(homes) else None))
    for i, inv in invaders.invasions(g).items():
        out["invasions"].append(dict(id=i, name=inv["name"], target=inv["target"], nation=inv["nation"],
                                     bribe=invaders.bribe_cost(g, i)))
    out["enemies"] = sum(1 for w in g.walkers.values() if w.role in invaders.TYPES and w.anim != "die")
    out["triremes"] = sum(1 for w in g.walkers.values() if w.role == "trireme")
    from . import navy
    out["crew_all"], out["crew_label"] = bool(state(g).get("crew_all")), navy.crew_all_label(g)   # FUN_0051AE00
    out["navy"] = []
    for w in navy.triremes(g):
        navy.init(g, w)
        b = navy.wharf(g, w)
        lab, click = navy.label(g, b) if b is not None else (None, False)
        out["navy"].append(dict(id=w.id, x=w.x, y=w.y, act=w.act, label=lab, clickable=click, hull=navy.hp_pct(w),
                                hull_text=navy.hull_text(w), crew=navy.crew(g, w), name=w.name, wharf=b.id if b else None,
                                workers=b.employees if b else 0, staff=navy.staff(g, b),
                                mode=getattr(w, "next_act", 0x14) if w.act == 0x19 else w.act))
    return out
