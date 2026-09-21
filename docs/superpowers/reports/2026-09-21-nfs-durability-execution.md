# NFS durability correction: executed and observed

`apps/pv` now has explicit local **sync=STANDARD**, confirmed through the pinned
TrueNAS API after the single approved update and again after observation.
No production restart, database repair, PV migration or iSCSI change was performed.
Maintenance ownership was released at 2026-09-21T18:54:04.845934+00:00.

## Approval and protected scope

The user approved the [45-minute online window](2026-09-21-nfs-change-window.md),
including the narrow existing Loki recent-log recovery exception. The executable
receipt covers 52 accepted application/dependency/archive entries. Filebrowser's
local DB and Audiobookshelf retain their prior exclusions. The complete Loki
cold archive remains protected; neither log deletion nor repair was authorized.
This receipt does not claim every Loki record can be replayed.

The 61.1 GiB encrypted archive was re-read and its SHA-256 matched before ownership
was acquired. Its original 16:34:04 UTC capture time remains unchanged. The NAS
snapshot GUID, dataset/pool GUIDs, five VM identities and pinned certificate were
rechecked. The exact tools, pinned Python image, receipt and approval were stored
under `/var/lib/homelab-maintenance/operations/nfs-standard-20260921T180947Z` on the durable runner disk.

## Execution and observation

The ten-minute baseline ran from 2026-09-21T18:11:53.885748+00:00 to 2026-09-21T18:21:53.885810+00:00.
The single update completed at 18:22:39 UTC on 2026-09-21.
The durable update intent and verified result are retained in `nfs-standard.jsonl`;
the runner process exited successfully without stderr. A separate client readback
confirmed STANDARD before the observation began.

Observation ran from 2026-09-21T18:23:31.492641+00:00 to 2026-09-21T18:53:31.492712+00:00, with
31 readiness/log checks across thirty minutes. Continuous NAS I/O samples were
captured every ten seconds, with freshness and gap checks before closure.

| Check | Baseline | After STANDARD |
| --- | ---: | ---: |
| All Deployments/StatefulSets ready | 97 | 97 throughout |
| Affected workloads ready | 52 | 52 throughout |
| Affected running containers checked per sample | 64 | 64 |
| New container restarts | 0 | 0 |
| Database-corruption, storage-I/O, lock or storage-timeout markers | 0 | 0 |
| Pool read/write/checksum error counters | 0 | 0 |
| Busy write-wait average, weighted by operations | 1.269 ms | 0.479 ms |
| Largest ten-second average write wait | 1.777 ms | 3.639 ms |
| Busy ten-second I/O intervals | 60 | 180 |

These are pool I/O wait measurements under the load observed, not application
response times or latency percentiles. No injected load was used. All three
nodes remained ready with fresh leases, and the monitored container identities
and restart counters remained unchanged. Log requests completed without detected
truncation. No agreed regression trigger was reached.

Final identity-checked readback confirms STANDARD, all five VMs running, and
unchanged iSCSI state: stopped/disabled, zero targets and extents. The exact owned
latency collector was stopped and its exit verified. Only this operation's
copied NAS password file was removed; durable journals and backup evidence remain.
The persistent maintenance lock was released after the final checks and journal
writes. A final independent read confirms no active operation marker.

## Limits and next stage

STANDARD restores normal synchronous-write behavior; this observation does not
prove long-term SQLite reliability over NFS or behavior during power failure.
Existing application relationship findings and Loki's replay exception remain
recorded. No storage/data rollback was performed.

The retained-iSCSI pilot remains a separate stage. This operation did not build
Packer images, recreate VMs, enable iSCSI or move Jellyfin data.

[Sanitized execution evidence](evidence/2026-09-21-nfs-durability-execution.json)
contains identity/ownership references, pinned tool hashes and every observation
summary. Detailed private samples and journals accompany the encrypted backup.
