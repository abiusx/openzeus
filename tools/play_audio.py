#!/usr/bin/env python3
"""Build data/play/audio.json from zeus-original (sound_fxU.txt, music.txt) + the exe tables.
Run with re/venv/bin/python3 (needs pefile). Facts only; see docs/play/audio.md."""
import json, os, re, struct, collections
import pefile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, 'zeus-original/app/Audio')
pe = pefile.PE(os.path.join(ROOT, 'zeus-original/app/Zeus.exe'))
BASE = pe.OPTIONAL_HEADER.ImageBase
def rd(va, n): return pe.get_data(va - BASE, n)
def cstr(va, n=96): return rd(va, n).split(b'\0')[0].decode('latin1')

def listdir_ci(d):
    return {f.lower(): f for f in os.listdir(os.path.join(A, d))}
L1 = listdir_ci('Ambient/Layer1'); L2 = listdir_ci('Ambient/Layer2'); WV = listdir_ci('Wavs')
missing = []
def l2(f):
    r = L2.get(f.lower())
    if not r: missing.append('Layer2/' + f); return None
    return 'Ambient/Layer2/' + r
def l1(f):
    r = L1.get(f.lower())
    if not r: missing.append('Layer1/' + f); return None
    return 'Ambient/Layer1/' + r
def wv(f):
    r = WV.get(f.lower())
    if not r: missing.append('Wavs/' + f); return None
    return 'Wavs/' + r

# ---- category names -> index, exactly as the loader (0x005A17E0) matches them. Unmatched names keep
# the previous index (ORCHARD is spelled ORHCARD in the exe; MARBLE matches nothing).
CAT = {'COMMON_HOUSING':0,'ELITE_HOUSING':1,'FARMING':2,'ORHCARD':3,'SHEEP_FARM':6,'GOAT_FARM':7,'SEA':8,
 'TRIREME_WHARF':9,'HUNTING':10,'TIMBER_MILL':11,'STONE_CUTTER':12,'MINT':13,'FOUNDRY':14,'WORKSHOPS':15,
 'STORAGE':16,'AGORA_FOOD':17,'AGORA_FLEECE':18,'AGORA_OIL':19,'AGORA_WINE':20,'AGORA_ARMS':21,'AGORA_HORSE':22,
 'TRADE':23,'MUNICIPAL':24,'PALACE':25,'DEFENSIVE':26,'INFIRMARY':27,'THEATRE':28,'DRAMA':29,'PHILOSOPHY':30,
 'GYMNASIUM':31,'STADIUM':32,'SANCTUARY':33,'ARMORY':34,'HORSE_RANCH':35,'BEAUTIFICATION':36,'DESERT':37,
 'MEADOW':38,'FARMLAND':2,'BEACH':39,'ROCKY':40,'VEGETATION':41,'WATER':42,'LAVA':43,'MARBLE_QUARRY':44,
 'BOAR':45,'GOAT':46,'WOLF':47,'SHEEP':48,'FOUNTAIN':49,'ARTISAN':50,'MAINTENANCE_OFFICE':51,'RACETRACK':52,
 'BIBLIOTHEKE':53,'OBSERVATORY':54,'UNIVERSITY':55,'RESEARCH':56,'MUSEUM':57,'CHARIOT_FACTORY':58,
 'FRUIT_GROWERS_LODGE':59,'AGORA_CHARIOT':60,'DEER':61,'CATTLE':62,'CORRAL':63,'MAMMALDROME':64}
IDXNAME = {}
for n, i in CAT.items():
    if n in ('ORHCARD', 'FARMLAND', 'STONE_CUTTER'): continue
    IDXNAME[i] = n
IDXNAME[3] = 'ORCHARD (unused slot; the file name ORCHARD never matches, its sounds go to FARMING)'
IDXNAME[12] = 'STONE_CUTTER (no sounds in the file)'
IDXNAME[2] = 'FARMING (also receives ORCHARD, FARMLAND and the terrain list named FARMLAND)'

cats = {i: {'name': IDXNAME[i], 'weight': 0, 'files': []} for i in IDXNAME}
layer1 = []; freq = {}
sec = None; cur = 0
for raw in open(os.path.join(A, 'sound_fxU.txt'), errors='ignore'):
    line = raw.strip()
    if not line or line.startswith(';'): continue
    tok = line.split()
    if tok[0] == 'LAYER1_START': sec = 1; continue
    if tok[0] == 'LAYER2_START': sec = 2; continue
    if tok[0] == 'FREQUENCY_L1': freq['layer1'] = int(tok[1]); continue
    if tok[0] == 'FREQUENCY_L2': freq['layer2'] = int(tok[1]); continue
    if sec == 1:
        f = tok[0]
        layer1.append({'file': l1(f), 'jitter': int(tok[1]), 'flag': tok[2],
                       'pos_scale': [int(tok[3]), int(tok[4]), int(tok[5])], 'mode': tok[6],
                       'a': float(tok[7]), 'b': float(tok[8]), 'dir': tok[9], 'speed': float(tok[10]),
                       'secs_min': int(tok[11]), 'secs_max': int(tok[12])})
    elif sec == 2:
        if tok[0] == 'CATEGORY':
            cur = CAT.get(tok[1], cur)
            if tok[1] in CAT: cats[cur]['weight'] = int(tok[2])
            else: cats[cur]['weight'] = int(tok[2])  # unmatched: loader still stores weight on the sticky index
        else:
            p = l2(tok[0])
            if p and len(cats[cur]['files']) < 20: cats[cur]['files'].append(p)

# ---- building type -> category (g_building_type_info +0x18) and click sound table (0x005A3E30)
bld = json.load(open(os.path.join(ROOT, 'data/buildings.json')))
src = open(os.path.join(ROOT, 're/decomp/zeus.c'), errors='ignore').read().split('\n')
start = next(i for i, l in enumerate(src) if l.startswith('// ===== FUN_005a3e30'))
click = collections.defaultdict(list)
for l in src[start:start + 160]:
    m = re.search(r'FUN_005a3dc0\((0x[0-9a-f]+|\d+),\w+?_([0-9a-f]{8}),(\d)\)', l)
    if m:
        click[int(m.group(1), 0)].append((int(m.group(3)), cstr(int(m.group(2), 16)).replace('\\', '/')))
def clickfiles(t):
    ents = click.get(t, [])
    s0 = [p for slot, p in ents if slot == 0]
    s1 = [p for slot, p in ents if slot == 1]
    out = []
    for p in (s0[-1:] + s1):          # slot 0 is overwritten by later writes; slot 1 appends (max 3)
        r = l2(os.path.basename(p))
        if r: out.append(r)
    return out

SPECIAL = {80: 'only if the stadium has workers and a show is running',
           133: 'only if the ranch has walkers out', 134: 'only if the ranch (enclosure) has walkers out',
           216: 'only if the corral has animals (timer_aa or boost_timer nonzero)',
           199: 'only while a race is running (flags DAT_00ff80d5 and DAT_00fe6a5c both set; exact meaning unverified)'}
buildings = {}
for k, v in bld.items():
    t = v['zeus_id']
    if t is None:
        buildings[k] = {'category': None, 'ambient_files': [], 'click': [], 'rule': 'none (test building)'}
        continue
    c = struct.unpack('<8i', rd(0x5f6368 + t * 32, 32))[6]
    if c == 52: c_eff = [52, 'or 64 (MAMMALDROME) when DAT_00777288 is set']
    ent = {'zeus_id': t,
           'category': c if c >= 0 else None,
           'category_name': IDXNAME.get(c, '').split(' ')[0] if c >= 0 else None,
           'ambient_files': cats[c]['files'] if c >= 0 else [],
           'ambient_weight': cats[c]['weight'] if c >= 0 else None,
           'click': clickfiles(t)}
    if t in SPECIAL: ent['ambient_condition'] = SPECIAL[t]
    ent['rule'] = ('ambient: category pick when the building is under one of the 3 sampled screen points; '
                   'click: the first click file plays when its info panel opens' if ent['click'] and c >= 0 else
                   'click only' if ent['click'] else 'ambient only' if c >= 0 else 'silent')
    if k == 'maintenance': ent['click_note'] = 'table writes municipal1.wav (file does not exist) then maintenance1.wav; the second wins'
    if k in ('house', 'elite_house'): ent['click_note'] = 'all house levels (zeus ids 2..8 / 9..14) use the same click file'
    buildings[k] = ent

# ---- music
mus = {'general': [], 'combat_short': [], 'special_listed': [], 'combat_long': []}
sect = None
for raw in open(os.path.join(A, 'music.txt'), errors='ignore'):
    s = raw.strip()
    if not s or s.startswith(';'): continue
    if s == 'GENERAL_MUSIC': sect = 'general'
    elif s == 'COMBAT_MUSIC_SHORT': sect = 'combat_short'
    elif s == 'COMBAT_MUSIC_LONG': sect = 'combat_long'
    elif s == 'SPECIAL_MUSIC': sect = 'special_listed'
    else: mus[sect].append('Music/' + s)
for g in mus.values():
    for f in g: assert os.path.exists(os.path.join(A, f)), f

# ---- walker voice table (0x0064BF94: 20 x 24-byte names per info-panel walker class 1..50)
voices = {}
for t in range(1, 51):
    row = [cstr(0x64bf94 + (t * 20 + m - 20) * 0x18, 24) for m in range(20)]
    row = [x for x in row]
    while row and row[-1] in ('nothing.mp3', ''): row.pop()
    voices[str(t)] = row

# ---- what the walker window plays (docs/play/audio.md 3): FUN_005ABD00 on opening the land window (FUN_005717D0)
# and on a click on a figure box (0x00405E90). Row = the figure's thought group g (FUN_004E3750 = figure type table
# +0x10, the walker window's thought group), column = its phrase Figure+0x7D (FUN_005ABB90), < 20:
#   g 0x154..0x160 -> table 0x00653254 row g-0x154; 0x161..0x162 -> row g-0x161; 0x163..0x166 -> g-0x163;
#   0x167..0x168 -> g-0x167 (FUN_005A9480; the overlapping rows are the exe's);
#   else (not gods/heroes 0x43..0x47) class g-0xC9, 0 < class < 0x34 -> table 0x0064BF94 row class (FUN_005A9390).
# Files resolved to their on-disk spelling under Voice/Walker; None = no such file (nothing.mp3, warship_*, ...).
VW = listdir_ci('Voice/Walker')
def vrow(va):
    return [(lambda f: ('Voice/Walker/' + VW[f.lower()]) if f.lower() in VW else None)(cstr(va + m * 0x18, 24))
            for m in range(20)]
def trim(r):
    while r and r[-1] is None: r.pop()
    return r
by_group = {}
for g in list(range(0xca, 0xc9 + 0x34)) + list(range(0x154, 0x169)):
    if g >= 0x154:
        r = g - (0x154 if g <= 0x160 else 0x161 if g <= 0x162 else 0x163 if g <= 0x166 else 0x167)
        row = vrow(0x653254 + r * 20 * 0x18)
    else:
        row = vrow(0x64bf94 + (g - 0xc9 - 1) * 20 * 0x18)
    if any(row): by_group[str(g)] = trim(row)
# a figure without a thought group (FUN_004E3750 = -1): FUN_005A9250 plays an animal's sound from 0x0065A784
# (7 x 0x104 bytes) instead: cattle (type 0x4C or flag 0x80000), sheep 0x31, goat 0x32, horse 0x2B (and 0x2F of
# building 0x49/0xD4/199), deer (0x33 resource 1), boar (0x33 other), wolf 0x3B; same voice stream and volume
AN = ['cattle', 'sheep', 'goat', 'horse', 'deer', 'boar', 'wolf']
animal_voice = {}
for i, k in enumerate(AN):
    f = cstr(0x65a784 + i * 0x104, 0x104).replace('\\', '/').split('/')[-1]
    animal_voice[k] = l2(f)

# ---- figure sound samples (bug 393): table 0x010E0518 [kind * 0x11 + variant], filled by FUN_005A4C70(kind, path,
# variant) calls in FUN_005A5D00 (and FUN_005A4CA0 / FUN_005A54A0), read from the instructions (push variant; push
# path; push kind; call 0x5A4C70). Variants: 1 / 2 attack (FUN_004DB3D0(f, 0)), 3 / 4 missile (FUN_004DB3D0(f, 1),
# FUN_004D9D20), 7 hit (FUN_004DB7A0), 8 die (FUN_004DAB30), 0x10 special. FUN_005A6FE0 plays one only for a figure
# on screen, at the sfx volume, panned by its screen x; the variant pick is the CRT rand() (1 + rand % 2): not sim.
def combat_samples():
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    out = collections.defaultdict(dict)
    for va in (0x005A4CA0, 0x005A54A0, 0x005A5D00):
        pushes = []
        for ins in md.disasm(rd(va, 0x2000), va):
            if ins.mnemonic == 'push' and ins.op_str.startswith('0x') or ins.mnemonic == 'push' and ins.op_str.isdigit():
                pushes.append(int(ins.op_str, 0))
            elif ins.mnemonic == 'call':
                if ins.op_str == '0x5a4c70' and len(pushes) >= 3:
                    kind, path, var = pushes[-1], pushes[-2], pushes[-3]
                    f = cstr(path).replace('\\', '/')
                    name = f.split('/')[-1]
                    out[kind][var] = wv(name)
                pushes = []
            elif ins.mnemonic == 'ret':
                break
    return {str(k): {str(v): f for v, f in sorted(d.items())} for k, d in sorted(out.items())}


SAMPLES = combat_samples()
# exe figure type -> sound kind, Zeus (not the Poseidon game): FUN_004DB7A0 (hit) and FUN_004DAB30 (die) switch on
# the type to the same kinds; FUN_004DB3D0 (attack, variants 1 / 2 / missile 3 / 4) to these for the types listed in
# ATTACK_TYPES (others: no attack sound). Flags 0x80000 (and type 0x4C cattle) -> 0x83. Special cases: 0xC in
# formation 0x21 / 0x22 (Ares' warriors) -> 0x14; 0x33 resource 0 boar 0x40, else deer 0x84; 0x35 hunter resource 0
# 0x41 (die: else 0x7E); 0x25 agora vendor by agora (0x4A food, 0x49, 0x53, 0x68, 0x3D, 0x50); 0x3E by its building
# (0x32 / 0xD3 -> 0x45, 0x30 -> 0x5C, 0x31 / 0xD5 -> 0x5D); 0x3F only when +0x5D (trade city) != 8; invaders 0x28..0x2A
# by army (FUN_004DC560: ARMY_KIND); gods / monsters / heroes: their own (roles "god:", "monster:m", "hero:h" above)
TYPE_KIND = {1: 0x51, 2: 0x47, 3: 0x64, 4: 0x42, 9: 0x42, 0x1C: 0x42, 0x24: 0x42, 5: 0x4D, 7: 0x43, 8: 0x5E, 0xB: 1,
             0xC: 2, 0xD: 3, 0xF: 0x44, 0x10: 0x56, 0x11: 0x3F, 0x12: 0x3C, 0x13: 0x5F, 0x14: 0x60, 0x15: 0x61,
             0x16: 0x54, 0x17: 0x54, 0x1B: 0x54, 0x1D: 0x54, 0x19: 0x48, 0x1A: 0x55, 0x1E: 0x5B, 0x1F: 0x4C, 0x20: 0x4E,
             0x25: 0x4A, 0x26: 0x52, 0x27: 0, 0x2C: 0x63, 0x2E: 0, 0x2F: 0x65, 0x31: 0x5A, 0x32: 0x4B, 0x33: 0x40,
             0x35: 0x41, 0x37: 0x62, 0x39: 4, 0x3A: 0x3E, 0x3B: 0x69, 0x3C: 0x67, 0x3D: 0x66, 0x3E: 0x45, 0x3F: 9,
             0x40: 8, 0x41: 0x58, 0x42: 0x57, 0x48: 0x82, 0x49: 0x7A, 0x4A: 0x80, 0x4B: 0x7D, 0x4C: 0x83, 0x4D: 0x7B}
ATTACK_TYPES = [0xB, 0xC, 0xD, 0x16, 0x17, 0x1B, 0x1D, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x2E, 0x32, 0x33, 0x35, 0x39,
                0x3B, 0x3D, 0x3F, 0x40, 0x4C]
# FUN_004DC560(army, f, variant): per army 0..10; None = silent
ARMY_KIND = {'enemy_archer': [5, 0xB, 0xE, 0x13, 0x11, 0x71, 0x74, 0x76, 0x78, 0x6E, None],
             'enemy_infantry': [6, 0xA, 0xD, 0x12, 0x10, 0x72, 0x75, None, 0x79, 0x6F, 0x14],
             'enemy_cavalry': [7, 0xC, 0xF, None, None, 0x73, None, 0x77, None, 0x70, None]}
from play_walker_info import ROLE_TYPE  # noqa: E402  (our roles -> exe figure types)
FIGHT_ROLES = dict(ROLE_TYPE, wall_sentry=0x27, tower_sentry=0x2E, enemy_warship=0x40, enemy_transport=0x3F)

out = {
 'dir': 'zeus-original/app/Audio',
 'formats': {'wav': 'all 703 .wav (Ambient 245, Wavs 455, Music 3) are PCM 16-bit, valid headers (mostly mono 22050 Hz; 9 files 44100 Hz; 3 stereo): browser-playable, no conversion',
             'mp3': 'Music/Voice are MP3 (music 44100 Hz stereo 160 kb/s): browser-playable'},
 'music': {
   'city': mus['general'],
   'combat_short': mus['combat_short'], 'combat_long': mus['combat_long'],
   'special': {'mon1': 'Music/S_mon1.mp3', 'mon2': 'Music/S_mon2.mp3', 'dis': 'Music/S_dis.mp3', 'games': 'Music/S_games.mp3'},
   'menu': 'Music/Setup.mp3', 'mission_intro': 'Music/mission_intro.wav', 'mission_victory': 'Music/mission_victory.wav',
   'campaign_victory': 'Music/campaign_victory.wav',
   'rules': {
     'order': 'general list is played sequentially in music.txt order (index starts at -1, +1 per finished track, wraps); NOT shuffled (eZeus shuffles; the exe does not)',
     'combat_trigger': 'enemy units alive > 0, or enemy warships > 0, or two other condition functions (FUN_004E5E50(2,1), FUN_0052EEB0; unidentified, probably active invasion/monster event) -> state 1',
     'combat_pick': 'alternate long / short: first short (toggle starts 0 -> 1 = short), then long, then short...; random track inside the chosen list; when the track ends the next combat track starts',
     'combat_timeout_ms': 600000, 'after_combat': 'when the 10 min combat window ends or the threat is gone, the interrupted city track resumes at its saved position (state 3 -> resume)',
     'special_events': 'one-shot stingers (state 2) that pause the city track and resume it after: mon1 = monster/ hero-of-event arrival messages (arg 0,1,4), mon2 = monster slain / events (2,5), dis = disaster messages (3,6), games = games/ victory-type message (7); see docs/play/audio.md',
     'volume': 'music on/off DAT_00f2a76c; no per-track fade logic found in the exe (eZeus fades 1 s on switch)'}},
 'ambient': {
   'layer1': {'dir': 'Ambient/Layer1', 'per_frame_denominator': freq.get('layer1'), 'entries': layer1,
              'rules': '1 draw per rendered frame: rand % 2000 == 1 -> if no layer-1 sound is currently playing, pick one entry uniformly (rand % count) and play it positioned in 3D around the listener for secs_min..secs_max seconds (rand), volume = ambient slider; only in normal city view'},
   'layer2': {'dir': 'Ambient/Layer2', 'per_frame_denominator': freq.get('layer2'),
              'categories': {str(i): c for i, c in sorted(cats.items())},
              'rules': '1 draw per rendered frame: rand % 300 == 1 -> sample 3 random screen points (x in 0..W-10, y in 30..H), classify each tile as building / walker / terrain, draw rand(weight) for each, play from the highest; see docs/play/audio.md'},
   'terrain_to_category': {'tree(0x1)': 41, 'rock/cliff/copper/silver(0x300002 any)': 40, 'water(0x4, not 0x80000)': 42,
                           'meadow(0x800)': 38, 'beach(0x10000)': 39, 'marble(0x20000)': 44, 'lava/disaster(0x1000000)': 43,
                           'other (bare ground)': 37},
   'terrain_order': ['0x1 tree -> VEGETATION 41', '0x300002 -> ROCKY 40', '0x4 and not 0x80000 -> WATER 42', '0x800 -> MEADOW 38',
                     '0x10000 -> BEACH 39', '0x20000 -> MARBLE 44', '0x1000000 -> LAVA 43', 'else DESERT 37 (no sounds, weight 10)'],
   'walker_to_category': {'sheep(figure 0x31)': 48, 'goat(0x32)': 46, 'boar(0x33, resource!=1)': 45, 'deer(0x33, resource==1)': 61,
                          'wolf(0x3b)': 47, 'cattle(0x4c)': 62}},
 'buildings': buildings,
 'events': {
   'note': 'index = FUN_005A4C00 argument; played at the sfx volume slider, centre pan; unset indexes are silent',
   'button': {'idx': 0, 'file': wv('button.wav'), 'when': 'every left mouse press that mouse_poll accepts (any button/UI click)'},
   'collapse': {'idx': 1, 'file': wv('collapse.wav'), 'when': 'collapse_debris_spawn with the sound flag (building collapse)'},
   'earthquake': {'idx': 2, 'file': wv('D_Earthquake.wav'), 'when': 'earthquake disaster message'},
   'flood': {'idx': 3, 'file': wv('D_Flood.wav'), 'when': 'flood disaster message'},
   'landslide': {'idx': 4, 'file': wv('D_Landslide.wav'), 'when': 'landslide disaster'},
   'lava': {'idx': 5, 'file': wv('D_Lava.wav'), 'when': 'lava disaster'},
   'place_building': {'idx': 6, 'file': wv('place_building.wav'), 'when': 'a placed building/tile is committed by the build routine (flag param_6)'},
   'fire': {'idx': 7, 'file': wv('Fire.wav'), 'when': 'a building ignites (fire spread) and when a fire figure spawns'},
   'recreation_panel': {'idx': 24, 'file': l2('recreation1.wav'), 'when': 'info panel kind 0xC is drawn (beautification building panel)'},
   'archer_impact': {'idx': 25, 'file': wv('archer_impact.wav'), 'when': 'missile/arrow hits'},
   'fireball_hit': {'idx': 26, 'file': wv('Fireball_hit.wav'), 'when': 'fireball hits'},
   'demolish': {'idx': 9, 'file': None, 'when': 'clear_land_commit calls idx 9 but no sample is registered: silent'},
   'message_arrive': {'idx': 16, 'file': None, 'when': 'new message (FUN_00521A70 calls idx 0x10) but no sample is registered: silent'},
 },
 'combat': {
   'note': 'fight sounds per figure sound group (table 0x010E0518, filled by FUN_005A5D00; slot 1/2 attack, 7 hit, 8 die), '
           'played by FUN_005A6FE0 only when the figure is on screen, sfx volume; see docs/logic/services.md 6.1',
   'rules': {'attack': 'FUN_004DB3D0: the figure that walked into the fight, at its start; criminals also every time their '
                       'fight animation (8 frames, 1 per tick) reaches frame 1, and a vandal at work likewise',
             'hit': 'FUN_004DB7A0: on the figure hit by a non-lethal blow (every 24 fight ticks; criminals hit for 0 damage '
                    'but still make the watchman play its hit sound)',
             'die': 'FUN_004DAB30: on the figure killed (start of its 128-tick dying)',
             'monster': 'figure_monster_update 0x004C8760: atk1/atk2 (FUN_004DB3D0(f, 0) -> FUN_004DC2E0) every tick it '
                        'stands blocked (direction 11, bashing; 0x004C8C72) unless dying, and in melee (action 5) when its '
                        'fight animation is at frame 1 (0x004C8D22); after a smash (end of action 27, 0x00532791); '
                        'the Kraken plays slot 9 "appear" when spawned (0x0052F726); sound_play_sample refuses a playing sample'},
   'roles': {r: {'attack': [wv('outlaw_attack.wav')], 'hit': wv('outlaw_hit.wav'), 'die': wv('outlaw_die.wav'),
                 'group': '0x54 (types 0x16 disgruntled, 0x17 thief, 0x1B mugger, 0x1D vandal)'}
             for r in ('disgruntled', 'thief', 'mugger', 'vandal')} | {
       'watchman': {'attack': [wv('watchman_attack.wav')], 'hit': wv('gen_hit8.wav'), 'die': wv('gen_die8.wav'), 'group': '0x66 (type 0x3D)'},
       'hunter': {'attack': [wv('boar_hunter_attack.wav')], 'hit': wv('boar_hunter_hit.wav'), 'die': wv('boar_hunter_die.wav'),
                  'group': '0x41 (type 0x35 with resource 0; resource != 0 uses another group, not checked)'},
       'woodcutter': {'attack': [], 'hit': wv('gen_hit5.wav'), 'die': wv('gen_die5.wav'), 'group': '0x62 (type 0x37; no attack sample registered)'}}
     | {f'hero:h{h}': {'attack': [wv(f'H_{n}_atk1.wav'), wv(f'H_{n}_atk2.wav')], 'hit': wv(f'H_{n}_hit.wav'),
                       'die': wv(f'H_{n}_die.wav'), 'group': hex(0x15 + h) + ' (hero type 0x45, by hero id: sim/heroes good h<id>)'}
        for h, n in enumerate(('achilles', 'hercules', 'jason', 'odysseus', 'perseus', 'theseus', 'atalanta', 'bellerophon'))}
     | {f'monster:m{m}': {'attack': [wv(f'{pre}_atk{k}.wav') for k in (1, 2, 3, 4)], 'hit': wv(f'{pre}_hit.wav'),
                          'die': wv(f'{pre}_die.wav'), 'group': f'{g} (monster type 0x44, by name; sim/heroes good m<id>)',
                          **({'appear': wv(f'{pre}_appear.wav')} if m == 1 else {})}   # slot 9: monster_spawn_and_act 0x0052F726
        for m, pre, g in ((0, 'M_hydra', '0x25'), (1, 'M_kraken', '0x1d'), (2, 'M_cerberus', '0x23'), (3, 'M_cyclops', '0x24'),
                          (4, 'M_minotaur', '0x20'), (5, 'M_medusa', '0x1f'), (6, 'M_calydonian', '0x27'), (7, 'M_dragon', '0x28'),
                          (8, 'M_talos', '0x22'), (9, 'M_hector', '0x26'), (10, 'M_scylla', '0x21'), (11, 'M_maenads', '0x1e'),
                          (12, 'M_sphinx', '0x2a'), (13, 'M_chimera', '0x2b'), (14, 'M_harpies', '0x2c'), (15, 'M_echidna', '0x2d?'))},
   'samples': SAMPLES, 'type_kind': {str(k): v for k, v in TYPE_KIND.items()}, 'attack_types': ATTACK_TYPES,
   'army_kind': ARMY_KIND, 'role_type': FIGHT_ROLES, 'sanct_kind': {'hoplite:ares': 0x14}, 'role_kind': {'deer': 0x84},
   'military': {
     'attack': 'figure_fight_start 0x004D4BA0: the mover, FUN_004DB3D0(f, 0) (variant 1 or 2) at the start; '
               'horseman_charge_hit 0x004E1080 too',
     'periodic': 'fig_handler_enemy_infantry 0x004B9C20 action 5: attack_timer == 10 (cavalry none); '
                 'fig_handler_hoplite 0x004B26B0 (palace and Ares warriors): attack_timer == 1; a siege '
                 '(figure_check_next_tile 0x004D8BB0, direction 11): anim_frame == 1',
     'missile': 'FUN_004D9D20 = FUN_004DB3D0(f, 1) (variant 3 or 4): enemy archers at frame 1 of the shot (0x005011C0), '
                'rabble at attack_timer 1 of a throw (archer_fire_update 0x004B2F70), wall sentries with the arrow '
                '(0x004B9230), tower ballistas at attack_timer 1 (0x004BB7B0); kinds 0x27 / 0x2E are 0 (archer volley)',
     'hit': 'figure_hit 0x004D54D0: FUN_004DB7A0(target) on a blow that does not kill (variant 7)',
     'die': 'FUN_004DAB30 at the death (variant 8)',
     'impact': 'archer_impact (event 0x19) only under the flag 0x00777286 (not set in Zeus play): none'}},
 'ui': {'button': wv('button.wav'), 'place_building': wv('place_building.wav'),
        'error': None, 'note': 'no distinct error/deny sound exists in the exe table'},
 'walker_voices': {'dir': 'Voice/Walker', 'table_by_info_panel_class': voices,
        'by_thought_group': by_group, 'animals': animal_voice,
        'rule': 'walker window open (FUN_005717D0 -> FUN_005ABD00) and figure box click (0x00405E90): '
                'by_thought_group[thought group][phrase], else animals[kind]; one voice stream (AIL stream 1: a new '
                'one closes the old), played once at the speech volume (0x00F2A7D4), speech on (0x00F2A76D)',
        'note': 'row index = message index of the walker info panel (0..19); trailing nothing.mp3 removed. Class ids are the info-panel walker class (1..50), mapping to our walker keys is in docs/play/audio.md'},
}

os.makedirs(os.path.join(ROOT, 'data/play'), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, 'data/play/audio.json'), 'w'), indent=1)
print('missing:', missing)
print('click types:', len(click), 'bldg keys', len(buildings))
