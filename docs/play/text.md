# Play mode: text rendering and UI strings (research, 2026-10-27)

Data: `data/play/fonts.json` (`python3 tools/play_fonts.py`), `data/play/strings_ui.json`
(`python3 tools/play_strings.py`). Code: `viewer/play/text.js` (`window.ZText`). Python twin of the
line renderer for checks: `tools/play_fonts.py` class `Ref`. New exe names: `re/names/text.tsv`.
Companion: docs/play/ui.md (sprites and geometry of the panels; same evidence levels).

Evidence levels: **exe** = read in the decompile (`re/decomp/zeus.c`, address given); **seen** = matched pixel
for pixel on a screenshot of the real exe (oracle, below); **arm64** = refs/zeus-poseidon-arm64
`docs/engine/interface.md` sections 7.x (itself verified there; we re-read every function cited);
**hyp** = hypothesis. eZeus was not used.

## Ground truth
Oracle screenshots (docs/re/oracle.md; base script = "See a working city", 800x600, fresh `--write-dir`
each run; right click on a building opens its info window, e.g. `61:move 471,301; 62:rclick 471,301`).
Every check below renders with `text.js` and paints the glyphs over the screenshot: **0 mismatching
pixels** (tolerance 24/255) on:
- the Infirmary info window (title, two-line body, employees line): 5,195 glyph pixels;
- the top bar (File / Options / Help, funds, population, date): 1,928 px;
- 13 lines of a help page (`Zeus_MM.eng` "World View", with an `@P` paragraph): 22,847 px.
Also matched (Python twin, 100 %): control panel title "Population" (11C), "See Supplies" (9LTBK),
"Housing for"/"More people" (9B), "People wish to"/"Immigration" (9DKBU), "lack of housing" (9DKYEL),
bottom message strip "The city needs more / workers." (DKMESSAGE, 12 px step, second line starts with
a space).
Composites (original / ours painted over it / diff) and samples:
`.../scratchpad/text/compare_infirmary.png`,
`.../scratchpad/text/compare_topbar.png`, `.../scratchpad/text/compare_worldview.png`, `.../scratchpad/text/samples.png`
(screenshots in `.../scratchpad/orig/`). No web screenshots were downloaded: the oracle is exact.

## 1. Fonts (Zeus_Fonts.sg3, bank 0)
17 groups of 134 glyphs. A font is passed around as the image id of its first glyph; the exe compares
that id with group-table entries to pick its metrics (**exe** 0x00508800, 0x00507DA0). Glyph `g` (1..134)
= atlas image `first + g - 1`. All glyph anchors are 0 (top-left). (**exe**, atlas)

| rank | name (fonts.json key) | first | draw: space / extra / line h. | measure: space / extra | look, main uses (**seen** where tested) |
|---|---|---|---|---|---|
| 0 | SPR_FONTS (`SMALL`) | 201 | 4 / +1 / 9 | 4 / +1 | **mask** (type 20): 1 colour from the caller; debug overlays, bottom strip, top-left alerts |
| 1 | 11C | 335 | 6 / 0 / 11 | 6 / 0 | dark navy engraved: top menu, top bar numbers/date, info-window bodies, build menu, control-panel page title (**seen**) |
| 2 | 11C4 | 737 | 6/0/11 | 6/0 | green |
| 3 | 11C2 | 469 | 6/0/11 | 6/0 | pale blue/white: help and message pages (**seen**), control-panel numbers |
| 4 | 11C3 | 603 | 6/0/11 | 6/0 | orange |
| 5 | 11CB | 1273 | 6/0/11 | 6/0 | very dark navy: info-window employee lines (**seen**), hovered build-menu row |
| 6 | 22C | 871 | 8 / 0 / 23 | **10 / +1** | large dark navy: window titles (**seen**) |
| 7 | 22C2 | 1005 | 8 / 0 / 24 | **10 / +1** | large pale blue |
| 8 | 9B | 1139 | 6/0/11 | 6/0 | small very dark: control-panel labels (**seen**) |
| 9 | 11LTYEL | 1541 | 6/0/11 | 6/0 | yellow |
| 10 | 9LTBK | 1675 | 6/0/11 | 6/0 | small dark blue, light edge: panel buttons (**seen**) |
| 11 | 9LTBU | 1809 | 6/0/11 | 6/0 | small white |
| 12 | 9LTYEL | 1943 | 6/0/11 | 6/0 | small yellow |
| 13 | 9DKBU | 2077 | 6/0/11 | 6/0 | small pale, dark edge: control-panel texts (**seen**), tooltips (**exe**) |
| 14 | 9DKYEL | 2211 | 6/0/11 | 6/0 | small yellow-orange: highlighted values (**seen**) |
| 15 | 11LTBLUE | 2345 | 6/0/11 | 6/0 | pale blue |
| 16 | DKMESSAGE | 2479 | 4 / 0 / 7 | 6 / 0 | small dark: control-panel message strip (**seen**) |

- Colour: every font except SPR_FONTS is pre-coloured (one glyph set per colour); the colour argument
  only matters for the mask font, whose pixels are all replaced by it (glyph-mask blitter 0x00416C30,
  colour 0x00F1397C; **exe/arm64**). Colours are RGB555 (`0x7F9A` cream, `0xFFFF` white, `0x3EFA`
  light blue, `0xF800` red; 565 variants are substituted when the screen is 565). (**exe**)
- The sg3 has one more 134-glyph mask set at 1407..1540 (between 11CB and 11LTYEL, no group of its
  own; our extractor files it under 11CB). No code reaches it through the group table. (**exe**, atlas)
- "draw" = `string_draw` 0x00508800 (space advance, pixels added after each glyph, line height
  0x00F13960); "measure" = `string_width` 0x00507DA0, used only to centre/right-align. They disagree
  for 22C/22C2/DKMESSAGE; both are kept (centring in the exe uses measure, the pen moves by draw). (**exe**)

## 2. Characters
- Strings are bytes; English text is cp1252. `charmap[byte]` = glyph number, the exe's 256-byte table at
  0x0063BE0C (bytes < 0x20 are never looked up: the table's first 32 bytes are a file name). a-z 1-26,
  A-Z 27-52, 1-9 53-61, 0 62, `! " % * ( ) - + = : ; ' ? \ / , . _` 63-80, accented letters 81-134.
  No glyph: space, `# $ & @ < > [ ] ^ { | } ~` (**exe**). Lower-case glyphs look like small capitals.
- The upper half of the table is the GOG edition's mixed (mostly cp1252, partly Polish cp1250) mapping,
  e.g. 0xE0 `à` draws `Ó`. The game's English text uses only ASCII (one test string excepted), so this
  never shows; we keep the table as is. (**exe**, seen in samples.png)
- Lift (0x00508B50 line texts, 0x004F59B0 panel texts): bytes >= 0x80 are drawn `max(0, glyph h - line h)`
  higher (accent above the line), except 0xE7 (0); 18 Polish letters (`lift2`) exactly 2. (**exe**)

## 3. One line: `string_draw` 0x00508800
```
for byte c in text:
  if c < 0x20: skip
  g = (c == '#' or c == '_') ? 0 : charmap[c]
  if g == 0: x += space(font)                     # space, '@', '&', ... all advance one space
  else: blit glyph at (x, y - 3 - lift); x += glyph.width + extra(font)
after the call the pen variable 0x00F13A70 = advance + space(font)
```
(**exe**, **seen**.) `#` pulls characters from a prepared buffer in paragraphs (no game string has one);
the outline/shadow styles (0x00F13974/78) are never switched on in this exe (no writes); 0x00F13970 is
set around some calls but selects the plain path. Callers chain pieces with the pen: e.g.
`count_noun_draw` 0x00508DD0 draws `" 11"` then the noun at x + pen, so pieces are separated by one
space of the font. Centred: `x + max(0, (w - measure) / 2)` (0x00508670, integer division);
right-aligned: `x + max(0, w - measure)` (0x005094C0).

Numbers (`number_text_draw` 0x00508F00): the string is `sign + digits + suffix`, sign slot `'@'` (a
blank one space wide), `' '`, `'('`, `'-'` (negative numbers: slot then `-`); the usual suffix is the
exe string `" "` (0x005E8FD0). Example, the employees line: `" 11"`, `"Employees"`, `"(11 "`, `"needed)"`
= "11 Employees  (11 needed)" (**seen**).

## 4. Word-wrapped paragraph: `paragraph_draw` 0x005090A0 (and centred 0x005086E0)
Used by the info windows and the control panel. Up to 99 lines; each line:
```
w = 0
repeat: (ww, n) = next word (0x005091B0): each leading space 4 px, each char glyph.width + 1
                  (fixed, whatever the font), ends before a space or '$' that follows the word
        if w + ww >= width: stop            # strict: the line must stay below width
        w += ww; copy the n bytes (leading spaces included)
draw the line with string_draw at (x, y); y += 5 + line height(font)   # 16 for 11-px fonts
```
So a continuation line begins with the space that preceded its first word (visible: the original's
second lines are indented by one space; **seen**). A word wider than the box makes the exe emit empty
lines; we take the word anyway (ours).

## 5. Long texts: `text_layout` 0x004F5300 (help pages, messages, tooltips, objectives)
Font = 0x00EF8C9C (normal) and 0x00EF8C98 (link label). Line step 16, up to 999 lines.
- Line fill: words measured by 0x004F57A0 (space 4, glyph width + 1), added while the running width
  stays below `width`; spaces at the start of a line are dropped (unlike section 4). (**exe, seen**)
- `@P` ends the line and indents the next one by 50 px (x and running width start at 50); `@L` ends the
  line; `@Gn` inline picture n of a bank-2 group (not supported in text.js); `@n` = a link to record n,
  its label (next word, `&` = a blank) in the link font. (**exe; @P seen**)
- Drawing (0x004F58C0/0x004F59B0): glyph at `(x, y - lift)` with line height 11 (**no** -3 here);
  advance = glyph width (+2 for SPR_FONTS), 6 for any byte without glyph (spaces included). With the
  SPR_FONTS font the line is drawn a second time at (x-1, y-1) in 0x7F9A. (**exe, seen**)
- Only lines in [scroll, scroll + visible) are drawn (0x00EF8C58, 0x00EF8C64); mode 1 only counts lines.

## 6. Where the UI draws text (positions relative to the window's top-left)
| Element | Font | Rule | Evidence |
|---|---|---|---|
| Top menu titles (1:0, 2:0, 3:0) | 11C | y=6, x 10 / 55 / 130 at 800x600 | seen (ui.md: exe) |
| Top bar funds, population | 11C | y=5, after the icon (+16) | seen |
| Date `May 1340 BC` | 11C | y=5: month 25:m, then year via 0x00508E50 (`AD n` / `n BC`, 20:x) | seen |
| Dropdown items | 11C; hovered item 11LTYEL (colour 0xFAC1) | text at (x+8, 30+20i) | exe (0x00431210) |
| Build submenu rows (0x0058F650) | 11C; hovered row 11CB colour 0xFAC1 | name 28:type centred in 176 px at panelX-266; cost number at panelX-114; rows 24 px | exe |
| Control panel page title (88:p) | 11C | centred, y=30 at 800x600 | seen |
| Control panel buttons (14:k) | 9LTBK | centred in the button | seen |
| Control panel labels / body / values | 9B / 9DKBU / 9DKYEL | paragraphs, step 16 | seen |
| Control panel message strip | DKMESSAGE | paragraph, step 12 | seen |
| Tooltip (0x004F6E40) | 9DKBU (link font 9DKBU) | text_layout width 190, or 270 if > 2 lines; box (w+20) x (lines*16+10) with w 220 / 300; text at box+(5,7); box x = mouse+20 if mouse x < w+20, else mouse-w-20 (so normally left of the mouse); y = mouse+50, or mouse-72 if mouse y >= 200; outer rect colour 0x0084 (0,33,33), fill 0x09B2 (16,107,148) | exe, **seen** 10-29 (pages.md "Minimap colours and tooltips"; the earlier 210/290 box was wrong) |
| Help/message page (0x004F2D80) | 11C2 | text_layout width 400 at window+(24,50); title 22C at window y+10 | seen (window 480 wide at (80,88); title centring box not read) |
| Message window texts, objectives | 11C2 / 11CB | via text_layout (0x004F4380, 0x0052C070) | exe |

### Building info window (`info_window_background_draw` 0x005720E0 -> per-type panel)
Window: left L, top T (0x00FFA17C/78; L = 68 at 800x600 with the panel unfolded, **seen**), width C cells
of 16 px (0x1D = 29 by default), height H cells by class (geometry: docs/play/ui.md). Common layout of the
~40 panel functions (counts are call sites in the decompile):

| Text | Font | Position / width | Evidence |
|---|---|---|---|
| Title | 22C | centred in C*16 starting at L, y = T+10 (41 panels) | exe, seen |
| Status paragraph ("why" line: staffing, fire, curse, no road...) | 11C | (L+32, T+56), width (C-4)*16, step 16 | exe, seen |
| Description paragraph (group:1) | 11C | (L+32, T + H*16 - 113), width (C-4)*16 (some panels -75/-143/-158/-183) | exe |
| Inset box | frame tiles | (L+16, T+136), C-2 cells x 4 rows (houses: T+148, 10 rows) | exe, seen |
| Workers line (0x00577290, at y0 = T+142) | 11CB | icon (Zeus_Interface) at (L+40, y0+6); full staff: text y0+16, else y0+10; `" n"` + 8:12/13 at L+60, then `"(m "` + 69:0 at L+70+pen | exe, seen |
| Workers reason (understaffed) | 11CB | paragraph 69:k at (L+70, y0+26), width 400; k: 1 no people, 2 no road/labour access, 3 shift labour, 0 none | exe |
| Other rows (houses, storage, farms) | 11C / 11CB | mostly x = L+32 or L+36, y fixed per panel | exe (scan) |

Status text (Infirmary 0x00577D20; the culture/service panels repeat the pattern), group g = the
panel's text group (76 here): on fire -> g:8; else 0x00FFA144 < 1 -> **69:4** (needs road access),
0x00FFA144 == 2 -> **69:5** (no labour pool); no workers -> g:7; type disabled (curse) -> g:9; blessed ->
g:10; else by staffing % 0x00FFA148: >= 100 -> g:2, 75-99 -> g:3, 50-74 -> g:4, 25-49 -> g:5, < 25 -> g:6.
(**exe**; full staff -> 76:2 **seen**; meaning of 0x00FFA144 values from the 69:4/5 texts: hyp.)

## 7. Strings (`data/play/strings_ui.json`)
`extracted/text/zeus_text.json[group][index]` holds `Zeus_Text.eng` (group numbers = the exe's, index
0-based; lookup 0x00507BF0). `Zeus_MM.eng` (help pages and messages, `@` codes) is **not** extracted by
our tools yet (refs/zeus-poseidon-arm64/tools/engtext.py reads it).
| UI use | Lookup | Evidence |
|---|---|---|
| Top menus | 1 File, 2 Options, 3 Help, 4 Reports (index 0 = title) | exe, seen |
| Months | 25 short, 160 long; era 20 (0 BC, 1 AD) | exe, seen |
| Building names (build menu, storage titles) | 28:type (type = data/buildings.json `zeus_id`, all 127 checked) | exe (0x0058F650), names |
| House titles | 29:(type-2) (lower case: hut, shack...) ; texts 127 | exe |
| Info panel texts | per-type group: `buildings.<key>.text_group` (title = [g,0], description = [g,1], states [g,2..]) | exe (0x005720E0 switch) |
| Decorations | 137:2k title, 137:2k+1 description, k from 0x00577A10 | exe |
| Employees line | 8:12/13 (Employee/Employees), 69:0 "needed)", 69:1.. reasons | exe, seen |
| Control panel page titles / buttons | 88 / 14 | exe, seen |
| Tooltips (balloon help) | 68 (217 strings; widget -> index not read) | text, hyp |
| Dialogs | 5:0-1 Quit / Exit Game?, 18 No/Yes/Cancel/OK, 13 click to continue / paused | exe |
| Walkers | names 64:n, locality info 70 | exe (figure table +0x18), hyp per index |
| Reports | 50 workforce, 51 military, 54 trade, 55 population, 56 hygiene, 57 husbandry, 58 culture, 59 mythology, 60 finance, 61 overview, 63 messages | exe (scan) |

## 8. What the UI layer must implement
- Load `data/play/fonts.json`, pack `Zeus_Fonts` (`python3 tools/play_atlas.py Zeus_Fonts`), call
  `ZText.init({fonts, sprite})`. Fonts may be named `SPR_FONTS_11C` or `11C`.
- `push(sprite, x, y, alpha, tint)`: draw the sprite's top-left at (x, y) in screen pixels, no camera.
  `tint` ([r,g,b]) comes only for the mask font SPR_FONTS: the shader must replace the glyph RGB by it
  (`rgb = tint`, keep alpha). gl.js has no tint yet; until then avoid SPR_FONTS (none of the panel
  texts need it).
- Pass the exe's y (the text position, not the glyph top); text.js applies the -3 / lift itself.
- Chain pieces with the returned `cursor` (the exe's pen) for "number + noun" rows.
- Window frames, inset boxes, icons, scroll bars: docs/play/ui.md.

## Open questions
- The help window's title centring box.
- Tooltip widget -> 68:index mapping (per-screen virtual method +0x1C of 0x00641C10).
- `@G` picture group (bank 2) and the link click table (arm64 open question).
- Per-panel extra rows (storage, farms, sanctuaries) were scanned, not each verified on screen.
