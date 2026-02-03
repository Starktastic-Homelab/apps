#!/usr/bin/env bash
set -euo pipefail

# Service scaffolding generator for homelab-platform
# Usage: ./scripts/new-service.sh

# Dependency checks
for cmd in yq; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: $cmd is required but not installed."
    exit 1
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Homelab Service Generator${NC}"
echo "================================"
echo ""

# Prompt for service details
read -p "Service name (e.g., radarr): " SERVICE_NAME
if [[ -z $SERVICE_NAME ]]; then
  echo -e "${RED}Error: Service name is required${NC}"
  exit 1
fi

# Namespace selection - scan existing categories
echo ""
echo "Available categories:"
CATEGORIES=()
i=1
for dir in "$REPO_ROOT/apps/services"/*/; do
  if [[ -d $dir ]]; then
    category=$(basename "$dir")
    CATEGORIES+=("$category")
    echo "  $i) $category"
    ((i++))
  fi
done
echo "  $i) [NEW] Create new category"

read -p "Select category [1-$i]: " CAT_CHOICE

if [[ $CAT_CHOICE -eq $i ]]; then
  read -p "Enter new category name: " CATEGORY
  read -p "Enter namespace (default: $CATEGORY): " NAMESPACE
  NAMESPACE=${NAMESPACE:-$CATEGORY}
  echo -e "${YELLOW}Will create new category: $CATEGORY${NC}"
elif [[ $CAT_CHOICE -ge 1 && $CAT_CHOICE -lt $i ]]; then
  CATEGORY="${CATEGORIES[$((CAT_CHOICE - 1))]}"
  read -p "Enter namespace (default: $CATEGORY): " NAMESPACE
  NAMESPACE=${NAMESPACE:-$CATEGORY}
else
  echo -e "${RED}Invalid choice${NC}"
  exit 1
fi

read -p "Container image (e.g., lscr.io/linuxserver/radarr:latest): " IMAGE
read -p "Container port (e.g., 7878): " PORT

# Ingress configuration
echo ""
echo -e "${YELLOW}Ingress Configuration${NC}"
read -p "Enable ingress? [Y/n]: " INGRESS_ENABLED
INGRESS_ENABLED=${INGRESS_ENABLED:-Y}

if [[ $INGRESS_ENABLED =~ ^[Yy] ]]; then
  echo "Domain type:"
  echo "  1) internal (*.internal.starktastic.net)"
  echo "  2) public (*.starktastic.net)"
  echo "  3) media (*.benplus.vip)"
  read -p "Select [1-3, default=1]: " DOMAIN_CHOICE
  DOMAIN_CHOICE=${DOMAIN_CHOICE:-1}

  case $DOMAIN_CHOICE in
    1) DOMAIN_TYPE="internal" ;;
    2) DOMAIN_TYPE="public" ;;
    3) DOMAIN_TYPE="media" ;;
    *) DOMAIN_TYPE="internal" ;;
  esac

  read -p "Require Authentik middleware? [Y/n]: " AUTH
  AUTH=${AUTH:-Y}

  read -p "Enable rate limiting? [Y/n]: " RATELIMIT
  RATELIMIT=${RATELIMIT:-Y}

  read -p "Custom subdomain (default: $SERVICE_NAME): " SUBDOMAIN
  SUBDOMAIN=${SUBDOMAIN:-$SERVICE_NAME}

  INGRESS_BLOCK="
ingress:
  enabled: true
  host: $SUBDOMAIN
  domainType: \"$DOMAIN_TYPE\"
  port: $PORT
  auth: $([[ $AUTH =~ ^[Yy] ]] && echo "true" || echo "false")
  rateLimit: $([[ $RATELIMIT =~ ^[Yy] ]] && echo "true" || echo "false")"
else
  INGRESS_BLOCK=""
fi

# Persistence configuration
echo ""
echo -e "${YELLOW}Persistence Configuration${NC}"
read -p "Need persistent storage? [Y/n]: " PERSISTENCE
PERSISTENCE=${PERSISTENCE:-Y}

# Storage class - defaults to nfs-pv, can be overridden via environment
STORAGE_CLASS="${STORAGE_CLASS:-nfs-pv}"

if [[ $PERSISTENCE =~ ^[Yy] ]]; then
  read -p "Storage size (default: 5Gi): " STORAGE_SIZE
  STORAGE_SIZE=${STORAGE_SIZE:-5Gi}

  PERSISTENCE_BLOCK="
persistence:
  config:
    existingClaim: $SERVICE_NAME-config"
else
  PERSISTENCE_BLOCK=""
fi

# Create directory structure
SERVICE_DIR="$REPO_ROOT/apps/services/$CATEGORY/$SERVICE_NAME"
mkdir -p "$SERVICE_DIR/manifests"

# Generate app.yaml
cat >"$SERVICE_DIR/app.yaml" <<EOF
name: $SERVICE_NAME
namespace: $NAMESPACE
syncWave: "5"$INGRESS_BLOCK
EOF

# Generate values.yaml
cat >"$SERVICE_DIR/values.yaml" <<EOF
controllers:
  main:
    containers:
      main:
        image:
          repository: ${IMAGE%:*}
          tag: ${IMAGE#*:}
        probes:
          liveness:
            enabled: true
            type: HTTP
            path: /
            port: $PORT
          readiness:
            enabled: true
            type: HTTP
            path: /
            port: $PORT
          startup:
            enabled: true
            type: HTTP
            path: /
            port: $PORT
            spec:
              failureThreshold: 30
              periodSeconds: 5

service:
  main:
    controller: main
    ports:
      http:
        port: $PORT
$PERSISTENCE_BLOCK
EOF

# Create empty manifests placeholder if no persistence
if [[ ! $PERSISTENCE =~ ^[Yy] ]]; then
  touch "$SERVICE_DIR/manifests/.gitkeep"
else
  # Extract PVC to manifests
  if [[ -n $PERSISTENCE_BLOCK ]]; then
    cat >"$SERVICE_DIR/manifests/pvc.yaml" <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: $SERVICE_NAME-config
  namespace: $NAMESPACE
spec:
  accessModes: ["ReadWriteMany"]
  storageClassName: $STORAGE_CLASS
  resources:
    requests:
      storage: $STORAGE_SIZE
EOF
    # Remove PVC from values.yaml (keep only persistence reference)
    cat >"$SERVICE_DIR/values.yaml" <<EOF
controllers:
  main:
    containers:
      main:
        image:
          repository: ${IMAGE%:*}
          tag: ${IMAGE#*:}
        probes:
          liveness:
            enabled: true
            type: HTTP
            path: /
            port: $PORT
          readiness:
            enabled: true
            type: HTTP
            path: /
            port: $PORT
          startup:
            enabled: true
            type: HTTP
            path: /
            port: $PORT
            spec:
              failureThreshold: 30
              periodSeconds: 5

service:
  main:
    controller: main
    ports:
      http:
        port: $PORT

persistence:
  config:
    existingClaim: $SERVICE_NAME-config
EOF
  fi
fi

echo ""
echo -e "${GREEN}✅ Service scaffolded successfully!${NC}"
echo ""
echo "Created files:"
echo "  - $SERVICE_DIR/app.yaml"
echo "  - $SERVICE_DIR/values.yaml"
echo "  - $SERVICE_DIR/manifests/"
echo ""

if [[ $INGRESS_ENABLED =~ ^[Yy] ]]; then
  case $DOMAIN_TYPE in
    internal) echo -e "URL: ${BLUE}https://$SUBDOMAIN.internal.starktastic.net${NC}" ;;
    public) echo -e "URL: ${BLUE}https://$SUBDOMAIN.starktastic.net${NC}" ;;
    media) echo -e "URL: ${BLUE}https://$SUBDOMAIN.benplus.vip${NC}" ;;
  esac
fi
