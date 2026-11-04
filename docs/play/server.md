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

