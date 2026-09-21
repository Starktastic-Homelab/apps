# Jellyfin retained iSCSI production pilot

Status: proposed production design, prepared after Terraform #223 restored both workers to 28 GiB. No production iSCSI, credentials, ACLs, workloads or storage properties were changed during preparation. User approval of the migration and its maintenance window remains separate from preparation and PR review.

## Intent and scope

Keep K3s disposable while retaining application state on TrueNAS. Pilot the supported Jellyfin SQLite backend on a dedicated ext4 iSCSI volume, using the stock democratic-csi node-manual plugin qualified in the [completed lab](../reports/2026-09-21-static-iscsi-recovery.md). The lifecycle and recovery interfaces must also serve other SQLite applications. Do not install an unofficial PostgreSQL provider or migrate other apps in this pilot.

The selected policy remains approval-gated fencing: an uncertain writer stays held until its exact old VM is confirmed powered off. Normal clean maintenance can proceed after verified shutdown/unmount. Neither RWOP nor a Kubernetes NotReady status proves that an old process stopped writing.

## Read-only production findings

The [preflight evidence](../reports/evidence/2026-09-21-jellyfin-pilot-preflight.json) records the September 21 observations. Recheck these immediately before any mutation.

- TrueNAS is 25.10.7. The `apps` pool is healthy and its dataset has approximately 368 GiB available. The existing iSCSI portal listens only on `10.9.8.30:3260`. iSCSI is disabled/stopped, with no targets, extents or initiator groups.
- Jellyfin `/config` uses 28,190,802,944 allocated bytes (26.3 GiB). The main database is 189,108,224 bytes, owned by 1000:1000. The 15 GiB NFS PVC request is not a quota and cannot size the new block device. These are live sizing observations, not a consistent backup or integrity check.
- `media/jellyfin-cache` is a disposable 50 GiB local-path claim pinned to worker 2; it currently uses roughly 9 MiB. It must not continue preventing cross-worker scheduling. `/config/data/transcodes` is another disposable path, currently tiny; throttling and segment deletion are enabled.
- No K3s node has `open-iscsi` installed. All three have e2fsprogs. Storage IPs are 10.9.8.50–52.
- No dedicated fencing principal exists. The dashboard account is read-only; the provisioning token and root account are substantially broader than fencing requires.
- The existing snapshot task covers `apps/pv` recursively for one week. It will **not** cover a sibling `apps/iscsi` dataset automatically.

### Existing NFS durability issue

`apps/pv` has an explicit local `sync=disabled` setting, with no child dataset overriding it. This includes the current application NFS data. Disabling sync weakens crash durability; it is not evidence that this setting caused the observed SQLite locking errors. Moving apps to PostgreSQL does not remove the requirement that acknowledged durable writes actually reach storage.

Recommend a separately reviewed, versioned change to `apps/pv` from `DISABLED` to `STANDARD`, after confirming fresh database backups and observing storage latency during a maintenance window. It affects all applications using that dataset, so do not conceal it within the Jellyfin cutover. Performance regression requires investigation; reverting to disabled is an explicit durability tradeoff, not an automatic rollback. The new iSCSI parent and ZVOL must explicitly use `STANDARD` and must not inherit the old setting.

[TrueNAS describes synchronous-write behavior](https://www.truenas.com/docs/references/zilandslog/); [PostgreSQL documents the NFS durability requirements](https://www.postgresql.org/docs/current/creating-cluster.html#CREATING-CLUSTER-NFS). Client `async` mounts are distinct from disabling durable server writes.

## Recommended storage layout

Use a new `apps/iscsi/jellyfin-config` 64 GiB non-sparse ZVOL: 16 KiB volblocksize and 512-byte exported sectors, matching the lab settings. Explicitly set `sync=STANDARD`, preserve flush/barrier behavior, and disable insecure third-party copy. This starts near 41% occupied before filesystem overhead. Re-measure before allocation and require copied persistent data below 70% of usable ext4 capacity; otherwise review sizing before proceeding. Do not tune volblocksize or add a SLOG speculatively.

Reuse the existing portal after verifying its identity/listeners. Create a dedicated target, LUN 0, CHAP credential and exact worker initiator allowlist. Keep NAS management on the management interface and iSCSI on the storage network. Do not overwrite the NAS global IQN basename. Generate the final IQN using the current basename and record the returned native identities rather than inventing IDs in manifests. Leave non-pilot exports unchanged.

Use a new static PV and `media/jellyfin-config-iscsi` PVC, both protected from Argo prune/delete, with `Retain`, explicit binding and `ReadWriteOncePod`. Keep the existing NFS claim intact for rollback; do not mutate its immutable storage class. No dynamic StorageClass or cluster default-class change. Keep media mounts on their existing NFS claims.

Run the stock CSI node plugin on the two workers only, with the lab-pinned image/digests, `attachRequired=false`, no controller, no NAS API credential, ext4 `-n` formatting options, and automatic filesystem checks disabled. The no-write option is not sufficient by itself: external identity verification and admission remain mandatory. Do not copy run-specific lab manifests or old VM identities into production.

Replace the local-path cache mount with one disk-backed `emptyDir`, limited to 10 GiB total, containing separate cache and transcode subdirectories mounted at `/config/cache` and `/config/data/transcodes`. Preserve directory ownership 1000:1000. Propose a 12 GiB ephemeral-storage request/limit for the app (10 GiB disposable data plus writable-layer/log headroom). Require at least 25 GiB free on the selected worker and verify eviction thresholds before release. The current worker-1 free space is only about 26.8 GiB, so this check matters. Exhaustion may interrupt playback; it must not move the database to disposable storage. Retain the old cache PVC until acceptance, then delete it deliberately. Validate representative concurrent transcodes before considering the capacity adequate.

Jellyfin remains one replica with a Recreate strategy. Require the existing worker/GPU eligibility plus the new storage-ready node label; retain the exact image, probes, plugin versions and supported SQLite provider for the migration.

## Ownership and repository boundaries

| Repository | Responsibility |
| --- | --- |
| Ansible | Worker initiator packages/services, deterministic unique per-role IQNs, generic Proxmox fencing command and narrowly scoped account setup, generic rebuild prerequisites. No application catalog or service-volume definitions. |
| Apps | Pinned CSI node plugin, storage admission policies, durable service/native identity record, CHAP SealedSecret, external per-service onboarding/verification/backup commands, Jellyfin values and cutover runbook. |
| Terraform | VM lifecycle and production maintenance coordination. Destruction/recreation must stop old writers before replacement nodes reuse initiator identities. |

Service-specific NAS lifecycle stays in Apps. External commands run from the operator machine or the runner outside K3s; they are explicit maintenance operations, not an in-cluster NAS controller. Secrets remain outside Git except properly sealed CHAP, created using `scripts/seal.sh`.

## Fencing account and qualification

Create a separate PVE-realm service user and privilege-separated API token, with a custom role containing only `VM.Audit` and `VM.PowerMgmt`. Assign both the user and token this role at `/vms/201` and `/vms/202`, with propagation disabled. No grants on `/`, `/nodes`, storage, TrueNAS 100, master 200 or runner 300. If storage eligibility later expands, review the allowlist explicitly.

The installed Proxmox 9.2.20 API checks `VM.Audit` for configuration/current-status reads and `VM.PowerMgmt` for stop. Polling a task created by the same token does not require node-wide Sys.Audit. Token privileges are intersected with the user's privileges; configure and test both ACL layers. `VM.PowerMgmt` also permits start/reboot: Proxmox's role cannot express stop-only. The reviewed command must expose only identity-check, stop and verify; no automatic restart. See [Proxmox access-control documentation](https://github.com/proxmox/pve-docs/blob/master/pveum.adoc).

The generic command takes expected node, VMID, VM name and SMBIOS UUID from a reviewed generation record. Read configuration with `current=1` and reject pending identity changes. Verify expected name/UUID before any stop, check that no VM mutation/task or infrastructure deployment is in progress, submit one stop, poll its own UPID, then reread exact identity and `status=stopped`. Record the receipt outside Kubernetes with VM generation and timestamp. Timeout, denial, ambiguous response, changed UUID or unavailable API leaves writers held. Never use skiplock or treat a returned task ID as proof of power-off.

Serialize fencing against infrastructure apply/recreate operations under a documented maintenance lock. The existing Terraform/Ansible workflows do not yet share that lock. Its implementation and an explicit operator prohibition on concurrent GUI start/recreate are pilot prerequisites; checking a UUID once does not remove the race with VMID reuse. The command must not select a new generation from current VMID alone or automatically restart a fenced node.

Qualification sequence:

1. Apply the reviewed account definition; save effective user/token permissions and prove that only the two worker VM paths have the intended privileges. Read worker config/status using the actual token. Confirm protected-VM reads are denied and effective permissions contain no power/config privileges elsewhere. Do not issue destructive negative tests against protected production VMs.
2. Create one explicitly owned, diskless, networkless 128 MiB test VM on a verified unused VMID. Temporarily grant the same token the same role on that one path. Test wrong-UUID refusal, successful power-off and receipt polling, and timeout/lost-response handling that holds release until a fresh identity/status check succeeds. Remove the temporary ACL and VM and verify cleanup. This qualifies the permission route; it is not a partition or application-data test.
3. Before admitting Jellyfin, validate worker generation mapping, admission holds, clean unmount and controlled worker handoff. Reuse the completed isolated partition evidence, but keep first production fencing operator-approved. Never power off a production worker just to test a permission.

## Writer admission and rebuild recovery

Promote the tested policies into production scope: reject dynamic/aliased/foreign claims, changed driver/filesystem/Retain/native identity, and any pod referencing the retained claim without the required writer identity/authorization. Protect unlabelled-pod bypasses. Scope the policy to the retained platform; unrelated media workloads must keep working.

A fresh media namespace, new cluster, target change, filesystem change or uncertain prior writer requires external verification. Authorization binds the namespace UID, current storage record and exactly one permitted worker generation/placement. For this operator-managed pilot, render required node affinity to that one authorized worker and validate it against the external authorization record in admission; a generic worker selector is insufficient. A move requires a held workload and a new verified placement authorization. This prevents the scheduler from independently moving the writer to the other worker after a partition; it deliberately accepts downtime until operator recovery. Before release, verify native pool/ZVOL GUID, extent serial/NAA, target/IQN/LUN/portal, capacity, filesystem UUID and service marker, then validate SQLite on a private copy including any WAL. Never initialize/repair a missing or unrecognized existing service during normal recovery. If journal replay is required, remain held for explicit maintenance.

Admission alone does not revoke a running process. After a node becomes uncertain, block replacement placement before removing the stale pod; keep the new writer held until the exact old VM is fenced. Do not describe a namespace-scoped one-time authorization as permission for arbitrary future cross-node failover. A production external verification/release path must account for each placement transition; this is a required implementation gap beyond the lab fixture.

Clean planned handoff: hold the workload, stop the pod, prove the mount and CSI iSCSI session are gone from the old worker, verify identities, authorize the new placement and release one pod. Unreachable node: power-off receipt first, then stale-pod cleanup and release. Returning nodes remain excluded until stale sessions/mounts and generation identity are checked. Cluster replacement restores the external sealing key and reviewed identity records first, keeps writers held, and only then verifies/rebinds storage. Reusing an IQN while an old VM can still write is prohibited.

## Cold backup and cutover procedure

The proposed independent backup location is this laptop's encrypted `/home` filesystem (approximately 900 GiB free), under a private 0700 directory such as `/home/benf/Backups/homelab/jellyfin/<UTC-stamp>`. Destination selection is pending the user's answer. Do not use `/tmp` (a 16 GiB tmpfs), a K3s worker disk, or only another dataset on the same NAS as the independent copy. Include the sealing-key recovery material through the existing protected key-backup procedure; never put keys in the evidence report.

Before downtime, prefetch pinned tool/application images and verify every prerequisite above. Prepare two reviewed Git states: held/cutover (`replicas: 0`, replacement admission closed) and release (`replicas: 1`). Ensure Argo cannot restore the source writer during copying. Inspect/suspend any Jellyfin-specific API jobs or other consumers that can write `/config`. A replica patch alone is insufficient if Git immediately restores it.

During the approved Jellyfin-only maintenance window:

1. Drain active playback through an announced maintenance period; record the current image/configuration and non-sensitive application counts. Hold writes through Git/admission, stop Jellyfin gracefully and prove no process/pod on either worker is using its configuration. Never force-delete an uncertain writer. Verify the exact NFS source and a writable new target cannot both host an app writer.
2. Take a named source snapshot covering `apps/pv`, recording its GUID/time. It is a cold point for Jellyfin only, not a transactionally coordinated backup of the other applications in that dataset. Copy the full Jellyfin configuration subtree, preserving ownership, modes, symlinks and relevant extended attributes. Include SQLite DB/WAL/SHM files, plugin databases including LiteDB, metadata, trickplay, plugin binaries, XML and scheduled tasks. Exclude only the explicitly disposable mounted cache/transcode contents; record the exclusions. Do not copy only `jellyfin.db`, delete WAL files or alter locking settings.
3. Make an independent archive/copy on the selected laptop destination, hash it, fully extract into a separate directory, verify file hashes/metadata and run SQLite integrity checks against the extracted copy. Validate LiteDB/plugin readability through an isolated same-image Jellyfin startup using only the restored copy, with external network access blocked and no production writable mounts. Confirm existing server/catalog/users rather than an initial setup wizard. Protect private counts/identities. The archive is not accepted until this restore passes; stop and resume the original source if it fails.
4. Explicitly onboard the new target once, using an intent/receipt journal and generated native identities. Unknown API outcomes require query/reconciliation, not allocation retries. Format only that newly created, independently verified empty target in the onboarding operation. Copy the cold source state, verify per-file hashes and ownership, unmount, and record the ext4 UUID/service marker. Normal rebind code has no create or mkfs path. Ensure the source and destination cannot both be writable by Jellyfin.
5. Commit/seal the actual returned identities and CHAP via the approved mechanism, render their actual value layers, and reconcile the new static PV/PVC while writers remain held. Confirm NFS/media claims are unchanged. Run the external verification gate, then release one Jellyfin pod on an eligible worker using the reviewed cutover values.
6. Check exact `/health` body `Healthy`, existing user/catalog state, plugins, watched/resume state, direct play, hardware transcoding, forward/backward seeking and subsequent progress writes. Check logs for new SQLite/I/O errors and measure readiness/latency against the baseline. Then exercise one clean handoff between workers with the same database identity and fresh disposable cache. Do not induce a production partition or host reboot during the first cutover.
7. Observe at least 24 hours including representative playback and scheduled tasks before declaring the pilot accepted. Take and restore an independent backup of the new backend, add an explicit snapshot schedule for `apps/iscsi`, and document operator recovery. Keep the old NFS data and pre-cutover backup until this acceptance and explicit cleanup decision.

The recommendation to stop Jellyfin and preserve its configuration/data for manual backups follows [Jellyfin's backup documentation](https://jellyfin.org/docs/general/administration/backup-and-restore/). This design's additional identity, restore and writer gates address the specific remote-volume migration.

## Rollback

Before the target has been opened writable by Jellyfin, rollback can switch the held Git state back to the untouched NFS config/cache claims and release one source pod after verifying no target writer/session remains.

Once Jellyfin has opened the new backend, assume it has written state even without user traffic. The old NFS copy is stale. Hold/stop the iSCSI writer, prove quiescence or fence, take a fresh cold backup of its entire config, and restore that state to a new NFS rollback directory. Bind a separately reviewed retained NFS PV/PVC to that directory, preserving the original source as evidence. Verify integrity, ownership, identity and hashes before releasing a single writer. Never merge databases or blindly start the old copy. If latest state is corrupt, stop for an explicit choice of known-good restore point and acknowledged data loss.

Rolling back the application does not automatically delete ZVOLs, targets, old NFS copies, credentials or snapshots. Cleanup is a separate identity-checked operation after recovery is accepted.

## Delivery and readiness gates

Prepare separate reviewable changes for (1) the existing NFS sync setting and its verification, (2) generic Ansible prerequisites/fencing plus maintenance coordination, (3) Apps storage policies/plugin/external lifecycle, and (4) the Jellyfin held/cutover/release states. Keep each production change explicit; merging documentation does not start migration. Keep current PR #1232 as lab evidence/design, not a deployable platform.

The pilot is not ready for a production cutover until the actual scoped-token test, durable maintenance coordination, placement-specific writer hold, independent cold restore, sealing-key recovery, cache capacity check and current-value Helm/admission validation all pass. This document does not certify those future checks. It preserves the accepted static architecture and turns the remaining gaps into verifiable work.
