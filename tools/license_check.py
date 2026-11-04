"""Find code in our tree that is shared with the third-party (GPL) references in refs/.

Two checks, both reporting only OUR side (file, line, our text), so the tool can be run while rewriting without
showing their code:
  lines   a line of ours whose whitespace-normalized text also occurs in a reference file (non-trivial lines only:
          >= MIN_CHARS characters after normalization, not a bare keyword/bracket/import/comment line)
  tokens  a run of >= NGRAM consecutive tokens (identifiers, numbers, strings, operators; comments dropped)
          shared with a reference file of any language: catches copies with changed layout or names kept
Usage:
    python3 tools/license_check.py [--all] [--ngram N] [--min-chars N] [PATH ...]   (default: our tracked code)
Each hit is classed code / data (mostly numbers or strings: a table of format facts) / idiom (generic stdlib
vocabulary only; hidden unless --all). Exit status 1 when any code hit is found.
docs/references.md "GPL hygiene" describes how it was used and the result.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFS = [os.path.join(ROOT, "refs", r) for r in ("zeus-poseidon-arm64", "eZeus")]
CODE_EXT = {".py", ".js", ".mjs", ".java", ".sh", ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".patch", ".html",
            ".css", ".glsl", ".cmake", ".txt", ".tsv", ".json", ".md"}
OUR_EXT = {".py", ".js", ".mjs", ".java", ".sh", ".c", ".h", ".cpp", ".html", ".css", ".glsl"}
MIN_CHARS = 25
NGRAM = 20
TRIVIAL = re.compile(r"^(import |from \S+ import |#|//|/\*|\*|else:|try:|finally:|return$|pass$|break$|continue$|"
                     r"[\]\)\}\{\[;,:]+$|if __name__ == .__main__.:$|main\(sys\.argv\[1:\]\)$)")
TOKEN = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|0[xX][0-9a-fA-F]+|\d+|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|"
                   r"==|!=|<=|>=|<<|>>|\*\*|//|->|&&|\|\||[^\s\w]")


# Generic Python/stdlib/Ghidra-API vocabulary: a hit made only of these (plus punctuation) is an idiom, not a copy
# (ROOT = os.path.dirname(...), sys.path.insert, argparse set-up, open(...).read()). --all shows them too.
GENERIC = set("""import from as def return if else elif for in while not and or is None True False with try except
pass break continue class self lambda yield raise global nonlocal os sys path dirname abspath __file__ join insert
ROOT argparse ArgumentParser description __doc__ formatter_class RawDescriptionHelpFormatter add_argument
parse_args main argv open read write rb wb r w f d p out OUT makedirs exist_ok struct unpack_from subprocess run
urllib request json load dump print len range int str bytes bytearray list dict set tuple enumerate zip sorted
isfile isdir exists listdir basename splitext executable check capture_output text stdout def __init__ path
FileNotFoundError KeyError ValueError hex n i k v x y buf pos end tools re time hashlib math ap pe address
profile dest folder name splitext basename zipfile lines
java io PrintWriter decompiler DecompInterface DecompileResults listing Program util task TaskMonitor
public private class extends Override void throws Exception String args getScriptArgs ghidra app script GhidraScript
program model address Address data listing Function symbol SourceType getFunctionAt""".split())
IDENT = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")


def kind(tokens):
    """'idiom' (generic vocabulary only), 'data' (mostly numbers/strings: a table of facts), or 'code'."""
    ids = [t for t in tokens if IDENT.match(t)]
    lits = [t for t in tokens if t[0].isdigit() or t[0] in "\"'"]
    if all(t in GENERIC for t in ids):
        return "idiom" if len(lits) < len(tokens) // 3 else "data"
    if len(lits) * 2 >= len([t for t in tokens if t not in ",:-[]{}()"]):
        return "data"
    return "code"


def norm(line):
    return " ".join(line.split())


def strip_comments(text, ext):
    if ext in (".py", ".sh"):
        text = re.sub(r"(?m)#.*$", "", text)
        text = re.sub(r'"""[\s\S]*?"""', "", text)
    else:
        text = re.sub(r"/\*[\s\S]*?\*/", "", text)
        text = re.sub(r"(?m)//.*$", "", text)
    return text


def ref_files():
    for base in REFS:
        for d, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in (".git", "build", "__pycache__", "node_modules")]
            for f in files:
                if os.path.splitext(f)[1].lower() in CODE_EXT:
                    yield os.path.join(d, f)


def our_files(paths):
    if paths:
        out = []
        for p in paths:
            if os.path.isdir(p):
                out += [os.path.join(d, f) for d, _, fs in os.walk(p) for f in fs]
            else:
                out.append(p)
    else:
        out = subprocess.run(["git", "-C", ROOT, "ls-files"], capture_output=True, text=True).stdout.split()
        out = [os.path.join(ROOT, p) for p in out]
    return [p for p in out if os.path.splitext(p)[1].lower() in OUR_EXT and os.path.isfile(p)]


def read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def main(argv):
    global NGRAM, MIN_CHARS
    args, show = [], {"code", "data"}
    it = iter(argv)
    for a in it:
        if a == "--ngram":
            NGRAM = int(next(it))
        elif a == "--all":
            show = {"code", "data", "idiom"}
        elif a == "--min-chars":
            MIN_CHARS = int(next(it))
        else:
            args.append(a)
    ref_lines = set()
    ref_grams = set()
    nref = 0
    for p in ref_files():
        nref += 1
        text = read(p)
        for line in text.splitlines():
            n = norm(line)
            if len(n) >= MIN_CHARS:
                ref_lines.add(n)
        toks = TOKEN.findall(strip_comments(text, os.path.splitext(p)[1].lower()))
        for i in range(len(toks) - NGRAM + 1):
            ref_grams.add(hash(tuple(toks[i:i + NGRAM])))
    mine = our_files(args)
    hits = 0
    counts = {"code": 0, "data": 0, "idiom": 0}
    for p in mine:
        text = read(p)
        rel = os.path.relpath(p, ROOT)
        for no, line in enumerate(text.splitlines(), 1):
            n = norm(line)
            if len(n) >= MIN_CHARS and not TRIVIAL.match(n) and n in ref_lines:
                k = kind(TOKEN.findall(n))
                counts[k] += 1
                if k in show:
                    print(f"lines  {k:5s} {rel}:{no}: {n}")
                    hits += k != "idiom"
        ext = os.path.splitext(p)[1].lower()
        code = strip_comments(text, ext)
        # token positions -> line numbers of ours
        toks, lines = [], []
        for no, line in enumerate(code.splitlines(), 1):
            for t in TOKEN.findall(line):
                toks.append(t)
                lines.append(no)
        i, run_start = 0, None
        spans = []
        while i <= len(toks) - NGRAM:
            if hash(tuple(toks[i:i + NGRAM])) in ref_grams:
                if run_start is None:
                    run_start = i
            elif run_start is not None:
                spans.append((run_start, i - 1 + NGRAM - 1))
                run_start = None
            i += 1
        if run_start is not None:
            spans.append((run_start, len(toks) - 1))
        for a, b in spans:
            k = kind(toks[a:b + 1])
            counts[k] += 1
            if k in show:
                print(f"tokens {k:5s} {rel}:{lines[a]}-{lines[b]}: {b - a + 1} tokens: "
                      f"{' '.join(toks[a:min(b + 1, a + 30)])}")
                hits += k != "idiom"
    print(f"checked {len(mine)} files of ours against {nref} reference files "
          f"(lines >= {MIN_CHARS} chars, token runs >= {NGRAM}): {counts['code']} code, {counts['data']} data, "
          f"{counts['idiom']} idiom hits")
    return 1 if counts["code"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
