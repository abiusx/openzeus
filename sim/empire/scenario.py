"""The one loader: a scenario's empire (data/empire/<map>.json, built by tools/build_empire.py from the
Zeus map) -> model.Empire. Applies the exe's map-start setup (city_init_from_map 0x00511E30 ->
city_reset_on_map_start 0x0042E130): armies to their target (0 at the start), timers and fatigues 0,
distant cities become allies, colonies with relationship 3 pay tribute, trade open with everyone."""
import json
import os

from .model import City, Empire

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def available(map_name):
    return os.path.exists(os.path.join(ROOT, "data", "empire", f"{map_name}.json"))


def picture(map_name):
    """The scenario's map picture number (Zeus_MapOfGreece<NN>), 1 when the map has no empire data."""
    if not available(map_name):
        return 1
    return json.load(open(os.path.join(ROOT, "data", "empire", f"{map_name}.json")))["map_picture"]


def map_months(map_name):
    """The map's months count g_months_elapsed 0x00903114 (scenario block +0x7EC, read with the map: the colony start
    keeps it, FUN_005B0990; 0 in every Zeus adventure map, 35 / 421 in some Poseidon ones)."""
    import struct
    from ..world import read_map
    hdr, blocks = read_map(map_name)
    d = next(b for b in blocks if b["rank"] == 14)["data"]
    return struct.unpack_from("<i", d, 0x7EC)[0]


def load_scenario(map_name):
    return from_data(json.load(open(os.path.join(ROOT, "data", "empire", f"{map_name}.json"))))


def map_data(map_name):
    """The empire of any map name (sim/world.py map_path, e.g. `ADVENTURE.pak#N`) in data/empire format: the json when
    there is one, else tools/build_empire.py's build of that map container at run time (same converter)."""
    if available(map_name):
        return json.load(open(os.path.join(ROOT, "data", "empire", f"{map_name}.json")))
    import build_empire                              # tools/ (on sys.path via sim/world.py)
    from ..world import map_path, read_map
    return build_empire.build(map_path(map_name)[0], read_map(map_name))


def from_data(d):
    cities = []
    for r in d["cities"]:
        c = City(id=r["id"], name=r["name"], short=r["short"], leader=r["leader"], kind=r["kind"],
                 relation=r["relation"], route=r["route"], nation=r["nation"], buys=dict(r["buys"]),
                 sells=dict(r["sells"]), resources=list(r["resources"]), attitude=r["attitude"],
                 pleased=r["pleased"], displeased=r["displeased"], wealth=r["wealth"], strength=r["strength"],
                 tribute=dict(r["tribute"]), active=r["active"], visible=r["visible"], rebellion=r["rebellion"],
                 map=r["map"])
        if c.kind == "distant":
            c.relation = "ally"
        if c.kind == "colony" and c.relation == "colony" and c.tribute["mode"] != 1:
            c.tribute["mode"] = 1
        cities.append(c)
    return Empire(cities, d["routes"], d["map_picture"], d["source"])
