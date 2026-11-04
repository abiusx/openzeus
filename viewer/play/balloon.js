// Balloon help ("mouse help", Options > Help > Balloon help): FUN_004F6110 picks a text every frame, FUN_004F6BA0
// draws it (docs/play/options.md "Balloon help"). Widgets register their rect and text index (group 68) while they
// are drawn (Balloon.add); a screen without balloons clears the list (Balloon.none). Static texts need the ON level
// and 150 ms on targets (the timer restarts only on a frame with no target); "at once" texts show at SOME or ON.
"use strict";

const Balloon = (() => {
  let targets = [], since = 0, advisor = 0;
  function begin() { targets = []; advisor = 0; }
  // group: the text group (FUN_004F6B60: 68 in the city and windows, 44 on the world map 0x14); text: a string
  // instead of group:index (the exe's own tip boxes, e.g. kind 4 FUN_0051C800)
  function add(x, y, w, h, index, atOnce = false, group = 68) { targets.push([x, y, w, h, index, atOnce, group]); }
  // the Military page's company tips (FUN_004F6110 page 8 -> kind 4, FUN_0051C800): a string, at once
  function addTip(x, y, w, h, text) { targets.push([x, y, w, h, text, true, 0, 4]); }
  function none() { targets = []; }
  function onAdvisor(a) { advisor = a; }           // screen 7: the box's own placement (FUN_004F6BA0)

  function draw() {
    const level = window.Options ? Options.balloon() : 2, now = performance.now();
    if (window.Options && !Options.ready()) Options.load();   // the texts (options.json): balloons are ON from the start
    const [mx, my] = UIX.mouse;
    let hit = null;
    for (let i = targets.length - 1; i >= 0 && !hit; i--) {
      const q = targets[i];
      if (mx >= q[0] && my >= q[1] && mx < q[0] + q[2] && my < q[1] + q[3]) hit = q;
    }
    if (!hit || level === 0 || !window.Options || !Options.ready()) { since = now; return; }
    if (hit[5]) since = now;                         // dynamic texts: the timer restarts, shown at once
    else if (level !== 2 || now - since < 150) { if (level !== 2) since = now; return; }
    const text = typeof hit[4] === "string" ? hit[4] : Options.text(hit[6], hit[4]);
    if (!text) return;
    if (hit[7] === 4) {                              // FUN_0051C800: 150 x 20 at mouse+20 (x < 170, else mouse-170),
      const x = mx < 170 ? mx + 20 : mx - 170, y = my < 200 ? my + 10 : my - 32;   // mouse+10 (y < 200, else -32)
      uiPut(UIX.tipEdge, x, y, 1, 150, 20);
      uiPut(UIX.tipFill, x + 1, y + 1, 1, 148, 18);
      ZText.panel((sp, px, py) => UIX.batch.push(sp, px, py), "SPR_FONTS_9DKBU", text, x + 5, y + 5, 130);
      return;
    }
    // box: w 200 (text 180), more than 2 lines: 300 (280); (w+20) x (lines*16+10); x = mouse+20 if the mouse is left
    // of ox+100+w, else mouse-w-20; y = mouse+40 above oy+200, else mouse-62. Advisors (screen 7): x = mouse+50 on
    // the left; y = oy+432, or above it mouse - 74 (labor 1) / 54 (trade 6) / 58 (population 7) / 64 (others)
    let w = 200, n = ZText.panelLines("SPR_FONTS_9DKBU", text, w - 20).length;
    if (n > 2) { w = 300; n = ZText.panelLines("SPR_FONTS_9DKBU", text, w - 20).length; }
    const ox = Math.trunc((UIX.W - 640) / 2), oy = Math.trunc((UIX.H - 480) / 2), h = 16 * n + 10;
    let x = mx < ox + 100 + w ? mx + 20 : mx - w - 20, y = my < oy + 200 ? my + 40 : my - 62;
    if (advisor) {
      if (mx < ox + 100 + w) x = mx + 50;
      y = oy + 432;
      if (my < y) y = my - ({ 1: 74, 6: 54, 7: 58 }[advisor] || 64);
    }
    uiPut(UIX.tipEdge, x, y, 1, w + 20, h);
    uiPut(UIX.tipFill, x + 1, y + 1, 1, w + 18, h - 2);
    ZText.panel((sp, px, py) => UIX.batch.push(sp, px, py), "SPR_FONTS_9DKBU", text, x + 5, y + 7, w - 20);
  }
  return { begin, add, addTip, none, onAdvisor, draw };
})();
window.Balloon = Balloon;
