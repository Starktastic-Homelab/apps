# PostgreSQL retained-CSI preparation and cutover

Status: **inactive preparation**. The production server still uses its retained
NFS claim. The files in
[`scripts/postgres-retained-startup/production/`](../../scripts/postgres-retained-startup/production/)
are outside both ApplicationSet discovery paths. Merging this preparation does
not allocate an image, apply storage objects, change the server, copy data or
activate the guard. It is not an execution authorization or a performed restore.

## Prepared destination and current source

| Property | Prepared value |
|---|---|
| Namespace / PVC / PV | `databases` / `postgres-data-block` / `postgres-data-block` |
| Image owner | Reserved external owner `9999`, outside disposable VM lifecycle |
| Image | `k3s-block:9999/vm-9999-postgres.raw` |
| CSI handle | `homelab//k3s-block/9999/vm-9999-postgres.raw` |
| Capacity / filesystem | 16GiB / ext4 |
| Binding / lifecycle | Bidirectional prebinding without claim UID, RWOP, Retain, Argo prune/delete protection |
| Storage / cache / topology | `k3s-block` / `none` / region `homelab`, zone `pve` |
| Physical PostgreSQL identity | `7584099661242523698`, PG18.6 primary |

The source claim is `databases/data-postgres-postgresql-0`, UID
`13cb5e92-ca6d-4e37-aa39-e421b680797b`. Its PV UID is
`df5ba50f-ea7b-4b46-b822-ed617d63337c`, Retain, at
`10.9.8.30:/mnt/apps/pv/databases/data-postgres-postgresql-0`.
The current Pod UID is `a215fa64-dde0-4762-a256-d7c967393791`.
Refresh these identities and every source consumer before execution.

The October11 read-only scan reported about254MiB allocated for the complete
mounted tree, 438MiB of logical database sizes including templates, and192MiB of
WAL files. Only the built-in tablespaces were present; no symlinks were reported.
The data directory was1001:1001/0700. These are live planning measurements,
not an archive manifest or proof of stopped writers.

The block dataset `apps/k3s-block`, GUID `13918781591004512447`, had128GiB quota.
The published Jellyfin64GiB and Filebrowser4GiB images plus this16GiB destination
would total84GiB nominal capacity. Before allocation, check complete dataset and
pool usage, snapshots, hidden preserved files, staging/backup needs and full
remaining growth of existing images; leave at least4GiB immediate headroom beyond
the new image. Quota and PVC capacity do not reserve free space. The proposed
name was absent and owner9999 was unused as a VM; recheck both, refuse collisions,
and preserve historical Jellyfin files.

## Guard and chart integration

The [qualified guard](../../scripts/postgres-retained-startup/README.md) is copied
byte-for-byte into `production/guard-configmap.yaml`. The final overlay binds its
expected ID to the same canonical physical server as enrollment. It runs the
guard as1001 with read-only data before the unmodified pinned Bitnami entrypoint,
replaces the unconditional PID-removal init, and disables volumePermissions and
fsGroup handling. A populated target must already be accessible to1001.

The overlay uses an explicit existing claim, Linux workers and indefinite
not-ready/unreachable NoExecute tolerations. It preserves the server/exporter
containers, credentials, resource limits and PostgreSQL configuration. It does
not initialize data or replace CSI's accepted upstream format/repair behavior.
Single-writer safety comes from RWOP, verified VM retirement and the existing
rebuild cohort policy; the guard and a missing PID file are not fencing.

At separately approved activation, publish the PV/PVC and guard ConfigMap into
reviewed Application-owned locations and merge the overlay into the actual
PostgreSQL values. Arrays replace existing arrays: check every init and volume.
Changing a StatefulSet from volumeClaimTemplates to existingClaim changes
immutable fields. Prepare an explicit controller replacement while replicas
are held at zero, preserving the source PVC, rather than expecting an ordinary
Helm/Argo patch to perform the switch. Verify no old Pod remains.

To inspect the prepared render locally:

```sh
helm template postgres oci://registry-1.docker.io/bitnamicharts/postgresql \
  --version 18.12.4 --namespace databases -f templates/globals.yaml \
  -f infrastructure/controllers/databases/postgres/values.yaml \
  -f scripts/postgres-retained-startup/production/values.yaml > /tmp/postgres-csi-preparation.yaml
```

CI renders baseline, generic guard and production guard overlays, checks static
bindings and exact embedded source, and compares the actual production-overlay
containers to baseline. These checks establish source preparation only.

## Required run-specific approval

Before downtime, prepare a concrete operation manifest on verified VM300:
exact source and target identities, all PostgreSQL clients/jobs and their writer
holds, maintenance/release PRs, source admission guard and protection, guest
IDs/UUIDs, image allocation and copy commands, encrypted off-NAS paths and
recoverable recipient, independent restore procedure, cleanup list, downtime
window and rollback authority. Verify runtime hashes, boot, ownership and receipts.
Use the identified maintenance VM for privileged execution. Any new transfer of
credentials or recovery keys requires explicit scope approval; production CSI
or Proxmox administrator credentials must not enter the restore guest.

The existing `pg-backup` CronJob last succeeded at2026-10-10T23:00:15Z during this
preflight, but stores its dump on the same NAS. Success alone establishes neither
off-NAS recoverability nor an independently restored backup. Recheck backup
health, and qualify an encrypted off-NAS whole-cluster physical restore before
releasing the destination. Retain the accepted backup and the original NFS tree.

## Later maintenance, copy and release sequence

This sequence is a contract for the future reviewed operation, not a runnable
maintenance change in this preparation PR.

1. Review full source consumer inventory and private semantic baselines. Include
   all eight existing database consumers, the pilot, scheduled/manual backup
   Jobs and any administrative or enrollment clients. Autobrr still uses SQLite
   and does not consume its prepared database. Capture database/role identities,
   grants, memberships, extensions, physical ID, both ready ledger entries and
   the fixed pilot sentinel without publishing application records or secrets.
2. Reconcile an approved maintenance PR that holds affected consumers and the
   pilot at zero, suspends backup scheduling and holds PostgreSQL at zero. Omit
   the enrollment Sync Job from that temporary desired state while the server
   is stopped; preserve its canonical config, scripts and credentials. Otherwise
   a full sync would start a hook against an unavailable server. Verify all
   active Jobs have ended, source PVC/PV protection is effective, and the reviewed
   admission guard blocks new Pods using the old claim. A live scale command
   alone is not a durable hold against GitOps reconciliation.
3. Verify clean PostgreSQL shutdown, no old writer or mount, and the source files
   match the expected physical server. Cold-archive the **complete mounted tree**,
   including PGDATA and WAL, with numeric ownership, modes, ACLs and xattrs. Reject
   unexpected external tablespaces/symlinks until explicitly covered. Record
   private file-content/metadata manifests and archive hashes; encrypt, transfer
   outside the NAS failure domain, decrypt/readback verify, and retain receipts.
4. Independently restore that archive on the exact approved disposable guest,
   isolated from production clients and shares. Verify byte/metadata equality
   before startup, use the same pinned PG18.6 image, and prove the same physical
   ID, catalog, extensions, ledger, sentinel and private semantic baselines after
   startup. Any local authentication fixture changes only the disposable copy
   and must be explicit in the approved procedure. Never initialize over a
   failed restore, silently adopt a new ID, or use production controller tokens.
5. Allocate the new16GiB image through the qualified native Proxmox mechanism,
   only after fresh name/owner/quota checks. Verify returned volume ID, regular
   file and byte size. Stock CSI may format this specifically approved blank
   image. Use one approved helper to populate the filesystem while the server
   remains held. Verify all source content and metadata, physical ID and1001
   access before startup; reject partial copies or unknown writer state.
6. Stop the helper, verify clean unmount/detach and termination, and record the
   target volume identity, filesystem UUID, size and populated-data receipt.
   Keep source and consumers held. Apply the reviewed StatefulSet replacement
   and target binding; start one server on the verified block claim while
   consumers remain held. Verify sole attachment, guarded startup, original
   physical ID/catalog and server health. No source writer may coexist.
7. Restore the generation-specific enrollment Job in desired state and run a
   full native PostgreSQL Application hook against the healthy retained server.
   Verify both canonical logins, unchanged established objects and ready ledger,
   then repeat full sync. Restore the pilot and validate its ordered gates and
   existing sentinel. Release existing consumers through the reviewed PR only
   after database/restore acceptance; verify their application behavior and
   readiness, not merely SQL or Argo status. Preserve all existing credentials.
8. Verify clean server Pod recreation and movement between healthy workers using
   approved fencing. Retain the old-source admission guard and protected source,
   accepted encrypted backup and root-only immutable receipts. Remove only
   recorded temporary helpers, guest resources and private copies, independently
   verify absence, and release only the original maintenance owner. A production
   cluster destroy/rebuild is not included; use the qualified lab evidence for
   that lifecycle rather than claiming an unperformed production test.

This pauses PostgreSQL and its consumers, including Authentik. Confirm management
access that does not depend on their availability before the downtime window.
The copy is small; restore verification, fencing and application acceptance
dominate the window. Rehearse and agree the actual window in the execution plan.

## Rollback, rebuild and growth

Before any new target writes, return to the source only after verified target
shutdown/detach and a reviewed withdrawal of the protected source admission
guard, then restore source binding/controller and consumer desired state. Startup,
hooks, pilot and clients can all write: once any of those starts, the old NFS copy
must be treated as stale. After target writes, rollback requires another stopped
writer backup and verified reverse copy/restore of the newest state. A Git revert
alone must remain blocked from reopening the stale source.

Ordinary rebuilds keep the Packer/Terraform/Ansible flow: static Git binding
reattaches retained data, verified retirement excludes old VM writers, and a
control-plane replacement replaces the whole k3s cohort. No Velero checkpoint
or per-rebuild copy is added. Missing/wrong data blocks startup. A separately
approved logical restore that creates a new physical server requires reviewed
guard and enrollment identity changes; it is not ordinary retained-disk recovery.

Growth follows PVC request, verified backend/filesystem expansion, then Git PV
capacity reconciliation. Keep the accepted storage-fault manual fencing procedure
from the [CSI runbook](../../infrastructure/system/proxmox-csi/README.md).
Recurring off-NAS backup policy, archived-source retirement, legacy enrollment
adoption and application conversion remain separate decisions.
