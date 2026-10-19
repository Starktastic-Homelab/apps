# Redis and Immich retained-CSI production acceptance

Completed on 19 October 2026. Redis and Immich's dedicated PostgreSQL now use
static retained Proxmox CSI images. Their separate native operation owners were
released only after recovery qualification, production lifecycle checks, full
GitOps reconciliation, a six-minute health watch and exact temporary cleanup.

## Final state

| Workload | Accepted storage and behavior |
| --- | --- |
| Redis | 2 GiB ext4 RWOP/Retain image, external owner 9999, cache none; pinned existing Redis/exporter images; AOF enabled with `appendfsync everysec`. |
| Immich PostgreSQL | 10 GiB ext4 RWOP/Retain image, external owner 9999, cache none; original PostgreSQL 17.6 / VectorChord 0.4.3 / pgvector 0.8.1 image and physical system identifier `7614955115223928876`. |
| Immich files | Photos/videos and model cache remain on their existing NFS paths. |
| Redis access | Existing application passwords preserved. Default-account `CONFIG SET` and `ACL` are denied; a separate sealed maintenance account provides administration. Durability alerts and exporter coverage are active. |

The unmodified upstream CSI driver and normal Terraform/Ansible rebuild procedure
remain in use. Static Git bindings reconstruct Kubernetes metadata around the
retained images; a normal rebuild does not repeat this migration or require a
Velero checkpoint. Missing/wrong/empty storage is rejected by the startup guards.
This operation tested Pod recreation and movement between existing workers; it
was **not a production Terraform destroy/apply rehearsal**.

## Production evidence

- Redis recovered and compared the complete current-memory export before any
  source restart. Independent memory, live-AOF and cold recoveries passed using
  the pinned native engine. Initial target startup, recreation, worker movement
  and return to normal placement each preserved all 55 keys, with zero unexplained
  losses or accepted expirations. AOF, native ACL restrictions and exporter
  durability remained healthy with consumers running.
- Immich established a coordinated database/photo recovery point while all 21
  overlapping writable workloads were paused. Both dataset snapshot identities
  were confirmed before the 19 unrelated media workloads resumed. Filebrowser
  and the NFS provisioner resumed after the cold database archive and recovery
  checks. Separate pools were snapshotted sequentially under the writer barrier;
  this is not an atomic cross-pool snapshot claim.
- Immich's cold physical recovery preserved the original PostgreSQL identity.
  Independent logical recovery used a different physical identity and passed
  the unchanged complete schema, rows, roles, extensions and sequence-floor
  comparisons after restoring complete native sequence definitions on that
  disposable clone. Production data and schema were not altered by this fix.
- Initial startup, Pod recreation, cross-worker movement and normal placement
  each passed the full native PostgreSQL comparison. Raw image generation,
  filesystem UUID, CSI handle and PV/PVC identities stayed fixed. Every old
  writer/helper was natively retired before the next attachment; no force
  detach, empty initialization or missing-disk fallback was used.
- Redis reconciled all 7 scoped owners; Immich reconciled all 23. Each accepted
  manual sync bound the complete current revision vector, original sync options
  and exact application identity to successful native deployment history.
  Normal automation then passed separate 360-second watches: Redis
  75 events; Immich 53 events.
- An existing original photo passed its real authenticated API metadata and
  streamed content checksum check after each release. The 4112724-byte original
  matched its recorded checksum; no photo file was saved or API credential
  transferred to a helper, guest or recovery engine. The temporary read key was
  revoked and its private local file removed after acceptance.

## Explicitly accepted and qualified details

The user approved stock Dispatcharr DVR queue resets **after** full Redis
preservation passed. No Dispatcharr startup override was introduced. The stuck
Paperless scheduler was forcibly stopped only after separate approval, while
all Redis queue-preservation checks remained in force.

Native Redis restore reconstructs its radix tree. The approved comparator
excludes only the top-level `radix-tree-nodes` count, requiring exactly one
nonnegative integer counter. Entries, groups, pending owners/delivery state,
consumer metadata, other fields, key inventory and absolute expirations stay
strict. The original rejection remains in the private audit; successful recovery
was rerun under a distinct known native outcome.

The stock driver's WWN follows the VM SCSI slot. Both migrations correlated each
current attachment WWN to its actual guest device while keeping persistent image
and filesystem identities fixed. An old attachment WWN was rejected by the
unchanged native device checker. No upstream driver modification was needed.

Immich's forced move initially met worker02's real 24-volume limit. The user
approved one additional Lingarr pause. Lingarr's exact Pod/runtime/mount and disk
reference retired, the already-pending Immich Pod used the freed slot, and the
full movement checks passed. Lingarr resumed on worker01 with its original
replica count/placement policy and the same retained disk. The driver limit is
unchanged; future movement and drain plans must check per-worker attachment
capacity as well as aggregate NAS space.

Qualified continuations also handled a books-only NFS staging mount without
mistaking it for an Immich photo writer, preserved the original two-pool writer
barrier, and waited through API ordering between completed deployment history
and its operation status. A lost/failed reply was inspected; successful mutations
were adopted rather than repeated. Original failures, inputs, ownership and
clock records remain retained. The user explicitly authorized late continuation;
that did not silently rewrite the original clocks or data-safety rules.

## Retained recovery and cleanup

Both original NFS claims/PVs/data trees and immutable checkpoint snapshots remain
preserved and protected against accidental reuse. After each recorded authority
boundary the CSI image owns new writes: never reopen a stale NFS database as an
ad-hoc rollback. The retained targets, two encrypted off-NAS recovery copies
(VM300 and this computer), separate recovery keys and private native audit remain.

Only exact owned helpers, temporary plaintext archives/exports, restore resources
and temporary ACL material were removed. The Redis sealed maintenance credential
and its separate private recovery material remain intentionally retained. The
Immich read key cleanup did not change the existing statistics-only key.

## Repository delivery and checks

[Preparation PR #1403](https://github.com/Starktastic-Homelab/apps/pull/1403),
[Redis activation PR #1404](https://github.com/Starktastic-Homelab/apps/pull/1404) and
[Immich activation PR #1405](https://github.com/Starktastic-Homelab/apps/pull/1405)
were merged through their required CI gates. The final delivery records this
accepted state and promotes the approved Redis comparison correction.

The correction passed 16 state-contract tests and all 8 disconnected native Redis
qualification tests, including current-memory/AOF recovery, actual queue
recovery, ACL persistence, exporter durability, corruption and stock tail
handling. Each native fixture verified exact labeled cleanup. The final PR must
also pass repository CI before merge. No plaintext application records,
credentials, private keys or recovery payloads are committed.

The private audit is rooted at
`.superpowers/sdd/2026-10-18-redis-immich-retained-csi/`, including the immutable
102-file original code/metadata mirror, qualified operator bindings, original
failed outcomes and accepted phase chains. It is historical evidence, not a
reusable approval. Paperless's private index and Calibre's split-library
qualification remain separate follow-ups; ordinary files without a demonstrated
block-filesystem requirement stay on NFS.
