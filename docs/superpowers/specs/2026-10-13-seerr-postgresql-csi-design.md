# Seerr and Seerr-RU: PostgreSQL and retained CSI configuration

Status: accepted design with an approved inactive preparation plan. The disposable
rehearsal qualifies conversion compatibility; production enrollment, storage
allocation, outage and activation still require a separate execution proposal.
Both live instances still use SQLite on NFS. See the
[qualification report](../reports/2026-10-13-seerr-preflight.md),
[preparation evidence](../reports/2026-10-13-seerr-inactive-preparation.md) and
[activation mapping](../../../scripts/seerr-postgresql/README.md).

## Desired behavior

Preserve both instances' users, requests, media, issues, settings, integration
credentials, session secrets and ID allocation history. Use the existing shared
PostgreSQL 18.6 deployment with separate restricted owners and databases. Keep
stock Seerr 3.4.1 and unmodified upstream Proxmox CSI. Configuration stays on
retained block storage; shared media and download paths remain unchanged.

The usual Terraform destroy/apply workflow must recover from Git and retained
storage, without a Velero checkpoint or manually recreated database declarations.
Reuse the existing coupled worker replacement and verified VM retirement fencing,
PostgreSQL retained-data guard and enrollment completion protocol.

| Instance | Enrollment ID | Database and role | Retained PV/PVC | Initial size |
| --- | --- | --- | --- | --- |
| Seerr | `seerr` | `seerr` | `seerr-config-block` | 4GiB |
| Seerr-RU | `seerr-ru` | `seerr_ru` | `seerr-ru-config-block` | 4GiB |

These names are proposals, subject to current collision and ownership checks.
Use owner9999 image names `vm-9999-seerr.raw` and `vm-9999-seerr-ru.raw` on
`k3s-block`, with exact static CSI handles, ext4, Retain, RWOP, one replica,
Recreate and existing healthy-worker placement. Protect bindings from Argo prune
and deletion. Reserve both full 4GiB allocations against the existing aggregate
quota, established image growth and snapshots before creating anything.

The small settings directories currently need less than 8MiB each including
logs. Four GiB provides a modest explicit growth budget; PostgreSQL data growth
belongs to the existing shared database volume and its capacity checks.

## Conversion and startup contract

Follow the qualified stock procedure: initialize the PostgreSQL schema using
Seerr's pinned PostgreSQL migrations, then import application data with the
documented pinned pgloader image. Preserve the engine-specific migration ledger;
never import the SQLite migration table into PostgreSQL.

A cold production capture must include the SQLite main file, WAL/SHM sidecars and
all configuration. Produce a separate verified single-file DELETE-journal input
for pgloader through SQLite's native backup API. Compare its complete schema,
rows and allocator counters with the captured source; never change the source
or recovery archive. Loader exit status alone is insufficient: reject error logs,
partial imports, disabled triggers or unvalidated constraints. Compare every typed
field in all 14 application tables. Preserve sequence floors including deleted
SQLite IDs, rather than only the maximum surviving row ID.

Use native `DB_TYPE=postgres`, host `postgres-postgresql.databases`, port5432,
instance-specific DB/user, a Secret-sourced password and `DB_POOL_SIZE=3`.
Keep settings semantics and existing secrets unchanged. Retained configuration
contains an instance-specific identity marker and existing settings; inactive
SQLite files are removed from the target's active database path only after backup
and copy acceptance. Keep the original source and encrypted recovery copies.
Validate log symlink targets and retain diagnostic history in the recovery archive.

Before stock startup, a read-only guard must reject missing/wrong identity,
missing settings or required API/session keys, SQLite fallback files and a wrong
PostgreSQL configuration. Reuse the current Argo completion gate and canonical
role login. Verify the expected stock schema, PostgreSQL migration floor and
populated user data before stock Seerr can initialize an empty database. This
structural startup check supplements the full cutover comparison.

Preserve `baseApp` inheritance: common image, probes and container conventions
stay in Seerr's base values; Seerr-RU overrides only instance identity, claim,
credentials and gate inputs. Both apps must enable manifest discovery when their
new gate, guard, encrypted Secret and source-protection manifests become active.

Use stock `/api/v1/status/appdata` for health probes and verify its local response.
The current `/status` route can wait for GitHub's update check when the preserved
settings enable it; an external outage should not drive container health.
This changes only the probe endpoint, not application settings or update behavior.

## Delivery and production boundary

Prepare inactive sources, focused guard/consumer tests and actual layered chart
renders first. Reuse enrollment generation and existing SQL qualification. Seal
new app passwords with `scripts/seal.sh`, preserve every existing aggregate
ciphertext and refuse credential regeneration after an ambiguous partial result.
The preparation PR must leave all discovered production manifests unchanged.

Publish approved enrollment inputs before the outage, then require full hook
acceptance, canonical restricted logins and idempotent retry against the existing
PostgreSQL physical identity. No other database or role is renamed or rotated.

The later execution proposal freezes exact commands, identities, private transfer
destinations, allocation budget, absolute outage checkpoints and recovery gates.
Use the existing VM300 maintenance runtime and the qualified Prowlarr release
procedure. Hold both apps, base-configs, Filebrowser and the NFS provisioner;
recheck all direct, parent-directory and NAS-side writers before cold capture.
Expected impact is Seerr/Seerr-RU downtime and a bounded Filebrowser/provisioner
pause. Jellyfin, existing media playback and download workloads are outside scope.

Retain a verified encrypted cold backup on VM300 and this computer with the key
separate from Git; prove recovery before first target startup. Convert and verify
both stopped-writer snapshots, then accept each stock startup/API state, clean
recreation, healthy-worker movement and integrations. An offline rehearsal cannot
establish live integration or CSI movement acceptance. Require human fresh sign-in
and request-history checks if automated evidence cannot cover them.

Before target writes, rollback can resume the unchanged original source after
reconciling all children. After target writes, the source is stale: recovery must
preserve newest target state through a fresh consistent reverse conversion or
restore with an explicitly accepted loss boundary. A Git revert is insufficient.

Reconcile accepted live state through a CI-gated final apps PR while holds remain.
Do not rebuild the cluster in this interval. Release only the captured owned hold
after merged-main render/live equality and qualified stale-operation recovery.
Start observation before release, then require fresh final-main Healthy/Synced
acceptance and a six-minute watch through reconciliation after release. Delete
only captured temporary generations and
copies; retain old protected sources and encrypted recovery assets. Preparation
and execution require their own review and authorization.
