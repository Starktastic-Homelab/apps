# Storage VM growth

Growing a volume, growing a data disk, and what to do when the `apps/k3s-block` dataset runs low (ADR 0017,
Reconcile rules and Capacity).

Where commands run:
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve through the helper. ASCII only, no `$`,
  no single quotes in the row.
- `[P]`: root on pve. `[T]`: TrueNAS. `[K]`: `k3s kubectl` on the master. `[N]`: root on a worker.
- `[W]`: the workstation (`gh`, `git`).

## Before you start

- **Ben OK** for each PR merge and each `qm resize` and `pvresize`.
- A grow never stops the app, so no deny syncWindow and no lock of your own: `storage.yml` takes the lock itself.
- The maintenance lock is `FREE`. A run that finds it held skips and retries at the next hourly run.
- Outside every backup window (ansible `docs/backup-and-restore.md`, "Schedules") for a merge, a manual `storage.yml`
  dispatch, `qm resize` and `pvresize`. Scheduled `storage.yml` runs skip the windows themselves (D29).
- Not during a cutover, for "Grow a data disk" (a terraform PR): the freeze rule holds from a cutover's inventory PR
  to its reconciliation PR.

## Grow a volume

An inventory size PR. The reconcile runs `lvextend`, then on the worker with a logged-in session to the target it runs
`iscsiadm -m session -R` and an online `resize2fs` (ansible `roles/storage_vm/tasks/grow-volume.yml`).

1. **The PR.** In apps, raise `size` for the entry in `infrastructure/base-configs/files/retained-volumes.json`.
   Never lower it: CI rejects a size decrease, and the reconcile never shrinks.
2. **CI.** `python3 scripts/check-retained-inventory.py --base origin/main --override-label storage-removals-approved`
   `(not rehearsed)`. Expected: exit 0.
   - CI refuses a PR that takes the class over its VG's usable size (the data disk sizes in terraform `main`
     `storage/terraform.tfvars`, Task 2.6), or
     that leaves less than the snapshot reserve free (the largest entry in that VG, at least 10% of it).
   - A refusal there means "Grow a data disk" first.
3. **Merge.** **Ben OK.** Live event: `storage-changed`, then a `storage.yml` run.
   - The dry run refuses `no-space` when the VG's real free space is short, and the run fails before it takes the
     lock (D40). The next hourly run retries on its own. Grow the data disk, or lower the size again.
   - A volume that stops fitting between the dry run and the apply fails the apply and keeps the lock (D31).
4. **Read the run.** `[W]` `gh run view <run id> -R Starktastic-Homelab/ansible --log | grep -E
   "extend|Rescan|Grow the filesystem|refused:|error:"` (one row) `(not rehearsed)`.
   Expected: an `extend` action for the id, then on the worker `Rescan the session` and `Grow the filesystem online`
   changed. No `refused:` or `error:` line.
5. **Check the size where it changed.**
   - `[S]` `lvs --devices <PV of vg> --readonly --noheadings --units b -o lv_name,lv_size <vg>/<id>`
     `(not rehearsed)`. Expected: the new size in bytes.
   - `[K]` `get pv <id> -o jsonpath='{.spec.capacity.storage}'`. Expected: the new size.
   - Inside the app's pod: `df -B1 <mount path>`. Expected: about the new size, with no restart (lab Check 7:
     `2,077,073,408` bytes after 1 Gi to 2 Gi).
   - Not `kubectl get pvc`: the PVC request is the constant `1Mi` for every entry, and a bound static PVC never
     changes. `get pvc` keeps showing the bind-time capacity (Task 2.6 Steps 5-8).
6. **A skipped filesystem.** The grow step is level-triggered. If the volume was not mounted or not logged in during
   the run (a VolumeAttachment alone is not enough, F5), the next run grows it. A worker that does not answer within
   30 s is skipped too, and the run stays green: `WARNING: <node> is unreachable; not grown: <ids>. The next run
   retries.` A grow that fails on a worker that answers fails the run and keeps the lock (D31). An interrupted run
   is safe too: the retry finishes the `resize2fs` (lab Check 7, `pause_after: ["grow:lvextend"]`, then a kill and a
   retry).

## Grow a data disk

When a VG is too small. The order is fixed: resize the disk, `pvresize`, then a terraform PR that records the size.
The terraform `storage/` root uses the bpg provider, which never resizes a disk it does not own.

1. **The resize.** `[P]` `qm resize <D1:storage_vmid> virtio1 +<N>G` for `retained`, or `virtio2` for `regen`.
   **Ben OK.** `(not rehearsed)` in production; lab B7 Step 2 resized through the API.
   Expected: `qm config` shows the new size with the same volid. virtio-blk picks up the new size by itself.
2. **The PV.** `[S]` `pvresize --devices /dev/disk/by-id/virtio-retained /dev/disk/by-id/virtio-retained` (or
   `virtio-regen`). **Ben OK.** `(not rehearsed)`
   Expected: `vgs --devices /dev/disk/by-id/virtio-retained --readonly --units b -o vg_name,vg_size,vg_free retained`
   shows the larger size.
3. **The terraform PR.** Raise that disk's `size` in `storage/terraform.tfvars` to match.
   - Expected plan: no disk diff (lab B7, tfvars 9G against a 9G disk).
   - F10: any `data_disks` change sends the changed disks' options (bpg >=0.120.0 #3251) and deletes drives the config
     omits. The root disk `virtio0` is declared after the data disks, so bpg keeps it. A stale size fails safely: `Cannot shrink ... it is not supported!`, and a larger one
     fails with `Cannot resize ... it is not owned by this VM!`; the config is unchanged either way (lab F10 re-test).
   - Merge. **Ben OK.** Live event: a no-op apply.
4. **Last step: re-check the budget.** apps CI reads the new size from terraform `main` on its next run; there is no
   apps PR. Re-run the bootstrap runbook's "Check the VG budget".

## Dataset full

`StorageDatasetLow` (Task 2.4) fires on the `apps/k3s-block` dataset's free space, or when its gauge is stale.

- Thin overcommit: the two data disks (virtual size) exceed the dataset quota, and the plain LVs keep showing free
  space while the files under them cannot grow. If the dataset fills, new-block writes fail on every volume in both
  VGs at once. A quota hit most likely turns every mounted volume read-only; a full pool may pause the storage VM.
  Neither is tested. This alert is the only warning.
- **The staleness leg** (timestamp older than 3 h) means the `Write host gauges` step of the ansible `storage.yml`
  workflow (added by Task 2.4) is failing or not running. It is `continue-on-error`, so the run still looks green.
  Read that step's log before trusting capacity rule item 4 (Task 4.0).

1. `[T]` `zfs get -Hp available,used,usedbydataset,usedbysnapshots apps/k3s-block` `(not rehearsed)`.
2. Stop new work: no cutover starts while this fires. The per-cutover capacity gate (D20) needs `available` at or
   above the source's full length plus 10 GiB, until the first cutover's measured `used` change shows that zeros
   become holes (D20 stays open until then).
3. Make room, each with Ben's OK:
   - delete retired rollback images Ben has approved (ADR Capacity, "Two copies");
   - remove inventory entries of volumes that are no longer needed (the expiry deletes them after 3 days).
4. Space comes back only after the snapshots that hold the deleted blocks expire: 1 week on TrueNAS and 2 weeks on
   `usbbk`. A deleted LV returns its space at once only on the live dataset (lab Check 12: the `.raw` file's allocated
   size fell from about 400 MiB to 1.5 MiB after an expiry). So delete at least a week before the space is needed.
5. If writes already fail: the volumes have gone read-only. After space is back, follow
   `storage-vm-readonly-fs.md` "Restage" per app.

## Undo

- A volume grow: none. The reconcile never shrinks. A wrong size stays; a smaller new volume plus a copy is a new id.
- A data disk grow: none. Proxmox cannot shrink a disk.

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/<task>/`: the PR, the run log lines, the `lvs`,
  PV and `df` reads, and for a data disk the `qm config`, `vgs` and plan excerpts.
- Sources: ADR 0017, Reconcile rules (the `created` row), Capacity; migration plan Tasks 2.4, 2.6, 2.10 (D40), D20,
  D31; ansible `roles/storage_vm/tasks/grow-volume.yml`, `homelab_storage/plan.py:78-91` (`no-space`).
- Lab: report `:351-359` (Check 7) and `:603-640` (F10); `storage-lab/b5-grow2.txt`, `b5-grow3-crash.txt`.
- Lab: `storage-lab/b5-grow3-retry.txt`, `b5/pause-grow.json`, `storage-lab/b7/f10-cfg0.txt` to `f10-cfg3.txt`.
