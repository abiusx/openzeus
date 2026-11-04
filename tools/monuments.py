"""Parse the original's monument layouts (Model/Sanctuary_*.txt, Poseidon_Pyramid_*.txt) into
data/monuments.json: footprint (bounding box) and pieces [dx, dy, component, elevation] with
(dx, dy) relative to the box's top-left. Rows: sanctuary {x, y, component, flag}, pyramid
{x, y, component, elevation, build order} (docs/logic/monuments.md)."""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, "zeus-original", "app", "Model")
ROW = re.compile(r"\{\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*(-?\d+)\s*,(?:\s*(-?\d+)\s*,)?\s*[})]")   # 4 Zeus rows end in ",)"; the game reads them
# Zeus building type -> layout file (the Poseidon install uses Sanctuary_ZEUS_Pos)
SANCTUARIES = {84: "ZEUS_Pos", 85: "POSEIDON", 86: "DEMETER", 87: "APOLLO", 88: "ARTEMIS", 89: "ARES",
               90: "APHRODITE", 91: "HERMES", 92: "ATHENA", 93: "HEPHAISTOS", 94: "DIONYSUS", 95: "HADES",
               96: "HERA", 97: "ATLAS", 98: "POSEIDON_GRAND"}


def parse(path, pyramid):
    rows = []
    for line in open(path, encoding="latin-1"):
        line = line.split(";")[0]
        m = ROW.search(line)
        if m:
            x, y, c, f = (int(v) for v in m.groups()[:4])
            rows.append((x, y, c, f if pyramid else 0))
    x0 = min(r[0] for r in rows)
    y0 = min(r[1] for r in rows)
    w = max(r[0] for r in rows) - x0 + 1
    h = max(r[1] for r in rows) - y0 + 1
    # origin: the file's (0, 0) in box coordinates, the reference point of composite_road_entry 0x0053F810 (the exe's
    # loader FUN_00540110 keeps the file coordinates; ours are shifted to the box)
    return dict(w=w, h=h, pieces=[[x - x0, y - y0, c, e] for x, y, c, e in rows], origin=[-x0, -y0])


def build():
    out = {}
    for zid, name in SANCTUARIES.items():
        out[f"sanctuary_{name.lower().replace('_pos', '')}"] = dict(zeus_id=zid, **parse(
            os.path.join(MODEL, f"Sanctuary_{name}.txt"), False))
    out["palace"] = dict(zeus_id=117, **parse(os.path.join(MODEL, "palace.txt"), False))
    for i in range(1, 16):
        out[f"pyramid_{i:02d}"] = dict(zeus_id=99 + i, **parse(
            os.path.join(MODEL, f"Poseidon_Pyramid_{i:02d}.txt"), True))
    return out


if __name__ == "__main__":
    m = build()
    for k, v in m.items():
        print(k, v["w"], "x", v["h"], len([p for p in v["pieces"] if p[2] < 1000]), "pieces")
