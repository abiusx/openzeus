"""Test-only commands (decision 2026-10-31, the decision log; docs/play.md "Test commands").

A test command is one the original game has no player action for: it injects an event, sets a hidden value or
grants something for free. Each keeps working, but its output starts with a TEST COMMAND warning and the save
counts its uses per command (`Game.test_uses`, shown in `status`). Settings and module switches (`gods off`,
`military off`, `empire on WORLD`, `scenario on`, `poseidon on`, `difficulty`) and views are not test commands.

Switches:
  testcmds [on|off]          the game's setting (stored in the save; default on, also for old saves). While off, test
                             commands are refused; turning it back on is counted too ("testcmds on").
  live --no-test-commands    the server refuses them for its whole run (LOCKED), whatever the save says; `testcmds on`
                             is refused as well. Play mode's menus never offer a test command (data: "test": true).
"""

LOCKED = False      # set by `python3 -m sim live ... --no-test-commands` (one game per server process)

# name: (verb, first argument or None, what it does). Matched by name_of(); the one list of test commands.
COMMANDS = {
    "wolves":         ("wolves", None, "a new wolf pack at X Y (sim/military)"),
    "invade":         ("invade", None, "an invading army now, by land or sea (sim/military)"),
    "cityinvade":     ("cityinvade", None, "a rival's invasion event dated today (sim/empire)"),
    "cityrequest":    ("cityrequest", None, "a city's request event (sim/empire)"),
    "citystatus":     ("citystatus", None, "a city's status change event (sim/empire)"),
    "empire attitude": ("empire", "attitude", "set a city's attitude (sim/empire)"),
    "empire army":    ("empire", "army", "set a city's army strength (sim/empire)"),
    "jealous":        ("jealous", None, "set the gods' jealousy countdown (sim/gods)"),
    "godattack":      ("godattack", None, "a god attacks now (sim/gods)"),
    "godvisit":       ("godvisit", None, "a god's next visit now (sim/gods)"),
    "monster":        ("monster", None, "a monster event now (sim/heroes)"),
    "quest":          ("quest", None, "a god's quest now (sim/heroes)"),
    "heroes cheat":   ("heroes", "cheat", "the exe's cheat flag: any hero's hall, Send For free (sim/heroes)"),
    "alert raise":    ("alert", "raise", "raise a panel alert (sim/alerts.py)"),
    "funds":          ("funds", None, "add drachmas to the treasury"),
    "grant_monument": ("grant_monument", None, "grant a commemorative monument"),
    "build TEST":     ("build", None, "a building marked \"test\": true in data/buildings.json (endless_warehouse)"),
}
_BY_VERB = {}
for _n, (_v, _a, _d) in COMMANDS.items():
    _BY_VERB.setdefault(_v, []).append((_n, _a))


def name_of(g, op, a):
    """The test command's name for this command line, or None for a player action / setting / view."""
    for name, arg in _BY_VERB.get(op, ()):
        if op == "build":
            if a and (g.cat.buildings.get(a[0]) or {}).get("test"):
                return f"build {a[0]}"
        elif arg is None:
            return name
        elif a and a[0] == arg:
            if name == "heroes cheat" and a[1:2] == ["off"]:    # switching the cheat off is always allowed
                return None
            return name
    return None


def allowed(g):
    return not LOCKED and getattr(g, "testcmds", True)


def refuse(g, name):
    """The refusal text when test commands are off, else ''."""
    if LOCKED:
        return f"'{name}' is a test command; this server runs with --no-test-commands"
    if not getattr(g, "testcmds", True):
        return f"'{name}' is a test command and test commands are off in this game (`testcmds on` allows them)"
    return ""


def count(g, name, out):
    """Count one use of a test command; its output with the warning in front."""
    uses = g.sd("test_uses", {})
    uses[name] = uses.get(name, 0) + 1
    return f"TEST COMMAND ({name}, use {uses[name]}; not a player action, counted in the save): {out}"


def switch(g, a):
    """testcmds [on|off]."""
    if a and a[0] not in ("on", "off"):
        raise ValueError("usage: testcmds [on|off]")
    if a and a[0] == "on":
        if LOCKED:
            raise ValueError("test commands can't be switched on: this server runs with --no-test-commands")
        if not getattr(g, "testcmds", True):
            g.testcmds = True
            return count(g, "testcmds on", "test commands on")
    elif a:
        g.testcmds = False
    return summary(g)


def summary(g):
    """`status`'s line: on/off and the uses so far."""
    uses = getattr(g, "test_uses", None) or {}
    state = "off (this server)" if LOCKED else "on" if getattr(g, "testcmds", True) else "off"
    return (f"test commands {state}; used: "
            + (", ".join(f"{k} {n}" for k, n in sorted(uses.items())) if uses else "none"))
