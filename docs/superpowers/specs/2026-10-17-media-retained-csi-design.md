# Media application retained CSI migration

User authority: autonomously migrate Sonarr and RU, Radarr and RU, Lidarr,
Cleanuparr, Navidrome, Audiobookshelf, Shelfmark and Cineplete; pause for genuine
decisions, missing access or an actual approval-review rejection. Reuse the
unmodified upstream Proxmox CSI and existing verified retirement/rebuild design.

## Outcome

Move private application state from NFS to deterministic ext4 RWOP/Retain images
in k3s-block under VMID9999. Preserve exact pinned images, application identities,
credentials, settings, users, libraries, progress and history. Keep shared media,
download paths and Shelfmark's shared book ingest on existing NFS. No application
upgrade, new storage controller or infrastructure credentials in application labs.
The user selected Cleanuparr's pinned2.10.6 native PostgreSQL conversion, separately
rehearsed and verified across data/events/users, using existing declarative enrollment.

Each image is4GiB, exceeding the measured largest private tree of0.79GiB.
Cineplete's image contains config/ and data/ subdirectories preserving both old
claims. Audiobookshelf contains config/ and metadata/: its current container-only
metadata has34 small log files and empty cache/backup/stream directories, with
no custom cover or author images. Capture those logs before deleting the source
Pod and persist metadata from now on. Normal shutdown/startup logs may append;
settings and database acceptance are exact cold-copy/native checks.

A read-only init guard checks the application identity marker and required native
paths/SQLite headers before stock startup. It neither opens SQLite nor repairs
state. Use the actual app UID/GID:1000 for Servarr/Shelfmark/Cleanuparr, root for
Navidrome/Audiobookshelf/Cineplete. Preserve stock process identities. Keep one
writer, Recreate deployment, no init API token, fixed worker placement, cache none,
and permanent admission protection on held NFS source claims. RU variants use
minimal valuesOverride layers preserving baseApp inheritance.

## Preservation and execution

Inventory current app/Pod/VM/storage identities and all overlapping writers.
Acquire the installed immutable native maintenance owner/execution lock, record
before-intents and exact child terminals, never replay uncertain phases. Hold only
owning Argo Applications and overlapping Filebrowser/NFS provisioner. Retain old
claims/PVs before stopping each source. Verify API, CRI, kernel mounts and physical
attachment retirement; no forced detach or unreachable-node inference.

Serialize each scoped outage. Take an immutable native NAS snapshot; archive all
private regular files/directories, hardlinks and POSIX ownership/mode/mtime; reject
unhandled xattrs/specials. Source files stay unchanged. Preserve source-held
snapshots and accepted targets. Keep AES256 encrypted complete recovery bundles
on VM300 and this computer, keys separately outside Git. Private application data
and app credentials stay0700/0600; infrastructure/admin credentials never enter
fixtures. Native production credentials remain native. Qualify every file/POSIX
restore and SQLite integrity/table content before using exact stock-image offline
fixtures. Fixtures have no network destinations or production media; postpone
background scan/cleanup tasks only in disposable copies to avoid interpreting
absent media as deletion. Original cold archives and target data are unmodified.

Recheck complete raw-image growth reservations and pool physical free before
quota192Gi to256Gi and the fixed40Gi maximum allocation. Preserve unrelated raw
images, the protected Jellyfin partial image, datasets, snapshots and recovery.
No disk creation before capacity acceptance; no target writer before original
source recovery and single-writer/physical fencing acceptance. Merge reviewed
Git definitions under the owned Argo hold with exact-head CI and intended-only
Argo diff. Unexpected rebuild of an unpopulated image fails closed at the guard.

Pre-authority rollback can resume unchanged source only after every target/helper
writer is retired. After authority, target contains newest writes: never resume
stale NFS. Accept unchanged settings and native read-only APIs, clean recreation,
healthy-worker movement and restored default placement on the same FSUUID/WWN.
Restore ancestor services promptly after cold capture. Reconcile final desired
Git, retire held operations preserving all syncOptions, release only owned holds
and continuously watch all scoped workload/Pod generations for six clean minutes.
Encrypt audit, clean only exact owned plaintext/labs/helpers and release owner
last; retain cold recovery and separate keys. Publish sanitized recovery/report.

## Boundaries and evidence

No production downloads, scans, notifications, password resets or new auth tokens
are needed for acceptance. Native read-only API/DB proofs are distinct from a
fresh human OIDC login. No per-app admission loss exception or malformed-text
waiver is inherited from older migrations. Stop for a genuine preservation issue.
Primary contracts and measured facts are in the assessment report. Local tests,
hosted CI, cold recovery and actual live rollout are separate evidence gates.
