"""`python3 -m sim campaign ...` (docs/play.md "Campaigns").

  campaign list                                       the adventures (playable here or why not)
  campaign start ADVENTURE SAVE [--episode SLOT] [--seed N] [--difficulty D]
  campaign status SAVE                                episode, goals with current values, result, next step
  campaign brief SAVE [victory]                       the episode's briefing (or victory) text
  campaign next SAVE [--colony N|NAME] [--stay]       Proceed after a victory (the colony choice when asked;
                                                      --stay: continue building the city after the last episode)
  campaign setaside SAVE GOAL                         the objectives screen's "Set aside" on goal number GOAL
  campaign replay SAVE                                the episode again from its start (after a defeat)
  campaign win SAVE                                   TEST COMMAND: the exe's forced win flag 0x00F2A6DB (judged
                                                      at the next month change)
"""
import sys

from . import flow, goals


def _opt(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def _status_text(s):
    res = {0: "playing", 1: "VICTORY", -1: "DEFEAT"}[s["result"]]
    lines = [f"{s['title']}: episode {s['number']} ({s['role']}, slot {s['slot']}, {s['start']} start): "
             f"{s['intro']}", f"{s['date']}; {res}"]
    if s["lost"]:
        from .. import messages
        lines.append("  " + messages.text(s["lost"]))
    for r in s["goals"]:
        lines.append(f"  {r['n']}. [{'x' if r['met'] else ' '}] {r['name']}: {r['goal']} -- {r['now']}")
    if not s["goals"]:
        lines.append("  (no goals: an open-play episode; it does not end)")
    lines.append("next: " + s["next"]["text"])
    return "\n".join(lines)


def main(argv):
    from ..game import Game
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    op, a = argv[0], argv[1:]
    if op == "list":
        for x in flow.index():
            a_ = flow.load(x["id"])
            why = flow.playable(a_)
            print(f"{x['id']:<28s} {x.get('title') or x['name']:<34s} {len(a_['episodes'])} episodes  "
                  + (f"(not here: {why})" if why else "playable"))
        return 0
    if op == "start":
        if len(a) < 2:
            print("usage: campaign start ADVENTURE SAVE [--episode SLOT] [--seed N] [--difficulty D]")
            return 1
        slot = _opt(a, "--episode")
        try:
            g = flow.start(a[0], int(slot) if slot is not None else None, int(_opt(a, "--seed", 1)),
                           _opt(a, "--difficulty"))
        except ValueError as e:
            print(e)
            return 1
        g.save(flow.files(a[1])["replay"])
        g.save(a[1])
        print(f"new campaign game {a[1]}: difficulty {g.difficulty}, {g.city.treasury} dr")
        print(_status_text(flow.status(g)))
        return 0
    if op not in ("status", "brief", "next", "setaside", "replay", "win") or not a:
        print(f"unknown campaign command {op!r}\n{__doc__}")
        return 2
    save = a[0]
    if op == "replay":
        try:
            g = flow.replay(save)
        except ValueError as e:
            print(e)
            return 1
        g.save(save)
        print(f"{save}: back to the start of the episode")
        print(_status_text(flow.status(g)))
        return 0
    g = Game.load(save)
    if "campaign" not in g.__dict__:
        print(f"{save} is not a campaign game (`campaign start`)")
        return 1
    if op == "status":
        print(_status_text(flow.status(g)))
        return 0
    if op == "brief":
        print(flow.briefing(g, "victory" if a[1:2] == ["victory"] else "intro"))
        return 0
    if op == "win":
        from .. import testcmds
        why = testcmds.refuse(g, "campaign win")
        if why:
            print(why)
            return 1
        g.campaign["forced"] = True
        print(testcmds.count(g, "campaign win", "the episode is won at the next month change"))
        g.save(save)
        return 0
    if op == "setaside":
        try:
            print(goals.set_aside(g, int(a[1]) - 1))
        except (ValueError, IndexError) as e:
            print(e if isinstance(e, ValueError) else "usage: campaign setaside SAVE GOAL")
            return 1
        g.save(save)
        return 0
    try:                                                     # next
        new = flow.proceed(g, save, _opt(a, "--colony"), "--stay" in a)
    except flow.Choice as c:
        print(f"{c}\n(campaign next {save} --colony N)")
        return 1
    except ValueError as e:
        print(e)
        return 1
    if new is not g:
        new.save(flow.files(save)["replay"])
    new.save(save)
    print(_status_text(flow.status(new)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
