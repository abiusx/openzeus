# Docs index

## Where we are
- [../TODO.md](../TODO.md): the open work
- [features.md](features.md): the sandbox mechanics inventory vs our engine

## Playing
- [play.md](play.md): the CLI, the live server, test commands, the baseline save
- [play-strategy.md](play-strategy.md): strategy primer (agent players and new humans)
- [play-mode.md](play-mode.md): the browser game with the original's art (plan); details in play/ below
- [playtests/](playtests/): agent playtest reports and logs (2026-10-27 agent1, 10-30 haiku-1/2, 10-31 haiku-3)

## The original game and reverse engineering
- [zeus-original-inventory.md](zeus-original-inventory.md): what is in the extracted game, file formats
- [extraction-plan.md](extraction-plan.md): what we extract and how; [formats.md](formats.md): formats and readers
- [assets.md](assets.md): the game's files out of git: build them from your copy or install the asset pack
  (`tools/assets.py`), what is an asset (classification), templates, manifest, packs
- [references.md](references.md): other reimplementations and RE projects (reference only)
- [re-plan.md](re-plan.md): the RE plan; [re/method.md](re/method.md): how to RE a subsystem
- [re/oracle.md](re/oracle.md): running the original headless, state dumps, screenshots
- [re/structs.md](re/structs.md), [re/structs-generated.md](re/structs-generated.md): memory structures
- [logic/README.md](logic/README.md): the mechanics, one doc per subsystem (from the exe, verified/hypothesis tags),
  [logic/open-questions.md](logic/open-questions.md)

## Our engine
- [sim-design.md](sim-design.md): the simulation's design, performance
- [world-format.md](world-format.md): world files (custom worlds as data, `empire on NAME [--migrate]`)
- [campaign-format.md](campaign-format.md): the adventures (.pak) as data/campaign/*.json; how the exe plays
  episodes, colonies, carry-over, goals (track 1L)

## Play mode (viewer/play/)
- [play/bugs.md](play/bugs.md): every reported bug, fixed / as original / ours, with evidence
- [play/screens.md](play/screens.md): every in-game screen, ported or not
- [play/campaign.md](play/campaign.md): the campaign screens in play mode (adventure select, briefing, goals, victory,
  defeat, colony choice; server endpoints; oracle checks)
- Interface: [ui.md](play/ui.md) (the city UI), [pages.md](play/pages.md) (panel pages, overlays),
  [info.md](play/info.md) (info windows), [advisors.md](play/advisors.md), [lists.md](play/lists.md) (messages,
  goals), [alerts.md](play/alerts.md), [options.md](play/options.md), [help.md](play/help.md),
  [keys.md](play/keys.md), [undo.md](play/undo.md), [text.md](play/text.md) (fonts, strings), [world.md](play/world.md)
  (world map), [military.md](play/military.md), [gods.md](play/gods.md)
- Drawing: [draw-order.md](play/draw-order.md), [buildings.md](play/buildings.md), [walkers.md](play/walkers.md),
  [terrain.md](play/terrain.md), [monuments.md](play/monuments.md), [rotation.md](play/rotation.md),
  [hires.md](play/hires.md) (upscaled sprites, reproducible), [server.md](play/server.md) (a shared server), [gpu.md](play/gpu.md)
- [audio.md](play/audio.md), [comms.md](play/comms.md) (client/server protocol)
