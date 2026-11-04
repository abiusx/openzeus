# A shared server

One OpenZeus city that anyone can open in a browser, on a small cloud machine. Everyone who opens it plays the same
city at the same time.

## Setup
`tools/server/setup.sh` installs a server on a fresh Ubuntu 24.04 machine. Give it as the machine's start-up script
(cloud-init user data), or run it as root. It:
- installs Python 3.14 with uv, clones the public repository and installs requirements.txt;
- downloads the two asset packs and runs `python tools/assets.py install`;
- adds a systemd service, `openzeus`, that runs
  `python -m sim live saves/shared.pkl --host 0.0.0.0 --port 8080 --speed 30 --no-test-commands --shared`.

Log: /var/log/openzeus-setup.log. It takes a few minutes, most of it the packs' download.

`--shared` (docs/play.md "Live"): every address opens the city without the main menu, the visitor's leader name is
not sent, and the city stands still while no tab is open. Visitors may still start a new city or load another one.

## The default city and the reset
Put the city you want visitors to start from in `saves/` as `default.pkl` (with `default.parent.pkl` and
`default.replay.pkl` for a campaign city), then:
- `sudo tools/server/reset.sh`: puts the default city back (it replaces `shared*.pkl` and restarts the service);
- `sudo tools/server/reset.sh --keep`: makes the current city the new default.

## On your own KVM host
`sudo tools/server/kvm_vm.sh NAME NET PUBLIC_IP HOST_PORT BASE_IMAGE SSH_PUBKEY --cloudflare-only` makes a libvirt
guest (2 vCPU, 2 GB, 20 GB) on its own NAT network 192.168.NET.0/24 (the VM at .10), set up on first boot by
setup.sh through cloud-init, autostarted with the host; on a ufw host it adds the port forward HOST_PORT -> the VM's
8080 (`/etc/ufw/before.rules`, a backup next to it), DHCP / DNS on the VM's bridge and route rules, the port open to
Cloudflare's addresses only. Then the CDN's origin port for the site's host name is HOST_PORT. The script's comments
list each step. (11-04: the firewall must come before the VM's first boot: setup.sh needs the network then; a
failed setup can be run again in the VM: `bash /root/setup.sh`.)

## Hosts compared (11-04, the same campaign city, tools/profile_sim.py: the sim alone / 1x with frame recording)
| Host | sim alone | 1x recording | Notes |
|---|---|---|---|
| 1 shared vCPU AMD EPYC Genoa (a $6 cloud plan, no credit) | 1,490 ticks/s | 445 | direct sync check: 1x-4x smooth, 8x 106 of 120 |
| KVM guest, 2 vCPU of an AMD EPYC 7502P (busy host) | 905-935 | 270-285 | through the CDN: 1x 14.7, 2x 29.9, 4x 59.0 t/s (<= 1 stall >= 50 ms in 20 s), 8x 92.6 of 120 |
| 2 vCPU burstable (credit left) | 690-730 | 186-203 | credit runs out under load (below) |
| a recent laptop (Apple silicon) | 1,754 | 554 | |
The sim is one Python thread: per-core speed decides, not core count.

## In front of it
A CDN such as Cloudflare can proxy the server: the sprite sheets (`play/atlas/*.png`, `.bin`) are served cacheable
for a day, so the CDN serves them after the first visitor. Proxy HTTP to the server's port 8080.
A CDN caches per location: the first visitor at each one gets the sheets from the server itself (~0.9 MB/s measured
from the developer's machine to the one below, so ~2 min for the original's 124 MB); later ones from the CDN (5-17 MB/s:
~12 s to the city). The start screen shows a bar with MB done / total and the time left (bugs.md 483).

A restart (deploy, reset.sh) is seen by open tabs (frames meta `boot`): they fetch the new city whole
(bugs.md 481; before, a tab open over a restart could keep the old city's terrain).

## Measured (11-04, 2 vCPU burstable, 1 GB RAM, a campaign city of 6,700 people)
- The simulation alone: 423 ticks/s (a recent laptop: about 1,260).
- Through the CDN from another continent, polls take 200 to 350 ms. The city reached 25 ticks/s at 2x, 47 at 4x,
  86 at 8x, 154 at 16x and 203 at 32x (before bugs.md 482: the tab's margin was shorter than a poll cycle there, so
  it also stopped briefly on most polls). After 482: see "Measured after 482" below.
- Smoothness over a slow link: `node tools/sync_check.mjs URL --rates 15,30,60 --secs 30` (docs/play/comms.md
  "Margin over a slow link").

## Measured after 482 (11-04, the same machine and city, from the developer's machine through the CDN)
`node tools/sync_check.mjs https://openzeus-play.abiusx.com/ --rates 15,30,60 --secs 30`, poll round trip median
190-250 ms (max 400-800 ms now and then):
- with CPU credit left: 1x 14.9 t/s, 2 stalls >= 50 ms in 30 s (longest 150 ms); 2x 29.3 t/s, 3 (longest 416 ms,
  a 190 ms socket write under the lock plus a 241 ms sim step at the same moment: the write is outside the lock
  now); 4x 59.0 t/s, 2 (longest 171 ms). Before (bug 482's margin) a tab stopped on most polls over such a link.
- Fresh browser profile, sheets cached at the CDN: the city on screen after 10.8-12.6 s (124 MB).
- The machine is burstable: after about an hour of tests its CPU credit ran out (vmstat: 40-56 % steal, 10 % user),
  and the sim fell to ~20 ticks/s (60 ticks took ~3 s): 4x reached 42.8 t/s, then less than 2x. A city nobody
  watches stands still (SHARED_IDLE), so the credit comes back; for steady 4x and above take a machine with a
  higher baseline (Lightsail's larger bundles, or a non-burstable instance). The baseline share of this bundle
  was not checked.


## Where the CPU goes (11-04, profiled on the user's campaign city, May 1088 BC, 315 walkers, 675 buildings)
Tools: `python3 tools/profile_sim.py SAVE_COPY [--live --rate 15]` (cProfile over N ticks: the sim alone, or with
the live server's recording) and `python3 tools/profile_live.py SAVE_COPY --port P --secs S` (a whole live server
under one cProfile while a tab drives it: CPU per request path, gzip, autosaves).
On a laptop (Apple silicon), per tick at 1x:
- the simulation: 0.57 ms (1,754 ticks/s alone);
- recording the frame the tab draws (every tick at <= 2x, `frame_every`): 2.8 ms before, 1.5 ms after the fixes
  below. It was the biggest cost: 1x with recording ran 293 ticks/s, now 491. Its parts after the fixes: the walker
  records 0.43 ms (315 walkers), their JSON 0.3 ms, the episode's build-menu table 0.25 ms, deltas and houses the rest;
- serving: frames.json polls (15/s at 1x locally), gzip 0.2 % of a core, the 5 s autosave 8 ms each: small.
A live server at 1x with one tab used ~6 % of a laptop core; the 2 vCPU burstable instance is ~3x slower per core.
Fixed: the build-menu table (sim/allowed.py `unavailable`, every frame) scanned every building for each good's
stock (12 times a frame) and for the palace / venue per rule: the stocks are now taken once per read (`_memo`)
and the scans once per table; comms.dumps reuses one C JSON encoder (JSONEncoder.encode built one per call).
Output unchanged (tests, state hash, comms_check verify). Then (user 11-04) the frames' build-menu table is cached for 1 s of wall time,
and recomputed at once on a map change (Runner.episode_frame): 1x with recording 491 -> 554 ticks/s.
A frame's parts after that (296 walkers, 0.96 ms before the cache): menu table 0.23, walker animation state 0.15,
walker JSON 0.14, walker step 0.08, carried good 0.07, other walker fields 0.03, houses 0.03, waiting carts and
destinations 0.03, delta 0.03, alerts / sanctuaries / heroes / lava 0.02, the rest of the frame's JSON ~0.14. Left, by size: frames every tick at <= 2x (a frame every
3 ticks would cut recording ~3x; user 11-04: not done, per-tick animations were tuned against per-tick frames), reusing unchanged walkers' JSON between frames, and the exe's timing for
the menu table (buildings_availability 0x00402B80 runs at episode start and a few events, ours every frame).
