"""Write data/world/wartest.json: the military test world (docs/play/military.md "Test scenario"): the 8 allies of
data/world/partners.json (so scripts/full.txt's trading posts and docks migrate by name) plus two rivals to fight:
Sparta by land (Greek army) and Troy by sea (Trojan army, its invasions come by ship).

    python3 tools/make_world_wartest.py

Rival positions, paths, strengths and goods are INVENTED for testing (not from any Zeus map).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "world", "partners.json")
OUT = os.path.join(ROOT, "data", "world", "wartest.json")

RIVALS = [
    dict(name="Sparta", kind="foreign", relation="rival", route="land", nation=0, strength=4, wealth=3,
         attitude=20, buys={"wine": 12}, sells={"armor": 12},
         tribute=dict(mode="none", amount=0, good="drachmas", claim=50),
         map=dict(x=250, y=520, label="right"), path=[[300, 430], [420, 420], [560, 440]],
         note="invented: a land rival with a Greek army"),
    dict(name="Troy", kind="foreign", relation="rival", route="sea", nation=1, strength=3, wealth=4,
         attitude=20, buys={"olive_oil": 12}, sells={"bronze": 12},
         tribute=dict(mode="none", amount=0, good="drachmas", claim=50),
         map=dict(x=600, y=150, label="right"), path=[[610, 250], [630, 350]],
         note="invented: a sea rival with a Trojan army"),
]


def main():
    d = json.load(open(SRC))
    d["name"] = "wartest"
    d["note"] = ("Military test world (tools/make_world_wartest.py): partners' 8 allies + the invented rivals Sparta "
                 "(land) and Troy (sea). For scripts/military.txt (`empire on wartest --migrate`).")
    d["cities"] = d["cities"] + RIVALS
    with open(OUT, "w") as f:
        json.dump(d, f, indent=1)
    print(f"{len(d['cities'])} cities -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
