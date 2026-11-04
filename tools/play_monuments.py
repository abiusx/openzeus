"""Build data/play/monuments.json: how play mode draws sanctuaries, Poseidon pyramids and the palace
piece by piece (docs/play/monuments.md).

    python3 tools/play_monuments.py

Inputs: extracted/model/monument_images.json (per piece class: size, image per build stage, from
emulating the exe's class methods: tools/re_monument_images.py), extracted/sprites/*/atlas.json
(group rank -> atlas index), data/monuments.json + zeus-original/app/Model/*.txt (layouts; the sim's
data zeroes the sanctuary terrace elevations, the drawing needs them), and constants read from
Zeus.exe that are listed below with their addresses.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(ROOT, "extracted", "sprites")
OUT = os.path.join(ROOT, "data", "play", "monuments.json")
BANK_FILE = {4: "Zeus_General", 5: "Zeus_Terrain", 16: "SprAmbient", 52: "Poseidon_Loaded"}

# 0x00545940 (pyramid steps / monument ground): 8 neighbours N, NE, E, SE, S, SW, W, NW (grid offsets
# -228, -227, +1, +229, +228, +227, -1, -229 at 0x005D9888, view rotation 0) and the mask -> shape
# table at 0x006411C8 (256 ints; -1 = no image). Bit i set = neighbour i is higher.
NEIGHBOURS = [[0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1]]
SHAPES = {1: 5, 2: 6, 3: 5, 4: 7, 6: 7, 7: 9, 8: 0, 12: 7, 14: 7, 15: 9, 16: 1, 24: 1, 28: 10, 30: 10,
          32: 2, 48: 1, 56: 1, 60: 10, 62: 10, 64: 3, 96: 3, 112: 11, 120: 11, 128: 4, 129: 5, 131: 5,
          135: 9, 143: 9, 192: 3, 193: 8, 195: 8, 224: 3, 225: 8, 227: 8, 240: 11, 248: 11}
SANCTUARY_FILES = {84: "ZEUS_Pos", 85: "POSEIDON", 86: "DEMETER", 87: "APOLLO", 88: "ARTEMIS", 89: "ARES",
                   90: "APHRODITE", 91: "HERMES", 92: "ATHENA", 93: "HEPHAISTOS", 94: "DIONYSUS", 95: "HADES",
                   96: "HERA", 97: "ATLAS", 98: "POSEIDON_GRAND"}
from monuments import ROW  # noqa: E402  (same row syntax, incl. the 4 Zeus rows ending in ",)")

_atl = {}


def atlas(f):
    if f not in _atl:
        a = json.load(open(os.path.join(SPR, f, "atlas.json")))
        groups = sorted(a["groups"], key=lambda g: g["id"])
        # the loader keeps the groups whose first image is > 0, in order; image_id_from_packed_group
        # 0x0040FD10 counts ranks from 1 over those (SprAmbient has no system images: its rank 1 is id 0)
        ranks = [g for g in groups if g["first"] > 0]
        _atl[f] = (ranks, {i["index"]: i for i in a["images"]})
    return _atl[f]


def file_dir(name):
    real = {d.lower(): d for d in os.listdir(SPR)}
    return real[name.lower()]


def ref(img):
    """Emulator image (bank, rank, offset[, loaded file]) -> {file, index} of extracted/sprites."""
    if img is None:
        return None
    if "rule" in img:
        return {"steps": img["variant"]}
    f = file_dir(img["file"]) if "file" in img else BANK_FILE[img["bank"]]
    ranks, ims = atlas(f)
    g = ranks[img["rank"] - 1]
    idx = g["first"] + img["offset"]
    assert ims[idx]["group"] == g["name"], (img, g, ims[idx]["group"])
    if f == "Zeus_General" and g["name"] == "SPR_ROUGH_BASE":
        return "rough"
    return {"file": f, "index": idx}


def group(f, name):
    ranks, ims = atlas(f)
    g = next(g for g in ranks if g["name"] == name)
    n = 0
    while g["first"] + n in ims and ims[g["first"] + n]["group"] == name:
        n += 1
    return g["first"], n


def conan():
    """Large statues' carving (class +0x64 0x00554E60 -> Model/statue_conan.txt; drawn by +0x48 0x005407A0 /
    FUN_00430490 while the artisan works, who is hidden): per phase rows [x0, y0, x1, y1, look, distance, dirs n s e w
    = columns of views 0 2 4 6]; looks from table 0x005ED038 (SprMain rank = group_{rank-1}: group first, base, frames,
    stride). Small statues and the other classes have no conan file here (sanctuary_conan.txt: not mapped)."""
    path = os.path.join(ROOT, "zeus-original", "app", "Model", "statue_conan.txt")
    phases, cur = [], None
    for line in open(path, encoding="latin-1"):
        line = line.split(";")[0].strip()
        if not line.startswith("{"):
            continue
        v = [int(t) for t in line.strip("{}").split(",") if t.strip()]
        if len(v) == 1:
            cur = []
            phases.append(cur)
        else:
            cur.append(v)
    LOOKS = {0: ("group_22", 0, 12, 8), 1: ("group_24", 0, 7, 8), 2: ("group_25", 0, 7, 8), 3: ("group_23", 0, 8, 1),
             4: ("group_23", 7, 1, 1), 5: ("group_22", 10, 1, 1), 6: ("group_22", 0, 12, 2), 7: ("group_22", 0, 12, 8)}
    looks = {str(k): dict(first=group("SprMain", g)[0], base=b, frames=n, stride=st) for k, (g, b, n, st) in LOOKS.items()}
    return {"file": "SprMain", "phases": phases, "looks": looks,
            "classes": list(range(61, 109)) + list(range(125, 133)) + list(range(145, 149))}


def anim(f, first):
    """Animation constants of a group's first image from the raw .sg3 record (72 bytes; +0x1E frames,
    +0x20 stride between frames, +0x3A speed; play mode advances every 20*speed ms, buildings.md 3)."""
    import struct
    d = open(os.path.join(ROOT, "zeus-original", "app", "DATA", f + ".sg3"), "rb").read()
    rec = 72 if struct.unpack_from("<I", d, 4)[0] == 0xD6 else 64
    o = 680 + 40000 + rec * first
    frames, stride = struct.unpack_from("<hh", d, o + 0x1E)
    speed = d[o + 0x3A]
    return {"file": f, "first": first, "frames": frames, "stride": stride, "ms": 20 * speed if speed else 100}


def layout_rows(path):
    rows = []
    for line in open(path, encoding="latin-1"):
        m = ROW.search(line.split(";")[0])
        if m:
            rows.append(tuple(int(v) for v in m.groups()[:4]))
    x0, y0 = min(r[0] for r in rows), min(r[1] for r in rows)
    return [(x - x0, y - y0, c, e) for x, y, c, e in rows]


def layouts(classes):
    mon = json.load(open(os.path.join(ROOT, "data", "monuments.json")))
    out = {}
    for key, L in mon.items():
        zid = L["zeus_id"]
        if zid in SANCTUARY_FILES:
            kind = "sanctuary"
            rows = layout_rows(os.path.join(ROOT, "zeus-original", "app", "Model", f"Sanctuary_{SANCTUARY_FILES[zid]}.txt"))
            assert [r[:3] for r in rows] == [tuple(p[:3]) for p in L["pieces"]], key
            elev = [r[3] for r in rows]
        else:
            kind = "palace" if key == "palace" else "pyramid"
            elev = [p[3] for p in L["pieces"]]
        out[key] = {"kind": kind, "w": L["w"], "h": L["h"], "elev": elev}
    return out


def main():
    emu = json.load(open(os.path.join(ROOT, "extracted", "model", "monument_images.json")))
    classes = {}
    files = set()
    for cid, e in emu["classes"].items():
        c = {"size": e["size"], "phases": [ref(p["img"]) for p in e["phases"]]}
        if "poseidon_phases" in e:
            c["poseidon_phases"] = [ref(p["img"]) for p in e["poseidon_phases"]]
        # placement orientation 1..3 (b+0x9C; R key, bugs.md 133): the classes whose image depends on it
        for k in ("orient_phases", "orient_poseidon_phases"):
            if k in e:
                c[k] = {o: [ref(p["img"]) for p in ph] for o, ph in e[k].items()}
        # turned views 2/4/6 (docs/play/rotation.md): {view: {orientation: phases}} where the image reads the view
        for k in ("view_phases", "view_poseidon_phases"):
            if k in e:
                c[k] = {v: {o: [ref(p["img"]) for p in ph] for o, ph in d.items()} for v, d in e[k].items()}
        if int(cid) >= 1000:
            c = {"size": 1, "ground": True}          # extras: terrain tiles (0x0053C9F0), ground by the step rule
        if e["phases"] and e["phases"][-1]["flags"] & 4 and int(cid) < 1000:
            c["walkable"] = True
        classes[cid] = c
        for ph in c.get("phases", []) + c.get("poseidon_phases", []) + [
                q for k in ("orient_phases", "orient_poseidon_phases") for v in c.get(k, {}).values() for q in v] + [
                q for k in ("view_phases", "view_poseidon_phases") for d in c.get(k, {}).values() for v in d.values() for q in v]:
            if isinstance(ph, dict) and "file" in ph:
                files.add(ph["file"])
    # pyramid context check: base stages are the block images, then the class's own phases
    blocks_first, _ = group("Poseidon_Loaded", "SPR_POSEIDON_PYRAMID_BLOCKS")
    for cid, p in emu["pyramid"].items():
        E = (p["elev"] // 2) * 4
        for r in p["rows"]:
            got = ref(r["img"])
            s = r["stage"]
            if 0 < s <= E:
                want = {"file": "Poseidon_Loaded", "index": blocks_first + (4 if s % 4 == 0 else (s - 1) % 4)}
                assert got == want, (cid, s, got, want)
            elif s > E:
                assert got == classes[cid]["phases"][s - E], (cid, s, got)
    rough_first, rough_n = group("Zeus_General", "SPR_ROUGH_BASE")
    st = {n: group("Poseidon_Loaded", n)[0] for n in (
        "SPR_POSEIDON_PYRAMID_STEPS", "SPR_POSEIDON_PYRAMID_STEP_VARIANTS", "SPR_POSEIDON_PYRAMID_STEPS_BLACK",
        "SPR_POSEIDON_PYRAMID_STEP_VARIANTS_BLACK", "SPR_POSEIDON_PYRAMID_STEPS_BASE",
        "SPR_POSEIDON_PYRAMID_STEP_VARIANTS_BASE", "SPR_POSEIDON_PYRAMID_STEPS_BLACK_BASE",
        "SPR_POSEIDON_PYRAMID_STEP_VARIANTS_BLACK_BASE", "SPR_POSEIDON_PYRAMID_BLOCKS_BLACK",
        "SPR_IMPROVED_TRANSITION_STEPS")}
    sa = atlas("SprAmbient")[0]
    out = {
        "doc": "docs/play/monuments.md (generated by tools/play_monuments.py; do not edit by hand)",
        "mode": "zeus",
        "files": sorted(files | {"Zeus_General", "Zeus_Terrain", "Poseidon_Loaded", "SprAmbient"}),
        "pixels_per_height": 30,
        "rough": {"file": "Zeus_General", "first": rough_first, "count": rough_n},
        "blocks": {"file": "Poseidon_Loaded", "first": blocks_first, "black_first": st["SPR_POSEIDON_PYRAMID_BLOCKS_BLACK"]},
        "steps": {
            "neighbours": NEIGHBOURS, "shapes": {str(k): v for k, v in SHAPES.items()},
            "full": {"file": "Poseidon_Loaded",
                     "plain": [st["SPR_POSEIDON_PYRAMID_STEPS"], st["SPR_POSEIDON_PYRAMID_STEP_VARIANTS"],
                               st["SPR_POSEIDON_PYRAMID_STEPS_BLACK"], st["SPR_POSEIDON_PYRAMID_STEP_VARIANTS_BLACK"]],
                     "base": [st["SPR_POSEIDON_PYRAMID_STEPS_BASE"], st["SPR_POSEIDON_PYRAMID_STEP_VARIANTS_BASE"],
                              st["SPR_POSEIDON_PYRAMID_STEPS_BLACK_BASE"], st["SPR_POSEIDON_PYRAMID_STEP_VARIANTS_BLACK_BASE"]]},
            "half": {"file": "Zeus_Terrain", "first": group("Zeus_Terrain", "SPR_TRANSITION_STEPS")[0],
                     "improved": {"file": "Poseidon_Loaded", "first": st["SPR_IMPROVED_TRANSITION_STEPS"], "shapes": [4, 5, 6]}},
        },
        "anims": {
            "priestesses": dict(anim("SprAmbient", sa[61]["first"]), classes=[0, 110, 158], dx=58, dy=26,
                                when="root employees > 0 (exe 0x0044EE80, class method +0xF8)"),
            "firepot": dict(anim("SprAmbient", sa[68]["first"]), classes=[111, 112, 113, 114, 115, 116, 155, 156, 157, 162, 163],
                            dx=29, dy=30, when="pyramid: complete; sanctuary: while its god is in the city (exe 0x005406E0, 0x0055B6E0)"),
            # exe (-5, 40) from animation_draw's point, which for the palace is 119 px right of the front piece's
            # left-tile point (oracle runs/palace/c.bmp: front image top-left (60, 357), guard frame 3023 top-left
            # (120, 482), anchor (54, 53) -> anchor at image + (114, 178); bugs.md 93)
            "palace_guard": dict(anim("SprAmbient", sa[90]["first"]), classes=[3], dx=-5 + 119, dy=40,
                                 when="always (exe animation_draw 0x0045D140 case 0x75)"),
            "conan": conan(),
            "altar_sacrifice": {"classes": [2], "status": "not mapped: plays during a sacrifice (gods are out of scope)",
                                "groups": "SprAmbient rank 17/18, Poseidon_Loaded rank 67 by altar byte +0x9F (exe 0x005367B0)"},
        },
        "classes": classes,
        "layouts": layouts(classes),
    }
    for k in ("149", "150"):                          # observatory, museum: ordinary building animation
        ph = classes[k]["phases"][-1]
        im = atlas(ph["file"])[1][ph["index"]]
        classes[k]["anim"] = {"file": ph["file"], "start": ph["index"] + 1, "count": im["anim_frames"],
                              "dx": im["anchor_x"], "dy": im["anchor_y"]}
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    print("wrote", OUT, os.path.getsize(OUT), "bytes;", len(classes), "classes,", len(out["layouts"]), "layouts; files:",
          ", ".join(out["files"]))


if __name__ == "__main__":
    main()
