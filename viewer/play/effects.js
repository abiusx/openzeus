// Effect figures (the exe's figure type 6) as pictures: docs/play/walkers.md "Effect figures".
// The sim reports a spawner call in the frame's `fx` ([tick, kind, x, y, size], sim/effects.py); the exe makes the
// figures only on screen and with its own RNG, so play mode makes them here, with Math.random, and animates them by
// the effect handler FUN_00410E50 (data/play/walkers.json `effects`, tools/play_effects.py).
// "debris" = collapse_debris_spawn 0x004CCD40: size 1 -> for each corner of the tile (0,0) (1,0) (1,1) (0,1) (sign
// -1 / +1 per axis) and each of the directions (0,1) (1,0) (1,1) (tables 0x00639110 / 0x00639118) one dust figure,
// dest = tile + sign * dir * (rng & 3), +0x59 = (rng & 3) + 1 (its line-move speed and ticks per frame), +0x15C =
// rng % 5 (the group); size > 1: each tile of the area with rng & 3 == 0 gets the size-1 spawn, none -> one random
// tile. 9 frames; it dies at counter >= 9 * ticks. Movement: figure_line_move(fig, +0x59) towards dest (15 sub-steps
// a tile); ours moves +0x59 sub-steps a tick (hypothesis: the line mover's step table is not read).
// The disasters' post step (sim/disasters post_step, bugs.md 362): "lava" (subtype 1) and "spray" (subtype 4) stand
// at a fine spot of their tile, height 10; "drops" (subtype 2) drift from the middle, height 4. Drawn line_counter =
// height / 8 + 30 px up (walker_draw's line-move branch): debris at 30, so these 10 / 4 px above it.
(function () {
  const parts = [];
  const seen = new Set();
  const rnd = () => Math.floor(Math.random() * 32768);
  const CORNERS = [[0, 0], [1, 0], [1, 1], [0, 1]], DIRS = [[0, 1], [1, 0], [1, 1]];

  function debris1(t0, x0, y0, size = 1) {
    for (const [cx, cy] of CORNERS) {
      const sx = cx ? 1 : -1, sy = cy ? 1 : -1;
      const x = x0 + (cx ? size - 1 : 0), y = y0 + (cy ? size - 1 : 0);   // corner (size - 1): size 0 (a ship hit) -1
      for (const [dx, dy] of DIRS) {
        const r = rnd() & 3;
        const tpf = (rnd() & 3) + 1, group = rnd() % 5;
        parts.push({ kind: "debris", t0, x, y, tx: x + sx * dx * r, ty: y + sy * dy * r, tpf, group });
      }
    }
  }
  // FUN_00410430: the exe's sin / cos tables (256 steps, x 256, truncated); subtype 2 drifts by them (FUN_004106A0)
  const SIN = [], COS = [];
  for (let k = 0; k < 256; k++) { SIN.push(Math.trunc(Math.sin(k * 0.02454369260546875) * 256)); COS.push(Math.trunc(Math.cos(k * 0.02454369260546875) * 256)); }
  const MAX = 750;                                   // FUN_004104D0 makes none while 0x2EE effects live
  // FUN_004104D0 makes an effect only when its tile's spot is within 200 px of the view (table 0x005D8448: no subtype
  // 0..11 has flag 4, margins 200 x 200), and FUN_004106A0 deletes one that left it (every 16 ticks, by serial): so
  // the 750 cap counts the ones on screen.
  function onScreen(x, y) {
    if (typeof cam === "undefined" || typeof UIX === "undefined" || !UIX.panelX) return true;
    const [, cx, cy] = Scene.figureSpot(x, y, {});
    const w = (UIX.panelX * UIX.scale) / cam.zoom, h = innerHeight / cam.zoom;
    return cx >= cam.x - 200 && cy >= cam.y - 200 && cx <= cam.x + w + 200 && cy <= cam.y + h + 200;
  }
  function spawn(e) {
    const [t0, kind, x, y, size] = e;
    if (parts.length >= MAX || !onScreen(x, y)) return;
    if (kind === "lava" || kind === "spray") {         // standing, fine spot (of 15), height 10 (sim/effects.splash)
      parts.push({ kind, t0, x: x + e[4] / 15, y: y + e[5] / 15, v: e[6], still: true, rise: 10 });
      return;
    }
    if (kind === "drops") {                            // subtype 2: from the middle (fine 8), height 4, polar drift
      const a = e[4], sp = e[5];
      const vx = Math.trunc((COS[a] + SIN[a]) * sp / 32), vy = Math.trunc((COS[a] - SIN[a]) * sp / 32);
      parts.push({ kind, t0, x: x + 64 / 120, y: y + 64 / 120, vx: vx / 120, vy: vy / 120, v: e[6], rise: 4 });
      return;
    }
    if (kind !== "debris") return;
    if (size < 2) return debris1(t0, x, y, size);
    let n = 0;
    for (let j = 0; j < size; j++) for (let i = 0; i < size; i++) if ((rnd() & 3) === 0) { debris1(t0, x + i, y + j); n++; }
    if (!n) debris1(t0, x + rnd() % size, y + rnd() % size);
  }
  function collect() {
    const frames = [P.f0, P.f1].concat((typeof FRAMES !== "undefined" && FRAMES) || []);
    const t = P.t || 0;
    for (const f of frames) if (f && f.fx && f.fx.length) for (const e of f.fx) {
      if (e[0] > t + 1 || e[0] < t - 40) continue;   // made when the shown time reaches it (frames run ahead)
      const key = e.join(":");
      if (seen.has(key)) continue;
      seen.add(key);
      if (seen.size > 5000) seen.clear();
      spawn(e);
    }
  }
  function scene(out) {
    const E = MAP.walkers && MAP.walkers.effects;
    if (!E || !T) return;
    const t = P.t || 0;
    for (let i = parts.length - 1; i >= 0; i--) {     // the dead first: their slots count against the cap
      const p = parts[i], e = E[p.kind];
      const life = !e ? 0 : p.kind === "debris" ? e.frames * p.tpf : Array.isArray(e.frames) ? e.frames[p.v] : e.frames;
      if (t - p.t0 >= life) parts.splice(i, 1);
    }
    collect();
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i], age = t - p.t0;
      const e = E[p.kind];
      if (!e || ((p.t0 & 15) === (Math.floor(t) & 15) && !onScreen(p.x, p.y))) { parts.splice(i, 1); continue; }
      if (p.kind !== "debris") {                       // FUN_00410E50: counter + 1 a tick before the picture
        const frames = Array.isArray(e.frames) ? e.frames[p.v] : e.frames;
        if (age >= frames || age < -60) { parts.splice(i, 1); continue; }
        if (age < 1) continue;                         // made in the post step, first drawn after its update
        const c = Math.floor(age);                     // the effect's counter (whole ticks)
        let grp, fr = c;
        if (p.kind === "spray") { grp = e.groups[c < 10 ? 0 : 1]; fr = c % 10; }
        else grp = e.groups[p.v];
        const fx = p.still ? p.x : p.x + p.vx * c, fy = p.still ? p.y : p.y + p.vy * c;
        const sp = sprite(e.file, grp + fr);
        if (!sp) continue;
        const [d, cx, cy] = Scene.figureSpot(fx, fy, {}, 10 - p.rise);   // line_counter = height / 8 + 30
        out.push([d, fx, sp, cx - sp.ax, cy - sp.ay]);
        continue;
      }
      const life = e.frames * p.tpf;
      if (age >= life || age < -60) { parts.splice(i, 1); continue; }
      if (age < 0) continue;
      const dx = p.tx - p.x, dy = p.ty - p.y, len = Math.max(Math.abs(dx), Math.abs(dy));
      const k = len ? Math.min(1, age * p.tpf / 15 / len) : 0;
      const fx = p.x + dx * k, fy = p.y + dy * k;
      const sp = sprite(e.file, e.groups[p.group] + Math.floor(age / p.tpf));
      if (!sp) continue;
      const [d, cx, cy] = Scene.figureSpot(fx, fy, {});
      out.push([d, fx, sp, cx - sp.ax, cy - sp.ay]);       // at the tile's elevation, as a walker (bugs.md 362)
    }
  }
  window.Effects = { scene, spawn, parts };
})();
