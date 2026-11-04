"""Cliff / elevation ground pictures of Zeus: Master of Olympus for all 4 view orientations, ported from Zeus.exe
(GOG 2.1).  Companion of tools/terrain_images.py, which ports everything else of map_tiles_update_images.

    cliffs(flags, elev, rand, view, orig_ids=None, draw=None, piece=None, desirability=None)
        -> (ids, draw, flags_out)
    project(elev, flags, view) -> projected-altitude grid (map_elevation_project 0x0045ED20)

Self-check: python3 tools/terrain_cliffs.py  (view 0 against the sandbox map's own rank-4 / rank-5 grids; per-view
counts for views 2/4/6).

Conventions (same as terrain_images.py)
  * grids are [y][x], 228 x 228, flat index t = y*228 + x (the exe's own index; DAT_00da2f80 = 0).
  * image id = collection*0x4000 + n, collection 5 (Zeus_Terrain), n 0-based (atlas.json index = n + 201).
  * The exe names pictures by a packed code (collection << 9 | group), e.g. 0xa6b = Zeus_Terrain group 0x6b = 107
    SPR_E1_N.  Image = 5*0x4000 + first n of that group (FIRST_N below, = atlas.json groups[].first - 201).
    The bank lookup is sprite table 0x012AFBEC[coll*0x3311] (8-byte group entries, +4 = first image) and
    0x012BC820[coll*0x3311] (last valid group index); collection 5's entries are 0x012EF940 / 0x012FC574.
  * draw byte (rank 5 / g_grid_draw 0x00D404B8): r*8 + c inside a multi-tile piece, | 0x40 on the tile that draws.
  * view = 0, 2, 4, 6 (exe 0x00DA2F88).

How the exe recomputes cliffs on a turn: FUN_004A1B70 -> FUN_0051D760 -> FUN_00521520(3) (whole map; same body as
map_tiles_update_images 0x0051F450 without the rect):
 0. mode bit 1: map_elevation_project 0x0045ED20 (projected altitude 0x008ECD0A, see project()); it also cleans
    flags: tiles without 0x200 lose 0x400 and 0x800000; tiles with 0x200 lose 0x800, 0x80, 0x1.
 1. Pass 1, every tile with flags & 0x8C008 == 0 in row-major order: image = 0 unless the tile has 0x200; then
    FUN_0051FEC0 (cliff piece):
      flags &= 0xDFBFFDFF (clear 0x200, 0x400000, 0x20000000); per-tile code/dir/flags arrays (0x008AD5B4,
      0x0087A974, 0x00847D34) = 0;
      skip if FUN_00546380 (flag 0x10000000 special tiles);
      matcher FUN_0045E110(table 0x005F8F28, count FUN_0045E070() = 152, tile): d[i] = elev[nb_i] - elev[t] for
      the 8 neighbours (offsets 0x005D91A8 = N NE E SE S SW W NW = -228 -227 +1 +229 +228 +227 -1 -229).  No
      neighbour higher -> no match.  Records (16 int32 = 64 bytes):
        [0..7] pattern per neighbour: 3 = any, 4 = |d| <= 1, other = d must equal it (-1, 0, 1, 2)
        [8..11] picture code for view 0, 2, 4, 6 (column view/2): the only view-dependent part of the match
        [12] terrain flags OR-ed into the tile (0x400000, 0x20400000, 0x200)
        [13] direction 0/2/4/6 (-1 none): the 2x2 placement corner and the ramp partner neighbour
        [14] flag mask, [15] = 1: record only for ramp tiles (0x400), and only if (flags & [14]) == 0x400
      First matching record wins.  Code 1 / 2 = "fill the pit": FUN_0045FA20 raises the tile by 1 / 2 (no picture).
      Tiles with 0x800000 (ramp) remap the code (0xa6a.. -> 0xa8a.., 0xa76..0xa79 -> 0xa9e..0xaa1, 0xa6b/d/f/71 ->
      0xa9a.. / 0xaaa.. / 0xac4.. by FUN_0045E080: 0x800000 on the two side neighbours 0x005FB52C/0x005FB530).
      Ramp tiles with road 0x40: code + 8 if FUN_004A0480 (not beach and desirability > 4) or DAT_00B1E8C0, else +4.
      FUN_0045DE10: random variant (rand % FUN_0045DD40(code), 2 or 4 alternatives: 0xa59 -> 0xa2d/e/f etc.).
      FUN_0045FA20 then clamps the tile's elevation to [max(nb) - 2, min(nb) + 2] (editor tools 0xB1/0xB2 aside).
      Result by code: 0 -> if some neighbour is higher: SPR_SPACE (id 0x14000, hidden tile), flag 0x200, queued
      (editor lowers these); 1 / 2 -> nothing; 0xa92..0xa95 and 0xa53..0xa56, 0xa8a/c/e, 0xa90 -> deferred to
      pass 2 (2x2 pieces); else FUN_0045E700: piece &= 0xF0, draw 0x40, image = first(code); if dir >= 0 and the
      tile has 0x800000 the neighbour in direction dir gets image + 1, draw 0x41, flag 0x200; then flags |= rec[12]
      | 0x200.
 2. Pass 2, row-major, FUN_005200B0(flags, t, x, y) with the stored code/dir/flags (returns "handled" for any
    code != 0, so no other painter touches those tiles):
      0xa92..0xa95: FUN_0045E5A0(t, a, b) with (a, b) = 0x005FB63C[dir/2] = (4,2) (6,4) (0,6) (2,0): both
        neighbours t+nb[a], t+nb[b] must already show a picture of list 0x005FB558 (56 codes, count 0x005FB638);
        origin x,y -= dir2 (1,0) dir4 (1,1) dir6 (0,1).
      0xa53..0xa56, 0xa8a/c/e, 0xa90: same with (a, b) = 0x005FB65C[dir/2] = (0,6) (2,0) (4,2) (6,4).
      0xaaa..0xab1: FUN_0045E840: record of table 0x005FB69C (8 x {key, picA, picB, result}, filled once at run
        time) whose key = code; image[t] must be picA and image[t + 0x005FB52C[dir/2]] picB -> result code;
        origin -= dir0 (1,1) dir2 (0,1) dir6 (1,0).
      0xa9a..0xa9d: FUN_0045EB00: table 0x005FB71C (4 x {key, result}); image[t] and image[t + 0x005FB52C[dir/2]]
        both = first(code); result 0xa8b/d/f/91 with variants by rand & 3 (0xad2..0xadd); origin as 0xaaa.
      On success: draw[t] = 0x40, building_footprint_place 0x004A04B0(0, x, y, 2, 2, image, 0x200): the 4 tiles get
      flags & 0x93872F90 | 0x200, building 0, piece (piece & 0xE0) | 1, the image, draw r*8+c, and 0x40 on the
      view's anchor (r, c) = (1, 0) v0, (0, 0) v2, (0, 1) v4, (1, 1) v6 (0x00FA05E8 = view during the turn);
      then flags[t] |= rec[12] | 0x200.
      Tiles with 0x800000: by code, the ramp partner t + 0x005D9558[dir] gets 0x40 (0xaa2..0xaa9), 0x800400
      (0xa9e..0xaa9) and always loses 0x80 / gains 0x200.
 Offsets 0x005FB528 (3 int32 per dir/2): (0,-1,+1) (0,-228,+228) (0,+1,-1) (0,+228,-228).

What is ported: everything above (map_elevation_project, FUN_0051FEC0 + matcher + FUN_0045FA20 + FUN_0045E700,
FUN_005200B0 + FUN_0045E5A0 / FUN_0045E840 / FUN_0045EB00 + the footprint anchor).  Not ported: 0x10000000 special
tiles (FUN_00545940; treated as "special, skip"), the editor's lowering of hidden tiles, editor tools 0xB1/0xB2 in
FUN_0045FA20, and DAT_00B1E8C0 (unknown global, parameter `alt_road`, default 0).

Checks (2026-10-28): sandbox (426 cliff tiles, no 2x2 pieces) 100 % ids and draw bytes in view 0.  All maps of all
v247 .pak files under Adventures/ (64,593 cliff tiles, with 2x2 pieces and ramp partners), each at the view it
was saved in: 99.87 %; three maps were saved in view 4 / 6 and match 100 % there and 0 % in view 0, which checks
the per-view picture column and the 2x2 anchor (draw 0x48 v0, 0x49 v6).  View 2 has no saved map to check
against (same code path).  Residue (83 tiles): editor history (cliff tiles later painted with water / rock / tree
images, unfilled pits that the code would raise (codes 1/2), hidden tiles), not differences in the rules.
"""
import numpy as np

N = 228
NN = N * N
COL = 5 * 0x4000
CLIFF, RAMP, RAMP2, ROAD, BEACH, OFFMAP, SPECIAL = 0x200, 0x400, 0x800000, 0x40, 0x10000, 0x80000, 0x10000000
SKIP_TILE = 0x8C008
NB = (-228, -227, 1, 229, 228, 227, -1, -229)          # 0x005D91A8 (= 0x005D9558[0..7]); N NE E SE S SW W NW
SIDE = ((0, -1, 1), (0, -228, 228), (0, 1, -1), (0, 228, -228))   # 0x005FB528, row dir/2

# first n (0-based image index of Zeus_Terrain) of groups 1..221; from extracted/sprites/Zeus_Terrain/atlas.json
# (groups[].first - 201).  Group g of the exe's packed code (5 << 9 | g) = atlas group id g.
FIRST_N = (
    0, 1281, 1280, 978, 163, 243, 275, 333, 1142, 105, 361, 1074, 430, 1082, 49, 37,
    422, 650, 1134, 560, 414, 376, 404, 394, 1090, 771, 763, 1150, 1042, 1010, 1158, 362,
    696, 542, 462, 1, 1098, 61, 714, 347, 390, 900, 851, 1282, 1294, 1295, 1296, 1297,
    1298, 1299, 1328, 1329, 1300, 1301, 1302, 1303, 1304, 1305, 1306, 1307, 1308, 1309, 1310, 1311,
    1312, 1313, 1314, 1315, 1316, 1317, 1318, 1319, 1320, 1321, 1322, 1323, 1273, 1271, 1269, 1267,
    1265, 1263, 1324, 1325, 1326, 1327, 1159, 1160, 1161, 1162, 1163, 1164, 1165, 1166, 1167, 1168,
    1169, 1170, 1171, 1172, 1173, 1174, 1175, 1176, 1177, 1178, 1179, 1180, 1181, 1182, 1183, 1184,
    1185, 1186, 1187, 1188, 1189, 1190, 1191, 1192, 1193, 1194, 1195, 1196, 1197, 1198, 1199, 1200,
    1201, 1202, 1204, 1206, 1208, 1203, 1205, 1207, 1209, 1210, 1211, 1212, 1213, 1214, 1215, 1216,
    1217, 1218, 1219, 1220, 1221, 1222, 1223, 1224, 1225, 1226, 1228, 1230, 1232, 1234, 1236, 1238,
    1240, 1242, 1244, 1246, 1248, 1250, 1252, 1254, 1256, 1258, 1260, 1262, 1264, 1266, 1268, 1270,
    1272, 1229, 1227, 1231, 1233, 1235, 1237, 1239, 1241, 1243, 1245, 1247, 1249, 1251, 1253, 1255,
    1257, 1259, 1261, 1278, 1279, 1277, 1276, 1275, 1274, 456, 1424, 1364, 1330, 448, 438, 446,
    436, 1484, 1488, 1492, 1485, 1489, 1493, 1486, 1490, 1494, 1487, 1491, 1495,
)


def image_of(code):
    """Packed picture code (collection << 9 | group) -> image id (the exe's 0x012AFBEC lookup)."""
    coll, g = code >> 9, code & 0x1FF
    if g == 0:
        return 0
    assert coll == 5, hex(code)
    if g - 1 >= len(FIRST_N):          # beyond the bank's last group: the exe takes group 1
        g = 1
    return COL + FIRST_N[g - 1]


def grp(g):
    """Image id of group g's first picture (font_group_entry(g - 1) + 4 on collection 5)."""
    return COL + FIRST_N[g - 1]


# 0x005F8F28: 152 records (pattern[8], pictures per view[4], flags, dir, mask, ramp_only)
CLIFF_TABLE = (
    ((1, 1, 1, 1, 2, 2, 2, 2), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 1, 2, 2, 2, 2, 1, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 2, 2, 2, 1, 1, 1, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 2, 1, 1, 1, 1, 2, 2), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 1, 1, 0, 0, 2, 2, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 0, 0, 2, 2, 1, 1, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((0, 2, 2, 1, 1, 1, 1, 0), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 1, 1, 1, 1, 0, 0, 2), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 2, 2, 0, 0, 1, 1, 2), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 0, 0, 1, 1, 2, 2, 2), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((0, 1, 1, 2, 2, 2, 2, 0), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 2, 2, 2, 2, 0, 0, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((0, 0, 0, 2, 1, 3, 0, 0), (0xa62, 0xa68, 0xa66, 0xa64), 0x400000, -1, 0x0, 0),
    ((0, 0, 0, 3, 1, 2, 0, 0), (0xa63, 0xa69, 0xa67, 0xa65), 0x400000, -1, 0x0, 0),
    ((0, 0, 0, 0, 0, 2, 1, 3), (0xa64, 0xa62, 0xa68, 0xa66), 0x400000, -1, 0x0, 0),
    ((0, 0, 0, 0, 0, 3, 1, 2), (0xa65, 0xa63, 0xa69, 0xa67), 0x400000, -1, 0x0, 0),
    ((1, 3, 0, 0, 0, 0, 0, 2), (0xa66, 0xa64, 0xa62, 0xa68), 0x400000, -1, 0x0, 0),
    ((1, 2, 0, 0, 0, 0, 0, 3), (0xa67, 0xa65, 0xa63, 0xa69), 0x400000, -1, 0x0, 0),
    ((0, 2, 1, 3, 0, 0, 0, 0), (0xa68, 0xa66, 0xa64, 0xa62), 0x400000, -1, 0x0, 0),
    ((0, 3, 1, 2, 0, 0, 0, 0), (0xa69, 0xa67, 0xa65, 0xa63), 0x400000, -1, 0x0, 0),
    ((2, 2, 2, 2, 2, 2, 2, 2), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((2, 3, 2, 3, 2, 3, 2, 3), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((3, 2, 3, 2, 3, 2, 3, 2), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((2, 2, 2, 3, 3, 2, 3, 3), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((3, 3, 2, 2, 2, 3, 3, 2), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((3, 2, 3, 3, 2, 2, 2, 3), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((2, 3, 3, 2, 3, 3, 2, 2), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((3, 3, 2, 3, 3, 3, 2, 3), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((3, 3, 3, 2, 3, 3, 3, 2), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((2, 3, 3, 3, 2, 3, 3, 3), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((3, 2, 3, 3, 3, 2, 3, 3), (0x2, 0x2, 0x2, 0x2), 0x0, -1, 0x0, 0),
    ((2, 3, 3, 3, 3, 3, 2, 2), (0xa5e, 0xa61, 0xa60, 0xa5f), 0x400000, 0, 0x0, 0),
    ((2, 2, 2, 3, 3, 3, 3, 3), (0xa5f, 0xa5e, 0xa61, 0xa60), 0x400000, 2, 0x0, 0),
    ((3, 3, 2, 2, 2, 3, 3, 3), (0xa60, 0xa5f, 0xa5e, 0xa61), 0x400000, 4, 0x0, 0),
    ((3, 3, 3, 3, 2, 2, 2, 3), (0xa61, 0xa60, 0xa5f, 0xa5e), 0x400000, 6, 0x0, 0),
    ((1, 1, 1, 1, 1, 1, 1, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 1, 3, 1, 3, 1, 3, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 3, 1, 3, 1, 3, 1, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 1, 1, 4, 4, 1, 4, 4), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((4, 4, 1, 1, 1, 4, 4, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((4, 1, 4, 4, 1, 1, 1, 4), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 4, 4, 1, 4, 4, 1, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((4, 4, 1, 4, 4, 4, 1, 4), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((4, 4, 4, 1, 4, 4, 4, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 4, 4, 4, 1, 4, 4, 4), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((4, 1, 4, 4, 4, 1, 4, 4), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 1, 3, 1, 3, 1, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 3, 1, 3, 1, 3, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 1, 3, 3, 3, 1, 3, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 1, 3, 1, 3, 3, 3, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 2, 1, 1, 1, 1, 0, 0), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((0, 0, 2, 2, 1, 1, 1, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 1, 0, 0, 2, 2, 1, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 1, 1, 1, 0, 0, 2, 2), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 3, 3, 3, 3, 3, 1, 1), (0xa72, 0xa75, 0xa74, 0xa73), 0x20400000, 0, 0x0, 0),
    ((1, 1, 1, 3, 3, 3, 3, 3), (0xa73, 0xa72, 0xa75, 0xa74), 0x20400000, 2, 0x0, 0),
    ((3, 3, 1, 1, 1, 3, 3, 3), (0xa74, 0xa73, 0xa72, 0xa75), 0x20400000, 4, 0x0, 0),
    ((3, 3, 3, 3, 1, 1, 1, 3), (0xa75, 0xa74, 0xa73, 0xa72), 0x20400000, 6, 0x0, 0),
    ((3, 3, 0, 2, 0, 3, 3, 3), (0xa1f, 0xa5c, 0xa5a, 0xa58), 0x400000, -1, 0x0, 0),
    ((3, 3, 3, 3, 0, 2, 0, 3), (0xa58, 0xa1f, 0xa5c, 0xa5a), 0x400000, -1, 0x0, 0),
    ((0, 3, 3, 3, 3, 3, 0, 2), (0xa5a, 0xa58, 0xa1f, 0xa5c), 0x400000, -1, 0x0, 0),
    ((0, 2, 0, 3, 3, 3, 3, 3), (0xa5c, 0xa5a, 0xa58, 0xa1f), 0x400000, -1, 0x0, 0),
    ((3, 3, 0, 1, 0, 3, 3, 3), (0xa6a, 0xa70, 0xa6e, 0xa6c), 0x20400000, 4, 0x0, 0),
    ((3, 3, 3, 3, 0, 1, 0, 3), (0xa6c, 0xa6a, 0xa70, 0xa6e), 0x20400000, 6, 0x0, 0),
    ((0, 3, 3, 3, 3, 3, 0, 1), (0xa6e, 0xa6c, 0xa6a, 0xa70), 0x20400000, 0, 0x0, 0),
    ((0, 1, 0, 3, 3, 3, 3, 3), (0xa70, 0xa6e, 0xa6c, 0xa6a), 0x20400000, 2, 0x0, 0),
    ((3, 3, 0, 3, 2, 3, 0, 3), (0xa57, 0xa5d, 0xa5b, 0xa59), 0x400000, -1, 0x0, 0),
    ((0, 3, 3, 3, 0, 3, 2, 3), (0xa59, 0xa57, 0xa5d, 0xa5b), 0x400000, -1, 0x0, 0),
    ((2, 3, 0, 3, 3, 3, 0, 3), (0xa5b, 0xa59, 0xa57, 0xa5d), 0x400000, -1, 0x0, 0),
    ((0, 3, 2, 3, 0, 3, 3, 3), (0xa5d, 0xa5b, 0xa59, 0xa57), 0x400000, -1, 0x0, 0),
    ((3, 3, 0, 4, 1, 4, 0, 3), (0xa76, 0xa79, 0xa78, 0xa77), 0x200, 0, 0x400, 1),
    ((0, 3, 3, 3, 0, 4, 1, 4), (0xa77, 0xa76, 0xa79, 0xa78), 0x200, 2, 0x400, 1),
    ((1, 4, 0, 3, 3, 3, 0, 4), (0xa78, 0xa77, 0xa76, 0xa79), 0x200, 4, 0x400, 1),
    ((0, 4, 1, 4, 0, 3, 3, 3), (0xa79, 0xa78, 0xa77, 0xa76), 0x200, 6, 0x400, 1),
    ((3, 3, 0, 4, 1, 4, 0, 3), (0xa6b, 0xa71, 0xa6f, 0xa6d), 0x200, 0, 0x0, 0),
    ((0, 3, 3, 3, 0, 4, 1, 4), (0xa6d, 0xa6b, 0xa71, 0xa6f), 0x200, 2, 0x0, 0),
    ((1, 4, 0, 3, 3, 3, 0, 4), (0xa6f, 0xa6d, 0xa6b, 0xa71), 0x200, 4, 0x0, 0),
    ((0, 4, 1, 4, 0, 3, 3, 3), (0xa71, 0xa6f, 0xa6d, 0xa6b), 0x200, 6, 0x0, 0),
    ((3, 3, 1, 2, 1, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 2, 1, 3, 3, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 3, 3, 3, 3, 3, 1, 2), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 3, 3, 1, 2, 1, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 1, 2, 2, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 2, 2, 3, 3, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 3, 3, 3, 3, 3, 1, 2), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 3, 3, 1, 2, 2, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 2, 2, 1, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 2, 1, 3, 3, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 3, 3, 3, 3, 3, 2, 2), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 3, 3, 2, 2, 1, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 2, 1, 1, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 1, 1, 3, 3, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 3, 3, 3, 3, 3, 2, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 3, 3, 2, 1, 1, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 1, 1, 2, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 1, 2, 3, 3, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 3, 3, 3, 3, 3, 1, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 3, 3, 1, 1, 2, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 2, 1, 2, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 1, 2, 3, 3, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((2, 3, 3, 3, 3, 3, 2, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 3, 3, 2, 1, 2, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 0, 1, 1, 3, 3, 3), (0xa6b, 0xa71, 0xa6f, 0xa6d), 0x200, 0, 0x0, 0),
    ((3, 3, 3, 3, 0, 1, 1, 3), (0xa6d, 0xa6b, 0xa71, 0xa6f), 0x200, 2, 0x0, 0),
    ((1, 3, 3, 3, 3, 3, 0, 1), (0xa6f, 0xa6d, 0xa6b, 0xa71), 0x200, 4, 0x0, 0),
    ((0, 1, 1, 3, 3, 3, 3, 3), (0xa71, 0xa6f, 0xa6d, 0xa6b), 0x200, 6, 0x0, 0),
    ((0, 3, 3, 3, 3, 3, 1, 1), (0xa77, 0xa76, 0xa79, 0xa78), 0x200, 2, 0x400, 1),
    ((1, 1, 0, 3, 3, 3, 3, 3), (0xa78, 0xa77, 0xa76, 0xa79), 0x200, 4, 0x400, 1),
    ((3, 3, 1, 1, 0, 3, 3, 3), (0xa79, 0xa78, 0xa77, 0xa76), 0x200, 6, 0x400, 1),
    ((3, 3, 3, 3, 1, 1, 0, 3), (0xa76, 0xa79, 0xa78, 0xa77), 0x200, 0, 0x400, 1),
    ((0, 3, 3, 3, 3, 3, 1, 1), (0xa6d, 0xa6b, 0xa71, 0xa6f), 0x200, 2, 0x0, 0),
    ((1, 1, 0, 3, 3, 3, 3, 3), (0xa6f, 0xa6d, 0xa6b, 0xa71), 0x200, 4, 0x0, 0),
    ((3, 3, 1, 1, 0, 3, 3, 3), (0xa71, 0xa6f, 0xa6d, 0xa6b), 0x200, 6, 0x0, 0),
    ((3, 3, 3, 3, 1, 1, 0, 3), (0xa6b, 0xa71, 0xa6f, 0xa6d), 0x200, 0, 0x0, 0),
    ((1, 3, 3, 3, 3, 3, 1, 0), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 0, 1, 3, 3, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 1, 0, 1, 3, 3, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 3, 3, 1, 0, 1, 3), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 1, 3, 0, 0, 0, 0, 0), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((3, 3, 3, 3, 3, 0, 0, 1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 3, 3, 3, 3, 3, 0, 0), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
    ((1, 0, 0, 0, -1, -1, -1, -1), (0xa6f, 0xa6d, 0xa6b, 0xa71), 0x0, -1, 0x0, 0),
    ((0, 0, -1, -1, -1, -1, 1, 0), (0xa6d, 0xa6b, 0xa71, 0xa6f), 0x0, -1, 0x0, 0),
    ((-1, -1, -1, -1, 1, 0, 0, 0), (0xa6b, 0xa71, 0xa6f, 0xa6d), 0x0, -1, 0x0, 0),
    ((-1, -1, 1, 0, 0, 0, -1, -1), (0xa71, 0xa6f, 0xa6d, 0xa6b), 0x0, -1, 0x0, 0),
    ((1, -1, -1, -1, -1, 0, 0, 0), (0xa6b, 0xa71, 0xa6f, 0xa6d), 0x0, -1, 0x0, 0),
    ((-1, -1, -1, 0, 0, 0, 1, -1), (0xa6d, 0xa6b, 0xa71, 0xa6f), 0x0, -1, 0x0, 0),
    ((-1, 0, 0, 0, 1, -1, -1, -1), (0xa6f, 0xa6d, 0xa6b, 0xa71), 0x0, -1, 0x0, 0),
    ((0, 0, 1, -1, -1, -1, -1, 0), (0xa71, 0xa6f, 0xa6d, 0xa6b), 0x0, -1, 0x0, 0),
    ((0, 0, 0, 0, 0, 1, -1, 0), (0xa6c, 0xa6a, 0xa70, 0xa6e), 0x20400000, 6, 0x0, 0),
    ((-1, -1, 1, 0, 0, -1, -1, -1), (0xa71, 0xa6f, 0xa6d, 0xa6b), 0x0, -1, 0x0, 0),
    ((-1, -1, -1, -1, 1, 0, 0, -1), (0xa6b, 0xa71, 0xa6f, 0xa6d), 0x0, -1, 0x0, 0),
    ((0, -1, -1, -1, -1, -1, 1, 0), (0xa6d, 0xa6b, 0xa71, 0xa6f), 0x0, -1, 0x0, 0),
    ((1, 0, 0, -1, -1, -1, -1, -1), (0xa6f, 0xa6d, 0xa6b, 0xa71), 0x0, -1, 0x0, 0),
    ((1, -1, -1, -1, -1, -1, 0, 0), (0xa6b, 0xa71, 0xa6f, 0xa6d), 0x0, -1, 0x0, 0),
    ((-1, -1, -1, -1, 0, 0, 1, -1), (0xa6d, 0xa6b, 0xa71, 0xa6f), 0x0, -1, 0x0, 0),
    ((-1, -1, 0, 0, 1, -1, -1, -1), (0xa6f, 0xa6d, 0xa6b, 0xa71), 0x0, -1, 0x0, 0),
    ((0, 0, 1, -1, -1, -1, -1, -1), (0xa71, 0xa6f, 0xa6d, 0xa6b), 0x0, -1, 0x0, 0),
    ((0, 0, 0, 0, 1, -1, -1, -1), (0xa6b, 0xa71, 0xa6f, 0xa6d), 0x0, -1, 0x0, 0),
    ((-1, -1, 0, 0, 0, 0, 1, -1), (0xa6d, 0xa6b, 0xa71, 0xa6f), 0x0, -1, 0x0, 0),
    ((1, -1, -1, -1, 0, 0, 0, 0), (0xa6f, 0xa6d, 0xa6b, 0xa71), 0x0, -1, 0x0, 0),
    ((0, 0, 1, -1, -1, -1, 0, 0), (0xa71, 0xa6f, 0xa6d, 0xa6b), 0x0, -1, 0x0, 0),
    ((0, -1, -1, -1, 1, 0, 0, 0), (0xa6b, 0xa71, 0xa6f, 0xa6d), 0x0, -1, 0x0, 0),
    ((0, 0, 0, -1, -1, -1, 1, 0), (0xa6d, 0xa6b, 0xa71, 0xa6f), 0x0, -1, 0x0, 0),
    ((1, 0, 0, 0, 0, -1, -1, -1), (0xa6f, 0xa6d, 0xa6b, 0xa71), 0x0, -1, 0x0, 0),
    ((-1, -1, 1, 0, 0, 0, 0, -1), (0xa71, 0xa6f, 0xa6d, 0xa6b), 0x0, -1, 0x0, 0),
    ((0, 0, 1, 1, -1, -1, -1, 0), (0xa71, 0xa6f, 0xa6d, 0xa6b), 0x0, -1, 0x0, 0),
    ((-1, 1, 0, 0, 0, 0, 0, -1), (0xa70, 0xa6e, 0xa6c, 0xa6a), 0x0, -1, 0x0, 0),
    ((1, 0, 0, -1, 0, 0, 0, 2), (0xa6f, 0xa6f, 0xa6b, 0xa71), 0x0, -1, 0x0, 0),
    ((0, 0, -1, -1, -1, 1, 0, 0), (0xa6c, 0xa6a, 0xa70, 0xa6e), 0x0, -1, 0x0, 0),
    ((0, 0, 0, -1, -1, 1, 0, 0), (0xa6c, 0xa6a, 0xa70, 0xa6e), 0x0, -1, 0x0, 0),
    ((0, 0, 0, 2, 1, -1, -1, -1), (0x1, 0x1, 0x1, 0x1), 0x0, -1, 0x0, 0),
)

# 0x005FB558: pictures that count as "cliff" for the 2x2 neighbour test (FUN_0045E5A0); count 0x005FB638 = 56
PIECE_LIST = (0xa6d, 0xa3d, 0xa3e, 0xa3f, 0xa71, 0xa47, 0xa6f, 0xa40, 0xa41, 0xa42, 0xa6b, 0xa48, 0xa9a, 0xa9b,
              0xa9c, 0xa9d, 0xa92, 0xa93, 0xa94, 0xa95, 0xa82, 0xa86, 0xa83, 0xa87, 0xa88, 0xa84, 0xa85, 0xa89,
              0xaaa, 0xaab, 0xaac, 0xaad, 0xaaf, 0xaae, 0xab0, 0xab1, 0xac9, 0xac7, 0xac4, 0xa03, 0xa8b, 0xa8d,
              0xa8f, 0xa91, 0xaa2, 0xaa3, 0xaa4, 0xaa5, 0xaa6, 0xaa7, 0xaa8, 0xaa9, 0xa9e, 0xa9f, 0xaa0, 0xaa1)
PAIR_A = ((4, 2), (6, 4), (0, 6), (2, 0))      # 0x005FB63C, row dir/2: codes 0xa92..0xa95
PAIR_B = ((0, 6), (2, 0), (4, 2), (6, 4))      # 0x005FB65C: codes 0xa53..0xa56, 0xa8a, 0xa8c, 0xa8e, 0xa90
DEFER_B = {0xa53, 0xa54, 0xa55, 0xa56, 0xa8a, 0xa8c, 0xa8e, 0xa90}
# 0x005FB69C: {key: (picA, picB, result)}, built once by FUN_0045E840 (font_group_entry(i) = group i + 1)
STEP_TABLE = {
    0xaaa: (grp(154), grp(170), 0xa82),
    0xaab: (grp(171), grp(154), 0xa86),
    0xaac: (grp(155), grp(172), 0xa83),
    0xaad: (grp(173), grp(155), 0xa87),
    0xaaf: (grp(156), image_of(0xaaf), 0xa88),
    0xaae: (image_of(0xaae), image_of(0xa9c), 0xa84),
    0xab0: (image_of(0xa9d), image_of(0xab0), 0xa85),
    0xab1: (image_of(0xab1), image_of(0xa9d), 0xa89),
}
DOUBLE_TABLE = {0xa9a: 0xa8b, 0xa9b: 0xa8d, 0xa9c: 0xa8f, 0xa9d: 0xa91}         # 0x005FB71C
DOUBLE_VARIANTS = {0xa8b: (0xad2, 0xad3, 0xad4), 0xa8d: (0xad5, 0xad6, 0xad7),  # FUN_0045EB00, rand & 3 = 1..3
                   0xa8f: (0xad8, 0xad9, 0xada), 0xa91: (0xadb, 0xadc, 0xadd)}
# FUN_0045E110: code remap on 0x800000 tiles; None = by FUN_0045E080 (default, 1, 2, 3)
RAMP_REMAP = {0xa6a: 0xa8a, 0xa6c: 0xa8c, 0xa6e: 0xa8e, 0xa70: 0xa90,
              0xa6b: (0xac9, 0xaab, 0xaaa, 0xa9a), 0xa6d: (0xac7, 0xaad, 0xaac, 0xa9b),
              0xa6f: (0xac4, 0xaae, 0xaaf, 0xa9c), 0xa71: (0xa03, 0xab1, 0xab0, 0xa9d),
              0xa72: 0xa92, 0xa73: 0xa93, 0xa74: 0xa94, 0xa75: 0xa95,
              0xa76: 0xa9e, 0xa77: 0xa9f, 0xa78: 0xaa0, 0xa79: 0xaa1}
# FUN_0045DD40 / FUN_0045DE10: random variants: code -> alternatives for rand % (len + 1) = 1.. (0 keeps code)
VARIANTS = {0xa1f: (0xa39,), 0xa57: (0xa34,), 0xa58: (0xa3a,), 0xa59: (0xa2d, 0xa2e, 0xa2f), 0xa5a: (0xa3b,),
            0xa5b: (0xa30, 0xa31, 0xa32), 0xa5c: (0xa3c,), 0xa5d: (0xa33,), 0xa6a: (0xa49,), 0xa6b: (0xa48,),
            0xa6c: (0xa4a,), 0xa6d: (0xa3d, 0xa3e, 0xa3f), 0xa6e: (0xa4b,), 0xa6f: (0xa40, 0xa41, 0xa42),
            0xa70: (0xa4c,), 0xa71: (0xa47,), 0xa8a: (0xa53,), 0xa8c: (0xa54,), 0xa8e: (0xa55,), 0xa90: (0xa56,)}
VARIANT_COUNT_3 = {0xa9a, 0xa9b, 0xa9c, 0xa9d}   # count 3 in FUN_0045DD40 but no alternatives in FUN_0045DE10
SPACE_ID = COL + 0                                # SPR_SPACE: hidden tile below a plateau
ANCHOR = {0: (1, 0), 2: (0, 0), 4: (0, 1), 6: (1, 1)}   # (r, c) of the drawing tile of a 2x2 (building_footprint_place)


def _variant(code, rnd):
    """FUN_0045DE10."""
    alts = VARIANTS.get(code)
    if alts is None:
        return code
    k = rnd % (len(alts) + 1)
    return code if k == 0 else alts[k - 1]


def project(elev, flags=None, view=0):
    """map_elevation_project 0x0045ED20: projected altitude grid 0x008ECD0A for the view.  Each tile of height h
    marks the tile h steps away in (dx, dy) = (-1,-1) v0, (+1,-1) v2, (+1,+1) v4, (-1,+1) v6 (max with what is
    there), and when its (dx, dy) neighbour is higher by s, the s tiles beyond get h+1 .. h+s.  Used by the exe to
    pick the tile under the cursor (FUN_0045FB00: tile + proj * (-dx, -dy)), not by the ground pictures."""
    dx, dy = {0: (-1, -1), 2: (1, -1), 4: (1, 1), 6: (-1, 1)}[view]
    e = np.asarray(elev, np.int8).ravel().tolist()
    fl = None if flags is None else np.asarray(flags, np.uint32).ravel().tolist()
    p = [0] * NN
    step = dy * N + dx

    def inplay(x, y):
        if not (0 <= x < N and 0 <= y < N):
            return False
        return fl is None or not fl[y * N + x] & OFFMAP
    for y in range(N):
        for x in range(N):
            t = y * N + x
            h = e[t]
            if not inplay(x + h * dx, y + h * dy):
                continue
            tg = t + h * step
            h = max(h, p[tg])
            p[tg] = h
            nbr = t + step
            s = e[nbr] if 0 <= nbr < NN else 0
            if s - h > 0:
                q = nbr + h * step
                for i in range(1, s - h + 1):
                    if 0 <= q < NN:
                        p[q] = h + i
                    q += step
    return np.array(p, np.int8).reshape(N, N)


class _Cliffs:
    def __init__(self, flags, elev, rand, view, ids, draw, piece, desirability, alt_road):
        self.f = np.asarray(flags, np.uint32).ravel().tolist()
        self.e = np.asarray(elev, np.int8).ravel().tolist()
        self.r = np.asarray(rand, np.uint8).ravel().tolist()
        self.id = ids
        self.dr = draw
        self.pc = piece
        self.de = None if desirability is None else np.asarray(desirability, np.int8).ravel().tolist()
        self.view = view
        self.alt_road = alt_road
        self.code = [0] * NN
        self.dir = [0] * NN
        self.rfl = [0] * NN
        self.hidden = []                  # 0x00FA0724 list (the editor lowers these)
        self.raised = 0

    def E(self, t):
        return self.e[t] if 0 <= t < NN else 0

    # ---- FUN_0045E110 ---------------------------------------------------------------------
    def match(self, t):
        h = self.e[t]
        d = []
        for o in NB:
            u = t + o
            d.append(self.e[u] - h if 0 <= u < NN else 0)
        if not any(v > 0 for v in d):
            return None
        f = self.f[t]
        col = self.view // 2
        for pat, pics, rfl, rdir, mask, ramp_only in CLIFF_TABLE:
            if ramp_only and not f & RAMP:
                continue
            ok = True
            for p, v in zip(pat, d):
                if p == 3:
                    continue
                if p == 4:
                    if abs(v) > 1:
                        ok = False
                        break
                elif p != v:
                    ok = False
                    break
            if not ok:
                continue
            code = pics[col]
            if code in (1, 2):
                return code, None, None           # dir / flags globals stay stale in the exe (unused)
            f = self.f[t]
            if f & RAMP2:
                m = RAMP_REMAP.get(code)
                if isinstance(m, tuple):
                    code = m[self.side_ramp(t, rdir)]
                elif m is not None:
                    code = m
                if f & RAMP:
                    code = self.road_adj(code, t)
                    return _variant(code, self.r[t]), rdir, rfl
            if not ramp_only:
                return _variant(code, self.r[t]), rdir, rfl
            if mask & f == RAMP:
                code = self.road_adj(code, t)
                return _variant(code, self.r[t]), rdir, rfl
        return None

    def side_ramp(self, t, rdir):
        """FUN_0045E080: 0x800000 on the two side tiles (0x005FB52C / 0x005FB530 of row dir/2)."""
        _, a, b = SIDE[(rdir // 2) if rdir >= 0 else 0]    # rdir -1: (-1/2)*12 = 0 in C (truncation)
        u3 = self.f[t + b] & RAMP2
        u2 = self.f[t + a] & RAMP2
        if not u3 and u2:
            return 1
        if u3 and not u2:
            return 2
        if u3 and u2:
            return 3
        return 0

    def road_adj(self, code, t):
        if self.f[t] & ROAD:
            des = 0 if self.de is None else self.de[t]
            if (not self.f[t] & BEACH and des > 4) or self.alt_road:
                return code + 8
            return code + 4
        return code

    # ---- FUN_0045FA20 -----------------------------------------------------------------------
    def settle(self, t, code):
        h = self.e[t]
        if code == 1 or code == 2:
            self.e[t] = h + code
            self.raised += 1
            return
        hi, lo = 0, 16
        for o in NB:
            v = self.E(t + o)
            hi, lo = max(hi, v), min(lo, v)
        h = min(h, lo + 2)
        h = max(h, hi - 2)
        self.e[t] = h

    # ---- pass 1: FUN_0051FEC0 ----------------------------------------------------------------
    def pass1(self, t):
        self.f[t] &= 0xDFBFFDFF
        self.code[t] = self.dir[t] = self.rfl[t] = 0
        if self.f[t] & SPECIAL:
            return
        m = self.match(t)
        if m is not None:
            self.code[t], self.dir[t], self.rfl[t] = m[0], (m[1] if m[1] is not None else 0), (m[2] or 0)
        code = self.code[t]
        self.settle(t, code)
        if code in (1, 2):
            return
        if code == 0:
            for o in NB:
                u = t + o
                if not 0 <= u < NN:
                    break                                  # the exe ends the scan on an off-grid neighbour
                if self.e[t] < self.e[u]:
                    self.id[t] = SPACE_ID
                    self.hidden.append(t)
                    self.f[t] |= CLIFF
                    return
            return
        if 0xa92 <= code <= 0xa95 or code in DEFER_B:
            return
        self.paint(t, self.dir[t], code)
        if self.rfl[t]:
            self.f[t] |= self.rfl[t]
        self.f[t] |= CLIFF

    def paint(self, t, rdir, code):
        """FUN_0045E700."""
        if self.pc[t]:
            self.pc[t] &= 0xF0
        self.dr[t] = 0x40
        img = image_of(code)
        self.id[t] = img
        if rdir >= 0 and self.f[t] & RAMP2:
            u = t + NB[rdir]
            if self.pc[u]:
                self.pc[u] &= 0xF0
            self.dr[u] = 0x41
            self.id[u] = img + 1
            self.f[u] |= CLIFF

    # ---- pass 2: FUN_005200B0 ----------------------------------------------------------------
    def in_list(self, u):
        return 0 <= u < NN and self.id[u] in self._list_ids

    def pass2(self, t, x, y):
        code, rdir, rfl = self.code[t], self.dir[t], self.rfl[t]
        if code == 0:
            return False
        dr2 = (rdir // 2) if rdir >= 0 else 0
        placed = None
        if 0xa92 <= code <= 0xa95 or code in DEFER_B:
            a, b = (PAIR_A if 0xa92 <= code <= 0xa95 else PAIR_B)[dr2]
            if self.in_list(t + NB[a]) and self.in_list(t + NB[b]):
                self.dr[t] = 0x40
                ox, oy = {2: (1, 0), 4: (1, 1), 6: (0, 1)}.get(rdir, (0, 0))
                placed = (x - ox, y - oy, code)
        elif 0xaaa <= code <= 0xab1 or 0xa9a <= code <= 0xa9d:
            off = SIDE[dr2][1]
            if 0xaaa <= code <= 0xab1:
                rec = STEP_TABLE.get(code)
                res = 0
                if rec and self.id[t] == rec[0] and self.id[t + off] == rec[1]:
                    res = rec[2]
            else:
                res = 0
                key = DOUBLE_TABLE[code]
                img = image_of(code)
                if self.id[t] == img and self.id[t + off] == img:
                    res = key
                    k = self.r[t] & 3
                    if k:
                        res = DOUBLE_VARIANTS[key][k - 1]
            if res:
                self.dr[t] = 0x40
                ox, oy = {0: (1, 1), 2: (0, 1), 6: (1, 0)}.get(rdir, (0, 0))
                placed = (x - ox, y - oy, res)
        if placed is not None:
            self.place2x2(*placed)
            if rfl:
                self.f[t] |= rfl
            self.f[t] |= CLIFF
        if self.f[t] & RAMP2 and rdir >= 0:
            u = t + NB[rdir]
            if 0xaa2 <= code <= 0xaa9:
                self.f[u] |= ROAD
            if 0xa9e <= code <= 0xaa9:
                self.f[u] |= 0x800400
            if 0xa9e <= code <= 0xaa9 or code in (0xa03, 0xac4, 0xac7, 0xac9) or 0xa9a <= code <= 0xa9d \
                    or 0xaaa <= code <= 0xab1:
                self.f[u] = (self.f[u] & ~0x80) | CLIFF
        return True

    def place2x2(self, x, y, code):
        """building_footprint_place(0, x, y, 2, 2, image, 0x200) 0x004A04B0."""
        if x < 0 or y < 0 or x + 1 >= N or y + 1 >= N:
            return
        img = image_of(code)
        ar, ac = ANCHOR[self.view]
        for r in range(2):
            for c in range(2):
                u = (y + r) * N + x + c
                self.f[u] = (self.f[u] & 0x93872F90) | CLIFF
                self.pc[u] = (self.pc[u] & 0xE0) | 1
                self.id[u] = img
                self.dr[u] = (r * 8 + c) | (0x40 if (r, c) == (ar, ac) else 0)
                self.placed.add(u)

    def run(self, project_flags=True):
        self._list_ids = {image_of(c) for c in PIECE_LIST}
        self.placed = set()
        if project_flags:                                       # map_elevation_project's flag clean-up
            for t in range(NN):
                f = self.f[t]
                if not f & CLIFF:
                    f &= ~(RAMP | RAMP2)
                else:
                    f &= ~(0x800 | 0x80 | 0x1)
                self.f[t] = f & 0xFFFFFFFF
        for t in range(NN):                                     # pass 1
            if self.f[t] & SKIP_TILE:
                continue
            if not self.f[t] & CLIFF:
                self.id[t] = 0
            self.pass1(t)
        self.handled = [False] * NN
        for y in range(N):                                      # pass 2 (cliff part only)
            for x in range(N):
                t = y * N + x
                if self.f[t] & SKIP_TILE:
                    continue
                self.handled[t] = self.pass2(t, x, y)


def cliffs(flags, elev, rand, view=0, orig_ids=None, draw=None, piece=None, desirability=None, alt_road=0,
           full=False):
    """Recompute the cliff part of the ground pictures for view 0/2/4/6, as the exe does on load and on every turn.

    flags   u32[228][228] terrain flags (rank 6), with the map's own cliff bits (0x200) set
    elev    elevation (rank 23);  rand: random grid (rank 8)
    orig_ids, draw, piece: the current image ids (rank 4, v247 numbering converted by the caller or not:
            ids are only kept for tiles the algorithm does not touch), draw bytes (rank 5), piece (rank 7)
    desirability: only for road ramps;  alt_road: the unknown global DAT_00B1E8C0
    Returns (ids, draw, flags_out) as full grids.  Cliff tiles are those with flags_out & 0x200: use ids/draw
    there and terrain_images for the rest.  Pass 1 zeroes the image of every non-cliff tile (the other painters
    of terrain_images fill them); tiles that had 0x200 on input and lost it keep their old image in the exe too.
    full=True also returns a dict with 'code' (picture code per tile), 'elev' (after FUN_0045FA20), 'hidden'
    (SPR_SPACE tiles), 'raised' (tiles raised by codes 1/2), 'placed' (2x2 tiles).
    """
    z = np.zeros((N, N), np.uint8)
    ids = ([0] * NN if orig_ids is None else np.asarray(orig_ids, np.int64).ravel().tolist())
    dr = ([0] * NN if draw is None else np.asarray(draw, np.uint8).ravel().tolist())
    pc = np.asarray(z if piece is None else piece, np.uint8).ravel().tolist()
    c = _Cliffs(flags, elev, rand, view, ids, dr, pc, desirability, alt_road)
    c.run()
    out = (np.array(c.id, np.uint32).reshape(N, N), np.array(c.dr, np.uint8).reshape(N, N),
           np.array(c.f, np.uint32).reshape(N, N))
    if full:
        return out + ({'code': np.array(c.code, np.int32).reshape(N, N), 'elev': np.array(c.e, np.int8).reshape(N, N),
                       'hidden': c.hidden, 'raised': c.raised, 'placed': c.placed,
                       'piece': np.array(c.pc, np.uint8).reshape(N, N)},)
    return out


def turned(x, y, view):
    """World tile -> the tile position it is shown at in a view-0 projection (docs/play/rotation.md)."""
    return {0: (x, y), 2: (y, N - 1 - x), 4: (N - 1 - x, N - 1 - y), 6: (N - 1 - y, x)}[view]


def _selfcheck(map_path=None):
    import os
    import sys
    from collections import Counter
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import mapfile
    import terrain_images
    path = map_path or os.path.join(here, "..", "zeus-original/app/Adventures/}Open Play Sandbox.pak")
    hdr, blocks = mapfile.read_file(path)[0]
    d = {b["rank"]: b["data"] for b in blocks}

    def grid(r, dt):
        return np.frombuffer(d[r], dt)[:NN].reshape(N, N)
    fl, el, rn, pc, dr0 = grid(6, "<u4"), grid(23, "u1"), grid(8, "u1"), grid(7, "u1"), grid(5, "u1")
    ref = grid(4, "<u4")
    ref = terrain_images.norm_ids(ref) if hdr["version"] < 300 else ref
    cl_in = (fl & CLIFF) > 0
    ids, drw, fo, info = cliffs(fl, el, rn, 0, orig_ids=ref, draw=dr0, piece=pc, full=True)
    cl_out = (fo & CLIFF) > 0
    both = cl_in & cl_out
    ok = both & (ids == ref)
    okd = both & (drw == dr0)
    print("view 0: map cliff tiles %d, computed cliff tiles %d, in both %d" % (cl_in.sum(), cl_out.sum(), both.sum()))
    print("view 0: image id match %d / %d = %.2f%% of the map's cliff tiles; draw byte match %.2f%%"
          % (ok.sum(), cl_in.sum(), 100.0 * ok.sum() / cl_in.sum(), 100.0 * okd.sum() / cl_in.sum()))
    rest = (cl_in ^ cl_out) | (both & ((ids != ref) | (drw != dr0)))
    for y, x in zip(*np.nonzero(rest)):
        print("  miss (%d,%d) flags %08x->%08x elev %d code %#x id %d ref %d draw %#x ref %#x"
              % (x, y, fl[y, x], fo[y, x], el[y, x], info['code'][y, x], ids[y, x] - COL, ref[y, x] - COL,
                 drw[y, x], dr0[y, x]))
    fbits = (fo ^ fl) & cl_out
    print("view 0: elevation changed by FUN_0045FA20 on %d tiles, raised %d, hidden (SPR_SPACE) %d, 2x2 tiles %d,"
          " cliff tiles whose flags differ from the map %d"
          % ((info['elev'] != el.astype(np.int8)).sum(), info['raised'], len(info['hidden']), len(info['placed']),
             (fbits > 0).sum()))
    print("        changed flag bits on those tiles: %s (0x1 = map_elevation_project drops tree bits on cliff tiles)"
          % dict(Counter(hex(int(b)) for b in fbits[fbits > 0])))
    for v in (2, 4, 6):
        ids_v, drw_v, fo_v, inf = cliffs(fl, el, rn, v, orig_ids=ref, draw=dr0, piece=pc, full=True)
        cv = (fo_v & CLIFF) > 0
        diff = cv & (ids_v != ids)
        print("view %d: cliff tiles %d, hidden %d, 2x2 tiles %d, draw bytes %s, ids differing from view 0: %d, "
              "distinct ids %d" % (v, cv.sum(), len(inf['hidden']), len(inf['placed']),
                                   dict(Counter(drw_v[cv].tolist())), diff.sum(), len(set(ids_v[cv].tolist()))))
    # Maps the editor saved while the view was turned: their stored pictures/draw bytes are those of that view.
    for name, k, view in (("}Open Play Military.pak", 0, 6), ("&Enlightenment in the West.pak", 0, 4)):
        hdr2, bl2 = mapfile.read_file(os.path.join(here, "..", "zeus-original/app/Adventures", name))[k]
        d2 = {b["rank"]: b["data"] for b in bl2}

        def g2(r, dt):
            return np.frombuffer(d2[r], dt)[:NN].reshape(N, N)
        f2, r2 = g2(6, "<u4"), g2(4, "<u4")
        r2 = terrain_images.norm_ids(r2) if hdr2["version"] < 300 else r2
        c2 = (f2 & CLIFF) > 0
        res = []
        for v in (0, 2, 4, 6):
            i2, d2v, _ = cliffs(f2, g2(23, "u1"), g2(8, "u1"), v, orig_ids=r2, draw=g2(5, "u1"), piece=g2(7, "u1"))
            res.append("v%d %.1f%%" % (v, 100.0 * (c2 & (i2 == r2) & (d2v == g2(5, "u1"))).sum() / c2.sum()))
        print("%s map %d (saved in view %d), %d cliff tiles, id+draw match: %s" % (name, k, view, c2.sum(),
                                                                                 ", ".join(res)))
    return ok.sum() / cl_in.sum()


if __name__ == "__main__":
    _selfcheck()
