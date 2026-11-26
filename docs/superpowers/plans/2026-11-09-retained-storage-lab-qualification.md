# Retained storage VM: build and lab qualification plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build every component ADR 0017 needs for its lab on unmerged branches, then run all 12 lab checks on disposable
VMs, so that Ben has evidence before any production change.

**Architecture:**
- **Part A** writes the code with offline tests, in four repos:
  - ansible: the storage role, reconcile, fencer and worker settings;
  - packer: three images;
  - terraform: a `storage/` root on bpg;
  - apps: democratic-csi, the inventory and renderer, and alerts.
- **Part B** builds a disposable lab and runs the ADR's lab checks against that code, then deletes everything. The lab
  has:
  - a storage VM;
  - a two-node k3s cluster;
  - a tiny lab-only NFS server, which backs the `regen` disk so NFS faults can be injected;
  - a lab-only bridge.

Nothing merges, and production is never a target. The shared mutations are limited to:
- lab VMs, a lab bridge and a lab Proxmox storage on the one Proxmox host;
- one host reboot for check 1, which Ben schedules.

**Tech stack:** Debian 13 (trixie); LIO through `python3-rtslib-fb` 2.1.76 and `targetcli-fb` 2.1.53; lvm2 2.03.31;
nftables 1.1.3; open-iscsi 2.1.11; democratic-csi v1.9.5 with chart 0.15.1; k3s v1.37.2+k3s1; packer plugin proxmox
v1.2.4; terraform with bpg/proxmox in `storage/` only; stdlib Python 3 with `unittest`.

**Spec:** apps `docs/adr/0017-retained-block-storage-vm-iscsi.md` (Accepted, with 2026-11-09 errata). Read the whole ADR
before any task. This plan repeats only the values each task needs.

**Evidence:**
- `~/.cache/claude-homelab-live/csi-slots/plan-scout-*.md` holds cited repo and upstream facts.
- `lab-plan-review.json` in the same folder holds the review this plan absorbed.

## Global Constraints

- **Branches.** Branch `feat/retained-storage-vm` from `origin/main` in ansible, packer, terraform and apps. Use a
  worktree under `~/.cache/claude-homelab-live/worktrees/<repo>-storage-vm`.
  - Commit with `git -c user.name="Ben Faingold" -c user.email=<ben-git-email> commit …`.
  - Never push, open a PR or merge unless Ben asks.
- **Live work.** Every live mutation needs Ben's explicit OK at that step. This covers `qm`, `pvesh`, `pvesm`, host
  network changes, packer builds, terraform applies, TrueNAS, ZFS, and any write to a production VM. Read-only checks
  also need an OK per session (memory `backup-review-live-access`).
- **Backup windows** (Asia/Jerusalem; ansible `docs/backup-and-restore.md:35-47`). No lab mutation, VM start or heavy
  I/O during:
  - 01:55-02:15 (dumps);
  - :25-:50 of 03, 09, 15 and 21 (TrueNAS snapshot, replication, `main/immich` snapshot);
  - 04:25 until the backup unit has finished;
  - Sunday 00:55-01:15 (vzdump);
  - Sunday 05:25 until maint has finished.

  Further rules:
  - **The backup lock.** Any step that touches `usbbk` holds `/run/lock/homelab-backup.lock` (runbook :115-129), and
    releases it well before 04:30 and Sunday 05:30.
  - **Never put lab files under pve `/root`, `/etc` or `/srv/backup-src`.** restic uploads the first two
    (`homelab-backup.py:221`), and every run unmounts the third.
  - **An unexpected pve reboot stops the lab.** Follow runbook :332-369. Only Ben clears the pstore record, and backups
    refuse until he does.
- **Maintenance-lock serialization.** While the lab holds the production lock (B1 Step 4 to B10), no ansible or terraform
  merge that triggers `deploy.yml` lands. The resource PRs (Task B0) land and deploy before B1 Step 4.
- **Docs commits.** Any ansible, terraform or packer commit that touches only docs carries `[skip ci]` in its subject (for
  terraform, in the PR title). A push to apps `main` only refreshes ArgoCD.
- **No production targets.**
  - Lab VMs are tagged `lab-storage`, `lab-k3s` or `lab-nfs`, never `k3s`, `master`, `worker` or `storage`.
  - Lab ansible runs use the static inventory `<lab>/inventory.yml`, hosts and groups only. Every lab override goes in
    `<lab>/vars.yml` and is passed as `-e @<lab>/vars.yml` on every lab `ansible-playbook` call, including
    `--list-tasks`. Extra vars beat the repo's `group_vars/all`; inventory group vars would lose to it.
  - The lab guard (Task A9) refuses any run whose `vip_address` is `10.9.9.99`, or not an address of a host in
    `masters`.
  - Lab runs never use production tokens, kubeconfigs, sealed secrets or the vault.
- **Lab shell.** All lab tooling runs in a container on VM300 that mounts only `<lab>`
  (`/var/lib/homelab-maintenance/lab-storage`, mounted as `/maintenance/lab-storage`). It has no runner work dir, no
  `_github_home` and no production `/maintenance` files.
  - `HOME=<lab>` and `KUBECONFIG=<lab>/.kube/config` are exported.
  - Every `kubectl` and `helm` call goes through `<lab>/labkube.sh`. It refuses unless the current server is
    `https://<lab-server vmbr0 address>:6443` and `kubectl get nodes -o name` is exactly `node/lab-server` and
    `node/lab-agent`.
- **Lab layout.** `<lab>` = `/var/lib/homelab-maintenance/lab-storage` on VM300. Raw evidence is copied to
  `~/.cache/claude-homelab-live/storage-lab/`, because scratch is tmpfs.
- **Secrets.**
  - Never print token Secrets, API tokens, k3s tokens or lab keys.
  - Ben provisions the lab credentials (Task B1). The executor never reads production credential files.
  - Ansible tasks that handle secrets use `no_log: true`. Evidence is scrubbed before it is copied.
- **Pinned versions.**
  - democratic-csi image
    `ghcr.io/democratic-csi/democratic-csi:v1.9.5@sha256:fc3b7d7ed3a616714139525075312758e23a5d425ffb539ad12c9bd20fb6001f`,
    chart `democratic-csi` 0.15.1 from `https://democratic-csi.github.io/charts/`.
  - bpg/proxmox: the newest release published on or before 2026-10-26, recorded in `storage/providers.tf`.
  - k3s `v1.37.2+k3s1`.
- **Names.**

  | Item | Value |
  |---|---|
  | Target IQN | `iqn.2026-11.net.starktastic.storage:<id>` |
  | Worker IQN | `iqn.2026-11.net.starktastic:<inventory_hostname>` (must equal the Kubernetes node name) |
  | VGs | `retained`, `regen` |
  | Cluster-wide tags, on VG `retained` only | `hold_create`, `hold_fence`, `fenced:<node>:<bootID>` |
  | Per-VG ledger tags | `ledger:<id>:creating`, `ledger:<id>:created`, `tombstone:<id>` |
  | LV tag | `pending-delete:<unix seconds>` |
  | `id` regex | `^(?!snapshot|pvmove)[a-z0-9][a-z0-9-]{0,62}$` |
  | LIO lock | `/run/lock/storage-lio` (flock) |
  | Save file | `/etc/rtslib-fb-target/saveconfig.json` |
  | Config | `/etc/homelab-storage/config.json` |
  | Out-of-service taint | `node.kubernetes.io/out-of-service=nodeshutdown:NoExecute` |
  | CSI driver name | `org.democratic-csi.node-manual` |
  | Metrics prefix | `storage_` |
  | ScrapeConfig `jobName` | `storage-vm` |

- **Timings** are config keys with production defaults:

  | Key | Default |
  |---|---|
  | `not_ready_seconds` | 300 |
  | `loop_seconds` | 15 |
  | `proof_timeout_seconds` | 60 |
  | `quarantine_seconds` | 259200 |
  | `blind_after_seconds` | 600 |
  | `pause_after` | `[]` |

  `pause_after` is a lab-only checkpoint list. Production never sets it.
- **Python on the storage VM:** stdlib plus Debian's `python3-rtslib-fb`, no pip.
  - Every subprocess goes through one module-level `host.run()`, and paths are module constants, so tests can fake the
    host. This is the `homelab-backup.py:22,40` convention: a `FakeHost.install()` patches them, as in
    `test_proxmox_backup.py:44-99`.
  - `rtslib` is imported lazily, so CI runs without it.
- **Tests:** `unittest`.
  - ansible tests go in `scripts/tests/`, following `test_proxmox_backup.py`. They may import PyYAML and Ansible's
    Templar, and they render templates through Templar.
  - Each test file gets its own step in `.github/workflows/validate.yml` job `lint`, after the existing test steps.
  - New playbooks are appended to the syntax-check list at `validate.yml:125`.
  - apps tests go in `scripts/storage/tests/` and are discovered automatically.
  - Tests that need `helm`, `terraform` or `packer` binaries say so, and are added to a CI job that has that binary.

## Review Focus

1. **Lab objects captured by production.** A lab VM with a `k3s` or `storage` tag would land in a production inventory
   group, and the next `deploy.yml` would configure it. Lab overrides set as inventory group vars would lose to
   `group_vars/all` and aim the lab at the production VIP. These are pinned by:
   - Task A9: `test_storage_group_requires_exact_tag` and `test_lab_guard`;
   - Task B1: the tag audit.
2. **A restart of `rtslib-fb-targetctl` or `nftables`.** A restart drops every session, or opens the firewall and empties
   the `fenced` set. Task A9 tests that nothing restarts either unit, and that nftables changes only reload.
3. **`blkid -p` exits 2 on an unreadable device.** Task A4 tests that `mkfs` runs only on an LV created in the same
   run, after a successful direct read.
4. **Clock skew between the storage VM and the API server.** NotReady age comes from the API response's `Date` header
   minus `lastTransitionTime`, never local time. Task A6 tests a storage-VM clock that runs 10 minutes fast.
5. **A fence on one VG leaking to the other.** A `fenced:` tag on `retained` must strip the worker's ACLs from `regen`
   targets too. Task A4 tests `test_fence_applies_to_regen_targets`.

---

## Part A: build (offline, on branches)

### Task A1: ansible: additive storage bridge role

**Files:**
- Create: `roles/proxmox_storage_bridge/{defaults,tasks,handlers}/main.yml`, `templates/bridge.j2`
- Create: `proxmox-storage-bridge.yml` (hosts `proxmox_hosts`)
- Create: `scripts/tests/test_proxmox_storage_bridge.py`
- Modify: `.github/workflows/validate.yml` (lint step, syntax-check list)

**Interfaces:**
- Produces vars `proxmox_storage_bridge_name` (default `vmbr2`) and `proxmox_storage_bridge_state`
  (`present`/`absent`). The lab uses `vmbr9`.

- [ ] **Step 1: Write the failing tests:**
  - `test_refuses_without_interfaces_d_source`: the first task asserts `/etc/network/interfaces` contains
    `source /etc/network/interfaces.d/*`.
  - `test_renders_uplinkless_bridge`: `bridge.j2` renders `auto vmbr2`, `iface vmbr2 inet manual`,
    `bridge-ports none`, `bridge-stp off` and `bridge-fd 0`, with no `address` line.
  - `test_never_writes_main_interfaces_file`.
  - `test_present_runs_ifup_only_this_bridge`: no task runs `ifreload`.
  - `test_absent_order`:
    1. assert that no `/etc/pve/qemu-server/*.conf` references the bridge;
    2. `ifdown <name>`;
    3. remove the file;
    4. assert `ip link show <name>` fails.
  - `test_host_only`: the playbook targets `proxmox_hosts` only, modelled on `test_proxmox_backup.py:434-447`.
- [ ] **Step 2: Run** `python3 scripts/tests/test_proxmox_storage_bridge.py`. Expected: FAIL.
- [ ] **Step 3: Implement** the role. It writes `/etc/network/interfaces.d/<name>` at mode 0644.
- [ ] **Step 4: Run** the test and `ansible-lint --offline`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): add an additive uplink-less storage bridge role`.

### Task A2: ansible: inventory validation, ledger and fence tags (pure)

**Files:**
- Create: `roles/storage_vm/files/homelab_storage/__init__.py`, `inventory.py`, `ledger.py`
- Create: `scripts/tests/test_storage_inventory.py`, `scripts/tests/test_storage_ledger.py`

**Interfaces:**
- Produces:
  - `inventory.load(text: str) -> list[Volume]`.
    - `Volume` is a frozen dataclass of `id`, `namespace`, `claim`, `size_bytes`, `cls` and `origin`.
    - It raises `InventoryError`.
  - `inventory.parse_size(s) -> int`, which accepts `Gi`/`Mi` only.
  - `inventory.vg_for(cls) -> 'retained'|'regen'`.
  - `ledger.Ledger.from_tags(tags)`, the per-VG `ledger:` and `tombstone:` tags, with `.state(id)` and
    `.tombstoned(id)`.
  - `ledger.Cluster.from_tags(retained_tags)`, read **only** from VG `retained`, with `.fenced() -> dict[node, bootid]`
    and `.holds() -> set[str]`.
  - `ledger.tag_*` helpers that return the exact strings from Global Constraints.

- [ ] **Step 1: Write the failing tests:**
  - `test_rejects_bad_id`: rejects `"Bad"`, `"-a"`, `"a"*64`, `"snapshot"`, `"snapshot-x"`, `"pvmove"` and `"pvmove1"`.
  - `test_rejects_duplicate_id`.
  - `test_class_picks_vg`.
  - `test_ledger_roundtrip`.
  - `test_fenced_tag_parses_uuid`.
  - `test_unknown_bootid`.
  - `test_cluster_tags_ignored_on_regen`: building `Cluster` from `regen` tags raises `ValueError`.
- [ ] **Step 2: Run** both tests. Expected: FAIL.
- [ ] **Step 3: Implement** with stdlib `json`, `re` and `dataclasses`.
- [ ] **Step 4: Run** both tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): parse the volume inventory and the LVM ledger`.

### Task A3: ansible: reconcile decisions (pure)

**Files:**
- Create: `roles/storage_vm/files/homelab_storage/plan.py`
- Create: `scripts/tests/test_storage_plan.py`

**Interfaces:**
- Consumes Task A2.
- Produces `plan.decide(volumes, vgs: dict[str, VgState], cluster: Cluster|None, removed_ok=2) -> Decision`.
  - `VgState` holds `ledger`, `lvs: dict[id, LvState(size_bytes, tags)]` and `present`.
  - `Decision` holds `actions`, `refusals: list[Refusal(id, reason)]` and `fail`.
  - `Action.kind` is one of `create_new`, `create_raw`, `export`, `extend`, `mark_pending` or `clear_pending`.
  - `cluster` is None when VG `retained` is missing or unreadable. Every action is then refused.

- [ ] **Step 1: Write the failing tests**, one per row of the ADR reconcile table:

  | Test | Input | Expected |
  |---|---|---|
  | `test_created_and_present_exports` | ledger `created`, LV exists | `export` |
  | `test_grow_extends` | inventory larger than LV | `extend` |
  | `test_shrink_refused` | inventory smaller | refusal `shrink` |
  | `test_new_origin_new` | not ledgered, no LV, `new` | `create_new` |
  | `test_new_origin_migrated` | `migrated` | `create_raw` |
  | `test_ledgered_lv_missing` | ledgered, no LV | refusal `lv-missing`, `fail` |
  | `test_orphan_refused` | LV not ledgered | refusal `orphan` |
  | `test_creating_refused` | ledger `creating` | refusal `crashed-create` |
  | `test_tombstone_refused` | tombstoned | refusal `tombstoned` |
  | `test_vg_missing_refuses_all` | `regen` missing | every `regen` entry refused, `fail` |
  | `test_retained_missing_refuses_everything` | `cluster` is None | every entry in both VGs refused, `fail` |
  | `test_hold_create` | `hold_create` | `export` only; every entry without an LV listed; `fail` |
  | `test_removed_marks_pending` | id removed | `mark_pending` |
  | `test_readded_clears_pending` | id back | `clear_pending` |
  | `test_more_than_two_removals_refused` | 3 removals | all refused, `fail` |
  | `test_id_in_other_vg_refused` | ledgered in `regen`, inventory `retained` | refusal `other-vg` |
  | `test_namespace_change_is_render_only` | only `namespace`/`claim` changed | no storage action |
- [ ] **Step 2: Run** `python3 scripts/tests/test_storage_plan.py`. Expected: FAIL.
- [ ] **Step 3: Implement** `decide()` as a pure function.
- [ ] **Step 4: Run** the test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): decide reconcile actions from the inventory and the ledger`.

### Task A4: ansible: host adapters and the reconcile executor

**Files:**
- Create: `roles/storage_vm/files/homelab_storage/host.py`, `lvm.py`, `lio.py`, `nft.py`, `metrics.py`, `reconcile.py`
- Create: `roles/storage_vm/files/storage-reconcile` (wrapper)
- Create: `scripts/tests/test_storage_reconcile.py`

**Interfaces:**
- Consumes Task A3.
- Produces:
  - `host.run(argv, check=True) -> CompletedProcess`.
  - `host.LIO_LOCK`, a flock context manager.
  - `host.checkpoint(name: str)`. It reads the config key `pause_after`; when `name` is in it, it logs
    `PAUSED at <name> pid=<pid>`, flushes, and sends SIGSTOP to its own process. Otherwise it does nothing.
  - `lvm.vgs() -> dict[str, VgState]`, from `vgs`/`lvs --reportformat json … --units b`.
  - `lvm.create(vg, id, size_bytes)` runs `lvcreate -n <id> -L <size>b -W y --yes -Z y <vg>`.
  - `lvm.extend(vg, id, size_bytes)`.
  - `lio.Lio`, a narrow wrapper over rtslib:
    - `ensure_target(id, dev, acl_iqns, portal)`;
    - `delete_target(id)`;
    - `delete_acl(iqn) -> list[session_info]`;
    - `acl_iqns(id)`;
    - `lun0_device(id) -> str|None`;
    - `sessions(id) -> list[str]`, which reads configfs `acls/<iqn>/info` and `dynamic_sessions` directly, and raises
      `InUse` on any read error;
    - `targets() -> set[id]`;
    - `save()`, which writes through `RTSRoot().save_to_file(tmp)`, `fsync`s, then `os.replace`s.
  - `lio.wwn(id) = str(uuid5(NAMESPACE_URL, 'iqn.2026-11.net.starktastic.storage:' + id))`.
  - `nft.ensure_fenced(addr)`, `nft.remove_fenced(addr)` and `nft.is_fenced(addr)`. The last parses
    `nft -j list set inet filter fenced`.
  - `metrics.write(name, samples)`: an atomic textfile under `/var/lib/prometheus/node-exporter/`.
  - CLI `storage-reconcile validate --inventory FILE`: schema checks only, no host I/O.
  - CLI `storage-reconcile apply --inventory FILE --config FILE [--dry-run]`. It prints JSON
    `{sha, actions, refusals, exported: [{id, size_bytes}]}` and exits 1 if `fail`.

- [ ] **Step 1: Write the failing tests** with a `FakeHost`:
  - `test_create_new_order`: calls in this order, each followed by `checkpoint('create:<step>')`:
    1. tag `ledger:<id>:creating`;
    2. `lvcreate`;
    3. `dd if=/dev/<vg>/<id> of=/dev/null bs=1M count=1 iflag=direct`;
    4. `blkid -p` (exit 2);
    5. `mkfs.ext4 -O mmp -e remount-ro -E mmp_update_interval=5`;
    6. mount on a private tmp dir, marker `.homelab-<id>-data` containing `homelab/<id>/data/v1\n`, umount;
    7. ledger `created`;
    8. `ensure_target`;
    9. `save`.
  - `test_unreadable_device_never_formats`: `dd` fails, so there is no `mkfs`, the ledger stays `creating`, and the
    exit code is 1.
  - `test_blkid_signature_never_formats`.
  - `test_existing_lv_never_formatted`: no `mkfs`, `blkid` or `dd` on `export`.
  - `test_create_raw_has_no_mkfs`.
  - `test_fenced_worker_acl_omitted`.
  - `test_fence_applies_to_regen_targets`: with `fenced:w2:B` on `retained`, a `regen` target's `ensure_target` gets
    only w1's IQN.
  - `test_fenced_worker_missing_from_set_fails`.
  - `test_extend_then_checkpoint`: `lvextend` is followed by `checkpoint('grow:lvextend')`.
  - `test_exported_lists_every_lv`: `exported` has every exported id with its LV size, whether or not it grew this run.
  - `test_save_is_atomic`.
  - `test_metrics_written`: `storage_vg_free_bytes{vg}`, `storage_target_missing{id}`, `storage_pending_delete{id,since}`,
    `storage_hold_create` and `storage_last_reconcile_success_timestamp_seconds`.
  - `test_whole_run_holds_lio_lock`.
  - `test_wwn_stable`.
  - `test_checkpoint_pauses_only_when_configured`: SIGSTOP is sent only for a listed name.
  - `test_targetctl_started_only_when_inactive_and_sessionless`: after `save`, if `systemctl is-active
    rtslib-fb-targetctl` is false and no session exists, `systemctl start rtslib-fb-targetctl` runs once; with sessions
    present it does not, and a warning is logged.
  - `test_validate_does_no_host_io`: `validate` makes no `host.run` calls.
- [ ] **Step 2: Run** `python3 scripts/tests/test_storage_reconcile.py`. Expected: FAIL.
- [ ] **Step 3: Implement** the modules.
  - TPG settings: `authentication=0`, `generate_node_acls=0`, `cache_dynamic_acls=0`, `demo_mode_discovery=0`.
  - Backstore: `emulate_tpu=1` and the deterministic `wwn`.
  - Portal: only `<bridge address>:3260`.
- [ ] **Step 4: Run** the test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): reconcile LVs and LIO targets from the plan`.

### Task A5: ansible: boot check and fence-set restore

**Files:**
- Modify: `roles/storage_vm/files/homelab_storage/reconcile.py`
- Test: `scripts/tests/test_storage_reconcile.py`

**Interfaces:**
- Produces:
  - `storage-reconcile boot-check --config FILE`:
    1. delete the ACLs of every worker in a `fenced:` tag, on every target in both VGs;
    2. `save`;
    3. exit 1 if any VG named in the config is missing, or if any ledgered `created` LV lacks LUN 0 bound to
       `/dev/<vg>/<id>`.
  - `restore_set(config)` re-adds every tagged worker's bridge address to the nft set. It reads `vgs` tags only and
    holds the LIO lock. Task A7 exposes it as `storage-fencer restore-set`, the ADR's name.

- [ ] **Step 1: Write the failing tests:**
  - `test_boot_check_fails_on_lunless_target`.
  - `test_boot_check_fails_on_missing_vg`.
  - `test_boot_check_strips_fenced_acls_before_check`: the order is delete, save, check.
  - `test_restore_set_adds_every_tagged_address`.
  - `test_restore_set_unknown_node_fails`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** both.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): check targets at boot and re-apply fences`.

### Task A6: ansible: fencer decisions (pure) and API client

**Files:**
- Create: `roles/storage_vm/files/homelab_storage/kube.py`, `fence_policy.py`
- Create: `scripts/tests/test_storage_fence_policy.py`

**Interfaces:**
- Produces `kube.Client(api, token_file, ca_file)`, stdlib `urllib` and `ssl` with a 5 s timeout. It re-reads the token
  and CA files on each request.
  - `.get(path) -> (body, server_time)`, where `server_time` comes from the `Date` header.
  - `.patch_node_taints(node, taints, resource_version)` sends `application/json-patch+json`:
    `[{"op":"test","path":"/metadata/resourceVersion","value":rv},{"op":"add","path":"/spec/taints","value":taints}]`.
    On a 409 or 422 it re-reads the node and retries up to 3 times.
  - It raises `ApiAuthError` on 401/403 and `ApiUnreachable` otherwise.
- Produces `fence_policy.evaluate(nodes, vas, cluster: Cluster, history: BootHistory, cfg, server_time) -> Verdict`.
  - `Verdict` holds `fence`, `unfence`, `continue_fence` and `reasons`.
  - `BootHistory` is stored in `/var/lib/storage-fencer/bootids.json` as `{node: {seen: […], last_ready: id}}`.

- [ ] **Step 1: Write the failing tests** (`w1` and `w2`, `not_ready_seconds=300`):

  | Test | Situation | Expected |
  |---|---|---|
  | `test_fences_after_window` | `w2` NotReady 301 s by server time, `w1` Ready | `fence == 'w2'` |
  | `test_not_before_window` | 299 s | none |
  | `test_clock_skew_uses_server_time` | local +600 s, server 100 s | none |
  | `test_needs_other_ready_untainted` | `w1` tainted | none, `no-peer` |
  | `test_both_not_ready` | both NotReady | none |
  | `test_one_at_a_time` | `w1` fenced | none |
  | `test_foreign_va_refused` | `w2` VA `spec.attacher == csi.proxmox.sinextra.dev` | none, `foreign-va` |
  | `test_holds_block` | `hold_fence` or `hold_create` | none |
  | `test_bootid_is_last_ready` | last Ready A, current B | tag bootID A |
  | `test_unfence_needs_unseen_bootid` | tag `w2:A`, Ready with A, or with a seen B | `continue_fence` |
  | `test_unfence_new_bootid` | Ready with unseen C | `unfence == ['w2']` |
  | `test_unknown_bootid_never_auto_unfences` | tag `w2:unknown` | stays fenced |
  | `test_unconfigured_node_ignored` | node not in `cfg.workers` | never fenced |

  Client tests:
  - `test_auth_error_vs_unreachable`.
  - `test_date_header_parsed`.
  - `test_patch_taints_node_without_taints_field`: a node JSON with no `spec.taints` gets an `add` op, and the
    resulting list holds the out-of-service taint.
  - `test_patch_preserves_other_taints`.
  - `test_patch_conflict_retries`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** both modules. Ready age comes from the `Ready` condition's `lastTransitionTime`.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): decide when the storage VM fences a worker`.

### Task A7: ansible: fencer executor, loop and CLI

**Files:**
- Create: `roles/storage_vm/files/homelab_storage/fencer.py`, `roles/storage_vm/files/storage-fencer`
- Create: `scripts/tests/test_storage_fencer.py`

**Interfaces:**
- Consumes Tasks A4–A6.
- Produces the CLI:

  | Command | What it does |
  |---|---|
  | `storage-fencer run` | The loop, every `loop_seconds`; handles SIGTERM between loops. |
  | `storage-fencer fence <node>` | Fence steps 1–5 with no taint of its own; the tag is `unknown`, and a running fencer finishes the fence and settles the tag. Prints the proof. |
  | `storage-fencer unfence <node> [--confirm-stopped]` | A tag with bootID `unknown` needs `--confirm-stopped`. Without it, prints the `qm status <vmid> --verbose` instruction and exits 1. |
  | `storage-fencer prove <node>` | Read-only. Prints JSON `{acl_present: {target: bool}, addr_in_set, established: [lines]}`; exits 1 if any leg fails. |
  | `storage-fencer restore-set` | `restore_set` from Task A5. |
  | `storage-fencer status` | JSON. |

- [ ] **Step 1: Write the failing tests:**
  - `test_fence_step_order`: under the LIO lock, with `checkpoint('fence:<n>')` after each step:
    1. tag `fenced:w2:A`;
    2. `nft.ensure_fenced`;
    3. `delete_acl` on every target in both VGs, logging the sessions;
    4. the proof;
    5. `save`;
    6. the taint patch.
  - `test_proof_failure_no_taint`: an `ss` line for 60 s (fake clock) means no taint, the failures counter grows, and
    the next loop retries.
  - `test_proof_checks_all_three`: an ACL present, an address missing, or an
    `ss -Htn state established '( sport = :3260 )' dst <addr>` line each fail the proof.
  - `test_prove_cli_read_only`: `prove` makes no write calls; it exits 1 with an `ss` line and 0 when all legs pass.
  - `test_resume_after_crash_each_step`: a fresh fencer started from the state left after each of steps 1–5 converges
    with one taint.
  - `test_unfence_order_tag_last`: ACLs, address, `save`, taint, tag, with `checkpoint('unfence:<n>')` after each.
  - `test_unfence_unknown_needs_confirmation`.
  - `test_api_error_does_nothing`: `ApiUnreachable` or `ApiAuthError` means no lio, nft or taint calls, and
    `storage_fencer_api_errors_total{code="unreachable"|"auth"}` grows.
  - `test_history_frozen_while_fenced`: each loop records the current bootID of **unfenced** workers in `seen` (and
    `last_ready` while Ready). A fenced worker's history is not changed. After an unfence, its new bootID is added.
  - `test_slow_reboot_unfences`:
    - tag `w2:A`, `seen={A}`;
    - loop 1: `w2` NotReady with C, and C is still unseen;
    - loop 2: Ready with C, so `w2` is unfenced.
  - `test_manual_fence_unknown_bootid`.
  - `test_metrics`: `storage_fence_active{node}`, `storage_fence_failures_total`,
    `storage_fencer_last_api_success_timestamp_seconds`, `storage_fencer_api_errors_total{code}`.
- [ ] **Step 2: Run** `python3 scripts/tests/test_storage_fencer.py`. Expected: FAIL.
- [ ] **Step 3: Implement** the executor. Every step is idempotent.
- [ ] **Step 4: Run** the test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): fence and unfence workers at the storage side`.

### Task A8: ansible: expiry

**Files:**
- Modify: `roles/storage_vm/files/homelab_storage/reconcile.py`
- Create: `scripts/tests/test_storage_expiry.py`

**Interfaces:**
- Produces:
  - `storage-reconcile expire-candidates --config FILE`. It prints JSON
    `[{id, vg, since, volume_handle, iqn, sessions: bool}]` for `pending-delete` LVs older than `quarantine_seconds`,
    and skips everything when `hold_create` is set.
  - `storage-reconcile expire --id ID --config FILE`. Under the LIO lock it re-checks the age, the hold and the sessions,
    then runs, in order:
    1. `delete_target`;
    2. `save`;
    3. `blkdiscard`;
    4. `lvremove -y`;
    5. remove `ledger:<id>:*`;
    6. add `tombstone:<id>`.

    Any error exits 1.

- [ ] **Step 1: Write the failing tests:**
  - `test_not_old_enough`.
  - `test_hold_create_skips`.
  - `test_session_read_error_counts_in_use`.
  - `test_expire_order`.
  - `test_expire_rechecks_session`.
  - `test_tombstone_written`.
- [ ] **Step 2: Run** the test. Expected: FAIL.
- [ ] **Step 3: Implement** it.
- [ ] **Step 4: Run** the test. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): expire removed volumes after quarantine`.

### Task A9: ansible: storage_vm role, playbooks, lab guard and inventory group

**Files:**
- Create: `roles/storage_vm/{defaults,tasks,handlers}/main.yml`
- Create these templates:
  - `config.json.j2`;
  - `nftables.conf.j2`;
  - `storage-fencer.service.j2`;
  - `nftables.service.d-50-fences.conf.j2`;
  - `rtslib-fb-targetctl.service.d-50-homelab.conf.j2`.
- Create: `storage.yml`, `storage-expiry.yml`, `tasks/lab-guard.yml`
- Create: `lab/inventory.example.yml` and `lab/vars.example.yml`. These are examples only; the real ones live in
  `<lab>`.
- Modify: `inventory/proxmox.yml` (group `storage`), `.github/workflows/validate.yml`
- Create: `scripts/tests/test_storage_vm_role.py`

**Interfaces:**
- **Role variables:**
  - `storage_vm_workers`: a list of `{name, bridge_address}`. `name` equals the node name and the inventory hostname.
  - `storage_vm_bridge_address`.
  - `storage_vm_ssh_sources`: a required, non-empty list of addresses or CIDRs.
  - `storage_vm_api_url`, default `https://{{ vip_address }}:6443`.
  - `storage_vm_inventory_repo` and `storage_vm_inventory_branch` (default `main`). The branch must be a branch name;
    a 7–40 hex value fails.
  - `storage_vm_inventory_path`, default `infrastructure/base-configs/files/retained-volumes.json`.
  - `storage_vm_timings`.
  - `storage_vm_maintenance_root`, default `/maintenance`.
- **`tasks/lab-guard.yml`**, imported as the first play of `k3s.yml`, `storage.yml` and `storage-expiry.yml`, tagged
  `always`. When the `inventory_file` path contains `/lab-storage/`, it asserts `vip_address != '10.9.9.99'` and
  `vip_address in groups['masters'] | map('extract', hostvars, 'ansible_host')`.
- **`storage.yml` plays:**
  1. **localhost:** resolve `refs/heads/<branch>` with `git ls-remote` and log the SHA. Fetch the file at that SHA.
     Run `storage-reconcile validate` from the controller's role files.
  2. **`masters[0]`:** slurp `k3s.yaml` (no_log), rewrite it to `storage_vm_api_url`, write a 0600 tempfile. This is
     the i915-acceptance pattern.
  3. **`storage` (become), before any lock call:** copy the package and the inventory to a temp dir. Run
     `python3 -I <tmp>/storage-reconcile apply --dry-run`, which reads the real ledger. A nonzero exit ends the run.
  4. **`storage` (become):**
     1. `maintenance_lock.py verify --root {{ storage_vm_maintenance_root }}`, with `delegate_to: localhost`,
        `become: false`, `run_once: true`;
     2. the role;
     3. the token Secret `democratic-csi/storage-fencer-token` to `/etc/storage-fencer/{token,ca.crt}` (0600,
        `no_log`, notify `Restart storage-fencer`). A missing Secret is a warning;
     4. `storage-reconcile apply`.
  5. **`workers`:** for each `exported` id whose PV has a VolumeAttachment on this node:
     1. find that target's session and run `iscsiadm -m session -r <sid> -R`;
     2. read `blockdev --getsize64` of `/dev/disk/by-path/ip-<portal>-iscsi-<iqn>-lun-0`;
     3. fail if it is smaller than `size_bytes`;
     4. otherwise run online `resize2fs` on it.

     This is level-triggered, so an interrupted grow finishes on the next run.
- **`storage-expiry.yml` plays:**
  1. the lab guard;
  2. lock verify (delegated to localhost, as above);
  3. kubeconfig;
  4. `expire-candidates`;
  5. on localhost, per candidate:
     1. list PVs with `spec.csi.volumeHandle == id`;
     2. refuse if any has a VolumeAttachment, or a `claimRef` PVC used by a Pod;
     3. delete the PVCs and PVs;
     4. `expire --id`.
- **Handlers:** `Reload systemd`, `Reload nftables` (`systemctl reload nftables`) and `Restart storage-fencer`. These
  are the only restarts allowed.
- **Drop-ins:**
  - The ansible targetctl drop-in carries `After=nftables.service` and two `ExecStartPost=` lines, in order:
    1. `storage-fencer restore-set`;
    2. `storage-reconcile boot-check`.

    It has no vgchange line; that lives in the image (Task A11).
  - The nftables drop-in carries `ExecReload=/usr/local/sbin/storage-fencer restore-set` and
    `ExecStartPost=-/usr/local/sbin/storage-fencer restore-set`.

- [ ] **Step 1: Write the failing tests:**
  - `test_storage_group_requires_exact_tag`: true for `["storage"]`, false for `["lab-storage"]`.
  - `test_lab_guard`: the guard is the first play of all three playbooks, it is tagged `always`, and it asserts the
    VIP rules.
  - `test_no_restart_of_target_or_nftables`.
  - `test_role_never_sets_targetctl_state`: the role only enables `rtslib-fb-targetctl`.
  - `test_nftables_order`: policy drop. Then, in order: `ip saddr @fenced drop`;
    `ct state established,related accept`; `iif lo accept`; tcp/22 from `storage_vm_ssh_sources`; tcp/3260 and
    tcp/9100 on the bridge interface from the worker bridge addresses only.
  - `test_empty_ssh_sources_fails`.
  - `test_fenced_set_elements_rendered`.
  - `test_targetctl_dropin`: the exact lines above, and no `vgchange`.
  - `test_nftables_dropin`.
  - `test_packages_held`: `python3-rtslib-fb` and `targetcli-fb`.
  - `test_token_copy_no_log_and_restarts_only_fencer`.
  - `test_ledger_dry_run_on_storage_before_lock`: play 3 comes before any `maintenance_lock.py` task.
  - `test_lock_verify_runs_on_controller`: every `maintenance_lock.py` task has `delegate_to: localhost` and
    `become: false`.
  - `test_expiry_verifies_lock_before_delete`.
  - `test_branch_rejects_sha`.
  - `test_resolves_branch_tip_and_logs_sha`.
  - `test_growth_play_is_level_triggered`: it loops over `exported`, not over a grown list.
- [ ] **Step 2: Run** the test. Expected: FAIL.
- [ ] **Step 3: Implement** the role and the playbooks.
  - Asserts come first, as in `roles/proxmox_backup`.
  - Programs go to `/usr/local/lib/homelab-storage/` and wrappers to `/usr/local/sbin/` at 0755.
  - Add the playbooks to the syntax-check list, and a lint step per new test file from A2–A9.
- [ ] **Step 4: Run** all new tests, `ansible-lint --offline`, and
  `ansible-playbook -i inventory/proxmox.yml --syntax-check storage.yml storage-expiry.yml`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): add the storage VM role and its playbooks`.

### Task A10: ansible: worker iSCSI and k3s settings

**Files:**
- Modify: `roles/k3s_common/{defaults,tasks}/main.yml`, `roles/k3s_workers/tasks/main.yml`
- Modify: `scripts/tests/test_proxmox_csi_bootstrap.py`
- Create: `scripts/tests/test_k3s_storage_settings.py`

**Interfaces:**
- Produces `k3s_common_kube_controller_manager_args`, which adds `disable-force-detach-on-timeout=true` on masters.

- [ ] **Step 1: Write the failing tests:**
  - `test_iqn_written_before_install`: on workers, `/etc/iscsi/initiatorname.iscsi` is written with
    `InitiatorName=iqn.2026-11.net.starktastic:{{ inventory_hostname }}` before `apt: open-iscsi`, and both come before
    the join.
  - `test_kcm_flag_masters_only`.
  - `test_kubelet_dropin`: `/var/lib/rancher/k3s/agent/etc/kubelet.conf.d/50-graceful-shutdown.conf` contains
    `apiVersion: kubelet.config.k8s.io/v1beta1`, `kind: KubeletConfiguration`, `shutdownGracePeriod: 90s` and
    `shutdownGracePeriodCriticalPods: 40s` (was 60s/10s; raised by the F14 fix, 2026-11-18). It is not a `kubelet-arg`.
  - `test_fstrim_timer_enabled`.
  - `test_no_multipath`.
  - `test_persistent_journal`: `/var/log/journal` exists, which check 11 needs.
  - An update to `test_disabled_preserves_exact_config_bytes`.
- [ ] **Step 2: Run** both files. Expected: FAIL.
- [ ] **Step 3: Implement.** `iscsid.socket` is enabled and `node.startup` stays `manual`.
- [ ] **Step 4: Run** the tests and lint. Expected: PASS.
- [ ] **Step 5: Commit** `feat(k3s): add worker iSCSI identity, graceful shutdown and no timed force-detach`.

### Task A11: packer: base, k3s and storage images

**Files:**
- Delete: `source.pkr.hcl`, `build.pkr.hcl`, `scripts/bootstrap.sh`, `scripts/delete_builder_user.sh`
- Create: `source-{base,k3s,storage}.pkr.hcl`, `build-{base,k3s,storage}.pkr.hcl`
- Create: `scripts/{base,k3s,storage,seal}.sh`, `files/storage/rtslib-fb-targetctl.service.d/10-lvm.conf`
- Modify: `config.pkr.hcl`, `variables.pkr.hcl`, `http/preseed.cfg.tmpl:385`, `.github/workflows/build.yml`
- Create: `scripts/tests/test_image_layout.py`

**Interfaces:**
- Produces:
  - Sources `proxmox-iso.base`, `proxmox-clone.k3s` and `proxmox-clone.storage`, which are also the manifest names.
  - Vars `base_vm_id` (900), `k3s_vm_id` (901), `storage_vm_id` (902) and `vm_name_prefix` (`packer`).
  - `local.vm_name.<role>` = `<prefix>-<role>-<debian>-<stamp>`.
  - The image drop-in, `10-lvm.conf`: `Wants=network-online.target`, `After=network-online.target`,
    `ExecStartPre=/sbin/vgchange -ay retained` and `ExecStartPre=-/sbin/vgchange -ay regen`.

- [ ] **Step 1: Write the failing tests:**
  - `test_preseed_has_no_compiler`: `pkgsel/include` is exactly `qemu-guest-agent openssh-server`.
  - `test_clone_sources_inject_key`: `ssh_username` only, `clone_vm_id = var.base_vm_id`, `task_timeout = "10m"`,
    `cloud_init = true`, plus the repeated hardware block.
  - `test_seal_contents`: `seal.sh` runs last in every build, and contains:
    - `truncate -s 0 /etc/machine-id`;
    - the dbus relink;
    - `cloud-init clean --logs`;
    - `userdel -r -f "$BUILDER_USER"` followed by a fatal `getent passwd` check;
    - `rm -f /etc/sudoers.d/$BUILDER_USER`;
    - and, only under `CLONE_BUILD=1`, removal of `/etc/sudoers.d/90-cloud-init-users`.
  - `test_clone_scripts_wait_for_cloud_init`.
  - `test_gpu_stack_only_in_k3s`.
  - `test_storage_script`: it installs `targetcli-fb lvm2 nftables prometheus-node-exporter`, runs
    `systemctl enable nftables` and `apt-mark hold python3-rtslib-fb targetcli-fb`, and fails if `build-essential` or
    `gcc` is installed.
  - `test_lvm_dropin`: the exact `10-lvm.conf` lines above.
  - `test_build_workflow_order`:
    - `base` runs `-only='proxmox-iso.base'`;
    - `k3s` and `storage` need `base`;
    - the release and terraform PR jobs select `name=="k3s"`;
    - `push-storage-manifest` needs `storage`;
    - both manifest jobs merge by `name`;
    - there is a `concurrency` group.
  - `test_pkrvars_keys_unchanged`.
- [ ] **Step 2: Run** `python3 scripts/tests/test_image_layout.py`. Expected: FAIL.
- [ ] **Step 3: Implement** the split using the line map in `plan-scout-packer.md` §1. Add the test as a CI step.
- [ ] **Step 4: Run** the test, then `packer fmt -check -recursive .`, `packer validate .` (with the CLAUDE.md
  placeholder vars, in a `hashicorp/packer:light` container), `shellcheck scripts/*.sh` and
  `shfmt -i 2 -ci -s -d scripts/`. Expected: pass.
- [ ] **Step 5: Commit** `feat(images): split the template into base, k3s and storage images`.

### Task A12: terraform: the storage/ root on bpg and the clone-source check

**Files:**
- Create: `storage/{providers,main,variables,outputs}.tf`
- Create: `scripts/check_clone_source.py`
- Create: `scripts/tests/test-storage-root.py`, `scripts/tests/test-check-clone-source.py`

**Interfaces:**
- Variables:

  | Variable | Default |
  |---|---|
  | `storage_template_vmid` | — |
  | `vm_id`, `name` | — |
  | `cores` | 2 |
  | `memory` | 2048 |
  | `lan_bridge` | `vmbr0` |
  | `lan_ipv4`, `lan_gateway` (nullable) | — |
  | `storage_bridge`, `storage_ipv4` | — |
  | `nameserver` | — |
  | `cloudinit_datastore` | — |
  | `username` | `debian` |
  | `ssh_pub_keys` (list, sensitive) | — |
  | `data_disks` (list of `{interface, datastore_id, path_in_datastore, size}`) | — |
  | `tags` | `["storage"]` |
  | `generation` | — |

- VM `proxmox_virtual_environment_vm.storage`:
  - `clone { vm_id = var.storage_template_vmid, full = true }`;
  - `initialization`: a `user_account` (username and keys), one `ip_config` per NIC in NIC order, and `dns`;
  - `stop_on_destroy = true`, `purge_on_destroy = false`, `delete_unreferenced_disks_on_destroy = false`;
  - disks with `path_in_datastore`, `file_format = "raw"`, `discard = "on"` and `iothread = true`;
  - data disks with `cache = "none"`;
  - lifecycle `prevent_destroy = true`, `ignore_changes = [clone, startup]`, and
    `replace_triggered_by = [terraform_data.generation]`. Ansible `guest_startup.yml` owns `startup`, as it does for the
    k3s VMs (`modules/vm/main.tf:291-293`).
- Backend key: `storage/terraform.tfstate`.
- `check_clone_source.py <vmid>` queries `GET /api2/json/cluster/resources?type=vm` with the `PROXMOX_VE_*` env. It
  exits 0 only if an entry has `vmid == <vmid>` and `template == 1`. The foundation plan wires it into `apply.yml`.

- [ ] **Step 1: Write the failing tests:**
  - `test-storage-root.py`, with the `test-rebuild-cohort.py` pattern and the terraform binary:
    - `test_template_change_is_noop`;
    - `test_generation_change_refused` ("Instance cannot be destroyed");
    - `test_data_disks_attach_existing`;
    - `test_destroy_keeps_unreferenced_disks`;
    - `test_cloud_init_user_and_keys`;
    - `test_startup_ignored_and_cache_none`;
    - `test_root_is_independent`: no root or module file references `storage/`, and the backend keys differ.
  - `test-check-clone-source.py`, with a canned API: `test_present_template` (exit 0), `test_absent` (1) and
    `test_not_a_template` (1).
- [ ] **Step 2: Run** both. Expected: FAIL.
- [ ] **Step 3: Implement.** Add both tests to `validate-and-plan.yml` job `rebuild-policy-tests`.
- [ ] **Step 4: Run** the tests, `terraform fmt -check -recursive .` and
  `terraform -chdir=storage init -backend=false && terraform -chdir=storage validate`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): add a separate storage VM root on bpg`.

### Task A13: apps: democratic-csi app and fencer RBAC

**Files:**
- Create: `infrastructure/system/democratic-csi/app.yaml` (`deployPhase: controllers`, `manifests: true`, chart 0.15.1),
  `values.yaml`, `manifests/namespace.yaml` (PSA `enforce: privileged`) and `manifests/storage-fencer.yaml`
- Create: `scripts/storage/tests/test_democratic_csi_values.py` (needs `helm`; the `validate` job has it)

**Interfaces:**
- Produces the CSIDriver `org.democratic-csi.node-manual`, and in `democratic-csi` the SA `storage-fencer` and the
  `kubernetes.io/service-account-token` Secret `storage-fencer-token`.

- [ ] **Step 1: Write the failing tests:**
  - `test_images_pinned_by_digest`.
  - `test_blkid_strategy_on_node`.
  - `test_attacher_runs`.
  - `test_no_provisioner_resizer_snapshotter`.
  - `test_mkfs_options`: `["-O","mmp","-e","remount-ro"]`.
  - `test_fencer_rbac`: exactly `nodes: get,list,watch,patch` and `storage.k8s.io volumeattachments: get,list`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s scripts/storage/tests -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the app.
- [ ] **Step 4: Run** the tests and kubeconform. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): add democratic-csi node-manual and the fencer account`.

### Task A14: apps: inventory, renderer, guard and CI check

**Files:**
- Create: `infrastructure/base-configs/files/retained-volumes.json` (`[]`)
- Create: `infrastructure/base-configs/templates/retained-volumes.yaml` and `retained-volumes-guard.yaml`
- Modify: `templates/globals.yaml` (`global.network.storagePortal`)
- Create: `scripts/check-retained-inventory.py`, `scripts/storage/tests/test_retained_inventory.py`
- Modify: `.github/workflows/validate-and-diff.yml`. Add a step after the NAS test, with checkout `fetch-depth: 0` and
  `pull_request` types plus `labeled` and `unlabeled`. The step goes after `:93-96` and before "Check alert policy". The
  new types also re-run the required `homepage-render` and diff jobs on label events (`:3-6`, `:235-278`); check that
  they still pass on a label-only event.

**Interfaces:**
- Per entry, it renders:
  - a PV `<id>`: `ReadWriteOncePod`, `Retain`, `fsType: ext4`, `volumeHandle: <id>`, volumeAttributes
    `{portal, iqn, lun: "0", node_attach_driver: iscsi, provisioner_driver: node-manual}`, `claimRef` without a uid, and
    `Prune=false,Delete=false`;
  - a PVC `<namespace>/<claim>` with `volumeName: <id>`;
  - a marker-only guard for `origin: new`.
- `python3 scripts/check-retained-inventory.py --base origin/main --override-label storage-removals-approved`.

- [ ] **Step 1: Write the failing tests:**
  - `test_id_change_rejected`.
  - `test_class_or_origin_change_rejected`.
  - `test_size_decrease_rejected`.
  - `test_bad_id_rejected`: the A2 cases.
  - `test_regex_matches_ansible`: the pattern string equals the Global Constraints one.
  - `test_three_removals_need_label`.
  - `test_readd_allowed`.
  - `test_render_pv_shape`: `helm template retained infrastructure/base-configs -f templates/globals.yaml -f <fixture>
    --show-only templates/retained-volumes.yaml`.
  - `test_guard_marker_only_for_new`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the files.
- [ ] **Step 4: Run** the tests, yamllint and kubeconform. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): render retained volumes from one inventory`.

### Task A15: apps: storage VM scrape and alerts

**Files:**
- Create: `services/operations/kube-prometheus-stack/manifests/storage-vm.yaml`. It holds:
  - a ScrapeConfig with `jobName: storage-vm`, label `release: kube-prometheus-stack`, and a static target
    `<storagePortal host>:9100`;
  - a PrometheusRule.
- Modify: `scripts/check-alert-policy.py`

- [ ] **Step 1: Write the failing promtool cases**, each one firing:
  - `StorageVMDown`: `up{job="storage-vm"} == 0` for 5 m.
  - `StorageReconcileFailing`: no success for 2 h.
  - `StorageTargetMissing`.
  - `StorageVGLowSpace`: under 15 %.
  - `StoragePendingDelete`.
  - `StorageHoldCreate`.
  - `StorageWorkerFenced`.
  - `StorageFenceFailed`.
  - `StorageFencerBlind`: no API success for 10 m, or `node_textfile_mtime_seconds` older than 10 m. One case each for
    auth, unreachable and stale.
  - `NodeOutOfServiceTaintStuck`: `kube_node_spec_taint{key="node.kubernetes.io/out-of-service"}` for 15 m.

  Also `test_job_matchers_match_scrapeconfig`: every `job="…"` matcher equals the ScrapeConfig `jobName`.

  Build each `absent()`-style case as its own promtool group, and append `*storage_tests` as
  `scripts/check-alert-policy.py:275` and `:352` do for the existing sets.
- [ ] **Step 2: Run** `python3 scripts/check-alert-policy.py`, with `promtool` on PATH or the docker prefix from
  `validate-and-diff.yml:98-105` as arguments. Expected: FAIL.
- [ ] **Step 3: Implement** the rules.
- [ ] **Step 4: Run** it again. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): scrape the storage VM and alert on storage and fencing`.

---

### Task A16: variant N, a storage-VM-side NFS mount (built 2026-11-16, removed 2026-11-18)

> **Removed (Ben, 2026-11-18: D1 = host path).** The variant N legs ran in B8 Check 8 and B10 Step 4. The code was
> then removed from the ansible and packer branches, `nfs-common` included. Only the panic sysctl and
> `test_guest_panics_on_oops` stay: an oops should reboot the storage VM on the host path too.

**Files:**
- Modify: packer `scripts/storage.sh` and `scripts/tests/test_image_layout.py`, which add `nfs-common` to
  `test_storage_script`.
- Modify: ansible `roles/storage_vm`, adding:
  - `storage_vm_nfs_mounts`, a list of `{what, where, options}`, default `[]`;
  - `storage_vm_loop_disks`, a list of `{file, vg}`, default `[]`;
  - a systemd `.mount` per mount and a `storage-loop@.service` (`losetup --direct-io=on --find --show <file>`);
  - the targetctl drop-in, which gains `Requires=` and `After=` on those units only when the lists are non-empty;
  - sysctl `kernel.panic_on_oops=1` and `kernel.panic=10` in the storage VM.
- Test: `scripts/tests/test_storage_vm_role.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_no_nfs_units_by_default`.
  - `test_mount_before_loop_before_targetctl`.
  - `test_loop_uses_direct_io`.
  - `test_guest_panics_on_oops`.
  - `test_nfs_common_in_storage_image`.
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the changes.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(storage): optionally attach data disks from an in-guest NFS mount`.

---

## Part B: lab qualification (live; Ben approves each mutation)

**Recording.** Each step records the commands it ran, the scrubbed output and pass/fail in
`docs/superpowers/reports/2026-11-<dd>-retained-storage-lab-results.md`.

**Failures.** A failed check stops the lab for a design decision. Never patch around a failure in the lab.

**Crash windows.** Use `pause_after` (Task A4) to stop a process at a named step, then SIGKILL it or reboot. Never race
a timed kill.

### Task B0: Make room on the host (before any lab VM; Ben picks the option)

**Decided (Ben, 2026-11-16), supersedes the options below:**
- ansible `feat/arc-cap-vm300-balloon`: ARC cap 8 GiB through a tmpfiles line in `proxmox_guest_startup`, applied
  live on merge (Ben OK'd the live write; merge attended, outside the backup windows), and VM300 balloon = 4096.
- terraform `feat/k3s-memory-shrink`, one PR: master 16 to 12 GiB, both workers 28 to 24 GiB, normal mode, with
  the attended-merge checklist in its body (re-plan right before merge, apps merges and Renovate held, each worker
  Ready within 5 minutes, any `-/+` or disk line is a stop). Merges after the ansible PR has deployed and VM300
  reads 4 GiB actual.
- Live read 2026-11-16: MemAvailable 10.0 GiB before either change; expected about 13 GiB after the ansible PR
  and VM200, plus 8 GiB from the workers. The B1 Step 1 gate is unchanged.

The host had about 6 GiB available on 11-15, after KSM went off, with the 1 GiB crash-kernel reservation still in place.
The lab peak is 5.5 GiB. Ben picks one option (refresh advice §D):

- **Option 1: cap the host ARC at 8 GiB (recommended).** An ansible PR writes only the modprobe option and refreshes the
  initramfs. It has no live sysfs task, because `proxmox-guest-startup.yml` runs on merge without a lock. It takes
  effect at the next host boot, together with ansible#333's crashkernel removal. That gives about +5.6 GiB.
- **Option 2: shrink VM200 from 16 to 12 GiB.** A terraform PR. The saved plan must show `~ update in-place` with no disk
  change, and any `-/+` is a hard stop. VM200 is drained first. It costs a master reboot.

In both cases VM300 goes to a fixed 4096 MiB (balloon off), because helm-diff peaks at 3.4 GiB and lab tooling runs
there. The PRs merge and deploy before B1 Step 4 takes the lock.

### Task B1: Preflight, allocation and credentials

- [ ] **Step 1: Read-only preflight** (Ben OKs using the live helper):
  - `/proc/meminfo`, ARC `size` and `c_max`, and `/proc/cmdline` (is `crashkernel=` still reserved?);
  - `qm list` with tags, and `qm config` for 100, 200, 201, 202 and 300 (cores, memory, balloon);
  - VM300's actual memory (`pvesh get /nodes/pve/qemu/300/status/current`);
  - `pvesm list k3s-block` for owner 9970, and `pvesm status`;
  - `zfs get available` for `apps/k3s-block` and `vm-pool`, and `zfs list usbbk`;
  - `systemctl list-timers 'homelab-backup-*'`, `ls /var/lib/systemd/pstore`, and the vzdump job's VM list in
    `/etc/pve/jobs.cfg`;
  - `/proc/self/mountstats` for `k3s-block`, as a baseline;
  - the vmbr0 and vmbr1 DHCP pools, and `ip -br link`.

  Expected:
  - MemAvailable is at least 8.5 GiB (the 5.5 GiB lab peak plus 3 GiB), read while VM300 holds its full 4096 MiB;
  - pstore is empty, the last `pve-backup` run is green, and `usbbk` has at least 50 GiB free;
  - the vzdump job lists only 100 and 300;
  - IDs 970–979, 9970 and 9979 are unused;
  - `vmbr9` and storage `lab-nfs` are absent;
  - no VM outside 100, 200–202 and 300 carries `k3s`, `master`, `worker` or `storage`.

  Repeat the tag audit after every clone. Any collision aborts.
- [ ] **Step 2: Record the allocation:**

  | VM | Name | RAM | NICs | Tag |
  |---|---|---|---|---|
  | 970 | `lab-nfs` | 512 MiB, 1 vCPU | vmbr0 | `lab-nfs` |
  | 971 | `lab-storage` | 1.5 GiB, 2 vCPU | vmbr0, vmbr9 (10.99.9.10) | `lab-storage` |
  | 972 | `lab-server` | 2 GiB, 2 vCPU | vmbr0, vmbr1, vmbr9 (.11) | `lab-k3s` |
  | 973 | `lab-agent` | 1.5 GiB, 2 vCPU | vmbr0, vmbr1, vmbr9 (.12) | `lab-k3s` |

  Every lab VM gets `--cpuunits 50` and no ballooning. There are two k3s nodes because fencing needs a Ready peer.
  Templates are built one at a time, before any lab VM runs.
  | 974/975/976 | lab templates | — | — | `lab` |

  - The vmbr0 and vmbr1 addresses are static, picked outside the DHCP pools in Step 1. The VIP is 972's vmbr0 address.
  - **Data disks:**
    - `retained`: `k3s-block:9970/vm-9970-disk-0.raw`, 8 GiB, on the real production path, for checks 1, 10 and 12;
    - `regen`: `lab-nfs:9970/vm-9970-disk-1.raw`, 4 GiB, on the lab NFS so check 8 can fault it.
  - The ceiling is 5.5 GiB. Stop any start that leaves MemAvailable under 3 GiB, or VM300 under its full 4096 MiB.
- [ ] **Step 3: Credentials. Ben performs this; the executor never reads the values.**
  - Ben creates a Proxmox user and API token scoped to a pool `lab-storage` (VMIDs 970–979 and 9970), with datastore
    allocation on `k3s-block`, `lab-nfs`, `vm-pool` and `local-zfs`.
    **Layout (2026-11-16):** per-VMID ACLs instead of a pool, so packer and bpg need no pool argument. User
    `lab-storage@pve`, token `lab` (privsep 0). `PVEVMAdmin` on `/vms/970`–`976` and `/vms/9970`; `PVEDatastoreUser` on
    `k3s-block`, `local-zfs` and `vm-pool` (`lab-nfs` after B2 Step 3); a `LabISO` role (`Datastore.Audit`,
    `Datastore.AllocateTemplate`) on `local` for the ISO upload; `PVESDNUser` on `/sdn/zones/localnetwork`; `PVEAuditor`
    on `/nodes/pve`. `pve.env` is in sourced form (`set -a; . pve.env`).
    **Finding (2026-11-16, B2 Step 2):** destroying a VM drops its `/vms/<id>` ACLs on PVE 9.2.28, with or without
    `purge` (the clone checks lost `/vms/972` and `/vms/973`). Per-VMID grants cannot survive B7's rebuilds, so the
    lab goes back to the pool above: `PVEVMAdmin` on `/pool/lab-storage`, templates 974-976 as members, every lab
    clone and create passes the pool (`pool=` for `qm clone`/API, a lab-only `pool_id` variable in terraform
    `storage/`), and every lab mutation first asserts that the pool's members are lab IDs only. B11 removes the pool
    and its ACL.
  - He writes `<lab>/creds/pve.env` at mode 0600 with:
    - `PKR_VAR_proxmox_api_*`, `PKR_VAR_runner_host_ip` and the repo's non-secret packer vars;
    - `PROXMOX_VE_ENDPOINT` and `PROXMOX_VE_API_TOKEN`.
  - The executor generates `<lab>/ssh/id_lab` (ed25519, mode 0600).
  - `<lab>/creds` and `<lab>/ssh` are a tmpfs mount (mode 0700). Otherwise the Sunday vzdump of VM300 would carry them
    off-site. After a VM300 reboot, Ben re-creates `pve.env` and the executor makes a new key.
  - **Lab data stays local (Ben, 2026-11-16: temporary exclude).** The lab disk on `k3s-block` is still replicated to
    `usbbk/tn`, but restic skips it. The ansible PR `feat/lab-backup-exclude` adds
    `/srv/backup-src/k3s-block/images/9970` to `proxmox_backup_excludes`, and it merges and deploys before B3. So B9
    Step 3 (off-site restore) is recorded as not run; the off-site path was proven on 2026-11-13 with real images.
  - The lab ansible runs use a lab copy of the ansible branch in `<lab>/ansible`. In it, `group_vars/all/secrets.yml`
    is replaced by an unencrypted lab file with every key the vault defines, set to empty or anonymous values, so
    `docker_hub_*` stays empty. There is no `.vault_pass`, and `ANSIBLE_VAULT_PASSWORD_FILE` is unset, so a vaulted
    file fails loudly.
  - Host-level steps on `pve` run as root through the existing access method, with Ben's per-step OK. They are B2 Step
    1, the `pvesm` calls, and `qm` calls.
- [ ] **Step 4: The outer maintenance lock.** It is required from B2 through B10, because lab tooling shares VM300
  with production deploys, which have OOM'd before.
  - Ben approves the window. Take the lock in the production root with owner `lab/storage-<date>`.
  - Before each heavy step (packer, terraform, `k3s.yml`, `storage.yml`, `helm`), confirm that no `deploy.yml` run is
    in progress, and record VM300's MemAvailable.
  - Also create the lab root `<lab>` with its own `runner-instance` file. Acquire a lab lock there for the lab
    playbooks.
  - Lab VMs are stopped between sessions:
    1. set `hold_fence`;
    2. stop 972 and 973, then 971, then 970.

    Start them in reverse order and clear the hold last.
    `lab-nfs` is a hard NFS 4.2 mount on pve: before stopping 970, run `pvesm set lab-nfs --disable 1` and
    `umount /mnt/pve/lab-nfs`; after 970 is back, `pvesm set lab-nfs --disable 0` (2026-11-16, B2 Step 3).
  - `<lab>` is on VM300's disk, which the Sunday vzdump uploads off-site. So disk images and restore copies never go
    there.

### Task B2: Lab bridge, lab NFS and lab images

- [ ] **Step 1: Bridge.** Run `proxmox-storage-bridge.yml -e proxmox_storage_bridge_name=vmbr9` twice. Expected:
  - the second run is idempotent;
  - `ip link show vmbr9` shows the UP admin flag;
  - NO-CARRIER is normal until a VM attaches.
- [ ] **Step 2: Images.**
  - Write `<lab>/lab.pkrvars.hcl` with `base_vm_id=974`, `k3s_vm_id=975`, `storage_vm_id=976` and
    `vm_name_prefix="lab"`.
  - Before each build, a guard checks that the var-file's IDs are 974–976 and that `qm status <id>` fails.
  - Run `packer build -only=<each> -var-file=<lab>/lab.pkrvars.hcl .` with **no `-force`**, in order base, k3s,
    storage. There is no manifest push and no release.
  - Expected:
    - `qm config 976` has no `ciuser` or `sshkeys`;
    - a throwaway clone of each template shows an empty-then-regenerated machine-id, `/var/lib/dbus/machine-id`
      linked to it, no builder user in `getent passwd`, no `/etc/sudoers.d/<builder>` or `90-cloud-init-users`, and
      `cloud-init status` reporting a fresh first boot;
    - on 976's clone, `dpkg -l gcc` reports not installed.
- [ ] **Step 3: Lab NFS.**
  1. Clone VM 970 from template 974.
  2. Install `nfs-kernel-server`, and export `/srv/lab` as `rw,no_root_squash,sync` to pve's vmbr0 address only.
  3. On pve, run `pvesm add nfs lab-nfs --server <970 addr> --export /srv/lab --content images --options vers=4.2`.

  Expected: `findmnt /mnt/pve/lab-nfs` shows `vers=4.2`.

  **Decision D1: qualify both (Ben, 2026-11-15); host path chosen (Ben, 2026-11-18, see ADR 0017).** The variant N
  text below records what the lab ran. pve's NFS client is the code path of the 10-23 and 11-15 oopses, so the lab
  also qualifies **variant N**:
  - VM 970 also exports `/srv/labn` to 971's vmbr0 address.
  - 971 mounts it itself (`vers=4.2,hard`), with a systemd mount ordered before `rtslib-fb-targetctl`.
  - 971 attaches `/srv/labn/regen-n.raw` (2 GiB) with `losetup --direct-io=on`, and that loop device carries VG
    `regen` for the variant N legs (`storage_vm_loop_disks: [{file: /srv/labn/regen-n.raw, vg: regen}]`).

  This needs `nfs-common` in the storage image and the mount and loop units in the role; that is Task A16. The
  reconciler knows only `retained` and `regen`, so the two `regen` placements run one after the other: the variant N
  legs first, then `regen` is recreated on the host-attached disk (the class is regenerable by definition, and this is
  lab data) and the ADR path is tested as written.

### Task B3: Lab storage VM

- [ ] **Step 1:** Run `pvesm alloc k3s-block 9970 vm-9970-disk-0.raw 8G --format raw` and
  `pvesm alloc lab-nfs 9970 vm-9970-disk-1.raw 4G --format raw`.
- [ ] **Step 2:** Run terraform `storage/` from the branch.
  - Use a local-backend override written only in `<lab>`, and `pve.env`.
  - Lab tfvars: VM 971, `lab-storage`, template 976, tags `["lab-storage"]`, `ssh_pub_keys = [<lab>/ssh/id_lab.pub]`,
    the static NICs, and `data_disks` virtio1 → `9970/vm-9970-disk-0.raw` on `k3s-block` and virtio2 →
    `9970/vm-9970-disk-1.raw` on `lab-nfs`.
  - Run `check_clone_source.py 976 && terraform apply`.
  - Expected:
    - VM 971 runs, and `qm config 971` shows both volids with `discard=on`;
    - `ip -br link show vmbr9` is UP, and `bridge link show master vmbr9` lists `tap971i1`;
    - `rtslib-fb-targetctl` is failed or inactive at this point. There are no VGs yet, and that is expected.
- [ ] **Step 3: VG bootstrap** (manual): `pvcreate`, `vgcreate retained /dev/vdb`, `vgcreate regen /dev/vdc`, then
  `vgchange --addtag hold_fence retained`.
- [ ] **Step 4: Write the lab files.**
  - `<lab>/inventory.yml`: hosts and groups only. It defines `storage: lab-storage`, `all_k3s`,
    `masters: lab-server` and `workers: lab-server, lab-agent`, with `ansible_host` set to the vmbr0 addresses.
  - `<lab>/vars.yml`:
    - `vip_address` (972's vmbr0 address);
    - `mgmt_iface: eth0` and `flannel_iface: eth1`;
    - `proxmox_csi_enabled: false` and `k3s_node_retirement_enabled: false`;
    - `storage_vm_api_url`;
    - `storage_vm_workers`, with names `lab-server` and `lab-agent` and their vmbr9 addresses;
    - `storage_vm_bridge_address: 10.99.9.10`;
    - `storage_vm_ssh_sources`: VM300's vmbr0 address plus the LAN CIDR;
    - `storage_vm_inventory_repo`, a bare repo in `<lab>`;
    - `storage_vm_maintenance_root: /maintenance/lab-storage`;
    - `storage_vm_timings` with `quarantine_seconds: 900`.

### Task B4: Lab k3s and democratic-csi

- [ ] **Step 1:** For 972 and 973, run `qm clone 975 <id> --full --name lab-server|lab-agent`, then:

  ```
  qm set <id> --tags lab-k3s --ciuser debian --sshkeys <lab>/ssh/id_lab.pub --nameserver 10.9.9.1 \
    --net0 virtio,bridge=vmbr0 --net1 virtio,bridge=vmbr1 --net2 virtio,bridge=vmbr9 \
    --ipconfig0 ip=<vmbr0>/24 --ipconfig1 ip=<vmbr1>/24,gw=10.9.8.1 --ipconfig2 ip=10.99.9.1{1,2}/24
  ```

  Then start both and re-run the tag audit.
- [ ] **Step 2: Run k3s.**
  1. Run `ansible-playbook -i <lab>/inventory.yml -e @<lab>/vars.yml k3s.yml --skip-tags argocd,kube-vip
     --list-tasks` from `<lab>/ansible`. Confirm that the lab guard is listed and that no `bootstrap_cluster` or
     `kube-vip` task is.
  2. Run it for real, without `-v`. The server issues its own token, which the playbook harvests; no
     `global_k3s_token` is passed.
  3. Write `<lab>/.kube/config` from the server's `k3s.yaml`, with the server set to the 972 address.

  Expected:
  - `labkube.sh get nodes -o name` shows exactly `node/lab-server` and `node/lab-agent`, both Ready;
  - each `initiatorname.iscsi` ends in its node name;
  - `/configz` shows `shutdownGracePeriod` `1m0s` (`1m30s` once the F14 fix is deployed, 2026-11-18);
  - kube-controller-manager has `--disable-force-detach-on-timeout=true`;
  - `config.yaml` has no `max-volume-attachments` label;
  - `flannel.1` uses the eth1 address, and no udp/8472 traffic shows on eth2.
- [ ] **Step 3:** Install democratic-csi through `labkube.sh helm install`, with the branch values and the pinned chart,
  then apply `manifests/`. Expected: the CSIDriver exists, the node DaemonSet runs on both nodes, and
  `storage-fencer-token` exists.
- [ ] **Step 4:** Run `storage.yml` twice. Expected:
  - run 1 starts `rtslib-fb-targetctl` (A4 rule) and leaves it active;
  - run 2 changes nothing;
  - `nftables` and `storage-fencer` are active;
  - `/etc/storage-fencer/token` is mode 0600;
  - the fencer logs an API success.
- [ ] **Step 5: Deploy the test volumes.** Commit three inventory entries to the lab repo:
  - `lab-sqlite` (`new`, `retained`, 1Gi);
  - `lab-raw` (`migrated`, `retained`, 1Gi);
  - `lab-regen` (`new`, `regenerable`, 1Gi).

  Run `storage.yml`, then render and apply the volumes:

  ```
  helm template lab infrastructure/base-configs -f templates/globals.yaml \
    --set global.network.storagePortal=10.99.9.10:3260 --show-only templates/retained-volumes.yaml \
    | labkube.sh apply -f -
  ```

  Deploy a synthetic SQLite writer (WAL, `synchronous=FULL`, numbered rows, acknowledged numbers logged) on
  `lab-sqlite`, behind its marker guard. Expected: the writer is Running on `lab-agent`.

### Task B5: Checks 4, 5, 7 and 12 (no outage)

- [x] **Check 4: missing and blank devices.**
  - **Missing LV:** point a PV at `lab-missing`. Expected: ContainerCreating, and no `mkfs` anywhere.
  - **Blank migrated LV:** bind `lab-raw` with a migrated-style guard. Expected: the guard fails the init container,
    and `dumpe2fs -h` shows MMP on the filesystem the driver made. Record this as the documented residual risk.
  - **Ledgered LV missing at boot:**
    1. scale `lab-regen` to 0;
    2. run `lvrename regen lab-regen lab-regen-hidden`;
    3. reboot only VM 971, without running `storage.yml` in between.

    Expected:
    - `rtslib-fb-targetctl` is failed, and its `boot-check` line names `lab-regen`;
    - `retained` targets serve, and the writer continues after the reconnect.

    Undo the rename and run `storage.yml`.
  - **VG missing:**
    1. scale `lab-regen` to 0 and confirm no session exists for its IQN;
    2. under the lab lock, delete its target and backstore and save;
    3. check that `lvs -o lv_attr` shows the LV is not open;
    4. run `vgchange -an regen`, then `qm set 971 --delete virtio2`.

    Expected:
    - `storage.yml` refuses every `regen` entry and fails;
    - a reboot of 971 with the disk still detached leaves the `retained` targets serving, with the unit failed.

    Then re-attach the same volid and run `storage.yml`.
  - **Populated LV with no udev fs data:**
    1. scale the writer to 0;
    2. write `/etc/udev/rules.d/59-lab-noblkid.rules` on the agent, setting
       `ENV{UDEV_DISABLE_PERSISTENT_STORAGE_BLKID_FLAG}="1"` for `ENV{ID_PATH}=="*iscsi-<lab-sqlite iqn>*"`;
    3. run `udevadm control --reload`;
    4. scale the writer to 1.

    First confirm that the by-path link exists and that `udevadm info` shows no `ID_FS_TYPE`. Expected: no `mkfs` in the
    driver log, and the rows are intact. Remove the rule afterwards.
- [x] **Check 5: ledger and deletion.**
  - **New and lost:** a new entry is created. An LV renamed away while ledgered is refused.
  - **Orphan:** an `lvcreate` outside the ledger is refused.
  - **Crash mid-create:** with `pause_after: ["create:lvcreate"]`, SIGKILL the paused process. The retry refuses
    (`crashed-create`).
  - **Tombstone:** a tombstoned id is refused.
  - **Old SHA:**
    1. commit A adds `lab-later`;
    2. commit B removes it;
    3. move the branch back to A only in a clone, then run with `storage_vm_inventory_branch` pointing at the real
       branch.

    Expected: the run logs B's SHA and marks `lab-later` pending. A 40-hex `storage_vm_inventory_branch` fails before
    any lock.
  - **Removal while running:** removing `lab-sqlite` while its writer runs keeps the target, sets `pending-delete`, and
    the expiry refuses (VolumeAttachment present). Re-adding it within 15 minutes clears the tag.
  - **Copy pair:**
    1. create a Block-mode PV/PVC pair `lab-copy-src` with `volumeHandle: lab-regen` and a `sleep` pod using it;
    2. remove `lab-regen` from the inventory;
    3. wait past the quarantine.

    Expected: the expiry refuses (VolumeAttachment present). Delete the pod and pair afterwards.
  - **Login without a pod:** on the agent, run `iscsiadm -m node -T <iqn> -p 10.99.9.10 -o new` and `-l` for a
    removed id, with no pod and no VolumeAttachment. Expected: the expiry refuses (session). Log out afterwards.
  - **CI rejects a class change:** run the apps check against a fixture.
  - **Expiry deletes:** after 900 s with no pod, no VolumeAttachment and no session, the expiry deletes the PVC, PV
    and LV, and records the tombstone.
  - **Hold:** `hold_create` blocks every create.
  - **Lock:** `storage-expiry.yml` with the lab lock released fails at verify, and nothing is deleted.
- [x] **Check 7: online growth.**
  - Raise `lab-sqlite` to 2Gi and run `storage.yml`. Expected: `df` in the pod shows about 2 GiB without a restart.
  - Repeat to 3Gi with `pause_after: ["grow:lvextend"]`, SIGKILL, then run `storage.yml` again. Expected: the retry
    grows the filesystem.
- [x] **Check 12: network, metrics and reclaim.**
  - **Unlisted bridge source:**
    1. on 973, `ip addr add 10.99.9.50/24 dev eth2`;
    2. `nc -s 10.99.9.50 -w3 -zv 10.99.9.10 3260` fails;
    3. `nc -s 10.99.9.12 …` succeeds;
    4. remove the address.
  - **LAN sources:** from pve and from 973's vmbr0 and vmbr1 addresses, `nc -w3 -zv <971 vmbr0 addr> 3260` and the same
    for `9100` fail.
  - **SSH:** SSH from the tooling container works after `systemctl reload nftables`.
  - **Metrics:** `curl -s 10.99.9.10:9100/metrics`, run from 973 (source .12), shows `storage_pending_delete` after a
    removal.
  - **Unstage isolation:** unstaging one of two volumes on 973 leaves the other writer running.
  - **Reclaim:** after an expiry, `du` of `vm-9970-disk-0.raw` on the `k3s-block` mount falls.

### Task B6: Check 6, hangs and fencing

Before each case, put the writer on 973 and confirm that its VolumeAttachment is on 973 and its rows are intact. After
each case, put things back:
1. if 973 kept its bootID, reboot it (`qm reset`);
2. wait for the automatic unfence;
3. cordon 972, delete the writer pod so it lands on 973, then uncordon 972.

- [x] **Step 1:** Remove `hold_fence`. In the lab there is no Proxmox CSI VolumeAttachment. Confirm clean evaluations in
  the fencer log.
- [x] **Step 2: Fencer stopped.** `qm suspend 973` for 10 minutes. Expected: the VolumeAttachment stays on 973, and the
  writer is not recreated. Then resume it.
- [x] **Step 3: Four hang cases, with the fencer running:**
  1. `qm suspend 973`;
  2. `kill -STOP` of 973's QEMU pid (`/var/run/qemu-server/973.pid`);
  3. `echo freeze > /sys/power/state` inside 973;
  4. `qm set 973 --net0 <existing net0 string>,link_down=1`.

  Each time, expect:
  - the fencer log shows the proof (no ACL, address in set, no socket) before the taint;
  - the writer is Running on 972 within about 6 minutes;
  - every acknowledged row is present.
- [x] **Step 4: After resume.** Expected:
  - 973's kernel log shows I/O errors and ext4 remount-ro;
  - `dumpe2fs -h` on 972's mount shows the MMP sequence moving;
  - `e2fsck -fn` on an `lvcreate -s` snapshot is clean.

  Remove the snapshot.
- [x] **Step 5: In-flight ACL removal.**
  1. With `fio` writing on 973, run `storage-fencer prove lab-agent`. Expected: exit 1, with the ACL present, the
     address not in the set, and the established socket listed.
  2. Run `storage-fencer fence lab-agent`. Expected: `delete_acl` returns within 30 s, the proof passes, and the writes
     acknowledged before the fence are on 972 after the move.
- [x] **Step 6: Crash convergence.** For each `fence:1`…`fence:5` and `unfence:1`…`unfence:4`:
  1. set `pause_after` to that step;
  2. trigger it;
  3. SIGKILL the paused fencer;
  4. clear `pause_after`;
  5. restart it.

  Once more at `fence:3`, reboot 971 instead of killing. Expected: each converges to a finished operation, with one
  taint at most.
- [x] **Step 7: Persistence.** During a fence, expect the address to stay in the set and the ACLs to stay missing
  across each of:
  - `systemctl reload nftables`;
  - a manual `systemctl restart nftables`;
  - a reconcile that changes the nftables template;
  - a 971 reboot.
- [x] **Step 8: BootID rules.**
  - A worker that hangs, is fenced, and is rebooted after the tag is settled is unfenced with no manual step.
  - A resume with the same bootID stays fenced.
  - A `vmstate` snapshot taken before the fence and rolled back after it stays fenced. Delete the snapshot afterwards.
  - A slow reboot is fenced, its tag settles on the new bootID, and it stays fenced when it turns `Ready`; one more
    reboot unfences it. Make one with a oneshot unit ordered before `k3s-agent` that sleeps 360 s, then remove the unit.
  - With the fencer stopped for one loop, a worker reboots, turns `Ready`, mounts a retained volume and is then held
    NotReady past 5 minutes: it is fenced, and it stays fenced when it turns `Ready` again on the same boot.
  - Restart the fencer while a worker is fenced: the tag goes to `unknown` and settles again on the next loop.
- [x] **Step 9: Refusals.** In each case nothing is fenced, and the expected metrics appear:
  - both nodes NotReady (stop k3s on 972, then pause 973);
  - the API unreachable (drop 6443 on 972);
  - the token Secret deleted;
  - the token rotated;
  - `hold_fence` set;
  - a dummy VolumeAttachment object on 973 with `spec.attacher: csi.proxmox.sinextra.dev`.

  For the auth cases and a stale-textfile case (fencer stopped for 11 minutes):
  1. save `curl 10.99.9.10:9100/metrics` captures before and after the 10-minute mark;
  2. turn them into promtool `input_series`;
  3. run them against the A15 rules.

  Expected: `StorageFencerBlind` fires.
- [x] **Step 10: Manual fence with the fencer stopped.** Stop the fencer, then run `storage-fencer fence lab-agent`. Expected:
  - the tag stays `unknown`, and a resumed 973 stays fenced;
  - with the fencer running again, the tag is settled on the next loop;
  - `unfence lab-agent` without `--confirm-stopped` exits 1;
  - with it, after `qm status 973 --verbose` shows stopped, the unfence completes.

### Task B7: Checks 2 and 3, rebuilds

- [x] **Check 2: full k3s rebuild.**
  1. Destroy 972 and 973 and re-clone them as in B4 Step 1.
  2. Re-run `k3s.yml` (the new server issues its own token), democratic-csi, and the rendered volumes.
  3. Run `storage.yml`.

  Expected:
  - `/etc/storage-fencer/{token,ca.crt}` checksums change (never print them);
  - the fencer restarts, and its API-success metric advances;
  - every PV binds;
  - the writer is Running with every acknowledged row;
  - the IQNs are unchanged;
  - no `mkfs` runs.
- [x] **Check 3: storage VM rebuild.**
  1. In the lab copy, set `prevent_destroy = false`, bump `generation`, run `check_clone_source.py 976 && terraform
     apply`, then run `storage.yml`. Expected:
     - the same volids and LV UUIDs;
     - every target re-exported;
     - the writer reconnects;
     - fences and ledgers intact.
  2. Run `qm resize 971 virtio1 +1G` by hand. Expected: `terraform plan` shows the size diff, and an apply neither
     resizes nor moves the disk. Then `pvresize`.
  3. Bump `generation` again with `storage_template_vmid = 9979` (unused). Expected: `check_clone_source.py 9979` exits
     1, no apply runs, and `qm status 971` is still running.
  4. Restore `prevent_destroy` and the template ID.

### Task B8: Checks 8, 9 and 11

- [x] **Check 8: NFS stall and export withdrawal**, on the `regen` disk, which is on `lab-nfs`:
  - **Stall:** with a `lab-regen` writer running, run `systemctl stop nfs-kernel-server` on VM 970 for 3 minutes, then
    start it again.
  - **Withdrawal:** run `exportfs -u <pve>:/srv/lab` for 3 minutes, then `exportfs -r`.

  Each host-path leg stalls pve's own NFS client. So each is attended, runs only with Ben's OK at that step, stays
  outside the backup windows, and is preceded by an empty-pstore check. Under variant N, run the same two legs against
  `/srv/labn` first, while `regen` sits on the loop device; they stall only 971's client.

  Expected for each:
  - the writer blocks or gets I/O errors, and never reports a lost acknowledged row;
  - `retained` I/O continues throughout;
  - while the stall lasts, `vgs retained`, `storage-fencer prove lab-server` and a reconcile each finish within 30 s. A
    block here is a design finding for "Hang policy";
  - afterwards, `e2fsck -fn` on a snapshot is clean, a manual pod restart restages, and `journalctl -k` on pve is clean.

  No rule ever targets 10.9.8.30 or the `k3s-block` mount.
- [x] **Check 9: crash and latency.**
  - **Crash:** `kill -9` the writer mid-transaction 20 times. Expected: `PRAGMA integrity_check` returns `ok` each time.
  - **Hard stop:** `qm stop 971` mid-write. After it starts again, `qm stop 973` mid-write. Expected after each:
    `PRAGMA integrity_check` returns `ok`, `e2fsck -fn` on a snapshot is clean, and every acknowledged row is present.
  - **Latency:** run `fio --rw=randwrite --bs=4k --fsync=1 --size=256m --runtime=60` and the SQLite fsync loop on
    `lab-sqlite`. Run the same on the Proxmox CSI path:
    1. `pvesm alloc k3s-block 9970 vm-9970-disk-2.raw 1G --format raw`;
    2. hot-plug it into 973 as `scsi1`;
    3. run the tests;
    4. detach and `pvesm free` it.
  - Record p50, p99 and IOPS. Ben sets any gate.
- [x] **Check 11: graceful shutdown.** (First run FAIL on "no fence", F14/F15; re-tested with the fix and PASS
  2026-11-18, report "Check 11 re-test". The re-test used `qm shutdown 973` and added the legs below.)
  1. Before the shutdown, confirm `/etc/systemd/logind.conf.d/99-kubelet.conf` (InhibitDelayMaxUSec at least 90 s) and
     `/configz` `shutdownGracePeriod` `1m30s` and `shutdownGracePeriodCriticalPods` `40s` on 973.
  2. Note T0, then run `systemctl poweroff` on 973 with the writer running.
  3. Before T0+300 s, expect:
     - the writer Running on 972 with every row;
     - 973's VolumeAttachment gone;
     - no `fenced:` tag.
  4. Run `qm start 973` before T0+240 s. Expected: no `fenced:` tag or taint ever appears, and 973 is Ready.
  5. `journalctl -b -1` on 973 shows the pod's SIGTERM before the iSCSI logout.
  6. Expectation (F14): no fence; both VolumeAttachments are released before the fence window (lab: 60 s
     NotReady), through NodeUnstage, not the taint.
  7. F21: restart the node DaemonSet while the volumes are staged, sweep `/proc/*/mountinfo` on the worker (no
     private globalmount copy in any container), then repeat 2-6. In the shutdown journal, each ext4
     `unmounting filesystem` comes before that disk's `Synchronizing SCSI cache`, with no I/O or JBD2 errors.
  8. Drained leg (F15): with nothing staged, the worker stops in under 40 s, and the node plugin's containers exit
     `csi-driver` first, then the sidecars.

### Task B9: Check 10, restore drills

- [x] **Step 1: Single-app restore.**
  All B9 copies go to `/usbbk/restore/lab-<date>/` on pve, never under `<lab>`, `/root` or `/etc`. Before copying,
  take the backup lock and check that the space is free. Every session ends before 04:25.
  1. With 971 stopped, `cp --sparse=always` `vm-9970-disk-0.raw` into that directory.
  2. On pve, run `losetup` read-write on the copy, then `vgimportclone -n restore_<date>`, then `vgchange -ay`. Only one
     copy is attached at a time, so pve's LVM never sees two VGs named `retained`.
  3. Mount `lab-sqlite` `ro` and copy the DB.
  4. Unwind (`umount`, `vgchange -an`, `losetup -d`), then delete the copy.

  Expected: the copied rows match the source at copy time.

  The `zfs clone` from a `usbbk` snapshot leg is **optional**, and only with Ben's explicit go-ahead and these limits:
  - after the next replication has FINISHED with the lab image in it;
  - outside replication windows;
  - only if `zfs get -H keystatus usbbk/tn/k3s-block` is `available`. Never run `load-key`, and never read a key
    file;
  - a lab-named clone, destroyed in the same session.

  Otherwise that leg is recorded as not run.
- [x] **Step 2: Whole-disk restore while fenced.**
  1. With 971 stopped and nothing fenced, copy disk-0 to `/usbbk/restore/lab-<date>/T0.raw`. Offline, add a dummy
     `fenced:lab-server:stale` tag to the copy (`losetup` + `vgchange --addtag`, no activation). Record `lvs retained`
     and the sha256.
  2. Boot 971, add `lab-later`, and run `storage.yml`.
  3. Fence 973. Record the `fenced:lab-agent:<bootID>` tag and the taint.
  4. Run ADR runbook steps 1–6, restoring `T0.raw` over disk-0 in step 2, with Ben's OK at that step:
     - 971 is stopped;
     - first keep the current disk-0 as a rollback copy, which is deleted only after verification;
     - `cp --sparse=always`, then compare sha256, as in ansible runbook :168-189;
     - never a ZFS rollback.

  Expected:
  - after step 3: the live tag is re-added and `stale` is deleted;
  - after boot: 973 is still fenced;
  - after step 5: `storage.yml` refuses `lab-later` (`lv-missing`), lists it, and creates nothing;
  - clearing the holds happens only after it is resolved.
- [ ] **Step 3: Off-site restore. Not run (Ben, 2026-11-16):** the lab image is excluded from restic (B1 Step 3).
  Kept as written in case the exclude is lifted. The off-site gate was met on 2026-11-13 (ansible runbook :375-377).
  - **Preconditions:** Ben's OK, the backup lock held, and a green 04:30 run whose replica snapshot contains
    `vm-9970-disk-0.raw`.
  - **Restore,** timed, through the runbook's `R()` wrapper (:131-145); the executor never reads `restic.pass`:
    `R restore <snapshot id> --target /usbbk/restore/lab-<date> --sparse --include
    /srv/backup-src/k3s-block/images/9970/vm-9970-disk-0.raw`.
  - **Expected:**
    - the sha256 equals the same file in the replica snapshot that run read;
    - `vgimportclone`, an `ro` mount, and `PRAGMA integrity_check` returns `ok`.
  - Unwind and delete the copy. `journalctl -k` is clean.

### Task B10: Check 1, cold boot (production outage; Ben schedules it)

- [x] **Step 1: Settle the ADR wording with Ben.** The ADR said "TrueNAS starting last", while its Boot order section
  starts TrueNAS first. Ben (2026-11-17): TrueNAS is ordered first, but its NFS is the last thing to come up; Check 1
  passes on Step 3 (production order). Step 4 (late NFS) is a recorded design input. The ADR now says so.
- [x] **Step 2: Lab startup.** Run `qm set 970 --onboot 1 --startup order=1,up=60`, `qm set 971 --onboot 1 --startup
  order=2,up=<measured>`, and `qm set 972|973 --onboot 1`. 970 holds TrueNAS's slot because 971's `regen` disk is on
  its `lab-nfs` storage: with 970 after 971, pve would refuse to start 971 ("not online") and Step 3 would become
  Step 4. `startup` needs `Sys.Modify` on `/`, so it runs as root on pve, not with the lab token. Measure `up=` by
  rebooting 971 alone: it is the time until `rtslib-fb-targetctl` is active and `iscsiadm -m discovery -t st -p
  10.99.9.10` from 973 lists the targets. Done 2026-11-17: about 11.4 s, set `up=30`.
- [x] **Step 2b: Pick the slot.** The reboot happens outside the backup windows. It does not span an :00, because the
  hourly `health` run fails until `usbbk-import` (which runs after `pve-guests`) finishes. It does not span a :30 of
  03/09/15/21, because a missed TrueNAS snapshot can push the replica past 8 h.
  - **If B10 shares Ben's pve investigation window,** release the lab's outer lock before that runbook's P8. Stop the
    lab VMs with `hold_fence` set. Run Step 3 only on the clean return boot, never after stress or memtest.
  - **Afterwards:** `systemctl status usbbk-import`, empty pstore, and one manual `health` pass.
- [x] **Step 3: Host reboot, production order.** Expected:
  - VM 100 starts first, 971 next;
  - 971 starts with no manual `qm start`, and the pve-guests journal has no "not online" line for 971–973;
  - `rtslib-fb-targetctl` is active before the first reconcile;
  - the writer recovers with every row;
  - at shutdown, 972 and 973 stop before 971.
- [x] **Step 4: Late NFS for 971.** In the same window, after Step 3:
  1. `qm shutdown 970 971 972 973`;
  2. start 971 before 970 (or with `lab-nfs` offline);
  3. record what happens.

  A VM whose storage is offline is already known to refuse to start: that is what stopped VMs 201 and 202 on 11-05 and
  11-07. So this step measures whether `order=2` after VM 100's `up=180` is enough, including after a cold boot. If it
  is not, bring that to Ben before foundation. Under variant N, also start 971 with its in-guest mount unreachable.
  Expected: the `.mount` unit retries until its timeout, then the loop unit and `rtslib-fb-targetctl` fail by
  `Requires=`, so `retained` targets on the virtio disk are not restored either (unlike the host-attached path, where a
  missing `regen` is tolerated). Record how long the wait is and whether a later `systemctl start
  rtslib-fb-targetctl` after 970 returns restores everything. This is a design input to D1, not a failure. Also check
  `vgs regen` after boot: if the loop PV is missing although the unit is active, a udev race hit `vgchange` (fix:
  `ExecStartPost=/bin/udevadm settle` in the loop unit).
- [x] **Step 5:** If Ben does not schedule the reboot, record check 1 as not run. Foundation does not start until it
  passes. Done 2026-11-19: the reboot ran 2026-11-17 (Step 3 PASS). Ben closed Check 1 on that run, with no
  re-run on the final code; see the report's B10 Step 5.

### Task B11: Results and cleanup

- [x] **Step 1: Write the results report.** It covers:
  - each check's result and evidence;
  - the measured `up=`;
  - the latency numbers;
  - lab-storage's peak RSS and CPU;
  - the NFS findings, for the host path and for variant N (both ran);
  - variant N leftovers: its units on 971 were removed by hand on 2026-11-17; delete `/srv/labn/regen-n.raw` and the
    `/srv/labn` export on 970;
  - the limits: no server fence, the ZFS-clone leg if skipped, the simulated hang methods, and that the lab cannot
    measure the oops rate;
  - every ADR change the lab forces. These go back to Ben before production.
- [ ] **Step 2: Cleanup, with Ben's OK.**
  1. Run `for id in 970 971 972 973 974 975 976; do qm stop $id; qm destroy $id --purge; done`, then confirm with
     `qm list` that 970–979 are gone.
  2. `pvesm free` every 9970 volid on `k3s-block` and `lab-nfs`, confirm that the `9970/` dir is gone, then
     `pvesm remove lab-nfs`. The freed 9970 images stay in TrueNAS snapshots for 1 week, in the replica for 2 weeks, and
     in restic `daily` for up to 12 months. That is expected; do not rewrite the repository. With the B1 exclude, restic
     should hold none; check with `R find --path` scoped to `images/9970`.
  3. Run `proxmox-storage-bridge.yml -e proxmox_storage_bridge_name=vmbr9 -e proxmox_storage_bridge_state=absent`.
  4. Remove the lab user, token and pool; the tooling container; and `<lab>`, after the evidence is copied out.
  5. Release the outer lock.
  6. An ansible PR reverts the B1 Step 3 exclude (`/srv/backup-src/k3s-block/images/9970`) once the 9970 volids are
     freed.
- [ ] **Step 3: Commit the report** on the apps plan branch: `docs(storage): record the storage VM lab results`. List the
  four repos' branches for Ben.

## Not in this plan (next plans)

- **Foundation:**
  - the production bridge PR;
  - the first packer build in the new layout (a full rebuild);
  - terraform's matrix, drift, `--chdir`, wiring `check_clone_source.py` into `apply.yml`, and the manifest selection
    by name;
  - the `storage.yml` and expiry workflows, with the lock-held pre-check, the stale-lock alert, and no SHA taken from
    the dispatch payload;
  - the apps `storage-changed` dispatch;
  - the worker NICs, one per PR;
  - the bridge role's own workflow, and `deploy.yml` `paths-ignore` entries for its role, playbook, workflow and test;
  - `guest_startup.yml`: add the storage VM key only after the VM exists, because the role reads every listed VM's
    config;
  - the backup exclude. Add one `regen` path **next to** the five `vm-9999` excludes, which go at Retirement. Update
    their test (`test_proxmox_backup.py:274-280`), runbook :29 and :327-330, and the `.github` "Backup inputs"
    contract row and `profile/README.md`. Ship docs-only parts with `[skip ci]`;
  - a dump rule that alarms on a missing or stale `retained` image, added at the first cutover, not before: the rule
    checks mtime, so an idle image would fail it;
  - the node-retirement vars move.
- **Per-volume migration plan:** cutovers. The off-site gate was met on 2026-11-13. At migration start, re-check that
  `pve-backup` has been green for 7 days and pstore is empty.
- **Runbooks:** restore, hang fencing and growth, with commands taken from this lab's evidence.
