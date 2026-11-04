// Playhead stalls of a live tab (bugs.md 442): every animation frame's P.t and buffer end, the slow requests, and the
// terrain rebuilds. A stall = P.t unchanged over several frames while live and playing: every walker stops at once
// (the user: "everyone walks two blocks, then a pause"). Headless muted Chrome on YOUR OWN server (a COPY of a save,
// not a game in play), live at the server's speed.
//
//   node tools/playhead_stall_check.mjs http://127.0.0.1:PORT/play.html SECS X Y
//
// Prints the stalls [wall ms, length ms, P.t, buffer end], the requests slower than 60 ms, and the terrain rebuilds.
// Exit 1 when a stall is longer than 100 ms.
import { launch } from "./play_cdp.mjs";
const [URL_, SECS = 10, X = 100, Y = 100] = process.argv.slice(2), sleep = ms => new Promise(r => setTimeout(r, ms));
const b = await launch({ dpr: 1.25 });
const base = new URL(URL_);
const prefs = JSON.stringify({ muted: true, tips: false, hires: { choice: Object.fromEntries(["terrain", "buildings", "figures", "ui"].map(s => [s, "original"])), filter: "mip", text: true } });
await b.open(new URL("play/atlas/compressed.json", base).href, 800);
await b.eval(`localStorage.setItem("polis-play", ${JSON.stringify(prefs)}), 0`);
await b.open(URL_);
await b.waitFor("typeof STARTUP !== 'undefined' && STARTUP.ready > 0 && !document.getElementById('loading')", 180000);
await b.eval("(typeof setMuted === 'function' && setMuted(true), 0)");
await b.eval(`clampCam = () => {}; cam.zoom = 1; cam.x = tileX(${X}, ${Y}) - (UIX.panelX * UIX.scale) / 2 / cam.zoom; cam.y = tileY(${X}, ${Y}) - innerHeight / 2 / cam.zoom; 0`);
await sleep(4000);
await b.eval(`(() => { window.__R = []; window.__Q = [];
  const og = getJSON; window.getJSON = async function(u, ...a) { const t0 = performance.now(); try { return await og(u, ...a); } finally { window.__Q.push([t0|0, (performance.now()-t0)|0, String(u).split('?')[0], P.t|0]); } };
  const ob = buildTerrain; window.__B = []; window.buildTerrain = function(...a) { const t0 = performance.now(); try { return ob.apply(this, a); } finally { window.__B.push([t0|0, (performance.now()-t0)|0]); } };
  const oa = Comms.applyTerrain; Comms.applyTerrain = function(...a) { const t0 = performance.now(); try { return oa.apply(this, a); } finally { window.__B.push(["apply", t0|0, (performance.now()-t0)|0]); } };
  const f = () => { window.__R.push([performance.now()|0, P.t, bufEnd()]); requestAnimationFrame(f); }; requestAnimationFrame(f); return 0; })()`);
await sleep(+SECS * 1000);
const R = JSON.parse(await b.eval("JSON.stringify(window.__R)")), Q = JSON.parse(await b.eval("JSON.stringify(window.__Q)"));
const B = JSON.parse(await b.eval("JSON.stringify(window.__B)")); console.log("buildTerrain", JSON.stringify(B));
await b.close();
let i = 1; const fr = [];
while (i < R.length) { if (R[i][1] === R[i-1][1]) { let j = i; while (j < R.length && R[j][1] === R[i-1][1]) j++; fr.push([R[i-1][0], R[j-1][0] - R[i-1][0], Math.round(R[i-1][1]), R[i-1][2]]); i = j; } else i++; }
console.log('freezes [wall ms, ms, P.t, bufEnd]:', JSON.stringify(fr));
const slow = Q.filter(q => q[1] > 60);
console.log('requests', Q.length, 'slow >60ms:', JSON.stringify(slow.slice(0, 30)));
process.exit(fr.some(f => f[1] > 100) ? 1 : 0);
