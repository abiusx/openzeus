// Frame readback of rate-100 looks in play mode (bug 393: gods' appear / cast / attack, the archer's shot, melee).
// Headless Chrome (tools/play_cdp.mjs, muted) on YOUR OWN server (a save copy): wraps scene.js blockIndex, unpauses
// the server, and records for every figure of the given roles drawn the block name and frame per game tick (P.t),
// then pauses again. Prints per block the runs "frame@ticks A..B" so the ticks per frame can be read off. Role keys
// are prefixes of MAP.walkers.roles ("god" = every god_*; enemy_infantry, enemy_cavalry, rabble, ...); blocks: walk,
// fight, die and the work looks (a figure drawn twice in a frame, the picture and its click box, records twice: same
// frame). --id N: one walker only (fights / looks; the walker ids drawn are listed without it; -1 = walking figures).
//
// --pos: also the fighters' drawn spot per tick (drawFight's tile position minus the walker's tile: the closing-in,
// look [11]); --sounds: the figure sounds asked for (audio.sfxAt replaced by a recorder: the browser is muted by
// play_cdp's --mute-audio, the page's own mute stays off so play.js fightSounds runs) as "tick file" (bug 393).
//
//   node tools/god_rate_check.mjs http://127.0.0.1:8811/play.html [--secs 12] [--roles god,enemy_archer] [--id N]
//        [--pos] [--sounds] [--rate R]
import { launch } from "./play_cdp.mjs";

const URL_ = process.argv[2];
const opt = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const SECS = +opt("--secs", 12), ROLES = opt("--roles", "god,enemy_archer").split(","), ONE = opt("--id", null);
const POS = process.argv.includes("--pos"), SOUNDS = process.argv.includes("--sounds"), RATE = opt("--rate", null);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const base = URL_.replace(/\/play\.html.*$/, "");

const HOOK = `(() => {
  if (window.__rc) return true;
  window.__rc = { rec: [], pos: [], snd: [] };
  const roles = ${JSON.stringify(ROLES)};
  const orig = blockIndex;
  const pre = roles.map(r => r === "god" ? "god_" : r);
  const name = (blk) => {
    for (const [rk, m] of Object.entries(MAP.walkers.roles)) {
      if (!pre.some(p => rk.startsWith(p))) continue;
      for (const k of ["walk", "fight", "die"]) if (m[k] === blk) return rk + ":" + k;
      for (const [k, v] of Object.entries(m.work || {})) if (v === blk) return rk + ":" + k;
    }
    return null;
  };
  // the walker drawn: drawFight's id (fights, deaths, work looks); -1 for a walking figure
  let cur = -1;
  const df = drawFight;
  let fa = null;
  drawFight = function (out, m, role, id, a) { cur = id; fa = a; try { return df.apply(this, arguments); } finally { cur = -1; fa = null; } };
  const fs = figureSpot;
  figureSpot = function (fx, fy) {
    if (cur !== -1 && fa) window.__rc.pos.push([Math.floor(P.t), cur, fa[0][0],
      +(fx - fa[1]).toFixed(3), +(fy - fa[2]).toFixed(3), JSON.stringify(fa[0][11] || null), fa[0][12] == null ? null : fa[0][12]]);
    return fs.apply(this, arguments);
  };
  if (typeof audio !== "undefined" && audio) audio.sfxAt = (file, pan) => { window.__rc.snd.push([Math.floor(P.t), file]); };
  blockIndex = function (blk, dir, fr) {
    const n = name(blk);
    if (n) window.__rc.rec.push([Math.floor(P.t), n, fr % (blk.frames || 1), cur]);
    return orig(blk, dir, fr);
  };
  return true;
})()`;

const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
try {
  await b.open(URL_);
  await b.waitFor("typeof P !== 'undefined' && P.f0 && window.Gods && MAP.walkers && MAP.walkers.roles.god_zeus", 180000);
  await b.eval(SOUNDS ? "setMuted(false); true" : "setMuted(true); true");
  await b.eval(HOOK);
  // centre on the first god / archer so it is drawn
  await b.eval(`(() => { const w = P.f0.walkers.find(w => ${JSON.stringify(ROLES)}.includes(w[3])); if (!w) return false;
    cam.x = tileX(w[1], w[2]) - (UIX.panelX * UIX.scale) / 2 / cam.zoom; cam.y = tileY(w[1], w[2]) - innerHeight / 2 / cam.zoom; return true; })()`);
  await sleep(1500);
  // --rate R: the server's speed for the recording (start the server slow, e.g. --speed 1, so the page loads first)
  await fetch(base + "/control", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(RATE ? { paused: false, rate: +RATE } : { paused: false }) });
  await sleep(SECS * 1000);
  await fetch(base + "/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paused: true }) });
  const rec = await b.eval("window.__rc.rec");
  const by = {}, ids = new Set();
  for (const [t, n, fr, id] of rec) {
    ids.add(id);
    if (ONE != null && String(id) !== ONE) continue;
    const key = ONE != null ? n : n + " #" + id;
    const runs = by[key] || (by[key] = []);
    const last = runs[runs.length - 1];
    if (last && last[0] === fr && t >= last[1] && t <= last[2] + 1) last[2] = Math.max(last[2], t);
    else if (!last || last[0] !== fr || t > last[2] + 1) runs.push([fr, t, t]);
  }
  if (ONE == null) console.log("walkers drawn: " + [...ids].join(" "));
  for (const [n, runs] of Object.entries(by)) {
    console.log(n);
    console.log("  " + runs.map(([fr, a, z]) => `${fr}@${a}..${z}`).join(" "));
  }
  if (POS) {
    const seen = new Set();
    console.log("fight spots: tick id kind dx dy [p, heading] counter_ref");
    for (const r of await b.eval("window.__rc.pos")) {
      const k = r.join(" ");
      if (seen.has(k) || (ONE != null && String(r[1]) !== ONE)) continue;
      seen.add(k);
      console.log("  " + k);
    }
  }
  if (SOUNDS) {
    console.log("sounds: tick file");
    for (const r of await b.eval("window.__rc.snd")) console.log("  " + r.join(" "));
  }
} finally {
  await b.close();
}
