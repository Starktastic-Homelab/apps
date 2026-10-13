# Prowlarr: PostgreSQL main state and retained CSI configuration

Status: live data cutover accepted on October 13, 2026. Prowlarr now uses the
existing PostgreSQL service and retained CSI configuration. Independent cold and
PostgreSQL restores, real integrations, clean recreation and healthy-worker
movement passed. This activation publishes the tested live state; owned hold
release requires exact current-main/Git/live equality after the CI-gated merge.
See the [production report](../reports/2026-10-13-prowlarr-production-cutover.md).

This specializes the established [live migration workflow](2026-10-10-live-storage-migrations-design.md)
for Prowlarr. Its older recommendation to keep Prowlarr on SQLite is superseded
for this application by the successful PostgreSQL rehearsal. It does not change
another application's engine or shared media/download storage.

## Final state

Keep the exact current Prowlarr 2.6.5.5623-ls161 image digest. Use the existing
shared PostgreSQL 18.6 service and unmodified upstream Proxmox CSI. Preserve the
API key, users, indexers, applications, download client, notifications, tags,
profiles, filters, mappings and all main-database rows at conversion time.

| Item | Planned binding |
| --- | --- |
| Main enrollment ID / DB / owner | `prowlarr-main` / `prowlarr_main` / `prowlarr_main` |
| Log enrollment ID / DB / owner | `prowlarr-log` / `prowlarr_log` / `prowlarr_log` |
| Aggregate password keys | `prowlarr-main-password`, `prowlarr-log-password` |
| Application SealedSecret | `media/prowlarr-postgres-secret`, keys `main-password`, `log-password` |
| PostgreSQL service | `postgres-postgresql.databases:5432` |
| PostgreSQL physical ID | Existing `7584099661242523698`; no new server or physical restore |
| Each connection pool | `Maximum Pool Size=5;Timeout=10` |
| Retained PV / PVC | `prowlarr-config-block` / `media/prowlarr-config-block` |
| Initial image / filesystem | 4GiB / ext4, full logical growth budget reserved |
| Proxmox image | `k3s-block:9999/vm-9999-prowlarr.raw` |
| CSI handle | `homelab//k3s-block/9999/vm-9999-prowlarr.raw` |
| Fencing and placement | RWOP, one replica, Recreate, healthy k3s worker |
| Old source | Retain `media/prowlarr` and its bound PV/NFS directory; deny new Pods mounting that claim |

Four GiB allows growth beyond the measured roughly 305MiB directory without using
an NFS request as a capacity measurement. Recheck current usage and the existing
160GiB aggregate quota against all established image growth, snapshots and this
full 4GiB reservation before allocation. Refuse a conflicting image, consumed
owner 9999, incompatible topology or insufficient headroom; never overwrite an
existing target. The separately approved
[October 13 quota amendment](../reports/2026-10-13-csi-quota-160g.md) raised the
initial 128GiB ceiling without changing image sizes or the headroom gate.
No Ansible per-service inventory or new storage controller is
needed: the permanent app binding lives in Git. Established VM-retirement fencing
and coupled worker replacement on control-plane replacement remain required.

Both roles are ordinary restricted owners of their own database. Do not grant
superuser or add shared-role behavior to enrollment. Reuse `prepare.py new`,
`scripts/seal.sh` and the existing encrypted aggregate to prepare each declaration
once, retaining all prior ciphertext. No existing database or role is adopted,
renamed, rotated or deleted. The unused Autobrr PostgreSQL enrollment remains.

Use Prowlarr's two native XML fields, `PostgresMainDbConnectionString` and
`PostgresLogDbConnectionString`, on the retained config directory; this is the
configuration route exercised in the lab. Build them from the canonical new
application credentials and fixed host/DB/role/pool settings. Modify only the
target copy. Remove conflicting scalar PostgresHost/User/Password settings from
that copy, preserving every unrelated XML setting and the API key. Publish only
SealedSecret ciphertext. The helper's optional PostgreSQL URI output is not an
Npgsql connection string and must not be substituted for these fields.

## Log policy

Start a fresh PostgreSQL log database and fresh filesystem diagnostic logs. Retain
the old logs.db, any WAL/SHM sidecars and the complete old logs directory in the
encrypted stopped-writer recovery archive and original NFS source. Do not import
them, truncate the source or count log rows as main search history.

Copy and verify the entire private directory first. Only after complete archive
and target-copy acceptance, remove the copied inactive SQLite main/log files and
copied filesystem logs from the target's active paths. This cleanup is limited to
the new copy; the original and recovery archive remain. Retain definitions,
backups and other application files with ownership, permissions and required
metadata. Prowlarr then creates new active diagnostic logs through its stock code.
Main History is preserved before startup; ordinary Prowlarr retention resumes
once the application runs. This is not a promise to disable its housekeeping.

## Preparation package and focused checks

Prepare all sources outside activation before requesting execution approval:

- Final `services/media/prowlarr/values.yaml`: target claim, placement/fencing,
  retained-state init and two enrollment/login gate pairs; original image and
  value cascade preserved, no temporary replicas0.
- `services/media/prowlarr/manifests/retained-startup-guard.yaml`: a read-only
  ConfigMap guard for marker `.homelab-prowlarr-config` with value
  `homelab/prowlarr/config/v1\n`, existing config.xml/API key, both exact canonical
  connection strings and absence of active SQLite DB/WAL/SHM files. It must never
  generate configuration, write secrets, create a database or repair data.
- `services/media/prowlarr/manifests/postgres-completion-gate.yaml` and
  `prowlarr-postgres-secret.yaml`: one dedicated ServiceAccount, existing named
  GET-only Roles and encrypted app keys. Reuse existing completion code; namespace
  and credential mounts are composed for two declarations without duplicate init
  names. Only acceptance inits see the projected API token. Main and log login
  inits see only their own password. Reject an uninitialized main DB by checking
  the established stock schema, migration floor 44 and populated Users/Config before
  the application can bootstrap fresh state. Verify log login separately.
- Matching PostgreSQL `enrollment-configmap.yaml`, `enrollment-job.yaml` and
  `enrollment-secret.yaml` changes, preserving existing declarations/ciphertext.
  Prepare once; full-hook retry verifies the same identities and credentials.
- Static `infrastructure/base-configs/templates/prowlarr-block-storage/pv.yaml`
  and `pvc.yaml`, with Retain and `Prune=false,Delete=false`, exact claimRef and
  volumeName, ext4/cache-none and the established topology.
- `services/media/prowlarr/manifests/source-hold.yaml`: permanent old-claim Pod
  admission denial, using the existing Autobrr pattern. It does not exclude
  Filebrowser's parent-directory access, NAS processes or arbitrary NFS clients.
- A private frozen operation package under VM300's native maintenance root, with
  reviewed command bodies, image pins, current source/target identities, bounded
  phase checkpoints, operation owner and accepted intent/PID/terminal receipts.
  Keep credentials and real data out of Git and tool output.

Focused tests must demonstrate a valid read-only retained guard; rejection of
missing/wrong marker, missing API key, wrong/partial credentials and SQLite
fallback files; no byte changes or secret output; two gate identities, correct
mounts/RBAC, failed enrollment/log login/empty-main blocking; and the actual Helm
render with every value layer. Use `scripts/test-prowlarr-retained-startup.py` for
these app-specific contracts. Reuse existing gate/SQL qualification rather than
adding another enrollment engine or repeating full cluster rebuild tests.

Render app-template 5.2.1 with globals, common, media-arr-common and the Prowlarr
values. Render base-configs and inspect the static binding/source protection too.
Run relevant pre-commit, YAML, raw-manifest schema and repository compatibility
checks. A passing local render is preparation evidence, not live rollout evidence.

## Live operation and impact

Prepare the final reconciliation diff and enrollment bundle before any outage.
Apply the approved new enrollment inputs while Prowlarr still uses SQLite; require
successful full PostgreSQL hook acceptance, canonical main/log login, restricted
ownership and an idempotent full-sync retry. A failure may delay fresh service
rollouts, but does not authorize changing existing PostgreSQL consumers.

Acquire the native maintenance owner and scoped deny window for `prowlarr`,
`base-configs`, `filebrowser`, and `nfs-provisioner`. Confirm exact owners and idle
operations before the hold.
Resolve queued/stale operations only by the already qualified release procedure.
Do not suspend PostgreSQL or its existing backup schedule for this app move.
Its current `pg_dumpall` covers all databases; verify a completed post-acceptance
backup includes both new databases and roles, without restoring over production.
A scheduled dump captured during conversion is not cutover recovery acceptance.

Install the old-source guard, protect the exact source PVC/PV against prune/delete,
stop Prowlarr, Filebrowser and the provisioner, and verify all direct/parent-path
and NAS writers are absent. Existing unrelated NFS mounts keep operating; new
provisioning waits. Require source unmount and stable directory metadata before
capturing a complete cold archive. SQLite checks and conversion must include
committed WAL content: materialize a consistent main DB from the frozen copy
using SQLite's backup API; do not ignore WAL with an immutable open of an
unconsolidated copied main file.

Retain the encrypted archive on VM300 and this computer, with its recovery key
separate from both ciphertext and Git. The archive contains the real API key,
integration credentials, user data, main history and old logs. Its private
transfer/storage destinations and any isolated restore VM must be explicitly
included in execution approval. Never send administrator or production SQL
credentials to a restored-data validator. Verify decrypt/readback, full directory
metadata and application recovery from an independent copy before target release.

Allocate only the approved blank 4GiB target using the established Proxmox path,
record image and filesystem identity, bind the static PV/PVC and complete the
stopped-writer copy. Terminate/detach copy helpers before allowing the app writer.
Restore Filebrowser and the provisioner once their write-exclusion requirement
ends and their own Git/live acceptance is restored; Prowlarr remains held.

Initialize the two new DB schemas with the pinned stock Prowlarr under helper
isolation: no Service/ingress selection, no application/indexer/download-client
egress, only the required PostgreSQL connection. Stop the schema helper before
loading. Refuse any established/unaccepted application data in the destination.
Remove only documented stock initialization rows in the new main DB, keep its
schema, and use the qualified pinned PGLoader data-only/quoted-identifier options.
Compare all source tables, counts and typed fields at PostgreSQL precision;
verify IDs/allocator high-water marks, zero loader errors and unchanged source.
Do not normalize/drop source records or patch the application to make it pass.

Require a consistent dump of both target DBs with the writer stopped and verify
the qualified independent restore. New app-owned DB credentials may be used by
the approved native helpers; only disposable fixture SQL credentials enter any
offline restore environment. Build validator XML from the archived pre-cutover
config and fixture DB fields; never transfer the target XML containing new
production SQL passwords into that environment. Then release one target writer,
verify PostgreSQL backend/settings/authentication/API key, ordinary searches and configured
application/client integration, exact housekeeping completion, restart and clean
movement between healthy workers. Preserve any new target writes before rollback.

Expect a Prowlarr outage during backup, conversion and acceptance; dependent apps'
Prowlarr-backed searches/RSS requests may fail or retry. Filebrowser has a shorter
copy-window outage and new NFS provisioning pauses. Existing downloads, media
playback and unrelated PostgreSQL consumers remain running. No PostgreSQL
restart, VM replacement or cluster rebuild is part of this cutover.

The concrete package must propose absolute start/checkpoint/end times and an
explicit rollback deadline before approval. The lab's 33-second SQL restore is not
a production downtime estimate. A checkpoint expiry stops forward work; it never
authorizes destroying current data or releasing an unverified writer.

## Git reconciliation and recovery

Restore Prowlarr service before the final activation/reconciliation merge. Keep
the owned Argo hold while awaiting that merge. Final Git includes the accepted
static binding, guard, credentials/gates and one-replica workload; it excludes
temporary hold windows, helpers, replicas0 and plaintext XML/credentials. Keep the
protected source excluded from extraneous-resource comparison as in Autobrr.

After merge, render the merged revision and compare it to the accepted live state,
resolve stale queued operations, remove only the owned window, and require
Healthy/Synced at that revision. Verify one CSI attachment and normal worker
retirement fencing. Ordinary rebuilds then recover configuration from retained
CSI and databases/credentials from retained PostgreSQL and encrypted Git inputs.
No Velero or pre-merge backup checkpoint is introduced. Do not rebuild the cluster
between live cutover and final reconciliation because old Git cannot recover the
temporary live-only state or hold.

Before the first target app writes, rollback can stop/detach the new writer and
restore the exact original SQLite workload under the scoped hold. The temporary
source guard may be removed only for that verified original-writer restoration.
After target writes, preserve current target state first: do not blindly restore
the stale source or assume a Git revert converts PostgreSQL back to SQLite.
Forward recovery is preferred; a reverse conversion or loss boundary needs a
decision. Keep hold/receipts on an uncertain outcome rather than replaying writes.

Cleanup deletes only exact owned helpers and disposable test resources. Keep the
old source, encrypted recovery archive, key, retained image and declared SQL
identities. No cleanup of unused Autobrr SQL objects or shared infrastructure is
included. Finish only after final merge/reconciliation, cleanup verification and
release of the native maintenance owner.

References: [upstream support boundary](https://wiki.servarr.com/prowlarr/postgres-setup),
[native Prowlarr connections](https://github.com/Prowlarr/Prowlarr/blob/v2.6.5.5623/src/NzbDrone.Core/Datastore/ConnectionStringFactory.cs),
[existing enrollment contract](../../../scripts/postgres-enrollment/README.md),
[Autobrr retained pattern](../../../services/media/autobrr/README.md).
