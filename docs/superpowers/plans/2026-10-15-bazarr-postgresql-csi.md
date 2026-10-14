# Bazarr PostgreSQL and CSI Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, then one fresh whole-branch review before production. Steps use checkbox syntax.

**Goal:** Preserve existing Bazarr state while moving its database to PostgreSQL and private config to retained CSI, then reconcile Git and clean up.

**Architecture:** Reuse native enrollment/completion and retained storage/fencing. Add only Bazarr's retained-state check and exact typed conversion adapter. Qualify real data in an offline lab before enrolling or changing production storage.

**Tech Stack:** Bazarr1.6.1, PostgreSQL18.6, pgloader, existing bjw-s5.2.1 chart, unmodified Proxmox CSI, native maintenance/SSH/QGA.

**Spec:** `docs/superpowers/specs/2026-10-15-bazarr-postgresql-csi-design.md`

## Global Constraints

- Fixed database/role/enrollment `bazarr`; Secret `bazarr-postgres-secret/password`.
- Fixed4GiB ext4/RWOP/Retain `bazarr-config-block`, owner9999; no VM9999.
- Preserve image pin, media paths, existing settings/credentials, all16 application tables and stock Alembic ledger.
- Use existing enrollment and serializer; no PostgreSQL replacement or shared controller changes.
- No-NIC VM980 only; no administrator credentials; private0700 directories/0600 files; all temporaries captured and removed.
- Current quotas, complete image-growth budget, connection/resource and writer gates apply before mutations.
- One immutable90/180-minute outage clock; no stale rollback after target writes and no blind replay.
- Autonomous Bazarr completion/merge approved; pause for preservation failure or changed scope, not routine task transitions.

## Review Focus

- Active WAL: rehearsal and final source snapshots must include committed writes, never mistake checkpoint counts for full current data.
- Binary/timestamp/text data: comparison must reject changed ffprobe blobs, lost precision, bad Unicode and silently omitted fields.
- Generated versus external IDs: numeric allocator floors and non-generated/text keys must be distinguished by actual schema.
- Missing settings/database: stock defaults must not create a replacement installation on a fresh cluster.
- Reconciliation: tracking metadata, stale sync history and native watch transport must retain full spec/generation checks.

### Task1: Bazarr state contract and inactive preparation

**Files:** Create `scripts/bazarr-postgresql/{guard.py,main.sql,data.py,prepare.py,README.md}`, `scripts/test-bazarr-retained-startup.py`, inactive `production/` sources; update scoped CI checks after qualification.

**Interfaces:** `guard.validate(root:Path,env:Mapping[str,str])->None`; `data.materialize(source:Path,destination:Path)->dict`; `data.capture(query:Callable[[str],list[dict]])->dict`; `data.compare(sqlite:Path,postgres:dict)->dict`; `prepare.build_sources()->tuple[list[dict],dict]` and exclusive existing enrollment generation adapter.

- [ ] Write guard/data/source tests first: valid preserved config; missing/wrong marker, malformed/empty YAML, missing API/session ID, conflicting URL/env, active SQLite; WAL native snapshot; timestamp/blob/Unicode field mismatch; text/external IDs versus discovered sequences; empty SQL data; actual value layers and fixed bindings.
- [ ] Run tests and confirm expected missing-Bazarr-contract failures; implement minimal contract using stock vendored YAML and existing enrollment/serializer.
- [ ] Render actual globals/common/media-arr/bazarr plus inactive override, validate schema and run focused tests. Confirm all existing discovered app values/secrets are unchanged. Commit.

### Task2: Native offline real-data qualification and execution packet

**Files:** Private ignored `.superpowers/sdd/2026-10-15-bazarr-postgresql-csi/` transport, stage commands, receipts; sanitized qualification report in `docs/superpowers/reports/`; reuse existing maintenance lock/retirement/recovery primitives with Bazarr-specific bindings.

**Interfaces:** Task1 typed proof and guarded values; immutable command packet declares per-stage inputs, exact VM/resource/boot identity, private paths, ownership and no-replay intents. Lab accepted proof binds source DB/settings hashes, all typed rows, allocators and independent restore.

- [ ] Test native packet negative gates before mutation: changed VM/boot/UID/hash, prior intent/unknown child, foreign mounts, bad footer, missing tracking and empty/unsupported watch version.
- [ ] Acquire fresh maintenance owner; take a WAL-inclusive native online SQLite backup and stable settings copy into temporary root-only VM300 storage. Verify source writer remains healthy; copy rehearsal state/public images into no-NIC VM980 through verified private media.
- [ ] Initialize pinned stock PostgreSQL schema, import using documented data-only/case/timestamp behavior, compare every field/relationship/allocator, run stock app startup/restart/new-ID probe, custom dump and independent fresh restore. Reject preservation differences.
- [ ] Produce inactive credentials once through existing sealing workflow, preserve all prior aggregate ciphertext, and assemble exact enrollment/cutover/recovery/reconciliation/cleanup commands. Include working typed API watch, metadata adoption and current-source full sync.
- [ ] Validate local/real packet gates and preparation renders; commit sanitized qualification/implementation. Dispatch one fresh final whole-branch review with this spec, plan, all Review Focus items and ledger rulings; fix substantive findings once with failing regression tests before production.

### Task3: Enrollment, cutover and final Git reconciliation

**Files:** Scoped enrollment declarations; final `services/media/bazarr/{values.yaml,manifests/*}`, `infrastructure/base-configs/templates/bazarr-block-storage/{pv,pvc}.yaml`, scoped CI/README and Bazarr storage runbook. Private receipts/recovery outside Git.

**Interfaces:** Task2 accepted lab/packet proof; existing Argo completion hook, physical PG identity, source/target identity proofs, encrypted recovery and original outage clock.

- [ ] Publish/merge enrollment after five exact-head hosted checks; verify current-generation hook, restricted login and repeat idempotency without credential rotation.
- [ ] Refresh owners/UIDs/VMs/boots/writers/capacity; acquire exact scoped hold, protect old claim and retire all writers; start one native outage clock. Capture/restore/readback complete cold recovery before image allocation.
- [ ] Allocate only absent owned image, copy accepted config/marker, materialize cold DB, initialize/import and compare stock PG schema/data/floors. Independent SQL recovery must pass before target startup. Remove all helpers/writers/devices before real app acceptance.
- [ ] Start stock PostgreSQL/CSI Bazarr, verify settings/libraries/history/integrations, native writer retirement, recreation and healthy-worker movement; preserve newest writes. Accept complete manual PostgreSQL backup.
- [ ] Publish final scoped reconciliation PR, inspect exact final diff and five hosted checks, merge under user authority. Prove complete merged-main/live equality, captured-queue retirement and pre-release watch; fresh current-source full sync must resolve to exact merge SHA and remain Healthy/Synced for six minutes.
- [ ] Remove only owned helper/Job/lab/media/plaintext generations, preserve protected NFS and encrypted recovery, release owner and verify all affected apps/nodes. Commit/report concrete accepted results; mark tasks complete only with live evidence.
