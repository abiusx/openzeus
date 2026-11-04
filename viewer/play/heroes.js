// Play mode: monsters, heroes and the Hero's Hall (sim/heroes; docs/logic/heroes-monsters.md "Ours").
// Roles from data/play/heroes.json (tools/play_heroes.py) merged over walkers.json: role "monster" / "hero" picks
// "monster_<id>" / "hero_<id>" by the walker's good ("m<id>" / "h<id>"); g1 walk, g2 die, g3 fight (monster smash /
// bash / hero duel as "fight" looks), image = first + frame * 8 + dir (monster_anim_info 0x00533B60, 0x004FA860).
// A figure's sprite file (zeus_<name>, Poseidon_<name>; viewer/play/atlas from tools/play_atlas.py) loads when it is
// on the map. The hall: its hero's statue (SPR_HERO_STATUES + id, building_extra_draw 0x0044F320) at the draw point
// + (0x2B, -0x48); while the hero exists a fire pot (SprAmbient rank 69) at the draw point + (0x7D, 0x3C) (0x0045C580).
// A hero on deep water swims: his g4 group (action 0x13 look) on a raft, SprAmbient rank 87 (scene.js; bug 392).
"use strict";

const Heroes = (() => {
  let busy = false, H = null;

  async function init() {
    const WM = MAP.walkers && MAP.walkers.roles;
    if (!WM) return;
    try {
      H = await getJSON("/data/play/heroes.json");
      for (const [k, v] of Object.entries(H.roles || {})) WM[k] = v;
      MAP.heroesMissile = H.missile || null;          // a monster's missile picture (scene.js drawArrow)
    } catch (e) { H = null; }
  }

  async function want(files) {                      // sprite files load on demand
    if (busy || !files.size) return;
    busy = true;
    try { await loadAtlases(R, [...files]); } catch (e) { } finally { busy = false; }
  }

  function scene() {
    const WM = MAP.walkers && MAP.walkers.roles, f = P.f0;
    if (!WM || !f || !f.walkers || !H) return;
    const files = new Set();
    for (const w of f.walkers) {
      if (w[3] !== "monster" && w[3] !== "hero") continue;
      const r = WM[(WM[w[3]].map || {})[w[4]]];
      if (r && r.file && !atlas[r.file]) files.add(r.file);
      if (w[3] === "hero" && H.hero_raft && !atlas[H.hero_raft.file]) files.add(H.hero_raft.file);
    }
    want(files);
    sounds();
  }

  // a monster's sounds from the frame's sfx (sim walkers.sfx [tick, id, x, y, role, god, kind, until]; audio.json
  // combat "monster:m<id>", rules.monster): "bash" = atk1 / atk2 every tick until `until` while it stands blocked
  // (0x004C8C72) or smashes in a rampage (25, 0x00532700); sound_play_sample refuses a sample still playing, so a
  // loop; "appear" = the Kraken's slot 9 at its spawn (0x0052F726); "atk3" / "atk4" = the missile attack's sound;
  // "hit" = slot 7. On screen only, panned (FUN_005A6FE0).
  let soundTick = null;
  const heard = new Set(), loops = new Map(), playing = new Map();
  function pan(x, y) {
    const sx = (tileX(x, y) + 29 - cam.x) * cam.zoom, sy = (tileY(x, y) + 15 - cam.y) * cam.zoom;
    return (sx < 0 || sy < 0 || sx > innerWidth || sy > innerHeight) ? null : sx / innerWidth * 2 - 1;
  }
  function goodOf(id) {
    for (const f of [P.f1, P.f0]) if (f) { const w = f.walkers.find(w => w[0] === id); if (w) return w; }
    return null;
  }
  function sounds() {
    const t = Math.floor(P.t), from = soundTick;
    soundTick = t;
    const C = MAP.audio && MAP.audio.combat;
    if (typeof audio === "undefined" || !audio || audio.muted || !C || from == null || t <= from || t - from > 60) return;
    for (const f of [P.f0, P.f1]) if (f && f.sfx) for (const e of f.sfx) {
      const [tick, id, x, y, role, , kind, until] = e;
      if (role !== "monster" || !(tick > from && tick <= t)) continue;
      const key = id + ":" + tick + ":" + kind;
      if (heard.has(key)) continue;
      heard.add(key);
      if (heard.size > 500) heard.clear();
      const w = goodOf(id), row = w && C.roles["monster:" + w[4]];
      if (!row) continue;
      if (kind === "bash") { const L = loops.get(id); loops.set(id, { good: w[4], until: Math.max(until, L ? L.until : 0) }); continue; }
      const p = pan(x, y);
      if (kind === "appear" && row.appear && p !== null) audio.sfxAt(row.appear, p);
      // the missile attack (28) at its frame 1: FUN_004DB3D0(f, 1) -> slot 3 / 4 (atk3 / atk4, picked by the sim's
      // CRT rand); a building hit by its missile: FUN_004DB7A0 -> slot 7; any hit that does not kill it: slot 7
      if ((kind === "atk3" || kind === "atk4") && row.attack && p !== null) audio.sfxAt(row.attack[kind === "atk3" ? 2 : 3], p);
      if (kind === "hit" && row.hit && p !== null) audio.sfxAt(row.hit, p);
    }
    const now = audio.ctx ? audio.ctx.currentTime : 0;
    for (const [id, L] of loops) {
      const w = P.f1 && P.f1.walkers.find(w => w[0] === id);
      if (!w || t > L.until) { loops.delete(id); continue; }
      const row = C.roles["monster:" + L.good], p = pan(w[1], w[2]);
      if (!row || !row.attack || p === null) continue;
      const k = Math.floor(Math.random() * 2), pk = id + ":" + k;
      if ((playing.get(pk) || 0) > now) continue;
      playing.set(pk, now + 30);                      // pending until the buffer is known
      audio.play(row.attack[k], audio.sfx, p).then(src => {
        playing.set(pk, src && src.buffer ? audio.ctx.currentTime + src.buffer.duration : 0);
      });
    }
  }

  function hallExtra(out, depth, b, tl, bw, dyBase) {   // the statue on the hall (Zeus heroes 0..5)
    const S = H && H.hall_statue, A = H && H.hall_firepot;
    if (!S || !tl) return;
    const sp = b.hero < S.count && sprite(S.file, S.first + b.hero);
    if (sp) overlayAt(out, depth, b.x, sp, tl, bw, S.dx, dyBase + S.dy);
    if (A && b.anim === "work") {                       // the fire pot while the hero exists (0x0045C580)
      if (!atlas[A.file]) { want(new Set([A.file])); return; }
      const fs = sprite(A.file, A.first + A.stride * (Math.floor(performance.now() / A.ms) % A.frames));
      if (fs) overlayAt(out, depth, b.x, fs, tl, bw, A.dx - fs.ax, dyBase + A.dy - fs.ay);
    }
  }

  // The Hero's Hall window, as hero_hall_info_draw 0x0057C720 draws it (L, T = the window's corner: the info window
  // setup gives type 0x7D 40 x 29 cells at (0, 0x2D), not the mouse rule; oracle 1I-hero hall.bmp): title 185:8+h
  // (22C) centred at T+10 over cols*16; separator (tile_row_draw: SPR_MARBLE_BAR, 0x27 tiles at (L+8, T+0x36));
  // status (0x0057C630, or 69:4 without road access; 11C) centred at T+0x26 over (cols-2)*16 from L; "<hero>
  // Requires" ("%s %s", 185:h, 185:0x3B) at (L+16, T+0x40), "Status" (185:0x3C) right-aligned over (cols-2)*16 from
  // L+16; inset (L+16, T+0x4C, 0x26 x 8); 5 rows at T + 84/104/124/144/164 + 3 (table 0x00642B5A): SPR_CHECKBOX tick
  // / empty (+0x4000 + !met) at L+27, the requirement at L+54, the value right-aligned at L+27 + (cols-4)*16
  // (FUN_004FAA70: font rank 5 11CB when met, rank 4 11C3 unmet); the needed text centred at T + 8*16 + 0x5E;
  // "Send For <hero>" (hero_can_send_for 0x004FA670): a RIMS highlight 544 x 20 (0x0063B370) at (L+0x30,
  // T+rows*16-0x26), hovered +8 (0x00509230), the label (11C) centred at T+(rows-2)*16.
  const HALL = { cols: 0x28, rows: 0x1D, x: 0, y: 0x2D };
  // Medusa's statues (frame "statues", sim heroes.frame: [x, y, role, good, fdx, fdy, look, tick]): a figure 0x46
  // at the victim's tile with the victim's picture of that moment (monster_petrify 0x005323A0 copies +0x04), drawn
  // with the draw colour 0x6318 (fig_handler_turned_to_stone 0x004C9EF0; gl.js colour blit) for 10 000 ticks. The
  // picture: the victim's fight frame at the petrify tick, else its walk picture standing; at the tile centre (a new
  // figure, tile progress 0); sorted as a walker (walkerSpot -> order.js).
  function statues(out) {
    const f = P.f0, WM = MAP.walkers && MAP.walkers.roles;
    if (!f || !f.statues || !WM) return;
    for (const s of f.statues) try {
      const [x, y, role, good, fdx, fdy, look, tick] = s, m = roleOf(WM, role, good);
      if (!m) continue;
      const o0 = out.length, key = "statue:" + x + ":" + y;
      if (look && look[0] === "fight" && m.fight) {
        const a = look.slice(); a[5] = 0; a[6] = 0; a[3] = fdx; a[4] = fdy;
        drawFight(out, m, role, key, [a, x, y], tick);
      } else {
        const walk = m.walk; if (!walk) continue;
        const [depth, cx, cy] = figureSpot(x, y, { big: BIG.has(role) });   // the figure's picture point (scene.js, bugs.md 251)
        const sp = sprite(walk.file || m.file, blockIndex(walk, viewDir(DIR_DELTA[`${fdx},${fdy}`] ?? 3), 0));
        if (sp) out.push([depth, x, sp, cx - sp.ax, cy - sp.ay]);
      }
      for (let i = o0; i < out.length; i++) out[i].tint = 0x6318;
    } catch (e) { }
  }

  function hallSize() { return { cols: HALL.cols, rows: HALL.rows, x: HALL.x, y: HALL.y }; }

  function drawHall(b, L, T, cols, rows) {
    const h = (b.info || {}).hall;
    if (!h) return false;
    const F = f => "SPR_FONTS_" + f, W2 = (cols - 2) * 16;
    uiText(h.hall_title || h.name, L, T + 10, F("22C"), { center: cols * 16 });
    for (let i = 0; i < 0x27; i++) uiPut(sprite("Zeus_Interface", 604 + (i === 0 ? 0 : i < 0x26 ? 1 : 2)), L + 8 + 16 * i, T + 0x36);
    uiText(!h.road ? h.texts.no_road : h.status, L, T + 0x26, F("11C"), { center: W2 });
    uiText(`${h.name} ${h.texts.requires}`, L + 16, T + 0x40, F("11C"));
    uiText(h.texts.status, L + 16, T + 0x40, F("11C"), { align: "right", width: W2 });
    uiFrame("plain", L + 16, T + 0x4C, cols - 2, 8);
    const ROWS = [84, 104, 124, 144, 164];
    for (let i = 0; i < 5; i++) {
      const y = T + ROWS[i] + 3, met = h.met[i];
      const cb = sprite("Zeus_Interface", met ? 607 : 608);
      if (cb) uiPut(cb, L + 27, y);
      uiText(h.reqs[i], L + 54, y, F(met ? "11CB" : "11C3"));
      uiText(h.values[i], L + 27, y, F(met ? "11CB" : "11C3"), { align: "right", width: (cols - 4) * 16 });
    }
    if (h.needed_text) uiText(h.needed_text, L, T + 8 * 16 + 0x5E, F("11C"), { center: W2 });
    if (h.can_send) {
      const bx = L + 0x30, by = T + rows * 16 - 0x26, bw = 544, bh = 20;
      if (window.ZInfo && ZInfo.rims) ZInfo.rims(bx, by, bw, bh, uiHover(bx, by, bw, bh));
      uiText(`${h.texts.send_for} ${h.name}`, L, T + (rows - 2) * 16, F("11C"), { center: W2 });
      UIX.hits.push([bx, by, bw, bh, () => sendCommands([`sendfor ${h.name.toLowerCase()}`]), h.texts.send_for]);
    }
    return true;
  }

  // the raft under a swimming hero (figure_hero_update 0x004C8F50: deep water 0x4000000 outside a bridge; bug 392)
  function raft() { return H && H.hero_raft; }
  function swimming(x, y) {
    if (x < 0 || y < 0 || x >= N || y >= N || !(T.flags[y * N + x] & 0x4000000)) return false;
    return !(window.Bridges && Bridges.at(x, y) != null);
  }

  return { init, scene, hallExtra, drawHall, hallSize, statues, raft, swimming };
})();

window.Heroes = Heroes;
