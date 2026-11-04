"""data/play/gods.json: play-mode pictures of gods and priests (viewer/play/gods.js; sim/gods).

    python3 tools/play_gods.py        (after tools/build_gods.py and tools/sg3.py's extracted/sprites)

God figure 0x43: one sprite file per god (PTR_s_Zeus_Zeus_0063a88c: Zeus_Zeus .. Poseidon_Atlas); the handler picks
an action group per action (byte table 0x004C8704 -> 0x004C86D0: 0 walk, 1 vanish, 2 attack, 3 appear, 4 cast)
and the god's sprite group for it from 0x0063A934 (god x 5; 0x800 = not directional). A group's frame count is the
first sprite's anim_frames (FUN_004EA4E0). Directional groups are frame-major (8 directions per frame, NE first,
as SprMain's walkers; seen: consecutive images alternate width). Walk and 0x0B vanish: one frame a tick; appear,
cast, attack and the fights' vanish at rate 100: data/gods.json frame_ticks per frame (docs/logic/religion.md
"Animation", bug 393).
Priest figure 0x41: SprMain packed groups 0x6692 (walk, group_145: 8 x 12) and 0x6693 (die, group_146: 8).
Bolts (figures 0x2D / 0x34; walker_player_missile 0x004BACE0 and fig_handler_enemy_missile 0x004BD970, the same switch
on the god figure's resource): packed "destruction" groups (collection 17; FUN_005af770: entry rank - 1 = atlas group)
Zeus 0x2230, Poseidon 0x223A, Demeter 0x2234, Apollo 0x2229, Artemis 0x2232, Aphrodite 0x223B, Hermes / Hera 0x2239,
Athena 0x2233, Dionysus / Atlas 0x2235, else 0x2231; frame-major, 8 directions (the 32-way angle / 4), the frame by
FUN_005af8c0 (one a tick, ours).
Followers (figure 0x47 "Entranced", fig_handler_piper_follower 0x004C9F30): the entranced walker's own type's walk
group (figure_type_table +0x1C), Dionysus' own (resource 0x44): monster_anim_info(0x11) = Zeus_Satyr group 0x6201 =
its first group. Walkers carry good = the original role.
Output: {"roles": {"god": by-good map, "god_<name>": {file, walk, work: {appear, vanish, attack, cast}}, "priest",
"entranced": by-good map, "follower_satyr"}, "bolts": [14 x {file, start, frames, dirs}]}
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRS = ["NE", "E", "SE", "S", "SW", "W", "NW", "N"]


def atlas(f):
    a = json.load(open(os.path.join(ROOT, "extracted", "sprites", f, "atlas.json")))
    return [g["first"] for g in a["groups"]], {i["index"]: i for i in a["images"]}


# god sound groups (FUN_004DC180: god -> group, FUN_005A6FE0(fig, group, slot)); their files registered by
# FUN_005A4CA0 (FUN_005A4C70(group, "audio\\wavs\\G_<god>_<kind>.wav", slot)): 9 mat (appear), 10 demat (vanish),
# 1..4 atk, 7 hit, 11 sanctify (blessing / help), 12 curse, 13 G_miss (a bolt that hits nothing)
SOUND_NAMES = ["zeus", "poseidon", "demeter", "apollo", "artemis", "ares", "aphrodite", "hermes", "athena",
               "hephaestus", "dionysus", "hades", "hera", "atlas"]
SLOTS = {"mat": 9, "demat": 10, "atk1": 1, "atk2": 2, "atk3": 3, "atk4": 4, "hit": 7, "sanctify": 11, "curse": 12}


def sounds():
    exe = open(os.path.join(ROOT, "zeus-original", "app", "Zeus.exe"), "rb").read().lower()
    wd = os.path.join(ROOT, "zeus-original", "app", "Audio", "Wavs")
    disk = {f.lower(): f for f in os.listdir(wd)}
    out = []
    for name in SOUND_NAMES:
        row = {}
        for kind in SLOTS:
            f = f"g_{name}_{kind}.wav"
            if ("audio\\wavs\\" + f).encode() in exe and f in disk:
                k = "atk" if kind.startswith("atk") else kind
                v = "Wavs/" + disk[f]
                if k == "atk":
                    row.setdefault("atk", []).append(v)
                else:
                    row[k] = v
        row["miss"] = "Wavs/" + disk["g_miss.wav"] if "g_miss.wav" in disk else None
        out.append(row)
    return out


def main():
    T = json.load(open(os.path.join(ROOT, "data", "gods.json")))
    roles = {"god": {"by": "good", "map": {g: f"god_{g}" for g in T["gods"]}, "fallback_role": "god_zeus",
                     "orig": "FIG_GOD (type 67): picture file by god (figure +0x0B)"}}
    for gi, name in enumerate(T["gods"]):
        f = T["sprite_files"][gi]
        first, im = atlas(f)
        blocks = []
        for k in range(5):
            v = T["sprite_groups"][gi][k]
            sg, flat = v & ~0x800, bool(v & 0x800)
            n = im[first[sg]]["anim_frames"] or 1
            b = dict(file=f, start=first[sg], dirs=1 if flat else 8, frames=n,
                     order="frame" if flat else "frame-major")
            if not flat:
                b["dir_order"] = DIRS
            blocks.append(b)
        walk, vanish, attack, appear, cast = blocks
        # rate-100 looks (bug 393): one frame per frame_ticks ticks from the look's start (data/gods.json, sim
        # gods.attack.tpf); rate 0 (one a tick): 0x0B vanish ("vanish"), the duel 0x3C ("duel")
        ft = T["frame_ticks"][gi]
        roles[f"god_{name}"] = dict(file=f, walk=walk, work=dict(
            appear=dict(appear, clamp=appear["frames"] - 1, ticks_per_frame=ft[3]),
            vanish=dict(vanish, clamp=vanish["frames"] - 1),
            vanish_gated=dict(vanish, clamp=vanish["frames"] - 1, ticks_per_frame=ft[1]),
            attack=dict(attack, ticks_per_frame=ft[2]), cast=dict(cast, ticks_per_frame=ft[4]), duel=attack),
            orig=f"FIG_GOD {name}: {f} groups {T['sprite_groups'][gi]}",
            # outside a work look the god's action is a walk-group one (rate 0: sprite_anim_step +1 every tick,
            # standing or stepping; figure_god_handler 0x004C5D40 tail, bug 393); the default case (frame 0, still)
            # covers only actions the god passes through in a tick (0..3, 0x12, 0x1E, 0x31, 0x33, 0x35, 0x36,
            # 0x3D, 0x3E, 0x5A)
            frame_rule="tick")
    roles["priest"] = dict(file="SprMain", walk=dict(start=8105, dirs=8, frames=12, order="frame-major", dir_order=DIRS),
                           die=dict(start=8201, dirs=1, frames=8, order="frame"), orig="FIG_PRIEST (type 65): 0x6692/0x6693")
    BOLT = {0: 0x2230, 1: 0x223A, 2: 0x2234, 3: 0x2229, 4: 0x2232, 6: 0x223B, 7: 0x2239, 12: 0x2239, 8: 0x2233,
            10: 0x2235, 13: 0x2235}
    dfirst, dim = atlas("destruction")
    bolts = []
    for gi in range(14):
        packed = BOLT.get(gi, 0x2231)
        assert packed >> 9 == 17
        first = dfirst[(packed & 0x1FF) - 1]
        # fig_handler_enemy_missile / walker_player_missile, type 0x43 branch: sprite_anim_step(group, .., 100): rate 100
        from play_buildings import raw_speed, rate100_ticks
        bolts.append(dict(file="destruction", start=first, frames=dim[first]["anim_frames"] or 1, dirs=8,
                          packed=hex(packed), ticks_per_frame=rate100_ticks(raw_speed("destruction", first))))
    sfirst, sim_ = atlas("zeus_satyr")
    roles["follower_satyr"] = dict(file="zeus_satyr", walk=dict(file="zeus_satyr", start=sfirst[0], dirs=8,
                                   frames=sim_[sfirst[0]]["anim_frames"] or 1, order="frame-major", dir_order=DIRS),
                                   orig="FIG_ENTRANCED (type 71), resource 0x44: Zeus_Satyr 0x6201")
    W = json.load(open(os.path.join(ROOT, "data", "play", "walkers.json")))["roles"]
    roles["entranced"] = {"by": "good", "map": dict({r: r for r in W if not W[r].get("by")}, satyr="follower_satyr"),
                          "fallback_role": "immigrant", "orig": "FIG_ENTRANCED (type 71): the walker's own walk group"}
    # a helping god's figures (sim/gods gifts.py): Hades' miners (figure 0x3E, figure_miner: the silver digging
    # look) and Athena's growers (figure 5: tending olives), role god_helper, good = the walkers.json role
    roles["god_helper"] = {"by": "good", "map": {"miner": "miner", "grower": "grower"}, "fallback_role": "miner",
                           "orig": "FIG_MINER (62) / FIG_GROWER (5) sent by Hades / Athena"}
    out = {"_doc": "tools/play_gods.py (docs/play/gods.md)", "roles": roles, "bolts": bolts, "sounds": sounds()}
    with open(os.path.join(ROOT, "data", "play", "gods.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"data/play/gods.json: {len(roles)} roles")


if __name__ == "__main__":
    main()
