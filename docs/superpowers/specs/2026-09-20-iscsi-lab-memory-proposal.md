# Temporary RAM arrangement for the shared-host iSCSI lab

Date: 2026-09-20. Status: RAM arrangement approved. The user subsequently
requested both workers in one PR and proposed full destruction/recreation.
The user selected and confirmed destroy/recreate and merged PR #222. All three
K3s VMs have been recreated; Terraform and Ansible passed. Application recovery
and the sampled observation window are complete. See the [execution report](../reports/2026-09-20-cluster-rebuild-memory.md).

The user accepted potential Filebrowser local-database and Audiobookshelf
metadata loss for this operation. Earlier preservation gates for those two
items below are superseded by that explicit decision. The procedure below
records the design choices; current execution status is in the report.

The user approved the proposed temporary RAM arrangement and runner shutdown.
K3s VM changes go through the Terraform repository, with merges remaining under
the user's control. This arrangement avoids a TrueNAS outage.

## Recommended allocation

All quantities below are GiB of configured guest RAM.

| VM | Role | Before maintenance | Temporary target | Reason |
|---|---|---:|---:|---|
| 100 | Production TrueNAS | 32 | 32 | Preserve the shared storage service and avoid a whole-cluster shutdown |
| 200 | K3s master | 16 | 16 | Hosts application pods as well as the control plane; less historical spare RAM |
| 201 | K3s worker-01 | 28 | 20 | Reclaim 8 GiB during the joint worker maintenance window |
| 202 | K3s worker-02 | 28 | 20 | Reclaim another 8 GiB in the same PR |
| 300 | Infrastructure runner | Up to 4 | Stopped after CI finishes | Needed for Terraform plan/apply and downstream Ansible |
| New lab VMs | NAS + server + two workers | 0 | 8 + 2 + 1 + 1 | Initial synthetic storage/recovery tests, 12 GiB total |

This leaves 88 GiB assigned to running production guests and 100 GiB including
the lab, against 125.55 GiB physical host RAM. The difference is not all free:
the host, ZFS ARC, QEMU and other allocations also consume memory. Do not launch
based solely on configured totals.

The initial lab size is a constrained test budget, not an application sizing
result. TrueNAS documents 8 GB as its basic minimum; K3s documents 2 GB for a
server and 512 MB for an agent, excluding workloads. Start with synthetic SQLite
fixtures and CSI lifecycle tests. If those components cannot operate within
this budget, stop and revise the lab size. Full application-copy tests remain
a later phase and may require more memory.

Sources: [TrueNAS hardware guide](https://www.truenas.com/docs/scale/gettingstarted/tnhardwareguide/),
[K3s requirements](https://docs.k3s.io/installation/requirements).

## Evidence and choice of target

The [live audit](../reports/2026-09-20-application-state-audit.md) records these
minimum guest `MemAvailable` values across all retained samples over seven days:

| Guest | Lowest available | Proposed reduction | Illustrative headroom after subtraction |
|---|---:|---:|---:|
| master-01 | 5.376 | 0 | 5.376 |
| worker-01 | 12.710 | 8 | 4.710 |
| worker-02 | 13.177 | 8 | 5.177 |

Subtraction is a stress comparison, not a prediction: cache behavior, reboot
effects and future workload growth can change memory use. Many workloads lack
memory limits, so their small resource requests are not a sufficient sizing
argument. Cutting the master to 12 GiB would leave only 1.376 GiB under the same
comparison; avoid that cut.

Workers at 22 GiB would preserve another 2 GiB each, but save only 12 GiB total.
With about 5 GiB available before maintenance, that was unlikely to meet the
20 GiB launch gate below. Workers at 20 GiB save 16 GiB and are the proposed
target for both workers. Observe both guests after the update and restore RAM
if either shows pressure; do not start the lab until production is healthy.

The runner's observed host memory was about 0.63 GiB, despite its 4 GiB maximum.
Count only measured recovery after it stops. Likewise, do not count the host's
approximately 8.53 GiB of potential ARC shrinkage as already available memory.

## Executed maintenance and remaining gates

The original two-PR, per-VM override proposal was superseded by the user's
request for both workers together. PR #222 changed only the existing shared
`worker_memory` setting from 28672 to 20480 MiB. The normal saved plan verified
exactly those two in-place memory updates.

The user selected and confirmed full destroy/recreate and merged at 19:34:39
UTC. That path bypasses the saved plan and Kubernetes drain, destroys master
200 and workers 201/202 including their OS disks, then applies and dispatches
Ansible. TrueNAS 100 and runner 300 are outside that Terraform state. The user
accepted Filebrowser local-database and Audiobookshelf metadata loss for this
operation. Both infrastructure workflows passed and the effective VM RAM
matches the target table above.

Keep runner 300 online through recovery. Verify node readiness, retained storage
bindings, restored secrets/certificates and application health. Observe at
least 30 minutes plus representative normal workload activity. Sustained guest
`MemAvailable` below 2 GiB, MemoryPressure, OOM or unrecovered services stops
progression to lab startup.

Once recovery is complete, verify runner idleness, stop accepting new jobs and
shut it down cleanly. Lab execution must use a verified local route independent
of the runner. Measure actual host `MemAvailable` again: require at least 20 GiB
for the 12 GiB guest budget and 8 GiB operational allowance. If unmet, leave the
lab off and reassess; do not automatically shrink the master or NAS.

A normal in-place RAM reversal may restart workers: the pinned Telmate provider
defaults `automatic_reboot` to true and memory hotplug is not configured.
Downstream Ansible also reconciles K3s/bootstrap, so review its scope when
preparing the eventual reversal.

Sources: [pinned provider reboot defaults](https://github.com/Telmate/terraform-provider-proxmox/blob/v3.0.2-rc10/proxmox/Internal/resource/guest/reboot/schema.go),
[pinned VM implementation](https://github.com/Telmate/terraform-provider-proxmox/blob/v3.0.2-rc10/proxmox/resource_vm_qemu.go).

## Runtime guard and reversal

Start lab VMs individually and measure the host after each start. Lab VMs stay
off at host boot and use an isolated test network and test-only disks. Before
launch, implement and verify an external guard that can stop only lab guests
without relying on the lab cluster. Pause tests and shut down lab guests if
host available memory stays below 6 GiB for 30 seconds, production shows memory
pressure, or host OOM occurs. Use a bounded graceful shutdown with a test-only
forced-stop fallback if necessary. Do not rely on this guard to compensate for
failing the initial launch gate.

To reverse the RAM changes, stop the lab first, start runner 300, and restore
worker RAM to 28672 MiB through a reviewed Terraform change and prepared
maintenance. Recheck actual host capacity before increasing RAM. Keep existing VM disks;
do not use replacement or infrastructure-destroy recovery.

## If TrueNAS RAM reduction becomes necessary

It is not part of the recommended first attempt. No live TrueNAS memory history
or workload sizing has yet justified a lower target. A separate proposal would
need that evidence and a whole-storage maintenance window: quiesce writers,
stop all dependent clients including VMs 200–202, verify backup/recovery access,
then stop and resize VM 100. Restore TrueNAS and verify pools, datasets and
exports before the master, then workers and applications. Check other clients
and the runner's storage/backend dependencies too; stopping only Kubernetes
does not prove that the NAS has no active users.

## Current execution status

[Terraform PR #222](https://github.com/Starktastic-Homelab/terraform/pull/222)
was merged and its full rebuild succeeded. Historical memory-only plan
inspection is retained in
[the sanitized plan evidence](../reports/evidence/2026-09-20-workers-ram-plan.json);
it does not describe the subsequently selected destroy operation.

All 68 claims are Bound, with every NFS backend matching the pre-rebuild
inventory. All 38 Sealed Secrets and seven certificates recovered. Sonarr and
Radarr RU recovered after the user changed their live AllowedHosts settings.
The tested optional correction for probes with restrictive hostnames is
[apps PR #1231](https://github.com/Starktastic-Homelab/apps/pull/1231).

Runner 300 was shut down after recovery and an idleness check. At 20:16 UTC
host available memory was 21.83 GiB. No lab VMs have been created. See the
[execution report](../reports/2026-09-20-cluster-rebuild-memory.md) for current
health, memory evidence and remaining acceptance gates.
