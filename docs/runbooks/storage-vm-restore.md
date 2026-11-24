# Storage VM restore

Restoring retained data that lives on the storage VM's `retained` disk (ADR 0017, Backups). The disk is one `.raw`
file in `apps/k3s-block`. TrueNAS snapshots replicate it to `usbbk/tn`, and restic uploads the replica off-site.
Also here: what to do when the storage VM's boot check fails.

Where commands run:
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve through the helper. ASCII only, no `$`,
  no single quotes in the row.
- `[P]`: root on pve (`$` works in a pve shell). `[T]`: TrueNAS. `[K]`: `k3s kubectl` on the master.
- `[R]`: root on VM300, the runner. `[W]`: the workstation.

Names:
- `R` = `/dev/disk/by-id/virtio-retained`, the PV of VG `retained` on the storage VM.
- `<image>` = the live retained file: `pvesm path k3s-block:<D1:placeholder_vmid>/<retained_volname>` on pve.
- `R()` = the restic wrapper in ansible `docs/backup-and-restore.md`, "Run restic by hand".

## Before you start

- **Ben OK** for every mutation: each scale, window, lock, shutdown, copy, tag and start.
- Outside every backup window. A step that touches `usbbk` holds `/run/lock/homelab-backup.lock`
  (`exec 9>/run/lock/homelab-backup.lock; flock -n 9`) and releases it well before 04:30 and Sunday 05:30.
- Pick a snapshot from a green backup run (ansible `docs/backup-and-restore.md`, "Restore paths").
- Free space: `[T]` `zfs get -Hp available,usedbysnapshots apps/k3s-block` shows room for a rollback copy of the
  image (a whole-disk restore), and `df -h /usbbk` shows room for the restore (`(not rehearsed)`).
- A deny syncWindow on every app whose writer is touched (`storage-vm-cutover.md` "Hold").

## Whole-disk restore

The whole `retained` disk goes back to an older snapshot. Every retained app loses what it wrote since. The hold in
step 3 is the only protection against the reconcile recreating later volumes empty (Ben chose this over a Git field or
an automatic ledger mirror).

1. **Lock, window, drain, record.**
   - Take the maintenance lock under this runbook's own owner and nonce, as in `storage-vm-cutover.md` "Lock":
     `[R]` `sh /run/homelab-cutover/lock.sh acquire storage-restore claude-code/storage-restore/<UTC ts>`, one row.
     **Ben OK.** `(not rehearsed)`
   - Add the deny syncWindow. Scale every retained writer to 0 and confirm each unstage, as in
     `storage-vm-rebuild.md` "Writer drain": the restore cuts I/O far longer than `replacement_timeout`.
   - Record the live fence tags: `[S]`
     `vgs --devices /dev/disk/by-id/virtio-retained --readonly --noheadings -o vg_tags retained`, every `fenced:*`
     entry. Lab B9 recorded `fenced:<node>:<bootID>` this way.
   - Record every node with the out-of-service taint: `[K]`
     `get nodes -o jsonpath='{range .items[*]}{.metadata.name} {.spec.taints}{"\n"}{end}'` `(not rehearsed)`.
   - Record whether the live VG already carries `hold_fence`. While automatic fencing is held, it does.
   - If it does not: `[S]` `vgchange --devices /dev/disk/by-id/virtio-retained --addtag hold_fence retained`.
     **Ben OK.** `(not rehearsed)`
2. **Shut down the storage VM and put the restored `.raw` in place.**
   - `[P]` `qm shutdown <D1:storage_vmid>`, then `qm status <D1:storage_vmid>` reads `stopped`. **Ben OK.**
     The lab used a graceful shutdown here.
   - Get the restored file: a replica snapshot mounted read-only (ansible `docs/backup-and-restore.md`, "One image
     from the replica", step 2), or a restic restore ("Off-site restic restore" below, steps 1-3).
   - `[P]` with the backup lock held, keep the current file as a rollback copy, copy byte for byte, then compare
     (ansible doc step 3; lab B9 Runbook step 2):
     ```sh
     live=$(pvesm path k3s-block:<D1:placeholder_vmid>/<retained_volname>)
     ls -ls "$live"
     cp --sparse=always "$live" "$live.pre-restore"
     cp --sparse=always <restored file> "$live"
     sha256sum <restored file> "$live"
     ```
     Expected: both sums equal. Keep `$live.pre-restore` until the restore is verified.
3. **Before booting, set the hold** from pve, without activating the VG (lab B9 Runbook step 3). **Ben OK.**
   ```sh
   dev=$(losetup --find --show "$live")
   vgchange --devices "$dev" --config 'activation{auto_activation_volume_list=[]}' --addtag hold_create \
     --addtag hold_fence --addtag fenced:<node>:<bootID> --deltag fenced:<old node>:<old bootID> retained
   vgchange --devices "$dev" -an retained
   losetup -d "$dev"
   losetup -j "$live"
   dmsetup ls
   ```
   - Steps 2 and 3 run in one pve shell: they share `$live` and `$dev`.
   - The two `vgchange` lines are marked (lab form plus --devices; not rehearsed).
   - Add one `--addtag` for each `fenced:*` tag recorded in step 1. Add one `--deltag` for each `fenced:*` tag in the
     image that was not recorded. Leave out either flag when there is none.
   - Expected: the VG UUID unchanged; `losetup -j` prints nothing; `dmsetup ls` shows no `retained-*` entry.
   - If `regen` was restored too, repeat this step for `regen`'s file and VG. The holds always go on `retained`, even
     for a regen-only restore: the reconcile and the fencer read holds from `retained` only. (Ben, 2026-11-16.)
4. **Boot the storage VM.** `[P]` `qm start <D1:storage_vmid>`. **Ben OK.**
   Expected (lab B9): `rtslib-fb-targetctl` and `storage-fencer` active within about 20 s; the `fenced` set restored
   from the tags; a fenced worker stays fenced and keeps its taint. A volume created after the snapshot logs
   `Could not create StorageObject <id> ... skipped`, and its target comes back empty (F17).
5. **Reconcile through the storage workflow, under this runbook's lock** (D51). The playbook needs the vault
   password, the SSH key and the Proxmox token, which only the workflow has, so the run adopts the held lock.
   - `[W]` `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main -f held_lock_owner=<the owner from
     step 1>`, then read the run (`gh run view <run> -R Starktastic-Homelab/ansible --log-failed`). **Ben OK.**
     `(not rehearsed)` in production; the lab ran `storage.yml` by hand under the lab lock.
   - The run checks that the input is a `claude-code/storage-restore/<UTC ts>` owner and that `operation.json` holds
     it under operation `storage-cutover:storage-restore` (step 1's `acquire`), then reconciles under it. It never takes or releases the lock. It also prints the lock-held warning and skips
     the dry-run: both are expected on this path.
   - Expected: the run fails as designed. Each inventory entry with no LV is refused: `refused: <id>: hold-create`
     (not `lv-missing`: the restored ledger never knew it). The log has `hold_create set, <n> creates refused` (F16's
     log line, Task 0.2).
   - `hold_create` also holds back grows. So `hold_create set, 0 creates refused` can mean a held grow: compare each
     inventory `size` with `lvs --devices /dev/disk/by-id/virtio-retained --readonly --units b -o lv_name,lv_size
     retained` before step 6.
   - Resolve every missing volume from an older backup, or, with Ben's OK, drop the entry from the inventory (lab B9:
     a volume created after the snapshot with no data). Re-run until only the `hold_create set, 0 creates refused`
     line is left.
   - After each run, `[R]` read the holder without the nonce, as in `storage-vm-cutover.md` "Stale lock" step 1.
     Expected: the second field is the owner from step 1, so the failed run left the lock with this runbook.
     (`maintenance_lock_op.sh` takes CI owners only and refuses this one.)
   - **Abort** if any worker carries the out-of-service taint without a matching `fenced:` tag.
   - **F17:** the reconcile neither flags nor removes targets for volumes created after the snapshot. The LIO
     configuration is on the root disk, which the restore does not roll back. List them: `[S]` `targetcli ls /iscsi`
     against the `ledger:<id>:created` tags. Remove each empty one by hand, under the LIO lock. **Ben OK.**
     `(not rehearsed)`: `flock /run/lock/storage-lio targetcli /iscsi delete iqn.2026-11.net.starktastic.storage:<id>`,
     then `flock /run/lock/storage-lio targetcli saveconfig`.
6. **Clear `hold_create`, put `hold_fence` back, release.**
   - `[S]` `vgchange --devices /dev/disk/by-id/virtio-retained --deltag hold_create retained`. **Ben OK.**
     `(not rehearsed)`; lab B5 and B9 cleared it the same way, unscoped.
   - Put `hold_fence` back to the state recorded in step 1. While automatic fencing is held (Ben, 2026-11-21), it
     stays set: change nothing. Only if step 1 recorded no `hold_fence`, delete it with `--deltag hold_fence`.
   - The same dispatch as in step 5, **Ben OK**. Expected: green, `failed=0`, and the lock still held by this
     runbook's owner (the same `[R]` read).
   - Release the lock: `[R]` `sh /run/homelab-cutover/lock.sh release storage-restore
     claude-code/storage-restore/<UTC ts>` (step 1's suffix and owner), one row; expected `released`. This is the
     "another `claude-code/` owner" row of `storage-vm-cutover.md` "Stale lock" step 2.
   - Dispatch `storage.yml`, now with no `held_lock_owner`. **Ben OK.** `[W]` `gh workflow run storage.yml -R
     Starktastic-Homelab/ansible --ref main` `(not rehearsed)`. Expected: a green run, so anything skipped under the
     lock applies now, not at the next hourly run.
   - Remove the syncWindow. Scale the writers back up. **Ben OK** for each.
   - Expected: each app starts at the snapshot's data. Delete `$live.pre-restore` once Ben has verified the apps.

## Single app from a ZFS clone

One app's files from a replica snapshot, with the live disk untouched. Hold `/run/lock/homelab-backup.lock`
throughout. Clone into `usbbk/restore-<date>`, never under `usbbk/tn`, and destroy the clone before the next `:30`
replication. Gate C1 runs this once (migration plan Task 4.C1).

Every step is `[P]`. The ZFS clone and `losetup` of a clone are `(not rehearsed)`: the lab restored from a
`cp --sparse=always` copy instead (lab B9 Step 1).

1. `zfs load-key` if needed: `[ "$(zfs get -H -o value keystatus usbbk/tn/k3s-block)" = available ] || zfs load-key -L
   file:///etc/homelab-backup/apps.key usbbk/tn/k3s-block` (ansible doc, "One image from the replica").
2. `zfs list -t snapshot -o name,creation -r usbbk/tn/k3s-block | tail`, then
   `zfs clone usbbk/tn/k3s-block@auto-<date> usbbk/restore-<date>`. **Ben OK.**
3. `dev=$(losetup --find --show <clone mountpoint>/images/<D1:placeholder_vmid>/<retained_volname>)`, read-write.
4. `vgimportclone -n restore_<date> $dev`, then `vgchange -ay restore_<date>` (lab B9 Step 1). Expected: the LVs of
   the clone, active under the new VG name. The live `retained` VG is untouched.
5. `mkdir -p /mnt/restore-<id>` and `mount -o ro /dev/restore_<date>/<id> /mnt/restore-<id>`. Mounting `ro` lets the
   journal replay on the writable clone. The lab mounted its copy `ro,noload`.
6. Copy the files out to `/usbbk/restore/<id>-<date>/`. Take each SQLite database with its `-wal` file (and `-shm`):
   in the lab the WAL held committed rows. Putting them into the live app is app-specific and Ben's call: the app at 0,
   the files copied in through a one-off pod on its claim `(not rehearsed)`.
7. Unwind: `umount /mnt/restore-<id>`, `vgchange -an restore_<date>`, `losetup -d $dev`,
   `zfs destroy usbbk/restore-<date>`. **Ben OK** for the destroy.
   Expected (lab B9): no loop device, no `restore_*` dm entry, the kernel log only loop and ext4 lines, pstore empty.
   LVM may print `fd 9 leaked` warnings (the lock fd); they are harmless.

## Off-site restic restore

The same single-app restore, from the Storage Box. It downloads the whole retained image.

1. `[P]` `R snapshots --tag daily`. Pick a snapshot ID from a green run.
2. `[P]` `df -h /usbbk`. Expected: free space above the image's apparent size.
3. `[P]` with the backup lock held:
   `R restore <snapshot-id> --target /usbbk/restore --sparse --include
   /srv/backup-src/k3s-block/images/<D1:placeholder_vmid>/<retained_volname>` (ansible doc, "One image from restic";
   drilled on 2026-11-13 for other images, never for the retained image).
4. Then "Single app from a ZFS clone" steps 3-7 on
   `/usbbk/restore/srv/backup-src/k3s-block/images/<D1:placeholder_vmid>/<retained_volname>`, with
   `rm` of the restored file in place of the `zfs destroy`. **Ben OK.**
5. The `regen` image is excluded from restic by one path, so it never restores off-site.

## Boot check failed

`StorageBootCheckFailed` (Task 2.4) fires when the boot check's textfile reads `storage_boot_check_ok 0`.

A reconcile that logs `error: storage VM still booting: rtslib-fb-targetctl is not settled` was refused, because the
boot restore was still running or queued, or `systemctl show` gave no answer. It changed nothing and the run fails.
Wait until `[S]` `systemctl show -p LoadState,ActiveState,Job rtslib-fb-targetctl` reads `loaded`, one of `active`,
`failed` or `inactive`, and an empty `Job=` `(not rehearsed)`. Then, by where the refusal came from:
- under this runbook's `held_lock_owner` ("Whole-disk restore" step 5), in either step: the lock is this runbook's
  and stays held. Repeat that step;
- otherwise, in `Dry-run before the lock`: no lock was taken. Dispatch `storage.yml` again, **Ben OK**;
- otherwise, in `Reconcile under the lock` (the storage VM rebooted after the dry run): the run keeps the lock (D31).
  Release it as in ansible `docs/maintenance-lock-release.md`, then dispatch again, **Ben OK** for each.

A unit that stays `activating` is a stalled boot: follow step 1 below.

- D7: the alert needs Prometheus and Alertmanager, which live on `regen` after wave 1. A storage VM that is down takes
  them with it. Then only the healthchecks.io Watchdog dead-man check sees it, after about 10 minutes (ADR,
  Consequences, "Silent storage-VM failure"). For a VM that is down, see `storage-vm-rebuild.md` "VM down".

1. `[S]` `journalctl -b -u rtslib-fb-targetctl --no-pager | tail -60` `(not rehearsed)`. Look for:
   - `error: <id>: LUN 0 is not bound to /dev/<vg>/<id>`: a ledgered LV is missing, or its VG did not activate. The
     target is restored with ACLs but no LUN (lab B5 Check 4);
   - `error: VG <vg> is missing`: a data disk is gone, renamed, or stalled. The other VG's targets still serve;
   - `Could not create StorageObject <id> ... skipped`: the device for that target does not exist.
2. A VG missing: `[P]` `qm config <D1:storage_vmid> | grep -E "^virtio[12]:"` shows both data volids. A stalled
   backend holds the whole boot (F24); wait for it, do not reset with `module.async_probe=1`.
3. A ledgered LV missing: never recreate it. Follow `storage-vm-crashed-create.md` "lost (ledgered, LV missing)",
   or "Whole-disk restore" above.
4. After the cause is fixed: one `storage.yml` run re-exports every target. **Ben OK.**
   `[W]` `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main` `(not rehearsed)`.
   Expected (lab B5): `failed=0`, every LUN back, `storage_target_missing` 0.
5. N1: `rtslib-fb-targetctl` may stay `failed` after that, by design: the reconcile does not start it while sessions
   exist (`warning: rtslib-fb-targetctl is inactive but sessions exist (...); not starting it`). The next boot starts
   it normally. The boot check runs again only then.

## Undo

- Whole-disk restore, before step 6: shut the storage VM down, copy `$live.pre-restore` back over `$live`, compare
  sha256, boot. The holds set in step 3 were set on the restored file only. **Ben OK.**
- Single-app and off-site restores change nothing live until files are copied in; unwind as in step 7.

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/<task>/` (Gate C1: `evidence/4.C1/`): the
  recorded tags and taints, the sha256 lines, the `vgchange` output, the run logs and the refusal lines.
- Sources: ADR 0017, Backups (Whole-disk restore as corrected by Task 0.4 row 11, Single-app restore); migration plan
  Task 0.2 (F16), Task 4.C1, D7; ansible `docs/backup-and-restore.md` "Restore paths" (origin/main `b59841a`).
- Lab: report `:781-813` (B9 Steps 1-2); `storage-lab/b9/notes.md`; `storage-lab/b5/notes.md` Check 4 (boot check).
- Lab: `storage-lab/b11/restic-9970.txt` (the lab image was excluded from restic, so the off-site leg never ran).
