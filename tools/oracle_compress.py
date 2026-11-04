"""Compress the oracle's runs in place: state dumps re/oracle/runs/*/dump/tick_NNNNNN.bin -> tick_NNNNNN.bin.zst,
and with --shots the screenshots re/oracle/runs/**/*.bmp -> lossless WebP (*.webp).

A dump is ~4.2 MB of raw memory and compresses ~38x at zstd level 9 (~110 KB, ~10 ms). Every reader goes through
tools/oracle.py (read_dump / dump_files / Dump), which reads both forms; a .bin path that no longer exists falls back
to its .zst, so paths cited in docs keep working. Each file is written to a temporary name, read back and compared
with the original, renamed, and only then is the .bin removed. Python 3.14 (compression.zstd), no other dependency.
New runs keep writing plain .bin (zeus-run); compress them with this tool afterwards. docs/re/oracle.md "Disk".
Shots (--shots): an 800x600 BMP (1.44 MB) is ~340 KB as lossless WebP (Pillow, quality 50 = effort, method 4);
each is decoded back and compared pixel by pixel before the .bmp goes; oracle.shot() resolves cited .bmp paths.

    python3 tools/oracle_compress.py [RUN ...]       # default: every run; -j N workers (default: CPU count)
    python3 tools/oracle_compress.py --shots [RUN ...]  # the screenshots instead
    python3 tools/oracle_compress.py --check RUN     # count plain / compressed dumps
"""
import argparse
import glob
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from compression import zstd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "re", "oracle", "runs")
LEVEL = 9


def one(path):
    data = open(path, "rb").read()
    packed = zstd.compress(data, LEVEL)
    tmp = path + ".zst.tmp"
    with open(tmp, "wb") as f:
        f.write(packed)
    if zstd.decompress(open(tmp, "rb").read()) != data:
        os.remove(tmp)
        return path, 0, 0, "verify failed"
    os.replace(tmp, path + ".zst")
    os.remove(path)
    return path, len(data), len(packed), ""


def one_shot(path):
    from PIL import Image
    im = Image.open(path)
    im.load()
    rgb = im.convert("RGB")
    tmp = path[:-4] + ".webp.tmp"
    rgb.save(tmp, "WEBP", lossless=True, quality=50, method=4)
    back = Image.open(tmp)
    back.load()
    if back.convert("RGB").tobytes() != rgb.tobytes() or im.mode not in ("RGB", "P", "L"):
        os.remove(tmp)
        return path, 0, 0, f"verify failed (mode {im.mode})"
    n = os.path.getsize(path)
    os.replace(tmp, path[:-4] + ".webp")
    os.remove(path)
    return path, n, os.path.getsize(path[:-4] + ".webp"), ""


def runs(names):
    return [os.path.join(RUNS, n) for n in names] if names else sorted(glob.glob(os.path.join(RUNS, "*")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="*")
    ap.add_argument("-j", type=int, default=os.cpu_count())
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--shots", action="store_true")
    a = ap.parse_args()
    files = []
    for r in runs(a.runs):
        if a.shots:
            files += glob.glob(os.path.join(r, "**", "*.bmp"), recursive=True)
            continue
        plain = glob.glob(os.path.join(r, "dump", "tick_*.bin"))
        if a.check:
            z = glob.glob(os.path.join(r, "dump", "tick_*.bin.zst"))
            print(f"{os.path.basename(r)}: {len(plain)} plain, {len(z)} compressed")
        files += plain
    if a.check:
        return
    for t in glob.glob(os.path.join(RUNS, "*", "dump", "*.zst.tmp")) + \
            glob.glob(os.path.join(RUNS, "**", "*.webp.tmp"), recursive=True):   # an interrupted earlier pass
        os.remove(t)
    before = after = n = 0
    errors = []
    with ProcessPoolExecutor(a.j) as ex:
        for k, (p, b, c, err) in enumerate(ex.map(one_shot if a.shots else one, sorted(files), chunksize=8), 1):
            if err:
                errors.append(f"{p}: {err}")
                continue
            before, after, n = before + b, after + c, n + 1
            if k % 500 == 0:
                print(f"{k}/{len(files)}  {before / 1e9:.2f} GB -> {after / 1e9:.3f} GB", flush=True)
    print(f"done: {n} {'shots' if a.shots else 'dumps'}, {before / 1e9:.2f} GB -> {after / 1e9:.3f} GB" + (f", {len(errors)} errors" if errors else ""))
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
