// New game (File > New adventure, and the campaign screens' New Adventure): the exe's way into a city (oracle
// re/oracle/scenarios/newgame-flow.txt, newgame-adventures.txt, newgame-openplay.txt, 1L-europa1.txt at 800x600;
// docs/play/screens.md "New game", docs/play/campaign.md):
//  0. the front end on a browser's first open (no leader name stored; boot()): the main menu (screen 0) and the
//     leader-name screen (0x36); Return to Roster comes back to the leader-name screen (user 11-01);
//  1. the family menu (screen 0x30, FUN_004FDC80 / FUN_004FDD50): Adventures, Custom Adventures, Tutorials, Return,
//     the Zeus logo and the leader's name;
//  2. the Adventures window: the family's adventures (GET /adventures.json: sim/campaign flow.adventures, the
//     open plays of data/maps.json in their places), the chosen one's name and description, Begin Adventure;
//     a tutorial starts at once from its Adventures/tutorialNN.sav, on its goals screen (campaign.js "tutorial");
//  3. the episode start (briefing, screen 0x35: FUN_0052E520): title, episode, the goals (or "Open Play, no
//     episode goals"), the briefing with its scrollbar, the difficulty (153:d+1, arrows) and "To the city": a map
//     starts as before (POST /control {new, map, difficulty}), an adventure through the campaign module (POST
//     /campaign {op: "start"}). campaign.js draws the same screen between episodes (NewGame.intro).
// The full-screen pictures behind them: ui.js uiBackdrop. The leader name: localStorage "zeus-leader" (ours: one
// leader per browser and server origin; the exe keeps a roster of players), posted to the server (/control
// {player}) for the texts that name the player (sim/messages.py PLAYER).
"use strict";

const NewGame = (() => {
  let cur = null;          // {stage: "family"|"list"|"intro", family, lists, sel, diff, busy, msg, scroll}
  const t = (g, i) => (window.Options ? Options.text(g, i) : "");
  const ct = (g, i) => (cur && cur.texts && cur.texts[g] && cur.texts[g][i]) || t(g, i);
  const ox = () => Math.trunc((UIX.W - 640) / 2), oy = () => Math.trunc((UIX.H - 480) / 2);
  const rec = (n) => { const H = window.Help && Help.data(); return (H && n >= 0 && H.records[n]) || null; };
  const UP = 332, DOWN = 336, CANCEL = 328, PROCEED = 268, SUP = 576, SDOWN = 578, BAR = 205;
  const brief = { scroll: 0, range: 0, key: null, lay: null };

  // the three lists: the exe's Adventures (Zeus campaigns by .pak name; Open Play Sandbox = data/maps.json
  // "sandbox"), Custom Adventures (the Zeus adventure folders; Open Play Sandbox 2 = "sandbox2"; then ours), Tutorials
  function build(d) {
    const maps = d.maps || [], map = (k) => maps.find(m => m.key === k);
    const asMap = { open_play_sandbox: "sandbox", open_play_sandbox_2: "sandbox2" };
    const row = (a) => asMap[a.id] && map(asMap[a.id]) ? Object.assign({ map: map(asMap[a.id]) }, a, { why: "" }) : a;
    const custom = d.custom.map(row).concat(maps.filter(m => m.ours).map(m => ({ map: m, name: m.name, ours: true, why: "" })));
    return { adventures: d.adventures.map(row), custom, tutorials: d.tutorials };
  }

  const LEADER = "zeus-leader";
  function leader() { try { return localStorage.getItem(LEADER) || ""; } catch (e) { return ""; } }
  function tellServer(name) {
    fetch("/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ player: name }) })
      .catch(() => {});
  }
  // page load: a stored leader goes straight to the city (its name to the server); none: the main menu (user 11-01)
  function boot() {
    const n = leader();
    if (n) tellServer(n); else open("main");
  }

  async function open(stage = "family") {
    if (window.Options) Options.load();
    cur = { stage, family: "adventures", lists: { adventures: [], custom: [], tutorials: [] }, sel: 0, diff: 2,
            busy: false, msg: "", scroll: 0, name: leader(), dlg: false };
    if (window.Help) await Help.ensure();
    try { cur.lists = build(await getJSON("/adventures.json")); } catch (e) { cur.msg = "server unreachable"; }
    try { cur.texts = (await getJSON("/data/campaign/texts.json")).groups; } catch (e) { cur.texts = null; }
    UIX.info = null; UIX.submenu = null;
  }
  const close = () => { cur = null; };
  const isOpen = () => !!cur;
  const items = () => (cur ? cur.lists[cur.family] || [] : []);

  // an entry's texts: list row, name, description, episode title, briefing, goal rows
  function texts(e) {
    if (e.map) {                                    // an open play map (data/maps.json)
      const m = e.map, a = rec(m.adventure), ep = rec(m.episode);
      const T = { row: e.name || (a ? a[13] : m.title || m.key), name: a ? a[13] : m.title || m.key,
                  intro: a ? a[15] : m.intro || "", ep: ep ? ep[13] : m.episode_title || "",
                  brief: ep ? ep[15] : m.episode_text || "", goals: [] };
      if (m.ours) Object.assign(T, { row: m.name, name: m.name, intro: m.note + " @P " + T.intro, brief: m.note + " @P " + T.brief });
      return T;
    }
    const a = rec(e.brief), ep = rec(e.intro), s = e.strings || {};      // s: a custom adventure's .txt texts
    const tut = cur && cur.family === "tutorials" ? ct(333, e.index) : "";
    return { row: tut || e.name, name: a ? a[13] : s.title || e.name,
             intro: (e.why ? "(" + e.why + ") @P " : "") + (a ? a[15] : s.desc || ""),
             ep: ep ? ep[13] : s.ep_title || "", brief: ep ? ep[15] : s.ep_body || "", goals: e.goals || [], voice: e.voice, jingle: e.jingle };
  }

  // the front-end button tables (28-byte widgets: x1, y1, x2, y2 on the 800 x 600 screen, drawn at + (ox - 0x50,
  // oy - 0x3C)): button_bar_draw 0x0059ED50 style 6 = SPR_PANELING 205.. (x2 - x1) / 16 tiles, + 3 hovered; the label
  // 11C (font rank 1) centred in the given width at + (dx, 6) (FUN_00509320: dx 0, width x2 - x1; FUN_00509470:
  // the tutorials' dx 15 / 13, width x2 - x1 + 1)
  function bar(x, y, cells, label, fn, dx = 0, w = 16 * cells) {
    const hov = uiHover(x, y, 16 * cells, 25);
    for (let c = 0; c < cells; c++) uiPut(sprite("Zeus_Interface", BAR + (hov ? 3 : 0) + (c === 0 ? 0 : c === cells - 1 ? 2 : 1)), x + 16 * c, y);
    uiText(label, x + dx, y + 6, "SPR_FONTS_11C", { center: w });
    UIX.hits.push([x, y, 16 * cells, 25, fn, label]);
  }
  const tx = (x) => x + ox() - 0x50, ty = (y) => y + oy() - 0x3C;      // table coords -> interface px

  // the animated logo (FUN_005860F0): packed 0x6A8B Zeus (PoseidonImps group 138, 4 frames) / 0x6A8A Poseidon
  // (group 137, 3 frames) by sprite_anim_step 0x005AF8C0: the first image's speed byte 10 = 200 ms a frame; top-left
  function logo(x, y, poseidon) {
    const g = poseidon ? "group_137" : "group_138", n = poseidon ? 3 : 4;
    uiPut(groupSprite("PoseidonImps", g, Math.floor(performance.now() / 200) % n), x, y);
  }

  // 0. the main menu, screen 0 (FUN_005900B0: picture 0x11 Poseidon_FE_MainMenu; FUN_00420240: the logos, Zeus at
  // (ox + 0x46, oy - 0x3C), Poseidon at (ox + 0x1B8, oy - 0x30), the five buttons of table 0x005EB840, labels 30:0..4;
  // clicks FUN_00420120). Ours: Play Poseidon only while Poseidon is on (it is off: a toast), the editor and the
  // website are not ported (a toast), Quit closes the menus onto the city the server runs (a browser tab cannot quit).
  const MAIN = [[93, 90, 349], [453, 90, 709], [521, 374, 777], [117, 278, 373], [28, 516, 284]];
  function drawMain() {
    logo(ox() + 0x1B8, oy() - 0x30, true);
    logo(ox() + 0x46, oy() - 0x3C, false);
    const say = (m) => () => { if (typeof toast === "function") toast(m); };
    const fns = [() => { cur.stage = "leader"; }, say("Poseidon is off (ours: Options, or `poseidon on` on the server)"),
                 say("Not in the browser version (ours)"), say("The Adventure Editor is not ported (ours)"), close];
    MAIN.forEach(([x1, y1, x2], i) => bar(tx(x1), ty(y1), (x2 - x1) >> 4, ct(30, i), fns[i]));
  }

  // 0. the leader-name screen 0x36 (FUN_00590150: picture 5 Zeus_FE_Registry; FUN_005901B0 + the proceed widget
  // 0x005E9EC0 at (ox + 0x1D0, oy + 0xF9)): titled frame (ox + 0x80, oy + 0xA0) 24 x 8, 31:0 22C centred in 0x180 at
  // y + 0xAC; 13:5 "Continue" 11C at (ox + 0x17E, oy + 0xFF); the Choose name box (window_highlight_draw 25 x 25 at
  // (ox + 0x127, oy + 0xF6)) and 13:8 centred in 0xB4 at (ox + 0x91, oy + 0x100); the name field: plain inset
  // (ox + 0xA0, oy + 0xD0) 20 x 2, the name 11C2 at (ox + 0xB0, oy + 0xD8), the cursor (FUN_0059FD60: 200 ms hidden,
  // 400 ms shown) 4 x 2 white under the pen. Input 1 (FUN_005084E0(1, name, 0x1F, 0x68, ...)): a key is refused
  // at 31 characters or when the name is 104 px wide in SPR_FONTS (FUN_005080A0). Proceed with no name: the 0x3F
  // popup 5:0x5E "No Leader" (FUN_005863D0). Ours: the name field starts with the stored name (the exe: empty);
  // Choose name (the exe's roster of saved players, screen 0x2F) is not ported.
  function drawLeader() {
    const X = ox(), Y = oy(), c = cur;
    uiFrame("titled", X + 0x80, Y + 0xA0, 24, 8);
    uiText(ct(31, 0), X + 0x80, Y + 0xAC, "SPR_FONTS_22C", { center: 0x180 });
    uiText(ct(13, 5), X + 0x17E, Y + 0xFF, "SPR_FONTS_11C");
    if (window.Options) Options.rims(X + 0x127, Y + 0xF6, 25, 25, uiHover(X + 0x127, Y + 0xF6, 25, 25));
    uiText(ct(13, 8), X + 0x91, Y + 0x100, "SPR_FONTS_11C", { center: 0xB4 });
    uiFrame("plain", X + 0xA0, Y + 0xD0, 20, 2);
    uiText(c.name, X + 0xB0, Y + 0xD8, "SPR_FONTS_11C2");
    if (performance.now() % 600 >= 200) {
      const cx = X + 0xB0 + (c.name && window.ZText ? ZText.advance("SPR_FONTS_11C2", c.name) : 0);
      uiPut(UIX.white, cx, Y + 0xD8 + 0xF, 1, 4, 2);
    }
    const px = X + 0x1D0, py = Y + 0xF9;
    uiPut(sprite("Zeus_Interface", PROCEED + (uiHover(px, py, 24, 24) ? 1 : 0)), px, py);
    UIX.hits.push([px, py, 24, 24, leaderGo, ct(13, 5)]);
    if (c.dlg) noLeader();
  }
  function leaderGo() {
    const n = cur.name.trim();
    if (!n) { cur.dlg = true; return; }
    try { localStorage.setItem(LEADER, n); } catch (e) { }
    tellServer(n);
    cur.name = n; cur.stage = "family";
  }
  // the 0x3F popup with one button (FUN_00432380(0x5E, ..., 1): titled frame 30 x 10 at (ox + 0x50, oy + 0x50), 5:0x5E
  // 22C centred in 0x1E0 at y + 0x14, 5:0x5F 11C at y + 0x3C, the OK widget of table 0x005EF938 (324) at (256, 100))
  function noLeader() {
    const cx = ox() + 0x50, cy = oy() + 0x50, ok = () => { cur.dlg = false; };
    uiFlushText();                                  // the screen's texts under the popup
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    uiFrame("titled", cx, cy, 30, 10);
    uiText(t(5, 0x5E), cx, cy + 0x14, "SPR_FONTS_22C", { center: 0x1E0 });
    uiText(t(5, 0x5F), cx, cy + 0x3C, "SPR_FONTS_11C", { center: 0x1E0 });
    const hov = uiHover(cx + 256, cy + 100, 34, 34);
    uiPut(sprite("Zeus_Interface", 324 + (hov ? 1 : 0)), cx + 256, cy + 100);
    UIX.hits.push([cx + 256, cy + 100, 34, 34, ok, "OK"]);
  }
  // the keyboard on the leader-name screen (the exe's WM_CHAR into input 1; Enter = Continue, Esc closes the popup)
  function key(e) {
    if (!cur || cur.stage !== "leader") return false;
    const c = cur;
    if (c.dlg) { if (e.key === "Enter" || e.key === "Escape") c.dlg = false; e.preventDefault(); return true; }
    if (e.key === "Enter") leaderGo();
    else if (e.key === "Backspace") c.name = c.name.slice(0, -1);
    else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && e.key.charCodeAt(0) >= 0x20 && e.key.charCodeAt(0) < 0x100) {
      const fits = !window.ZText || ZText.measure("SPR_FONTS", c.name) < 0x68;
      if (c.name.length < 0x1F && fits) c.name += e.key;
    }
    e.preventDefault();
    return true;
  }

  // 1. the family menu, screen 0x30 (FUN_004FDC80: picture 1 Zeus_FE_ChooseGame, 293:7 "[player_name]" 22C (rank 6)
  // centred in 0x13C at (ox + 0xA2, oy - 0x1C); FUN_004FDD50 the buttons of table 0x0063B858; screen_draw: the logo
  // at (ox - 0x41, oy - 0x2D)). Not drawn (ours): Resume Adventure (0) and Load Saved Adventure (3), the roster's saved
  // adventures; Play Tutorial (QA) (2) is off in the shipped game.
  function drawFamily() {
    const go = (f) => () => { cur.family = f; cur.stage = "list"; cur.sel = 0; cur.scroll = 0; };
    logo(ox() - 0x41, oy() - 0x2D, false);
    uiText(cur.name || leader(), ox() + 0xA2, oy() - 0x1C, "SPR_FONTS_22C", { center: 0x13C });
    bar(tx(480), ty(248), 14, ct(293, 9), go("adventures"));
    bar(tx(480), ty(277), 14, ct(293, 5), go("custom"));
    bar(tx(533), ty(512), 14, ct(293, 1), go("tutorials"));
    bar(tx(12), ty(542), 14, ct(293, 6), () => { cur.name = leader(); cur.stage = "leader"; });
    if (cur.msg) uiText(cur.msg, ox() + 400, oy() + 260, "SPR_FONTS_11C");
  }

  // 2. the tutorials, screen 2 (FUN_005BE830: picture 0x14 Zeus_FE_tutorials, whose blue / magenta slots the buttons
  // cover; FUN_005BE860): 293:11 / 293:12 (11C) centred in 0x128 at (ox - 0x10 / ox + 0x168, oy + 5); Exit tutorial
  // (table 0x0065C328, 293:13); 8 + 8 tutorials (tables 0x0065C348 / 0x0065C428: (85 / 460, 108 + 51 i) 16 tiles,
  // the names 333:(8 col + i) at + (15 / 13, 6) centred in 257). Clicks (FUN_005BE720): a tutorial -> FUN_005BECC0
  // (col, i): its save at once (tutorial_load_save), on its goals screen; Exit -> FUN_004FDEF0, the family menu.
  function drawTutorials() {
    const c = cur, L = items();
    uiText(ct(293, 11), ox() - 0x10, oy() + 5, "SPR_FONTS_11C", { center: 0x128 });
    uiText(ct(293, 12), ox() + 0x168, oy() + 5, "SPR_FONTS_11C", { center: 0x128 });
    bar(tx(12), ty(561), 14, ct(293, 13), () => { c.stage = "family"; });
    for (let col = 0; col < 2; col++) for (let i = 0; i < 8; i++) {
      const k = 8 * col + i, e = L.find(r => r.index === k) || L[k];
      bar(tx(col ? 460 : 85), ty(108 + 51 * i), 16, ct(333, k), () => {
        if (!e) return;
        c.sel = L.indexOf(e);
        start();
      }, col ? 13 : 15, 257);
    }
    if (c.msg) uiText(c.msg, ox() - 64, oy() + 470, "SPR_FONTS_11C");
  }

  // 2. the Adventures window (measured): 13 rows, the arrows step the list (ours: the exe's track not drawn)
  function drawList() {
    const X = ox() - 72, Y = oy() + 32, c = cur, L = items();
    uiFrame("titled", X, Y, 22, 24);
    uiText(c.family === "tutorials" ? ct(293, 1) : c.family === "custom" ? ct(293, 5) : t(293, 9), X + 8, Y + 16, "SPR_FONTS_22C", { center: 336 });
    uiText(t(287, 5), X + 24, Y + 50, "SPR_FONTS_9LTBK");
    uiFrame("plain", X + 24, Y + 60, 17, 13);
    c.scroll = Math.max(0, Math.min(c.scroll, L.length - 13));
    L.slice(c.scroll, c.scroll + 13).forEach((e, k) => {
      const i = c.scroll + k, y = Y + 66 + 16 * k, hov = uiHover(X + 28, y, 264, 16), T = texts(e);
      // a row that cannot start: the list font of a disabled row (ours: 11CB, as the unchosen rows)
      uiText(T.row, X + 38, y, i === c.sel && !e.why ? "SPR_FONTS_11C2" : "SPR_FONTS_11CB");
      UIX.hits.push([X + 28, y, 264, 16, () => { c.sel = i; c.diff = e.map ? e.map.difficulty : 2; }, ""]);
      if (hov) UIX.hoverName = T.row;
    });
    const step = (d) => () => { c.scroll = Math.max(0, Math.min(L.length - 13, c.scroll + d)); };
    uiPut(sprite("Zeus_Interface", UP), X + 298, Y + 60);
    uiPut(sprite("Zeus_Interface", DOWN), X + 298, Y + 242);
    UIX.hits.push([X + 298, Y + 60, 26, 26, step(-1), "up"]);
    UIX.hits.push([X + 298, Y + 242, 26, 26, step(1), "down"]);
    uiFrame("plain", X + 300, Y + 92, 2, 9);
    const bx = X + 18, by = Y + 340, px = X + 296, py = Y + 340;
    uiPut(sprite("Zeus_Interface", CANCEL + (uiHover(bx, by, 34, 22) ? 1 : 0)), bx, by);
    UIX.hits.push([bx, by, 34, 22, () => { c.stage = "family"; }, "Cancel"]);
    uiText(t(287, 6), X + 156, Y + 346, "SPR_FONTS_11C");
    uiPut(sprite("Zeus_Interface", PROCEED + (uiHover(px, py, 24, 24) ? 1 : 0)), px, py);
    const begin = () => {
      const e = L[c.sel];
      if (!e) return;
      if (e.why) { c.msg = e.why; return; }
      // a tutorial starts from its save at once, on its goals screen (FUN_005BECC0 -> tutorial_load_save 0x005BEBD0;
      // oracle 1L5-tut00 start.bmp): no briefing
      if (c.family === "tutorials") return start();
      c.stage = "intro"; c.msg = ""; c.diff = e.map ? e.map.difficulty : 2; brief.key = null;
    };
    UIX.hits.push([X + 150, py, 172, 24, begin, t(287, 6)]);
    // the picture window (FUN_004248F0: the chosen adventure's picture, table 0x005EBBD8 by its header's picture
    // field, at (ox + 0x126, oy - 0x23); its frame measured on newgame-openplay b1) and the description window
    const e = L[c.sel];
    const DX = ox() + 284, DY = oy() + 290;
    frameBox(DX, oy() - 45, 419, 320, 0, 0, 0, 0);
    const pic = e ? picture(e.picture || 0) : null;
    if (pic) uiPut(pic, ox() + 0x126, oy() - 0x23);
    frameBox(DX, DY + 1, 419, 232, DX + 11, DY + 12, 396, 212);      // ring 364..782 x 351..582 (b1)
    if (e) {
      const T = texts(e);
      uiText(T.name, DX + 10, DY + 35, "SPR_FONTS_11C3", { center: 400 });
      ZText.wrap("SPR_FONTS_11C2", T.intro.replace(/@[PL]/g, " ").trim(), 384)
        .forEach((ln, i) => uiText(ln.trim(), DX + 20, DY + 58 + 16 * i, "SPR_FONTS_11C2"));
    }
    if (c.msg) uiText(c.msg, X + 24, Y + 300, "SPR_FONTS_11C", { width: 300 });
  }

  // table 0x005EBBD8 (index = the adventure header's picture, +0xCC29C): 0 the open plays' and custom adventures'
  // picture, 1..8 the Zeus campaigns' and the tutorials' (Zeus_Interface SPR_CAMPAIGN_*), 9..14 Poseidon's
  // (Poseidon_Loaded SPR_POS_CAMP1..6). Matched: 0 GENERIC (newgame-openplay b1), 6 ZEUS (1L-europa1 s32); the rest
  // by the groups' names and order.
  const PICS = ["GENERIC", "HERCULE", "JASON", "PERSEUS_MEDUSA", "TROJAN_WAR", "ATHENS", "ZEUS", "PELOPONNESIAN_WAR",
                "TUTORIAL"];
  function picture(n) {
    if (n < PICS.length) return groupSprite("Zeus_Interface", "SPR_CAMPAIGN_" + PICS[n]);
    return groupSprite("Poseidon_Loaded", "SPR_POS_CAMP" + (n - 8));
  }

  // the description box (measured): the titled ring with a dark (plain-fill) inside and a plain inset of any pixel
  // size, its last column / row pulled back to the size (as the RIMS highlight does)
  function frameBox(X, Y, W, H, x, y, w, h) {
    const first = UIX.D.frames.plain.sprite_group.index, I = (k) => sprite("Zeus_Interface", first + k);
    const tf = UIX.D.frames.titled.sprite_group.index, TI = (k) => sprite("Zeus_Interface", tf + k);
    const tc = Math.ceil(W / 16), tr = Math.ceil(H / 16);    // the titled ring, last column / row pulled back
    for (let r = 0; r < tr; r++) for (let c = 0; c < tc; c++) {
      const lc = c === tc - 1, lr = r === tr - 1, k = r === 0 ? (c === 0 ? 0 : lc ? 11 : 1 + (c - 1) % 10)
        : lr ? (c === 0 ? 132 : lc ? 143 : 0x85 + (c - 1) % 10) : (c === 0 ? 0xC : lc ? 0x17 : -1);
      if (k >= 0) uiPut(TI(k), lc ? X + W - 16 : X + 16 * c, lr ? Y + H - 16 : Y + 16 * r);
    }
    const inner = [X + 8, Y + 8, X + W - 8, Y + H - 8];
    for (let r = 0; r * 16 < H; r++) for (let c = 0; c * 16 < W; c++) uiPutClip(I(8 + (c % 5) + ((r * 7) % 35)), X + 16 * c, Y + 16 * r, inner);
    const nc = Math.ceil(w / 16), nr = Math.ceil(h / 16);
    for (let r = 0; r < nr; r++) for (let c = 0; c < nc; c++) {
      const lc = c === nc - 1, lr = r === nr - 1, k = r === 0 ? (c === 0 ? 0 : lc ? 6 : 1 + (c - 1) % 5)
        : lr ? (c === 0 ? 42 : lc ? 48 : 0x2B + (c - 1) % 5) : (c === 0 ? 7 : lc ? 0xD : -1);
      if (k >= 0) uiPut(I(k), lc ? x + w - 16 : x + 16 * c, lr ? y + h - 16 : y + 16 * r);
    }
  }

  // 3. the episode start, screen 0x35 (FUN_0052E520; shots 1L-europa1 s40, 1L-europa-colony g87 / h146):
  // titled frame (ox, oy) 40 x 29; the adventure title 22C centred in 640 at y + 10; the episode title 11C at
  // (x + 16, y + 0x2A); marble bar 39 tiles at (x + 8, y + 0x36); 44:276 "Goal" at (x + 51, y + 0x40); the goals box
  // plain (x + 16, y + 0x4C) 38 x B, B = (max(n,1)*20 + 19) / 16 + 1; no goals: 44:280; each goal: the empty tick box
  // (607 + 1) at (x + 0x1B, y + 84 + 20i + 3) and its text (11C2) at (x + 51, y + 90 + 20i); the briefing as
  // objectives_screen_draw's body (top y + 16B + 104, 0x188 - 16B high, 0x280 wide: 36 columns + scrollbar, else 38);
  // 44:219 + 153:(d+1) at (x + 0x96, y + 0x1AB), arrows (table 0x005EF988) at (x + 0x6E, y + 0x1A6), 62:5 at
  // (x + 0x1D2, y + 0x1AB), proceed (0x005E9EC0) at (x + 0x234, y + 0x1A4).
  // o = {name, ep, brief, briefKey, goals: [{goal}], diff, setDiff(d), go(), msg}
  function intro(o) {
    const X = ox(), Y = oy(), W = 640;
    uiFrame("titled", X, Y, 40, 29);
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    uiText(o.name, X, Y + 10, "SPR_FONTS_22C", { center: W });
    uiText(o.ep, X + 16, Y + 0x2A, "SPR_FONTS_11C");
    for (let i = 0; i < 39; i++) uiPut(sprite("Zeus_Interface", 604 + (i === 0 ? 0 : i < 38 ? 1 : 2)), X + 8 + 16 * i, Y + 0x36);
    uiText(t(44, 276), X + 51, Y + 0x40, "SPR_FONTS_11C");
    const n = o.goals.length, B = Math.trunc((Math.max(n, 1) * 20 + 19) / 16) + 1;
    uiFrame("plain", X + 16, Y + 0x4C, 38, B);
    if (!n) uiText(t(44, 280), X + 9, Y + 0x5A, "SPR_FONTS_11C2", { center: 608 });
    o.goals.forEach((r, i) => {
      uiPut(sprite("Zeus_Interface", 608), X + 0x1B, Y + 84 + 20 * i + 3);
      uiText(r.goal, X + 51, Y + 90 + 20 * i, "SPR_FONTS_11C2");
    });
    const top = Y + 16 * B + 0x48, T = top + 0x20, R = Math.trunc((0x188 - 16 * B) / 16) - 4 - 1;
    Lists.textBox(brief, o.briefKey + ":" + UIX.W + ":" + UIX.H, o.brief, X + 16, T, 0x280 / 16 - 4, R);
    // difficulty: up / down (small arrows, held = pressed look), 44:219 + 153:(d+1); To the city 62:5 + proceed
    const ay = Y + 422, held = (x) => UIX.down && uiHover(x, ay, 16, 16);
    uiPut(sprite("Zeus_Interface", SUP + (held(X + 110) ? 1 : 0)), X + 110, ay);      // table 0x005EF988: (0, 0), (17, 0)
    uiPut(sprite("Zeus_Interface", SDOWN + (held(X + 127) ? 1 : 0)), X + 127, ay);
    if (o.setDiff) {
      UIX.hits.push([X + 110, ay, 17, 16, () => o.setDiff(Math.min(4, o.diff + 1)), "up"]);
      UIX.hits.push([X + 127, ay, 16, 16, () => o.setDiff(Math.max(0, o.diff - 1)), "down"]);
    }
    const dl = t(44, 219);
    uiText(dl, X + 150, Y + 427, "SPR_FONTS_11C");
    if (o.diff != null) uiText(t(153, o.diff + 1), X + 150 + ZText.advance("SPR_FONTS_11C", dl) + 6, Y + 427, "SPR_FONTS_11C");
    uiText(t(62, 5), X + 466, Y + 427, "SPR_FONTS_11C");
    const px = X + 564, py = Y + 420;
    uiPut(sprite("Zeus_Interface", PROCEED + (uiHover(px, py, 24, 24) ? 1 : 0)), px, py);
    UIX.hits.push([X + 460, py, 140, 24, o.go, t(62, 5)]);
    if (o.msg) uiText(o.msg, X + 16, Y + 404, "SPR_FONTS_11C");
  }

  function drawIntro() {
    const c = cur, e = items()[c.sel], T = texts(e);
    if (T.voice && c.voiced !== T.voice && typeof audio !== "undefined" && audio && audio.ctx) {         // the episode's spoken intro + jingle (sim/campaign flow.voices)
      c.voiced = T.voice;
      if (typeof audio !== "undefined" && audio) audio.screenSound(T.voice, T.jingle);
    }
    intro({ name: T.name, ep: T.ep, brief: T.brief, briefKey: c.family + ":" + c.sel, goals: T.goals, diff: c.diff,
            setDiff: (d) => { c.diff = d; }, go: start, msg: c.msg });
  }

  const DIFF = ["VeryEasy", "Easy", "Normal", "Hard", "Impossible"];      // g_difficulty order (sim/data.py)
  async function post(url, body) {
    try {
      return await (await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body), signal: AbortSignal.timeout(60000) })).json();
    } catch (e) { return { ok: false, out: "server unreachable" }; }
  }
  async function start() {
    const c = cur;
    if (!c || c.busy) return;
    const e = items()[c.sel];
    c.busy = true;
    Loading.start();
    // a campaign starts on its briefing (flow.screen "briefing"): the same screen, so it is "briefed" at once
    const tut = c.family === "tutorials";            // the save's own difficulty; its goals screen comes up (flow)
    const r = e.map ? await post("/control", { new: true, map: e.map.key, difficulty: DIFF[c.diff] })
                    : await post("/campaign", tut ? { op: "start", adventure: e.id } : { op: "start", adventure: e.id, difficulty: DIFF[c.diff] });
    if (r.ok && !e.map && !tut) await post("/campaign", { op: "briefed" });
    c.busy = false;
    if (!r.ok) { Loading.end(); c.msg = r.out || "failed"; return; }
    close();
    UIX.info = null;
    if (window.Campaign) Campaign.refresh();
    if (typeof resetPlayback === "function") resetPlayback();
  }

  function draw() {
    if (!cur) return;
    if (window.Balloon) Balloon.none();
    UIX.hits.push([0, 0, UIX.W, UIX.H, null, ""]);
    // the full-screen pictures (FUN_00505310): family menu 0x11, lists 0x12 / tutorials 0x14 (1L-tutlist list),
    // episode start 0x13 (ui.js uiBackdrop)
    uiBackdrop(cur.stage === "main" ? "mainmenu" : cur.stage === "leader" ? "registry"
               : cur.stage === "family" ? "family" : cur.stage === "intro" ? "briefing"
               : cur.family === "tutorials" ? "tutorials" : "adventures");
    if (cur.stage === "main") drawMain();
    else if (cur.stage === "leader") drawLeader();
    else if (cur.stage === "family") drawFamily();
    else if (cur.stage === "list") (cur.family === "tutorials" ? drawTutorials : drawList)();
    else if (items()[cur.sel]) drawIntro();
  }
  // a right click goes back a step (ours)
  function rightClick() {
    if (!cur) return false;
    if (cur.stage === "intro") cur.stage = "list"; else if (cur.stage === "list") cur.stage = "family";
    else if (cur.stage === "leader") { if (cur.dlg) cur.dlg = false; else cur.stage = "main"; }
    else close();
    return true;
  }
  return { open, close, isOpen, draw, rightClick, intro, brief, boot, key, leader, state: () => cur };
})();
window.NewGame = NewGame;
