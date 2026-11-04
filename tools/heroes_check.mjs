// Rendering check for track 1I's figure colours and minimap pictures in play mode (sim/heroes, viewer/play/heroes.js,
// gl.js colour blit; CLAUDE.md "Rendering checks"). Headless Chrome at dpr 1.25 (tools/play_cdp.mjs) on YOUR OWN
// server (a save copy with petrified statues / devoured victims / monsters, paused). For every statue (frame
// "statues") and tinted walker (frame "tint"), at zoom 1 and 2: centres it, reads the frame back with gl.readPixels
// right after the page's frame with and without the colour (statues hidden / tint list emptied), and reports:
//   changed  pixels that differ inside the picture's box (covered: of them under a later picture, colour not tested)
//   off      changed pixels whose colour breaks the exe's blit (statue 0x6318: r = g = b; devoured 0x7C00: g = b = 0)
//   ring     pixels of the 1-px ring outside the box that differ (0 = no seam / edge line)
// Minimap: for each monster / hero / god on the map, the 2 px of its minimap cell against SPR_R_MONSTER / HERO / GOD
// image 0's first two pixels (ui.js minimapFigures, minimap_draw 0x00454980).
//
//   node tools/heroes_check.mjs http://127.0.0.1:8798/play.html [--shot DIR] [--dpr 1.25]
import { launch } from "./play_cdp.mjs";

const URL_ = process.argv[2];
const opt = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const DPR = +opt("--dpr", 1.25), SHOT = opt("--shot", null);

const PAGE = `(() => {
  if (window.__hc) return true;
  const orig = window.uiDraw;
  window.__hc = { want: null };
  window.uiDraw = function (R) {
    orig(R);
    const q = window.__hc.want;
    if (q) {
      const gl = R.gl, W = gl.drawingBufferWidth, H = gl.drawingBufferHeight, px = new Uint8Array(W * H * 4);
      gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, px);
      window.__hc.want = null;
      q.res({ W, H, px });
    }
  };
  window.__hcGrab = () => new Promise(res => { window.__hc.want = { res }; });
  window.__hcCompare = async (box, kind, off, over) => {
    const a = await __hcGrab();
    const keep = off(); await new Promise(r => setTimeout(r, 50));
    const b = await __hcGrab(); keep();
    await new Promise(r => setTimeout(r, 50));
    const c = await __hcGrab();                    // on again: pixels that change on their own (wall-clock animations) are left out
    const s = cam.zoom * devicePixelRatio;
    const x0 = Math.floor((box[0] - cam.x) * s) - 1, y0 = Math.floor((box[1] - cam.y) * s) - 1;
    const x1 = Math.ceil((box[0] + box[2] - cam.x) * s), y1 = Math.ceil((box[1] + box[3] - cam.y) * s);
    const at = (img, x, y) => { const Y = img.H - 1 - y, i = (Y * img.W + x) * 4; return [img.px[i], img.px[i + 1], img.px[i + 2]]; };
    const same = (p, q) => p[0] === q[0] && p[1] === q[1] && p[2] === q[2];
    let changed = 0, bad = 0, ring = 0, covered = 0, sample = null;
    for (let y = y0 + 1; y < y1; y++) for (let x = x0 + 1; x < x1; x++) {
      const p = at(a, x, y), q = at(b, x, y);
      if (same(p, q) || !same(p, at(c, x, y))) continue;
      changed++;
      const wx = x / s + cam.x, wy = y / s + cam.y;
      if (over.some(r => wx >= r[0] && wx < r[0] + r[2] && wy >= r[1] && wy < r[1] + r[3])) { covered++; continue; }
      const ok = kind === "statue" ? (p[0] === p[1] && p[1] === p[2]) : (p[1] === 0 && p[2] === 0);
      if (!ok) { bad++; if (!sample) sample = [x, y, p, q]; }
    }
    const moved = (x, y) => !same(at(a, x, y), at(b, x, y)) && same(at(a, x, y), at(c, x, y));
    for (let x = x0; x <= x1; x++) for (const y of [y0, y1]) if (moved(x, y)) ring++;
    for (let y = y0 + 1; y < y1; y++) for (const x of [x0, x1]) if (moved(x, y)) ring++;
    return { changed, covered, off: bad, ring, sample };
  };
  return true;
})()`;

const b = await launch({ width: 1280, height: 800, dpr: DPR });
let fails = 0;
try {
  await b.open(URL_);
  await b.waitFor("typeof P !== 'undefined' && P.f0 && window.Heroes && MAP.walkers && MAP.walkers.roles.monster_0", 180000);
  await b.eval(PAGE);
  await b.eval("setMuted(true); true");
  const items = await b.eval(`[...(P.f0.statues || []).map((s, i) => ['statue', i, s[0], s[1], s[2]]),
                               ...(P.f0.tint || []).map(([id]) => { const w = P.f0.walkers.find(w => w[0] === id); return w && ['tint', id, w[1], w[2], w[3]]; }).filter(Boolean)]`);
  for (const [kind, id, x, y, role] of items) {
    for (const zoom of [1, 2]) {
      const r = await b.eval(`(async () => {
        cam.zoom = ${zoom};
        cam.x = tileX(${x}, ${y}) - (UIX.panelX * UIX.scale) / 2 / cam.zoom; cam.y = tileY(${x}, ${y}) - innerHeight / 2 / cam.zoom;
        await new Promise(r => setTimeout(r, 800));
        // the picture's box: the union of the frame's draw entries tagged with this colour at this walker's x
        // (play.js drawCapture hook: the sorted list of [depth, x, sprite, left, top] entries, .tint)
        const T = '${kind}' === 'statue' ? 0x6318 : 0x7C00;
        // a devoured victim lies under its monster (drawn later, a translucent aura): monsters hidden for the test
        const km = MAP.walkers.roles.monster;
        if ('${kind}' === 'tint') { MAP.walkers.roles.monster = undefined; await new Promise(r => setTimeout(r, 100)); }
        try {
        const list = await new Promise(res => { window.drawCapture = l => { window.drawCapture = null; res(l.slice()); }; });
        const es = list.filter(e => e.tint === T && Math.abs(e[1] - ${x}) < 0.5);
        if (!es.length) return { missing: true };
        const bx0 = Math.min(...es.map(e => e[3])), by0 = Math.min(...es.map(e => e[4]));
        const box = [bx0, by0, Math.max(...es.map(e => e[3] + e[2].w)) - bx0, Math.max(...es.map(e => e[4] + e[2].h)) - by0];
        // pictures drawn over it (later in the sorted list, overlapping): their pixels blend (a monster's translucent
        // aura), so the colour test leaves their rectangles out
        const last = Math.max(...es.map(e => list.indexOf(e)));
        const over = list.slice(last + 1).filter(e => e[3] < box[0] + box[2] && e[3] + e[2].w > box[0] && e[4] < box[1] + box[3] && e[4] + e[2].h > box[1])
          .map(e => [e[3], e[4], e[2].w, e[2].h]);
        // without the colour: this statue left out of the frame's list / the tint list emptied
        const off = '${kind}' === 'statue'
          ? () => { const k0 = P.f0.statues, k1 = P.f1 && P.f1.statues; const f = l => l && l.filter((s, i) => i !== ${id});
                    P.f0.statues = f(k0); if (P.f1) P.f1.statues = f(k1); return () => { P.f0.statues = k0; if (P.f1) P.f1.statues = k1; }; }
          : () => { const k0 = P.f0.tint, k1 = P.f1 && P.f1.tint; const f = l => l && l.filter(t => t[0] !== ${id});
                    P.f0.tint = f(k0); if (P.f1) P.f1.tint = f(k1); return () => { P.f0.tint = k0; if (P.f1) P.f1.tint = k1; }; };
        return Object.assign({ box }, await __hcCompare(box, '${kind}', off, over));
        } finally { MAP.walkers.roles.monster = km; }
      })()`);
      const bad = !r || r.missing || r.off || r.ring || !r.changed;
      if (bad) fails++;
      console.log(`${kind} ${role} #${id} (${x},${y}) zoom ${zoom * 100}%:`, JSON.stringify(r), bad ? "FAIL" : "ok");
      if (SHOT) await b.shot(`${SHOT}/${kind}_${id}_${zoom}.png`);
    }
  }
  // minimap pictures
  const mm = await b.eval(`(async () => {
    UIX.mm.key = null; buildMinimap();
    const pics = { god: 'SPR_R_GOD', monster: 'SPR_R_MONSTER', hero: 'SPR_R_HERO' }, out = [];
    const d = UIX.mm.ctx.getImageData(0, 0, UIX.mm.canvas.width, UIX.mm.canvas.height);
    for (const w of P.f0.walkers) {
      if (!pics[w[3]] || (w[7] && w[7][0] === 'hidden')) continue;
      const gg = atlas.Zeus_Interface.groups[pics[w[3]]], c = firstPixels(sprite('Zeus_Interface', gg[0], true));
      const [px, py] = mmPx(w[1], w[2]), get = q => { const o = (py * d.width + q) * 4; return [d.data[o], d.data[o + 1], d.data[o + 2]]; };
      const head = P.f0.walkers.find(v => v[1] === w[1] && v[2] === w[2] && !(v[7] && v[7][0] === 'hidden'));
      out.push({ id: w[0], role: w[3], at: [w[1], w[2]], head: head[0] === w[0], want: [c[0].slice(0, 3), c[1].slice(0, 3)], got: [get(px), get(px + 1)] });
    }
    return out;
  })()`);
  for (const m of mm) {
    const ok = !m.head || JSON.stringify(m.want) === JSON.stringify(m.got);
    if (!ok) fails++;
    console.log(`minimap ${m.role} #${m.id} (${m.at}): want ${JSON.stringify(m.want)} got ${JSON.stringify(m.got)}${m.head ? "" : " (not the tile's first figure)"}`, ok ? "ok" : "FAIL");
  }
} finally {
  await b.close();
}
console.log(fails ? `${fails} FAIL` : "all ok");
process.exit(fails ? 1 : 0);
