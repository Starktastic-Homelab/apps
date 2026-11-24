# Storage VM held packages

Three packages on the storage VM are held, and why an upgrade of them needs a window (ADR 0017, The storage VM; F24).
No upgrade was rehearsed in the lab: **every command here is `(not rehearsed)`**.

Where commands run:
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve through the helper. ASCII only, no `$`,
  no single quotes in the row.
- `[P]`: root on pve. `[K]`: `k3s kubectl` on the master. `[R]`: root on VM300, the runner. `[W]`: the workstation
  (`gh`).

## Before you start

- **Ben OK** for the window, the drain, the upgrade and the reboot. Upgrades are deliberate; nothing runs them on a
  timer.
- A window drops every iSCSI session, so it needs the same writer drain as a rebuild.
- No cutover in progress (the freeze rule), and the maintenance lock is `FREE`.
- Not in a backup window (D29, provisional: backup until 06:00, maint until 07:00).

## What is held and why

- `python3-rtslib-fb` and `targetcli-fb`. A restart of `rtslib-fb-targetctl.service` drops every session, and a
  package upgrade can trigger one. Nothing else ever restarts that unit (ADR `:144-146`).
- `lvm2`. Its upgrade runs an unscoped `vgcfgbackup` (it reads every PV, not only `--devices`) and may replace
  `/etc/lvm/lvm.conf`. The image edits that file to set `event_activation = 0` (packer `scripts/storage.sh`, the F24
  block), so only the role activates `retained` and `regen` (F24, lab `b8/f24-notes.md`).
- The image holds all three (`apt-mark hold` in packer `scripts/storage.sh`), and the role holds them again (ansible
  `roles/storage_vm/tasks/main.yml:19-28`).
- The assert play refuses to run when `lvm2` is not held, `event_activation` is not 0, or `lvm2-monitor` and
  `blk-availability` are not masked (`roles/storage_vm/tasks/assert.yml:70-81`, the hold check at `:75`). So a
  `storage.yml` run fails at "Refuse stock LVM activation" until the hold and the config are back.
- Everything else upgrades as on any VM. A kernel or other package that needs a reboot still needs the drain.

## Upgrade window

1. **Read what is pending.** `[S]` `apt-get update` then `apt list --upgradable` and `apt-mark showhold`
   `(not rehearsed)`. Expected: the three held packages, plus whatever else is pending. Read the Debian changelog of
   each held package before going on.
2. **Lock.** **Ben OK.** `[R]` `sh /run/homelab-cutover/lock.sh acquire storage-upgrade
   claude-code/storage-upgrade/<UTC ts>` (one row) `(not rehearsed)`. `lock.sh` is staged only by migration plan
   Task 4.0 Step 9; stage it first if this runs before Part 4. It hardcodes the cutover prefix, so the operation reads
   `storage-cutover:storage-upgrade` (as the Task 5.x scale gate does). Hourly `storage.yml` runs then skip.
3. **Drain the writers.** `storage-vm-rebuild.md` "Writer drain", every step. Expected: no Pod mounts a storage VM
   volume, `[S]` `targetcli sessions` lists none.
4. **Hold the fencer.** `[S]` `vgchange --devices /dev/disk/by-id/virtio-retained --addtag hold_fence retained`
   `(not rehearsed)`, unless `retained` already has it (record which). A worker that loses its session must not be
   fenced while the storage VM is down.
5. **Unhold.** `[S]` `apt-mark unhold python3-rtslib-fb targetcli-fb lvm2` `(not rehearsed)`.
6. **Upgrade, keeping the edited `lvm.conf`.** `[S]`
   `env DEBIAN_FRONTEND=noninteractive apt-get -y -o Dpkg::Options::=--force-confold install python3-rtslib-fb
   targetcli-fb lvm2` `(not rehearsed)`. Split the row for `qm guest exec` if needed; it has no `$` and no single quote.
   Expected: the new versions; `lvmconfig global/event_activation` still prints `event_activation=0`.
   If dpkg wrote `/etc/lvm/lvm.conf.dpkg-dist`, compare it with the current file and bring it to Ben.
7. **Re-hold.** `[S]` `apt-mark hold python3-rtslib-fb targetcli-fb lvm2`, then `apt-mark showhold`
   `(not rehearsed)`. Expected: all three.
8. **Rebuild the initramfs** only if the upgrade did not: `[S]` `update-initramfs -u` `(not rehearsed)`. The lvm2
   hook copies `lvm.conf` into it (F24).
9. **Reboot.** `[P]` `qm reboot <D1:storage_vmid>` `(not rehearsed)`. **Ben OK.**
   Expected: the boot check passes (`StorageBootCheckFailed` stays quiet), the targets come back, the fencer is active.
10. **Restore the fence hold.** If step 4 added `hold_fence`: `[S]`
    `vgchange --devices /dev/disk/by-id/virtio-retained --deltag hold_fence retained` `(not rehearsed)`.
11. **Release the lock.** **Ben OK.** `[R]` `sh /run/homelab-cutover/lock.sh release storage-upgrade
    claude-code/storage-upgrade/<UTC ts>` (one row). Expected: `released`.
12. **The assert play.** Dispatch `storage.yml`. **Ben OK.**
    `[W]` `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main` `(not rehearsed)`.
    Expected: green, "Refuse stock LVM activation" passes, no changes beyond the targets it already had.
13. **Start the writers** as in `storage-vm-rebuild.md` "After the rebuild", step 5.

## Undo

- Before the reboot: `apt-mark hold` the three again. A downgrade needs the old `.deb` from `/var/cache/apt/archives`
  (`apt-get install <pkg>=<old version>`) `(not rehearsed)`.
- After a failed boot or a failed assert: rebuild the storage VM from the image (`storage-vm-rebuild.md`). The image
  has the old held versions and the F24 config. The VGs are on the data disks and survive it.

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/<task>/`: `apt list --upgradable` and
  `apt-mark showhold` before and after, the dpkg output, `lvmconfig global/event_activation`, the boot check result
  and the run URL.
- Sources: ADR 0017 `:140-146`; ansible `roles/storage_vm/tasks/main.yml:19-28`, `assert.yml:70-81`; packer
  `scripts/storage.sh` (the hold and the F24 block).
- Lab: none for an upgrade. `storage-lab/b8/f24-notes.md` is why `lvm2` is held.
