// Play-mode check of monster / hero animation frames (bug 386; docs/logic/heroes-monsters.md "Monster animation"):
// the exe advances a monster's / hero's frame +1 every tick over the whole group, walking, standing and fighting
// (figure_hero_update 0x004C9D18, monster_anim_info 0x00533B60). On YOUR OWN server (a save copy with a hero and / or
// a monster in view, running), centres tile X Y, then for --samples page frames records the picture index drawn for
// each figure of the given sprite files (WALKER_HITS) with the sim tick, and prints per figure: the indices seen,
// the frames (index - group start) / 8 seen, and the number of distinct frames against the group's count.
//
//   node tools/hero_frames_check.mjs http://127.0.0.1:8805/play.html X Y [--files zeus_heracles,zeus_hydra]
//        [--samples 120] [--shot OUT.png] [--dpr 1.25] [--zoom 2] [--unpause RATE]
// --unpause: the save copy starts paused (Game.live_paused); the check sets that rate and unpauses once centred.
import { launch } from "./play_cdp.mjs";

const [URL_, X, Y] = process.argv.slice(2);
const opt = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const FILES = opt("--files", "zeus_heracles,zeus_hydra").split(","), N = +opt("--samples", 120);
const SHOT = opt("--shot", null), DPR = +opt("--dpr", 1.25), ZOOM = +opt("--zoom", 1);

const b = await launch({ width: 1280, height: 800, dpr: DPR });
try {
  await b.open(URL_);
  for (let i = 0; i < 60 && !(await b.eval("!!(window.P && P.f0 && MAP.walkers)")); i++) await new Promise(r => setTimeout(r, 500));
  await b.eval(`cam.zoom = ${ZOOM}; cam.x = tileX(${X}, ${Y}) - (UIX.panelX * UIX.scale) / 2 / cam.zoom;
                cam.y = tileY(${X}, ${Y}) - innerHeight / 2 / cam.zoom; true`);
  await new Promise(r => setTimeout(r, 3000));
  if (opt("--unpause", null)) await fetch(new URL("/control", URL_), { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paused: false, rate: +opt("--unpause", 10) }) });
  const seen = {};
  for (let i = 0; i < N; i++) {
    const r = await b.eval(`new Promise(res => requestAnimationFrame(() => requestAnimationFrame(() =>
      res({ t: Math.floor(P.t), h: WALKER_HITS.filter(h => ${JSON.stringify(FILES)}.includes(h[8])).map(h => [h[0], h[8], h[9]]) }))))`);
    for (const [id, file, idx] of r.h) (seen[id + " " + file] ||= []).push([r.t, idx]);
  }
  const roles = await b.eval(`JSON.stringify(Object.fromEntries(Object.entries(MAP.walkers.roles).filter(([k, v]) => ${JSON.stringify(FILES)}.includes(v.file))))`);
  const R = Object.values(JSON.parse(roles));
  for (const [k, v] of Object.entries(seen)) {
    const file = k.split(" ")[1], m = R.find(r => r.file === file);
    const grp = idx => ["walk", "fight", "die", "special"].map(g => [g, m[g]]).find(([, blk]) => idx >= blk.start && idx < blk.start + blk.frames * blk.dirs);
    const by = {};
    for (const [t, idx] of v) {
      const g = grp(idx);
      if (!g) continue;
      const fr = Math.floor((idx - g[1].start) / g[1].dirs);
      (by[g[0]] ||= { n: g[1].frames, fr: new Set(), ticks: new Set(), seq: [] });
      by[g[0]].fr.add(fr); by[g[0]].ticks.add(t);
      if (by[g[0]].seq.length < 40) by[g[0]].seq.push(`${t}:${fr}`);
    }
    for (const [g, o] of Object.entries(by))
      console.log(`${k} ${g}: ${o.fr.size}/${o.n} frames over ${o.ticks.size} ticks; seq ${o.seq.join(" ")}`);
  }
  if (SHOT) {
    if (opt("--unpause", null)) await fetch(new URL("/control", URL_), { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paused: true }) });
    await b.shot(SHOT);
  }
} finally { await b.close(); }
