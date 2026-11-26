# Retained storage VM: production migration plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all 33 Proxmox CSI retained volumes onto the storage VM of ADR 0017 and retire Proxmox CSI, with no
retained data lost and every live step behind Ben's OK.

**Architecture:** Six parts, run in order. Each part ends at a gate, and the next part does not start until the gate
has passed.
- **Part 0, preparation (offline, on branches).** Rebase the four `feat/retained-storage-vm` branches and fix what the
  lab left open.
- **Part 1, prerequisites (ADR Migration 0).**
- **Part 2, Foundation code (offline, TDD).** Build what the lab did not need: the CI paths, the workflows, the copy
  Job, the binding switch, the alerts and the runbooks.
- **Part 3, Foundation live (ADR Migration 2).** This part runs the bridge, the ansible PR, the three-image rebuild, the
  storage VM and democratic-csi, then gates F1 and F2.
- **Part 4, cutovers (ADR Migration 3).** One parametrised cutover task, a wave table, and gate C1.
- **Part 5, Retirement (ADR Migration 4).** Automatic fencing stays off (Ben, 2026-11-21): `hold_fence` stays on
  `retained`, the fencer keeps refusing, and the manual fence stays the only fence. Removing `hold_fence` and gate R1
  are a later, separate decision.

Parts 0 and 2 are code. They follow the lab plan's Part A style: test first, then code, then commit. Parts 1, 3, 4 and 5
are live. They follow its Part B style: a command, an Expected line, and Ben's OK on every mutation. Each PR is opened
and merged only when Ben asks.

**Tech stack:** as the lab plan (`2026-11-09-retained-storage-lab-qualification.md`, Tech stack), plus Argo CD chart
`argo-cd` 10.18.2 and ansible 15.0.0 on ansible `main` (#347).

**Spec:** apps `docs/adr/0017-retained-block-storage-vm-iscsi.md`. Ben accepted it on 2026-11-08 and approved it again
on 2026-11-21 at `654c825d` (rebased in Task 0.4 to `e2617509`), branch `docs/adr-0014-retained-storage-vm`. Read the whole ADR before any task. Where this
plan and the ADR disagree, the ADR wins, unless a decision below records Ben choosing otherwise.

**Evidence:** `~/.cache/claude-homelab-live/storage-migration/scout-*.md` (2026-11-21, read-only, cited). The lab
report is `docs/superpowers/reports/2026-11-16-retained-storage-lab-results.md`. The Part A rulings digest is
`~/Projects/homelab/storage-vm-part-a-rulings.md`.

## Global Constraints

- **Branches and commits.**
  - Work on the existing `feat/retained-storage-vm` branches, rebased in Task 0.1.
  - Split PR branches off them (`git switch -c <topic> ...`) when a task names a PR.
  - Commit with `git -c user.name="Ben Faingold" -c user.email=<ben-git-email> commit`. End every message with
    `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. End every PR body with
    `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
  - Never push, open a PR or merge unless Ben asks in that session. No branch exists on the remote yet, and the local
    branches track `origin/main`, so never run a bare `git push`: always `git push -u origin <branch>`.
  - `[skip ci]` goes only on the squash subject of a PR that is docs-only. It never goes on a branch commit: the
    squash body lists branch subjects, and terraform's apply scans the title, the body and the last commit message.
- **Every merge is a live event.**
  - packer `main`: a push builds.
  - terraform: merging a PR applies its saved plan with auto-approve. `apply.yml` runs on `pull_request_target`, using
    the base branch's copy of the workflow. `validate-and-plan.yml` runs on `pull_request`, using the PR's copy. So a
    PR is planned by its own workflow and applied by main's. Apply is skipped if the PR title, body or last
    commit message contains `[skip ci]`, `[ci skip]`, `[no ci]`, `[skip actions]` or `[actions skip]` anywhere, so never
    quote those patterns in a terraform PR that should apply.
  - ansible `main`: a push deploys `k3s.yml`. Every k3s node restarts k3s once, one at a time.
  - apps `main`: ArgoCD syncs.
  - A docs-only commit in packer, terraform or ansible carries `[skip ci]` in its subject (for terraform, in the PR
    title).
  - Each task names the event its merge triggers.
- **Live work.**
  - Every live mutation needs Ben's explicit OK at that step. This covers `qm`, `pvesh`, `pvesm`, `zfs`, TrueNAS,
    host network changes, `kubectl` writes, Argo patches, a packer build or terraform apply started by a merge, and
    any write to the storage VM.
  - Read-only live checks need one OK per session, for the helper in memory `backup-review-live-access`.
  - An approval relayed by another session does not count.
  - Live `kubectl` runs as `k3s kubectl` on the master through `qm guest exec`, via the pve helper. The runner user
    has no kubectl, and the helper reaches only pve and TrueNAS. GitHub reads (`gh`) run on the workstation.
    Maintenance-lock handling runs on VM300 through the helper. Task 4.0 settles where the copy tool runs (D23).
  - Remote commands are ASCII only.
- **Retained data.** Never force-detach, recreate or reformat an image. Never drop RWOP, `Retain`, prune protection
  or a source hold. Never fake a marker to pass a guard. A guard that refuses is a stop.
- **Secrets.** Refer to secrets by name only. Never print `proxmox-csi-config`, Proxmox or TrueNAS tokens, CHAP
  secrets, sealed-secret plaintext, the fencer token, `KUBECONFIG_RAW` or `ORG_DISPATCH_TOKEN`.
- **Backup windows** (Asia/Jerusalem; ansible `docs/backup-and-restore.md:35-47` at origin/main `71b0d70`). No
  mutation, VM start, copy Job or heavy I/O runs during:
  - 01:55-02:15 daily (pg-backup and Immich DB dumps at 02:00);
  - :25-:50 of 03, 09, 15 and 21 (TrueNAS snapshots at :30 and :45, then replication to `usbbk`);
  - 04:25 daily until `homelab-backup-backup` has finished (the off-site upload at 04:30);
  - Sunday 00:55-01:15 (vzdump of VM100 and VM300 at 01:00);
  - Sunday 05:25 until `homelab-backup-maint` has finished.

  Large copies also avoid 02:00-05:30. Any step that touches `usbbk` holds `/run/lock/homelab-backup.lock`
  (`exec 9>/run/lock/homelab-backup.lock; flock -n 9`) and releases it well before 04:30 and Sunday 05:30. The backup
  refuses on a pstore crash record, so an unexpected pve reboot stops everything until Ben clears it. A replica
  snapshot over 8 h old before 04:30 skips that night's upload.
- **Serialization.**
  - One maintenance-lock user at a time.
  - Cutovers run one at a time, and each finishes its 6-minute watch before the next copy starts.
  - **Freeze rule (ADR "No packer or terraform rebuild"):** from a cutover's inventory PR to its reconciliation PR,
    nothing merges in packer or terraform, and no drift or Debian-ISO PR is merged.
  - Apps merges are held around any full rebuild.
- **Maintenance lock.** A `storage.yml`, `storage-expiry.yml` or `deploy.yml` run that fails keeps the lock.
  Releasing a stale lock follows the lock helper's own release path (ansible `scripts/maintenance_lock.py`), with
  Ben's OK, after the run's log has been read. `MaintenanceLockStale` (2.4) fires after 6 h.
- **Storage VM commands** run as root through `qm guest exec <D1:storage_vmid>` via the pve helper (ASCII, no single
  quotes). The storage VM has no operator SSH key; only the workflows log in.
- **wwn.** This rule lapses when 5.3 merges. Until Retirement, no in-place terraform update of a worker merges unless
  the plan names it and carries the `wwn=` restore (memory `terraform-apply-strips-csi-wwn`). The guard from Task 1.4
  enforces this.
- **Names, timings, versions:** as in the lab plan's Global Constraints tables. Production values are the defaults.
  `pause_after` is never set, and Task 0.3 refuses it in production.
- **Evidence** goes to `~/.cache/claude-homelab-live/storage-migration/evidence/<task>/`, never to scratch (it is
  tmpfs) and never to pve `/root`, `/etc` or `/srv/backup-src`.

## Decisions for Ben

Each row names the task that waits for it. The recommendation is the plan's default; Ben's answer replaces it.
Steps write an undecided value as a named parameter, such as `<D1:storage_vmid>`.

| ID | Decision | Blocks | Recommendation |
|---|---|---|---|
| D1 | IDs and addresses: storage VM VMID and name, LAN IP (vmbr0), the bridge address on `10.99.2.0/24`; the worker bridge addresses; the placeholder VMID that owns the data disks (never a real VM, not 9999, outside every packer and terraform range) | 2.1, 2.3, 2.4, 3.4 | Decided (Ben, 2026-11-23): VMID `101`, name `storage-01`, LAN `10.9.9.40`, bridge `10.99.2.10`, workers `.21`/`.22` (`worker_bridge_start` 21), placeholder VMID `9998`. Never .60-.63 (lab statics) or 9990 (terraform test fixture). |
| D2 | Data disk sizes, `werror`/`rerror`, overcommit, after the 219 vs 288 GiB quota read (Task 1.1) | 3.4 | Decided (Ben, 2026-11-23): `retained_gib` 232, `regen_gib` 56 (288 logical, equal to the quota: no thin overcommit; about 13 and 3 GiB above the D44 reserve). Error policy: the QEMU default, no `werror`/`rerror` (bpg up to 0.121.0 has no such keys, the plan forbids a `qm set` side channel, and ADR 0017 already records no policy; a pause would end read-only after the 120 s `replacement_timeout` anyway). Accepted risk. The disks only grow (ADR grow procedure). Holes (answered 2026-11-23, read-only): `apps/k3s-block` has lz4, so zeros a copy writes should be stored as holes; tempo measures it. No quota raise or snapshot prune; Ben pre-approved the D20 switch to allocated size after tempo (see D20). |
| D3 | Worker NICs: fold `storage_nic` into the Foundation full rebuild (no in-place worker update, so no wwn strip) vs the ADR's one in-place PR per worker, each with a drain and a scripted `wwn=` restore and reboot | 2.1, 3.3 | Decided (Ben, 2026-11-23): fold `storage_nic` into the Task 3.3 rebuild (`<D3:nic_path>` = `fold`). Costs: a broken NIC needs another rebuild to undo; the D5 trim capture now spans two changes. |
| D4 | Apply mode for the Foundation rebuild PR (normal, drain, destroy) | 3.3 | **Decided (Ben, 2026-11-23): as recommended.** normal, as #243 |
| D5 | ArgoCD cold start: trim `vm-pool` minutes before the rebuild and capture it (memory `argocd-cold-start`, asked 11-21) | 3.3 | **Decided (Ben, 2026-11-23): as recommended.** yes |
| D6 | F16: the `hold_create` refusal. Log the reason on apply. Does the dry run report the hold, and with which exit code? | 0.2 | **Decided (Ben, 2026-11-21):** apply logs `hold_create set, N creates refused` and exits 1; the dry run prints the same line and keeps exit 0 (ruling R6) |
| D7 | How a failed boot check alerts (lab F2) | 2.4 | **Decided (Ben, 2026-11-23): as recommended.** Boot check writes a node-exporter textfile `storage_boot_check_ok 0/1`; alert `StorageBootCheckFailed`. After wave 1, Prometheus lives on `regen`, so a storage VM that is down takes the alert with it; the out-of-cluster path is the healthchecks.io Watchdog dead-man (live since 11-11). The runbook says so |
| D8 | kube-controller-manager `disable-force-detach-on-timeout=true`: live check or alert | 2.4, 3.2 | **Decided (Ben, 2026-11-23): as recommended.** A read-only check in Task 3.2 after deploy, plus an ansible test; no alert |
| D9 | Storage VM still stopped after a cold boot with late NFS: retry or alert | 2.4 | **Decided (Ben, 2026-11-22):** alert only, no auto-retry: Alert on `up{job="storage-vm"} == 0` for 10 min (already covered if `StorageVMDown` exists, else add it); for the time before wave 1; after wave 1 only the healthchecks Watchdog sees it (D7); Ben runs `qm start` after the alert |
| D10 | Lab F1: bound NodeStage's 30 min login retry | 2.7 | **Decided (Ben, 2026-11-23): as recommended.** Accept, plus a runbook line |
| D11 | Lab F9: when an ext4-error-flagged fs gets an offline `e2fsck` | 2.7 | **Decided (Ben, 2026-11-23): as recommended.** At the next drained window, after a copy of the LV; runbook |
| D12 | `lvremove`/tombstone gap (`lv-missing` blocks reconciles) | 2.7 | **Decided (Ben, 2026-11-23): as recommended.** Accept, plus a runbook in the F3 runbook |
| D13 | `storage_fencer_refusing{node,reason}` gauge | 5.5 | **Deferred (Ben, 2026-11-21):** automatic fencing is left out of this plan (`hold_fence` stays), so this decision waits for that later plan |
| D14 | Shared pods: karakeep data + meilisearch, Home Assistant config + matter | 4 | One hold and one outage per pod, with two copy Jobs run one after the other in it |
| D15 | The C1 app | 4.C1 | bytestash |
| D16 | Storage template pin: the branch's fixed `storage_template_vmid` 902 vs the ADR's "manifest entry" | 2.1 | Decided (Ben, 2026-11-23): the manifest, the k3s way. CI reads the `storage` entry of `packer-manifest.json` by `builds[].name` (the k3s jq form); bpg clones by VMID, taken from that entry; the clone check refuses a template whose name differs. Matches the ADR text and the post-5.13 k3s form (fixed VMID checked against the manifest name). Tasks 2.1a/2.1b rework. |
| D17 | Retained dump rule timing: the ADR says "first cutover", and its wave 1 is `regen` except that D14 pulls karakeep-data (retained) into the karakeep-meilisearch outage | 2.8 | Decided (Ben, 2026-11-23): merge it right after the first `retained` cutover, karakeep-data in wave 1 (ADR order). |
| D18 | Give F1 and F2 something to check: a canary inventory entry `f1-canary` (`origin: new`, class `regenerable`, so VG `regen`, 1 GiB) mounted by a tiny writer | 3.6, 3.7 | **Decided (Ben, 2026-11-23): as recommended.** Yes. Remove it after F2; its 3-day expiry is also the first production expiry |
| D19 | filebrowser guard (no guard on main; the ADR does not name it) | 1.3 | **Decided (Ben, 2026-11-23): as recommended.** Add it with Jellyfin's |
| D20 | The capacity gate's quantity (ADR wording conflicts) | 4.0 | Decided (Ben, 2026-11-23): as recommended, full length plus 10 GiB; pre-approved (2026-11-23) to switch to the source's allocated size plus 10 GiB when tempo's `used` delta is at most half its full length. ADR row 5 applied (D `1705df34`). |
| D21 | storage.yml lock: the ADR's "try once, exit 0 when held" and "dry run before the lock", vs the playbook running its dry run under the lock | 2.2 | **Decided (Ben, 2026-11-23): as recommended.** Split it: a dry run with no lock, then try the lock once, then the apply. The workflow does the lock |
| D22 | The persistent-journal task added for the lab ships to every node | 0.3 | **Decided (Ben, 2026-11-21):** storage VM and workers (`<D22:journal_scope>` = `storage VM and workers`): off the masters, on the storage VM role and on the workers, because Check 11 reads a worker's previous-boot journal |
| D23 | Tool host for the copy tool and the cutover (it needs `kubectl`, `gh` and the lock) | 4.0 | Ben installs pinned `kubectl` and `gh` for root on VM300, with a root-only kubeconfig for a dedicated, least-privilege ServiceAccount (an apps PR; Ben mints the token). Alternatives: the `KUBECONFIG_RAW` target file; or cluster steps through `qm guest exec` on the master and GitHub steps from the workstation |
| D24 | Guards for Jellyfin and filebrowser: whether their volumes carry an identity marker | 1.3 | **Decided (Ben, 2026-11-22):** write the markers (done, `evidence/1.3/marker-write.txt`), and no retained guard checks native layout: pure-layout apps are marker-only, content checks and the Postgres system identifier stay, NFS guards unchanged (`<D24:guard_form>` = `marker, no layout`). Amended by D47 (2026-11-22): content checks and the Postgres system identifier are dropped too |
| D25 | Departures in the terraform wiring: second steps in the existing plan and drift jobs instead of matrix legs; the clone-source check inside `maintenance_apply.py` under the lock instead of a separate `apply.yml` step; one root per PR | 2.1a | Decided (Ben, 2026-11-23): accept all three; the storage VM keeps its own root (a single root was weighed: whole-root destroy mode with no `-exclude` in Terraform 1.17.2, unreviewed dispatch applies, the `infrastructure-changed` coupling and the blast radius rule it out; no Terraform-level ordering need, so no `depends_on`). |
| D26 | A forward copy that grows the filesystem (`resize2fs`) makes a reverse copy impossible | 4.T | Keep each migrated size equal to its binding capacity until reconciliation; grow afterwards through the growth runbook |
| D27 | Removing the Proxmox CSI chart (5.1) ends reverse-copy rollback for every volume | 5.1 | Only once the last cutover's `copied` date is at least 7 days old |
| D28 | The fencer token after a k3s rebuild: only `storage.yml` copies it, so the fencer is blind until the next run: up to an hour, or about 3 h when D29 window skips fall in a row | 2.2 | **Deferred (Ben, 2026-11-21):** automatic fencing is left out of this plan (`hold_fence` stays), so this decision waits for that later plan |
| D29 | `storage.yml` hourly cron runs inside backup windows | 2.2 | **Decided (Ben, 2026-11-23):** keep the hourly schedule on GitHub Actions, as recommended; the window ends 06:00 (`<D29:backup_end>`) and 07:00 (`<D29:maint_end>`) stay provisional until confirmed from healthchecks.io durations. Keep the cron at `5 * * * *` and skip scheduled runs at run time inside the backup windows (`storage_ready.backup_window`), so DST and "until finished" ends work |
| D30 | Redis has no dump job, so "a fresh dump confirmed off-site" (ADR wave 6) has no source | 4.W wave 6 | **Decided (Ben, 2026-11-23): (b) waive.** No fresh Redis dump; ADR wave 6 names Redis as the exception (D `a922fcd6`). |
| D31 | A failed `storage.yml` or `storage-expiry.yml` run: keep the maintenance lock, or release it when only refusals were logged | 2.2 | **Decided (Ben, 2026-11-22):** keep it, as `deploy.yml` does; `MaintenanceLockStale` fires after 6 h. A `no-space` or `vg-missing` refusal (2.10) fails the apply the same way; see D40 and D42 |
| D32 | Code PRs whose paths are not all in `deploy.yml` `paths-ignore` (the bridge PR in 3.1, the PV-paths PR in 3.5) merge with `[skip ci]` in the squash subject, and the right workflow is then dispatched by hand (precedent ansible#314). Validate does not re-run on `main` for them | 3.1, 3.5 | **Decided (Ben, 2026-11-23): as recommended.** Accept. The PR's own green checks are the test gate |
| D33 | A `StorageFencerRefusing` alert on the D13 gauge | deferred (was 5.0) | **Deferred (Ben, 2026-11-21):** automatic fencing is left out of this plan (`hold_fence` stays), so this decision waits for that later plan |
| D34 | `<retained_max_age_h>` for the `retained` dump rule (not in the ADR) | 2.8 | Decided (Ben, 2026-11-23): 26, as the daily rules |
| D35 | The storage VM's `lan_gateway` (the plan carries the lab value `10.9.9.1`) | 2.1b | Decided (Ben, 2026-11-23): `10.9.9.1`. |
| D36 | The copy tool finds the source by the rule "inventory `id` equals the old image name `vm-9999-<id>.raw`" | 2.5 | **Decided (Ben, 2026-11-23): as recommended.** Accept; ids that break the rule get an explicit `source` field |
| D37 | Reverse-copy gate: its read-only mount of the new LV (`ro,noload` with MMP, via PV `mountOptions` on node-manual) is unproven, and some ids may have no guard the gate can run | 4.0 | Before the first cutover, build the per-id gate coverage list, and prove the read-only mount once on the canary (3.6) before R2 is ever needed; an id without coverage gets no reverse copy and Ben accepts that per id |
| D38 | How the one-flag guard (2.9) is proven live: the Argo CD `helm.parameters` path, `fsGroup` on a RWOP ext4 volume for a non-root app, and the guard's read of the marker | 3.9 | A second, flagged canary `f1-flagged` (an app-template app with `retained: f1-flagged`, uid 568) after the Part 3 gate and outside any wave, then removed and its expiry checked. Alternative, only if Ben drops the flagged canary from 3.9: prove it on the first real new app, added after the Part 3 gate and outside any wave (D39), with no data it needs until the three facts pass |
| D39 | New stateful apps that need a retained volume while Parts 3-4 run (part-4 "New stateful apps during Parts 3-4") | 3.9, before the first Part 4 wave | **Decided (Ben, 2026-11-22):** before Task 3.9 has passed, a new app waits (amended by D46, 2026-11-22: the old Proxmox CSI ceremony is no longer an option). After 3.9 and outside a wave, it may join directly as an `origin: new` entry with the one-flag guard (not a 4.W row). No new retained inventory entry between a wave's inventory PR and its last switch |
| D40 | Whether the `no-space` refusal (2.10) goes in `BLOCKING` (`reconcile.py:25`), so the dry run fails before the lock is taken; pairs with D31 | 2.10 | **Decided (Ben, 2026-11-22):** `no-space` goes in `BLOCKING` (`reconcile.py:25`), so the dry run fails before the lock is taken (`test_dry_run_fails_on_no_space_before_lock`) |
| D41 | After Retirement, terraform PRs that replace k3s VMs: Node retirement does not drain, so normal mode hard-stops each worker with retained volumes staged (3.10 V1 tests that crash) | 5.11, before the first terraform PR after Retirement that replaces k3s VMs | **Decided (Ben, 2026-11-22):** after Retirement, any terraform PR that replaces k3s VMs while retained volumes are staged runs in drain mode, enforced in code: a normal-mode apply whose plan replaces a k3s VM switches itself to drain mode in `maintenance_apply.py` `execute()`, after the plan read in `execute()`, dispatch included (Task 5.11). Task 3.10 V1 still runs and records the crash cost, but no longer decides D41 |
| D42 | Dry-run gate with one VG missing (2.10): (a) the dry run exits 0 and the apply runs the present class (the failed run keeps the lock under D31), or (b) keep the dry run failing before the lock | 2.10, before the Task 3.2 merge | **Decided (Ben, 2026-11-22):** option (b): the dry run keeps failing on any missing VG, before the lock; the apply-time per-class split still protects `retained` from a VG lost mid-run. Accepted cost: a `regen` disk out at dry-run time pauses `retained` creates and grows until it returns |
| D43 | Requirement 2, backup half: retained backups on the ZFS path or a storage-VM path | TrueNAS decommission (outside this plan) | **Decided (Ben, 2026-11-22):** deferred. Retained backups stay on the ZFS path (TrueNAS snapshots replicated to `usbbk/tn`, restic reads the replica). Trigger, a hard precondition of decommissioning TrueNAS: a storage-VM backup path (an LVM snapshot of each retained LV inside the storage VM, then restic from the storage VM to the off-site repo) is built, runs alongside the ZFS path for a while, and a restore from it is drilled; only then does the ZFS path go. Restores from existing off-site restic snapshots do not need ZFS; only new backups and the local ZFS-clone restore do. Not built in this plan (part-5 Not in this plan) |
| D44 | Keep D43's storage-VM path open: free space in each VG for one LVM snapshot of its largest volume | 2.6 | **Decided (Ben, 2026-11-22):** a per-VG reserve, one rule: reserve = the largest entry's size in that VG, but at least 10% of the VG usable size. `scripts/check-retained-inventory.py`'s per-VG size sum refuses an inventory that leaves less than the reserve free in that VG (`test_inventory_refused_when_reserve_not_free`, `test_inventory_accepted_with_reserve_free`). The reconcile's `no-space` precheck (2.10) is unchanged: it guards a single create or extend against actual free space |
| D45 | Requirement-5 exception: which local code it covers besides the lifecycle engine, storage-fencer and the node DaemonSet patch | none (a rule for 2.5, 2.9, 5.9 and later pieces) | **Decided (Ben, 2026-11-22):** widened by rule: small local glue with tests that never writes retained data. Permanently: the csi-driver preStop hold, the generic startup guard `guard.py` (D47) and the one-flag guard layer and its CI check (2.9). Temporarily, by name as a time-limited carve-out (it writes retained data, so not under the rule): the migration copy tool (`migrate_volume.py`, `copy_volume.sh`, 2.5), until Task 5.9 deletes it. Future pieces are judged against that rule |
| D46 | Requirement 4 for guards: the `base-configs` group guards list apps by name, so a new app could need a shared-code edit | 1.3a (freeze tests), 5.12 | **Decided (Ben, 2026-11-22):** convert all, then delete. Already in 1.3a (apps#1707, "All in #1707"): the group guards are one generic marker script in a file with no app names. Amended by D47 (2026-11-22): there are no app-owned content guards either; every guard is that script, in ConfigMap `retained-startup-guard`. After 5.9, migrated volumes the one-flag layer can serve may move to the rendered guard; the template is never deleted, because the hand-wired guards (the NFS-side ones never convert) keep mounting it, and the rendered guard mounts it too (D48). CI refuses app names in `guard.py` and any `*retained*` ConfigMap that app values mount but `retained-startup-guard`, and an `origin: new` volume's guard must be `guard.py` called with its id. Before 3.9, a new retained app waits (D39 amended) |
| D47 | Guards that are not generic: content checks, database checks against the Postgres backend, and the Postgres system identifier | 1.3a (apps#1707), 2.9, 5.12 | **Decided (Ben, 2026-11-22):** one generic startup guard, `infrastructure/base-configs/files/retained-startup/guard.py <app> <root> [<kind> [<marker-file>]]`, in ConfigMap `retained-startup-guard` (namespaces databases, home-automation, media, monitoring, operations; D48 adds every inventory namespace in 2.9); no content checks, no DB checks, no system-identifier checks, all removed in apps#1707 ("Drop them in #1707 too"). Ben: "If the guards cannot be generic, then we should consider dropping the guards." Postgres got the marker `/bitnami/postgresql/.homelab-postgres-data` (`evidence/1.3/pg-marker-write.txt`); immich-postgres already had `/data/.homelab-immich-postgres-data` |
| D48 | Task 2.9's renderer: a second marker script (`<id>-retained-guard`, argv root only) or the same `guard.py` and ConfigMap as D47 | 2.9 | **Decided (Ben, 2026-11-22): one guard.** "Yes, one guard." The layer runs `python3 -I -B /retained-startup/guard.py <id> /retained` from ConfigMap `retained-startup-guard`; 2.9 deletes `retained-volumes-guard.yaml` (it rendered only `<id>-retained-guard`), and `retained-startup-guard.yaml` adds every inventory namespace to its fixed five. 1.3a's `test_no_other_retained_configmap_is_mounted` is unchanged |
| D49 | Genericity audit 2026-11-22: unmerged-branch findings folded into Part 2 (Ben OK); main's Postgres completion gate handled in its own PR (session postgres-enrollment-one) | 1.4, 2.1a, 2.1b, 2.2, 2.3, 2.6, 2.9, 2.10, 2.11, 2.12 | **Decided (Ben, 2026-11-22):** "I also approve folding the unmerged branches into part 2". Each finding sits in the task that touches its files; new tasks 2.11 (packer) and 2.12 (apps democratic-csi values). Ledger: "Audit fold-in (Ben, 2026-11-22)" at the end of `outline.md` (not in the assembled plan) |
| D50 | Move the k3s root (VMs 200-202) from telmate 3.0.2-rc10 to bpg/proxmox 0.123.1 (the `storage/` pin since terraform#248) by import, and its sub-choices (a)-(k) | 5.13 Step 3 | **Decided (Ben, 2026-11-23): all sub-choices as recommended** ("Accept all"). **The move itself is decided (Ben, 2026-11-16):** "no reason to have 2 separate Proxmox providers"; bar in `handoff-csi-slots.md` item 6. Sub-choices, recommended: (a) keep 5.3 a separate telmate PR; cost: none beyond one more PR, while folding it puts `pool_id` into the adoption plan and loses 5.3's wwn-guard proof. (b) `reboot_after_update = false`, permanently, as `storage/`; cost: a later CPU or memory PR applies as pending until the next reboot or rebuild, drift cannot see that, and an `os_disk_size` change errors instead of applying. (c) `stop_on_destroy = false`, `timeout_shutdown_vm = 240`, `timeout_stop_vm = 600`, `purge_on_destroy = true` (false if Step 1 finds a vzdump job, replication job or HA resource naming 200-202 by VMID); cost: a hung guest fails the apply after 240 s, see (g). (d) clone source fixed at template VMID 901, checked by name against the manifest `vm_name` in every mode, destroy included; the manifest `vm_name` is the replace trigger; cost: none. (e) the cohort key is the master's `network_device[0].mac_address`, not the SMBIOS uuid (bpg leaves `smbios` empty in state); fallback if Step 2 shows the MAC is not unknown on replace: key on the master's `terraform_data.generation.output` (not `id`, which changes only when the resource is replaced; `output` should plan unknown on any `input` change: image, incarnation or nonce; Step 2's cohort test settles it if the fallback is taken), cost: a master replace forced by another attribute (`vm_id`, `node_name`) no longer rebuilds the workers, and no planned PR changes those; `smbios {}` is not a free fallback: imported VMs keep `smbios = []` in state (vm.go:5670-5683), so adding the block is a change and bpg writes a new random uuid (vm.go:4119-4121), pending under (b), so each guest's DMI uuid changes at its next reboot, a live identity change that ansible's `k3s_node_retirement` keys on (`filter_plugins/k3s_node_retirement.py:16-29`; it should match again once kubelet reports the new `systemUUID`, unproven); pinning today's uuid instead would make every replacement reuse it, so `candidate()` returns `{}` and retirement silently never fires. (f) keep the `PM_*` secret names, mapped by `scripts/bpg_env.sh`; cost: none. (g) drop #245 (merged 2026-11-22) and accept two changes: a failed apply no longer restarts the VMs (`restart_vms`), so it can leave a VM off with the lock held, and a guest that outlasts 240 s fails the apply (PVE then force-stops it) where #245 fell back to a hard stop; alternative: port #245's restart to bpg state ids, cost about 40 lines and the `PM_*` reads kept. (h) a canary before the first real replace (Ben OK): PR B creates a throwaway VM (VMID 299 if free) from 901 through the same module with `started = false`, `on_boot = false`, the GPU mapping and no `k3s` tag, and PR C destroys it; cost: two more apply events, each a full ansible deploy that restarts k3s, and the canary does not prove guest shutdown, the cloud-init boot, the agent or GPU function; alternative: accept that the first bpg create is the full-cluster replace. (i) the failed-destroy retry property is lost under bpg (the generation updates before the VM's destroy fails), so accept it with a recovery: a `rebuild_nonce` input in every generation, bumped by a one-line PR; cost: until that PR the cluster mixes images and state says the rollout finished, a dispatch after a failed replace silently yields mixed images (the runbook forbids it), a bump of the shared nonce replaces all three VMs, not only the stale one, and the force-stopped VM must first be started by hand (`qm start`, Ben OK) and its node Ready, or the nonce PR's drain times out on that node's pods (NotReady, no kubelet to confirm deletes) with the lock held; nodes the failed run cordoned stay cordoned and are not in the next run's `drained_nodes`, so they are uncordoned by hand; if the failed run also destroyed or recreated another VM, Ready is unreachable: delete the dead Nodes (Ben OK) while the master serves the API, otherwise destroy mode; and a failed run's lock is released by ansible `docs/maintenance-lock-release.md` (ansible#352). (j) telmate stays in the adoption PR to forget its resources, and PR B (mandatory, enforced by CI) drops telmate, `imports.tf` and the `removed` blocks before any other terraform merge, replace, destroy-mode run or packer PR, and is also PR A's recovery path (Step 10); cost: one more PR, plus a CI gate that is a red check only (admins can bypass branch protection), so `execute()` is the hard stop. (k) the storage VM keeps `stop_on_destroy = true`, and PR B records why in a one-line comment in `storage/main.tf` (comment only, no plan change): `prevent_destroy = true` refuses every destroy, replace included, so the VM goes only in the deliberate rebuild PR pair after the writer drain (Task 3.7, runbook `storage-vm-rebuild.md`); its data disks survive any stop (`purge_on_destroy = false`, `delete_unreferenced_disks_on_destroy = false`, owned by the placeholder VMID); lab B7 proved this path (971 hard-stopped and destroyed in 3 s, disks kept) and Gate F1 (Task 3.7, before Part 5) re-runs it in production; and #245's shutdown never covered it (`vm_targets` filters `proxmox_vm_qemu`), so nothing is lost relative to today; cost: if a rebuild skips the writer drain, an initiator with a live session sees I/O errors (F9/F13 restage) and in-flight unacknowledged writes fail; alternative `false` with `timeout_shutdown_vm = 180` (the host-reboot `qm shutdown` bound; bpg's default is 1800 s), cost: a destroy path Gate F1 never ran, and a hung guest fails the rebuild apply with the lock held. D41's anchor moves: the drain switch follows the one plan read in `execute()`, since the wwn guard is deleted |
| D51 | How a whole-disk restore (runbook `storage-vm-restore.md` steps 5-6) runs the reconcile under the restore lock: the vault password, SSH key and Proxmox token exist only as Actions secrets, so a hand run on the runner cannot work | 2.13, 2.7 | **Decided (Ben, 2026-11-23): option B.** `storage.yml` gains an optional `workflow_dispatch` input `held_lock_owner`; set, the job adopts the existing lock (owner must equal the input and start `claude-code/storage-restore/`), takes the nonce from the lock record without printing it, reconciles, and never releases. Rejected: A (`lock.sh run` on the runner; needs the secrets on the host), C (release and dispatch; a failed run keeps its own lock, so locks swap twice with a gap). |

## Review Focus

1. **A copy of a live filesystem.** The source still has a writer: the operator re-creates the pod, a CronJob or
   Job mounts it, or an RWOP claim is held elsewhere. Expected: the copy Job refuses unless the source PVC has no
   mounting pod and no VolumeAttachment other than the Job's own. Pinned in Task 2.5:
   `test_refuses_when_source_has_pod`.
2. **The wrong `volumeHandle`.** A temporary PV points at another app's LV or image. Expected: the Job refuses unless
   both handles match the inventory entry and the source binding file. Task 2.5:
   `test_refuses_handle_not_in_inventory`.
3. **The flag PR merged before a verified copy.** Expected: the migrated guard refuses an empty or foreign
   filesystem, and the app never starts. Task 2.6: `test_switch_requires_guard_mounted`. A CI check refuses a
   binding switch whose entry has no `copied` marker. Task 2.6: `test_flag_without_copied_marker_fails`.
4. **ArgoCD prunes a temporary pair.** Expected: every temporary PV and PVC carries
   `Prune=false,Delete=false` and `Retain`, and no Argo app owns them. Task 2.5: `test_temp_pairs_not_owned`.
5. **A rebuild lands mid-cutover.** Expected: the cutover pre-check refuses while a packer `build.yml` run or a
   terraform apply run is active, while any packer, terraform or ansible PR has auto-merge enabled, or while the
   maintenance lock is held by someone else. Open drift PRs alone do not block, because drift opens them daily and the
   freeze rule forbids merging them. Task 2.5: `test_precheck_refuses_active_build`.

## Pinned interfaces (every part uses these names)

| Thing | Name |
|---|---|
| Copy tool | apps `scripts/storage/migrate_volume.py` with subcommands `precheck <id>`, `render <id> --direction forward\|reverse --out <dir>`, `verify-teardown <id>`; the Job runs `scripts/storage/copy_volume.sh` inside it from a ConfigMap |
| Rendered pair names | PV/PVC `migrate-src-<id>`, `migrate-dst-<id>`; Job `migrate-<id>`; all in the app's namespace; label `homelab.starktastic.net/migration=<id>` |
| Copy tests | `scripts/storage/tests/test_migrate_volume.py` |
| Inventory | `infrastructure/base-configs/files/retained-volumes.json` with the new field `copied` (ISO date) |
| Binding switch CI check | `scripts/check-retained-inventory.py` (extended), tests `scripts/storage/tests/test_retained_inventory.py` |
| ansible workflows | `.github/workflows/storage.yml`, `.github/workflows/storage-expiry.yml`, `.github/workflows/storage-bridge.yml` |
| apps dispatch | `.github/workflows/storage-dispatch.yaml` sending event `storage-changed` (2.4) |
| New alerts | `StorageBootCheckFailed`, `StorageVMDown`, `StorageDatasetLow`, `MaintenanceLockStale`, in `services/operations/kube-prometheus-stack/manifests/storage-vm.yaml` (with the existing storage alerts) |
| Runbooks (apps `docs/runbooks/`) | `storage-vm-restore.md`, `storage-vm-fencing.md`, `storage-vm-growth.md`, `storage-vm-crashed-create.md`, `storage-vm-expiry.md`, `storage-vm-readonly-fs.md`, `storage-vm-rebuild.md`, `storage-vm-upgrade-held.md`, `storage-vm-bootstrap.md`, `storage-vm-cutover.md`, `pve-planned-reboot.md` |
| Copy tool additions | `precheck <id> --direction forward\|reverse`; the reverse gate files `gate.yaml`, `migrate-gate-<id>`, `migrate-guard-<id>` (2.5) |
| New claim names | `<id>-iscsi`; operator StatefulSet claims `<id>-iscsi-<sts>-0` (2.6) |
| Cutover lock operation | `storage-cutover:<id>[:<id2>]` (one hold for a D14 pair) |
| New ansible playbooks | `storage-dry-run.yml` (D21), `storage-host-metrics.yml` (2.4) |
| Evidence | `~/.cache/claude-homelab-live/storage-migration/evidence/<task>/` |

---

## Part 0: preparation (offline)

Everything here runs on the workstation. It touches only the six worktrees and the evidence folder. There are no live
commands, no pushes and no PRs. Parts 1 and 2 build on the rebased branches and on the evidence this part writes.

Rules for this part, on top of the Global Constraints:
- **No `[skip ci]` in any Part 0 commit.** Every commit here rides a `feat/`, `fix/` or `docs/` branch. Some of those
  branches merge as intended live events: packer builds in 3.3, the ansible deploy in 3.2, the terraform applies in 1.4
  and 2.1.
  - A marker in a branch commit skips that PR's required checks.
  - GitHub's squash body lists the branch subjects.
  - terraform `apply.yml` (origin/main :48-58) scans the PR title, the body and the last commit message for
    `\[(skip ci|ci skip|no ci|skip actions|actions skip)\]`.

  So a marker on a branch commit can silently cancel the merge's build, apply or deploy. The docs-only rule belongs on
  the squash subject of a docs-only PR, at merge time (memory `pr-merge-mechanics`).
- **One env file.** Shell state does not carry between calls, so Task 0.1 Step 1 writes
  `~/.cache/claude-homelab-live/storage-migration/evidence/env.sh`. Every command block starts by sourcing it. It
  defines:
  - the worktrees: `$A`, `$P`, `$T`, `$AP`, `$W`, `$D`;
  - the tools: `$TF` (terraform v1.17.2, CI's version) and `$PC` (the provider cache, bpg 0.118.0 and telmate
    3.0.2-rc10);
  - the Pythons: `$VPY` (the existing venv: PyYAML, `websocket-client`, ansible-core 2.21.6) and `$VPY15` (ansible
    15.0.0, set up in Step 1);
  - `$EVR`, the evidence root;
  - `g`, which is `git` with the identity. The workstation has no git identity, and rebases also write a committer.
- **Missing tools** are recorded as "not run locally, PR CI covers it", never installed without asking:
  - packer and shellcheck are not on the workstation and have no local image (`docker image ls`, 2026-11-21);
  - shfmt runs from the local `mvdan/shfmt:latest`, promtool from `prom/prometheus:v3.16.0`, and helm from
    `~/.cache/claude-household-boundary/bin/helm` (`alpine/helm:4.3.1`; CI has v4.3.2).
- **Evidence** goes to `$EVR/0.<n>/`.

### Task 0.1: Rebase and re-qualify the branches

**Files:**
- Rebase (worktrees under `~/.cache/claude-homelab-live/worktrees/`, all on 2026-11-21):

  | Short | Worktree | Branch | Tip | Behind |
  |---|---|---|---|---|
  | A | `ansible-storage-vm` | `feat/retained-storage-vm` | `a036b47` | 9 |
  | P | `packer-storage-vm` | `feat/retained-storage-vm` | `e43d185` | 1 |
  | T | `terraform-storage-vm` | `feat/retained-storage-vm` | `edb2dbf` | 2 |
  | AP | `apps-storage-vm` | `feat/retained-storage-vm` | `b2c3d350` | 34 |
  | W | `terraform-csi-wwn-guard` | `fix/csi-wwn-guard` | `da37a0d` | 2 |
- Modify (T):
  - `storage/variables.tf`: drop `variable "pool_id"` (:91-95);
  - `storage/main.tf:10`: drop `pool_id`;
  - `storage/providers.tf:19`: reword the comment.
- Test (T): `scripts/tests/test-storage-root.py`. `test_pool_is_lab_only` (:205-210) becomes `test_no_pool_id`.
- Modify (A): `.github/workflows/validate.yml`, three steps in job `lint`.
- Test (A): `scripts/tests/test_storage_vm_role.py`, `WorkflowTests` (:684).
- Modify (P):
  - `README.md` and `CLAUDE.md` (the conflict resolution);
  - `docs/i915-sriov.md:26`;
  - `docs/diagrams/build-pipeline.svg`, `docs/diagrams/chain.svg` and `docs/diagrams/banner.svg`.
- Test (P): `scripts/tests/test_image_layout.py`, `TestImageLayout`.

**Interfaces:**
- Consumes `origin/main` as read on 2026-11-21: ansible `71b0d70`, packer `d510340`, terraform `cc493bd` and apps
  `c5f60a0d`. Step 1 re-reads them.
- Produces:
  - five rebased branches, each with a backup ref on its old tip;
  - `$EVR/0.1/heads.txt` (old tip, new tip, base) and `$EVR/0.1/*.log`;
  - the tests `test_no_pool_id` (T), `test_validate_runs_every_storage_test` (A) and `test_docs_name_current_files`
    (P).
- Consumers: 1.2 reads A's `roles/k3s_common`, 1.4 merges W, and Part 2 builds on all five.

- [ ] **Step 1: Write the env file, set up ansible 15, record state and make backup refs.**
  Run:
  ```sh
  mkdir -p ~/.cache/claude-homelab-live/storage-migration/evidence/0.1
  cat > ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh <<'EOF'
  WT=~/.cache/claude-homelab-live/worktrees
  A=$WT/ansible-storage-vm P=$WT/packer-storage-vm T=$WT/terraform-storage-vm AP=$WT/apps-storage-vm
  W=$WT/terraform-csi-wwn-guard D=$WT/apps-adr-0017
  TF=~/.cache/claude-homelab-live/bin/terraform PC=~/.cache/claude-homelab-live/tf-plugin-cache
  VPY=~/.cache/claude-homelab-live/venv/bin/python V15=~/.cache/claude-homelab-live/venv-ansible15
  VPY15=$V15/bin/python COLL15=~/.cache/claude-homelab-live/collections-ansible15
  EVR=~/.cache/claude-homelab-live/storage-migration/evidence
  g() { git -c user.name="Ben Faingold" -c user.email=<ben-git-email> "$@"; }
  EOF
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; EV=$EVR/0.1
  for r in $A $P $T $AP $W; do
    git -C $r fetch origin
    test -z "$(git -C $r status --porcelain)" || echo "DIRTY $r"
    echo "$r $(git -C $r rev-parse HEAD) $(git -C $r rev-parse origin/main)" >> $EV/heads-before.txt
  done
  for r in $A $P $T $AP; do git -C $r branch backup/storage-vm-pre-rebase-20261121; done
  git -C $W branch backup/csi-wwn-guard-pre-rebase-20261121
  ```
  Then set up ansible 15. This downloads from PyPI and Galaxy, so ask Ben once first:
  ```sh
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh
  python3 -m venv $V15 && $V15/bin/pip install -r $A/requirements.txt PyYAML
  $V15/bin/ansible-galaxy collection install -r $A/requirements.yml -p $COLL15
  ```
  T and W share terraform's git dir, so each gets its own backup name (AP and D share apps' the same way). The
  20261116 refs stay.
  Expected:
  - no `DIRTY` line;
  - five new refs under `refs/heads/backup/`;
  - `$V15/bin/ansible --version` runs.

  If an `origin/main` SHA differs from the Interfaces line, run `git -C <r> merge-tree --write-tree --name-only
  origin/main HEAD`. Stop if a file conflicts that this task does not name.

- [ ] **Step 2: Rebase A.** merge-tree is clean (tree `0431355`).
  Run:
  ```sh
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh
  g -C $A rebase origin/main
  git -C $A grep -n -e 'chart_version' -e '--enable-helm' -- roles/bootstrap_cluster/tasks/argocd.yml
  git -C $A diff --quiet origin/main HEAD -- group_vars/proxmox_hosts roles/proxmox_guest_startup roles/i915_sriov \
    requirements.txt && echo KEPT
  git -C $A rev-list --count origin/main..HEAD
  ```
  Expected:
  - no conflict;
  - argo-cd `10.18.2` (#349) and `kustomize.buildOptions: --enable-helm` are both present;
  - `KEPT`: ansible#340 (ARC cap, VM300 balloon), the host i915 pin and ansible 15.0.0 are untouched;
  - `32` commits.

- [ ] **Step 3: Rebase P.** It conflicts in `CLAUDE.md` and `README.md`, from #114 `d510340`.
  Run: `g -C $P rebase origin/main`. It stops at each of `ceab867`, `d3f390f`, `091f578` and `e43d185` that conflicts.
  Resolve every stop the same way:
  - Keep main's README layout: the SVG `<img>` blocks, the sections and the tables.
  - Carry in the branch's facts:
    - templates base 900, k3s 901 and storage 902;
    - the files `scripts/{base,k3s,storage,seal}.sh` and `source-*`/`build-*.pkr.hcl`;
    - the job order and the manifest by name;
    - the branch's CLAUDE.md lines `:3-4`, `:10`, `:57` and `:81-83` (the manifest contract), as they stand before the
      rebase.
  - Drop the branch's mermaid block (README `:56-60`). The SVGs replace it.
  - Then `git -C $P add CLAUDE.md README.md && g -C $P rebase --continue`.

  Then run `git -C $P diff origin/main HEAD -- debian.auto.pkrvars.hcl` and
  `git -C $P grep -n xelp_enable_ccs -- scripts/k3s.sh`.
  Expected:
  - 4 commits on `d510340`;
  - the pkrvars diff is one comment line, and `i915_sriov_version = "2025.12.10.2"` and
    `i915_sriov_kernel_series = "6.12"` are unchanged;
  - the #113 GRUB line is at `scripts/k3s.sh:89`.

  Steps 9 and 10 fix the diagrams and the remaining stale names.

- [ ] **Step 4: Rebase T.** merge-tree is clean (tree `5bd485d`).
  Run: `g -C $T rebase origin/main`, then
  `git -C $T diff --quiet origin/main HEAD -- main.tf modules terraform.tfvars packer-manifest.json && echo KEPT`.
  Expected:
  - no conflict;
  - `KEPT`. That keeps #243 `network_queues = var.worker_cores` (`main.tf:69`, `modules/vm/main.tf:64`) and #241
    `master_memory = 12288` and `worker_memory = 24576`.

- [ ] **Step 5: Rebase AP.** It conflicts in `scripts/check-alert-policy.py`, from #1680 `b5264477`.
  Run: `g -C $AP rebase origin/main`. Keep both sides of the conflict, main's `TempoBlocklistPollFailing` case first and
  the branch's storage-vm ScrapeConfig and rule cases after it. Then
  `git -C $AP add scripts/check-alert-policy.py && g -C $AP rebase --continue`.
  Then:
  ```sh
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; cd $AP
  grep -c TempoBlocklistPollFailing scripts/check-alert-policy.py; grep -c storage-vm scripts/check-alert-policy.py
  grep -n -e 'v4.3.2' -e 'Check retained volume inventory' -e 'fetch-depth: 0' .github/workflows/validate-and-diff.yml
  ```
  Expected:
  - 7 commits on `origin/main`;
  - both counts are at least 1;
  - helm `v4.3.2` (#1685), the inventory step and `fetch-depth: 0` are all present.

- [ ] **Step 6: Rebase W.** It conflicts in `CLAUDE.md` and `README.md`, from #242 `ca3942a`. `maintenance_apply.py` is
  clean against main.
  Run: `g -C $W rebase origin/main`. Resolve on main's layout:
  - re-insert the branch's CLAUDE.md bullet that begins "Any in-place update of a VM holding CSI disks strips `wwn=`";
  - re-insert the README paragraphs that begin "This keeps CSI slots out of the plan diff", in #242's section on
    Proxmox CSI disk ownership.

  Then `git -C $W add CLAUDE.md README.md && g -C $W rebase --continue`.
  Expected: 1 commit on `cc493bd`, and `git -C $W diff --stat origin/main HEAD` lists 9 files: `da37a0d`'s 8
  plus `docs/storage-safe-maintenance.md`, where #242 moved the CSI section (done 2026-11-21: `8801807`).
  Task 2.1a's `--chdir` also edits `maintenance_apply.py`, so T rebases again after 1.4 merges W.

- [ ] **Step 7: T: write the failing `test_no_pool_id`.** Replace `test_pool_is_lab_only` (:205-210) with:
  ```python
  def test_no_pool_id(self):
      # The storage VM is never in a resource pool (ADR 0017: not in the Proxmox CSI pool).
      for name in ('main.tf', 'variables.tf'):
          self.assertNotIn('pool_id', (STORAGE / name).read_text(), name)
      self.assertIsNone(self.planned_vm().get('pool_id'))
  ```
  Run: `cd $T && TERRAFORM=$TF STORAGE_PLUGIN_DIR=$PC python3 scripts/tests/test-storage-root.py
  StorageRoot.test_no_pool_id` (source env first).
  Expected: FAIL, `'pool_id' unexpectedly found in 'main.tf'`.

- [ ] **Step 8: T: drop the lab pool and reword the pin comment.**
  - Delete `variable "pool_id"` (`storage/variables.tf:91-95`) and `pool_id = var.pool_id` (`storage/main.tf:10`).
  - Keep every F10 part of `edb2dbf`: the `virtio0` block, the `path_in_datastore` validation and
    `test_root_disk_added_to_existing_state`. This is a new commit on top, and history is not rewritten.
  - Reword `storage/providers.tf:19` to
    `# Newest release on or before 2026-10-26; the version ADR 0017's lab qualified.`

  Run: the whole `test-storage-root.py`, then `$TF fmt -check -recursive .`
  Expected: PASS (11 tests), and fmt is clean.
  Commit: `g -C $T commit -am "fix(storage): drop the lab-only pool_id, keep the F10 root disk"`. The body is
  `The ADR 0017 lab token was pool-scoped; production sends no pool.`, then the Co-Authored-By line.

- [ ] **Step 9: P: write the failing docs test.** In `TestImageLayout`:
  ```python
  def test_docs_name_current_files(self):
      docs = ["README.md", "CLAUDE.md"] + sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").rglob("*")
                                                 if p.suffix in (".md", ".svg"))
      for rel in docs:
          for old in ("bootstrap.sh", "delete_builder_user.sh", "source.pkr.hcl", "build.pkr.hcl",
                      "proxmox-iso.debian-13", "template VM 900"):
              self.assertNotIn(old, read(rel), f"{rel}: {old}")
      for vmid in ("900", "901", "902"):
          self.assertIn(vmid, read("README.md"))
  ```
  Run: `cd $P && python3 scripts/tests/test_image_layout.py`
  Expected: FAIL. On main the hits are:
  - `docs/i915-sriov.md:26`;
  - `docs/diagrams/build-pipeline.svg:3,128,130,146`;
  - `docs/diagrams/chain.svg:3,140`;
  - any README alt text that Step 3 kept from main (main `README.md:2,19,22,32`).

  `banner.svg:69` draws "900 / template VM" as a stat. That form does not match the test, so Step 10 fixes it by eye.

- [ ] **Step 10: P: fix the docs and redraw the diagrams.**
  - `docs/i915-sriov.md:26`: `scripts/bootstrap.sh` becomes `scripts/k3s.sh`.
  - `build-pipeline.svg`: redraw it with jobs `base`, then `k3s` and `storage`; the scripts `base.sh`, `k3s.sh`,
    `storage.sh` and `seal.sh`; and the two manifest PRs.
  - `chain.svg`, `banner.svg:69` and the README alt texts: the template becomes "templates 900 (base), 901 (k3s) and
    902 (storage)".
  - Tooling. The CLAUDE.md "Diagram tooling" row is stale: `.github` origin/main `67c2d64` retired `render-diagrams.sh`
    and `diagrams.yml`. The real tool is the uncommitted kit in `~/Projects/homelab/readme-redesign/kit/` (memory
    `readme-redesign`). `stamp.py` resolves its paths from its own location, so any working directory works. It writes
    into the `readme-redesign/packer` worktree, not into P.
    ```sh
    . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; R=~/Projects/homelab/readme-redesign
    test -z "$(git -C $R/packer status --porcelain)" || echo "DIRTY kit worktree: stop"
    python3 $R/kit/stamp.py packer && for f in build-pipeline chain banner; do
      diff -q $R/packer/docs/diagrams/$f.svg $P/docs/diagrams/$f.svg; done  # unchanged templates == P?
    ```
    - If the diffs are silent, edit `kit/packer/{build-pipeline,chain,banner}.tpl.svg`, re-stamp, copy the three SVGs
      to `$P/docs/diagrams/`, and check them with `python3 $R/kit/preview.py packer` and
      `python3 $R/kit/stamp.py packer --stress && python3 $R/kit/preview.py packer --stress`.
    - If they differ, the kit is out of sync with main (UNVERIFIED today). Hand-edit P's SVGs instead, and keep the
      scoped ids and classes (memory gotcha).
    - Either way, end with `git -C $R/packer checkout -- docs/diagrams`.
  - From `$P`, run `python3 ~/Projects/homelab/.github/scripts/check-readme-images.py`.

  Run: `python3 scripts/tests/test_image_layout.py`
  Expected: PASS, and the image check passes.
  Commit: `g -C $P commit -am "docs(images): name the three templates and scripts in the docs and diagrams"`.

- [ ] **Step 11: A: write the failing CI-wiring test.** In `WorkflowTests` (`test_storage_vm_role.py:684`):
  ```python
  def test_validate_runs_every_storage_test(self):
      text = (ROOT / '.github/workflows/validate.yml').read_text()
      lint = text.index('Install ansible-lint')
      tests = sorted((ROOT / 'scripts/tests').glob('test_storage_*.py'))
      for path in tests + [ROOT / 'scripts/tests/test_argocd_bootstrap.py']:
          step = f'run: python3 scripts/tests/{path.name}'
          self.assertIn(step, text, path.name)
          self.assertGreater(text.index(step), lint, path.name)  # test_argocd_bootstrap imports ansible
  ```
  Run: `cd $A && $VPY15 scripts/tests/test_storage_vm_role.py WorkflowTests`
  Expected: FAIL. `test_storage_host.py`, `test_storage_lvm.py` and `test_argocd_bootstrap.py` have no step.

- [ ] **Step 12: A: add the steps.** In job `lint`, after "Test storage VM role and playbooks" (:96-97), add:
  - "Test storage host adapters", `run: python3 scripts/tests/test_storage_host.py`;
  - "Test storage LVM adapter", `run: python3 scripts/tests/test_storage_lvm.py`;
  - "Test Argo CD bootstrap values", `run: python3 scripts/tests/test_argocd_bootstrap.py`.

  Run: the Step 11 command. Expected: PASS.
  Commit: `g -C $A commit -am "ci(storage): run the storage host, LVM and Argo CD bootstrap tests"`.

- [ ] **Step 13: Re-qualify A under ansible 15.0.0.**
  Run:
  ```sh
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; EV=$EVR/0.1; cd $A
  $V15/bin/ansible --version > $EV/a-ansible-version.log
  for t in scripts/tests/test_storage_*.py scripts/tests/test_argocd_bootstrap.py \
      scripts/tests/test_k3s_storage_settings.py scripts/tests/test_proxmox_csi_bootstrap.py \
      scripts/tests/test_proxmox_storage_bridge.py scripts/tests/test_proxmox_backup.py; do
    $VPY15 $t > $EV/a-$(basename $t .py).log 2>&1 || echo "FAIL $t"; done
  $VPY15 -m unittest discover -s scripts/tests -p 'test_maintenance*.py' > $EV/a-maintenance.log 2>&1 || echo FAIL
  echo dummy > $EV/dummy-vault-pass
  ANSIBLE_VAULT_PASSWORD_FILE=$EV/dummy-vault-pass ANSIBLE_COLLECTIONS_PATH=$COLL15 \
    $V15/bin/ansible-playbook -i lab/inventory.example.yml --syntax-check k3s.yml proxmox-storage-bridge.yml \
    storage.yml storage-expiry.yml proxmox-backup.yml proxmox-guest-startup.yml > $EV/a-syntax.log 2>&1 || echo FAIL
  ```
  - `inventory/proxmox.yml` is the dynamic `community.proxmox.proxmox` plugin, which needs the `PROXMOX_*` secrets.
    CI's own form, `-i inventory/proxmox.yml` with the full list at `validate.yml:155`, therefore runs only in the PR
    (LA:110). The example inventory has hosts and groups only.
  - The env var overrides `ansible.cfg`'s `vault_password_file = .vault_pass`, so nothing is written as `.vault_pass`.
  - `ansible-lint` runs in CI (LA:149).

  Expected:
  - no `FAIL` line;
  - `a-syntax.log` lists `playbook: <name>` for each playbook;
  - the ansible-core version is recorded.

  A test that fails only under 15.0.0 is a stop: bring the log to Ben (m12).

- [ ] **Step 14: Re-qualify P.**
  Run:
  ```sh
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; EV=$EVR/0.1; cd $P
  python3 scripts/tests/test_image_layout.py > $EV/p-layout.log 2>&1 || echo FAIL
  python3 scripts/tests/test_i915_compat.py > $EV/p-i915.log 2>&1 || echo FAIL
  docker run --rm -v "$PWD:/w" -w /w mvdan/shfmt:latest -i 2 -ci -s -d scripts/ || echo FAIL
  for f in scripts/i915_compat.py scripts/tests/test_i915_compat.py; do
    git -C $A show origin/main:$f | cmp - $f || echo "DIFFERS $f"; done
  ```
  Expected: no `FAIL` or `DIFFERS` line. The checker and its test stay byte-identical with ansible's.
  `packer fmt -check`, `packer validate` (with the placeholder vars from P `CLAUDE.md:22-24`) and
  `shellcheck scripts/*.sh` are "not run locally, PR CI covers it" (`validate.yml`, `format.yml`), unless Ben OKs
  pulling `hashicorp/packer:light` and `koalaman/shellcheck`.

- [ ] **Step 15: Re-qualify T and W.**
  Run:
  ```sh
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; EV=$EVR/0.1; cd $T
  TERRAFORM=$TF STORAGE_PLUGIN_DIR=$PC python3 scripts/tests/test-storage-root.py > $EV/t-root.log 2>&1 || echo FAIL
  TERRAFORM=$TF COHORT_PLUGIN_DIR=$PC python3 scripts/tests/test-rebuild-cohort.py > $EV/t-cohort.log 2>&1 || echo FAIL
  python3 scripts/tests/test-check-clone-source.py > $EV/t-ccs.log 2>&1 || echo FAIL
  $TF fmt -check -recursive . || echo FAIL
  $TF -chdir=storage init -backend=false -plugin-dir=$PC > /dev/null && $TF -chdir=storage validate || echo FAIL
  rm -rf storage/.terraform storage/.terraform.lock.hcl
  mkdir -p $EV/helper && git -C ~/Projects/homelab/ansible archive 887269798650e88fed791bb4f22a47bf50ad17be scripts \
    | tar -x -C $EV/helper   # the helper commit CI pins, validate-and-plan.yml:19
  cd $W
  PYTHONPATH=$EV/helper/scripts $VPY scripts/tests/test-maintenance-workflow.py > $EV/w-maint.log 2>&1 || echo FAIL
  TERRAFORM=$TF COHORT_PLUGIN_DIR=$PC python3 scripts/tests/test-rebuild-cohort.py > $EV/w-cohort.log 2>&1 || echo FAIL
  ```
  Expected: no `FAIL` line, and validate prints `Success!`. W's test imports only the stdlib and loads the helper
  through `PYTHONPATH`. Whether it needs anything beyond the pinned `scripts/` is UNVERIFIED.

- [ ] **Step 16: Re-qualify AP.**
  Run:
  ```sh
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; EV=$EVR/0.1; cd $AP
  $VPY -m unittest discover -s scripts/storage/tests -v > $EV/ap-storage.log 2>&1 || echo FAIL
  $VPY scripts/check-retained-inventory.py --base origin/main --override-label storage-removals-approved || echo FAIL
  PATH=~/.cache/claude-household-boundary/bin:$PATH $VPY scripts/check-alert-policy.py \
    docker run --rm -i --network none --entrypoint promtool prom/prometheus:v3.16.0 \
    > $EV/ap-alerts.log 2>&1 || echo FAIL
  ```
  Expected:
  - the storage tests PASS, including `test_empty_inventory_renders_nothing`;
  - the inventory check passes on `[]`;
  - the alert policy passes.

  `check-alert-policy.py:28` runs `docker manifest inspect`, which needs the network. If only that leg fails, record
  "network leg not run locally, PR CI covers it" (LAp:60).

- [ ] **Step 17: Record the result.**
  - `$EVR/0.1/heads.txt`: each worktree's old tip, new tip and `origin/main`.
  - `$EVR/0.1/commits.md`: each new commit as repo, files and message (CLAUDE.md "Working across repos").
  - `$EVR/0.1/unowned-stale.md`: the text outside packer that names the single template or `bootstrap.sh`. It
    becomes wrong only when 3.3's packer merge moves the k3s template to 901. Hits on origin/main:
    - ansible `docs/i915-sriov.md:50`;
    - terraform `README.md:33` and `docs/diagrams/cluster-topology.svg:3,120`;
    - `.github` `CLAUDE.md:11,41`, `profile/README.md:27`, and `docs/diagrams/platform.svg:3,186`,
      `delivery-chain.svg:126` and `workflow-map.svg:207`;
    - apps: none.

    Task 5.6 owns the `.github` rows. The others need a docs-only PR after 3.3, with `[skip ci]` in its squash subject
    only (Task 3.3 Step 11).

  Expected: the three files exist. Nothing is pushed.

### Task 0.2: F16 (TDD)

`<D6:hold_line>` = `hold_create set, N creates refused` (recommended): an apply under `hold_create` logs it and exits 1.
`<D6:dry_run_exit>` = `0` (recommended, ruling R6): the dry run logs the same line and keeps its exit code. N counts
the `hold-create` refusals. The F16 case is N = 0: every entry already has an LV, `plan.py:116-117` sets `d.fail` with
no refusal, and today the run exits 1 with nothing logged. If Ben sets `<D6:dry_run_exit>` = 1, add `hold-create` to
`BLOCKING` (`reconcile.py:24`) and flip the `rc == 0` in `test_dry_run_makes_no_writes`. Nothing else changes.

**Files:**
- Modify (A): `roles/storage_vm/files/homelab_storage/reconcile.py`, in `apply()` (:199-238) and the `BLOCKING` comment
  (:23).
- Test (A):
  - `scripts/tests/test_storage_plan.py`, in `PlanTest` next to `test_hold_create` (:89);
  - `scripts/tests/test_storage_reconcile.py`, in `GrowAndReportTest` next to
    `test_failed_run_keeps_old_success_timestamp` (:506), and `LockAndTargetctlTest.test_dry_run_makes_no_writes`
    (:647).

**Interfaces:**
- Consumes these, unchanged:
  - `plan.decide()`, with `Decision.fail` and `Refusal(id, 'hold-create')`;
  - `ledger.HOLD_CREATE` and `Cluster.holds()`;
  - `host.log()`, which writes to stderr (`host.py:14`); stdout carries the JSON report.
- Produces the stderr line `<D6:hold_line>`, on apply and on dry run. It appears only when VG `retained` is readable
  and tagged `hold_create`. The JSON report is unchanged.
- Consumers: the restore runbook (2.7) and the `storage.yml` workflow log (2.2).

- [ ] **Step 1: Pin the plan side.** This is a characterization test. It passes before the change, and `plan.py` does
  not change. In `PlanTest`:
  ```python
  def test_hold_create_fails_without_creates(self):
      d = run([vol('a', size=2 * GI)], vg([ledger.tag_created('a')], {'a': GI}), tags=[ledger.HOLD_CREATE])
      self.assertEqual(kinds(d), [('export', 'a')])  # the extend is held back
      self.assertEqual(refused(d), set())
      self.assertTrue(d.fail)
  ```
  Run: `cd $A && python3 scripts/tests/test_storage_plan.py`
  Expected: PASS.
  A run-level `Refusal` in `plan.py` is not the fix. It would break the exact `refused(d)` in `test_hold_create` and the
  exact `out['refusals']` in `test_failed_run_keeps_old_success_timestamp`.

- [ ] **Step 2: Write the failing reconcile tests.**
  - In `GrowAndReportTest`:
    ```python
    def test_hold_create_logs_reason_without_creates(self):
        self.fake(vgs={'retained': vg(['ledger:a:created', 'hold_create'], {'a': (GI, ())}), 'regen': vg()})
        rc, out = self.apply([entry('a')])
        self.assertEqual((rc, out['refusals']), (1, []))
        self.assertIn('hold_create set, 0 creates refused', self.err)
        self.fake(vgs={'retained': vg(['ledger:a:created'], {'a': (GI, ())}), 'regen': vg()})
        self.apply([entry('a')])
        self.assertNotIn('hold_create set', self.err)
    ```
  - In `test_failed_run_keeps_old_success_timestamp` (:506), add
    `self.assertIn('hold_create set, 1 creates refused', self.err)`.
  - In `test_dry_run_makes_no_writes` (:647), right after the dry-run `rc` assert, add
    `self.assertIn('hold_create set, 1 creates refused', self.err)`. Keep the dry run's `rc == 0` and its comment.

  Run: `python3 scripts/tests/test_storage_reconcile.py`
  Expected: FAIL. All three new `assertIn` lines fail with `'hold_create set, …' not found`.

- [ ] **Step 3: Implement.**
  - Add `_hold_line(d, cluster) -> str | None` to `reconcile.py`:
    - when `cluster is not None and HOLD_CREATE in cluster.holds()`, it returns
      `f'hold_create set, {n} creates refused'`, with `n = sum(r.reason == 'hold-create' for r in d.refusals)`;
    - otherwise it returns `None`.
  - `apply()` passes a non-`None` line to `host.log()` in both paths:
    - in the dry run, after the JSON `print` and before the `return`;
    - in the apply, before the `refused:` loop (:235).
  - The exit codes stay as they are.
  - Replace the comment at :23 with `# A dry run (before the maintenance lock) exits 1 only for these. hold_create and
    per-entry refusals do not block it (R6, D6); it logs the hold line instead.`

  Run: `python3 scripts/tests/test_storage_reconcile.py && python3 scripts/tests/test_storage_plan.py &&
  python3 scripts/tests/test_storage_expiry.py`
  Expected: PASS. `test_hold_create_skips` (`test_storage_expiry.py:69`) passes unchanged.

- [ ] **Step 4: Commit.**
  Run `g -C $A commit -am "fix(storage): log why a hold_create reconcile fails (lab F16)"`. The body is
  `Under hold_create an apply with no create to refuse exited 1 and logged nothing. Log "hold_create set, N creates
  refused" on apply and on dry run; the dry run still exits 0 (R6, D6).`, then the Co-Authored-By line.
  Save the three test logs to `$EVR/0.2/`.

### Task 0.3: Production guards for lab hooks (TDD)

`<D22:journal_scope>` = `storage VM and workers` (recommended, the D22 row). The journal task exists today only in
`roles/k3s_common/tasks/main.yml:199-206`, ungated, tested by `test_persistent_journal` (:81). `k3s_common` is a meta
dependency of `k3s_init`, `k3s_masters` and `k3s_workers`, so it runs on every k3s node. Nothing in `roles/storage_vm`
has one. So the recommendation is: gate the `k3s_common` task to the `workers` group (`inventory/proxmox.yml:17-18`),
give it a flush handler, and add the same task and handler to the storage VM. Check 11 at 300 s (5.5) reads a
worker's previous-boot journal; the masters do not need one. The other two answers are branches in Step 5.

**Files:**
- Modify (A):
  - `roles/storage_vm/tasks/assert.yml`: a new last task;
  - `roles/storage_vm/tasks/main.yml` and `roles/storage_vm/handlers/main.yml`, for D22;
  - `roles/k3s_common/tasks/main.yml:199-206` and `roles/k3s_common/handlers/main.yml`, for D22.
- Test (A): `scripts/tests/test_storage_vm_role.py` (`RoleTests`, including the handler list in
  `test_no_restart_of_target_or_nftables`, :167-168) and `scripts/tests/test_k3s_storage_settings.py`
  (`test_persistent_journal`, :81-83).

**Interfaces:**
- Consumes:
  - the lab guard's own test, word for word (`tasks/lab-guard.yml:12`):
    `'/lab-storage/' in (inventory_file | default(''))`;
  - the role default `storage_vm_timings.pause_after: []` (`roles/storage_vm/defaults/main.yml:31`).
- Produces:
  - the task "Refuse lab checkpoints outside the lab" in `assert.yml`. Both `main.yml` and `dry-run.yml` import
    `assert.yml` first (`test_asserts_come_first`), so `storage.yml` and its dry run refuse before `config.json` is
    written;
  - under `<D22:journal_scope>`, the task "Ensure the persistent journal directory exists" and the handler "Flush the
    journal to disk", in the storage VM role and, gated to `workers`, in `k3s_common`. They ship with A's branch
    (the 3.2 deploy). The 1.2 kubelet PR copies only A's `k3s_common` `:123-145`, so it carries no journal task.

- [ ] **Step 1: Write the failing `pause_after` test.** In `RoleTests`:
  ```python
  def test_pause_after_refused_outside_lab(self):
      t = next(t for t in role_tasks('assert') if 'pause_after' in json.dumps(t))
      self.assertNotIn('when', t)
      that = module(t, 'assert')['that']
      prod, lab = '/work/ansible/inventory/proxmox.yml', '/maintenance/lab-storage/inventory.yml'
      paused = dict(defaults()['storage_vm_timings'], pause_after=['reconcile:after-create'])
      self.assertTrue(holds(that, inventory_file=prod))
      self.assertFalse(holds(that, inventory_file=prod, storage_vm_timings=paused))
      self.assertFalse(holds(that, storage_vm_timings=paused))  # no inventory_file is not the lab
      self.assertTrue(holds(that, inventory_file=lab, storage_vm_timings=paused))
  ```
  The checkpoint name is only an example: any non-empty list is refused.
  Run: `cd $A && $VPY15 scripts/tests/test_storage_vm_role.py RoleTests.test_pause_after_refused_outside_lab`
  Expected: FAIL (`StopIteration`: there is no such task yet).

- [ ] **Step 2: Implement.** Add this task to the end of `assert.yml`, after "Refuse stock LVM activation". It must not
  go first, because `test_empty_ssh_sources_fails` reads `role_tasks('assert')[0]` by position.
  ```yaml
  # pause_after SIGSTOPs reconcile or the fencer at a checkpoint (lab only); a stopped fencer fences nothing.
  - name: Refuse lab checkpoints outside the lab
    ansible.builtin.assert:
      that:
        - >-
          (storage_vm_timings.pause_after | default([]) | length == 0)
          or ('/lab-storage/' in (inventory_file | default('')))
      fail_msg: storage_vm_timings.pause_after is lab-only (ADR 0017); production never sets it.
  ```
  Run: the whole `test_storage_vm_role.py`. Expected: PASS.
  Commit: `g -C $A commit -am "fix(storage): refuse pause_after outside the lab inventory"`.

- [ ] **Step 3: D22: write the failing tests** (`storage VM and workers`; Step 5 for the other answers).
  - In `test_k3s_storage_settings.py`, replace `test_persistent_journal` (:81-83) with
    `test_persistent_journal_on_workers_only`. It asserts:
    - `find(common_tasks(), "ansible.builtin.file", path="/var/log/journal")` has `state: directory`,
      `owner: root`, `group: systemd-journal`, `mode: "2755"`;
    - its `when` is `"'workers' in group_names"`, the style of the `'masters' in group_names` gate at :120;
    - its `notify` is `Flush the journal to disk`;
    - the handler of that name in `roles/k3s_common/handlers/main.yml` has `ansible.builtin.command`
      `argv: [journalctl, --flush]` and `changed_when: true`.
  - In `RoleTests`, add `test_persistent_journal_on_storage_vm`. It asserts:
    - `by_name(role_tasks(), 'Ensure the persistent journal directory exists')` has `ansible.builtin.file` ==
      `{path: /var/log/journal, state: directory, owner: root, group: systemd-journal, mode: '2755'}`;
    - its `notify` is `Flush the journal to disk`;
    - the handler of that name in `handlers/main.yml` has `ansible.builtin.command` `argv: [journalctl, --flush]` and
      `changed_when: true`.
  - In `test_no_restart_of_target_or_nftables` (:168), append `'Flush the journal to disk'` to the expected handler
    names. The handler goes last in `handlers/main.yml`, so the `handlers[1]` and `handlers[2]` checks keep their
    indexes.

    A handler, not a `when: … is changed` task, keeps ansible-lint's `no-handler` rule quiet (`.ansible-lint`
    `profile: production`). On the storage VM, handlers run at "Apply unit and ruleset changes before the reconcile",
    the `meta: flush_handlers` at `main.yml:155`. `k3s_common` has no `flush_handlers`, so on the workers the flush
    runs at the end of the `k3s.yml` "Join workers" play (:96), beside "Restart k3s". Without the flush, journald keeps
    logging to `/run` until the next boot (LA:115), and the boot before Gate F2 (storage VM) or the first worker
    reboot after the deploy would be lost.

  Run: `$VPY15 scripts/tests/test_k3s_storage_settings.py; $VPY15 scripts/tests/test_storage_vm_role.py`
  Expected: FAIL in both files.

- [ ] **Step 4: D22: implement** (`storage VM and workers`).
  - In `roles/k3s_common/tasks/main.yml:199-206`, keep the task. Add `when: "'workers' in group_names"` and
    `notify: Flush the journal to disk`, and change the comment to `# Persistent journal, workers only: Check 11
    reads a worker's previous-boot log (D22).`
  - Append the "Flush the journal to disk" handler to `roles/k3s_common/handlers/main.yml`, after "Restart k3s".
  - In `roles/storage_vm/tasks/main.yml`, add the directory task after "Create the storage directories" (:43-55), with
    `notify: Flush the journal to disk` and the comment `# Persistent journal: the boot check and the Gate F2 reboot
    read the previous boot's log.`
  - Append the handler to `roles/storage_vm/handlers/main.yml`, after "Restart storage-fencer".

  Run: both test files, then the Task 0.1 Step 13 block. Expected: PASS.
  Commit: `g -C $A commit -am "fix(storage): persistent journal on the storage VM and workers only (D22)"`.

  Nothing is undone live: the branch was never deployed, so no master has the directory from it. Whether Debian 13's
  systemd already ships `/var/log/journal` is UNVERIFIED. The task is idempotent either way, and the gate only stops
  the role creating it on the masters; it does not remove one the image ships.

- [ ] **Step 5: D22 branches.** Record the answer Ben gave, and the branch taken, in `$EVR/0.3/d22.txt`.
  - `storage VM and workers` (recommended): Steps 3 and 4 as written.
  - `storage VM only`: in Step 3, replace `test_persistent_journal` with `test_no_persistent_journal_on_k3s_nodes`
    (no `ansible.builtin.file` task in `common_tasks()` has `path: /var/log/journal`) and drop the `k3s_common`
    handler assertion; keep the `RoleTests` changes. In Step 4, delete `roles/k3s_common/tasks/main.yml:199-206`, the
    comment and the task, and add no `k3s_common` handler. Commit subject: `fix(storage): keep the persistent
    journal on the storage VM only (D22)`. Then the worker's previous-boot journal is gone, so 5.5 Step 2's Check 11
    ordering evidence must come from elsewhere (VolumeAttachment and event times against the node's NotReady time,
    plus the storage VM's session-logout times from `SVM journalctl`). Write that into `d22.txt` for 5.5.
  - `every node`: Steps 3 and 4 as written, except the `k3s_common` task gets no `when`. The test is named
    `test_persistent_journal_on_every_node` and asserts `'when' not in task` instead of the workers gate; the
    notify and handler assertions stay. Commit subject: `fix(storage): persistent journal on every node (D22)`.

### Task 0.4: Doc corrections

**Files:**
- Rebase (D): `apps-adr-0017`, branch `docs/adr-0014-retained-storage-vm`, tip `654c825d`, 134 behind `origin/main`. It
  conflicts in `docs/adr/README.md`.
- Modify (D): `docs/adr/0017-retained-block-storage-vm-iscsi.md`. The lines cited below are as at `654c825d`; the
  rebase does not touch this file.

**Interfaces:**
- Consumes Ben's answers on `<D16:storage_template_pin>`, `<D17:dump_rule_at>`, `<D20:margin_gib>` and
  `<D3:nic_path>`, and on D30 only if he waives the redis dump. It also consumes the runbook names that the outline
  pins (apps `docs/runbooks/storage-vm-*.md`).
- Produces an ADR whose text matches the plan, so the plan header's "the ADR wins" rule has nothing to override. These
  tasks cite the corrected lines: 2.1 (D16), 2.7 (the runbook name), 2.8 (D17), 4.0 and 4.T (D20), 3.3 (D3) and
  5.5 (row 10, fencing stays held).
- Merge event: apps `main`, docs only, so nothing syncs. apps needs no `[skip ci]`.

- [ ] **Step 1: Rebase D.**
  Run:
  ```sh
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; mkdir -p $EVR/0.4
  git -C $D fetch origin && git -C $D branch backup/adr-0017-pre-rebase-20261121 && g -C $D rebase origin/main
  ```
  At the `docs/adr/README.md` conflict, keep main's table and insert the branch's `| 0017 | … | Accepted |` row
  (branch line 32) between main's `0016` and `0018` rows. Then
  `git -C $D add docs/adr/README.md && g -C $D rebase --continue`.
  Expected:
  - 8 commits on `origin/main`;
  - `git -C $D diff --stat origin/main HEAD` touches only `docs/adr/0017-*.md`, `docs/adr/README.md` and
    `docs/superpowers/**`.

  The plan header's `654c825d` is now the pre-rebase SHA. Write the new SHA of "record Ben's ADR 0017 decisions and
  production gates" to `$EVR/0.4/heads.txt`, and use it in the header.

- [ ] **Step 2: Show Ben the edits and get his OK on each.** Write each edit, with its exact old and new text, to
  `$EVR/0.4/adr-edits.md`. Apply only the rows he approves. Rows 6 and 7 apply only if `<D3:nic_path>` = `fold`.
  Each row gives its gate, the old text and the new text:
  1. **Stale citation** (:671). Old: ``as in ansible `docs/backup-and-restore.md:168-189`.``
     New: ``as in ansible `docs/backup-and-restore.md`, **One image from the replica**, step 3.``
     That block is now at :203-213. A section name does not go stale the way a line number does.
  2. **Stale citation** (:949). Old: `(ansible runbook :375-377)`.
     New: ``(ansible `docs/backup-and-restore.md`, **Restore drill**)``. The drill is now at :524-530.
  3. **`<D16:storage_template_pin>` = `manifest`** (Ben, 2026-11-23). **Applied 2026-11-23:** D `60075cbf`. :74 stays: it already says the pin comes from
     the storage entry of `packer-manifest.json`, selected by `builds[].name`. Two lines change:
     - (:203-204) Old: ``The storage VM pins its template on its own variable.``
       New: ``The storage root reads the `storage` entry the same way: CI passes its `artifact_id` and
       `custom_data.vm_name` to the root as variables, and the clone check refuses a template at that VMID with another
       name (Ben, D16).``
     - (:198-199) Old: ``It publishes the storage entry in its own job, so a failed k3s build (for example the
       kernel-series check) does not block it.``
       New: ``One manifest PR carries the entry of every build that succeeded, so a failed k3s build (for example the
       kernel-series check) does not block the storage entry (D16).``
     - (:200) Old: ``It takes the release tag and terraform PR title from the k3s entry, and fails if that entry is
       missing.``
       New: ``It takes the release tag from the k3s entry, and fails if that entry is missing; the terraform PR title
       names every template it updates (D16).``
  4. **`<D17:dump_rule_at>` = `first retained cutover`** (:662). Old: `It is added at the first cutover, not before,
     because the`. The new text depends on where D14's karakeep pair runs (D17):
     - D17 default (ADR order, pair in wave 1, slot 4): ``It is added at the first `retained` cutover (karakeep-data,
       in the wave-1 karakeep outage, D14), not before, because the``;
     - D17 alternative (pair first in wave 2): ``It is added at the first `retained` cutover (karakeep-data, first in
       wave 2 in the karakeep outage, D14; the four wave-1 cutovers before it are `regen`), not before, because the``.
  5. **`<D20:margin_gib>` = `10`** (:715-719, the whole "Per-cutover gate" bullet). **Applied 2026-11-23** with Ben's
     pre-approved switch to allocated size after tempo added: D `1705df34`.
     New: ``**Per-cutover gate.** Before each copy, `zfs get available,usedbysnapshots apps/k3s-block` must show
     `available` of at least the source's full length plus 10 GiB, and `usbbk` must have matching space. The copy
     writes the full length (no `conv=sparse`), so each LV may allocate all of it unless zero blocks end up as holes
     (ZFS compression on `apps/k3s-block`, or Proxmox `detect_zeroes` with `discard=on`; neither measured). The gate
     stays at the full length until the dataset's measured `used` change over the first cutover (tempo) shows that
     zeros become holes (Ben, D20).``
  6. **`<D3:nic_path>` = `fold`** (:213). Old: `Adding a NIC restarts that VM, so the workers get theirs one per PR,
     each drained by hand first.`
     New: ``The workers get theirs in the Foundation full rebuild, as a `storage_nic` commit on the first k3s manifest
     PR, so no in-place worker update strips `wwn=` from Proxmox CSI disks (Ben, D3).``
  7. **`<D3:nic_path>` = `fold`** (:954-955, :959 and :1020).
     - Swap Foundation items 1 and 2, so the bridge PR comes before the three-image layout.
     - :959 becomes `4. The worker NICs, folded into the three-image rebuild (D3).`
     - In :1020, `rolled out one worker per PR` becomes `added to the workers in the Foundation rebuild`.
  8. **Pinned runbook name** (:664). Old: `` `docs/runbooks/retained-storage-restore.md` ``.
     New: `` `docs/runbooks/storage-vm-restore.md` ``, the name the outline pins.
  9. **D30 = waiver (b) only** (:995-997, wave 6). **Applied 2026-11-23** (Ben chose (b)): D `a922fcd6`. Not offered under D30's recommendation (a). If Ben waives the
     fresh redis dump (4.W wave 6, option (b)), write a row whose new text names redis as the exception to "a fresh
     dump confirmed off-site before each cutover", in Ben's words, before the redis inventory PR. That row goes
     through Steps 3-5 like the others, even if the rest of 0.4 is already committed.
  10. **Automatic fencing stays off after Retirement** (Ben, 2026-11-21; D13, D28 and D33 deferred). Old texts are at
      `654c825d`, quoted unwrapped; the ADR's wrapping differs.
      - Migration 4, Retirement (:1007-1012, two bullets). Old: ``- Once no Proxmox CSI VolumeAttachment remains,
        remove `hold_fence` from `retained`. That switches automatic fencing on.`` and ``- **Gate R1 (production
        timings):** right after that, one planned fence drill: `qm suspend` a worker, see the fence, the taint and the
        move at the 300 s threshold (about 7 minutes from the hang), then resume it and see it stay fenced until its
        reboot. The first planned reboot of an unfenced worker with volumes staged, after R1, covers Check 11 at 300
        s.``
        New: ``- Automatic fencing stays off after Retirement: `hold_fence` stays on `retained`, the fencer keeps
        refusing, and the manual fence stays the only fence (Ben, 2026-11-21). Turning it on, with Gate R1 (a planned
        `qm suspend` fence drill at the 300 s threshold), is a later decision.`` and ``- Check 11 at 300 s runs at the
        first planned worker reboot after Retirement, with fencing held.``
      - Consequences, Easier (:783-784). Old: ``This starts at Retirement, when `hold_fence` is removed.``
        New: ``This starts when automatic fencing is turned on, a later decision: `hold_fence` stays on `retained`
        after Retirement (Ben, 2026-11-21).``
      - Qualification, Not proven there (:844-845). Old: `the production timings: the fencer ran at a 60 s threshold,
        not 300 s, and Check 11 was not re-run at 300 s: Retirement gate R1 and the first planned worker reboot;`
        New: `the production timings: the fencer ran at a 60 s threshold, not 300 s, and Check 11 was not re-run at
        300 s: Check 11 at the first planned worker reboot after Retirement; the fence at 300 s waits for Gate R1,
        which comes with the later decision to turn automatic fencing on;`
      - Accepted untested, F18 (:853). Old: `first seen at the first host reboot after Retirement;`
        New: `first seen at the first host reboot after automatic fencing is turned on (a later decision);`
      - Qualification gate status (:862). Old: `(F1 and F2 before the first cutover, C1 before the Servarr apps, R1 at
        Retirement);` New: `(F1 and F2 before the first cutover, C1 before the Servarr apps; R1 waits for the later
        automatic-fencing decision);`
      - Migration 1 (:951-952). Old: `Its gaps close in production through gates F1, F2, C1 and R1 below (Ben,
        2026-11-21).` New: `Its gaps close in production through gates F1, F2 and C1 below (Ben, 2026-11-21); Gate R1
        waits for the later decision to turn automatic fencing on.`
      - Migration 2.3, Foundation (:957-958; not in Ben's list, added because it implies fencing turns on at
        Retirement). Old: `fencing stays off while Proxmox CSI disks remain attached to the workers. Until Retirement,
        the manual fence is the only fence.` New: `fencing stays off while Proxmox CSI disks remain attached to the
        workers, and after Retirement too (Ben, 2026-11-21). The manual fence is the only fence until a later decision
        turns automatic fencing on.`
      - Fence condition 6 (:438-439; not in Ben's list, added because it calls the hold a migration-only pause).
        Old: `` `hold_fence` is the manual pause for runbooks and the migration. ``
        New: `` `hold_fence` is the manual pause for runbooks and the migration, and it stays set after Retirement
        until a later decision turns automatic fencing on (Ben, 2026-11-21). ``
      - Checks 1 and 11 (:864-870, :931-935) do not name R1, so they need no edit.

  Expected: Ben approves or rewords each row. A declined row is marked declined in `adr-edits.md`, and that row's plan
  task follows the ADR text as it stands.

- [ ] **Step 3: Apply the approved rows.** Use exact string edits, not line numbers, because each edit shifts the lines
  after it. Wrap at 120 columns, as the ADR does.
  Run: `git -C $D diff --stat; git -C $D diff > $EVR/0.4/adr.diff`
  Expected: only `docs/adr/0017-retained-block-storage-vm-iscsi.md` changes.

- [ ] **Step 4: Check the text.**
  Run:
  ```sh
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; EV=$EVR/0.4
  tr '\n' ' ' < $D/docs/adr/0017-retained-block-storage-vm-iscsi.md | tr -s ' ' > $EV/adr-flat.txt  # undo wraps
  grep -o -e ':168-189' -e ':375-377' -e 'retained-storage-restore' -e 'pins its template on its own variable' \
    -e 'in its own job' $EV/adr-flat.txt
  grep -o -e 'refuses a template at that VMID with another name' -e 'first `retained` cutover' \
    -e 'full length plus 10 GiB' $EV/adr-flat.txt
  ```
  Expected:
  - the first grep prints nothing;
  - the second prints one match each for rows 3, 4 and 5, if Ben approved them;
  - with the D3 fold, `grep -o -e 'one per PR' -e 'one worker per PR' $EV/adr-flat.txt` prints nothing;
  - with row 10, `` grep -o -e 'when `hold_fence` is removed' -e 'Retirement gate R1' -e 'R1 at Retirement'
    -e 'C1 and R1 below' -e 'That switches automatic fencing on' -e 'Until Retirement, the manual fence'
    -e 'host reboot after Retirement;' $EV/adr-flat.txt `` prints nothing, and
    `grep -c 'Automatic fencing stays off after Retirement' $EV/adr-flat.txt` prints `1`.

  The ADR has no test suite, so these greps are the check.

- [ ] **Step 5: Commit.**
  Run `g -C $D commit -am "docs(storage): correct ADR 0017 citations and record Ben's migration decisions"`. The body
  lists the applied rows, their D-ids and the date of Ben's OK, then the Co-Authored-By line. Nothing is pushed. The
  plan file goes on D in its own commit, made by whoever assembles the parts.

---

## Part 1: prerequisites (live; ADR Migration 0)

ADR Migration 0 asks for three things before any Foundation work: the kubelet graceful shutdown ships on its own,
Jellyfin gets a guard, and `pve-backup` has been green for 7 days with pstore empty. This part also lands the wwn guard,
because the Global Constraints ("wwn") rely on it from here until Retirement. D19 (filebrowser guard: yes) is folded
into Task 1.3.

**How live reads run in this part.**
- Reads go through the helper `/opt/azure-cli/bin/python3 -I ~/.cache/claude-homelab-live/bin/live.py <rows.json>`.
  Each row is `["pve" | "tn", "<bash command>", <timeout s>]`: `pve` runs over SSH as root, and `tn` runs on TrueNAS
  (VM 100) through QGA (`live.py:1-2,13-18`). Commands are ASCII only; the helper asserts it (`live.py:14`). On `tn`,
  use literal paths and no shell variables (memory `backup-review-live-access`, 2026-11-15 pitfall).
- `kubectl` has no helper host. It runs as `qm guest exec <master vmid> -- k3s kubectl ...` in a `pve` row, on the first
  VM whose Proxmox tags hold `k3s` and `master`. Find that VM with
  `pvesh get /cluster/resources --type vm --output-format json`; never hardcode a VMID or node name (memory
  `backup-review-live-access`: the runner user has no kubectl). This is the Global Constraints rule (Live work).
  Below, `KUBE <args>` is short for that row.
- `gh` reads run on the workstation and print names and metadata only.
- Each task writes its rows file, the scrubbed raw output and a short `facts.md` to `evidence/<task>/`.
- A read-only check needs one Ben OK per session. Every mutation and every merge below is marked **Ben OK**.

**Order.** 1.1 comes first. 1.2, 1.3 and 1.4 then run one at a time. Two reasons:
- the 1.2 deploy and the 1.4 apply both take the maintenance lock (`maintenance_apply.py:24`; ansible `deploy.yml`
  "Acquire external maintenance ownership");
- apps controller merges must not land during a deploy (memory `pr-merge-mechanics`).

No merge lands inside a backup window (Global Constraints).

### Task 1.1: Read-only pre-check session

**Files:**
- Create (evidence only, no repo): `evidence/1.1/rows.json`, `evidence/1.1/out.txt`, `evidence/1.1/facts.md`

**Interfaces:**
- Consumes: D1 candidates `<D1:storage_vmid>` and `<D1:placeholder_vmid>`, if Ben has named them. Otherwise this task
  records the free IDs he can pick from.
- Produces, in `facts.md`:
  - the backup and pstore state (gate for Part 3);
  - `quota_gib`, `refquota_gib`, `available_gib`, `used_gib`, `usedbysnapshots_gib` and the pve mount size
    (input to D2);
  - `k3s_block_mount_path`, the `findmnt` target of the `k3s-block` mount (input to 2.4
    `roles/storage_vm/tasks/host-metrics.yml`);
  - `retired_images_present` (a list; input to Task 4.0);
  - the free VMIDs, and the packer and terraform ACL facts (inputs to 2.1 and 3.3);
  - `org_dispatch_visibility` (input to 2.4);
  - `argocd_version` (input to 4.0, syncWindow form);
  - `proxmox_csi_driver`: the CSIDriver fields and the controller and node image tags (input to 2.5, m7);
  - `k3s_version`, the kubelet version per node (input to 2.5, VolumeAttachment naming);
  - `pve_mem_available_gib`;
  - `runner_lan_ip`, VM300's LAN IPv4 (input to 2.3 `storage_vm_ssh_sources`).

- [ ] **Step 1: Ask Ben for the session's read-only OK.** Show him the rows file from Step 2 first.
  Expected: Ben OK for read-only use of the helper in this session.
- [ ] **Step 2: Write `evidence/1.1/rows.json`.** The rows:
  - Backup and pstore (`pve`):
    - `journalctl -u homelab-backup@backup.service --since -8d --no-pager | grep -E 'PROBLEM|Added to the repository'`
    - `systemctl list-timers 'homelab-backup-*' --no-pager`
    - `ls -A /var/lib/systemd/pstore`

    The unit, timers and pstore path come from ansible `docs/backup-and-restore.md:44-46,88,113-115`.
  - Quota (`tn`):
    - `zfs get -Hp quota,refquota,available,used,usedbysnapshots,usedbydataset apps/k3s-block`

    The `refquota` and `usedby*` columns are what can explain a 219 GiB mount under a 288 GiB quota (ADR :817;
    proxmox-csi `README.md:21-22` on apps main).
  - Mount size (`pve`):
    - `pvesm status --storage k3s-block`
    - `d=$(dirname "$(pvesm path k3s-block:9999/vm-9999-jellyfin.raw)");
      findmnt -no TARGET,SIZE,AVAIL -T "$d"; df -B1 "$d"` (one row)

    pve shell variables are fine; the variable rule is for TrueNAS only. Do not assume the mount path.
  - Images (`pve`):
    - `pvesm list k3s-block --vmid 9999`

    Compare against the 10 retired names `vm-9999-{grafana,prowlarr,bazarr,seerr,seerr-ru,cineplete,cleanuparr,ntfy,
    pgadmin,changedetection-data}.raw` (proxmox-csi `README.md:63-64`).
  - VMIDs (`pve`):
    - `qm status 901; qm status 902`
    - `qm status <D1:storage_vmid>`, `qm status <D1:placeholder_vmid>`, and
      `pvesm list k3s-block --vmid <D1:placeholder_vmid>` (an orphan image can exist with no VM)
  - ACLs (`pve`):
    - `pveum user list --output-format json |
      python3 -c 'import json,sys; [print(u["userid"]) for u in json.load(sys.stdin)]'` (one row)
    - `pveum acl list --output-format json`

    Paths, roles and user ids only. `pveum` never prints token secrets.
  - Per-user permissions (`pve`), for the packer user `<packer_user>` and the terraform user `<terraform_user>` that Ben
    names from the list above:
    - `pveum user permissions <packer_user> --path /vms/901`, and the same for `/vms/902`
    - `pveum user permissions <terraform_user> --path /vms/<D1:storage_vmid>`, and the same for `/vms/902`,
      `/storage/k3s-block` and `/storage/local-zfs`
    - `pveum user token list <packer_user> --output-format json` and the same for `<terraform_user>`: token ids and
      the `privsep` flag only
    - for each privsep token: `pveum user token permissions <user> <tokenid> --path <same paths>`. A privilege-separated
      token has only its own ACLs, not its user's. The exact `token permissions` subcommand form is UNVERIFIED here;
      if it is refused, read the token's rows from `pveum acl list` instead.
  - Argo CD and the CSI driver (`pve`):
    - `KUBE -n argocd get deploy argocd-server -o jsonpath='{.spec.template.spec.containers[0].image}'`
    - `KUBE get csidriver csi.proxmox.sinextra.dev -o yaml`
    - `KUBE get deploy,ds -A -o
      jsonpath='{range .items[*]}{.metadata.name}{" "}{.spec.template.spec.containers[*].image}{"\n"}{end}'` (one row),
      filtered for `proxmox`: the controller Deployment and the node DaemonSet (namespace `csi-proxmox`, apps
      `infrastructure/system/proxmox-csi/app.yaml:2`)
    - `KUBE get nodes -o
      jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.nodeInfo.kubeletVersion}{"\n"}{end}'` (one row)
  - Runner (`pve`):
    - `qm guest cmd 300 network-get-interfaces`

    Keep the non-loopback IPv4 addresses only. If the agent does not answer, record `runner_lan_ip` UNVERIFIED; Task
    2.3 then stops rather than guess it.
  - Memory (`pve`):
    - `grep -E 'MemTotal|MemAvailable' /proc/meminfo`
    - `awk '$1=="size"||$1=="c_max"{print $1,$3}' /proc/spl/kstat/zfs/arcstats`
    - `pvesh get /nodes/pve/qemu/300/status/current --output-format json`

    Read the `mem` and `maxmem` fields of the last one.
- [ ] **Step 3: Run the rows.**
  - Run: `/opt/azure-cli/bin/python3 -I ~/.cache/claude-homelab-live/bin/live.py evidence/1.1/rows.json
    > evidence/1.1/out.txt` (one line)
  - Expected, per row:
    - backups: at least 7 `Added to the repository` lines on distinct days and no `PROBLEM` line; the backup timer next
      at 04:30;
    - pstore: empty output;
    - `zfs get`: numeric values, recorded as-is;
    - `pvesm list`: the 33 live images present (cross-check with scout-volumes "Inventory"), plus any of the 10 retired
      ones, recorded by name and size;
    - `qm status 901`/`902`/D1 IDs: `does not exist` each, and no image under the placeholder;
    - the argocd-server image tag;
    - `findmnt`: the mount target, recorded as `k3s_block_mount_path` (Task 2.4 assumes `/mnt/pve/k3s-block`);
    - the CSIDriver with `attachRequired`, `volumeLifecycleModes` and `fsGroupPolicy`, and the controller and node
      image tags. Anything other than v0.22.x with `Persistent` mode is a stop for Ben (Task 2.5, m7);
    - every node reports the same kubelet version, expected `v1.37.2+k3s1` (ansible `group_vars/all/vars.yml:23` on
      main);
    - one LAN IPv4 for VM300 inside `10.9.9.0/24`, recorded as `runner_lan_ip`; an address outside it is recorded
      as-is, and Task 2.3 adds it to `storage_vm_ssh_sources`;
    - MemAvailable is at least 5 GiB, read while VM300 holds its full 4096 MiB. That is a 2 GiB storage guest plus the
      lab plan's 3 GiB margin (lab plan B1 Step 1).

  The run stops on its own if a command is not ASCII.
- [ ] **Step 4: Read the GitHub metadata on the workstation** (names only, never values):
  - Run: `gh secret list --repo Starktastic-Homelab/terraform` and `gh secret list --org Starktastic-Homelab`
  - Run: `gh api orgs/Starktastic-Homelab/actions/secrets/ORG_DISPATCH_TOKEN --jq .visibility`; if it is `selected`,
    also run `gh api orgs/Starktastic-Homelab/actions/secrets/ORG_DISPATCH_TOKEN/repositories
    --jq '.repositories[].name'` (one line)
  - Expected:
    - the terraform list shows `PM_API_URL`, `PM_API_TOKEN_ID`, `PM_API_TOKEN_SECRET`, `S3_ACCESS_KEY`,
      `S3_SECRET_KEY`, `S3_ENDPOINT` and `S3_TF_PLAN_BUCKET` (`apply.yml:111-116,148-152`);
    - `ORG_DISPATCH_TOKEN` is `all`, or `selected` with `apps` listed. If `apps` is not listed, Task 2.4 waits for Ben
      to grant it or uses the hourly schedule only.

    If `gh` lacks `admin:org` scope, the org reads fail. Record that and ask Ben to read the setting.
- [ ] **Step 5: Write `evidence/1.1/facts.md`.** One line per produced fact, each with its source row.
  - Flag each failed expectation as a stop for the task it blocks: backup or pstore blocks Part 3; a taken VMID
    blocks 3.3 and 3.4; the packer rights block 3.3; an UNVERIFIED `runner_lan_ip` blocks 2.3.
  - **Packer rights.** Per-VMID grants on `/vms/901` or `/vms/902` alone do not survive `packer build -force`, because
    a destroy drops them (memory `pve-destroy-drops-vm-acl`). The packer user needs its rights from `/vms` or from a
    pool path.
  - Hand the quota numbers to Ben for D2.
  - Expected: `facts.md` answers each item in the task index list. Anything not answered is marked UNVERIFIED, with
    the reason.

### Task 1.2: Kubelet graceful shutdown PR (ansible)

**Files** (new worktree `~/.cache/claude-homelab-live/worktrees/ansible-kubelet-shutdown`, branch
`feat/kubelet-graceful-shutdown` from ansible `origin/main`, not from A):
- Modify: `roles/k3s_common/tasks/main.yml`
- Create: `scripts/tests/test_k3s_storage_settings.py`
- Modify: `.github/workflows/validate.yml`

**Interfaces:**
- Consumes: A HEAD `roles/k3s_common/tasks/main.yml:123-145`, the two drop-in tasks at 90s/40s from the F14 fix
  `ce72f98`. Do not use `bd761c3`, whose values are 60s/10s.
- Produces: `/var/lib/rancher/k3s/agent/etc/kubelet.conf.d/50-graceful-shutdown.conf` on every k3s node. The kubelet
  then writes `/etc/systemd/logind.conf.d/99-kubelet.conf` itself (ADR Check 11 text, ADR :932-935).
- Produces: the test `StorageSettingsTests.test_kubelet_dropin`. A's file adds the iSCSI, kube-controller-manager,
  fstrim and multipath tests at the next rebase.

- [ ] **Step 1: Create the worktree.**
  - Run: `git -C ~/.cache/claude-homelab-live/worktrees/ansible-storage-vm worktree add
    ~/.cache/claude-homelab-live/worktrees/ansible-kubelet-shutdown -b feat/kubelet-graceful-shutdown origin/main`
  - Expected: a clean tree at ansible `origin/main`, which at the 11-21 read was `71b0d70`.
- [ ] **Step 2: Write the failing test.**
  - Create `scripts/tests/test_k3s_storage_settings.py` from A HEAD's file, keeping only:
    - the module docstring;
    - the helpers `read`, `common_tasks` and `find`, with the `DataLoader` import only (drop the `Templar` import);
    - `test_kubelet_dropin`.

    Drop the other tests (`test_iqn_written_before_install`, `test_iscsid_socket_and_manual_startup`,
    `test_kcm_flag_masters_only`, `test_fstrim_timer_enabled`, `test_no_multipath` and the rest). They test code that is
    not on main and would fail here.
  - The test, as short code:

    ```python
    def test_kubelet_dropin(self):
        _, task = find(common_tasks(), "ansible.builtin.copy",
                       dest="/var/lib/rancher/k3s/agent/etc/kubelet.conf.d/50-graceful-shutdown.conf")
        lines = task["ansible.builtin.copy"]["content"].splitlines()
        for line in ("apiVersion: kubelet.config.k8s.io/v1beta1", "kind: KubeletConfiguration",
                     "shutdownGracePeriod: 90s", "shutdownGracePeriodCriticalPods: 40s"):
            self.assertIn(line, lines)
        config = next(t for t in common_tasks() if t["name"] == "Write the K3s node config")
        self.assertNotIn("shutdownGracePeriod", config["ansible.builtin.copy"]["content"])  # not a kubelet-arg
    ```

  - Add the CI step after "Test Proxmox CSI bootstrap rendering" (`validate.yml:42-43` on main), exactly as `bd761c3`
    added it:

    ```yaml
          - name: Test K3s storage settings
            run: python3 scripts/tests/test_k3s_storage_settings.py
    ```

  - Run: `~/.cache/claude-homelab-live/venv/bin/python -B scripts/tests/test_k3s_storage_settings.py`
  - Expected: FAIL with `AssertionError: no ansible.builtin.copy task with {'dest':
    '/var/lib/rancher/k3s/agent/etc/kubelet.conf.d/50-graceful-shutdown.conf'}`.
- [ ] **Step 3: Add the two tasks.**
  - Copy A HEAD `roles/k3s_common/tasks/main.yml:123-145` verbatim: the comment, "Ensure the kubelet config drop-in
    directory exists", the F14 comment, and "Configure kubelet graceful node shutdown" with
    `shutdownGracePeriod: 90s`, `shutdownGracePeriodCriticalPods: 40s`, mode `0644` and `notify: Restart k3s`.
  - Insert them after "Configure K3s internal leader election" (main `:110-121`) and before "Check if K3s is already
    installed" (main `:123`), as on A.
  - Run: `diff <(git -C ~/.cache/claude-homelab-live/worktrees/ansible-storage-vm show
    HEAD:roles/k3s_common/tasks/main.yml | sed -n 123,145p) <(sed -n 123,145p roles/k3s_common/tasks/main.yml)`
  - Expected: no output.
  - Run: `git diff feat/kubelet-graceful-shutdown feat/retained-storage-vm -- roles/k3s_common/tasks/main.yml` (both
    branches are in the same repository, so the new worktree sees A's branch)
  - Expected: only A's storage hunks remain (the `/etc/iscsi` tasks, `open-iscsi`, `iscsid.socket`, `fstrim.timer`,
    `k3s_common_kube_controller_manager_args`, and the persistent journal task, gated to workers by Task 0.3 under
    `<D22:journal_scope>`). There is no difference in the drop-in tasks. This PR carries no journal task: main has
    none, and it reaches main with the Task 3.2 PR.
- [ ] **Step 4: Run to PASS, then lint.**
  - Run: `~/.cache/claude-homelab-live/venv/bin/python -B scripts/tests/test_k3s_storage_settings.py`
  - Expected: `Ran 1 test ... OK`. This test passed on A HEAD on 2026-11-21.
  - Run: `~/.cache/claude-homelab-live/venv/bin/ansible-lint roles/k3s_common`
  - Expected: no new findings. The workstation venv has ansible-core 2.21.6; CI runs ansible 15.0.0 (#347), so the PR's
    "Ansible Lint" and "Ansible Syntax Check" are the authority.
- [ ] **Step 5: Commit.**
  - Message: `feat(k3s): add kubelet graceful node shutdown drop-in (90s/40s, ADR 0017 F14)`
  - Files: the three above, and no `CLAUDE.md` or `README.md`. `CLAUDE.md` is not in `deploy.yml` `paths-ignore`, so
    keep docs out of this deploying PR (memory `pr-merge-mechanics`).
  - This is not docs-only, so it gets no `[skip ci]`.
- [ ] **Step 6: Pre-merge read** (read-only, session OK).
  - Rows:
    - `KUBE get --raw /api/v1/nodes/<node>/proxy/configz` for each `KUBE get nodes -o name`, keeping only the
      `shutdownGracePeriod*` fields;
    - `qm config <vmid> | grep -E '^(name|startup|tags)'` for each `k3s`-tagged VM.
  - Expected:
    - the baseline is `shutdownGracePeriod` `0s` (unset) on every node;
    - no k3s VM has a `startup` `down=` below 90. terraform ignores `startup_shutdown` on these VMs (proxmox guest
      startup comment, ansible `group_vars/proxmox_hosts/guest_startup.yml:6`). PVE's default stop timeout on host
      shutdown is UNVERIFIED; a `down=` under 90 s would cut the new grace period short, so it is a stop for Ben.
  - Evidence: `evidence/1.2/before.txt`.
- [ ] **Step 7: Push, open the PR and merge** (Ben asks; **Ben OK** at the merge).
  - Pre-checks:
    - no `deploy.yml` or terraform `apply.yml` run is in progress
      (`gh run list --repo Starktastic-Homelab/ansible --workflow deploy.yml -L 3`, and the same for terraform
      `apply.yml`);
    - the maintenance lock is free;
    - outside every backup window;
    - apps merges are held until Step 9 passes.
  - Run: `git push -u origin feat/kubelet-graceful-shutdown`, then `gh pr create --repo Starktastic-Homelab/ansible
    --base main --head feat/kubelet-graceful-shutdown --title "feat(k3s): add kubelet graceful node shutdown drop-in
    (90s/40s, ADR 0017 F14)"`. The body says what the deploy does (below) and ends with the Claude Code line.
  - When "Ansible Lint" and "Ansible Syntax Check" are green, run
    `gh pr merge <N> --squash --match-head-commit <full 40-char head sha>`. No skip marker: this merge must deploy.
  - **Live event:** the push to `main` runs `deploy.yml`, which runs `k3s.yml`:
    - the handler "Restart k3s" (`roles/k3s_common/handlers/main.yml`, `throttle: 1`) restarts `k3s` or `k3s-agent`
      on every node, one at a time;
    - the ArgoCD helm step re-runs;
    - the `handoff` job rewrites `KUBECONFIG_RAW`.
  - Expected: `gh run watch <run id> --repo Starktastic-Homelab/ansible` ends `success`, with "Apply Configuration" and
    "Push kubeconfig to org secret" both green.
- [ ] **Step 8: If the deploy fails.**
  - A failed deploy keeps the lock (`deploy.yml` "Release ownership after successful configuration" runs only on
    success). Stop and bring the log to Ben. Never clear the lock by hand.
  - Rollback is a new PR that replaces the copy task with `ansible.builtin.file: state: absent` on the same path,
    with `notify: Restart k3s`. A plain revert removes the task but leaves the file on every node.
- [ ] **Step 9: Post-merge checks** (read-only).
  - Rows:
    - configz per node, as in Step 6;
    - for each `k3s`-tagged VM, `qm guest exec <vmid> -- cat /etc/systemd/logind.conf.d/99-kubelet.conf`;
    - for each `k3s`-tagged VM, `qm guest exec <vmid> -- busctl get-property org.freedesktop.login1
      /org/freedesktop/login1 org.freedesktop.login1.Manager InhibitDelayMaxUSec`;
    - for each `k3s`-tagged VM, `qm guest exec <vmid> -- systemd-inhibit --list --mode=delay --no-pager`;
    - `KUBE get nodes`;
    - `KUBE get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`.
  - Expected:
    - every node shows `"shutdownGracePeriod":"1m30s"` and `"shutdownGracePeriodCriticalPods":"40s"`, the lab's form
      (`storage-lab/b10/f14/deploy.log:18,23`);
    - `InhibitDelayMaxSec=90` in the drop-in;
    - `InhibitDelayMaxUSec` reads `t 90000000`. The lab recorded the value (`storage-lab/b10/notes.md:111`) but not the
      command, so the `busctl` form is UNVERIFIED;
    - a `kubelet` delay inhibitor is listed;
    - every node is Ready, and no pod is new in Failed or Pending.

    After k3s restarts, a GPU pod in `UnexpectedAdmissionError` can appear. Delete it by hand only with **Ben OK**
    (memory `gpu-admission-race`).
  - Evidence: `evidence/1.2/after.txt`.
- [ ] **Step 10: Re-base A** (offline).
  - Run: `. ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; git -C $A fetch origin && g -C $A rebase
    origin/main` (one line), once `origin/main` shows the merge. A `rebase --continue` also uses `g`.
  - Conflicts are expected in `scripts/tests/test_k3s_storage_settings.py` and `.github/workflows/validate.yml`. Keep
    A's version of the test file, which is a superset, and keep a single "Test K3s storage settings" step.
  - Then re-run A's suites (Task 0.1 commands).
  - Expected: `git -C <A> diff origin/main -- roles/k3s_common/tasks/main.yml` no longer shows the drop-in tasks.
  - Remove the worktree: `git -C <A> worktree remove ~/.cache/claude-homelab-live/worktrees/ansible-kubelet-shutdown`.

### Task 1.3: Jellyfin and filebrowser guards (apps)

Two PRs, because the guard ConfigMaps and the apps sync independently:
- base-configs is in `config-apps`, which has no RollingSync (`bootstrap/appsets/config-apps.yaml:23-29`);
- the apps are in `cluster-apps`.

If both changes went in one PR, Jellyfin could restart before its ConfigMap knew `jellyfin`, and the guard would
refuse. A refusing guard is a stop (Global Constraints). So the ConfigMap PR (1.3a) merges and is verified live
before the wiring PR (1.3b).
- Amended 2026-11-22 (D47): the generic guard knows no app names, so the reason is now only that ConfigMap
  `retained-startup-guard` must exist in `media` and `operations` before a pod mounts it; until then the pod waits in
  ContainerCreating. 1.3a creates it in both namespaces.

**Guard shape (D24, D47, Ben 2026-11-22).** Both apps run the one generic guard, ConfigMap `retained-startup-guard`
(`infrastructure/base-configs/templates/retained-startup-guard.yaml`), with no entry for either app. The first draft
extended `media-retained-startup-guard` and `operations-home-retained-startup-guard`; 1.3a deletes both.

Neither volume held an identity marker. Ben chose to write them (done 2026-11-22, `evidence/1.3/marker-write.txt`, in
the form of sonarr's: 0440 1000:1000), and he chose that no retained guard checks native layout. So Jellyfin and
filebrowser need no guard entry (the generic guard has none, D47), and the same PR (1.3a) drops the layout checks
from every other retained guard:
- pure-layout apps become marker-only;
- content checks, DB checks and the Postgres system identifier are dropped too (D47, Ben 2026-11-22): every
  retained guard, NFS guards included, is the one generic guard, and `postgres` and `immich-postgres` use markers.

The 41 guards of 1.3a are in `evidence/1.3/report-generic-guard.md` ("Final guard table"),
`docs/runbooks/retained-startup-guard.md` and `GUARDS`; 1.3b adds Jellyfin and filebrowser. The older
`evidence/1.3/guard-map.json` (33 rows, one per block-storage volume, before D47) is history.

**Files** (new worktree `~/.cache/claude-homelab-live/worktrees/apps-p0-guards` from apps `origin/main`, branches
`feat/p0-guard-layouts` (1.3a) and `feat/p0-guard-wiring` (1.3b)):
- 1.3a:
  - Modify: `infrastructure/base-configs/templates/media-block-storage/guard-configmap.yaml`. It is a double-quoted
    YAML scalar; keep that form. It has no `{{`, so Helm passes it through.
  - Modify: `infrastructure/base-configs/templates/operations-home-block-storage/guard-operations.yaml`, both `base.py`
    and `guard.py`. Leave `guard-home-automation.yaml` alone: it is a separate copy in `home-automation`.
  - Create: `scripts/storage/tests/test_startup_guards.py`. No guard test exists on apps main today; the only test there
    is `test_nas_rpc.py`.
  - Modify: `docs/runbooks/jellyfin-storage.md`, one sentence under "Normal operation and rebuilds". `:40` says the old
    guards were removed, which becomes misleading.
  - Amended 2026-11-22 (D46): the list above is the first 1.3a commit and is history (the media ConfigMap is now a
    block scalar with `.Files.Get`, and `base.py` is gone). The final 1.3a also creates
    `infrastructure/base-configs/files/retained-startup/guard.py` (rendered with `.Files.Get` into the six group
    templates), deletes `utility-home-block-storage/guard-home-automation.yaml`, and adds `manifests/kustomization.yaml`
    plus `manifests/retained-startup/*` in 19 app dirs; the full list is in `evidence/1.3/report-guard-files.md`.
  - Amended 2026-11-22 (D47): the D46 list above is history too. The final 1.3a (76 files, `evidence/1.3/
    report-generic-guard.md`) creates `infrastructure/base-configs/files/retained-startup/guard.py`,
    `infrastructure/base-configs/templates/retained-startup-guard.yaml` and `docs/runbooks/retained-startup-guard.md`
    (the marker table); deletes the 7 group guard templates, the 15 per-app guard and database-guard manifests and
    every `manifests/kustomization.yaml` and `retained-startup/` dir the branch had added; and edits the values files,
    13 runbooks and `services/media/autobrr/README.md`.
- 1.3b:
  - Modify: `services/media/jellyfin/values.yaml`, `services/operations/filebrowser/values.yaml`
  - Modify: `scripts/storage/tests/test_startup_guards.py` (the wiring test and two `GUARDS` rows; the freeze is
    already in 1.3a, D47)
  - Modify: `docs/runbooks/retained-startup-guard.md`, one row each for Jellyfin and filebrowser (D47)

**Interfaces:**
- Consumes: the live layout read in Step 1, which gives:
  - `<L:jellyfin_files>`, expected `('system.xml', 'data/data/jellyfin.db')`. These come from the retired iSCSI
    checks, removed in apps `19d7d111`, `scripts/storage/*`: `root/'data/data/jellyfin.db'` and `system.xml`. The
    paths are UNVERIFIED on the current Jellyfin 12 volume.
  - `<L:filebrowser_files>`, expected `('database.sqlite',)`
    (`services/operations/filebrowser/manifests/templates/configmap.yaml:10`).
    That it is SQLite is UNVERIFIED; scout-volumes guessed BoltDB.
  - `<L:jellyfin_uid>:<L:jellyfin_gid>` and `<L:filebrowser_uid>:<L:filebrowser_gid>`, the owners of those files.
  - Amended 2026-11-22 (D47): no guard reads files or headers, so `<L:*_files>` is history. Only the owners are still
    used (Step 8's `runAsUser`), read from `evidence/1.3/layout.txt`.
- Produces:
  - no entry for Jellyfin or filebrowser in any guard: the generic guard accepts any well-formed app name with
    the right marker, and no layout checks are left in any retained guard (as amended below);
  - an init container `retained-state` in both apps: `/retained-startup/guard.py <app> /retained`, with the claim
    mounted read-only at `/retained`;
  - the log line `Retained identity accepted.`, which the generic guard prints for both apps.
  - Amended 2026-11-22 (D46, "All in #1707"): 1.3a also turns the group guards into one generic marker script,
    `infrastructure/base-configs/files/retained-startup/guard.py`, with no app names. The content checks move to
    app-owned guards in `<app>/manifests/retained-startup/guard.py`: cleanuparr, cineplete, changedetection,
    qbittorrent (used by qbittorrent-ru too), stirling-pdf, mosquitto, zigbee2mqtt. The 12 per-app inline guards become
    files plus kustomize generators with byte-identical data. The enrollment and completion-gate scripts and
    `bazarr-scripts.yaml` stay inline: they are hash-bound or read by path. Evidence:
    `evidence/1.3/brief-guard-files.md`, `evidence/1.3/report-guard-files.md`.
  - Amended 2026-11-22 (D47, "Drop them in #1707 too"): the app-owned guards above are gone. Every retained guard
    runs `python3 -I -B /retained-startup/guard.py <app> <root> [<kind> [<marker-file>]]` from ConfigMap
    `retained-startup-guard` (namespaces databases, home-automation, media, monitoring, operations). No guard checks
    content, the Postgres backend or the Postgres system identifier. Enrollment and completion gates are unchanged.
    The 41 guards and their markers are in `evidence/1.3/report-generic-guard.md`.

- [ ] **Step 1: Read the live layout** (read-only, session OK). Done (`evidence/1.3/layout.txt`); superseded by D47:
  no guard reads files or SQLite headers, so the file and header checks below are history. Only the owners still count.
  - Find each pod with `KUBE -n media get pod -l app.kubernetes.io/instance=jellyfin -o name`; filebrowser is the same
    with `-n operations` and `instance=filebrowser`. The label is app-template's standard one; UNVERIFIED on these
    releases, so fall back to `get pods` and a name match.
  - Jellyfin row: `KUBE -n media exec <pod> -c main -- sh -c 'cd /config && ls -lan . data data/data | head -60;
    stat -c "%a %u:%g %s %n" system.xml data/data/jellyfin.db; head -c 16 data/data/jellyfin.db | od -c | head -2;
    ls -la .homelab-jellyfin-data .retained-volume.json 2>&1'`
  - filebrowser row: the same shape for `/home/filebrowser/data`: `database.sqlite`, and `.homelab-filebrowser-data`.
    Whether the `gtstef/filebrowser` image has `sh`, `stat` and `od` is UNVERIFIED. If it has none, stop: an ephemeral
    debug container is a mutation that needs its own **Ben OK**.
  - Expected:
    - every `<L:*_files>` entry exists as a regular file with size greater than 0;
    - each `.db`/`.sqlite` header reads `S Q L i t e   f o r m a t   3 \0`;
    - every parent directory has `x` for the guard's uid;
    - record the owners;
    - record whether any marker exists.
  - If a path differs, Step 3 uses what Step 1 read; say so in `evidence/1.3/facts.md`. If filebrowser's
    `database.sqlite` is not SQLite, stop for Ben: the guard checks the SQLite header by file suffix, so that file
    cannot be listed without failing.
  - Evidence: `evidence/1.3/layout.txt`.
- [ ] **Step 2: Write the failing guard tests (1.3a).** Done; superseded by the D46 amendment: the tests now run
  the guard files directly (`scripts/storage/tests/test_startup_guards.py` on the 1.3a branch), so the sketch below
  is history.
  - Create the worktree: `git -C ~/.cache/claude-homelab-live/worktrees/apps-storage-vm worktree add
    ~/.cache/claude-homelab-live/worktrees/apps-p0-guards -b feat/p0-guard-layouts origin/main`.
  - The test, as short code:

    ```python
    T = "infrastructure/base-configs/templates/"
    GUARDS = {"jellyfin": T + "media-block-storage/guard-configmap.yaml",
              "filebrowser": T + "operations-home-block-storage/guard-operations.yaml"}
    SQLITE = b"SQLite format 3\0" + b"\0" * 84
    LAYOUT = {"jellyfin": {"system.xml": b"<ServerConfiguration/>", "data/data/jellyfin.db": SQLITE},
              "filebrowser": {"database.sqlite": SQLITE}}          # = <L:*_files> from Step 1

    def run_guard(app, root) -> int:
        """Write every data key of the ConfigMap into a temp dir, then run
        [sys.executable, "-I", "-B", dir / "guard.py", app, str(root)]; return the exit code."""

    def test_accepts_native_layout(self):          # per app; with the marker on the marker-present branch
        self.assertEqual(run_guard(app, tree(LAYOUT[app])), 0)
    def test_refuses_missing_or_wrong_marker(self):  # marker-present branch only
    def test_refuses_blank_filesystem(self):       # only lost+found/
        self.assertEqual(run_guard(app, tree({"lost+found/": None})), 1)
    def test_refuses_each_missing_file(self):      # drop one LAYOUT entry at a time
    def test_refuses_wrong_sqlite_header(self):    # b"\0" * 100 in the .db/.sqlite file
    def test_refuses_symlinked_file(self):         # the db is a symlink to a valid file outside root
    def test_other_apps_keep_their_marker(self):   # sonarr tree without marker -> 1, with marker -> 0
    ```

    `tree()` builds a `TemporaryDirectory` from a `{relative path: bytes | None for a dir}` map. Read the ConfigMaps
    with `yaml.safe_load`; CI installs PyYAML earlier in the same `validate` job (`validate-and-diff.yml:67`).
  - Run: `~/.cache/claude-homelab-live/venv/bin/python -B -m unittest discover -s scripts/storage/tests -p
    'test_startup_guards.py' -v`
  - Expected: FAIL in `test_accepts_native_layout` for both apps: exit 1 (`Invalid retained root or application`),
    not 0.

    The refusal tests already pass before the change, because an unknown app is refused. They pin behaviour and are
    not the red step. `test_other_apps_keep_their_marker` passes too; it guards the edit of the escaped string.
- [ ] **Step 3: Make the guards marker-only (D24).** Jellyfin and filebrowser are `()`. In every other retained guard,
  drop the layout checks (existence, type, size, magic header) and keep the marker, the content checks, the Postgres
  identifier, root anti-redirect and the log lines. Leave the NFS guards unchanged. Update the runbook sentences that
  describe native-state checks. Superseded by D47: content checks and the Postgres identifier are dropped too, and
  every guard is the generic one.
- [ ] **Step 4: Run to PASS.**
  - Run: the Step 2 command.
  - Expected: all tests OK.
  - Run: `~/.cache/claude-homelab-live/venv/bin/yamllint
    infrastructure/base-configs/templates/media-block-storage/guard-configmap.yaml
    infrastructure/base-configs/templates/operations-home-block-storage/guard-operations.yaml`
    (D47: both files are deleted; run yamllint with `.github/yamllint.yaml` on the changed yaml files instead)
  - Expected: no errors.
- [ ] **Step 5: Commit (1.3a).**
  - Message: `feat(storage): marker guards for Jellyfin and filebrowser, no native-layout checks (ADR 0017 Migration 0)`
  - Apps needs no skip marker.
- [ ] **Step 6: Merge 1.3a** (Ben asks; **Ben OK**).
  - Push with `git push -u origin feat/p0-guard-layouts`, then `gh pr create`. Check the diff preview with
    `git merge-tree --write-tree origin/main <head>` (memory `pr-merge-mechanics`). Then
    `gh pr merge <N> --squash --match-head-commit <sha>`.
  - Merge at a time Ben picks, outside every backup window.
  - **Precondition (D47):** both database markers exist live. Without them, the database refuses startup and every app
    that depends on it goes down. Each is a regular file of 1 to 128 bytes holding exactly `homelab/<app>/data/v1`
    and a newline, on the claim root, outside PGDATA:
    - `/bitnami/postgresql/.homelab-postgres-data`, `homelab/postgres/data/v1`, 0440 1001:1001, written 2026-11-22
      with Ben's OK (`evidence/1.3/pg-marker-write.txt`);
    - `/data/.homelab-immich-postgres-data`, `homelab/immich-postgres/data/v1`, 0440 owned by `postgres` (uid 999),
      already there (`evidence/1.3/pg-marker-ref.txt`).

    autobrr's guard gets stricter (no symlink, a regular file of 128 bytes or less); its marker is a regular 26-byte
    file (`evidence/1.3/autobrr-marker.txt`). Re-read all three just before the merge (read-only).
  - **Live event (D47):** ArgoCD syncs `base-configs` and every app whose pod spec changed. The pod-spec change
    restarts 41 workloads (the list is in `evidence/1.3/report-generic-guard.md`, "Restart list at merge"):
    - databases: postgres-postgresql and redis-master (StatefulSets), pgadmin;
    - media: audiobookshelf, autobrr, bazarr, calibre-web, cineplete, cleanuparr, immich-postgres, lidarr, lingarr,
      navidrome, prowlarr, qbittorrent, qbittorrent-ru, radarr, radarr-ru, seerr, seerr-ru, shelfmark, sonarr,
      sonarr-ru;
    - home-automation: home-assistant, mosquitto, zigbee2mqtt;
    - operations: bytestash, changedetection, convertx, excalidash, karakeep, microbin, ntfy, paperless-ngx,
      stirling-pdf;
    - monitoring: kube-prometheus-stack's prometheus, alertmanager and grafana, and loki and tempo (StatefulSets);
    - crowdsec: crowdsec-lapi.

    39 of them run the generic guard; excalidash and crowdsec-lapi only lose their `retained-database` init.
    base-configs and the apps sync independently, so a pod that starts before both have synced can wait in
    ContainerCreating on a ConfigMap that does not exist yet. That is a wait, not a refusal; it converges once both
    have synced.
  - Check: every restarted pod's guard init container `Completed` with `Retained identity accepted.`, and each app
    Healthy:
    `KUBE get pods -A -o json`, filtered to init containers that mount `retained-startup`, with
    `state.terminated.reason`, and the ArgoCD Applications Synced and Healthy.
  - Expected: no init container in Error or CrashLoopBackOff. A refusing guard is a stop (Step 13): revert the PR
    (**Ben OK**), never touch the volume.
  - Evidence: `evidence/1.3/configmaps.txt`.
- [ ] **Step 7: Write the failing wiring test (1.3b).**
  - Branch `feat/p0-guard-wiring` from the new `origin/main`.
  - The test, as short code:

    ```python
    WIRING = {"jellyfin": ("services/media/jellyfin/values.yaml", "jellyfin-config", "/config",
                           "retained-startup-guard"),
              "filebrowser": ("services/operations/filebrowser/values.yaml", "data", "/home/filebrowser/data",
                              "retained-startup-guard")}

    def test_values_wire_guard_read_only(self):
        init = values["controllers"]["main"]["initContainers"]["retained-state"]
        self.assertEqual(init["command"], ["python3", "-I", "-B", "/retained-startup/guard.py", app, "/retained"])
        self.assertTrue(init["image"]["digest"].startswith("sha256:"))   # Renovate may bump it
        claim = values["persistence"][volume]
        self.assertEqual(claim["globalMounts"], [])
        self.assertEqual(claim["advancedMounts"]["main"]["retained-state"], [{"path": "/retained", "readOnly": True}])
        self.assertIn({"path": app_path}, claim["advancedMounts"]["main"]["main"])
        startup = values["persistence"]["retained-startup"]
        self.assertEqual((startup["type"], startup["name"]), ("configMap", configmap))
        self.assertEqual(startup["advancedMounts"]["main"]["retained-state"],
                         [{"path": "/retained-startup", "readOnly": True}])
    ```

  - Add `jellyfin` and `filebrowser` to the pinned `GUARDS` table, `("jellyfin", "/retained")` and
    `("filebrowser", "/retained")`: 1.3a's `test_every_guard_is_the_generic_guard` asserts that the guards it finds are
    exactly `GUARDS`, and it checks most of `WIRING` for every guard.
  - The group guard freeze (D46, as amended by D47) is already on main from 1.3a: `test_no_other_guard_configmap` and
    `test_no_other_retained_configmap_is_mounted` refuse any retained guard ConfigMap other than
    `retained-startup-guard`, and `test_guard_and_template_name_no_app` keeps app names out of `guard.py`. 1.3b adds
    no freeze test. A new retained app uses its rendered guard (Task 2.9); Task 5.12 converts migrated volumes.
  - Run: the Step 2 command.
  - Expected: FAIL with `KeyError: 'initContainers'` for filebrowser and `KeyError: 'retained-state'` for Jellyfin, and
    `test_every_guard_is_the_generic_guard` FAILS on the two new `GUARDS` rows.
- [ ] **Step 8: Wire the init containers.** Copy the audiobookshelf block
  (`services/media/audiobookshelf/values.yaml:31-60,78-100` on main): python image digest `sha256:a11116e6...`,
  `readOnlyRootFilesystem: true`, `capabilities.drop: [ALL]`,
  `seccompProfile: RuntimeDefault`, requests 10m/32Mi, limits 100m/64Mi.
  - Run as the file owner: `runAsUser`/`runAsGroup` = `<L:*_uid>`/`<L:*_gid>`, with `runAsNonRoot: true` when that uid
    is not 0, as autobrr does (`services/media/autobrr/values.yaml:60-64` after 1.3a). The existing
    root-with-no-capabilities form cannot read 0600 files owned by another uid.
  - Jellyfin:
    - `jellyfin-config` goes from `globalMounts: [/config]` to `globalMounts: []`, plus `advancedMounts.main.main:
      [{path: /config}]` and `advancedMounts.main.retained-state: [{path: /retained, readOnly: true}]`;
    - add `retained-startup` (configMap `retained-startup-guard`, `defaultMode: 292`, mounted only in
      `retained-state` at `/retained-startup`, read-only), as audiobookshelf does;
    - the `disposable` emptyDir mount at `/config/cache` stays as it is;
    - `disposable-dirs` no longer gets `/config`, which it never used: it writes only `/disposable`.
  - filebrowser: the same for `data`, with `/home/filebrowser/data`, and `retained-startup` with configMap
    `retained-startup-guard`. filebrowser has no `initContainers` key yet; add it under
    `controllers.main`.
- [ ] **Step 9: Run to PASS.**
  - Run: the Step 2 command, `python3 scripts/check-jellyfin-compat.py` (it reads only the probes, `:78-82`), and
    yamllint on both values files.
  - Expected: all pass.

    The PR's argocd-diff-preview shows changes to the Jellyfin and filebrowser Deployments only: one init container,
    one ConfigMap volume, and `/config` moved to per-container mounts.
- [ ] **Step 10: Commit (1.3b).**
  - Message: `feat(storage): run the marker guard before Jellyfin and filebrowser start`
- [ ] **Step 11: Merge 1.3b** (Ben asks; **Ben OK**).
  - Merge at a time Ben picks for a Jellyfin restart (not the evening), outside every backup window, and after Step 6's
    check.
  - **Live event:** ArgoCD syncs `jellyfin` and `filebrowser`. Each Deployment is `Recreate`, so each app is down
    once, for about a minute.
- [ ] **Step 12: Check that the guards passed** (read-only).
  - Rows:
    - `KUBE -n media get pod <new pod> -o
      jsonpath='{.status.initContainerStatuses[?(@.name=="retained-state")].state.terminated.reason}'` (one row)
    - `KUBE -n media logs <new pod> -c retained-state`
    - the same two for filebrowser in `operations`
  - From the workstation:
    - `curl -fsS https://benplus.app/health`
    - `curl -fsS -o /dev/null -w '%{http_code}' https://files.internal.starktastic.net/api/health`

    This follows memory `ingress-probe-from-workstation`; the hosts come from the values and `app.yaml` files.
  - Expected:
    - `Completed` for both init containers;
    - the log line `Retained identity accepted.` from both (the generic guard's accept line, D47);
    - `Healthy` from Jellyfin and `200` from filebrowser.

    After a restart, a Jellyfin GPU pod can show `UnexpectedAdmissionError` (memory `gpu-admission-race`).
  - Evidence: `evidence/1.3/after.txt`.
- [ ] **Step 13: If a guard refuses, stop.**
  - The app stays down: its old pod is gone, and the init container keeps failing. Do not touch the volume and do not
    create a file to satisfy the guard.
  - Rollback is a revert PR of 1.3b (**Ben OK**). It brings the app back with no guard. Then compare Step 1's evidence
    with the marker the guard expects (`homelab/<app>/data/v1`).

### Task 1.4: wwn guard PR (terraform, W)

**Files** (W = `~/.cache/claude-homelab-live/worktrees/terraform-csi-wwn-guard`, branch `fix/csi-wwn-guard`, rebased in
Task 0.1; one commit, originally `da37a0d`):
- Create: `scripts/csi_wwn_guard.py`
- Modify: `scripts/maintenance_apply.py`, `.github/workflows/apply.yml`, `.github/workflows/validate-and-plan.yml`,
  `.github/PULL_REQUEST_TEMPLATE.md`, `scripts/tests/test-maintenance-workflow.py`, `README.md`, `CLAUDE.md`
- Step 2a (audit fold-in, D49) changes `scripts/csi_wwn_guard.py`, `scripts/maintenance_apply.py`, both workflows,
  the test file and any doc that names `CSI_WWN_ACK` in a second commit; it creates no file.

**Interfaces:**
- Produces:
  - `csi_wwn_guard.scsi_updates(plan) -> list[str]` and `ACK_TEXT`;
  - the plan-comment line `No in-place updates of VMs holding SCSI disks.`, or a `WARNING: ...` naming the VMs;
  - the apply-time refusal in `maintenance_apply.execute()`, before any drain, with the lock released
    (`maintenance_apply.py:40-42`);
  - the PR-body box `- [ ] Accept that this apply strips wwn from Proxmox CSI disks`, and the dispatch input
    `accept_csi_wwn_loss`.
- Consumed by: the wwn rule in the Global Constraints; Tasks 2.1, 3.3 and 5.3.

- [ ] **Step 1: Confirm the rebase from Task 0.1** (offline).
  - Run: `git -C <W> rev-list --count HEAD..origin/main` and `git -C <W> log --oneline origin/main..HEAD`
  - Expected: `0`, and exactly one commit, `fix: refuse applies that would strip wwn from Proxmox CSI disks` (Step 2a
    adds the second). Otherwise finish Task 0.1 for W first.
- [ ] **Step 2: Re-run the suites** (offline).
  - The lock helper is the reviewed one CI pins:
    `git -C ~/.cache/claude-homelab-live/worktrees/ansible-storage-vm worktree add --detach
    ~/.cache/claude-homelab-live/worktrees/ansible-lock-helper 887269798650`. That commit is on
    `codex/storage-maintenance`
    only; keep that branch (CLAUDE.md).
  - Run: `PYTHONPATH=~/.cache/claude-homelab-live/worktrees/ansible-lock-helper/scripts
    ~/.cache/claude-homelab-live/venv/bin/python -B scripts/tests/test-maintenance-workflow.py`
  - Expected: OK, including `test_csi_wwn_guard_refuses_before_any_mutation_and_releases_lock`,
    `test_csi_wwn_ack_lets_the_apply_through`, `test_saved_plan_used_and_no_changes_skips_mutation` and
    `test_ack_text_matches_workflow_and_template`.
  - Run: `PATH=~/.cache/claude-homelab-live/bin:$PATH python3 scripts/tests/test-rebuild-cohort.py` (needs
    `terraform`) and `python3 scripts/check-readme-images.py`
  - Expected: OK for both.
- [ ] **Step 2a: Audit fold-in** (offline, TDD; D49, genericity audit 2026-11-22, "terraform `fix/csi-wwn-guard`").
  Four low findings, one commit. Line numbers are at W `8801807`.
  - Write the failing tests in `scripts/tests/test-maintenance-workflow.py`:
    - `test_ack_read_by_maintenance_apply` (replaces `test_csi_wwn_ack_lets_the_apply_through`, which sets
      `CSI_WWN_ACK`): with the CSI plan fixture and `EVENT_NAME=pull_request_target`, `execute('normal', True,
      self.lock)` applies when env `PR_BODY` has a line `- [x] ` + `ACK_TEXT`. It refuses, with the lock released as in
      `test_csi_wwn_guard_refuses_before_any_mutation_and_releases_lock`, for `- [ ] ` + `ACK_TEXT`, for the text inside
      a longer line, and with no `PR_BODY`; a CRLF body (`\r\n` line ends) with the ticked line applies. With `EVENT_NAME=workflow_dispatch`, `ACCEPT_CSI_WWN_LOSS=true` applies and
      `TRUE` or `false` refuses.
    - Rewrite `test_ack_text_matches_workflow_and_template` as `test_ack_text_lives_in_the_guard_and_template`:
      `apply.yml` contains neither `ACK_TEXT` nor `csi_wwn_ack`; job `apply` env maps
      `PR_BODY: ${{ github.event.pull_request.body }}` and `ACCEPT_CSI_WWN_LOSS: ${{ inputs.accept_csi_wwn_loss }}`;
      the template keeps `- [ ] ` + `ACK_TEXT`; the skip-pattern assert stays. Drop its step-order asserts
      (`Create Terraform plan` < guard step < `Upload plan log artifact`).
    - `test_plan_step_runs_the_guard`: `validate-and-plan.yml` has no step `Check for VM updates that strip Proxmox
      CSI wwn`. Run the `Create Terraform plan` script with `sh -e -c` and a fake `terraform` on `PATH` (as Task
      2.1a's `test-storage-ci.py` runs step scripts): plan exit 1 fails the step and never calls `terraform show`;
      exit 2 appends the guard's line to `plan.log` and re-encodes `plan.log.b64`.
    - `test_capture_is_explicit`: the fake `run_command` records `kwargs['capture_output']`. In a drain-mode run it
      is `True` exactly for `kubectl get nodes -o json` and `terraform show -json plan.tfplan`.
    - In `CsiWwnGuardTests`, `test_update_without_disks_key_is_flagged`: `vm()` with `before` `{'name': 'x'}` (no
      `disks` key) and actions `['update']` is flagged. `update-no-scsi`, `scsi_updates({}) == []` and the
      `['create']` case (`before` `None`) still pass.
  - Run: the Step 2 command. Expected: FAIL (the five tests above).
  - Implement:
    - `scripts/csi_wwn_guard.py`: `acknowledged(env) -> bool`: on `workflow_dispatch`,
      `env.get('ACCEPT_CSI_WWN_LOSS') == 'true'`; otherwise some line of `env.get('PR_BODY', '')`, stripped, equals
      `'- [x] ' + ACK_TEXT`. In `scsi_updates`, an `['update']` whose `before` has no `disks` key is a hit, with
      `# shortcut: reads telmate 3.0.2-rc10's disks schema (pinned exactly); the guard lapses at Retirement 5.3.`
    - `scripts/maintenance_apply.py`: `run(*args, capture=False)` passes `capture_output=capture`; the two reads pass
      `capture=True`; the ack check becomes `not acknowledged(os.environ)`.
    - `apply.yml`: delete the bash ack grep and `CSI_WWN_ACK` (check step, `check-conditions` output, `apply` env).
      Add `PR_BODY` and `ACCEPT_CSI_WWN_LOSS` to the `apply` job env. Keep the `accept_csi_wwn_loss` input.
    - `validate-and-plan.yml`: in `Create Terraform plan`, after the `EXIT_CODE -eq 1` check, run
      `apk add --no-cache python3`, then
      `terraform show -json plan.tfplan | python3 scripts/csi_wwn_guard.py | tee -a plan.log`, then
      `base64 plan.log > plan.log.b64` again. The first `base64` stays where it is, so a failed plan still has its
      log. Delete the separate guard step.
    - Grep `CSI_WWN_ACK\|Check for VM updates` in `README.md`, `CLAUDE.md` and `docs/`, and fix each hit.
  - Run: the Step 2 commands. Expected: OK, including the five tests above and
    `test_csi_wwn_guard_refuses_before_any_mutation_and_releases_lock`; `git -C <W> grep -n CSI_WWN_ACK` prints
    nothing.
  - Commit: `refactor: read the wwn ack in maintenance_apply, run the guard in the plan step, fail closed without disks`.
  - Later references: Task 2.1a's "W's guard step" and "W's capture test" now mean the plan step and `capture=True`
    (2.1a Steps 3 and 7 say so). Task 5.11 adds its line inside `Create Terraform plan` (pointer at its Files list).
- [ ] **Step 3: Push and open the PR** (Ben asks).
  - Run: `git -C <W> push -u origin fix/csi-wwn-guard`, then `gh pr create --repo Starktastic-Homelab/terraform --base
    main --head fix/csi-wwn-guard --title "fix: refuse applies that would strip wwn from Proxmox CSI disks"`.
  - Body: the repo template with every box unticked, including the new wwn box and the drain and destroy boxes. Add a
    two-line summary and the Claude Code line.
  - Never write a GitHub skip pattern anywhere in the title, body or commit (memory `terraform-skip-ci-pr-body`). This
    merge should run its apply.
  - Expected: `validate-and-plan.yml` runs from the PR head (`on: pull_request`, `validate-and-plan.yml:3-9`), so the
    new step runs. The sticky plan comment shows `No changes.` and `No in-place updates of VMs holding SCSI disks.`
    Any other plan line is a stop.
- [ ] **Step 4: Merge** (**Ben OK**).
  - Pre-checks:
    - no other terraform or ansible run is active;
    - the lock is free;
    - Task 1.2's deploy is finished;
    - outside every backup window.
  - If the PR is behind `main`, run `gh pr update-branch <N> --rebase --repo Starktastic-Homelab/terraform`. Wait for
    the plan comment's `updated_at` to come after the rebase and still say `No changes.`
  - Then run `gh pr merge <N> --squash --match-head-commit <full sha>` (memory `pr-merge-mechanics`).
  - **Live event:** `apply.yml` (`pull_request_target: closed`) takes and releases the maintenance lock. The saved plan
    exited 0, so `execute()` sets `changed=False` and runs no terraform command (`maintenance_apply.py:15-22,33`). It
    reports `has_changes=false`, so "Trigger Ansible after successful lock release" is skipped and no
    `infrastructure-changed` is sent.
- [ ] **Step 5: Check the apply.**
  - Run: `gh run list --repo Starktastic-Homelab/terraform --workflow apply.yml -L 1
    --json databaseId,conclusion,headSha`
  - Then: `gh run view <id> --repo Starktastic-Homelab/terraform --json jobs --jq '.jobs[] | [.name, .conclusion]'`
  - Then: `gh run list --repo Starktastic-Homelab/ansible --workflow deploy.yml -L 1`
  - Expected:
    - the apply job is `success` and the trigger job `skipped`;
    - no new deploy run;
    - the maintenance lock is free afterwards.
  - Evidence: `evidence/1.4/` holds the plan comment (`gh pr view <N> --comments`) and the run summaries.
- [ ] **Step 6: Re-base T** (offline).
  - T changes `scripts/maintenance_apply.py` for `--chdir` (Task 2.1), the same file this PR changed. Run:
    `. ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh; git -C $T fetch origin && g -C $T rebase
    origin/main` (one line), then re-run T's suites (Task 0.1 commands). A `rebase --continue` also uses `g`.
  - Expected: T's `maintenance_apply.py` keeps both the wwn refusal and its own changes.
  - Remove the lock-helper worktree when Part 2 no longer needs it.

**Part 1 gate.** The part is done when all of these hold:
- `evidence/1.1/facts.md` shows the backup gate met and pstore empty;
- the drop-in is live on every node (1.2 Step 9);
- both guards passed (1.3 Step 12);
- the wwn guard is on terraform `main` with a no-op apply (1.4 Step 5);
- A and T are re-based on the new `main`.

Ben confirms the gate before Part 2's code merges and before any Part 3 step.

---

## Part 2: Foundation code (offline, TDD, on branches)

Part 2 builds, offline and test first, the code the lab did not need. Each task ends at a commit; PRs open only when
Ben asks, and each merge happens in the Part 3 task named under it. Global Constraints apply to every step.
Tasks 2.1, 2.2, 2.3, 2.8, 2.10 and 2.11 are drafted here; 2.4-2.7, 2.9 and 2.12 are drafted in another part.
Items marked "audit fold-in" come from the genericity audit of 2026-11-22 (D49), folded into the task that already
touches the files.

**Built since: the Part 2 final-review fix pass (local, unpushed, 2026-11-23;
`evidence/part2-final/fix-list.json`).** These change what the task text below says a run does; where the two differ,
this block and the code win.
- A (ansible, `feat/retained-storage-vm`):
  - n=1 (`e1a5bc9`): `roles/storage_vm/tasks/assert.yml` runs first in `storage-dry-run.yml` and in the role. It
    refuses a worker that is in the installed `/etc/homelab-storage/config.json` but missing from the rendered
    `storage_vm_workers`, before any config, nftables or ACL write. An unreadable installed config fails; none
    installed (first bootstrap) passes. A deliberate removal passes only when the new `storage.yml` dispatch input
    `remove_workers` names it. Then `lio.ensure_target(..., cut=())` still refuses (`InUse`) to delete an ACL with a
    session or unreadable info, except a fenced worker's. A worker that drops out between the dry run and the apply is
    refused under the lock, which D31 keeps.
  - n=3 (`206fc8c`): the `storage.yml` dispatch input `max_removals` (`[1-9][0-9]{0,2}`) sets the removal brake for
    that run only. The step `Validate the dispatch approvals` (id `approvals`) writes both inputs to
    `storage-approvals.json` as `storage_vm_remove_workers` (list) and `storage_vm_max_removals` (int); both playbook
    steps read it with `-e @storage-approvals.json`, and the credential cleanup deletes it.
  - n=11 (`1fb6bd1`, `aaa5ba1`): the playbook `storage-preflight.yml` runs in `storage.yml` and `storage-expiry.yml`
    as the step `Check that k3s answers before the lock` (id `preflight`, output `k3s`), before the lock (and in
    `storage.yml` before the dry run). No k3s binary, no `k3s.yaml` or no `ok` from `/readyz` on `masters[0]` gives
    `k3s=false`: a green skip with a `::warning::`, no lock. An unreachable master, any other error, or no `k3s`
    output fails the run, still without the lock. The D51 adopted-lock path skips it.
  - n=17 (`63d5720`, `a430b6a`, `1173846`): `storage-preflight.yml` first imports the inventory fetch and validate, so
    the expiry fails before the lock on a fetch error. A missing inventory file fails at `git checkout`; it never
    reads as empty.
  - n=2 (`46fa58b`, `e8c3565`): the dry run writes `storage-reconcile.prom` (`ok=False`: the last-success timestamp
    kept; a failed write only warns). It marks a target missing only for an exported id or an `lv-missing` refusal.
  - n=4 (`7829fd0`): `grow.yml` probes each node with attached exported volumes (`wait_for_connection`, 30 s). An
    unreachable one logs `WARNING: <node> is unreachable; not grown: <ids>. The next run retries.` and the run stays
    green; a grow failure on a reachable worker fails it.
  - n=15 (`f8a4605`): in the `storage.yml` play `Configure the storage VM and reconcile`, after the reconcile, a root
    with no `storage-boot-check.prom` and `rtslib-fb-targetctl` `active` runs `storage-reconcile boot-check` once; a
    non-zero exit fails the run in the last play, after grow and cleanup.
- AP (apps): n=7 (`c96060fc`) the absent legs of `StorageFencerBlind` and `StorageReconcileFailing` are
  `absent_over_time(...[5m])`, with promtool cases; n=8 (`9634761b`, `56f95f1c`) apps CI refuses removing an entry whose
  claim git still binds, and the `storage-removals-approved` label does not cover it; n=9 (`690016e4`) pins the
  rendered PVC's prune and delete protection and RWOP; n=10 (`3980766e`, `1a2a587e`) the static resolver consumers
  (loki, kube-prometheus-stack) get the full guard rule.

**Names this part pins** (other parts use the same ones):

| Name | Meaning | Recommendation (D1, D2) |
|---|---|---|
| `<D1:storage_vmid>`, `<D1:storage_name>` | storage VM VMID and name | `101`, `storage-01` (D1 decided 2026-11-23) |
| `<D1:storage_lan_ip>` | storage VM address on `vmbr0` (`10.9.9.0/24`), no mask | `10.9.9.40` (D1 decided) |
| `<D1:storage_bridge_ip>` | storage VM address on `vmbr2` (`10.99.2.0/24`), the LIO portal | `10.99.2.10` |
| `<D1:worker_bridge_start>` | host number of `kube-worker-01` on `vmbr2`; `kube-worker-02` gets the next one | `21` |
| `<D1:placeholder_vmid>` | the VMID that owns both data disks (never a real VM, not 9999) | `9998` |
| `<retained_volname>` | `vm-<D1:placeholder_vmid>-disk-0.raw`, on `virtio1`, VG `retained` | fixed by this part |
| `<regen_volname>` | `vm-<D1:placeholder_vmid>-disk-1.raw`, on `virtio2`, VG `regen` | fixed by this part |
| `<D2:retained_gib>`, `<D2:regen_gib>` | data disk sizes in GiB | `232` and `56` (D2 decided 2026-11-23; D44 floor 220 and 54) |

Task 3.4 must `pvesm alloc` the two disks under exactly these volume names. The test fixtures use the same pattern
(T `scripts/tests/test-storage-root.py:27-28`, `9990/vm-9990-disk-0.raw`), and so did the lab
(`9970/vm-9970-disk-{0,1}.raw`).

**Local test setup** (used by the Run lines below; nothing here touches a live system). Shell state does not carry
between calls, so every Run block in this part starts with these lines:

```sh
. ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh   # T, A, EVR and g() (Task 0.1 Step 1)
L=~/.cache/claude-homelab-live
PY=$L/venv/bin/python3                      # has ansible and PyYAML; the system python has neither
export TERRAFORM=$L/bin/terraform STORAGE_PLUGIN_DIR=$L/tf-plugin-cache COHORT_PLUGIN_DIR=$L/tf-plugin-cache
H=$EVR/0.1/helper                           # extracted in Task 0.1 at the pinned commit 8872697
test -f $H/scripts/maintenance_lock.py || { mkdir -p $H && git -C ~/Projects/homelab/ansible archive \
  887269798650e88fed791bb4f22a47bf50ad17be scripts | tar -x -C $H; }
# $H/scripts/maintenance_lock.py is the pinned lock helper that terraform and deploy.yml check out.
```

The workstation has no git identity: every commit, cherry-pick and rebase in this part uses `g` (from env.sh), and so
does any `rebase --continue` or `cherry-pick --continue` after a conflict.

`$L/bin/terraform` is v1.17.2, the CI pin; `$L/tf-plugin-cache` holds bpg 0.118.0 and telmate 3.0.2-rc10 in
`-plugin-dir` layout.

### Task 2.1: terraform: the storage root in CI

Four PRs, in merge order 2.1a (Task 3.3 Step 2), 2.1c (folded, Task 3.3 Steps 6-7), 2.1d (Task 3.3 Step 8, right
after the rebuild apply), 2.1b (Task 3.4 Step 3). Before starting: Task 1.4 (the wwn guard, terraform#244) is merged
(`410ae515`, 2026-11-22), and T is rebased onto `origin/main` again (done in Task 1.4 Step 6; redo it if main moved) (after the setup block above,
`git -C $T fetch origin && g -C $T rebase origin/main`), because `--chdir` edits the same `maintenance_apply.py`
function that W changed. Every cite below to `maintenance_apply.py` means the post-W file.

Two facts from the workflows shape all of 2.1:
- `validate-and-plan.yml` runs on `pull_request` (T `.github/workflows/validate-and-plan.yml:3-4`), so a PR is planned
  by **its own** copy of the workflow. Only `apply.yml` runs on `pull_request_target` (`apply.yml:3-8`). Which commit
  the `closed` event checks out (the merge commit or the base before it) is UNVERIFIED, so every design below works
  either way.
- The saved plan lives in S3 at `pr-<n>/` (`validate-and-plan.yml:98-107` uploads, `apply.yml:144-154` downloads
  recursively, the `cleanup` job deletes the prefix recursively). The 2.1a PR is planned by the new workflow and applied
  by the old one, so the k3s plan stays at the unprefixed `pr-<n>/plan.tfplan` and the storage plan goes to
  `pr-<n>/storage/`. The old recursive download then puts it at `storage/plan.tfplan`, where `--chdir storage` reads it.

Three departures from the ADR and outline wording, for Ben to accept with this part:
- The storage root is planned by an extra step in the existing jobs, not by a GitHub `matrix` entry. A matrix job keeps
  only one leg's outputs, and the S3 prefix, the plan comment and the drift issue are per job.
- The clone-source check runs inside `maintenance_apply.py` (called from `apply.yml`), right before the apply, under
  the lock. It reads the template VMID and name from the saved plan. CI takes both from the manifest's `storage`
  entry, the k3s way (D16, Task 2.1a Step 9a).
- A PR may change the k3s root or the storage root, never both. A plan check refuses both. The cost: any storage drift
  blocks every k3s PR until a storage PR resolves it, so drift on the storage VM must be fixed first.

### Task 2.1a: terraform: wiring PR (CI path, storage legs, secret mapping)

This task departs from the ADR in three ways, all under D25: the storage root gets second steps in the existing
plan and drift jobs (not matrix legs), the clone-source check runs inside `maintenance_apply.py` under the lock, and
each PR may touch only one root.

**Files** (worktree T, branch `feat/retained-storage-vm`):
- Modify: `scripts/maintenance_apply.py` (`execute`, CLI)
- Create: `scripts/bpg_env.sh`
- Modify: `.github/workflows/validate-and-plan.yml`, `.github/workflows/apply.yml`, `.github/workflows/drift.yml`
- Modify: `scripts/tests/test-maintenance-workflow.py`
- Create: `scripts/tests/test-storage-ci.py`
- Modify: `scripts/tests/test-storage-root.py`
- Modify: `CLAUDE.md` (What runs live, Commands, Contracts)
- Audit fold-in (Step 8a): Modify `scripts/check_clone_source.py`, `storage/main.tf` (root disk comment only),
  `scripts/tests/test-rebuild-cohort.py`; Create `scripts/tests/tf_offline.py`, `scripts/tests/test-clone-source.py`
- D16 rework (Step 9a): Create `scripts/storage_template_env.sh`; Modify `scripts/check_clone_source.py`,
  `scripts/maintenance_apply.py`, `storage/variables.tf`, the storage steps of `validate-and-plan.yml` and `drift.yml`,
  `CLAUDE.md`, and `scripts/tests/{test-clone-source,test-maintenance-workflow,test-storage-root,test-storage-ci}.py`

**Interfaces:**
- Consumes: `check_clone_source.main(vmid) -> 0|1` (T `scripts/check_clone_source.py:14-24`); W's
  `csi_wwn_guard.scsi_updates` and the `terraform show -json plan.tfplan` call inside `execute`; secrets
  `PM_API_URL`, `PM_API_TOKEN_ID`, `PM_API_TOKEN_SECRET`, `S3_*`, var `TF_VAR_SSH_PUB_KEY` (names only).
- Produces:
  - `execute(mode, saved_plan, root=Path('/maintenance'), workdir=None)`; CLI `--chdir DIR`. `root` keeps meaning the
    lock root.
  - `scripts/bpg_env.sh`, sourced, exporting `PROXMOX_VE_ENDPOINT`, `PROXMOX_VE_API_TOKEN`, `PROXMOX_VE_INSECURE=true`
    and `TF_VAR_ssh_pub_keys`. `PROXMOX_VE_INSECURE` matches `storage/providers.tf:27` (`insecure = true`); without it
    `check_clone_source.py:17` verifies pve's certificate, which the repo treats as untrusted.
  - S3 objects `pr-<n>/storage/plan.tfplan` and `pr-<n>/storage/plan.exitcode`.
  - apply step id `apply-storage`, writing `changed=` only. The `apply` job's `has_changes` output stays
    `${{ steps.apply.outputs.has_changes }}`.
  - Step 9a (D16): `scripts/storage_template_env.sh`, sourced, exporting `TF_VAR_storage_template_vmid` (the manifest
    `storage` entry's `artifact_id`) and `TF_VAR_storage_template_name` (its `custom_data.vm_name`); the variable
    `storage_template_name`; `check_clone_source.main(vmid, root_disk=None, name=None)`, which Task 5.13 reuses for k3s.

- [ ] **Step 1: Write the failing tests for `--chdir`** in `scripts/tests/test-maintenance-workflow.py`, class
  `WorkflowTests`. Make the fake `run_command` record `(kwargs.get('cwd'), args)`, and add:
  - `test_chdir_runs_in_the_root_and_never_dispatches`: write `storage/plan.tfplan` and `storage/plan.exitcode`
    (`2`), then call `execute('normal', True, self.lock, workdir='storage')`:
    ```python
    self.assertTrue(all(cwd == 'storage' for cwd, a in self.calls if a[0] == 'terraform'))
    self.assertIn(('storage', ['terraform', 'apply', 'plan.tfplan']), self.calls)
    out = dict(l.split('=', 1) for l in self.output.read_text().splitlines())
    self.assertEqual(out, {'changed': 'true'})   # no has_changes, no drained_nodes
    self.assertFalse((self.lock / 'operation.json').exists())
    ```
  - `test_chdir_refuses_other_modes_before_lock`: for `drain` and `destroy`, and for `normal` with
    `saved_plan=False`, `execute(..., workdir='storage')` raises `ValueError`, and `self.commands == []` with no
    `operation.json`.
  - `test_chdir_reads_its_own_plan_files`: `storage/plan.exitcode` missing while a root `plan.exitcode` (`2`)
    exists raises `ValueError('PR plan or its successful exit status is missing')`.
  - `test_clone_check_runs_only_for_a_create`: patch `maintenance_apply.check_clone_source.main`. Let the fake
    `terraform show -json` return a plan whose `resource_changes` has
    `{'type': 'proxmox_virtual_environment_vm', 'change': {'actions': ['delete', 'create']}}` and
    `variables.storage_template_vmid.value == 902`:
    ```python
    main.assert_called_once_with(902)
    ```
    With actions `['update']` or `['no-op']`, `main` is not called.
  - `test_missing_clone_source_refuses_before_apply`: `main` returns 1, so `SystemExit` names `902`. No
    `terraform apply` is in `self.commands`, and the lock is released (as W's refusal does).
  - `test_clone_check_error_releases_lock`: patched `main` raises `ssl.SSLError` (and, in a second case,
    `urllib.error.URLError`). The call raises `SystemExit` naming `902`, no `terraform apply` is in `self.commands`,
    and the lock is released. Nothing has changed yet, so a failed check must not leave a held lock.
  - Update `WiringTests.test_only_one_mutating_job_and_download_failure_cannot_reach_it`. There are now exactly two
    `maintenance_apply.py` steps, both in job `apply`. The second has id `apply-storage`, runs after the first, and its
    `if` equals the download step's `if`. Each `if` is evaluated with the existing `eval` pattern.
- [ ] **Step 2: Run**
  `cd $T && PYTHONPATH=$H/scripts $PY scripts/tests/test-maintenance-workflow.py`.
  Expected: FAIL (`execute() got an unexpected keyword argument 'workdir'`, and the wiring count is 1).
- [ ] **Step 3: Implement `--chdir`** in `scripts/maintenance_apply.py`. Behaviour:
  - `workdir` set and (`mode != 'normal'` or not `saved_plan`): `raise ValueError('--chdir applies a saved plan in
    normal mode only')` before `acquire`.
  - Plan files are read from `Path(workdir or '.')`. Every `subprocess.run` gets `cwd=workdir`. No `-chdir=` argument;
    W's two reads pass `capture=True` (Task 1.4 Step 2a), so `cwd` changes nothing else about them.
  - Lock operation `'terraform-' + (workdir + '-' if workdir else '') + mode` (`terraform-storage-normal`). It is the
    same helper and the same lock.
  - Keep the parsed `terraform show -json` document that W's guard reads. If any `resource_changes[]` has type
    `proxmox_virtual_environment_vm` and `'create'` in its actions, call
    `check_clone_source.main(int(doc['variables']['storage_template_vmid']['value']))` as
    `try: ok = check_clone_source.main(vmid) == 0` / `except Exception: ok = False`. When not ok, `release(...)`,
    then `raise SystemExit('Refusing apply: clone source <vmid> is missing, not a template, or unreadable')`. Only this
    check is wrapped: no blanket `try/finally`, because a failed mutation keeps the lock. This
    happens before `advance(..., 'acquired', 'applying')`. The VMID comes from the saved plan, not from the checkout,
    because no HCL parser exists in the container and the checkout commit is UNVERIFIED.
  - Output: with `workdir`, write only `changed=<true|false>`; without it, keep `has_changes=` and `drained_nodes=`
    as today.
  - CLI: `parser.add_argument('--chdir')`, passed as `workdir`.

  Run Step 2 again. Expected: PASS except the wiring test (the workflow is not edited yet).
- [ ] **Step 4: Write the failing tests for the workflows** in a new `scripts/tests/test-storage-ci.py` (stdlib,
  PyYAML, `sh`, `jq`; model: `WiringTests` and ansible `scripts/tests/test_deploy_lock.py`, which executes step
  scripts against fakes). Run each step script with `sh -e -c`, not bash: the `hashicorp/terraform` image has no
  bash until the S3 step installs it, and `drift.yml` never installs it.
  - `test_bpg_env_maps_existing_secrets`: run `sh -c '. scripts/bpg_env.sh; env'` with
    `PM_API_URL=https://192.0.2.5:8006/api2/json`, `PM_API_TOKEN_ID=ci@pve!t`, `PM_API_TOKEN_SECRET=s` and
    `TF_VAR_ssh_pub_key` holding two key lines:
    ```python
    self.assertEqual(env['PROXMOX_VE_ENDPOINT'], 'https://192.0.2.5:8006/')
    self.assertEqual(env['PROXMOX_VE_API_TOKEN'], 'ci@pve!t=s')
    self.assertEqual(json.loads(env['TF_VAR_ssh_pub_keys']), [KEY1, KEY2])
    self.assertEqual(env['PROXMOX_VE_INSECURE'], 'true')
    self.assertNotIn('s', run.stderr.split())   # never echoes, no set -x
    ```
    The URL without `/api2/json` gives the same endpoint, and an empty key variable exits non-zero.
  - `test_k3s_plan_prefix_unchanged`: the k3s upload destination ends in `/pr-${{ github.event.pull_request.number }}/`
    with sources `plan.tfplan` and `plan.exitcode`, and the apply download source is still that prefix, recursive.
    This keeps the old and new workflows compatible across the 2.1a merge.
  - `test_storage_plan_skips_without_tfvars`: run the `Create storage root plan` step script in a temp copy with a fake
    `terraform` on `PATH` (it records its argv and exits as told) and no `storage/terraform.tfvars`. Expected: exit 0,
    `planned=false` in `GITHUB_OUTPUT`, a line `storage root has no terraform.tfvars: not planned` in `plan.log`,
    `terraform -chdir=storage validate` was called, and `terraform ... plan` was not.
  - `test_storage_plan_uploads_to_its_own_prefix`: with tfvars and fake exit 2, the script writes `planned=true` and
    `storage/plan.exitcode` = `2`. The upload step has `if: steps.storage-plan.outputs.planned == 'true'` and
    destination `.../pr-${{ github.event.pull_request.number }}/storage/`. Fake exit 1 fails the step.
  - `test_one_root_per_pr`: with root `plan.exitcode` = `2` and storage exit 2, the step fails with
    `changes both the k3s root and the storage root`. Every other combination passes.
  - `test_storage_apply_never_dispatches`: the `apply` job's outputs reference only `steps.apply`.
    `trigger-ansible` contains neither `apply-storage` nor `changed`. The `apply-storage` run calls
    `maintenance_apply.py --mode normal --saved-plan --chdir storage`.
  - `test_storage_apply_skips_only_when_unconfigured`: run the `apply-storage` script with a fake `python3`.
    - Without tfvars and without `storage/plan.exitcode`: exit 0, prints `storage root not configured`, no call.
    - With `storage/plan.exitcode` present: `maintenance_apply.py` is called.
  - `test_missing_storage_plan_refused_before_any_mutation`: the step `Require the storage plan` sits after the
    download and before the first `maintenance_apply.py` step, with the download step's `if`. Its script exits 1
    with `storage/terraform.tfvars exists but the PR has no storage plan; re-run the PR plan` when tfvars exist and
    `storage/plan.exitcode` does not, and exits 0 otherwise. This case is reachable: a PR last planned before 2.1b
    merged and merged after it. Refusing first keeps the k3s step from applying and then losing its dispatch to a
    failed storage step.
  - `test_drift_covers_storage`: the drift `check` job has a step id `storage-plan` after `plan`, and job output
    `drift_detected` is `${{ steps.plan.outputs.drift == 'true' || steps.storage-plan.outputs.drift == 'true' }}`.
    The summary and upload conditions use the same combined value. Parse `drift.yml`: `TF_VAR_ssh_pub_key` maps to
    `${{ vars.TF_VAR_SSH_PUB_KEY }}` in the `storage-plan` step env or the job env (today it is only in the
    `Check for drift` step env, `drift.yml:38-41`). Assert the same for the `validate-and-plan.yml` `storage-plan` step.
    Run the step script with only the env the workflow gives that step (job env plus step env, `PM_*` faked): no tfvars
    gives `drift=false` and exit 0; fake exit 2 gives `drift=true` and appends `## storage root` to `drift.log`.
  - `test_no_base_image_var_reaches_storage`: no step whose `run` contains `-chdir=storage` or `--chdir storage` has
    `TF_VAR_base_vm_name` in its step env.
  - `test_storage_files_removed`: the `Remove saved plan` steps in both workflows remove `storage/plan.tfplan` and
    `storage/plan.exitcode`.
- [ ] **Step 5: Add the base-image test** to `scripts/tests/test-storage-root.py`:
  `test_base_image_change_leaves_storage_untouched`.
  ```python
  self.assertNotIn('base_vm_name', self.created['configuration']['root_module'].get('variables', {}))
  for source in STORAGE.glob('*.tf'):
      self.assertNotIn('packer-manifest', source.read_text())
  # plan with TF_VAR_base_vm_name=new-template set in the environment
  self.assertEqual(actions(doc), {VM: ['no-op'], GENERATION: ['no-op']})
  ```
  This needs `plan()` to accept an extra env (add a keyword argument to `run`). Also replace `test_pool_is_lab_only`
  with `test_no_pool_id` here if Task 0.1 has not done it yet (outline 0.1).
- [ ] **Step 6: Run**
  `cd $T && $PY scripts/tests/test-storage-ci.py && $PY scripts/tests/test-storage-root.py`.
  Expected: FAIL (no `bpg_env.sh`, no storage steps). `test_base_image_change_leaves_storage_untouched` already
  passes; it pins the current structure.
- [ ] **Step 7: Implement.**
  - `scripts/bpg_env.sh`, POSIX `sh` (no bashisms), sourced. It sets
    `PROXMOX_VE_ENDPOINT="${PM_API_URL%/api2/json}"`, adding a trailing `/` if missing, and
    `PROXMOX_VE_API_TOKEN="$PM_API_TOKEN_ID=$PM_API_TOKEN_SECRET"` (bpg's `user@realm!id=secret` form) and
    `PROXMOX_VE_INSECURE=true` (the provider's `insecure = true`; the clone check reads it). It sets
    `TF_VAR_ssh_pub_keys` to a JSON list of the non-empty lines of `$TF_VAR_ssh_pub_key`, built by
    `python3 -c 'import json,sys; print(json.dumps([l for l in sys.stdin.read().splitlines() if l.strip()]))'`, and
    fails when that list is empty. No `set -x` and no echo. The real `PM_API_URL` shape is UNVERIFIED; it is a secret.
    Stripping is a no-op when the suffix is absent.
  - `validate-and-plan.yml`, job `validate-and-plan`:
    - Before the S3 step, add `apk add --no-cache python3 jq`. Keep W's python install if it is already there.
    - After the k3s plan step (which runs W's guard since Task 1.4 Step 2a), add a step `Create storage root plan`,
      id `storage-plan`, with env
      `TF_VAR_ssh_pub_key: ${{ vars.TF_VAR_SSH_PUB_KEY }}`. Its script:
      1. `. scripts/bpg_env.sh`;
      2. `terraform -chdir=storage init -input=false` and `terraform -chdir=storage validate`;
      3. without `storage/terraform.tfvars`, append the skip line, write `planned=false` and re-encode
         `plan.log.b64`;
      4. otherwise run `terraform -chdir=storage plan -no-color -input=false -detailed-exitcode -out=plan.tfplan` into
         `storage/plan.log`, write `storage/plan.exitcode`, append `## storage root` and the log to `plan.log`,
         re-encode `plan.log.b64` and write `planned=true`;
      5. fail on exit 1, or when root `plan.exitcode` and storage exit are both 2.
    - Add a second `./.github/actions/s3-cp` upload with that `if` and destination `pr-<n>/storage/`.
    - Extend `Remove saved plan from the runner workspace`.
  - `apply.yml`, job `apply`:
    - After the download step, add `Require the storage plan` (the check in
      `test_missing_storage_plan_refused_before_any_mutation`).
    - After `Acquire ownership and execute infrastructure operation` (id `apply`), add `Apply the storage root`, id
      `apply-storage`, with
      `if: env.APPLY_MODE != 'destroy' && github.event_name == 'pull_request_target'` (the download step's
      condition, so dispatch and destroy applies never touch `storage/`).
    - Its script: if neither `storage/terraform.tfvars` nor `storage/plan.exitcode` exists, print
      `storage root not configured: nothing to apply` and exit 0. Otherwise source `scripts/bpg_env.sh` and run
      `python3 scripts/maintenance_apply.py --mode normal --saved-plan --chdir storage`.
    - `TF_VAR_ssh_pub_key: ${{ vars.TF_VAR_SSH_PUB_KEY }}` is already in the `apply` job env (T `apply.yml:105-117`).
    - Extend `Remove saved plan from the runner workspace` with the storage files.
    - Leave `trigger-ansible` and the job outputs unchanged.
  - `drift.yml`, job `check`:
    - Add `apk add --no-cache python3`.
    - After `Check for drift`, add `Check the storage root for drift`, id `storage-plan`, with step env
      `TF_VAR_ssh_pub_key: ${{ vars.TF_VAR_SSH_PUB_KEY }}` (the job env has only `PM_*` and `AWS_*`). Its script:
      without tfvars write `drift=false` and stop, before sourcing anything; otherwise source `bpg_env.sh`, then
      `terraform -chdir=storage init` and
      `plan -detailed-exitcode -no-color -input=false`. Exit 2 gives `drift=true` and appends `## storage root` and
      the log to `drift.log`; then re-encode `drift.log.b64`.
    - Point `outputs.drift_detected`, the summary `if` and the upload `if` at the combined value.
  - `CLAUDE.md`:
    - "What runs live": a PR may change one root; `storage/` applies in normal mode from its saved plan, never on
      dispatch or in destroy mode, and never dispatches ansible.
    - Commands: `test-storage-ci.py`.
    - Contracts: bpg reads `PROXMOX_VE_*` mapped from the `PM_*` secrets in `scripts/bpg_env.sh`.
  - `validate-and-plan.yml` job `maintenance-tests`: add `run: python3 scripts/tests/test-storage-ci.py`. The job
    already installs PyYAML; `jq` and `bash` are on `ubuntu-latest`.
- [ ] **Step 8: Run** Step 2, Step 6, `$TERRAFORM fmt -check -recursive .` and
  `$TERRAFORM -chdir=storage init -backend=false -plugin-dir=$STORAGE_PLUGIN_DIR && $TERRAFORM -chdir=storage validate`,
  then `$PY scripts/tests/test-rebuild-cohort.py`. Expected: PASS, with `14 offline real-provider planning checks
  passed`. Remove `storage/.terraform` and `storage/.terraform.lock.hcl` afterwards; never commit them.
- [ ] **Step 8a: Audit fold-in** (TDD; D49, genericity audit "terraform `storage-vm`").
  - Root disk tied to the template (finding 1, medium). The audit's preferred fix, packer writing the size and pool
    into the manifest for terraform to read, is not taken: Step 5 pins that no `storage/*.tf` reads
    `packer-manifest.json`, and CI passes only the template's VMID and name from it (Step 9a, D16). The template on
    pve is the source of truth for its disk, and the clone check already reads it at create:
    - Tests first. In `test-maintenance-workflow.py`, extend `test_clone_check_runs_only_for_a_create`: the fake
      plan's create carries `change.after.disk` with `virtio0` (`local-zfs`, `4`), and `main` is called as
      `main(902, ('local-zfs', 4))`. New `scripts/tests/test-clone-source.py` (stdlib, `urllib.request.urlopen`
      patched): a template whose config has `virtio0: local-zfs:base-902-disk-0,size=4G` passes for
      `('local-zfs', 4)`; `('local-zfs', 8)` and `('local-lvm', 4)` return 1 and print both values; a config without
      `virtio0` returns 1; `main(902)` with no disk behaves as today.
    - Implement `main(vmid, root_disk=None)`: after the template check, when `root_disk` is set, read
      `/nodes/<node>/qemu/<vmid>/config` (`node` from the same `cluster/resources` row), compare `virtio0`'s storage
      and `size=` in GiB, and on a mismatch print `clone source <vmid> root disk <storage>:<size>G, plan wants
      <storage>:<size>G` and return 1. `execute()` passes the planned `virtio0` `(datastore_id, size)`. The
      `storage/main.tf:77-79` comment says the create checks it.
    - UNVERIFIED: that `qm config 902` shows the root disk as `virtio0` with `size=4G` (P `source-base.pkr.hcl:50-53`
      sets `disk_size = "4G"`; the bus is not checked), and that the token's audit right covers the config read. Task
      3.3 Step 4's `qm config 902` settles both; until then the fixture is the assumption.
  - Low findings:
    - `check_clone_source.py` had no caller: Step 3 above is its caller. Nothing more.
    - One offline harness. `scripts/tests/tf_offline.py` `prepare(src, dst)` copies `*.tf` and writes
      `zz_offline_override.tf` with `terraform { backend "local" {} }` in place of the regex removal of `backend "s3"`,
      and inits normally in the temp copy (no `-backend=false`; the local state stays there)
      (`test-storage-root.py:59-61`, `test-rebuild-cohort.py:72-74`). Provider settings come from env, not from
      rewriting `provider "proxmox"`: bpg `PROXMOX_VE_ENDPOINT=https://127.0.0.1:1/`,
      `PROXMOX_VE_API_TOKEN=offline@pve!test=00000000-0000-0000-0000-000000000000`, `PROXMOX_VE_INSECURE=true`;
      telmate `PM_API_URL`, `PM_API_TOKEN_ID`, `PM_API_TOKEN_SECRET`, `PM_TLS_INSECURE=true`. If a provider block sets
      an attribute from a variable, pass that variable with `-var` instead; no regex stays. Both `setUpClass`/`main()`
      call it.
    - Narrow the source-text greps, do not drop them: `test_root_is_independent` (`test-storage-root.py:218-221`)
      matches `^\s*(source|path|config)\s*=\s*"[^"]*storage` and `data\s+"terraform_remote_state"`, not the bare word;
      `test_no_pool_id` (`:205-208`) matches `^\s*pool_id\s*=` and `variable "pool_id"`. Each gets a fixture case: a
      `source = "../storage"` line and a `terraform_remote_state` block are caught, a comment naming `storage/` is not.
  - Add `python3 scripts/tests/test-clone-source.py` to the `validate-and-plan.yml` job `maintenance-tests`.
  - Run: Step 2, Step 6, `$PY scripts/tests/test-clone-source.py` and `$PY scripts/tests/test-rebuild-cohort.py`.
    Expected: PASS, with `14 offline real-provider planning checks passed`.
- [ ] **Step 9: Commit** (one commit per concern, in this order):
  1. `feat(storage): apply a saved plan in another root with --chdir, checking the clone source`
  2. `ci(storage): plan, apply and drift-check the storage root from its own S3 prefix`
  3. `feat(storage): the clone check compares the template's root disk with the plan`
  4. `test(storage): one offline plan harness for both roots`

  Both end with the Co-Authored-By line.
- [ ] **Step 9a: D16 rework** (follow-up on T `feat/retained-storage-vm`, on top of `5a31da8`; Ben, 2026-11-23).
  The storage root takes its template from the `storage` entry of `packer-manifest.json`, the k3s way. bpg clones by
  VMID, so `storage_template_vmid` comes from the entry's `artifact_id`; the new variable `storage_template_name` comes
  from its `custom_data.vm_name`. CI sets both; no tfvars does. The VM keeps `ignore_changes = [clone, startup]`, so
  the entry matters only at a create or a generation rebuild. Packer delivers the entry from Task 2.11 Step 4a on.
  - The commit must stand on `ci/storage-root` (Step 10), which has neither 2.1b's nor 2.1d's commits: no `jq` in the
    plan or drift job, no `K3S`/`OLD`/`STORAGE` fixtures, `DISKS` without `serial`. So it brings its own fixtures and
    `jq`, and keeps off the lines those commits changed (`git -C $T show 6ed0579 e5e5f7e 24f0c2a 5a31da8`).
  - Tests first (902 stays only as the fixture's template VMID):
    - `test-clone-source.py`, class `CloneSourceRootDisk` (fixture template `name='storage-template'`): `check()`
      passes keyword arguments through to `main(902, *args, **kwargs)`.
      - `test_matching_name_passes`: `main(902, ('local-zfs', 4), name='storage-template')` returns 0 and prints
        `clone source 902 is a template named storage-template`.
      - `test_name_mismatch_prints_both_names`: `name='packer-storage-other'` returns 1, prints
        `clone source 902 is named storage-template, plan wants packer-storage-other`, and
        `urls == ['/api2/json/cluster/resources?type=vm']` (it refuses before the config read).
      - `test_no_root_disk_reads_only_resources` stays: `main(902)` with no name prints
        `clone source 902 is a template`, as the CLI test `test-check-clone-source.py` expects.
    - `test-maintenance-workflow.py`:
      - `storage_vm()`: `variables` gains `'storage_template_name': {'value': 'packer-storage-13.7.0-1'}`.
      - `test_clone_check_runs_only_for_a_create`:
        `main.assert_called_once_with(902, ('local-zfs', 4), name='packer-storage-13.7.0-1')`.
      - `test_unreadable_clone_inputs_refuse_and_release_lock` gains two cases, `no storage_template_name` (the key
        deleted) and `empty storage_template_name` (value `''`). Each refuses with `Refusing apply: clone source` and
        releases the lock while the patched `main` returns 0 (`name=None` would skip the name check, so a missing or
        empty name must refuse on its own).
    - `test-storage-root.py`:
      - `FIXTURE` gains `storage_template_name='packer-storage-13.7.0-1'` on its last line (after `generation='1'`),
        not its first: the first line's diff context holds 2.1b's `DISKS` change.
      - `test_template_change_is_noop`: `-var=storage_template_vmid=903` plus
        `-var=storage_template_name=packer-storage-13.7.0-2` still gives `{VM: ['no-op'], GENERATION: ['no-op']}`.
        Every packer build renames the template, so without this every manifest PR would trip the one-root-per-PR
        check.
      - `test_template_name_in_saved_plan`: `self.created['variables']['storage_template_name']['value'] ==
        'packer-storage-13.7.0-1'`. `maintenance_apply.py` reads it there; an unreferenced variable is still in
        `terraform show -json` `variables` (checked offline with terraform 1.17.2, 2026-11-23).
      - `test_template_name_validated`: `-var=storage_template_name=` and `-var='storage_template_name=bad name'`
        each fail `plan`.
    - `test-storage-ci.py`:
      - New constants after `FAKE_PM`: `TEMPLATE = {'name': 'storage', 'artifact_id': '902', 'custom_data':
        {'vm_name': 'packer-storage-13.7.0-1'}}` and `OTHER = {'name': 'k3s', 'artifact_id': '901', 'custom_data':
        {'vm_name': 'packer-k3s-13.7.0-1'}}`. `Sandbox(..., tfvars=True)` also writes `packer-manifest.json` as
        `{'builds': [OTHER, TEMPLATE]}` (keyword `manifest=`, `None` writes none). The fake `terraform` writes
        `$TF_VAR_storage_template_vmid $TF_VAR_storage_template_name` to `$CALLS.vars` on `plan`.
      - `test_storage_template_env`: in a Sandbox, the script `. scripts/storage_template_env.sh; env`:
        - `[OTHER, TEMPLATE]` prints `TF_VAR_storage_template_vmid=902` and
          `TF_VAR_storage_template_name=packer-storage-13.7.0-1`;
        - two `storage` entries: the last one's values;
        - no `storage` entry, `artifact_id` missing or `'abc'`, or `vm_name` missing: non-zero exit, and no
          `TF_VAR_storage_template_` line.
      - `test_storage_plan_reads_manifest_only_with_tfvars`, on the `storage-plan` step script:
        - no tfvars, `manifest=None`: exit 0 and `planned=false` (Task 3.3's state: main has no `storage` entry yet);
        - tfvars and `[OTHER]`: non-zero exit, no `-chdir=storage plan` call, no `planned=` output;
        - tfvars and the full manifest: `calls.vars` reads `902 packer-storage-13.7.0-1`.
      - `test_drift_reads_manifest_only_with_tfvars`: the same three cases on the drift `storage-plan` step, with
        `drift=false` for the first.
      - `test_no_base_image_var_reaches_storage` gains the converse: the steps `Create Terraform plan`,
        `Check for drift` and `Acquire ownership and execute infrastructure operation` never mention
        `storage_template`.
  - Run:
    `cd $T && PYTHONPATH=$H/scripts $PY scripts/tests/test-maintenance-workflow.py; $PY scripts/tests/test-clone-source.py;
    $PY scripts/tests/test-storage-ci.py; $PY scripts/tests/test-storage-root.py`.
    Expected: FAIL (`main() got an unexpected keyword argument 'name'`, no `scripts/storage_template_env.sh`,
    `Value for undeclared variable` `storage_template_name`).
  - Implement:
    - `scripts/check_clone_source.py`: `main(vmid, root_disk=None, name=None)`. After the template row is found and
      before any config read: when `name is not None and row.get('name') != name`, print
      `clone source <vmid> is named <row name>, plan wants <name>` to stderr and return 1. The success line becomes
      `clone source <vmid> is a template`, plus ` named <name>` when `name` is given. Update the docstring. The CLI
      stays `main(int(sys.argv[1]))`.
    - `scripts/maintenance_apply.py`, the create branch, inside the existing `try`:
      `name = plan['variables']['storage_template_name']['value']` and
      `ok = root_disk is not None and bool(name) and check_clone_source.main(vmid, root_disk, name=name) == 0`. The
      refusal becomes `Refusing apply: clone source <vmid> is missing, not a template, misnamed or unreadable, or the
      plan lacks its template VMID, template name or virtio0 root disk`.
    - `storage/variables.tf`: `variable "storage_template_name"`, `type = string`, description `"PVE name of the
      template at storage_template_vmid (the manifest's storage entry); only the clone check reads it"`, validation
      `can(regex("^[A-Za-z0-9.-]+$", var.storage_template_name))`. `storage_template_vmid`'s description becomes
      `"VMID of the Packer storage template (the manifest entry's artifact_id); ignored after creation"`. Neither text
      may contain the literal `packer-manifest` (Step 5's grep).
    - `scripts/storage_template_env.sh`, POSIX `sh`, sourced, no echo:
      ```sh
      # The storage entry of packer-manifest.json, by name as the k3s steps read theirs. Plain assignments, then export:
      # `export X=$(...)` would hide jq's exit status from sh -e.
      entry=$(jq -ec '[.builds[] | select(.name=="storage")] | last' packer-manifest.json)
      TF_VAR_storage_template_vmid=$(printf '%s' "$entry" | jq -er '.artifact_id | tonumber')
      TF_VAR_storage_template_name=$(printf '%s' "$entry" | jq -er '.custom_data.vm_name')
      export TF_VAR_storage_template_vmid TF_VAR_storage_template_name
      ```
      With no match `last` is `null`, so `jq -e` exits 1 and the sourcing step fails.
    - `validate-and-plan.yml` `Create storage root plan`: `apk add --no-cache jq` and
      `. scripts/storage_template_env.sh` right after the no-tfvars `exit 0` block, before
      `terraform -chdir=storage plan`. `drift.yml` `Check the storage root for drift`: its `apk add --no-cache python3`
      becomes `apk add --no-cache python3 jq`, and the source line goes right after `. scripts/bpg_env.sh`. The steps
      install `jq` themselves: before 2.1d no job step does. A missing `storage` entry while
      `storage/terraform.tfvars` exists fails the step (fail closed).
    - `apply.yml`: no change. The saved plan carries both values.
    - `CLAUDE.md` Contracts, a new bullet right after `Proxmox credentials` (not next to `Image ← packer`, which 2.1d
      rewrites): "Storage template ← packer: the `storage` entry of `packer-manifest.json`
      (`scripts/storage_template_env.sh`); the clone check refuses when the template at that VMID is missing, has
      another name or another root disk".
  - Run: the four tests above, `$TERRAFORM fmt -check -recursive .` and `$PY scripts/tests/test-rebuild-cohort.py`.
    Expected: PASS, `14 offline real-provider planning checks passed`, except `StorageRoot.test_production_tfvars`
    (`No value for required variable` `storage_template_name`), which Task 2.1b Step 5a fixes.
  - Commit `feat(storage): take the storage template from the packer manifest, checked by name (D16)`.
- [ ] **Step 10: PR (only when Ben asks; merged in Task 3.3 Step 2, before the freeze).**
  - T's 2.1a commits are the prefix of its stack up to `fix(storage): fail closed on missing clone-check inputs and
    drop stale storage plans` (`e51275b`); 2.1d's, 2.1b's and Step 9a's follow. Pick that prefix, then Step 9a's two
    commits (`c1f3adf` and its review fix `f154ddd`). Two picks: one `cherry-pick` with a range and a SHA after it
    reads the SHA as a second range end and picks nothing more.
    ```sh
    git -C $T fetch origin
    END=$(git -C $T log feat/retained-storage-vm --format=%H -1 --grep '^fix(storage): fail closed on missing clone-check')
    D16=$(git -C $T log feat/retained-storage-vm --format=%H -1 --grep '^feat(storage): take the storage template from')
    FIX=$(git -C $T log feat/retained-storage-vm --format=%H -1 --grep '^fix(storage): the manifest storage VMID must be')
    git -C $T switch -c ci/storage-root origin/main && g -C $T cherry-pick origin/main..$END && g -C $T cherry-pick $D16 $FIX
    ```
    A conflict is a stop: `git -C $T cherry-pick --abort` and bring it to Ben.
  - Check: `git -C $T diff --name-only $END ci/storage-root` equals the sorted union of
    `git -C $T show --name-only --format= $D16 $FIX`;
    the four Step 9a test files pass on `ci/storage-root` (Step 9a's Run, with no `test_production_tfvars` there);
    `git -C $T grep -n pool_id -- storage/`
    finds nothing, `git -C $T ls-tree ci/storage-root storage/terraform.tfvars` prints nothing (a tfvars here would
    make this PR the create), and `$PY scripts/tests/test-storage-root.py StorageRoot.test_no_pool_id` passes on
    `ci/storage-root`.
  - `git -C $T push -u origin ci/storage-root`, then
    `gh pr create --title "ci: plan and apply the storage VM root (no-op for k3s)"`.
  - The PR body must not contain any skip pattern from Global Constraints.
  - Expected plan comment: the k3s plan shows `No changes.`; the storage leg shows the not-planned line.
  - Merge event: an apply of a no-op k3s plan, with no ansible dispatch (same as 1.4). The storage step either does
    not exist (old `apply.yml`) or prints `storage root not configured`.
  - **Ben OK** to merge. Evidence: the run URL and its log tail in `evidence/2.1a/`.

### Task 2.1b: terraform: production `storage/terraform.tfvars` (the create PR)

**Files** (worktree T):
- Create: `storage/terraform.tfvars`
- Modify: `scripts/tests/test-storage-root.py`
- Audit fold-in (Steps 1a, 3a): Modify `storage/variables.tf` (`data_disks` gains `serial`), `storage/main.tf` (the
  dynamic `disk` passes it), and the `DISKS` fixture in `scripts/tests/test-storage-root.py`

**Interfaces:**
- Consumes: D1 and D2 values (table above); the manifest `storage` entry through 2.1a Step 9a's
  `storage_template_env.sh` (D16; its `artifact_id` is packer's fixed `storage_vm_id` 902, P `variables.pkr.hcl:32-34`);
  the 3.4 `pvesm alloc` volume names.
- Produces: `storage/terraform.tfvars`, which becomes the storage root's plan input from the 2.1a CI path.

- [ ] **Step 1: Write the failing test** `test_production_tfvars` in `scripts/tests/test-storage-root.py`. It plans a
  second temp copy that holds `storage/terraform.tfvars` plus only `ssh_pub_keys=[KEY]` (no fixture file):
  ```python
  vm = planned(prod)
  self.assertEqual((vm['clone'][0]['vm_id'], vm['vm_id'], vm['name']), (902, <D1:storage_vmid>, '<D1:storage_name>'))
  self.assertIsNone(vm.get('pool_id')); self.assertEqual(vm['tags'], ['storage'])
  disks = {d['interface']: (d['datastore_id'], d['path_in_datastore'], d['size']) for d in vm['disk']}
  self.assertEqual(disks['virtio1'], ('k3s-block', '<D1:placeholder_vmid>/<retained_volname>', <D2:retained_gib>))
  self.assertEqual(disks['virtio2'], ('k3s-block', '<D1:placeholder_vmid>/<regen_volname>', <D2:regen_gib>))
  self.assertNotIn(<D1:placeholder_vmid>, (9999, 900, 901, 902, 200, 201, 202, 300, 100))
  self.assertEqual([c['ipv4'][0]['address'] for c in vm['initialization'][0]['ip_config']],
                   ['<D1:storage_lan_ip>/24', '<D1:storage_bridge_ip>/24'])
  self.assertEqual([n['bridge'] for n in vm['network_device']], ['vmbr0', 'vmbr2'])
  self.assertEqual(generation_input(prod), '1')
  ```
- [ ] **Step 1a: Write the failing serial checks** (audit fold-in, D49; genericity audit "ansible `storage-vm`"
  finding 3). In `test_production_tfvars`:
  `{d['interface']: d['serial'] for d in vm['disk'] if d['interface'] != 'virtio0'} == {'virtio1': 'retained',
  'virtio2': 'regen'}`. The fixture `DISKS` gains `serial='retained'` and `serial='regen'`. A fixture with a duplicate
  serial, an empty one or one over 20 characters fails `plan` on variable validation.
  - bpg 0.118.0 `disk` has an optional `serial` ("The drive's reported serial number"; read 2026-11-22 with
    `providers schema -json` against `$L/tf-plugin-cache`).
  - The guest then sees `/dev/disk/by-id/virtio-retained` and `/dev/disk/by-id/virtio-regen`, which Task 2.3 uses in
    place of the PCI by-path names. UNVERIFIED until Task 3.5 Step 1 (`ls -l /dev/disk/by-id/` on the storage VM):
    that Debian 13's udev names a virtio-blk serial `virtio-<serial>`.
- [ ] **Step 2: Run** `cd $T && $PY scripts/tests/test-storage-root.py`. Expected: FAIL (no
  `storage/terraform.tfvars`).
- [ ] **Step 3: Write `storage/terraform.tfvars`**:
  ```hcl
  vm_id                 = <D1:storage_vmid>
  name                  = "<D1:storage_name>"
  lan_ipv4              = "<D1:storage_lan_ip>/24"
  lan_gateway           = "<D35:lan_gateway>"
  storage_bridge        = "vmbr2"
  storage_ipv4          = "<D1:storage_bridge_ip>/24"
  nameserver            = "10.9.9.1"
  cloudinit_datastore   = "local-zfs"
  generation            = "1"
  data_disks = [
    {
      interface         = "virtio1"
      datastore_id      = "k3s-block"
      path_in_datastore = "<D1:placeholder_vmid>/<retained_volname>"
      size              = <D2:retained_gib>
      serial            = "retained"
    },
    {
      interface         = "virtio2"
      datastore_id      = "k3s-block"
      path_in_datastore = "<D1:placeholder_vmid>/<regen_volname>"
      size              = <D2:regen_gib>
      serial            = "regen"
    },
  ]
  ```
  - No `storage_template_vmid` or `storage_template_name`: CI takes both from the manifest (D16, Step 5a).
  - `<D35:lan_gateway>` is `10.9.9.1`, lab-qualified (`storage-lab/tf-storage/lab.auto.tfvars.json`; Ben, D35, 2026-11-23). `nameserver` is the root's value (T `terraform.tfvars`). `cores`, `memory` and `tags`
    keep their defaults; `pool_id` no longer exists (Task 0.1 Step 8).
  - Size and overcommit follow D2.
  - Error policy (D2 decided): the QEMU default. Set no `werror`/`rerror` and add no `qm set` side channel; bpg up to
    0.123.1 has no such keys (2026-11-23 schema and source read to 0.121.0; 2026-11-24 source read of 0.123.1).
- [ ] **Step 3a: Add the disk serial** (audit fold-in). `storage/variables.tf`: the `data_disks` object gains
  `serial = string`, validated non-empty, at most 20 characters and distinct across disks. `storage/main.tf`: the
  dynamic `disk` sets `serial = disk.value.serial`. It lands in this PR, before the create: a serial added later is an
  update of the running VM.
- [ ] **Step 4: Run** Step 2 and `$TERRAFORM fmt -check -recursive .`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): production storage VM tfvars (ADR 0017 Foundation 3)`.
- [ ] **Step 5a: D16 rework** (follow-up on T, after 2.1a Step 9a's commit; Steps 1-5 and `5a31da8` are done with
  `storage_template_vmid = 902` in the tfvars, which this step removes).
  - Test first, in `test_production_tfvars`:
    - `self.assertNotIn('storage_template', (STORAGE / 'terraform.tfvars').read_text())`;
    - `keys.auto.tfvars.json` holds only the CI-supplied keys: `ssh_pub_keys=[KEY]`, `storage_template_vmid=902`
      and `storage_template_name='packer-storage-13.7.0-1'` (what `storage_template_env.sh` gives for 2.1a's
      manifest fixture);
    - the clone assertion stays `(902, 101, 'storage-01')`, now fed by that key;
    - `prod['variables']['storage_template_name']['value'] == 'packer-storage-13.7.0-1'`.
    - New `test_production_tfvars_needs_the_manifest`: the same copy with only `ssh_pub_keys`. `plan` fails, and its
      output names `storage_template_vmid` and `storage_template_name` (`No value for required variable`).
  - Run `cd $T && $PY scripts/tests/test-storage-root.py`. Expected: FAIL (`storage_template` found in the tfvars).
  - Implement: delete the `storage_template_vmid = 902` line from `storage/terraform.tfvars`, then
    `$TERRAFORM fmt storage/terraform.tfvars` (the `=` column moves).
  - Run Step 4. Expected: PASS, `test_production_tfvars` included.
  - Commit `feat(storage): the production tfvars leave the template to the manifest (D16)`.
- [ ] **Step 6: PR (only when Ben asks; merged in Task 3.4 Step 3, after both `pvesm alloc` calls).**
  - `git -C $T fetch origin && git -C $T switch -c feat/storage-vm-create origin/main` (2.1a is merged by then),
    `g -C $T cherry-pick <Step 5 SHA> 5a31da8 <Step 5a SHA>` (`5a31da8`: `test(storage): derive the placeholder VMID
    from the planned disk path`; read the two SHAs with `git -C $T log feat/retained-storage-vm --format=%H -1 --grep`
    and each subject), then `git -C $T push -u origin feat/storage-vm-create`.
  - Before the push: `git -C $T show origin/main:packer-manifest.json | jq -e '[.builds[] | select(.name=="storage")]
    | last | .artifact_id == "902" and (.custom_data.vm_name | length > 0)'` prints `true` (Task 2.11 Step 4a's entry,
    merged in 3.3). Otherwise the PR's storage plan step fails closed: stop.
  - Title `feat: create the storage VM (ADR 0017)`; the body has no skip pattern.
  - Expected plan comment: k3s `No changes.`; storage `Plan: 2 to add, 0 to change, 0 to destroy` (the VM and
    `terraform_data.generation`).
  - Merge event: the k3s step applies nothing and dispatches nothing. Then `apply-storage` runs the clone check on the
    saved plan's VMID (902) and name, prints `clone source 902 is a template named <manifest storage vm_name>`, and
    creates the VM under the maintenance lock. There is no ansible dispatch.
  - **Ben OK** to merge. Evidence: the plan comment and the apply log tail in `evidence/3.4/`.

### Task 2.1c: terraform: worker `storage_nic` (D3)

**Files** (worktree T, topic branch `feat/storage-nic` off `origin/main`, so it cherry-picks onto a packer manifest
branch):
- Modify: `variables.tf`, `main.tf` (module `worker_nodes` only), `terraform.tfvars`
- Modify: `scripts/tests/test-rebuild-cohort.py`

**Interfaces:**
- Produces: `variable "storage_nic"`, type
  `object({ bridge = string, base_cidr = string, start_offset = number })`, default `null`. Workers get the NIC last:
  the next `netN` and `ipconfigN` after `network_interfaces` (`net2`/`ipconfig2` in production, with two
  interfaces), so `ipconfig0` stays ansible's address (T `CLAUDE.md`, Gotchas). `module "master_nodes"` never
  reads it. `modules/vm` needs no change: its `network` block loops over `network_bridges`, and it pads 16
  `ipconfigN` (origin/main `modules/vm/main.tf:2-4,38-64`).
- Consumes: `<D1:worker_bridge_start>`; bridge `vmbr2` from Task 3.1.

- [ ] **Step 1: Write the failing checks** in `test-rebuild-cohort.py` `main()`, after `'Packer image change'`, using
  `check()`:
  - `'storage NIC alone updates workers in place'`, with
    `-var=storage_nic={bridge="offline2",base_cidr="198.51.100.0/24",start_offset=21}`. Expected
    `dict(noop, **{w: ['update'] for w in WORKERS})`, master `no-op`. This is the wwn-strip shape, and why D3 folds it.
  - On that document: each worker's `after.network[-1].bridge == 'offline2'`, its earlier entries are unchanged, and
    `after.ipconfig1` is `'ip=198.51.100.21/24'` / `'ip=198.51.100.22/24'`. The cohort fixture has one interface
    (`bridge='offline'`), so the storage NIC is `net1`/`ipconfig1` there.
  - That telmate 3.0.2-rc10 plans an added `network` block as `['update']` and not as a replacement is UNVERIFIED
    until this check runs. If it plans a replacement, keep the observed value, and tell Ben before D3 is settled,
    because it changes the reason for folding.
  - `'storage NIC folded into an image change'`: the same var plus `-var=base_vm_name=new-template`. Expected
    `{node: ['delete', 'create'] for node in NODES}`.
  - `'storage NIC default is a no-op'`: the existing `'unchanged'` check already covers it once the variable exists.
    Keep it first.
  - Bump the final message to `16 offline real-provider planning checks`.
- [ ] **Step 2: Run** `cd $T && $PY scripts/tests/test-rebuild-cohort.py`. Expected: FAIL (`Value for undeclared
  variable "storage_nic"`).
- [ ] **Step 3: Implement.**
  - In `module "worker_nodes"`:
    - `network_bridges = concat(local.network_bridges, var.storage_nic == null ? [] : [var.storage_nic.bridge])`;
    - `ipconfigs = concat(local.worker_ipconfigs[count.index], var.storage_nic == null ? [] :
      ["ip=${cidrhost(var.storage_nic.base_cidr, var.storage_nic.start_offset + count.index)}/${split("/",
      var.storage_nic.base_cidr)[1]}"])`.

    Add no gateway: the subnet is never routed (ADR "Subnet").
  - `terraform.tfvars`:
    `storage_nic = { bridge = "vmbr2", base_cidr = "10.99.2.0/24", start_offset = <D1:worker_bridge_start> }`.
    Because the subnet is fixed forever, these addresses must equal ansible `storage_vm_workers` (Task 2.3).
- [ ] **Step 4: Run** Step 2 and `$TERRAFORM fmt -check -recursive .`. Expected: PASS, 16 checks.
- [ ] **Step 5: Commit** `feat(k3s): give the workers a storage-bridge NIC (apply only with a VM replacement)`.
  The message says, as `7dc633b` did, that this commit is applied only together with a VM replacement.
- [ ] **Step 6: Use (fold path, D3 = fold).** This step runs in Task 3.3 Step 6, not now. Cherry-pick the commit onto
  the packer `packer-build-<run>` branch, after the rebuilt manifest commit that 3.3 Step 6 makes; those two commits
  are the only changes on that branch, with no workflow edits. The workflow that plans it is the branch's own
  `validate-and-plan.yml`, which contains 2.1a.
  - Expected plan (read in 3.3 Step 7): every k3s VM `delete, create`, no `update`, so W's guard prints nothing. The
    storage leg prints `storage root has no terraform.tfvars: not planned` (2.1b is not merged yet).
- **Per-worker variant (D3 = ADR).** Add `storage_nic_workers` (a set of worker indexes, default empty). Workers
  outside it get no NIC. There are two PRs, `[0]` and then `[0, 1]`. Each one:
  - is planned as one worker `update`;
  - is merged with the wwn box ticked, after that worker is drained by hand;
  - is followed by the scripted `qm set <vmid> --scsiN ...,wwn=...` restore and a reboot (memory
    `terraform-apply-strips-csi-wwn`).

  Its test is `'storage NIC on one worker'`: `WORKERS[0]` `update`, the rest `no-op`.

### Task 2.1d: terraform: select the k3s image by name (PR in Task 3.3 Step 8)

**Files** (worktree T, branch `feat/retained-storage-vm`, after 2.1a's commits, which it edits; Step 6 cherry-picks
it onto the PR branch `ci/manifest-by-name`):
- Modify: `.github/workflows/apply.yml` (step `Prepare reviewed image and private kubeconfig`),
  `.github/workflows/validate-and-plan.yml` (steps `Read manifest file`, `Create Terraform plan`),
  `.github/workflows/drift.yml` (steps `Read manifest file`, `Check for drift`)
- Modify: `scripts/tests/test-storage-ci.py`, `CLAUDE.md` (Contracts: "only `builds[0]...` is read")
- Modify, in 3.3 only: `packer-manifest.json` (drop the `debian-13` entry)

**Interfaces:**
- Consumes: the manifest from packer `push-manifest` (P `.github/workflows/build.yml:151-154`), entries `k3s` and the
  old `debian-13`; from Task 2.11 Step 4a on, the same PR also carries the `storage` entry, which this selector skips
  and 2.1a Step 9a's `storage_template_env.sh` reads (D16; the fixtures hold one to prove order does not matter).
- Produces: `TF_VAR_base_vm_name` from `[.builds[] | select(.name=="k3s")] | last | .custom_data.vm_name`, the
  expression packer's own release step uses (P `build.yml:123`).

- [ ] **Step 1: Write the failing test** `test_manifest_selected_by_name` in `test-storage-ci.py`:
  ```python
  for wf in ('apply.yml', 'validate-and-plan.yml', 'drift.yml'):
      self.assertNotIn('builds[0]', text(wf))
  expr = JQ.search(text('drift.yml')).group(1)            # same string in validate-and-plan.yml
  self.assertEqual(jq(expr, [K3S, OLD, STORAGE]), K3S_NAME); self.assertEqual(jq(expr, [STORAGE, OLD, K3S]), K3S_NAME)
  self.assertNotEqual(jq_rc(expr, [OLD]), 0)               # a manifest without k3s fails loudly
  ```
  For `apply.yml`, run the step script in a temp dir with a fixture `packer-manifest.json`, fake `GITHUB_ENV`,
  `KUBECONFIG` and `KUBECONFIG_RAW`. Expected: `TF_VAR_base_vm_name=<k3s name>` in both orders, and a non-zero exit
  with only `debian-13`.
- [ ] **Step 2: Run** `cd $T && $PY scripts/tests/test-storage-ci.py`. Expected: FAIL (`builds[0]` present).
- [ ] **Step 3: Implement.**
  - `apply.yml`: in the heredoc,
    `name = next(b for b in json.loads(Path('packer-manifest.json').read_text())['builds'] if b['name'] ==
    'k3s')['custom_data']['vm_name']`. StopIteration fails the step.
  - `validate-and-plan.yml` and `drift.yml`: replace `Read manifest file` with a step that runs
    `apk add --no-cache jq` and appends `TF_VAR_base_vm_name=$(jq -er '<expr>' packer-manifest.json)` to
    `$GITHUB_ENV`. Drop the `fromJSON(env.manifest)` env lines.
  - `CLAUDE.md` Contracts: "the `k3s` entry of `packer-manifest.json` is read by name".
- [ ] **Step 4: Run** Step 2. Expected: PASS.
- [ ] **Step 5: Commit** `ci: read the k3s image from the manifest by name`.
- [ ] **Step 5a: D16 rework** (follow-up on T, after 2.1a Step 9a; it needs this task's `JQ` and `drift.yml` read, so
  it rides this PR, not 2.1a's).
  - Test first: `Shared.test_storage_template_read_like_k3s`. The k3s expression that `JQ` finds in `drift.yml`, minus
    its trailing ` | .custom_data.vm_name` and with `"k3s"` replaced by `"storage"`, appears in
    `scripts/storage_template_env.sh` (`[.builds[] | select(.name=="storage")] | last`). `STORAGE` gains
    `'artifact_id': '902'`.
  - Run `cd $T && $PY scripts/tests/test-storage-ci.py`. Expected: PASS at once (Step 9a wrote the same form); it
    pins the two reads together from now on.
  - Commit `test(storage): the storage template read matches the k3s one (D16)`. Done: `58b674f` (2026-11-23), with the
    pin as an equality, not a substring, and a mutation (`last` to `first`) that fails it.
- [ ] **Step 6: PR (in Task 3.3 Step 8, right after Step 7's rebuild apply finished, before any other terraform PR).**
  - `git -C $T fetch origin && git -C $T switch -c ci/manifest-by-name origin/main`, then
    `g -C $T cherry-pick <Step 5 SHA> e5e5f7e <Step 5a SHA>` (`e5e5f7e`: `ci: apply takes the last k3s manifest
    entry, like plan and drift`).
  - Add a second commit that deletes the `debian-13` object from `packer-manifest.json` (by name, with `jq`), with
    message `chore: drop the pre-split debian-13 manifest entry`.
  - Title `ci: select the k3s image by name`.
  - Expected plan comment: k3s `No changes.`, because the k3s name is the same one `builds[0]` gave; the storage leg
    prints the not-planned line (2.1b is not merged yet).
  - Merge event: a no-op apply, no dispatch. **Ben OK**. Evidence in `evidence/3.3/`.
  - Never merge it before the first three-build manifest PR: today's manifest has only `debian-13`
    (`origin/main:packer-manifest.json`), so the select would fail every plan.

### Task 2.2: ansible: storage workflows

**Files** (worktree A, branch `feat/retained-storage-vm`; ships in the Task 3.2 PR):
- Create: `.github/workflows/storage.yml`, `.github/workflows/storage-expiry.yml`
- Create: `storage-dry-run.yml` (playbook), `scripts/storage_ready.py`
- Create: `scripts/tests/test_storage_workflows.py`
- Modify: `.github/workflows/deploy.yml` (`paths-ignore`), `.github/workflows/validate.yml`
- Modify: `scripts/tests/test_storage_vm_role.py` (dry-run playbook checks)
- Audit fold-in (D49, genericity audit "ansible `storage-vm`"):
  - Create: `storage-play-lab-guard.yml`, `storage-play-fetch-inventory.yml`, `storage-play-cleanup.yml`;
  - Modify: `storage.yml`, `storage-expiry.yml` (import those plays), `roles/storage_vm/tasks/expire-volume.yml:55-57`;
  - Modify: `scripts/tests/test_storage_vm_role.py` (delete `WorkflowTests`, `:705-723`);
  - Modify: `scripts/tests/test_sealing_recovery.py`, `.github/workflows/csi-activation-preflight.yml` (Step 3).

**Interfaces:**
- Consumes:
  - the playbooks `storage.yml` and `storage-expiry.yml`, unchanged apart from the audit fold-in's imports;
  - `roles/storage_vm/tasks/{fetch-inventory,dry-run,lock-verify}.yml`;
  - the pinned helper `887269798650e88fed791bb4f22a47bf50ad17be` `scripts/maintenance_lock.py` (`acquire --operation X
    --github-env`, `verify`, `release`; `deploy.yml:56-62,93-105`);
  - secrets `PROXMOX_URL`, `PROXMOX_USER`, `PROXMOX_TOKEN_ID`, `PROXMOX_TOKEN_SECRET`, `SSH_PRIVATE_KEY`,
    `ANSIBLE_VAULT_PASSWORD` (names only, as in `deploy.yml:48-51,84-91`).
- Produces:
  - workflow `storage.yml`: concurrency group `storage-reconcile`, operation name `ansible-storage`;
  - workflow `storage-expiry.yml`: group `storage-expiry`, operation `ansible-storage-expiry`;
  - event `repository_dispatch: storage-changed` (payload ignored);
  - step outputs `ready` (id `ready`) and `acquired` (id `lock`);
  - `storage_ready.skip_reason(hosts, group_vars) -> str | None`;
  - `storage_ready.backup_window(now) -> str | None` (D29), with `now` an aware `datetime`.

What the code does today, and the decisions this task builds in:
- `fetch-inventory.yml` asserts exactly one `storage` host (`roles/storage_vm/tasks/fetch-inventory.yml:4-11`), so a
  scheduled run would go red from 3.2 until 3.4. It must instead skip before any playbook, both while the group is
  empty and while `storage_vm_pv_devices` is the placeholder (Task 2.3, set in 3.5).
- `storage.yml` runs its dry-run play (`storage.yml:37-47`) and then the lock check (`:54-58`) in one invocation, so
  the lock has to be held before the playbook starts. Per D21, the workflow does four things in order:
  1. a dry run with no lock, through the new `storage-dry-run.yml`, which holds the fetch, dry-run and cleanup plays
     only;
  2. a check for `/maintenance/operation.json`, then one `acquire` (ADR "How a run works": it exits 0 with a
     warning when the lock is held);
  3. `storage.yml` under the lock. It runs its own dry-run play again at the same fetched SHA, so the applied SHA is
     always dry-run in that invocation. The first dry run may have seen an older SHA, and that is harmless;
  4. release.

  A tag-selected subset of `storage.yml` was rejected. Its cleanup play reads the `masters[0]` kubeconfig fact, which
  a dry-run-only run never sets.
- **A failed run keeps the lock (D31)**, in both `storage.yml` and `storage-expiry.yml`, as `deploy.yml` does
  (`deploy.yml:104-105`, release only after success; terraform `CLAUDE.md`: failed runs keep the lock). Later runs
  then exit 0 with the held warning, and `MaintenanceLockStale` (2.4) fires after 6 h. The stale lock is released
  through the helper's release path with Ben's OK, after the run's log is read (Global Constraints "Maintenance
  lock"). **Decided (Ben, 2026-11-22):** a failed run keeps the lock, as `deploy.yml` does; `MaintenanceLockStale`
  fires after 6 h. A `no-space` or `vg-missing` refusal (Task 2.10) fails the apply the same way.
- **Backup windows (D29).** D29's answer (Ben, 2026-11-23: keep the hourly run on Actions), skipping the windows on
  the hourly run, is built as a
  schedule-only skip evaluated at run time in `storage_ready.py` (`backup_window`), not as hours left out of the cron
  string: a UTC hour list shifts at each Jerusalem DST change, and the 04:25 and Sunday 05:25 windows end "when the
  unit has finished", which no cron string can express. The cron stays `5 * * * *` (Step 3 gives the details).
- Lock helper (m13, settled offline). `git -C $A diff 8872697 HEAD -- scripts/maintenance_lock.py` only adds
  `ExecutionBusy`, `_execution_guard` and `execution()`, and wraps `acquire`, `release` and `advance` in
  `_execution_guard`; `_guard`, `_record` and `verify` are unchanged. So the pinned copy's acquire and release work
  with the repo copy's `verify`, which `lock-verify.yml:7` calls. The workflows use the pinned copy for acquire and
  release, as `deploy.yml` does, and a test pins the mix.

- [ ] **Step 1: Write the failing tests** in `scripts/tests/test_storage_workflows.py` (stdlib, PyYAML; model
  `test_deploy_lock.py`):
  - `test_workflow_skips_without_storage_host`:
    ```python
    self.assertEqual(skip_reason([], {}), 'no host in the storage group')
    self.assertEqual(skip_reason(['storage-01'], {}), 'storage_vm_pv_devices is the placeholder')
    self.assertEqual(skip_reason(['storage-01'], {'storage_vm_pv_devices': {'retained': '', 'regen': '/dev/b'}}),
                     'storage_vm_pv_devices is the placeholder')
    self.assertIsNone(skip_reason(['storage-01'], {'storage_vm_pv_devices': PV}))
    with self.assertRaises(SystemExit): skip_reason(['a', 'b'], {'storage_vm_pv_devices': PV})
    ```
    Also `storage_ready.main(hosts=[])` with `GITHUB_OUTPUT` set: exit 0, `ready=false`, stdout
    `Skipping: no host in the storage group; nothing touched`.
    In both workflows, every step after id `ready` except the final credential cleanup (and 2.4's `Write host gauges`,
    gated on its own `gauges` output) has an `if` that is false when `steps.ready.outputs.ready` is `'false'`
    (evaluated like terraform's `WiringTests`).
  - `test_dry_run_before_lock_then_apply_then_release`: in `storage.yml`, step order is `ready`, dry run
    (`storage-dry-run.yml`), `lock`, reconcile (`storage.yml`), release. The dry run does not reference
    `maintenance_lock.py`.
  - `test_schedule_skips_inside_windows` (D29): with a fixed clock, `backup_window` gives a window name at 02:05
    Asia/Jerusalem on a weekday in January (UTC+2) and in July (UTC+3), at Sunday 01:05, at 05:05 daily and at Sunday
    06:05; it gives `None` at 03:05 and 12:05. `storage_ready.main(hosts=[...one host...], event='schedule', now=<02:05
    local>)` with real PV paths writes `ready=false` and prints `Skipping: inside backup window dumps; the next hourly
    run retries`. The same call with `event='repository_dispatch'`, `'workflow_dispatch'` or `'push'` writes
    `ready=true`.
  - `test_lock_held_exits_zero`: run the `lock` step script against a fixture lock dir. Substitute the helper path and
    the `/maintenance` root as `test_deploy_lock.py:27-31` does, replacing the helper path first, because
    `/maintenance` is also a prefix of `/maintenance_lock.py`.
    - With an `operation.json` present: exit 0, a `::warning::` line containing `held`, `acquired=false`, and the
      record is untouched.
    - Without one: `acquired=true` and `MAINTENANCE_NONCE` in `GITHUB_ENV`.
  - `test_held_lock_skips_before_dry_run`: the step `Skip while another maintenance operation runs` (before the dry
    run) exits 0 and sets `held=true` when `operation.json` exists. The dry run's `if` requires `held != 'true'`.
  - `test_release_only_after_success` (D31): in both `storage.yml` and `storage-expiry.yml`, the release step's `if`
    is `steps.lock.outputs.acquired == 'true'`, with no `always()` and no `failure()`. Run each reconcile script with
    a fake `ansible-playbook` that exits 1: `operation.json` stays.
  - `test_no_sha_from_payload`: neither workflow text contains `client_payload` or `storage_vm_inventory_branch`, and
    no `ansible-playbook` call passes `-e`.
  - `test_triggers`:
    - `storage.yml`: `repository_dispatch.types == ['storage-changed']`, `workflow_dispatch`, `schedule` one cron
      `'5 * * * *'`, and `push` paths `['group_vars/storage/**', 'roles/storage_vm/**', 'storage-dry-run.yml',
      'storage-play-*.yml', 'storage.yml']`.
    - `storage-expiry.yml`: `schedule` `'5 10 * * *'` and `workflow_dispatch` only.
    - Each has its own `concurrency.group` with `cancel-in-progress: false`, and `timeout-minutes`.
  - `test_lock_helper_pinned_like_deploy`: the `maintenance-helper` checkout `ref` in both equals the one in
    `deploy.yml`.
  - `test_pinned_acquire_repo_verify_compatible`: load the pinned helper from `$PINNED_LOCK_HELPER` and the repo
    copy. Pinned `acquire`, then repo `verify(root, owner, nonce)`, then pinned `release`; no exception. A wrong nonce
    makes repo `verify` raise `PermissionError`.
  - `test_deploy_ignores_storage_only_paths`: `deploy.yml` `paths-ignore` contains:
    - `roles/storage_vm/**`, `storage.yml`, `storage-expiry.yml`, `storage-dry-run.yml`, `storage-play-*.yml`,
      `group_vars/storage/**`;
    - `.github/workflows/storage.yml`, `.github/workflows/storage-expiry.yml`;
    - `scripts/storage_ready.py`, `scripts/tests/test_storage_workflows.py`.

    It contains none of `roles/k3s_common/**`, `k3s.yml` or `tasks/lab-guard.yml`, which `k3s.yml` uses.
  - In `test_storage_vm_role.py`, add `test_dry_run_playbook_takes_no_lock`:
    - `storage-dry-run.yml` plays, with each `import_playbook` resolved, are by hosts: `all` (lab guard),
      `localhost` (fetch), `storage` (dry run), and `localhost` (remove `{{ storage_vm_checkout.path }}` only);
    - the dry-run play equals `storage.yml`'s dry-run play;
    - the text has no `lock-verify` or `maintenance_lock`.
  - Audit fold-in (D49), same files:
    - `test_storage_playbooks_share_plays` (`test_storage_vm_role.py`): `storage.yml`, `storage-expiry.yml` and
      `storage-dry-run.yml` start with `import_playbook: storage-play-lab-guard.yml`; `storage.yml` and
      `storage-expiry.yml` import `storage-play-fetch-inventory.yml` and `storage-play-cleanup.yml`; no top-level
      `storage*.yml` defines a play named `Lab guard` or `Fetch and validate the inventory at the branch tip` itself.
      `storage-expiry.yml` keeps its order: lab guard, `Verify maintenance ownership`, fetch. Every existing test that
      lists plays by hosts reads them through one helper, `plays(path)`, which resolves imports.
    - `test_expiry_users_expression` (`test_storage_vm_role.py`): template the `expire-volume.yml:55-57` expression
      with ansible's `Templar` over fixture results: two claims, a pod mounting the first, a pod with no `volumes`, a
      pod mounting an unrelated claim. Expected: the first claim's name only. It passes on today's nested loop and
      pins the output for the rewrite.
    - Delete `WorkflowTests` (`test_storage_vm_role.py:705-723`): it reads `validate.yml` text, including how the
      syntax-check line ends, and one discover step (Step 3) makes a per-file check moot.
- [ ] **Step 2: Run**
  `cd $A && PINNED_LOCK_HELPER=$H/scripts/maintenance_lock.py $PY scripts/tests/test_storage_workflows.py && $PY
  scripts/tests/test_storage_vm_role.py`.
  Expected: FAIL (no `scripts/storage_ready.py`, no workflows, no `storage-dry-run.yml`).
- [ ] **Step 3: Implement.**
  - `scripts/storage_ready.py`:
    - `skip_reason(hosts, group_vars)`:
      - no hosts gives `'no host in the storage group'`;
      - more than one exits 1 with `more than one host in the storage group`, since that is a misconfiguration and
        must not be skipped;
      - a `storage_vm_pv_devices` that is not a mapping with exactly `retained` and `regen`, each a string starting
        `/dev/`, gives `'storage_vm_pv_devices is the placeholder'`;
      - otherwise `None`.
    - `backup_window(now)` (D29, `<D29:window_skip>`): convert `now` with `ZoneInfo('Asia/Jerusalem')` (stdlib;
      DST moves the UTC mapping, so the check is never a cron hour list) and return the first matching name from
      the Global Constraints windows, copied verbatim from the lab plan:
      `dumps` 01:55-02:15 daily; `vzdump` Sunday 00:55-01:15; `backup` 04:25-`<D29:backup_end>`; `maint` Sunday
      05:25-`<D29:maint_end>`. The `:25-:50` snapshot windows are never hit by a `:05` cron and need no entry. The
      backup and maint windows end "when the unit has finished", which a runner container cannot see; the
      provisional values are `<D29:backup_end>` = 06:00 and `<D29:maint_end>` = 07:00, UNVERIFIED (the docs give no
      run time). Ben confirms both, for example from the healthchecks run durations (D29, decided 2026-11-23).
      `ZoneInfo` needs tzdata in `python:3.14-trixie` (UNVERIFIED); if it raises there, add the `tzdata` wheel to the
      requirements. A failed lookup fails the step, never skips the window check.
    - `main(hosts=None, event=None, now=None)`:
      - `event` defaults to `$GITHUB_EVENT_NAME`, `now` to `datetime.now(timezone.utc)`;
      - when `event == 'schedule'` and `backup_window(now)` names a window, print `Skipping: inside backup window
        <name>; the next hourly run retries`, write `ready=false` and exit 0. Dispatch,
        manual and push runs are never window-skipped: they fire at merge or operator time, which the operator keeps
        out of the windows;
      - when `hosts` is None, read the `storage` group with
        `InventoryManager(loader=DataLoader(), sources=['inventory/proxmox.yml'])`. The exact accessor (for example
        `get_groups_dict()`) is UNVERIFIED for ansible 15.0.0; confirm it in a REPL in `$L/venv`;
      - load `group_vars/storage/storage_vm.yml` with `yaml.safe_load`, or use `{}` when the file is absent. That file
        holds no vault data, so no vault is needed;
      - print the skip line and write `ready=false|true` to `$GITHUB_OUTPUT`.
  - Audit fold-in, first: the `storage-play-*.yml` files, at the repo root (a playbook imported from a subdirectory
    resolves `tasks/lab-guard.yml` and the roles against that subdirectory: checked 2026-11-22 with
    `ansible-playbook --syntax-check` on a scratch copy of A, ansible 15.0.0). Move the `Lab guard` play (`storage.yml:5-14`), the `Fetch and validate
    the inventory at the branch tip` play (`storage.yml:16-25`) and the `Remove the kubeconfig and the inventory
    checkout` task (`storage.yml:136-147`, its play header included) there, one file each, and `import_playbook` them
    from `storage.yml` and `storage-expiry.yml`. Each playbook's own last task after the removal (`storage-expiry.yml`'s
    `Fail if a volume was refused or failed`, and `storage.yml`'s, if any) moves into a following `localhost` play of
    its own. `diff` the two copies of each play first; stop on a difference that is not a play name. `k3s.yml` keeps
    importing `tasks/lab-guard.yml` itself.
  - `storage-dry-run.yml`: `import_playbook` of `storage-play-lab-guard.yml` and `storage-play-fetch-inventory.yml`,
    the dry-run play copied from `storage.yml:37-47`, and a cleanup play that removes only the inventory checkout.
  - Audit fold-in: `expire-volume.yml:55-57`. Replace the triple nested `{% for %}` with a filter chain (checked
    2026-11-22 with ansible 15.0.0's `Templar` on fixture results: true for a mounting pod, false otherwise): per result
    `r`, `r.resources | map(attribute='spec.volumes', default=[]) | flatten |
    selectattr('persistentVolumeClaim', 'defined') | map(attribute='persistentVolumeClaim.claimName')` contains
    `r.item.name`. `test_expiry_users_expression` stays green.
  - `roles/storage_vm/tasks/dry-run.yml`: register the dry-run command and add a `debug` of its `stderr_lines`, shown
    when stderr is not empty. Otherwise Task 0.2's `hold_create set, N creates refused` line (exit 0) never reaches the
    workflow log without `-v` (Part 0 final review). Pin it in `RoleTests` with the task's `register` and `when`.
  - `.github/workflows/storage.yml`. Job `reconcile`, `runs-on: self-hosted`, `timeout-minutes: 30`, container
    `python:3.14-trixie` with volume `/var/lib/homelab-maintenance:/maintenance`. Env: `HOMELAB_RUNNER_INSTANCE`
    (the value in `deploy.yml:43`), `MAINTENANCE_OWNER` and the `PROXMOX_*` secrets. Steps:
    1. checkout; checkout the pinned helper (as `deploy.yml:56-62`); pip cache; install requirements and collections
       (as `deploy.yml:64-76`);
    2. `Prepare private connection credentials` (umask 077, `private_key.pem`, `.vault_pass`; `deploy.yml:84-91`);
    3. id `ready`: `python3 scripts/storage_ready.py`;
       - Task 2.4 (part 2b) later inserts the step `Write host gauges` between this step and step 4, gated on
         `steps.ready.outputs.gauges == 'true'` only (an output 2.4 adds; it stays true on a window skip); it is not
         part of this task.
    4. id `held`, `Skip while another maintenance operation runs`: `test -e /maintenance/operation.json`; set `held`
       and print a `::warning::`;
       - Built since (final review n=11): id `preflight`, `Check that k3s answers before the lock`, runs
         `storage-preflight.yml` between this step and step 5; a `k3s=false` answer gates steps 5-8 off (block above).
    5. `Dry-run before the lock`: `ansible-playbook -i inventory/proxmox.yml --vault-password-file .vault_pass
       --private-key private_key.pem storage-dry-run.yml`;
    6. id `lock`, `Try the maintenance lock once`: if `/maintenance/operation.json` exists, print
       `::warning::Maintenance lock is held; skipping, the next hourly run retries` and write `acquired=false`.
       Otherwise run `python3 maintenance-helper/scripts/maintenance_lock.py acquire --operation ansible-storage
       --github-env` and write `acquired=true`;
    7. `Reconcile under the lock`: `maintenance_lock.py verify`, then `ansible-playbook ... storage.yml`;
    8. `Release the lock after success`: `maintenance_lock.py release`, `if: steps.lock.outputs.acquired == 'true'`;
    9. `Remove private controller credentials`, `if: always()`: `rm -f .vault_pass private_key.pem`.

    Steps 4-8 carry `if` conditions on `ready`, `held` and `acquired` (2.4's `Write host gauges` on `gauges` only).
    Triggers are those of `test_triggers`.
  - `.github/workflows/storage-expiry.yml`: the same job without the dry-run step (built since, final review n=11 and
    n=17: with the `preflight` step, which fetches and validates the inventory before the lock). The operation is
    `ansible-storage-expiry`, the playbook `storage-expiry.yml` (which runs `lock-verify` first and skips a VG tagged
    `hold_create`; `test_storage_expiry.py:69`), and the cron is daily.
  - Schedules are UTC. `5 * * * *` never lands in a `:25-:50` snapshot window, but it does land at 02:05 Jerusalem
    (dumps), Sunday 01:05 (vzdump) and inside the 04:25 and Sunday 05:25 windows. Per D29, scheduled runs skip those
    windows in `storage_ready.py` (`backup_window`, above), so `ready=false` gates every later step and the hourly
    backstop (which can create LVs and targets after a lost dispatch or a lock-held skip) never takes the lock or
    mutates inside a window. The cron stays `5 * * * *`, because a UTC hour list breaks at each DST change.
    `storage-expiry.yml` runs the same `ready` step; `5 10 * * *` is 12:05 or 13:05 in Jerusalem, outside every
    window.
  - After a lock-held skip or a window skip, the next hourly run outside a window does the delayed reconcile. An
    operator who needs it sooner dispatches `storage.yml` by hand outside a window (**Ben OK**).
  - The `push` trigger is an addition to the ADR's three triggers (dispatch, manual, hourly). It makes a storage-role
    merge run on the storage VM at merge time, instead of at the next hourly run at an unplanned minute.
  - `deploy.yml` ignoring the storage role and playbooks assumes deploys never run the storage play. Today `k3s.yml` has
    none (`grep storage k3s.yml` hits only the lab guard). The ADR's token copy "from both `deploy.yml` and the hourly
    `storage.yml`" is therefore half built, and so is ADR "How a run works" ("Normal deploys run the same play to export
    and repair"): after a k3s rebuild, the token copy and ACL/target repair wait for the next hourly `storage.yml` run.
    Both departures are D28, deferred with automatic fencing (Ben, 2026-11-21): while `hold_fence` stays, a blind fencer
    refuses anyway. The choice for Ben when fencing is revisited: (a) end `deploy.yml` with a `storage.yml` dispatch (it
    skips under the lock, inside a window on schedule only, or while the storage group is empty), or (b) accept a blind
    fencer for up to an hour, longer when the next hourly runs fall in a D29 window skip (with the provisional D29 ends,
    a rebuild at 04:10 waits for 06:05). This task adds neither.
  - `deploy.yml` `paths-ignore`: add the ten paths of `test_deploy_ignores_storage_only_paths`.
  - `validate.yml`:
    - job `lint`: add a checkout of the pinned helper to `maintenance-helper` (with `persist-credentials: false`).
      Audit fold-in: replace every per-file `python3 scripts/tests/test_*.py` step and the `test_maintenance*.py`
      discover step (`validate.yml:26-27`) with one step `Run unit tests`:
      `python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v`, with env
      `PINNED_LOCK_HELPER: maintenance-helper/scripts/maintenance_lock.py`. It runs after `Install Ansible
      collections` (`test_argocd_bootstrap.py` and `test_storage_vm_role.py` import ansible) and after the helper
      checkout, so `test_storage_workflows.py` needs no step of its own, and Tasks 2.4, 2.6 and 2.10 add no per-file
      step. Check it locally first:
      `cd $A && PINNED_LOCK_HELPER=$H/scripts/maintenance_lock.py $PY -m unittest discover -s scripts/tests -p
      'test_*.py'`. Expected: `OK`. On A today (2026-11-22) this ran 457 tests with 3 errors, all in
      `test_sealing_recovery.py`, which needs `KUBESEAL_BINARY` and runs in `csi-activation-preflight.yml` instead.
      So, first: decorate its `RecoveryTests` `skipUnless(os.environ.get('KUBESEAL_BINARY'))`, and have the
      preflight step also set `REQUIRE_KUBESEAL: '1'`, which makes the module raise when `KUBESEAL_BINARY` is unset,
      so the preflight run can never pass by skipping (Files: that test and `csi-activation-preflight.yml`);
    - job `syntax-check`: add `storage-dry-run.yml` to the list at `validate.yml:155`.
- [ ] **Step 4: Run** Step 2, `$PY scripts/tests/test_workflow_credentials.py` (the new self-hosted jobs write both
  credential files under `umask 077` and remove them last with `always()`), `$PY scripts/tests/test_deploy_lock.py`,
  and `cd $A && echo dummy > .vault_pass && $L/venv/bin/ansible-lint --offline; rm -f .vault_pass`. Expected: PASS.
- [ ] **Step 5: Commit**:
  1. `feat(storage): skip storage runs until the storage VM is configured`;
  2. `ci(storage): reconcile and expiry workflows with a dry run before one lock try`.
- Merge event: Task 3.2 (deploy plus k3s restarts, from the rest of that PR). The push also triggers `storage.yml`,
  which prints `Skipping: no host in the storage group` and exits 0. That line in the 3.2 run log is the check, and it
  goes to `evidence/3.2/`.

### Task 2.3: ansible: bridge workflow and production vars

**Files** (worktree A):
- Bridge PR branch `feat/storage-bridge` off `origin/main` (Task 3.1):
  - cherry-pick `08f540f`, `325e16a` (role, playbook, test, validate steps);
  - Create: `.github/workflows/storage-bridge.yml`;
  - Modify: `.github/workflows/deploy.yml` (`paths-ignore`), `scripts/tests/test_proxmox_storage_bridge.py`.
- On `feat/retained-storage-vm` (Task 3.2):
  - Create: `group_vars/storage/storage_vm.yml`;
  - Modify: `roles/storage_vm/defaults/main.yml`, `lab/vars.example.yml`, `scripts/tests/test_storage_vm_role.py`.
  - Audit fold-in (D49, genericity audit "ansible `storage-vm`"): Modify `tasks/lab-guard.yml`,
    `roles/storage_vm/tasks/assert.yml:84-92`, `lab/inventory.example.yml`, `group_vars/all/vars.yml`
    (`production_vip_address`).

**Interfaces:**
- Consumes: `proxmox-storage-bridge.yml` (hosts `proxmox_hosts`, in `inventory/hosts.yml`); the precedent
  `proxmox-guest-startup.yml` workflow; D1 addresses; terraform worker names `kube-worker-01` and `kube-worker-02`
  (`name_prefix` `kube`, origin/main `main.tf:59`).
- Produces:
  - `storage-bridge.yml` push paths `roles/proxmox_storage_bridge/**` and `proxmox-storage-bridge.yml`;
  - group vars `storage_vm_workers`, `storage_vm_bridge_address` and `storage_vm_ssh_sources`;
  - role default `storage_vm_pv_devices: {}`, which `tasks/assert.yml:26-33` refuses and `storage_ready.py` skips.

- [ ] **Step 1: Write the failing tests.**
  - `test_proxmox_storage_bridge.py` `test_workflow_and_deploy_ignore`, modelled on
    `test_proxmox_backup.py:488-498`:
    ```python
    for p in ('roles/proxmox_storage_bridge/**', 'proxmox-storage-bridge.yml',
              '.github/workflows/storage-bridge.yml', 'scripts/tests/test_proxmox_storage_bridge.py'):
        self.assertIn(p, deploy_ignored)
    self.assertEqual(sorted(own[True]['push']['paths']),
                     ['proxmox-storage-bridge.yml', 'roles/proxmox_storage_bridge/**'])
    self.assertIn('-i inventory/hosts.yml', run); self.assertIn('proxmox-storage-bridge.yml', run)
    self.assertNotIn('proxmox_storage_bridge_state', run)   # a merge can only add the bridge
    ```
  - `test_storage_vm_role.py`:
    - `test_production_pv_devices_not_lab`: role default `storage_vm_pv_devices == {}`, and neither
      `defaults/main.yml` nor `group_vars/storage/storage_vm.yml` contains `pci-0000:06:0b.0` or `pci-0000:06:0c.0`.
      `holds(that, storage_vm_pv_devices={})` is False for the `tasks/assert.yml` PV assert.
    - `test_production_storage_vars` (audit fold-in: the worker list comes from the inventory, never a hand-kept
      copy of the `workers` group and terraform's addresses). Load `group_vars/storage/storage_vm.yml` and template it
      with ansible's `Templar` over a fake inventory: `groups['workers'] == ['kube-worker-02', 'kube-worker-01']`, each
      with `proxmox_ipconfig0 == {'ip': '10.9.9.5<n>/24', ...}`, `proxmox_ipconfig1 == {'ip': '10.9.8.5<n>/24', ...}`
      (production workers already have `ipconfig1` on `vmbr1`, T `terraform.tfvars:11-23`) and
      `proxmox_ipconfig2 == {'ip': '10.99.2.<n>/24', ...}` (`<D1:worker_bridge_start>` for 01, the next for 02).
      The first assert in `tasks/assert.yml` holds for it:
      ```python
      self.assertEqual(v['storage_vm_workers'], [
          {'name': 'kube-worker-01', 'bridge_address': '10.99.2.<D1:worker_bridge_start>'},
          {'name': 'kube-worker-02', 'bridge_address': '10.99.2.<D1:worker_bridge_start + 1>'}])
      self.assertEqual(v['storage_vm_bridge_address'], '<D1:storage_bridge_ip>')
      self.assertNotIn('storage_vm_pv_devices', raw)          # the file as loaded; set in Task 3.5
      ```
      With `groups['workers'] == []`, or a worker with no `proxmox_ipconfigN` inside `10.99.2.0/24`, or with two,
      templating fails or the `tasks/assert.yml` workers assert fails; neither yields a shorter list. A worker that
      drops out of the Proxmox inventory does yield one: the installed-config assert refuses it unless `remove_workers`
      names it (built since, final review n=1). The selection is
      by subnet, never by index: the storage NIC is `ipconfig2` in production (2.1c's `storage_nic`, after `vmbr0` and
      `vmbr1`) and `ipconfig1` in the one-NIC cohort fixture. Mutation check: a template that reads
      `proxmox_ipconfig1` fails this test. That the proxmox inventory parses `ipconfig2` into `.ip` as it does
      `proxmox_ipconfig0` (`inventory/proxmox.yml:24`) is
      UNVERIFIED until a read-only `ansible-inventory -i inventory/proxmox.yml --host kube-worker-01` on the runner
      after the Task 3.3 rebuild; the lab passes its own `storage_vm_workers` with `-e @<lab>/vars.yml`, which wins.
    - Audit fold-in, lab detection: `test_lab_guard` (`:130-142`) and `test_pause_after_refused_outside_lab`
      (`:175-...`) key the lab on the inventory variable `lab: true`, not on `/lab-storage/` in `inventory_file`: a lab
      run is `lab=True` with any path, production is `lab` unset. The VIP check compares with `production_vip_address`
      (`group_vars/all/vars.yml`), not the literal `10.9.9.99`; `:731` does the same. `LabExampleTests`:
      `lab/inventory.example.yml` sets `all.vars.lab: true`, and `lab/vars.example.yml` does not set `lab` (the guard
      exists to catch a run that forgot that file).
    - In the test helper `defaults()` (`test_storage_vm_role.py:50-58`), add the lab map
      `'storage_vm_pv_devices': {'retained': '/dev/disk/by-path/pci-0000:06:0b.0', 'regen':
      '/dev/disk/by-path/pci-0000:06:0c.0'}` to its `variables.update`. Every render that went through the old default
      keeps its bytes. Tests that pass `storage_vm_pv_devices=` still override it. Then run the whole file, not only
      the new tests.
    - Audit fold-in, the drop-in test: `test_targetctl_dropin` (`:693-694`) stops comparing bytes. It renders with a
      non-default device, `{'retained': '/dev/disk/by-id/virtio-retained', 'regen': '/dev/disk/by-id/virtio-regen'}`
      (the Task 2.1b serials), and compares only the non-comment lines with the expected ones
      (`Wants=`/`After=dev-disk-by\x2did-virtio\x2dretained.device`, `vgchange --devices
      /dev/disk/by-id/virtio-retained -ay retained`, and the rest of `TARGETCTL_DROPIN` without its `#` lines).
    - Audit fold-in, `test_production_pv_devices_not_lab`: neither file contains `by-path/pci-` at all.
- [ ] **Step 2: Run** `cd $A && $PY scripts/tests/test_proxmox_storage_bridge.py; $PY
  scripts/tests/test_storage_vm_role.py`. Expected: FAIL (no workflow; default still holds the lab paths; no
  group_vars file).
- [ ] **Step 3: Implement.**
  - `.github/workflows/storage-bridge.yml`: a copy of `proxmox-guest-startup.yml` (container, pip, `sshpass`, vault
    file, `if: always()` cleanup) running `ansible-playbook -i inventory/hosts.yml --vault-password-file .vault_pass
    proxmox-storage-bridge.yml`. Triggers: `push` on `main` with the two paths above, and `workflow_dispatch`.
  - `deploy.yml` `paths-ignore`: the four bridge paths.
  - `roles/storage_vm/defaults/main.yml:16-20`: replace the lab map with `storage_vm_pv_devices: {}`. The comment says
    it is set per VM in `group_vars/storage/storage_vm.yml` to `/dev/disk/by-id/virtio-retained` and
    `/dev/disk/by-id/virtio-regen` (the Task 2.1b serials; audit fold-in, in place of the PCI by-path names) in Task
    3.5, and that the role and `storage_ready.py` refuse or skip until then. The value waits for 3.5 because the first
    run that sees real PV paths configures the VM (the merge-event note below).
  - Audit fold-in, lab detection: `tasks/lab-guard.yml:12` and `roles/storage_vm/tasks/assert.yml:89` test
    `lab | default(false) | bool`; `lab/inventory.example.yml` sets `all: vars: lab: true` and its comment drops the
    `/lab-storage/` path rule. `group_vars/all/vars.yml` gets `production_vip_address: 10.9.9.99` and
    `vip_address: "{{ production_vip_address }}"`; the guard's first condition becomes
    `vip_address != production_vip_address`, and `lab/vars.example.yml:3`'s comment says so.
  - `lab/vars.example.yml`: add the lab `storage_vm_pv_devices` (the two lab by-path links), since the default no
    longer carries them.
  - `group_vars/storage/storage_vm.yml`:
    ```yaml
    ---
    # Production storage VM (ADR 0017). The workers come from the inventory; storage_vm_bridge_address must equal
    # terraform storage/terraform.tfvars storage_ipv4 (fixed subnet).
    # Every k3s worker, with its storage-bridge address from terraform storage_nic: the one Proxmox
    # ipconfigN whose address is inside storage_vm_bridge_subnet (ipconfig2 in production; never by index).
    storage_vm_bridge_subnet: 10.99.2.0/24
    storage_vm_workers: <expression>
    storage_vm_bridge_address: <D1:storage_bridge_ip>
    storage_vm_ssh_sources:
      - 10.9.9.0/24
    ```
    - `<expression>` builds the same sorted `[{name, bridge_address}]` list from `groups['workers']`. For each worker
      it takes the `.ip` of every `proxmox_ipconfig<N>` hostvar (`N` digits), strips the mask, keeps those inside
      `storage_vm_bridge_subnet`, and fails templating unless exactly one remains. Use a filter the runner's ansible
      image already has (check `ansible.utils.ipaddr`/`netaddr` there; otherwise a plain prefix compare on the /24),
      and record the check as the old comment did.
    - `tasks/assert.yml` gains one assert: every `bridge_address` is inside `storage_vm_bridge_subnet`, differs from
      `storage_vm_bridge_address`, and the addresses are unique. Tests: a worker on `10.99.2.10`, two workers on one
      address, and one outside the subnet each fail it.
    - `10.9.9.0/24` is the LAN the storage VM sits on, and the runner (`10.9.9.10`) and the VIP are on it.
    - The runner VM300 is `10.9.9.10` (`evidence/1.1/facts.md`, `runner_lan_ip`), inside `10.9.9.0/24`.
- [ ] **Step 4: Run** Step 2, `$PY scripts/tests/test_workflow_credentials.py` and `ansible-lint --offline` (as in
  2.2). Expected: PASS.
- [ ] **Step 5: Commit**:
  - on `feat/storage-bridge`: `ci(storage): apply the storage bridge from its own workflow, not deploy`;
  - on `feat/retained-storage-vm`: `feat(storage): production storage VM vars; PV paths refused until set`;
  - on `feat/retained-storage-vm` (audit fold-in): `refactor(storage): workers from the inventory, lab marked by its
    inventory, drop-in test by content`.
- Merge events:
  - The bridge PR (3.1) also edits `.github/workflows/deploy.yml` and `.github/workflows/validate.yml` (from
    `08f540f`), which are not in `paths-ignore`, so a plain merge would start a full deploy. Per D32, merge it as in
    3.1 Step 3: squash with `[skip ci]` in the squash subject (never on a branch commit), so no push workflow runs,
    then `gh workflow run storage-bridge.yml -R Starktastic-Homelab/ansible --ref main`, which adds `vmbr2` on pve.
    No deploy runs. `validate.yml` does not re-run on `main`; the PR's own green checks are the test gate.
    **Ben OK** for both.
  - The vars ship in the 3.2 PR.
  - The 3.5 PR that sets `storage_vm_pv_devices` (Task 3.5 Step 3) touches `group_vars/storage/storage_vm.yml` and
    `scripts/tests/test_storage_vm_role.py` (its `test_production_storage_vars` asserts the key is absent). The test
    file is not in `deploy.yml` `paths-ignore`, so a plain merge would start a full deploy. Run 3.5 Step 3's path
    check first:
    - every path ignored: merge plainly; `storage.yml` runs on `push` and no deploy runs;
    - any path not ignored (the expected case): per D32, squash with `[skip ci]` in the squash subject, check that no
      push run started on the merge SHA, then `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main`
      (**Ben OK**). The PR's own green checks are the test gate.

    Either way, merge it only **after** the VG bootstrap (3.5 Step 2), because the first `storage.yml` run that
    sees real PV paths configures the VM. That ordering is 3.5's, not D32.

### Task 2.8: ansible: backups

Three branches off `origin/main` in A, and one in `.github`. A PR that mixes `roles/proxmox_backup/**` with `docs/`
runs a full deploy, because `docs/` is not in `deploy.yml` `paths-ignore`. `[skip ci]` on it would also skip
`proxmox-backup.yml`. So the code PRs and the docs-only PR are separate. `[skip ci]` goes only on the docs PR's squash
subject at merge, never on a branch commit (Global Constraints).

**Files:**
- `feat/storage-regen-exclude` (merged in 3.5): Modify `roles/proxmox_backup/defaults/main.yml`
  (`proxmox_backup_excludes`, origin/main `:42-49`), `scripts/tests/test_proxmox_backup.py`
  (`test_excludes_cover_regenerable_images`, origin/main `:328-334`).
- `docs/storage-regen-exclude` (merged after it, `[skip ci]` in the squash subject): Modify
  `docs/backup-and-restore.md` (the `daily` row at origin/main `:29`, and **Re-initialise an excluded image** from
  `:361`).
- `feat/storage-retained-dump-rule` (merged at the first `retained` cutover, D17): Modify
  `roles/proxmox_backup/defaults/main.yml` (`proxmox_backup_dump_rules`, origin/main `:53-`),
  `scripts/tests/test_proxmox_backup.py`.
- `feat/storage-vm-startup` (merged in 3.5, after the VM exists): Modify `group_vars/proxmox_hosts/guest_startup.yml`
  (`:7-8`), `scripts/tests/test_proxmox_guest_startup.py`.
- `.github` repo `~/Projects/homelab/.github` (no worktree alias in the outline; add a worktree
  `$L/worktrees/github-storage-vm` on branch `docs/storage-backup-inputs`): Modify `CLAUDE.md:52` ("Backup inputs").

**Interfaces:**
- Consumes: `<D1:placeholder_vmid>`, `<regen_volname>`, `<retained_volname>` (the 2.1b `path_in_datastore` values and
  the 3.4 `pvesm alloc` names); `dump_problems(entries, now, rules)`
  (`roles/proxmox_backup/files/homelab-backup.py:80`).
- Produces:
  - exclude `/srv/backup-src/k3s-block/images/<D1:placeholder_vmid>/<regen_volname>`;
  - dump rule `{ glob: /srv/backup-src/k3s-block/images/<D1:placeholder_vmid>/<retained_volname>, max_age_h:
    <retained_max_age_h>, min_count: 1 }`;
  - startup `"<D1:storage_vmid>": "order=2,up=30"`.

- [ ] **Step 1: Write the failing tests.**
  - `test_excludes_cover_regenerable_images`: add the regen path to the expected list, next to the five `vm-9999`
    images:
    ```python
    images = sorted([*(f'/srv/backup-src/k3s-block/images/9999/vm-9999-{n}.raw' for n in FIVE),
                     '/srv/backup-src/k3s-block/images/<D1:placeholder_vmid>/<regen_volname>'])
    ```
    Add `test_retained_image_is_backed_up`: the retained path is in no exclude line.
  - `test_retained_image_dump_rule` (dump-rule branch only):
    - the rule above is in `proxmox_backup_dump_rules`;
    - `dump_problems` with one entry for that path, `<retained_max_age_h> + 1` hours old, reports `stale:`;
    - a fresh entry reports nothing;
    - no entry reports missing (as `test_dump_problems_flags_old_empty_and_missing` builds its inputs).
  - `test_storage_vm_starts_after_truenas` (startup branch):
    `proxmox_guest_startup == {'100': 'order=1,up=180', '<D1:storage_vmid>': 'order=2,up=30'}`. The workers stay
    unordered, so they start after both and stop first.
- [ ] **Step 2: Run** `cd $A && $PY scripts/tests/test_proxmox_backup.py; $PY
  scripts/tests/test_proxmox_guest_startup.py`. Expected: FAIL on each branch's new assertion.
- [ ] **Step 3: Implement.**
  - The exclude: one line after the five `vm-9999` lines, with the comment
    `# storage VM regen disk (ADR 0017); the five above go at Retirement`.
  - The dump rule, with the comment
    `# The storage VM's retained image (ADR 0017): missing or not written means its replica is stale`.
    `<retained_max_age_h>` is not in the ADR. The recommendation is `26`, the daily rules' value. MMP rewrites a
    mounted ext4 every 5 s (ADR copy step: `mmp_update_interval=5`), so a live image's mtime is at most one replication
    old. Ben confirmed 26 (D34, 2026-11-23).
  - The startup entry under `proxmox_guest_startup`, with the comment
    `# Storage VM (ADR 0017): after TrueNAS NFS, before the unordered k3s VMs`.
    - Add no balloon entry. Whether bpg's default leaves the balloon off on this VM is UNVERIFIED; read
      `qm config <D1:storage_vmid>` in 3.5 before deciding.
  - Docs (branch `docs/storage-regen-exclude`):
    - `:29`: "six images", naming the regen disk.
    - **Re-initialise an excluded image**: a line that the regen disk is excluded too and is re-created through the
      storage VM runbook (`storage-vm-rebuild.md`, Task 2.7), not by this section's `vm-9999` steps.
  - `.github` `CLAUDE.md:52`:
    - Producer: add terraform `storage/terraform.tfvars` (`data_disks`).
    - Consumer: unchanged.
    - Also add the regen image to the row text. `profile/README.md` has no such row (grep), so it needs no change.
- [ ] **Step 4: Run** Step 2. Expected: PASS.
- [ ] **Step 5: Commit**:
  - `feat(backup): exclude the storage VM regen disk from restic`;
  - `docs(backup): name the storage VM regen exclude` (no `[skip ci]` on the commit; the squash subject gets it);
  - `feat(backup): alarm on a missing or stale retained image`;
  - `feat(startup): start the storage VM after TrueNAS`;
  - in `.github`, `docs: storage VM regen image in Backup inputs`.
- Merge events:
  - The exclude PR triggers `proxmox-backup.yml` only (`deploy.yml` ignores `roles/proxmox_backup/**` and
    `scripts/tests/test_proxmox_backup.py`). It rewrites `/etc/homelab-backup.d/excludes.txt` on pve. Check in 3.5:
    after the next `daily` run, `restic ls latest --tag daily` has nothing under `images/<D1:placeholder_vmid>/` except
    `<retained_volname>`.
  - The docs PR is merged with `[skip ci]` in the squash subject and triggers nothing:
    `gh pr merge <n> -R Starktastic-Homelab/ansible --squash --match-head-commit <sha>
    --subject "docs(backup): name the storage VM regen exclude [skip ci] (#<n>)"`. Memory `pr-merge-mechanics` says a
    docs-only ansible merge may need `--admin`.
  - The dump-rule PR triggers `proxmox-backup.yml` at the first `retained` cutover. Check it after the first health
    run.
  - The startup PR triggers `proxmox-guest-startup.yml`, which runs `qm set <D1:storage_vmid> --startup order=2,up=30`,
    a pve mutation. Check `qm config` in 3.5.
  - The `.github` PR triggers only `readme-images.yml` (`pull_request` on `main`, paths `docs/diagrams/**`,
    `'**/*.md'`, its script and itself; origin/main `.github/workflows/readme-images.yml:3-10`). Nothing runs on the
    merge to `main`.

  Each merge needs **Ben OK**. Evidence goes to `evidence/3.5/` and to `evidence/4.T-<first retained id>/`.

### Task 2.10: ansible: VG free-space check before create and grow; one missing VG refuses only its class

Worktree A, branch `feat/retained-storage-vm`, after Task 2.4's A commit; it ships in the Task 3.2 PR with the rest of
the branch. Line numbers are at A `a036b47`.

ADR reconcile table (`:357`) orders a create as "a VG free-space check, which refuses the entry if the VG is short
(Capacity); ledger `creating`; plain `lvcreate`". The code has no such check: `plan._entry` (`plan.py:55-63`) plans
`create_new`/`create_raw` from the inventory alone, and `Executor._create` (`reconcile.py:78-83`) writes the
`creating` tag before `lvcreate`. An entry larger than VG free therefore fails at `lvcreate` with the tag already
written, which every later run refuses as `crashed-create` until the manual recovery (Ben OK). `lvm.Vg` already reads
`vg_free` (`lvm.py:11,22,58`); `plan` never sees it. This task is the backstop under the apps CI size check (Task 2.6
Steps 5-8), which cannot see LVs kept for a removed entry until expiry.

Second fix, same task (critic point 4, Steps 5-8): `decide` (`plan.py:79-82`) refuses every entry, `retained`
included, with `vg-missing` and `fail=True` when either VG is missing or does not answer. A lost or stalled `regen`
disk, which holds only regenerable data, so stops every `retained` create and grow.

**Files:**
- Modify: `roles/storage_vm/files/homelab_storage/plan.py` (`VgState`, `decide`).
- Modify: `roles/storage_vm/files/homelab_storage/lvm.py:19-22,40,58` (`free_bytes` moves to `VgState`; build `Vg`
  with keywords).
- Modify (Step 2, D40): `roles/storage_vm/files/homelab_storage/reconcile.py:25`, `BLOCKING` gains `no-space`. The
  dry-run `return` in `apply` (`reconcile.py:213`) is unchanged (D42 option (b)).
- Test: `scripts/tests/test_storage_plan.py`, `scripts/tests/test_storage_reconcile.py`.
- Steps 9-11 (audit fold-in, D49, genericity audit "ansible `storage-vm`" low findings), same worktree and PR:
  - Modify: `roles/storage_vm/files/homelab_storage/config.py:6,29-30` (drop `vgs`; add `initiator_prefix`),
    `lvm.py:61` (`VG_NAMES`), `plan.py:79`, `reconcile.py` (`:32`, `:162-172` `_exported`, `:292`, CLI `:365-380`),
    `lio.py:6-7,22`, `fencer.py:73,103,138` (it calls `lio.worker_iqn` and passes the config's prefix);
  - Modify: `roles/storage_vm/templates/config.json.j2:9`, `roles/storage_vm/tasks/grow.yml:48`,
    `roles/k3s_common/tasks/main.yml:162`, `group_vars/all/vars.yml` (`storage_initiator_iqn_prefix`);
  - Modify (call sites that pass the default config path): `storage.yml:110-111`, `storage-expiry.yml:55`,
    `roles/storage_vm/tasks/expire-volume.yml:86`, `roles/storage_vm/templates/rtslib-fb-targetctl.service.d-50-homelab.conf.j2:17,20`;
  - Test: `scripts/tests/test_storage_reconcile.py`, `test_storage_lvm.py`, `test_storage_plan.py`,
    `test_storage_vm_role.py` (`:393-400`), `test_storage_fencer.py:29`.

**Interfaces:**
- Consumes: `vg_free` from `vgs --units b` (`lvm.py:11`), as `VgState.free_bytes`.
- Produces:
  - `plan.VgState.free_bytes: int | None = None`. `None` means not read and skips the check (plan fixtures only);
    `lvm._read` always sets an int, and a test pins that;
  - the refusal reason `no-space` for a `create_new`, `create_raw` or `extend` that does not fit. It is in `BLOCKING`
    (`reconcile.py:25`, D40): the dry run exits 1 before the lock is taken, and an apply that still meets it (free
    space lost between the dry run and the apply) logs `refused: <id>: no-space` and exits 1, as for any refusal;
  - `vg-missing` per class (Steps 5-8): only the entries whose class maps to the missing VG;
  - the refusal reason `other-vg-unread` (Steps 5-8, `fail=False`): an entry with no record in its own VG while the
    other VG is missing, so the cross-VG duplicate-id check cannot run.

Rule: per VG, `free` starts at `free_bytes`. The pass runs in `decide` directly after the per-entry loop (after
`plan.py:99`, so after the `hold_create` filter) and before the removed-entries loop (`plan.py:100`). Walk the
planned actions in inventory order (a held create consumes nothing). A create needs `size_bytes <= free`, an extend
needs `size_bytes - lv.size_bytes <= free`; a fitting action subtracts its need from `free`. A create that does not
fit is dropped, with no other action for that entry (it has no target yet). An extend that does not fit is dropped
and its `export` (and `clear_pending`) kept, as `shrink` does at `plan.py:66-67`. Sizes are multiples of 4 MiB
(`inventory.py`), the default extent, so the sums are exact.

**Decided (Ben, 2026-11-22):** `no-space` goes in `BLOCKING` (`reconcile.py:25`, D40), so the dry run fails before
the lock is taken. An oversized entry therefore stops the hourly run with no lock held, and the next run retries; no
tag was written, so after making room (growth runbook "Grow a data disk") or shrinking the PR, the next run creates
it. Only an apply that meets `no-space` after a passing dry run (free space lost in between) fails under the lock,
and per D31 that run keeps the lock until it is released (Ben OK).

- [ ] **Step 1: Write the failing tests.**
  - `test_storage_plan.py` (the `vg()` helper gains `free=None`, passed as `free_bytes`):
    - `test_create_refused_when_vg_too_small`: `vol('a', size=2 * GI)` against `retained=vg(free=GI)` gives
      `refused == {('a', 'no-space')}` and no action for `a`; with `free=2 * GI` it plans `create_new`.
    - `test_free_space_is_cumulative`: `vol('a', size=GI)`, `vol('b', size=GI)` with `free=GI` plans `a` and refuses
      `b` `no-space`; a `regenerable` entry is checked against `regen`'s free, not `retained`'s.
    - `test_extend_refused_when_vg_too_small`: a created LV of `GI` and an entry of `3 * GI` with `free=GI` keeps
      `('export', 'a')`, drops `extend`, and refuses `no-space`; with `free=2 * GI` it extends.
    - `test_hold_create_consumes_no_space`: under `hold_create`, `vol('a', size=2 * GI)` against
      `retained=vg(free=GI)` gives only `('a', 'hold-create')` and no `no-space` refusal (`decide` keeps only `export`
      actions under a hold, `plan.py:94-98`, so the pass sees no create).
    - `test_unread_free_skips_check`: `free=None` plans the create (the existing tests stay unchanged).
  - `test_storage_reconcile.py`:
    - `test_create_refused_when_vg_too_small_writes_no_tag`: `vg(free=GI)` on `retained` and one `origin: new`
      entry of `2 * GI`. `apply` (not dry run) returns 1, logs `refused: a: no-space`, runs no `lvcreate`, and no
      `vgchange --addtag ledger:a:creating` appears in the recorded commands.
    - `test_dry_run_fails_on_no_space_before_lock` (D40): the same state, `apply(..., dry_run=True)` returns 1 and
      logs `refused: a: no-space`; the recorded commands are reads only (`vgs`, `lvs`: no `lvcreate`, no `vgchange`),
      and no lock or checkpoint is written; the only file written is `storage-reconcile.prom` (built since, final
      review n=2: the dry run writes the gauges). The dry run runs before the lock in `storage.yml` (Task 2.2
      `test_dry_run_before_lock_then_apply_then_release`), so the run stops with no lock held.
    - `test_vg_read_sets_free_bytes`: `lvm.vgs()` on the fake gives `free_bytes == 50 * GI` (an int, never `None`).
  - Run: `cd $A && $PY scripts/tests/test_storage_plan.py && $PY scripts/tests/test_storage_reconcile.py`.
  - Expected: FAIL (`VgState` has no `free_bytes`; no `no-space` reason; the dry run returns 0 because `BLOCKING` has
    no `no-space`).
- [ ] **Step 2: Implement.**
  - `plan.VgState`: add `free_bytes: int | None = None` after `present`. `lvm.Vg` drops its own `free_bytes`, and
    `_read` and `_absent` build `Vg` with keywords, since the field order changes.
  - `plan.decide`: directly after the per-entry loop (after `plan.py:99`, the `hold` filter included) and before the
    removed-entries loop, apply the rule above in one pass over `d.actions`; append `Refusal(id, 'no-space')`. The
    removed-entries loop, the removal brake and the `hold` return (`plan.py:116-118`) are unchanged.
  - `reconcile.BLOCKING` (`reconcile.py:25`): add `'no-space'` (D40), and add `no-space` to the comment above it.
  - `Executor._create` is unchanged: the check runs before any action, so the tag is never written for a refused
    entry.
- [ ] **Step 3: Run** Step 1, then `$PY scripts/tests/test_storage_lvm.py` and the role's other storage tests as Task
  2.4 Step 3 runs them. Expected: PASS.
- [ ] **Step 4: Commit** `fix(storage): refuse a create or grow that does not fit in VG free space`. Code commit, no
  `[skip ci]`. Merge event: the ansible storage PR in Task 3.2 (a deploy, with k3s restarting on every node). The
  Task 3.2 PR contents list must name this task next to Tasks 2.2-2.4 and 2.6 (its owner adds it).

One missing VG (Steps 5-8). Rule for `decide`:
- `cluster is None` still refuses everything first (`plan.py:79`). `reconcile._state` (`reconcile.py:30-38`) reads
  the cluster tags from `retained` only, so a missing `retained` always gives `cluster=None` and keeps today's
  behaviour (`test_retained_missing_refuses_everything` stays). In practice only a missing `regen` takes the new path.
- Both VGs missing: refuse every entry `vg-missing`, no actions, `fail=True`, as today.
- One VG missing: set `d.fail = True` whether or not the inventory has an entry of that class. An entry whose class
  maps to the missing VG gets `vg-missing`; if its id is `created` with an LV in the present VG (a class move), that
  target keeps its `export`, as `other-vg` does at `plan.py:50-53`.
- An entry of the present VG: guard before `_entry`, since an absent `other` has an empty ledger and no LVs and would
  pass the cross-VG check silently. An entry with no record in its own VG (no ledger state, no tombstone, no LV, so a
  would-be create) gets `other-vg-unread` (`fail=False`) and no action. An entry with a record goes through `_entry`
  as today: its cross-VG check already ran when it was created, and a later create of the same id in the other VG
  would have been refused against this one. So exports, extends and `clear_pending` of `created` entries go on.
- The free-space pass and the removed-entries loop run as before; the absent VG has no LVs and adds nothing.
- Residual: new `retained` creates still stop while `regen` is out.

Dry-run gate (D42). `storage.yml` runs the dry run in its own play (`storage.yml:44-47`, `tasks/dry-run.yml:38-43`)
before the apply play takes the lock, and the dry run exits 1 on any `BLOCKING` reason (`vg-missing` is one) or any VG
not present (`test_dry_run_regen_stall`, `test_dry_run_missing_vg_empty_inventory`). So with `regen` out at dry-run
time the run still stops before the apply, and the `decide` change only acts when a VG is lost between the dry run and
the apply, or for the final read.
- **Decided (Ben, 2026-11-22):** option (b): the dry run keeps failing on any missing VG, before the lock; the
  apply-time per-class split still protects `retained` from a VG lost mid-run. Accepted cost: a `regen` disk out at
  dry-run time pauses `retained` creates and grows until it returns. A held lock would block every deploy and apply.
- Option (a), a dry run that exits 0 with one VG missing so the apply runs the present class: not chosen.
- The ADR reconcile rows (One VG missing, Both VGs missing) carry the per-class rule and its dry-run caveat; keep
  them in step with D42. The `DegradedTest` docstring (F11 approach A) is updated in Step 5.

- [ ] **Step 5: Write the failing tests.**
  - `test_storage_plan.py`:
    - Replace `test_vg_missing_refuses_all` (`:77`, it pins the old rule) with
      `test_regen_missing_keeps_retained_lifecycle`: `retained` holds a `created` LV `a` of `GI`, `regen` is
      `vg(present=False)`, inventory `vol('a', size=2 * GI)` and `vol('p', cls='regenerable')`. It plans
      `('export', 'a')` and `('extend', 'a')`, refuses `{('p', 'vg-missing')}`, and `d.fail` is true.
    - `test_both_vgs_missing_refuses_all`: both `vg(present=False)` with a cluster; every entry `vg-missing`, no
      actions, `d.fail` true.
    - `test_other_vg_unread_refuses_entry_only`: `regen` missing, `retained` holds `created` `a`; inventory `a` and a
      new `vol('b')`. `b` is refused `other-vg-unread` with no action, `a` keeps its `export`, and no other entry is
      refused for it.
    - `test_class_move_keeps_live_export`: `regen` missing, `retained` holds `created` `a`, inventory
      `vol('a', cls='regenerable')`: refused `vg-missing`, `('export', 'a')` on `retained` kept.
    - `test_retained_missing_refuses_everything` stays unchanged.
  - `test_storage_reconcile.py`:
    - `test_apply_regen_stall_grows_retained`: fake with `regen` stalled, `retained` holding `created` `a`; `apply`
      (not dry run) of `entry('a', size='2Gi')` and `entry('p', cls='regenerable')` returns 1, runs `lvextend` on
      `retained/a`, and refuses `p` `vg-missing`.
    - `test_dry_run_regen_stall` stays as it is (exit 1, D42 option (b)).
    - Update the `DegradedTest` docstring: a `regen` that does not answer refuses its own class and new creates.
  - Run: `cd $A && $PY scripts/tests/test_storage_plan.py && $PY scripts/tests/test_storage_reconcile.py`.
  - Expected: FAIL (no `other-vg-unread`; `retained` entries refused `vg-missing`).
- [ ] **Step 6: Implement.**
  - `plan.decide`: replace the `all(... present ...)` check at `plan.py:79-82` with the rule above: keep the
    `cluster is None` and both-missing refusals, set `fail` for one missing VG, refuse the missing class per entry,
    and guard the present class's would-be creates before `_entry`. Keep `_entry`'s cross-VG duplicate-id check
    unchanged for every entry it still sees.
  - `reconcile.apply`: the dry-run `return` (`reconcile.py:213`) is unchanged (D42 option (b)).
- [ ] **Step 7: Run** Step 5, then the Step 3 suite. Expected: PASS.
- [ ] **Step 8: Commit** `fix(storage): a missing VG refuses only its own class`. Code commit, no `[skip ci]`, in the
  same Task 3.2 PR as Step 4.
- [ ] **Step 9: Audit fold-in: write the failing tests** (D49; one copy of the VG names, the IQNs and the config path).
  - VG names: `lvm.VG_NAMES == ('retained', 'regen')` is the one copy; `plan.py:79`, `lvm.vgs()`'s default,
    `reconcile.py:32,292` and the `activate --vg` choices read it. A config with a `vgs` key is refused as an unknown
    key (`config.py` is strict); one without it loads; `config.json.j2` renders no `vgs`.
  - `--config` default: every `reconcile` subcommand defaults `--config` to `config.PATH`, as `fencer.py:338` does.
    `reconcile.main(['boot-check'])` with `config.PATH` patched to a fixture reads that fixture. The role test pins
    that `storage.yml`, `storage-expiry.yml`, `expire-volume.yml` and the targetctl drop-in no longer pass
    `--config /etc/homelab-storage/config.json`, and that `dry-run.yml:43` still passes its own path.
  - IQNs: each row of `reconcile._exported` carries `iqn` (`lio.iqn(id)`); `grow.yml` reads `storage_vm_volume.iqn`
    and never builds the target IQN itself. `lio.worker_iqn(name, prefix)` takes the config's `initiator_prefix`;
    `config.json.j2` renders it from `storage_initiator_iqn_prefix`, and `k3s_common`'s `InitiatorName` line renders
    from the same variable to the same bytes as today (`InitiatorName=iqn.2026-11.net.starktastic:<host>`), so no
    node's initiator changes. `TARGET_PREFIX` stays in `lio.py`, its one copy outside apps (the apps IQN literal is
    accepted by the audit).
  - Run: `cd $A && $PY -m unittest discover -s scripts/tests -p 'test_storage_*.py'`. Expected: FAIL (the new tests).
- [ ] **Step 10: Implement** the three changes above. The targetctl drop-in loses `--config ...` on its two
  `storage-reconcile` lines; Task 2.3's content compare of `TARGETCTL_DROPIN` follows.
- [ ] **Step 11: Run** Step 9's command, then `$PY scripts/tests/test_storage_vm_role.py` and `ansible-lint --offline`
  (as in 2.2). Expected: PASS. Commit `refactor(storage): one copy of the VG names, the IQNs and the config path`.
  It ships in the Task 3.2 PR; the `k3s_common` change renders the same file, so the deploy restarts no initiator.

### Task 2.11: packer: one manifest PR, a tested merge script, one clone source (audit fold-in)

Worktree P, branch `feat/retained-storage-vm`, after Task 0.1's rebase; it ships in the Task 3.3 Step 4 packer PR.
One commit touches A (`feat/retained-storage-vm`, ships in the Task 3.2 PR, which merges first). Source: D49,
genericity audit "packer `storage-vm`". No other task touches these files. Line numbers are at P `1be2ec2`.

Built-in choice, revised by D16 (Ben, 2026-11-23). Steps 1-4 (done, P `d3e25ec`) dropped the storage manifest PR
because terraform read no storage entry. D16 makes the storage root read it (Task 2.1a Step 9a), so Step 4a puts the
entry back, into the one manifest PR: `push-storage-manifest` stays gone, and so do its conflict with the k3s PR
(Task 3.3 Steps 5-6) and its extra apply. Departure from ADR :198 ("publishes the storage entry in its own job"):
the entry rides the shared `push-manifest` job, which runs when either build succeeded, so a failed k3s build still
publishes it, and a failed storage build keeps main's old `storage` entry. The PR title names every merged template,
not only k3s (ADR :200). Task 0.4 row 3 rewords ADR :198 and :200 to match. `storage/*.tf` still never names
`packer-manifest` (Task 2.1a Step 5): CI reads the entry.

**Files:**
- Modify: `.github/workflows/build.yml`: delete job `push-storage-manifest` (`:171-...`) and the `storage` job's
  `outputs` and `Get Packer build manifest` step; `push-manifest` (`:129-169`) calls the merge script.
- Create: `scripts/merge-manifest.sh`, `scripts/tests/test_merge_manifest.py`.
- Create: `source-clone.pkr.hcl`; Delete: `source-k3s.pkr.hcl`, `source-storage.pkr.hcl`.
- Modify: `config.pkr.hcl:14` (`local.templates`, `local.git_tag`), `build-base.pkr.hcl:35`, `build-k3s.pkr.hcl:27`,
  `build-storage.pkr.hcl:28` (`git_tag = local.git_tag.<role>`; build-level `source` blocks).
- Delete: `files/storage/rtslib-fb-targetctl.service.d/10-lvm.conf`; Modify: `build-storage.pkr.hcl:3-7` (its file
  provisioner), `scripts/storage.sh:52-54`.
- Modify: `scripts/tests/test_image_layout.py`, `.github/workflows/validate.yml` (run the new test), and `CLAUDE.md`,
  `README.md` and `docs/diagrams/build-pipeline.svg` where they show the storage manifest PR (diagram tooling per
  CLAUDE.md).
- Modify (A): `roles/storage_vm/templates/rtslib-fb-targetctl.service.d-50-homelab.conf.j2` (`[Unit]` gains
  `Wants=network-online.target` and `After=network-online.target`), `scripts/tests/test_storage_vm_role.py`.
- D16 rework (Step 4a): Modify `.github/workflows/build.yml` (`storage` job outputs, `push-manifest`),
  `scripts/merge-manifest.sh`, `scripts/tests/test_merge_manifest.py`, `scripts/tests/test_image_layout.py`, and the
  manifest lines of `CLAUDE.md`, `README.md` and `docs/diagrams/build-pipeline.svg`.

**Interfaces:**
- Produces: `scripts/merge-manifest.sh ROLE NEW CURRENT`, the merged manifest on stdout: CURRENT's builds without any
  named ROLE, plus NEW's last ROLE build, k3s first (`sort_by(.name != "k3s")`, until Step 6), with `last_run_uuid`
  set to that build's `packer_run_uuid`. Non-zero exit and no output when NEW has no ROLE build.
- One manifest PR per build, `packer-build-<run>`, from `push-manifest`.
- Step 4a (D16): `scripts/merge-manifest.sh NEEDS CURRENT`, where NEEDS is `push-manifest`'s `toJSON(needs)`: every
  job with `result == "success"` has its last build of the job's name merged into CURRENT, as above; non-zero exit and
  no output when no job succeeded or a successful job's manifest lacks its build. The manifest PR then carries `k3s`
  and `storage` entries, each with `artifact_id` (its VMID) and `custom_data.vm_name`.

- [ ] **Step 1: Write the failing tests.**
  - `scripts/tests/test_merge_manifest.py` (stdlib; runs the script with `bash` and `jq` on `PATH`):
    - CURRENT `[debian-13]` plus a new k3s gives `[k3s, debian-13]` and the new `last_run_uuid`;
    - CURRENT `[k3s (old), debian-13]` gives one k3s, the new one, first;
    - a `storage` entry in CURRENT is kept untouched;
    - NEW without a k3s build exits non-zero and prints nothing;
    - `build.yml` `push-manifest` runs `scripts/merge-manifest.sh k3s` and contains no `jq --argjson`.
  - `test_image_layout.py`:
    - `test_build_workflow_order` (`:214-234`): jobs are `{base, k3s, storage, create-release, push-manifest}`; `storage`
      has no `outputs`; drop the `push-storage-manifest` asserts (`:229-230`) and the inline-merge string assert
      (`:231-233`).
    - `test_sources_and_manifests` (`:82-95`): one `source "proxmox-clone" "clone"` in `source-clone.pkr.hcl`; each
      clone build has `source "source.proxmox-clone.clone"` with `name = "<role>"`, `vm_id = var.<role>_vm_id` and
      `vm_name = local.vm_name.<role>`; each manifest post-processor has `git_tag = local.git_tag.<role>`; the git_tag
      `regex(` appears once, in `config.pkr.hcl`.
    - `test_vm_ids_and_names` (`:71-80`): the role list is `local.templates` (one copy), not the literal
      `for role in ["base", "k3s", "storage"]` (`:80`).
    - Drop the source-text pins: the apt line (`:167`), the `install -D ... 10-lvm.conf` lines (`:171-172`, `:182`),
      `test_lvm_dropin` (`:186-188`, its file goes), and any other assert on indentation or a jq string. Keep the
      behavioural ones: seal order (`test_seal_contents`), the clone-only sudoers removal, no `open-iscsi`, F24 ordering
      (`test_storage_lvm_stock_activation_off`) and the `.builds[0]` ban.
    - `test_storage_image_has_no_targetctl_dropin`: no `10-lvm.conf` under `files/` or in `scripts/storage.sh`.
  - A `test_storage_vm_role.py`: the targetctl drop-in's non-comment lines (Task 2.3's compare) include
    `Wants=network-online.target` and `After=network-online.target` under `[Unit]`.
  - Run: `cd $P && python3 scripts/tests/test_merge_manifest.py; python3 scripts/tests/test_image_layout.py`, and
    `cd $A && $PY scripts/tests/test_storage_vm_role.py`. Expected: FAIL.
- [ ] **Step 2: Implement.**
  - `scripts/merge-manifest.sh`: `set -euo pipefail`, the k3s job's jq expression (`build.yml:153-154`, with
    `last_run_uuid`), the role as `$1`.
  - `build.yml` as in Files; `push-manifest` writes `$RUNNER_TEMP/new.json` as today and runs
    `scripts/merge-manifest.sh k3s "$RUNNER_TEMP/new.json" packer-manifest.json > "$RUNNER_TEMP/merged.json"`. It
    checks out packer too (the script lives there), into a subdirectory.
  - `config.pkr.hcl`: `templates = { base = var.base_vm_id, k3s = var.k3s_vm_id, storage = var.storage_vm_id }`;
    `vm_name = { for role, _ in local.templates : role => ... }`; `git_tag = { for role, name in local.vm_name : role =>
    "v${join(".", regex("(\\d+\\.\\d+\\.\\d+)-(\\d+)", name))}" }`.
  - `source-clone.pkr.hcl`: today's `source-k3s.pkr.hcl` without `vm_id`, `vm_name` and `template_description`, which
    move into each build's `source "source.proxmox-clone.clone" { name = "<role>" ... }`. That `-only='proxmox-clone.k3s'`
    and `-only='proxmox-clone.storage'` still match a renamed build-level source is UNVERIFIED for packer with plugin
    `v1.2.4`: PR CI's `packer validate` and the build's `-only` settle it. If `-only` no longer matches, keep the two
    source files and say why in a comment; the other changes stand.
  - The seal provisioner stays once per build file: HCL has no shared provisioner.
  - Delete `10-lvm.conf`, its file provisioner and `scripts/storage.sh:52-54`. A: add the two `[Unit]` lines.
- [ ] **Step 3: Run** Step 1's commands, then Task 0.1 Step 14's packer Run block. Expected: PASS, no `FAIL` line.
  `packer fmt -check`, `packer validate` and `shellcheck` run in PR CI only, as in Task 0.1.
- [ ] **Step 4: Commit**: P `ci(packer): one manifest PR from a tested merge script, one clone source` and
  `refactor(storage): targetctl ordering moves from the image to ansible`; A `fix(storage): order targetctl after
  network-online (moved from the image)`. Code commits, no `[skip ci]`.
- Merge events: the A commit rides the Task 3.2 PR; the P commits ride the Task 3.3 Step 4 packer PR. Task 3.3
  then has no `-storage` manifest PR (its Step 5 is skipped) and no manifest conflict to rebuild (Step 6 keeps only the
  `storage_nic` cherry-pick).
- [x] **Step 4a: D16 rework** (done 2026-11-23: P `ad5e0ae`, `44c9814`; follow-up on P `feat/retained-storage-vm`, on top of `e72e154`; rides the same Task 3.3
  Step 4 packer PR). Today the `storage` job has no `outputs` and `push-manifest` (`needs: k3s`) merges only the k3s
  entry, so terraform `main` would never get a `storage` entry and 2.1b's plan would fail closed.
  - Tests first:
    - `test_merge_manifest.py`, rewritten for `merge-manifest.sh NEEDS CURRENT`. A helper builds NEEDS as
      `{role: {'result': result, 'outputs': {'manifest': json.dumps({'builds': [...]})}}}` (`outputs` `{}` on failure):
      - `test_merges_every_successful_build`: k3s and storage `success`, CURRENT `[debian-13]` gives names
        `["k3s","debian-13","storage"]`, each the new entry;
      - `test_failed_build_keeps_its_old_entry`: storage `failure`, CURRENT `[k3s (old), debian-13, storage (old)]`
        gives the new k3s and the old storage entry unchanged;
      - `test_replaces_old_entries`: CURRENT's old k3s and storage are replaced, one entry each, the new ones;
      - `test_no_successful_build_fails_silently`: both `failure`: non-zero exit, empty stdout;
      - `test_success_without_its_build_fails`: k3s `success` whose manifest holds only a storage build: non-zero exit,
        empty stdout;
      - `test_push_manifest_uses_script`: the job passes `${{ toJSON(needs) }}` in env, runs
        `scripts/merge-manifest.sh "$RUNNER_TEMP/needs.json" packer-manifest.json`, and has no `jq --argjson` and no
        `needs.k3s.outputs`.
    - `test_image_layout.py` `test_build_workflow_order`:
      - the `storage` job has `manifest: ${{ steps.get-manifest.outputs.file }}` in `outputs` (drop the
        `assertNotIn("outputs:", jobs["storage"])` line and its comment), and its `Get Packer build manifest` step
        equals the k3s job's;
      - `push-manifest` has `needs: [k3s, storage]`, equal to `list(CLONES)`, and
        `if: ${{ !cancelled() && contains(needs.*.result, 'success') }}`;
      - `create-release` keeps `needs: k3s` and `select(.name=="k3s")` (the release tag stays the k3s entry's).
  - Run `cd $P && python3 scripts/tests/test_merge_manifest.py; python3 scripts/tests/test_image_layout.py`. Expected:
    FAIL (the script takes ROLE NEW CURRENT; `storage` has no outputs).
  - Implement:
    - `scripts/merge-manifest.sh NEEDS CURRENT`, `set -euo pipefail`: `roles=$(jq -r 'to_entries[] |
      select(.value.result == "success") | .key' "$1")`, fail when empty; for each role, `entry` is the last build of
      that name in `.[$role].outputs.manifest` (`jq -ce`, so a missing build fails), merged with today's expression
      (by name, k3s first until Step 6, `last_run_uuid` from the build). Hold the result in a variable and print it
      once at the end, so any failure prints nothing.
    - `build.yml`: the `storage` job gains the k3s job's `outputs` and `Get Packer build manifest` step. `push-manifest`
      gets `needs: [k3s, storage]`, the `if` above, and env `NEEDS: ${{ toJSON(needs) }}`; its script writes
      `printf '%s' "$NEEDS" > "$RUNNER_TEMP/needs.json"` in place of `new.json`, runs the script on it, and titles the
      PR `Update VM templates (<names>)`, the merged roles' `custom_data.vm_name` joined by `, `
      (`jq -r --slurpfile needs "$RUNNER_TEMP/needs.json" '[.builds[] | select(.name as $n | $needs[0][$n].result ==
      "success") | .custom_data.vm_name] | join(", ")' packer-manifest.json`). The job name becomes `Push manifest to
      terraform repo`.
    - `CLAUDE.md`, `README.md`, `build-pipeline.svg`: where they say only the k3s entry reaches terraform, say the
      one manifest PR carries every built template's entry (diagram tooling per CLAUDE.md).
  - Run the two tests again, then Task 0.1 Step 14's packer Run block. Expected: PASS, no `FAIL` line.
  - Commit P `ci(packer): the manifest PR carries the storage entry too (D16)`. Code commit, no `[skip ci]`.
- [ ] **Step 5: Check the first build** (part of Task 3.3 Step 4's Expected): one manifest PR opened,
  `packer-build-<run>`; `jq -r '[.builds[].name]' packer-manifest.json` on it reads `["k3s","debian-13","storage"]`;
  `jq -r '.builds[] | select(.name=="storage") | .artifact_id, .custom_data.vm_name' packer-manifest.json` prints `902`
  and a name equal to `qm config 902`'s `name`; `qm config 902` shows `template: 1`. This settles the UNVERIFIED
  `artifact_id` of a `proxmox-clone` build (expected the VMID, as `debian-13`'s `"900"` from `proxmox-iso` on main).
- [ ] **Step 6: Drop the k3s-first sort** (a later packer PR, only after Task 3.3 Step 8 has merged 2.1d, so terraform
  reads the k3s entry by name).
  - P branch `chore/manifest-merge-by-name` off `origin/main`: delete `| sort_by(.name != "k3s")` and the "k3s stays at
    builds[0]" comment from `scripts/merge-manifest.sh`; the test's order cases become "entries keep their order; the
    role's entry is replaced or appended".
  - Run: `python3 scripts/tests/test_merge_manifest.py`. Expected: PASS.
  - Commit `ci: the manifest merge no longer keeps k3s first (terraform reads by name)`.
  - PR when Ben asks. Squash with `[skip ci]` in the squash subject: a push to packer `main` is a full three-template
    build (CLAUDE.md), and this change only affects the next build's manifest PR.
  - Merge event: none. Check: `gh run list -R Starktastic-Homelab/packer --workflow build.yml -L 1 --json headSha`
    shows no run on the merge SHA. **Ben OK**.

---

### Task 2.4: apps: dispatch, addresses, alerts

Worktrees: AP (`~/.cache/claude-homelab-live/worktrees/apps-storage-vm`) and A (`.../ansible-storage-vm`). Line
numbers are at AP `b2c3d350` and A `a036b47`, before the Task 0.1 rebase; re-check them after it.

**Built since (local, unpushed, 2026-11-23):** the reconcile and the expire step refuse while the storage VM's boot
restore is not settled (A `f73f949`, `3717c25`); a push that touches `storage-host-metrics.yml` runs `storage.yml`,
and a test checks the push paths cover every imported playbook (A `ac22330`, `cfc3496`); `StorageReconcileFailing`
fires after 5 h, the worst D29 skip gap plus 1 h (AP `324dae90`, `a18f259d`).

**Files:**
- Create (AP): `.github/workflows/storage-dispatch.yaml`.
- Modify (AP): `templates/globals.yaml:13-14` (`storagePortal`, drop the `shortcut:` comment).
- Modify (AP): `services/operations/kube-prometheus-stack/manifests/storage-vm.yaml:1-2,13` (ScrapeConfig target, drop
  the `shortcut:` comment) and its `PrometheusRule` (three new alerts, runbook lines on all of them).
- Modify (AP): `scripts/check-alert-policy.py:361-411` (promtool cases in the `storage_tests` list).
- Modify (AP): `scripts/storage/tests/test_retained_inventory.py:129`. The portal is hardcoded there as
  `192.0.2.10:3260`; read it from `templates/globals.yaml` instead.
- Create (AP): `scripts/storage/tests/test_storage_workflows.py`.
- Modify (A): `roles/storage_vm/files/homelab_storage/reconcile.py:279-298` (`boot_check` writes a textfile).
- Create (A): `roles/storage_vm/tasks/host-metrics.yml` (dataset and lock gauges, written on the storage VM). This is
  a task file run on `storage`. Neither the `storage.yml` playbook nor `storage-dry-run.yml` includes it: both stay as
  2.2 pins them.
- Create (A): `storage-host-metrics.yml`, a playbook with no lock. It has two plays: the lab guard, as
  `import_playbook: storage-play-lab-guard.yml` (Task 2.2's audit fold-in; not a copy of `storage.yml:4-13`), then a
  play on `storage` (`gather_facts: false`) that runs `import_role: name: storage_vm,
  tasks_from: host-metrics.yml`. It never calls `lock-verify` or `maintenance_lock`.
- Modify (A), on `feat/retained-storage-vm` after Task 2.2's commits (it ships in the Task 3.2 PR):
  - `.github/workflows/storage.yml`: add the step `Write host gauges` (Step 2);
  - `scripts/storage_ready.py` (2.2's): add the step output `gauges` (Step 2), so a D29 window skip still writes the
    gauges;
  - `.github/workflows/deploy.yml` `paths-ignore`: add `storage-host-metrics.yml`,
    `scripts/tests/test_storage_vm_role.py` and `scripts/tests/test_storage_reconcile.py`. Origin/main
    `deploy.yml:12-25` lists none of them. The two test files are storage-only, and without this a PR that touches only
    them (such as the Task 3.5 PV-paths PR) starts a full deploy. `test_storage_fencer.py` stays deploy-triggering, as
    Part 5 expects;
  - `.github/workflows/validate.yml` job `syntax-check`: add `storage-host-metrics.yml` to the list at
    `validate.yml:155`.
- Test (A): `scripts/tests/test_storage_reconcile.py`, `scripts/tests/test_storage_vm_role.py`, and A's
  `scripts/tests/test_storage_workflows.py` from Task 2.2. Do not confuse it with the AP file of the same name below.

**Interfaces:**
- Consumes: D1 `<D1:storage_bridge_ip>` (the storage VM's address on `10.99.2.0/24`); the secret name
  `ORG_DISPATCH_TOKEN`, if Task 1.1 shows that apps can see it (`evidence/1.1/`); `metrics.write(name, samples)`
  (A `roles/storage_vm/files/homelab_storage/metrics.py:13`, textfile dir `/var/lib/prometheus/node-exporter`, `:6`).
- Produces:
  - the event `storage-changed` to `Starktastic-Homelab/ansible`, with no payload;
  - the textfile `storage-boot-check.prom`, holding `storage_boot_check_ok` (1 or 0) and
    `storage_boot_check_timestamp_seconds`;
  - the textfile `storage-host.prom`, holding `storage_dataset_avail_bytes{dataset="apps/k3s-block"}`, `storage_dataset_timestamp_seconds` and
    `storage_maintenance_lock_created_timestamp_seconds{operation}` (0 when the lock is free);
  - the `ready` step output `gauges` (`true` or `false`), read only by `Write host gauges`;
  - the alerts `StorageBootCheckFailed`, `StorageDatasetLow` and `MaintenanceLockStale`. `StorageVMDown` already exists
    (`storage-vm.yaml:26-33`, `for: 5m`), so D9 needs no new rule; it only gets its runbook line.

Two facts shape this task:
- **Metric source.** No exporter runs on pve or on the runner. A has no node-exporter role outside `storage_vm`, and
  apps has no scrape job besides `storage-vm`. `check-alert-policy.py:353-354` also requires every `job=` matcher in
  `storage-vm.yaml` to be `storage-vm`. So both new gauges are written on the storage VM, whose node-exporter is
  already scraped. The writes come from the workflow step `Write host gauges` in the ansible `storage.yml` workflow,
  which runs `storage-host-metrics.yml`:
  - the dataset figures from a read-only `df` on pve;
  - the lock figure from `/maintenance/operation.json`, the same mount `deploy.yml:41` uses. 2.2's job already mounts
    it.

  The step sits after `ready` and before 2.2's `held` step, and its `if` depends only on the `ready` step's `gauges`
  output, not on `ready` itself. This supersedes the "gated on `ready == 'true'`" wording in Task 2.2 Step 3 (steps 3
  and 4-8 notes). D29's window skip (decided, Ben 2026-11-23) makes `ready` false on scheduled runs at 02:05 daily,
  Sunday 01:05 and, with the provisional `<D29:backup_end>` 06:00 and `<D29:maint_end>` 07:00, 05:05 daily and
  Sunday 06:05. A step gated on `ready` would then write nothing from 00:05 to 03:05 and from 04:05 to 07:05 every
  Sunday, 3 h gaps that sit on the
  3 h staleness leg of `StorageDatasetLow`. The step writes gauges
  only and changes no LVM or target, so it runs inside the windows too. It also runs while another operation
  (deploy, terraform, a cutover, or a failed run that kept the lock) holds the lock, so it writes every hour and
  `MaintenanceLockStale` sees the real holder. It is `continue-on-error`, so a gauge failure never skips the
  reconcile or the release. `storage-expiry.yml` does not get it; hourly is enough.
- **Boot check.** The boot check has no metric today (`reconcile.py:279-298` only logs).

- [ ] **Step 1: Write the failing tests.**
  - AP `test_storage_workflows.py`:
    - `test_dispatch_on_inventory_push_only`. Load `storage-dispatch.yaml` and assert:
      - `doc.get('on', doc.get(True)) == {'push': {'branches': ['main'],
        'paths': ['infrastructure/base-configs/files/retained-volumes.json']}}`;
      - `event-type == 'storage-changed'`;
      - `repository == 'Starktastic-Homelab/ansible'`.

      PyYAML (YAML 1.1) loads a bare `on:` key as the boolean `True`, hence the lookup.
    - `test_dispatch_sends_no_sha`: no `client-payload` key, and no `github.sha` anywhere in the file. The ADR says
      `storage.yml` re-resolves `main` itself.
  - AP `check-alert-policy.py`, a firing case and a quiet case for each alert:
    - `StorageBootCheckFailed`. Fires on `storage_boot_check_ok 0x30`. Fires on a timestamp older than
      `node_boot_time_seconds`. Quiet on `1x30` with a timestamp newer than the boot time.
    - `StorageDatasetLow`. Fires when avail is 19 GiB. Fires on a timestamp more than 3 h old. Quiet when avail
      is 21 GiB and fresh. Quiet when avail is 21 GiB and the timestamp is 2 h old (one failed hourly write; the
      gauges run every hour, window skips included).
    - `MaintenanceLockStale`. Fires when `created` is 7 h old. Quiet when it is 1 h old. Quiet on `0` (lock free).
  - AP `test_render_pv_shape`: expects the portal from `globals.yaml`, so it fails while the fixture still says
    `192.0.2.10`.
  - A `test_storage_reconcile.py`:
    - `test_boot_check_writes_metric`: with a missing LUN binding, `boot_check` returns 1 and calls
      `metrics.write('storage-boot-check', ...)` with `storage_boot_check_ok` 0 and a timestamp;
    - the clean case writes 1.
  - A `test_storage_vm_role.py`:
    - `test_host_metrics_reads_only_on_pve`: every task in `host-metrics.yml` delegated to a pve host runs only `df`,
      with `changed_when: false`;
    - `test_host_metrics_never_reads_nonce`: the lock task reads `operation` and `created_at` only, and the string
      `nonce` does not occur.
    - `test_host_metrics_playbook_takes_no_lock`: `storage-host-metrics.yml` plays are, by hosts, `all` (lab guard)
      and `storage` (imports `tasks_from: host-metrics.yml`), and the text has no `lock-verify` or `maintenance_lock`.
    - In `test_lab_guard` (`test_storage_vm_role.py:130-131`), add `storage-host-metrics.yml` to the playbook tuple.
  - A `test_storage_workflows.py` (2.2's file):
    - `test_host_gauges_before_held_unlocked`: in `storage.yml`, the step `Write host gauges` comes after id `ready`
      and before id `held`; its `if` is exactly `steps.ready.outputs.gauges == 'true'` and mentions neither `held` nor
      `lock`; it has `continue-on-error: true`; its run text has `-i inventory/proxmox.yml -i inventory/hosts.yml`,
      `sshpass` and `storage-host-metrics.yml`, and no `maintenance_lock.py` and no `-e`.
    - `test_window_skip_still_writes_gauges` (D29): `storage_ready.main(hosts=[...one host...], event='schedule',
      now=<02:05 local>)` with real PV paths writes `ready=false` and `gauges=true`; at 03:05 it writes `ready=true`
      and `gauges=true`; inside the window with `hosts=[]` or the placeholder PV paths it writes `gauges=false`; with
      `event='workflow_dispatch'` at 02:05 it writes both `true`.
    - `test_deploy_ignores_storage_only_paths`: add the three paths from Files to its "contains" list.
    - 2.2's "every step after `ready` has an `if` that is false when `ready` is `'false'`" check gets one named
      exemption, `Write host gauges`, next to the credential cleanup: inside a window `ready` is `'false'` while
      `gauges` is `'true'`, and the step must run. `test_host_gauges_before_held_unlocked` pins its `if` instead.
    - 2.2's `test_dry_run_before_lock_then_apply_then_release`, `test_no_sha_from_payload` and
      `test_schedule_skips_inside_windows` must still pass unchanged with the new step and the new output.
      `test_triggers` stays as is: the push
      paths already hold `roles/storage_vm/**`, and a change to `storage-host-metrics.yml` alone waits for the next
      hourly run.

  Run, in AP: `python3 -m unittest discover -s scripts/storage/tests -v && python3 scripts/check-alert-policy.py
  <promtool cmd>`. Then in A: `python3 scripts/tests/test_storage_reconcile.py &&
  python3 scripts/tests/test_storage_vm_role.py && PINNED_LOCK_HELPER=$H/scripts/maintenance_lock.py
  python3 scripts/tests/test_storage_workflows.py` (as 2.2 Step 2 runs it).

  Expected: FAIL. The workflow file is missing, the alerts are missing (KeyError in `storage[alert]`), and
  `boot_check` writes nothing.
- [ ] **Step 2: Implement.**
  - **`storage-dispatch.yaml`:**
    - one job `dispatch` on `ubuntu-latest`;
    - one step `peter-evans/repository-dispatch@v4` with `token: ${{ secrets.ORG_DISPATCH_TOKEN }}`,
      `repository: Starktastic-Homelab/ansible` and `event-type: storage-changed`;
    - the same action and version as terraform `apply.yml:195-199`.

    A separate file with a `paths:` filter is smaller than another branch in `refresh.yaml`'s bash. `refresh.yaml`
    already refreshes `base-configs` for this path (`refresh.yaml:97-99`). If 1.1 shows the token is not visible to
    apps, Ben grants it, or this file is left out and the hourly run is the only trigger. Keep the test either way.
  - **Addresses:**
    - `storagePortal: "<D1:storage_bridge_ip>:3260"`;
    - the ScrapeConfig target `"<D1:storage_bridge_ip>:9100"`.

    `check-alert-policy.py:355-357` already asserts that the two hosts match.
  - **`boot_check`:** before returning, call `metrics.write('storage-boot-check', [('storage_boot_check_ok', {}, 0 if
    errors else 1), ('storage_boot_check_timestamp_seconds', {}, time.time())])`. The write sits outside `LIO_LOCK`
    and changes nothing else.
  - **`host-metrics.yml`** (a task file, run on `storage`):
    - `df -B1 --output=size,avail <k3s-block mount>`, delegated to `groups['proxmox_hosts'][0]` with
      `changed_when: false`. The mount path is UNVERIFIED; `/mnt/pve/k3s-block` is the PVE default for an NFS storage
      of that name. Task 1.1 reads the real path into `evidence/1.1/`.
    - Read `/maintenance/operation.json`, delegated to `localhost` (the workflow container), keeping `operation` and
      `created_at` only.
    - Write `storage-host.prom` on the storage VM atomically, as `metrics.py` does (temporary file plus rename).
    - Only `storage-host-metrics.yml` runs this file (see Files).
  - **`storage_ready.main`** (2.2's): also write `gauges=true|false` to `$GITHUB_OUTPUT`. `gauges` is `true` exactly
    when `skip_reason` gives `None`, whatever the window. On a schedule run inside a window, main still prints the
    window line and writes `ready=false`, but now reads the storage group (read only, no vault) before it exits, to
    set `gauges`. This moves 2.2's "before reading the inventory": an inventory error inside a window now fails the
    step, as it does outside one. Outside a window `gauges` equals `ready`.
  - **Step `Write host gauges`** in A `.github/workflows/storage.yml`, inserted between 2.2's step 3 (id `ready`) and
    step 4 (id `held`):
    - `if: steps.ready.outputs.gauges == 'true'`, so it is skipped under 2.2's "touch nothing" rule (an empty
      `storage` group, or `storage_vm_pv_devices` still the placeholder), runs inside D29's backup windows (it writes
      gauges only: a read-only `df` and a textfile, no LVM or target change), and never depends on `ready`, `held` or
      `acquired`;
    - `continue-on-error: true`;
    - run: `apt-get update && apt-get install -y sshpass` (as `proxmox-guest-startup.yml:37-38`; one run block, so the
      step keeps its `if`), then `ansible-playbook -i inventory/proxmox.yml -i inventory/hosts.yml
      --vault-password-file .vault_pass --private-key private_key.pem storage-host-metrics.yml`.
    - Why both inventories: `proxmox_hosts` (pve, `10.9.9.20`, root) is defined only in `inventory/hosts.yml:2-6`, and
      `inventory/proxmox.yml` has no such group. With only `proxmox.yml`, `groups['proxmox_hosts'][0]` is undefined.
      The pve login uses the vaulted `group_vars/proxmox_hosts/` vars and `sshpass`, as the `proxmox-guest-startup.yml`
      workflow does (`:37-38,49`).
    - UNVERIFIED: that the pve password login works with `--private-key private_key.pem` on the same command line
      (ssh tries the key, then the password). A failure is non-blocking, and shows as the `StorageDatasetLow`
      staleness leg within 3 h. Check the first run's step log in Task 3.5.
    - Gate: the `df` figure is only as good as Task 1.1's answer to 219 vs 288 GiB (D2). If 1.1 shows that the NFS
      `df` does not reflect the TrueNAS quota, stop and bring the metric source to Ben.
  - **Alerts in `storage-vm.yaml`:**

    ```yaml
    - alert: StorageBootCheckFailed   # D7
      expr: |
        storage_boot_check_ok{job="storage-vm"} == 0
        or storage_boot_check_timestamp_seconds{job="storage-vm"}
           < on (instance, job) node_boot_time_seconds{job="storage-vm"}
        or absent(storage_boot_check_ok{job="storage-vm"})
      for: 10m
      labels: {severity: critical}
    - alert: StorageDatasetLow
      expr: |
        storage_dataset_avail_bytes{job="storage-vm"} < 20 * 1024^3
        or time() - storage_dataset_timestamp_seconds{job="storage-vm"} > 3 * 3600
      for: 15m
      labels: {severity: warning}
    - alert: MaintenanceLockStale
      expr: |
        storage_maintenance_lock_created_timestamp_seconds{job="storage-vm"} > 0
        and time() - storage_maintenance_lock_created_timestamp_seconds{job="storage-vm"} > 6 * 3600
      labels: {severity: warning}
    ```
  - The floor is absolute, 20 GiB (Ben, 2026-11-23). pve's `df` size is used-by-dataset plus available (about 150 GiB
    while snapshots hold 137.9 GiB), not the 288 GiB quota, so a ratio of it means nothing; `df` avail is already the
    quota-bounded figure. No `storage_dataset_size_bytes` gauge.

  - **Runbook lines**, as the last sentence of each `description`:
    - `StorageBootCheckFailed`: `See docs/runbooks/storage-vm-restore.md, "Boot check failed".`
    - `StorageVMDown`: `See docs/runbooks/storage-vm-rebuild.md, "VM down".` Add one sentence to its description:
      after wave 1, Prometheus runs on `regen`, so this alert dies with the VM, and the healthchecks.io Watchdog
      dead-man is the out-of-cluster signal (D7, D9).
    - `StorageDatasetLow`: `See docs/runbooks/storage-vm-growth.md, "Dataset full".`
    - `MaintenanceLockStale`: `See docs/runbooks/storage-vm-cutover.md, "Stale lock".`
- [ ] **Step 3: Run** the Step 1 commands, plus `yamllint` and kubeconform as `validate-and-diff.yml` runs them. In A
  also run `$PY scripts/tests/test_workflow_credentials.py` and `ansible-lint --offline` as 2.2 Step 4 does.
  Expected: PASS.
- [ ] **Step 4: Commit** each repo separately.
  - AP: `feat(storage): dispatch storage-changed, real storage VM address, boot, dataset and lock alerts`.
  - A: `feat(storage): boot check and host gauges for the storage VM alerts`.

  Both are code commits, so they carry no `[skip ci]`. Merge events:
  - AP rides the AP branch merge in Task 3.6: ArgoCD syncs, and `globals.yaml` makes `refresh.yaml` refresh every
    app;
  - A rides the ansible storage PR in Task 3.2: a deploy, with k3s restarting on every node.

### Task 2.5: apps: the copy Job

Worktree AP. This is new code: `scripts/storage/migrate_volume.py` and `scripts/storage/copy_volume.sh`.

**Files:**
- Create: `scripts/storage/migrate_volume.py`, `scripts/storage/copy_volume.sh`.
- Create: `scripts/storage/tests/test_migrate_volume.py`.
- Modify: `scripts/storage/README.md` (one paragraph: what the tool is, and that it runs only on the tool host
  that Task 4.0 Step 7 settles, D23).

**Interfaces:**
- Consumes:
  - the inventory entry (`infrastructure/base-configs/files/retained-volumes.json`);
  - the source binding file: the one YAML doc under `infrastructure/base-configs/templates/**` with
    `kind: PersistentVolume` and `csi.volumeHandle == homelab//k3s-block/9999/vm-9999-<id>.raw` (files containing
    `{{` are skipped; the scouts found no `{{` in any binding file);
  - live JSON from `kubectl get pods,pv,pvc,volumeattachments,jobs,cronjobs,deployments,statefulsets -A -o json`;
  - `gh run list` and `gh pr list`;
  - the lock record `<lock-root>/operation.json` (default `/var/lib/homelab-maintenance`), reading only `operation`
    and `owner`.
- Produces:
  - `migrate_volume.py precheck <id> [--direction forward|reverse]`: exit 0, or exit 1 with one `refused: <reason>`
    line per failure;
  - `migrate_volume.py render <id> --direction forward|reverse --out <dir>`: writes `pairs.yaml` (two PV/PVC pairs),
    `job.yaml` (ConfigMap `migrate-<id>` holding `copy_volume.sh`, plus Job `migrate-<id>`) and `render.json`
    (the handles, sizes and claims it used, and `apps_head`, the clone's `git rev-parse HEAD`). Reverse runs in two
    passes: without a passing `<dir>/gate.log` it runs the reverse `decide`, and if that gives no reason writes only
    `gate.yaml` and `render.json`, prints `gate-required` and exits 0 (the source gate below);
  - the log lines `gate-fsck-ok <id>` and `gate-guard-ok <id>` (reverse source gate);
  - `migrate_volume.py verify-teardown <id>`: exit 0 only when nothing labelled
    `homelab.starktastic.net/migration=<id>` is left and no VolumeAttachment names a `migrate-*-<id>` PV;
  - the rule **id == x**: a migrated entry's `id` equals the `<x>` of its old handle `vm-9999-<x>.raw`. This is how
    the tool finds the source without a new inventory field. Task 4.W must use these ids. The rendered PV is named
    `<id>` and is cluster-scoped. On apps origin/main `c5f60a0d` the binding files carry 33 distinct `<x>`
    values, and none of them is an existing PV or PVC name (checked by `git grep` while drafting). Ids are permanent, so
    Ben confirms the rule before the first inventory PR.
  - **Migration-only code.** `migrate_volume.py`, `copy_volume.sh`, `test_migrate_volume.py` and the README paragraph
    are deleted in Part 5 (Task 5.9), once the last cutover and its rollback window are over. Nothing outside the
    migration may import, call or render them, and no workflow runs them.

**Settled open fact m7 (Proxmox CSI v0.22, Block mode and a second PV on one handle).** Sources: the upstream
`sergelogvinov/proxmox-csi-plugin` repo, read through a summariser on 2026-11-21. `pkg/csi/node.go` was read at tag
`v0.22.0`; `pkg/csi/controller.go` and `pkg/csi/utils.go` at `v0.22.1`. Chart 0.5.16, pinned at
`infrastructure/system/proxmox-csi/app.yaml`, ships appVersion `v0.22.1`, and `values.yaml` does not override the
image. The scouts' `v0.22.0` is one patch behind.
- **Block mode: SETTLED, supported.**
  - `NodeStageVolume` returns early for `GetBlock()` ("raw device, skipped").
  - `NodePublishVolume` bind-mounts the device file into the pod.
  - `SINGLE_NODE_SINGLE_WRITER` (RWOP) is in the accepted access modes.
  - The controller rejects no access type.
- **Second PV on the same handle: SETTLED on the driver side.**
  - `attachVolume` looks the disk up in the VM config by disk path (`VolumeLun(cfgs.Current, vol.Disk())`) and
    reuses the lun it is already on.
  - `detachVolume` detaches by the same disk key.
  - So two PVs on one handle on one node share one SCSI slot, and detaching either one pulls the disk from under the
    other.
- **The same question on the Kubernetes side: SETTLED** (kubernetes `master`, not the cluster's tag; this naming
  has been stable for years, but re-read it at the k3s version in Task 1.1 if in doubt).
  `pkg/volume/csi/csi_attacher.go` names a VolumeAttachment
  `csi-<sha256(handle + driver + node)>`. Two PVs on one handle on one node therefore share one VA object, and only
  `spec.source.persistentVolumeName` tells them apart.

  Consequence: the tool matches VolumeAttachments on every PV that carries the handle, never on a PV name alone.
  RWOP does not protect a copy, because the temporary PVC and the app's PVC are different claims. The protection is
  the hold, the pre-check, and the exclusive open in `copy_volume.sh`.
- **UNVERIFIED:** `generateWWN(vol.PV(), lun)` feeds the WWN, and `vol` comes from
  `NewVolumeFromVolumeID(<handle>)`, so `vol.PV()` is most likely a function of the handle. The `pkg/volume` source
  returned 404 and was not read.
- **Still to confirm read-only in Task 1.1:** `kubectl get csidriver csi.proxmox.sinextra.dev -o yaml`
  (`attachRequired`, `volumeLifecycleModes`) and the running controller and node image tags. If either shows
  something other than v0.22.x with Persistent mode, STOP and bring it to Ben.
- **Target side:** democratic-csi node-manual with `volumeMode: Block` was already exercised in the lab. See
  `~/.cache/claude-homelab-live/storage-lab/b5/copy.yaml` and lab report `:337`. `attachRequired: true`
  (`infrastructure/system/democratic-csi/manifests/values.yaml:5`), so node-manual volumes get VAs too.

**What `render` emits** (Python dicts dumped with PyYAML, which `requirements.txt` already pins; no template engine).
All objects go in the entry's namespace and carry the label `homelab.starktastic.net/migration=<id>`.
- **PV and PVC `migrate-src-<id>` (forward):**
  - driver `csi.proxmox.sinextra.dev`;
  - handle copied from the binding file, `fsType` omitted;
  - `volumeAttributes` copied from the binding file (`storage: k3s-block`, `cache: none`);
  - `nodeAffinity` copied verbatim from the binding file (topology region `homelab`, zone `pve`);
  - capacity = the binding PV's capacity;
  - `volumeMode: Block`, `ReadWriteOncePod`, `persistentVolumeReclaimPolicy: Retain`, `storageClassName: ""`;
  - a `claimRef` with no uid; the PVC has `volumeName`.
- **PV and PVC `migrate-dst-<id>` (forward):**
  - driver `org.democratic-csi.node-manual`, handle `<id>`;
  - `volumeAttributes` equal to the renderer's (`retained-volumes.yaml:22-28`: portal from `globals.yaml`,
    iqn `iqn.2026-11.net.starktastic.storage:<id>`, `lun: "0"`, `node_attach_driver: iscsi`,
    `provisioner_driver: node-manual`);
  - capacity = the inventory `size`;
  - `volumeMode: Block`, RWOP, `Retain`.
- **Reverse:** the same two pairs with the roles swapped. `migrate-src-<id>` is the node-manual LV, and
  `migrate-dst-<id>` is the old image. A PV's `csi` spec is immutable, so the forward pairs must be torn down
  (`verify-teardown <id>` exit 0) before a reverse render is applied. Precheck's `handle` reason refuses otherwise.
- **Reverse source gate** (4.T R2 step 4; the reverse render's first step). The LV is copied back only if it is a
  clean filesystem that the app's guard (the generic guard, D47) accepts. Pass 1 of `render --direction reverse`
  first runs the reverse `decide` (lock, writer, rebuild and the rest) plus the guard-template check below, prints
  every reason found, and on any reason exits 1 and writes nothing, so no gate Job is applied unchecked. Otherwise
  it writes `gate.yaml` (ConfigMap `migrate-<id>` included). Pass 1 only writes files, so R2's entry check can run
  it before the hold: there a `gate` line is the one that matters, because the others clear once the hold is in place.
  - PV and PVC `migrate-gate-<id>`: node-manual, handle `<id>`, `volumeMode: Block`, RWOP, `Retain`, labelled as
    above. Job `migrate-gate-<id>` (same image, `securityContext` and `nodeSelector` as the copy Job, ConfigMap
    `migrate-<id>`) runs `sh /migrate/copy_volume.sh gate <id>` with it at `/dev/migrate-src`: `e2fsck -fn "$SRC"`,
    any exit other than 0 refuses, then it prints `gate-fsck-ok <id>`. Nothing is written: `-n` opens the device
    read-only.
  - PV and PVC `migrate-guard-<id>`: the same handle with `volumeMode: Filesystem`, `fsType: ext4`,
    `mountOptions: [ro, noload]` (no journal replay), and the pod volume `readOnly: true`. Job `migrate-guard-<id>`
    copies the guard init container whole (image, command, args, env, `securityContext`, mounts), the pod-level
    `securityContext`, and every non-PVC volume it mounts, from the live pod template that references `<new_claim>`.
    That template is found with the `writer` matcher (a claim reference, or a `volumeClaimTemplates` name that derives
    it); it is still there under the hold at 0 replicas. The claim volume is pointed at `migrate-guard-<id>`. The guard
    is not reimplemented. A first init container (pinned python image) refuses unless `/proc/self/mounts` shows that
    mount `ro`; the main container prints `gate-guard-ok <id>`. Render refuses `gate` on zero or two matching
    templates, on zero or two init containers that mount the claim, or if that init container also mounts another
    PVC.
  - UNVERIFIED (no lab run): that democratic-csi node-manual passes PV `mountOptions` to its NodeStage mount, and that
    an ext4 `ro,noload` mount of an MMP filesystem writes nothing. The in-pod `ro` check sees only the pod's bind
    mount, not the staging mount, so it does not prove this. If the `ro` check refuses, stop: never run the guard on
    a read-write mount.
  - First proof (D37): this read-only gate mount is first exercised on the `f1-canary` LV in Task 3.6, before any
    cutover, so R2 never runs it for the first time. This task only writes and unit-tests the render; it proves
    nothing live. Until 3.6 records that proof, treat the gate as unproven, and an id with no guard the gate can run
    gets no reverse copy (Ben accepts that per id, D37).
  - The two halves run one after the other, never together (**Ben OK** at each apply): the Block half, then, once
    its Job is Succeeded and no VA names `migrate-gate-<id>`, the Filesystem half. Their logs go, in order, to
    `<dir>/gate.log`. Then tear the gate objects down and run `verify-teardown <id>` (it covers them by label).
  - Pass 2, the same `render` command, writes `pairs.yaml` and `job.yaml` only if `gate.log` holds both ok lines for
    `<id>` and no `migrate-gate-<id>` or `migrate-guard-<id>` PV is live (`handle` otherwise). Else it refuses `gate`
    and writes nothing. Both passes check `stale-clone`; HEAD may move between them (4.T's clone rule re-fetches),
    which does not force the gate again.
- **Every PV and PVC** carries the annotation `argocd.argoproj.io/sync-options: Prune=false,Delete=false`. None
  carries an `argocd.argoproj.io/tracking-id` annotation or an `app.kubernetes.io/instance` label, so no Argo app
  owns them. `render` refuses an `--out` inside the repo, so they can never land in a path Argo reads. The rendered
  set goes to `evidence/4.T-<id>/`.
- **The Job `migrate-<id>`:**
  - `backoffLimit: 0`, `restartPolicy: Never`, `activeDeadlineSeconds: 14400`. The longest copy is Jellyfin's 64 GiB,
    read three times. Killing a raw copy is harmless.
  - No `ttlSecondsAfterFinished`: the pod log is evidence.
  - `nodeSelector: {node-role.kubernetes.io/worker: "true"}`. The node pin is the RWOP claims plus the source PV's
    topology.
  - One container, image `python@sha256:8c9a3bf2d6dea60d60a2ae2a07c2b2fb1e7d8daed64b146b6792c74ae0d62ac4`, the
    digest Grafana's `postgres-enrollment-acceptance` gate uses
    (`services/operations/kube-prometheus-stack/values.yaml:300` after 1.3a; since apps#1707 every guard uses the same digest).
    UNVERIFIED: that it ships `dd`, `cmp`, `blockdev`, `e2fsck`, `tune2fs`, `dumpe2fs` and `resize2fs`. Step 1 checks
    this offline. If a tool is missing, pin another image by digest that has them, and pin that digest in the test.
    Result (2026-11-23): the python digest ships none of the e2fsprogs tools, so the copy and gate Jobs run the democratic-csi
    node plugin image, read at render time from `node.driver.image` in
    `infrastructure/system/democratic-csi/manifests/values.yaml` (no second pin); the guard Job keeps the python digest.
  - `command: [sh, /migrate/copy_volume.sh, <direction>, <inventory size bytes>]`.
  - `volumeDevices` `/dev/migrate-src` and `/dev/migrate-dst`; the ConfigMap is mounted at `/migrate`.
  - `securityContext`: `runAsUser: 0`, `allowPrivilegeEscalation: false`, capabilities drop ALL,
    `readOnlyRootFilesystem: true`, seccomp `RuntimeDefault`. Device nodes are root-owned, so no capability is needed.
    This is UNVERIFIED until the first `regen` copy (tempo). On `EACCES`, stop and bring it to Ben; do not add
    `privileged`.

**What `copy_volume.sh` does** (behaviour; `set -eu`, every step logged; any failure exits non-zero and leaves the
source untouched):
0. `SRC=${MIGRATE_SRC:-/dev/migrate-src}` and `DST=${MIGRATE_DST:-/dev/migrate-dst}`. The steps below use these;
   the env override exists for the loop-device test only.
   `$1` is `forward`, `reverse` or `gate` (then `$2` is the id). `gate` runs `e2fsck -fn "$SRC"`, prints
   `gate-fsck-ok <id>` on exit 0 and stops; it never reaches the steps below, so a reverse `copy.log` has no `e2fsck`
   line.
1. `S=$(blockdev --getsize64 /dev/migrate-src)` and `T=$(blockdev --getsize64 /dev/migrate-dst)`. Refuse if `T < S`,
   or if `S % 4194304 != 0`. Reverse also refuses unless `T == S`: the old image's live byte size must equal the
   source bytes (4.T Step 1 checked the image against `<bytes>` before the forward hold; this re-checks it live).
2. Hold an exclusive open (`O_EXCL`, through `python3 -c`) on both devices for the whole of steps 3-4, then release it.
   - A same-node mount of either device during the copy then fails with `EBUSY`.
   - It does not cover a writer on another node. That case is covered by the hold and by the `precheck` run before
     and after the Job.
   - `dd` and `cmp` do not open with `O_EXCL`, so they still run. `e2fsck`, `tune2fs` and `resize2fs` in step 5 open
     the device exclusively themselves, so the hold is released before them.
3. `dd if=/dev/migrate-src of=/dev/migrate-dst bs=4M count=$((S/4194304)) iflag=direct oflag=direct conv=fsync`.
   There is no `conv=sparse` (ADR Migration 3.4).
4. `cmp -n "$S" /dev/migrate-src /dev/migrate-dst`.
5. Forward only, on the target:
   1. `e2fsck -fp /dev/migrate-dst`, where any exit other than 0 stops the Job. An exit of 1 means the copy differs
      from a clean filesystem, and that is Ben's call.
   2. `tune2fs -O mmp -E mmp_update_interval=5 -e remount-ro /dev/migrate-dst`.
   3. `dumpe2fs -h /dev/migrate-dst`, matched whitespace-tolerantly (`dumpe2fs` pads its fields):
      `^Filesystem features:.*\bmmp\b`, `^Errors behavior:\s+Remount read-only$` and
      `^MMP update interval:\s+5$`.
   4. If `$2 > S`: `resize2fs /dev/migrate-dst`, then `dumpe2fs -h` again, where block count times block size must
      equal `T`.
6. Reverse: steps 1-4 only. The old image keeps MMP and `remount-ro`, which Proxmox CSI mounts fine (MMP adds about
   42-45 s per mount, ADR `:257-258`).
7. Print `copy-ok <direction> <S> <T>`.

Rollback limit: if step 5.4 grew the filesystem, a reverse copy fails its own `T >= S` check, because the old image
is smaller. Recommendation for Task 4.W: keep every migrated `size` equal to its binding capacity (no growth during the
migration), so that `resize2fs` never runs before reconciliation. Grow afterwards with the growth runbook.

**What `precheck <id>` refuses** (Review Focus 1, 2 and 5). It is pure `decide(entry, binding, live, ci, lock, clone,
direction) -> [reasons]` plus thin collectors.
- `stale-clone`: `clone` is `{head, origin_main, dirty}`; it refuses when `head != origin_main` (the local
  `origin/main` ref; the tool never fetches, 4.T's clone rule does) or the work tree is dirty. `render` refuses the
  same way before writing anything. Under the clone rule the tool clone is always detached at a fresh `origin/main`,
  so this never fires on the forward path; it catches a skipped fetch.
- `no-entry`: the entry is missing, its `origin` is not `migrated`, or it already has `copied` (forward only).
- `handle`:
  - no binding PV carries `vm-9999-<id>.raw`, or more than one does;
  - the live PV with that name has a different handle, driver or capacity;
  - the live rendered PV `<id>` is missing, or has a handle other than `<id>` or a driver other than node-manual;
  - an existing `migrate-*-<id>` PV has a handle other than the expected one.
- `size`: forward needs inventory size >= binding capacity; reverse needs binding capacity >= inventory size.
- `writer`, on either handle:
  - a Pod in any phase except Succeeded or Failed references a PVC bound to any PV with that handle;
  - a VolumeAttachment's `spec.source.persistentVolumeName` is any PV with that handle;
  - a non-suspended CronJob, or an unfinished Job, references such a PVC;
  - a Deployment or StatefulSet with `spec.replicas > 0` references such a PVC, directly or by a
    `volumeClaimTemplates` name that derives it.

  This version is stricter than Review Focus 1. Precheck runs before the apply and again after the Job has finished
  (its pod is Succeeded, its VAs are gone), so it never has to allow the Job's own VA.
- `rebuild`:
  - a `build.yml` run in packer, an `apply.yml` run in terraform or a `deploy.yml` run in ansible is `queued`,
    `in_progress`, `waiting`, `requested` or `pending`;
  - any open PR in packer, terraform or ansible has a non-null `autoMergeRequest`.

  Open PRs without auto-merge, drift PRs among them, do not block (Review Focus 5).
- `lock`: `operation.json` is missing, or its `operation` is not `storage-cutover:<id>[:<id2>]` with `<id>` among the
  listed ids. The cutover (4.T step 2) takes the lock under that name. A D14 shared pod lists both ids, so its second
  copy Job passes under the same hold. `:` is allowed by the helper (`maintenance_lock.py:129`). The nonce is never
  read. The `lock` reason is the same in both directions, so a reverse precheck after Step 10.3 released the lock
  refuses until R2 step 1 takes it again.

- [ ] **Step 1: Check the image offline.**
  - Run: `docker run --rm python@sha256:8c9a3bf2d6dea60d60a2ae2a07c2b2fb1e7d8daed64b146b6792c74ae0d62ac4 sh -c 'for t in
    dd cmp blockdev e2fsck tune2fs dumpe2fs resize2fs; do command -v $t || echo MISSING $t; done'`.
  - Expected: seven paths, no `MISSING`. Otherwise pick and pin another image (see above).
- [ ] **Step 2: Write the failing tests** in `scripts/storage/tests/test_migrate_volume.py`. They use fixture dicts for
  `live`, `ci` and `lock`, a temporary repo tree for the binding files, and one `entry('tempo', origin='migrated')`.
  - `test_refuses_when_source_has_pod` (Review Focus 1). Each of these gives a `writer` reason:
    - a Running pod on the old claim;
    - a Pending pod on the old claim;
    - a VA whose PV is the old PV;
    - an unsuspended CronJob on the old claim;
    - an STS with `replicas: 1` whose template derives the old claim.

    `replicas: 0`, a Succeeded pod and a suspended CronJob give no `writer` reason.
  - `test_refuses_va_on_shared_handle`. A VA named for the shared handle, whose `persistentVolumeName` is the app PV,
    gives `writer`. The VA is matched by handle, so a VA that names any PV carrying the handle counts.
  - `test_refuses_handle_not_in_inventory` (Review Focus 2). Each of these gives `handle`:
    - no binding PV with `vm-9999-tempo.raw`;
    - two binding PVs with it;
    - a live PV whose handle differs from git;
    - a rendered PV `tempo` with handle `loki`;
    - a stale `migrate-dst-tempo` PV with another handle.

    `render` refuses the same cases and writes nothing.
  - `test_temp_pairs_not_owned` (Review Focus 4). For every rendered PV and PVC:
    - the sync-options annotation is `Prune=false,Delete=false`;
    - every PV is `Retain`;
    - there is no `argocd.argoproj.io/tracking-id` annotation and no `app.kubernetes.io/instance` label;
    - the migration label is set.

    `render --out <repo>/infrastructure/x` exits 1.
  - `test_precheck_refuses_active_build` (Review Focus 5). Each of these gives `rebuild`:
    - packer `build.yml` `in_progress`;
    - terraform `apply.yml` `queued`;
    - ansible `deploy.yml` `in_progress`;
    - a terraform PR with `autoMergeRequest` set.

    Each of these gives `lock`:
    - `operation.json` missing;
    - an `operation` of `ansible-deploy`;
    - an `operation` of `storage-cutover:loki` for id `tempo`.

    `storage-cutover:karakeep-data:karakeep-meilisearch` passes for either id.
  - `test_drift_pr_alone_does_not_block`: an open terraform drift PR with no auto-merge gives no `rebuild` reason.
  - `test_refuses_target_smaller`: forward with size `4Gi` against binding capacity `5Gi` gives `size`. Reverse with
    inventory `6Gi` against binding `5Gi` also gives `size`.
  - `test_refuses_copied_entry`: forward on an entry that already has `copied` gives `no-entry`.
  - `test_render_forward_shape`:
    - src has driver `csi.proxmox.sinextra.dev`, the binding handle, `volumeMode: Block` and the binding
      `nodeAffinity`;
    - dst has driver node-manual, handle `tempo`, and an iqn ending `:tempo`;
    - the Job has `backoffLimit: 0`, both `volumeDevices`, and the pinned image digest.
  - `test_render_reverse_swaps`: with a passing `gate.log` and a `render.json` from pass 1 in `--out`, src and dst
    are exchanged, and the Job's first argument is `reverse`.
  - `test_reverse_requires_clean_source` (4.T R2 step 4):
    - pass 1 (no `gate.log`) writes `gate.yaml` and `render.json` but no `pairs.yaml` or `job.yaml`, and prints
      `gate-required`;
    - `gate.yaml` holds PVs `migrate-gate-tempo` (Block) and `migrate-guard-tempo` (Filesystem, `mountOptions`
      `[ro, noload]`, volume `readOnly: true`), both with handle `tempo`; Job `migrate-gate-tempo`'s first argument is
      `gate`; Job `migrate-guard-tempo` runs the fixture writer's guard init container on `migrate-guard-tempo`;
    - pass 2 refuses `gate` and writes nothing when `gate.log` lacks `gate-fsck-ok tempo` or `gate-guard-ok tempo`,
      holds the lines for another id, or a `migrate-gate-tempo` PV is still live (`handle`);
    - a writer template with no init container on the claim, two templates on the claim, or a guard init container
      that also mounts another PVC makes pass 1 refuse `gate`; the guard Job carries the template's env and pod
      `securityContext`;
    - pass 1 with `operation.json` missing refuses `lock` and writes no `gate.yaml`.
  - `test_precheck_reverse_requires_lock`: reverse precheck with `operation.json` missing, or with `ansible-deploy`,
    gives `lock`; with `storage-cutover:tempo` it gives none.
  - `test_refuses_stale_clone`: `clone` with `head != origin_main`, or `dirty: true`, gives `stale-clone` from
    precheck, and render writes nothing; render writes `apps_head` into `render.json`.
  - `test_copy_script_steps`. The text of `copy_volume.sh` must contain, in this order:
    - `iflag=direct oflag=direct conv=fsync`;
    - `cmp -n`;
    - `e2fsck -fp`;
    - `tune2fs -O mmp -E mmp_update_interval=5 -e remount-ro`;
    - `dumpe2fs -h`;
    - `resize2fs`.

    It must not contain `sparse`. It contains `e2fsck -fn` only in the `gate` branch, which exits before step 1, and
    the reverse `T == S` refusal.
  - `test_copy_script_on_loop_devices`, skipped unless `os.geteuid() == 0` and `losetup` exists:
    - make a 64 MiB ext4 image with a marker file, and a 128 MiB blank image;
    - run the script with `MIGRATE_SRC` and `MIGRATE_DST` set to the two loop devices;
    - assert `copy-ok`, that the marker reads back after a read-only mount of the target, that `dumpe2fs -h` shows
      `mmp`, and that the target filesystem is 128 MiB;
    - `gate` on the target prints `gate-fsck-ok`; on a scratch copy whose root inode was cleared
      (`debugfs -w -R 'clri <2>'`), `gate` exits non-zero;
    - `reverse` from the 128 MiB target to the 64 MiB source refuses (`T < S`), and to a 192 MiB blank image refuses
      (`T != S`).
  - `test_verify_teardown_refuses_leftovers`. Each of these exits 1:
    - a labelled PVC is left;
    - a VA names `migrate-src-tempo`.

    Empty `live` exits 0.

  Run, in AP: `python3 -m unittest discover -s scripts/storage/tests -v`. Expected: FAIL (`migrate_volume` not found).
- [ ] **Step 3: Implement.**
  - `migrate_volume.py`, with `argparse` subcommands `precheck`, `render` and `verify-teardown`.
  - `decide(...)` returns the reasons above, in that order.
  - Collectors:
    - `kubectl ... -o json`;
    - `gh run list -R Starktastic-Homelab/<repo> --workflow <file> --json status --limit 20`;
    - `gh pr list -R Starktastic-Homelab/<repo> --state open --json number,title,autoMergeRequest`;
    - `json.load(open(<lock-root>/operation.json))`, keeping only `operation` and `owner`;
    - `git rev-parse HEAD`, `git rev-parse origin/main` and `git status --porcelain` in the clone (no fetch).
  - `verify-teardown` polls for up to 300 s, then exits 1 listing what is left.
  - It prints no Secret, token, nonce or kubeconfig content.
  - It needs `kubectl`, `gh` and the lock root on one tool host (D23). The runner user has no `kubectl`, and whether
    root on VM300 has `kubectl` and `gh` is UNVERIFIED; Task 4.0 Step 7 checks it and settles the host.
  - `copy_volume.sh` as above.
- [ ] **Step 4: Run** the tests, plus `shellcheck scripts/storage/copy_volume.sh` and kubeconform on a `render` output
  from a fixture. Expected: PASS. The loop-device test shows as skipped in CI.
- [ ] **Step 5: Run the loop-device test once as root on the workstation** (offline: loop devices only, no live
  system):
  - Run: `sudo -E python3 -m unittest scripts.storage.tests.test_migrate_volume -k loop_devices -v`.
  - Expected: `ok` and not `skipped`. Paste the output into `evidence/2.5/loop-test.txt`.
  - This is the only test of the `O_EXCL` hold, the `e2fsck` exit rule and the `dumpe2fs` matching before the first
    real copy, tempo, which is the first proof on real storage (ADR `:839-840`).
- [ ] **Step 6: Commit** `feat(storage): copy Job tool for retained volume cutovers`.
  This is apps code. It ships with the AP branch merge (Task 3.6) and has no live effect: nothing renders it into
  Argo. It is removed again in Task 5.9 (migration-only, see Produces).

### Task 2.6: apps: the binding switch and the renderer

Worktrees AP and A.

**Files:**
- Modify (AP): `scripts/check-retained-inventory.py`:
  - `:18` allows an optional `copied` field;
  - `:35-65` validates it;
  - a new `check_bindings(head, root)` is called from `main()` `:111`.
- Test (AP): `scripts/storage/tests/test_retained_inventory.py`.
- Modify (A): `roles/storage_vm/files/homelab_storage/inventory.py:12,53-56`, which accepts an optional `copied`.
- Test (A): `scripts/tests/test_storage_inventory.py`, run by `validate.yml`'s one discover step (Task 2.2).
- Audit fold-in (D49, genericity audit "apps `storage-vm`" finding 5), in the Step 4 AP commit:
  - Modify (AP): `scripts/storage/tests/test_retained_inventory.py:16`: drop the workstation helm fallback
    (`~/.cache/claude-household-boundary/bin/helm`): `HELM = shutil.which('helm')`, and the render tests fail with
    `helm not on PATH` when it is missing. From here on every workstation Run line for `scripts/storage/tests` is
    prefixed `PATH=~/.cache/claude-household-boundary/bin:$PATH` (the wrapper part 0 uses); CI has helm.
  - Modify (AP): rename `test_regex_matches_ansible` (`:58`) to `test_id_pattern_tripwire`. It compares the regex with
    a copy of itself and never reads ansible: its comment and `scripts/check-retained-inventory.py:15` say it pins the
    literal so a change is deliberate, and that ansible `roles/storage_vm/files/homelab_storage/inventory.py:7` must
    change with it. The contract-index row ("Retained volume id pattern") goes in with Task 5.6.
- Steps 1-4 make no change to `infrastructure/base-configs/templates/retained-volumes.yaml`. It never reads `copied`,
  and a test pins that it does not.
- Steps 5-8 (growth and VG size):
  - Modify (AP): `infrastructure/base-configs/templates/retained-volumes.yaml:42-44`, the PVC request becomes the
    constant `1Mi`; the PV capacity (`:10-11`) keeps following `size`.
  - Create (AP): `scripts/storage/vg-sizes.json`, the two data disk sizes mirrored from terraform.
  - Modify (AP): `scripts/check-retained-inventory.py` (`check()` gains the per-VG size sum; `main()` loads the file).
  - Test (AP): `scripts/storage/tests/test_retained_inventory.py` (`RenderTests`, `CheckTests`).

**Interfaces:**
- Consumes: the inventory (with `copied`), and every `values.yaml` under `services/` and `infrastructure/`, with the
  base layering of `bootstrap/appsets/cluster-apps.yaml:138-158`:
  - `templates/common.yaml` for services;
  - then `commonValuesExtras`;
  - then `<baseApp or own>/values.yaml`;
  - then the app's own values when `valuesOverride: true`.
- Produces:
  - inventory field `copied`: an ISO date string `YYYY-MM-DD`. It is allowed only on `origin: migrated`, and is set by
    the switch PR (4.T step 6);
  - **claim naming:** the new claim is `<id>-iscsi` (`existingClaim` and `claimName` styles). For the operator STS
    style, the new `volumeClaimTemplate` name is `<id>-iscsi` and the inventory claim is
    `<id>-iscsi-<statefulset>-0`: `prometheus-iscsi-prometheus-kube-prometheus-stack-prometheus-0` and
    `alertmanager-iscsi-alertmanager-kube-prometheus-stack-alertmanager-0`;
  - **what "switched" means:** an app's effective values reference an inventory claim as `existingClaim` or
    `claimName`, or carry a `volumeClaimTemplate` with `spec.volumeName: <id>`;
  - (Steps 5-8) every rendered retained PVC requests `1Mi`, whatever its `size`; a growth PR changes only the PV;
  - (Steps 5-8) `scripts/storage/vg-sizes.json`: `{"retained_gib": <D2:retained_gib>, "regen_gib": <D2:regen_gib>}`,
    the `size` values of `virtio1` and `virtio2` in terraform `storage/terraform.tfvars` `data_disks` (Task 2.1b);
  - (Steps 5-8) CI rule: per VG (`class: retained` to VG `retained`, `regenerable` to `regen`), the summed `size` of
    the head inventory must leave at least the VG's snapshot reserve free in that VG's usable bytes,
    `<gib> * 1 GiB - 4 MiB`. Reserve = the largest head entry's `size` in that VG, but at least 10% of the VG's
    usable bytes (Ben, 2026-11-22).

Per-style switch (the edit the switch PR makes; the guard follows by volume name):
- **`existingClaim` (app-template)**, for example `services/operations/tempo/values.yaml:115-117`
  `persistence.data.existingClaim: tempo-data-block`:
  - set the new claim;
  - the guard init container already mounts this persistence key (`advancedMounts.main.retained-state`, `:118-121`),
    so it now reads the new claim;
  - same for autobrr (`services/media/autobrr/values.yaml:97-106` after 1.3a) and karakeep (`values.yaml:185-202`,
    two keys, one switch PR each, D14).
- **`claimName` (loki)**, `services/operations/loki/values.yaml:82-85` `singleBinary.extraVolumes[retained-data]`:
  - set the new claim;
  - the `retained-state` init container (`:48`) mounts `retained-data` (`:76`), so it follows.
- **STS `volumeClaimTemplate` (kube-prometheus-stack)**: prometheus `values.yaml:88-101`, alertmanager `:167-180`. In
  one PR, for each:
  - `volumeClaimTemplate.metadata.name` changes from `prometheus-data-block` to `prometheus-iscsi`;
  - `spec.volumeName` becomes `prometheus`, the inventory id;
  - `spec.storageClassName` becomes `""`;
  - the guard init container's `volumeMounts[].name` (`:77`, alertmanager `:156`) changes to the new template name.

  A claim rename alone fails, because the derived claim name must change and the guard mount is keyed on the template
  name.
- **-ru variants are already scoped.** `sonarr-ru` (`values.yaml:19-20`), `radarr-ru` (`:20`) and `qbittorrent-ru`
  (`:21`) set their own `existingClaim` over the base layering. So switching a base app does not move its variant. A
  check pins that this stays true.
- **Bitnami `primary`/`master.persistence.existingClaim` (wave 6)** has no resolver yet. The check fails closed on any
  values file that names an inventory claim in a style it cannot resolve. Wave 6 adds its resolver first (Task 4.W).

**Settled open fact m8 (operator recreating the STS).** Sources: prometheus-operator `v0.95.2`, the appVersion of
chart `kube-prometheus-stack` 93.2.2 (`services/operations/kube-prometheus-stack/app.yaml`), read through a summariser
on 2026-11-21.
- **SETTLED for Alertmanager.** `pkg/alertmanager/operator.go` `sync()`:
  - skips a CR with `spec.paused: true` ("no action taken");
  - otherwise calls `k8s.ForceUpdateStatefulSet`.

  `pkg/k8s/statefulset.go` `ForceUpdateStatefulSet`:
  - on an HTTP 422 `Invalid` update (an immutable field such as `volumeClaimTemplates`), it logs "recreating
    StatefulSet because the update operation wasn't possible";
  - it deletes the STS with **foreground** propagation, so the pods are deleted too;
  - it does not wait, and the next reconcile recreates the STS.
- **Prometheus: the paused skip is SETTLED** (`pkg/prometheus/server/operator.go` `sync()`). That it calls the same
  `ForceUpdateStatefulSet` is UNVERIFIED in source (the page was truncated). Red Hat bugs 2042441 and OCPBUGS-17346
  show the same log line and foreground delete for the Prometheus STS.
- **Consequence for 4.T.** Under the hold the CR has `replicas: 0`, so the foreground delete removes no running pod. The
  old PVC survives, because `persistentVolumeClaimRetentionPolicy.whenDeleted: Retain` is set at `values.yaml:35-37`
  (prometheus) and `:115-117` (alertmanager). The recreated STS adopts the pre-rendered PVC by its derived name.
- **Evidence and fallback.** The first wave-1 STS cutover records the operator log line in `evidence/4.T-<id>/`. If no
  recreate happens within 10 minutes of the sync, the window is gone and Argo has synced the CR back to 1, so follow
  4.W's operator-style fallback: read the StatefulSet's `.spec.replicas` and the pods on `<old_claim>`. Only if it is
  at 0 and no pod mounts `<old_claim>`, run `kubectl -n monitoring delete sts <name> --cascade=orphan` (**Ben OK**).
  Otherwise re-hold first (re-add the owned window, patch the CR to `replicas: 0`, confirm no pod on either claim),
  then the orphan delete, then lift the window again (**Ben OK** at each). Never orphan-delete while a pod runs.

**Ordering (cross-repo).** Both checks reject unknown keys today: apps `check-retained-inventory.py:41` and ansible
`inventory.py:53-54` (`set(e) != FIELDS`). An apps `main` holding `copied` before the storage VM's ansible accepts it
would fail every `storage.yml` run at validation (live targets stay, `StorageReconcileFailing` fires). So:
1. the A commit below rides the ansible storage PR (Task 3.2);
2. Task 3.5's `storage.yml` run proves it is deployed;
3. only then can an apps PR set `copied`. The first one is the first switch PR in 4.T.

- [ ] **Step 1: Write the failing tests.**
  - AP `test_retained_inventory.py`, `CheckTests`:
    - `test_copied_optional_iso_date`. `entry(origin='migrated', copied='2026-12-01')` passes. These fail:
      `'2026-13-01'`, `'01-12-2026'`, `''` and `20261201` (an int).
    - `test_copied_forbidden_on_new`: `entry(origin='new', copied='2026-12-01')` gives an error.
    - `test_copied_may_be_removed`: base has `copied`, head lacks it, and there is no error. A revert of a switch PR
      has to pass CI.
  - AP `BindingTests`. Each builds a temporary tree with an `app.yaml`, a `values.yaml` and a static binding file, and
    calls `chk.check_bindings(entries, root)`.
    - `test_flag_without_copied_marker_fails` (Review Focus 3). Values with `persistence.data.existingClaim:
      tempo-iscsi`, against `entry('tempo', claim='tempo-iscsi', origin='migrated')` with no `copied`, give an error
      naming tempo and `copied`. The same tree with `copied` set gives no error.
    - `test_switch_requires_guard_mounted` (Review Focus 3):
      - app-template: if no init container is listed under the key's `advancedMounts.<ctrl>`, that is an error;
      - loki: if no `singleBinary.initContainers[].volumeMounts[].name` equals the `extraVolumes` name, that is an
        error;
      - kps: if no init container mounts the new template name, that is an error;
      - each style's correct tree passes.
    - `test_claim_reuses_static_pvc_fails`: an entry with `claim: tempo-data-block`, `namespace: monitoring`, next to
      the static PVC of that name in `monitoring-block-storage/tempo-bindings.yaml`, gives an error.
    - `test_sts_claim_must_match_template`: kps values with template `prometheus-iscsi` and `volumeName: prometheus`,
      against an entry claim other than `prometheus-iscsi-prometheus-kube-prometheus-stack-prometheus-0`, give an
      error.
    - `test_variant_inherits_base_claim_fails`: a variant with `baseApp` and `valuesOverride: true` that does not
      override the base's switched `existingClaim` gives an error (two apps on one RWOP claim).
    - `test_unknown_binding_style_fails`: a values file naming an inventory claim under `primary.persistence` gives
      an error saying that no resolver exists.
    - `test_repo_bindings_pass`: `check_bindings` on the real tree with the real inventory returns `[]`.
  - AP `RenderTests.test_copied_does_not_change_render`: the PV and PVC render identically with and without `copied`.
  - A `test_storage_inventory.py`:
    - `test_accepts_copied`: `load()` of an entry with `copied: "2026-12-01"` returns the same `Volume`;
    - `test_rejects_bad_copied`: a bad date, `copied` on `origin: new`, and a non-string `copied` all raise
      `InventoryError`;
    - `test_rejects_unknown_key` still raises for `foo`.

  Run, in AP: `PATH=~/.cache/claude-household-boundary/bin:$PATH python3 -m unittest discover -s scripts/storage/tests
  -v`. Then in A:
  `python3 scripts/tests/test_storage_inventory.py`.

  Expected: FAIL (`copied` is rejected as an unknown field, and `check_bindings` does not exist).
- [ ] **Step 2: Implement.**
  - Both repos: `FIELDS` stays the required set, `OPTIONAL = {'copied'}`, and the shape check is
    `FIELDS <= set(e) <= FIELDS | OPTIONAL`. `copied` must `fullmatch(r'\d{4}-\d{2}-\d{2}')` and parse with
    `datetime.date.fromisoformat`. It is refused on `origin: new`. A keeps the error message style of
    `inventory.py:54`.
  - AP `check_bindings(entries, root) -> [errors]`:
    1. Collect the static PVC names `(namespace, name)` from every YAML doc with `kind: PersistentVolumeClaim` under
       `infrastructure/` and `services/`, skipping files that contain `{{`. Refuse an entry claim that equals one.
    2. For each `app.yaml` under `services/` and `infrastructure/`, build the effective values in the appset order
       above (a deep dict merge; lists are replaced, as Helm does).
    3. Resolve the bindings with three resolvers: app-template `persistence.*`, loki `singleBinary.extraVolumes`, and
       the kps `prometheusSpec.storageSpec` and `alertmanagerSpec.storage`. A table maps the two kps paths to their
       STS names, with the comment `shortcut: STS names are chart-derived; re-check on a kube-prometheus-stack
       major`.
    4. For every binding to an inventory claim (or `volumeName: <id>`):
       - the entry needs `copied` if it is migrated;
       - an init container must mount the volume;
       - for kps, the claim must equal `<template>-<sts>-0`.
    5. Any other values occurrence of an inventory claim string is "unresolved style".
    6. A variant whose effective binding equals its base app's switched claim is an error.
  - Wire it: `main()` adds `check_bindings(head, Path('.'))` errors to the existing ones. The CI step at
    `validate-and-diff.yml:104-107` needs no change.
- [ ] **Step 3: Run** the Step 1 commands. Expected: PASS. `test_repo_bindings_pass` passes because the inventory is
  `[]`.
- [ ] **Step 4: Commit** each repo separately.
  - AP: `feat(storage): copied marker and binding-switch checks for migrated volumes`.
  - A: `feat(storage): accept the copied marker in the volume inventory`.

  Merge events:
  - A rides Task 3.2, a deploy with k3s restarting on every node;
  - AP rides Task 3.6, where ArgoCD syncs and nothing renders, because the inventory is empty.

**Growth on the Kubernetes side (audit: growth bug, verified).** Today `retained-volumes.yaml:44` renders the PVC
request from `size`, like the PV capacity at `:11`. Read on 2026-11-22 from kubernetes `master` (stable for years;
re-read at the k3s version from Task 1.1 if in doubt):
- **Increase is rejected.** `plugin/pkg/admission/storage/persistentvolume/resize/admission.go` (the
  `PersistentVolumeClaimResize` admission plugin, on by default, and k3s keeps the defaults) checks only a larger
  request. `allowResize` returns false when the class name is `""`, so the update fails with Forbidden "only dynamically
  provisioned pvc can be resized and the storageclass that provisions the pvc must support resize". base-configs would
  fail its sync on every growth PR and stay failed, while `storage.yml` still grows the LV and the filesystem.
- **Decrease is rejected at or below the bound capacity.** `pkg/apis/core/validation/validation.go`
  `ValidatePersistentVolumeClaimUpdate` allows a smaller request only while it stays above `status.capacity`
  ("field can not be less than status.capacity"). Any other spec change is "spec is immutable after creation except
  resources.requests and volumeAttributesClassName for bound claims"; an unbound claim may not change its request at
  all.
- **Binding needs PV capacity >= request.** `pkg/controller/volume/persistentvolume/pv_controller.go`
  `checkVolumeSatisfyClaim` refuses "requested PV is too small" otherwise.
- **`status.capacity` is set once.** The same file (`:797-800`) sets it only when the claim becomes Bound, so
  `kubectl get pvc` shows the bind-time PV capacity forever. Apps and `df` see the filesystem, and kubelet volume stats
  read the filesystem too; no ResourceQuota or LimitRange exists in apps (grep), and no rule or dashboard reads
  `kube_persistentvolumeclaim_resource_requests_storage_bytes`.
- PV `spec.capacity` is mutable (`ValidatePersistentVolumeUpdate` pins only the volume source, `volumeMode` and node
  affinity), so a growth PR may raise it.

Decision: render the PVC request as the constant `1Mi` for every entry, and keep the PV capacity on `size`. It binds
(the smallest legal `size` is `4Mi`), it never changes after the first render, and it needs no inventory field. A
stored `request` field would add a key to both validators (apps `check-retained-inventory.py`, ansible
`inventory.py`), with the same cross-repo ordering as `copied`, plus a CI immutability rule; the constant needs
neither. The constant is pinned by a test, and changing it is never safe: raising it is rejected by admission, and
lowering it below a bound claim's `status.capacity` is rejected by validation.

Ordering: the constant must be on `main` before the first inventory entry renders. A PVC already created with
request = `size` cannot move to `1Mi`, since `1Mi` is below its `status.capacity`. Steps 5-8 commit on AP before the
Task 3.6 merge, and the first entry (`f1-canary`, D18) comes after it, so no PVC exists with the old request. If one
does (a lab cluster), it keeps its request until it is deleted and re-rendered (Ben OK, retained data untouched: only
the PVC object).

> **Superseded 2026-11-25 (Ben):** apps CI now reads the sizes from terraform `main` `storage/terraform.tfvars`
> (`check-retained-inventory.py --storage-tfvars`, default the raw URL); `vg-sizes.json` is deleted and growth needs
> only the terraform PR. The inventory `claim` must also be `<id>-iscsi` (or `<id>-iscsi-<sts>-0` for a
> kube-prometheus-stack StatefulSet), and the id-change detector is gone. Text below is the original build record.

**VG size in apps CI (audit: size check).** The data disk sizes live in terraform `storage/terraform.tfvars`
`data_disks[*].size` (GiB, Task 2.1b). apps CI cannot read terraform, so a small committed file mirrors them:
`scripts/storage/vg-sizes.json`. It is kept by hand: the growth runbook's "Grow a data disk" (Task 2.7 Step 3) updates
it in an apps PR after the terraform PR is applied, and the bootstrap runbook (Task 2.7 Step 9) checks it against the
live `vgs`. A stale value is safe in both directions: too small fails closed (CI refuses a PR until the file is
updated), too large is caught by the reconcile's free-space refusal (Task 2.10), which writes no tag. Usable bytes are
`<gib> GiB - 4 MiB`: the PV data area starts at 1 MiB and the 4 MiB extents round the rest down. That pe_start is the
lvm2 default and is UNVERIFIED for the production `vgcreate`; Task 2.7 Step 9's check catches a difference. The sum
sees only entries in the head inventory; an entry removed earlier keeps its LV until expiry, and only the reconcile
check sees that space.

**Snapshot reserve (Ben, 2026-11-22).** The check also keeps free, per VG, the largest entry's `size` in that VG, but
at least 10% of the VG's usable bytes. Why: one LVM snapshot of the largest volume must always fit, so the deferred
storage-VM backup path (requirement 2, backup half: LVM snapshot per retained LV, then restic) stays possible. It is a
CI rule only: the reconcile's no-space precheck (Task 2.10) is unchanged and still guards a single create or extend
against actual free space. The reserve uses the same head inventory and the same `vg-sizes.json` as the sum.

- [ ] **Step 5: Write the failing tests** (AP `test_retained_inventory.py`):
  - `RenderTests.test_growth_changes_pv_not_pvc`: render `entry('app-data', size='5Gi')` and `size='6Gi'`. The PV
    `spec.capacity.storage` is `5Gi` and then `6Gi`; the two PVC documents are equal.
  - `RenderTests.test_pvc_request_immutable_across_size_change`: for sizes `4Mi`, `5Gi` and `64Gi`, the PVC
    `spec.resources.requests.storage` is exactly `'1Mi'` (the literal is pinned here; a change to it fails this test,
    which is how CI refuses a change of the request), and the PV capacity is >= the request.
  - `CheckTests.test_sizes_over_vg_refused`, with `vg_bytes={'retained': 10 * GI - 4 * MI, 'regen': 2 * GI - 4 * MI}`
    passed to `chk.check`:
    - two `retained` entries of `5Gi` give an error naming VG `retained`, the sum and the usable bytes;
    - one `retained` entry of `10Gi - 4Mi` (`10236Mi`) is refused: it fits, but leaves no reserve;
    - a `regenerable` `3Gi` entry gives an error naming `regen`, while `retained` `2Gi` + `3Gi` stays within its own
      budget;
    - a growth PR that pushes a class over its VG or into its reserve gives the error; `3Gi` -> `3584Mi` alongside
      `2Gi` passes (free `4604Mi` >= `3584Mi`).
  - `CheckTests.test_inventory_refused_when_reserve_not_free`, same `vg_bytes` (`retained` usable `10236Mi`, so the
    10% floor is `10236Mi // 10` in bytes, about `1023.6Mi`):
    - `retained` entries `4Gi` and `3Gi` (free `3068Mi`, below the largest entry `4Gi`) give an error naming VG
      `retained`, the free bytes and the reserve;
    - with a `retained` VG of `10232Mi`, one entry of `5120Mi` (free `5112Mi`, below its own `5120Mi`) is refused
      (sizes are 4 MiB multiples, so `5119Mi` would be refused by the size pattern first);
    - 19 `retained` entries of `500Mi` (free `736Mi`, largest `500Mi`) are refused by the 10% floor.
  - `CheckTests.test_inventory_accepted_with_reserve_free`, same `vg_bytes`:
    - `retained` entries `2Gi` and `3Gi` (free `5116Mi`, reserve `3Gi`) pass;
    - with a `retained` VG of `10232Mi`, one entry of `5116Mi` (free equals the reserve) passes;
    - 18 `retained` entries of `500Mi` (free `1236Mi`, above the 10% floor) pass;
    - the reserve is per VG: `retained` `2Gi` + `3Gi` plus one `regenerable` `512Mi` entry (regen free `1532Mi` >=
      reserve `512Mi`) pass; the `512Mi` counts toward neither `retained`'s sum nor its largest entry.
  - `CheckTests.test_vg_sizes_file`: `scripts/storage/vg-sizes.json` has exactly `retained_gib` and `regen_gib`,
    positive ints; `main(['--vg-sizes', <missing>, ...])` exits 1 (fail closed).

  Run, in AP: `PATH=~/.cache/claude-household-boundary/bin:$PATH python3 -m unittest discover -s scripts/storage/tests
  -v`. Expected: FAIL (the PVC request follows
  `size`, `check()` takes no `vg_bytes` and keeps no reserve, the file is missing).
- [ ] **Step 6: Implement.**
  - `retained-volumes.yaml:44`: `storage: 1Mi`, with the comment `# Constant: a bound static PVC's request can never
    grow (class "") nor drop below status.capacity. Growth changes the PV only (ADR 0017).`
  - `scripts/storage/vg-sizes.json`: the two keys above, from Task 2.1b's `<D2:retained_gib>` and `<D2:regen_gib>`.
  - `check-retained-inventory.py`: `VG_FOR = {'retained': 'retained', 'regenerable': 'regen'}`;
    `check(base, head, override=False, vg_bytes=None)` adds, when `vg_bytes` is given, one error per VG whose head sum
    exceeds it, else one error per VG where `usable - sum < max(largest, usable // RESERVE_MIN_DIVISOR)`, with
    `RESERVE_MIN_DIVISOR = 10` and the comment `# Keep one LVM snapshot of the largest LV possible (deferred storage-VM
    backup path, Ben 2026-11-22).`; `main()` gains `--vg-sizes` (default `scripts/storage/vg-sizes.json`, as
    `--inventory`), loads it, passes `{vg: gib * GI - 4 * MI}`; a missing or malformed file is an error, never a skip.
- [ ] **Step 7: Run** the Step 5 command, plus `scripts/check-retained-inventory.py --base origin/main
  --override-label <label>` on the real tree. Expected: PASS, including `test_inventory_refused_when_reserve_not_free`
  and `test_inventory_accepted_with_reserve_free` (the real inventory is `[]`, so no VG has a sum or a largest entry
  and the 10% floor is free).
- [ ] **Step 8: Commit** `fix(storage): constant PVC request so growth changes only the PV; per-VG size check with
  snapshot reserve`. Merge
  event: AP rides Task 3.6, as Step 4. No ansible change: the inventory schema is unchanged.

### Task 2.7: apps: runbooks

Worktree D (`~/.cache/claude-homelab-live/worktrees/apps-adr-0017`). The runbooks are docs-only apps commits, and
apps needs no `[skip ci]`. AP's `docs/runbooks/` is stale against `main` (scout-precedent), so write the runbooks on D
or on the rebased AP, never on pre-rebase AP.

**Files:** Create `docs/runbooks/<name>.md` for the 11 names pinned in the outline, plus one row each in the runbook
index, if `docs/runbooks/` has one at that time (UNVERIFIED; none was seen at AP HEAD).

**Interfaces:**
- Consumes:
  - the ADR (`docs/adr/0017-retained-block-storage-vm-iscsi.md`; line numbers below are at D);
  - the lab report `docs/superpowers/reports/2026-11-16-retained-storage-lab-results.md` (D);
  - the lab evidence under `~/.cache/claude-homelab-live/storage-lab/`;
  - ansible role files at A `a036b47`.
- Produces: the section names that the alerts (2.4) and Tasks 3.5, 3.7, 3.8 and 4.T point at.

Every runbook uses the same frame:
- a "Before you start" list (lock, backup windows, the deny syncWindow if writers are touched, Ben's OK lines);
- numbered steps, each with where it runs (runner, pve, storage VM) and an Expected line;
- "Undo";
- "Evidence" (`~/.cache/claude-homelab-live/storage-migration/evidence/<task>/`).

Every command is copied from the cited evidence and changed only for production names. Any command with no lab source
is marked `(not rehearsed)`.

- [ ] **Step 1: Write `storage-vm-restore.md`.**
  - Sections:
    - "Whole-disk restore", steps 1-6. This is the ADR section of that name as corrected by Task 0.4 row 11 (step 6
      clears only `hold_create` and restores `hold_fence` as recorded), with F17 in step 5 and F16's log line from Task
      0.2. Say that `hold_create` also holds back grows, so `0 creates refused` can mean a held grow.
    - "Single app from a ZFS clone" (ADR `:693-701`).
    - "Off-site restic restore" (ADR `:703-704`).
    - "Boot check failed" (2.4 alert: read `journalctl -u rtslib-fb-targetctl`, then this runbook or the
      crashed-create one). D7: `StorageBootCheckFailed` needs Prometheus and Alertmanager, which live on `regen` after
      wave 1; a storage VM that is down takes them with it, and then only the healthchecks.io Watchdog dead-man
      alerts (about 10 min, ADR `:807-810`).
  - Sources:
    - report `:781-813` (B9 Steps 1-2) and `storage-lab/b9/notes.md`;
    - `storage-lab/b11/restic-9970.txt` (restic leg);
    - ansible `docs/backup-and-restore.md` "One image from the replica" at origin/main `:203-213`. The ADR cites
      `:168-189` (stale, scout-adrvalues), and Task 0.4 fixes that.
  - Name clash: the ADR `:664` names this file `retained-storage-restore.md`, but the outline pins
    `storage-vm-restore.md`. Task 0.4 aligns the ADR.
- [ ] **Step 2: Write `storage-vm-fencing.md`.**
  - Sections:
    - "Reading the fencer" (alerts `StorageWorkerFenced`, `StorageFenceFailed`, `StorageFenceDraining`,
      `StorageFencerBlind`, `NodeOutOfServiceTaintStuck`).
    - "Manual fence" (ADR `:581-597`).
    - "Migration-only qm stop before the taint" (ADR `:597-604`, Ben 2026-11-21).
    - "Manual unfence" (`--confirm-stopped`, F8). After a k3s rebuild the fencer token is stale until the next
      `storage.yml` run (D28), so a manual `unfence` fails: dispatch `storage.yml` first (**Ben OK**), then unfence.
    - "Unfence after a host cold boot" (F18 path, one more reboot).
    - "Before renumbering a worker bridge address" (the F7 accepted edge).
  - Sources:
    - report `:399-572` (B6, F7/F8 fixes);
    - `storage-lab/b6/runbook.md`, `b6/notes.md`, `b6-s7-reconcile.txt`, `b6-s7a-undo.txt`;
    - `storage-lab/f7f8-install.txt`, `f7f8-render.txt`, `f7f8-undo.txt`;
    - `storage-lab/b10/notes.md:32-38` (F18 and the unfence by reboot).
- [ ] **Step 3: Write `storage-vm-growth.md`.**
  - Sections:
    - "Grow a volume" (an inventory size PR; reconcile `lvextend`, `iscsiadm -R`, online `resize2fs`; ADR reconcile
      table, `grow-volume.yml`). Only the PV capacity changes; the PVC request stays `1Mi` (Task 2.6 Steps 5-8), and
      `kubectl get pvc` keeps showing the bind-time capacity, so check the size with the PV or `df` in the pod. CI
      refuses a PR that takes the class over its VG (`scripts/storage/vg-sizes.json`); the reconcile refuses
      `no-space` when VG free is short, and the dry run fails on it before the lock (Task 2.10, D40).
    - "Grow a data disk" (ADR `:731-736`: `qm resize`, `pvresize`, terraform PR; the F10 note that any `data_disks`
      change sends the changed disks' options (bpg >=0.120.0 #3251) and still deletes undeclared drives, so keep
      `virtio0` declared). Last step: an apps PR that sets the new GiB in
      `scripts/storage/vg-sizes.json`; until it merges, CI keeps the old budget (fails closed).
    - "Dataset full" (`StorageDatasetLow`, the capacity gate D20, the snapshot expiry delay ADR `:728-729`). Add: a
      firing on the staleness leg (timestamp older than 3 h) means the `Write host gauges` step of the ansible
      `storage.yml` workflow is failing or not running (it is `continue-on-error`, so the run still looks green).
      Read that step's log before trusting capacity rule item 4 (Task 4.0).
  - Sources:
    - report `:351-359` (Check 7) and `:603-640` (F10);
    - `storage-lab/b5-grow2.txt`, `b5-grow3-crash.txt`, `b5-grow3-retry.txt`, `b5/pause-grow.json`;
    - `storage-lab/b7/f10-cfg0.txt`..`f10-cfg3.txt`;
    - A `roles/storage_vm/tasks/grow-volume.yml`.
- [ ] **Step 4: Write `storage-vm-crashed-create.md`.**
  - Sections:
    - "crashed-create" (inspect, then adopt by tag or remove, with Ben OK).
    - "orphan" (inspect, then adopt as a manual tag operation, ADR reconcile table).
    - "lost (ledgered, LV missing)".
    - "lv-missing after a failed expiry: the lvremove/tombstone gap" (D12, ADR `:823-824`; the manual tombstone).
  - Sources:
    - report `:322-350` (Check 5);
    - `storage-lab/b5-crash.txt`, `b5-crash-retry.txt`, `b5-orphan.txt`, `b5-lost-orphan.txt`, `b5-tombstone.txt`,
      `b5/pause-create.json`, `b5/notes.md`. (`b5-hexbranch.txt` is the old-SHA and 40-hex check, not this.)
- [ ] **Step 5: Write `storage-vm-expiry.md`.**
  - Sections:
    - "How expiry decides" (ADR deletion rules, after the reconcile table).
    - "Half-expiry recovery through storage.yml" (F3/F4, LA:97: the target is gone, and a retry is refused as busy
      until the reconcile re-exports).
    - "Expiry refused: VA, session or copy pair".
    - "First production expiry check" (Task 3.8 canary).
  - Sources:
    - report `:322-350`;
    - `storage-lab/b5-expiry1.txt`, `b5-expiry2.txt`, `b5-expiry3.txt`, `b5-expiry-nolock.txt`, `b5-hold.txt`,
      `b5/va.yaml`, `b5/copy.yaml`;
    - A `roles/storage_vm/tasks/expire-volume.yml`, `storage-expiry.yml`.
- [ ] **Step 6: Write `storage-vm-readonly-fs.md`.**
  - Sections:
    - "Symptoms".
    - "Restage" (scale to 0, confirm the unstage, scale up; a same-node delete does not restage, F13, ADR
      `:921-925`).
    - "Offline e2fsck of an error-flagged filesystem" (D11: at the next drained window, after a copy of the LV; Ben OK).
  - Sources:
    - report `:641-683` (B8 Check 8, F13 at `:676`);
    - `storage-lab/b8/notes.md` (legs N-stall, N-withdraw, H-stall, H-withdraw);
    - `storage-lab/b10/notes.md:160-165` and `b10/f14/fsck.log`, `fsck-n.txt`, `repair.log`, `repair-verify.txt`,
      `repair-lab-sqlite.txt`, `repair-lab-regen.txt`. This is an `e2fsck -fn` and then `-fy` on lab filesystems whose
      error flag dated from 11-17, run for F21. It is not the F9 rebuild rehearsal: the lab notes list the F9 `e2fsck`
      rehearsal as not run (`b10/notes.md:98`). So the D11 procedure is rehearsed only in that F21 form.
- [ ] **Step 7: Write `storage-vm-rebuild.md`.**
  - Sections:
    - "Why drain first" (F9, ADR `:167-171`).
    - "Writer drain".
    - "Rebuild PR pair" (`prevent_destroy=false` plus a generation bump, then restore it; Task 3.7).
    - "After the rebuild" (`storage.yml`, startup and onboot, check UUIDs, tags and IQNs).
    - "VM down" (the `StorageVMDown` line, D9: no auto-retry. D7/D9: the alert works only before wave 1; after it,
      Prometheus and Alertmanager are on `regen` and go down with the VM, so only the healthchecks.io Watchdog
      dead-man sees it, ADR `:807-810`).
  - Sources:
    - report `:573-640` (B7 Check 3, F9, F10);
    - `storage-lab/b7/notes.md:13-33`, `b7/base-971.txt`, `b7/after2-971.txt`, `b7/after3-971.txt`,
      `b7/qm971-before.txt`, `b7/qm971-after.txt`, `storage-lab/b7c3-storage.txt`;
    - `storage-lab/tf-storage/` (the lab root).
- [ ] **Step 8: Write `storage-vm-upgrade-held.md`.** There is **no lab evidence**: no upgrade was rehearsed.
  - Sections:
    - "What is held and why" (ADR `:142-145`: a targetctl restart drops every session; the lvm2 `vgcfgbackup` and
      `lvm.conf` risk, F24).
    - "Upgrade window" (drain as in the rebuild runbook, `apt-mark unhold`, upgrade, re-hold, reboot, the assert
      play).
  - Sources: ADR `:140-145`; A `roles/storage_vm/tasks/main.yml:19-24` (hold) and `roles/storage_vm/tasks/assert.yml:75`
    (the hold check); `storage-lab/b8/f24-notes.md` (why lvm2 is held). Mark every command `(not rehearsed)`.
- [ ] **Step 9: Write `storage-vm-bootstrap.md`** (used in Task 3.5).
  - Sections:
    - "Check the disks are the D1/D2 disks and blank".
    - "pvcreate and vgcreate `retained` and `regen`".
    - "Tag `retained` `hold_fence`".
    - "Check the VG budget" (read-only): `vgs --units b --nosuffix -o vg_name,vg_size retained regen`. Expected: each
      `vg_size` equals `<gib> * 1073741824 - 4194304` for its key in apps `scripts/storage/vg-sizes.json` (Task 2.6).
      If a `vg_size` is smaller, stop: the CI rule's 4 MiB is wrong for this `vgcreate`, so fix the rule in Task 2.6's
      code first. Larger only makes CI conservative; note it in the evidence.
    - "First storage.yml".
  - Sources: report `:185-187` (B3 Step 3: `pvcreate`, `vgcreate retained /dev/vdb`, `vgcreate regen /dev/vdc`,
    `vgchange --addtag hold_fence retained`); ADR `:360` ("one-time manual bootstrap") and `:955-957`. Use the
    production by-id names from Task 3.5 (`/dev/disk/by-id/virtio-retained`, `virtio-regen`; Task 2.1b's serials),
    never `/dev/vdX`.
- [ ] **Step 10: Write `storage-vm-cutover.md`**, the human-readable form of Task 4.T. There is **no lab evidence**
  for the copy: the lab never ran a copy Job (report `:337` only shows a Block pair).
  - Sections:
    - "Capacity gate".
    - "Inventory PR".
    - "Lock" (operation `storage-cutover:<id>[:<id2>]`).
    - "Hold".
    - "precheck, render, apply, Job".
    - "Verify and re-run precheck".
    - "Switch PR".
    - "Lift the hold and the 6-minute watch".
    - "Reconciliation PR".
    - "Teardown and verify-teardown".
    - "Rollback (revert, or reverse copy)".
    - "Stale lock" (`MaintenanceLockStale`; its `operation` label names the holder, read hourly by `Write host
      gauges`; confirm against the real `/var/lib/homelab-maintenance/operation.json` on VM300, read through the pve
      helper, before acting. A failed run keeps the lock (D31): read that run's log first, then release through the
      lock helper's own release path with the owner and nonce, with Ben's OK; ansible `docs/maintenance-execution.md`).
    - "NodeStage login retry" (D10, lab F1, ADR `:264-267`; accepted, not mitigated): a NodeStage against a target
      that does not answer retries `iscsiadm -l` 15 times, about 2 min each, so it holds the volume's lock for about
      30 min. Meanwhile NodeUnstage is refused, the VA can outlive its PV, and a target with that IQN created inside
      the window is logged into with no pod. Once the target answers, compare `[S] targetcli sessions` with the pods
      on that claim, and delete the pod so it gets a fresh NodeStage. `(not rehearsed)` for both.
  - Sources: ADR `:968-984`; Tasks 2.5 and 2.6; the precedent runbooks named in scout-precedent §3-§5.
- [ ] **Step 11: Write `pve-planned-reboot.md`** (Task 3.8; Ben may combine it with the memtest reboot).
  - Sections:
    - "Gate" (backup windows, `pve-backup` green, pstore empty, no CI runs).
    - "The runner goes down".
    - "Shutdown order".
    - "Boot and start order" (`up=180` on VM 100, storage VM `order=2,up=30`).
    - "After boot" (targets, the fencer, GPU admission race pods, worker NFS race).
    - "Runner credentials after a reboot" (F19).
  - Sources:
    - `~/Projects/homelab/pve-one-reboot-runbook-2026-11-15.md`, `pve-reboot-report-2026-11-16.md`,
      `pve-window-runbook-2026-11-15.md`;
    - report `:815-848` (B10);
    - `storage-lab/b10/notes.md:15-39`, `b10/b10go-2026-11-17-1902.log`, `b10/b10resume-2026-11-17-1906.log`,
      `b10/s4/`;
    - memory notes `proxmox-worker-autostart-nfs-race`, `gpu-admission-race`, `pve-memtest-plan`.
- [ ] **Step 12: Check every runbook.**
  - Run: `rg -n "192\.0\.2\.|10\.99\.9\.|lab-|9970|97[0-6]" docs/runbooks/storage-vm-*.md
    docs/runbooks/pve-planned-reboot.md`.
  - Expected: no hits, except inside quoted lab evidence lines that are marked as such.
  - Wrap lines at 120 characters.
- [ ] **Step 13: Commit** `docs(runbooks): storage VM operations, cutover and planned host reboot (ADR 0017)`.
  Merge event: apps `main`, where ArgoCD syncs and nothing changes (docs only). Ben reviews before the merge.

### Task 2.9: apps: the one-flag guard layer and the guard coverage check

Worktree AP, on `feat/retained-storage-vm` after Task 2.6, so it merges with the rest of AP in Task 3.6 Step 2. ADR
Guards, "The one-flag guard" (Ben, 2026-11-22). The design, its critique and the prototype renders are in
`evidence/one-flag-guard/` (`design.md`, `critique.md`, `crit/rg2.yaml`, `crit/o0.yaml`-`o5.yaml`).

One guard (D48, Ben 2026-11-22): the layer runs apps#1707's generic guard, `infrastructure/base-configs/files/
retained-startup/guard.py <app> <root> [<kind> [<marker-file>]]`, from ConfigMap `retained-startup-guard`. There is
one guard implementation. AP must contain apps#1707: if `infrastructure/base-configs/files/retained-startup/guard.py`
is missing on AP, run `g -C $AP rebase origin/main` first. The marker is unchanged: `guard.py <id> <root>` reads
`<root>/.homelab-<id>-data` holding `homelab/<id>/data/v1` and a newline, as the lab's marker guard did and as
`storage.yml` writes it (ansible `roles/storage_vm/files/homelab_storage/reconcile.py:107-108`). `guard.py` is stricter
on the id: it refuses one that ends in `-`, which `check-retained-inventory.py`'s `ID_PATTERN` allows.

**Files:**
- Create: `templates/retained-guard.yaml`, the shared layer. Start from `evidence/one-flag-guard/crit/rg2.yaml`:
  - `retained.id: ""`;
  - `controllers.main.strategy: Recreate`;
  - init container `0-retained-guard`: image `python` with the digest today's guards pin (`sha256:8c9a3bf2...`, in the Renovate-managed form:
    `repository: python` with `digest:` on the next line; copy it whole from `services/media/audiobookshelf/values.yaml`), command `[python3, -I, -B, /retained-startup/guard.py,
    '{{ .Values.retained.id }}', /retained]`, no args, no env, no `dependsOn`, securityContext `runAsNonRoot`,
    1000/1000, no privilege escalation, read-only root, drop ALL, RuntimeDefault; requests 10m/32Mi, limits 100m/64Mi;
  - `persistence.config.enabled: false`;
  - `persistence.retained`: `existingClaim: '{{ required "retained.id is required" .Values.retained.id }}-iscsi'`,
    `globalMounts: []`, `advancedMounts.main.main: [{path: /config}]`,
    `advancedMounts.main.0-retained-guard: [{path: /retained, readOnly: true}]`;
  - `persistence.retained-guard`: `type: configMap`, `name: retained-startup-guard`, `defaultMode: 292`, mounted only
    in `0-retained-guard` at `/retained-startup`, read-only.
  - The templated id in the command: app-template 5.3.0 renders it. Checked 2026-11-22 with the cached chart, helm
    3.19.0 and `--set-string retained.id=f1-flagged`, as the AppSet passes it: the command came out `[python3, -I, -B,
    /retained-startup/guard.py, f1-flagged, /retained]`. `_command.tpl` itself does not template; the chart templates
    the whole values first. Step 1's `test_flag_renders_guard_first` pins that literal argv. Fallback, decided here,
    if that test fails or a chart bump stops the values templating: env `RETAINED_ID: '{{ .Values.retained.id }}'`
    (app-template renders env values itself, `_env.tpl:68`; the same check rendered `value: f1-flagged`) and
    `$(RETAINED_ID)` in place of the id in the command, which the kubelet expands without a shell. An unexpanded
    `$(RETAINED_ID)` fails `guard.py`'s name check, so it fails closed. This is not 3.9 Step 2's `helm.parameters`
    fallback, which is about how the id reaches Helm. Taking the fallback changes two tests with it:
    `test_flag_renders_guard_first` pins `$(RETAINED_ID)` in the argv and `RETAINED_ID: f1-flagged` in the env, and
    the check resolves a `$(VAR)` in the guard's argv from that container's env before it compares `<app>` with the
    entry's id (an unresolved `$(VAR)` fails the check).
- Delete: `infrastructure/base-configs/templates/retained-volumes-guard.yaml`. It renders only the marker-only
  ConfigMap `<id>-retained-guard` with its own `guard.py`, one per `origin: new` entry, and nothing else, so nothing
  is left in it. The PV and PVC stay in `retained-volumes.yaml`.
- Modify: `scripts/storage/tests/test_retained_inventory.py`: delete `test_guard_marker_only_for_new` and the two
  `retained-volumes-guard.yaml` lines at the end of `test_numeric_like_values_render_as_strings`.
- Modify: `infrastructure/base-configs/templates/retained-startup-guard.yaml` (1.3a). It renders ConfigMap
  `retained-startup-guard` in a fixed list of five namespaces; the guard must be in every inventory namespace too,
  the canary's `democratic-csi` included. Keep the fixed list (the hand-wired guards, NFS-side ones included, are not
  all in the inventory) and add each `namespace` of `files/retained-volumes.json`, de-duplicated:
  `$namespaces := list "databases" ... "operations"`, append each entry's `.namespace`, then `range ($namespaces |
  uniq | sortAlpha)`, with `namespace: {{ . | quote }}` (1.3a renders it unquoted; inventory namespaces are only
  checked to be non-empty strings, so `1e3` would render as a number). A duplicate ConfigMap would break the
  base-configs sync. No second list to keep in step.
- Modify: `scripts/storage/tests/test_startup_guards.py` (1.3a). `template_namespaces()` parses `range list (...)`
  by regex, so read the fixed list from the `$namespaces := list (...)` line instead.
  `test_template_namespaces_are_the_consumers` keeps both asserts on that fixed list: it equals the `guards()`
  namespaces and is the pinned five. Add `test_template_covers_inventory_namespaces`: rendered with an empty
  inventory, exactly the five; with fixture entries in `democratic-csi`, `media` and `1e3`, one
  `retained-startup-guard` in each of the seven namespaces, no duplicate, and every `metadata.namespace` a string.
  `test_no_other_retained_configmap_is_mounted` needs no change: the layer and a hand-wired `origin: new` consumer
  both mount `retained-startup-guard`. 1.3a's `apps()` reads only app values, not the layer, so a flagged app needs no test
  edit (the `GUARDS` table was deleted in apps#1707); `check-retained-guards.py` covers it.
  The hand-wired `origin: new` shape is a plain-manifest consumer like the canary, which `apps()` does not read. An
  app-template `origin: new` app uses the flag: a hand-wired guard in its values outside the fixed five fails 1.3a's
  namespace asserts, so CI stops it (fails closed, not a supported shape).
- Modify: `bootstrap/appsets/cluster-apps.yaml` `templatePatch` (`:133-202`): `{{- $retained := dig "retained" "" . }}`.
  When it is set, and only in the `$isService` (app-template) branch, the chart source gets
  `- $values/templates/retained-guard.yaml` after the `commonValuesExtras` loop and before the app's own
  `values.yaml`, and `helm.parameters: [{name: retained.id, value: <id>, forceString: true}]`. A `baseApp` variant
  reads only its own `app.yaml`, so it sets its own `retained:` or gets no layer.
- Create: `scripts/check-retained-guards.py`, run in `validate-and-diff.yml` next to `check-retained-inventory.py`.
- Test: `scripts/storage/tests/test_retained_guards.py`.
- Audit fold-in (D49, genericity audit "apps `storage-vm`" finding 1): the second guard is already removed above
  (`retained-volumes-guard.yaml` and its two tests); nothing ships an interim copy before apps#1707.
- Audit fold-in (finding 4): Modify `bootstrap/appsets/cluster-apps.yaml:108-115`, the Secret `jqPathExpressions`.
  It selects on an annotation, not on names: `select(.metadata.annotations["homelab.starktastic.net/live-secret-data"]
  != "true") | .data`. Each Secret it names today (`alertmanager-kube-prometheus-stack-alertmanager`, `authentik`,
  `falco-falcosidekick`, `democratic-csi-driver-config`) gets that annotation from its chart values. Whether each
  chart can annotate that Secret is UNVERIFIED: Step 1 tests it per chart, and a chart that cannot keeps its name in
  the expression with a comment naming the missing chart key. A new Secret that must go live then needs one
  annotation, not a shared-list edit.
- `renovate.json`: no change. The layer's digest stays hand-bumped, as today's guard digests are, because one bump
  restarts every flagged app (ADR Consequences, "Shared guard layer"); a bump is a maintenance-window PR.
- Modify: `docs/diagrams/value-cascade.svg` source and the README text it feeds, if they list the value layers.

**Interfaces:**
- Consumes:
  - the inventory `infrastructure/base-configs/files/retained-volumes.json`, read by `retained-volumes.yaml` (PV and
    PVC) and, from this task, by `retained-startup-guard.yaml` (its namespaces);
  - the generic guard `guard.py` and ConfigMap `retained-startup-guard` (apps#1707, D47);
  - the AppSet layering (`cluster-apps.yaml:142-173`);
  - Task 2.6's `check_bindings`, which stays scoped to migrated bindings: the layer's `existingClaim` is templated, so a
    flagged app gives `check_bindings` nothing, and `check-retained-guards.py` covers it (`retained:` is refused on
    migrated entries). A test pins both.
- Produces:
  - the `app.yaml` key `retained: <id>` (a string), for `origin: new` entries only; CI refuses it on a `migrated`
    entry;
  - claim name `<id>-iscsi` for flagged apps;
  - ConfigMap `retained-startup-guard` in every inventory namespace;
  - the guard's log line, as `guard.py` prints it (`Retained identity accepted.`).
- An `origin: new` claim's guard, flagged or hand-wired, mounts ConfigMap `retained-startup-guard` and runs
  `guard.py` with the entry's id as `<app>`. No app adds a content check after it (D47), and a new retained app never
  edits shared guard code (D46). Add this case to the Step 1 check-script cases.
- Later (D46): Task 5.12 lifts the refusal of `retained:` on `migrated` entries (with `copied` set) and adds marker
  overrides from an apps-only file, passed as the guard's `<app>`, `<kind>` and `<marker-file>` arguments. Write the
  check so that lifting the refusal is one rule's change, and keep `guard.py` and the layer free of app names and app
  versions.

First sync of a new app (accepted): base-configs renders the PV and the PVC, and the PVC goes into the entry's
namespace, as does ConfigMap `retained-startup-guard` when no other entry or fixed namespace has it. base-configs'
only `CreateNamespace` target is its destination `default` (`config-apps.yaml`), so the namespace exists only once the
app itself syncs (its own `CreateNamespace=true`, `cluster-apps.yaml:91`). Until then base-configs' sync fails on that
PVC (and that ConfigMap) and retries (`retry.limit: 30`, backoff to 5 min, over 2 h in all), and may post an ntfy
sync-failed line. The app's pod waits Pending on its claim in the meantime. This is accepted, not fixed: the inventory
PR and the app PR can merge together, and the retries cover the gap.
UNVERIFIED: whether the failed PVC stops the later sync waves of base-configs; read the first new app's base-configs
sync result in Task 3.9.

- [ ] **Step 1: Write the failing tests** (`test_retained_guards.py`). Render with the docker helm wrapper (memory
  `workstation-offline-checks`) and the cached app-template 5.3.0, using the AppSet's layering:
  - `test_flag_renders_guard_first`: a fixture app with only `retained: f1-flagged` renders a Deployment whose first
    init container is `0-retained-guard`, which mounts claim `f1-flagged-iscsi` read-only at `/retained` and ConfigMap
    `retained-startup-guard` read-only at `/retained-startup`, with command exactly `[python3, -I, -B,
    /retained-startup/guard.py, f1-flagged, /retained]` when the id comes in as `--set-string retained.id=f1-flagged`;
    the main container mounts the claim at `/config`; there is no `config` nfs claim; the strategy is `Recreate`.
  - `test_guard_runs_before_app_init_containers`: the fixture adds an app init container `aaa-init` that mounts the
    claim; the guard still comes first (Kahn order, `crit/o4.yaml`).
  - `test_empty_id_fails`: the render fails (`required`).
  - `test_custom_mounts_replace_default`: a fixture with `persistence.retained.advancedMounts.main.main: [{path:
    /data}]` mounts `/data` and not `/config`.
  - `test_layer_missing_fails` runs on a custom-mount fixture (the schema rejects `persistence.retained` with no
    `existingClaim`). A zero-line `/config` app without the layer renders onto the NFS `config` claim instead, so
    that case is caught by the coverage check: `test_check_reads_appset_layering` drops the AppSet branch and expects
    the zero-line fixture's inventory claim to be reported unconsumed.
  - check script cases, on fixture trees. A consumer is matched to an entry by `(namespace, claim)`: the app's
    destination namespace (`cluster-apps.yaml` `destination.namespace`, from the app's generator `namespace`) and the
    claim it mounts. Consumers are counted by state:
    - `test_consumer_matched_by_namespace_and_claim`: a flagged app (and, separately, a hand-written consumer) in
      namespace `tools` mounting claim `f1-flagged-iscsi`, against an entry with `namespace: media` and the same claim,
      fails: the entry has no consumer, and the consumer's claim is not in the inventory. The same app in `media`
      passes;
    - an `origin: new` entry, or a `migrated` entry with `copied`, needs exactly one consumer; none or two fail;
    - a `migrated` entry without `copied` (between its Inventory PR and its switch PR, or after a switch revert) needs
      none: no consumer passes, one consumer fails;
    - a consumer with no guard, a read-write guard mount, a guard after another claim-mounting init container, or a
      guard without the `retained-startup-guard` mount fails;
    - an `origin: new` consumer whose guard runs `guard.py` with an `<app>` other than the entry's id fails, and so
      does an `origin: new` entry whose id `guard.py` would refuse (`x-`), so CI stops it before a pod does;
    - a flagged app whose inventory `claim` is not `<id>-iscsi` fails; `retained:` on a `migrated` entry, on a
      non-services app, or with an id not in the inventory fails; a variant of a flagged base app gets no layer;
    - `test_flagged_app_invisible_to_check_bindings`: Task 2.6's `check_bindings` returns `[]` for a flagged fixture,
      and `check-retained-guards.py` passes it;
    - a hand-written migrated guard (audiobookshelf's shape) passes, and so does the F1 canary's shape: a plain
      Deployment under a kustomize `manifests/` dir, init container `guard` running `python3 -I -B
      /retained-startup/guard.py f1-canary /data`, ConfigMap `retained-startup-guard` (`defaultMode: 292`),
      claim `f1-canary` (built as written; the live canary uses `f1-canary-iscsi` after the 2026-11-25 claim rule).
  - Run: `$VPY -B -m unittest discover -s scripts/storage/tests -p 'test_retained_guards.py' -v`.
  - Expected: FAIL (no layer, no AppSet key, no script).
  - Audit fold-in: `test_live_secret_annotation`: render the four apps above as Step 2 renders apps
    (`check-admin-gate.py` `render_app`); each named Secret carries the annotation, and the AppSet's Secret expression
    compares no `metadata.name` except a documented fallback. Expected: FAIL until Step 2.
- [ ] **Step 2: Write the layer, the AppSet change and the check.** Change nothing else in the AppSet. The check
  derives each app's value files from `cluster-apps.yaml`'s `templatePatch` (never a second copy of the layering) and
  looks at every app, not only the changed ones:
  - app-template apps: render with `helm template`, as `scripts/check-admin-gate.py:471-481` `render_app` does (in
    CI it pulls the chart by repo and version; offline tests use fixtures and the cached 5.3.0 tarball);
  - plain manifests and kustomize `manifests/` dirs: read the `Deployment`/`StatefulSet` pod specs directly;
  - kube-prometheus-stack, loki and the Bitnami charts: Task 2.6's static resolvers (Bitnami's arrives with wave 6,
    Task 4.W), not a render.
- [ ] **Step 3: Run to PASS.** The Step 1 command, then the whole `scripts/storage/tests` suite (with Task 2.6's
  `PATH` prefix),
  `scripts/check-retained-inventory.py --base origin/main`, `scripts/check-admin-gate.py`, and yamllint with
  `.github/yamllint.yaml`. Expected: all pass, and the AppSet renders unchanged for every app without `retained:`
  (compare `argocd appset generate` output, or the diff preview, before and after).
- [ ] **Step 4: Commit** `feat(storage): one-flag retained guard layer and guard coverage check (ADR 0017)`.
  Live proof is Task 3.9 (D38): until it passes, no real app uses the flag. The Secret-annotation change is its own
  commit, `refactor(argocd): live Secret data selected by annotation, not by name` (and its follow-up for authentik and
  falcosidekick). democratic-csi cannot annotate its Secret and stays a name fallback. The diff preview shows the
  annotation on three Secrets (kube-prometheus-stack Alertmanager, `authentik`, `falco-falcosidekick`; falcosidekick's
  chart-wide `customAnnotations` also puts it on its Role, Service and Deployment metadata) and a changed pod-template
  checksum on 3 Deployments: authentik server and worker (`checksum/secret`) and `falco-falcosidekick`
  (`checksum/config`). Both charts hash the whole rendered Secret, annotations included, and `cluster-apps.yaml` does
  not ignore those keys (do not add them). Merge event (Task 3.6 Step 2): those 3 Deployments roll once. UNVERIFIED:
  that the Alertmanager StatefulSet does not roll (its chart has no checksum; the operator owns the pod template).

### Task 2.12: apps: democratic-csi values and its test (audit fold-in)

Worktree AP, `feat/retained-storage-vm`, any time before Task 3.6 Step 2, where it merges with the rest of AP. D49,
genericity audit "apps `storage-vm`" findings 2 and 3. No other task touches these files.

**Files:**
- Modify: `scripts/storage/tests/test_democratic_csi_values.py` (`:80-86` exact driver digest, `:147-151` `0.15.1`).
- Modify: `infrastructure/system/democratic-csi/manifests/values.yaml:81-84` (delete `node.cleanup`).
- Modify, only if Step 3 finds Renovate blind to the form: `renovate.json`.

- [ ] **Step 1: Write the failing tests.**
  - `test_no_values_for_patched_out_containers`: `values.yaml` has no `node.cleanup`; `node-shutdown-patch.yaml` still
    removes the cleanup container (`test_patch_targets_exist_upstream` keeps checking the index against the chart).
  - `test_images_pinned_by_digest` keeps its `@sha256:[0-9a-f]{64}$` regex and drops the exact
    `ghcr.io/democratic-csi/democratic-csi:v1.9.5@sha256:...` assert. `test_chart_ref` keeps name and repo and checks
    the version is an exact `^\d+\.\d+\.\d+$` pin, not `0.15.1`: Renovate already gates that chart
    (`renovate.json:85-87`). The `:v2.9.0@` registrar check (`:249`) stays; it ties the mount list to that version.
  - Run: `cd $AP && PATH=~/.cache/claude-household-boundary/bin:$PATH python3 -m unittest discover -s
    scripts/storage/tests -p 'test_democratic_csi_values.py' -v`. Expected: FAIL (`node.cleanup` present).
- [ ] **Step 2: Delete `values.yaml:81-84`.** Run Step 1. Expected: PASS. Render
  `infrastructure/system/democratic-csi/manifests` with `kustomize build --enable-helm` (as `validate-and-diff.yml`
  does) before and after. Expected: identical output, since the patch removes the cleanup container anyway.
- [ ] **Step 3: Check whether Renovate sees `registry:` + `tag:` images** (read-only).
  - Find a file on apps `main` with the same form: `git -C $AP grep -n -A1 -E '^\s+registry: ' origin/main -- '*.yaml'`.
  - Read the Dependency Dashboard: `gh issue list -R Starktastic-Homelab/apps --search 'Dependency Dashboard in:title'
    --json number`, then `gh issue view <n> -R Starktastic-Homelab/apps --json body --jq .body | grep -n '<that image>'`.
  - Expected: the image is listed, and nothing changes. If it is not listed, or no `main` file has the form, add one
    `customManagers` regex entry to `renovate.json` (datasource `docker`, `registry: <depName>` then
    `tag: <currentValue>@<currentDigest>`), keep the democratic-csi no-automerge rule matching these images, and
    check the JSON with `python3 -m json.tool renovate.json`. Whether the regex matches is UNVERIFIED until Renovate's
    first run after Task 3.6 Step 2; read the dashboard then.
- [ ] **Step 4: Commit** `test(storage): democratic-csi tests check shape, not pinned versions; drop dead cleanup
  values`, and `chore(renovate): track registry/tag images` if Step 3 added the rule.

### Task 2.13: ansible: `storage.yml` reconciles under a held runbook lock (D51)

The restore runbook (`docs/runbooks/storage-vm-restore.md` steps 5 and 6) must run the reconcile while it holds its own
lock. The playbook needs the vault password, the SSH key and the Proxmox token, which exist only as Actions secrets,
so the run goes through the workflow, which adopts the held lock (Ben, D51).

**Files** (worktree A, branch `feat/retained-storage-vm`, after Task 2.4's commits; ships in the Task 3.2 PR):
- Modify: `.github/workflows/storage.yml`.
- Modify or create: the workflow test that pins `storage.yml`'s steps (`scripts/tests/test_storage_workflows.py`).
- Modify (D): `docs/runbooks/storage-vm-restore.md` steps 5 and 6 (replace the open question).

**Interfaces:**
- Consumes: the lock record `/maintenance/operation.json` (`owner`, `nonce`, `operation`), the pinned
  `maintenance_lock.py verify`, the owner shape the restore runbook takes (`claude-code/storage-restore/<UTC ts>`).
- Produces: `workflow_dispatch` input `held_lock_owner` (string, default empty).

- [ ] **Step 1: Write the failing tests** (parse `storage.yml` with PyYAML, as the existing workflow tests do):
  - `test_held_lock_input`: `on.workflow_dispatch.inputs.held_lock_owner` exists, `required: false`, default `''`.
  - `test_held_lock_adopt_step`: a step that runs only when the input is non-empty, and refuses (non-zero exit) unless
    `operation.json` exists, its `owner` equals the input exactly, and the input matches
    `^claude-code/storage-restore/[0-9TZ:-]+$`. It writes `MAINTENANCE_OWNER` and `MAINTENANCE_NONCE` to `GITHUB_ENV`
    with `::add-mask::` on the nonce first and never echoes it.
  - `test_held_lock_skips_acquire_and_release`: with the input set, the `Try the maintenance lock once` and
    `Release the lock after success` steps do not run, and `Reconcile under the lock` still runs `maintenance_lock.py
    verify` first. With the input empty every existing step behaves as before (the existing tests stay green).
  - `test_held_lock_not_on_other_triggers`: the adopt step's `if` includes `github.event_name == 'workflow_dispatch'`.
  - Run the ansible suite. Expected: FAIL on the four new tests.
- [ ] **Step 2: Implement** the input, the adopt step (python3 `-I`, standard library, no `set -x`) and the `if`
  changes. The owner regex and prefix live in one place in the step. The dry-run and `ready`/`held` steps are
  unchanged.
- [ ] **Step 3: Run** the ansible suite, `test_workflow_credentials.py` and `ansible-lint --offline`. Expected: PASS.
- [ ] **Step 4: Runbook (D).** Steps 5 and 6 of `storage-vm-restore.md`: `gh workflow run storage.yml -R
  Starktastic-Homelab/ansible -f held_lock_owner=<the owner from step 1>`, then read the run. Expected in step 5: the
  run fails as designed with the `hold-create` refusals, and the restore lock is still held by the restore owner
  (`maintenance_lock_op.sh verify` with that owner). Step 6: the same dispatch, green. Drop the open question.
- [ ] **Step 5: Commit** (A) `feat(storage): reconcile under a held runbook lock from a dispatch input`; (D)
  `docs(runbooks): restore reconciles through the storage workflow under its own lock`.

---

## Part 3: Foundation live (ADR Migration 2)

Part 3 runs ADR Migration step 2 (ADR `:953-967`) in production: the bridge, the ansible storage PR, the three-image
rebuild with the worker storage NICs folded in (D3), the storage VM and its data disks, democratic-csi with an empty
inventory and the D18 canary, then gates F1 and F2 and the Task 3.10 drill. Every app stays on Proxmox CSI for the whole
part, so a storage-side failure here costs only an empty storage VM (ADR `:966-967`). The exception is Task 3.10: it
cordons a production worker, moves its pods gracefully (four stay Pending), then hard-stops it with only the canary
written. Global Constraints apply to every step; they are not repeated here.

**Before Part 3 starts:**
- Part 1 is done, and `evidence/1.1/facts.md` shows the backup gate met and pstore empty.
- D1, D2, D3, D4, D5 and D18 are decided. The names below are Part 2a's pinned table (`<D1:storage_vmid>`,
  `<D1:storage_name>`, `<D1:storage_lan_ip>`, `<D1:storage_bridge_ip>`, `<D1:worker_bridge_start>`,
  `<D1:placeholder_vmid>`, `<retained_volname>`, `<regen_volname>`, `<D2:retained_gib>`, `<D2:regen_gib>`).
- Part 0 and Part 2 are committed on their branches, and every suite in them passes.
- The Task 2.7 runbooks are merged to apps `main` before Task 3.5. Tasks 3.5, 3.7, 3.8 and 3.10 run from them:
  `storage-vm-bootstrap.md`, `storage-vm-rebuild.md`, `storage-vm-readonly-fs.md`, `pve-planned-reboot.md` and
  `storage-vm-fencing.md`.
  That PR is docs-only apart from the empty inventory `[]` it may carry (Task 3.5 Step 0), which nothing on `main`
  reads yet, so its merge makes ArgoCD sync with no change. Nothing earlier merges it; Task 3.5 Step 0 does.

**How live steps run.**
- Reads use Part 1's convention ("How live reads run in this part"): the helper with a rows file, `pve` and `tn` rows,
  `KUBE <args>` for kubectl through QGA on the first ready tagged master, and `gh` on the workstation printing metadata
  only. They need one read-only Ben OK per session.
- `VM <vmid> '<cmd>'` is short for a `pve` row `qm guest exec <vmid> -- bash -c '<cmd>'`. It reaches the storage VM and
  the workers through QGA (the workstation has no SSH key for them). Commands are ASCII only, with double quotes
  inside `'<cmd>'`, never single quotes. Find worker VMIDs by their Proxmox tags, as Part 1 does, and never hardcode
  them.
- Every local commit, cherry-pick and rebase below runs `. env.sh` first and uses `g` (Task 0.1 Step 1), because the
  workstation has no git identity.
- A mutation through the helper (`pvesm`, `qm`, `zpool`, a write on the storage VM, a `KUBE` write) runs only after
  **Ben OK** at that step, with the exact command shown first.
- A merge is a live event. Each step names it. A PR is pushed, opened and merged only when Ben asks, and is merged with
  `gh pr merge <n> --squash --match-head-commit <sha>` (memory `pr-merge-mechanics`).
- Each task writes its rows files, the scrubbed output, the run URLs and a short `facts.md` to `evidence/3.<n>/`.

**Order.** The tasks run one at a time, in order 3.1 to 3.8 (Task 3.9 comes after the Part 3 gate), with two
exceptions: Task 3.6 Step 7 (D37) runs inside Task 3.7, between its Steps 7 and 8, while the canary writer is drained;
and Task 3.10 runs inside Task 3.8, after its Step 6 (F2 written up) and before its Step 7 stops the canary. 3.1 comes
before 3.3 because the folded worker NIC needs `vmbr2`. 3.2 comes before 3.3 so that the rebuilt cluster deploys with
Argo's `--enable-helm` and the worker IQNs. No merge lands inside a backup window, and none lands while another workflow
holds the maintenance lock.

### Task 3.1: Bridge PR (ansible)

**Files:**
- PR branch (worktree A): `feat/storage-bridge`, built in Task 2.3 (`08f540f`, `325e16a` plus the 2.3 commit
  `ci(storage): apply the storage bridge from its own workflow, not deploy`).
- Create (evidence): `evidence/3.1/{rows-pre.json,pre.txt,rows-post.json,post.txt,facts.md}`.

**Interfaces:**
- Consumes: A `roles/proxmox_storage_bridge/` (default `proxmox_storage_bridge_name: vmbr2`, `defaults/main.yml:4`),
  `proxmox-storage-bridge.yml` (hosts `proxmox_hosts`), `.github/workflows/storage-bridge.yml` (2.3: `push` on the role
  and playbook paths, plus `workflow_dispatch`).
- Produces: bridge `vmbr2` on pve with no address and no uplink, from `/etc/network/interfaces.d/vmbr2`. Task 3.3
  (worker NICs) and Task 3.4 (storage VM `net1`) consume it.

- [x] **Step 1: Read-only pre-check** (rows file `evidence/3.1/rows-pre.json`, `pve`):
  - `ip -br link`, `ip -br addr`
  - `grep -nE '^source /etc/network/interfaces\.d/\*' /etc/network/interfaces`
  - `ls -la /etc/network/interfaces.d/`, `grep -rn vmbr2 /etc/network/interfaces /etc/network/interfaces.d/ || true`
  - `grep -l 'bridge=vmbr2' /etc/pve/qemu-server/*.conf || true`

  Expected: `vmbr2` does not exist, no file or guest names it, and the `source` line is present (the role refuses
  without it, `roles/proxmox_storage_bridge/tasks/main.yml` first task). Save the full `ip -br link` as the baseline.
  Any hit on `vmbr2` is a stop: bring it to Ben, who picks another name (D1).
- [x] **Step 2: Push and open the PR** (only when Ben asks).
  - `git -C $A push -u origin feat/storage-bridge`
  - `gh pr create -R Starktastic-Homelab/ansible --head feat/storage-bridge --title "feat(storage): additive storage
    bridge vmbr2 with its own workflow (ADR 0017)"`, with the Co-Authored-By trailer in the commits and the Claude Code
    line ending the body.
  - Expected: `validate.yml` green, including `test_proxmox_storage_bridge.py` and the syntax check.
- [x] **Step 3: Merge with `[skip ci]` in the squash subject, then dispatch the bridge workflow.** **Ben OK.**
  - Why: the PR also edits `.github/workflows/validate.yml` (`08f540f`) and `.github/workflows/deploy.yml` (2.3's
    `paths-ignore` lines). Neither file is in `deploy.yml`'s `paths-ignore` (origin/main `deploy.yml:12-25`), and a
    push runs a workflow unless every changed path is ignored. So a plain merge would also start a full `deploy.yml`.
    The precedent is ansible#314: merged with `[skip ci]`, then the workflow was dispatched by hand (memory
    `proxmox-worker-autostart-nfs-race`). This is D32.
  - Run: `gh pr merge <n> -R Starktastic-Homelab/ansible --squash --match-head-commit <sha> --subject "feat(storage):
    additive storage bridge vmbr2 (ADR 0017) [skip ci] (#<n>)"`
  - Expected: no push workflow runs (`gh run list -R Starktastic-Homelab/ansible --limit 5 --json
    workflowName,event,headSha` shows nothing on the merge SHA).
  - Then: `gh workflow run storage-bridge.yml -R Starktastic-Homelab/ansible --ref main` (**Ben OK**: this is the
    host network change).
  - Live event: `storage-bridge.yml` writes `/etc/network/interfaces.d/vmbr2` and runs `ifup vmbr2` only. It never
    runs `ifreload` (role comment, `tasks/main.yml:2-3`).
  - Expected: run green, `changed=2` (file written, bridge brought up), `failed=0`.
- [x] **Step 4: Idempotence.** Dispatch `storage-bridge.yml` once more (**Ben OK**). Expected: `changed=0`.
- [x] **Step 5: Read-only post-check** (`rows-post.json`, `pve`): the Step 1 rows plus `ip link show vmbr2` and
  `ip -br addr show vmbr2`.
  - Expected: `vmbr2` exists with the `UP` admin flag. `NO-CARRIER` is normal until a guest attaches (lab B2 Step 1).
    It has no address.
  - Every other line of `ip -br link` and `ip -br addr` equals the Step 1 baseline (vmbr0 and vmbr1 untouched).
  - Write `evidence/3.1/facts.md`.
- **Rollback.** A revert alone does not remove the bridge: the revert deletes the workflow, so nothing runs.
  1. While no guest uses `vmbr2` (Step 1's `grep -l` is empty), on pve: `ifdown vmbr2 && rm
     /etc/network/interfaces.d/vmbr2`. This is the role's `absent` path, which the workflow cannot reach by design
     (2.3 `test_workflow_and_deploy_ignore`). **Ben OK.**
  2. Then a revert PR, merged with `[skip ci]`.

  After Task 3.3 the workers use `vmbr2`, so from then on a rollback is a terraform change first.
- **Done 2026-11-23:** ansible#353 merged as `8c7f3f7` with `[skip ci]`; dispatch `changed=2`, then `changed=0`; post-check clean apart from the kernel IPv6 link-local on `vmbr2` (no IPv4, no uplink). Evidence `evidence/3.1/`.

### Task 3.2: Ansible storage PR

**Files:**
- PR branch (worktree A): `feat/retained-storage-vm`. Before pushing, run `. env.sh; git -C $A fetch origin && g -C
  $A rebase origin/main`, so the 1.2 and 3.1 commits drop out. Then re-run the Part 0.1 ansible suites.
- Contents:
  - the role `roles/storage_vm/`, the playbooks `storage.yml`, `storage-expiry.yml` and `storage-dry-run.yml`, and
    `tasks/lab-guard.yml`;
  - `roles/k3s_common` (IQN, open-iscsi, `iscsid.socket`, fstrim, no-force-detach);
  - `roles/bootstrap_cluster/tasks/argocd.yml:89-90` (`--enable-helm`);
  - `inventory/proxmox.yml` (`storage` group);
  - Tasks 0.2, 0.3, 2.2 (workflows `storage.yml` and `storage-expiry.yml`, `scripts/storage_ready.py`), 2.3
    (`group_vars/storage/storage_vm.yml` with no `storage_vm_pv_devices` key, so the role default `{}` applies), 2.10
    (VG free-space check, `no-space` refusal, per-class VG-missing refusal, and their tests), and the A parts of 2.4
    and 2.6.
- Create (evidence): `evidence/3.2/{rows-pre.json,pre.txt,rows-post.json,post.txt,facts.md}`.

**Interfaces:**
- Consumes:
  - `deploy.yml`, which runs `k3s.yml` with the pinned lock helper `887269798650`;
  - `k3s_common_kube_controller_manager_args` (A `roles/k3s_common/defaults/main.yml:50`);
  - `InitiatorName=iqn.2026-11.net.starktastic:{{ inventory_hostname }}` (A `roles/k3s_common/tasks/main.yml:162`).
- Produces:
  - on every k3s node: `/etc/iscsi/initiatorname.iscsi`, `iscsid.socket` enabled, `fstrim.timer` enabled;
  - on the masters: `disable-force-detach-on-timeout=true` (D8);
  - `argocd-cm` `kustomize.buildOptions: --enable-helm`;
  - the workflows `storage.yml` (hourly at `:05` UTC, `storage-changed`, push, dispatch) and `storage-expiry.yml`
    (daily at `10:05` UTC). Both skip with `Skipping: no host in the storage group; nothing touched` until 3.4 and
    3.5.

- [x] **Step 1: Read-only pre-check** (`rows-pre.json`):
  - `gh run list` for all five repos (`--status in_progress` and `--status queued`): nothing running;
  - `pve`: `test -e /var/lib/homelab-maintenance/operation.json && echo HELD || echo FREE`, run through `VM` on the
    runner VM300 (found by name, never hardcoded). Expected `FREE`;
  - `KUBE get applications -n argocd -o
    jsonpath='{range .items[*]}{.metadata.name} {.status.sync.status} {.status.health.status}{"\n"}{end}'`. Expected:
    every app Synced and Healthy;
  - for each k3s node, `VM <id> 'cat /etc/iscsi/initiatorname.iscsi 2>/dev/null; systemctl is-enabled iscsid.socket
    fstrim.timer 2>/dev/null; true'`. This is the before state.

  Hold apps merges from here until Step 4 passes (memory `pr-merge-mechanics`: no apps controller merge during a
  deploy).
- [x] **Step 2: Push and open the PR** (only when Ben asks).
  - `git -C $A push -u origin feat/retained-storage-vm`
  - `gh pr create -R Starktastic-Homelab/ansible --head feat/retained-storage-vm --title "feat(storage): storage VM
    role, storage workflows and k3s iSCSI settings (ADR 0017)"`. Neither the title nor the squash subject carries
    `[skip ci]`.
  - Expected: `validate.yml` green, including the steps that 0.1 and 2.2 added.
- [x] **Step 3: Merge.** **Ben OK.**
  - Live events:
    1. `deploy.yml` runs `k3s.yml` under the maintenance lock. The kubelet drop-in is already live from 1.2. The
       initiator-name file notifies `Restart k3s`, and the controller-manager argument changes `config.yaml` on the
       masters, so every k3s node restarts k3s once, one at a time (handler `throttle: 1`,
       `roles/k3s_common/handlers/main.yml:6-10`).
    2. `storage.yml` runs from its `push` trigger and skips.
    3. ArgoCD is upgraded in place by the bootstrap role with the new `argocd-cm`.
  - Expected: deploy run green with `failed=0` and the lock released afterwards (`FREE`). `storage.yml` run green, its
    log has `Skipping: no host in the storage group; nothing touched`, and its later steps are skipped. Save both run
    URLs and log tails to `evidence/3.2/`.
- [x] **Step 4: Read-only post-check** (`rows-post.json`):
  - **Played nothing on storage.** The deploy log has no task from role `storage_vm` (`gh run view <id> --log | grep -c
    'storage_vm :'` is `0`). The only storage-related play is the skipped lab guard. `ansible-inventory` is not run
    live.
  - **IQNs.** On each k3s node, `cat /etc/iscsi/initiatorname.iscsi` reads
    `InitiatorName=iqn.2026-11.net.starktastic:<node name>`, and the names are distinct. `systemctl is-enabled
    iscsid.socket fstrim.timer` reads `enabled` twice. `systemctl is-active iscsid` may read `inactive`: the socket
    starts it on demand.
  - **D8 (no-force-detach).** On each master:
    - `grep -n disable-force-detach /etc/rancher/k3s/config.yaml` shows the flag;
    - `journalctl -u k3s -b --no-pager | grep -o 'disable-force-detach-on-timeout=true' | tail -1` prints it. This is
      the lab B4 check: the k3s journal shows the controller-manager arguments.
  - **Argo.** `KUBE -n argocd get cm argocd-cm -o jsonpath='{.data.kustomize\.buildOptions}'` reads `--enable-helm`.
    Every app is Synced and Healthy again.
  - **D22 (`<D22:journal_scope>` = `storage VM and workers`).** On every k3s node, record
    `test -d /var/log/journal && echo DIR || echo NODIR` and `journalctl --header -n0 2>/dev/null | grep -m1 "File
    path"` (`/var/log/journal/...` means PERSISTENT, `/run/log/journal/...` means VOLATILE) in `rows-post.json` and
    `facts.md`. Judge per node, never by task name. The gates below are for the recommended answer; if
    `$EVR/0.3/d22.txt` records another, use its branch: `every node` expects PERSISTENT on every node, and `storage VM
    only` records the k3s nodes without a gate (5.5 Step 2 then needs other Check 11 evidence, 0.3 Step 5).
    - **Workers: PERSISTENT on each.** This is the gate: Check 11 at 300 s (Task 5.5) reads a worker's previous-boot
      journal. A worker reading VOLATILE is a stop.
    - **Masters: VOLATILE expected, not a gate.** The task is off the masters, but removing it never removes the
      directory, and the image may ship it (0.3 UNVERIFIED; lab b10 notes `:103`: `/var/log/journal` already existed
      on 973). A master reading PERSISTENT is recorded and brought to Ben; it does not stop the run.
    - **Storage VM:** it does not exist until 3.4 and is first configured in 3.5 Step 3. Its PERSISTENT check is in
      Task 3.5 Step 4.
  - **Kubelet (1.2 still in force).** `KUBE get --raw /api/v1/nodes/<node>/proxy/configz` on one worker shows
    `shutdownGracePeriod` `1m30s` and `shutdownGracePeriodCriticalPods` `40s`.
  - Then lift the apps hold. Write `facts.md`.
- **Rollback:** a revert PR (itself a deploy). The IQN files and the config line revert by the next deploy. Nothing on
  the storage side exists yet.
- **Done 2026-11-23:** ansible#355 merged as `d9b919d`; deploy green, every Step 4 check passed. The first `storage.yml` run failed closed before the lock (`storage_ready.py` could not load the `community.proxmox` inventory plugin through the Python API); fixed by ansible#356 (`5f7d66d`, `init_plugin_loader()`), then a dispatched run skipped green. D22: all three k3s nodes PERSISTENT, including the master (recorded for Ben). Evidence `evidence/3.2/`.

### Task 3.3: Three-image build and the full rebuild

**Files:**
- PR branches:
  - packer (worktree P): `feat/retained-storage-vm`, rebased in 0.1. It is the three-image layout.
  - terraform (worktree T): `ci/storage-root` (2.1a), the bot branches `packer-build-<run>-storage` and
    `packer-build-<run>`, `feat/storage-nic` (2.1c, cherry-picked onto `packer-build-<run>`) and
    `ci/manifest-by-name` (2.1d).
- Create (evidence): `evidence/3.3/` with the rows files, the plan excerpts read from the head run log, the run URLs,
  the D5 capture path and `facts.md`.

**Interfaces:**
- Consumes:
  - packer `build.yml`, whose jobs are `base`, then `k3s` and `storage` (both `needs: base`, serialized by the single
    self-hosted runner, in no fixed order), then `create-release` and the two manifest PRs (P
    `.github/workflows/build.yml:21-200`);
  - the manifest merge expression `sort_by(.name != "k3s")` (P `build.yml:154,196`);
  - 2.1a's storage leg and `apply-storage` step, W's wwn guard (Task 1.4), and 2.1c's `storage_nic` with
    `<D1:worker_bridge_start>`;
  - the D5 run sheet `~/.cache/claude-homelab-live/trim-rebuild-test.md`.
- Produces:
  - templates VM 900 (base), 901 (k3s) and 902 (storage);
  - a manifest with the `k3s`, `debian-13` and `storage` entries, then `debian-13` dropped by 2.1d;
  - three new k3s VMs, the workers with `net2` on `vmbr2` at `10.99.2.<D1:worker_bridge_start>` and the next
    address;
  - a fresh `KUBECONFIG_RAW`.

- [x] **Step 1: Pre-checks** (`rows-pre.json`). Abort if any one fails.
  - `pve`:
    - `ls -A /var/lib/systemd/pstore` (empty);
    - the 1.1 backup rows (no `PROBLEM` since the last read, last run green);
    - `qm status 901; qm status 902` (`does not exist`, or packer-owned templates);
    - `grep -E 'MemTotal|MemAvailable' /proc/meminfo`;
    - `ip -br link show vmbr2` lists the bridge (Task 2.4's workflow ran). Without it the apply destroys the k3s VMs
      and the creates fail.
  - Lock `FREE`, and no run queued or in progress in any repo.
  - `gh pr list` in packer, terraform, ansible and apps with `--json number,title,autoMergeRequest`: no auto-merge
    set anywhere. Open drift PRs alone do not block (Review Focus 5).
  - Last terraform `drift.yml` run clean (memory `worker-net-queues-rebuild`: check drift before any terraform PR).
  - Cluster baseline: every app Synced and Healthy. VolumeAttachments counted per node (33 expected; re-read live). The
    wwn count per worker from `qm config <worker> | grep -c 'wwn='` equals its VA count.
  - 1.1's packer-rights fact holds: the packer user's rights on 901 and 902 come from `/vms` or a pool path, not
    per-VMID ACLs (memory `pve-destroy-drops-vm-acl`).
- [x] **Step 2: Merge 2.1a (`ci/storage-root`)** as Part 2a Task 2.1a Step 10 describes. **Ben OK.**
  - It merges first because the bot manifest PRs are planned by their own copy of `validate-and-plan.yml`, which then
    contains the storage leg.
  - Live event: a no-op k3s apply with no ansible dispatch.
  - Evidence goes to `evidence/2.1a/`.
- [x] **Step 3: Freeze and hold.** From here until Step 10, nothing else merges in packer, terraform, ansible or apps.
  No drift or Debian-ISO PR is merged. Record the start time in `facts.md`.
  - **Renovate.** apps `renovate.json` has `platformAutomerge: true` and runs after 22:00 and before 06:00 on
    weekdays and all weekend (Asia/Jerusalem). So a new PR can open with auto-merge already on after any check. Ben
    suspends Renovate for apps for the window, through the Renovate app's repository access, not an apps merge. If he
    does not, Steps 4-9 run on a weekday between 06:00 and 22:00 Asia/Jerusalem, and must end before 22:00.
  - **Before each merge in Steps 4-9,** re-run `gh pr list` in packer, terraform, ansible and apps with `--json
    number,title,autoMergeRequest`, with no path filter. Expected: no PR has `autoMergeRequest`, and no PR merged in
    any of the four repos since Step 3 started (`gh pr list --state merged --search "merged:>=<start time>"`) other
    than this task's own: the packer PR (Step 4), the two manifest PRs (Steps 5 and 7) and 2.1d (Step 8). Either one
    is a stop.
- [x] **Step 4: Merge the packer PR.**
  - Push and open it only when Ben asks: `git -C $P push -u origin feat/retained-storage-vm`, then `gh pr create -R
    Starktastic-Homelab/packer --head feat/retained-storage-vm --title "feat: three-image layout, base, k3s and
    storage (ADR 0017)"`. There is no `[skip ci]` anywhere, since the push to `main` must build.
  - Merge. **Ben OK** (it starts a packer build).
  - Live event: `build.yml` on push.
    - `base` runs `packer build -force` at VM 900. The old k3s template at 900 is destroyed at the start, so from now
      until Step 7's apply no k3s VM can be recreated.
    - Then `k3s` builds 901 and `storage` builds 902, one at a time.
    - `create-release` follows, and one manifest PR opens (Task 2.11, D16): `Update VM templates (<k3s name>,
      <storage name>)` on `packer-build-<run>`, carrying the `k3s` and `storage` entries.
  - Expected:
    - all jobs green;
    - `qm config 900`, `qm config 901` and `qm config 902` each show `template: 1`, and their `name` equals the
      `custom_data.vm_name` of the matching manifest entry;
    - `qm config 902` has no `ciuser` or `sshkeys` (lab B2 Step 2);
    - the one manifest PR is open, and Task 2.11 Step 5's checks pass: names `["k3s","debian-13","storage"]`, and the
      `storage` entry's `artifact_id` is `902` and its `vm_name` is `qm config 902`'s `name`.
  - **If `k3s` fails:** no k3s template exists. Fix forward on a packer PR with terraform still frozen, and do not
    merge any terraform PR. A lost worker in this window cannot be replaced, so bring it to Ben at once.
  - **If only `storage` fails:** the manifest PR carries the new k3s entry and no `storage` entry. Go on with Steps
    5-9 (skip Step 5's merge). Bring the fix forward to Ben before Task 3.4: the `storage` entry reaches terraform only
    through a manifest PR (2.1b's plan fails closed without it), and a new packer build also renames the k3s template,
    so merging its manifest PR is another k3s rebuild.
- [x] **Step 5: Merge the `-storage` manifest PR first.** **Ben OK.** (Audit fold-in, Task 2.11: packer no longer
  opens a `-storage` PR. With 2.11 merged, skip this step; Step 6 then needs no manifest rebuild, only the
  `storage_nic` cherry-pick, and its check reads `["k3s","debian-13","storage"]`: the one PR carries both entries,
  D16.)
  - Expected plan, read from the run on the PR's current head:
    - k3s `No changes.`, because `builds[0]` is still `debian-13` (a stable sort of two non-k3s entries);
    - storage leg `storage root has no terraform.tfvars: not planned` (2.1b is not merged yet).
  - Live event: a no-op apply, no dispatch.
- [x] **Step 6: Update the k3s manifest PR branch, then fold in `storage_nic`.** Both bot PRs rewrote
  `packer-manifest.json` from the same base, so after Step 5 the k3s PR conflicts. Rebuild its manifest with the same
  expression `build.yml:154` uses:
  ```sh
  . ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh
  git -C $T fetch origin && git -C $T switch packer-build-<run>
  NEW=$(git -C $T show origin/packer-build-<run>:packer-manifest.json | jq -ce '[.builds[]|select(.name=="k3s")]|last')
  git -C $T reset --hard origin/main
  git -C $T show origin/main:packer-manifest.json | jq --argjson new "$NEW" \
    '.builds = ([.builds[] | select(.name != $new.name)] + [$new] | sort_by(.name != "k3s"))
     | .last_run_uuid = $new.packer_run_uuid' > $T/packer-manifest.json
  ```
  - Commit it with `g -C $T commit -am` and the bot's message `Update Packer manifest file - <run>`. Then
    `g -C $T cherry-pick <2.1c commit>`
    (`feat(k3s): give the workers a storage-bridge NIC (apply only with a VM replacement)`).
  - Push with `git -C $T push --force-with-lease origin packer-build-<run>`. **Ben OK** to push.
  - Check before the push: `jq -r '[.builds[].name]' packer-manifest.json` reads `["k3s","debian-13","storage"]`, and
    `git diff origin/main --stat` lists only `packer-manifest.json`, `main.tf`, `variables.tf`, `terraform.tfvars` and
    `scripts/tests/test-rebuild-cohort.py`.
  - **Per-worker variant (D3 = ADR).** The k3s PR stays the bot's manifest commit only. The two `storage_nic_workers`
    PRs of 2.1c run after Step 10, each with a manual drain, the wwn box, the scripted `qm set ... wwn=` restore and a
    reboot.
- [x] **Step 7: Read the plan and merge in the D4 mode.**
  - Read the plan from the log of the `validate-and-plan.yml` run on the PR's current head, not from the comment
    (memory `worker-net-queues-rebuild`: the comment can exceed GitHub's limit).
  - Expected:
    - every k3s VM `delete, create` with no `update`, so W's wwn guard prints nothing;
    - the workers' last `network` block has bridge `vmbr2`, and their `ipconfig2` is
      `ip=10.99.2.<D1:worker_bridge_start>/24` and the next host;
    - the master gets no `vmbr2` NIC;
    - the clone source is the k3s name, which equals `qm config 901` `name`, a template;
    - storage leg not planned;
    - no skip pattern in the title, the body or the last commit.
  - D4 = normal: tick no drain or destroy box.
  - D5 (if yes): follow `trim-rebuild-test.md` steps 2-7 exactly. Start the capture host part, then `zpool trim -w
    vm-pool` on pve (**Ben OK**, a host write), then `zpool status -t vm-pool` reads 100% trimmed.
  - Then Ben merges: `gh pr merge <n> -R Starktastic-Homelab/terraform --squash --match-head-commit <sha>`. **Ben OK.**
  - Live events:
    1. `apply.yml` takes the lock and applies the saved plan (3 VMs replaced). `apply-storage` prints
       `storage root not configured: nothing to apply`.
    2. `infrastructure-changed` is dispatched to ansible.
    3. `deploy.yml` runs `k3s.yml` and the ArgoCD bootstrap, and rewrites `KUBECONFIG_RAW`.
    4. ArgoCD reconciles every app.
  - Expected: apply green, deploy green, lock `FREE`. The 11-20 rebuild took about 44 min from merge to all Healthy
    (memory `worker-net-queues-rebuild`).
- [x] **Step 8: Merge 2.1d (`ci/manifest-by-name`) right away**, before any other terraform PR, as Part 2a Task 2.1d
  Step 6 describes. **Ben OK.**
  - Expected plan: k3s `No changes.` (the `k3s` entry gives the same name `builds[0]` gave); storage leg not planned.
  - Live event: a no-op apply, no dispatch.
- [x] **Step 9: Post-checks** (`rows-post.json`):
  - **GPU.** `gh workflow run i915-acceptance.yml -R Starktastic-Homelab/ansible -f mode=current-stack` (**Ben OK**,
    as after #243). Expected: green on both workers.
  - **Distinct identities.** On each k3s node, `cat /etc/machine-id`: three distinct values. The IQNs equal
    `iqn.2026-11.net.starktastic:<node>` as in Task 3.2.
  - **Cluster.**
    - every app Synced and Healthy;
    - the VolumeAttachment count equals the Step 1 baseline, and every VA is attached;
    - every PVC Bound;
    - on each worker, `qm config <worker> | grep -c 'wwn='` equals its VA count;
    - an ingress probe from the workstation returns 200 or 302 (memory `ingress-probe-from-workstation`).
  - **Storage NIC.**
    - `qm config <worker>` has `net2: virtio=...,bridge=vmbr2`, and the master has no `vmbr2` line;
    - `VM <worker> 'ip -br addr'` shows the third NIC UP with `10.99.2.<n>/24`;
    - `VM <worker1> 'ping -c 3 -W 2 10.99.2.<D1:worker_bridge_start + 1>'` (and the reverse) gives 0% loss;
    - `VM <worker> 'ip -d link show flannel.1'` shows `dev eth1`, so flannel stays off the storage NIC (lab B4).
  - **Argo.** `argocd-cm` still has `--enable-helm` (the rebuild reinstalled ArgoCD from the 3.2 role).
  - **D22 again.** Every node is new, so 3.2's reading is stale. Re-run the 3.2 Step 4 D22 reads on each node.
    Expected: PERSISTENT on each worker (a stop otherwise); a master is recorded, as in 3.2.
  - **GPU admission race.** List `Failed` pods with reason `UnexpectedAdmissionError` in `media`, and delete them by
    name only with **Ben OK** (memory `gpu-admission-race`).
  - **D5.** Run the guest capture parts and the yardstick analysis per the run sheet. Store them where the run sheet
    says, and link them from `evidence/3.3/facts.md`.
- [x] **Step 10: Lift the holds.** Apps merges resume, and Ben resumes Renovate if he suspended it. The next terraform
  `drift.yml` run must be clean before any other terraform PR merges. Record the end time.
- [ ] **Step 11: Docs-only PRs for the stale single-template text** (after Step 10 and the clean `drift.yml` run).
  - Re-grep `origin/main` for each ansible and terraform hit in `evidence/0.1/unowned-stale.md`; the line numbers may
    have moved. On 11-21 they were ansible `docs/i915-sriov.md:50` (packer `scripts/bootstrap.sh`, now
    `scripts/k3s.sh`) and terraform `README.md:33` plus `docs/diagrams/cluster-topology.svg:3,120` (the template
    "VM 900", now the k3s template VM 901, cloned by name). The `.github` rows are Task 5.6's, not this step's.
  - One branch per repo off `origin/main`, `docs/k3s-template-901`, touching only those files. Branch commits carry no
    skip pattern: ansible `docs(i915): the guest i915 parameter lives in packer scripts/k3s.sh`, terraform
    `docs: the k3s template is VM 901`.
  - Push and open each only when Ben asks. Merge each with **Ben OK**:
    - ansible: `docs/` is not in `deploy.yml` `paths-ignore`, so `[skip ci]` in the squash subject is required:
      `gh pr merge <n> -R Starktastic-Homelab/ansible --squash --match-head-commit <sha> --subject "docs(i915): the
      guest i915 parameter lives in packer scripts/k3s.sh [skip ci] (#<n>)"`. It may need `--admin` (memory
      `pr-merge-mechanics`).
    - terraform: the SVG is not in `apply.yml` `paths-ignore`, and the skip is read from the PR title, body and last
      commit, not from `--subject`. So the PR title is `docs: the k3s template is VM 901 [skip ci]`, and the squash
      subject is that title. `validate-and-plan.yml` and `readme-images.yml` run on the PR; expected plan k3s
      `No changes.`, storage leg not planned (2.1b is not merged yet).
  - Live event: none. Expected: `gh run list -R Starktastic-Homelab/<repo> --limit 5 --json workflowName,event,headSha`
    shows no push run on the ansible merge SHA, and terraform's `apply.yml` run on the merge logs `Skip pattern
    detected` and applies nothing.
- **Rollback.** There is no image rollback: a new packer PR plus another full rebuild. A storage NIC revert also rides a
  replacement, never an in-place update (wwn).

### Task 3.4: Data disks and the storage VM

**Files:**
- PR branch (worktree T): `feat/storage-vm-create` (2.1b, `storage/terraform.tfvars` and its test).
- Create (evidence): `evidence/3.4/{rows-pre.json,pre.txt,alloc.txt,rows-post.json,post.txt,facts.md}`.

**Interfaces:**
- Consumes: `<D1:placeholder_vmid>`, `<retained_volname>` (`vm-<D1:placeholder_vmid>-disk-0.raw`), `<regen_volname>`
  (`vm-<D1:placeholder_vmid>-disk-1.raw`), `<D2:retained_gib>`, `<D2:regen_gib>`, D2's error policy, main's manifest
  `storage` entry (template VMID 902 and its name, D16),
  `vmbr2`, and 2.1a's `apply-storage` with the clone check (`check_clone_source.main`).
- Produces:
  - volids `k3s-block:<D1:placeholder_vmid>/<retained_volname>` and `k3s-block:<D1:placeholder_vmid>/<regen_volname>`;
  - VM `<D1:storage_vmid>` `<D1:storage_name>`, tag `storage`, at `<D1:storage_lan_ip>` and `<D1:storage_bridge_ip>`;
  - the storage root state at key `storage/terraform.tfstate`;
  - the inventory group `storage` with one host.

- [ ] **Step 1: Pre-check** (`rows-pre.json`, `pve`):
  - `qm status <D1:storage_vmid>; qm status <D1:placeholder_vmid>`: both `does not exist`;
  - `pvesm list k3s-block --vmid <D1:placeholder_vmid>`: empty;
  - `qm config 902 | grep -E '^(name|template):'`: `template: 1`, and `name` equals
    `git -C $T show origin/main:packer-manifest.json | jq -er '[.builds[] | select(.name=="storage")] | last |
    .custom_data.vm_name'` (the clone check refuses any other name, D16);
  - `pvesm status --storage k3s-block`, and on `tn` `zfs get -Hp quota,available,used apps/k3s-block`. These are the
    before values against D2's capacity reading, and both sizes at or above D2's D44 floor (retained >= 220, regen
    >= 54 GiB);
  - `grep MemAvailable /proc/meminfo`: at least 5 GiB, as 1.1 required;
  - the tag audit: `pvesh get /cluster/resources --type vm --output-format json`. No VM carries the tag `storage`;
  - the terraform CI token's rights, names only (`pveum user token permissions <terraform user> <token id>`): it holds
    `VM.Allocate` and `VM.Clone` on `/vms` or `/`, and `VM.Clone` on 902, not only on `/pool/k3s-csi`. Since 0.1 dropped
    `pool_id`, the storage VM is created outside any pool (Part 0 final review). If the rights are pool-only, stop: the
    2.1b apply would fail closed and waste a merge event.

  Run it outside the backup windows, with the lock `FREE`.
- [ ] **Step 2: Allocate the two data disks.** **Ben OK** (two pve writes).
  ```sh
  pvesm alloc k3s-block <D1:placeholder_vmid> <retained_volname> <D2:retained_gib>G --format raw
  pvesm alloc k3s-block <D1:placeholder_vmid> <regen_volname> <D2:regen_gib>G --format raw
  ```
  - Expected: each prints `successfully created 'k3s-block:<D1:placeholder_vmid>/<volname>'`, and
    `pvesm list k3s-block --vmid <D1:placeholder_vmid>` lists both at the D2 sizes.
  - Record `zfs get used apps/k3s-block` after the allocation. A thin raw file should barely move it (UNVERIFIED for
    this NFS export; record it, do not assume it).
  - These names must equal 2.1b's `path_in_datastore` byte for byte.
  - Undo, only before Step 3: `pvesm free k3s-block:<D1:placeholder_vmid>/<volname>`. **Ben OK.**
- [ ] **Step 3: Push, open and merge 2.1b** as Part 2a Task 2.1b Step 6 describes.
  - The expected plan comment: k3s `No changes.`, storage `Plan: 2 to add, 0 to change, 0 to destroy`.
  - **Ben OK** to merge.
  - Live event: the k3s step applies nothing, then `apply-storage` runs under the maintenance lock. It prints
    `clone source 902 is a template named <manifest storage vm_name>` before `terraform apply` and creates the VM.
    There is no ansible dispatch.
  - This create is the first fresh clone with `virtio0` declared, which was traced only in source (lab report
    `:635`). A partial create (VM present, apply red) is a stop: do not re-run, and bring the apply log to Ben.
  - Evidence: plan excerpt and apply log tail.
- [ ] **Step 4: Post-check** (`rows-post.json`).
  - `pve`: `pvesh get /nodes/pve/qemu/<D1:storage_vmid>/config --output-format json`. Expected:
    - `name` `<D1:storage_name>`, `tags` `storage`, `onboot` `1`, `cpu` `host`;
    - `virtio0` on `local-zfs` at `4G` with `discard=on`;
    - `virtio1` `k3s-block:<D1:placeholder_vmid>/<retained_volname>` and `virtio2`
      `k3s-block:<D1:placeholder_vmid>/<regen_volname>`, each with `discard=on`, `iothread=1`, `cache=none` and the D2
      size, and no `werror`/`rerror` (D2: the QEMU default);
    - `net0` on `vmbr0`, `net1` on `vmbr2`;
    - no `startup` line yet (2.8 sets it in 3.5).

    `onboot` other than `1` is a stop: bpg's default is assumed on (scout-terraform section 3), and nothing else owns
    it.
  - `qm status <D1:storage_vmid>` reads `running`. The tag audit shows only `<D1:storage_vmid>` with `storage`.
  - `VM <D1:storage_vmid> '...'`:
    - `cloud-init status` reads `done`;
    - `lsblk -b -dno NAME,SIZE` shows `vda` 4 GiB, `vdb` and `vdc` at the D2 sizes;
    - `blkid -p /dev/vdb; echo rc=$?; blkid -p /dev/vdc; echo rc=$?` gives `rc=2` twice (blank);
    - `ip -br addr` shows `<D1:storage_lan_ip>/24` and `<D1:storage_bridge_ip>/24`;
    - `systemctl is-active rtslib-fb-targetctl` reads `active` (oneshot, `RemainAfterExit`; the journal says `No saved
      config file at /etc/rtslib-fb-target/saveconfig.json, ok, exiting`), and there are no VGs and no targets yet
      (read 2026-11-24 on VM 101; the earlier `inactive` or `failed` expectation came from lab B3 Step 2);
    - `systemctl is-active ssh` reads `active`.
  - `VM <worker1> 'ping -c 3 -W 2 <D1:storage_bridge_ip>'` gives 0% loss.
  - `pve`: `timeout 5 bash -c '</dev/tcp/<D1:storage_lan_ip>/22' && echo open` prints `open`.
  - The SSH login itself is first proven by 3.5's `storage.yml`, because only the workflow key is installed
    (`TF_VAR_SSH_PUB_KEY`).
  - The next scheduled `storage.yml` run outside a backup window prints `Skipping: storage_vm_pv_devices is the
    placeholder; nothing touched` (2.2). A scheduled run inside a window prints `Skipping: inside backup window
    <name>; the next hourly run retries` instead (D29); wait for the next one. Save that log line.
  - Write `facts.md`, including the storage VM's MAC addresses and the 2.1b apply's run URL.
- **Rollback (empty VM).** A terraform PR cannot destroy it while `prevent_destroy` is set. Leave it stopped (`qm
  shutdown <D1:storage_vmid>`, **Ben OK**) and bring it to Ben. The data disks belong to the placeholder VMID and
  survive any destroy (`storage/main.tf:93-95`).

### Task 3.5: Storage VM configuration

**Files:**
- PR branches (worktree A), each off `origin/main`:
  - `feat/storage-pv-devices`: Modify `group_vars/storage/storage_vm.yml` (add `storage_vm_pv_devices`) and
    `scripts/tests/test_storage_vm_role.py` (`test_production_storage_vars`: replace
    `assertNotIn('storage_vm_pv_devices', v)` with an equality on the two read paths).
    Commit `feat(storage): production storage VM PV paths`.
  - `feat/storage-vm-startup`, `feat/storage-regen-exclude` and `docs/storage-regen-exclude`, from Task 2.8.
- PR branch (`.github`, worktree `$L/worktrees/github-storage-vm`): `docs/storage-backup-inputs`, from Task 2.8
  (`CLAUDE.md:52`, the "Backup inputs" row).
- Create (evidence): `evidence/3.5/` with the by-path read, the bootstrap output, the run URLs, `qm config`, the
  excludes file and the restic listing.

**Interfaces:**
- Consumes:
  - runbook `docs/runbooks/storage-vm-bootstrap.md` (2.7 Step 9);
  - the role's per-VG `--devices` scoping (A `roles/storage_vm/files/homelab_storage/lvm.py:26-27`);
  - the asserts that refuse stock LVM activation (A `roles/storage_vm/tasks/assert.yml`, "Refuse stock LVM
    activation") and require two distinct PV paths ("Require one distinct PV path per VG");
  - `storage_ready.skip_reason` (2.2).
- Produces:
  - `storage_vm_pv_devices: {retained: <by-path of virtio1>, regen: <by-path of virtio2>}` (after the audit fold-in:
    `/dev/disk/by-id/virtio-retained` and `/dev/disk/by-id/virtio-regen`, Step 1);
  - VG `retained` tagged `hold_fence`, and VG `regen`;
  - a configured storage VM with `rtslib-fb-targetctl`, `nftables` and `storage-fencer` running, 0 targets, and the
    fencer blind (no token yet);
  - `startup: order=2,up=30`, and the regen exclude in `/etc/homelab-backup.d/excludes.txt`.

- [ ] **Step 0: The 2.7 runbooks and the empty inventory on apps `main`.**
  - Why the inventory: from Step 3 every `storage.yml` run, and the daily `storage-expiry.yml`, fetches
    `infrastructure/base-configs/files/retained-volumes.json` from apps `main` before the lock. The file arrives with
    the AP branch only in Task 3.6, so without it every run goes red at the fetch, the role never installs, and none of
    Step 3's or Step 4's Expected lines can pass. The role never treats a missing file as empty: a later path rename
    would then read as "every volume removed". So the file lands as `[]` here.
  - `git -C $D show origin/main:infrastructure/base-configs/files/retained-volumes.json`. If it prints `[]`, skip the
    inventory bullets below.
  - If it is missing: add the one file with the content `[]` and a newline, byte-identical to AP's
    (`git -C <AP> show <AP tip>:infrastructure/base-configs/files/retained-volumes.json`), to the runbook PR below,
    or, when the runbooks are already on `main`, as a one-file PR `docs/storage-empty-inventory` off `origin/main`
    (commit `feat(storage): empty retained inventory`). Live event: none. Nothing on `main` reads the file yet (the
    renderer and the dispatch step come with AP), so ArgoCD syncs with no change. AP's own add of the same bytes
    rebases cleanly in Task 3.6.
  - `git -C $D fetch origin && git -C $D show origin/main:docs/runbooks/storage-vm-bootstrap.md | head -3`. If it
    prints the runbook, and the inventory check above printed `[]`, go to Step 1.
  - If it is missing: the 2.7 commit (Part 2b Task 2.7 Step 13) sits on D with the ADR and plan edits. Build
    `docs/storage-vm-runbooks` off `origin/main` with only that commit: `git -C $D switch -c docs/storage-vm-runbooks
    origin/main && g -C $D cherry-pick <2.7 commit>`. Then `git -C $D diff --name-only origin/main` lists only
    `docs/runbooks/` files, plus `infrastructure/base-configs/files/retained-volumes.json` when the inventory rides
    along. Ben may pick D whole instead; record his choice in `evidence/3.5/facts.md`.
  - Push and open it when Ben asks (`git -C $D push -u origin docs/storage-vm-runbooks`, `gh pr create -R
    Starktastic-Homelab/apps`). Merge with `gh pr merge <n> -R Starktastic-Homelab/apps --squash --match-head-commit
    <sha>`. **Ben OK.** Live event: ArgoCD syncs with no change (docs, and an inventory nothing reads yet).
  - Expected: the `show` above now prints the runbook, and `storage-vm-rebuild.md`, `storage-vm-readonly-fs.md` and
    `pve-planned-reboot.md` exist on `origin/main` too; the inventory `show` prints `[]`.
- [ ] **Step 1: Read the production by-path names** (read-only; `VM <D1:storage_vmid> '...'` and `pve`). Audit
  fold-in (Tasks 2.1b, 2.3): the data disks carry serials `retained` and `regen`. Also run `ls -l /dev/disk/by-id/ |
  grep virtio-`; `storage_vm_pv_devices` gets `/dev/disk/by-id/virtio-retained` and `/dev/disk/by-id/virtio-regen`,
  and the by-path read below only confirms they resolve to the `virtio1` and `virtio2` devices.
  - `ls -l /dev/disk/by-path/ | grep -v -- "-part"`
  - `for p in /dev/disk/by-path/pci-*; do echo "$p $(readlink -f $p) $(blockdev --getsize64 $(readlink -f $p))"; done`
  - `pve`: `qm showcmd <D1:storage_vmid> --pretty | grep -E 'virtio-blk|drive-virtio'`, which maps each `virtioN` to its
    PCI `addr=`.
  - Expected: two by-path links, one per data disk. The PCI address of the `virtio1` device (volid
    `<retained_volname>`) maps to `vdb`, and that of `virtio2` (`<regen_volname>`) maps to `vdc`. The lab read
    `pci-0000:06:0b.0` and `pci-0000:06:0c.0` (A `roles/storage_vm/defaults/main.yml:16-20` before 2.3); production
    should match, but the values written are the ones read here.
  - Map through the `qm showcmd` slot, never through the size alone. If D2 gives both disks the same size, size proves
    nothing. A swap would put retained data on the backup-excluded disk.
  - Two readers (the executor and a second subagent) confirm the mapping independently. Any disagreement is a stop.
- [ ] **Step 2: VG bootstrap** per `storage-vm-bootstrap.md`, on the storage VM, outside the backup windows. **Ben
  OK** (writes to both data disks).
  - Precondition, read again: `blkid -p <path>; echo rc=$?` gives `rc=2` for both paths.
  - Commands, scoped like the role (`--devices`):
    ```sh
    R=<by-path of virtio1>; G=<by-path of virtio2>
    pvcreate --devices "$R" "$R" && vgcreate --devices "$R" retained "$R"
    pvcreate --devices "$G" "$G" && vgcreate --devices "$G" regen "$G"
    vgchange --devices "$R" --addtag hold_fence retained
    ```
  - This form is not rehearsed: the lab bootstrapped with `/dev/vdX` before F11, F12 and F24 (lab B3 Step 3). If the
    image's LVM config refuses `--devices`, stop and bring it to Ben. Do not edit `lvm.conf`.
  - Expected:
    - `vgs --devices "$R" --noheadings -o vg_name,vg_uuid,vg_tags retained` shows `hold_fence`;
    - `vgs --devices "$G" --noheadings -o vg_name,vg_uuid regen` shows the VG with no tags;
    - `pvs --devices "$R" --noheadings -o pv_name,vg_name` maps `$R` to `retained`, and the same for `$G` and `regen`;
    - `lvs` shows 0 LVs.

    Save the VG UUIDs. Task 3.7 compares against them.
  - Undo, only while both VGs hold no LV: `vgremove` and `pvremove` with the same `--devices`. **Ben OK.**
- [ ] **Step 3: The PV-paths PR** (`feat/storage-pv-devices`).
  - Write the two paths from Step 1. Run `$PY scripts/tests/test_storage_vm_role.py` and
    `$PY scripts/tests/test_storage_workflows.py` (2.2 setup). Expected: PASS.
  - Push and open it when Ben asks. The title has no `[skip ci]`.
  - **Pre-merge path check.** Compare `git -C $A diff --name-only origin/main...feat/storage-pv-devices` with the
    `paths-ignore` list of `git -C $A show origin/main:.github/workflows/deploy.yml`. 2.2's nine paths do not cover
    `scripts/tests/test_storage_vm_role.py`, and neither does origin/main `deploy.yml:12-25`. A push that changes any
    path outside `paths-ignore` starts a full `deploy.yml`: `k3s.yml` under the lock, k3s restarts, the ArgoCD helm
    step and a `KUBECONFIG_RAW` rewrite. It would also race `storage.yml` for the lock, and `storage.yml` tries only
    once.
    - **Every path is ignored:** merge plainly. `storage.yml` runs on `push` (`group_vars/storage/**`), and no deploy
      runs.
    - **Any path is not ignored (expected while 2.2 lacks the test path):** merge with `[skip ci]` in the squash
      subject, as 3.1 does (precedent ansible#314): `gh pr merge <n> -R Starktastic-Homelab/ansible --squash
      --match-head-commit <sha> --subject "feat(storage): production storage VM PV paths [skip ci] (#<n>)"`. Check
      that `gh run list -R Starktastic-Homelab/ansible --limit 5 --json workflowName,event,headSha` shows no run on
      the merge SHA. Then run `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main` (**Ben OK**).
  - Merge. **Ben OK** (it configures the storage VM).
  - Live event: the `storage.yml` run (push, or the manual dispatch), and no deploy. The run goes: `ready=true`, the
    k3s check (`preflight`, `k3s=true`), the dry run (no lock), one lock try, the reconcile under the lock, the
    first-root boot check, release. If a deploy run appears anyway, stop. Let
    it finish, check that the lock is `FREE`, then dispatch `storage.yml` by hand (**Ben OK**).
  - Expected:
    - run green; `Check that k3s answers before the lock` wrote `k3s=true`; dry run clean (no worker refusal: no
      `config.json` is installed yet); `acquired=true`; play recap `failed=0`; lock `FREE` afterwards;
    - `Run the boot check once on a root that never ran it` ran (no textfile yet, `rtslib-fb-targetctl` active) and
      `Fail if the first boot check failed` was skipped;
    - the log shows the inventory SHA it fetched and the warning
      `democratic-csi/storage-fencer-token is missing or not populated; the fencer stays blind` (playbook
      `storage.yml:65-67`);
    - this run is the first SSH login to the storage VM.
  - If this run fails before the role has installed once, the next daily `storage-expiry.yml` (10:05 UTC) passes its
    pre-lock checks, takes the lock and fails at `storage-reconcile expire-candidates`, which is not installed yet; the
    failed run keeps the lock (D31). So merge Step 3 well before 10:05 UTC and have a green `storage.yml` run by then.
    If the expiry did take the lock, read its log, then release it as in ansible `docs/maintenance-lock-release.md`
    (**Ben OK**).
- [ ] **Step 4: Read-only check and the idempotence run.**
  - `VM <D1:storage_vmid> '...'`:
    - `systemctl is-active rtslib-fb-targetctl nftables storage-fencer` reads `active` three times;
    - `targetcli ls /iscsi` lists no target;
    - `nft list set inet filter fenced` has no elements;
    - `vgs --devices "$R" --noheadings -o vg_tags retained` still has `hold_fence`;
    - `cat /var/lib/prometheus/node-exporter/storage-boot-check.prom` holds `storage_boot_check_ok 1` (2.4), written
      by Step 3's first-root boot check;
    - D22: `journalctl --header -n0 2>/dev/null | grep -m1 "File path"` reads `/var/log/journal/...` (PERSISTENT).
      VOLATILE is a stop: the boot check and Gate F2 read the previous boot's journal.
  - Then `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main` (**Ben OK**). Expected: `failed=0`,
    and the only changed tasks are the always-changed scratch tasks (lab B4 Step 4, run 4).
- [ ] **Step 5: Merge the startup PR** (`feat/storage-vm-startup`, 2.8). **Ben OK.**
  - Live event: `proxmox-guest-startup.yml` runs `qm set <D1:storage_vmid> --startup order=2,up=30`.
  - Expected: `qm config <D1:storage_vmid> | grep -E '^(startup|onboot):'` reads `onboot: 1` and
    `startup: order=2,up=30`. `qm config 100` still has `order=1,up=180`.
  - Read `qm config <D1:storage_vmid> | grep -E '^balloon:'` now, for 2.8's open balloon question.
- [ ] **Step 6: Merge the regen exclude PR, its docs PR, then the `.github` Backup inputs PR.** **Ben OK** for
  each.
  - Live events: `feat/storage-regen-exclude` triggers `proxmox-backup.yml` only, which rewrites
    `/etc/homelab-backup.d/excludes.txt` on pve. `docs/storage-regen-exclude` is merged with `[skip ci]` in the squash
    subject (never on a branch commit) and triggers nothing.
    It may need `--admin` (memory `pr-merge-mechanics`).
  - Expected: `grep -n '<D1:placeholder_vmid>' /etc/homelab-backup.d/excludes.txt` shows exactly the
    `<regen_volname>` path.
  - `grep -E '^\s*vmid' /etc/pve/jobs.cfg` still lists only 100 and 300: the storage VM is not in vzdump, because its
    root disk is disposable.
  - Then the `.github` PR `docs/storage-backup-inputs` (2.8), docs-only. Push and open it when Ben asks; merge with
    `gh pr merge <n> -R Starktastic-Homelab/.github --squash --match-head-commit <sha>`. **Ben OK.**
    - Expected: `readme-images.yml` green on the PR. It is `.github`'s only workflow and runs on `pull_request` only,
      so the merge triggers nothing and needs no `[skip ci]`.
    - After the merge, `git -C ~/Projects/homelab/.github show origin/main:CLAUDE.md | grep -n 'Backup inputs'` names
      terraform `storage/terraform.tfvars` and the regen image.
- [ ] **Step 7: Confirm the exclude on the next scheduled backup.** Do not start a manual backup. After the next 04:30
  run reports success:
  - `R ls latest --tag daily /srv/backup-src/k3s-block/images/<D1:placeholder_vmid>` (ansible
    `docs/backup-and-restore.md:162-168`).
  - Expected: `<retained_volname>` is listed, and `<regen_volname>` is not.
  - Write `facts.md`.

### Task 3.6: democratic-csi and the canary (apps)

**Files:**
- PR branches (worktree AP):
  - `feat/retained-storage-vm`, rebased in 0.1 and holding 2.4-2.6;
  - `feat/f1-canary` off `origin/main` after that merge:
    - Modify: `infrastructure/base-configs/files/retained-volumes.json` (one entry);
    - Create: `infrastructure/system/f1-canary/app.yaml` (namespace `democratic-csi`, `deployPhase: services`);
    - Create: `infrastructure/system/f1-canary/manifests/f1-canary.yaml` (writer ConfigMap and Deployment).
    Its own services-phase app (Ben 2026-11-25, pre-merge review): inside the controllers-phase democratic-csi app, a
    canary that is down would hold back every services app's sync under RollingSync.
- Create (evidence): `evidence/3.6/`, including `d37-guard.yaml` and `d37-ro-mount.md` (Step 7, D37).

**Interfaces:**
- Consumes:
  - the renderer `infrastructure/base-configs/templates/retained-volumes.yaml` (PV named `<id>`, PVC `<claim>`, both
    `Prune=false,Delete=false`);
  - the generic guard `guard.py` in ConfigMap `retained-startup-guard` (marker-only, D24; one guard, D48), which
    Task 2.9 renders in every inventory namespace, `democratic-csi` included once the canary's entry is in;
  - the democratic-csi node DaemonSet `democratic-csi-node` (`manifests/kustomization.yaml:20-23`), on workers only
    (`values.yaml:37-39`);
  - `storage.yml:62-98`, the token copy;
  - the lab writer `~/.cache/claude-homelab-live/storage-lab/b4/writer.yaml`;
  - 2.4's `storage-dispatch.yaml`.
- Produces:
  - the democratic-csi app, Secret `democratic-csi/storage-fencer-token`, the `storage-vm` ScrapeConfig and the alerts;
  - inventory entry `f1-canary`, `{"id": "f1-canary", "namespace": "democratic-csi", "claim": "f1-canary-iscsi",
    "size": "1Gi", "class": "regenerable", "origin": "new"}`. D18 says `regen`; the inventory class value is
    `regenerable` (`check-retained-inventory.py:20`), which selects VG `regen`;
  - LV `regen/f1-canary` and target `iqn.2026-11.net.starktastic.storage:f1-canary`;
  - Deployment `democratic-csi/f1-canary-writer`;
  - the D37 read-only mount proof `evidence/3.6/d37-ro-mount.md` (Step 7), which Task 4.0 Step 10 reads.

- [x] **Step 1: Pre-check.** Read-only:
  - Task 3.2's `argocd-cm` still reads `--enable-helm`;
  - `templates/globals.yaml` `storagePortal` on the branch is `<D1:storage_bridge_ip>:3260`, and `storage-vm.yaml`'s
    target is `<D1:storage_bridge_ip>:9100`. Neither file still holds `192.0.2.10`;
  - every app Synced and Healthy, and the lock `FREE`.
- [x] **Step 2: Merge the AP branch** (empty inventory). Push and open it when Ben asks: `git -C $AP push -u origin
  feat/retained-storage-vm`, then `gh pr create -R Starktastic-Homelab/apps --head feat/retained-storage-vm --title
  "feat(storage): democratic-csi beside Proxmox CSI, storage VM alerts and migration tooling (ADR 0017)"`.
  - Expected: `validate-and-diff.yml` green. The diff preview renders the democratic-csi app through kustomize with
    helm (`--enable-helm` in `.github/argocd-diff-preview-values.yaml`).
  - Merge. **Ben OK.**
  - Live events:
    - ArgoCD creates the `democratic-csi` app in the `controllers` phase and syncs `kube-prometheus-stack` (ScrapeConfig
      and rules);
    - the `globals.yaml` change makes `refresh.yaml` refresh every app;
    - `storage-dispatch.yaml` does not fire, because the inventory file is unchanged (`[]` on `main` since Task 3.5
      Step 0);
    - the Task 2.9 live-Secret annotation changes the pod-template checksum of authentik server and worker and of
      `falco-falcosidekick`, so those 3 Deployments roll once (the diff preview shows the 3 checksum changes). authentik serves forward-auth
      for every ingress, so admin and `*.internal` access drops briefly while its server rolls.
  - Expected:
    - app `democratic-csi` Synced and Healthy;
    - `authentik` and `falco` Synced and Healthy after that one roll;
    - `KUBE get csidriver org.democratic-csi.node-manual` exists;
    - the node DaemonSet is 2/2, on the two workers only;
    - the controller is on the master;
    - `KUBE -n democratic-csi get secret storage-fencer-token -o jsonpath='{.type}'` reads
      `kubernetes.io/service-account-token`. Never print its data.

    `StorageFencerBlind` is expected to fire from here until Step 4, because the token is not on the storage VM yet.
- [x] **Step 3: Check the render** (read-only):
  - `KUBE -n democratic-csi get ds democratic-csi-node -o jsonpath='{.spec.template.spec.terminationGracePeriodSeconds}
    {.spec.template.spec.initContainers[*].name} {.spec.template.spec.containers[*].name}'`. Expected
    `45 csi-proxy driver-registrar csi-driver`, with no `cleanup` (`node-shutdown-patch.yaml`).
  - `...containers[?(@.name=="csi-driver")].env[?(@.name=="MOUNT_DEFAULT_TIMEOUT")].value` reads `900000`
    (`values.yaml:51-52`).
  - The scrape, through the Prometheus API service proxy (memory `backup-review-live-access`):
    ```sh
    KUBE get --raw '/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/'\
'query?query=up%7Bjob%3D%22storage-vm%22%7D'
    ```
    returns value `1`. This is the first proof that a pod reaches the bridge address through the worker NIC and the
    storage VM's nftables (scout-apps, "Also unproven"). If the value is `0` or empty, stop.
- [x] **Step 4: Copy the fencer token.** `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main`
  (**Ben OK**: it writes the token to the storage VM).
  - Expected: `failed=0`. `Copy the storage-fencer token and CA` is changed twice, the `Restart storage-fencer` handler
    runs, and the warning from 3.5 is gone.
  - `VM <D1:storage_vmid> 'stat -c "%U %a" /etc/storage-fencer/token /etc/storage-fencer/ca.crt'` reads `root 600`
    twice. Never print or hash the contents in the evidence.
  - `journalctl -u storage-fencer -b --since -10min --no-pager | grep -iE "error|refus|fence" | tail` shows no API
    error after the restart. With `hold_fence` set, the fencer refuses any fence (ADR `:956-958`), and nothing is
    NotReady, so it logs nothing to fence.
  - Within 10 minutes, `ALERTS{alertname="StorageFencerBlind"}` (same proxy query, URL-encoded) returns nothing.
- [x] **Step 5: The canary PR** (`feat/f1-canary`, D18).
  - The writer manifest copies `storage-lab/b4/writer.yaml` with production names:
    - ConfigMap `f1-canary-writer`;
    - Deployment `f1-canary-writer` in `democratic-csi`: `replicas: 1`, `strategy: Recreate`,
      `nodeSelector: {node-role.kubernetes.io/worker: "true"}` (the master has no bridge NIC);
    - init container `guard` running `python3 -I -B /retained-startup/guard.py f1-canary /data`, with ConfigMap
      `retained-startup-guard` (`defaultMode: 292`, as 1.3a pins for guards) read-only at `/retained-startup`;
    - claim `f1-canary-iscsi` (apps CI's claim rule, 2026-11-25: `<id>-iscsi`);
    - the writer exits on SIGTERM (as PID 1 it would otherwise ignore it and every drain would be a SIGKILL);
    - image `python@sha256:8c9a3bf2d6dea60d60a2ae2a07c2b2fb1e7d8daed64b146b6792c74ae0d62ac4`, the digest apps already
      pins (`services/operations/kube-prometheus-stack/values.yaml:300` after 1.3a, a completion gate; the guards use
      `a11116e6`).
  - The namespace `democratic-csi` exists from Step 2 (`manifests/namespace.yaml`), so base-configs can render the PVC
    into it, and the `f1-canary` app reuses it.
  - Run locally (scout-apps "Test commands"):
    - `python3 -m unittest discover -s scripts/storage/tests -v`;
    - `python3 scripts/check-retained-inventory.py --base origin/main`;
    - `python3 scripts/check-retained-guards.py` (Task 2.9; it must see the canary's plain Deployment as the claim's one
      guarded consumer);
    - kubeconform on the manifest.

    Expected: PASS.
  - Merge. **Ben OK.**
  - Live events:
    1. base-configs renders PV `f1-canary`, PVC `democratic-csi/f1-canary-iscsi` and ConfigMap
       `democratic-csi/retained-startup-guard`;
    2. ArgoCD creates the `f1-canary` app and the writer;
    3. `storage-dispatch.yaml` sends `storage-changed`, and `storage.yml` creates the LV, the filesystem, the marker
       and the target.

    The writer pod waits in ContainerCreating until the target exists, retrying the login. If the dispatch is not
    wired (1.1: `ORG_DISPATCH_TOKEN` not visible to apps), dispatch `storage.yml` by hand right after the merge
    (**Ben OK**). Otherwise the hourly run could leave the pod past democratic-csi's 30-minute NodeStage retry (lab F1,
    D10).
- [x] **Step 6: Check the canary** (read-only):
  - `gh run list -R Starktastic-Homelab/ansible --workflow storage.yml --limit 3 --json event,createdAt,conclusion`.
    The run right after the merge has event `repository_dispatch` (or `workflow_dispatch` if Step 5 needed the
    fallback) and conclusion `success`.
  - `VM <D1:storage_vmid> '...'`:
    - `lvs --devices "$G" --noheadings -o lv_name,lv_uuid,lv_size regen` shows `f1-canary` at `1.00g`;
    - `vgs --devices "$G" --noheadings -o vg_tags regen` has `ledger:f1-canary:created`;
    - `targetcli ls /iscsi` has the canary target with ACLs for both worker IQNs;
    - `blkid -o value -s UUID /dev/regen/f1-canary` gives the filesystem UUID;
    - `dumpe2fs -h /dev/regen/f1-canary 2>/dev/null | grep -E "^Filesystem features|^Errors behavior"` shows `mmp`
      and `Remount read-only`.
  - `KUBE -n democratic-csi get pvc f1-canary-iscsi` reads Bound, and the PV is RWOP and Retain.
  - `KUBE -n democratic-csi logs deploy/f1-canary-writer -c guard` reads `Retained identity accepted.`, and
    `-c writer --tail 3` shows `start host=<worker> integrity=ok count=0 max=0 contiguous=True` and then `ack` lines.
  - `VM <that worker> 'iscsiadm -m session'` shows one session from its bridge address to
    `<D1:storage_bridge_ip>:3260`.
  - Save the LV UUID, the filesystem UUID and the last `ack`. Task 3.7 compares against them.
- [x] **Step 7: D37, prove the reverse gate's read-only mount once on the canary** `(not rehearsed)`. Run it inside
  Task 3.7, after its Step 7 compare and before its Step 8 starts the writer: the claim is RWOP on one handle, so the
  writer must be at 0. Outside every backup window, lock `FREE`. Evidence: `evidence/3.6/d37-ro-mount.md`, which Task
  4.0 Step 10 reads for `gate_ro_mount_proven`.
  - Why by hand: the canary is `origin: new` with no old image, so `migrate_volume.py render --direction reverse`
    cannot run on it. Write `evidence/3.6/d37-guard.yaml` with the shape of 2.5's Filesystem half (Part 2b, "Reverse
    source gate"), all labelled `homelab.starktastic.net/migration=f1-canary`, none in an Argo app:
    - PV `migrate-guard-f1-canary`: driver `org.democratic-csi.node-manual`, handle `f1-canary`, `volumeAttributes`
      copied from `KUBE get pv f1-canary -o jsonpath='{.spec.csi.volumeAttributes}'`, `volumeMode: Filesystem`,
      `fsType: ext4`, `mountOptions: [ro, noload]`, `1Gi`, RWOP, `Retain`, a `claimRef` to the PVC below;
    - PVC `democratic-csi/migrate-guard-f1-canary` with `volumeName` set and `storageClassName: ""`;
    - Job `migrate-guard-f1-canary` in `democratic-csi`, worker `nodeSelector`, pod volume `readOnly: true` at
      `/data`: a first init container (the pinned python digest of Step 5) that exits 1 unless `/proc/self/mounts`
      shows `/data` with `ro`; then the writer's `guard` init container copied whole, with a second pod volume for
      ConfigMap `retained-startup-guard` (`defaultMode: 292`) read-only at `/retained-startup`, the ConfigMap Step 5
      put in `democratic-csi`; then a main container that
      prints `gate-guard-ok f1-canary` and sleeps 300 s, so the staging mount can be read. The sleep is the only
      departure from 2.5's shape.
  - Before (read-only): `VM <D1:storage_vmid> 'sha256sum /dev/regen/f1-canary; dumpe2fs -h /dev/regen/f1-canary
    2>/dev/null | grep -E "^(Last mount time|Last write time|Mount count)"'`. No initiator has the LV now, so
    nothing else writes it.
  - Apply (**Ben OK**): `VM <master> 'echo <base64 of d37-guard.yaml> | base64 -d > /run/d37-guard.yaml && k3s
    kubectl apply -f /run/d37-guard.yaml'`, the base64 form Task 4.0 uses (no D23 tool host exists yet).
  - While the main container sleeps, on its node: `VM <worker> 'findmnt -rn -o SOURCE,TARGET,FSTYPE,OPTIONS -t
    ext4'` and `VM <worker> 'journalctl -k --since -10min --no-pager | grep -i ext4'`. Expected: the staging
    (`globalmount`) and pod mounts of the canary device both read `ro`, and the options or the kernel line show no
    journal replay (`noload` or `norecovery`; which spelling the kernel prints is UNVERIFIED, record it). An `rw` on
    either mount is a fail, whatever the in-pod check said: it sees only the bind mount (Part 2b).
  - Expected Job result: `KUBE -n democratic-csi logs job/migrate-guard-f1-canary --all-containers` shows the `ro`
    check passed, `Retained identity accepted.` and `gate-guard-ok f1-canary`.
  - Tear down (**Ben OK**; the PV is `Retain`, so no data is touched): `KUBE -n democratic-csi delete job
    migrate-guard-f1-canary`, then the PVC, then `KUBE delete pv migrate-guard-f1-canary`, then `VM <master> 'rm -f
    /run/d37-guard.yaml'`. Expected: no VolumeAttachment names `migrate-guard-f1-canary`, and `VM <worker> 'iscsiadm
    -m session'` lists no canary session.
  - After: the same `sha256sum` and `dumpe2fs` reads equal the before values. A changed hash means the mount wrote.
  - Write `result: proven` with these excerpts, or `result: not proven: <reason>`, to `d37-ro-mount.md`. Not proven
    goes to Ben and blocks the first cutover (4.0 Step 10, D37). It does not fail F1, and no retry edits retained
    data.

### Task 3.7: Gate F1 (Check 3)

A deliberate rebuild of the storage VM. The 3.4 create was the first fresh clone with `virtio0` declared, and this
task rebuilds from such a clone (ADR `:962-963`; lab report `:581-592`). Ben OKs each merge.

**Files:**
- PR branches (worktree T), each off `origin/main`:
  - `feat/storage-vm-rebuild`:
    - Modify `storage/main.tf:100` to `prevent_destroy = false`;
    - Modify `storage/terraform.tfvars` to `generation = "2"`;
    - Modify `scripts/tests/test-storage-root.py` so `test_production_tfvars` expects `'2'`.

    Commit `feat(storage): rebuild the storage VM once (ADR 0017 gate F1)`.
  - `fix/storage-vm-prevent-destroy`: Modify `storage/main.tf:100` back to `prevent_destroy = true`. Commit
    `fix(storage): restore prevent_destroy after gate F1`.
- PR branches (worktree AP), off `origin/main`: `chore/f1-canary-drain` and `chore/f1-canary-start`, each modifying
  `replicas` in `infrastructure/system/f1-canary/manifests/f1-canary.yaml`.
- Create (evidence): `evidence/3.7/` (`base.txt`, `after.txt`, plan excerpts, run URLs, `facts.md`).

**Interfaces:**
- Consumes:
  - runbook `storage-vm-rebuild.md` ("Why drain first", "Writer drain", "Rebuild PR pair", "After the rebuild");
  - 2.1a's clone check and `--chdir`;
  - `terraform_data.generation` with `replace_triggered_by` (T `storage/main.tf:1-3,103`);
  - the 3.5 VG UUIDs and the 3.6 canary identities.
- Produces: a rebuilt `<D1:storage_vmid>` with the same data volids, VGs, tags, IQNs and filesystem, and
  `generation = "2"` on `main` from now on.

- [x] **Step 1: Baseline** (read-only, `evidence/3.7/base.txt`). Use the lab B7 recipe (`storage-lab/b7/base-971.txt`):
  - `VM <D1:storage_vmid> '...'`:
    - `lvs` with `-o vg_name,lv_name,lv_uuid,lv_size`;
    - `vgs` with `-o vg_name,vg_uuid,vg_tags` (both with `--devices`);
    - `find /sys/kernel/config/target/iscsi -maxdepth 4 -path "*/acls/*" -type d` (target and ACL IQNs);
    - `blkid -o value -s UUID /dev/regen/f1-canary`;
    - `systemctl show storage-fencer -p NRestarts -p ActiveEnterTimestamp`.
  - `pvesh get /nodes/pve/qemu/<D1:storage_vmid>/config --output-format json`, keeping `virtio0-2`, `net0-1`, `onboot`
    and `startup`.
  - The canary's last `ack` number.
  - The tfvars test pins generation `"1"`, so a plain bump would leave every later terraform PR red. Expected for the
    gate: `prevent_destroy` blocks a generation-only plan. That is `test_generation_change_refused`
    (`test-storage-root.py:132-135`), which passes on `main` today.
- [x] **Step 2: Drain the canary writer** (runbook "Writer drain": F9 says a rebuild outlasts iSCSI recovery).
  - Merge `chore/f1-canary-drain` (`replicas: 0`). **Ben OK.** Live event: ArgoCD scales the writer to 0.
  - Expected: no pod. `KUBE get volumeattachments -o
    jsonpath='{range .items[*]}{.spec.source.persistentVolumeName} {.status.attached}{"\n"}{end}' | grep f1-canary` is
    empty. `VM <worker> 'iscsiadm -m session'` lists no canary session.
  - Variant (Ben's call): leave the writer running to watch F9 again. Then expect read-only ext4 and a pod restart,
    recovered by the readonly-fs runbook "Restage" (F13), and the filesystem error flag stays set (D11).
- [x] **Step 3: Pre-merge gate.**
  - No `build.yml` run in packer is queued or in progress.
  - `qm config 902` `name` equals `custom_data.vm_name` of main's manifest `storage` entry: the rebuild clones the
    saved plan's VMID and name, and the clone check refuses a mismatch (D16). No packer push may land while the
    rebuild PR is open (ADR `:72-74`).
  - Lock `FREE`.
  - Outside the backup windows, and well clear of the next `storage.yml` hourly run at `:05` UTC.
- [x] **Step 4: The rebuild PR.** Push and open `feat/storage-vm-rebuild` when Ben asks. Title `feat: rebuild the
  storage VM once (ADR 0017 gate F1)`; the body names no skip pattern.
  - Expected CI:
    - `rebuild-policy-tests` fails exactly `test_generation_change_refused` and
      `test_destroy_keeps_unreferenced_disks`, both of which assert `prevent_destroy` (`test-storage-root.py:132-135,
      177-184`). Any other failure is a stop.
    - Plan from the head run's log: k3s `No changes.`; storage `Plan: 1 to add, 1 to change, 1 to destroy` (the VM
      replaced, `terraform_data.generation` updated). The disk blocks before and after are identical, with
      `virtio1`/`virtio2` the 3.4 volids, `delete_unreferenced_disks_on_destroy = false` and
      `purge_on_destroy = false`.
  - Re-run the plan right before the merge.
  - Merge with the red required check: `gh pr merge <n> -R Starktastic-Homelab/terraform --squash --admin
    --match-head-commit <sha>`. **Ben OK** (it destroys and recreates the storage VM).
  - Live event: `apply.yml`. The k3s step applies nothing. `apply-storage` takes the lock, then
    the clone check prints `clone source 902 is a template named <manifest storage vm_name>`, then it applies. There
    is no ansible dispatch.
  - Expected: apply green with `1 added, 1 changed, 1 destroyed`. The lab took 55 s (destroy 3 s, create 50 s).
    `StorageVMDown` may fire for the gap (`for: 5m`), and `StorageBootCheckFailed` (absent) until Step 6.
- [x] **Step 5: The restore PR, right away.** Until it merges the VM has no destroy guard, so nothing else merges in
  terraform in between.
  - Push and open `fix/storage-vm-prevent-destroy` when Ben asks. Title
    `fix: restore prevent_destroy on the storage VM`.
  - Expected: CI fully green. The plan shows k3s `No changes.` and storage `No changes.` (a lifecycle edit plans
    nothing).
  - Merge. **Ben OK.** Live event: a no-op apply.
- [x] **Step 6: Reconfigure.** Run `gh workflow run storage.yml -R Starktastic-Homelab/ansible --ref main` (**Ben
  OK**). If the hourly run gets there first, that run is the evidence.
  - Expected: `failed=0`. The role installs again on the fresh root, copies the token, and re-exports the canary
    target from the ledger. No create runs: the LV exists and the ledger says `created`.
  - Then `gh workflow run proxmox-guest-startup.yml -R Starktastic-Homelab/ansible --ref main` (**Ben OK**). The
    recreate dropped `startup` (lab B7: "onboot 1/cpuunits null"; `ignore_changes` covers `startup`). Expected:
    `changed=1` for `<D1:storage_vmid>`.
  - No `known_hosts` refresh is needed, because ansible runs with `StrictHostKeyChecking=no` (A
    `group_vars/all/vars.yml:3`).
- [x] **Step 7: Compare** (read-only, `after.txt`, same rows as Step 1). Expected, against `base.txt`:
  - `virtio1` and `virtio2` have the same volids and sizes. `virtio0` is new, the MACs are new, `onboot: 1`, and
    `startup: order=2,up=30`;
  - the LV UUIDs, the VG UUIDs and the VG tags are identical (`hold_fence` on `retained`, the canary ledger on
    `regen`). These match the 3.5 bootstrap UUIDs;
  - the target IQN and both ACL IQNs are identical;
  - the canary filesystem UUID is identical, so no `mkfs` ran;
  - `rtslib-fb-targetctl`, `nftables` and `storage-fencer` are active. The fencer shows a fresh `ActiveEnterTimestamp`,
    `NRestarts=0`, an empty `fenced` set, and `StorageFencerBlind` quiet;
  - `storage_boot_check_ok 1`.

  Any difference in a UUID, tag or IQN fails F1. Stop: Part 4 does not start, and the finding goes to Ben.
- [x] **Step 7b: Run Task 3.6 Step 7 (D37) now**, while the writer is still drained. Its outcome does not change the
  F1 verdict. If Step 2's variant kept the writer running, run it instead in Task 3.8 Step 7, after its writer-off
  sub-step and before the removal PR.
- [x] **Step 8: Start the writer.** Merge `chore/f1-canary-start` (`replicas: 1`). **Ben OK.**
  - Expected: the pod runs on a worker. Its writer log `start ... integrity=ok count=<n> max=<n> contiguous=True` has
    `n` at or above Step 1's last `ack`, and then `ack` lines follow.
  - A drained, cleanly unmounted filesystem mounts with no MMP error flag. If the Step 2 variant was used, follow the
    readonly-fs runbook first.
  - Write `facts.md` with F1 PASS or FAIL against each expectation (outline 3.7).

### Task 3.8: Gate F2 (Check 1)

One planned pve host reboot with the storage VM up, on the final code (ADR `:964-967`), run from
`docs/runbooks/pve-planned-reboot.md` (2.7 Step 11). `hold_fence` is set, so this does not test the cold-boot fence
rule F18 (ADR accepted-untested list). The canary writer runs through the reboot; that is the point.

What F2 does not cover:
- **Late NFS at cold boot (D9).** F2 is a warm reboot with TrueNAS up, so `k3s-block` is normally active before
  `startall`. It shows only a boot with NFS on time. Step 4's late-NFS branch records a failure if it happens; it does
  not prove the D9 recovery. D9 is decided: alert only, no auto-retry (Ben, 2026-11-22).
- **Scale.** The only volume is the canary on `regen`. The boot with about 33 real volumes staged, and the `retained`
  VG's LUN-0 restore and boot check with real LVs, are proven later by Task 5.10 (a planned pve host reboot with every
  retained volume staged), not here. An unclean host reset stays not proven (Part 5 Accepted untested).

**Rulings** (Ben, 2026-11-25): re-gate at T-2 and accept the residual late-cron risk (no cron pausing); packer
`c14e49f` and ansible `9695e1c` land after F2 and Step 8; a forced stop of any guest, or a retained volume still
staged at power-off, is an F2 FAIL; slot "now" (start 16:12 IST, the 15 IST hour excluded).

**Files:**
- Create (evidence): `evidence/3.8/` with `pre.txt` (gate, T-30), `gh-gate.txt`, `regate.txt` (T-2), `reboot.txt`,
  `post1.txt`-`post3.txt`, `alerts-post.txt`, `health-post.txt`, `settle.log`, the first run's log
  (`storage-run-45641155917.log`) and `facts.md`. Pre-flight review: `evidence/3.8-preflight.md`.
- Later: PR branch (worktree AP) `chore/f1-canary-stop` off `origin/main` (`replicas: 0` in `f1-canary.yaml`), then
  `chore/f1-canary-remove` off `origin/main` after it merges:
  - Modify `retained-volumes.json` (remove the entry);
  - Delete `infrastructure/system/f1-canary/` (the app and its manifest).

**Interfaces:**
- Consumes:
  - the runbook's sections "Gate", "The runner goes down", "Shutdown order", "Boot and start order", "After boot" and
    "Runner credentials after a reboot";
  - the slot rule in Step 1 (lab `memsize/b10clock.sh` is lab-only: it allows the 10 UTC hour and starts at :02);
  - `~/.cache/claude-homelab-live/storage-migration/f2rows.py`, the production read-only rows generator with modes
    `gate`, `regate` and `post`. It writes `evidence/3.8/rows-<mode>.json`, run as
    `/opt/azure-cli/bin/python3 -I ~/.cache/claude-homelab-live/bin/live.py <rows.json>`. It reuses the kube prefix
    from `evidence/3.3/rows-post.json` and the identity rows from `evidence/3.7/rows-base.json`, and hard-codes the
    VMIDs (100, 101, 200-202, 300), workers 201/202, the canary and the output path; Task 5.10 adapts those. The gh
    reads, the reboot, the alert read and the settle loop were separate rows. Its automerge section is a stub. The
    lab `memsize/b10gate.sh` and `memsize/b10post.sh` are lab-only (lab VMIDs, lab lock owner, host writes);
  - `startup` for VM 100 (`order=1,up=180`) and `<D1:storage_vmid>` (`order=2,up=30`);
  - memory notes `proxmox-worker-autostart-nfs-race`, `gpu-admission-race` and `pve-memtest-plan`.
- Produces: the F2 verdict, and the first production expiry (`f1-canary`), which is the gate for Task 4.0.

- [x] **Step 1: Pick the slot** (Ben). All of these hold:
  - outside every backup window;
  - the start falls in hh:12-hh:30 Asia/Jerusalem, never 01:00-06:59, never in the 03, 09, 15 or 21 hours, not in the
    hour that holds 10:05 UTC (the daily `storage-expiry.yml`: 12 IST in winter, 13 in summer; compute it in UTC), and
    not Sunday 00:xx. Then the reboot spans no `:00` (the hourly health fails until `usbbk-import` is done) and no
    TrueNAS `:30` run;
  - a weekday, starting between 07:12 and 20:30 IST: apps Renovate auto-merges weekdays after 22:00 or before 06:00
    and all weekend, and its required checks need no self-hosted runner;
  - it also starts after that hour's `storage.yml` run at `:05` UTC has finished. A run killed by the reboot keeps
    the lock (2.2, D31).

  The outage is about 20 minutes (2026-11-25: 17 min from T0 to every app Healthy). Tell the household.
  2026-11-25: Wednesday 16:12 IST, after `storage.yml` 45630292946 finished at 14:09:54Z.
- [x] **Step 2: Gate** (read-only, T-30 min, `f2rows.py gate` into `pre.txt`, gh reads into `gh-gate.txt`). Abort if
  any fails.
  - pve: pstore empty; `uname -r` is the newest installed `proxmox-kernel` (an upgrade since boot would confound F2);
    `pgrep -af '[r]estic|[v]zdump|[z]fs (send|recv)|[z]pool (scrub|trim)'` empty (`-f`: a `zfs recv` is named `zfs`);
    `zpool status` shows no scrub or trim running; the last TrueNAS replication green.
  - TrueNAS: no scrub, resilver or SMART test on VM 100's pools (Ben, UI; f2rows has no TrueNAS read). A forced stop
    of VM 100 is an F2 FAIL (Rulings). 2026-11-25: not read.
  - Timers: `systemctl list-timers --all --no-pager` (the `homelab-backup*` glob misses `homelab-dispatch@*` and
    `zfs-trim-weekly`). The health timer is exempt by name. Every other NEXT is after T0+15 min, except the
    `homelab-dispatch@storage.yml` timer, whose LAST run must have finished.
  - `gh run list` in all five repos: nothing in progress or queued, except the stale apps "Validate manifests" run
    from 2026-08-06 (a zombie; see Observed). `gh pr list --json number,autoMergeRequest`: no PR with auto-merge.
  - VM300: lock `FREE` (`test ! -e /var/lib/homelab-maintenance/operation.json`), `pgrep -c -x Runner.Worker` 0.
  - Hold all merges in every repo until Step 7 (through Task 3.10).
  - `qm config 100` has `order=1,up=180`. `qm config <D1:storage_vmid>` has `onboot: 1` and `startup: order=2,up=30`.
    Every k3s VM and VM300 has `onboot: 1` and no `startup`. No guest has `down=`. `ha-manager status` is empty.
  - VM 100's last shutdown was clean, with pools exported (the previous gate's Step 4 records it). This is the 11-15
    runbook's pre-check: no `down=` is set, so a stop longer than 180 s would be forced.
  - Baseline (`pre.txt`):
    - every app Healthy;
    - VAs per attacher and node (`{.spec.attacher} {.spec.nodeName}` through `uniq -c`), and per worker
      `qm config <vmid> | grep -cE '^scsi[0-9]+:.*wwn='`;
    - the canary's node and last `ack`; `democratic-csi-node` `priorityClassName` is `system-node-critical`;
    - on the storage VM, `systemctl show rtslib-fb-targetctl storage-fencer -p ActiveEnterTimestamp`, `uptime -s`,
      and the identity rows: `lvs -o lv_name,lv_uuid,lv_tags` and `vgs -o vg_name,vg_uuid,vg_tags` on both VGs
      (`retained` has `hold_fence` only), target ACLs, the canary FS UUID, `nft list set inet filter fenced`, the
      boot-check textfile, `systemctl --failed` (`openipmi` failed on image 902 is known);
    - the storage VM's `qm config` (template, `virtio0` volid, MACs);
    - the ansible `main` SHA, the SHA the last `storage.yml` run logged ("final code"), and that run's `storage-01`
      recap line (Step 5's "changes nothing" baseline).
  - On VM300, `findmnt -t tmpfs -o TARGET` through `VM`. This records what a reboot will wipe (F19). The lab's
    `<lab>/ssh` and `<lab>/creds` are gone since B11, so no homelab credential is expected there; any one found is
    listed for Ben.
  - **Re-gate at T-2** (`f2rows.py regate` into `regate.txt`, plus the gh reads). Abort on any hit: a run in progress
    or queued (the zombie aside), an auto-merge PR, lock held, `Runner.Worker` above 0, the newest `storage.yml` run
    not completed after hh:05 UTC, or the clock outside Step 1. Re-read the canary's last `ack`. The last 1-2 min keep
    a residual late-cron risk (accepted, Rulings).
  - Expected (2026-11-25): kernel 7.0.14-29 newest installed, pstore 0; nothing busy; at T-2 next health 17:00,
    dispatch `storage.yml` 17:05 (at T-30: 16:00, 16:05), expiry tomorrow 12:05 IST; startup as above, HA none;
    lock `FREE`, Worker 0, Listener 1, only system tmpfs; 81 apps Synced/Healthy; Proxmox CSI VA 17+16 = wwn 17/16,
    one democratic-csi VA on kube-worker-02; canary on kube-worker-02, `ack` 43345 at T-2; identity as 3.7 after.
- [x] **Step 3: Reboot.** On pve, `systemd-run --on-active=5 --unit=f2-host-reboot systemctl reboot` through the
  helper, never a plain reboot through `live.py`. **Ben OK.**
  - It is a plain reboot, so pve's own `stopall` order is what gets tested.
  - It has none of the 11-15 runbook's USB export or unplug, KFENCE, stress or rasdaemon steps.
  - Record the old `boot_id` and poll for a new one (`reboot.txt`). Note T0. Ben watches POST on JetKVM.
  - VM300 goes down too: no workflow runs until it is back. The helper runs from the workstation.
  - 2026-11-25: scheduled 14:12:09Z, T0 14:12:14Z, pve up 16:16:24 IST (about 4 min).
- [x] **Step 4: Boot and order** (read-only, `f2rows.py post` into `post1.txt`; no host writes, no `systemctl start`).
  - `pvesh get /nodes/pve/tasks --limit 300 --output-format json`, filtered to `qmshutdown`, `qmstop`, `qmstart`,
    `startall` and `stopall` from boot minus 1 h, sorted by starttime: each guest's newest `qmshutdown` before the
    boot and first `qmstart` after it;
  - for the `qmshutdown` rows of 200-202, 300, 101 and 100: status `OK`, duration under 150 s, and
    `pvesh get /nodes/pve/tasks/<upid>/log` with no `terminat|still running|SIGTERM|SIGKILL|timeout|failed`. No guest
    has `down=`, so a forced stop happens inside the same `qmshutdown` task: any forced stop is an F2 FAIL (Rulings);
  - `journalctl -b -u pve-guests --no-pager | grep -ci 'not online'`;
  - `journalctl -b -1 -u pve-guests --no-pager -o short-iso | grep -iE 'stop|shutdown' | tail -15`;
  - pve `journalctl -b -1 -p err --no-pager` (an oops during shutdown); 2026-11-25: not read, pstore only;
  - VM 100's own log of this shutdown (pools exported), recorded in `post` as the next gate's "clean previous
    shutdown" evidence (Step 2). 2026-11-25: not read; only its `qmshutdown` status and duration.

  Expected:
  - **shutdown:** the unordered guests' `qmshutdown` (200-202, 300) end before the storage VM's starts, and VM 100
    stops last. 2026-11-25: `stopall` 45 s; 200-202 38 s, 300 3 s, 101 2 s, 100 3 s; all `OK`, no forced markers;
  - **start:** VM 100 first; `<D1:storage_vmid>` about 180 s later; the unordered guests (master, workers, VM300)
    about 30 s after that. 2026-11-25: +181 s, +31 s. The `qmstart` `WARNINGS` on 201/202 ("iothread is only valid
    with virtio disk or virtio-scsi-single controller", one per wwn slot) are cosmetic and expected;
  - `not online` count `0`;
  - pve: `systemctl --failed` empty, `usbbk-import` finished (16:21:01), pools healthy, pstore empty.

  Then read the next scheduled `homelab-backup@health` run after `usbbk-import` (`health-post.txt`). Expected: green
  (2026-11-25: 17:00 IST success, no manual start). A manual `systemctl start` needs **Ben OK**.

  **If the storage VM or a worker was refused as `not online` (late NFS):** F2 has failed its "no manual step"
  criterion.
  - Record it and stop. Bring it to Ben before Part 4 (D9: alert only, so the recovery below is by hand).
  - Recovery, with **Ben OK**: `qm start <D1:storage_vmid>` once `pvesm status --storage k3s-block` is active, then
    `qm start` for the stopped workers (memory `proxmox-worker-autostart-nfs-race`). If only 101 was refused and the
    workers run, wait out the D10 30 min NodeStage bound before deleting any pod.

  **If the storage VM does not boot, `rtslib-fb-targetctl` fails, or `storage_boot_check_ok` is 0:** stop and delete
  no pods. Follow `storage-vm-restore.md` ("Boot check failed") or `storage-vm-readonly-fs.md` ("Restage"); Ben
  decides.
- [x] **Step 5: Targets with no manual step** (read-only, `post1.txt`).
  - `VM <D1:storage_vmid> '...'`:
    - `uptime -s`;
    - `systemctl show rtslib-fb-targetctl storage-fencer -p ActiveState -p ActiveEnterTimestamp`;
    - the identity rows from Step 2 (targets and ACLs read as 3.7 did);
    - `cat /var/lib/prometheus/node-exporter/storage-boot-check.prom`;
    - `journalctl -b -u rtslib-fb-targetctl --no-pager -o short-iso | head -12`;
    - `vgs ... -o vg_tags retained` and `nft list set inet filter fenced`.
  - The first `storage.yml` run whose job `startedAt` (`gh run view <id> --json jobs`) is after the storage VM's
    `uptime -s`, not the first by `createdAt` (a run queued during the outage predates the boot). The backstop is
    `Persistent=false`: if none comes, wait up to 60 min for the next `:05`, or a one-off dispatch with **Ben OK**.
  - Expected:
    - `rtslib-fb-targetctl` is active within seconds of boot (lab and 2026-11-25: 5 s), and its
      `ActiveEnterTimestamp` is earlier than that run's job `startedAt`;
    - `storage_boot_check_ok 1` with a timestamp after boot;
    - identity equal to `pre.txt` (LV and VG UUIDs, tags, ACLs, FS UUID, volids, MACs);
    - `retained` still has only `hold_fence` and no `fenced:` tag, and the `fenced` set is empty. The hold makes the
      fencer refuse; F18's NotReady-from-watch-start rule also applies. A fencer "No route to host" to the API until
      k3s is up is expected;
    - that run is green with "Try the maintenance lock once" acquired, and "Reconcile under the lock" and "Release the
      lock after success" `success`, not skipped, and no `##[warning]` annotation (lock held, k3s down, window; grepping
      `::warning::` matches the echoed step scripts). A skip on a lock
      from before T0 is a STOP; a red step before the lock is a CI retry, not an F2 FAIL. A k3s-down, window or
      post-T0 lock skip is not a verdict; read the next run (same `startedAt` rule). "Changes nothing" means identity
      unchanged and a `storage-01` recap equal to Step 2's baseline recap. 2026-11-25: run 45641155917 (dispatch
      15:05:10Z, job start 15:05:14Z), `storage-01 ok=58 changed=7 failed=0`, as 3.7.
- [x] **Step 6: Workloads** (read-only, `post1.txt`-`post3.txt`, `settle.log`, `alerts-post.txt`).
  - The canary writer is Running. Read the Running pod's logs by name (a stale Error pod can be the one
    `logs deploy/...` picks). Its new log shows `start ... integrity=ok ... contiguous=True` with `count` at or
    above the T-2 `ack`, then `ack` lines. The pod was rescheduled or restarted by the workers' graceful shutdown
    (1.2) and needed no manual step. 2026-11-25: kube-worker-02, `count=43839 max=43839` (>= 43345), acks continue.
  - Unstage before power-off, for every retained volume staged at T0 (the democratic-csi VAs per node in `pre.txt`):
    its old worker's `journalctl -b -1 -o short-iso` shows `UnmountVolume.TearDown`, `UnmountDevice` succeeded and
    the iSCSI connection shutdown before that journal ends and before the storage VM's `qmshutdown`. Read the whole
    match list, not `tail -8`. `journalctl -b -1 -k` and the new boot's kernel log have no
    `EXT4-fs (error|warning)|MMP|I/O error|session recovery|conn error` (the root `vda1` mount lines are normal). A
    retained volume still staged at power-off is an F2 FAIL (Rulings), even when the writer recovers. The worker-side
    read stands in for a storage-VM-side session-close read and a `dumpe2fs -h` error count (the storage VM's
    `-b -1` kernel log had no session lines). F2 had one such volume, the canary: 2026-11-25 TearDown 16:12:22,
    UnmountDevice and logout 16:12:23, journal end 16:12:50, 101 `qmshutdown` 16:12:56.
  - Production: nodes Ready, every app Healthy (deadline about 30 min, from the 3.3 rebuild's 28 min; 2026-11-25:
    81/81 by 16:29 IST), and an ingress probe 200 or 302.
  - VAs per attacher and node: the Proxmox CSI VA count per worker equals its wwn count, and the Proxmox CSI total
    equals `pre.txt`; the democratic-csi VA count equals `pre.txt`, each VA on its writer's node (F2: one, PV
    `f1-canary`). Per-node counts may move.
    Do not use `wwn_check.py` (static 11-16 list). 2026-11-25: 14+19 = wwn 14/19 (total 33).
  - GPU admission race: list `UnexpectedAdmissionError` pods in `media`, and delete them by name with **Ben OK**
    (2026-11-25: none).
  - Alerts, about 15 min after the workers are Ready: none of StorageVMDown, StorageBootCheckFailed,
    StorageTargetMissing, StorageFencerBlind, MaintenanceLockStale or TempoBlocklistPollFailing firing. Cold-start
    pending `KubePodCrashLooping` and `CPUThrottlingHigh` are expected. Leave no file on pve.
  - The runner is online: on VM300, `systemctl is-active 'actions.runner.*'` and `pgrep -c -x Runner.Listener` (the
    org runners API needs admin:org). Lock `FREE`. Queued runs drain. On VM300, `findmnt -t tmpfs` again.
    Re-provision only what Ben re-creates; the executor never restores a credential itself.
  - Merges: `gh pr list --json number,autoMergeRequest` again in all five repos, and
    `git -C <repo> log --since=<T0-30m> origin/main` after a fetch. Any commit is a recorded deviation. 2026-11-25:
    not read after boot.
  - Write F2 PASS or FAIL against each outline expectation in `facts.md`. Keep the merge hold through Task 3.10.
- Done 2026-11-25 16:12 IST: **F2 PASS** on image 902 (before packer `c14e49f`) (`evidence/3.8/facts.md`). Rows from
  `f2rows.py`, not the B10 scripts; pre-flight findings in `evidence/3.8-preflight.md` (folded into Steps 1-6 above;
  runbook updated on apps branch `docs/pve-planned-reboot-f2`).
- Observed, not F2 criteria (2026-11-25):
  - Proxmox CSI (non-retained) volumes on both workers: kubelet `UnmountDevice` failed "EOF" at 16:12:49-52 (the CSI
    node plugin was gone before the unmount); systemd unmounted them at shutdown, no ext4 error after boot. Task 1.2's
    ordering covers democratic-csi, not proxmox-csi. Follow-up.
  - kube-worker-01 root disk `vda`: one READ I/O error at 05:46:37 IST, on the previous boot, before F2.
    Unexplained. Follow-up.
  - About 30 leftover Error pods from shutdowns (some from the 3.3 rebuild), terminated by graceful node shutdown and
    not GC'd. Cleanup is a mutation (Ben).
  - The stale apps "Validate manifests" run from 2026-08-06 still shows queued or in progress.
- **Combined with the memtest (Ben's call, memory `pve-memtest-plan`).** The memtest runbook stops guests by hand in
  step S1 (`qm shutdown` 200, 201, 202, 300, then 100), so that VM 100 is never force-stopped. That list omits the
  storage VM, and a manual order does not test pve's `stopall` order. The lab plan also said to run Check 1 only on a
  clean return boot, never after memtest (B10 Step 2b). So a combined run proves only the boot half:
  - add `qm shutdown <D1:storage_vmid> --timeout 180` after the workers and before VM 100 in S1 (**Ben OK**);
  - run Steps 4-6 on the return boot after Esc;
  - record the shutdown half as not proven on the final code. The only evidence for it is then lab B10's 11-17 slots.

  The recommendation is a separate plain reboot for F2.
- [x] **Step 7: Remove the canary.** Done 2026-11-26 (`evidence/3.8/step7.md`): apps#1730, apps#1731; tag
  `pending-delete:1795685971` (09:39:31Z); base-configs OutOfSync until the expiry (not predicted). Original text: Gate: F2 PASS, and both Task 3.10 verdicts PASS or Ben's ruling on each FAIL
  (a FAIL can still be re-run with the canary).
  1. **Writer off first.** Merge `chore/f1-canary-stop`, a new branch off `origin/main` that sets `replicas: 0` in
     `f1-canary.yaml` (the 3.7 drain branch is already merged) (**Ben OK**). Then confirm: no
     pod, no VolumeAttachment on `f1-canary`, and no iSCSI session to its target. The expiry refuses otherwise
     (ADR "Deletion").
  2. **The removal PR** `chore/f1-canary-remove`: the inventory entry, and delete `infrastructure/system/f1-canary/`.
     There is no `kustomization.yaml` line: the Application comes from the appset files generator, so deleting the
     directory removes it (cascade). One removal, so no override label. **Ben OK**: the merge is the approval to
     delete (ADR "Deletion").
     - Live events: ArgoCD prunes the writer and `democratic-csi/retained-startup-guard` (no other entry is there).
       The PV and PVC stay, because they are `Prune=false,Delete=false`. `storage-changed` makes `storage.yml` tag
       `regen/f1-canary` `pending-delete`.
       `StoragePendingDelete` fires, as expected.
     - Expected: `lvs -o lv_name,lv_tags` shows the `pending-delete` tag with today's date, and the target is still
       exported. Record the tag's epoch.
- [ ] **Step 8: Check the first production expiry** (read-only). It runs at the first daily `storage-expiry.yml` run
  (`5 10 * * *` UTC) that starts more than 72 h after the epoch in the `pending-delete` tag ("3 days later" can be a
  day early). Count from the runs actually seen, not the schedule. Ansible `9695e1c` (it touches the `storage.yml`
  push paths) must not merge between the Step 7 tag and Step 8 (Rulings: after Step 8).
  - Expected:
    - the run is green;
    - `lvs regen` has no `f1-canary`;
    - `vgs ... -o vg_tags regen` has `tombstone:f1-canary` and no `ledger:f1-canary:*`;
    - `find /sys/kernel/config/target/iscsi -maxdepth 1` has no canary IQN (not `targetcli ls`, which may auto-save
      the live config on exit);
    - PV `f1-canary` and PVC `democratic-csi/f1-canary-iscsi` are gone;
    - `StoragePendingDelete` has resolved;
    - no `lv-missing` refusal in the next `storage.yml` run.
  - This is Task 4.0's gate. If any check fails, follow `storage-vm-expiry.md` "Half-expiry recovery through
    storage.yml" and the crashed-create runbook's tombstone-gap section (D12) before Part 4.
  - Evidence goes to `evidence/3.8/expiry.txt`.

### Task 3.10: Hard stop with the writer running, and the manual fence drill `(not rehearsed)`

It runs inside Task 3.8, after its Step 6 (F2 PASS, 2026-11-25) and before its Step 7 removes the canary, while the
canary writer still runs. One hard stop of the worker that hosts the canary serves two verdicts:
- **V1, a worker hard stop with a retained-style volume staged and written.** No gate proves this today. The lab's
  Check 2 drained its writer first, Task 3.3's full rebuild ran before democratic-csi existed, and routine
  packer-to-terraform applies run in normal mode (until Task 5.11, D41), where the Telmate delete hard-stops each worker
  (requirements audit, requirement 3, gap 1). `qm stop` is the stand-in for that delete.
- **V2, the manual fence runbook** (`storage-vm-fencing.md`, Task 2.7 Step 2: "Manual fence" and "Manual unfence").
  With `hold_fence` set it is the only fence (ADR `:508`, `:54`), and nothing has run it in production.

ADR 0017 cites in this task are to the unpushed branch `docs/adr-0014-retained-storage-vm` (`9026640b`). Code cites
are ansible `origin/main` `f0497cf` (prefix A, `homelab_storage/` = `roles/storage_vm/files/homelab_storage/`) and apps
`origin/main` `6a474b48`.

**Variant: cordon first** (Ben, 2026-11-25, binding). W = `kube-worker-02` (VMID 202, the canary's node), W2 =
`kube-worker-01` (201). Before the stop, 202 is cordoned and every pod with a Proxmox CSI volume moves to 201 by a
graceful delete, so the stop crashes only the canary writer and a few stateless pods. With no foreign VA left on 202,
the running fencer finishes the manual fence and taints 202 itself (A `fencer.py:4-5,255-259`). What this changes
(pre-flight finding 5):
- V1 = a hard stop with only the canary staged and written: the crash of a live writer, the MMP wait, the journal
  replay, integrity against the streamed ack, and no error flag.
- V2 = the manual fence, the fencer's own taint (no foreign VA) and the manual unfence.
- Not proven here, recorded in `facts.md`, left for Task 5.x or never: the migration-only `qm stop` before a manual
  taint (runbook "Migration-only qm stop before the taint", ADR `:716-717`), the force-detach of Proxmox CSI disks
  from a stopped VM (proxmox-csi-plugin 0.5.16), the manual taint itself, and the fencer's `foreign-va` refusal live.

The storage VM holds only the canary, so no data other than the canary is at risk on it. The production cost is the
pod moves: each app on 202 restarts once on 201, postgres's move blips authentik and every app behind it, and four
apps stay Pending from their move until Step 9 (201 has 29 slots, A `group_vars/all/proxmox_csi.yml:7,14`).

**Rulings** (carried from F2, Ben 2026-11-25): any data-safety deviation is a stop; nothing merges in any repo from
Step 3 to the end of Step 10. Ben's host writes for this drill (each **Ben OK** on the day): a transient
`systemd-run` unit on the master that streams the canary writer's log (Step 5), and
`blockdev --flushbufs /dev/regen/f1-canary` on storage-01 right before each `dumpe2fs -h` read. No other file or unit
on any host.

**Files:**
- Exists: `evidence/3.10-preflight.md` (findings 1-11, M1-M12, decisions, critic); `evidence/3.10/pre0.txt` and
  `rows-pre0.json` (live read 2026-11-25 about 17:50 IST).
- Rewrite (helper): the existing `~/.cache/claude-homelab-live/storage-migration/f310rows.py` (2026-11-25 17:55,
  modes `gate`, `regate`, `watch`, `fenceproof`, `move`, `dumpe2fs`, `post`) to the mode list below, modelled on
  `f2rows.py`. Delete the stale `evidence/3.10/rows-*.json` except `rows-pre0.json` (among them the host-write
  `rows-dumpe2fs.json` and a `rows-move.json` with `--since` hard-coded to 08:10 UTC), so none is run by mistake on the
  day. It writes `evidence/3.10/rows-<mode>.json` for
  `/opt/azure-cli/bin/python3 -I ~/.cache/claude-homelab-live/bin/live.py`.
  Rows are `[host, cmd, timeout]`; the kube prefix `K()` comes from `evidence/3.3/rows-post.json`, the storage
  identity rows (configfs ACLs, not `targetcli ls`, M10) from `evidence/3.7/rows-base.json`. QGA rows are
  `qm guest exec <vmid> --timeout N -- sh -c '...'` piped to the out-data printer; ASCII only, no `$` and no single
  quote inside the `sh -c` body, so a pod name or time goes in as a literal argument. Keep the existing assertions
  (ASCII, `bash -n`, no `$` or `'` in a guest `sh -c` body). VMIDs 101, 201 and 202 are hard-coded, as in
  `f2rows.py`; the master is not: it comes from the `K()` tag lookup (`k3s` and `master` tags, `rows-post.json`), and
  the `ack-*` rows reuse that same `$M` lookup outside the `sh -c` body. Every write or mutation mode prints
  `WRITE: Ben OK` when it writes its rows file. Modes:
  - read-only: `pre`, `progress`, `regate`, `watch`, `prove`, `restage`, `post`, `ack-read`;
  - host write, **Ben OK** each run: `flush` (flushbufs, then `dumpe2fs -h`), `ack-start <pod>`, `ack-stop`;
  - cluster or VM mutation, **Ben OK** each run: `cordon`, `delete <ns>/<pod> ...`, `stop`, `fence`, `unfence`,
    `start`, `uncordon`. The `fence` and `unfence` rows use `qm guest exec 101 --timeout 240` and a row timeout of
    300 (finding 6).
- Create (evidence): `evidence/3.10/` with `pre.txt`, `moves.txt`, `regate.txt`, `ack-stream.txt`, `stop.txt`,
  `fence.txt`, `restage.txt`, `post.txt`, the rows files and `facts.md`.

**Interfaces:**
- Consumes:
  - runbook `storage-vm-fencing.md` (apps `docs/runbooks/`): "Manual fence" (`:63-90`) and "Manual unfence"
    (`:110-132`);
  - `storage-fencer fence <node>`, `prove <node>`, `unfence <node> --confirm-stopped` and `status`
    (A `homelab_storage/fencer.py:1-9,292-333`); fence steps and the "proof failed, no taint" exit
    (`fencer.py:86-124`), the unfence order taint, ACL, nft, save, tag (`fencer.py:133-146`), the settle of an
    `unknown` tag (`fencer.py:216-237`), the `tainted`/`untainted` log lines (`fencer.py:77-82`);
  - the stall reasons `not-ready-too-short`, `watch-too-short`, `foreign-va` and the hold (A
    `homelab_storage/fence_policy.py:114-123`); `not_ready_seconds: 300`, `loop_seconds: 15`,
    `proof_timeout_seconds: 60` (A `roles/storage_vm/defaults/main.yml:33-35`); the LIO flock gives up after 120 s
    with `held for over 120 s` (A `homelab_storage/host.py:66,82`);
  - the taint `node.kubernetes.io/out-of-service=nodeshutdown:NoExecute` (A `homelab_storage/kube.py:11`);
  - `storage-fencer.prom` in `/var/lib/prometheus/node-exporter/` on storage-01 (A `homelab_storage/metrics.py:6`);
  - the canary from Task 3.6: `start host=... integrity=... count=... max=... contiguous=...` and `ack <n>` (apps
    `infrastructure/system/f1-canary/manifests/f1-canary.yaml:21,30`), any worker (`:54-55`), RWOP and Recreate
    (`:40-42`); democratic-csi `MOUNT_DEFAULT_TIMEOUT` 900000 ms (apps
    `infrastructure/system/democratic-csi/manifests/values.yaml:47-52`, F6);
  - alerts StorageWorkerFenced, StorageFenceFailed, NodeOutOfServiceTaintStuck (apps
    `services/operations/kube-prometheus-stack/manifests/storage-vm.yaml:126,133,170`), the three Proxmox CSI
    headroom alerts (`proxmox-csi-capacity.yaml:35,45,55`), TempoBlocklistPollFailing (`custom-rules.yaml:174`);
  - Task 3.8 Step 6's production checks; memory notes `tempo-torn-block-retention` (`tempo_prune.py dry|delete`),
    `gpu-admission-race`, `ingress-probe-from-workstation`.
- Produces: verdicts V1 and V2 in `facts.md`, V1's crash cost, the pod-move cost, the not-proven list, and Ben's
  rebalance decision (Step 10).

**Outcome (2026-11-26, `evidence/3.10/facts.md`): V1 PASS, V2 PASS.** T0 08:28:44Z; last ack 359366 = restage
`count=359366 integrity=ok contiguous=True` on kube-worker-01; MMP wait 44 s, journal recovery complete, dumpe2fs clean
with MMP on kube-worker-01. `hold_fence` from T0+5.95 min with no self-fence; manual fence 08:40:53Z exit 0, the
fencer's own taint 7 s later; unfence clean; 202 Ready 08:43:41Z. Pod moves: postgres 93 s, Tier C 45-65 s, the
Pending four about 21-25 min. Expected alerts only (StorageWorkerFenced, attach headroom, the Pending four,
TargetDown for 202). No merges or runs during the drill. Rebalance (Ben: media six) left 201=23, 202=10.

- [x] **Step 1: Slot, Pending list and notice** (Ben, decided 2026-11-25).
  - Slot: Thursday 2026-11-26, Step 3 at 10:10 IST (08:10 UTC), after the 08:05 UTC `storage.yml` run has finished.
    Step 9 starts by 08:50 UTC, before the 09:05 UTC run. It clears every backup window (M9: hh:25-hh:50 in the 03,
    09, 15 and 21 IST hours, 01:55-02:15, 04:25-07:00, Sunday 00:55-01:15, the 10 UTC hour), apps Renovate (weekdays
    22:00-06:00 and weekends Asia/Jerusalem, finding 10), `storage-expiry.yml` (10:05 UTC) and late `drift.yml`
    runs (from about 15:30 UTC, M8). The drill takes no maintenance lock (`lock.sh` is staged in Task 4.0).
  - Budget (typical): moves 08:10-08:22, re-gate and stop about 08:25 (T0), stall watch to T0+7 min, fence about
    08:33, restage done by about 08:36 (MMP 42 s) or 08:46 (720 s worst case), Step 9 by 08:50. If Step 7 (the
    fence) has not started by 08:50 UTC, skip Steps 7-8: nothing is fenced, so Step 9 runs without the unfence, V2
    is not run, and V1 keeps the stall and the writer's restart after `qm start` (integrity and `count` against the
    streamed ack still read); Ben picks a new slot for V2. In this branch 202 stays cordoned after `qm start` until
    the new canary pod is Running on kube-worker-01, so V1's `on kube-worker-01` still holds; only then uncordon.
    If the fence ran, Step 9's unfence waits for its restage gate (Step 9, first bullet) even past 08:50 UTC: 202 is
    not started early. A fencer command that then meets the 09:05 UTC run's lock (`held for over 120 s`) is retried
    after that run (Step 4). Ben confirms. Step 8's remaining reads continue after Step 9.
  - Pending list (201 has 14 used of 29 slots, 15 free; 202 has 19 volumes, pre0.txt): the last four
    deleted stay Pending until Step 9. Ben confirmed 2026-11-25: lingarr, stirling-pdf, bytestash, filebrowser.
    They move: calibre-web, radarr-ru, sonarr-ru, qbittorrent-ru.
  - Household notice: each app on 202 restarts once between 10:10 and about 10:25 IST (postgres first: authentik
    login and every protected app blink for a minute or two; Home Assistant, Mosquitto and zigbee2mqtt restart, so
    automations pause briefly; monitoring has a short gap). The four Pending apps are down from about 10:20 to about
    11:00 IST.
  - Expected alerts (M1), none of them a FAIL: StorageWorkerFenced (critical, no `for:`) from Step 7 to Step 9;
    NodeOutOfServiceTaintStuck if the taint stays over 15 min; ProxmoxCSINodeAttachmentHeadroomLow on
    kube-worker-01 once it has 29 of 29 (15 min); the cluster headroom alert (under 10 free, 30 min) and
    ProxmoxCSIClusterAttachmentCapacityExhausted (critical, 5 min, once 201 is at 29 of 29) from the cordon (Step 3)
    and Tier C until the uncordon (the rules count only Ready, schedulable workers, `proxmox-csi-capacity.yaml:34`);
    KubeNodeNotReady/Unreachable and TargetDown for 202; KubePodNotReady for the four Pending pods.
  - Merge hold: nothing merges in any repo from Step 3 to the end of Step 10.
- [x] **Step 2: Pre-check and baseline** (read-only, `f310rows.py pre` into `pre.txt`, about 09:50-10:05 IST).
  Abort if any check fails.
  - D28 (M3): the newest `storage.yml` run is newer than the newest ansible `deploy.yml` run, and its step
    "Reconcile under the lock" is `success` (`gh run view <id> --json jobs`), not a green run that skipped. From
    `storage-fencer.prom`: `time() - storage_fencer_last_api_success_timestamp_seconds < 60` (compare with `date +%s`
    on 101) and `storage_fencer_api_errors_total{code="auth"}` recorded (pre0: 0). If the token may be stale, dispatch
    `storage.yml` first (**Ben OK**). `unfence` removes the taint through the API first (ADR `:520-524`).
  - `VM 101 'storage-fencer status'`: `"fenced": {}` and `"holds": ["hold_fence"]`; `nft list set inet filter
    fenced` empty; the canary target has both worker ACLs, read from configfs (the 3.7 identity row, M10).
    `storage_fence_active` 0 for both workers and `storage_fence_failures_total` from the `.prom` file (finding 8; pre0:
    0, 0, 0).
  - The canary writer runs on kube-worker-02: its Running pod by name
    (`KUBE -n democratic-csi get pods -l app.kubernetes.io/name=f1-canary-writer --field-selector=status.phase=Running
    -o wide`). Never `logs deploy/...`: it can pick the stale Completed pod `...z7ps7` (finding 3). Record the pod
    name, its `start` line and last `ack` by pod name. If it is not on 202, stop and bring it to Ben.
  - 202's bootID (`KUBE get node kube-worker-02 -o jsonpath='{.status.nodeInfo.bootID}'`, M6). Both workers Ready,
    no out-of-service taint, neither cordoned.
  - VAs with PV names per node (pre0: 14 csi.proxmox on 201; 19 csi.proxmox and the one node-manual `f1-canary` on
    202); `qm config` scsi and wwn counts (pre0: 201 14/14, 202 19/19; every scsi line on a worker is a CSI disk,
    terraform `modules/vm/main.tf:15,295`). If the split differs from pre0, redo the Pending list with Ben.
  - Pods per node: where postgres, redis, CoreDNS, Prometheus, Alertmanager, Loki, Tempo, the Argo controller and
    repo-server, and authentik server/worker run (pre0: all of them on 202 except redis and one authentik-server
    on 201), the democratic-csi controller pods (the external attacher, apps
    `infrastructure/system/democratic-csi/manifests/values.yaml:7-9`) and any other democratic-csi Deployment pod,
    every non-DaemonSet pod on 202 with its PVCs, and 201's allocatable and requests (pre0: 5317Mi, 22%).
  - The `.spec.nodeSelector` and `.spec.affinity` of each Tier A, C and D pod (jsonpath
    `{.spec.nodeSelector}{.spec.affinity}`), so a pod pinned to 202 (zigbee2mqtt's coordinator, Home Assistant's
    matter) is known before the slot. A pinned pod goes to Ben before Step 3.
  - 201's kernel log this boot: no `I/O error|blk_update` (pre0: clean; the 11-25 05:46 vda error was the previous
    boot, finding 8). 201's `iscsiadm -m session` and `findmnt -rn -t ext4` (baseline for Step 6).
  - democratic-csi live: the node DaemonSet's `MOUNT_DEFAULT_TIMEOUT` reads `900000` (the pre0 read came back cut).
  - Apps: every app Synced/Healthy, as Task 3.8 Step 2; alerts firing now (the baseline for Step 10); Tempo:
    `increase(tempodb_blocklist_tenant_index_errors_total[15m])` and `ALERTS{alertname="TempoBlocklistPollFailing"}`.
  - `f310rows.py flush` (**Ben OK**): `VM 101 'blockdev --flushbufs /dev/regen/f1-canary && dumpe2fs -h
    /dev/regen/f1-canary 2>/dev/null |
    grep -E "^(Filesystem state|FS Error count|First error|Last error|MMP)|mmp_node_name|mmp_sequence"'`.
    The flush is needed: LIO's iblock I/O bypasses storage-01's page cache, so a plain read shows a stale superblock
    (finding 2, `evidence/3.7/facts.md:14`). Expected: `mmp_node_name` kube-worker-02, no `FS Error count` line
    (unless Task 3.7's writer-running variant left one, D11). Record it, with any `First error` and `Last error`
    lines: Step 8 compares against them. A baseline flag goes to Ben here, before Step 3.
- [x] **Step 3: Cordon 202 and move its pods** (`moves.txt`, 08:10 UTC, after the 08:05 UTC run has finished).
  - First: the 08:05 UTC `storage.yml` run finished with `success` and its step "Reconcile under the lock"
    `success` (as Step 2); `gh pr list` in all five repos with `--json number,title,autoMergeRequest` shows no
    auto-merge (disabling one needs **Ben OK**); the canary is still Running on 202.
  - A fresh `f310rows.py progress` read just before the cordon: the delete list comes from it, not from `pre.txt`
    (Deployment pod names can change in 20 min).
  - `KUBE cordon kube-worker-02`. **Ben OK.** Record the cordon time (`date -u`) in `moves.txt`: the merge check in
    Step 10 starts there.
  - Show Ben the delete list (namespace, pod name from that fresh read, PVCs), then delete by name, tier by tier, with
    `KUBE -n <ns> delete pod <name> --wait=false`. **Ben OK** for the list. Never the canary writer, never a DaemonSet
    pod (traefik, the CSI node plugins, node-exporter, ...), never a Completed leftover. Do not scale: ArgoCD selfHeal
    undoes a scale-down. After each tier, `f310rows.py progress` (VAs per node, scsi/wwn counts, pod phases) and go
    on only when the tier is Running on 201:
    - Tier A, critical (9 volumes): `postgres-postgresql-0` alone first, wait Running on 201; then
      `prometheus-kube-prometheus-stack-prometheus-0`, `alertmanager-kube-prometheus-stack-alertmanager-0`, `loki-0`,
      `tempo-0` (a graceful move avoids the Tempo tear), home-assistant (config and matter volumes), mosquitto,
      zigbee2mqtt. Expected after: csi.proxmox VAs 201=23, 202=10, scsi/wwn 23/23 and 10/10.
    - Tier B, stateless: `argocd-application-controller-0`, the argocd-repo-server, authentik-server and
      authentik-worker pods, and the CoreDNS pod on 202 (one at a time, each back Running before the next). Any
      democratic-csi controller pod on 202 goes here too and is not struck: left there it dies at T0 and the
      node-manual VA's move in Step 8 waits for its rescheduling. Any other non-DaemonSet pod on 202 goes on this tier
      unless Ben strikes it; one left there dies at T0, recorded.
    - Tier C (6 volumes): radarr, sonarr, calibre-web, radarr-ru, sonarr-ru, qbittorrent-ru. Expected after: 201=29,
      202=4, scsi/wwn 29/29 and 4/4.
    - Tier D (4 volumes, the Pending list): lingarr, stirling-pdf, bytestash, filebrowser. Expected: their new pods
      Pending (FailedScheduling on the attach limit), 202 has 0 csi.proxmox VAs and `qm config 202` has 0 scsi lines.
  - A pod that does not leave 202 or come up on 201 within about 5 min: stop and bring it to Ben (it is a move
    problem, not a drill result).
  - Record each app's downtime (delete to Running), for the pod-move cost (finding 11).
- [x] **Step 4: Re-gate at T-2** (read-only, `f310rows.py regate` into `regate.txt`; finding 9). All must hold:
  - `gh run list --status in_progress` and `--status queued` in all five repos print nothing except the stale apps
    run 31122150442 (2026-08-06, M7); `gh pr list ... autoMergeRequest` none (finding 10).
  - VM300: `pgrep -c -x Runner.Worker` 0 and `/var/lib/homelab-maintenance/operation.json` absent (lock `FREE`).
  - Zero non-node-manual VA on 202:
    `KUBE get volumeattachments -o jsonpath='{range .items[*]}{.spec.attacher} {.spec.nodeName}{"\n"}{end}' |
    awk '$2=="kube-worker-02" && $1!="org.democratic-csi.node-manual"' | wc -l` prints 0 (finding 5), the node-manual
    `f1-canary` VA is on 202, and `qm config 202 | grep -cE '^scsi[0-9]+:'` prints 0. No democratic-csi controller
    pod on 202.
  - The canary pod from `pre.txt` is Running on 202 and printing `ack` lines; `storage-fencer.prom` API success
    under 60 s old, auth errors unchanged.
  - Latest T0 is 08:35 UTC (the budget leaves the watch, the fence and the restage before 08:50). Past it, do not
    stop 202: Ben chooses between waiting for the 09:05 UTC run to finish and re-gating, or uncordoning 202
    (**Ben OK**) and rescheduling.
  - A `storage.yml` run that starts late after this point is expected, not an abort: if a fencer command later
    fails with `held for over 120 s`, wait for that run to finish and run the command again. If the run fails and had
    taken the maintenance lock (after "Try the maintenance lock once"), D31: finish the step in progress that restores
    service, then stop and bring it to Ben.
- [x] **Step 5: Stream the acks and hard stop 202** (V1, `ack-stream.txt`, `stop.txt`).
  - `f310rows.py ack-start <pod>` (**Ben OK**, host write): on the master,
    `systemd-run --unit=f310-ack --collect --property=RuntimeMaxSec=1800 k3s kubectl -n democratic-csi logs -f
    pod/<pod> -c writer --timestamps --tail 20` (`--tail 20`: the full log is hundreds of thousands of lines;
    `--collect`: the unit is unloaded however it ends, failed included, so no `reset-failed` is needed). Check one
    read of `ack-read` shows fresh `ack` lines.
  - `f310rows.py stop`: first, on the master, `systemctl is-active f310-ack` and a fresh `ack-read` tail; the row runs
    `qm stop` only when that reads `active` (RuntimeMaxSec or a broken stream must not leave the bound predating T0).
    Then `date -u +%FT%T.%NZ; qm stop 202; date -u +%FT%T.%NZ; qm status 202 --verbose`. **Ben OK**: it hard-stops
    202, the canary writer and any pod left there; the same OK covers `ack-stop` 30 s later (one OK, two runs). T0
    is the first timestamp. Expected: `status: stopped` and `qmpstatus: stopped` within seconds.
  - 30 s after T0, `f310rows.py ack-stop` (`systemctl stop f310-ack`; "not loaded" means the stream already ended and
    counts as success, recorded), then `ack-read` (`journalctl -u f310-ack --no-pager -o short-iso |
    grep -E " ack [0-9]|f310-ack" | tail -n 60`, read-only; the unit is gone, its journal stays). Record in
    `stop.txt` which way the unit ended (stopped, exited, failed or RuntimeMaxSec), the last complete `ack <n>` line,
    its container timestamp and T0. The streamed ack is a lower bound on the fsynced rows (the writer prints `ack`
    only after its `synchronous=FULL` commit), so Step 8 tests `count >= n`; that bound counts only if the stream was
    live up to T0 (V1 Required).
- [x] **Step 6: Watch the stall** (read-only, `f310rows.py watch` into `stop.txt`, every 1-2 min until T0+7 min or
  until the fencer logs its `hold_fence` line for kube-worker-02, whichever is later; M4). Expected:
  - 202 NotReady from about T0+40-50 s (the Ready transition starts the 300 s clock, `fence_policy.py:114-115`).
  - The fencer (`journalctl -u storage-fencer --since "<T0>" --no-pager | grep -E "kube-worker-02|error"`, absolute
    `--since`, M5): `kube-worker-02: not-ready-too-short`, then from about T0+5.8-6.2 min `kube-worker-02: hold_fence`
    (`fence_policy.py:122-123`). `watch-too-short` after a fencer restart is accepted. A `foreign-va` line means a
    VA did not detach: stop and bring it to Ben. Any fence or taint the fencer makes by itself here: V2 FAIL, stop.
    `storage_fence_active{node="kube-worker-02"}` 0 in the `.prom` file.
  - The node-manual `f1-canary` VA stays on kube-worker-02. The old canary pod shows Terminating from about
    T0+5.5 min (default 300 s `unreachable` toleration) and its replacement is Pending on the RWOP claim (lab
    `storage-lab/b6/runbook.md:100`).
  - No canary mount on 201: `VM 201 'iscsiadm -m session; findmnt -rn -t ext4'` matches `pre.txt` (201 keeps its
    ACL, so only Kubernetes keeps it off the LUN). A canary session or mount on 201 before Step 7's taint is a data
    safety stop and a V1 FAIL.
- [x] **Step 7: Manual fence** (runbook "Manual fence" steps 1-2, `fence.txt`). `qm status 202 --verbose` reads
  `stopped`, then `f310rows.py fence`: `VM 101 'storage-fencer fence kube-worker-02'` (`--timeout 240`). **Ben OK**:
  this is the last human gate. A passing proof lets the running loop taint 202 within about one loop (15 s), which
  evicts the old canary pod and moves the canary to 201.
  - Expected: exit 0; stderr shows `fence kube-worker-02: tagged, bootID not settled yet`, the ACL deletes and
    `fence kube-worker-02: proven`; stdout is a passing proof, every `acl_present` false, `addr_in_set` true,
    `established` empty.
  - Then `f310rows.py prove` (read-only): `prove kube-worker-02` exits 0 with the same proof; `status` lists
    kube-worker-02 under `fenced`; the nft set `fenced` holds 202's bridge address; configfs has no ACL for 202.
  - The `unknown` tag lasts about 15 s (M6): the loop logs `fence kube-worker-02: settled on bootID <id>` with the
    bootID from `pre.txt`, then `tainted kube-worker-02` (`fencer.py:77-82`), at about T0+7 min when Step 7 follows
    Step 6 at once (the fencer's own taint, no foreign VA).
  - Failure branch (finding 6): on exit 1, or exit `None` from a guest-exec timeout (unknown, not a failure, until
    checked), take no further mutation. Read `status`, `prove kube-worker-02` and
    `journalctl -u storage-fencer --since "<T0>" | grep -E "kube-worker-02|error"` into `fence.txt`. A failed proof has
    already tagged, added the nft element and deleted ACLs (`fencer.py:92-116`), and the running loop keeps retrying
    and taints once its own proof passes, so "stop" does not freeze the state: bring it all to Ben. `held for over
    120 s` is a late `storage.yml` run: wait for it and run the fence again (Step 4).
  - If the proof passed but no `tainted kube-worker-02` follows within about 1 min (4 loops): V2 FAIL, recorded.
    The fencer taints only with a passing proof and no foreign VA (`fencer.py:255-259`), and the runbook checks VAs
    before its taint (`:84-85`, `:97-99`), so first take fresh reads of all of these into `fence.txt`: (1) the
    Step 4 `awk` count of foreign VAs on kube-worker-02 prints 0; (2) `qm status 202 --verbose` reads `stopped`;
    (3) `prove kube-worker-02` exits 0; (4) `status` lists the tag; (5) the journal line that says why the loop did
    not taint (an `error: API:`, `held for over 120 s` or `error: loop:` line). Only with all five, restoring service
    is the runbook's "Manual fence" step 3 "After Retirement" line,
    `KUBE taint node kube-worker-02 node.kubernetes.io/out-of-service=nodeshutdown:NoExecute` (**Ben OK**), recorded as
    a deviation. On a foreign VA, or with no reason found, do not taint (a hand taint then is the force-detach of a
    Proxmox CSI disk this drill never does): bring it to Ben.
- [x] **Step 8: The restage on 201** (read-only, `f310rows.py restage` into `restage.txt`). V1's evidence. T6 is the
  taint's `timeAdded` (`KUBE get node kube-worker-02 -o jsonpath='{.spec.taints}'`) if present (the fencer patches
  the taint without it, A `kube.py:11,30-39`), else the timestamp of the fencer's `tainted kube-worker-02` journal
  line, else the old canary pod's deletion.
  - Re-check `gh pr list ... autoMergeRequest` in all five repos: none (finding 10).
  - PodGC removes the old canary pod; the node-manual VA moves to kube-worker-01; the new writer pod runs on 201.
  - `VM 201 'journalctl -k --since "<T6 minus 1 min, UTC>" --no-pager | grep -E "EXT4|MMP|mounting fs with errors"'`
    (absolute time, M5). Expected: the MMP wait (lab: `MMP interval 42 higher than expected, please wait`; about 42 s,
    up to about 720 s, ADR `:265-266`), then `EXT4-fs (sdX): recovery complete` and `mounted filesystem ... r/w`
    (lab `b7:24`, `b8:58`, `b10:138`). No `mounting fs with errors` and no `EXT4-fs error` line: this kernel read is
    the main no-error-flag evidence (finding 2). Optional: `/sys/fs/ext4/<sdX>/errors_count` reads 0.
  - The new pod's events (`KUBE -n democratic-csi get events --field-selector involvedObject.name=<new pod>`): the
    stage completes within `MOUNT_DEFAULT_TIMEOUT` (900 s) with no `INTERNAL` stage error left behind (F6).
  - By the new pod's name: `-c guard` prints `Retained identity accepted.`; `-c writer --timestamps | grep -m1
    " start "` prints `start host=kube-worker-01 integrity=ok count=<n> max=<n> contiguous=True` with `n` at or above
    Step 5's streamed ack, then `ack` lines (with `--previous` if it restarted). `contiguous` is only `count == max`,
    so rows missing at the end show only as `n` below the streamed ack (finding 3). Record T0 minus the last ack's
    timestamp.
  - `f310rows.py flush` (**Ben OK**): the Step 2 read again. Expected: `mmp_node_name` kube-worker-01; if `pre.txt`
    has no `FS Error count` line, none now; if it has one, `FS Error count`, `First error` and `Last error` unchanged
    from `pre.txt` and no First or Last error time after T0. Otherwise V1 FAIL. 202 died without an I/O error, so no
    flag is set (D11 is the case where the old mounter lived on); the kernel read on 201 stays the main evidence.
  - Production: every pod on 201 Running except the four named Pending pods and their dependents; an ingress probe
    returns 200 or 302 against an app whose whole chain (pod, postgres, redis, authentik) is Running.
- [x] **Step 9: Unfence, check the disks, start 202** (runbook "Manual unfence", `post.txt`; by 08:50 UTC unless the
  restage gate below holds it).
  - Restage gate first (a `restage` read): the old canary pod is gone from the API, the node-manual VA is attached on
    kube-worker-01, and 201's kernel log shows `mounted filesystem ... r/w` or the new writer is Running. The unfence
    gives 202 its ACL back and `qm start` boots it, so not while 201 may still be in the MMP wait (up to about 720 s)
    or the old pod exists: a stale iscsid node record on 202 could log in at boot. If 08:50 UTC passes first, wait
    (Step 1); Ben confirms.
  - `qm status 202 --verbose` reads `stopped`, then `f310rows.py unfence`:
    `VM 101 'storage-fencer unfence kube-worker-02 --confirm-stopped'` (`--timeout 240`). **Ben OK.** Expected: exit
    0, stderr `untainted kube-worker-02` then `unfenced kube-worker-02` (the order taint, ACL, nft, save, tag:
    `fencer.py:133-146`; lab `b6/runbook.md:40`). `KUBE get node kube-worker-02 -o jsonpath='{.spec.taints}'` has no
    out-of-service taint. With 202 unfenced but NotReady, only `hold_fence` keeps the loop from fencing it again.
  - Unfence failure (finding 7): on any non-zero exit or exit `None`, read `status`, `prove kube-worker-02` and
    `journalctl -u storage-fencer | grep -E "kube-worker-02|error"` first. If the `fenced:kube-worker-02:` tag is
    still there, the loop re-taints 202 within about 15 s (`fencer.py:255-259`): let it settle, then run the unfence
    again (every unfence step is safe to repeat). Refresh the token (`storage.yml`, **Ben OK**, D28) only on
    `error: API: ...` with 401/403 or `token unreadable`. Remove the taint by hand
    (`KUBE taint node kube-worker-02 node.kubernetes.io/out-of-service=nodeshutdown:NoExecute-`, **Ben OK**) only when
    `status` shows no tag for kube-worker-02; never while a tag exists.
  - Before `qm start` (finding 1): `qm config 202 | grep -cE '^scsi[0-9]+:'` equals the csi.proxmox VAs on 202, which
    is 0; no csi.proxmox VA names kube-worker-02; 201's wwn scsi count equals its csi.proxmox VA count (29). On any
    mismatch do not start 202: a leftover scsi line would open a `vm-9999-*.raw` that 201 has mounted. Bring it to
    Ben.
  - `qm start 202`. **Ben OK.** Then, once 202 is Ready on a new bootID, `KUBE uncordon kube-worker-02` (**Ben OK**).
    The four Pending pods schedule on 202 (the only node with free slots).
  - GPU admission race: list `UnexpectedAdmissionError` pods in `media` and delete them by name (**Ben OK**).
- [x] **Step 10: Post-checks, rebalance and verdicts** (read-only `f310rows.py post` into `post.txt`, then `facts.md`).
  - Expected: 202 Ready on a new bootID, no `.spec.unschedulable`; `storage-fencer status` `"fenced": {}` and
    `"holds": ["hold_fence"]`; the nft set `fenced` empty; the canary target has both ACLs again (configfs); the
    canary writer stays on 201 (nothing moves it back); the four Pending pods Running on 202; every app Healthy.
  - 202 after boot (data safety, pre-flight critic): `VM 202 'iscsiadm -m session; findmnt -rn -t ext4'` shows no
    canary session or mount (201 has it mounted, and the unfence gave 202 its ACL back). Any: stop, bring it to Ben.
  - Counts (M2, the 3.8 wording): 33 csi.proxmox VAs in total (expected 201=29, 202=4); per worker the VAs equal the
    wwn scsi lines; exactly one node-manual VA, on kube-worker-01. Per-node counts are not compared with `pre.txt`.
  - Merges: `gh pr list --state merged --search "merged:>=<cordon time>"` (the Step 3 cordon timestamp in
    `moves.txt`, where the hold starts) in all five repos, and `git -C <repo> log
    --since=<T0-30m> origin/main` after a fetch. Any merge is a recorded deviation (finding 10).
  - Alerts, about 15 min after 202 is Ready (finding 11, from Task 3.8 Step 6): none of StorageVMDown,
    StorageBootCheckFailed, StorageTargetMissing, StorageFencerBlind, StorageFenceFailed, MaintenanceLockStale or
    TempoBlocklistPollFailing firing; the Step 1 expected alerts resolved, except
    ProxmoxCSINodeAttachmentHeadroomLow on kube-worker-01 until the rebalance; `storage_fence_failures_total` in the
    `.prom` file unchanged from `pre.txt` (M1). An increase is accepted only if each one matches a
    `held for over 120 s` or `error: loop:` journal line during a recorded late `storage.yml` run (a loop that waits
    out the LIO lock counts a failure, `fencer.py:190-192`, and StorageFenceFailed may fire with it); any other
    increase is a deviation.
  - Tempo (moved in Tier A): 5-10 min after it was Running, `increase(tempodb_blocklist_tenant_index_errors_total[15m])`
    flat and no `failed to poll` in its log; `ALERTS{alertname="TempoBlocklistPollFailing"}` again at about T+45 min
    (the rule has `for: 30m`); `tempo_prune.py dry`, and a prune only with **Ben OK**. Read the logs of the other
    crash-sensitive apps that moved (Home Assistant, zigbee2mqtt, qbittorrent-ru, Loki, Prometheus) for corruption or
    replay errors.
  - Runner online, lock `FREE`; queued runs drain.
  - Rebalance (**Ben decides**): 201 holds 29 of 29 slots and 202 holds 4, so no new Proxmox CSI volume fits on 201
    and its headroom alert stays. Options: leave it; or move named pods back (cordon 201, delete by name, uncordon
    201, each **Ben OK**), for example Tier C's six (201=23, 202=10). Record the choice.
  - Lift the merge hold.
  - **V1, Required** (finding 4; FAIL means any one missed):
    - no canary session or mount on 201, and no fence or taint the fencer made by itself, before Step 7;
    - `start ... integrity=ok ... contiguous=True` on kube-worker-01, with `count` at or above Step 5's streamed ack;
    - the stream was live up to T0: the last streamed ack's container timestamp is within about 2 s of T0 (allowing
      for NTP skew between 202 and pve) and the streamed ack numbers are contiguous up to it. A larger gap makes the
      count test inconclusive, not PASS: bring it to Ben;
    - no error flag: no `mounting fs with errors` or `EXT4-fs error` in 201's kernel log, and in the flushed
      `dumpe2fs -h` `FS Error count` absent or unchanged from Step 2, with no First or Last error time after T0;
    - no manual step other than the fence (and, if the fencer did not taint, the recorded manual taint).
  - **V1, Recorded as findings:** the MMP wait and its length, the replay lines, the fencer's reason lines, the guard
    line, the F6 events, T0 minus the last ack, and the crash cost (lost or kept rows, error flags, the MMP wait,
    manual steps). Drain mode is already decided (D41, enforced by Task 5.11); V1 no longer decides it.
  - **V2 PASS:** Steps 6-9 met: the stall held at `hold_fence`; the fence printed a passing proof, the tag settled on
    202's `pre.txt` bootID and the fencer tainted 202 itself; the unfence ran as the runbook writes it and left
    `"fenced": {}`, the nft set empty and both ACLs. Any runbook line that proved wrong goes into `facts.md` and to Ben
    as a runbook fix.
  - **Pod-move cost** (finding 11): each moved app's downtime, the Pending window of the four, any error in the moved
    apps' logs, the Tempo result.
  - **Not proven** (record each): the migration-only `qm stop` before a manual taint; the force-detach of Proxmox CSI
    disks from a stopped VM; the manual taint; the `foreign-va` refusal live; and against a real rebuild a fresh root
    disk, `k3s_node_retirement` deleting the stale Node and the VA left on a deleted Node; an unclean stop of the
    storage VM or of the pve host (M11).
  - A V1 FAIL: record it, stop before Part 4 and bring it to Ben. D41 covers planned rebuilds after Retirement only,
    not a worker crash during Part 4, so a FAIL needs Ben's decision before any cutover.
  - A V2 FAIL: stop before Part 4 and bring it to Ben, with the runbook fix.
  - Runbook follow-up for Ben (finding 11): fix the 15-min timing in `pve-planned-reboot.md:251`.

**Part 3 gate.** F1 and F2 have passed, Task 3.10's two verdicts are PASS (or Ben has decided each FAIL, see Task 3.10
Step 10), and the canary's expiry is clean. The cutovers in Part 4 start only after that.

### Task 3.9: Prove the one-flag guard (apps, D38)

After the Part 3 gate (F1, F2, Task 3.10 and the canary's expiry clean), and outside any Part 4 wave: run it before
Part 4 starts or after it ends, never between a wave's Inventory PR and its last switch. It does not gate Part 4. It
proves the three open facts of ADR Guards, "The one-flag guard": that the id reaches Helm through the AppSet's
`helm.parameters`, that `fsGroup` lets a non-root app write a fresh RWOP ext4 volume, and that the guard's fixed uid
can read the marker the storage VM wrote. No real app uses the flag until this passes.

**Files** (branch `feat/f1-flagged` off `origin/main`):
- Modify: `infrastructure/base-configs/files/retained-volumes.json`: entry `{"id": "f1-flagged", "namespace":
  "democratic-csi", "claim": "f1-flagged-iscsi", "size": "1Gi", "class": "regenerable", "origin": "new"}` (the exact
  field set the inventory schema then has).
- Create: `services/operations/f1-flagged/app.yaml` (`name: f1-flagged`, `namespace: democratic-csi`,
  `deployPhase: services`, `retained: f1-flagged`) and `values.yaml`: one main container, the same python digest,
  `runAsUser: 568`, `runAsGroup: 568`, `fsGroup: 568` (an app gid other than `templates/common.yaml`'s 1000: the
  layer relies on the pod's `fsGroup`, which kubelet adds to every container, the guard included, and applies to the
  volume's group), command `sh -c 'date > /config/write-test && cat
  /config/write-test && sleep infinity'`, worker `nodeSelector`. No guard, mount or strategy lines: the layer supplies
  them.

- [ ] **Step 1: Render offline.** Run the Task 2.9 tests and `scripts/check-retained-guards.py` on the branch.
  Expected: PASS, and the render shows `0-retained-guard` first with claim `f1-flagged-iscsi`.
- [ ] **Step 2: Read the PR's argocd-diff-preview** (Ben asks for the push and PR). Expected: the new Application
  `f1-flagged` renders the guard init container, the `f1-flagged-iscsi` claim and `strategy: Recreate`. If the guard
  or claim is missing, the `helm.parameters` path does not work on Argo CD 3.6.2: stop, and switch Task 2.9 to the
  fallback (`retained.id` in `values.yaml` plus a `commonValuesExtras` line) before going on.
- [ ] **Step 3: Merge** (**Ben OK**). Live events: base-configs renders the PV, the PVC and
  `democratic-csi/retained-startup-guard` (back, since the canary's entry is gone); the dispatch creates the LV,
  filesystem, marker and target; the app starts. Dispatch `storage.yml` by hand if the dispatch is not wired, as in
  Task 3.6 Step 5 (**Ben OK**).
- [ ] **Step 4: Check** (read-only):
  - `KUBE -n democratic-csi logs deploy/f1-flagged -c 0-retained-guard` reads `Retained identity accepted.`;
  - `KUBE -n democratic-csi logs deploy/f1-flagged -c main` prints the date it wrote;
  - `KUBE -n democratic-csi exec deploy/f1-flagged -c main -- sh -c 'id; stat -c "%a %u:%g %n" /config
    /config/.homelab-f1-flagged-data /config/write-test'`.
  - Expected: guard accepted; the write succeeded as uid 568; `/config` and the marker have group 568 with group read
    (kubelet's `fsGroup` change). Record the marker's "other" digit too: it shows what the storage VM wrote, which
    matters only for an app that sets no `fsGroup` (none does today; `templates/common.yaml` sets 1000). If the write
    fails with permission denied, `fsGroup` is not applied to RWOP here: stop for Ben (the layer then needs a
    documented uid rule for `origin: new`). If the guard refuses, stop for Ben; never edit the marker by hand.
  - Evidence: `evidence/3.9/`.
- [ ] **Step 5: Remove the flagged canary** (**Ben OK**), right after Step 4: a PR that deletes
  `services/operations/f1-flagged/` and the inventory entry.
- [ ] **Step 6: Check its expiry** (read-only, 3 days later), with Task 3.8 Step 8's checks for `f1-flagged`.
  Evidence: `evidence/3.9/expiry.txt`. No Part 4 wave and no other maintenance-lock user starts until it is clean.

---

## Part 4: cutovers (ADR Migration 3)

This part moves the 33 Proxmox CSI volumes, one cutover at a time. Task 4.0 runs once. Task 4.T is the cutover
template. Task 4.W gives every volume's parameters and the per-wave deltas, and it says which 4.T steps change. Task
4.C1 is gate C1. Everything here is live (Part B style): each step has a command or a PR action, an Expected line,
and **Ben OK** on every mutation. The Global Constraints apply throughout, in particular: Live work, Retained data,
Backup windows, Serialization (one cutover at a time, the freeze rule) and Evidence.

**Old budget until Task 5.1.** Volumes not yet moved still sit on Proxmox CSI SCSI slots, so the old 29-slot budget
stays in force for them until Task 5.1. Losing a worker during the migration can still strand old-path volumes.
Moved volumes restage on the peer only after the manual fence and taint (`storage-vm-fencing.md`), since `hold_fence`
is set. Task 5.8 is the gate that proves one worker carries every retained volume.

**New stateful apps during Parts 3-4** (D39). **Decided (Ben, 2026-11-22):**
- Before Task 3.9 has passed, a new app that needs a retained volume waits (D46, Ben 2026-11-22: this replaces the
  earlier option of the old Proxmox CSI ceremony, which D46 ruled out).
- After Task 3.9 has passed, and outside a wave, a new app may join the storage VM directly as an `origin: new`
  inventory entry with the one-flag guard. It is not a 4.W row, and Part 5's entry gate allows it.
- No new retained inventory entry is added between a wave's inventory PR and its last switch.

**Where commands run.** Every live command goes into a rows file and runs through the helper, as in Part 1:
`/opt/azure-cli/bin/python3 -I ~/.cache/claude-homelab-live/bin/live.py <rows.json>`. Commands are ASCII only.
Resource versions, indexes, ids and SHAs are pasted in as literals: pve expands `$var` before the guest sees it
(memory `backup-review-live-access`, 2026-11-15 pitfall). So no `[R]` or `[K-host]` row contains `$`: anything that
needs a shell variable runs from a script that Task 4.0 Step 9 stages on that host. Task 4.0 Step 9 also probes the
expansion once.
- `[K] <args>`: `k3s kubectl <args>` as root on the first Ready VM tagged `k3s;master`, via a `pve` row running
  `qm guest exec <vmid> -- ...`. This is Part 1's `KUBE`. If Task 4.0 Step 7 puts a working `kubectl` on VM300,
  `[K]` may run there instead; both talk to the same API.
- `[R]`: root on VM300 (the runner), via `qm guest exec 300`.
- `[P]`: root on pve.
- `[T]`: TrueNAS (VM 100), via a `tn` row, with literal paths only.
- `[S]`: the storage VM, via `qm guest exec <D1:storage_vmid>` from pve (Global Constraints; Part 3's
  `VM <vmid> '<cmd>'` path, already used from Task 3.5 on).
- `[W]`: the workstation (`gh`, `git`).
- `[TOOL]`: the host that Task 4.0 Step 7 picks for `scripts/storage/migrate_volume.py`. Its working directory per
  cutover is `<td>` = `/run/homelab-cutover/<id>/` (root-only; created by `install -d` on the tool host). Files
  rendered there are applied there with `[TOOL] kubectl apply`, then copied back to `<ev>` (`evidence/4.T-<id>/`) on
  the workstation.
- `[K-host]`: a root shell on the same master as `[K]`.

**Evidence.** Each cutover writes to `evidence/4.T-<id>/` (a D14 pair uses the first id). That covers the rows files,
the scrubbed output, `appproject-before.json`, `writers.txt`, `render/`, `copy.log`, `capacity.txt`, `watch.log` and
a `facts.md`. No secret, nonce or token value is ever written there.

**Window check.** Before every mutating step, run `TZ=Asia/Jerusalem date '+%a %H:%M'` and refuse to start inside a
backup window (Global Constraints). A cutover starts only when steps 3-8 fit before the next window. For an estimate,
use the copy rate measured at the earlier cutovers (`copy.log` start and end times).

### Task 4.0: Cutover readiness, once

**Files:**
- Create (evidence only): `evidence/4.0/rows.json`, `evidence/4.0/out.txt`, `evidence/4.0/facts.md`.
- No repo change, except the apps PR with D23's ServiceAccount and RBAC if Step 7 needs it. That PR is not drafted in
  this plan; draft it when Ben answers D23, before the first cutover.

**Interfaces:**
- Consumes:
  - `evidence/1.1/facts.md` (`retired_images_present`, `argocd_version`, `proxmox_csi_driver`);
  - Task 3.8's canary expiry;
  - `evidence/3.10/facts.md`: V1 and V2 PASS, or Ben's recorded decision on each FAIL (Task 3.10 Step 10);
  - Task 2.5's tool, from apps `main` after Task 3.6, and its reverse source gate rule (pass 1 refuses `gate` on zero
    or two writer templates, on zero or two init containers that mount the claim, or on a guard init container that
    also mounts another PVC);
  - D37: Task 3.6's one-time proof of the gate's read-only mount (`ro,noload` with MMP, PV `mountOptions` on
    node-manual), expected in `evidence/3.6/`;
  - the Task 4.W rows (values file, writer and guard);
  - `<D20:margin_gib>` (recommendation: 10).
- Produces, in `evidence/4.0/facts.md`:
  - `gate_expiry_clean`;
  - `drill_verdicts` (V1 and V2 from Task 3.10, each `PASS` or the decision Ben recorded for a FAIL);
  - `backup_green_7d` and `pstore_empty`;
  - `retired_images_deleted` (a list);
  - `capacity_rule`;
  - `freeze_checks`;
  - `m7_confirmed` and `m8_confirmed`;
  - `tool_host`;
  - `syncwindow_form`;
  - `lock_helper_sha256`, `lock_sh_sha256` and `watch_sh_sha256`;
  - `gate_ro_mount_proven` and `gate_coverage` (D37; 4.T R2's entry check reads both).

- [ ] **Step 1: Gate: the canary's expiry finished clean** (read-only; one helper OK for the session).
  - Run:
    - `[W] gh run list -R Starktastic-Homelab/ansible --workflow storage-expiry.yml --limit 5
      --json databaseId,createdAt,conclusion` (one line);
    - `[W] gh run view <run id> -R Starktastic-Homelab/ansible --log | grep -E 'f1-canary|lv-missing|refused'`,
      for the run that expired `f1-canary`;
    - `[S] vgs --readonly --noheadings -o vg_name,vg_tags regen retained`;
    - `[S] lvs --readonly --noheadings -o vg_name,lv_name`;
    - `[W] gh run list -R Starktastic-Homelab/ansible --workflow storage.yml --limit 3 --json conclusion` (one line).
  - Expected:
    - the expiry run is `success`;
    - `regen` carries `tombstone:f1-canary` and no `ledger:f1-canary:*` tag;
    - no LV `f1-canary`, and no `lv-missing` line;
    - the last three `storage.yml` runs are `success`;
    - `evidence/3.10/facts.md` has V1 and V2 `PASS`, or Ben's recorded decision on each FAIL (Task 3.10 Step 10).
      Record both as `drill_verdicts`. With neither, stop before any cutover.
  - If not, stop. Follow the F3 runbook (`docs/runbooks/storage-vm-crashed-create.md`, "lv-missing after a failed
    expiry") and the expiry runbook (`storage-vm-expiry.md`) first, then repeat this step.
- [ ] **Step 2: Re-check the backup gate.** Re-run Part 1 Task 1.1's three backup and pstore rows.
  - Expected: 7 `Added to the repository` lines on distinct days, no `PROBLEM` line, and an empty pstore. Otherwise
    stop; no cutover starts.
- [ ] **Step 3: Delete the retired images** (one **Ben OK** per image).
  - For each name in `evidence/1.1/facts.md` `retired_images_present` (a subset of
    `vm-9999-{grafana,prowlarr,bazarr,seerr,seerr-ru,cineplete,cleanuparr,ntfy,pgadmin,changedetection-data}.raw`,
    proxmox-csi `README.md:63-64`), first read:
    - `[K] get pv -o jsonpath='{range .items[*]}{.spec.csi.volumeHandle}{"\n"}{end}'`;
    - `[P] grep -l 'vm-9999-<name>.raw' /etc/pve/qemu-server/*.conf`;
    - `[P] pvesm list k3s-block --vmid 9999`.
  - Expected: no PV handle and no VM config names the image, and `pvesm list` shows its size.
  - Then show Ben the image name, its size, and that the deletion cannot be undone. On **Ben OK**:
    `[P] pvesm free k3s-block:9999/vm-9999-<name>.raw`.
  - Expected: `pvesm list` no longer shows it.
  - Space comes back only after the snapshots expire: 1 week on TrueNAS and 2 weeks on `usbbk` (ADR `:726-729`). Do
    this step at least a week before wave 5 (Jellyfin, 64 GiB). Record the date in `facts.md`.
- [ ] **Step 4: Fix the capacity rule** (D20; ADR `:715-719`). Write it into `facts.md` as `capacity_rule`. Task 4.T
  Step 1 applies it.
  - `N` = the source's full length in bytes (binding capacity: `GiB * 2^30`). `M` = `<D20:margin_gib> * 2^30`.
  - Pass when all of these hold:
    1. `[T] zfs get -Hp available apps/k3s-block` is at least `N + M`;
    2. `[P] zfs get -Hp available usbbk` is at least `N + M`. This is the ADR's "matching space"; the quantity is
       this plan's reading;
    3. the storage VM's `storage_vg_free_bytes{vg="<vg>"}` is at least the inventory size;
    4. `StorageDatasetLow` is not firing.
  - The first cutover (tempo) measures the dataset's `used` change (4.T Step 5). Until then the rule gates on the full
    length. Ben pre-approved the switch (2026-11-23; `apps/k3s-block` has lz4, so zeros should become holes): when
    tempo's delta is well below tempo's `N` (at most half), record `capacity_rule: allocated` in `facts.md`, and from
    the next cutover on `N` = the source image's allocated bytes, `[P] du -B1 <source raw path>`, read just before the
    copy. A delta above half keeps the full length, and the quota question goes back to Ben.
- [ ] **Step 5: Fix the freeze checks** (Global Constraints, freeze rule; Review Focus 5). Write them into `facts.md`
  as `freeze_checks`. Task 4.T Step 2 runs them.
  - `[W] for r in packer terraform ansible; do gh pr list -R Starktastic-Homelab/$r --state open
    --json number,title,autoMergeRequest --jq '.[] | select(.autoMergeRequest != null) | .number'; done` (one line).
    Expected: no output.
  - `[W] gh run list -R Starktastic-Homelab/packer --workflow build.yml --limit 5 --json status`, and the same for
    terraform `apply.yml` and ansible `deploy.yml`. Expected: no `queued`, `in_progress`, `waiting`, `requested` or
    `pending` run.
  - `[W] gh pr list -R Starktastic-Homelab/apps --state open --json number,title,autoMergeRequest,files
    --jq '.[] | select(.autoMergeRequest != null) | select(any(.files[]; .path | startswith("<app dir>/"))) |
    .number'` (one line). Expected: no output. apps `renovate.json` has `platformAutomerge: true` (`:6`) and
    `automerge: true` (`:9`). If a PR is listed, on **Ben OK** run
    `gh pr merge <n> -R Starktastic-Homelab/apps --disable-auto`. Re-enable it at Task 4.T Step 10.4.
  - Open drift and Debian-ISO PRs do not block, but they are not merged while a cutover runs.
- [ ] **Step 6: Re-confirm the settled facts m7 and m8** (read-only).
  - m7 (Task 2.5):
    - `[K] get csidriver csi.proxmox.sinextra.dev -o jsonpath='{.spec.attachRequired} {.spec.volumeLifecycleModes}'`;
    - `[K] -n csi-proxmox get ds,deploy -o jsonpath='{range .items[*]}{.metadata.name}
      {.spec.template.spec.containers[*].image}{"\n"}{end}'`
      (one line; namespace from `infrastructure/system/proxmox-csi/app.yaml:2`).
    - Expected: `true [Persistent]` and image tags `v0.22.x`.
  - m8 (Task 2.6):
    - `[K] -n monitoring get deploy -o jsonpath='{range .items[*]}{.metadata.name}
      {.spec.template.spec.containers[0].image}{"\n"}{end}'`.
    - Expected: the operator image is `v0.95.2`.
  - Any other value: STOP and bring it to Ben. The copy design rests on these.
- [ ] **Step 7: Settle the tool host (a decision for Ben; it blocks the first cutover).**
  - Task 2.5's `migrate_volume.py` needs three things in one place:
    - `kubectl` with read access to pods, PVs, PVCs, VolumeAttachments, Jobs, CronJobs, Deployments and
      StatefulSets in every namespace;
    - `gh`, authenticated, reading runs and PRs;
    - the lock root `/var/lib/homelab-maintenance` (its default).
  - The facts on record:
    - the runner user has no kubectl (memory `backup-review-live-access`), and the root case is UNVERIFIED;
    - only the masters have `k3s kubectl`, and they have neither `gh` nor the lock root;
    - the lock root lives on VM300.
  - Run (read-only):
    `[R] command -v kubectl gh python3; ls -l /var/lib/homelab-maintenance/runner-instance`.
  - Expected: three paths and the file.
  - If `kubectl` or `gh` is missing, stop and ask Ben the one D23 question. Recommendation: Ben installs pinned
    `kubectl` and `gh` for root on VM300, with a root-only kubeconfig for a dedicated ServiceAccount (read on pods,
    PVs, PVCs, VolumeAttachments, Jobs, CronJobs, Deployments and StatefulSets cluster-wide, plus `create` and
    `delete` on PVs, PVCs, Jobs and ConfigMaps). The SA and its RBAC ship in an apps PR (**Ben OK**); Ben mints the
    token and writes the kubeconfig. This is D23's recommendation. D23's alternatives: (a) the `KUBECONFIG_RAW`
    target file instead of the ServiceAccount kubeconfig; (b) cluster steps through `qm guest exec` on a master,
    GitHub steps from the workstation. Claude never reads the kubeconfig or the `gh` token. Do not improvise a
    transport.
  - Then (the clone rule below, once):
    - `[TOOL] git -C <apps clone> fetch origin && git -C <apps clone> checkout --detach origin/main
      && git -C <apps clone> rev-parse HEAD && git -C <apps clone> status --porcelain`;
    - `[TOOL] cd <apps clone> && python3 scripts/storage/migrate_volume.py --help`.
  - Expected: the three subcommands, a HEAD at or after the Task 3.6 merge, and a clean work tree. Record `tool_host`
    and the clone path.
- [ ] **Step 8: Fix the syncWindow form** (read-only, server-side dry run).
  - The hold was qualified on Argo CD 3.5.3 (hold report `2026-10-12-native-argo-migration-hold-qualification.md:1-21`,
    which also covers blocked self-heal drift) and used on 3.6.1 (Immich, scout-precedent §1 Form B). Compare
    `argocd_version` from `evidence/1.1/facts.md`. A newer minor is acceptable only if the step below passes.
  - `[K] -n argocd get appproject default -o json`. Record `.metadata.uid`, `.metadata.resourceVersion`,
    `.metadata.ownerReferences`, `.metadata.annotations` and `.spec.syncWindows`.
    - Expected: no ownerReferences and no `argocd.argoproj.io/tracking-id` annotation (spec
      `2026-10-10-live-storage-migrations-design.md:42-47`).
    - Expected: no apps file declares the project: `[W] git -C <apps> grep -l "kind: AppProject" origin/main` is
      empty.
  - Dry-run Form A, with the add guarded by the resourceVersion. The patch for an absent `.spec.syncWindows` is
    `[K] -n argocd patch appproject default --type json --dry-run=server -o json -p
    '[{"op":"test","path":"/metadata/resourceVersion","value":"<rv>"},{"op":"add","path":"/spec/syncWindows",
    "value":[{"kind":"deny","schedule":"* * * * *","duration":"24h","timeZone":"UTC","applications":["tempo"],
    "manualSync":false,"syncOverrun":false,"description":"storage-cutover:dry-run"}]}]'`. When the field exists, the
    path is `/spec/syncWindows/-` and the value is the window object alone.
  - Expected:
    - the returned object keeps all seven window fields, `syncOverrun: false` and `description` included. A field
      that the CRD drops means the form is not supported, so stop;
    - the same command with a wrong `<rv>` is refused with a `test operation` error.
  - Write `syncwindow_form` into `facts.md`: the two add forms, and the guarded remove of Task 4.T Step 8.
- [ ] **Step 9: Stage the pinned lock helper on VM300** (**Ben OK**: it downloads one file from the ansible repo).
  - `[W] git -C ~/.cache/claude-homelab-live/worktrees/ansible-storage-vm show
    887269798650e88fed791bb4f22a47bf50ad17be:scripts/maintenance_lock.py | sha256sum`.
  - `[R] install -d -m 0700 /run/homelab-cutover && curl -fsSL -o /run/homelab-cutover/maintenance_lock.py
    https://raw.githubusercontent.com/Starktastic-Homelab/ansible/887269798650e88fed791bb4f22a47bf50ad17be/scripts/maintenance_lock.py
    && sha256sum /run/homelab-cutover/maintenance_lock.py` (one row).
  - Expected: the two hashes match. Record `lock_helper_sha256`.
  - Probe the expansion: `[R] echo $(hostname)`. Expected: one host name. Record
    `qga_dollar_expanded_by_pve: yes` if it is pve's name, `no` if it is VM300's. The intro rule holds either way.
  - Stage `lock.sh` (**Ben OK**). Write it on the workstation as
    `evidence/4.0/lock.sh`, then send it as `[R] echo <base64 of lock.sh> | base64 -d > /run/homelab-cutover/lock.sh
    && chmod 0700 /run/homelab-cutover/lock.sh && sha256sum /run/homelab-cutover/lock.sh`. Base64 carries no `$`.

    ```sh
    #!/bin/sh
    # usage: lock.sh acquire|release <op-suffix> <owner>; the nonce never leaves this host.
    set -eu
    cd /run/homelab-cutover
    root=/var/lib/homelab-maintenance
    HOMELAB_RUNNER_INSTANCE="$(cat "$root/runner-instance")"; MAINTENANCE_OWNER="$3"
    export HOMELAB_RUNNER_INSTANCE MAINTENANCE_OWNER
    case "$1" in
      acquire)
        test ! -e "$root/operation.json"
        umask 077
        python3 maintenance_lock.py acquire --root "$root" --operation "storage-cutover:$2" > "$2.nonce"
        python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["operation"],d["owner"],d["created_at"])' \
          "$root/operation.json" ;;
      release)
        MAINTENANCE_NONCE="$(cat "$2.nonce")" python3 maintenance_lock.py release --root "$root"
        rm -f "$2.nonce"
        test ! -e "$root/operation.json" && echo released ;;
      *) echo "usage: lock.sh acquire|release <op-suffix> <owner>" >&2; exit 2 ;;
    esac
    ```

    Expected: the hash matches the workstation copy's. Record it as `lock_sh_sha256`.
  - Stage `watch.sh` on the `[K]` master the same way (**Ben OK**), as `/run/homelab-cutover/watch.sh`:

    ```sh
    #!/bin/sh
    # usage: watch.sh <app> <ns> <selector>; 60 samples, 15 s apart (6 min).
    for i in $(seq 1 60); do
      date -u +%T
      k3s kubectl -n argocd get application "$1" \
        -o jsonpath='{.status.sync.status} {.status.health.status} {.status.sync.revisions}{"\n"}'
      f='{range .items[*]}{.metadata.name} {.status.phase} {.status.containerStatuses[*].restartCount}'
      f="$f"' {.spec.volumes[*].persistentVolumeClaim.claimName} {.spec.containers[*].image}{"\n"}{end}'
      k3s kubectl -n "$2" get pods -l "$3" -o jsonpath="$f"
      sleep 15
    done
    ```

    Expected: the hash matches the workstation copy's. Record it as `watch_sh_sha256`. Both scripts live on tmpfs:
    redo this after a reboot of either host, and re-stage `watch.sh` if the first Ready master changes. Both scripts
    are `(not rehearsed)`; `sh -n` passes on both.
  - `/run` is tmpfs. A VM300 reboot loses the helper and every nonce file under it; redo this step after one, and see
    "Stale lock" in `docs/runbooks/storage-vm-cutover.md` for a lock whose nonce was lost.
- [ ] **Step 10: Build the per-id gate coverage list** (D37; offline, before the first cutover). 4.T R2 copies a volume
  back only through Task 2.5's source gate, so an id the gate cannot run on has no reverse copy.
  - The read-only mount: look in `evidence/3.6/` for D37's one-time canary proof of the gate's `ro,noload` mount.
    Record `gate_ro_mount_proven: yes` with its source file, or `no`. `no` is a stop before the first cutover: D37
    wants the proof before R2 can be needed (from the first Step 8.2), and the canary is gone after Task 3.8's
    expiry. Bring it to Ben.
  - Per 4.W row, read the writer and guard named in its "Style, values, writer and guard" notes:
    `[W] git -C <apps> show origin/main:<values file>` (the operator CR's `initContainers` for notes (a) and (b), the
    Bitnami `<root>.initContainers` for wave 6). Against the gate rule, check that:
    1. exactly one pod template will reference `<new_claim>` (for D14 pairs, one shared template for both ids);
    2. exactly one init container mounts the claim's volume, and it is the row's guard;
    3. that init container mounts no other PVC.
  - Write `gate_coverage` into `facts.md`: one line per id, `covered` or `none: <failed condition>`. These are git
    values (UNVERIFIED for operator-built and chart-built templates); R2's entry check confirms them live with pass 1.
  - For each `none` id, show Ben the reason and that a rollback after writes then has no reverse copy (only R1 and
    R1b). On **Ben OK** per id, record `none accepted <date>`. An id that is `none` without that line does not start
    its cutover.
- [ ] **Step 11: Write `evidence/4.0/facts.md`**, one line per produced fact with its source row. Any failed
  Expected is a stop for every cutover.

### Task 4.T: The cutover task (parametrised by volume)

Run this once per 4.W row, in 4.W order, after Task 4.0. A D14 pair (karakeep, home-assistant) runs it once with two
ids: one hold, two copy Jobs one after the other, and the deltas listed in 4.W. Wave 6 replaces Steps 3.4-3.8 and 8.2
with the Git hold and its release PRs (4.W, wave 6).

**Clone rule.** `precheck`, `render` and `verify-teardown` read the inventory and binding files from the tool host's
apps clone, so before each of them (in 4.T and in R1-R3) run
`[TOOL] git -C <apps clone> fetch origin && git -C <apps clone> checkout --detach origin/main && git -C <apps clone>
rev-parse HEAD && git -C <apps clone> status --porcelain`, then `[TOOL] git -C <apps clone> merge-base --is-ancestor
<merge sha> HEAD`. `<merge sha>` is that of the cutover's latest merged PR (inventory, switch, reconciliation or an R3
revert), read with `[W] gh pr view <n> -R Starktastic-Homelab/apps --json mergeCommit`. Expected: a clean work tree and
exit 0. Record HEAD in `<ev>/clone-head.txt`. A mismatch
is a stop: fetch again after the merge, never run the tool on a stale tree.

**Files** (apps, a fresh worktree off `origin/main` per PR; ids from 4.W):
- Inventory PR, branch `storage/inventory-<id>`. Modify `infrastructure/base-configs/files/retained-volumes.json`
  (add the entry).
- Switch PR, branch `storage/switch-<id>`:
  - Modify the values file and key named in the 4.W row;
  - Modify `infrastructure/base-configs/files/retained-volumes.json` (`copied`).
- Reconciliation PR, branch `storage/reconcile-<id>`. Modify or delete the 4.W row's binding file. Remove only that
  volume's PV and PVC documents. Never touch `templates/retained-startup-guard.yaml`: it carries no `Prune=false`,
  and every hand-wired guard, NFS ones included, still mounts its ConfigMap (D47; the old `guard-*.yaml` files went
  in apps#1707).
- Evidence: `evidence/4.T-<id>/`.

**Interfaces:**
- Consumes:
  - the 4.W row: `<id>`, `<ns>`, `<app>` (the Argo Application), `<old_claim>`, `<old_pv>`, `<new_claim>`,
    `<size>`, `<bytes>` (`<size>` in bytes), `<class>` (`retained` or `regenerable`), `<vg>` (`retained` or `regen`),
    `<style>`, `<values_key>`, `<writer>`, `<selector>` (the writer's pod label selector, 4.W rules), `<hold>`,
    `<binding_file>`;
  - Task 2.5:
    - `migrate_volume.py precheck <id> [--direction forward|reverse]`;
    - `migrate_volume.py render <id> --direction forward|reverse --out <dir>`;
    - `migrate_volume.py verify-teardown <id>`;
    - the objects `migrate-src-<id>`, `migrate-dst-<id>` and Job `migrate-<id>`, labelled
      `homelab.starktastic.net/migration=<id>`;
    - the log line `copy-ok <direction> <S> <T>`;
    - the reverse source gate (R2): `render <id> --direction reverse` in two passes on one `--out` dir. Pass 1
      prints `gate-required` and writes `gate.yaml` (ConfigMap `migrate-<id>`, PV/PVC/Job `migrate-gate-<id>` and
      `migrate-guard-<id>`) and `render.json`; pass 2 reads `<dir>/gate.log` and writes `pairs.yaml` and
      `job.yaml`;
    - the log lines `gate-fsck-ok <id>` and `gate-guard-ok <id>`, `apps_head` in `render.json`, and the refusals
      `stale-clone` and `gate`;
  - Task 2.6: the `copied` field, `check_bindings`, and the per-style switch;
  - Task 2.2: the workflow `storage.yml` (operation `ansible-storage`), and the reconcile report's `actions` and
    `refusals`;
  - Task 2.4: `storage_target_missing{id}`, `storage_vg_free_bytes{vg}`, `StorageDatasetLow`;
  - Task 4.0: `capacity_rule`, `freeze_checks`, `syncwindow_form`, `tool_host`, `gate_ro_mount_proven`,
    `gate_coverage` (D37), and the helper in `/run/homelab-cutover/`.
- Produces:
  - the maintenance lock operation `storage-cutover:<id>` (`storage-cutover:<id1>:<id2>` for a D14 pair), owner
    `claude-code/storage-cutover-<id>/<UTC ts>`;
  - the deny window with `description` `storage-cutover:<id>`;
  - the evidence set above.

**Merge events in this task** (each needs **Ben OK**, merged with `gh pr merge <n> -R Starktastic-Homelab/apps
--squash --match-head-commit <full 40-char SHA>`, after `git merge-tree --write-tree origin/main <head>` shows only
this task's files; memory `pr-merge-mechanics`):
- Inventory PR:
  - ArgoCD syncs `base-configs`, which renders PV `<id>` and PVC `<ns>/<new_claim>`;
  - `refresh.yaml` refreshes `base-configs`;
  - `storage-dispatch.yaml` sends `storage-changed`, and ansible `storage.yml` creates the raw LV and its target. That
    is a storage VM mutation.
- Switch PR: the held app goes OutOfSync. The deny window blocks its sync, and `base-configs` renders nothing new
  (`test_copied_does_not_change_render`). The dispatch fires again, and `storage.yml` exits 0 with the lock-held
  warning.
- Reconciliation PR: ArgoCD syncs `base-configs`. The old PV and PVC stay live, because of `Prune=false`.

- [ ] **Step 1: Capacity gate** (read-only).
  - Run the four `capacity_rule` reads (Task 4.0 Step 4) for `<bytes>` and `<vg>`.
  - Also run `[T] zfs get -Hp used,usedbydataset,usedbysnapshots apps/k3s-block` and save it as the "before" line in
    `capacity.txt`.
  - Also run `[P] pvesm list k3s-block --vmid 9999` and save it in `capacity.txt`.
  - Expected: all four pass, and the size of `vm-9999-<id>.raw` equals `<bytes>` exactly (D26: a smaller image makes
    the Job run `resize2fs`, a larger one makes it refuse mid-outage). If one fails, stop before Step 2. The growth
    runbook (`storage-vm-growth.md`, "Dataset full") and Ben's call come first.
- [ ] **Step 2: Inventory PR, the raw LV, then the lock.**
  1. Run `freeze_checks` (Task 4.0 Step 5). Expected: all empty. From here until Step 10.3 releases the lock (after
     the Step 9 reconciliation PR has merged and `base-configs` is `Synced Healthy`), nothing merges in packer,
     terraform or ansible, and no drift or Debian-ISO PR is merged (Global Constraints freeze rule; ADR `:984`). An
     ansible merge would restart k3s on every node.
  2. `[W]` In a worktree of apps `origin/main`, add this entry to `retained-volumes.json` (keep the array order):
     `{"id": "<id>", "namespace": "<ns>", "claim": "<new_claim>", "size": "<size>", "class": "<class>",
     "origin": "migrated"}`. `<new_claim>` must be `<id>-iscsi`, or `<id>-iscsi-<sts>-0` for the two
     kube-prometheus-stack StatefulSets; apps CI refuses any other name (claim rule, 2026-11-25).
  3. Run: `python3 scripts/check-retained-inventory.py --base origin/main --override-label storage-removals-approved
     && python3 -m unittest discover -s scripts/storage/tests -v`. Expected: exit 0, and all tests `ok`.
  4. Commit: `feat(storage): add <id> to the retained inventory (ADR 0017 cutover)`.
  5. Push and open the PR (**Ben OK**): `git push -u origin storage/inventory-<id>`, then `gh pr create -R
     Starktastic-Homelab/apps`. The body states the merge events above and ends with the Claude Code line.
  6. Merge (**Ben OK**, window check first).
  7. Wait for the LV:
     - `[W] gh run list -R Starktastic-Homelab/ansible --workflow storage.yml --limit 3
       --json databaseId,event,createdAt,conclusion` (one line).
     - Expected: a `repository_dispatch` run created after the merge, `success`. If none appears within 10 min
       (dispatch not wired, Task 2.4), then on **Ben OK** run
       `gh workflow run storage.yml -R Starktastic-Homelab/ansible`.
     - `[W] gh run view <run id> -R Starktastic-Homelab/ansible --log | grep -E '"create_raw"|refused:|error:'`.
       Expected: one `create_raw` action for `<id>` in VG `<vg>`, and no `refused:` or `error:` line. The exact log
       format is UNVERIFIED until the first run.
     - `[S] lvs --readonly --noheadings -o lv_name,lv_size --units b <vg>/<id>`. Expected: `<id>` and `<bytes>B`.
     - `[K] get pv <id> -o jsonpath='{.spec.csi.driver} {.status.phase} {.spec.claimRef.name}'`. Expected:
       `org.democratic-csi.node-manual Bound <new_claim>`.
     - Prometheus `storage_target_missing{id="<id>"}`, through the API proxy (memory `backup-review-live-access`).
       Expected: `0`. During the prometheus cutover itself, use the `[S]` read only.
  8. Take the maintenance lock (**Ben OK**), with the staged script (Task 4.0 Step 9), in one row:
     `[R] sh /run/homelab-cutover/lock.sh acquire <id> claude-code/storage-cutover-<id>/<ts>`. For a D14 pair, the
     second argument is `<id1>:<id2>`. The script refuses if `operation.json` already exists.
     Expected: `storage-cutover:<id> claude-code/storage-cutover-<id>/<ts> <time>`. The nonce stays in the root-only
     file and is never printed. Write the owner into `facts.md`.
  9. Re-run `freeze_checks`. Expected: all empty.
- [ ] **Step 3: Hold** (deny window, writer inventory, scale to 0).
  1. Read the project: `[K] -n argocd get appproject default -o json > appproject-before.json`. Record `uid`,
     `resourceVersion` and `.spec.syncWindows`. Ownership must be as in Task 4.0 Step 8.
  2. Check that the app is idle:
     `[K] -n argocd get application <app> -o jsonpath='{.status.sync.status} {.status.health.status}
     {.status.operationState.phase} {.operation}'` (one line). Expected: `Synced Healthy Succeeded`, and no
     `.operation`. Otherwise stop: an operation must be resolved before the hold (spec
     `2026-10-10-live-storage-migrations-design.md:63-65`).
  3. Record the writer baseline (image and replicas) and fix `<selector>`:
     - app-template rows: `[K] -n <ns> get deploy -l app.kubernetes.io/instance=<app> -o jsonpath='{range .items[*]}
       {.metadata.name} {.spec.replicas} {.spec.template.spec.containers[*].image}{"\n"}{end}'`. `<selector>` is
       `app.kubernetes.io/instance=<app>`;
     - StatefulSet rows: `[K] -n <ns> get sts <writer> -o jsonpath='{.spec.replicas} {.spec.selector.matchLabels}
       {.spec.template.spec.containers[*].image}'`. `<selector>` is the `matchLabels`, joined as `k=v,k=v`;
     - operator CR rows: replicas from `[K] -n monitoring get <prometheus|alertmanager> <cr> -o
       jsonpath='{.spec.replicas}'`; the CR has no pod selector, so `<selector>` comes from the `matchLabels` of
       the operator's StatefulSet, read as for StatefulSet rows.

     Expected: exactly the 4.W writer. Its name is UNVERIFIED until this read. Write `<selector>` into `facts.md`.
  4. Add the window (**Ben OK**), with the `syncwindow_form` add that matches the state read in 3.1:
     `[K] -n argocd patch appproject default --type json -p '[{"op":"test","path":"/metadata/resourceVersion",
     "value":"<rv>"},{"op":"add","path":"/spec/syncWindows/-","value":{"kind":"deny","schedule":"* * * * *",
     "duration":"24h","timeZone":"UTC","applications":["<app>"],"manualSync":false,"syncOverrun":false,
     "description":"storage-cutover:<id>"}}]'`.
     When `.spec.syncWindows` is absent, the op is `add` `/spec/syncWindows` with a one-element array.
     Expected: `patched`. A `test` failure means the project changed: re-read and retry once; a second failure is a
     stop.
  5. Read it back: `[K] -n argocd get appproject default -o jsonpath='{range .spec.syncWindows[*]}{.description}|
     {.kind}|{.schedule}|{.duration}|{.timeZone}|{.applications}|{.manualSync}|{.syncOverrun}{"\n"}{end}'`.
     Expected:
     - the windows from 3.1, unchanged;
     - plus exactly one `storage-cutover:<id>|deny|* * * * *|24h|UTC|["<app>"]|false|false`.

     Record its index `<i>`.
  6. Re-check the app. Expected: still no `.operation`, and `operationState` unchanged (spec `:71-73`).
  7. Writer inventory into `writers.txt` (read-only):
     - `[K] get pods -A -o json`, filtered for any pod whose `.spec.volumes[].persistentVolumeClaim.claimName` is
       `<old_claim>` in `<ns>`;
     - `[K] get cronjobs,jobs -A -o json`, filtered the same way;
     - `[K] get volumeattachments -o jsonpath='{range .items[*]}{.metadata.name} {.spec.source.persistentVolumeName}
       {.spec.nodeName}{"\n"}{end}'`;
     - `[P] for v in <worker vmids from pvesh tags k3s;worker>; do echo $v; qm config $v | grep -n
       'vm-9999-<id>.raw'; done` (worker VMIDs pasted as literals).

     Expected: the one 4.W writer pod, and one VA on `<old_pv>` on its node. A second writer is a stop.
  8. Scale to 0 (**Ben OK**), by `<hold>`:
     - Deployment: `[K] -n <ns> scale deploy -l app.kubernetes.io/instance=<app>,app.kubernetes.io/controller=main
       --replicas=0`;
     - StatefulSet: `[K] -n <ns> scale sts <writer> --replicas=0`;
     - operator CR: `[K] -n monitoring patch <prometheus|alertmanager> <cr> --type merge -p
       '{"spec":{"replicas":0}}'`. The operator scales its StatefulSet; do not scale the StatefulSet by hand;
     - plus any extra hold the 4.W row names (a CronJob `suspend`, a second container of the same pod).

     The window keeps Argo self-heal from undoing these (hold report `:17-18`).
  9. Wait for a cold source. Poll every 15 s for up to 10 min:
     - `[K] -n <ns> get pods -o json` shows no pod on `<old_claim>`;
     - no VA names `<old_pv>`;
     - the `qm config` grep from 3.7 prints nothing for any worker.

     Expected: all three. Then run `[TOOL] cd <apps clone> && python3 scripts/storage/migrate_volume.py precheck <id>`.
     Expected: exit 0. Any `refused:` line is a stop. Never force-detach.
- [ ] **Step 4: Copy Job** (Task 2.5).
  1. `[TOOL] install -d -m 0700 <td>/render && cd <apps clone> && python3 scripts/storage/migrate_volume.py render <id>
     --direction forward --out <td>/render`. Then copy back: `[TOOL] cat <td>/render/pairs.yaml`, `job.yaml` and
     `render.json`, one row each, with the helper output saved as `<ev>/render/<file>`.
     Expected: `pairs.yaml`, `job.yaml` and `render.json`. `render.json` shows the binding handle
     `homelab//k3s-block/9999/vm-9999-<id>.raw`, the target handle `<id>`, the source capacity `<bytes>`, and the
     target size `<bytes>` (4.W keeps every size equal to its binding capacity).
  2. Apply the pairs (**Ben OK**): `[TOOL] kubectl apply -f <td>/render/pairs.yaml`.
     Expected: both PVCs `Bound`, read with `[K] -n <ns> get pvc migrate-src-<id> migrate-dst-<id>
     -o jsonpath='{range .items[*]}{.metadata.name} {.status.phase}{"\n"}{end}'`.
  3. Re-run precheck. Expected: exit 0.
  4. Apply the Job (**Ben OK**, window check first): `[TOOL] kubectl apply -f <td>/render/job.yaml`.
  5. Poll every 60 s: `[K] -n <ns> get job migrate-<id> -o jsonpath='{.status.succeeded} {.status.failed}'`.
     Expected: `1` and no `failed` before `activeDeadlineSeconds: 14400`. If the Job fails, keep the hold and the lock,
     save the log, and stop. The source was only read.
  6. Save the log: `[K] -n <ns> logs job/migrate-<id> > <ev>/copy.log`. Save the Job's pod node too.
- [ ] **Step 5: Verify** (read-only).
  - `copy.log` holds:
    - `copy-ok forward <bytes> <bytes>`;
    - an `e2fsck -fp` exit of 0;
    - the three `dumpe2fs -h` matches (`mmp`, `Remount read-only`, `MMP update interval: 5`);
    - no `resize2fs` line.

    `e2fsck` exit 1 (fixed) is Ben's call, not a pass.
  - The Job pod is `Succeeded`, and no VA names `migrate-src-<id>`, `migrate-dst-<id>`, `<old_pv>` or `<id>`.
  - `[TOOL] cd <apps clone> && python3 scripts/storage/migrate_volume.py precheck <id>`. Expected: exit 0 again, so no
    writer appeared during the copy.
  - `[T] zfs get -Hp used,usedbydataset,usedbysnapshots apps/k3s-block`: write it as the "after" line in
    `capacity.txt`, with the delta.
    - On the first cutover (tempo) this is D20's measurement: hand Ben the delta against `<bytes>`.
    - A delta of at most half of `<bytes>` means zeros became holes: switch `capacity_rule` to `allocated` (Task 4.0
      Step 4, pre-approved by Ben 2026-11-23) and tell Ben the numbers. Otherwise stop and bring them to Ben.
  - Record the verify date as `<copied>` (UTC, `YYYY-MM-DD`) in `facts.md`.
- [ ] **Step 6: Switch PR** (Task 2.6; sets `copied` and switches the binding in one PR).
  1. `[W]` In a worktree off apps `origin/main`, make the 4.W row's edit:
     - `existingClaim` and `claimName` styles: `<old_claim>` becomes `<new_claim>`;
     - kps style: the template name becomes `<id>-iscsi`, `volumeName` becomes `<id>`, and `storageClassName` becomes
       `""`, and the guard's `volumeMounts[].name` becomes `<id>-iscsi` (2.6);
     - add `"copied": "<copied>"` to the entry.

     Change nothing else. No image bump rides along (scout-precedent §8, the Renovate `sha:` trap).
  2. Run: `python3 scripts/check-retained-inventory.py --base origin/main --override-label storage-removals-approved
     && python3 -m unittest discover -s scripts/storage/tests -v`. Expected: exit 0. `check_bindings` passes, because
     `copied` is set and the guard mounts the new claim.
  3. Commit: `feat(storage): switch <id> to the storage VM (ADR 0017 cutover)`.
  4. Push and open the PR (**Ben OK**). The body says it merges under the hold and names Step 8's watch.
  5. `[W] gh pr checks <n> -R Starktastic-Homelab/apps`. Expected: all pass. Read the argocd-diff-preview comment:
     only `<app>` changes, plus `base-configs` with no rendered diff.
- [ ] **Step 7: Merge the switch PR under the hold.** (The outline's step list skips 7; this is the gap between the
  switch and the release.)
  1. Merge (**Ben OK**). Record the merge SHA as `<sha>`.
  2. After the refresh, read `[K] -n argocd get application <app> -o jsonpath='{.status.sync.status}
     {.status.sync.revisions} {.status.operationState.phase} {.status.operationState.operation.sync.revisions}
     {.operation}'` (one line). Expected:
     - `OutOfSync` at `<sha>`;
     - the live writer is still at 0;
     - no `Running` operation pinned to a revision before `<sha>`.
  3. A queued operation:
     - If one exists, or an operation pins an older revision, do not lift the window. A stale sync would start the app
       on `<old_claim>`, and the old image would then take writes that the target does not have.
     - Capture first: `[K] -n argocd get application <app> -o json`, saved as `<ev>/op-before.json`. Record `<uid>`,
       `<rv>`, `<op>` (the full `.operation`) and `<state>` (the full `.status.operationState`), pasted as literals.
     - Retire it with the qualified patch (hold report `:24-28`). This needs **Ben OK**, with `<op>` shown to him
       first:
       `[K] -n argocd patch application <app> --type json -p '[{"op":"test","path":"/metadata/uid","value":"<uid>"},
       {"op":"test","path":"/metadata/resourceVersion","value":"<rv>"},{"op":"test","path":"/operation","value":<op>},
       {"op":"test","path":"/status/operationState","value":<state>},{"op":"remove","path":"/operation"},
       {"op":"replace","path":"/status/operationState/phase","value":"Failed"},
       {"op":"add","path":"/status/operationState/finishedAt","value":"<now-utc>"}]'`
       (`<now-utc>` as `date -u +%Y-%m-%dT%H:%M:%SZ`). Expected: `patched`; a refresh then shows no `.operation`,
       no resurrected old operation, and comparedTo at `<sha>`. A `test` failure is a stop: no second
       request (hold report `:66`).
     - An operation that cannot be classified is a stop (hold report `:63-66`).
  4. Rollback point R1 (before writes): if anything is wrong now, revert the switch PR under the hold (see Rollback).
- [ ] **Step 8: Lift the hold, native checks, and the 6-minute watch.**
  1. Start the watch before the release (**Ben OK**: it starts a transient unit on the master):
     `[K-host] systemd-run --unit=cutover-watch-<id> -p RemainAfterExit=yes
     -p StandardOutput=file:/run/cutover-watch-<id>.log sh /run/homelab-cutover/watch.sh <app> <ns> <selector>`
     (one row). For the R1, R1b and R2 watches, the expected claim is `<old_claim>`.
  2. Remove only the owned window (**Ben OK**). First re-read the project: record `<rv2>`, and check that index `<i>`
     still holds `storage-cutover:<id>`. Then:
     `[K] -n argocd patch appproject default --type json -p '[{"op":"test","path":"/metadata/resourceVersion",
     "value":"<rv2>"},{"op":"test","path":"/spec/syncWindows/<i>/description","value":"storage-cutover:<id>"},
     {"op":"test","path":"/spec/syncWindows/<i>/applications","value":["<app>"]},
     {"op":"remove","path":"/spec/syncWindows/<i>"}]'`.
     Expected: `patched`. The read-back shows the windows from Step 3.1 only.
  3. If nothing syncs within about 5 min:
     - RollingSync does not sync later steps while any app is unhealthy (scout-precedent §1). First confirm that
       `.status.operationState.phase` is not `Running`.
     - Then, on **Ben OK**, start one sync:
       `[K] -n argocd patch application <app> --type merge -p '{"operation":{"initiatedBy":{"username":
       "storage-cutover-<id>"},"sync":{"revisions":<revs>,"prune":false,"syncOptions":<opts>}}}'`. The appsets render
       multi-source apps (chart source plus the apps repo, `bootstrap/appsets/cluster-apps.yaml`), so `<revs>` is the
       full resolved `.status.sync.revisions` array from the Step 7.2 read (it contains `<sha>`), and `<opts>` is the
       app's `.spec.syncPolicy.syncOptions` (hold report `:50-56`: complete current sources, resolved revision
       arrays, prune disabled). Expected: `patched`; `.status.operationState.operation.sync.revisions` contains
       `<sha>`; phase `Running`, then `Succeeded`.
  4. Expected in `/run/cutover-watch-<id>.log`, for 6 minutes after the first Ready:
     - `Synced Healthy` at a revision list containing `<sha>`;
     - one pod, on `<new_claim>`, never on `<old_claim>`;
     - a restart count that does not grow;
     - the image from the Step 3.3 baseline.

     The first start waits about 42 s for MMP, up to about 720 s on slow storage (ADR `:258-259`).
     - A pod on `<old_claim>` at any point: scale to 0 at once (**Ben OK**), re-add the window, and stop. Both images
       may then hold writes; Ben decides.
     - Any other failed check goes to Rollback.
  5. Native checks:
     - the guard init container exited 0:
       `[K] -n <ns> get pod <pod> -o jsonpath='{range .status.initContainerStatuses[*]}{.name}
       {.state.terminated.exitCode}{"\n"}{end}'`;
     - the VA for PV `<id>` has attacher `org.democratic-csi.node-manual`;
     - `storage_target_missing{id="<id>"}` is `0`;
     - the per-class app check in 4.W.

     Save the watch log and the checks to `<ev>/watch.log`, and stop the unit:
     `[K-host] systemctl stop cutover-watch-<id>; systemctl reset-failed cutover-watch-<id>`.
  6. For the wave-6 Git hold, follow the 4.W release deltas instead of 8.2. A D14 pair runs Steps 7-8 once, on its
     one window (4.W).
- [ ] **Step 9: Reconciliation PR** (removes the old binding files; the old image is kept).
  1. `[W]` In a worktree off `origin/main`, delete the PV and PVC documents for `<old_pv>` and `<old_claim>` from
     `<binding_file>` (and its `pvc.yaml` sibling, where the row lists one). Delete the file only when it becomes
     empty.
  2. Run the Step 2.3 checks. Expected: exit 0. `check_bindings` still passes: the new claim is not a static PVC.
  3. Commit: `chore(storage): drop the Proxmox CSI binding of <id> (ADR 0017 reconciliation)`.
  4. Re-run `freeze_checks` (Task 4.0 Step 5). Expected: all empty. Then push, open the PR and merge it (**Ben OK**
     each).
  5. Read `[K] -n argocd get application base-configs -o jsonpath='{.status.sync.status} {.status.health.status}'`.
     Expected: `Synced Healthy`.
     - If `base-configs` stays `OutOfSync` only because of the now-unmanaged `<old_pv>` and `<old_claim>`: on
       **Ben OK**, run `[K] -n <ns> delete pvc <old_claim>`, and then `[K] delete pv <old_pv>`.
     - Read `[K] get pv <old_pv> -o jsonpath='{.spec.persistentVolumeReclaimPolicy}'` first. Expected: `Retain`,
       which means the delete leaves the image.
     - Afterwards, `[P] pvesm list k3s-block --vmid 9999` still lists `vm-9999-<id>.raw` at its size.
  6. A rollback after this point starts by reverting this PR (Rollback R3). The reason: `precheck` and
     `render --direction reverse` find the source in the binding file, and that file is now gone from `main`.
- [ ] **Step 10: Teardown, then release the lock** (after the watch).
  1. Delete the temporary objects (**Ben OK**). The Job's pod log is already saved.
     - `[K] -n <ns> delete job migrate-<id>`;
     - `[K] -n <ns> delete configmap migrate-<id>`;
     - `[K] -n <ns> delete pvc migrate-src-<id> migrate-dst-<id>`;
     - `[K] delete pv migrate-src-<id> migrate-dst-<id>`.

     Both PVs are `Retain`, so no data is touched.
  2. `[TOOL] cd <apps clone> && python3 scripts/storage/migrate_volume.py verify-teardown <id>`. Expected: exit 0.
  3. Release the lock (**Ben OK**), in one row:
     `[R] sh /run/homelab-cutover/lock.sh release <id> <owner>` (`<id1>:<id2>` for a pair).
     Expected: `released`. Then dispatch `storage.yml` (**Ben OK**): `[W] gh workflow run storage.yml -R
     Starktastic-Homelab/ansible --ref main`. Expected: a green run, so the switch PR's lock-held skip applies now.
  4. Re-enable any auto-merge that Step 2.1 disabled (**Ben OK**).
  5. A push deploy that failed on the held lock needs `gh run rerun --failed` now (memory `pr-merge-mechanics`). By
     the freeze rule there should be none.
  6. Write `facts.md`: the times, `<copied>`, the capacity delta, the Job node, and the PR numbers.
  7. The next cutover may start only now (Global Constraints, Serialization).

**Rollback** (ADR `:982-983`; scout-precedent §6). Never remove the inventory entry before a verified reverse copy.
- **R1, before the target takes writes** (Step 7, before the window is lifted):
  1. Revert the switch PR (**Ben OK**). Its CI passes, because `test_copied_may_be_removed`.
  2. Check that the app is `OutOfSync` towards `<old_claim>`.
  3. Lift the window as in Step 8, and run the watch with `<old_claim>` as the expected claim.
  4. Tear down as in Step 10.
  5. The entry and its LV stay, holding a copy no app has written. Retry the cutover later; removing the entry
     without a reverse copy needs an ADR exception (ADR `:982-983`), so it is not offered here.
     - Retry: run Step 1 again (a new "before" line), then Step 2.1. The entry is already on `main` without
       `copied`, so skip Steps 2.2-2.7 (no new inventory PR; a duplicate id fails CI). Instead check that
       `[S] lvs --readonly --noheadings -o lv_name,lv_size --units b <vg>/<id>` shows `<bytes>B`, that
       `[K] get pv <id>` is `Bound <new_claim>`, and that `storage_target_missing{id="<id>"}` is 0. Then continue at
       Step 2.8. The new forward copy in Steps 4-5 overwrites the earlier copy on the LV.
- **Which rollback.** The split is whether the target took app writes (ADR `:982-983`), not the step number. R2
  applies only if `<ev>/watch.log` and the Step 8.5 output show both that the guard init container exited 0 and that
  the main container went Ready on `<new_claim>`. If not (the guard refused, the pod stuck in init, or no pod
  started), use **R1b**, never a reverse copy. If the guard exited 0 and the main container started but never went
  Ready, it may have written (migrations): stop, re-hold (R2 steps 1-2) and bring it to Ben; neither R1b nor R2 runs
  without his choice. **R1b** (no reverse copy):
  1. Hold again as in R2 steps 1-2 (lock, Steps 3.1-3.9 on `<new_claim>`; at most one pod and one VA, since none may
     have started).
  2. Revert the switch PR (**Ben OK**), lift the window and run the watch on `<old_claim>` (Step 8).
  3. Tear down the forward pairs (Steps 10.1-10.2), then Steps 10.3-10.7 (release the lock). Keep the LV and its
     entry for Ben to inspect (a guard refusal may mean the driver formatted it, ADR `:250-254`).
- **R2, after writes** (any time after Step 8.2 once the entry condition above holds; also via R3). Its own
  sequence, not a replay of the forward steps. Task 2.5's reverse source gate runs in this order: pass 1 as the entry
  check (before the hold), pass 1 under the hold, the Block apply, the Filesystem apply, `gate.log`, the gate
  teardown, then pass 2. Every `[TOOL]` step follows the clone rule first.
  0. Entry check (read-only), before step 1 and before any hold. If any part fails, stop here and bring it to Ben
     while the app still runs; never start the hold without it.
     - `evidence/4.0/facts.md` has `gate_ro_mount_proven: yes` and `gate_coverage` `covered` for `<id>` (D37). An id
       recorded `none accepted` has no reverse copy.
     - Pass 1: `[TOOL] install -d -m 0700 <td>/reverse-entry && cd <apps clone> && python3
       scripts/storage/migrate_volume.py render <id> --direction reverse --out <td>/reverse-entry`. Save the output as
       `<ev>/reverse/entry.txt`.
     - Expected: exit 0 with `gate-required` (possible when the lock is still held and the app is already at 0), or
       exit 1 with every `refused:` line one of `lock`, `writer`, `handle` or `rebuild`. Steps 1-3 (and R3's
       revert) clear them; a `rebuild` line waits for `freeze_checks` to pass. A `gate` line is a stop (the live
       writer template or its guard fails the gate rule; record it in `gate_coverage`). So are `stale-clone` (fetch
       again), `no-entry` and `size`. Nothing under `<td>/reverse-entry` is ever applied.
  1. The lock. Read `[R] python3 -c 'import json;d=json.load(open("/var/lib/homelab-maintenance/operation.json"));
     print(d["operation"],d["owner"])'` (one row; a missing file means released). If it does not print
     `storage-cutover:<id>` (Step 10.3 already released it): run `freeze_checks` (Step 2.1, including disabling
     auto-merge), take the lock as in Step 2.8 (**Ben OK**; `<id1>:<id2>` for a D14 pair), and re-run
     `freeze_checks` (Step 2.9).
  2. Hold again: Steps 3.1 to 3.6 (a fresh `<rv>` and writer baseline, a new window). Step 3.2 gates only on no
     `.operation` and a phase that is not `Running`; sync and health are recorded, not gated, because a rollback
     runs on a Degraded app. Steps 3.7 and 3.9 change: inventory and wait on `<new_claim>` and the VA for PV `<id>`
     (expected: at most one pod and one VA on `<id>`), and
     replace the `qm config` grep with `[S] targetcli sessions` (output form UNVERIFIED), which must list no session for
     `iqn.2026-11.net.starktastic.storage:<id>` once cold. Scale as in Step 3.8. Skip Step 3.9's forward
     `precheck` (it refuses `no-entry`, because the entry has `copied`).
  3. Tear down the forward pairs (Step 10.1 to 10.2), if they still exist. A PV's `csi` spec is immutable, so the
     reverse render needs them gone first.
  4. Source gate (Task 2.5, "Reverse source gate"; the LV is only read). Any failure is a stop: keep the hold and
     the lock, and bring it to Ben.
     1. Record in `facts.md` the name of the latest TrueNAS `apps/k3s-block` snapshot taken after the forward hold
        (`[T] zfs list -t snapshot -o name,creation -s creation apps/k3s-block`): it is the fallback copy of the old
        image.
     2. Pass 1 under the hold: `[TOOL] install -d -m 0700 <td>/reverse && cd <apps clone> && python3
        scripts/storage/migrate_volume.py render <id> --direction reverse --out <td>/reverse`. Expected: exit 0,
        `gate-required`, and only `gate.yaml` and `render.json` in `<td>/reverse`. Copy both back to `<ev>/reverse/`
        (`render.json` as `render-pass1.json`). Its `apps_head` equals the HEAD in `<ev>/clone-head.txt`.
     3. Split `gate.yaml` into its two halves (no apply; `(not rehearsed)`):
        `[TOOL] cd <td>/reverse && kubectl apply -f gate.yaml --dry-run=client -o json > gate.json && python3 -c
        'import json;l=json.load(open("gate.json"));n="migrate-guard-<id>";[json.dump(dict(l,items=[i for i in
        l["items"] if (i["metadata"]["name"]==n)==f]),open(p,"w")) for p,f in (("gate-block.json",False),
        ("gate-fs.json",True))];print([(i["kind"],i["metadata"]["name"]) for i in l["items"]])'` (one row).
        Expected: `gate-block.json` holds ConfigMap `migrate-<id>` and PV, PVC and Job `migrate-gate-<id>`;
        `gate-fs.json` holds PV, PVC and Job `migrate-guard-<id>`; nothing else.
     4. Block half (**Ben OK**, window check first): `[TOOL] kubectl apply -f <td>/reverse/gate-block.json`. Poll
        every 30 s: `[K] -n <ns> get job migrate-gate-<id> -o jsonpath='{.status.succeeded} {.status.failed}'`.
        Expected: `1` and no `failed`. Then poll `[K] get volumeattachment -o
        jsonpath='{range .items[*]}{.spec.source.persistentVolumeName}{"\n"}{end}'` until it lists no
        `migrate-gate-<id>`. Save `[K] -n <ns> logs job/migrate-gate-<id>` as `<ev>/reverse/gate.log`. Expected:
        `gate-fsck-ok <id>`. A failed Job (an `e2fsck -fn` exit other than 0) is a stop.
     5. Filesystem half (**Ben OK**, window check first, only after sub-step 4 above): `[TOOL] kubectl apply -f
        <td>/reverse/gate-fs.json`. Poll Job `migrate-guard-<id>` as in sub-step 4 above. Expected: `1`. Append
        `[K] -n <ns> logs job/migrate-guard-<id> --all-containers` to `<ev>/reverse/gate.log`, after the Block half's
        lines. Expected: the `ro` check passed, the guard exited 0, and `gate-guard-ok <id>`. If the `ro` check
        refuses, stop: the guard never runs on a read-write mount (D37). A guard refusal means the LV is not a source.
     6. Put `gate.log` on the tool host: `[TOOL] echo <base64 of <ev>/reverse/gate.log> | base64 -d >
        <td>/reverse/gate.log && sha256sum <td>/reverse/gate.log`. Expected: the workstation copy's hash.
     7. Tear the gate down (**Ben OK**). Both PVs are `Retain`, so no data is touched:
        - `[K] -n <ns> delete job migrate-gate-<id> migrate-guard-<id>`;
        - `[K] -n <ns> delete configmap migrate-<id>`;
        - `[K] -n <ns> delete pvc migrate-gate-<id> migrate-guard-<id>`;
        - `[K] delete pv migrate-gate-<id> migrate-guard-<id>`;
        - `[TOOL] cd <apps clone> && python3 scripts/storage/migrate_volume.py verify-teardown <id>`. Expected:
          exit 0.
     8. Pass 2, the same command: `[TOOL] cd <apps clone> && python3 scripts/storage/migrate_volume.py render <id>
        --direction reverse --out <td>/reverse`. Expected: exit 0, no `refused:` line, and `pairs.yaml` and `job.yaml`
        written. A `gate` line (an ok line missing from `gate.log`, or the lines name another id) or a `handle` line
        (a gate PV still live) is a stop. `apps_head` may differ from pass 1's after a re-fetch; record both. Copy
        `pairs.yaml`, `job.yaml` and `render.json` back to `<ev>/reverse/`. `render.json` shows source handle `<id>`,
        target handle `homelab//k3s-block/9999/vm-9999-<id>.raw`, and both sizes `<bytes>`.
  5. `[TOOL] cd <apps clone> && python3 scripts/storage/migrate_volume.py precheck <id> --direction reverse`. Expected:
     exit 0.
  6. Apply pass 2's `<td>/reverse/pairs.yaml` and then its `job.yaml` as in Steps 4.2 and 4.4 (**Ben OK** at each
     apply), re-running only the reverse precheck in place of Step 4.3. Save the log as `<ev>/reverse/copy.log`
     (never over the forward `copy.log`). Expected: `copy-ok reverse <bytes> <bytes>`, and no `e2fsck`, `dumpe2fs`
     or `resize2fs` line (the reverse runs Task 2.5 steps 1-4 only). Run the reverse precheck again after the Job.
  7. Revert the switch PR (**Ben OK**).
  8. Lift the window, and run the watch on `<old_claim>`.
  9. Tear down the reverse pairs, run `verify-teardown <id>`, then Steps 10.3 to 10.7 (release the lock, re-enable
     auto-merge, `facts.md`). For a D14 pair, run step 0 per id before the hold, and steps 3-6 per id under the
     pair's one lock.
  10. Then, and only then, offer Ben the entry-removal PR. It is reconciled after the lock is released, because
     `storage.yml` skips while the lock is held.
  11. The old image now carries MMP and `remount-ro` (Task 2.5 step 6). Proxmox CSI mounts it, with the MMP wait.
- **R3, after the reconciliation PR:** run R2's step 0 first; its `handle` line is expected here, and R3 step
  1's revert clears it. Inside "Then run R2", step 0 shows no `handle` line.
  1. Revert the reconciliation PR first (**Ben OK**), so `<old_pv>` and `<old_claim>` return to `main`.
  2. Check that `[K] get pvc -n <ns> <old_claim>` is `Bound` to `<old_pv>`. Argo recreates them if Step 9.5 deleted
     them; the image is unchanged.
  3. Then run R2.
- An interrupted step keeps the hold, the lock and both images. Never replay an uncertain apply, copy or delete
  (spec `:172-175`); bring the state to Ben.

### Task 4.W: Wave table

Source: apps `origin/main` `c5f60a0d` (2026-11-21), read with `git show`. Re-read every value live at execution
(Task 4.T Step 1 and Step 3.3). These are git values, not live sizes.

**Interfaces:**
- Consumes:
  - Task 2.5: the rule id == x, and the reverse source gate rule (one writer template on `<new_claim>`, one guard
    init container on the claim, no other PVC on it), which each row's writer and guard notes must meet;
  - Task 2.6: the binding styles and `copied`.
- Produces: the rows (and their writer and guard notes) that Task 4.0 Step 10 turns into `gate_coverage` (D37), and
  the per-wave deltas Task 4.T applies.

**Rules for every row:**
- `id` is the `<x>` of the old handle `vm-9999-<x>.raw` (Task 2.5, rule id == x). Six ids are longer than the scouts'
  short names: `bytestash-data`, `convertx-config`, `microbin-config`, `mosquitto-config`, `stirling-pdf-config` and
  `zigbee2mqtt-config`. Ben confirms the rule (D36) before the first inventory PR.
- `size` equals the binding capacity, so `resize2fs` never runs and a reverse copy stays possible (Task 2.5). Grow
  only after reconciliation, with the growth runbook.
- `class` is `regenerable` (VG `regen`) or `retained` (VG `retained`); the `VG` column says which.
- `<new_claim>` is `<id>-iscsi`, and `<old_pv>` equals `<old_claim>`. The two operator StatefulSets are the
  exception; see notes (a) and (b).
- `<selector>`:
  - app-template rows use `app.kubernetes.io/instance=<app>`;
  - every other row takes it from the writer's `.spec.selector.matchLabels`, read by name in Step 3.3 (UNVERIFIED
    until then).

  Step 3.3 and the Step 8.1 watch use `<selector>`, never a guessed label.
- The binding line is the PV's `volumeHandle` line. A `pv.yaml` row also has a `pvc.yaml` in the same directory.
- Hold codes:
  - `W+D0`: deny window, plus scale the app-template `main` Deployment to 0;
  - `W+S0`: deny window, plus scale the StatefulSet to 0;
  - `W+CR0`: deny window, plus the operator CR's `replicas: 0`;
  - `G`: the wave-6 Git hold.
- Path prefixes:
  - `MO/` = `infrastructure/base-configs/templates/monitoring-block-storage/`;
  - `OH/` = `.../operations-home-block-storage/`;
  - `UH/` = `.../utility-home-block-storage/`;
  - `ME/` = `.../media-block-storage/`;
  - `BC/` = `infrastructure/base-configs/templates/`;
  - `SV/` = `services/`;
  - `DB/` = `infrastructure/controllers/databases/`.
- Writer names marked `(live)` are derived and UNVERIFIED until Step 3.3 reads them.

**Totals:** 33 volumes, 192 GiB.

| Wave | Volumes | GiB |
|---|---|---|
| 1 | 6 | 41 |
| 2 | 14 | 31 |
| 3 | 5 | 20 |
| 4 | 4 | 8 |
| 5 | 1 | 64 |
| 6 | 3 | 28 |

**Karakeep placement (D14, D17).** The ADR's group 1 has `karakeep-meilisearch` in slot 4. D14 puts it in one
outage with `karakeep-data`, which is `retained`. The table follows the ADR: the pair runs in wave 1, slot 4. So
`karakeep-data` is the first `retained` cutover, and D17's dump rule merges after it. This is D17's recommended
default; D17's alternative moves the pair to the start of wave 2.

The alternative, for Ben: run the pair first in wave 2. Wave 1 then proves the copy Job on regenerable data only.

#### Wave 1: monitoring and Karakeep (ADR group 1)

| # | id | ns / Argo app | old claim (+ `-block`) | GiB | VG | binding |
|---|---|---|---|---|---|---|
| 1 | tempo | monitoring / tempo | tempo-data | 5 | regen | `MO/tempo-bindings.yaml:21` |
| 2 | alertmanager | monitoring / kube-prometheus-stack | (a) | 2 | regen | `MO/alertmanager-bindings.yaml:21` |
| 3 | loki | monitoring / loki | loki-data | 10 | regen | `MO/loki-bindings.yaml:21` |
| 4 | karakeep-data | operations / karakeep | karakeep-data | 4 | retained | `OH/karakeep-bindings.yaml:21` |
| 5 | karakeep-meilisearch | operations / karakeep | karakeep-meilisearch | 4 | regen | `OH/karakeep-bindings.yaml:75` |
| 6 | prometheus | monitoring / kube-prometheus-stack | (b) | 16 | regen | `MO/prometheus-bindings.yaml:21` |

Style, values, writer and guard:
- `tempo`:
  - existingClaim, `SV/operations/tempo/values.yaml:117` (`persistence.data`);
  - STS `tempo` (`:5-6`), hold W+S0;
  - guard `retained-state` (`:83`).
- `alertmanager`:
  - kps `volumeClaimTemplate`, `SV/operations/kube-prometheus-stack/values.yaml:167-180`;
  - CR `kube-prometheus-stack-alertmanager` (live), hold W+CR0;
  - guard `retained-state` (`:128`), mount `:156`.
- `loki`:
  - claimName, `SV/operations/loki/values.yaml:85` (`singleBinary.extraVolumes`);
  - STS `loki` (live), hold W+S0;
  - guard `retained-state` (`:48`), mount `:76`.
- `karakeep-data`:
  - existingClaim, `SV/operations/karakeep/values.yaml:186` (`persistence.data`), container `main`;
  - hold W+D0, shared with row 5;
  - guard `retained-data` (`:117`).
- `karakeep-meilisearch`:
  - existingClaim, same file `:196` (`persistence.meilisearch`), container `meilisearch` in the same pod;
  - guard `retained-meilisearch` (`:146`, marker only).
- `prometheus`:
  - kps `volumeClaimTemplate`, same kps file `:88-101` (`prometheusSpec.storageSpec`);
  - CR `kube-prometheus-stack-prometheus` (live), hold W+CR0;
  - guard `retained-state` (`:49`), mount `:77`.

Notes:
- (a) old claim `alertmanager-data-block-alertmanager-kube-prometheus-stack-alertmanager-0`, old PV
  `alertmanager-data-block`. New claim `alertmanager-iscsi-alertmanager-kube-prometheus-stack-alertmanager-0`, new
  template `alertmanager-iscsi` (Task 2.6).
- (b) old claim `prometheus-data-block-prometheus-kube-prometheus-stack-prometheus-0`, old PV
  `prometheus-data-block`. New claim `prometheus-iscsi-prometheus-kube-prometheus-stack-prometheus-0`, new template
  `prometheus-iscsi`.

Wave 1 deltas and gotchas:
- **Before tempo:**
  - the `regen` exclude (Task 2.8, merged in 3.5) is live:
    `[P] grep -c '<D1:placeholder_vmid>' /etc/homelab-backup.d/excludes.txt` prints 1;
  - the five regen images are restic excludes. The DR re-initialisation pre-approval (apps
    `docs/runbooks/monitoring-storage.md:24-27`) is not a migration shortcut: the ADR says "copied, not started
    empty" (ADR `:986`).
- **tempo, the first real copy** (ADR `:839-840`):
  - before Step 1, check the torn-block state: `tempodb_blocklist_poll_errors_total` has not grown in 1 h, and
    `kubelet_volume_stats_available_bytes{persistentvolumeclaim="tempo-data-block"}` is above 20 % of capacity;
  - if either fails, prune first, before the hold, with **Ben OK** (memory `tempo-torn-block-retention`, recipe
    `~/.cache/claude-homelab-live/tempo_prune.py`);
  - Step 5 takes D20's `used` measurement here;
  - an `EACCES` from the Job means stop: do not add `privileged` (Task 2.5);
  - native check: `TempoBlocklistPollFailing` stays quiet, and a trace search over the hour before the hold returns
    results (Grafana Explore, Ben).
- **alertmanager and prometheus (the operator style; Task 2.6 m8):**
  - the hold is the CR's `replicas: 0`; the StatefulSet is never scaled by hand;
  - after the window lifts, Argo syncs the CR back to 1 replica with the new template. The operator gets a 422,
    deletes the StatefulSet in the foreground and recreates it. The old PVC survives through
    `persistentVolumeClaimRetentionPolicy: Retain` (`values.yaml:36-38`, `:115-117`);
  - save the operator log line `recreating StatefulSet` to the evidence. If no recreate happens within 10 min of the
    sync (Task 2.6 m8), the CR is back at 1 by then:
    1. read `[K] -n monitoring get sts <name> -o jsonpath='{.spec.replicas}'` and the pods on `<old_claim>`;
    2. if the StatefulSet is at 0 and no pod mounts `<old_claim>`, run `[K] -n monitoring delete sts <name>
       --cascade=orphan` (**Ben OK**). No pod is orphaned, and the operator recreates it from the new template;
    3. otherwise re-hold: re-add the owned window (Steps 3.4-3.5), patch the CR to `replicas: 0` (Step 3.8), confirm
       no pod on either claim, run the orphan delete, then lift the window again as in Step 8.2 (**Ben OK** at each);
  - while either is down, the Watchdog stops, and healthchecks.io alerts Ben by its dead-man. Tell Ben before the
    hold;
  - alertmanager native check: the silence count is the same before the hold and after. Read it with `[K] get --raw
    /api/v1/namespaces/monitoring/services/kube-prometheus-stack-alertmanager:9093/proxy/api/v2/silences`;
  - prometheus native check: `prometheus_tsdb_lowest_timestamp_seconds` after the start is no later than before the
    hold. Size retention (`retentionSize: "8GB"`, `:28`) dropped one block on a first start in October
    (scout-precedent §8). A drop again is Ben's call;
  - during the prometheus cutover, the Step 2.7 and Step 8.5 metric reads use `[S]`;
  - no Prometheus or operator image bump in the same window (the Renovate `sha:` trap).
- **loki:** `enableStatefulSetAutoDeletePVC: false` (`loki/values.yaml:42`) stays. A log gap while Loki is down is
  expected; whether Alloy buffers it is UNVERIFIED. Native check: a LogQL count over the hour before the hold returns
  lines, through the promtool route in the Prometheus pod (memory `backup-review-live-access`; ask Ben first).
- **D14, the karakeep pair (rows 4-5):**
  - one lock, with operation `storage-cutover:karakeep-data:karakeep-meilisearch`;
  - one window on `karakeep`, and one Deployment scaled to 0, which stops both containers;
  - Step 2: one inventory PR with both entries. Expect two `create_raw` actions, one in `retained` and one in `regen`;
  - Step 3.7: filter on both old claims. Expected: one pod (the shared writer), and one VA per old PV of the pair (two
    in all), both on that pod's node. Any other pod or VA on either PV is a stop. Step 3.9: poll both old claims and
    both old PVs, and grep `qm config` for both `vm-9999-<id>.raw` names; then run `precheck` once per id, and both
    must exit 0;
  - Steps 4-5 run twice, one Job after the other, with a render per id;
  - Step 6: two switch PRs (Task 2.6), merged one after the other under the hold;
  - Steps 7-8 once;
  - Step 9: one reconciliation PR, which deletes `karakeep-bindings.yaml` (both pairs);
  - Step 10 per id, then one release;
  - the Meilisearch guard checks only the identity marker, and the container wipes the index if `.version_marker`
    differs from the engine (apps `docs/runbooks/operations-home-storage.md:24`). The byte copy keeps the marker. No
    Meilisearch or Karakeep bump in the window;
  - native check: Ben searches for one saved bookmark.
- **D17, after the karakeep pair** (the first `retained` cutover). After that cutover's Step 10 has released the lock,
  merge Task 2.8's `feat/storage-retained-dump-rule` (**Ben OK**).
  - It is an ansible merge, so it never lands inside a freeze. Its event is `proxmox-backup.yml` only (Task 2.8).
  - Expected: the next `homelab-backup@health` run reports no `stale:` and no `missing` line for the retained glob.
    Read the journal as in Task 1.1. Evidence goes to `evidence/4.T-karakeep-data/`.
  - This is `<D17:dump_rule_at>` = after the first `retained` cutover. Under the alternative placement, it moves to
    the first wave-2 cutover.

#### Wave 2: small apps (VG `retained`)

| # | id | ns / Argo app | old claim (+ `-block`) | GiB | binding |
|---|---|---|---|---|---|
| 7 | bytestash-data | operations / bytestash | bytestash-data | 2 | `OH/bytestash-bindings.yaml:21` |
| 8 | microbin-config | operations / microbin | microbin-config | 1 | `UH/microbin-bindings.yaml:21` |
| 9 | convertx-config | operations / convertx | convertx-config | 4 | `OH/convertx-bindings.yaml:21` |
| 10 | autobrr | media / autobrr | autobrr-config | 1 | `BC/autobrr-block-storage/pv.yaml:21` |
| 11 | calibre-web | media / calibre-web | calibre-web | 1 | `BC/calibre-web-block-storage/pv.yaml:21` |
| 12 | lingarr | media / lingarr | lingarr | 1 | `UH/lingarr-bindings.yaml:21` |
| 13 | stirling-pdf-config | operations / stirling-pdf | stirling-pdf-config | 1 | `UH/stirling-pdf-bindings.yaml:21` |
| 14 | paperless-data | operations / paperless-ngx | paperless-data | 1 | `BC/paperless-data-block-storage/pv.yaml:21` |
| 15 | qbittorrent | media / qbittorrent | qbittorrent | 2 | `UH/qbittorrent-bindings.yaml:21` |
| 16 | qbittorrent-ru | media / qbittorrent-ru | qbittorrent-ru | 1 | `UH/qbittorrent-ru-bindings.yaml:21` |
| 17 | audiobookshelf | media / audiobookshelf | audiobookshelf-config | 4 | `ME/audiobookshelf-bindings.yaml:21` |
| 18 | navidrome | media / navidrome | navidrome-config | 4 | `ME/navidrome-bindings.yaml:21` |
| 19 | shelfmark | media / shelfmark | shelfmark-config | 4 | `ME/shelfmark-bindings.yaml:21` |
| 20 | filebrowser | operations / filebrowser | filebrowser-data | 4 | `BC/filebrowser-block-storage/pv.yaml:21` |

Every wave-2 row is the existingClaim style with hold `W+D0`.

| id | values file:line | guard |
|---|---|---|
| bytestash-data | `SV/operations/bytestash/values.yaml:86` | `retained-data` `:48` |
| microbin-config | `SV/operations/microbin/values.yaml:112` | `retained-data` `:61` |
| convertx-config | `SV/operations/convertx/values.yaml:83` | `retained-convertx-data` `:43` |
| autobrr | `SV/media/autobrr/values.yaml:98` | `retained-state` `:48` |
| calibre-web | `SV/media/calibre-web/values.yaml:89` | `retained-state` `:42` |
| lingarr | `SV/media/lingarr/values.yaml:123` | `retained-data` `:57` |
| stirling-pdf-config | `SV/operations/stirling-pdf/values.yaml:90` | `retained-data` `:37` |
| paperless-data | `SV/operations/paperless-ngx/values.yaml:111` | `retained-data` `:84` |
| qbittorrent | `SV/media/qbittorrent/values.yaml:132` | `retained-data` `:19` |
| qbittorrent-ru | `SV/media/qbittorrent-ru/values.yaml:21` (own key over `baseApp`) | the base app's |
| audiobookshelf | `SV/media/audiobookshelf/values.yaml:79` | `retained-state` `:32` |
| navidrome | `SV/media/navidrome/values.yaml:86` | `retained-state` `:40` |
| shelfmark | `SV/media/shelfmark/values.yaml:96` | `retained-state` `:43` |
| filebrowser | `SV/operations/filebrowser/values.yaml:71` | none on main; Task 1.3 (D19) |

Wave 2 deltas and gotchas:
- **C1 app first** (`<D15:c1_id>`; recommendation `bytestash-data`, row 7). After its watch, Ben creates one item
  titled `c1-<date>` in the app. It exists only on the new storage. Task 4.C1 runs after the whole wave. If Ben picks
  another D15 app, it moves to row 7.
- **qbittorrent before qbittorrent-ru.** Each has its own window, its own `existingClaim` and its own switch PR.
  Task 2.6's variant check pins that switching the base app does not move the variant.
- **filebrowser:** Task 1.3's guard must be on main and passing (Task 1.3 evidence). Otherwise move filebrowser to
  the end of the wave.
- **lingarr** is also a PostgreSQL consumer (`SV/media/lingarr/values.yaml:14-15`). Its volume holds config only. The
  scouts' SQLite note is UNVERIFIED for the database. It is held again in wave 6.
- **paperless-data** holds the data dir only; its database is PostgreSQL (`values.yaml:12`).
- **Native check, per app:**
  - `[W] curl -s -o /dev/null -w '%{http_code}' https://<host>` gives 200, or 302 to `auth.starktastic.net` (memory
    `ingress-probe-from-workstation`);
  - the pod log has no `database is locked` or `malformed` line;
  - Ben opens the app and sees one existing item.
- **Gate C1** (Task 4.C1) after row 20 and before wave 3.

#### Wave 3: Servarr (VG `retained`)

| # | id | ns / Argo app | old claim (+ `-block`) | GiB | binding |
|---|---|---|---|---|---|
| 21 | sonarr | media / sonarr | sonarr-config | 4 | `ME/sonarr-bindings.yaml:21` |
| 22 | sonarr-ru | media / sonarr-ru | sonarr-ru-config | 4 | `ME/sonarr-ru-bindings.yaml:21` |
| 23 | radarr | media / radarr | radarr-config | 4 | `ME/radarr-bindings.yaml:21` |
| 24 | radarr-ru | media / radarr-ru | radarr-ru-config | 4 | `ME/radarr-ru-bindings.yaml:21` |
| 25 | lidarr | media / lidarr | lidarr-config | 4 | `ME/lidarr-bindings.yaml:21` |

All existingClaim, `W+D0`. Values: `SV/media/sonarr/values.yaml:71`, `SV/media/sonarr-ru/values.yaml:20`,
`SV/media/radarr/values.yaml:71`, `SV/media/radarr-ru/values.yaml:20`, `SV/media/lidarr/values.yaml:71`. Guards:
`retained-state` `:33` in each base app; the `-ru` variants inherit it through `baseApp`.

Wave 3 deltas and gotchas:
- Base before variant, as in wave 2.
- Stale health: one throwing check freezes old errors (memory `servarr-stale-health`). Confirm a health error live
  before blaming storage.
- Native check: Ben opens System > Status and the series or movie list; the log shows no SQLite error.

#### Wave 4: Home Assistant stack (VG `retained`)

| # | id | ns / Argo app | old claim (+ `-block`) | GiB | binding |
|---|---|---|---|---|---|
| 26 | mosquitto-config | h-a / mosquitto | mosquitto-config | 1 | `UH/mosquitto-bindings.yaml:21` |
| 27 | zigbee2mqtt-config | h-a / zigbee2mqtt | zigbee2mqtt-config | 1 | `UH/zigbee2mqtt-bindings.yaml:21` |
| 28 | home-assistant-config | h-a / home-assistant | home-assistant-config | 4 | `OH/home-assistant-bindings.yaml:21` |
| 29 | home-assistant-matter | h-a / home-assistant | home-assistant-matter | 2 | `OH/home-assistant-bindings.yaml:75` |

`h-a` is the namespace `home-automation`. All existingClaim, `W+D0`. Values:
- `SV/home-automation/mosquitto/values.yaml:94` (guard `retained-data` `:32`);
- `SV/home-automation/zigbee2mqtt/values.yaml:96` (guard `retained-data` `:43`);
- `SV/home-automation/home-assistant/values.yaml:162` (container `main`, guard `retained-home-assistant-config`
  `:75`) and `:172` (container `matter-server` in the same pod, guard `retained-matter-server-data` `:104`).

Wave 4 deltas and gotchas:
- Order: mosquitto, then zigbee2mqtt, then the Home Assistant pair. While mosquitto is down, zigbee2mqtt and Home
  Assistant lose MQTT. That is expected; they reconnect after the watch.
- D14 pair (rows 28-29): run as for karakeep, with operation
  `storage-cutover:home-assistant-config:home-assistant-matter`. One reconciliation PR deletes
  `home-assistant-bindings.yaml`.
- Native check (Ben): the Home Assistant UI loads with its history, zigbee2mqtt shows its devices online, and one
  Matter device responds.

#### Wave 5: Jellyfin (VG `retained`)

| # | id | ns / Argo app | old claim (+ `-block`) | GiB | binding |
|---|---|---|---|---|---|
| 30 | jellyfin | media / jellyfin | jellyfin-config | 64 | `BC/jellyfin-block-storage/pv.yaml:21` |

existingClaim `SV/media/jellyfin/values.yaml:89`, `W+D0`. Guard: none on main, only `disposable-dirs` (`:62`). Task
1.3's guard is a prerequisite (ADR `:947`).

Wave 5 deltas and gotchas:
- **Copy time.** The Job writes 64 GiB once and reads it three times (`dd`, `cmp`, `e2fsck`). With `R` the slowest
  MiB/s seen in earlier `copy.log` files, the estimate is `4 * 65536 / R` seconds.
  - It must stay under the Job's `activeDeadlineSeconds: 14400`, so `R` must be at least about 19 MiB/s.
  - It must also end before the next backup window, so start right after the 09:50 or 15:50 window ends.
  - If either fails, stop. Raising the deadline is a Task 2.5 change, and Ben's call.
- **Capacity.** Task 4.0 Step 3's deletions must be at least a week old. Gate on 64 GiB plus `<D20:margin_gib>`.
- **Extra hold:** suspend the LDAP CronJob, which calls the API every 15 min
  (`SV/media/jellyfin/manifests/ldap-library-sync.yaml:9`). After the window is set, on **Ben OK**, run
  `[K] -n media patch cronjob jellyfin-ldap-library-sync --type merge -p '{"spec":{"suspend":true}}'`. The
  post-lift sync restores `suspend` from git.
- `/config/cache` is a 10 GiB emptyDir (`values.yaml:94-103`) and is not on the volume.
- After the watch, re-check `EnableThrottling` and `EnableSegmentDeletion` in `encoding.xml` (memory
  `jellyfin-disposable-cache`).
- Native check (Ben): one film plays, and the library is complete.

#### Wave 6: databases (VG `retained`)

| # | id | ns / Argo app | old claim (+ `-block`) | GiB | binding |
|---|---|---|---|---|---|
| 31 | redis-data | databases / redis | redis-data | 2 | `BC/redis-immich-block-storage/redis.yaml:21` |
| 32 | immich-postgres | media / immich | immich-postgres | 10 | `BC/redis-immich-block-storage/immich.yaml:21` |
| 33 | postgres | databases / postgres | postgres-data | 16 | `BC/postgres-block-storage/pv.yaml:21` |

Style, values, writer and guard (all hold `G`):
- `redis-data`:
  - Bitnami `master.persistence.existingClaim`, `DB/redis/values.yaml:9`;
  - STS `redis-master` (live);
  - guard `verify-retained-data` (`:27`), which mounts volume `redis-data`.
- `immich-postgres`:
  - existingClaim, `SV/media/immich/values.yaml:181` (`persistence.pgdata`);
  - app-template controller `postgres` (`:70`), Deployment name (live);
  - guard `verify-retained-data` (`:84`).
- `postgres`:
  - Bitnami `primary.persistence.existingClaim`, `DB/postgres/values.yaml:47`;
  - STS `postgres-postgresql` (live);
  - guard `verify-retained-data` (`:68`), which mounts volume `data`.

Order: redis, then immich-postgres, then postgres (ADR `:995`).

**Wave 6 prework (code, TDD; apps, branch `storage/bitnami-resolver` off `origin/main`).** Task 2.6 leaves Bitnami
bindings unresolved on purpose.
- **Files:**
  - Modify `scripts/check-retained-inventory.py` (`check_bindings`: one more resolver);
  - Test `scripts/storage/tests/test_retained_inventory.py`.
- **Interfaces:**
  - Consumes Task 2.6's `check_bindings(entries, root)`.
  - Produces a resolver for `primary.persistence.existingClaim` (volume `data`) and `master.persistence.existingClaim`
    (volume `redis-data`), with the guard rule "an entry of `primary.initContainers` or `master.initContainers`
    mounts that volume".
- [ ] **Step 1: Write the failing tests.**
  - `test_bitnami_existing_claim_resolves`:
    - `{'primary': {'persistence': {'existingClaim': 'postgres-iscsi'}, 'initContainers': [{'name':
      'verify-retained-data', 'volumeMounts': [{'name': 'data'}]}]}}` with `entry('postgres', claim='postgres-iscsi',
      origin='migrated', copied='2026-12-01')` gives `[]`;
    - the same without `copied` gives an error naming `postgres` and `copied`;
    - with no init container mounting `data`, it gives an error;
    - the `master` / `redis-data` mirror case behaves the same way.
  - Change `test_unknown_binding_style_fails` to use `foo.persistence.existingClaim`.
  - Run: `python3 -m unittest discover -s scripts/storage/tests -v`. Expected: FAIL (`primary.persistence` is still
    reported as an unresolved style).
- [ ] **Step 2: Implement** the resolver in the Task 2.6 resolver table:
  - the path, `existingClaim`;
  - the guard list path, `<root>.initContainers`;
  - the volume name, `data` or `redis-data`, with the comment `shortcut: Bitnami volume names are chart-derived;
    re-check on a postgresql or redis chart major`.
- [ ] **Step 3: Run** Step 1. Expected: PASS, and `test_repo_bindings_pass` still passes.
- [ ] **Step 4: Check offline that the switch leaves the StatefulSets mutable.** Render both charts before and after
  the switch edit, with the docker helm wrapper (memory `workstation-offline-checks`):
  `helm template postgres bitnami/postgresql --version 18.12.20 -f templates/globals.yaml
  -f infrastructure/controllers/databases/postgres/values.yaml`, and the same for redis 28.3.12.
  - Expected: no `volumeClaimTemplates` in either StatefulSet. Only the pod template's claim changes.
  - Otherwise, stop: the switch would need a StatefulSet replacement (runbook `postgresql-storage.md:66-70`).
- [ ] **Step 5: Commit** `feat(storage): resolve Bitnami existingClaim bindings for migrated volumes`. Merge it
  (**Ben OK**) before the redis inventory PR. Merge event: ArgoCD syncs, and nothing renders.

**Wave 6 deltas** (ADR `:995-999`; apps `docs/runbooks/postgresql-storage.md`, a historical record from which only
the ADR's three deltas are taken: a Git hold, the enrollment hook, and a fresh dump confirmed off-site):
- **The Git hold replaces Step 3.4-3.8** (`postgresql-storage.md:179-187`; the DB-wave precedent
  `git show 45c7fb8c:scripts/postgres-retained-startup/production/cutover/README.md:63-73`). For each database, two
  apps PRs, each merged (**Ben OK**) only after the previous runtime gate:
  1. **Client hold PR.** Every consumer at 0 replicas, the pilot at 0, and the backup jobs suspended.
     - Consumers. Derive them at execution and mark the list UNVERIFIED until the live read below agrees:
       - postgres: `[W] git grep -l -i -E 'postgres(ql)?[-.](postgresql\.)?databases|postgres-postgresql' origin/main
         -- services infrastructure ':!*.md'`. On `c5f60a0d` this lists authentik, crowdsec, pgadmin, bazarr,
         cleanuparr, dispatcharr, lingarr, prowlarr, seerr, seerr-ru, excalidash, kube-prometheus-stack (Grafana),
         ntfy, paperless-ngx and postgres-enrollment-pilot. Add the apps whose host comes from a Secret (mealie
         sets `DB_ENGINE: "postgres"` at `SV/operations/mealie/values.yaml:13`; listmonk and vaultwarden are
         UNVERIFIED);
       - redis: `[W] git grep -l -E 'redis-master|redis\.databases' origin/main -- services infrastructure ':!*.md'`
         lists authentik, dispatcharr and immich. Paperless is a precedent consumer (scout-precedent §2), UNVERIFIED
         today;
       - immich-postgres: `immich-main` only.
     - Live check before the PR:
       - postgres: `[K] -n databases exec <pod> -- psql -U postgres -Atc "select datname, usename, count(*) from
         pg_stat_activity where backend_type = 'client backend' group by 1, 2"`;
       - redis: `CLIENT LIST`, run through `redis-cli` in its pod.

       The password comes from the pod's own environment, never printed. Every client maps to an app on the list.
     - Backup jobs:
       - `pg-backup` (`BC/pg-backup/cronjob.yaml`, schedule `0 2 * * *`, in `base-configs`) gets `suspend: true`;
       - Immich's own 02:00 dump stops with `immich-main`.

       Suspending a CronJob does not drain a running Job, so check there is none.
     - Gate: the clients are at 0, no Job is active, and the live client list is empty.
  2. **Server hold PR.**
     - The server goes to 0: `primary.replicaCount: 0` at `DB/postgres/values.yaml:31`, `master.count: 0` for redis,
       and `controllers.postgres.replicas: 0` for immich.
     - For postgres, the PR also removes `DB/postgres/manifests/enrollment-job.yaml` (the Sync hook) and keeps its
       ConfigMap, roles and credentials (runbook `:184-186`).
     - Gate: the server pod is gone, no VA names the old PV, and the `qm config` grep is empty. Then precheck exits 0.
  - The lock (Step 2.8) is taken before the client hold PR. Holding authentik takes SSO down, so confirm management
    access that does not need it first (runbook `:231-232`). `[K]` through QGA does not need it.
  - Consumer gates wait 600 s for a healthy `postgres` (e.g. `SV/media/bazarr/manifests/postgres-completion-gate.yaml`).
    That is why the consumers are held too.
- **Fresh dump confirmed off-site, before each inventory PR** (not redis: D30 waived it, see below; ADR
  `:997-999`: in a TrueNAS :30 snapshot, replicated, and listed by `R ls` after a green backup run). Run it on the
  day of the cutover, after the 04:30 run has finished green (`R()` as ansible `docs/backup-and-restore.md:162-164`,
  on pve, holding the backup lock):
  - postgres: `R ls latest --tag daily /srv/backup-src/pv/databases/pg-backup` lists that day's
    `pg_dumpall_*.sql.gz` (the dump rule glob, ansible `roles/proxmox_backup/defaults/main.yml:54`);
  - immich-postgres: the same day's `immich-db-backup-*.sql.gz` under `/srv/backup-src/immich/backups` (`:57`). That
    share is an NFS source read directly, not a replica, so "replicated" means the restic run itself; the snapshot tag
    is UNVERIFIED;
  - redis: no dump job exists. **D30 decided (Ben, 2026-11-23): (b), waived**; the ADR records the exception (wave 6).
    No fresh dump and no listing gate: the redis copy Job (Step 4.4) runs after the server hold, as for any volume.
    Option (a) below is kept for reference only.
    - (a) Recommended, a real fresh dump. After the client hold gate, run `SAVE` through `redis-cli` in the pod,
      from a script staged on the `[K-host]` like `watch.sh` (the password comes from the pod's environment, is
      never printed, and no row contains `$`). Expected: `OK`, `LASTSAVE` advanced, and `INFO persistence` shows
      `rdb_last_bgsave_status:ok`. Then the server hold (gate 2) stops Redis cleanly, so the cold old image holds
      that `dump.rdb`. Wait for the next TrueNAS :30 snapshot of `apps/k3s-block` to replicate, then on **Ben OK**
      `[P] systemctl start --no-block homelab-backup@backup.service`. Expected after it ends green:
      `R ls latest --tag daily /srv/backup-src/k3s-block/images/9999` lists `vm-9999-redis-data.raw` in a snapshot
      created after the server hold (whether a manual run carries the `daily` tag is UNVERIFIED; if not, use
      `R ls latest` on that run's snapshot id). The :30 snapshots run only at 03, 09, 15 and 21, and the backup
      start waits for that window to end (:50), so time the client hold just before one; the Redis consumers stay
      held until the listing. This is the one planned exception to the intro's "steps 3-8 fit before the next
      window" rule: the hold spans the window, and nothing mutates inside it.
    - (b) Ben explicitly waives ADR `:997` for redis; Task 0.4 records the waiver in the ADR first. The day's 04:30
      image of a running Redis is then the only off-site copy, and it is not a dump.
  - A tighter point is optional: on **Ben OK**, `[K] -n databases create job --from=cronjob/pg-backup
    pg-backup-manual-<date>` after the client hold, then a manual `systemctl start --no-block
    homelab-backup@backup.service` once the next :30 snapshot has replicated.
- **Release replaces Step 8.2**, one PR per gate (runbook `:210-222`; precedent patches 04-09):
  1. server only (the hook is still out). Gate: the guard passes, the server is healthy, and the physical ID matches;
     `DB/postgres/manifests/enrollment-configmap.yaml` holds `expectedSystemIdentifier`. The guard no longer reads
     it (D47), so read it here (read-only): `[K] -n databases exec <pod> -- psql -U postgres -Atc "select
     system_identifier from pg_control_system()"`, with the password from the pod's own environment, never printed;
  2. hook restored (postgres only). Gate: a full non-selective sync, the `postgres-enrollment` Sync hook `Succeeded`,
     then one more full sync;
  3. pilot, then the consumers (authentik first), then the backup schedule.

  The 6-minute watch runs on the server after gate 1 and again after the consumers are back. The deny window is not
  used in wave 6. The Step 7 queued-operation check still applies to each released app.
- **Step 7 in wave 6.** With no window, the switch PR syncs at once. Step 7.2's Expected becomes `Synced` at `<sha>`,
  with the server still at 0 replicas (from the server hold PR) and no pod on either claim. R1 step 2 reads the same
  way after its revert.
- **Rollback in wave 6.** R1 to R3 apply, with the Git hold PRs in place of the window. To hold again, revert the
  release PRs, in reverse order. To release, re-merge them in order.
- **Native checks:**
  - postgres: the physical ID; every consumer logs in; Ben signs in through Authentik;
  - immich: an old photo opens (Ben);
  - redis: `INFO persistence` shows the RDB or AOF loaded, and Immich's worker reconnects. A Redis restart drops
    Immich's worker for about 40 s, so pick a time with no Immich jobs running (memory `renovate-apps-pitfalls`).
- **Renovate traps:** no postgres:18.6-alpine digest bump (it rewrites the enrollment Job; memory
  `renovate-apps-pitfalls`). The Redis guard's version pin and Bazarr's 1.6.3 guard schema went with apps#1707 (D47),
  so those two traps are gone; memories `renovate-apps-pitfalls` and `bazarr-163-guard-schema` predate that.
- **Reconciliation:** as Step 9. After postgres, `BC/postgres-block-storage/` is deleted.

### Task 4.C1: Gate C1 (Check 10)

On the D15 app `<D15:c1_id>` (recommendation `bytestash-data`), while its old image `vm-9999-<D15:c1_id>.raw` is still
the rollback (ADR `:988-992`). It restores once from a `usbbk` ZFS clone and once off-site with `restic restore` of the
whole `retained` image. Each restore uses a snapshot taken after the cutover, and each is checked for the C1 marker. It
runs on pve, between cutovers (never during one), outside the backup windows, and holding
`/run/lock/homelab-backup.lock` the whole time. Nothing touches the live storage VM or the app. The ZFS-clone leg is
`(not rehearsed)`: the lab did not run it (lab report B9, `storage-lab/b9/notes.md`). Only the `cp` copy leg passed
there.

**Files:**
- Create (evidence only): `evidence/4.C1/rows-*.json`, `out-*.txt`, `facts.md`.
- No repo change.

**Interfaces:**
- Consumes:
  - the `<D15:c1_id>` cutover's `<copied>` date and Ben's marker snippet `c1-<date>` (4.W wave 2);
  - `<D1:placeholder_vmid>` and `<retained_volname>` (the Task 3.4 `pvesm alloc` name);
  - the single-app runbook `docs/runbooks/storage-vm-restore.md`, sections "Single app from a ZFS clone" and
    "Off-site restic restore" (Task 2.7; ADR `:693-704`).
- Produces: `facts.md` with `c1_clone_pass` and `c1_restic_pass`, and the snapshot names used.

- [ ] **Step 1: Preconditions** (read-only).
  - `[P] zfs list -t snapshot -o name,creation -r usbbk/tn/k3s-block | tail -5`. Expected: a snapshot created after
    the marker was written, so after the next :30 replication.
  - `[P] R snapshots --tag daily` (`R()` as ansible `docs/backup-and-restore.md:162-164`). Expected: a snapshot from
    a green run after the marker. Green means no `PROBLEM` line in that run's journal (runbook `:182-185`).
  - `[P] df -B1 /usbbk` and `zfs get -Hp available usbbk`. Expected: at least the retained image's allocated size,
    plus `<D20:margin_gib>` GiB. The allocated size comes from
    `[P] du -B1 $(pvesm path k3s-block:<D1:placeholder_vmid>/<retained_volname>)`.
  - `[P] losetup -a; dmsetup ls; vgs`. Expected: no loop device on a restore path, and no `restore_*` VG.
- [ ] **Step 2: ZFS-clone leg** (**Ben OK**, one script under the backup lock, with an unwind trap;
  `(not rehearsed)`). Run it as a `systemd-run --unit=c1-clone -p RemainAfterExit=yes` unit, as lab B9 did. The steps:
  1. `exec 9>/run/lock/homelab-backup.lock; flock -n 9` (runbook `:146-148`);
  2. `zfs load-key -L file:///etc/homelab-backup/apps.key usbbk/tn/k3s-block`, only if `keystatus` is not
     `available` (runbook `:197-198`);
  3. `zfs clone usbbk/tn/k3s-block@<snap> usbbk/restore-<date>`. Never clone under `usbbk/tn`;
  4. `dev=$(losetup --find --show /usbbk/restore-<date>/images/<D1:placeholder_vmid>/<retained_volname>)`. The
     clone's mount path is UNVERIFIED; read it with `zfs get -H mountpoint usbbk/restore-<date>`;
  5. `vgs -o vg_name,vg_uuid,lv_active` first: if pve's LVM auto-activated the clone's VG, run `vgchange -an
     --select vg_uuid=<uuid>` on it (the UUID from `pvs -o vg_uuid $dev`). Then `vgimportclone -n restore_<date> $dev
     && vgchange -ay restore_<date>`;
  6. `mkdir -p /usbbk/restore/c1-<date>/clone /usbbk/restore/c1-<date>/mnt &&
     mount -o ro /dev/restore_<date>/<D15:c1_id>
     /usbbk/restore/c1-<date>/mnt`. Mounting `ro` replays the journal on the writable clone (ADR `:699`); the lab
     used `ro,noload`. MMP holds this mount for about 42 s `(not rehearsed)`;
  7. copy every SQLite file with its `-wal` and `-shm` into `/usbbk/restore/c1-<date>/clone/`;
  8. unwind: `umount`, `vgchange -an restore_<date>`, `losetup -d $dev`, `zfs destroy usbbk/restore-<date>`.

  Expected:
  - unit `exited success 0`;
  - `losetup -a`, `dmsetup ls | grep restore_` and `zfs list usbbk/restore-<date>` are empty afterwards.

  The clone is destroyed before the next :30 replication (ADR `:694`).
- [ ] **Step 3: Check the clone leg's data** (read-only).
  - `[P] python3 -c "import sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);
    print(c.execute('pragma integrity_check').fetchone()[0])" /usbbk/restore/c1-<date>/clone/<db file>` (one row).
    The file name is UNVERIFIED (scout-volumes: `snippets.db`).
  - `[P] grep -c 'c1-<date>' /usbbk/restore/c1-<date>/clone/*`.
  - Expected: `ok`, and a count of at least 1 across the db and wal files. Ben confirms that the marker is his.
- [ ] **Step 4: restic leg** (**Ben OK**; under the backup lock; never across 04:30).
  1. `R restore <snapshot-id> --target /usbbk/restore --sparse --include
     /srv/backup-src/k3s-block/images/<D1:placeholder_vmid>/<retained_volname>` (runbook `:222-226`, ADR `:703`). This
     restores the whole `retained` image.
  2. Run the same steps 2.4 to 2.8 on `/usbbk/restore/srv/backup-src/k3s-block/images/<D1:placeholder_vmid>/
     <retained_volname>`, copying into `/usbbk/restore/c1-<date>/restic/`, with no `zfs` steps.
  3. Delete the restored image afterwards.

  Expected: restic exit 0; the same unwind checks; the restore time, recorded in `facts.md`.
- [ ] **Step 5: Check the restic leg's data.** As in Step 3, on `/usbbk/restore/c1-<date>/restic/`. Expected: `ok`
  and the marker.
- [ ] **Step 6: Clean up and record** (**Ben OK** for the delete).
  - `[P] rm -r /usbbk/restore/c1-<date>`, then `ls -A /usbbk/restore`. Expected: empty, and `ls -A
    /var/lib/systemd/pstore` empty.
  - Write `facts.md`: both passes, the snapshot names, the times.
- Gate: both legs pass before any wave 3 inventory PR. A failed leg is a stop: the old image stays, and Ben decides.

---

## Part 5: Retirement (ADR Migration 4)

This part removes Proxmox CSI once the last volume runs on the storage VM. Automatic fencing stays off (Ben,
2026-11-21): `hold_fence` stays on `retained`, the fencer keeps running and refusing, and the manual fence stays the
only fence. Removing `hold_fence` and gate R1 are a later, separate decision (Not in this plan). Code steps of 5.1,
5.2, 5.3, 5.6, 5.9, 5.11, 5.12 and 5.13 follow the Part A style. Live steps follow the Part B style.

**Entry gate (all of these, read in Task 5.1 Step 1):**
- every 4.W row is done: every `origin: migrated` entry (33; D39 as amended by D46 adds none) has a
  `copied` date, and every 4.T reconciliation PR is merged. `origin: new` entries added after Task 3.9 are allowed;
- gate C1 has passed (`evidence/4.C1/`);
- no VolumeAttachment has attacher `csi.proxmox.sinextra.dev`;
- no cutover is open, and nobody else holds the maintenance lock.

**Execution order.** The task IDs are the outline's; 5.8, 5.9 and 5.10 were added after the requirements audit, and
5.11 after D41 (Ben, 2026-11-22), and 5.13 after D50 (Ben, 2026-11-23). The order they run in is:
1. 5.1. It starts only after Ben's rollback gate in 5.1 Step 2.
2. 5.2a.
3. 5.3, which must come before 5.4: the pool has to be empty before it is deleted.
4. 5.4.
5. 5.5 (fencing stays held; Check 11 at 300 s at the first planned worker reboot after that).
6. 5.8 (the scale gate), after 5.5 Step 2 has passed.
7. 5.10 (the planned host reboot with every retained volume staged), after 5.8 has passed.
8. 5.13 (the k3s root to bpg, D50), after 5.10 has passed (`host_reboot_pass: yes`) and its merge hold is lifted. 5.11
   has merged long before (it lands after 5.3). From the moment 5.13's adoption PR opens until its PR B (and, under
   D50(h), PR C) has merged, hold every other terraform PR unmerged (packer-build and Renovate alike), merge no PR with
   the destroy box ticked, and dispatch no `apply.yml` (except the Step 10 recovery dispatch, Ben OK). In the same
   window, and again from Step 15's merge until its deploy has ended, run no 5.12 conversion batch and no 5.7 free
   (both are live, and the hold above covers terraform PRs only). `adoption_gate.py` refuses every other plan
   while import blocks remain, and destroy mode refuses before the lock.
9. 5.6, which also carries 5.13's contract-index commit.

5.9 (the copy tool removal) runs any time after 5.1 has merged and its Step 7 has passed: that merge closes the last
reverse-copy window (D27).

5.12 (migrated volumes onto the one-flag layer, D46, D47, D48) runs after 5.9 has merged: until then the reverse
source gate copies each migrated volume's hand-wired guard. Its conversion batches are live events, each at a time Ben picks.

5.11 (drain mode for k3s VM replaces, D41) runs after 5.3 has applied and its deploy has ended, and before any other
terraform PR. Until 5.11 has merged, a terraform PR that replaces k3s VMs after 5.1 gets both lines `- [x] Drain cluster
nodes before apply` and `- [x] I confirm the destructive action selected above` added to its body before the merge (Ben
OK), or every packer-build PR is held unmerged until 5.11 has merged.

5.7 runs per image, from one week after each image's `copied` date. 5.2b follows 5.7, once the five regen images are
gone.

**How live steps run.** As Part 1 says ("How live reads run in this part"):
- `pve` and `tn` rows go through the helper;
- `KUBE <args>` is `qm guest exec <master vmid> -- k3s kubectl <args>` in a `pve` row;
- `gh` runs on the workstation.

This part adds `SVM <cmd>`, which is Part 4's `[S]`: a `pve` row
`qm guest exec <D1:storage_vmid> -- bash -c '<cmd>'`, run as root (no `sudo`). Task 3.4 Step 4's
`VM <D1:storage_vmid>` reads already proved that qemu-guest-agent answers there; there is no SSH key for it (Part 3,
"How live steps run"). `[R] <cmd>` is Part 4's: root on VM300 through a `pve` row `qm guest exec 300`. Commands are
ASCII only and contain no `'`, since they sit inside the single-quoted `bash -c`, and no `$`, since pve expands it
first (Part 4, "Where commands run"). A mutation needs **Ben OK** with the exact command shown first.

Evidence goes to `$EVR/5.<n>/`, which is `evidence/5.<n>/`.

**Worktrees.** By now every `feat/retained-storage-vm` branch has merged, so every Part 5 PR branches off
`origin/main` in a new worktree. `env.sh` does not define these names, so set them after sourcing it:
`RA=$WT/apps-retire RN=$WT/ansible-retire RT=$WT/terraform-retire GR=$WT/github-retire`. Create each once with
`git -C <repo> fetch origin && git -C <repo> worktree add --detach <dir> origin/main`, where `<repo>` is `$AP` for
`$RA`, `$A` for `$RN`, `$T` for `$RT` and `~/Projects/homelab/.github` for `$GR`. Each task then cuts its branch with
`git -C <dir> switch -c <branch> origin/main` after a fresh fetch.

Line numbers below are at `origin/main` as fetched on 2026-11-21:
- apps `c5f60a0d`;
- ansible `71b0d70`;
- terraform `cc493bd`;
- `.github` `67c2d64`;
- the A branch `a036b47` for the fencer code that 5.5 cites.

Parts 0-4 move them, so every step re-greps before it edits.

Task ID 5.0 (the refusing gauge, D13 and D33) is unused: it is deferred with automatic fencing (Not in this plan).

### Task 5.1: apps: remove the Proxmox CSI chart, its settings, the slot alerts and the old bindings

**Files** (worktree `$RA`, branch `chore/retire-proxmox-csi` off `origin/main`):
- Delete:
  - `infrastructure/system/proxmox-csi/app.yaml`, `values.yaml` (chart `proxmox-csi-plugin` 0.5.16) and
    `shared-storage-settings.json`;
  - `infrastructure/system/sealed-secrets/manifests/namespace.yaml` (Namespace `csi-proxmox`), `proxmox-api-trust.yaml`
    and `proxmox-csi-config.yaml`. These three are the whole `manifests/` dir;
  - `services/operations/kube-prometheus-stack/manifests/proxmox-csi-capacity.yaml`. These are the slot alerts:
    `ProxmoxCSINodeAttachmentHeadroomLow`, `ProxmoxCSIClusterAttachmentHeadroomLow` and
    `ProxmoxCSIClusterAttachmentCapacityExhausted`, plus the recording rules `homelab:proxmox_csi_attachments:count` and
    `homelab:proxmox_csi_slots_free:count`;
  - `docs/runbooks/proxmox-csi-capacity.md`. Nothing links to it (`git grep proxmox-csi-capacity.md`);
  - any old binding file left behind. On origin/main they are the `pv.yaml`/`pvc.yaml` pairs in
    `infrastructure/base-configs/templates/<x>-block-storage/` for `autobrr`, `calibre-web`, `filebrowser`,
    `jellyfin`, `paperless-data` and `postgres`, plus the `*-bindings.yaml` files and
    `redis-immich-block-storage/{immich,redis}.yaml`. Each 4.T reconciliation PR removes its own.
    Expected here: none left. Never delete `templates/retained-startup-guard.yaml` or
    `files/retained-startup/guard.py`: every hand-wired guard, NFS ones included, mounts that ConfigMap (D47; the old
    `guard-*.yaml` files went in apps#1707).
- Modify:
  - `infrastructure/system/sealed-secrets/app.yaml:9`: drop `manifests: true`, so the appset renders no empty directory
    source (`bootstrap/appsets/cluster-apps.yaml:189-200`);
  - `infrastructure/system/proxmox-csi/README.md`. Keep the file and its path, because it is the single quota record
    (`:21-26`) and about 25 runbooks link to its `#retired-migration-sources-2026-11-16` anchor. Add a first paragraph:
    "Retired <date> (ADR 0017 Migration 4). The quota section stays current; the rest is history." Without
    `app.yaml`, the appset (`pathPattern: infrastructure/**/app.yaml`) no longer sees the dir;
  - `homepage/catalog.yaml:273-290` (`capacity` tile):
    - drop the `CSI Slots Free` and `Tightest Worker` metrics;
    - set the comment and `description` to `fullest volume, TSDB`;
    - regenerate with `python3 scripts/homepage/generate.py` (CLAUDE.md:29,67-68). It rewrites
      `services/operations/homepage-admin/manifests/templates/configmap.yaml` (`:1386-1388`);
  - `scripts/homepage/rendercheck/mock/{alarm,data}/kube-prometheus-stack-prometheus-monitoring-9090/values.json`: drop
    the two `homelab:proxmox_csi_slots_free:count` keys (alarm `:12,21`, data `:23,35`);
  - `services/operations/kube-prometheus-stack/manifests/grafana-dashboard-homelab-operations.yaml`. Repoint both panels
    in place, so the grid keeps no hole:
    - the stat "CSI slots free" (`:341-362`) becomes "Storage VG free", with expr
      `min(storage_vg_free_bytes{job="storage-vm"} / storage_vg_size_bytes{job="storage-vm"})` in percent;
    - the per-node panel (`:935`) becomes `storage_vg_free_bytes{job="storage-vm"}` with legend `{{vg}}`;
  - `renovate.json:78-83`: drop the `proxmox-csi-plugin` package rule;
  - `infrastructure/controllers/databases/pgadmin/values.yaml:22`: drop `storageClass: proxmox-retained`. It is unused
    with `existingClaim: pgadmin-files`;
  - `README.md:105`, `:142` (the app row) and `:216`;
  - `CLAUDE.md:77-79` (prebind and "29 slots" now point at `infrastructure/base-configs/files/retained-volumes.json`
    and the storage runbooks) and `:97-100` (the "CSI topology and slots" contract becomes the storage VM inventory
    and `storage-vm.yaml`);
  - `docs/operations/operator-notes.md:7`;
  - `docs/runbooks/storage-vm-rebuild.md` (Task 2.7): add a "k3s-block registration" line with the facts that
    `shared-storage-settings.json` held. The values are storage id `k3s-block`, NFS server `10.9.9.30`, export
    `/mnt/apps/k3s-block` and node `pve` (`shared-storage-settings.json:2-5`). The storage VM's data disks still live
    there, and that file is their only apps record;
  - the diagrams `docs/diagrams/gitops-flow.svg:208` (`proxmox-csi` box) and `request-path.svg:201` ("storage class:
    Proxmox CSI block"), through the kit:
    - edit `~/Projects/homelab/readme-redesign/kit/apps/gitops-flow.tpl.svg:114` and `request-path.tpl.svg:101`;
    - run `python3 ~/Projects/homelab/readme-redesign/kit/stamp.py apps`;
    - copy the two outputs from `readme-redesign/apps/docs/diagrams/` into `$RA` (as Task 0.1 Step 10 does for
      packer);
  - the app counts (memory `readme-redesign`): `README.md:48` ("76 Applications") and `docs/diagrams/banner.svg:69`.
    Recount with `git -C $RA ls-files 'infrastructure/**/app.yaml' 'services/**/app.yaml' | wc -l`. democratic-csi
    (3.6) added one and this task removes one.

**Interfaces:**
- Consumes:
  - the 4.W completion;
  - `storage_vg_free_bytes` and `storage_vg_size_bytes` (`storage-vm.yaml`, `StorageVGLowSpace`).
- Produces: no `csi.proxmox.sinextra.dev` object in Git or the cluster: no CSIDriver, no StorageClass
  `proxmox-retained`, no Namespace `csi-proxmox`, no PrometheusRule `proxmox-csi-capacity`.

- [ ] **Step 1: Entry gate (read-only).**
  - `jq '[.[] | select(.origin=="migrated" and .copied)] | length'
    infrastructure/base-configs/files/retained-volumes.json` on apps main. Expected: `33`.
  - `git -C $RA grep -n -E "proxmox-retained|csi\.proxmox\.sinextra\.dev" origin/main -- ':!docs'` lists only the files
    in **Files** above, and no binding file.
  - `KUBE get volumeattachments -o jsonpath='{range .items[*]}{.spec.attacher}{"\n"}{end}' | sort -u`. Expected: only
    `org.democratic-csi.node-manual`.
  - `KUBE get pv -o json`, filtered with python to the PVs whose `spec.csi.driver == "csi.proxmox.sinextra.dev"`. Print
    the name, `persistentVolumeReclaimPolicy`, `status.phase`, `claimRef` and `metadata.finalizers`. Expected:
    - every one is `Retain`;
    - none is claimed by a PVC that a Pod mounts (cross-check `KUBE get pods -A -o json` volumes);
    - no finalizer other than `kubernetes.io/pv-protection`. An `external-attacher/...` finalizer is UNVERIFIED; if one
      appears, stop and bring it to Ben.

  Write `evidence/5.1/gate.md`.
- [ ] **Step 2: Ben's rollback gate.** After this merge no Proxmox CSI PV can be created, so the reverse copy of
  Task 2.5, and with it the 4.T rollback "after writes", ends for every volume at once. Recommendation: start only once
  the last cutover's `copied` date is at least 7 days old (D27), matching 5.7's one-week rule. **Ben OK** to end
  rollback by reverse copy.
- [ ] **Step 3: Leftover live PV/PVC objects** (only if Step 1 listed any). They carry `Prune=false,Delete=false`
  (for example `media-block-storage/lidarr-bindings.yaml:6,43` on origin/main), so they outlive their Git files. This
  runs while the controller still runs.
  - Per volume: `KUBE -n <ns> delete pvc <old claim>`, then `KUBE delete pv <old pv>`. **Ben OK** per volume.
  - Expected: both are gone. `Retain` leaves the image: `pvesm list k3s-block --vmid 9999` still lists
    `vm-9999-<x>.raw`.
- [ ] **Step 4: Write the change** (Files above).
  - Run:
    - `cd $RA && python3 scripts/homepage/generate.py --check`;
    - `python3 -m unittest discover -s scripts/homepage/tests -v`;
    - `python3 -m unittest discover -s scripts/storage/tests -v`;
    - `python3 scripts/check-retained-inventory.py`;
    - `python3 scripts/check-alert-policy.py docker run --rm -i --network none --entrypoint promtool
      prom/prometheus:v3.16.0`;
    - `yamllint .`.
  - Expected: all PASS. `check_bindings` (Task 2.6) still passes, since its static-PVC list only shrinks.
- [ ] **Step 5: Commit:**
  `g -C $RA commit -am "chore(storage): retire Proxmox CSI: chart, settings, slot alerts and panels (ADR 0017)"`.
- [ ] **Step 6: PR and merge** (**Ben OK**).
  - Merge event: ArgoCD syncs.
    - The appset drops Application `proxmox-csi`, and its `resources-finalizer` (`cluster-apps.yaml:69`) deletes the
      controller, the node DaemonSet, the CSIDriver and the StorageClass.
    - `sealed-secrets` prunes Namespace `csi-proxmox` with its Secret and ConfigMap (`prune: true`, `:88`).
    - kube-prometheus-stack prunes the PrometheusRule.
    - homepage-admin and Grafana reload.
  - Hold other apps merges until Step 7 passes.
- [ ] **Step 7: Check.**
  - `KUBE get application -n argocd proxmox-csi` gives NotFound.
  - `KUBE get csidriver,sc` shows no `csi.proxmox.sinextra.dev` and no `proxmox-retained`.
  - `KUBE get ns csi-proxmox` gives NotFound.
  - `KUBE -n monitoring get prometheusrule proxmox-csi-capacity` gives NotFound.
  - Every Application is `Synced`/`Healthy`, and every retained app is Running with its guard init container
    `Completed`.
  - The homepage-admin Capacity tile renders.

  Write the outputs to `evidence/5.1/`.

### Task 5.2: ansible: node-retirement vars, CSI topology, excludes, preflight

Two PRs plus a docs PR, all in worktree `$RN`:
- **5.2a** `chore/retire-csi-topology`: vars move, plus removing `proxmox_csi.yml` and its wiring. Merge event: full
  deploy.
- **5.2b** `chore/backup-drop-vm-9999-excludes`: merged only after 5.7 has deleted all five regen images
  (`vm-9999-{prometheus,loki,tempo,alertmanager,karakeep-meilisearch}.raw`). Before that, dropping an exclude makes
  the next `daily` restic run upload a regenerable image off-site. Merge event: `proxmox-backup.yml` only (both files
  are in `deploy.yml` `paths-ignore`, `:22-25`).
- **5.2-docs** `docs/retire-csi`: the docs, squash subject with `[skip ci]`.

**Files:**
- 5.2a:
  - Create `group_vars/all/k3s_node_retirement.yml`, holding `proxmox_csi.yml:18-22` verbatim with their comments:
    `k3s_node_retirement_enabled: true`, and
    `k3s_node_retirement_ca_path: "{{ playbook_dir }}/files/proxmox-api-trust.pem"`;
  - Delete `group_vars/all/proxmox_csi.yml` and `roles/bootstrap_cluster/tasks/proxmox-csi.yml`;
  - Modify `roles/k3s_common/tasks/main.yml`:
    - drop task 1 "Validate enabled Proxmox CSI topology..." (`:1-14`);
    - drop the `{% if proxmox_csi_enabled %} node-label ...{% endif %}` block (`:82-87`);
  - Modify `roles/bootstrap_cluster/tasks/main.yml`: drop the include task (`:2-6`);
  - Test `scripts/tests/test_proxmox_csi_bootstrap.py`. It reads `proxmox_csi.yml` at `:22-24,82,105`.
- 5.2b:
  - Modify `roles/proxmox_backup/defaults/main.yml`, `proxmox_backup_excludes` (`:43-47`). The regen line from Task
    2.8 stays;
  - Test `scripts/tests/test_proxmox_backup.py`, `test_excludes_cover_regenerable_images` (`:328-334`).
- 5.2-docs: `CLAUDE.md:32-33,64-66,94`, `README.md:101,104,110,115,120,136,180` (README is in `paths-ignore`; it
  rides here anyway), `docs/maintenance-coordination.md` "Proxmox CSI bootstrap" (`:154`) and
  `docs/backup-and-restore.md:29` (after 5.2b).
  - Also `docs/proxmox-csi-storage.md`: a first line saying never to run `proxmox-csi-storage.yml` after Task 5.4. It
    would recreate the pool, user, token and ACLs.
- Unchanged:
  - `roles/k3s_node_retirement/`. The ADR keeps it, and it has no CSI or SCSI reference (`git grep -i -E
    "scsi|csi|volumeattachment" origin/main -- roles/k3s_node_retirement` is empty).
  - `files/proxmox-api-trust.pem`: retirement and the preflight use it.
  - `roles/proxmox_csi_storage/`: see Not in this plan.

**Interfaces:**
- Consumes: `k3s_node_retirement_enabled` (`k3s.yml:82`); `k3s_node_retirement_ca_path`
  (`roles/k3s_node_retirement/tasks/main.yml:43`, `csi-activation-preflight.yml:18`).
- Produces: the same two variables from `group_vars/all/k3s_node_retirement.yml`, and no `proxmox_csi_*` variable
  anywhere.

- [ ] **Step 1 (5.2a, commit 1): Write the failing test.** In `test_proxmox_csi_bootstrap.py`, repoint
  `test_production_activation_keeps_explicit_opt_out` (`:104-115`):
  ```python
  retirement = read("group_vars/all/k3s_node_retirement.yml")
  self.assertIs(retirement["k3s_node_retirement_enabled"], True)
  self.assertEqual(retirement["k3s_node_retirement_ca_path"], "{{ playbook_dir }}/files/proxmox-api-trust.pem")
  self.assertNotIn("k3s_node_retirement_enabled", read("group_vars/all/proxmox_csi.yml"))
  ```
  Run: `. ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh && cd $RN && $VPY
  scripts/tests/test_proxmox_csi_bootstrap.py`. Expected: FAIL (the file does not exist).
- [ ] **Step 2: Move the two vars** (Files). Run Step 1, then `$VPY scripts/tests/test_node_retirement.py` and
  `$VPY scripts/tests/test_csi_preflight.py`. Expected: PASS.
  Commit: `g -C $RN commit -am "refactor(k3s): node-retirement settings in their own group_vars file"`. Run `git add`
  for the new file first.
- [ ] **Step 3 (5.2a, commit 2): Write the failing tests.** In `test_proxmox_csi_bootstrap.py`:
  - delete `test_new_nodes_get_inventory_topology`, `test_invalid_topology_fails_before_host_configuration`,
    `test_existing_nodes_receive_the_same_host_specific_labels` and
    `test_bootstrap_tags_select_the_included_operations`;
  - `variables()` stops reading `proxmox_csi.yml` and setting `proxmox_csi_*`;
  - keep `test_disabled_preserves_exact_config_bytes` with its expected bytes, including the branch's
    `disable-force-detach-on-timeout=true` line;
  - from `test_production_activation_keeps_explicit_opt_out`, keep only the Step 1 retirement assertions;
  - add:
    ```python
    def test_no_proxmox_csi_topology_left(self):
        for path in ("group_vars/all/proxmox_csi.yml", "roles/bootstrap_cluster/tasks/proxmox-csi.yml"):
            self.assertFalse((ROOT / path).exists(), path)
        for p in [*ROOT.glob("roles/**/*.yml"), *ROOT.glob("group_vars/**/*.yml"), ROOT / "k3s.yml"]:
            self.assertNotRegex(p.read_text(), r"proxmox_csi_(enabled|region|node_labels)", str(p))
        for groups in (["workers"], ["masters"]):  # a stray flag must not bring labels back
            config = yaml.safe_load(self.render_config(self.variables(group_names=groups, proxmox_csi_enabled=True)))
            self.assertNotIn("node-label", config)
    ```

  Run Step 1's command. Expected: FAIL (the files still exist).
- [ ] **Step 4: Remove** the files and blocks listed under 5.2a.
  - Run:
    - Step 1's command;
    - `$VPY scripts/tests/test_node_retirement.py`;
    - `$VPY scripts/tests/test_csi_preflight.py`;
    - the `validate.yml:125` syntax check under `$VPY15`
      (`ansible-playbook --syntax-check k3s.yml ... csi-activation-preflight.yml proxmox-backup.yml`, the list as on
      the branch);
    - `ansible-lint --offline`, with the dummy `.vault_pass` as in Task 2.2 Step 4.
  - Expected: PASS.
  - Commit: `g -C $RN commit -am "chore(k3s): drop the Proxmox CSI topology labels and slot budget (ADR 0017)"`.
- [ ] **Step 5: Decide `csi-activation-preflight.yml`** (Ben). What it does (`csi-activation-preflight.yml:1-110`):
  - it proves sealed-secret recovery with the external Vault key;
  - it proves strict TLS and complete Proxmox visibility for the deployment token, which is the gate for
    `k3s_node_retirement` (`docs/maintenance-coordination.md:106`);
  - only its optional ciphertext inputs are CSI-specific (`.github/workflows/csi-activation-preflight.yml:4-12`).

  Recommendation: keep it unchanged. The rename and dropping the CSI inputs are in Not in this plan. Record the decision
  in `evidence/5.2/`.
- [ ] **Step 6: Merge 5.2a** (**Ben OK**).
  - Merge event: `deploy.yml` (push). `k3s.yml` rewrites each node's k3s config without `node-label`, and k3s restarts
    on every node, one at a time. Bootstrap no longer patches labels.
  - Merge only outside backup windows, with no cutover open, and with apps merges held.
- [ ] **Step 7: Check the live labels.**
  - `KUBE get nodes -L topology.kubernetes.io/region,topology.kubernetes.io/zone,\
    csi.proxmox.sinextra.dev/max-volume-attachments` (one argument, no space).
  - Whether k3s removes labels dropped from `node-label` is UNVERIFIED. If they remain, run per node (**Ben OK**):
    `KUBE label node <n> topology.kubernetes.io/region- topology.kubernetes.io/zone-
    csi.proxmox.sinextra.dev/max-volume-attachments-`.
  - Expected: the three columns are empty. `intel.feature.node.kubernetes.io/gpu` is unchanged, because
    `roles/k3s_workers/tasks/main.yml:29-40` sets it.
  - The next k3s restart (5.3's dispatched deploy) must not bring the labels back. Check again after it.
- [ ] **Step 8 (5.2b): Write the failing test**, after 5.7 has deleted the five regen images:
  ```python
  images = ['/srv/backup-src/k3s-block/images/<D1:placeholder_vmid>/<regen_volname>']   # Task 2.8's line only
  self.assertEqual(sorted(lines), sorted(images + ['/srv/backup-src/immich/thumbs',
                                                   '/srv/backup-src/immich/encoded-video']))
  ```
  Run: `cd $RN && $VPY scripts/tests/test_proxmox_backup.py`. Expected: FAIL (the five lines are still rendered).
- [ ] **Step 9: Remove** the five `vm-9999` lines (`defaults/main.yml:43-47`) and Task 2.8's comment
  `# ... the five above go at Retirement`.
  - Run Step 8. Expected: PASS.
  - Commit: `g -C $RN commit -am "chore(backup): drop the vm-9999 regen excludes after their images are gone"`.
  - Merge (**Ben OK**). The event is `proxmox-backup.yml`, which rewrites `/etc/homelab-backup.d/excludes.txt` on pve.
  - Check:
    - `pve` row `cat /etc/homelab-backup.d/excludes.txt` shows three lines;
    - the next `daily` run is green (`journalctl -u homelab-backup@backup.service` "Added to the repository", no
      `PROBLEM`).
- [ ] **Step 10: 5.2-docs.**
  - Edit the files listed under 5.2-docs.
  - Commit: `g -C $RN commit -am "docs: retire the Proxmox CSI topology notes"`.
  - The squash subject carries `[skip ci]`. Memory `pr-merge-mechanics`: a docs-only ansible merge needs `--admin`.
  - Merge event: none. **Ben OK**.

### Task 5.3: terraform: remove `k3s_resource_pool` and the `disks[0].scsi` ignore

Strictly after the last detach, which is 5.1 Step 1's zero Proxmox CSI VolumeAttachments. It runs before 5.4.

**Files** (worktree `$RT`, branch `chore/retire-csi-pool` off `origin/main`):
- Modify:
  - `variables.tf:106-115`: delete `variable "k3s_resource_pool"`;
  - `terraform.tfvars:30`: delete the `k3s_resource_pool` line;
  - `main.tf:28,61`: delete `pool = var.k3s_resource_pool` in `master_nodes` and `worker_nodes`;
  - `modules/vm/main.tf:293-297`: drop `disks[0].scsi` and its comment from `ignore_changes`, and keep
    `startup_shutdown`. The module variable `pool` stays, defaulting to `null`
    (`modules/vm/variables.tf:155-159`);
  - docs, in the same PR: `README.md:54-60`, `CLAUDE.md:51-52,75` and
    `docs/storage-safe-maintenance.md:43-53,111-126`. No skip marker is needed, because this PR must apply.
- Test: `scripts/tests/test-rebuild-cohort.py:136-146` (the pool block), run by `validate-and-plan.yml:37`.

**Interfaces:**
- Consumes:
  - the wwn guard (Task 1.4): `scripts/csi_wwn_guard.py` `scsi_updates(plan)`, which flags an in-place update whose
    prior state holds a SCSI disk;
  - the pool `k3s-csi`.
- Produces: no pool membership in config. 5.4 then finds the pool empty.

- [ ] **Step 1: Write the failing test.** Replace the pool block with:
  ```python
  enrolled = copy.deepcopy(legacy)
  for node in NODES:
      attributes(enrolled, node)['pool'] = 'offline-csi'
  document = check('pool removal updates VMs without replacement', enrolled, {node: ['update'] for node in NODES})
  assert all(change['change']['after'].get('pool') in (None, '') for change in document['resource_changes'])
  refusal = run(root, 'plan', '-refresh=false', '-input=false', '-no-color', '-var=k3s_resource_pool=x', success=False)
  assert 'undeclared variable' in (refusal.stdout + refusal.stderr).lower()
  ```
  Run:
  `. ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh && cd $RT && TERRAFORM=$TF $VPY
  scripts/tests/test-rebuild-cohort.py`. Set `COHORT_PLUGIN_DIR` as Task 0.1 does (`test-rebuild-cohort.py:19,89-90`).

  Expected: FAIL (`-var=k3s_resource_pool=x` is accepted).
- [ ] **Step 2: Implement** (Files). Run Step 1, `$TF fmt -check -recursive` and `$TF validate`. Expected: PASS.
  Commit: `g -C $RT commit -am "chore: drop the Proxmox CSI pool and SCSI ignore after the last detach (ADR 0017)"`.
- [ ] **Step 3: Read-only pre-check.**
  - `pve` rows `qm config <vmid> | grep -E '^scsi[0-9]+:'` for the master and both workers (VMIDs from
    `pvesh get /cluster/resources --type vm`). Expected: empty.
  - `pvesh get /pools/k3s-csi --output-format json`: record the members.
- [ ] **Step 4: Open the PR** (**Ben OK**). The title and body carry no skip marker (Global Constraints). Apply mode
  normal. Read the plan comment.
  - Expected: three in-place `update`s (master and both workers), with only `pool` changing, and nothing under
    `disks`.
  - The wwn guard reports nothing. That is the proof that state holds no SCSI slot. If it lists any VM, STOP: never
    tick the ack, and bring it to Ben.
  - Whether telmate reboots on a pool-only update is UNVERIFIED. Read it from the plan and the apply log.
- [ ] **Step 5: Merge** (**Ben OK**).
  - Merge event: apply with auto-approve. `has_changes` is true, so it dispatches `infrastructure-changed`, which runs
    a full deploy with k3s restarting on every node.
  - Hold apps merges until the deploy ends. The wwn rule of the Global Constraints lapses with this merge.
- [ ] **Step 6: Check.**
  - The apply log shows `3 changed`.
  - `pvesh get /pools/k3s-csi` lists no `qemu` member. If one remains, removing it is a 5.4 step.
  - The node bootIDs are recorded against Step 3:
    `KUBE get nodes -o jsonpath='{range .items[*]}{.metadata.name} {.status.nodeInfo.bootID}{"\n"}{end}'`.
  - The deploy is green, and 5.2 Step 7's labels are still absent.
  - A follow-up `terraform plan` (the next PR's plan or `drift.yml`) shows no change.

  Write the outputs to `evidence/5.3/`.

### Task 5.4: Proxmox side (live): CSI pool, user, token, ACLs

The names come from `roles/proxmox_csi_storage/defaults/main.yml:3-19` and `shared-storage-settings.json`:
- pool `k3s-csi`;
- user `kubernetes-csi@pve`;
- token `retained`;
- role `HomelabCSI`;
- ACL paths `/pool/k3s-csi` (propagate 1), `/storage/k3s-block` and `/vms/9999`.

Each path is granted to both the user and the token (`tasks/main.yml:306-328`).

Never touch:
- the storage `k3s-block`. Its registration stays, because the storage VM's data disks live there;
- `images/9999`, which is Task 5.7's;
- the deployment tokens.

Refer to tokens by name only.

**Files:** evidence only, `evidence/5.4/`.
**Interfaces:**
- Consumes: 5.3's empty pool.
- Produces: no CSI identity on pve.

- [ ] **Step 1: Read-only** (`pve` rows):
  - `pvesh get /pools/k3s-csi --output-format json`;
  - `pveum acl list --output-format json`, filtered with python to print `path ugid roleid propagate` for rows whose
    `ugid` starts with `kubernetes-csi@pve` or whose `roleid` is `HomelabCSI`;
  - `pveum user token list kubernetes-csi@pve --output-format json` (token ids only);
  - `pveum role list --output-format json`, keeping `HomelabCSI`;
  - `pvesm status --storage k3s-block`;
  - `pveum help acl`, `pveum help user` and `pvesh usage /pools/{poolid} -v` to confirm the spellings below
    (UNVERIFIED until this read).

  Expected:
  - the pool has no members;
  - there are exactly six ACL rows: three paths, each for the user and the token;
  - no other ugid uses `HomelabCSI`;
  - `k3s-block` is active.
- [ ] **Step 2: Delete the ACLs**, one row at a time (**Ben OK** per path):
  - `pveum acl delete <path> --roles HomelabCSI --tokens 'kubernetes-csi@pve!retained'`;
  - `pveum acl delete <path> --roles HomelabCSI --users kubernetes-csi@pve`.

  Expected: Step 1's filter prints nothing.
- [ ] **Step 3: Delete the token, the user and the role** (**Ben OK** each):
  - `pveum user token remove kubernetes-csi@pve retained`;
  - `pveum user delete kubernetes-csi@pve`;
  - `pveum role delete HomelabCSI`, only if Step 1 showed no other user of it.

  Expected: the user is absent from `pveum user list`, and the role is absent from `pveum role list`.
- [ ] **Step 4: Delete the pool** (**Ben OK**). If 5.3 Step 6 left a member, first run
  `pvesh set /pools/k3s-csi --vms <vmid> --delete 1` (UNVERIFIED spelling; Step 1's usage read decides). Then run
  `pvesh delete /pools/k3s-csi`.
  - Expected: `pvesh get /pools` has no `k3s-csi`, and `pvesm status --storage k3s-block` is still active.
  - The next `storage.yml` run is green.
  - The next terraform plan shows no change.
- [ ] **Step 5: Remove the CSI token file on VM300** without reading it. The path
  `/var/lib/homelab-maintenance/private/proxmox-csi.json` is inferred from `shared-storage-settings.json:8`
  (`/maintenance/private/proxmox-csi.json`) and the container mount `deploy.yml:41`, so it is UNVERIFIED.
  - Run `test -f <path> && rm -f <path>` on VM300, by Ben or through a path he approves (**Ben OK**). Never `cat` it.
  - Expected: `test -e <path>` fails.

### Task 5.5: Fencing stays held; Check 11 at 300 s

Automatic fencing stays off (Ben, 2026-11-21): `hold_fence` stays on `retained`, `storage-fencer` keeps running and
refuses every new fence, and the manual fence (`storage-fencer fence`, runbook `storage-vm-fencing.md`) stays the only
fence. Removing `hold_fence` and gate R1 are not in this plan (see Not in this plan).

**Files:**
- Modify (apps, `$RA`, branch `docs/storage-fencing-after-retirement`): `docs/runbooks/storage-vm-fencing.md` (Task
  2.7). Drop the migration-only passage: `qm stop` before the taint when a worker holds a non-node-manual
  VolumeAttachment (ADR `:597-604`, "Until Retirement only"). Step 1 proves no such VolumeAttachment is left. Say in
  the runbook that `hold_fence` stays on `retained` after Retirement, so the manual fence is still the only fence.
- Evidence: `evidence/5.5/`.

**Interfaces:**
- Consumes:
  - `<retained_pv>`, which is `storage_vm_pv_devices.retained` from Task 3.5;
  - the worker VMIDs and names;
  - `not_ready_seconds` 300 (production default, lab plan Global Constraints);
  - `$EVR/0.3/d22.txt` (the journal scope, D22).
- Produces: proof that no Proxmox CSI VolumeAttachment is left and that `hold_fence` is still set; Check 11 at 300 s.

- [ ] **Step 1: Pre-check (read-only).**
  - Run `KUBE get volumeattachments -o jsonpath='{range .items[*]}{.spec.attacher}{"\n"}{end}' | sort -u`. Expected:
    only `org.democratic-csi.node-manual`. This is the lab runbook's check (`b6/runbook.md:90`): no Proxmox CSI
    VolumeAttachment remains, so the migration-only `qm stop` step can no longer apply.
  - Run `qm config <worker vmid> | grep -E '^scsi[0-9]+:'` for both workers. Expected: empty.
  - Run `KUBE get csidriver`. Expected: no `csi.proxmox.sinextra.dev`.
  - Run `SVM vgs --devices <retained_pv> --readonly --noheadings -o vg_tags retained`. Expected: `hold_fence`, and no
    `fenced:` tag and no `hold_create`. `hold_create` would mean a whole-disk restore is still open (ADR `:674`).
  - Run `SVM storage-fencer status`. Expected: `"fenced": {}` and `"holds": ["hold_fence"]`.
  - Run `SVM systemctl is-active storage-fencer`. Expected: `active`. The fencer still ships and runs; it refuses.
  - Both workers are Ready, and no node has the out-of-service taint.
  - D28 (the fencer token after a k3s rebuild) is deferred (Ben, 2026-11-21) with the rest of automatic fencing, so
    this step does not revisit it. `StorageFencerBlind` still reports a blind fencer.

  Write the outputs to `evidence/5.5/precheck.md`.
- [ ] **Step 2: Check 11 at 300 s.** It runs at the first planned worker reboot after the last Proxmox CSI detach
  (Step 1 has passed), with fencing held. Ben picks the worker and the time; it must be an unfenced worker with
  volumes staged, outside the backup windows, with no cutover open.
  - Because the fencer refuses every new fence, this check's "no fence" expectation is met trivially. What it still
    proves at 300 s: the shutdown order, the VolumeAttachment release before poweroff, and that the worker's NotReady
    time stays under the 300 s threshold, so the same reboot would not fence once fencing is turned on.
  - Worker reads below use Part 3's `VM <vmid> '<cmd>'`: a `pve` row `qm guest exec <worker vmid> -- bash -c
    '<cmd>'` (QGA; no SSH key reaches the workers). ASCII only, no `'` inside, double quotes for patterns.
  - Before the reboot (read-only):
    - `VM <vmid> 'journalctl --header -n0 | grep -m1 "File path"'` shows `/var/log/journal/`. That is D22
      (`storage VM and workers`, Task 0.3). If it shows `/run/log/journal/`, the previous boot will be gone: STOP and
      bring it to Ben before the reboot;
    - the map of each staged disk to its target and its pod:
      `VM <vmid> 'ls -l /dev/disk/by-path | grep -E "iscsi-iqn"; iscsiadm -m session'`, and the container IDs of the
      pods mounting those volumes, from `KUBE get pods -A -o json` (`status.containerStatuses[].containerID`,
      `spec.nodeName == <n>`). Record T0.
  - The reboot is `qm reboot <vmid>` with no drain (**Ben OK**).
  - After the boot (read-only), the previous boot's journal on that worker, cut to the shutdown (one `pve` row; the
    lines below are one command):
    ```
    VM <vmid> 'journalctl -b -1 -o short-precise --no-pager | grep -E
      -e "cri-containerd-.*scope: (Deactivated|Stopping timed out)" -e "Stopping k3s-agent"
      -e "EXT4-fs \(sd[a-z]+\): unmounting filesystem" -e "\[sd[a-z]+\] Synchronizing SCSI cache"
      -e "iscsid.*Connection[0-9]+:0 to .*is shutdown" -e "logout-all.sh"'
    ```
    These are the lines the lab read (`storage-lab/b10/f14/journal-lega-prev-boot.txt:54-82`).
  - The fencer's view of the reboot (read-only):
    `SVM journalctl -u storage-fencer --since <T0> --no-pager | grep -E "<n>: |NotReady past|fence <n>"`.
  - Expected:
    - `journalctl --list-boots` on the worker has a `-1` entry;
    - per staged volume, in time order: every app container scope from the map is `Deactivated` (none `Stopping timed
      out`), then `EXT4-fs (<sdX>): unmounting filesystem`, then `[<sdX>] Synchronizing SCSI cache` (the disk
      removed), then the `iscsid` `Connection<N>:0 to [target: <its IQN>` line ending `is shutdown`. So the apps stop
      before iscsid logs out, and each ext4 unmount comes before its disk is removed. Any other order is F21 again:
      STOP and bring it to Ben;
    - `logout-all.sh` finds no session left (`No matching sessions found`): the driver logged out, not the system
      unit;
    - no fence: the fencer journal has no `NotReady past` line and no `fence <n>:` line since T0, and
      `storage_fence_active` stays 0. With `hold_fence` set this holds by construction;
    - while the worker is NotReady, the fencer logs `<n>: not-ready-too-short` (or `watch-too-short`). It logs the
      hold refusal `<n>: hold_fence` only once the worker has been NotReady past 300 s with a Ready peer
      (`fence_policy.py:114-123`, A branch `a036b47`). So a `<n>: hold_fence` line means the reboot outlasted the
      threshold and would have fenced with fencing on: record it and bring it to Ben;
    - the worker's NotReady time is under 300 s. The Node's Ready condition keeps only its last transition, so read
      it within the hour (the event TTL) from `KUBE get events -n default --field-selector
      involvedObject.kind=Node,involvedObject.name=<n> -o wide`: the `NodeNotReady` event to the `NodeReady` event.
      Cross-check it with the first and last `<n>: not-ready-too-short` lines in the fencer read above. Record it;
    - the VolumeAttachments are released before poweroff;
    - no out-of-service taint;
    - the volumes restage after the boot;
    - the ADR Check 11 items hold (`/configz` shows `1m30s`/`40s`).
  - After the worker reboots, pods may fail admission with `UnexpectedAdmissionError` (memory `gpu-admission-race`).
    Delete them by hand (**Ben OK**).

  Write `evidence/5.5/check11.md`: T0, the disk/target/pod map, the journal excerpts above with their timestamps,
  the ordering verdict per volume, the fencer lines, the longest NotReady age, and the other Expected items.
- [ ] **Step 3: The fencing runbook PR** (Files; **Ben OK**). Merge event: none (docs only; ArgoCD ignores `docs/`).

### Task 5.6: .github: contract rows and profile

**Files** (`$GR`, branch `docs/storage-vm-contracts` off `origin/main`). `CLAUDE.md` is also
`~/Projects/homelab/CLAUDE.md` (symlink).
- `CLAUDE.md`:
  - `:11`: packer "Debian 13 Proxmox template (VM 900)" becomes templates 900 (base), 901 (k3s) and 902 (storage);
  - trigger chain `:18-27`:
    - step 1 opens one manifest PR carrying the k3s and storage entries (Task 2.11 Step 4a, D16);
    - add apps `storage-changed` to ansible `storage.yml`, plus the hourly run and the daily `storage-expiry.yml`;
  - contract index:
    - replace `:47` "CSI pool, slots, topology" with these rows:
      - **Storage inventory**: apps `infrastructure/base-configs/files/retained-volumes.json` and
        `scripts/check-retained-inventory.py` → ansible `roles/storage_vm/` (`inventory.py`), `storage.yml`;
      - **Storage image**: packer `build-storage.pkr.hcl` manifest (`storage` entry: `artifact_id`,
        `custom_data.vm_name`) → terraform `scripts/storage_template_env.sh` (`storage_template_vmid`,
        `storage_template_name`) and `scripts/check_clone_source.py` (D16);
      - **Storage root disk**: packer `source-base.pkr.hcl` `disks` ↔ terraform `storage/main.tf` `virtio0` (a root
        disk over 4 GiB fails the create part-way, ADR "Changes per repo"; checked at create by terraform
        `scripts/check_clone_source.py` since Task 2.1a Step 8a);
      - **Retained id pattern** (Task 2.6 audit fold-in): apps `scripts/check-retained-inventory.py` `ID_PATTERN` ↔
        ansible `roles/storage_vm/files/homelab_storage/inventory.py` `ID_PATTERN`;
      - **Startup order**: ansible `group_vars/proxmox_hosts/guest_startup.yml` ↔ terraform `storage/terraform.tfvars`
        VMID;
      - **Storage network**: ansible bridge role and `storage_vm_*` group_vars ↔ apps `templates/globals.yaml`
        `storagePortal` and `storage-vm.yaml` scrape target;
      - **Fencer credential**: apps `infrastructure/system/democratic-csi/manifests/storage-fencer.yaml` → ansible
        `storage.yml` token copy;
    - `:49`: keep `csi-activation-preflight.yml` if 5.2 Step 5 kept it;
    - `:50` Worker labels: drop the `proxmox-csi/values.yaml` consumer;
    - `:52` Backup inputs: drop `vm-9999-*` (after 5.2b), and keep Task 2.8's storage VM images;
  - source of truth:
    - `:61`: "CSI resource pool" becomes "storage VM VMID, size and data disks";
    - `:62`: "CSI slot budget and topology" becomes "storage VM role, fencer and LVM layout".
- `profile/README.md`:
  - `:27`, the template;
  - `:34`, the app count: recount, as 5.1 does;
  - `:87`, the preflight row, reworded to "Read-only check of the deployment token's Proxmox visibility and
    sealed-secret recovery", if it was kept;
  - `:127`, Cluster storage: "Retained block volumes from a storage VM over iSCSI (ADR 0017), plus NFS from
    TrueNAS".
- Diagrams `docs/diagrams/platform.svg:3,186`, `delivery-chain.svg:126` and `workflow-map.svg:207` (from Task 0.1
  `unowned-stale.md`), plus any CSI box. The kit has no `.github` templates (`kit/gen_shared.py:8` covers packer,
  terraform, ansible and apps only), so edit these SVGs by hand. Whether another tool exists is UNVERIFIED; ask Ben.
  `check-readme-images.py` must pass.

**Interfaces:**
- Consumes: the decisions of 5.2 Step 5 and 5.2b, D1/D16 values, and Task 5.13 (template VMID 901, the bpg `tags` and
  `initialization.ip_config` contract).
- Produces: the CLAUDE.md that every repo session loads.

- [ ] **Step 1: Edit** as listed. Keep `profile/README.md` consistent with `CLAUDE.md` (CLAUDE.md:5).
- [ ] **Step 2: Run** `python3 scripts/check-readme-images.py` in the worktree. Expected: PASS. Then
  `git grep -n -i -E "proxmox csi|k3s-csi|proxmox_csi|slots"`. Expected: only historical mentions that Ben accepts.
- [ ] **Step 3: Commit** (per-repo commits, CLAUDE.md "Working across repos"):
  `docs: storage VM contracts replace Proxmox CSI (ADR 0017)`. List repo, files and message in `evidence/5.6/` for Ben.
  A second commit on the same branch is Task 5.13 Step 14 (the contract index).
- [ ] **Step 4: PR and merge** (**Ben OK**). Merge event: `readme-images.yml` only.

### Task 5.7: Old images

One deletion per step. Each one runs only when all of these hold:
- the app's `copied` date is at least 7 days old;
- 5.1 has merged, so no PV references the image;
- Ben approves that image.

Never inside a backup window.

**Files:** evidence only, `evidence/5.7/<image>.md`.
**Interfaces:**
- Consumes: the inventory `copied` dates and the `pvesm list k3s-block --vmid 9999` names.
- Produces: freed space (after snapshot expiry: 1 week on TrueNAS, 2 weeks on `usbbk`, ADR Capacity). The five regen
  deletions unblock 5.2b.

- [ ] **Step 1: List (read-only).**
  - `pvesm list k3s-block --vmid 9999` gives each image's name and size.
  - Join it with the inventory's `copied` dates.
  - `KUBE get pv -o json`: no PV whose `volumeHandle` ends in that image name.
  - `pvesm help free` confirms the spelling (UNVERIFIED until read).

  Write `evidence/5.7/list.md` with image, size, app, `copied` and eligible date.
- [ ] **Step 2: Per image, ask Ben** with exactly this line:
  `Delete k3s-block:9999/vm-9999-<x>.raw (<size> GiB, app <app>, on new storage since <copied>). This cannot be undone;
  the only copies left are TrueNAS/usbbk snapshots until they expire, and restic history.`
  Expected: **Ben OK** for that one image.
- [ ] **Step 3: Delete it:** `pvesm free k3s-block:9999/vm-9999-<x>.raw` (`pve` row).
  - Expected: it is absent from `pvesm list k3s-block --vmid 9999`.
  - The app is unchanged.
  - `zfs get -Hp used,usedbysnapshots apps/k3s-block` (`tn` row) shows the space held by snapshots, until they expire.
- [ ] **Step 4:** After the fifth regen image (`prometheus`, `loki`, `tempo`, `alertmanager`, `karakeep-meilisearch`),
  run Task 5.2 Steps 8-9 (5.2b).

### Task 5.8: Scale gate: one worker carries every retained volume

Requirement 1 exists because losing a worker stranded volumes over the 29-slot budget (ADR `:26-28`). The lab ran 3
volumes (ADR `:889`). This gate puts every retained volume on one worker, then on the other, and reads a clean
shutdown at that count. It runs after 5.5 Step 2, in a planned window Ben picks: outside the backup windows, with no
cutover open, and holding the maintenance lock the whole time. Each half takes every app down for one worker reboot;
Ben picks a time when that is acceptable.

**Files:** evidence only, `evidence/5.8/`.

**Interfaces:**
- Consumes:
  - `<N>`: the number of PVs with `spec.csi.driver == "org.democratic-csi.node-manual"` that a Pod mounts (33 at
    the Part 5 entry, plus any entry added since);
  - the worker VMIDs and names; `<A>` is drained first, `<B>` carries the load first;
  - Task 4.0 Step 9's `lock.sh` on VM300 and its `lock_sh_sha256`;
  - 5.5 Step 2's journal read (Check 11).
- Produces: `evidence/5.8/scale.md` with `<N>`, the counts per half, the ordering verdict per volume and the longest
  preStop hold, and `scale_gate_pass`.

- [ ] **Step 1: Pre-check (read-only).**
  - Run the window check (Part 4, "Window check"). Expected: not in a backup window, and the whole gate fits.
  - Run 5.5 Step 1. Expected: as there.
  - `KUBE get nodes` and `KUBE get applications -n argocd`. Expected: both workers Ready, every Application
    `Synced`/`Healthy`.
  - `[R] sha256sum /run/homelab-cutover/lock.sh /run/homelab-cutover/maintenance_lock.py`. Expected: the hashes in
    `evidence/4.0/facts.md`. If `/run` was cleared by a VM300 reboot, re-stage both as Task 4.0 Step 9 does
    (**Ben OK**).
  - `KUBE get volumeattachments -o jsonpath='{range .items[*]}{.spec.nodeName} {.spec.attacher}
    {.status.attached}{"\n"}{end}' | sort | uniq -c` (one line). Record the split per worker; the sum is `<N>`.
  - `KUBE get pods -A -o wide --field-selector spec.nodeName=<A>`. Record the pods that need a node resource the
    other worker may lack (GPU, memory). Whether one worker fits every pod is UNVERIFIED; this step lists the risk,
    and Ben decides whether to go on.
- [ ] **Step 2: Take the maintenance lock** (**Ben OK**):
  `[R] sh /run/homelab-cutover/lock.sh acquire scale-gate claude-code/scale-gate/<ts>`.
  Expected: `storage-cutover:scale-gate claude-code/scale-gate/<ts> <time>`. The nonce stays on VM300. Reusing the
  cutover prefix is deliberate: `lock.sh` hardcodes it, and its only parser, Task 2.5's `lock` refusal, is not run
  here.
- [ ] **Step 3: Cordon and drain `<A>`** (**Ben OK**):
  `KUBE drain <A> --ignore-daemonsets --delete-emptydir-data --timeout=900s`. No `--force`, no
  `--disable-eviction` and no `--grace-period`: every volume detaches through the normal unstage, never by force.
  - Expected: the drain finishes; a PodDisruptionBudget that blocks it is recorded and brought to Ben, never forced.
- [ ] **Step 4: Every retained volume stages on `<B>`** (read-only). Wait until no pod is `Pending` or
  `ContainerCreating` (at most 15 min), then:
  - the VolumeAttachment count above. Expected: `<N> <B> org.democratic-csi.node-manual true`, and nothing on `<A>`;
  - `VM <B vmid> 'iscsiadm -m session | grep -c iqn.2026-11.net.starktastic.storage:'`. Expected: `<N>`;
  - `VM <A vmid> 'iscsiadm -m session'`. Expected: `No active sessions`;
  - `KUBE get applications -n argocd`. Expected: every Application `Synced`/`Healthy`, and every retained app's pod
    Running on `<B>` with its guard init container `Completed`;
  - `KUBE get events -A --field-selector reason=FailedMount` and `reason=FailedAttachVolume`, since the drain.
    Expected: transient Multi-Attach events while volumes move are normal; none still recurring once the pods are
    Running, and none carrying a NodeStage error;
  - the csi-driver logs of the democratic-csi node pod on `<B>` (`KUBE -n democratic-csi get pods -o wide` to find
    it), `logs <pod> -c csi-driver --since=1h | grep -i -E "NodeStageVolume.*(error|fail)"`. Expected: empty.
  - A pod that stays `Pending` for a node resource (not storage) is recorded and brought to Ben; it does not fail
    the storage check, but the gate is not `pass` until Ben accepts it.
- [ ] **Step 5: Clean shutdown at full count.** Run 5.5 Step 2 on `<B>` with `<A>` still cordoned: the read-only
  reads before, `qm reboot <B vmid>` with no drain (**Ben OK**), and the journal reads after.
  - Expected: 5.5 Step 2's Expected lines, for all `<N>` volumes. In addition:
    - the `<N>` `iscsid ... is shutdown` lines all come after the last app scope `Deactivated` and before poweroff;
    - the preStop hold ends within the 40 s critical budget (this assumes the democratic-csi node pod has a
      node-critical priority class, so it stops in the critical phase; UNVERIFIED: no `priorityClassName` is set in
      `infrastructure/system/democratic-csi/`, so read the rendered DaemonSet first and bring a mismatch to Ben):
      add the democratic-csi node pod's container IDs to the map before the reboot; in the previous boot's journal,
      the last app scope `Deactivated` to that pod's `csi-driver` scope `Deactivated` is under 40 s, and no
      `Stopping timed out` line names that pod;
    - after the boot, Step 4's checks pass again on `<B>`.
  - Delete `UnexpectedAdmissionError` pods by hand (**Ben OK**), as in 5.5 Step 2.
- [ ] **Step 6: Uncordon `<A>`** (**Ben OK**): `KUBE uncordon <A>`. Expected: `<A>` Ready and schedulable. Pods stay
  on `<B>`; that is fine.
- [ ] **Step 7: The other way.** Repeat Steps 3-6 with `<A>` and `<B>` swapped, each mutation with its own **Ben OK**.
  Before Step 3, re-run the window check. Expected: as above, with `<N>` on `<A>`.
- [ ] **Step 8: Release the lock** (**Ben OK**): `[R] sh /run/homelab-cutover/lock.sh release scale-gate
  claude-code/scale-gate/<ts>`. Expected: `released`.
  - If any step failed, bring it to Ben before this step; he decides whether to release the lock.
  - Write `evidence/5.8/scale.md`, with `scale_gate_pass: yes` only if Steps 4-5 passed both ways.

### Task 5.9: apps: remove the copy tool

The copy tool is migration-only code on the data path (Task 2.5). The req-5 exception covers it only until this task
deletes it (D45, Ben 2026-11-22). Once 5.1 has merged, no Proxmox CSI PV can be created, so the last reverse-copy
window (D27) is closed and the tool is dead. This task deletes it in one apps PR. Ben asks for the PR; nothing here
opens it unasked.

**Files** (worktree `$RA`, branch `chore/remove-copy-tool` off `origin/main`):
- Delete: `scripts/storage/migrate_volume.py`, `scripts/storage/copy_volume.sh`,
  `scripts/storage/tests/test_migrate_volume.py`, and any template or fixture only they use (re-grep).
- Modify: `scripts/storage/README.md`, dropping Task 2.5's paragraph.
- Delete: D23's ServiceAccount and RBAC for the tool host, if that apps PR merged (Task 4.0 Files).
- Modify: any runbook passage under `docs/runbooks/` that tells the operator to run `migrate_volume.py` (rollback
  by reverse copy): drop it or mark it historical.
- Modify or delete: any other Proxmox CSI code path in apps left dead by 5.1, found by Step 1. That includes the
  Proxmox CSI side of Task 2.6's `check_bindings` (the static-PVC list) if it has nothing left to check; keep the
  inventory and `copied` checks.

**Interfaces:**
- Consumes: 5.1 merged, with its Step 7 passed; 5.1 Step 2's D27 gate.
- Produces: no copy tool in apps `main`.

- [ ] **Step 1: Find (read-only).**
  `git -C $RA grep -n -E "migrate_volume|copy_volume|migrate-|csi.proxmox.sinextra.dev|vm-9999|proxmox-csi"
  -- scripts/ infrastructure/ services/ bootstrap/ .github/ docs/runbooks/`. Expected: a list; every hit is either
  in the Files above or kept on purpose (an ADR or history mention, Not in this plan).
  Write it to `evidence/5.9/grep.txt`.
- [ ] **Step 2: Write the change** (Files above). Run:
  - `python3 -m unittest discover -s scripts/storage/tests -v`;
  - `python3 scripts/check-retained-inventory.py`;
  - `yamllint .`.
  - Expected: all PASS, and Step 1's grep shows only the kept hits.
- [ ] **Step 3: Commit:**
  `g -C $RA commit -am "chore(storage): remove the migration copy tool (ADR 0017)"`.
- [ ] **Step 4: PR and merge**, when Ben asks for the PR (**Ben OK**). Merge event: ArgoCD refresh only; no
  Application renders `scripts/`.

### Task 5.10: Planned host reboot with every retained volume staged

Gate F2 (Task 3.8) rebooted pve with one canary on `regen`. This task runs one more planned pve host reboot from
`docs/runbooks/pve-planned-reboot.md`, now with every retained volume staged, on the final code. It proves what Task
3.8's "What F2 does not cover", Scale bullet leaves for later: the boot with all `<N>` volumes, LUN 0 restored on every
`retained` target, and `storage_boot_check_ok` with real LVs. It re-runs Task 3.8 Steps 1-6 with the additions below.
It runs after 5.8 has passed, in a planned window Ben picks, outside the backup windows, with no cutover open, and
holding the maintenance lock. `hold_fence` is still set, so it does not test F18, and it does not stage a late NFS
(D9). VM300, the runner, goes down with the host, as in Task 3.8: no workflow runs until it is back.

**Files:** evidence only, `evidence/5.10/` with `gate.txt`, `pre.txt`, `post.txt`, the rows files and `facts.md`.

**Interfaces:**
- Consumes:
  - everything Task 3.8 consumes (the runbook sections, `b10clock.sh`, `b10post.sh`, the `startup` settings and the
    memory notes);
  - `<N>` from 5.8 Step 1, re-counted here;
  - Task 4.0 Step 9's `lock.sh` on VM300 and its `lock_sh_sha256`;
  - `evidence/5.8/scale.md` with `scale_gate_pass: yes`.
- Produces: `evidence/5.10/facts.md` with `<N>`, the LUN-0 count per VG, the boot check result, and
  `host_reboot_pass`.

- [ ] **Step 1: Pick the slot** (Ben). As Task 3.8 Step 1: outside every backup window, the start in hh:02-hh:30
  Asia/Jerusalem with the same excluded hours (`b10clock.sh`), and after that hour's `storage.yml` run at `:05` UTC
  has finished. Every app is down for the outage (about 12 minutes plus the storage VM's 30 s slot). Tell the
  household.
- [ ] **Step 2: Gate and baseline** (read-only, `gate.txt` and `pre.txt`). Run Task 3.8 Step 2 as written, with the
  canary lines replaced by these:
  - `[R] sha256sum /run/homelab-cutover/lock.sh /run/homelab-cutover/maintenance_lock.py`. Expected: the hashes in
    `evidence/4.0/facts.md`. If `/run` was cleared, re-stage both as Task 4.0 Step 9 does (**Ben OK**).
  - `KUBE get volumeattachments` counted per node and attacher, as 5.8 Step 1 does. Expected: every attacher is
    `org.democratic-csi.node-manual`; the sum is `<N>`.
  - `SVM 'lvs --readonly --noheadings -o vg_name,lv_name,lv_tags'` and `SVM 'targetcli ls /iscsi'`. Record the
    `created` ids per VG and the targets with their `lun0` lines.
  - `SVM 'cat /var/lib/prometheus/node-exporter/storage-boot-check.prom'`. Expected: `storage_boot_check_ok 1`.
  - Expected for the gate: as Task 3.8 Step 2. Abort if any check fails.
- [ ] **Step 3: Take the maintenance lock** (**Ben OK**):
  `[R] sh /run/homelab-cutover/lock.sh acquire host-reboot claude-code/host-reboot/<ts>`.
  - Expected: `storage-cutover:host-reboot claude-code/host-reboot/<ts> <time>`.
  - `/run` is tmpfs, so the reboot loses the nonce file. Keep it on VM300's own disk (**Ben OK**):
    `[R] install -m 0600 /run/homelab-cutover/host-reboot.nonce /root/host-reboot.nonce`. The nonce never leaves
    VM300 and is never printed.
  - The lock lives in `/var/lib/homelab-maintenance`, so it survives the reboot. Hourly `storage.yml` runs skip with
    the held warning until Step 7.
- [ ] **Step 4: Reboot.** Task 3.8 Step 3: on pve, `systemctl reboot` through the helper (**Ben OK**). Note T0. Ben
  watches POST on JetKVM. VM300 goes down too; the helper runs from the workstation.
- [ ] **Step 5: Boot and order** (read-only, `post.txt`). Task 3.8 Step 4 as written, with its Expected lines, its
  `homelab-backup@health.service` run (**Ben OK**) and its late-NFS branch. A late-NFS refusal fails this task; record
  it and bring it to Ben (D9). The recovery is Task 3.8 Step 4's, each command with **Ben OK**. Also expected: no
  `qmstop` task, and no forced-stop or timeout line in `journalctl -b -1 -u pve-guests`, for any k3s VM or the storage
  VM (k3s VMs have no `down=`, so pve's 180 s default applies). A forced stop is a crash of every retained app on that
  worker: it fails 5.10 and goes to Ben.
- [ ] **Step 6: Targets with no manual step** (read-only). Task 3.8 Step 5's reads, plus:
  - `SVM 'targetcli ls /iscsi'` and `SVM 'lvs --readonly --noheadings -o vg_name,lv_name,lv_tags'`;
  - `SVM 'journalctl -b -u rtslib-fb-targetctl --no-pager -o short-iso | grep -E "boot-check|error:"'`.
  - Expected:
    - Task 3.8 Step 5's Expected lines, except that the first `storage.yml` run after T0 skips with the held
      warning (the lock is held);
    - every `created` id in `retained`, and in `regen`, has a target with `lun0` bound to `/dev/<vg>/<id>`, and the
      count per VG equals `pre.txt`;
    - `storage_boot_check_ok 1` with a timestamp after boot, and no `LUN 0 is not bound` or `VG ... is missing` line
      in this boot's journal;
    - for each `created` retained id, `SVM 'dumpe2fs -h /dev/retained/<id> 2>/dev/null | grep -E "^(Filesystem
      state|FS Error count)"'` (read-only) shows no `FS Error count` line, recorded per id in `post.txt`.
- [ ] **Step 7: Workloads, then release the lock.**
  - Task 3.8 Step 6's production checks (read-only), with the canary line replaced by: every retained app's pod
    Running with its guard init container `Completed`, and the VolumeAttachment count per node summing to `<N>`, all
    `org.democratic-csi.node-manual`. Delete `UnexpectedAdmissionError` pods by name (**Ben OK**). The runner is
    online, and `findmnt -t tmpfs` on VM300 is read again (F19).
  - Re-stage `lock.sh` and `maintenance_lock.py` as Task 4.0 Step 9 does (**Ben OK**), then
    `[R] install -m 0600 /root/host-reboot.nonce /run/homelab-cutover/host-reboot.nonce` and
    `[R] rm -f /root/host-reboot.nonce` (**Ben OK**).
  - If any step failed, bring it to Ben before the release; he decides whether to release the lock.
  - Release (**Ben OK**): `[R] sh /run/homelab-cutover/lock.sh release host-reboot claude-code/host-reboot/<ts>`.
    Expected: `released`. UNVERIFIED: whether the release accepts a lock taken before a VM300 reboot
    (`lock.sh` reads `runner-instance` again). If it refuses, follow "Stale lock" in
    `docs/runbooks/storage-vm-cutover.md`, with **Ben OK**.
  - Dispatch `storage.yml` once (**Ben OK**). Expected: green, and nothing changes on the storage side.
  - Write `facts.md` with `host_reboot_pass: yes` only if Steps 5-7 met every Expected line. Then lift the merge hold.

### Task 5.11: terraform: drain mode for any k3s VM replace (D41)

**Decided (Ben, 2026-11-22):** after Retirement, any terraform PR that replaces k3s VMs while retained volumes are
staged runs in drain mode, enforced in code (D41). Task 3.10 V1 recorded the crash cost of the normal-mode hard stop;
it no longer decides this.

**Where it is enforced, and why there.** In `scripts/maintenance_apply.py` `execute()`, right after the wwn guard
(Task 1.4) reads the plan with `terraform show -json plan.tfplan`, and before the drain block: a normal-mode apply
whose plan replaces a k3s VM switches itself to drain mode. The plan comment says so before the merge. The options
read in the terraform repo (read-only, `origin/main` `cc493bd` plus W `8801807`):
- Failing the PR's plan job: `upload-plan` needs `validate-and-plan`, so a failure leaves no saved plan in S3, and
  `validate-and-plan.yml` sets no `types:`, so ticking the drain box later never re-runs the check. Packer's bot PRs
  would stop at a red check until someone edits them by hand.
- Refusing at apply time, as the wwn guard does: the refusal comes after the merge, `workflow_dispatch` hardcodes
  `APPLY_MODE="normal"` (`apply.yml`, job `check-conditions`), and a re-run reads the old PR body, so the only way
  back is a new PR.
- Switching to drain at apply time needs no new input, covers PR merges and dispatches alike, and reuses the one plan
  read, the existing drain code and the `drained_nodes` handoff that ansible already uncordons from.

The rule fires on every k3s VM replace, without reading VolumeAttachments. After Task 5.1 every retained app is staged
on a worker at all times (the inventory is never empty; 5.8 proves one worker carries all of them), so "while retained
volumes are staged" always holds when this code runs, and a VolumeAttachment read would only add a `kubectl` call in
normal mode that never changes the answer. The code carries that as a `shortcut:` comment. A delete-only change (a
scale-down) is not a replace and is outside D41's wording, so it does not switch; Ben can widen that later.

The cost: a normal-mode k3s replace now needs the Kubernetes API. If it is unreachable, `kubectl get nodes` fails, the
apply stops before any terraform mutation and keeps the lock, as every failed drain does today; destroy mode stays the
way out for a dead cluster.

**When it lands: after Task 5.3 has applied (see Execution order), not earlier.** Landing earlier is not harmless:
Task 3.3's rebuild runs in normal mode on purpose (D4 = normal, Task 3.3 Step 7), and Task 3.7's rebuild drains only
the canary writer (runbook `storage-vm-rebuild.md`, "Writer drain"). This change would turn both into full drains.
It does not affect 5.3 either way: 5.3's plan has in-place `update`s only, no replace. It must merge before the first
terraform PR after 5.3, which is usually Packer's next `packer-build-<run>` PR.

**Destroy mode is unchanged.** It never drains (drain and destroy are mutually exclusive in `apply.yml`) and stays the
rebuild-from-nothing path, so a destroy with retained volumes staged still hard-stops every worker. Bring that to Ben
as an open point; this task does not decide it.

**Files** (worktree `$RT`, branch `fix/drain-on-k3s-replace` off `origin/main`; re-grep every anchor, since Parts 0-4
moved the files):
- Create: `scripts/k3s_replace_guard.py`.
- Modify:
  - `scripts/maintenance_apply.py`: `execute()`, after the wwn check and before `if mode == 'drain':`;
  - `.github/workflows/validate-and-plan.yml`: the step `Check for VM updates that strip Proxmox CSI wwn` (Task 1.4;
    since Task 1.4 Step 2a this is the wwn guard line inside `Create Terraform plan`, so add the line after it there)
    gets one more line, before its `base64 plan.log > plan.log.b64`:
    `terraform show -json plan.tfplan | python3 scripts/k3s_replace_guard.py | tee -a plan.log`;
  - `.github/PULL_REQUEST_TEMPLATE.md`: one line under the drain box: a plan that replaces a k3s VM drains even when
    the box is not ticked (D41);
  - docs, in the same PR: `CLAUDE.md` (the drain and PR-checkbox bullets), `README.md` (the apply modes table, the
    **Drain** row) and `docs/storage-safe-maintenance.md` (Task 1.4's section; re-grep `drain`).
- Test: `scripts/tests/test-maintenance-workflow.py`, run by `validate-and-plan.yml` job `maintenance-tests`.

**Interfaces:**
- Consumes:
  - the wwn guard's plan read in `execute()` (Task 1.4): one `terraform show -json plan.tfplan` call, made for a
    saved plan and, on dispatch, after `terraform plan -out=plan.tfplan`;
  - Task 2.1's `workdir` (`--chdir storage`): the storage root never drains, and `--chdir` refuses every mode but
    `normal` (`test_chdir_refuses_other_modes_before_lock`), so the switch runs only when `workdir` is `None`;
  - the k3s VM addresses `module.master_nodes[<i>].proxmox_vm_qemu.vm` and
    `module.worker_nodes[<i>].proxmox_vm_qemu.vm` (`main.tf` modules `master_nodes` and `worker_nodes`, `count`;
    `modules/vm/main.tf` resource `proxmox_vm_qemu.vm`). Task 5.13 retargets these to
    `proxmox_virtual_environment_vm`.
- Produces:
  - `k3s_replace_guard.K3S_PREFIXES = ('module.master_nodes[', 'module.worker_nodes[')`;
  - `k3s_replace_guard.k3s_replacements(plan) -> list[str]`: addresses of `proxmox_vm_qemu` changes under those
    prefixes whose `actions` hold both `delete` and `create` (either order);
  - the CLI (stdin plan JSON, exit 0): `No k3s VM replaces.`, or
    `NOTICE: this plan replaces k3s VMs (<addresses>), so apply drains every node first (D41).`;
  - in `execute()`, for `mode == 'normal'`, `workdir is None` and a non-empty `k3s_replacements(plan)`: the line
    `::notice::k3s VM replace: draining first (D41): <addresses>`, then `mode = 'drain'`. The lock was already taken
    as `terraform-normal`; that name stays. `drained_nodes` and `has_changes` are written as in drain mode.

- [ ] **Step 1: Write the failing tests** in `scripts/tests/test-maintenance-workflow.py`. Add
  `from k3s_replace_guard import k3s_replacements`, the constants
  `K3S_WORKER='module.worker_nodes[0].proxmox_vm_qemu.vm'` and `K3S_MASTER='module.master_nodes[0].proxmox_vm_qemu.vm'`,
  and build changes with the existing `vm(address, actions)` helper. With plan files, write `plan.tfplan` and
  `plan.exitcode` (`2`) as `test_saved_plan_used_and_no_changes_skips_mutation` does.
  - Class `K3sReplaceGuardTests`:
    - `test_only_replaces_of_k3s_vms_are_flagged`: a plan with `K3S_WORKER` `['delete','create']`, `K3S_MASTER`
      `['create','delete']`, `module.worker_nodes[1].proxmox_vm_qemu.vm` `['update']`, `proxmox_vm_qemu.other`
      `['delete','create']`, and an inline `{'address': 'module.worker_nodes[0].null_resource.x', 'type':
      'null_resource', 'change': {'actions': ['delete','create']}}` (`vm()` hardcodes `proxmox_vm_qemu`).
      Expected: `k3s_replacements(plan) == [K3S_WORKER, K3S_MASTER]`.
    - `test_replace_guard_cli_reports_without_failing`: run the script with `sys.executable -I`, once on that plan and
      once on `{'resource_changes': []}`. Expected: exit 0 both times; the first output starts with `NOTICE:` and names
      both addresses; the second is `No k3s VM replaces.`
  - Class `WorkflowTests`:
    - `test_normal_mode_k3s_replace_drains_first`: `self.plan` holds `K3S_WORKER` `['delete','create']`;
      `execute('normal', True, self.lock)`. Expected: every `kubectl cordon` and `kubectl drain` comes before
      `['terraform','apply','plan.tfplan']`; `GITHUB_OUTPUT` has `has_changes=true` and
      `drained_nodes=["worker","master"]` (the fake node list, without `held-worker`); the lock is released.
    - `test_dispatch_k3s_replace_drains_first`: the same plan, `execute('normal', False, self.lock)`. Expected:
      `terraform plan -out=plan.tfplan`, then the drains, then `terraform apply plan.tfplan`.
    - `test_normal_mode_without_k3s_replace_does_not_drain`: `self.plan` holds `K3S_WORKER` `['update']` with no SCSI
      slot, and `execute('normal', True, self.lock)`. Expected: no command starts with `kubectl`, and
      `drained_nodes=[]`.
    - `test_wwn_refusal_comes_before_the_drain_switch`: `self.plan` holds `K3S_WORKER` `['update']` with `CSI_DISK` and
      `K3S_MASTER` `['delete','create']`; no `CSI_WWN_ACK`. Expected: `SystemExit` naming the wwn refusal, no `kubectl`
      command and no `terraform apply`, and the lock released (as
      `test_csi_wwn_guard_refuses_before_any_mutation_and_releases_lock`).
    - `test_chdir_never_drains`: `storage/plan.tfplan` and `storage/plan.exitcode` (`2`), `self.plan` holds
      `K3S_WORKER` `['delete','create']`, `execute('normal', True, self.lock, workdir='storage')`. Expected: no
      `kubectl` command, and `terraform apply plan.tfplan` ran (in the storage root, as Task 2.1's tests check).
    - `test_k3s_replace_with_api_down_keeps_the_lock`: the k3s replace plan, `self.fail='kubectl get nodes'`,
      `execute('normal', True, self.lock)`. Expected: `CalledProcessError`, no `terraform apply`, and
      `operation.json` still present (as `test_failed_mutations_keep_lock_and_skip_later_stages`).
    - `test_destroy_mode_skips_the_replace_switch`: as `test_destroy_mode_skips_the_guard`, with a k3s replace in
      `self.plan`. Expected: no `terraform show` and no `kubectl` command.
  - Class `WiringTests`:
    - `test_plan_comment_runs_the_replace_guard`: the `validate-and-plan` step `Create Terraform plan` also runs
      `scripts/k3s_replace_guard.py`, appends to `plan.log`, and both come before `base64 plan.log > plan.log.b64`.
  - Run: `. ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh && cd $RT &&
    PYTHONPATH=<lock helper>/scripts $VPY -B scripts/tests/test-maintenance-workflow.py`, with the lock helper at the
    ref `apply.yml` pins (re-grep `ref:` in job `apply`; Task 1.4 Step 2 shows the worktree recipe).
  - Expected: FAIL at import, `ModuleNotFoundError: No module named 'k3s_replace_guard'`.
- [ ] **Step 2: Write `scripts/k3s_replace_guard.py`** (Interfaces), shaped like `scripts/csi_wwn_guard.py`: a module
  docstring with the D41 reason (normal mode hard-stops a worker with retained volumes staged; Node retirement does
  not drain) and the usage line, `k3s_replacements(plan)`, and a `__main__` that prints the report line. Run Step 1.
  - Expected: the `K3sReplaceGuardTests` pass; `test_normal_mode_k3s_replace_drains_first` and
    `test_dispatch_k3s_replace_drains_first` still FAIL (no `kubectl drain` in `self.commands`); the wiring test FAILs.
- [ ] **Step 3: Implement the switch in `execute()`** and the `validate-and-plan.yml` line (Files). Keep the wwn
  check first. Keep the plan JSON in one variable so `terraform show` runs once. Add above the switch:
  `# shortcut: drains on any k3s replace without reading VolumeAttachments; after Retirement retained volumes are
  always staged. Read node-manual VolumeAttachments if that ever stops holding.` Run Step 1, then
  `TERRAFORM=$TF $VPY scripts/tests/test-rebuild-cohort.py` (with `COHORT_PLUGIN_DIR` as Task 0.1 sets it) and
  `python3 scripts/check-readme-images.py`.
  - Expected: all OK, including the Task 1.4 and Task 2.1 tests unchanged.
- [ ] **Step 4: Template and docs** (Files). The template line and the three docs say what Step 3 does: a plan that
  replaces a k3s VM drains every node first, also from a dispatch; destroy mode never drains. Run Step 1 again.
  - Expected: OK, including `test_ack_text_matches_workflow_and_template`.
  - Commit: `g -C $RT commit -am "fix: drain first when a plan replaces k3s VMs (ADR 0017, D41)"` after
    `g -C $RT add scripts/k3s_replace_guard.py`.
- [ ] **Step 5: Push and open the PR** (Ben asks for the PR; **Ben OK** for the push).
  - Run: `git -C $RT push -u origin fix/drain-on-k3s-replace`, then
    `gh pr create --repo Starktastic-Homelab/terraform --base main --head fix/drain-on-k3s-replace --title "fix: drain
    first when a plan replaces k3s VMs"` (one line).
  - Body: the repo template with every box unticked (drain, destroy, confirm and the wwn box), a two-line summary
    naming D41, and the Claude Code line.
  - This PR changes code, so it must run its apply: no skip pattern anywhere in the title, body or commit (memory
    `terraform-skip-ci-pr-body`). Skip markers are for docs-only PRs only.
  - Expected: `validate-and-plan.yml` runs from the PR head, so the new line runs. The sticky plan comment shows
    `No changes.`, `No in-place updates of VMs holding SCSI disks.` and `No k3s VM replaces.` Any other plan line is a
    stop. `maintenance-tests` and `rebuild-policy-tests` are green.
- [ ] **Step 6: Merge** (**Ben OK**). Pre-checks as Task 1.4 Step 4: no other terraform or ansible run is active, the
  lock is free, no cutover is open, outside every backup window. If the PR is behind `main`, update it with
  `gh pr update-branch <N> --rebase --repo Starktastic-Homelab/terraform` and wait for a fresh `No changes.` comment.
  Then `gh pr merge <N> --squash --match-head-commit <full sha>` (memory `pr-merge-mechanics`).
  - **Live event:** `apply.yml` takes and releases the maintenance lock. The saved plan exited 0, so `execute()` runs
    no terraform or `kubectl` command and reports `has_changes=false`; "Trigger Ansible after successful lock release"
    is skipped.
- [ ] **Step 7: Check** (read-only). `gh run list --repo Starktastic-Homelab/terraform --workflow apply.yml -L 1
  --json databaseId,conclusion,headSha`, then `gh run view <id> --json jobs --jq '.jobs[] | [.name, .conclusion]'`, and
  `gh run list --repo Starktastic-Homelab/ansible --workflow deploy.yml -L 1`.
  - Expected: the apply job `success`, the trigger job `skipped`, no new deploy run, the lock free afterwards.
  - Evidence: `evidence/5.11/` holds the plan comment and the run summaries.
- [ ] **Step 8: First real use** (the next terraform PR that replaces k3s VMs, usually Packer's; read-only checks,
  and its merge needs **Ben OK** like any terraform merge).
  - Expected before the merge: the plan comment has the `NOTICE: this plan replaces k3s VMs` line naming every
    replaced VM.
  - Expected after the merge: the apply log has `::notice::k3s VM replace: draining first (D41)`, a cordon and a drain
    for every node before `terraform apply`, and the `infrastructure-changed` payload's `drained_nodes` lists them;
    ansible's deploy uncordons them.
  - Drain runs `--timeout=120s` per node with `--disable-eviction`. A pod that takes longer fails the drain; the apply
    then keeps the lock, as any failed mutation does (`maintenance_apply.py`, "Failed mutations retain ownership").
    Bring it to Ben.
  - UNVERIFIED: that a finished drain means every retained volume on the old worker is unstaged (NodeUnstage done)
    before the VM is deleted. Read `KUBE get volumeattachments` and `SVM 'targetcli ls /iscsi'` after the apply, and
    each retained app's guard init container `Completed` on its new pod; record it in `evidence/5.11/first-use.md`.

### Task 5.12: apps: migrated volumes onto the one-flag layer (D46, D47, D48)

Ben, 2026-11-22: adding a stateful app must never mean editing shared guard code (ADR Guards, "Shared guard code holds
no app names"). Since 1.3a (apps#1707, D47) every retained guard is already the one generic guard, `guard.py` in
ConfigMap `retained-startup-guard`, with no app names, no content checks and no DB checks. So this task shrinks to
two things. It runs after Retirement, on Task 2.9's one-flag layer, so its steps are drafted at entry (Step 0).

**Scope:**
- Convert migrated volumes to the one-flag layer where needed. The work list is re-read at entry from the values
  files and the inventory:
  - app-template apps on their `main` controller can move to `retained: <id>`, with their own mount list and a uid
    override where the guard's uid cannot read the marker;
  - the rest keep their hand-wired generic guard: the other charts (prometheus, alertmanager, loki), tempo
    (app-template, but a StatefulSet, so the layer's `Recreate` fails its render), the second volumes
    (karakeep-meilisearch, home-assistant-matter), the Bitnami databases (postgres, redis) and immich-postgres
    (app-template, but on controller `postgres`, not `main`).
- Out of scope: the NFS-side guards. About ten of 1.3a's 41 `GUARDS` rows sit on claims that never move (bazarr,
  prowlarr, seerr, seerr-ru, cleanuparr, cineplete, changedetection, ntfy, pgadmin, grafana; not in
  `evidence/1.3/guard-map.json`). They keep their guard and its ConfigMap, so `retained-startup-guard` is never
  deleted. It is also the layer's ConfigMap: there is one guard, `guard.py`, for hand-wired and rendered guards.

  A conversion that only moves boilerplate is optional; Ben picks the list in Step 0.
- Markers that differ from `.homelab-<id>-data` (for example id `bytestash-data` has `.homelab-bytestash-data`) become
  the guard's `<app>`, `<kind>` and `<marker-file>` arguments in the layer's command. The overrides go in an apps-only
  file listing, per volume id, `app`, `kind` and `marker_file` (the shape of `infrastructure/base-configs/files/ordinary-file-volumes.json`,
  which dropped its unread `marker`/`identity` fields in apps#1707). ansible never reads it, so
  there is no cross-repo schema change. How the overrides reach the layer's argv is still open: the layer is a values
  file rendered inside each app's own app-template chart, so it cannot read `infrastructure/base-configs/files/`.
  Step 0 settles the path (for example the AppSet passing them as `helm.parameters`, as it passes `retained.id`).
  If no path keeps the overrides apps-only, stop and redesign with Ben: a key in the retained inventory means an
  ansible PR first, deployed and proven by a storage.yml run, as Task 2.6 did for `copied`.
- `check-retained-guards.py` allows `retained:` on a `migrated` entry with `copied` set.
- Nothing is deleted. `templates/retained-startup-guard.yaml` and `files/retained-startup/guard.py` stay, and so do
  1.3a's tests (`scripts/storage/tests/test_startup_guards.py`) and the freeze.

**Hazards the steps must cover:**
- A marker read first (read-only; an image without `sh` gets a debug container only with **Ben OK**). A name or
  content mismatch is a stop, and so is a marker the guard's uid cannot read: the fix is a uid override, never chmod,
  chown or a rewritten marker.
- Guard init containers have several names (`retained-state`, `retained-data`, `retained-convertx-data`,
  `retained-home-assistant-config`, `retained-matter-server-data`, `retained-meilisearch`, `verify-retained-data`); each
  conversion removes the app's existing one and its `retained-startup` persistence entry.
- 1.3a's `GUARDS` table pins every hand-wired guard, and Task 2.9's check-script cases pin the layer. The code PR
  flips Task 2.9's "`retained:` on a migrated entry fails" to "fails without `copied`"; each batch updates its apps'
  `GUARDS` rows. A batch that converts the last hand-wired guard in one of the fixed five namespaces also drops that
  namespace from the template's fixed list and from `test_template_namespaces_are_the_consumers`'s pinned five, or
  its equality assert fails; the inventory entries keep the ConfigMap in that namespace.
- The code PR must leave `guard.py`, so ConfigMap `retained-startup-guard`, byte-identical, or Reloader restarts every
  guarded app outside `monitoring`. Overrides change only the converted apps' commands.
- Each batch merge restarts its apps once (**Ben OK**, at a time Ben picks, outside every backup window). Per app, the
  guard init container `Completed` and the app healthy, as in 1.3 Step 12. A refusing guard is a stop: revert the
  batch, never touch the volume (1.3 Step 13).

- [ ] **Step 0: Draft the steps at entry.** Re-read the values files, the inventory, Task 2.9 as merged and the Scope
  above; write the code PR and the batches (from the 4.W waves) as Part A and Part B steps, with their Expected lines
  and evidence under `evidence/5.12/`. Ben reviews them before Step 1.
- [ ] **Step 1: Run them**, each PR and merge when Ben asks (**Ben OK**). Done when the conversions Ben picked are on
  `main`; `retained-startup-guard` stays.

### Task 5.13: terraform: move the k3s root from telmate to bpg by import (D50)

**Decided (Ben, 2026-11-16):** the k3s root moves to bpg/proxmox, the provider `storage/` already uses, so there
is one Proxmox provider. The bar (`~/Projects/homelab/handoff-csi-slots.md` item 6) is:
- adopt VMs 200-202 by `import` plus a telmate `removed { lifecycle { destroy = false } }`;
- the adoption plan is a no-op: no replace, no reboot, and no `disk` or `hostpci` change;
- the task covers clone, cloud-init, the GPU mapping, tags, startup order and `drift.yml`, and the packer manifest
  consumers.

**Why it waits for Retirement (ADR 0017 F10).** On any change to the disk list, bpg deletes every live drive that the
config does not list. bpg's `disk` is a flat list, so there is no equivalent of telmate's `disks[0].scsi` ignore. The
move is safe only once `qm config 200-202` has no `scsiN` line. That holds after 5.1 Step 1 (zero Proxmox CSI
VolumeAttachments) and 5.3. After the move, never attach a drive to a k3s VM out of band: the next disk edit would
detach it.

**Where it sits, exactly.** After 5.10 has passed and before 5.6 (Execution order item 8):
- 5.5 Check 11, 5.8 and 5.10 all hold the maintenance lock or a merge hold in windows Ben picks. Running 5.13 after
  5.10 means none of its merges can hit `apply.yml`'s lock acquire during those windows, and 5.13 never causes the
  "planned worker reboot" that 5.5 Step 2 waits for (the adoption reboots nothing; Step 15's replace is a drained
  rebuild, not a reboot).
- 5.3 stays a separate telmate PR (D50(a)). After 5.4 the pool is gone, so bpg's `pool_id` reads empty and the config
  sets none. That avoids lab B7's pool-read drift.
- 5.11 has merged, so this task retargets its guard, its `vm()` test helper and its wiring-test anchor to bpg (Files).
  Without that, the switch would match nothing and silently stop draining.
- First-use evidence: 5.11 Step 8 is the first packer PR after 5.11, which normally merges between 5.3 and 5.10
  under telmate; it writes `evidence/5.11/first-use.md`. Step 15 here is the first bpg replace and writes
  `evidence/5.13/first-replace.md`. If no k3s-replacing PR merged between 5.11 and 5.13, Step 15's PR is both: it
  writes both files, and 5.11 Step 8's Expected lines are read against the bpg addresses.

**Why the adoption plan cannot be literally `No changes.`**
- The plan imports three VMs and forgets three, with no PVE call for the forgets.
- It creates three `terraform_data.generation` resources. A create does not fire `replace_triggered_by` (terraform
  v1.17.2 `eval_context_builtin.go:430` fires only on update, replace and forget-replace), so the new resource does
  not replace its VM.
- It makes an in-place update on each imported VM, for the provider-only attributes that differ from what import
  seeds (`reboot_after_update`, `timeout_shutdown_vm`, `timeout_stop_vm`, and `purge_on_destroy` if D50(c) sets it
  false). That update is not an empty body: `vmUpdate` always sets the name (vm.go:6324-6330), so each VM gets one
  config write of its unchanged name. That is hot-applied and leaves nothing pending; every other block is gated on
  `HasChange` (critique, checked).
- The gate is therefore an **allowlist**, enforced by code on the real plan JSON (`scripts/adoption_gate.py`, Files),
  in CI before the merge (a red check and no saved plan in S3; admins can bypass) and in `execute()` before the apply
  (the hard stop). The human plan read in Step 9 is a second look, not the gate.
- The PR plan is the first real bpg Read of these VMs. There is no second lab (Ben, 2026-11-21).

**Destroy behaviour, and why #245 goes (D50(c), (g)).**
- bpg's `stop_on_destroy = false` runs `status/shutdown` with `forceStop=1` and `timeout=timeout_shutdown_vm`, but
  only while the PVE config has `agent: 1` (`vm.go:2010-2079`). Otherwise it hard-stops. That makes #245's
  `graceful_shutdown()` redundant, and destroy mode gets a guest shutdown too, where #245 covered it the same way.
- `timeout_shutdown_vm = 240` is #245's reviewed bound, against about 95 s measured; bpg's 1800 s default would hold a
  run 30 min on a hung guest. `vmDelete` puts the whole delete under `max(timeout_stop_vm, timeout_shutdown_vm)`
  (vm.go:7522-7535), 300 s by default, which would leave about 60 s for `DeleteVM`; `timeout_stop_vm = 600` makes the
  240 s shutdown the only bound that matters.
- What D50(g) accepts:
  - a timeout **fails** the apply (the error comes from `WaitForTask`) and PVE force-stops the VM. The apply keeps the
    lock. #245 fell back to a hard stop instead;
  - `restart_vms()` has no bpg counterpart: a failed apply can leave VMs off, with the lock held;
  - shutdowns run per resource under terraform parallelism, not in one batch.
- `storage/` keeps `stop_on_destroy = true` (D50(k)). Nothing recorded why (research-repos section 8); PR B adds the
  reason as a comment. The k3s VMs must not copy it, or #245's reason comes back.
- **The retry property is lost (D50(i)).** On a replace, `terraform_data.generation` updates before or alongside the
  VM's destroy. If the destroy then fails (a 240 s timeout, say), state holds the new generation and the old VM, so the
  next plan has no trigger and does not replace it; with the VM force-stopped, it plans only `started = true` on the
  old image. Telmate kept the trigger in the VM's own state. Recovery (in the docs and runbook from this PR), each
  step brought to Ben:
  1. Never dispatch after a failed replace.
  2. Start every VM the failed run left stopped (`qm start <id>`, **Ben OK**), and wait until `KUBE get nodes` shows
     every node Ready. Without this, the nonce PR's drain (5.11 switches it to drain mode, since it replaces all three)
     waits on the pods of the NotReady node: `--disable-eviction` deletes them, no kubelet confirms, and the 120 s
     timeout fails the run after the lock is taken and before any apply. #245's `restart_vms` used to cover this.
  3. Release the lock by ansible `docs/maintenance-lock-release.md` (ansible#352, `b59841a`): section 3.4
     for this shape, then section 4 (**Ben OK** at each mutation).
  4. Open a PR that bumps `rebuild_nonce` in `terraform.tfvars`, which replaces all three VMs (the cohort rule replaces
     the workers anyway when the master goes). Its pre-merge check: every node Ready.
  5. After its deploy, uncordon by hand (**Ben OK**) any node still `SchedulingDisabled`: the failed run cordoned
     them, and the next run's `drained_nodes` lists only nodes that were schedulable, so ansible skips them.

  This recovery assumes the failed run's only casualty is a VM left stopped. Terraform keeps going on resources that
  do not depend on the failed one: on an image change each VM's own generation triggers its replace, so another VM may
  already be destroyed or freshly recreated (no k3s until ansible runs). A destroyed VM cannot be started, and "every
  node Ready" is then unreachable. If the master still serves the API, delete the dead Nodes' objects (**Ben OK**) so
  the drain lists only live nodes. If the master is gone or fresh, there is no API, and destroy mode is the way out
  (5.11: "destroy mode stays the way out for a dead cluster"), after PR B. Bring either case to Ben.

  A 5.11 drain that tolerates a NotReady node was rejected: it would delete a node's pods unconfirmed, the risk D41
  drains to avoid. Stamping the generation into `description` was rejected: it plans an in-place restamp, not a
  replace.
- All of this is from reading source. Lab B7 only ran a hard stop. Step 15 proves the shutdown from the PVE task log.

**Files** (worktree `$RT`, branch `feat/k3s-bpg` off `origin/main`; re-grep every anchor). PR A is the adoption, PR B
the mandatory scaffolding removal (D50(j)), PR C the canary removal (only under D50(h)).
- Create (PR A):
  - `imports.tf` (root; `import` blocks are root-only): three
    `import { to = module.<x>[<i>].proxmox_virtual_environment_vm.vm, id = "pve/<vmid>" }` blocks;
  - in `modules/vm/main.tf`: `removed { from = proxmox_vm_qemu.vm  lifecycle { destroy = false } }`, which applies to
    every `count` instance (M6). `validate` proves the form;
  - `scripts/adoption_gate.py`: `adoption_violations(plan, root) -> list[str]`, and a CLI
    (`--root <dir>`, plan JSON on stdin) that prints `Adoption gate: OK` or one `ADOPTION GATE:` line per violation
    and exits 1. Input that is empty or not plan JSON is a violation (fail closed). Rules:
    - static (C1): if any `*.tf` in `root` holds an `import` block but no change in the plan carries
      `change.importing` or a `proxmox_vm_qemu` `forget`, that is a violation ("leftover import blocks: merge PR B
      first"). PR A imports, so it passes; a retry that only forgets (Step 10 failure path) passes; after PR B there
      are no import blocks. Between the two, every other plan (a packer PR, a dispatch) is refused. The detector strips
      `#`, `//` and `/* */` comments before matching `^\s*import\s*\{`, so a commented block does not count;
    - adoption mode is on when any change carries `change.importing` or is a `proxmox_vm_qemu` `forget`. A `forget` of
      any other type (a later `removed` block in either root) does not turn it on. Off, the plan passes untouched
      (every PR after PR B). This scope is documented in the module docstring;
    - in adoption mode each change must be: `proxmox_vm_qemu` with `['forget']`; `proxmox_virtual_environment_vm` with
      `['no-op']` or `['update']` whose changed keys (before != after, plus every key in `after_unknown`) are a subset
      of `{reboot_after_update, timeout_shutdown_vm, timeout_stop_vm, purge_on_destroy}`; or `terraform_data`
      `generation` with `['create']`;
    - anything else, and any action holding `delete`, is a violation, named with its address and keys;
    - output: addresses, action lists and key names only, never a value. Plan JSON carries sensitive values in clear
      (`after` beside `after_sensitive`), and the lines go to a public PR comment.
- Create (PR B, D50(h) only): `canary.tf`: `module "canary"` from `./modules/vm`, VMID `<D50h vmid>`, name
  `k3s-canary`, `tags = ["canary"]` (no `k3s`, so ansible's groups and `k3s_node_retirement` skip it), `started =
  false` (which also sets `on_boot = false`, so a host boot never starts it on a worker's GPU), worker sizes, the GPU
  mapping, template 901, and one unused address in `ip_configs`.
- Modify (PR A):
  - `providers.tf`: `required_providers` holds `proxmox = { source = "bpg/proxmox", version = "0.123.1" }` (the `storage/` pin) and
    `telmate = { source = "telmate/proxmox", version = "3.0.2-rc10" }`; `provider "proxmox" { insecure = true }`
    (endpoint and token from `PROXMOX_VE_*`, set by `bpg_env.sh`) and `provider "telmate" { pm_tls_insecure = true }`
    (today's block, renamed; it still reads `PM_API_URL`, `PM_API_TOKEN_ID` and `PM_API_TOKEN_SECRET` from the env,
    which every workflow keeps setting). Without the `telmate` block the CI plan fails TLS against the self-signed PVE
    certificate. `modules/vm/providers.tf` lists both sources, no versions. Telmate stays because forgetting its
    resources needs its provider (M6, default path): `removed` takes no `provider` argument (v1.17.2
    `configs/removed.go`), so the forget resolves telmate from the provider address in state. Step 3's `validate` is
    the first proof. PR B removes both telmate blocks.
  - `modules/vm/main.tf`: one `proxmox_virtual_environment_vm.vm`, mirroring Step 1's `qm config` attribute for
    attribute (the research-repos section 2 mapping):
    - `clone { vm_id = var.template_vmid, full = true }`;
    - `disk { interface = "virtio0", ... }` only;
    - `initialization` with `interface = "ide2"`, `datastore_id`, one `ip_config` per NIC in NIC order, `dns` and
      `user_account { keys }`;
    - workers get `hostpci { device = "hostpci0", mapping = var.pci_mapping, pcie = false, rombar = false }`;
    - sorted `tags` list, `on_boot = var.started` (telmate's `start_at_node_boot = true`), `started = var.started`,
      `agent { enabled = true }`, `boot_order = ["virtio0"]`;
    - `machine`, `bios`, `scsi_hardware` and `operating_system { type = <live ostype> }` from Step 1, since bpg's
      defaults are not telmate's (telmate's `os_type = "cloud-init"` is a provisioning flag, not PVE's `ostype`);
      no `cipassword` (Step 1 asserts it is unset);
    - `reboot_after_update = false`, `stop_on_destroy = false`, `timeout_shutdown_vm = 240`, `timeout_stop_vm = 600`,
      `purge_on_destroy` per D50(c);
    - `lifecycle { ignore_changes = [clone, startup], replace_triggered_by = [terraform_data.generation] }`;
    - `terraform_data.generation` with `input = jsonencode([var.template_name, var.control_plane_incarnation,
      var.rebuild_nonce])`. It replaces telmate's `force_recreate_on_change_of` and the clone-by-name.
  - `modules/vm/variables.tf`, `modules/vm/outputs.tf`: bpg-shaped inputs (`keys` list, `tags` list, `ip_configs`
    objects, `os_disk_size` in GiB, `pci_mapping`, `template_vmid`, `rebuild_nonce`, `started` default `true`, `machine`, `bios`, `scsihw`, `ostype`); drop
    telmate's `os_type`, `cipassword`, the five `usb` blocks and `pool`. Output `incarnation =
    proxmox_virtual_environment_vm.vm.network_device[0].mac_address`, which replaces `smbios_uuid`.
  - `main.tf`, `variables.tf`, `terraform.tfvars`, `outputs.tf`:
    - drop the `ip=..,gw=..` string locals;
    - `k3s_template_vmid = 901` (one `k3s_template_vmid = <n>` line in `terraform.tfvars`, which the destroy-mode
      check reads);
    - `template_name = var.base_vm_name`, still from the manifest;
    - `control_plane_incarnation` replaces `control_plane_uuids`;
    - `rebuild_nonce = 0` (D50(i));
    - `os_disk_size = 96`;
    - `ssh_pub_keys` list.
  - `renovate.json`: drop the telmate rule; add one rule matching `bpg/proxmox` in the root and in `storage/`, grouped,
    `automerge: false` (a bpg bump changes how imported VMs are read); add a second group rule matching `hashicorp/terraform`
    across the docker (plan image) and github-releases (`terraform_version`) datasources, `automerge: false`, so the
    pins move in one PR (Renovate made #232 and #240 as lone bumps; a split leaves the plan image and the apply
    binary on different versions, and Terraform refuses a saved plan another version made, after the lock is taken).
  - `scripts/maintenance_apply.py`:
    - delete #245's `pve_request`, `vm_status`, `vm_targets`, `shutdown_vms`, `graceful_shutdown`, `restart_vms` and
      their calls;
    - delete the `csi_wwn_guard` import and check, keeping the one `terraform show -json` read that 5.11's switch and
      the clone check use;
    - after that read, before the clone check: `adoption_violations(doc, workdir or '.')`; any hit releases the lock
      and refuses (nothing has changed yet). This refuses any plan while import blocks are left over, and a retry that
      would import a half-built VM (C1);
    - the clone check, scoped by root: with `workdir == 'storage'` it stays exactly as 2.1a after Step 9a (first
      create, `storage_template_vmid` and `storage_template_name`, the virtio0 root-disk comparison, D16). With
      `workdir is None` it runs once per distinct
      `change.after.clone[0].vm_id` among the `proxmox_virtual_environment_vm` creates, as
      `check_clone_source.main(vmid, name=doc['variables']['base_vm_name']['value'])`, with no root-disk comparison
      (the k3s clone grows virtio0 to 96 GiB). Every lookup stays inside the `try` and fails closed with the lock
      released, as e51275b;
    - destroy mode, before the lock: refuse while any root `*.tf` holds an `import` block (C1: after `terraform
      destroy`, a leftover import of `pve/200` fails the recreate with the cluster gone and the lock held);
    - destroy mode, after the lock and before `terraform destroy` (I6): read the VMID from `terraform.tfvars`'s
      `k3s_template_vmid` line (one regex; destroy mode has no saved plan and applies the merged checkout) and the name from `TF_VAR_base_vm_name`,
      then `check_clone_source.main(vmid, name=...)`; any failure, a missing line or a missing variable releases the
      lock and refuses. Telmate refused a missing template name in every mode; this keeps that in destroy mode.
  - `scripts/check_clone_source.py`: no change. `main(vmid, root_disk=None, name=None)` and its name check (refuse a
    template whose name differs, printing both names) exist since Task 2.1a Step 9a (D16); the k3s branch calls it.
  - `scripts/k3s_replace_guard.py` (5.11): the type filter becomes `proxmox_virtual_environment_vm`.
  - Delete `scripts/csi_wwn_guard.py`.
  - `.github/workflows/apply.yml`: remove input `accept_csi_wwn_loss` and env `ACCEPT_CSI_WWN_LOSS`; source
    `scripts/bpg_env.sh` in the k3s `maintenance_apply.py` step (the `python:trixie` container has `python3` and
    bash); `Setup Terraform` pins `terraform_version: 'v1.17.2'` with the same Renovate comment as
    `rebuild-policy-tests` (m8). The `PM_*` secrets stay as `bpg_env.sh`'s input and as telmate's env until PR B.
  - `.github/workflows/validate-and-plan.yml` (container `hashicorp/terraform`, Alpine: run steps use busybox `sh`,
    so no `pipefail` and no `PIPESTATUS`; bash arrives only in the later AWS CLI step):
    - container image `hashicorp/terraform:1.17.2` instead of `latest` (m8; the Renovate group above bumps it together with the `terraform_version` pins, as one reviewed PR whose
      offline cohort tests re-check the v1.17.2 semantics U1 and U12 rest on; those tests run on `setup-terraform`, not
      on the plan image, so the equality test below is what covers the image);
    - `Create Terraform plan` gets `id: plan`. Its first lines become `apk add --no-cache python3` and
      `. scripts/bpg_env.sh`, before `terraform plan` (`bpg_env.sh` needs `python3`; today `apk add` sits after the
      plan). The storage step's comment "python3 ... comes from the step above" stays true;
    - after the plan, the wwn guard line is replaced by (the step already runs under `set -e`, so a failed `show`
      ends the step and every later upload is skipped):

      ```sh
      terraform show -json plan.tfplan > plan.json
      python3 scripts/k3s_replace_guard.py < plan.json | tee -a plan.log
      GATE=0
      python3 scripts/adoption_gate.py --root . < plan.json > gate.log || GATE=1
      rm -f plan.json
      cat gate.log; cat gate.log >> plan.log
      echo "gate=$GATE" >> "$GITHUB_OUTPUT"
      base64 plan.log > plan.log.b64
      ```

    - `Upload Terraform plan and exitcode to S3` gets `if: steps.plan.outputs.gate == '0'`;
    - a new step after `Install AWS CLI and bash ...`, `Remove the k3s plan from S3 after a failed adoption gate`,
      `if: steps.plan.outputs.gate != '0'`, shaped like `Remove stale storage root plan from S3`: `aws s3 rm` of
      `pr-<n>/plan.tfplan` and `pr-<n>/plan.exitcode`, so a plan saved by an earlier, passing push cannot outlive this
      one (a saved plan carries its own config, so merging would apply the old plan);
    - a new last step before the cleanup, `Fail on the adoption gate`, `if: steps.plan.outputs.gate != '0'`, runs
      `exit 1` after `Upload plan log artifact`, so the job is red with the gate lines in its artifact;
    - job `comment` gets `if: ${{ !cancelled() }}`, so the comment posts the gate lines even though its `needs` job
      failed (cost: when the plan itself errors before the artifact, the comment job fails too);
    - `plan.json` and `gate.log` join the cleanup step's `rm -f` list.

    Known, unchanged (m-new-6): the removal step runs only when the gate fails, so a later push whose plan errors
    (exit 1, an `apk` failure, `bpg_env.sh` exiting) leaves an earlier push's saved plan in S3. That is today's
    behaviour, and `execute()` still gates the old plan in the window.

    Result: a failing gate shows its lines in the comment, leaves no k3s saved plan in S3 (so a bypassed merge stops
    in `execute()` at "PR plan ... missing", before the lock), and leaves the check red. Whether that check blocks a
    merge depends on branch protection's required checks (Step 7 reads them); admins can bypass either way, so
    `execute()`'s gate is the hard stop and the CI half is the early, visible one. Cost: about 20 workflow lines and
    two wiring tests.
  - `.github/workflows/drift.yml`: in the k3s `Check for drift` step, `apk add --no-cache python3` and
    `. scripts/bpg_env.sh` before `terraform plan` (the storage step's own `apk add` stays); image
    `hashicorp/terraform:1.17.2`.
  - The three workflows' manifest reads stay as they are: `vm_name` is still `TF_VAR_base_vm_name`.
  - `.github/PULL_REQUEST_TEMPLATE.md`: remove the "Proxmox CSI disks" box.
  - `scripts/tests/tf_offline.py`: add `prepare(..., exclude=())` so the offline copy can leave out `imports.tf`. The
    `PM_*` placeholders stay until PR B.
  - `docs/diagrams/cluster-topology.svg:160`: `smbios_uuid` becomes the master MAC (re-render with
    `scripts/render-diagrams.sh`).
  - Docs in the same PR: `CLAUDE.md`, `README.md` and `docs/storage-safe-maintenance.md`. Remove the `power_state`,
    the qmstop paragraph and "Clean shutdown before destroy", the wwn sections, the `force_recreate_on_change_of`
    text and the permission probe. Add:
    - the destroy is a guest shutdown (240 s) while the agent is on, and a timeout fails the apply with the VM
      force-stopped and the lock held;
    - the D50(i) recovery (no dispatch after a failed replace; bump `rebuild_nonce`);
    - F10 means no out-of-band drives;
    - `reboot_after_update = false`: a CPU or memory change applies as pending; bpg's read may already show the new
      value, so drift hides that the VM still runs the old size. Check `qm pending <id>` and reboot or rebuild;
    - imported VMs drift in full, rebuilt VMs only on their configured blocks.
- Modify (PR B): `providers.tf`, `modules/vm/providers.tf` (drop telmate and `provider "telmate"`), delete
  `imports.tf`, the `removed` block, `tf_offline.py`'s `PM_*` placeholders and the cohort test's `provider "telmate"`
  override; `CLAUDE.md` and `README.md` lose the telmate pin; `storage/main.tf` gets one comment line above
  `stop_on_destroy = true` (D50(k)): "Hard stop on purpose: prevent_destroy limits a destroy to the rebuild PR pair
  after the writer drain, and the data disks are kept." Under D50(h), add `canary.tf`.
- Modify (PR C, D50(h) only): delete `canary.tf`.
- Test:
  - `scripts/tests/test-rebuild-cohort.py`: a full rewrite to bpg addresses, `terraform_data` state and provider
    `registry.terraform.io/bpg/proxmox`. While the fixture holds the telmate half (PR A), telmate's permission probe
    still calls the closed endpoint, so the override passed to `prepare()` (`test-rebuild-cohort.py:69-71` today)
    stays, renamed to `provider "telmate" {\n  pm_minimum_permission_check = false\n}`; the old `provider "proxmox"`
    form would now target bpg and fail as an unknown argument. bpg's offline env already comes from `tf_offline.ENV`.
    PR B deletes the override with the telmate half;
  - `scripts/tests/test-maintenance-workflow.py`: delete the wwn and shutdown fixtures and tests; the `vm()` helper
    takes `type=` defaulting to `proxmox_virtual_environment_vm` (M5); add the gate, clone-check and destroy tests;
  - `scripts/tests/test-adoption-gate.py` (`test-clone-source.py` needs nothing new since Task 2.1a Step 9a);
  - all run by `validate-and-plan.yml` jobs `rebuild-policy-tests` and `maintenance-tests`.

**Interfaces:**
- Consumes:
  - bpg 0.123.1 `proxmox_virtual_environment_vm` (as `storage/main.tf`) and `$PC` (`-plugin-dir` layout);
  - `scripts/bpg_env.sh`, which maps `PM_*` to `PROXMOX_VE_*` and `TF_VAR_ssh_pub_key` to `TF_VAR_ssh_pub_keys`;
  - Task 2.11's manifest read (`... select(.name=="k3s") | last | .custom_data.vm_name`);
  - template VMID 901, whose PVE name is the manifest `vm_name`;
  - 5.11's `k3s_replace_guard.k3s_replacements(plan)`;
  - Task 2.1a's clone check (e51275b form, plus Step 9a's `name=`, D16);
  - ansible `k3s_node_retirement` (`filter_plugins/k3s_node_retirement.py:88-104`): every QEMU VM, templates and the
    D50(h) canary included, must carry exactly one `smbios1` uuid, all distinct, or the deploy fails. bpg sends no
    `smbios1` on clone (vm.go:2805, nil without a block), so a bpg-created VM's uuid comes from PVE's clone (U14).
- Produces:
  - addresses `module.master_nodes[0].proxmox_virtual_environment_vm.vm` and
    `module.worker_nodes[0..1].proxmox_virtual_environment_vm.vm`;
  - `module.<x>[<i>].terraform_data.generation` and the root variable `rebuild_nonce`;
  - module output `incarnation`;
  - `scripts/adoption_gate.py`;
  - after PR B, a root with no `telmate/proxmox` provider, no `import` and no `removed` block;
  - the same PVE-side contract for ansible `inventory/proxmox.yml` (tags `k3s` plus `master` or `worker`, and
    `ipconfig0` of the form `ip=<addr>/<mask>`).

- [ ] **Step 1: Read-only capture** (helper `pve` rows, run as Part 5's "How live steps run" says):
  - Run:
    - `qm config 200`, `qm config 201`, `qm config 202`, `qm config 901`;
    - `qm pending 200`, `qm pending 201`, `qm pending 202`;
    - `pvesh get /cluster/backup --output-format json`, `pvesh get /cluster/replication --output-format json`,
      `pvesh get /cluster/ha/resources --output-format json`;
    - `pvesh get /cluster/mapping/pci/k3s-worker-gpus --output-format json`;
    - `pvesh get /cluster/resources --type vm --output-format json`, then `qm config <id> | grep -E '^smbios1:'` for
      every `qemu` VMID it lists (templates included); under D50(h), check the canary VMID (299) is unused;
    - read ansible `filter_plugins/k3s_node_retirement.py` `verified()` at `origin/main` and record the rule it
      enforces (one `uuid=` per QEMU VM, all distinct, none equal to the retired generation).
  - Save to `evidence/5.13/qm-config-before.txt`. `qm config` holds no secret: keys are public, and `cipassword` is
    unset.
  - Expected:
    - no `^scsi[0-9]+:`, `^unused[0-9]+:`, `^sata`, `^ide[013]:`, `^hostpci[1-9]`, `^efidisk0:`, `^tpmstate0:` or
      `^amd-sev:` line (bpg >=0.120.0 import records the last three even at defaults, #3241);
    - `agent: 1` on all three; nothing pending;
    - 901 has `template: 1`, and its `name` equals the manifest `vm_name`;
    - every QEMU VM has exactly one `smbios1` `uuid=`, and no two are equal. Record 901's (or its absence): if 901 has
      none, U14 decides at Step 13 or 15 whether PVE's clone adds one;
    - no `cipassword` line.
  - Any extra drive line is a STOP, because F10 would detach it. Bring it to Ben.
  - Record `balloon`, `ostype`, `machine`, `bios`, `scsihw`, `onboot`, `serial0`, `vga`, `cpu`, `cpuunits`, the
    virtio0 options, the `sshkeys` encoding, the net `firewall=`/`queues=` and `startup`. Step 3 mirrors each one; a
    missed one stops at the Step 9 gate (fail closed, one wasted round).
  - If a backup job, replication job or HA resource names 200-202 by VMID, record it: `purge_on_destroy = true` would
    drop them on every replace. Then D50(c) sets it false; bring it to Ben.
- [ ] **Step 2: Write the failing tests.**
  - `test-rebuild-cohort.py`, through `tf_offline.prepare(..., plugin_dir=$PC, exclude=('imports.tf',))` with
    `-refresh=false`:
    - `adoption_is_allowlisted_noop`: the fixture state holds the three telmate resources (today's fixture) plus the
      three bpg resources, pre-seeded with the values bpg Read would write from Step 1's capture (`clone = []`,
      provider-only attributes at their import defaults per `vm.go:5630-5643`), and no `terraform_data`.
      Expected: `adoption_violations(plan, root) == []` (`root` the offline copy, which holds no `imports.tf`, so the
      static rule is exercised in `test-adoption-gate.py` instead), each `proxmox_vm_qemu` change is `['forget']`, and the three
      `terraform_data.generation` changes are `['create']` with no VM replaced (U1, settled by source).
    - `adoption_fixture_bites`: the same fixture with virtio0 `size` set to 95. Expected: a violation naming `disk`.
    - `new_image_replaces_all`: from the post-adoption state (with `terraform_data`, and the VMs still `clone = []`),
      change `base_vm_name`. Expected: all three VMs are `['delete','create']`, and each planned create has
      `change.after.clone[0].vm_id == 901`. Terraform v1.17.2 builds the replacement create from the unignored config
      (`node_resource_abstract_instance.go:1219-1231`), so this is a regression test, not an open question.
    - `master_replace_replaces_workers` and `interrupted_apply_retry_still_replaces_workers`: the old cohort cases on
      bpg addresses (the second with the worker generations still at the old value). The master's planned
      `network_device[0].mac_address` must be unknown on replace (U7).
    - `failed_destroy_retry_needs_nonce_bump` (D50(i)): `terraform_data.generation` already at the new value and the
      VM still the old one. Expected: the plan does not replace the VM (the loss, asserted). Then with
      `rebuild_nonce = 1`: all three VMs are `['delete','create']`.
    - `no_rebuild_flag_keeps_workers`: `rebuild_workers_with_control_plane = false`, then a master replace. Expected:
      the workers are `no-op`.
  - `test-adoption-gate.py`, on hand-built plan JSON: the allowlisted adoption passes; an imported VM with an
    `initialization` change, a `disk` change, a key in `after_unknown`, a `delete`, or an extra resource each fails and
    the CLI exits 1 naming it; a plan with no import and no forget passes untouched when the root has no import
    block; the same plan with `imports.tf` in the root fails as leftover import blocks (C1); PR A's importing plan with
    `imports.tf` passes; a forget-only plan with `imports.tf` passes (Step 10 retry); a root whose only `import {` is
    commented out (`#`, `//` and `/* */`) counts as no import block; a `forget` of a non-`proxmox_vm_qemu` type leaves
    adoption mode off; empty stdin exits 1; and a violation whose `after` holds `SENTINEL-VALUE` (in a key also in
    `after_sensitive`) never prints `SENTINEL-VALUE`.
  - `test-maintenance-workflow.py`:
    - `test_k3s_create_checks_clone_source_by_plan`: a k3s replace plan with `after.clone[0].vm_id = 901` on three
      creates calls `check_clone_source.main(901, name='<base_vm_name>')` once, with no `root_disk`, before any
      `kubectl`.
    - `test_k3s_clone_refusal_releases_lock_before_drain`, and `test_k3s_plan_without_base_vm_name_is_refused`
      (fail closed).
    - `test_storage_create_still_checks_root_disk`: the 2.1a Step 9a case, unchanged
      (`main(902, ('local-zfs', 4), name='packer-storage-13.7.0-1')`).
    - `test_adoption_violation_refuses_and_releases_lock`: an importing VM with a `disk` change (the half-built-VM
      retry). Expected: `SystemExit`, no `terraform apply`, lock released.
    - `test_destroy_refused_while_import_blocks_remain` (C1): a fake root holding `imports.tf`, empty state, mode
      `destroy`. Expected: `SystemExit` naming PR B's cleanup, and no lock taken.
    - `test_destroy_checks_clone_source_before_destroy` (I6): mode `destroy`, `terraform.tfvars` with
      `k3s_template_vmid = 901`, `TF_VAR_base_vm_name` set; a failing check refuses with no `terraform destroy` and the
      lock released; a missing line or variable refuses too.
    - 5.11's `K3S_WORKER` and `K3S_MASTER` become `module.<x>[0].proxmox_virtual_environment_vm.vm`, and
      `test_only_replaces_of_k3s_vms_are_flagged` gains a `terraform_data` delete/create that must not be flagged.
    - Delete `test_wwn_refusal_comes_before_the_drain_switch`, the wwn guard tests and the #245 shutdown tests
      (`test-maintenance-workflow.py:237-320` at a8aff78).
    - `WiringTests`: no workflow names `csi_wwn_guard.py`, `ACCEPT_CSI_WWN_LOSS` or `accept_csi_wwn_loss`; these steps source `scripts/bpg_env.sh`: `Create Terraform plan`,
      drift's `Check for drift` and apply's `Acquire ownership ...` step (not `Validate Terraform template`, which only
      runs `init` and `validate`), after an `apk add --no-cache python3` line in the Alpine
      containers; `Create Terraform plan` (`id: plan`) has no `PIPESTATUS` and no `pipefail`, runs `adoption_gate.py`
      and writes `gate=` to `$GITHUB_OUTPUT` before its last `base64 plan.log` line; the k3s S3 upload carries
      `if: steps.plan.outputs.gate == '0'`; the S3 removal step and `Fail on the adoption gate` carry `!= '0'`, and the
      latter comes after `Upload plan log artifact`; job `comment` runs on `!cancelled()`; in `validate-and-plan.yml`,
      `apply.yml` and `drift.yml` (not `format.yml`) every `hashicorp/terraform` image tag and `terraform_version` (the `v` stripped) are equal to
      each other, with no literal in the test, so a correct grouped bump stays green and a lone bump goes red;
      `test_plan_comment_runs_the_replace_guard` anchors on `Create Terraform plan`.
  - `test-maintenance-workflow.py`, the plan-step sandbox test (`test_plan_step_runs_the_guard`, lines 285-305 at the
    worktree; 5.11 renames it): it runs the real `Create Terraform plan` script under `sh -e` with a fake `terraform`, a
    fake `apk` and the ambient env. After N1 the script sources `bpg_env.sh` (exits 1 without `TF_VAR_ssh_pub_key`) and
    writes `"$GITHUB_OUTPUT"`. Give the sandbox `TF_VAR_ssh_pub_key`, a `GITHUB_OUTPUT` file and the `adoption_gate.py`
    path, and assert `gate=0` in that file. Step 6 would catch it fail closed, at the cost of a round.
  - `test-clone-source.py`: nothing new; 2.1a Step 9a's `test_name_mismatch_prints_both_names` covers the name check.
  - Run: `. ~/.cache/claude-homelab-live/storage-migration/evidence/env.sh && cd $RT && COHORT_PLUGIN_DIR=$PC
    TERRAFORM=$TF $VPY scripts/tests/test-rebuild-cohort.py`, then `$VPY -B scripts/tests/test-adoption-gate.py`, then
    `PYTHONPATH=<lock helper>/scripts $VPY -B scripts/tests/test-maintenance-workflow.py`. The lock helper is at the
    ref `apply.yml` pins, as in 5.11 Step 1.
  - Expected: FAIL (no `proxmox_virtual_environment_vm` in the k3s module; `exclude` and `adoption_gate` unknown).
- [ ] **Step 3: Implement the HCL** (Files, PR A: providers, module, root, `imports.tf`, the `removed` block).
  - Run `$TF fmt -check -recursive` and `$TF init -backend=false -plugin-dir=$PC && $TF validate`. `validate` checks
    the import and removed addresses (U3).
  - Run Step 2's cohort test. Expected: PASS. Iterate on the module until `adoption_is_allowlisted_noop` passes
    without widening the allowlist.
  - Commit: `g -C $RT commit -am "feat: move the k3s VMs to bpg/proxmox by import (ADR 0017, D50)"`, after
    `g -C $RT add imports.tf`.
- [ ] **Step 4: Implement the scripts** (Files: `adoption_gate.py`, `maintenance_apply.py`, `k3s_replace_guard.py`,
  delete `csi_wwn_guard.py`; `check_clone_source.py` already has `name=`, Task 2.1a Step 9a).
  - Run Step 2's gate, maintenance and clone-source tests. Expected: PASS, including 2.1a's `--chdir` tests and 5.11's
    tests on the new constants.
  - Commit: `g -C $RT commit -am "refactor: gate the adoption, check the k3s clone source, drop the wwn guard and
    pre-destroy shutdown (D50)"`, after `g -C $RT add scripts/adoption_gate.py scripts/tests/test-adoption-gate.py`
    and `g -C $RT rm scripts/csi_wwn_guard.py`.
- [ ] **Step 5: Workflows, template, diagram and docs** (Files).
  - Run Step 2 again and `python3 scripts/check-readme-images.py`. Also run
    `git -C $RT grep -nE 'telmate|proxmox_vm_qemu|PM_API|csi_wwn'`. Expected hits: only the `removed` block, `scripts/tests/test-storage-ci.py` (the `FAKE_PM` inputs for
    `bpg_env.sh`, which stay), `docs/superpowers/plans/2026-09-01-k3s-*.md` (Codex history, never edited), both
    `providers.tf` files, `bpg_env.sh`, `adoption_gate.py` and its test (the forget type), `tf_offline.py`'s
    placeholders, the cohort fixture's telmate half and its `provider "telmate"` override, the workflows' `PM_*` env
    lines, and the telmate pin in `CLAUDE.md` and `README.md` (PR B removes it).
  - Commit: `g -C $RT commit -am "ci: run the k3s root through bpg_env.sh and the adoption gate (D50)"`.
- [ ] **Step 6: Offline gate.** Run every test in `validate-and-plan.yml` locally, as Steps 2-5 do. Expected: all
  PASS. Record the `removed` form that validated in `evidence/5.13/offline.md`.
- [ ] **Step 7: Pre-PR read-only checks.**
  - Re-run Step 1's `qm config` and `qm pending` lines. Expected: identical to `qm-config-before.txt`.
  - `gh pr list --repo Starktastic-Homelab/terraform --state open`. Every saved plan merged after this one fails at
    `terraform apply` after the lock is taken, and keeps the lock. Expected: no other open PR; if any is open
    (packer-build, Renovate or other), it stays unmerged until PR B (or PR C) has merged, then is rebased.
  - Record each node's `bootID` (Step 11's `KUBE get nodes` line) in `evidence/5.13/bootid-before.txt`.
  - `gh api repos/Starktastic-Homelab/terraform/branches/main/protection/required_status_checks --jq .contexts`
    (read-only). Record whether `Terraform validate and plan` is required. The read needs admin on the token and may 404: then record
    "unknown", Ben reads it in the UI (Settings, Branches), and until then treat the CI gate as advisory. If not required, the red gate check is advisory and
    `execute()` is the only stop: say so to Ben; this task does not change branch protection.
- [ ] **Step 8: Push and open PR A** (Ben asks for the PR; **Ben OK** for the push).
  - `git -C $RT push -u origin feat/k3s-bpg`, then
    `gh pr create --repo Starktastic-Homelab/terraform --base main --head feat/k3s-bpg --title "feat: move the k3s
    VMs to bpg/proxmox by import"`.
  - Body: the repo template with every box unticked, a short summary naming D50, and the Claude Code line.
  - This PR must apply, so it carries no skip marker in the title, body or commits (memory `terraform-skip-ci-pr-body`).
- [ ] **Step 9: Read the real plan comment** (the first real bpg Read of 200-202).
  - Expected:
    - `Adoption gate: OK` and the plan job green. A failing gate is the STOP: its lines name the drifting keys;
    - 3 to import, 3 to add, 3 to change, 0 to destroy and 3 to forget (terraform 1.17's exact summary wording is not
      pinned here);
    - `No k3s VM replaces.` from 5.11's guard;
    - `user_account.password` shown as sensitive or null, and no other secret in the public comment (keys, MACs and
      IPs are public already) (M14).
  - On a STOP: fix the module to match the live value, extend the fixture in the same commit, and push (**Ben OK** for
    each push, since it publishes to a public repo). Read the new comment.
  - Save the comment to `evidence/5.13/plan-comment.md`.
- [ ] **Step 10: Merge PR A** (**Ben OK**, given for both live events below).
  - Pre-checks as 5.11 Step 6, plus Step 7 again, plus: `evidence/5.13/` holds Ben's named procedure for releasing a
    failed `apply.yml` run's lock (item 2 below). If it is missing, stop and ask Ben before merging.
  - Merge with `gh pr merge <N> --squash --match-head-commit <full sha>`.
  - **Live event 1:** `apply.yml` takes the lock, `execute()` re-runs the adoption gate on the saved plan, and the
    apply imports, creates and forgets in normal mode. No replace, so no drain.
  - **Live event 2 (certain):** the plan exit code is 2 (three creates), so `has_changes=true` dispatches
    `infrastructure-changed`, and ansible's full deploy restarts k3s on every node. Hold apps merges until it ends.
  - **If the apply fails** (the lock stays held, no dispatch, no deploy). Nothing is retried until Ben has read it.
    1. Bring the apply log to Ben. Classify each of 200-202 from the log and `qm config` (read-only, no state read):
       imported (bpg), forgotten (telmate), its update applied, its `terraform_data` created.
    2. Release the lock by ansible `docs/maintenance-lock-release.md` (ansible#352, `b59841a`, 2026-11-23): identify
       the holder (section 2), reconcile by shape (section 3), then `scripts/maintenance_lock_op.sh` staged from one
       ansible commit (section 4, **Ben OK** at each mutation). Record the run, stage and outcome in `evidence/5.13/`.
       The adoption stops no VM, so nothing needs starting.
    3. A VM whose import failed but whose telmate forget went through is in neither state. Retry by one `apply.yml`
       dispatch (**Ben OK**), before PR B: its plan imports that VM, so the static rule and the allowlist pass and
       `execute()` re-checks. A dispatch has no saved plan, so `changed = True` whatever the plan shows
       (`maintenance_apply.py:107-115`): `has_changes=true` dispatches `infrastructure-changed` and a full ansible
       deploy restarts k3s on every node. It is a live event like event 2: hold apps merges until it ends. After PR B the same address would plan a create at a VMID that exists; bpg's create
       fails closed, but with the lock held. A VM imported but not yet forgotten retries the same way (a forget-only
       plan passes the static rule).
    4. Every VM imported and forgotten, and only an update or a `terraform_data` create failed: a dispatch is refused
       by design (import blocks remain, the plan imports nothing). PR B is the recovery: push and open it now
       (**Ben OK**). Its plan has no import and no forget, so the gate is off and the plan is read by hand: Expected
       only `update`s on the allowlisted keys and `create`s of `terraform_data.generation`, nothing else (a create
       fires no `replace_triggered_by`). Anything else is a STOP. Merge (**Ben OK**); it is a live event with a deploy
       if anything changes.
    5. Then Step 11 runs against the final state, and Step 12's remaining items follow.
- [ ] **Step 11: Check** (read-only), only after the ansible deploy has ended green.
  - The apply log shows the three imports, three adds and three forgets, and nothing destroyed.
  - `qm config 200-202` diffs empty against Step 1, and `qm pending 200-202` shows nothing pending (a missed change
    under `reboot_after_update = false` would only show there).
  - Each node's `bootID` is unchanged from before the merge (a k3s restart keeps it):
    `KUBE get nodes -o jsonpath='{range .items[*]}{.metadata.name} {.status.nodeInfo.bootID}{"\n"}{end}'`,
    compared with `bootid-before.txt`.
  - Dispatch `drift.yml` (**Ben OK**). Expected: exit 0 on the k3s step. Record its duration (U11).
  - Update the memory note `terraform-apply-strips-csi-wwn.md` (the guard is gone) and `handoff-csi-slots.md` item 6
    (done, with the PR number).
  - Evidence goes to `evidence/5.13/`.
- [ ] **Step 12: PR B, the mandatory cleanup** (D50(j); Ben asks for the PR; **Ben OK** for the push and the merge).
  It merges before any other terraform PR, any replace and any destroy-mode run. Normally after Step 11 has passed;
  as Step 10's recovery, earlier, and then without `canary.tf` (under D50(h) the canary moves to its own PR after
  Step 11, with the same checks).
  - Files (PR B). Add `WiringTests.test_no_adoption_scaffolding_left`: no `import {` or `removed {` block in any `*.tf`
    in the root or `modules/`, and no `telmate` in any `required_providers`. Run it first against PR A's tree:
    Expected FAIL; then after the deletions: PASS, with the full Step 6 run.
  - Push, open (same no-skip-marker rule), read the plan comment. Expected: `Adoption gate: OK` and `No changes.`; under
    D50(h) instead `2 to add` (the `module.canary` VM and its `terraform_data`), and nothing else.
  - Merge (**Ben OK**). Without the canary: exit 0, no lock mutation, no deploy. With the canary: **live event**, the
    lock, the clone check of 901 by name, the create, and a full ansible deploy (k3s restarts); hold apps merges until
    it ends.
  - Delete `$PC`'s telmate directory after the merge.
- [ ] **Step 13: Canary check and PR C** (D50(h) only).
  - Read-only: `qm config <canary>`. Expected: `hostpci0: mapping=k3s-worker-gpus,pcie=0,rombar=0`, `ide2` a
    cloud-init drive on the configured datastore, `virtio0` at 96G, `ipconfig0: ip=<addr>/<mask>` (U9), `tags: canary`,
    no `onboot: 1`, status `stopped`, and one `smbios1` `uuid=` that differs from 901's and from every other QEMU
    VM's in Step 1's list (U14; none at all is a STOP: retirement reads every QEMU VM's config only when it retires a
    worker, so the first deploy after a worker replace, Step 15's, would fail; bring it to Ben). The apply
    log shows the clone check naming 901 and its name.
  - Then, only after PR B's ansible deploy has ended green (`deploy.yml` holds the maintenance lock, so an earlier
    merge fails at `apply.yml`'s acquire), PR C deletes `canary.tf` (Ben asks; **Ben OK** for push and merge). Expected plan: the canary VM and its
    `terraform_data` destroyed, nothing else. The merge is a live event with a full ansible deploy; hold apps merges.
    Afterwards `qm status <canary>` errors (gone), and Step 1's backup, replication and HA reads are unchanged.
  - A failed create keeps the lock with a half-built VM at the canary VMID: bring it to Ben; recovery is PR C plus, if
    the address left state, `qm destroy <canary>` (**Ben OK**). No k3s VM is touched either way.
  - Write `evidence/5.13/canary.md`. Then lift the terraform PR hold.
- [ ] **Step 14: `.github` contract index** (a second commit on 5.6's `$GR` branch, listed for Ben; it merges with
  5.6):
  - "Image manifest": add consumers `scripts/maintenance_apply.py` (reads `variables.base_vm_name`) and
    `scripts/check_clone_source.py`; add "`vm_name` is the k3s replace trigger and the template name check".
  - New row **k3s image**: packer k3s build `vm_id` 901 → terraform `terraform.tfvars` `k3s_template_vmid`, like 5.6's
    "Storage image" row.
  - "VM tags, SSH address": add "written by bpg `tags` and `initialization.ip_config`; ansible reads `ipconfig0`".
  - Drop telmate wherever `profile/README.md` names it. Research found none.
- [ ] **Step 15: First real replace** (the next packer-build PR; its merge needs **Ben OK** as usual).
  - Before the merge, the plan comment shows three `-/+` through `replace_triggered_by`, `Adoption gate: OK` and 5.11's
    NOTICE.
  - After the apply:
    - the apply log shows the clone check naming 901 and its name, and 5.11's drain lines;
    - the PVE task log (`pvesh get /nodes/pve/tasks --vmid <id>`) shows `qmshutdown` before `qmdestroy` for each VM,
      not `qmstop`, and a shutdown under 240 s (U8);
    - `qm config 201` has `hostpci0: mapping=k3s-worker-gpus,pcie=0,rombar=0`, `ipconfig0: ip=<addr>/<mask>`,
      `tags: k3s;worker`, `onboot: 1` and no `startup`;
    - each of 200-202 has one `smbios1` `uuid=`, different from its Step 1 value, from 901's and from every other
      QEMU VM's (U14), and ansible's `k3s_node_retirement` ran without a refusal;
    - ansible's inventory groups both workers, and `KUBE get nodes` shows the GPU allocatable on both;
    - `drift.yml` the next day exits 0.
  - Write `evidence/5.13/first-replace.md` (and `evidence/5.11/first-use.md`, if this PR is also 5.11 Step 8).
  - A failure mid-replace keeps the lock: bring it to Ben. A destroy that timed out follows the D50(i) recovery
    ("Destroy behaviour": start the stopped VM first, then release, then the nonce PR); never dispatch.

**UNVERIFIED** (each line says how the task settles it; U1, U4 and U12 of revision 1 are settled and removed, and U13 is now the
accepted loss in D50(i)):
- U2: forgetting the telmate resources needs telmate installed. Assumed true (M6); PR B is the default path either way.
- U3: the `removed` form inside `modules/vm`, and that the plan JSON shows `forget`. Check: Step 3's `validate` and
  Step 2.
- U5: bpg's import ID `pve/200` (`vm.go:1798-1814`). Check: Step 9.
- U6: live values the fixture cannot know (`balloon`, `ostype`, `serial0`/`vga` from the template, `cpuunits`, the
  `sshkeys` encoding, the net `firewall=`, the cloud-init `upgrade` default). Check: Step 1, then the Step 9 gate.
- U7: bpg plans the master's MAC as unknown on a replace. Check: Step 2. Fallback: D50(e).
- U8: the destroy is a guest shutdown while `agent: 1`, and a timeout errors rather than hangs. Check: Step 15's task
  log. The timeout path stays unproven unless a guest hangs.
- U9: bpg's create path for this module (clone of 901, the GPU mapping, `ide2`, the `ipconfig0` string, the token's
  rights for clone and mapping). Check: Step 13 under D50(h), otherwise Step 15. The storage root's production
  create already proved clone, cloud-init and resize with the same provider.
- U10: `purge_on_destroy = true` drops a VMID from backup, replication and HA config. Check: Step 1.
- U11: bpg's agent reads during refresh lengthen plans. Check: Step 11's `drift.yml` duration.
- U14: PVE's clone gives each bpg-created VM a fresh `smbios1` uuid (bpg sends none on clone, vm.go:2805). Check:
  Step 13 under D50(h), otherwise Step 15. If it does not, bring it to Ben: declaring `smbios {}` fixes creates but
  costs a pending uuid write on the imported VMs (D50(e)).

## Accepted untested (Ben, 2026-11-21)

These come from ADR `:846-856`. They are not tested by any gate in this plan, and no step may claim them as proven.
- **A stall of the `retained` disk or of the whole backend.**
  - Every lab stall hit `regen`, on its own storage.
  - In production, such a stall can only be staged by stalling pve's NFS. That freezes Proxmox CSI and every VM, as it
    does today.
  - The design fails closed there: a retained read that fails is a failed fencer loop, never empty fence tags (ADR
    LVM isolation).
- **Real hangs.** Every lab hang was simulated: `qm suspend`, `SIGSTOP`, an in-guest freeze or `link_down`. Gate R1,
  which would also be a `qm suspend`, is not in this plan.
- **The cold-boot fence rule (F18) on a real host boot with fencing on.**
  - It was lab-tested only through guest cycles.
  - F2 ran with `hold_fence` set.
  - First seen at the first host reboot after automatic fencing is turned on (a later decision).
- **Smaller paths, argued from source or code reading:**
  - F6's mount wait over 120 s (kubelet's Uncertain path);
  - F7 route 2.
  - `StorageFencerBlind`'s absent legs left this list: they are `absent_over_time(...[5m])`, and promtool cases in
    apps CI show one failed scrape stays quiet and a sustained absence fires.

- **A `regen` VG missing at dry-run time** (accepted by Ben, D42, 2026-11-22). The dry run keeps failing on any
  missing VG, before the lock, so the retained lifecycle (creates and grows) pauses until the VG returns: a lost
  regen disk from the replica (`storage-vm-restore.md` "Whole-disk restore", regen only); a blank re-creation with no
  replica copy has no runbook yet and needs Ben (the bootstrap runbook refuses a VM that has LVs). The apply-time
  per-class split still protects `retained` from a VG lost mid-run.
Added after the requirements audit (2026-11-22), not yet accepted by Ben. Tasks 5.8 and 5.10 do not prove these:
- **An unclean host reset with all retained volumes staged.** Task 5.10 proves only a planned host reboot with every
  retained volume staged; 5.5 and 5.8 reboot workers. This host had kernel oopses on 10-23, 11-10 and 11-15. Recovery
  from such a reset rests on the MMP wait beyond 120 s, which is already accepted untested above.
- **A cold boot where NFS comes up late** (D9, decided alert only, Ben 2026-11-22). `StorageVMDown` fires and Ben
  runs `qm start`; no gate here stages a late NFS at boot.

## Not in this plan

- **ansible `roles/proxmox_csi_storage/`, `proxmox-csi-storage.yml`, `scripts/tests/test_proxmox_csi_storage.py` and
  `docs/proxmox-csi-storage.md`.** They are kept: they are the only ansible record of how the `k3s-block` NFS storage
  that the storage VM still uses was registered. After 5.4 they must never run, because they would recreate the CSI
  pool, user, token and ACLs. 5.2-docs says so. Reducing them to the storage registration is later work.
- **`rebuild_workers_with_control_plane = true`** and its CSI comment (`terraform.tfvars:27-29`). Whether the
  cohort rule is still needed without Proxmox CSI is a separate decision.
- **`csi-activation-preflight.yml`:** a rename, dropping its CSI ciphertext inputs, and the `proxmox-csi-config`
  branch of `scripts/verify_sealing_recovery.py:53`. This applies if 5.2 Step 5 keeps the file.
- **Task 2.6's static-PVC check**, if 5.9 Step 1 finds it still has something to check. The copy tool itself is
  removed in Task 5.9.
- **Moving the proxmox-csi README** (the quota record) into the storage docs. The `*-block-storage/` directories hold
  no guards since apps#1707, so they go with their last binding file.
- **Per-app runbooks** (`docs/runbooks/*-storage.md`) that still describe Proxmox CSI operations, and the old
  Proxmox CSI plans and reports under `docs/superpowers/`. Both are history.
- **The VMID 9999 reservation and the empty `images/9999` directory** after the last old image is gone.
- **Automatic fencing (remove `hold_fence`, Gate R1).** A later decision by Ben (2026-11-21). Until then `hold_fence`
  stays on `retained` and the manual fence is the only fence. R1 would check the production timings: right after
  `hold_fence` is removed, `qm suspend` one worker and see the fence, the taint and the pods' move to the peer at the
  300 s threshold (about 7 minutes from the hang), then `qm resume` it and see it stay fenced on the same bootID, and
  see it unfenced after a reboot. That decision also takes up D28 (the fencer token after a k3s rebuild) and the
  first real-host-boot test of F18.
- **The refusing gauge and its alert** (`storage_fencer_refusing{node,reason}` and `StorageFencerRefusing`, the old
  Task 5.0). They wait for the later automatic-fencing decision: D13 and D33 are deferred (Ben, 2026-11-21).
- **NAS-agnostic backups of retained volumes** (D43, deferred by Ben, 2026-11-22). Retained backups stay on the ZFS
  path: TrueNAS snapshots replicated to `usbbk/tn`, restic reading the replica. Trigger, a hard precondition of
  decommissioning TrueNAS: a storage-VM backup path (an LVM snapshot of each retained LV inside the storage VM, then
  restic from the storage VM to the off-site repo) is built, runs alongside the ZFS path for a while, and a restore
  from it is drilled; only then does the ZFS path go. Restores from existing off-site restic snapshots need no ZFS;
  new backups and the local ZFS-clone restore do. The per-VG snapshot reserve (D44, Task 2.6) keeps this path open.
