"""World map dialogs vs the exe (bugs.md 122, docs/play/world.md "Dialogs"): renders each dialog in play mode
(tools/screens_check.mjs: dpr 1.25, interface 80 %, a 1024 x 768 interface, readPixels) and compares it with the
oracle shots of re/oracle/scenarios/worldmap-dialogs*.txt (runs 1F-wmdlg1, 1F-wmdlg2; tools/screens_compare.py).
Usage (your own server on a NEW sandbox game, not a game in play; the file must not exist):
    python3 -m sim live /tmp/new-sandbox.pkl --port 8794 --speed 0 &
    python3 tools/world_dialog_check.py http://127.0.0.1:8794 OUTDIR [SHOT ...]
The history2 shot needs the request the oracle made first: it sends `request Tiryns drachmas` to that server.
The strike shots (oracle 1F-strike, re/oracle/scenarios/worldmap-strike.txt: Tiryns' army and attitude poked) need
their own NEW sandbox server, run alone and in this order: `... OUTDIR req_strike strike_list strike_hover
strike_hover2 strike_confirm strike_confirm_hover after_strike history3` (they send the same pokes as commands, and
after_strike makes the strike request the oracle made)."""
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "re", "oracle", "runs")
# shot: (run, city, dialog kind, extra JSON, rect x,y,w,h in the 1024 x 768 screen, mouse or None)
SHOTS = {
    "advice": ("1F-wmdlg1", "Tiryns", "advice", {}, (179, 200, 480, 368), None),
    "request": ("1F-wmdlg1", "Tiryns", "request", {}, (159, 298, 528, 176), None),
    "requests": ("1F-wmdlg1", "Tiryns", "requests", {}, (171, 176, 496, 416), None),
    "gift": ("1F-wmdlg1", "Tiryns", "gift", {}, (319, 340, 208, 96), None),
    "history": ("1F-wmdlg1", "Tiryns", "history", {}, (123, 200, 592, 368), None),
    "gift_hover": ("1F-wmdlg2", "Tiryns", "gift", {}, (319, 340, 208, 96), (419, 393)),
    "giftsize": ("1F-wmdlg2", "Tiryns", "giftsize", {"item": "drachmas"}, (269, 312, 352, 144), None),
    "giftsize_hover": ("1F-wmdlg2", "Tiryns", "giftsize", {"item": "drachmas"}, (269, 312, 352, 144), (444, 392)),
    "request_hover": ("1F-wmdlg2", "Tiryns", "request", {}, (159, 298, 528, 176), (419, 351)),
    "req_rival": ("1F-wmdlg2", "Sparta", "request", {}, (159, 312, 528, 144), None),
    "advice_rival": ("1F-wmdlg2", "Sparta", "advice", {}, (179, 200, 480, 368), None),
    "req_vassal": ("1F-wmdlg2", "Miletos", "request", {}, (159, 284, 528, 208), None),
    "advice_vassal": ("1F-wmdlg2", "Miletos", "advice", {}, (179, 200, 480, 368), None),
    "req_colony": ("1F-wmdlg2", "Elis", "request", {}, (159, 298, 528, 176), None),
    "advice_colony": ("1F-wmdlg2", "Elis", "advice", {}, (179, 200, 480, 368), None),
    "gift_colony": ("1F-wmdlg2", "Elis", "gift", {}, (319, 340, 208, 96), None),
    "history2": ("1F-wmdlg2", "Tiryns", "history", {}, (123, 200, 592, 368), None),
}
# the strike popups (world.js strikeOpen / strikeList / strikeConfirm): shot -> (mouse, commands sent first, page JS
# after the city is selected); the request dialog's strike row is row 4, Sparta / Delos the list
ST = "WorldMap.openDialog('request', {}); WorldMap.strikeOpen(4); "
UNDER = (140, 40, 560, 440)                     # the list at (150, 50) and the request dialog under it
STRIKE = {
    "req_strike": ((876, 485), ["empire army Tiryns 20", "empire attitude Tiryns 100"], "WorldMap.openDialog('request', {});",
                   (159, 298, 528, 176)),
    "strike_list": ((600, 600), [], ST, UNDER),
    "strike_hover": ((252, 93), [], ST, UNDER),
    "strike_hover2": ((250, 187), [], ST, UNDER),
    "strike_confirm": ((250, 72), [], ST + "const d = WorldMap.dialog(); d.target = d.list[0]; d.confirm = 0x4A;", UNDER),
    "strike_confirm_hover": ((545, 341), [], ST + "const d = WorldMap.dialog(); d.target = d.list[0]; d.confirm = 0x4A;", UNDER),
    "after_strike": ((545, 341), ["request Tiryns strike Sparta"], "WorldMap.openDialog('request', {});", (159, 298, 528, 176)),
    "history3": ((931, 109), [], "WorldMap.openDialog('history', {});", (123, 200, 592, 368)),
}
for _k, (_m, _c, _js, _r) in STRIKE.items():
    SHOTS[_k] = ("1F-strike", "Tiryns", None, {}, _r, _m)


def send(base, cmds):
    req = urllib.request.Request(base + "/cmd", data=json.dumps({"cmds": cmds}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req).read()
    except Exception as e:  # noqa: BLE001
        print("command failed:", e)


def main(a):
    base, out = a[0], a[1]
    names = a[2:] or [k for k in SHOTS if k not in STRIKE]
    os.makedirs(out, exist_ok=True)
    total = 0
    for n in names:
        run, cname, kind, extra, (x, y, w, h), mouse = SHOTS[n]
        if n == "history2":
            send(base, ["request Tiryns drachmas"])
        then = f"WorldMap.openDialog({json.dumps(kind)}, {json.dumps(extra)});"
        if n in STRIKE:
            if STRIKE[n][1]:
                send(base, STRIKE[n][1])
            then = STRIKE[n][2]
        js = ("document.body.classList.remove('dev'); WorldMap.isOpen() || WorldMap.toggle();"
              f" const t = setInterval(() => {{ const c = WorldMap.data && WorldMap.data.cities.find(c => c.name === {json.dumps(cname)});"
              f" if (c && (c.asks || []).length) {{ clearInterval(t); WorldMap.select(c.id); {then} }} }}, 100);")
        each = f"UIX.mouse = [{mouse[0]}, {mouse[1]}];" if mouse else "UIX.mouse = [-1, -1];"
        ppm = os.path.join(out, n + ".ppm")
        subprocess.run(["node", os.path.join(ROOT, "tools", "screens_check.mjs"), base + "/play.html?tex=png", ppm,
                        "--size", "820x615", "--rect", f"{x},{y},{w},{h}", "--open", js, "--each", each],
                       check=True, capture_output=True)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "screens_compare.py"), ppm,
                            os.path.join(RUNS, run, n + ".bmp" if n not in ("gift_colony",) else n + ".bmp"),
                            f"{x},{y}", "--diff", os.path.join(out, n + "_diff.png")], capture_output=True, text=True)
        print(f"{n:16s} {r.stdout.strip()}")
        total += r.returncode
    return total


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1:]) else 0)
