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
Prowlarr operation. The initial inventory had no default-project sync window. The disposable
rehearsal subsequently acquired its own scoped maintenance owner; it created no
production application holds.

## Rehearsal contract

[Seerr's official procedure](https://docs.seerr.dev/extending-seerr/database-config/#migrating-from-sqlite-to-postgresql)
initializes PostgreSQL with Seerr before importing SQLite application data using
the documented pgloader build. Exact v3.4.1
[database configuration](https://github.com/seerr-team/seerr/blob/v3.4.1/server/datasource.ts)
and [startup](https://github.com/seerr-team/seerr/blob/v3.4.1/server/index.ts)
confirm separate engine migrations and ordinary startup migration execution.

The disposable probe retained the stock-created PostgreSQL migration ledger,
excluded SQLite's migration ledger from the data import, and compared every typed
field of all 14 application tables. Both instances passed: constraints remained
validated, triggers enabled, all 14 ID allocator floors were verified, settings
and session secrets were preserved, API user/request counts matched, and stock
startup plus clean restart succeeded. PostgreSQL 18.6 used only fixture credentials
and restricted instance owners. See the [non-secret acceptance evidence](evidence/2026-10-13-seerr-postgresql-qualification.json).

## Disposable qualification and limits

The user approved a fresh no-NIC VM980 after VM300's initial memory precondition
rejected running the application stack on its approximately 850MiB RAM. The lab
used two CPUs, 3GiB RAM, a 12GiB root disk and less than 1GiB combined media.
Allocation preserved the approved shared-pool capacity reserve. Exact stock image
digests were verified before import; no production infrastructure credential,
SQL administrator password or kubeconfig entered the guest.

Online SQLite backups included committed WAL and source settings stayed unchanged
through capture. Pgloader could not open a bare read-only snapshot retaining its
WAL-mode header; its process could exit zero despite logging an error. Qualification
therefore required a separately materialized DELETE-journal input, with complete
schema, row and allocator equality to the unchanged captured snapshot, followed
by full PostgreSQL comparison. No source database was converted in place.

The first stock app started but its readiness probe timed out: `/api/v1/status`
checked GitHub for updates under the preserved settings. The no-NIC lab has no
upstream access. The resumed probe used stock `/api/v1/status/appdata`, verified
local permissions/path and the pinned package version, and kept settings intact.
[Stock routes](https://github.com/seerr-team/seerr/blob/v3.4.1/server/routes/index.ts)
confirm this local handler avoids the update fetch. Every interrupted attempt was
reconciled to a definite process outcome before continuation; existing imported
Seerr data was verified and reused, rather than importing it twice.

The no-NIC test establishes conversion compatibility, local API access and
preservation across clean restart. It does not prove live Sonarr/Radarr/media
integrations, human sign-in, CSI attachment/movement, a total cluster rebuild or
production backup recoverability. A separately approved fresh fenced cold capture
and production acceptance procedure remain required.

## Exact cleanup

Both accepted instance proofs preceded cleanup. The captured VM980 generation
and its owned disks were retired after checking that no other VM referenced the
lab volumes or media. Hash-verified public/private ISOs and temporary real-data
copies were removed from Proxmox, VM300 and this computer. The maintenance owner
and nonce were released. Final native checks found both original app Pods,
claims/PVs and NFS paths unchanged, both apps Healthy/Synced, shared PostgreSQL
Ready on the same Pod, and no production hold created.

## Next design

The [written proposal](../specs/2026-10-13-seerr-postgresql-csi-design.md) uses the
existing PostgreSQL enrollment/completion flow, two independent restricted owners
and retained 4GiB CSI configuration volumes. It preserves Seerr-RU inheritance
and carries forward the qualified Prowlarr release/cleanup procedure. This PR
changes documentation only: no live enrollment, storage allocation or cutover.
