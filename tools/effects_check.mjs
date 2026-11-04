// Effect figures in play mode (docs/play/walkers.md "Effect figures", bugs.md 362): opens play mode on a running
// live server (a COPY of a save, own port), centres the view on a raw tile, lets the game run, then takes a shot
// and prints how many effect figures of each kind are alive (viewer/play/effects.js).
//
//   python3 tools/oracle_disaster.py save europa4 COPY.pkl 24 280       # ours ~ exe shot m060 (lava + 288 ticks)
//   python3 -m sim live COPY.pkl --port 8803 --speed 30 &
//   node tools/effects_check.mjs http://127.0.0.1:8803/play.html OUT.png 82 193 [--wait 6000] [--size 800x600]
// --exe-cam COL,ROW instead of the tile: the exe's camera (0x00DA2F64 / 68, an even row) at its pixel scale, so the
// shot lines up with an oracle shot: zoom 1 / dpr, cam (60 COL - 6870, 15 ROW - 30) (bugs.md 363); --size 640x480
// gives the exe's 800 x 600 at dpr 1.25 (the landslide's ground, bugs.md 366). --eval JS runs before the wait (e.g.
// "MsgWin.close(); document.getElementById('bar').style.display = 'none'" for a clean map).
import { launch } from "./play_cdp.mjs";

const a = process.argv.slice(2);
const opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const [url, out, tx, ty] = a;
const [W, H] = opt("--size", "800x600").split("x").map(Number);
const b = await launch({ width: W, height: H, dpr: +opt("--dpr", "1.25") });
await b.open(url);
await new Promise(r => setTimeout(r, 4000));
await b.eval("setMuted(true); true");
const ec = opt("--exe-cam", null);
if (ec) {
  const [col, row] = ec.split(",").map(Number);
  await b.eval(`cam.zoom = 1 / devicePixelRatio; cam.x = ${60 * col - 6870}; cam.y = ${15 * row - 30}; true`);
} else {
  await b.eval(`cam.zoom = 1; cam.x = tileX(${tx}, ${ty}) - (UIX.panelX * UIX.scale) / 2; cam.y = tileY(${tx}, ${ty}) - innerHeight / 2; true`);
}
if (opt("--eval", null)) await b.eval(`(() => { ${opt("--eval", "")}; return true; })()`);
await new Promise(r => setTimeout(r, +opt("--wait", "6000")));
const n = await b.eval("JSON.stringify(Effects.parts.reduce((m, p) => (m[p.kind] = (m[p.kind] || 0) + 1, m), {}))");
await b.shot(out);
console.log(out, n);
await b.close();
