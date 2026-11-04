# Hi-res sprites in play mode (2026-10-28)

**Decision (user, 10-28):** Remacri for every sprite. The model runs once at 4x per side; those masters are
kept (`extracted/hires/`, git-ignored, ~2 GB PNG) and play mode loads a 2x-per-side copy made from them by
`tools/hires_derive.py` (box filter, alpha snapped to 0/128/255): ~1.2 GB of GPU texture (+1/3 mipmaps),
about 4x the originals' sprite pixels; 4x in game would be ~5 GB. The originals stay selectable per set.
Sets: terrain (Zeus_Terrain; ground tiles keep blocky alpha and a ring of neighbour context), buildings
(every building/monument/god/statue atlas), figures (SprMain, PoseidonImps, SprAmbient), ui (Zeus_Interface and,
from 10-29, the Zeus_Fonts glyphs; Options "Hi-res text" keeps the original glyphs with the hi-res ui).
GPU-compressed (ASTC / BC7) copies of every hi-res sheet and of the original's own atlases (10-29, below).

## Reproduce from scratch
Players get the hi-res sets from the asset pack (docs/assets.md, `tools/assets.py build --hires pack` or `install`);
`tools/assets.py build --hires upscale` runs the steps below (2-3, and 4 when the encoders are there). The
`version` of hires/index.json and atlas/compressed.json is a hash of the sheet files (11-04; it was the clock), so
the same sheets give the same json.

Inputs: the original game (GOG Zeus + Poseidon 2.1.0.10, unpacked to `zeus-original/`, README) and the sprites
extracted from it (`extracted/sprites/<FILE>/atlas.json` + PNGs, docs/extraction-plan.md). Then:

    # 1. models + python (any folder; the tools take --models DIR or $ZEUS_ESRGAN)
    mkdir -p $ESR && cd $ESR && python3 -m venv --system-site-packages venv && venv/bin/pip install spandrel==0.4.2
    for f in 4x-UltraSharp.pth 4x_foolhardy_Remacri.pth 4x_NMKD-Siax_200k.pth 4x_NMKD-Superscale-SP_178000_G.pth; do
      curl -sL -o $f https://huggingface.co/uwg/upscaler/resolve/main/ESRGAN/$f; done
    shasum -a 256 *.pth     # must match the table below
    # 2. 4x masters (Remacri), ~25 min on Apple MPS; the full set lists are in "Pipeline" below
    ZEUS_ESRGAN=$ESR python3 tools/upscale_sprites.py --scale 4 --out extracted/hires --methods remacri --set ...
    # 3. the 2x copies play mode loads, ~1.5 min (writes viewer/play/atlas/hires/ + index.json with sheets, version)
    python3 tools/hires_derive.py --scale 2
    # 4. GPU-compressed copies (ASTC 4x4 for Apple GPUs/mobiles, BC7 for Windows/Linux GPUs), hi-res sets with
    #    their mips (~3 min) and the original's own atlases (~1 min); play mode prefers them
    python3 -m venv re/venv && re/venv/bin/pip install astc-encoder-py==0.1.12 numpy pillow texture2ddecoder==1.0.6
    sh tools/build_bc7enc.sh          # -> .cache/bc7enc/bc7e (bc7enc_rdo + ISPC, pinned; see the script)
    re/venv/bin/python tools/hires_compress.py --bc7enc .cache/bc7enc/bc7e
    re/venv/bin/python tools/hires_compress.py --bc7enc .cache/bc7enc/bc7e --originals

| file | sha256 |
|---|---|
| 4x_foolhardy_Remacri.pth (the one used) | e1a73bd89c2da1ae494774746398689048b5a892bd9653e146713f9df8bca86a |
| 4x-UltraSharp.pth | a5812231fc936b42af08a5edba784195495d303d5b3248c24489ef0c4021fe01 |
| 4x_NMKD-Siax_200k.pth | 560424d9f68625713fc47e9e7289a98aabe1d744e1cd6a9ae5a35e9957fd127e |
| 4x_NMKD-Superscale-SP_178000_G.pth | 1d1b0078fe71446e0469d8d4df59e96baa80d83cda600d68237d655830821bcc |

Versions used (10-28): Python 3.14.6, torch 2.14.1 (MPS), spandrel 0.4.2, numpy 2.5.0, Pillow 12.2.0, macOS
(Apple silicon). Compression (10-29, re/venv: Python 3.14.6, numpy 2.5.4, Pillow 13.0.0):
- astc-encoder-py 0.1.12 from PyPI (https://pypi.org/project/astc-encoder-py/0.1.12/), wheel
  astc_encoder_py-0.1.12-cp37-abi3-macosx_11_0_arm64.whl sha256 b7fdd11d997610da9e64a91bb031a5e18f41cfd20315763019fb14227b461c85
  (ARM astcenc inside; preset medium, 8 threads).
- bc7enc_rdo (https://github.com/richgel999/bc7enc_rdo, commit b9438627eef73a1157e84201b6fa6eb2ffd6d9f0) with its
  bc7e.ispc encoder compiled by ISPC 1.32.0 (https://github.com/ispc/ispc/releases/download/v1.32.0/ispc-v1.32.0-macOS.arm64.tar.gz,
  sha256 efc5180095554628c01022507329ba7a2141c7ba97cf1bccc2df85dc47874e02, target neon-i32x8), Apple clang 17.0.0,
  no OpenMP; all of it by tools/build_bc7enc.sh. Flags `-U -u4`.
- texture2ddecoder 1.0.6 (PyPI): only for the checks (tools/hires_check.py compressed decodes the blocks). ML output may differ in the last bits on other devices (GPU float math); the pipeline is
otherwise deterministic (context patches use a fixed seed). The weights' licences are the model authors'
(check before any release; the decision log).

## GPU formats, loading, and a native engine (findings 10-28)
- The user's browser (Chrome 152, ANGLE Metal, Apple M5 Pro) exposes EXT_texture_compression_bptc (BC7),
  WEBGL_compressed_texture_astc (profiles ldr, hdr), s3tc, s3tc_srgb, rgtc, etc, etc1, pvrtc. So one machine can
  take ASTC or BC7; in general Apple GPUs/mobiles have ASTC, Windows/Linux desktop GPUs BC7 (s3tc).
- Decision (user): precomputed is best ("the scripts and source mats are there anyways"); a few seconds less per
  start makes testing faster. So the compressed copies are built once by tools/hires_compress.py, never on load.
- Where load time went: PNG decode on the CPU, mip levels (JS, then GPU), uploads of uncompressed RGBA (4 bytes a
  texel), and the original's atlases loaded one file after another. Profile now (warm cache): startup files
  0.2 s, the original's atlases 2.1 s, all hi-res sets (ASTC) 0.25 s, world on screen ~2.7 s (was 12.7 s).
- Browser vs a native engine (e.g. Godot), for loading and GPU memory: the gain is the asset format, not the
  engine. Godot imports textures once into GPU-compressed formats (S3TC/BPTC on desktop, ASTC on Apple/mobile)
  with mips, and loading is a read straight into GPU memory; the browser does the same with precomputed
  ASTC/BC7 (what we do now) or KTX2/Basis (one file, transcoded on load). Drawing a few thousand sprites a
  frame is trivial for both. Uncompressed 4x of every sprite is ~5 GB of GPU memory, ASTC 4x ~1.3 GB.

## Pipeline (all sprites, 10-28)
    # 4x masters, one model run (~25 min on MPS; extracted/hires/, 1.7 GB)
    python3 tools/upscale_sprites.py --scale 4 --out extracted/hires --methods remacri \
        --set terrain --alpha auto --context 1 Zeus_Terrain \
        --set buildings --alpha auto destruction Poseidon_AtlasStat Poseidon_GrandStatue1 Poseidon_GrandStatue2 Poseidon_GrandStatue3 Poseidon_HeraStat Poseidon_Loaded Poseidon_Sanctuary3 Poseidon_Unloaded Zeus_General Zeus_God01 Zeus_God02 Zeus_God03 Zeus_God04 Zeus_God05 Zeus_God06 Zeus_God07 Zeus_God08 Zeus_God09 Zeus_God10 Zeus_God11 Zeus_God12 Zeus_Greek Zeus_Sanctuary1 Zeus_Sanctuary2 Zeus_Sanctuary3 zeus_statcon1 Zeus_Unloaded \
        --set figures --alpha auto SprMain PoseidonImps SprAmbient \
        --set ui --alpha auto Zeus_Interface $G       # G = the 17 font groups, see "Fonts"
    # the copies play mode loads (viewer/play/atlas/hires/, 476 MB; ~1.5 min)
    python3 tools/hires_derive.py --scale 2 [SET...]
- A set's files are packed together on shared 4096 sheets (`<set>_<n>.png`), one json per atlas file.
- `--alpha auto`: block alpha (the original's outline) for pieces that must tessellate (every terrain tile, tall
  ones too, and every interface piece: Scale2x alpha rounds staircase/tile corners, so neighbours leave dotted
  gaps, bugs.md 74, 87), Scale2x outline for the rest (buildings, figures).
- Dithered foliage (bugs.md 129): `PREBLUR` in tools/upscale_sprites.py blurs the model input colour (Gaussian,
  sigma 0.5 original px) of SPR_GRAPEVINE, SPR_OLIVE_TREE (Zeus_General) and SPR_FRUIT_TREE (Poseidon_Loaded):
  their art is single-pixel dither and Remacri turned each dot into a white/black/pink highlight. A full run applies
  it; to redo only those sprites in existing masters (10-28, ~1 min), then re-derive and re-compress the set:

      python3 tools/upscale_sprites.py --scale 4 --out extracted/hires --methods remacri --patch \
          --set buildings --alpha auto Zeus_General@SPR_GRAPEVINE Zeus_General@SPR_OLIVE_TREE Poseidon_Loaded@SPR_FRUIT_TREE
      python3 tools/hires_derive.py --scale 2 buildings
      $ENC/bin/python tools/hires_compress.py buildings
- Large sprites go through the model in 192 px tiles (16 px overlap) so its 4x activations fit in memory.
- Fonts are in the ui set (10-29). 2x layers: terrain 1, buildings 9, figures 11, ui 2 (23 x 4096^2, ~2 GB with mips
  when all four sets are on). Startup with all four: ~6 s (downloads start at page load, in parallel with the
  original's atlases; mips are drawn on the GPU, gl.js MIP_FS); it was ~13 s with JS-built mips.
- The 2x copy decides alpha per 2x2 master block by counts, not by mean (a half-covered outline block averaged
  to 128 = shadow = black: dotted outlines, bugs.md 77). Sheet urls carry `?v=<index.json version>`.

Below: the test pipeline that led to Remacri (the 4x test sets are gone).

## Build
    python3 tools/upscale_sprites.py [--models DIR] [--methods nearest,scale4x,...] [--out DIR]
            [--set NAME [--alpha nearest|scale4x] [--context N] SPEC ...]...
SPEC: `FILE:A-B` (atlas indices), `FILE@GROUP`, `walker:ROLE` (its blocks in data/play/walkers.json).
Without `--set` it builds the two sets above (~1 min on MPS). `--models` is the folder with the .pth weights
and a `venv/` with spandrel + torch (the tool re-runs itself with that python); default: `$ZEUS_ESRGAN` or
`.cache/esrgan/` (git-ignored; download the weights there as in step 1).

Per sprite:
- shadow (pure red) -> black at 50 % alpha, as tools/play_atlas.py;
- colour into the model with transparent pixels filled from their neighbours (no dark edge pulled in);
- alpha: `scale4x` (figures: Scale4x of the original's alpha, crisp smooth outline) or `nearest` (tiles: each
  original pixel's alpha as a 4x4 block, so tiles keep the exact outline and still tessellate);
- `--context N` (terrain default 1): the tile is upscaled inside a ring of random tiles of its group and cropped.
  Without it the model sees an isolated diamond and paints big brush strokes; with it, fine grass blades.
  Seams were measured both ways (|dRGB| between horizontal neighbour texels across tile joins vs inside tiles,
  6x6 patches): every ML method lowers the join/interior ratio below the original's own (IN_FILL1: original
  8.1, isolated ML 1.7-3.6, context ML 2.2-3.0), i.e. no join is sharper than the texture around it.
- every sprite sits in a 4-aligned cell with 4 texels of bled colour around it, so mip levels 1-2 never mix two
  sprites and level 2 is exactly one texel per original pixel.

Output (git-ignored, served by the play server): `viewer/play/atlas/hires/<set>/<method>/<FILE>.json` +
`_<n>.png`, same layout as the play atlas plus `"scale": 4` (x, y, w, h, anchors in hi-res texels), and
`viewer/play/atlas/hires/index.json` (sets, methods, labels). Size: ~230 MB (git-ignored).

- Outline band of ground tiles (tools/hires_derive.py `fix_edges`, 10-29, bugs.md 171): the model paints halos
  on the diamond outline (the context ring is random tiles), so every seam showed single light/dark texels in a
  dotted line (Remacri, beach and shallow water, from ~300 %). Before shrinking, each opaque master texel of a
  Zeus_Terrain flat tile (height <= 30 per tile) within 4 texels (1 original pixel) of the outline is clamped to
  its original pixel's colour +- 12 per channel (865k texels). Read back at dpr 1.25 near (111,113): outliers
  (|L - mean of 4 neighbours 3 px away| > 25) per 1000 seam pixels vs off-seam pixels, Remacri: v0 500 % 0.81 /
  0.17 (was ~1000 light dots on the screen), v2 0.45 / 0.15, v4 0 / 0.04, v6 0 / 0.02; 200 % v0 30 / 37, v4 6.3 /
  6.5 (texture, not seams); the original's terrain 0 / 0 at 500 %. Filters (mips, nearest) make no difference:
  the halos were in the texels. Rebuild: `python3 tools/hires_derive.py --scale 2 terrain`, then
  `tools/hires_compress.py terrain` (until it is rerun, index.json has no `compressed` entry for terrain and
  play mode loads the PNG).

## Renderer
- `sprite(file, i)` returns the hi-res variant when its set's method is not "original" (`HIRES.over`). A hi-res
  sprite has the original's world `w, h, ax, ay` plus its texel size `uw, uh`; `Batch.push` uses `uw, uh` for
  the UVs. Same world rect, 4x the texels; the per-sprite UV clamp is unchanged (half a texel in).
- Each set's sheets are the layers of one 4096x4096 texture array (gl.js `hiAlloc`/`setHiLayer`, the last 4 texture
  units, sheet id 1024 + set * 64 + layer; switching a set to "original" frees it). While a set is on, the original's
  textures it covers completely are freed (docs/play/gpu.md).
  Crops of a hi-res sprite go through `subSprite` (offsets in world px, texels scaled); colour lookups that read
  the original's pixels (minimap) use `sprite(file, i, true)`.
- GPU-compressed sheets: see "GPU-compressed sheets (10-29)" below.
- Loading shows a progress box (`#hiprog`, play.js `hiresProgress`): per set, sheets downloaded (30 %) then
  layers prepared (70 %, one per repaint); at startup "N of M" sets
  and an overall bar on top, each set weighed by its layer count (index.json `sheets`, from tools/hires_derive.py). Mip levels are built by hand: colour
  alpha-weighted, alpha = max of the 2x2 (generateMipmap's mean alpha left dark seams between ground tiles when
  zoomed out, bugs.md 68). Filter (Options): `mipmaps, crisp` (default: NEAREST_MIPMAP_NEAREST),
  `trilinear`, `nearest (no mips)` (point-sampled minification: shimmer at 100 %).
- Ties: hi-res sheets and the ground batches add 1/512 texel to the UVs (gl.js `uBias`, and in the vertex shader for sheet ids >= 100), bugs.md 62.

## Switch in game
- Options menu (bottom bar, `Options ▾`): `Hi-res walker`, `Hi-res terrain` (Original + the six), `Hi-res filter`.
- Keys: `H` cycles the immigrant's method, `Shift+H` the terrain's (a toast names it).
- Kept in the prefs (`polis-play` localStorage, `hires: {choice, filter}`); default Original.

## Test results (Chrome, own server :8795, dpr 1.25, tab muted)
- Placement/size: every one of the 104 immigrant images at 100/200/400 % and 3 positions (fractional, half,
  whole): `nearest` hi-res is pixel-identical to the original (312/312 per zoom, same tie rule). All methods:
  bounding box identical to the original's (0 px difference); coverage IoU 0.91-0.97 (Scale4x alpha rounds the
  staircase outline). Live: 200 walker instances over 40 frames drawn from the hi-res sheet, 0 draw errors.
- Edges: no dark halo. Mean luminance of the outline ring on grey / white backgrounds: original 86 / 115,
  ML 101-102 / 162-165 at 100 % (the mipmapped outline is partly transparent, so lighter), equal at 400 %. The
  original's black outline pixels drop from 18 % to 7 % of the ring at 100-200 % (softer outline).
- Ground joins: 0 black pixels with every method over 12 camera offsets x 8 zooms x 2 places (bugs.md 62).
- Colour: the drawn ground = the texture bytes (400/400); the "washed out" look is the original art (bugs.md 61).
- Shimmer (offline, walk cycle, mean |dRGB| between consecutive frames, opaque texels, vs nearest = real motion):
  scale4x x1.01, UltraSharp x1.39, Remacri x1.49, Siax x1.77, Superscale x1.82. The ML models invent detail
  per frame (folds, highlights) that changes frame to frame; Siax adds the most texture (Laplacian 61 vs 35).
  At 100 % the mips average most of it away; at 400 % it is visible. Scale4x is stable but adds little.

Contact sheets of one run: walker (4 frames facing S per method) and a 3x3 grass patch per method were written
to the session scratch folder (not kept).

## Fonts (tried 10-28; in the ui set since 10-29)
Shipped 10-29: the 17 font groups (2,412 glyphs) are upscaled with the ui set (Remacri, Scale4x alpha: `auto`
gives them `scale4x`, they are not interface tiles) and derived with it; the 2x ui set still has 2 layers
(masters: 6 sheets). Options "Hi-res text: upscaled / original" (prefs `hires.text`) keeps the original glyphs
while the ui set is hi-res; with the ui set on "Original" both are the original's. Text needs no code change
(text.js draws glyphs through `sprite()`). Checked at dpr 1.25 in play (below, "Checks 10-29").
History (10-28):
The UI text is drawn from Zeus_Fonts glyphs (data/play/fonts.json, viewer/play/text.js) through `sprite()`, so a
hi-res set holding Zeus_Fonts would apply to text with no text.js change (mask fonts are tinted from alpha).
Tried on all 17 font groups (2,412 glyphs, alpha by Scale4x of the original's): nearest, Scale4x (EPX, the
ScaleNx family) and Remacri, each ~1 min:

    G=$(python3 -c "import json;a=json.load(open('extracted/sprites/Zeus_Fonts/atlas.json'));print(' '.join('Zeus_Fonts@'+g['name'] for g in a['groups'] if g['name'].startswith('SPR_FONTS')))")
    python3 tools/upscale_sprites.py --scale 4 --out extracted/hires --methods nearest,scale4x,remacri --set fonts --alpha scale4x $G
    python3 tools/font_samples.py          # -> extracted/hires/fonts_sample.png (a sentence per font and method, at 2x)

Result (sample sheet, 5 fonts x 3 methods): both smooth the staircase diagonals of S, 2, 3, 7, O, W at 200 %.
Scale4x keeps the original's crisp 2-tone edge and exact stroke widths; Remacri is softer and slightly rounder
(the big 22C font looks best with it; the 9-px fonts lose a little contrast). Neither smears glyphs. xBRZ was not
tried (no implementation in the toolchain; a pip package would be a new dependency). Better than the blocky
originals, but not shipped (then): play mode had room for 4 hi-res sets only (gl.js HI_SETS: texture units 12..15,
units 0..11 held the original's sheets), all taken (terrain, buildings, figures, ui). To ship: fold Zeus_Fonts
into the "ui" set (rebuild ui's masters with the font groups added, one method for UI and text) or free a unit
for a fifth set; then `tools/hires_derive.py --scale 2 ui`. The 4x font masters stay in extracted/hires/fonts/
(git-ignored); the play index does not list them.


## GPU-compressed sheets (10-29)
tools/hires_compress.py writes, per hi-res sheet, `<set>_<n>.astc.bin` and `<set>_<n>.bc7.bin`: the sheet padded
to 4096 and its 13 mip levels (our max-alpha rule), 4x4 blocks of 16 bytes, levels back to back; with
`--originals`, `<FILE>_<n>.astc.bin` / `.bc7.bin` of the original's own atlas sheets (level 0 only: drawn 1:1,
no mips) and `viewer/play/atlas/compressed.json` (formats, sheet sizes, version). Zeus_Interface and Zeus_Fonts
stay PNG (their pixels are compared 1:1 with the exe's screenshots; ui.js reads minimap colours from the
interface image).
- Format per browser (play.js `texFormat`): ASTC with WEBGL_compressed_texture_astc (Apple GPUs, mobiles), else
  BC7 with EXT_texture_compression_bptc (Windows/Linux desktop GPUs), else PNG. `?tex=astc|bc7|png` in the url
  forces one. Hi-res sets use it whenever they are on.
- **The original's own sheets are compressed by default** (user 10-29: "if it's slight variation it's fine"; the
  10-29 PNG default before it). Measured on scrub-granary (new sandbox + granary at 150,141, camera 114,272) against
  the exe's shot, map area 10..590 x 80..580, max channel difference per pixel:
  | | exact | <= 4 | <= 8 | <= 16 | <= 32 |
  |---|---|---|---|---|---|
  | PNG | 0.1 % | 14.7 % | 97.2 % | 97.2 % | 97.2 % |
  | ASTC | 0.0 % | 13.3 % | 67.9 % | 96.0 % | 97.2 % |
  - The exe renders in 16-bit colour (RGB565: every red/blue of its shot is a multiple of 8, green of 4); rounding
    ours the same way puts 100 % of the map within 4. So PNG is exact up to the exe's colour depth.
  - The 2.8 % beyond 32 is not the map: a 20-row strip at the top of the exe's shot (y 80..100, a screen element
    there) plus a few granary edge pixels. ASTC adds up to 16 levels (of 255) on about 28 % of pixels.
  - Options "Original sprites: exact (PNG)" (prefs `hires.origPng`, next load) or `?tex=png` keeps the PNGs;
    tools/oracle_view_compare.py adds `?tex=png` itself (`--tex`).
- Loading: hi-res sets go straight into their texture arrays (gl.js `hiAlloc(.., fmt)`, `setHiLayerCompressed`);
  the original's sheets are stacked into compressed textures (`addEmptySheet(.., fmt)`, `subCompressed`; layout and
  units: docs/play/gpu.md). No PNG decode, no mip pass, 1 byte per texel.
- Alpha: every sheet holds only 0, 128 (shadow) and 255. Compression gets some texels wrong, so the fragment
  shader snaps alpha back (gl.js): within 0.25 of a level on the original's sheets and on hi-res sheets with the
  nearest-texel filters, within 0.04 with the trilinear filter (filtered alpha is legitimately in between).
- BC7 encoder: bc7enc_rdo + bc7e.ispc (tools/build_bc7enc.sh), quality `-u4` (`-u6` took 3.6x as long for 6 %
  less colour error). etcpak 0.9.15's compress_bc7 (tried 10-28, "crashed") ran on 10-29 but its alpha was exact
  on only 93 % of texels. bc7enc_rdo with OpenMP (libomp) spun for minutes per sheet on 10 cores; the build has no
  OpenMP and hires_compress.py runs one process per core instead.
- The original's sheets are bled before encoding (colour under transparent texels from their neighbours; never
  drawn): BC7 alpha errors > 63 on Zeus_General_0 went from 599 to 40.

Quality (tools/hires_check.py compressed: level 0 decoded with texture2ddecoder vs the PNG; alpha "off" = by more
than the shader's snap of 63):

| sheets | format | mean abs dRGB, opaque texels | alpha off > 63, covered texels |
|---|---|---|---|
| hi-res, 23 sheets (386 M texels) | ASTC | 1.85 | 219 |
| | BC7 | 1.71 | 747 |
| original's atlases, 43 sheets (141 M texels) | ASTC | 3.80 | 1,817 |
| | BC7 | 3.65 | 6,216 |

(The figure 0.55 noted on 10-28 for one ASTC sheet does not reproduce with this decoder: figures_0 gives 2.27.)
Encoding: hi-res sets ~2.5 min for both formats (18-core M5 Pro), originals ~1 min.

## Startup (10-29, Chrome 152, M5 Pro, dpr 1.25, warm cache, save H copy on :8811)
play.js `STARTUP` (ms since navigation, read after load): maps, atlases (the original's), hires, ready.

| hi-res sets | textures | atlases loaded | ready |
|---|---|---|---|
| none (original) | PNG (before) | 1.90-2.05 s | 2.21-2.29 s |
| none | ASTC | 0.24-0.25 s | 0.38-0.40 s (first load 0.74 s) |
| none | BC7 | 0.39-0.61 s | 0.55-0.84 s |
| all four (remacri) | PNG everything | 3.8-6.4 s | 11.4-20.8 s |
| all four | ASTC everything | 0.28 s | 0.95-1.05 s |
| all four | BC7 everything | 0.25-0.26 s | 0.88-0.94 s |

The rows with compressed originals need the opt-in above; by default (PNG originals) startup is the PNG row
plus the hi-res sets (all four ASTC: ~2.6 s; 10-28: ~2.7 s). Headless re-runs (tools/hires_view_check.mjs
--startup 3, dpr 1.25): all four ASTC 0.81-0.94 s, BC7 0.85-1.09 s, PNG 5.2-6.1 s; originals only ASTC 0.36-0.41 s,
PNG 1.62-1.71 s.

## Checks (10-29)
tools/hires_check.py (offline, against the original's pixels) and tools/hires_view_check.mjs (in play, headless
Chrome, dpr 1.25, readback after the frame).

Outline dots, the class of bugs.md 171 (`hires_check.py halo`, 2x copies, tol 32: a texel off its original
pixel's 3x3 opaque range by > 32; per 1000 texels on the outline band / inside). Band above inside = the model
paints the edges:

| set | before | after |
|---|---|---|
| terrain, flat tiles | 0.00 / 4.60 (10-29 fix) | 0.00 / 4.60 |
| terrain, tall tiles (trees, rocks, cliffs) | **18.64 / 10.37** | 0.00 / 10.16 |
| buildings | 5.44 / 10.13 | unchanged |
| figures | 8.96 / 18.80 | 0.00 / 0.00 (steady, below) |
| ui (Zeus_Interface) | 1.06 / 6.93 | unchanged |
| ui (Zeus_Fonts, new) | 13.17 / 35.27 | - |

Only the tall terrain pictures had it: their ground diamond meets the neighbours too, but they are upscaled
without the context ring. tools/hires_derive.py now clamps the outline band of every Zeus_Terrain picture
(`REFINE` "edges"; 1.76 M master texels). Buildings, figures and ui have fewer outliers on the band than
inside (detail inside the picture, not edge halos); left as they are. Worst ui pictures are the big
paintings (SPR_R_HERO 1751: inside detail, looks right).

In play (tools/hires_view_check.mjs, save H copy on :8811, headless Chrome dpr 1.25, city paused, readback in a
rAF after the frame; all four sets Remacri unless said): at (111,113) (beach and shallow water, bugs.md 171), 4
views x 100/200/500 %, dots per 1000 pixels within 1 px of a tile edge / elsewhere:
- 500 %: ASTC 0-0.12 / 0.08-0.18, BC7 0-0.12 / 0.08-0.16, PNG 0-0.5 / 0.06-0.17; original sprites 0 / 0.
- 200 %: 13.4-36.6 / 10.7-34.9 with every format; original sprites 7.6-24.1 / 6.6-24.3 (same seam/off ratio:
  grass texture, not seams). 100 %: ~100 / ~95 with every format and the original.
- Pure black pixels on the map area at 100 %: PNG 5-15, ASTC 64-90, BC7 212-234 per frame: near-black outline
  texels of sprites (fish crates, outlines) decoded to 0, not gaps (looked at: the PNG frame has a dark grey
  texel there). GL errors: 0 in every shot.
- Text at dpr 1.25 (panel of the palace shot, ui set Original vs Remacri): same layout, glyph coverage alike
  (yellow text pixels 411 vs 424), upscaled glyphs smoother; no missing glyphs.
- Looked at (screenshots, 4 views, 100 % and 200 %, ASTC): palace with walls, towers and gatehouses, Athena and
  Apollo sanctuaries, stadium, gatehouse, tower, villa (elite house), grand agora, avenue, dock/wharf area, horse
  ranch, fishing wharf, obelisk, cliffs and rocks (101,168). Not checked: bridges (none in save H). BC7 and PNG
  only at (111,113).

## Shimmer (10-29)
`hires_check.py shimmer`: walk cycles of 12 roles (immigrant .. competition, every unmirrored direction, 12
frames), mean |dRGB| between consecutive frames, anchors aligned, at 2x, as a ratio to the nearest upscale (the
original's own frame-to-frame change). Variants applied to the 4x masters before the shrink:

| variant | frame to frame | abs dRGB from plain Remacri |
|---|---|---|
| nearest (original) | x1.00 (21.28) | - |
| Remacri as built 10-28 | **x1.175** (immigrant alone x1.31) | 0 |
| clamp to the 3x3 range of the original | x1.083 | 2.93 |
| same + 30 % bicubic ("steady", shipped) | **x0.993** | 6.58 |
| 50 % bicubic, no clamp | x0.992 | 7.58 |
| bicubic only | x0.88 (immigrant) | 16.6 |
| same-neighbourhood averaging (consist:1/2) | x1.30 (immigrant, no change) | 0.06-0.17 |

Cause: the original's frames are separate renders that differ pixel by pixel; the model sharpens those
differences into folds and highlights that jump. "Temporal consistency" by reusing the model's output for
identical neighbourhoods does nothing (3x3 patterns almost never repeat across frames). Shipped: tools/hires_derive.py
`REFINE` "steady" for SprMain, PoseidonImps, SprAmbient (hires_derive.steady: clamp_local tol 0, then 70 % model +
30 % bicubic of the bled original): as steady as the original and closer to the model than to the original
(6.6 vs 12.4). Contact sheet: `hires_check.py shimmer --sheet OUT.png`.
