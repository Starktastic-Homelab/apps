# Seerr and Seerr-RU preparation

The user approved inspecting both instances, rehearsing PostgreSQL conversion on
disposable copies, preparing retained CSI and incorporating the completed
Prowlarr operation's qualified release/cleanup findings. Production cutover has
not started. No application hold, enrollment change or CSI allocation occurred.

## Fresh native inventory

Read-only checks at 11:52UTC on October13 found both Applications Healthy/Synced
with no queued operation. Both use stock Seerr3.4.1 pinned at image digest
`sha256:f4768de5f616248d723e05891f3345a1402123775d03bf0890dbfedc0831bda1`.
The Russian variant inherits the base image/values through `baseApp`; it has a
separate Deployment and NFS claim. Preserve that inheritance during preparation.

| Instance | Users | Requests | Media | Config directory, including logs |
|---|---:|---:|---:|---:|
| Seerr | 8 | 418 | 415 | 7,144,586 logical bytes |
| Seerr-RU | 2 | 70 | 72 | 6,818,885 logical bytes |

Both SQLite databases have committed state in WAL files larger than their main
database files. A raw live copy of `db.sqlite3` is insufficient. Rehearsal needs
the native SQLite online backup API through a read-only source connection;
production still needs a fresh fenced cold capture with WAL and all configuration.
The counts above are an inventory snapshot, not a backup or conversion result.

Each has one Sonarr and one Radarr declaration and an existing API key. Settings
also contain session and notification secrets; no values were printed or placed
in this report. There are 15 SQLite tables and 53 SQLite migration records in
each instance. Logs include symlinks; the cold-copy plan must validate their
targets and preserve or explicitly account for them.

The source paths are `/mnt/apps/pv/media/seerr` and
`/mnt/apps/pv/media/seerr-ru`. Both original PVs already use Retain. Native Pod
inventory also found Filebrowser and the NFS provisioner mounting their parent
`/mnt/apps/pv`; their writer access must be fenced during a cold capture.
Shared PostgreSQL remains Ready on the same Pod generation as the accepted
Prowlarr operation. There is no default-project sync window or active maintenance
owner after reconciliation of the stopped rehearsal probe.

## Rehearsal contract

[Seerr's official procedure](https://docs.seerr.dev/extending-seerr/database-config/#migrating-from-sqlite-to-postgresql)
initializes PostgreSQL with Seerr before importing SQLite application data using
the documented pgloader build. Exact v3.4.1
[database configuration](https://github.com/seerr-team/seerr/blob/v3.4.1/server/datasource.ts)
and [startup](https://github.com/seerr-team/seerr/blob/v3.4.1/server/index.ts)
confirm separate engine migrations and ordinary startup migration execution.

The disposable probe will retain the stock-created PostgreSQL migration ledger,
exclude SQLite's migration ledger from the data import, and compare every typed
field of every application table. It must verify constraints and sequence floors,
settings/session-secret preservation, API user/request counts, stock startup and
clean restart. Any loader error, partial import, unexpected field change or
startup failure rejects the candidate. This is preparation, not evidence that
conversion has passed yet.

## Lab location decision

VM300's initial memory check rejected running PostgreSQL, Seerr and pgloader
there: it has approximately 850MiB total memory and 390MiB available. The probe
ended before image pulls, snapshots or lab containers. The exact process was
confirmed absent, execution was reacquired and its empty maintenance owner was
released. Production workloads were unchanged.

A fresh no-NIC VM980 using the existing offline lab method is recommended,
subject to the human's lab-resource/private-copy transfer decision and fresh
measured capacity. A temporary VM300 memory increase is the alternative. Do not
weaken the memory floor or use the shared production PostgreSQL for the test.

Read-only Proxmox checks found VM980 absent, the stopped template900 unchanged,
about 8.66GiB memory free and about 22.96GiB free in the shared local/local-zfs
pool. Those storage reports describe the same capacity and must not be added
together. Media/image-size, memory and full disk-growth reservations must pass
before any lab allocation. No new lab has been created.
