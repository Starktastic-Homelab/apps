# Storage VM cutover

Moving one volume from its Proxmox CSI image to the storage VM (ADR 0017, Migration, step 3). This is the readable
form of migration plan Task 4.T. The plan has the full commands, the evidence files and the D14 pair and wave-6
deltas; where this runbook and Task 4.T differ, Task 4.T wins.

**No lab evidence for the copy.** The lab never ran a copy Job; it only bound a Block pair (lab report `:337`). Every
command here is `(not rehearsed)` until the first cutover (tempo) records it.

Where commands run:
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve through the helper. ASCII only, no `$`,
  no single quotes in the row.
- `[P]`: root on pve. `[T]`: TrueNAS. `[K]`: `k3s kubectl` on the master. `[K-host]`: a root shell on the master.
- `[R]`: root on VM300, the runner. `[TOOL]`: the copy-tool host (`tool_host`, Task 4.0). `[W]`: the workstation.

Names, from the Task 4.W row: `<id>`, `<ns>`, `<app>` (the Argo Application), `<old_claim>`, `<old_pv>`,
`<new_claim>`, `<size>`, `<bytes>`, `<class>`, `<vg>`, `<writer>`, `<selector>`, `<binding_file>`. `<ev>` is
`~/.cache/claude-homelab-live/storage-migration/evidence/4.T-<id>/`.

## Before you start

- Task 4.0 is done: `capacity_rule`, `freeze_checks`, `syncwindow_form`, `tool_host`, `gate_coverage` and the helper in
  `/run/homelab-cutover/` (`lock.sh`, `watch.sh`).
- **Ben OK** at every merge, apply, scale, patch, delete and lock change. Each one is marked.
- One cutover at a time. The next starts only after the previous one released its lock.
- **The freeze rule.** From the inventory PR until the lock is released, nothing merges in packer, terraform or
  ansible, and no drift or Debian-ISO PR is merged. An ansible merge restarts k3s on every node.
- **The clone rule.** Before every `precheck`, `render` and `verify-teardown`, the tool host's apps clone is a clean
  detached `origin/main` that contains the latest cutover merge (Task 4.T, Clone rule). A stale clone is a stop.
- Outside every backup window (ansible `docs/backup-and-restore.md`, "Schedules"; migration plan, Global constraints).
  The copy Job may run up to 4 h (`activeDeadlineSeconds: 14400`), so start it only when the 4 h that follow miss
  02:00-05:30 and the `:25-:50` slots of 03, 09, 15 and 21 (Asia/Jerusalem).
- The maintenance lock is `FREE` before "Lock", and this runbook holds it from "Lock" to "Teardown and
  verify-teardown". While it is held, every `storage.yml` run skips.
- PRs merge with `gh pr merge <n> -R Starktastic-Homelab/apps --squash --match-head-commit <full SHA>`.

## Capacity gate

Read-only. Stop here if any check fails; the growth runbook "Dataset full" and Ben's call come first.

1. The four `capacity_rule` reads (Task 4.0 Step 4) for `<bytes>` and `<vg>`. Expected: all pass.
2. `[T]` `zfs get -Hp used,usedbydataset,usedbysnapshots apps/k3s-block` into `<ev>/capacity.txt` as "before".
3. `[P]` `pvesm list k3s-block --vmid 9999`. Expected: `vm-9999-<id>.raw` is exactly `<bytes>` (D26: smaller makes
   the Job run `resize2fs`, larger makes it refuse mid-outage).
4. D20: `apps/k3s-block` `available` is at least the source's full length plus 10 GiB, until the first cutover's
   measured delta shows zeros become holes.

## Inventory PR

1. `freeze_checks`. Expected: all empty.
2. In apps, branch `storage/inventory-<id>`, add to `infrastructure/base-configs/files/retained-volumes.json`:
   `{"id": "<id>", "namespace": "<ns>", "claim": "<new_claim>", "size": "<size>", "class": "<class>",
   "origin": "migrated"}`.
3. `python3 scripts/check-retained-inventory.py --base origin/main --override-label storage-removals-approved
   && python3 -m unittest discover -s scripts/storage/tests -v`. Expected: exit 0.
4. Commit `feat(storage): add <id> to the retained inventory (ADR 0017 cutover)`, push, open the PR. **Ben OK.**
5. Merge. **Ben OK.** Live events: `base-configs` renders PV `<id>` and PVC `<ns>/<new_claim>`; `storage-changed`
   dispatches `storage.yml`, which creates the raw LV and its target.
6. Wait for the LV. Expected:
   - `[W]` a `storage.yml` run after the merge, `success`, with one `create_raw` action for `<id>` and no `refused:`
     or `error:` line. None within 10 min: dispatch it by hand, **Ben OK**;
   - `[S]` `lvs --devices /dev/disk/by-id/virtio-<vg> --readonly --noheadings -o lv_name,lv_size --units b <vg>/<id>`
     shows `<bytes>B` (the PV is `virtio-retained` or `virtio-regen`);
   - `[K]` PV `<id>` is `org.democratic-csi.node-manual Bound <new_claim>`;
   - `storage_target_missing{id="<id>"}` is `0`.

## Lock

The cutover holds the maintenance lock from here to the teardown, so no `storage.yml` or deploy run changes the
storage VM under it.

1. **Ben OK.** `[R]` `sh /run/homelab-cutover/lock.sh acquire <id> claude-code/storage-cutover-<id>/<UTC ts>`, one row.
   For a D14 pair the first argument is `<id1>:<id2>`.
   Expected: `storage-cutover:<id> claude-code/storage-cutover-<id>/<ts> <time>`. The script refuses if
   `operation.json` exists. The nonce stays in the root-only file and is never printed.
2. Write the owner into `<ev>/facts.md`. Re-run `freeze_checks`. Expected: all empty.
3. Hourly `storage.yml` runs now skip with the lock-held warning. That is expected.

## Hold

1. `[K]` save `-n argocd get appproject default -o json` as `appproject-before.json`. Record `resourceVersion` and
   `.spec.syncWindows`.
2. `[K]` the app is idle: `Synced Healthy Succeeded` and no `.operation`. Otherwise stop.
3. Record the writer baseline (replicas and image) and `<selector>` (Task 4.T Step 3.3, by style).
4. **Ben OK.** Add the deny window with a `test` on `resourceVersion` (Task 4.T Step 3.4): `kind: deny`,
   `schedule: "* * * * *"`, `duration: 24h`, `applications: ["<app>"]`, `manualSync: false`,
   `description: storage-cutover:<id>`. Read it back; record its index `<i>`. A second `test` failure is a stop.
5. `[K]` the app still has no `.operation`.
6. Writer inventory into `<ev>/writers.txt`: Pods, CronJobs and Jobs on `<old_claim>`, the VolumeAttachments, and
   `[P]` a `qm config` grep for `vm-9999-<id>.raw` on each worker. Expected: the one 4.W writer and one VA. A second
   writer is a stop.
7. **Ben OK.** Scale the writer to 0 by its style: `scale deploy` or `scale sts --replicas=0`, or patch the operator
   CR's `spec.replicas` to 0 (never the operator's StatefulSet). Plus any extra hold the 4.W row names.
8. Wait for a cold source, polling every 15 s for up to 10 min: no pod on `<old_claim>`, no VA on `<old_pv>`, the
   `qm config` grep empty. **Never force-detach.**
9. `[TOOL]` `cd <apps clone> && python3 scripts/storage/migrate_volume.py precheck <id>`. Expected: exit 0. Any
   `refused:` line is a stop.

## precheck, render, apply, Job

1. `[TOOL]` `install -d -m 0700 <td>/render && cd <apps clone> && python3 scripts/storage/migrate_volume.py render
   <id> --direction forward --out <td>/render`. Copy `pairs.yaml`, `job.yaml`, `render.json` to `<ev>/render/`.
   Expected: binding handle `homelab//k3s-block/9999/vm-9999-<id>.raw`, target handle `<id>`, both sizes `<bytes>`.
2. **Ben OK.** `[TOOL]` `kubectl apply -f <td>/render/pairs.yaml`. Expected: `migrate-src-<id>` and
   `migrate-dst-<id>` `Bound`.
3. Re-run `precheck <id>`. Expected: exit 0.
4. **Ben OK.** `[TOOL]` `kubectl apply -f <td>/render/job.yaml`.
5. `[K]` poll `-n <ns> get job migrate-<id> -o jsonpath='{.status.succeeded} {.status.failed}'` every 60 s.
   Expected: `1`, no `failed`, inside `activeDeadlineSeconds: 14400`. A failed Job: keep the hold and the lock, save
   the log, stop. The source was only read.
6. `[K]` `-n <ns> logs job/migrate-<id> > <ev>/copy.log`; record the Job pod's node.

## Verify and re-run precheck

Read-only.

- `copy.log` has `copy-ok forward <bytes> <bytes>`, an `e2fsck -fp` exit 0, the three `dumpe2fs -h` matches (`mmp`,
  `Remount read-only`, `MMP update interval: 5`) and no `resize2fs` line. `e2fsck` exit 1 is Ben's call, not a pass.
- The Job pod is `Succeeded`, and no VA names `migrate-src-<id>`, `migrate-dst-<id>`, `<old_pv>` or `<id>`.
- `[TOOL]` `precheck <id>` again. Expected: exit 0, so no writer appeared during the copy.
- `[T]` the `zfs get` again as "after", with the delta. On the first cutover, give Ben the delta against `<bytes>`
  (D20's measurement).
- Record the verify date as `<copied>` (UTC `YYYY-MM-DD`).

## Switch PR

1. In apps, branch `storage/switch-<id>`: the 4.W row's binding edit (`<old_claim>` to `<new_claim>`, or the kps
   template, `volumeName` and guard mount), plus `"copied": "<copied>"` on the entry. Nothing else, no image bump.
2. The same checks as the inventory PR. `check_bindings` passes because `copied` is set.
3. Commit `feat(storage): switch <id> to the storage VM (ADR 0017 cutover)`, push, open the PR. **Ben OK.**
   `gh pr checks` all pass; the diff preview changes only `<app>`, and `base-configs` renders nothing new.
4. Merge under the hold. **Ben OK.** Record `<sha>`.
5. `[K]` the app is `OutOfSync` at `<sha>`, the writer is still at 0, and no operation is pinned to an older
   revision. A queued or older operation: do not lift the window; retire it only with the qualified patch in Task 4.T
   Step 7.3, with `<op>` shown to Ben first. A `test` failure or an operation that cannot be classified is a stop.

## Lift the hold and the 6-minute watch

1. **Ben OK.** `[K-host]` `systemd-run --unit=cutover-watch-<id> -p RemainAfterExit=yes
   -p StandardOutput=file:/run/cutover-watch-<id>.log sh /run/homelab-cutover/watch.sh <app> <ns> <selector>`.
2. **Ben OK.** Re-read the project (`<rv2>`), check index `<i>` is still `storage-cutover:<id>`, then remove only that
   window with `test` ops on `resourceVersion`, `description` and `applications` (Task 4.T Step 8.2). Expected:
   `patched`; the windows from the hold's step 1 are left.
3. Nothing syncs within about 5 min: confirm no `Running` operation, then **Ben OK** for one sync with the full
   resolved revision array and `prune: false` (Task 4.T Step 8.3).
4. Expected in the watch log for 6 minutes after the first Ready: `Synced Healthy` at `<sha>`; one pod, on
   `<new_claim>` only; no growing restart count; the baseline image. The first start waits about 42 s for MMP, up to
   about 720 s on slow storage.
   - A pod on `<old_claim>` at any point: scale to 0 at once (**Ben OK**), re-add the window, stop. Ben decides.
   - Any other failed check: Rollback.
5. Native checks: the guard init container exited 0; the VA for PV `<id>` has attacher
   `org.democratic-csi.node-manual`; `storage_target_missing{id="<id>"}` is `0`; the 4.W per-class check.
6. Save the log as `<ev>/watch.log`; `[K-host]` `systemctl stop cutover-watch-<id>; systemctl reset-failed
   cutover-watch-<id>`.

## Reconciliation PR

The old binding files go; the old image stays as the rollback copy.

1. In apps, branch `storage/reconcile-<id>`: delete only the PV and PVC documents of `<old_pv>` and `<old_claim>` from
   `<binding_file>` (the file only when it becomes empty). Never touch `templates/retained-startup-guard.yaml` (D47).
2. The same checks. Commit `chore(storage): drop the Proxmox CSI binding of <id> (ADR 0017 reconciliation)`.
3. `freeze_checks`, then push, open and merge. **Ben OK** each.
4. `[K]` `base-configs` is `Synced Healthy`. If it stays `OutOfSync` only for the unmanaged old PV and PVC: check the PV
   is `Retain`, then **Ben OK** to delete the PVC and then the PV. `[P]` `pvesm list k3s-block --vmid 9999` still
   lists `vm-9999-<id>.raw` at its size.

## Teardown and verify-teardown

1. **Ben OK.** `[K]` delete Job `migrate-<id>`, ConfigMap `migrate-<id>`, PVCs `migrate-src-<id>` and
   `migrate-dst-<id>`, then PVs `migrate-src-<id>` and `migrate-dst-<id>`. Both PVs are `Retain`: no data is touched.
2. `[TOOL]` `cd <apps clone> && python3 scripts/storage/migrate_volume.py verify-teardown <id>`. Expected: exit 0.
3. **Ben OK.** `[R]` `sh /run/homelab-cutover/lock.sh release <id> <owner>`, one row. Expected: `released`.
   Then dispatch `storage.yml`, **Ben OK**, `[W]` `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref
   main` `(not rehearsed)`. Expected: a green run. A change that merged under the lock (the switch PR's lock-held
   skip) applies now, not at the next hourly run (up to about 3 h away across the D29 window skips).
4. Re-enable any auto-merge `freeze_checks` disabled. **Ben OK.**
5. Write `facts.md`: the times, `<copied>`, the capacity delta, the Job node, the PR numbers.

## Rollback (revert, or reverse copy)

The split is whether the target took app writes, not the step number (ADR Migration, Rollback). **Never remove the
inventory entry before a verified reverse copy.** An interrupted step keeps the hold, the lock and both images: never
replay an uncertain apply, copy or delete; bring the state to Ben.

- **R1, before the window is lifted.** Revert the switch PR (**Ben OK**); the app goes `OutOfSync` towards
  `<old_claim>`; lift the window and watch on `<old_claim>`; tear down. The entry and its LV stay; a retry skips the
  inventory PR (Task 4.T R1 step 5).
- **R1b, the target took no writes** (the guard refused, the pod stuck in init, or no pod started). Hold again on
  `<new_claim>`, revert the switch PR (**Ben OK**), lift and watch on `<old_claim>`, tear down, release the lock. Keep
  the LV and the entry for Ben to inspect.
- **Not sure** (the guard exited 0 and the main container started but never went Ready): stop, hold again and bring it
  to Ben. Neither R1b nor R2 runs without his choice.
- **R2, after writes** (the guard exited 0 and the main container went Ready on `<new_claim>`). A reverse copy with
  its own sequence (Task 4.T R2): the entry check (`gate_coverage` covered, reverse render pass 1) before any hold;
  the lock (take it again if released); hold again on `<new_claim>`, with `[S]` `targetcli sessions` empty for the
  target; forward pairs torn down; the reverse source gate (record the latest TrueNAS snapshot, Block half
  `gate-fsck-ok`, Filesystem half `gate-guard-ok`, gate teardown); pass 2; reverse precheck; pairs and Job, expecting
  `copy-ok reverse <bytes> <bytes>`; revert the switch PR; lift and watch on `<old_claim>`; tear down and release.
  Only then offer Ben the entry-removal PR. An id with no gate coverage has no reverse copy.
- **R3, after the reconciliation PR.** Revert the reconciliation PR first (**Ben OK**), check `<old_claim>` is `Bound`
  to `<old_pv>` again, then R2.

## Stale lock

`MaintenanceLockStale` (Task 2.4). Its `operation` label names the holder, as read hourly by the `Write host gauges`
step. The gauge can be an hour old: confirm against the real file before acting.

1. `[R]` read the holder without the nonce, one row:
   `python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(d[sys.argv[2]],d[sys.argv[3]])"
   /var/lib/homelab-maintenance/operation.json operation owner` (one row, no single quotes; the plan's Task 4.T R2
   step 1 has them).
   A missing file means it was released.
2. By owner:
   - A CI owner (`Starktastic-Homelab/<repo>/<run>/<attempt>`): a failed run keeps its lock (D31). Read that run's
     log first, then release as in ansible `docs/maintenance-lock-release.md` (identify the holder, match the run,
     check no process is left, then its release script), with Ben's OK.
   - `claude-code/storage-cutover-<id>/<ts>`: a cutover is in progress or was interrupted. Read `<ev>/facts.md` and the
     cluster state. Releasing it ends the freeze, so never release it mid-cutover. Its taker releases it with
     `lock.sh release` after the teardown (Teardown step 3). `maintenance-lock-release.md` refuses `claude-code/`
     owners.
   - Another `claude-code/` owner (a ledger fix, an offline `e2fsck`, an upgrade window, the scale gate; operation
     `storage-cutover:<suffix>`): released by whoever took it, with `lock.sh release <suffix> <owner>`.

## NodeStage login retry

D10, lab F1, ADR `:265-268`. Accepted, not mitigated.

- A NodeStage against a target that does not answer retries `iscsiadm -l` 15 times, about 2 min each, so it holds
  the volume's lock for about 30 min.
- Meanwhile NodeUnstage is refused, the VA can outlive its PV, and a target with that IQN created inside the window is
  logged into with no pod.

Once the target answers `(not rehearsed)`:
1. `[S]` `targetcli sessions`, and `[K]` the pods on that claim. Compare: a session from a worker with no pod there is a
   stray login.
2. **Ben OK.** `[K]` delete the pod, so it gets a fresh NodeStage. Expected: one session, from the new pod's node.

## Undo

- Before the switch PR merges: R1.
- After it: R1b, R2 or R3 as above. The old image is kept until Ben approves its retirement, so every cutover has a
  way back.

## Evidence

- `<ev>/`: `capacity.txt`, `clone-head.txt`, `facts.md`, `appproject-before.json`, `writers.txt`, `render/`,
  `copy.log`, `watch.log`, and `reverse/` for an R2.
- Sources: ADR 0017, Migration step 3 and its Rollback, Workers `:265-268`; migration plan Task 4.T, 4.0, 4.W, Tasks
  2.4, 2.5, 2.6, D10, D20, D26, D31, D37, D47; ansible `docs/maintenance-lock-release.md`.
- Lab: none for the copy. Report `:337` (a Block pair bound, no Job); F1 for the login retry.
