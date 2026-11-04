"""Build data/military.json for the military module (sim/military, docs/logic/military.md) from extracted/model.

Per difficulty: the Figure_model rows of the fighting figures (by our role name) and the enemy model rows
(11 armies x 6 rows: infantry, missile, cavalry, warship, transport, unused). Columns as figure_type_value
0x004E1B20 reads them. Hand-editable afterwards like data/*.json.

Also from Zeus.exe: the invaders' target classes (TARGETS 0x006383E0, i32[11][50] building types, docs/logic/military.md
"Enemy targets"), read with pefile.

Usage: re/venv/bin/python tools/build_military.py   (needs extracted/model/model_<difficulty>.json: tools/model.py,
       and zeus-original/app/Zeus.exe)
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "extracted", "model")
DIFFICULTIES = ["VeryEasy", "Easy", "Normal", "Hard", "Impossible"]
COLS = ["unit_type", "hp", "attack", "armor", "missile_armor", "missile_attack", "missile_range", "missile_rate",
        "speed", "frequency", "defensive_morale", "special_pct", "special_range"]
# our walker role -> Figure_model row (figure type)
ROLES = {"rabble": 11, "hoplite": 12, "horseman": 13, "wall_sentry": 39, "tower_sentry": 46, "trireme": 57,
         "wolf": 59, "watchman": 61, "hunter": 53, "shepherd": 30, "goatherd": 31, "sheep": 49, "goat": 50,
         "cattle": 76, "boar": 51, "woodcutter": 55, "immigrant": 1,
         "god": 67, "monster": 68, "hero": 69}        # sim/heroes (rows 67..69; unit class set by figure_type_value)
CLASSES = ["infantry", "missile", "cavalry", "warship", "transport"]
# army index (Formation+0x6A, city+0xCC nation) -> sprite file (extracted/sprites/<file>); docs/logic/military.md
ARMY_SPRITES = ["Zeus_Greek", "Zeus_Trojan", "Zeus_persian", "Zeus_centaur", "Zeus_amazon", "Poseidon_Egyptian",
                "Poseidon_Mayan", None, "Poseidon_Oceanid", "Poseidon_Atlantean", "Zeus_AresWarriors"]


def row(r):
    return {c: r[c] for c in COLS}


def targets():
    import struct
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from disasm import read
    b = read(0x006383E0, 11 * 50 * 4)
    return [[v for v in struct.unpack_from("<50i", b, c * 200) if v] for c in range(11)]


def archer_shots():
    """Per army: the archer's shot (action 6, fig_handler_enemy_archer 0x004B99B0): sprite_anim_step(fight group
    0x006381B4[army], .., rate 100) until the frame wraps to 0, then action 7 and attack_timer 0 (the reload counts
    again: archer_try_shoot 0x005009E0). frames = the group's first image anim_frames, frame_ticks per frame at the
    exe's default game speed (tools/play_buildings.py rate100_ticks; bug 393)."""
    import struct
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from disasm import read
    from play_military import atlas_groups, anim_frames, FILES
    from play_buildings import raw_speed, rate100_ticks
    b = read(0x006381AC, 11 * 16)
    out = []
    for a in range(11):
        ids = struct.unpack_from("<4i", b, a * 16)
        coll = ids[0] >> 9
        if not coll:
            out.append(None)
            continue
        f = FILES()[coll]
        first = atlas_groups(f)[(ids[2] & 511) - 1][0]
        sp = raw_speed(f, first)
        out.append(dict(frames=anim_frames(f, first), speed=sp, frame_ticks=rate100_ticks(sp)))
    return out


def shot_table():
    """SHOT[army]: the frame of action 6 at which the archer's missile leaves (invader handler 0x00500B70, action 6 at
    0x005011C0 builds the table on the stack: mov [esp + 0x14 + 4 i], imm / reg, 0x005011CE..0x00501220; the check
    `anim_frame == [esp + army * 4 + 0x14]` at 0x0050125F). Read from the instructions (capstone)."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import capstone
    from disasm import read
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    regs, slots = {}, {}
    for ins in md.disasm(read(0x005011CE, 0x52), 0x005011CE):
        if ins.mnemonic != "mov":
            continue
        dst, src = ins.operands
        val = src.imm if src.type == capstone.x86.X86_OP_IMM else regs.get(src.reg) \
            if src.type == capstone.x86.X86_OP_REG else None
        if dst.type == capstone.x86.X86_OP_REG:
            regs[dst.reg] = val
        elif dst.type == capstone.x86.X86_OP_MEM and dst.mem.base == capstone.x86.X86_REG_ESP:
            slots[dst.mem.disp] = val
    return [slots[0x14 + 4 * a] for a in range(11)]


# building_footprint_place 0x004A04B0 writes the footprint's width - 1 into the piece grid's low nibble (line of fire
# 0x004D9B80 blocks on it). FUN_00496CA0 places these as 1x1 parts, so their tiles carry 0 (checked against the
# original saves' grids: tools/los_piece_check.py): storehouse 0x3A and trading post 0x3E (9 / 16 parts, case 0x3A),
# dock 0x3C (its land square as parts; its 2x2 water square by FUN_004A1350, nibble 1). [width inside the size x size
# box from the origin, width outside it]
LOS_PART_WIDTH = {"storehouse": [1, 1], "trading_post": [1, 1], "dock": [1, 2]}


def main():
    out = {"source": "extracted/model/model_<difficulty>.json (Figure_model 0x00786068, enemy rows 0x007851F8)",
           "columns": COLS, "armies": [], "difficulty": {}, "targets": targets(),
           "targets_note": "exe building types per target class 0..10 (house types 2..8 common levels, 9..14 elite)",
           "los_part_width": LOS_PART_WIDTH}
    for d in DIFFICULTIES:
        m = json.load(open(os.path.join(EX, f"model_{d}.json")))
        figs = {f["id"]: f for f in m["figures"]}
        armies = []
        for a in range(11):
            rows = [e for e in m["enemies"] if e["army"] == a]
            armies.append({CLASSES[i]: row(rows[i]) for i in range(5)})
            if d == "Normal":
                out["armies"].append(dict(index=a, name=rows[0]["name"], sprites=ARMY_SPRITES[a]))
        out["difficulty"][d] = dict(figures={k: row(figs[v]) for k, v in ROLES.items()}, armies=armies)
    for a, shot, sf in zip(out["armies"], archer_shots(), shot_table()):
        if shot is not None:
            shot["shot_frame"] = sf      # the missile at this frame (action 6, 0x005011C0); frame 1: the sound
        a["archer_shot"] = shot
    p = os.path.join(ROOT, "data", "military.json")
    with open(p, "w") as f:
        json.dump(out, f, indent=1)
    print("wrote", p)


if __name__ == "__main__":
    main()
