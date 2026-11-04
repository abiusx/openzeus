"""Build data/heroes.json for the heroes-and-monsters module (sim/heroes, docs/logic/heroes-monsters.md).

From the original game:
- monster behaviour rows per difficulty (Model/monster_behavior_<level>.txt via extracted/model/model_<d>.json,
  tools/model.py: 9 values, loader 0x0052F460);
- names (text group 190 monsters, 185 heroes and the hall texts; extracted/text/zeus_text.json);
- from Zeus.exe (read with pefile): the hero requirements g_hero_requirements 0x0063B3D0 (i32[8][5][6]), the monster
  target figure lists 0x00638C78 (i32[11][15]; building lists are data/military.json "targets"), the missile frame per
  monster 0x006409F0 (u32[18]), the arrival voice per hero (FUN_005A0F70's names 0x006469D8, 0x28 apart:
  Audio/Voice/Walker/<name>, played by hero_arrival_event_update 0x00481A80);
- the monument piece classes a monster attacks (nearest_attackable_building 0x004ABE80: vt+0x8C true, vt+0x9C not the
  constant true, i.e. "started" decides) and how they take damage (vt+0x90: 0x00556020 damaged flag + stage 0, 0x00536D00
  the whole building to rubble: the palace), from the class vtables (tools/re_monument_images.py vtables());
- the small id maps the exe keeps as switch code (cited by address below: god_monster 0x00586C90,
  god_guardian_monster 0x00586D50, monster_hero 0x00586DB0, sea monsters 0x0052F120, ranged 0x0052FA00).

Exe figure types in the target lists are mapped to our walker roles through data/play/walkers.json's "orig" notes
("... (type N)").

Usage: re/venv/bin/python tools/build_heroes.py   (needs extracted/model (tools/model.py), extracted/text, Zeus.exe)
"""
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DIFFICULTIES = ["VeryEasy", "Easy", "Normal", "Hard", "Impossible"]

# god id 0..13 -> monster id (god_monster 0x00586C90)
GOD_MONSTER = [3, 1, 5, 10, 6, 7, 9, 4, 0, 8, 11, 2, 12, 13]
# friendly god -> guardian monster (god_guardian_monster 0x00586D50): Poseidon Kraken, Ares Dragon,
# Hephaistos Talos, Hades Cerberus
GUARDIAN = {1: 1, 5: 7, 9: 8, 11: 2}
# monster id -> the hero who can slay it (monster_hero 0x00586DB0)
MONSTER_HERO = [1, 4, 1, 3, 5, 4, 5, 2, 2, 0, 3, 0, 6, 7, 6, 7]
SEA = (1, 10)                    # figure_is_sea_monster 0x0052F120
NO_RANGED = (5, 16)              # monster_has_ranged 0x0052FA00 false
# sprite file per monster / hero (extracted/sprites/<stem>; Zeus_<name> list 0x00640A4C; the Poseidon ones
# (Sphinx, Chimera, Harpies, Echidna, Atalanta, Bellerophon) are in the Poseidon_ files)
MONSTER_SPRITES = ["zeus_hydra", "zeus_kraken", "zeus_cerberus", "zeus_cyclops", "zeus_minotaur", "zeus_medusa",
                   "zeus_calydonianboar", "zeus_dragon", "zeus_talos", "zeus_hector", "zeus_scylla", "zeus_maenads",
                   "Poseidon_Sphinx", "Poseidon_Chimera", "Poseidon_Harpie", "Poseidon_Echidna"]
HERO_SPRITES = ["zeus_achilles", "zeus_heracles", "zeus_jason", "zeus_odysseus", "zeus_perseus", "zeus_theseus",
                "Poseidon_Atalanta", "Poseidon_Bellerophon"]


def exe(va, n):
    from disasm import read
    return read(va, n)


def anim_frames(stem):
    """Frames of the 4 animation groups g1 walk, g2 die, g3 attack, g4 special (monster_anim_info 0x00533B60 reads the
    group's first image's anim_frames, image record +30): from extracted/sprites/<stem>/atlas.json."""
    a = json.load(open(os.path.join(ROOT, "extracted", "sprites", stem, "atlas.json")))
    imgs = a["images"]
    by = {im["index"]: im for im in imgs} if isinstance(imgs, list) else {int(k): v for k, v in imgs.items()}
    out = []
    for gr in sorted(a["groups"], key=lambda x: x["first"])[:4]:
        out.append(by[gr["first"]].get("anim_frames", 0))
    return out


def role_of_type():
    w = json.load(open(os.path.join(ROOT, "data", "play", "walkers.json")))["roles"]
    out = {}
    for role, v in w.items():
        o = v.get("orig", "") if isinstance(v, dict) else ""
        for m in re.finditer(r"\(type (\d+)\)", o):
            out.setdefault(int(m.group(1)), role)
    out.setdefault(69, "hero")
    # types without a walkers.json role of their own: ours' one "cart" role is the exe's cart 4, storehouseman 9,
    # deliveryman 36 and ox cart 28 (0x1C) (sim/systems/walkers.py HERMES_133); 43 a god, 65 a priest (sim/gods)
    for t, r in ((9, "cart"), (36, "cart"), (28, "cart"), (43, "god"), (65, "priest")):
        out.setdefault(t, r)
    return out


def piece_attack():
    """Monument piece classes (docs/logic/monuments.md) attackable by monsters and the ones whose damage method
    collapses the whole building (0x00536D00) instead of resetting the piece (0x00556020)."""
    import re_monument_images as R
    r32 = lambda a: struct.unpack("<I", exe(a, 4))[0]
    att, collapse = [], []
    for cid, (o, v) in sorted(R.vtables().items()):
        if r32(v + 0x8C) == 0x00565940 and r32(v + 0x9C) != 0x00565940:
            att.append(cid)
            if r32(v + 0x90) == 0x00536D00:
                collapse.append(cid)
            else:
                assert r32(v + 0x90) == 0x00556020, (cid, hex(r32(v + 0x90)))
    return att, collapse


def main():
    text = json.load(open(os.path.join(ROOT, "extracted", "text", "zeus_text.json")))
    t185, t190 = text["185"], text["190"]
    v = struct.unpack("<240i", exe(0x0063B3D0, 240 * 4))
    reqs = [[list(v[h * 30 + i * 6:h * 30 + i * 6 + 6]) for i in range(5)] for h in range(8)]
    ft = struct.unpack("<165i", exe(0x00638C78, 165 * 4))
    roles = role_of_type()
    tfig = [[roles.get(x, f"type{x}") for x in ft[c * 15:(c + 1) * 15] if x] for c in range(11)]
    missile = list(struct.unpack("<18I", exe(0x006409F0, 18 * 4)))
    beh = {d: {m["id"]: m["values"] for m in json.load(open(os.path.join(ROOT, "extracted", "model",
                                                                         f"model_{d}.json")))["monsters"]}
           for d in DIFFICULTIES}
    monsters = []
    frames = [anim_frames(MONSTER_SPRITES[m]) for m in range(16)]
    for m in range(18):
        monsters.append(dict(id=m, name=t190[m], hero=MONSTER_HERO[m] if m < 16 else -1,
                             sea=m in SEA, ranged=m not in NO_RANGED, missile_frame=missile[m],
                             sprites=MONSTER_SPRITES[m] if m < 16 else None,
                             frames=frames[m] if m < 16 else None,
                             behaviour={d: beh[d].get(m) for d in DIFFICULTIES} if m < 16 else None))
    voice = [exe(0x006469D8 + 0x28 * h, 0x28).split(b"\0")[0].decode("latin1") for h in range(8)]
    heroes = []
    for h in range(8):
        heroes.append(dict(id=h, name=t185[h], hall=t185[8 + h], sprites=HERO_SPRITES[h],
                           monsters=[m for m in range(16) if MONSTER_HERO[m] == h], requirements=reqs[h],
                           voice=voice[h]))
    att, collapse = piece_attack()
    out = {"source": "tools/build_heroes.py (docs/logic/heroes-monsters.md)",
           "piece_attack": att, "piece_collapse": collapse,
           "behaviour_note": "9 bytes per monster: rest days (min,max) at aggressiveness 1, 2, 3; rampage months; "
                             "unused; target-search rings (monster_params_load 0x00532290)",
           "monsters": monsters, "heroes": heroes, "god_monster": GOD_MONSTER,
           "guardian": {str(k): v for k, v in GUARDIAN.items()}, "target_figures": tfig,
           "texts": {str(i): s for i, s in enumerate(t185)},
           "ticker": text["19"][234:243],
           "no_road": text["69"][4],                  # 69:4, the hall window without road access
           "goods": text["98"][:26], "gods": text["157"][:14], "units": text["8"][44:52],
           "figure_names": text["64"][:20],           # 64:v3 in the companies row (FUN_004FAA70)
           "ratings": text["61"][140:156]}            # 61:(crime level + 6) for the unrest row (0x005B6690), from 140   # hall window rows       # 19:234+hero "Your city is now worthy of X's presence", 19:242
    p = os.path.join(ROOT, "data", "heroes.json")
    with open(p, "w") as f:
        json.dump(out, f, indent=1)
    print("wrote", p)


if __name__ == "__main__":
    main()
