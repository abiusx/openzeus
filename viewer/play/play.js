// Play mode (docs/play-mode.md): the live simulation drawn with the original game's sprites.
// Data: /terrain.json (the map's terrain images), /state.json (buildings), /frames.json (walkers every
// 1..15 ticks, interpolated), /data/play/*.json (sprite/audio mapping tables). Protocol 2 (docs/play/comms.md,
// comms.js): deltas on what the tab holds, polls only when the buffer runs low; ?proto=1 = the old full answers.
"use strict";

const N = 228;
const ATLAS_FILES = ["Zeus_Terrain", "Zeus_General", "SprMain", "SprAmbient", "Poseidon_Loaded", "Zeus_Interface",
                     "destruction", "Zeus_Greek", "Poseidon_Unloaded", "Zeus_Unloaded", "PoseidonImps", "Zeus_Fonts"];
// image id = collection * 0x4000 + n (refs/zeus-poseidon-arm64/formats/map.md); v247 maps: +2 for >= 2
const COLLECTIONS = { 1: "Zeus_Interface", 2: "Zeus_Unloaded", 3: "Poseidon_Unloaded", 4: "Zeus_General",
                      5: "Zeus_Terrain", 16: "SprAmbient", 17: "destruction", 51: "SprMain", 52: "Poseidon_Loaded" };
// fallback building images until data/play/buildings.json exists (same groups as the sim viewer)
const FALLBACK_GROUPS = {
  wheat_farm: "SPR_B_FARM", onion_farm: "SPR_B_FARM", carrot_farm: "SPR_B_FARM", sheep_farm: "SPR_B_SHEARER",
  goat_farm: "SPR_B_DAIRY", olive_tree: "SPR_OLIVE_TREE", grapevine: "SPR_GRAPEVINE", growers_lodge: "SPR_B_GROWERS_LODGE",
  timber_mill: "SPR_B_TIMBER_MILL", marble_quarry: "SPR_B_STONECUTTER_LODGE", winery: "SPR_B_WINERY", oil_press: "SPR_B_OILER",
  granary: "SPR_B_GRANARY", storehouse: "SPR_B_SBAY_GOODS", fountain: "SPR_B_FOUNTAIN1", infirmary: "SPR_B_INFIRMARY",
  maintenance: "SPR_B_MAINTENANCE_OFFICE", guardpost: "SPR_B_WATCHPOST", tax_office: "SPR_B_TAX_OFFICE",
  palace: "SPR_B_PALACE1_FRONT", podium: "SPR_B_PODIUM", gymnasium: "SPR_B_GYMNASIUM", theatre: "SPR_B_THEATER",
  stadium: "SPR_B_STADIUM_N", gardens: "SPR_GARDENS1", food_vendor: "SPR_B_STALL_FOOD", fleece_vendor: "SPR_B_STALL_FLEECE",
  oil_vendor: "SPR_B_STALL_OIL", wine_vendor: "SPR_B_STALL_WINE", arms_vendor: "SPR_B_STALL_ARMOR",
  horse_trainer: "SPR_B_STALL_HORSE", foundry: "SPR_B_FOUNDRY", mint: "SPR_B_MINT", armory: "SPR_B_ARMORY",
  horse_ranch: "SPR_B_RANCH_HOUSE", hunting_lodge: "SPR_B_HUNTING_LODGE", fishing_wharf: "SPR_B_FISHERY",
  urchin_quay: "SPR_B_URCHIN_COLLECTOR", sculpture_studio: "SPR_B_SCULPT_STUDIO", college: "SPR_B_COLLEGE",
  drama_school: "SPR_B_DRAMA_SCHOOL", roadblock: "SPR_B_ROADBLOCK",
};

// --- atlases ---------------------------------------------------------------------------------------
const atlas = {};                                 // file -> {images, groups, sheetIdx, yOff, imgs, cache, set, demand}
// Texture layout (docs/play/gpu.md). The sheets of one load are grouped by hi-res set (index.json: the set whose files
// include the file; files in no set: one group each) and by format: GPU-compressed (tools/hires_compress.py
// --originals, compressed.json: no PNG decode, docs/play/hires.md "Startup") or PNG (the interface, fonts and the
// alpha-blended files). A group's sheets (4096 wide, heights powers of two: tools/play_atlas.py) are stacked tallest
// first into textures whose heights are powers of two adding up to the group's total (its binary decomposition,
// each at most 16384): no empty rows, and every texture size a power of two as before. A sprite's y gets its sheet's
// offset in the texture. Each texture remembers its uploads (info.uploads) so it can be freed and loaded again:
// textures of files a hi-res set covers completely are freed while the set is on (hiresTextures), files loaded on
// demand (gods, monsters, heroes, armies) when unused for EVICT_MS (evictIdle); a draw that needs a freed texture
// loads it again (resumeSheet). Decoded images are not kept, but Zeus_Interface's (ui.js firstPixels reads the
// minimap colours from it).
let ATLAS_PENDING = 0;                            // loadAtlases calls in flight (tools/comms_check.mjs waits for 0)
async function loadAtlases(r, files) {
  ATLAS_PENDING++;
  try { return await loadAtlasesNow(r, files); } finally { ATLAS_PENDING--; }
}
async function loadAtlasesNow(r, files) {
  const C = await atlasCompressed(), ix = await hiresIndex();
  // all files at once: first every file's json, then every sheet (so the download bar knows them all from the
  // start: a GPU sheet is width x height bytes, compressed.json)
  const jsons = (await Promise.all(files.filter(f => !atlas[f]).map(async f => {
    try { return [f, await (await fetch(`play/atlas/${f}.json`)).json()]; } catch (e) { console.warn("no atlas", f); return null; }
  }))).filter(Boolean);
  const loaded = await Promise.all(jsons.map(async ([f, j]) => [f, j, await Promise.all(j.sheets.map(s => C && C.sheets[s]
    ? (u => loadBuffer(u, C.sheets[s][0] * C.sheets[s][1]).then(buf => ({ buf, w: C.sheets[s][0], h: C.sheets[s][1], url: u })))(`play/atlas/${s.replace(/\.png$/, C.suffix)}?v=${C.version}`)
    : (u => loadImage(u).then(img => ({ img, w: img.width, h: img.height, url: u })))(`play/atlas/${s}`)))]));
  const setOf = f => Object.keys(ix.sets).find(s => (ix.sets[s].files || []).includes(f)), demand = !!STARTUP.atlases;
  const groups = new Map();                       // "<set or file>/<format>" -> [{f, k, sheet}]
  for (const [f, j, sheets] of loaded) {
    const set = setOf(f);
    atlas[f] = { images: j.images, groups: j.groups, sheetIdx: [], yOff: [], imgs: sheets.map(() => null), cache: {}, set, demand };
    sheets.forEach((sh, k) => {
      const key = `${set || f}/${sh.buf ? C.fmt : "png"}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({ f, k, sh });
    });
  }
  const MAX = Math.min(16384, r.gl.getParameter(r.gl.MAX_TEXTURE_SIZE));
  for (const [key, list] of groups) {
    list.sort((p, q) => q.sh.h - p.sh.h);         // stable: tallest first
    const fmt = key.slice(key.lastIndexOf("/") + 1);
    let rest = list.reduce((t, e) => t + e.sh.h, 0), i = 0;
    while (i < list.length) {
      let H = MAX;
      while (H > rest) H >>= 1;                    // >= the next sheet's height (all powers of two)
      const info = { what: key, files: new Set(), uploads: [], evict: demand && !atlas[list[i].f].set };
      const id = r.addEmptySheet(4096, H, fmt, info);
      for (let y = 0; i < list.length && y + list[i].sh.h <= H; i++) {
        const { f, k, sh } = list[i], A = atlas[f];
        if (sh.buf) { r.subCompressed(id, fmt, sh.buf, 0, y, sh.w, sh.h); BUFFERS.delete(sh.url); }
        else {
          r.subImage(id, sh.img, 0, y);
          IMAGES.delete(sh.url);
          if (f === "Zeus_Interface") A.imgs[k] = sh.img;
        }
        info.files.add(f);
        info.uploads.push({ url: sh.url, cmp: !!sh.buf, y, w: sh.w, h: sh.h });
        A.sheetIdx[k] = id; A.yOff[k] = y;
        y += sh.h; rest -= sh.h;
      }
    }
  }
}
// a freed texture (SpriteGL.suspend) a draw needs: its sheets downloaded again (HTTP cache) and uploaded
const RESUMING = new Map();
function resumeSheet(i) {
  const s = R.sheets[i], inf = s && s.info;
  if (!inf || !inf.uploads || s.tex) return Promise.resolve();
  if (!RESUMING.has(i)) RESUMING.set(i, (async () => {
    try {
      const data = await Promise.all(inf.uploads.map(u => u.cmp ? loadBuffer(u.url) : loadImage(u.url)));
      if (!s.tex) {
        R.restore(i);
        inf.uploads.forEach((u, k) => u.cmp ? R.subCompressed(i, s.fmt, data[k], 0, u.y, u.w, u.h) : R.subImage(i, data[k], 0, u.y));
      }
      inf.uploads.forEach(u => (u.cmp ? BUFFERS : IMAGES).delete(u.url));
    } catch (e) { console.warn("atlas texture", inf.what, e); } finally { RESUMING.delete(i); }
  })());
  return RESUMING.get(i);
}
// Freed when no draw used them for a while (a texture still drawn, e.g. by a batch built before, stays): files loaded
// on demand (gods, monsters, heroes, armies) after EVICT_MS, the original's textures a hi-res set covers (hiresTextures)
// after COVERED_MS
const EVICT_MS = 60000, COVERED_MS = 3000;
function evictIdle() {
  const now = performance.now();
  R.sheets.forEach((s, i) => {
    const inf = s.info;
    if (s.tex && inf && inf.uploads && now - R.used[i] > (inf.covered ? COVERED_MS : inf.evict ? EVICT_MS : Infinity)) R.suspend(i);
  });
}
// marks the original's textures whose every file the hi-res sprites `over` (file -> Map) cover completely (evictIdle
// frees them); the others are loaded again if they were freed (awaited: turning a set off waits for its originals)
function hiresTextures(over) {
  const full = f => {
    const o = over[f], a = atlas[f];
    if (!o || !a) return false;
    for (const k in a.images) if (!o.has(+k)) return false;
    return true;
  };
  const wait = [];
  R.sheets.forEach((s, i) => {
    const inf = s.info;
    if (!inf || !inf.files || inf.evict) return;
    inf.covered = [...inf.files].every(full);
    if (!inf.covered && !s.tex) wait.push(resumeSheet(i));
  });
  return Promise.all(wait);
}
// Options: the GPU memory of the textures (SpriteGL.memory: bytes as allocated)
function gpuMemText() {
  const L = R.memory(), mb = b => Math.round(b / 1048576), hi = L.filter(e => e.hires).reduce((t, e) => t + e.bytes, 0);
  const all = L.reduce((t, e) => t + e.bytes, 0);
  return `GPU textures: ${mb(all)} MB (original sprites ${mb(all - hi)}, hi-res ${mb(hi)})`;
}
function showGpuMem() { const e = $("gpumem"); if (e) e.textContent = gpuMemText(); }
const STARTUP = {};                               // startup profile, ms since navigation: maps, atlases, hires, ready
// GPU-compressed textures (tools/hires_compress.py): the first of ASTC, BC7 this browser takes; `?tex=astc|bc7|png`
// in the page url forces one (testing; docs/play/hires.md)
let TEX_FMT = null;
function texFormat() {
  if (TEX_FMT) return TEX_FMT;
  const q = new URLSearchParams(location.search).get("tex");
  return (TEX_FMT = q ? (R.hasFormat(q) ? q : "png") : (["astc", "bc7"].find(f => R.hasFormat(f)) || "png"));
}
// The original's own sheets compressed (fast start, ~0.4 s instead of ~2.2 s) by default (user 10-29: slight colour
// variation is fine). Options "Original sprites: exact (PNG)" (prefs hires.origPng, next load) or `?tex=png` keeps
// the PNGs. Measured on scrub-granary vs the exe: PNG within 4 of the exe's 16-bit colours on the whole map; ASTC
// within 16 for 96 % of pixels (docs/play/hires.md). Pixel comparisons with the exe (oracle_view_compare.py) use ?tex=png.
let ATLAS_CMP;                                    // compressed.json for texFormat(), or null: the PNGs
async function atlasCompressed() {
  if (ATLAS_CMP === undefined) {
    ATLAS_CMP = null;
    const q = new URLSearchParams(location.search).get("tex");
    if (q ? q === "png" : (prefs().hires || {}).origPng) return ATLAS_CMP;
    try {
      const c = await (await fetch("play/atlas/compressed.json", { cache: "no-store" })).json(), f = texFormat();
      if (c.formats[f]) ATLAS_CMP = { fmt: f, suffix: c.formats[f].suffix, sheets: c.sheets, version: c.version };
    } catch (e) { }
  }
  return ATLAS_CMP;
}

// decoded images by url, so a download started early (hiresPrefetch) is picked up where it is used
// Download progress (ours, user 11-04: a first visit over a slow link takes minutes, "fine if you display a proper
// loading bar"): the sprite sheets come through fetchCounted, which counts the bytes as they stream in, per kind
// (orig: the original's sheets; hires: the hi-res sets'). The start screen (#loading, showLoading) and the hi-res
// box (hiresProgress) show sheets and MB done / total, a bar and the time left. The total grows while the sheets'
// answers start (Content-Length), within about a round trip of the first sheet, as every sheet is asked at once.
const DL = { orig: { got: 0, total: 0, files: 0, done: 0, t0: 0 }, hires: { got: 0, total: 0, files: 0, done: 0, t0: 0 } };
async function fetchCounted(url, expect = 0) {   // the body (ArrayBuffer); expect: its size if known before
  const c = DL[url.includes("play/atlas/hires/") ? "hires" : "orig"];
  if (!c.t0) c.t0 = performance.now();
  c.files++;
  c.total += expect;
  let got = 0, len = 0;
  try {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    // a compressed answer's Content-Length is not the size of what the stream yields: counted as it comes
    len = r.headers.get("Content-Encoding") ? 0 : +r.headers.get("Content-Length") || 0;
    c.total += len - expect;
    expect = 0;
    if (!r.body) { const b = await r.arrayBuffer(); got = b.byteLength; c.got += got; if (!len) c.total += got; return b; }
    const rd = r.body.getReader(), parts = [];
    for (;;) {
      const { done, value } = await rd.read();
      if (done) break;
      parts.push(value); got += value.length; c.got += value.length;
      if (!len) c.total += value.length;
    }
    c.done++;
    if (parts.length === 1 && parts[0].byteOffset === 0 && parts[0].byteLength === parts[0].buffer.byteLength) return parts[0].buffer;
    const out = new Uint8Array(got);
    let o = 0;
    for (const p of parts) { out.set(p, o); o += p.length; }
    return out.buffer;
  } catch (e) {
    c.got -= got; c.total -= expect + (len || got);   // a failed sheet is asked again later (resumeSheet): not counted
    throw e;
  } finally { c.files--; }
}
const mbText = b => (b / 1048576).toFixed(b < 10485760 ? 1 : 0);
function dlText(c) {                              // "12 / 43 sheets · 45 / 124 MB · 2.1 MB/s · about 1 min left"
  const now = performance.now(), secs = (now - c.t0) / 1000, rate = secs > 1 ? c.got / secs : 0;
  const left = rate > 0 && c.total > c.got ? (c.total - c.got) / rate : 0;
  const eta = left > 90 ? `about ${Math.round(left / 60)} min left` : left > 3 ? `about ${Math.round(left)} s left` : "";
  return [`${c.done} / ${c.done + c.files} sheets`, c.total ? `${mbText(c.got)} / ${mbText(c.total)} MB` : "",
          rate > 0 ? `${mbText(rate)} MB/s` : "", eta].filter(Boolean).join(" · ");
}
function showLoading() {                          // the start screen's bar (until the city shows): all sheets,
  const el = $("loading");                        // a line per kind (the chosen hi-res sets download alongside)
  if (!el) return false;
  const o = DL.orig, h = DL.hires, total = o.total + h.total, f = total ? Math.min(1, (o.got + h.got) / total) : 0;
  el.querySelector("i").style.width = `${Math.round(100 * f)}%`;
  el.querySelector(".num").textContent = o.done + o.files ? (h.done + h.files ? "Original: " : "") + dlText(o) : "";
  el.querySelector(".hi").textContent = h.done + h.files ? "Hi-res: " + dlText(h) : "";
  return true;
}
const IMAGES = new Map();
function loadImage(url) {                         // (fetched, so its bytes are counted: fetchCounted)
  if (!IMAGES.has(url)) IMAGES.set(url, (async () => {
    const u = URL.createObjectURL(new Blob([await fetchCounted(url)], { type: "image/png" }));
    try { const img = new Image(); img.src = u; await img.decode(); return img; } finally { URL.revokeObjectURL(u); }
  })());
  return IMAGES.get(url);
}

function sprite(file, index, orig) {             // orig: the original's image even when a hi-res set is on
  const o = !orig && HIRES.over[file];            // a hi-res variant chosen for this image (docs/play/hires.md)
  if (o) { const h = o.get(+index); if (h) return h; }
  const a = atlas[file];
  if (!a) return null;
  let s = a.cache[index];
  if (s !== undefined) return s;
  const e = a.images[index];
  // e[9]: a mirrored alpha-masked picture, drawn 1 px right of the exact mirror (tools/play_atlas.py, FUN_00414190)
  s = e ? { sheet: a.sheetIdx[e[0]], x: e[1], y: e[2] + a.yOff[e[0]], w: e[3], h: e[4], ax: e[5] - (e[9] || 0), ay: e[6], flip: e[7] != null, iso: e[8] || 0 } : null;
  a.cache[index] = s;
  return s;
}

// part of a sprite: offset and size in world px from its top-left (a hi-res sprite has uw/w texels per px)
function subSprite(sp, dx, dy, w, h) {
  const k = sp.uw ? sp.uw / sp.w : 1, o = { ...sp, x: sp.x + dx * k, y: sp.y + dy * k, w, h };
  if (sp.uw) { o.uw = w * k; o.uh = h * k; }
  return o;
}

// --- hi-res variants (docs/play/hires.md): upscales by tools/upscale_sprites.py in play/atlas/hires/, per set
// (terrain, buildings, figures, ui) one method at a time; each set's sheets are one texture array (gl.js
// hiAlloc). A hi-res sprite keeps the world size and anchor of the original (w, h, ax, ay in world px) and
// carries its texel size (uw, uh); its sheets are mipmapped.
const HIRES = { index: null, choice: {}, filter: "mip", text: true, origPng: false, over: {}, setOver: {}, busy: false };
// the set's GPU-compressed copy this browser can use (tools/hires_compress.py): {fmt, suffix, ...}, or null: the PNGs
const hiresCmp = S => { const f = texFormat(), c = S.compressed && S.compressed[f]; return c ? { ...c, fmt: f } : null; };
const hiresUrl = (ix, dir, sheet, cmp) =>
  `${dir}/${cmp ? sheet.replace(/\.png$/, cmp.suffix) : sheet}?v=${ix.version || 0}`;
const BUFFERS = new Map();                        // like IMAGES, for the .astc.bin / .bc7.bin downloads
function loadBuffer(url, expect = 0) {
  if (!BUFFERS.has(url)) BUFFERS.set(url, fetchCounted(url, expect));
  return BUFFERS.get(url);
}

// startup: begin downloading the chosen sets' sheets right away, alongside the original's atlases
async function hiresPrefetch(choice) {
  const ix = await hiresIndex();
  for (const [set, m] of Object.entries(choice || {})) {
    const S = ix.sets[set];
    if (!S || m === "original" || !S.methods.includes(m) || !S.files.length) continue;
    const dir = `play/atlas/hires/${set}/${m}`, astc = hiresCmp(S);
    fetch(`${dir}/${S.files[0]}.json`, { cache: "no-store" }).then(r => r.json())
      .then(j => j.sheets.forEach(s => (astc ? loadBuffer : loadImage)(hiresUrl(ix, dir, s, astc)).catch(() => {}))).catch(() => {});
  }
}
let hiresIndexP = null;                           // one request (hiresPrefetch, loadAtlases and the start all ask)
function hiresIndex() {
  return hiresIndexP || (hiresIndexP = fetch("play/atlas/hires/index.json", { cache: "no-store" }).then(r => r.json())
    .catch(() => ({ sets: {}, labels: {} })).then(ix => (HIRES.index = ix)));
}
// the progress box (#hiprog): the set's text and 0..1 (null hides the box); with HIRES.all = {done, total}
// (startup: several sets, in layers) an overall bar on top, each set counting its layers
let hiresShown = null;                            // the last hiresProgress arguments (refreshed by the bytes timer)
function hiresProgress(text, frac, layers = 1) {
  const box = $("hiprog");
  if (!box) return;
  box.hidden = text == null;
  hiresShown = text == null ? null : [text, frac, layers];
  if (text == null) return;
  const pct = f => `${Math.round(100 * Math.max(0, Math.min(1, f)))}%`, bars = box.querySelectorAll("i"), A = HIRES.all;
  const c = DL.hires;
  box.querySelector("span.set").textContent = text + (c.files && c.total ? ` · ${mbText(c.got)} / ${mbText(c.total)} MB` : "");
  box.querySelector("span.dl").textContent = c.files ? dlText(c) : "";
  bars[1].style.width = pct(frac);
  box.querySelector("span.all").textContent = A ? `Loading hi-res sprites: ${pct((A.done + frac * layers) / A.total)}` : "";
  if (A) bars[0].style.width = pct((A.done + frac * layers) / A.total);
}
const nextPaint = () => new Promise(r => setTimeout(r, 0));   // let the page repaint between layers

// set: a set of index.json; method: "original" or one of its methods; label: progress prefix (startup: "2 of 4")
async function setHires(set, method, label = "") {
  const ix = await hiresIndex(), S = ix.sets[set], a = Object.keys(ix.sets).indexOf(set);
  if (!S) return;
  if (a >= 4) return console.warn("hi-res: only 4 sets fit (gl.js HI_SETS)", set);
  if (method !== "original" && !S.methods.includes(method)) method = "original";
  HIRES.choice[set] = method;
  const over = {};                               // file -> Map(index -> sprite)
  if (method === "original") {                   // the original's textures back first (hiresTextures), then free the set
    await hiresTextures(hiresMerge({ ...HIRES.setOver, [set]: over }));
    R.hiFree(a);
  } else {
    const dir = `play/atlas/hires/${set}/${method}`;
    const js = await Promise.all(S.files.map(async f => [f, await (await fetch(`${dir}/${f}.json`, { cache: "no-store" })).json()]));
    const names = js.length ? js[0][1].sheets : [];  // the set's sheets, shared by its files
    const what = `Hi-res ${set}${label ? ` (${label})` : ""}`;
    const L = names.length, astc = hiresCmp(S);
    hiresProgress(`${what}: downloading ${L} sheets…`, 0, L);
    R.hiAlloc(a, names.length, astc ? astc.fmt : "png", set);
    if (astc) {                                     // GPU-compressed, mips included: straight to the texture
      let got = 0;
      await Promise.all(names.map(async (s, k) => {
        const url = hiresUrl(ix, dir, s, astc), buf = await loadBuffer(url);
        BUFFERS.delete(url);
        R.setHiLayerCompressed(a, k, buf);
        hiresProgress(`${what}: ${++got} / ${L}`, got / L, L);
      }));
    } else {
      let got = 0;
      const imgs = await Promise.all(names.map(async s => {
        const url = hiresUrl(ix, dir, s);              // version: a rebuilt sheet is never taken from the cache
        const img = await loadImage(url);
        IMAGES.delete(url);                           // on the GPU now: don't keep the decoded copy
        hiresProgress(`${what}: downloading ${++got} / ${L}`, 0.3 * got / L, L);
        return img;
      }));
      for (let k = 0; k < imgs.length; k++) {         // mip levels drawn on the GPU (gl.js MIP_FS): one layer per paint
        hiresProgress(`${what}: preparing ${k + 1} / ${L}`, 0.3 + 0.7 * k / L, L);
        await nextPaint();
        R.setHiLayer(a, k, imgs[k]);
      }
    }
    if (HIRES.all) HIRES.all.done += L;           // startup: the overall bar goes on to the next set
    else hiresProgress(null);
    for (const [f, j] of js) {
      const k = j.scale, m = new Map();
      for (const [i, e] of Object.entries(j.images))
        m.set(+i, { sheet: R.hiId(a, e[0]), x: e[1], y: e[2], uw: e[3], uh: e[4], w: e[3] / k, h: e[4] / k, ax: e[5] / k - (e[9] || 0), ay: e[6] / k, flip: e[7] != null, iso: e[8] || 0 });
      over[f] = m;
    }
  }
  HIRES.setOver[set] = over;
  HIRES.over = hiresMerge();
  hiresTextures(HIRES.over);                     // the original's textures this set covers: freed when unused
  if (T) buildTerrain();                          // ground pictures of any set (e.g. Zeus_General's) in the new sprites
  hiresMenu();
  save();
}
// HIRES.over from the sets' maps; the ui set's font glyphs (Zeus_Fonts) only with HIRES.text (Options "Hi-res text")
function hiresMerge(setOver = HIRES.setOver) {
  const over = {};
  for (const so of Object.values(setOver)) for (const [f, m] of Object.entries(so))
    if (f !== "Zeus_Fonts" || HIRES.text) over[f] = over[f] ? new Map([...over[f], ...m]) : m;
  return over;
}
async function setHiresText(on) {
  HIRES.text = on;
  const over = hiresMerge();
  await hiresTextures(over);
  HIRES.over = over;
  hiresMenu(); save();
}
function setHiresFilter(f) {
  HIRES.filter = f;
  R.setHiFilter(f);
  hiresMenu(); save();
}
// the dev Options menu: one select per set + the filter; keys: H cycles the walker, Shift+H the terrain
function hiresMenu() {
  const box = $("hires");
  if (!box || !HIRES.index) return;
  const L = HIRES.index.labels || {};
  if (!box.dataset.built) {
    box.dataset.built = 1;
    for (const [set, S] of Object.entries(HIRES.index.sets)) {
      const lab = document.createElement("label");
      lab.textContent = `Hi-res ${set}`;
      const sel = document.createElement("select");
      sel.id = "hires_" + set;
      for (const m of ["original", ...S.methods]) sel.add(new Option(L[m] || m, m));
      sel.onchange = () => setHires(set, sel.value).catch(e => { console.warn("hi-res", set, e); hiresProgress(null); });
      lab.appendChild(sel); box.appendChild(lab);
    }
    const lab = document.createElement("label");
    lab.textContent = "Hi-res filter";
    const sel = document.createElement("select");
    sel.id = "hires_filter";
    for (const [v, t] of [["mip", "mipmaps, crisp"], ["smooth", "trilinear"], ["nearest", "nearest (no mips)"]]) sel.add(new Option(t, v));
    sel.onchange = () => setHiresFilter(sel.value);
    lab.appendChild(sel); box.appendChild(lab);
    const tl = document.createElement("label"), ts = document.createElement("select");
    tl.textContent = "Hi-res text";                // the ui set's font glyphs, or the original's (with hi-res ui)
    ts.id = "hires_text";
    for (const [v, t] of [["on", "upscaled"], ["off", "original"]]) ts.add(new Option(t, v));
    ts.onchange = () => setHiresText(ts.value === "on");
    tl.appendChild(ts); box.appendChild(tl);
    const ol = document.createElement("label"), os = document.createElement("select");
    ol.textContent = "Original sprites";           // takes effect on the next load (atlasCompressed)
    os.id = "hires_origcmp";
    for (const [v, t] of [["cmp", "compressed, fast start (reload)"], ["png", "exact (PNG, reload)"]]) os.add(new Option(t, v));
    os.onchange = () => { HIRES.origPng = os.value === "png"; save(); toast("Original sprites: on the next page load"); };
    ol.appendChild(os); box.appendChild(ol);
    const gm = document.createElement("div");      // GPU memory of the textures (docs/play/gpu.md)
    gm.className = "lbl"; gm.id = "gpumem";
    box.appendChild(gm);
  }
  showGpuMem();
  for (const set of Object.keys(HIRES.index.sets)) { const s = $("hires_" + set); if (s) s.value = HIRES.choice[set] || "original"; }
  $("hires_filter").value = HIRES.filter;
  $("hires_text").value = HIRES.text ? "on" : "off";
  $("hires_origcmp").value = HIRES.origPng ? "png" : "cmp";
}
function cycleHires(set) {
  const S = HIRES.index && HIRES.index.sets[set];
  if (!S || HIRES.busy) return;
  const all = ["original", ...S.methods], cur = all.indexOf(HIRES.choice[set] || "original"), next = all[(cur + 1) % all.length];
  HIRES.busy = true;
  setHires(set, next).finally(() => { HIRES.busy = false; toast(`${set}: ${(HIRES.index.labels || {})[next] || next}`); });
}

function groupSprite(file, group, k = 0) {
  const g = atlas[file] && atlas[file].groups[group];
  return g ? sprite(file, g[0] + k) : null;
}

// --- geometry --------------------------------------------------------------------------------------
// View orientation (docs/play/rotation.md): the exe's 0x00DA2F88 = 0, 2, 4, 6; the screen grid of each view
// (FUN_00449FF0) is the plain one of the turned tile coordinates viewXY. EVERY drawer goes through these:
// tileX/tileY (world tile -> screen box), draw order: order.js (not tileDepth/footDepth), viewFoot (which tile is a
// footprint's top corner in this view), screenTile (the inverse), viewDir (walker headings).
let VIEW = 0;
function viewXY(x, y) {                           // world tile (may be fractional) -> turned tile
  switch (VIEW) {
    case 2: return [y, N - 1 - x];
    case 4: return [N - 1 - x, N - 1 - y];
    case 6: return [N - 1 - y, x];
    default: return [x, y];
  }
}
function worldXY(rx, ry) {                        // turned tile -> world tile
  switch (VIEW) {
    case 2: return [N - 1 - ry, rx];
    case 4: return [N - 1 - rx, N - 1 - ry];
    case 6: return [ry, N - 1 - rx];
    default: return [rx, ry];
  }
}
const tileX = (x, y) => { const [a, b] = viewXY(x, y); return (a - b) * 30; };   // top-left corner of the tile's 58x30 diamond box
const tileY = (x, y) => { const [a, b] = viewXY(x, y); return (a + b) * 15; };
const tileDepth = (x, y) => { const [a, b] = viewXY(x, y); return a + b; };        // draw order: back to front
// footprint x..x+w-1, y..y+h-1 in this view: ax, ay = the world tile at its top corner (draw anchor of the
// usual place() convention), lx, ly = the one at its left corner (the exe's anchor tile), w, h = its extent along the turned axes, depth = its bottom (front) tile's
function viewFoot(x, y, w = 1, h = w) {
  const [a0, b0] = viewXY(x, y), [a1, b1] = viewXY(x + w - 1, y + h - 1);
  const ra = Math.min(a0, a1), rb = Math.min(b0, b1), [ax, ay] = worldXY(ra, rb), [lx, ly] = worldXY(ra, Math.max(b0, b1));
  return { ax, ay, lx, ly, w: Math.abs(a1 - a0) + 1, h: Math.abs(b1 - b0) + 1, depth: Math.max(a0, a1) + Math.max(b0, b1) };
}
const footDepth = (x, y, w = 1, h = w) => viewFoot(x, y, w, h).depth;
const viewDir = d => (d - VIEW) & 7;              // world heading 0..7 -> picture direction (walker_draw 0x0044FEF0)
const viewMirror = () => VIEW === 2 || VIEW === 6; // building pictures drawn mirrored (building_mirrored 0x0045DC10)
const MIRRORED = new WeakMap();
function mirrored(sp) {                           // the same picture flipped left-right (anchor mirrored too)
  if (!sp) return sp;
  let m = MIRRORED.get(sp);
  if (!m) { m = { ...sp, flip: !sp.flip, ax: sp.w - 1 - (sp.ax || 0) }; MIRRORED.set(sp, m); }
  return m;
}

// --- state -----------------------------------------------------------------------------------------
const R = new SpriteGL(document.getElementById("view"));
const cam = { x: 0, y: 0, zoom: 1 };
let T = null;                                     // terrain.json
let S = null;                                     // state.json
const P = { t: 0, rate: 120, playing: true, liveTick: 0, f0: null, f1: null, stateTick: -1, stateSeq: -1 };
const FRAMES = [];                                // buffered server frames (sorted by tick), ~3 s ahead
const MAP = { buildings: null, walkers: null, audio: null, monuments: null, ui: null, fonts: null, strings_ui: null, info_panels: null,
              walker_info: null };
let terrainBatch, objBatch, waterBatch;
let WATER = [];                                   // animated water tiles: [x, y, px, py, first, phase base, kind]
let LAVA = [];                                    // lava tiles (terrain.json lava): [px, py, SPR_LAVA index, slot, centre, frame]
let lavaBatch;
// terrain pictures taller than their diamond (cliff faces, rocks, trees): sorted with the objects, so a
// building behind them is covered (bugs.md 84): [depth, x, sprite, left, top]
let TALL = [];
let OCC = null;                                   // tile -> index into S.buildings (+1), rebuilt per state
let audio = null;

function buildOcc() {
  OCC = new Int32Array(N * N);
  S.buildings.forEach((b, k) => {
    const w = b.w || b.size || 1, h = b.h || b.size || 1;
    for (let y = b.y; y < b.y + h; y++) for (let x = b.x; x < b.x + w; x++) if (x < N && y < N) OCC[y * N + x] = k + 1;
    for (const [p, n] of [[b.pier, 2], [b.corral, 4]]) if (p)     // dock pier, ranch corral (bugs.md 131, 134)
      for (let y = p[1]; y < p[1] + n; y++) for (let x = p[0]; x < p[0] + n; x++) if (x < N && y < N) OCC[y * N + x] = k + 1;
  });
}

function screenTileFlat(sx, sy) {                 // screen px -> the flat cell (FUN_0044A460: ignores elevation)
  const wx = cam.x + sx / cam.zoom - 29, wy = cam.y + sy / cam.zoom - 15;
  const [x, y] = worldXY(Math.round((wx / 30 + wy / 15) / 2), Math.round((wy / 15 - wx / 30) / 2));
  return x < 0 || y < 0 || x >= N || y >= N ? null : [x, y];
}
// the mouse's tile (FUN_0044A270): the flat cell moved forward (+1, +1 in view 0) by the projected elevation there
// (FUN_0045FB00), so the tile picked is the one drawn under the mouse on raised land (bugs.md 389)
function screenTile(sx, sy) {
  const t = screenTileFlat(sx, sy);
  if (!t || !T || !T.elev) return t;
  const [dx, dy] = PROJ_STEP[VIEW] || PROJ_STEP[0], p = projectedElev()[t[1] * N + t[0]];
  if (!p) return t;
  const x = t[0] - dx * p, y = t[1] - dy * p;
  return x < 0 || y < 0 || x >= N || y >= N ? null : [x, y];
}
// map_elevation_project 0x0045ED20 (projected altitude grid 0x008ECD0A), redone when the terrain or the view
// changes. Per tile (rows, then columns) of elevation e: the cell e steps back (view 0: (-e, -e)), if in the play
// area, takes max(its value, e); then, when the tile behind is higher by d > 0, the d cells behind that cell (the
// cliff face) get e + 1 .. e + d, overwritten as they come. Read only by the cursor pick.
const PROJ_STEP = { 0: [-1, -1], 2: [1, -1], 4: [1, 1], 6: [-1, 1] };
let projCache = null;
function projectedElev() {
  if (projCache && projCache.T === T && projCache.view === VIEW) return projCache.P;
  const P = new Int8Array(N * N), [dx, dy] = PROJ_STEP[VIEW] || PROJ_STEP[0];
  const play = (x, y) => x >= 0 && y >= 0 && x < N && y < N && !(T.flags[y * N + x] & 0x80000);
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    if (T.flags[y * N + x] & 0x80000) continue;   // the play area's rows only
    const e = T.elev[y * N + x] || 0;
    if (!play(x + e * dx, y + e * dy)) continue;
    const k = (y + e * dy) * N + x + e * dx;
    if (e > P[k]) P[k] = e;
    const bx = x + dx, by = y + dy, eb = bx >= 0 && by >= 0 && bx < N && by < N ? T.elev[by * N + bx] || 0 : 0;
    for (let j = 1; j <= eb - e; j++) {
      const u = x + dx * (e + j), v = y + dy * (e + j);
      if (u >= 0 && v >= 0 && u < N && v < N) P[v * N + u] = e + j;
    }
  }
  projCache = { T, view: VIEW, P };
  return P;
}

function buildingAt(x, y) { const k = OCC && OCC[y * N + x]; return k ? S.buildings[k - 1] : null; }
// a horse ranch's corral is drawn as ground (horses walk over it): tall terrain pictures on it are hidden (bugs.md 134)
function inCorral(t) { const b = t && buildingAt(t[0], t[1]), c = b && b.corral; return !!c && t[0] >= c[0] && t[0] < c[0] + 4 && t[1] >= c[1] && t[1] < c[1] + 4; }

// what the audio layer hears at a screen point (audio.js knows nothing else about the game)
function probe(sx, sy) {
  const t = screenTileFlat(sx, sy);                // FUN_005A4790 picks with FUN_0044A460 (no elevation)
  if (!t || !T) return undefined;
  const [x, y] = t;
  const b = buildingAt(x, y);
  if (b && b.kind !== "road") return { building: b.key, burning: !!b.burning };
  if (P.f0) for (const w of P.f0.walkers) if (w[1] === x && w[2] === y) return { animal: w[3] };
  return { terrain: T.flags[y * N + x] };
}

function buildTerrain() {
  patchCleared();                                 // a clear the terrain may not show yet (build.js)
  terrainBatch.clear();
  WATER = []; TALL = []; LAVA = [];
  const ag = atlas.Zeus_Terrain && atlas.Zeus_Terrain.groups;
  const lavaFirst = ag && ag.SPR_LAVA && ag.SPR_LAVA[0];
  if (!T.lavaMap) T.lavaMap = new Map((T.lava || []).map(r => [r[0], r]));   // sim/live.py _lava_tiles
  const coast = ag && ag.SPR_BEACH_COAST && ag.SPR_BEACH_COAST[0], anims = ag && ag.SPR_WATER_ANIMS && ag.SPR_WATER_ANIMS[0];
  const old = T.version < 300;
  if (!T.altMap) T.altMap = new Map((T.alt || []).map(r => [r[0], r.slice(1)]));    // terrain.json alt (rotation.md)
  const ALT = T.altMap;
  if (!T.cliffMap) T.cliffMap = {};                 // cliffs of a turned view: tile -> [id, draw] (rotation.md)
  const CL = VIEW ? (T.cliffMap[VIEW] || (T.cliffMap[VIEW] = new Map((T["cliffs" + VIEW] || []).map(r => [r[0], [r[1], r[2]]])))) : null;
  const AV = new Map((VIEW && T["avenues" + VIEW]) || T.avenues || []);   // avenue/boulevard pictures of this view (Zeus_General), sim/live.py
  // monument step tiles: the exe draws only the step picture there (scene.js stepGround, bugs.md 400)
  const STEP = typeof stepGround === "function" ? stepGround() : new Set();
  // the road drag's route, in the terrain while the mouse is down (build.js setRoadPreview, bugs.md 464)
  const PV = typeof Build !== "undefined" && Build.roadPreview && Build.roadPreview.view === VIEW ? Build.roadPreview : null;
  // a server started before the turned-view terrain (sim/live.py cliffs2/4/6, alt) sends view-0 pictures only:
  // cliffs and edges then come out as black holes (bugs.md 156); say so instead of drawing it silently wrong
  if (VIEW && !T["cliffs" + VIEW] && !T.warnedViews && typeof toast === "function") {
    T.warnedViews = true; toast("This server predates turned views (no per-view terrain): restart it", true);
  }
  // a road / avenue tile's picture is its ground picture in the exe (road_set_tile 0x0049FF10 writes it to the picture
  // grid 0x00D4CFC8), no top: in pass 1, or again at its own cell when raised (pass 2 step 1, Order.terrain), so a
  // raised road covers the top of a cliff behind it (bugs.md 427: ours drew every road in pass 1)
  const flatGround = (sp, x, y, i) => {
    const px = tileX(x, y), y0 = tileY(x, y) - T.elev[i] * 30 + 30 - sp.h, key = Order.terrain(x, y, false, false);
    if (key != null) TALL.push([key, x, sp, px, y0, [x, y]]);
    else terrainBatch.push(sp, px, y0);
  };
  for (let s = 0; s <= 2 * N - 2; s++) {
    for (let rx = Math.max(0, s - N + 1); rx <= Math.min(s, N - 1); rx++) {   // back to front in this view
      const [x, y] = worldXY(rx, s - rx), i = y * N + x;
      if (STEP.has(i)) continue;
      const av = AV.get(i);
      if (av && av < 288) {                       // avenue/boulevard road tile: flat SPR_BOUL_ROAD picture
        const sp = sprite("Zeus_General", av);
        if (sp) { flatGround(sp, x, y, i); continue; }
      }
      // roads replace the ground image (bridges: water + pieces, bridges.js; a ramp 0x400 keeps its own picture,
      // which the server gives as the exe's road-on-ramp picture when it has a road: sim/terrain_view.py ramp_roads)
      if ((T.road[i] || (PV && PV.roads.has(i))) && !av && !(T.flags[i] & 0x404)) {
        const sp = Scene.roadSprite(x, y);
        if (sp) { flatGround(sp, x, y, i); continue; }
      }
      let id = T.ids[i];
      if (VIEW && ALT) { const d = ALT.get(i); if (d) id += d[(VIEW >> 1) - 1]; }   // pattern tiles: column view/2
      let drw = T.draw[i];
      const cl = CL && CL.get(i);
      if (cl) { id = cl[0]; drw = cl[1]; }
      const pv = PV && PV.pics.get(i);                // a ramp of the drag's route: its road picture
      if (pv) { id = pv[0]; drw = pv[1]; }
      if (!id || (T.flags[i] & 0x80000)) continue;                         // off-map tiles stay black
      if (!VIEW && !(drw & 0x40)) continue;          // view 0: the map's anchor bit; other views: blockAnchor below
      let col = id >>> 14;
      if (old && col >= 2) col += 2;
      const file = COLLECTIONS[col];
      const idx = (id & 0x3fff) + 201;            // map n is 0-based: atlas index n+201 (docs/play/terrain.md)
      if (col === 5 && (T.flags[i] & 4) && !(T.draw[i] & 0x0f)) {   // water animation (terrain.md 5)
        const deep = T.flags[i] & 0x4000000;
        if (!deep && coast && idx >= coast && idx < coast + 6) { WATER.push([x, y, tileX(x, y), tileY(x, y) - T.elev[i] * 30, coast, idx - coast, 6, 1]); continue; }
        if (deep && anims && idx >= anims && idx < anims + 90) { WATER.push([x, y, tileX(x, y), tileY(x, y) - T.elev[i] * 30, anims, idx - anims, 90, 15]); continue; }
      }
      const lv = lavaFirst && T.lavaMap.get(i);
      if (lv && lv[2] < 0 && col === 5 && idx >= lavaFirst && idx < lavaFirst + 6) {   // a centre tile: animated (drawLava)
        LAVA.push([tileX(x, y), tileY(x, y) - T.elev[i] * 30, idx - lavaFirst, lv[1], 1, idx - lavaFirst]);
        continue;
      }
      if (lv && lv[2] >= 0) LAVA.push([tileX(x, y), tileY(x, y) - T.elev[i] * 30, lv[2 + (VIEW >> 1)], lv[1], 0, 0]);
      const sp = file && sprite(file, idx);
      if (!sp) continue;
      const n = Math.max(1, sp.iso);
      if (VIEW && !(n > 1 ? blockAnchor(drw, n) : drw & 0x40)) continue;
      const px = tileX(x, y), py = tileY(x, y) - T.elev[i] * 30;
      // the image's footprint is x..x+n-1, y-n+1..y (anchor = left corner). The exe draws a ground picture in two
      // parts (docs/play/draw-order.md 2-3; bugs.md 177, 185): the base in pass 1 (the terrain batch), or again at
      // its cell (GROUND) when raised (Order.terrain); and the top of a picture with one (image +0x35: trees,
      // rocks, cliffs, tufts) at step 4 of its anchor cell like a building's: the upper h - (15n + 1) rows
      // (building_top_draw 0x005ADF00), OBJECT of that cell. Both are skipped on a building's tiles (drawFrame).
      const f = T.flags[i], simple = n === 1 && (f & 0x881) && !(f & 0x1000c208), top = sp.h > 30 * n;
      const y0 = py + 30 + 15 * (n - 1) - sp.h, cut = top ? sp.h - 15 * n - 1 : 0;
      const key = Order.terrain(x, y, top, simple), base = cut ? subSprite(sp, 0, cut, sp.w, sp.h - cut) : sp;
      if (key != null) TALL.push([key, x, base, px, y0 + cut, [x, y]]);
      else terrainBatch.push(base, px, y0 + cut);
      // [7]: the top's rows inside the footprint diamond, drawn under everything when a building stands here
      const d0 = Math.max(0, sp.h - 30 * n);
      if (cut) TALL.push([Order.terrainTop(x, y, simple, n), x, subSprite(sp, 0, 0, sp.w, cut), px, y0, [x, y], n,
                         cut > d0 ? [subSprite(sp, 0, d0, sp.w, cut - d0), px, y0 + d0] : null]);
    }
  }
}

// a multi-tile ground piece (draw byte = row*8 + column inside the block) is drawn from its left corner
// in this view: (0, n-1) in view 0, (0, 0) in 2, (n-1, 0) in 4, (n-1, n-1) in 6 (FUN_004A1BE0 moves the
// anchor bit 0x40 on a turn; building_footprint_place 0x004A04B0 the same for buildings)
function blockAnchor(d, n) {
  const c = d & 7, r = (d >> 3) & 7, m = n - 1;
  return VIEW === 2 ? c === 0 && r === 0 : VIEW === 4 ? c === m && r === 0 : VIEW === 6 ? c === m && r === m : c === 0 && r === m;
}

// buildings without a mapping entry yet: the first image of the sim viewer's group
// one step per displayed frame more than 60 ms after the last (exe 0x007D3B1C, ground_tile_draw 0x00457900):
// shallow interior +1 (wrap 6), deep +15 (wrap 90)
let waterStep = 0, waterAt = 0;
function drawWater() {
  const now = performance.now();
  if (now - waterAt <= 60 && waterBatch.n) return;          // exe: a step when > 60 ms (0x007D3B1C)
  waterAt = now;
  waterStep++;
  waterBatch.clear();
  for (const [, , px, py, first, base, wrap, inc] of WATER) {
    const sp = sprite("Zeus_Terrain", first + (base + inc * waterStep) % wrap);
    if (sp) waterBatch.push(sp, px, py + 30 - sp.h);
  }
}

// lava (sim/disasters, FUN_00507980 via ground_tile_draw 0x00457900): an edge tile is its ground + SPR_LAVA k drawn
// with the 16-bit AND mask of its flow's colour (vtable +0x10 0x00507950: v | v << 6 | 0xF863, v = cooling % * 15 /
// 100; the oracle's RGB555 blit, as the bridge ghost); a centre tile is its own SPR_LAVA picture, one frame further
// per draw while its flow runs or cools (states 2 / 3: id + 1, back to the first at + 5), masked the same. The exe
// steps it on every drawn frame; ours on the water's > 60 ms clock (I'm not certain of the exe's frame cadence).
let lavaAt = 0;
function lavaMask(c3) { const v = Math.trunc(c3 * 15 * 0.01); return v | (v << 6) | 0xF863; }
function drawLava() {
  if (!LAVA.length) { if (lavaBatch.n) lavaBatch.clear(); return; }
  const ag = atlas.Zeus_Terrain && atlas.Zeus_Terrain.groups, first = ag && ag.SPR_LAVA && ag.SPR_LAVA[0];
  if (!first) return;
  const st = new Map(((P.f0 && P.f0.lava) || []).map(r => [r[0], r]));
  const now = performance.now(), step = now - lavaAt > 60;
  if (step) lavaAt = now;
  lavaBatch.clear();
  for (const e of LAVA) {
    const o = st.get(e[3]), run = o && (o[1] === 2 || o[1] === 3);
    let k = e[2], mask = o ? lavaMask(o[2]) : 0;
    if (e[4]) {                                   // centre: animated and masked while it runs
      if (run && step) { e[5]++; if (e[5] >= 5) e[5] = 0; }
      k = e[5];
      if (!run) mask = 0;
    }
    const sp = sprite("Zeus_Terrain", first + k);
    if (sp) lavaBatch.push(sp, e[0], e[1] + 30 - sp.h, mask ? 65536 + mask : 1);
  }
}

function fallbackBuilding(out, b) {
  const g = FALLBACK_GROUPS[b.key];
  const sp = g && groupSprite("Zeus_General", g);
  if (!sp) return;
  const w = b.w || b.size || 1, h = b.h || b.size || 1, n = Math.max(1, sp.iso || w);
  const f = viewFoot(b.x, b.y, w, h);
  out.push([Order.obj(b.x, b.y, w, h), b.x, viewMirror() ? mirrored(sp) : sp, tileX(f.ax, f.ay) - 30 * (n - 1), tileY(f.ax, f.ay) + 30 * n - sp.h - T.elev[f.ay * N + f.ax] * 30]);
}

// The loop must never stop: time, drawing and sound are guarded separately, and the scene guards each
// building/walker (scene.js), so one bad sprite costs one sprite, not the frame.
let frameErrors = 0;
function guard(fn) { try { fn(); } catch (e) { if (frameErrors++ < 5) console.error(e); } }
function frame() {
  if (P.live) pollFrames();                       // synced live: ask when due (pollDue; one request in flight)
  guard(advance);
  guard(drawFrame);
  guard(() => uiDraw(R));
  guard(() => audio && audio.tick(innerWidth, innerHeight));
  // a campaign screen's narration ends with the city back (audio.js screenSoundEnd)
  guard(() => { if (audio && audio.screenKey && !(window.Campaign && Campaign.screen()) && !(window.NewGame && NewGame.isOpen())) audio.screenSoundEnd(); });
  guard(fightSounds);
  requestAnimationFrame(frame);
}

// fight sounds (data/play/audio.json "combat", docs/logic/services.md 6.1, docs/play/audio.md 4.1): the events of the
// melee anims in the frames (scene.js fightAnim) that fall in the ticks played since the last call, for figures on
// screen only (FUN_005A6FE0 skips off-screen ones). Soldiers, invaders, wolves, citizens (bug 393): the sample table
// (combat.samples[kind][variant]: 1 / 2 attack, 3 / 4 missile, 7 hit, 8 die) by the figure's sound kind (type_kind by
// exe type, army_kind for invaders, sanct_kind for Ares' warriors); the sim's "hit" / "shot" sfx (units.hit, throws,
// sentries); periodic attack sounds from the looks (infantry at attack_timer 10, hoplites at 1, sieges at frame 1,
// archers' shot at frame 1)
const FIGHTERS = new Set(["disgruntled", "thief", "mugger", "vandal"]);
const OWN_ROLES = new Set(["god", "monster", "hero"]);          // their own sounds (gods.js, heroes.js, below)
let soundTick = null;
const heardSfx = new Set();
function soundKind(C, role, good) {
  if (C.sanct_kind && C.sanct_kind[role + ":" + good] != null) return C.sanct_kind[role + ":" + good];
  if (C.role_kind && C.role_kind[role] != null) return C.role_kind[role];     // 0x33 with resource 1: deer 0x84
  const ak = C.army_kind && C.army_kind[role];
  if (ak) { const a = /^army(\d+)/.exec(good || ""); return ak[a ? +a[1] : 0]; }
  const ty = C.role_type && C.role_type[role];
  return ty == null ? null : C.type_kind[String(ty)];
}
function kindSample(C, k, v) { const r = k == null ? null : C.samples[String(k)]; return r ? r[String(v)] || null : null; }
function fightSounds() {
  const t = Math.floor(P.t), from = soundTick;
  soundTick = t;
  const C = MAP.audio && MAP.audio.combat;
  if (!audio || audio.muted || !C || from == null || t <= from || t - from > 60 || !P.f0) return;
  const seen = new Map();
  for (const f of [P.f0, P.f1]) if (f) for (const w of f.walkers) if (w[7]) seen.set(w[0] + ":" + w[7][0] + ":" + w[7][1], w);
  const inWin = k => k > from && k <= t;
  const panOf = (x, y) => {
    const sx = (tileX(x, y) + 29 - cam.x) * cam.zoom, sy = (tileY(x, y) + 15 - cam.y) * cam.zoom;
    return (sx < 0 || sy < 0 || sx > innerWidth || sy > innerHeight) ? null : sx / innerWidth * 2 - 1;
  };
  const pick = l => l && l.length ? l[Math.floor(Math.random() * l.length)] : null;
  const WM = MAP.walkers && MAP.walkers.roles;
  for (const w of seen.values()) {
    const [, x, y, role, good] = w, [kind, t0, end, , , , , h0, foe, mover] = w[7];
    const pan = panOf(x, y);
    if (pan === null) continue;
    const me = C.roles[role + ":" + good] || C.roles[role] || {}, them = C.roles[foe] || {};   // monsters / heroes by good (sim/heroes)
    const sk = OWN_ROLES.has(role) || C.roles[role] ? null : soundKind(C, role, good);
    const play = f => f && audio.sfxAt(f, pan);
    if (kind === "die") { if (inWin(t0)) play(me.die || kindSample(C, sk, 8)); continue; }
    const atk12 = me.attack ? me.attack.slice(0, 2) : [kindSample(C, sk, 1), kindSample(C, sk, 2)].filter(Boolean);
    if (kind === "fight" && mover && inWin(t0)) play(pick(atk12));   // FUN_004DB3D0(f, 0): slot 1 or 2
    if (kind === "fight" && sk != null) {                 // the handlers' own attack sounds in action 5
      const at = role === "enemy_infantry" ? 10 : role === "hoplite" ? 1 : -1;
      if (at >= 0) for (let k = t0 + at; k < end; k += 24) if (inWin(k)) play(pick(atk12));
    }
    if (kind === "work" && w[7][8] === "siege" && sk != null) {   // figure_check_next_tile 0x004D8BB0: anim_frame == 1
      const blk = (((roleOf2(WM, role, good) || {}).work) || {}).siege;
      if (blk && window.Scene) for (let k = Math.max(from + 1, t0 + 1); k <= t; k++)
        if (Scene.imageStep(blk.speed, k - 1) % (blk.frames || 1) === 1 && Scene.imageStep(blk.speed, k - 2) % (blk.frames || 1) !== 1) play(pick(atk12));
    }
    if (kind === "work" && w[7][8] === "shoot" && role === "enemy_archer" && sk != null) {   // 0x005011C0: frame 1
      const blk = (((roleOf2(WM, role, good) || {}).work) || {}).shoot;
      const k = t0 + ((blk && blk.ticks_per_frame) || 1) + 1;
      if (inWin(k)) play(pick([kindSample(C, sk, 3), kindSample(C, sk, 4)].filter(Boolean)));
    }
    if (role === "monster" && kind === "fight" && foe && foe !== "hero") {   // melee (action 5; the duel is 0x17)
      const F = ((MAP.walkers.roles[(MAP.walkers.roles.monster.map || {})[w[4]]] || {}).fight || {}).frames || 0;
      if (F) for (let k = t0 + 1; k < end; k += F) if (inWin(k)) play(pick(atk12));   // anim frame 1 (0x004C8D22)
    }
    if (!FIGHTERS.has(role)) continue;            // the criminal's record carries both sides' blows
    for (let k = t0 + 1; k < end; k += 8) if (inWin(k)) play(pick(me.attack));     // fight anim frame 1
    if (kind !== "fight") continue;
    for (let k = h0 + 24; k < end; k += 24) if (inWin(k)) play(me.hit);           // defender's blows
    for (let k = t0 + 24; k < end; k += 24) if (inWin(k)) play(them.hit);         // its own (0 damage)
  }
  // the sim's events (sim walkers.sfx [tick, id, x, y, role, god, kind, until]): "hit" (figure_hit 0x004D54D0 ->
  // FUN_004DB7A0 on a blow that does not kill: variant 7), "shot" (FUN_004D9D20: variant 3 / 4). Gods / monsters /
  // heroes: gods.js, heroes.js
  for (const f of [P.f0, P.f1]) if (f && f.sfx) for (const e of f.sfx) {
    const [tick, id, x, y, role, , kind] = e;
    if (OWN_ROLES.has(role) || !(tick > from && tick <= t) || (kind !== "hit" && kind !== "shot")) continue;
    const key = id + ":" + tick + ":" + kind;
    if (heardSfx.has(key)) continue;
    heardSfx.add(key);
    if (heardSfx.size > 500) heardSfx.clear();
    const pan = panOf(x, y);
    if (pan === null) continue;
    const ww = f.walkers.find(v => v[0] === id), good = ww ? ww[4] : "";
    const sk = soundKind(C, role, good), row = C.roles[role];
    const file = kind === "hit" ? (row && row.hit) || kindSample(C, sk, 7)
      : pick([kindSample(C, sk, 3), kindSample(C, sk, 4)].filter(Boolean));
    if (file) audio.sfxAt(file, pan);
  }
}
function roleOf2(WM, role, good) {
  if (!WM) return null;
  if (good && WM[role + ":" + good]) return WM[role + ":" + good];
  const m = WM[role];
  return m && m.by === "good" ? WM[(m.map && m.map[good]) || m.fallback_role] : m;
}

// scroll limits as the exe (0x0051CC70, recomputed on every turn): the map area never shows past the play area
// (tiles without the off-map flag 0x80000) in the current view; a map smaller than the screen is centred
let camBox = { T: null, view: -1, box: null };
function clampCam() {
  if (camBox.T !== T || camBox.view !== VIEW) {
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    for (let i = 0; i < N * N; i++) if (!(T.flags[i] & 0x80000)) {
      const x = i % N, y = (i / N) | 0, px = tileX(x, y), py = tileY(x, y);
      if (px < x0) x0 = px; if (px + 60 > x1) x1 = px + 60; if (py < y0) y0 = py; if (py + 30 > y1) y1 = py + 30;
    }
    camBox = { T, view: VIEW, box: x0 < x1 ? [x0 + 30, x1 - 30, y0 + 15, y1 - 15] : null };   // inside the edge's teeth
  }
  const b = camBox.box;
  if (!b || !UIX.panelX) return;
  const w = (UIX.panelX * UIX.scale) / cam.zoom, h = innerHeight / cam.zoom;
  cam.x = w >= b[1] - b[0] ? (b[0] + b[1] - w) / 2 : Math.min(Math.max(cam.x, b[0]), b[1] - w);
  cam.y = h >= b[3] - b[2] ? (b[2] + b[3] - h) / 2 : Math.min(Math.max(cam.y, b[2]), b[3] - h);
}

// tall terrain (TALL) whose picture meets the world rect [x0, x1) x [y0, y1), into list
let rbSet = null, rbOf = null;
function tallTerrain(list, x0, y0, x1, y1) {
  // roadblock tiles (a tile list in the state, not buildings): the exe's picture grid holds the roadblock there
  if (rbOf !== (S && S.roadblocks)) { rbOf = S && S.roadblocks; rbSet = new Set((rbOf || []).map(([x, y]) => y * N + x)); }
  for (const d of TALL) {
    const t = d[5];
    if (inCorral(t) || (window.Overlays && Overlays.covers(t)) ||
        !(d[3] < x1 && d[3] + d[2].w > x0 && d[4] < y1 && d[4] + d[2].h > y0)) continue;
    // a building's tile shows the building's picture, no terrain (bugs.md 185); a tree / rubble just cleared
    // (build.js clearNow) loses its top until the new terrain comes, but keeps its ground diamond (bugs.md 388:
    // the diamond's upper half belongs to the top's rows, hidden whole it left a black triangle for ~1 s)
    if (t && ((OCC && OCC[t[1] * N + t[0]]) || rbSet.has(t[1] * N + t[0]) || clearedTree(t[0], t[1]))) {
      // its ground diamond only, under everything (no hole where a building picture leaves one), also under the
      // pass-1 buildings (Order.pass1 keys -1 - tile: roadblocks, corrals, types 2 / 9; bugs.md 427)
      const under = -2 - N * N;
      if (!d[6]) list.push([under, d[1], d[2], d[3], d[4]]);
      else if (d[7]) list.push([under, d[1], ...d[7]]);
      continue;
    }
    if (d[6] && Order.topHidden(t[0], t[1], d[6])) continue;
    list.push(d);
  }
}

// Walker-window figure crops (exe FUN_00572FE0, docs/play/info.md "Walker window"): per listed figure the exe
// centres a 5 x 15 cell view (map_view_set_size 0x0051CC50, clip (0,30)-(298,240)) on its tile: column - 2,
// row (cell row - elevation - 6) & ~1 (FUN_00572F50), draws the city with only that figure (walker_draw param_4)
// and copies the 48x48 pixels at that figure's sprite top-left (0x007D3B3C/38), x >= 0, y >= the top bar (30),
// into its box. Ours: the same scene at 100 % (one picture px = one interface px) in the box, scissored; the other
// figures' entries (wid) are left out. Where the top or left was clamped, the crop moves as the exe's does.
let FRAME_LIST = [];
const WALKER_EXE = [0, 0];                        // exe figure picture - ours (bugs.md 251: scene.js figureSpot draws as the exe since 10-30)
const cropBatches = [];                          // one per box of this UI frame
const cropLast = new Map();                       // id -> last anchor (a figure inside a building keeps its spot)
function cropOrigin(id) {
  const a = (window.Scene && Scene.walkerAnchor(id)) || cropLast.get(id);
  if (!a) return null;
  cropLast.set(id, a);
  const [sl, st, fx, fy] = a, [rx, ry] = viewXY(fx, fy), e = (T.elev[fy * N + fx] || 0);
  // the tile point in the small view: x 90 / 120 by the cell column's parity, y 105 + 15 e + 15 p
  // (cell row = x + y + 1 in the view's turned tiles, grid 0x007D3BEC from FUN_00449FF0; p = parity of row - e - 6);
  // WALKER_EXE: the exe's figure picture - ours (0 since bugs.md 251)
  const xs = 90 + 30 * ((rx - ry) & 1), ys = 105 + 15 * e + 15 * ((rx + ry + 1 - e - 6) & 1);
  const lx = sl - tileX(fx, fy) + xs + WALKER_EXE[0], ty = st - tileY(fx, fy) + ys + WALKER_EXE[1];
  return [sl + Math.max(0, lx) - lx, st + Math.max(30, ty) - ty];
}
function drawCrop(id, bx, by, w, h) {              // box interior at (bx, by) in interface px
  const o = T && S && cropOrigin(id);
  if (!o) return false;
  const list = [];
  const x0 = o[0], y0 = o[1], x1 = x0 + w, y1 = y0 + h;
  for (const e of FRAME_LIST) {
    if (e.wid != null && e.wid !== id) continue;
    if (!(e[3] < x1 && e[3] + e[2].w > x0 && e[4] < y1 && e[4] + e[2].h > y0)) continue;
    list.push(e);
  }
  tallTerrain(list, x0, y0, x1, y1);
  list.sort((a, b) => a[0] - b[0]);
  const k = UIX.cuts.length;
  if (!cropBatches[k]) { cropBatches[k] = R.batch(); cropBatches[k].bias = objBatch.bias; }
  const cropBatch = cropBatches[k];
  cropBatch.clear();
  for (const e of list) cropBatch.push(e[2], e[3], e[4], e.tint ? 2 + e.tint : 1);
  UIX.cuts.push({ at: UIX.batch.n, draw: () => {
    const gl = R.gl, s = UIX.scale * (window.devicePixelRatio || 1), H = gl.drawingBufferHeight;
    const X = Math.round(bx * s), Y = Math.round(by * s), W = Math.round((bx + w) * s) - X, Hh = Math.round((by + h) * s) - Y;
    gl.enable(gl.SCISSOR_TEST);
    gl.scissor(X, H - Y - Hh, W, Hh);
    gl.clearColor(0, 0, 0, 1); gl.clear(gl.COLOR_BUFFER_BIT);
    R.begin({ x: x0 - bx, y: y0 - by, zoom: UIX.scale }, false);
    waterBatch.draw();
    terrainBatch.draw();
    lavaBatch.draw();
    guard(() => window.Overlays && Overlays.drawGround());
    cropBatch.draw();
    gl.disable(gl.SCISSOR_TEST);
  } });
  return true;
}

function drawFrame() {
  if (!T || !S) return;
  clampCam();
  const list = [];
  guard(() => Scene.sceneBuildings(list, fallbackBuilding));
  guard(() => Scene.sceneWalls(list));
  guard(() => Bridges.scene(list));
  guard(() => Scene.sceneAvenues(list));
  guard(() => Scene.sceneGardens(list));
  guard(() => Scene.sceneRoadblocks(list));
  Order.big.clear();                              // cart-like figures' tiles of this frame (Order.topHidden)
  guard(() => Scene.sceneWalkers(list));
  guard(() => Scene.sceneWaterLife(list));                      // fishing / urchin spots
  guard(() => window.Effects && Effects.scene(list));           // dust, splashes (effects.js)
  const m0 = list.length;
  guard(() => window.Military && Military.scene(list));         // company standards (military.js)
  for (let i = m0; i < list.length; i++) list[i].wid = -1;      // figures of their own in the exe (walker crops)
  guard(() => window.Gods && Gods.scene());                     // god atlases on demand (gods.js)
  guard(() => window.Heroes && Heroes.scene());                 // monster / hero atlases on demand (heroes.js)
  guard(() => window.Overlays && Overlays.scene(list));         // overlay columns / panels (overlays.js)
  FRAME_LIST = list.slice();                      // the scene before tall terrain, in push order (walker crops)
  tallTerrain(list, cam.x, cam.y, cam.x + innerWidth / cam.zoom, cam.y + innerHeight / cam.zoom);   // on screen only
  list.sort((a, b) => a[0] - b[0]);               // one key per entry (order.js); stable: equal keys keep push order
  if (window.drawCapture) drawCapture(list);       // tools/draw_order_check.mjs
  objBatch.clear();
  for (const e of list) objBatch.push(e[2], e[3], e[4], e.tint ? 2 + e.tint : 1);   // e.tint: a figure's draw colour (gl.js)
  R.begin(cam);
  guard(drawWater);
  guard(drawLava);
  waterBatch.draw();
  terrainBatch.draw();
  lavaBatch.draw();
  guard(() => window.Overlays && Overlays.drawGround());       // overlay: flattened buildings, appeal tiles
  objBatch.draw();
  guard(drawGhost);
  Build.ghost.draw();
}

// --- data ------------------------------------------------------------------------------------------
// every request has a timeout: a hung request must never leave a poll loop "busy" forever
async function getJSON(u, ms = 8000) {
  const r = await fetch(u, { signal: AbortSignal.timeout(ms) });
  if (!r.ok) throw new Error(u);
  return r.json();
}

async function loadMaps() {
  // all at once (one after another cost a round trip each: ~2.5 s over a far link)
  const keys = ["buildings", "walkers", "audio", "monuments", "ui", "fonts", "strings_ui", "info_panels", "walker_info", "military"];
  const [maps, res] = await Promise.all([Promise.all(keys.map(k => getJSON(`/data/play/${k}.json`).catch(() => null))),
                                         getJSON("/data/resources.json").catch(() => null)]);
  keys.forEach((k, i) => { MAP[k] = maps[i]; });
  if (res) Scene.setResources(res);
  if (window.Military) Military.init();           // military.json roles over walkers.json (military.js)
  if (window.Gods) await Gods.init();             // gods.json roles over walkers.json (gods.js)
  if (window.Heroes) await Heroes.init();         // heroes.json roles over walkers.json (heroes.js)
}

// Two modes (sim/live.py): LIVE drives the server's one timeline (speed/pause change the city, building
// allowed); REPLAY plays the recording at any tick and speed, read-only.
// Synced live (docs/play-mode.md): a visible live tab is the clock. Its polls ask the server for ticks up to
// its playhead + ahead(), so what it draws is at most ahead() ticks behind the city; a placed building is
// real (right click, depth) within a poll. Without such polls the server runs on its own wall clock.
P.live = true;
P.window = 75;                                    // server: how far behind live still counts as live
const LAG = 30;                                   // the timeline slider: this close to live = live
const REC = 15;                                   // server frame grid (ticks)
const AHEAD_Q = +new URLSearchParams(location.search).get("ahead");   // ?ahead=N: a fixed margin (testing)
// the margin: the next frame (frames every P.every ticks) + twice the play time one poll cycle takes. The server
// simulates only up to playhead + margin, and one poll is in flight at a time: a poll leaves when half the margin
// is left in the buffer, so that half must cover the cycle and the other half is what the answer adds. The cycle:
// the network round trip of the driving polls (smoothed, + 3x its mean deviation: a slow answer now and then must
// not empty the buffer either) + a drawn frame + the server's simulation of the ticks the poll asks (meta.work /
// meta.ran: its cost per tick x the ticks; at a speed the sim barely keeps up with, the margin grows by
// 1 / (1 - the sim's share of real time)). Before (bug 468) the margin was 1.5 x (round trip + frame), at most
// 0.4 s: over a ~300 ms link (the shared server behind a CDN) the buffer ran dry on every poll, the walkers stopped
// ~100-170 ms three times a second and the city ran at ~75 % of its speed (bugs.md 482). At most LEAD_MAX s of
// play, and a third of the live window less its frames (the catch-up jump in advance() needs window - 2 x margin;
// commands are accepted within the window, sim/live.py live_window)
let pollRtt = 0.03, pollDev = 0.005, tickCost = 0;   // s: network round trip, its deviation; s of sim per tick
const LEAD_MAX = 1;
const leadSecs = () => {
  const cycle = pollRtt + 3 * pollDev + 1 / Math.max(5, fps), load = Math.min(0.9, P.rate * tickCost);
  return Math.min(LEAD_MAX, Math.max(0.1, 2 * cycle / (1 - load)));
};
function ahead() {
  if (AHEAD_Q > 0) return AHEAD_Q;
  const every = P.every || 1, cap = Math.max(every + 1, Math.floor(((P.window || 75) - 2 * REC) / 3));
  return Math.min(cap, every + Math.ceil(P.rate * leadSecs()));
}

function jumpTo(tick) {                           // drop the buffer unless the tick is inside it
  if (tick <= bufEnd() && tick >= (FRAMES[0] ? FRAMES[0].tick : 0)) { P.t = tick; return; }
  FRAMES.length = 0;
  P.t = tick;
  P.stateTick = -1; P.stateSeq = -1;
}

function setLive(on) {
  P.live = on;
  document.body.classList.toggle("replay", !on);
  if (on) { P.playing = !P.paused; jumpTo(Math.max(0, P.liveTick - ahead())); }
  if (!on && Build.tool) selectTool(null);
}

async function control(body) {                   // live speed / pause: the server's state
  try {
    const r = await (await fetch("/control", { method: "POST", headers: { "Content-Type": "application/json" },
                                                body: JSON.stringify(body), signal: AbortSignal.timeout(4000) })).json();
    P.serverRate = r.rate; P.paused = r.paused;
  } catch (e) { }
}

// three independent loops, so a slow state or terrain download never stalls the walkers
const busy = { frames: false, state: false, terrain: false };
let lastMapVersion = -1, mapVersion = -1, lastTerrainAt = 0;
const bufEnd = () => FRAMES.length ? FRAMES[FRAMES.length - 1].tick : -1;

// Protocol (docs/play/comms.md): 2 = deltas on the frame / snapshot / terrain the tab holds and polls only when
// due; ?proto=1 = full answers and a poll every animation frame (the code before 10-30; tools/comms_check.mjs).
const PROTO = +new URLSearchParams(location.search).get("proto") || Comms.PROTO;
const COMMS = window.COMMS = { apply: 0, frames: 0, deltas: 0, resync: 0 };   // ms decoding deltas; counts
let polledAt = 0, frameBase = true, terrainBase = true;
// protocol 2: a live tab polls when its buffer is down to half the margin (the poll asks the margin again), or
// every 250 ms for the live meta (pause, speed, other tabs' buildings); a replaying tab when less than a second
// of play is buffered, or every 500 ms (the timeline's live end); a hidden tab on every interval (1 s in Chrome)
function pollDue() {
  if (PROTO < 2 || !FRAMES.length) return true;
  const since = performance.now() - polledAt, buf = bufEnd() - P.t;
  if (P.live) return document.visibilityState !== "visible" || buf < ahead() / 2 || since > 250;
  return buf < P.rate + 45 || since > 500;
}

async function pollFrames() {
  if (busy.frames || !pollDue()) return;
  busy.frames = true;
  polledAt = performance.now();
  try {
    if (P.firstTick != null && P.t < P.firstTick)  // the recording starts later (a loaded save, a restart)
      P.t = P.live ? Math.max(P.firstTick, P.liveTick - ahead()) : P.firstTick;
    const from = Math.max(bufEnd() + 1, Math.floor(P.t));
    const to = P.live ? from + 100000 : Math.floor(P.t) + 2 * P.rate + 45;
    // a hidden tab, or one that stopped drawing (screen asleep, no rAF for 1 s), lets the server run on alone: the
    // city keeps going while the player is away (ours, user 10-31: AFK-playable; bugs.md 321)
    // Watchdog (bugs.md 344): a live, unpaused playhead that has not moved for 2 s while the server's tick is
    // ahead of it is stuck on a hiccup of either side (a missing frame, a lost answer): stop driving, so the
    // server runs on alone (DRIVE_TIMEOUT) and its next frames catch the tab up (advance: "the server ran alone").
    const stuck = stalled();
    const drive = P.live && !stuck && document.visibilityState === "visible" && performance.now() - advancedAt < 1000
      ? `&want=${Math.floor(P.t + ahead())}${!P.paused && screenPauses() ? "&hold=1" : ""}` : "";   // hold: live.py watch
    const last = FRAMES.length ? FRAMES[FRAMES.length - 1] : null;     // protocol 2: the deltas' base
    const v2 = PROTO >= 2 ? `&v=2${last && last.fs != null && frameBase ? `&base=${last.fs}` : ""}` : "";
    const r = await getJSON(`frames.json?from=${from}&to=${to}&at=${Math.floor(P.t)}${drive}${v2}`, 4000);
    P.okAt = performance.now();
    if (drive) {                                  // (the TCP way: deviation first, from the old mean)
      const work = r.meta.work || 0, rtt = Math.min(2, Math.max(0, (P.okAt - polledAt) / 1000 - work));
      if (r.meta.ran > 0) tickCost = tickCost * 0.8 + (work / r.meta.ran) * 0.2;
      pollDev = pollDev * 0.75 + Math.abs(rtt - pollRtt) * 0.25;
      pollRtt = pollRtt * 0.8 + rtt * 0.2;
    }
    P.error = r.meta.error || "";
    // a new server process (a restart, a deploy: meta.boot) or a new city / a loaded save: start over. The ids the
    // tab holds (frame fs, snapshot seq, terrain tid) are another process's (bugs.md 481: an open tab kept the
    // terrain of the city before the restart, roads and all)
    const reboot = r.meta.boot != null && P.boot != null && r.meta.boot !== P.boot;
    if (r.meta.boot != null) P.boot = r.meta.boot;
    if (reboot || r.meta.live_tick < P.liveTick - 60 || (FRAMES.length && r.meta.first > bufEnd() + REC)) {
      resetPlayback();                            // the server started a new city or loaded a save
      P.t = Math.max(r.meta.first, r.meta.live_tick - ahead());
    }
    let frames = r.frames;
    if (PROTO >= 2) {
      const t0 = performance.now();
      try { frames = Comms.decodeFrames(last, r.frames).frames; frameBase = true; }
      catch (e) { console.warn(e.message); frames = r.frames.filter(f => f._b === undefined); frameBase = false; COMMS.resync++; }
      COMMS.apply += performance.now() - t0;
      COMMS.frames += frames.length; COMMS.deltas += r.frames.length - r.frames.filter(f => f._b === undefined).length;
    }
    for (const f of frames) {
      if (f.tick > bufEnd()) FRAMES.push(f);
      // re-recorded at the same tick (a command; its deltas build on the new one): the tab takes it
      else if (PROTO >= 2 && f.tick === bufEnd() && f.fs !== FRAMES[FRAMES.length - 1].fs) FRAMES[FRAMES.length - 1] = f;
    }
    while (FRAMES.length > 2 && FRAMES[1].tick < P.t - 60) FRAMES.shift();
    P.liveTick = r.meta.live_tick;
    P.liveAt = performance.now();
    P.serverRate = r.meta.rate; P.paused = r.meta.paused; P.window = r.meta.window; P.firstTick = r.meta.first;
    if (window.Campaign) Campaign.meta(r.meta.campaign);     // the campaign screens (campaign.js)
    mapVersion = r.meta.version;
    P.every = r.meta.every || REC;
    if (P.live && (r.meta.view || 0) !== VIEW) tellView();
    // live: the newest building snapshot (at most ahead() ticks past the playhead); replay: the one at the playhead
    if (P.live && r.meta.head_seq != null ? r.meta.head_seq !== P.stateSeq : r.meta.state_tick !== P.stateTick) pollState();
    if (mapVersion !== lastMapVersion && performance.now() - lastTerrainAt > 1500) pollTerrain();
  } catch (e) { }
  busy.frames = false;
}

function resetPlayback() {
  if (window.Loading) Loading.mark();
  FRAMES.length = 0;
  P.t = 0; P.f0 = P.f1 = null; P.stateTick = -1; P.stateSeq = -1;
  lastMapVersion = -1; lastTerrainAt = 0;
}

let stateGen = 0;                                 // a state answer older than the newest request is dropped
async function pollState() {
  if (busy.state) return;
  busy.state = true;
  const gen = ++stateGen;
  try {
    const have = PROTO >= 2 && S && S.seq != null && S.seq === P.stateSeq ? S : null;    // protocol 2: the deltas' base
    const v2 = PROTO >= 2 ? `&v=2${have ? `&base=${have.seq}` : ""}` : "";
    const r = await getJSON((P.live ? "state.json?lite=1" : `state.json?t=${Math.floor(P.t)}&lite=1`) + v2, 15000);
    if (gen === stateGen) {
      let s = r;
      if (PROTO >= 2) {
        const t0 = performance.now();
        try { s = Comms.applyState(have, r).state; } catch (e) { console.warn(e.message); s = null; COMMS.resync++; }
        COMMS.apply += performance.now() - t0;
      }
      if (s) {
        S = s;
        P.stateTick = s.tick;
        P.stateSeq = s.seq != null ? s.seq : -1;
        buildOcc();
      } else P.stateSeq = -1;                     // the next poll asks the whole snapshot
    }
  } catch (e) { }
  if (gen === stateGen) busy.state = false;
}

let terrainGen = 0;                               // a terrain answer older than the newest request is dropped
let terrainBuiltAt = 0;                           // the last terrain answer applied (Loading)

// Loading (ours, user 11-04): a new game, a load, a campaign start / proceed / replay stall the tab for seconds
// while the server builds the city and the tab refetches it; a spinner in the middle of the screen shows it.
// Loading.start() before the request; it hides itself once the new city's frames and terrain are in (both arrived
// after the start), on Loading.end() (the request failed or was refused), or after 60 s at most.
const Loading = window.Loading = (() => {
  let at = 0;
  const el = () => document.getElementById("cityload");
  const start = () => { at = performance.now(); el().hidden = false; };
  const mark = () => { if (at) at = performance.now(); };   // resetPlayback: only answers after it count (new city)
  const end = () => { at = 0; el().hidden = true; };
  // advance(): done once a frame and a terrain build both came after the start (resetPlayback emptied FRAMES)
  const check = () => { if (at && ((FRAMES.length && terrainBuiltAt > at && P.okAt > at) || performance.now() - at > 60000)) end(); };
  return { start, end, check, mark, get on() { return !!at; } };
})();
async function pollTerrain(force) {
  if (busy.terrain && !force) return;
  busy.terrain = true;
  lastTerrainAt = performance.now();
  const gen = ++terrainGen;
  try {
    const v = mapVersion;
    // protocol 2: a delta on the terrain the tab holds, unless the tab changed it (build.js patchCleared)
    const have = PROTO >= 2 && terrainBase && T && T.tid != null && !T.patched ? T : null;
    const t = await getJSON(PROTO >= 2 ? `terrain.json?v=2${have ? `&base=${have.tid}` : ""}` : "terrain.json", 30000);
    if (gen === terrainGen) {
      if (PROTO >= 2) {
        const t0 = performance.now();
        try { T = Comms.applyTerrain(have, t); terrainBase = true; }
        catch (e) { console.warn(e.message); terrainBase = false; COMMS.resync++; throw e; }
        COMMS.apply += performance.now() - t0;
      } else T = t;
      lastMapVersion = T.map_version != null ? T.map_version : v;
      buildTerrain();
      terrainBuiltAt = performance.now();
    }
  } catch (e) { }
  if (gen === terrainGen) busy.terrain = false;
}

// right after a command changed the map (clear, bugs.md 102): the new buildings and terrain at once, not at
// the next poll (pollTerrain waits 1.5 s after the last fetch)
function refreshNow() {
  busy.state = false;
  pollState();
  pollTerrain(true);
}

// playhead: advances with wall time but never past the buffered frames (no jumps, no freezes)
// screens that stop the simulation (simulation_due 0x005168A0: screen_pauses_sim 0x0063D8B8 is non-zero for every
// screen but the city 1, build submenu 6, 0x12, 0x1E, 0x20/0x48 military command, 0x23 balloon over the city, 0x27,
// 0x49, 0x56, 0x58, 0x59): message / help window 5, info 9, advisors 7, top menus 3, dialogs, lists, world map 0x14
// ours (user 10-31): info windows (right click) and message windows pause only if Options says so (the original's
// pause was its most annoying part); default off. Ours (user 11-04): the world map too ("Pause on the world map",
// default off: the city runs under it; docs/play/world.md "Running city"). The other screens pause as the original.
const PAUSE = { info: false, msg: false, auto: true, world: false };   // auto: message windows close after 10 s (msgwin.js)
function screenPauses() {
  const w = window;
  return !!((PAUSE.info && UIX.info) || (PAUSE.msg && w.MsgWin && MsgWin.isOpen()) || (w.Help && Help.isOpen()) || (w.Advisors && Advisors.isOpen())
    || (PAUSE.world && w.WorldMap && WorldMap.isOpen()) || (w.Lists && Lists.isOpen()) || (w.NewGame && NewGame.isOpen())
    || (w.Campaign && Campaign.isOpen())
    || (w.Options && (Options.isOpen() || Options.isMenu(2) || Options.isMenu(3))) || (w.FM && (FM.open || FM.dlg)));
}

let last = performance.now(), fps = 60, advancedAt = last;   // advancedAt: the last drawn frame (pollFrames)
let movedAt = last, movedT = -1;                  // the playhead's last move (pollFrames' watchdog)
// a live, playing playhead unmoved for 2 s while the server's tick is ahead: stuck on a hiccup (bugs.md 344)
const stalled = () => P.live && P.playing && P.liveTick > P.t && performance.now() - movedAt > 2000;
function advance() {
  const now = performance.now(), dt = Math.min(0.25, (now - last) / 1000);
  Loading.check();
  last = advancedAt = now;
  fps = fps * 0.95 + (dt > 0 ? 1 / dt : 0) * 0.05;
  panKeys(dt);
  if (!FRAMES.length) return hud();
  if (P.t < FRAMES[0].tick) P.t = FRAMES[0].tick;
  if (P.live) {                                   // the clock: the server simulates what this playhead asks for
    P.rate = P.serverRate || P.rate;
    P.playing = !P.paused && !screenPauses();     // the playhead drives the server (synced live): it stops too
    const head = bufEnd();
    // the server ran alone (tab hidden, a stalled frame or answer): a big lag jumps, always before it reaches
    // the live window (a command from there is refused, bug 455)
    const behind = head - P.t - ahead();
    if (behind > Math.min(ahead() * 4 + 60, (P.window || 75) - 2 * ahead())) P.t = head - ahead();
    // never past the newest frame: if the sim can't keep up, the walkers wait for it. A playhead behind its
    // margin plays faster until it is back (ours, bug 455): it asks for "playhead + margin", which the sim has
    // passed, so the sim waits for it and a hiccup's lag would otherwise stay for good
    else if (P.playing) P.t = Math.min(head, P.t + P.rate * dt + (behind > 0 ? Math.min(behind, behind * 3 * dt + 1) : 0));
  } else if (P.playing) {
    P.t = Math.min(bufEnd(), P.t + P.rate * dt);
  }
  if (P.t !== movedT || !P.playing) { movedT = P.t; movedAt = now; }
  let lo = 0, hi = FRAMES.length - 1;             // last frame with tick <= P.t
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (FRAMES[m].tick <= P.t) lo = m; else hi = m - 1; }
  P.f0 = FRAMES[lo];
  P.f1 = FRAMES[lo + 1] || null;
  hud();
}

// connection / server state banner (the loop keeps running and reconnects by itself)
function status() {
  const el = UI.status, now = performance.now();
  let msg = "";
  if (P.okAt && now - P.okAt > 3000) msg = `Server not responding (${Math.round((now - P.okAt) / 1000)} s); retrying…`;
  else if (P.error) msg = `Server error: ${P.error}. Press play (space) to try again.`;
  else if (frameErrors) msg = `Drawing error (see console): ${frameErrors} so far; the game keeps running.`;
  if (el.textContent !== msg) { el.textContent = msg; el.hidden = !msg; }
  // the spinner (ours): the watchdog let the server run on to catch the tab up, or the server is silent
  const sync = P.okAt && now - P.okAt > 3000 ? "Waiting for the server…" : stalled() ? "Catching up with the city…" : "";
  if (UI.synct.textContent !== sync) { UI.synct.textContent = sync; UI.sync.hidden = !sync; }
}

function hud() {
  status();
  const f = P.f0;
  UI.date.textContent = f ? f.date : "connecting…";
  UI.pop.textContent = f ? f.population.toLocaleString() : "";
  UI.money.textContent = f ? f.treasury.toLocaleString() + " dr" : "";
  UI.fps.textContent = `${fps.toFixed(0)} fps · tick ${Math.floor(P.t)}`;
  UI.zoom.textContent = Math.round(cam.zoom * 100) + "%";
  UI.play.textContent = P.playing ? "❚❚" : "▶";
  for (const b of UI.speeds) b.classList.toggle("on", +b.dataset.rate === P.rate);
  UI.mode.textContent = P.live ? "● LIVE" : "REPLAY";
  UI.mode.title = P.live ? "following the city; speed and pause change the city" : "replaying the recording (read-only): click to go live";
  if (!UI.scrubbing) {
    UI.timeline.max = Math.max(1, P.liveTick);
    UI.timeline.min = P.firstTick || 0;
    // live: the knob sits at the live end (the playhead trails the server by the margin, which on a young
    // timeline is a visible share of the bar and made the knob wobble while it caught up)
    UI.timeline.value = P.live ? UI.timeline.max : Math.floor(P.t);
  }
}

// --- camera + input --------------------------------------------------------------------------------
const view = document.getElementById("view");
const keys = new Set();
const PAN = { w: [0, -1], a: [-1, 0], s: [0, 1], d: [1, 0], arrowup: [0, -1], arrowleft: [-1, 0], arrowdown: [0, 1], arrowright: [1, 0] };
function panKeys(dt) {
  if (window.WorldMap && WorldMap.isOpen()) return;   // the world map scrolls its picture instead (world.js)
  let vx = 0, vy = 0;
  for (const k of keys) if (PAN[k]) { vx += PAN[k][0]; vy += PAN[k][1]; }
  if (!vx && !vy) return;
  const speed = (keys.has("shift") ? 2400 : 1000) * dt / cam.zoom      // screen px per second
    * (window.Options ? Options.scrollFactor() : 1);                    // Options > Speed > scroll speed
  cam.x += vx * speed; cam.y += vy * speed;
}

function zoomAt(z, sx = innerWidth / 2, sy = innerHeight / 2) {
  if (window.WorldMap && WorldMap.isOpen()) { WorldMap.zoomBy(z / cam.zoom, sx / UIX.scale, sy / UIX.scale); return; }   // world.js "Zoom"
  z = Math.min(5, Math.max(0.25, z));                 // 25 % .. 500 % (user 10-28)
  const wx = cam.x + sx / cam.zoom, wy = cam.y + sy / cam.zoom;
  cam.zoom = z; cam.x = wx - sx / z; cam.y = wy - sy / z;
}

// world tile (fractional) under a screen-plane pixel of this view (tileX/tileY's inverse, no elevation)
function pixelWorld(px, py) { return worldXY((px / 30 + py / 15) / 2, (py / 15 - px / 30) / 2); }

// turn the view (FUN_00408930): d = +2 PgUp / right third of the rotate button (FUN_0044A620), -2 PgDn / left
// third (FUN_0044A6E0), 0 Home / middle (FUN_00408A60: back to 0). The tile at the centre of the map area stays
// there (FUN_00449F80). Presentation only, except for the rule below.
// The sim keeps the view for one rule only, the wall sentries' walkable wall tiles (exe 0x00587E50 per view,
// 0x004CFEE0 moves sentries on a turn; docs/play/rotation.md "The view in the sim"): a live tab tells it its view
// (`view N`, no tick: accepted at any time) whenever the frames' meta shows another one.
let viewSent = -1;
function tellView() {
  if (viewSent === VIEW) return;
  const v = viewSent = VIEW;
  fetch("/cmd", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cmd: `view ${v}` }) })
    .catch(() => { }).finally(() => { setTimeout(() => { if (viewSent === v) viewSent = -1; }, 1000); });
}

function rotateView(d) {
  const nv = d ? (VIEW + d + 8) & 7 : 0;
  if (nv === VIEW) return;
  const sx = (UIX.panelX * UIX.scale) / 2 / cam.zoom, sy = innerHeight / 2 / cam.zoom;
  const [x, y] = pixelWorld(cam.x + sx, cam.y + sy);
  VIEW = nv;
  cam.x = tileX(x, y) - sx; cam.y = tileY(x, y) - sy;
  if (T) buildTerrain();
  waterAt = 0; waterBatch.clear();
  UIX.mm.key = null;                              // minimap: rebuilt in this view
  if (P.live) tellView();
}

const SPEEDS = [15, 30, 60, 120, 240, 480, 960, 1920];   // 1x = 15 ticks/s
function setRate(r) { if (P.live) control({ rate: r }); else P.rate = r; }
function stepRate(d) { const i = SPEEDS.indexOf(P.rate); setRate(SPEEDS[Math.max(0, Math.min(SPEEDS.length - 1, (i < 0 ? 3 : i) + d))]); }

let drag = null;
view.addEventListener("contextmenu", e => e.preventDefault());
// WebGL can lose its context (GPU reset, driver update): all textures are gone, so start over
// before a reload, keep the music's place (audio.js resumes it) and count the resets (bugs.md 53: music restarting)
function keepMusic() {
  try {
    const m = audio && audio.musicAt();
    if (m) sessionStorage.setItem("polis-music", JSON.stringify(m));
    const n = +(localStorage.getItem("polis-gl-resets") || 0) + 1;
    localStorage.setItem("polis-gl-resets", String(n));
    console.warn(`[play] graphics context lost (${n} so far); reloading`);
  } catch (e) { }
}
view.addEventListener("webglcontextlost", e => { e.preventDefault(); keepMusic(); UI.status.textContent = "Graphics reset; reloading…"; UI.status.hidden = false; });
view.addEventListener("webglcontextrestored", () => location.reload());
addEventListener("pagehide", () => { try { const m = audio && audio.musicAt(); if (m) sessionStorage.setItem("polis-music", JSON.stringify(m)); } catch (e) { } });
let downInUI = false;
view.addEventListener("mousedown", e => {
  if (audio) audio.start();
  downInUI = uiDown(e);
  if (downInUI) return;
  if (audio) audio.sfxNamed("button");
  // a selected company = the exe's move-order mode 0x48: a right click only leaves it and clears the selection
  // (screen_input 0x00514C10 on the right-button release flag 0x00F2A6FC, mouse_poll 0x0050B470)
  if (e.button === 2 && window.MilPanel && MilPanel.mode()) { MilPanel.close(); return; }   // milpanel.js (0x48 / 0x20)
  if (e.button === 2 && window.Military && Military.selected) { Military.select(0); return; }
  if (e.button === 2 && !Build.tool) {             // right click: a walker's window, else the building's
    const mx = e.clientX / UIX.scale, my = e.clientY / UIX.scale;
    const wx = cam.x + e.clientX / cam.zoom, wy = cam.y + e.clientY / cam.zoom;
    let hit = null;                               // the frontmost walker picture under the cursor (bugs.md 80)
    for (const h of Scene.walkerHits()) if (wx >= h[1] && wy >= h[2] && wx < h[1] + h[3] && wy < h[2] + h[4] && (!hit || h[5] >= hit[5])) hit = h;
    const t = screenTile(e.clientX, e.clientY), b = t && buildingAt(t[0], t[1]);
    // a walker standing on the clicked building's own tiles (horses in a corral, a boat at a pier) leaves the
    // click to the building, as the exe's tile rule (FUN_005717D0: the tile's building first)
    if (hit && !(b && buildingAt(hit[6], hit[7]) === b)) { openWalkers(hit[6], hit[7], hit[0], mx, my); return; }
    if (b && b.key !== "bridge") openInfo(b, mx, my);   // a bridge is land in the exe (water crossing 70:21)
    else if (t) openWalkers(t[0], t[1], null, mx, my);   // land: its window with the walkers around that tile (exe)
    return;
  }
  if (buildDown(e)) return;
  if (e.button !== 0) return;
  drag = { x: e.clientX, y: e.clientY, cx: cam.x, cy: cam.y };
  if (window.MilPanel && MilPanel.mode()) { drag.box = true; MilPanel.boxStart(e); }   // 0x48 / 0x20: a selection box
  else view.classList.add("drag");
});
window.addEventListener("mouseup", e => {
  if (downInUI) { downInUI = false; return; }
  if (buildUp(e)) return;
  if (drag && drag.box && window.MilPanel && MilPanel.boxEnd(e)) { }   // FUN_00433A60 / 0x00433700: a box selection
  else if (drag && (drag.box || Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) < 4) && window.MilPanel && e.button === 0)
    MilPanel.mapClick(e, screenTile(e.clientX, e.clientY));      // 0x48 / 0x20: select a company or trireme, or a move order
  else if (drag && Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) < 4 && window.Military) Military.mapClick(e);
  if (drag && Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) < 4 && audio) {   // a click, not a drag
    const t = screenTile(e.clientX, e.clientY), b = t && buildingAt(t[0], t[1]);
    if (b) audio.click(b.key);
  }
  drag = null;
  view.classList.remove("drag");
});
window.addEventListener("mousemove", e => {
  const overUI = uiMove(e);
  if (!overUI || drag || Build.dragFrom) buildMove(e);
  if (drag && drag.box) { if (window.MilPanel) MilPanel.boxMove(e); }
  else if (drag) { cam.x = drag.cx - (e.clientX - drag.x) / cam.zoom; cam.y = drag.cy - (e.clientY - drag.y) / cam.zoom; }
  tip(e);
});
view.addEventListener("wheel", e => { e.preventDefault(); if (inUI(e.clientX, e.clientY) && !(window.WorldMap && WorldMap.isOpen())) return; zoomAt(cam.zoom * (e.deltaY < 0 ? 1.25 : 0.8), e.clientX, e.clientY); }, { passive: false });
window.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT") return;
  if (window.NewGame && NewGame.key(e)) return;   // the leader-name screen takes the keyboard (newgame.js)
  if (fmKey(e)) return;                           // File dialogs take the keyboard
  const k = e.key.toLowerCase();
  // ours (user 11-03): Esc leaves the world map for the city (not during a colony choice)
  if (k === "escape" && window.WorldMap && WorldMap.isOpen() && !WorldMap.colony) { WorldMap.close(); e.preventDefault(); return; }
  if (buildKey(k)) return;
  keys.add(k);
  if (PAN[k]) e.preventDefault();
  // the original's keys (manual appendix 2; exe WM_KEYDOWN/WM_CHAR 0x005C4E04, docs/play/keys.md)
  const PAGE_KEYS = "1234567890-";
  if (!e.ctrlKey && !e.metaKey && !e.altKey && PAGE_KEYS.includes(e.key)) pageKey(PAGE_KEYS.indexOf(e.key));
  else if (k === "p") togglePlay();
  else if (k === "pageup") { rotateView(2); e.preventDefault(); }       // exe WM_KEYDOWN 0x21 -> 0x00408930 (F135F8 = 2)
  else if (k === "pagedown") { rotateView(-2); e.preventDefault(); }    // 0x22 (F135F8 = 1)
  else if (k === "home") { rotateView(0); e.preventDefault(); }         // 0x24 (F135F8 = 0)
  else if (k === " ") { toggleOverlay(); e.preventDefault(); }
  else if (k === "tab") { UIX.tab = UIX.tab ? 0 : 1; e.preventDefault(); }
  else if (/^f[1-4]$/.test(k)) { bookmark(+k[1] - 1, e.ctrlKey || e.metaKey); e.preventDefault(); }
  else if (k === "]" || k === "+" || k === "=") stepRate(1);
  else if (k === "[" || k === "_") stepRate(-1);
  // ours
  else if (k === "e") zoomAt(cam.zoom * 1.25);
  else if (k === "q") zoomAt(cam.zoom * 0.8);
  else if (k === "0" && (e.ctrlKey || e.altKey)) zoomAt(1);
  else if (e.key === "M" && audio) { audio.start(); setMuted(!audio.muted); }
  else if (k === "escape") { closeMenus(); UIX.submenu = null; UIX.info = null; }
  else if (k === "`") document.body.classList.toggle("dev");
  else if (k === "h" && !e.ctrlKey && !e.metaKey) cycleHires(e.shiftKey ? "terrain" : "figures");   // docs/play/hires.md
});
// build_menu_select 0x0051CA20: on the city screen (1) or an advisor (7) only; with an advisor open, a page
// without one takes no key; the current page's key toggles 1 <-> 7 (when the page has an advisor);
// another page's key switches the page, and its advisor while one is open (FUN_00516D50)
function pageKey(i) {
  const A = window.Advisors, open = !!(A && A.isOpen()), adv = A ? A.advisorOfPage(i) : 0;
  if (open && !adv) return;
  const tut = P.f0 && P.f0.episode && P.f0.episode.tutorial;      // FUN_00516F50: a tutorial's category off
  if (tut && !tut.build_categories[i]) return;
  if (i === UIX.page && adv) { if (open) A.close(); else { UIX.submenu = null; UIX.info = null; A.open(adv); } return; }
  UIX.page = i; UIX.tab = 0; UIX.submenu = null;
  if (open) A.open(adv);
}
window.addEventListener("keyup", e => keys.delete(e.key.toLowerCase()));
window.addEventListener("blur", () => keys.clear());

let showTips = true;
function tip(e) {
  const el = document.getElementById("tip");
  if (!T || drag || !showTips || e.target !== view || inUI(e.clientX, e.clientY)) { el.style.display = "none"; return; }
  const t = screenTile(e.clientX, e.clientY);
  if (!t) { el.style.display = "none"; return; }
  const [x, y] = t;
  let text = `(${x},${y})`;
  const b = buildingAt(x, y);
  if (b) text += `  ${b.key}${b.kind === "house" ? " L" + b.level : ""}  ${b.reason || ""}`;
  el.textContent = text;
  el.style.display = "block";
  el.style.left = e.clientX + 14 + "px";
  el.style.top = e.clientY + 14 + "px";
}

// --- control bar + menus (viewer/play.html) --------------------------------------------------------
const $ = id => document.getElementById(id);
const UI = { sync: $("sync"), synct: $("synct"), date: $("date"), pop: $("pop"), money: $("money"), fps: $("fps"), zoom: $("zoomv"), play: $("play"), speeds: [],
             mode: $("mode"), timeline: $("timeline"), scrubbing: false, status: $("status") };
// space: the original swaps the page's overlay with normal view (WM_CHAR, 0x00516C60)
const lastOverlay = {};
function toggleOverlay() {
  const pg = UIX.page, cur = UIX.overlay[pg];
  if (cur) { lastOverlay[pg] = cur; UIX.overlay[pg] = 0; return; }
  const ovs = (UIX.D && UIX.D.pages[pg] && UIX.D.pages[pg].overlays) || [];
  UIX.overlay[pg] = lastOverlay[pg] || (ovs[0] && ovs[0].id) || 0;
}

// F1-F4 go to a bookmarked view, Ctrl+F1-F4 bookmark the current one (kept in the prefs)
function bookmark(i, set) {
  const p = prefs(), b = p.bookmarks || [];
  if (set) {
    b[i] = camView();
    try { localStorage.setItem(PREFS, JSON.stringify({ ...p, bookmarks: b })); } catch (e) { }
    return toast(`bookmark F${i + 1} set`);
  }
  const v = b[i];
  if (!v) return toast(`no bookmark on F${i + 1} (Ctrl+F${i + 1} sets it)`);
  setCamView(v);
}

// keep the messages above the dev bar, whatever its height (it wraps on narrow windows)
function placeMsgs() {
  const bar = $("bar"), m = $("msgs");
  if (bar && m) m.style.bottom = (getComputedStyle(bar).display !== "none" ? bar.offsetHeight + 8 : 8) + "px";
}
addEventListener("resize", placeMsgs);
setInterval(placeMsgs, 1000);

function togglePlay() { if (P.live) control({ paused: !P.paused }); else P.playing = !P.playing; }
UI.mode.onclick = () => setLive(true);
UI.timeline.addEventListener("pointerdown", () => { UI.scrubbing = true; });
UI.timeline.addEventListener("input", () => {
  const t = +UI.timeline.value;
  if (t >= P.liveTick - LAG) return setLive(true);
  if (P.live) setLive(false);
  jumpTo(t);
});
window.addEventListener("pointerup", () => { UI.scrubbing = false; });
const SPEED_LABEL = r => `${r / 15}×`;
for (const r of SPEEDS) {
  const b = document.createElement("button");
  b.textContent = SPEED_LABEL(r);
  b.dataset.rate = r;
  b.title = `${r} ticks/s`;
  b.onclick = () => setRate(r);
  $("speeds").appendChild(b);
  UI.speeds.push(b);
}
$("play").onclick = togglePlay;
$("live").onclick = () => setLive(true);
$("zin").onclick = () => zoomAt(cam.zoom * 1.25);
$("zout").onclick = () => zoomAt(cam.zoom * 0.8);
$("zoomv").onclick = () => zoomAt(1);
function closeMenus() { for (const m of document.querySelectorAll(".menu")) m.hidden = true; }
for (const [btn, menu] of [["soundb", "soundm"], ["optb", "optm"], ["helpb", "helpm"]]) {
  $(btn).onclick = e => { const m = $(menu), was = m.hidden; closeMenus(); m.hidden = !was; e.stopPropagation(); if (menu === "optm") showGpuMem(); };
}
view.addEventListener("mousedown", closeMenus);
function setMuted(v) { if (!audio) return; audio.start(); if (audio.muted !== v) audio.toggle(); $("mute").checked = v; save(); }
$("mute").onchange = e => setMuted(e.target.checked);
for (const ch of ["music", "sfx", "amb", "voice"]) {
  $("v_" + ch).oninput = e => { if (audio) { audio.start(); audio.setVolume(ch, +e.target.value / 100); } save(); };
}
$("tips").onchange = e => { showTips = e.target.checked; save(); };
let newArmed = 0;
$("newcity").onclick = () => {                    // two clicks: the running city is discarded
  if (performance.now() - newArmed > 3000) { newArmed = performance.now(); $("newcity").textContent = "Click again to confirm"; return; }
  $("newcity").textContent = "New empty city";
  newArmed = 0;
  closeMenus();
  newCity();
};

const PREFS = "polis-play";
function save() {
  try {
    localStorage.setItem(PREFS, JSON.stringify({ ...prefs(), tips: showTips, muted: audio ? audio.muted : false,
      vol: Object.fromEntries(["music", "sfx", "amb", "voice"].map(c => [c, +$("v_" + c).value])),
      cam: camReady ? camView() : prefs().cam,     // still loading: keep the saved view (the camera is at 0,0)
      ui: UIX.size, pause: { ...PAUSE }, barFolded: document.body.classList.contains("barc"),
      hires: { choice: HIRES.choice, filter: HIRES.filter, text: HIRES.text, origPng: HIRES.origPng } }));
  } catch (e) { }
}
// the camera as the world point at the screen centre + zoom (independent of the window size)
// in view-0 pixels whatever the view (docs/play/rotation.md), so saves and bookmarks survive a turn
function camView() {
  const [x, y] = pixelWorld(cam.x + innerWidth / 2 / cam.zoom, cam.y + innerHeight / 2 / cam.zoom);
  return { x: (x - y) * 30, y: (x + y) * 15, zoom: cam.zoom };
}
function setCamView(v) {
  const x = (v.x / 30 + v.y / 15) / 2, y = (v.y / 15 - v.x / 30) / 2;
  cam.zoom = v.zoom; cam.x = tileX(x, y) - innerWidth / 2 / cam.zoom; cam.y = tileY(x, y) - innerHeight / 2 / cam.zoom;
}
let savedCam = null, camReady = false;
function saveCam() {                               // camera changes come from many places: poll it
  if (!camReady) return;
  const v = camView(), k = `${Math.round(v.x)},${Math.round(v.y)},${v.zoom}`;
  if (k !== savedCam) { savedCam = k; save(); }
}
function prefs() { try { return JSON.parse(localStorage.getItem(PREFS)) || {}; } catch (e) { return {}; } }
function restore() {
  let p = null;
  try { p = JSON.parse(localStorage.getItem(PREFS)); } catch (e) { }
  if (!p) return;
  showTips = p.tips !== false; $("tips").checked = showTips;
  for (const c of ["music", "sfx", "amb", "voice"]) if (p.vol && p.vol[c] != null) { $("v_" + c).value = p.vol[c]; if (audio) audio.setVolume(c, p.vol[c] / 100); }
  if (p.muted && audio) { audio.muted = true; $("mute").checked = true; }
  if (p.ui && p.ui.pct) uiSetSize(p.ui.pct, !!p.ui.sharp);
  if (p.pause) { PAUSE.info = !!p.pause.info; PAUSE.msg = !!p.pause.msg; PAUSE.auto = p.pause.auto !== false; PAUSE.world = !!p.pause.world; }
  $("pauseinfo").checked = PAUSE.info; $("pausemsg").checked = PAUSE.msg; $("autoclose").checked = PAUSE.auto; $("pauseworld").checked = PAUSE.world;
  foldBar(!!p.barFolded);
}
function foldBar(on) {
  document.body.classList.toggle("barc", on);
  $("barc").textContent = on ? "▶" : "◀";
  $("barc").title = on ? "show the bar" : "hide the bar (click the tab to show it again)";
  placeMsgs();
}
$("barc").onclick = () => { foldBar(!document.body.classList.contains("barc")); save(); };
$("pauseinfo").onchange = e => { PAUSE.info = e.target.checked; save(); };
$("pausemsg").onchange = e => { PAUSE.msg = e.target.checked; save(); };
$("autoclose").onchange = e => { PAUSE.auto = e.target.checked; save(); };
$("pauseworld").onchange = e => { PAUSE.world = e.target.checked; save(); };

// Options > Interface size (ui.js uiSetSize): the label shows what is drawn (sharp rounds it)
function showUiSize() {
  const dpr = window.devicePixelRatio || 1, real = Math.round(UIX.scale * 100);
  $("uiscale").value = UIX.size.pct; $("uisharp").checked = UIX.size.sharp;
  $("uiscalev").textContent = ` ${real}%` + (UIX.size.sharp ? ` (${Math.round(UIX.scale * dpr)}:1)` : "");
}
$("uiscale").oninput = e => { uiSetSize(+e.target.value, $("uisharp").checked); showUiSize(); save(); };
$("uisharp").onchange = e => { uiSetSize(+$("uiscale").value, e.target.checked); showUiSize(); save(); };

// --- start -----------------------------------------------------------------------------------------
(async () => {
  terrainBatch = R.batch();
  waterBatch = R.batch();
  lavaBatch = R.batch();
  terrainBatch.bias = waterBatch.bias = lavaBatch.bias = 1 / 512;  // ground tiles: one tie rule at the joins (gl.js)
  buildInit(R);
  objBatch = R.batch();
  objBatch.bias = 1 / 512;                        // the same tie rule: ground tops and bases meet in the two batches (bugs.md 185)
  R.onMissing = resumeSheet;                      // a draw needs a freed texture (loadAtlases)
  { const u = +new URLSearchParams(location.search).get("units"); if (u > 0) R.unitBudget = Math.min(u, R.units); }   // tests: split draws
  setInterval(evictIdle, 1000);
  // the download bars (showLoading, hiresProgress) move while a big sheet streams in
  const dlTimer = setInterval(() => { showLoading(); if (hiresShown) hiresProgress(...hiresShown); }, 250);
  hiresPrefetch((prefs().hires || {}).choice);    // not awaited: downloads while the rest loads
  await loadMaps();
  STARTUP.maps = performance.now();
  await loadAtlases(R, [...new Set([...ATLAS_FILES, ...((MAP.monuments && MAP.monuments.files) || [])])]);
  STARTUP.atlases = performance.now();
  if (MAP.fonts && window.ZText) ZText.init({ fonts: MAP.fonts, sprite: (f, i) => sprite(f, i) });
  if (MAP.info_panels && window.ZInfo) ZInfo.init(MAP.info_panels);
  if (MAP.ui) uiInit(R, MAP.ui);
  if (MAP.audio) audio = new PlayAudio(MAP.audio, probe);
  restore();
  showUiSize();
  {                                               // hi-res variants from the prefs (default: the original)
    const h = prefs().hires || {};
    if (h.filter) HIRES.filter = h.filter;
    if (h.text === false) HIRES.text = false;
    HIRES.origPng = !!h.origPng;
    const ix = await hiresIndex();
    const on = Object.keys(ix.sets).filter(s => ((h.choice || {})[s] || "original") !== "original");
    HIRES.all = on.length ? { done: 0, total: on.reduce((t, s) => t + (ix.sets[s].sheets || 1), 0) } : null;
    for (const set of Object.keys(ix.sets)) {
      const m = (h.choice || {})[set] || "original";
      HIRES.choice[set] = m;
      if (m !== "original") try { await setHires(set, m, `${on.indexOf(set) + 1} of ${on.length}`); }
                            catch (e) { console.warn("hi-res", set, m, e); hiresProgress(null); }
    }
    HIRES.all = null;
    hiresProgress(null);
    hiresMenu();
  }
  STARTUP.hires = performance.now();
  T = Comms.mark(await getJSON("terrain.json"));   // (the server's keys: protocol 2 deltas build on them)
  buildTerrain();
  const pc = prefs().cam;
  if (pc && isFinite(pc.x) && isFinite(pc.y) && pc.zoom > 0) {   // where the player left off
    setCamView(pc);
  } else {
    const cx = 150, cy = 140;                     // around the sandbox city
    cam.x = tileX(cx, cy) - innerWidth / 2;
    cam.y = tileY(cx, cy) - innerHeight / 2;
  }
  savedCam = null; camReady = true;
  setInterval(saveCam, 1000);
  addEventListener("pagehide", saveCam);
  // GPU memory back at once (gl.js release), also for a page kept in the back/forward cache: it starts again if shown
  addEventListener("pagehide", () => R.release());
  addEventListener("pageshow", e => { if (e.persisted) location.reload(); });
  document.getElementById("loading").remove();
  clearInterval(dlTimer);
  setInterval(() => { if (hiresShown) hiresProgress(...hiresShown); }, 250);   // (a set switched on later)
  STARTUP.ready = performance.now();                // ms since navigation (docs/play/hires.md "Startup")
  setInterval(pollFrames, 100);
  requestAnimationFrame(frame);
  if (window.NewGame) NewGame.boot();             // first open (no leader name stored): the front end's main menu
})();
