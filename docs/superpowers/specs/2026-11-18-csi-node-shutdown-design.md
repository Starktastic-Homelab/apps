# CSI node shutdown (F14, F15) design

Status: approved by Ben 2026-11-18. Amended after the final code review: `cleanup` is removed and `csi-driver`'s
preStop does no socket `rm` (see the amendment under Design). Sub-project 1 of the pre-teardown fix round (order: F14/F15, then F11+F12, then
F6, then the F4/F5, F9, zfs and F10 re-runs). Evidence: `storage-lab/rootcause-wf_678ed45a-3c6.json`, Check 11 in
`docs/superpowers/reports/2026-11-16-retained-storage-lab-results.md`.

## Why

Check 11 failed. An undrained worker shutdown (a `qm shutdown`, or the Proxmox host shutting its guests down)
leaves every retained volume on that worker attached until the fencer cuts it: about 50 s of node-monitor grace plus
`not_ready_seconds` (300 s) in production, so a retained app is down about 6 minutes. ADR 0017 says the opposite
("Graceful shutdown (the kubelet drop-in) moves the volumes before the fence would fire"). Ben chose to fix it, not
reword it (2026-11-18).

## Root cause (F14)

1. kubelet's graceful shutdown kills each priority group, waits for that group's pod unmounts (NodeUnpublish, the
   kubernetes#125070 wait), then moves on. It never waits for NodeUnstage, which the volume reconciler runs about
   100 ms later.
2. By then the critical group, which holds `democratic-csi-node` (`system-node-critical`), is terminating:
   - the chart's `cleanup` container has a hard-coded preStop `rm -rf /plugins/<driver> /registration/<driver>-reg.sock`,
     so the socket is gone at once;
   - `csi-proxy` and `driver-registrar` have no preStop and get SIGTERM at once: the in-flight RPC ends in EOF and
     the driver is unregistered.
3. kubelet never records the unstage, so `volumesInUse` keeps the volume. With
   `disable-force-detach-on-timeout=true` the attach-detach controller holds the VolumeAttachment until kubelet comes
   back or the fencer taints the node.

Longer grace periods alone cannot fix it: a group ends as soon as its pods and pod mounts are gone.

## Goals

- An undrained shutdown of a worker with staged retained volumes unstages them, logs out of iSCSI, and publishes an
  empty `volumesInUse` before the node plugin dies, so the VolumeAttachment is released and the replacement pod
  attaches elsewhere with no fence.
- A worker with nothing staged shuts down as fast as today.
- Only the four shutdown hooks and the registrar mount removal (F21) differ from upstream; every other chart change still arrives through Renovate.
- F15: find what the about 90 s poweroff wait is, and remove it if it is k3s leftovers.

## Non-goals and anti-goals

- No change to the fencer, its NotReady rule, settle or unfence. The fence stays the backstop.
- Never force-detach, never drop RWOP or `Retain`, never touch an image or MMP. (Binding retained-data rules.)
- Not a fix for a hard power loss or a hung worker: those still go through the fence.
- Anti-goal: a shutdown that can hang for minutes waiting on storage (an NFS stall, F11). Every wait is bounded.

## Approaches (Ben picked C, 2026-11-18)

- A. Our own node DaemonSet: `node.linux.enabled: false`, a rendered copy in `manifests/` with the hooks, plus a CI
  drift check. Contained in apps, but a 200-line copy to keep in step on every chart bump.
- B. Vendor the chart into the repo. Simple, but Renovate stops bumping it and each upgrade is a manual re-vendor.
- **C. Kustomize with Helm inflation (chosen).** Argo CD builds `manifests/` with kustomize, which inflates the
  upstream chart and patches only the node DaemonSet. Upstream changes flow through untouched; only the hooks are
  ours. Costs: a cluster-wide Argo CD setting in ansible, a two-repo order, and CI diff-preview config.

## Design

### ansible (`roles/bootstrap_cluster/tasks/argocd.yml`, branch `feat/retained-storage-vm` or its own PR)

- `configs.cm."kustomize.buildOptions": --enable-helm`. The two existing kustomize apps (authentik, jellyfin)
  inflate no charts, so they render the same (checked by the diff preview on the apps PR).
- `roles/k3s_common/tasks/main.yml` kubelet drop-in: `shutdownGracePeriod: 90s`,
  `shutdownGracePeriodCriticalPods: 40s` (today 60s / 10s). Non-critical pods keep 50 s.
- F15 only, after evidence (below): a k3s-agent drop-in `After=iscsid.service open-iscsi.service` so iSCSI logout
  runs after kubelet, and, if the wait is k3s cgroup leftovers, a shutdown-only unit that runs `k3s-killall.sh`-style
  cleanup with `TimeoutStopSec=30`.

### apps (`infrastructure/system/democratic-csi/`)

- `app.yaml`: drop the `chart:` block; keep `manifests: true`.
- `values.yaml` moves to `manifests/values.yaml`, unchanged.
- `manifests/kustomization.yaml`:
  - `helmCharts`: democratic-csi from `https://democratic-csi.github.io/charts/`, version `0.15.1`, release name and
    namespace as today, `valuesFile: values.yaml`, `includeCRDs: true`.
  - `resources`: `namespace.yaml`, `storage-fencer.yaml` (unchanged).
  - `patches` on the node DaemonSet:
    - pod: `terminationGracePeriodSeconds: 45`;
    - `csi-driver`: `preStop` exec: wait until `/proc/mounts` has no
      `plugins/kubernetes.io/csi/org.democratic-csi.node-manual/*/globalmount`, at most 20 s; only if it found one,
      sleep 12 s so the 10 s node-status update publishes the empty `volumesInUse`; then run the chart's
      `rm -rf /plugins/<driver> /registration/<driver>-reg.sock`. `csi-driver` mounts `/var/lib/kubelet`
      Bidirectional, so it sees mounts staged after the pod started;
    - `cleanup`: its preStop is replaced by a no-op (`sleep 0`). It mounts `/var/lib/kubelet/plugins` with no
      propagation and no hostPID, so it cannot see new stages; a wait there would return at once and its `rm -rf`
      would cut the unstage again (builder check, 2026-11-18). My call: move the `rm -rf` into `csi-driver`.
    - Amendment (final review, 2026-11-18): `cleanup` is removed instead, and the `rm -rf` is dropped. `cleanup`'s
      shell ignores SIGTERM, so it held every pod stop to the full grace; and a preStop also runs on a liveness
      restart, where an `rm` would orphan the live sidecars' sockets. driver-registrar v2.9.0 clears a stale socket
      at start and removes its own on SIGTERM.
    - `csi-proxy`, `driver-registrar`: moved from `containers` to `initContainers` with `restartPolicy: Always`
      (native sidecars, GA in Kubernetes 1.33; Ben, 2026-11-18). Kubernetes stops sidecars only after the main
      containers have exited, in reverse order, so they live exactly as long as `csi-driver`'s conditional wait.
      The patch is structural (two containers move), so it is a JSON6902 or strategic-merge `$patch: delete` plus
      add; the test asserts both names exist in the upstream template and end up only in `initContainers`.
    - Amendment (Leg A, F21/F22, Ben 2026-11-18 "Remove the mount"):
      - `driver-registrar`: its `kubelet-dir` mount (all of `/var/lib/kubelet`, no propagation, so rprivate) is
        removed. A registrar started while volumes were staged held private copies of every globalmount, so the
        driver's umount did not end the filesystem and node-manual's iSCSI logout landed under a live ext4
        (journal abort, lost unflushed writes). Proven in the lab: a mountinfo sweep after a node-DS restart
        found private copies only in the registrar, and the fixed spec leaves none. v2.9.0 never reads that path
        (`--mode=kubelet-registration-probe` exits 0). This is a fifth divergence from upstream (charts#76/#77).
      - `csi-driver` preStop: hold while a node-manual `globalmount` directory or an iSCSI session to
        `iqn.2026-11.net.starktastic.storage:*` exists, not while `/proc/mounts` lists a globalmount. The
        mount entry goes at the unstage's first step (umount); the directory goes at its last (rmdir, after the
        logout), so the old hook let SIGTERM in mid-unstage. Bounds unchanged (20 s + 12 s).
      - Tests: every node-pod mount whose hostPath covers the CSI plugin or pods tree must be HostToContainer or
        Bidirectional; the registrar mounts only `socket-dir` and `registration-dir`.
  - The wait returns at once when nothing is staged.
- `bootstrap/appsets/cluster-apps.yaml`: the infrastructure branch always emits a chart source from `.chart.repo`
  with `missingkey=error`. Wrap that source in `{{- if dig "chart" false . }}`. This touches the template every
  infrastructure app renders through, so the diff preview must show every other app unchanged.
- democratic-csi exists only on the unmerged `feat/retained-storage-vm` branches, not on apps `main`, so there are no
  production objects to update in place. My call: fold this into those branches; the app's first production sync
  is already the kustomize one.
- `scripts/storage/tests/test_democratic_csi_values.py`: read the chart reference from `manifests/kustomization.yaml`
  instead of `app.yaml`; add an assertion that the rendered node DaemonSet has the four hooks and that the four
  container names in the patch exist in the upstream template (a rename then fails the test instead of adding a
  broken container).
- `.github/workflows/validate-and-diff.yml`: mount a `values.yaml` with the same `kustomize.buildOptions` into the
  diff-preview container (`/argocd-config/values.yaml`, per its docs), or every PR touching the app fails to render.
- Renovate: its kustomize manager bumps `helmCharts` versions (documented); the old `chart:` entry goes away.

### Order and delivery

- Production: the ansible change (Argo setting + kubelet drop-in) must be deployed before the apps storage branch
  merges, or democratic-csi's first sync fails to render. This adds one more ansible-first step to the ADR 0017
  rollout, which already needs ansible before apps. While the lab holds the production lock, no ansible merge.
- Lab: the lab installs democratic-csi with plain helm, not Argo. The re-test renders with
  `kustomize build --enable-helm` and applies the result, so it proves the pod behaviour, not the Argo wiring; the
  diff preview and the first production sync prove the wiring.

## Lab re-test (each mutation needs Ben's OK at run time)

Setup: lab 970-973 up, fencer clean, both writers on lab-agent (973) with VAs on lab-agent; lab timings 60 s / 5 s.

1. Evidence for F15 first: make 973's journal persistent; add a serial console (`qm set 973 --serial0 socket`,
   `console=ttyS0`) and capture it from pve during each poweroff. One baseline `qm shutdown 973` on today's code,
   drained, to see what the 90 s is.
2. Deploy: the kubelet drop-in on the lab workers (k3s restart), then the rendered democratic-csi on the lab.
3. Leg A, undrained shutdown: `qm shutdown 973` with both writers on it. PASS:
   - node plugin log shows NodeUnstage OK and iSCSI logout for both volumes before the plugin exits;
   - container exit order: `csi-driver` first, then `driver-registrar` and `csi-proxy` (sidecars);
   - both VolumeAttachments are deleted before the fencer's `fence lab-agent` line would fire (the 60 s window), and
     no `fenced:` tag is written;
   - replacement pods Running on lab-server; rows grow, contiguous; timed: shutdown start to replacement Running.
4. Leg B, nothing staged: drained 973 shutdown time within a few seconds of the F18 control (103 s, or the F15 fix's
   new number); the node plugin's containers exit within a second of each other's turn (main first, then sidecars).
5. Leg C, rollout: restart the node DaemonSet on a node with staged volumes; the writer keeps writing (no unstage on
   rollout), each pod ends within the 32 s hold.
6. F15 fix (if the evidence names k3s leftovers): deploy, repeat Leg B; PASS = poweroff under 40 s on a drained node.
7. Check the Proxmox host's guest shutdown timeout covers 90 s kubelet grace plus poweroff.

## Docs to change after the re-test

- ADR 0017: the graceful-shutdown line and Check 11; cite the cleanup preStop and kubernetes#125070.
- Report: F14, F15 and Check 11 results; correct "6-min force-detach" (report :706, b8 notes :76).
- Plan: Check 11 expectation (plan :1312-1322).

## Decided: holding csi-proxy and driver-registrar (Ben, 2026-11-18)

Native sidecars, not a fixed `preStop: sleep` of 32 s. The sleep would have added about 32 s to every worker
shutdown, drained or not (kubelet's critical group waits for every critical pod; a drain does not evict DaemonSet
pods). With sidecars a nothing-staged shutdown stays as fast as today. Cost: a structural patch, and the lab must
prove the sidecar order holds during kubelet's node shutdown, not only during a pod delete (Leg A, Leg B).

## Left to the builder

- Exact shell of the preStop wait (the driver image has `sh`; `cleanup` is busybox).
- Whether the patch is strategic-merge or JSON6902, as long as a renamed container fails the test.
- Release name and `namespace` handling so rendered names match today's exactly.

## My calls (Ben can overrule)

- Keep `csi-proxy` (as a sidecar) rather than disabling it: smallest change from today.
- Move the chart's `rm -rf` from `cleanup` into `csi-driver`'s preStop, after the wait.
- Fold this into the unmerged `feat/retained-storage-vm` branches, not a follow-up PR.
- Hold times 20 s wait + 12 s publish, grace 45 s, critical tier 40 s: from the Check 11 timeline (unstage about
  100 ms after pod unmount, node status every 10 s).
- Lab Leg A judged at the lab's 60 s fence window; not re-run at production's 300 s.
- F15's fix only after the serial console names the wait; otherwise F15 is documented, not fixed.
