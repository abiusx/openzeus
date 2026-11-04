// Play mode: gods and priests (sim/gods; docs/play/gods.md). Roles from data/play/gods.json (tools/play_gods.py)
// merged over walkers.json: role "god" picks "god_<name>" by the walker's good (the god's name); its atlas
// (Zeus_Zeus .. Poseidon_Atlas, viewer/play/atlas from tools/play_atlas.py) loads when that god is on the map.
// Appear / vanish / attack / cast play as "work" looks (sim gods.figures.look): one frame per the block's
// ticks_per_frame (rate-100 groups, data/gods.json frame_ticks; bug 393), 0x0B vanish and the duel one a tick.
// Bolts (role god_bolt, an "arrow" look): scene.js drawArrow takes the god's picture from Gods.bolt (gods.json bolts).
// Followers (role entranced, good = the walker's own role; Dionysus' satyrs: zeus_satyr, loaded on demand).
"use strict";

const Gods = (() => {
  let busy = false, bolts = null, snd = null;

  async function init() {
    const WM = MAP.walkers && MAP.walkers.roles;
    if (!WM) return;
    try {
      const G = await getJSON("/data/play/gods.json");
      for (const [k, v] of Object.entries(G.roles || {})) WM[k] = v;
      bolts = G.bolts || null;
      snd = G.sounds || null;
    } catch (e) { }
  }

  async function want(files) {                      // god sprite files load on demand
    if (busy || !files.size) return;
    busy = true;
    try { await loadAtlases(R, [...files]); } catch (e) { } finally { busy = false; }
  }

  function scene() {
    const WM = MAP.walkers && MAP.walkers.roles, f = P.f0;
    if (!WM || !f || !f.walkers) return;
    const files = new Set();
    for (const w of f.walkers) {
      if (w[3] !== "god" && !(w[3] === "entranced" && w[4] === "satyr")) continue;
      const r = w[3] === "god" ? WM[`god_${w[4]}`] : WM.follower_satyr;
      if (r && r.file && !atlas[r.file]) files.add(r.file);
    }
    want(files);
    sounds();
  }

  // the god's sounds (gods.json sounds, FUN_004DC180 -> FUN_005A6FE0 group 0x2E + .., only on screen, panned): a god
  // "work" look carries its sound kind at [10] (sim gods.look: mat appear, demat vanish, sanctify bless / help,
  // curse); played once when the look starts in the ticks drawn since the last frame
  let soundTick = null;
  const heard = new Set();
  function sounds() {
    const t = Math.floor(P.t), from = soundTick;
    soundTick = t;
    if (typeof audio === "undefined" || !audio || audio.muted || !snd || from == null || t <= from || t - from > 60) return;
    for (const f of [P.f0, P.f1]) if (f) for (const w of f.walkers) {
      const L = w[7];
      if (w[3] !== "god" || !L || L[0] !== "work" || !L[10] || !(L[1] > from && L[1] <= t)) continue;
      const key = w[0] + ":" + L[1] + ":" + L[10];
      if (heard.has(key)) continue;
      heard.add(key);
      if (heard.size > 500) heard.clear();
      const gi = (MAP.walkers.roles.god.map ? Object.keys(MAP.walkers.roles.god.map).indexOf(w[4]) : -1);
      const row = snd[gi], file = row && row[L[10]];
      const sx = (tileX(w[1], w[2]) + 29 - cam.x) * cam.zoom, sy = (tileY(w[1], w[2]) + 15 - cam.y) * cam.zoom;
      if (!file || sx < 0 || sy < 0 || sx > innerWidth || sy > innerHeight) continue;
      audio.sfxAt(file, sx / innerWidth * 2 - 1);
    }
    figureSounds(from, t);
  }

  // the sim's figure sounds (frame "sfx", sim walkers.sfx: [tick, id, x, y, role, god, kind, until]): "miss" a god's
  // bolt that hit nothing (G_miss, FUN_004DC180(god, 13)), "hit" a god hit and alive (FUN_004DB7A0: G_<god>_hit),
  // "atk" a god walking into a fight (FUN_004DB3D0(god, 0): atk1 / atk2 at random), "charm" Aphrodite's / Dionysus'
  // entrancing walk until `until` (god_entrance_roam_tick calls FUN_004DB3D0(god, 0) every tick; the sound layer
  // refuses a sample still playing: sound_play_sample 0x005C80B0); on screen only, panned
  const loops = new Map(), playing = new Map();
  function playOnce(key, file, pan) {
    const now = audio.ctx ? audio.ctx.currentTime : 0;
    if ((playing.get(key) || 0) > now) return;
    playing.set(key, now + 30);                       // pending until the buffer is known
    audio.play(file, audio.sfx, pan).then(src => {
      playing.set(key, src && src.buffer ? audio.ctx.currentTime + src.buffer.duration : 0);
    });
  }
  function screenPan(x, y) {
    const sx = (tileX(x, y) + 29 - cam.x) * cam.zoom, sy = (tileY(x, y) + 15 - cam.y) * cam.zoom;
    return (sx < 0 || sy < 0 || sx > innerWidth || sy > innerHeight) ? null : sx / innerWidth * 2 - 1;
  }
  function figureSounds(from, t) {
    for (const f of [P.f0, P.f1]) if (f && f.sfx) for (const e of f.sfx) {
      const [tick, id, x, y, , god, kind, until] = e;
      if (!(tick > from && tick <= t)) continue;
      const key = "s:" + id + ":" + tick + ":" + kind;
      if (heard.has(key)) continue;
      heard.add(key);
      if (heard.size > 500) heard.clear();
      const row = snd[god];
      if (!row) continue;
      if (kind === "charm") { loops.set(id, { god, until }); continue; }
      const file = kind === "miss" ? row.miss : kind === "hit" ? row.hit
        : kind === "atk" && row.atk ? row.atk[Math.floor(Math.random() * 2)] : null;
      const pan = screenPan(x, y);
      if (file && pan !== null) audio.sfxAt(file, pan);
    }
    for (const [id, L] of loops) {
      const w = P.f1 && P.f1.walkers.find(w => w[0] === id);
      if (!w || t > L.until) { loops.delete(id); continue; }
      const row = snd[L.god], pan = screenPan(w[1], w[2]);
      if (!row || !row.atk || pan === null) continue;
      const k = Math.floor(Math.random() * 2);
      playOnce(id + ":" + k, row.atk[k], pan);
    }
  }

  // the bolt picture of god i (0x2D / 0x34 by the god's resource): {file, start, frames, dirs}
  function bolt(i) { return bolts && bolts[i]; }

  return { init, scene, bolt };
})();

window.Gods = Gods;
