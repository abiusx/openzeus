"""Write data/world/partners.json: a world file (docs/world-format.md) with the 8 trade partners of
data/trade.json (Sardis, Babylon, Susa, Ecbatana, Tyre, Miletus, Memphis, Corinth), all allies, with their
buys/sells and land/sea routes, on Zeus_MapOfGreece08 (the Aegean, no portrait).

    python3 tools/make_world_partners.py

Map positions, route paths, nations and the player city's name are INVENTED here (the partners never had a place
on a map): the player sits on the Ionian coast, the inland cities at the picture's east edge in their
real compass direction, Tyre and Memphis south-east / south over the sea, Corinth on the Isthmus. After this
first write the file is data: edit it by hand (this script would overwrite it).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "world", "partners.json")

# name: (x, y, label, nation, path from the city towards the player (the player's spot is added by the loader))
PLACES = {
    "Sardis":   (730, 300, "right", 2, [[705, 360]]),
    "Babylon":  (810, 380, "left", 2, [[750, 400]]),
    "Susa":     (810, 470, "left", 2, [[755, 455]]),
    "Ecbatana": (800, 200, "left", 2, [[760, 280], [715, 355]]),
    "Tyre":     (795, 655, "left", 2, [[720, 610], [640, 545], [612, 470]]),
    "Miletus":  (640, 482, "left", 0, [[652, 452]]),
    "Memphis":  (520, 705, "right", 2, [[590, 655], [610, 560], [598, 470]]),
    "Corinth":  (298, 368, "top", 0, [[335, 385], [420, 420], [520, 440], [610, 432]]),
}
PLAYER = dict(name="Ephesus", kind="player", map=dict(x=680, y=420, label="right"))


def main():
    partners = json.load(open(os.path.join(ROOT, "data", "trade.json")))["partners"]
    cities = [PLAYER]
    for p in partners:
        x, y, label, nation, path = PLACES[p["name"]]
        cities.append(dict(name=p["name"], kind="foreign", relation="ally", route=p["route"], nation=nation,
                           buys=p["buys"], sells=p["sells"], attitude=60,
                           map=dict(x=x, y=y, label=label), path=path))
    d = dict(format="world", version=1, name="partners",
             note="The 8 partners of data/trade.json as allies, for saves from before the world module "
                  "(`empire on partners --migrate`). Positions, paths, nations and the player's name are invented "
                  "(tools/make_world_partners.py); goods and routes are data/trade.json's.",
             picture=8, cities=cities)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(d, f, indent=1)
    print(f"{len(cities)} cities -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
