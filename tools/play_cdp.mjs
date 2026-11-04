// Headless Chrome driver for play-mode checks (docs/play/draw-order.md "Check").
// Starts its own Chrome (temporary profile, --mute-audio, never the user's browser) and talks to it over the
// DevTools protocol with Node's built-in WebSocket (Node >= 22). No npm packages.
//
//   import { launch } from "./play_cdp.mjs";
//   const b = await launch({ width: 1280, height: 800, dpr: 1.25 });
//   await b.open("http://127.0.0.1:8797/play.html");
//   const v = await b.eval("1 + 1");
//   await b.shot("/tmp/a.png");
//   await b.close();
//
// CLI: node tools/play_cdp.mjs URL OUT.png [--wait MS] [--eval JS] [--dpr 1.25] [--size 1280x800]
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const sleep = ms => new Promise(r => setTimeout(r, ms));

// Chromes still open when the script ends early (a timeout, Ctrl-C, an uncaught error) are killed on the way
// out, so no headless Chrome outlives its script (10-30: orphans held ~1 GB of GPU memory each).
const LIVE = new Set();
function killAll() {
  for (const { proc, prof } of LIVE) {
    try { proc.kill("SIGKILL"); } catch (e) { }
    try { rmSync(prof, { recursive: true, force: true }); } catch (e) { }
  }
  LIVE.clear();
}
process.on("exit", killAll);
for (const [sig, n] of [["SIGINT", 2], ["SIGTERM", 15], ["SIGHUP", 1]]) process.on(sig, () => { killAll(); process.exit(128 + n); });
process.on("uncaughtException", e => { killAll(); console.error(e); process.exit(1); });
process.on("unhandledRejection", e => { killAll(); console.error(e); process.exit(1); });

// leader: the leader name put in the fresh profile's localStorage before play.html runs ("N", the oracle runs' player),
// so play mode skips its first-open front end (newgame.js boot); null = none stored (the front end shows)
export async function launch({ width = 1280, height = 800, dpr = 1.25, port = 9300 + Math.floor(Math.random() * 500), leader = "N" } = {}) {
  const prof = mkdtempSync(join(tmpdir(), "zeus-cdp-"));
  const proc = spawn(CHROME, [
    "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${prof}`, "--mute-audio",
    "--no-first-run", "--no-default-browser-check", "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding", "--use-angle=metal", "--enable-webgl", "--ignore-gpu-blocklist",
    `--window-size=${width},${height}`, "about:blank"], { stdio: "ignore" });
  LIVE.add({ proc, prof });
  let ver = null;
  for (let i = 0; i < 100 && !ver; i++) {
    try { ver = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(); } catch (e) { await sleep(100); }
  }
  if (!ver) { proc.kill(); throw new Error("chrome did not start"); }
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = tabs.find(t => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let id = 0;
  const pending = new Map(), logs = [];
  let b = null;
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
    else if (m.method === "Runtime.consoleAPICalled") logs.push(m.params.args.map(a => a.value ?? a.description).join(" "));
    else if (m.method === "Runtime.exceptionThrown") logs.push("EXC " + (m.params.exceptionDetails.exception || {}).description);
    if (m.method && b && b.onEvent) b.onEvent(m);   // other DevTools events (Network.*: tools/comms_check.mjs)
  };
  const send = (method, params = {}) => new Promise((res, rej) => { const k = ++id; pending.set(k, { res, rej }); ws.send(JSON.stringify({ id: k, method, params })); });
  await send("Runtime.enable");
  await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: dpr, mobile: false });
  if (leader != null) await send("Page.addScriptToEvaluateOnNewDocument", { source:
    `try { if (!localStorage.getItem("zeus-leader")) localStorage.setItem("zeus-leader", ${JSON.stringify(leader)}); } catch (e) { }` });
  b = {
    send, logs, pid: proc.pid,                    // Chrome's own pid (its GPU process is a child: tools/gpu_check.mjs)
    async open(url, waitMs = 0) { await send("Page.navigate", { url }); if (waitMs) await sleep(waitMs); },
    async eval(expr, awaitPromise = true) {
      const r = await send("Runtime.evaluate", { expression: expr, awaitPromise, returnByValue: true });
      if (r.exceptionDetails) throw new Error("eval: " + (r.exceptionDetails.exception ? r.exceptionDetails.exception.description : r.exceptionDetails.text));
      return r.result.value;
    },
    async waitFor(expr, ms = 60000) {
      const t0 = Date.now();
      while (Date.now() - t0 < ms) { try { if (await b.eval(expr)) return true; } catch (e) { } await sleep(250); }
      throw new Error("timeout waiting for " + expr);
    },
    async shot(path) {
      const r = await send("Page.captureScreenshot", { format: "png" });
      writeFileSync(path, Buffer.from(r.data, "base64"));
    },
    send,                                         // raw DevTools call, e.g. send("Emulation.setCPUThrottlingRate", { rate: 6 })
    async close() {
      try { ws.close(); } catch (e) { }
      proc.kill(); await sleep(300); rmSync(prof, { recursive: true, force: true });
      for (const c of LIVE) if (c.proc === proc) LIVE.delete(c);
    },
  };
  return b;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
  const [w, h] = opt("--size", "1280x800").split("x").map(Number);
  const b = await launch({ width: w, height: h, dpr: +opt("--dpr", 1.25) });
  try {
    await b.open(a[0], +opt("--wait", 8000));
    if (opt("--eval")) console.log(JSON.stringify(await b.eval(opt("--eval"))));
    if (a[1] && !a[1].startsWith("--")) await b.shot(a[1]);
  } finally { await b.close(); }
}
