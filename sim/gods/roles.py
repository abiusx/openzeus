"""The scenario's god roles (scenario_gods_apply 0x00586F70) and the god records' start values (god_reset 0x004F1A30).

The god block comes from the scenario module (sim/scenario, track 1G: `scenario.gods(g)`, the episode's block) when
the game has one, else from data/gods/<map>.json (tools/build_gods.py, the same block read from the map's adventure).
A map with neither has no god roles: every sanctuary may be built, nobody gets jealous (ours: "free").
"""
import json
import os

from . import ROOT, GODS

LISTED = set(range(0, 4)) | set(range(12, 18))           # scenario_slot_listed 0x00587080


def block(g):
    try:
        from .. import scenario
        if getattr(g, "scenario", None) is not None:
            b = scenario.gods(g)
            if b:
                return b
    except ImportError:
        pass
    p = os.path.join(ROOT, "data", "gods", f"{g.map_name}.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def init(g, st):
    b = block(g)
    st.setdefault("on", True)
    st["free"] = b is None
    st["max_sanct"] = b["max_sanctuaries"] if b else 4
    st["monster"] = b.get("independent_monster", -1) if b else -1
    st["rec"] = []
    for i in range(14):
        st["rec"].append(dict(unfriendly=2, listed=2, jealous=0, slot=-1,
                              mood=50, prayer=0, oracle=0, figure=0, pending=0, pending_months=0,
                              attack_slot=-1))
    if b:
        for s, gid in enumerate(b["slots"]):
            if 0 <= gid < 14:
                r = st["rec"][gid]
                r["slot"] = s
                r["listed"] = 1 if s in LISTED else 0
                r["unfriendly"] = 1 if s < 12 else 0
                r["jealous"] = 1 if b["jealous"][s] else 0
    for b in getattr(g, "buildings", {}).values():     # saves from before the gods module: no priests ran, so a
        if b.key.startswith("sanctuary_") and b.misc.get("complete") and not b.misc.get("activity"):
            b.misc["activity"] = 22         # complete sanctuary restarts as at its completion (cycle_buildings_pass_32)
    st["jealousy"] = 99                     # city 0x00FE6A58+1 (oracle: 99 at the start)
    st["help_cand"] = -1                    # g_god_help_candidate 0x0063A888
    st["curse"] = {}                        # g_type_curse 0x00EF60B0: zeus type -> month_advance calls left
    st["stop"] = 0                          # g_production_stop 0x00EF6163
    st["trade_block"] = [0, 0]              # 0x00FEAED8 / 0x00FEAEDA
    st["log"] = []                          # (tick, text): attacks, visits, help (ours, for tests and the CLI)


def friendly(g):
    st = g.gods
    return [i for i in range(14) if st["rec"][i]["unfriendly"] == 0]


def unfriendly(g):
    st = g.gods
    return [i for i in range(14) if st["rec"][i]["unfriendly"] == 1]


def names(ids):
    return [GODS[i] for i in ids]


def apply(g, st):
    """A later episode's god block on a running city (episode_start_load kind 2): scenario_gods_apply 0x00586F70
    (every god listed = 2, then each slotted god's listed / unfriendly / may-be-jealous from its slot; the rest of
    a god record, mood and the like, kept), max sanctuaries (+0xDC) and the independent monster (+0x60)."""
    b = block(g)
    if b is None:
        return
    st["free"] = False
    st["max_sanct"] = b["max_sanctuaries"]
    st["monster"] = b.get("independent_monster", -1)
    for r in st["rec"]:
        r["listed"] = 2
    for s, gid in enumerate(b["slots"]):
        if 0 <= gid < 14:
            r = st["rec"][gid]
            r["slot"] = s
            r["listed"] = 1 if s in LISTED else 0
            r["unfriendly"] = 1 if s < 12 else 0
            r["jealous"] = 1 if b["jealous"][s] else 0
