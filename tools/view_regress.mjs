// Before/after picture check of a play-mode change (CLAUDE.md "Rendering checks"): the same paused save served by two
// servers (old code, new code; each a COPY of the save, not a game in play), shot in headless muted Chrome at dpr 1.25 at
// each target tile in views 0/2/4/6 and zoom 100 % / 200 %, and compared pixel by pixel (PNG sprites, ?tex=png).
//   node tools/view_regress.mjs URL_OLD URL_NEW OUTDIR [--no-walkers] X,Y[:name] ...
// --no-walkers: pixels inside any figure's picture (Scene.walkerHits, either page) and the panel are not compared
// (figures keep moving on each page's own playhead, so their poses differ between two pages)
// Pause both servers first (POST {"paused": true} to /control) so both show the same tick. Prints per shot the share
// of changed pixels and the changed box; writes OUTDIR/<name>_v<view>_z<zoom>_{old,new,diff}.png for changed shots.
import { launch } from "./play_cdp.mjs";
import { writeFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";

const args = process.argv.slice(2), noWalkers = args.includes("--no-walkers");
const [urlA, urlB, out, ...targets] = args.filter(a => a !== "--no-walkers");
mkdirSync(out, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function shots(url, tag) {
  const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
  try {
    await b.open(url + (url.includes("?") ? "&" : "?") + "tex=png");
    await b.waitFor("typeof S !== 'undefined' && S && T && P.f0 && objBatch && objBatch.n > 0", 180000);
    await b.eval("P.playing && togglePlay(), clampCam = () => {}, 0");
    for (const t of targets) {
      const [xy, name = xy.replace(",", "_")] = t.split(":"), [x, y] = xy.split(",").map(Number);
      for (const view of [0, 2, 4, 6]) for (const z of [1, 2]) {
        await b.eval(`(() => { { let n = 0; while (VIEW !== ${view} && n++ < 4) rotateView(2); } cam.zoom = ${z};
          cam.x = tileX(${x}, ${y}) - UIX.panelX * UIX.scale / 2 / cam.zoom; cam.y = tileY(${x}, ${y}) - innerHeight / 2 / cam.zoom; return 1; })()`);
        await sleep(900);
        await b.shot(`${out}/${name}_v${view}_z${z}_${tag}.png`);
        writeFileSync(`${out}/${name}_v${view}_z${z}_${tag}.json`, JSON.stringify(await b.eval(`(() => {
          const d = devicePixelRatio, r = Scene.walkerHits().map(h => [(h[1] - cam.x) * cam.zoom * d, (h[2] - cam.y) * cam.zoom * d,
            h[3] * cam.zoom * d, h[4] * cam.zoom * d]);
          return { panelX: UIX.panelX * UIX.scale * d, walkers: r }; })()`)));
      }
    }
  } finally { await b.close(); }
}
await shots(urlA, "old");
await shots(urlB, "new");
const py = `
import sys, numpy as np
from PIL import Image
import json
out, mask, names = sys.argv[1], sys.argv[2] == "1", sys.argv[3:]
for n in names:
    a = np.asarray(Image.open(f"{out}/{n}_old.png").convert("RGB")).astype(int)
    b = np.asarray(Image.open(f"{out}/{n}_new.png").convert("RGB")).astype(int)
    d = np.abs(a - b).max(axis=2) > 0
    if mask:
        for t in ("old", "new"):
            j = json.load(open(f"{out}/{n}_{t}.json"))
            d[:, int(j["panelX"]):] = False
            for x, y, w, h in j["walkers"]:
                d[max(0, int(y) - 2):int(y + h) + 3, max(0, int(x) - 2):int(x + w) + 3] = False
    ys, xs = np.nonzero(d)
    box = f"x {xs.min()}..{xs.max()} y {ys.min()}..{ys.max()}" if len(xs) else "-"
    print(f"{n}: {100 * d.mean():.3f} % changed ({int(d.sum())} px) {box}")
    if d.any():
        Image.fromarray((d * 255).astype(np.uint8)).save(f"{out}/{n}_diff.png")
`;
const names = [];
for (const t of targets) { const [xy, name = xy.replace(",", "_")] = t.split(":"); for (const v of [0, 2, 4, 6]) for (const z of [1, 2]) names.push(`${name}_v${v}_z${z}`); }
process.stdout.write(execFileSync("python3", ["-c", py, out, noWalkers ? "1" : "0", ...names]).toString());
