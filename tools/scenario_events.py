"""Scheduled events and god slots of a Zeus adventure (.pak / .set) or map (.map), decoded (docs/logic/events.md).

    python3 tools/scenario_events.py list FILE...        events + gods of each episode/colony (+ the map's own block 16)
    python3 tools/scenario_events.py openplay            list for every open-play adventure the game ships
    python3 tools/scenario_events.py oracle RUN_DIR      what an oracle run did with them, month by month (dumps)
    python3 tools/scenario_events.py oracle-script       prints re/oracle/scenarios/open-play-events.txt
    python3 tools/scenario_events.py oracle-events RUN   per record: when its year/state/active/flags changed (dumps)
    python3 tools/scenario_events.py ours MAP YEARS [SEED]   the same in our sim (sim/scenario): a new game on MAP,
                                                         nothing built, YEARS years; the engine's log + record changes

Where the data lives (refs/zeus-poseidon-arm64/formats/set.md, pak.md; GOG Zeus.exe addresses):
- A .pak starts with a .set header (adventure object). At an episode start `FUN_00420390` (from `FUN_004214f0`)
  copies the episode's 150 x 124-byte event records (object +0x9C00 + ep*18600, `FUN_0042b710`) over `g_events`
  (0x009173F4), sets `g_events_count` from +0xC366C[ep] (`FUN_0042b760`), resolves each record (`FUN_00467660`),
  and copies the episode's god block (object +0x8B98 + ep*300, `FUN_0042b4d0`) into `g_scenario_gods`
  (0x00FFA450). Colonies are ep 10..13 (+0x37290 events, +0xC3694 counts).
  The map's own block 16 (0x009173F0: count + 150 records) is therefore NOT what the game plays.
- File offsets differ by .set version: v5 (all open-play files) has 224-byte god blocks and events at 0x97D8.
- Value groups (4 x i16: value, a, b, c), resolved at start by `FUN_004673c0`: a >= 0 and b < 0 -> a;
  a >= 0, b >= 0 -> one of a, b (, c if >= 0) at random; a < 0 -> random in [b, c]
  (quirk: a < 0 and b == c >= 0 -> value = a). Groups: +0x04 item/subject, +0x0C amount, +0x14 year offset,
  +0x1C city/point, +0x58 second city.
Text: event type names = text group 156, gods 157, monsters 190, heroes 185, city status 35.
"""
import glob
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import oracle  # noqa: E402
import mapfile  # noqa: E402

ADV = os.path.join(ROOT, "zeus-original", "app", "Adventures")
OPEN_PLAY = ["}Open Play Sandbox.pak", "Open Play Sandbox 2/Open Play Sandbox 2.pak",
             "}Open Play Economic.pak", "Open Play Economic 2/Open Play Economic 2.pak",
             "}Open Play Military.pak", "Open Play Military 2/Open Play Military 2.pak"]
T = json.load(open(os.path.join(ROOT, "extracted", "text", "zeus_text.json")))
TYPE = T["156"] + [""] * 20
for i, n in {0x1D: "tribute in (internal)", 0x1E: "tribute out (internal)", 0x1F: "relationship letter (internal)",
             0x20: "granted delivery (internal)", 0x21: "refused demand (internal)", 0x22: "ally strike (internal)",
             0x23: "games begin (internal, games.md)", 0x24: "games: cannot participate (internal)",
             0x25: "games conclude (internal)", 0x26: "internal 0x26 (FUN_00481A30)",
             0x27: "hero arrival (internal)"}.items():
    TYPE[i] = n
GOD = T["157"][:14]
MONSTER = T["190"][:18] if "190" in T else [str(i) for i in range(18)]
HERO = T["185"][:8]
STATUS = T["35"]
# old (pre-Poseidon, map version < 303) goods numbers, as `goods_remap_all` 0x0050F7E0 / `FUN_0050F3C0` renumber
# them at load; event items 19..: 19 drachmas, 20 troops?, ... (world-map.md 9: new 23 drachmas, 24 troops, 25 food)
OLD_GOODS = {1: "urchin", 2: "fish", 3: "meat", 4: "cheese", 5: "carrots", 6: "onions", 7: "wheat", 8: "wood",
             9: "bronze", 10: "marble", 11: "grapes", 12: "olives", 13: "fleece", 14: "horses", 15: "armor",
             16: "sculpture", 17: "olive oil", 18: "wine", 19: "drachmas", 20: "troops", 21: "food"}
SET_LAYOUT = {5: dict(events=0x97D8, counts=0xC3241, gods=0x8B98, god_size=224),
              26: dict(events=0x9C00, counts=0xC3669, gods=0x8B98, god_size=300)}


def i16(b, o):
    return struct.unpack_from("<h", b, o)[0]


def group(r, o):
    """The value group at +o as written by the editor: 'v', 'a|b|c' (choice) or 'b..c' (range)."""
    a, b, c = i16(r, o + 2), i16(r, o + 4), i16(r, o + 6)
    if a >= 0:
        return str(a) if b < 0 else "|".join(str(x) for x in (a, b, c) if x >= 0)
    if b >= 0 and b == c:
        return f"{a} (quirk: b == c)"
    return f"{b}..{c}"


def goods(r, o):
    a, b, c = i16(r, o + 2), i16(r, o + 4), i16(r, o + 6)
    if a < 0:
        return group(r, o)
    return "|".join(OLD_GOODS.get(x, str(x)) for x in (a, b, c) if x >= 0) if b >= 0 else OLD_GOODS.get(a, str(a))


def describe(r):
    """One record (as stored in the file, before resolution) -> dict of the fields that matter for its type."""
    t, flags = r[2], struct.unpack_from("<I", r, 0x28)[0]
    d = dict(type=t, name=TYPE[t], month=r[3] + 1, year="+" + group(r, 0x14), flags=hex(flags))
    if flags & 1:
        d["template"] = "only fired by a chain (flags & 1: skipped by scenario_events_monthly 0x0046D380)"
    if i16(r, 0x24) >= 0:
        d["then"] = f"event #{i16(r, 0x24)}"
    if t == 4:      # quest, FUN_00482820
        g = r[0x60]
        d.update(god=GOD[g] if g < 14 else g, quest=r[0x7A], hero_of_monster_slot=r[0x36], statue_variant=i16(r, 0x38),
                 note="v<26 files: quest byte +0x7A forced to 0 by the loader 0x00425D00")
    elif t == 23:   # gift, event_gift 0x00474A80
        d.update(item=goods(r, 0x04), amount=group(r, 0x0C), city=group(r, 0x1C))
    elif t == 26:   # monster invasion, monster_event_update 0x00481430
        d.update(monster_slot=group(r, 0x04), lead_months=i16(r, 0x2C),
                 targets=[r[0x38], r[0x3A], r[0x3C]], aggressiveness=r[0x3E], god_sent_text=r[0x60])
    elif t == 27:   # god invasion, event_god_attack 0x00482B10
        d.update(god="|".join(GOD[int(x)] for x in group(r, 0x04).split("|")) if ".." not in group(r, 0x04)
                 else group(r, 0x04), warn=bool(flags & 0x40))
    elif t == 2:    # invasion, invasion_event_month 0x00476E20
        d.update(invader_city=group(r, 0x58), strength_pct=group(r, 0x0C), entry_point=group(r, 0x1C),
                 lead_months=i16(r, 0x2C))
    elif t == 1:    # request, event_request
        d.update(kind=r[0x60], item=goods(r, 0x04), amount=group(r, 0x0C), city=group(r, 0x1C),
                 deadline_months=i16(r, 0x2C))
    elif t == 19:   # city status change, event_city_status_change 0x00473680
        d.update(change=STATUS[r[0x60]] if r[0x60] < len(STATUS) else r[0x60], city=group(r, 0x1C),
                 amount=group(r, 0x0C))
    elif t in (13, 14, 15, 16, 21, 22):
        d.update(item=goods(r, 0x04), amount=group(r, 0x0C), city=group(r, 0x1C))
    else:
        d.update(subject=group(r, 0x04), amount=group(r, 0x0C), city=group(r, 0x1C))
    return d


def gods(blk):
    slot = struct.unpack_from("<24i", blk, 0)
    name = lambda s: [GOD[slot[i]] for i in s if slot[i] >= 0]  # noqa: E731
    indep = struct.unpack_from("<i", blk, 0x60)[0]
    return {"unfriendly 0..3 (0,1 bring their monster)": name(range(0, 4)), "unfriendly 4..11": name(range(4, 12)),
            "friendly 12..17": name(range(12, 18)), "friendly 18..23": name(range(18, 24)),
            "may be jealous": [GOD[slot[i]] for i in range(24) if blk[0xC4 + i] and slot[i] >= 0],
            "independent monster (slot 2)": MONSTER[indep] if 0 <= indep < 18 else indep,
            "max sanctuaries +0xDC": blk[0xDC]}


def read_set(d):
    ver = struct.unpack_from("<I", d, 4)[0]
    L = SET_LAYOUT[ver]
    out = dict(version=ver, episodes=struct.unpack_from("<i", d, 8)[0], colonies=struct.unpack_from("<i", d, 0x10)[0],
               kind=d[0x49108 if ver == 5 else 0x49530], parts=[])
    counts = struct.unpack_from("<14i", d, L["counts"])
    for ep in range(14):
        n = counts[ep]
        if not n and ep:
            continue
        base = L["events"] + ep * 18600
        part = dict(part=f"episode {ep + 1}" if ep < 10 else f"colony {ep - 9}", events=[])
        for i in range(n):
            part["events"].append(describe(d[base + i * 124: base + (i + 1) * 124]))
        if ep < 10:
            part["gods"] = gods(d[L["gods"] + ep * L["god_size"]:][:L["god_size"]])
        out["parts"].append(part)
    return out


def map_events(path):
    out = []
    for m, (hdr, blocks) in enumerate(mapfile.read_file(path)):
        b = [x for x in blocks if x["rank"] == 16][0]["data"]
        n = struct.unpack_from("<i", b, 0)[0]
        out.append([describe(b[4 + i * 124: 4 + (i + 1) * 124]) for i in range(n)])
    return out


def show(path):
    d = open(path, "rb").read()
    print(f"== {os.path.relpath(path, ROOT)}")
    if d[:4] == struct.pack("<I", 0x22A7):
        s = read_set(d)
        print(f"  .set v{s['version']}, kind {s['kind']}, episodes {s['episodes']}, colonies {s['colonies']}")
        for p in s["parts"]:
            print(f"  -- {p['part']}: {len(p['events'])} events")
            for i, e in enumerate(p["events"]):
                print(f"    #{i:2d} " + ", ".join(f"{k}={v}" for k, v in e.items()))
            if "gods" in p:
                for k, v in p["gods"].items():
                    print(f"    gods {k}: {v}")
    else:
        for m, evs in enumerate(map_events(path)):
            print(f"  -- map container {m}, block 16 (editor copy; replaced at episode start): {len(evs)} events")
            for i, e in enumerate(evs):
                print(f"    #{i:2d} " + ", ".join(f"{k}={v}" for k, v in e.items()))


# ---- oracle dumps -------------------------------------------------------------------------------------------
def oracle(run):
    from oracle import Dump
    files = oracle.dump_files(os.path.join(run, "dump"))
    last = None
    for f in files:
        D = Dump(f)
        year, month = D.at(0x0091EC04), D.at(0x0091EC08)
        g = D.block(120)                       # g_gods 0x00EF5DD8, 14 x 52
        figs = D.block(28)                     # g_figures 0x00DBD788, 2000 x 0x184
        ev = D.block(13)
        n = D.at(0x009173F0)
        jc = D.at(0x00FE6A58 + 1, "<B")
        on = []
        for k in range(1, 2000):
            fr = figs[k * 0x184:(k + 1) * 0x184]
            if fr[0x0E] and fr[0x0A] in (0x43, 0x44, 0x45):
                kind = {0x43: "god", 0x44: "monster", 0x45: "hero"}[fr[0x0A]]
                who = fr[0x0B]
                if kind == "god":
                    who = next((GOD[i] for i in range(14) if struct.unpack_from("<i", g, i * 52 + 0x18)[0] == k), "?")
                elif kind == "monster":
                    who = MONSTER[who] if who < 18 else who
                else:
                    who = HERO[who] if who < 8 else who
                on.append(f"{kind} {who} (fig {k})")
        attack = [GOD[i] for i in range(14) if struct.unpack_from("<i", g, i * 52 + 0x24)[0] >= 0]
        evs = []
        for i in range(n):
            r = ev[i * 124:(i + 1) * 124]
            if r[2] >= 0x1D and i16(r, 0x30) == 10:
                continue                       # finished internal events (tribute in, ...)
            evs.append(f"#{i} {r[2]} {TYPE[r[2]]} y{i16(r, 0x14)} m{r[3] + 1} st{i16(r, 0x30)} act{r[0x32]} "
                       f"fl{struct.unpack_from('<I', r, 0x28)[0]:#x}")
        line = (f"year {year} month {month + 1}: jealousy countdown {jc}; attacking gods {attack}; on map {on}; "
                f"events {evs}")
        tick = os.path.basename(f)[5:11]
        if line != last:
            print(f"tick {tick}: {line}")
        last = line


def oracle_script():
    head = ("5:key 27; 12:click 220,101; 17:char 78; 20:click 556,320; 27:click 590,256; 31:click 120,306; "
            "33:click 315,442; 38:click 656,491; 46:rclick 300,300")
    acts = [(float(t), f"{t}:rclick 300,300") for t in range(60, 44000, 20)]
    acts += [(float(t), f"{t}:shot DIR/t{t}.bmp") for t in range(4000, 44001, 4000)]
    acts.sort(key=lambda a: a[0])
    print('# Track 1A (docs/logic/events.md "Oracle check"): Open Play Sandbox (}Open Play Sandbox.pak, as sandbox-start.txt,\n'
          "# difficulty Mortal), nothing built, ~19.5 game years (190 000 ticks, 7 min) with a right click every 20 s (closes message popups) and a\n"
          "# screenshot every 4000 s. Generated by: python3 tools/scenario_events.py oracle-script > this file.\n"
          "# Run: ZEUS_STATE_DUMP_EVERY=816 --seconds 44010 (one dump per game month); read with tools/scenario_events.py oracle DIR.")
    print("; ".join([head] + [a for _, a in acts]))


def _changes(rows):
    """rows: [(label, {record index: (type, year, month, state, active, flags)})] -> one line per change."""
    last = {}
    for label, recs in rows:
        for i, r in sorted(recs.items()):
            if last.get(i) != r:
                t, y, m, st, act, fl = r
                print(f"{label}: #{i} {TYPE[t]} date y+{y} m{m + 1} state {st} active {act} flags {fl:#x}")
                last[i] = r


def oracle_events(run):
    """The scheduled records of an oracle run, printed when they change (internal types 0x1D.. left out)."""
    from oracle import Dump
    rows = []
    for f in oracle.dump_files(os.path.join(run, "dump")):
        D = Dump(f)
        year, month, n = D.at(0x0091EC04), D.at(0x0091EC08), D.at(0x009173F0)
        ev = D.block(13)
        recs = {}
        for i in range(n):
            r = ev[i * 124:(i + 1) * 124]
            if r[2] < 0x1D:
                recs[i] = (r[2], i16(r, 0x14), r[3], i16(r, 0x30), r[0x32], struct.unpack_from("<I", r, 0x28)[0])
        rows.append((f"dump {abs(year)} {'BC' if year < 0 else 'AD'} month {month + 1}", recs))
    _changes(rows)


def ours(map_name, years, seed=1):
    """A new game in our sim, nothing built: the records' changes month by month and the engine's log."""
    sys.path.insert(0, ROOT)
    from sim.game import Game, MONTHS
    g = Game(map_name, seed=seed)
    tpm = g.rules["ticks_per_day"] * g.rules["days_per_month"]
    rows = []
    y0 = g.start_year
    for _ in range(years * 12 + 1):
        recs = {e["id"]: (e["type"], e["year"], e["month"], e["state"], e["active"], e["flags"])
                for e in (g.scenario.events if g.scenario else [])}
        y = g.year
        rows.append((f"ours {abs(y)} {'BC' if y < 0 else 'AD'} month {g.month + 1}", recs))
        g.step(tpm)
    _changes(rows)
    for m, t in (g.scenario.log if g.scenario else []):
        y = y0 + m // 12
        print(f"log {MONTHS[m % 12]} {abs(y)} {'BC' if y < 0 else 'AD'}: {t}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "list":
        for p in a[1:]:
            show(p)
    elif a[0] == "openplay":
        for p in OPEN_PLAY:
            show(os.path.join(ADV, p))
        show(os.path.join(ADV, "Open Play Sandbox 2", "Open Play Sandbox 2P.map"))
    elif a[0] == "oracle":
        oracle(a[1])
    elif a[0] == "oracle-script":
        oracle_script()
    elif a[0] == "oracle-events":
        oracle_events(a[1])
    elif a[0] == "ours":
        ours(a[1], int(a[2]), int(a[3]) if len(a) > 3 else 1)
    else:
        sys.exit(__doc__)
