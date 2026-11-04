"""Sprite mapping of the heroes-and-monsters module for play mode -> data/play/heroes.json (sim/heroes,
docs/logic/heroes-monsters.md "Monster animation").

From the exe (cited, values from the decompile): monster_anim_info 0x00533B60 and the hero picture switch 0x004FA860
pick group g1 walk/stand, g2 die (action 4), g3 attack/fight (monster 5, 12, 16, 25, 27; hero 5), g4 special
(monster 28 missile; hero 0x13 swimming) of the figure's own sprite file (Zeus_<name> list 0x00640A4C / 0x0063B38C);
image = group first + frame * 8 + direction (8 directions; the Kraken's and Scylla's death: 1). The frame (+0x01) goes
+1 every tick in every group, walking or standing, wrapped at the group's frame count (figure_hero_update 0x004C9D18,
figure_monster_update); dying: min(timer, frames - 1) for a hero (0x004C9DFA), min(timer / 2, frames - 1) for a
monster -> roles' frame_rule "tick", die_rate 1 / 2 (viewer/play/scene.js; bug 386). Group firsts and frame
counts from extracted/sprites/<file>/atlas.json (frames = the group's first image's anim_frames).
The Hero's Hall statue (building_extra_draw 0x0044F320): SPR_HERO_STATUES (Zeus_General) + hero id at draw point +
(0x2B, -0x48); Atalanta and Bellerophon from the Poseidon set (hypothesis: Poseidon_Loaded group of the same name;
not found -> none).

The hall's fire pot (city_draw 0x00459xxx case 0x7D: only while the hero's figure exists, hero_record_figure; drawn by
0x0045C580): SprAmbient rank 69 (set 0x2045, the sanctuary fire pots' group), its per-building frame counter +0xEC,
at the draw point + (0x7D - anchor x, 0x3C - anchor y) (oracle 1I-hero h_0900.bmp).

The hero's raft (bug 392): on deep water outside a bridge the hero shows his g4 group (action 0x13 look) and, as his
extra picture, SprAmbient rank 87 (0x2057: 4 frames x 16, image first + frame * 16 + 2 * view dir).

Walkers carry good = "m<monster id>" / "h<hero id>" (sim/heroes), so roles "monster" / "hero" resolve by good.

Usage: python3 tools/play_heroes.py    (atlases: python3 tools/play_atlas.py <the files listed in "files">)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(ROOT, "extracted", "sprites")
DIRS8 = ["NE", "E", "SE", "S", "SW", "W", "NW", "N"]


def groups(f):
    a = json.load(open(os.path.join(SPR, f, "atlas.json")))
    im = {i["index"]: i for i in a["images"]}
    gs = sorted(a["groups"], key=lambda g: g["first"])
    out = []
    for i, g in enumerate(gs):
        nxt = gs[i + 1]["first"] if i + 1 < len(gs) else max(im) + 1
        out.append((g["first"], nxt - g["first"], im[g["first"]].get("anim_frames") or 1))
    return out


def block(f, first, count, frames):
    if count < 8 * frames:                       # one direction (the Kraken's / Scylla's death)
        return dict(file=f, start=first, dirs=1, frames=count, order="frame")
    return dict(file=f, start=first, dirs=8, frames=frames, order="frame-major", dir_order=DIRS8)


def main():
    d = json.load(open(os.path.join(ROOT, "data", "heroes.json")))
    roles = {"monster": {"by": "good", "map": {}, "fallback_role": "monster_11"},
             "hero": {"by": "good", "map": {}, "fallback_role": "hero_0"}}
    files = []
    for kind, rows, pre in (("monster", d["monsters"][:16], "m"), ("hero", d["heroes"], "h")):
        for r in rows:
            f = r["sprites"]
            if not f or not os.path.exists(os.path.join(SPR, f, "atlas.json")):
                continue
            g = groups(f)
            role = f"{kind}_{r['id']}"
            roles[kind]["map"][f"{pre}{r['id']}"] = role
            sp = block(f, *g[3])
            roles[role] = dict(file=f, walk=block(f, *g[0]), die=block(f, *g[1]), fight=block(f, *g[2]),
                               special=sp, work={"special": dict(sp, offset=1)} if kind == "monster" else None, orig=f"{r['name']} ({'0x44' if kind == 'monster' else '0x45'})",
                               frame_rule="tick", die_rate=2 if kind == "monster" else 1)
            if roles[role]["work"] is None:
                del roles[role]["work"]                  # the monster's 28 look "work" / "special" (heroes: none)
            files.append(f)
    gen = json.load(open(os.path.join(SPR, "Zeus_General", "atlas.json")))
    first = next(g["first"] for g in gen["groups"] if g["name"] == "SPR_HERO_STATUES")
    statue = dict(file="Zeus_General", first=first, count=6, dx=0x2B, dy=-0x48,
                  src="building_extra_draw 0x0044F320: SPR_HERO_STATUES + hero id at the draw point + (0x2B, -0x48)")
    import play_monuments
    sa = json.load(open(os.path.join(SPR, "SprAmbient", "atlas.json")))["groups"]
    firepot = dict(play_monuments.anim("SprAmbient", sa[68]["first"]), dx=0x7D, dy=0x3C,
                   src="0x0045C580: SprAmbient rank 69 at the draw point + (0x7D - ax, 0x3C - ay) while the hero exists")
    raft = dict(play_monuments.anim("SprAmbient", sa[86]["first"]), dx=-2, dy=-10,
                src="figure_hero_update 0x004C8F50 tail: on deep water (not a bridge) sprite_extra = "
                    "sprite_anim_step(0x2057 = SprAmbient rank 87, a per-figure counter, view dir * 2, 100): image first + "
                    "frame * stride + 2 * dir, at the plain point (picture point - (2, 10)), under the hero except "
                    "facing S (walker_draw 0x0044FEF0)")
    # a monster's missile (0x34 / 0x2D from monster_missile_attack 0x00530ED0): both handlers' 0x44 branch switch on
    # the MISSILE's own +0x0B (zeroed by figure_create, never set by 0x004D9D70: disassembly 0x004BDC44 / 0x004BB575 read
    # [current figure + 0x0B]), so every monster's missile takes the default case: sprite_anim_step(0x222F, &its
    # anim_frame, direction (32-way angle - 4 view) / 4, 100): the destruction file's group 46, 8 frames x 8 directions,
    # rate 100 (image speed +0x3A -> ticks a frame, play_buildings.rate100_ticks); no extra picture
    from play_buildings import raw_speed, rate100_ticks
    da = json.load(open(os.path.join(SPR, "destruction", "atlas.json")))
    m0 = da["groups"][(0x222F & 0x1FF) - 1]["first"]
    mim = next(i for i in da["images"] if i["index"] == m0)
    missile = dict(file="destruction", start=m0, frames=mim["anim_frames"] or 1, dirs=8, packed="0x222f",
                   ticks_per_frame=rate100_ticks(raw_speed("destruction", m0)))
    out = {"source": "tools/play_heroes.py", "roles": roles, "files": files, "hall_statue": statue,
           "hall_firepot": firepot, "hero_raft": raft, "missile": missile}
    p = os.path.join(ROOT, "data", "play", "heroes.json")
    with open(p, "w") as fh:
        json.dump(out, fh, indent=1)
    print("wrote", p, len(files), "sprite files")


if __name__ == "__main__":
    main()
