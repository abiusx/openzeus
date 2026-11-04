"""Emulate Zeus.exe's monument piece classes to find which image each piece shows at each build stage.

    re/venv/bin/python tools/re_monument_images.py        (needs unicorn + capstone + pefile: re/venv)

Writes extracted/model/monument_images.json (read by tools/play_monuments.py; docs/play/monuments.md).
Method: the 171 piece classes (docs/logic/monuments.md) are static objects whose vtables are set by
tiny static constructors (`mov ecx, OBJ; jmp CTOR`, CTOR writes `[eax] = VTABLE`). For each class we
run, in an x86 emulator on the exe's own code, vt+0x00 (piece size), vt+0x08 (stage count) and
vt+0x4C (`piece_image(&flags)`, called by refresh_piece_image 0x0053D300) on a fake piece record
(g_buildings 0x0092E658 + id*0x118: type +0x10, part index +0x12, tile +0x0C, stage +0x58,
orientation +0x9C = 0..3: "orient_phases" where it changes the image), with fake sprite-bank group tables so that a returned image id decodes to
(bank, group rank, offset). The sprite loader 0x005AC570(name, bank) is stubbed and logged (it loads
per-god/per-stage files into banks 6, 7, 8, 14, 65). The pyramid neighbour rule 0x00545940 is stubbed
and logged (its arguments give the step variant). View rotation 0x00DA2F88 = 0, and 2/4/6 for "view_phases"
(turned views, docs/play/rotation.md).
"""
import json
import os
import re
import struct
import sys

import capstone
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_UNMAPPED
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import disasm  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "extracted", "model", "monument_images.json")
pe, base = disasm.pe, disasm.base

BUILDINGS = 0x0092E658          # g_buildings (record 0x118)
BANKS = 0x012AEBE8              # sprite banks, 0xCC44 each; +0x1004 group table, +0xDC38 last rank
LAYOUTS = 0x00FE5100            # composite layout manager: +0x270+type*4 piece list, +0x958+type*4 count
GRID_ELEV, GRID_BUILDING = 0x008E01FA, 0x00D26E98
LOADER, NEIGHBOUR_RULE = 0x005AC570, 0x00545940
STRIDE = 54                     # fake group table: rank r starts at (r-1)*STRIDE
ID, TILE = 1, 100 * 228 + 100

mu = Uc(UC_ARCH_X86, UC_MODE_32)
mu.mem_map(base, 0x01620000 - base)
for s in pe.sections:
    d = s.get_data()
    mu.mem_write(base + s.VirtualAddress, d[:s.Misc_VirtualSize] if len(d) > s.Misc_VirtualSize else d)
STACK, SCR, TAB, LAY = 0x02000000, 0x03000000, 0x01700000, 0x01800000
mu.mem_map(STACK - 0x100000, 0x100000)
mu.mem_map(SCR, 0x10000)
mu.mem_map(TAB, 0x100000)
mu.mem_map(LAY, 0x10000)
RET = SCR + 0xF000
mu.mem_write(RET, b"\xf4")


def w32(a, v):
    mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))


def r32(a):
    return struct.unpack("<I", mu.mem_read(a, 4))[0]


for bank in range(70):
    bb = BANKS + bank * 0xCC44
    if bb + 0xDC40 >= 0x01620000:
        break
    t = TAB + bank * 0x3000
    w32(bb + 0x1004, t)
    w32(bb + 0xDC38, 299)
    for k in range(300):
        w32(t + 8 * k + 4, k * STRIDE)

unmapped, loads, rule_calls = [], [], []


def on_unmapped(uc, acc, addr, size, val, ud):
    unmapped.append(addr)
    if len(unmapped) > 8 or addr < 0x10000:
        return False
    uc.mem_map(addr & ~0xFFF, 0x1000)
    return True


def stub(log, nargs, ret):
    def hook(uc, addr, size, ud):
        esp = uc.reg_read(UC_X86_REG_ESP)
        args = [r32(esp + 4 * (i + 1)) for i in range(nargs)]
        log.append(args)
        uc.reg_write(UC_X86_REG_EAX, ret)
        uc.reg_write(UC_X86_REG_ESP, esp + 4 * (nargs + 1))
        uc.reg_write(UC_X86_REG_EIP, r32(esp))
    return hook


mu.hook_add(UC_HOOK_MEM_UNMAPPED, on_unmapped)
mu.hook_add(UC_HOOK_CODE, stub(loads, 2, 0), begin=LOADER, end=LOADER)          # thiscall (name, bank)
mu.hook_add(UC_HOOK_CODE, stub(rule_calls, 3, 0x7777), begin=NEIGHBOUR_RULE, end=NEIGHBOUR_RULE)


def call(fn, ecx, args=()):
    sp = STACK - 0x1000
    for a in reversed(args):
        sp -= 4
        w32(sp, a)
    sp -= 4
    w32(sp, RET)
    mu.reg_write(UC_X86_REG_ESP, sp)
    mu.reg_write(UC_X86_REG_ECX, ecx)
    mu.reg_write(UC_X86_REG_EAX, 0)
    mu.emu_start(fn, RET, count=200000)
    return mu.reg_read(UC_X86_REG_EAX)


def vtables():
    """class id -> (object, vtable) from the static constructors."""
    objs = {i: r32(0x00640E08 + 4 * i) for i in range(164)}
    objs.update({1000 + i: r32(0x00641098 + 4 * i) for i in range(7)})
    text = [s for s in pe.sections if s.Name.startswith(b".text")][0]
    data = pe.__data__[text.PointerToRawData:text.PointerToRawData + text.SizeOfRawData]
    tva = base + text.VirtualAddress
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    ctor = {}
    for m in re.finditer(rb"\xb9(....)[\xe8\xe9](....)", data, re.S):
        a = struct.unpack("<I", m.group(1))[0]
        if 0x00FE4600 <= a <= 0x00FE5100:
            site = tva + m.start() + 5
            ctor.setdefault(a, set()).add((site + 5 + struct.unpack("<i", m.group(2))[0]) & 0xFFFFFFFF)
    out = {}
    for cid, o in objs.items():
        vts = set()
        for c in ctor.get(o, ()):
            for ins in md.disasm(disasm.read(c, 60), c):
                mm = re.match(r"dword ptr \[e[a-z]x\], (0x[0-9a-f]+)", ins.op_str)
                if ins.mnemonic == "mov" and mm:
                    vts.add(int(mm.group(1), 16))
                    break
                if ins.mnemonic == "ret":
                    break
        assert len(vts) == 1, (cid, vts)
        out[cid] = (o, vts.pop())
    return out


def sname(a):
    return bytes(mu.mem_read(a, 40)).split(b"\0")[0].decode()


def piece(cid, o, v, typ, stage, elev=0, poseidon=False, orient=0, view=0):
    """Run vt+0x4C for a piece of class cid; returns (image dict or None, flags)."""
    w32(0x00DA2F88, view)                 # view orientation 0, 2, 4, 6 (docs/play/rotation.md)
    w32(0x006AA4E0, int(poseidon))        # poseidon_game() 0x004200F0
    w32(0x00902BB0, int(poseidon))
    w32(o, v)
    w32(o + 4, ID)
    b = BUILDINGS + ID * 0x118
    mu.mem_write(b, b"\0" * 0x118)
    mu.mem_write(b + 0x10, struct.pack("<hh", typ, 0))
    w32(b + 0x0C, TILE)
    w32(b + 0x58, stage)
    mu.mem_write(b + 0x9C, bytes([orient]))          # placement orientation (FUN_0053C390 stores DAT_00DA23C4)
    mu.mem_write(LAY, b"\0" * 0x48)
    w32(LAY + 8, cid)
    w32(LAY + 0xC, 1)
    w32(LAY + 0x10, elev)
    w32(LAYOUTS + 0x270 + typ * 4, LAY)
    w32(LAYOUTS + 0x958 + typ * 4, 1)
    E = (elev // 2) * 4 if 100 <= typ <= 114 else 0
    mu.mem_write(GRID_ELEV + TILE, bytes([min(elev, (stage // 4) * 2) if stage < E else elev]))
    mu.mem_write(GRID_BUILDING + 2 * TILE, struct.pack("<h", ID))
    del loads[:], rule_calls[:], unmapped[:]
    img = call(r32(v + 0x4C), o, (SCR + 0x200,))
    flags = r32(SCR + 0x200)
    if img == 0x7777:
        return {"rule": "steps", "variant": rule_calls[0][1]}, flags
    if not img:
        return None, flags
    bank, n = divmod(img, 0x4000)
    k, off = divmod(n, STRIDE)
    r = {"bank": bank, "rank": k + 1, "offset": off}
    if loads:
        r["file"] = sname(loads[-1][0])
        assert loads[-1][1] == bank, (cid, loads, bank)
    return r, flags


def main():
    vt = vtables()
    res = {"about": __doc__.strip().splitlines()[0], "classes": {}, "pyramid": {}}
    for cid in sorted(vt):
        o, v = vt[cid]
        w32(o, v)
        w32(o + 4, ID)
        mu.mem_write(BUILDINGS + ID * 0x118, b"\0" * 0x118)
        mu.mem_write(BUILDINGS + ID * 0x118 + 0x10, struct.pack("<h", 0x54))
        n = call(r32(v + 8), o)
        size = call(r32(v + 0), o)
        ph, phx = [], []
        for s in range(n):
            ph.append(piece(cid, o, v, 0x54, s))
            phx.append(piece(cid, o, v, 0x54, s, poseidon=True))
        e = {"size": size, "stages": n, "vtable": hex(v), "image_fn": hex(r32(v + 0x4C)),
             "phases": [dict(img=i, flags=f) for i, f in ph]}
        if phx != ph:
            e["poseidon_phases"] = [dict(img=i, flags=f) for i, f in phx]
        for orient in (1, 2, 3):                 # rotated placements (R key, bugs.md 133): only when they differ
            po = [piece(cid, o, v, 0x54, s, orient=orient) for s in range(n)]
            pox = [piece(cid, o, v, 0x54, s, poseidon=True, orient=orient) for s in range(n)]
            if po != ph or pox != phx:
                e.setdefault("orient_phases", {})[str(orient)] = [dict(img=i, flags=f) for i, f in po]
                if pox != po:
                    e.setdefault("orient_poseidon_phases", {})[str(orient)] = [dict(img=i, flags=f) for i, f in pox]
        # turned views (PgUp/PgDn, docs/play/rotation.md): the image also reads 0x00DA2F88; kept per view and
        # orientation where it differs from that orientation's view-0 phases
        for view in (2, 4, 6):
            for orient in range(4):
                p0 = [piece(cid, o, v, 0x54, s, orient=orient) for s in range(n)]
                p0x = [piece(cid, o, v, 0x54, s, poseidon=True, orient=orient) for s in range(n)]
                pv = [piece(cid, o, v, 0x54, s, orient=orient, view=view) for s in range(n)]
                pvx = [piece(cid, o, v, 0x54, s, poseidon=True, orient=orient, view=view) for s in range(n)]
                if pv != p0:
                    e.setdefault("view_phases", {}).setdefault(str(view), {})[str(orient)] = [dict(img=i, flags=f) for i, f in pv]
                if pvx != p0x:
                    e.setdefault("view_poseidon_phases", {}).setdefault(str(view), {})[str(orient)] = [dict(img=i, flags=f) for i, f in pvx]
        res["classes"][str(cid)] = e
    # pyramid context (type 100): a piece at layout elevation 2 rising through its base stages
    for cid in (117, 118, 119, 120, 121, 122, 124, 145, 149, 150, 151, 160, 161, 162, 163):
        o, v = vt[cid]
        rows = []
        mu.mem_write(BUILDINGS + ID * 0x118, b"\0" * 0x118)
        n = None
        for s in range(16):
            img, f = piece(cid, o, v, 100, s, elev=2)
            if n is None:
                n = call(r32(v + 8), o)
            if s >= n:
                break
            rows.append(dict(stage=s, img=img, flags=f))
        res["pyramid"][str(cid)] = dict(elev=2, stages=n, rows=rows)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1)
    print("wrote", OUT, len(res["classes"]), "classes")


if __name__ == "__main__":
    main()
