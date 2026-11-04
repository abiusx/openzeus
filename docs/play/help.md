# Help window (screen 5) in play mode

The in-game help ("Mythology Manual", `Zeus_MM.eng`, format: refs/zeus-poseidon-arm64/formats/eng.md "MM file")
drawn as `help_page_draw` 0x004F2D80 draws plain pages. Code: `viewer/play/help.js`, text layout in
`viewer/play/text.js` (`helpLayout` = text_layout 0x004F5300, `helpLine` = text_line_draw 0x004F58C0).
Data: `data/play/help.json`.

## Reproduce
```
re/venv/bin/python tools/play_help.py     # Zeus_MM.eng + Zeus.exe tables -> data/play/help.json
```
Inputs: `zeus-original/app/Zeus_MM.eng`, `Zeus.exe` (tables below), `extracted/text/zeus_text.json` (12:0 "Back").
Pictures (`@G n`, record picture fields): Zeus_Unloaded SPR_PICS, image 202 + n - 1 (already in the atlas).

## Which record opens
| Entry | Record | Exe |
|---|---|---|
| Info window help button | building type's `g_building_type_info` +0x14 (0x005F6368 + 32*type + 0x14); 0 -> 1 Table of Contents; hero hall by hero (63..68, 74, 107) | 0x00580400, building_info_panel_prepare |
| Land/walker window help button | land kind: road 5, water crossing 28, park 20, wall 31, else 113 Terrain Types; for road, crossing and other land with a figure shown: sheep/goat 95, wolf 101, boar 102 (deer 151), cattle 152, trireme 103, god 93, monster 92, hero 94, soldiers 96, others 91 Walkers | FUN_005731D0 |
| Advisor help button | the current panel page's tab help (page_help 0x005169B0, table 0x0063E4B4: 76..85, 75) | 0x005169F0 |
| World map help button | 88 World View | 0x004081D0 |
| Right click on panel widgets | page buttons: page help; road/roadblock/clear, tabs, build buttons, magnifier: 86 Control Panel; alert buttons 97..100 (only an active one, docs/play/alerts.md); messages 87; goals 90; world map 88; overlay buttons: current page help; undo, rotate: none | tables 0x0063DC40, 0x0063DF80 (+0x20), handlers 0x00516A00/0x00516A10/0x005169F0 |
| Help menu: Help / About | 1 / 0 | 0x00402500 / 0x004025C0 |

The info window's help (e = 0) repaints the city under the help window: the info window is hidden while help is up
and comes back on close (seen: oracle land-help2.bmp shows the city where the land window was). Advisors and the
world map open it with e = 1: they stay drawn behind it.

## Layout (plain pages, 30x28 cells at (ox, oy+24), ox/oy = the 640x480 origin)
- Titled frame; title 22C centred in (X+8, W+20) at Y+14 (title x != 0: plain at (X+tx, Y+ty)).
- Caption (record +0x1E != 0): 11C paragraph at (X+cx, Y+cy), width W-cx-16; it counts as at least one 16-px line,
  so About's text box starts at Y+60 (seen).
- Text top T = Y+48 (Y+32 with a title x), pushed below pictures/caption; rows R = H/16 - (T-Y+pad)/16 - 1
  (pad 48 for layout 0, else 32); visible lines R-1. Measured at width 16*(cols-4)-16; if it does not fit: scrollbar
  and inner width cols-4, else cols-2 (drawn at 16C-16: wraps can differ from the measure, as exe).
- Inner plain frame (X+16, T) C x R, clip = inset 3 px. Body 11C2 at (X+24, T+6), 16 px lines; links 11C4 (green),
  boxes x0-2..x1+2, y-1..y+13, act on the left press; history 199 deep; Back (layout 0, history > 0) image 252 at
  (X+16, Y+H-36), label 12:0 at (X+52, Y+H-31); close image 537 at (X+W-38, Y+H-36).
- Scrollbar at (X+16+16C-1, T), h 16R: arrows 332/336 (+1 hovered, +2 held; step 1 line, repeated while held:
  ours every 30 ms, the exe every input pass), track plain frame 2 cols at top = T + (h-trackH)/2, ball 230 at
  (x+5, top + (trackH-24)*(pos*100/range)/100); drag in the track; mouse wheel 3 lines per notch.
- Right click anywhere closes (returns to the previous screen); no keys.

The event-message layout (layout 2, records 220..228: date line, action buttons, go-to button) is its own module:
viewer/play/msgwin.js, docs/play/screens.md "Event-message window". Pictures (`@G`) occur only in tutorial records (layout 3), not in help pages:
implemented per text_layout; compared 11-01 on the tutorial goals screen (oracle 1L5-tut00 start.bmp, bugs.md 349):
the drawing pass resets a delayed picture's rows where it is drawn, so the text after it starts one line lower than
the measuring pass says (text.js helpLayout(..., draw = true)).

## Checks (oracle, 800x600, tools/screens_check.mjs at dpr 1.25 + tools/screens_compare.py, tol 30)
Scenario re/oracle/scenarios/help-pages.txt (Help menu -> Help; Table of Contents -> Agora link; 3 clicks on the
down arrow; Back; land window help).
| Shot | Ours | Differing px |
|---|---|---|
| toc.bmp (record 1, 480x448 at (80,84)) | `Help.open(1)` | 0 |
| about.bmp (record 0, 448x272) | `Help.open(0)` | 0 |
| land-help2.bmp (record 113 Terrain Types) | `Help.open(113)` | 0 |
| agora.bmp (record 8 after a link: Back button) | `Help.open(1)`, `Help.go(8)` | 0 |
| agora-scroll.bmp (scrolled; ball position) | scroll = range - 15 | 0 |
| back.bmp (Back to the TOC, scroll restored) | toc | 0 |
