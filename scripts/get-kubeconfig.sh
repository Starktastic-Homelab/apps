#!/bin/bash
set -euo pipefail

# Configuration
USER="debian"
HOST="10.9.9.50"
KEY="$HOME/Developer/homelab/id_rsa"
LOCAL_CONFIG="$HOME/.kube/config"

echo "🔌 Fetching Kubeconfig from $HOST..."

# 1. SSH, cat the file (sudo), replace IP, and write to a temp file
TMP_CONFIG=$(mktemp)
ssh -o StrictHostKeyChecking=no -i "$KEY" "$USER@$HOST" \
  "sudo cat /etc/rancher/k3s/k3s.yaml" |
  sed "s/127.0.0.1/$HOST/g" >"$TMP_CONFIG"

# 2. Atomically move into place
mv "$TMP_CONFIG" "$LOCAL_CONFIG"
chmod 600 "$LOCAL_CONFIG"

echo "✅ Updated $LOCAL_CONFIG"
echo "   Current Context: $(kubectl config current-context)"
