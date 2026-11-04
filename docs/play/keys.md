# Play mode keys

Source: the manual (Zeus - Manual.pdf, Appendix 2 "Keyboard Controls") and the exe's key handlers
(WM_KEYDOWN 0x005C4E04, WM_CHAR 0x005C560F; tables in refs/zeus-poseidon-arm64 docs/engine/interface.md 3.2).

| Key | Original | Play mode |
|---|---|---|
| 1..9, 0, - | panel page (build_menu_select 0x0051CA20: '1'..'9' -> 0..8, '0' -> 9, '-' -> 10 Overview); only on the city screen (1) or an advisor (7); the current page's key toggles 1 <-> 7 when the page has an advisor (0x0063E488[page]); with an advisor open, another page's key opens that page's advisor (FUN_00516D50), a page without one takes no key | same (play.js pageKey) |
| space | swap the page's overlay with normal view (0x00516C60) | same (first overlay if none used yet) |
| P | pause (game_paused 0x00F2A768) | pauses the live server |
| [ / ] | game speed -10 / +10 (0x00402430) | speed step down / up (+ also up) |
| Tab | overview map / info area | radar tab / pages |
| Ctrl+F1..F4, F1..F4 | bookmark / go to view (slots 0x00FA05C0) | same, kept in localStorage |
| R | rotate the footprint (see "Rotating buildings") | see below |
| M | freeze the footprint (manual: big sanctuaries) | freeze; click anywhere builds at the frozen spot |
| arrows | scroll | scroll |
| Home, PgUp, PgDn | turn the view: Home north, PgUp +90 (view +2), PgDn -90 (0x00408930; the rotate button by thirds: left PgDn, middle Home, right PgUp) | same (docs/play/rotation.md) |
| F5, F6, F7, Alt-X | window/resolution/exit | not mapped (browser) |
| + / - (exe) | sound-frag debug step (0x005C3670) | + = speed up; - is the Overview page |
| Ctrl+G/H/J, Ctrl+A | debug events, "Allow All" | not mapped (cheat keys) |
| Ctrl/Alt+digits | company / fleet groups | mapped (milpanel.js, 1B) |

## Rotating buildings (R while placing; exe: GetAsyncKeyState('R') in each tool's preview, FUN_00451820 dispatch)
| Building | Exe | Ours |
|---|---|---|
| sanctuaries, Poseidon pyramids/monuments, palace | 4 orientations (FUN_0053DE20; pieces turned by composite_offset_rotate, images per b+0x9C) | yes (bugs.md 133) |
| water park | 8 picture variants, R or an automatic 1.5 s cycle (FUN_0041BC90); a long drag picks random ones | yes, R only; drags use the R variant (bugs.md 136) |
| stadium | 2 (FUN_005AFD80) | yes |
| gatehouse | 2 (FUN_004E5190) | yes |
| commemorative monuments (0x77) | 4 (FUN_00456E30) | no: not buildable in ours yet |
| horse ranch | 4 (FUN_004532B0) | no: ours is one fixed piece (bugs.md 134) |
| race track (Poseidon, 199) | 8 with an automatic cycle, only fitting ones (FUN_0056E5E0) | no (Poseidon) |
| agoras | none: the exe searches spot and side (bugs.md 30) | same |
| statues, gardens, benches, columns, other buildings | none (build_cursor_preview turns only a tool that set an orientation) | none |
Also: R in window_proc toggles 0x0160AC8C, which nothing else in the decompile reads.

Ours: W A S D scroll, wheel / q e zoom, Ctrl+0 zoom reset, Shift+M mute, ` dev bar.
There is no road key in the original (roads are on the panel).
