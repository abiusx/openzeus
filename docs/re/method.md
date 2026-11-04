# RE method (read this before working on a subsystem)

## Goal
For each subsystem, a doc in `docs/logic/<subsystem>.md` precise enough to re-implement the
behavior in Python **identically** (same integers, same order of operations, same RNG draws),
so our port can be diffed tick by tick against the original.

## Tools
- `re/decomp/zeus.c`: full Ghidra decompile (~280k lines). Functions are headed
  `// ===== name @ address, N bytes =====`.
- `python3 tools/fn.py NAME_OR_ADDR ...` prints functions; `python3 tools/fn.py --callers NAME` lists callers.
- `re/venv/bin/python tools/disasm.py ADDR [N]`: raw disassembly. Use it when the decompiler
  drops register arguments (e.g. `__fastcall`/ECX "this" pointers) or the output looks wrong.
- `extracted/model/*.json`: the parsed model tables (see docs/logic/housing-evolution.md for the house columns).
- `docs/re/structs.md`: shared field names. `refs/zeus-poseidon-arm64/formats/sav.md`: every
  saved block (= simulation state) with its address. `refs/zeus-poseidon-arm64/docs/engine/*.md`:
  tick order, terrain, rendering, verified facts. Partly French.
- `refs/eZeus/`: readable C++ remake. Use it to learn **what** exists and to guess names. **Never**
  use it for numbers or formulas: it is known to differ (e.g. its housing uses invented pow() formulas).
- Game text: `zeus-original/app/Zeus_Text.eng` (strings) helps identify reason codes and messages.
- `zeus-original/app/*.pdf`: manuals (designer intent).
- **Do not run Ghidra** (the project is single-user and locked). To rename things, add rows to
  `re/names/<subsystem>.tsv` and `re/structs/<subsystem>.tsv`; they are applied in batches
  (`re/ghidra/refresh.sh`, run by the coordinator), after which zeus.c is regenerated.

## Naming files
- `re/names/<subsystem>.tsv`: `address<TAB>name<TAB>function|data<TAB>type<TAB>evidence`.
  Function names are snake_case and describe what the function does. Only name what you've understood.
- `re/structs/<subsystem>.tsv`: `struct<TAB>offset<TAB>type<TAB>name` (types u8 i8 u16 i16 u32 i32,
  `[n]` arrays). Add fields to the existing `Building`/`Figure` structs, or define new structs
  with a `size` row. Don't redefine fields someone else already named unless you're correcting them
  (then say so in the evidence/doc).

## Doc format (`docs/logic/<subsystem>.md`)
- Start with a short summary of the mechanic in plain words.
- Then the exact rules as pseudocode, with integer arithmetic exactly as the exe does it
  (division truncation, clamping, order of updates, when RNG is drawn and which RNG variable).
- Every rule is tagged **verified** (read in the code, with the function address) or
  **hypothesis** (with the reason).
- Constants: give the value and where it comes from (model column, immediate in code, table address).
- When it runs: which tick step / cycle step / month event, and at what frequency.
- State: which fields/grids it reads and writes.
- An "Open questions" section at the end.
- Write in English.
