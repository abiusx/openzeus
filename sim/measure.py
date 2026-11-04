"""Goal measurements: what the exe's goal checker reads (scenario_goals_check 0x00526990 -> goal_met 0x00526FC0 and
its counters FUN_00525FB0 .. FUN_00526370), measured by the core and judged elsewhere (the campaign module, 1L-3).
Goal-agnostic: values only, no goal records. `goals` CLI command / measure.values(g).

  population        g_population                              (goal 0 Population)
  treasury          g_treasury                                (1 Treasury)
  sanctuaries       {god: True} per god whose sanctuary is finished (FUN_004F0B30: god_sanctuary_building and
                    monument_progress > 99); finished = their count (2 Sanctuary: one god, or a count >= N, the
                    counter FUN_00525FB0 assigns distinct finished gods to the goals)
  units             FUN_004DE170(unit): 11 every soldier (rabble + hoplites + horsemen), 12 hoplites + horsemen,
                    13 horsemen, 57 triremes (player figures 0x39, figures_type39_count 0x004DF3C0); soldiers are
                    the palace companies' members, at home or away, not the defensive aid on loan (the count loop
                    at 0x004DE2xx skips companies with +0x52) (3 Support)
  events            {record id: state +0x30} of the episode's events (4 Quest: 10, 5 Slay: 5; FUN_0052EE00)
  produced_last_year  {good: loads} last calendar year's g_produced / 100 (yearly_stats_rollover 0x004888E0 copies
                    g_produced to 0x00FE9724 at the year's end; FUN_00526370 keeps the max of it) (6 Yearly production)
  relations         {world city id: relationship} (7 Rule: vassal, 2)
  profit_last_year  0x00FE9714 = last year's income - expenses (ledger_totals_refresh 0x00488960); ours: the sum of
                    last calendar year's monthly ledgers (8 Yearly profit; FUN_00526330 keeps the max)
  housing           {house building type 2..14 (= our level + 2): people} (9 Housing: FUN_005262A0 sums the
                    occupants +0x1C of houses whose type +0x10 >= the goal's)
  trading_partners  world cities that are trading partners (FUN_00525EC0) (10 Trading partners)
  year, scenario_year  for 12 Time limit / 13 Survival time (scenario_start_year + v1 <= year)
  stock             {good: units} in granaries, storehouses, trading posts (14 Set aside goods: the counter's
                    writer was not found in the exe yet, docs/campaign-format.md "Open questions")
  hippodrome_length None (15 / 16 are Poseidon, stage 3)
  debt_months       g_debt_months (36 loses the episode, scenario_goals_check)

Counters an episode keeps: g.year_stats (episode games only): last year's production, filled at the year's end.
"""


def start(g):
    """sim/episode.py: an episode game keeps last year's production (absent in open play). A continue start keeps
    the saved city's (0x00FE9724 is part of the save)."""
    if "year_stats" not in g.__dict__:
        g.year_stats = dict(produced_last={}, year=None)


def year_end(g):
    """systems.run_day at the year's first month (after the produced history took December): last year's
    production = the months of the closed year (yearly_stats_rollover 0x004888E0)."""
    st = g.__dict__.get("year_stats")
    if st is None:
        return
    hist = getattr(g, "produced_hist", [])
    n = min(12, len(hist), g.month_index - g.__dict__.get("months0", 0))
    tot = {}
    for m in hist[len(hist) - n:] if n > 0 else []:
        for k, v in m.items():
            tot[k] = tot.get(k, 0) + v
    st["produced_last"] = tot
    st["year"] = g.year - 1


def profit_last_year(g):
    y = g.month_index // 12 - 1
    return sum(sum(v for v in (h.get("ledger") or {}).values() if isinstance(v, (int, float)))
               for h in g.history if isinstance(h.get("mi"), int) and h["mi"] // 12 == y)


def units(g):
    from .systems import military
    n = dict(rabble=0, hoplite=0, horseman=0)
    for s, c in military.companies(g).items():
        if isinstance(s, int) and s <= 20 and c.get("type") in n and not c.get("event"):
            n[c["type"]] += c["members"] if isinstance(c["members"], int) else len(c["members"])
    tri = sum(1 for w in g.walkers.values() if w.role == "trireme" and w.anim != "die")
    return {11: n["rabble"] + n["hoplite"] + n["horseman"], 12: n["hoplite"] + n["horseman"], 13: n["horseman"],
            57: tri}


def sanctuaries(g):
    from . import gods
    return {gods.GODS[i]: True for i in range(14) if gods.built(g, i)}


def housing(g):
    out = {}
    for b in g.buildings.values():
        if b.kind == "house" and b.occupants:
            t = b.level + 2
            out[t] = out.get(t, 0) + b.occupants
    return out


def people_at_least(g, house_type):
    """Goal 9's counter: people in houses of building type >= house_type (2 hut .. 8 townhouse, 9 elite lot ..
    14 estate)."""
    return sum(v for t, v in housing(g).items() if t >= house_type)


def values(g):
    from . import empire, scenario
    from .systems import economy
    e = empire.get(g)
    st = g.__dict__.get("year_stats") or {}
    s = sanctuaries(g)
    return dict(
        population=g.city.population, treasury=g.city.treasury, debt_months=g.city.months_in_debt,
        sanctuaries=s, sanctuaries_finished=len(s), units=units(g),
        events={ev["id"]: ev.get("state", 0) for ev in scenario.events(g)},
        produced_last_year={k: v // 100 for k, v in st.get("produced_last", {}).items()},
        relations={c.id: c.relation for c in e.cities.values()} if e is not None else {},
        profit_last_year=profit_last_year(g), housing=housing(g),
        trading_partners=sum(1 for c in e.cities.values() if c.kind != "player" and c.trading()) if e else 0,
        year=g.year, scenario_year=g.__dict__.get("scenario_year", g.start_year),
        stock={k: economy.city_stock(g, k) for k in g.cat.resources if economy.city_stock(g, k)},
        hippodrome_length=None)


def text(g):
    m = values(g)
    lines = [f"{k}: {v}" for k, v in m.items() if k not in ("relations", "events")]
    lines.append("events (state): " + (", ".join(f"#{i} {s}" for i, s in m["events"].items()) or "none"))
    lines.append("relations: " + (", ".join(f"{i} {r}" for i, r in m["relations"].items()) or "none"))
    return "\n".join(lines)
