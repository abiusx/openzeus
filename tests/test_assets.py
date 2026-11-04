"""The asset split (tools/assets.py, docs/assets.md): the tracked templates and the runtime JSON agree."""
import os
import sys

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import assets  # noqa: E402


def test_assets_templates_match_runtime():
    """every assets/templates/ file merges to its runtime file, and splitting that file gives the template back
    (a builder rewrote data/... without `tools/assets.py split`, or a template was edited without `merge`).
    Needs the game's text files (zeus-original/app); an asset-pack install has none: nothing to check."""
    if not os.path.exists(os.path.join(assets.GAME, "Zeus_Text.eng")):
        return
    pool = assets.text_pool()
    index = assets.pool_index(pool)
    bad = []
    for f in assets.templates():
        t = open(os.path.join(assets.TEMPLATES, f), encoding="utf-8").read()
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            bad.append(f"{f}: missing (tools/assets.py merge)")
            continue
        r = open(p, encoding="utf-8").read()
        if assets.merge_text(t, pool) != r:
            bad.append(f"{f}: differs from its template (tools/assets.py split {f}, or merge)")
        elif assets.split_text(r, index)[0] != t:
            bad.append(f"{f}: template not up to date (tools/assets.py split {f})")
    assert not bad, "\n".join(bad)


if __name__ == "__main__":
    from test_sim import main
    main([__file__])
