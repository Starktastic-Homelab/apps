# Storage VM LVM isolation (lab F11, F12): design

Status: draft for Ben, 2026-11-18. Ben picked approach A ("fail closed") on 2026-11-18. The doc has
been revised after a builder check, a fact-check and a hang hunt (output in
`storage-lab/b8/f11-f12-design-check.json`).
Code: ansible `feat/retained-storage-vm` (`roles/storage_vm`). Evidence: the lab report section "B8
Check 8", `storage-lab/b8/notes.md`, and `storage-lab/b8/f11-f12-design-workflow.md`.

## Why

- **F11.** A 3-minute stall of the regen disk hung `storage-reconcile apply --dry-run` past the
  probe's 60 s cap.
  - The code has a single LVM read: a bare `vgs` followed by a bare `lvs`. Neither names a VG, so
    each one opens every PV, and `host.run` has no timeout.
  - Every caller goes through that read: apply, dry run, boot-check, restore-set, expiry, and the
    fencer (`Fencer.cluster()`, called on every loop pass while it holds `LIO_LOCK`).
  - So, reading the code (the lab tested only the dry run), a regen-only stall stops all fencing
    for as long as it lasts.
  - `vgs retained` stayed fast in the lab only because it limits the scan to retained, and the code
    never runs it.
- **F12.** During an export withdrawal, an unscoped `lvs` rewrote `/run/lvm/hints` without the
  failing PV. After the restore, VG regen stayed "missing" and every volume, retained included, was
  refused until someone ran `pvscan --cache`.

## Goals

- A regen-only fault (stall, I/O errors, missing disk) never hangs a command that needs only
  retained: the fencer loop, `prove`, `status`, `restore-set`, the nftables hooks, and boot
  activation of retained.
- Every LVM command run by the reconcile and the fencer has a time limit, and so does every wait
  for `LIO_LOCK`. The unbounded calls that remain are listed under "Named residuals".
- After a regen fault clears, the next run is clean: no `pvscan` and no reboot.

## Non-goals

- Approach B: serving or growing retained while regen does not answer. Under A, a missing regen
  still refuses every change, as today. Live targets are never removed.
- A stall of the whole NFS mount. In production both disks sit on one `k3s-block` mount, so that
  stall hits retained too.
- LVM commands typed by hand. These still use hints, so the runbook gives the scoped form.

## Anti-goals

- **Killing an LVM write or activation.**
  - `lvextend` goes through `lv_update_and_reload`: vg_write, then suspend with the new table
    preloaded, then vg_commit, then resume. A kill between suspend and resume leaves the LV
    suspended, and all I/O hangs until someone runs `dmsetup resume`.
  - A killed activation can leave a dm device that was created but never resumed.
  - Check 9's VM crashes do not cover either case, because a crash also wipes the dm state.
- **Any new way for retained to fail to come up at boot.**
- **Touching retained data, protection, holds or `Retain`.**

## Approaches

| | While regen doesn't answer | Cost |
|---|---|---|
| **A (picked)** | Regen reads as missing after its time limit. The plan refuses every change, as today. Live targets stay up. | `plan.py` is unchanged. |
| B | Retained exports and grows still go ahead. Creates, pending marks and expiry are refused, and the run still fails. | New plan rules, and an ordering rule against the removal brake. Helps only when regen alone is faulty. |
| C (rejected) | `timeout(1)` and systemd limits only, no code change. | `timeout(1)` still waits for a child stuck in D state, and retained stays blocked. |

`hints = "none"` (the F12 suggestion) is also rejected. The scoped commands below never read or
rewrite hints. All it would change is that hand-typed `vgs retained` would scan the stalled disk too.
Udev's autoactivation already runs without hints (lvm2 `vgchange.c`).

## Design

1. **`host.run(argv, check=True, timeout=None)`: give up waiting, never kill.**
   - With a timeout set, the child writes stdout and stderr to anonymous `tempfile.TemporaryFile()`
     files, not pipes, and keeps `close_fds=True`.
   - When the timeout passes, `run` does four things:
     - logs `<cmd> gave no answer in N s; left running (pid P)`;
     - closes the parent's copies of the output files;
     - records the child against its key (below);
     - raises `subprocess.TimeoutExpired`.
   - Later calls reap finished children with `poll()`. A child is never killed and never waited on.
   - **One live abandoned child per key.** While an abandoned child for key K is still alive in this
     process, a new call with key K raises `TimeoutExpired` at once without starting a child. LVM
     calls use the VG name as the key.
     - This caps pile-up at one child per VG.
     - The apply loop skips the rest of a stalled VG's actions with no extra code.
     - A late, abandoned retained tag write (for example an unfence's `--deltag fenced:…`) cannot
       race a fresh read: the fencer loop fails closed until that write has landed.
   - Without a timeout, behaviour is unchanged.

2. **One VG and one PV per LVM command** (`lvm.py`).
   - New config key `pv_devices: {retained: <path>, regen: <path>}`. It touches:
     - `config.py`: add to `KEYS`; exactly those two keys, distinct values starting with `/dev/`;
     - `templates/config.json.j2`, from `storage_vm_pv_devices`;
     - `assert.yml`;
     - every test config fixture.
   - Every LVM argv gets `--devices <that VG's PV>` straight after the command name, and names one
     VG or one `<vg>/<lv>`. Reads also get `--readonly`, which takes no lock (lvm2 `locking.c`).
   - lvm2 2.03.31 facts this rests on (`lvmcmdline.c`):
     - `--devices` drops the other devices before it opens any of them;
     - it sets `use_hints=0`, so our commands neither read nor write the hints file. That is what
       fixes F12.
   - Time limits:
     - `LVM_TIMEOUT = 30` s per VG read. `vgs` and `lvs` share one deadline.
     - `LVM_TIMEOUT` per write.
   - `vgs(names)` reads one VG at a time. On any `SubprocessError` it logs
     `error: VG <n> unreadable on <pv>: <reason>` and returns that VG as `present=False`, even when
     `vgs` worked and only `lvs` failed.
   - `vg_tags_only(name)` runs only `vgs`. `Fencer.cluster()` and `_fenced_tags()` need only VG tags,
     so they use it.
   - New `lvm.remove(vg, id)` replaces `reconcile.expire`'s raw `lvremove`.
   - New `lvm.activate(vg)` runs a scoped `vgchange -ay`.
   - A test walks every argv the suite produces whose `argv[0]` is an LVM tool. Each must carry
     `--devices` and a single VG name.

3. **Retained-only readers.**
   - `Fencer.cluster()` and `reconcile._fenced_tags()` read only retained. That covers the loop,
     fence, unfence, `status`, `restore-set` and the nftables hooks.
   - `boot_check` makes one read instead of two.
   - If retained cannot be read, `cluster()` raises. It never returns empty fence tags.
     - The raise counts as a loop failure.
     - `restore-set` keeps the full set fenced.
     - Both are today's fail-closed paths.
   - Both `main()`s catch `subprocess.SubprocessError` instead of `CalledProcessError`, so a timeout
     also exits 1.

4. **Plan unchanged (A), with three small run-level fixes.**
   - A regen that times out reads as missing, so `vg-missing` refuses everything. Live targets stay
     up.
   - **Dry run:** return 1 when any configured VG is not present, even with an empty inventory. This
     also catches a wrong `pv_devices` path, so no separate Ansible check task is needed (one would
     have no time limit).
   - **Final read:** if `_state` after the apply loses a VG that the first read saw, count it as an
     error, and keep the first read's sizes for the report and metrics.
   - **Expiry:** `_pending` returns `[]` when any VG is not present, so nothing expires while
     degraded.
   - New gauge `storage_vg_present{vg}`.

5. **Bounded `LIO_LOCK` wait.**
   - `Flock.__enter__` polls with `LOCK_NB` against a 120 s deadline, then raises `TimeoutError`.
     That is an `OSError`, which both `main()`s already map to exit 1. In the fencer it is a loop
     failure, and metrics are still written.
   - `main.yml`'s `flock /run/lock/storage-lio storage-fencer status` becomes `flock -w 120`.

6. **PV paths** (`storage_vm_pv_devices`).
   - Use the slot links under `/dev/disk/by-path` for virtio1 (retained) and virtio2 (regen). They
     come from terraform's interfaces and need no content probe.
   - The exact names are taken from 971 before coding (lab step 0).
   - The `lvm-pv-uuid-*` links depend on a blkid probe, so a probe that hits I/O errors could drop
     them. That is a risk, not a proven fact, so they are not used.

7. **Boot** (`rtslib-fb-targetctl.service.d-50-homelab.conf.j2`). Packer's `10-lvm.conf` stays as
   it is: it covers the first boot, before the role has run (superseded 2026-11-19: it no longer activates, see the F24 design). The role's drop-in:
   - `Wants=` and `After=` the retained PV's `.device` unit.
   - `KillMode=process`. The unit is Debian's oneshot with `RemainAfterExit` and no main process
     left after `ExecStart`, so a failed start or a stop never signals an abandoned activation.
     `ExecStop` (`targetctl clear`) is unchanged. `storage-fencer.service` gets the same.
   - Resets `ExecStartPre=` and then runs, in order:
     1. `ExecStartPre=/bin/sh -c '/sbin/vgchange --devices <retained pv> -ay retained || /sbin/vgchange -ay retained'` (superseded 2026-11-19 by `2026-11-19-storage-vm-boot-lvm-design.md`: no fallback).
        This stays fatal, as today. The unscoped fallback means a wrong or renamed path cannot stop
        retained from coming up.
     2. `ExecStartPre=-/usr/local/sbin/storage-reconcile activate --vg regen --config …`, a new
        subcommand that runs the scoped activate under the 30 s give-up rule. It stays non-fatal,
        as today.
     3. `ExecStartPre=-/usr/local/sbin/storage-fencer restore-set`, a new early copy that only edits
        the nft set. It means the fenced set is complete before any target listens; the
        nftables-time call may now fail early in boot, because the by-path link may not exist yet.
        It is non-fatal, so a bad fence tag cannot stop retained targets from coming up.
   - `ExecStartPost` keeps `restore-set` (fatal, as today, so the unit still reports a failure) and
     `boot-check`.
   - `Executor.target` runs `lvm.activate(vg)` when the LV's device node is missing, so a regen whose
     boot activation was abandoned comes back on the next apply.
   - `_start_targetctl`'s `systemctl start` gets a 300 s give-up limit.
   - **Lab gate:** with regen not activated, `targetctl restore` must still restore the retained
     targets, and the unit must reach `boot-check`. Otherwise this item comes back to Ben.

8. **Fence and regen ACLs: a lab question first.**
   - `lio.delete_acl` removes the worker's ACL on every target, regen included, as an in-process
     configfs rmdir under `LIO_LOCK`. `proof()`, `save()`, `add_acl` and boot-check's `delete_acl`
     walk the same directories.
   - The lab fences a worker that has regen I/O in flight during a regen stall, then checks that the
     fence, `prove <other worker>`, `restore-set` and the next loop all finish.
   - If any of them block, the fix (moving regen ACL work out of the locked in-process path) comes
     back to Ben as its own item.

9. **Named residuals** (go in the ADR). Each needs regen to answer at plan time and then stall in
   the middle of the work, or a stall of retained itself:
   - a regen create: `dd`, `blkid`, `mkfs`, `mount`, `umount`, and the in-process marker `fsync`;
   - expire's `blkdiscard`. A give-up limit there would leave the LV open `O_EXCL`, so `lvremove`
     fails and the volume is half-expired;
   - in-process rtslib and configfs work, and `lio.save`'s `fsync`;
   - `nft`, `ss` and `systemctl is-active`;
   - `targetctl restore` on a regen that activated and then stalled before the restore;
   - the boot activation of retained.

   While one of these holds `LIO_LOCK`, other lock users give up after 120 s (item 5) and do not
   hang. Follow-up: bound the create steps and move the marker write into a child process.

## Tests (RED today, GREEN after)

- **host.run:**
  - a timed-out child is alive afterwards and is later reaped;
  - the parent holds no file descriptor to the child's output;
  - a second call with the same key starts no child and raises at once.
- **Scoping:** the walk from item 2.
- **Regen stall in the fake** (regen calls block past the limit; the fake asserts each regen call
  has a timeout):
  - dry run returns 1 with `vg-missing`;
  - `Fencer.loop_once` still fences a NotReady worker;
  - `restore_set` and `boot_check` complete;
  - two regen actions in an apply start one child, not two.
- **Abandoned retained tag write:** the next `loop_once` makes no LVM call and takes no action.
- **Regen withdrawn, then restored:** the second dry run is clean with no `pvscan`. The fake models
  stale hints for unscoped argv; the real proof is lab step 2.
- **Run-level fixes:** dry run returns 1 with an empty inventory and a missing VG; a lost final read
  fails the run; `_pending` is empty when degraded; `storage_vg_present`.
- **Retained-only reads:** `cluster()` raises when retained cannot be read; `boot_check` reads once;
  `cluster()` and `_fenced_tags()` run only `vgs`.
- **Lock:** `Flock` gives up at its deadline.
- **Drop-in render:** the reset; the retained line with its fallback (superseded 2026-11-19, F24); the regen activate with `-`;
  `restore-set` in both `ExecStartPre` (`-`) and `ExecStartPost`; device ordering; `KillMode=process`.
- **Existing tests:** fakes take `timeout`; call-order pins become per-VG.

## Lab re-test on 971 (Ben OKs each step)

0. **Read-only checks.**
   - `ls -l /dev/disk/by-path` and `pvs -o pv_name,vg_name`.
   - `systemctl cat rtslib-fb-targetctl nftables lvm2-monitor`.
   - `systemctl show -p Type,KillMode,TimeoutStartUSec,TimeoutStopUSec,LimitNOFILE rtslib-fb-targetctl storage-fencer`.
   - `lvmconfig --typeconfig full activation/event_activation`.
   - A scoped `vgs --devices … --readonly <vg>` per VG.
   - `lslocks` during one of those reads, expecting no LVM lock.
1. **Regen stall, 3 min** (B8 H-stall recipe).
   - Dry run: about 30 s, rc 1.
   - `storage-fencer status`: under 1 s.
   - Fencer journal: no gap over 45 s.
   - An apply during the stall, with the fencer gap measured.
   - Mid-stall, with an abandoned regen child alive: `lslocks`, `ps -eo pid,stat,wchan,cmd`, then a
     timed retained tag write (`fence`/`unfence`) and `status`.
   - The item 8 fence row.
   - After the uncut: the children drain, and `dmsetup info -c` shows every LV ACTIVE.
2. **Regen withdrawn, then restored** (B8 H-withdraw recipe).
   - The first apply after the restore is clean with no `pvscan`.
   - The by-path link survives.
3. **Reboot with regen stalled.**
   - Retained targets come up.
   - `boot-check` fails with `VG regen is missing`.
   - Time from that failure to the fencer going active.
   - `systemd-analyze critical-chain`, and whether `lvm2-monitor` or udev autoactivation hung.
   - `ps` shows the abandoned `vgchange` still alive, not killed.
   - After the uncut, `apply` activates and exports regen.
   - If `lvm2-monitor` or autoactivation blocks the boot, the image change (for example
     `auto_activation_volume_list`) comes back to Ben as a packer item.
4. **Reboot with a wrong retained path.** Retained targets still come up, through the fallback (void: ran with stock activation on; see F24).
5. **Regression.** B8 retained rows, B10 boot rows, and both test suites.

## ADR 0017 changes

- **Hang policy:**
  - every LVM command reads only its own VG's PV and has a time limit;
  - a timed-out command is left running and never killed, and later calls for that VG fail at once
    until it ends;
  - the fencer and `restore-set` read retained tags only;
  - `LIO_LOCK` waits at most 120 s.
- **Reconcile table:** "VG missing → refuse everything" also covers a regen that does not answer
  within the limit.
- **Named residuals:** the list in item 9.
- **Lab report:** F11 and F12 rows, with the re-test results.

## My calls (Ben can overrule)

- `KillMode=process` on both units, instead of a separate regen-activation unit.
- The unscoped fallback for retained boot activation (superseded 2026-11-19, F24).
- An extra, non-fatal `restore-set` in `ExecStartPre`. The fatal one stays in `ExecStartPost`.
- A 120 s lock deadline and a 300 s limit for `systemctl start`.
- No `StorageVGMissing` alert in this change. The gauge is added; the alert rule would be an apps
  commit later. Until then a regen fault shows only through `StorageReconcileFailing`, after 2 h.

## Left to the builder

Helper and test names, and how the drop-in escapes the `.device` unit name.
