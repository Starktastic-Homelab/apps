#!/bin/bash
set -euo pipefail

# Usage: ./scripts/seal.sh <secret-name> <namespace> [--cluster-wide]
# Example: ./scripts/seal.sh ntfy-secret argocd --cluster-wide

SECRET_NAME="${1:-}"
NAMESPACE="${2:-}"
FLAG="${3:-}"

if [[ -z "$SECRET_NAME" ]] || [[ -z "$NAMESPACE" ]]; then
  echo "Usage: $0 <secret-name> <namespace> [--cluster-wide]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_FILE="$SCRIPT_DIR/sealed-secrets-cert.pem"

if [[ ! -f "$CERT_FILE" ]]; then
  echo "❌ Error: Sealed secrets cert not found at $CERT_FILE"
  echo "   This cert must match the pre-seeded key in Ansible vault."
  exit 1
fi

SCOPE="strict"
if [[ "$FLAG" == "--cluster-wide" ]]; then
  SCOPE="cluster-wide"
fi

echo " Enter your key-value pairs (e.g. password=SuperSecret). Press Ctrl+D when done."

kubectl create secret generic "$SECRET_NAME" \
  --namespace "$NAMESPACE" \
  --from-env-file /dev/stdin \
  --dry-run=client \
  -o yaml |
  kubeseal \
    --cert "$CERT_FILE" \
    --scope "$SCOPE" \
    --format yaml >"$SECRET_NAME.yaml"

echo "✅ Done! Saved $SECRET_NAME.yaml"
