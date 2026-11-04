// GPU memory, texture units and whole-map pixel regression of play mode (docs/play/gpu.md). Headless muted Chrome
// (tools/play_cdp.mjs, dpr 1.25) on your own server (a COPY of a save, paused; not a game in play).
//
//   node tools/gpu_check.mjs URL OUT --tag TAG [--tex png,default] [--hires original|remacri] [--views 0,4]
//        [--zooms 1,2] [--ref OUT/OTHER.json] [--only NAME,..] [--units N] [--evict] [--no-pixels] [--startup N]
//
// Per texture mode (?tex=png, or "default" = the page's own choice: compressed originals and hi-res sets):
// - loads the page with the hi-res sets set to --hires (prefs), waits until the on-demand atlases of the figures on
//   the map (gods, monsters, heroes, armies) stop loading;
// - memory: the page's texture list (gl.js SpriteGL.memory(); older code: computed from R.sheets / R.hi) and the
//   phys footprint of Chrome's GPU and renderer processes (macOS `footprint`);
// - pixels: freezes the page's clock (performance.now) and playhead (the last frame's tick), then for each view x
//   zoom moves the camera over the whole map in screen-sized steps and, in a rAF, draws the map (drawFrame, no UI)
//   and reads the whole canvas back with gl.readPixels; per shot a hash of the pixels. --ref: compare with another
//   run's hashes and save the differing shots as OUT/<TAG>_<shot>.png (rerun the other code with --only those names
//   to get its pictures); --units N: the renderer's texture-unit budget (gl.js unitBudget; forces split draws);
//   --evict: frees every atlas texture first, so each shot loads what it needs again (play.js resumeSheet).
// Writes OUT/<TAG>.json: {modes: {tex: {mem, gpuMB, rendererMB, startup, tick, shots: {name: hash}}}}.
import { launch } from "./play_cdp.mjs";
import { execFileSync, execSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
const [URL_, OUT] = a;
if (!URL_ || !OUT || !opt("--tag")) { console.error("usage: node tools/gpu_check.mjs URL OUT --tag TAG [...]"); process.exit(2); }
mkdirSync(OUT, { recursive: true });
const TAG = opt("--tag"), TEX = opt("--tex", "png,default").split(","), HI = opt("--hires", "original");
const VIEWS = opt("--views", "0,4").split(",").map(Number), ZOOMS = opt("--zooms", "1,2").split(",").map(Number);
const REF = opt("--ref") ? JSON.parse(readFileSync(opt("--ref"))) : null, ONLY = opt("--only") ? new Set(opt("--only").split(",")) : null;
const UNITS = opt("--units"), PIXELS = !a.includes("--no-pixels"), STARTUP_N = +opt("--startup", 0), EVICT = a.includes("--evict");
const sleep = ms => new Promise(r => setTimeout(r, ms));

const PAGE = `window.GC = {
  mem() {
    if (R.memory) return R.memory();
    const L = [];                                    // older code: from the sheet list
    R.sheets.forEach((s, i) => L.push({ what: "sheet " + i, w: s.w, h: s.h, fmt: s.cmp ? texFormat() : "rgba8", bytes: s.w * s.h * (s.cmp ? 1 : 4) }));
    R.hi.forEach((h, k) => h && L.push({ what: "hi-res " + k, layers: h.n, fmt: h.fmt, bytes: Math.round(h.n * 4096 * 4096 * (h.fmt === "png" ? 4 : 1) * 4 / 3) }));
    return L;
  },
  cpu() {                                            // decoded images / downloaded buffers the page keeps
    let imgs = 0, px = 0;
    for (const f of Object.values(atlas)) for (const i of f.imgs || []) if (i) { imgs++; px += i.width * i.height; }
    return { atlasImages: imgs, atlasImageMB: +(px * 4 / 1048576).toFixed(1), images: IMAGES.size, buffers: typeof BUFFERS !== "undefined" ? BUFFERS.size : 0 };
  },
  freeze() {
    const T0 = 1e8;                                  // the same clock in every run (animations); textures count as just used
    if (R.used) R.used.fill(T0);
    performance.now = () => T0;
    P.paused = true; P.playing = false;
    clampCam = () => {};
    P.t = FRAMES[FRAMES.length - 1].tick;
    waterStep = 0; waterAt = -1e9;
    return P.t;
  },
  setView(v) { let n = 0; while (VIEW !== v && n++ < 4) rotateView(2); return VIEW; },
  bounds() {
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const [x, y] of [[0, 0], [N - 1, 0], [0, N - 1], [N - 1, N - 1]]) {
      const X = tileX(x, y), Y = tileY(x, y);
      x0 = Math.min(x0, X); x1 = Math.max(x1, X + 58); y0 = Math.min(y0, Y); y1 = Math.max(y1, Y + 30);
    }
    return [x0, y0 - 300, x1, y1 + 30, R.canvas.clientWidth, R.canvas.clientHeight];
  },
  evict() {                                          // --evict: free every atlas texture (SpriteGL.suspend)
    let n = 0;
    R.sheets.forEach((s, i) => { if (s.tex && s.info && s.info.uploads) { R.suspend(i); n++; } });
    return n;
  },
  async shot(x, y, z) {
    const draw = () => new Promise(res => requestAnimationFrame(() => { cam.x = x; cam.y = y; cam.zoom = z; drawFrame(); res(); }));
    if (typeof RESUMING !== "undefined") {             // freed textures this view needs: loaded again first (resumeSheet)
      await draw();
      if (RESUMING.size) { GC.resumed = (GC.resumed || 0) + RESUMING.size; await Promise.all([...RESUMING.values()]); }
    }
    return new Promise(res => requestAnimationFrame(() => {
      cam.x = x; cam.y = y; cam.zoom = z;
      drawFrame();
      const gl = R.gl, W = gl.drawingBufferWidth, H = gl.drawingBufferHeight, px = new Uint8Array(W * H * 4);
      gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, px);
      const u = new Uint32Array(px.buffer);
      let h1 = 0x811c9dc5, h2 = 7, lit = 0;
      for (let i = 0; i < u.length; i++) { const v = u[i]; h1 = Math.imul(h1 ^ v, 16777619); h2 = (Math.imul(h2, 31) + v) | 0; if ((v & 0xffffff) !== 0) lit++; }
      GC.last = { px, W, H };
      res({ h: (h1 >>> 0).toString(16) + (h2 >>> 0).toString(16), lit, err: gl.getError() });
    }));
  },
  png() {
    const { px, W, H } = GC.last, c = document.createElement("canvas");
    c.width = W; c.height = H;
    const x = c.getContext("2d"), d = x.createImageData(W, H);
    for (let y = 0; y < H; y++) d.data.set(px.subarray((H - 1 - y) * W * 4, (H - y) * W * 4), y * W * 4);
    x.putImageData(d, 0, 0);
    return c.toDataURL("image/png").split(",")[1];
  },
};`;

function footprintMB(pid) {
  try { const m = execFileSync("footprint", [String(pid)]).toString().match(/Footprint: ([\d.]+) (KB|MB|GB)/); return m ? +(+m[1] * { KB: 1 / 1024, MB: 1, GB: 1024 }[m[2]]).toFixed(0) : null; } catch (e) { return null; }
}
function children(pid, type) {
  return execSync("ps -ax -o pid=,ppid=,command=").toString().split("\n").map(l => l.trim().match(/^(\d+)\s+(\d+)\s+(.*)$/))
    .filter(m => m && +m[2] === pid && m[3].includes(`--type=${type}`)).map(m => +m[1]);
}

const result = { tag: TAG, hires: HI, modes: {} };
const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
const prefs = JSON.stringify({ muted: true, tips: false, hires: { choice: Object.fromEntries(["terrain", "buildings", "figures", "ui"].map(s => [s, HI])), filter: "mip", text: true } });
const ready = "typeof STARTUP !== 'undefined' && STARTUP.ready > 0 && !document.getElementById('loading')";
let diffs = 0;
try {
  await b.open(new URL("play/atlas/compressed.json", URL_).href, 800);   // same origin, without the page
  await b.eval(`localStorage.setItem("polis-play", ${JSON.stringify(prefs)}), 0`);
  for (const tex of TEX) {
    const q = [tex !== "default" && `tex=${tex}`, UNITS && `units=${UNITS}`].filter(Boolean).join("&");
    const M = result.modes[tex] = { startup: [] };
    for (let k = 0; k <= STARTUP_N; k++) {
      await b.open(`${URL_}?k=${k}${q ? "&" + q : ""}`);
      await b.waitFor(ready, 180000);
      if (k) M.startup.push(await b.eval("JSON.stringify(STARTUP)").then(JSON.parse));
    }
    await b.eval(PAGE);
    await b.eval("(typeof setMuted === 'function' && setMuted(true), 0)");
    await b.waitFor("FRAMES.length > 0 && P.f0", 60000);
    let n = -1;                                         // on-demand atlases (gods.js, heroes.js, military.js)
    for (let i = 0; i < 40; i++) { await sleep(500); const m = await b.eval("Object.keys(atlas).length"); if (m === n && i > 6) break; n = m; }
    M.atlases = await b.eval("Object.keys(atlas).sort()");
    M.mem = await b.eval("GC.mem()");
    M.textureMB = +(M.mem.reduce((t, e) => t + e.bytes, 0) / 1048576).toFixed(1);
    M.cpu = await b.eval("GC.cpu()");
    M.gpuMB = children(b.pid, "gpu-process").map(footprintMB)[0];
    M.rendererMB = children(b.pid, "renderer").map(footprintMB);
    console.log(JSON.stringify({ tex, textureMB: M.textureMB, gpuMB: M.gpuMB, rendererMB: M.rendererMB, cpu: M.cpu, startup: M.startup.map(s => Math.round(s.ready)) }));
    if (!PIXELS) continue;
    M.tick = await b.eval("GC.freeze()");
    if (EVICT) console.log("evicted", await b.eval("GC.evict()"), "textures");
    await sleep(300);
    M.shots = {};
    for (const v of VIEWS) {
      await b.eval(`GC.setView(${v})`);
      const [x0, y0, x1, y1, cw, ch] = await b.eval("GC.bounds()");
      for (const z of ZOOMS) {
        const sx = Math.floor(cw / z), sy = Math.floor(ch / z);
        let lit = 0, cnt = 0;
        for (let y = y0; y < y1; y += sy) for (let x = x0; x < x1; x += sx) {
          const name = `${tex}_v${v}_z${z}_${x}_${y}`;
          if (ONLY && !ONLY.has(name)) continue;
          const r = await b.eval(`GC.shot(${x}, ${y}, ${z})`);
          if (r.err) console.log("GL error", r.err, name);
          M.shots[name] = r.h; lit += r.lit; cnt++;
          const ref = REF && REF.modes[tex] && REF.modes[tex].shots && REF.modes[tex].shots[name];
          if (ONLY || (ref && ref !== r.h)) {
            writeFileSync(`${OUT}/${TAG}_${name}.png`, Buffer.from(await b.eval("GC.png()"), "base64"));
            if (ref) { diffs++; console.log("differs", name); }
          }
        }
        console.log(JSON.stringify({ tex, view: v, zoom: z, shots: cnt, litPixels: lit, resumed: await b.eval("GC.resumed || 0") }));
      }
    }
  }
  const exc = b.logs.filter(l => l.startsWith("EXC") || /too many|error/i.test(l));
  if (exc.length) console.log("page errors:", exc.slice(0, 8));
  result.errors = exc.slice(0, 20);
} finally {
  writeFileSync(`${OUT}/${TAG}.json`, JSON.stringify(result, null, 1));
  await b.close();
}
if (REF) console.log(diffs ? `${diffs} shots differ from ${opt("--ref")}` : `all shots equal to ${opt("--ref")}`);
