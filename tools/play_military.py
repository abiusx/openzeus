"""Sprite mapping of the military module for play mode -> data/play/military.json (docs/play/military.md).

From Zeus.exe (pefile): the invaders' sprite tables per army (missile 0x006381AC, infantry 0x0063825C, cavalry
0x0063830C: walk, die, fight, wall-attack packed ids = collection*512 + group number) and the army sg3 names
(0x0063B9F8 / collections 0x0063BA24). From extracted/sprites/<file>/atlas.json: each group's first atlas index and
image count (group number n = atlas group n-1). Fixed SprMain / SprAmbient / Zeus_General groups from the handlers
(docs/logic/military.md "Defence sprites", "Wolf sprites", "Soldier sprites", the standard 0x004B3E00).

Usage: re/venv/bin/python tools/play_military.py
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from play_buildings import raw_speed, rate100_ticks  # noqa: E402
DIRS8 = ["NE", "E", "SE", "S", "SW", "W", "NW", "N"]


def atlas_groups(f):
    a = json.load(open(os.path.join(ROOT, "extracted", "sprites", f, "atlas.json")))
    gs = sorted(a["groups"], key=lambda g: g["first"])
    total = max(int(k) for k in a["images"]) + 1 if isinstance(a["images"], dict) else len(a["images"]) + 1
    out = {}
    for i, g in enumerate(gs):
        nxt = gs[i + 1]["first"] if i + 1 < len(gs) else total
        out[g["id"]] = (g["first"], nxt - g["first"])
    return out


_AF = {}


def anim_frames(f, idx):
    """The atlas image's anim_frames (.sg3 record +0x1E)."""
    if f not in _AF:
        a = json.load(open(os.path.join(ROOT, "extracted", "sprites", f, "atlas.json")))
        ims = a["images"].values() if isinstance(a["images"], dict) else a["images"]
        _AF[f] = {im["index"]: im.get("anim_frames", 0) for im in ims}
    return _AF[f].get(idx, 0)


def block(f, groups, n, dirs=8):
    """A walker block for packed group number n (atlas group n-1). Death groups: one direction unless the group
    holds >= 64 images in eights (Ares warriors 19 x 8, Egyptian/Atlantean cavalry 9 x 8)."""
    first, count = groups[n - 1]
    if dirs == 1 and not (count >= 64 and count % 8 == 0):
        # the exe's count is the group's first image's anim_frames (FUN_005AF5F0, e.g. fig_handler_enemy_infantry
        # 0x004B9C20 dying: min(timer / 2, n - 1)): 15 for the Persian / Amazon / Centaur deaths of 16 images (bug 393)
        af = anim_frames(f, first)
        return dict(file=f, start=first, dirs=1, frames=af if 0 < af <= count else count, order="frame")
    return dict(file=f, start=first, dirs=8, frames=count // 8, order="frame-major", dir_order=DIRS8)


def FILES():
    """Sprite collection -> army sprite file, in the extracted folder's own spelling."""
    on_disk = {d.lower(): d for d in os.listdir(os.path.join(ROOT, "extracted", "sprites"))}
    files = {18: "Zeus_Greek", 19: "Zeus_Trojan", 20: "Zeus_persian", 21: "Zeus_centaur", 22: "Zeus_amazon",
             54: "Poseidon_Egyptian", 55: "Poseidon_Mayan", 56: "Poseidon_Phoenician", 57: "Poseidon_Oceanid",
             58: "Poseidon_Atlantean", 50: "Zeus_AresWarriors"}
    return {k: on_disk.get(v.lower(), v) for k, v in files.items()}


def main():
    from disasm import read
    names = [read(p, 32).split(b"\0")[0].decode() for p in struct.unpack("<11I", read(0x0063B9F8, 44))]
    files = FILES()
    roles = {}
    armies = []
    for cls, base in (("enemy_archer", 0x006381AC), ("enemy_infantry", 0x0063825C), ("enemy_cavalry", 0x0063830C)):
        b = read(base, 11 * 16)
        by = {}
        for a in range(11):
            ids = struct.unpack_from("<4i", b, a * 16)
            coll = ids[0] >> 9
            if not coll:
                continue
            f = files[coll]
            gr = atlas_groups(f)
            w, d, fi, wall = [v & 511 for v in ids]
            key = f"{cls}_{a}"
            roles[key] = dict(file=f, walk=block(f, gr, w), die=block(f, gr, d, dirs=1),
                              fight=block(f, gr, fi), fight_rule="enemy", orig=f"army {a} ({names[a]}) {cls}")
            if cls == "enemy_archer":
                # melee (action 5): fig_handler_enemy_archer 0x004B99B0 draws sprite_anim_step(fight group, .., rate
                # 100) on its anim_frame (infantry / cavalry: frame (attack_timer - 10) / 2 once it is >= 12, "enemy")
                fb = roles[key]["fight"]
                roles[key]["fight"] = dict(fb, ticks_per_frame=rate100_ticks(raw_speed(f, fb["start"])))
                roles[key]["fight_rule"] = "rate100"
            # siege (direction 0xB, figure_check_next_tile 0x004D8BB0: standing at a wall / building it hits): the
            # handlers (0x004B99B0 / 0x004B9C20 / 0x004B9E20) play the wall-attack group (archers +0xC; infantry and
            # cavalry their fight group) with sprite_anim_step(.., rate 100): the frame steps on a tick only when the
            # wall-clock gate 0x006668EC[speed] fired that game turn (0x00413330: once per 20 * speed ms), speed =
            # the group's first image +0x3A (bug 393)
            sg = block(f, gr, wall if cls == "enemy_archer" and wall != fi else fi)
            roles[key]["work"] = {"siege": dict(sg, rate=100, speed=raw_speed(f, sg["start"]))}
            # the shot (action 6): the fight group at rate 100 too, one frame per ticks_per_frame, held in action 6
            # until it wraps (fig_handler_enemy_archer 0x004B99B0; sim invaders, bug 393); archer_try_shoot sets
            # anim_frame 0 and the tail steps it in the same tick: frame 1 at the shot's start (offset 1; oracle
            # 1B-inv-city, figure 1845: frames 1..11 at dumps 376..386, the wrap at 387)
            sh = block(f, gr, fi)
            roles[key]["work"]["shoot"] = dict(sh, ticks_per_frame=rate100_ticks(raw_speed(f, sh["start"])),
                                               offset=1) if cls == "enemy_archer" else sh
            by[f"army{a}"] = key
        roles[cls] = dict(by="good", map=by, fallback_role=by.get("army0", next(iter(by.values()))))
    for a in range(11):
        armies.append(dict(index=a, sg3=names[a], file=next((files[c] for c in files if names[a].lower().startswith(files[c].lower())), names[a])))
    sm = atlas_groups("SprMain")
    amb = atlas_groups("SprAmbient")
    idle = dict(block("SprMain", sm, 84), seq=[13, 1, 1, 1, 1, 1, 13, 1, 1, 1, 1, 1])   # frames 0 and 6 held 13 ticks
    roles["tower_sentry"] = dict(file="SprMain", walk=block("SprMain", sm, 81), die=block("SprMain", sm, 82, 1),
                                 work={"idle": idle, "shoot": dict(block("SprMain", sm, 83), ticks_per_frame=2)},
                                 orig="FIG_BALLISTA (type 46): SprMain packed 0x6654 idle, 0x6653 shoot")
    roles["wall_sentry"] = dict(file="SprMain", walk=block("SprMain", sm, 81), die=block("SprMain", sm, 82, 1),
                                fight=block("SprMain", sm, 83),
                                work={"shoot": dict(block("SprMain", sm, 83), ticks_per_frame=2, clamp=4),   # T 0x005F61E8
                                      "post": dict(block("SprMain", sm, 84), ticks_per_frame=3, loop=4)},
                                orig="FIG_WALLGUY (type 39): SprMain packed 0x6651 walk, 0x6652 die, 0x6653 shoot, 0x6654 post")
    # ships (docs/logic/navy.md "Pictures"): moving = 4 frames x 16 headings (the odd ones for the 8 directions),
    # dying 12 x 8, idle 1 x 8; enemy warships: army 0 Zeus_Greek groups 10/11/12, every other nation SprMain 92/93/94
    # (table 0x6383BC/0x6383C8); transports SprMain 196/197/198 (Oceanid transports, Destruction 54/55: not drawn)
    def ship(f, gr, walk, die, idle):
        w = dict(file=f, start=gr[walk][0] + 1, dirs=8, frames=4, order="frame-major", stride_dir=2, stride_frame=16,
                 dir_order=DIRS8)
        st = dict(file=f, start=gr[idle][0], dirs=8, frames=1, order="frame-major", dir_order=DIRS8)
        return dict(file=f, walk=w, die=dict(file=f, start=gr[die][0], dirs=8, frames=12, order="frame-major",
                                             dir_order=DIRS8),
                    work={"idle": st, "idle_empty": st, "shoot": dict(w, ticks_per_frame=1)})
    gg = atlas_groups(files[18])
    by = {}
    for a in range(11):
        key = f"enemy_warship_{a}"
        roles[key] = dict(ship(files[18], gg, 10, 11, 12) if a == 0 else ship("SprMain", sm, 92, 93, 94),
                          orig=f"enemy warship 0x40, nationality {a}")
        by[f"army{a}"] = key
    roles["enemy_warship"] = dict(by="good", map=by, fallback_role="enemy_warship_1")
    roles["enemy_transport"] = dict(ship("SprMain", sm, 196, 197, 198), orig="enemy transport 0x3F")
    roles["trireme"] = dict(ship("SprMain", sm, 120, 121, 122), orig="FIG_TRIREME 0x39")
    # its overlays (walker_draw, Zeus games): the crew (+0x150) PoseidonImps 133 (4 x 8; frame 0 standing), 135 while
    # shooting (12 x 8, frame +0x131 / 3), 134 sinking (12 x 8); none while the crew is home (wharf C4 & 1). The
    # selection flag (+0x180, only while selected): 131 moving (4 x 16, odd headings), 132 standing (1 x 8)
    pi = atlas_groups("PoseidonImps")
    plain = lambda n, frames, **kw: dict(file="PoseidonImps", start=pi[n][0], dirs=8, frames=frames, order="frame-major",
                                         dir_order=DIRS8, **kw)
    roles["trireme"]["layers"] = dict(walk=[plain(133, 4)], idle=[plain(133, 1)], idle_empty=[],
                                      shoot=[plain(135, 12, ticks_per_frame=3)], die=[plain(134, 12)])
    roles["trireme"]["flag"] = dict(walk=dict(file="PoseidonImps", start=pi[131][0] + 1, dirs=8, frames=4,
                                              order="frame-major", stride_dir=2, stride_frame=16, dir_order=DIRS8),
                                    still=plain(132, 1))
    arrow = dict(file="SprAmbient", start=amb[79][0], dirs=32, shadow=amb[78][0])
    enemy_arrows = {"0": dict(file="SprAmbient", start=amb[51][0], dirs=1, shadow=amb[50][0]),
                    "1": dict(file="SprAmbient", start=amb[71][0], dirs=32, shadow=amb[70][0])}
    # the palace companies' and wolves' blocks over walkers.json (tools/play_walkers.py): rabble fight = 6945 (12 x 8,
    # pick up a stone and throw; the knife group 7041 is never referenced), fight-frame rules, wolf look blocks
    def fixed(n, frames, **kw):
        return dict(file="SprMain", start=sm[n][0], dirs=8, frames=frames, order="frame-major", dir_order=DIRS8, **kw)
    over = {
        # melee (fig_handler_rabble 0x004B31F0, action 5): the handler's prologue +1 a tick (wrap 12, kept in action 5)
        # and sprite_anim_step(6945, .., rate 100) +1 more on the gated ticks: fr = dt + dt // ticks_per_frame
        # the throw (actions 10 / 0xB / 0x11 standing with a target, bug 436): the same group by sprite_anim_step(..,
        # rate 100) on its anim_frame alone (the prologue's +1 is undone while it stands), stepped in the look's first
        # tick: fr = (c0 + 1 + dt // ticks_per_frame) % 12, c0 from look [12] (sim forces.look), while it stands
        # with a target
        "rabble": dict(fight=fixed(127, 12, ticks_per_frame=rate100_ticks(raw_speed("SprMain", sm[127][0]))),
                       fight2=None, fight_rule="rabble",
                       work={"throw": fixed(127, 12, ticks_per_frame=rate100_ticks(raw_speed("SprMain", sm[127][0])),
                                            counter=True, offset=1)}),
        "hoplite": dict(fight_rule="hoplite", die_rate=1),
        "horseman": dict(),
        "wolf": dict(fight=fixed(232, 8), fight_rule="tick", die_rate=1,
                     work={"stand": fixed(233, 8, ticks_per_frame=1), "lie": fixed(234, 8, ticks_per_frame=1)}),
    }
    assert over["rabble"]["fight"]["start"] == 6945, over["rabble"]["fight"]["start"]
    # sanctuary troops (bug 393; sim forces: good "amazon" for companies 31 / 32, "ares" for 33 / 34): the soldier
    # handlers draw them with an army's sprite set (FUN_004ffb70(army) loads it into the army slot 0x6400..)
    # - Artemis' Amazons (formation 0x1F / 0x20, rabble 0xB, fig_handler_rabble 0x004B31F0, army 4): the archer table
    #   of army 4 (0x006381EC walk, 0x006381F0 die, 0x006381F4 fight: Zeus_amazon groups 4 / 6 / 5); walk at
    #   anim_frame, which the rabble prologue wraps at 12 (frames 0..11 of 15); melee: frame attack_timer while < 12, else
    #   0; throwing (actions 10 / 0xB / 0x11 with a target): attack_timer 1..11, else frame 11 (+0x58); dying timer / 2
    # - Ares' warriors (formation 0x21 / 0x22, hoplite 0xC, fig_handler_hoplite 0x004B26B0, army 10): 0x6401 walk
    #   (sprite_anim_step rate 0), 0x6402 die min(timer, n) and 0x6403 fight (attack_timer if < n else 0) both drawn
    #   with direction 0 (FUN_005af770(.., 0)); the attack sound at attack_timer 1 (kind 0x14)
    am, ar = roles["enemy_archer_4"], roles["enemy_infantry_10"]
    roles["rabble:amazon"] = dict(file=am["file"], walk=dict(am["walk"], frames=12), die=am["die"],
                                  fight=dict({k: v for k, v in am["fight"].items() if k != "ticks_per_frame"}),
                                  fight_rule="amazon",
                                  work={"throw": dict({k: v for k, v in am["fight"].items() if k != "ticks_per_frame"},
                                                      ticks_per_frame=1, clamp=11, offset=1)},
                                  orig="Artemis' Amazons: rabble 0xB in formation 0x1F / 0x20, army 4 archer sprites")
    roles["hoplite:ares"] = dict(file=ar["file"], walk=ar["walk"], die=dict(ar["die"], dir0=True), die_rate=1,
                                 fight=ar["fight"], fight_rule="hoplite",
                                 orig="Ares' warriors: hoplite 0xC in formation 0x21 / 0x22, Zeus_AresWarriors 1 / 2 / 3")
    out = dict(
        overrides=over,
        note="tools/play_military.py; docs/play/military.md. roles merge into walkers.json roles (by-good for invaders: "
             "good = army<N>).",
        roles=roles, armies=armies, arrow=arrow, enemy_arrows=enemy_arrows,
        wolf=dict(stand=dict(file="SprMain", start=sm[233][0], dirs=8, frames=8, order="frame-major", dir_order=DIRS8),
                  lie=dict(file="SprMain", start=sm[234][0], dirs=8, frames=8, order="frame-major", dir_order=DIRS8),
                  fight=dict(file="SprMain", start=sm[232][0], dirs=8, frames=8, order="frame-major", dir_order=DIRS8)),
        standard=dict(file="Zeus_General", poles="SPR_STD_POLES", flags="SPR_FLAG_COMPANIES", god1="SPR_FLAG_GOD1",
                      god2="SPR_FLAG_GOD2", loan="SPR_FLAG_LOAN"))
    # texts of the military screens (docs/play/military.md "The exe's military screens"): 51 military, 138 company
    # names / types / morale words, 184 trireme panel, 269 trireme names, 283 the army dialog, 5 popups, 13 "Right-click to continue" (extracted/text/zeus_text.json)
    T = json.load(open(os.path.join(ROOT, "extracted", "text", "zeus_text.json")))
    out["texts"] = {g: T.get(g, []) for g in ("5", "13", "51", "138", "184", "269", "283")}
    p = os.path.join(ROOT, "data", "play", "military.json")
    json.dump(out, open(p, "w"), indent=1)
    print("wrote", p, len(roles), "roles")


if __name__ == "__main__":
    main()
