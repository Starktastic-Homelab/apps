# Bazarr PostgreSQL and retained CSI migration

Status: design direction and autonomous completion approved October15. Execute
inline; stop for failed preservation qualification or a decision that changes scope.
The approval includes scoped PR publication/merge and temporary rehearsal resources.
Record all concrete resource identities and command hashes before live mutations.

## Outcome and boundaries

Preserve Bazarr settings, API/authentication and provider credentials, language
profiles, Sonarr/Radarr IDs and paths, subtitle inventory, blacklist and history.
Use the existing PostgreSQL18.6 enrollment system and unmodified Proxmox CSI.
Keep the pinned `lscr.io/linuxserver/bazarr:v1.6.1-ls364@sha256:d24bd0048c759a468970989e9df11a6b96a7628d556d00f923e60a35ba59237b`.
Media and subtitles remain on `media-library-pvc` at `/data` on NFS; keep the
existing `/scripts` ConfigMap and post-processing behavior. No image upgrade,
other database conversion, quota increase, historical partial deletion or new
controller is included. Normal Terraform rebuilds remain Git/retained-data driven.

## Identities and startup

Enrollment ID/database/role: `bazarr`. Application Secret:
`media/bazarr-postgres-secret`, key `password`. Reuse Argo acceptance and restricted
login gates, preserving all existing enrollment ciphertext. Do not rotate or
recreate a completed credential bundle after a partial or lost response.

Target PV/PVC: `bazarr-config-block`,4GiB, ext4, RWOP, Retain, prune/delete protected.
Volume: `k3s-block:9999/vm-9999-bazarr.raw`; CSI handle:
`homelab//k3s-block/9999/vm-9999-bazarr.raw`. VM9999 is image ownership only.
One replica, Recreate, healthy-worker placement and existing verified VM retirement
provide fencing. Reject conflicting resources/images before allocation.

Set stock `POSTGRES_ENABLED=true`, `POSTGRES_HOST=postgres-postgresql.databases`,
`POSTGRES_PORT=5432`, `POSTGRES_DATABASE=bazarr`, `POSTGRES_USERNAME=bazarr`, and a
Secret-sourced `POSTGRES_PASSWORD`; reject conflicting `POSTGRES_URL`/config paths.
Use `PGSSLCERT=/tmp/postgresql.crt` only if the pinned non-root runtime requires it.
Set `postgresql.enabled: true` in retained config as well: stock backup uses this
setting independently of the environment. Preserve every other YAML setting and
identifier; add `.homelab-bazarr-config` containing
`homelab/bazarr/config/v1\n`. Exclude SQLite active-path files from accepted target
only after recovery proof. Never delete them from the original source/archive.

A read-only retained-settings guard uses the pinned app's vendored YAML parser,
without importing application configuration modules or running initialization.
Reject missing/wrong marker, empty/malformed settings, missing API/session IDs,
conflicting environment and active SQLite files. Enrollment acceptance precedes a
read-only canonical SQL guard. Require the exact17 stock tables, the qualified
Alembic revision, configured system state and preserved library/profile data before
stock startup; empty or wrong databases must not become fresh installations.
Keep stock `/ping` probes after checking they have no external dependency.

## Conversion and proof

Follow the [official procedure](https://wiki.bazarr.media/Additional-Configuration/PostgreSQL-Database/):
initialize the stock PostgreSQL schema once, stop its writer, clear only seeded
`system`, `table_settings_languages`, `table_settings_notifier`, then use pinned
pgloader with quoted identifiers, data-only loading and documented timestamp casts.
Preserve the stock PostgreSQL Alembic ledger; reconcile the source revision against
that stock schema before import. Compare all16 application tables, every typed
field and relationship, binary ffprobe caches, booleans, mixed-case column names,
timestamp precision and text/Unicode. Reject loader errors, partial imports,
unvalidated constraints and disabled triggers. Discover actual generated sequences;
raise floors to at least source SQLite counters and surviving numeric IDs. Text
keys and non-generated Servarr IDs must not acquire invented allocators.

A live native SQLite backup is rehearsal input only. Preserve WAL-inclusive state
through SQLite's backup API, independently inspect the consistent copy, and never
claim immutable live-file counts include WAL. Production uses a fresh stopped-writer
capture of the entire private tree including WAL/SHM, ownership/modes/ACLs/xattrs.
Materialize a separate DELETE-journal database without altering the recovery archive.
A loader exit or startup alone is not preservation/recovery proof.

## Rehearsal, credentials and recovery

Use disposable no-NIC VM980 from template900,2 CPUs,3GiB RAM,12GiB vm-pool.
Require absent VM980, exact new UUID, no NIC before first start, disk-only boot,
6GiB available host RAM and20GiB vm-pool availability. Any host change needed to
meet those gates is a separate decision. No production administrator login or
PostgreSQL administrator password enters the lab. Copy only Bazarr consistent DB,
settings and public pinned tools/images through root-only VM300/PVE media; existing
app/provider credentials in settings remain private and offline. Use fixture SQL
credentials; no actual NAS media or production integration endpoints are reachable.
Verify complete conversion, stock startup/restart, new generated-ID behavior and
an independent fresh PostgreSQL custom-dump restore. Remove only captured owned
lab/media/plaintext generations after acceptance or a safe failed-rehearsal cleanup.

Stock PostgreSQL-mode backup ZIPs contain settings only; their SQLite-centric
restore UI is not the database recovery path. Shared PostgreSQL backups plus the
qualified SQL/config recovery procedure cover it. Production cold and SQL recovery copies are encrypted and readback verified on
VM300 plus this computer, with a separate key outside Git. Protect original
`/mnt/apps/pv/media/bazarr` and its bound source PVC/PV indefinitely.
Before target writes, only a verified unchanged source may reopen. After target
writes, never revert to stale SQLite/NFS; preserve newest writes and request a
recovery decision if forward completion fails.

## Production and reconciliation

Use the installed VM300 maintenance owner/execution exclusion, immutable command
packet, captured UIDs/VM UUIDs/boots, no-replay intents and native child retirement.
Refresh full existing-image growth, snapshots/partials, staging and8GiB headroom
against the unchanged160GiB quota; refresh PostgreSQL connection/resource capacity.
The October15 assessment is evidence, not an execution-time allocation gate.

Prepare and qualify commands before outage. Hold exactly Bazarr, base-configs,
Filebrowser and NFS provisioner. Identify all source and ancestor writers, install
an old-source Pod guard and stop/retire them before cold capture. Resume Filebrowser
and provisioner after independent source recovery. Jellyfin playback and download
apps are outside downtime scope. Record one outage clock; checkpoint90 minutes
before target startup,180 minutes overall, same VM300 boot/monotonic clock. Preserve
failed receipts and original clocks; an expired/unknown stage is not replayable.

After target population/import/recovery, test stock API settings/history/library,
clean recreation and healthy-worker movement with unchanged physical volume identity.
Cover integration acceptance automatically where read-only evidence suffices; pause
for human acceptance only if it cannot. Run one manual unchanged PostgreSQL backup
and verify both role/database coverage, gzip EOF and the stock completion footer.

Publish/merge scoped reconciliation after all five hosted checks on its exact head.
Adopt only missing Argo tracking annotations after exact live-spec comparison.
Require full merged-main/server-normalized equality before retiring captured stale
queues. Use native typed-list/watch API with a nonempty resourceVersion. Start watch
before hold release; require six minutes without deployment/spec/claim regression,
Healthy/Synced and successful full current-source operations resolving to merged SHA.
Argo auto-sync follows HEAD; do not override that policy with a conflicting SHA.
Remove exact owned helpers/Job/lab/media/plaintext, retain targets/sources/encrypted
recovery, release maintenance ownership, and freshly verify final state.
