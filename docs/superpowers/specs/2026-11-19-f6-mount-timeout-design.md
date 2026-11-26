# F6: the first NodeStage after a fencing failover (short design)

Date: 2026-11-19. Status: approved by Ben 2026-11-19. Lab finding F6 (report `2026-11-16-retained-storage-lab-results.md`, B6).
Research: workflow `wf_028baed2-5c7` (democratic-csi v1.9.5 `b5be00c0`, chart 0.15.1, Kubernetes v1.37.2, Linux 6.12
`fs/ext4/mmp.c`), sources kept under the session scratchpad `src/`.

## Intent

After an unclean stop (every fencing failover), ext4 MMP makes the next mount wait. The node plugin's 30 s mount
timeout fires first, and the failure leaves a mount nobody cleans up if the pod goes away before kubelet retries. Ben,
2026-11-19: fix it with the driver's mount timeout, 900 s.

## Mechanism (verified in source unless marked)

1. **MMP wait.** `ext4_multi_mount_protect` sleeps `min(2C+1, C+60)` twice, where C is the check interval the old
   holder's kmmpd last wrote (`clamp(2 x write latency, 5, 300)`). The lab's "MMP interval 42" is C = 10, so 42-44 s.
   On the NFS-backed LVs the worst case is about 720 s plus I/O.
2. **The 30 s timeout does not stop the mount.** `MOUNT_DEFAULT_TIMEOUT` (ms, env only, `src/utils/mount.js:13-22`,
   default 30000, 0 means 30000) is a spawn timeout. SIGTERM reaches only the bash wrapper `docker/mount`, which does not
   `exec` mount, so mount(8) finishes anyway. The rejection arrives when it does (lab: kernel mount :54, error :55).
3. **It is reported as final.** The plain `{timeout: true}` object becomes gRPC `INTERNAL`
   (`bin/democratic-csi:285-304`), with no unmount or iSCSI logout. kubelet treats `INTERNAL` as final and records the
   device as not mounted (`operation_generator.go:685-712`).
4. **The leak.** Normally kubelet's retry finds the mount and succeeds. If the pod is deleted first, kubelet only marks
   the volume detached and never calls NodeUnstage. The attach-detach controller moves the VA at once, the old node
   keeps its mount, session and kmmpd, and the next node's mount fails busy (lab: 10 min). Reconstruction never cleans
   a global mount. MMP was what blocked a double mount.

## Approaches

1. **Driver mount timeout 900 s (Ben's pick).** One entry in the chart's existing `node.driver.extraEnv`:
   `MOUNT_DEFAULT_TIMEOUT: "900000"`. kubelet's own 2 min deadline on NodeStage always fires first and is non-final
   (`DeadlineExceeded`, device Uncertain); retries during the wait get `ABORTED` from the driver's per-volume lock, also
   non-final; when the mount ends the next retry reuses it. An Uncertain device gets NodeUnstage when its pod is deleted,
   so both the first-stage failure (healthy case: one NodeStage, ~44 s) and the leak are gone. 900 s covers the 720 s
   worst case; a value just above 120 s would not, since a driver timeout mid-wait would send a final error again.
2. MMP update interval 2 s: halves the healthy wait only, does nothing for the leak, and adds sync writes on NFS.
   Not taken.
3. Patch the driver (`exec mount`, or map timeouts to `DEADLINE_EXCEEDED`), or a node sweeper for leaked mounts: a fork
   or new code that treats the symptom. Not taken.

## Design

- **apps** `infrastructure/system/democratic-csi/manifests/values.yaml`, `node.driver.extraEnv`: add
  `MOUNT_DEFAULT_TIMEOUT` = `"900000"`, with a comment naming F6, the MMP worst case and kubelet's 2 min deadline.
  No JSON6902 patch (the chart renders `extraEnv` into the `csi-driver` container).
- **Cost, accepted with the pick:** the same timeout covers `umount`, `findmnt` and bind mounts. A hung unmount of a dead
  filesystem holds that volume's driver lock for up to 15 min instead of 30 s (the stale-filesystem checks use
  `err.timeout`). Other volumes are not blocked.
- **Do not set** `ISCSI_DEFAULT_TIMEOUT` (a string breaks spawn) or `FILESYSTEM_DEFAULT_TIMEOUT` (unused).
- **Docs:** ADR 0017 gets one bullet where it describes the node plugin (the timeout and why), and the report's F6
  entry gets its status.

## Tests (RED first)

- `scripts/storage/tests/test_democratic_csi_values.py`: the rendered `csi-driver` container of the node DaemonSet has
  `MOUNT_DEFAULT_TIMEOUT` = `"900000"`, and the value parses as an integer above 720000 (the MMP worst case) and
  above 120000 (kubelet's NodeStage deadline). No other container gets it; the controller does not need it.

## Lab check (each step with Ben's OK; clock gate; writers drained for the node DaemonSet change)

1. Apply the same env to the lab's node DaemonSet (JSON patch, as F14 did), roll it out, and confirm the variable in
   both node pods' `csi-driver` containers.
2. Fencing failover with the writer on lab-agent (hard stop 973, the loop fence): the writer's NodeStage on lab-server
   succeeds on the first call after the MMP wait, with no `INTERNAL` and no `timeout:true` in the driver log; rows
   contiguous.
3. Leak case: a second failover, and scale the writer to 0 during the MMP wait. Expect kubelet to NodeUnstage on
   lab-server after the stage returns (driver log), no global mount or session left there, and the next start
   (scale to 1) mounts normally.
4. Not covered by the lab unless Ben asks: a wait longer than 120 s (needs injected write latency before the fence), the
   Uncertain path itself. It rests on the source reading above.

## Unverified, to watch in the lab

That the pinned image digest is the v1.9.5 build; that the node process runs `/usr/local/bin/mount` (the bash wrapper);
that the csi-grpc-proxy in front of the driver adds no timeout of its own.
