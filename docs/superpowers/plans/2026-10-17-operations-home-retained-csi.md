# Operations and Home Assistant migration implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans inline. One independent whole-package review before production; no per-task delegation.

**Goal:** Complete the six requested application migrations with unattended rebuild recovery and no unnecessary app PVCs.
**Architecture:** Existing static upstream CSI for four apps' files; shared PostgreSQL for Excalidash/CrowdSec with original encrypted identities. Native owned serial cutovers and final Git reconciliation.
**Tech Stack:** app-template5.2.1, CrowdSec chart0.24.2, PostgreSQL18.6, native installed maintenance runtime, Python stdlib and existing psycopg/Helm tools.
**Spec:** docs/superpowers/specs/2026-10-17-operations-home-retained-csi-design.md

## Global Constraints

- Preserve all data, keys, registrations, native images/charts and interfaces.
- Only CrowdSec source timestamps may truncate below one microsecond; no other loss.
- Existing file engines unchanged; Excalidash/CrowdSec must pass independent full-state PostgreSQL conversion/recovery before activation.
-20GiB fixed maximum new images; full growth, staging,8GiB spare and physical free accepted before each allocation.
- Private data/credentials never in Git/logs; encrypt full recovery on VM300 plus this computer, keys separate.
- Fresh exclusive owner/nonce, original two-hour pre-target and24-hour cohort clocks, before-intents/terminals, no uncertain replay or force detach.
- Exact-head hosted CI/scoped Argo diff before autonomous merges; live acceptance separately proved.

## Review Focus

- PostgreSQL-only apps must recover JWT/CSRF/CAPI/cscli/shared credentials without relying on deleted Kubernetes metadata or fresh registrations.
- Nanosecond/timezone normalization must apply only to CrowdSec source timestamps, preserving every other value exactly.
- Karakeep's search-version guard must never wipe an intact store; both DB/job and search state must survive together.
- Home Assistant/Matter restore must retain integration/auth/custom-component identities without contacting devices from fixtures.
- Mixed namespaces, multiple claims/controllers and inherited empty ByteStash config must not omit a source writer, claim, copy or guard.

### Task 1: Exact state contracts and native conversion/recovery qualification

**Files:** assessment/spec; scripts/operations-home-postgresql/data.py; scripts/test-operations-home-postgresql.py; private qualification evidence.
**Interfaces:** read_source(app,path), normalize(app,value,kind,source), read_target(app,connection), compare(app,source,target,columns), transfer(app,path,connection,bootstrap,identity). Produces qualified full field/table comparison and stock image/schema/credential contracts.

- [ ] Record accepted precision exception and exact runtime/image/mount/UID/storage/secret identities; inspect native chart hooks and meaning of every persisted file.
- [ ] Write failing canonicalization tests: CrowdSec9-digit dates accepted only with deterministic sub-microsecond truncation; Excalidash epoch milliseconds/text accepted with exact instant equivalence; malformed timezone/invalid UTF8/NUL/changed or omitted field/BLOB/null/duplicate/integer/float loss refused.
- [ ] Implement minimal typed converter/comparison using existing psycopg and stdlib, with one exclusive serializable transaction, stock markers intact, ordered FK insertion and no lowered allocator floors. Run RED then GREEN.
- [ ] Qualify native provider-created schemas and populated synthetic stock-image startup, fresh empty and wrong-generation refusal, full comparison and independent dump/restore. Retain failures privately.
- [ ] Confirm real source conversion/recovery gates are executable before authority; no unqualified backend switch or fresh registration is accepted.

Run: python3 scripts/test-operations-home-postgresql.py and isolated exact pinned Docker fixtures. Expected: native populated recovery passes, all preservation refusals pass, live sources unchanged.

### Task 2: Inactive manifests and frozen native cutover package

**Files:** scripts/operations-home-retained/guard.py, production/*, check.sh; scripts/test-operations-home-retained.py; scoped CI; private native package; docs/runbooks/operations-home-storage.md.
**Interfaces:** Consumes Task1 exact profiles; produces fixed manifests and immutable one-shot native phase dispatcher, backup/restore/helper/conversion/acceptance/lifecycle/hold/watch/cleanup commands.

- [ ] Write guard refusal tests before code: absent/wrong/linked markers, missing native SQLite/search/Matter identity, wrong Meilisearch version, wrong consumer UID and conflicting/empty SQL state refuse without mutation.
- [ ] Reuse existing read-only path/header guard behavior and native ownership/POSIX/encryption/retirement primitives; add only required mixed-namespace and native chart hooks. Preserve source versions and existing process users.
- [ ] Render actual globals/common/app layers and exact CrowdSec chart. Test six correct static claims, Recreate/single writer/RO guard/token scope, no stale NFS app mount, no unnecessary PVC for two SQL apps, exact image/probe/auth/resource equivalence.
- [ ] Prepare/seal only new database identities after native collision checks; preserve every prior enrollment ciphertext/generation contract. Seal existing app identities without rotating values; qualify chart hook behavior and missing-credential fail-closed startup.
- [ ] Test per-app source/ancestor stop order, exact API/CRI/kernel/physical retirement, capacity accounting, before-intent/no-replay, exact file restore/population, original clocks, queue reconciliation and six-minute watch; preserve historical terminal evidence.
- [ ] Freeze package and all prerequisite hashes. One fresh independent whole-package review; fix Critical/Important findings with RED/GREEN. Run relevant complete checks and hosted CI; merge inactive preparation only when intended diff is proved.

Run: both new test scripts, relevant existing checks, actual layered Helm/kubeconform, native package qualification. Expected: safe refusal and populated recovery pass; no source outage or application activation before accepted review/CI.

### Task 3: Serialized production migrations and final reconciliation

**Files:** scoped values/manifests, static base-configs bindings, PostgreSQL enrollment bundle, runbook, completion report and native private evidence.
**Interfaces:** Consumes frozen reviewed package and fresh native state; produces accepted sources/targets/current-main runtime, durable encrypted recoveries, exact owned cleanup and released owner.

- [ ] Recheck live identities/owners/nodes/Secrets/engines/capacity; acquire fresh owner, preserve clocks and install only scoped holds.
- [ ] For each app, protect source, stop all writers gracefully, verify full retirement, snapshot/capture/encrypt every source; independently restore native cold state before allocating/importing.
- [ ] Populate file targets from immutable original cold sources and verify every file/POSIX value; retire helpers. For SQL apps, rehearse real cold conversion and independent SQL restore, then separately convert native target with exact current-generation checks.
- [ ] Merge tested activation definitions under hold with all hosted checks and intended-only diff, then declare authority and start each target once.
- [ ] Verify preserved native data, keys/auth and existing integrations, recreation and healthy-worker movement; no deliberate device actions or remediation tests.
- [ ] Reconcile complete current Git/live resources, resolve only captured queues, release owned holds and watch six clean minutes; all scoped Apps Healthy/Synced at current main.
- [ ] Encrypt audit, delete only exact owned temporary/plaintext/helper/fixture state, release owner last, merge completion evidence. Retain original sources/snapshots, current targets, ciphertexts/keys and unrelated operations.

Run: frozen exact native phases once, app-specific acceptance, final desired/live watch, cleanup/current-main checks. Expected: all six apps accepted, two SQL apps require no file PVC if qualified, no stale source rollback or unrelated workload changes.
