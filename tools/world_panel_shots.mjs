// World map side panel vs the exe (bugs.md 204; compare: tools/world_panel_compare.py). Captures the panel
// (186 x 600 UI px at one device px per UI px: dpr 1.25, UI 80 % sharp) for each city of the oracle run
// re/oracle/runs/worldmap (a new sandbox game: Olympia, Tiryns, ...), selected as in the exe shots.
// Usage (your own server on a NEW sandbox game, not a game in play):
//   python3 -m sim live /tmp/new-sandbox.pkl --port 8824 --speed 0 &     (the file must not exist: a new game)
//   node tools/world_panel_shots.mjs http://127.0.0.1:8824/play.html OUTDIR
import { launch } from "./play_cdp.mjs";
import { mkdirSync } from "node:fs";

const [URL_, OUT] = process.argv.slice(2);
if (!URL_ || !OUT) { console.error("usage: node tools/world_panel_shots.mjs URL OUTDIR"); process.exit(2); }
mkdirSync(OUT, { recursive: true });
const SHOTS = { wm_player: "Olympia", wm_ally2: "Tiryns", wm_ally4: "Aulis", wm_rival3: "Sparta", wm_rival5: "Delos",
                       wm_vassal6: "Miletos", wm_colony: "Elis", wm_distant7: "Thasus" };
const b = await launch({ width: 1024, height: 800, dpr: 1.25 });
try {
  await b.open(URL_);
  await b.waitFor("typeof UIX !== 'undefined' && UIX.D && window.WorldMap && typeof S !== 'undefined' && S && S.buildings && window.ZText", 180000);
  await b.eval("document.body.classList.remove('dev'); uiSetSize(80, true); WorldMap.isOpen() || WorldMap.toggle(); true");
  await b.waitFor("WorldMap.conf && WorldMap.data && WorldMap.data.cities");
  await new Promise(r => setTimeout(r, 1500));
  const lay = await b.eval("({ scale: UIX.scale, W: UIX.W, panelX: UIX.panelX })");
  if (Math.abs(lay.scale * 1.25 - 1) > 1e-6) throw new Error("UI scale is not one device px per UI px: " + JSON.stringify(lay));
  for (const [shot, name] of Object.entries(SHOTS)) {
    const ok = await b.eval(`(() => { const c = WorldMap.data.cities.find(c => c.name === ${JSON.stringify(name)}); if (!c) return false; WorldMap.select(c.id); UIX.mouse = [-1, -1]; return true; })()`);
    if (!ok) { console.log(shot, name, "missing"); continue; }
    await new Promise(r => setTimeout(r, 300));
    const r = await b.send("Page.captureScreenshot", { format: "png" });   // the whole window; the compare crops the panel (right 186 px)
    const { writeFileSync } = await import("node:fs");
    writeFileSync(`${OUT}/${shot}.png`, Buffer.from(r.data, "base64"));
    console.log(shot, name, "ok");
  }
} finally { await b.close(); }
