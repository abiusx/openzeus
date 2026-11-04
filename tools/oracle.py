"""Read raw state dumps from the oracle (zeus-run + re/oracle/zeus-run-state-dump.patch).

    from oracle import Dump
    d = Dump('re/oracle/runs/tutorial/dump/tick_001500.bin')
    d.block(35)              # bytes of save block 35 (buildings)
    d.at(0x00FE6A58 + 0x0C, '<i')  # read by absolute exe address

Run a scenario: see docs/re/oracle.md.
"""
import glob, os, struct


def read_dump(path):
    """A dump's bytes: tick_NNNNNN.bin, or its zstd copy tick_NNNNNN.bin.zst (tools/oracle_compress.py; a .bin path
    that no longer exists falls back to the .zst, so paths cited in docs keep working). Python 3.14 compression.zstd."""
    if not path.endswith('.zst') and not os.path.exists(path) and os.path.exists(path + '.zst'):
        path += '.zst'
    data = open(path, 'rb').read()
    if path.endswith('.zst'):
        from compression import zstd
        data = zstd.decompress(data)
    return data


def shot(path):
    """A screenshot path: run shots are converted to lossless WebP (tools/oracle_compress.py --shots); a .bmp path
    that no longer exists resolves to its .webp, so paths cited in docs and scenario files keep working."""
    if path.endswith('.bmp') and not os.path.exists(path):
        for ext in ('.webp', '.png'):
            if os.path.exists(path[:-4] + ext):
                return path[:-4] + ext
    return path


def dump_files(d):
    """The dumps in a run's dump/ folder in tick order, plain or compressed, named by their plain path
    (.../tick_NNNNNN.bin, which read_dump resolves), so the callers' name parsing ([5:11], [-10:-4]) is unchanged."""
    names = {os.path.basename(f)[:15] for f in glob.glob(os.path.join(d, 'tick_*.bin')) +
             glob.glob(os.path.join(d, 'tick_*.bin.zst'))}
    return [os.path.join(d, n) for n in sorted(names)]


class Dump:
    def __init__(self, path):
        self.path = path
        self.data = read_dump(path)
        self.zones = []  # (block, address, size, offset)
        for line in open(os.path.join(os.path.dirname(path), 'zones.txt')):
            b, a, s, o = line.split()
            self.zones.append((int(b), int(a, 16), int(s), int(o)))

    def block(self, rank):
        for b, a, s, o in self.zones:
            if b == rank:
                return self.data[o:o + s]
        raise KeyError(rank)

    def at(self, address, fmt='<i'):
        n = struct.calcsize(fmt)
        for b, a, s, o in self.zones:
            if a <= address and address + n <= a + s:
                return struct.unpack_from(fmt, self.data, o + address - a)[0]
        raise KeyError(hex(address))
