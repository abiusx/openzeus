"""The campaign module (track 1L-3): plays the original adventures (data/campaign/*.json, tools/build_campaign.py)
on the core. The core never imports it (tests/test_campaign.py test_campaign_isolated): it reaches the game through the
core's episode switches (sim/episode.py, sim/allowed.py, sim/measure.py, sim/scenario episode_end) and one named
hook (sim/hooks.py "day" -> goals.day). docs/campaign-format.md "The campaign module"; CLI: docs/play.md
"Campaigns".

API (for the CLI and the screens of 1L-4):
  flow.index() / flow.playable(a)        the adventures and whether they start here
  flow.start(adventure, slot, seed, difficulty) -> Game     a new city episode
  flow.status(g) -> dict                 episode, goals with values, result, the next step
  flow.next_step(g) -> dict              what Proceed would do (episode / colony choice / end)
  flow.proceed(g, save, colony, stay) -> Game                after a victory (raises flow.Choice for a colony)
  flow.replay(save) -> Game              the episode's start again (after a defeat)
  flow.briefing(g, "intro"|"victory")    the Zeus_MM text
  goals.set_aside(g, i)                  the objectives screen's Set aside on goal i
  goals.month_check(g)                   goals_month_check (the day hook calls it at the month change)
Screens (1L-4, play mode through sim/live.py; docs/play/campaign.md):
  flow.screen(g) / flow.screens(g)       the screen up (briefing, victory, complete, defeat) and what it draws
  flow.briefed(g) / continue_building(g) To the city / Continue building this city
  flow.adventures()                      the new-game lists (adventures, custom, tutorials)
  texts.rows(g, goals, colony)           the goal rows as the exe writes them (group 194)
State on the game (saved with it): g.campaign = {adventure, slot, prev, colony, won, goals, result (0 / 1 won /
-1 lost), lost (phrase id), forced, stay, done, briefed, defeat_at}.
"""
from . import flow, goals  # noqa: F401
