# Play mode: the browser GUI with the original's art (plan, 2026-10-27)

Goal (user): a game view as close to the original as possible (terrain, buildings, animations,
walkers, sounds, interface) so differences from Zeus are visible. **Separate from the sim viewer**
(`viewer/index.html` stays as is): play mode is `viewer/play.html`, fed by the same live server.

## Decisions (discussion 2026-10-27)
- Simulation stays Python (headless, deterministic, authoritative); real-time play needs 15..150
  ticks/s, the sim does ~13k. A port later is feasible (docs: sim is ~4k lines, no graphics).
- Renderer: our own WebGL2 sprite batcher (no engine, no library). Release later: pywebview
  (native window, system webview, same Python process) + PyInstaller; dev: local server + browser.
- Editor needs (fast forward/back, snapshots) come later on the same page; lag is fine there.

## Decoupling (user rule 2026-10-27)
Graphics stay as decoupled from the game logic as possible. The sim knows nothing about sprites or
sound; the play client holds no game rules. The only contract between them is data: the server's
JSON (`/terrain.json`, `/state.json`, `/frame.json`, commands via `/cmd`) and the mapping tables in
`data/play/*.json` (sim key/role/state -> original sprite/sound). Anything the renderer needs to show
(a walker's facing, an animation state) is exported by the sim as plain state, never computed from
rules in JS.

## Pieces
1. **Atlases** (`tools/play_atlas.py`): pack the needed original sprites (extracted/sprites/<file>,
   atlas.json `index`) into texture sheets + JSON (`viewer/play/atlas/`, git-ignored).
2. **Terrain**: the map's image grid (rank 4: `collection*0x4000 + n`, image = atlas `index` n+201 (n 0-based; list position n+200, docs/play/terrain.md);
   v247 maps: collection +2, 3 -> 5 `Zeus_Terrain`), draw flag rank 5 bit 0x40, elevation rank 23
   (y - 30*alt). Projection: tile (x, y) at ((x-y)*30, (x+y)*15), 58x30 diamonds, drawn by x+y.
   Verified 2026-10-27 by rendering the sandbox. Changes in play (trees cut, roads, rubble, cleared
   land) need the original's terrain image choice (research: docs/play/terrain.md).
3. **Buildings**: base image + animation overlays per building, multi-tile placement, house levels,
   crops, construction (research: data/play/buildings.json, docs/play/buildings.md).
   Monuments piece by piece (stage images, terraces, pyramid steps): data/play/monuments.json,
   docs/play/monuments.md, viewer/play/monuments.js.
4. **Walkers**: sprite sets per role, 8 directions, walk frames, carried goods, interpolation
   between server frames (research: data/play/walkers.json, docs/play/walkers.md).
5. **Audio**: building ambient sounds near the view, walker/UI sounds, music (research:
   data/play/audio.json, docs/play/audio.md).
6. **Interface**: the original control panel (Zeus_Interface) with the 11 tabs (research: data/play/ui.json from
   tools/play_ui.py, docs/play/ui.md; composite check tools/play_ui_composite.py). Building info windows per type:
   docs/play/info.md (viewer/play/info.js, data/play/info_panels.json from tools/play_info.py). Page contents (info boxes)
   and the map overlays ("See water", "See problems", ...): docs/play/pages.md (viewer/play/pages.js,
   viewer/play/overlays.js; data/play/pages.json, data/play/overlays.json).
   World map screen: docs/play/world.md (viewer/play/world.js, data/play/world.json from tools/play_world.py).
   All in-game screens vs the exe (inventory, status, checks): docs/play/screens.md. Help window: docs/play/help.md
   (viewer/play/help.js, data/play/help.json from tools/play_help.py); Options / Help / File menus, option dialogs,
   balloon help: docs/play/options.md (options.js, filemenu.js, balloon.js; data/play/options.json from
   tools/play_options.py); Messages list and Goals: docs/play/lists.md (lists.js).

## Sprite references (convention for data/play/*.json)
`{"file": "<dir under extracted/sprites>", "index": <atlas.json image index>}`; ranges as
`{"file", "start", "count"}`. Atlas `index` counts the 200 system images (file image = map number + 200).

## Built (2026-10-27)
- `viewer/play/scene.js` buildings/roads/walkers, `audio.js`, `build.js`, `gl.js`, `play.js` (input, buffered frames, menus).
- Terrain in play: `sim/terrain_view.py` (server-side presentation, not a sim system) rebuilds the original's view of the
  current flags (cut trees in `g.regrow` = stumps, roads from the sim) and recomputes changed regions with
  `tools/terrain_images.py`; `/terrain.json` ships the ids (current numbering). Cliffs keep the map's ids and draw bytes.
  Water animates in the client (60 ms steps, terrain.md 5).
- Building: the build panel sends the sim's own commands (`POST /cmd`: build/road/clear/wall/bridge); `/footprint.json`
  is only a preview hint; the server's answer is shown as a message. Options > New empty city: `POST /control {new}`.
- Server: `/frames.json` (window of frames; the sim stays ~2 s of playback ahead of the furthest tab), `state.json?lite=1`.
  Protocol 2 (10-30, docs/play/comms.md): deltas on what the tab holds (frames, snapshots, terrain), polls when due.
- Sim changes made for fidelity while doing this: idle soldiers stay home (companies are counts, no walkers);
  boar/deer roam through forest (0x00569D90 has no tree bit).
- Live vs replay (user decision 2026-10-27): the server owns one live timeline, paced by the wall clock at its own
  speed (`/control {rate|paused}`); it tracks no tabs. A tab is LIVE (follows the server a steady ~0.5 s behind;
  speed/pause/build act on the city) or REPLAY (timeline slider; plays recorded frames at its own speed; read-only).
  Commands carry the sender's tick; the server rejects them unless the tick is within `live_window()` of live.
- **Synced live (user decision 2026-10-28, replaces the wall-clock lag for attached tabs).** The lag made every
  placement unreal for 1-2 s (ghost drawn over other buildings, no right click, settings showing late, sheep late);
  each was patched separately. Now:
  - A live tab drives the clock. Each poll carries its playhead; the server simulates only up to
    playhead + AHEAD ticks. AHEAD starts at a few ticks and can go down to 1 to test.
  - Without a driving tab (closed, or a background tab Chrome throttles) for about 1 s, the server falls back to its
    own wall clock as before.
  - Frames come every tick at low speed and stay on the 15-tick grid at high speed. Older frames are thinned to the
    grid, so replay memory stays as before.
  - Live tabs show the newest building snapshot, not the one at the playhead (at most AHEAD ticks apart). Replay
    still shows the snapshot at the playhead.
  - Pause and speed stay on the server (`/control`), so every tab and a restart agree.
  - Scripts and agents (`run`, `live --script`) are unchanged.
  - Implemented: `/frames.json?...&want=T` (sim/live.py `driven()`, `frame_every()`, DRIVE_TIMEOUT); client
    `ahead()` = frame interval + ceil(rate x 0.1) (since 11-04 sized from the round trip: docs/play/comms.md
    "Margin over a slow link"), or `play.html?ahead=N` for a fixed margin. Snapshots carry
    `seq` (re-recorded at the same tick after a command); `/cmd` returns the seq, pending values compare S.seq.
    Measured 2026-10-28 (copy of the playtest city): exact rate at 30/120/480/1920 ticks/s, 0 stalled frames;
    the tab trails the server by 3 / 12 / 47 / 167 ticks; a placed building is real (right click) 16-35 ms
    after the click; pause survives save/load; with no tab the server runs on its own at its rate.
- Monuments/palace: `viewer/play/monuments.js` + `data/play/monuments.json` (docs/play/monuments.md); the sim export
  carries per-piece stages. Small atlas sheets share 4096x4096 textures (the shader binds at most 16).

## Saving (File menu)
File > New / Load / Save / Delete adventure (viewer/play/filemenu.js; the dropdown follows the exe, the
dialogs are ours). Named saves are server-side pickles in `saves/play/NAME.pkl` (GET /saves.json, POST
/control {save_as | load | delete | new}). Loading replaces the live city for every tab (tabs follow the
new timeline). The server also autosaves the running city every 5 s to its own save path, so
`python3 -m sim live SAVE` (no --script) resumes where it stopped.
