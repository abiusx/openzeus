"""The README's gameplay animation, step 2: frames from tools/readme_gif.mjs -> an animated GIF.

  python3 tools/readme_gif.py FRAMEDIR OUT.gif [--width 960] [--ms 100] [--colors 256]

Scales the frames to --width (Lanczos), builds one shared palette from a sample of the frames (so colours don't
flicker between frames), and writes a looping GIF with --ms per frame. Keep it under 5 MB (the public export's limit).
"""
import argparse
import glob
import os

from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames")
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--ms", type=int, default=100)
    ap.add_argument("--colors", type=int, default=256)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.frames, "f*.png")))
    if not files:
        raise SystemExit(f"no frames in {a.frames}")
    ims = []
    for f in files:
        im = Image.open(f).convert("RGB")
        h = round(im.height * a.width / im.width)
        ims.append(im.resize((a.width, h), Image.LANCZOS))
    # one palette for every frame: quantize a strip of sampled frames together
    step = max(1, len(ims) // 6)
    sample = ims[::step]
    strip = Image.new("RGB", (a.width, sum(i.height for i in sample)))
    y = 0
    for i in sample:
        strip.paste(i, (0, y))
        y += i.height
    pal = strip.quantize(colors=a.colors, method=Image.Quantize.MEDIANCUT)
    q = [i.quantize(palette=pal, dither=Image.Dither.NONE) for i in ims]
    q[0].save(a.out, save_all=True, append_images=q[1:], duration=a.ms, loop=0, optimize=True, disposal=1)
    print(f"{a.out}: {len(q)} frames, {a.width}x{q[0].height}, {os.path.getsize(a.out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
