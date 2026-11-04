"""Adventure and episode flow as the exe plays it (track 1L-3; docs/campaign-format.md "The campaign module").

Files, next to the player's save SAVE (ours; the exe keeps one of each per player in its save folder):
  SAVE                 the game being played
  <SAVE>.parent<ext>   parent.dat: the parent city saved at the end of every won episode (episode_end_save_parent
                       0x0052D2B0); colony and continue starts load it
  <SAVE>.replay<ext>   autosave_replay.sav: the game as the episode started (autosave_if_due 0x005123D0 right after
                       episode_start_load); the defeat screen's "Replay episode" loads it (0x00421730)

The flow (exe addresses in docs/campaign-format.md):
  start(adventure, slot)   a new city (record +0x58 = 0) on the parent map; slot 0 unless asked
  next_step(g)             what Proceed does now: {"kind": "episode" | "colony" | "end", ...}
  proceed(g, save, colony) the victory screen's Proceed (0x0052DA50): the end-of-episode events (wm_sub_471E90),
                           episode_end_save_parent, then episode_won_advance 0x00421920 / episode_next_slot
                           0x00422FC0: next 3 = the adventure is won (the last episode's screen 0x43 also offers
                           "Continue building this city": stay=True); next 1 = the colony choice (a colony city of
                           the empire not founded yet, colony_choice_click 0x00421AF0; colony n plays slot 9+n and
                           the slot that led there is kept, 0x00F2A7B2); after a colony the parent continues at that
                           slot + 1; else slot + 1. Returns the next episode's game (or g when the adventure ends).
  replay(save)             the episode's start again (the defeat screen's Replay episode)
"""
import json
import os

from .. import episode, hooks
from . import goals as G

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOK = "sim.campaign.goals:day"


class Choice(Exception):
    """Proceed needs the player's colony choice: .options = [(n, city id, name)]."""

    def __init__(self, options):
        super().__init__("choose a colony: " + ", ".join(f"{n} {name}" for n, _, name in options))
        self.options = options


# --- the adventures --------------------------------------------------------------------------------------------------

def index():
    return json.load(open(os.path.join(ROOT, "data", "campaign", "index.json")))["adventures"]


def load(aid):
    p = os.path.join(ROOT, "data", "campaign", f"{aid}.json")
    if not os.path.exists(p):
        raise ValueError(f"no adventure {aid!r} (`campaign list`)")
    return json.load(open(p))


def playable(a):
    """'' when the adventure can be started here, else why not."""
    if a.get("game") != "zeus":
        return "Poseidon adventure (Poseidon is off; stage 3)"
    return ""


def episode_rec(a, slot):
    ep = next((e for e in a["episodes"] if e["slot"] == slot), None)
    if ep is None:
        raise ValueError(f"{a['id']} has no episode in slot {slot} (slots: {[e['slot'] for e in a['episodes']]})")
    ep = dict(ep)
    ep.setdefault("source", a["source"])
    return ep


def map_of(a, slot):
    """The episode's map container: the parent map (0) for slots 0..9, colony n's (9 + n) for its slot."""
    if slot < 10:
        return f"{a['source']}#0"
    col = next(c for c in a["colonies"] if c["slot"] == slot)
    return f"{a['source']}#{col['map']}"


def episode_of(g):
    st = g.campaign
    return episode_rec(load(st["adventure"]), st["slot"])


def files(save):
    base, ext = os.path.splitext(save)
    return dict(parent=f"{base}.parent{ext or '.pkl'}", replay=f"{base}.replay{ext or '.pkl'}")


# --- starting an episode ---------------------------------------------------------------------------------------------

def _begin(g, a, ep, prev=None, colony=None, won=0):
    """What every start does for the campaign: the goal table (goals_load_episode), the result flags cleared
    (0x00FEB160 = -1, 0x00F2A6DB / 0x00F2A6DC = 0, 0x00FEB168 = 0, 0x00FEAF28 = 0), the month check attached."""
    g.campaign = dict(adventure=a["id"], slot=ep["slot"], prev=prev, colony=colony, won=won,
                      goals=G.records(ep), result=0, lost=None, forced=False, stay=False, done=False,
                      briefed=False)          # 1L-4: the briefing screen (0x35) is up until "To the city"
    m = g.__dict__.get("mil")
    if m and m.get("game_lost"):                    # a sack in an earlier episode does not lose this one
        m["game_lost"] = False
    hooks.attach(g, "day", HOOK)
    return g


def start(aid, slot=None, seed=1, difficulty=None):
    """A new adventure (or one of its new-city episodes): start kind 0 on the parent map."""
    a = load(aid)
    why = playable(a)
    if why:
        raise ValueError(f"{aid}: {why}")
    if a.get("tutorial"):                         # tutorial_load_save 0x005BEBD0: the tutorial's start save, its slot
        from .. import savimport
        path = os.path.join(ROOT, a["tutorial"]["start_save"])
        g = savimport.load(path, seed=seed, difficulty=difficulty)
        return _begin(g, a, episode_rec(a, g.sav["slot"]))
    slot = 0 if slot is None else slot
    ep = episode_rec(a, slot)
    if ep["start"] != "new_city":
        starts = [e["slot"] for e in a["episodes"] if e["start"] == "new_city"]
        raise ValueError(f"slot {slot} starts as '{ep['start']}' (it needs the city of the episode before); "
                         f"new-city slots: {starts}")
    g = episode.new_city(map_of(a, slot), ep, seed=seed, difficulty=difficulty)
    return _begin(g, a, ep)


# --- after a victory ------------------------------------------------------------------------------------------------

def colony_options(g):
    """colony_choice_click 0x00421AF0: colony n = 1..4 (colony_index_nth: the n-th kind-1 city of the empire) not
    active yet and with a map in the adventure."""
    a = load(g.campaign["adventure"])
    e = g.empire
    cols = [c for _, c in sorted(e.cities.items()) if c.kind == "colony"] if e is not None else []
    out = []
    for n in range(1, 5):
        if n > len(cols) or cols[n - 1].active:
            continue
        if any(c["n"] == n and c.get("map") is not None for c in a["colonies"]):
            out.append((n, cols[n - 1].id, cols[n - 1].name))
    return out


def next_step(g):
    st = g.campaign
    if st.get("done"):
        return dict(kind="done", text="the adventure is complete")
    if st["result"] < 0:
        return dict(kind="lost", text="defeat: `campaign replay SAVE` plays the episode again from its start")
    if st["result"] == 0:
        return dict(kind="play", text="play on: the goals are judged at every month change")
    if st.get("stay"):
        return dict(kind="stay", text="continuing to build this city after the last episode")
    ep = episode_of(g)
    if ep["slot"] >= 10:
        a = load(st["adventure"])
        return dict(kind="episode", slot=st["prev"] + 1,
                    text=f"Proceed: back to the parent city, episode slot {st['prev'] + 1} "
                         f"({_title(episode_rec(a, st['prev'] + 1))})")
    if ep["next"] == "end":
        return dict(kind="end", text="Proceed: the adventure is won (or `--stay`: continue building this city)")
    if ep["next"] == "colony":
        return dict(kind="colony", options=colony_options(g),
                    text="Proceed: choose a colony: " + ", ".join(f"{n} {name}" for n, _, name in colony_options(g)))
    a = load(st["adventure"])
    return dict(kind="episode", slot=ep["slot"] + 1,
                text=f"Proceed: episode slot {ep['slot'] + 1} ({_title(episode_rec(a, ep['slot'] + 1))})")


def _title(ep):
    """The episode's title for the CLI lines: its intro record's (the custom adventures' come from their .txt texts,
    sim/campaign/texts.py: no record, bugs.md)."""
    return (ep.get("intro") or {}).get("title") or f"episode {ep['slot']}"


def end_save_parent(g, parent_path):
    """episode_end_save_parent 0x0052D2B0: in a colony (record +0x58 = 1) the parent city comes back from
    parent.dat with the colony's empire, treasury and date (colony kind 1, tribute 1, parent kind 0; the colony-
    founded flag 0x00902C04 = 1); in a parent episode the city itself. Saved as parent.dat; returns that game."""
    from ..game import Game
    ep = episode_of(g)
    if ep["start"] == "colony":
        blob = g.campaign.get("parent_dat")
        if blob:                                   # game_file_load 0x0050E610 of a colony save (slot > 9) writes the
            with open(parent_path + ".tmp", "wb") as f:     # parent.dat it carries back to the file
                f.write(blob)
            os.replace(parent_path + ".tmp", parent_path)
        p = Game.load(parent_path)
        p = episode.back_from_colony(p, g, g.campaign["colony"])
        p.campaign = dict(g.campaign, colony_founded=g.campaign["colony"])
        p.campaign.pop("parent_dat", None)
    else:
        p = g
        p.campaign["colony_founded"] = None
    p.save(parent_path)
    return p


def proceed(g, save, colony=None, stay=False):
    """The victory screen's Proceed (0x0052DA50). Returns the game to play next (saved by the caller)."""
    from ..game import Game
    st = g.campaign
    if st["result"] != 1 or st.get("stay") or st.get("done"):
        raise ValueError("Proceed is offered after a victory only (`campaign status`)")
    ep = episode_of(g)
    a = load(st["adventure"])
    nxt = next_step(g)
    if nxt["kind"] == "colony":                    # check the choice before anything is changed
        opts = nxt["options"]
        if colony is None:
            raise Choice(opts)
        pick = next((o for o in opts if str(colony).lower() in (str(o[0]), o[2].lower())), None)
        if pick is None:
            raise ValueError(f"{colony!r} is not a colony that can be founded now: "
                             + (", ".join(f"{n} {name}" for n, _, name in opts) or "none"))
    if stay and nxt["kind"] != "end":
        raise ValueError("'continue building this city' is offered after the last episode only")
    from .. import scenario
    scenario.episode_end(g)                       # wm_sub_471E90: the events flagged for the episode's end
    paths = files(save)
    p = end_save_parent(g, paths["parent"])
    if nxt["kind"] == "end":                       # FUN_00421900: next 3 -> screen 0x43
        if stay:                                   # 0x00567820: 0x00FEAF28 = 1, goals no longer judged
            g.campaign["stay"] = True
            return g
        g.campaign["done"] = True                  # episode_won_advance: adventure won (0x004FDEF0)
        g.campaign["won"] = st.get("won", 0) + 1
        return g
    won = st.get("won", 0) + 1                     # 0x00F2A7C0
    if nxt["kind"] == "colony":
        n, cid, _ = pick
        slot = 9 + n
        cep = episode_rec(a, slot)
        new = episode.colony(p, map_of(a, slot), cep, cid, seed=p.seed, difficulty=p.difficulty)
        _begin(new, a, cep, prev=ep["slot"], colony=cid, won=won)
        with open(paths["parent"], "rb") as f:     # game_file_save 0x0050E2C0 in a colony (slot > 9) appends
            new.campaign["parent_dat"] = f.read()  # parent.dat (up to 500000 bytes): every colony save has it
        return new
    slot = nxt["slot"]
    nep = episode_rec(a, slot)
    if nep["start"] == "new_city":
        new = episode.new_city(map_of(a, slot), nep, seed=p.seed, difficulty=p.difficulty)
        return _begin(new, a, nep, prev=ep["slot"], won=won)
    new = Game.load(paths["parent"])               # continue: parent.dat as saved, then the episode's switches
    founded = (new.campaign or {}).get("colony_founded") if "campaign" in new.__dict__ else None
    episode.resume(new, nep)
    _begin(new, a, nep, prev=ep["slot"], won=won)
    if founded is not None:                        # FUN_0041FE40 (entering the city with 0x00902C04 = 1): the colony
        from .. import messages                    # monument message and a commemorative monument (kind 3)
        from ..systems import commemorative
        c = new.empire.cities.get(founded) if new.empire is not None else None
        messages.post(new, 0x51A, 0x51B, last_colony=c.name if c else "")   # [last_colony]: wm_sub_466850
        commemorative.grant(new, 3)
    return new


def replay(save):
    from ..game import Game
    p = files(save)["replay"]
    if not os.path.exists(p):
        raise ValueError(f"no replay file {p} (written when an episode starts through `campaign start` / `next`)")
    return Game.load(p)


# --- status -----------------------------------------------------------------------------------------------------------

def status(g):
    """A plain dict for the CLI and later screens (1L-4)."""
    st = g.campaign
    a = load(st["adventure"])
    ep = episode_rec(a, st["slot"])
    in_colony = ep["start"] == "colony"
    rows = []                                      # goals_status_update 0x0052B7D0: the counters as of the last check
    for i, r in enumerate(st["goals"]):
        what, now = G.describe(g, r, in_colony)
        ok = (not G.year_reached(g, r)) if r["type"] == 12 else G.met(g, dict(r, v=list(r["v"])))
        rows.append(dict(n=i + 1, type=r["type"], name=G.NAMES[r["type"]] if r["type"] < len(G.NAMES) else "?",
                         goal=what, now=now, met=ok))
    return dict(adventure=a["id"], title=a.get("brief", {}).get("title") or a["name"], slot=st["slot"],
                number=ep["number"], role=ep["role"], start=ep["start"], intro=(ep.get("intro") or {}).get("title"),
                date=g.date(), result=st["result"], lost=st.get("lost"), goals=rows, next=next_step(g))


def briefing(g, which="intro"):
    """The episode's briefing (or victory) text: Zeus_MM.eng record body (data/play/help.json records[id][15])."""
    ep = episode_of(g)
    rec = ep.get(which) or {}
    if not rec.get("id"):
        return ""
    h = json.load(open(os.path.join(ROOT, "data", "play", "help.json")))["records"]
    r = h[rec["id"]] if rec["id"] < len(h) else None
    body = r[15] if r and len(r) > 15 else ""
    import re
    return f"{rec.get('title', '')}\n" + re.sub(r"@[A-Z]", "\n", body).strip()


# --- the screens (track 1L-4; docs/play/campaign.md) -----------------------------------------------------------------
# The screen a campaign game is on, as the exe shows it (the live server pauses the city while one is up):
#   briefing  the episode start screen 0x35 (0x0052E520) until "To the city" (flow.briefed)
#   tutorial  a tutorial's start: its goals screen 0x3B with the tutorial buttons (objectives_screen_draw 0x0052C070
#             while 0x006AA4CC == 2; oracle 1L5-tut00 start.bmp) until a right click (flow.briefed)
#   victory   screen 0x42 (FUN_0052D590) from the month check that won until Proceed
#   complete  screen 0x43 (FUN_0052D7C0) after Proceed on the last episode until "Continue building this city"
#   defeat    screen 0x33 (FUN_00422AB0 on fullscreen_background_b 0x00422270) from the next day's check after
#             the loss (0x00FEB164 defers the first defeat of a session by a day; ours: every one)
#   None      the city

def screen(g):
    st = g.__dict__.get("campaign")
    if not st:
        return None
    if not st.get("briefed", True):
        return "tutorial" if load(st["adventure"]).get("tutorial") else "briefing"
    if st.get("stay"):
        return None
    if st.get("done"):
        return "complete"
    if st["result"] == 1:
        return "victory"
    if st["result"] < 0 and g.tick >= st.get("defeat_at", 0):
        return "defeat"
    return None


def briefed(g, difficulty=None):
    """The briefing's "To the city" (0x0052E500 -> the city), with the difficulty its arrows chose
    (sim/episode.py set_difficulty)."""
    if difficulty:
        from .. import episode
        episode.set_difficulty(g, difficulty)
    g.campaign["briefed"] = True


def continue_building(g):
    """0x43's "Continue building this city" (0x00567820): 0x00FEAF28 = 1 (goals no longer judged), back to the
    city; the city then shows the top-left line "You have already won this adventure, and have chosen to continue
    governing" (oracle 1L4-complete after.bmp; not ported)."""
    st = g.campaign
    if not st.get("done"):
        raise ValueError("'continue building this city' is offered after the adventure is won")
    st["done"], st["stay"] = False, True


ORDER_PREFIX = "#&@[]^{}"


def list_name(a):
    """The adventure list's row: the .pak name without its sort prefix (s32: "Hercules Labors", not the record's
    "Hercules' Labors")."""
    n = a["name"]
    return n[1:] if n[:1] in ORDER_PREFIX else n


def custom_texts(a):
    """A custom adventure's texts (a folder adventure: the editor's DIR/NAME.txt, `key="text"`): Adventure_Title /
    _Introduction / _Complete, Parent_Episode_N_Title / _Introduction / _Complete, Colony_N_Title / _Introduction /
    _Complete / _Selection. {} for the original adventures (their texts are Zeus_MM.eng records)."""
    if a.get("kind") != "folder":
        return {}
    import re
    p = os.path.splitext(os.path.join(ROOT, a["source"]))[0] + ".txt"
    if not os.path.exists(p):
        return {}
    return dict(re.findall(r'^(\w+)="(.*?)"', open(p, encoding="latin-1").read(), re.M | re.S))


def episode_texts(a, ep):
    """{title, intro, victory} strings of a custom adventure's episode (Parent_Episode_N_* / Colony_N_*), else {}."""
    T = custom_texts(a)
    if not T:
        return {}
    k = f"Colony_{ep['slot'] - 9}" if ep["slot"] >= 10 else f"Parent_Episode_{ep['number']}"
    return dict(title=T.get(k + "_Title", ""), intro=T.get(k + "_Introduction", ""), victory=T.get(k + "_Complete", ""),
                selection=T.get(k + "_Selection", ""))


# the original Zeus adventures' narration (table FUN_005A73D0 at 0x00F2AB58: audio\voice\campaign\c<n>_e<m>_i / _v,
# c<n>_v): adventure n = its complete record (DAT_006B3294, Zeus_MM) - 486 + 1, episode m = the slot + 1 (colonies 11..14)
VOICE_COMPLETE_BASE = 486
# the music stream's loop under the narration (FUN_005A88C0 / FUN_005A8640): Zeus adventures mission_intro (briefing),
# mission_victory (victory), campaign_victory (complete); a custom adventure plays mission_intro on its briefing and
# victory (FUN_005A87A0 / FUN_005A8830 name only that file) and campaign_victory on its complete screen
JINGLES = dict(intro="Music/mission_intro.wav", victory="Music/mission_victory.wav", complete="Music/campaign_victory.wav")


def voices(a, ep):
    """The spoken texts of an adventure's screens (paths for GET /audio/, sim/live.py; those that exist): intro
    (briefing 0x35, FUN_005A88C0(0) from 0x0052E3D0), victory (0x42, FUN_005A88C0(1) from FUN_0052D590), complete
    (0x43, FUN_005A8640 from FUN_0052D7C0); jingles: the music file each plays looped with it (docs/play/campaign.md
    "voices"). Zeus adventures: Voice/Campaign/C<n>_E<m>_i / _v, C<n>_v. Custom adventures: the editor's
    NAME_P<n>_i / _v per parent episode, _C<n>_i / _v per colony, _A_v next to their .pak."""
    out = {}
    if a.get("kind") == "zeus_campaign":
        n = (a.get("complete") or {}).get("id", -1) - VOICE_COMPLETE_BASE
        if not 0 <= n < 7 or not 0 <= ep["slot"] <= 13:
            return {}
        d = os.path.join(ROOT, "zeus-original", "app", "Audio", "Voice", "Campaign")
        for name, f in (("intro", f"C{n + 1}_E{ep['slot'] + 1}_i.mp3"), ("victory", f"C{n + 1}_E{ep['slot'] + 1}_v.mp3"),
                        ("complete", f"C{n + 1}_v.mp3")):
            if os.path.exists(os.path.join(d, f)):
                out[name] = "Voice/Campaign/" + f
        if out:
            out["jingles"] = dict(JINGLES)
        return out
    if a.get("kind") != "folder":
        return {}
    d = os.path.dirname(a["source"])
    base = os.path.splitext(os.path.basename(a["source"]))[0]
    k = f"C{ep['slot'] - 9}" if ep["slot"] >= 10 else f"P{ep['number']}"
    for name, f in (("intro", f"{base}_{k}_i.mp3"), ("victory", f"{base}_{k}_v.mp3"), ("complete", f"{base}_A_v.mp3")):
        if os.path.exists(os.path.join(ROOT, d, f)):
            out[name] = "Adventures/" + os.path.relpath(os.path.join(d, f), os.path.join("zeus-original", "app", "Adventures"))
    if out:
        out["jingles"] = dict(JINGLES, victory=JINGLES["intro"])
    return out


def briefing_rows(g, a, ep):
    """The briefing's goal rows (0x0052E520): goal texts only, every box empty."""
    from . import texts
    recs = G.records(ep)
    for r in recs:
        r["start_year"] = ep.get("start_year", 0)
    return texts.rows(g, recs, colony=ep["start"] == "colony", briefing=True)


def adventures():
    """The new-game screens' lists (viewer/play/newgame.js): Adventures (the exe's original adventures: Zeus
    campaigns by .pak name, Poseidon off), Custom Adventures (the Zeus adventure folders), Tutorials (menu order,
    not playable yet). Each: id, name (list row), brief (Zeus_MM record of the description, 0x8B40), episode (its
    first episode's intro record and goal rows), picture, playable / why."""
    out = dict(adventures=[], custom=[], tutorials=[])
    for x in sorted(index(), key=lambda x: x["name"]):
        a = load(x["id"])
        if a["game"] != "zeus":
            continue
        ep = episode_rec(a, 0)
        e = dict(id=a["id"], name=list_name(a), brief=(a.get("brief") or {}).get("id", -1),
                 intro=(ep.get("intro") or {}).get("id", -1), why=playable(a), episodes=len(a["episodes"]),
                 goals=briefing_rows(None, a, ep), start_year=ep.get("start_year"),
                 picture=a["header"].get("picture", 0))      # the list's picture (table 0x005EBBD8, FUN_004248F0)
        T = custom_texts(a)
        if T:                                     # a custom adventure: its .txt instead of Zeus_MM records
            et = episode_texts(a, ep)
            e["strings"] = dict(title=T.get("Adventure_Title", ""), desc=T.get("Adventure_Introduction", ""),
                                ep_title=et["title"], ep_body=et["intro"])
        v = voices(a, ep)
        if v.get("intro"):
            e["voice"], e["jingle"] = v["intro"], v["jingles"]["intro"]
        if a.get("tutorial"):
            e["index"] = a["tutorial"]["index"]
            out["tutorials"].append(e)
        elif a["kind"] == "folder":
            out["custom"].append(e)
        else:
            out["adventures"].append(e)
    out["tutorials"].sort(key=lambda e: e["index"])
    return out


def tutorial_nav(a):
    """The tutorial buttons of the goals screen (objectives_screen_draw 0x0052C070, table 0x006408D8, texts 293:14..17):
    Previous tutorial when there is one before (FUN_005BEA70: the tutorials in their order, basic 0..7 then
    advanced 8..15), New tutorial, Next tutorial when there is one after (FUN_005BEAC0), Start this tutorial over.
    Returns {index, prev: id | None, next: id | None}."""
    ids = [e["id"] for e in adventures()["tutorials"]]          # in their order (index)
    k = ids.index(a["id"]) if a["id"] in ids else -1
    return dict(id=a["id"], index=a["tutorial"]["index"], prev=ids[k - 1] if k > 0 else None,
                next=ids[k + 1] if 0 <= k < len(ids) - 1 else None)


def top_left(g):
    """The city view's campaign lines (top_left_texts_draw 0x0058F130): after "Continue building this city"
    (0x00FEAF28) the line 6:5 "You have already won this adventure, and have chosen to continue governing"; with a time
    limit goal (type 12; FUN_0052E230) a box (FUN_00509B90(1, 0x28, 0xE6, 0x14, 0x1FE3): x 1, y 40, 230 x 20, the
    pixels ANDed with 0x1FE3) and 6:2 "Months to complete adventure" + the months, else with a survival goal (13;
    FUN_0052E240) the box at (1, 42, 200 x 18) and 6:3 "Months until victory" + the months; months = 12 x max(0,
    target year - year - 1) + 12 - month (target 0x0091EC00 = scenario_start_year + v1). 6:2 in red 0xF800 at (7, 46) over
    a black shadow (x 7..8, y 45 and 47); 6:3 in red at (2, 46), no shadow (play mode: campaign.js drawTopLeft)."""
    st = g.campaign
    out = dict(won=bool(st.get("stay")))
    for t, kind in ((12, "limit"), (13, "survival")):
        r = next((r for r in st.get("goals", []) if r["type"] == t), None)
        if r is not None:
            target = g.__dict__.get("scenario_year", g.start_year) + r["v"][0]
            out.update(kind=kind, months=12 * max(0, target - g.year - 1) + 12 - g.month)
            break
    return out


def screens(g):
    """What the campaign screens draw (GET /campaign.json): the screen, the records (adventure 0x8B40, complete
    0x8B44, the episode's intro +0x64C / victory +0x658), the city, the goal rows, the loss phrase, the colony
    choice."""
    from . import texts
    st = g.campaign
    a = load(st["adventure"])
    ep = episode_rec(a, st["slot"])
    colony = ep["start"] == "colony"
    sc = screen(g)
    city = ""
    e = getattr(g, "empire", None)
    try:
        city = e.player().name if e is not None else ""
    except StopIteration:
        pass
    out = dict(campaign=True, screen=sc, adventure=a["id"], slot=st["slot"], start=ep["start"],
               brief=(a.get("brief") or {}).get("id", -1), complete=(a.get("complete") or {}).get("id", -1),
               intro=(ep.get("intro") or {}).get("id", -1), victory=(ep.get("victory") or {}).get("id", -1),
               city=city, result=st["result"], done=bool(st.get("done")), stay=bool(st.get("stay")),
               goals=texts.rows(g, st["goals"], colony, briefing=sc == "briefing"),
               lost=st.get("lost"), next=next_step(g)["kind"])
    T = custom_texts(a)
    if T:                                         # a custom adventure: its .txt texts (records -1)
        et = episode_texts(a, ep)
        out["strings"] = dict(title=T.get("Adventure_Title", ""), ep_title=et["title"], ep_body=et["intro"],
                              victory_body=et["victory"], complete_title=T.get("Adventure_Title", ""),
                              complete_body=T.get("Adventure_Complete", ""))
    out["voices"] = voices(a, ep)
    out["top_left"] = top_left(g)
    if a.get("tutorial"):
        out["tutorial"] = tutorial_nav(a)
    if st.get("lost"):
        from .. import messages
        out["lost_title"] = messages.text(G.LOSE_TITLE)
        out["lost_text"] = messages.text(st["lost"], city=G._parent_city(g))
    if out["next"] == "colony" and st["result"] == 1:
        # the choice screen's text of a colony (FUN_0042B890: the colony episode's intro record subtitle)
        out["colonies"] = [dict(n=n, id=cid, name=name, text=(episode_rec(a, 9 + n).get("intro") or {}).get("subtitle", "")
                                or (episode_texts(a, episode_rec(a, 9 + n)) or {}).get("selection", ""))
                           for n, cid, name in colony_options(g)]
    return out
