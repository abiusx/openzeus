"""Every file a game can be saved to or loaded from, in one place (user 10-31).

Ours (written by Game.save): a header, then the game pickled and zstd-compressed (Python 3.14 compression.zstd):

    b"ZEUSPORT-SAVE\\n"     magic (14 bytes)
    u16 format version     FORMAT (below); a reader migrates older versions in Game.load
    u8  codec              b"Z" zstd, b"P" plain pickle
    u8  reserved (0)
    payload                pickle.dumps(game, HIGHEST_PROTOCOL), compressed by the codec

A 2.4 MB game (the 228x228 grids are mostly zeros) is ~10x smaller. kind(path) also recognises:
  "pickle"   saves from before the header (a bare pickle): still load
  "map"      an original Zeus .map (b"MAPS"): a new game on that map (World reads it, tools/mapfile.py)
  "pak"      an original adventure .pak (u32 0x22A7 .set header + MAPS containers): a new game on its first map
  "sav"      an original Zeus .sav: converted into a Game by sim/savimport.py (Game.load)
"""
import pickle
import struct

MAGIC = b"ZEUSPORT-SAVE\n"
FORMAT = 1                  # 1: header + zstd pickle (2026-10-31)
LEVEL = 3                   # zstd level: the live server saves every 5 s; 3 is ~10 ms for a big city


def kind(path):
    with open(path, "rb") as f:
        head = f.read(len(MAGIC) + 4)
    if head.startswith(MAGIC):
        return "ours"
    if head[:1] == b"\x80":                         # a pickle protocol opcode
        return "pickle"
    if head[:4] == b"MAPS":
        return "map"
    if len(head) >= 4 and struct.unpack_from("<I", head)[0] == 0x22A7:
        return "pak"
    if path.lower().endswith(".sav"):
        return "sav"
    return "unknown"


def header(path):
    """(format version, codec) of one of our files."""
    with open(path, "rb") as f:
        head = f.read(len(MAGIC) + 4)
    version, codec = struct.unpack_from("<HB", head, len(MAGIC))
    return version, bytes([codec])


def write(obj, f, compress=True):
    """Write obj to an open binary file in our format."""
    data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)
    codec = b"Z" if compress else b"P"
    if compress:
        from compression import zstd
        data = zstd.compress(data, LEVEL)
    f.write(MAGIC + struct.pack("<HBB", FORMAT, codec[0], 0) + data)


def read(path):
    """(object, format version) of a save: ours or a bare pickle (version 0). The original's files are not saves:
    Game.load turns a .map / .pak into a new game and converts a .sav (see kind)."""
    k = kind(path)
    with open(path, "rb") as f:
        raw = f.read()
    if k == "pickle":
        return pickle.loads(raw), 0
    if k != "ours":
        raise ValueError(f"{path}: not one of our saves ({k})")
    version, codec = struct.unpack_from("<HB", raw, len(MAGIC))
    if version > FORMAT:
        raise ValueError(f"{path}: save format {version} is newer than this program ({FORMAT})")
    data = raw[len(MAGIC) + 4:]
    if codec == ord("Z"):
        from compression import zstd
        data = zstd.decompress(data)
    elif codec != ord("P"):
        raise ValueError(f"{path}: unknown codec {chr(codec)!r}")
    return pickle.loads(data), version
