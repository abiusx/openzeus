"""Tiny HTTP server for the viewer.

  /                  viewer/index.html
  /state.json        snapshot of the live save (re-read when the file changes)
  /timeline.json     list of recorded snapshots (from `run --record DIR`), if --record DIR given
  /snap/NAME.json    one recorded snapshot
"""
import json
import os
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

from . import export
from .game import Game

VIEWER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "viewer")


def serve(save=None, port=8765, record_dir=None):
    cache = {"mtime": None, "body": b"{}"}

    def live_state():
        if not save or not os.path.exists(save):
            return b'{"error": "no save"}'
        m = os.path.getmtime(save)
        if m != cache["mtime"]:
            for _ in range(5):             # the CLI may be writing the pickle right now
                try:
                    g = Game.load(save)
                    break
                except Exception:
                    time.sleep(0.1)
            else:
                return cache["body"]
            cache["body"] = json.dumps(export.snapshot(g), default=int).encode()
            cache["mtime"] = m
        return cache["body"]

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=VIEWER, **kw)

        def log_message(self, *a):
            pass

        def send_json(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/state.json":
                return self.send_json(live_state())
            if path == "/timeline.json":
                names = sorted(f for f in os.listdir(record_dir) if f.endswith(".json")) if record_dir else []
                return self.send_json(json.dumps(dict(live=bool(save), snapshots=names)).encode())
            if path.startswith("/snap/") and record_dir:
                name = os.path.basename(path[6:])
                with open(os.path.join(record_dir, name), "rb") as f:
                    return self.send_json(f.read())
            return super().do_GET()

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"viewer on http://127.0.0.1:{port}/  (save: {save}, recordings: {record_dir})")
    httpd.serve_forever()
