"""The original game's files that OpenZeus needs at runtime (docs/assets.md): build them from your own copy of the
game, or install them from the asset pack. Both give the same files (sha256 per file in assets/manifest.json).

    python3 tools/assets.py build --game PATH [--hires pack|skip|upscale] [--gpu pack|build|skip] [--pack ZIP|URL ...]
    python3 tools/assets.py build --installer setup_zeus_and_poseidon_2.1.0.10.exe ...   (innoextract, then as above)
    python3 tools/assets.py install PACK.zip|URL [PACK2 ...] [--force]
    python3 tools/assets.py pack OUT.zip [--parts base,gpu,hires]
    python3 tools/assets.py verify [--parts base,gpu,hires,dev]
  for contributors:
    python3 tools/assets.py manifest            assets/manifest.json from the files in the tree
    python3 tools/assets.py split [FILE ...]    runtime JSON -> assets/templates/ (the game's strings as references)
    python3 tools/assets.py split --scan        template every tracked JSON that holds the game's strings
    python3 tools/assets.py merge               assets/templates/ + the game's text files -> runtime JSON

PATH is the game folder (the one with Zeus.exe, DATA/, Model/, Adventures/, Audio/; GOG Zeus + Poseidon 2.1.0.10).
It becomes zeus-original/app (a symlink, or the folder itself), which the sim and play mode read at runtime.

Parts (assets/manifest.json): base = what the build makes from the game folder with this repo's tools (game
text in data/, the original's sprite sheets, backdrops, the Adventures/ and Audio/ folders); gpu = the
GPU-compressed copies of the original's sheets (tools/hires_compress.py --originals: needs the ASTC/BC7 encoders,
docs/play/hires.md); hires = the upscaled sprite sets (pack only: the upscaler needs the ML models and a GPU);
dev = files the build makes for contributors' tools only (never packed).
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
GAME = os.path.join(ROOT, "zeus-original", "app")       # where the sim, play mode and the tools read the game
TEMPLATES = os.path.join(ROOT, "assets", "templates")
MANIFEST = os.path.join(ROOT, "assets", "manifest.json")
GITIGNORE = os.path.join(ROOT, ".gitignore")
ATLAS = "viewer/play/atlas"
GOG_EXE_SHA256 = "382bcd286192a06eb8fdc45f5c37390a19999f5db9c940c3ce2dfcd775e90a57"   # Zeus.exe, GOG 2.1.0.10
NEEDED = ["Zeus.exe", "Zeus_Text.eng", "Zeus_MM.eng", "DATA", "Model", "Adventures", "Audio",
          "Model/Zeus eventmsg.txt", "DATA/SprMain.sg3", "Audio/Wavs"]
PARTS = ("base", "gpu", "hires", "dev")
PACKED = ("base", "gpu", "hires")
# the original's sprite files whose sheets play mode loads (tools/play_atlas.py; on demand: gods, heroes, monsters,
# armies, monuments). viewer/sprites (tools/viewer_sprites.py) reads Zeus_General and Poseidon_Loaded.
ATLAS_FILES = """Zeus_Terrain Zeus_General SprMain SprAmbient Poseidon_Loaded Zeus_Interface destruction Zeus_Greek
 Poseidon_Unloaded Zeus_Unloaded PoseidonImps Zeus_Fonts Poseidon_Atalanta Poseidon_Atlantean Poseidon_Atlas
 Poseidon_AtlasStat Poseidon_Bellerophon Poseidon_Chimera Poseidon_Echidna Poseidon_Egyptian Poseidon_GrandStatue1
 Poseidon_GrandStatue2 Poseidon_GrandStatue3 Poseidon_Harpie Poseidon_Hera Poseidon_HeraStat Poseidon_Mayan
 Poseidon_Oceanid Poseidon_Phoenician Poseidon_Sanctuary3 Poseidon_Sphinx zeus_achilles Zeus_amazon Zeus_Aphrodite
 Zeus_Apollo Zeus_Ares Zeus_AresWarriors Zeus_Artemis Zeus_Athena zeus_calydonianboar Zeus_centaur zeus_cerberus
 zeus_cyclops Zeus_Demeter Zeus_Dionysus zeus_dragon Zeus_God01 Zeus_God02 Zeus_God03 Zeus_God04 Zeus_God05
 Zeus_God06 Zeus_God07 Zeus_God08 Zeus_God09 Zeus_God10 Zeus_God11 Zeus_God12 Zeus_Hades zeus_hector Zeus_Hephaestus
 zeus_heracles Zeus_Hermes zeus_hydra zeus_jason zeus_kraken zeus_maenads zeus_medusa zeus_minotaur zeus_odysseus
 zeus_perseus Zeus_persian Zeus_Poseidon Zeus_Sanctuary1 Zeus_Sanctuary2 Zeus_Sanctuary3 zeus_satyr zeus_scylla
 zeus_statcon1 zeus_talos zeus_theseus Zeus_trojan Zeus_Zeus""".split()
# hi-res sets (docs/play/hires.md "Pipeline"): the upscaler's inputs, for --hires upscale
HIRES_SETS = [
    ("terrain", ["--context", "1"], ["Zeus_Terrain"]),
    ("buildings", [], "destruction Poseidon_AtlasStat Poseidon_GrandStatue1 Poseidon_GrandStatue2 Poseidon_GrandStatue3 "
                      "Poseidon_HeraStat Poseidon_Loaded Poseidon_Sanctuary3 Poseidon_Unloaded Zeus_General Zeus_God01 "
                      "Zeus_God02 Zeus_God03 Zeus_God04 Zeus_God05 Zeus_God06 Zeus_God07 Zeus_God08 Zeus_God09 Zeus_God10 "
                      "Zeus_God11 Zeus_God12 Zeus_Greek Zeus_Sanctuary1 Zeus_Sanctuary2 Zeus_Sanctuary3 zeus_statcon1 "
                      "Zeus_Unloaded".split()),
    ("figures", [], ["SprMain", "PoseidonImps", "SprAmbient"]),
    ("ui", [], ["Zeus_Interface"]),                    # + the 17 Zeus_Fonts groups (added in upscale())
]


class Fail(Exception):
    pass


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run(*cmd, cwd=ROOT):
    print("  $", " ".join(os.path.relpath(c, ROOT) if os.path.isabs(str(c)) and str(c).startswith(ROOT) else str(c)
                          for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd)
    if r.returncode:
        raise Fail(f"step failed (exit {r.returncode}): {' '.join(map(str, cmd))}")


# ---------------------------------------------------------------- the game folder

def game_folder(path):
    """The folder holding Zeus.exe: PATH itself, or PATH/app (innoextract's output), else a clear error."""
    for p in (path, os.path.join(path, "app")):
        if os.path.isfile(os.path.join(p, "Zeus.exe")):
            missing = [n for n in NEEDED if not os.path.exists(os.path.join(p, n))]
            if missing:
                raise Fail(f"{p}: not a complete Zeus + Poseidon folder, missing: {', '.join(missing)}")
            return os.path.abspath(p)
    raise Fail(f"{path}: no Zeus.exe here (give the game folder: the one with Zeus.exe, DATA/, Model/, Adventures/, "
               f"Audio/; or --installer setup_zeus_and_poseidon_2.1.0.10.exe)")


def link_game(src):
    """zeus-original/app -> the game folder (symlink; a copy of the runtime folders where links are not allowed)."""
    src = os.path.realpath(src)
    if os.path.lexists(GAME):
        if os.path.realpath(GAME) == src:
            return
        if os.path.islink(GAME):
            os.remove(GAME)
        elif not os.path.exists(os.path.join(GAME, "Zeus.exe")):
            raise Fail(f"{rel(GAME)} exists without Zeus.exe (an asset-pack install?): move it away to build from {src}")
        else:
            raise Fail(f"{rel(GAME)} is another game folder: remove it or pass --game {rel(GAME)}")
    os.makedirs(os.path.dirname(GAME), exist_ok=True)
    try:
        os.symlink(src, GAME, target_is_directory=True)
        print(f"  {rel(GAME)} -> {src}")
    except OSError:
        print(f"  no symlinks here: copying {src} to {rel(GAME)}")
        shutil.copytree(src, GAME)


def from_installer(exe):
    if not shutil.which("innoextract"):
        raise Fail("innoextract not found (https://constexpr.org/innoextract/, e.g. `brew install innoextract`, "
                   "`apt install innoextract`); or unpack the installer yourself and pass --game")
    out = os.path.join(ROOT, "zeus-original")
    if os.path.exists(os.path.join(out, "app", "Zeus.exe")):
        print(f"  {rel(out)}/app already unpacked")
    else:
        run("innoextract", "-s", "-d", out, exe)
    return os.path.join(out, "app")


# ---------------------------------------------------------------- the game's text (pool) and the templates

class PE:
    """Zeus.exe's sections, enough to read data at a virtual address (stdlib only)."""
    def __init__(self, path):
        self.d = open(path, "rb").read()
        pe = struct.unpack_from("<I", self.d, 0x3C)[0]
        nsec, = struct.unpack_from("<H", self.d, pe + 6)
        opt, = struct.unpack_from("<H", self.d, pe + 20)
        self.base, = struct.unpack_from("<I", self.d, pe + 24 + 28)
        o = pe + 24 + opt
        self.secs = [struct.unpack_from("<4I", self.d, o + 40 * i + 8) for i in range(nsec)]   # vsize, va, rawsize, raw

    def read(self, va, n):
        rva = va - self.base
        for vs, sva, _, raw in self.secs:
            if sva <= rva < sva + vs:
                return self.d[raw + rva - sva:raw + rva - sva + n]
        raise ValueError(hex(va))


def text_pool(game=GAME):
    """id -> string of every text the game ships that our data quotes: Zeus_Text.eng ("t:GROUP:INDEX"), the help
    records of Zeus_MM.eng ("mm:RECORD:FIELD", 0 title, 1 caption, 2 body), Model/Zeus eventmsg.txt ("ev:NAME", read
    as the exe does, tools/build_messages.py); "~n" after an id = whitespace collapsed (" ".join(s.split()))."""
    import engtext
    import build_messages
    out = {}
    for g, ss in engtext.read(os.path.join(game, "Zeus_Text.eng")).items():
        for i, s in enumerate(ss):
            out[f"t:{g}:{i}"] = s
    d = open(os.path.join(game, "Zeus_MM.eng"), "rb").read()
    n, = struct.unpack_from("<I", d, 0x14)
    for i in range(n):
        for k, o in enumerate(struct.unpack_from("<3I", d, 0x18 + 80 * i + 0x44)):
            if o:
                out[f"mm:{i}:{k}"] = d[0x13898 + o:d.index(b"\0", 0x13898 + o)].decode("cp1252")
    names = build_messages.phrase_names(PE(os.path.join(game, "Zeus.exe")).read)
    texts = build_messages.parse(open(os.path.join(game, "Model", "Zeus eventmsg.txt"), "rb").read(),
                                 {x.lower() for x in names})
    for name in names:
        if name.lower() in texts:
            out["ev:" + name.lower()] = texts[name.lower()]
    for k, s in list(out.items()):
        c = " ".join(s.split())
        if c != s:
            out[k + "~n"] = c
    return out


def resolve(pool, ref):
    if ref not in pool:
        raise Fail(f"text {ref} not in the game's files (another game version?)")
    return pool[ref]


LIT = re.compile(r'"(?:[^"\\]|\\.)*"')
REF_LIT = re.compile(r'"@\{([^{}"\\]+)\}(u?)"')
REF = re.compile(r"@\{[^{}]*\}u?")
IDENT = re.compile(r"[a-z0-9_]+|[A-Z0-9_]+|[A-Z][a-z]?")
KEEP = {"Normal", "Easy", "Hard", "Impossible", "Very Easy"}      # difficulty names: our keys too


def quotable(s):
    """A string that is the game's writing if the game ships it: not one of our identifiers (lower-case ids,
    upper-case names, compass points), not a bare number or sign."""
    return re.search(r"[A-Za-z]", s) is not None and len(s.strip()) > 1 and not IDENT.fullmatch(s) and s not in KEEP


def split_text(text, index):
    """JSON text -> (template text, references made, game strings left in it). Each string literal that is a game
    text becomes "@{ID}" ("@{ID}u": written without \\u escapes); everything else stays byte for byte."""
    out, pos, n, left = [], 0, 0, []
    for m in LIT.finditer(text):
        lit = m.group(0)
        s = json.loads(lit)
        if REF.fullmatch(s):
            raise Fail(f"a string looks like a reference: {lit}")
        rid = index.get(s) if quotable(s) else None
        if rid is None:
            continue
        rep = f'"@{{{rid}}}"' if lit == json.dumps(s) else f'"@{{{rid}}}u"' if lit == json.dumps(s, ensure_ascii=False) else None
        if rep is None:
            left.append(s)
            continue
        out += [text[pos:m.start()], rep]
        pos, n = m.end(), n + 1
    out.append(text[pos:])
    return "".join(out), n, left


def merge_text(tmpl, pool):
    return REF_LIT.sub(lambda m: json.dumps(resolve(pool, m.group(1)), ensure_ascii=not m.group(2)), tmpl)


def templates():
    """runtime paths (relative to the repo) that have a template"""
    out = []
    for d, _, fs in os.walk(TEMPLATES):
        out += [rel(os.path.join(d, f))[len("assets/templates/"):] for f in fs if f.endswith(".json")]
    return sorted(out)


def pool_index(pool):
    ix = {}
    for k, s in pool.items():                    # first id wins: t, then mm, then ev; raw before ~n
        ix.setdefault(s, k)
    return ix


# our own files whose few game words are names we chose (Sardis, Troy; "Blank" army): not templated
OURS = {"data/trade.json", "data/world/partners.json", "data/world/wartest.json", "data/military.json"}


def scan_candidates(index):
    """tracked JSON files (data/, extracted/model/) that quote the game's text"""
    files = subprocess.run(["git", "ls-files", "data/*.json", "data/**/*.json", "extracted/model/*.json"], cwd=ROOT,
                           capture_output=True, text=True).stdout.split()
    files = [f for f in sorted(set(files)) if not GENERATED_RE.fullmatch(f) and f not in OURS]
    return [f for f in files if split_text(open(os.path.join(ROOT, f), encoding="utf-8").read(), index)[1]]


def cmd_split(a):
    pool = text_pool()
    index = pool_index(pool)
    files = scan_candidates(index) if a.scan else (a.files or templates())
    total = 0
    for f in files:
        f = rel(os.path.abspath(f)) if os.path.exists(f) else f
        text = open(os.path.join(ROOT, f), encoding="utf-8").read()
        t, n, left = split_text(text, index)
        if left:
            raise Fail(f"{f}: {len(left)} game strings not written as json.dumps writes them: {left[:3]}")
        if merge_text(t, pool) != text:
            raise Fail(f"{f}: the template does not merge back to the file")
        p = os.path.join(TEMPLATES, f)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if not os.path.exists(p) or open(p, encoding="utf-8").read() != t:
            open(p, "w", encoding="utf-8").write(t)
            print(f"  {rel(p)}: {n} strings")
        total += n
    write_gitignore()
    print(f"{len(files)} templates, {total} strings referenced")


def cmd_merge(a=None, pool=None):
    pool = pool or text_pool()
    for f in templates():
        t = open(os.path.join(TEMPLATES, f), encoding="utf-8").read()
        out = merge_text(t, pool)
        json.loads(out)
        p = os.path.join(ROOT, f)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if not os.path.exists(p) or open(p, encoding="utf-8").read() != out:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(out)
    print(f"  {len(templates())} files from assets/templates/")


# ---------------------------------------------------------------- what the assets are (manifest)

# whole files the build writes (git-ignored; the templates' outputs are added by write_gitignore)
GENERATED = ["extracted/text/zeus_text.json", "extracted/text/zeus_text.txt", "extracted/model/model_*.json",
             "extracted/model/tax_sentiment.json"]
GENERATED_RE = re.compile("|".join(fnmatch.translate(g) for g in GENERATED))


def part_of(path):
    if path.startswith(ATLAS + "/hires/"):
        return "hires"
    if path.startswith(ATLAS + "/") and (path.endswith(".bin") or path == ATLAS + "/compressed.json"):
        return "gpu"
    if path.startswith("extracted/") and path != "extracted/text/zeus_text.json":
        return "dev"
    return "base"


def walk(top):
    out = []
    for d, dirs, fs in os.walk(os.path.join(ROOT, top)):
        dirs[:] = sorted(x for x in dirs if not os.path.islink(os.path.join(d, x)))
        out += [rel(os.path.join(d, f)) for f in sorted(fs)
                if not os.path.islink(os.path.join(d, f)) and f != ".DS_Store"]
    return out


def asset_files():
    """every asset path in the tree, by the rules of docs/assets.md"""
    out = set(templates())
    for g in GENERATED:
        d, pat = os.path.split(g)
        if os.path.isdir(os.path.join(ROOT, d)):
            out |= {f"{d}/{f}" for f in os.listdir(os.path.join(ROOT, d)) if fnmatch.fnmatch(f, pat)}
    for top in ("zeus-original/app/Adventures", "zeus-original/app/Audio", "viewer/sprites", ATLAS + "/backdrops",
                ATLAS + "/world", ATLAS + "/hires"):
        out |= set(walk(top))
    # GPU copies: only of the sheets compressed.json lists (play mode loads no others; hires_compress.py leaves out
    # the interface, the fonts and the alpha-blended files)
    cp = os.path.join(ROOT, ATLAS, "compressed.json")
    cmp = json.load(open(cp)) if os.path.exists(cp) else {"sheets": {}, "formats": {}}
    if os.path.exists(cp):
        out.add(ATLAS + "/compressed.json")
    for name in ATLAS_FILES:
        j = os.path.join(ROOT, ATLAS, name + ".json")
        if os.path.exists(j):
            out.add(rel(j))
            for s in json.load(open(j))["sheets"]:
                out.add(f"{ATLAS}/{s}")
                if s in cmp["sheets"]:
                    out |= {f"{ATLAS}/{s[:-4]}{f['suffix']}" for f in cmp["formats"].values()}
    return sorted(out)


def load_manifest(path=MANIFEST):
    try:
        return json.load(open(path))
    except OSError:
        return {"files": {}}


def write_manifest(files, path=MANIFEST):
    """{path: [size, sha256, part]}, one line per file (diffs stay readable)"""
    rows = ",\n".join(f"  {json.dumps(p)}: {json.dumps(v)}" for p, v in sorted(files.items()))
    head = {"format": 1, "game": "Zeus + Poseidon, GOG 2.1.0.10 (Zeus.exe sha256 " + GOG_EXE_SHA256 + ")",
            "note": "tools/assets.py: every file built from the game or installed from the asset pack (docs/assets.md)"}
    with open(path, "w") as f:
        f.write("{\n" + "".join(f" {json.dumps(k)}: {json.dumps(v)},\n" for k, v in head.items()) +
                ' "files": {\n' + rows + "\n }\n}\n")


def cmd_manifest(a):
    files = {p: [os.path.getsize(os.path.join(ROOT, p)), sha256(os.path.join(ROOT, p)), part_of(p)] for p in asset_files()}
    old = load_manifest()["files"]
    keep = {p: v for p, v in old.items() if p not in files and v[2] in (a.keep or [])}    # parts not in this tree
    write_manifest({**keep, **files})
    by = {}
    for v in {**keep, **files}.values():
        by.setdefault(v[2], [0, 0])
        by[v[2]][0] += 1
        by[v[2]][1] += v[0]
    print(f"{rel(MANIFEST)}: " + ", ".join(f"{k} {n} files {b / 1e6:.0f} MB" for k, (n, b) in sorted(by.items())))


def verify(parts, quiet=False):
    """files of the parts that are missing or differ from assets/manifest.json: [(path, why)]"""
    bad = []
    for p, (size, h, part) in sorted(load_manifest()["files"].items()):
        if part not in parts:
            continue
        f = os.path.join(ROOT, p)
        if not os.path.isfile(f):
            bad.append((p, "missing"))
        elif os.path.getsize(f) != size or sha256(f) != h:
            bad.append((p, "differs"))
    if not quiet:
        for p, why in bad[:40]:
            print(f"  {why}: {p}")
        if len(bad) > 40:
            print(f"  ... {len(bad) - 40} more")
    return bad


def cmd_verify(a):
    parts = a.parts.split(",")
    bad = verify(parts)
    n = sum(1 for v in load_manifest()["files"].values() if v[2] in parts)
    print(f"{n - len(bad)} of {n} files as in {rel(MANIFEST)} ({','.join(parts)})")
    return 1 if bad else 0


def write_gitignore():
    """the block of generated files in .gitignore (the templates' outputs and GENERATED)"""
    start, end = "# assets: generated by tools/assets.py (docs/assets.md) - begin", "# assets - end"
    body = [start, "# the game's text, built from your copy or installed from the asset pack"] + GENERATED + \
        ["/" + t for t in templates()] + [end]
    s = open(GITIGNORE).read() if os.path.exists(GITIGNORE) else ""
    if start in s:
        s = s[:s.index(start)] + "\n".join(body) + s[s.index(end) + len(end):]
    else:
        s = s.rstrip("\n") + "\n" + "\n".join(body) + "\n"
    open(GITIGNORE, "w").write(s)


# ---------------------------------------------------------------- pack / install

STORED = (".png", ".jpg", ".mp3")             # already compressed: stored as is


def cmd_pack(a):
    parts = a.parts.split(",")
    man = {p: v for p, v in load_manifest()["files"].items() if v[2] in parts}
    if not man:
        raise Fail(f"no files of {parts} in {rel(MANIFEST)}")
    bad = verify(parts)
    if bad:
        raise Fail(f"{len(bad)} files differ from {rel(MANIFEST)} (above): build or install them first, "
                   f"or run `tools/assets.py manifest`")
    out = os.path.abspath(a.out)
    tmp = out + ".part"
    with zipfile.ZipFile(tmp, "w", allowZip64=True) as z:
        def add(name, data=None, path=None):
            zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            zi.external_attr = 0o644 << 16
            zi.compress_type = zipfile.ZIP_STORED if name.lower().endswith(STORED) else zipfile.ZIP_DEFLATED
            if data is not None:
                z.writestr(zi, data, compresslevel=6)
            else:
                with open(path, "rb") as src, z.open(zi, "w", force_zip64=True) as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
        head = {"format": 1, "parts": parts, "files": man}
        add("openzeus-assets.json", json.dumps(head, indent=0, sort_keys=True).encode())
        for i, p in enumerate(sorted(man)):
            add(p, path=os.path.join(ROOT, p))
            if i % 200 == 0:
                print(f"  {i}/{len(man)} {p}", flush=True)
    os.replace(tmp, out)
    size = sum(v[0] for v in man.values())
    print(f"{out}: {len(man)} files, {size / 1e6:.0f} MB -> {os.path.getsize(out) / 1e6:.0f} MB")


def fetch(src):
    if not re.match(r"https?://", src):
        if not os.path.isfile(src):
            raise Fail(f"{src}: no such pack")
        return src
    d = os.path.join(ROOT, ".cache", "assets")
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, os.path.basename(src.split("?")[0]) or "pack.zip")
    if not os.path.exists(dst):
        print(f"  downloading {src}")
        with urllib.request.urlopen(src) as r, open(dst + ".part", "wb") as f:
            total, got = int(r.headers.get("Content-Length") or 0), 0
            for b in iter(lambda: r.read(1 << 20), b""):
                f.write(b)
                got += len(b)
                if total and got % (64 << 20) < (1 << 20):
                    print(f"  {got / 1e6:.0f} / {total / 1e6:.0f} MB", flush=True)
        os.replace(dst + ".part", dst)
    return dst


def install(src, parts=PACKED, force=False):
    """unpack the files of `parts` from a pack, checking each against the pack's and the repo's manifest"""
    path = fetch(src)
    want = load_manifest()["files"]
    n = skipped = 0
    with zipfile.ZipFile(path) as z:
        try:
            head = json.loads(z.read("openzeus-assets.json"))
        except KeyError:
            raise Fail(f"{src}: not an OpenZeus asset pack (no openzeus-assets.json)")
        files = {p: v for p, v in head["files"].items() if v[2] in parts}
        stale = [p for p, v in files.items() if p in want and want[p][1] != v[1]]
        if stale and not force:
            raise Fail(f"{src}: {len(stale)} files differ from this checkout's {rel(MANIFEST)} (e.g. {stale[0]}): "
                       f"the pack is for another version of the code (--force installs it anyway)")
        names = set(z.namelist())
        for p, (size, h, part) in sorted(files.items()):
            if p.startswith("/") or ".." in p.split("/") or part_of(p) != part or p not in names:
                raise Fail(f"{src}: bad entry {p}")
            f = os.path.join(ROOT, p)
            if os.path.isfile(f) and os.path.getsize(f) == size and sha256(f) == h:
                skipped += 1
                continue
            if os.path.islink(GAME) and p.startswith("zeus-original/app/"):
                raise Fail(f"{p} differs in the game folder {os.path.realpath(GAME)} (not written to; another game version?)")
            os.makedirs(os.path.dirname(f), exist_ok=True)
            hh = hashlib.sha256()
            with z.open(p) as zf, open(f + ".part", "wb") as out:
                for b in iter(lambda: zf.read(1 << 20), b""):
                    hh.update(b)
                    out.write(b)
            if hh.hexdigest() != h:
                os.remove(f + ".part")
                raise Fail(f"{src}: {p} is corrupt (sha256)")
            os.replace(f + ".part", f)
            n += 1
    missing = [p for p, v in want.items() if v[2] in parts and v[2] in head["parts"] and p not in files]
    print(f"  {src}: {n} files written, {skipped} already there" + (f"; {len(missing)} of the manifest's files not in it"
                                                                     if missing else ""))
    return head["parts"]


def cmd_install(a):
    got = set()
    for src in a.packs:
        got |= set(install(src, force=a.force))
    bad = verify(sorted(got & set(PACKED)))
    if bad:
        raise Fail(f"{len(bad)} files missing or different after the install (above)")
    print(f"installed: {', '.join(sorted(got))}" + ("" if "hires" in got else " (no hi-res sprites: the hires pack adds them)"))


# ---------------------------------------------------------------- build

def has_encoders(bc7enc, py=sys.executable):
    """astc-encoder-py importable by python `py`, and the bc7e binary (docs/play/hires.md step 4)"""
    if subprocess.run([py, "-c", "import astc_encoder"], capture_output=True).returncode:
        return False
    return bool(bc7enc) and os.access(bc7enc, os.X_OK)


def upscale():
    """--hires upscale: docs/play/hires.md "Reproduce from scratch" (models in $ZEUS_ESRGAN or .cache/esrgan)"""
    if not os.environ.get("ZEUS_ESRGAN") and not os.path.isdir(os.path.join(ROOT, ".cache", "esrgan")):
        raise Fail("--hires upscale needs the ESRGAN models and a venv with spandrel + torch: docs/play/hires.md "
                   "\"Reproduce from scratch\" step 1 ($ZEUS_ESRGAN or .cache/esrgan)")
    fonts = json.load(open(os.path.join(ROOT, "extracted", "sprites", "Zeus_Fonts", "atlas.json")))
    G = ["Zeus_Fonts@" + g["name"] for g in fonts["groups"] if g["name"].startswith("SPR_FONTS")]
    cmd = [sys.executable, os.path.join(TOOLS, "upscale_sprites.py"), "--scale", "4", "--out",
           os.path.join(ROOT, "extracted", "hires"), "--methods", "remacri"]
    for name, opts, files in HIRES_SETS:
        cmd += ["--set", name, "--alpha", "auto", *opts, *files, *(G if name == "ui" else [])]
    run(*cmd)
    run(sys.executable, os.path.join(TOOLS, "hires_derive.py"), "--scale", "2")


def cmd_build(a):
    print("1. game folder")
    src = from_installer(a.installer) if a.installer else a.game
    if not src:
        raise Fail("give --game PATH (the game folder) or --installer SETUP.exe")
    game = game_folder(src)
    link_game(game)
    h = sha256(os.path.join(GAME, "Zeus.exe"))
    if h != GOG_EXE_SHA256:
        print(f"  warning: Zeus.exe is not the GOG 2.1.0.10 build ({h[:12]}...): the files may differ from the pack's")
    py = sys.executable
    T = lambda n: os.path.join(TOOLS, n)          # noqa: E731
    print("2. text: Zeus_Text.eng -> extracted/text/, Model/ -> extracted/model/ (tools/engtext.py, tools/model.py)")
    os.makedirs(os.path.join(ROOT, "extracted", "text"), exist_ok=True)
    run(py, T("engtext.py"), os.path.join(GAME, "Zeus_Text.eng"), os.path.join(ROOT, "extracted", "text", "zeus_text"))
    run(py, T("model.py"), os.path.join(GAME, "Model"), os.path.join(ROOT, "extracted", "model"))
    print("3. the game's strings into data/ (assets/templates/)")
    cmd_merge()
    print("4. sprites: DATA/*.sg3 -> extracted/sprites/ (tools/sg3.py)")
    names = sorted(set(ATLAS_FILES) | ({f for _, _, fs in HIRES_SETS for f in fs} if a.hires == "upscale" else set()))
    run(py, T("sg3.py"), "export", os.path.join(GAME, "DATA"), os.path.join(ROOT, "extracted", "sprites"),
        *([] if a.all_sprites else names))
    print("5. play mode's sheets, backdrops, world map, viewer sprites")
    run(py, T("play_atlas.py"), *ATLAS_FILES)
    run(py, T("play_backdrops.py"))
    run(py, T("viewer_sprites.py"))
    packs = a.pack or []
    epy = a.encoder_python or py
    gpu = a.gpu or ("pack" if packs else "build" if has_encoders(a.bc7enc, epy) else "skip")
    hires = a.hires or ("pack" if packs else "skip")
    print(f"6. GPU-compressed sheets: {gpu}; hi-res sets: {hires}")
    if gpu == "build":
        if not has_encoders(a.bc7enc, epy):
            raise Fail("--gpu build needs astc-encoder-py (in this python or --encoder-python PY) and the bc7e binary "
                       "(--bc7enc PATH; sh tools/build_bc7enc.sh): docs/play/hires.md step 4")
        run(epy, T("hires_compress.py"), "--originals", "--bc7enc", a.bc7enc)
    want = [p for p, o in (("gpu", gpu), ("hires", hires)) if o == "pack"]
    if want:
        if not packs:
            raise Fail(f"--{'/--'.join(want)} pack needs --pack ZIP|URL (the asset pack with those parts)")
        for p in packs:
            install(p, parts=want, force=a.force)
    if hires == "upscale":
        upscale()
        if has_encoders(a.bc7enc, epy):
            run(epy, T("hires_compress.py"), "--bc7enc", a.bc7enc)
    print("7. check against assets/manifest.json")
    parts = ["base", "dev"] + [p for p, o in (("gpu", gpu), ("hires", hires)) if o in ("pack", "build")]
    bad = verify(parts)
    n = sum(1 for v in load_manifest()["files"].values() if v[2] in parts)
    print(f"  {n - len(bad)} of {n} files as in the manifest ({','.join(parts)})")
    if bad:
        print("  differences: another game version, or other Pillow/zlib versions than requirements.txt "
              "(PNG bytes; the pictures are the same)")
        if a.strict:
            return 1
    print("done." + ("" if hires != "skip" else " Hi-res sprites: not built (--hires pack --pack ZIP|URL adds them)."))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the assets from your copy of the game")
    b.add_argument("--game", help="the game folder (with Zeus.exe)")
    b.add_argument("--installer", help="the GOG installer .exe (unpacked with innoextract into zeus-original/)")
    b.add_argument("--hires", choices=("pack", "skip", "upscale"), help="hi-res sets: from --pack (default with "
                   "--pack), skip (default without), or upscale (ML models + GPU, docs/play/hires.md; not byte-identical)")
    b.add_argument("--gpu", choices=("pack", "build", "skip"), help="GPU-compressed sheets: from --pack, build "
                   "(encoders, default when present), or skip (play mode loads the PNGs)")
    b.add_argument("--pack", action="append", help="asset pack (zip or URL) for --hires/--gpu pack; repeatable")
    b.add_argument("--bc7enc", default=os.environ.get("BC7ENC") or os.path.join(ROOT, ".cache", "bc7enc", "bc7e"))
    b.add_argument("--encoder-python", help="python with astc-encoder-py for the GPU-compressed sheets (default: this one)")
    b.add_argument("--all-sprites", action="store_true", help="export every .sg3 to extracted/sprites (contributors)")
    b.add_argument("--strict", action="store_true", help="exit 1 when a file differs from the manifest")
    b.add_argument("--force", action="store_true", help="install a pack made for another version of the code")
    i = sub.add_parser("install", help="install the assets from the asset pack(s)")
    i.add_argument("packs", nargs="+")
    i.add_argument("--force", action="store_true")
    p = sub.add_parser("pack", help="write the asset pack from this tree")
    p.add_argument("out")
    p.add_argument("--parts", default="base,gpu,hires")
    v = sub.add_parser("verify", help="check the files against assets/manifest.json")
    v.add_argument("--parts", default="base,gpu,hires")
    m = sub.add_parser("manifest", help="(contributors) rewrite assets/manifest.json from the tree")
    m.add_argument("--keep", action="append", help="keep the manifest's entries of this part when its files are absent")
    s = sub.add_parser("split", help="(contributors) runtime JSON -> assets/templates/")
    s.add_argument("files", nargs="*")
    s.add_argument("--scan", action="store_true")
    sub.add_parser("merge", help="assets/templates/ + the game's text -> runtime JSON")
    a = ap.parse_args(argv)
    try:
        return {"build": cmd_build, "install": cmd_install, "pack": cmd_pack, "verify": cmd_verify,
                "manifest": cmd_manifest, "split": cmd_split, "merge": cmd_merge}[a.cmd](a) or 0
    except Fail as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
