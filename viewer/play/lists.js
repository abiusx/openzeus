// The lower control panel's Messages list (screen 0x11: background 0x00522340, draw 0x00522620, input 0x005229C0)
// and Goals screen (0x3B: objectives_screen_draw 0x0052C070), as the exe draws them (docs/play/lists.md).
// Texts: data/play/options.json (options.js), Zeus_MM.eng records: help.js. Messages are the city's message lines
// (state.json messages: tick + text); a goal-less open play city has no goals (44:280).
"use strict";

const Lists = (() => {
  let screen = null, goals = null;                  // "messages" | "goals"
  let child = null;                                 // the goals screen's child window (+0x84): a quest's text
  const msg = { scroll: 0, range: 0, read: new Set(), gone: new Set() };
  const brief = { scroll: 0, range: 0, key: null, lay: null };
  const ox = () => Math.trunc((UIX.W - 640) / 2), oy = () => Math.trunc((UIX.H - 480) / 2);
  const t = (g, i) => (window.Options ? Options.text(g, i) : "");
  const TPM = 51 * 16;                              // ticks per month (51-tick days, 16 days a month)

  function open(kind) {
    if (window.Options) Options.load();
    if (window.Help) Help.ensure();
    screen = kind; UIX.info = null; UIX.submenu = null;
    if (kind === "goals") getJSON("/goals.json").then(d => { goals = d; brief.key = null; }).catch(() => { goals = { adventure: -1, episode: -1, city: "", goals: [] }; });
  }
  function close() { screen = null; child = null; }
  function isOpen() { return !!screen || !!child; }

  // ---- messages -------------------------------------------------------------------------------------------
  const key = (m) => m.tick + "|" + m.text;
  function list() {                                 // oldest first, newest at the bottom (oracle messages-list12)
    return ((typeof S !== "undefined" && S && S.messages) || []).filter(m => !msg.gone.has(key(m)));
  }
  function dateOf(m) {                              // month 25:m and the year text of the message's tick
    const cur = String((typeof S !== "undefined" && S && S.date) || "").split(" ");
    const mi = [...Array(12).keys()].find(k => t(25, k) === cur[0]) ?? 0;
    const ys = parseInt(cur[1], 10) * (cur[2] === "BC" ? -1 : 1);
    // a message of the month pass (month_advance 0x00483C10 runs it before month + 1: our tick on the boundary)
    // carries the old month, as the exe's
    const mt = m.tick > 0 && m.tick % TPM === 0 ? m.tick - 1 : m.tick;
    const back = Math.floor(S.tick / TPM) - Math.floor(mt / TPM);
    const abs = (ys * 12 + mi) - back, y = Math.floor(abs / 12), mo = abs - 12 * y;
    return [t(25, mo), y];
  }
  // year_text_draw 0x00508E50: BC = number_text_draw(n, sign ' ', suffix ' ') then 20:0 at the pen (advance + one space);
  // AD = 20:1 then the number at the pen
  function yearText(y, x, yy, f) {
    const sp = 6, num = ZText.numberText(Math.abs(y), " ", " ");        // sign ' ', suffix 0x005E8FD0 = " "
    if (y < 0) { uiText(num, x, yy, f); uiText(t(20, 0), x + ZText.advance(f, num) + sp, yy, f); }
    else { uiText(t(20, 1), x, yy, f); uiText(num, x + ZText.advance(f, t(20, 1)) + sp, yy, f); }
  }
  // the subject: the message's title (sim/messages.py line(): "Title. Announcement", the '.' added unless the title
  // ends with ! ? .)
  const subject = (text) => { const i = text.search(/[.!?] /); return i > 0 ? text.slice(0, text[i] === "." ? i : i + 1) : text; };

  function drawMessages() {
    const X = ox(), Y = oy(), F = [X - 75, Y + 32], FC = 37, FR = 24, L = [X - 59, Y + 102], ms = list();
    uiFrame("titled", F[0], F[1], FC, FR);
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    uiText(t(63, 0), F[0], F[1] + 16, "SPR_FONTS_22C", { center: 16 * FC });
    uiFrame("plain", L[0], L[1], 33, 13);
    const bx = F[0] + 8 * FC - 140, by = F[1] + 16 * FR - 72;           // the two RIMS buttons' origin (0x005EE458)
    if (!ms.length) uiText(t(63, 1), L[0] + 16, L[1] + 80, "SPR_FONTS_11CB", { width: 16 * 30 });
    else {
      uiText(t(63, 2), L[0] + 42, L[1] - 18, "SPR_FONTS_11C");
      uiText(t(63, 3), L[0] + 170, L[1] - 18, "SPR_FONTS_11C");
      uiText(t(63, 4), L[0] + 40, L[1] + 16 * 13 + 3, "SPR_FONTS_11C", { width: 16 * 33 - 50 });
      uiText(t(63, 6), bx, F[1] + 16 * FR - 65, "SPR_FONTS_11C", { center: 0x118 });
    }
    uiText(t(63, 7), F[0] + 8 * FC - 240, F[1] + 16 * FR - 33, "SPR_FONTS_11C", { center: 0x1E0 });
    // buttons: [0] delete opened (only with messages) (0,0)-(280,30); [1] message options (-100,32)-(380,62); hovered:
    // the highlight's second variant
    const B = [[0, 0, 280, 30, () => { for (const m of ms) if (msg.read.has(key(m))) msg.gone.add(key(m)); }],
               [-100, 32, 380, 62, () => { Options.open("messages"); }]];
    B.forEach(([a, b, c, d, fn], i) => {
      if (i === 0 && !ms.length) return;
      const hov = uiHover(bx + a, by + b, c - a, d - b);
      Options.rims(bx + a, by + b, c - a, d - b, hov);
      UIX.hits.push([bx + a, by + b, c - a, d - b, fn, i ? t(63, 7) : t(63, 6)]);
    });
    // rows: 10 visible, 20 px apart
    msg.range = Math.max(0, ms.length - 10);
    msg.rows = [];
    msg.scroll = Math.max(0, Math.min(msg.scroll, msg.range));
    for (let i = 0; i < Math.min(10, ms.length - msg.scroll); i++) {
      const m = ms[msg.scroll + i], k = key(m), y = L[1] + 20 * i, read = msg.read.has(k);
      uiPut(sprite("Zeus_Interface", 244 + (read ? 15 : 14)), L[0] + (read ? 12 : 8), y + 6);
      const hov = uiHover(L[0], L[1] + 4 + 20 * i, 416, 18), f = hov ? "SPR_FONTS_11C3" : "SPR_FONTS_11C2";
      const [mo, yr] = dateOf(m);
      uiText(mo, L[0] + 42, y + 8, f);
      yearText(yr, L[0] + 72, y + 8, f);
      // ours: our message lines can be longer than the exe's subjects: cut at the list box's inner edge
      uiText(subject(m.text), L[0] + 180, y + 8, f, { clip: [L[0] + 3, L[1] + 3, L[0] + 16 * 33 - 3, L[1] + 16 * 13 - 3] });
      UIX.hits.push([L[0], L[1] + 4 + 20 * i, 416, 18, () => { msg.read.add(k); MsgWin.fromMessage(m); }, ""]);
      msg.rows.push([L[0], L[1] + 4 + 20 * i, 416, 18, () => msg.gone.add(k)]);
    }
    if (ms.length > 10) Help.scrollbar(L[0] + 16 * 33, L[1], 208, msg);
    corner(F[0], F[1], FC, FR, 87);
  }

  // help (rec) and close buttons at the window's bottom corners (0x005EF8E8 / 0x005EF910)
  function corner(x, y, cols, rows, rec) {
    const hx = x + 16, hy = y + 16 * rows - 42, cx = x + 16 * cols - 38, cy = y + 16 * rows - 36;
    uiPut(sprite("Zeus_Interface", 533 + (uiHover(hx, hy, 27, 27) ? 1 : 0)), hx, hy);
    uiPut(sprite("Zeus_Interface", 537 + (uiHover(cx, cy, 24, 24) ? 1 : 0)), cx, cy);
    if (rec != null) UIX.hits.push([hx, hy, 27, 27, () => Help.open(rec, 1), "Help"]);
    if (window.Balloon && screen === "messages") { Balloon.add(hx, hy, 27, 27, 1); Balloon.add(cx, cy, 24, 24, 2); }
    UIX.hits.push([cx, cy, 24, 24, close, "Close"]);
  }

  // ---- goals / victory / adventure complete (objectives_screen_draw 0x0052C070) --------------------------------
  // One drawer for screen 0x3B (goals, d = /goals.json), 0x42 (victory, FUN_0052D590) and 0x43 (adventure complete,
  // FUN_0052D7C0; d = /campaign.json, campaign.js). 0x43 moves everything by (DAT_00FE42D8, DAT_00FE42DC) = (100, -20).
  // Goal rows: widget table 0x00640830 (rect i = (430, 84 + 20i) - (594, 104 + 20i), relative to the 640 x 480
  // origin): the tick box SPR_CHECKBOX 607 (ticked) / 608 at (G.x + 0x1B, rect.y + 3), the goal text at rect.x - 0x1CB,
  // the status at rect.x - 0x5E (11C2, y + 6), and for a button row (Set aside, sim/campaign/texts.py) the
  // highlight (window_highlight_draw, hovered: the second look) over the status at rect.x - 0x6A, 164 x 20.
  function objectives(mode, d) {
    const X = ox(), Y = oy(), H = Help.data && Help.data(), dx = mode === "complete" ? 100 : 0, dy = mode === "complete" ? -20 : 0;
    const G = [X - 76 + dx, Y + dy], GC = 37, GR = 33;
    uiFrame("titled", G[0], G[1], GC, GR);
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    if (!d || !H) return;
    const rec = (n) => (n >= 0 && H.records[n]) || null, epNo = d.episode != null ? d.episode : d.intro;
    const advNo = d.adventure != null && typeof d.adventure === "number" ? d.adventure : d.brief;
    if (d.city) uiText(d.city, G[0] + 16, G[1] + 42, "SPR_FONTS_11C", { align: "right", width: 0x230 });
    // separator: SPR_MARBLE_BAR 604 (first), 605 (middle), 606 (last), 36 tiles at (G.x+8, G.y+54) (tile_row_draw)
    for (let i = 0; i < 36; i++) uiPut(sprite("Zeus_Interface", 604 + (i === 0 ? 0 : i < 35 ? 1 : 2)), G[0] + 8 + 16 * i, G[1] + 0x36);
    if (mode === "goals") {
      uiText(t(44, 276), G[0] + 99, G[1] + 0x40, "SPR_FONTS_11C");
      uiText(t(44, 277), G[0] + 437, G[1] + 0x40, "SPR_FONTS_11C");
      // a tutorial (0x006AA4CC == 2): "Right-click to continue" at +0x1BA and the tutorial buttons below it
      uiText(t(13, 3), G[0], G[1] + (d && d.tutorial ? 0x1BA : 0x1F8), "SPR_FONTS_11C", { center: 0x250 });
      if (d && d.tutorial) tutorialButtons(d.tutorial);
    } else uiText(t(62, 0), G[0], G[1] + 0x40, "SPR_FONTS_11C", { center: 0x250 });
    const rows = d.goals || [], n = rows.length, B = Math.trunc((Math.max(n, 1) * 20 + 19) / 16) + 1;
    uiFrame("plain", G[0] + 16, G[1] + 0x4C, 0x23, B);
    if (!n) uiText(t(44, 280), X + 430 - 0x12E + dx, Y + 84 + 6 + dy, "SPR_FONTS_11C2");     // rect 0 (430,84) - 302, + 6
    rows.forEach((r, i) => {
      const ry = Y + 84 + 20 * i + dy;
      uiPut(sprite("Zeus_Interface", 607 + (r.box ? 0 : 1)), G[0] + 0x1B, ry + 3);
      uiText(r.goal, X + 430 - 0x1CB + dx, ry + 6, "SPR_FONTS_11C2");
      if (r.button) {
        const bx = X + 430 - 0x6A + dx, hov = uiHover(bx, ry, 164, 20);
        Options.rims(bx, ry, 164, 20, hov);
        UIX.hits.push([bx, ry, 164, 20, () => { if (window.Campaign) Campaign.rowClick(i, r); }, ""]);
      }
      uiText(r.status, X + 430 - 0x5E + dx, ry + 6, "SPR_FONTS_11C2");
    });
    const s = d.strings || {};                     // a custom adventure's .txt texts (sim/campaign flow.screens)
    const title = mode === "goals" ? (rec(advNo) ? rec(advNo)[13] : s.title) : t(62, 0);
    const line = mode === "complete" ? (rec(d.complete) ? rec(d.complete)[13] : s.complete_title) : (rec(epNo) ? rec(epNo)[13] : s.ep_title);
    const bodyNo = mode === "complete" ? d.complete : mode === "victory" ? d.victory : epNo;
    const bodyRec = rec(bodyNo) || [, , , , , , , , , , , , , "", , mode === "complete" ? s.complete_body : mode === "victory" ? s.victory_body : s.ep_body];
    if (line) uiText(line, G[0] + 16, G[1] + 0x2A, "SPR_FONTS_11C");      // episode title (FUN_0042B640 / 0042B7B0)
    if (title) uiText(title, G[0], G[1] + 10, "SPR_FONTS_22C", { center: 0x250 });
    // the body: the record's text (11C2, links 11C4), laid out as a help page in (G.x, G.y+16B+72) 592 x (392-16B)
    const Yb = G[1] + 16 * B + 0x48, Hb = 0x188 - 16 * B, T = Yb + 0x20;
    const R = Math.trunc(Hb / 16) - Math.trunc((T - Yb + 0x20) / 16) - 1;
    textBox(brief, mode + ":" + bodyNo + ":" + (bodyRec[15] || "").length + ":" + UIX.W + ":" + UIX.H, bodyRec[15] || "",
            G[0] + 16, T, 0x250 / 16 - 4, R);
  }

  // The tutorial buttons of 0x3B (objectives_screen_draw 0x0052C070, table 0x006408D8 at (ox - 0x4E, oy); the click
  // 0x005BED70 by the row's parameter): 0 Previous tutorial (24,486)-(200,511) when there is one (FUN_005BEA70),
  // 1 New tutorial (208,486)-(384,511), 2 Next tutorial (392,486)-(568,511) when there is one (FUN_005BEAC0), 3 Start
  // this tutorial over (176,458)-(416,483); rims (FUN_00509230, hover look), 293:(14 + i) 11C centred at +6
  // (FUN_00509320). Ours: previous / next / over start that tutorial (its .sav) on the server; New tutorial opens the
  // tutorials list (the exe: FUN_005BE6F0, the tutorial menu).
  function tutorialButtons(tu) {
    const X = ox() - 0x4E, Y = oy();
    const go = (id) => async () => {
      if (!id || !window.Campaign) return;
      close();
      await Campaign.startTutorial(id);
    };
    const B = [[24, 486, 200, 511, tu.prev ? go(tu.prev) : null, !!tu.prev],
               [208, 486, 384, 511, async () => { close(); if (window.NewGame) { await NewGame.open(); NewGame.state().family = "tutorials"; NewGame.state().stage = "list"; } }, true],
               [392, 486, 568, 511, tu.next ? go(tu.next) : null, !!tu.next],
               [176, 458, 416, 483, go(tu.id), true]];
    B.forEach(([x1, y1, x2, y2, fn, shown], i) => {
      if (!shown) return;
      const x = X + x1, y = Y + y1, w = x2 - x1, h = y2 - y1, hov = uiHover(x, y, w, h);
      Options.rims(x, y, w, h, hov);
      uiText(t(293, 14 + i), x, y + 6, "SPR_FONTS_11C", { center: w });
      UIX.hits.push([x, y, w, h, fn, ""]);
    });
  }

  // A record's body in a plain frame at (x, T) of R rows, as objectives_screen_draw / the briefing 0x0052E520 lay
  // it out: (R - 1) lines shown; C0 columns with a scrollbar at x + 16 * C0 when it overflows, else C0 + 2;
  // text_layout at (x + 8, T + 6), width 16 * cols - 16 (11C2, links 11C4); a link opens the help window (ours).
  function textBox(st, key, body, x, T, C0, R) {
    const V = R - 1;
    // pictures (@G n: Zeus_Unloaded, as the help pages) take their height in lines and are drawn centred in the box
    const pic = (n) => (window.Help && Help.pic ? Help.pic(n) : null), picRows = (n) => { const sp = pic(n); return sp ? sp.h >> 4 : 0; };
    if (st.key !== key) {
      const N = ZText.helpLayout("SPR_FONTS_11C2", body, 16 * C0 - 16, picRows).count;
      st.range = N > V ? N - V : 0;
      st.C = st.range ? C0 : C0 + 2;
      st.lay = ZText.helpLayout("SPR_FONTS_11C2", body, 16 * st.C - 16, picRows, true);
      st.key = key; st.scroll = 0;
    }
    uiFrame("plain", x, T, st.C, R);
    uiFlushText();
    const clip = [x + 3, T + 3, x + 16 * st.C - 3, T + 16 * R - 3], boxes = [];
    const push = (sp, px, py) => uiClipPush((q, qx, qy) => UIX.batch.push(q, qx, qy), sp, px, py, clip);
    const L = st.lay.lines;
    for (let k = 0; k < L.length && k < st.scroll + V; k++) {      // as Help.draw: a picture whose line is scrolled
      const ln = L[k], y = T + 6 + 16 * (k - st.scroll);          // off is drawn shifted up (clipped)
      if (k >= st.scroll) ZText.helpLine(push, "SPR_FONTS_11C2", "SPR_FONTS_11C4", ln.text, x + 8 + ln.indent, y, boxes);
      if (ln.pic) { const sp = pic(ln.pic); if (sp) push(sp, x + 8 + Math.trunc((16 * st.C - sp.w - 4) / 2) - 4, y); }
    }
    for (const [a, b, c, d, r] of boxes) UIX.hits.push([a, b, c - a + 1, d - b + 1, () => Help.open(r, 1), ""]);
    if (st.range) Help.scrollbar(x + 16 * st.C, T, 16 * R, st);
  }

  function draw() {
    if (!screen && !child) return;
    uiFlushText();
    if (window.Balloon) Balloon.none();             // screen 0x11: only its help / close (68:1 / 68:2); 0x3B: none
    if (screen === "messages") drawMessages(); else if (screen) objectives("goals", goals);
    if (child) { uiFlushText(); drawQuest(); }
  }
  // the quest row's window when the army dialog can't open (0x00FE2588, drawn by 0x0052D010 in place of the goals
  // screen, whose picture stays): titled frame 28 x 12 at (ox + 0x32, oy + 0x32), the quest title 22C centred in 0x1C0
  // at (ox + 0x32, oy + 0x40), its text 11C at (ox + 0x4C, oy + 0x60) 0x1A0 wide, 13:3 at (ox + 0x32, oy + 0xDA)
  // centred in 0x1C0; a right click closes it (0x0052D200), the screen stays (sim/campaign texts.quest_window)
  function drawQuest() {
    const X = ox(), Y = oy();
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    uiFrame("titled", X + 0x32, Y + 0x32, 28, 12);
    uiText(child.title, X + 0x32, Y + 0x40, "SPR_FONTS_22C", { center: 0x1C0 });
    uiText(child.body, X + 0x4C, Y + 0x60, "SPR_FONTS_11C", { width: 0x1A0 });
    uiText(t(13, 3), X + 0x32, Y + 0xDA, "SPR_FONTS_11C", { center: 0x1C0 });
  }
  function questWindow(q) { child = q; }
  function rightClick(x, y) {                       // a right click on a message row deletes it; elsewhere closes
    if (child) { child = null; return true; }
    if (!screen) return false;
    if (screen === "messages") {
      const h = (msg.rows || []).find(q => x >= q[0] && y >= q[1] && x < q[0] + q[2] && y < q[1] + q[3]);
      if (h) { h[4](); return true; }
    }
    close();
    return true;
  }
  window.addEventListener("wheel", e => {
    if (!screen || (window.Help && Help.isOpen()) || (window.MsgWin && MsgWin.isOpen())) return;
    e.preventDefault(); e.stopPropagation();
    if (window.Campaign && Campaign.isOpen()) return;          // campaign.js scrolls its own screens
    const st = screen === "messages" ? msg : brief, n = Math.sign(e.deltaY) * Math.max(1, Math.round(Math.abs(e.deltaY) / 120)) * 3;
    st.scroll = Math.max(0, Math.min(st.range, st.scroll + n));
  }, { capture: true, passive: false });

  return { open, close, isOpen, draw, rightClick, questWindow, markRead: (m) => msg.read.add(key(m)), objectives, textBox, brief,
           refresh: () => { if (screen === "goals") open("goals"); } };
})();
window.Lists = Lists;
