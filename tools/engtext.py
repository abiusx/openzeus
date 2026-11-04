"""Zeus_Text.eng -> extracted/text/zeus_text.json + .txt (group -> list of strings).
Format: refs/zeus-poseidon-arm64/formats/eng.md. Usage: python3 tools/engtext.py ENG_FILE OUT_PREFIX"""
import json, struct, sys

def read(path):
    d = open(path, 'rb').read()
    assert d[:14] == b'Zeus textfile.', 'not a Zeus text file'
    ngroups, = struct.unpack_from('<I', d, 0x10)
    area = 0x1F5C
    table = [struct.unpack_from('<II', d, 0x1C + 8 * g) for g in range(1000)]
    groups = {}
    for g in range(1, ngroups):
        off, count = table[g]
        p, strings = area + off, []
        for _ in range(count):
            e = d.index(b'\0', p)
            strings.append(d[p:e].decode('cp1252'))
            p = e + 1
        groups[g] = strings
    return groups

if __name__ == '__main__':
    groups = read(sys.argv[1])
    json.dump(groups, open(sys.argv[2] + '.json', 'w'), indent=1, ensure_ascii=False)
    with open(sys.argv[2] + '.txt', 'w') as f:
        for g, ss in groups.items():
            for i, s in enumerate(ss):
                f.write(f'[{g}:{i}] {s}\n')
    print(len(groups), 'groups,', sum(map(len, groups.values())), 'strings')
