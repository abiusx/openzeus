// The campaign screens in play mode (track 1L-4; docs/play/campaign.md). The game's campaign state lives in the sim's
// campaign module (sim/campaign); the live server tells which screen is up (GET /campaign.json, flow.screens; the
// key meta.campaign of /frames.json changes whenever it must be fetched again) and holds the city while one is up,
// as the exe's screens stop simulation_due. Actions go to POST /campaign (sim/live.py campaign_op).
//   briefing  screen 0x35 (FUN_0052E520): NewGame.intro; "To the city" -> {op: "briefed"}
//   tutorial  a tutorial's start: its goals screen 0x3B with the tutorial buttons (Lists.objectives); a right click
//             -> {op: "briefed"}
//   victory   screen 0x42 (FUN_0052D590): Lists.objectives("victory") + Proceed (rect 0x00640948 at (ox - 60, oy + 34))
//   complete  screen 0x43 (FUN_0052D7C0): Lists.objectives("complete") + New Adventure / Continue building this city /
//             Exit Game (rects 0x00640968 at (ox + 20, oy + 14))
//   defeat    screen 0x33 (fullscreen_background_b 0x00422270 + FUN_00422AB0): Failure! New Adventure / Replay episode
//   colony    screen 0x34 (FUN_00421C70): the world map's colony choice (world.js WorldMap.colonyChoice)
//   set aside the 0x3F confirm (FUN_00432380 from 0x00529CC0: 5:0x1A "Set goods aside for parent city?" in a colony
//             start, else 5:0x1C "... for colony?") over the objectives screens; yes -> {op: "setaside"} (0x0052ECF0)
// Not drawn (ours): the full-screen pictures behind 0x35 / 0x43 / 0x33 (the city stays behind them).
"use strict";

const Campaign = (() => {
  let key = null, D = null, gen = 0, dlg = null, busy = false, msg = "", voiced = "";
  const t = (g, i) => (window.Options ? Options.text(g, i) : "");
  const ox = () => Math.trunc((UIX.W - 640) / 2), oy = () => Math.trunc((UIX.H - 480) / 2);
  const rec = (n) => { const H = window.Help && Help.data(); return (H && n >= 0 && H.records[n]) || null; };
  const BAR = 205;                                  // SPR_PANELING: button_bar_draw 0x0059ED50 (+ 3 hovered)

  function meta(k) {
    k = k || null;
    if (k === key) return;
    key = k;
    if (!k) { D = null; dlg = null; return; }
    refresh();
  }
  async function refresh() {
    const my = ++gen;
    try {
      if (window.Help) await Help.ensure();
      const d = await getJSON("/campaign.json");
      if (my === gen) { D = d.campaign ? d : null; msg = ""; }
    } catch (e) { /* the next meta change tries again */ }
  }
  const screen = () => (D ? D.screen : null);
  const active = () => !!D;
  const isOpen = () => !!(screen() || dlg);

  async function post(body) {
    if (busy) return { ok: false };
    busy = true;
    let r;
    try {
      r = await (await fetch("/campaign", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body), signal: AbortSignal.timeout(60000) })).json();
    } catch (e) { r = { ok: false, out: "server unreachable" }; }
    busy = false;
    if (!r.ok && !r.choose) msg = r.out || "failed";
    return r;
  }
  async function act(body, fresh) {
    if (fresh) Loading.start();
    const r = await post(body);
    if (fresh && !r.ok) Loading.end();
    if (r.ok && fresh) { UIX.info = null; if (typeof resetPlayback === "function") resetPlayback(); }
    await refresh();
    if (window.Lists) Lists.refresh();
    return r;
  }

  // the objectives screens' button rows (Lists.objectives): a lit Set aside row opens the 0x3F confirm
  // a lit quest row (0x0052BC20 -> FUN_0052D240): the army dialog for the quest when its hero is home and idle
  // (0x005BD950, kind "quest", milpanel.js), else the quest's text window (lists.js questWindow)
  async function rowClick(i, r) {
    if (r.type === 14) dlg = { goal: i, colony: D && D.start === "colony" };
    if (r.type !== 4 || !r.quest) return;
    if (!r.quest.army) { if (window.Lists) Lists.questWindow(r.quest); return; }
    let q = null;
    try { q = ((await getJSON("/heroes.json")).quests || []).find(x => x.id === r.quest.event) || null; } catch (e) { q = null; }
    if (!q || !window.MilPanel) return;
    if (window.Lists) Lists.close();
    MilPanel.openArmy(q.city_name || "", "quest", "land", [], [], q);
  }

  // the 0x3F popup (FUN_00432380 at (ox + 0x50, oy + 0x50); drawn by FUN_00431370 as world.js strikeConfirm):
  // titled frame 30 x 10, title 5:id 22C centred in 480 at y + 0x14, text 5:id+1 11C centred at y + 0x3C, two buttons
  // OK 324 at (256, 100), cancel 328 at (192, 100)
  function drawConfirm() {
    const cx = ox() + 0x50, cy = oy() + 0x50, id = dlg.colony ? 0x1A : 0x1C;
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    uiFrame("titled", cx, cy, 30, 10);
    uiText(t(5, id), cx, cy + 0x14, "SPR_FONTS_22C", { center: 480 });
    uiText(t(5, id + 1), cx, cy + 0x3C, "SPR_FONTS_11C", { center: 480 });
    const yes = async () => { const g = dlg.goal; dlg = null; await act({ op: "setaside", goal: g }); };
    [[256, 324, yes, "OK"], [192, 328, () => { dlg = null; }, "Cancel"]].forEach(([bx, img, fn, nm]) => {
      const hov = uiHover(cx + bx, cy + 100, 34, 34);
      uiPut(sprite("Zeus_Interface", img + (hov ? 1 : 0)), cx + bx, cy + 100);
      UIX.hits.push([cx + bx, cy + 100, 34, 34, fn, nm]);
    });
  }

  // a RIMS box button with its label centred 6 px down (11C), as FUN_00509230 + FUN_00509320
  function rimsButton(x, y, w, h, label, fn) {
    Options.rims(x, y, w, h, uiHover(x, y, w, h));
    uiText(label, x, y + 6, "SPR_FONTS_11C", { center: w });
    UIX.hits.push([x, y, w, h, fn, label]);
  }

  async function proceed(colony) {
    Loading.start();
    const r = await post(colony != null ? { op: "proceed", colony } : { op: "proceed" });
    if (!r.ok) Loading.end();                       // also the colony choice (r.choose): nothing loaded yet
    if (r.choose) {                                 // next 1: the colony choice screen 0x34 on the world map
      if (window.WorldMap) WorldMap.colonyChoice(D.colonies || r.choose.map(c => ({ n: c.n, name: c.name, id: c.id, intro: -1 })),
                                                 (n) => proceed(n));
      return;
    }
    if (window.WorldMap && WorldMap.isOpen()) WorldMap.close();
    if (r.ok) { UIX.info = null; if (typeof resetPlayback === "function") resetPlayback(); }
    await refresh();
  }

  function drawVictory() {
    Lists.objectives("victory", D);
    const X = ox(), Y = oy();
    rimsButton(X + 100 - 60, Y + 452 + 34, 354, 20, t(62, 2), () => proceed());
    if (msg) uiText(msg, X - 60, Y + 470, "SPR_FONTS_11C");
  }
  function drawComplete() {
    Lists.objectives("complete", D);
    const X = ox() + 20, Y = oy() + 14;
    rimsButton(X + 40, Y + 432, 250, 20, t(62, 4), () => { if (window.NewGame) NewGame.open(); });
    rimsButton(X + 300, Y + 432, 250, 20, t(62, 3), () => act({ op: "stay" }));
    rimsButton(X + 40, Y + 457, 250, 20, t(62, 7), () => { if (typeof toast === "function") toast("Exit game: close the browser tab (the server keeps the city)"); });
  }

  // screen 0x33: fullscreen_background_b (frame (ox + 0x30, oy + 9) 34 x 16; the title phrase 0xB90 centred in 0x220
  // at oy + 0x20; the loss phrase paragraph at (x + 0x19, oy + 0x40) width 0x200) + FUN_00422AB0 (two button bars
  // of 9 tiles at (x + 0x40 / x + 0x160, oy + 0xE0), 62:4 / 62:35 centred in 0x90 at + 6; one bar of 26 tiles when
  // FUN_005678D0() == 1: not seen)
  function bar(x, y, cells, label, fn) {
    const hov = uiHover(x, y, 16 * cells, 25);
    for (let c = 0; c < cells; c++) uiPut(sprite("Zeus_Interface", BAR + (hov ? 3 : 0) + (c === 0 ? 0 : c === cells - 1 ? 2 : 1)), x + 16 * c, y);
    uiText(label, x, y + 6, "SPR_FONTS_11C", { center: 0x90 });
    UIX.hits.push([x, y, 16 * cells, 25, fn, label]);
  }
  function drawDefeat() {
    const X = ox() + 0x30, Y = oy();
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    uiFrame("titled", X, Y + 9, 34, 16);
    uiText(D.lost_title || t(62, 1), X, Y + 0x20, "SPR_FONTS_22C", { center: 0x220 });
    if (D.lost_text) uiText(D.lost_text, X + 0x19, Y + 0x40, "SPR_FONTS_11C", { width: 0x200 });
    bar(X + 0x40, Y + 0xE0, 9, t(62, 4), () => { if (window.NewGame) NewGame.open(); });
    bar(X + 0x160, Y + 0xE0, 9, t(62, 35), () => act({ op: "replay" }, true));
    if (msg) uiText(msg, X + 0x19, Y + 0xC0, "SPR_FONTS_11C");
  }

  // the difficulty arrows (table 0x005EF988): taken with "To the city" (flow.briefed -> sim/episode.py
  // set_difficulty: a new city's funds x the chosen level; the level stays for colonies and continued cities)
  const DIFF = ["VeryEasy", "Easy", "Normal", "Hard", "Impossible"];
  let bdiff = null, bkey = null;
  function drawBriefing() {
    const k = D.adventure + ":" + D.slot;
    if (bkey !== k) { bkey = k; bdiff = null; }
    const a = rec(D.brief), ep = rec(D.intro), s = D.strings || {};
    NewGame.intro({ name: a ? a[13] : s.title || "", ep: ep ? ep[13] : s.ep_title || "", brief: ep ? ep[15] : s.ep_body || "",
                    briefKey: "c:" + D.adventure + ":" + D.slot,
                    goals: D.goals, diff: bdiff != null ? bdiff : D.difficulty, setDiff: (d) => { bdiff = d; },
                    go: () => act(bdiff != null ? { op: "briefed", difficulty: DIFF[bdiff] } : { op: "briefed" }), msg });
  }

  function draw() {
    if (!D && !dlg) return;
    if (window.Balloon && isOpen()) Balloon.none();
    if (window.NewGame && NewGame.isOpen()) return;            // New Adventure from a campaign screen: on top
    if (window.WorldMap && WorldMap.isOpen() && WorldMap.colony) {   // the colony choice (0x34) replaces the screen
      if (dlg) { uiFlushText(); drawConfirm(); }
      return;
    }
    const s = screen();
    if (s) uiFlushText();
    // the screen's narration + its looped jingle, once per screen (sim/campaign flow.voices; audio.js screenSound:
    // FUN_005A88C0 / FUN_005A8640); the city again ends it (play.js frame)
    const vk = { briefing: "intro", victory: "victory", complete: "complete" }[s];
    const v = vk && D.voices && D.voices[vk], j = v && D.voices.jingles && D.voices.jingles[vk];
    if (v && voiced !== s + v && typeof audio !== "undefined" && audio && audio.ctx) { voiced = s + v; audio.screenSound(v, j); }
    if (!s) voiced = "";
    // the full-screen pictures (FUN_00505310; ui.js uiBackdrop): briefing 0x35, adventure complete 0x43, defeat 0x33;
    // the episode's victory (0x42) and a tutorial's goals screen keep the city behind them
    const bd = { briefing: "briefing", complete: "complete", defeat: "defeat" }[s];
    if (bd && !(s === "briefing" && window.WorldMap && WorldMap.isOpen())) uiBackdrop(bd);
    if (s === "victory") drawVictory();
    else if (s === "complete") drawComplete();
    else if (s === "defeat") drawDefeat();
    else if (s === "briefing" && !(window.WorldMap && WorldMap.isOpen())) drawBriefing();
    else if (s === "tutorial" && window.Lists) Lists.objectives("goals", D);   // a tutorial's start: its goals screen
    if (dlg) { uiFlushText(); drawConfirm(); }
  }
  // the city view's campaign lines (top_left_texts_draw 0x0058F130, screen_draw 0x00514020 after the panel; server
  // flow.top_left): the mask font (DAT_012afbec + 4 = SPR_FONTS) at the exe's string_draw positions. "Continue
  // building this city": 6:5 black at (8, 47), cream 0x7F9A at (7, 46). A time limit: the box (1, 40, 230, 20) ANDed
  // with 0x1FE3 (FUN_00509B90; gl.js andRect), 6:2 + the months (number_text_draw '@', at the pen + 7) black at
  // x 7..8 / y 45, 47, then red 0xF800 at (7, 46). Survival: the box (1, 42, 200, 18), 6:3 red at (2, 46), the months
  // at the pen + 2, no shadow.
  function drawTopLeft(R) {
    const T = D && D.top_left;
    if (!T || screen()) return;
    const F = "SPR_FONTS", line = (id, n, x, y, color) => {
      const s = t(6, id);
      uiText(s, x, y, F, { color });
      // the pen (0x00F13A70) restarts at 0 before each text: the number at x + the text's cursor
      if (n != null) uiText(ZText.numberText(n), x + ZText.draw(null, F, s, 0, 0).cursor, y, F, { color });
    };
    if (T.won) { line(5, null, 8, 47, 0); line(5, null, 7, 46, 0x7F9A); }
    if (!T.kind) return;
    const [bx, by, bw, bh] = T.kind === "limit" ? [1, 40, 230, 20] : [1, 42, 200, 18];
    uiFlushText();                                  // what is queued so far is under the box
    UIX.cuts.push({ at: UIX.batch.n, draw: () => R.andRect(bx, by, bw, bh, 0x1FE3, UIX.scale) });
    if (T.kind === "limit") {
      for (const x of [7, 8]) for (const y of [45, 47]) line(2, T.months, x, y, 0);
      line(2, T.months, 7, 46, 0xF800);
    } else line(3, T.months, 2, 46, 0xF800);
  }
  // right clicks: the confirm closes; the campaign screens take none (FUN_0052BE10 for 0x42 / 0x43)
  function rightClick() {
    if (dlg) { dlg = null; return true; }
    if (screen() === "tutorial") { act({ op: "briefed" }); return true; }   // 0x3B: a right click closes it (13:3)
    return !!screen();
  }
  window.addEventListener("wheel", e => {
    if (!screen() || !window.Lists) return;
    e.preventDefault(); e.stopPropagation();
    const st = screen() === "briefing" ? NewGame.brief : Lists.brief, n = Math.sign(e.deltaY) * Math.max(1, Math.round(Math.abs(e.deltaY) / 120)) * 3;
    st.scroll = Math.max(0, Math.min(st.range, st.scroll + n));
  }, { capture: true, passive: false });

  const startTutorial = (id) => act({ op: "start", adventure: id }, true);   // the tutorial buttons (lists.js)
  return { meta, refresh, draw, drawTopLeft, startTutorial, isOpen, active, rightClick, rowClick, replay: () => act({ op: "replay" }, true),
           state: () => D, screen, confirmOpen: () => !!dlg };
})();
window.Campaign = Campaign;
