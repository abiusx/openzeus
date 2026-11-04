# GPU memory and texture units in play mode (2026-10-30)

Supporting work (the stage plan "Supporting work"; TODO.md "GPU memory"). Code: viewer/play/gl.js (SpriteGL, Batch),
viewer/play/play.js (loadAtlases, resumeSheet, evictIdle, hiresTextures, gpuMemText). Check: tools/gpu_check.mjs.

## Texture units
A WebGL2 draw can sample at most MAX_TEXTURE_IMAGE_UNITS textures (16 in Chrome/ANGLE Metal here; the hi-res texture
arrays take the last 4). Before: every atlas texture had a fixed unit (12 at most, `addSheet` threw "too many
sheets"). With `?tex=png` the baseline save used all 12 before any god came, so a god's atlas did not load and the
god was missing or drawn wrong (bugs.md 263); the default (compressed) mode used 8.

Now (gl.js):
- A texture is a sheet id (0..127, `MAX_IDS`); the vertex shader reads each sprite's sheet entry from a uniform table
  `uSheet[id]` = (width, height, unit, compressed). Hi-res layers keep their own ids (1024 + set * 64 + layer).
- `Batch.draw` splits its instance range into runs of consecutive sprites that use at most `unitBudget` 2D sheets
  (normally one run: the whole batch). `bindRun` puts each run's sheets on units: a sheet already bound stays, the
  others take the least recently used units; the table is uploaded when it changed. Runs are drawn in order, so the
  sprite order (order.js) is unchanged and so are the pixels (each sprite is blended exactly as before).
- Any number of atlases can be loaded; `?units=N` in the page url lowers the budget (tests: forces split draws).
- A texture binding outside a run (uploads) clears the unit bookkeeping (`_bind`); `begin` rebinds per frame.
- world.js: the world-map picture is a sheet of its own (it used to borrow the minimap's unit).

## Texture layout and freeing (play.js loadAtlases)
- The sheets of one load are grouped by hi-res set (index.json: the set listing the file; files in no set: one group
  each) and format (GPU-compressed / PNG). A group's sheets (4096 wide, heights powers of two, tools/play_atlas.py)
  are stacked tallest first into textures whose heights are powers of two adding up to the group's total (its binary
  decomposition, each at most 16384). No empty rows; every texture size stays a power of two. Before: fixed
  4096 x 4096 RGBA shared sheets (64 MB each, partly empty) and 4096 x 16384 compressed stacks.
- Each texture remembers its uploads (`info.uploads`: url, rows), so it can be freed (`SpriteGL.suspend`: the id,
  size and sprites stay) and loaded again (`resumeSheet`, from the HTTP cache). A draw that uses a freed texture draws
  nothing there and calls `R.onMissing` -> resumeSheet (the sprite appears a few frames later).
- `evictIdle` (every second) frees: textures of files loaded on demand (gods, monsters, heroes, armies; not in a
  hi-res set) after 60 s without a draw (`EVICT_MS`); the original's textures whose files a hi-res set covers
  completely (`hiresTextures` marks them `covered`) after 3 s without a draw (`COVERED_MS`; a batch built earlier
  that still draws them keeps them). Turning a set back to "original" first loads its originals again (awaited),
  then frees the set's array. Zeus_Fonts stays (191 glyphs are not in the ui set). Every hi-res set change rebuilds
  the ground batch (it holds Zeus_General / Poseidon_Loaded pictures too).
- Decoded PNG images and downloaded .bin buffers are not kept after upload, but Zeus_Interface's image (ui.js
  firstPixels reads the minimap colours from it; every minimap picture is in Zeus_Interface).
- `pagehide` frees every texture and loses the context (`SpriteGL.release`); a page shown again from the
  back/forward cache reloads. Without it a page left by navigation stayed in Chrome's back/forward cache with its
  textures: Chrome's GPU process grew by ~0.4-0.5 GB per navigation with the original sprites, ~2.6 GB with all
  hi-res sets as PNG (measured below; a plain reload did not accumulate).

## Options
Options shows "GPU textures: N MB (original sprites A, hi-res B)" (`gpuMemText`, `SpriteGL.memory()`: bytes as
allocated, resident textures only; hi-res arrays with their 13 mip levels), refreshed when the menu opens.

## Measurements (10-30)
Setup: baseline copy (the baseline save) with a hero's hall + Theseus, monsters Minotaur,
Talos, Maenads (`monster 0 140 150`, `monster 1 156 164`, `monster 2 145 140`), Athena visiting, Zeus and Poseidon
(`godattack`), so 7 on-demand figure atlases are on the map; served paused on :8790 (new) and :8800 (HEAD 3b34d0c in a
worktree, same paused save copy). Headless Chrome 150 (ANGLE Metal, Apple M5 Pro), dpr 1.25, 1280 x 800, fresh
browser per row, one load. "GPU process" = macOS `footprint` of Chrome's GPU process (a blank page: 70-240 MB);
"textures" = allocated texture bytes. Three leftover headless Chromes of earlier agents were running (not ours).

| sprites | textures | before: textures | GPU process | renderer | after: textures | GPU process | renderer |
|---|---|---|---|---|---|---|---|
| original | default (ASTC + PNG) | 449 MB | 979 MB | 632 MB | **354 MB** | 813 MB | 466 MB |
| original | `?tex=png` | 577 MB (Zeus, Poseidon not loaded) | 1147 | 728 | 633 MB (all 7 loaded) | 1152 | 598 |
| all four hi-res (Remacri) | default (ASTC) | 940 MB | 1443 | 640 | **608 MB** | 1041 | 498 |
| all four hi-res | `?tex=png` | 2540 MB | 3137 | 826 | 2080 MB | 2646 | 715 |

After 5 further page navigations in the same tab (gpu_check --startup 5): before 1942 / 4399 / 16384 MB GPU
process (original default / hi-res default / hi-res png), after 740 / 982 / 2574 MB.

Per group, after (allocated; default = ASTC originals, PNG for the interface, fonts and alpha-blended files):

| group | default | `?tex=png` |
|---|---|---|
| terrain (Zeus_Terrain) | 4 MB | 16 MB |
| buildings (General, Greek, Unloaded, Loaded, gods' statues, sanctuaries, ...) | 65 MB + destruction 32 MB | 292 MB |
| figures (SprMain, SprAmbient) + PoseidonImps (PNG) | 24 + 80 MB | 176 MB |
| ui (Zeus_Interface 32, Zeus_Fonts 4) | 36 MB | 36 MB |
| on demand: Zeus 32, Athena / Poseidon / Minotaur / Talos 16 each, Theseus / Maenads 8 each | 112 MB | 112 MB |
| hi-res arrays with mips: terrain 1, buildings 9, figures 11, ui 2 layers | 21 + 192 + 235 + 43 = 491 MB (ASTC) | 85 + 768 + 939 + 171 = 1963 MB |

With all four hi-res sets on, the original's resident textures are only Zeus_Fonts (4 MB), the on-demand figures and
the small canvases (117 MB). Decoded images kept by the page: 260 MB (default) / 584 MB (png) before, 32 MB after.

Startup (play.js STARTUP.ready, headless, same rows, 5-6 reloads): original default before 586-634 ms, after
583-621 ms; hi-res default before 908-2036 (median ~1030), after 893-1229 (median ~995); hi-res png before
4582-5854, after 4519-4683. Unchanged within noise.

## Checks
`tools/gpu_check.mjs` (old code from a worktree of HEAD on its own server, the same paused save): per mode it freezes
the page clock and playhead, walks the camera over the whole map in screen-sized steps (views 0 and 4, zoom 100 % and
200 %: 990 shots per mode) and hashes `gl.readPixels` of the drawn map in a rAF:
- default, original sprites: 990/990 equal to before. Default and `?tex=png` with all four hi-res sets: equal but
  the shots below.
- `?tex=png`: 975/990 equal; the 15 others show Zeus and Poseidon (before: missing or drawn wrong, bugs.md 263);
  the god atlases are PNG in both modes and the default mode, where they loaded before too, is equal.
- `--units 1` / `--units 2` / `--units 3` (split draws) and `--evict` (every atlas texture freed, then loaded again
  on demand): equal to the normal run.
- Hi-res sets switched on and off at runtime: the city frame equals a fresh load with those prefs, and equals the
  start after switching back (before: the ground batch kept stale pictures, so it did not).
- tools/draw_order_check.mjs: 0 out of order (4 views), same as before; drawFrame median 1.2 ms before and after.
- Big things: every shot of the whole map is pixel-equal to before, so the palace, Athena / Apollo sanctuaries,
  walls / towers / gatehouses, villas, stadium, agoras, avenues, docks / wharves / ranch and raised terrain of the
  baseline are unchanged in views 0 and 4 at 100 / 200 %. Not checked: views 2 / 6, bridges (none in the baseline).

Reproduce:

    cp the baseline save $TMP/base.pkl
    python3 -m sim do $TMP/base.pkl "heroes cheat" "build heroes_hall 170 150 theseus" "sendfor theseus" "days 16"
    python3 -m sim do $TMP/base.pkl "monster 0 140 150" "monster 1 156 164" "monster 2 145 140" \
        "godattack zeus" "godattack poseidon" "days 2"          # (Athena visits by herself here)
    python3 -m sim live $TMP/base.pkl --port 8790 --speed 30 &  # pause: POST {"paused": true} to /control, then
    # restart it from the saved (paused) file so every run sees the same tick; old code: a worktree of the old
    # commit (symlink zeus-original, viewer/play/atlas, viewer/sprites) serving a copy on another port
    node tools/gpu_check.mjs http://127.0.0.1:8800/play.html OUT --tag old --tex png,default
    node tools/gpu_check.mjs http://127.0.0.1:8790/play.html OUT --tag new --tex png,default --ref OUT/old.json
    node tools/gpu_check.mjs URL OUT --tag m --tex default --hires remacri --no-pixels --startup 5   # memory, startup
