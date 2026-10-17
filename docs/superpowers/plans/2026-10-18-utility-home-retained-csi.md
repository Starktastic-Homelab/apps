# Utility, download and MQTT retained-storage implementation

> Execute natively with superpowers:executing-plans. One independent final package review before production. The user authorized autonomous implementation, scoped merges and deployment, plus complete Vikunja removal. No repeated approval gates for the established workflow.

**Goal:** Migrate qBittorrent, qBittorrent RU, Changedetection, Stirling-PDF, Microbin, Lingarr, Mosquitto and Zigbee2MQTT private state to retained CSI. Retire Vikunja and its dedicated active resources.
**Architecture:** Existing unmodified Proxmox CSI, static Retain/RWOP ext4 images under owner9999, read-only native startup guards, original images/settings/identities, encrypted two-location recovery independent of Kubernetes metadata. Shared PostgreSQL and media/download paths remain unchanged.
**Spec:** This plan and the accepted retained-storage/rebuild design in docs/runbooks/media-storage.md and docs/runbooks/operations-home-storage.md. Fresh live assessment is private; publish only sanitized evidence.

## Global constraints

- Exact scope: eight named workloads, dedicated Vikunja resources, original shared source ancestors during capture, base-configs storage declarations and scoped dashboard removal. No app upgrades or torrent/payload deletion.
- Fixed target sizes: qBittorrent2GiB; each of the other seven1GiB,9GiB total. Before every allocation, reserve full growth of all current raw images, remaining cohort images,512MiB staging and8GiB spare against quota and pool free. User approved raising only apps/k3s-block quota256GiB to288GiB. Preserve dataset GUID13918781591004512447 and historical Jellyfin partial.
- Preserve every file, credentials, qBittorrent torrent/resume IDs/categories/save paths/modcache, Zigbee network/coordinator/device identities, MQTT retained/session state, and all existing PostgreSQL identities. Lingarr retains its local SQLite files alongside its existing PostgreSQL integration.
- Mosquitto currently specifies /config/data/ while mounting /mosquitto/data/. The former does not exist. Repair this within the migration: create a temporary in-container alias to its existing mounted source, force a native persistence flush, prove a readable stock database, then shut down gracefully; permanent config uses /mosquitto/data/. No MQTT device commands, registrations or network re-pairing.
- qBittorrent native service shutdown must complete before Pod retirement, so the current30-second Pod grace cannot truncate4055 torrent resume records. Do not change torrent settings to manufacture acceptance.
- Vikunja: cold files plus native database dump, dedicated Authentik configuration and original sealed declarations are encrypted and independently restored before dedicated live database/role/provider/app/claims/source files are retired. Remove only proved dedicated resources; preserve shared users/groups/policies, PostgreSQL/Authentik services and historical encrypted recoveries. No broad namespace or snapshot deletion.
- New exclusive maintenance owner/nonce/boot identities and receipts; no old operation replay. On uncertain native execution, preserve exclusion and reconcile before any continuation. User autonomy does not override an actual new decision or unresolved approval rejection.
- Exact-head hosted checks and scoped rendered Argo diff before every merge. Data recovery, application acceptance, recreation, worker movement and final six-minute normal automation watch are separate live gates.

### Task 1: Fresh assessment and executable state contracts

**Files:** sanitized assessment, this plan; private baseline and native package.
**Interfaces:** exact namespace/controller/Pod/PVC/PV/Secret/Argo identities; source paths, complete file formats, target sizes; native read-only acceptance and rollback boundaries.

1. Capture current live spec/UIDs/versions, private source sizes/layouts, every overlapping writer, healthy nodes and storage commitments. Inspect upstream pinned native formats.
2. Verify Vikunja dedicated DB/role/OIDC/dashboard/resource ownership and backup scope; verify all shared dependencies stay operational.
3. Qualify Mosquitto flush/path repair and graceful qBittorrent shutdown using stock isolated fixtures. Record startup guard requirements for native JSON/bencode/SQLite/H2/MQTT layouts.

Expected: no source outage, no live data mutation during assessment; exact data and ownership contracts ready.

### Task 2: Inactive resources and reviewed native execution package

**Files:** scripts/utility-home-retained/*, scoped tests/CI, inactive production manifests, runbook; private owned execution package.
**Interfaces:** consume Task1 contracts; produce retained identity/header guards, eight exact static bindings, per-app layered values and source admission holds, complete cold recovery/retirement/activation/lifecycle/watch commands and scoped Vikunja retirement commands.

1. Write failing guard refusal/format and capacity/scope tests before implementation; reuse existing file/POSIX, encryption, native ownership and physical retirement primitives. No new controller or driver fork.
2. Render actual app-template5.2.1 value layers including qBittorrent base inheritance. Preserve exact images, probes, services, mounts and secrets. Compare all objects; source guards prohibit stale NFS writers after authority.
3. Qualify independent native recovery, exact copy/POSIX checks, empty/wrong target refusal, first-writer boundary, queue/hold reconciliation and cleanup. Freeze packet plus all prerequisites. Review assembled programs, not only fragments.
4. One fresh independent whole-package review; fix substantive findings with regression checks. Run relevant checks and exact-head CI/scoped diff; merge preparation while inactive.

Expected: qualification passes without production downtime; only inactive assets added.

### Task 3: Owned serial migration and Vikunja retirement

**Files:** final desired app manifests, retained storage bindings, dashboards, runbook/report; private receipts.
**Interfaces:** consume frozen packet and fresh identities; produce accepted runtime/current main, independent recoveries and exact cleanup.

1. Acquire fresh owner and verify no conflicting operations, current boots/identities/capacity. Apply the approved quota increase with dataset identity checks. Install exact scoped holds.
2. For each source, capture native state, gracefully stop all writers and overlapping ancestors, verify API/CRI/kernel retirement, snapshot/capture/encrypt, transfer recovery to VM300 and this computer with keys separate, and independently restore/qualify.
3. Populate exact fresh images and verify complete native state/POSIX data; retire helpers; merge reviewed activation under hold; start target once and verify preservation/native APIs.
4. Verify recreation and other-worker attachment under physical old-writer retirement. Restore exact default placement. Reconcile every app to current Git.
5. Independently verify Vikunja backup restore and ownership, merge desired-state deletion, retire only its dedicated resources/data/role/OIDC app/provider and dashboard keys. Confirm no active references, stale controller or remaining dedicated writer.
6. Release only owned holds and watch six clean minutes. Encrypt audit, remove only exact owned plaintext/helpers/fixtures, release owner last. Publish sanitized evidence and outstanding unrelated issues.

Expected: eight apps Healthy/Synced and recoverable, Vikunja absent from active GitOps/runtime/dependencies, shared services healthy, no temporary owner/holds/helpers and no leaked plaintext.
