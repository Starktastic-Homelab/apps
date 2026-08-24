# FileBrowser Quantum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unauthenticated `filebrowser/filebrowser` deployment with FileBrowser Quantum behind Authentik OIDC, keeping the same internal hostname and adding a public share-link route.

**Architecture:** The app keeps its bjw-s `app-template` Deployment but gains a sibling Helm chart under `services/operations/filebrowser/manifests/` holding a ConfigMap (Quantum's `config.yaml`), a `local-path` PVC for the index, a SealedSecret for OIDC credentials, and a public IngressRoute scoped to `PathPrefix(/public/)`. The shared `templates/ingress-chart` gains an optional `probePath` so the blackbox probe can target `/api/health` instead of the OIDC-guarded root.

**Tech Stack:** k3s, ArgoCD ApplicationSet, Helm (bjw-s `app-template` v5.1.0), Traefik IngressRoute CRDs, Bitnami SealedSecrets, Prometheus Operator `Probe` CRD, Renovate.

## Global Constraints

- Work on branch `feat/filebrowser-quantum`. It already exists and holds the spec commits.
- Spec is `docs/superpowers/specs/2026-08-24-filebrowser-quantum-design.md`. It is the source of truth; this plan implements it.
- Image is `gtstef/filebrowser`, tag `1.5.3-stable`, digest `sha256:e2ac55ccbe53d63b3f1d7d5ea5b82edf589b005a4b747b59912f97c6ba4f969e`. Never the `-beta` channel.
- Never apply anything to the live cluster. This change ships through git only; @MrStarktastic reviews and merges the PR himself.
- Every commit carries these trailers:
  ```
  Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
  Copilot-Session: ad604922-e50f-4d41-8da9-5238ab3ccff3
  ```
- Quantum's config decoder uses `yaml.DisallowUnknownField()`. Only `server`, `auth`, `integrations`, `frontend`, `userDefaults` and `http` are valid top-level keys. Any typo is a hard startup failure, and CI does not validate this file — the container boot test in Task 2 is the only gate.
- Never write a `cluster.local` FQDN; CI greps for it and fails.
- `yamllint` config is `.github/yamllint.yaml`, and it ignores `**/templates/`.

---

### Task 1: Optional `probePath` in the shared ingress chart

The blackbox probe currently targets the bare FQDN. Once filebrowser is OIDC-only, the bare FQDN returns a redirect to Authentik rather than a health signal, so the probe needs to point at `/api/health`. This is a shared chart used by every app, so the new key must default to today's exact behaviour.

**Files:**
- Modify: `templates/ingress-chart/values.yaml`
- Modify: `templates/ingress-chart/templates/probe.yaml:19`

**Interfaces:**
- Consumes: nothing.
- Produces: `ingress.probePath` — an optional string read from an app's `app.yaml`. Empty or absent means the probe target stays `https://<fqdn>` exactly as before. Task 4 sets it to `/api/health`.

- [ ] **Step 1: Add the key to the chart defaults**

Edit `templates/ingress-chart/values.yaml`. Replace the whole `ingress:` block with:

```yaml
ingress:
  enabled: false
  host: ""
  domainType: "internal"  # public | internal | media
  port: 80
  serviceName: ""
  auth: false
  rateLimit: false
  probePath: ""  # optional path (must start with /) appended to the blackbox probe target
```

- [ ] **Step 2: Capture the current probe output as a baseline**

This proves the next edit changes nothing for apps that do not set `probePath`. Note that only 12 apps set `probe: true` — an app without it renders no Probe at all, so an empty render is a broken check rather than a passing one.

```bash
cd /home/ben/Developer/homelab/apps
rm -rf /tmp/oldchart && mkdir -p /tmp/oldchart
git archive HEAD templates/ingress-chart | tar -x -C /tmp/oldchart
helm template ing /tmp/oldchart/templates/ingress-chart \
  -f templates/globals.yaml -f services/operations/stirling-pdf/app.yaml \
  --show-only templates/probe.yaml | grep -A2 'static:'
```

Expected: a `- https://pdf.starktastic.net` line with no path suffix.

- [ ] **Step 3: Append the path to the probe target**

Edit `templates/ingress-chart/templates/probe.yaml`. Replace this line:

```yaml
        - https://{{ $fqdn }}
```

with:

```yaml
        - https://{{ $fqdn }}{{ .Values.ingress.probePath | default "" }}
```

- [ ] **Step 4: Verify every existing probe is byte-identical**

Checks all 12 probe-enabled apps against the pre-change chart, and fails loudly on an empty render so a silently-skipped app cannot pass as success.

```bash
cd /home/ben/Developer/homelab/apps
fail=0
for app in $(grep -rl 'probe: true' services/*/*/app.yaml); do
  helm template ing /tmp/oldchart/templates/ingress-chart \
    -f templates/globals.yaml -f "$app" --show-only templates/probe.yaml > /tmp/b.yaml 2>/dev/null
  helm template ing templates/ingress-chart \
    -f templates/globals.yaml -f "$app" --show-only templates/probe.yaml > /tmp/a.yaml 2>/dev/null
  if ! diff -q /tmp/b.yaml /tmp/a.yaml >/dev/null || [ ! -s /tmp/a.yaml ]; then
    echo "PROBLEM: $app"; fail=1
  fi
done
[ $fail -eq 0 ] && echo "ALL 12 PROBE APPS BYTE-IDENTICAL AND NON-EMPTY"
```

Expected: `ALL 12 PROBE APPS BYTE-IDENTICAL AND NON-EMPTY`. Any `PROBLEM:` line means the default leaked a value and that app's probe target would change — stop and fix before continuing.

- [ ] **Step 5: Verify a set `probePath` lands in the target**

```bash
cd /home/ben/Developer/homelab/apps
helm template ing templates/ingress-chart \
  -f templates/globals.yaml -f services/operations/stirling-pdf/app.yaml \
  --set ingress.probePath=/api/health \
  --show-only templates/probe.yaml | grep -A2 'static:'
rm -rf /tmp/oldchart /tmp/a.yaml /tmp/b.yaml
```

Expected: `- https://pdf.starktastic.net/api/health`.

- [ ] **Step 6: Commit**

```bash
cd /home/ben/Developer/homelab/apps
git add templates/ingress-chart/values.yaml templates/ingress-chart/templates/probe.yaml
git commit -F - <<'EOF'
feat(ingress-chart): optional probePath for blackbox targets

Apps that authenticate at the edge have no useful health signal on
their bare FQDN. probePath appends a path to the probe target so those
apps can point at a dedicated health endpoint instead.

Defaults to empty, leaving every existing probe target unchanged.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: ad604922-e50f-4d41-8da9-5238ab3ccff3
EOF
```

---

### Task 2: FileBrowser Quantum manifests chart

Creates the sibling Helm chart carrying everything the Deployment needs but `app-template` cannot express: the index PVC, Quantum's `config.yaml`, and the public share-link route. Ends by booting the real image against the rendered config, which is the only validation this file ever gets.

**Files:**
- Create: `services/operations/filebrowser/manifests/Chart.yaml`
- Create: `services/operations/filebrowser/manifests/templates/data-pvc.yaml`
- Create: `services/operations/filebrowser/manifests/templates/configmap.yaml`
- Create: `services/operations/filebrowser/manifests/templates/ingressroute-public.yaml`

**Interfaces:**
- Consumes: `ingress.probePath` from Task 1 (not used here, but Task 4 wires both together).
- Produces:
  - PVC `filebrowser-data-pvc` — 20Gi, RWO, `local-path`. Task 4 mounts it at `/home/filebrowser/data`.
  - ConfigMap `filebrowser-config` with a single key `config.yaml`. Task 4 mounts it at `/config`.
  - Secret key names `FILEBROWSER_OIDC_CLIENT_ID`, `FILEBROWSER_OIDC_CLIENT_SECRET`, `FILEBROWSER_JWT_TOKEN_SECRET` — created in Task 3, consumed in Task 4.
  - IngressRoute `filebrowser-public` on host `files.starktastic.net`.

- [ ] **Step 1: Create the chart metadata**

Create `services/operations/filebrowser/manifests/Chart.yaml`:

```yaml
apiVersion: v2
name: filebrowser-manifests
description: FileBrowser Quantum config, index PVC, OIDC secret and public share route
type: application
version: 0.0.0
```

- [ ] **Step 2: Create the index PVC**

Quantum runs a mandatory 10MB write/read speed test on `cacheDir` at startup and fatals if it cannot prepare the directory, which rules out the NFS volumes. `storageClassName` is stated explicitly because k3s recreates its `local-path` StorageClass on every restart, making it the newest default and the winner of the newest-wins tiebreak (ADR 0009).

Create `services/operations/filebrowser/manifests/templates/data-pvc.yaml`:

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: filebrowser-data-pvc
  namespace: operations
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: 20Gi
```

- [ ] **Step 3: Create the config ConfigMap**

Create `services/operations/filebrowser/manifests/templates/configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: filebrowser-config
  namespace: operations
data:
  config.yaml: |
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

- [ ] **Step 4: Create the public share-link route**

Every asset on a share page is served from `/public/static/`, and every unauthenticated API call from `/public/api/`, so this single prefix is sufficient. Nothing outside `/public/` is reachable on the public host. No Authentik middleware is attached — that is the entire point of this route — but `crowdsec-bouncer` and `rate-limit-strong` are, matching `microbin-public`.

Create `services/operations/filebrowser/manifests/templates/ingressroute-public.yaml`:

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: filebrowser-public
  namespace: operations
spec:
  entryPoints:
    - websecure
  routes:
    # Share links only. Everything under /public/ is unauthenticated by
    # design: the share page, its assets, and the hash-scoped API.
    - match: Host(`files.{{ .Values.global.domains.public }}`) && PathPrefix(`/public/`)
      kind: Rule
      services:
        - name: filebrowser
          port: 80
      middlewares:
        - name: crowdsec-bouncer
          namespace: traefik-system
        - name: rate-limit-strong
          namespace: traefik-system
  tls:
    store:
      name: default
      namespace: traefik-system
```

- [ ] **Step 5: Render the chart**

```bash
cd /home/ben/Developer/homelab/apps
helm template filebrowser-manifests services/operations/filebrowser/manifests \
  -f templates/globals.yaml
```

Expected: three documents. Confirm `externalUrl: "https://files.starktastic.net"`, the issuer URL `https://auth.starktastic.net/application/o/filebrowser/`, and the route match `Host(`files.starktastic.net`) && PathPrefix(`/public/`)`. No `{{` should remain anywhere in the output.

- [ ] **Step 6: Extract the rendered config and boot the real image against it**

This is the highest-value check in the change. CI's kubeconform step explicitly skips `*/manifests/templates/*` and yamllint ignores `**/templates/`, so nothing in the pipeline ever parses this file. Quantum rejects unknown fields outright.

```bash
cd /home/ben/Developer/homelab/apps
rm -rf /tmp/fbverify && mkdir -p /tmp/fbverify/{config,data,srv/apps,srv/media}
helm template filebrowser-manifests services/operations/filebrowser/manifests \
  -f templates/globals.yaml \
| python3 -c '
import sys, yaml
for doc in yaml.safe_load_all(sys.stdin):
    if doc and doc.get("kind") == "ConfigMap":
        open("/tmp/fbverify/config/config.yaml", "w").write(doc["data"]["config.yaml"])
        print("extracted config.yaml")
'
chmod -R 777 /tmp/fbverify
```

Expected: `extracted config.yaml`.

- [ ] **Step 7: Run the container and confirm a clean start**

The issuer is overridden to an Authentik application that already exists, because the `filebrowser` provider is not created until Task 3. Quantum performs OIDC discovery during startup validation, so pointing at a non-existent slug fatals — that is the behaviour being worked around here, and it is the same behaviour that makes Task 3 a hard prerequisite for rollout.

```bash
sed -i 's|application/o/filebrowser/|application/o/bytestash/|' /tmp/fbverify/config/config.yaml
timeout 60 docker run --rm --name fbq-verify \
  -e FILEBROWSER_CONFIG=/config/config.yaml \
  -e FILEBROWSER_OIDC_CLIENT_ID=verifyid \
  -e FILEBROWSER_OIDC_CLIENT_SECRET=verifysecret \
  -e FILEBROWSER_JWT_TOKEN_SECRET=verifyjwtsecretaaaaaaaaaaaaaaaaa \
  -v /tmp/fbverify/config:/config:ro \
  -v /tmp/fbverify/data:/home/filebrowser/data \
  -v /tmp/fbverify/srv/apps:/srv/apps \
  -v /tmp/fbverify/srv/media:/srv/media \
  gtstef/filebrowser:1.5.3-stable 2>&1 | head -20
```

Expected, with no `[FATAL]` line anywhere:

```
[INFO ] Using Config file        : /config/config.yaml
[INFO ] Auth Methods             : [oidc]
[INFO ] Sources                  : [apps: /srv/apps media: /srv/media]
[INFO ] OIDC Auth configured successfully
[INFO ] Running at               : http://0.0.0.0/
```

If a `[FATAL] Error reading config` or an unknown-field error appears, a key in Step 3 is wrong — fix it and re-run from Step 6.

- [ ] **Step 8: Clean up the scratch directory**

```bash
rm -rf /tmp/fbverify
```

- [ ] **Step 9: Commit**

```bash
cd /home/ben/Developer/homelab/apps
git add services/operations/filebrowser/manifests
git commit -F - <<'EOF'
feat(filebrowser): quantum config, index PVC and public share route

Adds the sibling manifests chart Quantum needs beyond app-template:

- 20Gi local-path PVC for the BoltDB, SQLite index and thumbnail cache.
  Quantum speed-tests cacheDir at startup and fatals if it cannot
  prepare it, so this cannot live on the NFS volumes.
- config.yaml as a ConfigMap: both sources, OIDC-only auth restricted
  to the Authentik admin group, and trustedHeaders so Traefik's
  forwarded scheme and host reach the OIDC redirect_uri.
- A public IngressRoute scoped to PathPrefix(/public/), which is the
  only unauthenticated surface Quantum exposes.

Verified by booting gtstef/filebrowser:1.5.3-stable against the
rendered config; nothing in CI parses this file.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: ad604922-e50f-4d41-8da9-5238ab3ccff3
EOF
```

---

### Task 3: OIDC SealedSecret

Quantum reads the client ID, client secret and JWT signing secret from the environment. `loadEnvConfig()` runs at the end of `loadConfigWithDefaults()` and before `ValidateConfig()`, so these satisfy validation without any placeholder in the ConfigMap.

**This task needs @MrStarktastic.** It depends on an Authentik provider that only he can create, and on secrets that must never be committed in plaintext. Stop and ask rather than guessing values.

**Files:**
- Create: `services/operations/filebrowser/manifests/templates/filebrowser-secret.yaml`

**Interfaces:**
- Consumes: the chart created in Task 2.
- Produces: Secret `filebrowser-secret` in namespace `operations`, with keys `FILEBROWSER_OIDC_CLIENT_ID`, `FILEBROWSER_OIDC_CLIENT_SECRET` and `FILEBROWSER_JWT_TOKEN_SECRET`. Task 4 consumes it via `envFrom`.

- [ ] **Step 1: Ask @MrStarktastic to create the Authentik provider**

Present exactly this, and wait for the client ID and client secret:

> Create an Authentik **OAuth2/OpenID Provider** plus its Application:
>
> - Application slug: `filebrowser` (the issuer URL depends on this exact string)
> - Redirect URI: `https://files.internal.starktastic.net/api/auth/oidc/callback`
> - Scopes: `openid`, `email`, `profile`
> - The `groups` claim must be present in the token — Quantum reads `groups` to match `adminGroup: "authentik Admins"`, and denies login outright to anyone outside it.
>
> This must exist before the Deployment rolls out. Quantum fetches OIDC discovery during startup validation, so the pod crashloops without it.
>
> Then send me the client ID and client secret.

- [ ] **Step 2: Generate the JWT signing secret**

Pinning it keeps sessions valid across pod restarts.

```bash
openssl rand -hex 32
```

Expected: 64 hex characters. Keep it for the next step.

- [ ] **Step 3: Seal the three values**

`scripts/seal.sh` reads `KEY=VALUE` pairs from stdin, ends on Ctrl+D, and writes `filebrowser-secret.yaml` into the current directory.

```bash
cd /home/ben/Developer/homelab/apps
./scripts/seal.sh filebrowser-secret operations
```

At the prompt, enter one per line, substituting the real values:

```
FILEBROWSER_OIDC_CLIENT_ID=<client id from Step 1>
FILEBROWSER_OIDC_CLIENT_SECRET=<client secret from Step 1>
FILEBROWSER_JWT_TOKEN_SECRET=<hex string from Step 2>
```

- [ ] **Step 4: Move it into the chart**

kubeseal 0.33.1 already emits both the leading `---` and the `spec.template` block, matching `bytestash-secret.yaml` and `karakeep-secret.yaml`. Confirm rather than append — an appended duplicate `template:` key would make the file invalid.

```bash
cd /home/ben/Developer/homelab/apps
mv filebrowser-secret.yaml services/operations/filebrowser/manifests/templates/
tail -5 services/operations/filebrowser/manifests/templates/filebrowser-secret.yaml
```

Expected:

```yaml
  template:
    metadata:
      name: filebrowser-secret
      namespace: operations
```

If that block is absent (older kubeseal), append exactly it, keeping `encryptedData` untouched.

- [ ] **Step 5: Verify no plaintext leaked**

```bash
cd /home/ben/Developer/homelab/apps
grep -c encryptedData services/operations/filebrowser/manifests/templates/filebrowser-secret.yaml
helm template filebrowser-manifests services/operations/filebrowser/manifests \
  -f templates/globals.yaml | grep -A6 'kind: SealedSecret'
```

Expected: `1`, then a SealedSecret whose three values are long opaque base64 strings. If any real client secret is readable, stop — do not commit.

- [ ] **Step 6: Commit**

```bash
cd /home/ben/Developer/homelab/apps
git add services/operations/filebrowser/manifests/templates/filebrowser-secret.yaml
git commit -F - <<'EOF'
feat(filebrowser): sealed OIDC credentials for quantum

Client ID, client secret and a pinned JWT signing secret, injected as
environment variables. Quantum applies env overrides before config
validation, so no placeholders are needed in the ConfigMap.

Pinning the JWT secret keeps sessions valid across pod restarts.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: ad604922-e50f-4d41-8da9-5238ab3ccff3
EOF
```

---

### Task 4: Cut the Deployment over to Quantum

Swaps the image and wiring. Also removes the Homepage widget, which breaks the moment Quantum deploys, and pins Renovate to the stable channel, which matters as soon as the new image exists — both belong to this deliverable.

**Files:**
- Modify: `services/operations/filebrowser/values.yaml` (full rewrite)
- Modify: `services/operations/filebrowser/app.yaml`
- Modify: `services/operations/homepage-admin/manifests/templates/configmap.yaml:789-791`
- Modify: `renovate.json`

**Interfaces:**
- Consumes: `ingress.probePath` (Task 1), `filebrowser-data-pvc` and `filebrowser-config` (Task 2), `filebrowser-secret` (Task 3).
- Produces: the running Deployment. Nothing later depends on it.

- [ ] **Step 1: Rewrite the Deployment values**

Four changes carry the design. The `init-db-dir` initContainer goes away because the database no longer lives on NFS. `FILEBROWSER_CONFIG` points at the ConfigMap mount rather than letting Quantum look inside the data volume, which the ConfigMap would otherwise have to mask. `media.enabled: true` is mandatory — `templates/common.yaml` ships that key disabled, and omitting it silently drops the `/srv/media` mount while everything still renders. Reloader restarts the pod on config change, since Quantum reads its config only at startup.

Replace the entire contents of `services/operations/filebrowser/values.yaml` with:

```yaml
controllers:
  main:
    annotations:
      reloader.stakater.com/auto: "true"
    containers:
      main:
        image:
          repository: gtstef/filebrowser
          tag: 1.5.3-stable@sha256:e2ac55ccbe53d63b3f1d7d5ea5b82edf589b005a4b747b59912f97c6ba4f969e
        securityContext:
          runAsUser: 1000
          runAsGroup: 1000
        env:
          FILEBROWSER_CONFIG: /config/config.yaml
        envFrom:
          - secretRef:
              name: filebrowser-secret
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 1Gi
        probes:
          liveness:
            enabled: true
            type: HTTP
            port: 80
            path: /api/health
          readiness:
            enabled: true
            type: HTTP
            port: 80
            path: /api/health
          startup:
            enabled: true
            type: TCP
            port: 80
            spec:
              failureThreshold: 30
              periodSeconds: 5

service:
  main:
    controller: main
    ports:
      http:
        port: 80

persistence:
  config:
    enabled: false
  fbconfig:
    type: configMap
    name: filebrowser-config
    globalMounts:
      - path: /config
        readOnly: true
  data:
    existingClaim: filebrowser-data-pvc
    globalMounts:
      - path: /home/filebrowser/data
  apps:
    existingClaim: filebrowser-apps-pvc
    globalMounts:
      - path: /srv/apps
  media:
    enabled: true
    existingClaim: filebrowser-media-pvc
    globalMounts:
      - path: /srv/media
```

- [ ] **Step 2: Update the app definition**

`auth` flips to `false` because Quantum handles OIDC itself, matching karakeep, mealie, vikunja and paperless-ngx. That also switches the blackbox module from `http_auth` to `http_2xx`, which follows redirects — hence `probePath`, so the probe reads a real 200 from `/api/health` rather than an Authentik redirect chain.

Replace the entire contents of `services/operations/filebrowser/app.yaml` with:

```yaml
name: filebrowser
namespace: operations
deployPhase: services
manifests: true
helmManifests: true
ingress:
  enabled: true
  host: files
  domainType: "internal"
  port: 80
  auth: false
  rateLimit: true
  probe: true
  probePath: /api/health
```

- [ ] **Step 3: Render the Deployment and check every mount**

```bash
cd /home/ben/Developer/homelab/apps
rm -rf /tmp/at5
helm pull oci://ghcr.io/bjw-s-labs/helm/app-template --version 5.1.0 \
  --untar --untardir /tmp/at5
helm template filebrowser /tmp/at5/app-template \
  -f templates/globals.yaml -f templates/common.yaml \
  -f services/operations/filebrowser/values.yaml \
| grep -A10 'volumeMounts:'
```

Expected: exactly four mounts — `/srv/apps`, `/home/filebrowser/data`, `/config`, `/srv/media`. If `/srv/media` is missing, `media.enabled: true` was dropped in Step 1.

- [ ] **Step 4: Render the probe and confirm the target and module**

```bash
cd /home/ben/Developer/homelab/apps
helm template ing templates/ingress-chart \
  -f templates/globals.yaml -f services/operations/filebrowser/app.yaml \
  --show-only templates/probe.yaml | grep -E 'module|https://'
```

Expected:

```
  module: http_2xx
        - https://files.internal.starktastic.net/api/health
```

- [ ] **Step 5: Remove the Homepage widget**

gethomepage's `filebrowser` widget POSTs to `{url}/api/login` and GETs `{url}/api/usage`. Quantum authenticates at `/api/auth/login` and has no usage endpoint, so the widget can only ever error. `href` and `siteMonitor` stay, so dashboard coverage is unaffected.

In `services/operations/homepage-admin/manifests/templates/configmap.yaml`, delete these three lines (789-791):

```yaml
            widget:
              type: filebrowser
              url: http://filebrowser.operations:80
```

The entry must end up as:

```yaml
        - Filebrowser:
            icon: filebrowser.png
            href: https://files.internal.starktastic.net
            description: Web file manager
            siteMonitor: http://filebrowser.operations:80
            namespace: operations
            app: filebrowser
```

- [ ] **Step 6: Pin Renovate to the stable channel**

`1.5.3-stable` and `1.5.3-beta` both exist as tags, and nothing else stops Renovate crossing channels.

Add this object to the `packageRules` array in `renovate.json`, after the qBittorrent rule:

```json
    {
      "description": "Track only FileBrowser Quantum's stable channel; the registry also publishes -beta tags for the same version",
      "matchDatasources": ["docker"],
      "matchPackageNames": ["gtstef/filebrowser"],
      "allowedVersions": "/-stable$/"
    },
```

- [ ] **Step 7: Verify the JSON still parses**

```bash
cd /home/ben/Developer/homelab/apps
python3 -m json.tool renovate.json > /dev/null && echo "VALID JSON"
```

Expected: `VALID JSON`.

- [ ] **Step 8: Verify Homepage coverage still passes**

```bash
cd /home/ben/Developer/homelab/apps
python3 scripts/check-homepage-coverage.py
```

Expected: the same success output as on `main`. The public host `files.starktastic.net` is templated, and the checker skips any `Host()` containing `{{`, so it is not expected to demand a dashboard entry for it.

- [ ] **Step 9: Commit**

```bash
cd /home/ben/Developer/homelab/apps
git add services/operations/filebrowser/values.yaml \
        services/operations/filebrowser/app.yaml \
        services/operations/homepage-admin/manifests/templates/configmap.yaml \
        renovate.json
git commit -F - <<'EOF'
feat(filebrowser): cut over to filebrowser quantum

Replaces filebrowser/filebrowser, which ran with FB_NOAUTH=true behind
an Authentik forward-auth middleware, with Quantum authenticating
natively against Authentik.

- Auth moves into the app, so the ingress middleware is dropped and the
  blackbox probe targets /api/health via the new probePath.
- Index and database move off NFS onto the local-path PVC, retiring the
  init-db-dir initContainer that existed to chown the NFS directory.
- The Homepage widget is removed rather than adapted: it calls
  /api/login and /api/usage, neither of which Quantum implements.
- Renovate is pinned to the -stable channel.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: ad604922-e50f-4d41-8da9-5238ab3ccff3
EOF
```

---

### Task 5: Repository-wide validation and pull request

Runs the same gates CI runs, then hands the change to @MrStarktastic.

**Files:** none modified.

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: a pull request.

- [ ] **Step 1: Lint the YAML CI actually lints**

```bash
cd /home/ben/Developer/homelab/apps
yamllint --config-file .github/yamllint.yaml \
  services/operations/filebrowser/app.yaml \
  services/operations/filebrowser/values.yaml
```

Expected: no output. Note that `.github/yamllint.yaml` ignores `**/templates/`, so the manifests chart is deliberately not covered here — Task 2's boot test is its gate.

- [ ] **Step 2: Confirm no `cluster.local` FQDN was introduced**

Use CI's exact expression rather than a bare `cluster.local` grep. CI matches `svc.cluster.local` and excludes `docs`, so a loose grep produces false positives from the spec and plan, which quote the rule.

```bash
cd /home/ben/Developer/homelab/apps
hits=$(git grep -n 'svc\.cluster\.local' -- . ':!docs' ':!.github' \
  | grep -v 'crowdsecLapiHost\|https://argocd-server' || true)
if [ -n "$hits" ]; then echo "$hits"; echo "WOULD FAIL"; else echo "CLEAN"; fi
```

Expected: `CLEAN`.

- [ ] **Step 3: Confirm the old image is fully gone**

```bash
cd /home/ben/Developer/homelab/apps
grep -rn 'filebrowser/filebrowser\|FB_NOAUTH\|FB_ROOT\|FB_DATABASE' \
  services/ infrastructure/ templates/ || echo "NO STALE REFERENCES"
```

Expected: `NO STALE REFERENCES`.

- [ ] **Step 4: Confirm the public hostname resolves**

The spec lists this as a manual prerequisite. Existing public hosts such as `mealie` and `karakeep` imply a wildcard record, but it was never verified — and if it does not resolve, share links silently fail while everything else looks healthy.

```bash
dig +short files.starktastic.net
```

Expected: the external load balancer address, matching what an existing public host returns:

```bash
dig +short mealie.starktastic.net
```

If `files` returns nothing while `mealie` resolves, there is no wildcard record. Flag it to @MrStarktastic in the PR — the internal UI still works, only sharing is affected.

- [ ] **Step 5: Review the full diff**

```bash
cd /home/ben/Developer/homelab/apps
git --no-pager diff main...HEAD --stat
```

Expected, ignoring the two spec commits: `templates/ingress-chart/values.yaml`, `templates/ingress-chart/templates/probe.yaml`, four new files under `services/operations/filebrowser/manifests/`, plus one new SealedSecret, `services/operations/filebrowser/{app,values}.yaml`, `services/operations/homepage-admin/manifests/templates/configmap.yaml`, `renovate.json`, and the plan and spec documents.

- [ ] **Step 6: Push and open the pull request**

```bash
cd /home/ben/Developer/homelab/apps
git push -u origin feat/filebrowser-quantum
gh pr create --title "feat(filebrowser): replace with FileBrowser Quantum" --body "$(cat <<'EOF'
Replaces `filebrowser/filebrowser` with FileBrowser Quantum, authenticating natively against Authentik.

The old deployment ran with `FB_NOAUTH=true` and relied entirely on an Authentik forward-auth middleware at the edge, which meant no per-user identity, no sharing, and no permissions. Quantum authenticates against Authentik itself.

### Changes

- **Auth** moves into the app. The ingress middleware is dropped (`auth: false`), matching karakeep, mealie and vikunja. Login is restricted to `authentik Admins`, who land as admins.
- **Storage** splits. The BoltDB, SQLite index and thumbnail cache move to a 20Gi `local-path` PVC; Quantum speed-tests `cacheDir` at startup and fatals on failure, so this cannot stay on NFS. The `/srv/apps` and `/srv/media` NFS mounts are unchanged, and the `init-db-dir` initContainer that chowned the NFS database directory is retired.
- **Sharing** gets a public route on `files.starktastic.net` scoped to `PathPrefix(/public/)` — the only unauthenticated surface Quantum exposes. The UI stays internal-only.
- **Probing** gains `ingress.probePath` in the shared chart, so the blackbox probe reads `/api/health` instead of an Authentik redirect. Defaults to empty; every existing probe target is byte-identical.
- **Homepage widget removed.** It calls `/api/login` and `/api/usage`; Quantum implements neither. `href` and `siteMonitor` remain, so coverage is unaffected.
- **Renovate** pinned to `-stable`, since the registry also publishes `-beta` tags for the same version.

### Verification

`gtstef/filebrowser:1.5.3-stable` was booted against the rendered `config.yaml` — this is the only validation the file gets, as CI's kubeconform step skips `*/manifests/templates/*`:

```
[INFO ] Using Config file        : /config/config.yaml
[INFO ] Auth Methods             : [oidc]
[INFO ] Sources                  : [apps: /srv/apps media: /srv/media]
[INFO ] OIDC Auth configured successfully
[INFO ] Running at               : http://0.0.0.0/
```

Also confirmed against the running container: `/api/health` returns 200 unauthenticated, and every asset on a share page resolves under `/public/static/`, so the public route needs no `/static/` exception.

### Before merging

The Authentik provider (slug `filebrowser`, redirect URI `https://files.internal.starktastic.net/api/auth/oidc/callback`) must exist. Quantum performs OIDC discovery during startup validation, so the pod crashloops without it.

### After deploying

Existing share links do not carry over — the old deployment had none. The first index build walks both sources and will take a while.

Rollback is a plain `git revert`. There is no data migration: Quantum is a hard fork with an incompatible database, and `/srv/apps/filebrowser/filebrowser.db` is left untouched on NFS, so the old deployment finds its database exactly where it left it. The only orphan is the `local-path` PVC.

Spec: `docs/superpowers/specs/2026-08-24-filebrowser-quantum-design.md`
Plan: `docs/superpowers/plans/2026-08-24-filebrowser-quantum.md`
EOF
)"
```

- [ ] **Step 7: Stop**

Do not merge, and do not touch the cluster. @MrStarktastic reviews and merges.
