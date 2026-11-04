"""Audit of play mode's figure animation blocks against the sprite data (bugs.md 393).

Every block (a dict with `start` and `frames`) in data/play/walkers.json, heroes.json, gods.json, military.json and
contestants.json is looked up in extracted/sprites/<file>/atlas.json: the block's first image's `anim_frames` (the
.sg3 record +0x1E, the count the exe's sprite_anim_step / walker handlers wrap at) and the size of its group
(images / dirs). Prints every block whose `frames` differs from the data's count, and a summary.

Usage: python3 tools/walker_frames_audit.py [--all]     (--all: list every block, matching or not)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPR = os.path.join(ROOT, "extracted", "sprites")
FILES = ["walkers", "heroes", "gods", "military", "contestants"]
_atlas = {}


def atlas(f):
    if f not in _atlas:
        p = os.path.join(SPR, f, "atlas.json")
        a = json.load(open(p)) if os.path.exists(p) else None
        if a:
            a["byidx"] = {im["index"]: im for im in a["images"]}
            firsts = sorted(g["first"] for g in a["groups"])
            a["gsize"] = {}
            for i, s in enumerate(firsts):
                a["gsize"][s] = (firsts[i + 1] if i + 1 < len(firsts) else len(a["images"]) + 1) - s
            a["gfirst"] = firsts
        _atlas[f] = a
    return _atlas[f]


def group_of(a, idx):
    import bisect
    i = bisect.bisect_right(a["gfirst"], idx) - 1
    return a["gfirst"][i] if i >= 0 else None


def blocks(o, path, file):
    if isinstance(o, dict):
        f = o.get("file", file)
        if "start" in o and "frames" in o and isinstance(o["start"], int):
            yield path, f, o
        for k, v in o.items():
            if isinstance(v, (dict, list)):
                yield from blocks(v, path + "." + str(k), f)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from blocks(v, path + f"[{i}]", file)


def main():
    show_all = "--all" in sys.argv
    n = bad = 0
    for name in FILES:
        p = os.path.join(ROOT, "data", "play", name + ".json")
        if not os.path.exists(p):
            continue
        d = json.load(open(p))
        for path, f, b in blocks(d.get("roles", d), name, d.get("file")):
            a = atlas(f) if f else None
            if not a:
                continue
            im = a["byidx"].get(b["start"])
            if im is None:
                continue
            n += 1
            af = im.get("anim_frames", 0)
            g0 = group_of(a, b["start"])
            dirs = b.get("dirs", 8) or 1
            gn = a["gsize"].get(g0, 0) // dirs if g0 is not None else 0
            ok = af in (0, b["frames"]) or b.get("frames_note")
            if not ok:
                bad += 1
            if show_all or not ok:
                print(f"{'  ' if ok else '!!'} {path}: {f} start {b['start']} frames {b['frames']} dirs {dirs}"
                      f" | anim_frames {af}, group {g0} size/dirs {gn}")
    print(f"{n} blocks, {bad} differ from the sprite data's anim_frames")


if __name__ == "__main__":
    main()
