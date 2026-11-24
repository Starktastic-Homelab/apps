# Read-only filesystem on a retained volume

What to do when a storage-VM volume went read-only on its worker (ADR 0017, Qualification Check 8; lab F9, F13).
Every volume is ext4 with `errors=remount-ro` and MMP, so an I/O error stops writes instead of corrupting data.

Where commands run:
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve through the helper. ASCII only, no `$`,
  no single quotes in the row.
- `[K]`: `k3s kubectl` on the master. `[N]`: root on a worker, `qm guest exec <worker vmid>`.

Names: `<id>` is the inventory id. The LV is `/dev/<vg>/<id>`, the target IQN is
`iqn.2026-11.net.starktastic.storage:<id>`, and the portal is `<bridge address>:3260`.

## Before you start

- **Ben OK** for every scale, window change, login and `e2fsck`.
- Fix the cause first. The target must answer again before any restage (`storage-vm-rebuild.md` "VM down", or the
  NFS backend).
- A deny syncWindow on the app, as in `storage-vm-cutover.md` "Hold", so Argo self-heal does not undo the scale.
- The maintenance lock for the offline `e2fsck`: steps 4-8 of that section hold it, so no `storage.yml` grow or
  expiry and no other lock user runs while the repair writes retained data or an LVM snapshot uses VG space. The
  restage alone needs no lock: it only scales the app.
- Outside every backup window for the offline `e2fsck`. The restage alone may run in a window if the app is down
  anyway.

## Symptoms

- The pod crash-loops: for example `unable to open database file`, or `Read-only file system`.
- `[N]` `journalctl -k --since -30min --no-pager | grep -iE "EXT4|I/O error|session recovery"` on the worker shows
  some of these (lab B6, B7, B8):
  - `session recovery timed out after 120 secs`;
  - `I/O error, dev sdX ... WRITE`;
  - `Aborting journal on device sdX-8`;
  - `EXT4-fs (sdX): Remounting filesystem read-only`.
- Causes seen in the lab: a storage VM outage longer than `replacement_timeout` (120 s, F9), an NFS export
  withdrawal under a data disk (B8), and a fence of a worker that was still alive (B6).
- A stall shorter than 120 s does not do this: I/O blocks, then resumes with no error (B8 stall legs).

## Restage

A same-node pod delete does **not** restage (F13): kubelet reuses the read-only global mount, and the new pod fails
the same way. Scale to 0, confirm the unstage, then scale up.

1. Hold the app (deny syncWindow). **Ben OK.**
2. `[K]` scale the writer to 0 (`scale deploy`, `scale sts`, or the operator CR's `replicas`, as in
   `storage-vm-cutover.md` "Hold"). **Ben OK.** `(not rehearsed)`
3. Confirm the unstage `(not rehearsed)`:
   - `[K]` no pod mounts the claim;
   - `[K]` no VolumeAttachment names PV `<id>`:
     `get volumeattachments -o jsonpath='{range .items[*]}{.spec.source.persistentVolumeName}{"\n"}{end}'`;
   - `[N]` `iscsiadm -m session` on that worker lists no session for the IQN.

   Expected: all three within seconds (lab: unstage in 5 s, session logged out). If the unstage hangs, a hung
   unmount can hold the volume's lock for up to 15 min (`MOUNT_DEFAULT_TIMEOUT`). Wait; never force-detach.
4. Scale back to the recorded replicas, then lift the window. **Ben OK.**
5. Expected on the worker: `MMP interval 42 higher than expected, please wait` (about 42-44 s, up to about 720 s on
   slow storage), then `mounting fs with errors, running e2fsck is recommended`, then a read-write mount. The app
   starts with its data at the last acknowledged write (lab: `count=2454 max=2454 contiguous=True`).
6. The ext4 error flag stays set. Record the volume for "Offline e2fsck of an error-flagged filesystem".

## Offline e2fsck of an error-flagged filesystem

D11: at the next drained window, after a copy of the LV, with Ben's OK. It writes to retained data.

Rehearsed only in the F21 form: an `e2fsck -fn` and then `-fy` on two lab filesystems whose error flag dated from
11-17. The F9 rehearsal never ran (lab B10 notes, B11 readiness list).

1. **Find flagged filesystems** (read-only). `[S]`
   `dumpe2fs -h /dev/<vg>/<id> 2>/dev/null | grep -E "^(Filesystem state|FS Error count|First error)"`
   `(not rehearsed)`.
   Expected for a flagged one: `Filesystem state: clean with errors` and `FS Error count: 1` or more, as in the lab.
2. **Drain** the app as in "Restage" steps 1-3. It stays at 0 until step 7.
3. **Read-only check on the storage VM** (lab form). `[S]` `blockdev --flushbufs /dev/<vg>/<id>`, then
   `e2fsck -fn /dev/<vg>/<id>`. Expected: `Warning! /dev/<vg>/<id> is in use.` (LIO holds it open), passes 1-5, and
   exit 0. Any error it reports goes to Ben before step 5. The lab ran it with `-F` too.
4. **Lock, then the copy** (D11). The maintenance lock is `FREE`; take it, **Ben OK**, `[R]`
   `sh /run/homelab-cutover/lock.sh acquire storage-fsck-<id> claude-code/storage-fsck-<id>/<UTC ts>` (one row)
   `(not rehearsed)`. Expected: one line `storage-cutover:storage-fsck-<id> <owner> <created_at>` (the prefix is
   hardcoded). `lock.sh` is staged only by migration plan Task 4.0 Step 9; stage it first if needed.
   For the copy, Ben picks one `(not rehearsed)`:
   - a TrueNAS snapshot of `apps/k3s-block` taken after the drain. It holds the whole disk, crash-consistent, and
     costs no VG space;
   - or a full-size LVM snapshot in the same VG:
     `lvcreate --devices <PV of vg> -s -L <LV size>b -n <id>-prefsck <vg>/<id>`. It needs that much VG free space;
     the snapshot reserve keeps room for the largest volume. Undo is in "Undo" below: the target comes off first.

   Record which, and its name, in the evidence.
5. **Repair through a worker** (lab form). LIO holds the LV open, so the lab repaired through a manual login on a
   worker. `[N]` **Ben OK** for each command `(not rehearsed)` in this production form. Each line is one
   `qm guest exec` argv on the worker, so there are no shell variables: write the values out before you run it
   (`<iqn>` is `iqn.2026-11.net.starktastic.storage:<id>`, `<addr>` is `<bridge address>:3260`, `<dev>` is
   `/dev/disk/by-path/ip-<addr>-iscsi-<iqn>-lun-0` with both filled in):
   ```sh
   iscsiadm -m node -T <iqn> -p <addr> -o new
   iscsiadm -m node -T <iqn> -p <addr> -o update -n node.startup -v manual
   iscsiadm -m node -T <iqn> -p <addr> -l
   e2fsck -fy <dev>
   dumpe2fs -h <dev>
   iscsiadm -m node -T <iqn> -p <addr> -u
   iscsiadm -m node -T <iqn> -p <addr> -o delete
   ```
   Read `Filesystem state` in the `dumpe2fs` output by eye; the argv has no pipe.
   Expected: `e2fsck` exit 0 (or 1, "errors corrected": Ben's call), `Filesystem state: clean`, then logged out and
   the node record gone. MMP refuses the login's mount anywhere else meanwhile.
6. **Re-check** on the storage VM as in step 3. Expected: exit 0 and `Filesystem state: clean`.
7. Start the app as in "Restage" step 4. Expected: no `mounting fs with errors` line.
8. Drop the copy when the app is verified: delete the LVM snapshot (`lvremove`, **Ben OK**), or let the TrueNAS
   snapshot expire. Then release the lock, **Ben OK**, `[R]`
   `sh /run/homelab-cutover/lock.sh release storage-fsck-<id> <owner>` (one row) `(not rehearsed)`. Expected:
   `released`. Then dispatch `storage.yml`, **Ben OK**, `[W]` `gh workflow run storage.yml -R
   Starktastic-Homelab/ansible --ref main` `(not rehearsed)`. Expected: a green run, so anything skipped under the
   lock applies now. Any stop between steps 4 and 8 keeps the lock until Ben decides.

## Undo

- Restage: nothing to undo. If the app does not start, keep it at 0 and bring the log to Ben.
- `e2fsck -fy` that made things worse, with the app still at 0: restore from the TrueNAS snapshot as in
  `storage-vm-restore.md` "Single app from a ZFS clone", keeping the lock from step 4 until the app is verified, or
  merge the LVM snapshot as below. **Ben OK.**
- **LVM snapshot merge** `(not rehearsed)`. LIO holds the origin open, and LVM only defers a merge into an open origin
  to its next activation. The app would then start on the unreverted origin, and a later storage VM boot would copy
  the pre-fsck blocks back over its new writes. So the target comes off first, and the app stays at 0 until the
  snapshot is gone. The lock from "Offline e2fsck" step 4 is held and the app is at 0 throughout; **Ben OK** for each
  row.
  1. `[S]` `targetcli sessions` lists no session for `<id>` (Restage step 3 confirmed the unstage).
  2. `[S]` take the target and its backstore off, under the LIO lock:
     `flock /run/lock/storage-lio targetcli /iscsi delete iqn.2026-11.net.starktastic.storage:<id>`, then
     `flock /run/lock/storage-lio targetcli /backstores/block delete <id>`, then
     `flock /run/lock/storage-lio targetcli saveconfig`. The LV and its data stay; only the export goes.
  3. `[S]` `lvs --devices <PV of vg> -o lv_name,lv_attr,lv_device_open <vg>/<id>`, without `--readonly`, which does
     not ask device-mapper and so cannot see an open device. Expected: the sixth `lv_attr` character is `-`, not `o`,
     and `lv_device_open` is empty: nothing holds the origin open. Anything else: stop and go to Ben.
  4. `[S]` `lvconvert --devices <PV of vg> --merge <vg>/<id>-prefsck`. Expected: `Merging of volume
     <vg>/<id>-prefsck started.` and then `<vg>/<id>: Merged: 100.00%`. A `Delaying merge since origin is open` line
     means the origin is still open: stop and go to Ben, and start nothing on that volume.
  5. `[S]` `lvs --devices <PV of vg> -a -o lv_name,lv_attr <vg>` (no `--readonly`, as in step 3). Expected: no
     `<id>-prefsck` row, and the `<id>` row no longer an origin (first `lv_attr` character `-`, not `o` or `O`). Only
     then may the app start.
  6. `[S]` the read-only check of "Offline e2fsck" step 3, `e2fsck -fn /dev/<vg>/<id>`: now without the in-use
     warning, and the state from before that section's step 5 (`clean with errors` is expected; the repair was undone).
  7. Release the lock and dispatch `storage.yml` as in "Offline e2fsck" step 8 (without the `lvremove`; the snapshot is
     gone). Only that
     run puts the target back: `held_lock_owner` takes only a `storage-restore` owner, so it cannot run under this
     lock. Expected: a green run and `targetcli ls /iscsi/iqn.2026-11.net.starktastic.storage:<id>` with LUN 0 and
     both worker ACLs. The app is still at 0 behind its deny syncWindow, so nothing writes in between.
  8. Start the app as in "Restage" step 4, and bring the log to Ben. The error flag is still set: a new repair is a new
     run of this section.

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/<task>/`: the kernel lines, the unstage reads,
  the `dumpe2fs` and `e2fsck` output, the copy's name, and the app's first start line.
- Sources: ADR 0017, Qualification Check 8, Disposable, Open questions (F9); migration plan D11.
- Lab: report `:641-683` (B8 Check 8; F13 at `:676`).
- Lab: `storage-lab/b8/notes.md` legs N-stall, N-withdraw, H-stall, H-withdraw.
- Lab: `storage-lab/b10/notes.md:160-165` (F21 fsck and repair), `b10/notes.md:98` (F9 e2fsck rehearsal not run).
- Lab: `storage-lab/b10/f14/fsck.log`, `fsck-n.txt`, `repair.log`, `repair-verify.txt`.
- Lab: `storage-lab/b10/f14/repair-lab-sqlite.txt`, `repair-lab-regen.txt`.
