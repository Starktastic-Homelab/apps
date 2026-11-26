# F23 Fence Drain Wait Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the fence's synchronous ACL-delete drain wait, delete retained ACLs first, and alert when a fence's ACL
deletes have waited over 2 minutes.

**Architecture:** `lio.delete_acl` orders targets retained-first with a never-raising key. The fencer loop publishes a
per-worker gauge with the time its ACL delete started (0 when none), written through the existing whole-textfile
`write_metrics`, guarded so a metrics fault never stops a fence. An apps PrometheusRule alert fires on that gauge.

**Tech Stack:** Python 3 (stdlib unittest), rtslib-fb (faked), PrometheusRule YAML, promtool v3.16.0 via Docker.

**Spec:** `~/.cache/claude-homelab-live/worktrees/apps-adr-0017/docs/superpowers/specs/2026-11-18-fence-drain-wait-design.md`

## Global Constraints

- Worktrees: ansible code and tests in `~/.cache/claude-homelab-live/worktrees/ansible-storage-vm` (branch
  `feat/retained-storage-vm`, uncommitted, mixed with earlier work); alert in `~/.cache/claude-homelab-live/worktrees/apps-storage-vm`;
  docs in `~/.cache/claude-homelab-live/worktrees/apps-adr-0017/docs`. **No commits** until Ben asks.
- Gauge name exactly `storage_fence_acl_delete_started_timestamp_seconds{node}`; 0 = no ACL delete running; one sample
  per configured worker.
- Alert name `StorageFenceDraining`, severity `critical`, no `for:`, expr exactly
  `0 < storage_fence_acl_delete_started_timestamp_seconds{job="storage-vm"} < time() - 120`.
- Regen test: LUN 0 backstore `udev_path` starts with `/dev/regen/`; order key `(is_regen, wwn)`; any exception reading
  it = not regen.
- Gauge is set after checkpoint `fence:2` (nft cut) and immediately before `lio_.delete_acl`; reset to 0 when
  `delete_acl` returns or raises; both writes `try/except` logging `error: metrics: <e>`; the reset never replaces the
  delete's exception.
- Manual `fence`/`unfence` never write the textfile.
- Storage suite: `~/.cache/claude-homelab-live/venv/bin/python3 -m unittest discover -s scripts/tests -p 'test_storage*.py'`
  (247 OK before this plan).

## Review Focus

1. A textfile write that raises (missing or read-only dir) during a fence: the fence still deletes the ACL and runs its
   proof. Test: Task 2 `test_metrics_failure_never_stops_fence`.
2. A freshly started fencer with an already tagged worker: the mid-fence textfile shows `storage_fence_active` 1 for it.
   Test: Task 2 `test_mid_fence_write_keeps_active`.
3. `continue_fence` re-running `fence_steps` every loop for a cut worker: the gauge is 0 after every loop and never
   carries an old start. Test: Task 2 `test_gauge_resets_each_loop`.
4. A target with no LUN 0 or a broken LUN link: sorts with retained and its ACL is still deleted. Test: Task 1
   `test_unreadable_lun_sorts_retained`.
5. Manual `fence` while the loop runs: writes no textfile. Test: Task 2 `test_manual_fence_writes_no_textfile`.

---

### Task 1: Retained-first ACL deletes

**Files:**
- Modify: `roles/storage_vm/files/homelab_storage/lio.py` (`delete_acl`, new helper)
- Test: `scripts/tests/test_storage_reconcile.py` (new class `LioOrderTest`, next to the existing `test_save_is_atomic` class)

**Interfaces:**
- Produces: `lio.Lio.delete_acl(acl_iqn) -> list[dict]` (unchanged signature and return), deletes in `(is_regen, wwn)` order;
  module function `lio._is_regen(target) -> bool` (never raises).

- [ ] **Step 1: Write the failing tests.** Fake rtslib via `mock.patch.dict(sys.modules, {'rtslib_fb': fake})` with
  `FabricModule('iscsi').targets` returning targets in the order regen-b, retained-c, retained-a (wwns
  `lio.iqn('b')` etc.); each target has one tpg (`tag=1`) with `node_acls` = one ACL for `W2` whose `delete()` appends
  the target id to a shared list, `path` = a tmp dir with an `info` file, and `luns` = one LUN 0 whose
  `storage_object.udev_path` is `/dev/regen/b`, `/dev/retained/c`, `/dev/retained/a`.
  - `test_retained_first`: `lio.Lio().delete_acl(W2)` deletes `['a', 'c', 'b']`, and the returned list's `target` values
    are in the same order.
  - `test_unreadable_lun_sorts_retained`: target `d`, listed first, has a LUN whose `storage_object` property raises
    `RuntimeError` and target `e` has no LUN 0; with regen `b`: order `['d', 'e', 'b']`, all three deleted.
- [ ] **Step 2: Run** `... -m unittest test_storage_reconcile.LioOrderTest` from `scripts/tests`. Expected: FAIL (listing
  order `['b', 'c', 'a']`).
- [ ] **Step 3: Implement** `_is_regen(t)`: True only if tpg tag 1's LUN 0 `storage_object.udev_path` starts with
  `/dev/regen/`; `except Exception: return False`. `delete_acl` iterates `sorted(self._targets(), key=lambda t:
  (_is_regen(t), t.wwn))`, computed before the first delete. Docstring line: retained first, so its sessions are torn
  down before a regen drain (ADR 0017 F23).
- [ ] **Step 4: Run** the class, then the whole storage suite. Expected: PASS, 249 OK.

### Task 2: Drain gauge in the fencer

**Files:**
- Modify: `roles/storage_vm/files/homelab_storage/fencer.py` (`fence_steps`, `_decide_and_act`, `write_metrics`, `__init__`)
- Test: `scripts/tests/test_storage_fencer.py` (new class `DrainGaugeTest(Base)`)

**Interfaces:**
- Consumes: `lio.Lio.delete_acl` (Task 1, unchanged signature).
- Produces: `Fencer.fence_steps(lio_, name, tagged, taint, report=False)`; `Fencer.acl_delete_started: dict[str, float]`;
  textfile sample `storage_fence_acl_delete_started_timestamp_seconds{node="<w>"}` for every worker in `self.addrs`.

- [ ] **Step 1: Write the failing tests** (use `hung_w2`, `loop`, `prom`; snapshot the textfile from inside the fake
  `delete_acl` by wrapping the FenceHost FakeLio's `delete_acl` with `mock.patch.object`):
  - `test_gauge_set_during_delete`: during w2's `delete_acl`, `prom()` has the w2 gauge with a value within 5 s of
    `time.time()` and the w1 gauge `0`; after `loop()`, both are `0`.
  - `test_gauge_reset_when_delete_raises`: fake `delete_acl` raises `OSError('rmdir')`; after the loop the w2 gauge is
    `0`, `storage_fence_failures_total 1`, and `self.err` contains `rmdir`.
  - `test_metrics_failure_never_stops_fence`: `metrics.write` patched to raise `OSError('ro')` only while the fake
    delete has not run yet (first call during the fence); the ACL is still deleted (`lio.delete_acl` recorded), the proof
    ran, and `self.err` contains `error: metrics: ro`.
  - `test_mid_fence_write_keeps_active`: fresh `Fencer` (via `running()`), w2 already tagged `fenced:w2:<A>` and still
    cut; snapshot during `delete_acl` shows `storage_fence_active{node="w2"} 1`.
  - `test_gauge_resets_each_loop`: two loops of a tagged, cut w2 (continue_fence path): after each, the w2 gauge is `0`;
    the two in-delete snapshots differ in value.
  - `test_manual_fence_writes_no_textfile`: `cli('fence', 'w2')` leaves no `textfile/storage-fencer.prom`.
- [ ] **Step 2: Run** `... -m unittest test_storage_fencer.DrainGaugeTest`. Expected: FAIL (no gauge sample).
- [ ] **Step 3: Implement.**
  - `__init__`: `self.acl_delete_started = {}`.
  - `write_metrics`: add `('storage_fence_acl_delete_started_timestamp_seconds', {'node': w},
    self.acl_delete_started.get(w, 0))` for each `w in sorted(self.addrs)`.
  - `fence_steps(..., report=False)`: after `host.checkpoint('fence:2')`, if `report`: set
    `self.acl_delete_started[name] = time.time()` and call a new `_report()` (wraps `write_metrics()` in
    `try/except Exception as e: host.log(f'error: metrics: {e}')`); run the delete loop in `try: ... finally:` that, if
    `report`, pops the entry and calls `_report()`.
  - `_decide_and_act`: right after `fenced = cluster.fenced()`, set `self.active = set(fenced)`; pass `report=True` at
    both `fence_steps` call sites.
- [ ] **Step 4: Run** the class, then the whole storage suite. Expected: PASS, 255 OK.

### Task 3: StorageFenceDraining alert

**Files:**
- Modify: `services/operations/kube-prometheus-stack/manifests/storage-vm.yaml` (new rule after `StorageFenceFailed`;
  `StorageFencerBlind` description)
- Test: `scripts/check-alert-policy.py` (`storage_tests` list)

**Interfaces:**
- Consumes: the Task 2 gauge name and labels.

- [ ] **Step 1: Add the promtool cases** to the `storage_tests` list (each its own group; eval `30m`), using the file's
  `S` label string:
  - fires: series `storage_fence_acl_delete_started_timestamp_seconds{S,node="worker-02"}` `60x30` and the same for
    `node="worker-01"` `0x30`; expected one sample `{__name__="storage_fence_acl_delete_started_timestamp_seconds",S,node="worker-02"}` value `60`;
  - no alert: `1740x30`; `1680x30`; `0+60x30` (each with expected `[]`).
- [ ] **Step 2: Run** `python3 scripts/check-alert-policy.py docker run --rm -i --network none --entrypoint promtool prom/prometheus:v3.16.0`
  (if Helm is missing on PATH, use the cached `alpine/helm:4.3.1` wrapper from memory `workstation-offline-checks`).
  Expected: FAIL (no rule `StorageFenceDraining`).
- [ ] **Step 3: Add the rule** with the Global Constraints expr; a YAML comment: `# 120 s > proof_timeout_seconds (60 s)
  + 2 x 5 s API calls; revisit if the proof timeout grows`; summary `The fence of {{ $labels.node }} has waited over 2
  minutes for its storage`; description `The storage behind {{ $labels.node }}'s volumes is not answering (since {{
  $value | humanizeTimestamp }}). The fence finishes, and the worker fails over, when it answers; nothing is tainted
  until then. Do not restart the fencer or the storage VM: the wait cannot be interrupted. StorageFencerBlind follows
  after 10 minutes for the same wait. If the fencer is not running, the gauge is stale, not a live drain.` Append to
  `StorageFencerBlind`'s description: ` If StorageFenceDraining is firing, this is the same wait: do not restart the
  fencer.`
- [ ] **Step 4: Run** the Step 2 command. Expected: PASS, and the apps storage tests
  (`scripts/storage/tests`) still OK.

### Task 4: Docs

**Files:**
- Modify: `docs/adr/0017-retained-block-storage-vm-iscsi.md` (named residuals "a lab question" item; the alert list
  where `StorageFencerBlind` is described)
- Modify: `docs/superpowers/reports/2026-11-16-retained-storage-lab-results.md` (F23 paragraph)

- [ ] **Step 1: ADR.** Replace the item-8 "a lab question" residual with the rule from the spec's Design 4 (wait for
  the hung worker's outstanding commands; D state, cannot be killed; nothing tainted until it ends; other `LIO_LOCK`
  users give up after 120 s; `StorageFenceDraining` after 2 minutes; storage-VM shutdown and manual targetcli wait;
  retained-first is best effort; one-at-a-time already forbids a second fence; reconcile `ensure_target` is a second
  drain site, seen as `StorageFenceFailed`). Add `StorageFenceDraining` wherever the ADR lists the fence alerts, with
  the stale-gauge note.
- [ ] **Step 2: Report.** F23: cause = the drain wait; replace "other fences wait" with `restore-set`, the reconcile,
  manual commands, and the same worker's settle and taint; status line "2026-11-18: kept by design (Ben, approach A),
  StorageFenceDraining added; lab re-check pending".
- [ ] **Step 3: Fact-check.** `grep -n 'StorageFenceDraining\|acl_delete_started'` across the three worktrees names
  the same strings; no "other fences wait" left.

### Task 5: Lab re-check (each step needs Ben's OK in this session)

- [ ] Deploy `storage.yml` to the lab (role overlay recipe, `memsize/f11deploy.sh`).
- [ ] Repeat the F23 leg (`memsize/f11s1.sh` shape, but let the fencer LOOP fence the hard-stopped worker after `not_ready_seconds`: a manual fence never sets the gauge) with the spec's Lab check probes; record in
  `storage-lab/b8/f11-retest.md`. Pass: gauge for lab-agent set during the stall and 0 after; retained `acls/` lists no
  lab-agent IQN during the stall; "deleted ACL" lines after the drain, regen last.
- [ ] Backstop check (spec Design 3, last bullet): read where the planned production storage VM's root disk lives (terraform
  `modules/vm` and the plan of record, no live call). If it is on `k3s-block`, note in the ADR that `StorageVMDown` is the backstop.
