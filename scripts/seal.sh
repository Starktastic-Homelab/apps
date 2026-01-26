#!/bin/bash

# Usage: ./scripts/seal.sh <secret-name> <namespace>
# Example: ./scripts/seal.sh pgadmin-secret databases

SECRET_NAME=$1
NAMESPACE=$2

if [ -z "$SECRET_NAME" ] || [ -z "$NAMESPACE" ]; then
  echo "Usage: $0 <secret-name> <namespace>"
  exit 1
fi

echo " Creating SealedSecret '$SECRET_NAME' in namespace '$NAMESPACE'..."
echo " Enter your key-value pairs (e.g. password=SuperSecret). Press Ctrl+D when done."

kubectl create secret generic $SECRET_NAME \
  --namespace $NAMESPACE \
  --from-env-file /dev/stdin \
  --dry-run=client \
  -o yaml |
  kubeseal \
    --controller-name=sealed-secrets-controller \
    --controller-namespace=kube-system \
    --format yaml >$SECRET_NAME.yaml

echo "✅ Done! Saved $SECRET_NAME.yaml"
