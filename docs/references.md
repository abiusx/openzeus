# External references

Cloned into `refs/` (shallow clones, read-only, not our code). Found 2026-10-26.

## zeus-poseidon-arm64 (`refs/zeus-poseidon-arm64`, GPL-2.0+)
Runs the **original GOG `Zeus.exe`** on Apple Silicon/Linux inside an x86 emulator (Unicorn),
with native rewrites of Windows APIs and hot paths. Targets **the same exe we have** (SHA-256
`382bcd28…75e90a57`, compiled 2002-01-04).
- `formats/`: file formats documented (sg3, pak, map, sav, set, model, eng, eventmsg, layout). Partly in French.
- `tools/`: Python readers for those formats (`sg3.py`, `pakfile.py`, `savefile.py`, `model.py`, `mapfile.py`, `engtext.py`, …) and Ghidra headless scripts (`tools/ghidra/`).
- `analysis/symbols.tsv`: all 4,872 exe functions, 322 named so far, with evidence (`noms.tsv`). `simulation.tsv` lists the functions reached during a tick.
- `docs/engine/simulation.md`: tick order and the 51-step cycle (16 cycles = 1 month). `terrain.md`, `rendering.md`, `interface.md` cover the other areas.
- `tests/scenarios`: ten deterministic replay scenarios that compare full game state tick by tick against the original. **This is our oracle for checking our port**: run a scenario in the original, dump the state, and diff it against our simulation.
- Also a playable build of the original on this Mac (release 1.7), so **we don't need Wine to play/observe the original**.

## eZeus (`refs/eZeus`, GPL-3.0)
A full C++ reimplementation of Zeus + Poseidon, about 440k lines, active (Oct 2026). By the
author's own account, **not an exact copy**: there are accidental differences. It's the most
complete readable description of all the mechanics (buildings, walkers, gods, heroes, monsters,
trade, the sg3 loader), but anything precise must be checked against the exe/model data.

## Others (not cloned)
- andrehamon/zeus-qol: QoL patch, Python, includes a city exporter
- Vicinity4813/zeus-world-maps-tools: world map, scenario and save tools (C#)
- Exiro1/Master-Of-Olympus-Java-Remake (MIT), Vinorcola/CityBuilderEngine (Qt, inactive)
- Julius/Augustus (Caesar III), Akhenaten (Pharaoh): sibling engines with the same architectural lineage

## Licensing note
Both main refs are GPL. Reading them to learn the formats and mechanics is fine. **Copying their
code** into our game makes our game GPL. Policy: our code is written by us from documented
behavior. If we do adapt code, we mark it and accept GPL for that component.

## What we use (2026-11-04; our code is MIT, LICENSE)
No code of either reference is copied into our tree (checked 11-04, "GPL hygiene" below). What we take is facts
and credit them:
- **zeus-poseidon-arm64** (GPL-2.0+, https://github.com/nic0lasm/zeus-poseidon-arm64):
  - file-format facts (sg3/555, map/sav/pak/set container, model, eng text): stated in our own words in
    docs/formats.md and docs/campaign-format.md; our readers (tools/sg3.py, mapfile.py, model.py, engtext.py) are
    our own code.
  - function names for the decompile: their analysis/noms.tsv is not in our repo. tools/upstream_names.py
    fetches it at commit 7aed754 (sha256 pinned) into the git-ignored re/names/.upstream/ when
    re/ghidra/refresh.sh runs; our re/names/*.tsv come after it and win. Our docs and code comments cite some
    of those names with their addresses (facts).
  - the emulator, as our oracle (dev tooling, not shipped): re/oracle/zeus-run-state-dump.patch is a patch to
    their GPL program (base commit re/oracle/zeus-run-base-commit) and stays GPL-2.0+ like it; it is the only
    GPL file in our tree. Scenario files in re/oracle/scenarios/ are our input scripts for their `zeus-run`
    (working-city.txt's event line is the same as theirs: the clicks that open the tutorial).
  - their docs/engine/*.md: hints (tick order, rendering), each checked against the exe.
- **eZeus** (GPL-3.0): hints only (what exists, where to look), always checked against the exe; no code.
- **blast.c** (Mark Adler, zlib licence): the PKWARE DCL format it decodes, and its three fixed code tables
  (format data), in tools/mapfile.py; the decoder is ours.

## GPL hygiene (11-04)
`python3 tools/license_check.py` compares every tracked code file of ours with every file in refs/ (both repos,
3,088 files) and prints only our side: (1) lines identical after whitespace normalization (>= 25 chars, not
bare keywords/brackets/imports/comments), (2) runs of >= 20 identical tokens (identifiers, numbers, strings,
operators; comments dropped; any language). Hits are classed code / data (mostly numbers or strings: tables of
facts) / idiom (only stdlib or Ghidra-API vocabulary, e.g. `ROOT = os.path.dirname(...)`; hidden unless
`--all`). Result 11-04: 0 code hits; 6 data hits, all facts: the exe's walker offset table
(tools/e1_figure_check.py, viewer/play/scene.js), the exe's sprite-collection names (tools/play_ui.py,
viewer/play/play.js), the Windows-1252 code page (viewer/play/text.js), a zero/one table (viewer/play/ui.js).
Rewritten that day from the format facts (docs/formats.md), identity checked with tools/reader_fingerprint.py
(every decoded sprite and map block, before = after) and `tools/sg3.py export` (70,050 output files, same
sha256): tools/sg3.py (decoder), tools/mapfile.py (DCL decoder), tools/model.py (file lookup). Removed: their
Ghidra scripts (re/ghidra/scripts: ApplySymbols, Decompile, ExportCodeMap, ExportFunctions, ExportPcode,
Listing, Xrefs; unused) and ExportDecompiled (replaced by our DecompileAll.java + Decomp.java, same zeus.c
except the header word "bytes"); re/names/00-arm64.tsv (fetched instead, above).
