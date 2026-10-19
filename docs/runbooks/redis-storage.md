# Redis retained storage

Status: active on retained CSI since 19 October 2026. See the
[production acceptance report](../superpowers/reports/2026-10-19-redis-immich-production.md).
Live values and static bindings are committed; the separate `production/`
fragments remain reference and qualification inputs, not an activation switch.

## Normal operation and rebuilds

Redis uses the stock upstream Proxmox CSI driver with a statically prebound
2GiB ext4 RWOP/Retain image, owner9999, cache none. Terraform does not own this
image. A normal cluster rebuild recreates the Kubernetes objects and reuses the
same image. The retained-data init guard validates the marker and complete native
AOF layout before stock Redis starts. Missing/wrong/empty storage blocks startup;
there is no dynamic fallback or empty initialization.

The default application password and data permissions stay unchanged. Native ACLs
deny application `CONFIG SET` and `ACL`; a distinct `homelab-maintenance` account
permits maintenance. Both accounts are declared by the sealed `redis-server-acl`
Secret on every startup. AOF uses `appendfsync everysec`. Alerts cover AOF being
disabled or unhealthy. This does not promise zero loss after an abrupt power
failure: Redis's normal every-second fsync policy still applies.

## Completed one-time migration

The following sequence describes the completed migration. Normal rebuilds do not
repeat it. The private operation audit preserves the original packet, its
102-file source mirror, qualified amendments and native phase/outcome chain.
Its approvals, inputs, nonce and deadlines are historical evidence, not a
reusable execution procedure. A new recovery operation requires fresh inspection,
reviewed commands and its own authorization.

1. Verify source process, all configured/connected consumers, capacity and
   private recovery destinations. Install scoped Argo holds and admission
   protection. Prepare the sealed maintenance account and an exact-head CI-green
   activation PR before starting downtime. Previously paused Immich queues require
   additional startup qualification; the current qualified inventory has all19
   unpaused.
2. Hold external producers for Immich, Dispatcharr and Paperless. Stop native
   scheduled producers, pause/drain BullMQ and Celery, including scheduled ETA
   jobs, and retire all consumer Pods and overlapping source ancestors. Redis
   stays running.
3. Preserve historical disk state separately. Export current Redis memory to a
   fresh RDB and full binary-safe checkpoint; old AOF files are not memory proof.
   Encrypt and retain two off-NAS copies, then independently decrypt and restore
   the full dataset using the pinned native engine while the original stays alive.
4. Verify the new Secret, apply native ACL restrictions, enable AOF on the same
   original Redis process and wait for healthy rewrite/fsync state. Snapshot and
   independently restore that live AOF too. Only then gracefully stop Redis and
   prove every old writer absent from all three native runtimes/mount tables.
5. Snapshot/archive the cold source. Prove encrypted off-NAS recovery again,
   allocate the exact new image once, populate the complete POSIX tree, write its
   marker last and verify raw generation, binding, filesystem UUID and the current
   attachment WWN. Retire all copy helpers before recording target authority.
6. Merge only the tested activation head under the hold. Replace the exact
   stopped old StatefulSet because removing its claim template is immutable.
   Start only Redis, compare the full frozen dataset and healthy AOF, then prove
   recreation, movement between healthy workers and restored normal placement.
7. Release consumers only after those checks. Verify recreated Celery worker
   roles and complete queue definitions; restore BullMQ's original global pause
   flags. The accepted Dispatcharr DVR reset applies only after full preservation
   passed and stock web startup resumes. Restore frontends, synchronize complete
   current revision vectors with original sync options, then release automation
   under a six-minute continuous native watch.
8. Remove exact owned temporary helpers/plaintext, retain recovery and source
   media, audit final identity and release the original maintenance owner last.

The stock driver derives WWN from the VM SCSI slot. Correlate each current WWN
with that attachment and its guest device; it is not a persistent disk identity.
The raw image generation, CSI handle, PV/PVC identities and filesystem UUID must
stay fixed across movement.

Redis stream recovery compares every persisted field, entry, group, pending
delivery, consumer and absolute expiration. Only the top-level internal
`radix-tree-nodes` count is excluded: it must still be present exactly once as a
nonnegative integer. The native restored dataset passed all 55 keys; altered
payloads or other metadata remain failures.

## Failure and recovery

A lost RPC reply is an unknown outcome, not a failed mutation. Inspect the original
native child and terminal through `transport.Session.inspect(key)`. Continue only
unfinished commands after the exact original outcome is known. Do not resubmit a
mutation under a different label, recreate ownership or renew its clocks. A known
successful initialization is adopted read-only. A failed native command requires
inspection; it is not automatically replayed.

Before current-memory and live-AOF recovery pass, keep Redis alive. Do not restart
it from historical disk or blindly restart Dispatcharr's web process, which can
reset DVR queues. After AOF has been enabled, a later failure must not disable it.
Before target authority, returning to the original source requires proving target
writers fully retired and validating the source/recovery point under the original
owner. If the original process was stopped, use only accepted current recovery,
not its earlier stale files.

After the `target-authority.json` boundary, the retained CSI image owns all new
writes. Never reopen stale NFS state or bypass its permanent source Pod policy.
Retire target writers before recovery, preserve the current raw image, and recover
the target from a validated current backup under a separately reviewed recovery
procedure. Never force detach or delete a disk to clear a failed operation.

The original source PVC/PV, NFS data, snapshots, retained target, encrypted copies
and separate keys are deliberately preserved. Temporary plaintext and binary
staging logs are cleaned by exact owned inventory, not broad path matching.
