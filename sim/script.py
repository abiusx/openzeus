"""Script files: one command per line, '#' comments; `include FILE` inserts another script
(path relative to the including file)."""
import os


def load(path, _depth=0):
    """[(where, line)] with includes expanded; where = 'file:lineno'."""
    if _depth > 8:
        raise ValueError(f"include nesting too deep at {path}")
    out = []
    for n, raw in enumerate(open(path), 1):
        line = raw.split("#")[0].strip()
        if not line:
            continue
        if line.split()[0] == "include":
            out += load(os.path.join(os.path.dirname(path), line.split(None, 1)[1]), _depth + 1)
        else:
            out.append((f"{os.path.basename(path)}:{n}", line))
    return out



def apply(g, line):
    """g.command(line) for a script line. Scripts skip one placement rule: a walker standing on the site
    (map_area_buildable 0x004A0DC0 refuses it; play mode and `do` apply it). Walkers wander differently after
    every sim change, so a scripted build would fail at random (decision 10-28, docs/logic/buildings.md)."""
    g.script_mode = True
    try:
        return g.command(line)
    finally:
        g.script_mode = False
