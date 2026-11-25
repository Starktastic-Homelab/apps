# Storage VM bootstrap

The one-time manual bootstrap of the two VGs on a new storage VM (ADR 0017, Reconcile rules: "Creating a VG is a
one-time manual bootstrap"; Migration 2.3). Migration plan Task 3.5 runs it once. Run it again only for a new,
blank data disk.

Where commands run:
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve through the helper. ASCII only, no `$`,
  no single quotes in the row.
- `[P]`: root on pve. `[W]`: the workstation (`gh`).

Names:
- `R` = `/dev/disk/by-id/virtio-retained` (data disk `virtio1`, serial `retained`, Task 2.1b).
- `G` = `/dev/disk/by-id/virtio-regen` (data disk `virtio2`, serial `regen`).
- Rows below write the paths out in full, because `[S]` rows cannot use shell variables.

Every command here is `(not rehearsed)` in this form. The lab bootstrapped with `/dev/vdb` and `/dev/vdc`, before
the F11, F12 and F24 fixes (lab report, B3 Step 3).

## Before you start

- **Ben OK** for every write. The bootstrap writes to both data disks.
- Outside every backup window (ansible `docs/backup-and-restore.md`, "Schedules").
- The storage VM exists (Task 3.4), and no `storage.yml` run has configured it yet: `storage_vm_pv_devices` is still
  the placeholder, so `scripts/storage_ready.py` skips every run.
- No LV exists on either disk. This runbook never runs on a disk with data.
- The maintenance lock is `FREE`. No lock of your own: no `storage.yml` run can write while `storage_vm_pv_devices`
  is the placeholder (`storage_ready.py` skips every run), and the first one, in "First storage.yml", takes the lock
  itself.
- No writers, so no deny syncWindow.

## Check the disks are the D1/D2 disks and blank

1. `[S]` `ls -l /dev/disk/by-id/ | grep virtio-` `(not rehearsed)`.
   Expected: `virtio-retained` and `virtio-regen`, each a link to one whole disk.
2. `[S]` `ls -l /dev/disk/by-path/ | grep -v -- -part` `(not rehearsed)`.
   Expected: two data-disk links. Note which `pci-...` path each by-id link resolves to.
3. `[P]` `qm showcmd <D1:storage_vmid> --pretty | grep -E "virtio-blk|drive-virtio"` `(not rehearsed)`.
   Expected: `virtio1` (volid `<retained_volname>`) and `virtio2` (`<regen_volname>`) each map to one PCI `addr=`.
   That address is the by-path link of the same disk as `virtio-retained` and `virtio-regen`.
   - Map through the slot, never through the size alone. A swap would put retained data on the backup-excluded disk.
   - Two readers confirm the mapping. Any disagreement is a stop.
4. `[S]` `blockdev --getsize64 /dev/disk/by-id/virtio-retained` and the same for `virtio-regen` `(not rehearsed)`.
   Expected: the D2 sizes in bytes (terraform `storage/terraform.tfvars`).
5. `[S]` `blkid -p /dev/disk/by-id/virtio-retained`, then the same for `virtio-regen` `(not rehearsed)`. Read the
   exit code from the `exitcode` field of the `qm guest exec` result: a row cannot use `$?`.
   Expected: exit code 2 (nothing found) for both. Anything else is a stop: the disk is not blank.

## pvcreate and vgcreate `retained` and `regen`

Scoped like the role: every command names one PV with `--devices` (ADR, LVM isolation).

1. `[S]` **Ben OK.** `(not rehearsed)`:
   ```sh
   pvcreate --devices /dev/disk/by-id/virtio-retained /dev/disk/by-id/virtio-retained
   vgcreate --devices /dev/disk/by-id/virtio-retained retained /dev/disk/by-id/virtio-retained
   ```
   Expected: `Physical volume ... successfully created` and `Volume group "retained" successfully created`.
2. `[S]` **Ben OK.** `(not rehearsed)`:
   ```sh
   pvcreate --devices /dev/disk/by-id/virtio-regen /dev/disk/by-id/virtio-regen
   vgcreate --devices /dev/disk/by-id/virtio-regen regen /dev/disk/by-id/virtio-regen
   ```
   Expected: the same two lines for `regen`.
3. If the image's LVM config refuses `--devices`, stop and bring it to Ben. Do not edit `lvm.conf`: stock
   activation stays off (F24).

## Tag `retained` `hold_fence`

Automatic fencing stays held (Ben, 2026-11-21). The tag goes on `retained` only: the reconcile and the fencer read
holds from `retained` only.

1. `[S]` **Ben OK.** `vgchange --devices /dev/disk/by-id/virtio-retained --addtag hold_fence retained`
   `(not rehearsed)`.
2. `[S]` read back `(not rehearsed)`:
   - `vgs --devices /dev/disk/by-id/virtio-retained --readonly --noheadings -o vg_name,vg_uuid,vg_tags retained`.
     Expected: `retained`, a UUID, `hold_fence` and no other tag.
   - `vgs --devices /dev/disk/by-id/virtio-regen --readonly --noheadings -o vg_name,vg_uuid,vg_tags regen`.
     Expected: `regen`, a UUID, no tags.
   - `pvs --devices /dev/disk/by-id/virtio-retained --noheadings -o pv_name,vg_name` maps the PV to `retained`; the
     same with `virtio-regen` maps to `regen`.
   - `lvs --devices /dev/disk/by-id/virtio-retained --readonly retained` and the same for `regen`. Expected: no LV.
3. Save both VG UUIDs in the evidence. The rebuild runbook ("After the rebuild") compares against them.

## Check the VG budget

Read-only. apps CI checks inventory sizes against the data disk sizes in terraform `main`
`storage/terraform.tfvars` (Task 2.6), assuming each VG's usable size is its disk size less 4 MiB of LVM metadata.
This check proves that for the real `vgcreate`.

1. `[S]` `vgs --units b --nosuffix -o vg_name,vg_size retained regen` `(not rehearsed)`.
2. Expected: each `vg_size` equals `<gib> * 1073741824 - 4194304`, where `<gib>` is the `size` of the data disk
   whose `serial` is that VG's name in terraform `storage/terraform.tfvars`.
   - **Smaller:** stop. The CI rule's 4 MiB is wrong for this `vgcreate`. Fix the rule in Task 2.6's code first.
   - **Larger:** CI is only conservative. Note it in the evidence and go on.

## First storage.yml

`storage.yml` reconciles only once `storage_vm_pv_devices` holds the two by-id paths (Task 3.5 Step 3, the
`feat/storage-pv-devices` PR). Its merge starts the first run on `push`.

1. Merge the PV-paths PR, or dispatch by hand. **Ben OK** (it configures the storage VM).
   `[W]` `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main` `(not rehearsed)`.
2. `[W]` read the run log.
   Expected:
   - `Ready: the storage VM is configured`;
   - `Check that k3s answers before the lock` wrote `k3s=true`. A `k3s does not answer` warning is a green skip with
     nothing applied: fix k3s, then dispatch again;
   - the dry run is clean, then `acquired=true`, the play recap has `failed=0`, and the release step ran. The worker
     check passes: no `config.json` is installed yet;
   - `Run the boot check once on a root that never ran it` ran (no boot-check textfile yet, `rtslib-fb-targetctl`
     active), and `Fail if the first boot check failed` was skipped;
   - the log names the inventory SHA it fetched;
   - `WARNING: democratic-csi/storage-fencer-token is missing or not populated; the fencer stays blind.`
     There is no token until democratic-csi is installed (Task 3.6).
3. `[S]` read-only `(not rehearsed)`:
   - `systemctl is-active rtslib-fb-targetctl nftables storage-fencer`. Expected: `active` three times.
   - `targetcli ls /iscsi`. Expected: no target.
   - `nft list set inet filter fenced`. Expected: no elements.
   - `vgs --devices /dev/disk/by-id/virtio-retained --readonly --noheadings -o vg_tags retained`. Expected:
     `hold_fence` only.
   - `cat /var/lib/prometheus/node-exporter/storage-boot-check.prom`. Expected: `storage_boot_check_ok 1` (Task 2.4),
     written by step 2's run. Later it is rewritten at each boot.
   - `journalctl --header -n0 2>/dev/null | grep -m1 "File path"`. Expected: a path under `/var/log/journal/`
     (persistent). A volatile journal is a stop: the boot check and the planned host reboot read the previous boot.
4. The lock is free afterwards (`MaintenanceLockStale` quiet). A failed run keeps the lock (D31): read its log, then
   release it as in ansible `docs/maintenance-lock-release.md`, with Ben's OK.

## Undo

Only while both VGs hold no LV. **Ben OK.** `(not rehearsed)`:

```sh
vgremove --devices /dev/disk/by-id/virtio-regen regen
pvremove --devices /dev/disk/by-id/virtio-regen /dev/disk/by-id/virtio-regen
vgremove --devices /dev/disk/by-id/virtio-retained retained
pvremove --devices /dev/disk/by-id/virtio-retained /dev/disk/by-id/virtio-retained
```

Never run it once a `storage.yml` run has created an LV.

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/3.5/`: the by-id, by-path and `qm showcmd`
  reads, the `blkid` exit codes, the bootstrap output, the VG UUIDs, the `vgs` budget read and the run URL.
- Sources: ADR 0017, Reconcile rules and Migration 2.3; migration plan Task 3.5 Steps 1-4.
- Lab: report `docs/superpowers/reports/2026-11-16-retained-storage-lab-results.md:185-187` (B3 Step 3, `/dev/vdX`).
