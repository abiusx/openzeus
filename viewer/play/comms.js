// Play mode's client/server protocol 2 (docs/play/comms.md; server side sim/comms.py): rebuilds whole frames,
// building snapshots and terrain from deltas. Pure functions, no page state (also loaded by tools/comms_check.mjs).
// A rebuilt document equals the server's full one; records that did not change are the same objects as in the base
// (the page never changes frame or snapshot records in place).
"use strict";
const Comms = (() => {
  const PROTO = 2;
  // the server's keys of a document: the page adds its own caches to some (play.js buildTerrain: T.altMap), which
  // a delta must not carry over to the next version
  const KEYS = Symbol("server keys");
  function mark(doc) {
    if (doc && typeof doc === "object" && !doc[KEYS]) Object.defineProperty(doc, KEYS, { value: Object.keys(doc) });
    return doc;
  }

  function keyOf(e, key) { return e[key]; }

  // the list `prev` with a keyed delta {up, rm, order} applied (records keyed by e[key]: 0 for list records, "id")
  function applyKeyed(prev, kd, key) {
    const idx = new Map();
    for (const e of prev) idx.set(keyOf(e, key), e);
    if (kd.rm) for (const k of kd.rm) idx.delete(k);
    const added = [];
    if (kd.up) for (const u of kd.up) {
      const k = keyOf(u, key), p = idx.get(k);
      if (p === undefined) { added.push(k); idx.set(k, u); }
      else if (Array.isArray(u) || typeof key !== "string") idx.set(k, u);
      else {                                       // dict record: changed fields, "_x" = gone fields
        const o = Object.assign({}, p, u);
        if (u._x) { for (const f of u._x) delete o[f]; delete o._x; }
        idx.set(k, o);
      }
    }
    let order = kd.order;
    if (!order) {
      order = [];
      for (const e of prev) { const k = keyOf(e, key); if (idx.has(k)) order.push(k); }
      for (const k of added) order.push(k);
    }
    const out = new Array(order.length);
    for (let i = 0; i < order.length; i++) {
      const e = idx.get(order[i]);
      if (e === undefined) throw new Error("comms: no record " + order[i]);
      out[i] = e;
    }
    return out;
  }

  // document `base` with delta d applied (d._b must be base's id: checked by the caller, who knows the id's field)
  function apply(base, d, keyed) {
    const o = {};
    for (const k of base[KEYS] || Object.keys(base)) o[k] = base[k];
    if (d.del) for (const k of d.del) delete o[k];
    if (d.set) Object.assign(o, d.set);
    if (d.keyed) for (const k in d.keyed) o[k] = applyKeyed(base[k] || [], d.keyed[k], keyed[k]);
    if (d.sub) for (const k in d.sub) {
      const v = o[k] = Object.assign({}, base[k], d.sub[k].set);
      if (d.sub[k].del) for (const x of d.sub[k].del) delete v[x];
    }
    if (d.ix) for (const k in d.ix) {
      const a = o[k] = base[k].slice(), x = d.ix[k];
      for (let i = 0; i < x.length; i += 2) a[x[i]] = x[i + 1];
    }
    return mark(o);
  }

  const FRAME_KEYED = { walkers: 0, houses: 0 }, STATE_KEYED = { buildings: "id", walkers: "id" };

  // frames.json?v=2 "frames": full frames and deltas ("_b" = the previous frame's fs). base: the frame the first
  // delta builds on (the newest the page holds) or null. Returns {frames: whole frames in order}; throws when a
  // delta's base is not the frame before it (the caller then asks again without a base).
  function decodeFrames(base, list) {
    const out = [];
    let prev = base;
    for (const f of list) {
      if (f._b === undefined) { prev = mark(f); out.push(f); continue; }
      if (!prev || prev.fs !== f._b) throw new Error(`comms: frame delta on ${f._b}, have ${prev ? prev.fs : "none"}`);
      prev = apply(prev, f, FRAME_KEYED);
      out.push(prev);
    }
    return { frames: out };
  }

  // state.json?lite=1&v=2 answer: a full snapshot, or {deltas: [...]} chained from S (d._b = the seq it builds on)
  function applyState(S, r) {
    if (!r.deltas) return { state: mark(r), deltas: 0 };
    let s = S;
    for (const d of r.deltas) {
      if (!s || s.seq !== d._b) throw new Error(`comms: state delta on ${d._b}, have ${s ? s.seq : "none"}`);
      s = apply(s, d, STATE_KEYED);
    }
    return { state: s, deltas: r.deltas.length };
  }

  // terrain.json?v=2 answer: a full terrain, or a delta on T (d._b = T.tid, the server's terrain serial)
  function applyTerrain(T, r) {
    if (r._b === undefined) return mark(r);
    if (!T || T.tid !== r._b) throw new Error(`comms: terrain delta on ${r._b}, have ${T ? T.tid : "none"}`);
    return apply(T, r, {});
  }

  return { PROTO, mark, apply, applyKeyed, decodeFrames, applyState, applyTerrain };
})();
if (typeof module !== "undefined") module.exports = Comms;
