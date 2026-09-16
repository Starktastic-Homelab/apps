# Jellyfin 12 upgrade

The compatibility preparation keeps Jellyfin on **10.11.11**. Its canonical
`Authorization: MediaBrowser Token="..."` headers, Homepage widget `version: 2`,
and body-aware readiness probe work with both 10.11.11 and 12.1.
The image upgrade remains a separate change.

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

## Isolated rehearsal

`services/media/jellyfin-rehearsal` restores only Jellyfin's subtree from the live
snapshot `apps/pv@jellyfin-rehearsal-20260916-359cdcb9`. Production remains on
10.11.11. The clone runs on worker-02 with its own 50 GiB NFS config claim,
10 GiB disposable cache, read-only media, and an 8 GiB memory / 2 CPU limit.
It has no ingress, discovery service, Kubernetes API token, or LDAP-sync job.
It uses the official OCI distribution of the same app-template 5.1.0 chart;
production's chart source and values are not changed.

NFS snapshot exposure is unavailable on this TrueNAS installation: the `.zfs`
snapshot directories appear empty to NFS clients. Restore **on the NAS itself**,
not through an NFS snapshot mount. The tracked helper has a fixed snapshot source
and a fixed private destination, `/mnt/apps/pv/media/jellyfin-rehearsal`, matching
the provisioner's `media/jellyfin-rehearsal` claim path. No new NAS share, service,
dataset, or host configuration is needed.

Before merging the rehearsal PR, copy and run the checked-in helper using an
existing trusted SSH connection:

```sh
scp services/media/jellyfin-rehearsal/manifests/prepare.py truenas_admin@10.9.9.30:/tmp/jellyfin-rehearsal-prepare.py
ssh -t truenas_admin@10.9.9.30 'sudo python3 /tmp/jellyfin-rehearsal-prepare.py --restore'
ssh truenas_admin@10.9.9.30 'rm /tmp/jellyfin-rehearsal-prepare.py'
```

The helper copies into an empty private directory, preserves ownership and
permissions, checks the copied SQLite databases (including WAL state), and
archives old plugin binaries while retaining their configurations. It writes a
snapshot-specific completion marker only after success. Confirm the restored
database and marker are visible through the ordinary NFS share before deployment.

Kodi Sync Queue's `kodisyncqueue.db` and `kodisyncqueue-log.db` use
[LiteDB, not SQLite](https://github.com/jellyfin/jellyfin-plugin-kodisyncqueue/blob/v15/Jellyfin.Plugin.KodiSyncQueue/Data/DbRepo.cs).
The helper preserves both files byte-for-byte; it does not claim a native LiteDB
integrity check. Require successful plugin startup and a real Kodi sync request
after installing the compatible replacement on the clone. Unrecognized `.db`
files still fail preparation rather than being silently skipped.

The init container only requires that marker and the private database; it never
accesses the NAS snapshot or recopies data. An empty, partial, or unrecognized
restore cannot start Jellyfin. Later starts preserve migrated data and newly
installed plugins. If restoration fails, stop and inspect the error; retry only
after explicitly cleaning the disposable rehearsal directory. Never repoint the
helper at production or roll back the shared dataset.

This live snapshot is crash-consistent, not a guaranteed clean application
checkpoint. A successful rehearsal does not replace the fresh cold backup before
production cutover. No new backup service or automatic dependency updates are
introduced for this temporary deployment.

After the rehearsal PR is merged, access it with
`kubectl -n media port-forward service/jellyfin-rehearsal 18096:8096`.
Use `http://127.0.0.1:18096` in a private browser window, not the production client
profile. Require completed migration logs and `/health` body **`Healthy`**, not
merely HTTP 200 or a new `/System/Info/Public` version.

Install these stable replacements **only on the 12.1 clone**, then run a full scan:

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
idle usage; the production cache currently pins Jellyfin to worker-01, which has
less memory headroom than the rehearsal worker.

## Controlled production upgrade

1. Through GitOps, suspend `jellyfin-ldap-library-sync` with `spec.suspend: true`
   and stop Jellyfin with `controllers.main.replicas: 0`. Wait for existing
   writers and the pod to terminate. Do not rely on live scaling that
   reconciliation can undo.
2. With Jellyfin stopped, back up the **complete `/config` volume**, including
   configuration, databases, metadata, plugin binaries and plugin configuration.
   Preserve ownership/permissions and keep an untouched copy outside that PVC.
   The separate disposable cache need not be copied. If using a snapshot of a
   shared NAS dataset, restore/clone only Jellyfin's directory, not every app.
3. Only after the isolated rehearsal succeeds and the fresh cold backup is
   secured, remove installed add-on binaries before starting the pinned 12.1
   image. Keep the complete original plugin state in the backup, retain plugin
   configurations, and reinstall the matching 12.1 builds afterward.
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
`python3 scripts/check-jellyfin-rehearsal.py` additionally checks NAS-local WAL
restoration, preservation of Kodi's LiteDB data/log, corrupt/partial-copy
rejection, marker gating without snapshot access, restart safety, and the rendered
clone's isolation.

- [Jellyfin 12 announcement and updating instructions](https://jellyfin.org/posts/jellyfin-release-12.0/)
- [Jellyfin backup and restore](https://jellyfin.org/docs/general/administration/backup-and-restore/)
- [Jellyfin storage guidance](https://jellyfin.org/docs/general/administration/storage/)
- [LDAP Authentication v24](https://github.com/jellyfin/jellyfin-plugin-ldapauth/releases/tag/v24)
- [Homepage Jellyfin widget](https://gethomepage.dev/widgets/services/jellyfin/)
