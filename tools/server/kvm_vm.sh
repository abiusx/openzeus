#!/bin/bash
# A KVM guest (libvirt) running the OpenZeus shared server, on a host whose firewall is ufw:
#   sudo tools/server/kvm_vm.sh NAME NET PUBLIC_IP HOST_PORT BASE_IMAGE SSH_PUBKEY [--cloudflare-only]
# NAME       the VM and its network (NAMEnet, bridge virbr-NAME: at most 9 characters)
# NET        the third octet of its private network 192.168.NET.0/24 (the VM is .10)
# PUBLIC_IP  the host address visitors reach; HOST_PORT on it is forwarded to the VM's 8080
# BASE_IMAGE an Ubuntu cloud image (.img/.qcow2); copied, resized to 20 GB
# SSH_PUBKEY a public key file for the VM's root and ubuntu users
# --cloudflare-only: the forwarded port accepts only Cloudflare's addresses (https://www.cloudflare.com/ips-v4)
# The VM: 2 vCPU, 2 GB, set up on first boot by tools/server/setup.sh (cloud-init), autostarted with the host.
# Firewall (before the VM boots: its first boot needs DHCP, DNS and the way out for setup.sh): a *nat block in
# /etc/ufw/before.rules (DNAT HOST_PORT -> .10:8080, masquerade out), DHCP/DNS in on its bridge, route rules;
# ufw reload. Docs: docs/play/server.md "On your own KVM host". Run it once per VM (it refuses an existing NAME).
set -euo pipefail
NAME=$1 NET=$2 PUB=$3 PORT=$4 BASE=$5 KEY=$6 CF=${7:-}
HERE=$(cd "$(dirname "$0")" && pwd)
DIR=/data/vms
SUB=192.168.$NET
MAC=52:54:00:0e:$(printf %02x "$NET"):10
virsh dominfo "$NAME" >/dev/null 2>&1 && { echo "VM $NAME exists" >&2; exit 1; }
mkdir -p "$DIR"

# network: own bridge, DHCP pins the VM at .10; forward mode open (NAT is ufw's, as the host's other VMs)
cat > /tmp/$NAME-net.xml <<EOF
<network>
  <name>${NAME}net</name>
  <forward mode='open'/>
  <bridge name='virbr-$NAME' stp='on' delay='0'/>
  <ip address='$SUB.1' netmask='255.255.255.0'>
    <dhcp>
      <range start='$SUB.100' end='$SUB.199'/>
      <host mac='$MAC' name='$NAME' ip='$SUB.10'/>
    </dhcp>
  </ip>
</network>
EOF
virsh net-define /tmp/$NAME-net.xml && virsh net-autostart ${NAME}net && virsh net-start ${NAME}net

# firewall (ufw)
R=/etc/ufw/before.rules
if ! grep -q "^# $NAME-vm DNAT" $R; then
  cp $R $R.bak-$NAME
  python3 - "$R" "$NAME" "$PUB" "$PORT" "$SUB" <<'PY'
import sys
p, name, pub, port, sub = sys.argv[1:]
s = open(p).read()
block = (f"# {name}-vm DNAT\n*nat\n:PREROUTING ACCEPT [0:0]\n"
         f"-A PREROUTING -d {pub} -p tcp --dport {port} -j DNAT --to-destination {sub}.10:8080\n"
         f":POSTROUTING ACCEPT [0:0]\n-A POSTROUTING -s {sub}.0/24 ! -d {sub}.0/24 -j MASQUERADE\nCOMMIT\n\n")
i = s.index("*filter\n")
open(p, "w").write(s[:i] + block + s[i:])
PY
fi
ufw allow in on virbr-$NAME to any port 67 proto udp >/dev/null    # the VM's DHCP and DNS from libvirt's dnsmasq
ufw allow in on virbr-$NAME to any port 53 >/dev/null
ufw route allow from $SUB.0/24 >/dev/null
if [ "$CF" = "--cloudflare-only" ]; then
  for c in $(curl -fsS https://www.cloudflare.com/ips-v4); do
    ufw route allow proto tcp from "$c" to $SUB.10 port 8080 comment "$NAME from cloudflare" >/dev/null
  done
else
  ufw route allow proto tcp to $SUB.10 port 8080 comment "$NAME" >/dev/null
fi
ufw reload

# disk + cloud-init seed: the key, then setup.sh as root
qemu-img convert -O qcow2 "$BASE" $DIR/$NAME.qcow2
qemu-img resize $DIR/$NAME.qcow2 20G
cat > /tmp/$NAME-user-data <<EOF
#cloud-config
hostname: $NAME
disable_root: false
ssh_authorized_keys:
  - $(cat "$KEY")
users:
  - default
  - name: root
    ssh_authorized_keys:
      - $(cat "$KEY")
write_files:
  - path: /root/setup.sh
    permissions: '0755'
    encoding: b64
    content: $(base64 -w0 "$HERE/setup.sh")
runcmd:
  - [bash, /root/setup.sh]
EOF
cloud-localds $DIR/$NAME-seed.iso /tmp/$NAME-user-data
virt-install --import --name "$NAME" --vcpus 2 --memory 2048 \
  --disk path=$DIR/$NAME.qcow2,bus=virtio --disk path=$DIR/$NAME-seed.iso,device=cdrom \
  --network network=${NAME}net,mac=$MAC,model=virtio --os-variant ubuntu24.04 \
  --graphics none --noautoconsole
virsh autostart "$NAME"
echo "VM $NAME: $SUB.10, $PUB:$PORT -> 8080; setup log in the VM: /var/log/openzeus-setup.log (a few minutes)"
