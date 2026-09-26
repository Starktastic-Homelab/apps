# Static retained iSCSI recovery on TrueNAS25.10.7

The user accepted static iSCSI with externally managed NAS lifecycle on September21,
after merging Apps1231/1233 and independently upgrading production TrueNAS to25.10.7.
This supersedes the full REST-controller choice in the September20 design; its
retained identity, isolation, exclusive-writer and independent-restore requirements
continue to apply. Production migration and PR merges remain separate user decisions.

## Selected architecture

Use the pinned stock democratic-csi1.9.5 node-manual node plugin. There is no CSI
NAS-management account, dynamic provisioner, CSI snapshot controller or controller
expansion. Provision each NAS ZVOL/extent/target once through external versioned
TrueNAS WebSocket automation. Export nonsecret pool/ZVOL GUID, path, capacity,
extent ID/serial/NAA, target ID/IQN, portal/LUN, filesystem UUID/type, service marker
and explicit retained PV/PVC binding to Git. Keep API credentials outside Kubernetes.
CHAP resides in a SealedSecret, never PV attributes or Git plaintext. Recreating a
cluster reconciles existing storage; it cannot allocate or initialize established
service storage. Kubernetes can be discarded independently of the NAS.

Separate four operations: (1) one-shot onboarding with external operation receipt;
(2) read-only verify/rebind; (3) explicit maintenance resize; (4) snapshot/restore to
a distinct target. Ordinary recovery never calls NAS create/delete or mkfs. Lost
mutation responses require querying the original identity and reconciling intent,
not repeating allocation. Snapshots/clones retain CHAP and exact initiator limits.
A clone gets a new manifest/service identity; it never silently replaces the source.
Offline expansion quiesces/unmounts, grows the same verified ZVOL, rescans the owned
initiator device, grows ext4, then reconciles PV/PVC capacity records. There is no
claim of Kubernetes-driven resize; if immutable PVC capacity requires rebinding,
Retain and the writer hold apply throughout and actual Argo behavior must be tested.

## Recovery and writer gates

New clusters install Sealed Secrets from an externally preserved lab key and decrypt
the CHAP Secret before any writable mount. Actual Argo reconciles controller, identity
policy and explicit bindings before the synthetic services. Applications start held.
An external recovery check verifies native identities, filesystem UUID and recorded
service before enabling writers. No Kubernetes-generated UID is a durable identity.
Admission denies dynamic/foreign claims, aliases, driver/fstype substitution, changed
Retain policy and storage-identity edits. Recovery exports exclude claimRef UID and
resourceVersion. Git annotations protect PV/PVC from Argo prune/delete.

A service has one RWOP filesystem claim. Rescheduling after clean unmount is distinct
from recovery after partition. A partitioned or uncertain old writer is never force-
deleted until the exact Proxmox VM UUID has been checked and power-off confirmed.
A timeout, permission error or changed VM identity prevents replacement. Production
fencing credentials are outside Kubernetes and restricted to the exact intended VMs;
this permission model must be verified separately before a production pilot.

A filesystem marker checked after mounting is too late to prevent accidental format.
The first probe evaluates `node.format.ext4.customOptions: ["-n"]` in the unchanged
stock image; this is mke2fs no-write mode, not a claim that the driver has a native
never-format feature. Pin ext4/unpartitioned devices and disable automatic fsck.
Require unchanged whole-device hashes on blank/wrong-volume rejection, before any
writable mount. If this does not hold in actual NodeStage, stop this candidate; no
unreviewed custom CSI image or silent relaxation. Read-only external checks and
admission remain necessary for wrong-but-valid filesystems and changed mappings.

## Isolated acceptance environment

Reuse the approved Proxmox host and compact resource envelope: owned fresh VM IDs
910–913, new names/UUIDs/tag, two private bridges, no production uplinks; TrueNAS25.10.7
8GiB, K3s server2GiB, workers1GiB each. Keep production workers20GiB while the lab is
needed; do not merge Terraform223 yet. Stop runner300 only after checking it is idle,
and restart it at cleanup. Use the corrected ownership/memory guard from the prior
fixture; never execute old /tmp helper scripts with embedded stale guard code.
All production nodes must be Ready without pressure, apps converged, host available
at least20GiB, and vm-pool at least130GiB free before allocation. Lab disk ceilings
remain50GiB, leaving80GiB headroom. Stage and checksum inputs separately. Preserve
exact lab ownership for cleanup; never attach production disks or copy production
credentials into test guests. No production NAS iSCSI mutations in this rehearsal.

## Acceptance and handoff

1. Stock-image formatting probe: existing ext4 retained; blank/unrecognized devices
   never formatted with the proposed option; actual NodeStage tested in lab later.
2. Native WebSocket onboarding and idempotency: retry lost response without duplicates;
   read-only rebind refuses missing, ambiguous, blank and redirected identities.
3. Actual Argo/Sealed Secrets fresh-cluster recovery twice, preserving acknowledged
   SQLite values and integrity, without old cluster state or replacement allocation.
4. Pod contention, clean move, control-only partition while storage remains reachable,
   failed fencing rejection, confirmed fence before replacement, and native snapshots
   with authentication/initiator checks on restored clones.
5. Interrupted external expansion at NAS/device/filesystem/record boundaries, actual
   GitOps capacity reconciliation, independent backup restore with lab NAS off.
6. Remove lab VMs/disks/networks/credentials/downloads, restore runner, verify production
   identities/health/capacity, and report passed/failed/untested precisely.

A Jellyfin pilot follows only accepted platform gates, a complete cold backup and
explicit migration/rollback plan. The NAS patch update does not fix upstream CSI
clone/retry code or establish performance improvement for SQLite on NFS.
