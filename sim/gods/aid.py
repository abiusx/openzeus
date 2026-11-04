"""Ares and Hermes help (docs/logic/religion.md "Help and prayers"): the two gods whose help acts on the empire's
events (sim/empire). The empire calls in through sim/gods: expedition_sent (army_dialog_dispatch ->
event_pay_tribute_or_gift's troops branch), expedition_battle (distant_battle_resolve's tail) and hermes_pays
(hermes_request_auto 0x004E7C00 in the request checks and payment).

Ares (ares_help 0x004E7610): the first event of item troops (24) in state 6 (forces away) with
event_months_until_due >= 2; automatic help only when the battle is close: sent = event_sent_forces_strength (no
heroes), E = the target city's army (1 without a city): gap = |sent - E| * 100 / max (E = 0 and sent = 0: help),
help when gap < 20. His figure (god_figure_spawn at the sanctuary when he is not on the map; one on the map is taken
where it stands) gets action 0x22 directly (no set_action: no sound): the vanish group, then hidden (+0x65 = 1) in
0x23 until the battle; the event gets flag 0x1000 (the enemy's army counts 50 % in distant_battle_resolve for a
player expedition). After that battle FUN_004C5780: action 10 (still hidden: the appear is not drawn), next 0x14
(hidden cleared, walk to the road by the sanctuary), then 0x0B. No such event: a prayer is queued.
Hermes (hermes_help 0x004E7980): the open requests (type 1 / 0x1E, active, state 0 and announced, or state 1; not
troops), at most 20. Exactly one: it is fulfilled for free (state 3 "on time", countdown rng % 4 + 1; no goods taken),
the help message. Several: message 0xE0 (title 0x734 "Hermes shares your burden", body 0xB8E "Hermes will fulfill an
outstanding request on your city, at no cost to you!") and the prayer goes pending (cost, 1 month): while Hermes is the
month's help candidate or has a pending prayer, the player's next request (type 1, kind != 9) is paid by him (no
stock needed, nothing taken; hermes_pending_clear 0x004E7C30). None: a prayer is queued.
"""
from . import rec, state, rng, sanctuary, NAMES
from .month import log

ARES, HERMES = 5, 7


def _expeditions(g):
    from ..empire import events, model
    return [ev for ev in events.live(g) if ev.get("item") == model.TROOPS and ev["state"] == 6]


def _close_battle(g, ev):
    from ..empire import war
    sent = war.sent_strength(g, ev) - 10 * len(ev.get("heroes", []))   # event_sent_forces_strength: no heroes
    c = g.empire.cities.get(ev.get("city"))
    e = c.army if c is not None else 1
    if sent > e:
        return (sent - e) * 100 // sent < 20
    if e == 0:
        return True
    return (e - sent) * 100 // e < 20


def ares(g, i, prayed):
    from .help import _granted
    from . import figures
    if getattr(g, "empire", None) is not None:
        for ev in _expeditions(g):
            if ev.get("due", g.month_index) - g.month_index < 2:
                continue
            if not prayed and not _close_battle(g, ev):
                continue
            w = figures.figure(g, i)
            if w is None:
                b = sanctuary(g, i)
                w = figures.out_of_sanctuary(g, i) if b is not None else None
                if w is None:
                    break
            w.path = []
            w.task, w.anim_t0, w.state = "ares", g.tick, "held"
            w.ares_ev = ev["id"]
            from ..systems import walkers
            walkers.schedule(g, w, figures.frames(i, 1))
            ev["god_help"] = True                  # event flag 0x1000
            _granted(g, i, prayed)
            log(g, f"{NAMES[i]} joins the expedition {ev['id']}")
            return
    r = rec(g, i)
    if prayed and not r["pending"]:
        from .help import cost
        r["prayer"] += cost(i, prayed)
        r["pending"] = 1
        r["pending_months"] = 1


def ares_act(g, w):
    """0x22 (the vanish group played) -> 0x23: hidden, waiting for the battle."""
    w.hidden = True
    return None


def expedition_sent(g, ev):
    """event_pay_tribute_or_gift, troops: when Ares is the help candidate or has a pending prayer."""
    st = state(g)
    if st["help_cand"] == ARES or rec(g, ARES)["pending"]:
        ares(g, ARES, bool(rec(g, ARES)["pending"]))


def expedition_battle(g, ev):
    """distant_battle_resolve: flag 0x1000 -> FUN_004C5780: Ares action 10 -> 0x14 (home), g_god_on_map = 1."""
    if not ev.get("god_help"):
        return
    from . import figures
    w = figures.figure(g, ARES)
    if w is None:
        return
    from ..systems import walkers
    state(g)["on_map"] = 1
    w.task, w.next_task, w.anim_t0, w.state = "appear", "ares_home", g.tick, "held"
    w.hidden = True                                # action 10 leaves +0x65 set: the appear is not drawn
    walkers.schedule(g, w, 10 + figures.dur(ARES, 3))   # the appear group at rate 100 (bug 393)


# --- Hermes ------------------------------------------------------------------------------------------------------------

def _open_requests(g):
    """FUN_004714f0 over the event list: request / tribute, state 0 announced or 1; not troops; at most 20."""
    from ..empire import events, model
    out = []
    for ev in events.live(g):
        if ev["type"] not in ("request", "tribute_out") or ev.get("item") == model.TROOPS:
            continue
        if ev["state"] == 1 or (ev["state"] == 0 and ev.get("countdown", 0) <= ev.get("deadline", 0)):
            if len(out) < 20:
                out.append(ev)
    return out


def hermes(g, i, prayed):
    from .help import _granted, _queue
    evs = _open_requests(g) if getattr(g, "empire", None) is not None else []
    if len(evs) == 1:
        ev = evs[0]
        ev["state"], ev["countdown"] = 3, rng(g).randrange(128) % 4 + 1
        ev["hermes"] = True
        _granted(g, i, prayed)
        log(g, f"{NAMES[i]} fulfils the request {ev['id']}")
        return
    if len(evs) > 1:
        if rec(g, i)["pending"]:
            return
        from .. import messages
        messages.post(g, 0x734, 0xB8E)
        r = rec(g, i)
        from .help import cost
        r["prayer"] += cost(i, prayed)
        r["pending"], r["pending_months"] = 1, 1
        return
    if prayed:
        _queue(g, i, prayed)


def hermes_pays(g, ev):
    """hermes_request_auto 0x004E7C00: Hermes the help candidate or pending, a request (type 1) not of kind 9."""
    st = state(g)
    return ((st["help_cand"] == HERMES or bool(rec(g, HERMES)["pending"])) and ev["type"] == "request"
            and ev.get("kind", 0) != 9)


def hermes_paid(g):
    """hermes_pending_clear 0x004E7C30."""
    rec(g, HERMES)["pending"] = 0
    st = state(g)
    if st["help_cand"] == HERMES:
        st["help_cand"] = -1


HELPERS = {ARES: ares, HERMES: hermes}
