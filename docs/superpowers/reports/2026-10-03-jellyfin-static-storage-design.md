# Jellyfin static storage: current implementation and simplification

Date: 2026-10-03. The user selected static Git-managed volume bindings and separate initial NAS allocation.
This is a repository-source audit and proposed simplification, not verification of live workload or NAS state.

## What exists today in Git

| Layer | Declared behavior | Source |
| --- | --- | --- |
| Application | One replica, Recreate; `/config` uses existing claim `jellyfin-config-iscsi`. | [values](../../../services/media/jellyfin/values.yaml) |
| Binding | Explicit PV/PVC `jellyfin-config-iscsi`, 64 GiB, ext4, RWOP; empty storageClassName and explicit volumeName; claimRef has namespace/name and no UID. | [retained manifests](../../../services/media/jellyfin/manifests/retained-storage.yaml) |
| Durable endpoint | Fixed CSI handle `19b50cf8-a026-408e-83df-521d13bec20b`, portal `10.9.8.30:3260`, IQN `iqn.2005-10.org.freenas.ctl:jellyfin`, LUN 0. | Same manifest |
| Retention | PV Retain plus ArgoCD Prune=false,Delete=false on both PV and PVC. These do not protect against deleting NAS data separately. | Same manifest |
| CSI | democratic-csi v1.9.5 node-manual, controller disabled, no StorageClasses, driver identity `org.democratic-csi.retained`. | [driver values](../../../infrastructure/system/retained-iscsi/values.yaml) |
| Filesystem | ext4 formatting configured with `-n`; automatic filesystem checking disabled. Existing identity checks run outside the CSI mount path. These flags do not by themselves validate the expected filesystem UUID. | Driver values and [probe](../../../scripts/storage/initiator_probe.py) |
| Authentication | The PV references the sealed `retained-jellyfin-chap` Secret. NAS allocation intent restricts initiators and source network. | Retained manifests and [intent](../../../storage/services/jellyfin.json) |
| Other Jellyfin storage | Media uses the shared NFS claim; cache and transcodes use bounded emptyDir. Legacy PVC resources are still declared for retention. | App values and [shared defaults](../../../templates/common.yaml) |

The static PV/PVC definitions already solve persistence of the binding across a fresh Kubernetes datastore: Git can
recreate the same handle and connection parameters without restoring the old claim UID. They do not alone authorize a
new writer or establish the identity of the device behind that endpoint.

## Why a complete rebuild is still not automatic

Application placement pins `kube-worker-01`, its specific SMBIOS UUID and its Kubernetes Node UID. The CSI node daemon
also requires an `iscsi-ready` label. The inspected Ansible worker path applies that label only after reviewed initiator
and VM-generation enrollment; enrollment is disabled by default in the role defaults.

Admission requires an external `retained-jellyfin-authorization` ConfigMap with a matching record hash, a release flag,
current namespace UID and current node/VM identity. Namespace UID stamping is restricted. The app's placement and the
release record must agree. A fresh cluster changes these UIDs; replaying the static PV/PVC and existing values therefore
cannot by itself restore normal startup.

The release helper requires fresh native-storage and filesystem checks, CHAP agreement and proof that the previous
writer cleanly disconnected or its exact VM generation is stopped. It does not accept a permanent Git release flag.
Sources: [renderer and policies](../../../scripts/storage/render_storage.py),
[release gate](../../../scripts/storage/release.py),
[live-observation construction](../../../scripts/storage/maintenance_cli.py).

The Ansible reference is the previously inspected maintenance-runner checkout at
`0fc25a3c90defc5b114be68e333c1592003cdc76`, roles `iscsi_initiator`, `k3s_workers` and `bootstrap_cluster`.
This is not a claim about what currently runs on the nodes; do not deploy this old checkout.

## How the volume was intended to be established

`storage/services/jellyfin.json` is an allocation intent, not the verified volume record. The explicit onboarding code
creates the ZVOL, initiator group, CHAP record, extent, target and LUN mapping, then records native identities. It refuses
to rerun an interrupted allocation blindly and does not format a filesystem. Its current validation is hardcoded to the
Jellyfin pilot and TrueNAS 25.10.7.

The renderer consumes a verified record including ZVOL GUID, export serial/NAA and filesystem UUID. That record and the
operation journals live on the external maintenance runner; Git contains the resulting bindings and a record hash. The
maintenance CLI also hardcodes Jellyfin operation paths. This combination is why adding another service currently needs
more work than adding an ordinary binding declaration.
Sources: [onboarding](../../../scripts/storage/onboard.py), [operator documentation](../../../scripts/storage/README.md).

The Jellyfin application README retains its earlier NFS upgrade narrative. Its `/config` description must not be used
as evidence of present iSCSI runtime state; the desired manifests now reference the iSCSI claim.

## Proposed improvements

1. **Keep the existing static CSI architecture.** A normal rebuild needs only node attachment, static declarations and
   credentials when authentication is enabled. No dynamic controller, NAS allocation API access for the CSI pods, Velero,
   adoption logic or retained Kubernetes database is needed for that attachment path.
2. **Use one reusable binding declaration per volume.** Record the actual verified handle, portal, IQN, LUN, size,
   filesystem and optional Secret reference. Keep non-secret expected device/filesystem identity durably with it. Reuse
   the existing renderer after removing hardcoded Jellyfin names, and generate the PV/PVC and narrow invariant policies.
   Keep service values limited to existingClaim and mounts. Initial NAS allocation and export configuration remain an
   explicit separate step; this design does not promise automatic provisioning from PVCs.
3. **Separate durable identity from temporary ownership.** Keep volume identity in Git; discover fresh cluster/VM identity
   during rebuild. Remove fixed Node/namespace UIDs from Git only once the replacement checks are qualified. Use stable
   capability placement labels, with Jellyfin's GPU requirement retained. Keep RWOP/Recreate, but do not treat them as
   cross-cluster fencing.
4. **Make rebuild verification shared and automatic.** Before services start, the existing Packer/Terraform/Ansible flow
   must establish old-writer shutdown, recovered secrets, prepared initiators and the original filesystem/device identity.
   Reuse the smallest existing verification functions first. No per-service hand-authored release receipt is required in
   the eventual routine path. Missing storage or uncertain shutdown holds the application; bootstrap cannot allocate,
   format or redirect storage. Exact gating/authorization wiring needs a reviewed implementation plan and lab evidence.
5. **Keep migration and data recovery exceptional.** The original-NFS hold, backup-reader restrictions, staged cutover and
   rollback receipts protect the migration history. Retire those from normal operation only after current data ownership
   and acceptance are established. Preserve their evidence. Restore to clones/new volumes and NAS data backups remain
   separate from reattaching a surviving volume after a cluster rebuild.

Portability comes from the static iSCSI contract: a Debian ZFS/LIO export can be consumed by the same node-manual driver.
NAS creation commands and storage identities change during a verified backend migration; application claim names can
remain the same. Replacing all NAS/provider tools is not a prerequisite for the first static-binding simplification.

## Open access-policy choice

CHAP removal has not been approved. It removes CHAP credential plumbing and the inspected CSI password-in-arguments
problem, but not storage verification or writer exclusion. The existing allowed network is `10.9.8.0/24`, identified in
[globals](../../../templates/globals.yaml) as the services network. Source inspection does not establish a dedicated,
restricted storage network. Before qualifying a no-CHAP profile, verify actual network/target restrictions. If CHAP is
retained, its safe credential path remains a qualification requirement. Existing live CHAP remains unchanged either way.

## Delivery boundary

This update changes documentation only. No existing worker affinity, admission rule, NAS export, Secret or migration hold
was changed. The next implementation plan must identify the new bootstrap gate before removing the old one, and stage
Jellyfin activation separately from inert generic fixtures. A successful full destroy/recreate test with missing-volume,
wrong-filesystem and competing-writer cases is required before claiming unattended recovery.
