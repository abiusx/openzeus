// Synced live smoothness over a slow link (bugs.md 482): does the playhead of a visible live tab advance on every
// animation frame, or does it run, wait for the next answer, and run again? Headless muted Chrome (play_cdp.mjs);
// the URL is your own server on a COPY of a save, or the shared public server (docs/play/server.md: visitors may
// change its city; reset it afterwards).
//
//   node tools/sync_check.mjs URL [--rates 15,30,60] [--secs 30] [--latency MS] [--down KBPS] [--cpu N] [--x X --y Y]
//
// --latency adds MS to every request's round trip in the tab (CDP Network.emulateNetworkConditions), so a local
// server stands in for a far one; --cpu N throttles the tab's CPU. For each rate (ticks/s; 15 = 1x) it sets the
// city's speed (/control), waits 4 s, then records every animation frame's playhead for SECS and prints:
// - the server's and the tab's ticks/s,
// - stalls: runs of frames in which a playing, live playhead did not move (it waits at its newest frame; every walker
//   stops), as count, total ms, the longest and the 5 longest [ms into the run, ms];
// - jumps: frames in which the playhead moved by more than 3x its frame's share (the catch-up rule, advance()),
// - the driving polls (frames.json with want): count, round trip median / p90 / max ms, and the tab's lead
//   (ahead() ticks, leadSecs) and its lag behind the server's tick (median, max ticks).
// Exit code 1 when a stall of 200 ms or more was seen.
import { launch } from "./play_cdp.mjs";

const args = process.argv.slice(2), url = args[0];
const opt = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const rates = opt("--rates", "15,30,60").split(",").map(Number), secs = +opt("--secs", 30);
const latency = +opt("--latency", 0), down = +opt("--down", 0), cpu = +opt("--cpu", 0);
const X = opt("--x", null), Y = opt("--y", null);
const base = new URL(url).origin, sleep = ms => new Promise(r => setTimeout(r, ms));
const control = body => fetch(base + "/control", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body) }).then(r => r.json());

const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
await b.open(base + "/play/atlas/compressed.json", 800);
await b.eval(`localStorage.setItem("polis-play", ${JSON.stringify(JSON.stringify({ muted: true, tips: false }))}), 0`);
await b.send("Network.enable");
if (latency || down) await b.send("Network.emulateNetworkConditions", { offline: false, latency,
  downloadThroughput: down ? down * 1024 / 8 : -1, uploadThroughput: -1 });
if (cpu > 1) await b.send("Emulation.setCPUThrottlingRate", { rate: cpu });
const t0 = Date.now();
await b.open(url);
await b.waitFor("typeof STARTUP !== 'undefined' && STARTUP.ready > 0 && typeof FRAMES !== 'undefined' && FRAMES.length > 0", 900000);
console.log(`ready after ${((Date.now() - t0) / 1000).toFixed(1)} s (STARTUP ${await b.eval("JSON.stringify(STARTUP)")})`);
await b.eval("(typeof setMuted === 'function' && setMuted(true), 0)");
if (X != null) await b.eval(`cam.x = tileX(${X}, ${Y}) - innerWidth / 2; cam.y = tileY(${X}, ${Y}) - innerHeight / 2; 0`);
// message windows pause nothing by default; close what comes so the city stays in plain play
await b.eval(`(() => { window.__R = []; window.__Q = [];
  const og = window.getJSON; window.getJSON = async function (u, ...a) { const s = performance.now();
    try { return await og(u, ...a); } finally { if (String(u).startsWith("frames.json") && String(u).includes("want="))
      window.__Q.push(performance.now() - s); } };
  const f = () => { window.__R.push([performance.now(), P.t, bufEnd(), P.liveTick, P.playing && P.live ? 1 : 0, ahead(), P.rate]);
    requestAnimationFrame(f); }; requestAnimationFrame(f); return 0; })()`);
let bad = false;
for (const rate of rates) {
  await control({ rate, paused: false });
  await sleep(4000);
  await b.eval("window.__R.length = 0; window.__Q.length = 0; 0");
  const s0 = (await (await fetch(base + "/frames.json?from=0&to=0")).json()).meta.live_tick, w0 = Date.now();
  await sleep(secs * 1000);
  const s1 = (await (await fetch(base + "/frames.json?from=0&to=0")).json()).meta.live_tick, dt = (Date.now() - w0) / 1000;
  const R = JSON.parse(await b.eval("JSON.stringify(window.__R)")), Q = JSON.parse(await b.eval("JSON.stringify(window.__Q)")).sort((p, q) => p - q);
  const stalls = [], jumps = [], lag = [];
  for (let i = 1; i < R.length; i++) {
    const [w, t, , live, playing] = R[i];
    lag.push(live - t);
    if (playing && t === R[i - 1][1]) {            // (synced: the server is often only as far as the tab asked)
      let j = i; while (j + 1 < R.length && R[j + 1][1] === t && R[j + 1][4]) j++;
      stalls.push([Math.round(R[i - 1][0] - R[0][0]), Math.round(R[j][0] - R[i - 1][0])]);
      i = j;
    } else if (playing && t - R[i - 1][1] > 3 * R[i][6] * (w - R[i - 1][0]) / 1000 + 2) jumps.push([Math.round(w - R[0][0]), Math.round(t - R[i - 1][1])]);
  }
  const real = stalls.filter(s => s[1] >= 50).sort((p, q) => q[1] - p[1]), all = stalls.filter(s => s[1] >= 20);
  const q = (a, p) => a.length ? Math.round(a[Math.min(a.length - 1, Math.floor(p * a.length))]) : "-";
  lag.sort((p, q2) => p - q2);
  const tab = (R[R.length - 1][1] - R[0][1]) / ((R[R.length - 1][0] - R[0][0]) / 1000);
  console.log(`rate ${rate}: server ${((s1 - s0) / dt).toFixed(1)} t/s, tab ${tab.toFixed(1)} t/s, frames ${R.length}; ` +
    `stalls >= 20 ms: ${all.length}, ${all.reduce((t, s) => t + s[1], 0)} ms; >= 50 ms: ${real.length}, ${real.reduce((t, s) => t + s[1], 0)} ms, longest ${real.length ? real[0][1] : 0} ms ` +
    `${JSON.stringify(real.slice(0, 5))}; jumps ${jumps.length} ${JSON.stringify(jumps.slice(0, 5))}; ` +
    `polls ${Q.length} rtt median ${q(Q, 0.5)} p90 ${q(Q, 0.9)} max ${q(Q, 1)} ms; lead ${R[R.length - 1][5]} ticks; lag median ${q(lag, 0.5)} max ${q(lag, 1)} ticks`);
  if (real.some(s => s[1] >= 200)) bad = true;
}
await b.close();
process.exit(bad ? 1 : 0);
