#!/bin/bash

# Usage: ./scripts/seal.sh <secret-name> <namespace> [--cluster-wide]
# Example: ./scripts/seal.sh ntfy-secret argocd --cluster-wide

SECRET_NAME=$1
NAMESPACE=$2
FLAG=$3

if [ -z "$SECRET_NAME" ] || [ -z "$NAMESPACE" ]; then
  echo "Usage: $0 <secret-name> <namespace> [--cluster-wide]"
  exit 1
fi

SCOPE="strict"
if [ "$FLAG" == "--cluster-wide" ]; then
  SCOPE="cluster-wide"
fi

echo " Enter your key-value pairs (e.g. password=SuperSecret). Press Ctrl+D when done."

kubectl create secret generic $SECRET_NAME \
  --namespace $NAMESPACE \
  --from-env-file /dev/stdin \
  --dry-run=client \
  -o yaml |
  kubeseal \
    --controller-name=sealed-secrets-controller \
    --controller-namespace=kube-system \
    --scope $SCOPE \
    --format yaml >$SECRET_NAME.yaml

echo "✅ Done! Saved $SECRET_NAME.yaml"
