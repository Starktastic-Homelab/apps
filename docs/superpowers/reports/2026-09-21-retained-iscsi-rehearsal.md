# Retained iSCSI rehearsal

Date:2026-09-21 Asia/Jerusalem (most recorded events are September20 UTC).
Status: two full recoveries passed; lab cleanup and final review complete.

## Decision supported by this run

Retained iSCSI can preserve embedded database state across complete K3s VM/disk
replacement. The tested recovery uses captured native identities and explicit
PV/PVC bindings, with fresh cluster state and credentials restored from outside
the cluster. It does not rely on old PVC UIDs or dynamically creating a new
volume for an established service.

This is evidence for a storage-platform candidate, not authorization to migrate
production or proof that NFS caused every application's symptoms. No production
NAS iSCSI configuration or application database migration was performed.

The pinned stock democratic-csi1.9.5/TrueNAS25.10.6 pairing has a significant
production limitation: **REST access requires FULL_ADMIN**. Dataset/iSCSI roles
successfully authenticate over JSON-RPC but return403 for REST. The test used a
fresh dedicated lab-only account; a naming prefix is not a permission boundary.
TrueNAS26 removes REST, so this result does not establish upgrade compatibility.
See [TrueNAS role implementation](https://github.com/truenas/middleware/blob/TS-25.10.6/src/middlewared/middlewared/role.py)
and [REST deprecation](https://www.truenas.com/docs/scale/26/gettingstarted/deprecations/).

## Fixture and isolation

One owned TrueNAS VM and three disposable K3s VMs used12GiB configured RAM and
50GiB total disk ceilings. IDs910–913 were checked by exact name, SMBIOS UUID and
tag. The guard monitored host memory/OOM and production node identity, pressure,
OOM and available-memory conditions. It could stop only matching lab identities.
It did not continuously check every production application's health.

Two private bridges had no uplinks. Host ingress/forwarding were dropped using
a scoped nft table. All nine live TCP probes from lab nodes to production
Proxmox/NAS ports were blocked. K3s required a dummy default route; this points
at a non-forwarding dummy interface, not a real gateway. IPv6 host interfaces
were disabled; separate live IPv6 escape probes were not performed.

Management used loopback-only SSH tunnels, fresh lab SSH keys, CA-verified NAS
HTTPS and a dedicated API/CHAP identity. No production private credentials were
copied into guests. Checksummed offline artifacts and immutable amd64 image
pins were imported. Versions:K3s1.37.0+k3s1, CSI chart0.15.1/image1.9.5,
app-template5.2.1, snapshot-controller8.2.1.

## Executed evidence

| Check | Observed result |
|---|---|
| Two synthetic services | Separate2GiB RWOP claims, ZFS GUIDs, extents, targets, serials and LUN mappings |
| Capture/adoption | Native identities saved externally before data initialization; existing PVs/PVCs adopted with server-side apply |
| Admission | Six actual API-server rejection paths:ordinary dynamic claim, class substitution, foreign binding, spoofed onboarding label, second PV alias, Retain→Delete |
| Initialization/startup | One consumed external initialization receipt; normal startup rejects missing DB and wrong marker without creating a file |
| Exclusive writer | Second pod on the same RWOP claim stayed Pending with explicit in-use scheduling rejection |
| Drain/remount | Service A moved worker A→B; exact acknowledged values and integrity survived |
| Partition/fence | Worker B lost control networking but kept NAS access; witness commits acknowledged through QGA; no replacement before UUID-verified VM power-off; replacement on worker A recovered all11 acknowledgements per service |
| Snapshot restore | Stock CSI snapshot ready; restored separate volume/GUID576388407740335325 recovered all11 snapshot-time acknowledgements and integrity |
| Expansion before backend | CSI paused; desired3Gi/NAS2Gi. Resumed native expansion to3Gi at NAS/block/filesystem/PVC; all16 acknowledgements per service survived |
| NAS outage | Lab NAS shut down and rebooted; writes blocked then resumed; all21 acknowledgements per service survived |
| Independent backup | SQLite online backups copied externally; while NAS was confirmed off, new local destination files restored all11 backup-time acknowledgements and passed integrity |
| Interrupted resize + full rebuild | NAS grew4Gi while filesystem/PVC remained3Gi; all old K3s VM OS disks destroyed. Fresh CA/node/PV/PVC UIDs, same NAS GUIDs and filesystem data; native resize completed4Gi |
| No replacement allocation | Fresh CSI controller logs contained zero CreateVolume requests during established-service recovery; NAS retained exactly the two original volumes plus the snapshot restore |
| Credentials | Fresh cluster CSI blocked on missing secret; external credentials restored explicitly. Invalid API credential returned401 on allocation attempt |
| Retention | Applications and service B PVC removed after writers stopped; native datasets/GUIDs remained unchanged |
| Second full rebuild | Fresh VM disks/CA/node/PV/PVC identities again; same4Gi/2Gi NAS volumes; all26 prior acknowledgements per service recovered, then five new writes each verified; zero CreateVolume calls |
| Cleanup/production reconciliation | All four lab VMs/disks, bridges, firewall table, ISOs, staging, tunnel listeners and private runtime removed; runner300 running with service active; production125/125 pods ready,77/77 apps Synced/Healthy,68/68 claims Bound with no NFS mapping changes |

The external ledger fsyncs each acknowledgement only after the SQLite commit
returns. Verification compares transaction IDs and deterministic values, then
runs integrity_check. Unacknowledged commits are allowed to survive. This was
small synthetic transactional traffic, not throughput or latency benchmarking.
VM shutdown/reboot does not prove physical NAS power-loss durability.

## Compatibility corrections and limitations

- Driver `zvolDedup: off` sends an unsupported `dedup` API field. Omitting the
  optional setting allowed the same original claims to finish provisioning;
  parent and resulting volumes were verified OFF. No vendor patch was used.
- The chart emits null snapshot-class parameters when the optional map is
  empty. A standard separate VolumeSnapshotClass with `parameters:{}` works.
- The actual binder identity was
  `system:serviceaccount:kube-system:persistent-volume-binder`; its exact UPDATE
  permission was needed for the temporary snapshot restore exception. That
  exception was closed after capture. Quantity maps required dynamic CEL typing.
- Proxmox config files contain special/snapshot sections. A regression test
  caught stale fields overriding the live section; parsing now stops at the
  first section. The corrected guard was loaded for fresh-cluster runs.
- The production Proxmox fencing adapter/privileges and failure-to-fence gate
  are not implemented or accepted by this run. Manual lab fencing is not a
  production fencing solution.
- The lab restored secrets from private external files. It did **not** deploy
  Sealed Secrets or test restoring its key and decrypting fresh-cluster secrets.
- The pinned application chart was rendered and applied, but an ArgoCD instance
  was not deployed in the lab. Actual Argo prune/delete and resize-drift behavior
  therefore remain untested despite Retain and Prune=false,Delete=false metadata.
- Partial initialization/provisioning lost-response reconciliation, all wrong-
  backend variants and interrupted fencing were not exhaustively fault-injected.
  Unit rejection checks and the actual retry/rebuild paths are narrower evidence.
- No Jellyfin catalog/playback, plugin migration, application performance,
  production snapshot restore or PostgreSQL migration was tested.

## Next production decision

Keep NFS for suitable shared files/media. Evaluate native PostgreSQL per service
only with an accepted migration and restore path; resolve the separately found
PostgreSQL backup false-success issue before adding dependencies. For SQLite-
only state, choose a supported NAS/CSI API and acceptable permission boundary,
then complete production credential/GitOps/fencing acceptance before a small
Jellyfin pilot. Do not turn the synthetic result into a blanket migration.

Evidence and executed helpers are in [the fixture](../../../tests/iscsi-platform/README.md),
with [first rebuild](../../../tests/iscsi-platform/rebuild-result-1.json),
[second rebuild](../../../tests/iscsi-platform/rebuild-result.json),
[snapshot](../../../tests/iscsi-platform/snapshot-result.json),
[independent backup](../../../tests/iscsi-platform/independent-backup-result.json),
[isolation](evidence/2026-09-21-lab-isolation.json),
[fencing](evidence/2026-09-21-lab-fencing.json) and
[artifact checksums](evidence/2026-09-21-lab-inputs.json).

## Final cleanup and review

The owned lab infrastructure and private credentials/downloads were removed.
The runner VM and its GitHub Actions service are running again. Host available
memory was 29.31 GiB after runner startup; vm-pool free capacity returned to
136.13 GiB (the pre-lab baseline). Production VM identities and K3s node UIDs
were unchanged during the isolated rehearsal. All three nodes were Ready with
no pressure, 125 pods were ready, 77 Argo applications were Synced/Healthy,
68 PVCs were Bound with no NFS mapping/retention differences, 38 Sealed Secrets
were synced and seven certificates were ready. The kernel journal check found
no matching OOM lines on Proxmox or VMs200–202 during the rehearsal window.
Existing restart counters are retained in the evidence; readiness is a point-in-time check.

Workers remain at the user-merged temporary 20 GiB configuration. Restoring
28 GiB belongs in a separate Terraform PR with a reviewed plan; this run made
no imperative production RAM change. TrueNAS remains32 GiB and master16 GiB.

The independent final review found no Critical or Minor issues and one Important
issue: a status/stop failure on the first lab VM could prevent shutdown attempts
on the remaining owned VMs. A new regression test failed before the fix; shutdown
now isolates each VM's errors, attempts all remaining identities and reports
aggregate failures. All17 safety tests pass. The source fix was made after the
successful live cleanup; it was unit-tested, not redeployed into another lab.
Configured pre-commit checks passed. Review did not independently authenticate
live evidence or accept production readiness. No production manifests changed.

Final evidence: [cleanup and capacity](evidence/2026-09-21-lab-cleanup.json),
[production health and identities](evidence/2026-09-21-production-after-lab.json),
[OOM journal check](evidence/2026-09-21-lab-oom-check.json).

## Follow-up driver evaluation

The [pinned driver source evaluation](2026-09-21-truenas-csi-evaluation.md)
found an authentication/initiator-preservation blocker in official
truenas-csi1.3.0 clone and retry paths. No production deployment was attempted.
The next bounded candidate is democratic-csi1.9.5 node-manual, subject to accepting
external NAS lifecycle management and completing the shared recovery/fencing gates.
