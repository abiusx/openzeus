"""The exe's event messages by phrase id (data/messages.json from tools/build_messages.py).

The exe posts a message (FUN_00521A70) as a record of phrase ids, title and announcement among them; the texts come
from Model/Zeus eventmsg.txt. `post(g, title, body, ...)` adds one line "Title. Announcement" to the city's
messages with the variables filled in: [player_name] (PLAYER: "Ruler", or the leader name play mode posts to /control {player}, sim/live.py), [city_name],
[leader_name], [nationality] (text group 37 by the city's nationality).
"""
import json
import os

from .data import DATA_DIR

PLAYER = "Ruler"
_cache = {}


def _data():
    if not _cache:
        _cache.update(json.load(open(os.path.join(DATA_DIR, "messages.json"))))
    return _cache


def condensed(pid):
    """The announcement's condensed text (the panel's message strip, FUN_00430D80) or None: phrase id -> its
    condensed phrase by FUN_00477D60 (data/messages_condensed.json from tools/build_messages_condensed.py)."""
    if "condensed" not in _cache:
        p = os.path.join(DATA_DIR, "messages_condensed.json")
        _data()
        _cache["condensed"] = json.load(open(p)) if os.path.exists(p) else {"map": {}, "texts": {}}
    c = _cache["condensed"]
    cid = c["map"].get(str(pid))
    return c["texts"][str(cid)][1] if cid is not None else None


STRIP_CHARS = 200     # FUN_00430D80 -> FUN_00466AD0(.., buf 0x00916AF8, 200) -> FUN_00505690 writes <= 200 chars


def strip_text(c, **kw):
    """The strip's text: the condensed phrase filled (FUN_00466AD0 sets 0x00916DF1, so [reason_phrase] is the
    reason's condensed phrase too, wm_sub_465EF0: pass it in kw; condensed_reason), cut at 200 characters."""
    return fill(c, **kw)[:STRIP_CHARS]


def condensed_reason(pid, **kw):
    """[reason_phrase] in the strip (wm_sub_465EF0 with 0x00916DF1 set -> FUN_00466AD0(reason)): the reason
    phrase's CONDENSED phrase (FUN_00477D60), filled; "" when it has none (the buffer stays empty). The message
    window's full text uses the full reason (FUN_00466970). Bug 461: ours put the full reason in the strip."""
    c = condensed(pid) if pid is not None and pid >= 0 else None
    return fill(c, **kw) if c is not None else ""


def text(pid, **kw):
    return fill(_data()["phrases"][str(pid)][1], **kw)


def fill(s, city=None, nation=None, player=None, **extra):
    """A phrase text with its variables filled in."""
    nat = _data()["nationality"]
    if nation is None and city is not None:
        nation = getattr(city, "nation", 0)
    vals = {"player_name": player or PLAYER,
            "city_name": getattr(city, "name", "") if city is not None else "",
            "leader_name": getattr(city, "leader", "") if city is not None else "",
            "greeting": (_data()["history"].get("greeting") or [""])[0],   # wm_sub_465B10: "O great" (bugs.md 328)
            "nationality": nat[nation] if nation is not None and 0 <= nation < len(nat) else ""}
    vals.update({k: str(v) for k, v in extra.items()})    # e.g. amount, item, itemshort (offers)
    lead = s.startswith("[reason_phrase]")
    for k, v in vals.items():
        s = s.replace(f"[{k}]", v)
    if lead and s[:1].islower():           # "Because you failed to send me ..." (oracle 1L5-requests m075: the
        s = s[0].upper() + s[1:]           # reason phrases start lower case, the message's first letter is upper)
    return s


def history(pid, rel=0, item=None):
    """A world-map history row's text (FUN_004669E0 for record +8): the phrase with [city_affected] = text group 91 by
    the record's relation byte (0 "this city", 1 "an ally", 2 "a rival", 3 "a vassal", 4 "a colony", 5 "your parent
    city"; wm_sub_466780) and [itemshort] = group 23 by the record's item id (wm_sub_465E00). item: a good name or
    an exe item id."""
    from .empire.model import GOOD_IDS
    h = _data()["history"]
    iid = GOOD_IDS.get(item, -1) if isinstance(item, str) else (-1 if item is None else item)
    s = _data()["phrases"].get(str(pid), (None, "N/A"))[1]   # build_messages leaves the "N/A" texts out (0x3E2)
    names = h["itemshort"]
    return (s.replace("[city_affected]", h["city_affected"][rel] if 0 <= rel < len(h["city_affected"]) else "")
             .replace("[itemshort]", names[iid] if 0 <= iid < len(names) else ""))


def item_words(item):
    """The offer texts' [item] and [itemshort] for a good name or an exe item id: [item] = text group 98, the unit
    phrase ("amphorae of wine", wm_sub_465DA0), [itemshort] = group 23 ("Wine", wm_sub_465E00); variable table
    0x005FBA68 / 0x005FBC00. Unknown items keep their own name."""
    from .empire.model import GOOD_IDS
    h = _data()["history"]
    iid = GOOD_IDS.get(item, -1) if isinstance(item, str) else (-1 if item is None else item)
    name = str(item).replace("_", " ")
    long, short = h.get("item", []), h["itemshort"]
    return (long[iid] if 0 < iid < len(long) else name), (short[iid] if 0 < iid < len(short) else name)


def line(title, body, **kw):
    t, b = text(title, **kw), text(body, **kw)
    return f"{t} {b}" if t[-1:] in "!?." else f"{t}. {b}"


class Msg(str):
    """A message line that also carries what the exe's message window shows (viewer/play/msgwin.js): title, body,
    the filter category (Model/Zeus event message categories.txt by the announcement phrase, FUN_00521970) and
    whether it pops up (the poster sets DAT_00FD36EC; the Messages options decide Full / Condensed / Off).
    Pickles and compares as its text; export.py adds the meta to state.json's message."""
    def __new__(cls, text, meta=None):
        o = super().__new__(cls, text)
        o.meta = dict(meta or {})
        return o

    def __reduce__(self):
        return (Msg, (str(self), self.meta))


def category(pid):
    return _data().get("categories", {}).get(str(pid), 19)


def post(g, title, body, popup=True, voice=None, meta=None, condensed_vars=None, **kw):
    """One message: the exe's title + announcement phrases (ids as in the exe's message record); it pops up in the
    message window (type 0 record 224 look) unless its category is set to Condensed or Off. voice: an Audio/ file the
    poster plays with it (a god's line, FUN_005A1050; play mode plays it when the message first arrives). meta: more
    fields for the message window (a request's record type 2, good, amount, months, button flags: sim/empire)."""
    t, b = text(title, **kw), text(body, **kw)
    extra = meta
    meta = dict(title=t, body=b, phrase=body, category=category(body), popup=popup, **(extra or {}))
    if voice:
        meta["voice"] = voice
    c = condensed(body)
    if c is not None:                                      # the panel strip's line (FUN_00430D80)
        meta["condensed"] = strip_text(c, **dict(kw, **(condensed_vars or {})))
    g.message(Msg(line(title, body, **kw), meta))
