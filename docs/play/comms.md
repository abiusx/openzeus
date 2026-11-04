# Client/server traffic in play mode (2026-10-30)

Supporting work (the stage plan "Supporting work"; TODO.md "Client/server comms"; bugs.md 202, 264). Code: sim/comms.py
(server: deltas), sim/live.py (recording, endpoints), viewer/play/comms.js (client: rebuilding), viewer/play/play.js
(pollFrames, pollState, pollTerrain, pollDue). Check and measurements: tools/comms_check.mjs.

## Before
- The live tab asked `/frames.json` on every animation frame (one request in flight): ~113 requests/s at 120 fps.
  Each answer carried the frame in effect at `from` even when the tab already had it, so a paused city still sent
  ~560 KB/s (the last frame, again and again).
- Every frame held the whole walker list (~21 KB of JSON for ~210 walkers); about 10 of them change per tick.
- Every building snapshot (`state.json?lite=1`, ~250 KB: buildings, walkers, reports...) was fetched whole, 2.5-10
  times a second (a snapshot every map change, or every 0.5 s of wall time).
- `terrain.json` (1 MB of JSON, ~66 KB gzipped) was fetched whole after each map change, at most every 1.5 s.

## Protocol 2
The server keeps the old answers (old pages, the sim viewer, `?proto=1`) and gives deltas when asked with `v=2`.
`/frames.json` meta carries `proto: 2` (the newest version the server speaks), and in a campaign game `campaign`: a key
that changes with the campaign screen; the tab then fetches /campaign.json (docs/play/campaign.md).

Each document has an id the tab sends back as `base`:
- frames: `fs`, a frame serial in every frame (unique per recorded frame, also across new games and loads; a frame
  re-recorded at the same tick after a command gets a new one);
- snapshots: `seq` (as before);
- terrain: `tid`, a serial of the terrains the server built (map_version restarts with a new city, tid does not).

Requests:
- `GET /frames.json?from=A&to=B&at=T[&want=W[&hold=1]]&v=2[&base=FS]` (hold: a screen pauses the tab, the stall
  watcher skips that time; bugs.md 467): the frames as before, but a frame whose predecessor in
  the answer (for the first one: the tab's newest frame `base`) is the base of its stored delta goes as that delta,
  and base's own frame is left out. A frame re-recorded at the tab's newest tick comes whole, and the tab takes it
  in place of its copy (before: it kept the old copy).
- `GET /state.json?lite=1[&t=T]&v=2[&base=SEQ]`: `{"deltas": [...]}`, the chain of deltas from SEQ to the snapshot
  in effect (`[]` = unchanged) when every link is kept (the last STATE_DELTAS = 64 snapshots) and the chain is smaller;
  else the whole snapshot.
- `GET /terrain.json?v=2[&base=TID]`: a delta on TID when the server still has it (the last 3 terrains it served),
  `{"_b": TID}` when TID is the newest; else the whole terrain.
- `GET /state_ticks.json`: `{"states": [[tick, seq]]}` (tests).

A delta (sim/comms.py docstring):
```
{"_b": base id,
 "set": {key: value}, "del": [key],                                   top-level keys, whole values
 "keyed": {key: {"up": [record], "rm": [id], "order": [id]}},         walkers, houses (frames); buildings, walkers (snapshots)
 "sub": {key: {"set": {k: v}, "del": [k]}},                           snapshot dicts (city, reports, stocks...)
 "ix": {key: [i, v, i, v, ...]}}                                      terrain grids (ids, draw, elev, flags, road, des)
```
Keyed lists: records with a unique id (frames: `[id, ...]`, element 0; snapshots: `{"id": ...}`). "up" holds new
records whole and changed ones: list records whole, dict records as their changed fields plus `"_x"` (gone fields).
"order" is sent only when the ids' order is not the base order minus "rm" plus the new ids in their order (the
draw order of equal-depth walkers follows the list order). The server compares JSON text (each record, each value),
not Python objects: the game changes some exported objects in place, and Python's `==` takes `True` for `1`.
A delta that would not be smaller than the document is not stored (the tab gets the document).

Server side (sim/live.py Runner): record_frame / record_state serialize the document in parts (comms.encode; joined
it is byte-identical to the old JSON), keep the encoding of the newest one and the one before (a re-record at the
same tick builds on the one before), and store the delta with the frame / snapshot: frames as
`(tick, json, fs, base fs, delta)`, snapshots as `(tick, json, seq, base seq, delta)`. Frames older than KEEP_RAW
(4000 ticks) lose their delta when they are compressed (a tab replaying that far back gets whole frames). Old frames
and snapshots are thinned by age (docs/sim-design.md "Live recording memory"); a kept one whose base was dropped
loses its delta too.

Client side (comms.js): `decodeFrames(base, list)`, `applyState(S, answer)`, `applyTerrain(T, answer)` rebuild whole
documents; records that did not change are the same objects as in the base (the page never changes frame or snapshot
records in place; build.js patchCleared changes the terrain in place, so it marks it `T.patched` and the next
terrain is asked whole). A document remembers its server keys (a symbol), so the page's own caches on it (buildTerrain:
`T.altMap`, `T.cliffMap`) are not carried over to the next version. A delta whose base is not the one the tab
holds (should not happen) is dropped, counted in `COMMS.resync`, and the next request asks the whole document.
The rest of the page reads `FRAMES`, `P.f0/f1`, `S` and `T` as before.

Polling (play.js pollDue, protocol 2):
- live, visible tab: when the buffer (newest frame - playhead) is below half of `ahead()` (the poll asks
  `want = playhead + ahead()` as before), or 250 ms after the last poll (pause, speed, other tabs' commands).
  ~15 polls/s at speed 30, ~22 at 120; the tab now trails the city by 2.5-3 ticks at speed 30 (3.5 before);
- replaying tab: when less than `rate + 45` ticks are buffered, or every 500 ms (the timeline's live end);
- hidden tab: every interval tick (100 ms; Chrome throttles it to 1 s), as before.
State and terrain are asked when the frames' meta says they changed, as before.

`?proto=1` in the page url: the old behaviour (full answers, a poll every animation frame); for comparisons.

## Numbers (2026-10-30)
Headless Chrome 150 (tools/play_cdp.mjs, 1280x800, dpr 1.25, 120 fps), live tab at speed 30 for 20 s after 10 s of
warm-up, message windows closed as they come; `assets` (sprite atlases loaded on demand) left out. KB/s = bytes over
the wire (CDP encodedDataLength, gzip and headers included). Parse = JSON.parse of every answer; apply = comms.js;
script = Chrome's ScriptDuration (drawing included); server = CPU s per s of the server process.

| city | protocol | KB/s total | frames | state | terrain | frames req/s | parse ms/s | apply ms/s | script ms/s | server |
|---|---|---|---|---|---|---|---|---|---|---|
| save H copy (672 buildings, ~210 walkers) | 1 (before) | 588 | 498 | 50 | 40 | 104 | 6.0 | - | 198 | 0.26 |
| save H copy | 2 | 25 | 18 | 6.8 | 0.2 | 15 | 0.55 | 1.2 | 184 | 0.17 |
| live-full copy (661 buildings, ~200 walkers) | 1 (before) | 577 | 492 | 45 | 39 | 109 | 6.2 | - | 189 | 0.24 |
| live-full copy | 2 | 25 | 18 | 6.2 | 0.2 | 15 | 0.6 | 1.4 | 198 | 0.17 |
| save H copy, speed 120 | 1 | 656 | 427 | 188 | 41 | 82 | 8.7 | - | 224 | 0.50 |
| save H copy, speed 120 | 2 | 51 | 29 | 22 | 0.3 | 22 | 1.1 | 2.6 | 210 | 0.38 |
| save H copy, paused | 1 | 561 | 561 | 0 | 0 | 120 | 5.1 | - | 171 | 0.09 |
| save H copy, paused | 2 | 2.2-3.5 | 1.5 | 0 | 0 | 3.9 | 0.05 | 0 | 142 | 0.01 |

(The "1 (before)" rows: the new server with `?proto=1`; HEAD 3b79483 measured the same on these copies: 588 and
617 KB/s.) Traffic is 13-250x lower; the tab's JSON parse + apply time 6 -> ~2 ms per second; the rest of the tab's
script time is drawing and did not change (its run-to-run spread is ~10 ms/s). A frame delta is ~1 KB of JSON for ~10 changed walkers; a snapshot delta
3-10 KB (walkers of the snapshot, coverage, reports); a terrain delta a few hundred bytes.

## Same pictures
`node tools/comms_check.mjs verify URL OUT` (server: a copy of a save on your own port):
0. a protocol-2 live tab plays 20 s while 20-40 commands change the tax rate (frames and snapshots re-recorded at the
   same tick), then the server is paused: every frame the tab holds, its snapshot and its terrain equal the server's
   whole ones (deep equal; the page's terrain caches left out, altMap checked against T.alt);
1. data: every frame of the last N ticks rebuilt from a keyframe chain and from 20 bases in the middle equals the whole
   frame; the last 12 snapshots chained from the one before equal the whole ones;
2. pixels: the page in replay mode with `?proto=1` and with protocol 2, the clock frozen, the playhead stepped over the
   same ticks (a snapshot per tick as the timeline gives it): a readPixels hash of the whole canvas per tick, drawn
   once on-demand sprite files (loadAtlases: `ATLAS_PENDING`) and freed textures (resumeSheet) are in. `--keep` also
   saves the `?proto=1` pictures (p1_<tick>.png) next to the differing protocol-2 ones.
11-04 (bugs.md 463, save C copy with lava): "terrain lavaMap differs" was the checker comparing the page's
lava cache (T.lavaMap, since fcf4c0c), now left out with the other caches; the pixel diffs at the first ticks
(4 px, both protocols, old viewer code too) were the monument step holes filled with ground until the second terrain
build (scene.js monumentStepsChanged skipped the first change), fixed. After: live tab, frames 301, states 12,
pixels 299 ticks, 0 differ.
Results 10-30 (save H copy): live tab 63 frames, snapshot, terrain equal, 0 resyncs; frames 301 / 201 checked, 0
differ; snapshots 12, 0 differ; pixels 299 ticks (299 distinct pictures, every tick) and 100 ticks, 0 differ.
A new city (`/control {new}`), replay -> live and back on the live-full copy: frames, snapshot and terrain equal, 0
resyncs. `python3 tests/test_sim.py test_comms_deltas` (tests/test_play.py): frames, a snapshot chain and terrain grids rebuilt by a Python
twin of comms.js equal the whole documents.

Info windows, overlays and advisors read `S`, `T` and the frames (equal above) or ask their own endpoints
(advisor.json, walker_info.json, ...), which did not change.

Recordings: `serve --record DIR` plays the monthly snapshots of `run --record` (sim/serve.py, viewer/index.html); it
does not use these endpoints and is unchanged. The live server's own recording (frames, snapshots) only gained `fs`
in every frame; `/frame.json` (the sim viewer) answers as before.

## Reproduce
```
W=$TMPDIR/zeus-comms; mkdir -p $W; cp a save $W/hard.pkl; cp saves/live-full.pkl $W/full.pkl
python3 -m sim live $W/hard.pkl --port 8790 --speed 30 &          # (not a game in play)
PID=$(pgrep -f "sim live $W/hard.pkl")
node tools/comms_check.mjs measure http://127.0.0.1:8790/play.html --secs 20 --warm 10 --rate 30 --server-pid $PID
node tools/comms_check.mjs measure http://127.0.0.1:8790/play.html --secs 20 --warm 10 --rate 30 --server-pid $PID --query proto=1
node tools/comms_check.mjs measure ... --rate 120          # and --paused
node tools/comms_check.mjs verify http://127.0.0.1:8790/play.html $W/verify --ticks 300 --step 1 --live 20 --cmds 40
```
(the same with `$W/full.pkl` on port 8800). Node v22.14.0, Google Chrome 150.0.7871.187, Python 3.14.6; no packages.
The cities move on between runs (the server autosaves the copy), so the numbers vary by a few percent.

## Clock handshake: no deadlock (2026-10-31, bugs.md 344)
A synced live tab plays up to its newest frame and asks for ticks past it (`want` = playhead + margin); the server
simulates what is asked. Each side waiting on the other must never stall the city:
- Server, `set_speed`: a fast rate records a frame every REC ticks, so the sim can stand between two frames; on a
  rate change it records a frame at its tick (128x then 1x froze the city: the tab wanted ...040+3, the sim was at
  ...053 and had no frame past ...040).
- Server, `/frames.json`: when the tab wants only ticks the sim has passed (want < tick) and its newest frame is
  behind the sim, one frame at the sim's tick (not when want == tick: every poll at high speed).
- Tab, watchdog (play.js pollFrames): live, playing, the server ahead and the playhead unmoved for 2 s: it stops
  sending `want`, the server runs alone after DRIVE_TIMEOUT (1 s) and `advance` catches the tab up. Checked alone
  against the old server: recovers in ~2-3 s. While stuck, a spinner in the middle of the screen says "Catching up
  with the city…" (ours, user 10-31), and "Waiting for the server…" when no answer came for 3 s (play.js status).
Check: tools/comms_check.mjs verify (0 differ in 2 of 3 runs; one run had 1 live-tab frame differ, likely the
command re-record race at one tick, `again` in record_frame, not proven) and the 128x -> 1x repro (headless).

## Left
- The snapshot still carries the whole walker list (walker_list, read by milpanel.js only): ~half of a snapshot
  delta. It could go, or come from the frames.
- Frames are still JSON with gzip only above 2 KB; a binary walker record would be ~4x smaller again. Not needed at
  ~25 KB/s.

## Stall watcher (11-03)
The live server times its lock (sim/live.py TimedLock): any hold of 100 ms or more (STALL_MS; the tab keeps ~130 ms of
frames ahead, so longer stops every walker) is printed to the server's stderr as `[stall] HH:MM:SS lock N ms at
function:line (tick T)` and kept (last 200) at GET /stalls.json. A watcher thread also compares ticks done with
speed x time every 2 s while the city runs and logs `slow` below 75 %. Found by bugs.md 442 (a terrain update held
the lock ~0.6 s once a game day).
