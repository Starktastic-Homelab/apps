# Cluster rebuild and temporary worker RAM reduction

Date: 2026-09-20. Status: VM recreation, Ansible bootstrap and application
reconciliation passed. Runner 300 is stopped. Memory samples span over
30 minutes; isolated-lab implementation and rehearsal remain outstanding.

## Authorized operation

The user selected and confirmed the Terraform PR's full destroy/recreate mode,
then merged [PR #222](https://github.com/Starktastic-Homelab/terraform/pull/222)
at 19:34:39 UTC, merge commit `6f5efde973e0116ee663264fc2b56cac5736f233`.
The user explicitly accepted potential loss of Filebrowser's local database
and Audiobookshelf metadata for this operation. Those are no longer preservation
blockers for this rebuild; this does not change their long-term recovery status.

The normal plan had verified only two memory changes. The user-selected destroy
mode instead destroyed and recreated master 200 and workers 201/202, with fresh
OS disks and Kubernetes identities. TrueNAS 100 and runner 300 were not part of
the destroy scope. The assistant did not merge or dispatch a second apply.

## Pipeline and VM evidence

- [Terraform run 35532752263](https://github.com/Starktastic-Homelab/terraform/actions/runs/35532752263)
  passed the destroy, recreation and downstream-dispatch steps.
- [Ansible run 35532918289](https://github.com/Starktastic-Homelab/ansible/actions/runs/35532918289)
  passed bootstrap and the organization kubeconfig-secret update.
- Proxmox reports master 200 at 16384 MiB and workers 201/202 at 20480 MiB.
  TrueNAS remains at 32768 MiB. Runner stayed online through recovery and was
  shut down at approximately 20:09 UTC after verifying it was idle.
- All three fresh nodes are Ready, with no MemoryPressure, DiskPressure or
  PIDPressure at the sampled checks. Master creation time is 19:39:53 UTC;
  both workers registered at 19:40:18 UTC.
- The local kubeconfig was refreshed securely through the authenticated
  Proxmox guest agent on VM 200 and installed atomically with mode 0600.
  Credential contents were not printed or placed in evidence files.

## Recovery observations

Initial config-application errors referenced missing namespaces and CRDs.
Source review and successive observations showed the intended independent
retry policy and RollingSync phases advancing: CRDs became Healthy at 19:43:44,
NFS and Sealed Secrets followed, then certificate management and controllers.
No manual sync, namespace creation or bootstrap code change was needed.

At both 20:07:44 and 20:16:49 UTC, all 77 Argo applications were Synced/Healthy and all 125
active pods were Ready. All 68 claims were Bound; comparing namespace/claim
and backend server/path found no NFS mismatches against the original inventory.
Every NFS PV retained its Retain policy. The two local claims were recreated;
local storage continuity is not claimed. All 38 current-generation Sealed
Secrets synced, their target Secret names exist, and all seven certificates
were Ready. Credential values were not captured.

Sonarr and Radarr RU initially restarted because their retained `AllowedHosts`
restrictions rejected the pod-IP HTTP Host used by startup probes. Requests to
the same pod IP with `Host: localhost` returned 200. The user changed their live
settings to `*` and confirmed doing so; they recovered before the proposed fix
was merged. This was an HTTP hostname-filtering failure, not evidence of a new
SQLite startup failure.

[Apps PR #1231](https://github.com/Starktastic-Homelab/apps/pull/1231) adds the
stable header to shared probes, so restrictive hostname settings can coexist
with Kubernetes health checks. It remains unmerged and is no longer an urgent
recovery dependency. All local checks, seven-app/21-probe render comparisons,
server-side dry-run admission and GitHub CI checks passed. No imperative
Deployment change or application configuration edit was made by the assistant.

Read-only retained-data checks found:

- PostgreSQL `PG_VERSION=18` with a December 15, 2025 modification time, 12
  directories beneath `base/`, and `global/pg_control`; its pod was Ready.
- Jellyfin `/config/data/data/jellyfin.db` is 188,723,200 bytes, with a valid
  SQLite header and a 19:12:57 UTC modification time preceding the rebuild.
  The public endpoint reports version 12.1.0 and `StartupWizardCompleted=true`.

These demonstrate retained/configured state presence, not full database
integrity, user-data fidelity or playback acceptance. No SQLite client opened
the live NFS databases and no SQL or user-content export was performed.

## Memory observations and runner shutdown

Samples begin at 19:46:23 UTC. Host available RAM was 21.98 GiB then, briefly
18.36 GiB during cold startup at 19:50, and 20.85 GiB at 20:05. There were no
observed OOM terminations or node memory-pressure conditions. Guest memory
pressure averages were zero at several samples; worker 202 briefly reported
0.10% avg10 / 0.15% avg60 at 20:10, so do not describe every sample as zero.

Before runner shutdown, Terraform, Ansible and Packer had no active runs.
The only remaining Apps check used GitHub-hosted `ubuntu-latest`. VM 300 had an
active listener but no Runner.Worker job process. The guest service was stopped
and verified inactive before `qm shutdown 300`; Proxmox confirmed stopped.

At 20:10:39 UTC host available RAM was **21.80 GiB**. Guest available memory was
approximately 7.94 GiB (master), 12.10 GiB (worker 01), and 11.14 GiB (worker 02).
This meets the immediate 20 GiB launch threshold, not a guarantee of capacity
under future load. Recheck immediately before starting any lab guest. A kernel
journal search since 19:34 UTC found no OOM matches on the host or any K3s
guest; retain that result alongside the sampled node conditions.

The fresh lab preflight found 136.13 GiB allocatable on vm-pool and proposed
IDs 910–913 unused. No test network, VM, disk or NAS configuration was created.
Installers for TrueNAS 25.10.6, K3s 1.37.0+k3s1 and democratic-csi chart 0.15.1
were checksum-verified locally; a complete offline fixture and tested external
shutdown guard are still required.

Evidence: [recovery snapshot](evidence/2026-09-20-cluster-rebuild-recovery.json),
[memory samples](evidence/2026-09-20-cluster-rebuild-memory.json),
[OOM checks](evidence/2026-09-20-cluster-rebuild-oom.json).

At 20:16:50 UTC, the final sample showed **21.83 GiB host available**, runner
300 stopped, zero guest memory-PSI averages and approximately 7.96 / 12.03 /
11.29 GiB available in master / worker 01 / worker 02. The 6 samples span
30.4 minutes; they are periodic observations rather than continuous
monitoring. No pod restart counters increased between the 20:07 and 20:16
snapshots, and all 125 pods remained Ready. The rebuild and RAM-preparation
phase is complete, with no lab started and no claim of peak-load validation.

Lab preparation additionally resolved Linux/amd64 digests for all eight CSI
chart images; their layers have not been downloaded. See the
[image-pin inventory](evidence/2026-09-20-iscsi-lab-csi-image-pins.json).
The official [TrueNAS 25.10 release notes](https://www.truenas.com/docs/scale/25.10/gettingstarted/scalereleasenotes/)
say REST removal is planned for 26, so the WebSocket transition alone does not
establish that this lab pairing is incompatible. Runtime CSI/NAS compatibility
still needs verification in the isolated fixture.

## Remaining acceptance

- The sampled observation window is complete; user-driven playback and peak
  workload acceptance were not performed and remain distinct from node health.
- Preserve current recovery evidence and update it if the optional probe fix
  is merged. The user owns merges and application hostname preferences.
- Complete the isolated-lab implementation, verified image set, management
  isolation, resource guard and cleanup procedure before starting test VMs.
- Recheck the measured 20 GiB launch gate immediately before lab startup.
  No production NAS iSCSI enablement or database migration is authorized here.

Later phase: [isolated retained-iSCSI rehearsal](2026-09-21-retained-iscsi-rehearsal.md). Earlier measurements above remain historical.
