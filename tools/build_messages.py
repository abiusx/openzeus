"""data/messages.json: the exe's event message texts the sim posts (title + announcement, by phrase id).

The exe posts a message (FUN_00521A70, type 0xDE / 0xE0) with a record of phrase ids: +0 the announcement,
+2 the title, +0x10 the reason (e.g. army_withdraws 0x00481E80: 0x445 / 0x442 / 0x444). A phrase id is the
position in the exe's name table at 0x005FBC38 ({u32 id, char *name}, 4172 entries, null name ends it); the text
of a name comes from Model/Zeus eventmsg.txt (read by FUN_00505770: `;` comments to the end of the line, bytes
< 0x21 separate tokens, a token that is a known name (no case) is followed by a "quoted" text; a backslash followed
by blanks and a line break splices the lines; tokens that are not names are skipped). Variables in the texts
([player_name], [city_name], [leader_name], [nationality]) are filled in by sim/messages.py.

    re/venv/bin/python tools/build_messages.py     (needs pefile; reads Zeus.exe, Model/Zeus eventmsg.txt and
                                                    extracted/text/zeus_text.json from tools/engtext.py)

[nationality] = text group 37 by the city's nationality (0 Greek .. 10 Ares' Sparti; wm_sub_465CA0 stores
37:nationality as a text variable; hypothesis that the message variable reads the same slot).
Output: {"nationality": [...], "category_defaults": [20], "categories": {id: message category (Model/Zeus event message
categories.txt, see categories())}, "history": {"city_affected": group 91, "itemshort": group 23, "item": group 98}, "phrases": {id (decimal
string): [name, text]}, ...} for the phrase families in FAMILIES and every *_history phrase (full texts only;
the CONDENSED variants and "N/A" placeholders are left out).
"""
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

NAME_TABLE = 0x005FBC38
EVENTMSG = os.path.join(ROOT, "zeus-original", "app", "Model", "Zeus eventmsg.txt")
CATEGORIES = os.path.join(ROOT, "zeus-original", "app", "Model", "Zeus event message categories.txt")
TEXT = os.path.join(ROOT, "extracted", "text", "zeus_text.json")     # tools/engtext.py (Zeus_Text.eng)
OUT = os.path.join(ROOT, "data", "messages.json")
MONSTERS = ("hydra", "kraken", "cerberus", "cyclops", "minotaur", "medusa", "calydonian_boar", "dragon", "talos",
            "hector", "scylla", "maenads", "sphinx", "chimera", "harpies", "echidna")
GODS14 = ("zeus", "poseidon", "demeter", "apollo", "artemis", "ares", "aphrodite", "hermes", "athena", "hephaestus",
          "dionysus", "hades", "hera", "atlas")
HEROES8 = ("achilles", "hercules", "jason", "odysseus", "perseus", "theseus", "atalanta", "bellerophon")
# phrase name prefixes (after PHRASE_) the sim uses: grants of commemorative monuments and the Panhellenic games
FAMILIES = ("population_", "happiness_monument_", "players_city_saved_", "city_conquered_by_player_", "becomes_ally_",
            "colony_monument_", "olympian_games_", "isthmian_games_", "nemean_games_", "pythian_games_", "home_games_",
            # incoming goods and troops (sim/empire/offers.py: incoming_goods_dialog 0x004745E0)
            "gift_", "rescue_cash_", "request_granted_", "demand_refused_", "raiding_party_returns_", "tribute_paid_", "support_troops_",
            # heroes and monsters (sim/heroes): monster in city / slain, invasions, god quests, hero halls, arrivals
            *[m + "_in_city_" for m in MONSTERS], *[m + "_slain_" for m in MONSTERS], "independent_",
            *[gd + "_unleashes_monster_" for gd in GODS14], *[gd + "_quest" for gd in GODS14],
            *[h + "_hall_available_" for h in HEROES8], *[h + "_arrives_" for h in HEROES8],
            # gods (sim/gods): jealous attack (god_attack_message 0x004F1110), invasion (event_god_attack), help
            *[gd + k for gd in GODS14 for k in ("_wooing0_", "_jealousy1_", "_jealousy2_", "_invades_", "_help_")],
            "oracle_",                                  # Consult Oracle with nothing to foresee (FUN_0047F6C0)
            "lose_",                                    # episode lost (scenario_goals_check 0x00526990, sim/campaign)
            # city status change (event_city_status_change 0x00473680, sim/empire/status_events.py), demand and
            # supply changes (event_demand_increase 0x00472540 ..), a city conquered by a rival (FUN_0046EAC0)
            "trade_suspended_", "trade_resumed_", "trade_shuts_down_", "trade_opens_up_", "demand_change_",
            "supply_change_", "tribute_suspended_", "tribute_resumed_", "rebellion_", "colony_rebellious_",
            "vassal_rebellious_", "becomes_rival_", "becomes_vassal_", "military_change_", "economic_change_",
            "city_active_", "city_inactive_", "city_appears_", "city_disappears_", "ally_conquered_by_rival_",
            "vassal_conquered_by_rival_", "colony_conquered_by_rival_",
            # a city destroyed by a rival or a monster (FUN_00477AB0; the parent city: the episode is lost)
            "ally_destroyed_by_", "vassal_destroyed_by_", "colony_devastated_by_", "parent_city_destroyed_by_",
            *[gd + "_disaster_" for gd in GODS14],
            # scenario requests (event_request 0x00470800, event_troops_request_update 0x0046ED70, sim/empire/requests.py):
            # by kind and tone, the favour change after one (request_resolve_attitude 0x0046FFA0), "you can now
            # fulfil" (0xD15..), the returning forces; invasions (invasion_event_month 0x00476E20); wage, price, favour
            # and rival-army events (sim/empire/city_events.py); the reasons 0..4 (really_benevolent .. weakness)
            "general_request_", "famine_relief_", "building_project_", "great_festival_", "financial_woes_",
            "ally_under_attack_", "vassal_under_attack_", "colony_under_attack_", "parentcity_under_attack_",
            "ally_attacks_rival_", "vassal_attacks_rival_", "ally_terrorized_", "vassal_terrorized_",
            "colony_terrorized_", "parentcity_terrorized_", "favor_change_", "attack_averted_", "monster_scared_off_",
            "got_enough_debens_", "got_goods_stocks_", "legion_returns_", "ally_conquers_rival_",
            "vassal_conquers_rival_", "raiding_party_wiped_out_", "invasion_", "wage_change_", "price_change_",
            "rival_away_", "landslide_", "really_benevolent", "benevolent", "hostile", "really_hostile", "weakness",
            "CONDENSED_price_change_oracle_prediction_",   # sic: the price events' prediction posts it (0x32B / 0x333)
            "tribute_due_", "tribute_received_",
            # terrain disasters (FUN_004474E0: the object's phrase base vtable +0x28 = title, + 1 by a god / chained,
            # + 2 no reason; sim/disasters): quake 0x52E, lava 0x522, flood 0x528 / Poseidon's 0x1022
            "quake_", "lava_", "flood_")     # event_tribute_out 0x004715C0 (sim/empire/diplomacy.py)


def phrase_names(read=None):
    """The exe's phrase names in id order; read(va, n) reads Zeus.exe (default: tools/disasm.py, pefile)."""
    if read is None:
        from disasm import read  # noqa: E402  (Zeus.exe reader)
    names, a = [], NAME_TABLE
    while True:
        ident, ptr = struct.unpack("<II", read(a, 8))
        if ptr == 0:
            return names
        assert ident == len(names), f"name table not in order at {len(names)}"
        names.append(read(ptr, 128).split(b"\0")[0].decode("latin-1"))
        a += 8


def parse(buf, known):
    """FUN_00505770's reading rules -> {lower-case name: text}."""
    out, pos, n, pending = {}, 0, len(buf), None
    while pos < n:
        c = buf[pos]
        if c == 0x3B:                                  # ; comment
            while pos < n and buf[pos] not in b"\r\n":
                pos += 1
        elif c < 0x21:
            pos += 1
        elif pending is None:
            end = pos
            while end < n and buf[end] >= 0x21:
                end += 1
            tok = buf[pos:end].decode("latin-1").lower()
            pending = tok if tok in known else None
            pos = end
        elif c == 0x22:                                # the text, up to the next quote
            pos += 1
            t = bytearray()
            while pos < n and buf[pos] != 0x22:
                if buf[pos] == 0x5C:                   # backslash + blanks + line break: lines spliced
                    j = pos + 1
                    while j < n and buf[j] < 0x21 and buf[j] not in b"\r\n":
                        j += 1
                    if j < n and buf[j] in b"\r\n":
                        j += 1
                        if j < n and buf[j] in b"\r\n" and buf[j] != buf[j - 1]:
                            j += 1
                        pos = j
                        continue
                t.append(buf[pos])
                pos += 1
            pos += 1
            out[pending] = t.decode("latin-1")
            pending = None
        else:                                          # a name not followed by a text: the game stops reading
            break
    return out


def categories(names):
    """Model/Zeus event message categories.txt as FUN_00466B80 reads it into the phrase -> category table
    0x00915A98 (0x104C bytes): `;` comments; the first 20 lines "i,default" (category i's default setting 0 off /
    1 condensed / 2 full, kept at 0x00916AE4); then "PHRASE_name,category,..." lines; every phrase not named takes
    the category of the phrase before it (id order; the first ones 0). The message filter FUN_00521970 looks up the
    message's first phrase (+0, the announcement); 19 (0x13) = always shown."""
    ids = {n.lower(): i for i, n in enumerate(names)}
    table, defaults = [-1] * 0x104C, []
    for raw in open(CATEGORIES, encoding="latin-1"):
        line = raw.split(";")[0].strip()
        if not line:
            continue
        f = [x.strip() for x in line.split(",")]
        if len(defaults) < 20:
            assert int(f[0]) == len(defaults), line
            defaults.append(int(f[1]))
            continue
        i = ids.get(f[0].lower())
        if i is not None and f[1].lstrip("-").isdigit():
            table[i] = int(f[1])
    prev = 0
    for i, v in enumerate(table):
        if v == -1:
            table[i] = prev
        prev = table[i]
    return table, defaults


def main():
    names = phrase_names()
    cats, cat_defaults = categories(names)
    texts = parse(open(EVENTMSG, "rb").read(), {x.lower() for x in names})
    phrases = {}
    for i, name in enumerate(names):
        short = name[len("PHRASE_"):]
        if not short.startswith(FAMILIES) and "_history" not in short:     # + every history row phrase (FUN_0042EEC0)
            continue
        t = texts.get(name.lower())
        if t is None or t.strip() == "N/A":
            continue
        phrases[str(i)] = [name, " ".join(t.split())]      # line breaks inside a text are layout only
    note = ("tools/build_messages.py: Zeus.exe phrase table 0x005FBC38 + Model/Zeus eventmsg.txt (FUN_00505770); "
            "ids are the exe's phrase ids (docs/logic/monuments.md, games.md)")
    rows = ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in phrases.items())
    tx = json.load(open(TEXT))
    nat = tx["37"][:11]                                   # [nationality]: text group 37 by the city's nationality
    # history rows (FUN_004669E0): [city_affected] = group 91 by the record's relation byte (+7: 0 this city,
    # 1 an ally, 2 a rival, 3 a vassal, 4 a colony, 5 your parent city; wm_sub_466780), [itemshort] = group 23 by
    # the record's item (+10; wm_sub_465E00)
    hist = {"city_affected": tx["91"][:6], "itemshort": tx["23"][:30],
            # the offer dialogs' [item] (wm_sub_465DA0, variable table 0x005FBA68): group 98 by the event's item,
            # the unit phrase ("amphorae of wine"; oracle sandbox: "my tribute of 4 amphorae of wine")
            "item": tx["98"][:30],
            # [gift_size] (wm_sub_466230): group 162 by the gift's size (func_0x0047fb50: 0 small, 1 medium, 2 large)
            "gift_size": tx["162"][:3],
            # [greeting] (variable table 0x005FBA2C -> wm_sub_465B10): group 32 entry 11 + DAT_00FEAEA4; 11..21 are
            # all "O great"
            "greeting": tx["32"][11:22],
            # [a_foreign_army] (wm_sub_465FB0): group 37 entry 22 + the city's nationality ("a Trojan army")
            "foreign_army": tx["37"][22:33]}
    cat = {k: cats[int(k)] for k in phrases}               # the message filter's category by phrase id
    open(OUT, "w").write(f'{{\n "note": {json.dumps(note)},\n "nationality": {json.dumps(nat)},\n'
                         f' "category_defaults": {json.dumps(cat_defaults)},\n "categories": {json.dumps(cat)},\n'
                         f' "history": {json.dumps(hist)},\n'
                         f' "phrases": {{\n{rows}\n }}\n}}\n')
    json.load(open(OUT))
    print(f"{len(phrases)} phrases of {len(names)} -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
