// Play-mode building: the original's build menu, a ghost preview, and the sim's own commands sent to
// the server (POST /cmd, the script language: build KEY X Y, road X1 Y1 X2 Y2, clear ...). The server
// decides what is legal; /footprint.json only colours the preview.
"use strict";

const CATEGORIES = [
  ["Population", ["house", "elite_house"]],
  ["Husbandry", ["wheat_farm", "onion_farm", "carrot_farm", "grapevine", "olive_tree", "fruit_tree", "growers_lodge",
                 "fruit_lodge", "sheep_farm", "goat_farm", "sheep", "goat", "cattle", "corral", "hunting_lodge",
                 "fishing_wharf", "urchin_quay", "horse_ranch"]],
  ["Industry", ["timber_mill", "marble_quarry", "foundry", "mint", "black_marble_shop", "orichalc_refinery", "winery",
                "oil_press", "sculpture_studio", "armory", "chariot_workshop", "artisans_guild"]],
  ["Distribution", ["granary", "storehouse", "agora", "grand_agora", "food_vendor", "fleece_vendor", "oil_vendor",
                    "wine_vendor", "arms_vendor", "horse_trainer", "chariot_vendor", "dock", "trading_post", "endless_warehouse"]],
  ["Hygiene & Safety", ["fountain", "infirmary", "maintenance", "guardpost"]],
  ["Administration", ["palace", "tax_office", "bridge", "roadblock"]],
  ["Culture", ["podium", "college", "gymnasium", "drama_school", "theatre", "stadium", "race_track", "bibliotheke",
               "university", "observatory", "laboratory", "inventors_workshop", "museum"]],
  ["Mythology", ["sanctuary_zeus", "sanctuary_poseidon", "sanctuary_demeter", "sanctuary_apollo", "sanctuary_artemis",
                 "sanctuary_ares", "sanctuary_aphrodite", "sanctuary_hermes", "sanctuary_athena", "sanctuary_hephaistos",
                 "sanctuary_dionysus", "sanctuary_hades", "sanctuary_hera", "sanctuary_atlas", "sanctuary_poseidon_grand",
                 "pyramid_01", "pyramid_02", "pyramid_03", "pyramid_04", "pyramid_05"]],
  ["Military", ["wall", "tower", "gatehouse", "trireme_wharf"]],
  ["Aesthetics", ["gardens", "bench", "flower_garden", "gazebo", "hedge_maze", "fish_pond", "short_obelisk", "tall_obelisk",
                  "sundial", "topiary", "spring", "stone_circle", "water_park", "bird_bath", "shell_garden",
                  "doric_column", "ionic_column", "corinthian_column", "dolphin_sculpture", "orrery", "baths",
                  "commemorative_monument", "avenue", "boulevard"]],
];
const LINE_TOOLS = { road: "path", wall: "wall",                             // drag A -> B (road: the game's route; wall: straight, 1-2 thick)
                     avenue: "avenue", boulevard: "boulevard" };              // straight, along a road
const ALONG_ROAD = new Set(["avenue", "boulevard"]);  // ghost from /footprint.json (red where it won't build)
const ROUTED = new Set(["road"]);                     // drag follows the game's route round buildings (bugs.md 69)
const CHECKED = new Set(["wall"]);                    // ghost tile by tile from /footprint.json, the command's rule (bugs.md 86)
const FILL_KINDS = new Set(["house", "decor", "orchard"]);                    // drag a rectangle, one per spot
// agoras: no side; the server searches the spot and side from the cursor tile as the exe (agora.snap, bugs.md 30)
const SNAPS = new Set(["agora", "grand_agora"]);
// monuments (sanctuaries, pyramids, palace): R turns them 0..3 (exe FUN_0053DE20, bugs.md 133), see sidesOf
const sidesOf = key => SIDES[key] || ((Build.cat[key] || {}).kind === "monument" ? MONUMENT_SIDES : undefined);
const MONUMENT_SIDES = ["0", "1", "2", "3"];
const SIDES = { stadium: ["v", "h"], water_park: ["0", "1", "2", "3", "4", "5", "6", "7"],
                gatehouse: ["h", "v"] };
// shore buildings, half over water (sim/systems/shore.py, bugs.md 131): the cursor tile is the anchor of the half-water
// square (the dock's pier); "auto" = the exe's first orientation that fits (FUN_004A10C0), R picks a water side
const SHORE = new Set(["fishing_wharf", "urchin_quay", "dock", "trireme_wharf"]);
for (const k of SHORE) SIDES[k] = ["auto", "n", "e", "s", "w"];
// horse ranch: R puts the 4x4 corral east (0, the exe's default), north, west or south of the house (bugs.md 134)
SIDES.horse_ranch = ["0", "1", "2", "3"];
// commemorative monument: the variant comes from the Monuments submenu (22: the granted ones, ui.js; tool.variant;
// the dev bar: "auto" = the first one granted); R turns it 0..3 as the exe's preview (FUN_00456E30 cycles
// DAT_00DA23C4 -> Building+0xAC: the god statues' facing; sim/systems/commemorative.py)
SIDES.commemorative_monument = ["0", "1", "2", "3"];
const COMMEM = "commemorative_monument";
const commemVariant = t => (t && t.variant) || "auto";
const commemShown = t => {                       // the variant the ghost shows: the chosen one, else the first granted
  if (t && t.variant) return t.variant;
  const a = (typeof S !== "undefined" && S && S.monuments_available) || [];
  return a.length ? a[0][0] : 1;
};
const commemSize = v => (v >= 22 && v <= 33) || (v >= 50 && v <= 61) || [36, 37, 64, 65].includes(v) ? 4 : 3;
const SERVER_GHOST = new Set([...SHORE, "horse_ranch"]);   // picture from /footprint.json's ghost (layout by the sim)                                     // R toggles; [0] = the exe's default
const BOXES = { gatehouse: { h: [5, 2], v: [2, 5] } };   // w x h per orientation (game.py gate_tiles, bugs.md 88)

const Build = {
  cat: {},              // data/buildings.json
  tool: null,           // {key} | {line: "road"} | {clear: true}
  side: 0,              // agora orientation index
  hover: null,          // [x, y]
  dragFrom: null,       // [x, y] while dragging a line/rect
  pending: null,        // {key, spots, w, h, tick}: a placed drag, drawn until a snapshot shows it
  frozen: null,         // [x, y]: footprint held in place ('m', the original's sanctuary helper)
  fp: null,             // last /footprint.json answer
  fpKey: "",
  ghost: null,          // batch
  ui: null,             // {green, red, yellow} diamond sprites
  busy: false,
  cleared: null,        // {rects, seq, gen}: a clear hidden until the snapshot and terrain show it (bugs.md 102)
};

function buildInit(R) {
  Build.ghost = R.batch();
  const c = document.createElement("canvas");               // three tile diamonds as a sprite sheet
  c.width = 180; c.height = 30;
  const x = c.getContext("2d");
  [["rgba(60,220,60,0.45)", 0], ["rgba(230,40,40,0.5)", 60], ["rgba(240,210,60,0.5)", 120]].forEach(([col, ox]) => {
    x.fillStyle = col;
    x.beginPath(); x.moveTo(ox + 29, 0); x.lineTo(ox + 58, 15); x.lineTo(ox + 29, 30); x.lineTo(ox, 15); x.closePath(); x.fill();
  });
  const sheet = R.addSheet(c);
  const d = ox => ({ sheet, x: ox, y: 0, w: 58, h: 30, ax: 0, ay: 0, flip: false, iso: 1 });
  Build.ui = { green: d(0), red: d(60), yellow: d(120) };
  getJSON("/data/buildings.json").then(c => { Build.cat = c; buildMenu(); }).catch(() => buildMenu());
}

// --- menu ------------------------------------------------------------------------------------------
function buildMenu() {
  const tabs = $("bcats"), list = $("blist");
  tabs.innerHTML = "";
  const show = (name, keys) => {
    for (const b of tabs.children) b.classList.toggle("on", b.textContent === name);
    list.innerHTML = "";
    for (const k of keys) {
      const spec = Build.cat[k];
      if ((!spec && Object.keys(Build.cat).length) || !buildable(k)) continue;
      const b = document.createElement("button");
      b.className = "item";
      b.dataset.key = k;
      b.innerHTML = `<span>${spec ? spec.name : k}</span><span class="cost">${spec && spec.cost ? spec.cost + " dr" : ""}</span>`;
      b.onclick = () => selectTool(LINE_TOOLS[k] ? { line: k } : { key: k });
      list.appendChild(b);
    }
    try { localStorage.setItem("polis-play-cat", name); } catch (e) { }
  };
  let first = CATEGORIES[0][0];
  try { first = localStorage.getItem("polis-play-cat") || first; } catch (e) { }
  for (const [name, keys] of CATEGORIES) {
    const b = document.createElement("button");
    b.textContent = name;
    b.onclick = () => show(name, keys);
    tabs.appendChild(b);
  }
  const c = CATEGORIES.find(c => c[0] === first) || CATEGORIES[0];
  show(c[0], c[1]);
  $("t_road").onclick = () => selectTool({ line: "road" });
  $("t_clear").onclick = () => selectTool({ clear: true });
  $("t_none").onclick = () => selectTool(null);
}

function selectTool(t) {
  if (t && !P.live) { toast("replaying (read-only): press ● LIVE or ⏭ live to build", true); t = null; }
  const was = Build.tool && Build.tool.key;
  Build.tool = t;
  if (!t || t.key !== was) Build.side = 0;        // a new tool starts in its default orientation (the exe:
  Build.dragFrom = null;                          // build_tool_select 0x00404330 sets the gatehouse's 1 = h)
  Build.frozen = null;
  Build.fp = null; Build.fpKey = "";
  const key = t && (t.key || t.line || (t.clear && "clear"));
  for (const b of document.querySelectorAll("#build .item, #build .tool")) b.classList.toggle("on", b.dataset.key === key);
  $("bhint").textContent = !t ? "Drag to scroll. Pick something to build."
    : t.line && ALONG_ROAD.has(t.line) ? `Drag along a road (${t.line}: the road stays, strips beside it). Right-click or Esc: stop.`
    : t.line ? `Drag from start to end (${t.line}). Right-click or Esc: stop.`
    : t.clear ? "Drag over the land to clear (trees, roads, buildings). Right-click or Esc: stop."
    : (FILL_KINDS.has(kindOf(t.key)) ? "Click, or drag to fill an area. " : "Click to place. ")
      + (sidesOf(t.key) ? "R: rotate. " : "") + "Right-click or Esc: stop.";
  view.classList.toggle("building", !!t);
}

const kindOf = key => (Build.cat[key] || {}).kind;
// Poseidon buildings show only after `poseidon on` (the sim's switch, sent in every frame; the decision log)
// sanctuaries: only those the scenario's Mythology menu offers (FUN_00402B80; frame.sanct from sim/gods, null = all)
// test-only buildings ("test": true, the endless warehouse; sim/testcmds.py) are never offered in play mode
// an episode's allowed buildings: frame.episode.unavailable (sim/allowed.py, buildings_availability 0x00402B80;
// absent in open play)
const episodeOff = key => !!(P.f0 && P.f0.episode && P.f0.episode.unavailable && P.f0.episode.unavailable.includes(key));
const buildable = key => !(Build.cat[key] || {}).test && (!(Build.cat[key] || {}).poseidon || !!(P.f0 && P.f0.poseidon)) &&
  !(key.startsWith("sanctuary_") && P.f0 && Array.isArray(P.f0.sanct) && !P.f0.sanct.includes(key)) && !episodeOff(key);
const sizeOf = key => (Build.cat[key] || {}).size || 1;
// monuments (palace, sanctuaries, pyramids) have a w x h layout box instead of a size
const boxOf = key => {
  const c = Build.cat[key] || {};
  const o = c.orientations || BOXES[key];
  if (SHORE.has(key)) return key === "trireme_wharf" ? [3, 3] : [2, 2];       // the half-water square
  if (o && sidesOf(key)) return o[sidesOf(key)[Build.side % sidesOf(key).length]];  // stadium: v 5x10, h 10x5; gatehouse h 5x2, v 2x5
  if (c.kind === "monument" && c.w) return Build.side % 2 ? [c.h, c.w] : [c.w, c.h];   // turned: H x W
  if (key === COMMEM) { const n = commemSize(commemShown(Build.tool)); return [n, n]; }   // large god statues: 4x4
  return [sizeOf(key), sizeOf(key)];
};

// --- geometry of a tool action ---------------------------------------------------------------------
function anchorFor(key, tx, ty) {                 // cursor tile -> top-left of the footprint (cursor near the middle)
  if (SNAPS.has(key) || SHORE.has(key)) return [tx, ty];   // agoras (0x0040BF40 searches from it), shore buildings
  const [w, h] = boxOf(key);
  if (!VIEW) return [tx - ((w - 1) >> 1), ty - ((h - 1) >> 1)];
  // turned view: centre the box on the cursor on screen (in turned tiles), then back to its world min tile
  const q = VIEW === 2 || VIEW === 6, sw = q ? h : w, sh = q ? w : h, [rx, ry] = viewXY(tx, ty);
  const a = worldXY(rx - ((sw - 1) >> 1), ry - ((sh - 1) >> 1)), c = worldXY(rx - ((sw - 1) >> 1) + sw - 1, ry - ((sh - 1) >> 1) + sh - 1);
  return [Math.min(a[0], c[0]), Math.min(a[1], c[1])];
}

function lineTiles(a, b) {                        // the road command's L: along x first, then along y
  const out = [], sx = b[0] >= a[0] ? 1 : -1, sy = b[1] >= a[1] ? 1 : -1;
  for (let x = a[0]; x !== b[0] + sx; x += sx) out.push([x, a[1]]);
  for (let y = a[1] + sy; y !== b[1] + sy; y += sy) out.push([b[0], y]);
  return out;
}

function fillSpots(key, a, b) {                   // drag-filled area: one footprint per size step
  const s = sizeOf(key), out = [];
  const [x0, x1] = [Math.min(a[0], b[0]), Math.max(a[0], b[0])], [y0, y1] = [Math.min(a[1], b[1]), Math.max(a[1], b[1])];
  for (let y = y0; y <= y1; y += s) for (let x = x0; x <= x1; x += s) out.push([x, y]);
  return out;
}

function commandsFor(end) {
  const t = Build.tool, a = Build.dragFrom || end;
  if (!t || !end) return [];
  if (t.line) return [`${LINE_TOOLS[t.line]} ${a[0]} ${a[1]} ${end[0]} ${end[1]}`];
  if (t.clear) return [`clear ${a[0]} ${a[1]} ${end[0]} ${end[1]}`];
  if (t.key === "bridge") return [`bridge ${end[0]} ${end[1]}`];   // one click on a water tile by a shore (FUN_0041C450)
  let side = sidesOf(t.key) ? " " + sidesOf(t.key)[Build.side % sidesOf(t.key).length] : "";
  if (t.key === COMMEM) side = ` ${commemVariant(t)}${side}`;          // build commemorative_monument X Y V O
  if (Build.dragFrom && FILL_KINDS.has(kindOf(t.key)))
    return fillSpots(t.key, anchorFor(t.key, ...a), anchorFor(t.key, ...end)).map(([x, y]) => `build ${t.key} ${x} ${y}${side}`);
  const [x, y] = anchorFor(t.key, ...end);
  return [`build ${t.key} ${x} ${y}${side}${t.city ? " " + t.city : ""}`];   // trade: the city chosen in the Trade menu
}

// --- server ----------------------------------------------------------------------------------------
// POST /cmd with the playhead's tick (the server refuses one more than its live window behind: a replay tab's
// click never changes the city). A live tab that lagged past the window on a hiccup (bug 455) is not dropped
// to replay: it rejoins live at the server's tick and sends the commands once more from there.
async function postCmds(cmds) {
  const post = async tick => (await fetch("/cmd", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmds, tick }), signal: AbortSignal.timeout(20000) })).json();
  let res = await post(Math.floor(P.t));
  if (res.live === false && P.live) {
    P.liveTick = Math.max(P.liveTick || 0, res.tick);
    jumpTo(Math.max(0, res.tick - ahead()));
    res = await post(res.tick);
  }
  return res;
}
async function sendCommands(cmds, { sound = true } = {}) {
  let last = 0, ok = 0, cost = 0;
  const fails = [];
  let res;
  try {                                           // one request: the server applies the whole drag at once
    res = await postCmds(cmds);
  } catch (e) { Build.pending = null; toast(`${cmds[0]}: server unreachable`, true); return null; }
  if (res.live === false) { Build.pending = null; toast(res.out, true); return null; }   // a replay tab
  (res.results || []).forEach((r, i) => {
    const cmd = cmds[i];
    last = r.tick;
    if (r.ok) { ok++; const m = /cost (\d+)/.exec(r.out || ""); if (m) cost += +m[1]; if (cmds.length === 1) toast(r.out || cmd); }
    else fails.push(r.warn || `${cmd}: ${r.out}`);                 // the original's warning when it has one
  });
  const verb = sound ? "placed" : "applied";       // settings (storage orders...) are not buildings
  if (cmds.length > 1 && ok) toast(`${cmds[0].split(" ").slice(0, 2).join(" ")}: ${ok} ${verb}${cost ? `, cost ${cost}` : ""}`);
  if (fails.length) toast(fails.length > 1 ? `${fails.length} not ${verb}, e.g. ${fails[0]}` : fails[0], true);
  // once per action, not per building; clearing is silent in the original (clear_land_commit 0x0049A460 plays
  // sound 9, which has no file: docs/play/audio.md), only the button click
  if (ok && sound && audio && !/^clear /.test(cmds[0])) audio.sfxNamed("place_building");
  // keep drawing what was placed until the tab has a snapshot with it (one poll in synced live; seq, not
  // tick: a snapshot is re-recorded at the same tick after a command) or, for animals (walkers), until
  // the playhead reaches the tick; failures: don't fake them
  if (Build.pending) Build.pending = fails.length ? null : { ...Build.pending, tick: last, seq: res.seq };
  if (fails.length && Build.roadPreview && Build.roadPreview.held) { Build.roadPreview = null; buildTerrain(); }
  const cleared = (res.results || []).map((r, i) => r.ok && /^clear /.test(cmds[i]) ? cmds[i].split(" ").slice(1).map(Number) : null)
    .filter(Boolean);
  if (cleared.length && res.seq != null) clearNow(cleared, res.seq);
  // roads, walls, bridges (terrain) and buildings show at once, not at the next terrain poll (~1.5-2 s later)
  else if (ok && sound && typeof refreshNow === "function") refreshNow();
  if (!P.live && last > P.t) jumpTo(last);
  Build.fpKey = "";
  return ok ? (res.seq != null ? res.seq : last) : null;   // the snapshot seq that has them (callers: pending values)
}

let fpTimer = null;
function refreshFootprint() {                     // debounced hint for the ghost colour
  const t = Build.tool, h = Build.hover;
  if (!t || !t.key || !h) return;
  const [x, y] = anchorFor(t.key, ...h);
  let side = sidesOf(t.key) ? sidesOf(t.key)[Build.side % sidesOf(t.key).length] : "";
  if (t.key === COMMEM) side = encodeURIComponent(`${commemShown(t)} ${side}`);   // the size depends on the variant
  const k = `${t.key} ${x} ${y} ${side} ${P.stateSeq}`;
  if (k === Build.fpKey) return;
  Build.fpKey = k;
  clearTimeout(fpTimer);
  fpTimer = setTimeout(async () => {
    try { Build.fp = { ...(await getJSON(`footprint.json?key=${t.key}&x=${x}&y=${y}&d=${side}`)), at: `${[x, y]}` }; } catch (e) { }
  }, 40);
}

let avTimer = null;
function refreshAvenueGhost(a, h, drag = true) {   // the server's per-tile verdict for an avenue/boulevard drag
  // road: no drag = the cursor tile alone (FUN_00452B80); a drag's ramp pictures are in the tab's view
  const k = `${Build.tool.line} ${a[0]} ${a[1]} ${h[0]} ${h[1]} ${drag ? VIEW : "c"} ${P.stateSeq}`;
  if (k === Build.fpKey) return;
  Build.fpKey = k;
  clearTimeout(avTimer);
  avTimer = setTimeout(async () => {
    try {
      const fp = await getJSON(drag ? `footprint.json?key=${Build.tool.line}&x=${a[0]}&y=${a[1]}&x2=${h[0]}&y2=${h[1]}&v=${VIEW}`
                                    : `footprint.json?key=${Build.tool.line}&x=${h[0]}&y=${h[1]}`);
      fp.k = k;
      Build.fp = fp;
    } catch (e) { }
  }, 40);
}

// --- clear: hidden at once (bugs.md 102) -----------------------------------------------------------
// Like a placed drag's ghost: what a successful clear removed is hidden from the next frame on, until the
// tab has a snapshot with the command's seq and terrain fetched after it. Per tile the sim's order
// (Game.clear): avenue segment (left alone here), building (hidden whole), roadblock, road, wall, trees
// and rubble (tall pictures hidden; flat ones wait for the terrain).
function clearNow(rects, seq) {
  Build.cleared = { rects: rects.map(([x1, y1, x2, y2]) => [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)]),
                    seq, gen: null, T };                  // T: the terrain as it was (patched; a newer one has the clear)
  if (T) buildTerrain();                          // patchCleared + rebuild the ground batch
  if (typeof refreshNow === "function") { refreshNow(); Build.cleared.gen = terrainGen; }
}
function clearedAt(x, y) {
  const c = Build.cleared;
  if (!c) return false;
  for (const [x0, y0, x1, y1] of c.rects) if (x >= x0 && x <= x1 && y >= y0 && y <= y1) return true;
  return false;
}
function clearedBuilding(b) {                     // a building with a tile in a cleared rect, while its snapshot is old
  const c = Build.cleared;
  if (!c || P.stateSeq >= c.seq) return false;
  const w = b.w || b.size || 1, h = b.h || b.size || 1;
  for (const [x0, y0, x1, y1] of c.rects) if (b.x <= x1 && b.x + w - 1 >= x0 && b.y <= y1 && b.y + h - 1 >= y0) return true;
  return false;
}
function clearedTree(x, y) {                      // a tree/rubble picture of the old terrain in a cleared rect
  const c = Build.cleared;
  return !!c && c.T === T && clearedAt(x, y) && !!(T.flags[y * N + x] & 0x1001) && !buildingAt(x, y);
}
function patchCleared() {                         // on the old terrain, before the ground is built
  const c = Build.cleared;
  if (!c || !T || c.T !== T) return;
  const AV = new Set((T.avenues || []).map(a => a[0]));
  for (const [x0, y0, x1, y1] of c.rects) for (let y = Math.max(0, y0); y <= Math.min(N - 1, y1); y++)
    for (let x = Math.max(0, x0); x <= Math.min(N - 1, x1); x++) {
      const i = y * N + x;
      if (AV.has(i) || buildingAt(x, y)) continue;
      if (T.road[i]) T.road[i] = 0, T.patched = true;            // (T is no delta base now: play.js pollTerrain)
      else if (T.flags[i] & 0x4000) T.flags[i] &= ~0x4000, T.patched = true;
      else if (T.flags[i] & 0x1001) groundLike(i);
    }
}
// a cleared tree / rubble tile until the new terrain comes (ours; bugs.md 388): the picture of the nearest plain
// ground tile at its height (1x1, no top), so the tile shows grass at once instead of a hole; none near: left as is
// (play.js tallTerrain then keeps its ground diamond). The server's terrain replaces it.
function groundLike(i) {
  const x = i % N, y = (i / N) | 0, e = T.elev[i];
  for (let r = 1; r <= 6; r++) for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
    if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue;
    const u = x + dx, v = y + dy, j = v * N + u;
    if (u < 0 || v < 0 || u >= N || v >= N || T.elev[j] !== e || (T.flags[j] & ~0x880) || T.road[j] || !(T.draw[j] & 0x40) || !T.ids[j]) continue;
    let col = T.ids[j] >>> 14;
    if (T.version < 300 && col >= 2) col += 2;
    const sp = COLLECTIONS[col] && sprite(COLLECTIONS[col], (T.ids[j] & 0x3fff) + 201);
    if (!sp || Math.max(1, sp.iso) !== 1 || sp.h > 30) continue;
    T.ids[i] = T.ids[j]; T.draw[i] = T.draw[j]; T.flags[i] &= ~0x1001;
    if (!T.altMap) T.altMap = new Map((T.alt || []).map(r => [r[0], r.slice(1)]));   // as play.js buildTerrain
    const a = T.altMap.get(j);
    if (a) T.altMap.set(i, a); else T.altMap.delete(i);
    T.patched = true;
    return;
  }
}
function clearDone() {                            // called per frame: drop the override once the tab has caught up
  const c = Build.cleared;
  if (c && P.stateSeq >= c.seq && c.gen != null && !busy.terrain && terrainGen >= c.gen) Build.cleared = null;
}

// --- ghost -----------------------------------------------------------------------------------------
function tileDiamond(list, sp, x, y, el) {        // el: the height to draw at (default: the tile's own)
  if (x < 0 || y < 0 || x >= N || y >= N) return;
  list.push([Order.LAST + tileDepth(x, y), x, sp, tileX(x, y), tileY(x, y) - (el != null ? el : T.elev[y * N + x] || 0) * 30]);
}

// one building picture per spot, translucent (the cursor ghost and the placed-but-not-yet-shown drag)
function ghostSpots(list, key, spots, w, hh, alpha) {
  const spec = Build.cat[key] || {};
  for (const [x, y] of spots) {
    const sprites = [];
    const fp = Build.fp;                            // monuments: the finished layout the server sent (footprint ghost)
    if (spec.kind === "monument") {
      // pieces are relative to the box corner: until the preview for this spot arrives, the last one moves along
      const gh = fp && fp.ghost && fp.ghost.key === key ? fp.ghost : Build.lastGhost && Build.lastGhost.key === key ? Build.lastGhost : null;
      if (fp && fp.ghost) Build.lastGhost = fp.ghost;
      if (gh && window.Monuments) Monuments.draw(sprites, Object.assign({}, gh, { x, y }), MCTX);
      for (const s of sprites) list.push([s[0] + 2000, s[1], s[2], s[3], s[4], alpha]);
      continue;
    }
    if (key === "bridge") {                       // the span the sim's rule gives from this tile, in its pieces (bridges.js)
      if (fp && fp.pieces && fp.x === x && fp.y === y && window.Bridges) {
        if (alpha === 1) for (const [tx, ty, p] of fp.pieces) Bridges.draw(sprites, tx, ty, p);   // placed, not yet shown
        else Bridges.ghost(sprites, fp);
      }
      // the exe's ghost (FUN_0041C8E0, bridges.js): the pieces opaque, each pixel ANDed with 0x1FE3 (green; gl.js), no diamonds
      for (const s of sprites) list.push([alpha === 1 ? s[0] + 2000 : s[0], s[1], s[2], s[3], s[4], alpha === 1 ? alpha : -1]);
      continue;
    }
    if (SERVER_GHOST.has(key)) {                  // the server's layout for this spot: picture by orientation, dock house, corral
      const gh = fp && fp.ghost && fp.ghost.key === key && fp.x === x && fp.y === y ? fp.ghost : null;
      if (gh) Scene.drawOne(sprites, Object.assign({ level: 0, occupants: 1, employees: 1, goods: {} }, gh), fallbackBuilding);
      for (const s of sprites) list.push([s[0] + 2000, s[1], s[2], s[3], s[4], alpha]);
      continue;
    }
    const vs = sidesOf(key), cm = key === COMMEM;
    const variant = vs && key === "water_park" ? +vs[Build.side % vs.length] : cm ? commemShown(Build.tool) : 0;   // bugs.md 136
    const orient = cm ? Build.side % 4 : undefined;                  // commemorative: R = facing (god statues)
    Scene.drawOne(sprites, { key, kind: spec.kind, x, y, w, h: hh, size: spec.size || w, level: 0, occupants: 1, variant, orient,
                             employees: 1, goods: {}, growth: 100 }, fallbackBuilding);
    for (const s of sprites) list.push([s[0] + 2000, s[1], s[2], s[3], s[4], alpha]);
  }
}

// The build tool over the map shoos sheep / goats / cattle off its footprint (FUN_004059C0 every frame; sim
// walkers.shoo): the server is told each change of tool or footprint, and null when the tool or the cursor leaves.
let hoverSent = "null";
function syncHover() {
  const t = Build.tool, h = Build.frozen || Build.hover;
  let v = null;
  if (t && h && P.live) {
    if (t.key && kindOf(t.key) !== "animal") v = [t.key, ...anchorFor(t.key, ...h)];
    else if (t.line) v = [t.line, ...h];
    else if (t.clear) v = ["clear", ...h];
  }
  const k = JSON.stringify(v);
  if (k === hoverSent) return;
  hoverSent = k;
  fetch("/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ hover: v }) })
    .catch(() => { hoverSent = ""; });
}

function drawGhost() {
  const g = Build.ghost;
  g.clear();
  syncHover();
  clearDone();
  const list = [], pd = Build.pending;
  // buildings show with the state snapshot; animals are walkers, drawn from frames at the (lagging) playhead
  const shown = pd && (kindOf(pd.key) === "animal" ? P.t >= pd.tick : pd.seq != null ? P.stateSeq >= pd.seq : P.stateTick >= pd.tick);
  if (shown) Build.pending = null;
  else if (pd && T) ghostSpots(list, pd.key, pd.spots, pd.w, pd.h, 1);
  const t = Build.tool, h = Build.hover;
  // the exe clears the tool when the last waiting monument of the variant is placed (FUN_00402B40)
  if (t && t.key === COMMEM && t.variant && !pd && S && !(S.monuments_available || []).some(a => a[0] === t.variant)) {
    selectTool(null);
    return flushGhost(list);
  }
  roadPreviewExpire(t);
  if (!t || !h || !T) return flushGhost(list);
  if (t.line && ROUTED.has(t.line)) {
    // the road tool as the exe (bugs.md 464; oracle slope-road): a drag puts its route in the terrain (roads_drag_place(1)
    // 0x0049ACB0 + map_tiles_update_images when the trace reaches the start), so the route shows in its road pictures
    // as built, ramp roads sloped (play.js buildTerrain with Build.roadPreview); over it every frame the cursor tile
    // (FUN_00452B80): the road picture tinted green (AND 0x1FE3) where a road may go, else the red diamond, which a
    // placed end always is (a road tile). No drag: the cursor tile alone.
    const a = Build.dragFrom || h, drag = !!Build.dragFrom;
    refreshAvenueGhost(a, h, drag);
    const fp = Build.fp && Build.fp.cursor && Build.fp.k && Build.fp.k.startsWith(`${t.line} ${a[0]} ${a[1]} ${h[0]} ${h[1]} `) ? Build.fp : null;
    setRoadPreview(drag && fp && fp.ok && fp.tiles.length ? fp : null);
    if (fp) roadCursor(list, fp.cursor);
  } else if (t.line && (ALONG_ROAD.has(t.line) || CHECKED.has(t.line))) {
    if (Build.roadPreview && !Build.roadPreview.held) setRoadPreview(null);
    const a = Build.dragFrom || h;
    refreshAvenueGhost(a, h);
    const fp = Build.fp && Build.fp.tiles && Build.fp.k && Build.fp.k.startsWith(`${t.line} ${a[0]} ${a[1]} `) ? Build.fp : null;
    if (fp && fp.tiles.length) for (const [x, y, ok] of fp.tiles) tileDiamond(list, ok ? Build.ui.green : Build.ui.red, x, y);
    else if (fp) { tileDiamond(list, Build.ui.red, a[0], a[1]); tileDiamond(list, Build.ui.red, h[0], h[1]); }
    else tileDiamond(list, Build.ui.red, h[0], h[1]);
  } else if (t.line) {
    for (const [x, y] of lineTiles(Build.dragFrom || h, h)) tileDiamond(list, Build.ui.yellow, x, y);
  } else if (t.clear) {
    const a = Build.dragFrom || h;
    for (let y = Math.min(a[1], h[1]); y <= Math.max(a[1], h[1]); y++)
      for (let x = Math.min(a[0], h[0]); x <= Math.max(a[0], h[0]); x++) tileDiamond(list, Build.ui.red, x, y);
  } else {
    refreshFootprint();
    const spots = Build.dragFrom && FILL_KINDS.has(kindOf(t.key))
      ? fillSpots(t.key, anchorFor(t.key, ...Build.dragFrom), anchorFor(t.key, ...h)) : [anchorFor(t.key, ...h)];
    if (Build.fp && Build.fp.snap && spots.length === 1 && Build.fp.at === `${spots[0]}`) spots[0] = [Build.fp.x, Build.fp.y];   // vendors: the stall; agoras: the searched spot
    const fp = Build.fp && Build.fp.x === spots[0][0] && Build.fp.y === spots[0][1] ? Build.fp : null;
    const w = fp ? fp.w : boxOf(t.key)[0], hh = fp ? fp.h : boxOf(t.key)[1];
    Build.lastSpots = { key: t.key, spots, w, h: hh };
    // The exe's cursor previews (build_cursor_preview 0x00451C70 and the per-tool ones it dispatches to, e.g.
    // FUN_00453DE0 wharves): a spot that may be built shows the building's picture under the AND mask 0x1FE3 (gl.js
    // alpha < 0) and no diamonds; a refused one only the footprint's SPR_BUILD_CURSOR diamonds, green where the tile
    // is fine and red where not. Monuments (FUN_0053DE20): never the picture, every part's tiles as diamonds in one
    // colour (green / red by the spot). All at the cursor tile's height (bugs.md 389, 464). Drag-filled kinds keep the
    // translucent pictures and the tab's own diamonds (their drag previews are other functions).
    const one = spots.length === 1 && !(Build.dragFrom && FILL_KINDS.has(kindOf(t.key)));
    const mon = (Build.cat[t.key] || {}).kind === "monument", bridge = t.key === "bridge";
    if (fp) Build.lastOk = !!fp.ok;
    const valid = fp ? !!fp.ok : Build.lastOk !== false;
    if (!one || bridge) ghostSpots(list, t.key, spots, w, hh, 0.6);
    else if (valid && !mon) ghostSpots(list, t.key, spots, w, hh, -1);
    for (const [x, y] of spots) {
      // build_cursor_preview 0x00451C70: the footprint's diamonds at fixed offsets from the cursor tile, all at the
      // cursor tile's elevation (its back corner in the view, where the ghost picture stands too: scene.js elevPx
      // of viewFoot ax/ay), not each at its own height (bugs.md 389: on a slope they split into two levels)
      const f0 = viewFoot(x, y, w, hh), el = T.elev[f0.ay * N + f0.ax] || 0;
      if (fp && spots.length === 1 && t.key === "bridge" && !fp.ok && fp.tiles.length) {
        // a refused span (FUN_0041C8E0): the start diamond green (2+ tiles scanned) or red, and a red one at the
        // last scanned tile, reached in (+-29, +-15) steps as the pieces (bridges.js ghost)
        const [ax, ay] = fp.tiles[0], n = fp.tiles.length, sd = fp.dir == null ? 0 : (fp.dir - VIEW + 8) & 7;
        const el = (T.elev[ay * N + ax] || 0) * 30, X = tileX(ax, ay), Y = tileY(ax, ay) - el;
        if (n >= 2) list.push([Order.LAST, ax, Build.ui.green, X, Y]);
        list.push([Order.LAST + 1, ax, Build.ui.red, X + (n - 1) * (sd <= 2 ? 29 : -29), Y + (n - 1) * (sd === 2 || sd === 4 ? 15 : -15)]);
      } else if (bridge && fp) for (const [tx, ty, ok] of fp.tiles) {
        if (ok && fp.pieces && fp.pieces.length) continue;   // a valid span: the green pieces only
        tileDiamond(list, ok ? Build.ui.green : Build.ui.red, tx, ty);
      }
      else if (one && mon) for (let j = 0; j < hh; j++) for (let i = 0; i < w; i++)
        tileDiamond(list, valid ? Build.ui.green : Build.ui.red, x + i, y + j, el);
      else if (one && valid) continue;                    // the tinted picture alone
      else if (one && fp) for (const [tx, ty, ok] of fp.tiles) tileDiamond(list, ok ? Build.ui.green : Build.ui.red, tx, ty, el);
      // drag-filled spots (houses, gardens, statues...) and a cursor before its server answer: red where the tab's
      // map has a building or a road (bugs.md 59; the build command still decides)
      else for (let j = 0; j < hh; j++) for (let i = 0; i < w; i++) {
        const tx = x + i, ty = y + j, k = ty * N + tx, taken = tx >= N || ty >= N || buildingAt(tx, ty) || (T.road && T.road[k]);
        tileDiamond(list, taken ? Build.ui.red : Build.ui.green, tx, ty, el);
      }
    }
  }
  flushGhost(list);
}
// The road drag's route in the terrain (play.js buildTerrain, Scene.roadSprite): {k, roads: Set of tile indices,
// pics: Map tile -> [id, draw] (ramp tiles in their road pictures, sim/terrain_view.py ramp_preview), view, held}.
// After the release it is held (the road placed but not yet in the tab's terrain) until a newer terrain or 3 s.
function setRoadPreview(fp) {
  const p = Build.roadPreview;
  if (!fp) {
    if (p && !p.held) { Build.roadPreview = null; buildTerrain(); }
    return;
  }
  if (p && p.k === fp.k && p.view === VIEW) return;
  Build.roadPreview = { k: fp.k, view: VIEW, roads: new Set(fp.tiles.map(([x, y]) => y * N + x)),
                        pics: new Map((fp.ramps || []).map(r => [r[0], [r[1], r[2]]])), held: null };
  buildTerrain();
}
function roadPreviewExpire(t) {
  const p = Build.roadPreview;
  if (!p) return;
  if (p.held ? (p.held.T !== T || performance.now() > p.held.until || p.view !== VIEW) : !(t && t.line && ROUTED.has(t.line) && Build.dragFrom)) {
    Build.roadPreview = null;
    buildTerrain();
  }
}
// FUN_00452B80's picture: the road picture under the AND mask 0x1FE3 (gl.js alpha < 0), else SPR_BUILD_CURSOR red
function roadCursor(list, c) {
  const [x, y, ok, pic] = c, ag = atlas.Zeus_Terrain && atlas.Zeus_Terrain.groups;
  const first = ok && pic && ag && ag[pic[0]] && ag[pic[0]][0], sp = first && sprite("Zeus_Terrain", first + pic[1]);
  if (!sp) return tileDiamond(list, ok ? Build.ui.green : Build.ui.red, x, y);
  list.push([Order.LAST + tileDepth(x, y), x, sp, tileX(x, y), tileY(x, y) - (T.elev[y * N + x] || 0) * 30 + 30 - sp.h, -1]);
}
function flushGhost(list) {
  list.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  for (const [, , sp, x, y, al] of list) Build.ghost.push(sp, x, y, al == null ? 1 : al);
}

// --- input (called from play.js) -------------------------------------------------------------------
function buildDown(e) {
  if (!Build.tool) return false;
  if (e.button === 2) { selectTool(null); return true; }
  const t = Build.frozen || screenTile(e.clientX, e.clientY);
  if (!t) return true;
  Build.dragFrom = t;
  return true;
}

function buildMove(e) {
  if (!Build.tool || Build.frozen) return;
  Build.hover = screenTile(e.clientX, e.clientY);
}

function buildUp(e) {
  if (!Build.tool || !Build.dragFrom) return false;
  const end = Build.frozen || screenTile(e.clientX, e.clientY) || Build.hover;
  const cmds = commandsFor(end);
  if (Build.roadPreview) Build.roadPreview.held = cmds.length ? { T, until: performance.now() + 3000 } : null;
  const ls = Build.tool.key && Build.lastSpots;     // keep showing the drag until the snapshot has it
  Build.pending = ls && ls.key === Build.tool.key && cmds.length ? { ...ls, tick: Infinity } : null;
  Build.dragFrom = null;
  Build.frozen = null;
  if (cmds.length) sendCommands(cmds);
  return true;
}

function buildKey(k) {
  if (k === "escape" && Build.tool) { selectTool(null); return true; }
  if (k === "m" && Build.tool && Build.tool.key && Build.hover) {   // freeze the footprint; scroll, then click
    Build.frozen = Build.frozen ? null : Build.hover.slice();
    return true;
  }
  if (k === "r" && Build.tool && Build.tool.key && sidesOf(Build.tool.key)) { Build.side++; Build.fpKey = ""; return true; }
  if (k === "b") { $("build").classList.toggle("hidden"); return true; }
  return false;
}

// --- messages --------------------------------------------------------------------------------------
function toast(text, bad) {
  const el = document.createElement("div");
  el.className = "msg" + (bad ? " bad" : "");
  el.textContent = text;
  const box = $("msgs");
  box.prepend(el);
  while (box.children.length > 6) box.lastChild.remove();
  setTimeout(() => el.classList.add("old"), 6000);
}

async function newCity() {
  Loading.start();
  try { await fetch("/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ new: true }) }); }
  catch (e) { Loading.end(); return toast("server unreachable", true); }
  resetPlayback();
  toast("new empty city: the scripted run was stopped");
}
