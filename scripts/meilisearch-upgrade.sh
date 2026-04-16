#!/bin/bash
set -euo pipefail

# Usage: ./scripts/meilisearch-upgrade.sh [--dry-run]
#
# Prepares Meilisearch for a version upgrade by wiping its PVC data.
# Karakeep will re-index into the new Meilisearch instance on startup.
#
# Run this BEFORE merging a Renovate Meilisearch version bump PR.

DRY_RUN=false
if [[ ${1:-} == "--dry-run" ]]; then
  DRY_RUN=true
  echo "🔍 Dry-run mode — no changes will be made"
fi

NAMESPACE="operations"
APP_NAME="karakeep"
PVC_NAME="karakeep-meilisearch"
LABEL_SELECTOR="app.kubernetes.io/name=$APP_NAME"

# Verify the PVC exists in the cluster
if ! kubectl get pvc -n "$NAMESPACE" "$PVC_NAME" &>/dev/null; then
  echo "❌ PVC '$PVC_NAME' not found in namespace '$NAMESPACE'"
  exit 1
fi

echo "📦 Meilisearch upgrade preparation"
echo "   Namespace:  $NAMESPACE"
echo "   App:        $APP_NAME"
echo "   PVC:        $PVC_NAME"
echo ""

# Step 1: Scale down
echo "⏬ Scaling down $APP_NAME..."
if [[ $DRY_RUN == true ]]; then
  echo "   (dry-run) kubectl scale deployment/$APP_NAME -n $NAMESPACE --replicas=0"
else
  kubectl scale deployment/"$APP_NAME" -n "$NAMESPACE" --replicas=0
  echo "⏳ Waiting for pods to terminate..."
  kubectl wait --for=delete pod -n "$NAMESPACE" -l "$LABEL_SELECTOR" --timeout=120s 2>/dev/null || true
fi

# Step 2: Wipe Meilisearch data via a temporary pod
# NFS-backed PVCs retain data across delete/recreate, so we must clear the contents directly.
echo "🗑️  Wiping Meilisearch data from PVC '$PVC_NAME'..."
if [[ $DRY_RUN == true ]]; then
  echo "   (dry-run) kubectl run meili-cleanup --rm -it ... rm -rf /meili_data/*"
else
  kubectl run meili-cleanup --rm -i --restart=Never \
    -n "$NAMESPACE" \
    --image=busybox:latest \
    --overrides="{
      \"spec\": {
        \"containers\": [{
          \"name\": \"meili-cleanup\",
          \"image\": \"busybox:latest\",
          \"command\": [\"sh\", \"-c\", \"rm -rf /meili_data/* && echo cleared\"],
          \"volumeMounts\": [{\"name\": \"data\", \"mountPath\": \"/meili_data\"}]
        }],
        \"volumes\": [{
          \"name\": \"data\",
          \"persistentVolumeClaim\": {\"claimName\": \"$PVC_NAME\"}
        }]
      }
    }"
fi

# Step 3: Scale back up
echo "⏫ Scaling up $APP_NAME..."
if [[ $DRY_RUN == true ]]; then
  echo "   (dry-run) kubectl scale deployment/$APP_NAME -n $NAMESPACE --replicas=1"
else
  kubectl scale deployment/"$APP_NAME" -n "$NAMESPACE" --replicas=1
  echo "⏳ Waiting for pod to be created..."
  until kubectl get pod -n "$NAMESPACE" -l "$LABEL_SELECTOR" -o name 2>/dev/null | grep -q .; do
    sleep 2
  done
  echo "⏳ Waiting for pod readiness..."
  kubectl wait --for=condition=ready pod -n "$NAMESPACE" -l "$LABEL_SELECTOR" --timeout=300s
fi

echo ""
echo "✅ Meilisearch PVC wiped and $APP_NAME restarted"
echo "   Karakeep will re-index into the new Meilisearch on startup."
echo ""
echo "   Next steps:"
echo "   1. Merge the Renovate Meilisearch PR"
echo "   2. Wait for ArgoCD to sync the new image"
echo "   3. Verify: kubectl exec -n $NAMESPACE \$(kubectl get pod -n $NAMESPACE -l $LABEL_SELECTOR -o jsonpath='{.items[0].metadata.name}') -c meilisearch -- wget -qO- http://localhost:7700/health"
