"""Print decompiled functions from re/decomp/zeus.c by name or address.
Usage: python3 tools/fn.py NAME_OR_ADDR...   (also: --callers NAME)"""
import re, sys, bisect
SRC = open(__file__.rsplit('/', 2)[0] + '/re/decomp/zeus.c', encoding='utf-8').read()
HEADS = [(m.start(), m.group(1), m.group(2)) for m in
         re.finditer(r'^// ===== (\S+) @ ([0-9a-f]+)', SRC, flags=re.M)]
POS = [h[0] for h in HEADS]

def body(key):
    key = key.lower().removeprefix('0x').removeprefix('fun_')
    for i, (p, name, addr) in enumerate(HEADS):
        if name.lower() in (key, 'fun_' + key) or addr.lstrip('0') == key.lstrip('0'):
            end = HEADS[i + 1][0] if i + 1 < len(HEADS) else len(SRC)
            return SRC[p:end]
    return f'// not found: {key}\n'

def callers(name):
    out = {}
    for m in re.finditer(re.escape(name) + r'\(', SRC):
        i = bisect.bisect(POS, m.start()) - 1
        if HEADS[i][1] != name:
            out[HEADS[i][1]] = out.get(HEADS[i][1], 0) + 1
    return out

if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == '--callers':
        for n in a[1:]:
            print(n, '<-', callers(n))
    else:
        for k in a:
            print(body(k))
