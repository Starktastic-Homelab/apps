# Planned pve host reboot with the storage VM

One planned reboot of the Proxmox host while the storage VM serves targets (ADR 0017, Boot order and Qualification
Check 1). Gate F2 (migration plan Task 3.8) and Task 5.10 run it. Ben may combine it with the memtest reboot (memory
`pve-memtest-plan`); see "Shutdown order" for what that costs.

Where commands run:
- `[P]`: root on pve, through the helper from the workstation. The runner is down for part of this.
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve. ASCII only, no `$`, no single quotes.
- `[R]`: root on VM300 (the runner), `qm guest exec 300`. `[K]`: `k3s kubectl` on the master. `[W]`: the workstation.

## Before you start

- **Ben OK** for the slot, the shutdown and every start below.
- `hold_fence` is set on `retained`, so this reboot does not test the cold-boot fence rule (F18).
- No deny syncWindow of its own: no writer is scaled by hand, every app stops with its worker, and Argo starts them
  again after boot. Any deny syncWindow already in place stays as it is. Not during a cutover (the freeze rule;
  `storage-vm-cutover.md`), so no cutover's "Hold" window is open.
- Run every check in "Gate" first.

## Gate

Read-only, at T-30 min. Abort if any check fails.

1. **The slot** (Ben):
   - outside every backup window;
   - the start falls in hh:02-hh:30 Asia/Jerusalem, never 01:00-06:59, never in the 03, 09, 15 or 21 hours, and not
     Sunday 00:xx. The reboot then spans no `:00` (the hourly health fails until `usbbk-import` is done) and no
     TrueNAS `:30` run;
   - after that hour's `storage.yml` run at `:05` UTC has finished. A run killed by the reboot keeps the lock (D31).
   - Tell the household: about 12 minutes of outage plus the storage VM's 30 s slot.
2. `[P]` pve (the 11-15 runbook's pre-checks, run on 11-16):
   - `ls /var/lib/systemd/pstore /sys/fs/pstore`: both empty. A record blocks the backups;
   - `systemctl list-timers 'homelab-backup*'` and `pgrep -af '[r]estic|[v]zdump|[z]fs (send|recv)'`: nothing
     running, and nothing due in 45 min. `-f` matches the full command line: without it pgrep sees only the name `zfs`, so a
     running `zfs recv` never matches. The brackets keep a wrapper shell that carries the pattern from matching itself;
   - the last TrueNAS replication to `usbbk` is green;
   - `pve-backup` green (healthchecks.io).
3. `[W]` `gh run list` in all five repos: nothing in progress or queued. No PR with auto-merge. Hold every merge until
   "After boot" ends.
4. `[R]` the maintenance lock is `FREE`: `/var/lib/homelab-maintenance/operation.json` does not exist.
5. `[P]` startup `(not rehearsed)`:
   - `qm config 100 | grep -E "^(startup|onboot):"`: `order=1,up=180`;
   - `qm config <D1:storage_vmid> | grep -E "^(startup|onboot):"`: `onboot: 1`, `startup: order=2,up=30`;
   - every k3s VM: `onboot: 1` and no `startup`.
6. VM 100's last shutdown was clean, with the pools exported (TrueNAS log of the previous boot). It has no `down=`, so
   a stop longer than 180 s is forced.
7. Baseline (`pre.txt`):
   - every app Healthy, and the VolumeAttachment count per node;
   - each retained writer's last row or `ack`, where the app prints one;
   - `[S]` `systemctl show rtslib-fb-targetctl storage-fencer -p ActiveEnterTimestamp`, `uptime -s`,
     `vgs --devices /dev/disk/by-id/virtio-retained --readonly --noheadings -o vg_tags retained` (`hold_fence`, no
     `fenced:` tag) and `nft list set inet filter fenced` (empty);
   - the ansible `main` SHA, and the SHA the last `storage.yml` run logged.

## The runner goes down

- VM300 is a guest. No workflow runs from the reboot until VM300 is back, and queued runs then drain.
- The helper runs from the workstation, so the steps below still work.
- `[R]` `findmnt -t tmpfs -o TARGET` before the reboot records what the reboot wipes (F19: a tmpfs is gone after a
  reboot; in the lab that was the SSH key and the Proxmox token). List any homelab credential found there for Ben.

## Shutdown order

1. `[P]` `systemctl reboot`. **Ben OK.** Note T0. Ben watches POST on JetKVM.
   - It is a plain reboot, so pve's own `stopall` order is what gets tested.
   - Unordered guests stop first (the k3s VMs and VM300), then the storage VM (`order=2`), then VM 100 (`order=1`)
     last. Each gets `down` or 180 s, then a forced stop. The workers' graceful shutdown (90 s) fits.
2. Expected (lab B10 Step 3, production order): stopall in about 2 min; workers before the storage VM, the storage
   VM in about 6 s, TrueNAS last. pve itself may then hang about 1.5 min on dead NFS storages before the reboot.
3. **Combined with the memtest.** The memtest runbook stops guests by hand (`qm shutdown` 200, 201, 202, 300, then
   100), so VM 100 is never force-stopped. Add `qm shutdown <D1:storage_vmid> --timeout 180` after the workers and
   before VM 100. A hand order does not test `stopall`, and the lab ran Check 1 only on a clean return boot. So a
   combined run proves only the boot half; record the shutdown half as not proven. A separate plain reboot is the
   recommendation.

## Boot and start order

1. Expected start (lab B10 Step 3 and production 11-16): pve reachable about 7 min after T0; VM 100 first; the storage
   VM about 180 s later; the unordered guests (master, workers, VM300) about 30 s after that.
2. `[P]` read the task log and the journal `(not rehearsed)`:
   - `pvesh get /nodes/pve/tasks --limit 200 --output-format json`, filtered to `qmshutdown`, `qmstop`, `qmstart`,
     `startall` and `stopall` since T0-30 min;
   - `journalctl -b -u pve-guests --no-pager | grep -ci "not online"`. Expected: `0`;
   - `journalctl -b -1 -u pve-guests --no-pager -o short-iso | grep -iE "stop|shutdown" | tail -15`.
   Expected: both workers' `qmshutdown` ended before the storage VM's started, VM 100 stopped last, and the start
   order as in step 1.
3. `[P]` `systemctl --failed` empty, `systemctl status usbbk-import` finished, pstore empty.
4. Then one `systemctl start homelab-backup@health.service` after `usbbk-import`. **Ben OK.** Expected: green.
5. **A guest refused as `not online` (late NFS).** No retry exists (D9). The storage VM and the workers stay stopped.
   - Record it. For Gate F2 this fails the "no manual step" criterion: stop and bring it to Ben.
   - Recovery, **Ben OK**: `[P]` `qm start <D1:storage_vmid>` once `pvesm status --storage k3s-block` is active, then
     `qm start` each stopped worker (memory `proxmox-worker-autostart-nfs-race`) `(not rehearsed)`.

## After boot

1. **Targets** (read-only). `[S]` `(not rehearsed)`:
   - `uptime -s`;
   - `systemctl show rtslib-fb-targetctl storage-fencer -p ActiveState -p ActiveEnterTimestamp`;
   - `targetcli ls /iscsi`: every target, each with LUN 0 and both worker ACLs;
   - `cat /var/lib/prometheus/node-exporter/storage-boot-check.prom`: `storage_boot_check_ok 1`, written after boot;
   - `journalctl -b -u rtslib-fb-targetctl --no-pager -o short-iso | head -12`;
   - `vgs --devices /dev/disk/by-id/virtio-retained --readonly --noheadings -o vg_tags retained` and
     `nft list set inet filter fenced`.

   Expected: `rtslib-fb-targetctl` active within seconds of boot (lab: 5 s), before the first `storage.yml` run after
   T0; `retained` still has `hold_fence` and no `fenced:` tag; the `fenced` set is empty.
2. **The fencer.** With `hold_fence` set it refuses every fence; its log shows `not-ready-too-short` or
   `watch-too-short` for each worker, and the `hold_fence` reason once one has been NotReady past 300 s. F18's
   NotReady-from-watch-start rule applies too. A `fenced:` tag after the boot is a stop: see
   `storage-vm-fencing.md` "Unfence after a host cold boot".
3. **The first `storage.yml` run.** `[W]`
   `gh run list -R Starktastic-Homelab/ansible --workflow storage.yml --limit 3 --json event,createdAt,conclusion`.
   Expected: green, and nothing changed on the storage side. A run with the warning `k3s does not answer on the first
   master` is a green skip that applied nothing: read the next run, which must show `k3s=true`.
4. **Workloads.**
   - Retained writers Running. Each starts with its data at or past its baseline row. The workers' graceful shutdown
     unstaged the volumes, so no manual step is needed.
   - Nodes Ready, every app Healthy, the VA count equal to `pre.txt`, and an ingress probe 200 or 302 (memory
     `ingress-probe-from-workstation`).
5. **GPU admission race.** `[K]` list `UnexpectedAdmissionError` pods in `media`, and delete them by name with
   **Ben OK** (memory `gpu-admission-race`). Their replacements run.
6. **Worker NFS race.** A worker still stopped after boot hit `not online`; see "Boot and start order" step 5.
7. Lift the merge hold.

## Runner credentials after a reboot

- F19: a runner reboot wipes its tmpfs mounts. In the lab that took the lab SSH key and the lab Proxmox token.
- `[R]` `findmnt -t tmpfs -o TARGET` again, and compare with the "The runner goes down" read.
- `[W]` the runner is online:
  `gh api orgs/Starktastic-Homelab/actions/runners --jq '.runners[] | .name+" "+.status'`.
- Re-provision only what Ben re-creates. Never restore a credential yourself.

## Undo

A reboot has no undo. If a check above fails, keep the merge hold and bring it to Ben with the reads.

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/3.8/` (or `5.10/`): `gate.txt`, `pre.txt`,
  `post.txt`, the run URLs and `facts.md`.
- Sources: ADR 0017, Boot order and Check 1; migration plan Task 3.8, D9; memory notes
  `proxmox-worker-autostart-nfs-race`, `gpu-admission-race`, `pve-memtest-plan`.
- Sources: `~/Projects/homelab/pve-one-reboot-runbook-2026-11-15.md`, `pve-reboot-report-2026-11-16.md`,
  `pve-window-runbook-2026-11-15.md`.
- Lab: report `:815-848` (B10); `storage-lab/b10/notes.md:15-39`; `b10/b10go-2026-11-17-1902.log`.
- Lab: `storage-lab/b10/b10resume-2026-11-17-1906.log`, `storage-lab/b10/s4/`.
