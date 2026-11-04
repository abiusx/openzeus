"""Find every instruction of Zeus.exe whose operand names an absolute address in [LO, HI) (data cross-references
the decompile can hide behind struct or array names). Run with re/venv/bin/python.
Usage: re/venv/bin/python tools/xref.py LO [HI=LO+4]   (hex; prints address, function start guess, instruction)"""
import sys, re, bisect, capstone
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from disasm import pe, base

HEADS = None


def functions():
    """Function starts from re/decomp/zeus.c headers (for the 'in' column)."""
    global HEADS
    if HEADS is None:
        src = open(__file__.rsplit('/', 2)[0] + '/re/decomp/zeus.c', encoding='utf-8').read()
        HEADS = sorted((int(a, 16), n) for n, a in re.findall(r'^// ===== (\S+) @ ([0-9a-f]+)', src, flags=re.M))
    return HEADS


def scan(lo, hi):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.skipdata = True
    heads = functions()
    starts = [h[0] for h in heads]
    out = []
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:          # executable sections only
            continue
        data = s.get_data()
        va0 = base + s.VirtualAddress
        for ins in md.disasm(data, va0):
            for m in re.finditer(r'0x([0-9a-f]+)', ins.op_str):
                v = int(m.group(1), 16)
                if lo <= v < hi:
                    i = bisect.bisect(starts, ins.address) - 1
                    out.append((ins.address, heads[i][1] if i >= 0 else '?', f'{ins.mnemonic} {ins.op_str}'))
                    break
    return out


if __name__ == '__main__':
    lo = int(sys.argv[1], 16)
    hi = int(sys.argv[2], 16) if len(sys.argv) > 2 else lo + 4
    for a, f, t in scan(lo, hi):
        print(f'{a:08x}  {f:32s}  {t}')
