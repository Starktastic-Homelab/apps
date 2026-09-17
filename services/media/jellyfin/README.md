# Jellyfin 12 upgrade

Production was upgraded from **10.11.11 to 12.1** on September 17, 2026.
The canonical `Authorization: MediaBrowser Token="..."` headers, Homepage widget
`version: 2`, and body-aware readiness probe remain in place and work with both
versions. This runbook retains the upgrade safeguards and rollback checkpoint.

## Why this needs a maintenance window

Jellyfin removed the constant `10.` version prefix: 12.0 is what would previously
have been called 10.12.0. It still introduces database migrations, .NET 10/plugin
changes, removal of `/emby` routes, disabled legacy authentication, and FFmpeg 8.
The LinuxServer image's Ubuntu 26.04 base is unchanged.
After migration, a full library scan is required to rebuild alternate versions.

At the September 16, 2026 review, 12.1 had open, data-dependent reports involving
[migration stalls](https://github.com/jellyfin/jellyfin/issues/18066),
[malformed-GUID migration failures](https://github.com/jellyfin/jellyfin/issues/18050),
and [scan memory growth](https://github.com/jellyfin/jellyfin/issues/18086).
These do not prove this installation will fail; they do make a rehearsal important.

## Preflight

1. Deploy the compatibility preparation on 10.11.11 first. Verify both Homepage
   widgets, LDAP library-policy synchronization, and Bazarr subtitle refreshes.
2. Verify a working **built-in administrator login**, independent of LDAP.
   Inventory installed plugins and confirm 12-compatible replacements. Official
   LDAP Authentication **v24** targets Jellyfin 12; test it against Authentik rather
   than assuming the current plugin binary is compatible.
3. Resolve usernames that differ only by capitalization before migration. Record
   library/collection counts, user access, GPU/transcoding settings, database size,
   available disk space and worker memory headroom.
4. Confirm the actual backup and restore destination. This repository's PostgreSQL
   and certificate backup jobs **do not back up Jellyfin**.

`jellyfin-config` mounts at `/config` on NFS. Its expected provisioner path is
`/mnt/apps/pv/media/jellyfin-config`; confirm the bound PV before filesystem work.
The separate node-local `/config/cache` volume does **not** move the database off
NFS. Jellyfin recommends local database storage; treat the existing NFS placement
as a migration risk, not something silently changed alongside the image.

### Preserve transcoding settings

Jellyfin 12 changed `EncoderPreset` from nullable to non-nullable. An old
`<EncoderPreset xsi:nil="true" />` or empty preset can make it reject and overwrite
the **entire `encoding.xml` with defaults**
([jellyfin/jellyfin#17861](https://github.com/jellyfin/jellyfin/issues/17861)).
The server can still report `Healthy` while VA-API, tone mapping, HEVC, and
low-power hardware encoders have been disabled.

Before the production upgrade, explicitly save the encoder preset as **Auto**
while still on 10.11.11. Use the dashboard or retrieve the complete
`GET /System/Configuration/encoding` object, set only `EncoderPreset` to `"auto"`,
and send it back with `POST /System/Configuration/encoding`. Never POST only the
single field: omitted options can reset other settings. Verify the saved XML
contains `<EncoderPreset>auto</EncoderPreset>` without `xsi:nil`, preserve all
other encoding options, and include that configuration in the cold backup.

If the maintenance hold has already stopped Jellyfin, take the untouched cold
backup first, then normalize the nil/empty preset in production's **working
volume**, not in the backup, before starting 12. Keep the backup unchanged.
Do not restart against a nil preset or try to recover lost settings from defaults.

If 12 has already reset a configuration, changing its preset alone cannot recover
lost settings. Restore the complete original encoding options from the pre-upgrade
copy through the supported API, normalize the preset, retain new 12-specific
defaults, and verify persistence after restart.

## Completed rehearsal and retirement

The isolated 12.1 rehearsal used a private configuration copy on worker-02,
read-only media, disposable cache, and bounded resources without production
ingress, discovery, or LDAP policy synchronization. Migration, compatible
add-ons, user access, the full scan, and hardware playback were verified before
the production cutover.

The temporary GitOps app, snapshot-specific restore helper, and rehearsal-only
CI check are retired after production acceptance. Their implementation remains
in Git history; do not blindly reuse its old fixed snapshot and destination.
The permanent compatibility checks remain enabled.

Removing the app lets ArgoCD delete its owned runtime resources and PVC.
The NFS PV has **Retain** policy, so this GitOps-only cleanup does not delete
`/mnt/apps/pv/media/jellyfin-rehearsal` or its retained PV
`pvc-b26fa377-ee5f-441c-827e-882fbccfd445`. The old live rehearsal snapshot
`apps/pv@jellyfin-rehearsal-20260916-359cdcb9` is also retained. Deleting those
requires separate approval after confirming the rehearsal pod is gone.
Snapshot references can retain blocks even after a directory is deleted.

NFS snapshot exposure is unavailable on this TrueNAS installation: the `.zfs`
snapshot directories appear empty to NFS clients. Restore **on the NAS itself**,
not through an NFS snapshot mount. Future rehearsals must use an empty private
destination, preserve ownership and permissions, validate the restored databases
including WAL state, and refuse to start from an incomplete copy.

Kodi Sync Queue's `kodisyncqueue.db` and `kodisyncqueue-log.db` use
[LiteDB, not SQLite](https://github.com/jellyfin/jellyfin-plugin-kodisyncqueue/blob/v15/Jellyfin.Plugin.KodiSyncQueue/Data/DbRepo.cs).
Preserve both files; SQLite checks cannot validate them. Require successful
plugin startup and a real Kodi sync request after installing a compatible build.
A live snapshot remains crash-consistent and does not replace the fresh cold
checkpoint required before production migration.

## Compatible add-ons

These stable 12.1 builds were verified in the rehearsal and installed in
production. Do not install them into 10.11.11:

| Add-on | Installed on 10.11.11 | Replacement for 12.1 |
|---|---|---|
| AniDB | 11 | [13](https://github.com/jellyfin/jellyfin-plugin-anidb/releases/tag/v13) |
| AniList | 13 | [15](https://github.com/jellyfin/jellyfin-plugin-anilist/releases/tag/v15) |
| Fanart | 14 | [15](https://github.com/jellyfin/jellyfin-plugin-fanart/releases/tag/v15) |
| File Transformation | 3.0.1.0 | [3.0.1.0, `Release-12.1.0.zip`](https://github.com/IAmParadox27/jellyfin-plugin-file-transformation/releases/download/3.0.1.0/Release-12.1.0.zip) |
| Intro Skipper | 1.10.11.24 | [12.0.4.0](https://github.com/intro-skipper/intro-skipper/releases/tag/12.0/v12.0.4.0) |
| Kodi Sync Queue | 15 | [16](https://github.com/jellyfin/jellyfin-plugin-kodisyncqueue/releases/tag/v16) |
| LDAP-Auth | 23 | [24](https://github.com/jellyfin/jellyfin-plugin-ldapauth/releases/tag/v24) |
| Playback Reporting | 17 | [19](https://github.com/jellyfin/jellyfin-plugin-playbackreporting/releases/tag/v19) |

File Transformation needs a different binary despite the unchanged version
number; load it before enabling Intro Skipper's optional web enhancements.
The Intro Skipper feed selects its manifest using Jellyfin's server version.

Check local and LDAP administrator access, ordinary-user library restrictions,
full-scan results, direct play, forced VA-API transcoding, HDR tone mapping,
subtitles, seeking, and the clients actually used. Record peak memory, not just
idle usage; the production cache pins Jellyfin to worker-01, so check that node's
headroom rather than extrapolating from a rehearsal worker.

## Controlled production upgrade

The temporary maintenance state retains the 10.11.11 image and all storage,
but sets production to zero replicas and suspends LDAP policy synchronization.
Merging that maintenance change starts the outage; simply preparing the PR does
not change the running service.

1. Through GitOps, suspend `jellyfin-ldap-library-sync` with `spec.suspend: true`
   and stop Jellyfin with `controllers.main.replicas: 0`. Wait for existing
   writers and the pod to terminate: suspending a CronJob does not cancel an
   already-running Job. Confirm no active LDAP-sync Job remains. Do not rely on
   live scaling that reconciliation can undo.
2. With Jellyfin stopped, back up the **complete `/config` volume**, including
   configuration, databases, metadata, plugin binaries and plugin configuration.
   Preserve ownership/permissions and keep an untouched copy outside that PVC.
   The separate disposable cache need not be copied. If using a snapshot of a
   shared NAS dataset, restore/clone only Jellyfin's directory, not every app.
3. Only after the isolated rehearsal succeeds and the fresh cold backup is
   secured, normalize the encoder preset if needed and remove installed add-on
   binaries before starting the pinned 12.1 image. Keep the complete original
   plugin state in the backup, retain plugin configurations, and reinstall the
   matching 12.1 builds afterward. An image-only dependency PR does **not** release
   the zero-replica hold. Once backup and configuration/plugin preparation are
   verified, remove `replicas: 0` (or set it to `1`) through a separate GitOps
   change to start the reviewed image. Keep the LDAP CronJob suspended.
4. Require completed migration logs and `/health` body **`Healthy`**, not merely
   HTTP 200 or a new `/System/Info/Public` version. The temporary startup server
   can report `Degraded` with HTTP 200. Readiness checks the body; startup and
   liveness intentionally remain HTTP checks so a responsive migration can continue.
5. Reinstall compatible plugins, then run a full library scan. Allow additional
   time and monitor memory/disk use. Check library access for a local administrator,
   an LDAP administrator and a normal LDAP user; verify both dashboards, Bazarr
   refreshes, direct play, forced Intel QSV/VA-API transcoding, HDR tone mapping,
   subtitles, seeking and the clients actually used.
6. Keep policy synchronization suspended until authentication and library access
   are verified, then remove the maintenance overrides through GitOps. Do not
   replace production's data volume with the disposable rehearsal copy.

### Verified checkpoint for the 12.1 cutover

The cold rollback snapshot is
`apps/pv@jellyfin-pre12-cold-20260917T061613Z-359cdcb9`. It preserves the complete
production configuration and original 10.11.11 plugin state; its SQLite databases
and WAL were checked on independent temporary restores.

Before migration, production's working copy received an explicit `auto` encoder
preset and its old add-ons were archived at `/config/data/plugins-before-12`,
retaining plugin configurations without changing the database files.
Production now runs the reviewed 12.1 image with all compatible add-ons active.
Local/LDAP administrator access, ordinary-user library restrictions, and playback
were verified before LDAP synchronization resumed. Keep the untouched cold
snapshot and old plugin archive.

During the first production full scan, a SQLite `database is locked` timeout
interrupted a playback-progress write. Library requests returned to normal after the scan.
The database remains on NFS; concurrent scans and playback remain a contention
risk, and moving database storage should be handled separately from this upgrade.

## Rollback

Stop Jellyfin and keep writers suspended. Restore the **complete pre-upgrade
configuration/data/plugin state into a clean destination**, then restore the
matching old image pin through Git. Do not overlay old files onto migrated data,
or start 10.11.11 against a database already migrated by 12.

Reverting only the image is **not** rollback. The compatibility preparation can
remain in place because it also supports 10.11.11. Resume writers only after the
restored instance and authentication are verified.

## Checks and upstream guidance

Run `python3 scripts/check-jellyfin-compat.py` and
`python3 scripts/check-homepage-coverage.py` from the repository root with the
existing Helm/PyYAML tooling and `curl`. These checks protect the repository
configuration; they do not replace a database restore/migration rehearsal.

- [Jellyfin 12 announcement and updating instructions](https://jellyfin.org/posts/jellyfin-release-12.0/)
- [Jellyfin backup and restore](https://jellyfin.org/docs/general/administration/backup-and-restore/)
- [Jellyfin storage guidance](https://jellyfin.org/docs/general/administration/storage/)
- [LDAP Authentication v24](https://github.com/jellyfin/jellyfin-plugin-ldapauth/releases/tag/v24)
- [Homepage Jellyfin widget](https://gethomepage.dev/widgets/services/jellyfin/)
