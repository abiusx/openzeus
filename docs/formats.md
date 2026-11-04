# File formats and our readers

The layouts below are stated in our own words; our readers implement them (MIT, no third-party code;
docs/references.md "What we use"). zeus-poseidon-arm64 documents the same formats in more detail
(`refs/zeus-poseidon-arm64/formats/*.md`, partly French). Identity check for any change to a reader:
`tools/reader_fingerprint.py` before/after (every decoded sprite and map block of the install, hashed).

| Format | Our tool | Output | Status |
|---|---|---|---|
| `.sg3` + `.555` sprites | `tools/sg3.py export DATA OUT` | `extracted/sprites/<file>/<group>/<idx>.png` + `atlas.json` (size, anchor, frames, iso size, mirror) | 70,587 images; only `Zeus_MapOfGreece01` (192) fails, because its `.555` isn't shipped |
| `Model/*.txt` | `tools/model.py MODEL OUT` | `extracted/model/model_<level>.json`, `tax_sentiment.json` | all 5 levels; reads integers the way the exe does |
| `Zeus_Text.eng` | `tools/engtext.py ENG OUT` | `extracted/text/zeus_text.{json,txt}` (`[group:index] text`) | 366 groups, 8,248 strings |
| `.map` / `.sav` / `.pak` | `tools/mapfile.py info|dump FILE [OUT]` | one `.bin` per block | container + PKWARE DCL explode (port of blast.c); block sizes check out |
| `.pak` / `.set` adventure header | `tools/build_campaign.py` | `data/campaign/<id>.json` | all 40 shipped .pak; docs/campaign-format.md |

## Map container (summary)
`MAPS` (maps only), u32 version, u32 block count, a 300 × 20-byte table (compressed, address,
elem size, count, converter), then the blocks in table order. A compressed block is
`u32 len` + DCL stream (`0x80000000` = stored raw, `0` = all zeros).
`.map` ranks: 4 image id grid (u32), 5 draw flags, **6 terrain flags (u32)**, 7 multi-tile size bits,
8 random grid, 15 meadow, **23 elevation (0..6)**, 24 projected elevation; others in map.md.
`.pak` = a `.set` adventure header (~842 KB: scenario settings) + 1..5 MAPS containers (parent
city, then colonies).

## Sandbox maps
- `Adventures/}Open Play Sandbox.pak`: Zeus, 2 maps, version 247
- `Adventures/Open Play Sandbox 2/Open Play Sandbox 2P.map` (+ `.pak`, `.set`): Poseidon, version 247
- Also `Open Play Economic/Military` (1 and 2).
The `.set` header (54 adventure fields + 4 goal tables) is decoded by `tools/build_campaign.py` into
data/campaign/*.json (docs/campaign-format.md; field order of adventure_read 0x00425D00). A .pak's maps are found by
the header's map_offsets (`mapfile.pak_map`); the first MAPS signature in the file is the header's map_buffer copy
(the last map published).

## Sprite files (.sg3 + .555)
All integers little-endian. An `.sg3` file is an index; the pixels are in `.555` files next to it.
- **Header** (680 bytes): u32 at 4 = version (0xD5 Zeus, 0xD6 with alpha masks), u32 at 12 = record slots,
  u32 at 16 = images used (record 0 is a dummy; images are 1..n), u32 at 20 = bitmaps used; at 80, 300 u16 =
  the first image index of each group.
- **Bitmaps** (200 records × 200 bytes, from 680): file name (65 bytes, NUL-terminated, cp1252), comment
  (51 bytes), then 5 u32 at +116: width, height, image count, first, last.
- **Image records** (record slots × 64 bytes for 0xD5, 72 for 0xD6, from 680 + 200 × 200): u32 +0 offset in
  the .555, u32 +4 length, u32 +8 length of the uncompressed part, i32 +16 mirror delta (non-zero: this image is
  image index + delta flipped left-right), i16 +20/+22 width/height, u16 +30 animation frames, i16 +34/+36
  anchor x/y, u8 +50 type, +51 compressed, +52 external, +53 has top, +55 iso size (tiles per side),
  +56 bitmap index; 0xD6 only: u32 +68 alpha-mask length.
- **Group names** (300 × 48 bytes, NUL-terminated) end the file; the file size is exactly header + bitmaps +
  records + names. A group exists when its first index or its name is non-zero.
- **Pixel source**: an external image's pixels are in the .555 named like its bitmap's file (extension .555),
  at offset − 1; otherwise in the .555 named like the .sg3, at offset. File names match case-insensitively.
  The image's `length` bytes follow, then (0xD6) its alpha-mask bytes.
- **Pixels** are RGB555 (bits 10-14 red, 5-9 green, 0-4 blue; each 5-bit value v widens to (v << 3) | (v >> 2)).
  - Plain (not compressed, not type 30): width × height u16, row by row; 0xF81F (magenta) = transparent.
  - Compressed: runs over the image as one pixel row after another (runs continue across row ends): a byte 255
    then a byte n skips n pixels (left transparent); any other byte n is followed by n u16 pixels.
  - Type 30 (building with an isometric ground part): the first `uncompressed length` bytes are the base, any
    bytes after it are compressed runs (as above) drawn over the whole image (the part standing above the base).
    The base is s × s tiles (s = iso size, or ((width + 2) // 2) // 30 when 0), occupying the bottom
    (width + 2) // 2 rows. Each tile is a 58 × 30 diamond of 900 u16 pixels stored row by row; its row y
    (0..29) covers columns |2y − 29| − 1 to 58 − (|2y − 29| − 1). The tiles come in the rows of the drawn
    diamond, top first, left to right: row r (0 .. 2s − 2) has s − |s − 1 − r| tiles, the k-th at
    x = (|s − 1 − r| + 2k) × 30, y = bottom part's top + 15 r. Base pixels whose low 15 bits are 0x03E0 (pure
    green) are not drawn.
  - Alpha mask (0xD6, alpha-mask length > 0): runs as above with one byte (a 5-bit level, values above 31 count
    as 31) per pixel; covered pixels take that alpha, others keep 255 (drawn) or 0.

## DCL compression
Compressed map/save blocks use PKWARE's Data Compression Library "implode" format (the one Mark Adler's
blast.c decodes; our `tools/mapfile.py explode` is our own decoder of it). Bits are read least-significant
first. Byte 0: 0 = literals stored as raw 8 bits, 1 = literals Huffman-coded; byte 1: 4, 5 or 6 = low bits of
a distance (dictionary 1, 2 or 4 KB). Then items, each led by one bit: 0 = a literal; 1 = a copy: a length
code, then the length's extra bits (length = base + extra; 519 = end of stream), then a distance code d and
k low bits (k = 2 when the length is 2, else byte 1): copy from (d << k) + low + 1 bytes back (copies may
overlap their own output). The three Huffman codes (literals, lengths, distances) are fixed by the format and
canonical (codes assigned in order of length, then symbol); each code's bits are stored inverted, first bit
first. Length symbols 0..15 have bases 3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264 and 0 (symbols
0..7) or 1..8 (symbols 8..15) extra bits.

