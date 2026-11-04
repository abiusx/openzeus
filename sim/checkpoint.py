"""Script checkpoints for `run`: the sim is deterministic, so the state after the first i lines of a
script depends only on (code, data, seed, map, those lines). `run` saves the state now and then
under that key and, on the next run, resumes from the longest prefix it has saved, so editing the
end of a long script re-simulates only the end. Kept in .cache/ckpt (git-ignored), newest KEEP.
"""
import glob
import hashlib
import os
import pickle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, ".cache", "ckpt")
KEEP = 80
EVERY = 816 * 12              # ticks between checkpoints (a year)
_code = None


def code_hash():
    """Every sim source file and data file: any change to them makes old checkpoints unusable."""
    global _code
    if _code is None:
        h = hashlib.sha256()
        files = sorted(glob.glob(os.path.join(ROOT, "sim", "**", "*.py"), recursive=True)
                       + glob.glob(os.path.join(ROOT, "data", "*.json")))
        for f in files:
            h.update(os.path.relpath(f, ROOT).encode())
            with open(f, "rb") as fh:
                h.update(fh.read())
        _code = h.hexdigest()
    return _code


def keys(lines, seed, map_name, code=True):
    """keys[i] = key of the state after lines[:i] (keys[0] = the fresh game). code=False: the key
    leaves the code out (for --stale: continue a state that older code produced)."""
    h = hashlib.sha256(f"{code_hash() if code else ''}|{seed}|{map_name}".encode())
    out = [h.hexdigest()]
    for line in lines:
        h.update(b"\n" + line.encode())
        out.append(h.hexdigest())
    return out


def _stale_index():
    import json
    p = os.path.join(DIR, "stale.json")
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def find(ks, stale=None):
    """(i, game) for the largest i with a saved checkpoint, or (0, None). stale: the code-free keys;
    then a checkpoint made by any code version for that script prefix will do."""
    from .game import Game
    idx = _stale_index() if stale else {}
    for i in range(len(ks) - 1, 0, -1):
        p = os.path.join(DIR, ks[i] + ".pkl")
        if stale and not os.path.exists(p) and stale[i] in idx:
            p = os.path.join(DIR, idx[stale[i]] + ".pkl")
        if os.path.exists(p):
            try:
                g = Game.load(p)
            except Exception:
                continue
            os.utime(p)
            return i, g
    return 0, None


def save(g, key, stale_key=None):
    os.makedirs(DIR, exist_ok=True)
    g.save(os.path.join(DIR, key + ".pkl"))
    if stale_key:                              # newest checkpoint for this script prefix, any code
        import json
        idx = _stale_index()
        idx[stale_key] = key
        with open(os.path.join(DIR, "stale.json"), "w") as f:
            json.dump(idx, f)
    files = sorted(glob.glob(os.path.join(DIR, "*.pkl")), key=os.path.getmtime)
    for f in files[:-KEEP]:
        os.remove(f)
