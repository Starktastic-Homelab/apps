# Media application retained storage

Sonarr and Sonarr-RU, Radarr and Radarr-RU, Lidarr, Cleanuparr, Navidrome,
Audiobookshelf, Shelfmark and Cineplete use independent4GiB static upstream
Proxmox CSI ext4 RWOP/Retain images. Each image is under
`k3s-block:9999/vm-9999-<app>.raw`, independently of worker VM lifecycles.
PV/PVC names are `<app>-config-block` in namespace `media` for claims.
The normal base/variant ApplicationSet cascade and existing verified VM-retirement
handoff reconstruct Kubernetes metadata after a full cluster replacement.
No Velero checkpoint or manual metadata restoration is required.

The NAS dataset quota is256Gi after this cohort. Before allocating or growing any
image, recheck dataset GUID, pool health, physical free and every existing raw
image's remaining full growth, staging and spare headroom. A quota is a ceiling,
not reserved physical space or a backup. Never overwrite/recreate an existing
raw image, force detach, or permit two writers to bypass a failed handoff.

Each stock engine starts only after a read-only guard validates its exact marker
and required native state, without opening SQLite, repairing a filesystem or
creating missing data. A wrong/absent marker or missing database stops startup.
Investigate the retained image and filesystem identity; do not create a marker or
an empty database to bypass the guard. Keep the pinned application images.
Sonarr/Radarr RU overrides retain their own claim and marker identities.

Cineplete retains both former claims under `config/` and `data/` on its image.
Audiobookshelf retains config/database under `config/` and its formerly
container-only metadata under `metadata/`; future metadata now survives Pod/VM
replacement. The source metadata consisted of logs and empty directories; the
cold operation captured it before retiring the old Pod. Ordinary shutdown and
startup log appends are outside that pre-stop metadata capture.
Shared media, downloads and Shelfmark book ingest continue to use their existing
NFS interfaces. Private database/config/key state moves to CSI.

Cleanuparr2.10.6 uses PostgreSQL with schemas `data`, `events`, `users` and its
existing dedicated-role enrollment/completion gate. Retained config preserves
JWT, Plex client identity and DataProtection keys. The original SQLite files are
retained in `.legacy-sqlite/` on CSI and in cold recovery, outside active database
paths; startup rejects active SQLite files to prevent silent fallback. Do not
run the native converter against preserved sources: it applies SQLite migrations
in place. Use only disposable copies and an independently verified empty
dedicated PostgreSQL target, never `--force`. Require every application table,
column and row to match, plus native PostgreSQL startup, before authority.
PostgreSQL's ordinary retained storage and backup procedure remains in
[the PostgreSQL runbook](postgresql-storage.md).

Migration is serialized under the existing native maintenance owner and a scoped
Argo hold. Stop the app and every source/ancestor writer, verify API/runtime/
mount retirement, snapshot and protect a complete cold archive, then independently
decrypt, restore and validate all files, POSIX metadata and native data. Offline
fixtures use only disposable copies and no production network/media. Disable or
postpone their background work; fixture changes never populate production.
Populate only a verified empty target, proving every file before the marker.
Merge reviewed desired definitions under the hold before permitting a target
writer. Before authority the unchanged NFS source may resume only after all
target/helpers retire. After authority, CSI/PostgreSQL contains the newest writes:
never resume stale NFS.

Acceptance requires native state/API preservation, clean Pod recreation, movement
to the other healthy worker and restored ordinary placement on the same retained
filesystem UUID. Reconcile exact desired/live resources and full current-source
Argo operations with all existing sync options, then watch six clean minutes.
Local linting, a ready Pod and an accepted synthetic fixture are separate gates.
Fresh human OIDC sign-ins are not inferred from native health/API checks.

Cold recovery ciphertext and manifests are retained outside Git on VM300 under
`/var/lib/homelab-maintenance/operations/media-csi-cutover-20261017/recovery/`
and on the operator computer under
`~/.local/share/homelab-recovery/media-csi-cutover-20261017/`.
Keys remain separate in the VM300 operation's `keys/` directory and
`~/.config/homelab-recovery-keys/media-csi-cutover-20261017/` on the computer.
Retain the original NFS sources and per-app `apps/pv` cold snapshots, independent
of cleanup of owned helpers/private staging. Verify hashes and independently
restore before relying on a recovery copy. These are point-in-time recovery
copies; retained disks and fresh Kubernetes metadata reconstruction are not
ongoing backups. Accepted production, lifecycle, reconciliation and cleanup evidence is recorded in
[the completion report](../superpowers/reports/2026-10-17-media-production-completion.md).
