# Operations and Home Assistant state migration

User authority: autonomously migrate Karakeep plus Meilisearch, Bytestash,
ConvertX, Excalidash, Home Assistant and CrowdSec; pause for real decisions,
missing access or actual unresolved approval-review rejection. The user accepted
CrowdSec timestamp truncation below one microsecond. The user also authorized fresh ConvertX application state without preserving its
old database or working files, while retaining its original encrypted recovery.
All other application records, fields and identities must survive.

## Final behavior

Retain the unmodified upstream Proxmox CSI, static ext4 RWOP/Retain bindings,
verified VM retirement and unattended rebuild flow. Keep all app/chart versions,
URLs, ingress, auth identities, probes, resources and nonstorage behavior unless
this document explicitly changes them. No Velero, engine upgrade or new controller.

Karakeep keeps SQLite main/job databases and intact Meilisearch1.55.0 storage on
two independent4GiB disks. Bytestash uses2GiB; ConvertX4GiB. Home Assistant
keeps SQLite history and custom components on4GiB and Matter identity/state on
2GiB. Total maximum new capacity20GiB. Each claim is APP-SUFFIX-block with static
raw image `k3s-block:9999/vm-9999-APP-SUFFIX.raw`. Preserve whole trees/POSIX
metadata; no cache or history removal except the authorized ConvertX reset. Old empty Bytestash inherited config claim
is retained/protected but no longer mounted. Existing Meilisearch wipe-on-version-
change wrapper is replaced by a guard that refuses missing/wrong native version;
ordinary startup runs the unchanged stock binary and never deletes an index.

Excalidash0.6.5 and CrowdSec1.8.1 use the existing shared PostgreSQL18.6 deployment
with separately scoped role/database, declarative idempotent enrollment, accepted
current-input Argo completion and canonical login. No application PVC is needed
only after native file inventory and exact stock-image startup prove all meaningful
state is in SQL or encrypted credentials. Excalidash original JWT/CSRF keys become
strictly scoped SealedSecret inputs; writable Prisma/runtime files are ephemeral.
CrowdSec preserves CAPI/cscli credentials and the existing chart-generated LAPI
shared/registration credentials through scoped encrypted declarations. Preserve
current agent/bouncer identities and TLS behavior; never recreate registrations
as a substitute for a complete transfer. Stock registration hooks must be proven
not to overwrite retained identities or block fresh-cluster bootstrap. Secret UID
or owner metadata adoption is explicit, values never rotate.

Use native PostgreSQL schemas/constraints and provider-specific migration records.
Transfer every application table/column/row without importing SQLite migration
records into a PostgreSQL generation. Preserve text/binary content, JSON strings,
nulls, booleans, floating values, timestamps/timezones, relations, duplicates and
allocator floors. Reject invalid encoding, truncation, schema drift or field loss.
Only CrowdSec source timestamps may deterministically truncate fractional digits
beyond six; difference is strictly below one microsecond, dates/timezones preserved.
Excalidash integer-epoch-millisecond and native textual datetimes require exact
instant equivalence. Real-current source conversion, full independent comparison,
stock startup and independent SQL dump restore are required before authority.
Any further incompatibility requires a decision; never silently weaken proofs.

## ConvertX fresh initialization

ConvertX uses its unchanged pinned image, deployment environment and interfaces to
initialize an empty store in an isolated fixture. Require zero users, jobs and
file-name records, strict SQLite integrity/foreign-key checks, native logical
backup equality, and healthy setup before creating an immutable seed archive and
complete file/POSIX proof. Only this newly initialized empty store may populate
ConvertX's retained image; restored or fixture-mutated original data never does.
The original encrypted NFS recovery and separate keys remain protected. This is a
one-time reset; ordinary Pod restarts and cluster rebuilds reuse retained state.
The explicit fresh-state continuation preserves the original outage clock and
failed restore evidence, without repeating stop, snapshot or backup transfers.

## Execution and recovery

Use the existing installed native maintenance runtime with a fresh exclusive owner,
nonce, immutable original monotonic clocks, before-intents and exact child terminals.
No completed or uncertain action is replayed. Old audit source is reference code,
not executable authorization/state. Each app has a two-hour pre-target checkpoint;
cohort owner/outage has24hours. A failed gate preserves its original hold, clocks,
source/target, receipts and recovery; only recorded unfinished work may continue.

Prepare complete command package, fixtures, inactive desired manifests and CI before
any outage. One independent whole-package review before production; fix Critical/
Important findings RED-to-GREEN. Serialize live cutovers. Hold only six app owners,
base-configs, postgres when enrollment changes, Filebrowser/NFS provisioner where
parent mounts overlap. Resolve all writer Pods, NAS processes, CRI containers,
kernel mounts and actual CSI/PVE attachments. Scale owning controllers before
waiting for graceful retirement; no force detach or unreachable-writer inference.
CrowdSec LAPI/agent traffic and ingress enforcement acceptance must preserve existing
security behavior; do not introduce fail-open or deliberately emit remediation.

Retain/protect original PVC/PV identities and permanent deny admission for old app
claims. Capture immutable NAS snapshots after native writer retirement. Archive
all files and POSIX metadata; reject unknown special/xattr features. Encrypt full
recovery on VM300 and this computer, separate keys outside Git. Independently
restore/decrypt complete files and native state, then use disposable copies for
stock-image fixtures. Fixtures have no route to production devices, external
services, media or infrastructure credentials. PostgreSQL app fixtures use only
synthetic database credentials and private copies of application data/keys. Source
cold data never changes, and fixture-mutated files never populate targets.

Fresh capacity gate covers all active raw-image remaining growth, all20GiB new
allocations, staging and8GiB spare, ZFS dataset GUID/quota, healthy pool and physical
free. Preserve the protected historical Jellyfin partial unchanged, accounting its
actual allocation. Do not infer capacity from NFS PVC requests. Quota stays256GiB
if the complete fresh budget fits; a different requirement is evaluated explicitly.

No target writer before complete recovery/population/conversion proof and helper
retirement. Declare authority before first target startup request. Before authority,
source rollback requires intact source and complete target retirement. After
new writes, source is stale: never reopen it automatically. Verify native state,
API/auth/integration behavior without deliberate device commands, clean Pod
recreation, movement to another healthy worker and restored normal placement,
same physical filesystem identities, correct stock DB and zero new restart loops.

Merge exact tested PR heads with full hosted CI and intended-only Argo diffs under
scope holds. Final Git must describe accepted permanent state; replace only known
held queues with full current-source syncs preserving sync options. Observe scoped
Deployment/Pod specs and readiness continuously for six minutes after hold removal.
Then encrypt audit, remove exact owned plaintext/helpers/fixtures, release owner
last, publish sanitized report/runbook. Keep original source roots/snapshots,
accepted images/SQL, off-NAS ciphertexts, keys and unrelated worktrees/operations.

## Acceptance boundaries

Local tests, fixture conversion/recovery, hosted CI and actual live acceptance are
separate. No human fresh OIDC sign-in or Terraform destroy/apply rehearsal is
claimed without doing it. Existing application errors/old failed Pods are baseline,
not automatic permission for unrelated repair. Per-app CSI is required only for
meaningful file state; PostgreSQL alone does not mandate an additional PVC.
