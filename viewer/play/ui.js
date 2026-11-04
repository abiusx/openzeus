// The original's in-game UI (docs/play/ui.md, data/play/ui.json): top bar, control panel, build submenus,
// minimap, info window; native pixel size at any window size (panelX: uiPanelX), optional integer scale.
// Screen-space layer drawn after the map. Text goes through window.ZText (viewer/play/text.js) when loaded.
// Presentation only: actions are the same commands/tools the rest of play mode uses.
"use strict";

const UIX = {
  D: null,              // ui.json
  batch: null,
  scale: 1,
  W: 0, H: 0, panelX: 0,
  mouse: [-1, -1], down: false,
  tab: 0,               // 0 overview (pages), 1 radar (the exe starts at 0: 0x00510ED0)
  godMap: true,         // ours, not the exe: the minimap over the god art at the panel's bottom (user request)
  page: 0,
  overlay: {},          // page -> overlay id
  submenu: null,        // open submenu id
  hoverName: "",        // hovered button name (name bar)
  info: null,           // open info window {b, x, y, rows}
  hits: [],             // this frame's hit rects [x, y, w, h, onClick, name]
  mm: null,             // minimap {sheet, canvas, key}
  colors: {},           // sprite -> first-two-pixel colours (minimap)
  textQueue: [],        // [str, x, y, font, opts] for the text layer
  zeusIds: {},          // tool id (zeus building type) -> our key
};

function uiInit(R, D) {
  UIX.D = D;
  UIX.batch = R.batch();
  for (const [k, v] of Object.entries(Build.cat || {})) if (v.zeus_id != null) UIX.zeusIds[v.zeus_id] = k;
  const c = document.createElement("canvas");             // 1 px colours for lines (minimap view rect)
  c.width = 6; c.height = 1;
  const x = c.getContext("2d");
  x.fillStyle = "#f00000"; x.fillRect(0, 0, 1, 1);                 // 0xF800 as the exe shows it (15-bit: 240,0,0; seen)
  x.fillStyle = "#ffffff"; x.fillRect(1, 0, 1, 1);
  x.fillStyle = "#000000"; x.fillRect(2, 0, 1, 1);
  x.fillStyle = "#f00000"; x.fillRect(3, 0, 1, 1);                 // 0xF800 (the population graph's bars): 240,0,0 seen
  x.fillStyle = "rgb(0,33,33)"; x.fillRect(4, 0, 1, 1);           // tooltip outline 0x0084 (555), seen (0,33,33)
  x.fillStyle = "rgb(16,107,148)"; x.fillRect(5, 0, 1, 1);        // tooltip fill 0x09B2 (555), seen (16,107,148)
  const sh = R.addSheet(c);
  UIX.red = { sheet: sh, x: 0, y: 0, w: 1, h: 1 };
  UIX.black = { sheet: sh, x: 2, y: 0, w: 1, h: 1 };              // 1-px rules (0x00509700, colour 0)
  UIX.white = { sheet: sh, x: 1, y: 0, w: 1, h: 1 };              // 0xFFFF (the text cursor, FUN_0059FD60)
  UIX.red565 = { sheet: sh, x: 3, y: 0, w: 1, h: 1 };
  UIX.tipEdge = { sheet: sh, x: 4, y: 0, w: 1, h: 1 };
  UIX.tipFill = { sheet: sh, x: 5, y: 0, w: 1, h: 1 };
  const mc = document.createElement("canvas");
  mc.width = 2 * (N + 3); mc.height = 2 * N + 1;                  // the exe's grid: 0xE7 cells x 0x1C9 rows (0x00449FF0)
  UIX.mm = { canvas: mc, ctx: mc.getContext("2d"), sheet: R.addEmptySheet(512, 512), key: "", box: null };
}

const uiRef = r => r && sprite(r.file, r.index);
const uiStateRef = (w, st) => (w.states && w.states[st]) || w.sprite;

// --- layout ----------------------------------------------------------------------------------------
// interface size (Options): pct of the original's pixel size; "sharp" rounds it to a whole number of
// screen pixels per interface pixel (at a browser zoom like 125 %, 100 % would put each 1-px line on
// 1.25 screen pixels: smeared text and frame lines, bugs.md 47/55)
UIX.size = { pct: 100, sharp: false };                // default: the look before the option existed
const UI_MIN_W = 244;                             // one 60-px view column + the 186-px panel - 2 (uiPanelX's minimum)
// Never larger than the scale that leaves the window UI_MIN_W interface pixels wide: the panel always fits (ours,
// bugs.md 267: 200 % in a 400-px-wide window would put it past the edge).
function uiScaleFor(pct, sharp) {
  const dpr = window.devicePixelRatio || 1, fit = innerWidth / UI_MIN_W;
  let s = Math.max(0.1, Math.min(2, pct / 100, fit));
  if (sharp) { s = Math.max(1, Math.round(s * dpr)) / dpr; while (s > fit && s * dpr > 1) s = (Math.round(s * dpr) - 1) / dpr; }
  return s;
}
function uiSetSize(pct, sharp) {
  UIX.size = { pct, sharp };
  UIX.scale = uiScaleFor(pct, sharp);
  uiLayout();
}

// ours: the height (interface px) of our speed bar at the bottom of the view while it is open (folded: a small tab);
// windows the exe puts on the view's bottom edge sit above it (info windows, the message window: bugs.md 390)
function uiBarH() {
  const bar = document.getElementById("bar");
  const open = bar && getComputedStyle(bar).display !== "none" && !document.body.classList.contains("barc");
  return open ? Math.ceil(bar.offsetHeight / UIX.scale) : 0;
}

function uiLayout() {
  UIX.scale = uiScaleFor(UIX.size.pct, UIX.size.sharp);   // also when the browser zoom (dpr) changes
  UIX.W = Math.floor(innerWidth / UIX.scale);
  UIX.H = Math.floor(innerHeight / UIX.scale);
  UIX.panelX = uiPanelX(UIX.W);
}

// panel x = the city view's right edge: map_view_set_size 0x00449E50 makes it 60 * cols - 2 (58-px tiles + 2), cols by
// screen width (view_panel_unfolded 0x0051CC00: 640 -> 8, 800 -> 10, 1024 -> 14; control_panel_position 0x0058E280:
// 478 / 598 / 838). Ours, other widths: as many 60-px columns as leave room for the 186-px panel (arm64's "mode 3"
// widths 184 + 60n give the same); the rest right of the panel takes the 800x600 edge strip (bugs.md 216).
// Ours at 640 wide: the exe's 8 columns (478) would put the panel's right edge at 664, 24 px past the screen (the
// 640 mode is not offered by our renderer as a fixed mode); the panel must stay inside the window (bugs.md 267),
// so 640 takes the same rule as every other width (7 columns, 418).
function uiPanelX(W) {
  const cols = Math.max(1, Math.floor((W - 184) / 60));
  return 60 * cols - 2;
}

function inUI(sx, sy) {                           // screen px (CSS) over the UI? (the map must not get it)
  const x = sx / UIX.scale, y = sy / UIX.scale;
  if (!UIX.D) return false;
  if (window.WorldMap && WorldMap.isOpen()) return true;
  if (window.Advisors && Advisors.isOpen()) return true;
  if (x >= UIX.panelX || y < 30) return true;
  return UIX.hits.some(h => x >= h[0] && y >= h[1] && x < h[0] + h[2] && y < h[1] + h[3]);
}

// --- drawing primitives ----------------------------------------------------------------------------
// at a fractional device scale (200 % x dpr 1.25 = 2.5) a piece's top or left edge can fall exactly on a
// pixel centre; the rasterizer may then leave that pixel to neither the piece nor the background under it,
// whose hole (transparent: the map shows through) starts at the same row (bugs.md 79). A 1/32 device pixel
// shift up-left gives every such pixel to the piece that starts there (1/1000 was lost to the rasterizer's
// sub-pixel snapping).
function uiPut(sp, x, y, alpha, dw, dh) {
  if (!sp) return;
  const e = 1 / 32 / (UIX.scale * (window.devicePixelRatio || 1));
  UIX.batch.push(sp, x - e, y - e, alpha == null ? 1 : alpha, dw, dh);
}

// uiPut cut to clip [x0, y0, x1, y1] (UI px): the world map's layer stays in its viewport (bugs.md 180). The
// text layer is drawn after every sprite, so text takes the same rect as opts.clip (uiText; see uiDraw).
function uiClipPush(push, sp, x, y, clip, dw, dh) {   // push(sprite, x, y, w, h); dw/dh: drawn size (stretch)
  if (!sp) return;
  const [x0, y0, x1, y1] = clip, W = dw || sp.w, H = dh || sp.h, fx = W / sp.w, fy = H / sp.h;
  const l = Math.max(0, x0 - x), t = Math.max(0, y0 - y), r = Math.min(W, x1 - x), b = Math.min(H, y1 - y);
  if (r <= l || b <= t) return;
  if (l === 0 && t === 0 && r === W && b === H) { push(sp, x, y, W, H); return; }
  if (sp.flip) return;                            // (no flipped sprites in the UI)
  push(subSprite(sp, l / fx, t / fy, (r - l) / fx, (b - t) / fy), x + l, y + t, r - l, b - t);
}
function uiPutClip(sp, x, y, clip, dw, dh) { uiClipPush((s, px, py, w, h) => uiPut(s, px, py, 1, w, h), sp, x, y, clip, dw, dh); }

// the full-screen picture behind a campaign / new-game screen (backdrop_jpeg_load via FUN_00505310, drawn by
// fullscreen_background_b 0x00422270: the 1024 x 768 picture centred on the screen; ours: black around it on a
// larger window). key: viewer/play/atlas/backdrops/KEY.jpg (tools/play_backdrops.py; docs/play/campaign.md
// "Backdrops"). One sheet for all of them, its texture replaced when the picture changes; until the file has
// loaded (or when it is missing) only the black.
const BACKDROP = { sheet: -1, shown: "", imgs: {} };
function uiBackdrop(key) {
  uiPut(UIX.black, 0, 0, 1, UIX.W, UIX.H);
  const B = BACKDROP;
  if (B.imgs[key] === undefined) {
    B.imgs[key] = null;
    const img = new Image();
    img.onload = () => { B.imgs[key] = img; };
    img.src = `play/atlas/backdrops/${key}.jpg`;
  }
  const img = B.imgs[key];
  if (!img || typeof R === "undefined") return;
  if (B.sheet < 0) B.sheet = R.addSheet(img, { what: "screen backdrop" });
  else if (B.shown !== key) R.setSheet(B.sheet, img);
  B.shown = key;
  uiPut({ sheet: B.sheet, x: 0, y: 0, w: img.width, h: img.height, ax: 0, ay: 0 },
        Math.trunc((UIX.W - img.width) / 2), Math.trunc((UIX.H - img.height) / 2));
}

function uiHover(x, y, w, h) {
  const [mx, my] = UIX.mouse;
  return mx >= x && my >= y && mx < x + w && my < y + h;
}

// a draw-table widget: rect relative to (ox, oy); state images normal/hover/selected/disabled
function uiWidget(w, ox, oy, { selected = false, disabled = false, onClick = null, name = "", hover = false } = {}) {
  const [rx, ry, rw, rh] = w.rect;
  const x = ox + rx, y = oy + ry, hov = !disabled && uiHover(x, y, rw, rh);
  const st = disabled ? "disabled" : selected ? "selected" : hov || hover ? "hover" : "normal";
  uiPut(uiRef(uiStateRef(w, st)), x, y);
  if (hov && name) UIX.hoverName = name;
  UIX.hits.push([x, y, rw, rh, disabled ? null : onClick, name]);
}

function uiText(str, x, y, font, opts) { if (str != null && str !== "") UIX.textQueue.push([String(str), x, y, font, opts || {}]); }

// 16-px marble frames (titled: SPR_MARBLE1, plain: SPR_MARBLE2), tile rules from ui.json `frames`
// fill: middle tiles only, no border (the top-bar dropdowns, 0x0059F0F0)
function uiFrame(kind, x, y, cols, rows, fill = false) {
  const F = UIX.D.frames[kind], first = F.sprite_group.index;
  const T0 = kind === "titled" ? { tl: 0, tr: 11, bl: 132, br: 143, tm: 1, bm: 0x85, l: 0xC, r: 0x17, m: 0xD, sw: 10, pstep: 0xC, pwrap: 0x78 }
                               : { tl: 0, tr: 6, bl: 42, br: 48, tm: 1, bm: 0x2B, l: 7, r: 0xD, m: 8, sw: 5, pstep: 7, pwrap: 0x23 };
  let p = 0;
  for (let r = 0; r < rows; r++) {
    let s = 0;
    for (let c = 0; c < cols; c++) {
      const last = c === cols - 1, firstC = c === 0;
      let k;
      if (fill) k = T0.m + s + p;
      else if (r === 0) k = firstC ? T0.tl : last ? T0.tr : T0.tm + s;
      else if (r === rows - 1) k = firstC ? T0.bl : last ? T0.br : T0.bm + s;
      else k = firstC ? T0.l + p : last ? T0.r + p : T0.m + s + p;
      if (fill || (!firstC && !last)) s = (s + 1) % T0.sw;
      uiPut(sprite("Zeus_Interface", first + k), x + 16 * c, y + 16 * r);
    }
    if (fill || (r > 0 && r < rows - 1)) p = (p + T0.pstep) % T0.pwrap;
  }
}

// frame_bottom_row_draw 0x0059F4F0: one row of a plain frame's bottom tiles (bl, bm + s for s = 0..4 cycling, br)
function uiFrameBottom(x, y, cols) {
  const first = UIX.D.frames.plain.sprite_group.index;
  for (let c = 0, s = 0; c < cols; c++) {
    const k = c === 0 ? 42 : c === cols - 1 ? 48 : 0x2B + s;
    if (c > 0 && c < cols - 1) s = (s + 1) % 5;
    uiPut(sprite("Zeus_Interface", first + k), x + 16 * c, y);
  }
}

// --- top bar ---------------------------------------------------------------------------------------
function drawTopBar() {
  const D = UIX.D.top_bar, bg = uiRef(D.background.sprite);
  if (!bg) return;
  uiPut(bg, 0, 0);
  for (let x = bg.w; x < UIX.panelX; x += 300) {   // wider than 1024: repeat the bar's right part (not original art)
    const w = Math.min(300, UIX.panelX - x);
    uiPut(subSprite(bg, bg.w - 300, 0, w, bg.h), x, 0);
  }
  let tx = 10;
  for (const m of D.menus.titles) {
    const tw = window.ZText ? ZText.measure("SPR_FONTS_11C", m.text) : m.text.length * 8;
    // the open menu's title gets colour 0xFAC1, which a pre-coloured font ignores: drawn as the others (oracle
    // options-menus: options.bmp)
    uiText(m.text, tx, 6, "SPR_FONTS_11C");
    if (window.Balloon) Balloon.add(tx - 4, 0, tw + 8, 24, 50 + m.group);   // 68:51..53 (FUN_00432110)
    if (m.group === 1) fmTitle(tx, tw);
    else if ((m.group === 2 || m.group === 3) && window.Options) Options.title(m.group, tx, tw);   // options.js
    else UIX.hits.push([tx - 4, 0, tw + 8, 24, () => toast(`${m.text}: not in play mode yet (the dev bar has speed/sound)`), m.text]);
    tx += (window.ZText ? ZText.advance("SPR_FONTS_11C", m.text) + 6 : tw) + 10;   // 0x004310E0: pen after the text (+ a space) + 10
  }
  const f = P.f0;
  // funds / population x (0x0058EB20: 800 wide 0xDB / 0x15E, 1024 0x17D / 0x20D; ours: the 800 ones while the
  // panel sits left of 838)
  const fx = UIX.panelX < 838 ? 219 : 381, px = UIX.panelX < 838 ? 350 : 525;
  uiPut(uiRef(D.funds.icon), fx, D.funds.y);
  uiPut(uiRef(D.population.icon), px, D.population.y);
  // balloons (FUN_00405DF0: y 4..17): funds 68:61, population 68:62, date 68:63
  if (window.Balloon) { Balloon.add(fx, 4, 72, 14, 61); Balloon.add(px, 4, 82, 14, 62); Balloon.add(UIX.panelX - 110, 4, 124, 14, 63); }
  if (f) {
    uiText(" " + f.treasury, fx + 16, 5, "SPR_FONTS_11C");        // number_text_draw sign slot '@': one space first
    uiText(" " + f.population, px + 16, 5, "SPR_FONTS_11C");
    // month (text_ref_draw: pen = advance + a space), then year_text_draw 0x00508E50: BC = the number with its sign
    // slot (one space) and 20:0 after it; AD = 20:1 then the number (oracle mil-a c.bmp "May  1340  BC": 0 px)
    const d = String(f.date).split(" ");
    uiText(d.length === 3 ? (d[2] === "BC" ? `${d[0]}  ${d[1]}  ${d[2]}` : `${d[0]}  ${d[2]}  ${d[1]}`) : f.date, UIX.panelX - 110, 5, "SPR_FONTS_11C");
  }
}

// a dropdown's frame starts at y 24 under the bar's 6-px bottom edge, which stays on top (oracle options-menus:
// the frame shows from y 30, ends at 24 + 16 rows): the bar's rows 24..29 drawn again over [x, x+w)
function uiTopBarOver(x, w) {
  const bg = uiRef(UIX.D.top_bar.background.sprite);
  if (bg && x < bg.w) uiPut(subSprite(bg, x, 24, Math.min(w, bg.w - x), bg.h - 24), x, 24);
}

// right of the panel: SPR_EDGE_800x600 (16x600 at 784 when 800 wide: the panel's right border). Ours, wider gaps
// (uiPanelX): the strip's plain left 8 columns tiled from the panel to the strip at W-16, rows 594..599 repeated
// below 600, the last column stretched over the window's last fraction of an interface pixel
// The canvas is round(window x dpr) device px, which can be half a device px more than the window (1366 x 1.25 =
// 1707.5 -> 1708): the fills reach the canvas edge, not the window's (bugs.md 267: the map showed in that column).
function uiCanvasWH() {
  const c = document.getElementById("view"), k = UIX.scale * (window.devicePixelRatio || 1);
  return [Math.max(innerWidth / UIX.scale, c ? c.width / k : 0), Math.max(innerHeight / UIX.scale, c ? c.height / k : 0)];
}
function uiEdgeFill(x0) {
  const E = UIX.D.layout.resolutions["800x600"].edge, edge = uiRef(E.sprite), [Wf, Hf] = uiCanvasWH();
  if (edge && x0 < Wf) {
    const col = (sp, x) => { uiPut(sp, x, 0); for (let y = sp.h; y < Hf; y += 6) uiPut(subSprite(sp, 0, sp.h - 6, sp.w, 6), x, y); };
    const ex = Math.max(x0, UIX.W - edge.w);
    for (let x = x0; x < ex; x += 8) col(subSprite(edge, 0, 0, Math.min(8, ex - x), edge.h), x);
    col(edge, ex);
    if (Wf > ex + edge.w) col(subSprite(edge, edge.w - 1, 0, 1, edge.h), ex + edge.w);
  }
}

// --- control panel ---------------------------------------------------------------------------------
function drawPanel() {
  const C = UIX.D.control_panel, X = UIX.panelX;
  const bg = uiRef(C.background.sprite);
  if (!bg) return;
  uiPut(bg, X, 0);
  for (let y = bg.h; y < uiCanvasWH()[1]; y += 6) uiPut(subSprite(bg, 0, bg.h - 6, bg.w, 6), X, y);   // rows 762..767 repeated (arm64)
  uiEdgeFill(X + bg.w);
  const mil = window.MilPanel && MilPanel.mode();   // screens 0x48 / 0x20 (milpanel.js): the military command panel
  if (mil) MilPanel.draw(X);
  if (!mil) C.tabs.forEach((t, i) => uiWidget(t, X, 0, { selected: UIX.tab === i, onClick: () => { UIX.tab = i; }, name: t.tooltip && t.tooltip.text }));
  // with an advisor open the page buttons also switch advisor (FUN_00516D50: page -> 0x0063E488), and only
  // they and the lower buttons take clicks on the panel (input case 7: tables 0x0063DC40, 0x0063DF80)
  const adv = window.Advisors && Advisors.isOpen(), keep = () => { if (adv) UIX.hits[UIX.hits.length - 1].adv = true; };
  // a tutorial's build categories (0x00FEAE06[i], FUN_00516F50: a page that is off does not open; drawn disabled)
  // and world map button (0x00FE6A5A, panel_world_map_btn 0x00409110); frame.episode from sim/episode.py
  const tut = P.f0 && P.f0.episode && P.f0.episode.tutorial, pageOff = i => !!(tut && !tut.build_categories[i]);
  if (!mil) C.pages.forEach((w, i) => { uiWidget(w, X, 0, { selected: UIX.page === i && UIX.tab === 0, name: w.tooltip && w.tooltip.text,
                                             disabled: pageOff(i),
                                             onClick: () => { UIX.page = i; UIX.tab = 0; UIX.submenu = null; if (adv && Advisors.advisorOfPage(i)) Advisors.open(Advisors.advisorOfPage(i)); } }); keep(); });
  const tools = { build_road: () => selectTool({ line: "road" }), build_roadblock: () => selectTool({ key: "roadblock" }),
                  clear: () => selectTool({ clear: true }),
                  // undo (0x00405B80 -> 0x004A7000): the last build/clear action, within 500 ticks; disabled
                  // otherwise (panel_draw 0x00517BF0: 0x00DA236C && 0x00DA2374); the server checks again
                  undo: P.f0 && P.f0.undo ? () => sendCommands(["undo"], { sound: false }) : null };
  for (const w of mil ? [] : C.tools) {
    const act = tools[w.name];
    const sel = (w.name === "build_road" && Build.tool && Build.tool.line === "road") || (w.name === "clear" && Build.tool && Build.tool.clear)
      || (w.name === "build_roadblock" && Build.tool && Build.tool.key === "roadblock");
    uiWidget(w, X, 0, { disabled: !act, selected: sel, onClick: act, name: w.tooltip && w.tooltip.text });
  }
  // lower buttons: messages (0x00405B90 -> screen 0x11), goals (0x004215D0 -> 0x3B), world map; lists.js
  const LOWER_ACT = { world_map: window.WorldMap ? () => { if (window.Advisors) Advisors.close(); WorldMap.toggle(); } : null,
                      messages: window.Lists ? () => { if (window.Advisors) Advisors.close(); Lists.open("messages"); } : null,
                      goals: window.Lists ? () => { if (window.Advisors) Advisors.close(); Lists.open("goals"); } : null };
  for (const w of C.lower) { uiWidget(w, X, 0, { name: w.tooltip && w.tooltip.text,
    disabled: w.name === "world_map" && !!tut && !tut.world_map_button,
    onClick: LOWER_ACT[w.name] || (() => toast(`${w.tooltip ? w.tooltip.text : w.name}: not in play mode yet`)) }); keep(); }
  drawAlerts(C, X, keep);
  // right click on a panel widget opens its help (40-byte tables +0x14 handlers: 0x00516A00 page help, 0x00516A10
  // the table's arg2 record, 0x005169F0 the current page's; help.md "Which record opens")
  const RH = (w, rec) => { if (w && w.rect) UIX.rhelp.push([X + w.rect[0], w.rect[1], w.rect[2], w.rect[3], rec]); };
  C.pages.forEach((w, i) => RH(w, () => Help.pageHelp(i)));
  C.tabs.forEach(w => RH(w, () => Help.rec("control_panel")));
  C.tools.forEach(w => { if (w.name !== "undo") RH(w, () => Help.rec("control_panel")); });
  // alert buttons: only an active one takes the right click (FUN_004319C0 skips state 0)
  (C.alerts || []).forEach((w, i) => { if (uiAlert(i)) RH(w, () => Help.data().lower[i]); });
  const LOWER = { messages: "messages", goals: "goals", world_map: "world_map" };
  C.lower.forEach(w => { if (LOWER[w.name]) RH(w, () => Help.rec(LOWER[w.name])); });
  if (C.rotate) {                                 // rotate button (FUN_00517940 / draw FUN_00517A20, docs/play/rotation.md)
    // thirds of its width: left = 1 (PgDn, -2), middle = 0 (Home, north), right = 2 (PgUp, +2); image =
    // first + (view/2)*8 + third+1 hovered (+4 instead while pressed)
    const r = C.rotate, [rx, ry, rw, rh] = r.rect, hov = uiHover(X + rx, ry, rw, rh);
    if (window.Balloon) {                         // thirds: left 68:45, middle 68:44, right 68:46 (0x00781814)
      const t3 = Math.trunc(rw / 3);
      Balloon.add(X + rx, ry, t3, rh, 45); Balloon.add(X + rx + t3, ry, t3, rh, 44); Balloon.add(X + rx + 2 * t3, ry, rw - 2 * t3, rh, 46);
    }
    const third = () => { const u = UIX.mouse[0] - X - rx; return u < rw / 3 ? 1 : u < (2 * rw) / 3 ? 0 : 2; };
    uiPut(sprite(r.sprite.file, r.sprite.index + (VIEW >> 1) * 8 + (hov ? third() + 1 : 0)), X + rx, ry);
    UIX.hits.push([X + rx, ry, rw, rh, () => { const t = third(); rotateView(t === 2 ? 2 : t === 1 ? -2 : 0); },
                   "Rotate"]);
  }
  if (UIX.godMap) {                               // the god art's opening: x 12..179, y 605..759 (dark frame line at x 11,
    const gh = Math.min(155, UIX.H - 605);        // y 604 and y 760; read back at dpr 1.25: 166 wide left 178-179 showing)
    if (gh >= 20) drawMinimap(X + 12, 605, 168, gh);
  }
  const LOWER_TIP = { messages: 11, goals: 9, world_map: 17 };        // shown at once (SOME or ON)
  if (window.Balloon) for (const w of C.lower) if (LOWER_TIP[w.name]) Balloon.add(X + w.rect[0], w.rect[1], w.rect[2], w.rect[3], LOWER_TIP[w.name], true);
  if (!mil && window.MsgWin) MsgWin.drawStrip(X);   // the message strip (FUN_005170A0 -> FUN_00430D80)
  if (mil) return;
  if (UIX.tab === 1) {
    if (window.Balloon) Balloon.add(X + C.minimap.radar_tab[0], C.minimap.radar_tab[1], 128, 110, 36);   // FUN_00405D40
    return drawMinimap(X + C.minimap.radar_tab[0], C.minimap.radar_tab[1], 128, 110);
  }
  drawPage(C, X);
}

// --- alert slots (sim/alerts.py, docs/play/alerts.md) ------------------------------------------------
// The 4 "go to" buttons left of the messages button: entries 0..3 of the lower table 0x0063DF80 at (panelX + 10 /
// 44 / 78 / 112, 478), 33x33, on every page and on the military panel. FUN_00410230 sets their picture: an active
// slot the group 0x005D83CC[type] (ui.json alert_types: +1 hovered, +2 pressed), an empty one the first image of
// SPR_BTN_ALERTS_DISABLED (= the panel art under it) and no clicks. Balloon 68:(178 + type) at once (FUN_004F5F00,
// hover ids 10..13). A click (0x00405BA0 -> FUN_00410290) centres the view on the slot's next tile (FUN_0044A7D0)
// and the sim moves to the one after (`alert go K`); after the last one the slot clears once the pressed look is
// over (the widget's +0x19 = 20 polls, FUN_00431BC0). While the mouse rests on an active button the sim keeps it past
// 8 days (`alert hover K`, FUN_004102F0 reads the hover byte). The hover byte decays only while the panel takes the
// mouse (FUN_004319C0 runs for the panel): a button the mouse left for the map keeps its hovered look and its hold
// until the mouse comes back over the panel (oracle 1D-alerts r*_n: slot 3 still hovered, slot 0 kept past 8 days).
function uiAlert(k) {
  const fl = UIX.alertFlash;
  if (fl && fl.k === k) return fl.rec;
  const a = P.f0 && P.f0.alerts;
  return (a && a[k]) || null;
}

function alertCmd(cmd) {
  fetch("/cmd", { method: "POST", headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ cmds: [cmd], tick: Math.floor(P.t) }) }).catch(() => { });
}

function uiCenterOn(x, y) {                      // FUN_0044A7D0: the tile at the middle of the city view
  if (typeof cam === "undefined") return;
  cam.x = tileX(x, y) - (UIX.panelX * UIX.scale) / 2 / cam.zoom;
  cam.y = tileY(x, y) - innerHeight / 2 / cam.zoom;
}

function drawAlerts(C, X, keep) {
  const T = C.alert_types, E = C.alert_empty;
  if (!C.alerts || !T) return;
  const fl = UIX.alertFlash;
  if (fl && --fl.frames <= 0) UIX.alertFlash = null;
  const onPanel = UIX.mouse[0] >= X, prev = UIX.alertHover == null ? -1 : UIX.alertHover;
  let hovered = onPanel ? -1 : prev;
  C.alerts.forEach((w, k) => {
    const [rx, ry, rw, rh] = w.rect, x = X + rx, a = uiAlert(k);
    if (!a || !T[a[0]]) { if (hovered === k) hovered = -1; uiPut(sprite(E.file, E.index), x, ry); return; }
    const pressed = UIX.alertFlash && UIX.alertFlash.k === k;
    if (onPanel && uiHover(x, ry, rw, rh)) hovered = k;
    const hov = hovered === k;
    const s = T[a[0]].sprite;
    uiPut(sprite(s.file, s.index + (pressed ? 2 : hov ? 1 : 0)), x, ry);
    if (window.Balloon) Balloon.add(x, ry, rw, rh, T[a[0]].balloon.index, true);
    UIX.hits.push([x, ry, rw, rh, () => {
      const cur = uiAlert(k);
      if (!cur || (UIX.alertFlash && UIX.alertFlash.k === k)) return;
      const n = cur[1], tiles = cur[2] || [], at = tiles.length < 20 && n < tiles.length ? tiles[n] : null;
      if (at) uiCenterOn(at[0], at[1]);
      const last = tiles.length >= 20 || n + 1 >= tiles.length;
      UIX.alertFlash = { k, frames: 20, rec: [cur[0], last ? cur[1] : n + 1, tiles, cur[3]] };
      alertCmd(`alert go ${k}`);
    }, T[a[0]].balloon.text]);
    keep();
  });
  if (hovered !== prev) {
    UIX.alertHover = hovered;
    alertCmd(`alert hover ${hovered}`);
  }
}

function drawPage(C, X) {
  const pg = UIX.D.pages[UIX.page];
  uiText(pg.title.text, X + 50, 30, "SPR_FONTS_11C", { center: 130 });
  const ovs = (pg.overlays || []);
  ovs.forEach((o, k) => {
    const w = { rect: C.overlay_buttons.rects[k], states: C.overlay_buttons.states, sprite: C.overlay_buttons.sprite };
    UIX.rhelp.push([X + w.rect[0], w.rect[1], w.rect[2], w.rect[3], () => Help.pageHelp(UIX.page)]);   // 0x005169F0
    const cur = UIX.overlay[UIX.page] === o.id;
    uiWidget(w, X, 0, { selected: cur, name: o.text, onClick: () => { UIX.overlay[UIX.page] = cur ? 0 : o.id; } });
    uiText(o.text, X + w.rect[0], w.rect[1] + 8, "SPR_FONTS_9LTBK", { center: w.rect[2] });
  });
  const u = (11 - ovs.length) * 20, hh = u + 32 - (u & 15);
  uiFrame("plain", X + 50, 300 - hh, 8, Math.max(1, hh / 16));
  if (window.ZPages) ZPages.draw(UIX.page, X, ovs.length);      // the page's info box (pages.js)
  if (UIX.page === 10) {                          // Overview: the minimap lives on the page, under the bar
    if (window.Balloon) Balloon.add(X + C.minimap.overview_page[0], C.minimap.overview_page[1], 128, 110, 36);
    drawMinimap(X + C.minimap.overview_page[0], C.minimap.overview_page[1], 128, 110);
  }
  // magnifier (FUN_00517580): the page's advisor (0x0063E488; none on Aesthetics outside Poseidon); advisors.js.
  // Its bar text (FUN_00517210, hover id 200): 51:79 'See more information', 51:80 'Hide full report' while an
  // advisor is open (0x00FA0428). The panel's hover id is not updated while the advisor screen is up, so the bar keeps
  // what it showed when the screen opened: the magnifier's 51:80 (oracle lo-overview-quest ov.bmp, bug 259).
  // The magnifier shows its selected picture while the advisor is open (SPR_MAG_GLASS + 2: 1.000 in ov.bmp). Hover
  // texts at y 0x134 (magnifier, build buttons), else 0x136.
  const AT = (i) => (window.Advisors && Advisors.text(51, i)) || "";
  const advOpen = window.Advisors && Advisors.isOpen();
  if (C.advisor_button && window.Advisors && Advisors.has(UIX.page)) {
    const before = UIX.hoverName;
    uiWidget(C.advisor_button, X, 0, { name: AT(advOpen ? 80 : 79), selected: !!advOpen, onClick: () => {
      UIX.submenu = null; UIX.info = null;
      if (Advisors.openPage(UIX.page) !== false) UIX.frozenHover = { text: AT(80), y: 0x134 };
    } });
    if (UIX.hoverName !== before) UIX.hoverY = 0x134;
  }
  uiFrame("plain", X + 50, 302, 8, 1);             // FUN_00517210: window_frame_draw(x, 0x12E, 8, 1) and
  uiFrameBottom(X + 50, 304, 8);                  // frame_bottom_row_draw(x, 0x130, 8)
  if (C.advisor_button) UIX.rhelp.push([X + C.advisor_button.rect[0], C.advisor_button.rect[1], C.advisor_button.rect[2], C.advisor_button.rect[3], () => Help.rec("control_panel")]);
  for (const b of pg.build_buttons) {
    if (!b || !pageButtonShown(b)) continue;
    UIX.rhelp.push([X + b.rect[0], b.rect[1], b.rect[2], b.rect[3], () => Help.rec("control_panel")]);
    const st = b.states, open = UIX.submenu === b.submenu && b.submenu != null;
    const armed = b.submenu == null && Build.tool && Build.tool.key === UIX.zeusIds[b.tool];
    const [rx, ry, rw, rh] = b.rect, hov = uiHover(X + rx, ry, rw, rh);
    uiPut(sprite(b.sprite.file, open || armed ? st.selected : hov ? st.hover : st.normal), X + rx, ry);
    const key = UIX.zeusIds[b.tool], spec = key && Build.cat[key];
    if (hov) { UIX.hoverName = b.text + (spec && spec.cost ? `   ${spec.cost}` : ""); UIX.hoverY = 0x134; }
    UIX.hits.push([X + rx, ry, rw, rh, () => {
      if (b.submenu != null) UIX.submenu = UIX.submenu === b.submenu ? null : b.submenu;
      else if (key) { UIX.submenu = null; selectTool(LINE_TOOLS[key] ? { line: key } : { key }); }
    }, b.text]);
  }
  if (!advOpen) UIX.frozenHover = { text: UIX.hoverName, y: UIX.hoverY || 0x136 };
  const hv = advOpen ? UIX.frozenHover || { text: "" } : { text: UIX.hoverName, y: UIX.hoverY };
  uiText(hv.text, X + 50, hv.y || 0x136, "SPR_FONTS_9DKBU", { center: 130 });
}

// a page's build button is hidden when its slot is not available (FUN_00516D50: state 2 when DAT_00787178[slot] == 0,
// set by FUN_00402B80: Poseidon-only tools outside Poseidon, Monuments without a granted commemorative, the scenario's
// sanctuaries). Ours, by its effect: hidden when nothing behind the button can be built (bugs.md 323; the oracle's
// Aesthetics page in open play shows Beautification and Recreational Areas only).
function pageButtonShown(b) {
  if (b.submenu == null) { const k = UIX.zeusIds[b.tool]; return !k || buildable(k); }
  // Trade (0x1A -> submenu 0xB): FUN_00403D40(0xB) is true when one of its items passes FUN_005B9410 (trade allowed,
  // a partner without a post / dock that trades something): with every partner's post built the button is state 2,
  // hidden (FUN_00516D50; bugs.md 444). The items: /trade.json (sim/live.py trade_menu, the same test)
  if (b.submenu === 11) return (!episodeOff("trading_post") || !episodeOff("dock")) && tradeItems().length > 0;
  if (b.submenu === 22) return !!(S && S.monuments_available && S.monuments_available.length);
  if (b.submenu === 23) return !!(S && S.halls_available && S.halls_available.length);   // hero_hall_buildable 0x004FA620
  if (b.submenu === 21) return !!(P.f0 && P.f0.poseidon);      // the Poseidon pyramid's god statues (Poseidon only)
  const M = UIX.D.submenus[String(b.submenu)];
  return !M || !Array.isArray(M.items) || M.items.some(it => UIX.zeusIds[it.tool] && buildable(UIX.zeusIds[it.tool]));
}

// --- build submenu (screen 6) ----------------------------------------------------------------------
function drawSubmenu() {
  const M = UIX.submenu != null && UIX.D.submenus[String(UIX.submenu)];
  if (!M) return;
  const S0 = UIX.D.submenu, X = UIX.panelX, C = 15;            // C: widest name / 16 (English GOG = 15)
  // Trade (11): one item per partner city without a post/dock yet, from the server (live.py trade_menu,
  // exe FUN_005B9410 / trade_building_label); the others: the fixed tool lists of ui.json
  const items = Array.isArray(M.items)
    ? M.items.filter(it => UIX.zeusIds[it.tool] && buildable(UIX.zeusIds[it.tool])).map(it => ({ key: UIX.zeusIds[it.tool], text: it.text }))
    : UIX.submenu === 11 ? tradeItems()
    // Monuments (22): the granted commemoratives (g_commemorative_available[v] != 0) in the exe's order, name 198:v
    : UIX.submenu === 22 ? ((S && S.monuments_available) || []).map(([v, , name]) => ({ key: "commemorative_monument", text: name, variant: v }))
    // Hero's Hall (23): the halls hero_hall_buildable 0x004FA620 lists (table 0x005F42CC, names 185:8+h); the hero
    // goes with the build command (build heroes_hall X Y HERO, as a trade post's city)
    : UIX.submenu === 23 ? ((S && S.halls_available) || []).map(([h, name]) => ({ key: "heroes_hall", text: name, city: String(h) }))
    : [];
  const n = items.length, x0 = X - 117 - 16 * C, cells = C + 7;
  const Y0 = S0.Y0_by_count[n] != null ? S0.Y0_by_count[n] : 18;
  items.forEach((it, i) => {
    const y = Y0 + 0x6E + 24 * i, hov = uiHover(x0, y, 16 * cells, 20);
    const tiles = S0.bar_tiles.sprites[hov ? "hovered" : "normal"];
    for (let c = 0; c < cells; c++) uiPut(uiRef(tiles[c === 0 ? 0 : c === cells - 1 ? 2 : 1]), x0 + 16 * c, y);
    const key = it.key, spec = Build.cat[key] || {};
    uiText(it.text, X - (16 * C + 20) - 0x59, y + 3, hov ? "SPR_FONTS_11CB" : "SPR_FONTS_11C", { center: 176 });
    if (spec.cost) { uiPut(uiRef(S0.cost.icon), X - 0x52, y - 2); uiText(spec.cost, X - 0x42, y + 4, "SPR_FONTS_11C"); }
    UIX.hits.push([x0, y, 16 * cells, 20, () => {
      UIX.submenu = null;
      selectTool(LINE_TOOLS[key] ? { line: key } : it.city ? { key, city: it.city } : it.variant ? { key, variant: it.variant } : { key });
    }, it.text]);
  });
}

function tradeItems() {                           // refreshed once per state snapshot while the menu is open
  const t = UIX.trade;
  if ((!t || t.seq !== P.stateSeq) && !UIX.tradeBusy) {
    UIX.tradeBusy = true;
    const seq = P.stateSeq;
    getJSON("/trade.json").then(list => { UIX.trade = { seq, list }; }).catch(() => { })
      .finally(() => { UIX.tradeBusy = false; });
  }
  return t ? t.list : [];
}

// --- minimap ---------------------------------------------------------------------------------------
function firstPixels(sp) {                        // the first two pixels of a sprite (SPR_R_* colours)
  const k = sp.sheet + ":" + sp.x + ":" + sp.y;
  if (UIX.colors[k]) return UIX.colors[k];
  let col = [[0, 0, 0, 255], [0, 0, 0, 255]];
  for (const a of Object.values(atlas)) {         // find the sheet image this sprite came from
    const si = a.sheetIdx.indexOf(sp.sheet);
    if (si < 0 || !a.imgs) continue;
    const img = a.imgs[si], ly = sp.y - a.yOff[si];
    if (!img || ly < 0 || ly >= img.height) continue;   // stacked sheets: several atlases share one texture
    const c = document.createElement("canvas");
    c.width = 2; c.height = 1;
    const x = c.getContext("2d");
    x.drawImage(img, sp.x, ly, 2, 1, 0, 0, 2, 1);
    const d = x.getImageData(0, 0, 2, 1).data;
    col = [[d[0], d[1], d[2], 255], [d[4], d[5], d[6], 255]];
    break;
  }
  return (UIX.colors[k] = col);
}

const MM_GROUPS = ["SPR_R_GRASS", "SPR_R_SCRUB", "SPR_R_RIVER", "SPR_R_DEEPWATER", "SPR_R_WOODS", "SPR_R_ROCK", "SPR_R_COPPER_ROCK",
                   "SPR_R_SILVER_ROCK", "SPR_R_QUARRY", "SPR_R_DUNES", "SPR_R_MEADOW", "SPR_R_ELEVATION", "SPR_R_ROAD", "SPR_R_SPACE"];
function mmTerrain(f, r) {                        // decision order from ui.json minimap.terrain (0x00454980)
  if (f & 0x80000) return ["SPR_R_SPACE", 0];
  if ((f & 0x15374AE7) === 0) return ["SPR_R_GRASS", r & 6];
  if ((f & 0x15374AE7) === 0x80) return ["SPR_R_SCRUB", r & 1];
  if (f & 0x4) return (f & 0x4000000) ? ["SPR_R_RIVER", r & 3] : ["SPR_R_DEEPWATER", r & 3];
  if (f & 0x1) return ["SPR_R_WOODS", r & 3];
  if (f & 0x20000) return ["SPR_R_QUARRY", r & 1];
  if ((f & 0x300002) === 0x100002) return ["SPR_R_COPPER_ROCK", r & 3];
  if ((f & 0x300002) === 0x200002) return ["SPR_R_SILVER_ROCK", r & 3];
  if (f & 0x2) return ["SPR_R_ROCK", r & 3];
  if (f & 0x10000) return ["SPR_R_DUNES", r & 7];
  if (f & 0x200) return ["SPR_R_ELEVATION", r & 3];
  if (f & 0x40) return ["SPR_R_ROAD", 0];
  if (f & 0x800) return ["SPR_R_MEADOW", 0];
  return ["SPR_R_GRASS", r & 6];
}

// Projection (0x00449FF0, rotation 0): tile (x, y) -> cell column (0xE6 + x - y) / 2, row 1 + x + y; a row is
// 1 px, a cell 2 px, odd rows drawn 1 px left (0x00454980: x = left - (row & 1)). In pixels: px = x - y + N + 1,
// py = x + y + 1. Cells outside the play area (and the filler around the diamond) show SPR_R_SPACE image 0.
// In a turned view the same projection on the turned tile (viewXY: the grid of FUN_00449FF0 for that view).
const mmPx = (x, y) => { const [a, b] = viewXY(x, y); return [a - b + N + 1, a + b + 1]; };
function buildMinimap() {
  const OV = window.Overlays && Overlays.mode() ? Overlays : null;     // an overlay's colours (pages.md "Minimap")
  const key = (T && T.map_version) + ":" + (S && (S.seq || S.tick)) + ":" + VIEW + ":" + (OV ? OV.mode() : 0);
  if (!T || !S) return;
  if (key === UIX.mm.key) return minimapFigures(OV);
  UIX.mm.key = key;
  const W = UIX.mm.canvas.width, H = UIX.mm.canvas.height;
  const img = UIX.mm.ctx.createImageData(W, H), d = img.data;
  const setPx = (px, py, c) => { if (px < 0 || py < 0 || px >= W || py >= H) return; const o = (py * W + px) * 4; d[o] = c[0]; d[o + 1] = c[1]; d[o + 2] = c[2]; d[o + 3] = 255; };
  const tileCol = (g, v) => { const gg = atlas.Zeus_Interface && atlas.Zeus_Interface.groups[g]; return gg ? firstPixels(sprite("Zeus_Interface", gg[0] + Math.min(v, gg[1] - 1), true)) : [[0, 0, 0], [0, 0, 0]]; };
  const space = tileCol("SPR_R_SPACE", 0);
  for (let py = 0; py < H; py++) for (let px = 0; px < W; px++) setPx(px, py, space[(px + (py & 1)) & 1]);
  // the play-area box in pixels (0x00449FF0: DAT_007d3b84..7c columns, 7d3b80..78 rows); the window stays inside it
  let x0 = W, x1 = -1, y0 = H, y1 = -1;
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const i = y * N + x, f = T.flags[i];
    if (f & 0x80000) continue;                     // not in the play area: filler (space)
    const [g, v] = T.road[i] ? ["SPR_R_ROAD", 0] : mmTerrain(f, Scene.tileRand(x, y));
    const ob = OV && buildingAt(x, y), ap = OV && OV.minimapAppeal(i, ob && ob.kind !== "road" && ob.kind !== "animal" ? ob : null);
    const c = ap ? [ap[0], ap[1]] : tileCol(g, v), [px, py] = mmPx(x, y);
    setPx(px, py, c[0]); setPx(px + 1, py, c[1]);
    x0 = Math.min(x0, px); x1 = Math.max(x1, px + 1); y0 = Math.min(y0, py); y1 = Math.max(y1, py);
  }
  UIX.mm.box = x1 < 0 ? null : [x0, x1, y0, y1];
  const per = UIX.D.minimap.buildings && UIX.D.minimap.buildings.per_type;
  for (const b of S.buildings) {
    if (OV && (OV.mode() === 17 || b.kind === "road" || b.kind === "animal")) continue;   // appeal: coloured above
    const spec = Build.cat[b.key], t = spec && per && per[String(spec.zeus_id)];
    const sp = !OV && t && t.sprite ? sprite(t.sprite.file, t.sprite.index, true) : null;   // firstPixels: original pixels
    const c = OV ? OV.minimapColour(b) : sp && firstPixels(sp);
    if (!c) continue;
    const w = b.w || b.size || 1, h = b.h || b.size || 1;
    for (let j = 0; j < h; j++) for (let k = 0; k < w; k++) {
      const [px, py] = mmPx(b.x + k, b.y + j);
      setPx(px, py, c[0]); setPx(px + 1, py, c[1]);
    }
  }
  UIX.mm.base = img;
  UIX.mm.figKey = null;
  minimapFigures(OV);
}

// figure dots (0x00454980, per tile before its building/terrain): a tile whose figure list starts with a figure
// other than type 6 is drawn as 2 px of one colour when one of its figures passes the overlay's walker test +0x10
// (FUN_00454920; no overlay: every figure), or is a ship (types 0x14/0x19/0x39 black, enemy ships 0x3F/0x40), a
// soldier, an invader (0x28..0x2A) or a boar/wolf. Colour: enemies (invaders, enemy ships) the climate colour
// (S.climate = scenario byte 0x3D8), else black. The exe picks it per pixel format (DAT_00f9c0e4): RGB555 (the
// oracle's, used here) climate 0/1/2 -> 0x3C00 / 0x0C1F / 0x041F; RGB565 1/0/2 -> 0x7800 / 0x181F / 0x080F.
// When the tile's first figure (the list head: figures are appended, so the earliest arrival; ours: the first in
// the frame's walker list) is a god (0x43), a monster (0x44) or a hero (0x45), the 2 px are instead the first two
// pixels of SPR_R_GOD / SPR_R_MONSTER / SPR_R_HERO image 0 (0x2DC/0x2DD/0x2DE, FUN_00456BA0). Redrawn per frame.
const MM_SHIPS = new Set(["ship", "boat", "trireme"]);
const MM_ENEMY = [[123, 0, 0], [24, 0, 255], [8, 0, 255]];    // 0x3C00 / 0x0C1F / 0x041F (555, v<<3|v>>2)
const MM_PIC = { god: "SPR_R_GOD", monster: "SPR_R_MONSTER", hero: "SPR_R_HERO" };
function minimapFigures(OV) {
  const f0 = P.f0, k = (f0 ? f0.tick : -1) + ":" + UIX.mm.key;
  if (!UIX.mm.base || k === UIX.mm.figKey) return;
  UIX.mm.figKey = k;
  const base = UIX.mm.base, W = base.width, H = base.height;
  const img = new ImageData(new Uint8ClampedArray(base.data), W, H), d = img.data;
  const tiles = new Map();                        // tile -> {head role, colour, shown}
  if (f0) for (const w of f0.walkers) {
    const role = w[3];
    if (w[7] && w[7][0] === "hidden") continue;
    const i = w[2] * N + w[1];
    let t = tiles.get(i);
    if (!t) tiles.set(i, t = { head: role, c: [0, 0, 0], show: false, enemy: false });
    const enemy = typeof role === "string" && role.startsWith("enemy_");
    const always = enemy || MM_SHIPS.has(role) || ["rabble", "hoplite", "horseman", "boar", "wolf"].includes(role);
    if (!always && OV && OV.walkerHidden(role, w[0])) continue;
    t.show = true;
    if (enemy && !t.enemy) { t.enemy = true; t.c = MM_ENEMY[(S && S.climate) | 0] || MM_ENEMY[0]; }
  }
  const pic = (g) => { const gg = atlas.Zeus_Interface && atlas.Zeus_Interface.groups[g]; return gg ? firstPixels(sprite("Zeus_Interface", gg[0], true)) : null; };
  for (const [i, t] of tiles) {
    if (!t.show) continue;
    const pc = MM_PIC[t.head] && pic(MM_PIC[t.head]), cs = pc ? [pc[0], pc[1]] : [t.c, t.c];
    const [px, py] = mmPx(i % N, Math.floor(i / N));
    [px, px + 1].forEach((q, j) => { if (q >= 0 && py >= 0 && q < W && py < H) { const o = (py * W + q) * 4, c = cs[j]; d[o] = c[0]; d[o + 1] = c[1]; d[o + 2] = c[2]; d[o + 3] = 255; } });
  }
  UIX.mm.ctx.putImageData(img, 0, 0);
  R.subImage(UIX.mm.sheet, UIX.mm.canvas, 0, 0);
}

// window origin (0x004547C0): centred on the main view, clamped to the play-area box; when the box is
// smaller than the window, the grid's centre. Rows start even.
function mmOrigin(c, size, lo, hi, total) {
  if (hi - lo + 1 - size < 1) return Math.max(0, Math.floor((total - size) / 2));
  return Math.max(lo, Math.min(hi + 1 - size, Math.round(c - size / 2)));
}

function drawMinimap(x, y, w, h) {
  buildMinimap();
  const W = UIX.mm.canvas.width, H = UIX.mm.canvas.height, box = UIX.mm.box || [0, W - 1, 0, H - 1];
  // the main view's centre tile -> minimap pixel
  const cx = cam.x + (UIX.panelX * UIX.scale) / 2 / cam.zoom, cy = cam.y + innerHeight / 2 / cam.zoom;
  const tx = (cx / 30 + cy / 15) / 2, ty = (cy / 15 - cx / 30) / 2;   // turned tile (this view)
  const mx = tx - ty + N + 1 + 1, my = tx + ty + 1;      // +1: the tile's 2-px cell centre
  const ox = mmOrigin(mx, w, box[0], box[1], W) & ~1, oy = mmOrigin(my, h, box[2], box[3], H) & ~1;
  uiPut({ sheet: UIX.mm.sheet, x: ox, y: oy, w, h }, x, y);
  // view rectangle (0x00509870, colour 0xF800): the visible map area; a tile is 60 px = 2 minimap px wide and
  // one iso row (15 px) = 1 minimap px tall
  const vw = (UIX.panelX * UIX.scale) / cam.zoom / 30, vh = innerHeight / cam.zoom / 15;
  const rx = x + mx - ox - vw / 2, ry = y + my - oy - vh / 2;
  const clip = (a, lo, hi) => Math.max(lo, Math.min(hi, a));
  const x0 = clip(rx, x, x + w), x1 = clip(rx + vw, x, x + w), y0 = clip(ry, y, y + h), y1 = clip(ry + vh, y, y + h);
  uiPut(UIX.red, x0, y0, 1, Math.max(1, x1 - x0), 1); uiPut(UIX.red, x0, y1 - 1, 1, Math.max(1, x1 - x0), 1);
  uiPut(UIX.red, x0, y0, 1, 1, Math.max(1, y1 - y0)); uiPut(UIX.red, x1 - 1, y0, 1, 1, Math.max(1, y1 - y0));
  UIX.hits.push([x, y, w, h, () => {               // click: centre the main view there
    const px = UIX.mouse[0] - x + ox, py = UIX.mouse[1] - y + oy;
    const a = px - 1 - N - 1, s = py - 1;          // a = x - y, s = x + y
    const [tx2, ty2] = worldXY((a + s) / 2, (s - a) / 2);
    cam.x = tileX(tx2, ty2) - (UIX.panelX * UIX.scale) / 2 / cam.zoom;
    cam.y = tileY(tx2, ty2) - innerHeight / 2 / cam.zoom;
  }, "Map"]);
}

// --- info window (right click on a building) -------------------------------------------------------
function openInfo(b, mx, my) {
  // the original places it at x 188 and top/bottom by the click (docs/play/ui.md); ours: at the cursor,
  // clamped to the map area (left of the panel, below the top bar, above the dev bar).
  // Size and contents per building type: viewer/play/info.js (docs/play/info.md).
  if (window.ZInfo && ZInfo.ready()) b = ZInfo.target(b);
  UIX.info = { id: b.id, key: b.key, mx, my };
  infoPlace(b);
  if (audio) audio.click(b.key);
}

// --- walker window (right click on a walker, or on land with walkers around: bugs.md 80) -------------
// The exe's land window (FUN_005717D0 -> FUN_005731D0): the figures on the clicked tile, then on its 8
// neighbours in the order of 0x00642AF8, at most 7; the first (or the clicked one) is selected. Contents:
// info.js ZInfo.drawWalkers (docs/play/info.md "Walker window").
const AROUND = [[0, 0], [0, -1], [0, 1], [1, 0], [-1, 0], [-1, -1], [1, -1], [-1, 1], [1, 1]];
function openWalkers(tx, ty, sel, mx, my) {
  const ws = (P.f0 && P.f0.walkers) || [], ids = [];
  for (const [dx, dy] of AROUND) for (const w of ws)
    if (w[1] === tx + dx && w[2] === ty + dy && ids.length < 7 && !(w[7] && (w[7][0] === "hidden" || w[7][0] === "arrow"))) ids.push(w[0]);   // missiles (types 45, 52) are not listed
  if (sel != null && !ids.includes(sel)) { ids.unshift(sel); ids.length = Math.min(ids.length, 7); }
  const look = {};                                // each walker's picture now (the row's boxes)
  for (const h of Scene.walkerHits()) if (ids.includes(h[0]) && !look[h[0]]) look[h[0]] = [h[8], h[9]];
  // the land window (FUN_005731D0): its kind from the tile's terrain (sim/live.py land_kind); with no walkers
  // it opens only once the server names the land (none on a building's own tile)
  const I = { walker: true, ids, sel: Math.max(0, ids.indexOf(sel)), data: null, mx, my, look, land: null };
  if (ids.length) { UIX.info = I; infoPlace(null); }
  getJSON(`/land.json?x=${tx}&y=${ty}`).then(d => {
    if (d.kind == null) return;
    I.land = d.kind;
    I.ruin = d.ruin;
    if (!ids.length && !UIX.info) { UIX.info = I; infoPlace(null); }
  }).catch(() => { });
  if (ids.length) getJSON(`/walker_info.json?ids=${ids.join(",")}`).then(d => {
    if (!UIX.info || UIX.info.ids !== ids) return;
    UIX.info.data = d;
    if (audio) audio.walkerVoice(d.find(q => q.id === ids[I.sel]));     // FUN_005717D0 -> FUN_005ABD00
  }).catch(() => { });
  return true;
}

function infoPlace(b) {                           // size by type (it can change: storage rows), then clamp
  const I = UIX.info, sz = b && b.key === "heroes_hall" && window.Heroes ? Heroes.hallSize()   // heroes.js
    : b && window.ZInfo && ZInfo.ready() && ZInfo.size(b);
  const rows = sz ? sz.rows : !b ? 22 : b.kind === "monument" ? 31 : (b.kind === "agora" || b.crop) ? 24 : 22;
  const cols = sz ? sz.cols : 29;
  I.closeX = (sz && sz.close_x) || 16 * cols - 36;      // 0x005724E0: table 0x005EF708's close x = cols*16 - 0x24
  if (I.rows === rows && I.cols === cols) return;
  const w = 16 * cols, h = 16 * rows;
  const bottom = UIX.H - uiBarH();
  I.x = Math.max(0, Math.min(Math.round(I.mx) + 12, UIX.panelX - w));
  I.y = Math.max(30, Math.min(Math.round(I.my) - 40, bottom - h));
  if (sz && sz.x != null) { I.x = sz.x; I.y = sz.y; }    // a fixed place for the type (0x00ffa17c / 0x00ffa178)
  I.rows = rows; I.cols = cols;
}

function drawInfo() {
  const I = UIX.info;
  if (!I) return;
  const b = !I.walker && S && S.buildings.find(q => q.id === I.id);
  if (!I.walker && !b) { UIX.info = null; return; }
  infoPlace(b);
  if (window.Balloon) Balloon.none();             // screen 9: only the window's own balloons
  const { x, y, rows, cols } = I;
  uiFrame("titled", x, y, cols, rows);
  UIX.hits.push([x, y, 16 * cols, 16 * rows, null, ""]);
  if (I.walker) { if (window.ZInfo) ZInfo.drawWalkers(I, x, y, cols, rows); }
  else if (b.key === "heroes_hall" && window.Heroes && Heroes.drawHall(b, x, y, cols, rows)) { }   // heroes.js
  else if (!(window.ZInfo && ZInfo.draw(b, x, y, cols, rows))) {      // no info.js data: the bare facts
    const spec = Build.cat[b.key] || {};
    uiText(spec.name || b.key, x, y + 10, "SPR_FONTS_22C", { center: 16 * cols });
    if (b.reason) uiText(b.reason, x + 32, y + 56, "SPR_FONTS_11C", { width: 16 * cols - 64 });
  }
  const IWD = UIX.D.info_window, hb = IWD.help_button, cb = IWD.close_button;
  const hy = y + 16 * rows - 40, cy = y + 16 * rows - 37, cx = x + I.closeX;
  uiPut(sprite(hb.sprite.file, hb.sprite.index + (uiHover(x + 14, hy, 27, 27) ? 1 : 0)), x + 14, hy);
  uiPut(sprite(cb.sprite.file, cb.sprite.index + (uiHover(cx, cy, 24, 24) ? 1 : 0)), cx, cy);
  UIX.hits.push([cx, cy, 24, 24, () => { UIX.info = null; }, "Close"]);
  if (window.Balloon) { Balloon.add(x + 14, hy, 27, 27, 1); Balloon.add(cx, cy, 24, 24, 2); }   // 68:1 / 68:2 (ids 10/11)
  // help (0x00580400): the building type's record (g_building_type_info +0x14), the land window's by land kind and
  // shown figure (FUN_005731D0); help.js
  UIX.hits.push([x + 14, hy, 27, 27, () => Help.open(() => (I.walker ? Help.forLand(I) : Help.forBuilding(b))), "Help"]);
}

// --- overlay tooltip (0x004F6A10 every frame -> view object +0x1C; box tooltip_draw 0x004F6E40; pages.md) ------
// with an overlay on and the mouse over the map (no widget under it, right button up): the text of the ground tile
// under the mouse; box w = 220 (text 190), 300 (270) for more than 2 lines, h = 16 lines + 10; outline (x, y, w+20,
// h), fill inside; x = mouse + 20 if mouse x < w + 20 else mouse - w - 20; y = mouse + 50, mouse - 72 from y 200
function drawOverlayTip() {
  UIX.tip = null;
  if (!window.Overlays || !Overlays.mode() || !window.ZText || UIX.rdown) return;
  if (window.Options && Options.balloon() === 0) return;              // balloon help OFF turns them off (0x004F6A10)
  const [mx, my] = UIX.mouse;
  if (mx >= UIX.panelX || my < 30 || UIX.hits.some(h => mx >= h[0] && my >= h[1] && mx < h[0] + h[2] && my < h[1] + h[3])) return;
  const t = screenTile(mx * UIX.scale, my * UIX.scale), text = t && Overlays.tooltipAt(t[0], t[1]);
  if (!text) return;
  let w = 220, n = ZText.panelLines("SPR_FONTS_9DKBU", text, w - 30).length;
  if (n > 2) { w = 300; n = ZText.panelLines("SPR_FONTS_9DKBU", text, w - 30).length; }
  const h = 16 * n + 10, x = mx < w + 20 ? mx + 20 : mx - w - 20, y = my >= 200 ? my - 72 : my + 50;
  uiPut(UIX.tipEdge, x, y, 1, w + 20, h);
  uiPut(UIX.tipFill, x + 1, y + 1, 1, w + 18, h - 2);
  UIX.tip = { text, x: x + 5, y: y + 7, w: w - 30 };
}

// --- frame -----------------------------------------------------------------------------------------
// the text queued so far goes into the sprite batch now: a window drawn after this call (a popup list, a dialog,
// the help window) covers it, as the exe draws a window over the screen's text
function uiFlushText() {
  if (window.ZText) for (const [s, x, y, font, o] of UIX.textQueue) {
    // the mask font (SPR_FONTS) with opts.color: every glyph pixel that RGB555 colour (gl.js alpha -(2 + colour);
    // the oracle's 555 surface drops bit 15: 0xF800 = red 30)
    const a = (tint) => (tint && o.color != null && !Array.isArray(o.color) ? -(2 + (o.color & 0x7FFF)) : 1);
    const push = o.clip ? (sp, px, py, _, tint) => uiClipPush((t, qx, qy, w, h) => UIX.batch.push(t, qx, qy, a(tint), w, h), sp, px, py, o.clip)
                        : (sp, px, py, _, tint) => UIX.batch.push(sp, px, py, a(tint));
    ZText.draw(push, font, s, x, y, o);
  }
  UIX.textQueue = [];
}

function uiDraw(R) {
  if (!UIX.D) return;
  uiLayout();
  if (!Object.keys(UIX.zeusIds).length) for (const [k, v] of Object.entries(Build.cat || {})) if (v.zeus_id != null) UIX.zeusIds[v.zeus_id] = k;
  UIX.hits = []; UIX.textQueue = []; UIX.hoverName = ""; UIX.hoverY = 0; UIX.tip = null; UIX.rhelp = []; UIX.cuts = [];
  UIX.batch.clear();
  if (window.Balloon) Balloon.begin();
  drawTopBar();
  if (window.WorldMap && WorldMap.isOpen()) {     // the world map replaces map and panel (world.js, its own balloons: group 44)
    if (window.Balloon) Balloon.none();
    WorldMap.draw(R);
    if (window.MilPanel && MilPanel.armyOpen()) { uiFlushText(); MilPanel.drawArmy(); }   // the army dialog (screen 0x21)
    // ours (user 11-04): a message window that popped up while the city runs under the map (world.js holdsPopups)
    if (window.MsgWin && MsgWin.isOpen()) { uiFlushText(); MsgWin.draw(); }
  }
  else if (window.MsgWin && MsgWin.isOpen() && MsgWin.modal()) {   // screen 5, layout 2 (msgwin.js): the panel over it (FUN_004F2880)
    MsgWin.draw(); uiFlushText();
    const n = UIX.hits.length;
    drawPanel(); UIX.hits.length = n; UIX.rhelp = [];
    if (window.Balloon) Balloon.none();
  }
  else if (window.Advisors && Advisors.isOpen()) {             // screen 7: the panel stays, the map is inert
    drawPanel();
    UIX.hits = UIX.hits.filter(h => h.adv);
    // screen 7 (FUN_004F6110): only the advisor's own targets (the panel's hover ids are not set there); the box
    // placement by advisor (balloon.js)
    if (window.Balloon) { Balloon.none(); Balloon.onAdvisor(Advisors.current); }
    Advisors.draw();
  }
  else {
    drawPanel();
    if (window.Campaign) Campaign.drawTopLeft(R);                  // top_left_texts_draw, after the panel
    drawSubmenu(); if (!(window.Help && Help.hidesInfo())) drawInfo(); if (!(window.Help && Help.isOpen())) drawOverlayTip();
    // ours (bugs.md 322): a message window that doesn't pause doesn't block either: city and panel stay live under it
    if (window.MsgWin && MsgWin.isOpen()) { uiFlushText(); MsgWin.draw(); }
  }
  if (window.Lists && !(window.MsgWin && MsgWin.isOpen())) Lists.draw();   // Messages list / Goals screens
  // the army dialog opened from a request message's Dispatch now (army_dialog_open from wm_sub_475AB0) or the
  // Overview: over the city screen as over the world map
  if (!(window.WorldMap && WorldMap.isOpen()) && window.MilPanel && MilPanel.armyOpen()) { uiFlushText(); MilPanel.drawArmy(); }
  if (window.Campaign) { uiFlushText(); Campaign.draw(); }          // campaign screens (campaign.js)
  fmDraw();
  if (window.Options) Options.draw();                               // Options / Help menus and dialogs
  if (window.NewGame && NewGame.isOpen()) { uiFlushText(); NewGame.draw(); }   // File > New adventure (newgame.js)
  if (window.Help && Help.isOpen()) { uiFlushText(); Help.draw(); }   // screen 5 over the screen it came from
  uiFlushText();
  if (UIX.tip && window.ZText) ZText.panel((sp, px, py) => UIX.batch.push(sp, px, py), "SPR_FONTS_9DKBU", UIX.tip.text, UIX.tip.x, UIX.tip.y, UIX.tip.w);
  if (window.Balloon) Balloon.draw();               // balloon help (balloon.js)
  // the batch in pieces where a map pass goes between (walker-window crops, play.js drawCrop: over the boxes,
  // under what is drawn after them)
  let at = 0;
  for (const c of UIX.cuts) {
    R.begin({ x: 0, y: 0, zoom: UIX.scale }, false);
    UIX.batch.draw(at, c.at);
    try { c.draw(); } catch (e) { console.error(e); }
    at = c.at;
  }
  R.begin({ x: 0, y: 0, zoom: UIX.scale }, false);
  UIX.batch.draw(at);
  uiRepeat(performance.now());
}

// held arrow buttons repeat (exe FUN_00431C80, the arrow-button lists: storage and trade limits 0x01607560 /
// 0x016073A0 / 0x01607480, tax and wage 0x0063DF10 / 0x0063DF48, labor priorities 0x006434D0, ...; docs/play/ui.md
// "Held buttons"): the press fires at once with counter 0; then on each UI tick (screen_input 0x00514C10: a tick
// when more than 29 ms passed since the last, DAT_00F9F9A0) while the button stays down over the same button, the
// counter goes up and fires when REPEAT[counter] (table 0x005F0028, counters 8..46), and on every tick from 48 on
// (held at 47). Off the button it waits (no count). Hits pushed with a 7th element `true` repeat.
const REPEAT = [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0,
                1, 0, 1, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0];
function uiRepeat(now) {
  const tick = now - (UIX.repT || 0) > 29;
  if (tick) UIX.repT = now;
  const r = UIX.rep;
  if (!r || !tick) return;
  if (!UIX.down) { UIX.rep = null; return; }
  const [mx, my] = UIX.mouse;
  let h = null;
  for (let i = UIX.hits.length - 1; i >= 0 && !h; i--) {
    const q = UIX.hits[i];
    if (mx >= q[0] && my >= q[1] && mx < q[0] + q[2] && my < q[1] + q[3]) h = q;
  }
  if (!h || !h[6] || !h[4] || h[5] !== r.name || h[0] !== r.x || h[1] !== r.y) return;
  if (++r.n >= 48) r.n = 47;
  else if (!REPEAT[r.n]) return;
  h[4]();
}
window.addEventListener("mouseup", e => { if (e.button === 0) { UIX.down = false; UIX.rep = null; } }, true);
window.addEventListener("mousedown", e => { if (e.button === 2) UIX.rdown = true; }, true);    // overlay tooltip: right button up
window.addEventListener("mouseup", e => { if (e.button === 2) UIX.rdown = false; }, true);
window.addEventListener("blur", () => { UIX.down = false; UIX.rep = null; });

// --- input (play.js calls these first; true = the UI took the event) -------------------------------
function uiMove(e) { UIX.mouse = [e.clientX / UIX.scale, e.clientY / UIX.scale]; return inUI(e.clientX, e.clientY); }

function uiDown(e) {
  if (!UIX.D) return false;
  const x = e.clientX / UIX.scale, y = e.clientY / UIX.scale;
  // a right click anywhere, the window included, closes an info window and does nothing else (exe:
  // info_window_click 0x005726E0 returns to the previous screen on the right button's release, flag
  // 0x00F2A6FC set by mouse_poll 0x0050B470; bugs.md 109)
  if (e.button === 2 && window.Help && Help.isOpen()) { Help.close(); return true; }   // 0x004F4CF0: right release
  if (e.button === 2 && window.MsgWin && MsgWin.rightClick(x, y)) return true;           // message window (no buttons): close
  if (e.button === 2 && window.NewGame && NewGame.rightClick()) return true;         // new game: a step back (ours)
  if (e.button === 2 && window.Campaign && Campaign.rightClick()) return true;       // campaign screens (campaign.js)
  if (e.button === 2 && window.Options && Options.rightClick()) return true;           // option dialogs: right click
  if (e.button === 2 && window.MilPanel && MilPanel.armyOpen() && MilPanel.rightClick()) return true;   // army dialog: cancel
  if (e.button === 2 && window.Lists && Lists.rightClick(x, y)) return true;          // messages: delete a row; else close
  if (e.button === 2 && UIX.info) { UIX.submenu = null; UIX.info = null; return true; }
  if (e.button === 2 && window.Advisors && Advisors.isOpen()) { Advisors.close(); return true; }   // 0x00F2A6FC -> screen 1
  if (e.button === 2 && !(window.Advisors && Advisors.isOpen()) && window.Help) {
    const h = UIX.rhelp.find(q => x >= q[0] && y >= q[1] && x < q[0] + q[2] && y < q[1] + q[3]);
    if (h) { UIX.submenu = null; Help.open(h[4]); return true; }
  }
  if (e.button === 2 && UIX.submenu != null && !inUI(e.clientX, e.clientY)) {   // right click closes
    UIX.submenu = null; return true;
  }
  for (let i = UIX.hits.length - 1; i >= 0; i--) {
    const h = UIX.hits[i];
    if (x >= h[0] && y >= h[1] && x < h[0] + h[2] && y < h[1] + h[3]) {
      if (e.button === 0 && h[4]) {
        if (audio) { audio.start(); audio.sfxNamed("button"); }
        UIX.down = true;
        UIX.rep = h[6] ? { name: h[5], x: h[0], y: h[1], n: 0 } : null;   // fires now with counter 0 (exe)
        h[4]();
      }
      return true;
    }
  }
  if (window.WorldMap && WorldMap.isOpen()) return WorldMap.down(e, x, y);
  if (inUI(e.clientX, e.clientY)) return true;
  if (e.button === 0 && UIX.info) { UIX.info = null; return true; }   // left click elsewhere closes it (bugs.md 81)
  if (e.button === 0 && UIX.submenu != null) UIX.submenu = null;
  return false;
}
