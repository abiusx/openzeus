// Drag-box selection and company groups in play mode (docs/play/military.md "The exe's military screens",
// FUN_00433380 .. FUN_00433B60). Headless muted Chrome (tools/play_cdp.mjs) on your own server with a COPY of the
// military test save (docs/play/military.md "Test scenario"):
//   python3 -m sim run scripts/military.txt --save /tmp/mil.pkl; cp /tmp/mil.pkl /tmp/mil-play.pkl
//   python3 -m sim live /tmp/mil-play.pkl --port 8792 --speed 30 &
//   node tools/milbox_check.mjs http://127.0.0.1:8792/play.html [OUT.png]
// Mobilizes companies A and B next to each other, opens screen 0x48 on A, drags a box over both soldiers
// (real mouse events), checks both are selected and the box was drawn white (gl.readPixels at dpr 1.25), stores
// the selection in group 1 (Ctrl+1), selects A alone, recalls group 1 (Alt+1). Prints PASS/FAIL lines.
import { launch } from "./play_cdp.mjs";

const [URL_, SHOT] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
let fails = 0;
const check = (ok, what) => { console.log((ok ? "PASS " : "FAIL ") + what); if (!ok) fails++; };
try {
  await b.open(URL_);
  await b.waitFor("typeof UIX !== 'undefined' && UIX.D && typeof S !== 'undefined' && S && P.f0 && window.Military && Military.data", 180000);
  const comps = await b.eval(`Military.data.companies.filter(c => !c.away && c.members > 0 && c.home).map(c => [c.slot, c.home])`);
  const [[A, ha], [B]] = [comps[0], comps[1]];
  const X = ha[0] - 12, Y = ha[1] + 1;
  await b.eval(`sendCommands(["mobilize ${A} ${X} ${Y}", "mobilize ${B} ${X + 4} ${Y}"], { sound: false }); true`);
  await b.waitFor(`Military.refresh(), Military.data.companies.filter(c => [${A},${B}].includes(c.slot)).every(c => c.on_map >= 8 && c.status === Military.data.companies.find(d => d.slot === c.slot).status) && Scene.walkerHits().length > 0`, 60000);
  await sleep(35000);                                  // the soldiers walk to the spot (speed 30: ~750 ticks)
  await b.eval(`for (let i = 0; i < 9 && window.MsgWin && MsgWin.isOpen(); i++) MsgWin.close(); MilPanel.select(${A}); true`);
  await b.eval(`(() => { const s = tileX(${X + 2}, ${Y}), t = tileY(${X + 2}, ${Y}); cam.x = s - 400 / cam.zoom; cam.y = t - 350 / cam.zoom; })(); true`);
  await sleep(1500);
  // the soldiers' screen spots (CSS px) -> a box around both companies
  const pts = await b.eval(`(() => { const d = Military.data, ids = new Set(d.companies.filter(c => [${A},${B}].includes(c.slot)).flatMap(c => c.ids));
    return Scene.walkerHits().filter(h => ids.has(h[0]) && Math.abs(h[6] - ${X + 2}) + Math.abs(h[7] - ${Y}) < 8).map(h => [(h[1] + h[3] / 2 - cam.x) * cam.zoom, (h[2] + h[4] / 2 - cam.y) * cam.zoom]); })()`);
  check(pts.length >= 6, `soldiers of ${A} and ${B} on screen: ${pts.length}`);
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const x0 = Math.min(...xs) - 50, y0 = Math.min(...ys) - 40, x1 = Math.max(...xs) + 50, y1 = Math.max(...ys) + 40;
  const M = (type, x, y, extra = {}) => b.send("Input.dispatchMouseEvent", { type, x, y, button: "left", buttons: type === "mouseReleased" ? 0 : 1, clickCount: 1, ...extra });
  await M("mouseMoved", x0, y0); await M("mousePressed", x0, y0);
  for (let k = 1; k <= 8; k++) { await M("mouseMoved", x0 + (x1 - x0) * k / 8, y0 + (y1 - y0) * k / 8); await sleep(60); }
  await sleep(400);
  console.log(`box from (${x0|0},${y0|0}) to (${x1|0},${y1|0}) CSS px: ${JSON.stringify(await b.eval("({ r: MilPanel.boxRect(), dui: downInUI, drag })"))}`);
  const px = await b.eval(`new Promise(res => {          // read back right after the next frame's uiDraw
    const orig = window.uiDraw;
    window.uiDraw = function (R) {
      orig(R);
      window.uiDraw = orig;
      const r = MilPanel.boxRect();
      if (!r) return res(null);
      const gl = R.gl, s = UIX.scale * devicePixelRatio, H = gl.drawingBufferHeight, p = new Uint8Array(4), out = [];
      for (const [x, y] of [[r[0], (r[1] + r[3]) / 2], [(r[0] + r[2]) / 2, r[1]], [r[2], (r[1] + r[3]) / 2], [(r[0] + r[2]) / 2, r[3]]]) {
        gl.readPixels(Math.round(Math.round(x) * s), H - 1 - Math.round(Math.round(y) * s), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, p);
        out.push([...p].slice(0, 3));
      }
      res({ r: r.map(Math.round), s, out });
    };
  })`);
  check(px && px.out.every(c => c[0] > 240 && c[1] > 240 && c[2] > 240), `box edges white (readPixels left/top/right/bottom): ${JSON.stringify(px)}`);
  if (SHOT) await b.shot(SHOT);
  await M("mouseReleased", x1, y1);
  await sleep(500);
  let sel = await b.eval(`MilPanel.selection`);
  check(sel.includes(A) && sel.includes(B) && (await b.eval(`MilPanel.mode()`)) === 0x48, `box selects ${A} and ${B}: [${sel}]`);
  const key = (mod, down = true) => b.send("Input.dispatchKeyEvent", { type: down ? "keyDown" : "keyUp", key: "1", code: "Digit1", windowsVirtualKeyCode: 49, modifiers: mod });
  await key(2); await key(2, false);                    // Ctrl+1: store
  await b.eval(`MilPanel.select(${A}); true`);
  sel = await b.eval(`MilPanel.selection`);
  check(sel.length === 1 && sel[0] === A, `click selects ${A} alone: [${sel}]`);
  await b.eval(`MilPanel.close(); true`);
  await key(1); await key(1, false);                    // Alt+1: recall (from the city screen)
  sel = await b.eval(`MilPanel.selection`);
  check(sel.includes(A) && sel.includes(B) && (await b.eval(`MilPanel.mode()`)) === 0x48, `Alt+1 recalls [${sel}]`);
  const errs = b.logs.filter(l => /EXC|rror/.test(l));
  check(!errs.length, `no page errors ${errs.slice(0, 3).join(" | ")}`);
  await b.eval(`sendCommands(["return ${A}", "return ${B}"], { sound: false }); true`).catch(() => 0);
} finally {
  await b.close();
}
process.exit(fails ? 1 : 0);
