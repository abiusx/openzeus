// Offers (sim/empire/offers.py): gifts, tribute, granted requests, plunder and defensive aid wait for the player's
// answer in the event-message window (msgwin.js, button set A: Accept / Postpone / Decline, as
// incoming_goods_dialog 0x004745E0). state.json "offers" lists the open ones; a new one (or one whose text or buttons
// changed, i.e. offered again) opens the window once while the city screen is idle, like message_queue_poll
// 0x00521D30; the buttons send `offer ID accept|postpone|decline`. Closing the window unanswered leaves the offer
// open (the sim offers it again next month). The Options > Messages category decides as in the exe (sim side,
// `msglevel`), so a non-Full category never reaches here with buttons.
"use strict";

const Offers = (() => {
  const shown = new Set();
  let wait = 0;
  const key = (o) => `${o.id}|${o.tick}|${o.accept}${o.postpone}${o.decline}`;
  async function answer(o, what) {
    if (typeof sendCommands === "function") await sendCommands([`offer ${o.id} ${what}`], { sound: false });
  }
  function open(o) {
    shown.add(key(o));
    const b = {};
    for (const k of ["accept", "postpone", "decline"]) if (o[k]) b[k] = () => answer(o, k);
    // ours, when the window closes itself (msgwin.js, bugs.md 326): tribute, and a gift / granted request / plunder
    // that fits whole (no Postpone button), are accepted (the exe also accepts tribute by itself, offers.py _auto); a
    // debt rescue (costs attitude), troops and partial room stay unanswered: offered again next month, no postpone used
    const take = o.accept && (o.kind === "tribute" || (["gift", "granted", "plunder"].includes(o.kind) && !o.postpone));
    MsgWin.open({ title: o.title, body: o.body, type: 0, tick: o.tick, buttons: b, onTimeout: take ? () => answer(o, "accept") : null });
  }
  setInterval(() => {
    const list = (typeof S !== "undefined" && S && S.offers) || null;
    if (!list || !window.MsgWin) return;
    const busy = MsgWin.isOpen() || (window.Help && Help.isOpen()) || (window.Lists && Lists.isOpen())
      || (window.Advisors && Advisors.isOpen()) || (window.WorldMap && WorldMap.holdsPopups())
      || (window.Options && Options.isOpen && Options.isOpen()) || (typeof UIX !== "undefined" && UIX.info);
    if (busy) { wait = 5; return; }
    if (wait > 0) { wait--; return; }
    const o = list.find(q => !shown.has(key(q)));
    if (o) open(o);
  }, 100);
  return { open, pending: () => ((typeof S !== "undefined" && S && S.offers) || []) };
})();
window.Offers = Offers;
