# Redis and Immich retained CSI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task after the user reviews this plan and selects the execution method. Steps use checkbox (`- [ ]`) syntax for tracking. Native inline execution with one independent final review is recommended; the user approved Native preparation on 18 October 2026.

**Goal:** Prepare and qualify complete Redis queue preservation with AOF on retained CSI, followed by a physical move of Immich's dedicated PostgreSQL cluster.

**Architecture:** Reuse the installed native maintenance runtime, existing scoped Argo holds, static retained Proxmox CSI bindings and verified VM retirement. Complete Redis before starting the Immich operation. Prepare inactive declarations and executable recovery/rollout commands first; production requires a later concrete execution approval.

**Tech Stack:** Redis8.10.2/chart28.3.1, PostgreSQL17.6/VectorChord0.4.3/pgvector0.8.1, Immich3.2.2, existing Python/PyYAML/Paramiko, Bash, native Redis/PostgreSQL binaries, Helm, Docker, Kubernetes/ArgoCD and unmodified Proxmox CSI.

**Spec:** [Approved Redis and Immich design](../specs/2026-10-18-redis-immich-retained-csi-design.md).

## Global Constraints

- Redis first, then Immich PostgreSQL; no shared-PostgreSQL/enrollment, Paperless index or Calibre migration in this plan.
- Preserve all records, pending jobs, credentials, native expiry semantics, identities, endpoints and original assets. Never initialize an empty target as a fallback.
- Redis2GiB: `databases/redis-data-block`, image `k3s-block:9999/vm-9999-redis-data.raw`; identity marker `.homelab-redis-data` containing `homelab/redis/data/v1\n`.
- Immich10GiB: `media/immich-postgres-block`, image `k3s-block:9999/vm-9999-immich-postgres.raw`; PG17 system identifier `7614955115223928876`.
- Static ext4/RWOP/Retain bindings with bidirectional prebinding, external owner9999, cache-none, prune/delete protection and indefinite not-ready/unreachable NoExecute holds; no driver fork, dynamic fallback or Velero.
- Keep NAS quota288GiB, dataset GUID13918781591004512447, full remaining image growth,512MiB staging and8GiB spare against both dataset availability and physical pool free. Keep the historical Jellyfin partial.
- Preserve the exact Redis/exporter and Immich image digests in the spec. Pin the current mutable Redis image references without upgrading either binary; no credential rotation or new controller.
- Redis target AOF enabled with `appendfsync everysec`; scheduled-RDB policy unchanged. Every-second fsync keeps its normal power-failure window, not a zero-loss guarantee.
- Immich photos/videos and ML cache remain on NFS at their current application paths. Preserve UID999 and actual POSIX metadata; no blanket chown, initdb, pg_upgrade or pg_resetwal.
- Real records, RDB/AOF, database copies, verifiers and credentials stay private outside Git. VM300 plus this computer retain encrypted recovery; keys are separate. Infrastructure credentials never enter application fixtures.
- Reuse fresh owner/nonce, immutable original clocks, recorded intents and known child outcomes; never replay a completed or uncertain mutation. Record authority before first target writes; never automatically reopen stale source afterward.
- Tasks1–5 prepare the operation. Task6 is gated by a separate execution proposal, including lab/data transfers, outage scope, exact time limits and merge authority.

## Review Focus

1. A running Redis with AOF off and historical AOF files must never be stopped/restarted before current-memory recovery and the AOF transition pass (Tasks1/4: `test_stale_disk_is_not_memory_recovery`, `test_restart_blocked_before_current_memory_restore`).
2. Binary keys/payloads, TTL expiry, stream pending state and a valid zero-byte AOF increment must survive; missing files, unknown types and unexplained disappearance must fail closed (Tasks1/3: checkpoint and native AOF fixtures).
3. PG control CRC warnings with exit0, wrong physical identity, standby signals and stale PID files must not turn a rebuild into empty initialization or unfenced cleanup (Task2: exact-image native guard/recovery fixtures).
4. Idle Redis consumers and inherited chart behavior must not escape the hold, create a dynamic claim, rewrite ownership or silently lose durability (Tasks3/4: render comparisons, consumer inventory and recurrence tests).
5. A timeout/lost reply, stale Argo queue or a failure after target authority must preserve current writes, original clocks and exact resource generations (Task4: native failure/reconciliation fixtures).

## File Map

Create `scripts/redis-immich-retained/` with only the two app-specific adapters:

- `redis_checkpoint.py`: private binary-safe native key/type/payload/expiry snapshots and comparison; no production writes.
- `postgres_checkpoint.py`: native PG17 data/schema/sequence/role/extension proof through `psql`, `pg_dump` and `pg_dumpall`; no database conversion.
- `redis-guard.sh`, `postgres-guard.sh`: read-only retained-state checks before stock startup.
- `fixtures.py`: exact-image disposable synthetic recovery and fault scenarios, isolated from production.
- `production/{redis-bindings.yaml,redis-values.yaml,redis-guard-configmap.yaml,redis-source-hold.yaml,redis-prometheus-rules.yaml,immich-postgres-bindings.yaml,immich-values.yaml,immich-guard-configmap.yaml,immich-source-hold.yaml}`: inactive reviewed desired fragments.
- `prometheus-tests.yaml`, `check.sh`, `README.md`: alert fixtures, exact layered rendering/validation and preparation/activation boundaries.

Create `scripts/test-redis-immich-state.py`, `scripts/test-redis-immich-native.py`
and `scripts/test-redis-immich-manifests.py`. Add only their relevant CI steps to
`.github/workflows/validate-and-diff.yml` after the tests exist.

Keep operational commands/private receipts in ignored
`.superpowers/sdd/2026-10-18-redis-immich-retained-csi/native/`:
`redis.py`, `immich.py`, `lifecycle.py`, `test_protocol.py` and the established transport/packet
adapters. Reference previous operations as code only; never reuse their ownership,
authorization, receipts, data, clocks or execution state. Do not build a generic
migration framework or change the installed Ansible maintenance runtime.

Only separately approved activation changes may touch
`infrastructure/controllers/databases/redis/{values.yaml,manifests/}`,
`services/media/immich/{values.yaml,manifests/}`, and
`infrastructure/base-configs/templates/redis-immich-block-storage/`.
The runbooks are `docs/runbooks/redis-storage.md` and
`docs/runbooks/immich-storage.md`; publish a sanitized preparation/completion report
at each corresponding evidence boundary.

### Task 1: Redis current-memory proof, guard and exact-image fixture

**Files:** `redis_checkpoint.py`, `redis-guard.sh`, `fixtures.py` and the state/native tests from the File Map.
**Interfaces:** `capture(client, captured_at_ms: int) -> dict` and `compare(expected: dict, actual: dict, now_ms: int) -> dict` in `redis_checkpoint.py`. Checkpoints have `version`, `captured_at_ms` and `databases` (integer DB index to byte-key/typed-value records); comparison returns `preserved`/`expired` counts or raises `ValueError`. `fixtures.py --app redis --receipt PATH` produces a metadata-only result and exact owned-resource cleanup proof. `redis-guard.sh` consumes read-only `/data` plus `/tmp` scratch and returns0 only for accepted native retained state.

- [x] **Step1: Write failing checkpoint tests.** Cover binary key/value bytes, duplicate SCAN results, string/list/set/hash/zset/stream values, stream group offsets/pending ownership and absolute expiry. Missing unexpired keys or changed payload/type/expiry fail; only deadline-explained expiry passes. Unknown module types or unsupported hash-field expiry refuse qualification instead of being dropped.

```python
def test_only_deadline_explains_absence(self):
    before = {'version': 1, 'captured_at_ms': 1000, 'databases': {
        0: {b'\xff\x00job': {'type': 'string', 'value': b'\x00payload', 'expires_at_ms': 5000}}}}
    missing = {'version': 1, 'captured_at_ms': 4999, 'databases': {0: {}}}
    with self.assertRaises(ValueError):
        state.compare(before, missing, now_ms=4999)
    self.assertEqual(state.compare(before, missing, now_ms=5001)['expired'], 1)
    changed = copy.deepcopy(before)
    changed['databases'][0][b'\xff\x00job']['value'] = b'changed'
    with self.assertRaises(ValueError):
        state.compare(before, changed, now_ms=4999)
```

- [x] **Step2: Run RED**, `python3 scripts/test-redis-immich-state.py`; confirm the new tests fail for missing/unimplemented behavior.
- [x] **Step3: Implement the minimal native adapter.** Use the existing `redis`5.2.1 client in the exact pinned Paperless3.1.3 image as an isolated Python-only helper, with byte responses and synthetic fixture credentials; do not run Paperless's entrypoint or invent a RESP parser. Private checkpoint persistence uses lossless base64 for byte values and retains native structure/order/deadlines. Use native source TIME and verified clocks; uncertain deadline ordering fails qualification rather than explaining a disappearance. Public output contains counts/hashes only. A supposedly frozen source changing outside native expiry fails the capture gate.
- [x] **Step4: Add native RED fixtures**, including `test_stale_disk_is_not_memory_recovery`, then implement them using the pinned Redis image and `/opt/bitnami/redis/bin/{redis-cli,redis-check-rdb,redis-check-aof}`. Start a synthetic Redis with AOF disabled and intentionally stale disk files; produce a current-memory native RDB, independently restore it, compare full checkpoint, enable source AOF, await successful rewrite, cleanly stop/copy/start/recreate and compare again. Include synthetic Celery/BullMQ pending/in-flight recovery through the corresponding pinned app clients, without production services or notifications.
- [x] **Step5: Implement the read-only guard and negative fixtures.** Require the exact marker, native manifest/referenced regular files, no symlink/path escape and successful nonrepair native checks. A valid empty dataset/zero-byte incremental file is accepted; empty/missing/wrong media, corrupt base data or manifest is refused. Qualify abrupt termination and native tail recovery explicitly; never add `--fix`, silent truncation or a lost-job exception. If stock recovery conflicts with the rebuild contract, stop for a decision.
- [x] **Step6: Run GREEN**, state tests plus `python3 scripts/test-redis-immich-native.py --app redis`; require byte-identical guard input before/after, complete restored native state, all expected refusals and exact fixture cleanup. Commit the Redis adapter/guard/fixture only after those checks pass.

### Task 2: Immich PG17 identity guard and independent recovery proof

**Files:** `postgres_checkpoint.py`, `postgres-guard.sh`, PG scenarios in `fixtures.py` and the state/native tests.
**Interfaces:** `export(connection_file: Path, destination: Path) -> dict` and `compare(expected: dict, actual: dict) -> dict` in `postgres_checkpoint.py`; `fixtures.py --app immich --receipt PATH` produces the same metadata-only result/cleanup schema as Task1. Its test entry point `run_postgres_case(case: str) -> dict` reports `guard_refused`, `guard_read_only` and `stock_recovery_qualified` for named synthetic cases. `postgres-guard.sh` consumes read-only `/data/pgdata`, `/tmp` scratch and `EXPECTED_SYSTEM_IDENTIFIER`.

- [ ] **Step1: Write/run RED** for all table/column content, duplicates, binary/non-ASCII values, vector values, schema/extension versions, migration rows, sequence floors and roles/verifiers. Native session output must be lossless; do not reuse SQLite-to-PostgreSQL casts or exemptions from previous migrations.
- [ ] **Step2: Implement native checkpoint export/comparison** using the exact PG17 `psql`, `/usr/bin/pg_dump` and `/usr/bin/pg_dumpall`. Keep records and verifiers private, output only sanitized proofs and use consistent read-only source transactions after app writers quiesce. Validate full schemas/data, not just counts or readiness.
- [ ] **Step3: Write/run native guard RED cases.** Adapt the small existing `scripts/postgres-retained-startup/guard.sh` without changing shared PG18 behavior. Pin PG17, `/data/pgdata`, `/usr/lib/postgresql/17/bin/pg_controldata` and expected ID`7614955115223928876` for production; synthetic fixtures supply their independently recorded IDs.

```python
def test_crc_warning_and_stale_pid_contract(self):
    for case in ('crc-warning-exit-zero', 'standby-signal', 'wrong-identity'):
        result = fixtures.run_postgres_case(case)
        self.assertTrue(result['guard_refused'])
        self.assertTrue(result['guard_read_only'])
    result = fixtures.run_postgres_case('stale-pid')
    self.assertTrue(result['guard_read_only'])
    self.assertTrue(result['stock_recovery_qualified'])
```

- [ ] **Step4: Implement exact-image fixtures.** Initialize only synthetic PG17 media with the installed extension versions and data checksums matching the recorded fixture. Prove clean cold copy and physical restore retain system identity, data and metadata; independently restore a logical dump to a fresh cluster and compare logical state while expecting a different physical system ID there. Test empty/wrong/linked/unreadable control/version/data, CRC warning with exit0, standby/recovery signals, stale PID and ordinary unclean WAL recovery. The guard leaves PID/signals/data untouched; the stock server handles only qualified recovery under fencing.
- [ ] **Step5: Run GREEN**, state tests plus `python3 scripts/test-redis-immich-native.py --app immich`; require read-only guard proofs, exact physical/logical preservation, no repair/init during guard startup and exact cleanup. Commit this independent PG deliverable.

### Task 3: Inactive bindings, exact chart adapters and durability alerts

**Files:** inactive `production/` fragments, `check.sh`, `README.md`, manifest tests and scoped CI steps from the File Map.
**Interfaces:** Consumes Task1/2 guards/fixtures; produces Redis/Immich rendered candidates plus a baseline-to-candidate change allowlist. `check.sh` requires `REDIS_CHART`, `APP_TEMPLATE_CHART` and `REDIS_IMMICH_RENDERS`; all outputs are private/offline.

- [ ] **Step1: Inspect exact charts/value layers before editing.** Redis uses globals plus chart28.3.1; Immich uses globals/common/service values and current ApplicationSet app-template5.3.0. Pull those exact charts into `/tmp/redis-immich-charts/{redis,app-template}`; if the source versions change, refresh the actual baseline and review rather than silently upgrading. Record supported existing-claim/init/volume/security/placement/probe fields and all existing command/config/module behavior. Keep guard/data images at the spec's exact pins and preserve native volume names.
- [ ] **Step2: Write/run RED manifest tests.** Reject dynamic/fallback or old source claims in target Pods, wrong image/volumeHandle/namespace/size, missing RWOP/Retain/prebinding/topology/protection, credentials reaching guards, an ownership init/fsGroup rewrite before a guard, stock PID-deletion init remaining, and unrelated container/config/auth changes. Test valid native zero-byte AOF increments separately from absent media.
- [ ] **Step3: Implement only inactive fragments.** CSI handles are `homelab//k3s-block/9999/vm-9999-redis-data.raw` and `homelab//k3s-block/9999/vm-9999-immich-postgres.raw`, with region`homelab`/zone`pve`. Replace Redis chart-generated data claim use with the explicit existing claim; pin actual Redis/exporter digests, set explicit AOF/everysec and retain the original RDB policy. Disable pre-guard ownership changes only after source access is proven. Replace only Immich's PG init/claim/placement; preserve other controllers, image pins, NFS mounts and endpoints. Source admission holds permanently refuse old app claim reuse without affecting unrelated consumers.
- [ ] **Step4: Qualify exporter metrics and add the inactive PrometheusRule.** Verify metric names/values against the exact exporter with synthetic AOF-enabled, AOF-disabled and failed-write fixtures. Use alerts `RedisAOFDisabled` and `RedisAOFWriteFailure`, `for: 2m`, `severity: warning`, and rule-selection label `release: kube-prometheus-stack`; preserve current notification routing. Do not restart Redis for a durability failure or send a production test notification. Pin metric selectors to the Redis service and test alert/recovery with promtool. A recurring AOF disable under real clients remains an execution blocker, not an automatic CONFIG SET loop.
- [ ] **Step5: Run GREEN**, `REDIS_CHART=/tmp/redis-immich-charts/redis APP_TEMPLATE_CHART=/tmp/redis-immich-charts/app-template REDIS_IMMICH_RENDERS=/tmp/redis-immich-renders bash scripts/redis-immich-retained/check.sh`, kubeconform on complete renders/fragments, state/native tests, promtool fixtures and relevant pre-commit hooks. Add their CI checks and compare complete rendered main containers/services/configuration against actual baselines. Commit; prove no active deployment path changed.

### Task 4: Finite native command package and failure recovery

**Files:** private `native/{redis.py,immich.py,lifecycle.py,test_protocol.py}` and established transport/packet adapters; initial runbooks. Public CI tests do not import or depend on ignored private operation files.
**Interfaces:** Each app exposes `preflight() -> dict` and `run_phase(name: str, expected_input_sha256: str) -> dict`. Dispatch requires a fresh frozen authorization/owner/nonce and recorded original clocks; each result names its receipt and exact child outcome. Lifecycle code consumes those receipts and refuses unknown/completed mutation replay.

- [ ] **Step1: Write/run RED package tests.** Test `test_restart_blocked_before_current_memory_restore`, `test_unaccounted_idle_consumer_blocks_quiescence`, `test_live_writer_blocks_target_start`, `test_aof_disable_recurrence_blocks_acceptance`, `test_lost_reply_preserves_original_intent_and_deadline`, `test_known_terminal_resumes_only_unfinished_work`, `test_post_authority_never_reopens_source` and `test_stale_queue_retirement_preserves_sync_options` against assembled commands, not mock success flags.
- [ ] **Step2: Implement Redis phases** in this exact dependency order: fresh identity/client/capacity preflight; acquire scoped ownership/holds and original clocks; quiesce verified producers/workers; protect historical disk state; export current memory; encrypt/copy/decrypt/native-restore/full compare; enable AOF on the still-live source; verify rewrite/persistence; graceful stop and full retirement; immutable snapshot/cold archive/recovery; allocate/populate/bind once; retire helpers; record target authority; start/accept/recreate/move/restore placement; reconcile exact current Git; release holds under watch; exact cleanup/audit/owner release. Do not allow shutdown before accepted current-memory recovery. A failed pre-target operation must not automatically disable already-restored source AOF.
- [ ] **Step3: Implement Immich phases** after Redis's complete acceptance/release: refresh identities/space/writers and validate no out-of-cluster tablespace/WAL roots; acquire fresh ownership/holds/clocks; gracefully quiesce server/jobs; establish coordinated database/original-asset recovery with all overlapping writers accounted for; clean PG shutdown and writer retirement; immutable cold archive/encrypted recovery/independent physical and logical restore; allocate/populate/bind once; verify UID/modes/WWN/filesystem ID and retire helpers; record authority; start/accept/recreate/move/restore placement; reconcile/release/watch/cleanup. Preserve original photo paths/credentials and test existing assets read-only through the real API after activation.
- [ ] **Step4: Qualify assembled commands on disposable synthetic media.** Use the verified local Docker runtime (Linux/x86_64, about31GiB RAM) with operation-labeled owned volumes, `--network none` or an owned internal network and no production path/credential mounts. No new Proxmox VM is needed for synthetic engine fixtures. Reuse the already-qualified NAS/storage/retirement primitives; test this operation's dispatch/gates on synthetic source/target trees. Exercise actual transport limits using read-only SSH/QGA probes; run mutations only against owned synthetic fixtures. Cover JSON/argv limits, native `exited` flag forms, server defaulting, snapshot/archive/POSIX roundtrip, encryption/decryption and partial-stage failures. Do not claim a new remote mutation was qualified by a read-only probe. Original deadlines survive continuation, exact ownership precedes every mutation, and source rollback requires retired target writers. Any additional remote lab, real production-data or credential transfer requires its own concrete approval before use.
- [ ] **Step5: Run GREEN**, `python3 .superpowers/sdd/2026-10-18-redis-immich-retained-csi/native/test_protocol.py`, for all package scenarios and original assertions; freeze the complete packet and checksums, write runbooks distinguishing pre-authority rollback from post-authority recovery, and commit only sanitized sources/tests/docs. Record any unqualified behavior as a blocker instead of weakening a preservation or rebuild gate.

### Task 5: Whole-package review and concrete execution proposal

**Files:** final source/test/CI diff, `docs/superpowers/reports/2026-10-18-redis-immich-preparation.md`, private packet/receipts and the two runbooks.
**Interfaces:** Consumes Tasks1–4's frozen package and native fixture proofs; produces a reviewed exact commit and a production proposal, not live authority.

- [ ] **Step1: Self-review complete spec coverage**, rerun relevant unit/native/render/schema/promtool/pre-commit checks and confirm no active application storage change. Verify fixture cleanup and preserved private boundaries.
- [ ] **Step2: Obtain one independent final review of the entire package**, including assembled commands and full preservation evidence. Under Native execution, do not delegate individual implementation tasks. Resolve verified material findings with focused regression cases, rerun affected checks and freeze the final reviewed package.
- [ ] **Step3: Publish preparation for exact-head CI/Argo diff review.** Keep target candidates inactive; do not claim hosted CI or local lint proves a production rollout. Never merge active changes or sync apps under preparation authority.
- [ ] **Step4: Present the concrete execution proposal.** Name all affected apps/owners and idle consumers, exact current generations and capacity, lab VM/container resources, sensitive payload/destination/retention and key handling, measured restore timings and explicit original deadline budgets, exact source/asset snapshots, recovery paths, activation PR scope and requested merge authority. Ask only for decisions/permissions not already supplied; an AOF policy decision is not authorization for its live transition.

### Task 6: Serial production operations — separate approval required

**Files:** approved frozen private packets/receipts, final active paths from the File Map, runbooks and sanitized completion reports.
**Interfaces:** Requires the explicit Task5 execution approval; produces native accepted Redis, then Immich retained storage and final current-main GitOps state.

- [ ] **Step1: Recheck every production prerequisite** immediately before each operation; refuse changed identities, existing targets, unknown writers, unavailable full-growth capacity, incomplete external recovery or a recurrent AOF disable.
- [ ] **Step2: Execute Redis's frozen phases once**, preserving current queues from memory and proving encrypted restore before enabling AOF/shutdown/target startup. Prove AOF remains healthy with real consumers and their native work; clean recreation, healthy-worker movement and restored normal placement use the same retained filesystem. Do not proceed to Immich until Redis is accepted and its owner released.
- [ ] **Step3: Execute Immich's frozen phases once**, including coordinated original-asset recovery, complete PG identity/data/schema/role/extension preservation and real existing-asset/API acceptance. Prove clean recreation, healthy-worker movement and restored normal placement with the same physical cluster/filesystem.
- [ ] **Step4: Reconcile under the scoped holds** using the exact reviewed activation heads, green hosted checks and intended-only diffs. Retire only captured stale operations, preserve every syncOption, use full current-source revision sets and watch scoped workload/Pod generations continuously for six minutes after hold release. Require fresh Healthy/Synced acceptance at actual merged main.
- [ ] **Step5: Finish each operation** by encrypting/retaining recovery and audit on the approved external locations, deleting only exact owned temporary plaintext/helpers/lab resources, verifying shared resources and normal automation, and releasing its maintenance owner last. Keep protected source PVC/PV/snapshots, accepted CSI images, recovery ciphertext and separate keys. Report actual acceptance and limitations without claiming an unperformed full-cluster destroy/apply test.

## Handoff

The design and implementation plan are approved. The user selected **Native**: implement the tightly coupled
native recovery/authority stages inline, then obtain one independent whole-package
review. No per-task delegation, production action, data transfer, lab creation or
autonomous merge is authorized merely by saving this plan.
