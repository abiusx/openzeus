// Rendering check for god figures in play mode (sim/gods, viewer/play/gods.js; CLAUDE.md "Rendering checks").
// Headless Chrome at dpr 1.25 (tools/play_cdp.mjs) on YOUR OWN server (a save copy with a god on the map):
// centres each god on the map, pauses, and reads the frame back with gl.readPixels right after the page's frame,
// twice: with the god drawn and with its role hidden. Reports, per god and zoom, the sprite box and how many pixels
// of the 1-px ring just outside the box differ between the two frames (a sprite must not touch pixels outside its
// box: 0 = no seam / edge line), and the dark-pixel runs (>= 6, luminance < 24) along the ring. Dionysus' satyrs
// (role entranced, good satyr) too; for each figure the picture's anchor in use vs the file's (a mirrored
// alpha-masked picture is drawn 1 px right: ax = anchor - 1, tools/play_atlas.py blend_shift, bugs.md 245).
//
//   node tools/gods_check.mjs http://127.0.0.1:8797/play.html [--shot DIR] [--dpr 1.25]
import { launch } from "./play_cdp.mjs";

const URL_ = process.argv[2];
const opt = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const DPR = +opt("--dpr", 1.25), SHOT = opt("--shot", null);
const sleep = ms => new Promise(r => setTimeout(r, ms));

const PAGE = `(() => {
  if (window.__gc) return true;
  const orig = window.uiDraw;
  window.__gc = { want: null };
  window.uiDraw = function (R) {
    orig(R);
    const q = window.__gc.want;
    if (q) {
      const gl = R.gl, W = gl.drawingBufferWidth, H = gl.drawingBufferHeight, px = new Uint8Array(W * H * 4);
      gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, px);
      window.__gc.want = null;
      q.res({ W, H, px });
    }
  };
  window.__gcGrab = () => new Promise(res => { window.__gc.want = { res }; });
  return true;
})()`;

const b = await launch({ width: 1280, height: 800, dpr: DPR });
try {
  await b.open(URL_);
  await b.waitFor("typeof P !== 'undefined' && P.f0 && window.Gods && MAP.walkers && MAP.walkers.roles.god_zeus", 180000);
  await b.eval(PAGE);
  await b.eval("setMuted(true); true");
  const gods = await b.eval("P.f0.walkers.filter(w => w[3] === 'god' || (w[3] === 'entranced' && w[4] === 'satyr')).map(w => [w[0], w[3] === 'god' ? w[4] : 'satyr'])");
  for (const [id, name] of gods) {
    const role = name === "satyr" ? "follower_satyr" : `god_${name}`, hide = name === "satyr" ? "follower_satyr" : "god";
    for (const zoom of [1, 2]) {
      const r = await b.eval(`(async () => {
        const w = P.f0.walkers.find(w => w[0] === ${id}); if (!w) return null;
        cam.zoom = ${zoom};
        cam.x = tileX(w[1], w[2]) - (UIX.panelX * UIX.scale) / 2 / cam.zoom; cam.y = tileY(w[1], w[2]) - innerHeight / 2 / cam.zoom;
        for (let i = 0; i < 40 && !atlas[MAP.walkers.roles['${role}'].file]; i++) await new Promise(r => setTimeout(r, 250));
        await new Promise(r => setTimeout(r, 600));
        const hit = WALKER_HITS.find(h => h[0] === ${id}); if (!hit) return { missing: true };
        const a = await __gcGrab();
        const keep = MAP.walkers.roles['${hide}']; delete MAP.walkers.roles['${hide}'];
        const bb = await __gcGrab(); MAP.walkers.roles['${hide}'] = keep;
        const s = cam.zoom * devicePixelRatio, x0 = Math.floor((hit[1] - cam.x) * s) - 1, y0 = Math.floor((hit[2] - cam.y) * s) - 1;
        const x1 = Math.ceil((hit[1] + hit[3] - cam.x) * s), y1 = Math.ceil((hit[2] + hit[4] - cam.y) * s);
        const ring = [];
        for (let x = x0; x <= x1; x++) ring.push([x, y0], [x, y1]);
        for (let y = y0 + 1; y < y1; y++) ring.push([x0, y], [x1, y]);
        let diff = 0, inside = 0, dark = 0, run = 0;
        const at = (img, x, y) => { const Y = img.H - 1 - y, i = (Y * img.W + x) * 4; return [img.px[i], img.px[i + 1], img.px[i + 2]]; };
        for (const [x, y] of ring) {
          if (x < 0 || y < 0 || x >= a.W || y >= a.H) continue;
          const p = at(a, x, y), q = at(bb, x, y);
          if (p[0] !== q[0] || p[1] !== q[1] || p[2] !== q[2]) diff++;
          const lum = (p[0] * 3 + p[1] * 6 + p[2]) / 10;
          run = lum < 24 ? run + 1 : 0; if (run === 6) dark++;
        }
        for (let y = y0 + 2; y < y1 - 1; y += 3) for (let x = x0 + 2; x < x1 - 1; x += 3) {
          const p = at(a, x, y), q = at(bb, x, y); if (p[0] !== q[0] || p[1] !== q[1] || p[2] !== q[2]) inside++;
        }
        const sp = sprite(hit[8], hit[9]), e = atlas[hit[8]] && atlas[hit[8]].images[hit[9]];
        return { box: [x0, y0, x1, y1], ringPx: ring.length, ringDiff: diff, darkRuns: dark, insideChanged: inside, file: hit[8], idx: hit[9],
                 ax: sp && sp.ax, anchor: e && e[5], mirrored: !!(e && e[7] != null) };
      })()`);
      console.log(name, `zoom ${zoom * 100}%`, JSON.stringify(r));
      if (SHOT) await b.shot(`${SHOT}/god_${name}_${zoom}.png`);
    }
  }
} finally {
  await b.close();
}
