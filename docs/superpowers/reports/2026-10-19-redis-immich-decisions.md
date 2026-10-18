# Redis and Immich preparation decisions

These are the implementation rulings recorded during the approved preparation,
in order, including their trade-offs. They do not grant production authority.

- Ruling: Normalize plan Task1 headings to Task 1 for the installed task tooling — wording only; cost if wrong: none to behavior.

- Ruling: Retain the private executable packet and its receipts after final review — the approved spec requires them for later execution; deleting them would discard the reviewed operation. Cost if wrong: private scratch remains on disk.

- Task 1: Ruling: Compare missing keys against the actual capture’s native start time, not a later comparison time — the example otherwise excuses a key already missing before expiry. Cost if wrong: a capture spanning an expiry may need repeating, rather than silently accepting unexplained loss.

- Task 1: Ruling: Run native redis-check-aof on full scratch copies — the exact checker opens r+ without --fix, so it cannot read the retained read-only mount directly. Original data remains read-only. Cost if wrong: startup needs scratch disk and copy I/O up to the retained AOF footprint.

- Task 1: Ruling: Permit native manifest history entries but check/copy only the active base and increments — history may reference already-collected files and is never loaded by Redis. Stock native loader still validates the whole manifest before readiness. Cost if wrong: an unused historical record does not itself trigger startup refusal.

- Task 1: Ruling: Keep qualified stock Redis final-increment recovery under the already accepted everysec policy. Guard checks identity, paths, base and earlier increments; the native main loader decides an invalid final increment, recovering an incomplete tail and refusing bad format. No --fix or guard writes to retained data. Full migration checkpoint remains mandatory before acceptance. This follows the spec’s qualified-native-unclean-end allowance. Cost if wrong: stock crash recovery may discard an incomplete final command within the accepted fsync window; this is explicit in the execution proposal.

- Task 2: Ruling: Omit only the exact duplicate CREATE of the independently initialized logical fixture’s known bootstrap role — native ALTER ROLE statements still restore every attribute and password verifier, and full global-state comparison must pass. Cost if wrong: logical restore is refused; it cannot waive role differences.

- Task 2: Ruling: Reject all external data symlinks/foreign tables for this dedicated closed-root cluster — the current approved cold-copy design has no external WAL/tablespace roots. Any newly discovered external root blocks execution for review. Cost if wrong: unusual but recoverable layouts require an explicit expanded copy contract.

- Task 3: Ruling: Materialize three scoped Immich value deletions before the ordinary layered render — upstream app-template rejects null fsGroup, and empty overlays do not delete the existing service key. The active source remains untouched and all other rendered workloads must match. Cost if wrong: render/schema/preservation gates refuse the candidate; activation must apply the same reviewed deletions.

- Task 3: Ruling: Match synthetic Redis to the actual chart’s module configuration and live UID/GID1001:1001 instead of the image’s broader defaults — read-only MODULE LIST exposed the difference; native and rendered-config tests now require the deployed set. Cost if wrong: configuration drift blocks qualification rather than claiming image-only evidence covers the chart.

- Task 3: Ruling: Run native recovery in a separate CI job and make required Validate run an explicit success gate afterward — the existing fifteen-minute job already has broad checks; this preserves its timeout and makes native failure block the existing required check. Cost if wrong: CI takes the added native job time before normal validation; no branch-protection change is needed.

- Task 4: read-only preflight exposed unlabeled NFS provisioner; exact Argo tracking annotation and current Application resource membership establish ownership, rather than assuming a release label. Capacity-only observation succeeds40files/288GiBquota. Whole asset-directory size walk did not return an accepted native terminal; later process inspection found no du reader. Ruling: use dataset GUID/mountpoint/used/referenced/available for the coordinated ZFS asset snapshot strategy, not an unnecessary full photo-tree size walk — no full asset copy is proposed and snapshot retention cost is stated separately; cost if wrong: future COW retention needs review, not a fabricated directory-size claim. No production change.

- Task 4: Ruling: use a temporary owned Service selector hold for external producers while native workers drain, rather than stopping web service processes inside still-probed Pods — avoids liveness-triggered restart during quiescence; source Pods still must stop and every configured/connected writer retire before capture; cost if wrong: endpoint drain alone is insufficient, so full subsequent native source/client retirement remains mandatory. This is preparation within the approved outage scope, not a live Service change. Implement remaining assembled control/transport/phase code and runbooks before final review.

- Task 4: Ruling: keep the Argo secret read bounded and memory-only inside the already privileged master process — persisting secret stdout as a child log would expand credential copies; gates bracket this read, all mutations keep native child receipts; cost if wrong: an unproven read fails rather than exposing or redistributing the credential.

- Task 4: read-only physical primitive qualified against current Jellyfin CSI: one matching VM202/WWN/cache-none/ext4/raw identity and all-three-node absence for the old Evicted Pod UID. Ruling: terminal Kubernetes metadata is never retirement evidence — delete only captured terminal metadata during planned scale-down, then separately prove old UID/runtime/mount absence on every node; cost if wrong: checkpoint blocks instead of treating an API phase as fencing. No live deletion was performed.

- Task 4: Ruling: prepare the distinct maintenance credential and strict SealedSecret before starting the outage, using the existing password verifier rather than transferring its plaintext — use exact repository seal.sh and public pre-seeded certificate; verify controller unseal/data hashes under the owned hold before producers pause; cost if wrong: stop before outage and retain current source unchanged. The new credential stays in a separate PC key root and native Kubernetes Secret; no administrator login is copied. Actual generation, verifier transfer and live creation require the finished execution proposal.

- Task 4: Ruling: use target-only imperative application of the pinned reviewed database resources while Argo remains held — a full Immich sync would start consumers before native target comparison/lifecycle; cost if wrong: activation refuses or remains held, rather than permitting a preservation claim after queues have already run. Removing Redis's immutable claim template requires exact stopped StatefulSet replacement after source retirement, never PVC deletion or force replacement.

- Task 4: Ruling: verify recreated Celery roles/queue definitions against the original options instead of replaying process-local cancellation state into new PIDs — subscriptions restart natively with the new worker processes; preserve BullMQ's global pause flags separately; cost if wrong: consumer release blocks. Current qualified Immich flags are all19 unpaused; any originally paused queue now blocks before outage pending stock-startup qualification, rather than assuming its pause survives app startup.

- Task 4: Ruling: preserve the executable private packet after review — it is required to execute and inspect unknown outcomes; cost if wrong: ignored operational code must remain protected0700 and kept out of Git. Only exact temporary data/helpers are cleanup candidates; source/target media, immutable snapshots, ciphertext, keys and private audit receipts remain retained.

- Final: Ruling: require30minutes of original time before release, with unchanged clocks and an early soft-reserve stop — the independent review reproduced hold loss at deadline expiry; cost if wrong: a late healthy cutover stays held and needs a separately approved finish-window decision, instead of releasing without time for acceptance/recovery.

The independent final review identified two operational defects: exact staging
ownership during cleanup and original-time reserve before hold release. Both
were reproduced before correction and now have focused passing regressions.
A minor runbook statement was corrected to describe PG physical identity/native
data checks accurately; it does not advertise a startup marker check. No review
findings were set aside, and no minor item remains deferred.
