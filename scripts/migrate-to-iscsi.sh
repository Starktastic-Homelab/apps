#!/bin/bash
set -euo pipefail

# =============================================================================
# NFS → iSCSI Migration Script
# Automates steps 2-4, 6-11 from the migration plan
# Run AFTER merging the packer PR and BEFORE/AFTER merging the apps PR
# =============================================================================

SSH_KEY="$HOME/Developer/homelab/id_rsa"
SSH_OPTS="-o StrictHostKeyChecking=no -i $SSH_KEY"
SSH_USER="debian"
NFS_SERVER="10.9.8.30"
NFS_BASE_PATH="/mnt/apps/pv"

NODES=(
  "10.9.9.50"  # kube-master-01
  "10.9.9.51"  # kube-worker-01
  "10.9.9.52"  # kube-worker-02
)

# ArgoCD app names that own migrating PVCs
ARGOCD_APPS=(
  home-assistant zigbee2mqtt mosquitto
  jellyfin immich calibre-web
  navidrome radarr sonarr bazarr lidarr prowlarr qbittorrent
  audiobookshelf seerr autobrr lingarr libretranslate shelfmark
  radarr-ru sonarr-ru qbittorrent-ru seerr-ru
  paperless-ngx mealie vaultwarden bytestash stirling-pdf changedetection microbin
  ntfy
  postgres redis pgadmin
  crowdsec
  kube-prometheus-stack loki tempo
)

# ---------------------------------------------------------------------------
# Static manifest PVCs (created by ArgoCD from manifests/ directories)
# Format: "namespace/pvc-name"
# ---------------------------------------------------------------------------
STATIC_PVCS=(
  "home-automation/home-assistant-config"
  "home-automation/zigbee2mqtt-config"
  "home-automation/mosquitto-config"
  "media/jellyfin-config"
  "media/immich-pgdata"
  "media/immich-model-cache"
  "operations/paperless-ngx-data"
  "operations/mealie-data"
  "operations/vaultwarden-data"
  "operations/bytestash-data"
  "operations/stirling-pdf-config"
  "operations/changedetection-data"
  "operations/microbin-config"
)

# ---------------------------------------------------------------------------
# Helm-managed PVCs (auto-created by StatefulSets or Helm charts)
# Format: "namespace/pvc-name"
# ---------------------------------------------------------------------------
HELM_PVCS=(
  # media — app-template config PVCs (Deployment-managed)
  "media/navidrome-config"
  "media/radarr-config"
  "media/sonarr-config"
  "media/bazarr-config"
  "media/lidarr-config"
  "media/prowlarr-config"
  "media/qbittorrent-config"
  "media/audiobookshelf-config"
  "media/seerr-config"
  "media/autobrr-config"
  "media/calibre-web-config"
  "media/shelfmark-config"
  "media/lingarr-lingarr-config"
  "media/libretranslate-libretranslate-models"
  # media — -ru variant config PVCs
  "media/radarr-ru-config"
  "media/sonarr-ru-config"
  "media/qbittorrent-ru-config"
  "media/seerr-ru-config"
  # operations — ntfy PVCs
  "operations/ntfy-config"
  "operations/ntfy-cache"
  # databases
  "databases/data-postgres-postgresql-0"
  "databases/redis-data-redis-master-0"
  "databases/pgadmin-pgadmin4"
  # crowdsec
  "crowdsec/crowdsec-lapi-data"
  # monitoring
  "monitoring/prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0"
  "monitoring/alertmanager-kube-prometheus-stack-alertmanager-db-alertmanager-kube-prometheus-stack-alertmanager-0"
  "monitoring/kube-prometheus-stack-grafana"
  "monitoring/storage-loki-0"
  "monitoring/tempo"
)

# ---------------------------------------------------------------------------
# Helm-managed StatefulSets that must be deleted alongside their PVCs
# Format: "namespace/type/name"
# ---------------------------------------------------------------------------
HELM_WORKLOADS=(
  "databases/statefulset/postgres-postgresql"
  "databases/statefulset/redis-master"
  "monitoring/statefulset/prometheus-kube-prometheus-stack-prometheus"
  "monitoring/statefulset/alertmanager-kube-prometheus-stack-alertmanager"
  "monitoring/statefulset/loki"
)

# ---------------------------------------------------------------------------
# Deployments to scale down
# Format: "namespace/deployment-name"
# ---------------------------------------------------------------------------
DEPLOYMENTS=(
  # home-automation
  "home-automation/home-assistant"
  "home-automation/zigbee2mqtt"
  "home-automation/mosquitto"
  # media — core services
  "media/jellyfin"
  "media/immich-main"
  "media/immich-machine-learning"
  "media/immich-postgres"
  "media/calibre-web"
  "media/shelfmark"
  # media — arr stack + tools
  "media/navidrome"
  "media/radarr"
  "media/sonarr"
  "media/bazarr"
  "media/lidarr"
  "media/prowlarr"
  "media/qbittorrent"
  "media/audiobookshelf"
  "media/seerr"
  "media/autobrr"
  "media/lingarr"
  "media/libretranslate"
  # media — -ru variants
  "media/radarr-ru"
  "media/sonarr-ru"
  "media/qbittorrent-ru"
  "media/seerr-ru"
  # operations
  "operations/paperless-ngx"
  "operations/mealie"
  "operations/vaultwarden"
  "operations/bytestash"
  "operations/stirling-pdf"
  "operations/changedetection"
  "operations/microbin"
  "operations/ntfy"
  # databases
  "databases/pgadmin-pgadmin4"
  # monitoring
  "monitoring/kube-prometheus-stack-grafana"
  "monitoring/tempo"
)

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
step() { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

pause() {
  echo ""
  read -rp "Press Enter to continue (or Ctrl+C to abort)..."
  echo ""
}

# =============================================================================
# Step 2: Verify open-iscsi is installed and running on all nodes
# =============================================================================
step_verify_iscsi() {
  step "STEP 2: Verifying open-iscsi on all nodes"

  for node in "${NODES[@]}"; do
    echo -n "  $node — open-iscsi: "
    if ssh $SSH_OPTS "$SSH_USER@$node" "dpkg -l open-iscsi 2>/dev/null | grep -q ^ii" 2>/dev/null; then
      log "installed"
    else
      err "NOT installed — run: ssh $SSH_USER@$node 'sudo apt install -y open-iscsi'"
      exit 1
    fi

    echo -n "  $node — iscsid:     "
    if ssh $SSH_OPTS "$SSH_USER@$node" "systemctl is-active iscsid" 2>/dev/null | grep -q active; then
      log "running"
    else
      err "NOT running — run: ssh $SSH_USER@$node 'sudo systemctl enable --now iscsid'"
      exit 1
    fi
  done
}

# =============================================================================
# Step 3: Pause ArgoCD auto-sync on all affected apps
# =============================================================================
step_pause_argocd() {
  step "STEP 3: Pausing ArgoCD auto-sync on affected apps"

  for app in "${ARGOCD_APPS[@]}"; do
    echo -n "  $app: "
    if kubectl -n argocd patch application "$app" \
      --type merge -p '{"spec":{"syncPolicy":null}}' >/dev/null 2>&1; then
      log "paused"
    else
      warn "not found or already paused"
    fi
  done
}

# =============================================================================
# Step 4: Scale down all affected workloads
# =============================================================================
step_scale_down() {
  step "STEP 4: Scaling down all affected workloads"

  for item in "${DEPLOYMENTS[@]}"; do
    ns="${item%%/*}"
    name="${item#*/}"
    echo -n "  deploy/$name ($ns): "
    if kubectl -n "$ns" scale deploy/"$name" --replicas=0 >/dev/null 2>&1; then
      log "scaled to 0"
    else
      warn "not found or already at 0"
    fi
  done

  for item in "${HELM_WORKLOADS[@]}"; do
    ns="${item%%/*}"
    rest="${item#*/}"
    kind="${rest%%/*}"
    name="${rest#*/}"
    if [[ "$kind" == "statefulset" ]]; then
      echo -n "  sts/$name ($ns): "
      if kubectl -n "$ns" scale sts/"$name" --replicas=0 >/dev/null 2>&1; then
        log "scaled to 0"
      else
        warn "not found or already at 0"
      fi
    fi
  done

  echo ""
  echo "  Waiting for pods to terminate..."
  for attempt in $(seq 1 12); do
    local terminating
    terminating=$(kubectl get pods -A --no-headers 2>/dev/null | grep -c Terminating || echo 0)
    [[ "$terminating" -eq 0 ]] && break
    echo "    $terminating pods still terminating (attempt $attempt/12)..."
    sleep 10
  done
  log "All workloads scaled down"
}

# =============================================================================
# Step 6: Sync democratic-csi via ArgoCD
# =============================================================================
step_deploy_democratic_csi() {
  step "STEP 6: Deploying democratic-csi"

  kubectl -n argocd patch application democratic-csi \
    --type merge -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true},"syncOptions":["CreateNamespace=true","ServerSideApply=true"]}}}' \
    >/dev/null 2>&1 || true

  echo "  Waiting for democratic-csi to sync..."
  for i in $(seq 1 24); do
    if kubectl get storageclass iscsi-pv >/dev/null 2>&1; then
      break
    fi
    echo "    Attempt $i/24: waiting for StorageClass..."
    sleep 10
  done

  echo -n "  Verifying iscsi-pv StorageClass: "
  if kubectl get storageclass iscsi-pv >/dev/null 2>&1; then
    log "exists"
  else
    err "iscsi-pv StorageClass not found — check democratic-csi deployment"
    echo "  Run: kubectl -n democratic-csi get pods"
    echo "  Run: kubectl -n democratic-csi logs -l app.kubernetes.io/name=democratic-csi --tail=50"
    exit 1
  fi

  echo -n "  Verifying democratic-csi pods: "
  if kubectl -n democratic-csi wait --for=condition=Ready pod -l app.kubernetes.io/name=democratic-csi --timeout=120s >/dev/null 2>&1; then
    log "all pods ready"
  else
    err "democratic-csi pods not ready"
    kubectl -n democratic-csi get pods
    exit 1
  fi
}

# =============================================================================
# Step 7+8: Delete old NFS PVCs
# =============================================================================
step_delete_old_pvcs() {
  step "STEP 7-8: Deleting old NFS PVCs"
  warn "Data is safe on TrueNAS at $NFS_BASE_PATH (reclaimPolicy: Retain)"
  echo ""

  echo "  Deleting Helm-managed StatefulSets..."
  for item in "${HELM_WORKLOADS[@]}"; do
    ns="${item%%/*}"
    rest="${item#*/}"
    kind="${rest%%/*}"
    name="${rest#*/}"
    echo -n "    $kind/$name ($ns): "
    if kubectl -n "$ns" delete "$kind/$name" --ignore-not-found >/dev/null 2>&1; then
      log "deleted"
    else
      warn "not found"
    fi
  done

  echo ""
  echo "  Deleting static manifest PVCs..."
  for item in "${STATIC_PVCS[@]}"; do
    ns="${item%%/*}"
    name="${item#*/}"
    echo -n "    $name ($ns): "
    if kubectl -n "$ns" delete pvc "$name" --ignore-not-found >/dev/null 2>&1; then
      log "deleted"
    else
      warn "not found"
    fi
  done

  echo ""
  echo "  Deleting Helm-managed PVCs..."
  for item in "${HELM_PVCS[@]}"; do
    ns="${item%%/*}"
    name="${item#*/}"
    echo -n "    $name ($ns): "
    if kubectl -n "$ns" delete pvc "$name" --ignore-not-found >/dev/null 2>&1; then
      log "deleted"
    else
      warn "not found"
    fi
  done
}

# =============================================================================
# Step 9: Re-enable ArgoCD auto-sync
# =============================================================================
step_reenable_argocd() {
  step "STEP 9: Re-enabling ArgoCD auto-sync"

  SYNC_POLICY='{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true},"syncOptions":["CreateNamespace=true","ServerSideApply=true"],"retry":{"limit":5,"backoff":{"duration":"10s","factor":2,"maxDuration":"3m"}}}}}'

  for app in "${ARGOCD_APPS[@]}"; do
    echo -n "  $app: "
    if kubectl -n argocd patch application "$app" \
      --type merge -p "$SYNC_POLICY" >/dev/null 2>&1; then
      log "auto-sync restored"
    else
      warn "not found"
    fi
  done

  echo ""
  echo "  Waiting for ArgoCD to recreate PVCs and workloads..."
  sleep 30

  echo "  Checking PVC binding status..."
  local all_bound=false
  for i in $(seq 1 60); do
    local pending
    pending=$(kubectl get pvc -A --no-headers 2>/dev/null \
      | grep -v Bound \
      | grep -v "media-library\|filebrowser\|cwa-book-ingest\|cert-backup\|pg-backup" \
      | wc -l)
    if [[ "$pending" -eq 0 ]]; then
      all_bound=true
      break
    fi
    echo "    Attempt $i/60: $pending PVCs still pending..."
    sleep 10
  done

  if $all_bound; then
    log "All PVCs bound"
  else
    warn "Some PVCs still not bound after 10 minutes — check manually"
    kubectl get pvc -A | grep -v Bound
  fi
}

# =============================================================================
# Step 10: Migrate data from NFS to new iSCSI PVCs
# =============================================================================
step_migrate_data() {
  step "STEP 10: Migrating data from NFS to new iSCSI PVCs"

  warn "Scaling down workloads for exclusive PVC access during data copy..."
  for item in "${DEPLOYMENTS[@]}"; do
    ns="${item%%/*}"
    name="${item#*/}"
    kubectl -n "$ns" scale deploy/"$name" --replicas=0 >/dev/null 2>&1 || true
  done
  for item in "${HELM_WORKLOADS[@]}"; do
    ns="${item%%/*}"
    rest="${item#*/}"
    kind="${rest%%/*}"
    name="${rest#*/}"
    [[ "$kind" == "statefulset" ]] && kubectl -n "$ns" scale sts/"$name" --replicas=0 >/dev/null 2>&1 || true
  done
  sleep 15

  ALL_PVCS=("${STATIC_PVCS[@]}" "${HELM_PVCS[@]}")

  for item in "${ALL_PVCS[@]}"; do
    ns="${item%%/*}"
    pvc_name="${item#*/}"
    nfs_path="$NFS_BASE_PATH/$ns/$pvc_name"

    echo -n "  $pvc_name ($ns): "

    if ! kubectl -n "$ns" get pvc "$pvc_name" -o jsonpath='{.status.phase}' 2>/dev/null | grep -q Bound; then
      warn "PVC not bound, skipping"
      continue
    fi

    JOB_NAME=$(echo "migrate-${pvc_name}" | sed 's/[^a-z0-9-]/-/g' | cut -c1-63 | sed 's/-$//')

    cat <<JOBEOF | kubectl apply -f - >/dev/null 2>&1
apiVersion: batch/v1
kind: Job
metadata:
  name: $JOB_NAME
  namespace: $ns
spec:
  ttlSecondsAfterFinished: 600
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: debian:bookworm-slim
          command:
            - /bin/bash
            - -c
            - |
              set -euo pipefail
              apt-get update -qq && apt-get install -y -qq rsync nfs-common >/dev/null 2>&1
              mkdir -p /mnt/nfs
              if ! mount -t nfs -o ro,nolock ${NFS_SERVER}:${nfs_path} /mnt/nfs 2>/dev/null; then
                echo "WARN: NFS path not found at ${nfs_path}, nothing to migrate"
                exit 0
              fi
              if [ -z "\$(ls -A /mnt/nfs 2>/dev/null)" ]; then
                echo "NFS directory empty, nothing to migrate"
                umount /mnt/nfs || true
                exit 0
              fi
              echo "Copying data from ${nfs_path} ..."
              rsync -a /mnt/nfs/ /mnt/iscsi/
              echo "Done. Synced \$(du -sh /mnt/iscsi | cut -f1) of data."
              umount /mnt/nfs || true
          securityContext:
            privileged: true
          volumeMounts:
            - name: iscsi-vol
              mountPath: /mnt/iscsi
      volumes:
        - name: iscsi-vol
          persistentVolumeClaim:
            claimName: $pvc_name
JOBEOF
    log "job/$JOB_NAME created"
  done

  echo ""
  echo "  Waiting for migration jobs to complete (up to 10 min each)..."
  for item in "${ALL_PVCS[@]}"; do
    ns="${item%%/*}"
    pvc_name="${item#*/}"
    JOB_NAME=$(echo "migrate-${pvc_name}" | sed 's/[^a-z0-9-]/-/g' | cut -c1-63 | sed 's/-$//')

    echo -n "  $JOB_NAME ($ns): "
    if kubectl -n "$ns" wait --for=condition=complete "job/$JOB_NAME" --timeout=600s >/dev/null 2>&1; then
      log "completed"
    elif kubectl -n "$ns" get job "$JOB_NAME" >/dev/null 2>&1; then
      warn "check logs: kubectl -n $ns logs job/$JOB_NAME"
    else
      warn "job not found"
    fi
  done
}

# =============================================================================
# Step 10b: Restore workloads via ArgoCD hard refresh
# =============================================================================
step_restore_workloads() {
  step "STEP 10b: Restoring workloads"

  for app in "${ARGOCD_APPS[@]}"; do
    kubectl -n argocd patch application "$app" \
      --type merge -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}' \
      >/dev/null 2>&1 || true
  done

  echo "  Waiting 60s for ArgoCD to reconcile..."
  sleep 60
}

# =============================================================================
# Step 11: Verification
# =============================================================================
step_verify() {
  step "STEP 11: Verification"

  echo ""
  echo "  StorageClasses:"
  kubectl get storageclass
  echo ""

  echo "  PVC Status (config PVCs should be iscsi-pv):"
  kubectl get pvc -A --sort-by='.metadata.namespace'
  echo ""

  echo "  Pod Status (checking for issues):"
  local problem_pods
  problem_pods=$(kubectl get pods -A --no-headers 2>/dev/null | grep -Ev "Running|Completed|migrate-" || true)
  if [[ -z "$problem_pods" ]]; then
    log "All pods Running or Completed"
  else
    warn "Some pods have issues:"
    echo "$problem_pods"
  fi
  echo ""

  echo "  Recent probe failures:"
  local unhealthy
  unhealthy=$(kubectl get events -A --field-selector reason=Unhealthy --sort-by='.lastTimestamp' 2>/dev/null | tail -5 || true)
  if [[ -z "$unhealthy" ]]; then
    log "No probe failures"
  else
    echo "$unhealthy"
  fi
}

# =============================================================================
# Cleanup migration jobs
# =============================================================================
step_cleanup() {
  step "CLEANUP: Removing migration jobs"

  ALL_PVCS=("${STATIC_PVCS[@]}" "${HELM_PVCS[@]}")
  for item in "${ALL_PVCS[@]}"; do
    ns="${item%%/*}"
    pvc_name="${item#*/}"
    JOB_NAME=$(echo "migrate-${pvc_name}" | sed 's/[^a-z0-9-]/-/g' | cut -c1-63 | sed 's/-$//')
    kubectl -n "$ns" delete job "$JOB_NAME" --ignore-not-found >/dev/null 2>&1 || true
  done
  log "Migration jobs cleaned up"
}

# =============================================================================
# Main
# =============================================================================
main() {
  echo "╔═══════════════════════════════════════════════════════╗"
  echo "║          NFS → iSCSI Migration Script                ║"
  echo "║          Homelab K3s Cluster                         ║"
  echo "╚═══════════════════════════════════════════════════════╝"
  echo ""
  warn "This script will cause downtime for ALL services"
  warn "Make sure the apps PR is MERGED before running step 6+"
  echo ""
  echo "Steps:"
  echo "  2)    Verify open-iscsi on nodes"
  echo "  3)    Pause ArgoCD auto-sync"
  echo "  4)    Scale down workloads"
  echo "        ── MERGE APPS PR #303 NOW ──"
  echo "  6)    Deploy democratic-csi"
  echo "  7-8)  Delete old NFS PVCs"
  echo "  9)    Re-enable ArgoCD (recreates PVCs + workloads)"
  echo "  10)   Migrate data from NFS → iSCSI"
  echo "  10b)  Restore workloads"
  echo "  11)   Verify"
  echo ""

  if [[ "${1:-}" == "--step" ]]; then
    case "${2:-}" in
      2) step_verify_iscsi ;;
      3) step_pause_argocd ;;
      4) step_scale_down ;;
      6) step_deploy_democratic_csi ;;
      7|8) step_delete_old_pvcs ;;
      9) step_reenable_argocd ;;
      10) step_migrate_data ;;
      10b) step_restore_workloads ;;
      11) step_verify ;;
      cleanup) step_cleanup ;;
      *) echo "Unknown step: ${2:-}"; echo "Usage: $0 [--step <2|3|4|6|7|9|10|10b|11|cleanup>]"; exit 1 ;;
    esac
    exit 0
  fi

  # ── Pre-merge steps ──
  step_verify_iscsi
  pause

  step_pause_argocd
  pause

  step_scale_down
  pause

  echo ""
  echo "╔═══════════════════════════════════════════════════════╗"
  echo "║  >>> MERGE APPS PR #303 NOW <<<                      ║"
  echo "║  https://github.com/Starktastic-Homelab/apps/pull/303║"
  echo "╚═══════════════════════════════════════════════════════╝"
  pause

  # ── Post-merge steps ──
  step_deploy_democratic_csi
  pause

  step_delete_old_pvcs
  pause

  step_reenable_argocd
  pause

  step_migrate_data
  pause

  step_restore_workloads

  step_verify

  echo ""
  echo "╔═══════════════════════════════════════════════════════╗"
  echo "║  Migration complete!                                 ║"
  echo "║  Run: $0 --step cleanup                              ║"
  echo "╚═══════════════════════════════════════════════════════╝"
}

main "$@"
