"""Episode starts and the city carried between episodes: the core's side of a campaign (docs/campaign-format.md
"How the exe plays an adventure"; track 1L-2). Generic: it takes an episode record in the documented format
(data/campaign/*.json "episodes", or any file in that format) and never imports the campaign module, which picks
the episodes, judges the goals and keeps the files (1L-3).

The three start kinds of episode_start_load 0x00420390 (record +0x58):
  new_city(map_name, ep, ...)            0: a new game on the map: start year, funds x difficulty, gods, events,
                                            player city, allowed table, games year, tutorial switches
  colony(parent, map_name, ep, city)     1: a new game on the colony map that keeps the parent's empire, treasury
                                            and date (parent.dat); the parent city -> kind 3, the colony -> player
  resume(g, ep)                          2: the next episode in the same city (a whole saved game): gods, events
                                            (rebased), player city, allowed table, games year; date and treasury kept
  back_from_colony(parent, colony, city) episode_end_save_parent 0x0052D2B0 in a colony: the parent city as it was,
                                            with the colony's empire, treasury and date; colony -> kind 1, tribute 1
Saving and loading the whole game is Game.save / Game.load (sim/savefile.py): parent.dat is one such save.

What an episode game keeps on g (absent in open play, so open play is unchanged): year0, scenario_year (the exe's
scenario_start_year 0x00902928: the episode's first year), games_year (scenario +0x328), allowed (the 100 flags,
sim/allowed.py), tutorial ({build_categories, world_map_button}, tutorials only), months0 (Game.month_index),
year_stats (sim/measure.py), episode ({slot, start}).
"""
import copy
import json
import os

START_KINDS = ("new_city", "colony", "continue")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(ref):
    """The episode record `CAMPAIGN#SLOT` (data/campaign/CAMPAIGN.json, tools/build_campaign.py), with the
    campaign's source file."""
    cid, _, slot = ref.partition("#")
    a = json.load(open(os.path.join(ROOT, "data", "campaign", f"{cid}.json")))
    ep = next(e for e in a["episodes"] if e["slot"] == int(slot or 0))
    ep.setdefault("source", a.get("source", ""))
    return ep


def start_of(ep):
    """Game(start=) of a new city (kind 0) from the episode record ep."""
    return dict(kind="new_city", episode=ep, player_city=ep.get("player_city"))


def open_play(ref):
    """An open play as the exe starts it (data/maps.json "episode", sim/world.py play): the adventure's only
    episode, a new city like any other (}Open Play Sandbox.pak: its player city's raw goods, so no carrot or onion
    farm and no urchin quay; oracle runs sandbox-food, sandbox2-food). The unrestricted open plays (sandbox_open,
    "ours") have no episode: Game(start=None) as before 10-31."""
    return start_of(load(ref))


def init(g, start):
    """Game.__init__, before the modules start: a colony's carried date and goods prices."""
    if start.get("months0"):
        g.months0 = start["months0"]
    if start.get("year0") is not None:
        g.year0 = start["year0"]
    if start.get("prices") is not None:
        g.prices = dict(start["prices"])


def apply(g, start):
    """Game.__init__, after the empire and scenario modules loaded the episode's (new_city, colony)."""
    ep = start["episode"]
    if start.get("kind", "new_city") == "new_city":
        g.year0 = ep["start_year"]                    # scenario_start_year = scenario +0
        # funds then the difficulty factor (0x0051D5F0, table 0x005F7F08), as Game.__init__ for open play
        g.start_funds = ep["funds"]                     # scenario_start_funds (set_difficulty at the briefing)
        g.city.treasury = ep["funds"] * g.rules.get("start_funds_pct", 100) // 100
    else:
        g.city.treasury = start["treasury"]           # the carried treasury (= scenario_start_funds)
        g.start_funds = start["treasury"]
    g.year_treasury = g.city.treasury                 # _DAT_00fe971c (FUN_0051D5F0 / the colony start)
    switches(g, ep, start.get("kind", "new_city"))


def switches(g, ep, kind):
    """What every start kind sets from the episode: scenario_start_year (new city: its start year; colony and
    continue: the current year), the games year +0x328 (0x00902C50), the allowed table (+0x408 -> 0x00902D30),
    the tutorial switches (0x00FEAE06[11] / 0x00FE6A5A: 1 unless a tutorial), the yearly counters."""
    g.scenario_year = ep["start_year"] if kind == "new_city" else g.year
    g.games_year = ep.get("games_year", 0)
    g.allowed = list(ep["allowed_raw"])
    t = ep.get("tutorial")
    if t:
        g.tutorial = dict(build_categories=list(t["build_categories"]), world_map_button=t["world_map_button"])
    else:
        g.__dict__.pop("tutorial", None)
    g.episode = dict(slot=ep.get("slot"), start=kind)
    from . import measure, allowed
    measure.start(g)
    allowed.mark(g)                                   # episode_start_load 0x00420390: rebuild_goods_lists


def set_difficulty(g, d):
    """The episode briefing's difficulty arrows (screen 0x35, table 0x005EF988), taken when "To the city" leaves the
    screen. The exe's difficulty is the global g_difficulty (0x00F2A988), read live by the rules (tax, wages,
    labour, requests, attitude, monsters, model files) and kept across loading a city (FUN_0042B230 / 0x00511C90
    save and restore it around the load), so a colony or continued city plays at the chosen level too. Funds: the
    exe builds the city after the briefing (screen_start_game 0x004214F0: screen 0x35 -> episode_start_load), so a
    new city's funds are scenario funds x start_funds_pct[chosen] (0x0051D5F0); a colony's carried treasury and a
    continued city's are not scaled. Ours builds the episode's game before its briefing: the catalog is reloaded
    for d and a new city still at tick 0 gets its funds again."""
    from .data import Catalog, DIFFICULTIES
    if d not in DIFFICULTIES:
        raise ValueError(f"difficulty is one of {', '.join(DIFFICULTIES)}, not {d!r}")
    if d == getattr(g, "difficulty", None):
        return
    g.difficulty, g.cat = d, Catalog(difficulty=d)
    g.rules = g.cat.rules
    st = getattr(g, "episode", None) or {}
    if st.get("start") == "new_city" and g.tick == 0 and getattr(g, "start_funds", None) is not None:
        g.city.treasury = g.year_treasury = g.start_funds * g.rules.get("start_funds_pct", 100) // 100


def new_city(map_name, ep, seed=1, difficulty=None, catalog=None):
    """Start kind 0: a new game on map_name (`ADVENTURE.pak#N`, sim/world.py map_path) with the episode's
    values; the empire is the map's own with the episode's player city."""
    from .game import Game
    return Game(map_name, seed, catalog=catalog, difficulty=difficulty, start=start_of(ep))


def carry(g):
    """What flows from one city into the next through parent.dat's partial merge (episode_start_load kind 1 and
    episode_end_save_parent 0x0052D2B0 copy these and nothing else): the world cities (g_cities, with their
    markers 0x008FEBE8 and histories 0x007796D4), the trade routes 0x009034F8 (into a colony only), the goods
    prices (goods_price 0x0065B9B0, rank 8: g.prices once a price event changed them), the treasury and the date."""
    return dict(empire=copy.deepcopy(g.empire), treasury=g.city.treasury, year0=g.start_year,
                months=g.month_index, prices=copy.deepcopy(g.__dict__.get("prices")))


def colony(parent, map_name, ep, city, seed=1, difficulty=None, catalog=None):
    """Start kind 1: the colony map (`ADVENTURE.pak#N`) with the parent's world cities, routes, prices, treasury and
    date. The parent city becomes kind 3 (parent), the colony city (its world city id) kind 0 (player), active; its
    resources from the episode; gods, events (rebased by the current month), allowed table from the episode.
    What the colony map brings itself (FUN_005B0990: city_record_reset and the map's blocks): the world map picture
    (0x0090311C, rank 114), the months count 0x00903114 (scenario block +0x7EC), a new city record (peak military
    strength 0x00FE6A78, the gifts / tribute totals), and g_events = the episode's (no run-time record of the parent's
    episode). Oracle 1L-europa-colony dump 620: picture 6 -> 1, months 2 -> 0, message list 0."""
    from .game import Game
    from . import scenario
    from .empire import scenario as escen
    c = carry(parent)
    e = c["empire"]
    if e is not None:
        old = e.player()
        old.kind, old.active, old.relation = "parent", True, "ally"     # kind 3, active, relationship 0
        nc = e.cities[city]
        nc.kind, nc.active = "player", True
        fresh = escen.from_data(escen.map_data(map_name))
        e.picture, e.months = fresh.picture, escen.map_months(map_name)
        e.events, e.peak_strength, e.totals = [], fresh.peak_strength, fresh.totals
    g = Game(map_name, seed, catalog=catalog, difficulty=difficulty or parent.difficulty,
             start=dict(kind="colony", episode=ep, empire=e, treasury=c["treasury"], year0=c["year0"],
                        months0=c["months"], prices=c["prices"], player_city=ep.get("player_city"),
                        resources_only=True))
    scenario.rebase(g)
    return g


def resume(g, ep):
    """Start kind 2 on a restored game (the whole city as saved), in episode_start_load's order (docs/logic/
    episode-transition.md): the episode's gods (slots, monsters, may-be-jealous, max sanctuaries; scenario_gods_apply);
    its events over g_events (resolved, then rebased by the current month): every run-time record of the last
    episode (requests, gifts and deliveries on their way, tributes, strikes, expeditions, invasions, offers) is gone
    with them; the message list emptied (FUN_00522230); its player city values; the sticky goods / food list marks
    cleared before the lists are rebuilt (FUN_0050D6C0); every city's army_months = 0 (an invasion on the map ends);
    allowed table and games year; treasury and date kept (scenario_start_funds and the year's starting treasury =
    the treasury). Every army away comes home (expedition_forces_home(_, 1)); heroes' halls (type 0x7D) removed; the
    hero records cleared and hero figures removed (FUN_00511DE0, figures 0x45 -> state 2); every monster on the map
    that a hero must slay is announced again (the 'hero needed' message); every enemy figure removed (FUN_0042C4E0:
    0x28..0x2A, 0x3F, 0x40)."""
    from . import empire, scenario, gods, military
    keep = g.scenario
    g.scenario = scenario.from_episode(g, ep)
    if keep is not None:
        g.scenario.log = keep.log
    empire.episode_reset(g)                       # g_events replaced: the run-time records go with the old ones
    g.city.messages = []                          # FUN_00522230: the message list (1000 records) emptied
    scenario.rebase(g)
    scenario.request_list_rebuild(g)
    if ep.get("player_city"):
        empire.set_player_city(g, ep["player_city"])
    marks_clear(g)                                # FUN_0050D6C0, then rebuild_goods_lists (switches: allowed.mark)
    military.episode_reset(g, armies=True)        # g_cities[].army_months = 0: the invasions end
    gods.reapply(g)
    g.start_funds = g.city.treasury               # scenario_start_funds = _DAT_00fe971c = g_treasury
    g.year_treasury = g.city.treasury
    armies_home(g)
    for b in [b for b in g.buildings.values() if b.key == "heroes_hall"]:
        g.demolish(b.id)                          # building_free: no message
    heroes_reset(g)
    monsters_announce(g)
    military.episode_reset(g, figures=True)       # FUN_0042C4E0: enemy soldiers and ships deleted
    switches(g, ep, "continue")
    return g


def marks_clear(g):
    """FUN_0050D6C0 (every episode start, before rebuild_goods_lists): the sticky marks of the city's goods list
    (0x00FE93EC[9 dwords]: g.goods_listed) and food list (0x00FEB0D2..0x00FEB0DA: City.foods_listed) cleared."""
    g.__dict__.pop("goods_listed", None)
    g.city.foods_listed.clear()


def armies_home(g):
    """expedition_forces_home 0x004DEE60 with its 'all' flag (the colony and continue starts, after g_events was
    replaced): every company (formation +0x9C != -1) and trireme (+0x132 != -1) away on an expedition comes home
    and its away mark is cleared; nothing else (the event records are already gone: an ally's troops lent to the
    expedition stay counted away, its loot is never delivered). Ours: they walk in from the map exit as from any
    expedition (the exe puts them at their buildings at once: a teleport, the decision log 'no shortcuts')."""
    from . import military
    from .systems import military as recruit
    away = {c["away"] for c in recruit.companies(g).values() if c.get("away") is not None}
    if military.on(g):
        from .military import navy
        away |= {w.away for w in navy.triremes(g) if getattr(w, "away", -1) >= 0}
        for aid in sorted(away):
            military.march_home(g, dict(id=aid))
            military.navy_return(g, aid)
    for c in recruit.companies(g).values():
        c.pop("away", None)


def heroes_reset(g):
    """FUN_00511DE0 + the figure pass of the continue start: hero records cleared, hero figures removed
    (sim/heroes episode_reset; bugs.md 397)."""
    from . import heroes
    if heroes.on(g):
        from .heroes import heroes as H
        H.episode_reset(g)


def monsters_announce(g):
    """The continue start's figure pass: a monster (figure 0x44) on the map that is not a guardian and belongs to
    an event gets its hero announced again (monster_hero, hero_monster_text, hero_needed_message 0x004FA710, which
    posts once per hero)."""
    from . import heroes
    if not heroes.on(g):
        return
    from .heroes import heroes as H, events as hev, monsters as M
    for m, r in list(M.records(g).items()):
        w = g.walkers.get(r.get("fig"))
        if w is None or w.anim == "die" or r.get("ev", -1) < 0 or heroes.is_guardian(g, m):
            continue
        h = heroes.data()["monsters"][m]["hero"]
        if h >= 0:
            H.needed(g, h, hev.hero_monster_text(h, m))


def back_from_colony(parent, colony_g, city):
    """episode_end_save_parent 0x0052D2B0 at the end of a colony episode: the parent city as it was saved, with the
    colony's world cities (g_cities: kinds, relations, attitudes, quotas and this year's traded loads +0x84, the
    trader countdowns +0x0A: ours trade_state used / countdown), markers, histories, goods prices, date and treasury;
    the rest of parent.dat stays (its routes, months count 0x00903114, city record: peak strength, gifts / tribute
    totals; its g_events, replaced at the next start anyway). The colony city becomes kind 1 (colony) paying tribute
    (mode 1), the parent city kind 0 (player); FUN_00461360 rebuilds the goods flags. The caller saves the result as
    parent.dat. Oracle 1L3-europa-return dump 920: picture 6 and months 3 (the parent's 2, a month on), not the
    colony's 1 / 0."""
    c = carry(colony_g)
    e = c["empire"]
    if e is not None:
        nc = e.cities[city]
        nc.kind = "colony"
        nc.tribute["mode"] = 1
        home = next(x for x in e.cities.values() if x.kind == "parent")
        home.kind = "player"
        if parent.empire is not None:
            parent.empire.cities = e.cities
        else:
            parent.empire = e
        from .empire import relations
        relations.goods_flags_rebuild(parent.empire)  # FUN_00461360 after the merge (0x0052D45F; bug 472)
        from .systems import trade
        st, cst = trade.state(parent), trade.state(colony_g)
        st["used"], st["countdown"] = copy.deepcopy(cst["used"]), list(cst["countdown"])
    if c["prices"] is not None:
        parent.prices = c["prices"]
    else:
        parent.__dict__.pop("prices", None)
    parent.city.treasury = c["treasury"]
    parent.months0 = parent.__dict__.get("months0", 0) + c["months"] - parent.month_index
    return parent
