# Operations and home application storage

Karakeep (including Meilisearch), ByteStash, ConvertX and Home Assistant (including Matter) use six retained ext4 Proxmox CSI volumes. Excalidash and CrowdSec use the existing PostgreSQL service and recover their original credentials from Sealed Secrets. The preparation definitions in `scripts/operations-home-retained/production/` are inactive until copied into their normal Argo source directories during the approved cutover.

| Application | Retained state | Capacity |
| --- | --- | --- |
| Karakeep | SQLite application and queue databases, uploads and configuration | 4GiB |
| Meilisearch | Complete original index and version markers | 4GiB |
| ByteStash | Snippets database and all original data files | 2GiB |
| ConvertX | Database, configuration and original working files | 4GiB |
| Home Assistant | Recorder database, `.storage`, auth, integrations and custom components | 4GiB |
| Matter | Complete certificates, fabrics, server state and configuration | 2GiB |
| Excalidash | PostgreSQL; original JWT/CSRF identity in Sealed Secrets | Shared PostgreSQL |
| CrowdSec | PostgreSQL; original CAPI, LAPI, registration and bouncer identities | Shared PostgreSQL |

The unused inherited ByteStash `/config` claim is retained with its original source archive but is not attached to the migrated app. Excalidash's generated Prisma files are supplied by its unchanged image. Neither PostgreSQL-only app needs an application PVC.

## Rebuild behavior

Static PV handles refer to images owned by VM9999 on `k3s-block`; their lifetimes are independent of worker VMs. RWOP, verified VM retirement and native CSI attachment handling provide fencing. Keep all PVs/PVCs at `Retain`, and retain the original source NFS directories and cold ZFS snapshots. Never force-detach a disk or start an old NFS writer after the target has accepted production writes.

A fresh cluster recreates bindings, read-only retained-state guards, the existing PostgreSQL enrollment completion gate, and original application identities. File guards refuse missing/wrong markers or native state before the stock image can initialize an empty store. SQL guards require the existing physical PostgreSQL identity, native tables and nonempty identity state. They do not create or repair data.

Meilisearch starts only when the running binary and both retained version markers agree with the qualified 1.55.0 format. Its previous index-wiping wrapper is removed. A Meilisearch image upgrade requires a separate retained-index migration qualification and manual Renovate review.

Home Assistant keeps its host networking and Matter keeps `PRIMARY_INTERFACE=eth1` and its existing loopback listener. Recovery fixtures have no external route and override only the fixture's Matter interface to loopback; they cannot contact production devices. No deliberate device actions or CrowdSec remediation tests form part of acceptance.

CrowdSec preserves its native chart and TLS/agent/bouncer behavior. PreSync Sealed Secrets and a credential gate precede the unmodified upstream registration hook. Existing unmanaged credential Secrets are adopted by exact UID and value, with metadata-only changes. Repeated sync and complete namespace recreation were qualified to preserve original bytes without fresh external registration. The existing TLS configuration has no persisted cscli password Secret; none is invented.

## Cutover gates

The user authorized autonomous execution and PR merges for these six applications. The only accepted conversion loss is deterministic truncation of CrowdSec source timestamps below one microsecond. All other fields, rows, keys and identities must compare exactly. A failed or ambiguous gate preserves the current state and original evidence; an intent is never permission to replay a mutation.

The private native packet under this plan's ignored `.superpowers/sdd/` workspace must be complete, frozen and independently reviewed before downtime. It verifies installed maintenance runtime hashes, VM/cluster/controller/PVC/PV generations and all ten source/shared Argo owners before acquiring a fresh maintenance owner and execution exclusion. Original monotonic clocks allow two hours before each application's target authority and 24 hours for the cohort; a restart or failed attempt cannot reset them.

For each application:

1. Stop overlapping Filebrowser/NFS-provisioner ancestors, then all app writers. CrowdSec agents stop before LAPI. Prove API, CRI and kernel mount retirement on every node and install an exact old-source admission hold.
2. Snapshot and archive every original source with complete file/POSIX/hardlink proofs. Encrypt and independently decrypt recovery, preserve verified copies on VM300 and this computer with separate keys, then resume only the original ancestor controllers.
3. Restore a complete disposable copy, verify all active SQLite databases, and start the unchanged stock images without an external route. SQL apps additionally require complete typed conversion, native migration/allocator preservation, stock startup and an independent SQL dump/restore.
4. Before each of the six allocations, reserve full remaining growth of every active raw image, all new claims, staging and 8GiB spare against both the unchanged 256GiB quota and physical pool free space. Preserve the historical Jellyfin partial unchanged, accounting for its fixed actual allocation.
5. Populate file targets from the original immutable archives, verify every byte and POSIX field, create the identity marker only after equality, and prove helper and physical attachment retirement. For SQL targets, use only the dedicated role, verify the physical database and empty schema, import once, independently export/restore the actual target and compare every application field, native migration record and allocator. Protect a separate encrypted SQL recovery on both media before authority.
6. Merge only the intended activation PR after exact-head hosted checks and Argo diff review. Compare complete current-Git workload/configuration with the frozen candidate. Mark authority before the first request permitting a writer, then sync only that app while the remaining owners stay held.
7. Verify native probes, guards, original Services/endpoints, retained physical identities and credentials. Prove Pod recreation and healthy worker movement for worker apps, then remove the temporary placement pin. CrowdSec retains its existing LAPI master placement and verifies all three agents.

After all apps pass, compare the full current desired/live resources, reconcile all ten owners and resolve only captured, unexecuted queues. Attach continuous Pod/Deployment/DaemonSet watches before removing the owned hold and require six clean minutes at current main. Remove only exact owned helpers, the synthetic credential fixture, temporary plaintext and fixture containers after encrypted audit protection. Release the original maintenance owner last. Preserve source directories, snapshots, current targets, durable ciphertexts and separate recovery keys.

## Recovery and growth

Durable encrypted recovery is stored under `~/.local/share/homelab-recovery/operations-home-csi-cutover-20261017/` on this computer and the matching VM300 operation's `recovery/` directory. Keys remain in the separate desktop `~/.config/homelab-recovery-keys/operations-home-csi-cutover-20261017/` directory and VM300 `keys/`. These directories and all plaintext credentials are outside Git. The existing Ansible-vault-managed Sealed Secrets key is required to recover encrypted application declarations and is never exported into app fixtures.

Before authority, rollback requires proving the complete original cold source unchanged and retiring every target helper/attachment. After authority, recover the accepted target; do not automatically fall back to the stale NFS copy. Keep original operation receipts and inspect an uncertain native PID/boot/start-time generation before any continuation.

Volume growth uses the existing retained CSI expansion procedure: check full committed growth and physical capacity, increase the declared PV/PVC/image capacity through the established workflow, and verify filesystem expansion. Never shrink images or silently increase the NAS quota. Changing a storage backend requires a separately qualified data move; the upstream CSI driver remains unmodified.
