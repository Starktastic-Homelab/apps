# Redis and Immich retained CSI

Status: written design approved by the user on18October2026; implementation
planning is authorized. The user selected preserving Redis queues with AOF on
retained CSI. Approval does not authorize an outage, runtime repair, secret/data
transfer, lab creation, allocation or cutover. The implementation plan still
requires review and an execution-method choice before command-package work.

## Intent and scope

Make shared Redis queue state durable and move Immich's dedicated PostgreSQL
files off direct NFS. Preserve existing records, pending jobs, identities,
credentials, endpoints, application behavior and original assets. Reuse the
unmodified upstream Proxmox CSI driver, static ext4 RWOP/Retain bindings and
verified VM retirement. Ordinary Terraform/Ansible rebuilds remain unattended,
without Velero or a manual recovery checkpoint.

Perform two serial operations: **Redis first, then Immich PostgreSQL**. Stop only
the freshly verified producers/consumers needed by each operation. Do not change
shared PostgreSQL, enrollment, other application storage or cluster controllers.
Paperless's own index migration and Calibre's split-library qualification are
separate follow-ups in the [assessment](../reports/2026-10-18-remaining-storage-assessment.md).

## Chosen approach and alternatives

Use current upstream engines and complete cold state transfer to retained block
images. This preserves physical PostgreSQL identity, Redis payloads and module
formats without an engine migration or application database conversion.

Leaving both services on NFS avoids a cutover but leaves Immich outside its
documented database-storage advice and leaves durable Redis writes on the
current network filesystem. Treating Redis as disposable was not selected by
the user. Moving Immich into shared PostgreSQL would additionally change its
major version, extension packaging and ownership; it is excluded.

## Storage and image contract

| Service | Proposed retained claim/image | Size | Other storage |
| --- | --- | --- | --- |
| Redis | `databases/redis-data-block`; `k3s-block:9999/vm-9999-redis-data.raw` |2GiB | Preserve and protect the original NFS claim and historical AOF files. |
| Immich PostgreSQL | `media/immich-postgres-block`; `k3s-block:9999/vm-9999-immich-postgres.raw` |10GiB | Photos/videos and model cache stay on their current NFS claims and paths. |

These are proposed names, not existing allocations. Require collision checks,
exact NAS dataset identity, fresh full-growth accounting,512MiB staging and8GiB
spare against both dataset availability and physical pool free before allocation.
The current288GiB quota remains unchanged. Retain the historical Jellyfin partial.

Each PV/PVC uses bidirectional static prebinding, a stable external owner outside
Terraform VM state, explicit ext4/cache-none attributes, Retain, RWOP and Argo
prune/delete protection. No dynamic fallback claim is allowed. PostgreSQL moves
from the control plane to the existing Linux worker pool; verify worker capacity
and preserve the other Immich controllers' placement. Preserve indefinite
not-ready/unreachable NoExecute holds and proven retirement fencing.

Pin Redis to the currently running digest
`registry-1.docker.io/bitnami/redis@sha256:f4797b37502e6db910d3653368fcfadc171ef605586917774de125ddd05b3e62`
and its exporter to
`registry-1.docker.io/bitnami/redis-exporter@sha256:a7144e7e82d7dc5dc5ce5b78e096fe74d9508379a1b8eef07a197adda6d964ad`.
Confirm their identities again before fixture creation. Preserve chart28.3.1,
native command/config composition, modules, authentication and service behavior.
Immich keeps its existing PostgreSQL17/VectorChord0.4.3/pgvector0.8.1 image digest
and server/ML images. No version upgrade or credential rotation is included.

## Redis current-memory recovery and durability

At assessment, mounted/Git configuration enables AOF, but the live server reports
`appendonly no`, no scheduled RDB saves and `aof_enabled:0`. Old AOF files are
not an authoritative backup of current memory. The disabling actor/reason is
unattributed; preserve that evidence and do not infer an application-data loss.
Preparation must trace available configuration/caller evidence and qualify the
transition using the exact running image. If an active controller/client keeps
disabling AOF, stop before execution until that cause is resolved.

Fresh inventory must identify all configured and connected clients, including
idle consumers, scheduled jobs and exporter/operator access. Current connections
include Immich and Paperless on database0 and Dispatcharr on database4. Do not
assume this snapshot is exhaustive. Gracefully quiesce every producer and worker,
drain in-flight tasks according to native behavior and prove there are no unknown
writers. Do not use forced termination or blanket Redis flushes.

While the source Redis process remains alive, export a complete native RDB from
current memory. Protect the old disk state separately. Encrypt the recovery on
VM300 and this computer, keep the recovery key separately outside Git, and prove
independent decryption/native restore with the exact engine and modules. Compare
all keys, types, payloads and absolute expiration semantics privately; permit
only expirations explained by the source checkpoint's native deadlines. Pending
queue state and consumer recovery must be checked, not merely key counts.

Only after current-memory recovery is proven may the reviewed operation enable
AOF on the still-running source, wait for successful rewrite/current persistence
and verify the on-disk state can recover the accepted queue state. A restart is
not a substitute for this transition. Keep producers quiescent through final
capture, graceful Redis shutdown, immutable source snapshot, complete cold
archive and target population. Preserve complete POSIX metadata and module data.
If current-memory export or AOF transition cannot be proven, keep the source
process and stop the operation; do not restart it into historical files.

Populate the target only from the untouched accepted cold state. A read-only
startup guard verifies the retained-volume identity, native AOF manifest and
referenced regular files before normal Redis startup, refusing missing/empty or
wrong media instead of starting an empty cache. Native recovery may handle
unclean ends only within the separately qualified exact-image behavior; no
unreviewed truncation, fix command or lost-job exception is allowed.

Final configuration explicitly enables AOF with the existing `everysec` fsync
policy. Preserve scheduled-RDB policy unless a separately reviewed change is
needed for backup. Do not claim zero loss after a power failure: every-second
fsync has its normal durability window. The original source-to-target migration
must preserve the accepted queue checkpoint in full.

Use the existing Redis exporter and Prometheus rules to report AOF disabled or
failed writes after verifying the actual metric names/semantics. Keep durability
failure observable without adding a liveness restart that could discard volatile
state. Final acceptance verifies AOF enabled and healthy with real consumers
running, then native queue processing and normal cache expiry. Diagnose any
recurring disable rather than applying an automatic CONFIG SET loop.

## Immich physical PostgreSQL transfer

Preserve PostgreSQL17.6 system identifier`7614955115223928876`, complete roles and
password verifiers, every database/table/sequence, migration records, installed
extensions and all original asset paths. Inventory every tablespace, WAL path,
symlink and external writer before defining the cold-copy roots. No blind
recursive chown, new initdb, pg_upgrade, pg_resetwal or extension upgrade.

Hold only verified owning Argo Applications and overlapping parent-volume writers
as required by the existing workflow. Gracefully stop the Immich server/jobs and
coordinate a recovery point for database metadata and original assets before
stopping PostgreSQL. Keep the asset layout and live permissions unchanged. Protect
the coordinated asset snapshot/backup and encrypted database recovery; do not
claim that a database-only copy protects original photos/videos.

After native clean PostgreSQL shutdown and complete writer retirement, snapshot
and archive the complete cluster data with its ownership/modes. Independently
decrypt/restore and start a disposable copy with the exact image, isolated from
production network/services/assets. Verify system identifier, native recovery,
all table contents, sequence floors, roles/verifiers, extensions and application
schema. An independent logical dump restore is an additional recovery proof,
not the source for target population. Protect credentials and records in those
artifacts; nothing enters Git or an unapproved lab.

Populate CSI from the untouched cold recovery after successful qualification.
Replace the current unconditional BusyBox `postmaster.pid` removal with a
read-only retained-data guard and the stock PostgreSQL startup. The guard checks
PG17, the exact physical identity and primary/recovery signals before startup;
it refuses empty, wrong or standby media. Matching unclean primary state may use
normal PostgreSQL WAL recovery only under verified fencing. Qualify stale-PID
behavior in the exact image; if stock startup cannot support the accepted rebuild
contract without a manual cleanup rule, present that decision before execution.

Verify the database natively and through Immich while retaining the same server
version, integration credentials, library paths and endpoints. Read acceptance
must cover existing assets and the API; no user photo deletion, replacement,
synthetic production upload or duplicate worker is part of qualification.

## Preparation, authority and completion

After written-spec approval, create the detailed implementation plan and select
execution method before implementing commands or active/inactive manifests.
Preparation produces isolated fixtures, complete executable commands, fail-closed
guards, rendered actual value layers, exact expected diffs and an independent
whole-package review. Proposed lab resources, sensitive transfers, outage scope,
operation clocks and PR merge authority require a concrete execution proposal
after the package is ready. No production action is authorized by this document.

Use the existing supervised VM300 runtime, serial owner/nonce, immutable operation
clocks, before-intents and known child terminals. Do not replay completed or
uncertain mutations. Qualify failure/recovery paths using disposable media before
asking for production execution. Rehearsal identity/data and infrastructure
credentials have distinct transfer boundaries; infrastructure credentials never
enter application restore fixtures.

The reviewed desired Git definitions must exist before outage. Reconcile them
under the owned Argo holds with exact-head CI and intended-only diffs, preserving
all sync options. Static binding, real native state, clean Pod recreation,
movement between healthy workers, restored normal placement and fresh
Healthy/Synced acceptance at the merged revision are separate mandatory gates.
Release only the owned holds under the existing six-minute workload watch.

Before first target writes, rollback is allowed only after complete target-writer
retirement and source validation. After authority, preserve newest target writes;
never automatically reopen stale NFS state. Keep source PVCs/PVs protected,
retired-source writer guards, immutable snapshots, accepted off-NAS encrypted
recovery and separately protected keys. Clean only exact temporary artifacts,
publish sanitized recovery instructions and release maintenance ownership last.
