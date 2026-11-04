# re/oracle: running the original game as a reference

What is here (the rest of re/oracle, the runs, is made on your machine and never committed):
- `scenarios/`: our oracle scenarios (`*.txt` scripts of clicks, keys and shots; `*.poke` memory pokes). MIT, as the
  rest of this repository.
- `zeus-run-state-dump.patch`: our state-dump and poke additions to the `zeus-run` emulator of
  [zeus-poseidon-arm64](https://github.com/nic0lasm/zeus-poseidon-arm64), applied on top of its commit in
  `zeus-run-base-commit`. The patch modifies a GPL program, so **this one file is licensed under the GNU General
  Public License, version 2 or (at your option) any later version**, the licence of the program it patches; it
  is not under this repository's MIT licence. It is development tooling only: neither the game nor any other file
  here uses or contains it.

How to build the emulator with the patch, run a scenario and compare its dumps with ours: docs/re/oracle.md.
