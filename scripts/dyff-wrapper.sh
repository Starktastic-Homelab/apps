#!/bin/sh

# Wrapper to pass arguments ($@) from kubectl to dyff
# This avoids kubectl's aggressive sanitization of environment variables
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
  --exclude "/spec/sources/targetRevision" \
  "$@"
