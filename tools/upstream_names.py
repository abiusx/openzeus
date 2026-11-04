"""Fetch the zeus-poseidon-arm64 function names (GPL, not in our repo) for naming the Ghidra decompile.

Their analysis/noms.tsv at a pinned commit is downloaded once into re/names/.upstream/raw/ (git-ignored), checked
against its sha256, and converted to our names columns (address, name, kind, type, evidence) as
re/names/.upstream/00-arm64.tsv. re/ghidra/refresh.sh runs this, then ApplyNames.java reads that file before
our own re/names/*.tsv (sorted by file name: ours, zz-merged.tsv last, win conflicts). tools/structs_doc.py
reads it too. Offline: falls back to a local clone in refs/zeus-poseidon-arm64 that has the commit.
Usage:
    python3 tools/upstream_names.py          (prints the converted file's path)
"""
import hashlib
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "https://github.com/nic0lasm/zeus-poseidon-arm64"
COMMIT = "7aed75415fb685682e219cf56dd7b311890e02ff"
PATH = "analysis/noms.tsv"
URL = f"https://raw.githubusercontent.com/nic0lasm/zeus-poseidon-arm64/{COMMIT}/{PATH}"
SHA256 = "ea3971aebd1e6bfcf64621d41cfb2b695e3d03b414da10587a88445eb85fc7d4"
CACHE = os.path.join(ROOT, "re", "names", ".upstream")
RAW = os.path.join(CACHE, "raw", "noms.tsv")   # a subfolder: ApplyNames reads every .tsv of CACHE
OUT = os.path.join(CACHE, "00-arm64.tsv")
# their columns: adresse, nom, module, statut, preuve, type (fonction | donnée)
KINDS = {"fonction": "function", "donnée": "data"}


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _get():
    try:
        with urllib.request.urlopen(URL, timeout=30) as r:
            return r.read()
    except OSError as e:
        clone = os.path.join(ROOT, "refs", "zeus-poseidon-arm64")
        r = subprocess.run(["git", "-C", clone, "show", f"{COMMIT}:{PATH}"], capture_output=True)
        if r.returncode:
            sys.exit(f"cannot fetch {URL} ({e}) and no local clone with commit {COMMIT}")
        return r.stdout


def fetch():
    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    raw = open(RAW, "rb").read() if os.path.exists(RAW) else b""
    if _sha(raw) != SHA256:
        raw = _get()
        if _sha(raw) != SHA256:
            sys.exit(f"{URL}: sha256 {_sha(raw)}, expected {SHA256}")
        with open(RAW, "wb") as f:
            f.write(raw)
    rows = raw.decode("utf-8").splitlines()[1:]
    out = ["address\tname\tkind\ttype\tevidence",
           f"# {REPO} {PATH} at {COMMIT} (GPL; fetched by tools/upstream_names.py, not committed)"]
    for line in rows:
        addr, name, _module, status, proof, kind = line.split("\t")
        out.append(f"{addr}\t{name}\t{KINDS[kind]}\t\t{status}: {proof}")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return OUT


if __name__ == "__main__":
    print(fetch())
