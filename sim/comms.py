"""Deltas between two versions of a JSON document for play mode's client/server protocol (docs/play/comms.md,
protocol 2): walker frames, building snapshots and terrain. Presentation transport only, no game rules; the client
side is viewer/play/comms.js.

A delta turns the base document into the new one exactly (the client checks "_b" against the base it holds):
  {"_b": base id,                       # the base's frame serial (fs) / snapshot seq / terrain map_version
   "set": {key: value},                 # top-level keys that are new or changed (whole values)
   "del": [key],                        # top-level keys that are gone
   "keyed": {key: {"up": [...],         # lists of records with a unique id: new records whole, changed list
                   "rm": [id],          #   records whole, changed dict records as {id, changed fields,
                   "order": [id]}},     #   "_x": [gone fields]}; "order" only when the ids' order is not the
                                        #   base order minus "rm" plus the new ids in their order
   "ix": {key: [i, v, i, v, ...]},      # equal-length lists of scalars (terrain grids): the changed indices
   "sub": {key: {"set": {k: v}, "del": [k]}}}   # dict values (snapshots: city, reports, ...): changed entries

Documents are compared as JSON text (each record, each top-level value), never as Python objects: the game
changes some exported objects in place, and Python's == takes True for 1. encode() serializes a document in parts
(join() of them is byte-identical to json.dumps of the whole), delta() compares two encodings.
"""
import json

FRAME_KEYED = {"walkers": 0, "houses": 0}          # live.record_frame: [id, ...] per walker / house
STATE_KEYED = {"buildings": "id", "walkers": "id"}  # export.snapshot: dicts with "id"
TERRAIN_GRIDS = ("ids", "draw", "elev", "flags", "road", "des")   # live.terrain: one int per tile


def dumps(obj):
    return json.dumps(obj, default=int, separators=(",", ":")).encode()


def encode(obj, keyed=None, grids=(), sub=False):
    """{key: bytes | ("K", ids, [record bytes]) | ("G", list of ints) | ("D", {key: bytes})} for a dict document
    (sub: dict values with string keys in parts too)."""
    parts = {}
    for k, v in obj.items():
        if keyed and k in keyed and isinstance(v, list):
            key = keyed[k]
            try:
                ids = [int(e[key]) for e in v]
            except (TypeError, KeyError, IndexError, ValueError):
                ids = None
            if ids is not None and len(set(ids)) == len(ids):
                parts[k] = ("K", ids, [dumps(e) for e in v])
                continue
        if k in grids and isinstance(v, list):
            parts[k] = ("G", v)
            continue
        if sub and isinstance(v, dict) and all(type(x) is str for x in v):
            parts[k] = ("D", {x: dumps(y) for x, y in v.items()})
            continue
        parts[k] = dumps(v)
    return parts


def _value(p):
    if isinstance(p, bytes):
        return p
    if p[0] == "D":
        return b"{" + b",".join(dumps(k) + b":" + v for k, v in p[1].items()) + b"}"
    return b"[" + b",".join(p[2]) + b"]" if p[0] == "K" else dumps(p[1])


def join(parts):
    """The document's JSON (identical to dumps of the dict encode() was given)."""
    return b"{" + b",".join(dumps(k) + b":" + _value(p) for k, p in parts.items()) + b"}"


def _keyed(q, p, key):
    _, ia, ra = q
    _, ib, rb = p
    pa = dict(zip(ia, ra))
    up = []
    for k, r in zip(ib, rb):
        pr = pa.get(k)
        if pr is None:
            up.append(r)
        elif pr != r:
            if isinstance(key, str):              # dict records: the changed fields only
                A, B = json.loads(pr), json.loads(r)
                fields = [dumps(key) + b":" + dumps(k)]
                for f, v in B.items():
                    if f != key:
                        vb = dumps(v)
                        if f not in A or dumps(A[f]) != vb:
                            fields.append(dumps(f) + b":" + vb)
                gone = [f for f in A if f not in B]
                if gone:
                    fields.append(b'"_x":' + dumps(gone))
                up.append(b"{" + b",".join(fields) + b"}")
            else:
                up.append(r)
    sb = set(ib)
    rm = [k for k in ia if k not in sb]
    out = []
    if up:
        out.append(b'"up":[' + b",".join(up) + b"]")
    if rm:
        out.append(b'"rm":' + dumps(rm))
    rms = set(rm)
    if [k for k in ia if k not in rms] + [k for k in ib if k not in pa] != ib:
        out.append(b'"order":' + dumps(ib))
    return b"{" + b",".join(out) + b"}"


def delta(prev, cur, base, keyed=None):
    """The delta (JSON bytes) turning encoding prev into encoding cur; base = prev's id."""
    st, kd, ix, sb = [], [], [], []
    for k, p in cur.items():
        q = prev.get(k)
        if q is None:
            st.append(dumps(k) + b":" + _value(p))
        elif isinstance(p, tuple) and isinstance(q, tuple) and p[0] == q[0] == "K":
            if p[1] != q[1] or p[2] != q[2]:
                kd.append(dumps(k) + b":" + _keyed(q, p, keyed[k]))
        elif isinstance(p, tuple) and isinstance(q, tuple) and p[0] == q[0] == "G" and len(p[1]) == len(q[1]):
            if p[1] != q[1]:
                ix.append(dumps(k) + b":" + dumps([x for i, (u, w) in enumerate(zip(q[1], p[1])) if u != w for x in (i, w)]))
        elif isinstance(p, tuple) and isinstance(q, tuple) and p[0] == q[0] == "D":
            if p[1] != q[1]:
                ch = [dumps(x) + b":" + y for x, y in p[1].items() if q[1].get(x) != y]
                gone = [x for x in q[1] if x not in p[1]]
                sb.append(dumps(k) + b":{" + b",".join(
                    ([b'"set":{' + b",".join(ch) + b"}"] if ch else []) + ([b'"del":' + dumps(gone)] if gone else [])) + b"}")
        else:
            v = _value(p)
            if v != _value(q):
                st.append(dumps(k) + b":" + v)
    out = [b'"_b":' + dumps(base)]
    if st:
        out.append(b'"set":{' + b",".join(st) + b"}")
    gone = [k for k in prev if k not in cur]
    if gone:
        out.append(b'"del":' + dumps(gone))
    if kd:
        out.append(b'"keyed":{' + b",".join(kd) + b"}")
    if ix:
        out.append(b'"ix":{' + b",".join(ix) + b"}")
    if sb:
        out.append(b'"sub":{' + b",".join(sb) + b"}")
    return b"{" + b",".join(out) + b"}"
