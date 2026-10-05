# Proxmox CSI and Jellyfin cutover implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` inline. The user has
> approved autopilot and agent PR merges until Jellyfin downtime ends. Check off
> execution steps only against observed results.

Status: first production attempt blocked during the independent backup by a
Proxmox NFS client stall. The complete NAS copy passed, but no backup restore,
worker replacement or CSI activation occurred. Jellyfin recovered on its original
iSCSI source; see the [incident and recovery report](../reports/2026-10-05-proxmox-csi-cutover-blocked.md).
The unpublished cold copy becomes stale after recovered source writes. Further
host recovery requires a separate decision and a fresh cutover attempt.

**Goal:** Migrate Jellyfin's existing ext4 configuration volume to the retained
Proxmox CSI platform while establishing the worker-rebuild safeguards once.

**Architecture:** Cold-copy the existing NAS ZVOL into a raw image owned by
external ID9999. Git reconstructs its static PV/PVC; stock CSI manages attachment.
Use a durable Git writer hold across the normal Terraform-to-Ansible handoff.

**Tech stack:** TrueNAS25.10.7, PVE9.2.20, CSI v0.20.0/chart0.5.10,
k3s v1.37.0+k3s1, ext4/cache-none. Keep Jellyfin's current pinned image unchanged.

**Spec:** [accepted architecture](../specs/2026-10-03-portable-iscsi-native-lifecycle-proposal.md),
[shared integration](2026-10-03-proxmox-csi-shared-integration.md),
[completed qualification](../reports/2026-10-04-proxmox-csi-rebuild-results.md),
and [shared setup receipt](../reports/2026-10-05-proxmox-csi-production-setup.md).

## Operational scope requiring approval

- One coordinated Jellyfin outage for quiescing, backup, restore validation,
  copying and release. Replacing workers201/202 also interrupts other workloads;
  the control-plane VM200 is intended to remain. Duration is not yet measured.
- Temporary validator VM980, cloned from template900: 2vCPU, 4GiB RAM, a 32GiB
  boot disk plus a 64GiB restored-data disk on `vm-pool`. Use a verified unused
  management address before allocation. Isolate application traffic; no production
  media mounts, LDAP connections, discovery broadcasts or application egress.
  Only management and required image/dependency downloads are permitted before
  running the restored application. No administrator or production CSI token
  enters this guest. Record its new UUID, disks and temporary SSH identity for
  cleanup; an occupied ID980 is a stop, not permission to delete it.
- A new owner-only cold image backup under the existing encrypted workstation
  destination `/home/benf/Backups/homelab/jellyfin/`, transferred over verified SSH.
  The workstation stores/transports bytes only; all filesystem and application
  restore testing runs on VM980. Preserve existing backups.
- Temporary nonprivileged tooling on VM300 may use the existing CSI credential
  in place to seal configuration and verify native client TLS. Vault recovery
  checks use the normal trusted Actions job. No new administrator credential
  transfer, token creation or ACL expansion is included.
- A 64GiB image at
  `/mnt/apps/k3s-block/images/9999/vm-9999-jellyfin.raw`, within the existing
  128GiB aggregate quota. Preserve the original ZVOL, iSCSI configuration and
  cold snapshot. Do not increase quota or remove old storage in this change.
- A TrueNAS snapshot task for `apps/k3s-block`, matching the existing task's
  six-hour schedule and one-week retention. Preserve the old task. These are
  storage snapshots, not a claim of application-consistent backups or a new
  routine-rebuild prerequisite.
- Activate verified retirement, CSI topology, the cohort policy, pool membership,
  recoverable sealed CSI configuration and the upstream controller through
  separately reviewed PRs in the order below. Normal rebuilds retain the user's
  existing PR merge procedure and require no backup checkpoint.

The previous approval covered shared allocation only and explicitly excluded
worker replacement and application migration. Approval of this plan supplies that
operational scope; it does not waive the preconditions. The user's subsequent
autopilot instruction temporarily authorizes migration PR merges until Jellyfin
downtime ends. Unexpected privilege changes or a different replacement plan
require another decision.

## Constraints and evidence

- Apps main `9a32641c261fb3d72ed2bfc2598f5acc57c891d6` records completed shared
  setup. Ansible PR282 merged as `64ead68bd9ff98546ee895c358605f7068e38f69`;
  its normal deployment succeeded. Retirement and CSI remain disabled.
- Ansible now trusts the independently verified API leaf for strict native TLS.
  This does not prove the deployment token has complete audit visibility. The
  production driver must separately prove trusted TLS with `insecure: false`.
- Source ZVOL GUID `14950202402923644020`, capacity68719476736 bytes, ext4 UUID
  `d3cc0be9-ad2f-4c67-a6fc-abc6104b7712`. Target dataset GUID
  `13918781591004512447`; owner9999 is reserved and is not a VM.
- NAS-local block/image tools and the authenticated QEMU guest-agent route were
  verified read-only. NAS SSH is disabled and remains disabled. No copy has run.
- Read-only inspection on October5 found VM980 absent, about136GiB free on
  `vm-pool`, about11GiB available host RAM and the target dataset empty. Repeat
  capacity, identity and ownership checks before allocation; these are snapshots
  of availability, not reservations.
- Current NAS task2 covers `apps/iscsi` recursively: minute0, hour`*/6`, every day,
  window00:00–23:59, naming`auto-%Y-%m-%d_%H-%M`, retention1WEEK. The new dataset
  is not covered. Original source ZFS `used` is not filesystem occupancy.
- Public planning observations are retained in the
  [preflight receipt](../reports/evidence/2026-10-05-proxmox-csi-cutover-preflight.json).
  They describe discovery, not completed migration acceptance.
- Preserve the maintenance lock, existing iSCSI generation safeguards, bootstrap
  sealing key and all unrelated services. No new controller, driver fork or
  duplicated Ansible service inventory. Preserve local `get-kubeconfig.sh` edits.

## Review focus

1. API visibility: HTTP200 must not turn a hidden old VM into proof of absence.
2. Restart races: Git holds both claims while workflow ownership changes hands.
3. Interrupted copy: an incomplete image must never have the final CSI handle.
4. Rebuild recovery: credentials and bindings must be recoverable outside k3s.
5. Rollback after writes: the original ZVOL becomes stale after target writes;
   restarting it would lose accepted changes.

## Task 1: Finish preconditions while Jellyfin remains available

Files: Ansible `group_vars/all/proxmox_csi.yml`, existing retirement role/filter
and bootstrap role; Apps `scripts/seal.sh`, `scripts/sealed-secrets-cert.pem`,
`infrastructure/system/proxmox-csi/values.yaml` and staged descriptor.

- [x] Add a manually invoked read-only preflight through the existing Ansible
  self-hosted Actions runner, using its normal `PROXMOX_*` and Vault secrets.
  Use native `ansible.builtin.uri` with the merged trust file and the existing
  complete-visibility filter. Read permissions, ACLs, all VM resources and QEMU
  configurations; recheck permissions/inventory for drift. Do not invoke the
  retirement role's deletion path or infer the identity from another API token.
  Keep credentials in the job, suppress secret-bearing output and clean temporary
  files. A failure blocks activation without changing grants automatically.
- [x] In that trusted runner context, verify that the Vault bootstrap private key
  matches both its certificate and Apps' public sealing certificate. Recover a
  sealed probe with the external key and compare its contents. Do not export the
  bootstrap private key to the workstation or validator or rely solely on the
  key currently present in Kubernetes.
- [x] Stage the actual CSI configuration using `scripts/seal.sh` on VM300,
  compact JSON under key`config.yaml`, region`homelab`, controllerVmID9999 and
  the existing scoped token. Only encrypted output leaves the protected runner.
  Verify recovery with the external bootstrap key before publication.
- [x] Supply the independently verified public PVE trust material through the
  chart's native controller `extraVolumes`/`extraVolumeMounts`, keeping
  `insecure: false`. Render the exact chart; qualify its native API TLS connection
  before enabling production attachment. Do not reuse the lab's insecure flag.
- [x] Prepare the Git hold, binding and release diffs and render each with actual
  value layers. Review a real Terraform plan for
  `rebuild_workers_with_control_plane=true`, `k3s_resource_pool="k3s-csi"`.
  Expect workers201/202 replaced and pool membership for200–202. Stop for any
  control-plane replacement, unrelated VM change or retained-image deletion.
  Do not merge this activation PR before Task3 is complete.
- [x] Prepare and qualify the disposable validator, including download of the
  exact pinned Jellyfin image before disabling application egress. No production
  data is written or attached merely to prepare the guest.

Deliverable: passing read-only runtime receipts, reviewed source diffs and an
exact provider plan. No outage starts with an unresolved precondition.

## Task 2: Establish a durable hold and a cold source

Files: Apps `services/media/jellyfin/values.yaml`,
`services/media/jellyfin/manifests/{ldap-library-sync,retained-storage}.yaml`.
Use an explicit deny policy for the source and proposed target claims; leave
the existing old-generation authorization intact behind that hold.

- [ ] Acquire the existing VM300 maintenance operation with fresh identities.
  Merge the reviewed hold PR: Jellyfin replicas0, LDAP CronJob suspended and
  admission denies new pods using either source or target claim. Verify ArgoCD
  has reconciled that exact revision and negative server-side admission probes
  fail. A replica count alone is not the hold.
- [ ] Wait for all Jellyfin/LDAP jobs and pods to terminate. Verify kubelet
  unmount, iSCSI session removal for this target and no other NAS-side initiator
  sessions or local mounts. Do not force detach a volume with an uncertain writer.
- [ ] Snapshot the exact source ZVOL after clean unmount, record GUID/name and
  verify readonly ext4 health. A dirty or unhealthy source blocks copying; stock
  CSI's accepted repair policy is not permission to repair the only source here.

Deliverable: independently verified cold source and a Git hold that survives
ArgoCD reconciliation, worker replacement and fresh cluster metadata.

## Task 3: Copy, back up and validate the application

No service-specific allocation code enters Ansible. Use a reviewed, operation-local
copy procedure via authenticated Proxmox/NAS management; retain its sanitized
commands and receipts with the operation.

- [ ] Recheck target dataset GUID, available quota/pool space and absence of the
  final image. Create the owner directory only if needed and an exclusively
  created temporary image. Copy all68719476736 source bytes, flush, and compare
  complete source/target hashes with the source still quiescent. Check target
  image size, ext4 UUID and readonly filesystem health. Failures leave the partial
  file unpublished and the writer hold active; never overwrite an existing image.
- [ ] Transfer the verified cold image to a new mode0600 off-NAS backup; verify
  its full hash. Restore that backup into VM980's separate64GiB disk, verify the
  restore hash and mount only that copy. No production source/target attachment
  is needed on the validator.
- [ ] On the isolated restored copy, check every persistent SQLite database with
  SQLite integrity checks including WAL recovery as appropriate. Run the exact
  Jellyfin image, verify startup and `Healthy`, compare application/server identity
  and library/user metadata with the cold baseline. Protect private content from
  public logs. No plugin upgrade, LDAP action or library scan against production.
- [ ] Publish the completed raw image without clobbering an existing final name
  only after copy and restore acceptance. Flush the parent directory. Record
  hashes/UUID/size and retain the original ZVOL, cold snapshot and off-NAS backup.
- [ ] Add the new dataset snapshot schedule; read back the exact task and ensure
  the original snapshot task and exports are unchanged.

Deliverable: verified final image plus an independently restored off-NAS backup.
Do not claim the isolated test proves GPU playback; test that after production
release using the existing acceptance procedure.

## Task 4: Activate the platform through normal PR handoffs

Files: Ansible `group_vars/all/proxmox_csi.yml`; Terraform's existing cohort/pool
inputs; Apps `infrastructure/system/proxmox-csi/{app.yaml,values.yaml}` and its
sealed configuration/trust manifests in the established prerequisite phase.

- [ ] After Task3, release migration maintenance ownership only when the durable
  Git hold and absence of writers are verified. Native deployment workflows must
  acquire their own ownership. Do not hold an outer operation that deadlocks
  those jobs or bypass their existing lock checks. The normal Terraform helper
  releases before Ansible dispatch; there is no claim of one lock across jobs.
- [ ] Merge Ansible enablement for retirement and region`homelab` topology; verify
  its deployment before worker replacement. Merge the exact reviewed Terraform
  activation plan, preserving native dependency order and dispatch.
- [ ] Require old worker UUIDs gone in full Proxmox inventory, new guest/Node UUID
  matches, old Node UIDs retired, all nodes Ready, labels correct and native drain
  recovery complete. Confirm the master is unchanged and the pool contains only
  intended k3s VMs. Partial failure retains the native failed-operation state;
  do not clear ownership or release Jellyfin to work around it.
- [ ] Publish/reconcile the recovered CSI Secret and public trust bundle before
  controller discovery. Activate stock CSI and verify authenticated TLS,
  controller/node readiness and expected API scope. The Jellyfin hold stays active.

Deliverable: qualified shared platform, preserved source/target, zero Jellyfin
writers. Repeat live checks immediately before release.

## Task 5: Bind and release Jellyfin

Files: Apps shared storage manifests and
`services/media/jellyfin/{values.yaml,manifests/ldap-library-sync.yaml,README.md}`.
Put provider-specific PV details in shared infrastructure; service values consume
only the new claim. Do not edit or repurpose the old bound PV/PVC in place.

- [ ] Declare PV/PVC`jellyfin-config-block`, namespace`media`,64GiB, ext4,
  Retain, RWOP, mutual prebinding without an old claim UID and Argo prune/delete
  protection. Use handle
  `homelab//k3s-block/9999/vm-9999-jellyfin.raw`, the qualified chart's class and
  cache-none parameters. Reconstruct from these declarations, not old metadata.
- [ ] Switch the held app to the new claim. Remove only its old iSCSI-specific
  writer label, generation affinity and iscsi-ready selector. Add the qualified
  infinite NoExecute tolerations for NotReady/Unreachable nodes, preserving GPU
  scheduling and all other app settings. Render both held and released stages;
  verify the old iSCSI claim remains denied.
- [ ] Acquire migration ownership for the final verified release, then merge the
  reviewed target-release PR. Permit only the intended target writer, start one
  replica, and observe one attachment, original filesystem/application identity,
  SQLite health and Jellyfin readiness. Verify actual playback/transcoding using
  existing acceptance checks; restore LDAP scheduling after acceptance.
- [ ] Confirm Terraform shows no CSI-attachment drift. Archive sanitized evidence,
  remove validator VM980 and its recorded temporary disks/SSH material, remove
  temporary credential/tool copies and release maintenance ownership. Keep the
  original source, snapshots and backup; source retirement is a later decision.

## Failure and rollback boundaries

- Before worker replacement and before target writes: keep target held, verify
  it has no writer, and revert the source hold only against its still-valid old
  generation authorization. Original source bytes remain unchanged.
- After worker replacement but before target writes: original source is still
  usable, but reverting Git alone cannot authorize new workers. Use the existing
  reviewed exact-generation iSCSI enrollment/release process; never remove its
  safeguards to shorten rollback.
- After any target write: stop and preserve the new image. Recover forward, or
  perform a separately reviewed cold reverse transfer of the newest data. Do not
  restart the stale original ZVOL as if it were current.
- Every uncertain identity, incomplete visibility, copy/hash/restore failure or
  interrupted deployment leaves the writer hold active. Preserve the appropriate
  operation receipt; do not erase a lock merely to retry.

This is a one-time conversion. Routine worker/control-plane rebuilds use the
accepted native lifecycle and stable Git bindings. Later volume growth remains
PVC request, verify backend/filesystem expansion, then reconcile Git PV capacity.
