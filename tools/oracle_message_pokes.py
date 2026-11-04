"""Pokes (ZEUS_POKE lines) that fill the exe's message queue with copies of its first entry, for oracle shots of the
Messages list with a scrollbar (re/oracle/scenarios/messages-list.txt). The queue: 0x00FD3838 + 0x3C*i (+8 year,
+0x0C id, +0x0E read flag, +0x0F month), count 0x00FD37F0.

    python3 tools/oracle_message_pokes.py DUMP N [TICK] > POKE   (DUMP: a tick dump of "See a working city", e.g.
                                                                  re/oracle/runs/messages-window/dump/tick_000000.bin)
Copy i (1..N-1): month (4 - i) mod 12, year -1341 from copy 5 on, id 100 + i, read when i % 3 == 0."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle import Dump  # noqa: E402

QUEUE, COUNT, SIZE = 0xFD3838, 0xFD37F0, 0x3C


def main(dump, n, tick=5):
    e = bytes(Dump(dump).at(QUEUE, f"{SIZE}s"))
    out = []
    for s in range(1, n):
        b = bytearray(e)
        b[0x0F] = (4 - s) % 12
        if s > 4:
            b[8:10] = struct.pack("<h", -1341)
        b[0x0C:0x0E] = struct.pack("<h", 100 + s)
        b[0x0E] = 1 if s % 3 == 0 else 0
        out += [f"{tick} {QUEUE + SIZE * s + o:X} 4 {struct.unpack_from('<i', b, o)[0]}" for o in range(0, SIZE, 4)]
    out.append(f"{tick} {COUNT:X} 4 {n}")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 5)
