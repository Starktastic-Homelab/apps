# Proxmox CSI

`app.yaml` is discovered in the controllers phase, after foundation.
Its namespace, encrypted configuration and public trust anchor are published by
the foundation `sealed-secrets` Application before controller activation.
The stock upstream chart is pinned to **0.5.15 / driver v0.22.0**. The OCI repository
uses [ArgoCD's Helm source format](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/)
(without `oci://` in `chart.repo`); Helm CLI rendering uses the prefix.

The persistent `k3s-block` storage and empty `k3s-csi` pool are provisioned;
see the [production setup results](../../../docs/superpowers/reports/2026-10-05-proxmox-csi-production-setup.md).
`shared-storage-settings.json` records the exact non-secret inputs to the manual
Ansible setup; Apps does not execute it. Jellyfin migration acceptance is recorded by the coordinated cutover plan. Existing NFS defaults, retained iSCSI and
Jellyfin declarations are unchanged.

The approved [coordinated cutover plan](../../../docs/superpowers/plans/2026-10-05-proxmox-csi-jellyfin-cutover.md)
stages deployment-access and secret-recovery checks before downtime, then a cold
copy and isolated restore before worker replacement and controller activation.
The controller activation follows those gates.

The NAS dataset `apps/k3s-block` (GUID `13918781591004512447`) has a **288GiB aggregate
quota** (live read 2026-11-16). It grew from 128GiB in reviewed steps: 160GiB in the
[October13 capacity amendment](../../../docs/superpowers/reports/2026-10-13-csi-quota-160g.md),
then 192GiB, 256GiB and 288GiB with the monitoring, media and utility/home cohorts.
This is the one place that states the current quota; runbooks link here.
It has no reservation. Individual images/PVCs retain their existing sizes;
allocation and growth must account for all images, snapshots, historical files
and required headroom using fresh measurements.

## Retired migration sources (2026-11-16)

On 2026-11-16 Ben decided to retire the state the storage migrations had kept for
rollback. This is the one place that records it; it supersedes every runbook line
that says to preserve, keep or resume that state.

Deleted on 2026-11-16:

- 41 retired NFS source directories under `/mnt/apps/pv`:
  `.homelab-checkpoints/calibre-csi-9a6db837d6ba`;
  `crowdsec/{crowdsec-config-pvc,crowdsec-db-pvc}`;
  `databases/{data-postgres-postgresql-0,pgadmin-pgadmin4,redis-data-redis-master-0}`;
  `default/{data-2dobom-0,data-twodobom-0}`; `filebrowser/filebrowser.db`;
  `media/{audiobookshelf,autobrr,bazarr,cineplete-config,cineplete-data,cleanuparr,cross-seed,flaresolverr,lazylibrarian,lidarr,lingarr,navidrome,prowlarr,qbittorrent,qbittorrent-ru,radarr,radarr-ru,recyclarr,seerr,seerr-ru,shelfmark,sonarr,sonarr-ru}`;
  `monitoring/{alertmanager-kube-prometheus-stack-alertmanager-db-alertmanager-kube-prometheus-stack-alertmanager-0,kube-prometheus-stack-grafana,prometheus-kube-prometheus-stack-prometheus-db-prometheus-kube-prometheus-stack-prometheus-0,storage-loki-0,storage-tempo-0}`;
  `operations/{bytestash,ntfy-cache,ntfy-config}`; `traefik-system/traefik`;
- the `k3s-block` file `.vm-9999-jellyfin.raw.partial-20261005`;
- all 32 manual cold ZFS snapshots on `apps/pv` (the September 2026 Jellyfin ones,
  `pre-nfs-standard`, every `homelab-*-cold-202610xx`, and the `redis-retained` and
  `immich-retained` ones);
- every encrypted cutover recovery copy and its keys on VM300
  (`/var/lib/homelab-maintenance/operations/`, except the live `pg-enrollment-*`,
  `enrollment` and `cnpg-qualification-20261010` receipts) and on the operator
  workstation (`~/.local/share/homelab-recovery`, `~/.config/homelab-recovery-keys`),
  including `vikunja-removal-20261018` and `monitoring-csi-cutover-20261016`.

Deleted when the PR that adds this section merges:

- the 14 old NFS claims `home-assistant-config`, `matter-server-data`,
  `mosquitto-config`, `zigbee2mqtt-config`, `calibre-web`, `immich-pgdata`,
  `bytestash-data`, `changedetection-data`, `convertx-config`, `excalidash-data`,
  `karakeep-data`, `karakeep-meilisearch`, `microbin-config` and
  `stirling-pdf-config`, with their PVs and directories;
- the ten old ordinary-file block images and their PV/PVCs
  (`vm-9999-{grafana,prowlarr,bazarr,seerr,seerr-ru,cineplete,cleanuparr,ntfy,pgadmin,changedetection-data}.raw`);
- the 40 live old-source Pod admission holds, plus the never-deployed qBittorrent and
  qBittorrent-RU copies in git (the `*-source-hold` policies,
  `postgres-storage-hold`, `ordinary-file-retired-csi-hold`,
  `calibre-retired-config-source-hold`, `paperless-retired-data-source-hold` and
  `immich-source-hold`, with their bindings).

The live `<app>-files` NFS claims and every other live directory and claim stay.

**Last copies.** The restic `daily` snapshots taken 2026-11-09 to 2026-11-16 (plus
any later daily taken before an item's deletion; ansible `docs/backup-and-restore.md`)
are the only remaining copies. With `forget --keep-daily 14 --keep-weekly 8
--keep-monthly 12` they age out by about 2027-01-10: the 2026-11-15 weekly is the
last one kept, and November's monthly slot is taken after the deletions. Ben chose
on 2026-11-16 not to pin them. VM300's recovery copies also sit in its weekly
vzdump (restic tag `vzdump`, keep-last 2, plus the local USB keep-last 3), so for
roughly two to three weeks. The workstation copies had no other backup beyond the
restic content they duplicated. Vikunja's data is gone once those vzdumps rotate.

Runbook steps that mention these sources, holds, snapshots or recovery copies are
history.

## Configuration and recovery contract

- The API controller runs on the control plane; the node DaemonSet runs on Linux
  workers. Native region/zone labels and guest prerequisites come from the opt-in
  Ansible bootstrap. Terraform enrolls all k3s VMs in the dedicated Proxmox pool.
- The chart consumes `csi-proxmox/proxmox-csi-config`, key `config.yaml`. It does
  not generate credentials. The manual Ansible shared setup stores a protected
  external JSON credential record; that record is **not** directly the chart's
  YAML configuration. Publication and recovery must compose the stock
  [configuration](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/v0.22.0/docs/config.md):
  `features.provider: default`, integer `features.controllerVmID` set to the
  reserved external image owner, and `clusters[]` containing the API URL, TLS
  verification choice, token ID/secret and region matching the node labels.
- The owner must remain outside disposable Terraform state and must never be
  reused as a VM. Shared setup checks it is unused; its reservation is an
  operator convention, not a Proxmox allocation lock.
- Use `scripts/seal.sh` for SealedSecret publication. Prove recovery of
  the sealing key and CSI configuration from outside Kubernetes before
  controller readiness and service writer release on a fresh cluster. The actual
  encrypted configuration is published from `../sealed-secrets/manifests/`; plaintext credentials
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
They preserve explicit harness/dispatch limits; production acceptance remains separate from those lab results.

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

The controller is enabled through a separately reviewed activation change after
the cold-copy and restore gates. Shared NAS allocation and external configuration
recovery are complete. The old source and its writer guards were
[retired on 2026-11-16](#retired-migration-sources-2026-11-16).
The accepted export-withdrawal recovery trade-off is unchanged: some storage I/O
faults require manual scale-down, verified detach and restaging. Ordinary rebuilds
must not require a Velero checkpoint or a manual backup verification step.

## Offline render

Run from the repository root (Helm required):

```bash
helm template proxmox-csi oci://ghcr.io/sergelogvinov/charts/proxmox-csi-plugin \
  --version 0.5.15 --namespace csi-proxmox -f templates/globals.yaml \
  -f infrastructure/system/proxmox-csi/values.yaml > /tmp/proxmox-csi.yaml
```

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

The foundation `sealed-secrets` Application owns the CSI namespace, SealedSecret
and public trust ConfigMap in `../sealed-secrets/manifests/`. The values' native
controller mount uses the qualified trust path. Controller discovery occurs in the later controllers phase. The API leaf expires on 2027-06-14; replace the anchor when the
server certificate rotates and restart the controller to refresh its subPath
mount. Runtime acceptance is tracked in the cutover plan.
