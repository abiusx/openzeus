# Messages list and Goals screens (play mode)

Code: `viewer/play/lists.js`; texts in `data/play/options.json` (`tools/play_options.py`: groups 13, 20, 25, 44, 63);
help records from `data/play/help.json`. Server: `GET /goals.json` (sim/live.py `goals_info`). Opened by the lower
panel's Messages and Goals buttons; right click closes (on a message row: deletes it).

## Messages (screen 0x11: background 0x00522340, draw 0x00522620)
- Titled frame F = (ox-75, oy+32) 37x24, title 63:0 (22C) centred in 592 at F.y+16; list box (plain) L = (ox-59, oy+102)
  33x13.
- No messages: 63:1 (11CB paragraph, width 480) at (L.x+16, L.y+80). Otherwise headers 63:2 / 63:3 at (L.x+42 / +170,
  L.y-18), hint 63:4 at (L.x+40, L.y+211) width 478, "Delete opened messages" 63:6 centred in 280 at
  (F.x+156, F.y+319) with its RIMS box (0,0)-(280,30) from (F.x+156, F.y+312).
- "Click to change how messages are received" 63:7 centred in 480 at (F.x+56, F.y+351), RIMS box (-100,32)-(380,62):
  opens the Messages options dialog (options.js). Hovered boxes: the highlight's second variant.
- Rows (10 visible, 20 px): icon SPR_BUTTONS1 258 (unread, at L.x+8) / 259 (read, L.x+12) at y+6; month 25:m at
  (L.x+42, y+8), year (year_text_draw 0x00508E50: " n " then 20:0 "BC" at the pen + 6; "AD" then the number) at
  L.x+72, subject at L.x+180; 11C2, hovered row 11C3. Scrollbar (more than 10) at (L.x+528, L.y) h 208.
- Help (533) at (F.x+16, F.y+342) -> record 87 Messages; close (537) at (F.x+554, F.y+348).
- Ours: the rows are the city's message lines (state.json `messages`, the last 30), oldest first and the newest at the
  bottom as the exe shows them (oracle messages-list12; FUN_005221B0 inserts new entries at queue slot 0, so the
  list does not draw in slot order); the subject is the line's title (up to the first
  ". "); read/deleted are this viewer's. Opening a message shows it in the event-message window (msgwin.js,
  docs/play/screens.md "Event-message window"); a right click there returns to the list, the row marked read
  (oracle runs/messages-window list-after.bmp: 0 px).

## Goals (screen 0x3B: objectives_screen_draw 0x0052C070)
- Titled frame G = (ox-76, oy) 37x33. Title: the adventure's Zeus_MM record title (adventure +0x8B40,
  FUN_0042B810) centred in 592 at G.y+10 (22C); episode title (episode 0 at +0x1BE4, +0x64C: FUN_0042B640) at
  (G.x+16, G.y+42) 11C; the player city right-aligned in 560 at the same line.
- Separator: SPR_MARBLE_BAR 604/605/606, 36 tiles at (G.x+8, G.y+54). Headers 44:276 "Goal" (G.x+99) and 44:277
  "Goal Status" (G.x+437) at G.y+64.
- Goals box: plain (G.x+16, G.y+76) 35 x B, B = (max(n,1)*20+19)/16 + 1. Open play (n = 0): 44:280 "Open Play, no
  episode goals" (11C2) at (ox+128, oy+90).
- "Right-click to continue" 13:3 (11C) centred in 592 at G.y+504 (G.y+442 with the tutorial buttons, not ours).
- Briefing: the episode record's body (FUN_0042B5E0) laid out as a help page in (G.x, G.y+16B+72) 592 x (392-16B):
  inner frame at (G.x+16, top+32), 33 columns with a scrollbar (at inner x + 16*33), else 35; 11C2, links 11C4.
  Ours: a link opens the help window (the exe follows it in place with the help window's history).
- Sandbox maps: `}Open Play Sandbox.pak` gives records 518 "Open Play Sandbox" / 517 "Utopia". A map without a .pak
  (a bare .map) shows no texts. Campaign goals (1L-4): the rows' texts, tick boxes and the Set aside button come from
  /goals.json (sim/campaign/texts.py); the same drawer is the victory and adventure-complete screens
  (`Lists.objectives`): docs/play/campaign.md.

## Checks (oracle runs/messages-goals, re/oracle/scenarios/messages-goals.txt, 800x600; ours at dpr 1.25)
| Shot | Ours | Differing px (tol 30) |
|---|---|---|
| messages.bmp (one unread message, May 1340 BC) | `Lists.open('messages')`, S.messages = one line, date May 1340 BC | 0 (592x384 at (5,92)) |
| goals.bmp (tutorial Big City: records 963 / 920, Megara) | `/goals.json` answered with those records, the right-click line drawn at the tutorial's y for the check | 0 in (4,60) 592x455; below: the tutorial's buttons (not ours) |
| messages-empty/empty.bmp (the one message deleted by a right click: 63:1) | S.messages = [] | 0 |
| messages-list12/l12.bmp (12 messages, 3 read: scrollbar, ball at the top) | 12 lines, months Jun 1341 .. May 1340 | 0 |
| messages-list12/hrow.bmp (row 3 hovered: 11C3) | mouse (250,217) | 0 |
| messages-list12/hdel.bmp, hopt.bmp (Delete opened / options box hovered: RIMS second look) | mouse on the box | 0, 0 |
| messages-list12/sdown.bmp (one click on the down arrow: 2 lines) | two steps | 0 |
| messages-list12/hup.bmp (then the mouse on the up arrow: 333) | scrolled 2, mouse (565,175) | 0 |
Scenario re/oracle/scenarios/messages-list.txt (pokes: tools/oracle_message_pokes.py). One click on the oracle's
down arrow moved 2 lines (the exe steps every input pass while held; the scripted click spans two); ours steps once
on the press and every 30 ms after while held. The goals briefing scrollbar was in goals.bmp (0 px above).
