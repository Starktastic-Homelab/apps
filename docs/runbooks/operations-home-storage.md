# Operations and home application storage

Activation is serialized through the approved cutover. The selected design puts Karakeep (including Meilisearch), ByteStash, ConvertX and Home Assistant (including Matter) on six retained ext4 Proxmox CSI volumes. Excalidash and CrowdSec will use the existing PostgreSQL service and recover their original credentials from Sealed Secrets. The preparation definitions that lived in `scripts/operations-home-retained/production/` were removed; recover them with `git show 45c7fb8c:<path>`.

| Application | Retained state | Capacity |
| --- | --- | --- |
| Karakeep | SQLite application and queue databases, uploads and configuration | 4GiB |
| Meilisearch | Rebuildable search index and engine version marker | 4GiB |
| ByteStash | Snippets database and all original data files | 2GiB |
| ConvertX | Fresh database and working state | 4GiB |
| Home Assistant | Recorder database, `.storage`, auth, integrations and custom components | 4GiB |
| Matter | Complete certificates, fabrics, server state and configuration | 2GiB |
| Excalidash | PostgreSQL; original JWT/CSRF identity in Sealed Secrets | Shared PostgreSQL |
| CrowdSec | PostgreSQL; original CAPI, LAPI, registration and bouncer identities | Shared PostgreSQL |

The original NFS source claims (including ByteStash's unused inherited `/config` claim), their admission holds, the cold ZFS snapshots and the encrypted recovery copies were [retired on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16). Excalidash's generated Prisma files are supplied by its unchanged image. Neither PostgreSQL-only app needs an application PVC.

## Rebuild behavior

Static PV handles refer to images owned by VM9999 on `k3s-block`; their lifetimes are independent of worker VMs. RWOP, verified VM retirement and native CSI attachment handling provide fencing. Keep all PVs/PVCs at `Retain`. Never force-detach a disk. The old NFS sources no longer exist.

The ConvertX reset occurs only in this cutover; it is not repeated on restarts or rebuilds. A fresh cluster recreates bindings, read-only retained-state guards, the existing PostgreSQL enrollment completion gate, and original application identities. Each file volume's guard is the generic marker guard (`infrastructure/base-configs/files/retained-startup/guard.py`, ConfigMap `retained-startup-guard`): it refuses a volume without `.homelab-<app>-data` holding exactly `homelab/<app>/data/v1` and a newline (`.homelab-karakeep-data`, `.homelab-karakeep-meilisearch-data`, `.homelab-bytestash-data`, `.homelab-convertx-data`, `.homelab-home-assistant-data`, `.homelab-home-assistant-matter-data`) before the stock image can initialize an empty store. It checks no native state. [The guard runbook](retained-startup-guard.md) gives the marker rule; each app's guard arguments are in its `values.yaml`. Excalidash and CrowdSec have no startup database check beyond the enrollment completion gate. Guards do not create or repair data. The single exception is a disaster-recovery re-initialisation of the lost Meilisearch image (`karakeep-meilisearch-block`) per ansible `docs/backup-and-restore.md`, "Re-initialise an excluded image", pre-approved by Ben on 2026-11-16 and allowed only once the image is missing and no replica copy of it exists; every other volume still needs its retained state.

The Meilisearch index is rebuildable (ADR 0010). Its guard requires only the volume identity marker. The container wipes only when `.version_marker` differs from the engine version or does not exist: it then logs what it is discarding, deletes only `data.ms` and that marker, writes the new version, and starts with an empty index; a same-version restart keeps the index. It exits without deleting anything when `/meili_data` lacks the identity marker as a regular file (for example a lost volume mount) or when `.version_marker` exists but cannot be read (a directory, a symlink, a read error). Meilisearch image updates stay manual in Renovate. Merge the ADR 0010 change first and wait for `base-configs` to sync the guard ConfigMaps before rebasing and merging an update such as Starktastic-Homelab/apps#1448; the old guard refuses any marker other than 1.55.0. After merging the update, rebuild search: in Karakeep go to `Admin Settings > Background Jobs > Reindex All Bookmarks`, or `POST /api/v1/admin/jobs/trigger/reindex` with body `{}` and an admin user's API key. If the reindex fails with `index_not_found`, restart Karakeep (it keeps its index handle while running), then retry. Until the reindex runs, search returns nothing; bookmarks themselves are unaffected.

Home Assistant keeps its host networking and Matter keeps `PRIMARY_INTERFACE=eth1` and its existing loopback listener. Recovery fixtures have no external route and override only the fixture's Matter interface to loopback; they cannot contact production devices. No deliberate device actions or CrowdSec remediation tests form part of acceptance.

CrowdSec preserves its native chart and TLS/agent/bouncer behavior. PreSync Sealed Secrets and a credential gate precede the unmodified upstream registration hook. Existing unmanaged credential Secrets are adopted by exact UID and value, with metadata-only changes. Repeated sync and complete namespace recreation were qualified to preserve original bytes without fresh external registration. The existing TLS configuration has no persisted cscli password Secret; none is invented.

## Cutover gates

The user authorized autonomous execution and PR merges for these six applications. The accepted exceptions are deterministic truncation of CrowdSec source timestamps below one microsecond and a fresh ConvertX application store without its old database or working files. ConvertX keeps its pinned image, deployment settings and original encrypted recovery; all other applications retain every field, row, key and identity. A failed or ambiguous gate preserves the current state and original evidence; an intent is never permission to replay a mutation.

The private native packet under this plan's ignored `.superpowers/sdd/` workspace must be complete, frozen and independently reviewed before downtime. It verifies installed maintenance runtime hashes, VM/cluster/controller/PVC/PV generations and all ten source/shared Argo owners before acquiring a fresh maintenance owner and execution exclusion. Original monotonic clocks allow two hours before each application's target authority and 24 hours for the cohort; a restart or failed attempt cannot reset them.

For each application (completed in October 2026; kept as history):

1. Stop overlapping Filebrowser/NFS-provisioner ancestors, then all app writers. CrowdSec agents stop before LAPI. Prove API, CRI and kernel mount retirement on every node and install an exact old-source admission hold.
2. Snapshot and archive every original source with complete file/POSIX/hardlink proofs. Encrypt and independently decrypt recovery, preserved verified copies on VM300 and the operator workstation with separate keys (deleted 2026-11-16), then resume only the original ancestor controllers.
3. Restore a complete disposable copy, verify all active SQLite databases, and start the unchanged stock images without an external route. ConvertX instead initializes a new empty store with its stock image: require healthy setup, zero users/jobs/file-name records, strict SQLite checks and exact native logical backup equality. SQL apps additionally require complete typed conversion, native migration/allocator preservation, stock startup and an independent SQL dump/restore.
4. Before each of the six allocations, reserve full remaining growth of every active raw image, all new claims, staging and 8GiB spare against both the dataset quota (256GiB during this cohort; current value in the [CSI README](../../infrastructure/system/proxmox-csi/README.md)) and physical pool free space.
5. Populate file targets from the original immutable archives (ConvertX uses only its verified fresh initialization archive), verify every byte and POSIX field, create the identity marker only after equality, and prove helper and physical attachment retirement. For SQL targets, use only the dedicated role, verify the physical database and empty schema, import once, independently export/restore the actual target and compare every application field, native migration record and allocator. Protect a separate encrypted SQL recovery on both media before authority.
6. Merge only the intended activation PR after exact-head hosted checks and Argo diff review. Compare complete current-Git workload/configuration with the frozen candidate. Mark authority before the first request permitting a writer, then sync only that app while the remaining owners stay held.
7. Verify native probes, guards, original Services/endpoints, retained physical identities and credentials. Prove Pod recreation and healthy worker movement for worker apps, then remove the temporary placement pin. CrowdSec retains its existing LAPI master placement and verifies all three agents.

After all apps pass, compare the full current desired/live resources, reconcile all ten owners and resolve only captured, unexecuted queues. Attach continuous Pod/Deployment/DaemonSet watches before removing the owned hold and require six clean minutes at current main. Remove only exact owned helpers, the synthetic credential fixture, temporary plaintext and fixture containers after encrypted audit protection. Release the original maintenance owner last.

## Recovery and growth

The `operations-home-csi-cutover-20261017` encrypted recovery copies and keys on the operator workstation and VM300 and the cold ZFS snapshots were [deleted on 2026-11-16](../../infrastructure/system/proxmox-csi/README.md#retired-migration-sources-2026-11-16). The existing Ansible-vault-managed Sealed Secrets key is required to recover encrypted application declarations and is never exported into app fixtures.

Recover the accepted target; there is no NFS copy to fall back to. Keep original operation receipts and inspect an uncertain native PID/boot/start-time generation before any continuation.

Volume growth uses the existing retained CSI expansion procedure: check full committed growth and physical capacity, increase the declared PV/PVC/image capacity through the established workflow, and verify filesystem expansion. Never shrink images or silently increase the NAS quota. Changing a storage backend requires a separately qualified data move; the upstream CSI driver remains unmodified.
