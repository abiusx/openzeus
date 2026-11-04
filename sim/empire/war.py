"""Armies on the world map (world-map.md 4.4, 6.7, 9): raids and conquests by the player, strikes by allies,
defensive aid, rival invasions. Distant battles are abstract, as the exe resolves them (distant_battle_resolve
0x00461540). On the city map (sim/military, when on): expedition companies march to the map exit and back
(march_out / march_home), and an arriving invasion becomes an army on the city map (invade), which closes the
event when it ends. Not yet: the allied defensive-aid army on the city map (0x004E2C10)."""
from . import events, relations
from .model import MONEY, TROOPS, STRIKE

LOSS_T = ((10, 70), (25, 50), (33, 33), (50, 25), (66, 20))   # d < limit -> pct; d <= 74 -> 10; else 0
RAID_LOSS_ENEMY = ((10, 25), (25, 18), (33, 12), (50, 9), (66, 6))
RAID_LOSS_PLAYER = ((1, 30), (3, 40), (5, 50), (7, 60), (9, 70))          # k < limit; k <= 10 -> 85; else 100
CONQUER_WIN = ((10, (70, 50, 70)), (25, (50, 50, 50)), (33, (33, 50, 33)), (50, (25, 50, 25)), (66, (20, 50, 20)))
RAID_WIN = ((10, (25, 25, 25)), (25, (18, 25, 18)), (33, (12, 25, 12)), (50, (9, 25, 9)), (66, (6, 25, 6)))
PLUNDER_D = (0.5, 0.66, 0.75, 1.0, 1.5)            # 0x005EC500
# expedition_attitude_effects 0x00483110: target class -> (win: ally, rival, colony, vassal | loss: ...)
ATT_CONQUER = {"ally": ((-100, 0, 0, 0), (-100, 0, 0, 0)), "rival": ((0, 10, 0, 0), (0, 2, 0, 0)),
               "colony": ((0, 0, -15, 0), (0, 0, -5, 0)), "vassal": ((0, 0, 0, 5), (0, 0, 0, -10))}
ATT_RAID = {**ATT_CONQUER, "rival": ((0, 20, 0, 0), (0, 5, 0, 0))}
COL = {"ally": 0, "rival": 1, "colony": 2, "vassal": 3}


def tier(table, d, last, beyond, last_lim=74):
    for lim, v in table:
        if d < lim:
            return v
    return last if d <= last_lim else beyond


def can_be_attacked(c):
    """city_can_be_attacked 0x0042E1E0."""
    if not c.exists():
        return False
    k = c.cls()
    return k in ("ally", "rival") or (k in ("vassal", "colony") and c.rebellion)


def home_companies(g):
    from ..systems import military
    return {s: comp for s, comp in military.companies(g).items()
            if (comp["type"] in ("horseman", "hoplite") or comp.get("sanct")) and not comp.get("away")
            and comp["members"] > 0 and not comp.get("event")}     # + the sanctuary companies 31..34 (FUN_005BB900)


def strike_targets(g, ally):
    """Rivals an ally/vassal would strike (0x0042DB70 with a target)."""
    return [c for c in g.empire.cities.values() if c is not ally and c.cls() == "rival" and c.exists()]


def can_be_asked(c, good):
    """city_can_be_asked 0x0042D260 (plunder choices)."""
    return c.request_fatigue.get(good, 0) < 41 and (good == MONEY or bool(c.sells.get(good)))


# --- the player's expedition (raid / conquer) ---

def eligible(g, c):
    """The army dialog's rows (screen 0x21, FUN_005BB900): horsemen and hoplite companies in the city (mobilized
    or not; never rabble), and the triremes at home when the city is reached by sea (FUN_0046ED20: route +0x140 == 2)."""
    from .. import military
    ships = military.navy_home(g) if c.route == "sea" and military.on(g) else []
    return home_companies(g), ships


def heroes_present(g):
    """The army dialog's hero rows: up to 3 heroes on the map and at home (figure +0x132 < 0; sim/heroes)."""
    try:
        from ..heroes import heroes as H
    except ImportError:
        return []
    out = []
    for h in range(len(H.records(g))):
        w = H.figure(g, h)
        if w is not None and getattr(w, "quest", None) is None and not getattr(w, "hidden", False):
            out.append(h)
    return out[:3]


def _heroes_go(g, ev, hs):
    """expedition_send_forces 0x004DEB30: an enlisted hero gets +0x132 = the event and action 14: he walks to the
    land exit and waits hidden there (16), as on a quest (sim/heroes hero_ai: the same actions; his status reads
    "away on a quest", 185:66, as in the exe, which uses +0x132 for both)."""
    from ..heroes import heroes as H
    from ..systems import walkers
    for h in hs:
        w = H.figure(g, h)
        if w is not None:
            w.quest, w.act, w.path, w.hidden = f"exp{ev['id']}", 14, [], False
            walkers.schedule(g, w, 1)


def _heroes_back(g, ev):
    """expedition_forces_home 0x004DEE60: the hero comes back from the exit to his hall (action 15)."""
    if not ev.get("heroes"):
        return
    from ..systems import walkers
    for w in list(g.walkers.values()):
        if w.role == "hero" and getattr(w, "quest", None) == f"exp{ev['id']}":
            w.quest, w.act, w.hidden, w.path = None, 15, False, []
            walkers.schedule(g, w, 1)


def attack(g, c, raid, plunder=None, ally=None, slots=None, ships=None, heroes=None):
    """expedition_event_create 0x0047FA60 + the army dialog (FUN_005BE0E0): the enlisted companies (slots; None =
    "Enlist All") and triremes (ship ids; None = all eligible) go; rabble never."""
    if not can_be_attacked(c):
        raise ValueError(f"{c.name} cannot be attacked (allies, rivals and rebelling vassals/colonies only)")
    comps, navy = eligible(g, c)
    if slots is not None:
        bad = [s for s in slots if s not in comps]
        if bad:
            raise ValueError(f"companies {bad} can't go (only horsemen and hoplites in the city: {sorted(comps)})")
        comps = {s: comps[s] for s in slots}
    if ships is not None:
        bad = [i for i in ships if i not in navy]
        if bad:
            raise ValueError(f"triremes {bad} can't go" + (" (destination not accessible by sea)" if c.route != "sea"
                                                          else f" (at home: {navy})"))
        navy = list(ships)
    hs = list(heroes or [])
    bad = [h for h in hs if h not in heroes_present(g)]
    if bad:
        raise ValueError(f"heroes {bad} are not in the city")
    if not comps and not navy and not hs:
        raise ValueError("Assign some companies first! (horsemen or hoplites at home, or triremes for a sea route)")
    if raid:
        plunder = plunder or MONEY
        if not can_be_asked(c, plunder):
            raise ValueError(f"{c.name} has no {plunder} to plunder")
    e = g.empire
    travel = e.travel_months(e.player().id, c.id)
    ev = events.add(g, type="expedition", city=c.id, item=TROOPS, raid=raid, plunder=plunder, state=6,
                    countdown=travel, travel=travel, due=g.month_index + travel + 1, companies=sorted(comps),
                    triremes=list(navy), heroes=hs)
    if hs:
        _heroes_go(g, ev, hs)
    for comp in comps.values():
        comp["away"] = ev["id"]
    if navy:
        from .. import military
        military.navy_send(g, ev["id"], navy)
    from .. import military
    if military.on(g):                                 # expedition_send_forces 0x004DEB30: they march to the exit
        military.march_out(g, ev, sorted(comps))
    ev["strength"] = max(1, min(100, sent_strength(g, ev)))
    if ally:
        a = e.find(ally) if isinstance(ally, str) else ally
        from .diplomacy import can_request, ask_effects
        thr, code = can_request(g, a, STRIKE)
        if thr < 0 or code != 3:
            raise ValueError(f"{a.name} will not join the attack")
        n = a.army * 2 // 5                            # expedition_ally_join 0x00483790
        a.army -= n
        a.away[1] += n
        ev["ally"], ev["ally_troops"] = a.id, n
        ask_effects(g, a, STRIKE)                      # 0x00483790: city_request_attitude_effects(ally, 0x1B)
    from .. import gods                                # event_pay_tribute_or_gift (troops): Ares may join (0x004E7610)
    gods.expedition_sent(g, ev)
    return (f"{'raid' if raid else 'conquest'} of {c.name}: {len(comps)} companies"
            + (f" and {len(navy)} triremes" if navy else "") + f" march ({travel} months each way)"
            + (f", with {ev['ally_troops']} soldiers of {e.cities[ev['ally']].name}" if ev.get("ally") is not None else ""))


def sent_strength(g, ev):
    """event_sent_forces_strength 0x004DEA00: horsemen count 2, others 1; ally troops 1 each."""
    from ..systems import military
    comps = military.companies(g)
    p = sum(comps[s]["members"] * (2 if comps[s]["type"] == "horseman" else 1) for s in ev["companies"] if s in comps)
    from .. import military                            # triremes x 6
    return p + ev.get("ally_troops", 0) + 6 * len(military.navy_away(g, ev["id"])) + 10 * len(ev.get("heroes", []))


def expedition_month(g, ev):
    """0x0046ED70 for kind 9."""
    e = g.empire
    c = e.cities[ev["city"]]
    if ev["state"] == 6:
        if (c.cls() in ("vassal", "colony") and not c.rebellion) or not c.visible or not c.active:
            g.message(f"The expedition against {c.name} is called off; your army comes home.")
            _soldiers_alert(g)
            return forces_home(g, ev)
        ev["countdown"] = max(0, ev["countdown"] - 1)
        if g.month_index >= ev["due"]:
            battle(g, ev, c)
        return
    ev["countdown"] -= 1
    if ev["countdown"] < 1:
        # event_troops_request_update cases 7 / 8: FUN_00521A70(0xDE, 0, the land exit's tile): the go-to button
        from ..messages import Msg
        home = dict(at=list(g.world.exit), kind=0xDE) if getattr(g.world, "exit", None) else {}
        if ev["state"] == 7:
            g.message(Msg(f"Your army is home from {c.name}, victorious.", home))
            if ev.get("loot"):                         # FUN_0047F930: type 0x20 flags 0x4100, offered now
                from . import offers
                good, amount = ev["loot"]
                offers.create(g, "plunder", c, good, amount)
        else:
            g.message(Msg(f"Your army is home from {c.name}, defeated.", home))
        _soldiers_alert(g)                             # the message 0xDE (0xB65 / 0xD64 / 0xB5F) with alert 14
        forces_home(g, ev)


def _soldiers_alert(g):
    """event_troops_request_update 0x0046ED70: the army comes home -> alert 14 "visit soldiers" at the land exit."""
    from .. import alerts
    alerts.raise_alert(g, alerts.SOLDIERS, tuple(g.world.exit))


def forces_home(g, ev):
    """expedition_forces_home 0x004DEE60 (+ ally troops back, 0x0042DAA0)."""
    from ..systems import military
    from .. import military as field_army
    if field_army.on(g):                               # 0x004DEE60: they walk in from the map exit
        field_army.march_home(g, ev)
        field_army.navy_return(g, ev["id"])            # triremes sail back from the sea entry
    _heroes_back(g, ev)                                # heroes: +10 strength each (0x004DEA00)
    for comp in military.companies(g).values():
        if comp.get("away") == ev["id"]:
            comp.pop("away")
    if ev.get("ally") is not None:
        a = g.empire.cities[ev["ally"]]
        a.away[1] -= ev["ally_troops"]
        a.army += ev["ally_troops"]
    events.done(ev)


def battle(g, ev, c):
    """distant_battle_resolve 0x00461540 for the player's expedition, then 0x0046ED70's outcome."""
    p = sent_strength(g, ev)
    E0 = c.army or 1
    from .. import gods
    E = E0 * 50 // 100 if gods.ares_helps(g, ev) else E0     # flag 0x1000 (Ares): the enemy counts 50 %
    raid = ev["raid"]
    if p < E:
        d = (E - p) * 100 // E
        if raid:
            k = ((E - p) * 100 // max(p, 1)) // 100
            pl, en, al = tier(RAID_LOSS_PLAYER, k, 85, 100, 10), tier(RAID_LOSS_ENEMY, d, 3, 0), 25
        else:
            pl, en, al = 80, tier(LOSS_T, d, 10, 0), 50
        win = False
    else:
        d = (p - E) * 100 // p
        x = (3 if raid else 10) if d <= 74 else 0
        pl, en, al = tier(RAID_WIN if raid else CONQUER_WIN, d, (x, 25 if raid else 50, x), (x, 25 if raid else 50, x))
        win = True
    wiped = casualties(g, ev, pl)
    if ev.get("ally") is not None:
        lost = ev["ally_troops"] * al // 100
        ev["ally_troops"] -= lost
        g.empire.cities[ev["ally"]].away[1] -= lost
    c.army = max(0, c.army - en * E0 // 100)          # the loss on the army before the 0x1000 halving
    gods.expedition_battle(g, ev)                     # 0x1000: FUN_004C5780, Ares comes back
    if c.strength == 6:
        win = False
    k = c.cls()
    g.message(f"Battle at {c.name}: your {p} against {E}: {'victory' if win else 'defeat'} "
              f"(you lost {pl}%, they lost {en}%).")
    if (not raid or wiped) and not win:
        attitude_effects(g, c, raid, False)
        if raid and wiped:
            g.message(f"Your raiding party at {c.name} was wiped out.")
            return forces_home(g, ev)
        ev["state"], ev["countdown"] = 9, max(1, ev["travel"])
        return
    attitude_effects(g, c, raid, True)                 # sic: a raid lost with survivors still plunders
    if raid:
        ev["loot"] = (ev["plunder"], plunder_amount(g, ev, c))
    else:
        conquer(g, c, k)
    ev["state"], ev["countdown"] = 7, ev["travel"]


def casualties(g, ev, pl):
    """expedition_casualties 0x004DF120: every company of the expedition (and its triremes, sunk by tier) loses pl %;
    True when none is left (the raid wiped out)."""
    from types import SimpleNamespace
    from ..systems import military as sysmil
    from ..military import forces
    comps = sysmil.companies(g)
    wiped = True
    for s in ev.get("companies", []):
        comp = comps.get(s)
        if comp is None:
            continue
        lost = comp["members"] * pl // 100
        # the dead get state 2 (flag 0x10) -> figure_delete 0x004DA250: a palace company's soldier costs the city
        # (rabble 6 people; hoplite / horseman 1 resident + 1 armor (+ 1 horse) from the house FUN_004CDC50 picks);
        # sanctuary / event troops (+0x94 = 1) are free. No group_member_lost here: no morale change (bug 471)
        if not comp.get("sanct") and not comp.get("event"):
            for _ in range(lost):
                forces.charge_death(g, SimpleNamespace(role=comp["type"]))
        comp["members"] -= lost
        if comp["members"] > 0:
            wiped = False
        else:                                         # every member dead: the company slot is freed (+0x5A = -1)
            comps.pop(s, None)
    from .. import military
    if military.navy_away(g, ev["id"]):               # the triremes: sunk by tier (navy.casualties)
        military.navy_casualties(g, ev["id"], pl)
        if military.navy_away(g, ev["id"]):
            wiped = False
    return wiped


def plunder_amount(g, ev, c):
    """city_request_choose 0x0042D380 for a raid: drachmas by wealth, goods by quota (capacity 50 per
    hoplite, 100 per horseman)."""
    from ..systems import military
    good = ev["plunder"]
    d = relations.diff(g)
    if good == MONEY:
        amount = int((c.wealth + 1) * (5, 4, 3, 2.5, 2)[d] * 200)
    else:
        comps = military.companies(g)
        cap = sum(comps[s]["members"] * (100 if comps[s]["type"] == "horseman" else 50) for s in ev["companies"] if s in comps)
        from .. import military
        cap += 600 * len(military.navy_away(g, ev["id"]))     # 600 per trireme
        amount = min(int(c.sells.get(good, 0) / PLUNDER_D[d]), cap)
    c.request_fatigue[good] = c.request_fatigue.get(good, 0) + 15
    return max(amount, 1)


def conquer(g, c, k):
    """expedition_conquer_success 0x00480240; history city_conquered_by_player 0xBE8 (a rebel vassal or colony:
    rebellion_quelled 0xBDC; a loyal colony: 0x3E2, colony_restored_no_reason, sic)."""
    phrase = 0xBDC if c.rebellion and k in ("vassal", "colony") else 0x3E2 if k == "colony" else 0xBE8
    if k in ("ally", "rival"):
        c.relation = "colony" if c.kind == "colony" else "vassal"
        c.attitude, c.displeased = 31, 0
        from ..systems import commemorative       # city_class 0 / 2 (ally, rival): 0x00402B00(5), a Conquest Monument
        from .. import messages
        commemorative.grant(g, 5)
        messages.post(g, 0x3BC, 0x3BD, city=c)    # "You conquered [city_name]!" (names the monument)
    else:
        g.message(f"The rebellion in {c.name} is crushed.")
    c.tribute["mode"], c.trade_open, c.rebellion = 1, True, False
    relations.note(g, c, phrase)                       # 0x3E2's text is "N/A" (eventmsg.txt): the row reads so


def attitude_effects(g, c, raid, win, k=None, strike=False):
    """expedition_attitude_effects 0x00483110: the target and every other active, visible city; history
    player_attacked 0xC72 / player_raided 0xC73 / an ally's strike (type 0x22) player_struck 0xC74, relation byte
    0 for the target, else by the city's class."""
    k = k or c.cls()
    phrase = 0xC74 if strike else 0xC73 if raid else 0xC72
    tab = (ATT_RAID if raid else ATT_CONQUER).get(k)
    if tab is None:
        return
    row = tab[0 if win else 1]
    for o in g.empire.cities.values():
        if o is c or not o.active or not o.visible or o.cls() not in COL:
            continue
        d = row[COL[o.cls()]]
        if d:
            relations.attitude_add(g, o, d, phrase, relations.REL.get(o.cls(), 0))
    if not win:
        d = -35 if raid else -100
    elif k == "rival":
        d = -20 if raid else -100
    elif k == "ally":
        d = -100
    else:
        d = row[COL[k]]
    relations.attitude_add(g, c, d, phrase)
    if k == "ally":
        g.message("Your allies are appalled that you attacked one of their own!")


# --- ally strike (type 0x22, event_ally_strike_update 0x00480A00) ---

def strike_month(g, ev):
    e = g.empire
    a, t = e.cities[ev["city"]], e.cities[ev["target"]]
    st = ev["state"]
    if st == 0:
        ev["travel"] = e.travel_months(a.id, t.id)
        n = a.army * 2 // 5
        if n < 1 or a.rebellion or t.cls() != "rival" or a.army < (a.army + sum(a.away)) // 5:
            g.message(f"{a.name} cannot strike {t.name} after all.")
            return events.done(ev)
        a.army -= n
        a.away[1] += n
        ev["n"], ev["state"], ev["countdown"] = n, 1, ev["travel"]
        g.message(f"{a.name} marches against {t.name} for you ({n} soldiers).")
        return
    ev["countdown"] -= 1
    if st == 1 and ev["countdown"] <= 0:
        n, r = ev["n"], t.army
        k = t.cls()                                    # the target's class before the battle
        if n > r and t.strength != 6:
            d = (n - r) * 100 // n
            lost = n * tier(LOSS_T, d, 10, 0) // 100
            t.army -= r * 50 // 100
            t.relation, t.tribute["mode"], t.trade_open, t.attitude = "vassal", 1, True, 31
            g.message(f"{a.name} has conquered {t.name} for you: it is now your vassal.")
            relations.note(g, t, 0xD94)               # strike_successful_history "Conquered on your behalf"
            win = True
        else:
            d = (r - n) * 100 // max(r, 1)
            lost = n * 75 // 100
            t.army -= tier(LOSS_T, d, 10, 0) * r // 100
            g.message(f"{a.name}'s strike against {t.name} failed.")
            win = False
        ev["n"] -= lost
        a.away[1] -= lost
        attitude_effects(g, t, False, win, k, strike=True)
        ev["state"], ev["countdown"] = (2 if win else 3), ev["travel"]
    elif st in (2, 3) and ev["countdown"] < 1:
        a.away[1] -= ev["n"]
        a.army += ev["n"]
        events.done(ev)


# --- defensive aid (request item 24, delivery type 0x20, 0x004752A0 item 0x18) ---

def aid_accept(g, ev, c):
    """Accept (state 6 -> 9, countdown 4): city_lend 0x0042DAD0 (army -> away), aid_army_spawn 0x004E2C10 (the
    city's soldiers appear at the map entry as event companies 21..30, sim/military). The offer event becomes
    the aid event."""
    n = ev["amount"]
    c.army -= n
    c.away[2] += n
    ev["type"], ev["state"], ev["countdown"] = "aid_troops", 9, 4
    from .. import alerts                             # event_delivery_update type 0x18: alert 14 at the map entry
    alerts.raise_alert(g, alerts.SOLDIERS, tuple(g.world.entry))
    from .. import military
    if military.on(g):
        made = military.aid_arrive(g, ev["id"], c.id, n, c.nation)
        return f"{n} soldiers from {c.name} arrive at the map entry ({made} companies)"
    return f"{n} soldiers from {c.name} arrive (the military module is off: bookkept only)"


def aid_month(g, ev):
    """State 9 monthly: after 4 months and only while no enemy is on the map, the troops go home
    (0x00481D10: away -= n, the army gets 0 back: the sender loses them; 0x004E3060: every event company of that
    city leaves through the map entry; message 0xE0 0x468/0x469)."""
    ev["countdown"] -= 1
    if ev["countdown"] > 0:
        return
    from .. import military, messages
    if military.on(g) and military.enemy_present(g):
        return
    c = g.empire.cities[ev["city"]]
    c.away[2] -= ev["amount"]
    if military.on(g):
        military.aid_recall(g, c.id)
    messages.post(g, 0x468, 0x469, city=c)
    events.done(ev)


def aid_lost(g, ev_id):
    """0x00481D40: the city's last event company is gone (killed, or sent home by the player): away -= n, message
    0x46E/0x46F, the event ends."""
    ev = next((e for e in events.live(g, "aid_troops") if e["id"] == ev_id), None)
    if ev is None:
        return
    from .. import messages
    c = g.empire.cities[ev["city"]]
    c.away[2] -= ev["amount"]
    messages.post(g, 0x46E, 0x46F, city=c)
    events.done(ev)


# --- rival invasions (type 2, military.md) ---

def invasion_pending(g, c):
    if any(ev["city"] == c.id for ev in events.live(g, "invasion")):
        return True
    if getattr(g, "scenario", None) is not None:          # a city's own invasion record (type 2, run-time)
        from . import invasion_events
        from .. import scenario
        return any(ev.get("city2") == c.id and ev["flags"] & scenario.DYNAMIC and invasion_events.pending(g, ev)
                   for ev in scenario.events(g, 2))
    return False


def invasion_create(g, c, strength, spontaneous=False):
    """city_invasion_event_create 0x0047F1C0 (spontaneous: flags 0x110, the "weakness" reason) / city_event_invasion
    0x00477830 (flags 0x120): a type-2 record dated this month (year offset, month), lead 2 (event_init_defaults),
    subtype +0x04 = 1, entry point +0x1C = (rng & 7) + 1 by land / + 9 by sea (with the landing +0x78), target +0x38 =
    10, the city +0x58 and the strength +0x0C set after month_events_dispatch (so nothing is posted at once). It is
    then the scheduled invasions' record (sim/empire/invasion_events.py: invasion_event_month 0x00476E20): the
    announcement 0x2D4 at the month's pass, the one-month warning, the army at the pass of the due month (oracle
    1L5-requests #18: created Apr 799 BC, the army at the June pass). Without the scenario module (old saves): our
    sim/empire queue as before."""
    if strength < 1 or invasion_pending(g, c):
        return False
    sea = c.route == "sea"
    point = (g.rng.randrange(128) & 7) + (9 if sea else 1)                      # (rnd & 7) + 1 land, + 9 sea
    landing = 0
    if sea:                    # +0x78 = FUN_00503EC0: rng_15 % the number of the map's landing points (0..2) that
        from ..military import navy               # exist, an index the spawn (0x503FD0) reads in the full table
        n = sum(1 for x in navy.sea_points(g)[1] if x)
        landing = g.rng.randrange(32768) % n if n else 0
    if getattr(g, "scenario", None) is not None:
        from .. import scenario
        y, m = scenario.today(g)
        ev = scenario.alloc(g, dict(type=2, year=y, month=m, item=1, lead=2, city=point, city2=c.id, amount=strength,
                                    flags=scenario.DYNAMIC | (0x10 if spontaneous else 0x20), b38=10,
                                    landing=landing, active=0, state=0, chain=-1, warned_bits=0))
        if ev is not None:
            scenario.log(g, f"event #{ev['id']}: {c.name} invades (strength {strength}, point {point})")
            return True
    events.add(g, type="invasion", city=c.id, item=TROOPS, amount=strength, due=g.month_index + 2,
               travel=g.empire.travel_months(c.id, g.empire.player().id), point=point, landing=landing)
    g.message(f"An army of {strength} from {c.name} is marching toward your city! It will arrive in 2 months.")
    return True


def invasion_month(g, ev):
    c = g.empire.cities[ev["city"]]
    if c.cls() != "rival" or not c.active or not c.visible:
        return events.done(ev)
    if ev.get("arrived"):                              # on the city map (sim/military): it closes the event
        return
    m = ev["due"] - g.month_index
    if m == 1:
        g.message(f"The army from {c.name} will reach your city next month!")
    elif m <= 0:
        from .. import military
        if military.on(g):                             # invasion_spawn 0x00504600: the battle on the city map
            ev["arrived"] = True
            military.invade(g, ev, ev.get("point", 8))
            return
        g.message(f"The army from {c.name} has reached your city. (The military module is off: "
                  "the invaders go home.)")
        events.done(ev)


# --- positions on the world map (event_world_map_position 0x004694E0) ---

def positions(g):
    e = g.empire
    pid = e.player().id
    out = []
    for ev in events.live(g):
        t, st = ev["type"], ev["state"]
        if t == "expedition":
            if st == 6:
                a, b, rem = pid, ev["city"], ev["countdown"]
            elif st in (7, 8, 9):
                a, b, rem = ev["city"], pid, ev["countdown"]
            else:
                continue
            who, n = "player", ev.get("strength", 0)
        elif t == "strike" and st in (1, 2, 3):
            a, b = (ev["city"], ev["target"]) if st == 1 else (ev["target"], ev["city"])
            rem, who, n = ev["countdown"], "ally", ev.get("n", 0)
        elif t == "invasion":
            a, b, rem = ev["city"], pid, ev["due"] - g.month_index
            who, n = "enemy", ev["amount"]
        else:
            continue
        p = _route_point(g, a, b, rem)
        if p is None:
            continue
        x, y, r = p
        out.append(dict(event=ev["id"], kind=t, who=who, x=x, y=y, sea=r["kind"] == "sea", strength=n,
                        size=0 if n <= 32 else 1 if n <= 66 else 2, city=ev["city"],
                        nation=e.cities[ev["city"]].nation, home=t == "expedition" and st != 6))
    out += _scenario_positions(g)
    for a in out:
        a["heroes"] = army_heroes(g, a["event"])
    return out


def army_heroes(g, key):
    """world_map_draw_army 0x00599740's heroes: the episode's hero slots 0..2 (scenario_hero_of_monster_slot; slot 2
    skipped when it repeats slot 0 or 1) whose figure is away on this event (+0x132 = the event: ours a quest's
    w.quest = the record id, an expedition's "exp<id>"). Returns the hero ids in slot order."""
    try:
        from ..heroes import heroes as H
    except ImportError:
        return []
    want = int(key[1:]) if isinstance(key, str) and key.startswith("s") else f"exp{key}"
    out, seen = [], []
    for k in range(3):
        h = H.hero_of_slot(g, k)
        seen.append(h)
        if h == -1 or (k == 2 and h in seen[:2]):
            continue
        w = H.figure(g, h)
        if w is not None and getattr(w, "quest", None) == want:
            out.append(h)
    return out


def _route_point(g, a, b, rem):
    """event_world_map_position's place on the route a -> b with rem months left: (x, y, route) or None."""
    e = g.empire
    r = e.route(a, b)
    if not r or not r["dots"]:
        return None
    T = max(1, e.travel_months(a, b))
    if rem < 0 or rem > T:
        return None
    if rem < 1:
        pct = 100
    elif rem == T:
        pct = 0
    else:
        pct = (g.tick % 51 + ((T - rem - 1) * 16 + g.day % 16) * 51) * 100 // (T * 816 - 816) if T > 1 else 100
    pct = max(0, min(100, pct))
    if r["a"] != a:
        pct = 100 - pct
    i = min(len(r["dots"]) - 1, len(r["dots"]) * pct // 100)
    x, y = r["dots"][i]
    return x, y, r


def _scenario_positions(g):
    """event_world_map_position 0x004694E0 for the scenario's pending invasions (type 2), troops requests (type 1, item 24) and quests (type 4,
    item 0x1A), drawn by world_map_draw_army 0x00599740 as the player's army (+0x77 = 0: no army sprite, only its
    heroes): state 6 from the player's city to the asking city (kind 2: to the rival +0x6F), the countdown its months
    left (0 once waiting there, flag 0x10000); states 7..9 back from that city."""
    from .. import scenario
    from . import eventmsg
    e = g.empire
    sc = getattr(g, "scenario", None)
    if sc is None:
        return []
    pid = e.player().id
    out = []
    from . import invasion_events
    for ev in sc.events:
        if ev["type"] == 2:                         # events_next_invasion + invasion_event_pending: the enemy on its
            c = e.cities.get(ev.get("city2"))      # way (+0x58 -> the player, the months until due; land when the
            if c is None or not invasion_events.pending(g, ev):          # point +0x1C < 9)
                continue
            p = _route_point(g, c.id, pid, scenario.months_until_due(g, ev))
            if p is None:
                continue
            x, y, r = p
            n = ev.get("amount", 0)
            out.append(dict(event=f"s{ev['id']}", kind="invasion", who="enemy", x=x, y=y, sea=ev.get("city", 8) >= 9,
                            strength=n, size=0 if n <= 32 else 1 if n <= 66 else 2, city=c.id, nation=c.nation,
                            home=False))
            continue
        if ev["type"] not in (1, 4) or ev.get("item") not in (24, 26) or ev["flags"] & scenario.TEMPLATE:
            continue
        st, rem = ev["state"], ev.get("countdown", 0)
        far = eventmsg.byte(ev, 0x6F) if ev["type"] == 1 and ev.get("kind") == 2 else ev.get("city")
        if st == 6:
            a, b = pid, far
            if ev["flags"] & 0x10000:
                rem = 0
        elif st in (7, 8, 9):
            a, b = far, pid
        else:
            continue
        if a not in e.cities or b not in e.cities:
            continue
        p = _route_point(g, a, b, rem)
        if p is None:
            continue
        x, y, r = p
        n = ev.get("strength", 0)
        out.append(dict(event=f"s{ev['id']}", kind="request" if ev["type"] == 1 else "quest", who="player", x=x, y=y,
                        sea=r["kind"] == "sea", strength=n, size=0 if n <= 32 else 1 if n <= 66 else 2, city=far,
                        nation=e.cities[far].nation, home=st != 6, hidden=n == 0))
    return out

