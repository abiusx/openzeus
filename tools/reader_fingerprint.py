"""Fingerprint everything our format readers (tools/sg3.py, tools/mapfile.py) decode from the original files.

One line per item: a sha256 of the decoded result (or the error). Run it before and after changing a reader and
diff the two outputs: identical files = the readers give identical results on every input.
  sg3   every .sg3 under zeus-original/app: header/bitmaps/groups/image records, then each image's decoded RGBA
        array (shape + bytes), or its error
  map   every .map/.sav/.pak/.set under zeus-original/app: read_file (header + each block's bytes), for .pak/.set
        pak_map_offsets and pak_map(0..4), and per container scenario_slots of every point table + scenario_origin
Usage:
    python3 tools/reader_fingerprint.py OUT.txt [sg3|map ...]
"""
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
APP = os.path.join(ROOT, "zeus-original", "app")


def h(b):
    return hashlib.sha256(b).hexdigest()[:24]


def files(exts):
    out = []
    for d, _, fs in os.walk(APP):
        out += [os.path.join(d, f) for f in fs if os.path.splitext(f)[1].lower() in exts]
    return sorted(out)


def sg3_lines(path):
    import sg3
    rel = os.path.relpath(path, APP)
    try:
        s = sg3.Sg3(path)
    except Exception as e:
        return [f"sg3 {rel} ERROR {type(e).__name__}: {e}"]
    meta = json.dumps(dict(version=s.version, max=s.max_images, n=s.num_images, nb=s.num_bitmaps,
                           bitmaps=s.bitmaps, groups=s.groups, images=s.images), sort_keys=True)
    out = [f"sg3 {rel} meta {h(meta.encode())}"]
    for im in s.images[1:]:
        try:
            a = s.decode(im)
            r = "empty" if a is None else f"{a.shape} {a.dtype} {h(a.tobytes())}"
        except Exception as e:
            r = f"ERROR {type(e).__name__}: {e}"
        out.append(f"sg3 {rel} {im['index']} group={s.group_of(im['index'])} {r}")
    return out


def map_lines(path):
    import mapfile
    rel = os.path.relpath(path, APP)
    out = []

    def blocks_desc(tag, hdr, blocks):
        out.append(f"map {rel} {tag} hdr {json.dumps(hdr, sort_keys=True)}")
        for b in blocks:
            meta = {k: v for k, v in b.items() if k != "data"}
            out.append(f"map {rel} {tag} block {json.dumps(meta, sort_keys=True)} {h(b['data'])}")
        try:
            pts = {k: mapfile.scenario_slots(blocks, k) for k in mapfile._POINT_TABLES}
            out.append(f"map {rel} {tag} points {h(json.dumps(pts).encode())} origin {mapfile.scenario_origin(blocks)}")
        except Exception as e:
            out.append(f"map {rel} {tag} points ERROR {type(e).__name__}: {e}")
    try:
        for m, (hdr, blocks) in enumerate(mapfile.read_file(path)):
            blocks_desc(f"c{m}", hdr, blocks)
    except Exception as e:
        out.append(f"map {rel} read_file ERROR {type(e).__name__}: {e}")
    if path.lower().endswith((".pak", ".set")):
        d = open(path, "rb").read()
        try:
            out.append(f"map {rel} offsets {mapfile.pak_map_offsets(d)}")
            for i in range(5):
                r = mapfile.pak_map(path, i)
                if r is None:
                    out.append(f"map {rel} pak_map {i} None")
                else:
                    blocks_desc(f"p{i}", *r)
        except Exception as e:
            out.append(f"map {rel} pak_map ERROR {type(e).__name__}: {e}")
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return
    kinds = argv[1:] or ["sg3", "map"]
    jobs = []
    if "sg3" in kinds:
        jobs += [(sg3_lines, p) for p in files({".sg3"})]
    if "map" in kinds:
        jobs += [(map_lines, p) for p in files({".map", ".sav", ".pak", ".set"})]
    lines = []
    with ProcessPoolExecutor() as ex:
        for r in ex.map(_run, jobs):
            lines += r
    with open(argv[0], "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"{len(jobs)} files, {len(lines)} items -> {argv[0]}")


def _run(job):
    fn, p = job
    return fn(p)


if __name__ == "__main__":
    main(sys.argv[1:])
