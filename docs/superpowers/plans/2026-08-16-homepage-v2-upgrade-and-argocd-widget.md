# Homepage v2 Upgrade and ArgoCD Widget Durability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the admin dashboard's ArgoCD tile survive cluster reprovisioning by replacing its expired API token with credential-free Prometheus queries, and upgrade both Homepage instances to v2.0.0.

**Architecture:** The ArgoCD application controller already serves `argocd_app_info` on port 8082, but the Helm chart never created a Service for it. Add a metrics Service plus ServiceMonitor from this repository (mirroring the existing `kube-vip` pair), then read the sync and health counts through Homepage's `prometheusmetric` widget instead of the ArgoCD REST API. The sealed API token is deleted, so there is no credential left to expire. The v2.0.0 image bump is an independent, config-free change.

**Tech Stack:** Kubernetes (k3s v1.36.3), ArgoCD v3.5.1 (chart argo-cd 10.3.3), Helm, kube-prometheus-stack, Prometheus Operator CRDs, Sealed Secrets 0.38.4, Homepage v2.0.0, Python 3 (validation script).

**Spec:** `docs/superpowers/specs/2026-08-16-homepage-v2-upgrade-and-argocd-widget-design.md`

## Global Constraints

- All work happens on a branch named `MrStarktastic/homepage-v2-argocd-widget`. Human PRs in this repository use the `MrStarktastic/<short-description>` branch convention; only Renovate uses `renovate/*`.
- Commit messages follow Conventional Commits with a scope, e.g. `fix(homepage-admin): ...`, `feat(argocd): ...`.
- Every commit must include these trailers:
  ```
  Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
  Copilot-Session: e8b02d74-20d1-4656-a372-ed4e3b09510f
  ```
- The cluster is GitOps-managed. Nothing is applied with `kubectl apply`. Changes reach the cluster only by merging to `main`, after which the `refresh` workflow syncs the affected ArgoCD applications.
- Do not touch the ArgoCD Helm release, `argocd-cm`, or `argocd-rbac-cm`. Those live in the Ansible bootstrap repository and are out of scope.
- The new manifests go under `infrastructure/configs/templates/`, which is excluded from yamllint (`**/templates/` in `.github/yamllint.yaml`), from prettier (`templates/` in `.prettierignore`), and from kubeconform (which only scans `*/manifests/*`). Their only automated gate is `helm template`, so render it explicitly.
- Do not add a `kubectl apply`, port-forward, or token-generation step anywhere. The whole point of this change is that no credential exists.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `infrastructure/configs/templates/argocd/metrics-service.yaml` | Create | Headless Service exposing the ArgoCD application controller's port 8082 so Prometheus has a scrape target. |
| `infrastructure/configs/templates/argocd/servicemonitor.yaml` | Create | ServiceMonitor telling Prometheus to scrape that Service. |
| `services/operations/homepage-admin/manifests/templates/configmap.yaml` | Modify (~L474-477) | Swap the "Deployments" tile's `argocd` widget for a `prometheusmetric` widget. |
| `services/operations/homepage-admin/manifests/templates/secrets.yaml` | Modify (L11) | Delete the now-unreferenced `HOMEPAGE_VAR_ARGOCD_KEY` sealed value. |
| `services/operations/homepage-admin/values.yaml` (L10) | Modify, via Renovate PR #1059 | Bump the Homepage image to v2.0.0 for both dashboards. |

The two new files are split rather than combined because they are different Kubernetes kinds serving different consumers (kubelet endpoints vs. Prometheus Operator), matching the existing `infrastructure/configs/templates/kube-vip/` pair exactly.

Note that `services/operations/homepage/` (the public dashboard) is **not** modified. It has no ArgoCD widget, and it inherits its image tag from `homepage-admin` through `baseApp: services/operations/homepage-admin` in its `app.yaml`.

---

## Task 1: Expose the ArgoCD application controller's metrics

**Files:**
- Create: `infrastructure/configs/templates/argocd/metrics-service.yaml`
- Create: `infrastructure/configs/templates/argocd/servicemonitor.yaml`
- Reference pattern: `infrastructure/configs/templates/kube-vip/service.yaml`, `infrastructure/configs/templates/kube-vip/servicemonitor.yaml`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: a Prometheus scrape target yielding the metric `argocd_app_info`, labelled `sync_status` (values `Synced`, `OutOfSync`) and `health_status` (values `Healthy`, `Progressing`, `Degraded`, `Missing`, `Unknown`, `Suspended`). Task 2's PromQL queries depend on this exact metric name and these exact label names.

- [ ] **Step 1: Create the working branch**

The spec commit is currently sitting on local `main`. Move it onto the feature branch so nothing lands on `main` outside a PR.

```bash
cd /home/ben/Developer/homelab/apps
git checkout -b MrStarktastic/homepage-v2-argocd-widget
git branch --show-current
```

Expected output: `MrStarktastic/homepage-v2-argocd-widget`

- [ ] **Step 2: Record the red baseline**

Prove the metric is absent before adding anything, so the green check in Task 3 means something.

```bash
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 &
sleep 6
curl -s --get --data-urlencode 'query=count(argocd_app_info) or vector(0)' \
  http://127.0.0.1:19090/api/v1/query
```

Expected output contains `"value":[<timestamp>,"0"]` — the `or vector(0)` fallback fires because nothing is scraping ArgoCD.

Then stop the port-forward:

```bash
pgrep -f 'port-forward svc/kube-prometheus-stack-prometheus'
kill <the PID printed above>
```

- [ ] **Step 3: Create the metrics Service**

Create `infrastructure/configs/templates/argocd/metrics-service.yaml` with exactly this content:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: argocd-controller-metrics
  namespace: argocd
  labels:
    app.kubernetes.io/name: argocd-application-controller
    app.kubernetes.io/component: metrics
spec:
  clusterIP: None
  selector:
    app.kubernetes.io/name: argocd-application-controller
  ports:
    - name: metrics
      protocol: TCP
      port: 8082
      targetPort: 8082
```

Three details that matter:

- The name is `argocd-controller-metrics`, **not** the chart's canonical `argocd-application-controller-metrics`. If anyone ever sets `controller.metrics.enabled: true` in the ArgoCD Helm values, the chart creates that canonical name and the install would fail on a conflict. A distinct name lets both coexist.
- `spec.selector` uses `app.kubernetes.io/name: argocd-application-controller`, which is the label the chart puts on the controller pod. Verified live on `argocd-application-controller-0`.
- No `argocd.argoproj.io/sync-wave` annotation. The other files in this directory use sync waves because ArgoCD's own config has ordering requirements; a metrics Service has none, and the `kube-vip` metrics pair carries no wave either.

- [ ] **Step 4: Create the ServiceMonitor**

Create `infrastructure/configs/templates/argocd/servicemonitor.yaml` with exactly this content:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: argocd-controller-metrics
  namespace: argocd
  labels:
    app.kubernetes.io/name: argocd-application-controller
    app.kubernetes.io/component: metrics
spec:
  endpoints:
    - port: metrics
      path: /metrics
  namespaceSelector:
    matchNames:
      - argocd
  selector:
    matchLabels:
      app.kubernetes.io/name: argocd-application-controller
      app.kubernetes.io/component: metrics
```

No discovery labels are needed. This cluster's Prometheus has `serviceMonitorSelector: {}` and `serviceMonitorNamespaceSelector: {}`, so it selects every ServiceMonitor in every namespace. Verify that assumption still holds if this is being applied much later:

```bash
kubectl -n monitoring get prometheus kube-prometheus-stack-prometheus \
  -o jsonpath='{.spec.serviceMonitorSelector}{"  "}{.spec.serviceMonitorNamespaceSelector}{"\n"}'
```

Expected output: `{}  {}`

- [ ] **Step 5: Verify the chart still renders and contains both objects**

This is the only automated gate these two files have.

```bash
cd /home/ben/Developer/homelab/apps
helm template configs infrastructure/configs -f templates/globals.yaml \
  | grep -E '^(kind|  name):' | grep -A1 -E 'Service$|ServiceMonitor'
```

Expected: the render succeeds (exit code 0) and the output includes `kind: Service` followed by `name: argocd-controller-metrics`, and `kind: ServiceMonitor` followed by `name: argocd-controller-metrics`.

If `helm template` exits non-zero, the YAML is malformed — fix it before continuing.

- [ ] **Step 6: Commit**

```bash
git add infrastructure/configs/templates/argocd/metrics-service.yaml \
        infrastructure/configs/templates/argocd/servicemonitor.yaml
git commit -F - <<'EOF'
feat(argocd): scrape application controller metrics

The controller already serves argocd_app_info on :8082, but the Helm
chart never creates a Service for it because controller.metrics.enabled
is false. Add a headless Service and ServiceMonitor so Prometheus can
reach it, mirroring the existing kube-vip metrics pair.

Named argocd-controller-metrics rather than the chart's canonical
argocd-application-controller-metrics so the two cannot collide if
controller.metrics.enabled is ever turned on upstream.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: e8b02d74-20d1-4656-a372-ed4e3b09510f
EOF
```

---

## Task 2: Replace the ArgoCD widget and delete its credential

**Files:**
- Modify: `services/operations/homepage-admin/manifests/templates/configmap.yaml:474-477`
- Modify: `services/operations/homepage-admin/manifests/templates/secrets.yaml:11`
- Test: `scripts/check-homepage-coverage.py`

**Interfaces:**
- Consumes: the `argocd_app_info` metric with `sync_status` and `health_status` labels, produced by Task 1.
- Produces: an admin dashboard tile with no credential dependency. Nothing later depends on its internals.

- [ ] **Step 1: Confirm the validation script passes before you change anything**

You need a known-good baseline, because this script is the gate for this task.

```bash
cd /home/ben/Developer/homelab/apps
python3 scripts/check-homepage-coverage.py
```

Expected output: `Homepage coverage OK: 48 hosts, both dashboards consistent`

If this fails before you have edited anything, stop and investigate — something else is broken.

- [ ] **Step 2: Swap the widget block**

In `services/operations/homepage-admin/manifests/templates/configmap.yaml`, find the `- Deployments:` entry (around line 467). Replace **only** these three lines:

```yaml
            widget:
              type: argocd
              url: https://argocd-server.argocd.svc.cluster.local:443
              key: {{ "{{" }}HOMEPAGE_VAR_ARGOCD_KEY{{ "}}" }}
```

with:

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

Leave the surrounding keys untouched. The entry must still read:

```yaml
        - Deployments:
            icon: argo-cd.png
            href: https://argocd.internal.starktastic.net
            description: Sync and health of every app
            siteMonitor: https://argocd-server.argocd.svc.cluster.local:443
            namespace: argocd
            app: argocd-server
            widget:
              ...
```

Keeping `siteMonitor`, `namespace` and `app` preserves the tile's uptime dot and its Kubernetes pod-status indicator, which never depended on the token.

Four things to be careful about:

- **Four metrics is the cap.** Homepage's block layout renders at most four. Do not add a fifth.
- **Do not escape the PromQL braces.** This file is a Helm template and escapes Homepage's own `{{ }}` syntax as `{{ "{{" }}...{{ "}}" }}`. PromQL label matchers use *single* braces, which Helm passes through untouched. Writing `{{ "{" }}` here would be wrong.
- **Keep the single quotes** around each `query:` value. The queries contain `:` and `"`, which break unquoted YAML.
- **`Unhealthy` is deliberately broader than the old widget's `Degraded` field.** Counting only `Degraded` would silently miss applications in `Missing` or `Unknown`. `Progressing` is excluded because it is a normal transient state during a sync.

- [ ] **Step 3: Delete the sealed credential**

In `services/operations/homepage-admin/manifests/templates/secrets.yaml`, delete the entire line 11, which begins:

```
    HOMEPAGE_VAR_ARGOCD_KEY: AgBRd9fyp/I4KcP3fdZx5MU+nUNN+aXlrIZk9IQg+tJSXQOlGDpMRrweA6stR/OrcAIRNTjcNMT4gmijmYh/wpLUNsW2F+9EkW8CtGhkHfxf...
```

It is a single very long line under `spec.encryptedData`. Delete the whole line, leaving the surrounding entries (`HOMEPAGE_VAR_ADGUARD_USER` above it, `HOMEPAGE_VAR_AUDIOBOOKSHELF_KEY` below it) intact.

Order matters: `check_secrets()` in the validation script fails when a `HOMEPAGE_VAR_*` is *referenced but not sealed*. Because Step 2 removed the only reference, removing the sealed value now is safe. Doing it in the opposite order would leave a failing intermediate state.

- [ ] **Step 4: Verify no reference to the credential survives**

```bash
cd /home/ben/Developer/homelab/apps
grep -rn 'HOMEPAGE_VAR_ARGOCD_KEY' --include='*.yaml' . ; echo "exit=$?"
```

Expected output: no matches, and `exit=1`.

- [ ] **Step 5: Run the validation script**

This renders both Homepage charts and walks the embedded `services.yaml`, which proves the YAML nested inside the Helm-escaped ConfigMap still parses — exactly the failure mode a hand-edited widget block introduces.

```bash
python3 scripts/check-homepage-coverage.py
```

Expected output: `Homepage coverage OK: 48 hosts, both dashboards consistent`

If it reports `secret not sealed (admin): HOMEPAGE_VAR_ARGOCD_KEY`, Step 2 did not remove the reference. If it fails to render, the YAML indentation in Step 2 is wrong — the `widget:` key sits at 12 spaces and its children at 14.

- [ ] **Step 6: Confirm the rendered widget looks right**

```bash
helm template homepage services/operations/homepage-admin/manifests \
  | grep -A20 'Deployments:'
```

Expected: the `Deployments:` block shows `type: prometheusmetric`, the Prometheus URL, and all four `query:` lines with their PromQL intact and unescaped.

- [ ] **Step 7: Commit**

```bash
git add services/operations/homepage-admin/manifests/templates/configmap.yaml \
        services/operations/homepage-admin/manifests/templates/secrets.yaml
git commit -F - <<'EOF'
fix(homepage-admin): read ArgoCD status from Prometheus, drop the token

The tile returned "invalid session: token signature is invalid" because
the sealed ArgoCD API token was signed with a server.secretkey that the
ArgoCD Helm chart regenerated when the cluster was reprovisioned. Since
rebuilds are routine, re-issuing the token only defers the failure.

Read the same sync and health counts from argocd_app_info through the
prometheusmetric widget instead, and delete the credential. Nothing is
left that can expire or be invalidated by a regenerated signing key.

Unhealthy counts everything except Healthy and Progressing, so Missing
and Unknown apps are visible — the old widget's degraded field missed
them.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
Copilot-Session: e8b02d74-20d1-4656-a372-ed4e3b09510f
EOF
```

---

## Task 3: Ship the ArgoCD fix and verify it in the cluster

**Files:** none modified. This task pushes Tasks 1-2 through CI into the cluster and closes the red/green loop opened in Task 1 Step 2.

**Interfaces:**
- Consumes: the committed work from Tasks 1 and 2.
- Produces: a live `argocd_app_info` scrape target and a working dashboard tile. Task 4 assumes the dashboard is otherwise healthy before the version bump, so that any breakage after the bump is attributable to v2.

- [ ] **Step 1: Push the branch and open the PR**

```bash
cd /home/ben/Developer/homelab/apps
git push -u origin MrStarktastic/homepage-v2-argocd-widget
gh pr create \
  --title 'fix(homepage-admin): read ArgoCD status from Prometheus instead of an API token' \
  --body 'The admin dashboard ArgoCD tile returned "invalid session: token signature is invalid". The sealed API token was signed with a `server.secretkey` that the ArgoCD Helm chart regenerated when the cluster was reprovisioned, and `argocd-secret` no longer carries the matching `accounts.homepage.tokens` entry either. Because rebuilds are routine, re-issuing the token only defers the failure.

This exposes the application controller metrics the chart never published (`:8082`, already being served) and reads the same counts from `argocd_app_info` through the `prometheusmetric` widget, then deletes the credential. Nothing is left that can expire.

Design: `docs/superpowers/specs/2026-08-16-homepage-v2-upgrade-and-argocd-widget-design.md`'
```

- [ ] **Step 2: Wait for CI and confirm it is green**

```bash
gh pr checks --watch
```

Expected: all checks pass. The `validate-and-diff` workflow runs yamllint, kubeconform, `scripts/check-homepage-coverage.py`, and posts an ArgoCD diff preview.

Read the diff preview comment on the PR. It should show exactly three things: the new Service, the new ServiceMonitor, and the changed `homepage-admin-config` ConfigMap plus `homepage-admin-secrets` SealedSecret. Anything else means an unintended change slipped in.

- [ ] **Step 3: Merge**

```bash
gh pr merge --squash --delete-branch
```

Merging to `main` triggers the `refresh` workflow, which syncs the affected ArgoCD applications.

- [ ] **Step 4: Confirm the sync landed**

Give ArgoCD a minute, then check that both new objects exist:

```bash
kubectl -n argocd get svc argocd-controller-metrics
kubectl -n argocd get servicemonitor argocd-controller-metrics
kubectl -n argocd get endpointslices -l kubernetes.io/service-name=argocd-controller-metrics \
  -o jsonpath='{range .items[*]}{.metadata.name}{" -> "}{range .endpoints[*].addresses[*]}{@}{" "}{end}{"\n"}{end}'
```

Expected: the Service exists with `CLUSTER-IP: None` and `PORT(S): 8082/TCP`, the ServiceMonitor exists, and the EndpointSlice lists one pod IP. An empty EndpointSlice means the Service selector does not match the controller pod — recheck the label in Task 1 Step 3.

- [ ] **Step 5: Green check — the metric is now in Prometheus**

This is the assertion that Task 1 Step 2 set up to fail.

```bash
kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 19090:9090 >/dev/null 2>&1 &
sleep 6
for q in 'count(argocd_app_info) or vector(0)' \
         'count(argocd_app_info{sync_status="Synced"}) or vector(0)' \
         'count(argocd_app_info{sync_status="OutOfSync"}) or vector(0)' \
         'count(argocd_app_info{health_status!~"Healthy|Progressing"}) or vector(0)'; do
  echo -n "$q => "
  curl -s --get --data-urlencode "query=$q" http://127.0.0.1:19090/api/v1/query \
    | grep -oP '"value":\[[0-9.]+,"\K[^"]+'
done
```

Expected: the first query returns a non-zero app count. The baseline measured on 2026-08-16 was 77 apps, 75 Synced, 2 OutOfSync, 0 Unhealthy. The exact numbers will differ; what matters is that the first query is no longer `0`.

Prometheus needs one scrape interval (30s by default) after the sync before the metric appears. If the first query still returns `0`, wait 60s and retry before assuming failure.

Stop the port-forward:

```bash
pgrep -f 'port-forward svc/kube-prometheus-stack-prometheus'
kill <the PID printed above>
```

- [ ] **Step 6: Confirm the tile renders**

Open `https://admin.starktastic.net` and find the "Deployments" tile under the Operations grouping.

Expected: four labelled numbers — Apps, Synced, OutOfSync, Unhealthy — matching the values from Step 5. No "API Error" text.

If the tile is blank, the Homepage pod cached the old ConfigMap. Stakater Reloader is deployed cluster-wide and should have restarted it; confirm with `kubectl -n operations get pods -l app.kubernetes.io/name=homepage-admin` and check the pod's age is newer than the merge.

---

## Task 4: Upgrade both dashboards to Homepage v2.0.0

**Files:**
- Modify: `services/operations/homepage-admin/values.yaml:10` — via Renovate PR #1059, not by hand.

**Interfaces:**
- Consumes: a verified-working dashboard from Task 3, so any post-bump breakage is attributable to v2.
- Produces: both Homepage instances running v2.0.0.

- [ ] **Step 1: Confirm the PR still contains only the tag bump**

```bash
cd /home/ben/Developer/homelab/apps
gh pr diff 1059
```

Expected: exactly one changed file, `services/operations/homepage-admin/values.yaml`, with one line changing from
`tag: v1.13.2@sha256:a0b71c8e757298d02560186bab9fbe3fc2d375c523a62cc1019177b37e48aa28`
to
`tag: v2.0.0@sha256:638dacf5c844e908dc06c1fd57a2b5694f8efd91f91f152829ea0c2f547458f2`

If Renovate has rebased to a newer v2.0.x, that is fine — verify against `gh release view <tag> --repo gethomepage/homepage` that the release notes still describe no additional breaking changes, then proceed.

**Do not add any accompanying edits.** v2.0.0's only breaking change is the built-in auth gate, which is opt-in via `HOMEPAGE_AUTH_ENABLED`; leaving it unset preserves v1.13.2 behaviour exactly. The ClusterRole rules, the `/app/config` and `/app/public/icons` mount paths, `HOMEPAGE_ALLOWED_HOSTS`, `LOG_TARGETS`, `HOMEPAGE_VAR_*` substitution and the `namespace:`/`app:` annotations are all unchanged, and `/api/healthcheck` is explicitly exempted from the new gate, so all three probes stay valid.

- [ ] **Step 2: Note that this bump upgrades both dashboards**

The PR touches only `homepage-admin`, but `services/operations/homepage/app.yaml` declares `baseApp: services/operations/homepage-admin`, so the public dashboard inherits the same image. Confirm:

```bash
grep -n 'baseApp' services/operations/homepage/app.yaml
```

Expected output: `baseApp: services/operations/homepage-admin`

Both instances must be checked in Step 5, not just the admin one.

- [ ] **Step 3: Merge the Renovate PR**

```bash
gh pr checks 1059 --watch
gh pr merge 1059 --squash --delete-branch
```

- [ ] **Step 4: Confirm both pods are running the new image**

```bash
kubectl -n operations get pods -l app.kubernetes.io/name=homepage-admin \
  -o jsonpath='{.items[*].spec.containers[0].image}{"\n"}'
kubectl -n operations get pods -l app.kubernetes.io/name=homepage \
  -o jsonpath='{.items[*].spec.containers[0].image}{"\n"}'
```

Expected: both print an image reference containing `v2.0.0`. Both pods should be `Running` with all containers ready:

```bash
kubectl -n operations get pods | grep homepage
```

If a pod is in `CrashLoopBackOff`, read `kubectl -n operations logs -l app.kubernetes.io/name=homepage-admin --tail=50` and go to the rollback step.

- [ ] **Step 5: Verify the four post-upgrade observations**

1. **The ArgoCD tile still works.** Load `https://admin.starktastic.net` and confirm the "Deployments" tile still shows four numbers. The `prometheusmetric` widget is unchanged in v2, so this should be unaffected — it is checked because it is the thing this whole plan exists to protect.
2. **The `*arr` queue rows still render.** Upstream #6859 changed the `*arr` widgets to use the `status` field as the queue's primary detail. Four widgets in the admin dashboard set `enableQueue: true` — find them with:
   ```bash
   grep -n -B12 'enableQueue: true' services/operations/homepage-admin/manifests/templates/configmap.yaml | grep -E '^\S+-\s+- '
   ```
   Expected output names the four tiles: `Radarr` (L814), `Radarr RU` (L838), `Sonarr` (L851), `Sonarr RU` (L864). Check each of those tiles on the dashboard shows queue entries rather than an empty or malformed list. This is cosmetic; note any difference rather than treating it as a blocker.
3. **Kubernetes pod-status dots still resolve.** Service tiles should show their coloured status indicator, confirming the Kubernetes integration and its unchanged RBAC still work.
4. **The public dashboard loads.** Open `https://starktastic.net` and confirm it renders with its tiles and widgets intact.

- [ ] **Step 6: Rollback path if any check fails**

The version bump is a single line and reverts independently of the ArgoCD work:

```bash
git checkout main && git pull
git revert <the squash-merge commit sha for PR 1059>
git push
```

The ArgoCD widget change does not depend on v2 and works unchanged on v1.13.2, so reverting the bump does not reintroduce the original bug.

---

## Notes for the implementer

**Known-good baselines measured on 2026-08-16**, useful for telling a real regression from an expected value:

- `scripts/check-homepage-coverage.py` → `Homepage coverage OK: 48 hosts, both dashboards consistent`
- `count(argocd_app_info)` before the change → `0`; after → 77
- ArgoCD applications: 77 total, 75 `Synced`, 2 `OutOfSync`, 77 `Healthy`

**Deliberately not done, so nobody re-adds it:**

- No new ArgoCD API token is generated, and no `argocd-secret` key is pinned. That was considered and rejected in the spec; it would commit ArgoCD's session-signing key to Git and fight both Helm and ArgoCD self-heal.
- The now-unused `accounts.homepage: apiKey` in `argocd-cm` and `g, homepage, role:homepage` in `argocd-rbac-cm` are left in place. They live in the Ansible bootstrap repository and are harmless — an account with no tokens grants nothing.
- Homepage's built-in auth is not enabled. Authentik ForwardAuth already gates both hosts via `auth: true`, and Homepage does not rate-limit its own credentials endpoint.
- The Pulse widget is not adopted; `widget.js` is missing from the published image at the digest this bump pins.
