# Jellyfin retained-storage maintenance

The approved design keeps the cluster disposable while retaining Jellyfin's
supported SQLite backend on a dedicated TrueNAS ext4/iSCSI target. The user owns PR merges. The prerequisite platform and native NAS allocation
are now deployed and verified; Jellyfin still uses its original NFS storage.
See the [allocation and next-stage report](../superpowers/reports/2026-09-21-jellyfin-allocation.md).

## Sequence and ownership

1. Review/merge the NFS tool and coordinated Ansible/Terraform maintenance changes.
   Bootstrap and qualify VM300's durable shared lock first. The runner marker and
   helper pin are mandatory; a missing bind mount must block every mutation.
2. Before the separate NFS window, inspect fresh consistent backups/actual
   restores for every critical `apps/pv` database. Apply STANDARD once, inspect
   readback and app/storage latency. Never auto-revert to DISABLED.
3. Enroll reviewed worker initiator generations and qualify the scoped token with
   the documented 128 MiB diskless/networkless VM. Verify temporary grants and VM
   cleanup. These are explicit live gates, not claims established by unit tests.
4. Onboard the reviewed 64 GiB target once. Preserve the returned native record and
   journal outside K3s. Normal verification must never create or format a target.
5. Schedule the Jellyfin outage only after prerequisites, rollback artifacts,
   source-held Git revision and independent backup tooling are ready. The laptop
   destination is approved; **the outage window is not yet approved**.
6. After a real cold restore succeeds, complete the explicit format/copy stage,
   record filesystem UUID/marker, seal actual CHAP through `scripts/seal.sh`,
   review the resulting static bindings and target-held/release revisions.
7. Verify exact worker placement and old-writer quiescence/fencing before release.
   Complete application checks, one clean worker handoff and 24-hour observation.
   Verify execution of the configured `apps/iscsi` snapshot task and restore a new independent backup.

The external workflow keeps ownership across manual stages. Continue with the
original owner/nonce and exact stage. Cancellation or uncertainty leaves it held.
Do not start/recreate VMs in the Proxmox GUI concurrently. Ansible documents the
original-owner reconciliation procedure; no timer is permission to clear a lock.

## Cold capture to the approved laptop

Use `/home/benf/Backups/homelab/jellyfin/<UTC-stamp>` on the confirmed encrypted
home filesystem, mode 0700. The source is approximately 26.3 GiB; allow room for
the archive plus two restored copies. `/tmp` is a small tmpfs and is rejected as
a destination. Do not stage the archive in a worker, reader pod or NAS dataset.

Before holding, save a private baseline with the exact image digest, hash of the
public server ID, user count, `/Items/Counts`, and each `/Plugins` entry's Id,
Version and Status. Use the existing protected API key through a private file;
never put it in Git, logs or command arguments. Preserve plugin/LiteDB state and
the full config tree, not only the main SQLite file. Independently preserve the
Sealed Secrets recovery key through the existing Ansible secret-backup procedure.

The `source-held` revision must set replicas to zero, suspend the LDAP sync job,
close ingress and install the source writer admission hold. Wait for existing
Jobs and config consumers to stop. Never force-delete an uncertain writer.
Record the actual immutable source-held revision in the runner's
`/maintenance/operations/jellyfin/stages.json`. Create a named source snapshot;
record its GUID and current dataset GUID/path after a fresh NAS read.

Dispatch `prepare-reader` under the original maintenance ownership. It creates
one read-only pod and saves its exact UID. Copy its nonsecret receipt and the
reviewed source/snapshot/baseline metadata to a private laptop JSON file. Include
`reader` (name, namespace, UID), `source_held_revision`, `source` (dataset_guid,
claim_uid and NFS path), `snapshot.guid`, `image`, `server_id_sha256`, `user_count`,
`item_counts`, and `plugins` in that metadata. Record that bytes come from the
**held live NFS source**; the snapshot is an additional recovery point.

On the laptop, with an explicit kubeconfig:

```sh
python scripts/storage/jellyfin_backup.py capture-pod \
  --kubeconfig /private/kubeconfig --metadata /private/jellyfin-cold-metadata.json \
  --destination /home/benf/Backups/homelab/jellyfin/REVIEWED-UTC-STAMP
```

The command verifies the reconciled Git hold, suspended/completed API jobs,
exact source PV/PVC and reader UID. It continuously rechecks the hold while
streaming a numeric-owner tar with ACL/xattrs directly into a private partial
file. Producer failure, loss of the source hold, full disk or failed metadata
write cannot publish a successful archive. Only cache and `data/transcodes` are
excluded. Never remove SQLite WAL/SHM or plugin lock files from the live source.

Then dispatch `delete-reader` on the runner. It verifies the recorded UID and
uses a Kubernetes UID deletion precondition; it cannot delete a replacement pod
that reused the name. A failed capture still needs this explicit owned cleanup.
The laptop itself performs only read-only source access and local restore work.

## Restore acceptance

Prefetch the **exact** current Jellyfin image before the outage. Do not substitute
an upgrade while testing migration. First extract into a new private directory:

```sh
python scripts/storage/jellyfin_backup.py verify-files \
  --archive /home/benf/Backups/homelab/jellyfin/REVIEWED-UTC-STAMP/config.tar \
  --scratch /home/benf/Backups/homelab/jellyfin/REVIEWED-UTC-STAMP/files-restore
```

Archive traversal/escaping links are rejected. File hashes, ownership, modes,
links, timestamps and xattrs/ACLs must match the pre-stream inventory. Metadata
that cannot be preserved is a failure; use an appropriately privileged local
restore environment instead of silently dropping it. SQLite integrity opens only
the extracted copy, including any WAL. Plugin files must be present too.

Use a second restored copy for the application check:

```sh
python scripts/storage/jellyfin_backup.py verify-application \
  --archive /home/benf/Backups/homelab/jellyfin/REVIEWED-UTC-STAMP/config.tar \
  --scratch /home/benf/Backups/homelab/jellyfin/REVIEWED-UTC-STAMP/app-restore \
  --api-key-file /private/jellyfin-api-key
```

The container has no external network, GPU or production mounts. It must become
exactly Healthy, identify the existing server rather than a setup wizard, and
match users/catalog/plugin loading to the private pre-hold baseline. Only then
is `passed.json` written. A file-level pass alone does not open cutover. Keep
private logs and counts out of published evidence. No real application restore
has been claimed from synthetic tests.

## Placement and recovery

The external authorization binds the native-record hash, namespace UID and one
worker hostname, node UID and SMBIOS UUID. A protected namespace stamp is needed
because Kubernetes CEL does not expose namespace metadata.uid; Namespace CREATE
rejects replayed stamps. Only the external verifier/admin trust boundary may
write the stamp. Do not put it or a released authorization in Git. Required pod
affinity contains one term with all three worker identities. Direct pod
prebinding is denied, and only the scheduler may create media pod bindings.

Before moving, hold the workload and admission, prove the old mount and CSI
session are gone, then verify/authorize the next worker. If unreachable, confirm
the exact old VM is powered off using fresh API identity/status checks. Never
interpret RWOP, NotReady or an old receipt as writer exclusivity. A fresh cluster
has no authorization and remains held until external recovery verification.

## Acceptance and rollback

Acceptance requires the Healthy body, existing catalog/users/plugins, watched
and resume state, direct play, hardware transcoding, seeking, new progress writes,
and one clean cross-worker move with unchanged database identity. Check SQLite/
I/O errors and readiness/storage latency against baseline. Verify at least
25 GiB worker free space and room beyond eviction thresholds before allocating
the 10 GiB shared cache/transcode volume with a 12 GiB ephemeral budget.

Before the target first opens writable, source rollback may use the untouched
original NFS config/cache after proving the target has no writer/session. Once
Jellyfin opens the target, assume it wrote data: hold/stop or fence, make a fresh
cold target backup, and restore to a **new NFS directory and retained claim**.
Never restart the stale original or merge databases. Corrupt latest state
requires an explicit restore-point/data-loss decision. Preserve both original
source and ZVOL until acceptance and a separate cleanup approval.


## Generate sequential review artifacts

Group D merges tools only; it does not stop Jellyfin. The separate source-held
PR is an outage artifact: merging it scales Jellyfin to zero, closes its ingress,
suspends its LDAP job and denies new source writers. Keep that PR draft until the
window is agreed. Generate it without native IDs:

```sh
python scripts/storage/jellyfin_stages.py source-held --output /private/source-held
```

The generator copies the entire service definition, preserving both original PVC
manifests. After native onboarding, a successful independent cold restore and the
explicit one-time initialization below, generate target-held and target-released
in separate fresh output directories with `--record`, `--node`, `--passed` and
`--sealed-chap`. These inputs are respectively the completed native/filesystem
record, reviewed next-worker generation, laptop `passed.json`, and the actual
SealedSecret produced by `scripts/seal.sh`. Inspect every diff and render it before
committing. Do not commit private baseline counts, plaintext CHAP, namespace
stamps or authorization ConfigMaps. Target stage generation rejects allocation
intents and incomplete restore evidence.

Record all actual immutable commit SHAs in `stages.json` outside Kubernetes.
Deploy target-held first. The external verifier checks that exact Argo revision
and Bound PV/PVC identity, closes authorization while probing, then writes a
permanent `target-may-have-written.json` **before** publishing permission. The
receipt is deliberately conservative: a failed release can still make the old
source ineligible for rollback. Never delete/reset it to make rollback pass.
Target-released changes replicas to one but leaves public ingress closed and the
LDAP job suspended. Use restricted operator access for acceptance; reopen ingress
and resume the job in a later reviewed acceptance commit.

For a worker move, make a new target-held commit for the new reviewed generation
and update its recorded SHA. Stop/unmount the old writer, hold authorization,
verify/fence as required, authorize the next generation, then release its matching
Git state. A new cluster begins held because the external authorization is not
in Git. A destroyed/recreated old VM needs explicit retirement reconciliation;
the current command only accepts a reachable clean old generation or the same
old generation currently verified stopped. It refuses to guess from a reused VMID.

## One-time initialization review gate

Native onboarding creates a blank LUN; it does **not** format it. The regular
verification/release command intentionally rejects it. The actual destructive
format/copy command sheet is a later review artifact, generated against the
returned native record and approved cold archive, not a runnable placeholder in
this preparation PR. Before executing that sheet under the same external lock:

1. Require the source-held SHA, cold restore receipt and exact NAS source snapshot
   GUID/path from fresh API reads. Verify all other source/target consumers and
   API writers are stopped. Both workers must prove no target session/mount, or
   the uncertain exact generation must be fenced. No force deletion.
2. On only the reviewed worker, log in using the returned IQN/LUN and owned CHAP
   session. Verify exported serial/NAA, 64 GiB capacity, no partitions, no mount
   and no filesystem/signature with independent readback. Preserve an exclusive
   intent receipt before formatting. An existing intent means reconcile, never
   repeat `mkfs` after a lost response. Never use a force-format option.
3. Create ext4 only on that newly allocated verified device. Record its actual
   UUID and a generated service UUID marker. Mount the cold NFS subtree read-only
   and the target only for maintenance. Copy the full config with numeric
   ownership, links, ACLs and xattrs, excluding only the two disposable paths.
   Check both copy-process exit statuses. Require persistent data below 70% of
   usable ext4 capacity and compare every file/metadata entry to the independently
   verified source inventory. Keep the original source untouched.
4. Write `.retained-volume.json` containing only service, marker and
   filesystem_uuid. Flush, unmount cleanly, log out only the owned session, then
   run the normal read-only native/filesystem/SQLite-copy verifier. Preserve
   intent and errors on failure; do not automatically repair or start Jellyfin.
5. Only the resulting completed record can generate static bindings and the two
   target Git revisions. Review/seal/commit these during the scheduled hold.

This gate is not claimed complete by fixture tests. Actual target commit IDs,
initialization commands with returned device identity, and post-write NFS rollback
bindings cannot be fabricated before those live identities and restore evidence
exist. Their preparation and review are required before target release.
