"""Zeus .map / .sav / .pak reader: block container + PKWARE DCL 'implode' decompression.

Formats: docs/formats.md ("Map container", "DCL compression"), docs/campaign-format.md (.pak/.set header).
Container: blocks, each the memory image of one game variable, described by a table of
300 x 20-byte entries (compressed?, address, element size, count, converter).

Usage:
    python3 tools/mapfile.py info FILE.map|FILE.sav|FILE.pak
    python3 tools/mapfile.py points FILE             every point table of the scenario block (logical)
    python3 tools/mapfile.py dump FILE OUT_DIR       one .bin per block + blocks.json
"""
import json
import os
import struct
import sys

GRID = 228


# ---- PKWARE DCL "implode" streams: decompression -------------------------------------------
# Format: docs/formats.md "DCL compression". The three fixed code tables below are the format's own (as published
# in Mark Adler's blast.c), each as code-length runs: low nibble = code length, high nibble + 1 = how many symbols
# in a row have it.

def _canonical(runs):
    """{(length, code): symbol} for a canonical prefix code given as code-length runs."""
    lengths = [n for b in runs for n in [b & 0x0F] * ((b >> 4) + 1)]
    table, code, prev = {}, 0, 0
    for length, sym in sorted((n, s) for s, n in enumerate(lengths) if n):
        code <<= length - prev
        prev = length
        table[(length, code)] = sym
        code += 1
    return table


_LITERALS = _canonical(bytes([
    11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8, 9, 7, 6, 7, 8, 7, 6,
    55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5, 7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9,
    8, 25, 11, 8, 11, 9, 12, 8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27,
    44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45, 44, 173]))
_LENGTHS = _canonical(bytes([2, 35, 36, 53, 38, 23]))
_DISTANCES = _canonical(bytes([2, 20, 53, 230, 247, 151, 248]))
# length symbol -> (extra bits, base): symbols 0..7 carry no extra bits; from 8 on, each base follows the last
_LENGTH_EXTRA = [0] * 8 + list(range(1, 9))
_LENGTH_BASE = [3, 2, 4, 5, 6, 7, 8, 9]
for _x in _LENGTH_EXTRA[7:-1]:
    _LENGTH_BASE.append(_LENGTH_BASE[-1] + (1 << _x))
_END_LENGTH = 519   # the length that marks the end of the stream
_MAX_CODE = 13


class _Bits:
    """Least-significant-bit-first reader over a byte string."""

    def __init__(self, data, start):
        self.data = bytes(data) + b"\0\0\0"
        self.limit = len(data) * 8
        self.at = start * 8

    def take(self, n):
        if self.at + n > self.limit:
            raise ValueError("DCL stream ends early")
        word = int.from_bytes(self.data[self.at >> 3:(self.at >> 3) + 3], "little")
        value = (word >> (self.at & 7)) & ((1 << n) - 1)
        self.at += n
        return value

    def symbol(self, table):
        """One prefix code; the stream holds every code bit inverted, first bit first."""
        code = 0
        for length in range(1, _MAX_CODE + 1):
            code = (code << 1) | (self.take(1) ^ 1)
            sym = table.get((length, code))
            if sym is not None:
                return sym
        raise ValueError("bad Huffman code")


def explode(data):
    coded_literals, window_bits = data[0], data[1]
    if coded_literals not in (0, 1) or window_bits not in (4, 5, 6):
        raise ValueError(f"bad DCL header {coded_literals} {window_bits}")
    src = _Bits(data, 2)
    out = bytearray()
    while True:
        if not src.take(1):
            out.append(src.symbol(_LITERALS) if coded_literals else src.take(8))
            continue
        ls = src.symbol(_LENGTHS)
        length = _LENGTH_BASE[ls] + src.take(_LENGTH_EXTRA[ls])
        if length == _END_LENGTH:
            return bytes(out)
        low = 2 if length == 2 else window_bits
        back = (src.symbol(_DISTANCES) << low) + src.take(low) + 1
        if back > len(out):
            raise ValueError("distance too far back")
        while length > 0:   # the copy may overlap what it writes: take at most `back` bytes at a time
            piece = out[len(out) - back:len(out) - back + min(length, back)]
            out += piece
            length -= len(piece)


# ---- container ---------------------------------------------------------------------------

def read_blocks(d, start=0):
    """Returns (header dict, list of blocks), reading a MAPS (.map) or .sav container at start."""
    p = start
    is_map = d[p:p + 4] == b"MAPS"
    if is_map:
        p += 4
    version, count = struct.unpack_from("<II", d, p)
    p += 8
    table = [struct.unpack_from("<IIIII", d, p + 20 * i) for i in range(300)]
    p += 6000
    first = 4 if is_map else 3
    blocks = []
    for i in range(first, count):
        compressed, addr, size, n, _ = table[i]
        total = size * n
        if compressed:
            clen, = struct.unpack_from("<I", d, p)
            p += 4
            if clen == 0x80000000:
                raw = d[p:p + total]
                p += total
            elif clen == 0:
                raw = bytes(total)
            else:
                raw = explode(d[p:p + clen])
                p += clen
        else:
            raw = d[p:p + total]
            p += total
        if len(raw) != total:
            raise ValueError(f"block {i} @{addr:#x}: {len(raw)} bytes, expected {total}")
        blocks.append(dict(rank=i, address=addr, size=size, count=n, compressed=compressed,
                           data=raw))
    return dict(kind="map" if is_map else "sav", version=version, count=count, end=p), blocks


def read_file(path):
    d = open(path, "rb").read()
    if path.lower().endswith(".pak"):
        i = d.find(b"MAPS")
        if i < 0:
            raise ValueError("no MAPS container in .pak")
        maps = []
        while i >= 0:
            hdr, blocks = read_blocks(d, i)
            maps.append((hdr, blocks))
            i = d.find(b"MAPS", hdr["end"])
        return maps
    return [read_blocks(d)]


def pak_map_offsets(d):
    """The 5 map offsets of a .pak (adventure +0x49538: parent city, colonies 1..4), as the exe seeks them
    (FUN_0042B230 by map slot 0x00F2A7B0: 0 -> [0], 10..13 -> [1..4]); None where no MAPS container starts there
    (the editor leaves stale values for absent maps). Note: read_file's first container of a multi-map .pak is the
    header's map_buffer copy (the LAST map published), not the parent city."""
    ver = struct.unpack_from("<I", d, 4)[0]
    offs = struct.unpack_from("<5I", d, 0x49535 if ver >= 23 else 0x4910D)
    return [o if d[o:o + 4] == b"MAPS" else None for o in offs]


def pak_map(path, index):
    """(hdr, blocks) of map `index` of a .pak (0 parent, 1..4 colony n), or None when absent."""
    d = open(path, "rb").read()
    o = pak_map_offsets(d)[index]
    return read_blocks(d, o) if o is not None else None


# ---- scenario block (rank 14) point tables -------------------------------------------------
# Offsets in the 2032-byte scenario block (exe address = 0x902928 + offset). Empty slot: x == -1
# (editor clear routines 0x405bc0..) or, for the spawn tables, x <= 0 (spawner skips x <= 0).
# Every table is the editor's marker list (FUN_004040D0: each marker drawn at grid index 0x00DA2F80 + 228 y + x):
# the points are LOGICAL map coordinates; raw (the 228 grid) = logical + scenario_origin (sim/world.py converts;
# docs/logic/map-terrain.md "Logical and raw coordinates").
#   name      offset  slots  elem  stride_to_y (elements)   tool id (FUN_004040D0 case), editor label (text 48)
_POINT_TABLES = {
    "wolf":    (0x28C, 4, "h", 4),   # 187 MAP_KILLER_POINT, figure 59, herd of 7 (FUN_004E0160 loop 1)
    "fishing": (0x29C, 8, "h", 8),   # 186 MAP_FISHING_POINT
    "urchin":  (0x2BC, 8, "h", 8),   # 189 (all -1 on the sandbox maps)
    "monster": (0x4E0, 3, "i", 3),   # 197 "Monster point 1..3" (monster_spawn 0x0052EEF0; was read as "native")
    "boar":    (0x3E8, 4, "i", 4),   # 190 MAP_PREY_POINT, figure 51, herd of 7 (loop 2)
    "deer":    (0x32C, 4, "h", 4),   # 210 MAP_DEER_POINT, spawns figure 51 too (loop 3)
    "land_invasion": (0x2E8, 8, "h", 16),  # 180 "Land Inv pt 1..8" (g_invasion_points 0x00902C10/30, slots 0..7)
    "sea_invasion":  (0x2F8, 8, "h", 16),  # 180 "Sea Inv pt 9..16" (slots 8..15)
    "landing":  (0x4F8, 3, "i", 3),  # 198 "Disembark pt 1..3" (g_landing_points 0x00902E20/2C)
    "entry":    (0x38C, 1, "h", 1),  # 181 g_map_entry 0x00902CB4 (immigrants, land traders)
    "exit":     (0x390, 1, "h", 1),  # 182 g_land_exit 0x00902CB8
    "sea_entry": (0x3B4, 1, "h", 1), # 184 g_sea_entry 0x00902CDC (ships); -1 = none
    "sea_exit": (0x3B8, 1, "h", 1),  # 185 0x00902CE0
    "quake":    (0x388, 1, "h", 1),  # 173 "Earthquake" 0x00902CB0 (not used by the sim)
    "disaster": (0x394, 8, "h", 8),  # 168 "Disaster pt 1..8" 0x00902CBC (not used by the sim)
    "landslide": (0x624, 3, "i", 3), # 163 "Landslide pt 1..3" 0x00902F4C (not used by the sim)
}


def scenario_slots(blocks, name):
    """[(x, y) or None, ...] per slot of a point table (logical; None: x or y < 0)."""
    d = [b for b in blocks if b["rank"] == 14][0]["data"]
    off, n, fmt, ystride = _POINT_TABLES[name]
    sz = 2 if fmt == "h" else 4
    xs = struct.unpack_from("<%d%s" % (n, fmt), d, off)
    ys = struct.unpack_from("<%d%s" % (n, fmt), d, off + ystride * sz)
    return [(x, y) if x >= 0 and y >= 0 else None for x, y in zip(xs, ys)]


def scenario_points(blocks, name):
    """[(x, y), ...] of the used slots of a point table (logical), as the herd spawner takes them (x > 0)."""
    return [p for p in scenario_slots(blocks, name) if p and p[0] > 0]


def scenario_origin(blocks):
    """The grid tile of logical (0, 0): the grid base 0x00DA2F80 = scenario block +0x34 (229 on the sandbox maps:
    (1, 1); 44 * 229 on the tutorial-size maps: (44, 44)); +0x2C / +0x30 = the play area's W, H."""
    d = [b for b in blocks if b["rank"] == 14][0]["data"]
    base = struct.unpack_from("<i", d, 0x34)[0]
    return (base % 228, base // 228)


def herd_points(blocks):
    """{'boar': [...], 'wolf': [...], 'deer': [...]} herd spawn points (7 animals each)."""
    return {k: scenario_points(blocks, k) for k in ("boar", "wolf", "deer")}


def fishing_points(blocks):
    return scenario_points(blocks, "fishing")


def urchin_points(blocks):
    return scenario_points(blocks, "urchin")


def _show_points(path):
    for m, (hdr, blocks) in enumerate(read_file(path)):
        print(f"container {m}")
        for k in _POINT_TABLES:
            print(f"  {k:13s}", [p for p in scenario_slots(blocks, k) if p])
        print("  origin (raw = logical + origin)", scenario_origin(blocks))


def main(argv):
    if len(argv) >= 2 and argv[0] in ("info", "dump"):
        maps = read_file(argv[1])
        for m, (hdr, blocks) in enumerate(maps):
            print(f"container {m}: {hdr['kind']} version {hdr['version']}, {hdr['count']} blocks")
            for b in blocks:
                print(f"  rank {b['rank']:3d} @{b['address']:08x} {b['size']:5d} x {b['count']:6d}"
                      f" {'z' if b['compressed'] else ' '} nonzero={sum(1 for x in b['data'] if x)}")
            if argv[0] == "dump":
                out = os.path.join(argv[2], f"map{m}")
                os.makedirs(out, exist_ok=True)
                for b in blocks:
                    open(os.path.join(out, f"rank{b['rank']:03d}.bin"), "wb").write(b["data"])
                json.dump([{k: v for k, v in b.items() if k != "data"} for b in blocks],
                          open(os.path.join(out, "blocks.json"), "w"), indent=1)
        return
    if len(argv) == 2 and argv[0] == "points":
        return _show_points(argv[1])
    print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
