"""CLI verbs of the gods module and its export for play mode.

    gods                      status: roles, sanctuaries (built / activity), prayer counters, jealousy, curses, log
    gods on|off               switch the module (off: sanctuary effects follow "complete", nothing comes)
    gods log                  the module's log (attacks, visits, help, sacrifices)
    pray GOD                  the sanctuary window's prayer button (0x00408DA0): "result N: ..." (1 heard, 2 granted,
                              3 refused: the window's text 132:god+0x26 / +0x18 / +0x34)
    oracle GOD                Consult Oracle (Zeus, Apollo; oracle_consult 0x004EA630, oracle.py)
    jealous [N]               set the jealousy countdown to N (default 1: the draw runs at the next monthly update)
    godattack GOD [scenario]  a god attacks now: jealous-style (god_attack_start) or as the type-27 event
    godvisit GOD              the god's next visit now (its sanctuary's visit timer to 0)
"""
from . import state, rec, god_id, sanctuary, built, active, menu, GODS, NAMES, T


def run(g, op, a):
    st = state(g)
    if op == "gods":
        if a and a[0] in ("on", "off"):
            st["on"] = a[0] == "on"
            if not st["on"]:
                from . import figures
                figures.remove_all(g)
            return f"gods {'on' if st['on'] else 'off'}"
        if a and a[0] == "log":
            return "\n".join(f"{t // g.rules['ticks_per_day']:6d}d {s}" for t, s in st["log"][-60:]) or "(empty)"
        return status(g)
    i = god_id(a[0]) if a else -1
    if op == "jealous":
        st["jealousy"] = int(a[0]) if a else 1
        return f"jealousy countdown {st['jealousy']}"
    if not 0 <= i < 14:
        raise ValueError(f"god is one of {', '.join(GODS)}")
    if op == "pray":
        from .help import pray
        code, text = pray(g, i)
        return f"result {code}: {text}"
    if op == "oracle":
        from .oracle import consult
        return consult(g, i)[1]
    if op == "godattack":
        if len(a) > 1 and a[1] == "scenario":
            from .invasion import debug_invade
            return debug_invade(g, i)
        from . import figures, month
        if not month.attack_slot(g, i):
            return f"{NAMES[i]}: no attack slot (not a scenario god of that side, or 4 attacking)"
        w = figures.attack_start(g, i)
        return f"{NAMES[i]} attacks at ({w.x},{w.y})" if w else f"{NAMES[i]}: could not appear"
    if op == "godvisit":
        b = sanctuary(g, i)
        if b is None or not built(g, i):
            return f"{NAMES[i]} has no built sanctuary"
        b.misc["visit_timer"] = 0
        return f"{NAMES[i]}'s visit timer 0 (activity {b.misc.get('activity', 0)}, staff {b.employees})"
    if op == "curse":
        return "curse is set by attacking gods (see `gods`)"
    return None


def status(g):
    st = state(g)
    from . import figures
    lines = [f"gods {'on' if st.get('on', True) else 'off'}" + (" (no scenario god block: free)" if st.get("free") else
             f", max sanctuaries {st['max_sanct']}, jealousy countdown {st['jealousy']}, help candidate "
             f"{GODS[st['help_cand']] if st['help_cand'] >= 0 else '-'}")]
    for i in range(14):
        r = rec(g, i)
        role = {0: "friendly", 1: "unfriendly", 2: "-"}[r["unfriendly"]]
        b = sanctuary(g, i)
        sb = (f"sanctuary #{b.id} {'built' if built(g, i) else str(b.misc.get('built', 0)) + '%'} activity "
              f"{b.misc.get('activity', 0)}{' active' if active(g, i) else ''}") if b else "no sanctuary"
        w = figures.figure(g, i)
        on = f" on map ({w.task} at {w.x},{w.y})" if w else ""
        if r["unfriendly"] == 2 and not b and not w:
            continue
        lines.append(f"  {NAMES[i]:10s} {role:10s} slot {r['slot']:2d}{' jealous' if r['jealous'] else ''}  {sb}  "
                     f"prayer {r['prayer']}/{T()['help_threshold'][i]}{' pending' if r['pending'] else ''}{on}")
    m = menu(g)
    lines.append("  buildable sanctuaries: " + ("all (free)" if m is None else ", ".join(m) or "none"))
    if st["curse"]:
        lines.append("  cursed types: " + ", ".join(f"{k}: {v // 16}m{v % 16}d" for k, v in st["curse"].items()))
    if st["stop"]:
        lines.append(f"  production stopped: {st['stop']} days")
    return "\n".join(lines)


def export(g):
    """/gods for play mode and the advisor."""
    st = state(g)
    from . import figures
    out = dict(on=st.get("on", True), free=st.get("free", False), max=st["max_sanct"], menu=menu(g),
               friendly=[i for i in range(14) if rec(g, i)["unfriendly"] == 0],
               unfriendly=[i for i in range(14) if rec(g, i)["unfriendly"] == 1],
               jealousy=st["jealousy"], curse=dict(st["curse"]), stop=st["stop"], gods=[])
    for i in range(14):
        r = rec(g, i)
        w = figures.figure(g, i)
        out["gods"].append(dict(id=i, slot=r["slot"], listed=r["listed"], prayer=r["prayer"],
                                attack_slot=r["attack_slot"], on_map=w.id if w else 0,
                                task=w.task if w else "", active=active(g, i)))
    return out
