"""Gods data for the sim (sim/gods): the scenario god block of each map's adventure episode, and the exe's god
tables (docs/logic/religion.md). Writes data/gods/<map>.json (one per map in sim/world.py MAPS) and data/gods.json.

    python3 tools/build_gods.py

Inputs: zeus-original/app/Adventures (the .pak of each map's adventure, episode 1) and zeus-original/app/Zeus.exe
(GOG build, SHA-256 382bcd28...75e90a57; data tables read at their virtual addresses), and the god sprite files'
frame counts from extracted/sprites/<file>/atlas.json (python3 tools/sg3.py, docs/extraction-plan.md).
- God block (`g_scenario_gods` 0x00FFA450, copied from the episode by `episode_start_load` 0x00420390): +0x00 int[24]
  god per slot (-1 empty), +0x60 independent monster, +0xC4 u8[24] may be jealous, +0xDC max sanctuaries.
  `scenario_gods_apply` 0x00586F70 turns slots into the god records' roles: unfriendly (slots 0..11), listed
  (slots 0..3, 12..17).
- Exe tables: jealousy weights 0x0063B01C (i32[14]), curse months 0x0063AEAC (i32[14*5], [god*5 + difficulty]),
  attack frame 0x0063A8FC (i32[14]). The switch tables (help threshold 0x004E6040, help cost 0x004E60B0, god power
  0x004EE710, visit bless chance 0x004E9290, priests 0x004EA330) are code; their values are copied here by hand
  from the decompile (re/decomp/zeus.c; python3 tools/fn.py ADDR).
- Voices (FUN_005A1050 (god, kind), Audio/Voice/Walker/<file>): per god a table of 0x28-byte names (its address is an
  immediate of that function, by god), kind k = entry k: 0/1/2 the jealous attack message by sanctuaries placed
  (3+ / 1..2 / none; god_attack_message 0x004F1110), 3 a god invasion (event_god_attack 0x00482B10), 4 a god's
  monster (monster_event_update 0x00481430), 5 / 6 a quest given / fulfilled (event_quest 0x00482820), 7 help
  (god_message 0x00480590); Apollo kind 1 in a Poseidon game: entry 8.
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
EXE = os.path.join(ROOT, "zeus-original", "app", "Zeus.exe")
ADV = os.path.join(ROOT, "zeus-original", "app", "Adventures")
OUT = os.path.join(ROOT, "data", "gods")
# the adventure whose episode 1 a map is played from (docs/logic/events.md "Open-play adventures the game ships")
ADVENTURE = {"sandbox": "}Open Play Sandbox.pak", "sandbox2": "Open Play Sandbox 2/Open Play Sandbox 2.pak"}
SPRITES = ["Zeus_Zeus", "Zeus_Poseidon", "Zeus_Demeter", "Zeus_Apollo", "Zeus_Artemis", "Zeus_Ares", "Zeus_Aphrodite",
           "Zeus_Hermes", "Zeus_Athena", "Zeus_Hephaestus", "Zeus_Dionysus", "Zeus_Hades", "Poseidon_Hera",
           "Poseidon_Atlas"]                                     # PTR_s_Zeus_Zeus_0063a88c
GODS = ["zeus", "poseidon", "demeter", "apollo", "artemis", "ares", "aphrodite", "hermes", "athena", "hephaistos",
        "dionysus", "hades", "hera", "atlas"]


def exe_reader():
    d = open(EXE, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
    secs = []
    for i in range(nsec):
        o = pe + 24 + opt + 40 * i
        vsize, va, rsize, raw = struct.unpack_from("<IIII", d, o + 8)
        secs.append((va, max(vsize, rsize), raw))

    def read(addr, n):
        rva = addr - base
        for va, size, raw in secs:
            if va <= rva < va + size:
                return d[raw + rva - va: raw + rva - va + n]
        raise ValueError(hex(addr))
    return read


def god_block(pak):
    from scenario_events import SET_LAYOUT
    d = open(pak, "rb").read()
    ver = struct.unpack_from("<I", d, 4)[0]
    L = SET_LAYOUT[ver]
    blk = d[L["gods"]: L["gods"] + L["god_size"]]          # episode 1
    slots = list(struct.unpack_from("<24i", blk, 0))
    return dict(source=os.path.relpath(pak, ROOT), episode=1, slots=slots,
                jealous=[blk[0xC4 + i] for i in range(24)],
                independent_monster=struct.unpack_from("<i", blk, 0x60)[0], max_sanctuaries=blk[0xDC])


VOICE_TABLES = {0: 0x00645830, 1: 0x00645970, 11: 0x00645AB0, 2: 0x00645BF0, 8: 0x00645D30, 4: 0x00645E70,
                3: 0x00645FB0, 5: 0x00646118, 9: 0x00646258, 6: 0x00646398, 7: 0x006464D8, 10: 0x00646618,
                12: 0x00646758, 13: 0x00646898}             # FUN_005A1050's string pointers by god


def voices(read):
    out = []
    for gi in range(14):
        row = []
        for k in range(9):
            nm = read(VOICE_TABLES[gi] + 0x28 * k, 0x28).split(b"\0")[0].decode("latin1")
            row.append(nm if nm[:3] == read(VOICE_TABLES[gi], 3).decode("latin1") else None)
        out.append(row)
    return out


def tables():
    read = exe_reader()
    i32s = lambda a, n: list(struct.unpack("<%di" % n, read(a, 4 * n)))   # noqa: E731
    curse = i32s(0x0063AEAC, 70)
    # g_god_curse_types 0x0063AA4C: 20 ints per god row, 0-terminated (row 14, past the table, is Zeus' random-row
    # quirk: it reads the curse-length table, i.e. types 2, 4, 6, 9 for the first entries of 0x0063AEAC)
    raw = i32s(0x0063AA4C, 20 * 15)
    ctypes = []
    for r in range(15):
        row = raw[r * 20:(r + 1) * 20]
        ctypes.append(row[:row.index(0)] if 0 in row else row)
    tb = i32s(0x006383E0, 50 * 11)                                # g_target_buildings: 50 ints per category
    cats = []
    for c in range(11):
        row = tb[c * 50:(c + 1) * 50]
        cats.append(row[:row.index(0)] if 0 in row else row)
    groups = i32s(0x0063A934, 70)                                 # god x 5 action groups -> sprite group (0x800 flat)
    from play_buildings import raw_speed, rate100_ticks, RATE100
    frames, speeds = [], []
    for gi, f in enumerate(SPRITES):
        a = json.load(open(os.path.join(ROOT, "extracted", "sprites", f, "atlas.json")))
        im = {i["index"]: i for i in a["images"]}
        first = [gr["first"] for gr in a["groups"]]
        fr, sp = [], []
        for k in range(5):
            sg = groups[gi * 5 + k] & ~0x800
            fr.append(im[first[sg]]["anim_frames"])               # FUN_004EA4E0: header +0x1E of the group's sprite
            sp.append(raw_speed(f, first[sg]))                    # header +0x3A: the rate-100 gate index
        frames.append(fr)
        speeds.append(sp)
    return {
        "_doc": "Generated by tools/build_gods.py from Zeus.exe (docs/logic/religion.md). Index = god id.",
        "gods": GODS,
        "jealousy_weight": i32s(0x0063B01C, 14),                       # +1 when drawn (jealousy_update 0x004F0B50)
        "curse_months": [curse[g * 5: g * 5 + 5] for g in range(14)],   # [god][difficulty] (god_curse_length)
        "attack_frame": i32s(0x0063A8FC, 14),                          # g_god_attack_frame
        "shot_frame": i32s(0x0063A8C4, 14),
        "curse_types": ctypes,                                         # [row] zeus types (row = god; 14 = quirk)
        "destroy_types": cats,                                         # [category] zeus types
        # god_destroy_category 0x004ED200 (-1 = Zeus / Ares: a random category 0..10)
        "destroy_category": [-1, 1, 0, 6, 0, -1, 7, 2, 3, 2, 6, 4, 9, 2],
        "voices": voices(read),         # [god][kind] Audio/Voice/Walker file (FUN_005A1050; see the docstring)
        "sprite_files": SPRITES,
        "sprite_groups": [[groups[g * 5 + k] for k in range(5)] for g in range(14)],   # 0x0063A934, |0x800 = flat
        "frames": frames,               # [god][walk, vanish, attack, appear, cast] (extracted/sprites/<file>/atlas.json)
        # figure_god_handler's tail steps every group but walk with sprite_anim_step(.., rate 100) in most actions
        # (appear 0x0A / 0x10, cast 0x0C / 0x13 / 0x39 .., attack 0x3B / 0x44 / 0x4B / 0x50 / 0x52 .., vanish 4 / 0x0F /
        # 0x51): one frame per frame_ticks ticks (tools/play_buildings.py rate100_ticks; docs/logic/religion.md
        # "Animation", bug 393). Rate 0 (one frame a tick): walk, 0x0B vanish, 0x22, 0x3C duel, 0x49.
        "image_speed": speeds,          # [god][group] sprite header +0x3A
        "frame_ticks": [[rate100_ticks(s) for s in sp] for sp in speeds],
        "rate100": dict(RATE100, _doc="ms per tick at the default game speed 90 (simulation_due 0x005168A0); "
                        "gate 0x006668EC[i] fires every gate_ms * i ms (0x00413330)"),
        # code tables (switches), copied from the decompile
        "help_threshold": [26, 14, 14, 14, 14, 122, 20, 32, 20, 32, 26, 20, 20, 14],     # 0x004E6040
        "help_cost": [[24, 36], [12, 18], [12, 18], [12, 18], [12, 18], [120, 180], [18, 27], [30, 45],
                      [18, 27], [30, 45], [24, 36], [18, 27], [18, 27], [12, 18]],     # 0x004E60B0 [auto, prayed]
        "power": [14, 13, 10, 7, 8, 5, 3, 2, 9, 4, 1, 12, 11, 6],                       # 0x004EE710
        "bless_chance": [10, 25, 33, 50, 50, 0, 10, 0, 50, 25, 25, 33, 33, 33],          # 0x004E9290
        "priests": [3, 3, 2, 2, 2, 1, 1, 1, 2, 1, 1, 3, 3, 2],                            # 0x004EA330
        # god building type lists 0x004E8F20..0x004E9260 (sanctification and curses); Zeus = all of them,
        # Aphrodite = houses 2..14 with residents
        "types": {"poseidon": [44, 45, 133], "demeter": [31, 32, 33],
                  "apollo": [79, 80, 81, 82, 202, 203, 205, 207], "artemis": [46], "ares": [], "hermes": [],
                  "athena": [41, 54], "hephaistos": [55, 135], "dionysus": [53], "hades": [48, 50, 122],
                  "hera": [214, 216], "atlas": [51, 211]},
    }


def main():
    from sim.world import MAPS
    os.makedirs(OUT, exist_ok=True)
    t = tables()
    with open(os.path.join(ROOT, "data", "gods.json"), "w") as f:
        json.dump(t, f, indent=1)
    print("data/gods.json")
    for name in MAPS:
        if name not in ADVENTURE:
            print(f"{name}: no adventure known, skipped (gods off for this map)")
            continue
        b = god_block(os.path.join(ADV, ADVENTURE[name]))
        b["_doc"] = ("Scenario god block of the map's adventure, episode 1 (tools/build_gods.py; docs/logic/religion.md "
                     "'Scenario god block'). slots: god id per slot (0..3 unfriendly + monster, 4..11 unfriendly, "
                     "12..17 friendly, 18..23 other friendly; -1 empty).")
        with open(os.path.join(OUT, f"{name}.json"), "w") as f:
            json.dump(b, f, indent=1)
        named = {s: GODS[g] for s, g in enumerate(b["slots"]) if 0 <= g < 14}
        print(f"{name}: {named}, max {b['max_sanctuaries']} -> data/gods/{name}.json")


if __name__ == "__main__":
    main()
