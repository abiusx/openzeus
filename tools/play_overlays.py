"""Build data/play/overlays.json: the original's map overlays ("See water", "See problems", ...; docs/play/pages.md).

    re/venv/bin/python tools/play_overlays.py      (needs pefile + unicorn; reads zeus-original/app/Zeus.exe)

How the exe draws an overlay (city_draw 0x00458170, ground_tile_draw 0x00457900): the current overlay id
0x00FA05F0 selects a view object 0x00641C10[id] whose vtable (set by the static constructors 0x0055E990..
0x0055EBF0) answers per building / walker / tile:
  +0x08 building drawn as is (else its footprint is drawn flat, 0x0044B050)   +0x10 walker drawn
  +0x0C building gets an overlay on this tile    +0x00 draw that overlay (x, y = the anchor tile's draw point)
  +0x20 overlay drawn in the last pass (over everything) instead of right after the building
  +0x18 terrain tile drawn as is (walls 0x4000 / garden 0x20 tiles become footprints)
  +0x14 / +0x04 walker icon; +0x24 minimap image (0x0055F250 via +0x28 red / +0x30 green / +0x2C purple) and
  +0x1C hover tooltip: emulated per type with the field swept (Probe; modes[id].minimap / .tooltip).
The visibility predicates are run in an emulator (unicorn) for every building / figure type, so the type lists
below are the exe's own answers; the draw routines were read in the disassembly (addresses in the output).
"""
import json
import os
import re
import struct

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UcError, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EAX, UC_X86_REG_EIP

import sg3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "zeus-original", "app", "Zeus.exe")
OUT = os.path.join(ROOT, "data", "play", "overlays.json")
SPR = os.path.join(ROOT, "extracted", "sprites")

PE = pefile.PE(EXE, fast_load=True)
BASE, SIZE = PE.OPTIONAL_HEADER.ImageBase, PE.OPTIONAL_HEADER.SizeOfImage
BLD, BSZ, FIG, FSZ = 0x0092E658, 0x118, 0x00DBD788, 0x184
VIEW_TABLE = 0x00641C10
# view objects (BSS) and the vtables their constructors store (mov [obj], vtable at 0x0055E990 + 0x20 k)
VTABLES = {0: 0x5E4424, 1: 0x5E4458, 2: 0x5E448C, 3: 0x5E44C0, 4: 0x5E44F4, 5: 0x5E4528, 6: 0x5E455C, 7: 0x5E4590,
           8: 0x5E45C4, 9: 0x5E45F8, 10: 0x5E462C, 11: 0x5E4660, 12: 0x5E4694, 13: 0x5E46C8, 14: 0x5E46FC,
           15: 0x5E4730, 16: 0x5E4764, 17: 0x5E4798, 18: 0x5E47CC, 19: 0x5E43F0}


def rd(va, n):
    rva = va - BASE
    for s in PE.sections:
        if s.VirtualAddress <= rva < s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData):
            b = s.get_data()[rva - s.VirtualAddress:rva - s.VirtualAddress + n]
            return b + b"\0" * (n - len(b))
    raise KeyError(hex(va))


def ints(va, n):
    return list(struct.unpack("<%di" % n, rd(va, 4 * n)))


class Emu:
    """Zeus.exe mapped in unicorn: call one method of a view object on a fake building / figure record."""
    TAB, STK, RET = 0x20000000, 0x30000000, 0x40000100

    def __init__(self):
        u = self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        u.mem_map(0, 0x10000)
        u.mem_map(BASE, (SIZE + 0xFFF) & ~0xFFF)
        for s in PE.sections:
            d = s.get_data()
            u.mem_write(BASE + s.VirtualAddress, d[:s.Misc_VirtualSize] if s.Misc_VirtualSize else d)
        u.mem_map(self.TAB, 0x100000)
        u.mem_map(self.STK - 0x100000, 0x200000)
        u.mem_map(0x40000000, 0x1000)
        for bank in range(40):                    # image banks: group table entry g -> first image g*32
            bb = 0x012AFBE8 + bank * 0xCC44
            t = self.TAB + bank * 0x1000
            u.mem_write(bb + 4, struct.pack("<I", t))
            u.mem_write(bb + 0xCC38, struct.pack("<i", 511))
            u.mem_write(t, b"".join(struct.pack("<II", 0, g * 32) for g in range(512)))
        for m, vt in VTABLES.items():
            u.mem_write(struct.unpack("<I", rd(VIEW_TABLE + 4 * m, 4))[0], struct.pack("<I", vt))
        u.mem_write(0x00564560, b"\xC2\x04\x00")  # building_status_flags: keep the flags we set

    def method(self, mode, k):
        return struct.unpack("<I", rd(VTABLES[mode] + 4 * k, 4))[0]

    def call(self, fn, args, this, full=False):
        u = self.u
        esp = self.STK - 0x1000 - 4 * len(args) - 4
        u.mem_write(esp, struct.pack("<I", self.RET) + b"".join(struct.pack("<i", a) for a in args))
        u.reg_write(UC_X86_REG_ESP, esp)
        u.reg_write(UC_X86_REG_ECX, this)
        u.emu_start(fn, self.RET, count=200000)
        return u.reg_read(UC_X86_REG_EAX) & (0xFFFFFFFF if full else 0xFF)

    def building(self, t, fields=()):
        self.u.mem_write(BLD, b"\0" * BSZ * 3)
        rec = BLD + BSZ
        self.u.mem_write(rec, b"\1")
        self.u.mem_write(rec + 0x10, struct.pack("<h", t))
        self.u.mem_write(rec + 5, bytes([1 if 2 <= t <= 14 else 0]))
        for off, fmt, v in fields:
            self.u.mem_write(rec + off, struct.pack("<" + fmt, v))

    def figure(self, t):
        self.u.mem_write(FIG, b"\0" * FSZ * 3)
        self.u.mem_write(FIG + FSZ, b"\1")
        self.u.mem_write(FIG + FSZ + 0x0A, bytes([t]))

    def this(self, mode):
        return struct.unpack("<I", rd(VIEW_TABLE + 4 * mode, 4))[0]


def visible_lists(e):
    out = {}
    for m in range(1, 20):
        b, f = [], []
        for t in range(1, 256):
            e.building(t)
            try:
                if e.call(e.method(m, 2), [1], e.this(m)):
                    b.append(t)
            except UcError:
                pass                              # monuments 100..114 ask their composite object (always drawn)
        for t in range(0, 80):
            e.figure(t)
            try:
                if e.call(e.method(m, 4), [1], e.this(m)):
                    f.append(t)
            except UcError:
                pass
        out[m] = (b, f)
    return out


def problem_classes(e):
    """Mode 18: per building type, the panel background and the problem bits it shows (0x00565030)."""
    classes = {}
    for t in range(1, 256):
        bits, bg = [], None
        for bit in range(11):
            e.building(t, [(0x110, "I", 1 << bit), (0x0C, "i", 228 * 100 + 100)])
            try:
                if e.call(e.method(18, 2), [1], e.this(18)):
                    bits.append(bit)
            except UcError:
                bits = None
                break
        if bits is None:
            continue
        classes.setdefault(tuple(bits), []).append(t)
    return classes


def figure_roles():
    """Our walker roles -> the exe's figure types, from data/play/walkers.json ("FIG_... (type N)")."""
    W = json.load(open(os.path.join(ROOT, "data", "play", "walkers.json")))["roles"]
    out = {}
    for role, v in W.items():
        m = re.search(r"\(type (\d+)\)", v.get("orig") or "")
        if m:
            out[role] = [int(m.group(1))]
    out["cart"] = [4, 9, 28, 36]                  # pusher group shared by the four (walkers.json note)
    out["buyer"] = [37]
    out["trainee"] = [15, 16, 17, 18]             # a school sends the venue's own figure
    out["stonecutter"] = [62]
    out["bull"] = [76]
    out["deer"] = [51]                            # Poseidon deer: shown like the boar (hyp)
    return out


def atlas_group(f, name):
    a = json.load(open(os.path.join(SPR, f, "atlas.json")))
    g = {x["name"]: x for x in a["groups"]}[name]
    return {"file": f, "index": g["first"], "group": name}


CLASS_OF_BITS = {(0, 1, 2, 3, 4, 5): "house", (4, 5, 6, 7, 8): "producer", (4, 5, 6, 7, 8, 9): "workshop", (10,): "sanctuary",
                 (4, 5): "other", tuple(range(11)): "always"}   # "always": never flattened (0x0055EE70), panel as "other"


def slot_list(va):
    """[count, bit...]* 0: one icon slot per group (0x00565212 loop)."""
    out, v = [], ints(va, 12)
    i = 0
    while v[i]:
        out.append(v[i + 1:i + 1 + v[i]])
        i += 1 + v[i]
    return out


def footprint_tables():
    """0x0044B050: footprint images per size (positions 0x005F5D08.., image offsets 0x005F87BC..)."""
    T = {2: (0x5F5D08, 0x5F87BC, 4), 3: (0x5F5D28, 0x5F87CC, 9), 4: (0x5F5D70, 0x5F87F0, 16),
         5: (0x5F5DF0, 0x5F8830, 25), 6: (0x5F5EB8, 0x5F8894, 36)}
    out = {}
    for n, (pa, ia, k) in T.items():
        pos, img = ints(pa, 2 * k), ints(ia, k)
        tiles = []
        for (dx, dy), off in zip(zip(pos[0::2], pos[1::2]), img):
            s, d = dy // 15 + (n - 1), dx // 30 - (n - 1)     # i+j, i-j (relative to the left tile (0, n-1))
            tiles.append([(s + d) // 2, (s - d) // 2, off])
        out[n] = tiles
    return out


def supply_tables():
    return {"slots": ints(0x641D44, 6), "goods": ints(0x641D2C, 6),
            "low_common": [ints(0x641C78 + 12 * L, 3) for L in range(7)],
            "low_elite": [ints(0x641CCC + 24 * L, 6) for L in range(4)]}


# ---- minimap colours (+0x24 and its predicates +0x28/+0x2C/+0x30) and hover tooltips (+0x1C) -------------
TILE = 228 * 100 + 100                            # the probed tile (grid offset)
GRID_BUILDING, GRID_FIGURE, GRID_DES = 0xD26E98, 0xD0D878, 0xC9B4E8
MM_TILE, TEXT_PTR, SCRATCH, TIPBUF = 0x7D3BE0, 0xF13A60, 0x40000800, 0x40000A00
FIRST_BUILD, R_ROAD = 0x51, 0x92                  # bank-1 (Zeus_Interface) group indices the colour methods use
MM_OFF = {(FIRST_BUILD, 10): "red", (FIRST_BUILD, 5): "green", (FIRST_BUILD, 20): "purple",
          (FIRST_BUILD, 60): "black", (R_ROAD, 0): "road"}
# per overlay: (our field, [(record offset, struct fmt)], sweep values); fields written with the same value
FIELDS = {
    2: ("problem bits (b+0x110)", [(0x110, "I")], [0, 0x7FF]), 3: ("problem bits (b+0x110)", [(0x110, "I")], [0, 0x7FF]),
    18: ("problem bits (b+0x110)", [(0x110, "I")], [0, 0x7FF]),
    5: ("coverage.water", [(0x77, "B")], range(256)), 6: ("coverage.healer", [(0x78, "B")], range(256)),
    7: ("max(risk fire b+0x48, damage b+0x46)", [(0x48, "h"), (0x46, "h")], range(0, 1301)),
    8: ("unrest", [(0xF4, "i")], range(0, 121)), 9: ("tax_days", [(0x4E, "B")], range(256)),
    10: ("culture", [(0x80, "b")], range(-128, 128)), 11: ("coverage.competition", [(0x6C, "B")], range(256)),
    12: ("coverage.philosophy", [(0x6D, "B")], range(256)), 13: ("coverage.athletics", [(0x6F, "B")], range(256)),
    14: ("coverage.drama", [(0x71, "B")], range(256)), 15: ("sanctuary_activity (b+0x32)", [(0x32, "B")], range(256)),
}


def coarse(vals):
    vals = list(vals)
    step = max(1, len(vals) // 12)
    return sorted(set(vals[::step]) | {vals[0], vals[-1]})


def bands(vals, outs):
    out = []
    for v, o in zip(vals, outs):
        if out and out[-1][2] == o and out[-1][1] == v - 1:
            out[-1][1] = v
        else:
            out.append([v, v, o])
    return out


class Probe:
    """Calls a view object's method on the building at TILE (record 1) with given field values."""

    def __init__(self, e):
        self.e = e
        u = e.u
        u.mem_write(MM_TILE, struct.pack("<i", TILE))
        u.mem_write(GRID_BUILDING + 2 * TILE, struct.pack("<h", 1))
        u.mem_write(GRID_FIGURE + 2 * TILE, struct.pack("<h", 0))
        t = Emu.TAB + 0x1000                      # bank 1: group g -> first image g*256 (offsets up to 60 stay apart)
        u.mem_write(t, b"".join(struct.pack("<II", 0, g * 256) for g in range(512)))
        u.hook_add(UC_HOOK_CODE, self._text, begin=0x508060, end=0x508060)
        # g_building_model 0x00782F70 (221 x 10 i32, loaded from Model/ at run time): hazards ask cols 6/7 (risks)
        cols = ("cost", "desirability", "des_step", "des_step_size", "des_range", "employees", "fire_risk",
                "damage_risk", "resource_used", "risk_reducer")
        rows = json.load(open(os.path.join(ROOT, "extracted", "model", "model_Normal.json")))["buildings"]
        for r in rows:
            u.mem_write(0x00782F70 + 40 * r["id"], struct.pack("<10i", *(r[c] for c in cols)))

    @staticmethod
    def _text(u, addr, size, _):
        """text_pointer_store_a(group, index): return the token "{group:index}" instead of the string."""
        esp = struct.unpack("<I", u.reg_read(UC_X86_REG_ESP).to_bytes(4, "little"))[0]
        ret, g, i = struct.unpack("<Iii", u.mem_read(esp, 12))
        u.mem_write(SCRATCH, ("{%d:%d}" % (g, i)).encode() + b"\0")
        u.mem_write(TEXT_PTR, struct.pack("<I", SCRATCH))
        u.reg_write(UC_X86_REG_ESP, esp + 4)
        u.reg_write(UC_X86_REG_EIP, ret)

    def setup(self, t, spec, v, extra=()):
        flds = [(0x0C, "i", TILE)] + [(off, fmt, v) for off, fmt in (spec[1] if spec else [])] + list(extra)
        self.e.building(t, flds)

    def colour(self, m, t, spec=None, v=0):
        self.setup(t, spec, v)
        try:
            r = self.e.call(self.e.method(m, 9), [1], self.e.this(m), full=True) - 0x4000
        except UcError:
            return "error"
        return MM_OFF.get(divmod(r, 256), "?%x" % r)

    def tip(self, m, t, spec=None, v=0, extra=(), des=0):
        self.setup(t, spec, v, extra)
        self.e.u.mem_write(GRID_DES + TILE, struct.pack("<b", des))
        self.e.u.mem_write(TIPBUF, b"\0" * 256)
        try:
            ok = self.e.call(self.e.method(m, 7), [TILE, TIPBUF], self.e.this(m))
        except UcError:
            return "error"
        if not ok:
            return None
        return bytes(self.e.u.mem_read(TIPBUF, 256)).split(b"\0")[0].decode("latin-1")


def grouped(p, fn, m, spec, types):
    """Group building types by their answers over coarse values, then sweep the field finely on each group."""
    vals = list(spec[2]) if spec else [0]
    sig = {}
    for t in types:
        sig.setdefault(tuple(fn(m, t, spec, v) for v in coarse(vals)), []).append(t)
    out = []
    for s, ts in sig.items():
        fine = [fn(m, ts[0], spec, v) for v in vals]
        if ts[-1] != ts[0]:
            assert fine == [fn(m, ts[-1], spec, v) for v in vals], (m, ts)
        b = bands(vals, fine)
        out.append((ts, b))
    return out


def colour_palette():
    s = sg3.Sg3(os.path.join(ROOT, "zeus-original", "app", "DATA", "Zeus_Interface.sg3"))
    first = {g["id"] - 1: g for g in s.groups}     # exe group index = sg3 group id - 1 (0x51 SPR_R_FIRST_BUILD)

    def ref(gi, off):
        g = first[gi]
        idx = g["first"] + off
        pieces = []
        for n in range(5 if gi == FIRST_BUILD else 1):
            px = s.decode(s.images[idx + n])
            opaque = [tuple(int(c) for c in p[:3]) for row in px for p in row if p[3]]
            pieces.append(max(set(opaque), key=opaque.count))
        px = s.decode(s.images[idx])
        two = [[int(c) for c in px[0, k][:3]] for k in range(2)]
        return {"file": "Zeus_Interface", "index": idx, "group": g["name"], "offset": off, "rgb": two,
                "rgb555": ["0x%04X" % ((r >> 3) << 10 | (gg >> 3) << 5 | (b >> 3)) for r, gg, b in two],
                "piece_rgb": [list(c) for c in pieces]}
    pal = {name: ref(gi, off) for (gi, off), name in MM_OFF.items()}
    pal["appeal"] = [ref(0xBB, 8 + 5 * k) | {"k": k} for k in range(10)]
    return pal


MM_EV = {
    1: "+0x2C 0x0055F390 = drawn as is (+0x08)", 4: "+0x2C 0x0055F390 = drawn as is (+0x08)",
    2: "+0x28 0x0055FFF0 = drawn and problem panel on this tile (+0x0C 0x00560130); +0x2C 0x005608A0 = drawn, no panel",
    3: "+0x28 0x0055FFF0 = drawn and problem panel on this tile (+0x0C 0x00560130); +0x2C 0x005608A0 = drawn, no panel",
    5: "+0x28 0x00560520: common house (2..8) and water b+0x77 / 10 <= 3; +0x30 0x00560580: common house water/10 > 3, "
       "or elite house (9..14); +0x2C 0x005608A0: drawn (+0x08) and no column (+0x0C)",
    6: "+0x28 0x00560850 / +0x30 0x00560910: house (2..14), healer b+0x78 / 10 <= 3 red, > 3 green; +0x2C 0x005608A0",
    7: "+0x28 0x00561050 / +0x30 0x005610C0: column shown (+0x0C 0x00560A40: root type has a fire or collapse risk "
       "(g_building_model cols 6/7), not an agora, fire b+0x48 >= 100 or damage b+0x46 >= 100) and max(fire, damage)/100 "
       "<= 3 red, > 3 green (sic: high risk is green); +0x2C 0x005608A0",
    8: "+0x28 0x00561310 / +0x30 0x00561360: house, unrest b+0xF4 / 10 >= 7 red, < 7 green; +0x2C 0x005608A0",
    9: "+0x28 0x00561650 / +0x30 0x005616B0: house, tax coverage b+0x4E / 5 <= 3 red, > 3 green; +0x2C 0x005608A0",
    10: "+0x28 0x00561AC0 / +0x30 0x00561B30: (column shown (+0x0C 0x00562080) or elite house) and culture b+0x80 / 10 "
        "<= 3 red, > 3 green; +0x2C 0x005608A0",
    11: "+0x28 0x00562C00 / +0x30 0x00562C70: same shape, competition b+0x6C", 12: "0x00561E50 / 0x00561EC0: philosophy b+0x6D",
    13: "0x005624C0 / 0x00562530: athletics b+0x6F", 14: "0x00562860 / 0x005628D0: drama b+0x71",
    15: "+0x28 0x00562F50 / +0x30 0x00562FA0: sanctuary (84..98) and root (0x0049B920) b+0x32 & 0xFE <= 6 red (activity "
        "0..7), else green; +0x2C 0x005608A0",
    16: "+0x2C 0x0055F390 = drawn as is (+0x08)",
    17: "+0x2C 0x0055F390; but the minimap loop colours every tile with flags & 8 (buildings) or desirability != 0 from "
        "the appeal palette first (0x0044BCF0), so buildings never reach +0x24 except tiles without the 8 flag",
    18: "+0x28 0x0055F390 = drawn as is (+0x08 0x00564840: any problem bit of its class); +0x2C false",
    19: "+0x2C 0x0055F390 = drawn as is (roadblocks; avenue/agoras are the road colour anyway)",
}


def minimap_rules(e, p):
    out = {}
    for m in range(1, 20):
        spec = FIELDS.get(m)
        groups = []
        for ts, b in grouped(p, p.colour, m, spec, range(1, 256)):
            cols = {c for _, _, c in b} - {"error"}
            if cols <= {"black"} or any(c == "error" for _, _, c in b):
                continue                          # monuments 100..114 (composite objects) fail in the emulator
            if len(cols) == 1:
                groups.append({"types": ts, "colour": b[0][2]})
            elif spec and spec[2] == [0, 0x7FF]:
                groups.append({"types": ts, "no_problem": b[0][2], "problem": b[-1][2]})
            else:
                groups.append({"types": ts, "field": spec[0], "bands": b})
        out[m] = {"ev": MM_EV[m], "else": "black", "groups": groups}
    return out


TIP_EV = {
    1: "0x0055FB20", 4: "0x0055FB20", 2: "0x0055FF50 -> 0x00565360", 3: "0x0055FF50 -> 0x00565360", 5: "0x00560470",
    6: "0x00560710", 7: "0x00560F10", 8: "0x00561270", 9: "0x00561550", 10: "0x00561970", 11: "0x00562B30",
    12: "0x00561D80", 13: "0x005623F0", 14: "0x00562790", 15: "0x00562EB0", 16: "0x005638A0", 17: "0x005643F0",
    18: "0x00565360", 19: "0x00565750 (none)",
}


def tooltip_rules(e, p):
    out = {}
    for m in (5, 6, 8, 9, 10, 11, 12, 13, 14):
        spec = FIELDS[m]
        groups = []
        for ts, b in grouped(p, p.tip, m, spec, range(1, 256)):
            if any(o is None or o == "error" for _, _, o in b):
                continue
            groups.append({"types": ts, "field": spec[0], "bands": b})
        out[m] = {"when": "house under the mouse with its column on this tile (+0x0C): common houses any tile; elite "
                          "houses only the tile whose picture is the house (tile image test, not emulated)",
                  "groups": groups}
    out[5]["elite"] = "{66:17}"
    out[5]["note"] = "elite houses (9..14): always 66:17 (exe 0x005604A6)"
    out[6]["line2"] = {"field": "fed (b+0x7F ate)", "join": "@L",
                       "values": {str(f): p.tip(6, 5, FIELDS[6], 50, extra=[(0x7F, "B", f)]).split("@L")[1] for f in (0, 1)}}
    out[6]["note"] = "text = band line + '@L' + (ate ? 66:26 : 66:27); elite houses too (tile test)"
    out[9]["paid"] = {"field": "taxes paid this year (b+0x88 + 5000) / 10000 drachmas (house_taxes_paid_display 0x004956A0)",
                      "if_gt_0": "N{66:49}", "probe_37": p.tip(9, 5, FIELDS[9], 1, extra=[(0x88, "i", 37 * 10000)]),
                      "else": "bands by tax coverage below"}
    out[10]["poseidon"] = "Poseidon games: 66:106..116 (science) instead of 50..60"
    out[11]["poseidon"] = "Poseidon: 66:129..132 (curator)"
    out[12]["poseidon"] = "Poseidon: 66:121..124 (astronomer)"
    out[13]["poseidon"] = "Poseidon: 66:117..120 (scholar)"
    out[14]["poseidon"] = "Poseidon: 66:125..128 (inventor)"
    fire = [p.tip(7, 20, ("", [(0x48, "h")]), v) for v in range(0, 1301)]
    dmg = [p.tip(7, 20, ("", [(0x46, "h")]), v) for v in range(0, 1301)]
    assert all(p.tip(7, t) is not None for t in range(1, 100))
    out[7] = {"when": "any building under the mouse (no type or column test); multi-part buildings use the root "
                      "(parent chain b+0x38)",
              "rule": "burning (root b+0x4A != 0; sanctuaries/monuments via 0x0040FC40) -> 66:34; else v = max(fire "
                      "b+0x48, damage b+0x46), k = v<=100:0, <=200:1, <=400:2, <=600:3, <=800:4, else 5; "
                      "fire > damage -> 66:(28+k), else 66:(35+k)",
              "fire_only": bands(range(1301), fire), "damage_only": bands(range(1301), dmg),
              "burning": p.tip(7, 20, None, 0, extra=[(0x4A, "h", 1)])}
    out[17] = {"when": "any map tile under the mouse (building or not)", "field": "tile desirability (T.des, signed)",
               "bands": bands(range(-128, 128), [p.tip(17, 0, None, 0, des=d) for d in range(-128, 128)])}
    out[15] = {"when": "completed sanctuary (0x0053ECA0 >= 100), only its column part (0x004EA390; +0x0C 0x00562E10)",
               "field": "sanctuary_activity (root b+0x32)",
               "bands": [[0, 0, "{66:80}"], [1, 7, "{66:79}"], [8, 255, "{66:77}"]],
               "note": "read in the disassembly (the column-part test is not emulated); 66:78 is never used"}
    for m in (2, 3, 18):
        per = {}
        for t in range(1, 256):
            for bit in range(11):
                r = p.tip(m, t, ("", [(0x110, "I")]), 1 << bit)
                if r and r != "error":
                    per.setdefault(t, {})[bit] = r
        sig = {}
        for t, d in per.items():
            sig.setdefault(json.dumps(d, sort_keys=True), []).append(t)
        out[m] = {"when": "building with a problem bit of its class (same class lists as the panel); the text is "
                          "66:4 + '@L' + for each set bit in slot order 66:(5+bit) + '@L'; sanctuaries only when complete",
                  "groups": [{"types": ts, "bit_text": json.loads(k)} for k, ts in sig.items()]}
        if m in (2, 3):
            out[m]["walker"] = ("no building on the tile: a figure there for which +0x14 holds (cart waiting, figure types "
                                "4/9/36 with figure+0x7B set; 0x0055FFA0) -> 0x00565360 on the figure: 66:16 'This cart has no "
                                "destination.', 0x005655A7.., not emulated)")
    out[1] = out[4] = {
        "when": "house under the mouse with its supply panel (+0x0C 0x0055F7E0)",
        "rule": "66:1 + '@L', then for each slot k < (elite 6 : 3) whose good the house needs now or at the next level "
                "(house_param 0x00433D80 on type and type+1, type 8/14: itself) and is low (0x0055F440, the blinking "
                "test): text 23:[43 Food, 14 Fleece, 20 Olive oil, 18 Armor, 21 Wine, 15 Horses][k] + ' '; if none: "
                "the whole text is 66:3 'Nothing'",
        "slot_text": [[23, 43], [23, 14], [23, 20], [23, 18], [23, 21], [23, 15]]}
    out[16] = {"when": "elite house under the mouse (+0x0C 0x00563150), on its picture tile",
               "rule": "counts from 0x00563180 (soldiers living there, spare horses, spare armour, warriors lacking armour; "
                       "chariots in Poseidon): lines like 66:83 'This house has ' N 66:86/87 ' spare suits of armor.' / "
                       "66:84/85 ' spare horses.', N 66:81/82 ' warriors ... lack armor.', N 66:90/91 hoplite(s) / "
                       "66:88/89 horsem(e)n + 66:98/99 ' live(s) here.'; singular when N == 1",
               "status": "decoded 10-30 (disassembly): one line by the elite-house quadrant's picture offset under the "
                         "mouse (1 spare armour, 4 spare horses, 3 lacking armour, 2 soldiers: H 88/89 [66:2 and] P "
                         "90/91 + 98/99); overlays.js securityTip"}
    out[19] = {"when": "never (0x00565750 returns false)"}
    for m, d in out.items():
        d["ev"] = TIP_EV[m]
    return out


def main():
    e = Emu()
    vis = visible_lists(e)
    probs = problem_classes(e)
    fp = footprint_tables()
    names = json.load(open(os.path.join(ROOT, "data", "play", "ui.json")))["overlays"]["names"]
    column = {                                    # id: (field, divisor, style, exe draw fn) read in the disassembly
        5: ("coverage.water", 10, 2, "0x00560410: n = b+0x77 (water) / 10; elite houses 10"),
        6: ("coverage.healer", 10, 0, "0x00560680: n = b+0x78 (healer) / 10; + SPR_HOUSE_ATE_FOOD at (x+20, y) if b+0x7F"),
        7: ("risk", 100, 1, "0x00560B00: n = max(fire b+0x48, damage b+0x46) / 100, anchor part only"),
        8: ("unrest", 10, 1, "0x00561230: n = b+0xF4 (unrest) / 10"),
        9: ("tax_days", 5, 0, "0x00561450: n = b+0x4E (tax coverage) / 5"),
        10: ("culture", 10, 0, "0x00561930: n = b+0x80 (culture points) / 10"),
        11: ("coverage.competition", 10, 0, "0x00562AF0: n = b+0x6C / 10"),
        12: ("coverage.philosophy", 10, 0, "0x00561D40: n = b+0x6D / 10"),
        13: ("coverage.athletics", 10, 0, "0x00562040: n = b+0x6F / 10"),
        14: ("coverage.drama", 10, 0, "0x00562750: n = b+0x71 / 10"),
        15: ("sanctuary_activity", 2, 0, "0x00562E70: n = sanctuary b+0x32 / 2 on its column part (0x004EA390)"),
    }
    kinds = {1: "supplies", 2: "problems", 3: "problems", 4: "supplies", 17: "appeal", 18: "problems", 19: "none", 16: "none"}
    modes = {}
    for m in range(1, 20):
        b, f = vis[m]
        d = {"name": names[str(m)], "buildings": b, "walkers": f,
             "last_pass": bool(e.call(e.method(m, 8), [], e.this(m))),
             "terrain_flat": {16: 0x20, 17: 0x4000}.get(m, 0x4020)}
        if m in column:
            fld, div, style, ev = column[m]
            d.update(kind="column", field=fld, div=div, style=style, ev=ev)
        else:
            d["kind"] = kinds.get(m, "none")
        modes[m] = d
    modes[7]["visible_if"] = "risk >= 100 (fire or damage) or burning (0x00560960)"
    modes[18]["visible_if"] = "any problem bit of its class (0x00564840)"
    modes[2]["visible_if"] = modes[3]["visible_if"] = "type list; problem panel when a bit of its class is set (0x00560130)"
    modes[16]["note"] = ("elite houses (types 9..14, +0x0C 0x00563150) get the soldiers pad instead of a footprint "
                         "(0x00563240, `security_elite`); walls stay")
    modes[19]["visible_if"] = "avenue/boulevard only on road tiles (0x00565700)"
    out = {
        "_doc": "Generated by tools/play_overlays.py from Zeus.exe (docs/play/pages.md). Building types are zeus ids "
                "(data/buildings.json zeus_id), walker types are the exe's figure types (role_figures maps ours).",
        "view_table": hex(VIEW_TABLE), "modes": modes,
        "role_figures": figure_roles(),
        "always_visible_note": "0x0055EE70: agoras 63/64, avenue 118, boulevard 126 and pyramids 100..114 are never flattened",
        "footprint": {
            "ev": "0x0044B050: size 1 -> SPR_FOOT_PRINT1[0] (houses SPR_FOOT_PRINT2[0]); size n -> SPR_FOOT_PRINT1_NW + off "
                  "(houses SPR_FOOT_PRINT2_NW), off -1 = SPR_FOOT_PRINT1[1] (interior); tiles [i, j, off] from the min corner",
            "single": atlas_group("Zeus_Terrain", "SPR_FOOT_PRINT1"), "single_house": atlas_group("Zeus_Terrain", "SPR_FOOT_PRINT2"),
            "nw": atlas_group("Zeus_Terrain", "SPR_FOOT_PRINT1_NW"), "nw_house": atlas_group("Zeus_Terrain", "SPR_FOOT_PRINT2_NW"),
            "tiles": fp,
            "rule": "general w x h (checked against every table): (0,0) 0 top, (w-1,0) 2, (w-1,h-1) 4, (0,h-1) 6, "
                    "edges j=0 1, i=w-1 3, j=h-1 5, i=0 7, inside -1"},
        "column": {
            "ev": "0x0055EC00(n, x, y, style): n clamped to 10; colour c = 12 for style 2, 0 for style 0, style 1: n>=9 9, "
                  ">=7 6, >=5 3 else 0; base (c+2) at (x+9, y-8); n>=1: top (c) at (x+5, y-10n-top_h+15) and n-1 middles "
                  "(c+1) at (x+17, y-5-10k); x, y = top-left of the anchor tile (the left tile (x, y+h-1)), raised",
            "sprite": atlas_group("Zeus_Interface", "SPR_OV_PILLARS")},
        "supplies": {
            "ev": "0x0055F5A0: background at (x+11, y-16): SPR_OVERLAY_SLOT3 (common, 3 slots) / SPR_OVERLAY_SLOT6 (elite); slot i "
                  "at (x+21+26i, y-6) when the house needs it now or at the next level (house_param 0x00433D80); icon "
                  "SPR_SUPPLY_OK, or when stock <= low[level][i] (0x0055F440) blinking SPR_SUPPLY_LOW_ON/OFF every 512 ms; "
                  "icon index by good (0x0055F3E0): fleece 0, armor 1, food 2, oil 3, wine 4, horses 5",
            "bg3": atlas_group("Zeus_General", "SPR_OVERLAY_SLOT3"), "bg6": atlas_group("Zeus_General", "SPR_OVERLAY_SLOT6"),
            "ok": atlas_group("Zeus_General", "SPR_SUPPLY_OK"), "low_on": atlas_group("Zeus_General", "SPR_SUPPLY_LOW_ON"),
            "low_off": atlas_group("Zeus_General", "SPR_SUPPLY_LOW_OFF"),
            "slot_goods": ["food", "fleece", "olive_oil", "armor", "wine", "horses"],
            "slot_needs": ["food_types", "fleece", "oil", "arms", "wine", "horses"],
            "icon": {"fleece": 0, "armor": 1, "food": 2, "olive_oil": 3, "wine": 4, "horses": 5},
            "exe_tables": supply_tables()},
        "problems": {
            "ev": "0x00565030: background at (x, y), icons from (x+k, y+k) (k 2 houses, 10 others), 26 px per slot; "
                  "icon = SPR_PROBLEM_ICONS[bit]; bits from building_status_flags 0x00564560",
            "bits": {"0": "house devolving (0x00484660 returns -1: below its own level)", "1": "house empty", "2": "unrest > 80", "3": "plague",
                     "4": "fire risk > 800", "5": "collapse risk > 800", "6": "no workers / no labor access",
                     "7": "short of workers", "8": "production halted", "9": "short of raw material (stock < 100, 400 sculpture)",
                     "10": "sanctuary idle (activity < 5)", "11": "walker icon: cart waiting (0x00564B00)"},
            "classes": [{"class": CLASS_OF_BITS.get(k, "other"), "types": v, "bits": list(k)} for k, v in probs.items()],
            "slots": {k: slot_list(a) for k, a in (("house", 0x641D8C), ("workshop", 0x641DBC), ("producer", 0x641DEC),
                                                   ("sanctuary", 0x641E1C), ("other", 0x641E4C))},
            "bg": {"house": atlas_group("Zeus_General", "SPR_OVERLAY_SLOT4"), "workshop": atlas_group("Zeus_General", "SPR_OVERLAY_SLOT3"),
                   "producer": atlas_group("Zeus_General", "SPR_OVERLAY_SLOT3"), "sanctuary": atlas_group("Zeus_General", "SPR_OVERLAY_SLOT1"),
                   "other": atlas_group("Zeus_General", "SPR_OVERLAY_SLOT1")},
            "icons": atlas_group("Zeus_General", "SPR_PROBLEM_ICONS")},
        "security_elite": dict(atlas_group("Zeus_Terrain", "SPR_ELITE_OVERLAY"), ev=(
            "0x00563240 (See security, per elite house on its image-2 quadrant): image 0 pad (iso 4) at (x+0x1E, "
            "y-0x4B), then rows of 1 spare armour, 2 unarmed, 5 spare horses, 4 chariots, 3 hoplites (packed 0xACA + 3); "
            "counts 0x00563180; viewer/play/overlays.js securityPad")),
        "hygiene_food": {"ev": "0x00560680: drawn at (x+20, y) when the house ate (b+0x7F)",
                         "sprite": atlas_group("Zeus_General", "SPR_HOUSE_ATE_FOOD")},
        "appeal": {
            "ev": "0x0044B830: buildable or built tiles (flags & 0x15361667 == 0, or 0x8) with desirability != 0 or a building/"
                  "garden: SPR_DES_HOUSE (house tiles) / SPR_DES_NOHOUSE [d <= -11: 0, d < 70: d/10 + 2 (C division), else 9]; "
                  "wall tiles SPR_IN_FILL1[rand & 7]; other tiles keep their image; buildings not in the list are flattened",
            "house": atlas_group("Zeus_Terrain", "SPR_DES_HOUSE"), "other": atlas_group("Zeus_Terrain", "SPR_DES_NOHOUSE"),
            "wall": atlas_group("Zeus_Terrain", "SPR_IN_FILL1")},
    }
    p = Probe(e)                                  # after the lists above: it changes the emulator's tables
    mm, tt = minimap_rules(e, p), tooltip_rules(e, p)
    for m, d in modes.items():
        d["minimap"] = mm[m]
        d["tooltip"] = tt.get(m, {"when": "none"})
    texts = json.load(open(os.path.join(ROOT, "extracted", "text", "zeus_text.json")))
    used = sorted({(int(g), int(i)) for g, i in re.findall(r"\{(\d+):(\d+)\}", json.dumps(tt))} | {(23, k) for k in (43, 14, 20, 18, 21, 15)}
                  | {(66, k) for k in list(range(0, 17)) + list(range(77, 100))})
    out["minimap"] = {
        "ev": "minimap_draw 0x00454980: with an overlay on (0x00FA05F0 != 0) a building's draw tile (draw byte 0x40) gets "
              "the image from the view object's +0x24 (0x0055F250, all overlays) instead of its per-type group; burning "
              "tint off. 0x0055F250: avenue 118 / boulevard 126 / agoras 63, 64 -> SPR_R_ROAD; else +0x28 true -> red "
              "(SPR_R_FIRST_BUILD+10); else +0x30 -> green (+5); else +0x2C -> purple (+20); else black (+60, the same "
              "image the normal minimap uses for walls). The piece size picks image + n as for normal buildings "
              "(ui.json minimap.buildings.rule; for the road colour image + n runs into the next groups, sic).",
        "order": ["road", "red", "green", "purple", "black"],
        "palette": colour_palette(),
        "appeal": {
            "ev": "overlay 17 only, before figures and buildings: tile flags & 8 or desirability != 0 -> k = 0x0044BCF0 "
                  "(d <= -11: 0, d < 70: d/10 + 2 (C division), else 9; the main view's SPR_DES_* index), image "
                  "SPR_R_LAVA + 8 + 5k (palette.appeal[k]); other tiles: normal terrain",
            "group": "SPR_R_LAVA"},
        "figures": "0x00454920: a tile's figures give a dot only if the overlay's walker test (+0x10, modes[id].walkers) "
                   "holds for one of them (or figure type 6 with b+0x16C in 1..9); the normal map's extra types "
                   "22/23/27/29 are dotted only with no overlay. Dot colours unchanged (ui.json minimap.figures).",
        "terrain": "unchanged by overlays (except appeal); walls stay SPR_R_FIRST_BUILD+60",
    }
    out["tooltip"] = {
        "ev": "game_turn calls 0x004F6A10 every frame (no delay): needs mouse help on (0x00F2A7B4 != 0, Options; "
              "default 2), no UI widget under the mouse (0x00781834 <= 0), right button up, city screen, not the "
              "editor, a map tile under the mouse (0x00DA2F6C = tile from the mouse, 0x0044A270: the ground diamond, "
              "not the sprite) and an overlay on; then +0x1C(tile, buf 0x00EF7F70) builds the text; true -> drawn "
              "by tooltip_draw 0x004F6E40 this frame",
        "box": "width w = 220; text_layout width 190 (font 9DKBU, 0x00EF8C9C); if more than 2 lines: w = 300, width 270. "
               "h = lines*16 + 10. x = mouse_x + 20 if mouse_x < w + 20 else mouse_x - w - 20 (normally LEFT of the "
               "mouse); y = mouse_y + 50, or mouse_y - 72 when mouse_y >= 200. Outline rect (x, y, w+20, h) colour "
               "0x0084 (555) / 0x0104 (565) = rgb(0,33,33); fill (x+1, y+1, w+18, h-2) 0x09B2 (555) / 0x1372 (565) = "
               "rgb(16,107,148); text at (x+5, y+7), width w-30. '@L' ends a line.",
        "token": "{group:index} = extracted/text/zeus_text.json group/index; a leading number is the value printed by "
                 "number_to_text 0x00508540",
        "texts": {"%d:%d" % (g, i): texts[str(g)][i] for g, i in used},
    }
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print("wrote", OUT, {m: (len(d["buildings"]), len(d["walkers"])) for m, d in modes.items()})


if __name__ == "__main__":
    main()
