# NFS durability: fresh identity and backup preflight

Observed September 21, 2026, 15:56–16:20 UTC. This records read-only production
inspection, independent restores, and a temporary archive-transport probe.
No VM power state, workload configuration, snapshot schedule, NFS export, or ZFS
sync property changed. All probes and restore containers were cleaned up.

## Confirmed prerequisites

TrueNAS is still `TrueNAS-25.10.7`. Pool `apps` is healthy/ONLINE with GUID
`9917900421692286909`. Dataset `apps/pv` still has GUID
`14547210392972608779`, no child datasets, and explicit local `sync=DISABLED`.
The reviewed `nfs_sync.py inspect` accepted those identities without policy edits.
The UI certificate came through the authenticated Proxmox guest-agent route;
the NAS client verified its trust anchor and exact SHA-256 leaf before login.
The restored credential file is now mode 0600; secrets are excluded from Git.

The dataset has approximately 368.7 GiB available. The live file tree occupies
approximately 69.0 GiB (allocated bytes, not a predicted compressed archive size).
Snapshots run every six hours, retain one week, and most recently completed
`apps/pv@auto-2026-09-21_18-00` at 15:00 UTC. These are live filesystem snapshots,
not evidence that every application's database can be restored.

Current mapping found 63 claims on `apps/pv` and 52 Deployments/StatefulSets,
including generated StatefulSet claims. All 52 had their requested ready count.
NFS connections observed on TrueNAS came from the three K3s storage IPs.
An idle five-second pool sample saw little activity; its isolated 6 ms read and
1 ms write samples do not establish production latency or predict STANDARD's cost.

The real Ansible deployment after #267 and Terraform's no-change workflow after
#225 both passed their guarded paths and released ownership. These observations
qualify normal workflow execution, not concurrent workflow cancellation or reboot.

## Independent database restores completed

The following existing database-native archives were copied to the encrypted
laptop filesystem under `/home/benf/Backups/homelab/pre-nfs-standard/20260921T1600Z`.
The directory is 0700 and files are 0600. Archives and sanitized restore records
are retained. Test containers and transient restore logs were removed.

| Archive | Created, UTC | Compressed bytes | Restore result |
| --- | --- | ---: | --- |
| Shared PostgreSQL | September 20, 23:21 | 33,143,428 | All nine expected databases, 542 user tables, 658,914 counted rows |
| Immich PostgreSQL | September 20, 23:00 | 50,630,315 | All 71 Immich tables, 319,716 counted rows; vector/vchord extensions loaded |

Both passed gzip integrity, completion-marker checks, full SQL restore with
`ON_ERROR_STOP`, and queries counting every restored user table. Both used the
exact production database image digest, networking disabled, and only a Unix
socket listener. Restore exit codes and warning counts were zero. These counts
come from the archives; they are not comparisons with concurrently changing live
data. These are database restores, not full application/filesystem acceptance.

The Bitnami harness needed an explicit name for UID 1001 and a supported C/UTF-8
locale. The first row-count harness omitted Docker's stdin flag and incorrectly
reported zero tables; that result was rejected. Fresh restores with stdin passed
through and explicit expected table counts produced the results above.

The source archives exceed a 24-hour age at approximately 23:00–23:21 UTC on
September 21, regardless of when they were copied or restored. Refresh them for a
later maintenance window. No complete NFS coverage receipt was issued.

## Remaining coverage

The user selected all remaining application state, retaining earlier exclusions
for Filebrowser's local database and Audiobookshelf. The full `apps/pv` tree will
be copied, including files/attachments as well as databases; Audiobookshelf's NFS
configuration may be included incidentally but is not an acceptance gate.
Filebrowser's worker-local database is outside this dataset.

The bounded archive search found Home Assistant and Bazarr backups older than
24 hours, and Sonarr/Radarr variants, Lidarr, and Prowlarr backups several days
old. No fresh independent Jellyfin archive was found. Many other embedded-DB
services have no restore evidence from this inspection. pgAdmin's old `.bak`,
Calibre processed-book ZIPs, and qBittorrent's live `BT_backup` files are not
accepted as full independent application backups.

The PostgreSQL dump does not preserve Paperless/Mealie/Vaultwarden/Listmonk/etc.
files stored alongside their databases. Copying the full affected tree covers
those on `apps/pv`. Original media on `main/media` is outside this NFS property
change and outside this archive; retain its separate protection. The archive
must not be described as a complete NAS-disaster recovery set. External sealing
key/Vault recovery material remains a separate protected recovery requirement.

## Qualified copy path

An NFSv4.2 read-only mount of an existing snapshot on Proxmox succeeded, but file
reads returned `ESTALE`. The exact test mount was removed; no NFS configuration
was changed to work around it. Do not use that snapshot export path for copying.

The replacement route passed end to end: TrueNAS read an existing snapshot
locally, wrote a private temporary `tar.zst` outside the live export, and served
it through `core.download` / `filesystem.get` over certificate-verified HTTPS.
The laptop checked the whole archive hash, streamed its member, and matched the
member's SHA-256 to the independently checked source backup. Both temporary
archive copies were removed. This was one 33 MB file, not a whole-tree test of
ownership, ACLs, xattrs, hard links, or application recovery.

The [sanitized evidence](evidence/2026-09-21-nfs-backup-preflight.json) contains
exact identities, hashes, restore counts, workload mappings, and limitations.

## Proposed backup-only window

Reserve a 30-minute application-outage window for stop/snapshot/start; this is
scheduling headroom, not a measured recovery guarantee. The ~69 GiB copy and
restore verification run after applications return and may take substantially
longer. This window does not authorize the NFS property update or iSCSI creation.

1. Recheck NAS/dataset identities and free space, all five VM identities, current
   ready replicas, backup destination space, and absence of another operation.
   Acquire the durable VM300 maintenance lock with an exact owner and private
   nonce; journal the plan and current VM states there. Prohibit simultaneous
   manual VM starts/replacements. TrueNAS 100 and runner 300 remain running.
2. Gracefully shut down master 200 first to stop the control plane/Argo from
   scheduling replacement writers, then workers 201 and 202. Require successful
   graceful shutdown and exact stopped-state/UUID readback for all three. Do not
   use forced power-off or delete pods. If a guest fails to stop cleanly, abandon
   the snapshot attempt, recover the recorded original running set, and inspect.
3. Verify the three storage clients have stopped writing and no other client or
   host process is writing this dataset. Take one uniquely named recursive
   `apps/pv@pre-nfs-standard-<UTC>` snapshot. Record its returned identity/GUID and
   creation time. A lost response requires querying that exact name and journal,
   never blindly issuing another create.
4. Start master 200, verify its API/node readiness, then start workers 201/202.
   Verify all three nodes and recorded application replicas recover. Keep the
   operation held if recovery is uncertain. No disks or Terraform settings change.
5. Read only that immutable snapshot locally on TrueNAS. Produce a private,
   low-priority archive under an explicitly owned staging directory on the `apps`
   parent outside `/mnt/apps/pv`, preserving numeric owners, modes, ACLs, xattrs,
   symlinks and hard links and excluding `.zfs` recursion. Check available space
   before starting. Publish only after the archive process, integrity test, file
   fsync, rename and directory fsync succeed. Never overwrite an earlier attempt.
6. Transfer through the qualified pinned-HTTPS route to a new encrypted-home
   backup directory; verify source/received hashes. Fully restore into isolated
   scratch storage, compare per-file contents and metadata, and check every
   discovered SQLite database with its WAL/journal state on the private copy.
   Perform same-image database/plugin recovery checks where file integrity alone
   is insufficient, including Jellyfin's LiteDB/plugin state. Preserve the original
   archive unchanged. Do not issue a passed receipt for untested services.
7. Record complete per-application coverage and actual restore outcomes, resolve
   any failure before approving the durability update, and release maintenance
   ownership only after the window's operation is reconciled. Clean up only exact
   task-owned temporary files; retain the cold snapshot and independent archive.

Approved VM identities to recheck before any power action:

| VM | Name | SMBIOS UUID |
| --- | --- | --- |
| 100 | truenas | e6895d73-d782-46fb-951c-2f88405a14d8 |
| 200 | kube-master-01 | 459b5ce3-d527-4edb-9617-206b50476a3f |
| 201 | kube-worker-01 | 8b2aa6c7-b54f-4323-9900-bdbb85098f62 |
| 202 | kube-worker-02 | d6c40da9-aaa5-4b5c-a9ce-70d3cfdcc4b4 |
| 300 | runner | cc1aeeb7-4827-466c-9d4b-5dc6c881f193 |

The user subsequently approved the backup-only outage. Execution and restore
results are tracked in the [cold-backup report](2026-09-21-cold-backup-window.md).
