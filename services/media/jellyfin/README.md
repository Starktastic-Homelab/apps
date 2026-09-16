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

## Controlled upgrade

1. Through GitOps, suspend `jellyfin-ldap-library-sync` with `spec.suspend: true`
   and stop Jellyfin with `controllers.main.replicas: 0`. Wait for existing
   writers and the pod to terminate. Do not rely on live scaling that
   reconciliation can undo.
2. With Jellyfin stopped, back up the **complete `/config` volume**, including
   configuration, databases, metadata, plugin binaries and plugin configuration.
   Preserve ownership/permissions and keep an untouched copy outside that PVC.
   The separate disposable cache need not be copied. If using a snapshot of a
   shared NAS dataset, restore/clone only Jellyfin's directory, not every app.
3. Prove the backup restores into a separate volume, then rehearse the exact
   proposed image against that copy. After the cold backup, resume production
   10.11.11 and its writers through GitOps while the isolated rehearsal runs.
   Give the clone no production ingress/discovery, read-only media mounts and no
   policy-sync job. Following upstream guidance, remove installed add-on plugins
   from the clone before migration; keep their original state in the backup and
   reinstall compatible versions afterward.
4. Require completed migration logs and `/health` body **`Healthy`**, not merely
   HTTP 200 or a new `/System/Info/Public` version. The temporary startup server
   can report `Degraded` with HTTP 200. Readiness checks the body; startup and
   liveness intentionally remain HTTP checks so a responsive migration can continue.
5. Reinstall compatible plugins, then run a full library scan. Allow additional
   time and monitor memory/disk use. Check library access for a local administrator,
   an LDAP administrator and a normal LDAP user; verify both dashboards, Bazarr
   refreshes, direct play, forced Intel QSV/VA-API transcoding, HDR tone mapping,
   subtitles, seeking and the clients actually used.
6. Only after the rehearsal succeeds, repeat the stopped backup and upgrade for
   production using the pinned image, including plugin removal/reinstallation
   and the full scan. Keep policy synchronization suspended until authentication
   and library access are verified, then remove the maintenance overrides
   through GitOps.

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
