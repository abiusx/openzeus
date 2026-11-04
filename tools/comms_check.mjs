// Client/server traffic of play mode (docs/play/comms.md): measure, and check that the delta protocol shows the same.
// Headless muted Chrome (tools/play_cdp.mjs, dpr 1.25) on your own server (a COPY of a save; not a game in play).
//
//   node tools/comms_check.mjs measure URL [--secs 20] [--rate 30] [--warm 6] [--query proto=1] [--server-pid PID] [--paused]
//       live tab at speed RATE for SECS seconds: bytes over the wire per second (CDP Network encodedDataLength, by
//       endpoint), requests per second, JSON parse ms per second (Response.json patched), apply ms per second
//       (the page's COMMS counters; older code: none), script/task ms per second (CDP Performance), fps, ticks
//       played per second, server CPU s per second (ps, --server-pid).
//   node tools/comms_check.mjs verify URL OUT [--ticks 300] [--step 1] [--at X,Y] [--live 15] [--cmds 20]
//       0. live: a protocol-2 tab plays LIVE seconds while CMDS commands change the tax rate (snapshots and frames
//          re-recorded at the same tick); then the server is paused; its frames, snapshot and terrain (built
//          from deltas) must equal the server's full ones;
//       1. data: every recorded frame in the last TICKS ticks fetched with the delta protocol (v=2, chained from a
//          keyframe) equals the full frame (old protocol), and every building snapshot chained by deltas equals the
//          full snapshot (deep equal, key order ignored);
//       2. pixels: the page in replay mode with ?proto=1 (old protocol, full frames and snapshots) and without it,
//          clock frozen (performance.now), playhead stepped over the same ticks; per tick a readPixels hash of the
//          whole canvas at the same camera. Differing ticks are saved as OUT/<proto>_<tick>.png.
//       The server is paused after step 0 (POST /control {"paused": true}) so the recording does not move meanwhile.
import { launch } from "./play_cdp.mjs";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const [MODE, URL_, OUT] = a;
if (!MODE || !URL_) { console.error("usage: node tools/comms_check.mjs measure|verify URL [OUT] [...]"); process.exit(2); }
const sleep = ms => new Promise(r => setTimeout(r, ms));
const base = new URL(URL_);
const post = (path, body) => fetch(new URL(path, base), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(r => r.json());
const ready = "typeof STARTUP !== 'undefined' && STARTUP.ready > 0 && !document.getElementById('loading')";
const prefs = JSON.stringify({ muted: true, tips: false, hires: { choice: Object.fromEntries(["terrain", "buildings", "figures", "ui"].map(s => [s, "original"])), filter: "mip", text: true } });

async function openPage(b, q) {
  await b.open(new URL("play/atlas/compressed.json", base).href, 800);       // same origin, without the page
  await b.eval(`localStorage.setItem("polis-play", ${JSON.stringify(prefs)}), 0`);
  const u = new URL(URL_);
  for (const kv of (q || "").split("&").filter(Boolean)) { const [k, v] = kv.split("="); u.searchParams.set(k, v ?? ""); }
  await b.open(u.href);
  await b.waitFor(ready, 180000);
  await b.eval("(typeof setMuted === 'function' && setMuted(true), 0)");
  await b.waitFor("FRAMES.length > 0 && P.f0 && S", 60000);
}

// in-page counters: JSON parse time of every fetch answer, frames drawn, playhead progress
const COUNT = `window.CC = { parse: 0, n: 0, raf: 0, t0: P.t, a0: window.COMMS ? COMMS.apply : 0 };
(() => { const j = Response.prototype.json;
  Response.prototype.json = async function () { const t = await this.text(), s = performance.now(); const v = JSON.parse(t); CC.parse += performance.now() - s; CC.n++; return v; };
  const loop = () => { CC.raf++; requestAnimationFrame(loop); }; requestAnimationFrame(loop);
  // message windows stop the city (screenPauses): closed as they come, so the run keeps the speed
  setInterval(() => { if (window.MsgWin && MsgWin.isOpen()) { MsgWin.close(); CC.msgs = (CC.msgs || 0) + 1; } }, 50); })(); 0`;

function cpuSecs(pid) {
  if (!pid) return null;
  const s = execFileSync("ps", ["-o", "cputime=", "-p", String(pid)]).toString().trim();     // [[dd-]hh:]mm:ss.cc
  return s.split(":").reverse().reduce((t, v, i) => t + parseFloat(v) * [1, 60, 3600][i], 0);
}

async function measure() {
  const SECS = +opt("--secs", 20), RATE = +opt("--rate", 30), WARM = +opt("--warm", 6), PID = opt("--server-pid");
  await post("control", { rate: RATE, paused: a.includes("--paused") });
  const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
  try {
    await openPage(b, opt("--query", ""));
    await b.eval("setLive(true), (window.MsgWin && MsgWin.isOpen() && MsgWin.close()), 0");
    await sleep(WARM * 1000);
    const reqs = new Map(), bytes = {}, count = {};
    await b.send("Network.enable");
    await b.send("Performance.enable");
    const kind = u => { const p = new URL(u).pathname; return /frames?\.json$/.test(p) ? "frames" : p === "/state.json" ? "state" : p === "/terrain.json" ? "terrain" : /\.json$/.test(p) && !p.startsWith("/play/") ? p.replace(/^\//, "") : "assets"; };
    const onMsg = m => {
      if (m.method === "Network.requestWillBeSent") reqs.set(m.params.requestId, kind(m.params.request.url));
      else if (m.method === "Network.loadingFinished" && reqs.has(m.params.requestId)) {
        const k = reqs.get(m.params.requestId);
        bytes[k] = (bytes[k] || 0) + m.params.encodedDataLength; count[k] = (count[k] || 0) + 1;
      }
    };
    const metrics = async () => Object.fromEntries((await b.send("Performance.getMetrics")).metrics.map(m => [m.name, m.value]));
    await b.eval(COUNT);
    const m0 = await metrics(), c0 = cpuSecs(PID), w0 = Date.now();
    b.onEvent = onMsg;
    await sleep(SECS * 1000);
    b.onEvent = null;
    const m1 = await metrics(), c1 = cpuSecs(PID), dt = (Date.now() - w0) / 1000;
    const cc = await b.eval("({ parse: CC.parse, n: CC.n, raf: CC.raf, ticks: P.t - CC.t0, apply: window.COMMS ? COMMS.apply - CC.a0 : null, live: P.live, liveTick: P.liveTick, t: P.t, pauses: screenPauses(), paused: P.paused, msg: CC.msgs || 0 })");
    const total = Object.entries(bytes).reduce((s, [k, v]) => s + (k === "assets" ? 0 : v), 0);   // sprites loaded on demand: not traffic
    const per = v => +(v / dt).toFixed(1);
    const out = {
      secs: +dt.toFixed(1), rate: RATE, query: opt("--query", ""),
      KBps: +(total / 1024 / dt).toFixed(1), KBps_by: Object.fromEntries(Object.entries(bytes).map(([k, v]) => [k, +(v / 1024 / dt).toFixed(1)])),
      reqps: Object.fromEntries(Object.entries(count).map(([k, v]) => [k, per(v)])),
      parse_ms_per_s: +(cc.parse / dt).toFixed(2), apply_ms_per_s: cc.apply == null ? null : +(cc.apply / dt).toFixed(2),
      script_ms_per_s: +((m1.ScriptDuration - m0.ScriptDuration) * 1000 / dt).toFixed(1),
      task_ms_per_s: +((m1.TaskDuration - m0.TaskDuration) * 1000 / dt).toFixed(1),
      fps: per(cc.raf), ticks_per_s: per(cc.ticks), trail: +(cc.liveTick - cc.t).toFixed(1),
      screen_pauses: cc.pauses, paused: cc.paused, msgs_closed: cc.msg,
      server_cpu: c0 == null ? null : +((c1 - c0) / dt).toFixed(3),
    };
    console.log(JSON.stringify(out));
  } finally { await b.close(); }
}

// deep equality, key order ignored
function same(x, y) {
  if (x === y) return true;
  if (typeof x !== "object" || typeof y !== "object" || !x || !y || Array.isArray(x) !== Array.isArray(y)) return false;
  if (Array.isArray(x)) return x.length === y.length && x.every((v, i) => same(v, y[i]));
  const kx = Object.keys(x), ky = Object.keys(y);
  return kx.length === ky.length && kx.every(k => k in y && same(x[k], y[k]));
}
function firstDiff(x, y, p = "") {
  if (same(x, y)) return null;
  if (typeof x !== "object" || typeof y !== "object" || !x || !y) return `${p}: ${JSON.stringify(x)?.slice(0, 120)} != ${JSON.stringify(y)?.slice(0, 120)}`;
  for (const k of new Set([...Object.keys(x), ...Object.keys(y)])) { const d = firstDiff(x[k], y[k], `${p}.${k}`); if (d) return d; }
  return `${p}: key order/length`;
}

async function verify() {
  const TICKS = +opt("--ticks", 300), STEP = +opt("--step", 1), LIVE = +opt("--live", 15);
  mkdirSync(OUT, { recursive: true });
  const get = q => fetch(new URL(q, base)).then(r => r.json());
  // 0. a live tab (protocol 2) for LIVE seconds, then the server paused: the tab's frames, snapshot and terrain
  //    (built from deltas) against the server's full ones
  let lbad = 0;
  if (LIVE > 0) {
    await post("control", { paused: false });
    const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
    try {
      await openPage(b, "");
      await b.eval("setLive(true), setInterval(() => { if (window.MsgWin && MsgWin.isOpen()) MsgWin.close(); }, 50), 0");
      // commands meanwhile (re-recorded frames and snapshots at the same tick): the tax rate back and forth
      const CMDS = +opt("--cmds", 20), t0 = Date.now();
      let n = 0, tax = (await get("state.json?lite=1")).city.tax;
      while (Date.now() - t0 < LIVE * 1000) {
        await sleep(LIVE * 1000 / (CMDS + 1));
        if (n < CMDS) { await post("cmd", { cmds: [`tax ${n % 2 ? tax : tax + 2}`] }); n++; }
      }
      if (n % 2) await post("cmd", { cmds: [`tax ${tax}`] });
      await sleep(500);
      await post("control", { paused: true });
      await sleep(2500);
      const r = await b.eval(`(async () => {
        const same = ${same.toString()};
        const j = async u => (await fetch(u)).json();
        const out = { frames: FRAMES.length, fbad: [], sbad: 0, tbad: 0, comms: COMMS };
        const full = (await j("frames.json?from=" + FRAMES[0].tick + "&to=" + bufEnd())).frames, by = new Map(full.map(f => [f.tick, f]));
        for (const f of FRAMES) if (!same(f, by.get(f.tick))) out.fbad.push(f.tick);
        const s = await j("state.json?lite=1");
        out.seq = [S.seq, s.seq]; out.sbad = same(S, s) ? 0 : 1;
        const t = await j("terrain.json");
        // the page's own caches and marks on T (buildTerrain: altMap, cliffMap, lavaMap; warnedViews) are left out
        // (bugs.md 463: lavaMap was compared since the lava picture, fcf4c0c); altMap must be T.alt's
        const { tid, altMap, cliffMap, lavaMap, warnedViews, ...a } = T, { tid: tid2, ...c } = t;
        out.altMap = altMap ? altMap.size === (T.alt || []).length && (T.alt || []).every(r => same(altMap.get(r[0]), r.slice(1))) : null;
        out.tid = [tid, tid2]; out.tbad = same(a, c) ? 0 : 1;
        out.tkeys = [...new Set([...Object.keys(a), ...Object.keys(c)])].filter(k => !same(a[k], c[k]))
          .map(k => k + (Array.isArray(a[k]) && Array.isArray(c[k]) ? ":" + a[k].length + "/" + c[k].length + "@" + a[k].findIndex((v, i) => !same(v, c[k][i])) : ""));
        return out;
      })()`);
      console.log(`live tab: ${r.frames} frames (${r.fbad.length} differ${r.fbad.length ? ": " + r.fbad.slice(0, 5) : ""}), snapshot seq ${r.seq} ${r.sbad ? "differs" : "equal"}, terrain tid ${r.tid} ${r.tbad ? "differs " + r.tkeys : "equal"} (altMap ${r.altMap}); ${JSON.stringify(r.comms)}`);
      lbad = r.fbad.length + r.sbad + r.tbad + (r.altMap === false ? 1 : 0);
      const exc = b.logs.filter(l => l.startsWith("EXC") || l.startsWith("comms"));
      if (exc.length) console.log("page:", exc.slice(0, 5));
    } finally { await b.close(); }
  }
  await post("control", { paused: true });
  // 1. data
  const meta = (await get(`frames.json?from=0&to=0`)).meta;
  const t1 = meta.live_tick, t0 = Math.max(meta.first, t1 - TICKS);
  const full = (await get(`frames.json?from=${t0}&to=${t1}`)).frames;
  const dl = await get(`frames.json?from=${t0}&to=${t1}&v=2`);
  const C = await import("../viewer/play/comms.js"), { decodeFrames, applyState } = C.default || C;
  const got = decodeFrames(null, dl.frames).frames;
  let bad = 0;
  if (got.length !== full.length) { console.log("frame count differs", got.length, full.length); bad++; }
  for (let i = 0; i < Math.min(got.length, full.length); i++) {
    const d = firstDiff(got[i], full[i]);
    if (d) { if (bad++ < 5) console.log("frame", full[i].tick, d); }
  }
  // deltas from a base in the middle (what a playing tab asks for)
  for (let k = 1; k < full.length; k += Math.max(1, Math.floor(full.length / 20))) {
    const r = await get(`frames.json?from=${full[k].tick + 1}&to=${t1}&v=2&base=${full[k].fs}`);
    const dec = decodeFrames(got[k], r.frames).frames;
    for (const f of dec) { const j = full.findIndex(g => g.tick === f.tick); const d = j < 0 ? "no such tick" : firstDiff(f, full[j]); if (d) { if (bad++ < 5) console.log("frame from base", full[k].tick, f.tick, d); } }
  }
  console.log(`frames: ${full.length} (ticks ${t0}..${t1}), keyframe chain + 20 bases checked, ${bad} differ`);
  // snapshots: each recorded state's full copy vs the chain from the one before
  const states = (await get("state_ticks.json")).states;          // [[tick, seq]]
  let sbad = 0, prev = null;
  for (const [tick, seq] of states.slice(-12)) {
    const fullS = await get(`state.json?t=${tick}&lite=1`);
    if (prev) {
      const r = await get(`state.json?t=${tick}&lite=1&v=2&base=${prev.seq}`);
      const s = r.deltas ? applyState(prev, r).state : r;
      const d = firstDiff(s, fullS);
      if (d) { if (sbad++ < 5) console.log("state", tick, seq, d); }
      if (!r.deltas) console.log("state", tick, "came full");
    }
    prev = fullS;
  }
  console.log(`states: ${Math.min(12, states.length)} checked, ${sbad} differ`);
  // 2. pixels
  const ticks = [];
  for (let t = Math.max(meta.first + 1, t1 - TICKS); t <= t1 - 2; t += STEP) ticks.push(t);
  const AT = opt("--at");
  const hashes = {};
  for (const proto of ["proto=1", ""]) {
    const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
    try {
      await openPage(b, proto);
      await b.eval("setLive(false), P.playing = false, 0");
      if (AT) await b.eval(`(() => { const [x, y] = [${AT}]; cam.x = tileX(x, y) - innerWidth / 2; cam.y = tileY(x, y) - innerHeight / 2; })()`);
      await b.eval(`window.VC = {
        async at(t) {
          jumpTo(t); P.playing = false;
          const t0 = Date.now();
          while (Date.now() - t0 < 20000) {
            const okF = FRAMES.length && FRAMES[0].tick <= t && bufEnd() > t;
            if (okF && S && P.stateTick === VC.stateAt(t) && !busy.state) break;
            await new Promise(r => setTimeout(r, 30));
          }
          P.t = t;
          // sprite files loaded on demand (heroes, monsters, gods, armies: loadAtlases) or freed textures loaded
          // again (resumeSheet) draw nothing until they are in: draw (frozen clock) until none is in flight, so
          // the hash does not depend on how fast this tab fetched them (bugs.md 463)
          const frozen = () => { const now = performance.now; performance.now = () => 1e8; try { advance(); drawFrame(); } finally { performance.now = now; } };
          const idle = () => (typeof ATLAS_PENDING === "undefined" || ATLAS_PENDING === 0) && (typeof RESUMING === "undefined" || RESUMING.size === 0);
          for (let k = 0, t1 = Date.now(); Date.now() - t1 < 20000; k++) {
            await new Promise(r => requestAnimationFrame(r));
            P.t = t; frozen();
            await new Promise(r => setTimeout(r, 30));
            if (idle() && k >= 1) break;
          }
          P.t = t;
          return new Promise(res => requestAnimationFrame(() => {
            const now = performance.now; performance.now = () => 1e8;
            try { advance(); drawFrame(); } finally { performance.now = now; }
            const gl = R.gl, W = gl.drawingBufferWidth, H = gl.drawingBufferHeight, px = new Uint8Array(W * H * 4);
            gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, px);
            const u = new Uint32Array(px.buffer); let h1 = 0x811c9dc5, h2 = 7;
            for (let i = 0; i < u.length; i++) { const v = u[i]; h1 = Math.imul(h1 ^ v, 16777619); h2 = (Math.imul(h2, 31) + v) | 0; }
            VC.last = { px, W, H };
            res({ h: (h1 >>> 0).toString(16) + (h2 >>> 0).toString(16), st: P.stateTick, f0: P.f0 && P.f0.tick });
          }));
        },
        stateAt(t) { let s = -1; for (const [k] of VC.states) if (k <= t) s = k; return s; },
        png() { const { px, W, H } = VC.last, c = document.createElement("canvas"); c.width = W; c.height = H;
          const x = c.getContext("2d"), d = x.createImageData(W, H);
          for (let y = 0; y < H; y++) d.data.set(px.subarray((H - 1 - y) * W * 4, (H - y) * W * 4), y * W * 4);
          x.putImageData(d, 0, 0); return c.toDataURL("image/png").split(",")[1]; },
      }; 0`);
      await b.eval(`fetch("state_ticks.json").then(r => r.json()).then(j => { VC.states = j.states; return 0; })`);
      const H = hashes[proto || "v2"] = {};
      for (const t of ticks) {
        const r = await b.eval(`VC.at(${t})`);
        H[t] = r.h;
        if (proto === "" && hashes["proto=1"][t] !== r.h) writeFileSync(`${OUT}/v2_${t}.png`, Buffer.from(await b.eval("VC.png()"), "base64"));
        if (proto && a.includes("--keep")) writeFileSync(`${OUT}/p1_${t}.png`, Buffer.from(await b.eval("VC.png()"), "base64"));
      }
      const exc = b.logs.filter(l => l.startsWith("EXC"));
      if (exc.length) console.log(proto || "v2", "page errors:", exc.slice(0, 5));
    } finally { await b.close(); }
  }
  const diff = ticks.filter(t => hashes["proto=1"][t] !== hashes.v2[t]);
  const distinct = new Set(Object.values(hashes.v2)).size;
  console.log(`pixels: ${ticks.length} ticks (${ticks[0]}..${ticks[ticks.length - 1]}), ${distinct} distinct pictures, ${diff.length} differ${diff.length ? ": " + diff.slice(0, 10).join(",") : ""}`);
  writeFileSync(`${OUT}/verify.json`, JSON.stringify({ ticks, hashes, frameDiffs: bad, stateDiffs: sbad }, null, 1));
  process.exitCode = lbad || bad || sbad || diff.length ? 1 : 0;
}

if (MODE === "measure") await measure();
else if (MODE === "verify") await verify();
else { console.error("mode: measure | verify"); process.exit(2); }
