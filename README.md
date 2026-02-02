# Homelab Platform

GitOps repository for managing a Kubernetes homelab using ArgoCD with an App-of-Apps pattern.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Bootstrap                                │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │  foundation  │  │ infra-configs│  │     ApplicationSets    │ │
│  │  (wave -10)  │  │   (wave 1)   │  │  infra.yaml services   │ │
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
│       ├── infra.yaml      # ApplicationSet for infrastructure controllers
│       └── services.yaml   # ApplicationSet for user services
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
│       ├── sealed-secrets/
│       └── nfs-provisioner/
│
├── services/               # User-facing applications
│   ├── media/              # Prowlarr, qBittorrent, etc.
│   └── operations/         # ntfy, monitoring, etc.
│
├── templates/
│   └── common.yaml         # Shared Helm values for app-template
│
└── scripts/                # Utility scripts
    ├── seal.sh             # Seal secrets with kubeseal
    └── dyff-wrapper.sh     # YAML diff for CI
```

## 🚀 Bootstrap Order

The deployment follows a strict ordering via ArgoCD sync-waves:

| Wave | Component | Description |
|------|-----------|-------------|
| -10 | `foundation` | Namespaces and basic RBAC |
| 0 | `infra` ApplicationSet | Infrastructure controllers (Traefik, DBs, Auth) |
| 1 | `infra-configs` | Ingress routes, certificates, middlewares |
| 2 | `services` ApplicationSet | User applications |

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
   ```
3. Add `values.yaml` (extends `templates/common.yaml`)
4. Add `manifests/` folder (can contain `.gitkeep` if empty, or extra manifests)

## 🧩 Presets

### IngressRoute Preset (Services only)

Services using `app-template` can generate Traefik IngressRoutes via the `ingressPreset` in `values.yaml`:

```yaml
ingressPreset:
  enabled: true
  type: internal      # internal = websec-int, public = websecure
  host: myapp.internal.starktastic.net
  service:
    name: myapp       # defaults to release name
    port: 8080
  auth: true          # add authentik-middleware
  tls:
    secretName: ""    # leave empty for cluster default, or specify cert secret
```

**Preset types:**
| Type | Entrypoint | Domain Pattern |
|------|------------|----------------|
| `internal` | `websec-int` | `*.internal.starktastic.net` |
| `public` | `websecure` | `*.starktastic.net` or `*.benplus.vip` |

**Options:**
- `auth: true` - Adds `authentik-middleware` for SSO authentication
- `tls.secretName` - Specify a TLS secret (e.g., `benplus-vip-tls` for Jellyfin)

All IngressRoutes include `rate-limit-strong` middleware from `traefik-system`.

### Persistence Presets

Common values from `apps/templates/common.yaml` provide default persistence:

```yaml
# Default NFS config volume (1Gi, /config)
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

| Domain | Purpose |
|--------|----------|
| `starktastic.net` | Primary external domain |
| `*.internal.starktastic.net` | Internal services (behind Authentik) |
| `benplus.vip` | Email/alternate domain |

### Other Configuration

| Setting | Value | Location |
|---------|-------|----------|
| Timezone | `Asia/Jerusalem` | `apps/templates/common.yaml` |
| PUID/PGID | `1000/1000` | `apps/templates/common.yaml` |
| Admin Email | `benfaingold@gmail.com` | ClusterIssuer, pgadmin |
