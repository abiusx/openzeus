// The README's gameplay animation, step 1: record frames of a running city in headless Chrome with every hi-res
// set on. Step 2 (tools/readme_gif.py) turns the frames into the GIF.
//
//   python3 -m sim live COPY_OF_A_SAVE.pkl --port 8797 --speed 30 &       # your own server, on a copy
//   node tools/readme_gif.mjs http://127.0.0.1:8797/play.html FRAMEDIR [--at X,Y] [--frames 60] [--every 100]
//        [--size 1280x800] [--rate 30]
//   python3 tools/readme_gif.py FRAMEDIR release/public/media/gameplay.gif
//
// --at: the tile to centre on (default: the palace); --every: ms between frames; --rate: the city's speed in
// ticks/s while recording (30 = the 2x button). The browser's bottom bar (ours, not the game's) is cropped away.
import { launch } from "./play_cdp.mjs";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const a = process.argv.slice(2);
const opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const [url, out] = a;
if (!url || !out) { console.error("usage: node tools/readme_gif.mjs URL FRAMEDIR [--at X,Y] [--frames N] [--every MS]"); process.exit(2); }
const [W, H] = opt("--size", "1280x800").split("x").map(Number);
const frames = +opt("--frames", 60), every = +opt("--every", 100), rate = +opt("--rate", 30);
const at = opt("--at", null);
const sleep = ms => new Promise(r => setTimeout(r, ms));
mkdirSync(out, { recursive: true });

const b = await launch({ width: W, height: H, dpr: 1 });
// every hi-res set on (play.js prefs "polis-play": hires.choice per set), before the page's scripts run
await b.send("Page.addScriptToEvaluateOnNewDocument", { source: `try { const p = JSON.parse(localStorage.getItem("polis-play") || "{}");
  p.hires = Object.assign(p.hires || {}, { choice: { terrain: "remacri", buildings: "remacri", figures: "remacri", ui: "remacri" } });
  localStorage.setItem("polis-play", JSON.stringify(p)); } catch (e) { }` });
await b.open(url);
await b.waitFor("typeof S !== 'undefined' && S && S.tick != null && !(window.HIRES && HIRES.all)", 180000);
const base = new URL(url).origin;
await fetch(base + "/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rate, paused: false }) });
const [x, y] = at ? at.split(",").map(Number)
  : await b.eval("(() => { const p = (S.buildings || []).find(q => q.kind === 'palace'); return p ? [p.x + 2, p.y + 2] : [114, 114]; })()");
await b.eval(`uiCenterOn(${x}, ${y}); 0`);
await sleep(6000);                                        // the view's sheets load, walkers fill in
const barH = await b.eval("(() => { const e = document.getElementById('bar'); return e ? Math.ceil(e.getBoundingClientRect().height) : 0; })()");
const panelTop = await b.eval("(() => { const e = document.getElementById('bar'); return e && e.getBoundingClientRect().top > 100 ? 1 : 0; })()");
// the dev bar sits at the bottom in play mode; crop it off (clip in CSS px at dpr 1)
const clip = panelTop ? { x: 0, y: 0, width: W, height: H - barH, scale: 1 } : { x: 0, y: barH, width: W, height: H - barH, scale: 1 };
for (let i = 0; i < frames; i++) {
  const t0 = Date.now();
  const r = await b.send("Page.captureScreenshot", { format: "png", clip });
  writeFileSync(join(out, `f${String(i).padStart(3, "0")}.png`), Buffer.from(r.data, "base64"));
  await sleep(Math.max(0, every - (Date.now() - t0)));
}
console.log(`${frames} frames, ${clip.width}x${clip.height}, centred on (${x},${y})`);
await b.close();
