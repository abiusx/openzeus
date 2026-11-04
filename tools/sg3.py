"""Zeus sprite extractor: .sg3 index + .555 pixels -> PNG files + JSON atlas.

Format: docs/formats.md "Sprite files (.sg3 + .555)".

Usage:
    python3 tools/sg3.py info   FILE.sg3
    python3 tools/sg3.py export DATA_DIR OUT_DIR [NAME ...]   all .sg3 in DATA_DIR (or only NAMEs)

Output: OUT_DIR/<sg3 name>/<group>/<image index>.png and OUT_DIR/<sg3 name>/atlas.json.
"""
import json
import os
import struct
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image as PILImage

# File layout (docs/formats.md): header, 200 bitmap records, image records, 300 group names.
HEADER_BYTES = 680
GROUP_FIRST_AT = 80              # u16 first image of each group, inside the header
N_BITMAPS, BITMAP_BYTES = 200, 200
N_GROUPS, GROUP_NAME_BYTES = 300, 48
RECORD_BYTES = {0xD5: 64, 0xD6: 72}
# image record up to byte 57: offset, length, uncompressed length, ?, mirror delta, width, height, (6), frames, (2),
# anchor x, anchor y, (12), type, compressed, external, has_top, (1), iso size, bitmap
IMAGE_RECORD = struct.Struct("<IIIIihh6xH2xhh12xBBBBxBB")
ALPHA_LEN_AT = 68                # u32, 0xD6 records only
DIAMOND_W, DIAMOND_H = 58, 30    # one iso tile; tiles sit 60 px apart across, 15 down
ISO_KEY = 0x03E0                 # pure green in an iso base: not drawn
TRANSPARENT = 0xF81F             # magenta in uncompressed images
SKIP = 255                       # run byte: the next byte is a count of pixels to skip


class Sg3Error(Exception):
    """The file does not decode as documented."""


def _text(raw):
    return raw.partition(b"\0")[0].decode("cp1252")


def _diamond_mask():
    """(30, 58) bool: the pixels of one iso tile. Row y holds 58 - 2 * (|2y - 29| - 1) pixels, centred."""
    rows = np.arange(DIAMOND_H)[:, None]
    cols = np.arange(DIAMOND_W)[None, :]
    inset = np.abs(2 * rows - (DIAMOND_H - 1)) - 1
    return (cols >= inset) & (cols < DIAMOND_W - inset)


_DIAMOND = _diamond_mask()
_DIAMOND_PIXELS = int(_DIAMOND.sum())   # 900


class Sg3:
    def __init__(self, path):
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        with open(path, "rb") as f:
            raw = f.read()
        head = struct.unpack_from("<6I", raw)
        self.version, self.max_images, self.num_images, self.num_bitmaps = head[1], head[3], head[4], head[5]
        if self.version not in RECORD_BYTES:
            raise Sg3Error(f"{path}: unknown version {self.version:#x}")
        rec_len = RECORD_BYTES[self.version]
        records_at = HEADER_BYTES + N_BITMAPS * BITMAP_BYTES
        groups_at = records_at + self.max_images * rec_len
        if groups_at + N_GROUPS * GROUP_NAME_BYTES != len(raw):
            raise Sg3Error(f"{path}: unexpected size {len(raw)}")

        self.bitmaps = []
        for b in range(self.num_bitmaps):
            at = HEADER_BYTES + b * BITMAP_BYTES
            width, height, count, first, last = struct.unpack_from("<5I", raw, at + 116)
            self.bitmaps.append(dict(file=_text(raw[at:at + 65]), comment=_text(raw[at + 65:at + 116]),
                                     width=width, height=height, images=count, first=first, last=last))

        self.images = [self._record(raw, records_at + k * rec_len, k, rec_len) for k in range(self.num_images + 1)]

        firsts = struct.unpack_from(f"<{N_GROUPS}H", raw, GROUP_FIRST_AT)
        self.groups = []
        for g, first in enumerate(firsts):
            at = groups_at + g * GROUP_NAME_BYTES
            label = _text(raw[at:at + GROUP_NAME_BYTES])
            if first or label:   # unused slots have neither
                self.groups.append(dict(id=g, name=label or f"group_{g}", first=first))
        self._files = {}
        self._dir = None

    @staticmethod
    def _record(raw, at, index, rec_len):
        (offset, length, ulen, _, mirror, width, height, frames, ax, ay,
         kind, packed, external, top, iso, bitmap) = IMAGE_RECORD.unpack_from(raw, at)
        alpha = struct.unpack_from("<I", raw, at + ALPHA_LEN_AT)[0] if rec_len > ALPHA_LEN_AT else 0
        return dict(index=index, offset=offset, length=length, ulen=ulen, invert=mirror, width=width,
                    height=height, anim_frames=frames, anchor_x=ax, anchor_y=ay, type=kind, compressed=packed,
                    external=external, has_top=top, iso_size=iso, bitmap=bitmap, alpha_len=alpha)

    def group_of(self, index):
        """Name of the group holding image `index`: the one with the highest start <= index (later id on ties)."""
        owners = [(g["first"], g["id"], g["name"]) for g in self.groups if g["first"] <= index]
        return max(owners)[2] if owners else "ungrouped"

    def _pixel_data(self, im):
        """Bytes of the .555 file an image's pixels live in (case-insensitive name, read once)."""
        if im["external"]:
            wanted = os.path.splitext(self.bitmaps[im["bitmap"]]["file"])[0] + ".555"
        else:
            wanted = self.name + ".555"
        if wanted not in self._files:
            folder = os.path.dirname(self.path)
            if self._dir is None:
                self._dir = {entry.lower(): entry for entry in os.listdir(folder)}
            actual = self._dir.get(wanted.lower())
            if actual is None:
                raise Sg3Error(f"missing pixel file {wanted}")
            with open(os.path.join(folder, actual), "rb") as f:
                self._files[wanted] = f.read()
        return self._files[wanted]

    def decode(self, im):
        """RGBA uint8 array (h, w, 4), or None for an empty image."""
        src = self.images[im["index"] + im["invert"]] if im["invert"] else im
        w, h = src["width"], src["height"]
        if w <= 0 or h <= 0 or src["length"] == 0:
            return None
        data = self._pixel_data(src)
        start = src["offset"] - 1 if src["external"] else src["offset"]
        split = start + src["length"]
        stop = split + src["alpha_len"]
        if stop > len(data):
            raise Sg3Error(f"image {im['index']}: data past end of file")
        body, mask = data[start:split], data[split:stop]

        rgb = np.zeros((h, w), np.uint16)
        shown = np.zeros((h, w), bool)
        if src["type"] == 30:
            _paint_iso_base(rgb, shown, body[:src["ulen"]], src["iso_size"], src["index"])
            if len(body) > src["ulen"]:
                _paint_runs(rgb.reshape(-1), shown.reshape(-1), body[src["ulen"]:])
        elif src["compressed"]:
            _paint_runs(rgb.reshape(-1), shown.reshape(-1), body)
        else:
            if len(body) != 2 * w * h:
                raise Sg3Error(f"image {im['index']}: bad plain length")
            rgb[:] = np.frombuffer(body, "<u2").reshape(h, w)
            shown[:] = rgb != TRANSPARENT

        rgba = np.empty((h, w, 4), np.uint8)
        for channel, low_bit in enumerate((10, 5, 0)):
            rgba[..., channel] = _widen((rgb >> low_bit) & 0x1F)
        rgba[..., 3] = np.where(shown, 255, 0)
        if mask:
            level = np.full(w * h, -1, np.int16)
            _paint_runs(level, None, mask, unit=1)
            level = level.reshape(h, w)
            rgba[..., 3] = np.where(level >= 0, _widen(np.minimum(np.maximum(level, 0), 31)), rgba[..., 3])
        return rgba[:, ::-1] if im["invert"] else rgba


def _widen(five_bit):
    """0..31 -> 0..255 the usual way: the top bits repeated below."""
    return (five_bit << 3) | (five_bit >> 2)


def _paint_runs(dest, shown, data, unit=2):
    """Run-length data over a flat pixel array, continuing across line ends: SKIP n leaves n pixels as they are;
    any other byte n is followed by n pixel values (`unit` bytes each: u16 colours, or u8 alpha levels)."""
    kind = "<u2" if unit == 2 else np.uint8
    at, cursor, end, total = 0, 0, len(data), dest.size
    while at < end:
        n = data[at]
        if n == SKIP:
            cursor += data[at + 1]
            at += 2
            continue
        at += 1
        if cursor + n > total or at + unit * n > end:
            raise Sg3Error("run out of bounds")
        dest[cursor:cursor + n] = np.frombuffer(data, kind, n, at)
        if shown is not None:
            shown[cursor:cursor + n] = True
        at += unit * n
        cursor += n


def _paint_iso_base(rgb, shown, data, iso_size, index):
    """The ground part of a building: size x size iso tiles at the bottom of the image, stored tile after tile in
    rows of the drawn diamond (top row first, left to right), each tile's 900 pixels row by row."""
    h, w = rgb.shape
    base_h = (w + 2) // 2
    n = iso_size or base_h // DIAMOND_H
    if len(data) != n * n * _DIAMOND_PIXELS * 2:
        raise Sg3Error(f"image {index}: iso base length {len(data)}")
    pixels = np.frombuffer(data, "<u2")
    top = h - base_h
    tile = 0
    for row in range(2 * n - 1):
        indent = abs(n - 1 - row)          # in half tiles from the left edge
        for k in range(n - indent):
            x = (indent + 2 * k) * (DIAMOND_H)
            y = top + row * (DIAMOND_H // 2)
            part = pixels[tile * _DIAMOND_PIXELS:(tile + 1) * _DIAMOND_PIXELS]
            tile += 1
            rgb[y:y + DIAMOND_H, x:x + DIAMOND_W][_DIAMOND] = part
            shown[y:y + DIAMOND_H, x:x + DIAMOND_W][_DIAMOND] = (part & 0x7FFF) != ISO_KEY


def _safe(name):
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name).strip("_") or "unnamed"


def export(path, out_dir):
    s = Sg3(path)
    dest = os.path.join(out_dir, s.name)
    os.makedirs(dest, exist_ok=True)
    atlas = dict(file=os.path.basename(path), version=s.version, bitmaps=s.bitmaps,
                 groups=s.groups, images=[])
    errors = 0
    for im in s.images[1:]:
        group = s.group_of(im["index"])
        entry = {k: im[k] for k in ("index", "width", "height", "anchor_x", "anchor_y",
                                    "anim_frames", "type", "iso_size", "bitmap")}
        entry["group"] = group
        entry["mirror_of"] = im["index"] + im["invert"] if im["invert"] else None
        try:
            rgba = s.decode(im)
        except (Sg3Error, ValueError) as e:
            entry["error"] = str(e)
            errors += 1
            rgba = None
        if rgba is not None:
            rel = os.path.join(_safe(group), f"{im['index']:05d}.png")
            os.makedirs(os.path.join(dest, _safe(group)), exist_ok=True)
            PILImage.fromarray(rgba, "RGBA").save(os.path.join(dest, rel), optimize=False)
            entry["png"] = rel
        atlas["images"].append(entry)
    with open(os.path.join(dest, "atlas.json"), "w") as f:
        json.dump(atlas, f, indent=1)
    return s.name, len(s.images) - 1, errors


def main(argv):
    if len(argv) >= 2 and argv[0] == "info":
        s = Sg3(argv[1])
        print(f"{s.name}: version {s.version:#x}, {s.num_images} images, {s.num_bitmaps} bitmaps")
        for g in s.groups:
            print(f"  group {g['id']:3d} first={g['first']:5d} {g['name']}")
        return
    if len(argv) >= 3 and argv[0] == "export":
        data, out = argv[1], argv[2]
        names = set(n.lower() for n in argv[3:])
        files = sorted(os.path.join(data, f) for f in os.listdir(data)
                       if f.lower().endswith(".sg3")
                       and (not names or os.path.splitext(f)[0].lower() in names))
        total = bad = 0
        with ProcessPoolExecutor() as ex:
            for name, n, err in ex.map(export, files, [out] * len(files)):
                total, bad = total + n, bad + err
                print(f"{name}: {n} images, {err} errors", flush=True)
        print(f"TOTAL {len(files)} files, {total} images, {bad} errors")
        return
    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
