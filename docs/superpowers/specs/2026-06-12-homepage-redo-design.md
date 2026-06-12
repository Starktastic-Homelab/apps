# Homepage Configmaps Redo — Design

**Date:** 2026-06-12
**Status:** Approved (pending spec review)

## Problem

The cluster runs two Homepage instances:

- **Regular** (`starktastic.net`, chart `services/operations/homepage`) — served to all users.
- **Admin** (`admin.starktastic.net`, chart `services/operations/homepage-admin`) — admin-only.

Their `services.yaml` configmaps have drifted and grown ad-hoc. We want to rebuild both
`configmap.yaml` files from scratch: capture every service in the repo that has a WebUI,
organize them under one consistent taxonomy, and use Homepage widgets wherever the app
supports one.

### Membership rule (drives which services land where)

- **Regular** includes services whose ingress host is `*.starktastic.net` or `(*.)?benplus.app`.
- **Admin** includes everything the regular instance has **plus** services on
  `*.internal.starktastic.net`.

## Architecture (Approach A — two independent configmaps)

The ApplicationSet renders each app's **own** `manifests/` directory
(`bootstrap/appsets/cluster-apps.yaml:168` → `{{.path.path}}/manifests`). `baseApp`
(set on `homepage`, pointing at `homepage-admin`) redirects only **Helm values**, not
manifests, and the manifests chart receives only `globals.yaml`. Therefore the two
`configmap.yaml` files are fully independent static templates with no shared-block
mechanism. We rewrite both by hand.

- **Admin is tabbed**, **regular is flat**:
  - *Admin* groups sections into four tabs (`tab:` key) with PWA shortcuts:
    **Home** (Streaming, Requests, Home & Life, Calendar) ·
    **Media** (Movies & TV, Music & Books, Downloads) ·
    **Operations** (Productivity, Monitoring, Security, Documents & Files, Utilities) ·
    **Infrastructure** (Proxmox, Cluster VMs, Networking, Databases).
  - *Regular* is a single scrolling page (no `tab:` keys, no PWA shortcuts).
- **One canonical taxonomy** is shared across both; the regular instance simply omits
  sections/items that don't qualify by domain.
- Single-item sections on the regular instance are **kept** (strict canonical taxonomy).
- Helm/templating untouched: only `manifests/templates/configmap.yaml` per chart is
  rewritten (plus a secret addition, below). `rbac.yaml`, `proxmox.yaml`, info widgets,
  `bookmarks.yaml`, and `kubernetes.yaml` mode are preserved.

## Canonical taxonomy

| Section | Admin members | Regular members |
| --- | --- | --- |
| Streaming | Jellyfin, Immich, Navidrome, Audiobookshelf, Calibre-Web | same |
| Requests | Seerr, Seerr RU, Shelfmark | same |
| Home & Life | Home Assistant, Zigbee2MQTT, Mealie, Cineplete | Mealie |
| Movies & TV | Radarr, Radarr RU, Sonarr, Sonarr RU | — |
| Music & Books | Lidarr, Bazarr, Lingarr, Prowlarr, Autobrr | — |
| Downloads | qBittorrent, qBittorrent RU | — |
| Calendar | calendar widget (sonarr/radarr/lidarr) | — |
| Productivity | Vikunja, Karakeep, Listmonk, ByteStash | Vikunja, Karakeep, Listmonk |
| Monitoring | Grafana, Prometheus, Traefik, CrowdSec | — |
| Security | Authentik, Vaultwarden, ArgoCD | Authentik |
| Documents & Files | Paperless-ngx, Filebrowser, Changedetection | — |
| Utilities | SearXNG, CyberChef, Stirling PDF, MeTube, MicroBin, PairDrop, Excalidash, ConvertX | + ntfy |
| Infrastructure (Proxmox / Cluster VMs / Networking / Databases) | Proxmox, kube VMs, Traefik/MetalLB/CrowdSec, PostgreSQL/pgAdmin | — |

Notes:
- **ntfy** (`ntfy.starktastic.net`) lives in **Utilities** on both instances.
- **Paperless-ngx** lives in **Documents & Files** only (not duplicated in Productivity).
- **Authentik** becomes a **Security** service tile (with widget) on both instances; its
  former bookmark entry on the regular instance is removed.

## Service inventory (host → cluster URL → widget)

### Streaming (both)
- Jellyfin — `https://benplus.app` — `http://jellyfin-main.media.svc.cluster.local:8096` — widget: jellyfin (blocks/nowPlaying/user/episodeNumber)
- Immich — `https://photos.benplus.app` — `http://immich-main.media.svc.cluster.local:2283` — widget: immich v2
- Navidrome — `https://music.benplus.app` — `http://navidrome.media.svc.cluster.local:4533` — widget: navidrome (user/token/salt)
- Audiobookshelf — `https://audiobooks.benplus.app` — `http://audiobookshelf.media.svc.cluster.local:80` — widget: audiobookshelf
- Calibre-Web — `https://books.benplus.app` — `http://calibre-web.media.svc.cluster.local:8083` — widget: calibreweb (user/pass)

### Requests (both)
- Seerr — `https://request.benplus.app` — `http://seerr.media.svc.cluster.local:5055` — widget: seerr
- Seerr RU — `https://request-ru.benplus.app` — `http://seerr-ru.media.svc.cluster.local:5055` — widget: seerr
- Shelfmark — `https://request-books.benplus.app` — link only

### Home & Life
- Home Assistant *(admin)* — `https://ha.internal.starktastic.net` — `http://home-assistant-main.home-automation.svc.cluster.local:8123` — widget: homeassistant
- Zigbee2MQTT *(admin)* — `https://zigbee2mqtt.internal.starktastic.net` — link only
- Mealie *(both)* — `https://mealie.starktastic.net` — `http://mealie.operations.svc.cluster.local:9000` — widget: mealie v2
- Cineplete *(admin)* — `https://cineplete.internal.starktastic.net` — link only

### Movies & TV (admin)
- Radarr — `https://radarr.internal.starktastic.net` — `http://radarr.media.svc.cluster.local:7878` — widget: radarr (enableQueue)
- Radarr RU — `https://radarr-ru.internal.starktastic.net` — `http://radarr-ru.media.svc.cluster.local:7878` — widget: radarr (enableQueue)
- Sonarr — `https://sonarr.internal.starktastic.net` — `http://sonarr.media.svc.cluster.local:8989` — widget: sonarr (enableQueue)
- Sonarr RU — `https://sonarr-ru.internal.starktastic.net` — `http://sonarr-ru.media.svc.cluster.local:8989` — widget: sonarr (enableQueue)

### Music & Books (admin)
- Lidarr — `https://lidarr.internal.starktastic.net` — `http://lidarr.media.svc.cluster.local:8686` — widget: lidarr
- Bazarr — `https://bazarr.internal.starktastic.net` — `http://bazarr.media.svc.cluster.local:6767` — widget: bazarr
- Lingarr — `https://lingarr.internal.starktastic.net` — link only
- Prowlarr — `https://prowlarr.internal.starktastic.net` — `http://prowlarr.media.svc.cluster.local:9696` — widget: prowlarr
- Autobrr — `https://autobrr.internal.starktastic.net` — `http://autobrr.media.svc.cluster.local:7474` — widget: autobrr

### Downloads (admin)
- qBittorrent — `https://qbittorrent.internal.starktastic.net` — `http://qbittorrent-main.media.svc.cluster.local:8080` — widget: qbittorrent
- qBittorrent RU — `https://qbittorrent-ru.internal.starktastic.net` — `http://qbittorrent-ru-main.media.svc.cluster.local:8080` — widget: qbittorrent

### Calendar (admin)
- Calendar widget (monthly, 15 events) integrating Sonarr, Sonarr RU, Radarr, Radarr RU, Lidarr.

### Productivity
- Vikunja *(both)* — `https://vikunja.starktastic.net` — `http://vikunja.operations.svc.cluster.local:3456` — widget: vikunja v2 (`enableTaskList: true`), key `HOMEPAGE_VAR_VIKUNJA_KEY` **[new secret]**. Vikunja is OIDC-only, but a personal API token (created in its UI) works for the widget key.
- Karakeep *(both)* — `https://karakeep.starktastic.net` — `http://karakeep.operations.svc.cluster.local:3000` — widget: karakeep
- Listmonk *(both)* — `https://listmonk.starktastic.net` — link only (no Homepage widget exists)
- ByteStash *(admin)* — `https://bytestash.internal.starktastic.net` — link only

### Monitoring (admin)
- Grafana — `https://grafana.internal.starktastic.net` — `http://kube-prometheus-stack-grafana.monitoring.svc.cluster.local:80` — widget: grafana (alertmanager, user/pass, v2)
- Prometheus — `https://grafana.internal.starktastic.net/explore` — `http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090` — widget: prometheus
- Traefik — `https://traefik.internal.starktastic.net` — `http://traefik.traefik-system.svc.cluster.local:9000` — widget: traefik
- CrowdSec — `https://app.crowdsec.net` — link only

### Security
- Authentik *(both)* — `https://auth.starktastic.net` — `http://authentik-server.authentik.svc.cluster.local:80` — widget: authentik v2
- Vaultwarden *(admin)* — `https://vaultwarden.internal.starktastic.net` — link only
- ArgoCD *(admin)* — `https://argocd.internal.starktastic.net` — `http://argocd-server.argocd.svc.cluster.local:80` — widget: argocd

### Documents & Files (admin)
- Paperless-ngx — `https://paperless.internal.starktastic.net` — `http://paperless-ngx.operations.svc.cluster.local:8000` — widget: paperlessngx
- Filebrowser — `https://files.internal.starktastic.net` — link only
- Changedetection — `https://changedetection.internal.starktastic.net` — `http://changedetection.operations.svc.cluster.local:5000` — widget: changedetectionio

### Utilities
- SearXNG *(both)* — `https://search.starktastic.net` — `http://searxng.operations.svc.cluster.local:8080` — widget: searxng
- CyberChef *(both)* — `https://cyberchef.starktastic.net` — link only
- Stirling PDF *(both)* — `https://pdf.starktastic.net` — link only
- MeTube *(both)* — `https://metube.benplus.app` — link only
- MicroBin *(both)* — `https://microbin.starktastic.net` — link only
- PairDrop *(both)* — `https://pairdrop.starktastic.net` — link only
- Excalidash *(both)* — `https://excalidash.starktastic.net` — link only
- ConvertX *(both)* — `https://convertx.starktastic.net` — link only
- ntfy *(both)* — `https://ntfy.starktastic.net` — link only

### Infrastructure (admin)
- Proxmox VE — `https://10.9.9.20:8006` — widget: proxmox (node pve)
- Cluster VMs — kube-master-01 (200), kube-worker-01 (201), kube-worker-02 (202) via proxmox node/VMID
- Networking — Traefik Dashboard, MetalLB (info), CrowdSec LAPI
- Databases — PostgreSQL (info), pgAdmin (`https://pgadmin.internal.starktastic.net`)

## Layout (column counts, all `style: row`)

- **Admin** (each section carries a `tab:` per the four tabs above):
  - *Home tab:* Streaming 5 · Requests 3 · Home&Life 4 · Calendar 1
  - *Media tab:* Movies&TV 4 · Music&Books 5 · Downloads 2
  - *Operations tab:* Productivity 4 · Monitoring 4 · Security 3 · Documents&Files 3 · Utilities 4
  - *Infrastructure tab:* Proxmox 1 · Cluster VMs 3 · Networking 3 · Databases 2
  - PWA shortcuts: Home `/#home`, Media `/#media`, Operations `/#operations`, Infrastructure `/#infrastructure`.
- **Regular** (flat, no tabs): Streaming 5 · Requests 3 · Home&Life 1 · Productivity 3 · Security 1 · Utilities 4

## Info widgets (`widgets.yaml`)

- Both: `search` (duckduckgo) · `openmeteo` (Tel Aviv, metric) · `datetime` (xl, h23).
- Admin only, placed first: `kubernetes` cluster widget (cluster + nodes, cpu/mem).

## Other config

- `kubernetes.yaml`: admin `mode: cluster`, regular `mode: disabled`.
- `proxmox.yaml`: admin only, unchanged.
- Bookmarks:
  - Admin: Developer (GitHub, ArgoCD), Documentation (Homepage, Kubernetes), External (Cloudflare, Mailgun) — unchanged.
  - Regular: `Links` group with GitHub only (Authentik moved to Security tile).

## Secrets (out-of-band, by user)

Add a sealed `HOMEPAGE_VAR_VIKUNJA_KEY` entry to **both** SealedSecrets:
- `services/operations/homepage/manifests/templates/secrets.yaml`
- `services/operations/homepage-admin/manifests/templates/secrets.yaml`

The configmaps reference `{{ HOMEPAGE_VAR_VIKUNJA_KEY }}`; the rewrite does not seal the
value (requires kubeseal cert + the real key). Until sealed, the Vikunja widget will fail
to populate but the tile/link still works.

## Out of scope

- Services without a WebUI (recyclarr, unpackerr, subgen, qbit-manage, cross-seed,
  flaresolverr, mosquitto, libretranslate-as-API, etc.).
- Changing which widgets are exposed on the public instance (user will prune later).
- Helm chart / values restructuring; sealing secret values.
