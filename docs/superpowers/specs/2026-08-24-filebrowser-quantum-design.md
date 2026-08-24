# Replace FileBrowser with FileBrowser Quantum

Date: 2026-08-24
Status: Approved, not yet implemented

## Problem

`services/operations/filebrowser` runs `filebrowser/filebrowser:v2.63.23` with
`FB_NOAUTH=true`, its BoltDB on NFS at `/srv/apps/filebrowser/filebrowser.db`,
and a single `/srv` root spanning two mounts. Access control is entirely
external: the Traefik IngressRoute carries `authentik-middleware`, so anyone who
clears forward-auth gets unrestricted read-write over both mounts.

Four things are wanted from the replacement, all of which upstream FileBrowser
does not offer and FileBrowser Quantum (`gtsteffaniak/filebrowser`) does:

- Indexed search across both trees.
- Native Authentik OIDC, rather than a proxy-auth shim with no user identity.
- Real multi-source support, so `apps` and `media` are separate roots with
  separate rules instead of two directories under one tree.
- Preview/gallery UX for the media library.

There is a fifth thing, not asked for but exposed by the work: `/srv/apps` is
the `nfs-pv` dynamic provisioner root (`/mnt/apps/pv`, laid out as
`<namespace>/<pvc-name>`). It contains every app's persistent state — Vaultwarden
data, Authentik media, Paperless documents. Today that is read-write to any
authenticated user.

The new access model narrows this to a single admin group. It does not make the
tree unshareable — sharing from `apps` is explicitly retained (see Decisions) —
so the remaining exposure is deliberate and admin-initiated rather than ambient.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Release line | `1.5.3-stable` | v2.0.x is beta. Nothing migrates either way, and the v1→v2 config rewrite is ~6 lines later. |
| Image variant | full, not `-slim` | 86MB vs 26MB; the difference is ffmpeg/exiftool, i.e. video thumbnails. |
| State placement | one 20Gi `local-path` RWO PVC | SQLite and BoltDB over NFS is a corruption/perf trap. Accepts a node pin. |
| Access model | admin-only, both sources | `userGroups` restricted to `authentik Admins`. |
| Sharing | permitted from both sources | Explicitly requested; `private` is not set on either source. |
| Share reach | split ingress | Full UI stays internal; only `/public/` is internet-facing. |
| Break-glass login | none | `password.enabled: false`. Recovery is editing the ConfigMap. |

### Why state cannot stay on NFS

Quantum keeps three things under its data directory:

- `database.db` — BoltDB: users, settings, **share links**.
- `cache/sql/index_<source>.db` — SQLite index, one per source.
  (`backend/database/sql/index.go:74` joins `Server.CacheDir` + `sql` +
  `index_<name>.db`.)
- thumbnails and the archive spool.

Both engines use mmap and file locking. Beyond that, Quantum runs a **mandatory
10MB write/read speed test against `cacheDir` at startup** and fatals if the
directory cannot be prepared (`backend/common/settings/config.go`,
`testCacheDirSpeed` / `PrepareDownloadSpoolDir`). NFS is disqualified.

`emptyDir` was rejected: it does not reduce NVMe wear — the index is written to
node-local storage either way — it merely discards the result, forcing a full
re-index of 10Ti of NFS media on every pod restart. Persisting the volume writes
*less* over time, not more.

Context on wear tolerance: the NVMe is at 15% used / 31.3 TB written, of which
~81% of pool writes are Jellyfin transcode scratch. A file index plus thumbnails
is noise against that.

### Accepted risk

Share links live in BoltDB on node-local storage. If the node backing the PVC is
lost, the index and thumbnails rebuild themselves but **existing share links do
not** and must be re-issued. This is accepted; re-issuing a link is cheap.

## Architecture

### File layout

```
services/operations/filebrowser/
  app.yaml                      MODIFIED  manifests + helmManifests: true, auth: false
  values.yaml                   REWRITTEN
  manifests/
    Chart.yaml                  NEW
    templates/
      config.yaml               NEW  ConfigMap → Quantum config.yaml
      data-pvc.yaml             NEW  20Gi local-path RWO
      secret.yaml               NEW  SealedSecret
      public-ingressroute.yaml  NEW  files.<public>, PathPrefix(`/public/`)

services/operations/homepage-admin/manifests/templates/configmap.yaml
                                MODIFIED  drop the dead `widget:` block
templates/ingress-chart/
  values.yaml                   MODIFIED  add `ingress.probePath: ""`
  templates/probe.yaml          MODIFIED  append probePath to the target URL
```

`infrastructure/base-configs/templates/filebrowser-storage/{apps,media}.yaml` is
**unchanged**. Both NFS PVs and PVCs carry over verbatim; only their role changes,
from two directories under one root to two named sources.

### Volumes

| Mount | Backing | Notes |
|---|---|---|
| `/srv/apps` | `filebrowser-apps-pvc` (NFS RWX) | existing, unchanged |
| `/srv/media` | `filebrowser-media-pvc` (NFS RWX) | existing, unchanged |
| `/home/filebrowser/data` | new 20Gi `local-path` RWO | BoltDB, SQLite index, thumbnails, archive spool |
| `/config` | `filebrowser-config` ConfigMap | read-only, `config.yaml` only |

`/home/filebrowser/data` is Quantum's Docker default data directory, which is
also where it looks for `config.yaml`. Mounting the ConfigMap there directly
would mask the data volume, and a `subPath` mount would pin the file to its
value at pod creation, defeating Reloader. Instead the ConfigMap mounts at its
own path and `FILEBROWSER_CONFIG=/config/config.yaml` points Quantum at it.

`backend/cmd/cli.go:37-46` resolves the config path as `-c` flag →
`FILEBROWSER_CONFIG` → `config.yaml`, and fatals outright if the env var names a
file that does not exist. A missing or misnamed ConfigMap therefore fails fast
and loudly rather than silently starting on defaults.

The `local-path` PVC follows `services/media/jellyfin/manifests/cache-pvc.yaml`:
RWO, `storageClassName: local-path` stated explicitly. It must stay explicit;
k3s recreates its `local-path` StorageClass on every restart, making it the
newest default and the winner of the newest-wins tiebreak (ADR 0009).

### Deletions

- The `init-db-dir` busybox initContainer. It existed only to `mkdir` and `chown`
  `/srv/apps/filebrowser` for the BoltDB, which now lives on `local-path`.
- The `FB_ROOT` / `FB_DATABASE` / `FB_NOAUTH` env block. Quantum is
  file-configured.
- The homepage `widget:` block (see below).

### Retained deliberately

`runAsUser: 1000` / `runAsGroup: 1000`, plus `fsGroup: 1000` inherited from
`templates/common.yaml`. Files written to `/srv/media` must keep landing as
`1000:1000` or ownership desyncs with the \*arr stack sharing
`/mnt/main/media` through `media-library-pvc`.

### Ingress

Two routes.

**Internal** — shared `ingress-chart`, `files.internal.starktastic.net`,
entrypoint `websec-int`, `auth: false`.

`auth: false` is load-bearing, not tidiness. Leaving `authentik-middleware`
attached would gate `/api/auth/oidc/callback` behind Authentik's proxy provider,
and would gate `/public/` share links behind a login — defeating the purpose.
This also matches every other native-OIDC service here: karakeep, mealie,
vikunja, paperless-ngx all set `auth: false`.

**Public** — hand-written IngressRoute, `files.<public domain>`, entrypoint
`websecure`, middlewares `crowdsec-bouncer` + `rate-limit-strong`, matching:

```
Host(`files.{{ .Values.global.domains.public }}`) && PathPrefix(`/public/`)
```

Every unauthenticated share route in Quantum lives under one prefix
(`backend/http/httpRouter.go:222`: `publicPath := config.Server.BaseURL + "public"`),
covering `/public/share/<hash>`, `/public/api/...` and `/public/static/`. All
public API handlers are wrapped in `withHashFile`, so they require the share
hash. The internet-facing surface is therefore exactly the hash-gated share
handlers; the file tree, the authenticated API and the login page are
unreachable from outside.

TLS needs no work: `*.starktastic.net` is already covered by
`starktastic-net-tls` via the default Traefik store.

`helmManifests: true` (precedent: `homepage-admin`) is required so the manifests
chart can read `.Values.global.domains.public` rather than hard-coding the
domain — consistent with the repo rule that each value has exactly one home.

#### Interaction with `check-homepage-coverage.py`

`static_hosts()` collects `Host()` rules from standalone IngressRoute manifests
but skips any host containing `{{` (`scripts/check-homepage-coverage.py`). The
templated form above is therefore invisible to the check, which is the correct
outcome: `files.starktastic.net` is not a browsable service — its root 404s at
Traefik — so it should not be required on a dashboard. No exclusion list entry
is needed and CI stays green.

## Configuration

`manifests/templates/config.yaml`, mounted read-only at `/config/config.yaml`
and selected via `FILEBROWSER_CONFIG`:

```yaml
server:
  port: 80
  database: /home/filebrowser/data/database.db
  cacheDir: /home/filebrowser/data/cache
  externalUrl: "https://files.{{ .Values.global.domains.public }}"
  numImageProcessors: 2
  maxArchiveSize: 5
  logging:
    - levels: "info|warning|error"
  sources:
    - path: /srv/apps
      name: apps
      config:
        defaultEnabled: true
    - path: /srv/media
      name: media
      config:
        defaultEnabled: true
http:
  trustedHeaders:
    - X-Forwarded-Proto
    - X-Forwarded-Host
    - X-Forwarded-For
    - X-Real-IP
auth:
  methods:
    password:
      enabled: false
    oidc:
      enabled: true
      issuerUrl: "https://auth.{{ .Values.global.domains.public }}/application/o/filebrowser/"
      adminGroup: "authentik Admins"
      userGroups: ["authentik Admins"]
userDefaults:
  account:
    permissions:
      admin: false
      modify: true
      create: true
      delete: true
      share: true
      download: true
      api: false
```

Notes on specific values:

- **`maxArchiveSize: 5`** (GB), down from a default of 20. Archives spool into
  `cacheDir`, which is the same 20Gi volume holding the index and thumbnails.
  The default lets one "download this folder" fill the disk out from under the
  index.
- **`http.trustedHeaders`** is mandatory. Without it Quantum derives the OIDC
  callback from Traefik's internal `http://` request and Authentik rejects the
  `redirect_uri`. `http` is a valid top-level key in v1.5.x
  (`config.go`, `validFields`); it becomes `trustProxyHeaders: true` in v2.
- **`numImageProcessors: 2`**, down from a default of "all cores", so thumbnail
  generation does not contend with Jellyfin transcoding.
- **`externalUrl`** makes generated share links point at the public host. It is
  not used for the OIDC callback, so it does not interfere with the internal
  login flow.
- **`userGroups`** restricts login itself: users outside `authentik Admins` are
  denied even with a valid Authentik session.

### Secrets

`clientId`, `clientSecret` and the JWT signing secret are **not** in the
ConfigMap. They arrive via `envFrom: secretRef` from a SealedSecret, following
`bytestash-secret`:

- `FILEBROWSER_OIDC_CLIENT_ID`
- `FILEBROWSER_OIDC_CLIENT_SECRET`
- `FILEBROWSER_JWT_TOKEN_SECRET`

`loadEnvConfig()` is called at the end of `loadConfigWithDefaults()`, before
`ValidateConfig()` (`config.go:883`, `config.go:922`), so env-injected values
satisfy validation. No placeholder values are needed in the ConfigMap.

Pinning the JWT secret keeps sessions valid across pod restarts.

### Resources

`requests: 100m / 256Mi`, `limits: 1000m / 1Gi` — the mealie/listmonk shape,
with headroom for the initial 10Ti index walk.

### Reloader

`reloader.stakater.com/auto: "true"` on the controller. Quantum reads config
only at startup. The `cluster-apps` AppSet already ignores Reloader's
`last-reloaded-from` annotation on Deployments.

### Renovate

A `packageRules` entry pinning `gtstef/filebrowser` to the `-stable` channel.
Both `1.5.3-stable` and `1.5.3-beta` exist as tags, and nothing else prevents a
jump to the beta channel. This mirrors the existing `allowedVersions` rules for
qBittorrent and the LinuxServer images.

## Homepage

The homepage `filebrowser` widget must be removed, not adapted. It POSTs to
`{url}/api/login` and GETs `{url}/api/usage`
(`gethomepage/homepage`, `src/widgets/filebrowser/proxy.js`). Quantum's login is
`/api/auth/login` and it exposes no usage endpoint, so the widget cannot work.
With password auth disabled it could not authenticate in any case.

The tile keeps `href` and `siteMonitor`, so `check-homepage-coverage.py` — which
reads `href`, `siteMonitor` and `widget.url` — still finds the internal host.

## Monitoring

`app.yaml` keeps `probe: true`. With `auth: false` the ingress chart selects the
`http_2xx` blackbox module, which has `follow_redirects: true` and targets the
bare FQDN. Quantum auto-redirects to the provider when OIDC is the only enabled
method, so the probe would follow through and report green off *Authentik's*
login page — a signal that says nothing about FileBrowser.

`templates/ingress-chart` therefore gains an optional `ingress.probePath`,
defaulting to `""` so no existing app's rendered output changes. FileBrowser
sets it to `/api/health`, which is registered unauthenticated
(`httpRouter.go:85`, not wrapped in `withUser`).

## Migration and rollback

**There is no data migration.** Quantum is a hard fork with an incompatible
database, and the current instance runs `FB_NOAUTH=true` — no users, no shares,
no settings exist to carry over. `/srv/apps/filebrowser/filebrowser.db` is left
untouched on NFS and simply becomes a visible file inside the `apps` source.

Rollback is therefore a plain `git revert`: the previous deployment returns and
finds its database exactly where it left it. The only orphan is the `local-path`
PVC, which can be deleted by hand.

### Manual prerequisites

Both are out-of-band, matching every other OIDC app here — the Authentik
blueprints under `infrastructure/controllers/authentik/manifests/blueprints/`
cover branding and flows only, not per-application providers.

1. Authentik → OAuth2/OpenID provider; redirect URI
   `https://files.internal.starktastic.net/api/auth/oidc/callback`; application
   slug `filebrowser`. **This must exist before the Deployment rolls out** —
   Quantum validates OIDC discovery during startup and crashloops without it.
2. `./scripts/seal.sh filebrowser-secret operations` with the client ID, client
   secret, and a generated JWT secret.
3. Confirm `files.starktastic.net` resolves publicly. Existing public hosts such
   as `mealie` and `karakeep` imply a wildcard record, but this was not verified
   and should be checked rather than assumed.

## Failure modes

| Failure | Surface | Recovery |
|---|---|---|
| Unknown/typo'd config key | CrashLoopBackOff. The decoder uses `DisallowUnknownField()`; Quantum sleeps 5s before fatal specifically so k8s captures the error | fix the ConfigMap |
| Authentik provider missing, or Authentik down at pod start | CrashLoopBackOff — `[FATAL] Error validating OIDC auth: ... failed to create OIDC provider`. Quantum fetches OIDC discovery during startup validation, so Authentik is a hard boot dependency | create the provider before rollout; if Authentik is down, the pod recovers on its own once discovery succeeds |
| ConfigMap absent or `FILEBROWSER_CONFIG` misspelled | CrashLoopBackOff with an explicit "config file does not exist" fatal | fix the mount or the env var |
| `trustedHeaders` missing | Authentik rejects `redirect_uri` | add the header list |
| `groups` claim absent | login succeeds but the account is not admin, or is denied by `userGroups` | fix the Authentik scope mapping |
| Index DB corruption | `startupIntegrityCheck: quickCheck` detects and recreates it | none — self-healing |
| `cacheDir` full | archive/preview operations fail | lower `maxArchiveSize` or grow the PVC |
| Node backing the PVC lost | pod Pending, PVC unschedulable | delete PVC, rebind, re-index; **share links are lost** |

## Verification

**Local, before commit** — the check that matters:

Render the manifests chart, extract `config.yaml`, and boot
`gtstef/filebrowser:1.5.3-stable` against it, asserting it does not fatal during
config load. CI's kubeconform step explicitly skips `*/manifests/templates/*`,
so nothing in the pipeline validates this file, and the decoder rejects unknown
fields outright. This is the single highest-value check in the change.

This was already exercised against the real image while writing the spec, and
the intended config boots clean:

```
[INFO ] Using Config file        : /config/config.yaml
[INFO ] Auth Methods             : [oidc]
[INFO ] Sources                  : [apps: /srv/apps media: /srv/media]
[INFO ] OIDC Auth configured successfully
[INFO ] Running at               : http://0.0.0.0/
```

Confirmed at the same time: `/api/health` and `/public/api/health` both return
200 unauthenticated, and every asset referenced by `/public/share/<hash>` is
served from `/public/static/` — so ``PathPrefix(`/public/`)`` alone is a
sufficient public route, with no top-level `/static/` exception needed.

**CI** — expected to pass unchanged: yamllint, kubeconform, homepage coverage,
`argocd-diff-preview`.

**Post-deploy:**

1. `/api/health` returns 200.
2. OIDC login redirects to Authentik and returns an account with admin rights.
3. Both `apps` and `media` sources are listed.
4. Index build completes; search returns results from `media`.
5. A share link created from the UI opens over cellular, with the internal host
   unreachable.
6. A file created via the UI under `/srv/media` is owned `1000:1000`.

## Out of scope

- OnlyOffice integration (`integrations.office`).
- Per-path access rules or `denyByDefault` — unnecessary while login is
  restricted to a single admin group.
- WebDAV.
- Indexing exclusion rules (`neverWatchPath`, `folderPath`). Add only if
  re-index churn proves to be a problem; the default scheduler self-tunes.
- Any change to the two NFS PVs or their exports.
