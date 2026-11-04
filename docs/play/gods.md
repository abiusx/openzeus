# Play mode: gods, priests, bolts, followers (sim/gods; docs/logic/religion.md)

Data: `data/play/gods.json` from `python3 tools/play_gods.py` (after `python3 tools/build_gods.py` and
`python3 tools/sg3.py`'s extracted/sprites). Code: `viewer/play/gods.js` (roles merged over walkers.json, god atlases
loaded on demand), `scene.js` drawArrow (bolts).

Reproduce from scratch (outputs git-ignored: viewer/play/atlas):
```
python3 tools/build_gods.py                 # data/gods.json (tables, frame counts, voices), data/gods/<map>.json
python3 tools/play_gods.py                  # data/play/gods.json
python3 tools/play_atlas.py Zeus_Zeus Zeus_Poseidon Zeus_Demeter Zeus_Apollo Zeus_Artemis Zeus_Ares \
    Zeus_Aphrodite Zeus_Hermes Zeus_Athena Zeus_Hephaestus Zeus_Dionysus Zeus_Hades Poseidon_Hera Poseidon_Atlas \
    zeus_satyr                              # the god sprite files and Dionysus' satyrs (destruction is a default atlas)
```

- **God** (figure 0x43): one sprite file per god; action groups walk / vanish / attack / appear / cast (0x0063A934);
  appear, vanish, attack, cast play as "work" looks (sim `figures.look`, `fight.look`): appear, cast, attack and
  `vanish_gated` (action 4, 0x0F, 0x51) one frame per `ticks_per_frame` (rate 100: data/gods.json `frame_ticks`;
  religion.md "Animation", bug 393), `vanish` (0x0B) and `duel` (0x3C) one a tick. Check: tools/god_rate_check.mjs.
- **Priest** (0x41): SprMain 0x6692 walk, 0x6693 die.
- **Bolts** (0x2D friendly, 0x34 hostile; role `god_bolt`, look "arrow" with the god id): the `destruction` group of
  the god (religion.md "Gods fighting"), 8 frames x 8 directions, direction = `((dir32 - 4 view) & 31) >> 2` with
  dir32 = +0x11 = FUN_0058D050(from, to) << 1 (11-02; oracle 1H-bolt: dir32 30 / 24 -> directions 7 / 6; before: the
  screen angle), rate 100 (ticks_per_frame from the group's image speed, tools/play_gods.py; bug 393), drawn 10 px above the line point (walker_draw 0x0044FEF0 types 0x2D/0x34). Checked 10-29 on a baseline copy
  (headless Chrome, dpr 1.25, 100 %): Athena's red bolt (group 50) flies from her to the invaders.
- **Followers** (0x47, role `entranced`, good = the walker's own role): that role's walk; Dionysus' own three:
  Zeus_Satyr's first group (monster 0x11's walk 0x6201, monster_anim_info 0x00533B60). They walk as
  fig_handler_piper_follower 0x004C9F30 (sim/gods/attack.follower_act): each behind the previous chain member, route
  mode 10, speed 8 / 7; at the leave Dionysus' satyrs walk out by the land entry.
- **Alpha-masked pictures** (gods, satyrs, monsters, heroes, bolts): the exe blends them, (a * src + (31 - a) * dst)
  >> 5 (draw_runs_blended 0x00413E30), and draws a mirrored one 1 px right of the exact mirror (FUN_00414190); play
  mode copies the 1 px (play_atlas.py e[9]) and, since 10-30 (leftovers 3), the blend: tools/play_atlas.py blended()
  stores an opaque pixel (a = 31) one 5-bit step darker and a partly transparent one with alpha (a + 1) / 32 and
  colour image * a / (a + 1), so the premultiplied GL blend gives a/32 image + (31 - a)/32 ground; those files (atlas
  json "blend": 1) stay PNG (tools/hires_compress.py skips them) and gl.js snaps alpha only on GPU-compressed sheets
  (uniform uCmp). Checked with tools/e1_blend_check.py (play mode's SpriteGL over the exe's own ground, readPixels,
  dpr 1.25) on 1H-god g_0080 Athena frame 17 at (246, 276), ground from g_0045: the exe model reproduces all 3422
  pixels; play mode: the 1395 opaque pixels equal (5-bit), the 2027 partly transparent ones within one 5-bit step
  (the exe floors the 5-bit sum; the GPU blends 8-bit values). Hi-res sets: PoseidonImps' hi-res copy is not
  darkened. A god is one picture (the handler clears sprite_extra). Oracle: Athena 1.000 at the rule (1H-god), satyrs
  at the rule +1 (1H-follower), bugs.md 245.
- **Voices**: a god's message carries `voice` (sim/gods `voice`, FUN_005A1050); msgwin.js plays it once when the
  message first arrives (audio.js `godVoice`, the voice stream at the speech volume).
- **Sound effects** (FUN_004DC180: god -> sound group 0x2E.., FUN_005A6FE0; files registered by FUN_005A4CA0,
  gods.json `sounds` from tools/play_gods.py): slot 9 G_<god>_mat when the appear look starts, 10 demat (vanish),
  11 sanctify (a blessing, a help action), 12 curse (the curse's enter); sim gods.look puts the kind at look[10],
  gods.js plays it once, on screen only, panned. Checked 10-29 (headless, sfxAt recorded): Athena's visit plays
  G_athena_mat at the appear's first tick. Ares' 0x22 vanish (written directly, not by figure_set_action) is silent.
- **Figure sounds the looks cannot tell** (10-30): the sim's `walkers.sfx(g, w, kind, until)` collects
  [tick, id, x, y, role, god, kind, until] while the live recorder runs (sim/live.py, frame key `sfx`, like `gone`);
  gods.js plays them on screen, panned: `miss` = G_miss, a god's bolt that reached its end without a hit (0x2D:
  walker_player_missile; 0x34: fig_handler_enemy_missile when no building stands there; FUN_004DC180(god, 13));
  `hit` = G_<god>_hit, a god hit and still alive (figure_hit -> FUN_004DB7A0(god, 7): bolts of a defender, melee);
  `atk` = G_<god>_atk1 / atk2 at random, a god walking into a melee fight (figure_fight_start -> FUN_004DB3D0(god,
  0), sim units.start_fight); `charm` = Aphrodite's / Dionysus' entrancing walk (attack 0x40, 400 ticks):
  god_entrance_roam_tick calls FUN_004DB3D0(god, 0) every tick, and sound_play_sample 0x005C80B0 refuses a sample
  that is still playing, so atk1 / atk2 sound back to back (gods.js: each tick a random one of the two unless it
  still plays). atk3 / atk4 (FUN_004DB3D0 with param 2 != 0) are never asked for a god. Checked 10-30 (headless,
  audio.play recorded, a copy of a sandbox with a palace, :8797): Dionysus' charm starts at tick 2628 and plays
  G_dionysus_atk1 then atk2 (the headless audio context stays suspended, so they never end there); test_gods_sounds
  (Zeus' bolts at Athena: hit and miss events; Dionysus: one charm event, until = tick + 400).
- Oracle shots (10-30): the prayer-result text matches (1H-pray, 0 px, bugs.md 244); Dionysus' followers are in
  1H-follower (re/oracle/scenarios/god-follower.txt), matched 10-30 (bugs.md 245; the "two pictures" theory was wrong:
  the handler clears sprite_extra); blessing / curse / bolt shots: steps in the stage plan 1H.
