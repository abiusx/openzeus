"""ZEUS_POKE lines that set figure +0x1D (the "lifted" layer flag read by walker_draw 0x0044FEF0) on figures 1..N
for ticks T0..T1, so a run shows how city_draw 0x00458170 layers a lifted figure (docs/play/draw-order.md 3.7).

    python3 tools/oracle_poke_lifted.py T0 T1 [N=80] >> POKE.txt
Used by re/oracle/scenarios/gate-walk-lifted.txt."""
import sys

FIGURES = 0x00DBD788          # g_figures, 0x184 bytes each
t0, t1 = int(sys.argv[1]), int(sys.argv[2])
n = int(sys.argv[3]) if len(sys.argv) > 3 else 80
for t in range(t0, t1 + 1):
    for k in range(1, n):
        print(t, f"{FIGURES + k * 0x184 + 0x1D:x}", 1, 1)
