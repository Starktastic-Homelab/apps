# Storage VM rebuild

A deliberate rebuild of the storage VM from its packer template (ADR 0017, Storage VM "A deliberate rebuild is its
own PR" and Disposable). The data disks are owned by a placeholder VMID, so they survive. Gate F1 (migration plan
Task 3.7) ran this runbook on 2026-11-25 (terraform#252 and #253, F1 PASS). Also here: what to do when the storage
VM is down.

Where commands run:
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve through the helper. ASCII only, no `$`,
  no single quotes in the row.
- `[P]`: root on pve. `[K]`: `k3s kubectl` on the master. `[N]`: root on a worker, `qm guest exec <worker vmid>`.
- `[W]`: the workstation (`gh`, `git`).

`R` = `/dev/disk/by-id/virtio-retained`, `G` = `/dev/disk/by-id/virtio-regen`, written out in `[S]` rows.

## Before you start

- **Ben OK** for each merge and each scale.
- Maintenance lock `FREE` before the rebuild PR. `apply-storage` takes it itself.
- Outside every backup window. Run the rebuild, the restore and the reconfigure inside one gap between the hourly
  `storage.yml` runs (`:05` UTC from the pve backstop; GitHub's own cron may fire late, `:30` seen), and never across
  `10:05` UTC: `storage-expiry.yml` on an unconfigured fresh root fails and keeps the lock.
- Pre-checks (read-only): `[P]` `ha-manager status` lists no HA resource for the VM; `pvesr list` has no job for it;
  `qm config <D1:storage_vmid> | grep -E "^(protection|lock|hookscript):"` prints nothing; no ACL on
  `/vms/<D1:storage_vmid>` (a destroy drops it, memory `pve-destroy-drops-vm-acl`).
- No packer `build.yml` run queued or in progress, and no packer push while the rebuild PR is open: every build
  replaces the template at its fixed VMID (ADR, "A deliberate rebuild is its own PR").
- Nothing else merges in terraform between the rebuild PR and its restore PR.
- Not during a cutover: the freeze rule holds from a cutover's inventory PR to its reconciliation PR.
- Every retained writer is drained ("Writer drain"). A deny syncWindow holds each writer whose app Argo would
  otherwise scale back up.

## Why drain first

- The storage root gets no graceful shutdown: `maintenance_apply.py` shuts down only `proxmox_vm_qemu` targets, so
  bpg hard-stops the storage VM before the destroy.
- A rebuild cut I/O for about 2 min 23 s in the lab (F9). The initiator's `replacement_timeout` is 120 s.
- After 120 s every mounted filesystem gets I/O errors and goes read-only. Each pod then needs a restage, which waits
  about 44 s for MMP and leaves the ext4 error flag set.
- Raising `replacement_timeout` would not cover a full rebuild.
- So scale every writer to 0 first. A drained, cleanly unmounted volume remounts with no MMP wait and no error flag.
- If a writer was left running, follow `storage-vm-readonly-fs.md` "Restage" afterwards, and the flagged filesystem
  waits for "Offline e2fsck of an error-flagged filesystem".

## Writer drain

1. `[K]` list the writers on the storage VM:
   `get volumeattachments -o jsonpath='{range .items[*]}{.spec.attacher} {.spec.nodeName}
   {.spec.source.persistentVolumeName}{"\n"}{end}'` (one row).
   Expected: one line per staged volume. Lines with `org.democratic-csi.node-manual` are the ones to drain.
2. For each app with such a volume, hold it so Argo does not undo the scale:
   - a writer defined in Git (like the F1 canary): merge a `replicas: 0` PR. **Ben OK.**
   - an ArgoCD app: add a deny syncWindow on the `default` AppProject as in `storage-vm-cutover.md` "Hold", then scale
     to 0. **Ben OK** for each.
3. Wait until the drain is complete:
   - `[K]` the step 1 read shows no `org.democratic-csi.node-manual` line, and each held app is `Synced Healthy` with
     no pod;
   - `[N]` `iscsiadm -m session` on every worker lists no `iqn.2026-11.net.starktastic.storage:` target. Exit 21 with
     `No active sessions` is the clean answer;
   - `[S]` `targetcli sessions` prints `(no open sessions)`.
4. Record each writer's last row or `ack` where the app prints one, to compare after the restart.

## Rebuild PR pair

Two terraform PRs, merged back to back. Until the second merges, the storage VM has no destroy guard.

1. **Baseline** (read-only, `base.txt`). The lab B7 rows in this scoped form:
   - `[S]` `lvs --devices /dev/disk/by-id/virtio-retained --readonly -o vg_name,lv_name,lv_uuid,lv_size retained`, and
     the same for `regen` with `virtio-regen`;
   - `[S]` `vgs --devices /dev/disk/by-id/virtio-retained --readonly -o vg_name,vg_uuid,vg_tags retained`, and the same
     for `regen`;
   - `[S]` `find /sys/kernel/config/target/iscsi -maxdepth 4 -path "*/acls/*" -type d` (target and ACL IQNs);
   - `[S]` `blkid -o value -s UUID /dev/<vg>/<id>` for every LV with a filesystem;
   - `[S]` `systemctl show storage-fencer -p NRestarts -p ActiveEnterTimestamp`;
   - `[P]` `pvesh get /nodes/pve/qemu/<D1:storage_vmid>/config --output-format json`, keeping `virtio0`-`virtio2`,
     `net0`-`net1`, `onboot` and `startup`.
2. **The rebuild PR** (terraform, `feat/storage-vm-rebuild`):
   - `storage/main.tf`: `prevent_destroy = false`;
   - `storage/terraform.tfvars`: bump `generation` by one;
   - `scripts/tests/test-storage-root.py`: `test_production_tfvars` expects the new generation.

   The title and body name no skip pattern.
   Expected CI:
   - `Offline cluster rebuild policy` fails with `failures=2, errors=0`: exactly `test_generation_change_refused` and
     `test_destroy_keeps_unreferenced_disks`, the two tests that assert `prevent_destroy`. Any other failure is a stop.
     It is not a required check, so the PR shows `UNSTABLE`, not `BLOCKED`; the required checks (`Terraform validate
     and plan`, the format check) are green;
   - k3s plan `No changes.`; storage plan `Plan: 1 to add, 1 to change, 1 to destroy`;
   - the disk blocks before and after are identical: `virtio1` and `virtio2` keep their volids,
     `delete_unreferenced_disks_on_destroy = false`, `purge_on_destroy = false`.
3. Re-run the plan right before the merge. Check again: lock `FREE`, packer idle, the template name matches the
   manifest, and the next `:05` run is far enough away.
4. Merge. **Ben OK** (it destroys and recreates the storage VM). A plain squash, no `--admin`:
   `[W]` `gh pr merge <n> -R Starktastic-Homelab/terraform --squash --match-head-commit <sha>`.
   Expected: `apply.yml` green. `apply-storage` prints `clone source <template vmid> is a template named <name>` and
   `Graceful shutdown before Terraform: none`, then `1 added, 1 changed, 1 destroyed`. 2026-11-25: destroy 3 s,
   create 22 s (the lab took 55 s). `Trigger Ansible` is skipped. Lock `FREE` after. `StorageVMDown` may fire for
   the gap.
5. **The restore PR, right away** (`fix/storage-vm-prevent-destroy`): `prevent_destroy = true`. Keep the new
   generation and its test. After the squash merge, rebase the branch onto `main` and open it only once the rebuild
   apply is green.
   Expected: CI green, including `Offline cluster rebuild policy`; both plans `No changes.`. Lock `FREE` before the
   merge. Merge. **Ben OK.** The apply is a no-op.

## After the rebuild

1. Reconfigure. **Ben OK.** `[W]` `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main`.
   If an hourly run gets there first, use that run (2026-11-25: GitHub's late cron did, at 12:30 UTC).
   Expected: `failed=0`. The role installs on the fresh root, copies the fencer token, and re-exports every target from
   the ledger. No create runs: each LV exists and its ledger says `created`. The worker check passes, because the
   fresh root has no installed `config.json`. The fresh root has no boot-check textfile either, so the run runs the
   boot check once after the re-export (`Run the boot check once on a root that never ran it`); a non-zero exit fails
   the run in its last play and keeps the lock (D31): then `storage-vm-restore.md` "Boot check failed".
   A green run counts only if it took the lock, ran `Reconcile volumes and targets`, skipped `Fail if the reconcile
   refused an entry or failed`, and ran the boot check (or a later run found the textfile). `Reconcile volumes and
   targets` reports `changed` on every run and does not print its actions, so the UUID compare in step 3 is the proof
   that nothing was created. On a fresh root the host-gauges sub-step fails with `ModuleNotFoundError:
   homelab_storage`; that is harmless.
2. Startup and onboot. The recreate drops `startup` (lab: `onboot 1`, `cpuunits` null after the recreate).
   **Ben OK.** `[W]` `gh workflow run proxmox-guest-startup.yml -R Starktastic-Homelab/ansible --ref main`.
   Expected: the task line `changed: [pve] => (item=<D1:storage_vmid>: order=2,up=30)`, recap `changed=1`.
   `[P]` `qm config <D1:storage_vmid> | grep -E "^(startup|onboot):"` reads `onboot: 1` and `startup: order=2,up=30`.
3. Compare (read-only, `after.txt`, the same rows as the baseline). Expected:
   - `virtio1` and `virtio2`: the same volids and sizes. `virtio0` and the MACs are new;
   - LV UUIDs, VG UUIDs and VG tags identical (`hold_fence` on `retained`, the ledgers, the tombstones, any
     `fenced:` tag). They also match the bootstrap UUIDs (`storage-vm-bootstrap.md`);
   - target IQNs and ACL IQNs identical;
   - filesystem UUIDs identical, so no `mkfs` ran;
   - `rtslib-fb-targetctl`, `nftables` and `storage-fencer` active; the fencer has a fresh `ActiveEnterTimestamp` and
     `NRestarts=0`; the `fenced` set matches the `fenced:` tags; `StorageFencerBlind` quiet;
   - `[S]` `cat /var/lib/prometheus/node-exporter/storage-boot-check.prom` holds `storage_boot_check_ok 1`.

   Any difference in a UUID, tag or IQN is a stop. Bring it to Ben before any writer starts.
4. No `known_hosts` refresh: ansible runs with `StrictHostKeyChecking=no` (ansible `group_vars/all/vars.yml`).
5. Start the writers: revert the `replicas: 0` PRs, or remove the deny windows (as in `storage-vm-cutover.md`, "Lift
   the hold and the 6-minute watch"). **Ben OK.**
   Expected: each app starts with its data at or past the recorded last row. A drained volume mounts with no MMP
   error flag.

## VM down

`StorageVMDown` fires when `up{job="storage-vm"}` has been 0 for its `for:` time.

- No automatic retry (D9, Ben 2026-11-22): a storage VM still stopped after a cold boot with a late NFS stays stopped
  until someone runs `qm start`.
- The alert works only before wave 1. After wave 1, Prometheus and Alertmanager live on `regen`, so a storage VM that
  is down takes them with it (D7). Then only the healthchecks.io Watchdog dead-man check sees it, after about
  10 minutes (ADR, Consequences, "Silent storage-VM failure").
- Every retained app waits meanwhile: its pods stay in ContainerCreating and the workers keep retrying the login.

1. `[P]` `qm status <D1:storage_vmid> --verbose` `(not rehearsed)`. Note `status` and `qmpstatus`.
2. `[P]` `pvesm status --storage k3s-block` `(not rehearsed)`. Expected: `active`.
   - Not active: the NFS from TrueNAS is late or down. pve refuses to start the VM (`storage 'k3s-block' is not
     online`; lab B10 Step 4). Fix TrueNAS first.
3. Stopped, and `k3s-block` active: `[P]` `qm start <D1:storage_vmid>`. **Ben OK.** `(not rehearsed)`
   Expected: in the lab, starting the NFS VM and then the storage VM brought every target back within 45 s.
   Then start any worker that also failed `not online` (memory `proxmox-worker-autostart-nfs-race`).
4. Running but not answering: read `[S]` `journalctl -b -u rtslib-fb-targetctl --no-pager | tail -40`
   `(not rehearsed)`. If the boot check failed, follow `storage-vm-restore.md` "Boot check failed". A stalled data
   disk holds the whole boot in the initramfs for as long as the stall lasts (F24, accepted). Do not reset it with
   `module.async_probe=1`.
5. After the targets are back: pods restage on their own. A pod that went read-only follows
   `storage-vm-readonly-fs.md` "Restage".

## Undo

- Before the rebuild PR merges: close it.
- After the apply: there is no undo. The VM is new; the data disks are the same. Merge the restore PR, then follow
  "After the rebuild".
- The clone check refuses (for example a missing clone source): it fails before the destroy, `check_clone_source`
  exits 1, and no plan file is applied. Fix the template, re-run the PR plan, then re-run `apply.yml`.
- The apply fails after it took the lock: the lock stays held in `applying` on purpose. Read the apply log first.
  Release the lock only with **Ben OK**. `repository_dispatch` skips the storage root, so the fix is a new terraform
  PR; keep `prevent_destroy = false` in it if the VM is tainted or half-created.
- The delete failed and left the old VM stopped: `[P]` `qm start <D1:storage_vmid>`. **Ben OK.** Then follow "VM down".

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/<task>/`: `base.txt`, `after.txt`, plan excerpts,
  run URLs and `facts.md`.
- Gate F1, 2026-11-25: `evidence/3.7/` (terraform#252 rebuild, #253 restore; apps#1723 and #1724 drain and start).
- Sources: ADR 0017, Storage VM, Disposable, Consequences; migration plan Task 3.7, D7, D9.
- Lab: report `:573-640` (B7 Check 3, F9, F10); `storage-lab/b7/notes.md:13-33`.
- Lab: baselines `storage-lab/b7/base-971.txt`, `b7/after2-971.txt`, `b7/after3-971.txt`.
- Lab: `storage-lab/b7/qm971-before.txt`, `b7/qm971-after.txt`.
- Lab: `storage-lab/b7c3-storage.txt`, `storage-lab/tf-storage/`.
