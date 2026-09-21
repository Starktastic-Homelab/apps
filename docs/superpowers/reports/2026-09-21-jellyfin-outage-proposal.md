# Proposed Jellyfin cold-migration window

## Approval and trigger

Apps #1237 is merged. Apps #1238 is the outage trigger and must remain draft
until the user approves the window. The operator acquires the persistent shared
maintenance lock before the user merges #1238. Neither this document nor the
preparation checks authorize stopping Jellyfin now.

Reserve two hours for the supervised window as a planning allowance, not a
promised recovery deadline. The operator reports progress and unresolved gates.
At 90 minutes, reassess remaining work: before target writes, prefer restoring
the untouched source through a reviewed Git rollback if completion is uncertain.
After possible target writes, follow the fresh-target-copy rollback path; never
restart stale source data merely to meet the time allowance.

## Visible effect and scope

Only Jellyfin is intentionally unavailable. Existing playback will stop. Public
ingress closes, the Deployment has zero replicas, and LDAP library-sync jobs are
suspended. Existing jobs and config consumers must finish or stop cleanly.
Other applications and all VMs remain running. No production fencing or forced
pod deletion is part of the planned path.

The source PVCs and their data remain retained. The hold installs an admission
policy that permits only the constrained read-only backup reader on the original
config claim. No iSCSI binding, formatting or target writer is created by #1238.

## Fresh checks before the hold

- Confirm the current source PV/PVC identities, exact image, application health,
  users/catalog/plugins and server identity privately; record active sessions.
- Confirm available encrypted laptop space, exact local restore image, worker
  headroom and current worker/namespace identities. Recheck NAS volume identities
  against the retained native record, snapshot policy and storage service.
- Acquire new shared maintenance ownership on VM300. Record the original owner
  privately and preserve it through all stages; never reuse a completed lock.
- Resolve the two old Failed Jellyfin pod records only after proving their exact
  containers and mounts are inactive. Delete only by verified UID under ownership,
  without force. Their mere presence blocks the conservative reader guard.

The observed running pod at preparation was `jellyfin-74f576499d-2c78f`, healthy
with zero restarts. The old/new ReplicaSet difference shows an explicit
`kubectl.kubernetes.io/restartedAt` change at 20:50:07 UTC; the application
specification and pinned image are otherwise unchanged. Re-read this baseline at
window start rather than treating this observation as permanent authorization.

## Execution checkpoints

1. After user merge, verify the exact source-held Git revision, stopped writers,
   suspended/completed jobs and closed ingress. Record a fresh source snapshot.
2. Stream the full held configuration to the encrypted laptop, preserving WAL,
   plugin state, ownership, links, ACLs and xattrs. Only cache and transcodes are
   disposable. Remove the owned read-only reader using its exact UID.
3. Independently verify the archive and a separate same-image application restore.
   A failed restore stops progression; no format/copy is permitted on that basis.
4. Present the final initialization command sheet with the actual native/device
   identities and passed cold-restore receipt before execution. Preserve an
   exclusive durable format intent. Refuse nonblank, mounted, mismatched or
   concurrently owned devices; never use forced formatting or repeat an uncertain
   format. This is the remaining explicit destructive-action review gate.
5. Under the same ownership, initialize only the approved target, copy and verify
   all persistent state, record the returned filesystem UUID and marker, cleanly
   unmount/logout, and run the normal read-only target verification.
6. Seal actual CHAP and generate/review target-held and target-released revisions.
   User merges them in order; external authorization binds exactly one worker
   generation. Public ingress and LDAP writes stay closed for operator acceptance.
7. Verify health, catalog/users/plugins, progress state, direct play, hardware
   transcode and seek. Reopen service through a reviewed acceptance change. Complete
   clean worker handoff, independent target backup/restore and 24-hour observation
   before declaring the pilot accepted.

## Rollback and retained evidence

Before target write authorization, keep the original NFS config as the recovery
source, prove target quiescence, and restore the pre-hold service definitions via
a reviewed Git change. After the conservative first-write receipt, the NFS source
is stale: hold the target, take a fresh cold target backup and restore to a new
NFS directory and retained claim. Never merge databases or silently choose an
older restore point. Preserve source, target, journals and independent archives;
cleanup requires a separate decision.
