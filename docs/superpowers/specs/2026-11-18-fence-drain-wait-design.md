# F23: the fence's drain wait, kept and made visible (short design)

Date: 2026-11-18. Status: draft for Ben. Lab finding F23 (spec item 8 of
`2026-11-18-storage-vm-lvm-isolation-design.md`). Research: `storage-lab/b8/f23-research.json`; design check
2026-11-18 (code and alert reviewers; promtool v3.16.0 run on the expression and cases).

## Intent

In the lab, a fence of a hard-stopped worker whose regen I/O was in flight blocked on the regen ACL delete for the whole
regen stall (~2 min), holding `LIO_LOCK`. The research (Linux v6.12 LIO and configfs source, rtslib-fb) shows this wait
is the safety mechanism: the ACL rmdir returns only after LIO has finished the dead worker's queued commands, and those
finish only when the stalled disk answers. Until then nothing is tainted, so no new writer can mount while the old writes
can still land. The nft cut stops new packets only. Ben chose to keep the wait (approach A, 2026-11-18) and to add an
alert that fires while a fence is stuck draining; today nothing fires until the fencer's textfile is 600 s stale.

## Goals

- Keep the synchronous ACL delete under `LIO_LOCK` as a deliberate drain barrier.
- A fence whose ACL deletes have not finished after 2 minutes raises `StorageFenceDraining`.
- Retained sessions are torn down before the regen drain: retained ACLs are deleted first (best effort; when both
  backends stall, the retained delete can itself be the one that waits). No failover gain is claimed.
- The ADR and the lab report state the wait as a rule, with the right cause.
- A monitoring fault (textfile write, an odd LUN) never stops a fence from cutting.

## Non-goals and anti-goals

- No faster failover during a stall: the proof cannot pass before the drain (the target-side socket stays ESTABLISHED
  and listing the target's `acls/` blocks), and the taint is per node.
- No out-of-process ACL deletes, no separate regen portal (approach B), no soft mounts or QEMU error policy (approach C).
- No change to the reconcile's per-target ACL order (`Executor.target` -> `ensure_target`); it is a second drain site
  with no gauge, where the fencer loop's 120 s lock timeouts raise `StorageFenceFailed` instead.
- Anti-goal: anything that lets the taint go on before the dead worker's queued writes are released.

## Approaches

- **A, keep the wait and document it, plus an alert gauge (Ben's pick).** Fails closed, smallest change. Cost: while a
  backend stalls, that worker's failover waits, and `restore-set`, the reconcile, manual LIO commands and the storage
  VM's shutdown wait behind it (lock users give up after 120 s). In production both data disks sit on the same
  `k3s-block` NFS mount, so a real stall freezes retained too and the extra cost is small.
- B, regen on its own portal with an abandoned child for its ACL delete: frees retained failover from a regen-only stall,
  but the per-node taint would fail over that worker's regen volumes before their drain (stale-write risk), and the portal
  becomes part of PV identity. Not taken.
- C, bound the stall below LIO (soft NFS, QEMU `werror`): a shared mount would hand retained I/O errors. Not taken.

## Design

1. **Retained first.** `lio.Lio.delete_acl` builds its target order before the first delete, keyed on
   `(is_regen, wwn)`: `is_regen` is true when LUN 0's backstore `udev_path` starts with `/dev/regen/`. Any exception while
   reading it (no LUN 0, a broken LUN link, `RTSLibNotInCFS`) counts as not regen, so the target is deleted early and the
   sort can never stop a delete. Reading LUNs never touches `acls/`. `boot_check` uses `delete_acl`, so it gets the order.
2. **Gauge `storage_fence_acl_delete_started_timestamp_seconds{node}`** (0 = no ACL delete running), one sample per
   configured worker, emitted by `write_metrics` with the rest of the fencer's samples (the textfile is replaced whole;
   a gauge-only write would drop the other series and trip `StorageFencerBlind`'s `absent()`).
   - `fence_steps(..., report=False)`: the two loop call sites in `_decide_and_act` pass `report=True`; manual `fence`
     does not, keeping its rule of never writing the textfile (a stuck manual fence shows as the loop's lock failures).
   - With `report`, after the nft cut (checkpoint `fence:2`) and just before `delete_acl`: set the node's start time to
     now and call `write_metrics()`; when `delete_acl` returns or raises, set 0 and write again. Both writes are in
     `try/except` that logs `error: metrics: ...` and carries on; the reset never hides the delete's own exception.
     Placing it after the cut means a slow textfile write can never delay the cut, and the 120 s measures only the ACL
     deletes (instant on a healthy backend), not the LVM tag write or the proof poll.
   - `self.active` is set to the tagged workers at the top of `_decide_and_act` (and recomputed at its end as today), so a
     mid-loop write never publishes `storage_fence_active 0` for a fenced worker (after a fencer restart it is empty).
3. **Alert `StorageFenceDraining`** (apps `storage-vm.yaml`, severity critical like the other fence alerts, no `for:`):
   `0 < storage_fence_acl_delete_started_timestamp_seconds{job="storage-vm"} < time() - 120`. Summary: the fence of
   `{{ $labels.node }}` has waited over 2 minutes for its storage. Description: the storage behind the worker's volumes is
   not answering (since `{{ $value | humanizeTimestamp }}`); the fence finishes, and the worker fails over, when it does;
   nothing is tainted until then; do not restart the fencer or the storage VM (the wait cannot be interrupted);
   `StorageFencerBlind` follows after 10 minutes for the same wait. A rule comment ties 120 s to
   `proof_timeout_seconds` (60 s in production): a later increase of that timeout gets a second look.
   - The textfile collector exports a file that is not rewritten, so the frozen start time keeps the alert firing.
   - `StorageFencerBlind`'s description gains: "If StorageFenceDraining is firing, this is the same wait: do not
     restart the fencer." No inhibit rule: if the fencer really dies, Blind is the alert that is right.
   - A fencer that exits with the gauge set leaves it set until its next loop rewrites the file (or Blind fires at
     600 s); the runbook line says "Draining plus a fencer that is not running" means a stale gauge, not a live drain.
   - If the production storage VM's root disk (and so the textfile and node exporter) is on `k3s-block`, a full stall
     can stop scrapes; `StorageVMDown` is then the backstop. To verify on the production VM config before deploy.
4. **Docs.**
   - ADR 0017: the "a lab question" residual becomes a rule: a fence waits for the hung worker's outstanding commands on
     a stalled backend; the wait cannot be killed (D state); nothing is tainted until it ends; other `LIO_LOCK` users give
     up after 120 s and fail closed; `StorageFenceDraining` fires after 2 minutes; the storage VM's shutdown and manual
     targetcli commands also wait; retained-first is best effort; `one-at-a-time` already forbids a second fence; the
     reconcile's ensure_target is a second drain site.
   - Lab report F23: the cause is the drain wait, not the nft order; replace "other fences wait" with what does wait
     (`restore-set`, the reconcile, manual commands, the same worker's settle and taint).
   - Alert runbook lines for `StorageFenceDraining` and the Blind note.

## Tests (RED first)

- `lio.delete_acl`: a fake rtslib lists a regen target first; deletes happen retained first, then regen, in wwn order; a
  target whose `storage_object` raises sorts with retained and every ACL is still deleted.
- Fencer: during the fake `delete_acl` the textfile already holds the gauge for w2 > 0 and `storage_fence_active` 1 for
  w2 (fresh `Fencer`, tagged w2); after the loop the gauge is 0; a raising `delete_acl` also leaves 0 and the error
  propagates; a raising `metrics.write` still deletes the ACL and runs the proof; manual `fence` writes no textfile.
- Alert policy (`scripts/check-alert-policy.py` `storage_tests`, promtool, eval at 30m where `time()` is 1800):
  fires for `node="worker-02"` series `60x30` with `worker-01` at `0x30` idle (one sample, value 60); no alert for
  `1740x30` (60 s old), `1680x30` (exactly 120 s, strict), `0+60x30` (a new start each minute, repeated failed proofs).

## Lab check (later, each step needs Ben's OK)

Repeat the F23 leg with the new code. During the stall: the textfile shows the gauge for lab-agent; `timeout 5 ls` of a
retained target's `acls/` shows no lab-agent IQN (retained already cut); `/proc/<pid>/stack` of the waiting fencer;
`timeout 5 ls` of the regen `acls/` (expected to block); `ss` shows the worker's regen :3260 connection still
ESTABLISHED. The "deleted ACL" log lines appear together after the drain, regen last. After: gauge 0, alert resolved.

## Left to the builder

Metric help text, test names, and where the in-progress dict lives on `Fencer`.
