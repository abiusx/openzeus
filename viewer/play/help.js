// The help window (screen 5): a Zeus_MM.eng record drawn as help_page_draw 0x004F2D80 does for plain pages
// (layout != 2), with links, the Back history, the scrollbar 0x005A0A70 and the mouse wheel. Data:
// data/play/help.json (tools/play_help.py). Rules, positions and evidence: docs/play/help.md.
// Help.open(record) from the help buttons (info window, advisors, world map), right clicks on panel widgets
// (ui.js) and the Help menu; right click or the close button returns to the screen below.
"use strict";

const Help = (() => {
  let D = null, loading = false, cur = null;      // cur = {rec, hist: [[rec, scroll]], scroll, drag, m}
  let boxes = [];
  const BODY = "SPR_FONTS_11C2", LINK = "SPR_FONTS_11C4", UP = 332, DOWN = 336, BALL = 230, BACK = 252, CLOSE = 537;
  const PIC0 = 202;                               // Zeus_Unloaded SPR_PICS: picture n = image 202 + n - 1

  async function load() {
    if (D || loading) return;
    loading = true;
    try { D = await getJSON("/data/play/help.json"); } catch (e) { console.warn("help.json", e); }
    loading = false;
  }

  const pic = (n) => sprite("Zeus_Unloaded", PIC0 + n - 1);
  const ox = () => Math.trunc((UIX.W - 640) / 2), oy = () => Math.trunc((UIX.H - 480) / 2);

  // message_window_open 0x004F2600(r, e, 0): history cleared, scroll 0. rec: a number, or a function of the data
  // (help.json loads on the first use)
  // keep = e: 1 leaves the screen below as drawn (advisors, world map); 0 repaints the city under it, so the info
  // window is not shown while the help is up (help_page_draw: 0x0051CAB0 unless 0xEF8C68), and comes back on close
  async function open(rec, keep = 0) {
    if (!D) await load();
    if (!D) return;
    if (typeof rec === "function") rec = rec();
    if (rec == null || rec < 0 || !D.records[rec]) rec = 1;
    cur = { rec, hist: [], scroll: 0, m: null, keep };
    if (window.FM) FM.open = false;
  }
  function close() { cur = null; boxes = []; }
  function isOpen() { return !!cur; }
  function hidesInfo() { return !!cur && !cur.keep; }

  // which record a building's / the land window's help button opens (0x00580400: 0 -> 1 Table of Contents)
  function forBuilding(b) {
    if (!D || !b) return 1;
    const z = (Build.cat[b.key] || {}).zeus_id;
    if (z === 0x7D) return D.hero_hall[b.level] || 1;
    return D.by_type[String(z)] || 1;
  }
  function forLand(I) {
    if (!D) return 1;
    const k = I.land, byKind = D.land[String(k)];
    if (k === 0x0C || k === 0x18) return byKind;          // park, wall: before the figure check (FUN_005731D0)
    const f = I.data && I.data[I.sel];
    if (I.ids && I.ids.length && f && f.type != null) {
      if (f.role === "deer") return D.deer;                 // boar type 51 with a resource: 151 Deer
      return D.figures[String(f.type)] || D.figure_default;
    }
    return byKind != null ? byKind : D.land_default;
  }

  function measure(c) {                            // the record's geometry and the measure pass (once per page)
    const r = D.records[c.rec];
    const [layout, , rx, ry, cols, rows, pn, px, py, tx, ty, cx, cy, title, caption, body] = r;
    const X = ox() + rx, Y = oy() + ry, W = 16 * cols, H = 16 * rows, topPad = layout === 0 ? 48 : 32;
    let T = Y + (tx ? 32 : 48);
    if (pn) { const sp = pic(pn); if (sp) T = Math.max(T, Y + py + sp.h + 8); }
    let capH = 0;
    if (cx) {                                       // paragraph_draw: at least one line (16 px) even when empty
      capH = 16 * Math.max(1, ZText.wrap("SPR_FONTS_11C", caption, W - cx - 16).length);
      if (T < Y + cy + capH) T = Y + cy + capH + 4;
    }
    const R = Math.trunc(H / 16) - Math.trunc((T - Y + topPad) / 16) - 1, V = R - 1;
    const picRows = (n) => { const sp = pic(n); return sp ? sp.h >> 4 : 0; };
    const N = ZText.helpLayout(BODY, body, 16 * (cols - 4) - 16, picRows).count;
    const range = N > V ? N - V : 0, C = range ? cols - 4 : cols - 2;
    const lay = ZText.helpLayout(BODY, body, 16 * C - 16, picRows);
    c.m = { r, layout, X, Y, W, H, T, R, V, C, range, lay, pn, px, py, tx, ty, cx, cy, title, caption };
    c.scroll = Math.max(0, Math.min(c.scroll, range));
  }

  function go(rec) {                               // link 0x004F5200: push (record, scroll), at most 199 deep
    if (!D.records[rec]) return;
    if (cur.hist.length < 199) cur.hist.push([cur.rec, cur.scroll]);
    cur.rec = rec; cur.scroll = 0; cur.m = null;
  }
  function back() {                                // 0x004F5180
    if (!cur.hist.length) return;
    const [r, s] = cur.hist.pop();
    cur.rec = r; cur.scroll = s; cur.m = null;
  }
  function scrollBy(n) { if (cur && cur.m) cur.scroll = Math.max(0, Math.min(cur.m.range, cur.scroll + n)); }

  function draw() {
    if (!cur || !D || !window.ZText) return;
    if (window.Balloon) Balloon.none();             // screen 5 has no balloons
    if (!cur.m) measure(cur);
    const m = cur.m, { X, Y, W, H, T, R, V, C } = m;
    uiFrame("titled", X, Y, W / 16, H / 16);
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);           // screen 5: nothing below takes clicks
    if (m.tx) uiText(m.title, X + m.tx, Y + m.ty, "SPR_FONTS_22C");
    else uiText(m.title, X + 8, Y + 0x0E, "SPR_FONTS_22C", { center: W + 0x14 });
    if (m.pn) { const sp = pic(m.pn); if (sp) uiPut(sp, X + m.px, Y + m.py); }
    if (m.cx) uiText(m.caption, X + m.cx, Y + m.cy, "SPR_FONTS_11C", { width: W - m.cx - 16 });
    uiFrame("plain", X + 16, T, C, R);
    const clip = [X + 16 + 3, T + 3, X + 16 + 16 * C - 3, T + 16 * R - 3];   // the inner frame inset 3 px (0xF139B0..BC)
    uiFlushText();
    // body: lines [scroll, scroll + V) at (X+24, T+6), 16 px apart; pictures centred in the box, drawn shifted up
    // when their line is scrolled off, not at all below the visible lines
    boxes = [];
    const push = (sp, px, py) => uiClipPush((t, qx, qy) => UIX.batch.push(t, qx, qy), sp, px, py, clip);
    const lines = m.lay.lines, x0 = X + 24, y0 = T + 6;
    for (let k = 0; k < lines.length && k < cur.scroll + V; k++) {
      const ln = lines[k], y = y0 + (k - cur.scroll) * 16;
      if (k >= cur.scroll) ZText.helpLine(push, BODY, LINK, ln.text, x0 + ln.indent, y, boxes);
      if (ln.pic) { const sp = pic(ln.pic); if (sp) push(sp, x0 + Math.trunc((16 * C - sp.w - 4) / 2) - 4, y); }
    }
    if (m.range) scrollbar(X + 16 + 16 * C - 1, T, 16 * R);
    // links act on the left press: the first box holding the mouse (x0-2..x1+2, y-1..y+13 inclusive)
    for (const [a, b, c, d, rec] of boxes.slice().reverse()) UIX.hits.push([a, b, c - a + 1, d - b + 1, () => go(rec), ""]);
    if (m.layout === 0 && cur.hist.length) {       // Back (0x005EF7F8) at (X+16, Y+H-36) 31x20, label 12:0
      const bx = X + 16, by = Y + H - 36, hov = uiHover(bx, by, 31, 20);
      uiPut(sprite("Zeus_Interface", BACK + (hov ? 1 : 0)), bx, by);
      uiText(D.back, X + 52, Y + H - 31, "SPR_FONTS_11C");
      UIX.hits.push([bx, by, 31, 20, back, "Back"]);
    }
    const cx = X + W - 38, cy = Y + H - 36;          // close (0x005EF820) 24x24
    uiPut(sprite("Zeus_Interface", CLOSE + (uiHover(cx, cy, 24, 24) ? 1 : 0)), cx, cy);
    UIX.hits.push([cx, cy, 24, 24, close, "Close"]);
  }

  // scrollbar 0x005A0A70 / 0x005A0C00: arrows 39x26 at the top and bottom (kind 6: step while held), the track a
  // plain frame 2 cells wide, the ball at (x+5, top + (trackH-24) * (pos*100/range) / 100); drag in the track
  // st = {scroll, range, drag, armed} (shared with the Messages list and the Goals briefing: lists.js)
  function scrollbar(x, y, h, st = null) {
    const c = st || cur, range = st ? st.range : cur.m.range;
    const by = (d) => { c.scroll = Math.max(0, Math.min(range, c.scroll + d)); };
    const trackH = 16 * Math.trunc((h - 52) / 16), top = y + Math.trunc((h - trackH) / 2);
    const now = performance.now();
    const arrow = (img, ay, d) => {
      const hov = uiHover(x, ay, 39, 26), held = hov && UIX.down;
      uiPut(sprite("Zeus_Interface", img + (held ? 2 : hov ? 1 : 0)), x, ay);
      if (held && now - (c.lastStep || 0) > 29) { c.lastStep = now; if (c.armed) by(d); }
      UIX.hits.push([x, ay, 39, 26, () => { c.armed = true; c.lastStep = now; by(d); }, ""]);
    };
    if (!UIX.down) c.armed = false;
    arrow(UP, y, -1);
    arrow(DOWN, y + h - 26, 1);
    uiFrame("plain", x + 2, top, 2, trackH / 16);
    const [, my] = UIX.mouse;
    if (UIX.down && c.drag) {
      const off = Math.max(0, Math.min(my - top, trackH - 24));
      c.scroll = Math.trunc(range * Math.trunc(off * 100 / (trackH - 24)) / 100);
    } else c.drag = false;
    const off = Math.trunc((trackH - 24) * Math.trunc(c.scroll * 100 / range) / 100);
    uiPut(sprite("Zeus_Interface", BALL), x + 5, top + off);
    UIX.hits.push([x, top, 39, trackH, () => { c.drag = true; }, ""]);
  }

  // mouse wheel (MSWHEEL_ROLLMSG): pos -= (delta / 120) * 3 lines
  window.addEventListener("wheel", e => {
    if (!cur) return;
    e.preventDefault(); e.stopPropagation();
    scrollBy(Math.sign(e.deltaY) * Math.max(1, Math.round(Math.abs(e.deltaY) / 120)) * 3);
  }, { capture: true, passive: false });

  // a text record not in Zeus_MM.eng (our messages): drawn as a plain help page (record slot 1000)
  async function openText(title, body) {
    if (!D) await load();
    if (!D) return;
    D.records[1000] = [0, 0, 0, 24, 30, 28, 0, 0, 0, 0, 0, 0, 0, title, "", body];
    open(1000);
  }
  return { open, openText, close, isOpen, hidesInfo, draw, scrollbar, ensure: load, forBuilding, forLand, data: () => D, go, back, state: () => cur, pic,
           rec: (name) => (D ? D[name] : 1), pageHelp: (p) => (D ? D.page_help[p] : 1) };
})();
window.Help = Help;
