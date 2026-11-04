#!/bin/bash
# OpenZeus shared server (Ubuntu 24.04, e.g. as cloud-init user data): installs from the public repo and the public asset packs,
# then runs one shared city on port 8080 as a systemd service. Log: /var/log/openzeus-setup.log
exec > /var/log/openzeus-setup.log 2>&1
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git curl ca-certificates
useradd -m -s /bin/bash openzeus || true
sudo -iu openzeus bash -euxo pipefail <<'EOS'
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.14
test -d ~/openzeus/.git || git clone https://github.com/abiusx/openzeus.git ~/openzeus   # a rerun keeps it
cd ~/openzeus
uv venv --python 3.14 ~/venv
. ~/venv/bin/activate
uv pip install -r requirements.txt
mkdir -p ~/packs
curl -fL -o ~/packs/openzeus-assets-base.zip https://openzeus-dl.abiusx.com/openzeus-assets-base.zip
curl -fL -o ~/packs/openzeus-assets-hires.zip https://openzeus-dl.abiusx.com/openzeus-assets-hires.zip
python tools/assets.py install ~/packs/openzeus-assets-base.zip ~/packs/openzeus-assets-hires.zip
rm -rf ~/packs
mkdir -p saves
EOS
cat > /etc/systemd/system/openzeus.service <<'EOF'
[Unit]
Description=OpenZeus shared city
After=network-online.target
[Service]
User=openzeus
WorkingDirectory=/home/openzeus/openzeus
ExecStart=/home/openzeus/venv/bin/python -m sim live saves/shared.pkl --host 0.0.0.0 --port 8080 --speed 30 --no-test-commands --shared
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOF
# images with ufw on (Vultr's Ubuntu: only ssh open): open the city's port
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then ufw allow 8080/tcp; fi
systemctl daemon-reload
systemctl enable --now openzeus
echo "OPENZEUS SETUP DONE"
