# Storage VM expiry

How a removed volume is deleted, and what to do when that goes wrong (ADR 0017, Deletion). Merging the PR that
removes an inventory entry is Ben's approval to delete it. The daily `storage-expiry.yml` deletes it 3 days later.

Where commands run:
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve through the helper. ASCII only, no `$`,
  no single quotes in the row.
- `[K]`: `k3s kubectl` on the master. `[N]`: root on a worker. `[W]`: the workstation (`gh`).

Names: `<id>`, `<vg>` and its PV `<pv>` (`/dev/disk/by-id/virtio-retained` or `/dev/disk/by-id/virtio-regen`).

## Before you start

- **Ben OK** for every dispatch, delete and lock release.
- A refused or failed expiry fails the run, and a failed run keeps the maintenance lock (D31). While it is held, every
  `storage.yml` run skips. Read the run's log, then release the lock as in ansible
  `docs/maintenance-lock-release.md`, with Ben's OK. That doc has no section for the storage workflows; their owner
  shape and stage `acquired` match its ansible deploy case (3.6).
- Outside every backup window (ansible `docs/backup-and-restore.md`, "Schedules") for a manual dispatch; the daily run
  is scheduled outside them.
- No writer is touched, so no deny syncWindow.

## How expiry decides

1. **Removal.** A `storage.yml` run that finds a `created` LV with no inventory entry keeps its target exported and
   tags the LV `pending-delete:<unix time>`. `StoragePendingDelete` fires. Re-adding the entry clears the tag.
   - **More than 2 removals.** apps CI refuses more than 2 in one change unless the PR carries the
     `storage-removals-approved` label. The label passes apps CI only; the storage side has its own brake
     (`max_removals`, 2 per run). Two ways through, Ben picks:
     - split the change into PRs of at most 2 removals each, and merge the next only after a `storage.yml` run has
       tagged the previous one's LVs `pending-delete` (a tagged LV no longer counts);
     - or, for a labelled PR: after the merge, dispatch one run with the brake raised, **Ben OK**, `[W]`
       `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main -f max_removals=<n>` `(not rehearsed)`,
       with `<n>` the number of removals (a positive integer below 1000). It applies to that run only; the next run
       uses 2 again. Expected: green, every removed LV tagged.
     Until one of these is done, every run refuses `removal-brake` in the dry run, takes no lock and applies nothing
     for any entry (creates and grows included); `StorageReconcileFailing` fires after 5 h.
   - **A claim still bound.** apps CI refuses removing an entry whose claim git still binds: an app's values (by
     namespace, including derived StatefulSet claims and `volumeName` ids) or a committed manifest still names it
     (`<id>: removed, but <file> still binds <ns>/<claim>; remove the binding first`). The label does not cover this.
     Remove the binding first, in an earlier PR or in the same one.
2. **The daily run.** `storage-expiry.yml` runs at 10:05 UTC, outside every backup window. Before the lock, the step
   `Check that k3s answers before the lock` (`storage-preflight.yml`) fetches and validates the inventory from apps
   `main`, then asks k3s on the first master for `/readyz`:
   - k3s missing or not ready (a rebuild before its deploy): a green skip,
     `::warning::k3s does not answer on the first master (a rebuild before its deploy?); skipping without the lock, the
     next run retries`;
   - a fetch or validate error (a GitHub outage, a missing inventory file), an unreachable master, or any other error:
     the run fails, without the lock. A missing inventory file never reads as an empty inventory.

   Then it tries the lock once; a held lock skips the day
   (`::warning::Maintenance lock is held; skipping, the next daily run retries`).
3. **Candidates** (`storage-reconcile expire-candidates`): LVs whose newest `pending-delete` tag is older than 3 days
   (259200 s). There are none at all while `retained` carries `hold_create`, or while either VG cannot be read.
4. **Back in the inventory.** A candidate that is in the inventory on `main` again is never expired:
   `WARNING: <id> is pending-delete but in the inventory on main; not expired.`
5. **In-use checks**, per candidate. Each one must pass; any error counts as in use:
   - the Kubernetes API answers;
   - no VolumeAttachment names a PV whose `volumeHandle` is `<id>` for driver `org.democratic-csi.node-manual`. This
     also catches a migration copy pair;
   - no Pod mounts a claim of those PVs (found through each PV's `claimRef`);
   - the LIO target has no session: each NodeACL's `info` reads no active session. A read error counts as in use.
6. **Delete.** It deletes the PVCs, then the PVs, then runs `storage-reconcile expire --id <id>` on the storage VM.
   That re-checks age, hold and sessions under the LIO lock, then: delete the target, save, `blkdiscard`, `lvremove`,
   and one `vgchange` that drops `ledger:<id>:*` and adds `tombstone:<id>`.
7. **Never back.** A tombstoned id is refused forever: `refused: <id>: tombstoned`. A new volume takes a new id.

## Half-expiry recovery through storage.yml

F3, F4. The order is target, save, `blkdiscard`, `lvremove`, tombstone. If `expire` fails after the target delete, the
volume is half-expired: PVC, PV and target gone; LV, ledger tag and `pending-delete` tag kept; no tombstone. No data is
lost.

A retry is refused as busy: the sessions of a deleted target cannot be read, and that counts as in use. It stays
refused until a `storage.yml` run re-exports the target.

1. `[W]` read the failed expiry run: `gh run view <run id> -R Starktastic-Homelab/ansible --log | grep -E
   "error: expire|still in use|blkdiscard|lvremove"` (one row) `(not rehearsed)`.
   Expected: `error: expire <id>: ...` naming the failed command.
2. `[S]` confirm the half state `(not rehearsed)`:
   - `lvs --devices <pv> --readonly --noheadings -o lv_name,lv_tags <vg>` shows `<id>` with its `pending-delete` tag;
   - `vgs --devices <pv> --readonly --noheadings -o vg_tags <vg>` shows `ledger:<id>:created` and no `tombstone:<id>`;
   - `targetcli ls /iscsi` has no target for `<id>`;
   - `[K]` no PV `<id>`.
   If the LV is gone too, this is the tombstone gap: follow `storage-vm-crashed-create.md` "lv-missing after a failed
   expiry: the lvremove/tombstone gap" instead.
3. Release the failed run's lock (see "Before you start").
4. Fix the cause the log named. The F4 cause (`blkdiscard` refusing a signed device under a pty) is fixed in code:
   `host.run` gives every command `/dev/null` as stdin.
5. Dispatch `storage.yml`. **Ben OK.** `[W]` `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main`.
   Expected: green; the target for `<id>` is back (export of a `created` LV not in the inventory). The tag stays.
6. Let the next daily expiry run, or dispatch it. **Ben OK.**
   `[W]` `gh workflow run storage-expiry.yml -R Starktastic-Homelab/ansible --ref main`.
   Expected: the candidate passes the checks (its PV and PVC are already gone), and `expire` finishes: LV and target
   gone, `tombstone:<id>`, run green (lab B5 expiry run 3).

## Expiry refused: VA, session or copy pair

`<id> is still in use; nothing deleted.` (the assert in ansible `roles/storage_vm/tasks/expire-volume.yml`). The run
fails after the cleanup and keeps the lock.

1. `[W]` read which clause failed in the run log: the first failing assertion is printed. The order is the session,
   then the VolumeAttachment, then the Pods.
2. Find the user `(not rehearsed)`:
   - `[K]` `get volumeattachments -o jsonpath='{range .items[*]}{.metadata.name} {.spec.source.persistentVolumeName}
     {.spec.nodeName}{"\n"}{end}'`. A migration copy pair shows as PV `migrate-src-<id>` or `migrate-dst-<id>`, whose
     `volumeHandle` is `<id>`;
   - `[K]` the Pods in the claim's namespace that mount the claim;
   - `[N]` `iscsiadm -m session` on each worker. A hand login with no Pod and no VolumeAttachment blocks the expiry
     too (lab B5).
3. Each user is either a mistake or a reason to keep the volume. Ben decides:
   - keep it: re-add the entry to the inventory (the next run clears the tag);
   - remove the user: delete the copy pair's Job, PVCs and PVs (`storage-vm-cutover.md` "Teardown and
     verify-teardown"), or log out the hand session
     (`iscsiadm -m node -T iqn.2026-11.net.starktastic.storage:<id> -p <bridge address>:3260 -u`, then `-o delete`).
     **Ben OK** for each.
4. Release the lock, then let the next daily run expire it.

## First production expiry check

Task 3.8 Steps 7-8: the F1 canary is the first volume removed in production, and its expiry gates Part 4.

1. Writer off first, and confirm: no Pod, no VolumeAttachment on the canary, no iSCSI session to its target.
2. The removal PR (the inventory entry, the writer manifest, its `kustomization.yaml` line). One removal, so no
   override label. **Ben OK.**
   Expected: ArgoCD prunes the writer. The PV and PVC stay (`Prune=false,Delete=false`). `storage.yml` tags the LV
   `pending-delete` with today's time, the target stays exported, and `StoragePendingDelete` fires.
3. Three days later, after the first daily run once the tag is more than 3 days old (read-only). Expected:
   - the `storage-expiry.yml` run is green;
   - `[S]` `lvs --devices /dev/disk/by-id/virtio-regen --readonly regen` has no canary LV;
   - `[S]` `vgs --devices /dev/disk/by-id/virtio-regen --readonly --noheadings -o vg_tags regen` has
     `tombstone:<canary id>` and no `ledger:<canary id>:*`;
   - `[S]` `targetcli ls /iscsi` has no canary target;
   - `[K]` the canary PV and PVC are gone;
   - `StoragePendingDelete` has resolved;
   - the next `storage.yml` run has no `lv-missing` line.
4. If any check fails: "Half-expiry recovery through storage.yml" above, and the crashed-create runbook's tombstone
   gap section (D12), before Part 4.

## Undo

- Before the expiry: revert the removal PR (re-add the entry). The next `storage.yml` run clears `pending-delete`.
- After the expiry: none. The data is discarded and the id is tombstoned. Snapshots taken before the deletion stay in
  the `usbbk` replica for 2 weeks; restore into a new id as in `storage-vm-restore.md`.

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/<task>/` (Task 3.8: `evidence/3.8/expiry.txt`):
  the run URLs, the refusal lines, the `lvs`, `vgs` and `targetcli` reads before and after.
- Sources: ADR 0017, Deletion and Reconcile rules; migration plan Task 3.8, D31; ansible
  `roles/storage_vm/tasks/expire.yml`, `expire-volume.yml`, `storage-expiry.yml`,
  `homelab_storage/reconcile.py:313-361`.
- Lab: report `:322-350` (Check 5); `storage-lab/b5-expiry1.txt`, `b5-expiry2.txt`, `b5-expiry3.txt`.
- Lab: `storage-lab/b5-expiry-nolock.txt`, `b5-hold.txt`, `b5/va.yaml`, `b5/copy.yaml`.
