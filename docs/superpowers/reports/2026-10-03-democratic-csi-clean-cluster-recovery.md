# democratic-csi clean-cluster recovery assessment

Date: 2026-10-03. Scope: pinned source and synthetic probes, no infrastructure access or deployment.

## Result

The inspected stock democratic-csi v1.9.5 does not provide the requested combination of ordinary dynamically provisioned
PVCs, disposable Kubernetes metadata, automatic original-volume recovery and refusal to allocate a replacement when
expected storage is missing. Dropping CHAP and targeting TrueNAS 25 remove separate concerns; they do not change this
identity/lifecycle gap. A design decision is needed before implementation or lab allocation.

This is a bounded conclusion about the inspected paths, not a claim that all CSI drivers or future releases lack a
solution. We did not run Kubernetes, TrueNAS, ZFS, LIO, iscsiadm or node staging.

## Evidence and reproduction

Source: democratic-csi v1.9.5, commit `b5be00c0748cbae251e661392cc7ab9fea335ac9`. The
[recovery probe](evidence/2026-10-03-democratic-csi-recovery-probes.cjs) verifies SHA-256 hashes and evaluates whole upstream
methods in a JavaScript VM with simulated storage and no network/process APIs. It exercises the TrueNAS API controller
and the shared ZFS CLI controller used by Debian ZFS/LIO and the SSH TrueNAS profile. Export creation is mocked; no result
here qualifies target mappings, filesystem identity, credentials or writer exclusion.

```sh
node --check docs/superpowers/reports/evidence/2026-10-03-democratic-csi-recovery-probes.cjs
node docs/superpowers/reports/evidence/2026-10-03-democratic-csi-recovery-probes.cjs /path/to/democratic-csi-v1.9.5
```

Results: all assertions passed on October 3. [Captured output](evidence/2026-10-03-democratic-csi-recovery-results.json).

| Scenario | TrueNAS API controller | Shared ZFS CLI controller |
| --- | --- | --- |
| Same request ID and retained dataset | Returns original handle; synthetic fixture remains intact | Same |
| Same PVC namespace/name, new request ID | Requests a new dataset and returns a new handle; old fixture remains | Same |
| Direct existence lookup fails | Representative HTTP 403, 500 and timeout stop before mutation | Permission denied and connection timeout stop before mutation |
| Original request ID but dataset is missing | Requests creation of a dataset | Same |

The mocked idempotent ZFS create operation models the upstream utility's handling of an existing dataset; the TrueNAS
case uses the actual DatasetGet/DatasetCreate methods with mocked HTTP responses. These demonstrate control flow, not
physical preservation or runtime backend behavior. Original fixture sentinels are only simulated data.

### Identity is tied to the provisioning request

The Kubernetes external provisioner derives the request name from the PVC UID. Passing PVC namespace/name as additional
metadata does not replace that identity. democratic-csi `getVolumeIdFromCall` uses the request name by default; both
controllers derive the dataset path from that ID. The new cluster's recreated PVC therefore targets a new dataset even
when its namespace/name matches the previous claim.

Sources: [Kubernetes provisioner v5.1.0](https://github.com/kubernetes-csi/external-provisioner/blob/v5.1.0/pkg/controller/controller.go),
[identity function](https://github.com/democratic-csi/democratic-csi/blob/v1.9.5/src/driver/index.js#L448-L552),
[ZFS CLI create](https://github.com/democratic-csi/democratic-csi/blob/v1.9.5/src/driver/controller-zfs/index.js#L639-L1333),
[TrueNAS API create](https://github.com/democratic-csi/democratic-csi/blob/v1.9.5/src/driver/freenas/api.js#L2633-L3395).
The external-provisioner source is a reference for the UID naming behavior, not a claim about the live sidecar version.

### Stable target names are not a recovery contract

`iscsi.nameTemplate` names export assets; it does not replace the ZVOL ID. In issue #44, apparent recovery through an old
target accompanied by a newly allocated ZVOL was explicitly identified by the maintainer as a bug. Issue #289 discusses
the resulting identity collisions and introduces the private volume-ID setting. Do not use target-name reuse as adoption.

Sources: [maintainer comment on target reuse](https://github.com/democratic-csi/democratic-csi/issues/44#issuecomment-762550237),
[private-ID discussion](https://github.com/democratic-csi/democratic-csi/issues/289#issuecomment-1500977095).
These discussions concern older versions; the current inspected source separately confirms the ID/target distinction.

The released `examples/private.yaml` explicitly marks `_private.csi.volume.idTemplate` and `deleteStrategy` unsupported.
A stable template also cannot establish that a missing dataset is a new application rather than lost existing storage.
The probe holds the request ID constant and removes the dataset: the normal creation path still requests new storage.
[Private configuration warning](https://github.com/democratic-csi/democratic-csi/blob/v1.9.5/examples/private.yaml).

### Correct the scope of the earlier lookup finding

The earlier [probe](evidence/2026-10-03-democratic-csi-source-probes.cjs) demonstrates that API `ListVolumes` can return an
empty list for HTTP 403. The normal `CreateVolume` path uses a direct dataset lookup instead and does not use that empty
list as evidence of absence. With the representative errors tested here it stops before mutation. The enumeration bug
still matters to any proposed recovery inventory, but it is not proof of empty-volume allocation on those errors.
[DatasetGet](https://github.com/democratic-csi/democratic-csi/blob/v1.9.5/src/driver/freenas/http/api.js#L442-L461).

### Stored metadata is necessary but does not implement rebinding

The driver stores its CSI name, share context and management markers as ZFS properties. It can enumerate those records,
and configured dataset properties can record application names. These are useful recovery inputs. In the inspected
source/docs/bin/contrib paths, no supported process was found that reconstructs and binds Kubernetes PV/PVC objects by
application identity on a fresh cluster. Building that process locally would introduce the recovery machinery the user
wanted to avoid. An asynchronous export of PVs to Git would also reintroduce the rejected freshness window.

## Decision options

1. **Use explicit Git-managed bindings for durable application volumes (recommended fallback to assess).** Provision the
   NAS volume/export once, declare a static PV with its handle and connection details, and bind the application's PVC to
   it. Rebuild reapplies those declarations. The native democratic-csi `node-manual` path can attach to existing iSCSI
   exports on either backend. A missing PV keeps its explicitly bound claim pending; a missing target cannot cause a
   CSI controller to allocate a replacement when dynamic provisioning is disabled for that path. Filesystem identity and
   old-writer exclusion still need qualification. This changes onboarding: each durable volume needs an explicit storage
   allocation and binding record. It does not deliver automatic allocation from ordinary PVC values alone. It also
   returns to the static attachment model already used for Jellyfin; it is a simpler candidate lifecycle around that
   model, not a claim to have introduced CSI or eliminated every existing safeguard.
2. **Keep automatic PVC-only allocation as a hard requirement.** The current stock-driver proposal cannot be selected.
   A supported upstream recovery feature or separately approved maintained recovery component is needed. No such
   component has been selected, implemented or qualified. This route carries development/maintenance and availability
   uncertainty. It is not authorization to message upstream, fork a driver or create another local controller.

[Upstream static iSCSI example](https://github.com/democratic-csi/democratic-csi/blob/v1.9.5/examples/node-manual-iscsi-pv.yaml),
[Kubernetes explicit PV binding](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#reserving-a-persistentvolume).

Both choices retain the desired destroy/apply workflow and the boundary that NAS data, its identity, Git and bootstrap
secrets survive outside the cluster. Neither requires Velero or preservation of the old Kubernetes datastore. CHAP is an
independent access-policy decision; neither this investigation nor its findings authorize disabling it.

No lab execution is justified until this onboarding/recovery decision is made. Documentation checks and both synthetic
probe suites passed. `pre-commit` is unavailable; no YAML/Helm resources changed, and no runtime qualification occurred.
