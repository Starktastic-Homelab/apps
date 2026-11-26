# CSI node shutdown (F14, F15) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An undrained worker shutdown unstages its retained volumes and releases their VolumeAttachments before the
democratic-csi node plugin dies, so no fence is needed; a drained shutdown is no slower than today.

**Architecture:** Argo CD builds democratic-csi's `manifests/` with kustomize, which inflates the upstream chart and
JSON6902-patches the node DaemonSet: `csi-driver` gets a bounded wait-for-unstage preStop that also does the chart's
socket cleanup, `cleanup`'s preStop becomes a no-op, and `csi-proxy` and `driver-registrar` become native sidecars.
ansible enables kustomize Helm inflation in Argo CD and raises kubelet's shutdown grace.

**Amended after the final review (2026-11-18):** `cleanup` is removed, not given a no-op preStop (its shell ignores
SIGTERM, so it held every pod stop to the full grace), and `csi-driver`'s preStop does no socket `rm` (the preStop
also runs on a liveness restart; registrar v2.9.0 clears and removes its own socket). The node pod has 1 container
plus 2 sidecar init containers. Task 1 text below is the original; the ledger has the fix.

**Tech Stack:** kustomize (`kubectl kustomize --enable-helm`), Helm chart democratic-csi 0.15.1, Argo CD
ApplicationSet, ansible, Python unittest.

**Spec:** `docs/superpowers/specs/2026-11-18-csi-node-shutdown-design.md` (apps-adr-0017 worktree; approved by Ben
2026-11-18).

## Global Constraints

- Worktrees: apps `~/.cache/claude-homelab-live/worktrees/apps-storage-vm` (branch `feat/retained-storage-vm`, HEAD
  785cd5bf, clean) and ansible `.../ansible-storage-vm` (same branch, uncommitted). Commit nothing; Ben commits.
- Chart: `democratic-csi` from `https://democratic-csi.github.io/charts/`, version `0.15.1`, release name
  `democratic-csi`, namespace `democratic-csi`. Driver name `org.democratic-csi.node-manual`.
- Hold values: wait at most 20 s for no `plugins/kubernetes.io/csi/org.democratic-csi.node-manual/*/globalmount`
  in `/proc/mounts`; sleep 12 s only if one was seen; pod `terminationGracePeriodSeconds: 45`; kubelet
  `shutdownGracePeriod: 90s`, `shutdownGracePeriodCriticalPods: 40s`.
- Never force-detach, drop RWOP or `Retain`, touch an image or MMP. Every wait is bounded.
- Lab: every mutation needs Ben's OK at run time; QGA commands ASCII-only; never print tokens; live ops from the
  runner via the existing helpers (`memsize/env.sh`).
- No ansible merge while the lab holds the production lock.

## Review Focus

1. A chart bump that renames or reorders a node container: the JSON6902 move must fail the test, never ship a pod
   with a duplicated or missing container (Task 1 test `test_patch_targets_exist_upstream`).
2. A node with nothing staged: the csi-driver preStop must exit within a second, not sleep 12 s (Task 1 test
   `test_prestop_wait_is_conditional`, by running the hook script against a fake `/proc/mounts`).
3. The appset guard: every other infrastructure app must render exactly as before (Task 1 Step 6, and the diff
   preview on the PR).
4. A shutdown while the NFS backing stalls (F11): the 20 s cap must hold, so kubelet's 40 s critical tier still ends
   (Task 1 hook script test with a wait that never clears: exits in about 20 s).
5. Sidecar order during kubelet's node shutdown, not only a pod delete (Task 3 Leg A container exit order).

---

### Task 1: apps — democratic-csi through kustomize with the shutdown patch

**Files:**
- Modify: `bootstrap/appsets/cluster-apps.yaml:161-173` (infrastructure chart source)
- Modify: `infrastructure/system/democratic-csi/app.yaml` (drop `chart:`)
- Move: `infrastructure/system/democratic-csi/values.yaml` → `infrastructure/system/democratic-csi/manifests/values.yaml`
- Create: `infrastructure/system/democratic-csi/manifests/kustomization.yaml`
- Create: `infrastructure/system/democratic-csi/manifests/node-shutdown-patch.yaml`
- Modify: `.github/workflows/validate-and-diff.yml` (kubeconform exclusions; diff-preview Argo values)
- Create: `.github/argocd-diff-preview-values.yaml`
- Test: `scripts/storage/tests/test_democratic_csi_values.py`

**Interfaces:**
- Produces: `render()` in the test returns the kustomize-rendered docs (chart + patch + resources). Task 3 uses the
  same command to render the lab DaemonSet: `kubectl kustomize --enable-helm infrastructure/system/democratic-csi/manifests`.
- Produces: `node-shutdown-patch.yaml` holds the structural changes (sidecars, cleanup hook, grace);
  `values.yaml` `node.driver.lifecycle.preStop` carries the csi-driver hook (upstream key, chart node.yaml:96-98).
  Plan-level call: the spec put the csi-driver hook in the patch; the chart's own key is sturdier across bumps.

- [ ] **Step 1: Write the failing tests** in `test_democratic_csi_values.py`.
  - `render()`: read the chart ref from `manifests/kustomization.yaml` (`helmCharts[0]`); copy `manifests/` to a temp
    dir; if `DEMOCRATIC_CSI_CHART` is set, copy the unpacked chart to `<tmp>/charts/democratic-csi` so kustomize does
    not pull; run `kubectl kustomize --enable-helm <tmp>` (fall back to `kustomize build --enable-helm` if `kubectl`
    is absent).
  - Keep every existing test unchanged; they must pass on the new render.
  - `test_chart_ref`: `helmCharts[0]` has `name: democratic-csi`, `version: 0.15.1`,
    `repo: https://democratic-csi.github.io/charts/`, `releaseName: democratic-csi`, `namespace: democratic-csi`,
    `valuesFile: values.yaml`; `app.yaml` has no `chart` key.
  - `test_sidecars`: node DaemonSet `containers` names == `['csi-driver', 'cleanup']`; `initContainers` contains
    `csi-proxy` and `driver-registrar`, each with `restartPolicy: Always`; each keeps its upstream image.
  - `test_prestops`: `csi-driver` preStop command contains `org.democratic-csi.node-manual`, `globalmount`, `20`,
    `12` and the chart's `rm -rf /plugins/org.democratic-csi.node-manual /registration/org.democratic-csi.node-manual-reg.sock`;
    `cleanup`'s preStop does not contain `rm`; pod `terminationGracePeriodSeconds == 45`.
  - `test_patch_targets_exist_upstream`: render the chart alone (helm template, same values) and assert the node
    DaemonSet's containers are exactly `['csi-driver', 'csi-proxy', 'driver-registrar', 'cleanup']` in that order —
    the indexes the JSON6902 patch moves.
  - `test_prestop_wait_is_conditional`: extract the csi-driver hook script; run it with `sh` against a temp file in
    place of `/proc/mounts` (the script reads `${PROC_MOUNTS:-/proc/mounts}`) and with `rm` stubbed on `PATH`:
    empty file → exits in under 2 s; a file with a matching globalmount line that a background job removes after
    3 s → exits in 15-17 s (3 s wait + 12 s); a line that never clears → exits in 32-34 s (20 s cap + 12 s).
- [ ] **Step 2: Run** `python3 -m unittest scripts/storage/tests/test_democratic_csi_values.py -v` (offline:
  `DEMOCRATIC_CSI_CHART=<scratchpad>/dcsi/democratic-csi`, with kubectl or kustomize and helm on PATH; the workstation
  uses the docker helm wrapper per memory `workstation-offline-checks`). Expected: FAIL (no kustomization.yaml).
- [ ] **Step 3: Implement.**
  - `kustomization.yaml`: `helmCharts` per `test_chart_ref` (`includeCRDs: true`); `resources: [namespace.yaml,
    storage-fencer.yaml]`; `patches: [{path: node-shutdown-patch.yaml, target: {kind: DaemonSet, name:
    democratic-csi-node}}]` (use the rendered DaemonSet name).
  - `node-shutdown-patch.yaml` (JSON6902): set `terminationGracePeriodSeconds: 45`; add `initContainers: []` if
    absent; move container index 2 (`driver-registrar`) then index 1 (`csi-proxy`) to `/initContainers/-`, adding
    `restartPolicy: Always` to each; replace `cleanup`'s `lifecycle.preStop` with `exec: [sh, -c, "true"]`.
  - `values.yaml` (moved, otherwise unchanged): add `node.driver.lifecycle.preStop.exec.command: [sh, -c, <script>]`
    (the chart's own key, so this hook needs no patch; the test extracts the script from the render). Script: poll `${PROC_MOUNTS:-/proc/mounts}` once a second for the
    globalmount pattern, at most 20 polls; if any poll saw one, `sleep 12`; then the chart's `rm -rf` line.
  - `app.yaml`: remove the `chart:` block; keep `manifests: true`.
  - `cluster-apps.yaml`: wrap the non-service chart source (`- repoURL: "{{ .chart.repo }}"` through its `valueFiles`
    list) in `{{- if dig "chart" false . }}` … `{{- end }}`.
  - `validate-and-diff.yml`: kubeconform `find` adds `-not -name 'values.yaml' -not -name '*-patch.yaml'`; the
    diff-preview `docker run` adds `-v $(pwd)/pull-request/.github/argocd-diff-preview-values.yaml:/argocd-config/values.yaml`;
    that file sets `configs.cm."kustomize.buildOptions": --enable-helm`.
- [ ] **Step 4: Run** the Step 2 command. Expected: all tests PASS, old and new.
- [ ] **Step 5: Run** the other repo checks the workflow runs offline: `yamllint -c .github/yamllint.yaml .` and
  `python3 -m unittest discover -s scripts/storage/tests`. Expected: clean.
- [ ] **Step 6: Appset check** (offline; the PR's diff preview is the real proof, Review Focus 3). Run
  `git diff bootstrap/appsets/cluster-apps.yaml`: only the two guard lines are added. Run
  `grep -L '^chart:' infrastructure/*/*/app.yaml`: it lists only democratic-csi (every other infrastructure app still
  takes the guarded branch's chart source).
- [ ] **Step 7: No commit.** Record the change in `storage-lab/b10/notes.md`.

### Task 2: ansible — Argo CD Helm inflation and kubelet shutdown grace

**Files:**
- Modify: `roles/bootstrap_cluster/tasks/argocd.yml` (`configs.cm`)
- Modify: `roles/k3s_common/tasks/main.yml:133-144` (kubelet drop-in)
- Test: `scripts/tests/test_k3s_storage_settings.py` (`test_kubelet_dropin`), new `scripts/tests/test_argocd_bootstrap.py`

**Interfaces:**
- Produces: kubelet drop-in `50-graceful-shutdown.conf` with `shutdownGracePeriod: 90s`,
  `shutdownGracePeriodCriticalPods: 40s`. Task 3 deploys it to the lab workers.

- [ ] **Step 1: Write the failing tests.** `test_kubelet_dropin` expects `90s` and `40s`.
  `test_argocd_bootstrap.py::test_kustomize_helm_inflation`: load `argocd.yml`, find the task that installs the
  argo-cd chart, parse its values, assert `configs.cm["kustomize.buildOptions"] == "--enable-helm"`, and that the
  existing `cm` keys (`url`, `accounts.homepage`, `oidc.config`) are still there.
- [ ] **Step 2: Run** `python3 -m unittest scripts/tests/test_k3s_storage_settings.py scripts/tests/test_argocd_bootstrap.py`.
  Expected: FAIL on both.
- [ ] **Step 3: Implement** the two value changes; one-line comment on the drop-in: "critical tier covers the CSI
  node plugin's unstage wait (ADR 0017, F14)".
- [ ] **Step 4: Run** every `scripts/tests/test_*.py`, `ansible-lint` (production profile, dummy vault file as
  before), and `ansible-playbook --syntax-check k3s.yml`. Expected: all OK, 0 lint failures.
- [ ] **Step 5: No commit.** Record in the lab notes.

### Task 3: lab re-test (operations; Ben's OK per mutation)

Script: `memsize/f14.sh <phase>`, modelled on `f18.sh` (same helpers, `clock_ok`, `pvegate`, one phase per call,
`STOP:` on anything unexpected). Outputs to `storage-lab/b10/f14/`.

- [ ] **Step 1: `pre`** (read-only): lab clean (no fence or hold tags, 3 targets x 2 ACLs, nft empty); both writers
  Running; record which node each writer and VA is on; `dbcheck` baseline.
- [ ] **Step 2: `evidence-setup`** (mutation): on 973, `Storage=persistent` journald (check
  `journalctl --list-boots` survives the next boot); `qm set 973 --serial0 socket` and `console=ttyS0` on 973's
  kernel cmdline (takes effect at the next boot); a pve-side capture of the serial socket to a file for each poweroff.
- [ ] **Step 3: `baseline`** (mutation, F15 evidence, today's code): drain writers off 973, `qm shutdown 973`, time
  it, start it; save the serial capture and `journalctl -b -1` stop-job lines. PASS = the capture names what the
  about 90 s wait is (a stop job, or systemd-shutdown "Waiting for process" names).
- [ ] **Step 4: `deploy`** (mutation): kubelet drop-in on lab workers via the lab play (k3s-agent restarts, one node
  at a time, writers drained from the node being restarted); then render with Task 1's command in the lab shell and
  `kubectl replace` only the node DaemonSet (the lab's helm release stays; `replace`, not server-side apply, so the
  moved containers do not stay behind). PASS: both node pods Running with 1 container + 2 sidecar init containers; kubelet's logind drop-in raised
  `InhibitDelayMaxUSec` to at least 90 s (`busctl get-property org.freedesktop.login1 /org/freedesktop/login1
  org.freedesktop.login1.Manager InhibitDelayMaxUSec`);
  `kubectl get csinode` lists the driver on both workers.
- [ ] **Step 5: Leg C, rollout** (mutation): `rollout restart` the node DaemonSet while both writers write on 973.
  PASS: writers keep writing (rows contiguous), each old pod ends within 33 s, no VA change.
- [ ] **Step 6: Leg A, undrained shutdown** (mutation): both writers and VAs on 973; `qm shutdown 973`. PASS:
  - node plugin log (captured from the pod before it dies, streamed to a file on the runner) shows NodeUnstage OK
    and iSCSI logout for both volumes;
  - container exit order csi-driver first, then driver-registrar and csi-proxy (pod status or kubelet log in
    the persistent journal);
  - both VAs deleted, and no `fence lab-agent` line and no `fenced:` tag (the lab's 60 s window);
  - replacement pods Running on lab-server; timed from `qm shutdown` to replacement Running; rows grow, contiguous.
  Then start 973 and put the writers back as before.
- [ ] **Step 7: Leg B, drained shutdown** (mutation): no volumes on 973; `qm shutdown 973`. PASS: time within 5 s of
  Step 3's baseline (or of Task 4's new figure).
- [ ] **Step 8: Proxmox guest shutdown timeout** (read-only): the host's guest-stop timeout for workers on a host
  reboot (`down=` in `qm config`, else pve's default) exceeds 90 s grace plus the measured poweroff. Record it.
- [ ] **Step 9: `final`**: writers back, rows PASS vs baseline, no fence or hold tags, `pvegate`.

### Task 4: F15 fix (only if Task 3 Step 3 names k3s leftovers or an unordered iSCSI stop)

**Files:** `roles/k3s_common/tasks/main.yml`, `roles/k3s_common/templates/` (new drop-in), test
`scripts/tests/test_k3s_storage_settings.py`.

- [ ] **Step 1: Failing test** `test_k3s_agent_stop_order`: a drop-in for `k3s-agent.service` with
  `After=iscsid.service open-iscsi.service`; and, if the evidence names cgroup leftovers, a unit named outside
  `k3s*.service` with `Before=k3s-agent.service`, `RemainAfterExit=yes`, `TimeoutStopSec=30`, whose `ExecStop` kills
  the k3s-agent cgroup's leftover processes. If the evidence names something else, stop and bring it to Ben.
- [ ] **Step 2-4:** run (FAIL), implement, run all tests and lint (PASS).
- [ ] **Step 5:** lab: deploy, repeat Task 3 Step 7. PASS: drained poweroff under 40 s.

### Task 5: docs

**Files (apps-adr-0017):** ADR 0017 graceful-shutdown line and Check 11; report F14, F15, Check 11, the
"6-min force-detach" correction (report :706); plan Check 11 expectation (:1312-1322). Also `storage-lab/b10/notes.md`
and memory.

- [x] **Step 1:** ADR: graceful shutdown now unstages before the node plugin exits (cite kubernetes#125070 and the
  cleanup preStop); the fence remains the backstop for hangs and power loss; F15 outcome.
- [x] **Step 2:** Report: Task 3's measured results replace "lab re-test pending"; Check 11 re-run result.
- [x] **Step 3:** Plan: Check 11's expectation is "no fence; VAs released before the fence window".
