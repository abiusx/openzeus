"""An open-play adventure episode (.pak) -> data/scenario/<map>.json: its scheduled events, god block and scenario
block, as the exe loads them at the episode start (docs/logic/events.md "Where the events come from", "Data file").

    python3 tools/build_scenario.py            writes data/scenario/sandbox.json and sandbox2.json
    python3 tools/build_scenario.py --check    rebuilds in memory and compares with the files

Inputs (zeus-original, GOG 2.1.0.10): Adventures/}Open Play Sandbox.pak (episode 1) for `sandbox`,
Adventures/Open Play Sandbox 2/Open Play Sandbox 2.pak (episode 1) for `sandbox2`. The file layout and the record
decoding are tools/scenario_events.py's (SET_LAYOUT; refs/zeus-poseidon-arm64/formats/set.md).

What the loader does to the records before the game sees them (applied here, so the data file is what the game
plays; `raw` keeps the file bytes):
- adventure_read 0x00425D00 fix-ups by .set version: v < 25: requests (type 1) of kind 7 get item 24 (troops);
  v < 26: byte +0x7A of quests (type 4) is zeroed.
- event_goods_remap 0x0050F3C0 (from goods_remap_all 0x0050F7E0, maps older than version 303): the item group
  +0x04 of types that carry a good (event_has_goods_item 0x00468DA0: table 0x00632700 + type*20, byte +0x13) is
  renumbered from the old (pre-Poseidon) goods to the new ones, and the choice list compacted (a range a<0, b..c
  turns into the choice b|c). Hypothesis (events.md): the remap runs after the episode copy (a 5000-drachma
  reward is item 19 = old drachmas; new 19 = sculpture). The same table renumbers byte +0x70 (`b70`) of records
  with flags & 0x4000 (none in the shipped open-play episodes).
The value groups are NOT resolved here: the sim resolves them at the game start (event_resolve_at_start
0x00467660, with its own RNG), as the exe does.
"""
import hashlib
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import scenario_events as se  # noqa: E402

ADV = os.path.join(ROOT, "zeus-original", "app", "Adventures")
MAPS = {"sandbox": ("}Open Play Sandbox.pak", 0), "sandbox2": ("Open Play Sandbox 2/Open Play Sandbox 2.pak", 0)}
OUT = os.path.join(ROOT, "data", "scenario")
# event_has_goods_item 0x00468DA0: byte +0x13 of the 20-byte type table at 0x00632700 (read from Zeus.exe)
HAS_GOODS = {1, 4, 13, 14, 15, 16, 21, 22, 23, 29, 30, 32, 33}
# event_goods_remap 0x0050F3C0: old goods number -> new (0 = not in the table: the item becomes 0, a/b/c keep theirs)
REMAP = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 9, 9: 10, 10: 11, 11: 12, 12: 13, 13: 14, 14: 15, 15: 18,
         16: 19, 17: 20, 18: 21, 19: 23, 20: 24, 21: 25, 22: 26, 23: 27}
GROUPS = {"item": 0x04, "amount": 0x0C, "year": 0x14, "city": 0x1C, "city2": 0x58}


def i16(b, o):
    return struct.unpack_from("<h", b, o)[0]


def remap_item(grp):
    """event_goods_remap on the group [value, a, b, c] (ported as is, incl. the compaction)."""
    v = REMAP.get(grp[0], 0)
    L = [REMAP.get(x, 0) or x for x in grp[1:]]          # 0 -> the original value is kept (negatives stay)
    u6, u5 = L[0], L[2]
    path = "53a"
    if L[0] < 0:
        if L[1] < 0:
            if L[2] >= 0:
                u5, u6 = -1, L[2]
        else:
            u4, u8, u6 = L[2], -1, L[1]
            path = "53f"
    if path == "53a":
        u8, u4 = L[1], u5
        if L[1] < 0:
            path = "53f"
    if path == "53f":
        u5 = u4
        if u4 >= 0:
            u5, u8 = -1, u4
    return [v, u6, u8, u5]


def record(r, ver, remap=True):
    """remap=False: no goods renumbering (adventure_read 0x00425D00 remaps only .set versions < 22 (FUN_00425260);
    the open-play files are v5)."""
    r = bytearray(r)
    t = r[2]
    if ver < 25 and t == 1 and r[0x60] == 7:
        struct.pack_into("<4h", r, 0x04, 24, 24, -1, -1)  # sic: the fix-up sets item 24; hypothesis: the whole group
    if ver < 26 and t == 4:
        r[0x7A] = 0
    groups = {k: [i16(r, o + 2 * j) for j in range(4)] for k, o in GROUPS.items()}
    if t in HAS_GOODS and remap:
        groups["item"] = remap_item(groups["item"])
    flags = struct.unpack_from("<I", r, 0x28)[0]
    # the same remap of byte +0x70 when flags & 0x4000 (default 0); not ported: +0x66 (the parent's item, set at
    # run time; 0 in the files) and +0x74 by FUN_00512610 (the gift's food, run time)
    b70 = REMAP.get(r[0x70], 0) if flags & 0x4000 and remap else r[0x70]
    return dict(type=t, name=se.TYPE[t], month=r[3], flags=flags, chain=i16(r, 0x24), lead=i16(r, 0x2C),
                groups=groups, b36=i16(r, 0x36), b38=i16(r, 0x38), b3a=i16(r, 0x3A), b3c=i16(r, 0x3C),
                b3e=i16(r, 0x3E), kind=r[0x60], b70=b70, quest=r[0x7A], raw=bytes(r).hex())


def gods(blk):
    slots = list(struct.unpack_from("<24i", blk, 0))
    return dict(slots=slots, names=[se.GOD[s] if 0 <= s < 14 else None for s in slots],
                independent_monster=struct.unpack_from("<i", blk, 0x60)[0],
                jealous=[bool(blk[0xC4 + i]) for i in range(24)], max_sanctuaries=blk[0xDC], raw=bytes(blk).hex())


def build(name):
    rel, ep = MAPS[name]
    path = os.path.join(ADV, rel)
    d = open(path, "rb").read()
    ver = struct.unpack_from("<I", d, 4)[0]
    L = se.SET_LAYOUT[ver]
    n = struct.unpack_from("<14i", d, L["counts"])[ep]
    base = L["events"] + ep * 18600
    evs = [record(d[base + i * 124: base + (i + 1) * 124], ver) for i in range(n)]
    for i, e in enumerate(evs):
        e["index"] = i
    sc = d[0x1BE4 + ep * 0x7F0:][:0x7F0]
    return {
        "_doc": "Built by tools/build_scenario.py (docs/logic/events.md 'Data file'); do not edit by hand. Groups are "
                "[value, a, b, c] as in the file (resolved by the sim at the start); items in the new goods numbering.",
        "source": os.path.relpath(path, ROOT), "sha256": hashlib.sha256(d).hexdigest(), "episode": ep + 1,
        "set_version": ver,
        "scenario": dict(start_year=i16(sc, 0), funds=struct.unpack_from("<i", sc, 0x20)[0], raw=sc.hex()),
        "gods": gods(d[L["gods"] + ep * L["god_size"]:][:L["god_size"]]),
        "events": evs,
    }


def dump(obj):
    head = {k: v for k, v in obj.items() if k != "events"}
    rows = ",\n".join("  " + json.dumps({"index": e["index"], **{k: v for k, v in e.items() if k != "index"}})
                      for e in obj["events"])
    s = json.dumps(head, indent=1)[:-2] + ',\n "events": [\n' + rows + "\n ]\n}\n"
    json.loads(s)
    return s


def main():
    check = "--check" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    bad = 0
    for name in MAPS:
        s = dump(build(name))
        p = os.path.join(OUT, f"{name}.json")
        if check:
            same = os.path.exists(p) and open(p).read() == s
            bad += not same
            print(f"{os.path.relpath(p, ROOT)}: {'same' if same else 'DIFFERS'}")
        else:
            open(p, "w").write(s)
            print(f"{os.path.relpath(p, ROOT)}: {len(json.loads(s)['events'])} events")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
