# Jellyfin retained block storage accepted

Jellyfin now uses the original ext4 filesystem in a NAS-backed raw image attached
by unmodified upstream Proxmox CSI v0.20.0/chart0.5.10. The shared Git PV/PVC
reconstructs the stable binding; normal Terraform rebuilds require no Velero
checkpoint or manual backup verification. The source ZVOL is preserved and denied
by admission. It became stale when target writes began and cannot be restarted as
an ordinary rollback.

The fresh outage began at00:40:51Z on October6. Jellyfin became Ready at02:06:35Z,
about86minutes later; authenticated playback and GPU checks followed. This is the
measured one-time conversion interval, including backup, independent restore and
worker replacement, not a routine rebuild estimate. Production acceptance was
recorded at02:11:30Z and repeated at02:13:07Z. LDAP remains suspended live until
this follow-up PR is merged. Temporary migration-only merge authority ended when
health/playback recovered.

## Evidence and validation

The [sanitized receipt](evidence/2026-10-06-proxmox-csi-jellyfin-cutover.json)
contains identities, hashes and acceptance results, without credentials or private
media/user rows. Full protected operational evidence remains on VM300 under
`/var/lib/homelab-maintenance/operations/jellyfin-csi-cutover-20261006/` and
`jellyfin-csi-release-20261006/`; NAS/validator receipts remain in their fresh
October6 operation directories.

- Fresh snapshot: `apps/iscsi/jellyfin-config@pre-proxmox-csi-20261006`.
  The complete64GiB source/copy hash matched:
  `7d2e104599f1f0573c55b8039b1dba7baef584511a9755476e1b6329749aa9bc`.
  Both read-only ext4 checks passed.
- Completed owner-only encrypted off-NAS backup:
  `/home/benf/Backups/homelab/jellyfin/proxmox-csi-20261006T004950Z/image.raw.gz`.
  Compressed27,963,782,685bytes; all68,719,476,736 raw bytes were independently
  restored, flushed and read back with the matching hash. The workstation stored
  and transported bytes only; it never mounted or ran the restored application.
- Isolated VM980 ran the exact pinned production image without production media
  or network access. All five SQLite databases passed integrity checks before and
  after startup; original server identity and critical metadata counts matched.
- Only workers201/202 were replaced. Native Terraform apply
  [37399797942](https://github.com/Starktastic-Homelab/terraform/actions/runs/37399797942)
  and Ansible handoff
  [37400092382](https://github.com/Starktastic-Homelab/ansible/actions/runs/37400092382)
  succeeded. Full Proxmox inventory and guest/Node UUID checks proved old worker
  generations absent and old Nodes retired. Master200 was preserved; all three
  Nodes were Ready with the required topology. Pool membership is200–202 only.
- Strict CSI TLS, encrypted configuration recovery, the exact qualified stock
  controller image and two node plugins passed. Retained static64GiB ext4/RWOP
  PV/PVC`jellyfin-config-block` was mutually Bound and unattached before release.
- PR1299 released one replica at revision
  `6af0bb098597f42f25ab20c25937593ebf38b365`. Exactly one Kubernetes/PVE attachment
  exists, on worker202 with cache-none. The ext4 UUID remains
  `d3cc0be9-ad2f-4c67-a6fc-abc6104b7712`. All five live SQLite quick checks passed;
  `kodisyncqueue.db` is explicitly recorded as a non-SQLite-format plugin file.
- `/health` was `Healthy`; original server identity/version12.1.0,14users,
  292movies,148series,5059episodes,53boxsets and28,794API items matched.
  Authenticated HTTP206 delivered an8MiB production media sample, five video
  frames decoded, and Intel`h264_vaapi` encoded five frames in the production
  container. This bounded playback/encoder check does not claim full client,
  subtitle, HDR or server-managed streaming-transcode coverage. Transient sample
  files were removed. The configured encoder remains VAAPI on`renderD128`.
- Read-only Terraform drift run
  [37402653368](https://github.com/Starktastic-Homelab/terraform/actions/runs/37402653368)
  reported no changes after CSI attachment.
- VM980's exact fresh UUID, its three owned disks and temporary SSH key were
  removed after acceptance. The production image, source, snapshots and backup
  were preserved. Durable writer holds protected each normal maintenance-lock
  handoff; no native lock was bypassed or stolen. The release operation archived
  twelve sanitized procedures and released its owned nonce lock after cleanup.
  Temporary sealing/TLS directories and containers are absent; permanent scoped
  runtime credentials remain in their protected locations.

## Operational rulings

The plan ledger records these decisions in execution order, including the first
attempt. Superseded validator settings describe that attempt only.

1. Add relevant infrastructure documentation so path-filtered required checks
   run for the planning PR. Cost if wrong: extra documentation; no branch
   protection bypass.
2. Use normal group-vars loading with explicit localhost inventory for offline
   Ansible syntax validation, avoiding explicit Vault vars-files decryption.
   Cost if wrong: incomplete offline coverage; real trusted preflight still gates.
3. Correct upstream's native key to`controllerVmID`, verified in config.go.
   Cost if wrong: owner identity misconfiguration; actual runtime owner is checked.
4. Leave Terraform action boxes unchecked for normal worker-only mode. Cost if
   wrong: incorrect outage scope; the real plan independently excludes master
   replacement and broad master drain.
5. For the first validator, require full4GiB guest allocation,256MiB QEMU
   allowance and2GiB host reserve, with the existing post-start floor. Cost if
   wrong: host memory pressure; no production memory/cache adjustment was made.
   This resource setting was superseded for the fresh retry below.
6. Use native DHCP for temporary dependency access; accept the guest-agent address
   only after fresh UUID/MAC and production-address checks. Disconnect the vNIC
   before restored bytes or app startup. Cost if wrong: address collision or
   isolation failure; those identity/link checks gate execution.
7. Use fresh October6 operation/snapshot/image/backup identities and preserve
   October5 evidence. Cost if wrong: stale data reuse or evidence loss; old artifacts
   were never overwritten or used to authorize publication.
8. Cap the fresh isolated validator at2GiB guest RAM/1.5GiB container memory,
   retaining256MiB QEMU allowance and2GiB host reserve. Cost if wrong: OOM blocks
   qualification; production memory was unchanged.
9. Count only nonterminal Pods as active writers; independently require mount and
   session absence before copying/replacement. Cost if wrong: hidden writer;
   terminal Pod state alone was never the coldness proof.
10. Recognize the existing generation-guard denial when it precedes the migration
    hold denial; separately verify exact hold rules, generation and unfiltered
    Deny binding. Cost if wrong: invalid probe attribution; no live policy was
    weakened, and independent coldness/zero-writer gates remain mandatory.
11. Determine SQLite files by their header, matching cold validation. Record the
    known non-SQLite`kodisyncqueue.db` and require all five actual SQLite paths.
    Cost if wrong: omitted health coverage; exact inventory/header checks guard it.

No minor review findings were deferred. Preserve the earlier NFS stall evidence:
recovery and this completed transfer do not establish a permanent kernel fix.
Source retirement, broader client playback coverage and additional service
migrations are outside this cutover.
