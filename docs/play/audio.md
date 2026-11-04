# Play-mode audio: what the original does (2026-10-27)

Data: `data/play/audio.json` (built by `tools/play_audio.py`, run with `re/venv/bin/python3`). Paths are relative to
`zeus-original/app/Audio`. Evidence: decompile `re/decomp/zeus.c` (addresses below), `Audio/sound_fxU.txt`,
`Audio/music.txt`, and eZeus (`refs/eZeus/audio/*`, facts only; eZeus is an approximation, the exe differs).
"Frame" = one call of `game_turn` 0x00513580 (once per rendered main-loop iteration, not per sim tick). The frame rate
is not established here (assume 30 to 60), so the rates below are given per frame.

## 1. Music
Files: 14 general tracks, 4 short + 2 long battle tracks, 4 stingers (`S_mon1/S_mon2/S_dis/S_games.mp3`), `Setup.mp3` (menu),
`mission_intro/mission_victory/campaign_victory.wav` (campaign only: looped under the briefing / victory / adventure-complete narration, docs/play/campaign.md "Voices"). Lists come from `Audio/music.txt` (parser 0x005A3690,
sections GENERAL_MUSIC / COMBAT_MUSIC_SHORT / COMBAT_MUSIC_LONG; a SPECIAL_MUSIC section is parsed but empty).
- Normal play: the general list plays **in file order** (Amolfi, Perifanos, Proi, Tamagia, Eplitha, Eilavia, Pnevma, Mnimio,
  Oyonos, Zoi, Iremos, Afigisi, Naoss, Fengari), then wraps. `FUN_005A31D0` (0x005A31D0) does `idx = idx+1; if idx > count: idx = 0`,
  idx starts at -1. When a track ends, the next starts (`FUN_005A34C0`, called every 6th frame from `game_turn`, counter `DAT_00F9BE4C`). eZeus shuffles; the exe does not.
  Uncertain: off-by-one at the wrap (whether `count` is n or n-1); play it as a plain cycle.
- Combat: `FUN_005A3480` returns true when enemy units alive > 0, enemy warships > 0, or two further unidentified checks
  (`FUN_004E5E50(2,1)`, `FUN_0052EEB0`; probably an active invasion/monster event). Then state 1: `FUN_005A33A0` picks a random battle track,
  **alternating short and long** (toggle starts on short); next track when it ends. Window limit `+0x4E90 = 600000 ms` (init in
  `FUN_005A3A60`); after it expires or the threat ends the interrupted city track **resumes from its saved position** (`FUN_005C9140` seek).
- Stingers `FUN_005A1210(n)` (0x005A1210, state 2, pauses city music then resumes it): n=0,1,4 -> S_mon1; 2,5 -> S_mon2; 3,6 -> S_dis; 7 -> S_games.
  Callers: monster/hero event messages (0x00481430 monster_event_update: 0,1,2; 0x00477ab0: 4), monster slain 0x00481350 (2), 0x0046FFA0 (5, a
  scripted-event message), 0x0046E1A0 (7, games/victory-type message), 0x004474E0/0x0046D790 (3 and 6, disaster messages: 0x102A/0x1029 variants).
  Meaning of 0/1/4 vs 2/5 vs 3/6 is inferred from callers; low confidence. None of this occurs in sandbox play.
  Ported 11-04 (TODO "No sound when Maenads / Achilles arrived"): the same state-2 rule for the god lines
  (FUN_005A1050), the hero arrival line (FUN_005A0F70: Voice/Walker/<0x006469D8 + hero * 0x28>, ach / hec / jas /
  ody / per / the / ata / bel _ev_1.mp3) and the stingers: each plays only from state 0 / 1 / 3 (refused while one
  of them plays) and when its file exists (FUN_005A0EA0); the city track fades out (FUN_005C86A0) with its place
  saved (+0x4E54), and FUN_005A34C0 resumes it there (FUN_005A3220 → FUN_005C9140) once both streams are silent.
  So a god-sent monster plays only its god's line (the FUN_005A1210(0) after the spawn is refused), any other
  monster S_mon1, a slain one S_mon2 (0x00481350 and state 2 of 0x00481430), an arrived hero his line. Ours:
  messages carry `voice` / `stinger` (sim/heroes/events.post), msgwin.js plays them as the message arrives,
  audio.js specials(). The other callers too: disaster_start S_dis (sim/disasters start), 0x0046E1A0 S_games (games
  begin), request_resolve_attitude S_mon2 with 0x8D4 (a quest monster slain in time, sim/empire/requests),
  0x00477AB0 S_mon1 for a city destroyed by a monster (status_events.destroyed); event_sink_land (Poseidon) is not
  ported (docs/logic/events.md).
- Flags: music enable `DAT_00F2A76C`. No crossfade code found (eZeus uses a 1 s fade).
- Sandbox (our case): cycle the 14 tracks in order, once started loop forever; no battle tracks unless we add attacks.

## 2. Ambient
Loader `FUN_005A17E0` (0x005A17E0) reads `sound_fxU.txt` (the `U` build; `DAT_` table at 0x00647xxx).
### Layer 1 (`Ambient/Layer1`, 21 entries, file lines `LAYER1_START`)
Atmospheric loops: winds (7), shimmers, bells/space bells, chimes, a voice, "dark2". Each line: file, jitter, F|S flag, 3-number position scale,
mode letter (L/B/C/R), a, b, direction (CW/CCW/RCW), speed, min seconds, max seconds.
- Trigger (0x005139xx, in `game_turn`): `rand() % 2000 == 1` per frame (`FREQUENCY_L1 2000`), only in normal city view, only if none is already playing
  (flag `+0x5914`); then `sound_listener_update` (0x005A2C30) picks an entry uniformly (`rand % count`) and plays it **in 3D** (DirectSound 3D) for
  a random `secs_min..secs_max` seconds (field value *1000 ms), volume = ambient slider (`DAT_00F2A7D8`), source distance 60.
- Mode letters: R -> L or C at random (50/50), C=2, L=3, B=4; other -> 1. Mode 1 = random point in a box (scale 2,0,2), 2 = orbit round the listener at angle a..b with CW/CCW/RCW (RCW random 50/50) at `speed`,
  3 = one of 8 fixed ring positions (a, b indexes), 4 = at the listener (B: head-centred, e.g. `shimmer7`). The exact spatial maths is **uncertain**; the intent is a slowly
  moving/panning atmosphere. Browser: StereoPanner (or PannerNode) with a slow pan sweep is enough; `jitter` is 0 everywhere (no pitch randomization).
- Extra files in Layer1 not referenced by the list (bird2, bird5, sparrow1, water_space2, wind_02s): not referenced by the list (unused by this loader).

### Layer 2 (`Ambient/Layer2`, 219 files in `CATEGORY` blocks): the "world sounds"
Mechanism = `FUN_005A4790` (0x005A4790), called from `game_turn` with `rand() % 300 == 1` per frame (`FREQUENCY_L2 300`), only in normal city view:
1. Abort if sound is off, enemy units/warships alive, or the two combat-ish checks above are true (no ambience during attacks).
2. Take **3 random screen points** (x in 0..W-10, y in 30..H), convert to a map tile (`FUN_0044A460`; retry until 3 valid tiles).
3. For each tile: if it has a building -> category = building-type field +6 (`FUN_005A4670`, table `g_building_type_info` 0x005F6368, +0x18); else if a
   walker stands there -> animal category (`FUN_005A4710`); else terrain category (`FUN_005A46A0`).
4. Score = `rand(0..weight)` with weight from the `CATEGORY NAME weight` line (50 mostly, 100 SEA/MINT/animals, 40 FOUNDRY/BEAUTIFICATION/CORRAL/HORSE_AGORA, 30 TRIREME/WATER, 20 agora/sanctuary/theatre, 10 DESERT/PHILOSOPHY). Pick the highest of the 3.
   So busy/loud building types win over bare ground, but anything on screen can play. Empty categories are silent.
5. Extra gates on the chosen building: stadium (80) needs workers>0 and a show running; horse ranch (133/134) needs walkers out; corral (216) needs animals;
   race track (199) needs a race flag; a **burning** building plays the fire sample instead (event 7). Enemies alive -> nothing.
6. `FUN_005A14F0(category)`: picks a random file of the category that has **not yet been played in the current round** (bag shuffle: flags per file,
   reset when all were played; up to 200 tries), plays it once at the ambient volume; pan taken from the tile position (the call uses `__ftol()` of a screen value; exact pan formula unverified).
- Terrain categories (`FUN_005A46A0`, flags from docs/logic/map-terrain.md): tree 0x1 -> VEGETATION; rock/cliff/ore 0x300002 -> ROCKY (rumble, rockslides);
  water 0x4 (not off-map 0x80000) -> WATER; meadow 0x800 -> MEADOW (birds); beach 0x10000 -> BEACH (waves); marble 0x20000 -> MARBLE(quarry) sounds; 0x1000000 -> LAVA; else DESERT (silent).
- Animal categories: sheep (figure type 0x31), goat 0x32, boar 0x33 (resource!=1) / deer (resource==1), wolf 0x3B, cattle 0x4C.
- File-loader quirks that change content (faithfully reproduced in the JSON): category names ORCHARD (exe spells it ORHCARD), MARBLE and FARMLAND do not
  match their own slots; unmatched names inherit the previous index. Result: FARMING (cat 2) also holds orchard1/2, rustling*, bird* (17 files); category 44 (MARBLE_QUARRY) holds marble1/2; STONE_CUTTER and ORCHARD slots are empty.
- eZeus approximates this: `egamewidget.cpp:739` plays `playSoundForTile` for a tile within +-3 of the view centre with probability 1/250 per frame when nothing is playing. Use the exe rule above instead.

### Per building (JSON `buildings.<key>`)
- `category` / `ambient_files`: from `g_building_type_info` row +6 (read from the exe for every key in data/buildings.json). `null` = none (roads, walls, bridges, agora/grand agora, empty stall, ruin, monuments, goat/sheep/cattle/grapevine... see JSON).
  Houses: COMMON_HOUSING (wagon/city sounds), ELITE_HOUSING; all sanctuaries/pyramids: SANCTUARY (2 files); gardens, benches, statues, columns, baths...: BEAUTIFICATION (win_chime1/2, recreation1).
- `click`: table built by `FUN_005A3E30` (0x005A3E30, `FUN_005A3DC0(type, file, slot)`): when a building's **info panel is opened** (draw routine `FUN_005720E0`, flag `DAT_00FFA188`,
  panel kind 2 = building) the slot-0 file plays once at the sfx volume (`DAT_00F2A7CC`). It is a single fixed file per type (e.g. house city1.wav, elite house elite1.wav, farms bird5.wav, hunting_lodge hunting1.wav, sanctuaries sanctuary1.wav, palace palace2.wav, beautification recreation1.wav, agora gen1). Poseidon-game type 0x49 uses a different sample (`DAT_010E3BF0`; not in our scope).
  Types without an entry (roads, walls, bridges, ruin, empty stall, monuments) are silent on click.
- Nothing plays continuously from a building: there are **no looping building sounds**, only the randomly sampled one-shots above.

## 3. Walkers
- Walkers make **no ambient footstep/work sounds** in the exe except through the category mechanism (animals) and the info-panel voices.
- Voice lines (`Voice/Walker/*.mp3`, 703 files): `FUN_005A9390/FUN_005A9480` -> `FUN_005A3AD0` play `Voice/Walker/<prefix>_<kind>_<n>.mp3` when a walker's info panel shows a message, row = (panel class, message variant 0..19), table at 0x0064BF94
  (extracted into `walker_voices.table_by_info_panel_class`). Kinds: `i` = intro line, `e` = the "excuse/state" lines of walkers with status messages, `g` = 7 general remarks, `w` = trader walk lines, `ev` = god event lines (`FUN_005A1050`: `zeu_ev_1.mp3`...).
  Prefix hints: imm immigrant, emi emigrant, vag vagrant, pla plague, ovn/oth/omg/ods Olympian-visitor types, nob noble, shp shepherd, fsh fisher, lmb lumberjack, art artisan, fdv/flv/oiv/wiv/arv/htr/chv vendors, trd trader, trs trade ship, act actor, ath athlete, phl philosopher, hlr healer, clk clerk, wtb/wtc water-carrier-ish, hsm/hpl/rbl/tri.
  Mapping class id -> our walker keys: left to the walker/UI work (needs data/play/walkers.json). `warship_*`, `guard_*`, `CHARIOT.mp3` named in the table do not exist on disk (silent).
- When (ported 10-29, bugs.md 213): the land window opening (FUN_005717D0, a click with no building, or on road /
  tree) calls FUN_005ABD00 for the selected figure (the first), and so does a click on a figure box (0x00405E90).
  Row = the figure's thought group g (FUN_004E3750; the walker window's group): g 0x154..0x160 -> table 0x00653254
  row g-0x154, 0x161/0x162 -> g-0x161, 0x163..0x166 -> g-0x163, 0x167/0x168 -> g-0x167 (FUN_005A9480; Poseidon-era
  groups: fruit lodge 340 tdr, deer hunter 341 dht, rancher 342 rch, orichalc 343 mtl, scholars 345..347); other g:
  class g-0xC9 in table 0x0064BF94 (FUN_005A9390, 0 < class < 0x34; gods/heroes 0x43..0x47 have their own tables).
  Column = the phrase Figure+0x7D (FUN_005ABB90, < 20; -1 plays nothing). A figure with no thought group plays its
  animal sound from 0x0065A784 (FUN_005A9250: cattle, sheep, goat, horse, deer, boar, wolf; Ambient/Layer2/*1.wav).
  One AIL stream (slot 1): a new voice closes the one playing; once, at the voice volume. Tell me more plays nothing.
  Data: `walker_voices.by_thought_group` / `.animals` (tools/play_audio.py, files on their disk spelling); play mode
  audio.js `walkerVoice`, the Options speech slider (S.speech / v_speech).
- Voice volume slider `DAT_00F2A7D4`, enable `DAT_00F2A76D`.
- God voices (`G_*` in Wavs, `FUN_005A4C70`): god events only (not sandbox).

## 4. Event and UI sounds (`FUN_005A4B60` registers, `FUN_005A4C00(n)` plays; sfx volume, centre pan 0x40)
| n | file | trigger (caller) |
|---|---|---|
| 0 | Wavs/button.wav | every accepted mouse press (`mouse_poll` 0x0050B470) |
| 1 | Wavs/collapse.wav | `collapse_debris_spawn` 0x004CCD40 (with sound flag) |
| 2 | Wavs/D_Earthquake.wav | earthquake disaster (0x004474E0 region) |
| 3 | Wavs/D_Flood.wav | flood (0x0046D790) |
| 4 | Wavs/D_Landslide.wav | landslide |
| 5 | Wavs/D_Lava.wav | lava |
| 6 | Wavs/place_building.wav | build routine `FUN_00496CA0` after committing a placement (not on rejects) |
| 7 | Wavs/Fire.wav | `buildings_fire_burn_spread` 0x00493140 (each ignition) and `fire_figure_spawn` 0x004CDB50 |
| 0x18 | Ambient/Layer2/recreation1.wav | info panel kind 0xC drawn (`FUN_005720E0`) |
| 0x19 | Wavs/archer_impact.wav, 0x1A Fireball_hit.wav | military only |
| 9 | none | demolish (`clear_land_commit` 0x0049A460 calls it, nothing registered) |
| 0x10 | none | new message (`FUN_00521A70` calls it, nothing registered) |
No error/deny sound exists. Volumes: sfx `DAT_00F2A7CC`, ambient `DAT_00F2A7D8`, voice `DAT_00F2A7D4`, enable flags `DAT_00F2A76B` (sfx), `76C` (music), `76D` (voice).

## 4.1 Combat sounds (11-02, bug 393; data/play/audio.json "combat", tools/play_audio.py)
Table 0x010E0518 [kind * 0x11 + variant] filled by FUN_005A4C70(kind, path, variant) in FUN_005A5D00 / 0x005A4CA0 /
0x005A54A0 (read from the instructions: `samples`; paths the exe names but the disk lacks stay null = silent, as in the
exe). Variants: 1 / 2 attack (FUN_004DB3D0(f, 0), 1 + CRT rand % 2), 3 / 4 missile (FUN_004DB3D0(f, 1) via
FUN_004D9D20), 7 hit (FUN_004DB7A0), 8 die (FUN_004DAB30), 0x10 special. Kind by figure type (`type_kind`, the switches
of those three functions, Zeus game), invaders by army (`army_kind`, FUN_004DC560), Ares' warriors 0x14 (`sanct_kind`),
deer 0x84 (`role_kind`); our roles -> types `role_type` (play_walker_info.ROLE_TYPE). FUN_005A6FE0 plays only for a
figure on screen, sfx volume, panned by screen x. When (play.js fightSounds): the mover's attack at the fight start
(figure_fight_start); enemy infantry at attack_timer 10, hoplites (palace and Ares) at 1 (the handlers' tails); a siege
at anim_frame 1 (figure_check_next_tile); an enemy archer's shot at its frame 1 (0x005011C0); the sim's sfx "hit"
(units.hit / navy.hit: a blow that does not kill) and "shot" (rabble throw, wall sentry, tower ballista); die at the
death look's start. The arrow impact (event 0x19) only plays under the flag 0x00777286, never set in Zeus play: none.
Criminals, watchmen, heroes, monsters, gods keep their own rows (`roles`).

## 5. Browser playability
All 703 `.wav` are RIFF PCM format tag 1, 16-bit, valid headers (checked with Python `wave`): 22050 Hz mono (most), 44100 Hz (9, e.g. sanctuary1, H_achilles_die), 3 stereo
(place_building, water_space2 and one more in Layer2). No ADPCM. All MP3 (music 44.1 kHz stereo 160 kb/s, voices) play in every browser. **No conversion needed.** Serve the files as-is.
Optional (size only): the music is 74 MB; keep it as MP3 (do not re-encode). If a smaller layer-1/2 bundle is wanted later:
`ffmpeg -i in.wav -c:a libvorbis -q:a 3 out.ogg` (not recommended: loses nothing audible but gains little). Names have mixed case (`D_Earthquake.wav`, `drama1.WAV`);
the JSON already holds the real on-disk spelling; the server must serve case-exactly on Linux.

## 6. What the browser player must implement
1. WebAudio context started on first user gesture (autoplay policy); master/music/sfx/ambient gains.
2. Music: HTMLAudioElement or buffer streaming, sequential cycle of `music.city`; optional battle switching later.
3. Layer 2: every frame (or each 33 ms) with p = 1/300: sample 3 random screen points -> tile -> building/walker/terrain category; score `rand(weight)`; play highest;
   per-category bag shuffle; gates (stadium shows, ranch walkers, burning -> Fire.wav, no enemies). Needs a screen->tile query and building category from `audio.json`.
4. Layer 1: p = 1/2000 per frame, one at a time, random of 21, duration per entry `secs_min..secs_max` s, pan sweep.
5. Click on a building: play `buildings.<key>.click[0]` once; UI: `button.wav` on every click; `place_building.wav` on successful placement; `Fire.wav` on ignition; `collapse.wav` on collapse.
6. Voices: done (section 3).

## Uncertainties
- Frame rate used by the probabilities; exact pan/position formulas for layer 1 and layer 2.
- Meaning of the unidentified combat checks (`FUN_004E5E50`, `FUN_0052EEB0`) and of racetrack flags (`DAT_00FF80D5`, `DAT_00FE6A5C`).
- Stinger argument meanings (inferred from callers); music wrap off-by-one; whether `__ftol()` pan is horizontal screen position.
