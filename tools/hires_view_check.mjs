// Hi-res / compressed-texture check in play mode (docs/play/hires.md "Checks"): headless Chrome (tools/play_cdp.mjs:
// own profile, muted, dpr 1.25) on your own server (a COPY of a save, not a game in play).
// For each texture format (?tex=, gl.js / play.js texFormat) and hi-res setting it loads the page, pauses the city
// and, for each view x zoom x place, reads the frame back with gl.readPixels in a rAF after the page's frame
// (CLAUDE.md "Rendering checks") and measures on the map area:
//   seam: device pixels within 1 px of a tile edge (flat ground, from pixelWorld) vs the rest; a pixel is a dot
//         when its luminance is off the mean of the 4 pixels 3 px away by > 25 (bugs.md 171); per 1000 pixels.
//   black: pure black pixels (gaps between tiles show the black clear colour, bugs.md 62).
// and saves a screenshot per shot (OUT/<tag>_v<view>_z<zoom>_<place>.png). Places: "x,y" tiles or building keys
// (the first building whose key matches, e.g. palace, sanctuary, stadium).
//   node tools/hires_view_check.mjs http://127.0.0.1:8811/play.html OUT_DIR [--tex astc,bc7,png]
//        [--hires remacri|original] [--views 0,2,4,6] [--zooms 1,2,5] [--at "111,113;palace;stadium"] [--startup N]
// --startup N: also N reloads per format, reporting play.js STARTUP (ms since navigation: maps, atlases, hires, ready).
import { launch } from "./play_cdp.mjs";
import { mkdirSync, writeFileSync } from "node:fs";

const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const [URL_, OUT] = a;
if (!URL_ || !OUT) { console.error("usage: node tools/hires_view_check.mjs URL OUT_DIR [--tex ..] [--hires ..] [--views ..] [--zooms ..] [--at ..]"); process.exit(2); }
mkdirSync(OUT, { recursive: true });
const TEX = opt("--tex", "astc,bc7,png").split(","), HI = opt("--hires", "remacri");
const VIEWS = opt("--views", "0,2,4,6").split(",").map(Number), ZOOMS = opt("--zooms", "1,2,5").split(",").map(Number);
const AT = opt("--at", "111,113;palace").split(";"), STARTUP_N = +opt("--startup", 0);
const [W, H] = opt("--size", "1280x800").split("x").map(Number);

const PAGE = `window.HVC = {
  setView(v) { let n = 0; while (VIEW !== v && n++ < 4) rotateView(2); return VIEW; },
  find(p) {
    if (/^\\d+,\\d+$/.test(p)) return p.split(",").map(Number);
    const b = S.buildings.find(b => b.key.includes(p));
    return b ? [b.x + ((b.w || 1) - 1) / 2, b.y + ((b.h || 1) - 1) / 2] : null;
  },
  centre(x, y, z) {
    cam.zoom = z;
    const sx = (UIX.panelX * UIX.scale) / 2 / cam.zoom, sy = innerHeight / 2 / cam.zoom;
    cam.x = tileX(x, y) + 29 - sx; cam.y = tileY(x, y) + 15 - sy;
  },
  grab() {
    return new Promise(res => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => {
      const gl = R.gl, Wd = gl.drawingBufferWidth, Hd = gl.drawingBufferHeight, px = new Uint8Array(Wd * Hd * 4);
      gl.readPixels(0, 0, Wd, Hd, gl.RGBA, gl.UNSIGNED_BYTE, px);
      const dpr = devicePixelRatio, mapW = Math.floor(UIX.panelX * UIX.scale * dpr) - 4, top = Math.ceil(40 * dpr);
      const L = (x, y) => { const i = ((Hd - 1 - y) * Wd + x) * 4; return 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2]; };
      const perp = 26.7 * cam.zoom * dpr;          // device px between parallel tile edges
      let ns = 0, no = 0, ds = 0, dO = 0, black = 0;
      for (let y = top + 3; y < Hd - 40 * dpr; y++) for (let x = 3; x < mapW - 3; x++) {
        const [tx, ty] = pixelWorld(cam.x + x / dpr / cam.zoom, cam.y + y / dpr / cam.zoom);
        const fx = tx - Math.floor(tx), fy = ty - Math.floor(ty);
        const seam = Math.min(fx, 1 - fx, fy, 1 - fy) * perp < 1;
        const i = ((Hd - 1 - y) * Wd + x) * 4;
        if (px[i] === 0 && px[i + 1] === 0 && px[i + 2] === 0) black++;
        const d = Math.abs(L(x, y) - (L(x - 3, y) + L(x + 3, y) + L(x, y - 3) + L(x, y + 3)) / 4) > 25;
        if (seam) { ns++; ds += d; } else { no++; dO += d; }
      }
      res({ seam: +(1000 * ds / Math.max(ns, 1)).toFixed(2), off: +(1000 * dO / Math.max(no, 1)).toFixed(2), ns, black, err: gl.getError() });
    }))));
  },
};`;

const b = await launch({ width: W, height: H, dpr: +opt("--dpr", 1.25) });
const prefs = JSON.stringify({ muted: true, tips: false, hires: { choice: Object.fromEntries(["terrain", "buildings", "figures", "ui"].map(s => [s, HI])), filter: "mip", text: true } });
const ready = "typeof STARTUP !== 'undefined' && STARTUP.ready > 0 && !document.getElementById('loading')";
const results = [];
try {
  await b.open(new URL("play/atlas/hires/index.json", URL_).href, 1000);   // same origin, without the page (it saves its prefs)
  await b.eval(`localStorage.setItem("polis-play", ${JSON.stringify(prefs)}), 0`);
  for (const tex of TEX) {
    const url = `${URL_}?tex=${tex}`;
    for (let k = 0; k <= STARTUP_N; k++) {
      await b.open(url + `&k=${k}`);
      await b.waitFor(ready, 120000);
      if (k) console.log(JSON.stringify({ tex, hires: HI, startup: await b.eval("JSON.stringify(STARTUP)").then(JSON.parse) }));
    }
    await b.eval(PAGE);
    await b.eval("(typeof setMuted === 'function' && setMuted(true), P.playing && togglePlay(), 0)");
    const fmt = await b.eval("[texFormat(), R.hi.map(h => h && h.fmt).join('/')].join(' ')");
    if (HI !== "original" && fmt.includes("//")) throw new Error("hi-res sets not loaded: " + fmt);
    for (const v of VIEWS) {
      await b.eval(`HVC.setView(${v})`);
      for (const z of ZOOMS) for (const p of AT) {
        const at = await b.eval(`HVC.find(${JSON.stringify(p)})`);
        if (!at) { console.log(`no ${p}`); continue; }
        await b.eval(`HVC.centre(${at[0]}, ${at[1]}, ${z})`);
        const m = await b.eval("HVC.grab()");
        const tag = `${tex}_${HI}_v${v}_z${z}_${p.replace(/[^a-z0-9]+/gi, "-")}`;
        await b.shot(`${OUT}/${tag}.png`);
        const r = { tex, fmt, hires: HI, view: v, zoom: z, at: p, ...m };
        results.push(r);
        console.log(JSON.stringify(r));
      }
    }
  }
  const exc = b.logs.filter(l => l.startsWith("EXC"));
  if (exc.length) console.log("exceptions:", exc.slice(0, 5));
} finally {
  writeFileSync(`${OUT}/results_${HI}.json`, JSON.stringify(results, null, 1));
  await b.close();
}
