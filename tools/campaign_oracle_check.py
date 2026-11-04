"""Compare an episode's start state in an oracle dump with data/campaign/<id>.json (tools/build_campaign.py).

    python3 tools/campaign_oracle_check.py ID SLOT DUMP      e.g. housing 0 re/oracle/runs/tutorial/dump/tick_000000.bin

Checked (docs/campaign-format.md "Oracle checks"): the live scenario block 0x00902928 fields episode_start_load
0x00420390 writes (start year +0, funds +0x20 for a new city, +0x288, +0x328, allowed +0x408, the episode record
+0x644 without its run-time name/flag bytes), the event count 0x009173F0 and each event's type/month/flags/groups'
a,b,c (the values are rolled at the start), the god block 0x00FFA450, the player city (g_cities 0x008FBAC0, kind 0):
resources +0xA8, buy +0xBC / sell +0xC4 lists, +0x60, wealth/military/attitude, the tutorial switches 0x00FEAE06[11] /
0x00FE6A5A. The goals (0x00FE2768) are not in the dumps: compare the briefing screenshot by eye.
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from oracle import Dump  # noqa: E402
import build_empire  # noqa: E402

GOODS = build_empire.GOODS


def main(cid, slot, path):
    a = json.load(open(os.path.join(ROOT, "data", "campaign", f"{cid}.json")))
    ep = next(e for e in a["episodes"] if e["slot"] == int(slot))
    d = Dump(path)
    sc = d.block(9)
    bad = []

    def eq(name, ours, exe):
        ok = ours == exe
        print(f"{'ok ' if ok else 'BAD'} {name}: ours {ours} exe {exe}" if not ok or not isinstance(ours, list)
              else f"ok  {name} ({len(ours)} values)")
        if not ok:
            bad.append(name)

    i16 = lambda b, o: struct.unpack_from("<h", b, o)[0]   # noqa: E731
    i32 = lambda b, o: struct.unpack_from("<i", b, o)[0]   # noqa: E731
    if ep["start"] == "new_city":
        eq("start year", ep["start_year"], i16(sc, 0))
        eq("funds (scenario, before difficulty)", ep["funds"], i32(sc, 0x20))
    print(f"    treasury now {d.at(0x00FE6A64, '<i')} (difficulty-adjusted), year {d.at(0x0091EC04, '<i')} "
          f"month {d.at(0x0091EC08, '<i')}")
    if ep["poseidon"] is None:
        print(f"    poseidon flag +0x288: not in the file (stale object value), exe {i16(sc, 0x288)}")
    else:
        eq("poseidon flag +0x288", ep["poseidon"], i16(sc, 0x288))
    eq("games year +0x328", ep["games_year"], i16(sc, 0x328))
    eq("allowed +0x408", ep["allowed_raw"], list(struct.unpack_from("<100h", sc, 0x408)))
    rec = sc[0x644:0x644 + 356]
    r = ep["record"]
    eq("record intro/victory/map", [(ep["intro"] or {}).get("id", i32(rec, 8)), (ep["victory"] or {}).get("id", i32(rec, 0x14)),
                                    r["map"]], [i32(rec, 8), i32(rec, 0x14), i32(rec, 0xC)])
    eq("record +0x18..+0x4F", r["b18"], list(struct.unpack_from("<14i", rec, 0x18)))
    print(f"    record name (run time) {rec[0x5D:].split(bytes(1))[0]!r}, +0x58 kind {i32(rec, 0x58)}, +0x54 next {i32(rec, 0x54)}")
    n = d.at(0x009173F0, "<i")
    eq("event count", len(ep["events"]), n)
    evb = d.block(13)
    for e in ep["events"][:n]:
        x = evb[124 * e["index"]:124 * (e["index"] + 1)]
        exe = [x[2], x[3], i16(x, 0x24), [i16(x, 0x04 + 2 * k) for k in (1, 2, 3)], [i16(x, 0x0C + 2 * k) for k in (1, 2, 3)],
               [i16(x, 0x14 + 2 * k) for k in (1, 2, 3)], [i16(x, 0x1C + 2 * k) for k in (1, 2, 3)]]
        m = e["month"]
        if ep["start"] != "new_city" and not e["flags"] & 0x20001:   # FUN_00467930: rebased on the current month
            m += d.at(0x0091EC08, "<i")
            m = m - 11 if m > 11 else m                              # sic: -11 (and year +1, not compared here)
        ours = [e["type"], m, e["chain"], e["groups"]["item"][1:], e["groups"]["amount"][1:],
                e["groups"]["year"][1:], e["groups"]["city"][1:]]
        if ours != exe:
            eq(f"event {e['index']}", ours, exe)
    print(f"ok  events: {n} compared (type, month, chain, item/amount/year/city choices)" if not any(
        b.startswith("event ") for b in bad) else "")
    gods = bytes.fromhex(ep["gods"]["raw"])
    g = d.block(122)
    eq("gods +0x00..+0xDC (slots, monster, b64, jealous, max sanct)", gods[:0xDD].hex(), g[:0xDD].hex())
    eq("gods monument count +0xE0", ep["gods"]["monument_count"], i32(g, 0xE0))
    cities = d.block(7)
    pc = next(i for i in range(22) if cities[0x23C * i] and cities[0x23C * i + 2] == 0)
    c = cities[0x23C * pc:0x23C * (pc + 1)]
    pcd = ep["player_city"]
    eq("player city resources +0xA8", pcd["resources"], [GOODS.get(x) for x in c[0xA8:0xBC] if x])
    if "buys" in pcd:   # not for a colony start (kind 1 writes only the resources)
        eq("player city buys +0xBC", pcd["buys"], [GOODS.get(x) for x in c[0xBC:0xC0] if x])
        eq("player city sells +0xC4", pcd["sells"], [GOODS.get(x) for x in c[0xC4:0xC8] if x])
        eq("player city +0x60", pcd["table_60"], {GOODS[k]: c[0x60 + k] for k in range(1, 23) if c[0x60 + k]})
    if pcd.get("wealth") is not None:
        eq("player city wealth/military/attitude", [pcd["wealth"], pcd["military"], pcd["attitude"]],
           [i32(c, 0xD8), i32(c, 0xDC), i32(c, 0x164)])
    tut = ep["tutorial"] or dict(build_categories=[1] * 11, world_map_button=1)
    eq("build categories 0x00FEAE06", tut["build_categories"], [d.at(0x00FEAE06 + k, "<B") for k in range(11)])
    eq("world map button 0x00FE6A5A", tut["world_map_button"], d.at(0x00FE6A5A, "<B"))
    print(f"{len(bad)} differences" + (f": {bad}" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(*sys.argv[1:]))
