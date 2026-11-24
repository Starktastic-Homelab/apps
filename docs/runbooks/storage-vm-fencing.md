# Storage-side fencing

How to read `storage-fencer`, and how to fence and unfence a worker by hand (ADR 0017, Hang policy and old-writer
exclusion). Automatic fencing ships held: `hold_fence` stays on `retained`, and the manual fence is the only fence
until a later decision turns automatic fencing on (Ben, 2026-11-21). The rule never changes: **never move a volume
without proof that the old writer is cut off.**

Where commands run:
- `[S]`: root on the storage VM, `qm guest exec <D1:storage_vmid>` from pve through the helper. ASCII only, no `$`,
  no single quotes in the row.
- `[P]`: root on pve. `[K]`: `k3s kubectl` on the master. `[W]`: the workstation (`gh`).

Names: `<node>` is the worker's node name, `<vmid>` its VMID, `<bridge address>` its address on the storage bridge.
The taint is exactly `node.kubernetes.io/out-of-service=nodeshutdown:NoExecute` (ansible
`roles/storage_vm/files/homelab_storage/kube.py:11`).

## Before you start

- **Ben OK** for every fence, unfence, taint, `qm stop` and `qm start`.
- One worker fenced at a time.
- No lock is needed: the fencer works under the storage VM's own LIO lock. Do not run a fence while a cutover holds the
  maintenance lock unless the cutover is what needs it; tell the cutover's owner.
- The fencer token is fresh (D28): the last `storage.yml` run is green and newer than the last ansible `deploy.yml`
  run, and `StorageFencerBlind` is quiet. A manual fence needs no API; a manual unfence does.
- Outside every backup window (ansible `docs/backup-and-restore.md`, "Schedules") for a planned fence, unfence or `qm
  stop`. A fence for a hung worker does not wait for one; note the window in the evidence.
- Retained writers are not touched here, so no deny syncWindow. The taint evicts the worker's pods.

## Reading the fencer

1. `[S]` `storage-fencer status`. Prints the fence tags, the holds and the bootID history as JSON. Exit 1 when a fence
   tag is malformed or conflicting. Normal: `"fenced": {}` and `"holds": ["hold_fence"]`.
2. `[S]` `storage-fencer prove <node>`. A read-only proof as JSON: `acl_present` per target, `addr_in_set`,
   `established`. Exit 0 only when every leg passes (no ACL, address in the set, no socket).
3. `[S]` `journalctl -u storage-fencer -o short-iso --since -30min --no-pager | tail -200` `(not rehearsed)`. Lines
   that start with the dollar sign are the command trace. Loop reason lines, one per worker that is not Ready:
   - `<node>: not-ready-too-short` or `<node>: watch-too-short`: NotReady for less than 300 s, counted from the later
     of the NotReady time and the fencer's watch start (F18);
   - `<node>: foreign-va`: the worker still holds a VolumeAttachment of another driver (Proxmox CSI until
     Retirement). The fencer never taints it;
   - `<node>: hold_fence` (or `hold_create`): the hold blocks the new fence;
   - `<node>: no-peer`, `<node>: one-at-a-time`, `<node>: no-ready-condition`.

   Fence lines: `fence <node>: NotReady past 300 s`, `fence <node>: tagged, bootID not settled yet`,
   `fence <node>: deleted ACL <target>: <info>`, `fence <node>: proven`, `tainted <node>`,
   `fence <node>: settled on bootID <id>`, then each loop `<node>: seen-bootid` or `<node>: not-ready`.
   Unfence lines: `untainted <node>`, then `unfenced <node>`.
4. Alerts:
   - **`StorageWorkerFenced`**: a fenced worker needs a reboot. One that is Ready on its fenced bootID, or on one
     already seen, may be a resumed or rolled-back hung boot: reboot it (`qm reboot <vmid>`, **Ben OK**). Never
     unfence it by hand while it runs (F8).
   - **`StorageFenceFailed`**: a proof failed (no taint), or the loop could not get the LIO lock. It retries every
     loop. Read the `error: fence <node>: proof failed, no taint: {...}` line.
   - **`StorageFenceDraining`**: a fence's ACL deletes started over 2 minutes ago. LIO is waiting for the worker's
     queued commands, which a stalled disk holds (F23). That wait is the safety barrier: do not restart the fencer.
     If the fencer is not running, the gauge is stale, not a live drain.
   - **`StorageFencerBlind`**: no API success for 10 minutes, or a stale textfile. If `StorageFenceDraining` also
     fires, it is the same wait. A 401 after a k3s rebuild or a token rotation: dispatch `storage.yml` (**Ben OK**),
     which copies the new token and restarts the fencer (lab B6 Step 9).
   - **`NodeOutOfServiceTaintStuck`**: an out-of-service taint present for over 15 minutes. Check `status`: a taint
     with no `fenced:` tag is a leftover; one with a tag waits for the worker's reboot.

## Manual fence

For a worker that is lost or hung while `hold_fence` is set, or when the fencer refuses (for example with both
workers NotReady).

1. `[P]` `qm status <vmid> --verbose`. Note `status` and `qmpstatus`. A paused VM shows `running` with
   `qmpstatus: paused`.
2. `[S]` `storage-fencer fence <node>`. **Ben OK.**
   Expected (lab B6 Step 5 and Step 10): exit 0 and a proof that passes,
   `{"acl_present": {...all false}, "addr_in_set": true, "established": []}`. The VG `retained` gets
   `fenced:<node>:unknown`. The CLI never taints.
   - It needs no API and takes no bootID. A running fencer settles the tag on its next loop
     (`fence <node>: settled on bootID ...`). While the fencer is down the tag stays `unknown`.
   - An unknown name fails with `error: <name> is not a configured worker`, exit 1.
   - On a stalled backend the command waits, unkillable, until the disk answers (F23). It never sets the drain gauge,
     so `StorageFenceDraining` does not fire; a running loop shows the wait as `StorageFenceFailed`.
3. Taint, only after step 2 printed a passing proof. A taint before that lets a new writer mount while the old
   worker's queued writes can still land.
   - `[K]` `get node <node> -o jsonpath='{.spec.taints}'` `(not rehearsed)`. A running fencer finishes a manual
     fence, taint included, even under the hold, unless a foreign VolumeAttachment blocks it (ansible
     `fencer.py:4-5`). If the taint is already there, skip the next line.
   - Before Retirement the worker still holds Proxmox CSI volumes: follow "Migration-only qm stop before the taint"
     instead.
   - After Retirement: `[K]` `taint node <node> node.kubernetes.io/out-of-service=nodeshutdown:NoExecute`. **Ben OK.**
     `(not rehearsed)`
4. Expected after the taint: the worker's pods are evicted and force-detached, and they start on the other worker.
   The first mount waits for MMP (about 42 s, up to about 720 s on slow storage). Each app starts with its data at
   the last write it fsynced (lab: every move `contiguous=True` at the old pod's last ack).

## Migration-only qm stop before the taint

Until Retirement only (Ben, 2026-11-21, accepted for the migration). The taint force-detaches every driver's volumes,
and the storage fence proves nothing about Proxmox CSI disks.

1. `[K]` `get volumeattachments -o jsonpath='{range .items[*]}{.spec.attacher} {.spec.nodeName}{"\n"}{end}'`
   `(not rehearsed)`. If the worker has any VolumeAttachment whose attacher is not
   `org.democratic-csi.node-manual`, go on. If not, use "Manual fence" step 3 as after Retirement.
2. `[P]` `qm stop <vmid>`. **Ben OK.** A hard stop of a worker that is still alive loses its unfsynced writes, as in
   a crash.
3. `[P]` `qm status <vmid> --verbose`. Expected: `status: stopped` and `qmpstatus: stopped` (lab B6 Step 10b). Not
   `running`, and not `qmpstatus: paused`. If the stop fails, do not taint: the host reboot is the last resort.
4. `[K]` `taint node <node> node.kubernetes.io/out-of-service=nodeshutdown:NoExecute`. **Ben OK.**
   `(not rehearsed)`
5. Expected: PodGC removes the old pods. The retained pods restage on the other worker after the MMP wait. Proxmox CSI
   pods reschedule there too; any that the other worker has no free slot for stay Pending until the worker is back.
   Record them.

## Manual unfence

Every manual unfence, of an `unknown` or a settled tag, needs the VM proven off (F8). While the fencer runs, a worker
that really rebooted needs no manual unfence: the loop does it when the worker is Ready on a new bootID.

1. D28: after a k3s rebuild the fencer token is stale until the next `storage.yml` run, and `unfence` removes the
   taint through the API first. So with a stale token it fails with nothing changed. Dispatch `storage.yml` first.
   **Ben OK.** `[W]` `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main` `(not rehearsed)`.
   Expected: green, `Copy the storage-fencer token and CA` changed, the fencer restarted.
2. `[P]` `qm status <vmid> --verbose`. Expected: `status: stopped`.
3. `[S]` `storage-fencer unfence <node> --confirm-stopped`. **Ben OK.**
   Expected (lab B6 Step 10b): exit 0; the taint removed first, the worker's ACLs back on every target, the
   `fenced` set empty, and the tag gone last. Its log shows `untainted <node>` (when a taint was there) and
   `unfenced <node>`.
   - A bare `storage-fencer unfence <node>` exits 1 and changes nothing; it prints the `qm status` and
     `--confirm-stopped` hint.
   - `<node> is not fenced` with exit 0: nothing to do.
4. `[K]` `get node <node> -o jsonpath='{.spec.taints}'`: no out-of-service taint. Only if one is left, and `status`
   shows no tag for the node: `[K]` `taint node <node> node.kubernetes.io/out-of-service=nodeshutdown:NoExecute-`.
   **Ben OK.** `(not rehearsed)`
5. `[P]` `qm start <vmid>`. **Ben OK.**
   Expected: the worker Ready on a new bootID; `[S]` `storage-fencer status` shows `"fenced": {}`. Pods do not move
   back on their own. Delete `UnexpectedAdmissionError` GPU pods by name (memory `gpu-admission-race`), **Ben OK**.

## Unfence after a host cold boot

F18: after a host cold boot the API still shows each worker's NotReady from before the shutdown. The fencer counts
NotReady from its own watch start, so a normal cold boot fences nothing. With `hold_fence` set it cannot fence anyway.

If a worker is fenced after a boot anyway (a tag settled on its current bootID, or a fence that started on a boot that
was Ready only between two reads), it stays fenced while Ready: the fencer cannot tell it from a boot that mounted
before the cut.

1. `[S]` `storage-fencer status`. Note the tag and its bootID.
2. `[K]` the worker's pods are gone from it or Pending, and it has no retained VolumeAttachment, no pods using retained
   claims, and no iSCSI session.
3. Reboot it once more. **Ben OK.** `[P]` `qm reboot <vmid>`.
   Expected (lab B10): `untainted <node>`, the tag removed and `unfenced <node>` within about 16 s of the new boot
   turning Ready; the `fenced` set empty and the ACLs back.
4. With the fencer stopped, use "Manual unfence" instead.

## Before renumbering a worker bridge address

F7, accepted: changing a fenced worker's `bridge_address` makes `storage-fencer restore-set` drop the old address from
the `fenced` set. Established flows could then pass the nft rule again, and only the deleted ACLs still block them.

1. `[S]` `storage-fencer status`. Expected: the worker has no `fenced:` tag.
2. If it is fenced, unfence it first ("Manual unfence", or a reboot while the fencer runs).
3. Then change `bridge_address` (terraform `storage_nic` and the ansible worker list), one worker per PR, the worker
   drained first, as for adding a NIC. The worker keeps its name, so the run's worker check needs no `remove_workers`
   ("A worker missing from the inventory" below).

## A worker missing from the inventory

Every `storage.yml` run compares the installed `/etc/homelab-storage/config.json` with the rendered worker list before
it writes any config, nftables rule or ACL. A worker in the installed config but not in the list is refused:
`<worker> is in the installed config.json but not in the inventory (a Proxmox inventory drop-out?). Nothing was
changed.` Without this, its ACLs would go and its sessions with them. An unreadable installed config fails the same
way.

- **A drop-out** (the Proxmox API missed the guest; `inventory/proxmox.yml` lists it with only a warning). Refused in
  the dry run: no lock, nothing changed, and the next run retries. Refused under the lock (it dropped out after the
  dry run): the run keeps the lock (D31). Read the log, check that the guest is running and still carries its tags
  (`[P]` `qm config <vmid> | grep -E "^tags:"`), then release the lock as in ansible
  `docs/maintenance-lock-release.md`, **Ben OK**. The next run's dry run passing the worker check is the proof that
  the inventory sees it again; the inventory itself needs the Proxmox token, which only the workflow has (D51).
- **A deliberate removal** (a worker that leaves for good). **Ben OK** for each step `(not rehearsed)`:
  1. Drain it: no Pod of a retained app on it, `[N]` `iscsiadm -m session` on it lists no session to the storage VM,
     and `[S]` `storage-fencer status` shows no `fenced:` tag for it (unfence first, as above).
  2. Remove it from the inventory (its PR), then dispatch one run that names it, `[W]`
     `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main -f remove_workers=<name>`. The input takes
     names separated by commas or spaces, for that run only.
  3. Expected: green; its ACLs are gone from every target and its address from the nft allow. A worker named there
     that still has a session is not cut off: the reconcile refuses that target (`not removing the ACL of <iqn>: it
     has an iSCSI session`), the run fails and keeps the lock (D31). Go back to step 1, then release the lock.

## Undo

- A manual fence: "Manual unfence" once the VM is proven stopped, or a reboot while the fencer runs.
- A taint applied too early (before a passing proof): remove it at once with the `taint ... NoExecute-` line, then
  bring it to Ben. Do not let a pod mount on the other worker meanwhile.
- An unfence cannot be undone except by a new fence.

## Evidence

- Write to `~/.cache/claude-homelab-live/storage-migration/evidence/<task>/` (Task 3.10: `fence.txt`, `move.txt`,
  `post.txt`): every command's output, the `status` JSON before and after, and the fencer journal lines.
- Sources: ADR 0017, Hang policy (Manual fallback, Visibility, Fences survive restarts and reloads); migration plan
  Task 3.10, D28; ansible `roles/storage_vm/files/homelab_storage/fencer.py`, `fence_policy.py:105-126`.
- Lab: report `:399-572` (B6, F7 and F8 fixes); `storage-lab/b6/notes.md` Steps 5, 9, 10 and the F7/F8 re-run.
- Lab: `storage-lab/b6/runbook.md` (written from code before the run), `b6-s7-reconcile.txt`, `b6-s7a-undo.txt`.
- Lab: `storage-lab/f7f8-install.txt`, `f7f8-render.txt`, `f7f8-undo.txt`.
- Lab: `storage-lab/b10/notes.md:32-38` (F18, the unfence by reboot).
