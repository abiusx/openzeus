"""World map side panel: ours (tools/world_panel_shots.mjs) vs the exe's shots re/oracle/runs/worldmap/wm_*.bmp.
Usage: python3 tools/world_panel_compare.py OURS_DIR [--out SIDE_BY_SIDE.png]
Per shot: % of the 186 x 600 panel pixels within 8 per channel, overall and per region (title box, attitude,
goods frame, tribute box, buttons). Needs Pillow."""
import sys, os
from PIL import Image
import oracle  # noqa: E402  (shot paths: .bmp -> .png, tools/oracle.py)

ORACLE = os.path.join(os.path.dirname(__file__), "..", "re", "oracle", "runs", "worldmap")
SHOTS = ["wm_player", "wm_ally2", "wm_ally4", "wm_rival3", "wm_rival5", "wm_vassal6", "wm_colony", "wm_distant7"]
REGIONS = {"title": (0, 0, 186, 88), "attitude": (0, 128, 186, 164), "goods": (0, 168, 186, 400),
           "tribute": (0, 404, 186, 456), "buttons": (0, 456, 186, 600), "all": (0, 0, 186, 600)}


def main(argv):
    ours = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    pairs = []
    for s in SHOTS:
        p = os.path.join(ours, s + ".png")
        if not os.path.exists(p):
            print(f"{s}: no capture"); continue
        a = Image.open(p).convert("RGB")
        px = 60 * ((a.width - 184) // 60) - 2                # the panel at uiPanelX (ui.js; one device px per UI px)
        a = a.crop((px, 0, px + 186, 600))
        e = Image.open(oracle.shot(os.path.join(ORACLE, s + ".bmp"))).convert("RGB").crop((838, 0, 1024, 600))
        pa, pe = a.load(), e.load()
        res = []
        for name, (x0, y0, x1, y1) in REGIONS.items():
            n = ok = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    n += 1
                    ok += all(abs(u - v) <= 8 for u, v in zip(pa[x, y], pe[x, y]))
            res.append(f"{name} {100 * ok / n:.1f}%")
        print(f"{s}: " + ", ".join(res))
        pairs.append((e, a))
    if out and pairs:
        im = Image.new("RGB", (len(pairs) * 384, 600), (0, 0, 0))
        for i, (e, a) in enumerate(pairs):
            im.paste(e, (i * 384, 0)); im.paste(a, (i * 384 + 190, 0))
        im.save(out)


if __name__ == "__main__":
    main(sys.argv[1:])
