# Media retained-storage production completion

Sonarr, Sonarr-RU, Radarr, Radarr-RU, Lidarr, Cleanuparr, Navidrome,
Audiobookshelf, Shelfmark and Cineplete now use independent retained Proxmox CSI
ext4 disks. Cleanuparr additionally uses its dedicated PostgreSQL database.
The other nine engines, all ten application images, service endpoints and shared
media/download/ingest interfaces remain unchanged. The existing upstream driver
and verified VM-retirement/rebuild procedure remain in use without Velero.

[Preparation PR #1379](https://github.com/Starktastic-Homelab/apps/pull/1379)
merged as `59d672d`.
[Activation PR #1380](https://github.com/Starktastic-Homelab/apps/pull/1380)
merged as `335800075bce574c039312276c2b13d8469214f7` under the owned
14-application hold, after the first Sonarr cold restore, target population and
physical helper retirement passed. All five hosted checks passed on tested head
`a603d6d30c9f428199fe257fa0761d36d189844f`; the reviewed Argo preview contained
exactly the ten workloads, base-configs and PostgreSQL.

## Accepted cold recovery and live lifecycle

| Workload | Cold regular files | Native bytes | Preserved state |
| --- | --- | --- | --- |
| sonarr | 1377 | 607,047,784 | Original engine and complete private state |
| sonarr-ru | 337 | 141,560,212 | Original engine and complete private state |
| radarr | 1819 | 820,508,188 | Original engine and complete private state |
| radarr-ru | 325 | 184,172,177 | Original engine and complete private state |
| lidarr | 445 | 193,573,870 | Original engine and complete private state |
| cleanuparr | 65 | 4,882,829 | PostgreSQL; retained keys/config and legacy SQLite |
| navidrome | 493 | 32,592,868 | Original engine and complete private state |
| audiobookshelf | 50 | 454,409 | Original engine and complete private state |
| shelfmark | 160 | 7,619,427 | Original engine and complete private state |
| cineplete | 9 | 34,125,208 | Original engine and complete private state |

All ten independent cold restores passed complete content/POSIX checks and
stock-image startup before target authority. SQLite integrity, foreign keys,
schema and complete byte-safe table row multisets were checked on disposable
copies. Fixture-only Servarr schedules/commands and operational log additions
were distinguished explicitly; fixture-mutated files never populated production.
Every application passed clean Pod recreation, movement to the other healthy
worker, and return to ordinary placement on its original retained filesystem UUID.
Each transition verified old runtime/mount/device/Proxmox retirement where
required, with zero restarts in the accepted target generation. No forced detach
was used. This operation did not run a live full Terraform destroy/apply rehearsal.

Cineplete retains both former config and data claims under `config/` and `data/`.
Audiobookshelf retains its config/database and previously container-only metadata
on one disk. The pre-stop metadata capture preserved all 34 files, 56,123 bytes,
and POSIX metadata; it contained logs and empty directories. Ordinary later
shutdown/startup log appends are outside that capture. Shared media, downloads
and Shelfmark book ingest remain on their existing NFS interfaces.

## Cleanuparr PostgreSQL conversion

The exact 2.10.6 native converter passed both the isolated real-data rehearsal and
the production import: all 43 application tables, 454 columns and 13,566 rows
matched across `data`, `events` and `users`. Independent guards required an empty
dedicated target; no `--force` was used. Existing application rows in the copied
SQLite inputs remained unchanged. Native PostgreSQL startup and lifecycle checks
passed using the existing JWT, Plex identity and DataProtection keys.
Original SQLite files remain in `.legacy-sqlite/` on CSI and in cold recovery,
outside active paths; startup refuses active SQLite fallback.

The converter applies SQLite schema migrations in place, so it received only
writable disposable copies. Preserved NFS, immutable cold archives and production
CSI population never entered it. A real-data comparison initially rejected
SQLite timestamps without offsets. The pinned
[UTC value converter](https://github.com/Cleanuparr/Cleanuparr/blob/v2.10.6/code/backend/Cleanuparr.Persistence/Converters/UtcDateTimeOffsetConverter.cs)
explicitly stores those strings as UTC. Comparison now opts into that contract
only on the SQLite source side; PostgreSQL still requires timezone information,
and changed timestamps or missing rows still fail. Two new regressions passed
RED to GREEN. Only the unfinished comparison/startup tail continued; the already
successful isolated conversion was not replayed. Production import remained
blocked until the complete real-data rehearsal passed.

## Storage, reconciliation and recovery

Each app has a 4 GiB ext4 RWOP/Retain image at
`k3s-block:9999/vm-9999-<app>.raw`, independent of worker lifecycles. Allocation
checked dataset identity, healthy pool, physical free space, full remaining growth
of every existing raw image, new allocations, 512 MiB staging and 8 GiB spare.
The dataset quota is now 256 GiB; it is a ceiling, not reserved physical space.
All original NFS claims, source roots and ten cold ZFS snapshots remain retained.
Read-only startup guards reject missing/wrong/linked state without opening SQLite
or creating an empty database.

All 57 changed desired/live resources matched the current activation commit.
Only missing Argo tracking metadata was adopted. Captured unexecuted held queues
were replaced with full current-source operations, preserving every sync option.
The continuous six-minute typed Deployment/Pod watch accepted all 34 events
without a generation/spec/readiness/restart regression. All 14 applications were
Healthy and Synced at the current sources, all existing sync options were
preserved, and every prior media/database Secret value and UID remained unchanged.
All ten services then passed another native/physical check after the watch and
after temporary-resource cleanup.

All 81 logical native phases are accepted, including the separately journaled
continuations. Only owned helper/API resources, NAS spool and guest/runner staging
were removed. Encrypted audit protection preceded exact accepted-only local
plaintext fixture removal. The original maintenance owner was released last,
within the unchanged original 24-hour cohort deadline. All sources, retained
images, ten cold ZFS snapshots, two-host recovery media and separate keys remain.

AES-encrypted cold archives and complete hash manifests remain on VM300 under
`/var/lib/homelab-maintenance/operations/media-csi-cutover-20261017/recovery/`
and on this computer under
`~/.local/share/homelab-recovery/media-csi-cutover-20261017/`.
Keys remain separately protected in the VM300 operation's `keys/` directory and
`~/.config/homelab-recovery-keys/media-csi-cutover-20261017/` on this computer.
All ten backups passed encryption/decryption roundtrip and independent native
restore checks. Native audit ciphertext is retained on both hosts; local/final
audit ciphertext is retained on the computer. After this report merges, the
prepared closeout captures its exact merge and fresh current-main health, protects
the final local audit, then removes only this operation's working key, private
workspace and inventoried temporary scripts. Its sanitized cleanup terminal is
retained beside recovery outside Git.

These are point-in-time recovery copies. This operation does not establish
continuous backup coverage or infer human OIDC sign-ins, external scans/downloads
or notification delivery from native health. Follow the
[media storage runbook](../../runbooks/media-storage.md) for recovery and the
[PostgreSQL runbook](../../runbooks/postgresql-storage.md) for its ordinary backups.
Never restart stale NFS/SQLite sources after target authority.

## Qualification and bounded corrections

Fresh final checks passed 52 native package tests and 13 permanent guard/render
tests. Actual value layers previously rendered 119 valid resources with no invalid
resources or errors and two SealedSecret schema skips; native controlled-Secret
readiness/login were separate mandatory gates. One independent whole-package
review found two Important issues, both fixed RED to GREEN before execution:
permanent Cleanuparr prerequisites before conversion, and protected audit plus
accepted-only local plaintext cleanup before owner release. No Critical or Minor
findings remained. No deferred minor findings exist.

Runtime corrections preserved the original owner, clocks, failed terminals and
complete packet history. Source Deployment scale-down now precedes ordinary Pod
retirement. Helper identity receipts have distinct names from command receipts;
admission permits only the exact native topology labels. Retirement uses bounded
passive waits for the same strict predicates. Literal YAML scalars preserve the
PostgreSQL completion script bytes and acceptance generation. Every correction
was reproduced RED to GREEN; continuations performed only unfinished work.
No completed allocation, data copy, conversion or authority request was replayed.
The final 107-file packet is
`8b105933a21befc577431fb65077597956a6dc741528b15915c206d03ed15ec9`.
Protected encrypted audits retain all earlier packets and original failure evidence.

The first cleanup attempt deleted the reader and successful conversion Job, but
the API left its completed Pod orphaned. Cleanup stopped at its bounded wait;
all services remained online. An actual emitted-program regression reproduced it.
Cleanup now retires only the exact recorded successful Pod with UID/RV
preconditions, skips an already-gone Pod and refuses a changed identity. The
continuation removed only that orphan and the remaining owned resources; it never
replayed deletion of the already-gone reader/Job or any migration. Ordinary
runtime/mount checks and protected audit still gate owner release.

A later local check rejected the control-plane cleanup program before intent or
submission because shell escaping of its full receipt dictionary exceeded the
existing argv bound. No command-size limit was raised. Standard-library
zlib/base64 JSON now carries the complete metadata with unchanged native checks:
449 actual identities fit in a 36,795-byte shell-escaped wrapper. A regression
reproduced the old overflow, proved exact metadata roundtrip and passed the
original bounds. Only the three unsubmitted guest cleanups and remaining
runner/local cleanup continued; the protected native audit, NAS cleanup and
already-completed operations were not replayed.



## Implementation rulings and limits

| Ruling, in execution order | Reason and cost if wrong |
| --- | --- |
| Reuse the established retained-CSI design and inline autonomy. | Preserves the requested scope; app-specific gaps block authority. Cleanuparr conversion was explicitly added by the user. |
| Use an exact read-only NFS cold-archive helper. | Avoids slow interactive copying; mount/permission and complete-copy gates must pass. |
| Keep ciphertext-only range transport because VM300 lacks the NFS helper. | Avoids installing runner packages; complete hashes and transfer gates block incomplete recovery. |
| Qualify each current cold source during its own outage. | Synthetic fixtures cannot prove current data; native qualification can extend downtime before authority. |
| Require fresh production state/capacity/identity checks after review. | Review cannot establish live conditions; preflight blocks without an outage if they differ. |
| Independently restore every current cold source before authority. | Review did not execute current restores; failures retain the unchanged source and extend downtime. |
| Compare every real Cleanuparr table/column/row. | Synthetic conversion proves mechanics only; a mismatch blocks the production writer. |
| Execute native snapshot/backup/fencing gates independently of review. | Reviewer did not operate the NAS; uncertainty preserves ownership and prevents target authority. |
| Require exact-head activation CI, intended Argo diff and held merge. | Review alone cannot establish future CI; any failure blocks merge. |
| Require live recreation/movement and a six-minute current-source watch. | Local fixtures cannot prove attachment lifecycle; failed runtime checks leave acceptance incomplete. |
| Keep human OIDC and external downloads/scans/notifications outside native acceptance. | Those checks were outside the agreed native acceptance; an integration issue needs separate follow-up. |
| Retain upstream CSI and installed runtime as qualified dependencies. | Their hashes/generations/invocations remain checked; a pre-existing dependency defect can block execution. |
| Require native SealedSecret decryption and database login. | Source review cannot prove decryption; missing/wrong credentials block import/startup. |
| Use recorded native proofs for protected synthetic directories and repeat exact-current restores. | The reviewer could not inspect container-owned trees; real recovery gates still block errors before authority. |
| Scale the Deployment before ordinary graceful Pod retirement. | Avoids a ReplicaSet replacement race; no force or clock reset, and cold recovery still gates authority. |
| Interpret offset-less UTC only for the pinned SQLite source contract. | Preserves PostgreSQL timezone strictness; complete field equality and stock startup still gate authority. |
| Explicitly retire the recorded successful converter Pod after Job deletion. | API deletion may orphan it; changed UID/runtime/mount checks block cleanup and preserve ownership. |
| Compress only complete receipt metadata, retaining the original command-size limit and strict checks. | Exact metadata roundtrip, budget and native checks must pass; failure preserves ownership. |
