# Homepage Configmaps Redo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite both Homepage `configmap.yaml` files from scratch under one canonical taxonomy — admin tabbed (full service set), regular flat (non-internal subset) — maximizing Homepage widgets.

**Architecture:** Two independent static-YAML Helm-templated ConfigMaps (Approach A). The ApplicationSet renders each app's own `manifests/` dir, so there is no shared-block mechanism; each file is rewritten by hand. `{{ HOMEPAGE_VAR_* }}` secret refs are escaped for Helm as `{{ "{{" }}HOMEPAGE_VAR_X{{ "}}" }}`.

**Tech Stack:** Kubernetes ConfigMaps, Helm v3, gethomepage.dev (Homepage dashboard), Prettier (CI formatter), kubeseal (SealedSecrets).

**Spec:** `docs/superpowers/specs/2026-06-12-homepage-redo-design.md`

---

## File Structure

- `services/operations/homepage-admin/manifests/templates/configmap.yaml` — **rewrite** (admin, tabbed, full set).
- `services/operations/homepage/manifests/templates/configmap.yaml` — **rewrite** (regular, flat, non-internal subset).
- `services/operations/homepage-admin/manifests/templates/secrets.yaml` — **user-sealed addition** of `HOMEPAGE_VAR_VIKUNJA_KEY`.
- `services/operations/homepage/manifests/templates/secrets.yaml` — **user-sealed addition** of `HOMEPAGE_VAR_VIKUNJA_KEY`.

No other files change. `rbac.yaml`, `Chart.yaml`, `app.yaml`, `values.yaml` are untouched.

### Key conventions (verified)
- Helm escaping for Homepage's own `{{ }}` syntax: write `{{ "{{" }}HOMEPAGE_VAR_X{{ "}}" }}`. After `helm template`, this renders to the literal `{{HOMEPAGE_VAR_X}}` that Homepage substitutes at runtime.
- Render check: `helm template <name> <chart-dir> -f templates/globals.yaml` (the manifests chart only consumes `globals.yaml`).
- Format gate: Prettier (`.github/workflows/format.yaml`). `services/` is **not** in `.prettierignore`, so these files are auto-formatted. Run `npx --yes prettier --write <file>` before committing to match CI.
- yamllint is **not** a CI gate (no yamllint workflow) — do not chase yamllint warnings.

---

## Task 1: Rewrite the admin ConfigMap (tabbed, full set)

**Files:**
- Modify (replace entire contents): `services/operations/homepage-admin/manifests/templates/configmap.yaml`

- [ ] **Step 1: Replace the entire file with the content below**

````yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: homepage-admin-config
  namespace: operations
data:
  proxmox.yaml: |
    pve:
      url: https://10.9.9.20:8006
      token: {{ "{{" }}HOMEPAGE_VAR_PROXMOX_USER{{ "}}" }}
      secret: {{ "{{" }}HOMEPAGE_VAR_PROXMOX_PASS{{ "}}" }}
  docker.yaml: ""
  custom.js: ""
  custom.css: ""
  kubernetes.yaml: |
    mode: cluster
  settings.yaml: |
    title: Starktastic Services
    headerStyle: boxedWidgets
    statusStyle: dot
    useEqualHeights: true
    hideVersion: true
    disableCollapse: false
    disableIndexing: true
    iconStyle: theme
    quicklaunch:
      searchDescriptions: true
      hideInternetSearch: false
      showSearchSuggestions: true
      provider: duckduckgo
    pwa:
      shortcuts:
        - name: Home
          url: "/#home"
        - name: Media
          url: "/#media"
        - name: Operations
          url: "/#operations"
        - name: Infrastructure
          url: "/#infrastructure"
    layout:
      # -- Home tab --
      Streaming:
        tab: Home
        style: row
        columns: 5
        icon: jellyfin.png
      Requests:
        tab: Home
        style: row
        columns: 3
        icon: overseerr.png
      Home & Life:
        tab: Home
        style: row
        columns: 4
        icon: home-assistant.png
      Calendar:
        tab: Home
        style: row
        columns: 1
      # -- Media tab --
      Movies & TV:
        tab: Media
        style: row
        columns: 4
        icon: radarr.png
      Music & Books:
        tab: Media
        style: row
        columns: 5
        icon: navidrome.png
      Downloads:
        tab: Media
        style: row
        columns: 2
        icon: qbittorrent.png
      # -- Operations tab --
      Productivity:
        tab: Operations
        style: row
        columns: 4
        icon: vikunja.png
      Monitoring:
        tab: Operations
        style: row
        columns: 4
        icon: grafana.png
      Security:
        tab: Operations
        style: row
        columns: 3
        icon: authentik.png
      Documents & Files:
        tab: Operations
        style: row
        columns: 3
        icon: paperless-ngx.png
      Utilities:
        tab: Operations
        style: row
        columns: 4
        icon: mdi-tools
      # -- Infrastructure tab --
      Proxmox:
        tab: Infrastructure
        style: row
        columns: 1
        icon: proxmox.png
      Cluster VMs:
        tab: Infrastructure
        style: row
        columns: 3
        icon: proxmox.png
      Networking:
        tab: Infrastructure
        style: row
        columns: 3
        icon: traefik.png
      Databases:
        tab: Infrastructure
        style: row
        columns: 2
        icon: postgres.png
  widgets.yaml: |
    - kubernetes:
        cluster:
          show: true
          cpu: true
          memory: true
          showLabel: true
          label: "cluster"
        nodes:
          show: true
          cpu: true
          memory: true
          showLabel: true
    - search:
        provider: duckduckgo
        target: _blank
    - openmeteo:
        label: Weather
        latitude: 32.08
        longitude: 34.78
        timezone: Asia/Jerusalem
        units: metric
    - datetime:
        text_size: xl
        format:
          dateStyle: long
          timeStyle: short
          hourCycle: h23
  services.yaml: |
    # ==================== HOME TAB ====================
    - Streaming:
        - Jellyfin:
            icon: jellyfin.png
            href: https://benplus.app
            description: Movies, TV & Anime
            widget:
              type: jellyfin
              url: http://jellyfin-main.media.svc.cluster.local:8096
              key: {{ "{{" }}HOMEPAGE_VAR_JELLYFIN_KEY{{ "}}" }}
              enableBlocks: true
              enableNowPlaying: true
              enableUser: true
              showEpisodeNumber: true
        - Immich:
            icon: immich.png
            href: https://photos.benplus.app
            description: Photos & Videos
            widget:
              type: immich
              url: http://immich-main.media.svc.cluster.local:2283
              key: {{ "{{" }}HOMEPAGE_VAR_IMMICH_KEY{{ "}}" }}
              version: 2
        - Navidrome:
            icon: navidrome.png
            href: https://music.benplus.app
            description: Music streaming
            widget:
              type: navidrome
              url: http://navidrome.media.svc.cluster.local:4533
              user: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_USER{{ "}}" }}
              token: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_TOKEN{{ "}}" }}
              salt: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_SALT{{ "}}" }}
        - Audiobookshelf:
            icon: audiobookshelf.png
            href: https://audiobooks.benplus.app
            description: Audiobooks & Podcasts
            widget:
              type: audiobookshelf
              url: http://audiobookshelf.media.svc.cluster.local:80
              key: {{ "{{" }}HOMEPAGE_VAR_AUDIOBOOKSHELF_KEY{{ "}}" }}
        - Calibre-Web:
            icon: calibre-web.png
            href: https://books.benplus.app
            description: E-book library
            widget:
              type: calibreweb
              url: http://calibre-web.media.svc.cluster.local:8083
              username: {{ "{{" }}HOMEPAGE_VAR_CALIBRE_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_CALIBRE_PASS{{ "}}" }}
    - Requests:
        - Seerr:
            icon: overseerr.png
            href: https://request.benplus.app
            description: Request movies & TV
            widget:
              type: seerr
              url: http://seerr.media.svc.cluster.local:5055
              key: {{ "{{" }}HOMEPAGE_VAR_SEERR_KEY{{ "}}" }}
        - Seerr RU:
            icon: overseerr.png
            href: https://request-ru.benplus.app
            description: Request movies & TV (RU)
            widget:
              type: seerr
              url: http://seerr-ru.media.svc.cluster.local:5055
              key: {{ "{{" }}HOMEPAGE_VAR_SEERR_RU_KEY{{ "}}" }}
        - Shelfmark:
            icon: mdi-bookshelf
            href: https://request-books.benplus.app
            description: Book requests
    - Home & Life:
        - Home Assistant:
            icon: home-assistant.png
            href: https://ha.internal.starktastic.net
            description: Smart home control
            widget:
              type: homeassistant
              url: http://home-assistant-main.home-automation.svc.cluster.local:8123
              key: {{ "{{" }}HOMEPAGE_VAR_HASS_KEY{{ "}}" }}
        - Zigbee2MQTT:
            icon: zigbee2mqtt.png
            href: https://zigbee2mqtt.internal.starktastic.net
            description: Zigbee device management
        - Mealie:
            icon: mealie.png
            href: https://mealie.starktastic.net
            description: Recipe manager
            widget:
              type: mealie
              url: http://mealie.operations.svc.cluster.local:9000
              key: {{ "{{" }}HOMEPAGE_VAR_MEALIE_KEY{{ "}}" }}
              version: 2
        - Cineplete:
            icon: mdi-movie-open-check
            href: https://cineplete.internal.starktastic.net
            description: Movie tracker
    - Calendar:
        - Calendar:
            widget:
              type: calendar
              view: monthly
              maxEvents: 15
              showTime: true
              integrations:
                - type: sonarr
                  service_group: Movies & TV
                  service_name: Sonarr
                  color: "#3B82F6"
                  params:
                    unmonitored: true
                - type: sonarr
                  service_group: Movies & TV
                  service_name: Sonarr RU
                  color: "#60A5FA"
                  params:
                    unmonitored: true
                - type: radarr
                  service_group: Movies & TV
                  service_name: Radarr
                  color: "#DC2626"
                  params:
                    unmonitored: true
                - type: radarr
                  service_group: Movies & TV
                  service_name: Radarr RU
                  color: "#F87171"
                  params:
                    unmonitored: true
                - type: lidarr
                  service_group: Music & Books
                  service_name: Lidarr
                  color: "#22C55E"
                  params:
                    unmonitored: true
    # ==================== MEDIA TAB ====================
    - Movies & TV:
        - Radarr:
            icon: radarr.png
            href: https://radarr.internal.starktastic.net
            description: Movie management
            widget:
              type: radarr
              url: http://radarr.media.svc.cluster.local:7878
              key: {{ "{{" }}HOMEPAGE_VAR_RADARR_KEY{{ "}}" }}
              enableQueue: true
        - Radarr RU:
            icon: radarr.png
            href: https://radarr-ru.internal.starktastic.net
            description: Movie management (RU)
            widget:
              type: radarr
              url: http://radarr-ru.media.svc.cluster.local:7878
              key: {{ "{{" }}HOMEPAGE_VAR_RADARR_RU_KEY{{ "}}" }}
              enableQueue: true
        - Sonarr:
            icon: sonarr.png
            href: https://sonarr.internal.starktastic.net
            description: TV series management
            widget:
              type: sonarr
              url: http://sonarr.media.svc.cluster.local:8989
              key: {{ "{{" }}HOMEPAGE_VAR_SONARR_KEY{{ "}}" }}
              enableQueue: true
        - Sonarr RU:
            icon: sonarr.png
            href: https://sonarr-ru.internal.starktastic.net
            description: TV series management (RU)
            widget:
              type: sonarr
              url: http://sonarr-ru.media.svc.cluster.local:8989
              key: {{ "{{" }}HOMEPAGE_VAR_SONARR_RU_KEY{{ "}}" }}
              enableQueue: true
    - Music & Books:
        - Lidarr:
            icon: lidarr.png
            href: https://lidarr.internal.starktastic.net
            description: Music management
            widget:
              type: lidarr
              url: http://lidarr.media.svc.cluster.local:8686
              key: {{ "{{" }}HOMEPAGE_VAR_LIDARR_KEY{{ "}}" }}
        - Bazarr:
            icon: bazarr.png
            href: https://bazarr.internal.starktastic.net
            description: Subtitle management
            widget:
              type: bazarr
              url: http://bazarr.media.svc.cluster.local:6767
              key: {{ "{{" }}HOMEPAGE_VAR_BAZARR_KEY{{ "}}" }}
        - Lingarr:
            icon: mdi-translate
            href: https://lingarr.internal.starktastic.net
            description: Subtitle translation
        - Prowlarr:
            icon: prowlarr.png
            href: https://prowlarr.internal.starktastic.net
            description: Indexer management
            widget:
              type: prowlarr
              url: http://prowlarr.media.svc.cluster.local:9696
              key: {{ "{{" }}HOMEPAGE_VAR_PROWLARR_KEY{{ "}}" }}
        - Autobrr:
            icon: autobrr.png
            href: https://autobrr.internal.starktastic.net
            description: Torrent automation
            widget:
              type: autobrr
              url: http://autobrr.media.svc.cluster.local:7474
              key: {{ "{{" }}HOMEPAGE_VAR_AUTOBRR_KEY{{ "}}" }}
    - Downloads:
        - qBittorrent:
            icon: qbittorrent.png
            href: https://qbittorrent.internal.starktastic.net
            description: Torrent client
            widget:
              type: qbittorrent
              url: http://qbittorrent-main.media.svc.cluster.local:8080
        - qBittorrent RU:
            icon: qbittorrent.png
            href: https://qbittorrent-ru.internal.starktastic.net
            description: Torrent client (RU)
            widget:
              type: qbittorrent
              url: http://qbittorrent-ru-main.media.svc.cluster.local:8080
    # ==================== OPERATIONS TAB ====================
    - Productivity:
        - Vikunja:
            icon: vikunja.png
            href: https://vikunja.starktastic.net
            description: Tasks & to-dos
            widget:
              type: vikunja
              url: http://vikunja.operations.svc.cluster.local:3456
              key: {{ "{{" }}HOMEPAGE_VAR_VIKUNJA_KEY{{ "}}" }}
              enableTaskList: true
              version: 2
        - Karakeep:
            icon: karakeep.png
            href: https://karakeep.starktastic.net
            description: Bookmarks & Read-later
            widget:
              type: karakeep
              url: http://karakeep.operations.svc.cluster.local:3000
              key: {{ "{{" }}HOMEPAGE_VAR_KARAKEEP_KEY{{ "}}" }}
        - Listmonk:
            icon: listmonk.png
            href: https://listmonk.starktastic.net
            description: Newsletter manager
        - ByteStash:
            icon: bytestash.png
            href: https://bytestash.internal.starktastic.net
            description: Code snippets
    - Monitoring:
        - Grafana:
            icon: grafana.png
            href: https://grafana.internal.starktastic.net
            description: Dashboards & Alerting
            widget:
              type: grafana
              alerts: alertmanager
              url: http://kube-prometheus-stack-grafana.monitoring.svc.cluster.local:80
              username: {{ "{{" }}HOMEPAGE_VAR_GRAFANA_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_GRAFANA_PASS{{ "}}" }}
              version: 2
        - Prometheus:
            icon: prometheus.png
            href: https://grafana.internal.starktastic.net/explore
            description: Metrics collection
            widget:
              type: prometheus
              url: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090
        - Traefik:
            icon: traefik.png
            href: https://traefik.internal.starktastic.net
            description: Reverse proxy
            widget:
              type: traefik
              url: http://traefik.traefik-system.svc.cluster.local:9000
        - CrowdSec:
            icon: crowdsec.png
            href: https://app.crowdsec.net
            description: Security engine
    - Security:
        - Authentik:
            icon: authentik.png
            href: https://auth.starktastic.net
            description: Identity provider
            widget:
              type: authentik
              url: http://authentik-server.authentik.svc.cluster.local:80
              key: {{ "{{" }}HOMEPAGE_VAR_AUTHENTIK_KEY{{ "}}" }}
              version: 2
        - Vaultwarden:
            icon: vaultwarden.png
            href: https://vaultwarden.internal.starktastic.net
            description: Password manager
        - ArgoCD:
            icon: argocd.png
            href: https://argocd.internal.starktastic.net
            description: GitOps deployment
            widget:
              type: argocd
              url: http://argocd-server.argocd.svc.cluster.local:80
              key: {{ "{{" }}HOMEPAGE_VAR_ARGOCD_KEY{{ "}}" }}
    - Documents & Files:
        - Paperless-ngx:
            icon: paperless-ngx.png
            href: https://paperless.internal.starktastic.net
            description: Document management
            widget:
              type: paperlessngx
              url: http://paperless-ngx.operations.svc.cluster.local:8000
              key: {{ "{{" }}HOMEPAGE_VAR_PAPERLESS_KEY{{ "}}" }}
        - Filebrowser:
            icon: filebrowser.png
            href: https://files.internal.starktastic.net
            description: Web file manager
        - Changedetection:
            icon: changedetection-io.png
            href: https://changedetection.internal.starktastic.net
            description: Website change monitor
            widget:
              type: changedetectionio
              url: http://changedetection.operations.svc.cluster.local:5000
              key: {{ "{{" }}HOMEPAGE_VAR_CHANGEDETECTION_KEY{{ "}}" }}
    - Utilities:
        - SearXNG:
            icon: searxng.png
            href: https://search.starktastic.net
            description: Private search engine
            widget:
              type: searxng
              url: http://searxng.operations.svc.cluster.local:8080
        - CyberChef:
            icon: cyberchef.png
            href: https://cyberchef.starktastic.net
            description: Data transformation
        - Stirling PDF:
            icon: stirling-pdf.png
            href: https://pdf.starktastic.net
            description: PDF tools
        - MeTube:
            icon: metube.png
            href: https://metube.benplus.app
            description: Video downloader
        - MicroBin:
            icon: microbin.png
            href: https://microbin.starktastic.net
            description: Paste & share
        - PairDrop:
            icon: pairdrop.png
            href: https://pairdrop.starktastic.net
            description: Local file sharing
        - Excalidash:
            icon: excalidraw.png
            href: https://excalidash.starktastic.net
            description: Collaborative whiteboard
        - ConvertX:
            icon: convertx.png
            href: https://convertx.starktastic.net
            description: File converter
        - ntfy:
            icon: ntfy.png
            href: https://ntfy.starktastic.net
            description: Push notifications
    # ==================== INFRASTRUCTURE TAB ====================
    - Proxmox:
        - Proxmox VE:
            icon: proxmox.png
            href: https://10.9.9.20:8006
            description: Hypervisor
            widget:
              type: proxmox
              url: https://10.9.9.20:8006
              username: {{ "{{" }}HOMEPAGE_VAR_PROXMOX_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_PROXMOX_PASS{{ "}}" }}
              node: pve
    - Cluster VMs:
        - kube-master-01:
            icon: proxmox.png
            description: Control plane (4c / 16GB)
            proxmoxNode: pve
            proxmoxVMID: 200
        - kube-worker-01:
            icon: proxmox.png
            description: Worker node (6c / 28GB / GPU)
            proxmoxNode: pve
            proxmoxVMID: 201
        - kube-worker-02:
            icon: proxmox.png
            description: Worker node (6c / 28GB / GPU)
            proxmoxNode: pve
            proxmoxVMID: 202
    - Networking:
        - Traefik Dashboard:
            icon: traefik.png
            href: https://traefik.internal.starktastic.net
            description: Reverse proxy dashboard
        - MetalLB:
            icon: metallb.png
            description: "Load balancer (ext: 10.9.8.90 / int: 10.9.9.90)"
        - CrowdSec LAPI:
            icon: crowdsec.png
            href: https://app.crowdsec.net
            description: Security decisions API
    - Databases:
        - PostgreSQL:
            icon: postgres.png
            description: Database server
        - pgAdmin:
            icon: pgadmin.png
            href: https://pgadmin.internal.starktastic.net
            description: Database management
  bookmarks.yaml: |
    - Developer:
        - GitHub:
            - abbr: GH
              href: https://github.com/Starktastic-Homelab
        - ArgoCD:
            - abbr: CD
              href: https://argocd.internal.starktastic.net
    - Documentation:
        - Homepage:
            - abbr: HP
              href: https://gethomepage.dev
        - Kubernetes:
            - abbr: K8
              href: https://kubernetes.io/docs
    - External:
        - Cloudflare:
            - abbr: CF
              href: https://dash.cloudflare.com
        - Mailgun:
            - abbr: MG
              href: https://app.mailgun.com
````

- [ ] **Step 2: Format with Prettier**

Run: `npx --yes prettier --write services/operations/homepage-admin/manifests/templates/configmap.yaml`
Expected: `... configmap.yaml <ms>ms` (file listed; no error).

- [ ] **Step 3: Verify Helm renders the chart**

Run: `helm template homepage-admin services/operations/homepage-admin/manifests -f templates/globals.yaml > /tmp/admin-render.yaml && echo OK`
Expected: prints `OK` (non-zero exit = template error to fix).

- [ ] **Step 4: Verify HOMEPAGE_VAR escaping rendered correctly**

Run: `grep -c '{{HOMEPAGE_VAR_' /tmp/admin-render.yaml`
Expected: a number `> 0` (e.g. ~20). Then confirm no broken escaping remains:
Run: `grep -n '{{ "{{"' /tmp/admin-render.yaml || echo "clean"`
Expected: prints `clean` (the escaped form must not survive into rendered output).

- [ ] **Step 5: Verify section + Vikunja presence**

Run: `grep -E '^    - (Streaming|Requests|Home & Life|Calendar|Movies & TV|Music & Books|Downloads|Productivity|Monitoring|Security|Documents & Files|Utilities|Proxmox|Cluster VMs|Networking|Databases):' services/operations/homepage-admin/manifests/templates/configmap.yaml | wc -l`
Expected: `16` (all 16 sections present).
Run: `grep -c 'HOMEPAGE_VAR_VIKUNJA_KEY' services/operations/homepage-admin/manifests/templates/configmap.yaml`
Expected: `1`.

- [ ] **Step 6: Commit**

```bash
git add services/operations/homepage-admin/manifests/templates/configmap.yaml
git commit -m "feat(homepage-admin): rebuild configmap with canonical taxonomy + Vikunja widget

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 2: Rewrite the regular ConfigMap (flat, non-internal subset)

**Files:**
- Modify (replace entire contents): `services/operations/homepage/manifests/templates/configmap.yaml`

- [ ] **Step 1: Replace the entire file with the content below**

````yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: homepage-config
  namespace: operations
data:
  docker.yaml: ""
  custom.js: ""
  custom.css: ""
  kubernetes.yaml: |
    mode: disabled
  settings.yaml: |
    title: Starktastic
    headerStyle: boxedWidgets
    statusStyle: dot
    useEqualHeights: true
    hideVersion: true
    disableCollapse: false
    disableIndexing: true
    iconStyle: theme
    quicklaunch:
      searchDescriptions: true
      hideInternetSearch: false
      showSearchSuggestions: true
      provider: duckduckgo
    layout:
      Streaming:
        style: row
        columns: 5
        icon: jellyfin.png
      Requests:
        style: row
        columns: 3
        icon: overseerr.png
      Home & Life:
        style: row
        columns: 1
        icon: home-assistant.png
      Productivity:
        style: row
        columns: 3
        icon: vikunja.png
      Security:
        style: row
        columns: 1
        icon: authentik.png
      Utilities:
        style: row
        columns: 4
        icon: mdi-tools
  widgets.yaml: |
    - search:
        provider: duckduckgo
        target: _blank
    - openmeteo:
        label: Weather
        latitude: 32.08
        longitude: 34.78
        timezone: Asia/Jerusalem
        units: metric
    - datetime:
        text_size: xl
        format:
          dateStyle: long
          timeStyle: short
          hourCycle: h23
  services.yaml: |
    - Streaming:
        - Jellyfin:
            icon: jellyfin.png
            href: https://benplus.app
            description: Movies, TV & Anime
            widget:
              type: jellyfin
              url: http://jellyfin-main.media.svc.cluster.local:8096
              key: {{ "{{" }}HOMEPAGE_VAR_JELLYFIN_KEY{{ "}}" }}
              enableBlocks: true
              enableNowPlaying: true
              enableUser: true
              showEpisodeNumber: true
        - Immich:
            icon: immich.png
            href: https://photos.benplus.app
            description: Photos & Videos
            widget:
              type: immich
              url: http://immich-main.media.svc.cluster.local:2283
              key: {{ "{{" }}HOMEPAGE_VAR_IMMICH_KEY{{ "}}" }}
              version: 2
        - Navidrome:
            icon: navidrome.png
            href: https://music.benplus.app
            description: Music streaming
            widget:
              type: navidrome
              url: http://navidrome.media.svc.cluster.local:4533
              user: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_USER{{ "}}" }}
              token: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_TOKEN{{ "}}" }}
              salt: {{ "{{" }}HOMEPAGE_VAR_NAVIDROME_SALT{{ "}}" }}
        - Audiobookshelf:
            icon: audiobookshelf.png
            href: https://audiobooks.benplus.app
            description: Audiobooks & Podcasts
            widget:
              type: audiobookshelf
              url: http://audiobookshelf.media.svc.cluster.local:80
              key: {{ "{{" }}HOMEPAGE_VAR_AUDIOBOOKSHELF_KEY{{ "}}" }}
        - Calibre-Web:
            icon: calibre-web.png
            href: https://books.benplus.app
            description: E-book library
            widget:
              type: calibreweb
              url: http://calibre-web.media.svc.cluster.local:8083
              username: {{ "{{" }}HOMEPAGE_VAR_CALIBRE_USER{{ "}}" }}
              password: {{ "{{" }}HOMEPAGE_VAR_CALIBRE_PASS{{ "}}" }}
    - Requests:
        - Seerr:
            icon: overseerr.png
            href: https://request.benplus.app
            description: Request movies & TV
            widget:
              type: seerr
              url: http://seerr.media.svc.cluster.local:5055
              key: {{ "{{" }}HOMEPAGE_VAR_SEERR_KEY{{ "}}" }}
        - Seerr RU:
            icon: overseerr.png
            href: https://request-ru.benplus.app
            description: Request movies & TV (RU)
            widget:
              type: seerr
              url: http://seerr-ru.media.svc.cluster.local:5055
              key: {{ "{{" }}HOMEPAGE_VAR_SEERR_RU_KEY{{ "}}" }}
        - Shelfmark:
            icon: mdi-bookshelf
            href: https://request-books.benplus.app
            description: Book requests
    - Home & Life:
        - Mealie:
            icon: mealie.png
            href: https://mealie.starktastic.net
            description: Recipe manager
            widget:
              type: mealie
              url: http://mealie.operations.svc.cluster.local:9000
              key: {{ "{{" }}HOMEPAGE_VAR_MEALIE_KEY{{ "}}" }}
              version: 2
    - Productivity:
        - Vikunja:
            icon: vikunja.png
            href: https://vikunja.starktastic.net
            description: Tasks & to-dos
            widget:
              type: vikunja
              url: http://vikunja.operations.svc.cluster.local:3456
              key: {{ "{{" }}HOMEPAGE_VAR_VIKUNJA_KEY{{ "}}" }}
              enableTaskList: true
              version: 2
        - Karakeep:
            icon: karakeep.png
            href: https://karakeep.starktastic.net
            description: Bookmarks & Read-later
            widget:
              type: karakeep
              url: http://karakeep.operations.svc.cluster.local:3000
              key: {{ "{{" }}HOMEPAGE_VAR_KARAKEEP_KEY{{ "}}" }}
        - Listmonk:
            icon: listmonk.png
            href: https://listmonk.starktastic.net
            description: Newsletter manager
    - Security:
        - Authentik:
            icon: authentik.png
            href: https://auth.starktastic.net
            description: Identity provider
    - Utilities:
        - SearXNG:
            icon: searxng.png
            href: https://search.starktastic.net
            description: Private search engine
            widget:
              type: searxng
              url: http://searxng.operations.svc.cluster.local:8080
        - CyberChef:
            icon: cyberchef.png
            href: https://cyberchef.starktastic.net
            description: Data transformation
        - Stirling PDF:
            icon: stirling-pdf.png
            href: https://pdf.starktastic.net
            description: PDF tools
        - MeTube:
            icon: metube.png
            href: https://metube.benplus.app
            description: Video downloader
        - MicroBin:
            icon: microbin.png
            href: https://microbin.starktastic.net
            description: Paste & share
        - PairDrop:
            icon: pairdrop.png
            href: https://pairdrop.starktastic.net
            description: Local file sharing
        - Excalidash:
            icon: excalidraw.png
            href: https://excalidash.starktastic.net
            description: Collaborative whiteboard
        - ConvertX:
            icon: convertx.png
            href: https://convertx.starktastic.net
            description: File converter
        - ntfy:
            icon: ntfy.png
            href: https://ntfy.starktastic.net
            description: Push notifications
  bookmarks.yaml: |
    - Links:
        - GitHub:
            - abbr: GH
              href: https://github.com/Starktastic-Homelab
````

- [ ] **Step 2: Format with Prettier**

Run: `npx --yes prettier --write services/operations/homepage/manifests/templates/configmap.yaml`
Expected: file listed; no error.

- [ ] **Step 3: Verify Helm renders the chart**

Run: `helm template homepage services/operations/homepage/manifests -f templates/globals.yaml > /tmp/regular-render.yaml && echo OK`
Expected: prints `OK`.

- [ ] **Step 4: Verify escaping + no internal hosts leaked into the public instance**

Run: `grep -n '{{ "{{"' /tmp/regular-render.yaml || echo "clean"`
Expected: `clean`.
Run: `grep -c 'internal.starktastic.net' services/operations/homepage/manifests/templates/configmap.yaml`
Expected: `0` (the public instance must contain no `*.internal.starktastic.net` hosts).

- [ ] **Step 5: Verify Authentik is link-only here (no widget/key)**

Run: `grep -n 'HOMEPAGE_VAR_AUTHENTIK_KEY' services/operations/homepage/manifests/templates/configmap.yaml || echo "none"`
Expected: `none` (public Authentik is link-only by design).
Run: `grep -c 'HOMEPAGE_VAR_VIKUNJA_KEY' services/operations/homepage/manifests/templates/configmap.yaml`
Expected: `1`.

- [ ] **Step 6: Commit**

```bash
git add services/operations/homepage/manifests/templates/configmap.yaml
git commit -m "feat(homepage): rebuild public configmap with canonical taxonomy + Vikunja widget

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Task 3: Seal the Vikunja API key into both secrets (USER manual step)

**Files:**
- Modify: `services/operations/homepage-admin/manifests/templates/secrets.yaml`
- Modify: `services/operations/homepage/manifests/templates/secrets.yaml`

> This task **cannot be done by an automated agent** — it needs the live cluster's kubeseal certificate and the real Vikunja API token. The configmaps above already reference `{{HOMEPAGE_VAR_VIKUNJA_KEY}}`; until this is sealed, the Vikunja widget shows an auth error but the tile/link still works.

- [ ] **Step 1: Create a Vikunja API token**

In the Vikunja UI (`https://vikunja.starktastic.net`) → Settings → API Tokens → create a token with read scope for tasks/projects. Copy the token value.

- [ ] **Step 2: Seal the value for the admin secret**

Run (replace `<TOKEN>`; the existing `secrets.yaml` files in this repo show the cert is the standard cluster sealed-secrets controller cert):
```bash
echo -n '<TOKEN>' | kubeseal --raw \
  --namespace operations \
  --name homepage-admin-secrets \
  --controller-name sealed-secrets \
  --controller-namespace kube-system
```
Expected: a long base64 ciphertext string.

- [ ] **Step 3: Add the sealed value to the admin secret**

Edit `services/operations/homepage-admin/manifests/templates/secrets.yaml` and add under `spec.encryptedData:`:
```yaml
    HOMEPAGE_VAR_VIKUNJA_KEY: <CIPHERTEXT_FROM_STEP_2>
```

- [ ] **Step 4: Seal the value for the public secret**

Run:
```bash
echo -n '<TOKEN>' | kubeseal --raw \
  --namespace operations \
  --name homepage-secrets \
  --controller-name sealed-secrets \
  --controller-namespace kube-system
```
Expected: a different ciphertext string (sealed values are name/namespace-scoped).

- [ ] **Step 5: Add the sealed value to the public secret**

Edit `services/operations/homepage/manifests/templates/secrets.yaml` and add under `spec.encryptedData:`:
```yaml
    HOMEPAGE_VAR_VIKUNJA_KEY: <CIPHERTEXT_FROM_STEP_4>
```

- [ ] **Step 6: Format and commit**

```bash
npx --yes prettier --write services/operations/homepage-admin/manifests/templates/secrets.yaml services/operations/homepage/manifests/templates/secrets.yaml
git add services/operations/homepage-admin/manifests/templates/secrets.yaml services/operations/homepage/manifests/templates/secrets.yaml
git commit -m "feat(homepage): add sealed Vikunja widget API key to both instances

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

> Confirm the exact `kubeseal` controller name/namespace against how other SealedSecrets in this repo were generated if Steps 2/4 error.

---

## Self-Review (against spec)

**Spec coverage:**
- Architecture (Approach A, admin tabbed / regular flat, canonical taxonomy) → Tasks 1 & 2 settings/layout blocks. ✅
- Full admin inventory (every section + widget) → Task 1 services.yaml. ✅
- Regular non-internal subset (6 sections) → Task 2 services.yaml. ✅
- Vikunja added both, widget both → Tasks 1 & 2 + secret Task 3. ✅
- Authentik: admin widget / public link-only → Task 1 (widget) + Task 2 (link-only, Step 5 assertion). ✅
- Paperless in Documents & Files only → Task 1. ✅
- ntfy in Utilities both → Tasks 1 & 2. ✅
- Karakeep/Listmonk/ByteStash → Productivity (admin); Karakeep/Listmonk → Productivity (regular). ✅
- Audiobookshelf/Calibre-Web → Streaming (de-duplicated from Music & Books) → Tasks 1 & 2. ✅
- Info widgets (admin adds kubernetes; both keep search/openmeteo/datetime) → Tasks 1 & 2. ✅
- kubernetes mode (admin cluster / regular disabled), proxmox.yaml admin-only → Tasks 1 & 2. ✅
- Bookmarks (admin 3 groups unchanged; regular Links/GitHub only, Authentik bookmark removed) → Tasks 1 & 2. ✅
- New sealed secret `HOMEPAGE_VAR_VIKUNJA_KEY` both → Task 3. ✅

**Placeholder scan:** none — full file contents provided for both configmaps; Task 3 placeholders are user-supplied secret material by necessity (documented as a manual step).

**Type/name consistency:** widget `type:` values, `HOMEPAGE_VAR_*` names, and cluster service URLs reused verbatim from the existing working configmaps; Vikunja URL/port verified against `services/operations/vikunja/values.yaml` (`vikunja.operations.svc.cluster.local:3456`).
