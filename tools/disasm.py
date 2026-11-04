"""Disassemble Zeus.exe at a virtual address. Run with re/venv/bin/python.
Usage: re/venv/bin/python tools/disasm.py ADDR [COUNT=40]"""
import sys, pefile, capstone
EXE = __file__.rsplit('/', 2)[0] + '/zeus-original/app/Zeus.exe'
pe = pefile.PE(EXE, fast_load=True)
base = pe.OPTIONAL_HEADER.ImageBase

def read(va, n):
    rva = va - base
    for s in pe.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + s.Misc_VirtualSize:
            off = s.PointerToRawData + rva - s.VirtualAddress
            return pe.__data__[off:off + n]
    raise ValueError(hex(va))

if __name__ == '__main__':
    va = int(sys.argv[1], 16); count = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for i, ins in enumerate(md.disasm(read(va, count * 15), va)):
        if i >= count: break
        print(f'{ins.address:08x}  {ins.mnemonic:6s} {ins.op_str}')
