# Immich PostgreSQL retained storage

Status: active on retained CSI since 19 October 2026, after Redis completed its
separate acceptance and ownership release. See the
[production acceptance report](../superpowers/reports/2026-10-19-redis-immich-production.md).

## Normal operation and rebuilds

Only the dedicated PostgreSQL17 data directory moves to the static10GiB ext4
RWOP/Retain image owned by9999 through stock Proxmox CSI. Its VectorChord/pgvector
packaging, physical database identity, credentials and endpoint stay the same.
Photos/videos remain at the existing `immich` subpath on NFS; the model cache and
Immich server/ML images stay unchanged.

Normal Terraform/Ansible cluster rebuilds reuse the retained image. A read-only
init guard validates PG17, its control-file CRC, exact physical system identifier,
required native data, and refuses standby/recovery signals and wrong/empty
storage. Stock PID/WAL handling is accepted only under the selected RWOP and VM
retirement fencing. There is no BusyBox PID-deletion init or recursive fsGroup
ownership rewrite. A missing or invalid image blocks startup.

## Coordinated one-time checkpoint

The approved strategy pauses all 21 workloads with overlapping writable mounts:
Immich-main, Filebrowser, Audiobookshelf, Bazarr, cross-seed, Jellyfin, Lidarr,
Lingarr, MeTube, Navidrome, both qbit-manage instances, both qBittorrent instances,
both Radarr instances, Shelfmark, both Sonarr instances, subgen and Unpackerr.
The NFS provisioner is an additional source ancestor. Refresh the actual writer,
client and mount census; an unknown writer blocks the checkpoint.

This describes the completed migration, not a command to repeat during rebuilds.
The private audit retains original sources, qualified operator amendments,
immutable inputs and native outcomes. Historical approvals and expired clocks
cannot authorize a new operation. The completed sequence was:

1. Hold Argo and external Immich requests; pause/drain native jobs. Retire
   Immich-main, the other20 writable-mount workloads and source ancestors from
   every native node. Keep PostgreSQL running for the export.
2. Prove no external tablespace or WAL path; export native database/role/schema/
   extension/sequence/record proofs and independent logical recovery artifacts.
   Gracefully stop PostgreSQL and prove native writer/mount retirement.
3. Take immutable, identity-bound snapshots of both `apps/pv` and `main/media`
   while all overlapping writers remain stopped. Confirm both generations.
   **Resume the 19 unrelated media workloads immediately after this barrier.**
   Immich-main stays stopped. Filebrowser and the NFS provisioner resume after
   the cold database archive and independent recovery are secured.
4. Archive only the database subtree with complete POSIX metadata. Encrypt and
   retain copies on VM300 and this computer, with separate keys outside Git.
   Independently decrypt the second copy, prove a clean native PG control state,
   restore the physical cluster with its original identity and separately restore
   all logical artifacts into a newly initialized disposable cluster. Compare
   complete data/schema/roles/extensions/sequences in both recoveries.
5. Allocate/populate the exact retained image once. Preserve all bytes, UID/GID,
   modes, timestamps, hardlinks, ACLs and xattrs; marker last. Verify prebinding,
   raw generation, attachment-specific WWN, ext4 UUID and all-helper retirement
   before authority.
6. Merge only the tested activation head while Argo remains held; start only the
   database. Compare native state before any Immich consumer starts. Prove Pod
   recreation, healthy-worker movement and restored normal placement with the
   same database identity and filesystem UUID.
7. Resume Immich-main and its original queue flags, restore frontends, synchronize
   full current Git revision vectors and watch normal automation for six minutes.
   Recheck an existing original photo through its real API and checksum. The
   temporary read-only API key stays on this computer; no original file is saved.
8. Clean exact temporary helpers/plaintext, retain source/target/snapshots and
   encrypted recovery with separate keys, audit and release native ownership.

The `main/media` snapshot may retain blocks changed elsewhere in that dataset.
It is not a full46TB copy. Snapshots on separate pools form a coordinated barrier
because writers are stopped until both are confirmed; they are not claimed to be
one atomic cross-pool transaction.

WWN follows the current VM SCSI slot. Match each attachment to its guest device;
keep the raw image generation, CSI handle, PV/PVC identities and filesystem UUID
fixed. The completed worker-movement test required one approved additional
Lingarr pause because worker02 had reached its 24-volume limit. Lingarr resumed
with its original replica count and placement policy and the same retained disk.
The driver limit is unchanged; check attachment capacity before future moves.

The independent logical recovery restored complete native sequence definitions,
including type and bounds, before requiring the original full schema/data proof.
It did not lower sequence floors or relax schema equality. Physical recovery
preserved the original PostgreSQL system identifier.

## Failure and recovery

Inspect unknown native outcomes instead of retrying mutations. Continue with the
original input, nonce, clocks, exact resource generations and known terminals.
Never renew the approved pre-target or total windows implicitly.

Before authority, source recovery still requires complete target retirement and a
validated coordinated database/photo recovery point. Before allowing uploads,
keep Immich down until database and original-asset consistency is established.
A snapshot-only restoration must affect only Immich's subtree; **never roll back
all of `main/media`**, because the 19 resumed workloads may have written new data
after the checkpoint barrier. Keep both snapshot generations and use a separately
reviewed subtree recovery when needed.

After authority, CSI is the database authority. Never reopen the retired NFS
cluster or remove its permanent Pod admission hold as an ad-hoc workaround. Fence
all current target writers, preserve the current image, and recover through a
validated current coordinated backup. No forced detach or empty initialization.
The original NFS PVC/PV/data and both checkpoint snapshots remain retained until
the user separately approves their removal.
