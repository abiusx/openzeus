// The top bar's Options and Help menus and the option dialogs, as the exe draws them (docs/play/options.md):
// dropdown 0x00431210 (screen 3), Display 0x0059AF60 (screen 0x0A), Sound 0x0059B5E0 (0x0B), Speed 0x0059B330
// (0x0C), Difficulty 0x0059B200 (0x45), Messages 0x0059BBE0 (0x1D); the toggles Autosave 0x00402660, Auto Defend
// 0x005692D0, Balloon help 0x004025D0, Warnings 0x00402620. Data: data/play/options.json (tools/play_options.py).
// Settings are this viewer's (localStorage): the exe keeps them in Zeus.inf, ours has one browser per player.
"use strict";

const Options = (() => {
  let D = null, loading = false, menu = null, dlg = null, ghost = null, snap = null, srv = null;
  const S = {                                       // defaults: the oracle's settings (re/oracle runs: options-menus)
    music: true, speech: true, general: true, ambient: true, sound3d: true,
    v_music: 50, v_speech: 100, v_general: 80, v_ambient: 80,
    game_speed: 90, scroll_speed: 60, autosave_off: false, auto_defend: false, balloon: 2, warnings: true,
    messages: Array(20).fill(2),
  };
  try { Object.assign(S, JSON.parse(localStorage.getItem("zeus-options") || "{}")); } catch (e) { }
  const save = () => { try { localStorage.setItem("zeus-options", JSON.stringify(S)); } catch (e) { } };

  async function load() {
    if (D || loading) return;
    loading = true;
    try { D = await getJSON("/data/play/options.json"); } catch (e) { console.warn("options.json", e); }
    loading = false;
  }
  const t = (g, i) => (D && D.texts[String(g)] && D.texts[String(g)][i]) || "";
  const ox = () => Math.trunc((UIX.W - 640) / 2), oy = () => Math.trunc((UIX.H - 480) / 2);

  // ---- audio and speed follow the settings ----------------------------------------------------------------
  function applyAudio() {
    if (typeof audio === "undefined" || !audio) return;
    audio.setVolume("music", S.music ? S.v_music / 100 : 0);
    audio.setVolume("sfx", S.general ? S.v_general / 100 : 0);
    audio.setVolume("amb", S.ambient ? S.v_ambient / 100 : 0);
    audio.setVolume("voice", S.speech ? S.v_speech / 100 : 0);   // walker voices (0x00F2A76D / 0x00F2A7D4)
  }
  // game speed -> ticks per second as simulation_due 0x005168A0: one tick per speed_delay_ms[(100-s)/10] + 2 ms;
  // speed 100 (2 ms) runs one tick per frame in the exe: 60 here (hypothesis: the frame rate)
  function tickRate(s) { const k = Math.trunc((100 - s) / 10); return k <= 0 ? 60 : Math.round(1000 / (D.speed_delay_ms[k] + 2)); }
  function applySpeed() { if (D && typeof setRate === "function") setRate(tickRate(S.game_speed)); }
  // scroll speed (FUN_00516950): one scroll step every ((100-s)/10)*12+2 ms; ours = the camera speed times the
  // exe's step rate relative to the default 60 (50 ms); 0 = no keyboard/edge scrolling
  function scrollFactor() { const k = Math.trunc((100 - S.scroll_speed) / 10); return k >= 10 ? 0 : 50 / (k * 12 + 2); }

  // ---- menus (dropdown 0x00431210) ------------------------------------------------------------------------
  // frame: titled middle tiles at (title x, 24), cols = widest string of the whole text group / 16 + 2
  // (0x005127C0), rows = (20n+20) / 16; items at (x+8, 30+20i), hovered 0xFAC1 (ours 11LTYEL)
  const titles = {};
  function title(group, x, w) {
    titles[group] = [x, w];
    const name = group === 2 ? "options" : "help";
    UIX.hits.push([x - 4, 0, w + 8, 24, () => { load(); menu = menu === name ? null : name; if (window.FM) FM.open = false; }, t(group, 0) || name]);
  }
  function isMenu(group) { return (group === 2 && menu === "options") || (group === 3 && menu === "help"); }
  function items(name) {
    if (!D) return [];
    const M = D.menus[name];
    return M.map(m => {
      let i = m.text;
      if (name === "options" && i === 9) i = S.autosave_off ? 10 : 9;
      if (name === "options" && i === 11) i = S.auto_defend ? 11 : 12;
      if (name === "help" && i === 2) i = [2, 3, 4][S.balloon];
      if (name === "help" && i === 5) i = S.warnings ? 6 : 5;
      return [t(name === "options" ? 2 : 3, i), m.fn];
    });
  }
  function dropdown(name, live) {
    const group = name === "options" ? 2 : 3, at = titles[group];
    if (!at || !D) return;
    const its = items(name), x = at[0];
    const widest = Math.max(1, ...D.texts[String(group)].map(s => ZText.measure("SPR_FONTS_11C", s)));
    const cols = Math.trunc(widest / 16) + 2, rows = Math.trunc((20 * its.length + 20) / 16);
    if (live) UIX.hits.push([0, 0, UIX.W, UIX.H, () => { menu = null; }, ""]);
    uiFrame("titled", x, 24, cols, rows, true);           // (x, 24) under the bar's edge; items at 36+20i
    uiTopBarOver(x, 16 * cols);
    if (live) UIX.hits.push([x, 24, 16 * cols, 16 * rows, null, ""]);
    its.forEach(([s, fn], i) => {
      const y = 36 + 20 * i, hov = live && uiHover(x, y - 2, 16 * cols, 20);
      uiText(s, x + 8, y, hov ? "SPR_FONTS_11LTYEL" : "SPR_FONTS_11C");
      if (live) UIX.hits.push([x, y - 2, 16 * cols, 20, () => { menu = null; ghost = { name }; act(fn); }, s]);
    });
  }
  // a menu open: moving over another title switches to it (as the exe's menu bar)
  function track() {
    if (!menu && !(window.FM && FM.open)) return;
    const [mx, my] = UIX.mouse;
    if (my >= 24) return;
    for (const [g, [x, w]] of Object.entries(titles)) if (mx >= x - 4 && mx < x + w + 4) {
      const name = +g === 2 ? "options" : "help";
      if (menu !== name) { menu = name; if (window.FM) FM.open = false; if (name === "options") refresh(); }
    }
    if (window.FM && FM.x != null && mx >= FM.x - 4 && mx < FM.x + 40 && menu) { menu = null; FM.open = true; }
  }

  async function act(fn) {
    switch (fn) {
      case "0x401db0": return open("display");
      case "0x401f90": return open("sound");
      case "0x4023d0": return open("speed");
      case "0x401ec0": return open("difficulty");
      case "0x4026a0": return open("messages");
      case "0x402660": S.autosave_off = !S.autosave_off; save(); return;
      case "0x5692d0": {                              // cannot be switched on while invaders are on the map
        await refresh();                              // the sim keeps the setting (sim/military/alarm.py)
        if (srv && srv.auto_defend != null) S.auto_defend = srv.auto_defend;
        if (!S.auto_defend && srv && srv.invaders) return;
        S.auto_defend = !S.auto_defend; save();
        try { await fetch("/cmd", { method: "POST", headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({ cmds: [`autodefend ${S.auto_defend ? "on" : "off"}`] }) }); }
        catch (e) { }
        return;
      }
      case "0x402500": return Help.open(1);
      case "0x4025d0": S.balloon = S.balloon === 0 ? 2 : 0; save(); return;    // 2 -> 0 -> 2 (SOME only from Zeus.inf)
      case "0x402620": S.warnings = !S.warnings; save(); return;
      case "0x4025c0": return Help.open(0);
    }
  }
  async function refresh() {
    try { srv = await getJSON("/options.json"); if (srv.auto_defend != null) S.auto_defend = srv.auto_defend; } catch (e) { }
  }
  function open(kind) { dlg = kind; snap = JSON.parse(JSON.stringify(S)); if (kind === "difficulty") refresh(); }
  function close(keep = true) {
    if (!keep && snap) { const sp = dlg === "speed"; Object.assign(S, snap); applyAudio(); if (sp) applySpeed(); }
    dlg = null; ghost = null; snap = null; save();
  }

  // ---- dialog pieces --------------------------------------------------------------------------------------
  // button bar 0x0059FBA0: SPR_PANELING first + 0x1A + 3v (left), +0x1B (middle, every cell), +0x1C (right);
  // v = 1 hovered, 2 normal
  function bar(x, y, cells, hov) {
    const v = hov ? 1 : 2, I = (k) => sprite("Zeus_Interface", 205 + 0x1A + 3 * v + k);
    for (let c = 0; c < cells; c++) uiPut(I(1), x + 16 * c, y);
    uiPut(I(0), x, y);
    uiPut(I(2), x + 16 * cells - 16, y);
  }
  function hoverIndex(rects) {                      // DAT_00781844: 1-based hovered hit rect
    const [mx, my] = UIX.mouse, X = ox(), Y = oy();
    for (let i = 0; i < rects.length; i++) {
      const [a, b, c, d] = rects[i];
      if (mx >= X + a && mx < X + c && my >= Y + b && my < Y + d) return i + 1;
    }
    return 0;
  }
  function hit(rect, fn, name) { const [a, b, c, d] = rect; UIX.hits.push([ox() + a, oy() + b, c - a, d - b, fn, name || ""]); }
  // arrow lists (0x00431C80): 24x24 at list origin + (x, y); the pressed image (+1) while held; held repeats
  function arrows(list, x0, y0, fn) {
    for (const a of list) {
      const x = x0 + a.x, y = y0 + a.y, held = UIX.down && uiHover(x, y, a.size, a.size);
      uiPut(sprite("Zeus_Interface", D.arrow_images[String(a.group)] + (held ? 1 : 0)), x, y);
      UIX.hits.push([x, y, a.size, a.size, () => fn(a), a.a1 ? "down" : "up", true]);
    }
  }
  const pct = (v) => ZText.numberText(v, "@", "%");
  // RIMS highlight (window_highlight_draw 0x0059F6E0): edges only, the last tile pulled back; hovered = +8
  function rims(x, y, w, h, hover) {
    const base = UIX.D.frames.highlight.sprite_group.index + (hover ? 8 : 0);
    const nc = Math.ceil(w / 16), nr = Math.ceil(h / 16), I = (k) => sprite("Zeus_Interface", base + k);
    for (let c = 0; c < nc; c++) {
      const tx = c === nc - 1 ? x + w - 16 : x + 16 * c;
      uiPut(I(c === 0 ? 0 : c === nc - 1 ? 2 : 1), tx, y);
      uiPut(I(c === 0 ? 6 : c === nc - 1 ? 4 : 5), tx, y + h - 16);
    }
    for (let r = 1; r < nr - 1; r++) { uiPut(I(7), x, y + 16 * r); uiPut(I(3), x + w - 16, y + 16 * r); }
  }

  // ---- dialogs --------------------------------------------------------------------------------------------
  const DRAW = {
    display() {                                     // 0x0059AF60: (ox+96, oy+80) 18x12
      const X = ox(), Y = oy(), h = hoverIndex(D.hits.display);
      uiFrame("titled", X + 0x60, Y + 0x50, 0x12, 0x0C);
      for (let i = 0; i < 4; i++) bar(X + 0x80, Y + 0x88 + 24 * i, 0x0E, h === i + 1);
      uiText(t(42, 0), X + 0x80, Y + 0x5E, "SPR_FONTS_22C", { center: 0xE0 });
      const full = !!document.fullscreenElement;
      [full ? 2 : 1, 3, 4, 5].forEach((k, i) => uiText(t(42, k), X + 0x80, Y + 0x8C + 24 * i, "SPR_FONTS_11C", { center: 0xE0 }));
      // full screen toggles the browser's; the resolutions are the browser window's (ours: they close only)
      const acts = [() => { (full ? document.exitFullscreen() : document.documentElement.requestFullscreen()).catch(() => { }); close(); },
                    () => close(), () => close(), () => close()];
      D.hits.display.forEach((r, i) => hit(r, acts[i], t(42, [full ? 2 : 1, 3, 4, 5][i])));
    },
    sound() {                                       // 0x0059B5E0: (ox+48, oy+80) 24x20
      const X = ox(), Y = oy(), H = D.hits.sound.slice(0, 7), h = hoverIndex(H);
      uiFrame("titled", X + 0x30, Y + 0x50, 0x18, 0x14);
      [0xA2, 0xC0, 0xDE, 0xFC].forEach((y, k) => bar(X + 0x40, Y + y, 0x0E, h === k + 1));
      bar(X + 0x90, Y + 0x146, 0x0C, h === 5);
      bar(X + 0x90, Y + 0x164, 0x0C, h === 6);
      bar(X + 0x40, Y + 0x11A, 0x0E, h === 7);
      uiText(t(46, 0), X + 0x60, Y + 0x5C, "SPR_FONTS_22C", { center: 0x120 });
      uiText(t(46, 12), X + 0x80, Y + 0x14A, "SPR_FONTS_11C", { center: 0xE0 });
      uiText(t(46, 9), X + 0x80, Y + 0x168, "SPR_FONTS_11C", { center: 0xE0 });
      uiText(t(46, 10), X + 0x70, Y + 0x8E, "SPR_FONTS_11C");
      uiText(t(46, 11), X + 0x150, Y + 0x8E, "SPR_FONTS_11C");
      const rows = [["music", 1, "v_music"], ["speech", 3, "v_speech"], ["general", 5, "v_general"], ["ambient", 7, "v_ambient"]];
      rows.forEach(([k, base, v], i) => {
        const y = Y + 0xA6 + 0x1E * i;
        uiText(t(46, base + (S[k] ? 1 : 0)), X + 0x40, y, "SPR_FONTS_11C", { center: 0xE0 });
        uiText(pct(S[v]), X + 0x172, y, "SPR_FONTS_11C");
      });
      uiText(t(46, S.sound3d ? 14 : 13), X + 0x40, Y + 0x11E, "SPR_FONTS_11C", { center: 0xE0 });
      // rows toggle (0x00402110; off stops the channel); OK keeps; Cancel restores (0x00402020)
      rows.forEach(([k], i) => hit(H[i], () => { S[k] = !S[k]; applyAudio(); }, t(46, rows[i][1] + 1)));
      hit(H[4], () => close(true), t(46, 12));
      hit(H[5], () => close(false), t(46, 9));
      hit(H[6], () => { S.sound3d = !S.sound3d; }, t(46, 14));
      arrows(D.arrows.sound, X + 0xD0, Y + 0x3C, (a) => {
        const k = rows[Math.trunc(D.arrows.sound.indexOf(a) / 2)][2];
        S[k] = Math.max(0, Math.min(100, S[k] + (a.a1 ? -5 : 5))); applyAudio();
      });
    },
    speed() {                                       // 0x0059B330: (ox+96, oy+80) 18x14
      const X = ox(), Y = oy(), h = hoverIndex(D.hits.speed);
      uiFrame("titled", X + 0x60, Y + 0x50, 0x12, 0x0E);
      bar(X + 0x90, Y + 0xE8, 0x0C, h === 1);
      bar(X + 0x90, Y + 0x106, 0x0C, h === 2);
      uiText(t(45, 0), X + 0x76, Y + 0x5C, "SPR_FONTS_22C", { center: 0xE0 });
      uiText(t(45, 4), X + 0x80, Y + 0xEC, "SPR_FONTS_11C", { center: 0xE0 });
      uiText(t(45, 1), X + 0x80, Y + 0x10A, "SPR_FONTS_11C", { center: 0xE0 });
      uiText(t(45, 2), X + 0x90, Y + 0x92, "SPR_FONTS_11C");
      uiText(pct(S.game_speed), X + 0x128, Y + 0x92, "SPR_FONTS_11C");
      uiText(t(45, 3), X + 0x90, Y + 0xB6, "SPR_FONTS_11C");
      uiText(pct(S.scroll_speed), X + 0x128, Y + 0xB6, "SPR_FONTS_11C");
      hit(D.hits.speed[0], () => close(true), t(45, 4));                          // OK 0x004066D0
      hit(D.hits.speed[1], () => close(false), t(45, 1));                         // Cancel 0x00402400
      arrows(D.arrows.speed, X + 0x80, Y + 0x28, (a) => {
        if (a.fn === "0x402430") { S.game_speed = Math.max(10, Math.min(100, S.game_speed + (a.a1 ? -10 : 10))); applySpeed(); }
        else S.scroll_speed = Math.max(0, Math.min(100, S.scroll_speed + (a.a1 ? -10 : 10)));
      });
    },
    difficulty() {                                  // 0x0059B200: (ox+48, oy+80) 24x12; no buttons, right click
      const X = ox(), Y = oy(), d = srv ? srv.difficulty : null;
      uiFrame("titled", X + 0x30, Y + 0x50, 0x18, 0x0C);
      uiText(t(153, 0), X + 0x30, Y + 0x5E, "SPR_FONTS_22C", { center: 0x180 });
      if (d != null) uiText(t(153, d + 1), X + 0x50, Y + 0xAE, "SPR_FONTS_11C", { center: 0xE0 });
      arrows(D.arrows.difficulty, X + 0x120, Y + 0x70, async (a) => {
        if (d == null) return;
        const n = Math.max(0, Math.min(4, d + (a.a1 ? -1 : 1)));            // 0x00401EE0: clamp 0..4
        if (n === d) return;
        const names = ["VeryEasy", "Easy", "Normal", "Hard", "Impossible"];  // g_difficulty order (sim/data.py)
        try {                                         // each click at once, silent (no toast, as the exe)
          const r = await (await fetch("/cmd", { method: "POST", headers: { "Content-Type": "application/json" },
                                                 body: JSON.stringify({ cmds: [`difficulty ${names[n]}`] }) })).json();
          const f = (r.results || []).find(x => !x.ok);
          if (f || r.live === false) toast(f ? f.out : r.out, true);
        } catch (e) { toast("difficulty: server unreachable", true); }
        refresh();
      });
      uiText(t(153, 8), X + 0x30, Y + 0xF6, "SPR_FONTS_11C", { center: 0x180 });
    },
    messages() {                                    // 0x0059BBE0: (ox, oy) 34x21, no title; 17 categories
      const X = ox(), Y = oy(), n = Math.min(20, D.texts["174"].length), R = D.hits.messages, h = hoverIndex(R.slice(0, n));
      uiFrame("titled", X, Y, 0x22, 0x15);
      for (let i = 0; i < n; i++) {
        const [a, b, c, d] = R[i];
        rims(X + a, Y + b, c - a, d - b, h === i + 1);
        uiText(t(174, i), X + a - 153, Y + b + 7, "SPR_FONTS_11C");
        uiText(t(183, S.messages[i]), X + a + 4, Y + b + 7, "SPR_FONTS_11C");
        hit(R[i], () => {                         // 0x004026C0; the sim keeps the levels too (offers answer by them)
          S.messages[i] = i === 19 ? 2 : (S.messages[i] + 1) % 3; save();
          sendCommands([`msglevel ${i} ${S.messages[i]}`], { sound: false }).catch(() => { });
        }, t(174, i));
      }
    },
  };

  function draw() {
    tick();
    track();
    if ((dlg || menu || (window.FM && (FM.open || FM.dlg))) && window.Balloon) Balloon.none();   // menus, dialogs: none
    if (dlg && D) {
      if (ghost) dropdown(ghost.name, false);       // the exe does not repaint the screen under the dialog
      uiFlushText();
      UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
      DRAW[dlg]();
      return;
    }
    if (menu) dropdown(menu, true);
  }
  function isOpen() { return !!dlg; }
  function rightClick() { if (dlg) { close(true); return true; } if (menu) { menu = null; return true; } return false; }

  // autosave (autosave_if_due 0x005123D0): in January and July (month_advance sets the pending flag), unless
  // switched off; ours saves the city as "autosave" on the server
  let lastMonth = null;
  function tick() {
    const f = P && P.f0;
    if (!f || !f.date || !D) return;
    const m = D.texts["25"].indexOf(String(f.date).split(" ")[0]);
    if (m < 0 || m === lastMonth) return;
    const first = lastMonth == null;
    lastMonth = m;
    if (!first && (m === 0 || m === 6) && !S.autosave_off && P.live)
      fetch("/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ save_as: "autosave" }) }).catch(() => { });
  }

  return { title, isMenu, draw, isOpen, rightClick, tick, scrollFactor, settings: S, load, text: t, ready: () => !!D, rims, open: (k) => { load().then(() => open(k)); },
           closeMenu: () => { menu = null; }, menuOpen: () => menu, balloon: () => S.balloon,
           act: (fn) => load().then(() => act(fn)) };   // e.g. act("0x5692d0"): the Military page's helmet (pages.js)
})();
window.Options = Options;
