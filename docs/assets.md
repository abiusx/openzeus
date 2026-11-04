# Assets: the original game's files, out of git (2026-11-04)

**Rule (user, 11-04):** the repo holds no asset or writing of the original game.
A player gets them one of two equal ways, and both give the same files (sha256 per file, `assets/manifest.json`):

1. **Build** them from their own copy of the game (GOG Zeus + Poseidon 2.1.0.10):

       python3 tools/assets.py build --game PATH                    # PATH = the folder with Zeus.exe, DATA/, Model/, ...
       python3 tools/assets.py build --installer setup_zeus_and_poseidon_2.1.0.10.exe   # innoextract first
       python3 tools/assets.py build --game PATH --pack openzeus-assets-hires.zip       # + the hi-res sets

2. **Install** them from the asset pack(s):

       python3 tools/assets.py install openzeus-assets-base.zip [openzeus-assets-hires.zip]   # or URLs

`python3 tools/assets.py verify` checks the tree against the manifest; `pack OUT.zip --parts ...` writes a pack from a
built tree. Python >= 3.14 and `requirements.txt` (numpy, Pillow; the build needs nothing else).

## What is where (classification)

| What | Class | Where it comes from |
|---|---|---|
| sim/, viewer/*.html, viewer/play/*.js, tools/, tests/, scripts/, docs/ | public: ours | git |
| data/*.json, data/play/*.json, ... that hold no text of the game (19 files: allowed, fixes, gods, gods/*, maps, military, monuments, resources, rules, trade, world/*, play/audio, fonts, gods, heroes, monuments, walkers) | public: facts / ours | git |
| extracted/model/building_sizes.json, monument_images.json (exe tables, emulator output) | public: facts | git |
| **assets/templates/** (68 files, 3.7 MB): the JSON below with every string of the game replaced by a reference | public: facts | git |
| assets/manifest.json (path, size, sha256, part of every asset file) | public | git |
| data/**/*.json built from the templates (64 files: messages, messages_condensed, play/help, strings_ui, options, info_panels, walker_info, pages, advisors, world, ui, overlays, military, buildings; campaign/* (42); buildings, houses, difficulty, heroes, empire/*, scenario/*) | asset: build (base) | `assets.py merge` = templates + the game's text files |
| extracted/text/zeus_text.json (Zeus_Text.eng; the sim reads group 19) | asset: build (base) | tools/engtext.py |
| zeus-original/app/Adventures/ (104 files, 65 MB: maps, .pak, tutorial .sav, voices of custom adventures) | asset: the game's own files (base) | your game folder, or the pack |
| zeus-original/app/Audio/ (1,634 files, 276 MB: Wavs, Ambient, Music, Voice) | asset: the game's own files (base) | your game folder, or the pack |
| viewer/play/atlas/&lt;FILE&gt;.json + _N.png (83 sprite files, 194 MB), backdrops/ (8 JPG), world/ (10 JPG) | asset: build (base) | tools/sg3.py -> extracted/sprites -> tools/play_atlas.py; tools/play_backdrops.py |
| viewer/sprites/ (133 PNG, the web viewer's building icons) | asset: build (base) | tools/viewer_sprites.py |
| viewer/play/atlas/*.astc.bin, *.bc7.bin of the 40 sheets compressed.json lists, compressed.json (81 files, 222 MB; the tree's older copies of PoseidonImps / destruction are unused, not listed) | asset: build with encoders, or pack (gpu) | tools/hires_compress.py --originals (astc-encoder-py + bc7e) |
| viewer/play/atlas/hires/ (4 sets: PNG + ASTC + BC7, 1,524 MB) | asset: **pack only** (hires) | the upscaler (ML models + GPU): docs/play/hires.md |
| extracted/model/model_*.json, tax_sentiment.json (Model/*.txt parsed: their file's numbers and record labels) | asset: build (dev, not packed) | tools/model.py |
| extracted/model/figure_handlers, gods, production, resources.json (our RE tables quoting building/figure names) | asset: build (dev) | templates |
| extracted/text/zeus_text.txt, extracted/sprites/ (449 MB of PNG) | asset: build (dev, not packed) | tools/engtext.py, tools/sg3.py |
| extracted/hires/ (4x masters, 1.7 GB), Binks/ (cutscenes), the rest of the game folder | not in any pack | the upscaler / your copy |
| re/decomp/, re/ghidra/projects/, re/oracle/runs/, re/venv/, saves/ | local | made on your machine (docs/re/method.md, docs/re/oracle.md); never in git |

Parts (the manifest's 4th column): **base** (2,121 files, 546 MB), **gpu** (81, 222 MB), **hires** (104, 1,524 MB),
**dev** (11, 1 MB; built, never packed). Packs (11-04): `openzeus-assets-base.zip` = base + gpu, 2,202 files, 768 MB -> 547 MB;
`openzeus-assets-hires.zip` = hires, 104 files, 1,524 MB -> 1,017 MB. One pack would be 1.56 GB, over the ~1.5 GB the user set,
so two: the base pack is all a player needs; the hi-res pack adds the upscaled sprites. Zips are deterministic
(sorted entries, fixed timestamps; PNG/JPG/MP3 stored, the rest deflated): the same tree gives the same zip bytes.

Kept in git on purpose (for the user's review before publishing): short quotations of the game's text in comments,
docstrings, tests and docs (about 30 files, one phrase or sentence each, e.g. sim/game.py "Only one of this
building allowed", tests/test_monuments.py the population milestone titles, docs/play/bugs.md), docs/play/pages_re/*.json
(RE notes quoting UI labels), the exe's phrase names in the templates (PHRASE_..., identifiers in the binary),
adventure file names and titles in data/campaign templates (they locate the .pak files), and single-word names
that are also our identifiers (wheat, armor, N, NE; difficulty names). Our own worlds (data/world/*.json,
data/trade.json) and data/military.json ("Blank") use a few city names the game also has (Sardis, Troy): ours,
not templated (tools/assets.py OURS).

## Templates (assets/templates/)
A template is the runtime JSON byte for byte, except that each string literal that is a text of the game is
`"@{ID}"` (written by json.dumps with \u escapes) or `"@{ID}u"` (written raw). `merge` puts the text back
(byte-identical to the file it came from; tools/assets.py checks this on every split). IDs, read from the player's
own files (tools/assets.py text_pool):

| ID | Source |
|---|---|
| `t:G:I` | Zeus_Text.eng group G, string I (tools/engtext.py; the exe's group numbers) |
| `mm:R:F` | Zeus_MM.eng help record R, field F (0 title, 1 caption, 2 body; tools/play_help.py) |
| `ev:NAME` | Model/Zeus eventmsg.txt, phrase NAME (read as the exe does with its phrase-name table, tools/build_messages.py) |
| `...~n` | the same text with its whitespace collapsed (`" ".join(s.split())`, as build_messages.py stores them) |

A string is replaced when it is one of the game's texts and not one of our identifiers (lower-case ids,
upper-case names, one or two letter tokens, numbers; tools/assets.py `quotable`). The first source wins for a text
that occurs twice (t, then mm, then ev).

### Contributors: editing data
The runtime files stay where they were (data/..., git-ignored), so every reader and builder works as before.
- After a builder rewrites a templated file (tools/build_campaign.py, play_strings.py, play_help.py, ...), or after
  a hand edit of data/buildings.json etc.: `python3 tools/assets.py split` (all templates) or `split FILE`, then
  commit the template. `split --scan` templates any other tracked JSON that quotes the game.
- After editing a template: `python3 tools/assets.py merge`.
- tests/test_assets.py fails when a template and its runtime file disagree (it needs the game's text files, so it
  checks nothing on an asset-pack install).
- When asset files change (a new atlas, a rebuilt sheet, a new template): `python3 tools/assets.py manifest`
  (`--keep hires` keeps the hi-res entries when that part is not in the tree), commit assets/manifest.json, and make
  new packs.
- Builders that read Zeus.exe need pefile / capstone / unicorn (requirements.txt, commented); assets.py itself reads
  the exe's phrase table with the standard library.

## What the build does (tools/assets.py build)
1. game folder: PATH (or PATH/app) must have Zeus.exe, Zeus_Text.eng, Zeus_MM.eng, DATA/, Model/, Adventures/,
   Audio/ (clear error naming what is missing); `--installer EXE` unpacks the GOG installer with innoextract into
   zeus-original/. zeus-original/app becomes a symlink to PATH (a copy where symlinks fail); the sim and play mode
   read Adventures/ and Audio/ there. Zeus.exe's sha256 is checked against GOG 2.1.0.10 (warning if not).
2. tools/engtext.py -> extracted/text/; tools/model.py -> extracted/model/.
3. `merge`: assets/templates/ -> data/... and extracted/model/...
4. tools/sg3.py export of the 83 sprite files play mode loads (`--all-sprites`: every .sg3) -> extracted/sprites/.
5. tools/play_atlas.py, play_backdrops.py (+ the world map pictures), viewer_sprites.py.
6. GPU sheets `--gpu pack|build|skip` (default: pack with --pack, build when astc-encoder-py (`--encoder-python
   PY`) and bc7e (`--bc7enc PATH`, default .cache/bc7enc/bc7e) are there, else skip: play mode then loads the PNGs).
   Hi-res `--hires pack|skip|upscale` (default: pack with --pack, else skip: Options shows no hi-res sets).
   `upscale` runs docs/play/hires.md "Pipeline" (ESRGAN models in $ZEUS_ESRGAN or .cache/esrgan, ~25 min on a GPU);
   ML output differs in the last bits between devices, so it is not byte-identical to the pack (not run 11-04).
7. verify against assets/manifest.json (`--strict`: exit 1 on a difference). PNG bytes depend on the Pillow/zlib
   version: requirements.txt pins the one the manifest was made with (12.2.0).
Idempotent: a second run rewrites the same files. ~30 s on an M5 Pro (+ ~55 s with `--gpu build`).

## Test (11-04, both paths from clean clones)
- First run (`build --game zeus-original/app`): 3 files differed from the working tree, SprMain/SprAmbient/Zeus_Greek.json,
  built 10-27 before tools/play_atlas.py wrote the blend flag on mirrored entries (same drawing; the tree has the new
  ones now). compressed.json differed only by its version, the clock (now a hash of the sheets: tools/hires_compress.py,
  hires_derive.py content_version). The tree also held stale .astc/.bc7 copies of PoseidonImps and destruction that
  compressed.json does not list (play mode never loads them): not assets any more.
- (i) `git clone`; `assets.py build --installer setup_zeus_and_poseidon_2.1.0.10.exe --gpu build --encoder-python
  re/venv/bin/python --hires pack --pack (hi-res pack of the working tree) --strict`: 2,317 of 2,317 files as in the
  manifest (the 81 GPU files re-encoded byte-identical: the encoders are deterministic on one machine); 72 s; a
  second run the same (idempotent). Tests 174 ok, tools/state_hash.py full fa59525c..., own server on a copy of the
  baseline save, headless Chrome at dpr 1.25: the city drawn (readPixels: 99 % non-black, ~10k colours).
- (ii) a second clean clone, `assets.py install` of the two packs written from (i): 2,306 files in 5 s (again: 0
  written); same tests and hash; screenshot with the original sprites and with all four hi-res sets on (loaded:
  terrain, buildings, figures, ui; 12k colours).
- (iii) every manifest file of base + gpu + hires (2,306) byte-identical between (i) and (ii). Packing the same tree
  twice gives the same zip (sha256).
- Errors: a folder without Zeus.exe, an incomplete game folder (lists what is missing), a zip that is not a pack, a
  missing pack: one-line messages, exit 2.
