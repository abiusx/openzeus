// Where play mode draws a god's work picture (blessing / curse / bolt-throwing) against the exe's rule
// (walker_draw 0x0044FEF0: picture top-left = tile corner + (31 + walk table x, 25 + walk table y) - anchor for a figure
// standing on its tile; docs/play/gods.md "Oracle shots", the stage plan 1H steps 2-4).
// On YOUR OWN live server (a save copy, not a game in play): sends CMD (e.g. "godvisit apollo") to /cmd, runs the sim fast,
// and in headless Chrome at dpr 1.25 (tools/play_cdp.mjs) waits until a god walker shows the work look KIND (sim
// gods.figures.look: cast = blessing / curse, attack = bolts); then pauses, centres it, and for every frame drawn
// prints the picture (file:index), its top-left minus the tile corner (tileX, tileY) and minus the anchor: the point
// (cx - corner) that the exe's rule puts at (31, 25) - elevation for a god standing still (direction table entry 0).
// Also reads the frame back (gl.readPixels after the page's frame) and counts the picture's opaque texels drawn
// unchanged (the blended pictures one 5-bit step darker: tools/play_atlas.py blended()).
//
//   node tools/gods_pose_check.mjs http://127.0.0.1:8797 "godvisit apollo" cast [--rate 300] [--max 600] [--shot DIR]
import { launch } from "./play_cdp.mjs";

const [BASE, CMD, KIND] = process.argv.slice(2);
const opt = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const RATE = +opt("--rate", 300), MAX = +opt("--max", 600), SHOT = opt("--shot", null);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const post = async (path, body) => (await fetch(BASE + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();

const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
try {
  await b.open(BASE + "/play.html");          // default sheets (?tex=png runs out of texture units on the baseline)
  await b.waitFor("typeof P !== 'undefined' && P.f0 && window.Gods && MAP.walkers && MAP.walkers.roles.god_zeus", 180000);
  await b.eval("setMuted(true); true");
  if (CMD) console.log("cmd:", JSON.stringify(await post("/cmd", { cmd: CMD })));
  await post("/control", { rate: RATE, paused: false });
  const god = "P.f1 && P.f1.walkers.find(w => w[3] === 'god')";
  for (let i = 0; i < MAX && !(await b.eval(`!!(${god})`)); i++) await sleep(250);
  await post("/control", { rate: 30, paused: false });
  let found = null;
  for (let i = 0; i < 10 * MAX && !found; i++) {
    await sleep(30);
    found = await b.eval(`(() => { const w = P.f1 && P.f1.walkers.find(w => w[3] === 'god' && w[7] && w[7][0] === 'work' && w[7][8] === '${KIND}'); return w ? [w[0], w[4], P.f1.tick] : null; })()`);
  }
  if (!found) { await post("/control", { paused: true }); console.log("no god with look", KIND); process.exit(1); }
  await post("/control", { rate: 3, paused: false });          // slow while the look runs
  console.log("god", found[1], "id", found[0], "look", KIND, "at tick", found[2]);
  const seen = new Set();
  await b.eval(`(() => { const w = P.f1.walkers.find(w => w[0] === ${found[0]}); cam.zoom = 1; cam.x = tileX(w[1], w[2]) - 300; cam.y = tileY(w[1], w[2]) - 300; return 0; })()`);
  for (let k = 0; k < 120; k++) {
    await sleep(120);
    const r = await b.eval(`(async () => {
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const hit = WALKER_HITS.find(h => h[0] === ${found[0]}); if (!hit) return { missing: true, t: P.t };
      const sp = sprite(hit[8], hit[9]);
      return { t: Math.floor(P.t), file: hit[8], idx: hit[9], tile: [hit[6], hit[7]],
               topLeft: [hit[1] - tileX(hit[6], hit[7]), hit[2] - tileY(hit[6], hit[7])],
               point: [hit[1] + sp.ax - tileX(hit[6], hit[7]), hit[2] + sp.ay - tileY(hit[6], hit[7])] };
    })()`);
    if (!r || r.missing) continue;   // its atlas still loading, or off the drawn area
    const key = `${r.file}:${r.idx}`;
    if (!seen.has(key)) { seen.add(key); console.log(JSON.stringify(r)); }
    if (SHOT && k === 5) await b.shot(`${SHOT}/pose_${found[1]}_${KIND}.png`);
  }
  await post("/control", { paused: true });
} finally {
  await b.close();
}
