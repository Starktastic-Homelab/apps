# Ledger refusals: crashed-create, orphan, lost

What to do when the reconcile refuses an entry because the LVM ledger and the LVs disagree (ADR 0017, Reconcile
rules; lab F3). The ledger is a tag set on each VG: `ledger:<id>:creating`, `ledger:<id>:created` and
`tombstone:<id>`. The reconcile never fixes these by itself. Each fix here is a manual tag or LV operation.

Where commands run:
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve through the helper. ASCII only, no `$`,
  no single quotes in the row.
- `[R]`: root on VM300, the runner. `[K]`: `k3s kubectl` on the master. `[W]`: the workstation (`gh`).

Names: `<vg>` is `retained` or `regen`; `<pv>` is its PV, `/dev/disk/by-id/virtio-retained` or
`/dev/disk/by-id/virtio-regen`.

## Before you start

- **Ben OK** for every tag change and every `lvremove`. Inspect first; never delete what you have not read.
- Read the refusal from the run log: `[W]` `gh run view <run id> -R Starktastic-Homelab/ansible --log | grep -E
  "refused:|error:"` (one row) `(not rehearsed)`. The lines read `refused: <id>: <reason>` (lab B5 runs).
- The maintenance lock. Which refusals fail the run before the lock depends on the reason:
  - `lv-missing` is in `BLOCKING` (`reconcile.py:27`), so the dry run fails first and no lock is taken;
  - `crashed-create` and `orphan` are not: the apply runs, exports every live target, then fails. **That run keeps
    the lock** (D31). Read its log, then release the lock as in ansible `docs/maintenance-lock-release.md`, with Ben's
    OK. That doc has no section for `storage.yml`; its owner shape (`Starktastic-Homelab/ansible/<run>/<attempt>`)
    and stage `acquired` match its ansible deploy case (3.6).
- Do the tag work while no `storage.yml` run is in progress: take the lock, **Ben OK**, `[R]`
  `sh /run/homelab-cutover/lock.sh acquire storage-ledger-<id> claude-code/storage-ledger-<id>/<UTC ts>` (one row)
  `(not rehearsed)`, and release it after with `lock.sh release storage-ledger-<id> <owner>`. Then dispatch
  `storage.yml`, **Ben OK**, `[W]` `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main`
  `(not rehearsed)`, so "the next run" below is now, not up to about 3 h away (D29). `lock.sh` is staged
  only by migration plan Task 4.0 Step 9; stage it first if needed. Its operation reads
  `storage-cutover:storage-ledger-<id>` (the prefix is hardcoded).
- Outside every backup window (ansible `docs/backup-and-restore.md`, "Schedules"). A manual `storage.yml` dispatch does
  not skip inside one; only the scheduled runs do (D29).
- No writer is touched, so no deny syncWindow.

Every read below is `(not rehearsed)` in this scoped form:
- the VG tags: `vgs --devices <pv> --readonly --noheadings -o vg_tags <vg>`;
- the LVs: `lvs --devices <pv> --readonly --noheadings --units b -o lv_name,lv_size,lv_tags <vg>`;
- the target: `targetcli ls /iscsi/iqn.2026-11.net.starktastic.storage:<id>`.

## crashed-create

`refused: <id>: crashed-create`: the VG still has `ledger:<id>:creating`. A create stopped between writing that tag
and `ledger:<id>:created`. The LV may or may not exist; for an `origin: new` entry `mkfs` and the marker may or may
not have run. No target exists yet: the target comes after `created`. The reconcile never retries it.

1. `[S]` read the VG tags and the LVs. Note whether `<id>` has an LV and its size.
2. If the LV exists, inspect it read-only: `[S]` `blkid -p /dev/<vg>/<id>` and
   `dumpe2fs -h /dev/<vg>/<id> 2>/dev/null | grep -E "^(Filesystem features|Filesystem state)"`.
   A create never held app data: the app consumes the volume only after `created`.
3. Ben picks one:
   - **Remove and let it create again** (the lab path). **Ben OK.** `[S]`
     `lvremove --devices <pv> -y <vg>/<id>` (only if the LV exists), then
     `vgchange --devices <pv> --deltag ledger:<id>:creating <vg>` `(not rehearsed)`; the lab ran the same two
     commands unscoped (lab B5 Check 5, crash mid-create).
     The next `storage.yml` run creates the volume from scratch.
   - **Adopt by tag**, only when step 2 shows the create finished up to the marker (`origin: new`) or the raw LV is
     complete (`origin: migrated`). **Ben OK.** `[S]`
     `vgchange --devices <pv> --deltag ledger:<id>:creating --addtag ledger:<id>:created <vg>` `(not rehearsed)`.
     One `vgchange`, so it is one metadata commit. The next run exports the target.
4. Expected: the next `storage.yml` run is green, with no `refused:` line for `<id>`.

## orphan

`refused: <id>: orphan`: an LV exists with no ledger tag. It can be a hand-made LV, a rename, or an LV from an older
ledger. Adopting it is a manual tag operation after inspection.

1. `[S]` read the VG tags and the LVs, then inspect the LV as in "crashed-create" step 2. Check the id in the inventory
   on apps `main` (present or not, its `class` and `size`).
2. Ben picks one:
   - **Adopt.** The LV is the right volume for an inventory entry, in the right VG, at least the inventory size.
     **Ben OK.** `[S]` `vgchange --devices <pv> --addtag ledger:<id>:created <vg>` `(not rehearsed)`.
     The next run exports it. An `origin: new` volume's guard then checks its marker.
   - **Remove.** It holds nothing Ben wants. **Ben OK.** `[S]` `lvremove --devices <pv> -y <vg>/<id>`
     `(not rehearsed)`; the lab removed its test orphan the same way, unscoped (lab B5 Check 5).
   - **Rename back**, when a rename made it (the lab's `lost + orphan` case): `lvrename` to the ledgered name.
     `(not rehearsed)`
3. Expected: the next run has no `orphan` line.

## lost (ledgered, LV missing)

`refused: <id>: lv-missing`: the ledger says `ledger:<id>:created`, but there is no LV. It blocks the dry run, so every
`storage.yml` run fails before the lock and changes nothing, other entries included, until this is fixed. The target,
if it exists, has no LUN 0, so nothing can mount it. **Never recreate the LV.**

1. `[S]` read the VG tags and the LVs of **both** VGs. Look for the data under another name (a rename) or in the other
   VG.
2. Check whether this is the expiry gap: the id is not in the inventory on `main`, and the last
   `storage-expiry.yml` run failed after `lvremove`. Then go to the next section.
3. Otherwise the data on this disk is gone. Ben picks one:
   - **Rename back** if step 1 found it (lab B5: `lvrename` back, then a green run). `(not rehearsed)`
   - **Restore** from a backup: `storage-vm-restore.md` "Whole-disk restore", or one volume through
     "Single app from a ZFS clone" into a new id.
   - **Give it up**: remove the entry from the inventory and write the tombstone as in the next section, step 4. A
     deleted id never comes back; a new volume takes a new id.
4. Expected: the next dry run has no `lv-missing` line.

## lv-missing after a failed expiry: the lvremove/tombstone gap

D12, accepted. The expiry runs `lvremove` and the tombstone `vgchange` as two commands (`reconcile.py:353-356`). A
failure between them leaves `ledger:<id>:created` with no LV and no tombstone. Then:

- every `storage.yml` dry run fails on `lv-missing` (the entry is no longer in the inventory, so other entries still
  plan, but nothing applies);
- the `storage-expiry.yml` run that failed keeps its lock (D31), so it also stops later runs.

1. Read the expiry run's log: `[W]` `gh run view <run id> -R Starktastic-Homelab/ansible --log | grep -E
   "expire|lvremove|vgchange|error:"` (one row) `(not rehearsed)`.
   Expected: `lvremove` ran, and the error is at or after the tag change.
2. Release that run's lock as in ansible `docs/maintenance-lock-release.md`, with Ben's OK.
3. `[S]` confirm the gap:
   - the LVs: no `<id>`;
   - the VG tags: `ledger:<id>:created` and no `tombstone:<id>`;
   - the target: gone (`targetcli` reports no such path);
   - `<id>` is not in the inventory on apps `main`.
4. Write the tombstone by hand, in one `vgchange`, as the expiry would have. **Ben OK.** `[S]`
   `vgchange --devices <pv> --deltag ledger:<id>:created --addtag tombstone:<id> <vg>` `(not rehearsed)`.
   Expected: the VG tags show `tombstone:<id>` and no `ledger:<id>:*`.
5. Dispatch `storage.yml`, **Ben OK**: `[W]` `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main`.
   Expected: green, and no `lv-missing` line.
6. If the id ever comes back in the inventory, the run refuses it: `refused: <id>: tombstoned` (lab B5).

## Undo

- An adopt: `vgchange --devices <pv> --deltag ledger:<id>:created <vg>` while no app has used the volume, which makes
  it an orphan again `(not rehearsed)`. After an app wrote to it, there is no undo.
- A tombstone written by mistake while the LV still exists: bring it to Ben. Do not delete the tag by hand while any
  run is in progress.
- An `lvremove` has no undo except a backup restore.

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/<task>/`: the refusal lines, the VG tags and LVs
  before and after, the inspection output, Ben's choice and the next run's result.
- Sources: ADR 0017, Reconcile rules, Open questions (the `lvremove` and tombstone gap); migration plan D12, D31;
  ansible `roles/storage_vm/files/homelab_storage/plan.py:49-75`, `reconcile.py:27,338-361`.
- Lab: report `:322-350` (Check 5); `storage-lab/b5/notes.md` Check 5; `storage-lab/b5-crash.txt`, `b5-crash-retry.txt`.
- Lab: `storage-lab/b5-orphan.txt`, `b5-lost-orphan.txt`, `b5-tombstone.txt`, `b5/pause-create.json`.
