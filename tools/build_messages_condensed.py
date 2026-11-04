"""data/messages_condensed.json: the condensed text of each event message (the control panel's message strip).

The panel strip (FUN_00430D80, drawn by FUN_005170A0 under the page buttons) shows a message's condensed phrase:
FUN_00477D60(announcement phrase id) is a jump table at 0x0047AB70 (0x1046 entries); each case returns another
phrase id (`mov eax, ID; ret`, usually the PHRASE_..._condensed one) or -1 (0x0047AB5A: no condensed text, the
message never enters the strip). FUN_00466AD0 then reads that phrase's text (Model/Zeus eventmsg.txt, read as
tools/build_messages.py does) and fills its variables.

    re/venv/bin/python tools/build_messages_condensed.py     (needs pefile + capstone; reads Zeus.exe and eventmsg.txt)

Output: {"note", "map": {announcement id: condensed id}, "texts": {condensed id: [name, text]}} (decimal string keys).
"""
import json
import os
import struct
import sys

import capstone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from disasm import read  # noqa: E402
from build_messages import phrase_names, parse, EVENTMSG  # noqa: E402

TABLE, COUNT, NONE = 0x0047AB70, 0x1046, 0x0047AB5A
OUT = os.path.join(ROOT, "data", "messages_condensed.json")


def condensed_map():
    md, out = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32), {}
    targets = struct.unpack(f"<{COUNT}I", read(TABLE, 4 * COUNT))
    for pid, t in enumerate(targets):
        if t == NONE:
            continue
        ins = list(md.disasm(read(t, 16), t))[:2]
        if ins[0].mnemonic == "or" and ins[0].op_str == "eax, 0xffffffff":
            continue                                       # -1 as well
        assert ins[0].mnemonic == "mov" and ins[0].op_str.startswith("eax, ") and ins[1].mnemonic == "ret", \
            (pid, hex(t), [(i.mnemonic, i.op_str) for i in ins])
        v = int(ins[0].op_str[5:], 0)
        if v < 0x80000000:
            out[pid] = v
    return out


def main():
    names = phrase_names()
    texts = parse(open(EVENTMSG, "rb").read(), {x.lower() for x in names})
    m = condensed_map()
    keep = {}
    for a, c in m.items():
        t = texts.get(names[c].lower()) if c < len(names) else None
        if t is None or t.strip() in ("", "N/A"):
            continue
        keep[a] = c
    used = sorted(set(keep.values()))
    note = ("tools/build_messages_condensed.py: FUN_00477D60 jump table 0x0047AB70 (announcement -> condensed phrase) "
            "+ Model/Zeus eventmsg.txt; the panel message strip FUN_00430D80 (docs/play/screens.md)")
    data = {"note": note, "map": {str(a): c for a, c in sorted(keep.items())},
            "texts": {str(c): [names[c], " ".join(texts[names[c].lower()].split())] for c in used}}
    with open(OUT, "w") as f:
        f.write(json.dumps(data, indent=0, ensure_ascii=False) + "\n")
    print(f"{len(keep)} announcements -> {len(used)} condensed texts ({len(m)} table cases) -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
