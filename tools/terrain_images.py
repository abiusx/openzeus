"""Terrain image assignment of Zeus: Master of Olympus, ported from Zeus.exe (GOG 2.1) for the play mode.

images(flags, elev, rand, orig_ids=None, ...) -> uint32 [228][228] grid of image ids.

Conventions
  * grids are [y][x] (index = y*228 + x), 228 x 228, like rank 6/8/23 of a .map.
  * image id = collection*0x4000 + n, here always collection 5 (Zeus_Terrain; v247 maps store 3, add +2
    to collections >= 2, `norm_ids()` does it).  n is 0-based: atlas.json image 'index' = n + 201
    (= position n + 200 in the 'images' list).  GROUPS[g] = (name, first n, count): image of group g,
    offset k = 5*0x4000 + first + k.  Group numbers are the ones in atlas.json 'groups'.
  * A tile is drawn only if its draw grid has 0x40 (see images_full(): multi-tile blocks).

What is ported (addresses in Zeus.exe, see docs/play/terrain.md): the loop map_tiles_update_images 0x0051F450 with
plain land (0x0051FBA0), scrub grass (0x0051F860), meadow/trees/reeds (0x004A81F0), water + shore (0x00520CA0),
beach (0x00520B80), rock / ore (0x00520580), marble (0x00520920), rubble (0x005214B0), marsh (0x00521150),
roads (0x004A0190, needs `desirability`).  Cliffs, ramps, lava, gardens are NOT computed: they keep `orig_ids`
(cliff tiles are static during play); special 0x10000000 tiles (monument extras) are computed as plain ground (the exe
does unless its step rule 0x00546380 gives a step image, drawn over them in play mode).
View orientation: ids are those of view 0 (north); images_full(alt=...) also gives the other views' deltas
for pattern-table tiles (column view/2 of each record).
"""
import numpy as np

N = 228
COL = 5 * 0x4000
T_WATER = [  # exe 0x00634C00, 48 records: (pattern[8], group_index per view orientation[4], flags, variants)
    ((1, 2, 1, 2, 1, 2, 1, 2), (79, 79, 79, 79), 0, 1),
    ((1, 2, 1, 2, 1, 2, 0, 2), (47, 46, 45, 44), 0, 1),
    ((0, 2, 1, 2, 1, 2, 1, 2), (44, 47, 46, 45), 0, 1),
    ((1, 2, 0, 2, 1, 2, 1, 2), (45, 44, 47, 46), 0, 1),
    ((1, 2, 1, 2, 0, 2, 1, 2), (46, 45, 44, 47), 0, 1),
    ((1, 2, 0, 2, 1, 2, 0, 2), (40, 42, 40, 42), 0, 2),
    ((0, 2, 1, 2, 0, 2, 1, 2), (42, 40, 42, 40), 0, 2),
    ((1, 2, 1, 2, 0, 0, 0, 2), (32, 28, 24, 36), 0, 4),
    ((0, 2, 1, 2, 1, 2, 0, 0), (36, 32, 28, 24), 0, 4),
    ((0, 0, 0, 2, 1, 2, 1, 2), (24, 36, 32, 28), 0, 4),
    ((1, 2, 0, 0, 0, 2, 1, 2), (28, 24, 36, 32), 0, 4),
    ((1, 2, 1, 2, 0, 1, 0, 2), (77, 76, 75, 78), 0, 1),
    ((0, 2, 1, 2, 1, 2, 0, 1), (78, 77, 76, 75), 0, 1),
    ((0, 1, 0, 2, 1, 2, 1, 2), (75, 78, 77, 76), 0, 1),
    ((1, 2, 0, 1, 0, 2, 1, 2), (76, 75, 78, 77), 0, 1),
    ((1, 2, 0, 0, 0, 0, 0, 2), (16, 12, 8, 20), 0, 4),
    ((0, 2, 1, 2, 0, 0, 0, 0), (20, 16, 12, 8), 0, 4),
    ((0, 0, 0, 2, 1, 2, 0, 0), (8, 20, 16, 12), 0, 4),
    ((0, 0, 0, 0, 0, 2, 1, 2), (12, 8, 20, 16), 0, 4),
    ((1, 2, 0, 1, 0, 0, 0, 2), (69, 66, 63, 72), 0, 1),
    ((0, 2, 1, 2, 0, 1, 0, 0), (72, 69, 66, 63), 0, 1),
    ((0, 0, 0, 2, 1, 2, 0, 1), (63, 72, 69, 66), 0, 1),
    ((0, 1, 0, 0, 0, 2, 1, 2), (66, 63, 72, 69), 0, 1),
    ((1, 2, 0, 0, 0, 1, 0, 2), (70, 67, 64, 73), 0, 1),
    ((0, 2, 1, 2, 0, 0, 0, 1), (73, 70, 67, 64), 0, 1),
    ((0, 1, 0, 2, 1, 2, 0, 0), (64, 73, 70, 67), 0, 1),
    ((0, 0, 0, 1, 0, 2, 1, 2), (67, 64, 73, 70), 0, 1),
    ((1, 2, 0, 1, 0, 1, 0, 2), (71, 68, 65, 74), 0, 1),
    ((0, 2, 1, 2, 0, 1, 0, 1), (74, 71, 68, 65), 0, 1),
    ((0, 1, 0, 2, 1, 2, 0, 1), (65, 74, 71, 68), 0, 1),
    ((0, 1, 0, 1, 0, 2, 1, 2), (68, 65, 74, 71), 0, 1),
    ((0, 1, 0, 1, 0, 1, 0, 1), (62, 62, 62, 62), 0, 1),
    ((0, 1, 0, 1, 0, 1, 0, 0), (60, 59, 58, 61), 0, 1),
    ((0, 0, 0, 1, 0, 1, 0, 1), (61, 60, 59, 58), 0, 1),
    ((0, 1, 0, 0, 0, 1, 0, 1), (58, 61, 60, 59), 0, 1),
    ((0, 1, 0, 1, 0, 0, 0, 1), (59, 58, 61, 60), 0, 1),
    ((0, 1, 0, 0, 0, 1, 0, 0), (48, 49, 48, 49), 0, 1),
    ((0, 0, 0, 1, 0, 0, 0, 1), (49, 48, 49, 48), 0, 1),
    ((0, 1, 0, 1, 0, 0, 0, 0), (56, 55, 54, 57), 0, 1),
    ((0, 0, 0, 1, 0, 1, 0, 0), (57, 56, 55, 54), 0, 1),
    ((0, 0, 0, 0, 0, 1, 0, 1), (54, 57, 56, 55), 0, 1),
    ((0, 1, 0, 0, 0, 0, 0, 1), (55, 54, 57, 56), 0, 1),
    ((0, 1, 0, 0, 0, 0, 0, 0), (52, 51, 50, 53), 0, 1),
    ((0, 0, 0, 1, 0, 0, 0, 0), (53, 52, 51, 50), 0, 1),
    ((0, 0, 0, 0, 0, 1, 0, 0), (50, 53, 52, 51), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 1), (51, 50, 53, 52), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 0), 0, 6),
    ((0, 0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 0), 0, 0),
]
T_EDGE = [  # exe 0x00636D38, 26 records: (pattern[8], group_index per view orientation[4], flags, variants)
    ((1, 2, 1, 2, 1, 2, 1, 2), (14, 14, 14, 14), 0, 6),
    ((1, 2, 1, 2, 1, 2, 0, 2), (14, 14, 14, 14), 0, 6),
    ((0, 2, 1, 2, 1, 2, 1, 2), (14, 14, 14, 14), 0, 6),
    ((1, 2, 0, 2, 1, 2, 1, 2), (14, 14, 14, 14), 0, 6),
    ((1, 2, 1, 2, 0, 2, 1, 2), (14, 14, 14, 14), 0, 6),
    ((1, 2, 0, 2, 1, 2, 0, 2), (14, 14, 14, 14), 0, 6),
    ((0, 2, 1, 2, 0, 2, 1, 2), (14, 14, 14, 14), 0, 6),
    ((1, 2, 1, 2, 1, 2, 0, 2), (14, 14, 14, 14), 0, 6),
    ((0, 2, 1, 2, 1, 2, 1, 2), (14, 14, 14, 14), 0, 6),
    ((1, 2, 0, 2, 1, 2, 1, 2), (14, 14, 14, 14), 0, 6),
    ((1, 2, 1, 2, 0, 2, 1, 2), (14, 14, 14, 14), 0, 6),
    ((1, 2, 1, 2, 0, 0, 0, 2), (1, 7, 5, 3), 0, 1),
    ((0, 2, 1, 2, 1, 2, 0, 0), (3, 1, 7, 5), 0, 1),
    ((0, 0, 0, 2, 1, 2, 1, 2), (5, 3, 1, 7), 0, 1),
    ((1, 2, 0, 0, 0, 2, 1, 2), (7, 5, 3, 1), 0, 1),
    ((1, 2, 0, 0, 0, 0, 0, 2), (0, 6, 4, 2), 0, 1),
    ((0, 2, 1, 2, 0, 0, 0, 0), (2, 0, 6, 4), 0, 1),
    ((0, 0, 0, 2, 1, 2, 0, 0), (4, 2, 0, 6), 0, 1),
    ((0, 0, 0, 0, 0, 2, 1, 2), (6, 4, 2, 0), 0, 1),
    ((0, 1, 0, 0, 0, 1, 0, 0), (12, 13, 12, 13), 0, 1),
    ((0, 0, 0, 1, 0, 0, 0, 1), (13, 12, 13, 12), 0, 1),
    ((0, 1, 0, 0, 0, 0, 0, 0), (8, 11, 10, 9), 0, 1),
    ((0, 0, 0, 1, 0, 0, 0, 0), (9, 8, 11, 10), 0, 1),
    ((0, 0, 0, 0, 0, 1, 0, 0), (10, 9, 8, 11), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 1), (11, 10, 9, 8), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 0), (14, 14, 14, 14), 0, 6),
]
T_CRACKS = [  # exe 0x00636BE0, 17 records: (pattern[8], group_index per view orientation[4], flags, variants)
    ((1, 2, 1, 2, 1, 2, 1, 2), (29, 29, 29, 29), 0, 1),
    ((1, 2, 1, 2, 1, 2, 0, 2), (25, 28, 27, 26), 0, 1),
    ((0, 2, 1, 2, 1, 2, 1, 2), (26, 25, 28, 27), 0, 1),
    ((1, 2, 0, 2, 1, 2, 1, 2), (27, 26, 25, 28), 0, 1),
    ((1, 2, 1, 2, 0, 2, 1, 2), (28, 27, 26, 25), 0, 1),
    ((1, 2, 1, 2, 0, 2, 0, 2), (8, 14, 12, 10), 0, 2),
    ((0, 2, 1, 2, 1, 2, 0, 2), (10, 8, 14, 12), 0, 2),
    ((0, 2, 0, 2, 1, 2, 1, 2), (12, 10, 8, 14), 0, 2),
    ((1, 2, 0, 2, 0, 2, 1, 2), (14, 12, 10, 8), 0, 2),
    ((1, 2, 0, 2, 1, 2, 0, 2), (0, 4, 0, 4), 0, 4),
    ((0, 2, 1, 2, 0, 2, 1, 2), (4, 0, 4, 0), 0, 4),
    ((1, 2, 0, 2, 0, 2, 0, 2), (16, 22, 18, 20), 0, 2),
    ((0, 2, 1, 2, 0, 2, 0, 2), (20, 16, 22, 18), 0, 2),
    ((0, 2, 0, 2, 1, 2, 0, 2), (18, 20, 16, 22), 0, 2),
    ((0, 2, 0, 2, 0, 2, 1, 2), (22, 18, 20, 16), 0, 2),
    ((0, 2, 0, 2, 0, 2, 0, 2), (24, 24, 24, 24), 0, 1),
    ((2, 2, 2, 2, 2, 2, 2, 2), (24, 24, 24, 24), 0, 1),
]
T_LAVA = [  # exe 0x00634FC0, 48 records (FUN_00520820 looks up the INVERTED lava bits: 1 = the neighbour is not lava)
    ((1, 2, 1, 2, 1, 2, 1, 2), (77, 77, 77, 77), 0, 1),
    ((1, 2, 1, 2, 1, 2, 0, 2), (45, 44, 43, 42), 0, 1),
    ((0, 2, 1, 2, 1, 2, 1, 2), (42, 45, 44, 43), 0, 1),
    ((1, 2, 0, 2, 1, 2, 1, 2), (43, 42, 45, 44), 0, 1),
    ((1, 2, 1, 2, 0, 2, 1, 2), (44, 43, 42, 45), 0, 1),
    ((1, 2, 0, 2, 1, 2, 0, 2), (38, 40, 38, 40), 0, 2),
    ((0, 2, 1, 2, 0, 2, 1, 2), (40, 38, 40, 38), 0, 2),
    ((1, 2, 1, 2, 0, 0, 0, 2), (30, 26, 22, 34), 0, 4),
    ((0, 2, 1, 2, 1, 2, 0, 0), (34, 30, 26, 22), 0, 4),
    ((0, 0, 0, 2, 1, 2, 1, 2), (22, 34, 30, 26), 0, 4),
    ((1, 2, 0, 0, 0, 2, 1, 2), (26, 22, 34, 30), 0, 4),
    ((1, 2, 1, 2, 0, 1, 0, 2), (75, 74, 73, 76), 0, 1),
    ((0, 2, 1, 2, 1, 2, 0, 1), (76, 75, 74, 73), 0, 1),
    ((0, 1, 0, 2, 1, 2, 1, 2), (73, 76, 75, 74), 0, 1),
    ((1, 2, 0, 1, 0, 2, 1, 2), (74, 73, 76, 75), 0, 1),
    ((1, 2, 0, 0, 0, 0, 0, 2), (14, 10, 6, 18), 0, 4),
    ((0, 2, 1, 2, 0, 0, 0, 0), (18, 14, 10, 6), 0, 4),
    ((0, 0, 0, 2, 1, 2, 0, 0), (6, 18, 14, 10), 0, 4),
    ((0, 0, 0, 0, 0, 2, 1, 2), (10, 6, 18, 14), 0, 4),
    ((1, 2, 0, 1, 0, 0, 0, 2), (67, 64, 61, 70), 0, 1),
    ((0, 2, 1, 2, 0, 1, 0, 0), (70, 67, 64, 61), 0, 1),
    ((0, 0, 0, 2, 1, 2, 0, 1), (61, 70, 67, 64), 0, 1),
    ((0, 1, 0, 0, 0, 2, 1, 2), (64, 61, 70, 67), 0, 1),
    ((1, 2, 0, 0, 0, 1, 0, 2), (68, 65, 62, 71), 0, 1),
    ((0, 2, 1, 2, 0, 0, 0, 1), (71, 68, 65, 62), 0, 1),
    ((0, 1, 0, 2, 1, 2, 0, 0), (62, 71, 68, 65), 0, 1),
    ((0, 0, 0, 1, 0, 2, 1, 2), (65, 62, 71, 68), 0, 1),
    ((1, 2, 0, 1, 0, 1, 0, 2), (69, 66, 63, 72), 0, 1),
    ((0, 2, 1, 2, 0, 1, 0, 1), (72, 69, 66, 63), 0, 1),
    ((0, 1, 0, 2, 1, 2, 0, 1), (63, 72, 69, 66), 0, 1),
    ((0, 1, 0, 1, 0, 2, 1, 2), (66, 63, 72, 69), 0, 1),
    ((0, 1, 0, 1, 0, 1, 0, 1), (60, 60, 60, 60), 0, 1),
    ((0, 1, 0, 1, 0, 1, 0, 0), (58, 57, 56, 59), 0, 1),
    ((0, 0, 0, 1, 0, 1, 0, 1), (59, 58, 57, 56), 0, 1),
    ((0, 1, 0, 0, 0, 1, 0, 1), (56, 59, 58, 57), 0, 1),
    ((0, 1, 0, 1, 0, 0, 0, 1), (57, 56, 59, 58), 0, 1),
    ((0, 1, 0, 0, 0, 1, 0, 0), (46, 47, 46, 47), 0, 1),
    ((0, 0, 0, 1, 0, 0, 0, 1), (47, 46, 47, 46), 0, 1),
    ((0, 1, 0, 1, 0, 0, 0, 0), (54, 53, 52, 55), 0, 1),
    ((0, 0, 0, 1, 0, 1, 0, 0), (55, 54, 53, 52), 0, 1),
    ((0, 0, 0, 0, 0, 1, 0, 1), (52, 55, 54, 53), 0, 1),
    ((0, 1, 0, 0, 0, 0, 0, 1), (53, 52, 55, 54), 0, 1),
    ((0, 1, 0, 0, 0, 0, 0, 0), (50, 49, 48, 51), 0, 1),
    ((0, 0, 0, 1, 0, 0, 0, 0), (51, 50, 49, 48), 0, 1),
    ((0, 0, 0, 0, 0, 1, 0, 0), (48, 51, 50, 49), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 1), (49, 48, 51, 50), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 0), 0, 6),
    ((0, 0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 0), 0, 0),
]
T_MARBLE = [  # exe 0x006375B0, 32 records: (pattern[8], group_index per view orientation[4], flags, variants)
    ((1, 2, 1, 2, 1, 2, 1, 2), (0, 0, 0, 0), 0, 6),
    ((1, 2, 1, 2, 1, 2, 0, 2), (0, 0, 0, 0), 0, 6),
    ((0, 2, 1, 2, 1, 2, 1, 2), (0, 0, 0, 0), 0, 6),
    ((1, 2, 0, 2, 1, 2, 1, 2), (0, 0, 0, 0), 0, 6),
    ((1, 2, 1, 2, 0, 2, 1, 2), (0, 0, 0, 0), 0, 6),
    ((1, 2, 0, 2, 1, 2, 0, 2), (0, 0, 0, 0), 0, 6),
    ((0, 2, 1, 2, 0, 2, 1, 2), (0, 0, 0, 0), 0, 6),
    ((1, 2, 1, 2, 1, 2, 0, 2), (0, 0, 0, 0), 0, 6),
    ((0, 2, 1, 2, 1, 2, 1, 2), (0, 0, 0, 0), 0, 6),
    ((1, 2, 0, 2, 1, 2, 1, 2), (0, 0, 0, 0), 0, 6),
    ((1, 2, 1, 2, 0, 2, 1, 2), (0, 0, 0, 0), 0, 6),
    ((1, 2, 1, 2, 0, 0, 0, 2), (10, 6, 18, 14), 0, 1),
    ((0, 2, 1, 2, 1, 2, 0, 0), (14, 10, 6, 18), 0, 1),
    ((0, 0, 0, 2, 1, 2, 1, 2), (18, 14, 10, 6), 0, 1),
    ((1, 2, 0, 0, 0, 2, 1, 2), (6, 18, 14, 10), 0, 1),
    ((1, 2, 0, 0, 0, 0, 0, 2), (7, 19, 15, 11), 0, 3),
    ((0, 2, 1, 2, 0, 0, 0, 0), (11, 7, 19, 15), 0, 3),
    ((0, 0, 0, 2, 1, 2, 0, 0), (15, 11, 7, 19), 0, 3),
    ((0, 0, 0, 0, 0, 2, 1, 2), (19, 15, 11, 7), 0, 3),
    ((1, 2, 0, 1, 0, 0, 0, 2), (26, 33, 30, 29), 0, 1),
    ((0, 2, 1, 2, 0, 1, 0, 0), (29, 26, 33, 30), 0, 1),
    ((0, 0, 0, 2, 1, 2, 0, 1), (30, 29, 26, 33), 0, 1),
    ((0, 1, 0, 0, 0, 2, 1, 2), (33, 30, 29, 26), 0, 1),
    ((1, 2, 0, 0, 0, 1, 0, 2), (27, 32, 31, 28), 0, 1),
    ((0, 2, 1, 2, 0, 0, 0, 1), (28, 27, 32, 31), 0, 1),
    ((0, 1, 0, 2, 1, 2, 0, 0), (31, 28, 27, 32), 0, 1),
    ((0, 0, 0, 1, 0, 2, 1, 2), (32, 31, 28, 27), 0, 1),
    ((0, 1, 0, 0, 0, 0, 0, 0), (23, 22, 25, 24), 0, 1),
    ((0, 0, 0, 1, 0, 0, 0, 0), (24, 23, 22, 25), 0, 1),
    ((0, 0, 0, 0, 0, 1, 0, 0), (25, 24, 23, 22), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 1), (22, 25, 24, 23), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 0), 0, 6),
]
T_PIT = [  # exe 0x00637830, 48 records (the 48th, count 0, never matches first): marble pits, shallow and deep
    ((1, 2, 1, 2, 1, 2, 1, 2), (37, 37, 37, 37), 0, 1),
    ((1, 2, 1, 2, 1, 2, 0, 2), (59, 58, 51, 50), 0, 1),
    ((0, 2, 1, 2, 1, 2, 1, 2), (50, 59, 58, 51), 0, 1),
    ((1, 2, 0, 2, 1, 2, 1, 2), (51, 50, 59, 58), 0, 1),
    ((1, 2, 1, 2, 0, 2, 1, 2), (58, 51, 50, 59), 0, 1),
    ((1, 2, 0, 2, 1, 2, 0, 2), (57, 56, 57, 56), 0, 1),
    ((0, 2, 1, 2, 0, 2, 1, 2), (56, 57, 56, 57), 0, 1),
    ((1, 2, 1, 2, 0, 0, 0, 2), (10, 6, 18, 14), 0, 1),
    ((0, 2, 1, 2, 1, 2, 0, 0), (14, 10, 6, 18), 0, 1),
    ((0, 0, 0, 2, 1, 2, 1, 2), (18, 14, 10, 6), 0, 1),
    ((1, 2, 0, 0, 0, 2, 1, 2), (6, 18, 14, 10), 0, 1),
    ((1, 2, 1, 2, 0, 1, 0, 2), (54, 53, 52, 55), 0, 1),
    ((0, 2, 1, 2, 1, 2, 0, 1), (55, 54, 53, 52), 0, 1),
    ((0, 1, 0, 2, 1, 2, 1, 2), (52, 55, 54, 53), 0, 1),
    ((1, 2, 0, 1, 0, 2, 1, 2), (53, 52, 55, 54), 0, 1),
    ((1, 2, 0, 0, 0, 0, 0, 2), (7, 19, 15, 11), 0, 3),
    ((0, 2, 1, 2, 0, 0, 0, 0), (11, 7, 19, 15), 0, 3),
    ((0, 0, 0, 2, 1, 2, 0, 0), (15, 11, 7, 19), 0, 3),
    ((0, 0, 0, 0, 0, 2, 1, 2), (19, 15, 11, 7), 0, 3),
    ((1, 2, 0, 1, 0, 0, 0, 2), (41, 38, 47, 44), 0, 1),
    ((0, 2, 1, 2, 0, 1, 0, 0), (44, 41, 38, 47), 0, 1),
    ((0, 0, 0, 2, 1, 2, 0, 1), (47, 44, 41, 38), 0, 1),
    ((0, 1, 0, 0, 0, 2, 1, 2), (38, 47, 44, 41), 0, 1),
    ((1, 2, 0, 0, 0, 1, 0, 2), (42, 39, 48, 45), 0, 1),
    ((0, 2, 1, 2, 0, 0, 0, 1), (45, 42, 39, 48), 0, 1),
    ((0, 1, 0, 2, 1, 2, 0, 0), (48, 45, 42, 39), 0, 1),
    ((0, 0, 0, 1, 0, 2, 1, 2), (39, 48, 45, 42), 0, 1),
    ((1, 2, 0, 1, 0, 1, 0, 2), (43, 40, 49, 46), 0, 1),
    ((0, 2, 1, 2, 0, 1, 0, 1), (46, 43, 40, 49), 0, 1),
    ((0, 1, 0, 2, 1, 2, 0, 1), (49, 46, 43, 40), 0, 1),
    ((0, 1, 0, 1, 0, 2, 1, 2), (40, 49, 46, 43), 0, 1),
    ((0, 1, 0, 1, 0, 1, 0, 1), (22, 22, 22, 22), 0, 1),
    ((0, 1, 0, 1, 0, 1, 0, 0), (26, 25, 24, 23), 0, 1),
    ((0, 0, 0, 1, 0, 1, 0, 1), (23, 26, 25, 24), 0, 1),
    ((0, 1, 0, 0, 0, 1, 0, 1), (24, 23, 26, 25), 0, 1),
    ((0, 1, 0, 1, 0, 0, 0, 1), (25, 24, 23, 26), 0, 1),
    ((0, 1, 0, 0, 0, 1, 0, 0), (32, 31, 32, 31), 0, 1),
    ((0, 0, 0, 1, 0, 0, 0, 1), (31, 32, 31, 32), 0, 1),
    ((0, 1, 0, 1, 0, 0, 0, 0), (27, 30, 29, 28), 0, 1),
    ((0, 0, 0, 1, 0, 1, 0, 0), (28, 27, 30, 29), 0, 1),
    ((0, 0, 0, 0, 0, 1, 0, 1), (29, 28, 27, 30), 0, 1),
    ((0, 1, 0, 0, 0, 0, 0, 1), (30, 29, 28, 27), 0, 1),
    ((0, 1, 0, 0, 0, 0, 0, 0), (34, 36, 35, 33), 0, 1),
    ((0, 0, 0, 1, 0, 0, 0, 0), (33, 34, 36, 35), 0, 1),
    ((0, 0, 0, 0, 0, 1, 0, 0), (35, 33, 34, 36), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 1), (36, 35, 33, 34), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 0), 0, 6),
]
T_ROAD_A = [  # exe 0x006371F0, 48 records: (pattern[8], group_index per view orientation[4], flags, variants)
    ((1, 0, 1, 0, 1, 0, 1, 0), (17, 17, 17, 17), 0, 1),
    ((1, 0, 1, 0, 1, 2, 0, 2), (13, 16, 15, 14), 0, 1),
    ((1, 1, 1, 1, 1, 2, 0, 2), (18, 21, 20, 19), 0, 1),
    ((1, 0, 1, 1, 1, 2, 0, 2), (26, 33, 32, 31), 0, 1),
    ((1, 1, 1, 0, 1, 2, 0, 2), (30, 29, 28, 27), 0, 1),
    ((0, 2, 1, 0, 1, 0, 1, 2), (14, 13, 16, 15), 0, 1),
    ((0, 2, 1, 1, 1, 1, 1, 2), (19, 18, 21, 20), 0, 1),
    ((0, 2, 1, 0, 1, 1, 1, 2), (31, 26, 33, 32), 0, 1),
    ((0, 2, 1, 1, 1, 0, 1, 2), (27, 30, 29, 28), 0, 1),
    ((1, 2, 0, 2, 1, 0, 1, 0), (15, 14, 13, 16), 0, 1),
    ((1, 2, 0, 2, 1, 1, 1, 1), (20, 19, 18, 21), 0, 1),
    ((1, 2, 0, 2, 1, 0, 1, 1), (32, 31, 26, 33), 0, 1),
    ((1, 2, 0, 2, 1, 1, 1, 0), (28, 27, 30, 29), 0, 1),
    ((1, 0, 1, 2, 0, 2, 1, 0), (16, 15, 14, 13), 0, 1),
    ((1, 1, 1, 2, 0, 2, 1, 1), (21, 20, 19, 18), 0, 1),
    ((1, 1, 1, 2, 0, 2, 1, 0), (33, 32, 31, 26), 0, 1),
    ((1, 0, 1, 2, 0, 2, 1, 1), (29, 28, 27, 30), 0, 1),
    ((1, 1, 1, 2, 0, 0, 0, 2), (22, 25, 24, 23), 0, 1),
    ((0, 2, 1, 1, 1, 2, 0, 0), (23, 22, 25, 24), 0, 1),
    ((0, 0, 0, 2, 1, 1, 1, 2), (24, 23, 22, 25), 0, 1),
    ((1, 2, 0, 0, 0, 2, 1, 1), (25, 24, 23, 22), 0, 1),
    ((1, 0, 1, 0, 1, 1, 1, 1), (34, 37, 36, 35), 0, 1),
    ((1, 1, 1, 0, 1, 0, 1, 1), (35, 34, 37, 36), 0, 1),
    ((1, 1, 1, 1, 1, 0, 1, 0), (36, 35, 34, 37), 0, 1),
    ((1, 0, 1, 1, 1, 1, 1, 0), (37, 36, 35, 34), 0, 1),
    ((1, 0, 1, 0, 1, 0, 1, 1), (38, 41, 40, 39), 0, 1),
    ((1, 1, 1, 0, 1, 0, 1, 0), (39, 38, 41, 40), 0, 1),
    ((1, 0, 1, 1, 1, 0, 1, 0), (40, 39, 38, 41), 0, 1),
    ((1, 0, 1, 0, 1, 1, 1, 0), (41, 40, 39, 38), 0, 1),
    ((1, 1, 1, 1, 1, 0, 1, 1), (42, 45, 44, 43), 0, 1),
    ((1, 1, 1, 1, 1, 1, 1, 0), (43, 42, 45, 44), 0, 1),
    ((1, 0, 1, 1, 1, 1, 1, 1), (44, 43, 42, 45), 0, 1),
    ((1, 1, 1, 0, 1, 1, 1, 1), (45, 44, 43, 42), 0, 1),
    ((1, 1, 1, 0, 1, 1, 1, 0), (46, 47, 46, 47), 0, 1),
    ((1, 0, 1, 1, 1, 0, 1, 1), (47, 46, 47, 46), 0, 1),
    ((1, 2, 1, 2, 0, 2, 0, 2), (4, 7, 6, 5), 0, 1),
    ((0, 2, 1, 2, 1, 2, 0, 2), (5, 4, 7, 6), 0, 1),
    ((0, 2, 0, 2, 1, 2, 1, 2), (6, 5, 4, 7), 0, 1),
    ((1, 2, 0, 2, 0, 2, 1, 2), (7, 6, 5, 4), 0, 1),
    ((1, 2, 0, 2, 1, 2, 0, 2), (0, 1, 0, 1), 0, 1),
    ((0, 2, 1, 2, 0, 2, 1, 2), (1, 0, 1, 0), 0, 1),
    ((1, 2, 0, 2, 0, 2, 0, 2), (8, 11, 10, 9), 0, 1),
    ((0, 2, 1, 2, 0, 2, 0, 2), (9, 8, 11, 10), 0, 1),
    ((0, 2, 0, 2, 1, 2, 0, 2), (10, 9, 8, 11), 0, 1),
    ((0, 2, 0, 2, 0, 2, 1, 2), (11, 10, 9, 8), 0, 1),
    ((0, 0, 0, 0, 0, 0, 0, 0), (12, 12, 12, 12), 0, 1),
    ((1, 1, 1, 1, 1, 1, 1, 1), (48, 48, 48, 48), 0, 1),
    ((2, 2, 2, 2, 2, 2, 2, 2), (12, 12, 12, 12), 0, 1),
]
T_ROAD_B = [  # exe 0x00637098, 17 records: (pattern[8], group_index per view orientation[4], flags, variants)
    ((1, 2, 1, 2, 1, 2, 1, 2), (17, 17, 17, 17), 0, 1),
    ((1, 2, 1, 2, 1, 2, 0, 2), (13, 16, 15, 14), 0, 1),
    ((0, 2, 1, 2, 1, 2, 1, 2), (14, 13, 16, 15), 0, 1),
    ((1, 2, 0, 2, 1, 2, 1, 2), (15, 14, 13, 16), 0, 1),
    ((1, 2, 1, 2, 0, 2, 1, 2), (16, 15, 14, 13), 0, 1),
    ((1, 2, 1, 2, 0, 2, 0, 2), (4, 7, 6, 5), 0, 1),
    ((0, 2, 1, 2, 1, 2, 0, 2), (5, 4, 7, 6), 0, 1),
    ((0, 2, 0, 2, 1, 2, 1, 2), (6, 5, 4, 7), 0, 1),
    ((1, 2, 0, 2, 0, 2, 1, 2), (7, 6, 5, 4), 0, 1),
    ((1, 2, 0, 2, 1, 2, 0, 2), (0, 1, 0, 1), 0, 1),
    ((0, 2, 1, 2, 0, 2, 1, 2), (1, 0, 1, 0), 0, 1),
    ((1, 2, 0, 2, 0, 2, 0, 2), (8, 11, 10, 9), 0, 1),
    ((0, 2, 1, 2, 0, 2, 0, 2), (9, 8, 11, 10), 0, 1),
    ((0, 2, 0, 2, 1, 2, 0, 2), (10, 9, 8, 11), 0, 1),
    ((0, 2, 0, 2, 0, 2, 1, 2), (11, 10, 9, 8), 0, 1),
    ((0, 2, 0, 2, 0, 2, 0, 2), (12, 12, 12, 12), 0, 1),
    ((2, 2, 2, 2, 2, 2, 2, 2), (12, 12, 12, 12), 0, 1),
]
GROUPS = {  # group id: (name, first n (0-based, atlas index = n+201), image count)
    1: ('SPR_SPACE', 0, 1),
    2: ('SPR_W_SHALLOW_2', 1281, 1),
    3: ('SPR_W_SHALLOW_1', 1280, 1),
    4: ('SPR_TREES', 978, 32),
    5: ('SPR_WATER', 163, 80),
    6: ('SPR_CRACKS', 243, 32),
    7: ('SPR_IN_FILL2', 275, 58),
    8: ('SPR_IMPASSABLE', 333, 14),
    9: ('SPR_MEADOW_GRASSY', 1142, 8),
    10: ('SPR_IN_FILL1', 105, 58),
    11: ('SPR_BUILD_CURSOR', 361, 1),
    12: ('SPR_STUMPS', 1074, 8),
    13: ('SPR_PRE_BUILD', 430, 6),
    14: ('SPR_STUMPS_SOME_GRASS', 1082, 8),
    15: ('SPR_THICK_GRASS_NOHAT', 49, 12),
    16: ('SPR_THICK_GRASS', 37, 12),
    17: ('SPR_SIGNPOSTS', 422, 8),
    18: ('SPR_BEACH', 650, 46),
    19: ('SPR_MEADOW_DESERT', 1134, 8),
    20: ('SPR_WATER_ANIMS', 560, 90),
    21: ('SPR_RUBBLE', 414, 8),
    22: ('SPR_ROCK_CLIFF', 376, 14),
    23: ('SPR_DES_HOUSE', 404, 10),
    24: ('SPR_DES_NOHOUSE', 394, 10),
    25: ('SPR_STUMPS_LOTS_GRASS', 1090, 8),
    26: ('SPR_MARSH', 771, 80),
    27: ('SPR_REED_GROWN', 763, 8),
    28: ('SPR_MEADOW_LIGHT_GRASS', 1150, 8),
    29: ('SPR_TREES_LOTS_GRASS', 1042, 32),
    30: ('SPR_TREES_SOME_GRASS', 1010, 32),
    31: ('SPR_ELEV_TILE', 1158, 1),
    32: ('SPR_ROCK_SILVER', 362, 14),
    33: ('SPR_ROADS', 696, 18),
    34: ('SPR_BEACH_ROAD', 542, 18),
    35: ('SPR_BEACH_COAST', 462, 80),
    36: ('SPR_GRASS', 1, 36),
    37: ('SPR_MEADOW', 1098, 36),
    38: ('SPR_THICK_GRASS_RIM', 61, 44),
    39: ('SPR_PAVED_ROADS', 714, 49),
    40: ('SPR_ROCK_COPPER', 347, 14),
    41: ('SPR_GRIDS', 390, 4),
    42: ('SPR_LAVA', 900, 78),
    43: ('SPR_RUTTED_ROAD', 851, 49),
    44: ('SPR_TRANSITION_STEPS', 1282, 12),
    45: ('SPR_E2_E_ALT', 1294, 1),
    46: ('SPR_E2_E_ALT2', 1295, 1),
    47: ('SPR_E2_E_ALT3', 1296, 1),
    48: ('SPR_E2_S_ALT', 1297, 1),
    49: ('SPR_E2_S_ALT2', 1298, 1),
    50: ('SPR_E2_S_ALT3', 1299, 1),
    51: ('SPR_E2_W_ALT', 1328, 1),
    52: ('SPR_E2_N_ALT', 1329, 1),
    53: ('SPR_E2_E_ALT4A', 1300, 1),
    54: ('SPR_E2_E_ALT4B', 1301, 1),
    55: ('SPR_E2_S_ALT4A', 1302, 1),
    56: ('SPR_E2_S_ALT4B', 1303, 1),
    57: ('SPR_E2_NW_ALT', 1304, 1),
    58: ('SPR_E2_NE_ALT', 1305, 1),
    59: ('SPR_E2_SE_ALT', 1306, 1),
    60: ('SPR_E2_SW_ALT', 1307, 1),
    61: ('SPR_E1_E_ALT', 1308, 1),
    62: ('SPR_E1_E_ALT2', 1309, 1),
    63: ('SPR_E1_E_ALT3', 1310, 1),
    64: ('SPR_E1_S_ALT', 1311, 1),
    65: ('SPR_E1_S_ALT2', 1312, 1),
    66: ('SPR_E1_S_ALT3', 1313, 1),
    67: ('SPR_E1_E_ALT4A', 1314, 1),
    68: ('SPR_E1_E_ALT4B', 1315, 1),
    69: ('SPR_E1_S_ALT4A', 1316, 1),
    70: ('SPR_E1_S_ALT4B', 1317, 1),
    71: ('SPR_E1_W_ALT', 1318, 1),
    72: ('SPR_E1_N_ALT', 1319, 1),
    73: ('SPR_E1_NW_ALT', 1320, 1),
    74: ('SPR_E1_NE_ALT', 1321, 1),
    75: ('SPR_E1_SE_ALT', 1322, 1),
    76: ('SPR_E1_SW_ALT', 1323, 1),
    77: ('SPR_TW1_1_H2', 1273, 1),
    78: ('SPR_TW1_H_12', 1271, 1),
    79: ('SPR_TS1_H_12', 1269, 1),
    80: ('SPR_TS1_1_H2', 1267, 1),
    81: ('SPR_TE1_1_H2', 1265, 1),
    82: ('SPR_TE1_H_12', 1263, 1),
    83: ('SPR_EH_NW_ALT', 1324, 1),
    84: ('SPR_EH_NE_ALT', 1325, 1),
    85: ('SPR_EH_SE_ALT', 1326, 1),
    86: ('SPR_EH_SW_ALT', 1327, 1),
    87: ('SPR_E2_N', 1159, 1),
    88: ('SPR_E2_NE', 1160, 1),
    89: ('SPR_E2_E', 1161, 1),
    90: ('SPR_E2_SE', 1162, 1),
    91: ('SPR_E2_S', 1163, 1),
    92: ('SPR_E2_SW', 1164, 1),
    93: ('SPR_E2_W', 1165, 1),
    94: ('SPR_E2_E_S', 1166, 1),
    95: ('SPR_E2_S_W', 1167, 1),
    96: ('SPR_E2_W_N', 1168, 1),
    97: ('SPR_E2_N_E', 1169, 1),
    98: ('SPR_TN_1_2', 1170, 1),
    99: ('SPR_TN_2_1', 1171, 1),
    100: ('SPR_TE_1_2', 1172, 1),
    101: ('SPR_TE_2_1', 1173, 1),
    102: ('SPR_TS_1_2', 1174, 1),
    103: ('SPR_TS_2_1', 1175, 1),
    104: ('SPR_TW_1_2', 1176, 1),
    105: ('SPR_TW_2_1', 1177, 1),
    106: ('SPR_E1_NW', 1178, 1),
    107: ('SPR_E1_N', 1179, 1),
    108: ('SPR_E1_NE', 1180, 1),
    109: ('SPR_E1_E', 1181, 1),
    110: ('SPR_E1_SE', 1182, 1),
    111: ('SPR_E1_S', 1183, 1),
    112: ('SPR_E1_SW', 1184, 1),
    113: ('SPR_E1_W', 1185, 1),
    114: ('SPR_E1_E_S', 1186, 1),
    115: ('SPR_E1_S_W', 1187, 1),
    116: ('SPR_E1_W_N', 1188, 1),
    117: ('SPR_E1_N_E', 1189, 1),
    118: ('SPR_E1_NPASS', 1190, 1),
    119: ('SPR_E1_EPASS', 1191, 1),
    120: ('SPR_E1_SPASS', 1192, 1),
    121: ('SPR_E1_WPASS', 1193, 1),
    122: ('SPR_E1_NROAD1', 1194, 1),
    123: ('SPR_E1_EROAD1', 1195, 1),
    124: ('SPR_E1_SROAD1', 1196, 1),
    125: ('SPR_E1_WROAD1', 1197, 1),
    126: ('SPR_E1_NROAD2', 1198, 1),
    127: ('SPR_E1_EROAD2', 1199, 1),
    128: ('SPR_E1_SROAD2', 1200, 1),
    129: ('SPR_E1_WROAD2', 1201, 1),
    130: ('SPR_TN_H_1', 1202, 1),
    131: ('SPR_TE_H_1', 1204, 1),
    132: ('SPR_TS_1_H', 1206, 1),
    133: ('SPR_TW_H_1', 1208, 1),
    134: ('SPR_TN_1_H', 1203, 1),
    135: ('SPR_TE_1_H', 1205, 1),
    136: ('SPR_TS_H_1', 1207, 1),
    137: ('SPR_TW_1_H', 1209, 1),
    138: ('SPR_EH_NW', 1210, 1),
    139: ('SPR_EH_N', 1211, 1),
    140: ('SPR_EH_NE', 1212, 1),
    141: ('SPR_EH_E', 1213, 1),
    142: ('SPR_EH_SE', 1214, 1),
    143: ('SPR_EH_S', 1215, 1),
    144: ('SPR_EH_SW', 1216, 1),
    145: ('SPR_EH_W', 1217, 1),
    146: ('SPR_EH_E_S', 1218, 1),
    147: ('SPR_EH_S_W', 1219, 1),
    148: ('SPR_EH_W_N', 1220, 1),
    149: ('SPR_EH_N_E', 1221, 1),
    150: ('SPR_EH_NPASS', 1222, 1),
    151: ('SPR_EH_EPASS', 1223, 1),
    152: ('SPR_EH_SPASS', 1224, 1),
    153: ('SPR_EH_WPASS', 1225, 1),
    154: ('SPR_EH_NNORM', 1226, 1),
    155: ('SPR_EH_ENORM', 1228, 1),
    156: ('SPR_EH_SNORM', 1230, 1),
    157: ('SPR_EH_WNORM', 1232, 1),
    158: ('SPR_EH_NPASS1', 1234, 1),
    159: ('SPR_EH_EPASS1', 1236, 1),
    160: ('SPR_EH_SPASS1', 1238, 1),
    161: ('SPR_EH_WPASS1', 1240, 1),
    162: ('SPR_EH_NROAD1', 1242, 1),
    163: ('SPR_EH_EROAD1', 1244, 1),
    164: ('SPR_EH_SROAD1', 1246, 1),
    165: ('SPR_EH_WROAD1', 1248, 1),
    166: ('SPR_EH_NROAD2', 1250, 1),
    167: ('SPR_EH_EROAD2', 1252, 1),
    168: ('SPR_EH_SROAD2', 1254, 1),
    169: ('SPR_EH_WROAD2', 1256, 1),
    170: ('SPR_TN1_H_1', 1258, 1),
    171: ('SPR_TN1_1_H', 1260, 1),
    172: ('SPR_TE1_H_1', 1262, 1),
    173: ('SPR_TE1_1_H', 1264, 1),
    174: ('SPR_TS1_1_H', 1266, 1),
    175: ('SPR_TS1_H_1', 1268, 1),
    176: ('SPR_TW1_H_1', 1270, 1),
    177: ('SPR_TW1_1_H', 1272, 1),
    178: ('SPR_EH_ENORM2', 1229, 1),
    179: ('SPR_EH_NNORM2', 1227, 1),
    180: ('SPR_EH_SNORM2', 1231, 1),
    181: ('SPR_EH_WNORM2', 1233, 1),
    182: ('SPR_EH_NPASS2', 1235, 1),
    183: ('SPR_EH_EPASS2', 1237, 1),
    184: ('SPR_EH_SPASS2', 1239, 1),
    185: ('SPR_EH_WPASS2', 1241, 1),
    186: ('SPR_EH_NROAD12', 1243, 1),
    187: ('SPR_EH_EROAD12', 1245, 1),
    188: ('SPR_EH_SROAD12', 1247, 1),
    189: ('SPR_EH_WROAD12', 1249, 1),
    190: ('SPR_EH_NROAD22', 1251, 1),
    191: ('SPR_EH_EROAD22', 1253, 1),
    192: ('SPR_EH_SROAD22', 1255, 1),
    193: ('SPR_EH_WROAD22', 1257, 1),
    194: ('SPR_TN1_H_12', 1259, 1),
    195: ('SPR_TN1_1_H2', 1261, 1),
    196: ('SPR_S_SHALLOW_1', 1278, 1),
    197: ('SPR_S_SHALLOW_2', 1279, 1),
    198: ('SPR_E_SHALLOW_2', 1277, 1),
    199: ('SPR_E_SHALLOW_1', 1276, 1),
    200: ('SPR_N_SHALLOW_2', 1275, 1),
    201: ('SPR_N_SHALLOW_1', 1274, 1),
    202: ('SPR_ELITE_OVERLAY', 456, 6),
    203: ('SPR_QUARRY_DEEP', 1424, 60),
    204: ('SPR_QUARRY_SHALLOW', 1364, 60),
    205: ('SPR_QUARRY', 1330, 34),
    206: ('SPR_FOOT_PRINT2_NW', 448, 8),
    207: ('SPR_FOOT_PRINT1_NW', 438, 8),
    208: ('SPR_FOOT_PRINT2', 446, 2),
    209: ('SPR_FOOT_PRINT1', 436, 2),
    210: ('SPR_EH_N_ALT1', 1484, 1),
    211: ('SPR_EH_N_ALT2', 1488, 1),
    212: ('SPR_EH_N_ALT3', 1492, 1),
    213: ('SPR_EH_E_ALT1', 1485, 1),
    214: ('SPR_EH_E_ALT2', 1489, 1),
    215: ('SPR_EH_E_ALT3', 1493, 1),
    216: ('SPR_EH_S_ALT1', 1486, 1),
    217: ('SPR_EH_S_ALT2', 1490, 1),
    218: ('SPR_EH_S_ALT3', 1494, 1),
    219: ('SPR_EH_W_ALT1', 1487, 1),
    220: ('SPR_EH_W_ALT2', 1491, 1),
    221: ('SPR_EH_W_ALT3', 1495, 1),
}

OFFMAP = 0x80000
N8 = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))   # N NE E SE S SW W NW

# terrain flag bits
TREE, ROCK, WATER, BUILDING, ROAD, GARDEN, SCRUB, CLIFF, MEADOW, RUBBLE = 1, 2, 4, 8, 0x40, 0x20, 0x80, 0x200, 0x800, 0x1000
BEACH, MARBLE, MARSH, DEEP, SPECIAL = 0x10000, 0x20000, 0x40000, 0x4000000, 0x10000000
SKIP_TILE = 0x8C008            # offmap | 0x8000 | wall | building: tile is left alone
PLAIN_MASK = 0x2CFED66F        # plain_ground requires none of these
BUSY_MASK = 0x2DFED66F         # 'something on the neighbour' test of the scrub tiles / 3x3 rock test


def _g(name):
    for gid, (n, f, c) in GROUPS.items():
        if n == name:
            return gid
    raise KeyError(name)


G_SPACE, G_TREES, G_STUMPS, G_STUMPS_SG, G_STUMPS_LG = 1, 4, 12, 14, 25
G_GRASS, G_THICK, G_NOHAT, G_RIM, G_FILL1, G_FILL2 = 36, 16, 15, 38, 10, 7
G_WATER, G_COAST, G_ANIMS, G_BEACH, G_CRACKS, G_RUBBLE = 5, 35, 20, 18, 6, 21
G_LAVA = 42
G_MARSH, G_REED, G_QUARRY, G_QSHALLOW, G_QDEEP = 26, 27, 205, 204, 203
BM_COL, BM_FIRST = 52 * 0x4000, (509, 543, 603)   # Poseidon_Loaded SPR_BM_QUARRY / BM_SHALLOW / BM_QUARRY_DEEP (n, 0-based)
G_MEADOW, G_MDESERT, G_MGRASSY, G_MLIGHT = 37, 19, 9, 28
G_IMPASS, G_COPPER, G_SILVER, G_ROCKCLIFF = 8, 40, 32, 22
G_ROADS, G_PAVED, G_RUTTED = 33, 39, 43


def first(gid):
    return GROUPS[gid][1]


def norm_ids(ids):
    """v247 map ids (collection 3 = Poseidon_Unloaded) -> current numbering (+2 for collections >= 2)."""
    ids = np.asarray(ids, np.int64)
    c = ids >> 14
    return np.where(c >= 2, ids + (2 << 14), ids).astype(np.uint32)


def _lookup(table, arr, rand, from_end=False):
    """Pattern-table search (FUN_004A6920).  arr[i] True = bit i, False = bit i+8; record pattern 1 needs
    True, 0 needs False, 2 ignores.  Returns (k, variant) or None.  variant = rand % count (rand >= 0)."""
    global _LAST_KS
    recs = reversed(table) if from_end else table
    for pat, ks, fl, cnt in recs:
        for p, a in zip(pat, arr):
            if p != 2 and (p == 1) != a:
                break
        else:
            _LAST_KS = ks
            return ks[0], (rand % cnt if cnt else 0)
    _LAST_KS = None
    return None


# The record's picture index per view orientation (column view/2): the last successful lookup's ks, read by
# the next image write of that tile (_Terrain._alt). Ids are computed for view 0; other views differ by
# ks[v] - ks[0] (docs/play/rotation.md "Terrain").
_LAST_KS = None
EDITOR = False      # True: earthquake fault tiles (0x2000000) drawn as cracks, as the editor stores them in the map


class _Terrain:
    def __init__(self, flags, rand, scrub, meadow, regrowth, piece, orig, rect, desirability, lava=None):
        self.f = [list(map(int, r)) for r in np.asarray(flags, np.uint32)]
        self.lava = lava or set()            # tiles with a lava node (the grid 0x00799168)
        self.lava_edge = {}                  # (x, y) -> T_LAVA ks (per view orientation): the tinted overlay
        self.rn = np.asarray(rand, np.uint8).tolist()
        self.sc = np.asarray(scrub, np.uint8).tolist()
        self.me = np.asarray(meadow, np.uint8).tolist()
        self.rg = np.asarray(regrowth, np.uint8).tolist()
        self.pc = np.asarray(piece, np.uint8).tolist()
        self.de = None if desirability is None else np.asarray(desirability, np.int8).tolist()
        self.id = [[0] * N for _ in range(N)]
        self.dr = [[0] * N for _ in range(N)]
        self.orig = orig
        self.alt = {}                       # (x, y) -> id deltas in views 2, 4, 6 (pattern-table tiles only)
        if orig is not None:
            self.id = [list(map(int, r)) for r in orig]
        if rect is None:
            rect = (0, 0, N - 1, N - 1)
        self.rect = rect

    # ---- accessors -------------------------------------------------------------------------
    def F(self, x, y):
        if 0 <= x < N and 0 <= y < N:
            return self.f[y][x]
        return OFFMAP

    def nb(self, x, y, mask):
        return [bool(self.F(x + dx, y + dy) & mask) for dx, dy in N8]

    def _alt(self, x, y):
        global _LAST_KS
        ks = _LAST_KS
        if ks and (ks[1] != ks[0] or ks[2] != ks[0] or ks[3] != ks[0]):
            self.alt[(x, y)] = (ks[1] - ks[0], ks[2] - ks[0], ks[3] - ks[0])
        else:
            self.alt.pop((x, y), None)

    def put(self, x, y, gid, k):
        self._alt(x, y)
        self.id[y][x] = COL + first(gid) + k
        self.pc[y][x] &= 0xF0
        self.dr[y][x] |= 0x40

    # ---- footprint helpers -------------------------------------------------------------------
    def near_edge(self, x, y, d=3):
        return any(self.F(x + a, y + b) & OFFMAP for a, b in ((d, 0), (-d, 0), (0, d), (0, -d)))

    def area_ok_plain(self, x, y, w, h):
        """map_area_buildable(x,y,w,h,mask=-1,image=1,allow_beach=0,ignore_walkers=1,strict=1) 0x004A0DC0."""
        if x < 3 or y < 3 or x + w - 1 >= N - 3 or y + h - 1 >= N - 3:
            return False
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if self.near_edge(xx, yy):
                    return False
                if self.f[yy][xx] & 0x3DFFDEEF or self.id[yy][xx] != 0:
                    return False
        return True

    def area_same(self, x, y, w, h, kind):
        """FUN_004A0FD0: every tile has (flags & 0x2DFED66F) == kind and no image yet."""
        if x + w > N or y + h > N:
            return False
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if (self.f[yy][xx] & BUSY_MASK) != kind or self.id[yy][xx] != 0:
                    return False
        return True

    def stamp_seq(self, x, y, w, h, gid, k0):
        """FUN_004A0680: consecutive images over the footprint (row-major), every tile drawn."""
        k = k0
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self._alt(xx, yy)
                self.f[yy][xx] &= 0x93872F90
                self.id[yy][xx] = COL + first(gid) + k
                self.pc[yy][xx] &= 0xF0
                self.dr[yy][xx] |= 0x40
                k += 1

    def stamp_block(self, x, y, w, h, gid, k, flags_or):
        """building_footprint_place 0x004A04B0: one image for the whole block, anchor = bottom-left tile."""
        for r in range(h):
            for c in range(w):
                yy, xx = y + r, x + c
                self._alt(xx, yy)
                self.f[yy][xx] = (self.f[yy][xx] & 0x93872F90) | flags_or
                self.id[yy][xx] = COL + first(gid) + k
                self.pc[yy][xx] = (self.pc[yy][xx] & 0xE0) | (w - 1)
                self.dr[yy][xx] = r * 8 + c + (0x40 if (c == 0 and r == h - 1) else 0)

    # ---- tile classes ------------------------------------------------------------------------
    def water(self, x, y):                                      # FUN_00520CA0
        f, r = self.f[y][x], self.rn[y][x]
        arr = [not (v & WATER) for v in (self.F(x + dx, y + dy) for dx, dy in N8)]
        res = _lookup(T_WATER, arr, r) or (0, 0)
        k, var = res
        beach_nb = any(self.F(x + dx, y + dy) & BEACH for dx, dy in N8)
        if f & BEACH:
            if k >= 8:
                return self.put(x, y, G_COAST, var + k)
        elif beach_nb:
            return self.put(x, y, G_COAST, var + k)          # (beach-road variants need quay objects: not ported)
        if not f & DEEP:
            if k == 0:
                return self.put(x, y, G_COAST, var)
            return self.put(x, y, G_WATER, var + k)
        arr = [not (self.F(x + dx, y + dy) & DEEP) for dx, dy in N8]
        k, var = _lookup(T_EDGE, arr, r, from_end=True) or (0, 0)
        return self.put(x, y, G_ANIMS, var * 15 + k)

    def tree(self, x, y):                                       # terrain_resource_image 0x004A81F0
        s = min(self.sc[y][x], 100)
        lvl = s // 34
        r = self.rn[y][x]
        if self.rg[y][x] != 255:
            return self.put(x, y, (G_STUMPS, G_STUMPS_SG, G_STUMPS_LG)[min(lvl, 2)], r & 7)
        ring = 0
        for rr in (3, 2, 1):
            if self.ring_full(x, y, rr):
                ring = rr
                break
        self.put(x, y, G_TREES, lvl * 32 + ring * 8 + (r & 7))

    def ring_full(self, x, y, rr):                              # trees_ring_full 0x004A4840
        for dy in range(-rr, rr + 1):
            for dx in range(-rr, rr + 1):
                if max(abs(dx), abs(dy)) != rr:
                    continue
                if not (0 <= x + dx < N and 0 <= y + dy < N):
                    continue                                     # ring_tile_off_map: outside the array only
                v = self.f[y + dy][x + dx]
                if not (v & TREE) and not (v & 0x300002):
                    return False
        return True

    def meadow(self, x, y):                                     # terrain_resource_image, meadow branch
        m, rg = self.me[y][x], self.rg[y][x]
        s = min(self.sc[y][x], 100)
        e1 = int((m - 1) * 0.010101010101010102 * rg * 0.011764705882352941)
        e2 = int((s - 1) / 96.0 * 12.0)
        r = self.rn[y][x]
        gid, k, base = G_MEADOW, e2, e1 * 12
        if e1 == 0:
            if e2 == 0:
                gid, k, base = G_MLIGHT, r & 7, 0
        elif e1 == 2:
            if e2 == 0:
                gid, k, base = G_MDESERT, r & 7, 0
            elif e2 == 11:
                gid, k, base = G_MGRASSY, r & 7, 0
        self.put(x, y, gid, k + base)

    def marsh(self, x, y):                                      # FUN_00521150 + reeds
        r = self.rn[y][x]
        arr = [not (v & MARSH) for v in (self.F(x + dx, y + dy) for dx, dy in N8)]
        k, var = _lookup(T_WATER, arr, r) or (0, 0)
        self.put(x, y, G_MARSH, var + k)
        if sum(1 for dx, dy in N8 if self.F(x + dx, y + dy) & MARSH) == 8:
            self.put(x, y, G_MARSH if self.rg[y][x] != 255 else G_REED, r & 7)

    def beach(self, x, y):                                      # FUN_00520B80 (no quay objects)
        self.put(x, y, G_BEACH, self.rn[y][x] % 6)

    def rubble(self, x, y):
        self.put(x, y, G_RUBBLE, self.rn[y][x] & 7)

    def rock(self, x, y):                                       # FUN_00520580
        f, r = self.f[y][x], self.rn[y][x]
        if self.pc[y][x] & 0x80:                                # cracks (desirability source rocks)
            arr = [bool(self.F(x + dx, y + dy) & ROCK and self.pc_at(x + dx, y + dy) & 0x80) for dx, dy in N8]
            res = _lookup(T_CRACKS, arr, r)
            self.put(x, y, G_CRACKS, (res[0] + res[1]) if res else 0)
            return True
        kind = f & 0x300002
        gid = {0x100002: G_COPPER, 0x200002: G_SILVER, 0x300002: G_ROCKCLIFF}.get(kind, G_IMPASS)
        if kind == 0x300000:
            return False                                         # orichalc: other collection, not ported
        if self.area_same(x, y, 3, 3, kind):
            self.stamp_block(x, y, 3, 3, gid, 12 + (r & 1), kind)
        elif self.area_same(x, y, 2, 2, kind):
            self.stamp_block(x, y, 2, 2, gid, 8 + (r & 3), kind)
        else:
            self.put(x, y, gid, r & 7)
        return True

    def fault(self, x, y):                                      # earthquake fault tiles: cracks, 0x0049E8A0-ish painter
        arr = self.nb(x, y, 0x2000000)
        res = _lookup(T_CRACKS, arr, self.rn[y][x])
        self.put(x, y, G_CRACKS, (res[0] + res[1]) if res else 0)

    def lava_tile(self, x, y):                                  # FUN_00520820 (a lava node's tile)
        """The T_LAVA record on the inverted lava bits (FUN_004A1FF0(0x1000000), FUN_004A6C60). Index 0 (lava all
        round): the tile's picture SPR_LAVA + rand % 6, done. Else the record's index goes to the node (+0x24) and the
        tile takes the next painters' ground (FUN_00507980 draws SPR_LAVA + index over it, tinted)."""
        arr = [not v for v in self.nb(x, y, 0x1000000)]
        res = _lookup(T_LAVA, arr, self.rn[y][x])
        self.lava_edge.pop((x, y), None)
        if res is None:
            return False
        if res[0] == 0:
            self.put(x, y, G_LAVA, res[1])
            return True
        self.lava_edge[(x, y)] = _LAST_KS
        return False

    def pc_at(self, x, y):
        return self.pc[y][x] if 0 <= x < N and 0 <= y < N else 0

    def marble(self, x, y):                                     # FUN_00520920 (play mode)
        """Untouched marble: SPR_QUARRY by T_MARBLE (neighbour not marble of the same kind). An interior
        tile (T_MARBLE k = 0) with regrowth != 255 is a pit (regrowth = quarry depth, docs/logic/map-terrain.md
        5b): SPR_QUARRY_SHALLOW by T_PIT on "neighbour regrowth > 100"; regrowth < 100 and that k = 0 too:
        SPR_QUARRY_DEEP by T_PIT on "neighbour regrowth > 0". Black marble: the Poseidon_Loaded groups."""
        r = self.rn[y][x]
        black = (self.f[y][x] & 0x120000) == 0x120000
        want = 0x120000 if black else 0x20000
        arr = [not ((self.F(x + dx, y + dy) & 0x120000) == want) for dx, dy in N8]
        res = _lookup(T_MARBLE, arr, r)
        stage, k = 0, (res[0] + res[1]) if res else 0
        g = self.rg[y][x]
        if (res is None or res[0] == 0) and g != 255:
            arr = [not (self.R(x + dx, y + dy) <= 100) for dx, dy in N8]
            res = _lookup(T_PIT, arr, r)
            stage, k = 1, (res[0] + res[1]) if res else 0
            if g < 100 and (res is None or res[0] == 0):
                arr = [not (self.R(x + dx, y + dy) <= 0) for dx, dy in N8]
                res = _lookup(T_PIT, arr, r)
                stage, k = 2, (res[0] + res[1]) if res else 0
        if black:                                               # image ids 0x6830/1/2: collection 52
            self.id[y][x] = BM_COL + BM_FIRST[stage] + k
            self.pc[y][x] &= 0xF0
            self.dr[y][x] |= 0x40
        else:
            self.put(x, y, (G_QUARRY, G_QSHALLOW, G_QDEEP)[stage], k)

    def R(self, x, y):
        return self.rg[y][x] if 0 <= x < N and 0 <= y < N else 255

    def grass(self, x, y):                                      # FUN_0051F860 (scrub tiles)
        f = self.f[y][x]
        s = min(self.sc[y][x], 100)
        if any(self.F(x + dx, y + dy) & BEACH for dx, dy in N8):
            arr = self.nb(x, y, BEACH)
            res = _lookup(T_EDGE, arr, -1)
            return self.put(x, y, G_BEACH, (res[0] if res else 0) + 6)
        g = int(s * 0.125)
        if g < 11:
            return self.put(x, y, G_GRASS, g)

        def busy(xx, yy):
            return any(self.F(xx + dx, yy + dy) & BUSY_MASK for dx, dy in N8)
        if not f & SPECIAL and busy(x, y):
            return self.put(x, y, G_THICK, 0)
        for dx, dy in N8:
            xx, yy = x + dx, y + dy
            if not (0 <= xx < N and 0 <= yy < N):
                return self.put(x, y, G_RIM, 0)
            fn = self.f[yy][xx]
            gn = int(min(self.sc[yy][xx], 100) * 0.125)
            if gn != 11 or fn & 0x10801 or (not fn & SPECIAL and busy(xx, yy)):
                return self.put(x, y, G_RIM, 0)
        return self.put(x, y, G_NOHAT, 0)

    def plain(self, x, y):                                      # map_tile_plain_ground 0x0051FBA0
        if self.f[y][x] & PLAIN_MASK:
            return False
        r = self.rn[y][x]
        gid = G_FILL2 if self.pc[y][x] & 0x20 else G_FILL1
        if r & 0xF0:
            self.stamp_seq(x, y, 1, 1, gid, r & 7)
        elif self.area_ok_plain(x, y, 4, 4):
            self.stamp_seq(x, y, 4, 4, gid, 42)
        elif self.area_ok_plain(x, y, 3, 3):
            self.stamp_seq(x, y, 3, 3, gid, 24 + (r & 1) * 9)
        elif self.area_ok_plain(x, y, 2, 2):
            self.stamp_seq(x, y, 2, 2, gid, 8 + (r & 3) * 4)
        else:
            self.stamp_seq(x, y, 1, 1, gid, r & 7)
        return True

    def road(self, x, y):                                       # FUN_004A0190, simplified (no quays / ramps)
        if self.de is None or self.F(x, y) & BEACH:
            return False
        d = self.de[y][x]
        tier = 0 if d < 0 else (1 if d < 16 else (2 if d < 30 else 3))
        if tier == 3:
            return False                                         # General collection road (group 47), not ported
        arr = self.nb(x, y, 0x8000040)
        if tier == 1:
            res = _lookup(T_ROAD_B, arr, -1)
            gid = G_ROADS
        else:
            res = _lookup(T_ROAD_A, arr, -1)
            gid = G_PAVED if tier == 2 else G_RUTTED
        self.put(x, y, gid, res[0] if res else 0)
        return True

    # ---- driver (map_tiles_update_images 0x0051F450, second pass) ----------------------------------
    def run(self):
        x0, y0, x1, y1 = self.rect
        for y in range(y0, y1 + 1):                              # first pass: clear
            for x in range(x0, x1 + 1):
                f = self.f[y][x]
                if not f & SKIP_TILE and not f & CLIFF:
                    self.id[y][x] = 0
                    self.dr[y][x] = 0 if self.orig is None else self.dr[y][x]
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                f = self.f[y][x]
                # 0x10000000 (monument extras): the exe computes the ground unless the step rule FUN_00546380 gives
                # a step image (then the tile keeps its image; play mode draws the step over it, monuments.js
                # stepSprite). Ours computes it always: the step picture covers it (bugs.md 399: skipped tiles were
                # left without a picture, black, where no step image applies)
                if f & SKIP_TILE or self.id[y][x] != 0:
                    continue
                self.tile(x, y, f)

    def tile(self, x, y, f):
        global _LAST_KS
        _LAST_KS = None
        if f & WATER:
            return self.water(x, y)
        if f & TREE:
            if f & 0xC064 == 0:
                return self.tree(x, y)
            return
        if f & 0x300002 and not f & MARBLE and self.rock(x, y):
            return
        if f & MARBLE:
            return self.marble(x, y)
        if f & 0x1000000 and (x, y) in self.lava and self.lava_tile(x, y):
            return
        if f & RUBBLE:
            return self.rubble(x, y)
        if f & ROAD:
            self.road(x, y)
            return
        if f & 0x2000000 and EDITOR:                             # play: a fault tile is drawn as the land it is
            return self.fault(x, y)                              # (oracle 1L5-quake m093: no cracks before the quake)
        if f & BEACH and not f & 0x48:
            return self.beach(x, y)
        if f & MARSH:
            return self.marsh(x, y)
        if f & GARDEN:
            return                                               # gardens (group in General collection): not ported
        if f & MEADOW:
            return self.meadow(x, y)
        if f & SCRUB and not f & 0x10801:
            return self.grass(x, y)
        self.plain(x, y)


def images_full(flags, elev=None, rand=None, orig_ids=None, scrub=None, meadow=None, regrowth=None,
                piece=None, desirability=None, rect=None, alt=None, lava=None, lava_edge=None):
    """Compute (ids, draw, piece) for the whole map or for rect=(x0, y0, x1, y1) (inclusive).

    flags       u32[228][228] terrain flags (rank 6 of a .map / sim World.flags)
    elev        u8[228][228] elevation (rank 23); unused for non-cliff tiles (cliffs keep orig_ids)
    rand        u8[228][228] random grid (rank 8)
    orig_ids    optional ids of the .map (rank 4; v247 numbering is converted): kept for cliff/special tiles
                and, with rect, for tiles outside the rectangle
    scrub       u8 grid (rank 22): scrub depth*8 (0..100);  meadow: rank 15;  regrowth: rank 19 (255 = grown)
    piece       u8 grid (rank 7): bit 0x20 selects IN_FILL2 land, 0x80 rock cracks
    desirability i8 grid, only for roads
    alt         optional dict, filled with {(x, y): (d2, d4, d6)}: the id deltas of views 2, 4, 6 for the tiles whose
                picture comes from a pattern table (column view/2 of FUN_004A6920; docs/play/rotation.md)
    lava        optional set of (x, y): the tiles of lava nodes (the exe's grid 0x00799168); lava_edge: optional dict,
                filled with {(x, y): ks} for the lava tiles drawn as ground + SPR_LAVA ks[view/2] overlay
    Returns ids (u32, collection 5), draw (u8, rank-5 like: 0x40 = draw here, low bits = r*8+c inside a block),
    piece (u8).  Tiles that are not computed (cliffs, lava, gardens, offmap) keep orig_ids or 0.
    """
    z = np.zeros((N, N), np.uint8)
    flags = np.asarray(flags, np.uint32)
    rand = z if rand is None else rand
    scrub = z if scrub is None else scrub
    meadow = z if meadow is None else meadow
    regrowth = np.full((N, N), 255, np.uint8) if regrowth is None else regrowth
    piece = z if piece is None else piece
    orig = None if orig_ids is None else norm_ids(orig_ids)
    t = _Terrain(flags, rand, scrub, meadow, regrowth, piece, orig, rect, desirability, lava)
    t.run()
    if lava_edge is not None:
        lava_edge.update(t.lava_edge)
    if alt is not None:                     # out: {(x, y): (d2, d4, d6)} id deltas of the other views
        alt.update(t.alt)
    return (np.array(t.id, np.uint32), np.array(t.dr, np.uint8), np.array(t.pc, np.uint8))


def images(flags, elev=None, rand=None, orig_ids=None, **kw):
    """Image id grid only (see images_full for the arguments)."""
    return images_full(flags, elev, rand, orig_ids, **kw)[0]


def expand_rect(flags, rect, draw=None):
    """FUN_0051F210 (map_tiles_update_images mode 2): grow the rect (x0, y0, x1, y1 inclusive) one row/column at a
    time while the line just outside it holds a tile with flags & 0x300022 (rock, ore, marble, garden), or a
    cliff tile whose draw byte is 1 / has 0x800000, so multi-tile blocks are never cut.  Use it on the footprint
    (+1 on the right/bottom, as the original passes x+w, y+h) before calling images(..., rect=...)."""
    f = np.asarray(flags, np.uint32)
    d = None if draw is None else np.asarray(draw, np.uint8)
    x0, y0, x1, y1 = rect

    def hit(xs, ys):
        for y in ys:
            for x in xs:
                v = int(f[y, x])
                if v & OFFMAP:
                    continue
                if v & 0x300022 or (v & CLIFF and ((d is not None and d[y, x] == 1) or v & 0x800000)):
                    return True
        return False
    changed = True
    while changed:
        changed = False
        if y0 > 0 and hit(range(x0, x1 + 1), [y0 - 1]):
            y0 -= 1; changed = True
        if y1 < N - 1 and hit(range(x0, x1 + 1), [y1 + 1]):
            y1 += 1; changed = True
        if x0 > 0 and hit([x0 - 1], range(y0, y1 + 1)):
            x0 -= 1; changed = True
        if x1 < N - 1 and hit([x1 + 1], range(y0, y1 + 1)):
            x1 += 1; changed = True
    return (x0, y0, x1, y1)


def animate_water(ids, flags, draw=None):
    """One water animation step (ground_tile_draw 0x00457900, every >60 ms of wall clock): single-tile water
    tiles whose image is a shallow-interior frame (SPR_BEACH_COAST 0..5) advance by 1 and wrap after 6; deep
    tiles (flag 0x4000000, SPR_WATER_ANIMS) advance by 15 and wrap after 90 (6 frames x 15 shapes).
    Returns a new id grid; the original also stores the new frame in the grid."""
    ids = np.array(ids, np.uint32)
    flags = np.asarray(flags, np.uint32)
    cf, af = COL + first(G_COAST), COL + first(G_ANIMS)
    shallow = (flags & WATER > 0) & (flags & DEEP == 0) & (ids >= cf) & (ids <= cf + 5)
    deep = (flags & WATER > 0) & (flags & DEEP > 0) & (ids >= af) & (ids <= af + 89)
    if draw is not None:
        single = (np.asarray(draw, np.uint8) & 0x0F) == 0
        shallow &= single
        deep &= single
    ids[shallow] = cf + (ids[shallow] - cf + 1) % 6
    ids[deep] = af + (ids[deep] - af + 15) % 90
    return ids


def _selfcheck(map_path=None):
    """Compare images() with the sandbox map's own rank-4 grid.  python3 tools/terrain_images.py"""
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import mapfile
    path = map_path or os.path.join(here, "..", "zeus-original/app/Adventures/}Open Play Sandbox.pak")
    hdr, blocks = mapfile.read_file(path)[0]
    d = {b["rank"]: b["data"] for b in blocks}

    def grid(r, dt):
        return np.frombuffer(d[r], dt)[:N * N].reshape(N, N)
    fl, img = grid(6, "<u4"), grid(4, "<u4")
    ids, drw, pcs = images_full(fl, grid(23, "u1"), grid(8, "u1"), scrub=grid(22, "u1"), meadow=grid(15, "u1"),
                                regrowth=grid(19, "u1"), piece=grid(7, "u1"),
                                desirability=np.full((N, N), 5, np.int8))
    ref = norm_ids(img) if hdr["version"] < 300 else img
    comp = ((fl & SKIP_TILE) == 0) & ((fl & CLIFF) == 0) & ((ref >> 14) == 5)
    ok = comp & (ids == ref)
    print("compared tiles %d (non-cliff, in play area), image id match %.2f%%" % (comp.sum(), 100.0 * ok.sum() / comp.sum()))
    dd = comp & ((grid(5, "u1") & 0x40) == (drw & 0x40))
    print("draw bit 0x40 match %.2f%%" % (100.0 * dd.sum() / comp.sum()))
    return ok.sum() / comp.sum()


if __name__ == "__main__":
    _selfcheck()
