// Synced live speed check: how many ticks/s the city reaches at each speed while a visible headless tab drives it.
// Run against your own server on a COPY of a save (not a game in play):
//   python3 -m sim live COPY.pkl --port 8790 --speed 30 &
//   node tools/speed_check.mjs http://127.0.0.1:8790/play.html [--rates 60,120,240,480,960,1920] [--secs 8]
// Prints per rate: wanted ticks/s, reached ticks/s (server tick), tab playhead ticks/s, frames.json round trips
// (count, median, p90 ms) and the tab's lead (ahead() ticks). --cpu N throttles the tab's CPU N times (a slow tab);
// --query "ahead=7" adds to play.html's query (ahead=N forces the old fixed margin).
import { launch } from "./play_cdp.mjs";

const args = process.argv.slice(2);
const cpu = +((i => i >= 0 ? args[i + 1] : 0)(args.indexOf("--cpu")));
const query = (i => i >= 0 ? args[i + 1] : "")(args.indexOf("--query"));
const url = args[0] + (query ? (args[0].includes("?") ? "&" : "?") + query : "");
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const rates = opt("--rates", "60,120,240,480,960,1920").split(",").map(Number);
const secs = +opt("--secs", 8);
const base = new URL(url).origin;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const control = body => fetch(base + "/control", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body) }).then(r => r.text());
const tick = async () => (await (await fetch(base + "/state.json")).json()).tick;

const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
if (cpu > 1) await b.send("Emulation.setCPUThrottlingRate", { rate: cpu });
await b.open(url);
await sleep(6000);
await b.eval(`(() => { const of = window.fetch; window.__rt = [];
  window.fetch = async (u, o) => { const t = performance.now(); const r = await of(u, o);
    if (String(u).startsWith("frames.json")) window.__rt.push(performance.now() - t); return r; }; })()`);
await control({ paused: false });
for (const r of rates) {
  await control({ rate: r });
  await sleep(2000);
  await b.eval("window.__rt.length = 0; 0");
  const t0 = await tick(), p0 = await b.eval("Math.floor(P.t)"), w0 = Date.now();
  await sleep(secs * 1000);
  const t1 = await tick(), p1 = await b.eval("Math.floor(P.t)"), dt = (Date.now() - w0) / 1000;
  const rt = (await b.eval("JSON.stringify(window.__rt)")); const a = JSON.parse(rt).sort((x, y) => x - y);
  const lead = await b.eval("ahead()");
  const q = p => a.length ? Math.round(a[Math.min(a.length - 1, Math.floor(p * a.length))]) : "-";
  console.log(`rate ${r}: server ${((t1 - t0) / dt).toFixed(0)} t/s, tab ${((p1 - p0) / dt).toFixed(0)} t/s, ` +
    `polls ${a.length} median ${q(0.5)} p90 ${q(0.9)} ms, lead ${lead} ticks`);
}
await control({ rate: 30 });
await b.close();
