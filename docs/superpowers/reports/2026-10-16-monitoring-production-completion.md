# Monitoring retained-CSI production completion

Prometheus, Alertmanager, Loki and Tempo now use retained Proxmox CSI ext4 disks.
The existing upstream driver, verified VM-retirement handoff and ordinary GitOps
rebuild procedure remain in use. No Velero metadata checkpoint is required.

The operation started on 2026-10-16 UTC and finished on 2026-10-17 Israel time.
[Activation PR #1374](https://github.com/Starktastic-Homelab/apps/pull/1374) merged
as `de062276803333d03a85aeba4ca31082d120735c` under the owned reconciliation hold,
before any new application writer acquired authority. The four cutovers ran
serially under the same native owner and original six-hour cohort deadline.
Failed phases retained their real terminals; continuations performed only work
that had not completed and never reset the original clocks.

## Accepted native recovery and storage

| Service | Retained disk | Cold files | Native bytes | Independent recovery and live checks |
| --- | --- | --- | --- | --- |
| Prometheus 3.15.0 | 16Gi | 82 | 8,517,443,320 | All 15 original blocks independently extended-analyzed; all 24 cold historical queries matched; 23 live matches plus one explicitly approved retention expiry; new scrapes and rule identities accepted. |
| Alertmanager 0.34.1 | 2Gi | 2 | 530 | Exact notification log and valid empty silences file; native recovery and silences API accepted. No production test notification was sent. |
| Loki 3.6.11 | 10Gi | 51,893 | 1,965,724,516 | Every native file and POSIX attribute checked, WAL/checkpoint recovery, five fixed historical queries and fresh ingestion accepted. |
| Tempo 2.9.0 | 5Gi | 348 | 57,246,002 | Every native file and POSIX attribute checked; three complete bounded search sets containing 5,513 results and 30 full trace payloads matched; fresh traces accepted. |

The images, native retention settings, credentials and service endpoints stayed
unchanged. Tempo alone moved to stock app-template 5.2.1, preserving its native
ConfigMap, Service, ServiceAccount, ServiceMonitor, ports and process settings.
Its existing metrics-generator wiring was preserved; this is not a claim that
end-to-end generated RED metrics were qualified.

All four disks use RWOP/Retain, deterministic static bindings and read-only
retained-state startup guards. Each application passed clean Pod recreation,
movement to the other healthy worker, and return to ordinary worker placement.
Every transition proved the old writer's API/runtime/mount/device/Proxmox
references retired before the next writer; the original filesystem identity
survived, with zero new container restarts at acceptance. No forced detach was
used. This operation did not perform a live Terraform destroy/apply test.

The NAS dataset quota increased from 160Gi to 192Gi after checking the actual
dataset identity, healthy pool, physical free space and full possible growth of
all existing raw images, the new 33Gi, 512Mi staging and 8Gi spare. A quota is a
limit rather than a physical reservation. No other application disk was removed.

## Explicitly accepted retention expiry

Prometheus received all 82 cold files intact. On first stock startup its unchanged
15-day/8GiB policy removed the oldest healthy block through normal size retention:
`01M4E7AE1N3FPQ90A12W1WTW04`, covering 2026-10-07 18:00 UTC through
2026-10-08 12:00 UTC. The size-retention counter increased once; the time-retention
counter did not. The user explicitly accepted this 18-hour expiry while keeping
the existing policy. Only that exact historical point was exempted; every other
missing or changed result continued to block acceptance. The encrypted cold
backup retains the expired block and the independent all-24-query proof.

## Native behavior and transport qualification

Loki's original copy encountered a reproducible stock kubectl WebSocket failure
with a slow reader: the synthetic 75-second pause failed at approximately 61
seconds. The supported stock SPDY transport passed the same pause. Only the
one-time copy continuation used that transport; no cluster driver, controller or
application was changed. Completed files and verified prefixes kept their inodes;
only missing bytes were appended. A later stalled transport client was retired by
its exact recorded process identity, retaining its real nonzero terminal. The
completed disk was accepted only after an independent complete file/POSIX/marker
verification and filesystem sync. No source or target data was recopied to hide
the failed transport. See the pinned upstream
[WebSocket implementation](https://raw.githubusercontent.com/kubernetes/client-go/v0.37.0/tools/remotecommand/websocket.go)
and [exec transport option](https://raw.githubusercontent.com/kubernetes/kubectl/v0.37.0/pkg/cmd/exec/exec.go).

Tempo's graceful shutdown left one WAL directory containing exactly one regular
zero-byte page and no metadata or other files. Stock Tempo warns when discarding
that empty scaffold. The original cold archive and subsequent fully detached
filesystems were examined read-only, matching the known filesystem identity and
proving no persisted trace payload existed in the qualified directory. Only that
physically proven empty case was accepted; nonempty, corrupt or unproven WAL
warnings still failed acceptance. No data repair or runtime workaround was added.
The behavior follows stock Tempo 2.9.0's
[WAL page creation and metadata flush](https://raw.githubusercontent.com/grafana/tempo/v2.9.0/tempodb/encoding/vparquet4/wal_block.go)
and [replay handling](https://raw.githubusercontent.com/grafana/tempo/v2.9.0/tempodb/wal/wal.go).

## Final GitOps and cleanup evidence

All 25 changed desired/live resources matched exactly. The full current-source
operations for kube-prometheus-stack, Loki, Tempo, base-configs, Filebrowser and
the NFS provisioner succeeded with `CreateNamespace=true`, `ServerSideApply=true`
and `RespectIgnoreDifferences=true` preserved. All six applications were Healthy
and Synced at the activation commit.

The accepted continuous six-minute watch observed 0 typed Deployment,
StatefulSet and Pod events. All 17 original monitoring Secret identities/types/data
fingerprints, Grafana's Deployment identity/specification and the other 13 normal
monitoring Pod generations/restart counts were unchanged. The four accepted CSI
Pod generations stayed ready without replacement or new restarts. All four
services then passed another native/physical/history/fresh-ingestion check after
the watch and after temporary-resource cleanup.

Only the owned Argo hold, migration helper objects, cold NAS snapshots/spool and
operation guest/runner plaintext were removed. Original NFS sources, retained
CSI images and encrypted recovery were preserved. Native audit encryption and
roundtrip verification passed, and the original maintenance owner was released
last at 2026-10-16T22:10:16.825766+00:00. The operation stayed within its original six-hour deadline.

After this report's PR merges, the prepared closeout captures its merge and a
fresh read-only current-main observation in the encrypted final local audit,
then removes only this operation's private local fixtures and working keys.
The sanitized final working-cleanup terminal is retained beside the recovery
media outside Git.

The initial final-watch attempt stopped on a REST request encoding error. The
continuation also refused an already-used receipt identity before guest
submission. Both failed terminals were preserved. The corrected continuation
used the published Argo 3.5.5 [SyncOptions object shape](https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.5/server/application/application.proto),
a new native identity and an entirely fresh six-minute watch; the already-removed
hold was not released again. No application or driver change was needed.

## Recovery and limits

Original NFS sources remain retained and admission-held. After CSI authority,
never restart an old NFS writer as an ordinary rollback. Preserve the four known
raw images and use verified retirement for normal VM replacement.

AES-encrypted cold backups and their complete SHA256 manifests remain on VM300
under `/var/lib/homelab-maintenance/operations/monitoring-csi-cutover-20261016/recovery/`
and on the operator computer under
`~/.local/share/homelab-recovery/monitoring-csi-cutover-20261016/`.
The keys remain separately protected in the operation's `keys/` directory on
VM300 and `~/.config/homelab-recovery-keys/monitoring-csi-cutover-20261016/` on the
computer. Native audit ciphertext is retained on both hosts; local/final audit
ciphertexts are retained on the computer. Plaintext working keys, copies and
fixtures are removed only after the final audit is protected. Recovery requires
complete checksum verification and an independent native restore before use.

These are verified point-in-time recovery copies, not continuous backups. Cold
cutovers pause telemetry collection/ingestion; agent retries are bounded and do
not establish gap-free new telemetry. Retention continues to operate normally.
Use the [storage runbook](../../runbooks/monitoring-storage.md) for recovery rules.

## Implementation rulings

| Ruling | Reason and practical limit |
| --- | --- |
| Reuse the approved design and native maintenance machinery. | Keeps the authorized scope; corrections require fresh evidence. |
| Preserve exported root ownership and run guard probes as the app UID. | Prevents a root-only test from concealing application permission failures. |
| Keep 16/2/10/5Gi capacities and native retention. | Full-growth checks include all disks; capacity or retention changes need a separate decision. |
| Use Tempo's normal values cascade and supported disabled placeholder. | Exact rendered native objects and process settings prevent adapter drift. |
| Qualify bounded encrypted streaming before source recovery. | Full hashes, deadlines and native ownership bound disk and transfer risks. |
| Separate non-disruptive qualification from production outage clocks. | Independent qualification never relaxes or restarts the original production window. |
| Continue a failed qualification stream from a verified prefix. | Bounded ranges and complete final hashes reject wrong or incomplete media. |
| Compare complete bounded Tempo search sets and full trace payloads. | Avoids nondeterministic limited subsets without accepting missing history. |
| Analyze immutable original Prometheus blocks separately. | Fixture compaction cannot hide an unanalyzed source block. |
| Accept valid empty Alertmanager native files. | Native parser/API checks establish validity; invented nonempty rules would reject valid state. |
| Merge reviewed CSI definitions under the hold before authority. | Guards block unpopulated disks if fresh metadata appears unexpectedly. |
| Add only official CI debug output after bootstrap failures. | Existing versions, timeouts and runtime behavior remain unchanged. |
| Continue failed stops only after inspecting actual replacement writers. | Immutable continuations retire exact current writers; no stop, backup or clock replay. |
| Use stock SPDY only for the qualified one-time Loki copy. | Addresses reproduced streaming behavior without a runtime component change. |
| Independently verify the completed Loki filesystem after transport failure. | Costs an additional complete read; never substitutes exit status for data proof. |
| Use the REST-specific sync-options object and a fresh watch receipt identity. | Preserves all declared options and failed evidence; a fresh complete watch must pass under the original deadline. |
| Classify only physically proven zero-byte Tempo WAL scaffolds. | Extra offline audits preserve strict refusal of nonempty or unproven loss signals. |

One independent final review found five important issues, all fixed and verified
with focused regression tests; no critical or minor findings remained. Local
qualification and hosted CI never replaced current cold restores or live checks.
Production notification tests stayed outside scope. Existing metrics-generator
wiring was preserved without claiming delivery health beyond the checks above.
