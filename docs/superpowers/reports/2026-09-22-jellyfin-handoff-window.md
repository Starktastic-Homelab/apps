# Jellyfin cold target backup and clean worker handoff

## Boundary and outage trigger

Prepared at the user's request; **the next maintenance window has not started**.
The associated draft PR is the outage trigger. Do not merge it before explicit
window approval and fresh preflight. It closes public ingress, suspends LDAP,
sets replicas to zero and selects the exact worker 01 generation. It does not
change the image, PV/PVC, filesystem, CSI driver, CHAP, or data.

Jellyfin is currently running on worker 02 after Apps #1244. Public HTTPS health,
operator playback/progress/seek/resume and hardware transcoding passed. Initial
migration acceptance is complete; clean handoff, independent target restore and
24-hour observation are still pending. Scheduled snapshot execution has now been
verified separately; it does not establish SQLite-consistent backup or restore.

Reserve two supervised hours as a planning allowance, with reassessment at
90 minutes. Playback stops during the window. Other apps and all VMs remain
running. No VM fence, reboot, forced pod deletion, formatting, automatic repair,
or old-NFS restart is part of this procedure. If clean quiescence cannot be proved,
stop and reconcile rather than broaden the authorization.

## Verified preparation (22 September 2026, UTC)

- Native retained-volume identity passed a fresh read-only NAS inspection.
- TrueNAS task 2 is enabled, recursive on `apps/iscsi`, every six hours, retaining
  one week. Its last state was FINISHED; the Jellyfin child has the actual
  `auto-2026-09-22_12-00` snapshot (also 06:00 and 00:00).
- Both workers have open-iscsi 2.1.11, e2fsprogs 1.47.2, active iscsid and their
  enrolled role IQNs. Worker 01 has no iSCSI session; worker 02 owns the live
  Jellyfin session. Both expose GPU resources.
- Worker 01 initially had only 25.03 GiB free and no cached Jellyfin image. Removed
  exactly two freshly verified unused, unpinned image caches (Stirling PDF and
  Dispatcharr), without deleting containers, volumes or application state; then
  prefetched the exact current Jellyfin digest. After pull, 30.91 GiB was free.
  Recheck free space immediately before the window and
  require at least 25 GiB and 12 GiB budget above the
  configured 5% disk eviction threshold are hard gates.
- Approved encrypted laptop backup filesystem had approximately 650 GiB free.
  Keep the accepted original archive and restore evidence. Use a new private UTC
  directory for this target archive and two independent restored copies.
- Original external runner ownership is still held. Runner SSH works; worker 01's
  host key was independently read through the verified Proxmox guest route and
  pinned. Do not depend on VM300's unresolved QEMU guest-agent channel.

These are preparation observations, not reusable release authorization.

## Exact identities

| Item | Reviewed value |
| --- | --- |
| Previous worker | kube-worker-02 / VM202 |
| Previous node UID | 63d963c8-0c04-4be8-81a3-07e8aa1cc240 |
| Previous SMBIOS UUID | d6c40da9-aaa5-4b5c-a9ce-70d3cfdcc4b4 |
| Next worker | kube-worker-01 / VM201 |
| Next node UID | ed4cb64c-0c87-414e-9538-110650ba2f34 |
| Next SMBIOS UUID | 8b2aa6c7-b54f-4323-9900-bdbb85098f62 |
| Media namespace UID | 232b7682-582d-46ac-aec5-10574a235f6e |
| Dataset | apps/iscsi/jellyfin-config |
| ZVOL GUID | 14950202402923644020 |
| Filesystem UUID | d3cc0be9-ad2f-4c67-a6fc-abc6104b7712 |
| Service marker | 19b50cf8-a026-408e-83df-521d13bec20b |
| Native record SHA256 | 6515cd395753fde8bb5e4a29533d1efcc9a8d9407548b49e9957cc997d3ad5e6 |
| Claim / volume | media/jellyfin-config-iscsi / jellyfin-config-iscsi |

The original migration operation is
`/var/lib/homelab-maintenance/operations/jellyfin-migration-20260922T055644Z`.
Continue its original owner/nonce; never acquire replacement ownership or delete
its first-write receipt. Stage new tools beside `release-tools`, preserving the
old execution evidence. New verification must include the merged Apps #1243
`node-db.node.session.auth.*` CHAP mapping; the old staged verifier is obsolete.

## Window execution sheet

1. **Before merge:** refresh the private API baseline, active playback count,
   public health, exact image digest, node/namespace identities, worker free space,
   runtime image presence, runner SSH/ownership and native NAS record. Require
   the exact image locally for the independent application restore. Inspect the
   actual PR diff and all required checks. Refresh credentials only through private
   files. Record a new window start and the agreed time allowance.
2. **Hold:** user merges the draft. Record the actual resulting main SHA, not the
   PR head, as `target-held` only after Argo reconciles it. Wait for the Jellyfin
   pod to terminate and LDAP jobs to finish; verify ingress is absent and replicas
   are zero. Under original ownership, run the reviewed `hold` operation to close
   `retained-jellyfin-authorization`. Verify both claims have no remaining pod
   consumers. Require the old generation to be reachable and prove all target
   mounts and its CSI session are gone. No manual logout beneath a mount.
3. **Fresh recovery point:** create one uniquely named snapshot of the exact
   Jellyfin ZVOL after quiescence. Journal intent before creation and inspect its
   returned GUID; a lost reply requires read-only reconciliation, not another
   create. This cold snapshot supplements the independent backup below.
4. **Read-only capture:** on worker 02 only, the original locked runner performs
   the prepared one-time login/mount sheet. It refuses existing sessions, node
   records or operation receipts; verifies serial/NAA/capacity, no partitions or
   holders, ext4 UUID and clean superblock; then mounts the target at
   `/mnt/jellyfin-handoff-readonly` with `ro,noload,nodev,nosuid,noexec` and verifies
   the marker. CHAP travels through stdin into the reviewed credential helper,
   never arguments. Preserve intent and mount ID. An uncertain reply stays held.
5. **Independent archive:** use the prepared `capture-target.py` sheet on the
   laptop, with new metadata containing the actual held SHA, cold snapshot GUID,
   native ZVOL identity, image and fresh private API baseline. It inventories and
   streams numeric-owner tar directly over pinned SSH to the approved backup root.
   Its live guard checks original ownership, exact Git/bindings, zero replicas,
   closed authorization/ingress, inactive LDAP, no PVC consumers, the exact
   read-only mount/marker and no worker 01 session. It records bytes as
   `held-live-iscsi-readonly-mount`, never as NFS or snapshot bytes. Only cache and
   transcodes are excluded. A failed guard/producer leaves unaccepted partials.
6. **Clean capture session:** under original ownership, verify the recorded mount
   ID, filesystem UUID and marker again, unmount that exact mount, and only after
   successful unmount log out/delete the session/node record created by this
   operation. Verify no target mount/session on either worker. Preserve receipts.
   Do not remove/retry an ambiguous login or mount intent without reconciliation.
7. **Independent restore:** run `jellyfin_backup.py verify-files --archive ...
   --scratch .../files-restore`, then `verify-application --archive ... --scratch
   .../app-restore --api-key-file ...` on separate copies on the encrypted laptop.
   Require files/metadata, SQLite integrity including WAL, existing server identity,
   users/catalog/plugins and same-image application health. Preserve accepted hash
   and `passed.json`. No successful restore is claimed during preparation.
8. **Authorize the new worker:** replace the canonical placement only while held:
   previous=worker 02, next=worker 01, `old_writer_mode=clean-unmount`. Preserve the
   previous placement and stages. Use the newly staged verifier to re-read native
   identity, old-generation quiescence, next-generation identity/headroom, CHAP and
   the target filesystem read-only on worker 01. Its private SQLite copies must
   pass. Release authorization only from fresh complete evidence; preserve the
   existing first-write receipt. No image or filesystem upgrade is allowed.
9. **Start and accept:** user merges the separate reviewed release revision
   (replicas one, exact worker 01 affinity; ingress/LDAP still held). Verify the
   actual node, ext4 UUID/marker, health, unchanged server/users/catalog/plugins,
   SQLite/I/O logs, direct play, progress, seek/resume and real GPU transcode.
   Then user merges the separate reopening revision. Confirm public HTTPS,
   LDAP schedule, readiness and restart count.
10. **Observe:** record the post-handoff public-restoration time as the start of
    the qualifying 24 hours. Review restart counts, storage/SQLite errors, latency,
    cache headroom and snapshot execution across the interval. An observation
    start time alone is not 24 hours of evidence; no background monitor has been
    assumed or installed by this preparation.

The private execution bundle is staged beside the original runner operation as
`handoff-preparation/`, with SHA256s and the base Git commit recorded. Its local
copy is `/tmp/jellyfin-handoff-prep`; preserve it on the approved encrypted backup
filesystem before relying on it. All sheets must run with ordinary `python3`,
without `-O` or `PYTHONOPTIMIZE`. The mount sheets are not standalone entrypoints:
use `window-mount.py mount --metadata PRIVATE-METADATA.json`, which first checks
the current hold and then dispatches only through original runner ownership.
Cleanup uses the corresponding `window-mount.py unmount` command and verifies
both the recorded mount ID and session listing. Capture uses:

```sh
python3 /tmp/jellyfin-handoff-prep/capture-target.py \
  --metadata PRIVATE-METADATA.json \
  --destination /home/benf/Backups/homelab/jellyfin/NEW-UTC-STAMP-cold-target
```

The literal metadata and destination placeholders are filled only after the
fresh cold snapshot and actual merged hold SHA exist. Prepared sheets compile;
a live negative guard test refused the currently running application before any
mount/session action. Successful execution remains a window-time gate.

Release/reopen file previews are prepared privately but are not deployed or
valid release commits yet. Actual held/release/reopen SHAs and the new snapshot
GUID cannot be recorded before their respective live steps.

## Failure handling and stop point

The preparation turn stops with the draft unmerged, replicas one, public ingress
open, LDAP enabled, the original writer authorization unchanged and worker 02's
CSI session intact. Fresh live gates will expire and must be repeated.

If backup or worker 01 acceptance fails, keep the workload held while assessing.
The preferred recovery is the **same current iSCSI volume** on worker 02, after
proving worker 01 has no writer/session and freshly verifying/re-authorizing
worker 02 through reviewed held/release Git revisions. Never reuse an old
released authorization. An uncertain writer is a stop condition.

The old NFS directory is stale. NFS rollback would require a fresh accepted target
backup, a new NFS directory and retained claim, and separately reviewed manifests.
A corrupt latest target requires an explicit restore-point/data-loss decision.
Neither source nor ZVOL cleanup is authorized by this window.
