# Homepage v2 upgrade and ArgoCD widget durability

Date: 2026-08-16
Status: Approved, not yet implemented

## Problem

Two things arrived together, and both land in the same two files.

### The ArgoCD widget is broken

The admin dashboard's "Deployments" tile renders an error instead of sync and
health counts:

```
API Error: HTTP Error
URL: https://argocd-server.argocd.svc.cluster.local/api/v1/applications
Response Data: {"error":"invalid session: token signature is invalid:
signature is invalid","code":16,...}
```

This is not a misconfiguration. It was diagnosed against the live cluster:

- The sealed token in `homepage-admin/manifests/templates/secrets.yaml` is a
  JWT with `sub: homepage:apiKey`, issued 2026-06-14 (commit `da9f436`), with
  no `exp` claim.
- Recomputing its HMAC-SHA256 signature against the live
  `secret/argocd-secret` key `server.secretkey` does **not** match.
- `argocd-secret` is owned by the ArgoCD Helm chart and was recreated on
  2026-08-12, when the cluster was reprovisioned. The chart generated a fresh
  random `server.secretkey`, which invalidates every token it previously
  signed.
- `argocd-secret` also no longer carries an `accounts.homepage.tokens` key. In
  ArgoCD v3.5.1 a local-account token is only accepted if its `jti` appears in
  that list, so the token has failed twice over.

The account plumbing itself is fine: `argocd-cm` declares
`accounts.homepage: apiKey`, and `argocd-rbac-cm` grants
`role:homepage → applications, get, */*`.

So the defect is not the token's contents. It is that a **static credential
committed to Git is bound to a signing key the ArgoCD chart regenerates on
every install.** The cluster is reprovisioned regularly, so re-issuing the
token fixes the dashboard until the next rebuild and no further.

### Homepage v2.0.0 is available

Renovate PR #1059 bumps `ghcr.io/gethomepage/homepage` from
`v1.13.2` to `v2.0.0`. It edits only
`services/operations/homepage-admin/values.yaml`, but
`services/operations/homepage/app.yaml` declares
`baseApp: services/operations/homepage-admin`, so the single bump upgrades
**both** dashboards. A major version deserves a check of what breaks and what
is newly worth using.

## Goals

1. Make the ArgoCD tile survive cluster reprovisioning without manual
   credential rotation, while keeping the status-count breakdown.
2. Upgrade both dashboards to Homepage v2.0.0 with the breaking changes
   understood rather than discovered in production.
3. Adopt v2 features that earn their place, and explicitly decline the ones
   that do not.

## Non-goals

- Enabling Homepage's new built-in authentication. Authentik ForwardAuth
  already gates both instances.
- Cleaning up the ArgoCD-side `accounts.homepage` account and `role:homepage`
  policy. Those live in the Ansible bootstrap repository, outside this repo.
- Broader ArgoCD alerting. Exposing the metrics makes it possible; writing the
  rules is separate work.

## Approach

### Considered and rejected

**Pin ArgoCD's signing key in Git.** Seal `server.secretkey` and
`accounts.homepage.tokens` into `argocd-secret` so the committed token stays
valid across rebuilds. This keeps the built-in `argocd` widget untouched, but
`argocd-secret` is Helm-owned, so it needs either a cross-repo Ansible change
or a Sealed Secrets patch (`sealedsecrets.bitnami.com/patch: "true"`, available
since v0.23.0; the cluster runs 0.38.4). Both variants carry real hazards: a
Helm upgrade reverts the patched keys unless the Secret is pinned with
`helm.sh/resource-policy: keep`, ArgoCD self-heal fights the patch without an
`ignoreDifferences` entry, and the change would commit ArgoCD's **session**
signing key — which signs every user session, not just one read-only token —
to Git. Rejected: more moving parts and a much larger blast radius than the
problem warrants.

**Replace the widget with `customapi` against the Kubernetes API.** Homepage
would read `applications.argoproj.io` custom resources using the
ServiceAccount token it already mounts, needing no ArgoCD credential at all.
This fails on capability: `customapi` has no filtering or aggregation. It can
count every item in an array (`format: size`) or list them
(`display: dynamic-list`), but it cannot count items *where*
`status.sync.status == "Synced"`. The status breakdown is the point of the
tile, so this loses the feature.

**Re-issue the token and re-seal.** Five minutes of work that breaks again at
the next reprovision. Useful only as a stopgap.

### Chosen: delete the credential, read the counts from Prometheus

`argocd-application-controller-0` already listens on port **8082** and serves
`argocd_app_info`, labelled with `sync_status` and `health_status`. The
Helm chart simply never created a Service or ServiceMonitor for it, because
`controller.metrics.enabled` is false. Verified live on 2026-08-16: 77
applications, 75 `Synced`, 2 `OutOfSync`, 77 `Healthy`.

Exposing that metric and querying it with Homepage's `prometheusmetric` widget
reproduces the same breakdown with **no credential in the system at all**.
Nothing can expire, be revoked, or be invalidated by a regenerated signing key,
so the tile survives every rebuild by construction.

The approach reuses two patterns already present in the repository rather than
introducing anything new:

- `infrastructure/configs/templates/kube-vip/` already ships a metrics Service
  plus ServiceMonitor for a component installed outside this repository. The
  ArgoCD case is identical.
- The admin dashboard already runs three `prometheusmetric` widgets against
  the in-cluster Prometheus, with the same `or vector(0)` idiom and `format`
  block.

It also removes a `siteMonitor`-independent failure mode from the dashboard and
makes ArgoCD's metrics available for future alert rules, which
`BACKLOG.md` records as a known gap.

The cost is honest and small: one additional scrape target, and counts that
are up to 30 seconds stale rather than fetched live on render.

## Design

### 1. Expose the application controller's metrics

Two new files under `infrastructure/configs/templates/argocd/`, mirroring the
`kube-vip` pair.

`metrics-service.yaml` — a headless Service in the `argocd` namespace whose
`spec.selector` is `app.kubernetes.io/name: argocd-application-controller`
(the label the chart puts on the controller pod), exposing port 8082 under the
name `metrics`. The Service itself carries
`app.kubernetes.io/component: metrics` so the ServiceMonitor has something
distinct to select on.

The Service is named **`argocd-controller-metrics`**, deliberately *not* the
chart's canonical `argocd-application-controller-metrics`. If
`controller.metrics.enabled` is ever set upstream, the chart would create that
name and the Helm install would fail on a conflict. A distinct name makes the
two coexist harmlessly.

`servicemonitor.yaml` — a ServiceMonitor in the `argocd` namespace selecting
the Service above by label, scraping the `metrics` port at `/metrics`.

No discovery labels are required: the cluster's Prometheus has
`serviceMonitorSelector: {}` and `serviceMonitorNamespaceSelector: {}`, so it
selects every ServiceMonitor in every namespace.

### 2. Swap the widget

In `services/operations/homepage-admin/manifests/templates/configmap.yaml`,
the "Deployments" entry (around line 468) is the only `argocd` widget in
either dashboard; the public dashboard has none. Only its `widget:` block
changes — `icon`, `href`, `description`, `siteMonitor`, `namespace` and `app`
all stay as they are, so the tile keeps its link and its Kubernetes pod-status
dot.

```yaml
widget:
  type: prometheusmetric
  url: http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090
  refreshInterval: 30000
  metrics:
    - label: Apps
      query: 'count(argocd_app_info) or vector(0)'
    - label: Synced
      query: 'count(argocd_app_info{sync_status="Synced"}) or vector(0)'
    - label: OutOfSync
      query: 'count(argocd_app_info{sync_status="OutOfSync"}) or vector(0)'
    - label: Unhealthy
      query: 'count(argocd_app_info{health_status!~"Healthy|Progressing"}) or vector(0)'
```

Four metrics is the display cap for the block layout, and matches the three
existing `prometheusmetric` widgets.

The fourth query is deliberately broader than the built-in widget's `degraded`
field. Counting only `Degraded` would silently ignore applications in
`Missing` or `Unknown`, which are equally broken states. `Progressing` is
excluded because it is a normal transient condition during a sync.

The embedded YAML lives inside a Helm-escaped ConfigMap, but PromQL label
matchers use single braces, which Helm passes through untouched. No `{{ }}`
escaping is needed for this block.

### 3. Remove the dead credential

Delete `HOMEPAGE_VAR_ARGOCD_KEY` from
`services/operations/homepage-admin/manifests/templates/secrets.yaml`. After
step 2 nothing references it, and leaving an invalid sealed credential in Git
invites someone to "fix" it later.

### 4. Upgrade to v2.0.0

Merge Renovate PR #1059 unchanged. No accompanying edits are required.

Homepage v2.0.0's only breaking change is a built-in authentication gate,
which is **opt-in**: with `HOMEPAGE_AUTH_ENABLED` unset the application behaves
exactly as v1.13.2 did. Everything this deployment depends on is unchanged —
the Kubernetes ClusterRole rules, the `/app/config` and `/app/public/icons`
mount paths, `HOMEPAGE_ALLOWED_HOSTS`, `LOG_TARGETS`, `HOMEPAGE_VAR_*`
substitution, and the `namespace:`/`app:` annotations that drive pod status.
The `/api/healthcheck` endpoint is explicitly exempted from the new auth gate,
so all three probes remain valid. There is no upstream migration guide because
there is nothing else to migrate.

One upstream change touches this deployment cosmetically: the `*arr` widgets
now use the `status` field as the queue's primary detail. Four widgets set
`enableQueue: true`, so their queue rows should be eyeballed after deploy.

### 5. v2 features considered

Declined, with reasons:

- **Built-in authentication.** Authentik ForwardAuth already gates both hosts
  through `auth: true` in `app.yaml`. A second gate duplicates working
  infrastructure, and Homepage does not rate-limit its own credentials
  endpoint.
- **Pulse widget.** `widget.js` is absent from the published image at the exact
  digest this PR pins, so the widget renders empty with no error. Not used
  here regardless.
- **qBittorrent API-key authentication.** Both qBittorrent widgets currently
  pass no credentials at all, so there is nothing to migrate.
- **Homepage MCP.** No consumer for it.
- **New Maintainerr, Sportarr, Syncthing and Duplicati widgets.** None of those
  services are deployed.

Not a risk: the Authentik widget's v1 API fallback regressed in v2.0.0 and the
fix missed the release tag, but this cluster runs Authentik 2026.5.6, which
takes the v2 API path.

## Testing

`scripts/check-homepage-coverage.py` already renders both Homepage manifests
charts and walks the embedded `services.yaml`, which proves the nested YAML
still parses. That is precisely the failure mode a hand-edited widget block
introduces, so it is the check to run before merging — no new harness is
needed. CI's existing kubeconform validation and ArgoCD diff preview cover the
two new manifests.

After deploying, four observations confirm the change:

1. Prometheus resolves `count(argocd_app_info)` to a non-zero value, proving
   the Service and ServiceMonitor are wired and the target is being scraped.
   Baseline measured 2026-08-16: 77 apps, 75 Synced, 2 OutOfSync, 77 Healthy.
2. The admin dashboard's "Deployments" tile renders four numbers rather than an
   API error.
3. The four `enableQueue: true` `*arr` widgets still render queue rows.
4. Both dashboards load and Kubernetes pod-status dots still resolve,
   confirming the v2 image did not disturb the Kubernetes integration.

## Rollback

The two changes are independent and revert independently. The widget swap does
not depend on v2 and works unchanged on v1.13.2; the version bump is a single
`tag:` line. Reverting the ArgoCD change restores a tile that was already
broken, so the only true regression risk lies in the image bump.
