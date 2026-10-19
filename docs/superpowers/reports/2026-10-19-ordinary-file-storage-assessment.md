# Ordinary-file storage assessment

The user authorized autonomous CSI narrowing and ntfy recovery on 19 October.
The two workers retain 29 usable CSI attachments each. Before narrowing there
are 41 attached private-state volumes. Emptying attachment slots does not require
deleting retained raw images.

## Select ordinary files for retained NFS

| Workloads | Authoritative database | Files to preserve on NFS |
|---|---|---|
| Prowlarr | Shared PostgreSQL, main and logs | Config XML, definitions, backups, logs |
| Seerr and Seerr RU | Separate shared PostgreSQL databases | Settings, settings backups, cache, logs |
| Bazarr | Shared PostgreSQL | YAML settings, native file cache, backups, logs |
| Cleanuparr | Shared PostgreSQL | DataProtection keys, JWT key, client identity, logs, inactive SQLite archives |
| Grafana | Shared PostgreSQL | Plugins and all existing private files, including export directories |
| pgAdmin | Shared PostgreSQL | Existing private storage, sessions, Azure credential cache |
| ntfy | Shared PostgreSQL, all three stores | Attachment files and retained identity |
| Cineplete | Native ordinary files | Configuration, overrides, scan results, cache, logs |
| Changedetection | Native JSON/history files | Watch identities, settings, secret, history and backups |

A metadata/signature census found no active SQLite files in these ten volumes.
Cleanuparr has three archived SQLite databases under `.legacy-sqlite`; preserve
them as inactive files. Lack of SQLite alone is not the acceptance criterion:
all eight PostgreSQL consumers' current SQL startup guards passed independent
read-only execution against their current databases. The unchanged retained file
and enrollment guards remain mandatory at startup.

Bazarr 1.6.1 uses the vendored `fcache` file backend, not a hidden SQLite cache.
Its pinned backend passed write/sync/reopen on the actual NFS export. Synthetic
NFS 4.1 write/fsync/rename, permissions, numeric ownership and cross-worker
checksum checks passed. The transfer verifier additionally passed complete file bytes, timestamps,
directories, symlinks and hard links on synthetic NFS data. The NAS dataset uses
POSIX ACLs with discard inheritance; Linux exposes a mode-derived NFS ACL. Only
the exact kernel mode projection is accepted. Named/inherited ACLs and extra
rights remain rejected. See [Linux nfsd ACL mapping](https://github.com/torvalds/linux/blob/master/fs/nfsd/nfs4acl.c). Temporary scratch mounts and directories are removed by exact
operation identity. These checks establish preparation, not completed app cutovers.

Fresh static paths `/mnt/apps/pv/<namespace>/<app>-files` are distinct from the
held pre-PostgreSQL NFS sources. PV/PVC bindings are reconstructible from Git,
prebound with an empty storage class and Retain plus no-delete/no-prune annotations.
PVC capacity is descriptive on NFS; this does not introduce a dataset quota or a
reservation. Private claims use RWO and one Recreate deployment. NFS does not offer
RWOP enforcement; writer retirement, one-replica deployment and the existing
whole-cluster VM retirement contract remain required. Separate services do not
share private directories.

All durable files are preserved; this phase does not trade state for emptyDir
caches. Application images, PostgreSQL databases, credentials, native settings,
endpoints and shared media mounts remain unchanged. Ten successful cutovers would
reduce CSI attachments from 41 to 31. Old CSI images stay retained and detached.

## Keep transactional local stores on CSI

Keep shared PostgreSQL, Immich PostgreSQL, Redis AOF, Prometheus, Loki, Tempo,
Meilisearch and the remaining active SQLite/H2 applications on CSI. Lingarr still
has `local.db` and `Hangfire.db` despite its PostgreSQL integration. qBittorrent's
fastresume/config state is separate from its NFS download payloads; this operation
does not claim to fix NAS payload I/O.

Alertmanager, Mosquitto, Zigbee2MQTT and Matter use native persisted snapshots or
identity stores rather than SQLite. They need separate native persistence and
recovery qualification before changing storage. Same-Pod volume consolidation is
not needed for the ten ordinary-file moves and is left out of their cutover.
Existing ordinary NFS consumers such as Mealie remain unchanged.

## ntfy repair completed first

[PR #1408](https://github.com/Starktastic-Homelab/apps/pull/1408), merge
`dc9970c1a09dbf8a03a27aaddfb14bdb75401f5e`, restored ntfy before storage changes.
Stock 2.31.0 added `message.claimed_at` and advanced message schema 15 to 16.
The guard now accepts exactly both qualified column/version pairs while retaining
physical PostgreSQL identity, ownership, initialized state and read-only checks.
Three synthetic native tests cover damaged/future states and migration/restart of
the actual configured ntfy image; CI repeats the binary test for future upgrades.
All six hosted checks passed; independent review found no actionable issues.

Live ntfy passed all three init guards, native health, all three existing tokens,
private authenticated publish/poll and anonymous denial, with zero main-container
restarts. All application controllers and Argo applications were healthy after
acceptance. Database state, credentials and retained CSI bindings were preserved.
This is ntfy recovery acceptance; ordinary-file NFS activation is still pending.
