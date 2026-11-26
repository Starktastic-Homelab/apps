# Storage VM LVM Isolation (F11, F12) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A regen-only disk fault never hangs a retained-only command. Every LVM command and every `LIO_LOCK` wait is bounded. After a regen fault clears, the next run is clean with no `pvscan`.

**Architecture:**
- Every LVM command names one VG and passes only that VG's PV via `--devices`, which also turns hints off.
- `host.run` gains a timeout that abandons the child instead of killing it, and a per-key rule: while an abandoned child for a VG is alive, later calls for that VG fail at once.
- The fencer and restore-set read retained tags only. `plan.py` is unchanged (approach A).

**Tech Stack:** Python 3 stdlib (`subprocess`, `tempfile`, `fcntl`), Ansible role templates, systemd drop-ins, `unittest`.

**Spec:** `~/.cache/claude-homelab-live/worktrees/apps-adr-0017/docs/superpowers/specs/2026-11-18-storage-vm-lvm-isolation-design.md`. Ben approved it on 2026-11-18.

**Worktree:** `~/.cache/claude-homelab-live/worktrees/ansible-storage-vm` (branch `feat/retained-storage-vm`, already 25 uncommitted files). All paths below are relative to it unless they start with `~`. Docs live in `apps-adr-0017`.

**Test command:** `~/.cache/claude-homelab-live/venv/bin/python3 -m unittest discover -s scripts/tests -p 'test_storage*.py'`. The baseline is 196 tests, OK.

## Global Constraints

- Retained data: never force-detach, recreate or reformat images; never drop RWOP, `Retain`, prune protection or a source hold; never fake markers to pass a guard.
- Never kill an LVM write or activation. A timed-out child is left running and never waited on (spec, Anti-goals).
- `LVM_TIMEOUT = 30` seconds per VG read (`vgs` and `lvs` share one deadline) and per LVM write.
- `LIO_LOCK` wait deadline is 120 s. The `systemctl start rtslib-fb-targetctl` limit is 300 s.
- Lab commands over QGA are ASCII only. Never print tokens, CHAP secrets, nonces or `pve.env` values.
- Every lab mutation needs Ben's explicit OK for that step. The clock gate (`clock_ok`) applies: never 01–06; not :20–:50 of 03/09/15/21; not across :55–:04.
- No commits, pushes or PRs. Changes stay uncommitted on the branch until Ben asks.
- While the lab holds the production lock (`lab/storage-2026-11-16`), there are no ansible, terraform or packer merges.

## Review Focus

1. **The regen PV path disappears at runtime** (slot link gone, disk detached). Expected: regen reads `present=False` with `VG regen unreadable on <pv>` in the log, and retained reads are unaffected. Pinned in Task 4: `test_missing_pv_is_absent_not_raise`.
2. **The retained read times out inside the fencer loop.** Expected: a counted loop failure with no fence, unfence or nft action, and metrics still written. Pinned in Task 5: `test_retained_timeout_is_loop_failure`.
3. **An abandoned child exits later with a nonzero rc.** Expected: a later call reaps it and logs the rc. Nothing raises into that unrelated call, and the key is free again. Pinned in Task 2: `test_late_failure_is_logged_on_reap`.
4. **The lock deadline is hit in the fencer loop.** Expected: a loop failure with metrics written, and the next loop runs normally. Pinned in Task 5: `test_lock_timeout_is_loop_failure`.
5. **The deployed config.json predates `pv_devices`.** Expected: `ConfigError` and exit 1 from both CLIs. The boot retained line still activates retained through its unscoped fallback. Pinned in Task 3 (`test_pv_devices_required`) and Task 7 (`test_dropin_retained_fallback`).

---

Spec coverage:

| Spec item | Task |
|---|---|
| 1 | 2 |
| 2 | 3 and 4 |
| 3 | 5 |
| 4 | 6 |
| 5 | 2, 5 and 7 |
| 6 | 1 and 3 |
| 7 | 6 and 7 |
| 8 | 9, step 1 |
| 9 and the ADR | 8 |

### Task 1: Read-only lab facts (needs Ben's OK)

**Files:**
- Write: `~/.cache/claude-homelab-live/storage-lab/b8/f11-step0.md`

**Interfaces:**
- Produces: the exact by-path link names for 971's virtio1 (retained) and virtio2 (regen). Task 3 uses them as the role defaults.

- [ ] **Step 1: Ask Ben for an OK to run read-only commands on 971 via the lab helper**

- [ ] **Step 2: Run on 971 (sudo, ASCII) and save the output to `f11-step0.md`**
  - `ls -l /dev/disk/by-path`
  - `pvs -o pv_name,vg_name --noheadings`
  - `systemctl cat rtslib-fb-targetctl nftables lvm2-monitor`
  - `systemctl show -p Type,KillMode,TimeoutStartUSec,TimeoutStopUSec,LimitNOFILE rtslib-fb-targetctl storage-fencer`
  - `lvmconfig --typeconfig full activation/event_activation activation/auto_activation_volume_list`
  - for each VG: `vgs --devices <link> --readonly --noheadings -o vg_name <vg>`
  - `lslocks` while the previous command runs (backgrounded with `sleep`)

  Expected:
  - two `pci-…` links that resolve to `vdb` and `vdc`;
  - each scoped `vgs` prints its own VG;
  - Type is `oneshot`;
  - no LVM entry in `lslocks`.

  If any of these fails, stop and report to Ben.

---

### Task 2: Bounded `host.run` and bounded `Flock`

**Files:**
- Modify: `roles/storage_vm/files/homelab_storage/host.py`
- Test: `scripts/tests/test_storage_host.py` (new)

**Interfaces:**
- Produces:
  - `host.run(argv, check=True, timeout=None, key=None) -> subprocess.CompletedProcess`. It raises `subprocess.TimeoutExpired` on a timeout, or at once when `key` has a live abandoned child.
  - `host.Flock(path, timeout=120)`, whose `__enter__` raises `TimeoutError` after the deadline.

- [ ] **Step 1: Write the failing tests** (real subprocesses, `sleep`/`sh`)

```python
def test_timeout_abandons_child(self):
    with self.assertRaises(subprocess.TimeoutExpired):
        host.run(['sleep', '5'], timeout=0.2, key='regen')
    pid = host._ABANDONED['regen'].pid
    os.kill(pid, 0)                       # still alive: not killed

def test_parent_holds_no_output_fd(self):
    before = set(os.listdir('/proc/self/fd'))
    with self.assertRaises(subprocess.TimeoutExpired):
        host.run(['sleep', '5'], timeout=0.2, key='k')
    self.assertEqual(set(os.listdir('/proc/self/fd')), before)

def test_live_key_raises_without_child(self):
    with self.assertRaises(subprocess.TimeoutExpired):
        host.run(['sleep', '5'], timeout=0.2, key='regen')
    with mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('started a child')):
        with self.assertRaises(subprocess.TimeoutExpired):
            host.run(['vgs', 'regen'], timeout=30, key='regen')

def test_other_key_unaffected(self):
    # with a live 'regen' child, a 'retained' call runs normally
    ...
    self.assertEqual(host.run(['true'], timeout=5, key='retained').returncode, 0)

def test_late_failure_is_logged_on_reap(self):
    with self.assertRaises(subprocess.TimeoutExpired):
        host.run(['sh', '-c', 'sleep 0.3; exit 5'], timeout=0.1, key='regen')
    time.sleep(0.5)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        host.run(['true'], timeout=5, key='regen')   # reaps, key free, no raise
    self.assertIn('exited 5 after it was abandoned', err.getvalue())

def test_no_timeout_unchanged(self):
    r = host.run(['sh', '-c', 'echo hi'])
    self.assertEqual(r.stdout, 'hi\n')

def test_flock_deadline(self):
    path = Path(self.tmp, 'lock')
    holder = os.open(path, os.O_RDWR | os.O_CREAT); fcntl.flock(holder, fcntl.LOCK_EX)
    t = time.monotonic()
    with self.assertRaises(TimeoutError):
        with host.Flock(path, timeout=0.3):
            pass
    self.assertLess(time.monotonic() - t, 2)
```

`tearDown` kills the leftover test children and clears `host._ABANDONED`.

- [ ] **Step 2: Run the tests.** Expected: FAIL (`run()` has no `timeout`/`key`; `Flock` has no `timeout`).

- [ ] **Step 3: Implement in `host.py`**
  - **Module dict `_ABANDONED = {}`** (key → `Popen`).
  - **At the start of every `run`:** poll each entry. A finished child is removed and logged: `<cmd> (pid P) exited R after it was abandoned` when R ≠ 0, `… finished after it was abandoned` otherwise.
  - **If `key` is still present:** log `<cmd> not started: an earlier command for <key> is still running` and raise `TimeoutExpired(argv, 0)`.
  - **`timeout=None`:** today's `subprocess.run` path, unchanged.
  - **With a timeout:**
    - `Popen(argv, stdin=DEVNULL, stdout=tf_out, stderr=tf_err, close_fds=True)`, where each `tf` is a `tempfile.TemporaryFile()`;
    - `wait(timeout)`; on expiry close both files, store the child under `key` (or `id(proc)` when `key` is None), log `<cmd> gave no answer in N s; left running (pid P)`, and raise `TimeoutExpired`;
    - otherwise seek and read both files and build the `CompletedProcess`;
    - the `check` handling is identical to today's.
  - **`Flock.__init__(self, path, timeout=120)`:** `__enter__` loops `flock(LOCK_EX | LOCK_NB)` with a 0.2 s sleep until the monotonic deadline, then closes the fd and raises `TimeoutError(f'{path}: held for over {timeout} s')`.

- [ ] **Step 4: Run the tests.** Expected: PASS. The full suite stays at 196 + 7, OK.

---

### Task 3: Config key `pv_devices`

**Files:**
- Modify:
  - `roles/storage_vm/files/homelab_storage/config.py`
  - `roles/storage_vm/templates/config.json.j2`
  - `roles/storage_vm/tasks/assert.yml`
  - `roles/storage_vm/defaults/main.yml`
  - `lab/vars.example.yml`
- Test:
  - `scripts/tests/test_storage_vm_role.py`
  - the `config()` fixtures in `test_storage_reconcile.py`, `test_storage_fencer.py` and `test_storage_expiry.py`
  - the config test, wherever `config.load` is tested today (grep for it)

**Interfaces:**
- Produces: `cfg['pv_devices'] == {'retained': str, 'regen': str}`. Fixtures use `/dev/disk/by-path/test-retained` and `/dev/disk/by-path/test-regen`.

- [ ] **Step 1: Write the failing tests**
  - `test_pv_devices_required`: a config without `pv_devices` raises `ConfigError` naming `pv_devices`.
  - `test_pv_devices_shape`: these each raise:
    - a key set other than `{retained, regen}`;
    - a non-str value;
    - a value not starting with `/dev/`;
    - equal values.
  - `test_config_template_pv_devices`: the rendered `config.json.j2` has `pv_devices` equal to the variable.
  - `test_assert_pv_devices`: `assert.yml` contains the four conditions.

- [ ] **Step 2: Run.** Expected: FAIL.

- [ ] **Step 3: Implement**
  - `config.py`: `KEYS['pv_devices'] = dict`, plus a shape check with message `pv_devices must map retained and regen to distinct /dev/ paths`.
  - Template: `"pv_devices": {{ storage_vm_pv_devices | to_json }},`.
  - Defaults: `storage_vm_pv_devices` holds the two by-path names from Task 1, with the comment `# terraform virtio1 (retained) and virtio2 (regen) slots; by-path, not lvm-pv-uuid (ADR 0017 F12)`.
  - `assert.yml`: a new assert block for the same four conditions.
  - Add `pv_devices` to every test `config()` fixture.

- [ ] **Step 4: Run the full suite.** Expected: OK.

---

### Task 4: Scoped, bounded LVM (`lvm.py`) and VG-aware fakes

**Files:**
- Modify: `roles/storage_vm/files/homelab_storage/lvm.py`
- Test:
  - `scripts/tests/test_storage_reconcile.py` (`FakeHost.run`)
  - `test_storage_fencer.py` (`FenceHost.run`)
  - `test_storage_expiry.py` (its `run`)
  - new `scripts/tests/test_storage_lvm.py`

**Interfaces:**
- Consumes: `host.run(..., timeout=, key=)` (Task 2) and `host.CONFIG['pv_devices']` (Task 3).
- Produces:
  - `lvm.LVM_TIMEOUT = 30`
  - `lvm.vgs(names) -> {name: Vg}`. It never raises for a VG it cannot read.
  - `lvm.vg_tags_only(name) -> Vg` (`lvs={}`)
  - `lvm.create`, `lvm.extend`, `lvm.vg_tags` and `lvm.lv_tags`, with the same signatures as today
  - `lvm.remove(vg, id)`
  - `lvm.activate(vg)`

- [ ] **Step 1: Make the three fakes VG-aware.** No production change yet.
  - `run(self, argv, check=True, timeout=None, key=None)`.
  - A `vgs`/`lvs` call reports only the VG named as the last argv element. If that element is not a VG name, it reports all VGs, which keeps today's behaviour.
  - New fake option `stalled=set()`: an LVM call for a stalled VG raises `TimeoutExpired` when `timeout` is set, and `AssertionError('unbounded call on stalled VG')` when it is not.
  - New option `stale_hints=set()`: an unscoped `vgs`/`lvs` call (no `--devices`) omits those VGs, which models F12.
  - Parse VG and tags after skipping a leading `--devices <path>` pair.
  - The suite stays green.

- [ ] **Step 2: Write the failing tests in `test_storage_lvm.py`** (against the reconcile `FakeHost`)
  - `test_every_lvm_argv_scoped`:
    - run `reconcile.main` apply (create, extend, export), boot-check and expire, and `Fencer.loop_once` with a fence;
    - for every recorded call with `argv[0]` in `{vgs, lvs, vgchange, lvchange, lvcreate, lvextend, lvremove, pvscan}`, assert that `argv[1:3] == ['--devices', cfg['pv_devices'][vg]]`, that exactly one VG or `vg/lv` is named, that the call has a timeout, and that reads include `--readonly`.
  - `test_regen_stall_reads_absent`: `stalled={'regen'}` makes `vgs()['regen'].present` False, keeps retained present, and logs `VG regen unreadable on /dev/disk/by-path/test-regen`.
  - `test_lvs_failure_is_absent`: `vgs` OK and `lvs` failing for retained gives `present=False`.
  - `test_shared_deadline`: with the fake recording `timeout`, the `lvs` timeout is at most 30 minus the time spent in `vgs`, and both are at most 30.
  - `test_missing_pv_is_absent_not_raise`: the regen fake call raises `CalledProcessError(5)`, which gives `present=False` and no exception.
  - `test_vg_tags_only_runs_vgs`: exactly one `vgs` call, no `lvs`.
  - `test_withdraw_restore_needs_no_pvscan`: with `stale_hints={'regen'}`, `vgs()` still sees regen, and no `pvscan` call is made.

- [ ] **Step 3: Run.** Expected: FAIL. Calls are unscoped, `vg_tags_only`/`remove`/`activate` are missing, and `vgs()` raises on a stall.

- [ ] **Step 4: Implement `lvm.py`**
  - `_dev(vg)` returns `host.CONFIG['pv_devices'][vg]`.
  - `_lvm(cmd, vg, *args, timeout=LVM_TIMEOUT, read=False)` builds `[cmd, '--devices', _dev(vg), *(['--readonly'] if read else []), *args]` and calls `host.run(argv, timeout=timeout, key=vg)`. The VG or `vg/lv` is the last element of `args`.
  - `vgs(names)`:
    - per VG, `deadline = time.monotonic() + LVM_TIMEOUT`;
    - `vgs … <vg>`, then `lvs … <vg>` with `timeout=max(0.1, deadline - now)`;
    - on `(subprocess.SubprocessError, ValueError, KeyError)`, log `error: VG {n} unreadable on {_dev(n)}: {e}` and return the absent `Vg`;
    - also update the docstring.
  - `vg_tags_only` uses the `vgs` half only.
  - `remove` runs `lvremove -y vg/id`; `activate` runs `vgchange -ay vg`. Both are scoped and use `LVM_TIMEOUT`.
  - `reconcile.expire` calls `lvm.remove`.

- [ ] **Step 5: Update the call-order pins** (for example `test_storage_fencer.py:791`, `test_storage_expiry.py:90`) to the per-VG sequence. Run the full suite. Expected: OK.

---

### Task 5: Retained-only readers, single boot read, `SubprocessError`

**Files:**
- Modify:
  - `roles/storage_vm/files/homelab_storage/fencer.py` (`cluster`, `main`)
  - `reconcile.py` (`_fenced_tags`, `boot_check`, `main`)
- Test: `scripts/tests/test_storage_fencer.py`, `test_storage_reconcile.py`

**Interfaces:**
- Consumes: `lvm.vg_tags_only`, `lvm.vgs` (Task 4) and `host.Flock` with its deadline (Task 2).

- [ ] **Step 1: Write the failing tests**
  - `test_loop_fences_during_regen_stall` (fencer, `stalled={'regen'}`): a NotReady worker past `not_ready_seconds` is fenced, and no call names regen.
  - `test_retained_timeout_is_loop_failure`: with `stalled={'retained'}`, `loop_once` makes no `lio.delete_acl`, nft or taint call, `failures` goes up by 1, and the metrics file is written.
  - `test_lock_timeout_is_loop_failure`: the fake lock's `__enter__` raises `TimeoutError`; the result is `failures`+1 and metrics written. The next `loop_once` with a normal lock acts as normal.
  - `test_cluster_raises_when_retained_unreadable`: raises `RuntimeError`, never returns empty tags.
  - `test_restore_set_regen_stall` and `test_boot_check_regen_stall`: both complete. `boot_check` returns 1 with `VG regen is missing` and still checks retained LUNs.
  - `test_boot_check_reads_once`: one `vgs`+`lvs` pair per VG.
  - `test_cli_timeout_exit_1`: both `main()`s return 1 on `TimeoutExpired` from `host.run`.

- [ ] **Step 2: Run.** Expected: FAIL.

- [ ] **Step 3: Implement**
  - `Fencer.cluster()` uses `lvm.vg_tags_only('retained')` and keeps today's `RuntimeError`.
  - `_fenced_tags(cfg, retained=None)` uses `vg_tags_only('retained')` unless a `Vg` is passed in.
  - `boot_check` passes `vgs['retained']` from its single read.
  - Both `main()` except-tuples replace `subprocess.CalledProcessError` with `subprocess.SubprocessError`. `TimeoutError` is already covered by `OSError`.

- [ ] **Step 4: Run the full suite.** Expected: OK.

---

### Task 6: Run-level fixes and the `activate` subcommand

**Files:**
- Modify: `roles/storage_vm/files/homelab_storage/reconcile.py`
- Test: `scripts/tests/test_storage_reconcile.py`, `test_storage_expiry.py`

**Interfaces:**
- Consumes: `lvm.activate`, `lvm.vgs` (Task 4).
- Produces: CLI `storage-reconcile activate --vg {retained,regen} --config F` (Task 7 uses it), with exit 0 on success and 1 on any error.

- [ ] **Step 1: Write the failing tests**
  - `test_dry_run_missing_vg_empty_inventory`: `[]` inventory with `stalled={'regen'}` gives rc 1.
  - `test_dry_run_regen_stall`: rc 1, all refusals `vg-missing`, finishes (fake timeouts).
  - `test_apply_regen_timeout_fails_entry`: a regen extend raises `TimeoutExpired`. Expected: that id is failed, retained actions still run, and rc is 1. The rule that a second call starts no child lives in `host.run` and is pinned by Task 2's `test_live_key_raises_without_child`. The fakes replace `host.run`, so re-testing it here would only test the fake.
  - `test_final_read_loss_fails_run`: the first read is OK, then regen stalls before the final read. Expected: rc 1, error `final read: VG regen unreadable`, and the report sizes taken from the first read.
  - `test_pending_empty_when_degraded`: a retained LV past quarantine with regen absent gives `expire-candidates` `[]`.
  - `test_vg_present_metric`: `storage_vg_present{vg="regen"} 0` and `{vg="retained"} 1`.
  - `test_target_activates_missing_dev`: export of a regen id whose `/dev/regen/<id>` does not exist (patch `os.path.exists`) calls `vgchange … -ay regen` before `lio.ensure_target`.
  - `test_start_targetctl_bounded`: the `systemctl start` call has `timeout=300`.
  - `test_activate_cli`: `activate --vg regen` gives rc 0 and a scoped `vgchange -ay regen`. With `stalled={'regen'}`, rc 1 within the fake timeout.

- [ ] **Step 2: Run.** Expected: FAIL.

- [ ] **Step 3: Implement in `reconcile.py`**
  - Dry run: `return 1 if BLOCKING & reasons or not all(v.present for v in vgs.values()) else 0`.
  - After `final, _ = _state(cfg)`: for each VG present in `vgs` but not in `final`, append `final read: VG {n} unreadable` and use `vgs[n]` in `final` for the report and metrics.
  - `_pending`: return `[]` when `not all(v.present for v in vgs.values())`.
  - `_write_metrics`: add `('storage_vg_present', {'vg': n}, int(v.present))` for each VG.
  - `Executor.target`: `if not os.path.exists(dev): lvm.activate(a.vg)` before `ensure_target`.
  - `_start_targetctl`: `host.run([... 'start' ...], check=False, timeout=300)`. A `TimeoutExpired` gives the error `systemctl start rtslib-fb-targetctl gave no answer in 300 s`.
  - New subparser `activate` with `--vg` (choices `['retained', 'regen']`) and `--config`. It calls `lvm.activate` and returns 0, or 1 through the existing except.

- [ ] **Step 4: Run the full suite.** Expected: OK.

---

### Task 7: Boot drop-in, unit KillMode, bounded `flock` in `main.yml`

**Files:**
- Modify:
  - `roles/storage_vm/templates/rtslib-fb-targetctl.service.d-50-homelab.conf.j2`
  - `roles/storage_vm/templates/storage-fencer.service.j2`
  - `roles/storage_vm/tasks/main.yml:117-121`
- Test: `scripts/tests/test_storage_vm_role.py` (`TARGETCTL_DROPIN` and the tests near lines 227 and 579)

**Interfaces:**
- Consumes: `storage_vm_pv_devices` (Task 3) and `storage-reconcile activate` (Task 6).

- [ ] **Step 1: Write the failing tests.** Update `TARGETCTL_DROPIN` to the exact expected text below, and add:
  - `test_dropin_retained_fallback`: the line is `ExecStartPre=/bin/sh -c '/sbin/vgchange --devices <retained> -ay retained || /sbin/vgchange -ay retained'`.
  - `test_dropin_order`: `ExecStartPre=` (reset) comes first, then the retained line, then `-…activate --vg regen`, then `-…storage-fencer restore-set`. `ExecStartPost` keeps the fatal `restore-set` and `boot-check`.
  - `test_dropin_device_ordering`: `Wants=` and `After=` carry the systemd-escaped retained `.device` unit, for example `dev-disk-by\x2dpath-test\x2dretained.device` for the fixture path. When `systemd-escape` is on PATH, the test also checks a `pci-0000:00:0b.0`-style path against `systemd-escape --path --suffix=device`.
  - `test_killmode_process`: both the drop-in and `storage-fencer.service.j2` contain `KillMode=process`.
  - `test_status_flock_bounded`: the `main.yml` status task argv starts with `[flock, -w, '120', /run/lock/storage-lio`.

Expected drop-in body (after the managed and comment lines):

```
[Unit]
After=nftables.service
Wants=<escaped retained device>
After=<escaped retained device>

[Service]
# A failed start or a stop never signals an abandoned (D-state) LVM child (ADR 0017 F11).
KillMode=process
ExecStartPre=
ExecStartPre=/bin/sh -c '/sbin/vgchange --devices <retained> -ay retained || /sbin/vgchange -ay retained'
ExecStartPre=-/usr/local/sbin/storage-reconcile activate --vg regen --config /etc/homelab-storage/config.json
ExecStartPre=-/usr/local/sbin/storage-fencer restore-set
ExecStartPost=/usr/local/sbin/storage-fencer restore-set
ExecStartPost=/usr/local/sbin/storage-reconcile boot-check --config /etc/homelab-storage/config.json
```

- [ ] **Step 2: Run.** Expected: FAIL.

- [ ] **Step 3: Implement**
  - Escape the device unit name with a Jinja expression in the template: strip the leading `/`, replace `-` with `\x2d`, then `/` with `-`, and append `.device`. No deploy-time `systemd-escape` call is needed.
  - Rewrite the header comment to say that the drop-in replaces the image's `10-lvm.conf` lines.

- [ ] **Step 4: Run the full suite.** Expected: OK. Then run `ansible-playbook --syntax-check storage.yml` (if the repo's usual lint wrapper exists, use that).

---

### Task 8: Docs

**Files:**
- Modify:
  - `~/.cache/claude-homelab-live/worktrees/apps-adr-0017/docs/adr/0017-retained-block-storage-vm-iscsi.md`
  - `…/docs/superpowers/reports/2026-11-16-retained-storage-lab-results.md`
  - the runbook section in the ADR that tells an operator to run `pvscan --cache` or bare `vgs` (grep for both)

- [ ] **Step 1: Update the ADR**
  - **Hang policy:** add the four lines from the spec ("ADR 0017 changes").
  - **Reconcile table:** "VG missing → refuse everything" also covers a regen that does not answer in 30 s.
  - **Named residuals:** add the list from spec item 9.
  - **Runbook:** use the scoped forms `vgs --devices <pv> --readonly <vg>` and `pvscan --cache` only when regen is not stalled.

- [ ] **Step 2: Update the lab report.** Mark F11 and F12 "fixed in code, re-test pending" and link the spec.

- [ ] **Step 3: Fact-check.** Every file, function and value named in the docs exists in the Task 2–7 diff, checked by grep.

---

### Task 9: Lab re-test on 971 (each step needs Ben's OK)

**Files:**
- Write: `~/.cache/claude-homelab-live/storage-lab/b8/f11-retest.md`. Later, the lab report gets its re-test section.

Deploy first: `storage.yml` against the lab (Ben OK), then a dry run, which must be clean. Before each leg, back up the scratch tooling to `~/.cache` and check `clock_ok`.

- [ ] **Step 1: Regen stall, 3 min** (B8 H-stall recipe). Pass when all of these hold:
  - the dry run finishes in under 40 s with rc 1 and `vg-missing`;
  - `storage-fencer status` takes under 1 s;
  - the fencer journal has no gap over 45 s;
  - an apply runs mid-stall, with the fencer gap measured;
  - mid-stall, with an abandoned regen child alive: `lslocks`, `ps -eo pid,stat,wchan,cmd | grep '[l]vm'`, then a timed retained tag write (`storage-fencer fence`/`unfence` on the lab worker, Ben OK) and `status`;
  - a fence of a hard-stopped worker that has regen I/O in flight finishes, and then `prove <other>`, `restore-set` and the next loop also finish. If any of these block, stop and report to Ben (spec item 8);
  - after the uncut: no abandoned LVM child is left, and `dmsetup info -c` shows every LV ACTIVE.

- [ ] **Step 2: Regen withdrawn, then restored** (B8 H-withdraw recipe). Pass when:
  - the first apply after the restore is clean with no `pvscan`;
  - the by-path link is still present.

- [ ] **Step 3: Reboot with regen stalled.** Pass when:
  - retained targets come up;
  - `boot-check` fails with `VG regen is missing`;
  - the time from that failure to the fencer going active is recorded;
  - `systemd-analyze critical-chain` shows no hang in `lvm2-monitor` or udev autoactivation (if one appears, stop: packer item for Ben);
  - `ps` shows the abandoned `vgchange` still alive;
  - after the uncut, `apply` activates and exports regen.

- [ ] **Step 4: Reboot with a deliberately wrong retained path** (a lab-only vars override, deployed). Pass when:
  - retained targets come up through the fallback;
  - the next dry run fails with `VG retained unreadable on <wrong path>`.

  Then restore the correct value and redeploy.

- [ ] **Step 5: Regression.** Pass when:
  - the B8 retained rows pass;
  - the B10 boot rows pass;
  - both test suites (ansible storage, apps `scripts/storage/tests`) are OK.
