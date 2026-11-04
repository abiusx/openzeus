// The event-message window: screen 5 with a layout-2 record (help_page_draw 0x004F2D80, buttons 0x004F28C0 /
// 0x004F4AC0, input 0x004F4CF0), as the exe draws a city message. One reusable window for every message, the
// sim's own and the dialogs other modules need (gifts: Accept / Postpone / Decline; invasions: Surrender / Bribe /
// Fight; requests: Dispatch now / Postpone / Refuse). Rules, positions and evidence: docs/play/screens.md
// "Event-message window"; the API is documented there too.
//
//   MsgWin.open({title, body, type, month, year | tick, to, site, reason, good, goodName, amount, months,
//                goto: [x, y], buttons: {accept, postpone, decline} | {surrender, bribe, fight, bribeAmount}
//                | {dispatch, postpone, refuse}, onClose})
//   MsgWin.fromMessage(m)       a state.json message ({tick, text, title?, body?, ...}) -> open
//   MsgWin.close(), isOpen(), draw() (ui.js, under the control panel), rightClick()
"use strict";

const MsgWin = (() => {
  let cur = null;
  const BODY = "SPR_FONTS_11C2", LINK = "SPR_FONTS_11C4", DATE = "SPR_FONTS_11C2";
  const HELP = 533, CLOSE = 537, GOTO = 264;        // SPR_PANEL_ICONS (group 134 = 0x286), SPR_EXCLAIM_BUTTON (113)
  const TPM = 51 * 16;
  const t = (g, i) => (window.Options ? Options.text(g, i) : "");
  // the three button sets of 0x0063B228 / 0x0063B280 / 0x0063B2D8 (3 x {x0, y0, x1, y1, handler}, 0x1C apart), in
  // slot order; bit = the message flag (+0x16) that shows the slot, text 44:k, font: set A 11C, sets B/C 9LTBK
  const SETS = [
    { font: "SPR_FONTS_11C", slots: [["accept", 4, 209], ["postpone", 2, 211], ["decline", 1, 210]] },
    { font: "SPR_FONTS_9LTBK", slots: [["surrender", 0x10, 282], ["bribe", 8, 281], ["fight", 0x20, 283]] },
    { font: "SPR_FONTS_9LTBK", slots: [["dispatch", 0x40, 275], ["postpone", 0x80, 211], ["refuse", 0x100, 212]] }];
  const RECTS = [[20, 0, 192, 25], [198, 0, 370, 25], [376, 0, 548, 25]];

  function open(m) {
    if (window.Options) Options.load();
    if (window.Help) Help.ensure();
    if (window.WorldMap && WorldMap.ensure) WorldMap.ensure();     // its icons (a request's type 2 line)
    const b = m.buttons || null;
    let set = -1;
    if (b) set = SETS.findIndex(s => s.slots.some(([k]) => k !== "postpone" && b[k]));
    if (b && set < 0 && b.postpone) set = 0;
    cur = { ...m, type: m.type | 0, set, m: null, sb: { scroll: 0, range: 0 }, left: AUTO_MS, lastT: null };
    UIX.info = null; UIX.submenu = null;
    if (window.FM) FM.open = false;
  }
  // ours (user 10-31): a window that doesn't pause the game closes itself after 10 s (Options ▾ "Close message
  // windows after 10 s", on by default). The countdown stops while the mouse rests on the window (moved within 30 s);
  // it runs from a timer, so a hidden tab drains its pop-ups too. A plain message closed this way stays unread in the
  // Messages list; m.onTimeout (offers.js: accept a gift or tribute that fits; request(): dispatch a goods request the
  // city can pay, user 11-04) runs at the end, else the window just closes (an offer left unanswered is offered again
  // next month; a troops request stays open = Postpone). bugs.md 326, 474
  const AUTO_MS = 10000;
  let mouseAt = 0;
  addEventListener("mousemove", () => { mouseAt = performance.now(); });
  const auto = () => !!cur && !modal() && (typeof PAUSE === "undefined" || PAUSE.auto !== false);
  setInterval(() => {
    if (!auto()) { if (cur) cur.lastT = null; return; }
    const now = performance.now(), dt = cur.lastT == null ? 0 : now - cur.lastT, m = cur.m;
    cur.lastT = now;
    const reading = document.visibilityState === "visible" && now - mouseAt < 30000 && m && uiHover(m.X, m.Y, m.W, m.H);
    if (!reading) cur.left -= dt;
    if (cur.left <= 0) timeUp();
  }, 250);
  function timeUp() {                              // the countdown's end (or a right click on an offer, not modal)
    const c = cur;
    c.onClose = null;                              // not read: it stays unread in the Messages list
    close();
    if (typeof c.onTimeout === "function") c.onTimeout();
  }

  function close() {
    const c = cur;
    cur = null;
    if (c && c.onClose) c.onClose();
  }
  const isOpen = () => !!cur;
  const flags = () => {                             // the shown slots' bits (0 = no action buttons)
    if (!cur || cur.set < 0) return 0;
    return SETS[cur.set].slots.reduce((f, [k, bit]) => f | (cur.buttons[k] ? bit : 0), 0);
  };

  // the message's month / year: given, or from its tick against the city's date (S.date "May 1340 BC", S.tick)
  function dateOf(c) {
    if (c.month != null && c.year != null) return [c.month, c.year];
    const cd = String((typeof S !== "undefined" && S && S.date) || "").split(" ");
    const mi = Math.max(0, [...Array(12).keys()].find(k => t(25, k) === cd[0]) ?? 0);
    const ys = parseInt(cd[1], 10) * (cd[2] === "BC" ? -1 : 1) || 0;
    const tick = c.tick != null ? c.tick : (S ? S.tick : 0);
    // the month pass (month_advance 0x00483C10: before month + 1; our tick on the boundary) posts in the old month
    const mt = tick > 0 && tick % TPM === 0 ? tick - 1 : tick;
    const back = S ? Math.floor(S.tick / TPM) - Math.floor(mt / TPM) : 0;
    const abs = ys * 12 + mi - back, y = Math.floor(abs / 12);
    return [abs - 12 * y, y];
  }

  // help_page_draw's first pass (DAT_00ef8c60 == 0, layout 2 with no picture and no caption): the window is as
  // wide as the city view (view width rounded down to 16, centred), 400 high at first; the text is measured at
  // 16*(cols-4)-16; when it fits, the height shrinks to (lines + 5 + extra) rows of 16 + 80 (extra 3 for types
  // 1, 2, 5, 6, 7, 8), at most 400, and FUN_004F27F0 spreads the button sets over the width; the window sits on
  // the view's bottom edge
  function measure(c) {
    // the city view (map_view_set_size 0x00449E50: right = 60 * cols - 2, bottom = 15 * (rows - 1) + 30; 800x600:
    // 10 x 39 -> 598, 600; 1024x768: 14 x 50 -> 838, 765); other sizes (ours): as many 60-px columns as fit
    // left of the panel, as many 15-px rows as fit
    const vw = 60 * Math.trunc((UIX.panelX + 2) / 60) - 2, vb = 15 * Math.trunc((UIX.H - uiBarH() - 30) / 15) + 30;   // ours: above our speed bar (bugs.md 390)
    const rem = vw & 15, W = vw - rem, X = rem >> 1, cols = W >> 4;
    let H = 400;
    const rows = (h) => Math.trunc(h / 16) - 5 - 1;   // (T - Y + 32) / 16 = (48 + 32) / 16
    const N = ZText.helpLayout(BODY, c.body || "", 16 * (cols - 4) - 16, () => 0).count;
    let R = rows(H), V = R - 1, C = cols - 4, range = 0, rects = RECTS;
    if (N > V) range = N - V;
    else {
      const extra = [1, 2, 5, 6, 7, 8].includes(c.type) ? 3 : 0;
      H = Math.min(400, (N + 5 + extra) * 16 + 80);
      R = rows(H); V = R - 1; C = cols - 2;
      const gap = Math.trunc((W - RECTS.reduce((s, r) => s + r[2] - r[0], 0)) / 3);   // FUN_004F2790
      let x = Math.trunc(gap / 2);
      rects = RECTS.map(([a, b, cc, d]) => { const r = [x, b, x + cc - a, d]; x += cc - a + gap; return r; });
    }
    const Y = vb - H, T = Y + 48;
    const lay = ZText.helpLayout(BODY, c.body || "", 16 * C - 16, () => 0);
    c.m = { X, Y, W, H, T, R, V, C, lay, rects, vb, key: UIX.W + "x" + UIX.H + "b" + uiBarH() };
    c.sb.range = range;
    c.sb.scroll = Math.max(0, Math.min(c.sb.scroll, range));
  }

  // year_text_draw 0x00508E50 at x; returns the pen it leaves (DAT_00F13A70: every string adds its advance + 6)
  function year(y, x, yy, f) {
    const num = ZText.numberText(Math.abs(y), " ", " "), sp = 6;
    if (y < 0) { uiText(num, x, yy, f); uiText(t(20, 0), x + ZText.advance(f, num) + sp, yy, f); return ZText.advance(f, num) + sp + ZText.advance(f, t(20, 0)) + sp; }
    uiText(t(20, 1), x, yy, f); uiText(num, x + ZText.advance(f, t(20, 1)) + sp, yy, f);
    return ZText.advance(f, t(20, 1)) + sp + ZText.advance(f, num) + sp;
  }
  const adv = (f, s) => ZText.advance(f, s) + 6;

  function goodIcon(g) {
    // help_page_draw 0x004F2D80 type 2: drachmas General group 3 (font_group_entry(3) + 0x10000, the world map's
    // SPR_REQUEST_CASH_ICON), food General SPR_GOODS_ICONS 0x13 (entry 0x7A + wine's + 0x10001), else the good's icon
    const wc = window.WorldMap && WorldMap.conf;
    if (g === "drachmas" && wc) return sprite(wc.icons.drachmas.file, wc.icons.drachmas.index);
    if (g === "food" && wc) return sprite(wc.dialog_icons.food.file, wc.dialog_icons.food.index);
    const r = window.MAP && MAP.info_panels && MAP.info_panels.goods_icons && MAP.info_panels.goods_icons[g];
    return r ? sprite(r.file, r.index) : null;
  }

  function draw() {
    if (!cur || !window.ZText) return;
    if (window.Balloon) Balloon.none();             // screen 5: no balloons
    if (!cur.m || cur.m.key !== UIX.W + "x" + UIX.H + "b" + uiBarH()) measure(cur);
    const c = cur, m = c.m, { X, Y, W, H, T, R, V, C } = m, Xi = X + 16, fl = flags();
    uiFrame("titled", X, Y, W / 16, H / 16);
    UIX.hits.push(modal() ? [0, 0, UIX.W, UIX.H, null, ""] : [X, Y, W, H, null, ""]);   // not modal: only the window
    uiText(c.title || "", X + 8, Y + 0x0E, "SPR_FONTS_22C", { center: W + 0x14 });
    uiFrame("plain", Xi, T, C, R);
    const clip = [Xi + 3, T + 3, Xi + 16 * C - 3, T + 16 * R - 3];
    uiFlushText();
    // date line (type != 4): month 25:m at (Xi+10, T+6), the year 12 px after it; then "To" 63:5 and the ruler's
    // name at Xi+0x50 + the year's pen (type 1 with a site: the site text at X+0xF0 instead)
    if (c.type !== 4) {
      const [mo, yr] = dateOf(c), ms = t(25, mo), yy = T + 6;
      uiText(ms, Xi + 10, yy, DATE);
      const yp = year(yr, Xi + 12 + adv(DATE, ms), yy, DATE);
      if (c.type === 1 && c.site) uiText(c.site, X + 0xF0, yy, DATE);
      else {
        uiText(t(63, 5), Xi + 0x50 + yp, yy, DATE);
        uiText(c.to || (S && S.player) || (window.NewGame && NewGame.leader()) || "Ruler", Xi + 0x50 + yp + adv(DATE, t(63, 5)), yy, DATE);
      }
    }
    // the line under the date and where the body starts
    let by = T + 0x38;
    if ([1, 7, 8].includes(c.type)) { if (!fl) uiText(t(12, 1), X + 100, T + 0x2C, DATE); by = T + 0x56; }
    else if (c.type === 3) { if (c.reason >= 3 && c.reason <= 7) uiText(t(12, c.reason), X + 0x40, T + 0x2C, DATE); by = T + 0x56; }
    else if (c.type === 4) by = T + 6;
    else if (c.type === 5) {
      uiPut(goodIcon(c.good), Xi + 8, T + 0x28);
      uiText(c.goodName || "", Xi + 0x20, T + 0x2C, DATE);
      by = T + 0x56;
    } else if (c.type === 6) {
      uiPut(goodIcon(c.good || "silver"), X + 0x40, T + 0x28);
      uiText(ZText.numberText(c.amount | 0, "@", " ") + t(6, 0), X + 100, T + 0x2C, DATE);
      by = T + 0x56;
    }
    const boxes = [], push = (sp, px, py) => uiClipPush((q, qx, qy) => UIX.batch.push(q, qx, qy), sp, px, py, clip);
    const lines = m.lay.lines;
    const sc = c.sb.scroll;
    let drawn = 0;
    for (let k = sc; k < lines.length && k < sc + V; k++, drawn++)
      ZText.helpLine(push, BODY, LINK, lines[k].text, Xi + 8 + lines[k].indent, by + (k - sc) * 16, boxes);
    if (c.type === 2 && c.good) {                   // the request: icon, amount + goods, "n months to comply"
      const ly = T + 0x56 + 16 * drawn;               // T+0x56 + DAT_00F13A6C (taken as the body's height: no shot)
      uiPut(goodIcon(c.good), Xi + 8, ly - 5);
      const n = ZText.numberText(c.amount | 0, "@", " ");
      uiText(n, Xi + 0x14, ly, DATE);
      uiText(c.goodName || "", Xi + 0x14 + adv(DATE, n), ly, DATE);
      if (c.months != null) {
        const cn = ZText.numberText(c.months, " ", ""), w = t(8, 4 + (Math.abs(c.months) === 1 ? 0 : 1));
        uiText(cn, Xi + 0xDC, ly, DATE); uiText(w, Xi + 0xDC + adv(DATE, cn), ly, DATE);
        uiText(t(12, 2), Xi + 0xDC + adv(DATE, cn) + adv(DATE, w), ly, DATE);
      }
    }
    if (c.sb.range && window.Help) Help.scrollbar(Xi + 16 * C - 1, T, 16 * R, c.sb);
    if (!fl) {
      // help (0x005EF898: drawn at Y+H-40, hit at Y+H-36 18x27) -> help record 87; go-to (0x005EF8C0) for
      // types 1/7/8 at (X+0x40, T+0x24); close (0x005EF820) at (X+W-38, Y+H-36)
      const hx = Xi, hy = Y + H - 40;
      uiPut(sprite("Zeus_Interface", HELP + (uiHover(hx, Y + H - 36, 18, 27) ? 1 : 0)), hx, hy);
      UIX.hits.push([hx, Y + H - 36, 18, 27, () => { close(); Help.open(87, 0); }, "Help"]);
      if ([1, 7, 8].includes(c.type)) {
        const gx = X + 0x40, gy = T + 0x24, hov = uiHover(gx, gy, 27, 27);
        uiPut(sprite("Zeus_Interface", GOTO + (hov && UIX.down ? 2 : hov ? 1 : 0)), gx, gy);
        UIX.hits.push([gx, gy, 27, 27, () => goTo(c), t(12, 1)]);
      }
      const cx = X + W - 38, cy = Y + H - 36;
      uiPut(sprite("Zeus_Interface", CLOSE + (uiHover(cx, cy, 24, 24) ? 1 : 0)), cx, cy);
      UIX.hits.push([cx, cy, 24, 24, close, "Close"]);
    } else {
      // FUN_004F28C0: the set's shown slots at (X + x0, view bottom - 35): RIMS box (x1-x0) x 25, hovered = the
      // highlight's second look; label centred from x0+6 in x1-x0 (+1 for the formatted ones) at y0+6
      const S0 = SETS[c.set], bx = m.vb - 35;
      S0.slots.forEach(([k, bit, id], i) => {
        if (!c.buttons[k]) return;
        const [a, b, cc, d] = m.rects[i], x = X + a, y = bx + b, w = cc - a, h = d - b;
        Options.rims(x, y, w, h, uiHover(x, y, w, h));
        let s = t(44, id);
        if (k === "bribe") s = s.replace("[bribe_amount]", String(c.buttons.bribeAmount ?? ""));
        uiText(s, x + 6, y + 6, S0.font, { center: w + (k === "bribe" || c.set === 2 ? 1 : 0) });
        UIX.hits.push([x, y, w, h, () => { const fn = c.buttons[k]; close(); if (typeof fn === "function") fn(); }, s]);
      });
    }
    if (auto()) {                                  // ours: the countdown, right end of the date line
      const n = Math.max(1, Math.ceil(c.left / 1000)), s = `${c.onTimeout ? "Accepts" : "Closes"} in ${n}`;
      uiText(s, Xi + 16 * C - 12 - ZText.advance(DATE, s), T + 6, DATE);
    }
    // links (exe: only when no buttons) open the help record, history kept by the help window
    if (!fl) for (const [a, b, cc, d, rec] of boxes.slice().reverse()) UIX.hits.push([a, b, cc - a + 1, d - b + 1, () => { close(); Help.open(rec, 0); }, ""]);
  }

  // wm_sub_522E30: centre the view on the message's tile and return to the city (the Messages list closes too)
  function goTo(c) {
    const g = c.goto;
    close();
    if (window.Lists) Lists.close();
    if (window.WorldMap && WorldMap.isOpen()) WorldMap.close();   // ours: a window over the running world map
    if (g) uiCenterOn(g[0], g[1]);                // ui.js (FUN_0044A7D0)
  }

  // a right click anywhere closes a window without action buttons (0x004F4CF0: 0x00F2A6FC and flags == 0), modal or
  // not (user 10-31: closing with a right click anywhere beats right-clicking the city under it)
  // the original's message window is modal (screen 5, the game paused); ours only while Options ▾ "Pause on message
  // windows" is on (play.js PAUSE.msg; bugs.md 317, 322)
  function modal() { return typeof PAUSE === "undefined" || PAUSE.msg; }

  function rightClick(x, y) {
    if (!cur) return false;
    if (!flags()) { close(); return true; }
    if (modal()) return true;                          // buttons (an offer), as the original: answer with a button
    timeUp();                                          // ours (bugs.md 326): not modal, a right click ends the countdown
    return true;
  }

  // a city message (state.json) in the window: our messages carry the exe's title / body phrases when the sim
  // posted them from Model/Zeus eventmsg.txt (sim/messages.py); other lines (ours) show their first sentence as
  // the title and the whole line as the body. A "(x,y)" in the line (ours) makes it a type 1 message with the
  // go-to button
  function fromMessage(msg, extra = {}) {
    const text = String(msg.text || "");
    let title = msg.title, body = msg.body;
    if (title == null || typeof title === "number") {            // a number: a phrase id (saves before bugs.md 316)
      const i = text.search(/[.!?] /);
      title = i > 0 ? text.slice(0, text[i] === "." ? i : i + 1) : text;
      body = text;
    }
    const at = msg.at || (/\((\d+),\s*(\d+)\)/.exec(text) || []).slice(1, 3).map(Number);
    const go = at && at.length === 2 && !isNaN(at[0]);
    open({ type: msg.type != null ? msg.type : go ? 1 : 0, title, body, tick: msg.tick, goto: go ? at : null, ...request(msg), ...extra });
  }

  // A scenario request's message (sim/empire/requests.py: record 0xDF type 2 / 0xE0, the event, its flags +0x16):
  // message_window_open 0x004F2600 keeps the 0x1C0 buttons only while request_can_fulfil (state.json events `can`;
  // a record no longer open finds nothing, FUN_004757B0) and clears them for good otherwise; a pressed button clears
  // them too (wm_sub_475AB0 / 475B20 / 475B50: +0x16 = 0). Dispatch now: goods leave at once
  // (event_pay_tribute_or_gift), troops open the army dialog (army_dialog_open); Postpone just closes; Refuse:
  // wm_sub_475B50. Type 2 draws the item's icon, amount and name (none for troops) and "n months to comply" while the
  // record is in state 0.
  const cleared = new Set();
  function request(msg) {
    if (msg.type !== 2 && !msg.buttons) return {};
    const key = msg.tick + "|" + msg.text, evs = (typeof S !== "undefined" && S && S.events) || [];
    const e = msg.event != null ? evs.find(q => q.id === msg.event) : null;
    const o = { good: msg.item === 24 ? null : msg.good, goodName: msg.goodName, amount: msg.amount,
                months: msg.event == null ? msg.months : e && e.state === 0 ? msg.months : null };   // tribute: the poster's
    if (!(msg.buttons & 0x1C0) || cleared.has(key)) return o;
    if (!e || !e.can) { cleared.add(key); return o; }
    const done = () => cleared.add(key);
    o.buttons = {
      dispatch: () => { done(); if (e.item === 24) armyFor(e); else sendCommands([`answer ${e.id} dispatch`], { sound: false }); },
      postpone: () => { done(); },
      refuse: () => { done(); sendCommands([`answer ${e.id} refuse`], { sound: false }); } };
    // ours (user 11-04): the 10 s countdown dispatches a goods / money / food request the city can pay ("Accepts in");
    // troops need the army dialog's choice of forces, so their window only closes (= Postpone)
    if (e.item !== 24) o.onTimeout = () => {
      const now = ((typeof S !== "undefined" && S && S.events) || []).find(q => q.id === e.id);
      if (!cleared.has(key) && now && now.can) o.buttons.dispatch();
    };
    return o;
  }
  function armyFor(e) {                              // army_dialog_open for the record (milpanel.js, kind "request")
    if (window.Military) Military.refresh();
    if (window.MilPanel) MilPanel.openArmy(e.city, "request", e.route, [], [], null, e);
  }

  // message_queue_poll 0x00521D30: a new message the sim marked to pop up (sim/messages.py Msg) opens while the
  // city screen is up (no window, dialog, advisor or list), one at a time, 5 polls after the last; it counts as
  // read. Its category's setting (Options > Messages, 0x00521970): 2 Full pops it, 1 Condensed / 0 Off do not
  // (Condensed shows it only in the panel's message strip, drawStrip); category 19 always pops.
  // Another game in the tab (a campaign episode switch loads the parent city with its message history, File > Load,
  // a timeline jump): the state's tick moves by more than any play speed covers in a poll; its messages are history
  // (the exe restores the queue with the save and plays a god's line only when it is posted, FUN_005A1050), so they
  // are primed as seen, not popped or voiced (bugs.md 430: the parent city's old Ares lines played over the
  // episode-4 briefing). While a campaign or new-game screen is up the exe's city stands still and the screen's
  // narration (FUN_005A88C0) holds the voice stream: no god line plays then either.
  const seen = new Set(), voiced = new Set();
  let primed = false, wait = 0, lastTick = null;
  const JUMP = 2000;                                 // ticks between two polls 100 ms apart (128x = 384)
  setInterval(() => {
    const ms = (typeof S !== "undefined" && S && S.messages) || null;
    if (!ms) return;
    const k = (m) => m.tick + "|" + m.text, tk = S.tick || 0;
    if (lastTick != null && Math.abs(tk - lastTick) > JUMP) primed = false;
    lastTick = tk;
    if (!primed) { for (const m of ms) { seen.add(k(m)); voiced.add(k(m)); } primed = !!ms.length || (S.tick > 0); return; }
    const screen = (window.Campaign && Campaign.screen && Campaign.screen()) || (window.NewGame && NewGame.isOpen && NewGame.isOpen());
    for (const q of ms) if ((q.voice || q.stinger) && !voiced.has(k(q))) {   // a god's / hero's line and a stinger
      voiced.add(k(q));                                                       // play as the message arrives
      const A = typeof audio !== "undefined" && audio, C = A && A.cfg && A.cfg.music;
      const st = q.stinger && C && C.special && C.special[q.stinger];
      if (!screen && A && A.specials) A.specials([[q.voice, 1], [st, 0]]);
    }
    const busy = cur || (window.Help && Help.isOpen()) || (window.Lists && Lists.isOpen()) || (window.Advisors && Advisors.isOpen())
      || (window.WorldMap && WorldMap.holdsPopups()) || (window.Options && Options.isOpen && Options.isOpen()) || (typeof UIX !== "undefined" && UIX.info);
    if (busy) { wait = 5; return; }
    if (wait > 0) { wait--; return; }
    const m = ms.find(q => !seen.has(k(q)) && q.popup);
    for (const q of ms) if (!q.popup) seen.add(k(q));
    if (!m) return;
    seen.add(k(m));
    const set = window.Options && Options.settings ? Options.settings.messages : null;
    const c = m.category == null ? 19 : m.category;
    if (c !== 19 && set && set[c] !== 2) return;
    fromMessage(m, { onClose: () => { if (window.Lists && Lists.markRead) Lists.markRead(m); } });   // read when closed by hand
  }, 100);

  // the panel's message strip (FUN_005170A0 -> FUN_00430D80; widget 0x007815A0 set up by FUN_00430FB0 on every new
  // message): the queue newest first (FUN_005221B0 inserts at 0), the messages whose category is not Off
  // (FUN_00521970) and whose announcement has a condensed phrase (FUN_00477D60; sim meta `condensed`); one shown,
  // the scroll-th, DKMESSAGE paragraph at (panelX+13, 517) wrapped in 155. More than one: SPR_SM_BUTTON_UP / _DOWN
  // (table 0x005ED1A8) at (panelX+162, 514 / 543) step it (0x00430D20; +1 while held). A click on the strip (panelX+8,
  // 512) 155x50 opens that message (0x00430ED0 -> FUN_00522BD0).
  let strip = { scroll: 0, head: null, held: null };
  function stripRows() {
    const ms = (typeof S !== "undefined" && S && S.messages) || [];
    const set = window.Options && Options.settings ? Options.settings.messages : null;
    return ms.slice().reverse().filter(m => m.condensed && !(m.category != null && m.category !== 19 && set && set[m.category] === 0));
  }
  function drawStrip(X) {
    const rows = stripRows(), head = rows.length ? rows[0].tick + "|" + rows[0].text : null;
    if (head !== strip.head) { strip.head = head; strip.scroll = 0; }
    strip.scroll = Math.max(0, Math.min(strip.scroll, rows.length - 1));
    const m = rows[strip.scroll];
    if (!m) return;
    UIX.hits.push([X + 8, 512, 155, 50, () => { if (window.Lists && Lists.markRead) Lists.markRead(m); fromMessage(m); }, ""]);
    if (window.ZText) ZText.paragraph((sp, px, py) => UIX.batch.push(sp, px, py), "SPR_FONTS_DKMESSAGE", m.condensed, X + 13, 517, 155);
    if (rows.length > 1) {
      const held = (k) => strip.held === k && UIX.down;
      uiPut(sprite("Zeus_Interface", 576 + (held(0) ? 1 : 0)), X + 162, 514);
      uiPut(sprite("Zeus_Interface", 578 + (held(1) ? 1 : 0)), X + 162, 543);
      UIX.hits.push([X + 162, 514, 17, 17, () => { strip.held = 0; strip.scroll = Math.max(0, strip.scroll - 1); }, ""]);
      UIX.hits.push([X + 162, 543, 17, 17, () => { strip.held = 1; strip.scroll = Math.min(rows.length - 1, strip.scroll + 1); }, ""]);
    }
  }

  window.addEventListener("wheel", e => {
    if (!cur || !cur.sb.range) return;
    e.preventDefault(); e.stopPropagation();
    cur.sb.scroll = Math.max(0, Math.min(cur.sb.range, cur.sb.scroll + Math.sign(e.deltaY) * Math.max(1, Math.round(Math.abs(e.deltaY) / 120)) * 3));
  }, { capture: true, passive: false });

  return { open, close, isOpen, modal, draw, rightClick, fromMessage, drawStrip, state: () => cur };
})();
window.MsgWin = MsgWin;
