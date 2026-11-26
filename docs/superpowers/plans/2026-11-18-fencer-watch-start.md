# Fencer watch start (F18) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A stale NotReady never starts a fence: rule 2 counts NotReady only from the fencer's watch start.

**Architecture:** `Fencer` keeps `watch_start`: the API server time of its first successful loop read, reset to `None`
by any loop whose API read fails. `fence_policy.evaluate` takes it and measures NotReady from
`max(lastTransitionTime, watch_start)`.

**Tech Stack:** Python 3 stdlib, unittest (ansible repo, `roles/storage_vm/files/homelab_storage`).

**Spec:** `docs/superpowers/specs/2026-11-18-fencer-watch-start-design.md` (apps-adr-0017 worktree).

## Global Constraints

- All ages use the API server's clock (the Date header `server_time`), never the storage VM's.
- No change to settle, unfence, holds, manual fences, or the order of the loop's steps.
- Never fence sooner than today: the watch start can only delay a fence.
- Work on ansible `feat/retained-storage-vm` in `~/.cache/claude-homelab-live/worktrees/ansible-storage-vm`; commit nothing.

## Review Focus

1. A fencer restart while a worker is already fenced: the watch start must not touch continue-fence, settle or unfence.
2. A loop that fails after the API read (an exception in the decision) must not reset the watch start; only a failed read does.
3. A worker whose NotReady began after the watch start: today's timing, unchanged.
4. A restart while a worker is NotReady: it is fenced `not_ready_seconds` after the new watch start, not never.
5. The log names why a fence waits (`watch-too-short`), so a delayed fence is visible in the journal.

---

### Task 1: watch start in the policy and the loop

**Files:**
- Modify: `roles/storage_vm/files/homelab_storage/fence_policy.py` (`evaluate`)
- Modify: `roles/storage_vm/files/homelab_storage/fencer.py` (`Fencer.__init__`, `loop_once`, `_decide_and_act`)
- Test: `scripts/tests/test_storage_fence_policy.py`, `scripts/tests/test_storage_fencer.py`

**Interfaces:**
- Produces: `fence_policy.evaluate(nodes, vas, cluster, history, cfg, server_time, opened, watch_start)`;
  `watch_start` is a tz-aware `datetime`. Reason `watch-too-short` when the watch start is the later bound and the
  window has not passed; `not-ready-too-short` keeps its meaning otherwise.
- Produces: `Fencer.watch_start` (`None` until the first successful read).

- [ ] **Step 1: Write the failing tests.**
  - Policy helper `evaluate(...)` gains `watch=NOW - timedelta(days=1)` and passes it as `watch_start`.
  - `test_watch_start_bounds_stale_notready`: `node('w2', ready=False, age=10000)` with `watch=NOW - timedelta(seconds=299)`
    gives `v.fence is None` and `v.reasons['w2'] == 'watch-too-short'`; with `seconds=300` gives `v.fence == 'w2'`.
  - `test_later_transition_keeps_its_window`: `age=299`, `watch=NOW - timedelta(days=1)` gives `not-ready-too-short`.
  - Fencer: `FakeApi.now` (default `SERVER_NOW`) replaces the three `SERVER_NOW` returns. `Base.loop()` and
    `Base.running()` set `watch_start = SERVER_NOW - timedelta(days=1)` on a Fencer they create, unless `fresh=True`.
  - `test_cold_boot_stale_notready_not_fenced`: `hung_w2()` with `age=10000`, `self.loop(fresh=True)`: no fence tags,
    `'w2: watch-too-short'` in the log; set `f.api.now = SERVER_NOW + timedelta(seconds=300)`, loop again: fence tag
    `fenced:w2:unknown`.
  - `test_failed_read_resets_watch_start`: a watching fencer, w2 NotReady `age=200`; one loop with `f.api.error` set;
    clear it, `now = SERVER_NOW + 150 s`: no fence (`watch-too-short`); `now = SERVER_NOW + 450 s`: fenced.
  - `test_restart_keeps_existing_fence`: a settled fence on w2 and a fresh fencer (`fresh=True`): the first loop still
    runs fence steps 2-6 (continue-fence) exactly as `test_restart_unsettles` expects.
- [ ] **Step 2: Run** `python3 scripts/tests/test_storage_fence_policy.py` and `test_storage_fencer.py`. Expected:
  the new tests FAIL (TypeError on `watch_start`, or a fence on the first loop).
- [ ] **Step 3: Implement.** `evaluate` uses `max(since, watch_start)` and picks the reason by which bound won.
  `loop_once`: after a successful read, `if self.watch_start is None: self.watch_start = server_time`; on the read's
  `ApiError`, `self.watch_start = None` before returning. `_decide_and_act` passes it to `evaluate`. Update the module
  docstring and the ADR reference comment in `evaluate`.
- [ ] **Step 4: Run** every `scripts/tests/test_storage_*.py`. Expected: all OK.
- [ ] **Step 5: No commit** (Ben commits later). Record the change in the lab notes.

### Task 2: ADR rule 2 and the report

**Files:**
- Modify: apps-adr-0017 `docs/adr/0017-retained-block-storage-vm-iscsi.md` (fence rule 2, "Planned events need nothing")
- Modify: `docs/superpowers/reports/2026-11-16-retained-storage-lab-results.md` (F18 fix line)

- [ ] **Step 1:** Rule 2 becomes: NotReady for at least 5 minutes, measured from the later of `lastTransitionTime`
  and the fencer's watch start (its first successful API read after it starts or after a failed read). Add one line
  under "Planned events": a host cold boot does not fence, because the API's NotReady from before the shutdown
  predates the watch start; the cost is up to 5 more minutes before a real hang is fenced after a fencer restart or
  an API outage.
- [ ] **Step 2:** In the report's F18 paragraph, replace "The fix direction is open." with the fix and "lab re-test
  pending".
