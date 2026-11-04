# Campaign screens in play mode (track 1L-4, 2026-10-31)

The original adventures in the browser: adventure select, the episode briefing, the in-game objectives with the
Set aside click, victory, adventure complete, defeat, the colony choice and the next episode's briefing. The rules
live in the campaign module (sim/campaign, docs/campaign-format.md "The campaign module"); play mode draws the exe's
screens and sends the player's choices to the live server, which calls the campaign module (the sim core never
does: tests/test_campaign.py test_campaign_isolated allows the two front ends sim/__main__.py and sim/live.py).

## How to play a campaign in the browser
The first time a browser opens play.html (no leader name stored for that server's origin) the front end shows: the
main menu, Play Zeus, the leader name, then the family menu (below, "Front end"). Later loads go straight into the
city the server runs. File > New adventure (or New Adventure on the defeat / adventure-complete screens) opens the
new-game screens:
1. the family menu: Adventures, Custom Adventures, Tutorials, Return to Roster (the leader-name screen), the Zeus
   logo and the leader's name;
2. a list: **Adventures** = the exe's (Zeus and Europa, Perseus and Medusa, Athens through the Ages, The Voyages of
   Jason, Hercules Labors, The Peloponnesian War, The Trojan War, Open Play Economic / Military / Sandbox); **Custom
   Adventures** = the Zeus adventure folders (Open Play Economic 2, Military 2, Sandbox 2, The Odyssey) and ours
   (Sandbox (ours), Sandbox 2 (ours)); **Tutorials** = the exe's two columns of 8 buttons (a click starts the
   tutorial from Adventures/tutorialNN.sav on its goals screen). Poseidon adventures are not listed (Poseidon off).
   Pick a row, Begin Adventure;
3. the briefing (goals, text, difficulty), To the city: the city starts. Open Play Sandbox / Sandbox 2 and ours
   start as before (POST /control new); every other row starts through the campaign module.
In the city the Goals button (lower panel) shows the episode's goals with their live status; a lit "Set aside" row
asks to set the goods aside. At the month change that meets the goals the victory screen comes up and the city stops;
Proceed plays on: the next episode's briefing, the colony choice on the world map (click a colony, then the arrow),
or after the last episode the adventure-complete screen (New Adventure / Continue building this city / Exit Game).
A lost episode shows the defeat screen a day later: Replay episode starts the episode again (File > Replay episode
does the same in a campaign). The campaign's parent.dat / replay files sit next to the server's save
(`SAVE.parent.pkl`, `SAVE.replay.pkl`; without a save: saves/play/campaign.pkl's).

## Screens (exe, ours, oracle pixel checks)
All checks at 800x600 interface px: dpr 1.25, interface 80 % (one interface px = one device px), tolerance 30
(tools/campaign_check.mjs + tools/screens_compare.py, below). "0 px" = no pixel differs.

| Screen | Exe | Ours | Oracle shots | Result |
|---|---|---|---|---|
| main menu | screen 0: FUN_005900B0 (picture 0x11), FUN_00420240 (draw), FUN_00420120 (clicks) | newgame.js `drawMain` | newgame-flow s1-menu | 800x600: 0 px (the Poseidon logo at its shot frame; other frames 461..566 px in its 95x48 box) |
| leader name | screen 0x36: FUN_00590150 (picture 5), FUN_005901B0 + proceed 0x005E9EC0; proceed FUN_005863D0 | newgame.js `drawLeader` | newgame-flow s2 (empty), s3 ("N") | 800x600: 0 px each (cursor shown) |
| family menu | screen 0x30: FUN_004FDC80 (picture 1, name), FUN_004FDD50 (table 0x0063B858), logo FUN_005860F0 | newgame.js `drawFamily` | newgame-flow s4 | 800x600 with leader "N": 0 px at six logo phases; each bar 224x25 hovered: 0 px (208..210 = 205..207) |
| tutorials | screen 2: FUN_005BE830 (picture 0x14), FUN_005BE860, clicks FUN_005BE720 -> FUN_005BECC0 | newgame.js `drawTutorials` | 1L-tutlist list | 800x600: 0 px |
| adventure list | C++ screen object (measured earlier, screens.md "New game") | newgame.js `drawList` from GET /adventures.json | 1L-europa1 s32 (the exe's 10 rows, Zeus and Europa chosen) | window 352x384 at (8,92): 0 px; description box: ring and inset differ (10696 px, as before: measured, not the exe's drawer), its text 0 px |
| 0x35 briefing | FUN_0052E520 (draw), 0x0052E3D0 (init), 0x0052E500 (To the city) | newgame.js `intro` (also for campaign.js between episodes) | 1L-europa1 s40 (episode 1, scrollbar); 1L-europa-colony g87 (slot 1), g109 (slot 2), h146 (colony Cydonia, two set-aside goals); 1L3-europa-return r170 (slot 3 after the colony) | 640x464 at (80,60): 0 px each |
| 0x3B goals with campaign goals | objectives_screen_draw 0x0052C070; clicks FUN_0052BE10 -> 0x0052BC20 | lists.js `objectives("goals")` | 1L4-goals goals (six poked goals, the Set aside row lit), hover (row hovered), after (Done, ticked) | 592x528 at (4,60): 0 px each |
| 0x3F set-aside confirm | 0x00529CC0 -> FUN_00432380 (5:0x1A in a colony start, else 5:0x1C); yes 0x0052ECF0 | campaign.js `drawConfirm` | 1L4-goals confirm, confirm_hover | 480x160 at (160,140): 0 px each |
| 0x42 victory | FUN_0052D590 (objectives draw + Proceed, rect 0x00640948); Proceed 0x0052DA50 | campaign.js `drawVictory` + `Lists.objectives("victory")` | 1L-europa-colony g81 / g102 / g126 (episodes 1..3), 1L3-europa-return r162 (colony, set-aside rows "0 in stock"), 1L4-complete victory / victory_hover | 592x528 at (4,60): 0 px each |
| 0x43 adventure complete | FUN_0052D7C0 (moved (100, -20); rects 0x00640968: 62:4 / 62:3 / 62:7); Continue 0x00567820 | campaign.js `drawComplete` | 1L4-complete complete, complete_hover | 592x528 at (104,40): 0 px each |
| 0x33 defeat | fullscreen_background_b 0x00422270 (frame, 0xB90 title, the loss phrase) + FUN_00422AB0 (bars 62:4 / 62:35); Replay 0x00421730 | campaign.js `drawDefeat` | 1L3-time-limit t104 ("Too bad, N You have lost ... out of time") | 544x256 at (128,69): 0 px (the player name fed as the oracle's "N"; ours: the leader name, "Front end") |
| 0x34 colony choice | FUN_00421C70, colony_choice_click 0x00421AF0 | world.js `colonyChoice` | 1L4-colony c134 (before a click), c138 (Cydonia picked), c139 (arrow hovered) | panel 186x600: 0 px each (ours at x 598, the exe's at 614: the panel position at 800 wide is ours, bugs.md 216); map 598x570 at (0,30) with ours at k = 1 and the exe's scroll (120, 84): 0 px (c134, c138) |

Not compared: the briefing's difficulty arrows held, the defeat bars hovered and the one-bar defeat (FUN_005678D0()
== 1), a quest row's click (type 4, 11-01: FUN_0052D240 -> the army dialog for the quest, or the quest's text window
0x0052D010; sim/campaign texts.quest_window, lists.js questWindow; no oracle shot), the scrolled briefing.

## What each screen shows (exe-read)
- Goal rows (sim/campaign/texts.py): goal text and status from text group 194 through the goal variables
  (FUN_00525E90 / token fill FUN_00505690; variables 0x005FBA5C: [amount] "%d", [item] group 98, [god] 157,
  [house_level] 28, [finish_date] "%d %s" with 20:0/1, [military_or_better] 138:0x47..0x4A, [diplomatic_status]
  253, [monster] 87, [god_quest] 52, [percent] "%d%%"). The tick box SPR_CHECKBOX 607 / 608 is the screen's own
  per-type test (a time limit is ticked once its year IS reached, as goals_status_update 0x0052B7D0). A type-14 row
  is a button when 0 < need <= the stock in loads (FUN_00529D10): the highlight over the status, 164x20 at
  rect.x - 0x6A. The briefing draws every box empty and shows quest / slay goals as with no event (26 / 27; oracle
  r170 "Slay a monster" while event 0 exists once the episode runs: hypothesis, the briefing comes before the
  episode's events).
- Layout of 0x3B / 0x42 / 0x43 (Lists.objectives): titled frame (ox - 76, oy) 37x33 (0x43: + (100, -20)); title
  22C centred in 0x250 (the adventure's record; 62:0 "Victory" on 0x42 / 0x43); episode line 11C at (+16, +0x2A)
  (0x43: the adventure-complete record's title); city right-aligned in 0x230; marble bar; 0x3B: headers 44:276 /
  44:277, "Right-click to continue" 13:3 at +0x1F8; 0x42 / 0x43: 62:0 centred at +0x40; goals box plain 35 x B; rows
  from the widget table 0x00640830 (430, 84 + 20i) - (594, 104 + 20i): box at (G.x + 0x1B, y + 3), goal at x - 0x1CB,
  status at x - 0x5E (11C2, y + 6); body: the episode's intro (0x3B), its victory record (0x42), the adventure-complete
  record (0x43) laid out as a help page with the scrollbar.
- 0x42 Proceed: RIMS box (ox + 40, oy + 486) 354x20, 62:2 centred at + 6; hovered look over it. 0x43: (ox + 60, oy +
  446) 250x20 New Adventure, (ox + 320, oy + 446) Continue building this city, (ox + 60, oy + 471) Exit Game (ours:
  a toast, as File > Exit).
- The defeat screen: titled frame (ox + 0x30, oy + 9) 34x16; the title phrase 0xB90 "Failure!" (22C) centred in 0x220
  at oy + 0x20; the loss phrase as a paragraph 0x200 wide at (x + 0x19, oy + 0x40) (11C); bars of 9 tiles at
  (x + 0x40 / x + 0x160, oy + 0xE0), labels centred in 0x90 at + 6.
- The colony choice: the colonies not founded yet as SPR_EMP_INACTIVE_COLONY at their map spot (not centred), the
  picked one SPR_EMP_ACTIVE_COLONY, names in red (0xF800) by the object's label side on the marker's size; the side
  panel with the world map's widgets (prev / next / help lit); 62:37 "Select a colony location" (9LTBK, 0xDC wide at
  (panel + 0x12, 0x17A)); after a pick: the name centred (11C, 0x97 at (panel + 0x10, 0x41)), 62:38 "Choose this
  location?", the colony's text (its intro record's subtitle, FUN_0042B890; custom adventures: Colony_N_Selection)
  as a paragraph 0xA0 wide at (panel + 0x14, 0xB9), and the proceed arrow (268) at (screen width - 0x23, 0x172).
- The city stops while a screen is up: the live server does not tick a campaign game whose flow.screen() is set
  (Runner.advance; it steps to the day's end so the month check that wins stops the city right there), and play
  mode's screenPauses() holds the playhead.
- Pause and timing (exe): the victory screen comes from the month check that wins (goals_month_check 0x0052B610);
  the defeat screen at the next day's check (0x00FEB164; oracle 1L3-time-limit: lost at tick 51, the screen at 102);
  ours the same for every defeat (the exe defers only the first one of a session).
- Custom adventures (folders): their texts come from the editor's NAME.txt (Adventure_Title / _Introduction /
  _Complete, Parent_Episode_N_* , Colony_N_*), and their spoken texts NAME_P<n>_i.mp3 (briefing), _v (victory),
  _C<n>_i / _v, _A_v (adventure complete) (GET /audio/Adventures/...).
- Voices (bugs.md 391; sim/campaign/flow.py voices, audio.js screenSound): the screens speak, with a looped jingle.
  Briefing 0x35: its init 0x0052E3D0 calls FUN_005A88C0(0); victory 0x42: FUN_0052D590 calls FUN_005A88C0(1) once
  (flag +4); adventure complete 0x43: FUN_0052D7C0 calls FUN_005A8640 once. Each: the music stream faded and closed
  (FUN_005C86A0: volume -5 every 33 ms), then, only if the voice is on (DAT_00F2A76D) and both files exist
  (FUN_005A0EA0), the voice once on AIL stream 1 and the jingle on stream 0 with loop count 0 (forever) at the music
  volume (FUN_005C8500(file, stream, loops)); flag 0x00F3D208 = 1 keeps the music update (FUN_005A34C0) waiting until
  the voice ends. The city again: episode_start_load (0x00420424, To the city) and episode_won_advance (0x0042197D,
  Proceed) close the voice stream and fade the music; the music update then starts the next city track. Proceed
  also starts Setup.mp3 (FUN_005A3170, when 0x010E4230 is set; not ported, ours: the next briefing's jingle).
  Files: the original Zeus adventures (kind 0) use the table FUN_005A73D0 (at 0x00F2AB58, 0x1D78 per adventure):
  Audio/Voice/Campaign/C<n>_E<m>_i.mp3 (briefing), _v (victory), C<n>_v.mp3 (complete), n = the adventure's
  complete record (DAT_006B3294) - 486 + 1 (C1 Hercules, C2 Jason, C3 Perseus, C4 Trojan War, C5 Athens, C6 Zeus
  and Europa, C7 Peloponnesian War), m = the episode slot (DAT_00F2A7B0) + 1 (colonies E11..E14); every adventure's
  episodes and colonies have their files. Jingles: Music/mission_intro.wav (briefing), mission_victory.wav (victory),
  campaign_victory.wav (complete). Custom adventures (FUN_005A87A0, kinds 1 / 4) name mission_intro.wav for both the
  briefing and the victory, and campaign_victory.wav on the complete screen (FUN_005A84A0 = NAME_A_v). Poseidon
  adventures (kind 3, FUN_005A8830 / FUN_005A83A0: NAME_P<n> / _C<n> _i / _v, FUN_005A85A0 _A_v): off with Poseidon.
  Ours: a page opened on a screen speaks at the first click (the browser starts sound only after a gesture).

## Server (sim/live.py)
- `GET /adventures.json`: flow.adventures() (adventures / custom / tutorials: id, list name, brief and intro records,
  first episode's goal rows, why it cannot start, custom texts, voice) + `maps` (maps_info).
- `GET /campaign.json`: flow.screens(g) (screen, records, city, goal rows, loss phrase, colony options, custom texts,
  voices) + tick + difficulty; `{"campaign": false}` in open play.
- `GET /goals.json`: in a campaign the episode's records, city and goal rows (flow.screens).
- `POST /campaign` (campaign_op): `{"op": "start", "adventure": A, "difficulty": D}` (a new game, its replay file
  written), `{"op": "briefed"}` (To the city), `{"op": "proceed"[, "colony": N]}` (answers `{"choose": [...]}` when
  the colony is needed), `{"op": "stay"}` (Continue building this city), `{"op": "replay"}`, `{"op": "setaside",
  "goal": I}`, `{"op": "win"}` (test command, refused with --no-test-commands).
- `/frames.json` meta `campaign`: a key that changes with the adventure, slot, result, screen and goal count; play
  mode fetches /campaign.json when it changes (docs/play/comms.md).

## Checks (reproduce)
Oracle runs (docs/re/oracle.md "Run", fresh write dir each time; then `python3 tools/oracle_compress.py --shots RUN`):
re/oracle/scenarios/1L4-goals.txt + .poke (--seconds 95), 1L4-complete.txt + .poke (100), 1L4-colony.txt with
1L-europa-colony.poke (150); the older runs 1L-europa1, 1L-europa-colony, 1L3-europa-return, 1L3-time-limit,
newgame-flow. Ours (own port, a copy or a fresh save, not a game in play):
```
python3 -m sim campaign start zeus_and_europa /tmp/c/eu.pkl --difficulty Easy
python3 -m sim live /tmp/c/eu.pkl --port 8781 --speed 120 &
node tools/campaign_check.mjs http://127.0.0.1:8781/play.html --size 640x480 \
  --until "window.Campaign && Campaign.screen()==='briefing'" --wait 1500 --mouse 700,10 --grab 80,60,640,464 /tmp/c/b.ppm \
  --click 600,490 --until "Campaign.screen()===null" \
  --js "await fetch('/campaign',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({op:'win'})})" \
  --until "Campaign.screen()==='victory'" --wait 800 --mouse 700,10 --grab 4,60,592,528 /tmp/c/v.ppm
re/venv/bin/python tools/screens_compare.py /tmp/c/b.ppm re/oracle/runs/1L-europa1/s40.bmp 80,60
re/venv/bin/python tools/screens_compare.py /tmp/c/v.ppm re/oracle/runs/1L-europa-colony/g81.bmp 4,60
```
and so on through Proceed (296,555) for g87 / g102 / g109 / g126, the colony choice (`--js "WorldMap.zoom =
1/WorldMap.view().fit; WorldMap.scroll[0]=120; WorldMap.scroll[1]=84"`, click 297,541; panel grab 598,0,186,600
against the shot at 614,0), h146, r162, r170. The goals / set-aside checks run on a save whose goals are the
1L4-goals pokes and a storehouse with 500 wood (as tests/test_campaign.py test_campaign_screen_texts), opened with
`--js "Lists.open('goals')"`; the 0x43 checks on an episode-1 game with `g.campaign["slot"] = 6` and result 1 (the
oracle pokes the live record's next to 3); the defeat on goal 1 = time limit 0 (1L3-time-limit.poke), the loss
text's "Ruler" replaced by the oracle's "N". The Ghidra decompiles of the functions Ghidra had not made
(0x0052E520 briefing, 0x0052BC20, 0x0052ECF0, 0x0052D620, 0x0052D9D0, 0x0052DA50, 0x00567820, 0x00421730, ...):
`re/ghidra/headless.sh -process Zeus.exe -noanalysis -readOnly -postScript DecompAt.java OUT.c ADDR...`
(re/ghidra/scripts/DecompAt.java creates the function at each address, read-only project).

## Not ported / left (after 1L-5)
- 1L-5 done: tutorials start from their .sav (startable from the Tutorials list); Replay episode as the exe
  (0x00421730, Ghidra DecompAt: a tutorial reloads its .sav through tutorial_load_save; an adventure has 0x006A9C9C
  = 1 (FUN_00423060: (0x0069DFD8 != 0) + 1, 0x0069DFD8 is never written; oracle 1L3-time-limit dump: 1) and loads
  autosave_replay.sav without the briefing: = ours; the other branch, FUN_00420370 = the record's start through
  the briefing, is never taken in the shipped game); difficulty names = text group 153 by g_difficulty + 1
  (0x00436206 / briefing): Beginner = VeryEasy (start funds x 150 %), Mortal = Easy (100), Hero = Normal (100),
  Titan = Hard (100), Olympian = Impossible (80) (table 0x005F7F08 = data/difficulty.json start_funds_pct; oracle:
  Zeus and Europa Mortal 5000 dr, tutorials VeryEasy); the quest goal row lights while its quest is outstanding
  (texts.quest_button, FUN_0052D240 / FUN_00471560); the city's top-left campaign lines are computed by the server
  (/campaign.json `top_left`: won / kind limit|survival / months, top_left_texts_draw 0x0058F130).
- Top-left lines (11-01): campaign.js `drawTopLeft` after the panel (screen_draw 0x00514020), the box through gl.js
  `andRect` (FUN_00509B90: the frame's pixels ANDed with 0x1FE3, RGB555), the mask font SPR_FONTS (DAT_012afbec + 4)
  in the caller's colour (ui.js uiFlushText: opts.color on a mask font = alpha -(2 + colour)); the months come with
  /campaign.json, whose key (sim/live.py campaign_key) changes monthly. Checked (dpr 1.25, interface 80 %):
  time limit vs 1L4-goals city.bmp with the months set to the oracle's 12000000 (its poke leaves the target year at
  its "none" value, year + 1000000): red and black text pixels 0 px (`screens_compare.py tl.ppm
  re/oracle/runs/1L4-goals/city.bmp 0,30 --only 240,0,0 --only 0,0,0 --mask 0,0,300,10 --mask 0,30,300,10`: the 15
  left are dark map pixels, the map under it is another camera), every box pixel = the same frame without the box
  ANDed with 0x1FE3 (3336 px, 0 differ); won line vs 1L4-complete after.bmp: cream 0x7F9A pixels 0 px; survival
  (no shot in the oracle): drawn as the decompile says.
- Tutorials (11-01, bugs.md 349): a tutorial starts on its goals screen 0x3B with the tutorial buttons (flow.screen
  "tutorial", campaign.js -> Lists.objectives; flow.tutorial_nav); vs 1L5-tut00 start.bmp 0 px but 5 (picture).
- Backdrops (11-01): the full-screen pictures behind the screens (FUN_00505310 -> backdrop_jpeg_load, drawn by
  fullscreen_background_b 0x00422270: the 1024 x 768 JPEG centred on the screen; ours: black around it on a larger
  window): ui.js uiBackdrop(key), one GPU sheet replaced per picture, files from `python3 tools/play_backdrops.py`
  (viewer/play/atlas/backdrops/, git-ignored). Briefing 0x35 Zeus_FE_MissionIntroduction, adventure complete 0x43
  Zeus_Victory, defeat 0x33 Zeus_Defeat, the family menu Zeus_FE_ChooseGame, the adventure lists
  Zeus_FE_CampaignSelection (custom adventures: the same, no shot), the tutorials list Zeus_FE_tutorials; the
  episode victory 0x42 and a tutorial's goals screen keep the city. Checked at dpr 1.25 / 80 % (800 x 600): outside
  the windows 0 px vs 1L-europa1 s40 (briefing) and s32 (list), 1L3-time-limit t104 (defeat), 1L4-complete complete,
  newgame-openplay b1; family menu vs newgame-flow s4 and the tutorials list vs 1L-tutlist list by the picture match
  only (the windows differ: the exe's name box and logo, and its tutorial menu of two button columns, not ported).
- Adventure picture (11-01): newgame.js drawList, FUN_004248F0: the header's picture (+0xCC29C, data/campaign
  `header.picture`, /adventures.json `picture`) indexes table 0x005EBBD8: 0 SPR_CAMPAIGN_GENERIC (open plays,
  custom), 1..8 HERCULE, JASON, PERSEUS_MEDUSA, TROJAN_WAR, ATHENS, ZEUS, PELOPONNESIAN_WAR, TUTORIAL, 9..14
  Poseidon_Loaded SPR_POS_CAMP1..6, at (ox + 0x126, oy - 0x23) in a titled ring (ox + 284, oy - 45) 419 x 320. vs
  b1 (GENERIC) and s32 (ZEUS): picture 0 px; the ring differs in its inner fill pattern (~3400 px of thin lines);
  1..5, 7..14 matched by the groups' names only.
- Front end (11-01, bugs 377 / 378, user decision 11-01): see "Front end" below.
- Briefing difficulty (11-01, bug 375): the arrows (table 0x005EF988) set the level taken with "To the city" (POST
  /campaign {op: "briefed", difficulty}; flow.briefed -> sim/episode.py set_difficulty). The exe's g_difficulty
  (0x00F2A988) is global, read live and kept across city loads (FUN_0042B230 / 0x00511C90 save and restore it), and
  the city is built after the briefing (screen_start_game 0x004214F0: leaving 0x35 runs episode_start_load), so a
  new city's funds are scenario funds x start_funds_pct[chosen]; colonies (carried treasury) and continued cities
  only change level. Ours builds the game before the briefing: the catalog is reloaded and a new city at tick 0 gets
  its funds again (test_campaign_briefing_difficulty; CDP: Easy + 2 arrows -> Hard, "Titan" drawn). The general
  Options > Difficulty mid-game (0x0059B200) is not ported (TODO).

## Front end (11-01, bugs 377 / 378)
User decision 11-01: the original's front end shows only on a browser's first open of play.html, i.e. while no
leader name is stored (localStorage "zeus-leader"; per origin, so each server port asks once). Later loads go
straight into the city the server runs; File > New adventure opens the family menu; Return to Roster opens the
leader-name screen. The name is posted to the server (POST /control {"player": NAME}, also on every later load) and
fills [player_name] in the server's texts (sim/messages.py PLAYER, e.g. the loss text, formerly always "Ruler"; one
name per server process, ours; kept in the save as live_player since 11-02, so a server restart keeps it, bugs.md 380) and the message window's addressee (msgwin.js).
- Main menu, screen 0 (newgame.js drawMain): picture 0x11 Poseidon_FE_MainMenu (its two framed boxes are in the
  picture); the animated logos (FUN_005860F0: sprite_anim_step on packed 0x6A8A Poseidon = PoseidonImps group 137,
  3 frames, 0x6A8B Zeus = group 138, 4 frames; speed byte 10 = 200 ms; drawn top-left) at (ox + 0x1B8, oy - 0x30) and
  (ox + 0x46, oy - 0x3C); five bars of table 0x005EB840 ((x1, y1, x2, y2) on the 800x600 screen + (ox - 0x50, oy -
  0x3C)), labels 30:0..4 11C centred at + 6. Clicks (FUN_00420120): Play Zeus -> the leader-name screen (the exe:
  the roster screen 0x2F when players are saved, else 0x36; ours has no roster). Ours: Play Poseidon, Activision
  Website and the Adventure Editor give a toast (Poseidon off; not ported); Quit closes the menus onto the city.
- Leader name, screen 0x36 (drawLeader): picture 5 Zeus_FE_Registry; titled frame (ox + 0x80, oy + 0xA0) 24 x 8,
  31:0 22C centred in 0x180 at oy + 0xAC, 13:5 11C at (ox + 0x17E, oy + 0xFF), the Choose name box (RIMS 25 x 25 at
  (ox + 0x127, oy + 0xF6)) with 13:8 centred in 0xB4 at (ox + 0x91, oy + 0x100), the field (plain (ox + 0xA0, oy +
  0xD0) 20 x 2, the name 11C2 at (ox + 0xB0, oy + 0xD8), the blinking 4 x 2 white cursor at the pen, y + 0xF), the
  proceed arrow at (ox + 0x1D0, oy + 0xF9). Typing: up to 31 characters and under 104 px in SPR_FONTS
  (FUN_005084E0(1, ...)); Enter = Continue; no name: the "No Leader" popup (5:0x5E / 0x5F, one OK button). Ours: the
  field starts with the stored name; Choose name (the roster) does nothing.
- Family menu, screen 0x30 (drawFamily): picture 1 Zeus_FE_ChooseGame (its name box is in the picture); the Zeus logo
  at (ox - 0x41, oy - 0x2D); the name (293:7 "[player_name]") 22C centred in 0x13C at (ox + 0xA2, oy - 0x1C); the
  buttons of table 0x0063B858: Adventures (480, 248), Custom Adventures (480, 277), Tutorials (533, 512), Return to
  Roster (12, 542). The exe's label font is rank 1 = 11C, as ours (bug 377: measured, 0 px). Not drawn: Resume
  Adventure and Load Saved Adventure (the roster's saved adventures; ours: File > Load), Play Tutorial (QA).
- Tutorials, screen 2 (drawTutorials): picture 0x14 Zeus_FE_tutorials, whose solid blue / magenta button slots the
  buttons cover; 293:11 / 293:12 (11C) centred in 0x128 at (ox - 0x10 / ox + 0x168, oy + 5); 8 + 8 bars of 16 tiles
  (tables 0x0065C348 / 0x0065C428 at (85 / 460, 108 + 51 i)), the names 333:k at + (15 / 13, 6) centred in 257;
  Exit tutorial (table 0x0065C328 (12, 561), 293:13) -> the family menu. A click starts the tutorial at once.
- At a large window (1280 x 800 CSS at dpr 1.25: 1600 x 1000 interface px) the Adventures and Custom Adventures lists,
  the briefing and the tutorials were looked at: the 1024 x 768 pictures centred on black, no slot or placeholder
  showing, no row clipped (the lists have 10 and 6 rows of 13).
- Checks: `node tools/campaign_check.mjs URL --size 640x480 --leader none --until "NewGame.state() &&
  NewGame.state().stage==='main'" --wait 1500 --mouse 799,599 --grab 0,0,800,600 s1.ppm --click 220,101 ...`, keys
  through `--js 'NewGame.key({key:"N",preventDefault(){}})'`; compare with `screens_compare.py s1.ppm
  re/oracle/runs/newgame-flow/s1-menu.bmp 0,0` (s2, s3, s4; 1L-tutlist list). tools/play_cdp.mjs stores the leader
  "N" (the oracle runs' player) in every fresh profile unless `leader: null` (campaign_check `--leader none`), so
  the other checks never see the front end.
