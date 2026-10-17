#!/bin/bash
set -euo pipefail

# Usage: ./scripts/seal.sh <secret-name> <namespace> [--cluster-wide] [--from-file=KEY=PATH ...]
# Example: ./scripts/seal.sh ntfy-secret argocd --cluster-wide

SECRET_NAME="${1:-}"
NAMESPACE="${2:-}"

if [[ -z $SECRET_NAME ]] || [[ -z $NAMESPACE ]]; then
  echo "Usage: $0 <secret-name> <namespace> [--cluster-wide] [--from-file=KEY=PATH ...]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_FILE="$SCRIPT_DIR/sealed-secrets-cert.pem"

if [[ ! -f $CERT_FILE ]]; then
  echo "❌ Error: Sealed secrets cert not found at $CERT_FILE"
  echo "   This cert must match the pre-seeded key in Ansible vault."
  exit 1
fi

shift 2
SCOPE="strict"
CREATE_ARGS=()
for option in "$@"; do
  case "$option" in
    --cluster-wide) SCOPE="cluster-wide" ;;
    --from-file=*) CREATE_ARGS+=("$option") ;;
    *) echo "Unknown sealing option: $option" >&2; exit 1 ;;
  esac
done

if [[ ${#CREATE_ARGS[@]} -eq 0 ]]; then
  echo " Enter your key-value pairs (e.g. password=SuperSecret). Press Ctrl+D when done."
  STDIN_BUFFER=$(cat)
  if [[ -z $STDIN_BUFFER ]]; then
    echo "❌ Error: No key-value pairs provided on stdin. Aborting." >&2
    exit 1
  fi
  # Keep the descriptor open until kubectl has consumed the exact existing env-file input.
  exec 3<<<"$STDIN_BUFFER"
  CREATE_ARGS+=(--from-env-file=/dev/fd/3)
fi

kubectl create secret generic "$SECRET_NAME" \
  --namespace "$NAMESPACE" \
  "${CREATE_ARGS[@]}" \
  --dry-run=client \
  -o yaml |
  kubeseal \
    --cert "$CERT_FILE" \
    --scope "$SCOPE" \
    --format yaml >"$SECRET_NAME.yaml"

echo "✅ Done! Saved $SECRET_NAME.yaml"
