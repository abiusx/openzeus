#!/bin/sh
# Re-apply re/names + re/structs to the Ghidra project and re-export re/decomp/zeus.c.
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Upstream names (GPL, not committed): fetched at a pinned commit into re/names/.upstream/ (tools/upstream_names.py).
python3 "$ROOT/tools/upstream_names.py" > /dev/null
"$ROOT/re/ghidra/headless.sh" -process Zeus.exe -noanalysis \
  -postScript ApplyNames.java "$ROOT/re/names" "$ROOT/re/structs" "$ROOT/re/names/.upstream" \
  -postScript DecompileAll.java "$ROOT/re/decomp/zeus.c.new" > "$ROOT/re/ghidra/refresh.log" 2>&1
mv "$ROOT/re/decomp/zeus.c.new" "$ROOT/re/decomp/zeus.c"
grep -E "ApplyNames|DecompileAll|ERROR" "$ROOT/re/ghidra/refresh.log" | head -20
