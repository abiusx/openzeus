# Undo (panel button, `undo` command)

## Exe (verified from the code)
- Every build-tool click starts an action: `undo_begin` 0x004A6CC0 (from build_tool_click, FUN_00408930,
  FUN_0051ECF0) forgets the previous undo, remembers the tool (0x00DA2370) and copies the terrain, building,
  piece, draw and related grids. While the action runs, `undo_record_building` 0x004A6E90 notes each building
  it creates or clears (id + 280-byte record, up to 500; build_commit, houses_drag_place, clear_land_commit
  0x0049A460 and the composite/agora/stadium builders).
- `undo_arm` 0x004A6FD0 after the action (build_commit; after a clear, cycle step 40 when the last tool was
  clear land): undo possible for **500 ticks** (0x00DA2368), cost of the action kept (0x00DA2364 = g_build_cost).
- `undo_expire` 0x004A7A50, every tick: the window closes when the 500 ticks are up; for building tools (not
  road 0x1C, clear 0x1D, wall 0x82, bridge 0x78/0xC9, avenue 0x76, boulevard 0x7E, gardens 0x80) also when
  nothing was recorded, when a noted building is removed / burnt / collapsed (state 2/4/5), moved or changed
  type, and for houses (tool 2) as soon as one has residents. Also cleared (0x00DA2374 = 0) by any fire or
  collapse (building_ignite 0x004950B0, buildings_fire_burn_spread, buildings_fire_collapse_risk), at the new
  year (month_advance 0x00483C10), by some road-access messages (buildings_road_access 0x004856A0).
- The panel's undo button (88:14, (148,435); handler 0x00405B80 -> **0x004A7000**) is enabled while armed
  and valid (panel_draw 0x00517BF0). Undo: treasury (0x00FE6A64) += the action's cost, the construction line
  (0x00FE96E4) -= it (a full refund); then by tool: clear land -> the cleared buildings' records come back
  (empty houses: residents were sent away before the record was taken) and the grids are restored; road /
  wall / bridge / avenue / gardens / orchards -> the grids are restored from the copies; buildings -> each
  noted building gets state 2 (removed at cycle step 40 without rubble; gatehouse via 0x004E5400). Then
  route rebuild. A per-resource list (0x00DA22D4, 36 slots, 0x00489230) is also put back (hypothesis: goods
  the action used, e.g. sanctuary marble).

## Ours (sim/game.py `action_begin` / `action_end` / `undo_last`, command `undo`)
- One action = one command at the CLI, or one batch (`/cmd` with `cmds`, a drag) in play mode (live.py
  `commands`); only build, road, wall, bridge, avenue, boulevard, clear, path start one (as the exe's build
  tools; settings like storage orders or priorities don't touch the undo).
- Kept: the tiles the action changed (flags, road, occ, avenue grids: before/after values), the buildings it
  created or removed, animals it placed, roadblocks, the treasury change. Undo puts the tiles back, removes
  the created buildings (and their walkers), returns cleared buildings empty, refunds the cost to the
  treasury and the construction ledger, rebuilds roads/access.
- Refused (`undo_state`): nothing to undo, >= 500 ticks later, a new year, any new fire or ruin since, a
  created building gone/changed, a created house with residents. The play-mode button is enabled from the
  frame's `undo` flag.
- Differences: ours restores only the changed tiles (the exe copies whole grids, which also reverts unrelated
  tile changes made in those ticks); the resource list 0x00DA22D4 is not modelled (our builds consume no goods); a cleared agora vendor stays an empty stall after undo.
- CLI text (ours, 10-30, bugs.md 280): `undone: agora, 3 x empty_stall (4 buildings) removed, ...`: an agora's
  stalls are buildings of their own in ours, so the bare count "4 built" read as one too many; the text names them.
- Verified 2026-10-28: CLI (build/road/clear/undo, refusal after 500 ticks); play mode: a 2-house batch, the
  real button click removed both, refunded 40, button disabled afterwards.
