# Proxmox CSI attachment capacity

Each retained volume consumes one virtual SCSI slot on the worker running it.
The stock v0.20.0 driver defaults to 24 attachments. Its label validation accepts
30, but its [attachment loop](https://github.com/sergelogvinov/proxmox-csi-plugin/blob/v0.20.0/pkg/csi/utils.go)
only searches `scsi1` through `scsi29`. Our supported allowance is therefore **29
per worker**, with worker OS disks on `virtio0` and cloud-init on `ide2`.
Growing an existing volume consumes no extra attachment slot.

Ansible's `group_vars/all/proxmox_csi.yml` supplies the native
`csi.proxmox.sinextra.dev/max-volume-attachments: "29"` worker label during
registration and reconciles existing Nodes. New workers and complete cluster
rebuilds receive it through the normal bootstrap. Keep the driver unmodified.

## First activation on the existing cluster

1. Merge and complete the Ansible attachment-capacity deployment first. Its
   normal serial worker configuration can restart each k3s agent; no VM
   replacement is required.
2. Verify both worker labels are 29. Inspect `kubectl -n csi-proxmox get pods -o
   wide`, then refresh only the CSI node plugin Pod for one worker using an
   ordinary exact-name Pod deletion. Wait for its replacement to become Ready
   and its CSINode driver's allocatable count to report 29 before proceeding to
   the other worker. Never delete application Pods or detach their disks for this.
3. Verify both live counts with `kubectl get csinodes -o yaml`, and verify all
   pre-existing VolumeAttachments and application controllers remain healthy.
   Changing the Node label alone does not prove the CSI allocation refreshed.
4. Merge the Apps capacity-alert change and check the rule group is loaded and
   its recording rules match fresh Kubernetes attachment counts. The metric
   budget must never be enabled ahead of the verified live limit.

## Alerts and response

The existing kube-state-metrics exporter already supplies worker readiness,
cordons and VolumeAttachment objects; no new exporter or API permissions are
needed. The recording rule uses the configured **29-slot budget**, rather than
claiming to measure CSINode allocation. Update Ansible and this budget together
if the supported driver or non-CSI disk layout changes.

Pending and deleting VolumeAttachments count as occupied. Duplicate scrapes are
deduplicated by object and worker; other CSI drivers are excluded. Workers with
no attachments still contribute their whole budget. Unready and cordoned
workers contribute no available scheduling capacity.

- `ProxmoxCSINodeAttachmentHeadroomLow`: at most three free slots on a worker for
  15 minutes. Inspect placement and plan capacity before adding more volumes.
- `ProxmoxCSIClusterAttachmentHeadroomLow`: fewer than ten free slots across
  eligible workers for 30 minutes. Plan a worker increase through Terraform.
- `ProxmoxCSIClusterAttachmentCapacityExhausted`: no eligible worker has free
  slots for five minutes. Inspect worker health, monitoring and pending
  attachments; do not delete retained PVCs/images or force-detach disks.

Two workers provide 58 total slots, with 41 attachments observed on October19
(17 and 24). They cannot run all those volumes on one surviving worker. The
accepted policy keeps two workers and uses advance alerts; it does not promise
full worker failover or automatic scaling. More services eventually require
additional worker capacity even when disk space remains available.

Validate the shipped rules and alert hold/recovery behavior with:

```sh
python3 scripts/test-proxmox-csi-capacity.py
```

The script also accepts a promtool command prefix (for example an isolated
container with the generated temporary directory mounted at its original path).
