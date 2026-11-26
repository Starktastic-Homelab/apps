# ADR 0017: Serve retained block volumes from a storage VM over iSCSI

- **Status:** Accepted
- **Date:** 2026-11-08

## Context

Retained application state (SQLite and WAL databases, PostgreSQL, Redis, monitoring stores) uses the stock
sergelogvinov Proxmox CSI driver (chart 0.5.15, driver v0.22.0, apps #1551).

- Each volume is a raw image `vm-9999-<name>.raw` on the Proxmox NFS storage `k3s-block`, backed by TrueNAS
  `apps/k3s-block`.
- The driver hot-plugs each image into a worker VM as a SCSI disk.

**The slot limit.**

- The driver only uses `scsi1`–`scsi29` (`for lun = 1; lun < 30`, `pkg/csi/utils.go` at v0.22.0), so each worker has
  29 slots.
- v0.22.0 is the newest release. The request for virtio-bus disks (sergelogvinov/proxmox-csi-plugin#182) was closed as
  not planned, and no open PR changes the limit.
- Proxmox caps a VM at `scsi0`–`scsi30` whatever the controller type (qemu-server `PVE/QemuServer/Drive.pm`), so other
  Proxmox-attached drivers hit the same wall.

**Live state, read-only on 2026-11-08 after the terraform#239 rebuild.**

- 33 live attachments: 15 on kube-worker-01 and 18 on kube-worker-02.
- 10 retired rollback images are bound but not attached.
- 33 volumes cannot fit in one worker's 29 slots, so losing either worker strands 4 volumes however they are placed.

**Per-volume ceremony.** Each volume needs a static PV/PVC pair, a guard entry, an init container, a source hold and a
runbook (3–10 files, apps commits f2a19da8, 8e27acc4, a7f1d79e, 663be3f9). An `nfs-pv` PVC needs none of these.

**Requirements Ben set on 2026-11-08:**

1. No per-VM attachment budget. Shrinking the volume count, a third worker and TrueNAS-specific guest iSCSI were all
   rejected as the design.
2. NAS-agnostic: no TrueNAS-only features, APIs or drivers. TrueNAS may be replaced.
3. After a full k3s rebuild or a Proxmox host reboot, the cluster reconnects to the same data from Git alone, as
   effortlessly as NFS. Identity fails closed: never start empty.
4. Adding a stateful app is close to adding an `nfs-pv` PVC.
5. Stock software only: no forks, no patched images, no locally maintained driver code, no adoption controller.
   Exception (Ben, 2026-11-21): the local lifecycle engine, `storage-fencer` and the node DaemonSet patch (Rationale).

**Recorded decisions that still hold:**

- SQLite and WAL must not live on a network filesystem (sqlite.org/wal.html: "WAL does not work over a network
  filesystem"; Jellyfin's storage documentation says the same).
- No Velero or backup dependency for bindings.
- One per-volume inventory, in apps.
- TrueNAS stays purely a NAS.
- Two workers.
- The off-site backup scope excludes regenerable stores (ansible `roles/proxmox_backup/defaults/main.yml`).
- Hung workers are fenced automatically at the storage side, never by a timer (Ben, 2026-11-09). Automatic fencing
  ships held: until a later decision turns it on, the manual fence is the only fence (Ben, 2026-11-21).

## Decision

Retained block volumes move from Proxmox CSI to a dedicated **storage VM**. The storage VM exports one LVM logical
volume per application volume as its own iSCSI target. The workers mount these targets as static PVs through
democratic-csi.

### Storage VM

**VM and disks**

- Debian 13, built from its own Packer storage image (below), with about 2 vCPU and 2 GiB RAM.
- It has its own Terraform root, `storage/`, with its own backend key in the same Garage `terraform-state` bucket,
  outside `modules/vm` and the k3s cohort. It uses `prevent_destroy` and `ignore_changes` on its clone source, so a new
  image, a cluster rebuild or a destroy-mode apply never replaces it.
  - `validate-and-plan.yml` and `drift.yml` gain a matrix entry for `storage/`.
  - `maintenance_apply.py` gains a `--chdir` argument, used in normal mode only, under the same maintenance lock and
    with no `infrastructure-changed` dispatch.
- **A deliberate rebuild is its own PR.**
  - The template pin comes from the storage entry of `packer-manifest.json`, selected by `builds[].name`.
  - Packer pushes are held while that PR is open, because every build replaces the template at its fixed VMID
    (`packer build -force`). The plan is re-run just before merging.
  - `apply.yml` checks through the Proxmox API that the clone source exists, so a missing template fails before the
    destroy.
- It is tagged `storage`, never `k3s`. It is not in the Proxmox CSI resource pool.
- **Two thin data disks on `k3s-block`**, each allocated once by hand (`pvesm alloc`). A placeholder VMID owns both, so
  destroying the VM leaves them alone (`destroy_vm` skips unowned disks, qemu-server `QemuServer.pm`).
  - The placeholder VMID must never exist as a real VM. 9999 is ruled out, because a VM with that ID would own every
    Proxmox CSI image.
  - Terraform only attaches the existing volids on a bus it manages (for example `virtio1`, `virtio2`), with
    `discard=on`. It never uses the ignored `disks[0].scsi`.
  - Terraform also declares the cloned root disk, `virtio0`, with the template's values, after the data disks (lab
    F10). On any change to the disk list bpg deletes every live ide, sata, scsi or virtio drive the config does not
    declare (cdrom and cloud-init excepted), and with `virtio0` first a plan gave it `virtio1`'s path. `data_disks`
    refuses `virtio0`. Any `data_disks` change re-sends every disk's options.
- Disk `retained`, VG `retained`: every volume that is backed up.
- Disk `regen`, VG `regen`: prometheus, loki, tempo, alertmanager and karakeep-meilisearch. The off-site job excludes it
  by one path, which keeps today's backup scope.
- **Decided (2026-11-18, Ben): the disks stay host-attached as above (D1).** Both host oopses (10-23 and 11-15) died in
  pve's NFS client, the one that mounts `k3s-block`, and every retained byte passes through that client. The lab also
  qualified variant N (the storage VM mounts the export itself and attaches the files as loop devices). It was rejected:
  - a late NFS at boot left variant N running with 0 targets, retained included, until a manual start, and blocked SSH
    for 90 s; the host path refuses to start the VM instead (lab B10 Step 4). Nothing retries that start: recovery
    is a manual `qm start` once the NFS is up (lab: starting the NFS VM and then the storage VM brought every target
    back in 45 s), and until then every retained app
    waits and in-cluster alerting is down (see Open questions);
  - it needs a storage-VM NIC on TrueNAS's network, an export entry, mount and loop units, and fixes for both findings;
  - its only gain lasts from Retirement until TrueNAS is replaced by the storage VM itself, when no NFS is left under
    the block data and pve's NFS exposure ends on either path.

**Volumes**

- Each volume is one LV with ext4, created with `mkfs.ext4 -O mmp -e remount-ro`.
- Each LV is exported as its own LIO target (`targetcli-fb`), with a single LUN 0 and ACLs for the two worker IQNs. The
  target IQN is `iqn.2026-11.net.starktastic.storage:<id>`.
  - One target per volume means unstaging one volume never logs out a session that other volumes share.
  - rtslib refuses a block backstore whose device does not exist. `targetctl restore` still creates that volume's target,
    portal and ACLs, but with no LUN 0 (rtslib `target.py`), so a missing LV yields a target with nothing behind it. The
    boot check below therefore asserts LUN 0 per ledgered LV, not just the target.
  - Each backstore gets a deterministic T10 serial (`wwn`) derived from the `id`, so a rebuilt storage VM presents the same
    SCSI identity.
- Backstores set `emulate_tpu=1`, so discards reach the thin disk.
- **Metrics.** `prometheus-node-exporter` runs with a textfile collector. The reconcile (its dry run too) and the
  expiry job write `vg_free_bytes` per VG, `pending_delete{id,since}`, `hold_create`, `target_missing{id}` and
  `last_reconcile_success_timestamp`. apps scrapes it on the bridge address (tcp/9100) and alerts when the target is
  `up == 0`. The storage's NFS mount uses `vers=4.2`, so a discard
  becomes a hole punch in the raw file.

**Restoring the configuration at boot**

- The reconcile ends with `targetctl save`.
- At boot, `rtslib-fb-targetctl.service` restores that file. Only the role's own commands activate `retained` and
  `regen` (lab F24, Ben 2026-11-19). Debian's stock LVM would otherwise activate both VGs at every boot, unscoped and
  untimed, in the initramfs (its udev rule runs `vgchange -aay`) and again in the main system. The storage image turns
  every stock path off: `event_activation = 0` in `lvm.conf`, copied into every initramfs and checked there at build
  time; `lvm2-monitor` and `blk-availability` masked; lvm2 held. The role's targetctl drop-in (`50-homelab.conf`) only adds
  `Wants=`/`After=network-online.target` and activates nothing, so before the first deploy the VGs stay inactive and
  the reconcile activates them scoped when it needs them. The role refuses a storage VM where stock activation is on
  or ran on the current boot (`/run/lvm/vgs_online` or `pvs_online` not empty). The role's drop-in:
  - activates retained from its own PV (`ExecStartPre=/sbin/vgchange --devices <retained PV> -ay retained`) with **no
    fallback**: a wrong path fails the unit at that line and no target is restored, regen included (fail closed; the
    fence set is still restored by `nftables.service`). Regen activates through `storage-reconcile activate --vg
    regen`, which gives up after 30 s without killing the command, and its leading `-` keeps a missing `regen` disk
    from stopping the `retained` targets; the boot check below still fails the unit for it. `KillMode=process` keeps a
    failed start or a stop from signalling a command that was given up on. The unit is ordered after the retained
    PV's `.device` unit;
  - runs an `ExecStartPost` check that fails the unit if any ledgered LV lacks a target with LUN 0 bound to
    `/dev/<vg>/<id>`. `targetctl restore` skips missing devices and still exits 0.
  - A fresh or rebuilt root boots before the role installs the drop-in, so that boot never ran the check. A
    `storage.yml` run that finds no `storage-boot-check.prom` while the unit is `active` runs
    `storage-reconcile boot-check` once, after the reconcile (so the targets exist) and before the grow; a non-zero
    exit fails the run in its last play.
- `targetctl restore` clears the live configuration first, and the unit's `ExecStop` is `targetctl clear`. So a restart
  of `rtslib-fb-targetctl.service`, including one triggered by a package upgrade, drops every session. The image holds
  `python3-rtslib-fb` and `targetcli-fb` (`apt-mark hold`), and nothing ever restarts that unit; upgrades are deliberate.
  It holds `lvm2` too: an lvm2 upgrade runs an unscoped `vgcfgbackup` and may replace `lvm.conf` (F24).
- `targetctl save` copies over the save file in place, not atomically. The reconcile saves through rtslib to a temporary
  file and renames it over `/etc/rtslib-fb-target/saveconfig.json`.
- Debian ships `nftables.service` disabled, and a restart flushes the ruleset before loading it. The image enables it, and
  handlers only ever reload it. A restart by hand leaves the storage VM with no ruleset, every port open, for up to
  about 0.16 s (lab).
- So a reboot of the storage VM or the host brings every target back without ansible, and a partial restore shows up as
  a failed unit. Nothing alerts on that unit yet (lab F2): node-exporter has no systemd collector, and
  `target_missing` is written only by the reconcile, which runs only from `storage.yml`. See Open questions.
- **A stalled data disk holds the whole boot (accepted, Ben 2026-11-19, lab F24).** If either data disk's backend does
  not answer while the storage VM boots, the kernel's probe of that disk waits on its partition-table read and the VM
  stays in the initramfs for as long as the stall lasts (no bound seen up to ~290 s). No target is served meanwhile,
  `retained` included, even when its own disk is fine. Once the stall ends the VM comes up within about 2 s and
  activates both VGs scoped as above (lab: 180 s stall). LVM settings cannot reach this wait. One boot with
  `module.async_probe=1` was worse: the VM did not recover after the stall, left no journal and needed a reset (cause
  unproven, no console capture). So the image keeps the stock kernel command line. Workers keep retrying login
  meanwhile (Boot order). Revisit only with a console-captured test.

**Disposable**

- The VM itself is disposable. Ansible re-renders the full target configuration from the apps inventory and the on-disk
  ledger.
- A rebuild cuts I/O to every volume for about 2 min 23 s (lab F9), longer than the initiator's `replacement_timeout`
  (120 s): every mounted filesystem would go read-only and need a pod restart, and the remount leaves the ext4 error
  flag set. So a rebuild is done deliberately, never as part of a fleet rebuild, and only after its writers are
  drained (scaled to 0). Raising `replacement_timeout` would not cover it. When a flagged filesystem gets an offline
  `e2fsck` is an open question.

### Packer images (decided by Ben on 2026-11-08)

Packer builds three templates instead of one:

| Image | Built from | Contents |
|---|---|---|
| Base | Debian ISO | The parts every VM shares today: preseed install, `full-upgrade`, qemu-guest-agent, cloud-init and its config, netplan with systemd-networkd/resolved, the GRUB timeout. **No GPU stack and no compiler:** the preseed's `pkgsel/include` drops `build-essential` and keeps `qemu-guest-agent` and `openssh-server`. |
| k3s | Base, via `proxmox-clone` | Today's k3s-only parts: build-essential, dkms, kernel headers, i915 SR-IOV DKMS and its kernel-series check, GPU firmware and VA driver, the i915 GRUB parameters, `nfs-common`, removal of ModemManager. |
| Storage | Base, via `proxmox-clone` | `targetcli-fb`, `lvm2`, `nftables`, `prometheus-node-exporter`, and the `rtslib-fb-targetctl.service` drop-in. Stock LVM activation off (`event_activation = 0`, every initramfs checked, `lvm2-monitor`/`blk-availability` masked, `lvm2` held; F24). A build check fails if `build-essential` or `gcc` is present. |

- **Why split.** The storage VM carries no compiler, no out-of-tree kernel module and no i915 pin.
- **Seal every image.** One step runs last in **all three** builds:
  - truncate the machine-id and relink the dbus copy;
  - `cloud-init clean --logs`;
  - delete the builder user, and in clone builds also `/etc/sudoers.d/90-cloud-init-users`.

  Without it, each layer's build boot would commit a machine-id and cloud-init state into every VM cloned from it.
  Clone builds run `cloud-init status --wait` before their first `apt` call.
- **Clone sources** set only `ssh_username`, with no password, key file or agent, so the plugin injects an ephemeral key
  through cloud-init. `clone_vm_id` points at the base template.
  - The three templates get distinct VMIDs and `vm_name` prefixes.
  - The placeholder VMID that owns the data disks is outside every packer and terraform range.
- **Build pipeline.**
  - `build.yml` builds the base first (`-only`), then k3s and storage.
  - One manifest PR carries the entry of every build that succeeded, so a failed k3s build (for example the
    kernel-series check) does not block the storage entry (D16).
  - It takes the release tag from the k3s entry, and fails if that entry is missing; the terraform PR title names every
    template it updates (D16).
  - `i915_sriov_version`, `i915_sriov_kernel_series` and `iso_name` stay in `debian.auto.pkrvars.hcl`.
- **Manifest contract.** The packer manifest carries three builds. terraform's `packer-manifest.json` consumers
  (`apply.yml`, `validate-and-plan.yml`, `drift.yml`, `variables.tf`) select the k3s template by name. The storage root
  reads the `storage` entry the same way: CI passes its `artifact_id` and `custom_data.vm_name` to the root as
  variables, and the clone check refuses a template at that VMID with another name (Ben, D16).
- **First build.** The first build in the new layout is a template change, so it replaces every k3s VM (a full cluster
  rebuild). Hold apps merges around it.

### Storage network

- A new Proxmox bridge with no physical uplink. It is added by an additive ansible task that never rewrites the host's
  interfaces file, and it ships in its own PR first.
- Only the storage VM and the two workers get a second NIC on it, through a terraform `storage_nic` variable that the
  master never sets.
- The workers get theirs in the Foundation full rebuild, as a `storage_nic` commit on the first k3s manifest PR, so no
  in-place worker update strips `wwn=` from Proxmox CSI disks (Ben, D3).
- The LIO portal listens only on the storage VM's bridge address: `auto_add_default_portal=false`, no wildcard portal.
- The nftables input chain on the storage VM is policy drop. Its first rule drops the `fenced` set (see the hang
  policy). It then accepts:
  - established and related traffic, and `lo`;
  - tcp/22 from the runner and the LAN, for ansible;
  - tcp/3260 and tcp/9100 only on the bridge, from the two workers' bridge addresses.
- There is no CHAP. Every iSCSI driver checked passes CHAP secrets in `iscsiadm` argv. The trust boundary is the bridge,
  which means everything on a worker that can reach the bridge NIC.
- **Subnet.** Production reserves 10.99.2.0/24 (`vmbr2`) and the lab uses 10.99.9.0/24 (`vmbr9`). Neither is routed
  or has a gateway. The portal address is part of every PV's identity, and a PV's source cannot be changed, so the subnet
  stays fixed.
- **Nodes on another machine (not planned).** Carry the bridge over a dedicated tagged storage VLAN with no gateway on
  OPNsense, and keep the subnet. Not over vmbr0/vmbr1: same-host traffic would not leave the host either, but without CHAP
  every LAN device would be one hop from tcp/3260, and OPNsense's inter-VLAN SNAT hides routed sources (Ben, 2026-11-16).
  Such a node also needs a static ansible inventory entry, its IQN in the ACLs, an nftables allow and a fencer config
  entry. Proxmox boot order does not cover it.

### Workers

**Initiator**

- Before iscsid first starts, ansible writes `/etc/iscsi/initiatorname.iscsi` as
  `InitiatorName=iqn.2026-11.net.starktastic:<inventory_hostname>`, then installs `open-iscsi`.
- ansible sets `node.startup = manual` in `/etc/iscsi/iscsid.conf`, so no session opens at boot and every login comes
  from kubelet's NodeStage. The fence's "Why this is enough" argument relies on it.
- The storage VM renders its ACLs from the same worker list with the same formula. A rebuilt worker therefore keeps its
  IQN, and the ACLs come from Git.
- `open-iscsi` is not baked into the k3s image, because a baked image would give every clone the same IQN.
- Workers never get RAM (`vmstate`) snapshots or hibernation; see the hang policy.

**Driver**

- democratic-csi **v1.9.5 in `node-manual` mode**, pinned, with the external attacher (`attachRequired: true`), so
  VolumeAttachments exist.
- It runs with `FILESYSTEM_TYPE_DETECTION_STRATEGY=blkid`. The default `lsblk` strategy reports "not formatted" whenever
  udev data is missing, which would let the driver mkfs over data. With `blkid`, only exit code 2 counts as blank, and
  any other error fails the stage (`src/utils/filesystem.js:507-527` at v1.9.5).
  - Residual risk: `blkid` also exits 2 when it cannot open or probe the device (util-linux `blkid.c`), and the driver
    would then format it. The guards are what catch that case for a populated volume.
  - The driver config sets `node.format.ext4.customOptions: ["-O", "mmp", "-e", "remount-ro"]`, so a filesystem the
    driver makes (a skipped migration copy) still gets MMP.
  - On the storage VM, the reconcile runs `mkfs` only on an LV it created in the same run, after a successful direct
    read of its first MiB, and never on `blkid` alone.
- It runs with `MOUNT_DEFAULT_TIMEOUT=900000` (ms; lab F6, Ben 2026-11-19). After a fencing failover ext4 MMP holds the
  next mount about 42 s, up to about 720 s on slow storage. The default 30 s timeout does not stop that mount but
  reports `INTERNAL`, which kubelet treats as final: a pod deleted before kubelet's retry then leaves the mount and the
  iSCSI session on that node, and nothing cleans them up. With 900 s, kubelet's own 2 min NodeStage deadline fires
  first and is non-final, retries during the wait get `ABORTED` from the driver's volume lock, and an uncertain stage is
  unstaged when its pod goes. The cost: `umount` and `findmnt` share the timeout, so a hung unmount of a dead
  filesystem holds that volume's lock for up to 15 min.
- NodeStage's login retry is bounded but long (lab F1): `retry(15, 2000)` around `iscsiadm -l`, each login about 2 min,
  so a stage against a target that does not answer holds the volume's operation lock for about 30 min. Meanwhile the
  pod's NodeUnstage is refused, the VolumeAttachment can outlive its PV, and a target with that IQN created inside the
  window would be logged into with no pod. Not mitigated; see Open questions.
- Each volume is a static PV/PVC: `ReadWriteOncePod`, `Retain`, Argo `Prune=false,Delete=false`.

**k3s settings**

- `disable-force-detach-on-timeout=true` on the servers' kube-controller-manager. The ansible role's tests pin it, but
  nothing checks at runtime that kube-controller-manager runs with it; without it a hung worker's volumes move on a
  timer with no fence (see Open questions).
- Graceful node shutdown through a kubelet config drop-in, `/var/lib/rancher/k3s/agent/etc/kubelet.conf.d/50-graceful-shutdown.conf`,
  with `shutdownGracePeriod: 90s` and `shutdownGracePeriodCriticalPods: 40s` (non-critical pods keep 50 s; the critical
  tier covers the node plugin's 32 s hold). kubelet has no command-line flag for these settings; k3s passes that
  directory to kubelet as `--config-dir`.
- Argo CD `kustomize.buildOptions: --enable-helm`, so democratic-csi renders as kustomize `helmCharts` plus a patch on
  the node DaemonSet (below). The ansible change deploys before the apps storage branch merges. The lab applied that
  patch by hand to a helm-installed DaemonSet, so its render through Argo CD is first proven by the apps PR's diff
  preview and first sync. The upstream fix (democratic-csi/charts PR #77) is unmerged, so every chart bump re-checks
  the patch: without it, a node DaemonSet rollout with volumes staged can lose unflushed writes again (lab F21).
- `fstrim.timer` enabled.

### Boot order

- ansible `group_vars/proxmox_hosts/guest_startup.yml` gives the storage VM `order=2,up=30`. In the lab, discovery from
  a worker listed every target within 11.4 s of `qm start` (B10, two runs). TrueNAS stays at `order=1,up=180`
  (ansible#314). Terraform ignores `startup` on the storage VM, as it does on the k3s VMs.
- The workers stay unordered, so Proxmox starts them after the storage VM and shuts them down before it.
- A worker that comes up early keeps retrying iSCSI login, and its pods wait in ContainerCreating.

### One inventory, reconciled automatically

**The inventory.** apps owns one JSON file with one entry per volume:

| Field | Meaning |
|---|---|
| `id` | Immutable. It names the LV, the target IQN and the ledger key. |
| `namespace`, `claim` | Render inputs for the PV and PVC only. `claim` is `<id>-iscsi`, or `<id>-iscsi-<sts>-0` for a kube-prometheus-stack operator StatefulSet (Ben, 2026-11-25). |
| `size` | Volume size. |
| `class` | `retained` or `regenerable`, which picks the VG. |
| `origin` | `migrated` or `new`. |

apps renders every PV and PVC from this file, and the generic guard's ConfigMap `retained-startup-guard` in each
namespace the file names (migration plan Task 2.9, D48). A new
app-template app opts in with `retained: <id>` (Ben, 2026-11-22; Guards, "The one-flag guard"); a migrated app moves
through its binding switch PR (Migration 3).

**apps CI rejects:**

- a `claim` other than `<id>-iscsi` (or `<id>-iscsi-<sts>-0` for a kube-prometheus-stack StatefulSet). A changed `id`
  is therefore a removal plus a new entry with a new claim, which the removal rule below refuses while git still
  binds the old claim;
- an `id` that does not match `^[a-z0-9][a-z0-9-]{0,62}$`, or that starts with `snapshot` or `pvmove` (lvm2 rejects
  those prefixes). It must be a valid LV
  name, target IQN and LVM tag.
- a changed `class` or `origin` for an existing `id`. Moving a volume between VGs is a manual runbook step: a new `id`
  plus a copy.
- a size decrease;
- sizes in one VG (one `class`) that add up to more than that VG's usable size, or that leave less than the snapshot
  reserve free in it (Capacity). The VG sizes come from terraform `main` `storage/terraform.tfvars` (`data_disks`,
  `serial` = VG), read at CI time and failing closed;
- duplicate IDs;
- more than 2 removals in one change, unless the PR carries the `storage-removals-approved` label. The label passes
  apps CI only. The storage side has its own brake (`max_removals`, 2 per run), which the label does not reach: a
  labelled change of more than 2 removals needs the `storage.yml` dispatch input `max_removals` for one run (Ben OK),
  or it is split into PRs of at most 2 removals, each reconciled before the next merges. Until then every `storage.yml`
  run refuses `removal-brake` before the lock and applies nothing;
- a removal whose claim git still binds: an app's values (by namespace, including derived StatefulSet claims and
  `volumeName` ids) or a committed manifest still names it. Expiry would delete a volume that an app at 0 replicas or a
  CronJob between runs still needs. The label does not cover this.

**Triggers.** An ansible workflow, `storage.yml`, has its own concurrency group. It runs on:

- `repository_dispatch` `storage-changed`, sent by an apps workflow on a push to `main` that touches the inventory, with
  `ORG_DISPATCH_TOKEN`;
- `workflow_dispatch`;
- a push to ansible `main` that touches the storage role, its playbooks or `group_vars/storage`;
- an hourly schedule (`5 * * * *`), as a backstop. Scheduled runs skip the backup windows (ansible
  `scripts/storage_ready.py` `WINDOWS`; migration plan D29, Ben 2026-11-23, kept on GitHub Actions), so the gap between
  scheduled applies is up to about 3 h (4 h on the DST fall-back Sunday). `StorageReconcileFailing` fires after 5 h with
  no successful reconcile; its threshold follows `WINDOWS` and is rechecked by hand when they change.

CI does not reject an `id` that comes back. Reverting an accidental removal within the 3 days has to work, and only the
storage side knows whether an `id` was actually deleted (the tombstone row below).

**How a run works.**

- The dispatch is only a wake-up. Every run reconciles against apps `main` HEAD and logs that SHA, so an old or
  out-of-order dispatch cannot re-apply an older inventory.
- A run first validates read-only: the schema, the brakes, whether both VGs and the ledgered LVs exist, and whether
  each new or grown volume fits its VG's free space (`no-space`, migration plan D40). A refusal exits before the run
  takes the maintenance lock. The dry run writes the reconcile gauges too, without moving the last-success timestamp, so
  a refusal before the lock reaches Prometheus. It marks a target missing only for an id already exported or refused
  `lv-missing`, never for a volume the apply has yet to create, so a skipped apply never fires `StorageTargetMissing`.
- Before the dry run, a run asks k3s on `masters[0]` for `/readyz` (`storage-preflight.yml`). No k3s binary, no
  kubeconfig or no `ok` answer (a k3s rebuild before its deploy) skips the run green with a warning, without the lock;
  an unreachable master, any other error, or a check that writes no answer fails it, still without the lock. The
  expiry does the same, after it fetches and validates the inventory, so a missing inventory file fails before the
  lock instead of keeping it. A missing file never reads as an empty inventory. The adopted-lock path (D51) skips this
  check.
- Before any config, nftables or ACL write, a run refuses a worker that is in the installed `config.json` but not in the
  rendered worker list: a Proxmox inventory drop-out lists a guest with only a warning, and its ACLs would go. A
  deliberate removal passes only when the `storage.yml` dispatch input `remove_workers` names it, for that run. Even
  then the reconcile never deletes the ACL of an initiator with an iSCSI session, or with unreadable session info,
  except a fenced worker's, so the worker is drained first. A worker that drops out between the dry run and the apply
  is refused under the lock, which the failed run keeps (D31).
- A run tries to take the lock once. If the lock is held, it exits 0 with a warning, and the next hourly run retries. The
  pinned helper has no distinct exit code for a held lock (its `acquire` fails with exit 1), so the workflow checks for
  `/maintenance/operation.json` just before `acquire`, which is race-free on the single runner. An alert fires when the
  lock has been held for over 6 hours, so a stale lock cannot silently skip every run.
- A failed `storage.yml` or `storage-expiry.yml` run keeps the maintenance lock, as `deploy.yml` does, until a person
  releases it; `MaintenanceLockStale` fires after 6 hours. A `no-space` or `vg-missing` refusal at apply time fails the
  run the same way (migration plan D31, Ben 2026-11-22).
  The design assumes a single self-hosted runner process, which serializes these jobs with deploy and apply. If a
  second runner is ever added, `deploy.yml` and `maintenance_apply.py` need a bounded wait on acquire as well.
- `deploy.yml` has no storage play. Export and repair come only from `storage.yml` runs (dispatch, push, hourly), so
  a lost target returns within the hour, or up to about 3 h across the window skips. Neither path deletes; only the
  expiry below does.
- A reconcile refuses, changing nothing, while the storage VM's boot restore (`rtslib-fb-targetctl`) is not settled:
  still running, queued, or unreadable. That restore clears the live LIO config first, so a run racing it would be
  undone. A failed unit or a failed boot check does not refuse, because the restore runbook's fix is a `storage.yml`
  run. The refusal fails the run; it takes no lock in the dry run, and keeps the lock (D31) when it comes at apply
  time, after a reboot since the dry run.

**Reconcile rules.** The ledger is an LVM tag set on each VG. It records a state per `id` (`creating` or `created`) and a
tombstone for each deliberately deleted `id`. It lives in the VG metadata on the data disk.

IDs are one namespace across both VGs. Before creating anything, the reconcile reads the ledgers, LV names and tombstones
of both `retained` and `regen`, and refuses an `id` it finds in the other VG.

| State | Action |
|---|---|
| In the ledger as `created`, LV exists | Ensure the target, ACLs and portal, leaving out the ACL of any worker named in a `fenced:` tag. If the size grew and the VG has the free space (else refuse `no-space`, keep the export), run `lvextend`, then on the worker with a logged-in session to the target (more than one refuses) run `iscsiadm -m session -R`, and online `resize2fs` only if `findmnt --source <device>` shows ext4 mounted. A VolumeAttachment alone is not enough: it outlives the login and the mount (lab F5). The step is level-triggered, so a skipped filesystem grows on a later run. A worker that does not answer within 30 s is skipped with a warning and the run stays green; a grow that fails on a reachable worker fails the run. democratic-csi node-manual advertises no volume expansion, so only the PV capacity follows the inventory. The PVC request is the constant `1Mi` for every entry: a bound static PVC with `storageClassName: ""` can never change its request, so only the PV capacity follows `size`; `kubectl get pvc` keeps showing the bind-time capacity. |
| Not in the ledger, no LV, `origin: new` | Create, in this order: a VG free-space check, which refuses the entry if the VG is short (Capacity); ledger `creating`; plain `lvcreate`, which fails if the LV exists; `mkfs.ext4 -O mmp -e remount-ro` only if `blkid -p` exits 2; identity marker; ledger `created`; target. |
| Not in the ledger, no LV, `origin: migrated` | Create a raw LV (the same free-space check, then ledger `creating`, then `created`) with **no mkfs and no marker**. The only filesystem and marker it can ever hold come from the migration copy, so a skipped copy fails closed at the guard. |
| In the ledger, LV missing | Refuse, fail the run and alert. Never recreate. |
| LV exists but not in the ledger (orphan) | Refuse. Adopting an orphan is a manual tag operation after inspection. |
| Ledger still `creating` (crashed run) | Refuse for manual review. Never retry automatically. |
| Inventory size smaller than the LV | Refuse that entry. Never shrink. |
| `id` has a tombstone | Refuse: a deleted volume never comes back. A new volume takes a new `id`. |
| One VG missing, or not answering within 30 s (lab F11) | Refuse that VG's entries (`vg-missing`) and fail the run; no create, grow, export change or expiry for them, and their live targets stay. An entry of the other VG whose cross-VG `id` check cannot be done is refused as `other-vg-unread`; the rest of the other VG's entries still apply (migration plan Task 2.10). This split acts at apply time, against a VG lost mid-run: a VG already missing at the dry run fails the run before the lock is taken (migration plan D42, accepted by Ben 2026-11-22). The dry run fails even with an empty inventory. Creating a VG is a one-time manual bootstrap. |
| Both VGs missing or not answering | Refuse everything: no create, grow, export change or expiry; live targets stay. |
| VG tagged `hold_create` | Export what exists, create and delete nothing, and fail the run listing every inventory entry that has no LV. |
| Entry removed from the inventory | Tag the LV `pending-delete` with a date and alert. The target stays exported. Re-adding the entry clears the tag. |

**Deletion.** A daily scheduled job takes the lock and handles `pending-delete` LVs older than **3 days**, against
`main`.

- It skips a VG tagged `hold_create`.
- It acts only when every check passes:
  - the Kubernetes API answers. It uses the kubeconfig from `masters[0]` with its server rewritten to the kube-vip address,
    as `i915-acceptance.yml` does;
  - no PV whose `volumeHandle` matches the target has a VolumeAttachment, or a bound PVC used by a Pod. This also catches
    temporary migration copy pairs. PVCs are found through each PV's `claimRef`.
  - the LIO target has no session: for every NodeACL under it, `acls/<iqn>/info` is read directly from configfs and
    shows no active session, and `dynamic_sessions` is empty. A read error counts as in use. rtslib's `NodeACL.session`
    is not used, because it returns `None` on a read error.
    `dynamic_sessions` alone proves nothing here, because it lists only demo-mode sessions and every worker logs in
    under an explicit ACL.
- It then deletes those PVCs and PVs, removes the target, runs `blkdiscard`, runs `lvremove`, and records the tombstone.
  The storage-VM step refuses while the boot restore is not settled, as the reconcile does.
- Any error counts as "in use": it skips and alerts.

Merging the PR that removes an entry is Ben's approval to delete. Snapshots taken before the deletion stay in the local
replica for their 2-week retention.

### Guards

- The identity guards stay. Those of `origin: new` volumes come from the one-flag layer (an `app.yaml` key, below),
  or are hand-wired in a plain manifest like the canary; only the guard ConfigMap's namespaces come from the
  inventory. Migrated volumes keep their hand-wired guard init container until Retirement, when the ones the one-flag
  layer can serve convert to it.
- **No native-layout checks** (Ben, 2026-11-22). A guard checks the identity marker (generic guard, below), not lists of
  the app's files, directories or file headers. There are no per-app file lists to keep in step with app upgrades. The
  marker is what fails a blank, freshly formatted or skipped-copy volume closed, because none of those holds it.
- **One generic marker guard** (D47, Ben 2026-11-22): "Why can't it be generic? If the guards cannot be generic, then
  we should consider dropping the guards." Every retained guard runs the same script, and shared guard code holds no
  app names. Since apps#1707:
  - the script is `infrastructure/base-configs/files/retained-startup/guard.py <app> <root> [<kind> [<marker-file>]]`.
    `kind` is `data` (the default) or `config`, and the marker file defaults to `.homelab-<app>-<kind>`. It accepts
    only a regular file of 1 to 128 bytes, not a symlink, holding exactly `homelab/<app>/<kind>/v1` and a newline;
  - `templates/retained-startup-guard.yaml` renders it into ConfigMap `retained-startup-guard` in the namespaces
    `databases`, `home-automation`, `media`, `monitoring` and `operations`, and (from migration plan Task 2.9) in
    every namespace with an inventory entry. Its accept line is
    `Retained identity accepted.`;
  - there are no content checks, no database checks against the Postgres backend, and no Postgres system-identifier
    checks. apps#1707 removed them all (D47). `postgres` and `immich-postgres` carry markers on their claim roots,
    outside PGDATA, like every other volume. Enrollment and completion gates are not guards and stay.
  - Jellyfin and filebrowser got markers before they move, and run the same guard.
- **The one-flag guard** (Ben, 2026-11-22). An app-template app opts a volume in with `retained: <id>` in its
  `app.yaml`. The `cluster-apps` ApplicationSet then adds the shared values file `templates/retained-guard.yaml` and
  passes the id to Helm. That one file carries what each app used to copy by hand:
  - the guard init container, keyed `0-retained-guard` so it runs first, with the guard image digest pinned once and a
    fixed non-root uid;
  - the claim `<id>-iscsi`, mounted read-only in the guard only, with a default `/config` mount in the main container
    (an app with other paths sets its own mount list);
  - the generic guard, run as `python3 -I -B /retained-startup/guard.py <id> /retained` from ConfigMap
    `retained-startup-guard` (one guard, migration plan D48, Ben 2026-11-22);
  - `strategy: Recreate` (the claim is RWOP), and the common NFS `config` volume turned off.

  A new `/config` app is therefore one inventory entry plus one `app.yaml` line, which is requirement 4. It fails
  closed: an empty id fails the render, a missing layer leaves the inventory claim unconsumed (CI rejects it), and an
  id with no inventory entry leaves the pod Pending.
  The flag starts with `origin: new` only.
- **Shared guard code holds no app names** (D46, Ben 2026-11-22). Adding a stateful app must never mean editing shared
  guard code. The group scripts under `infrastructure/base-configs/templates/*-block-storage/` used to break that:
  they listed apps by name. apps#1707 replaced them, and every per-app guard, with the generic guard above (D47).
  What is left:
  - **The rendered guard** (migration plan Task 2.9) is the guard of `origin: new` volumes: the generic guard above,
    from `retained-startup-guard`, called with the volume's id, so there is one guard implementation (migration plan
    D48, Ben 2026-11-22: "Yes, one guard"). It holds no app names and no app versions.
  - **Migrated volumes convert later.** After Retirement (migration plan Task 5.12, once the last reverse-copy window
    has closed, because the reverse source gate copies the hand-wired guard), app-template apps can move to
    `retained: <id>`. Volumes the layer cannot serve (other charts, StatefulSet controllers, second volumes) and the
    NFS-side guards keep their hand-wired generic guard.
  - **Marker names that differ from the id** (about ten, autobrr's in a different shape) come from an apps-only file in
    the shape of `infrastructure/base-configs/files/ordinary-file-volumes.json` with per-id `app`, `kind` and
    `marker_file` fields (apps#1707 dropped that file's unread `marker`/`identity` fields), which ansible never reads. How they
    reach the layer's command is open until migration plan Task 5.12: the layer renders inside each app's chart and
    cannot read base-configs files. Markers on retained data are never rewritten to fit the id.
  - **The freeze.** apps CI keeps `guard.py` free of app names and refuses any ConfigMap named `*retained*` that app
    values mount, other than `retained-startup-guard`. An `origin: new` volume's guard must be `guard.py` called with
    its id. `retained-startup-guard` stays: the hand-wired guards and the one-flag layer both mount it.
  - Each conversion restarts its app once. Conversions run in batches outside backup windows, each merge with Ben's OK.
- **apps CI proves every retained claim is guarded.** Keyed off the inventory, never off the flag, it renders every app
  with the ApplicationSet's layering. An `origin: new` claim, or a migrated one with `copied` set, needs exactly one
  consuming app; a migrated claim without `copied` (before its switch, or after a switch revert) needs none. Each
  consumer needs exactly one guard init container that mounts the claim read-only with its guard ConfigMap, and no
  init container that mounts the claim before it. A flagged app's claim is named `<id>-iscsi`.
- The guards catch a wrong or blank filesystem before the app starts. The `blkid` strategy is what stops the driver
  formatting over data whose udev data is missing; a device `blkid` cannot open still reads as blank (residual risk,
  Driver). Guards cannot stop either, because NodeStage runs before any init container.

### Hang policy and old-writer exclusion

Ben chose automatic storage-side fencing on 2026-11-09, replacing the earlier manual-only policy. It ships held:
`hold_fence` stays set and the manual fence stays the only fence until a later decision turns it on (Ben, 2026-11-21).
The rule it keeps is **never move a volume without proof that the old writer is cut off**. Kubernetes' blind timer stays
off. The out-of-service taint, which force-detaches, is applied only after the storage VM has proven that the old worker
can no longer reach any target.

**The fencer.** A small service, `storage-fencer`, runs on the storage VM. It is local code (Python, shipped and tested
by the ansible storage role), not driver code. It runs there because the storage VM holds the fence point (LIO and
nftables), it needs no Proxmox credential, and when the storage VM is down there is nothing to fence.

- **Credential.** A ServiceAccount, `storage-fencer`, defined in apps. Its ClusterRole can `get`/`list`/`watch` and
  `patch` nodes, and `get`/`list` VolumeAttachments. The fencer only touches the workers in its config, which ansible
  renders from the same worker list as the ACLs, together with each worker's bridge address.
  - The storage role copies the token Secret to `/etc/storage-fencer/token` (mode 0600, `no_log`) on every
    `storage.yml` run (dispatch, push, hourly; `deploy.yml` has no storage play), and restarts the fencer if the token
    changed. Across the window skips the next run can be about 3 h away.
  - A missing Secret is only a warning, so a k3s rebuild never blocks on it. After a rebuild the next run copies the new
    token.
- **API address.** The kube-vip address, over the LAN NIC. nftables filters input only, so this needs no new rule.
- **State.** The durable record of a fence is a VG tag on `retained`, `fenced:<node>:<bootID>`. It lives in the VG
  metadata, so it survives a storage-VM rebuild, and the reconcile reads it.
  - A tag is **unsettled** (`fenced:<node>:unknown`) from the moment it is written until the fence has been proven. The
    first API read after a passing proof **settles** it: one `vgchange` replaces `unknown` with the worker's bootID in
    that read. An unsettled tag is never cleared automatically.
  - The fencer also keeps `/var/lib/storage-fencer/bootids.json`: every bootID it has seen per worker while the worker
    was not fenced. It is frozen while the worker is fenced.
  - A rebuilt storage VM starts that file empty. The tag carries everything safety needs.

**When it fences.** Every 15 seconds it reads the nodes and VolumeAttachments. It fences a worker only when all of these
hold:

1. The API server answers with valid credentials. A fencer that cannot see the cluster does nothing.
2. The worker's `Ready` condition has not been `True` for at least **5 minutes**, counted from the later of its
   `lastTransitionTime` and the fencer's **watch start**: the server time of the fencer's first successful API read
   after it starts, after a loop whose API read failed, or after more than 3 loops (45 s) without a successful read,
   such as a long LIO lock wait. After a host cold boot the API still shows each worker's
   NotReady from before the shutdown, older than 5 minutes; without the watch start the fencer would cut a worker
   that is booting normally (lab finding F18).
3. Another worker is `Ready` and does not carry the out-of-service taint. Fencing gains nothing when there is nowhere to
   move, and two failing workers at once point to a network or control-plane fault rather than a dead worker.
4. No other worker is fenced. At most one worker is fenced at a time.
5. Every VolumeAttachment on the worker belongs to democratic-csi. The taint force-detaches every driver's volumes, and
   the fence proves nothing about Proxmox CSI disks, so a worker that still holds one is refused.
6. The `retained` VG is tagged neither `hold_fence` nor `hold_create`. `hold_fence` is the manual pause for runbooks and
   the migration, and it stays set after Retirement until a later decision turns automatic fencing on (Ben, 2026-11-21).
   It blocks new fences only: a fence that has started finishes, taint included (see below).

**How it fences.** It works under the storage VM's LIO lock (`flock /run/lock/storage-lio`, which the reconcile shares),
in this order:

1. Write the tag `fenced:<node>:unknown`. The bootID is not chosen here, because any choice made before the cut can
   be wrong: a worker can reboot, be `Ready` and mount between two reads, and kubelet mounts volumes even while
   NotReady.
2. Ensure the worker's bridge address is in the nftables set `fenced`. A drop rule for that set comes **before** the
   established/related accept, so open connections stop as well.
3. Delete the worker's NodeACL from every target, logging each ACL's session (`acls/<iqn>/info`) first. Removing an ACL
   is synchronous: LIO shuts down that initiator's sessions and waits for them to go.
4. **Prove it.** Poll for up to 60 seconds until all of these hold:
   - no target has a NodeACL for that IQN;
   - the address is in the `fenced` set (`nft get element`);
   - `ss -Htn state established '( sport = :3260 )' dst <bridge address>` prints nothing.

   If the proof fails, stop here: no taint. Alert `StorageFenceFailed`, and retry on every loop.
5. `targetctl save`.
6. Apply `node.kubernetes.io/out-of-service=nodeshutdown:NoExecute`. Kubernetes then evicts the worker's pods and
   force-detaches its VolumeAttachments, and the pods start on the other worker.

**Settling the bootID.** Each loop first runs the proof for every tagged worker, and only then reads the API.

- If the tag is unsettled and that proof passed, the tag gets the worker's bootID from this read.
- If the tag is settled and that proof failed, the fence fell off: the tag goes back to `unknown`, steps 2–6 cut the
  worker again, and a later loop settles it afresh.
- If the proof could not be run, nothing changes in that loop.
- The first loop after the fencer starts treats every tag as not proven, so a tag is settled again after any
  restart or storage-VM boot.

Why this is enough: after the cut no boot can log in. A boot can only have mounted a retained volume after it posted
its bootID, because the driver has `attachRequired: true` (kubelet stages a volume only after a successful node-status
update, and a new boot's first update stores its bootID), and because `node.startup = manual` leaves logins to
kubelet's NodeStage. So the read after the cut shows the last boot that could hold a mount, or a newer one, and every
older boot is dead.

**It is level-triggered.** Every step is idempotent, and every loop compares the actual state with the tags. A worker
with a `fenced:` tag that does not yet meet the unfence condition gets steps 2–6 again, proof included. A crash, a
storage-VM reboot or an API error at any step is therefore finished on the next loop, and the taint only ever follows a
fresh proof. A hold does not stop steps 2–6 for a worker that is already fenced, since the hold only blocks new fences
(condition 6). A VolumeAttachment from another driver still blocks step 6 (condition 5): the taint would force-detach a
disk the fence proves nothing about. (Ben, 2026-11-16.)

**How it unfences.** Only when all of these hold: the tag is settled; this loop's opening proof passed; the fenced
worker is `Ready` **with a bootID newer than the settled one**: not the one in the tag and not one in `bootids.json`.
The settled bootID was read after the storage was cut, so a newer boot started with no storage access and holds no
stale mounts. Then, under the LIO lock:

1. Remove the taint. If the API call fails, nothing has been reopened and the next loop retries.
2. Restore its ACLs from the rendered worker list.
3. Remove its address from the `fenced` set.
4. `targetctl save`.
5. Remove the tag, last.

If the fencer dies between steps 2 and 5, the next loop sees storage open under a tag. It cannot tell that from a
fence that fell off, so it cuts the worker again and settles on its current bootID. The worker then needs one more
reboot.

A worker that comes back with the settled bootID or one already seen stays fenced until it really reboots. That
covers a network partition, a resumed pause, a restored RAM snapshot, a boot that was `Ready` only between two reads,
and a slow boot that posted its bootID before the fence was settled. **Workers never take, roll back or resume RAM (`vmstate`) snapshots or hibernation
images.**

**Fences survive restarts and reloads.**

- `/etc/nftables.conf` declares the `fenced` set and renders its elements from the `fenced:` tags. The tags are read
  under the LIO lock, but the file is written and reloaded after it, so a rendered element can be stale by the time it
  loads (lab F7). A nftables.service drop-in adds `ExecStartPost` and `ExecReload` steps that run
  `storage-fencer restore-set` (`vgs -o vg_tags` needs no activation), which makes the live set match the tags:
  - it adds every tagged address first;
  - then, only when every tag was read, it removes every element that is not a tagged worker's bridge address;
  - a malformed, conflicting or unknown-node tag, or a missing VG, keeps every element (fail closed).

  No crash point needs an untagged element: a fence tags before it adds the address, and an unfence removes the
  address before the tag. Handlers use `systemctl reload nftables`, never a bare `nft -f`.
- The `rtslib-fb-targetctl.service` drop-in is ordered `After=nftables.service`. A non-fatal `ExecStartPre` runs
  `storage-fencer restore-set` before any target listens. Its `ExecStartPost` first runs
  `storage-fencer restore-set`, because nftables starts too early in boot to read the VG tags reliably. It then deletes
  the NodeACL of every worker named in a `fenced:` tag, runs `targetctl save`, and finally runs the missing-target
  check. A
  configuration saved in the middle of a fence therefore cannot re-admit the worker.
- The reconcile never restores an ACL for a worker named in a `fenced:` tag. It fails if a tagged worker's address is
  missing from the set, and, whenever the tags parse, if the set holds an address with no tag.
- Changing a fenced worker's `bridge_address` makes `restore-set` drop the old address. Established flows could then
  pass the nft rule again, and only the deleted ACLs still block them, so unfence a worker before renumbering it.
- A whole-disk restore carries the live fence tags across (see Backups).

**Visibility.** The fencer logs every step. Through the textfile collector it exports `storage_fence_active{node}`,
`storage_fence_failures_total`, `storage_fencer_last_api_success_timestamp_seconds` and
`storage_fencer_api_errors_total{code}`, with 401/403 counted apart from unreachable, and
`storage_fence_acl_delete_started_timestamp_seconds{node}` (0 when no ACL delete runs). apps alerts on:

- `StorageWorkerFenced`: a fenced worker needs a reboot. One that is `Ready` on its fenced bootID, or on a bootID
  already seen, may be a resumed or rolled-back hung boot: reboot it, and never unfence it by hand (lab F8);
- `StorageFenceFailed`;
- `StorageFenceDraining`: a fence's ACL deletes started over 2 minutes ago, so a backend stall that holds the fence
  (see "A fence waits for the drain") is seen before `StorageFencerBlind`. The textfile collector keeps exporting the
  last file, so a fencer that exits mid-delete leaves the gauge set: Draining plus a fencer that is not running means a
  stale gauge, not a live drain;
- `StorageFencerBlind`: no API success for 10 minutes, a stale textfile, or either series gone for 5 minutes
  (`absent_over_time`, so one failed scrape does not page), so a fencer that silently stops working is
  noticed. If `StorageFenceDraining` is firing, it is the same wait: do not restart the fencer;
- an out-of-service taint present for over 15 minutes, from kube-state-metrics `kube_node_spec_taint`, which does not
  depend on the fencer.

**What the fence does to a worker that is still alive.**

- Its I/O to the targets fails after the initiator's `replacement_timeout`, its ext4 filesystems remount read-only, and
  the taint has already evicted its stateful pods.
- Data it had not flushed is lost, exactly as in a crash. Apps that fsync (Postgres, SQLite) recover from their
  journals.
- It cannot corrupt anything.

**Planned events need nothing.**

- A normal reboot comes back well within 5 minutes. A worker that is fenced and rebooted afterwards is unfenced on its
  own.
- A host cold boot fences nothing: the API's NotReady from before the shutdown predates the watch start. The cost is
  that after a storage-VM reboot, a fencer restart or an API outage, a worker that is really hung is fenced up to
  5 minutes later than its NotReady age alone would allow.
- A worker whose new boot reached the API before the fence was settled stays fenced and needs one more reboot. That
  is a boot whose kubelet posted its bootID but stayed NotReady 5 minutes on, or a reset that lands within about a
  minute of the fence. The fencer cannot tell such a boot from one that mounted volumes before the cut.
- A slow boot that has not posted its bootID when the fence settles needs nothing: the tag settles on the old bootID,
  and the new boot is unfenced on its own when it turns `Ready` (lab B6 Step 8). It cannot have mounted, see "Why
  this is enough".
- The same one extra reboot applies if the fencer restarts, or an unfence is interrupted, while the worker is fenced
  and already on its new boot.
- Graceful shutdown (the kubelet drop-in plus the node plugin's shutdown patch and preStop) unstages and releases the volumes
  before the fence would fire. kubelet waits only for pod unmounts, not for NodeUnstage (kubernetes#125070), and the
  chart's node pod ended the unstage early: its `cleanup` container's preStop deleted the driver socket, its sidecars
  stopped at once, and `driver-registrar`'s private copy of `/var/lib/kubelet` kept the filesystem alive past the
  unmount, so the iSCSI logout landed under a live ext4 (lab Check 11, F14, F21). The node DaemonSet patch:
  - drops `cleanup` (its shell also ignored SIGTERM, which held every worker poweroff about 90 s, F15);
  - runs `csi-proxy` and `driver-registrar` as native sidecars, so they outlive `csi-driver`;
  - drops `driver-registrar`'s `kubelet-dir` mount (v2.9.0 never reads it).
  In the chart values, `csi-driver` gets a preStop that holds while a node-manual `globalmount` directory or an iSCSI
  session to the storage VM exists (at most 20 s), then 12 s so the node status publishes an empty `volumesInUse`.
  A worker with nothing staged still stops at once. The fence stays the backstop for hangs and power loss.
- Node retirement (`roles/k3s_node_retirement`) deletes the stale Node after the new VM exists; it does not drain or
  cordon. A rebuild in normal mode hard-stops each worker, so its staged retained volumes see a crash and an MMP wait
  (Harder or new, "Rebuilds hard-stop workers"). Its enabling variables move out of `group_vars/all/proxmox_csi.yml`
  before that file is deleted.

**Manual fallback.** If the fencer is down or refuses (for example with both workers NotReady), every manual fence still
goes through the tag, so the normal unfence clears it later:

1. Run `storage-fencer fence <node>` on the storage VM. It performs steps 1–5 and prints the proof.
   - It needs no API access and takes no bootID: the tag is `unknown`. A running fencer settles it on its next loop,
     and the normal unfence then applies.
   - While the fencer stays down the tag stays `unknown`.
   - Every manual unfence, of an `unknown` or a settled tag, is `storage-fencer unfence <node> --confirm-stopped`, run
     only after `qm status <vmid> --verbose` showed the VM `stopped` (lab F8). A bare `unfence` exits 1 and changes
     nothing. A paused VM shows `running` with `qmpstatus: paused`, and a paused VM is not off. While the fencer
     runs, a worker that rebooted needs no manual unfence: the loop does it.
   - `storage-fencer unfence` removes the taint first, so it needs the API. With the API down it fails with nothing
     changed.
   - On a stalled backend the command waits, unkillable, until the disk answers (see "A fence waits for the drain").
     It never sets the drain gauge, so `StorageFenceDraining` does not fire; a running loop shows the wait as lock
     failures (`StorageFenceFailed`).
2. Apply the taint by hand, and only after step 1 has printed a passing proof: a taint before that lets a new writer
   mount while the old worker's queued writes can still land. Until Retirement the worker may also hold Proxmox CSI
   volumes: the taint force-detaches those too, and the storage fence proves nothing about them (the fencer refuses
   this case, condition 5). Until Retirement only (Ben, 2026-11-21: accepted for the migration): if the worker has a
   VolumeAttachment whose attacher is not `org.democratic-csi.node-manual`, run `qm stop <vmid>` and taint only after
   `qm status <vmid> --verbose` shows `stopped` (not `running`, and not `qmpstatus: paused`). If the stop fails, do
   not taint; the host reboot is the last resort. A hard stop of a worker that is still alive loses its unfsynced
   writes, as in a crash.

**Unchanged parts of the exclusion.**

- `disable-force-detach-on-timeout=true` stays on, so nothing moves on a timer.
- The indefinite not-ready/unreachable tolerations stay. The out-of-service taint still evicts those pods, because
  they do not tolerate that key.

**ext4 MMP is a detector, not a fence.**

- It refuses a second mount only while the first mounter's kernel is running and still updating the MMP block.
- It does not stop a mount over a paused or hung mounter. After that mounter resumes, it may not notice. The storage
  fence covers that case: a resumed worker finds its sessions gone.
- `errors=remount-ro` makes a detected double mount stop writes instead of continuing.

**LVM isolation (lab F11, F12; design `superpowers/specs/2026-11-18-storage-vm-lvm-isolation-design.md`).**

- Every LVM command the reconcile and the fencer run names one VG and opens only that VG's PV
  (`--devices <pv>`, from `storage_vm_pv_devices`: the terraform slot's `/dev/disk/by-path` link). `--devices` also
  turns LVM hints off for that command, so a stale `/run/lvm/hints` (F12) never hides a VG from our code.
- Each command has a time limit: 30 s per VG read (`vgs` and `lvs` share it) and per write. A command past it is left
  running, never killed, because a killed `lvextend` can leave its LV suspended. It runs in its own session, so an
  Ansible task's hangup at exit never reaches it, and the two units use `KillMode=process`. Until that command ends,
  later commands for the same VG in that process fail at once. A VG that does not answer reads as missing: the reconcile
  then refuses that VG's entries, and entries whose cross-VG `id` check needs it, not the whole apply (Reconcile table;
  a VG already missing at the dry run fails the run before the lock, D42).
- The fencer and `restore-set` read the retained VG's tags only (`vgs` on retained), so a regen fault never reaches
  them. A retained read that fails is a failed loop, never empty fence tags.
- `LIO_LOCK` waits at most 120 s; a fencer loop that cannot get it counts a failure and writes its metrics.
- Hand-typed commands still use hints: use `vgs --devices <pv> --readonly <vg>`, and run `pvscan --cache` only when no
  disk is stalled.
- **Named residuals** (each needs regen to answer at plan time and then stall in the middle of the work, or retained
  itself to stall):
  - a regen create: `dd`, `blkid`, `mkfs`, `mount`, `umount` and the in-process marker `fsync`;
  - expire's `blkdiscard`, which has no limit on purpose: one that was given up on would keep the LV open `O_EXCL` and
    leave the volume half-expired;
  - in-process rtslib and configfs work other than the fence's ACL delete (a rule, below), and `lio.save`'s `fsync`;
  - `nft`, `ss` and `systemctl is-active`;
  - `targetctl restore` on a regen that activated and then stalled;
  - the boot activation of retained.

  While one of these holds `LIO_LOCK`, other lock users give up after 120 s instead of hanging.
- **A fence waits for the drain (lab finding F23, kept by design 2026-11-18).** An ACL delete returns only after LIO
  has finished the worker's outstanding commands, and on a stalled backend those finish only when the disk answers.
  That wait is what makes the fence safe: nothing is tainted until it ends, so no new writer can mount while the old
  worker's queued writes can still land (the nft cut stops new packets only). The wait cannot be killed (the fencer
  sits in D state); other `LIO_LOCK` users give up after 120 s and fail closed; for the fencer loop's fences
  `StorageFenceDraining` fires after 2 minutes (a manual fence does not set the gauge: see Manual fallback). The storage VM's shutdown and manual `targetcli` commands on that target also wait. The fence deletes
  retained ACLs first, so retained sessions are torn down before a regen drain; this is best effort (when both disks
  stall, the retained delete can be the one that waits) and gains no failover time, because the proof cannot pass
  before the drain and the taint is per node. `one-at-a-time` already forbids a second fence during the wait. The
  reconcile's `ensure_target` is a second drain site, with no gauge: there the fencer loop's lock timeouts raise
  `StorageFenceFailed`.

### Backups

- The `retained` disk is one `.raw` file in `apps/k3s-block`. TrueNAS replication to `usbbk/tn` and the restic job keep
  working, and one ZFS snapshot is crash-consistent across every retained volume.
- The `regen` disk is excluded from restic by one path. It is added **next to** the five `vm-9999-*.raw` excludes,
  which go at Retirement, and `test_excludes_cover_regenerable_images` gains it.
- A dump rule alarms on a missing or stale `retained` image. It is added at the first `retained` cutover (karakeep-data,
  in the wave-1 karakeep outage, D14), not before, because the
  rule checks mtime.
- **Whole-disk restore.** It is a manual runbook, `docs/runbooks/storage-vm-restore.md`:
  1. Take the lock and set the deny syncWindow. Scale every retained writer to 0 and confirm each unstage, as for a
     rebuild (Disposable): the restore cuts I/O far longer than `replacement_timeout`. Record the live fence tags
     (`vgs --devices <retained PV> --readonly --noheadings -o vg_tags retained`, every `fenced:*` entry) and every node
     that carries the out-of-service taint, and whether the live VG already carries `hold_fence`, then tag it
     `hold_fence`.
  2. Shut down the storage VM and put the restored `.raw` in place:
     - keep the current file as a rollback copy until the restore is verified, which needs dataset room;
     - copy byte for byte and compare sha256, as in ansible `docs/backup-and-restore.md`, **One image from the
       replica**, step 3.
  3. **Before booting**, set the hold from the Proxmox host without activating the VG:
     1. `dev=$(losetup --find --show <image>)`
     2. `vgchange --config 'activation{auto_activation_volume_list=[]}' --addtag hold_create --addtag hold_fence retained`,
        adding each recorded `fenced:<node>:<bootID>` tag and deleting (`--deltag`) any `fenced:*` tag in the image
        that was not recorded
     3. `vgchange -an retained`
     4. `losetup -d $dev`
     5. Confirm `losetup -j <image>` is empty and `dmsetup ls` shows no `retained-*` entries.

     Repeat steps 3–5 for `regen` if that disk was restored too. The holds in step 3 always go on `retained`, even for a
     regen-only restore: the reconcile and the fencer read holds from `retained` only. (Ben, 2026-11-16.)
  4. Boot the storage VM.
  5. From the runner, run the storage playbook by hand, under the runbook's own lock owner and nonce, not by dispatch.
     Resolve every missing volume from an older backup. Abort if any worker carries the out-of-service taint without a
     matching `fenced:` tag. Targets for volumes created after the snapshot come back empty: the LIO configuration is
     on the root disk, which the restore does not roll back, and `targetctl` skips the missing backstore. The reconcile
     neither flags nor removes them (lab F17), so list them here and remove them by hand.
  6. Clear `hold_create`. Put `hold_fence` back to the state recorded in step 1: while automatic fencing is held (Ben,
     2026-11-21), it stays set. Then release the lock, remove the syncWindow, and scale the writers back up.

  The hold is the only protection against a disk restored to an older snapshot recreating later volumes empty. Ben chose
  this over a Git field or an automatic ledger mirror.
- **Single-app restore.** Hold `/run/lock/homelab-backup.lock` throughout. Clone into `usbbk/restore-<date>`, never under
  `usbbk/tn`, and destroy the clone before the next :30 replication.
  1. `zfs load-key` if needed.
  2. `zfs clone` the `usbbk` snapshot.
  3. `losetup` the clone's `.raw` read-write.
  4. `vgimportclone -n restore_<date>`, then `vgchange -ay`.
  5. Mount the LV `ro`, so the journal replays on the writable clone.
  6. Copy the files, each SQLite database with its `-wal` file (in the lab the WAL held committed rows), then unwind
     and `zfs destroy` the clone.

  Off-site, `restic restore --sparse --include <image>` into `/usbbk/restore`, after a free-space check, then steps 3-6
  on the restored file.

### Capacity

| Measurement | Value |
|---|---|
| Declared live sizes | 155 GiB retained, 37 GiB regenerable |
| Proposed thin virtual disk sizes | `retained` 256 GiB, `regen` 64 GiB |
| `k3s-block` mount, live 2026-11-08 | 219 GiB total, 143 GiB available, 77 GiB used |
| Documented quota | 288 GiB, confirmed (TrueNAS `apps/k3s-block` quota 309 GB, lab read 2026-11-16). The mount's 219 GiB total does not match it; resolve before the foundation phase |

- **Per-cutover gate.** Before each copy, `zfs get available,usedbysnapshots apps/k3s-block` must show `available` of
  at least the source's full length plus 10 GiB, and `usbbk` must have matching space. The copy writes the full length
  (no `conv=sparse`), so each LV may allocate all of it unless zero blocks end up as holes. `apps/k3s-block` has lz4
  compression (read 2026-11-23), and ZFS stores all-zero records of a compressed dataset as holes, so they should; not
  yet measured. The gate stays at the full length until the dataset's measured `used` change over the first cutover
  (tempo) shows that zeros become holes (Ben, D20). A change well below tempo's full length then moves the gate to the
  source's allocated size plus 10 GiB for every later copy (Ben pre-approved, 2026-11-23).
- **Thin overcommit.** The proposed disks (320 GiB virtual) exceed the 288 GiB quota, and the plain LVs keep showing
  free space while the files under them cannot grow. If the dataset fills, new-block writes fail on every volume in
  both VGs at once (and on any Proxmox CSI image on the dataset). What the guest sees depends on the error, and no
  `werror` policy is set for the data disks: a quota hit (EDQUOT) is most likely reported to the guest as I/O errors,
  which turn every mounted volume read-only; only a full pool (ENOSPC) pauses the storage VM under QEMU's default,
  fencer included. Neither is tested. The dataset free-space alert below is the only warning.
- **Two copies.** Old images stay as rollback sources until Ben approves each deletion. Deleting the 10 retired rollback
  images (36 GiB declared) first, with his approval, eases the two-copy peak.
  - Space comes back only after snapshots expire: 1 week on TrueNAS and 2 weeks on `usbbk`. So delete them at least a
    week before the cutovers they make room for.
- **Oversized volumes.** apps CI refuses an inventory whose sizes in one VG add up to more than that VG's usable size.
  The reconcile also checks the VG's free space before it writes the ledger `creating` tag, so a new volume that does
  not fit is refused cleanly, with no `creating` tag, so nothing is left to recover on the VG (no `crashed-create`).
  `no-space` is a dry-run refusal, so the run fails before the lock is taken and the next run retries on its own
  (migration plan D40). A volume that stops fitting between the dry run and the apply fails the apply and keeps the
  lock until a person releases it (D31).
- **Snapshot reserve.** apps CI (`scripts/check-retained-inventory.py`) also refuses an inventory whose sizes in one VG
  leave less than a reserve free in that VG. The reserve is the largest entry's size in that VG, but at least 10% of
  the VG's usable size (Ben, 2026-11-22). Why: one LVM snapshot of the largest volume must fit, for the deferred
  storage-VM backup path (Consequences, Deferred). The reconcile's `no-space` check is unchanged: it guards only a
  single create or extend against the VG's actual free space.
- **Alerts** on VG free space and on dataset free space.
- **Growing a data disk:** `qm resize <storage-vm> virtio1|virtio2 +NG` (virtio-blk picks up the new size by itself), then
  `pvresize`, then a terraform PR that raises the disk's `size` to match. The `storage/` root uses the bpg provider,
  which attaches another VMID's disk with `path_in_datastore` and never moves or resizes a disk it does not own; telmate
  cannot attach an existing volid without a permanent diff (source reading). Lab check 3 confirms the bpg behaviour
  after the F10 fix; a fresh clone with `virtio0` declared is traced in source only.

## Rationale

Every option was scored against the five requirements. Each vendor claim was checked against upstream source by an
adversarial verifier.

**Chosen: storage VM + LIO + democratic-csi node-manual.**

| Requirement | How it is met |
|---|---|
| Slots | Two slots in total, both on the storage VM. The workers use none, because guest iSCSI has no per-VM disk budget. |
| NAS-agnostic | Met for the live data path, which needs only an NFS export, the one the NAS serves today. The backup half is deferred (Ben, 2026-11-22): retained backups and the local ZFS-clone restore stay on the ZFS path for now, TrueNAS snapshots replicated into `usbbk/tn` with restic reading the replica. That is plain OpenZFS, not a TrueNAS-only feature, so another ZFS NAS keeps it once those jobs are rebuilt. A NAS without ZFS keeps the live data, and the restic snapshots already off-site restore without ZFS, but new backups and the ZFS-clone restore stop. So a storage-VM backup path, built, run alongside the ZFS path and restore-drilled, is a hard precondition of decommissioning TrueNAS (Consequences, Deferred); the per-VG snapshot reserve (Capacity) keeps that path possible. |
| Rebuild | Reconnects from Git alone: the PV identity (portal, target IQN, LUN 0) and the worker IQNs come from Git, and the data disks survive VM rebuilds. |
| Fail closed | A missing LV gives a target with no LUN 0, which the boot check fails and nothing can mount; the ledger, the tombstones and the hold refuse lost volumes; `blkid` detection and the guards stop blank or wrong ones. |
| Stock software | Distribution packages and an upstream driver in a documented mode. The lifecycle engine (reconcile, ledger, holds, expiry), `storage-fencer` and the node DaemonSet patch are still local code; Ben accepted them as an exception to requirement 5 (2026-11-21). On 2026-11-22 Ben widened the exception into a rule: it also covers small local glue, with tests, that never writes retained data. It covers permanently the `csi-driver` preStop hold script in the chart values, the generic startup guard `guard.py` (read-only, apps#1707, D47) and the one-flag guard layer (read-only to data) and their CI check; and, separately, by name rather than by the rule (it writes retained data), temporarily the migration copy tool (`migrate_volume.py`, `copy_volume.sh`), whose cover expires when migration plan Task 5.9 deletes it at Retirement, once the last reverse-copy window has closed (Migration 4). Future local pieces are judged against that rule. None is a fork, a patched image or an adoption controller. |
| SQLite | Stays on ext4 on a block device. |
| Backups | Same replication path and off-site scope as today, so backups still need a ZFS NAS until the deferred storage-VM backup path replaces it (NAS-agnostic row; Consequences, Deferred); restore granularity becomes the whole image. |
| Future NAS | It is the natural first piece of a later all-in-one Debian NAS: a VG can `pvmove` onto new disks online. |

**Rejected:**

| Option | Disqualifier |
|---|---|
| Keep Proxmox CSI (shrink to 26 volumes or fewer, template the ceremony, or add a third worker) | Ben rejected keeping a slot budget. |
| Official TrueNAS CSI v1.4.0, democratic-csi `freenas-*`, tns-csi v0.22.0 | TrueNAS-specific. Dynamic volumes are named after the PVC UID. TrueNAS CSI's unpublish is a no-op and its static publish does not check ownership. tns-csi calls itself not production-ready. |
| democratic-csi `zfs-generic-*` | Identity is `pvc-<UID>`; stable names need an unsupported private template; missing datasets are re-created. |
| Any NFS-backed provisioner (nfs-pv, csi-driver-nfs, nfs-subdir) | Creates a missing directory, so a lost volume starts empty. SQLite would sit on a network filesystem, and Servarr and the Home Assistant recorder hard-code WAL. |
| Ceph in a VM with ceph-csi static RBD | The strongest fail-closed behaviour and a built-in storage-side fence (NetworkFence). But it needs about 9 GiB RAM against 9.4 GiB available on the host (2026-11-08), a size=1 pool that Ceph warns about permanently, and ongoing Ceph upkeep. |
| One data disk per worker with static `local` PVs | No failover between workers, and no RWOP. |
| iSCSI from the Proxmox host over today's `.raw` files (tgt) | Boot-ordering logic on the hypervisor, and Debian's tgt is 1.0.85 from 2023. LIO's file backstore opens files with `O_CREAT` and would create empty ones under an unmounted NFS path. |
| Longhorn, Rook-Ceph, LINSTOR/Piraeus, Mayastor | Volume identity lives in in-cluster resources, so a rebuild means a restore. |
| JuiceFS, SeaweedFS, Litestream, LiteFS | Network filesystems, or replication with a loss window. No old-writer exclusion. |
| virtiofs, NBD | SQLite on NFS one layer down, or no released driver. |
| In-tree Kubernetes `iscsi` volume | No RWOP (RWO/ROX only), so two pods on one node could mount a volume. Its attach is a no-op, but the attach-detach controller still tracks it, so `disable-force-detach-on-timeout` still protects it. Kept as the fallback if democratic-csi stalls: same targets, a PV rewrite, no data copy. |
| medik8s Self Node Remediation with the Proxmox `i6300esb` watchdog | Timing-based: after its safe time it assumes the node rebooted and applies the taint. A paused VM's virtual watchdog stops with it, so that assumption fails open. OLM-only. |
| A fencer Deployment in the cluster, calling the storage VM over SSH | An SSH key with root effect on the storage VM would sit in the cluster as a sealed secret, and the fencer would share the fate of the nodes it judges. |
| medik8s Fence Agents Remediation with `fence_pve` | The upstream image does not ship `fence_pve` (CentOS Stream 9 skips it), so it would need a derived image, and the Proxmox password would sit in agent argv. |

## Consequences

**Easier**

- No slot budget, and no slot alerts.
- A new stateful app is one inventory entry plus `retained: <id>` in its `app.yaml`, in one PR (plus a mount list if
  its data is not at `/config`). Its storage appears on merge.
- Automatic fencing ships held: `hold_fence` stays on `retained` after Retirement, and turning it on is a later
  decision (Ben, 2026-11-21). Until then, a lost or hung worker's retained apps wait for the manual fence (Hang policy)
  or for the worker to come back. Once it is on, losing or hanging a worker no longer strands volumes. About 6 minutes
  after it hangs (about 5 minutes after it goes NotReady), the storage VM cuts it off, and its stateful apps run on the
  other worker about 7 minutes after the hang, with no one at the keyboard. Extrapolated from lab runs at a 60 s
  threshold, plus 240 s for the 300 s one: fences 106-112 s and writers back 2 min 48 s to 3 min 5 s after the hang.
- The storage VM can later grow into the NAS.

**Harder or new**

- **Late NFS at cold boot needs a hand start.** A storage VM still stopped after a cold boot with the NFS late is not
  retried: `StorageVMDown` fires and every retained app waits for a manual `qm start` (migration plan D9, Ben
  2026-11-22).
- **A missing `regen` VG stops retained changes.** The dry run fails on any missing VG (migration plan D42, accepted by
  Ben 2026-11-22), so a `regen` disk that is out at dry-run time pauses retained creates and grows until it returns.
  A lost regen disk returns from the replica (`storage-vm-restore.md` "Whole-disk restore", regen only); a blank
  re-creation with no replica copy has no runbook yet and needs Ben (the bootstrap runbook refuses a VM that has
  LVs). Live retained targets keep serving.
- **Critical path.** The storage VM and the new bridge sit on the path of every retained volume. Every retained volume
  still also depends on the NAS, as today.
- **Double copy-on-write.** I/O goes through ext4, the LV, a raw file on NFS and then ZFS. In the lab the extra hop
  cost nothing measurable (Check 9): fio 4k writes with fsync ran at 158 IOPS, p50/p99 6/12 ms, on both paths, and
  SQLite commits at 83/s against Proxmox CSI's 78/s. The NFS backend's fsync sets the floor.
- **Driver maintenance.** democratic-csi has effectively one maintainer, and v1.9.5 came 18 months after v1.9.4. The
  fallback is the in-tree `iscsi` volume.
- **Coarser restores.** Restoring one app means cloning and mounting the whole image. An off-site restore of one app
  downloads the whole image, about 80 GiB in use today.
- **Fencer code.** `storage-fencer` is new local code that can taint any node it patches, though it only targets the
  configured workers. A bug in its proof step is the one path back to two writers. MMP stays on, but it is a partial
  backstop: it refuses a second mount only while the first mounter is still running, and does not catch a paused or
  hung mounter that resumes, which is the case a proof bug would expose.
- **False fences.** A worker that was alive but unreachable for 5 minutes loses its storage until it is rebooted. Its
  stateful apps restart on the other worker meanwhile, and writes they had not fsynced are lost.
- **Both workers down.** The fencer refuses when no worker is Ready, so that case still needs the manual fence.
- **Boot waits on both disks.** A storage VM that boots while either data disk's backend is stalled serves nothing,
  `retained` included, until the stall ends (accepted, see Restoring the configuration at boot).
- **Silent storage-VM failure.** If the storage VM fails to start, Prometheus and Alertmanager (on the `regen` disk) go
  down with it, so in-cluster alerting goes dark.
  - Alertmanager's Watchdog is routed to a healthchecks.io dead-man check (live since 2026-11-11). An outage that takes
    Alertmanager down alerts within about 10 minutes.
- **Marker guards.** Guards no longer check native layout (Ben, 2026-11-22). After a disk restore without the
  `hold_create` step, an `origin: new` volume could be recreated empty with a fresh marker and still pass its guard. A
  recreated `origin: migrated` volume holds no marker and is refused. A copy that carried the marker but lost app files
  also passes: no guard checks content (D47).
- **Rebuilds hard-stop workers.** Node retirement does not drain. A terraform PR that replaces k3s VMs, applied in
  normal mode, hard-stops each worker with its retained volumes staged: apps see a crash, writes they had not fsynced
  are lost, and the volumes restage after an MMP wait. So after Retirement such a PR must run in drain mode while
  retained volumes are staged, enforced in terraform (migration plan D41, Ben 2026-11-22; Task 5.11). Migration plan
  Task 3.10 (V1) still measures and records the crash cost.
- **Shared guard layer.** One edit to `templates/retained-guard.yaml` restarts every flagged app (after Task 5.12,
  every app on a rendered guard) in one sync: RollingSync's `services` step has no `maxUpdate`, and Reloader reloads on
  ConfigMap changes. One edit to `guard.py` changes `retained-startup-guard` in every guard namespace and restarts
  every guarded workload outside `monitoring` (Reloader ignores it), shared Postgres and Redis included. Such edits are
  scheduled like a maintenance window.
- **Automatic deletion.** An LV is deleted 3 days after its entry leaves the inventory. Unlike removing an `nfs-pv`
  PVC, which leaves the data, removing an entry deletes it; the only undo is a revert within those 3 days.
- **Backups need a ZFS NAS, for now.** The live data path needs only an NFS export, but retained backups and the local
  ZFS-clone restore rely on ZFS snapshots replicated from the NAS into `usbbk/tn`. Ben deferred the backup half of
  requirement 2 (2026-11-22): TrueNAS is not decommissioned until the storage-VM backup path is in place (Deferred).
  Until then, a NAS without ZFS would keep the restic snapshots already off-site restorable, but stop new backups and
  the ZFS-clone restore.

**Deferred**

- **NAS-agnostic backups** (requirement 2, backup half; Ben, 2026-11-22). Retained backups stay on the ZFS path for
  now: TrueNAS snapshots replicated to `usbbk/tn`, restic reading the replica. The replacement is a storage-VM backup
  path: an LVM snapshot of each retained LV inside the storage VM, then restic from the storage VM to the off-site
  repo. It is a hard precondition of decommissioning TrueNAS: it is built, runs alongside the ZFS path for a while,
  and a restore from it is drilled; only then does the ZFS path go. Restores from existing off-site restic snapshots
  do not need ZFS; only taking new backups and the local ZFS-clone restore do. It is not built in the migration plan;
  the per-VG snapshot reserve (Capacity) keeps it possible.

**Open questions**

- Whether Argo CD 3.6.2 passes `retained.id` to Helm through `helm.parameters` written by the ApplicationSet's
  `templatePatch`. The fallback is the id in `values.yaml` plus a `commonValuesExtras` line.
- Whether kubelet applies `fsGroup` to a ReadWriteOncePod ext4 volume. The layer relies on it twice: a non-root app
  writes its fresh volume through it, and the guard's fixed uid reads the marker through it (every services app gets
  `fsGroup` from `templates/common.yaml`). Task 3.9 of the migration plan proves it.
- The 219 GiB the `k3s-block` mount shows against the confirmed 288 GiB quota.
- Whether the `ORG_DISPATCH_TOKEN` org secret is visible to apps.
- The data disks' final sizes.
- How a failed boot check alerts (lab F2).
- Whether to bound NodeStage's 30 min login retry (lab F1).
- When a filesystem left with the ext4 error flag gets an offline `e2fsck` (lab F9).
- `lvremove` and the tombstone are separate commands, so a failure between them leaves `lv-missing`, which fails every
  run until fixed by hand (`lv-missing` is in `BLOCKING`, reconcile.py:27, so the dry run stops every apply, other
  entries included); since a failed run keeps the lock (D31), it then stops later runs (lab B5): whether to close
  that gap.
- Whether the fencer exports a `storage_fencer_refusing{node,reason}` gauge, so a long `hold`, `foreign-va` or
  `no-peer` refusal reaches Prometheus (lab B6 Step 9).
- A live check or alert that kube-controller-manager runs with `disable-force-detach-on-timeout=true`.
- Whether one worker can carry all 33 retained volumes at once (sessions, mounts, and unstage within the 40 s shutdown
  budget). The lab ran 3 (Qualification, scale); migration plan Task 5.8 checks it after Retirement, and Task 5.10 boots
  the host with every retained volume staged.
- The data disks' `werror` policy and the overcommit against the quota (Capacity).

**Qualification in a disposable lab (gate for any production change)**

Ran 2026-11-16 to 2026-11-19 and torn down; results and findings in
`superpowers/reports/2026-11-16-retained-storage-lab-results.md`. Not proven there (a selection; the full list is the
report's Limits), with where each closes:

- the whole boot sequence on the final code (Check 1 below): Foundation gate F2;
- a storage VM rebuild on a fresh clone with `virtio0` declared (Check 3): Foundation gate F1;
- the migration copy Job, and democratic-csi beside a live Proxmox CSI on the same workers: the first cutover
  (tempo, regenerable, old image kept);
- scale: 3 volumes against about 33, one fio and one SQLite stream, no concurrent load: watched as cutovers add
  volumes, then migration plan Task 5.8 (one worker) and Task 5.10 (planned host reboot with every retained volume
  staged, including the `retained` LUN-0 restore and `storage_boot_check_ok` with real LVs);
- the single-app restore from a ZFS clone and the off-site `restic restore` (Check 10): cutover gate C1;
- the production timings: the fencer ran at a 60 s threshold, not 300 s, and Check 11 was not re-run at 300 s: Check 11
  at the first planned worker reboot after Retirement; the fence at 300 s waits for Gate R1, which comes with the later
  decision to turn automatic fencing on;
- **accepted untested** (Ben, 2026-11-21):
  - a stall of the `retained` disk or of the whole backend. Every lab stall hit `regen`, on its own storage. In
    production it can only be staged by stalling pve's NFS, which freezes Proxmox CSI and every VM as it does today.
    The design fails closed there: a retained read that fails is a failed fencer loop, never empty fence tags (LVM
    isolation);
  - real hangs: every hang was simulated (`qm suspend`, `SIGSTOP`, an in-guest freeze, `link_down`);
  - the cold-boot fence rule (F18) on a real host boot with fencing on: lab-tested only through guest cycles, and F2
    runs with `hold_fence` set; first seen at the first host reboot after automatic fencing is turned on (a later
    decision);
  - smaller paths, argued from source or code reading: F6's mount wait over 120 s
    (kubelet's Uncertain path) and F7 route 2. `StorageFencerBlind`'s absent legs left this list: they are
    `absent_over_time(...[5m])`, and promtool cases in apps CI show one failed scrape stays quiet and a sustained
    absence fires.

A throwaway storage VM plus a two-node k3s cluster (a server that also runs workloads, and one agent), all deleted
afterwards. The fencer treats both nodes as workers and only the agent is ever fenced; fencing a server is outside the
lab. Every check had to pass. Status 2026-11-19: Check 10 is partial, Check 1 passed on code from before its fixes, and
Check 3 passed with the rebuild on a fresh clone with `virtio0` declared traced in source only (noted below); the rest
passed. **Decided (Ben, 2026-11-21): no second lab.** Checks 1, 3 and 10 and most unproven items close in production as
gates in Migration (F1 and F2 before the first cutover, C1 before the Servarr apps; R1 waits for the later
automatic-fencing decision); the rest are accepted untested (below).

1. **Boot.** A cold host boot in the production order of Boot order: TrueNAS is ordered first, but its NFS is the last
   thing to come up (Ben, 2026-11-17). Also a reboot of only the storage VM. Every target returns with no manual step, and `rtslib-fb-targetctl.service` is
   active before the first hourly reconcile. The reconcile now enforces part of this: it refuses while that unit is
   not settled (still running, queued, or unreadable), though a failed unit or boot check does not refuse (How a run
   works). On a host shutdown, the workers stop before the storage VM. Passed on the 2026-11-17 host reboot, which ran code from before the F18,
   F11/F12, F14 and F24 fixes; each fix passed only through guest cycles, and Ben closed the check without a re-run
   (2026-11-19). The whole boot sequence on the final code first runs at Foundation gate F2 (Migration).
2. **Full k3s rebuild from Git.** Every PV reattaches. A rebuilt worker keeps its IQN.
3. **Storage VM rebuild.** Both data disks survive and every target is re-exported. This check also confirms the bpg
   attach, and confirms that a manual disk change shows up in `terraform plan`. With the clone source missing, the apply
   fails before the destroy.
4. **Missing and blank devices.**
   - A missing LV: the pod never starts and nothing is formatted.
   - A blank LV: blocked by the guard.
   - A missing VG: the reconcile refuses.
   - A populated LV with udev data hidden: no mkfs runs.
5. **Ledger and deletion.**
   - A new entry is created; a lost one is refused.
   - An orphan LV and a crash mid-create are both refused.
   - A tombstoned `id` is refused.
   - An old SHA is a no-op.
   - A removal while the pod runs keeps the target.
   - Re-adding an entry on day 2 clears `pending-delete`.
   - A still-attached temporary copy pair blocks deletion.
   - A live explicit-ACL session (an `iscsiadm` login with no Pod and no VolumeAttachment) blocks deletion.
   - A `class` change is rejected by CI.
   - The expiry job deletes only after 3 days with no Pod and no VolumeAttachment.
   - `hold_create` blocks every create.
6. **Hangs and fencing.**
   - With the fencer stopped and a paused worker (`qm suspend`), its volumes never move.
   - With the fencer running, three cases: a paused worker; a hung worker (a `SIGSTOP`ped QEMU or a kernel freeze, not
     `echo c`, which is a crash); and a worker whose `net0` (the vmbr0 NIC that kubelet reaches the API through) is set
     `link_down=1` while its bridge NIC works. In each, the proof
     holds (no ACL, the address in the set, no established socket), the taint follows, and the volumes move within about
     7 minutes of the hang (lab, at a 60 s threshold: fences 106-112 s after the hang, writers back 2 min 48 s to
     3 min 5 s; see Consequences).
   - Resume the paused worker: it gets I/O errors and remounts read-only, MMP is recorded, and `e2fsck -fn` on the
     target finds nothing.
   - LIO removes a NodeACL with commands in flight without hanging, and in-flight writes finish before the session is
     gone. The proof reports a session while one is still open.
   - Kill the fencer after each fence and unfence step, and reboot the storage VM between fence steps 3 and 5. Each fence
     converges to a finished fence. An unfence killed before its last step ends fenced again on the current bootID (the
     restart un-settles the tag) and is unfenced after one more reboot.
   - Reload and restart nftables, run a reconcile that changes the nftables template, and reboot the storage VM during a
     fence: the drop and the missing ACLs stay. A restart leaves no ruleset for up to about 0.16 s (accepted, lab
     B6 Step 7); the missing ACLs hold throughout.
   - A rebooted fenced worker is unfenced only with a new bootID. One resumed with the same bootID, or rolled back to a
     `vmstate` snapshot taken before the fence, stays fenced.
   - A worker that hangs, is fenced, and is rebooted after the tag is settled is unfenced with no manual step.
   - A slow reboot, held before kubelet starts past 5 minutes after boot, is fenced, its tag settles on the old bootID,
     and it is unfenced on its own when it turns `Ready` (lab B6 Step 8). A settle on the new bootID is the next case.
   - With the fencer stopped for one loop, a worker reboots, turns `Ready`, mounts a retained volume and is then held
     NotReady past 5 minutes: it is fenced, and it stays fenced when it turns `Ready` again on the same boot.
   - Restart the fencer while a worker is fenced: the tag goes to `unknown` and settles again on the next loop.
   - The fencer does nothing when both workers are NotReady, when the API is unreachable, when the token is deleted or
     rotated (`StorageFencerBlind` fires), when `hold_fence` is set (a fence already started still finishes), or when the worker holds a non-democratic-csi
     VolumeAttachment.
   - A manual fence with the fencer stopped stays `unknown` and is not unfenced when the worker resumes. With the fencer
     running, the tag is settled on the next loop.
7. **Online growth.** Including an interrupted run and its retry.
8. **NFS stall and export withdrawal.** I/O errors and a manual restage, never silent corruption. The restage is a
   scale to 0, a confirmed unstage, then a scale up: a same-node pod delete reuses the read-only global mount (lab
   F13).
9. **Crash and latency.** `kill -9` mid-write, then SQLite `integrity_check`. fio and SQLite fsync latency compared with
   Proxmox CSI.
10. **Restore drills.** One app restored locally from a ZFS clone, and one off-site with `restic restore`. A whole-disk
    restore taken while a worker is fenced keeps that worker fenced. Partial (report B9): the whole-disk restore while
    fenced passed, and the single-app restore passed from a `cp --sparse=always` copy, not a ZFS clone. The ZFS-clone
    and off-site `restic restore` legs did not run; they close at cutover gate C1 (Migration).
11. **Graceful shutdown.** kubelet writes `/etc/systemd/logind.conf.d/99-kubelet.conf`, the node's `/configz` shows
    `shutdownGracePeriod` `1m30s` and `shutdownGracePeriodCriticalPods` `40s`, apps stop before iSCSI logs out, ext4 unmounts before each disk is removed, and an
    undrained shutdown releases its VolumeAttachments with no fence, also after a node-plugin restart while staged.
    Passed 2026-11-18 (report, Check 11 re-test).
12. **Network, metrics and reclaim.**
    - Port 3260 is refused from the LAN and from the workers' LAN addresses.
    - SSH from the runner still works with nftables loaded.
    - The `pending_delete` metric appears after an entry is removed.
    - Unstaging one volume leaves the other volumes on that worker doing I/O.
    - A deleted LV returns its space to the NAS.

**Migration** (follows `docs/superpowers/specs/2026-10-10-live-storage-migrations-design.md`)

0. **Prerequisites.**
   - Kubelet graceful shutdown ships on its own.
   - Jellyfin gets a guard.
   - **No live data moves until the off-site restic backup to the Hetzner Storage Box runs on schedule and one restore
     drill from it has passed.** Met on 2026-11-13 (ansible `docs/backup-and-restore.md`, **Restore drill**). At
     migration start, re-check that `pve-backup` has been green for 7 days and pstore is empty.
1. **Lab qualification** as above: ran 2026-11-16 to 2026-11-19. Its gaps close in production through gates F1, F2 and
   C1 below (Ben, 2026-11-21); Gate R1 waits for the later decision to turn automatic fencing on. Each gate runs only
   with Ben's OK at the time.
2. **Foundation.**
   1. The bridge PR.
   2. The three-image Packer layout (one full cluster rebuild).
   3. The storage VM, the data disks and the VG bootstrap. The bootstrap tags `retained` `hold_fence`, so automatic
      fencing stays off while Proxmox CSI disks remain attached to the workers, and after Retirement too (Ben,
      2026-11-21). The manual fence is the only fence until a later decision turns automatic fencing on.
   4. The worker NICs, folded into the three-image rebuild (D3).
   5. democratic-csi next to Proxmox CSI. The inventory starts empty.
   6. **Gates before the first cutover**, while the VGs hold no data:
      - **F1 (Check 3):** one deliberate rebuild of the storage VM, which was itself created from a fresh clone with
        `virtio0` declared. Both data disks survive, the VGs and tags are unchanged, and every target returns.
      - **F2 (Check 1):** one planned pve host reboot with the storage VM up, on the final code. Every target returns
        with no manual step, and the workers stop before the storage VM on the way down. `hold_fence` is set, so
        this does not test the cold-boot fence rule (F18); see the accepted-untested list. A failure
        here costs only an empty storage VM: every app still runs on Proxmox CSI.
3. **Cutovers, one volume at a time, serialized, each behind the capacity gate.**
   1. Add the entry (`origin: migrated`), so the reconcile creates a raw LV.
   2. Hold the app with a deny syncWindow on the `default` AppProject, inventory its writers, and scale it to 0.
   3. A copy Job uses temporary static Block-mode PV/PVC pairs on both sides. They are `Retain` and not pruned by Argo,
      and each `volumeHandle` is checked against the inventory.
   4. The Job checks that the target is at least as large as the source, then runs
      `dd bs=4M iflag=direct oflag=direct conv=fsync` over the source's full length. It deliberately does not use
      `conv=sparse`, which would leave the target's old blocks wherever the source holds zeros.
   5. With the target unmounted, it runs `cmp -n <source bytes>`, then `e2fsck -fp`, which also updates the last-check
      time, then `tune2fs -O mmp -E mmp_update_interval=5 -e remount-ro`. It confirms with `dumpe2fs -h`, and runs
      `resize2fs` if the inventory size is larger than the source.
   6. The binding switch (the app's claim, plus `copied`) goes in a separate PR from the inventory entry.
   7. Native app checks, then a 6-minute watch.

   - **Rollback:** a Git revert of the binding switch before the target takes writes; a reverse copy after that. The inventory
     entry is removed only after a reverse copy has finished and been verified.
   - **No packer or terraform rebuild** between a cutover and its reconciliation PR.
   - **Order:**
     1. tempo, alertmanager, loki, karakeep-meilisearch, prometheus (copied, not started empty);
     2. small SQLite apps;
        - **Gate C1 (Check 10)**, before the Servarr apps: on one migrated small SQLite app, while its old image is
          still the rollback, restore it once from a `usbbk` ZFS clone (the single-app runbook) and once off-site with
          `restic restore` of the `retained` image, each from a snapshot taken after that app's cutover, and check
          the app's data from each.
     3. the Servarr apps;
     4. the Home Assistant stack;
     5. Jellyfin;
     6. redis, then immich-postgres, then postgres. These follow `docs/runbooks/postgresql-storage.md`: a hold
        committed in Git for the server, consumers, pilot and backup jobs; the enrollment hook kept out while the
        server is at 0; and a fresh dump confirmed off-site before each cutover. "Confirmed off-site" means the dump is
        in a TrueNAS :30 snapshot, has been replicated, and `R ls` lists it after a green backup run. Redis is the
        exception (D30, Ben waived its fresh dump, 2026-11-23): it has no dump job and holds queues, caches and
        sessions. Its rollback sources are its old image, kept as above, and that day's 04:30 off-site backup of the
        running Redis, whose AOF is crash-consistent but is not a dump.
4. **Retirement.**
   - The old `.raw` images stay as rollback sources until Ben approves deleting each one.
   - After the last volume has moved, remove:
     - the proxmox-csi chart, `shared-storage-settings.json` and the slot alerts;
     - the topology labels and `max-volume-attachments`;
     - the migration copy tool (`migrate_volume.py`, `copy_volume.sh`), once the last reverse-copy window has closed.
   - Move `k3s_node_retirement_enabled` and its CA path to their own file before `group_vars/all/proxmox_csi.yml` goes,
     and repoint `scripts/tests/test_proxmox_csi_bootstrap.py`.
   - Remove terraform's `k3s_resource_pool` and its `ignore_changes` on `disks[0].scsi`.
   - Automatic fencing stays off after Retirement: `hold_fence` stays on `retained`, the fencer keeps refusing, and the
     manual fence stays the only fence (Ben, 2026-11-21). Turning it on, with Gate R1 (a planned `qm suspend` fence
     drill at the 300 s threshold), is a later decision.
   - Check 11 at 300 s runs at the first planned worker reboot after Retirement, with fencing held.
   - Replace the `CLAUDE.md` contract row "CSI pool, slots, topology" with storage-VM rows.

**Changes per repo**

| Repo | Changes |
|---|---|
| packer | Split `bootstrap.sh` into base, k3s and storage steps plus one seal step run last in every build; drop `build-essential` from the preseed; two `proxmox-clone` sources (key injection); three manifest builds; `build.yml` builds the base first, then k3s and storage in their own publish jobs. |
| terraform | Storage VM in its own root `storage/` and backend key (`prevent_destroy`, `ignore_changes` on clone, tag `storage`, no CSI pool), plus a `--chdir` normal-mode path in `maintenance_apply.py`, plan and drift matrix entries, and a clone-source pre-check in `apply.yml`; attached data disks with `discard=on` and the cloned root disk declared as `virtio0`; the `storage_nic` variable, added to the workers in the Foundation rebuild; manifest consumers pick the k3s template by name; a test that a base image change leaves the storage VM untouched. |
| ansible | Additive pve bridge; storage VM in `guest_startup.yml`; storage-VM role (reconcile, ledger, LIO, nftables with the `fenced` set, `targetctl save`, the LIO lock, `storage-fencer` with its unit, bootID history and tests, the nftables and `rtslib-fb-targetctl.service` fence drop-ins, `hold_fence`, and the token copy); deterministic worker IQNs and `open-iscsi`; k3s settings (no-force-detach, kubelet drop-in 90s/40s, fstrim); Argo CD `kustomize.buildOptions: --enable-helm`; the `storage.yml` workflow and the daily expiry job; backup exclude for the `regen` disk and its test; node-retirement variables in their own file; tests. |
| apps | Inventory, renderer and CI checks; democratic-csi chart through kustomize `helmCharts` with `blkid` detection and the node shutdown patch (no `cleanup`, native sidecars, no registrar `kubelet-dir`) plus the `csi-driver` preStop hold in the chart values; guard templating; the dispatch step; the `storage-fencer` ServiceAccount, ClusterRole (nodes, VolumeAttachments) and token Secret; a storage-VM ScrapeConfig and alerts (`StorageWorkerFenced`, `StorageFenceFailed`, `StorageFenceDraining`, `StorageFencerBlind`, a long-lived out-of-service taint, reconcile failure, missing target, VG and dataset free space, `pending-delete`, `hold_create`); runbooks (restore, hang fencing, growth, `crashed-create` and orphan recovery, half-expiry recovery through `storage.yml`, read-only filesystem recovery, the storage VM rebuild with its writer drain, and upgrading the held `lvm2`, `python3-rtslib-fb` and `targetcli-fb`). |
| .github | `CLAUDE.md` and `profile/README.md`: the `storage-changed` trigger, and contract rows for the inventory, the storage image and the startup order; update the "Backup inputs" row, which names the `vm-9999-*` images; a contract row for packer `source-base.pkr.hcl` `disks` against terraform `storage/main.tf` `virtio0` (a root disk over 4 GiB fails the create part-way). |
