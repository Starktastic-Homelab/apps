#!/bin/sh
set -eu
# Runs only inside a newly created lab guest, from read-only seed media.
case "$(hostname)" in iscsi-lab-server-*|iscsi-lab-worker-a-*|iscsi-lab-worker-b-*) ;; *) exit 1 ;; esac
cd /mnt/iscsi-seed
sha256sum -c SHA256SUMS >/dev/null
dpkg -i packages/*.deb >/dev/null
systemctl enable --now iscsid >/dev/null
install -m 0755 k3s /usr/local/bin/k3s
ln -sf k3s /usr/local/bin/kubectl
mkdir -p /var/lib/rancher/k3s/agent/images /etc/rancher/k3s
cp k3s-airgap-images-amd64.tar.zst /var/lib/rancher/k3s/agent/images/
printf 'Offline binaries, initiator packages and K3s images installed.\n'
