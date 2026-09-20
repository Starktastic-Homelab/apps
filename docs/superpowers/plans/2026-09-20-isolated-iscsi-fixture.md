# Isolated retained-iSCSI fixture implementation plan

> **For agentic workers:** Use superpowers:executing-plans. User authorized continuation after the approved RAM preparation; execute the isolated fixture and rehearsal without repeating production maintenance.

**Goal:** Rehearse retained shared block storage across disposable K3s clusters, then clean up all lab resources.
**Architecture:** Native Proxmox commands create four owned test VMs on private bridges. A small host-side guard enforces resource and ownership bounds; stock TrueNAS, K3s and democratic-csi provide the storage stack.
**Tech Stack:** Python standard library, qm/pvesh, nftables, Helm, Kubernetes admission policies, SQLite.
**Spec:** ../specs/2026-09-20-retained-iscsi-rehearsal-design.md

## Global constraints

- VM IDs910–913 only, unique per-run names/UUIDs, onboot=0, vm-pool disks; never modify production VM100 or200–202.
- RAM8192/2048/1024/1024MiB; require20GiB host available before first boot. Stop lab after host available<6GiB for30s, production memory pressure/OOM, or failed monitoring.
- NAS16GiB boot+16GiB data; Linux6GiB each. Charge staging separately and leave at least80GiB allocatable vm-pool headroom.
- Separate isolated bridges with no uplinks/default gateway/NAT. Drop lab forwarding and unsolicited host access for IPv4/IPv6. Never reload existing host networking.
- Dedicated secrets outside Git; trusted NAS TLS; no production data. User owns PR merges and production storage rollout decisions.

## Review focus

- Reused ID or stale UUID must never stop a foreign VM (guard ownership tests).
- Brief memory dip recovers without shutdown; sustained low memory triggers (clock-injected tests).
- Guard monitor failure must stop owned lab VMs (stale/error tests).
- Cross-network forwarding and unsolicited host access fail in live negative probes.
- Lost onboarding/resize responses never cause replacement allocation (lifecycle negative tests).

### Task 1: Preflight and owned resource guard

Files: tests/iscsi-platform/guard.py, test_guard.py, README.md; private external run manifest.
- [x] Test identity rejection, sustained thresholds, recovery reset, OOM and stale monitoring before implementing.
- [x] Implement bounded graceful shutdown with revalidated lab-only forced-stop fallback.
- [x] Run `python3 -m unittest discover -s tests/iscsi-platform -p 'test_*.py'` and verify failure then success.
- [x] Save current capacity and production health, exact names/UUIDs and disk bill; install guard as transient host service before VM boot.

### Task 2: Isolated fixture

Files: tests/iscsi-platform/README.md and sanitized bill of materials/report.
- [x] Verify all download digests and inspect the pinned TrueNAS installer interface.
- [x] Create only scoped nftables rules/private bridges; test configuration and leave production interfaces untouched.
- [x] Create stopped VMs, verify owner UUIDs, devices, resource limits, absent production NICs/credentials and HA membership.
- [x] Start sequentially with measured memory; install NAS and cloned4GiB Debian template resized upward to6GiB.
- [x] Transfer offline K3s/CSI inputs and initiator packages; verify no production reachability and three Ready nodes.

### Task 3: Retained lifecycle and rebuild

Files: tests/iscsi-platform/manifests, lifecycle.py, test_lifecycle.py, external write ledger.
- [x] Test sanitized export allowlist, wrong identity and missing-data rejection before implementing helper.
- [x] Provision two2GiB volumes, export actual backend identity, apply retention/admission guards and synthetic RWOP writers.
- [ ] Execute design acceptance matrix: replay/admission negatives, movement, partition and approved lab-only fencing, full cluster recreation, interrupted expansion, snapshot and independent backup restore.
- [x] Record each acceptance test as passed/failed/untested with source evidence; do not infer application acceptance from synthetic success.

### Task 4: Cleanup and report

Files: tests/iscsi-platform/README.md and reports/evidence.
- [ ] Stop and delete exact owned VMs/disks; remove only this run's bridges/nft table/guard/listeners/private artifacts.
- [ ] Verify original production identities/health and reconciled capacity; retain source, checksums and sanitized evidence.
- [ ] Run whole-branch review, fix important findings with regression tests, report outcomes and stop.

## Execution ledger

- Ruling: retain80GiB after the50GiB disk ceiling; current136GiB headroom permits the compact fixture. Staging goes on host local storage and is separately limited; unexpected growth stops allocation.
- Ruling: existing4GiB Debian template is cloned and enlarged, never shrunk. Replace inherited networking and cloud-init identity before first boot.
- Production preparation already complete: workers20GiB, runner300stopped, all125pods/77appshealthy; do not repeat it.

- 2026-09-21: owned VMs910–913 installed; TrueNAS25.10.6, K3s1.37.0+k3s1, three Ready nodes. NAS CA-signed HTTPS verified. Nine production-address TCP probes blocked across the three lab nodes. Guard production_ok=true, host available14.3GiB after K3s startup.
- Ruling: K3s requires a default route even with explicit node IPs. Use a dummy interface/default per official air-gap guidance, with no uplink; host forwarding remains blocked. Cost if wrong: lab networking fails, with no production route opened.
- Fixture correction: IDE seed attachment is pending until lab VM power-cycle. Verified pending state, cleanly stopped/started only identity-checked911–913, then seed mounted and all checksums passed.
- API compatibility finding: dedicated CSI user with DATASET_WRITE, DATASET_DELETE, SNAPSHOT_WRITE, SHARING_ISCSI_WRITE authenticates through JSON-RPC but receives403 on all tested REST endpoints. Investigating the pinned REST authorization requirement before CSI deployment.

- Ruling: TrueNAS25.10.6 source explicitly restricts REST to FULL_ADMIN; the dedicated lab CSI account requires that role (403 with granular roles,200 after upgrade). Continue synthetic compatibility tests only; production adoption requires an explicit broad-permission decision or a different supported driver/API path. Cost: compromise of the CSI account controls the entire NAS.
- Ruling: omit optional zvolDedup rather than patch the driver: driver1.9.5 sends unsupported `dedup`; parent and both created volumes verified OFF. Same original claims became Bound without replacement allocation. Cost: parent inheritance must be audited in a production configuration.
- Task3 helper safety checks: five lifecycle tests RED(import missing)→GREEN; guard+lifecycle suite14/14. Both2GiB RWOP claims Bound with distinct CSI handles, targets, extents, serials and ZVOL paths.

- Admission: native CEL type checking clean; six live server-side denial checks passed. Initialization consumed externally once; missing DB and wrong marker fail closed. Second RWOP pod stayed Pending with explicit in-use rejection.
- Drain: service-a moved from worker-a to worker-b after safe eviction; five pre-drain acknowledged transactions per service survived exact-value checks and integrity_check. Post-drain five more transactions per service verified.

- Partition/fence: worker-b control NIC disconnected while storage NIC stayed up; two witness commits returned via authenticated guest agent and were fsynced externally. Node became NotReady with no new writer. VM913 UUID revalidated and power-off confirmed at1789939344.519 before stale pod deletion. Both replacement writers on worker-a passed integrity and all11 acknowledged transactions each. Worker-b remains off until complete recreation.
- Guard parsing regression: Proxmox special cloud-init/snapshot sections were overriding live fields. Added failing test, fixed parser to stop at first section; suite15/15. Running guard retains its original module until planned restart; no current VM identity fields are overridden, and fresh fencing helpers use corrected parser.
- External online backups saved: two16KiB SQLite files outside the NAS, with SHA256 receipts; restoration with NAS unavailable remains pending.

- Snapshot: stock snapshot-controller8.2.1 + CSI sidecar created readyToUse snapshot. Exact restore exception needed the actual binder identity `system:serviceaccount:kube-system:persistent-volume-binder` and dynamic CEL quantity-map access. Restore produced separate handle and ZFS GUID576388407740335325, recovered all11 acknowledged records and integrity. Exception closed afterward.
- Expansion interruption before backend: controller paused; desired3Gi while NAS/PVC remained2Gi. Restarted controller; native retry handled one optimistic-lock conflict. NAS/block device/PVC reached3Gi, ext4 grew, all16 acknowledged records per service verified. Canonical capacity updated only afterward.
- Independent backup: NAS910 verified off at1789940100.3519046. Restored both external online backups to new local files with no NAS access; integrity and all11 backup-time acknowledgements passed. Lab NAS restarted; reconnect verification pending.

- NAS outage: blocked writes resumed after NAS reboot; all21 acknowledged rows per service survived exact checks. iSCSI sessions reconnected without duplicate writers. This is not physical power-loss durability proof.
- Second resize staged: writers scaled0 and unmounted; NAS grew to4GiB, PVC still3GiB/Resizing, last verified filesystem3GiB. External operation receipt records pending reconciliation; canonical recovery record intentionally remains3GiB.
- Full lab cluster replacement starting: verified owned IDs911–913 and only their OS/cloud-init disks; NAS910 disks excluded. Old cluster CA/node/PV/PVC identities saved outside cluster.

- Old lab K3s VM OS/cloud-init disks destroyed; fresh template clones have new SMBIOS UUIDs. Corrected guard restarted with new ownership manifest before any boot. NAS disks preserved and restarted. First fresh-node boot measured23.26GiB host available.

- Second full replacement passed: new VM disks, CA, node/PV/PVC identities; unchanged4Gi/2Gi NAS GUIDs; zero CreateVolume requests. All26 prior acknowledgements per service survived; five post-rebuild writes each verified (31 total per service). Application/PVC removal before this rebuild retained NAS data.
- Acceptance boundary: runtime storage recovery is demonstrated. Actual Argo prune/drift, Sealed Secrets-key restoration, production fencing and exhaustive lost-response cases remain unaccepted; report lists them explicitly. Production rollout remains blocked on supported API/permission design and those gates. Cleanup proceeds rather than extending this constrained fixture into production controllers.
