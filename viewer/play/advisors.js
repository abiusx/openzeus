// The advisor screens (screen 7; docs/play/advisors.md). Opened by the control panel's magnifier (advisor of the
// current page, exe table 0x0063E488); while one is open the page buttons switch advisor (FUN_00516D50), the map
// takes no clicks, a right click or the exit button closes it (screen_draw / input case 7).
// Data: /data/play/advisors.json (tools/play_advisors.py: frames, strings, the labor advisor's layout and tables)
// and the server's /advisor.json?a=N. All eleven advisors of the exe's table: labor (1), military (2), trade (6),
// population (7), hygiene (8), husbandry (9), culture (10), mythology (11), finance (12), overview (13), aesthetics (15).
// Presentation only: priorities and industry shut-downs are sim commands (priority CAT N, industry GOOD on|off).
"use strict";

const Advisors = (() => {
  let D = null, loading = false;
  let cur = 0, data = null, fetching = false, lastSeq = -1, lastFetch = 0, press = null;
  const CATS = ["husbandry", "industry", "storage", "hygiene", "admin", "culture", "mythology", "military"];
  const txt = (g, i) => { const t = D && D.texts[String(g)]; return (t && t[i]) || ""; };

  async function load() {
    if (D || loading) return;
    loading = true;
    try { D = await getJSON("/data/play/advisors.json"); } catch (e) { console.warn("advisors.json", e); }
    loading = false;
  }

  async function refresh(force) {
    if (!cur || fetching) return;
    if (!force && P.stateSeq === lastSeq && performance.now() - lastFetch < 2000) return;
    fetching = true;
    const a = cur, seq = P.stateSeq;
    try { const d = await getJSON(`/advisor.json?a=${a}`); if (a === cur) { data = d; lastSeq = seq; lastFetch = performance.now(); } }
    catch (e) { }
    fetching = false;
  }

  function advisorOfPage(page) { if (!D) load(); return D ? D.page_advisor[page] || 0 : 0; }   // lazy: getJSON is play.js's
  function has(page) {                        // FUN_00517580: no magnifier on Aesthetics outside Poseidon
    const a = advisorOfPage(page);
    return !!a && !(page === 9 && !(P.f0 && P.f0.poseidon));
  }
  function open(a) { if (!D || !D.advisors[String(a)]) return false; cur = a; data = null; refresh(true); return true; }
  function openPage(page) { return has(page) && open(advisorOfPage(page)); }
  function close() { cur = 0; data = null; press = null; more = null; }
  function isOpen() { return !!cur; }

  function frame() {                         // ((W-640)/2 + dx, (H-480)/2 + dy): the exe's 640x480 origin 0x00F2A6AC/A8
    const [dx, dy, cols, r0] = D.advisors[String(cur)].frame;
    const rows = cur === 11 && data && data.advisor === 11 ? mythRows(data) : r0;   // mythology: from its lists
    return { x: Math.trunc((UIX.W - 640) / 2) + dx, y: Math.trunc((UIX.H - 480) / 2) + dy, cols, rows };
  }

  async function cmd(line) {
    await sendCommands([line], { sound: false });
    refresh(true);
  }

  function draw() {
    if (!cur || !D) return;
    refresh(false);
    const f = frame(), { x, y, cols, rows } = f;
    uiFrame("titled", x, y, cols, rows);
    UIX.hits.push([x, y, 16 * cols, 16 * rows, null, ""]);       // the window swallows clicks
    if (cur === 1) drawLabor(f);
    else if (DRAW[cur]) { if (data && data.advisor === cur) DRAW[cur](f, data); else uiText(D.advisors[String(cur)].title_text, x + 15, y + 12, "SPR_FONTS_22C"); }
    else {
      const A = D.advisors[String(cur)];
      uiText(A.title_text, x + 15, y + 12, "SPR_FONTS_22C");        // position: the labor advisor's (ours for the rest)
      uiText("This advisor is not in play mode yet.", x + 32, y + 64, "SPR_FONTS_11C");
    }
    // help (0x005169F0) and exit (0x004066D0): draw table 0x005EF758 at (x, y + (rows-2)*16); exit x = cols*16-36
    const [hb, xb] = D.buttons, by = y + (rows - 2) * 16;
    uiWidget(hb, x, by, { name: "Help", onClick: () => Help.open(() => Help.pageHelp(UIX.page), 1) });   // 0x005169F0: the page's tab help
    uiWidget({ ...xb, rect: [cols * 16 - 36, xb.rect[1], xb.rect[2], xb.rect[3]] }, x, by, { name: "Exit", onClick: close });
    if (more && cur === 6) drawMore(f); else more = null;
  }

  function drawLabor({ x, y }) {
    const L = D.labor, T = (t) => txt(t[0], t[1]);
    uiText(T(L.title.text), x + L.title.pos[0], y + L.title.pos[1], L.title.font);
    for (const h of L.headers) uiText(T(h.text), x + h.pos[0], y + h.pos[1], h.font);
    uiFrame("plain", x + L.rows_inset.pos[0], y + L.rows_inset.pos[1], L.rows_inset.cols, L.rows_inset.rows);
    const ax = x + L.arrows_origin[0], ay = y + L.arrows_origin[1];
    const cats = data && data.cats;
    for (const a of L.arrows) {                 // image table 0x006434D0; the pressed image while held (+1)
      const [rx, ry, rw, rh] = a.rect, px = ax + rx, py = ay + ry;
      const held = press && press.row === a.row && press.dir === a.dir && UIX.down && uiHover(px, py, rw, rh);
      uiPut(sprite(a.sprite.file, a.sprite.index + (held ? 1 : 0)), px, py);
      UIX.hits.push([px, py, rw, rh, () => {
        press = { row: a.row, dir: a.dir };
        if (!cats) return;
        const p = cats[a.row].priority, n = a.dir === "up" ? Math.min(5, p + 1) : Math.max(0, p - 1);   // 0x00590580
        if (n !== p) { cats[a.row].priority = n; cmd(`priority ${CATS[a.row]} ${n}`); }
      }, a.dir === "up" ? "Raise priority" : "Lower priority", true]);       // held: repeats (ui.js uiRepeat)
    }
    for (let c = 0; c < 8; c++) {
      const dy = c * L.row_step, r = cats && cats[c];
      if (r) uiText(txt(L.priority.text_base[0], L.priority.text_base[1] + r.priority), x + L.priority.x, y + L.priority.y + dy,
                    L.priority.fonts[String(r.priority)]);
      uiText(txt(L.name.text_base[0], L.name.text_base[1] + c), x + L.name.x, y + L.name.y + dy, L.name.font);
      if (!r) continue;
      uiText(ZText.numberText(r.need), x + L.need.x, y + L.need.y + dy, L.need.font);
      uiText(ZText.numberText(r.have), x + L.have.x, y + L.have.y + dy, r.have !== r.need ? L.have.font_short : L.have.font);
    }
    uiText(T(L.industry_title.text), x + L.industry_title.pos[0], y + L.industry_title.pos[1], L.industry_title.font);
    uiText(T(L.industry_hint.text), x + L.industry_hint.pos[0], y + L.industry_hint.pos[1], L.industry_hint.font);
    const I = L.industry_inset;
    uiFrame("plain", x + I.pos[0], y + I.pos[1], I.cols, I.rows);
    if (!data || !data.industries) return;
    const ox = x + L.industry_origin[0], oy = y + L.industry_origin[1], R = L.industry_row;
    let k = 0;
    for (const ind of L.industries) {           // list order 0x00643470, shown while the city produces it, max 20
      if (k >= L.industry_max || !(ind.key in data.industries)) continue;
      const off = data.industries[ind.key], [l, t, r, b] = L.industry_rects[k];
      const ix = ox + l, iy = oy + t, ic = L.icons[String(ind.res)];
      if (ic) uiPut(sprite(ic.file, ic.index), ix, iy + 5);
      uiText(ind.name, ix + R.text_dx, iy + R.text_dy, R.name_font);
      uiText(txt(50, off ? R.status.off[1] : R.status.on[1]), ix + R.status_dx, iy + R.text_dy,
             off ? R.status.off_font : R.status.on_font);
      UIX.hits.push([ix, iy, r - l + 1, b - t + 1, () => {                    // FUN_00590660: toggle
        data.industries[ind.key] = !off;
        cmd(`industry ${ind.key} ${off ? "on" : "off"}`);
      }, ind.name]);
      k++;
    }
    if (!k) uiText(T(L.industry_none.text), x + L.industry_none.pos[0], y + L.industry_none.pos[1], L.industry_none.font,
                   { center: L.industry_none.center });
  }

  // --- advisors 8, 10, 12: layouts in advisors.json (tools/play_advisors.py), numbers from /advisor.json
  const pen = (font, s) => ZText.draw(() => {}, font, s, 0, 0).cursor;      // the exe's DAT_00F13A70 after a piece
  const T2 = (r) => txt(r[0], r[1]);
  const num = (n) => ZText.numberText(n);                                     // number_text_draw, '@' slot + " "
  function countLine(x, y, font, n, text, one) {                              // "<n> <noun>": number, then the noun at the pen
    const s = num(n);
    uiText(s, x, y, font);
    uiText(T2(n === 1 ? one : text), x + pen(font, s), y, font);
  }

  function drawHygiene({ x, y }, d) {                                         // FUN_00594080
    const L = D.hygiene, at = (e) => [x + e.pos[0], y + e.pos[1]];
    const pct = (v) => d.population ? Math.trunc(v * 100 / d.population) : 0;
    uiText(T2(L.title.text), ...at(L.title), L.title.font);
    uiText(txt(56, 24 + Math.trunc(d.health / 10)), ...at(L.health), d.health < L.health.low_below ? L.health.font_low : L.health.font);
    uiFrame("plain", ...at(L.inset1), L.inset1.cols, L.inset1.rows);
    uiText(txt(56, 35 + Math.trunc(pct(d.healer) / 10)), ...at(L.healer), L.healer.font);
    uiText(txt(56, d.fed ? 46 + Math.min(10, Math.max(1, Math.trunc(pct(d.fed) / 10))) : 46), ...at(L.food), L.food.font);
    uiText(T2(L.crises.text), ...at(L.crises), L.crises.font);
    const w5 = (n) => n === 0 ? 0 : n < 3 ? 1 : n < 6 ? 2 : n < 9 ? 3 : 4;    // FUN_00594000 / FUN_00594040
    uiText(txt(56, 58 + w5(d.plagues)), ...at(L.plague), L.plague.font);
    const [ix, iy] = at(L.infected), f = L.infected.font, pre = T2(L.infected.pre);
    uiText(pre, ix, iy, f);
    const nx = ix + pen(f, pre), ns = num(d.infected);
    uiText(ns, nx, iy, f);
    uiText(T2(d.infected === 1 ? L.infected.post_one : L.infected.post), nx + pen(f, ns), iy, f);
    uiText(T2(L.safety.text), ...at(L.safety), L.safety.font);
    uiFrame("plain", ...at(L.inset2), L.inset2.cols, L.inset2.rows);
    for (const k of ["maintenance", "watchposts"]) countLine(...at(L[k]), L[k].font, d[k], L[k].text, L[k].text_one);
    uiText(T2(L.crimes.text), ...at(L.crimes), L.crimes.font);
    for (const r of L.crime_rows) {
      const [cx, cy] = at(r), wd = txt(56, 80 + w5(d[r.key]));
      uiText(wd, cx, cy, L.crime_font);
      uiText(T2(r.text), cx + pen(L.crime_font, wd), cy, L.crime_font);
    }
  }

  function drawCulture({ x, y }, d) {                                         // FUN_00594B70
    const L = D.culture;
    uiText(T2(L.title.text), x + L.title.pos[0], y + L.title.pos[1], L.title.font);
    for (const h of L.headers) uiText(T2(h.text), x + h.pos[0], y + h.pos[1], h.font);
    uiFrame("plain", x + L.inset.pos[0], y + L.inset.pos[1], L.inset.cols, L.inset.rows);
    L.rows.forEach((r, c) => {
      const ry = y + L.row_y + c * L.row_step;
      countLine(x + L.row_x, ry, L.font, d.counts[r.key] || 0, r.text, r.text_one);
      if (!r.cov) return;
      const v = d.coverage[r.cov] || 0;
      let w = L.cov_words[0][1];
      for (const [lo, id] of L.cov_words) if (v >= lo) w = id;
      uiText(txt(58, w), x + L.cov_x, ry, L.font, { center: L.cov_w });
    });
  }

  function drawFinance({ x, y }, d) {                                         // finance_advisor_draw 0x005951F0
    const L = D.finance, f = L.font, [c0, c1] = L.cols;
    uiText(T2(L.title.text), x + L.title.pos[0], y + L.title.pos[1], L.title.font);
    for (const h of L.headers) uiText(T2(h.text), x + h.pos[0], y + h.pos[1], f);
    const row = (lx, ry, text, a, b) => {
      uiText(T2(text), x + lx, y + ry, f);
      if (a != null) uiText(num(a), x + c0, y + ry, f);
      if (b != null) uiText(num(b), x + c1, y + ry, f);
    };
    const rule = (ry) => { for (const [a, b] of L.rules) uiPut(UIX.black, x + a, y + ry, 1, b - a + 1, 1); };
    const sum = (rows, col) => rows.reduce((t, r) => t + (d[col][r.key] || 0), 0);
    const hip = !!(P.f0 && P.f0.poseidon), k = hip ? 0 : L.shift_without_hippodrome;
    const inc = L.income_rows.concat(hip ? [L.hippodrome] : []), exp = L.expense_rows;
    uiText(T2(L.income.text), x + L.head_x, y + L.income.y, f);
    for (const r of inc) row(L.label_x, r.y, r.text, d.last[r.key] || 0, d.this[r.key] || 0);
    rule(L.income_rule_y + k);
    const ti = [sum(inc, "last"), sum(inc, "this")], te = [sum(exp, "last"), sum(exp, "this")];
    row(L.label_x, L.income_total.y + k, L.income_total.text, ti[0], ti[1]);
    uiText(T2(L.expenses.text), x + L.head_x, y + L.expenses.y, f);
    for (const r of exp) row(L.label_x, r.y, r.text, d.last[r.key] || 0, d.this[r.key] || 0);
    rule(L.expense_rule_y);
    row(L.label_x, L.expense_total.y, L.expense_total.text, te[0], te[1]);
    row(L.head_x, L.net.y, L.net.text, ti[0] - te[0], ti[1] - te[1]);
    row(L.head_x, L.balance.y, L.balance.text, d.balance[0], d.balance[1]);
  }

  // --- advisors 9, 11, 7, 15, 6, 13, 2 (layouts: advisors.json, tools/play_advisors.py; data: live.py) -------------
  const numC = (n, suffix = "") => ZText.numberText(n, "@", suffix);       // number_text_draw_centered: '@' + digits
  const spr = (r, off = 0) => r && sprite(r.file, r.index + off);
  const goodsIcon = (res) => { const ic = D.labor.icons[String(res)]; return ic && sprite(ic.file, ic.index); };
  function rims(x, y, w, h, hover) {                // window_highlight_draw 0x0059F6E0 (as info.js): edges only
    const base = D.sprites.rims.index + (hover ? 8 : 0), nc = Math.ceil(w / 16), nr = Math.ceil(h / 16);
    for (let c = 0; c < nc; c++) {
      const tx = c === nc - 1 ? x + w - 16 : x + 16 * c;
      uiPut(sprite("Zeus_Interface", base + (c === 0 ? 0 : c === nc - 1 ? 2 : 1)), tx, y);
      uiPut(sprite("Zeus_Interface", base + (c === 0 ? 6 : c === nc - 1 ? 4 : 5)), tx, y + h - 16);
    }
    for (let r = 1; r < nr - 1; r++) {
      uiPut(sprite("Zeus_Interface", base + 7), x, y + 16 * r);
      uiPut(sprite("Zeus_Interface", base + 3), x + w - 16, y + 16 * r);
    }
  }
  const fill = (sp, x, y, w, h) => { if (w > 0 && h > 0) uiPut(sp, x, y, 1, w, h); };
  function box(x, y, w, h) {                         // FUN_00509870 colour 0: 1-px outline
    fill(UIX.black, x, y, w, 1); fill(UIX.black, x, y + h - 1, w, 1);
    fill(UIX.black, x, y, 1, h); fill(UIX.black, x + w - 1, y, 1, h);
  }
  // [amount] (FUN_0051B980 / FUN_00466B20 placeholders)
  const amount = (s, n) => s.replace("[amount]", String(n));

  function drawHusbandry({ x, y }, d) {                                      // FUN_00597720
    const L = D.husbandry, f = L.font;
    uiText(T2(L.title.text), x + L.title.pos[0], y + L.title.pos[1], L.title.font);
    uiText(T2(L.head.text), x + L.head.pos[0], y + L.head.pos[1], L.head.font);
    for (const h of [L.head_loads, L.head_people])
      uiText(T2(h.text), x + h.pos[0], y + h.pos[1], h.font, { width: h.width, align: "center", wrap: true });
    let ry = y + L.row_y, n = 0, units = 0, people = 0;
    const row = (count, name, u, p, pre) => {
      if (count != null) uiText(ZText.numberText(count, "@", ""), x + L.count_x, ry, f);
      if (pre) { uiText(pre, x + L.name_x, ry, f); uiText(name, x + L.name_x + pen(f, pre), ry, f); }
      else uiText(name, x + L.name_x, ry, f);
      uiText(numC(Math.trunc(u / 100)), x + L.loads_x, ry, f, { center: L.col_w });
      uiText(numC(p), x + L.people_x, ry, f, { center: L.col_w });
      units += u; people += p; n++; ry += L.row_step;
    };
    for (const r of d.rows) row(r.count, T2(r.text), r.units, r.people);
    for (const r of d.imports) row(null, txt(23, r.res), r.units, r.people, T2(L.imported));
    if (n) {
      const ty = y + L.row_y + (n + 1) * L.row_step;
      uiText(T2(L.total), x + L.name_x, ty, f);
      uiText(numC(Math.trunc(units / 100)), x + L.loads_x, ty, f, { center: L.col_w });
      uiText(numC(people), x + L.people_x, ty, f, { center: L.col_w });
    } else uiText(T2(L.none.text), x + L.none.pos[0], y + L.none.pos[1], f, { center: L.none.width });
  }

  function mythRows(d) {                                                     // FUN_00596FB0 frame height
    const n = d.sanctuaries.length, o = d.others, u = d.unfriendly.length;
    let h = n ? n * 20 + 99 : 0x52;
    if (o) h += (o + 1) * 16;
    if (u) h += (u + 1) * 16;
    if (u || d.heroes) h += 10;
    return (h >> 4) + 2;
  }
  function drawMythology({ x, y }, d) {
    const L = D.mythology;
    uiText(T2(L.title.text), x + L.title.pos[0], y + L.title.pos[1], L.title.font);
    uiText(T2(L.worship.text), x + L.worship.pos[0], y + L.worship.pos[1], L.worship.font);
    const n = d.sanctuaries.length;
    let ry = y + L.inset.pos[1];
    if (n) { uiFrame("plain", x + L.inset.pos[0], ry, L.inset.cols, n + 1); ry = y + L.row_y; }
    for (const s of d.sanctuaries) {
      uiText(txt(157, s.god), x + L.god_x, ry, L.god_font);
      const fo = L.state_fonts[String(s.font)];
      const t = s.text === 0x20 || s.text === 0x21 ? `${txt(59, 31)} ${s.pct} % ${txt(59, s.text)}` : txt(59, s.text);
      uiText(t, x + L.state_x, ry, fo);
      ry += L.row_step;
    }
    let yy = ry;
    if (n) {
      yy = ry + 0xC;
      if (d.others) {
        uiText(T2(L.others), x + L.label_x, yy, L.label_font);
        yy = ry + 0x1C;
        for (const g of d.friendly) { uiText(txt(157, g), x + L.label_x, yy, L.name_font); yy += 16; }
      }
    }
    let uy = yy + 10;
    if (d.unfriendly.length) {
      uiText(T2(L.unfriendly), x + L.label_x, uy, L.label_font); uy += 16;
      d.unfriendly.forEach((g, k) => {                                      // FUN_004F0AE0: 59:0x33+god / 59:0x41
        uiText(txt(157, g), x + L.label_x, uy, L.name_font);
        const st = (d.ustate || [])[k];
        if (st >= 0) uiText(txt(59, st), x + L.state_x, uy, L.label_font);
        uy += 16;
      });
    }
  }

  let popMode = 0;                                                           // 0x00665E30: 0 history, 1 society
  function popScale(m) {                                                     // FUN_00593EE0 -> [top, shift]
    const T = [[100, -1], [200, 0], [400, 1], [800, 2], [1600, 3], [3200, 4], [6400, 5], [12800, 6], [25600, 7]];
    for (const [top, sh] of T) if (m <= top) return [top, sh];
    return [51200, 8];
  }
  function drawPopulation({ x, y }, d) {                                     // FUN_00593740
    const L = D.population, m = popMode;
    uiFrame("plain", x + L.inset.pos[0], y + L.inset.pos[1], L.inset.cols, L.inset.rows);
    uiText(T2(L.title.text[m]), x + L.title.pos[0], y + L.title.pos[1], L.title.font);
    uiText(T2(L.caption.text[m]), x + L.caption.pos[0], y + L.caption.pos[1], L.caption.font, { center: L.caption.width });
    uiText(T2(L.button.text[m]), x + L.button.pos[0], y + L.button.pos[1], L.button.font, { center: L.button.width });
    const [hx, hy, hr, hb] = L.button.hit, hov = uiHover(x + hx, y + hy, hr - hx, hb - hy);
    rims(x + L.button.rims[0], y + L.button.rims[1], L.button.rims[2], L.button.rims[3], hov);   // FUN_00593A30
    UIX.hits.push([x + hx, y + hy, hr - hx, hb - hy, () => { popMode = 1 - popMode; }, T2(L.button.text[m])]);
    const gx = x + L.graph[0], gy = y + L.graph[1], lf = L.label_font;
    const bars = (vals, xs, w, sh) => {
      vals.forEach((v, i) => {
        const h = sh < 0 ? v << 1 : v >> sh;
        if (h <= 0) return;
        const bx = xs(i), by = gy + L.bar_bottom - h;
        fill(UIX.red565, bx, by, w, h); box(bx, by, w, h);              // FUN_00509B20 0xF800, FUN_00509870 0
      });
    };
    const scale = (top) => L.scale_y.forEach((dy, k) => uiText(numC([top, top >> 1, 0][k], " "), gx + L.scale_x, gy + dy, lf,
                                                                  { center: L.scale_w }));
    if (m === 0) {                                                           // FUN_00593A80
      const H = d.history, cnt = H.length;
      const N = cnt <= 20 ? 20 : cnt <= 40 ? 40 : cnt <= 100 ? 100 : cnt <= 200 ? 200 : 400;
      const start = N < cnt ? cnt - N : 0, get = (i) => H[start + i] || 0;   // FUN_00567710
      let mx = 0;
      for (let i = 0; i < N; i++) mx = Math.max(mx, get(i));
      const [top, sh] = popScale(mx);
      scale(top);
      let m0, y0, m1, y1;                                                    // FUN_00567750
      if (cnt <= N) { m0 = 0; y0 = d.start_year; m1 = N % 12; y1 = Math.trunc(N / 12) + d.start_year; }
      else {
        y1 = d.year; m1 = d.month - 1;
        if (m1 < 0) { m1 = d.month + 11; y1 = d.year - 1; }
        m0 = m1 - N % 12; if (m0 < 0) m0 += 12;
        y0 = y1 - Math.trunc(N / 12);
      }
      const year = (yr, px, py) => {                                         // year_text_draw 0x00508E50
        if (yr >= 0) { const a = txt(20, 1); uiText(a, px, py, lf); uiText(ZText.numberText(yr, " ", " "), px + pen(lf, a), py, lf); }
        else { const s = ZText.numberText(-yr, " ", " "); uiText(s, px, py, lf); uiText(txt(20, 0), px + pen(lf, s), py, lf); }
      };
      for (const [mm, yy, dx] of [[m0, y0, L.month_x[0]], [m1, y1, L.month_x[1]]]) {
        const s = txt(25, mm);
        uiText(s, gx + dx, gy + L.label_y, lf);
        year(yy, gx + dx + pen(lf, s), gy + L.label_y);
      }
      const w = N === 20 ? 20 : N === 40 ? 10 : N === 100 ? 4 : N === 200 ? 2 : 1;
      bars(Array.from({ length: N }, (_, i) => get(i)), (i) => gx + w * i, w, sh);
    } else {                                                                 // FUN_00593D20
      const lv = d.levels;
      const [top, sh] = popScale(Math.max(0, ...lv));
      scale(top);
      for (const s of L.society_labels) uiText(T2(s.text), gx + s.x, gy + L.label_y, lf, { center: s.width });
      bars(lv.slice(0, 13), (i) => gx + Math.trunc(i * 400 / 13), 30, sh);
    }
  }

  function drawAesthetics({ x, y }, d) {                                     // FUN_00596180
    const L = D.aesthetics;
    uiText(T2(L.title.text), x + L.title.pos[0], y + L.title.pos[1], L.title.font);
    uiText(T2(L.sub.text), x + L.sub.pos[0], y + L.sub.pos[1], L.sub.font);
    uiFrame("plain", x + L.inset.pos[0], y + L.inset.pos[1], L.inset.cols, L.inset.rows);
    const cy = y + L.comm.pos[1];
    uiText(T2(L.comm.text), x + L.comm.pos[0], cy, L.comm.font);
    const ly0 = cy + L.line_dy;
    if (!d.lines.length) { uiText(T2(L.none.text), x + L.comm.pos[0], ly0, L.none.font); return; }
    d.lines.forEach(([g, i, n], k) => {                                      // FUN_0051BD00 lines, 8 a column
      const name = txt(g, i);
      const s = T2(n === 1 ? L.one : L.many).replace("[commemorative_monument]", name).replace("[amount]", String(n));
      uiText(s, x + L.line_x + L.col_step * Math.trunc(k / L.per_col), ly0 + L.line_step * (k % L.per_col), L.line_font);
    });
  }

  let tradeHover = -1;
  function drawTrade({ x, y }, d) {                                          // FUN_005BAD80 + FUN_005BAEF0
    const L = D.trade, f = L.font;
    uiFrame("plain", x + L.inset.pos[0], y + L.inset.pos[1], L.inset.cols, L.inset.rows);
    uiText(T2(L.title.text), x + L.title.pos[0], y + L.title.pos[1], L.title.font);
    uiText(T2(L.prices.text), x + L.prices.pos[0], y + L.prices.pos[1], L.prices.font, { center: L.prices.width });
    d.goods.slice(0, L.max_rows).forEach((g, i) => {
      const ry = y + L.row_y + L.row_step * i, ty = ry + L.text_dy;
      const ic = goodsIcon(g.res);
      if (ic) uiPut(ic, x + L.icon_x, ry);
      uiText(txt(23, g.res), x + L.name_x, ty, f);
      uiText(ZText.numberText(g.price, "@", " "), x + L.price_x, ty, f, { center: L.price_w });
      if (g.state === 9) {
        const k = g.sells && g.buys ? "both" : g.sells ? "sells" : g.buys ? "buys" : null;
        if (k) uiText(txt(54, L.avail[k]), x + L.state_x, ty, f);
        return;
      }
      uiText(txt(54, L.state_text[String(g.state)]), x + L.state_x, ty, f);
      const c0 = g.cities[0];
      if (!c0) return;
      const [rl, rt, rr, rb] = L.city_rect, cx = x + L.city_x + rl;
      const hov = uiHover(x + L.city_x + rl, y + 0x3D + L.row_step * i + rt, rr - rl, rb - rt);
      uiText(c0.name, cx, ty, hov ? L.city_hover : c0.partner ? L.city_font : L.city_off);
      UIX.hits.push([x + L.city_x + rl, y + 0x3D + L.row_step * i + rt, rr - rl, rb - rt, () => {   // 0x005BA720
        const [px, py] = c0.post;
        cam.x = tileX(px, py) - (UIX.panelX * UIX.scale) / 2 / cam.zoom;
        cam.y = tileY(px, py) - innerHeight / 2 / cam.zoom;
        close();
      }, c0.name]);
      if (g.cities.length >= 3) {
        const mx = x + L.more_x, my = y + 0x37 + L.row_step * i;
        rims(mx, my, rr - rl, rb - rt, false);
        uiText(T2(L.more), x + L.more_text_x, ty, L.city_font);
        UIX.hits.push([mx, my, rr - rl, rb - rt, () => { more = { cities: g.cities.slice(1) }; }, T2(L.more)]);   // 0x005BA7D0
      } else if (g.cities.length === 2) {
        const c1 = g.cities[1];
        uiText(c1.name, x + L.more_text_x, ty, c1.partner ? L.city_font : L.city_off);
      }
    });
  }

  // the trade advisor's 'More' list (0x005BA7D0 -> screen 0x0F, list object 0x0160A808 drawn by FUN_005BF1E0):
  // the row's cities after the first; titled frame at (frame + 300, frame + 55), 13 columns (width 200 + 15),
  // floor((n*21 + 24) / 16) rows (one column up to 30); item k: text 21:name centred in x 5..201 at y 14 + 20k,
  // font 11C (entry 1), hovered 11LTBLUE (entry 15), not a trading partner 11LTYEL (entry 9; flags 0x18). A pick
  // (0x005BA780) centres the map on that city's post and closes the advisor; a click elsewhere closes the list.
  let more = null;
  function drawMore({ x, y }) {
    const n = more.cities.length, px = x + 300, py = y + 55, cols = 13, rows = Math.trunc((n * 21 + 24) / 16);
    UIX.hits.push([0, 0, UIX.W, UIX.H, () => { more = null; }, ""]);
    uiFlushText();                                                           // the list covers the rows' text
    uiFrame("titled", px, py, cols, rows);
    UIX.hits.push([px, py, cols * 16, rows * 16, null, ""]);
    more.cities.forEach((c, k) => {
      const rx = px + 5, ry = py + 14 + 20 * k, hov = uiHover(rx, ry, 196, 18);
      uiText(c.name, rx, ry, hov ? "SPR_FONTS_11LTBLUE" : c.partner ? "SPR_FONTS_11C" : "SPR_FONTS_11LTYEL", { center: 196 });
      UIX.hits.push([rx, ry, 196, 18, () => {
        const [tx, ty] = c.post;
        more = null;
        cam.x = tileX(tx, ty) - (UIX.panelX * UIX.scale) / 2 / cam.zoom;
        cam.y = tileY(tx, ty) - innerHeight / 2 / cam.zoom;
        close();
      }, c.name]);
    });
  }

  function overviewStatus(k, d) {                                            // -> [text, font rank, second line?]
    const s = d.sentiment;
    const cause = (base, def) => {                                           // FUN_00518A10.. 'past' flags: not kept
      return d.cause ? base + d.cause : def;
    };
    switch (k) {
      case "popularity": {                                                   // popularity_advisor_text 0x005B5AF0
        if (s < 1) return [txt(61, 15), 4, txt(61, d.cause + 0x26)];
        if (s > 99) return [txt(61, 0x1A), 5];
        const r = [txt(61, Math.trunc(s / 10) + 0x10), s < 30 ? 4 : 5];
        if (s < 50 && d.cause) r.push(txt(61, d.cause + 0x26));
        return r;
      }
      case "migration": {                                                    // 0x005B5FA0 (0x00FE9198 = 0 branch)
        if (d.immigrants > 4) return [txt(61, 0x43), 5];
        if (d.room < 1) return [txt(61, 0x41), 4];
        if (d.migration > 0x4F) return [txt(61, 0x43), 5];
        return [txt(61, cause(0x33, 0x3A)), 4];
      }
      case "food_production": {                                              // 0x005B6260
        if (d.eaten) {
          const p = Math.trunc(d.produced * 100 / d.eaten);
          if (p > 0x96) return [txt(61, 0x57), 5];
          if (p > 0x6E) return [txt(61, 0x56), 5];
          if (p > 0x5F) return [txt(61, 0x55), 5];
          if (p > 0x55) return [txt(61, 0x54), 5];
          if (p > 0x46) return [txt(61, 0x53), 4];
        }
        return [txt(61, 0x52), 4];
      }
      case "food_level": {                                                   // 0x005B5E10
        const p = d.eaten ? Math.trunc(d.stored * 100 / d.eaten) : 0;
        if (p <= 0) return [txt(61, 0x59), 4];
        if (p <= 0x31) return [txt(61, 0x5A), 4];
        if (p < 100) return [txt(61, 0x5B), 5];
        return [amount(txt(61, 0x5C), d.months), 5];
      }
      case "employment": {                                                   // 0x005B6350
        const u = d.unemployment, j = d.unfilled;
        let r;
        if (u >= 11) r = [amount(txt(61, 0x62), u), 4];
        else if (u >= 6) r = [amount(txt(61, 100), u), 5];
        else if (u >= 1) r = [amount(txt(61, 0x65), u), 5];
        else if (j >= 21) r = [amount(txt(61, 0x66), j), 4];
        else if (j >= 11) r = [amount(txt(61, 0x67), j), 4];
        else if (j >= 6) r = [amount(txt(61, 0x68), j), 5];
        else if (j >= 1) r = [amount(txt(61, 0x69), j), 5];
        if (u < 6 && j < 6) r = [txt(61, 0x6A), 5];
        return r;
      }
      case "hygiene": return [txt(61, Math.trunc(d.health / 10) + 0x74), d.health < 30 ? 4 : 5];   // 0x005B65C0
      case "unrest": {                                                       // 0x00519880 -> 0x00FEB544
        const U = d.unrest;
        let t = 0x8F;
        if (U.any && U.houses) {
          const hi = Math.trunc(U.high * 100 / U.houses);
          t = Math.trunc(U.mid * 100 / U.houses) > 0x32 ? 0x8A : hi < 0x1A ? (hi < 0xB ? 0x8E : 0x8C) : 0x8B;
        }
        return [txt(61, t), t === 0x8E || t === 0x8F ? 5 : 4];
      }
      case "finances": {                                                     // 0x005B6730
        if (d.year_start < d.treasury) return [amount(txt(61, 0x96), d.treasury - d.year_start), 5];
        if (d.year_start <= d.treasury) return [txt(61, 0x97), 5];
        return [amount(txt(61, 0x98), d.year_start - d.treasury), 4];
      }
      case "culture": {                                                      // 0x005B6830
        if (d.games) {                    // the next games: FUN_00565D40 of year type t; [games_name] = 58:(0x43 + t)
          const [t, r] = d.games, s = c => txt(61, c).replace("[games_name]", txt(58, 0x43 + t));
          if (r < 5) return [s(0xA5), 4];
          if (r < 10) return [s(0xA4), 4];
          if (r < 0x14) return [s(0xA3), 5];
          return [s(r < 0x1E ? 0xA2 : 0xA1), 5];
        }
        const a = Math.trunc(d.culture.reduce((t, v) => t + v, 0) / 4);
        if (a < 0x14) return [txt(61, 0xA0), 4];
        if (a < 0x28) return [txt(61, 0x9F), 4];
        if (a < 0x3C) return [txt(61, 0x9E), 5];
        if (a < 0x50) return [txt(61, 0x9D), 5];
        return [txt(61, 0x9C), 5];
      }
      case "mythology": return [txt(61, 0xB5), 5];                           // 0x005B69D0: no gods / monsters
      case "security": return d.invasion ? [txt(61, 0xB7), 4] : [txt(61, 0xB6), 5];   // 0x005B6AE0
    }
    return ["", 5];
  }
  function drawOverview({ x, y }, d) {                                       // FUN_005B7760
    const L = D.overview, b = spr(D.sprites.bullet);
    uiText(T2(L.title.text), x + L.title.pos[0], y + L.title.pos[1], L.title.font);
    uiFrame("plain", x + L.inset.pos[0], y + L.inset.pos[1], L.inset.cols, L.inset.rows);
    for (const r of L.rows) {
      uiPut(b, x + L.bullet_x, y + r.y);
      uiText(txt(61, r.label), x + L.label_x, y + r.y, L.label_font);
      const [t, fr, second] = overviewStatus(r.key, d), fo = L.fonts[String(fr)];
      if (r.key === "migration") uiText(t, x + L.status_x, y + r.y, fo, { width: L.para_w });
      else uiText(t, x + L.status_x, y + r.y, fo);
      if (second) uiText(second, x + L.status_x, y + L.second_y, fo);
    }
    const R = L.requests;
    uiText(T2(R.text), x + R.pos[0], y + R.pos[1], R.font);
    if (d.requests.length) uiText(T2(L.hint.text), x + R.pos[0] + pen(R.font, T2(R.text)), y + L.hint.y, L.hint.font);
    uiFrame("plain", x + L.req_frame.pos[0], y + L.req_frame.pos[1], L.req_frame.cols, L.req_frame.rows);
    const Q = L.req, rx = x + L.bullet_x, rel = { ally: 0, vassal: 1, rival: 2, parent: 3, colony: 4 };
    d.requests.slice(0, Q.max).forEach((q, k) => {
      const iy = y + Q.icon_y + Q.step * k, ty = y + Q.text_y + Q.step * k;
      // balloon (FUN_005B8630 table 0x0065B8D0 at (x+0x23, y+0x152), 528x23 rows, ids 0x6A4.. -> FUN_005B6EB0, at
      // once): 68:193 'click to fulfill', 194 when the request's event is in state 1 (overdue)
      if (window.Balloon && k < 8) Balloon.add(x + 0x23, y + 0x152 + 23 * k, 528, 23, q.overdue ? 194 : 193, true);
      if (q.kind === "quest") {                   // event type 4 (sim/scenario request_rows): Q.quest offsets
        const QQ = Q.quest, qf = L.fonts[q.ready ? QQ.fonts[0] : QQ.fonts[1]];
        uiPut(spr(q.ready ? D.sprites.request_done : D.sprites.request_open), rx, iy);
        if (q.god < 12) uiPut(spr(D.sprites.god_icons, q.god), rx + QQ.god_dx, iy);   // 12/13 (0x6837): Poseidon
        uiText(q.hero, rx + QQ.hero_dx, ty, qf);
        uiText(q.title, rx + QQ.title_dx, ty, qf);
        uiText(txt(157, q.god), rx + QQ.godname_dx, ty, qf);
        return;
      }
      // FUN_004713E0 (the stock or treasury covers it): bullet 12 and font 13 for amount, good and city; else bullet
      // 18, font 8 for amount and good, the city and its class by the relation (exe: city +0xD4 == 1 -> 14)
      const fo = L.fonts[q.relation === "ally" ? "14" : "8"], fa = L.fonts[q.can ? "13" : "8"];
      uiPut(spr(q.can ? D.sprites.request_done : D.sprites.request_open), rx, iy);
      const res = { drachmas: 23, food: 25 }[q.item] || (D.labor.industries.find((i) => i.key === q.item) || {}).res;
      // food (0x19): the goods icon after wine's (group 0x87B + FUN_0040FD80(0x15) + 1), name 23:25
      const wi = D.labor.icons["21"], ic = res === 25 ? wi && sprite(wi.file, wi.index + 1) : res && goodsIcon(res);
      if (ic) uiPut(ic, rx + Q.goods_dx, iy);
      uiText(ZText.numberText(q.amount, "@", ""), rx + Q.amount_dx, ty, fa);
      if (res && res !== 23) uiText(txt(23, res), rx + Q.good_dx, ty, fa);
      // the city's name within 0x50 px, else its short name (FUN_0042E2D0: 331:city, a custom name's first 4 letters)
      const cf = q.can ? fa : fo;
      uiText(q.short && pen(cf, q.city) >= 0x50 ? q.short : q.city, rx + Q.city_dx, ty, cf);
      if (q.relation in rel) uiText(txt(61, 197 + rel[q.relation]), rx + Q.class_dx, ty, fo);
      // stock column (+0x148, font 8): drachmas count_noun(8, 0, treasury) (8:0 when n = 1, else 8:1, as the exe);
      // goods / food: the loads in the city + 61:0xCC 'in city'; troops: none
      if (q.stock != null) {
        const sv = ZText.numberText(q.stock, q.item === "drachmas" ? " " : "@", "");
        uiText(sv, rx + Q.stock_dx, ty, L.fonts["8"]);
        uiText(q.item === "drachmas" ? txt(8, Math.abs(q.stock) === 1 ? 0 : 1) : txt(61, 0xCC), rx + Q.stock_dx + pen(L.fonts["8"], sv), ty, L.fonts["8"]);
      }
      if (q.overdue) uiText(txt(61, 205), rx + Q.due_dx, ty, L.fonts["14"]);
      else { const s = ZText.numberText(q.months, " ", ""); uiText(s, rx + Q.due_dx, ty, L.fonts["8"]);
             uiText(txt(8, q.months === 1 ? 4 : 5), rx + Q.due_dx + pen(L.fonts["8"], s), ty, L.fonts["8"]); }
    });
  }

  function drawMilitary({ x, y }, d) {                                       // FUN_00591C30
    const L = D.military, S = D.sprites;
    const A = L.army;
    uiText(T2(A.text), x + A.pos[0], y + A.pos[1], A.font, { center: A.width });
    const statusBar = (bx, by, w) => {                                       // FUN_005917A0: 13-px thin button pieces
      const n = Math.trunc(w / 13);
      for (let i = 0; i < n; i++) uiPut(spr(S.thin_button, i === 0 ? 0 : i < n - 1 ? 4 : 8), bx + 13 * i, by);
    };
    const statusText = (s, tx, ty, w, button) =>
      uiText(s, tx, ty, button ? L.status_font : L.status_plain, { center: Math.trunc(w / 13) * 13 });
    let sy = y + L.first_y, hy = y + 0x31;
    const cx = x + L.col_x, ix = cx + L.flag_dx, BL = window.Balloon;
    // balloons (FUN_00593470 hover ids 0x708.. / 0x76C.. / 2000.. -> FUN_004F5BB0, at once): per row the name
    // widget (0..170) 68:195/196/197 'go to company standard', the status widget (188..262) 68:201 + FUN_005918F0
    // (by the status 51:N of FUN_00591610: 18 -> 0, 21 -> 2, 22 -> 3, 23 -> 4, 24 -> 5, else 1); origin (x+0x16,
    // y+0x31), the next list (count+3)*16 lower
    const STATE = { 18: 0, 21: 2, 22: 3, 23: 4, 24: 5 };
    for (const sec of L.sections) {
      const rows = d.companies.filter((c) => c.type === sec.type);
      if (!rows.length) continue;
      if (BL) rows.forEach((c, k) => {
        BL.add(x + 0x16, hy + 16 * k, 170, 16, 195 + L.sections.indexOf(sec), true);
        BL.add(x + 0x16 + 188, hy + 16 * k, 74, 16, 201 + (STATE[c.status || (c.away ? 24 : 18)] ?? 1), true);
      });
      hy += (rows.length + 3) * 16;
      uiFrame("plain", cx, sy, L.col_cols, rows.length + 2);
      uiText(T2(sec.text), ix, sy + L.head_dx, L.head_font);
      uiText(T2(L.troops), x + L.troops_x, sy + L.head_dx, L.head_font);
      const y0 = sy + L.row_dy, tab = L.tables[sec.type];
      rows.forEach((c, k) => {
        const ry = y0 + L.row_step * k, [nr, sr] = [tab[2 * k], tab[2 * k + 1]];
        uiPut(spr(S.flags, c.banner), ix, ry);
        uiPut(spr(S.types, { horseman: 0, hoplite: 1, rabble: 2 }[c.type]), x + L.icon_x, ry);
        uiText(txt(138, c.banner), ix + L.name_dx + nr[0], y0 + 4 + nr[1], L.name_font);
        const btn = c.button !== false;                                      // FUN_00591610: fleeing / abroad are plain text
        if (btn) statusBar(ix + sr[0], y0 + 1 + sr[1], sr[2] - sr[0]);       // status 3 'at home': a button (1 px down: seen)
        if (btn && c.status != null)                     // 0x00591180: Marching/Still -> home; else muster at its spot
          UIX.hits.push([ix + sr[0], y0 + 1 + sr[1], sr[2] - sr[0], 14,
                         () => cmd(c.status === 19 || c.status === 20 ? `return ${c.slot}` : `mobilize ${c.slot}`), ""]);
        statusText(txt(51, c.status || (c.away ? 24 : 18)), ix + sr[0], y0 + 4 + sr[1], sr[2] - sr[0], btn);   // sim/military status
        uiText(ZText.numberText(c.soldiers, "@", ""), x + L.troops_x, ry + 4, L.name_font);
      });
      sy = y0 + L.row_step * rows.length + L.gap;
    }
    const rx = x + L.right_x, r5 = rx + 5, half = L.col_cols;
    const none = (ty) => uiText(txt(...L.none), r5 + half, ty, L.none_font, { center: half });
    const N = L.navy;
    uiText(T2(N.text), rx, y + N.y, A.font, { center: A.width });
    uiFrame("plain", rx, y + N.inset_y, half, N.rows);
    if (!d.navy.length) none(y + N.row_y);
    // navy balloons (ids 0x834.., at (x+300, y+0x21)): hull 68:200; crew 68:207 + FUN_00591950 (by the label 51:N of
    // FUN_00591680: 0x21 -> 0, 0x22/0x23 -> 1, 0x24 -> 2, 0x25 -> 3, 0x27 -> 4, 0x28 -> 5, 0x26 -> 6; none without a
    // trireme, or without crew unless unmanned)
    const CREW = { 0x21: 0, 0x22: 1, 0x23: 1, 0x24: 2, 0x25: 3, 0x27: 4, 0x28: 5, 0x26: 6 };
    if (BL) d.navy.slice(0, 6).forEach((w, k) => {
      BL.add(rx, y + 0x21 + 16 * k, 170, 16, 200, true);
      const lab = w.label != null ? w.label : 33, code = !w.trireme ? null : !w.workers ? (lab === 0x21 ? 0 : null) : CREW[lab];
      if (code != null) BL.add(rx + 188, y + 0x21 + 16 * k, 74, 16, 207 + code, true);
    });
    d.navy.slice(0, 6).forEach((w, k) => {
      const ry = y + N.row_y + 16 * k, [hr, cr] = [L.tables.navy[2 * k], L.tables.navy[2 * k + 1]], y0 = y + N.row_y;
      uiPut(spr(S.types, 3), rx + 0x13, ry);
      if (!w.workers) uiText(txt(51, 81), r5 + L.name_dx + hr[0], y0 + 4 + hr[1], D.overview.fonts["14"]);
      else if (!w.trireme) uiText(txt(51, 69), r5 + L.name_dx + hr[0], y0 + 4 + hr[1], L.name_font);
      else {
        const hp = w.hp, t = hp < 26 ? 0x35 : hp < 50 ? 0x34 : hp < 75 ? 0x33 : hp < 100 ? 0x32 : 0x31;
        uiText(txt(51, t), r5 + L.name_dx + hr[0], y0 + 4 + hr[1], L.name_font);
        const lab = w.label != null ? w.label : 33, click = w.clickable !== false;   // FUN_00591680 (sim navy.label)
        if (click) statusBar(r5 + cr[0], y0 + 1 + cr[1], cr[2] - cr[0]);
        if (click && w.id != null)                                                // 0x591400: crew home / aboard
          UIX.hits.push([r5 + cr[0], y0 + 1 + cr[1], cr[2] - cr[0], 14, () => cmd(`trireme ${w.id} crew`), ""]);
        statusText(txt(51, lab), r5 + cr[0], y0 + 4 + cr[1], cr[2] - cr[0], click);
      }
    });
    const O = L.other;
    uiText(T2(O.text), rx, y + O.y, A.font, { center: A.width });
    uiFrame("plain", rx, y + O.inset_y, half, O.rows);
    uiText(T2(O.text_merc), r5, y + O.head_y, L.head_font);
    uiText(T2(L.troops), rx + 0xAE, y + O.head_y, L.head_font);
    const extra = (rows, y0, tab) => rows.forEach((c, k) => {                // mercenaries (slots 21..30), mythical (31..)
      const ry = y0 + L.row_step * k, [nr, sr] = [tab[2 * k], tab[2 * k + 1]];
      uiPut(spr(S.types, { horseman: 0, hoplite: 5, rabble: 4 }[c.type]), rx + 0x13, ry);   // FUN_0051ABE0, slot > 20
      uiText(txt(138, c.banner), r5 + L.name_dx + nr[0], y0 + 4 + nr[1], L.name_font);
      uiText(ZText.numberText(c.soldiers, "@", ""), rx + 0xAE, ry + 4, L.name_font);
      statusBar(r5 + sr[0], y0 + 1 + sr[1], sr[2] - sr[0]);
      statusText(txt(51, c.away ? 24 : 18), r5 + sr[0], y0 + 4 + sr[1], sr[2] - sr[0], true);
    });
    const mercs = d.mercenaries || [], myth = d.mythical || [];
    // balloons: mercenaries (ids 0x898.., (x+300, y+0xB2), table 0x00644730) both widgets 68:199; mythical (0x8FC..,
    // y+0x183) name 197, status 201 + state
    if (BL) mercs.slice(0, 10).forEach((c, k) => { BL.add(rx, y + 0xB2 + 16 * k, 188, 16, 199, true); BL.add(rx + 188, y + 0xB2 + 16 * k, 74, 16, 199, true); });
    if (BL) myth.slice(0, 4).forEach((c, k) => { BL.add(rx, y + 0x183 + 16 * k, 170, 16, 197, true); BL.add(rx + 188, y + 0x183 + 16 * k, 74, 16, c.away ? 206 : 201, true); });
    if (mercs.length) extra(mercs, y + O.row_y, L.tables.merc); else none(y + O.row_y);
    const M = L.myth, my = y + O.row_y;
    uiFrame("plain", rx, my + M.inset_dy, half, M.rows);
    uiText(T2(M.text), r5, my + M.head_dy, L.head_font);
    uiText(T2(L.troops), rx + 0xAE, my + M.head_dy, L.head_font);
    if (myth.length) extra(myth, my + M.row_dy, L.tables.myth); else none(my + M.row_dy);   // ours: none (no gods)
    const B = L.lines, b = spr(S.bullet), f = B.font, ly = (k) => y + B.y[k];
    for (let k = 0; k < 3; k++) uiPut(b, x + B.bullet_x, ly(k));
    const cn = (n, k, px, py) => {                                           // count_noun_draw: " n" + noun, pen after
      const s = ZText.numberText(n, " ", ""), w = txt(8, k + (Math.abs(n) === 1 ? 0 : 1));
      uiText(s, px, py, f); uiText(w, px + pen(f, s), py, f);
      return pen(f, s) + pen(f, w);
    };
    const t0 = ly(0) - 1;
    const p1 = cn(d.soldiers, 0x2E, x + B.count_x, t0);
    // the pen (DAT_00F13A70): count_noun_draw resets it and adds number + noun; text_ref_draw adds to it (seen)
    uiText(txt(51, 55), x + B.in_dx + p1, t0, f);
    const p2 = p1 + pen(f, txt(51, 55));
    const p3 = cn(d.companies.length, 0x30, x + B.comp_dx + p2, t0);
    cn(d.triremes, 0x32, x + B.tri_dx + p3, t0);
    uiText(txt(51, d.invasion ? 57 : 56), x + B.text_x, ly(1) - 1, f);
    uiText(txt(51, 60), x + B.text_x, ly(2) - 1, f);
  }

  const DRAW = { 8: drawHygiene, 10: drawCulture, 12: drawFinance, 9: drawHusbandry, 11: drawMythology, 7: drawPopulation,
                 15: drawAesthetics, 6: drawTrade, 13: drawOverview, 2: drawMilitary };

  function requestIcon(item) {                     // the request's goods picture (FUN_005B7760 / 0x005B6F00 switch)
    if (!D) { load(); return null; }
    const res = { drachmas: 23 }[item] || (D.labor.industries.find((i) => i.key === item) || {}).res;
    return res ? goodsIcon(res) : null;
  }

  return { load, open, openPage, has, close, isOpen, text: txt, draw, refresh, advisorOfPage, requestIcon, get current() { return cur; }, get data() { return data; } };
})();

window.Advisors = Advisors;
