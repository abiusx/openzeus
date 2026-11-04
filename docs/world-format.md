# World files: custom worlds as data

A world file defines the cities of the world map (the empire): their kind and relation to the player, goods
and yearly quotas, place on the map picture, and trade routes. The loader is `sim/empire/world.py`
`load_world(name)`. It fills the same `City` / `Empire` records (`sim/empire/model.py`) that the faithful
Zeus scenarios get from `data/empire/<map>.json` (`scenario.py`), so the diplomacy, trade and war rules
(docs/logic/world-map.md) apply unchanged.

- Files live in `data/world/<name>.json`; a path to any `.json` file also works.
- New games keep the map's own Zeus scenario world. A game picks a world file with `empire on NAME`.
- `empire worlds` lists the world files.
- The world is saved inside the save file (`g.empire`), so later edits to the JSON don't change running games.
  Run `empire on NAME` again before any trading post exists, or use `--migrate` when one does.

## Format (version 1)
Top level:

| field | required | meaning |
|---|---|---|
| `format` | yes | `"world"` |
| `version` | yes | `1` |
| `name`, `note` | no | free text (say what is invented) |
| `picture` | no (1) | map picture 1..10 = `Zeus_MapOfGreece01..10` (838 × 738 px; 8–10 have no portrait corner) |
| `cities` | yes | list of cities; exactly one has `"kind": "player"`. A city's id is its position in this list |
| `routes` | no | extra routes between two non-player cities: `{from, to, kind, points}` (names, `land`/`sea`, control points between the two cities) |

City fields (only `name`, `map` and, for the player, `kind` are required):

| field | default | meaning |
|---|---|---|
| `name` | required | unique (case-insensitive); trading posts are bound to it on migration |
| `short` | name | short name |
| `leader` | `""` | shown as "Leader: …" |
| `kind` | `foreign` | `player`, `colony`, `foreign`, `parent`, `distant` (trades, no diplomacy), `enchanted`, `destroyed` |
| `relation` | `ally` (`colony` for a colony) | `ally`, `rival` (no trade, can be raided/conquered), `vassal`, `colony` |
| `route` | `land` | `land` (caravans from the map entry) or `sea` (ships; the city map needs a sea entry) |
| `nation` | 0 | marker and army icons: 0 Greek, 1 Trojan, 2 Persian, 3 Centaur, 4 Amazon |
| `buys` | `{}` | `{good: yearly loads}`: what the player can export to it |
| `sells` | `{}` | `{good: yearly loads}`: what the player can import from it. Buys + sells: at most 10 goods (the side panel) |
| `attitude` | 50 | 0..100 |
| `wealth`, `strength` | 3, 3 | 1..5 and 1..6 (6 = invincible); raids, gifts, battles |
| `tribute` | none | `{mode: none\|pays\|receives, amount, good, claim}`. `pays`: it pays you yearly; `receives`: you pay it. A colony with relation `colony` always pays |
| `active`, `visible` | true | an inactive city is drawn greyed and does not trade; an invisible one is not drawn |
| `resources` | `[]` | player only: goods the player city may produce |
| `map` | required | `{x, y, label}`: the marker's centre on the picture; `label` is `left`, `right`, `top` or `bottom`. Optional `w`, `h`, `icon` (by kind otherwise) |
| `path` | `[]` | not for the player: control points `[[x, y], ...]` from the city towards the player. The loader adds the city's and the player's positions at the ends. Dots are drawn every 5 px along it, and travel time = max(2, dots × 5 / 200) months (exe `0x004625A0`) |
| `note` | | free text |

Goods: `urchin fish meat cheese carrots onions wheat oranges wood bronze marble grapes olives fleece horses
black_marble orichalc armor sculpture olive_oil wine chariot` (plus `drachmas` for tribute). One load is
100 units (a sculpture is 400).
`oranges` (a Poseidon good, data/resources.json `"poseidon"`) are listed but never traded while Poseidon is off
(`poseidon on` allows them; the decision log 2026-10-30); our Zeus worlds (partners, wartest) don't list them.
`horses` and `chariot` in `buys`/`sells` are shown on the world map but never traded: a trading post or dock
can't import or export them (exe `storage_goods_list` 0x005B12C0; docs/logic/trade.md "Goods a post never
trades"). data/world/partners.json still lists chariots for Susa (buys), Ecbatana (sells) and Memphis (buys);
those entries do nothing.

Errors: `load_world` lists every problem with its field, for example
`cities[1] (A).kind: 'foe' not one of player, colony, ...`, and refuses the file until all are fixed.

## Example
```json
{"format": "world", "version": 1, "name": "two cities", "picture": 8,
 "cities": [
  {"name": "Ephesus", "kind": "player", "map": {"x": 680, "y": 420, "label": "right"}},
  {"name": "Sardis", "relation": "ally", "route": "land", "nation": 2,
   "buys": {"wine": 12}, "sells": {"bronze": 12, "wood": 24},
   "map": {"x": 730, "y": 300, "label": "right"}, "path": [[705, 360]]}
 ]}
```

## Adding a city
1. Add an object to `cities`, after the existing ones. Don't reorder the list in a world that saves already use;
   migration binds posts by name, so a reorder works only through `--migrate`.
2. Pick a free spot on the picture: open `zeus-original/app/DATA/Zeus_MapOfGreece0N.JPG` (838 × 738) and read
   the pixel position.
3. Give it a `path` that follows the sea for `sea` routes and the land for `land` routes.
4. Load it with `python3 -m sim do SAVE "empire on NAME"` (or `--migrate`); the error list names any bad field.
5. Check it in play mode's world map (control panel, world map button).

## The `partners` world
`data/world/partners.json` holds the 8 partners of `data/trade.json` (Sardis, Babylon, Susa, Ecbatana, Tyre,
Miletus, Memphis, Corinth). Their goods, quotas and land/sea routes are unchanged; all are allies (attitude
60) so trade goes on as before. The player city is "Ephesus", on picture 8.
**Positions, paths, nations and the player's name are invented** (`tools/make_world_partners.py`, first write;
the file is data after that; the script would overwrite hand edits).

## Migration (saves from before the world module)
`empire on WORLD --migrate` (or `empire on --migrate` for the map's scenario) on a save that has trading posts
or docks (sim/empire/world.py `migrate`):
- Each post or dock is re-bound to the world city with the same name as its old partner. The command refuses,
  naming the post, when that city is missing, trades by the other route kind, or is not a trading partner
  (rival, inactive).
- Caravans and ships under way keep their post; their partner id is renumbered.
- This year's used quotas, trade countdowns and trader lists move with the partner.
- A caravan of a partner the world lacks (only possible without a post) is removed with its donkeys.
- Without `--migrate`, `empire on` is refused while posts exist; `empire off` is refused while they exist.

Checked on a copy of `saves/live-full.pkl`: 4 posts (Susa, Sardis, Babylon, Ecbatana) re-bound; with import
orders on every good, 120 days imported exactly the same goods with and without migration.

Apply to a save:
```
cp saves/X.pkl saves/X.backup.pkl
python3 -m sim do saves/X.pkl "empire on partners --migrate"
```
A running `python3 -m sim live` server keeps its own copy in memory: stop it first, or send the command
through its /cmd endpoint.
