// Play mode: the military module's pictures and orders (docs/play/military.md, sim/military).
// - roles: data/play/military.json (tools/play_military.py) over walkers.json: invaders by army (good = army<N>),
//   tower / wall sentries, the palace companies' fixed blocks (rabble 6945) and the wolf's look blocks;
// - army atlases (Zeus_Greek .. Zeus_AresWarriors) load when an invasion of that army is on the map;
// - company standards (fig_handler_standard 0x004B3E00, drawn by walker_draw 0x0044FEF0 type 0xE): a pole
//   SPR_STD_POLES 20 - morale/5, the company flag SPR_FLAG_COMPANIES banner*7 + anim/2 (only a selected company's
//   flag waves), the class top SPR_FLAG_TOP_*; at the company's spot when mobilized, else on its palace piece;
// - orders: a selected company (control panel icons, pages.js) moves to a left-clicked tile (`move SLOT X Y`).
"use strict";

const Military = (() => {
  let data = null, polled = 0, busy = false, selected = 0;
  const TOP = { hoplite: "SPR_FLAG_TOP_INF", horseman: "SPR_FLAG_TOP_CAV", rabble: "SPR_FLAG_TOP_MISS" };

  function init() {                                // after loadMaps: merge roles into MAP.walkers.roles
    const M = MAP.military, WM = MAP.walkers && MAP.walkers.roles;
    if (!M || !WM) return;
    for (const [k, v] of Object.entries(M.roles || {})) WM[k] = v;
    for (const [k, o] of Object.entries(M.overrides || {})) {
      const m = WM[k] || (WM[k] = { file: "SprMain" });
      for (const [f, v] of Object.entries(o)) {
        if (v === null) delete m[f];
        else if (f === "work") m.work = Object.assign({}, m.work || {}, v);
        else m[f] = v;
      }
    }
  }

  async function poll() {                          // /military.json once a second (companies, invasions)
    if (busy || performance.now() - polled < 1000) return;
    busy = true; polled = performance.now();
    try {
      data = await (await fetch("/military.json")).json();
      const roles = (MAP.military && MAP.military.roles) || {}, want = new Set();
      for (const inv of data.invasions || [])
        for (const cls of ["enemy_archer", "enemy_infantry", "enemy_cavalry", "enemy_warship"]) {
          const r = roles[`${cls}_${inv.nation}`];
          if (r && r.file && !atlas[r.file]) want.add(r.file);
        }
      if (want.size) await loadAtlases(R, [...want]);
    } catch (e) { } finally { busy = false; }
  }

  // positions from the oracle (docs/play/monuments.md "Palace flag poles"): with P = the tile's 58x30 box
  // top-left, pole P + (16, -33), flag P + (25, -69), top icon P + (15, -84); depth = the tile's (a walker)
  function scene(out) {                            // the standards, in the walker pass
    poll();
    if (!data || !data.on) return;
    for (const c of data.companies || []) {
      const at = c.away || !(c.members > 0) ? null : c.mob ? c.dest : c.home;   // standing down: its palace piece
      if (!at) continue;
      const [x, y] = at;
      const [depth, cx, cy] = Scene.walkerSpot(x, y);
      const px = cx - 29, py = cy - 15;
      const pole = groupSprite("Zeus_General", "SPR_STD_POLES", Math.max(0, Math.min(20, 20 - Math.floor(c.morale / 5))));
      if (pole) out.push([depth, x, pole, px + 16, py - 33]);
      const anim = c.slot === selected ? Math.floor(performance.now() / 50) % 12 : 0;   // anim_frame +1 a tick (ours: 20/s)
      const flag = c.loan ? groupSprite("Zeus_General", "SPR_FLAG_LOAN", anim >> 1)      // defensive aid (+0x94)
        : groupSprite("Zeus_General", "SPR_FLAG_COMPANIES", (c.banner || 0) * 7 + (anim >> 1));
      if (flag) out.push([depth, x, flag, px + 25, py - 69]);
      const top = groupSprite("Zeus_General", TOP[c.type] || TOP.hoplite, 0);
      if (top) out.push([depth, x, top, px + 15, py - 84]);
    }
  }

  function select(slot) { selected = slot || 0; }
  function company(slot) { return data && (data.companies || []).find(c => c.slot === slot); }

  function mapClick(e) {                           // left click on the map with a company selected: move it there
    if (!selected || e.button !== 0) return false;
    const t = screenTile(e.clientX, e.clientY);
    if (!t) return false;
    sendCommands([`move ${selected} ${t[0]} ${t[1]}`], { sound: false }).then(() => { polled = 0; });
    return true;
  }

  return { init, scene, poll, select, mapClick, company, get selected() { return selected; }, get data() { return data; },
           refresh() { polled = 0; } };
})();

window.Military = Military;
