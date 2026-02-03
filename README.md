# Homelab Platform

GitOps repository for managing a Kubernetes homelab using ArgoCD with an App-of-Apps pattern.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Bootstrap                                │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  foundation  │  │ infra-configs│  │     ApplicationSet     │ │
│  │  (wave -10)  │  │   (wave 1)   │  │     platform.yaml      │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────────┘ │
└─────────┼─────────────────┼─────────────────────┼───────────────┘
          │                 │                     │
          ▼                 ▼                     ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐
│   Foundation    │  │     Configs     │  │      Controllers        │
│                 │  │                 │  │                         │
│  • Namespaces   │  │  • Ingresses    │  │  • Helm Charts          │
│  • RBAC         │  │  • Certs        │  │  • Values + Manifests   │
│                 │  │  • Middlewares  │  │                         │
└─────────────────┘  └─────────────────┘  └─────────────────────────┘
```

## 📁 Directory Structure

```
apps/
├── bootstrap/              # Entry point - deploy these first
│   ├── foundation.yaml     # Creates namespaces (sync-wave: -10)
│   ├── infra-configs.yaml  # Deploys configs after controllers (sync-wave: 1)
│   └── appsets/
│       └── platform.yaml   # Unified ApplicationSet for infra + services
│
├── foundation/             # Namespace definitions
│   └── namespaces/
│
├── infrastructure/
│   ├── configs/            # Non-Helm resources (ingresses, certs, etc.)
│   ├── controllers/        # Helm-based apps (each has app.yaml + values.yaml)
│   │   ├── authentik/
│   │   ├── databases/
│   │   └── traefik/
│   └── system/             # Cluster-level components
│       ├── cert-manager/
│       ├── intel-gpu/
│       ├── nfs-provisioner/
│       └── sealed-secrets/
│
├── services/               # User-facing applications
│   ├── media/              # Prowlarr, qBittorrent, Jellyfin, etc.
│   └── operations/         # ntfy, monitoring, etc.
│
├── templates/
│   ├── common.yaml         # Shared Helm values for services (app-template)
│   ├── infra-common.yaml   # Shared Helm values for infrastructure
│   └── ingress-chart/      # Dynamic IngressRoute generator
│
└── scripts/                # Utility scripts
    ├── new-service.sh      # Scaffold a new service
    ├── seal.sh             # Seal secrets with kubeseal
    └── dyff-wrapper.sh     # YAML diff for CI
```

## 🚀 Bootstrap Order

The deployment follows a strict ordering via ArgoCD sync-waves:

| Wave | Component | Description |
|------|-----------|-------------|
| -10 | `foundation` | Namespaces and basic RBAC |
| 0 | `platform` ApplicationSet (infrastructure) | Infrastructure controllers (Traefik, DBs, Auth) |
| 1 | `infra-configs` | Ingress routes, certificates, middlewares |
| 2+ | `platform` ApplicationSet (services) | User applications |

## 🔐 Secret Management

This repository uses [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) for encrypting secrets in Git.

### Sealing a Secret

```bash
# Namespace-scoped (strict) - default
./scripts/seal.sh <secret-name> <namespace>

# Cluster-wide scope
./scripts/seal.sh <secret-name> <namespace> --cluster-wide
```

The script will prompt you to enter key-value pairs interactively (press Ctrl+D when done).

## 📦 Adding a New Application

### Infrastructure Controller (Helm-based)

1. Create directory: `apps/infrastructure/controllers/<name>/`
2. Add `app.yaml`:
   ```yaml
   name: my-app
   namespace: my-namespace
   syncWave: "0"
   chart:
     repo: https://charts.example.com
     name: my-chart
     version: 1.0.0
   # Optional: ignore auto-generated fields
   ignoreDifferences:
     - group: ""
       kind: Secret
       jsonPointers:
         - /data/password
   ```
3. Add `values.yaml` with Helm values
4. Add `manifests/` folder (can contain `.gitkeep` if empty, or extra manifests)

### Service (using app-template)

1. Create directory: `apps/services/<category>/<name>/`
2. Add `app.yaml`:
   ```yaml
   name: my-service
   namespace: my-namespace
   syncWave: "5"
   
   ingress:
     enabled: true
     host: my-service          # Subdomain (or empty for root domain)
     domainType: "internal"    # public | internal | media
     port: 8080
     auth: true                # Authentik ForwardAuth middleware
     rateLimit: true           # Rate limiting middleware
   ```
3. Add `values.yaml` (extends `templates/common.yaml`)
4. Add `manifests/` folder for PVCs and any extra manifests

Or use the scaffolding script:
```bash
./scripts/new-service.sh
```

## 🧩 Shared Defaults

### Common Values (templates/common.yaml)

All services using `app-template` inherit these defaults:

```yaml
global:
  storageClass: "nfs-pv"
  domains:
    public: "starktastic.net"
    internal: "internal.starktastic.net"
    media: "benplus.vip"
  defaultTlsSecret: "starktastic-net-tls"

controllers:
  main:
    containers:
      main:
        env:
          TZ: "Asia/Jerusalem"
          PUID: "1000"
          PGID: "1000"

persistence:
  config:
    enabled: true
    type: persistentVolumeClaim
    storageClass: "nfs-pv"
    size: 1Gi
    accessMode: ReadWriteMany
    globalMounts:
      - path: /config
```

Apps can override or extend with additional volumes in their `values.yaml`.

### Ingress Chart (templates/ingress-chart/)

The ingress-chart automatically generates Traefik IngressRoutes based on `app.yaml` configuration:

| Field | Default | Description |
|-------|---------|-------------|
| `host` | (required) | Subdomain, or empty for root domain |
| `domainType` | `internal` | `public`, `internal`, or `media` |
| `port` | `80` | Service port |
| `auth` | `false` | Enable Authentik ForwardAuth middleware |
| `rateLimit` | `false` | Enable rate limiting middleware |
| `serviceName` | `<name>` | Override the target service name |

#### Domain Types

| Type | Domain | Entrypoint | LoadBalancer IP |
|------|--------|------------|-----------------|
| `public` | `*.starktastic.net` | `websecure` | `10.9.8.90` |
| `internal` | `*.internal.starktastic.net` | `websec-int` | `10.9.9.90` |
| `media` | `*.benplus.vip` | `websecure` | `10.9.8.90` |

## 🔧 Configuration

### ApplicationSet Features

- **Auto-sync**: Changes in Git are automatically applied
- **Self-heal**: Drift from Git state is corrected
- **Server-Side Apply**: Reduces conflicts with controllers
- **Pruning**: Removed resources are deleted

### ignoreDifferences

For apps that generate secrets or have controller-managed fields, add to `app.yaml`:

```yaml
ignoreDifferences:
  - group: ""
    kind: Secret
    jsonPointers:
      - /data/password
```

## 🛠️ Development

### Prerequisites

- ArgoCD installed with access to this repository
- `kubeseal` CLI for secret management
- `kubectl` configured for your cluster

### Validating Changes

```bash
# Lint YAML files
yamllint .

# Diff changes (used in CI)
./scripts/dyff-wrapper.sh
```

## 📚 Related Repositories

- `homelab-ansible` - K3s cluster provisioning
- `homelab-terraform` - VM infrastructure
- `homelab-packer` - Base image creation

## 🌐 Network Configuration

### IP Allocation

| Service | IP Address | Purpose |
|---------|------------|----------|
| NFS Server | `10.9.8.30` | Persistent storage backend |
| Traefik External | `10.9.8.90` | Public-facing ingress (LoadBalancer) |
| Traefik Internal | `10.9.9.90` | Internal services ingress (LoadBalancer) |
| qBittorrent | `10.9.8.91` | BitTorrent client (LoadBalancer) |

### VLANs

| VLAN | CIDR | Purpose |
|------|------|----------|
| MGMT | `10.9.9.0/24` | Management network |
| Services | `10.9.8.0/24` | Service network |
| Pods | `10.42.0.0/16` | Kubernetes pod network |

### Domains

| Domain | Purpose | LoadBalancer IP |
|--------|----------|-----------------|
| `*.starktastic.net` | Public external services | `10.9.8.90` |
| `*.internal.starktastic.net` | Internal services (behind Authentik) | `10.9.9.90` |
| `*.benplus.vip` | Media services (Jellyfin, Jellyseerr) | `10.9.8.90` |

### Other Configuration

| Setting | Value | Location |
|---------|-------|----------|
| Timezone | `Asia/Jerusalem` | `apps/templates/common.yaml` |
| PUID/PGID | `1000/1000` | `apps/templates/common.yaml` |
| Storage Class | `nfs-pv` | `apps/templates/common.yaml`, `apps/templates/infra-common.yaml` |
| Admin Email | `benfaingold@gmail.com` | ClusterIssuer, pgadmin |

## 🎮 GPU Support

Intel GPU passthrough is enabled for hardware transcoding:

### Components

- **intel-device-operator** (`apps/infrastructure/system/intel-device-operator/`) - Manages Intel device plugins
- **intel-gpu-plugin** (`apps/infrastructure/system/intel-gpu/`) - Exposes GPU resources to pods

### Usage

To use GPU in a service, add resource requests:

```yaml
controllers:
  main:
    containers:
      main:
        resources:
          requests:
            gpu.intel.com/i915: "1"
          limits:
            gpu.intel.com/i915: "1"
```

Worker nodes with Intel GPUs are labeled automatically by the device operator.

## 📼 Media Storage

### Static Media Volume

A dedicated 10Ti PV is provisioned for media storage:

| Resource | Details |
|----------|---------|
| NFS Server | `10.9.8.30:/mnt/main/media` |
| PV Name | `media-storage` |
| PVC | `media-pvc` (namespace: `media`) |
| Access Mode | `ReadWriteMany` |

### Mounting in Services

```yaml
persistence:
  media:
    existingClaim: media-pvc
    globalMounts:
      - path: /media
```

### Dynamic Storage (nfs-pv)

For application configs and caches, use the `nfs-pv` StorageClass which dynamically provisions NFS volumes.

## 🔧 Troubleshooting

### PostgreSQL postmaster.pid Lock

If PostgreSQL fails to start with "postmaster.pid already exists", the init container in `postgres/values.yaml` automatically removes stale lock files. This can happen after ungraceful NFS disconnections.

### Sealed Secrets Scope

Sealed secrets are namespace-scoped by default. If you get decryption errors:
1. Ensure the secret was sealed for the correct namespace
2. Use `--cluster-wide` flag if the secret needs to be used across namespaces

### ArgoCD Sync Wave Ordering

If resources fail to sync due to missing dependencies:
1. Check sync-wave annotations match the expected order
2. Ensure namespaces are created in foundation (wave -10)
3. Verify controllers are deployed before configs (wave 0 before wave 1)

### NFS Connectivity

If PVCs are stuck in Pending:
1. Verify NFS server (`10.9.8.30`) is accessible from nodes
2. Check `nfs-provisioner` pods are running
3. Verify StorageClass `nfs-pv` exists
