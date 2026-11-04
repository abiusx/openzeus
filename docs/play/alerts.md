# Alert slots ("go to" buttons) on the control panel (track 1D, 10-30)

The four 33x33 buttons left of the messages button. Code: sim/alerts.py (state, raisers' API, the `alert` command,
the frame export), viewer/play/ui.js `drawAlerts` (picture, click, hover, balloon), data/play/ui.json
`control_panel.alert_types` / `alert_empty` (tools/play_ui.py from the exe tables). Test: tests/test_play.py
`test_alerts`. Oracle: tools/oracle_alerts.py, runs 1D-alerts, 1D-alerts-1024, 1D-alerts-bal.

## The exe
- State: 4 records of 0x70 at 0x00665E48 (save block 132, cleared after a load by FUN_00510ED0 -> FUN_0040FFD0):
  +0 slot, +4 type (-1 none), +8 / +0xC / +0x10 year, month, day of the raise, +0x14 up to 20 tiles, +0x64 count,
  +0x68 next tile, +0x6C all visited.
- Slot by type range (FUN_00410190): slot 0 = 0..6, 1 = 7..8, 2 = 9..11, 3 = 12..14. A new alert of a range replaces
  the slot's (date, one tile, next 0); the slot index goes to 0x005E8FD4 (last raised).
- Types (balloon 68:(178 + type) at once, FUN_004F5F00 hover ids 10..13; picture group 0x005D83CC[type]):

| type | balloon | picture | raised by (exe) | ours |
|---|---|---|---|---|
| 0 | Go to site of fire | SPR_BTN_ALERTS_FIRE | buildings_fire_collapse_risk 0x00492260, message 0xDC 0xB3B (not spread fires) | risk.update |
| 1..4 | earthquake / tidal wave / landslide / lava flow | ..._EARTHQUAKE / _FLOOD / _LANDSLIDE / _LAVA | terrain disaster objects (FUN_004474E0, vtable +0xC gives the type) | not in ours (no terrain disasters) |
| 5 | Go to site of collapsed building | ..._COLLAPSED_BUILDING | buildings_fire_collapse_risk, message 0xB41 (not monsters, invaders, crime, gods) | risk.update |
| 6 | Go to site of blockage | ..._BLOCKED_ROAD | buildings_road_access 0x004856A0: the land route entry -> exit reopened (message 0xB77 at the cleared tile 0x00B1E8B4) | not in ours (no such rule) |
| 7 | Go to site of disease | ..._DISEASE | plague_messages 0x004482B0 behind 0x007D3AFC, which nothing sets: never | none (as the exe) |
| 8 | Go to source of plague | ..._PLAGUE | plague_infect_houses 0x00448490: the first house raises, the others add tiles (FUN_004100C0) | health.outbreak |
| 9 | Go to site of invasion | ..._ENEMY_INVASION | invasion_event_month (the spawn's tile), the transport landing 0x00461AB0 (once per event, the transport's tile) | invaders.invade, navy.unload |
| 10 | Go to site of monster attack | ..._MONSTER_INVASION | monster_spawn 0x0052EEF0 (not guardians) | heroes/monsters.spawn |
| 11 | Go to site of god's appearance | ..._GOD_INVASION | event_god_attack 0x00482B10 (the arrival tile) | gods/invasion handler, debug_invade |
| 12 | Go to god | ..._GOD_ARRIVES | god_attack_start 0x004F0EA0 (jealous god), god help message 0x00480590 (its tile, else the god's figure, else none); Hephaestus moves the tile to Talos (FUN_0040FF80) | gods/figures.attack_start, gods/help._granted, gods/gifts.hephaestus |
| 13 | Go to hero | ..._HERO_ARRIVES | hero_create 0x004FA4F0 | heroes/heroes.create |
| 14 | Visit soldiers | ..._SOLDIERS_RETURN | event_troops_request_update (army home / called off: the land exit), event_delivery_update type 0x18 (ally troops: the map entry), event_quest (hero home: the land exit) | empire/war (expedition_month, aid_accept), heroes/events |

- Picture (FUN_00410230 into the lower draw table 0x0063DF80 entries 0..3 at (panelX + 10/44/78/112, 22 + 456)):
  active: the type's group, +1 hovered, +2 pressed; empty: group 0x279 with offset -3 drawn +3 = the first image of
  SPR_BTN_ALERTS_DISABLED (1459), the panel art under it (0 px against the art), state 0: no clicks, no right click,
  no balloon. Same place on every page and on the military panel (the table is drawn by panel_draw and the
  military screens 0x48 / 0x20).
- Click (0x00405BA0 -> FUN_00410290): the next tile, when on the map, goes to the middle of the city view
  (FUN_0044A7D0); next + 1; after the last tile "all visited". A count outside 0..19 counts as none (20 tiles: no
  move). Right click: help 97..100 (only an active slot). No own sound (button.wav of every press).
- Expiry (FUN_004102F0, every frame on the city screen through FUN_00517CD0): cleared when all visited and the
  button's pressed byte +0x19 is 0 (set to 20 at the click, counted down by the table's input, FUN_00431BC0), or when
  more than 8 days old ((year*12 + month)*16 + day) and the hover byte +0x1A is 0. The hover byte decays only while
  the panel handles the mouse: a button left for the map stays "hovered" (look and hold) until the mouse is back on
  the panel.

## Ours
- The sim keeps the slots (g.alerts; the live server clears them when it loads a save, as the exe; `python3 -m sim do`
  calls and run checkpoints keep them) and exports them in every frame: `alerts` = per slot 0
  or [type, next, [[x, y] | null ...], serial] (sim/live.py record_frame, export.frame; comms deltas as any top-level
  key).
- The date of a raise: g.day, except inside run_day's month-end block (empire.day, scenario.month: the exe holds
  day_of_month at 15 there) and the day cycle's building steps (risk.update), which take g.day - 1 (alerts.dated).
  Oracle runs vs ours (tools/oracle_alerts.py --exe / --ours, same output): 1B-inv-land raised (Jan 15) by 816, gone
  at 1224; 1I-bash monster (Feb 15) by 1632, gone at 2040; 1H-god jealous god (Jan 5) by 255, gone at 714; all
  three identical (tick, date, tile).
- Play mode: the client draws the slots from the frame; a click centres the view (uiCenterOn, as the message
  window's go-to) and sends `alert go K`; the pressed look lasts 20 UI frames (ours; the exe counts its input polls:
  ~32 ticks in the oracle). `alert hover K|-1` tells the sim which button the mouse rests on (sticky while the mouse
  is off the panel, as the exe's hover byte).
- Not copied: the exe redraws the panel only when something changes, so its shots can show a stale slot (1D-alerts
  r7_n: slot 3 cleared by a poke still drawn; r7_gone: slot 1 expired at 1785 still drawn) and, in the working city
  run (1D-alerts-bal), the hovered look one move late; ours draws the state of every frame.

## Checks (10-30, dpr 1.25, interface 80 %, tools/screens_check.mjs + screens_compare.py, tol 30)
- Oracle 1D-alerts (re/oracle/scenarios/alerts.txt: Open Play Sandbox 800x600, the slots poked by
  `tools/oracle_alerts.py --poke`, 7 rounds covering all 15 types): every type's normal and hovered picture against
  the extracted sprites at (608 + 34k, 478): 0 px; ours vs the shots, slot row (606, 476) 140x37, rounds 0..6 with the
  mouse on each slot and on the map (sticky slot 3): 0 px (35 shots); pressed (r7_up2) 0 px; empty slots (r7_gone,
  slot 1 masked: the exe's stale picture) 0 px. Exe timeline from the dumps: the visited slot cleared after the
  second click (1445 -> 1462), slot 1 cleared at 1785 (day 35, raised day 26), slot 0 kept while hovered.
- 1D-alerts-1024 (1024x768): slot row at (846, 476) with the mouse on slot 0 and 1: 0 px.
- 1D-alerts-bal ("See a working city", slots poked to types 6 and 8): the balloon is 68:(178 + type) ("Go to site of
  blockage", "Go to source of plague", not 153 + type); ours box (438, 432) 220x26: 0 px. In the sandbox runs no panel
  balloon showed at all (also not the messages button's): not traced.
- End to end (headless, own server on a save copy): `alert raise 9 120 130` -> the frame's alerts -> a click centres
  the view on the tile and the slot clears; tools/panel_edge_check.mjs OK; tools/gpu_check.mjs (baseline save, paused,
  HEAD worktree vs this code, tex default, views 0/4, zoom 100/200 %): all 990 map shots equal (no map drawing
  changed). tests/test_sim.py on a clean worktree of HEAD + this change: ok.
