# F24: stock LVM off the storage VM's data disks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** only the storage role's own scoped commands ever activate VGs `retained` and `regen`; the image turns every
stock LVM path off, and the role refuses a VM where it is still on.

**Architecture:** the packer storage image sets `global/event_activation = 0`, masks `lvm2-monitor` and
`blk-availability`, rebuilds every initramfs and checks each one, holds lvm2, and drops the unscoped lines from its
`10-lvm.conf`. The ansible role's targetctl drop-in keeps only the scoped retained line (no fallback), holds lvm2, and
`assert.yml` refuses a VM whose image or current boot shows stock activation. Docs restate the boot rule; a lab task
proves it on 971.

**Tech Stack:** bash (packer provisioner), Ansible role YAML + Jinja2 templates, Python `unittest` offline tests,
lvm2 2.03.31, systemd 257, initramfs-tools (Debian 13).

**Spec:** `docs/superpowers/specs/2026-11-19-storage-vm-boot-lvm-design.md` (apps-adr-0017 worktree), approved by Ben
2026-11-19.

## Worktrees (all under `~/.cache/claude-homelab-live/worktrees/`, branch `feat/retained-storage-vm`, uncommitted work already present)

- `packer-storage-vm` (P): `scripts/storage.sh`, `files/storage/rtslib-fb-targetctl.service.d/10-lvm.conf`,
  `scripts/tests/test_image_layout.py`, `README.md`.
- `ansible-storage-vm` (A): `roles/storage_vm/templates/rtslib-fb-targetctl.service.d-50-homelab.conf.j2`,
  `roles/storage_vm/tasks/assert.yml`, `roles/storage_vm/tasks/main.yml`, `scripts/tests/test_storage_vm_role.py`.
- `apps-adr-0017` (D): `docs/adr/0017-retained-block-storage-vm-iscsi.md`,
  `docs/superpowers/reports/2026-11-16-retained-storage-lab-results.md`,
  `docs/superpowers/specs/2026-11-18-storage-vm-lvm-isolation-design.md`.

Test commands:
- P: `python3 scripts/tests/test_image_layout.py` (13 tests OK today).
- A: `~/.cache/claude-homelab-live/venv/bin/python3 -m unittest discover -s scripts/tests -p 'test_storage*.py'`
  (257 OK today).

## Global Constraints

- "only the role's own commands may ever activate retained and regen" (Ben, 2026-11-19).
- Retained activates only through `vgchange --devices <retained PV> -ay retained`; regen only through
  `storage-reconcile activate --vg regen`. No unscoped fallback.
- `event_activation = 0` goes in the `global` section of `/etc/lvm/lvm.conf`; the check is that
  `lvmconfig global/event_activation` prints exactly `event_activation=0`.
- Masked units: `lvm2-monitor.service`, `blk-availability.service`.
- `update-initramfs -u -k all`, then every `/boot/initrd.img-*` must carry the setting.
- `apt-mark hold lvm2` in the image; the role's hold loop adds `lvm2`.
- A wrong retained path fails the unit: no target restored, regen included (fail closed).
- Role checks run with `check_mode: false` and `changed_when: false`; `dry-run.yml` imports `assert.yml`, so the
  dry run refuses too.
- Retained-data rules stand: never force-detach, recreate or reformat images, drop RWOP, `Retain`, prune protection or a
  source hold, or fake markers to pass a guard.
- No commits unless Ben asks (the plan's commit steps are skipped; each task ends at a green suite). Docs-only commits
  in ansible and packer need `[skip ci]` when they are made.
- Lab: ASCII-only QGA commands; never print the lab token, nonces or `pve.env` values; clock gate (never 01–06, not
  :20–:50 of 03/09/15/21, not across :55–:04; scripts use minute < 38 and ≥ 5); every lab step needs Ben's OK in this
  session.

## Review Focus

1. Stock `lvm.conf` layout: the edit must land inside `global { }`, not create a second `global` block or a duplicate
   key. Expected: the `lvmconfig` check fails the build on anything but `event_activation=0`. (Task 1 test pins the
   check and its order.)
2. An initramfs that was not rebuilt (older kernel, a later `apt` trigger): Expected: the image build fails on any initrd
   whose `etc/lvm/lvm.conf` differs from `/etc/lvm/lvm.conf`, and on a running VM the role refuses because
   `/run/lvm/vgs_online` or `pvs_online` has entries. (Task 1 test pins the per-initrd check; Task 2 test pins the
   `/run/lvm` assert.)
3. `/run/lvm/vgs_online` absent (fresh boot with no LVM run at all): Expected: the assert passes (absent = empty), it
   does not fail on a missing directory. (Task 2 test.)
4. `systemctl is-enabled` exits non-zero for a masked unit: Expected: the read task never fails on rc, only the assert
   decides. (Task 2 test.)
5. Role deploy onto a VM booted from today's image (event activation on): Expected: refused before any unit or file
   change, with a message naming the packer change. (Task 2 test that the assert task sits in `assert.yml`, which is
   first in `main.yml` and `dry-run.yml` — the existing `test_asserts_come_first` covers order.)

---

### Task 1: Packer storage image turns stock LVM off

**Files:**
- Modify: `P/scripts/storage.sh` (after `apt-mark hold python3-rtslib-fb targetcli-fb`; replace the 10-lvm comment)
- Modify: `P/files/storage/rtslib-fb-targetctl.service.d/10-lvm.conf`
- Modify: `P/scripts/tests/test_image_layout.py` (`LVM_DROPIN`, `test_storage_script`)
- Modify: `P/README.md` line 78 (`storage.sh` row)

**Interfaces:**
- Produces: an image where `lvmconfig global/event_activation` = `event_activation=0`, both units masked, lvm2 held,
  every initrd's `etc/lvm/lvm.conf` byte-identical to `/etc/lvm/lvm.conf`, and `10-lvm.conf` with no `[Service]`.
  Task 2's asserts read exactly these four facts; Task 4 hand-applies the same lines.

- [ ] **Step 1: Write the failing tests**

`LVM_DROPIN` becomes:

```python
LVM_DROPIN = """[Unit]
Wants=network-online.target
After=network-online.target
"""
```

Add to `TestImageLayout`:

```python
    def test_storage_lvm_stock_activation_off(self):
        commands = shell_commands(read("scripts/storage.sh"))
        def at(prefix):
            return next(i for i, c in enumerate(commands) if c.startswith(prefix))
        install = at("apt install -y targetcli-fb lvm2")
        edit = next(i for i, c in enumerate(commands) if "event_activation = 0" in c and "/etc/lvm/lvm.conf" in c)
        check = next(i for i, c in enumerate(commands) if "lvmconfig global/event_activation" in c
                     and "event_activation=0" in c)
        mask = commands.index("systemctl mask lvm2-monitor.service blk-availability.service")
        rebuild = commands.index("update-initramfs -u -k all")
        verify = next(i for i, c in enumerate(commands) if c.startswith("for initrd in /boot/initrd.img-*"))
        self.assertIn("apt-mark hold lvm2", commands)
        self.assertLess(install, edit)
        self.assertLess(edit, check)
        self.assertLess(check, rebuild)
        self.assertLess(rebuild, verify)
        self.assertLess(install, mask)
        script = read("scripts/storage.sh")
        self.assertIn("unmkinitramfs", script)
        self.assertIn("-path '*/etc/lvm/lvm.conf'", script)  # both unmkinitramfs layouts (with or without early/main)
        self.assertIn("cmp -s", script)       # each initrd's lvm.conf equals the checked one
        self.assertNotIn("vgchange", script)  # the image never activates a VG
```

And in `test_lvm_dropin` add `self.assertNotIn("ExecStartPre", read(...))` on the same file.

- [ ] **Step 2: Run to verify they fail**

Run: `cd P && python3 scripts/tests/test_image_layout.py`
Expected: FAIL in `test_lvm_dropin` (file still has `[Service]`) and `test_storage_lvm_stock_activation_off`
(`StopIteration` / not in list).

- [ ] **Step 3: Implement in `scripts/storage.sh` and `10-lvm.conf`**

- `10-lvm.conf`: exactly `LVM_DROPIN` above.
- `storage.sh` comment over the `install -D` line: the drop-in orders targetctl after the network (portal bind); it
  activates nothing (F24).
- After the rtslib hold line, a block with a one-line why-comment per item (spec Design 1):
  - insert `event_activation = 0` as the first line inside the first `global {` of `/etc/lvm/lvm.conf` (for example
    `sed -i '0,/^global {/s//global {\n\tevent_activation = 0/'`), then
    `[ "$(lvmconfig global/event_activation)" = event_activation=0 ] || { echo "ERROR: ..." >&2; exit 1; }`;
  - `systemctl mask lvm2-monitor.service blk-availability.service`;
  - `apt-mark hold lvm2`;
  - `update-initramfs -u -k all`;
  - one loop `for initrd in /boot/initrd.img-*; do ...; done` that unpacks each into a fresh `mktemp -d` with
    `unmkinitramfs`, finds the file with `conf=$(find "$d" -path '*/etc/lvm/lvm.conf' -type f)` (an initrd with an
    early microcode cpio unpacks to `early/` + `main/`, one without unpacks flat), requires exactly one result
    (`[ "$(printf '%s\n' "$conf" | grep -c .)" -eq 1 ]`) and `cmp -s "$conf" /etc/lvm/lvm.conf`, exiting 1 with the
    initrd name otherwise, and removes the temp directory.
- README line 78: replace "LVM activation before target restore" with "stock LVM activation off (`event_activation = 0`,
  every initramfs checked, `lvm2` held, `lvm2-monitor`/`blk-availability` masked)".

- [ ] **Step 4: Run to verify they pass**

Run: `cd P && python3 scripts/tests/test_image_layout.py`
Expected: `Ran 14 tests` … `OK`. Also `bash -n scripts/storage.sh` prints nothing and
`shellcheck scripts/storage.sh` (if installed) adds no new warning.

- [ ] **Step 5: Commit** (only when Ben asks; message `feat(storage): turn stock LVM activation off (F24)`)

---

### Task 2: Ansible role: scoped retained only, and refuse stock activation

**Files:**
- Modify: `A/roles/storage_vm/templates/rtslib-fb-targetctl.service.d-50-homelab.conf.j2` (header comment, retained line)
- Modify: `A/roles/storage_vm/tasks/assert.yml` (append four read tasks and one assert)
- Modify: `A/roles/storage_vm/tasks/main.yml` (`Hold the LIO packages` → `Hold the LIO and LVM packages`, loop + `lvm2`)
- Test: `A/scripts/tests/test_storage_vm_role.py`

**Interfaces:**
- Consumes: Task 1's image facts.
- Produces: registered vars `storage_vm_lvm_event_activation` (command result), `storage_vm_lvm_units` (command
  result), `storage_vm_lvm_selection` (command result), `storage_vm_lvm_online` (find result); assert task name
  `Refuse stock LVM activation`.

- [ ] **Step 1: Write the failing tests**

- `TARGETCTL_DROPIN`: header comment replaced (new text, see Step 3) and the retained line becomes
  `"ExecStartPre=/sbin/vgchange --devices /dev/disk/by-path/pci-0000:06:0b.0 -ay retained\n"`.
- `test_dropin_order`: second prefix `'ExecStartPre=/sbin/vgchange --devices /dev/'`.
- Replace `test_dropin_retained_fallback` with:

```python
    def test_dropin_retained_scoped_only(self):
        out = render('rtslib-fb-targetctl.service.d-50-homelab.conf.j2',
                     storage_vm_pv_devices={'retained': '/dev/disk/by-path/test-retained', 'regen': '/dev/x'})
        self.assertIn('ExecStartPre=/sbin/vgchange --devices /dev/disk/by-path/test-retained -ay retained\n', out)
        self.assertNotIn('||', out)
        self.assertNotIn('/bin/sh', out)
        self.assertEqual(len(re.findall(r'vgchange', out)), 1)
```

- `test_packages_held`: name `'Hold the LIO and LVM packages'`, loop `['python3-rtslib-fb', 'targetcli-fb', 'lvm2']`.
- New:

```python
    STOCK_OK = {'storage_vm_lvm_event_activation': {'stdout': 'event_activation=0'},
                'storage_vm_lvm_units': {'stdout_lines': ['masked', 'masked']},
                'storage_vm_lvm_selection': {'stdout': 'hold ok installed'},
                'storage_vm_lvm_online': {'matched': 0}}

    def test_assert_stock_lvm_reads(self):
        tasks = role_tasks('assert')
        reads = {t['register']: t for t in tasks if t.get('register', '').startswith('storage_vm_lvm_')}
        self.assertEqual(set(reads), set(self.STOCK_OK))
        for t in reads.values():
            self.assertIs(t.get('check_mode'), False, t)
            self.assertIs(t.get('changed_when'), False, t)
        # --type full: exits 0 and prints the effective value even when the key is unset (old image: rc 5 without it)
        self.assertEqual(argv(reads['storage_vm_lvm_event_activation']),
                         ['/sbin/lvmconfig', '--type', 'full', 'global/event_activation'])
        self.assertEqual(argv(reads['storage_vm_lvm_units']),
                         ['systemctl', 'is-enabled', 'lvm2-monitor.service', 'blk-availability.service'])
        self.assertIs(reads['storage_vm_lvm_units'].get('failed_when'), False)   # masked exits non-zero
        self.assertEqual(argv(reads['storage_vm_lvm_selection']), ['dpkg-query', '-W', '--showformat=${Status}', 'lvm2'])
        find = module(reads['storage_vm_lvm_online'], 'find')
        self.assertEqual(find['paths'], ['/run/lvm/vgs_online', '/run/lvm/pvs_online'])
        self.assertEqual(find['file_type'], 'any')
        self.assertIs(find.get('hidden'), True)
        names = [t.get('name') for t in tasks]
        self.assertGreater(names.index('Refuse stock LVM activation'),
                           max(names.index(t['name']) for t in reads.values()))

    def test_assert_stock_lvm(self):
        that = module(by_name(role_tasks('assert'), 'Refuse stock LVM activation'), 'assert')['that']
        self.assertTrue(holds(that, **self.STOCK_OK))
        for key, bad in (('storage_vm_lvm_event_activation', {'stdout': 'event_activation=1'}),
                         ('storage_vm_lvm_event_activation', {'stdout': ''}),
                         ('storage_vm_lvm_units', {'stdout_lines': ['enabled', 'masked']}),
                         ('storage_vm_lvm_units', {'stdout_lines': ['masked']}),
                         ('storage_vm_lvm_selection', {'stdout': 'install ok installed'}),
                         ('storage_vm_lvm_online', {'matched': 1})):
            self.assertFalse(holds(that, **{**self.STOCK_OK, key: bad}), (key, bad))
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd A && ~/.cache/claude-homelab-live/venv/bin/python3 -m unittest discover -s scripts/tests -p 'test_storage_vm_role.py'`
Expected: FAIL/ERROR in `test_targetctl_dropin`, `test_dropin_order`, `test_dropin_retained_scoped_only`,
`test_packages_held`, `test_assert_stock_lvm_reads`, `test_assert_stock_lvm` (StopIteration: no such task).

- [ ] **Step 3: Implement**

- Drop-in header comment (exact text, two lines after `# {{ ansible_managed }}`, then the existing F11 sentences):
  `# The only LVM activation at boot (the image turns stock activation off, ADR 0017 F24): retained from its own PV,`
  `# no fallback, so a wrong path fails the unit and restores no targets; regen bounded and never killed (F11).`
  followed by the existing "Then re-applies fences, ... never clears targets." sentence.
- Retained line: `ExecStartPre=/sbin/vgchange --devices {{ storage_vm_pv_devices.retained }} -ay retained`.
- `assert.yml`, appended after the PV-path assert, four read tasks (`check_mode: false`, `changed_when: false`) with the
  argv and find args the test pins (`failed_when: false` on the `is-enabled` read only, so an old image reaches the
  assert and its message; the packer build check keeps plain `lvmconfig global/event_activation`, which must prove the
  key is set in the file; find with `paths`,
  `file_type: any`, `hidden: true`), then `Refuse stock LVM activation`:

```yaml
    that:
      - storage_vm_lvm_event_activation.stdout == 'event_activation=0'
      - storage_vm_lvm_units.stdout_lines == ['masked', 'masked']
      - storage_vm_lvm_selection.stdout.split() | first | default('') == 'hold'
      - storage_vm_lvm_online.matched == 0
    fail_msg: >-
      Stock LVM activation is on (event_activation, lvm2-monitor/blk-availability not masked, lvm2 not held, or
      /run/lvm/vgs_online|pvs_online not empty on this boot). Rebuild the storage VM from the packer storage image with
      the F24 change (scripts/storage.sh), or apply those lines and reboot; only the role may activate retained and
      regen (ADR 0017 F24).
```

  `find` on a missing path warns and returns `matched: 0`; that is the "absent = empty" case (Review Focus 3).
- `main.yml`: rename the hold task, add `lvm2` to its loop, and widen its comment: an lvm2 upgrade runs an unscoped
  `vgcfgbackup` and may replace `lvm.conf`.

- [ ] **Step 4: Run to verify they pass**

Run: `cd A && ~/.cache/claude-homelab-live/venv/bin/python3 -m unittest discover -s scripts/tests -p 'test_storage*.py'`
Expected: `Ran 259 tests` (257, one test replaced, two added) … `OK`. The playbook syntax check runs in CI only (it
needs the vault file); the tests above load every edited YAML file.

- [ ] **Step 5: Commit** (only when Ben asks; `feat(storage_vm): scoped retained activation only, refuse stock LVM (F24)`)

---

### Task 3: Docs

**Files:**
- Modify: `D/docs/adr/0017-retained-block-storage-vm-iscsi.md` lines 117–124 ("Restoring the configuration at boot")
- Modify: `D/docs/superpowers/reports/2026-11-16-retained-storage-lab-results.md` line 660 (F24) and line 650 (F11 status)
- Modify: `D/docs/superpowers/specs/2026-11-18-storage-vm-lvm-isolation-design.md` lines 146–155 (Boot item 7) and 248
  (lab check 4)

- [ ] **Step 1: ADR.** Replace "Debian 13 activates VGs through transient udev units, so there is no unit to order
  after" and the image's first-boot lines with: stock activation is off in the storage image (`event_activation = 0`,
  copied into every initramfs, `lvm2-monitor` and `blk-availability` masked, lvm2 held), so nothing activates the VGs
  before the role's drop-in; the image's `10-lvm.conf` only orders the unit after the network; before the first deploy
  the VGs stay inactive and the reconcile activates them scoped. The role's drop-in: retained from its own PV with **no
  fallback** (a wrong path fails the unit and no target is restored, regen included; the fence set is still restored by
  `nftables.service`); regen as today. The role refuses a VM where stock activation is on or ran on this boot.
  Keep the `KillMode`, device ordering and `ExecStartPost` bullets.
- [ ] **Step 2: Report F24 paragraph.** Replace "(udev settle on vdc; no LVM in the initramfs)" and the fallback
  sentence with the findings: the initramfs ran stock `vgchange -aay` on both VGs, unscoped, at every boot (proof:
  `/run/lvm/vgs_online` older than `/run/systemd/system`, twice); the diagnostic boot 2026-11-19 (stall 300 s): dm at
  191.7 s, vdc partition read failed at 288.2 s, root mounted 288.4 s, so the hold lasts the whole stall (no bound seen
  up to ~290 s) and is in the kernel and udev, not LVM. Status: activation fixed by spec
  `superpowers/specs/2026-11-19-storage-vm-boot-lvm-design.md` (Ben 2026-11-19); the hold is open for Ben. Add:
  "F11 Steps 3–4 and the B10 boot rows ran with stock activation on; they are re-run under F24, and Step 4's fallback
  result is void."
  Also append to the F11 status (line 650): "Steps 3–4 ran with stock activation on (F24) and are re-run under F24;
  Step 4's fallback result is void."
- [ ] **Step 3: Isolation spec.** Append on line 153 itself (the retained line) " (superseded 2026-11-19 by
  `2026-11-19-storage-vm-boot-lvm-design.md`: no fallback)"; on line 146 ("Packer's `10-lvm.conf` stays as it is")
  append " (superseded 2026-11-19: it no longer activates, see the F24 design)"; on lines 214 and 267 (the fallback in
  the test list and the calls list) append "(superseded 2026-11-19, F24)"; in lab check 4 (line 248) add "(void: ran
  with stock activation on; see F24)".
- [ ] **Step 4: Check.** `grep -n "vgchange -ay retained\|transient udev\|no LVM in the initramfs\|fallback" ` across
  the three files: every match about the boot fallback says "superseded" or "void" on the same line. Read each edited
  paragraph once against the spec.

---

### Task 4: Lab proof on 971 (each step only with Ben's OK in this session; clock gate)

Uses `~/.cache/claude-homelab-live/memsize/` helpers (`lab.sh`, `b6.sh`, `b8.sh`: `fz`, `kube`, `vm`, `hstall`,
`hstart`, `pvekern`) and the lab shell overlay `storage-lab/shell/ansible` + `f11deploy.sh`. Notes go to
`storage-lab/b8/f24-notes.md`. Writers are drained (scale 0, VA count 0) before every reboot and stay at 0 until a
configfs read shows LUN 0 bound to `/dev/<vg>/<id>` with 2 ACLs on all three targets (the f11s4.sh loop); only then
scale up and read `contiguous=True` for both. Before each step: `storage-fencer status` shows no fenced worker.

Activation evidence (the journal does not show which command activated a VG): no files under `/run/lvm/vgs_online` or
`pvs_online`, and the `/dev/mapper/retained-*` / `regen-*` nodes born after `/run/systemd/system` and after
`rtslib-fb-targetctl`'s `InactiveExitTimestamp` (Step 5: after the deploy started).

- [ ] **Step 1: Hand-apply the image lines on 971** (the Task 1 block, copied from `storage.sh`, ASCII only). Guard the
  `lvm.conf` edit so a retry cannot add a second key: stop if
  `grep -Eq '^[[:space:]]*event_activation[[:space:]]*=' /etc/lvm/lvm.conf` already matches. Then the `lvmconfig` check,
  mask both units, `apt-mark hold lvm2`, `update-initramfs -u -k all` plus the initrd check, and rewrite
  `/etc/systemd/system/rtslib-fb-targetctl.service.d/10-lvm.conf` to `LVM_DROPIN`; `systemctl daemon-reload`.
  Expected: every check prints OK; `systemctl cat rtslib-fb-targetctl` shows the role drop-in's lines and no
  `vgchange -ay regen`. The units stay running until the next shutdown, so that one shutdown still runs their stops
  (nothing is stalled then).
- [ ] **Step 2 (optional, read-only refusal proof):** before the reboot (this boot still has `vgs_online` files), run
  `storage.yml` with the Task 2 overlay. Expected: fails at `Refuse stock LVM activation` with the packer message;
  sha256 of `config.json` and both drop-ins unchanged (as f11s4 did).
- [ ] **Step 3: Clean reboot on the current role.** Expected: activation evidence above; all three LVs active; both
  units `masked` and `ActiveState=inactive`; `systemctl list-units 'lvm2-activation*'` empty and no lvm file under
  `/run/systemd/generator*/` (final-review minor 1); targets restored (LUN 0 + 2 ACLs each), boot-check passed; writers
  contiguous.
- [ ] **Step 4: Deploy the Task 2 role** through `f11deploy.sh` (rsync the overlay first). Expected: the dry run and
  `Refuse stock LVM activation` pass; `changed` only for the 50-homelab.conf template and its systemd reload handler
  (the hold task is `ok`: lvm2 was held in Step 1); the rendered drop-in on 971 has no `||`.
- [ ] **Step 5: Clean reboot on the new role.** Same expectations as Step 3.
- [ ] **Step 6: No-role boot.** Move the role drop-in aside (`50-homelab.conf` to `/root/`), `daemon-reload`, reboot.
  Expected: no `vgs_online` files, `dmsetup info` lists no `retained-*`/`regen-*`; `rtslib-fb-targetctl` active, exit 0,
  its journal logs `Could not create StorageObject ... skipped` / `Could not find matching StorageObject for LUN 0`;
  targets, portals and ACLs present and enabled with no LUN (no block access for anyone). The saved LIO config is not
  empty here, so this is not the image's true first boot (that one has an empty config; moving
  `/etc/rtslib-fb-target/saveconfig.json` aside would be Ben's separate call). Then deploy the role again. Expected:
  the reconcile's `ensure_target` activates each VG with the scoped `lvm.activate`, recreates backstores, LUN 0 and
  mapped LUNs, saves; activation evidence holds (nodes born after the deploy started); then writers back, contiguous.
- [ ] **Step 7: Re-runs under F24** (separate OKs; update the f11s3.sh/f11s4.sh header comments and expectations first):
  - F11 Step 3 (regen stalled at boot, stall cut before the reset): 971 held for the whole stall (hold not fixed, per
    the spec); userspace ~2–3 s after the uncut; activation evidence; retained and regen activated by the drop-in
    lines only; targets restored; boot-check passes; writers contiguous. The 30 s regen refusal at boot is not
    reachable this way (the stall is over by userspace); a variant that starts the stall after userspace and before
    targetctl is Ben's call.
  - F11 Step 4 (wrong retained path): the device unit times out (~90 s), the unit fails at the retained line, retained
    inactive, **no targets**, nft fence set present (`nft list set`); writers stay at 0; `storage.yml` restores with
    the right path; then the configfs read, then writers back.
  - B10 rows on a 971 boot (not a pve host reboot): targets up with LUN 0 + 2 ACLs, fencer up about 1 s after
    targetctl, no fence, writers contiguous. A pve host reboot row needs Ben's separate OK and its own clock window.
  Record each in `f24-notes.md` and the report (F24 status line).

---

## Self-review (2026-11-19)

- Spec coverage: Design 1 → Task 1; Design 2 (drop-in, asserts, hold) → Task 2; Design 3 → Task 3; Tests → Tasks 1–2;
  Lab check 1 → done (diagnostic boot), 2 → Task 4 Steps 1–5, 3 → Task 4 Steps 6–7. Plan review 2026-11-19
  (workflow wf_79b24edb-ebd, three lenses + verify) folded in: initrd lookup for both layouts, `lvmconfig --type full`
  on the role read, isolation-spec pointers on the matching lines, Task 4 expectations (no-role boot, writers held until
  LUN 0 + ACLs, F11 Step 3 cannot refuse regen, birth-time activation evidence, idempotent hand edit).
- Names: the four `storage_vm_lvm_*` registers and `Refuse stock LVM activation` are used identically in Task 2's
  tests and implementation.
- Not in scope (spec non-goals): the boot hold fix; per-VG `--setautoactivation`.
