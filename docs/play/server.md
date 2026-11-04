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

## Measured (11-04, 2 vCPU burstable, 1 GB RAM, a campaign city of 6,700 people)
- The simulation alone: 423 ticks/s (a recent laptop: about 1,260).
- Through the CDN from another continent, polls take 200 to 350 ms. The city reached 25 ticks/s at 2x, 47 at 4x,
  86 at 8x, 154 at 16x and 203 at 32x: smooth up to about 8x.
