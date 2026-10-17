# Media private-state assessment — October17

Read-only production inspection found all ten targets Healthy/Synced, one Ready
writer each, current node/VM identities and idle native owner. Approximately2GiB
of logical private data is spread across eleven NFS claims. Shared library and
book-ingest claims are excluded. Private trees contain only regular files and
directories, no xattrs or special files. No production changes have been made.

| Workload | Private logical MiB | Native retained state | Process UID:GID |
| --- | ---: | --- | --- |
| Sonarr | 578.84 | sonarr.db, logs.db, config.xml and full config tree | 1000:1000 |
| Sonarr RU | 134.37 | distinct Sonarr tree and identity | 1000:1000 |
| Radarr | 783.33 | radarr.db, logs.db, config.xml and full config tree | 1000:1000 |
| Radarr RU | 177.41 | distinct Radarr tree and identity | 1000:1000 |
| Lidarr | 184.71 | lidarr.db, logs.db, config.xml and full config tree | 1000:1000 |
| Cleanuparr | 8.67 | cleanuparr.db, users.db, events.db, keys and full config tree | 1000:1000 |
| Navidrome | 35.15 | navidrome.db and full config/cache tree | 0:0 |
| Audiobookshelf | 0.43 | absdatabase.sqlite, migrations and full config tree | 0:0 |
| Shelfmark | 7.27 | users.db, settings.json, .flask_secret, plugins/covers/full tree | 1000:1000 |
| Cineplete | 32.54 | config/config.yml plus data/overrides, scan/cache/results/logs | 0:0 |

Audiobookshelf also has34 container-only metadata log files,56,123bytes, and empty
cache/backups/streams directories. There are no custom cover/author images there.
Capture before source deletion and persist `/metadata` on the same retained image
as `/config`. Its [official Docker documentation](https://audiobookshelf.org/docs/documentation/install/docker/)
defines these as distinct data paths. Its [backup documentation](https://audiobookshelf.org/docs/category/server-management/)
includes database and metadata but excludes media files.

[Navidrome's native backup](https://www.navidrome.org/docs/usage/admin/cli/backup/)
covers its database; this migration preserves the entire private tree, with music
remaining on existing NFS. [Shelfmark's pinned environment contract](https://github.com/calibrain/shelfmark/blob/v1.3.15/docs/environment-variables.md)
keeps settings/users/plugins in config, shared ingest in books and temporary files
elsewhere. [Cineplete](https://github.com/sdblepas/CinePlete) stores user overrides
separately from its config: both existing claims must survive.

The [exact Cleanuparr2.10.6 documentation](https://github.com/Cleanuparr/Cleanuparr/blob/v2.10.6/docs/docs/installation/database.mdx)
confirms SQLite or PostgreSQL and the native migrate-to-postgres converter with
three schemas. The user selected its separately rehearsed PostgreSQL conversion. The exact
pinned converter source differs from that documentation: it applies pending SQLite
migrations in place before copying. Run it only against a writable disposable
copy, never the preserved original source or its immutable cold backup. Reject
any pre-existing target application schema/data independently of its native
applied-migration check; never use --force. Verify complete settings/users/events,
sequences and native startup before accepting target authority.

Dataset apps/k3s-block GUID13918781591004512447 is quota192GiB,121.09GiB available.
Existing raw files reserve another109.30GiB of growth; the pool is ONLINE with
266.28GiB physical free. Fixed4GiB images require at most40GiB plus512MiB staging
and8GiB headroom. Quota256GiB fits these measured commitments, subject to a fresh
physical/full-growth check immediately before allocation. Preserve the protected
partial Jellyfin image and all unrelated volumes/snapshots.

All images remain pinned to current digests; native readiness is not by itself a
data-preservation proof. Source cold snapshot, complete file/POSIX roundtrip,
SQLite integrity and complete byte-safe row comparison precede isolated stock
engine qualification and target authority. Offline fixtures postpone background
scans only in disposable copies so absent media does not alter library history.
