# Staged Proxmox CSI

`app.yaml.disabled` does **not** match the foundation ApplicationSet's
`infrastructure/**/app.yaml` discovery. Merging this directory installs nothing.
The stock upstream chart is pinned to **0.5.10 / driver v0.20.0**. The OCI repository
uses [ArgoCD's Helm source format](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/)
(without `oci://` in `chart.repo`); Helm CLI rendering uses the prefix.

The persistent `k3s-block` storage and empty `k3s-csi` pool are provisioned;
see the [production setup results](../../../docs/superpowers/reports/2026-10-05-proxmox-csi-production-setup.md).
`shared-storage-settings.json` records the exact non-secret inputs to the manual
Ansible setup; Apps does not execute it. Controller activation, VM enrollment and
application migration remain pending. Existing NFS defaults, retained iSCSI and
Jellyfin declarations are unchanged.

The approved [coordinated cutover plan](../../../docs/superpowers/plans/2026-10-05-proxmox-csi-jellyfin-cutover.md)
stages deployment-access and secret-recovery checks before downtime, then a cold
copy and isolated restore before worker replacement and controller activation.
The descriptor remains disabled until those gates pass.

## Configuration and recovery contract

- The API controller runs on the control plane; the node DaemonSet runs on Linux
  workers. Native region/zone labels and guest prerequisites come from the opt-in
  Ansible bootstrap. Terraform enrolls all k3s VMs in the dedicated Proxmox pool.
- The chart consumes `csi-proxmox/proxmox-csi-config`, key `config.yaml`. It does
  not generate credentials. The manual Ansible shared setup stores a protected
  external JSON credential record; that record is **not** directly the chart's
  YAML configuration. Publication and recovery must compose the stock
  [configuration](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/v0.20.0/docs/config.md):
  `features.provider: default`, integer `features.controllerVmID` set to the
  reserved external image owner, and `clusters[]` containing the API URL, TLS
  verification choice, token ID/secret and region matching the node labels.
- The owner must remain outside disposable Terraform state and must never be
  reused as a VM. Shared setup checks it is unused; its reservation is an
  operator convention, not a Proxmox allocation lock.
- Use `scripts/seal.sh` for eventual SealedSecret publication. Prove recovery of
  the sealing key and CSI configuration from outside Kubernetes before
  controller readiness and service writer release on a fresh cluster. The actual
  encrypted configuration is staged in `bootstrap-staged/`; plaintext credentials
  and the private sealing key remain outside Git.
- The stock namespace requires privileged Pod Security for the node plugin.
  Native attachment, resizer and accepted upstream format/repair behavior remain
  intact. Snapshotting and capacity publishing remain disabled in these values.

`proxmox-retained` is nondefault, expandable, ext4/cache-none, `Retain` and
`WaitForFirstConsumer`. It is still **dynamic-capable**: `Retain` does not forbid
new image allocation. Participating services must explicitly prebind an Apps-owned
PV/PVC using `volumeName`, `claimRef` without a Kubernetes UID, `ReadWriteOncePod`,
and the verified stable external `volumeHandle`. Each static PV must carry its
own `Retain`, filesystem and storage/cache attributes; StorageClass parameters
do not fill these in for a pre-existing PV. Preserve Argo prune/delete protection
and indefinite not-ready/unreachable NoExecute holds for the workload. No service
bindings are activated by this preparation.

## Qualification before activation

The [disposable integration results](../../../docs/superpowers/reports/2026-10-04-proxmox-csi-rebuild-results.md)
cover cold rebuilds, interrupted growth, worker movement and failure boundaries.
They preserve explicit harness/dispatch limits; production activation is still
separate. The descriptor remains disabled.

In an approved disposable integrated lab, exercise the shared setup's effective
API permissions and repeatability, external credential recovery, ArgoCD chart
resolution/secret ordering, native pool membership, worker-only replacement and
control-plane-triggered whole-cohort replacement. Inject interrupted replacement
to verify old-writer exclusion. Offline rendering does not qualify these paths.

Growth also needs integrated GitOps qualification: request PVC growth first,
verify backend and filesystem expansion, then reconcile the Git PV capacity.
Never raise PV capacity ahead of the real image. The disposable lab recovered
from fresh metadata at both tested interruption checkpoints using bidirectional
prebinding. After actual growth, updating Git PV capacity cleared Argo drift.
This qualifies the tested request/verify/reconcile sequence, not a one-edit
resize with permanently stale Git PV capacity.

Only a separately reviewed activation change may rename the descriptor to
`app.yaml` and update the staged-only CI assertion after these gates pass. Shared
NAS allocation is complete. Encrypted configuration publication is approved and externally recoverable;
activation, Jellyfin migration and retirement of the old writer guards remain later.
The accepted export-withdrawal recovery trade-off is unchanged: some storage I/O
faults require manual scale-down, verified detach and restaging. Ordinary rebuilds
must not require a Velero checkpoint or a manual backup verification step.

## Offline validation

Run from the repository root (Helm and PyYAML required):

```bash
helm template proxmox-csi oci://ghcr.io/sergelogvinov/charts/proxmox-csi-plugin \
  --version 0.5.10 --namespace csi-proxmox -f templates/globals.yaml \
  -f infrastructure/system/proxmox-csi/values.yaml > /tmp/proxmox-csi.yaml
python3 scripts/storage/tests/check_proxmox_csi_render.py /tmp/proxmox-csi.yaml
```

CI renders these actual value layers and checks the inactive descriptor, external
Secret reference, worker placement, native attachment/resize components and class
retention policy. Runtime binding and rebuild validation is still required by the
[integration plan](../../../docs/superpowers/plans/2026-10-03-proxmox-csi-shared-integration.md).

## Production preflight evidence

The [read-only deployment preflight](https://github.com/Starktastic-Homelab/ansible/actions/runs/37241575852)
passed with the real deployment identity: strict API TLS, complete VM visibility,
stable inventory and native recovery of a synthetic SealedSecret using the
external Vault bootstrap key. The subsequent [actual-configuration recovery](https://github.com/Starktastic-Homelab/ansible/actions/runs/37243642764)
also passed: the recovered `config.yaml` matched its exact original hash. The
[sanitized receipt](../../../docs/superpowers/reports/evidence/2026-10-05-proxmox-csi-config-recovery.json)
identifies both the encrypted manifest and plaintext hash without exposing the token.

The [native TLS receipt](../../../docs/superpowers/reports/evidence/2026-10-05-proxmox-csi-native-tls.json)
records the unmodified v0.20.0 controller's read-only `GetCapacity` test on VM300.
Without the public certificate it refused the connection; with the certificate
mounted at `/etc/ssl/certs/proxmox.pem` it read the expected 128GiB capacity with
`insecure: false`. Both temporary containers and their private files were removed.

`bootstrap-staged/` is outside active manifest sources. Its public ConfigMap and
the values' native controller mount prepare the same qualified trust path without
activating CSI. The API leaf expires on 2027-06-14; replace the anchor when the
server certificate rotates and restart the controller to refresh its subPath
mount. The cold-copy, independent restore and activation gates remain pending.
