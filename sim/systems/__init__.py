"""Daily/monthly system order. Rules come from docs/logic/ (simplified, see docs/sim-design.md)."""
from .. import empire, military as military_map, heroes as heroes_map
from .. import scenario
from .. import gods
from .. import alerts
from .. import allowed
from . import roads, desirability, housing, population, labor, walkers, services, economy, finance, risk, wild, trade, health, crime, agora, monuments, commemorative, military, avenues, stadium, games


def run_day(g):
    dpm = g.rules["days_per_month"]
    dom = g.day % dpm
    if dom == 0:
        month_start(g)
    military_map.day(g)                   # alarm counters, companies' morale (sim/military; its cycle steps: military_map.step)
    heroes_map.day(g)                     # monsters, heroes, quests (sim/heroes)
    with alerts.dated(g, g.day - 1):      # the exe's month-end block: day_of_month held at 15 (sim/alerts.py)
        empire.day(g)                     # world cities, diplomacy, expeditions (sim/empire)
        scenario.month(g)                 # the episode's scheduled events, at the month change (sim/scenario)
    if dom == 0:
        allowed.mark(g)                   # rebuild_goods_lists after month_events_dispatch: the sticky goods marks
    gods.day(g)                           # sanctuaries, priests, god visits, help, jealousy, curses (sim/gods)
    economy.tend_decay(g)                 # month_advance's tail: 0x004AA640
    health.update(g)
    alerts.day(g)                         # the panel's alert slots: more than 8 days old -> gone (sim/alerts)
    if dom in (0, dpm // 2):                # month_advance: city_sentiment_update 0x005671A0 on days 0 and 8
        finance.sentiment(g)
        risk.crime(g)
    if "hooks" in g.__dict__:             # modules outside the core by name (sim/hooks.py; campaign goals)
        from .. import hooks
        hooks.call(g, "day")


def run_step29(g):
    """Cycle step 29 of the day: formations_update(1) (FUN_00500910: the invaders' company AI; formations_pass)."""
    military_map.step(g, 29)
    wild.update(g, recount=False)


def _formations5(g):
    """Cycle step 5: formations_update(0) (formations_refresh recounts, formations_pass)."""
    military_map.step(g, 5)
    wild.update(g, recount=True)


def _relations13(g):
    military_map.step(g, 13)              # with no enemy alive the marks reset, then cities_relations_update


def _recruit14(g):
    military.update(g)                    # cycle_formations_pass_14 0x00567C70 (frozen while enemies are alive)


def _trade32(g):
    trade.update(g)                       # cities_trade_update 0x005B9EE0
    monuments.complete_check(g)           # cycle_buildings_pass_32 0x00495860


def _burn43(g):
    risk.burn(g)                          # buildings_fire_burn_spread 0x00493140


def _risk44(g):
    risk.update(g)                        # buildings_fire_collapse_risk 0x00492260 (by name: tests patch it)


def _crime45(g):
    crime.spawn(g)                        # houses_spawn_criminals 0x005BFDE0


def _animals49(g):
    walkers.animals_spawn(g)              # animals_spawn 0x004F8E30


def _labor25(g):
    labor.allocate(g)                     # by name: tools patch labor.allocate


def _houses39(g):
    housing.update(g)
    if g.day % g.rules["days_per_month"] in (0, 7):   # houses_evolve: house_consume_luxuries on day_of_month 0 / 7
        housing.consume_luxuries(g)


def _spawn31(g):
    """buildings_spawn_walkers 0x0048CFB0 (ours by system, not by building id: producers, carts, vendors, the
    artisans' guilds, services, the military's towers and trireme wharves)."""
    economy.produce(g)
    economy.dispatch(g)
    agora.update(g)                       # vendor_update 0x0040A4C0 (stall buyers; the agora's staffing)
    monuments.artisans(g)
    services.spawn(g)
    military_map.step(g, 31)


# simulation_cycle_step 0x00483840's switch (docs/logic/time-core.md section 3): the systems that run at their own
# step of the day; run_day is the step-50 point with month_advance. Game.step runs step s in the tick whose number
# % 51 is s + 1.
STEPS = {
    5: (_formations5,),                   # formations_update(0) 0x004DDD30
    6: (health.plague_countdown,),        # houses_plague_countdown 0x004483F0
    13: (_relations13,),
    14: (_recruit14,),
    20: (economy.produce20,),             # cycle_production_progress_20 0x00485360, terrain_regrow 0x004A7D30
    21: (housing.road_check,),            # buildings_road_access 0x004856A0 (its house part)
    23: (population.migrate, commemorative.day),  # city_population_update 0x00486190 (and its milestones)
    24: (population.evict,),              # house_evict_overcrowded 0x004871B0
    25: (_labor25,),                      # cycle_labor_25a/b/c 0x00487240 / 0x00487630 / 0x00487BA0
    29: (run_step29,),
    31: (_spawn31,),                      # buildings_spawn_walkers 0x0048CFB0
    32: (_trade32,),
    35: (services.coverage_decay,),       # houses_coverage_decay 0x00484D20
    37: (desirability.update,),           # desirability_from_buildings / _from_terrain 0x00493830 / 0x00493C80
    39: (_houses39,),                     # step 38's house desirability (0x004842A0) + houses_evolve 0x004FE290
    43: (_burn43,),
    44: (_risk44,),
    45: (_crime45,),
    48: (services.tax_decay,),            # buildings_tax_coverage_decay 0x00488220
    49: (_animals49,),
}


def run_step(g, s):
    for f in STEPS.get(s, ()):
        f(g)


def month_start(g):
    if g.day == 0:
        return
    housing.eat_food(g)
    health.month_start(g)
    finance.month_end(g)
    commemorative.month(g)
    games.month(g)                        # Panhellenic games: June begin, end of August conclude (games.py)
    if g.history:                         # the closed month's food per source / imported food (husbandry advisor)
        g.history[-1]["food_src"] = dict(getattr(g, "food_src_month", {}))
        g.history[-1]["food_imp"] = dict(getattr(g, "food_imp_month", {}))
    g.food_src_month, g.food_imp_month = {}, {}
    hist = g.sd("produced_hist", [])      # last 12 months of output, for the reports
    hist.append(getattr(g, "produced_month", {}))
    del hist[:-12]
    g.produced_month = {}
    economy.harvest(g)
    walkers.month_ready(g)
    if g.month == 0:
        if "year_stats" in g.__dict__:     # episode games: last year's counters for the goals (sim/measure.py)
            from .. import measure
            measure.year_end(g)
        g.year_treasury = g.city.treasury   # ledger_year_rollover 0x00488840: _DAT_00fe971c = g_treasury
        trade.year_start(g)
        risk.year_start(g)
        health.year_start(g)
