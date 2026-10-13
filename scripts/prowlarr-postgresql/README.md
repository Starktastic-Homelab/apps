# Inactive Prowlarr PostgreSQL and retained CSI preparation

These sources implement the app-specific part of the [merged design](../../docs/superpowers/specs/2026-10-13-prowlarr-postgresql-cutover-design.md).
No Application discovers this directory. Merging preparation changes neither
Prowlarr nor PostgreSQL; it allocates no volume and installs no source hold.
Production remains outside this package's local commands.

`guard.py` accepts only the existing identity marker, API key and two exact
PostgreSQL connections, with no active SQLite files. It reads only. `main.sql`
uses the main application owner in a read-only transaction: the 20 stock tables,
migration floor 44 and populated Users/Config must exist. Log login is separate.
This guard blocks fresh initialization; conversion/backup checks establish actual
data preservation. It does not replace those checks.

The final overlay orders retained-state, main enrollment acceptance/login, then
log enrollment acceptance/login using the chart's explicit `dependsOn` graph.
One dedicated ServiceAccount reuses the two existing named GET-only Roles.
Only enrollment inits mount the projected token. Each login sees only its own
password; retained-state reads both to check the XML. The main app has only its
retained `/config` mount and uses the already-qualified native XML route.
Npgsql [quoted connection values](https://www.npgsql.org/doc/connection-string-parameters.html)
preserve semicolons, quotes and spaces in passwords. Never substitute the generic
helper's optional PostgreSQL URI for this connection format.

## Prepare and verify locally

Use the existing Python/PyYAML, Helm, kubectl and kubeseal clients. The repository
public sealing certificate is sufficient; SQL or cluster credentials are not used.
The checked-in encrypted bundle has already been prepared once. Do not run
credential preparation again for this migration.

```sh
# Regenerate only non-secret source serialization after an intentional code change.
python3 scripts/prowlarr-postgresql/prepare.py sources

helm template prowlarr app-template --repo https://bjw-s-labs.github.io/helm-charts \
  --version 5.2.1 --namespace media -f templates/globals.yaml \
  -f templates/common.yaml -f templates/media-arr-common.yaml \
  -f services/media/prowlarr/values.yaml \
  -f scripts/prowlarr-postgresql/production/values.yaml > /tmp/prowlarr-retained.yaml

PROWLARR_SQL_TEST=1 PROWLARR_RETAINED_RENDER=/tmp/prowlarr-retained.yaml \
  python3 scripts/test-prowlarr-retained-startup.py
```

The SQL test creates one named disposable local PostgreSQL 18.6 container, no
network, bounded tmpfs/memory/CPU, synthetic credentials/data only. It verifies
empty/main schema rejection, retained populated state and real SCRAM failures;
it removes its own container. This is separate from the accepted real-copy app
rehearsal and performs no new live enrollment or cluster rebuild qualification.
Run relevant pre-commit hooks and rerun the tests afterward: embedded ConfigMap
bytes are part of the acceptance fingerprint and must survive formatting exactly.

For a future, separately designed enrollment, `prepare.py enrollment --output
/private/exclusive-bundle` wraps the existing generator twice. A preexisting output
is refused; a partial failure keeps exact intermediate ciphertext. Review it rather
than deleting it and regenerating. `publish_enrollment()` can reserialize an exact
completed bundle without sealing again. All prior aggregate ciphertext and app
keys are retained. Neither command applies anything or talks to SQL.

## Activation destinations, after execution approval

| Inactive source | Future active destination |
| --- | --- |
| `production/enrollment/enrollment-{configmap,job,secret}.yaml` | Corresponding PostgreSQL `manifests/` files |
| `production/enrollment/application-secret.yaml` | `services/media/prowlarr/manifests/prowlarr-postgres-secret.yaml` |
| `production/consumer-gate.yaml` | `services/media/prowlarr/manifests/postgres-completion-gate.yaml` |
| `production/guard-configmap.yaml` | `services/media/prowlarr/manifests/retained-startup-guard.yaml` |
| `production/source-hold.yaml` | `services/media/prowlarr/manifests/source-hold.yaml` |
| `production/pv.yaml`, `pvc.yaml` | `infrastructure/base-configs/templates/prowlarr-block-storage/` |
| `production/values.yaml` | Merge into Prowlarr's current values, retaining image/probes/service and value cascade |

Enrollment must become durable desired state before the new app starts: publish
only its three inputs in the approved pre-outage enrollment activation PR, require
a successful full PostgreSQL sync/hook and idempotent full-sync retry, and verify
the existing server Pod/physical identity stays unchanged. An imperative edit
that old Git can revert is insufficient for the consumer gate. This early merge
does not change Prowlarr's SQLite workload or restart PostgreSQL. The app/storage
activation remains the final reconciliation PR after live availability returns.

Preparation approval is not enrollment or outage approval. The private native
execution package must freeze these reviewed files, current object/VM identities,
every actual command body and private transfer destinations; propose absolute
start/checkpoint/end times and rollback deadline; and obtain execution approval
before any of the following live steps. The operation uses the existing VM300
maintenance runtime, not a new controller. Source and restore data never enter Git.

## Finite production sequence and required receipts

Each stage records intent before mutation, native PID/boot/start ticks for a
running command, terminal evidence and acceptance. Missing or uncertain terminal
proof stops for exact native-state reconciliation, never replay. Predecessor
receipts bind the operation, frozen package hash and current generations.

| Stage | Required predecessor and acceptance |
| --- | --- |
| `preflight` | Reviewed package + execution approval; exact original claim/PV/Deployment/API settings, PG physical ID, owner 9999 unused, blank target, full growth quota, Ready worker generations, all direct/parent/NAS writers accounted |
| `enrollment` | `preflight`; approved enrollment merge and full current-input hook success, repeated full sync, canonical two-role login/ownership, unchanged old ciphertext and PostgreSQL Pod |
| `hold-source` | `enrollment`; native maintenance owner/flock, exact four-app idle Argo owners and operation-owned deny window (`prowlarr,base-configs,filebrowser,nfs-provisioner`), original claim Retain/prune/delete protection and matching-claim Pod admission denial |
| `cold-backup` | `hold-source`; graceful UID/RV-guarded shutdown of all three accounted writers; original Pod/CRI/mount retirement on every current VM, NAS open-handle and client checks, stable cold directory metadata; complete archive independently extracted/read back |
| `encrypted-recovery` | `cold-backup`; encrypted archive retained on VM300 plus full-readback workstation copy outside Git, key separately protected, full metadata/hardlinks/bytes and original source unchanged |
| `cold-restore` | `encrypted-recovery`; latest full cold source restored independently, pinned stock app with original SQLite/config/API identity accepted in the approved NIC-less VM; no SQL/infra production credentials in validator |
| `allocate-copy` | `cold-restore`; refresh full quota/generation/blank-name gate; exact one-time 4Gi raw allocation, static binding, isolated helper, ext4 UUID/WWN/VM mapping, full stopped-writer target copy accepted |
| `convert` | `allocate-copy`; latest WAL-aware main materialization, isolated stock initialization of the two new schemas, schema helper stopped, qualified data-only PGLoader accepted with every table/typed field and allocator checked |
| `sql-restore` | `convert`; stopped-writer dumps of both new DBs, independent fresh PostgreSQL restore with fixture-only SQL credentials, all table fingerprints/allocators and stock app accepted; no restore over production |
| `release-app` | `sql-restore`; target XML/marker and fresh-log policy accepted; exact helper Pod/CRI/mount/attachment retirement; record first target app-write boundary, release one frozen final writer, require all five inits/stock API/auth/settings and real integrations |
| `movement` | `release-app`; clean recreation and movement between healthy workers with old writer/mount/attachment retirement, same filesystem and preserved settings; no forced detach/NotReady takeover |
| `git-reconcile` | `movement`; final app/storage/guard/gate desired state reviewed and merged, merged render matches accepted live state, retire only proven stale operations, watch resource transitions while removing only the owned window, all owners Healthy/Synced at merged revision |
| `finish` | `git-reconcile`; completed post-acceptance `pg_dumpall` includes both new DBs/roles, exact temporary helpers/lab/private staging cleaned and absence verified, retained source/archive/key/image/SQL identities kept, native owner released |

The archive contains **all** old `logs.db`, SQLite sidecars and filesystem logs,
plus API/integration credentials and complete private state. Validate metadata,
ACLs/xattrs/hardlinks using the established native copy checks; unexpected writers,
client identities or filesystem semantics require review. Never open the original
NFS SQLite database through a writable or immutable connection.

From a private further copy of the frozen archive, use SQLite `mode=ro` with its
backup API to materialize committed WAL into an exclusive consolidated main file;
require integrity/foreign-key/UTF-8/NUL checks and all-table fingerprints. Do not
discard sidecars or use `immutable=1` on an unconsolidated main file. Before loading,
the source copy must be quiescent and the materialized file becomes immutable.

For conversion, stock Prowlarr creates the new schemas under PostgreSQL-only
helper egress, no Service/ingress or app/indexer/client traffic. Stop that helper,
require the accepted stock initialization rows only, and truncate those new-main
rows with `RESTART IDENTITY`, preserving schema. Reject existing application data.
Use the qualified pinned PGLoader digest from the rehearsal with `quote identifiers`,
`data only`, `prefetch rows = 100`, `batch size = 1MB`. Credentials are supplied
privately to the helper; no credential URI in Pod arguments, Git or tool output.
Verify every typed field with native PostgreSQL timestamp casts, zero loader
errors and every allocator against both current maximum IDs and SQLite historical
high-water marks. Do not patch or normalize the application/source to pass.

Target cleanup occurs only after full-copy/archive acceptance: remove copied
inactive `prowlarr.db`/`logs.db` and their sidecars from active paths and start
fresh filesystem logs. Keep source/archive bytes unchanged. Write canonical XML
only in the new target, remove conflicting scalar PostgreSQL fields, preserve API
key/unrelated settings, then add the exact identity marker after acceptance.
Original diagnostic logs are never imported; main History is preserved, subject
to stock retention once the app runs.

Restore Filebrowser/provisioner after their write-exclusion requirement ends.
Their ancestor-share access means the retained old directory is not immutable;
the independently verified encrypted archive is the recovery copy. Prowlarr stays
held until target acceptance. All independent restore fixtures use pre-cutover XML
plus fixture DB strings, never target XML containing production SQL passwords.

## Expiry, impact and recovery

Prowlarr's search/RSS integrations have downtime during cold backup/conversion
and acceptance. Filebrowser has a shorter copy-window outage; new NFS provisioning
pauses. Existing mounts, downloads/playback and unrelated PostgreSQL consumers
keep running. No PostgreSQL restart or VM/cluster rebuild belongs to the cutover.
The rehearsal's 33-second SQL restore is not a production downtime estimate.
Set absolute checkpoint/finish times only after fresh native preflight; proposed
durations and all private archive/key/validator transfers are part of that approval.

Expiry stops forward work and retains holds/evidence. Before target app writes,
verified stop/detach permits restoration of the exact original writer under the
owned hold, withdrawing source admission only for that restoration. After target
writes, old NFS is stale: preserve newest SQL/CSI state and choose forward recovery
or an explicitly reviewed reverse conversion/loss boundary. Git revert alone is
never data rollback. Keep the app hold while waiting for final reconciliation;
do not rebuild the cluster in that interval. Cleanup never drops the new roles,
databases, retained image, old source or recovery archives.
