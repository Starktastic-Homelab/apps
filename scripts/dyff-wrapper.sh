#!/bin/sh

LIVE="$1"
MERGED="$2"

CLEAN_LIVE=$(mktemp)
CLEAN_MERGED=$(mktemp)

yq 'del(.spec.sources[]?.targetRevision)' "$LIVE" > "$CLEAN_LIVE"
yq 'del(.spec.sources[]?.targetRevision)' "$MERGED" > "$CLEAN_MERGED"

# 4. Run dyff on the CLEAN files
#    We still keep the standard metadata excludes just in case
exec dyff between \
  --omit-header \
  --set-exit-code \
  --ignore-order-changes \
  --exclude "/metadata/generation" \
  --exclude "/metadata/resourceVersion" \
  --exclude "/metadata/managedFields" \
  --exclude "/metadata/uid" \
  --exclude "/metadata/creationTimestamp" \
  --exclude "/metadata/annotations/kubectl.kubernetes.io/last-applied-configuration" \
  --exclude "/metadata/annotations/argocd.argoproj.io/tracking-id" \
  --exclude "/status" \
  --exclude "/spec/source/targetRevision" \
  "$CLEAN_LIVE" "$CLEAN_MERGED"
