# Media application retained storage

Sonarr and Sonarr-RU, Radarr and Radarr-RU, Lidarr, Cleanuparr, Navidrome,
Audiobookshelf, Shelfmark and Cineplete use independent4GiB static upstream
Proxmox CSI ext4 RWOP/Retain images. Each image is under
`k3s-block:9999/vm-9999-<app>.raw`, independently of worker VM lifecycles.
PV/PVC names are `<app>-config-block` in namespace `media` for claims.
Cleanuparr and Cineplete have since moved to the NFS claims `media/cleanuparr-files`
and `media/cineplete-files` (see the [ordinary-file runbook](ordinary-file-storage.md));
their `vm-9999-<app>.raw` images and `<app>-config-block` claims were
[retired on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16), so those parts of this page are history.
The normal base/variant ApplicationSet cascade and existing verified VM-retirement
handoff reconstruct Kubernetes metadata after a full cluster replacement.
No Velero checkpoint or manual metadata restoration is required.

The NAS dataset quota was raised to256Gi for this cohort; the [CSI README](../../infrastructure/system/proxmox-csi/README.md)
has the current value. Before allocating or growing any
image, recheck dataset GUID, pool health, physical free and every existing raw
image's remaining full growth, staging and spare headroom. A quota is a ceiling,
not reserved physical space or a backup. Never overwrite/recreate an existing
raw image, force detach, or permit two writers to bypass a failed handoff.

Each stock engine starts only after the generic marker guard (`infrastructure/base-configs/files/retained-startup/guard.py`, ConfigMap `retained-startup-guard`) finds its marker: a regular file
`.homelab-<app>-data` on the claim's root holding exactly `homelab/<app>/data/v1`
and a newline (for example `.homelab-sonarr-data`, `.homelab-radarr-ru-data`,
`.homelab-cleanuparr-data`, `.homelab-cineplete-data`). The guard runs read-only as
the app's own user. It checks no native files, formats or versions and never
creates or repairs data. A wrong/absent marker stops startup. Investigate the
retained image and filesystem identity; do not create a marker to bypass the guard.
Keep the pinned application images. Sonarr/Radarr RU overrides retain their own
claim and marker identities.

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
retained in `.legacy-sqlite/` on the `cleanuparr-files` claim, outside active database
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
writer. Before authority the unchanged NFS source could resume only after all
target/helpers retired. After authority, CSI/PostgreSQL contains the newest writes;
the NFS sources no longer exist.

Acceptance requires native state/API preservation, clean Pod recreation, movement
to the other healthy worker and restored ordinary placement on the same retained
filesystem UUID. Reconcile exact desired/live resources and full current-source
Argo operations with all existing sync options, then watch six clean minutes.
Local linting, a ready Pod and an accepted synthetic fixture are separate gates.
Fresh human OIDC sign-ins are not inferred from native health/API checks.

The `media-csi-cutover-20261017` cold recovery ciphertext, manifests and keys on
VM300 and the operator workstation, the cold ZFS snapshots, the original NFS sources
and their admission holds were [deleted on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16). Retained disks and fresh Kubernetes
metadata reconstruction are not ongoing backups. Accepted production, lifecycle, reconciliation and cleanup evidence is recorded in
[the completion report](../superpowers/reports/2026-10-17-media-production-completion.md).
