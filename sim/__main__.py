"""CLI. State lives in a save file so each call is independent (agent-friendly).

  python3 -m sim new SAVE [--map sandbox] [--seed N] [--difficulty VeryEasy|Easy|Normal|Hard|Impossible]  (default: the map's, data/maps.json)
  python3 -m sim do SAVE "build house 170 160" "road 160 158 180 158" "days 10" ...
  python3 -m sim status SAVE
  python3 -m sim look SAVE [X Y [W H]]        (default: around the map entry)
  python3 -m sim info SAVE X Y
  python3 -m sim catalog SAVE
  python3 -m sim history SAVE
  python3 -m sim map SAVE [STEP]               whole-map overview
  python3 -m sim houses SAVE                   every house: position, level, people, what it needs
  python3 -m sim coverage SAVE SERVICE [X Y W H]   which houses a service reaches
      (water healer philosophy athletics drama competition tax maintenance watchman)
  python3 -m sim risk SAVE                     buildings closest to burning/collapsing
  python3 -m sim report SAVE [TAB]             the original's control-panel tabs (population husbandry
      industry distribution hygiene administration culture mythology military aesthetics overview)
  python3 -m sim live [SAVE] [--script SCRIPT] [--map M] [--port 8765] [--speed TICKS/S] [--no-test-commands]
      (a new game's map: sandbox, with --script sandbox_open)
      run + animate in browser; --no-test-commands refuses test-only commands (wolves, invade, funds...;
      sim/testcmds.py, docs/play.md "Test commands") for the server's whole run
  python3 -m sim serve [SAVE] [--port 8765] [--record DIR]   live viewer in the browser
  python3 -m sim run SCRIPT [--save SAVE] [--seed N] [--map M] [--quiet] [--record DIR] [--no-cache]
      (default map: sandbox_open, everything buildable: the scripts/ benchmarks are written for it)
      resumes from the longest unchanged prefix of SCRIPT it has a checkpoint for (sim/checkpoint.py);
      --stale also takes checkpoints made by older code (fast iteration on late-game code; rerun
      without it before trusting results)
      --record DIR writes a monthly snapshot (JSON) for the viewer's timeline
      SCRIPT lines: commands as for `do`; blank lines and '#' comments ignored;
      'status' / 'look ...' / 'info X Y' print views at that point.
"""
import sys
import time

from .game import Game, CommandError
from . import render


VIEW_OPS = ("status", "look", "info", "catalog", "houses", "risk", "coverage", "map", "history", "report")


def views(g, line):
    p = line.split()
    if p[0] == "status": return render.status(g)
    if p[0] == "look":
        a = [int(v) for v in p[1:]]
        x, y = (a[0], a[1]) if len(a) >= 2 else (g.world.entry[0] - 30, g.world.entry[1] - 15)
        return render.look(g, x, y, *(a[2:4] or [60, 30]))
    if p[0] == "info": return render.info(g, int(p[1]), int(p[2]))
    if p[0] == "catalog": return render.catalog(g)
    if p[0] == "houses": return render.houses_report(g)
    if p[0] == "risk": return render.risk_report(g)
    if p[0] == "coverage":
        a = [int(v) for v in p[2:]]
        return render.coverage_map(g, p[1] if len(p) > 1 else "water", *a)
    if p[0] == "map": return render.overview(g, int(p[1]) if len(p) > 1 else 3)
    if p[0] == "history": return "\n".join(str(h) for h in g.history)
    if p[0] == "report":
        from . import reports
        tabs = [t for t in reports.TABS if len(p) < 2 or t.startswith(p[1])]
        return "\n\n".join(f"### {t}\n{reports.text(g, t)}" for t in tabs) or f"tabs: {' '.join(reports.TABS)}"
    return None


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    op = argv[0]
    opt = lambda name, default: argv[argv.index(name) + 1] if name in argv else default
    if op == "new":
        if len(argv) < 2 or argv[1].startswith("-"):        # `new --help` once wrote a save named "--help"
            print("usage: python3 -m sim new SAVE [--map M] [--seed N] [--difficulty D]")
            return 1
        try:                                        # --difficulty overrides the map's default (data/maps.json)
            g = Game(opt("--map", "sandbox"), int(opt("--seed", 1)), difficulty=opt("--difficulty", None))
        except ValueError as ex:
            print(ex)
            return 1
        g.save(argv[1])
        print(f"new game {argv[1]}: map {opt('--map', 'sandbox')}, seed {g.seed}, difficulty {g.difficulty}, entry {g.world.entry}, "
              f"{g.date()}, {g.city.treasury} dr")
        return 0
    if op == "live":
        from .live import live
        save = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else None
        live(save, opt("--script", None), int(opt("--port", 8765)), int(opt("--speed", 120)),
             opt("--map", None), int(opt("--seed", 1)), no_test="--no-test-commands" in argv,
             host=opt("--host", "127.0.0.1"), shared="--shared" in argv)
        return 0
    if op == "serve":
        from .serve import serve
        save = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else None
        serve(save, int(opt("--port", 8765)), opt("--record", None))
        return 0
    if op == "campaign":                            # the campaign module's CLI (sim/campaign; the core never imports it)
        from .campaign import cli
        return cli.main(argv[1:])
    if op == "run":
        from . import script, checkpoint
        seed, map_name = int(opt("--seed", 1)), opt("--map", "sandbox_open")
        lines = list(script.load(argv[1]))
        cache = "--record" not in argv and "--no-cache" not in argv
        steps = [l for _, l in lines if l.split()[0] not in VIEW_OPS]
        ks = checkpoint.keys(steps, seed, map_name) if cache else None
        sk = checkpoint.keys(steps, seed, map_name, code=False) if cache else None
        done, g = checkpoint.find(ks, sk if "--stale" in argv else None) if cache else (0, None)
        t0 = time.time()
        if g is None:
            g = Game(map_name, seed)
        else:
            print(f"[resumed from a checkpoint after {done} of {len(steps)} commands: {g.date()}, tick {g.tick};"
                  f" --no-cache to run from the start"
                  + ("; --stale: it may come from older code, so the early game is the old code's" if "--stale" in argv else "")
                  + "]")
            for e in getattr(g, "script_errors", []):
                print(e)
        if "--record" in argv:
            import os
            g.record_dir = opt("--record", None)
            os.makedirs(g.record_dir, exist_ok=True)
            from . import export
            export.write(g, f"{g.record_dir}/{g.tick:08d}.json")
        quiet = "--quiet" in argv
        rc = 1 if getattr(g, "script_errors", None) else 0
        k = 0                                  # state-changing commands seen
        last_ck = g.tick
        for n, line in lines:
            if line.split()[0] in VIEW_OPS:
                if k >= done:
                    print(f"--- {line}\n{views(g, line)}")
                continue
            k += 1
            if k <= done:
                continue
            try:
                r = script.apply(g, line)
                if not quiet: print(f"> {line}: {r}")
            except CommandError as e:
                msg = f"! {n}: {line}: {e}"
                print(msg)
                g.sd("script_errors", []).append(msg)
                rc = 1
            if cache and (g.tick - last_ck >= checkpoint.EVERY or k == len(steps)):
                checkpoint.save(g, ks[k], sk[k])
                last_ck = g.tick
        if "--save" in argv: g.save(opt("--save", None))
        if getattr(g, "record_dir", None):
            from . import export
            export.write(g, f"{g.record_dir}/{g.tick:08d}.json")
        from . import render
        print(render.stability(g)[0])
        print(f"[{g.date()}, {g.tick} ticks in {time.time() - t0:.1f}s]")
        return rc
    g = Game.load(argv[1])
    if op == "do":
        # all-or-nothing: on the first failing command nothing is saved (docs/play.md "Commands"); the lines
        # already printed for earlier commands are named as not saved (playtest 10-30: a player missed that)
        done = 0
        for cmd in argv[2:]:
            v = views(g, cmd)
            if v is not None:
                print(v)
                continue
            try:
                print(f"> {cmd}: {g.command(cmd)}")
                done += 1
            except CommandError as e:
                print(f"! {cmd}: {e}\n! nothing saved: " + (f"the batch is all-or-nothing, so the {done} command(s)"
                      " above did not take effect either; " if done else "") + "fix the command and run the whole batch"
                      " again")
                return 1
        g.save(argv[1])
        return 0
    v = views(g, " ".join([op] + argv[2:]))
    if v is None:
        print(f"unknown command {op}\n{__doc__}")
        return 2
    print(v)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
