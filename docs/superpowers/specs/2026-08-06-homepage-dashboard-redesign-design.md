# Homepage dashboard redesign

Date: 2026-08-06
Status: Approved, not yet implemented

## Problem

Both Homepage instances group services the way the repository groups directories:
tabs named `Home` / `Media` / `Operations` / `Infrastructure` mirror
`services/media`, `services/operations` and `infrastructure/`. That taxonomy
serves the person maintaining the repo, not the person using the dashboard. A
household member looking for the recipe app has to know it lives under
"operations".

Two further gaps follow from the same drift:

- **Services are missing.** Falco has an ingress at
  `falco.internal.starktastic.net` and appears on neither dashboard. Every
  service without a web UI (Recyclarr, Unpackerr, Subgen, Cross-seed,
  qbit-manage, Loki, Tempo, Alloy, MetalLB, cert-manager) is invisible by
  construction, because a dashboard entry is only ever written for something
  with a URL.
- **Two icons are broken.** `argocd.png` and `changedetection-io.png` do not
  exist in the dashboard-icons set; the correct names are `argo-cd` and
  `changedetection`.
- **Widgets are under-used.** Homepage v1.13.2 ships widget types for CrowdSec,
  ntfy, Dispatcharr and Filebrowser, all of which are link-only today. The
  `prometheusmetric` widget — arbitrary PromQL against the in-cluster
  Prometheus — is unused entirely.

## Goals

1. Replace both `services.yaml` / `settings.yaml` / `widgets.yaml` /
   `bookmarks.yaml` payloads with a taxonomy derived from user intent, not
   repository structure.
2. Place every service that has an ingress endpoint, plus every headless
   workload, on the admin dashboard.
3. Use every applicable widget the Homepage catalogue offers for the deployed
   stack.
4. Add information widgets covering homelab health, household context and
   outside-world data.
5. Make the "new service added but not put on the dashboard" failure loud
   instead of silent.
6. Fix the two broken icon references encountered in the rewritten config.

## Non-goals

- No changes to any chart, `values.yaml`, ingress definition or `app.yaml`.
- No new services deployed to satisfy a widget (no Glances, no Uptime Kuma).
- No theme or CSS overhaul beyond what the layout requires.

## Organising scheme: intent verbs

Sections are named for what the user is trying to do. A household member does
not need to know what Bazarr is to find the thing that plays films.

### Admin — `admin.starktastic.net` — five tabs

| Tab | Sections |
| --- | --- |
| **Pulse** | At a Glance · In Flight · Coming Up · Out There |
| **Play** | Watch · Listen · Read · Look Back · Ask For It |
| **Make** | Create · Convert · Find · Organise · Send |
| **Run** | Acquire · Refine · Home · Observe · Guard · Ship |
| **Iron** | Compute · Network · Storage · Data |

`Pulse` is the landing tab and answers "is everything OK?" before it offers
anything to click.

### User — `starktastic.net` — three tabs

| Tab | Sections |
| --- | --- |
| **Pulse** | At Home · Now Playing · Coming Up · Out There |
| **Play** | Watch · Listen · Read · Look Back · Ask For It |
| **Make** | Create · Convert · Find · Organise · Send |

The user page is a filtered projection of the admin scheme: identical section
names, with every `*.internal.starktastic.net` service removed. Adding a
service to the admin page and then deciding whether it is public is the only
judgement call needed to keep the two in sync.

## Service placement

### Admin — Pulse

- **At a Glance** — three `prometheusmetric` cards against
  `http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090`:
  - *Cluster Health*: nodes ready, unhealthy pods, firing alerts, fullest PVC
  - *Edge & Certs*: failing blackbox probes, nearest certificate expiry,
    Traefik request rate, p95 latency
  - *Security*: CrowdSec active decisions, Falco events over 24h, Traefik
    4xx/5xx rate
- **In Flight** — Jellyfin (now playing), qBittorrent, qBittorrent RU, ArgoCD,
  ntfy (latest message on the `alerts` topic)
- **Coming Up** — Calendar (Sonarr / Sonarr RU / Radarr / Radarr RU / Lidarr
  iCal), Vikunja task list, Mealie meal plan
- **Out There** — News via `customapi` against the keyless Hacker News Algolia
  endpoint. Stocks live in the header rather than this section, so *Out There*
  holds the news card alone.

### Admin — Play

- **Watch** — Jellyfin, Dispatcharr, Cineplete, Samsung TV+ (pod status)
- **Listen** — Navidrome, Audiobookshelf
- **Read** — Calibre-Web
- **Look Back** — Immich
- **Ask For It** — Seerr, Seerr RU, Shelfmark

### Admin — Make

- **Create** — Excalidash, ByteStash, MicroBin
- **Convert** — ConvertX, Stirling PDF, CyberChef, MeTube, LibreTranslate
  (pod status)
- **Find** — SearXNG, Karakeep, Changedetection
- **Organise** — Vikunja, Paperless-ngx, Filebrowser, Mealie
- **Send** — PairDrop, ntfy, Listmonk

### Admin — Run

- **Acquire** — Radarr, Radarr RU, Sonarr, Sonarr RU, Lidarr, Prowlarr,
  Autobrr, qBittorrent, qBittorrent RU
- **Refine** — Bazarr, Lingarr, Subgen, Recyclarr, Unpackerr, Cross-seed,
  qbit-manage, qbit-manage RU, FlareSolverr
- **Home** — Home Assistant, Zigbee2MQTT, Mosquitto
- **Observe** — Grafana, Prometheus, Loki, Tempo, Alloy, Blackbox Exporter,
  alertmanager-ntfy
- **Guard** — Authentik, Vaultwarden, CrowdSec, Falco, cert-manager,
  Sealed Secrets
- **Ship** — ArgoCD, plus the four existing GitHub PR `customapi` widgets
  (apps, ansible, packer, terraform)

### Admin — Iron

- **Compute** — Proxmox VE, kube-master-01, kube-worker-01, kube-worker-02,
  Intel Device Operator
- **Network** — OPNsense, AdGuard Home, Traefik, MetalLB
- **Storage** — TrueNAS, NFS provisioner
- **Data** — PostgreSQL, Redis, pgAdmin

### User page

- **Pulse** — *At Home* (Home Assistant sensors, no link since the host is
  internal) · *Now Playing* (Jellyfin, Navidrome) · *Coming Up* (Calendar,
  Vikunja, Mealie) · *Out There* (news)
- **Play** — *Watch*: Jellyfin · *Listen*: Navidrome, Audiobookshelf ·
  *Read*: Calibre-Web · *Look Back*: Immich · *Ask For It*: Seerr, Seerr RU,
  Shelfmark
- **Make** — *Create*: Excalidash, MicroBin · *Convert*: ConvertX, Stirling
  PDF, CyberChef, MeTube · *Find*: SearXNG, Karakeep · *Organise*: Vikunja,
  Mealie · *Send*: PairDrop, ntfy, Listmonk
- **Bookmarks** — "My Account" pointing at `auth.starktastic.net`

The ntfy *widget* is deliberately admin-only. The `alerts` topic carries
infrastructure alerts; the user page links to ntfy without surfacing message
content.

## Headless services

Services with no web UI are represented through the Kubernetes integration
rather than omitted. Homepage renders pod status plus CPU and memory for any
entry carrying `namespace` and `app` (or `podSelector`) fields, with no `href`.
`kubernetes.yaml` is already `mode: cluster` on the admin instance and the
ServiceAccount and RBAC already exist.

This covers Recyclarr, Unpackerr, Subgen, Cross-seed, qbit-manage,
qbit-manage-ru, FlareSolverr, LibreTranslate, Samsung TV+, Mosquitto, Loki,
Tempo, Alloy, alertmanager-ntfy, Blackbox Exporter, MetalLB, cert-manager,
Sealed Secrets, NFS provisioner, Intel Device Operator, PostgreSQL and Redis.
Prometheus keeps its `prometheus` widget and an `href` pointing at Grafana
Explore, since it has no ingress of its own.

## Status indicators

Every user-page service gains a `siteMonitor` pointing at its in-cluster
service URL. `statusStyle: dot` is already set on that instance but has never
rendered anything, because no service defines a monitor. Household members can
then distinguish "Jellyfin is down" from "my wifi is bad" without asking.

## New sealed secrets

All six are approved. Seal with `scripts/seal.sh` and add to the relevant
`secrets.yaml`.

| Key | Instance | Unlocks |
| --- | --- | --- |
| `HOMEPAGE_VAR_NTFY_TOKEN` | admin | `ntfy` widget — instance is `deny-all`, needs a `tk_` token |
| `HOMEPAGE_VAR_FINNHUB_KEY` | admin | `stocks` header widget, set as `providers.finnhub` in `settings.yaml` |
| `HOMEPAGE_VAR_DISPATCHARR_USER` / `_PASS` | admin | `dispatcharr` widget — channels and active streams |
| `HOMEPAGE_VAR_FILEBROWSER_USER` / `_PASS` | admin | `filebrowser` widget — disk used / available / total |
| `HOMEPAGE_VAR_CROWDSEC_USER` / `_PASS` | admin | `crowdsec` widget — alerts and bans |
| `HOMEPAGE_VAR_HASS_KEY` | user | `homeassistant` widget for the *At Home* section |

The CrowdSec LAPI runs in mutual-TLS mode. A comment in
`infrastructure/system/crowdsec/values.yaml` records that the chart's own
startup fails with "user/password and TLS are mutually exclusive" when both are
configured, which strongly suggests the password auth the `crowdsec` widget
requires is unavailable on this deployment. The widget is therefore attempted
but not assumed: if machine credentials cannot be issued, it is dropped and the
*Security* PromQL card covers ban counts via the metrics CrowdSec already
exports to Prometheus. `HOMEPAGE_VAR_CROWDSEC_USER` / `_PASS` are only sealed
if the widget proves viable.

## Settings changes

**Admin `settings.yaml`**

- Tabs assigned via `tab:` keys in `layout`
- `hideErrors: false` — a broken PromQL query must be visible during rollout
- `providers.finnhub` added
- `pwa.shortcuts` updated to the five new tabs
- `headerStyle: boxedWidgets`, `statusStyle: dot`, `iconStyle: theme` and
  `useEqualHeights: true` all retained

**User `settings.yaml`**

- Tabs introduced (the instance has none today)
- `hideErrors: true` retained — household members should never see a stack trace
- `pwa.shortcuts` updated to the three new tabs

**Header widgets**

- Admin: `logo`, `kubernetes` (cluster and nodes), `search`, `openmeteo`,
  `stocks`, `datetime`
- User: `logo`, `greeting`, `search`, `openmeteo`, `datetime` — no cluster
  statistics

## Risks

**PromQL cannot be verified from the development machine.** `kubectl` is
configured but the cluster rejects the local credentials, so no query in the
*At a Glance* row can be tested before deployment. Metrics from
kube-state-metrics, node-exporter, blackbox-exporter and Traefik are safe to
assume; the CrowdSec and Falco metric names are not. Every query must be run in
Grafana Explore and confirmed to return a value before it is pinned in the
ConfigMap. `hideErrors: false` on the admin instance exists to catch whatever
slips through.

**`settings.yaml` does not hot-reload.** Homepage picks up `services.yaml` and
`bookmarks.yaml` changes on a page refresh, but `settings.yaml` — which carries
the entire tab layout — does not reliably apply without a container restart.
Stakater Reloader is not deployed; the `reloader.stakater.com/auto` annotation
on ntfy is a no-op. After the pull request merges and ArgoCD syncs, both
Deployments need `kubectl rollout restart`. Deploying Reloader would remove the
manual step and is worth considering separately.

## Coverage check

`scripts/check-homepage-coverage.py`, following the conventions of the existing
`scripts/check-readme-images.py`:

- Read every `services/*/*/app.yaml` and `infrastructure/*/*/app.yaml`, plus
  standalone IngressRoute manifests, and resolve each hostname through
  `templates/globals.yaml`.
- Fail if any resolved host is absent from the admin ConfigMap.
- Fail if any non-internal host is absent from the user ConfigMap.
- Fail if any internal host appears in the user ConfigMap.

Two hosts are excluded by an explicit allowlist in the script: `starktastic.net`
(the user dashboard) and `admin.starktastic.net` (the admin dashboard). Neither
dashboard lists itself as a service. The admin instance instead carries a
bookmark to the user dashboard.

Wired into `.github/workflows/validate-and-diff.yml` as a step in the existing
`validate` job, alongside yamllint and kubeconform.

## Rejected alternatives

**Ingress annotation discovery.** Homepage can build both dashboards from
`gethomepage.dev/*` annotations on each IngressRoute, with a
`gethomepage.dev/instance` annotation choosing which dashboard a service lands
on. This removes the ConfigMaps and the coverage check entirely — a service
cannot be forgotten if its own ingress declares its dashboard entry. Rejected
because it scatters dashboard configuration across more than forty files,
gives up explicit control of section ordering, and the widget secrets would
have to be templated into annotations. Worth revisiting if the ConfigMaps
become painful to maintain.

**Content pipeline taxonomy** (`Ask → Fetch → Refine → Serve → Enjoy`).
Excellent for debugging the media stack, meaningless to household members, and
incompatible with the decision to make the user page a filtered subset of one
shared scheme.

**House-room metaphor** (`Living Room`, `Library`, `Basement`). Memorable and
genuinely intuitive, but several services have no obvious room and the
whimsy has no upgrade path when the stack grows.

## Rollout

One pull request containing both ConfigMaps, both `secrets.yaml` updates, the
coverage script and its CI step. After merge and ArgoCD sync, restart both
Deployments, then load each dashboard and confirm no widget renders an error.
Rollback is a single revert; ArgoCD restores the previous ConfigMaps and the
same restart applies.
