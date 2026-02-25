# Homelab Apps

![ArgoCD](https://img.shields.io/badge/ArgoCD-Synced-48bb78?logo=argo)
[![Kubernetes](https://img.shields.io/badge/K3s-v1.35-326CE5?logo=kubernetes)](https://k3s.io)
![Traefik](https://img.shields.io/badge/Traefik-v3-24A1C1?logo=traefikproxy)
![Authentik](https://img.shields.io/badge/Authentik-SSO-FD4B2D?logo=authentik)

GitOps repository for managing a Kubernetes homelab using ArgoCD with an App-of-Apps pattern. All cluster applications are defined declaratively and automatically synced from this repository.

## Overview

This repository contains the complete application layer for the homelab Kubernetes cluster. It is bootstrapped by [ansible](https://github.com/Starktastic-Homelab/ansible) and uses ArgoCD for continuous deployment.

**37 apps** across 3 categories: 11 infrastructure, 6 operations, 20 media services.

## Repository Structure

```
bootstrap/                          # Entry point — deploy these first
└── appsets/
    ├── cluster-apps.yaml           # Main ApplicationSet (matrix generator)
    └── config-apps.yaml            # Config ApplicationSet (base-configs + ingresses)

infrastructure/
├── base-configs/                   # Non-Helm cluster configs
│   └── templates/                  # Cert-backup, ingresses, certs, middlewares
├── configs/                        # IngressRoutes, certificates, middlewares
├── controllers/                    # Helm-based infrastructure
│   ├── authentik/                  # Identity provider & SSO
│   ├── traefik/                    # Ingress controller
│   └── databases/
│       ├── pgadmin/                # Database admin UI
│       ├── postgres/               # PostgreSQL
│       └── redis/                  # Redis cache
└── system/                         # Cluster-level components
    ├── cert-manager/               # TLS certificate automation
    ├── crowdsec/                   # Intrusion detection & bouncer
    ├── intel-device-operator/      # Intel GPU SR-IOV operator
    ├── nfs-provisioner/            # Dynamic NFS volume provisioning
    ├── prometheus-operator-crds/   # Monitoring CRDs (deploy phase: crds)
    └── sealed-secrets/             # Encrypted secrets in Git

services/
├── media/                          # 20 media apps (namespace: media)
│   ├── autobrr/                    # Torrent automation
│   ├── bazarr/                     # Subtitle management
│   ├── cross-seed/                 # Cross-seeding
│   ├── flaresolverr/               # Cloudflare bypass proxy
│   ├── jellyfin/                   # Media server (+ LDAP sync CronJob)
│   ├── lingarr/                    # Subtitle translation
│   ├── prowlarr/                   # Indexer manager
│   ├── qbit-manage/                # qBittorrent tag manager
│   ├── qbit-manage-ru/             # ↳ Russian variant (baseApp)
│   ├── qbittorrent/                # BitTorrent client
│   ├── qbittorrent-ru/             # ↳ Russian variant (baseApp)
│   ├── radarr/                     # Movie management
│   ├── radarr-ru/                  # ↳ Russian variant (baseApp)
│   ├── recyclarr/                  # TRaSH guide sync
│   ├── seerr/                      # Request management
│   ├── seerr-ru/                   # ↳ Russian variant (baseApp)
│   ├── sonarr/                     # TV management
│   ├── sonarr-ru/                  # ↳ Russian variant (baseApp)
│   ├── subgen/                     # AI subtitle generation
│   └── unpackerr/                  # Archive extraction
└── operations/                     # 6 ops apps (namespace: monitoring/operations)
    ├── alertmanager-ntfy/          # Alert → ntfy adapter
    ├── alloy/                      # Grafana Alloy (log/metric collector)
    ├── kube-prometheus-stack/       # Prometheus + Grafana + AlertManager
    ├── loki/                       # Log aggregation
    ├── ntfy/                       # Push notifications
    └── tempo/                      # Distributed tracing

templates/
├── globals.yaml                    # Cluster-wide values (domains, IPs, storage)
├── common.yaml                     # Shared defaults for all services
├── infra-common.yaml               # Shared defaults for infrastructure
└── ingress-chart/                  # Dynamic IngressRoute generator template

scripts/
├── get-kubeconfig.sh               # Fetch kubeconfig from cluster via SSH
├── new-service.sh                  # Scaffold a new service interactively
├── ntfy-manager.sh                 # Manage ntfy users/access in-cluster
└── seal.sh                         # Seal secrets with kubeseal
```

## Deployment Architecture

ArgoCD deploys all apps via two ApplicationSets with a **RollingSync** strategy:

```mermaid
flowchart LR
    subgraph RollingSync["Deploy Phases (cluster-apps)"]
        P1["1. crds\nprometheus-operator-crds"] --> P2["2. foundation\ncert-manager, base-configs"]
        P2 --> P3["3. controllers\ntraefik, authentik, databases,\ncrowdsec, sealed-secrets, ..."]
        P3 --> P4["4. services\nall media & operations apps"]
    end

    style P1 fill:#805ad5
    style P2 fill:#4299e1
    style P3 fill:#48bb78
    style P4 fill:#ed8936
```

| Phase | Label | Components |
|-------|-------|------------|
| 1 | `crds` | prometheus-operator-crds |
| 2 | `foundation` | cert-manager, base-configs |
| 3 | `controllers` | traefik, authentik, databases, crowdsec, sealed-secrets, intel-device-operator, nfs-provisioner, infra-configs |
| 4 | `services` | All 20 media apps + 6 operations apps |

## Infrastructure Components

### Controllers

| Component | Chart | Version | Description |
|-----------|-------|---------|-------------|
| Traefik | traefik | 39.0.2 | Ingress controller with dual entrypoints |
| Authentik | authentik | 2025.12.4 | Identity provider with OIDC SSO |
| PostgreSQL | postgresql | 18.4.1 | Database for Authentik and apps |
| Redis | redis | 25.3.2 | Cache for Authentik |
| pgAdmin | pgadmin4 | 1.59.0 | Database administration UI |

### System

| Component | Chart | Version | Description |
|-----------|-------|---------|-------------|
| cert-manager | cert-manager | v1.19.4 | TLS certificate automation (Let's Encrypt) |
| CrowdSec | crowdsec | 0.22.0 | Intrusion detection + Traefik bouncer |
| Intel GPU Operator | intel-device-plugins-operator | 0.35.0 | SR-IOV GPU sharing (20 pods/VF) |
| NFS Provisioner | nfs-subdir-external-provisioner | 4.0.18 | Dynamic NFS PV provisioning |
| Prometheus CRDs | prometheus-operator-crds | 27.0.0 | ServiceMonitor/PodMonitor CRDs |
| Sealed Secrets | sealed-secrets | 2.18.1 | Encrypt secrets for Git storage |

### Operations / Monitoring

| Component | Chart | Version | Description |
|-----------|-------|---------|-------------|
| kube-prometheus-stack | kube-prometheus-stack | 82.3.0 | Prometheus + Grafana + AlertManager |
| Loki | loki | 6.53.0 | Log aggregation |
| Alloy | alloy | 1.6.0 | Grafana Alloy (log/trace/metric collector) |
| Tempo | tempo | 1.24.4 | Distributed tracing |
| alertmanager-ntfy | app-template | 4.6.2 | AlertManager → ntfy webhook adapter |
| ntfy | app-template | 4.6.2 | Self-hosted push notifications |

## Domain & Network Configuration

| Domain | Purpose | LoadBalancer IP | Entrypoint |
|--------|---------|-----------------|------------|
| `*.starktastic.net` | Public services | `10.9.8.90` | `websecure` |
| `*.internal.starktastic.net` | Internal services | `10.9.9.90` | `websec-int` |
| `*.benplus.app` | Media services | `10.9.8.90` | `websecure` |

| Resource | IP / CIDR | Purpose |
|----------|-----------|---------|
| NFS Server | `10.9.8.30` | Persistent storage |
| qBittorrent | `10.9.8.91` | BitTorrent LB |
| qBittorrent-RU | `10.9.8.92` | BitTorrent LB (RU) |
| Management VLAN | `10.9.9.0/24` | Cluster management |
| Services VLAN | `10.9.8.0/24` | Service network |
| WireGuard VLAN | `10.9.10.0/24` | VPN network |

## Usage

### Adding a New Service

Use the interactive scaffolding script:

```bash
./scripts/new-service.sh
```

Or manually create `services/<category>/<name>/` with:

**app.yaml**:
```yaml
name: my-service
namespace: my-namespace

ingress:
  enabled: true
  host: my-service
  domainType: "internal"    # public | internal | media
  port: 8080
  auth: true                # Authentik ForwardAuth
  rateLimit: true           # CrowdSec rate limiting
```

**values.yaml** — extends `templates/common.yaml` (inherits TZ, PUID/PGID, probes, NFS config).

**manifests/** — plain Kubernetes manifests (PVCs, Secrets, ConfigMaps).

### Sealing Secrets

```bash
# Namespace-scoped (default)
./scripts/seal.sh <secret-name> <namespace>

# Cluster-wide scope
./scripts/seal.sh <secret-name> <namespace> --cluster-wide
```

### GPU Support

Intel GPU SR-IOV passthrough for hardware transcoding (20 pods share each VF):

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

## Pipeline Integration

```mermaid
flowchart TD
    Packer["📦 Packer\nVM Template"] -->|manifest.json| Terraform
    Terraform["🏗️ Terraform\nVM Provisioning"] -->|dispatch| Ansible
    Ansible["⚙️ Ansible\nK3s Cluster"] -->|bootstrap| Apps
    Apps["🚀 Apps\nGitOps Deployment"]

    style Packer fill:#4299e1,stroke:#2b6cb0
    style Terraform fill:#805ad5,stroke:#553c9a
    style Ansible fill:#48bb78,stroke:#276749
    style Apps fill:#ed8936,stroke:#c05621
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| PostgreSQL postmaster.pid lock | Init container auto-removes stale locks |
| Sealed secrets decryption error | Verify secret was sealed for correct namespace |
| PVC stuck in Pending | Verify NFS server `10.9.8.30` is accessible |
| GPU not available | Check intel-gpu-plugin pods are running |
| CrowdSec bouncer blocking | Check `cscli decisions list` in LAPI pod |

## Related Repositories

| Repository | Description |
|------------|-------------|
| [packer](https://github.com/Starktastic-Homelab/packer) | Builds Debian VM templates for Proxmox |
| [terraform](https://github.com/Starktastic-Homelab/terraform) | Provisions VMs on Proxmox |
| [ansible](https://github.com/Starktastic-Homelab/ansible) | K3s cluster bootstrap & configuration |

## License

MIT
