#!/bin/bash

# Usage: ./scripts/ntfy-manager.sh <command> <args>
# Example: ./scripts/ntfy-manager.sh user add ben
# Example: ./scripts/ntfy-manager.sh access /starktastic_media rw katya

# The label selector must match the bjw-s common chart default
LABEL_SELECTOR="app.kubernetes.io/name=ntfy"
NAMESPACE="operations"

# Find the pod
POD=$(kubectl get pod -n $NAMESPACE -l $LABEL_SELECTOR -o jsonpath="{.items[0].metadata.name}")

if [ -z "$POD" ]; then
  echo "❌ Ntfy pod not found in namespace '$NAMESPACE'"
  echo "   Is the app deployed and running?"
  exit 1
fi

echo "🔌 Connecting to $POD..."
# Execute the ntfy command inside the container
kubectl exec -it -n $NAMESPACE $POD -- ntfy "$@"
