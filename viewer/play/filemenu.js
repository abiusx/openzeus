// The top bar's File menu and its dialogs, drawn as the exe does (docs/play/options.md "File menu"): dropdown
// 0x00431210 with the menu table 0x005EFCC0 (New, Replay episode, Load, Save, Delete, Exit game); Load / Save / Delete
// share screen 0x0D (draw 0x0059BCD0, modes 1 / 0 / 2). New and Replay are ours (the exe goes to its adventure
// screens): a confirm box. Saves live on the server: GET /saves.json, POST /control {save_as | load | delete | new}.
"use strict";

const FM = {
  open: false,          // dropdown shown
  x: 10,                // title x (set by the top bar)
  dlg: null,            // {kind: "new"|"replay"|"load"|"save"|"delete", saves, name, top, busy, msg, fail}
  sb: { scroll: 0, range: 0 },
};
const FM_ROWS = 12;     // visible list rows (0x0059BCD0)

function fmText(i) {    // text group 1 (top_menu.file)
  const t = (typeof MAP !== "undefined" && MAP.strings_ui && MAP.strings_ui.top_menu && MAP.strings_ui.top_menu.file) || [];
  return (t[i] && t[i].text) || ["File", "New adventure", "Replay episode", "Load adventure", "Save adventure", "Exit game", "Delete adventure"][i];
}
// menu table 0x005EFCC0: text index per row
function fmItems() { return [[fmText(1), "new"], [fmText(2), "replay"], [fmText(3), "load"], [fmText(4), "save"], [fmText(6), "delete"], [fmText(5), "exit"]]; }
const fmOpt = (g, i) => (window.Options && Options.ready() ? Options.text(g, i) : "");

// File title in the top bar (ui.js drawTopBar calls this with the title's rect)
function fmTitle(x, w) {
  FM.x = x;
  UIX.hits.push([x - 4, 0, w + 8, 24, () => { FM.open = !FM.open; UIX.submenu = null; if (window.Options) { Options.closeMenu(); Options.load(); } }, "File"]);
}

// dropdown (as options.js): (x, 24) under the bar's edge, cols = widest string of group 1 / 16 + 2, rows =
// (20n+20)/16, items at (x+8, 36+20i)
function fmDropdown(live = true) {
  const items = fmItems(), x = FM.x;
  const all = [0, 1, 2, 3, 4, 5, 6].map(fmText);
  const tw = Math.max(1, ...all.map(s => (window.ZText ? ZText.measure("SPR_FONTS_11C", s) : 8 * s.length)));
  const cols = Math.trunc(tw / 16) + 2, rows = Math.trunc((20 * items.length + 20) / 16);
  if (live) UIX.hits.push([0, 0, UIX.W, UIX.H, () => { FM.open = false; }, ""]);       // a click elsewhere closes
  uiFrame("titled", x, 24, cols, rows, true);
  uiTopBarOver(x, 16 * cols);
  if (live) UIX.hits.push([x, 24, 16 * cols, 16 * rows, null, ""]);
  items.forEach(([s, kind], i) => {
    const y = 36 + 20 * i, hov = live && uiHover(x, y - 2, 16 * cols, 20);
    uiText(s, x + 8, y, hov ? "SPR_FONTS_11LTYEL" : "SPR_FONTS_11C");
    if (live) UIX.hits.push([x, y - 2, 16 * cols, 20, () => { FM.open = false; FM.ghost = kind; fmOpen(kind); }, s]);
  });
}

async function fmOpen(kind) {
  if (kind === "exit") { FM.ghost = null; return toast("Exit game: close the browser tab (the server keeps the city)"); }
  if (kind === "new" && window.NewGame) { FM.ghost = null; return NewGame.open(); }   // the map / difficulty choice (newgame.js)
  FM.dlg = { kind, saves: [], name: "", busy: false, msg: "", fail: 0 };
  FM.sb.scroll = 0;
  if (kind === "new" || kind === "replay") return;
  try { FM.dlg.saves = await getJSON("saves.json", 5000); }
  catch (e) { FM.dlg.msg = "server unreachable"; }
  if (kind === "save") FM.dlg.name = (FM.dlg.saves[0] && FM.dlg.saves[0].name) || "";
}

async function fmAct() {
  const d = FM.dlg;
  if (!d || d.busy) return;
  const name = d.name.trim();
  const isNew = d.kind === "new" || d.kind === "replay";
  if (!isNew && !name) return;
  if (d.kind !== "save" && !isNew && !d.saves.some(s => s.name === name)) { d.fail = 25; return; }   // 43:2 in red
  if (d.kind === "replay" && window.Campaign && Campaign.active()) {   // a campaign: the episode's start (flow.replay)
    FM.dlg = null; FM.ghost = null;
    return Campaign.replay();
  }
  const body = isNew ? (d.kind === "replay" && S && S.map ? { new: true, map: S.map } : { new: true }) : { [d.kind === "save" ? "save_as" : d.kind]: name };
  d.busy = true; d.msg = d.kind === "load" ? "loading..." : "";
  const fresh = isNew || d.kind === "load";
  if (fresh) Loading.start();
  let r;
  try {
    r = await (await fetch("/control", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: AbortSignal.timeout(60000) })).json();
  } catch (e) { r = { ok: false, out: "server unreachable" }; }
  d.busy = false;
  if (!r.ok) { if (fresh) Loading.end(); d.msg = r.out || "failed"; return; }
  FM.dlg = null; FM.ghost = null;
  if (isNew || d.kind === "load") { UIX.info = null; resetPlayback(); }
  toast(isNew ? "new empty city" : r.out);
}

// file dialog (screen 0x0D, 0x0059BCD0): titled frame (ox+128, oy+40) 24x21; inset frames (ox+144, oy+80) 20x2 (the
// name) and (ox+144, oy+120) 20x13 (the list); title 43:mode centred in 304 at (ox+160, oy+50) (load 1, save 0,
// delete 6; 43:2 "File does not exist" in red for a few frames after a failed load); "Proceed?" 43:5 at
// (ox+224, oy+342); 12 rows at (ox+160, oy+130+16i), hovered 11C2, others 11CB; scrollbar (ox+464, oy+120) h 208;
// buttons 0x005EF668: cancel (344,335) SPR_BUTTONS6 328, proceed (392,335) 324, 34x34; the name at (ox+160, oy+90)
// with the caret (FUN_0059FD60: blinks 200 ms off / 400 ms on; after the name: ours + one space)
function fmFileDialog(d) {
  const X = Math.trunc((UIX.W - 640) / 2), Y = Math.trunc((UIX.H - 480) / 2);
  uiFrame("titled", X + 0x80, Y + 0x28, 0x18, 0x15);
  uiFrame("plain", X + 0x90, Y + 0x50, 0x14, 2);
  uiFrame("plain", X + 0x90, Y + 0x78, 0x14, 0x0D);
  const mode = d.fail > 0 ? 2 : d.kind === "delete" ? 6 : d.kind === "load" ? 1 : 0;
  if (d.fail > 0) d.fail--;
  uiText(fmOpt(43, mode), X + 0xA0, Y + 0x32, "SPR_FONTS_22C", { center: 0x130, color: d.fail > 0 ? 0xF800 : undefined });
  uiText(fmOpt(43, 5), X + 0xE0, Y + 0x156, "SPR_FONTS_11C");
  const n = d.saves.length;
  FM.sb.range = Math.max(0, n - FM_ROWS);
  FM.sb.scroll = Math.max(0, Math.min(FM.sb.scroll, FM.sb.range));
  for (let i = 0; i < Math.min(FM_ROWS, n - FM.sb.scroll); i++) {
    const s = d.saves[FM.sb.scroll + i], ry = Y + 0x72 + 16 * (i + 1);
    const hov = uiHover(X + 160, Y + 128 + 16 * i, 288, 16);
    uiText(s.name, X + 0xA0, ry, hov ? "SPR_FONTS_11C2" : "SPR_FONTS_11CB");
    UIX.hits.push([X + 160, Y + 128 + 16 * i, 288, 16, () => { d.name = s.name; }, s.name]);   // 0x00401BB0
  }
  // buttons: +1 hovered (40-byte draw table)
  [[344, 328, () => { FM.dlg = null; FM.ghost = null; }, "Cancel"], [392, 324, fmAct, "Proceed"]].forEach(([bx, img, fn, nm]) => {
    const hov = uiHover(X + bx, Y + 335, 34, 34);
    uiPut(sprite("Zeus_Interface", img + (hov ? 1 : 0)), X + bx, Y + 335);
    UIX.hits.push([X + bx, Y + 335, 34, 34, fn, nm]);
  });
  if (window.Help) fmScrollbar(X + 0x1D0, Y + 0x78, 208);
  uiText(d.name, X + 0xA0, Y + 0x5A, "SPR_FONTS_11C2");
  const blink = window.__caret ?? performance.now() % 600 >= 200;  // 200 ms off, 400 ms on (FUN_0059FD60); __caret: checks
  if (blink && window.ZText && UIX.red) {         // FUN_0059FD60 (0xF13A93 == 0): a 2-px bar in 0xFFFF under the cursor
    const Wt = { ...UIX.red, x: 1 }, cx = X + 0xA0 + (d.name ? ZText.advance("SPR_FONTS_11C2", d.name) + 6 : 0);
    uiPut(Wt, cx, Y + 0x5B + 14, 1, 4, 2);       // 4x2 at (ox+160, oy+105) with no name: seen (oracle file-dialogs load.bmp)
  }
  if (d.msg) uiText(d.msg, X + 0xA0, Y + 0x156 - 18, "SPR_FONTS_11CB");
}
// the list's scrollbar: arrows and track always drawn, the ball only with more rows than fit
function fmScrollbar(x, y, h) {
  if (FM.sb.range > 0) return Help.scrollbar(x, y, h, FM.sb);
  const trackH = 16 * Math.trunc((h - 52) / 16), top = y + Math.trunc((h - trackH) / 2);
  uiPut(sprite("Zeus_Interface", 332), x, y);
  uiPut(sprite("Zeus_Interface", 336), x, y + h - 26);
  uiFrame("plain", x + 2, top, 2, trackH / 16);
}

// a text button on the original's button bar tiles (style 2 = normal, 1 = hovered: SPR_PANELING 205+0x1A+3v..)
function fmButton(label, x, y, cells, onClick, enabled = true) {
  const hov = enabled && uiHover(x, y, 16 * cells, 20), v = hov ? 1 : 2, I = (k) => sprite("Zeus_Interface", 205 + 0x1A + 3 * v + k);
  for (let c = 0; c < cells; c++) uiPut(I(1), x + 16 * c, y);
  uiPut(I(0), x, y); uiPut(I(2), x + 16 * cells - 16, y);
  uiText(label, x, y + 4, "SPR_FONTS_11C", { center: 16 * cells });
  if (enabled) UIX.hits.push([x, y, 16 * cells, 20, onClick, label]);
}

function fmDialog() {
  const d = FM.dlg;
  if (!d) return;
  if (FM.ghost) fmDropdown(false);                 // the exe does not repaint the menu away under the dialog
  uiFlushText();
  UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);  // modal
  if (d.kind !== "new" && d.kind !== "replay") return fmFileDialog(d);
  // ours: confirm a new city (New adventure) or a restart of this map (Replay episode)
  const cols = 24, rows = 10, W = 16 * cols, H = 16 * rows;
  const x = Math.trunc((UIX.W - 640) / 2) + 0x80, y = Math.trunc((UIX.H - 480) / 2) + 0x28;
  uiFrame("titled", x, y, cols, rows);
  uiText(fmText(d.kind === "new" ? 1 : 2), x, y + 10, "SPR_FONTS_22C", { center: W });
  uiText(d.kind === "new" ? "Start a new empty city? The current city is lost unless you saved it."
                          : "Start this map again? The current city is lost unless you saved it.", x + 32, y + 56, "SPR_FONTS_11C", { width: W - 64 });
  if (d.msg) uiText(d.msg, x + 32, y + H - 66, "SPR_FONTS_11CB");
  fmButton(fmOpt(45, 4) || "OK", x + 32, y + H - 44, 7, fmAct, !d.busy);
  fmButton(fmOpt(45, 1) || "Cancel", x + W - 32 - 112, y + H - 44, 7, () => { FM.dlg = null; FM.ghost = null; });
}

function fmDraw() { if (FM.open) fmDropdown(); fmDialog(); }

// keys while a dialog is open (play.js calls this first; true = taken): typing edits the name (0x00508480),
// Enter proceeds, Esc cancels (ours), PgUp/PgDn scroll the list by 12
function fmKey(e) {
  const d = FM.dlg;
  if (!d) {
    if (FM.open && e.key === "Escape") { FM.open = false; return true; }
    return false;
  }
  if (e.key === "Escape") { FM.dlg = null; FM.ghost = null; }
  else if (e.key === "Enter") fmAct();
  else if (e.key === "PageUp" || e.key === "PageDown") FM.sb.scroll += e.key === "PageDown" ? FM_ROWS : -FM_ROWS;
  else if (d.kind !== "new" && d.kind !== "replay") {
    if (e.key === "Backspace") d.name = d.name.slice(0, -1);
    else if (e.key.length === 1 && /[A-Za-z0-9 ._-]/.test(e.key) && d.name.length < 40) d.name += e.key;
  }
  e.preventDefault();
  return true;
}
