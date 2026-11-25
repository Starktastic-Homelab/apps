# Planned pve host reboot with the storage VM

One planned reboot of the Proxmox host while the storage VM serves targets (ADR 0017, Boot order and Qualification
Check 1). Gate F2 (migration plan Task 3.8) ran it on 2026-11-25 (PASS); Task 5.10 runs it again. Ben may combine it
with the memtest reboot (memory `pve-memtest-plan`); see "Shutdown order" for what that costs.

Where commands run:
- `[P]`: root on pve, through the helper from the workstation. The runner is down for part of this.
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve. ASCII only, no `$`, no single quotes.
- `[R]`: root on VM300 (the runner), `qm guest exec 300`. `[K]`: `k3s kubectl` on the master. `[W]`: the workstation.

The rows: `~/.cache/claude-homelab-live/storage-migration/f2rows.py gate|regate|post` writes
`evidence/3.8/rows-<mode>.json`, read-only, run through the helper (`live.py <rows.json>`). It reads
`evidence/3.3/rows-post.json` and `evidence/3.7/rows-base.json` and hard-codes F2's scale:
- VMIDs 100, 101, 200-202 and 300; workers 201/202 for the wwn and journal reads; the `evidence/3.8/` output path;
- the `f1-canary` labels; the `sv` row's `lvs` on `regen` only; the 3.7 `ident` row's `blkid`, which reads
  `/dev/regen/f1-canary` only; the `tail -8` and `tail -6` cuts on the worker and storage VM journals; an `echo ok`
  automerge stub.

Not in it: the `[W]` reads (`gh run list`, `gh pr list`); the kernel, HA and priorityClassName reads (hand rows
`rows-pre0.json`, `pre0.txt`); the qmstart warnings and canary journal (`rows-post2.json`, `post2.txt`); the k8s
re-read (`rows-post3.json`, `post3.txt`). For Task 5.10, changing the VMIDs and labels is not enough: generate the
blkid, writer and log reads from `retained-volumes.json` for every entry, drop the `tail` cuts and replace the stub.
Otherwise the identity and staged checks skip every volume but one and still print PASS.

## Before you start

- **Ben OK** for the slot, the shutdown and every start below.
- `hold_fence` is set on `retained`, so this reboot does not test the cold-boot fence rule (F18).
- No deny syncWindow of its own: no writer is scaled by hand, every app stops with its worker, and Argo starts them
  again after boot. Any deny syncWindow already in place stays as it is. Not during a cutover (the freeze rule;
  `storage-vm-cutover.md`), so no cutover's "Hold" window is open.
- **The merge hold** starts at the gate and ends at "After boot" step 9, or later if the plan holds it (F2: through
  Task 3.10). No storage-path change lands between the baseline and the last read (F2: packer c14e49f and ansible
  9695e1c land after F2 and Step 8).
- Run every check in "Gate" first, then "Re-gate at T-2".

## Gate

Read-only, at T-30 min (`f2rows.py gate`, saved as `pre.txt`, plus the `rows-pre0.json` hand row, saved as
`pre0.txt`). Abort if any check fails.

1. **The slot** (Ben). Compute it in UTC, then convert:
   - outside every backup window (step 2);
   - Monday to Friday, the start at hh:12-hh:30 Asia/Jerusalem, between 07:12 and 20:30. Renovate auto-merges
     weekdays after 22:00 and before 06:00 and all weekend (`renovate.json`), and its required checks need no
     self-hosted runner;
   - never in the 09, 15 or 21 hours, nor in the hour that holds 10:05 UTC (`storage-expiry.yml`: 12 IST in winter,
     13 in summer). The reboot then spans no `:00` (the hourly health fails until `usbbk-import` is done) and no
     TrueNAS `:30` run;
   - after that hour's `storage.yml` run at `:05` UTC has finished. A run killed by the reboot keeps the lock (D31).
     F2: the 16:05 IST run finished 16:09:54, start 16:12.
   - Tell the household: about 20 minutes of outage (F2: 17 min from T0 to every app Healthy).
2. `[P]` pve:
   - `uname -r` is the newest installed `proxmox-kernel`, so the reboot boots no new kernel or ZFS (F2: 7.0.14-29,
     upgradable packages not installed). Record `uptime -s` and `cat /proc/sys/kernel/random/boot_id`;
   - `ls /var/lib/systemd/pstore /sys/fs/pstore`: both empty. A record blocks the backups;
   - `systemctl list-timers --all --no-pager`, saved to `pre.txt`. `homelab-backup-health.timer` is exempt by name
     (hourly, always due). Every other NEXT is after T0+15 min, `homelab-dispatch@storage-expiry.yml.timer`,
     `homelab-backup-*` and `zfs-trim-weekly.timer` included. For `homelab-dispatch@storage.yml.timer` its LAST run
     has finished (step 3);
   - `pgrep -af '[r]estic|[v]zdump|[z]fs (send|recv)|[z]pool (scrub|trim)'` and `zpool status | grep -E 'scan:|trim'`:
     nothing running. `-f` matches the full command line: without it pgrep sees only the name `zfs`, so a running
     `zfs recv` never matches. The brackets keep a wrapper shell that carries the pattern from matching itself;
   - the last TrueNAS replication to `usbbk` is green;
   - `pve-backup` green (healthchecks.io).
   - TrueNAS: no scrub, resilver or SMART test running on VM 100's pools. Ben checks it in the TrueNAS UI; the helper
     does not read it (F2 did not).
3. `[W]` `gh run list --status in_progress` and `--status queued` in all five repos: empty (F2: one stale apps
   "Validate manifests" run from 2026-08-06 shows queued or in progress; it is a zombie). The newest `storage.yml` run
   has completed.
   `gh pr list --json number,autoMergeRequest` in all five: no auto-merge.
4. `[R]` the maintenance lock is `FREE`: `/var/lib/homelab-maintenance/operation.json` does not exist.
   `pgrep -c -x Runner.Worker` is 0 and `pgrep -c -x Runner.Listener` is 1.
5. `[P]` startup, for every guest in `qm list`: `qm config <vmid> | grep -E "^(startup|onboot):"`:
   - VM 100: `order=1,up=180`;
   - the storage VM: `onboot: 1`, `startup: order=2,up=30`;
   - every k3s VM and VM300: `onboot: 1` and no `startup`. VM300 is in no IaC, so only this read checks it;
   - no `down=` anywhere, and `ha-manager status` lists no service (only the `quorum` and `fencing` lines).
6. VM 100's last shutdown was clean, with the pools exported: the previous planned reboot's TrueNAS read ("After
   boot" step 3, in its `post*.txt`). F2 saved none, so 5.10 reads TrueNAS's log of the 2026-11-25 shutdown. It has
   no `down=`, so a stop longer than 180 s is forced.
7. Baseline (`pre.txt`):
   - every app Healthy;
   - VolumeAttachments per attacher and node: `{.spec.attacher} {.spec.nodeName}` through `sort | uniq -c`, and each
     worker's wwn slots: `qm config <vmid> | grep -cE '^scsi[0-9]+:.*wwn='`. The Proxmox CSI count per worker equals
     its wwn count. A democratic-csi VA (`org.democratic-csi.node-manual`) has no wwn slot. Do not use `wwn_check.py`
     (static 11-16 list);
   - each retained writer's node and last row or `ack`, where the app prints one (F2: the f1-canary);
   - `[K]` `kubectl -n democratic-csi get ds democratic-csi-node -o jsonpath='{.spec.template.spec.priorityClassName}'`:
     `system-node-critical` (F2: yes). Flag anything else;
   - `[S]` the storage identity (the `ident` row of `evidence/3.7/rows-base.json`): `lvs` and
     `vgs --devices /dev/disk/by-id/virtio-<vg> --readonly` names, UUIDs and tags of both VGs (`retained` has
     `hold_fence` and no `fenced:` tag), the target ACLs from configfs
     (`find /sys/kernel/config/target/iscsi -maxdepth 4 -path "*/acls/*" -type d`; not `targetcli ls`, which may save
     the live config on exit), each retained FS UUID (`blkid`), `systemctl show rtslib-fb-targetctl storage-fencer`,
     `nft list set inet filter fenced` (empty) and `storage-boot-check.prom`;
   - the storage VM's template and `virtio0` volid (`qm config <D1:storage_vmid>`). On image 902 `openipmi` is a
     failed unit at every boot; expected until packer c14e49f lands;
   - the ansible `main` SHA, and the SHA the last `storage.yml` run logged.

## Re-gate at T-2

Read-only, immediately before the reboot (`f2rows.py regate` plus the `[W]` reads, saved as `regate.txt`). Abort on
any hit (F2 did not save its T-2 `[W]` reads in `regate.txt`; save them there):
- the clock is still inside the slot (Gate step 1);
- `[W]` nothing in progress or queued in the five repos (the 2026-08-06 zombie aside), the newest `storage.yml` run
  has completed with `updatedAt` after hh:05 UTC, and no PR has auto-merge;
- `[R]` lock `FREE` and `Runner.Worker` 0;
- `[P]` nothing busy and the timers as in Gate step 2;
- each retained writer's last `ack`, re-read now (F2: 43345 at T-2).

A cron run that lands in the last 1-2 minutes can still start and be killed with the lock held. Ben accepted that
risk on 2026-11-25; no cron or timer is paused.

## The runner goes down

- VM300 is a guest. No workflow runs from the reboot until VM300 is back, and queued runs then drain.
- The helper runs from the workstation, so the steps below still work.
- `[R]` `findmnt -t tmpfs -o TARGET` before the reboot records what the reboot wipes (F19: a tmpfs is gone after a
  reboot; in the lab that was the SSH key and the Proxmox token). List any homelab credential found there for Ben.
  F2: system mounts only.

## Shutdown order

1. `[P]` **Ben OK.** Record the old boot_id, then
   `systemd-run --on-active=5 --unit=f2-host-reboot systemctl reboot`, so the helper call returns first. Never a plain
   `systemctl reboot` through `live.py`. T0 is 5 s later. Poll `cat /proc/sys/kernel/random/boot_id` until it changes.
   Ben watches POST on JetKVM.
   - pve's own `stopall` order is what gets tested.
   - Unordered guests stop first (the k3s VMs and VM300), then the storage VM (`order=2`), then VM 100 (`order=1`)
     last. Each gets `down` or 180 s, then a forced stop inside the same `qmshutdown` task (no separate `qmstop` row).
     The workers' graceful shutdown (90 s) fits.
2. Expected (F2, 2026-11-25): `stopall` 45 s; the k3s VMs 38 s and VM300 3 s, then the storage VM 2 s, then TrueNAS 3 s;
   pve reachable about 4 min after T0.
3. **Combined with the memtest.** The memtest runbook stops guests by hand (`qm shutdown` 200, 201, 202, 300, then
   100), so VM 100 is never force-stopped. Add `qm shutdown <D1:storage_vmid> --timeout 180` after the workers and
   before VM 100. A hand order does not test `stopall`, and the lab ran Check 1 only on a clean return boot. So a
   combined run proves only the boot half; record the shutdown half as not proven. A separate plain reboot is the
   recommendation.

## Boot and start order

1. Expected (F2): VM 100 first (`startall` about 5 min after T0); the storage VM 181 s later; the unordered guests 31 s
   after that. Each worker's `qmstart` ends `WARNINGS: <n>`, one "iothread is only valid with virtio disk or
   virtio-scsi-single controller" per wwn slot: cosmetic, expected.
2. `[P]` the task log and the journal (`f2rows.py post`, saved as `post1.txt`). From
   `pvesh get /nodes/pve/tasks --limit 300 --output-format json`, sorted by starttime: each guest's newest `qmshutdown`
   before the boot and first `qmstart` after it.
   - Order: the unordered guests' shutdowns end before the storage VM's starts, and its shutdown ends before VM 100's
     starts. Start order as in step 1.
   - Each `qmshutdown`: status `OK`, duration under 150 s, and `pvesh get /nodes/pve/tasks/<upid>/log` has no match
     for `terminat|still running|sigterm|sigkill|timeout|failed`. F2: 38/38/38/3/2/3 s, no marker.
   - `journalctl -b -u pve-guests --no-pager | grep -ci "not online"`. Expected: `0`.
   - `journalctl -b -1 -u pve-guests --no-pager -o short-iso | grep -iE "stop|shutdown|not online" | tail -12`.
   - **F2 FAIL** (Ben, 2026-11-25): a forced stop of any guest.
3. `[P]` `systemctl --failed` empty, `systemctl status usbbk-import` finished, `zpool status -x` healthy, pstore
   empty. `journalctl -b -1 -p err --no-pager | tail` has no oops, BUG or hung task `(not rehearsed)`: kdump is
   removed and panic-reboot is on, so pstore alone may miss a shutdown oops.
4. The hourly health run after `usbbk-import` is green. F2: the scheduled 17:00 run was green, so no start was needed.
   If none is due within the hour, one `systemctl start homelab-backup@health.service`. **Ben OK.**
5. **A guest refused as `not online` (late NFS)** `(not rehearsed)`. No retry exists (D9). Either case fails the
   "no manual step" criterion of Gate F2: record it, stop and bring it to Ben.
   - The storage VM and the workers stay stopped. Recovery, **Ben OK**: `[P]` `qm start <D1:storage_vmid>` once
     `pvesm status --storage k3s-block` is active, then `qm start` each stopped worker (memory
     `proxmox-worker-autostart-nfs-race`).
   - The storage VM stays stopped and the workers run: they start with no 30 s gap and their NodeStage calls find no
     target. Recovery, **Ben OK**: `qm start <D1:storage_vmid>` once `k3s-block` is active. Wait out the D10 30 min
     NodeStage bound before deleting any pod.

## After boot

Read-only unless marked. `f2rows.py post` gives `post1.txt` (steps 1, 3 and 5); `post2.txt` and `post3.txt` came
from the hand rows `rows-post2.json` (qmstart warnings, canary journal) and `rows-post3.json` (k8s re-read).

1. **Targets.** `[S]`:
   - `uptime -s`;
   - `systemctl show rtslib-fb-targetctl storage-fencer -p ActiveState -p ActiveEnterTimestamp -p NRestarts`;
   - the `ident` row again: LV and VG UUIDs and tags, the configfs ACLs and each FS UUID equal `pre.txt`;
   - `cat /var/lib/prometheus/node-exporter/storage-boot-check.prom`: `storage_boot_check_ok 1`, written after boot;
   - `journalctl -b -u rtslib-fb-targetctl --no-pager -o short-iso | head -12`;
   - `vgs ... -o vg_tags retained` and `nft list set inet filter fenced`;
   - `dumpe2fs -h /dev/<vg>/<lv>` for each retained LV: no `FS Error count` `(not rehearsed)`.

   Expected (F2): `rtslib-fb-targetctl` and `storage-fencer` active 5 s after boot, `NRestarts` 0, before the first
   `storage.yml` run; identity identical; `retained` has `hold_fence` and no `fenced:` tag; the `fenced` set is empty.
2. **The fencer.** With `hold_fence` set it refuses every fence. PASS: no fence decision, no `fenced:` tag and an empty
   `fenced` set, whatever reason it logs (`not-ready-too-short`, `watch-too-short`, `foreign-va`, `no-peer` or
   `hold_fence`). Until k3s answers it logs "No route to host" to the API: expected. F18's NotReady-from-watch-start
   rule applies too. A `fenced:` tag after the boot is a stop: see `storage-vm-fencing.md` "Unfence after a host cold
   boot".
3. **The shutdown path of each retained volume** (Task 1.2). `N` is each worker's democratic-csi VA count in
   `pre.txt`:
   - on each worker, previous boot, with no `tail`:
     `journalctl -b -1 -o short-iso | grep -iE "f1-canary|node-manual|TearDown|UnmountDevice"` (for 5.10, every
     retained id) and `journalctl -b -1 -u iscsid -o short-iso`. The count of `UnmountDevice succeeded` lines for
     `org.democratic-csi.node-manual^` is `N`, and so is the count of iscsid `is shutdown` lines for the
     `storageTargetIqnPrefix` targets. Each line comes before that worker's journal end and before the storage VM's
     `qmshutdown`. List any VA with no matching pair;
   - the same worker:
     `journalctl -b -1 -k | grep -iE "EXT4-fs (error|warning)|I/O error|session recovery|conn error|MMP"` is empty;
   - on its new node, `journalctl -b -k | grep -iE "EXT4|MMP|with errors|I/O error"`: no EXT4 error. F2 saw no canary
     mount line there; the writer check (step 5) shows the volume works;
   - `[S]` `journalctl -b -1 -k | grep -iE "iscsi|session|logout"`: F2 saw nothing relevant there. The worker's
     iscsid line is the evidence of the close;
   - TrueNAS's log of this shutdown shows each pool exported (Ben in the UI, or the helper if allowed)
     `(not rehearsed)`. Save it to `post*.txt`: it is the next gate's step 6 evidence.

   Expected (F2, kube-worker-02, `N` 1): TearDown 16:12:22, UnmountDevice succeeded and the iSCSI connection shutdown
   16:12:23, the worker's journal ended 16:12:50, the storage VM's `qmshutdown` 16:12:56. **F2 FAIL** (Ben,
   2026-11-25): a retained volume still staged at power-off, even when the writer recovers.

   Known, not a fail, for the attacher `csi.proxmox.sinextra.dev` only: non-retained Proxmox CSI volumes log
   `UnmountDevice failed ... EOF` about 31 s into the worker's shutdown, because the CSI node plugin goes first (Task
   1.2 orders democratic-csi only). systemd unmounts them; F2 saw no ext4 error after boot. An `UnmountDevice failed`
   (EOF or any other error) on an `org.democratic-csi.node-manual^...` volume is an F2 or 5.10 FAIL. The race does not
   depend on the driver, and only the canary's one volume (unstaged in 1 s) is proven: 5.10 checks the timing per
   volume.
4. **The first `storage.yml` run.** `[W]`:
   - Pick the first run whose job `startedAt` (`gh run view <id> --json jobs`, UTC) is after the storage VM's
     `uptime -s` in UTC. Not `createdAt`: a run queued during the outage predates the boot. `rtslib-fb-targetctl`'s
     ActiveEnterTimestamp is earlier than that `startedAt`.
   - Its steps `Try the maintenance lock once`, `Reconcile under the lock` and `Release the lock after success` are
     `success`, not skipped; `Skip while another maintenance operation runs` printed no lock-held warning; and the log
     has no `##[warning]` annotation (lock held, `k3s does not answer on the first master`, a window skip). Do not
     grep for `::warning::`: GitHub echoes the step scripts that hold it (F2: 3 echoed lines, 0 annotations). The
     lock step reports `success` even when it did not get the lock, so read all three. Otherwise read the next run.
   - A skip from a lock left from before T0 is a stop. A red step before the lock step (pip, galaxy, credentials) is
     a CI retry, not a fail.
   - Wait up to 60 min for the next `:05` dispatch (the backstop timer is `Persistent=false`), or one dispatch with
     **Ben OK**.
   - "Nothing changed" is the identity compare in step 1. The run's `changed=` is not 0 in steady state.

   Expected (F2): run 45641155917, the 17:05 IST pve backstop dispatch (not a cron), job start 15:05:14Z, 45 min
   after the targets; green, storage-01 `ok=58 changed=7 failed=0`, as in the 3.7 steady state.
5. **Workloads.**
   - Each retained writer Running in a new pod. Read the logs of the Running pod by name, not `deploy/...`: an Error
     pod can answer. Its start row is at or past the T-2 `ack` (F2: `integrity=ok count=43839`, ack 43345). A writer
     on a read-only FS: follow `storage-vm-readonly-fs.md` "Restage", **Ben OK**.
   - Nodes Ready, every app Healthy, and an ingress probe 200 or 302 (memory `ingress-probe-from-workstation`).
   - VAs per attacher and node: the Proxmox CSI count per worker equals its wwn count and the total equals
     `pre.txt`; the per-node split may move (F2: 17/16 before, 14/19 after, 33 both). One democratic-csi VA per
     retained writer, on the writer's node.
   - Expected (F2): ArgoCD all Healthy by about 16:29, about 9 min after the workers started. Not all Healthy 30 min
     after the workers start: bring it to Ben.
   - Known: pods the graceful node shutdown terminated stay as Error and are not garbage-collected (F2: about 30,
     some from the 3.3 rebuild). Deleting them is a mutation: **Ben OK**.
   - `[W]` `git -C apps log --since=<T0-30m> origin/main` is empty and no PR has auto-merge. Any commit is a
     deviation.
6. **GPU admission race.** `[K]` list `UnexpectedAdmissionError` pods in `media`, and delete them by name with
   **Ben OK** (memory `gpu-admission-race`). Their replacements run. F2: none.
7. **Alerts**, about 15 min after the workers are Ready. `[P]` `K get --raw` on the
   `prometheus-operated:9090` service proxy (`/api/v1/alerts`), parsed in the pipe; leave no file on pve. None of
   StorageVMDown, StorageBootCheckFailed, StorageTargetMissing, StorageFencerBlind, MaintenanceLockStale or
   TempoBlocklistPollFailing firing. Expected (F2): no storage alert; pending KubePodCrashLooping and
   CPUThrottlingHigh in `operations` from cold-start restarts.
8. **Worker NFS race.** A worker still stopped after boot hit `not online`; see "Boot and start order" step 5.
9. Lift the merge hold, unless the plan holds it longer (F2: through Task 3.10).

## Runner credentials after a reboot

- F19: a runner reboot wipes its tmpfs mounts. In the lab that took the lab SSH key and the lab Proxmox token.
- `[R]` `findmnt -t tmpfs -o TARGET` again, and compare with the "The runner goes down" read.
- `[R]` the runner is online: `systemctl is-active 'actions.runner.*'` is `active`, `pgrep -c -x Runner.Listener` is 1,
  and the lock is `FREE`. `gh api orgs/.../actions/runners` needs `admin:org` and returns 403.
- Re-provision only what Ben re-creates. Never restore a credential yourself.

## Undo

A reboot has no undo. If a check above fails, keep the merge hold and bring it to Ben with the reads. Ben decides.
- The storage VM does not boot: `storage-vm-rebuild.md` "VM down".
- The target restore fails (`storage_boot_check_ok 0`, `rtslib-fb-targetctl` failed): `storage-vm-restore.md` "Boot
  check failed".
- A retained volume comes back read-only: `storage-vm-readonly-fs.md` "Restage".

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/3.8/` (or `5.10/`): `gh-gate.txt`, `pre0.txt`,
  `pre.txt`, `regate.txt`, `reboot.txt`, `post1.txt` to `post3.txt`, `health-post.txt`, `settle.log`,
  `alerts-post.txt`, the first run's log, the `rows-*.json` files and `facts.md`.
- F2 (2026-11-25, PASS): `evidence/3.8/facts.md`; pre-flight review `evidence/3.8-preflight.md`; rows from
  `f2rows.py`, plus `rows-pre0.json`, `rows-post2.json`, `rows-post3.json`, `rows-reboot.json`, `rows-bootid.json`,
  `rows-alerts.json`, `rows-ops.json`, `rows-health.json` and `rows-settle.json`; first run
  `storage-run-45641155917.log`.
- Sources: ADR 0017, Boot order and Check 1; migration plan Task 3.8, D9; memory notes
  `proxmox-worker-autostart-nfs-race`, `gpu-admission-race`, `pve-memtest-plan`.
- Sources: `~/Projects/homelab/pve-one-reboot-runbook-2026-11-15.md`, `pve-reboot-report-2026-11-16.md`,
  `pve-window-runbook-2026-11-15.md`.
- Lab: report `:815-848` (B10); `storage-lab/b10/notes.md:15-39`; `b10/b10go-2026-11-17-1902.log`.
- Lab: `storage-lab/b10/b10resume-2026-11-17-1906.log`, `storage-lab/b10/s4/`. The lab `b10*.sh` scripts are
  lab-only (lab VMIDs); F2 did not use them.
